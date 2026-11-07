"""Day-1 smoke test (plan section 12.5). Run with your sandbox credentials:

    cd apps/api && PAYPAL_OWNER_CLIENT_ID=... PAYPAL_OWNER_SECRET=... \
        python scripts/smoke_paypal.py vendor-sandbox@example.com [minutes_to_poll]

Sends ONE $1.00 sandbox payout from Maya's business account, then polls until it settles or time runs out.
Paste the output into docs/smoke-test.md.
"""
from __future__ import annotations

import sys
import time
import uuid

from handshake.paypal import PayPalClient, PayPalError, PayPalTransient


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    receiver, minutes = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 5
    pp = PayPalClient()
    sbid = f"hs_smoke_{uuid.uuid4().hex[:10]}"
    try:
        r = pp.send_payout(sender_batch_id=sbid, receiver=receiver, recipient_type="EMAIL", amount="1.00",
                           currency="USD", note="Handshake smoke test", sender_item_id=sbid[:63])
    except (PayPalError, PayPalTransient) as e:
        print("PAYOUT FAILED TO CREATE:", e, getattr(e, "body", ""))
        print("=> decision gate: fall back to the Payouts simulator path and say so in the submission")
        return 1
    print(f"created batch {r['batch_id']} status={r['batch_status']} sender_batch_id={sbid}")
    t0, last = time.time(), None
    while time.time() - t0 < minutes * 60:
        j = pp.get_payout(r["batch_id"])
        st = (j["batch_status"], [i["status"] for i in j["items"]])
        if st != last:
            print(f"[{int(time.time() - t0):>4}s] batch={st[0]} items={st[1]}")
            last = st
        if j["batch_status"] in ("SUCCESS", "DENIED", "CANCELED"):
            break
        time.sleep(10)
    print("RESULT:", last, "=> proceed" if last and last[0] == "SUCCESS" else "=> use simulator/honest PENDING (see plan 12.5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
