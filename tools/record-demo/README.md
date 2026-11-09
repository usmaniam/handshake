# Demo recorder

Records a ~2 minute walkthrough of the live console (1280x720, captions and a visible cursor) with Playwright.
It drives the real console against your real data, finds the demo deals itself, and saves `out/handshake-demo.webm`.

## Run it (GitHub Codespace)
```bash
cd tools/record-demo
npm install
npx playwright install --with-deps chromium     # one-off: browser + system libraries

# 1. Make fresh demo data (creates one real $84 sandbox payout). Needs the agent keys from your seed output:
cd ../../apps/api && source .venv/bin/activate
HS_API=https://<api>.vercel.app ADMIN_TOKEN='...' HS_BUYER_KEY='...' HS_ACME_KEY='...' \
  PYTHONPATH=. python scripts/demo_scenarios.py
cd ../../tools/record-demo

# 2. Record
HS_TOKEN='<admin token>' CONSOLE_URL=https://<console>.vercel.app API_URL=https://<api>.vercel.app npm run record
```
Wait for the S1 deal to show Paid in the console before step 2 (about a minute).

## What it does to your data
- Signs in by typing the token into a password field (only dots are recorded; the token is never shown).
- **Approves the pending $210 order** if one is waiting (a real approval). Run step 1 again for a new one.
- Runs the red-team lab (harmless; it uses an isolated in-memory database).

## Options
`PACE=0.85` runs slower or faster (it prints the total run time; keep it under 3 minutes). `NO_VIDEO=1` rehearses
without recording. `SHOTS_DIR=/tmp/shots` saves a screenshot per caption so you can check each frame.

## Finish
- Download `out/handshake-demo.webm` (Explorer, right click, Download). YouTube and most forms accept webm.
- MP4: `sudo apt-get install -y ffmpeg && ffmpeg -i out/handshake-demo.webm -c:v libx264 -pix_fmt yuv420p -crf 20 handshake-demo.mp4`
- Add your voice with any editor or phone app, following `docs/demo-voiceover.md`.
- Don't commit `out/`. Rotate the admin token after judging.
