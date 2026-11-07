# PayPal sandbox smoke test (plan 12.5)

Status: **Payout check passed (2026-11-07).** The verified-webhook and Neon checks are pending the Vercel deploy.

## Steps
1. Create sandbox accounts in the Developer Dashboard: **Maya** (business, custom balance), **Vendor**, **Contractor**.
   Create a REST app on Maya's account, enable **Payouts**.
2. `cd apps/api && pip install -e . && python scripts/smoke_paypal.py <vendor-sandbox-email> 5`
3. Deploy `apps/api` to Vercel, register `https://<api>.vercel.app/v1/webhooks/paypal` on **Maya's app**,
   put the webhook ID in `PAYPAL_WEBHOOK_ID`, send one real payout, and confirm the webhook row in `webhook_events`
   (`verified = true`). Simulator events cannot be verified.
4. `GET https://<api>.vercel.app/health/db` returns ok (Neon reachable).

## Results
| Check | Result | Notes |
|---|---|---|
| OAuth token | Pass | |
| $1.00 payout created | Pass | batch id: XWDFJ3XLGZFAQ |
| Time to SUCCESS | About 32s | PENDING, PROCESSING, then SUCCESS |
| Real webhook verified | Not yet | Needs the deployed API (`docs/deploy.md`, step 8) |
| Neon round trip | Not yet | Needs the deployed API (`/health/db`) |

Decision gate: passed. A real sandbox payout can be created, so the demo can show a real payout instead of the simulator path.
