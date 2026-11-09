// Records a ~2.5 minute walkthrough of the Handshake console with captions and a visible cursor.
//
//   HS_TOKEN='<admin token>' CONSOLE_URL=https://<console>.vercel.app API_URL=https://<api>.vercel.app npm run record
//
// It drives the REAL console against your REAL data, and finds the demo deals itself (run
// `PYTHONPATH=. python scripts/demo_scenarios.py` in apps/api first so they exist). The token is typed into a
// password field, so only dots are recorded. Two steps change data: it approves the pending $210 order (if one
// is waiting) and it runs the red-team lab (harmless).
//
// Debug hooks: NO_VIDEO=1, SHOTS_DIR=<dir> (a screenshot per caption), PACE=0.5 (faster), CHROMIUM_PATH / CHROMIUM_ARGS.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const TOKEN = process.env.HS_TOKEN;
const CONSOLE = (process.env.CONSOLE_URL || "").replace(/\/$/, "");
const API = (process.env.API_URL || "").replace(/\/$/, "");
if (!TOKEN || !CONSOLE || !API) {
  console.error("Set HS_TOKEN, CONSOLE_URL and API_URL. See the comment at the top of this file.");
  process.exit(2);
}
const PACE = Number(process.env.PACE || 1);
const NO_VIDEO = process.env.NO_VIDEO === "1";
const SHOTS = process.env.SHOTS_DIR || "";
const OUT = path.resolve("out");
const VIEW = { width: 1280, height: 720 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms * PACE));
const T0 = Date.now();
const stamp = () => `${((Date.now() - T0) / 1000).toFixed(0).padStart(3)}s`;

// ---------------------------------------------------------------- find the demo deals through the API
async function get(p) {
  const r = await fetch(API + p, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!r.ok) throw new Error(`${p} -> ${r.status} ${r.status === 401 ? "(wrong admin token?)" : ""}`);
  return r.json();
}
const deals = await get("/v1/owner/deals"); // newest first
const failed = (d) => (d.verification?.checks || []).some((c) => !c.passed);
const drift = (d) => d.current_terms && d.accepted_terms && d.current_terms.version !== d.accepted_terms.version;
const pick = {
  paid: deals.find((d) => d.state === "PAID"),
  wrong: deals.find((d) => d.state === "HELD_DISPUTED" && !drift(d) && failed(d)),
  blocked: deals.find((d) => d.state === "BLOCKED_AT_COMMIT"),
  drift: deals.find((d) => d.state === "HELD_DISPUTED" && drift(d)),
};
const missing = Object.entries(pick).filter(([, v]) => !v).map(([k]) => k);
if (missing.length) {
  console.error(`Missing demo deals: ${missing.join(", ")}.\nRun the demo scenarios first (apps/api: PYTHONPATH=. python scripts/demo_scenarios.py).`);
  process.exit(3);
