"use client";
import { FormEvent, useEffect, useState } from "react";
import { useSummary } from "@/components/Shell";
import { ErrorBanner, Loading, ToneTag } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";

type Vendor = { id: string; name: string; category: string; trust_level: string; payee: string; verified: boolean };
type AgentRow = { id: string; name: string; role: string; status: string };

export default function Settings() {
  const { summary, reload: reloadSummary } = useSummary();
  const vendors = useApi<Vendor[]>("/v1/owner/vendors");
  const agents = useApi<AgentRow[]>("/v1/owner/agents");
  const [f, setF] = useState({ budget_total: "", approval_threshold: "", per_tx_cap: "", velocity_per_hour: "", budget_period_days: "", allowed_categories: "" });
  const [msg, setMsg] = useState<{ tone: "done" | "stop"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState<string | null>(null);
  const [sweep, setSweep] = useState<string | null>(null);

  useEffect(() => {
    if (!summary) return;
    const s = summary.settings;
    setF({ budget_total: String(Number(summary.budget_total)), approval_threshold: String(Number(summary.approval_threshold)),
      per_tx_cap: String(s.per_tx_cap), velocity_per_hour: String(s.velocity_per_hour), budget_period_days: String(s.budget_period_days),
      allowed_categories: s.allowed_categories.join(", ") });
  }, [summary]);

  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      await api("/v1/owner/policy", { method: "PUT", body: {
        budget_total: Number(f.budget_total), approval_threshold: Number(f.approval_threshold), per_tx_cap: Number(f.per_tx_cap),
        velocity_per_hour: Number(f.velocity_per_hour), budget_period_days: Number(f.budget_period_days),
        allowed_categories: f.allowed_categories.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean) } });
      setMsg({ tone: "done", text: "Limits saved. They apply to the next request." });
      reloadSummary();
    } catch (ex) { setMsg({ tone: "stop", text: (ex as ApiError).message }); }
    finally { setBusy(false); }
  }

  async function revoke(a: AgentRow) {
    if (!window.confirm(`Revoke ${a.name}? It will immediately lose access and can't be restored from here.`)) return;
    try { await api(`/v1/owner/agents/${a.id}/revoke`, { method: "POST", body: {} }); agents.reload(); }
    catch (ex) { setMsg({ tone: "stop", text: (ex as ApiError).message }); }
  }

  const field = (k: keyof typeof f, label: string, hint?: string, type = "number") => (
    <div className="field">
      <label htmlFor={k}>{label}</label>
      <input id={k} type={type} step={type === "number" ? "any" : undefined} min={type === "number" ? 0 : undefined} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} required />
      {hint && <span className="hint">{hint}</span>}
    </div>
  );

  return (
    <div className="page">
      <div className="page-head"><h1>Settings</h1><p className="muted">The limits your agents can&rsquo;t talk their way past.</p></div>

      <form className="section" onSubmit={save} aria-labelledby="lim-h">
        <h2 id="lim-h">Spending limits</h2>
        {!summary ? <Loading what="limits" /> : (
          <>
            <div className="form-grid">
              {field("budget_total", "Weekly budget ($)", "Reserved and paid money count against this.")}
              {field("approval_threshold", "Ask me above ($)", "Larger payments wait for your approval.")}
              {field("per_tx_cap", "Never pay more than ($)", "Hard limit per payment. Approval can't raise it.")}
              {field("velocity_per_hour", "Max payouts per hour")}
              {field("budget_period_days", "Budget period (days)")}
              {field("allowed_categories", "Allowed vendor categories", "Separate with commas.", "text")}
            </div>
            {msg && <div className={`banner ${msg.tone}`} role="status">{msg.text}</div>}
            <div className="actions"><button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save limits"}</button></div>
          </>
        )}
      </form>

      <section className="section" aria-labelledby="ven-h">
        <h2 id="ven-h">Verified vendors</h2>
        <ErrorBanner error={vendors.error} retry={vendors.reload} />
        {vendors.data && (
          <ul className="rows" style={{ listStyle: "none" }}>
            {vendors.data.map((v) => (
              <li key={v.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                <div><div className="title">{v.name}</div><div className="sub">{v.category} · pays to {v.payee}</div></div>
                <ToneTag tone={v.trust_level === "new" ? "review" : "done"}>{v.trust_level === "new" ? "New payee" : "Known payee"}</ToneTag>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section" aria-labelledby="ag-h">
        <h2 id="ag-h">Agents</h2>
        <ErrorBanner error={agents.error} retry={agents.reload} />
        {agents.data && (
          <ul className="rows" style={{ listStyle: "none" }}>
            {agents.data.map((a) => (
              <li key={a.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                <div><div className="title">{a.name}</div><div className="sub">{a.role === "buyer" ? "Buys for you" : "Sells to you"}</div></div>
                {a.status === "active" ? <button className="btn danger small" onClick={() => revoke(a)}>Revoke access</button> : <ToneTag tone="quiet">Revoked</ToneTag>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section" aria-labelledby="maint-h">
        <h2 id="maint-h">Checks and upkeep</h2>
        <div className="actions">
          <button className="btn" onClick={async () => { try { const r = await api<{ ok: boolean; checked: number }>("/v1/owner/audit/verify"); setAudit(r.ok ? `Audit log intact: ${r.checked} entries verified.` : "The audit log has been altered."); } catch (e) { setAudit((e as ApiError).message); } }}>Verify audit log</button>
          <button className="btn" onClick={async () => { try { const r = await api<{ expired: string[]; synced: number; resent: number }>("/v1/owner/sweep", { method: "POST", body: {} }); setSweep(`Checked ${r.synced} payouts with PayPal, resent ${r.resent}, expired ${r.expired.length} overdue deals.`); reloadSummary(); } catch (e) { setSweep((e as ApiError).message); } }}>Check PayPal for updates</button>
        </div>
        {audit && <p role="status">{audit}</p>}
        {sweep && <p role="status">{sweep}</p>}
      </section>
    </div>
  );
}
