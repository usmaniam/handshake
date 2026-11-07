"use client";
import { useState } from "react";
import DealRows from "@/components/DealRows";
import { ErrorBanner, Loading } from "@/components/ui";
import { DealRow, useApi } from "@/lib/api";

const ATTENTION = new Set(["OWNER_REVIEW", "HELD_DISPUTED", "PAYOUT_FAILED", "PAYOUT_HELD", "PAYOUT_UNCLAIMED", "BLOCKED_AT_COMMIT"]);
const DONE = new Set(["PAID", "CANCELLED", "EXPIRED", "PAYOUT_RETURNED"]);
const FILTERS = [
  { id: "all", label: "All", test: (_: DealRow) => true },
  { id: "attention", label: "Needs attention", test: (d: DealRow) => ATTENTION.has(d.state) },
  { id: "active", label: "In progress", test: (d: DealRow) => !ATTENTION.has(d.state) && !DONE.has(d.state) },
  { id: "done", label: "Finished", test: (d: DealRow) => DONE.has(d.state) },
];

export default function Deals() {
  const { data, error, loading, reload } = useApi<DealRow[]>("/v1/owner/deals", 8000);
  const [f, setF] = useState("all");
  const test = FILTERS.find((x) => x.id === f)!.test;
  const shown = (data ?? []).filter(test);
  return (
    <div className="page">
      <div className="page-head"><h1>Deals</h1><p className="muted">Every deal your agents have opened, newest first.</p></div>
      <div className="filters" role="group" aria-label="Filter deals">
        {FILTERS.map((x) => (
          <button key={x.id} className="chip" aria-pressed={f === x.id} onClick={() => setF(x.id)}>
            {x.label}{data ? ` (${data.filter(x.test).length})` : ""}
          </button>
        ))}
      </div>
      <ErrorBanner error={error} retry={reload} />
      {loading && !data ? <Loading what="deals" /> : shown.length ? <DealRows deals={shown} /> :
        <p className="empty">{f === "all" ? "No deals yet." : "No deals match this filter."}</p>}
    </div>
  );
}
