"use client";
import { useState } from "react";
import { ErrorBanner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";

type Row = { id: string; name: string; kind: string; owed: string; guarded: { mispaid: string; paid: string; completed?: boolean }; unguarded: { mispaid: string } };
type Result = {
  methodology: string; scenarios: Row[];
  summary: { attacks_run: number; benign_run: number; unguarded: { mispaid: string }; guarded: { mispaid: string; legit_completed: string; false_blocks: number; attacks_with_any_loss: string[] } };
};

export default function Lab() {
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try { setRes(await api<Result>("/v1/bench/run", { method: "POST", body: {} })); }
    catch (e) { setErr(e as ApiError); }
    finally { setBusy(false); }
  }

  const attacks = res?.scenarios.filter((r) => r.kind === "attack") ?? [];
  const benign = res?.scenarios.filter((r) => r.kind === "benign") ?? [];
  const max = Math.max(1, ...attacks.map((r) => Number(r.unguarded.mispaid)));
  const s = res?.summary;

  return (
    <div className="page">
      <div className="page-head">
        <h1>Red-team lab</h1>
        <p className="muted">Replays {res ? res.scenarios.length : 14} scenarios against a naive agent and against Handshake, so you can see what the checks actually prevent.</p>
      </div>
      <div className="actions">
        <button className="btn primary" onClick={run} disabled={busy}>{busy ? "Running scenarios…" : res ? "Run again" : "Run the scenarios"}</button>
      </div>
      <ErrorBanner error={err} />

      {res && s && (
        <>
          <section className="section" aria-label="Result">
            <h2>Without Handshake, a naive agent loses {money(s.unguarded.mispaid)}. With it, {money(s.guarded.mispaid)}.</h2>
            <p className="muted">
              {s.attacks_run} attacks. {s.guarded.legit_completed} legitimate deals completed, {s.guarded.false_blocks} wrongly blocked.
              {s.guarded.attacks_with_any_loss.length > 0 && ` The remaining loss is ${s.guarded.attacks_with_any_loss.join(", ")}: payments to a verified vendor that are within your limits. Handshake caps that loss; it can't tell it's unwanted.`}
            </p>
          </section>

          <section className="section" aria-label="Attacks">
            <h2>Attacks</h2>
            <div className="versus" role="table" aria-label="Money lost per attack">
              <span className="head" role="columnheader">Attack</span><span className="head" role="columnheader">Naive agent loses</span><span className="head" role="columnheader">Handshake loses</span>
              {attacks.map((r) => (
                <div key={r.id} style={{ display: "contents" }} role="row">
                  <span className="name" role="cell">{r.id}. {r.name}</span>
                  <span className="vcell" role="cell"><i className="vbar un" style={{ width: `${(Number(r.unguarded.mispaid) / max) * 100}%` }} /><span className="num">{money(r.unguarded.mispaid)}</span></span>
                  <span className="vcell" role="cell"><i className="vbar gu" style={{ width: `${(Number(r.guarded.mispaid) / max) * 100}%` }} /><span className="num">{money(r.guarded.mispaid)}</span></span>
                </div>
              ))}
            </div>
          </section>

          <section className="section" aria-label="Legitimate deals">
            <h2>Legitimate deals still go through</h2>
            <ul className="rows" style={{ listStyle: "none" }}>
              {benign.map((r) => (
                <li key={r.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                  <span>{r.id}. {r.name}</span>
                  <span className="num">{r.guarded.completed ? `Paid ${money(r.guarded.paid)}` : "Blocked"}</span>
                </li>
              ))}
            </ul>
          </section>

          <details>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>How this is measured</summary>
            <p className="muted small" style={{ whiteSpace: "pre-line", marginTop: 10, maxWidth: "70ch" }}>{res.methodology}</p>
          </details>
        </>
      )}
    </div>
  );
}
