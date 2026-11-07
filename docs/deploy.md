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
   `ALLOWED_ORIGINS` to the web project's URL. Keep `PAYOUT_RAIL=paypal` and `LLM_VERIFIER=auto`.
4. **Web env var:** `NEXT_PUBLIC_API_BASE_URL=https://<api-project>.vercel.app`.
5. **PayPal webhook:** in the Developer Dashboard, on **Maya's REST app**, add
   `https://<api-project>.vercel.app/v1/webhooks/paypal` with the `PAYMENT.PAYOUTS-ITEM.*` and
   `PAYMENT.PAYOUTSBATCH.*` events. Copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID` and redeploy.
6. **Verify:** `GET /health` and `/health/db`, sign in to the console, run `docs/smoke-test.md`.

Serverless notes: no background workers exist. A payout whose webhook never arrives is picked up by
**Settings > Check PayPal for updates** (`POST /v1/owner/sweep`), which also expires overdue deals. Add a Vercel Cron
hitting that endpoint if you want it automatic (it needs the `ADMIN_TOKEN` bearer header).
