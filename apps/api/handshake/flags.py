"""Heuristic scan of untrusted text. Flags feed the policy engine; they never loosen anything."""
from __future__ import annotations

import re

INJECTION = [
    r"ignore (all |any |the |your |previous |prior |above )*(instructions|criteria|rules|limits|polic(y|ies))",
    r"\bsystem\s*:", r"mark (this |it |the delivery |the work )?as (approved|verified|delivered|passed)",
    r"(approve|pay)( this| it| me)? (now|immediately)", r"\byou are now\b", r"\bdisregard\b",
    r"override (the )?(policy|limits|rules|checks)",
]
DEPOSIT = [r"\bdeposit\b", r"\bpre-?pay(ment)?\b", r"\badvance payment\b", r"\bup-?front\b",
           r"lock (in )?the price", r"\bsend (me |us )?(the )?(money|funds|payment)\b"]
URGENCY = [r"\bimmediately\b", r"\bright now\b", r"\btoday only\b", r"\burgent(ly)?\b",
           r"\bexpires? (today|soon)\b", r"\bbefore (the )?end of (the )?day\b", r"\blast chance\b"]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def scan(text: str, verified_payee: str | None = None, extra: list[str] | None = None) -> list[str]:
    t = " ".join((text or "").lower().split())
    flags: list[str] = []
    if _any(INJECTION, t):
        flags.append("prompt_injection")
    dep = _any(DEPOSIT, t)
    if dep:
        flags.append("deposit_pressure")
    emails = {e.lower() for e in EMAIL.findall(t)} | {e.lower() for e in (extra or []) if e}
    if any(e != (verified_payee or "").lower() for e in emails):
        flags.append("foreign_payee")
    if _any(URGENCY, t) and (dep or "foreign_payee" in flags):
        flags.append("urgency_pressure")
    return flags
