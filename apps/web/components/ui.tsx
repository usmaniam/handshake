"use client";
import { ReactNode } from "react";
import { ApiError, DealRow } from "@/lib/api";
import { stateInfo, TRACK } from "@/lib/format";

export function Tag({ state, children }: { state: string; children?: ReactNode }) {
  const s = stateInfo(state);
  return <span className={`tag ${s.tone}`}>{children ?? s.label}</span>;
}

export function ToneTag({ tone, children }: { tone: "done" | "wait" | "review" | "stop" | "quiet"; children: ReactNode }) {
  return <span className={`tag ${tone}`}>{children}</span>;
}

/** The parcel-tracking style line: where a deal is, coloured by how it's going. */
export function Track({ state, compact = false }: { state: string; compact?: boolean }) {
  const s = stateInfo(state);
  return (
    <ol className={`track ${s.tone} ${compact ? "compact" : ""}`} aria-label={`Progress: ${s.label}`}>
      {TRACK.map((label, i) => (
        <li key={label} className={`${i <= s.step ? "reached" : ""} ${i === s.step ? "now" : ""}`} aria-current={i === s.step ? "step" : undefined}>
          <span>{label}</span>
        </li>
      ))}
    </ol>
  );
}

/** Pass / fail / attention marks drawn as SVG so they never depend on font glyphs. */
export function Mark({ kind }: { kind: "ok" | "no" | "warn" }) {
  const fill = kind === "ok" ? "var(--teal)" : kind === "no" ? "var(--brick)" : "var(--amber)";
  const d = kind === "ok" ? "M5.2 9.3l2.7 2.7 5-5.4" : kind === "no" ? "M6 6l6 6M12 6l-6 6" : "M9 5v5.2M9 12.6v.2";
  return (
    <span className="mark" aria-hidden>
      <svg width="18" height="18" viewBox="0 0 18 18" focusable="false">
        <circle cx="9" cy="9" r="9" fill={fill} />
        <path d={d} fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function ErrorBanner({ error, retry }: { error: ApiError | string | null; retry?: () => void }) {
  if (!error) return null;
  const msg = typeof error === "string" ? error : error.message;
  return (
    <div className="banner stop" role="alert">
      <p>{msg}</p>
      {retry && <button className="btn small" style={{ marginTop: 10 }} onClick={retry}>Try again</button>}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted" role="status">Loading {what}…</p>;
}

export function dealAmount(d: DealRow) {
  return d.accepted_terms?.total ?? d.current_terms?.total ?? "0";
}
export function dealItem(d: DealRow) {
  const t = d.accepted_terms ?? d.current_terms;
  return t ? `${t.item} × ${t.quantity}` : "-";
}
