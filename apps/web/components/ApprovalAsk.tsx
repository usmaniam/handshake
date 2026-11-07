"use client";
import Link from "next/link";
import { useState } from "react";
import { api, Approval, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { ErrorBanner } from "./ui";

const KIND: Record<string, string> = {
  commit: "Reserve money for this deal",
  release: "Release payment",
  direct: "Send a payment",
};

/** "Needs your approval. approval_threshold: $210 is over..." -> "$210 is over..." */
export function plainReason(raw: string) {
  const s = raw
    .replace(/^(Needs your approval|Blocked|Payment held|Allowed by policy)\.\s*/, "")
    .split("; ")
    .map((p) => p.replace(/^[a-z_]+:\s*/, ""))
    .join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ApprovalAsk({ a, onDone }: { a: Approval; onDone: () => void }) {
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decide(approve: boolean) {
    setBusy(approve ? "yes" : "no"); setErr(null);
    try {
      await api(`/v1/owner/approvals/${a.id}`, { method: "POST", body: { approve, reason: approve ? "Approved in console" : "Denied in console" } });
      onDone();
    } catch (e) {
      setErr((e as ApiError).message);
      setBusy(null);
    }
  }

  return (
    <li className="ask">
      <div>
        <h3>{a.vendor ?? "Payment"} <span className="muted" style={{ fontWeight: 400 }}>· {KIND[a.kind] ?? a.kind}</span></h3>
        <p className="why">{plainReason(a.reason)}</p>
        {a.deal_id && <p className="small"><Link href={`/deals/${a.deal_id}`}>See the whole deal</Link></p>}
        <ErrorBanner error={err} />
      </div>
      <div className="actions">
        <button className="btn danger" disabled={!!busy} onClick={() => decide(false)}>{busy === "no" ? "Denying…" : "Deny"}</button>
        <button className="btn primary" disabled={!!busy} onClick={() => decide(true)}>{busy === "yes" ? "Approving…" : `Approve ${money(a.amount)}`}</button>
      </div>
    </li>
  );
}
