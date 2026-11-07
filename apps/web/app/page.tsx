"use client";
import Link from "next/link";
import { useSummary } from "@/components/Shell";
import ApprovalAsk from "@/components/ApprovalAsk";
import DealRows from "@/components/DealRows";
import { ErrorBanner, Loading } from "@/components/ui";
import { Approval, DealRow, useApi } from "@/lib/api";
import { money } from "@/lib/format";

export default function Today() {
  const { summary, reload: reloadSummary } = useSummary();
  const approvals = useApi<Approval[]>("/v1/owner/approvals", 8000);
  const deals = useApi<DealRow[]>("/v1/owner/deals", 8000);

  const total = Number(summary?.budget_total ?? 0) || 1;
  const pct = (v?: string) => `${Math.min(100, (Number(v ?? 0) / total) * 100)}%`;
  const refresh = () => { approvals.reload(); deals.reload(); reloadSummary(); };

  return (
    <div className="page">
      <div className="page-head">
        <h1>Today</h1>
        <p className="muted">{summary ? `${summary.owner}'s money, deals and anything waiting on you.` : ""}</p>
      </div>

      <section className="section budget" aria-labelledby="budget-h">
        <h2 id="budget-h">This week&rsquo;s budget</h2>
        {!summary ? <Loading what="budget" /> : (
          <>
            <div className="bar" role="img" aria-label={`Spent ${money(summary.spent)}, reserved ${money(summary.reserved)}, available ${money(summary.available)} of ${money(summary.budget_total)}`}>
              <i className="spent" style={{ width: pct(summary.spent) }} />
              <i className="reserved" style={{ width: pct(summary.reserved) }} />
            </div>
            <div className="legend">
              <div><b>{money(summary.available)}</b><span>Available of {money(summary.budget_total)}</span></div>
              <div><b>{money(summary.reserved)}</b><span><i className="dot" style={{ background: "var(--blue)" }} />Reserved for open deals</span></div>
              <div><b>{money(summary.spent)}</b><span><i className="dot" style={{ background: "var(--teal)" }} />Paid out</span></div>
              <div><b>{money(summary.blocked_amount)}</b><span>Requests Handshake refused</span></div>
            </div>
          </>
        )}
      </section>

      <section className="section" aria-labelledby="needs-h">
        <div className="section-head">
          <h2 id="needs-h">Needs you{approvals.data?.length ? ` (${approvals.data.length})` : ""}</h2>
        </div>
        <ErrorBanner error={approvals.error} retry={approvals.reload} />
        {approvals.loading && !approvals.data ? <Loading what="approvals" /> :
          approvals.data && approvals.data.length > 0 ? (
            <ul className="rows" style={{ listStyle: "none" }}>
              {approvals.data.map((a) => <ApprovalAsk key={a.id} a={a} onDone={refresh} />)}
            </ul>
          ) : <p className="empty">Nothing is waiting on you. Handshake asks when a payment is over your ${summary?.approval_threshold ? Number(summary.approval_threshold) : 100} limit, goes to a new payee, or looks unusual.</p>}
      </section>

      <section className="section" aria-labelledby="deals-h">
        <div className="section-head">
          <h2 id="deals-h">Recent deals</h2>
          <Link href="/deals" className="small">All deals</Link>
        </div>
        <ErrorBanner error={deals.error} retry={deals.reload} />
        {deals.loading && !deals.data ? <Loading what="deals" /> :
          deals.data && deals.data.length > 0 ? <DealRows deals={deals.data.slice(0, 6)} /> :
          <p className="empty">No deals yet. When your buyer agent starts negotiating with a seller, the deal shows up here.</p>}
      </section>
    </div>
  );
}
