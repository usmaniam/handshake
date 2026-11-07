"use client";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ColDef, ModuleRegistry, themeQuartz } from "ag-grid-community";
import { useMemo, useState } from "react";
import DecisionDrawer from "@/components/DecisionDrawer";
import { ErrorBanner, Loading } from "@/components/ui";
import { LedgerRow, useApi } from "@/lib/api";
import { money, stateInfo, when } from "@/lib/format";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  accentColor: "#2D5A9B", backgroundColor: "#F8FAF9", foregroundColor: "#16202B", headerBackgroundColor: "#EEF1F0",
  borderColor: "#CBD3D0", rowHoverColor: "#E2E7E5", fontSize: 14, headerFontWeight: 650,
  fontFamily: '"Schibsted Grotesk Variable", system-ui, sans-serif',
});

const DEC: Record<string, { text: string; cls: string }> = {
  ALLOW: { text: "Allowed", cls: "done" }, REQUIRE_APPROVAL: { text: "Needed approval", cls: "review" },
  HOLD: { text: "Held", cls: "review" }, BLOCK: { text: "Blocked", cls: "stop" },
};
const PHASE: Record<string, string> = { commit: "Reserve", release: "Release", direct: "Direct payment" };

export default function Ledger() {
  const { data, error, loading, reload } = useApi<LedgerRow[]>("/v1/owner/ledger", 8000);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const cols = useMemo<ColDef<LedgerRow>[]>(() => [
    { headerName: "When", field: "ts", valueFormatter: (p) => when(p.value), width: 150, sort: "desc" },
    { headerName: "Vendor", field: "vendor", valueFormatter: (p) => p.value ?? "Not tied to a deal", minWidth: 170, flex: 1 },
    { headerName: "Type", field: "phase", valueFormatter: (p) => PHASE[p.value] ?? p.value, width: 140 },
    { headerName: "Amount", field: "amount", valueFormatter: (p) => money(p.value), type: "rightAligned", width: 120, comparator: (a, b) => Number(a) - Number(b) },
    { headerName: "Decision", field: "decision", width: 170,
      cellRenderer: (p: { value: string }) => <span className={`tag ${DEC[p.value]?.cls ?? "quiet"}`}>{DEC[p.value]?.text ?? p.value}</span> },
    { headerName: "Payout", field: "payout_status", width: 190, valueFormatter: (p) => (p.value ? stateInfo(p.value).label : "-") },
    { headerName: "PayPal batch", field: "paypal_batch_id", valueFormatter: (p) => p.value ?? "-", minWidth: 190 },
  ], []);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Ledger</h1>
        <p className="muted">Every request your agents made and what Handshake did with it. Select a row to see why.</p>
      </div>
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="q">Search the ledger</label>
        <input id="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Vendor, amount, decision…" />
      </div>
      <ErrorBanner error={error} retry={reload} />
      {loading && !data ? <Loading what="ledger" /> : data && data.length === 0 ? <p className="empty">Nothing yet. Requests appear here the moment an agent asks to move money.</p> : (
        <div className="grid-host">
          <AgGridReact<LedgerRow>
            theme={theme} rowData={data ?? []} columnDefs={cols} quickFilterText={q}
            defaultColDef={{ sortable: true, resizable: true }}
            getRowId={(p) => p.data.payment_request_id}
            onRowClicked={(e) => e.data && setOpen(e.data.decision_id)}
            rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
            suppressCellFocus={false}
          />
        </div>
      )}
      {open && <DecisionDrawer id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
