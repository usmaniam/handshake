"""Deal service: state machine, commit/release flows, payouts, approvals, sweep, webhooks.

Invariants (tested): RELEASING is only entered through _begin_release (compare-and-set), every
transition is audited, terms are immutable after accept, payee always comes from the verified
vendor profile, and the amount paid is always the accepted total.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit
from .config import settings
from .db.models import (Agent, Approval, Deal, DealTerms, DecisionRow, Delivery, Message, Owner, Payout,
                        PaymentRequest, Shipment, Verification, VendorProfile, WebhookEvent)
from .flags import scan
from .paypal import EVENT_STATUS, LEDGER_FROM_PAYPAL, PayPalError, PayPalTransient, Rail
from .policy import ALLOW, APPROVAL, BLOCK, Ctx, PolicyResult, apply_judge, evaluate, explain
from .schemas import DeliveryIn, TermsIn
from .util import canon, dec, jsonable, q2, utcnow
from .verifier import proof_key, verify_delivery
from .verifier.llm import JUDGE_SYSTEM, JudgeResult, LLMError


class DomainError(Exception):
    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg)
        self.status = status


TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"NEGOTIATING"},
    "NEGOTIATING": {"AGREED", "CANCELLED"},
    "AGREED": {"RESERVED", "BLOCKED_AT_COMMIT", "CANCELLED"},
    "RESERVED": {"DELIVERY_CLAIMED", "EXPIRED", "CANCELLED"},
    "DELIVERY_CLAIMED": {"VERIFYING"},
    "VERIFYING": {"RELEASE_CHECK", "HELD_DISPUTED", "OWNER_REVIEW"},
    "RELEASE_CHECK": {"OWNER_REVIEW", "HELD_DISPUTED"},   # RELEASING only via _begin_release
    "OWNER_REVIEW": {"HELD_DISPUTED", "CANCELLED"},
    "HELD_DISPUTED": {"CANCELLED"},
    "PAYOUT_FAILED": {"CANCELLED"},
}
RELEASE_SOURCES = {"RELEASE_CHECK", "OWNER_REVIEW", "HELD_DISPUTED", "PAYOUT_FAILED"}
SPENT = ("RELEASING", "PAID", "PAYOUT_HELD", "PAYOUT_UNCLAIMED")
PAYOUT_STATES = {"RELEASING", "PAID", "PAYOUT_HELD", "PAYOUT_UNCLAIMED", "PAYOUT_FAILED", "PAYOUT_RETURNED"}
PAYOUT_FROM = {  # ledger status -> deal states it may be applied from
    "PAID": {"RELEASING", "PAYOUT_HELD", "PAYOUT_UNCLAIMED", "PAYOUT_FAILED"},
    "PAYOUT_FAILED": {"RELEASING", "PAYOUT_HELD", "PAYOUT_UNCLAIMED"},
    "PAYOUT_HELD": {"RELEASING", "PAYOUT_UNCLAIMED"},
    "PAYOUT_UNCLAIMED": {"RELEASING", "PAYOUT_HELD"},
    "PAYOUT_RETURNED": {"RELEASING", "PAYOUT_HELD", "PAYOUT_UNCLAIMED", "PAYOUT_FAILED", "PAID"},
}


def transition(s: Session, deal: Deal, to: str, actor: str, why: str = "", now=None, **payload) -> None:
    if to not in TRANSITIONS.get(deal.state, set()):
        raise DomainError(f"illegal transition {deal.state} -> {to}")
    frm, deal.state = deal.state, to
    audit.write(s, actor, "deal.transition", "deal", deal.id, {"from": frm, "to": to, "why": why, **payload}, now)


def _party(agent: Agent, deal: Deal) -> str:
    if agent.status != "active":
        raise DomainError("agent is revoked", 403)
    if agent.role == "buyer" and agent.owner_id == deal.owner_id:
        return "buyer"
    if agent.role == "seller" and agent.vendor_profile_id == deal.vendor_profile_id:
        return "seller"
    raise DomainError("not a party to this deal", 403)


def _need(agent: Agent, deal: Deal, role: str) -> None:
    if _party(agent, deal) != role:
        raise DomainError(f"only the {role} agent may do this", 403)


def terms_row(s: Session, deal: Deal, version: int | None) -> DealTerms | None:
    if version is None:
        return None
    return s.scalar(select(DealTerms).where(DealTerms.deal_id == deal.id, DealTerms.version == version))


def _fingerprint(t: TermsIn) -> str:
    d = t.model_dump(mode="json")
    d["unit_price"] = format(t.unit_price.normalize(), "f")
    return hashlib.sha256(canon(d).encode()).hexdigest()


def _add_terms(s: Session, deal: Deal, t: TermsIn, proposer: str, vp: VendorProfile) -> DealTerms:
    ver = deal.current_terms_version + 1
    row = DealTerms(deal_id=deal.id, version=ver, item=t.item, quantity=t.quantity, unit_price=t.unit_price,
                    total=q2(t.quantity * t.unit_price), currency=t.currency, payee_ref=vp.payee_value,
                    payee_hint=t.payee_hint, acceptance_criteria=t.acceptance_criteria, spec=jsonable(t.spec),
                    deliverable_type=t.deliverable_type, deadline=t.deadline, proposed_by=proposer,
                    fingerprint=_fingerprint(t))
    s.add(row)
    deal.current_terms_version = ver
    if deal.accepted_terms_version is None:
        deal.deadline = t.deadline
    s.flush()
    return row


# ---------------------------------------------------------------- negotiation

def create_deal(s: Session, agent: Agent, vendor_id: str, terms: TermsIn, text: str = "", now=None) -> Deal:
    now = now or utcnow()
    if agent.role != "buyer" or agent.status != "active":
        raise DomainError("only an active buyer agent can open a deal", 403)
    vp = s.get(VendorProfile, vendor_id)
    if not vp or vp.owner_id != agent.owner_id or not vp.verified_at:
        raise DomainError("vendor is not a verified profile of this owner", 422)
    deal = Deal(owner_id=agent.owner_id, vendor_profile_id=vp.id, buyer_agent_id=agent.id, state="DRAFT")
    s.add(deal)
    s.flush()
    audit.write(s, agent.id, "deal.created", "deal", deal.id, {"vendor": vp.id}, now)
    transition(s, deal, "NEGOTIATING", agent.id, "opened", now)
    _add_terms(s, deal, terms, agent.id, vp)
    _store_message(s, deal, agent, "offer", text, terms, vp, now)
    return deal


def _store_message(s, deal, agent, mtype, text, terms, vp, now) -> Message:
    extra = [terms.payee_hint] if terms and terms.payee_hint else []
    flags = scan(text, vp.payee_value, extra)
    m = Message(deal_id=deal.id, from_agent=agent.id, type=mtype, content=text,
                terms_json=jsonable(terms.model_dump()) if terms else None,
                provenance="counterparty_agent" if agent.role == "seller" else "agent_plan",
                flagged=bool(flags), flags=flags, ts=now)
    s.add(m)
    s.flush()
    if flags:
        audit.write(s, agent.id, "message.flagged", "message", m.id, {"flags": flags, "deal": deal.id}, now)
    return m


def post_message(s: Session, agent: Agent, deal: Deal, mtype: str, terms: TermsIn | None, text: str, now=None) -> Message:
    now = now or utcnow()
    _party(agent, deal)
    if deal.state in {"CANCELLED", "EXPIRED", "BLOCKED_AT_COMMIT", "PAID", "PAYOUT_RETURNED"}:
        raise DomainError(f"deal is {deal.state}; messaging is closed")
    vp = s.get(VendorProfile, deal.vendor_profile_id)
    if mtype in ("offer", "counter_offer"):
        if not terms:
            raise DomainError("terms required", 422)
        latest = terms_row(s, deal, deal.current_terms_version)
        if deal.state == "NEGOTIATING":
            if latest is None or latest.fingerprint != _fingerprint(terms):
                _add_terms(s, deal, terms, agent.id, vp)
        elif latest is not None and latest.fingerprint != _fingerprint(terms):
            row = _add_terms(s, deal, terms, agent.id, vp)  # new version; accepted version untouched
            audit.write(s, agent.id, "alert.terms_drift", "deal", deal.id,
                        {"accepted": deal.accepted_terms_version, "proposed": row.version}, now)
    elif mtype == "accept":
        if deal.state != "NEGOTIATING":
            raise DomainError("nothing to accept")
        latest = terms_row(s, deal, deal.current_terms_version)
        if latest.proposed_by == agent.id:
            raise DomainError("cannot accept your own offer")
        latest.accepted_at = now
        deal.accepted_terms_version = latest.version
        transition(s, deal, "AGREED", agent.id, "accepted", now, version=latest.version)
    elif mtype == "reject":
        if deal.state != "NEGOTIATING":
            raise DomainError("nothing to reject")
        transition(s, deal, "CANCELLED", agent.id, "rejected", now)
    return _store_message(s, deal, agent, mtype, text, terms, vp, now)


# ---------------------------------------------------------------- policy plumbing

def _cfg(owner: Owner) -> dict:
    d = {"per_tx_cap": 250, "velocity_per_hour": 5, "budget_period_days": 7,
         "allowed_categories": ["packaging", "materials", "creative services"]}
    d.update(owner.settings or {})
    return d


def _existing(s: Session, key: str) -> PaymentRequest | None:
    return s.scalar(select(PaymentRequest).where(PaymentRequest.idempotency_key == key))


def _new_pr(s, owner_id, deal, phase, amount, payee, key, prov) -> PaymentRequest:
    pr = PaymentRequest(owner_id=owner_id, deal_id=deal.id if deal else None, phase=phase, amount=q2(amount),
                        payee_ref=payee, idempotency_key=key, provenance_json=jsonable(prov))
    s.add(pr)
    try:
        s.flush()
    except IntegrityError as e:
        s.rollback()
        raise DomainError("request with this idempotency key is already in progress") from e
    return pr


def ctx_for_pr(s: Session, pr: PaymentRequest, now, owner_approved=False, override=False) -> Ctx:
    owner = s.get(Owner, pr.owner_id)
    cfg = _cfg(owner)
    deal = s.get(Deal, pr.deal_id) if pr.deal_id else None
    prov = pr.provenance_json or {}
    if deal:
        vp = s.get(VendorProfile, deal.vendor_profile_id)
    else:
        vp = s.scalar(select(VendorProfile).where(
            VendorProfile.owner_id == pr.owner_id, func.lower(VendorProfile.payee_value) == (pr.payee_ref or "").lower(),
            VendorProfile.verified_at.is_not(None)))
    since = now - timedelta(days=cfg["budget_period_days"])
    reserved = s.scalar(select(func.coalesce(func.sum(Deal.reserved_amount), 0)).where(
        Deal.owner_id == pr.owner_id, Deal.id != (deal.id if deal else "")))
    spent = s.scalar(select(func.coalesce(func.sum(Payout.amount), 0)).where(
        Payout.owner_id == pr.owner_id, Payout.status.in_(SPENT), Payout.ts >= since))
    recent = s.scalar(select(func.count()).select_from(Payout).where(
        Payout.owner_id == pr.owner_id, Payout.ts >= now - timedelta(hours=1)))
    c = Ctx(phase=pr.phase, amount=dec(pr.amount), claimed_payee=pr.payee_ref,
            profile_payee=vp.payee_value if vp else None, vendor_verified=bool(vp and vp.verified_at),
            vendor_category=vp.category if vp else None, vendor_trust=vp.trust_level if vp else "new",
            committed=dec(reserved) + dec(spent), budget_limit=dec(owner.budget_total), recent_payouts=int(recent),
            velocity_limit=int(cfg["velocity_per_hour"]), cap=dec(cfg["per_tx_cap"]), threshold=dec(owner.approval_threshold),
            categories=[x.lower() for x in cfg["allowed_categories"]], source=prov.get("source", "agent_plan"),
            injection_flagged=bool(prov.get("injection")), owner_approved=owner_approved, owner_override_delivery=override)
    if deal:
        t = terms_row(s, deal, deal.accepted_terms_version)
        c.has_deal, c.terms_amount, c.terms_payee = True, dec(t.total), t.payee_ref
        c.terms_drift = deal.current_terms_version != deal.accepted_terms_version
        c.already_paid = deal.state in PAYOUT_STATES - {"PAYOUT_FAILED"} or bool(s.scalar(
            select(func.count()).select_from(Payout).where(Payout.deal_id == deal.id, Payout.status.in_(SPENT))))
        c.pre_approved = bool(s.scalar(select(func.count()).select_from(Approval).where(
            Approval.deal_id == deal.id, Approval.kind == "commit", Approval.status == "approved")))
        msgs = s.scalars(select(Message).where(Message.deal_id == deal.id, Message.provenance == "counterparty_agent",
                                               Message.flagged.is_(True))).all()
        c.deposit_pressure = any("deposit_pressure" in m.flags for m in msgs)
        c.foreign_payee = any("foreign_payee" in m.flags for m in msgs)
        v = s.scalar(select(Verification).where(Verification.deal_id == deal.id).order_by(Verification.ts.desc()))
        d = s.scalar(select(Delivery).where(Delivery.deal_id == deal.id).order_by(Delivery.ts.desc()))
        if v:
            c.verdict, c.late = v.verdict, v.late
        c.proof_consumed = bool(d and d.consumed)
    return c


def _judge(llm, c: Ctx, res: PolicyResult, excerpts: list[str]) -> dict | None:
    try:
        payload = {"rules": [r.asdict() for r in res.results], "decision": res.decision, "amount": str(c.amount),
                   "untrusted_counterparty_excerpts": excerpts}
        return llm.json(JUDGE_SYSTEM, canon(payload), JudgeResult).model_dump()
    except (LLMError, Exception):  # noqa: BLE001  judge is advisory; failure never loosens anything
        return None


def _decide(s: Session, pr: PaymentRequest, c: Ctx, now, llm=None) -> tuple[DecisionRow, PolicyResult]:
    res = evaluate(c)
    ai = None
    if llm is not None and not c.owner_approved:
        ex = [m.content[:300] for m in s.scalars(select(Message).where(
            Message.deal_id == pr.deal_id, Message.flagged.is_(True)).limit(3))] if pr.deal_id else []
        ai = _judge(llm, c, res, ex)
        if ai:
            new = apply_judge(res.decision, ai["risk"])
            if new != res.decision:
                res.decision, res.explanation = new, explain(new, res.results) + " AI judge flagged elevated risk."
    row = DecisionRow(payment_request_id=pr.id, rule_results=[r.asdict() for r in res.results], ai_result=ai,
                      decision=res.decision, explanation=res.explanation, ts=now)
    s.add(row)
    s.flush()
    audit.write(s, "policy", "decision.recorded", "decision", row.id,
                {"pr": pr.id, "phase": pr.phase, "decision": res.decision}, now)
    return row, res


def _payout_view(p: Payout | None) -> dict | None:
    return None if p is None else {"id": p.id, "status": p.status, "paypal_status": p.paypal_status,
                                   "amount": str(p.amount), "receiver": p.receiver, "batch_id": p.paypal_batch_id}


def _result(s: Session, pr: PaymentRequest) -> dict:
    d = s.scalar(select(DecisionRow).where(DecisionRow.payment_request_id == pr.id))
    a = s.scalar(select(Approval).where(Approval.payment_request_id == pr.id))
    p = s.scalar(select(Payout).where(Payout.payment_request_id == pr.id).order_by(Payout.ts.desc()))
    deal = s.get(Deal, pr.deal_id) if pr.deal_id else None
    return {"payment_request_id": pr.id, "phase": pr.phase, "decision": d.decision, "decision_id": d.id,
            "explanation": d.explanation, "rules": d.rule_results, "deal_state": deal.state if deal else None,
            "approval_id": a.id if a else None, "approval_status": a.status if a else None, "payout": _payout_view(p)}


def _request_approval(s, deal, pr, row, now) -> Approval:
    a = Approval(decision_id=row.id, payment_request_id=pr.id, deal_id=deal.id if deal else None, kind=pr.phase)
    s.add(a)
    s.flush()
    audit.write(s, "policy", "approval.requested", "approval", a.id, {"pr": pr.id, "kind": pr.phase}, now)
    return a


# ---------------------------------------------------------------- commit

def _reserve(s, deal, t, actor, now) -> None:
    deal.reserved_amount = t.total
    transition(s, deal, "RESERVED", actor, "budget reserved", now, amount=str(t.total))


def commit(s: Session, agent: Agent, deal: Deal, key: str, now=None, llm=None) -> dict:
    now = now or utcnow()
    _need(agent, deal, "buyer")
    idem = f"{deal.id}:commit:{key}"
    if (old := _existing(s, idem)):
        return _result(s, old)
    if deal.state != "AGREED":
        raise DomainError(f"deal is {deal.state}; commit requires AGREED")
    if s.scalar(select(func.count()).select_from(Approval).where(
            Approval.deal_id == deal.id, Approval.kind == "commit", Approval.status == "pending")):
        raise DomainError("a commit approval is already pending")
    t = terms_row(s, deal, deal.accepted_terms_version)
    pr = _new_pr(s, deal.owner_id, deal, "commit", t.total, None, idem, {"source": "agent_plan"})
    row, res = _decide(s, pr, ctx_for_pr(s, pr, now), now, llm)
    if res.decision == ALLOW:
        _reserve(s, deal, t, agent.id, now)
    elif res.decision == APPROVAL:
        _request_approval(s, deal, pr, row, now)
    else:
        transition(s, deal, "BLOCKED_AT_COMMIT", "policy", res.explanation, now)
        audit.write(s, "policy", "alert.commit_blocked", "deal", deal.id, {"why": res.explanation}, now)
    return _result(s, pr)


# ---------------------------------------------------------------- delivery

def expire_if_overdue(s: Session, deal: Deal, now) -> bool:
    if deal.state == "RESERVED" and deal.deadline and now.date() > deal.deadline + timedelta(days=settings().expiry_grace_days):
        deal.reserved_amount = Decimal(0)
        transition(s, deal, "EXPIRED", "system", "deadline passed without delivery", now)
        audit.write(s, "system", "alert.deal_expired", "deal", deal.id, {"owner": deal.owner_id}, now)
        return True
    return False


def submit_delivery(s: Session, agent: Agent, deal: Deal, body: DeliveryIn, now=None, llm=None) -> dict:
    now = now or utcnow()
    _need(agent, deal, "seller")
    if expire_if_overdue(s, deal, now):
        raise DomainError("deal expired before delivery; budget returned")
    if deal.state != "RESERVED":
        raise DomainError(f"deal is {deal.state}; delivery requires RESERVED (budget reserved)")
    t = terms_row(s, deal, deal.accepted_terms_version)
    proof = body.model_dump()
    if proof.get("tracking_number"):
        proof["tracking_number"] = proof["tracking_number"].strip().upper()
    pk = proof_key(proof)
    consumed = bool(s.scalar(select(func.count()).select_from(Delivery).where(
        Delivery.proof_key == pk, Delivery.deal_id != deal.id)))
    d = Delivery(deal_id=deal.id, submitted_by=agent.id, proof_type=body.proof_type, proof_json=jsonable(proof),
                 proof_key=pk, consumed=consumed, ts=now)
    s.add(d)
    s.flush()
    transition(s, deal, "DELIVERY_CLAIMED", agent.id, "proof submitted", now)
    transition(s, deal, "VERIFYING", "verifier", "", now)
    ship = s.get(Shipment, proof["tracking_number"]) if proof.get("tracking_number") else None
    if t.deliverable_type == "physical_goods" and body.proof_type != "carrier_tracking":
        ship = None
    out = verify_delivery(t, proof, ship, consumed, now.date(), llm)
    v = Verification(delivery_id=d.id, deal_id=deal.id, deterministic=jsonable(out["deterministic"]),
                     llm=jsonable(out["llm"]), verdict=out["verdict"], reasons=out["reasons"], late=out["late"], ts=now)
    s.add(v)
    s.flush()
    nxt = {"PASS": "RELEASE_CHECK", "FAIL": "HELD_DISPUTED", "NEEDS_REVIEW": "OWNER_REVIEW"}[out["verdict"]]
    transition(s, deal, nxt, "verifier", "; ".join(out["reasons"]) or "all checks passed", now, verdict=out["verdict"])
    if out["flags"]:
        audit.write(s, "verifier", "alert.deliverable_flagged", "delivery", d.id, {"flags": out["flags"]}, now)
    return {"verification_id": v.id, "verdict": out["verdict"], "reasons": out["reasons"], "flags": out["flags"],
            "deal_state": deal.state}


# ---------------------------------------------------------------- release & payout

def _begin_release(s: Session, deal: Deal, via: str, now) -> None:
    if deal.state not in RELEASE_SOURCES:
        raise DomainError(f"cannot release from {deal.state}")
    if deal.state != "RELEASE_CHECK" and via not in ("approval", "owner_override", "retry"):
        raise DomainError("release from this state needs an owner decision", 403)
    frm = deal.state
    r = s.execute(update(Deal).where(Deal.id == deal.id, Deal.state == frm).values(state="RELEASING", reserved_amount=0))
    if r.rowcount != 1:
        raise DomainError("deal state changed concurrently; release not started")
    s.refresh(deal)
    audit.write(s, "policy", "deal.transition", "deal", deal.id, {"from": frm, "to": "RELEASING", "via": via}, now)


def _pay(s: Session, pr: PaymentRequest, deal: Deal | None, receiver: str, rtype: str, amount: Decimal,
         rail: Rail, via: str, now) -> Payout:
    if deal is not None:
        _begin_release(s, deal, via, now)
    n = s.scalar(select(func.count()).select_from(Payout).where(
        Payout.deal_id == deal.id if deal else Payout.payment_request_id == pr.id)) + 1
    sbid = f"hs_{deal.id}_release_{n}" if deal else f"hs_{pr.id}"
    p = Payout(owner_id=pr.owner_id, deal_id=deal.id if deal else None, payment_request_id=pr.id, sender_batch_id=sbid,
               amount=amount, currency=pr.currency, receiver=receiver, recipient_type=rtype, ts=now)
    s.add(p)
    s.commit()  # durable BEFORE the network call; a crash leaves a RELEASING row that sweep() re-sends safely
    _send(s, p, rail, now)
    return p


def _send(s: Session, p: Payout, rail: Rail, now) -> None:
    try:
        r = rail.send_payout(sender_batch_id=p.sender_batch_id, receiver=p.receiver, recipient_type=p.recipient_type,
                             amount=f"{p.amount:.2f}", currency=p.currency,
                             note=f"Handshake {p.deal_id or p.payment_request_id}", sender_item_id=p.id)
    except PayPalTransient as e:
        audit.write(s, "paypal", "payout.transient_error", "payout", p.id, {"error": str(e)[:200]}, now)
        s.commit()
        return
    except PayPalError as e:
        apply_payout_status(s, p, "FAILED", {"error": str(e), "body": e.body}, now)
        s.commit()
        return
    p.paypal_batch_id, p.paypal_status = r["batch_id"], r["batch_status"]
    audit.write(s, "paypal", "payout.sent", "payout", p.id, {"batch": r["batch_id"], "sender_batch_id": p.sender_batch_id}, now)
    s.commit()
    try:
        sync_batch(s, p, rail, now)
    except (PayPalError, PayPalTransient, KeyError):
        pass  # webhook or sweep will catch up
    s.commit()


def sync_batch(s: Session, p: Payout, rail: Rail, now) -> None:
    j = rail.get_payout(p.paypal_batch_id)
    item = next((i for i in j["items"] if i.get("sender_item_id") == p.id), (j["items"] or [None])[0])
    if item:
        p.paypal_item_id = item.get("item_id") or p.paypal_item_id
        apply_payout_status(s, p, item.get("status") or j["batch_status"], j, now)


def apply_payout_status(s: Session, p: Payout, paypal_status: str, raw: Any = None, now=None) -> None:
    now = now or utcnow()
    ledger = LEDGER_FROM_PAYPAL.get((paypal_status or "").upper())
    if ledger is None:
        audit.write(s, "paypal", "payout.unknown_status", "payout", p.id, {"status": paypal_status}, now)
        return
    if p.status == "PAID" and ledger != "PAYOUT_RETURNED":
        return  # stale / out-of-order event
    p.paypal_status, p.status = paypal_status.upper(), ledger
    if raw is not None:
        p.raw = jsonable(raw)
    audit.write(s, "paypal", "payout.status", "payout", p.id, {"paypal": paypal_status, "ledger": ledger}, now)
    deal = s.get(Deal, p.deal_id) if p.deal_id else None
    if not deal or ledger == "RELEASING" or deal.state not in PAYOUT_FROM.get(ledger, set()):
        return
    deal.state = ledger
    if ledger == "PAID":
        deal.paid_amount, deal.reserved_amount, deal.paid_at = p.amount, Decimal(0), now
    elif ledger == "PAYOUT_FAILED":
        deal.reserved_amount = p.amount  # budget stays reserved until retry/cancel
    elif ledger == "PAYOUT_RETURNED":
        deal.paid_amount = deal.reserved_amount = Decimal(0)  # budget returned
    audit.write(s, "paypal", "deal.transition", "deal", deal.id, {"to": ledger, "payout": p.id}, now)
    if ledger in ("PAYOUT_HELD", "PAYOUT_FAILED", "PAYOUT_UNCLAIMED"):
        audit.write(s, "paypal", "alert.payout_attention", "deal", deal.id, {"status": ledger}, now)


def _receiver(s: Session, deal: Deal | None, pr: PaymentRequest) -> tuple[str, str]:
    """Payee ALWAYS comes from the verified vendor profile, never from the request."""
    if deal:
        vp = s.get(VendorProfile, deal.vendor_profile_id)
    else:
        vp = s.scalar(select(VendorProfile).where(VendorProfile.owner_id == pr.owner_id,
                      func.lower(VendorProfile.payee_value) == (pr.payee_ref or "").lower(),
                      VendorProfile.verified_at.is_not(None)))
    if not vp:
        raise DomainError("no verified payee", 422)
    return vp.payee_value, vp.payee_type


def _act_release(s, deal, pr, row, res, rail, now, via="release_check") -> dict:
    if res.decision == ALLOW:
        recv, rtype = _receiver(s, deal, pr)
        t = terms_row(s, deal, deal.accepted_terms_version) if deal else None
        _pay(s, pr, deal, recv, rtype, t.total if t else dec(pr.amount), rail, via, now)
    elif res.decision == APPROVAL:
        if deal and deal.state == "RELEASE_CHECK":
            transition(s, deal, "OWNER_REVIEW", "policy", res.explanation, now)
        _request_approval(s, deal, pr, row, now)
    elif res.decision == BLOCK:
        if deal and deal.state == "RELEASE_CHECK":
            transition(s, deal, "HELD_DISPUTED", "policy", res.explanation, now)
        audit.write(s, "policy", "alert.release_blocked", "deal", deal.id if deal else pr.id, {"why": res.explanation}, now)
    return _result(s, pr)


def release(s: Session, agent: Agent, deal: Deal, key: str, claimed_amount: Decimal | None, claimed_payee: str | None,
            rail: Rail, now=None, llm=None) -> dict:
    now = now or utcnow()
    _need(agent, deal, "buyer")
    idem = f"{deal.id}:release:{key}"
    if (old := _existing(s, idem)):
        return _result(s, old)
    t = terms_row(s, deal, deal.accepted_terms_version)
    if t is None:
        raise DomainError("deal has no accepted terms")
    pr = _new_pr(s, deal.owner_id, deal, "release", claimed_amount if claimed_amount is not None else t.total,
                 claimed_payee, idem, {"source": "agent_plan"})
    row, res = _decide(s, pr, ctx_for_pr(s, pr, now), now, llm)
    return _act_release(s, deal, pr, row, res, rail, now)


def payment_request(s: Session, agent: Agent, body, key: str, rail: Rail, now=None, llm=None) -> dict:
    """Direct payment request (non-deal payments and the benchmark's guarded path)."""
    now = now or utcnow()
    if agent.role != "buyer" or agent.status != "active":
        raise DomainError("only an active buyer agent may request payments", 403)
    idem = f"{agent.id}:direct:{key}"
    if (old := _existing(s, idem)):
        return _result(s, old)
    deal = None
    if body.deal_id:
        deal = s.get(Deal, body.deal_id)
        if not deal:
            raise DomainError("unknown deal", 404)
        _need(agent, deal, "buyer")
    elif agent.owner_id is None:
        raise DomainError("no owner", 403)
    inj = "prompt_injection" in scan(body.source_text + " " + body.memo)
    pr = _new_pr(s, agent.owner_id, deal, "direct", body.amount, body.payee, idem,
                 {"source": body.instruction_source, "injection": inj, "memo": body.memo[:500]})
    row, res = _decide(s, pr, ctx_for_pr(s, pr, now), now, llm)
    if res.decision == ALLOW and deal is None:
        recv, rtype = _receiver(s, None, pr)
        _pay(s, pr, None, recv, rtype, dec(pr.amount), rail, "direct", now)
        return _result(s, pr)
    if res.decision == ALLOW and deal is not None:
        return _act_release(s, deal, pr, row, res, rail, now)
    if res.decision == APPROVAL:
        _request_approval(s, deal, pr, row, now)
    elif res.decision == BLOCK:
        audit.write(s, "policy", "alert.payment_blocked", "payment_request", pr.id, {"why": res.explanation}, now)
        if deal is not None and deal.state == "RELEASE_CHECK":
            transition(s, deal, "HELD_DISPUTED", "policy", res.explanation, now)
    return _result(s, pr)


# ---------------------------------------------------------------- owner decisions

def decide_approval(s: Session, approval_id: str, approve: bool, who: str, reason: str, rail: Rail, now=None) -> dict:
    now = now or utcnow()
    a = s.get(Approval, approval_id)
    if not a:
        raise DomainError("approval not found", 404)
    if a.status != "pending":
        raise DomainError(f"approval already {a.status}")
    pr = s.get(PaymentRequest, a.payment_request_id)
    deal = s.get(Deal, a.deal_id) if a.deal_id else None
    a.decided_by, a.reason, a.ts = who, reason, now
    if not approve:
        a.status = "denied"
        audit.write(s, who, "approval.denied", "approval", a.id, {"reason": reason}, now)
        if deal and a.kind == "commit":
            transition(s, deal, "CANCELLED", who, "commit denied", now)
        elif deal and a.kind == "release" and deal.state == "OWNER_REVIEW":
            transition(s, deal, "HELD_DISPUTED", who, "release denied", now)
        return _result(s, pr)
    a.status = "approved"  # re-evaluate: approval satisfies approval-type rules only; hard rules still apply
    res = evaluate(ctx_for_pr(s, pr, now, owner_approved=True))
    if res.decision != ALLOW:
        a.status = "denied"
        a.reason = f"approved but hard rules now fail: {res.explanation}"
        audit.write(s, who, "approval.invalidated", "approval", a.id, {"why": res.explanation}, now)
        raise DomainError(f"cannot proceed: {res.explanation}")
    audit.write(s, who, "approval.approved", "approval", a.id, {"reason": reason, "kind": a.kind}, now)
    if a.kind == "commit":
        _reserve(s, deal, terms_row(s, deal, deal.accepted_terms_version), who, now)
    elif a.kind == "release":
        _pay(s, pr, deal, *_receiver(s, deal, pr), terms_row(s, deal, deal.accepted_terms_version).total, rail, "approval", now)
    else:
        if deal is not None:
            _pay(s, pr, deal, *_receiver(s, deal, pr), terms_row(s, deal, deal.accepted_terms_version).total, rail, "approval", now)
        else:
            _pay(s, pr, None, *_receiver(s, None, pr), dec(pr.amount), rail, "approval", now)
    return _result(s, pr)


def resolve(s: Session, deal: Deal, action: str, who: str, reason: str, rail: Rail, now=None) -> dict:
    """Owner decision on OWNER_REVIEW / HELD_DISPUTED / PAYOUT_FAILED deals."""
    now = now or utcnow()
    if action == "cancel":
        if deal.state not in {"OWNER_REVIEW", "HELD_DISPUTED", "PAYOUT_FAILED", "RESERVED"}:
            raise DomainError(f"cannot cancel from {deal.state}")
        if deal.state == "RESERVED":
            transition(s, deal, "CANCELLED", who, reason or "owner cancelled", now)
        else:
            transition(s, deal, "CANCELLED", who, reason or "owner cancelled", now)
        deal.reserved_amount = Decimal(0)
        return {"deal_state": deal.state}
    if deal.state not in {"OWNER_REVIEW", "HELD_DISPUTED", "PAYOUT_FAILED"}:
        raise DomainError(f"cannot {action} from {deal.state}")
    via = "retry" if deal.state == "PAYOUT_FAILED" else "owner_override"
    audit.write(s, who, f"owner.{action}", "deal", deal.id, {"reason": reason, "from": deal.state}, now)
    t = terms_row(s, deal, deal.accepted_terms_version)
    pr = _new_pr(s, deal.owner_id, deal, "release", t.total, None, f"{deal.id}:release:owner:{uuid.uuid4().hex[:10]}",
                 {"source": "owner"})
    row = None
    ctx = ctx_for_pr(s, pr, now, owner_approved=True, override=True)
    ctx.already_paid = ctx.already_paid and deal.state != "PAYOUT_FAILED"
    res = evaluate(ctx)
    row = DecisionRow(payment_request_id=pr.id, rule_results=[r.asdict() for r in res.results], decision=res.decision,
                      explanation=res.explanation, ts=now)
    s.add(row)
    s.flush()
    if res.decision != ALLOW:
        raise DomainError(f"hard rule prevents release: {res.explanation}")
    return _act_release(s, deal, pr, row, res, rail, now, via=via)


# ---------------------------------------------------------------- sweep & webhooks

def sweep(s: Session, rail: Rail, now=None) -> dict:
    now = now or utcnow()
    expired = [d.id for d in s.scalars(select(Deal).where(Deal.state == "RESERVED")) if expire_if_overdue(s, d, now)]
    resent = synced = 0
    for p in s.scalars(select(Payout).where(Payout.status.in_(("RELEASING", "PAYOUT_HELD", "PAYOUT_UNCLAIMED")))):
        try:
            if p.paypal_batch_id is None:
                _send(s, p, rail, now)  # same sender_batch_id / PayPal-Request-Id: safe to repeat
                resent += 1
            else:
                sync_batch(s, p, rail, now)
                synced += 1
        except (PayPalError, PayPalTransient, KeyError):
            continue
    s.commit()
    return {"expired": expired, "resent": resent, "synced": synced}


def _find_payout(s: Session, res: dict) -> Payout | None:
    item_id, batch_id = res.get("payout_item_id"), res.get("payout_batch_id")
    sender = (res.get("payout_item") or {}).get("sender_item_id")
    for col, val in ((Payout.paypal_item_id, item_id), (Payout.id, sender), (Payout.paypal_batch_id, batch_id)):
        if val and (p := s.scalar(select(Payout).where(col == val))):
            return p
    return None


def handle_webhook(s: Session, headers: Any, raw: bytes, rail: Rail, now=None) -> dict:
    now = now or utcnow()
    if not rail.verify_webhook(headers, raw):
        raise DomainError("webhook signature verification failed", 400)
    ev = json.loads(raw)
    eid = ev.get("id")
    if not eid:
        raise DomainError("event has no id", 400)
    s.add(WebhookEvent(paypal_event_id=eid, event_type=ev.get("event_type", ""), verified=True, payload=ev))
    try:
        s.flush()
    except IntegrityError:
        s.rollback()
        return {"status": "duplicate"}
    et, res = ev.get("event_type", ""), ev.get("resource") or {}
    status = "ignored"
    if et.startswith("PAYMENT.PAYOUTS-ITEM."):
        p = _find_payout(s, res)
        if p and et in EVENT_STATUS:
            p.paypal_item_id = p.paypal_item_id or res.get("payout_item_id")
            apply_payout_status(s, p, EVENT_STATUS[et], ev, now)
            status = "processed"
    elif et.startswith("PAYMENT.PAYOUTSBATCH."):
        bid = (res.get("batch_header") or {}).get("payout_batch_id")
        p = s.scalar(select(Payout).where(Payout.paypal_batch_id == bid)) if bid else None
        if p:
            if et.endswith("DENIED"):
                apply_payout_status(s, p, "DENIED", ev, now)
            else:
                try:
                    sync_batch(s, p, rail, now)
                except (PayPalError, PayPalTransient, KeyError):
                    pass
            status = "processed"
    row = s.scalar(select(WebhookEvent).where(WebhookEvent.paypal_event_id == eid))
    row.processed_at = now
    s.commit()
    return {"status": status}


# ---------------------------------------------------------------- views

def deal_view(s: Session, deal: Deal) -> dict:
    cur, acc = terms_row(s, deal, deal.current_terms_version), terms_row(s, deal, deal.accepted_terms_version)
    v = s.scalar(select(Verification).where(Verification.deal_id == deal.id).order_by(Verification.ts.desc()))

    def tv(t):
        return None if t is None else {"version": t.version, "item": t.item, "quantity": t.quantity,
                                       "unit_price": str(t.unit_price), "total": str(t.total), "deadline": t.deadline.isoformat(),
                                       "deliverable_type": t.deliverable_type, "acceptance_criteria": t.acceptance_criteria,
                                       "accepted": t.accepted_at is not None}
    vp = s.get(VendorProfile, deal.vendor_profile_id)
    return {"id": deal.id, "state": deal.state, "vendor": vp.name if vp else None,
            "created_at": deal.created_at.isoformat(), "reserved_amount": str(deal.reserved_amount), "paid_amount": str(deal.paid_amount),
            "current_terms": tv(cur), "accepted_terms": tv(acc),
            "verification": None if not v else {"verdict": v.verdict, "reasons": v.reasons, "checks": v.deterministic.get("checks", []),
                                                "llm": v.llm}}
