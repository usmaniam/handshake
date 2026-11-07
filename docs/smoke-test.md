# PayPal sandbox smoke test (plan 12.5)

Status: **NOT YET RUN** (needs real sandbox credentials). Fill this in; it is part of the submission.

1. Create sandbox accounts in the Developer Dashboard: **Maya** (business, custom balance), **Vendor**, **Contractor**.
   Create a REST app on Maya's account, enable **Payouts**.
2. `cd apps/api && python scripts/smoke_paypal.py <vendor-sandbox-email> 5`
3. Deploy `apps/api` to Vercel, register `https://<api>.vercel.app/v1/webhooks/paypal` on **Maya's app**,
   put the webhook ID in `PAYPAL_WEBHOOK_ID`, send one real payout, and confirm the webhook row in `webhook_events`
   (`verified = true`). Simulator events cannot be verified.
4. `GET https://<api>.vercel.app/health/db` returns ok (Neon reachable).

## Results
| Check | Result | Notes |
|---|---|---|
| OAuth token | | |
| $1.00 payout created | | batch id: |
| Time to SUCCESS | | |
| Real webhook verified | | |
| Neon round trip | | |

Decision gate: if no real payout can be created, use the Payouts simulator path and say so in the submission.
