from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, service
from ..db import get_session
from ..db.models import (Agent, Approval, VendorProfile, AuditLog, BenchRun, Deal, DecisionRow, Message, Owner, PaymentRequest, Payout)
from ..schemas import ApprovalDecision, ResolveIn
from ..util import dec, utcnow
from .deps import owner_auth, rail_dep

router = APIRouter(prefix="/v1", tags=["owner console"])


@router.get("/owner/summary")
def summary(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    cfg = service._cfg(o)
    since = utcnow() - timedelta(days=cfg["budget_period_days"])
    reserved = dec(s.scalar(select(func.coalesce(func.sum(Deal.reserved_amount), 0)).where(Deal.owner_id == o.id)))
    spent = dec(s.scalar(select(func.coalesce(func.sum(Payout.amount), 0)).where(
        Payout.owner_id == o.id, Payout.status.in_(service.SPENT), Payout.ts >= since)))
    blocked = dec(s.scalar(select(func.coalesce(func.sum(PaymentRequest.amount), 0)).join(
        DecisionRow, DecisionRow.payment_request_id == PaymentRequest.id).where(
        PaymentRequest.owner_id == o.id, DecisionRow.decision == "BLOCK")))
    pending = s.scalar(select(func.count()).select_from(Approval).join(
        PaymentRequest, PaymentRequest.id == Approval.payment_request_id).where(
        PaymentRequest.owner_id == o.id, Approval.status == "pending"))
    return {"owner": o.name, "budget_total": str(o.budget_total), "reserved": str(reserved), "spent": str(spent),
            "available": str(dec(o.budget_total) - reserved - spent), "blocked_amount": str(blocked),
            "pending_approvals": pending, "settings": cfg, "approval_threshold": str(o.approval_threshold)}


@router.get("/owner/deals")
def deals(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    rows = s.scalars(select(Deal).where(Deal.owner_id == o.id).order_by(Deal.created_at.desc())).all()
    return [service.deal_view(s, d) for d in rows]


@router.get("/owner/deals/{deal_id}")
def deal_detail(deal_id: str, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    d = s.get(Deal, deal_id)
    if not d or d.owner_id != o.id:
        raise service.DomainError("deal not found", 404)
    out = service.deal_view(s, d)
    names = {a.id: a for a in s.scalars(select(Agent).where(Agent.owner_id == o.id))}
    out["messages"] = [{"id": m.id, "from": m.from_agent, "from_name": names[m.from_agent].name if m.from_agent in names else m.from_agent,
                        "role": names[m.from_agent].role if m.from_agent in names else None, "type": m.type, "text": m.content,
                        "flags": m.flags, "provenance": m.provenance, "ts": m.ts.isoformat()}
                       for m in s.scalars(select(Message).where(Message.deal_id == d.id).order_by(Message.ts))]
    out["timeline"] = [{"ts": a.ts, "event": a.event, "payload": a.payload} for a in s.scalars(
        select(AuditLog).where(AuditLog.ref_type == "deal", AuditLog.ref_id == d.id).order_by(AuditLog.id))]
    return out


@router.get("/owner/ledger")
def ledger(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    out = []
    vend = dict(s.execute(select(Deal.id, VendorProfile.name).join(VendorProfile, VendorProfile.id == Deal.vendor_profile_id)
                          .where(Deal.owner_id == o.id)).all())
    q = select(PaymentRequest).where(PaymentRequest.owner_id == o.id).order_by(PaymentRequest.ts.desc()).limit(500)
    for pr in s.scalars(q):
        d = s.scalar(select(DecisionRow).where(DecisionRow.payment_request_id == pr.id))
        p = s.scalar(select(Payout).where(Payout.payment_request_id == pr.id).order_by(Payout.ts.desc()))
        out.append({"ts": pr.ts.isoformat(), "payment_request_id": pr.id, "deal_id": pr.deal_id, "vendor": vend.get(pr.deal_id), "phase": pr.phase,
                    "amount": str(pr.amount), "payee": pr.payee_ref, "decision": d.decision if d else None,
                    "decision_id": d.id if d else None, "explanation": d.explanation if d else None,
                    "payout_status": p.status if p else None, "paypal_status": p.paypal_status if p else None,
                    "paypal_batch_id": p.paypal_batch_id if p else None})
    return out


@router.get("/owner/decisions/{decision_id}")
def decision(decision_id: str, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    d = s.get(DecisionRow, decision_id)
    pr = s.get(PaymentRequest, d.payment_request_id) if d else None
    if not d or pr.owner_id != o.id:
        raise service.DomainError("decision not found", 404)
    return {"id": d.id, "decision": d.decision, "explanation": d.explanation, "rules": d.rule_results, "ai": d.ai_result,
            "request": {"id": pr.id, "phase": pr.phase, "amount": str(pr.amount), "payee": pr.payee_ref, "deal_id": pr.deal_id,
                        "provenance": pr.provenance_json}}


@router.get("/owner/approvals")
def approvals(status: str = "pending", o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    q = select(Approval, PaymentRequest, DecisionRow).join(PaymentRequest, PaymentRequest.id == Approval.payment_request_id).join(
        DecisionRow, DecisionRow.id == Approval.decision_id).where(PaymentRequest.owner_id == o.id, Approval.status == status)
    vend = dict(s.execute(select(Deal.id, VendorProfile.name).join(VendorProfile, VendorProfile.id == Deal.vendor_profile_id)).all())
    return [{"id": a.id, "kind": a.kind, "deal_id": a.deal_id, "vendor": vend.get(a.deal_id), "amount": str(pr.amount),
             "reason": d.explanation, "status": a.status, "ts": a.ts.isoformat()} for a, pr, d in s.execute(q)]


@router.post("/owner/approvals/{approval_id}")
def decide(approval_id: str, body: ApprovalDecision, o: Owner = Depends(owner_auth), s: Session = Depends(get_session),
           rail=Depends(rail_dep)):
    a = s.get(Approval, approval_id)
    pr = s.get(PaymentRequest, a.payment_request_id) if a else None
    if not a or pr.owner_id != o.id:
        raise service.DomainError("approval not found", 404)
    out = service.decide_approval(s, approval_id, body.approve, f"owner:{o.id}", body.reason, rail)
    s.commit()
    return out


@router.post("/owner/deals/{deal_id}/resolve")
def resolve(deal_id: str, body: ResolveIn, o: Owner = Depends(owner_auth), s: Session = Depends(get_session), rail=Depends(rail_dep)):
    d = s.get(Deal, deal_id)
    if not d or d.owner_id != o.id:
        raise service.DomainError("deal not found", 404)
    out = service.resolve(s, d, body.action, f"owner:{o.id}", body.reason, rail)
    s.commit()
    return out


@router.put("/owner/policy")
def set_policy(body: dict, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    allowed = {"per_tx_cap", "velocity_per_hour", "budget_period_days", "allowed_categories"}
    bad = set(body) - allowed - {"budget_total", "approval_threshold"}
    if bad:
        raise service.DomainError(f"unknown policy keys: {sorted(bad)}", 422)
    if "budget_total" in body:
        o.budget_total = Decimal(str(body["budget_total"]))
    if "approval_threshold" in body:
        o.approval_threshold = Decimal(str(body["approval_threshold"]))
    o.settings = {**(o.settings or {}), **{k: v for k, v in body.items() if k in allowed}}
    audit.write(s, f"owner:{o.id}", "policy.updated", "owner", o.id, body)
    s.commit()
    return {"ok": True, "settings": service._cfg(o)}


@router.get("/owner/vendors")
def vendors(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    return [{"id": v.id, "name": v.name, "category": v.category, "trust_level": v.trust_level, "payee": v.payee_value,
             "verified": v.verified_at is not None} for v in s.scalars(select(VendorProfile).where(VendorProfile.owner_id == o.id))]


@router.get("/owner/agents")
def agents(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    return [{"id": a.id, "name": a.name, "role": a.role, "status": a.status} for a in s.scalars(
        select(Agent).where(Agent.owner_id == o.id))]


@router.post("/owner/agents/{agent_id}/revoke")
def revoke(agent_id: str, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    a = s.get(Agent, agent_id)
    if not a or a.owner_id != o.id:
        raise service.DomainError("agent not found", 404)
    a.status = "revoked"
    audit.write(s, f"owner:{o.id}", "agent.revoked", "agent", a.id, {})
    s.commit()
    return {"id": a.id, "status": a.status}


@router.get("/owner/audit/verify")
def audit_verify(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    return audit.verify(s)


@router.post("/owner/sweep")
def sweep(o: Owner = Depends(owner_auth), s: Session = Depends(get_session), rail=Depends(rail_dep)):
    return service.sweep(s, rail)


@router.post("/bench/run")
def bench_run(o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    from ..bench import run_all
    res = run_all()
    row = BenchRun(results=res)
    s.add(row)
    s.commit()
    return {"id": row.id, **res}


@router.get("/bench/runs/{run_id}")
def bench_get(run_id: str, o: Owner = Depends(owner_auth), s: Session = Depends(get_session)):
    r = s.get(BenchRun, run_id)
    if not r:
        raise service.DomainError("run not found", 404)
    return {"id": r.id, "ts": r.ts.isoformat(), **r.results}
