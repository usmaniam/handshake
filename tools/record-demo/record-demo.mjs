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
// Optional: a delivery the AI reviewer (not the fixed checks) stopped. Created by demo_scenarios.py s7.
pick.aiFail = deals.find((d) => d.state === "HELD_DISPUTED" && d.verification?.llm?.status === "ok" && d.verification?.verdict === "FAIL");
const missing = Object.entries(pick).filter(([k, v]) => !v && k !== "aiFail").map(([k]) => k);
if (!pick.aiFail) console.warn("No AI-reviewed failed delivery found: the AI segment will be skipped. Run: PYTHONPATH=. python scripts/demo_scenarios.py s7");
if (missing.length) {
  console.error(`Missing demo deals: ${missing.join(", ")}.\nRun the demo scenarios first (apps/api: PYTHONPATH=. python scripts/demo_scenarios.py).`);
  process.exit(3);
}
const pendingApprovals = await get("/v1/owner/approvals");
console.log(`Found: paid=${pick.paid.id} wrong=${pick.wrong.id} blocked=${pick.blocked.id} drift=${pick.drift.id}; pending approvals: ${pendingApprovals.length}`);

// ---------------------------------------------------------------- browser, captions, cursor
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: process.env.CHROMIUM_ARGS ? JSON.parse(process.env.CHROMIUM_ARGS) : undefined,
});
const context = await browser.newContext({
  viewport: VIEW, deviceScaleFactor: 1,
  ...(NO_VIDEO ? {} : { recordVideo: { dir: OUT, size: VIEW } }),
});
await context.addInitScript(() => {
  const css = `#__cap{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);max-width:1000px;padding:14px 24px;border-radius:10px;
    background:#16202b;color:#eef1f0;font:600 25px/1.35 "Schibsted Grotesk Variable",system-ui,sans-serif;text-align:center;
    z-index:2147483647;opacity:0;transition:opacity .25s;pointer-events:none;box-shadow:0 6px 28px rgba(0,0,0,.28)}
    #__cap.on{opacity:1}
    #__cap.left{left:380px;max-width:680px}
    main.main{padding-bottom:240px !important}
    #__cur{position:fixed;width:24px;height:24px;border-radius:50%;border:3px solid #fff;background:rgba(45,90,155,.6);
    box-shadow:0 0 0 2px #16202b;z-index:2147483646;pointer-events:none;left:-60px;top:-60px;transform:translate(-50%,-50%);transition:transform .1s}
    #__cur.down{transform:translate(-50%,-50%) scale(.65)}`;
  const ensure = () => {
    const root = document.documentElement;
    if (!root) return null;
    if (!document.getElementById("__cap")) {
      const st = document.createElement("style"); st.textContent = css; root.appendChild(st);
      const cap = document.createElement("div"); cap.id = "__cap"; root.appendChild(cap);
      const cur = document.createElement("div"); cur.id = "__cur"; root.appendChild(cur);
    }
    return { cap: document.getElementById("__cap"), cur: document.getElementById("__cur") };
  };
  window.__cap = (t, left) => { const e = ensure(); if (!e) return; e.cap.classList.toggle("left", !!left); if (t) { e.cap.textContent = t; e.cap.classList.add("on"); } else e.cap.classList.remove("on"); };
  window.__curMove = (x, y) => { const e = ensure(); if (e) { e.cur.style.left = x + "px"; e.cur.style.top = y + "px"; } };
  window.__curDown = (on) => { const e = ensure(); if (e) e.cur.classList.toggle("down", on); };
  document.addEventListener("mousemove", (e) => window.__curMove(e.clientX, e.clientY), true);
});
const page = await context.newPage();
let shotN = 0;

async function say(text, dwell = 3500, left = false) {
  await page.evaluate(([t, l]) => window.__cap(t, l), [text, left]);
  console.log(`[${stamp()}] ${text}`);
  await sleep(dwell);
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `${String(++shotN).padStart(2, "0")}.png`) }); }
}
const hush = () => page.evaluate(() => window.__cap(""));

async function moveTo(loc) {
  await loc.scrollIntoViewIfNeeded();
  const b = await loc.boundingBox();
  if (!b) throw new Error("element has no box");
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 28 });
  await sleep(350);
  return b;
}
async function click(loc) {
  const b = await moveTo(loc);
  await page.evaluate(() => window.__curDown(true));
  await sleep(120);
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
  await page.evaluate(() => window.__curDown(false));
  await sleep(300);
}
async function reveal(loc, block = "start") {
  await loc.evaluate((el, b) => el.scrollIntoView({ behavior: "smooth", block: b }), block);
  await sleep(1100);
}
const nav = (name) => click(page.locator("nav a", { hasText: name }).first());
async function openDeal(id) {
  await nav("Deals");
  await page.waitForSelector(`a[href="/deals/${id}"]`);
  await click(page.locator(`a[href="/deals/${id}"]`).first());
  await page.waitForSelector("h2", { state: "attached" });
  await page.getByRole("heading", { name: "What was agreed" }).waitFor();
  await sleep(600);
}

