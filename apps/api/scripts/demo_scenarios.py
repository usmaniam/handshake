"""Plays buyer + seller agents over HTTP so the console has live data (and for recording the demo).

    make reset-dev                                   # seeds with predictable dev keys
    ADMIN_TOKEN=dev PAYOUT_RAIL=fake make dev        # API on :8000
    ADMIN_TOKEN=dev python scripts/demo_scenarios.py [s1 s3 s5 s6 s8]   # default: all

Env: HS_API (default http://localhost:8000), ADMIN_TOKEN, HS_BUYER_KEY / HS_ACME_KEY (default hs_dev_*).
Tracking numbers are unique per run, so re-running never trips replay protection.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx

from handshake import agents
from handshake.verifier.llm import get_llm

LLM = get_llm() if "--llm" in sys.argv else None  # Gemini wording; behaviour stays scripted

API = os.environ.get("HS_API", "http://localhost:8000")
ADMIN = os.environ.get("ADMIN_TOKEN", "dev")
KEYS = {"buyer": os.environ.get("HS_BUYER_KEY", "hs_dev_buyer"), "acme": os.environ.get("HS_ACME_KEY", "hs_dev_acme")}
http = httpx.Client(base_url=API, timeout=30)
RUN = str(int(time.time()))[-6:]


def call(method: str, path: str, who: str, body: dict | None = None) -> dict:
    tok = ADMIN if who == "admin" else KEYS[who]
    h = {"Authorization": f"Bearer {tok}", "Idempotency-Key": f"demo-{uuid.uuid4().hex[:16]}"}
    r = http.request(method, path, json=body, headers=h)
    if r.status_code >= 400:
        print(f"   ! {method} {path} -> {r.status_code} {r.text[:160]}")
        return {"error": r.text, "status": r.status_code}
    return r.json()


def terms(qty=200, price="0.42", **kw) -> dict:
    return {"item": "mailer boxes 12x9x3 in", "quantity": qty, "unit_price": price,
            "deadline": (date.today() + timedelta(days=10)).isoformat(), "deliverable_type": "physical_goods",
            "acceptance_criteria": [f"{qty} units", "size 12x9x3 in", "delivered on time"], "spec": {"sku": "mailer-12x9x3"}, **kw}


def ship(tracking: str, qty: int, sku: str = "mailer-12x9x3") -> None:
    call("POST", "/mock-carrier", "admin", {"tracking": tracking, "status": "DELIVERED", "items": [{"sku": sku, "qty": qty}],
                                            "delivered_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()})


def agree(vendor: str, t: dict, text: str) -> str:
    d = call("POST", "/v1/deals", "buyer", {"vendor_id": vendor, "terms": t, "text": text})
    call("POST", f"/v1/deals/{d['id']}/messages", "acme", {"type": "accept", "text": "Agreed, thanks."})
    return d["id"]


def say(msg: str) -> None:
    print(f"\n== {msg}")


def s1(v: str) -> None:
    say("S1 honest supply order: delivered, verified, paid")
    d = agree(v, terms(200), "Restock: 200 mailer boxes at $0.42?")
    print("  commit:", call("POST", f"/v1/deals/{d}/commit", "buyer")["decision"])
    ship(f"TRK-{RUN}-1", 200)
    print("  verdict:", call("POST", f"/v1/deals/{d}/delivery", "acme", {"proof_type": "carrier_tracking", "tracking_number": f"TRK-{RUN}-1"})["verdict"])
    r = call("POST", f"/v1/deals/{d}/release", "buyer", {})
    print("  release:", r["decision"], "->", r["deal_state"])


def s3(v: str) -> None:
    say("S3 wrong item: verification fails, payment held")
    d = agree(v, terms(200), "200 mailer boxes please.")
    call("POST", f"/v1/deals/{d}/commit", "buyer")
    ship(f"TRK-{RUN}-3", 200, sku="poly-bags-6x9")
    r = call("POST", f"/v1/deals/{d}/delivery", "acme", {"proof_type": "carrier_tracking", "tracking_number": f"TRK-{RUN}-3"})
    print("  verdict:", r["verdict"], "|", "; ".join(r["reasons"])[:90])
    print("  release:", call("POST", f"/v1/deals/{d}/release", "buyer", {})["decision"])


def s5(v: str) -> None:
    say("S5 hostile deposit demand: blocked")
    d = agree(v, terms(300), "300 boxes.")
    call("POST", f"/v1/deals/{d}/messages", "acme", {"type": "note", "text":
         agents.phrase(LLM, "hostile_deposit", "Buyer wants 300 boxes; seller wants a deposit sent to pay@fast-supplies.example")})
    r = call("POST", f"/v1/deals/{d}/commit", "buyer")
    print("  commit:", r["decision"], "->", r["deal_state"])
    r = call("POST", "/v1/payment-requests", "buyer", {"amount": "60", "payee": "pay@fast-supplies.example",
             "instruction_source": "counterparty_agent", "source_text": "send deposit now", "deal_id": d})
    print("  direct payment to the new account:", r["decision"])


def s6(v: str) -> None:
    say("S6 terms drift after accept: blocked at release")
    d = agree(v, terms(200), "200 boxes.")
    call("POST", f"/v1/deals/{d}/commit", "buyer")
    call("POST", f"/v1/deals/{d}/messages", "acme", {"type": "counter_offer", "terms": terms(200, "0.90"),
         "text": agents.phrase(LLM, "terms_drift", "price rises from $0.42 to $0.90 per box")})
    ship(f"TRK-{RUN}-6", 200)
    call("POST", f"/v1/deals/{d}/delivery", "acme", {"proof_type": "carrier_tracking", "tracking_number": f"TRK-{RUN}-6"})
    r = call("POST", f"/v1/deals/{d}/release", "buyer", {})
    print("  release:", r["decision"], "->", r["deal_state"])


def s8(v: str) -> None:
    say("S8 large order: waits for Maya's approval (left pending)")
    d = agree(v, terms(500), "Bulk order: 500 boxes.")
    r = call("POST", f"/v1/deals/{d}/commit", "buyer")
    print("  commit:", r["decision"], "| approval:", r.get("approval_id"))


if __name__ == "__main__":
    vendors = {x["name"]: x["id"] for x in http.get("/v1/owner/vendors", headers={"Authorization": f"Bearer {ADMIN}"}).json()}
    acme = vendors["Acme Packaging"]
    chosen = [a for a in sys.argv[1:] if not a.startswith('--')] or ["s1", "s3", "s5", "s6", "s8"]
    for name in chosen:
        {"s1": s1, "s3": s3, "s5": s5, "s6": s6, "s8": s8}[name](acme)
    print("\nDone. Open the console and sign in with your admin token.")
