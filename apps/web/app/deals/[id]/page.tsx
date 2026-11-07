"use client";
import Link from "next/link";
import { use, useState } from "react";
import ApprovalAsk, { plainReason } from "@/components/ApprovalAsk";
import { useSummary } from "@/components/Shell";
import { ErrorBanner, Loading, Mark, Tag, ToneTag, Track } from "@/components/ui";
import { api, ApiError, Approval, DealDetail, useApi } from "@/lib/api";
import { cap, checkLabel, day, money, MOVED_TO, stateInfo, when } from "@/lib/format";

const FLAG: Record<string, string> = {
  deposit_pressure: "Pushes for a deposit", foreign_payee: "Mentions a different payee",
  prompt_injection: "Instructions aimed at the AI", urgency_pressure: "Urgency pressure", llm_injection_suspected: "AI reviewer saw injected instructions",
};
const MSG: Record<string, string> = { offer: "Offer", counter_offer: "Counter-offer", accept: "Accepted", reject: "Rejected", note: "" };

function describe(e: DealDetail["timeline"][number]): string {
  const p = e.payload || {};
  const lab = (s?: string) => (s ? stateInfo(s).label : "");
  switch (e.event) {
    case "deal.created": return "Deal opened.";
    case "deal.transition": {
      const via = p.via === "approval" ? " (you approved)" : p.via === "owner_override" ? " (you overrode)" : p.via === "retry" ? " (retry)" : "";
      const quiet = ["opened", "accepted", "budget reserved", "proof submitted", "all checks passed", ""];
      const why = p.why && !quiet.includes(String(p.why)) ? ` ${plainReason(String(p.why))}` : "";
      return `${MOVED_TO[p.to] ?? lab(p.to)}${via}.${why}`;
    }
    case "alert.terms_drift": return `Seller proposed changed terms after the deal was agreed (version ${p.proposed}). Handshake keeps enforcing version ${p.accepted}.`;
    case "alert.deal_expired": return "Deadline passed with no delivery. Budget returned.";
    case "alert.payout_attention": return `PayPal needs attention: ${lab(p.status)}.`;
    case "alert.deliverable_flagged": return "Delivered files contained text that looks like instructions to the AI.";
    case "owner.release": return "You chose to pay anyway.";
    case "owner.retry": return "You chose to retry the payout.";
    case "owner.cancel": return "You cancelled the deal.";
    default: return cap(e.event);
  }
}
const SHOW = new Set(["deal.created", "deal.transition", "alert.terms_drift", "alert.deal_expired", "alert.payout_attention",
  "alert.deliverable_flagged", "owner.release", "owner.retry", "owner.cancel"]);

