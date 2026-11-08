# PayPal sandbox smoke test (plan 12.5)

Status: **All checks passed (2026-11-08).** A real sandbox payout was created, settled, and its webhook was delivered and verified on the deployed API.

## Steps
1. Create sandbox accounts in the Developer Dashboard: **Maya** (business, custom balance), **Vendor**, **Contractor**.
   Create a REST app on Maya's account, enable **Payouts**.
2. `cd apps/api && pip install -e . && python scripts/smoke_paypal.py <vendor-sandbox-email> 5`
3. Deploy `apps/api` to Vercel, register `https://<api>.vercel.app/v1/webhooks/paypal` on **Maya's app**,
   put the webhook ID in `PAYPAL_WEBHOOK_ID`, send one real payout, and confirm in the PayPal dashboard
   (Event Logs > Webhook Events) that the delivery shows Success. Simulator events cannot be verified.
4. `GET https://<api>.vercel.app/health/db` returns ok (Neon reachable).

## Results
| Check | Result | Notes |
|---|---|---|
| OAuth token | Pass | |
| $1.00 payout created | Pass | batch id: XWDFJ3XLGZFAQ |
| Time to SUCCESS | About 32s | PENDING, PROCESSING, then SUCCESS |
| Real webhook verified | Pass | PayPal Webhook Events log: payouts-item succeeded, payouts-batch success and processing, all delivered with Success (our API returns 400 on a failed signature, so a 2xx delivery means it verified) |
| Neon round trip | Pass | `/health/db` returned `{"ok": true}` in about 3.1s on a cold start |
| End-to-end on the deployed API | Pass | `scripts/demo_scenarios.py` against Vercel: honest deal paid via real payout; wrong item held; hostile deposit blocked; price change blocked at release; large order waiting for approval |

## Gemini live check (2026-11-08, `scripts/check_gemini.py`)
| Check | `gemini-3.5-flash-lite` (low thinking) | `gemini-3.1-flash-lite` (low thinking) |
|---|---|---|
| Model available to the key | Pass | Pass |
| Honest delivery passes | Pass (1.2s) | Pass (1.6s) |
| Delivery missing criteria not passed | Pass (0.9s) | Pass (21.5s) |
| Injected instructions do not flip verdict | Pass, injection flagged (0.9s) | Pass, injection flagged (6.7s) |
| Stable over 3 runs | Pass (0.7-0.9s) | Pass (1.3-4.5s) |
| AI judge valid output | Pass, risk medium | Pass, risk medium |

`gemini-3.8-flash` (the original plan model) is available to the key but returned 503 UNAVAILABLE and 504 DEADLINE_EXCEEDED under the same test, so the default is `gemini-3.5-flash-lite`.

## Issues found and fixed during deployment
- `pip install -e .` failed (setuptools found several top-level folders). Fixed in `pyproject.toml`.
- Commit requests hung until Vercel's 60s limit when `GEMINI_API_KEY` was set: the Gemini call had no timeout. Fixed with a request timeout and by making the AI payment review opt-in (`LLM_JUDGE=on`). Deterministic checks decide every payment either way.
- The first timeout fix (8s) made every Gemini call fail: Google rejects request deadlines under 10s. Found by the live check; the default is now 12s and the code never sends less than 10s.
- The plan's model `gemini-3.8-flash` returned 503/504 under test; switched to `gemini-3.5-flash-lite`.

Decision gate: passed. A real sandbox payout was created, so the demo shows a real payout instead of the simulator path.
