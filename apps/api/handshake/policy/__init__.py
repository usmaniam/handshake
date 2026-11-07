"""Deterministic policy engine. Pure functions; the LLM may only make outcomes stricter."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ALLOW, APPROVAL, HOLD, BLOCK, PASS = "ALLOW", "REQUIRE_APPROVAL", "HOLD", "BLOCK", "PASS"
ORDER = {PASS: 0, ALLOW: 0, APPROVAL: 1, HOLD: 2, BLOCK: 3}
UNTRUSTED = {"counterparty_agent", "vendor_email", "web_content"}


@dataclass
class Ctx:
    phase: str                       # commit | release | direct
    amount: Decimal
    claimed_payee: str | None = None
    profile_payee: str | None = None  # verified vendor-profile payee
    vendor_verified: bool = False
    vendor_category: str | None = None
    vendor_trust: str = "known"
    has_deal: bool = False
    terms_amount: Decimal | None = None
    terms_payee: str | None = None
    terms_drift: bool = False
    verdict: str | None = None       # latest verification verdict
    proof_consumed: bool = False
    late: bool = False
    already_paid: bool = False
    committed: Decimal = Decimal(0)  # reserved + spent in window, excluding this deal
    budget_limit: Decimal = Decimal(600)
    recent_payouts: int = 0
    velocity_limit: int = 5
    cap: Decimal = Decimal(250)
    threshold: Decimal = Decimal(100)
    categories: list[str] = field(default_factory=lambda: ["packaging", "materials", "creative services"])
    deposit_pressure: bool = False
    foreign_payee: bool = False
    source: str = "agent_plan"
    injection_flagged: bool = False
    owner_approved: bool = False
    owner_override_delivery: bool = False
    pre_approved: bool = False       # owner already approved this deal's amount at commit


@dataclass
class RuleResult:
    rule: str
    outcome: str
    detail: str

    def asdict(self) -> dict:
        return {"rule": self.rule, "outcome": self.outcome, "detail": self.detail}


@dataclass
class PolicyResult:
    decision: str
    results: list[RuleResult]
    explanation: str


def escalate(d: str) -> str:
    return {ALLOW: APPROVAL, APPROVAL: BLOCK}.get(d, d)


def explain(decision: str, results: list[RuleResult]) -> str:
    head = {ALLOW: "Allowed by policy.", APPROVAL: "Needs your approval.",
            HOLD: "Payment held.", BLOCK: "Blocked."}[decision]
    bad = [f"{r.rule}: {r.detail}" for r in results if r.outcome != PASS]
    return head + (" " + "; ".join(bad) + "." if bad else "")


def evaluate(c: Ctx) -> PolicyResult:
    out: list[RuleResult] = []

    def chk(rule: str, bad: bool, on_fail: str, msg: str) -> None:
        out.append(RuleResult(rule, on_fail if bad else PASS, msg if bad else "ok"))

    ph = c.phase
    chk("per_transaction_cap", c.amount > c.cap, BLOCK, f"${c.amount} exceeds the ${c.cap} per-transaction cap")
    chk("vendor_allowlist", not c.vendor_verified, BLOCK, "payee is not a verified vendor profile")
    if c.vendor_verified:
        chk("category", (c.vendor_category or "").lower() not in c.categories, BLOCK,
            f"category '{c.vendor_category}' is not allowed")
    if ph in ("commit", "direct"):
        chk("budget_window", c.committed + c.amount > c.budget_limit, BLOCK,
            f"${c.committed} already committed; ${c.amount} would exceed the ${c.budget_limit} budget")
    chk("velocity", c.recent_payouts >= c.velocity_limit, BLOCK,
        f"{c.recent_payouts} payouts in the last hour (limit {c.velocity_limit})")
    if ph in ("commit", "direct") and not c.pre_approved:
        chk("new_payee", c.vendor_trust == "new", APPROVAL, "first payment to this payee")
    if not c.pre_approved:
        chk("approval_threshold", c.amount > c.threshold, APPROVAL,
            f"${c.amount} is over the ${c.threshold} approval threshold")
    if c.has_deal:
        chk("payee_change", (c.terms_payee or "").lower() != (c.profile_payee or "").lower(), BLOCK,
            "payout target differs from the verified vendor profile")
        chk("terms_drift", c.terms_drift, BLOCK, "terms were changed after they were accepted")
        if ph != "commit":
            mismatch = c.amount != c.terms_amount or (
                c.claimed_payee is not None and c.claimed_payee.lower() != (c.terms_payee or "").lower())
            chk("deal_match", mismatch, BLOCK, "requested amount or payee differs from the accepted terms")
            chk("delivery_required", c.verdict != "PASS" and not c.owner_override_delivery, HOLD,
                f"delivery verification is {c.verdict or 'missing'}, not PASS")
            chk("proof_consumed", c.proof_consumed, BLOCK, "delivery proof was already used in another deal")
            chk("deadline", c.late, APPROVAL, "delivered after the deadline")
        else:
            chk("deposit_pressure", c.deposit_pressure, BLOCK if c.foreign_payee else APPROVAL,
                "counterparty pushed for a deposit outside the agreed terms"
                + (" to a different account" if c.foreign_payee else ""))
        chk("duplicate", c.already_paid, BLOCK, "this deal has already been paid or a payout is in flight")

    d = max((r.outcome for r in out), key=ORDER.get, default=ALLOW)
    d = ALLOW if d == PASS else d
    if c.injection_flagged:
        d = BLOCK
        out.append(RuleResult("provenance", BLOCK, "instruction came with prompt-injection patterns"))
    elif c.source in UNTRUSTED:
        d = escalate(d)
        out.append(RuleResult("provenance", d if d != ALLOW else PASS,
                              f"instruction traced to untrusted source '{c.source}'; escalated one level"))
    else:
        out.append(RuleResult("provenance", PASS, "ok"))
    if c.owner_approved and d == APPROVAL:
        d = ALLOW
    return PolicyResult(d, out, explain(d, out))


def apply_judge(decision: str, risk: str | None) -> str:
    """AI judge can only escalate ALLOW -> REQUIRE_APPROVAL. Never loosens, never blocks."""
    return APPROVAL if (decision == ALLOW and risk == "high") else decision