export default function DealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { reload: reloadSummary } = useSummary();
  const { data: d, error, loading, reload } = useApi<DealDetail>(`/v1/owner/deals/${id}`, 6000);
  const approvals = useApi<Approval[]>("/v1/owner/approvals", 6000);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function resolve(action: "release" | "cancel" | "retry") {
    setBusy(true); setErr(null); setDone(null);
    try {
      const r = await api<{ deal_state: string }>(`/v1/owner/deals/${id}/resolve`, { method: "POST", body: { action, reason: "Decided in console" } });
      setDone(stateInfo(r.deal_state).label);
      setConfirm(false);
      reload(); reloadSummary();
    } catch (e) {
      setErr(String((e as ApiError).message).replace(/^cannot proceed: |^hard rule prevents release: /, "").replace(/^(Blocked|Payment held|Needs your approval)\.\s*/, ""));
    } finally { setBusy(false); }
  }

  if (loading && !d) return <Loading what="deal" />;
  if (error && !d) return <div className="page"><ErrorBanner error={error} retry={reload} /><Link href="/deals">Back to deals</Link></div>;
  if (!d) return null;

  const s = stateInfo(d.state);
  const t = d.accepted_terms ?? d.current_terms;
  const drift = !!(d.accepted_terms && d.current_terms && d.current_terms.version !== d.accepted_terms.version);
  const canPay = ["OWNER_REVIEW", "HELD_DISPUTED"].includes(d.state) && !drift;
  const canRetry = d.state === "PAYOUT_FAILED";
  const canCancel = ["OWNER_REVIEW", "HELD_DISPUTED", "PAYOUT_FAILED", "RESERVED"].includes(d.state);
  const v = d.verification;
  const failed = v?.checks.filter((c) => !c.passed) ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <p className="small"><Link href="/deals">All deals</Link></p>
        <h1>{d.vendor}{t ? `: ${t.item}` : ""}</h1>
        <p className="muted"><Tag state={d.state} /> &nbsp;{s.hint}</p>
      </div>

      <section aria-label="Progress"><Track state={d.state} /></section>

      {done && <div className="banner done" role="status">Done. The deal is now: {done}.</div>}
      <ErrorBanner error={err} />

      {drift && d.current_terms && d.accepted_terms && (
        <div className="banner stop" role="alert">
          <strong>The seller tried to change the deal after you agreed.</strong>{" "}
          They proposed {money(d.current_terms.total)} (version {d.current_terms.version}). Handshake ignores it and only pays the agreed {money(d.accepted_terms.total)} (version {d.accepted_terms.version}). To change the price, start a new deal.
        </div>
      )}

      {(approvals.data ?? []).filter((a) => a.deal_id === id).length > 0 && (
        <section className="section" aria-label="Waiting for your approval">
          <h2>Waiting for your approval</h2>
          <ul className="rows" style={{ listStyle: "none" }}>
            {(approvals.data ?? []).filter((a) => a.deal_id === id).map((a) => (
              <ApprovalAsk key={a.id} a={a} onDone={() => { approvals.reload(); reload(); reloadSummary(); }} />
            ))}
          </ul>
        </section>
      )}

      {(canPay || canRetry || canCancel) && (
        <section className="section" aria-label="Your decision">
          <h2>Your decision</h2>
          {confirm ? (
            <div className="confirm">
              <p>
                {failed.length ? `This delivery failed checks: ${failed.map((c) => c.detail).join("; ")}. ` : "Handshake wants a person to look at this delivery. "}
                Paying anyway sends <strong>{money(t?.total)}</strong> to {d.vendor}. Handshake still refuses if the price, payee or proof were tampered with.
              </p>
              <div className="actions">
                <button className="btn primary" disabled={busy} onClick={() => resolve("release")}>{busy ? "Paying…" : `Yes, pay ${money(t?.total)}`}</button>
                <button className="btn" disabled={busy} onClick={() => setConfirm(false)}>Keep on hold</button>
              </div>
            </div>
          ) : (
            <div className="actions">
              {canPay && <button className="btn primary" onClick={() => setConfirm(true)}>Pay anyway…</button>}
              {canRetry && <button className="btn primary" disabled={busy} onClick={() => resolve("retry")}>Retry payout</button>}
              {canCancel && <button className="btn danger" disabled={busy} onClick={() => resolve("cancel")}>Cancel deal{d.state === "RESERVED" ? " and free the budget" : ""}</button>}
            </div>
          )}
        </section>
      )}

      {t && (
        <section className="section" aria-labelledby="terms-h">
          <h2 id="terms-h">{d.accepted_terms ? "What was agreed" : "Current offer"}</h2>
          <dl className="facts">
            <div><dt>Total</dt><dd>{money(t.total)}</dd></div>
            <div><dt>Quantity</dt><dd>{t.quantity}</dd></div>
            <div><dt>Unit price</dt><dd>{money(Number(t.unit_price))}</dd></div>
            <div><dt>Due</dt><dd>{day(t.deadline)}</dd></div>
            <div><dt>Reserved</dt><dd>{money(d.reserved_amount)}</dd></div>
            <div><dt>Paid</dt><dd>{money(d.paid_amount)}</dd></div>
          </dl>
          {t.acceptance_criteria.length > 0 && (
            <p className="muted small">Accepted when: {t.acceptance_criteria.join(" · ")}</p>
          )}
        </section>
      )}

      <section className="section" aria-labelledby="checks-h">
        <div className="section-head">
          <h2 id="checks-h">Delivery checks</h2>
          {v && <ToneTag tone={v.verdict === "PASS" ? "done" : v.verdict === "FAIL" ? "stop" : "review"}>{v.verdict === "PASS" ? "Passed" : v.verdict === "FAIL" ? "Failed" : "Needs review"}</ToneTag>}
        </div>
        {!v ? <p className="empty">Nothing delivered yet. Handshake checks the delivery against the agreement before any money moves.</p> : (
          <>
            <ul className="checks">
              {v.checks.map((c) => (
                <li key={c.check}>
                  <Mark kind={c.passed ? "ok" : "no"} />
                  <span><span className="sr">{c.passed ? "Passed: " : "Failed: "}</span><strong>{checkLabel(c.check)}</strong><br /><span className="muted small">{c.detail}</span></span>
                </li>
              ))}
            </ul>
            {v.reasons.filter((r) => !v.checks.some((c) => !c.passed && r.includes(c.check))).map((r) => <p key={r} className="banner review">{r}</p>)}
            <p className="muted small">AI review: {v.llm.status === "ok" ? "completed" : v.llm.status === "error" ? "unavailable, so a person must decide" : "not used for this deal"}. Fixed checks decide first; the AI can only make the result stricter.</p>
          </>
        )}
      </section>

      <section className="section" aria-labelledby="chat-h">
        <h2 id="chat-h">Conversation</h2>
        <ul className="chat">
          {d.messages.map((m) => (
            <li key={m.id} className={`msg ${m.role === "seller" ? "seller" : ""} ${m.flags.length ? "flagged" : ""}`}>
              <div className="who">{m.from_name}{MSG[m.type] ? ` · ${MSG[m.type]}` : ""} <span className="muted" style={{ fontWeight: 400 }}>{when(m.ts)}</span></div>
              {m.text && <p>{m.text}</p>}
              {m.flags.length > 0 && <div className="flags">{m.flags.map((f) => <ToneTag key={f} tone="review">{FLAG[f] ?? f}</ToneTag>)}</div>}
            </li>
          ))}
        </ul>
        {d.messages.some((m) => m.flags.length) && <p className="muted small">Flagged messages come from the seller&rsquo;s side. Handshake never takes instructions from them, and the payee always comes from your verified vendor profile.</p>}
      </section>

      <section className="section" aria-labelledby="tl-h">
        <h2 id="tl-h">What happened</h2>
        <ul className="timeline">
          {d.timeline.filter((e) => SHOW.has(e.event)).map((e, i) => (
            <li key={i}><time>{when(e.ts)}</time><span>{describe(e)}</span></li>
          ))}
        </ul>
      </section>
    </div>
  );
}