try {
  // 1. Sign in ------------------------------------------------------------------------------------------
  await page.goto(CONSOLE, { waitUntil: "networkidle" });
  await say("Handshake: agents negotiate the deal. Handshake pays when it's delivered.", 3400);
  await click(page.getByLabel("Admin token"));
  await page.keyboard.type(TOKEN, { delay: 35 });
  await click(page.getByRole("button", { name: "Sign in" }));
  await page.getByRole("heading", { name: "Today" }).waitFor();
  await hush();

  // 2. Today --------------------------------------------------------------------------------------------
  await moveTo(page.locator(".bar").first());
  await say("Maya runs a small shop. Her AI agents buy for her, but never hold her PayPal credentials.", 4400);
  await hush();

  // 3. The honest deal ----------------------------------------------------------------------------------
  await openDeal(pick.paid.id);
  await say("An honest order. Terms agreed, budget reserved, delivery verified against the carrier.", 4000);
  await reveal(page.getByRole("heading", { name: "What happened" }), "start");
  await say("Then a real PayPal sandbox payout, confirmed by PayPal's webhook. Paid.", 4200);
  await hush();

  // 4. Wrong item ---------------------------------------------------------------------------------------
  await openDeal(pick.wrong.id);
  await reveal(page.getByRole("heading", { name: "Delivery checks" }), "start");
  await say("The seller shipped the wrong item. One check fails, so no money moves.", 4400);
  await hush();

  // 5. Hostile deposit ----------------------------------------------------------------------------------
  await openDeal(pick.blocked.id);
  await reveal(page.getByRole("heading", { name: "Conversation" }), "start");
  await say("After agreeing, this seller pushed a deposit to a different account. Flagged and refused.", 4200);
  await hush();

  // 6. Terms drift --------------------------------------------------------------------------------------
  await openDeal(pick.drift.id);
  await moveTo(page.locator(".banner.stop").first());
  await say("The seller raised the price after agreeing. Handshake ignores it and pays only what was agreed.", 4400);
  await hush();

  // 6b. The AI reviewer ---------------------------------------------------------------------------------
  if (pick.aiFail) {
    await openDeal(pick.aiFail.id);
    await reveal(page.getByRole("heading", { name: "Delivery checks" }), "start");
    await say("A designer's files pass every fixed check: the right count and the right file types.", 4400);
    const flags = page.locator(".banner.review");
    const nf = await flags.count();
    if (nf) await reveal(flags.nth(Math.floor(nf / 2)), "center");   // centre the group so the caption never covers it
    await say("But Gemini reads the work. The colour and the name don't match the agreement, and it spots hidden instructions telling it to approve.", 6600);
    await hush();
  }

  // 7. Approvals ----------------------------------------------------------------------------------------
  await nav("Approvals");
  await page.getByRole("heading", { name: "Approvals" }).waitFor();
  await sleep(700);
  const approve = page.getByRole("button", { name: /^Approve/ }).first();
  if (await approve.count()) {
    await moveTo(approve);
    await say("A $210 order is over Maya's $100 limit, so it waits for her approval.", 3600);
    await click(approve);
    await page.getByText("all caught up").waitFor({ timeout: 20000 });
    await say("One tap, and the budget is reserved. Approval never overrides a block.", 3000);
  } else {
    await say("Anything over Maya's limit waits here for her approval, from her phone if she likes.", 4000);
  }
  await hush();

  // 8. Ledger -------------------------------------------------------------------------------------------
  await nav("Ledger");
  await page.waitForSelector(".ag-row");
  await sleep(600);
  await say("The ledger runs on AG Grid: every request an agent made, sortable and searchable.", 3000, true);
  await click(page.getByLabel("Search the ledger"));
  await page.keyboard.type("Blocked", { delay: 110 });     // AG Grid quick filter, live
  await sleep(1300);
  await click(page.locator(".ag-row", { hasText: "Blocked" }).first().locator(".ag-cell").first());
  await page.waitForSelector(".drawer .checks");
  await reveal(page.locator(".drawer .checks li", { hasText: "Blocked" }).first(), "center");
  await say("Every decision explains itself, rule by rule, in plain language.", 4600, true);
  await click(page.getByRole("button", { name: "Close" }));
  await hush();

  // 9. Red-team lab -------------------------------------------------------------------------------------
  await nav("Red-team lab");
  await click(page.getByRole("button", { name: /Run the scenarios|Run again/ }));
  await page.waitForSelector(".versus .vbar", { timeout: 60000 });
  await sleep(600);
  await say("We replay 14 scenarios against a naive agent. Without Handshake it loses $1,052. With it, $150.", 4800);
  await reveal(page.locator(".versus .name", { hasText: "A9." }).first(), "center");
  await say("That $150 is ten small payments to a verified vendor. We cap it, and we show it.", 3800);
  await hush();

  // 10. Close -------------------------------------------------------------------------------------------
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(700);
  await say("Handshake. Agents negotiate the deal. Handshake pays when it's delivered.", 3600);
  await hush();
} catch (e) {
  console.error(`\nFAILED at ${stamp()}: ${e.message}`);
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, "failure.png") }).catch(() => {}); }
  process.exitCode = 1;
}

const video = page.video();
await context.close(); // flushes the video to disk
await browser.close();
const total = (Date.now() - T0) / 1000;
if (video && !NO_VIDEO) {
  const dest = path.join(OUT, "handshake-demo.webm");
  fs.renameSync(await video.path(), dest);
  console.log(`\nVideo saved: ${dest}`);
}
console.log(`Total run time: ${total.toFixed(0)}s${total > 175 ? "  (over the 3 minute limit: re-run with PACE=0.85)" : ""}`);
