"use client";
import ApprovalAsk from "@/components/ApprovalAsk";
import { useSummary } from "@/components/Shell";
import { ErrorBanner, Loading } from "@/components/ui";
import { Approval, useApi } from "@/lib/api";

export default function Approvals() {
  const { reload: reloadSummary } = useSummary();
  const { data, error, loading, reload } = useApi<Approval[]>("/v1/owner/approvals", 6000);
  return (
    <div className="page">
      <div className="page-head">
        <h1>Approvals</h1>
        <p className="muted">Approving only covers the limits you set. It never overrides a block, a changed price, or a missing delivery.</p>
      </div>
      <ErrorBanner error={error} retry={reload} />
      {loading && !data ? <Loading what="approvals" /> : data && data.length ? (
        <ul className="rows" style={{ listStyle: "none" }}>
          {data.map((a) => <ApprovalAsk key={a.id} a={a} onDone={() => { reload(); reloadSummary(); }} />)}
        </ul>
      ) : <p className="empty">You&rsquo;re all caught up.</p>}
    </div>
  );
}
