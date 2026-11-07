"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, FormEvent, ReactNode, useContext, useEffect, useState } from "react";
import { api, ApiError, getToken, setToken, Summary, useApi } from "@/lib/api";
import { ErrorBanner } from "./ui";

type Ctx = { summary: Summary | null; reload: () => void };
const SummaryCtx = createContext<Ctx>({ summary: null, reload: () => {} });
export const useSummary = () => useContext(SummaryCtx);

const NAV: { href: string; label: string; short?: string }[] = [
  { href: "/", label: "Today" },
  { href: "/deals", label: "Deals" },
  { href: "/approvals", label: "Approvals" },
  { href: "/ledger", label: "Ledger" },
  { href: "/lab", label: "Red-team lab", short: "Lab" },
  { href: "/settings", label: "Settings" },
];

function Login({ onDone }: { onDone: () => void }) {
  const [token, setTok] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    setToken(token.trim());
    try {
      await api("/v1/owner/summary");
      onDone();
    } catch (ex) {
      setToken("");
      const x = ex as ApiError;
      setErr(x.status === 401 ? "That admin token wasn't accepted. Use the ADMIN_TOKEN set on the API." : x.message);
    } finally { setBusy(false); }
  }

  return (
    <main className="login">
      <form onSubmit={submit}>
        <div>
          <h1>Handshake</h1>
          <p className="muted">Agents negotiate the deal. Handshake pays when it&rsquo;s delivered.</p>
        </div>
        <div className="field">
          <label htmlFor="tok">Admin token</label>
          <input id="tok" type="password" autoComplete="current-password" value={token} onChange={(e) => setTok(e.target.value)} required />
          <span className="hint">Stays in this browser tab only. It&rsquo;s cleared when you close the tab.</span>
        </div>
        <ErrorBanner error={err} />
        <button className="btn primary" disabled={busy || !token.trim()}>{busy ? "Checking…" : "Sign in"}</button>
      </form>
    </main>
  );
}

function Inner({ children, signOut }: { children: ReactNode; signOut: () => void }) {
  const path = usePathname();
  const { data, reload, error } = useApi<Summary>("/v1/owner/summary", 8000);
  const pending = data?.pending_approvals ?? 0;
  return (
    <SummaryCtx.Provider value={{ summary: data, reload }}>
      <div className="app">
        <aside className="rail">
          <Link href="/" className="brand">Handshake<small>Pays when it&rsquo;s delivered</small></Link>
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}>
                  {n.short ? <><span className="long">{n.label}</span><span className="short">{n.short}</span></> : n.label}
                  {n.href === "/approvals" && pending > 0 && <span className="badge" aria-label={`${pending} waiting`}>{pending}</span>}
                </Link>
              );
            })}
          </nav>
          <div className="rail-foot muted">
            <p>{data?.owner ? `Signed in as ${data.owner}` : ""}</p>
            <button className="btn small" style={{ marginTop: 8 }} onClick={signOut}>Sign out</button>
          </div>
        </aside>
        <main className="main">
          {error && error.status === 401 ? (<><ErrorBanner error="Your session is no longer valid." /><button className="btn" style={{ marginTop: 12 }} onClick={signOut}>Sign in again</button></>) : children}
        </main>
      </div>
    </SummaryCtx.Provider>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  useEffect(() => { setAuthed(!!getToken()); setReady(true); }, []);
  if (!ready) return null;
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  return <Inner signOut={() => { setToken(""); setAuthed(false); }}>{children}</Inner>;
}
