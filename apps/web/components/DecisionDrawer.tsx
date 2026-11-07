"use client";
import { useEffect, useRef } from "react";
import { Decision, useApi } from "@/lib/api";
import { money, ruleName } from "@/lib/format";
import { plainReason } from "./ApprovalAsk";
import { ErrorBanner, Loading, Mark, ToneTag } from "./ui";

const OUT: Record<string, { word: string; tone: "done" | "review" | "stop" }> = {
  PASS: { word: "Passed", tone: "done" },
  REQUIRE_APPROVAL: { word: "Needs approval", tone: "review" },
  HOLD: { word: "Held", tone: "review" },
  BLOCK: { word: "Blocked", tone: "stop" },
};
const HEAD: Record<string, { text: string; tone: "done" | "review" | "stop" }> = {
  ALLOW: { text: "Allowed", tone: "done" }, REQUIRE_APPROVAL: { text: "Needed your approval", tone: "review" },
  HOLD: { text: "Held back", tone: "review" }, BLOCK: { text: "Blocked", tone: "stop" },
};

export default function DecisionDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error, loading } = useApi<Decision>(`/v1/owner/decisions/${id}`);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const head = data ? HEAD[data.decision] : null;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="dd-h">
        <div className="section-head">
          <h2 id="dd-h">Why Handshake decided this</h2>
          <button ref={closeRef} className="btn small" onClick={onClose}>Close</button>
        </div>
        <ErrorBanner error={error} />
        {loading && !data ? <Loading what="decision" /> : data && head && (
          <>
            <div>
              <ToneTag tone={head.tone}>{head.text}</ToneTag>
              <p style={{ marginTop: 10 }}>{plainReason(data.explanation) || "Every check passed."}</p>
            </div>
            <dl className="facts">
              <div><dt>Amount</dt><dd>{money(data.request.amount)}</dd></div>
              <div><dt>Request type</dt><dd>{{ commit: "Reserve money", release: "Release payment", direct: "Direct payment" }[data.request.phase] ?? data.request.phase}</dd></div>
              <div><dt>Instruction source</dt><dd>{String(data.request.provenance?.source ?? "agent_plan").replace(/_/g, " ")}</dd></div>
            </dl>
            <section className="section">
              <h3>Checks that ran</h3>
              <ul className="checks">
                {data.rules.map((r) => {
                  const o = OUT[r.outcome] ?? OUT.PASS;
                  return (
                    <li key={r.rule}>
                      <Mark kind={r.outcome === "PASS" ? "ok" : r.outcome === "BLOCK" ? "no" : "warn"} />
                      <span><strong>{ruleName(r.rule)}</strong> <span className="muted">· {o.word}</span>{r.outcome !== "PASS" && <><br />{r.detail}</>}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
            {data.ai && (
              <section className="section">
                <h3>AI second opinion: {data.ai.risk} risk</h3>
                <p className="muted small">The AI can only make a decision stricter. It never loosens a check.</p>
                {data.ai.explanation && <p>{data.ai.explanation}</p>}
              </section>
            )}
          </>
        )}
      </aside>
    </>
  );
}
