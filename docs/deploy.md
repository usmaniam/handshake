# Deploying to Vercel (two projects, one repo)

| Project | Root directory | Framework |
|---|---|---|
| `handshake-api` | `apps/api` | Python (FastAPI via `index.py`, `vercel.json` sets 60s functions) |
| `handshake-web` | `apps/web` | Next.js |

1. **Database.** Add Neon via the Vercel Marketplace to `handshake-api`. It injects `DATABASE_URL` (pooled) and
   `DATABASE_URL_UNPOOLED`. The app rewrites `postgresql://` to `postgresql+psycopg://` and disables prepared statements
   for the pooler, so use the pooled URL as given.
2. **Migrate and seed (once, from your machine):**
   `cd apps/api && DATABASE_URL_UNPOOLED=... alembic upgrade head && DATABASE_URL=... python -m handshake.seed`
   (prints the agent API keys once; store them, they are not recoverable).
3. **API env vars:** everything in `.env.example` (API section). Set `ADMIN_TOKEN` to a long random string and
   `ALLOWED_ORIGINS` to the web project's URL. Keep `PAYOUT_RAIL=paypal` and `LLM_VERIFIER=auto`. Gemini is optional: with `GEMINI_API_KEY` set the code defaults to
   `gemini-3.5-flash-lite` with low thinking (verified live, see `docs/smoke-test.md`). Leave `LLM_JUDGE` unset unless you want the AI payment review.
4. **Web env var:** `NEXT_PUBLIC_API_BASE_URL=https://<api-project>.vercel.app`.
5. **PayPal webhook:** in the Developer Dashboard, on **Maya's REST app**, add
   `https://<api-project>.vercel.app/v1/webhooks/paypal` with the `PAYMENT.PAYOUTS-ITEM.*` and
   `PAYMENT.PAYOUTSBATCH.*` events. Copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID` and redeploy.
6. **Verify:** `GET /health` and `/health/db`, sign in to the console, run `docs/smoke-test.md`.

Serverless notes: no background workers exist. A payout whose webhook never arrives is picked up by
**Settings > Check PayPal for updates** (`POST /v1/owner/sweep`), which also expires overdue deals. There is no scheduled job yet. (Vercel Cron sends GET requests with a `CRON_SECRET`, while the sweep endpoint is a POST
behind `ADMIN_TOKEN`, so cron would need a small dedicated endpoint.)

## If something goes wrong
| Symptom | Likely cause |
|---|---|
| Console says it can't reach the API | `ALLOWED_ORIGINS` is wrong, or `NEXT_PUBLIC_API_BASE_URL` changed after the console was built (redeploy it) |
| Webhook delivery shows 400 | `PAYPAL_WEBHOOK_ID` is wrong (it is the webhook's ID, not the client ID) or the webhook is on a different PayPal app |
| Payout stays on "Paying out" | Webhook not arriving: use Settings > Check PayPal for updates |
| A request hangs for 60s | An outbound call without a timeout. Gemini calls are capped at `LLM_TIMEOUT_S` (min 10s) |
| `pip install -e .` fails | Use the repo's current `pyproject.toml` (explicit package list) |
| Seed run twice | It adds a second owner; never run `--reset` against a real database |
