"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const KEY = "handshake.admin";

export const getToken = () => (typeof window === "undefined" ? "" : sessionStorage.getItem(KEY) || "");
export const setToken = (t: string) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY));

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method: init.method || "GET",
      headers: {
        Authorization: `Bearer ${getToken()}`,
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError(0, `Can't reach the Handshake API at ${API_BASE}. Check that it's running and that this site's address is in ALLOWED_ORIGINS.`);
  }
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const msg = data?.error || (typeof data?.detail === "string" ? data.detail : null) || text.slice(0, 200) || res.statusText;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

/** GET with optional polling. Keeps the last good data on screen while refreshing. */
export function useApi<T = any>(path: string | null, pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (alive.current) setError(e as ApiError);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    setLoading(true);
    load();
    const t = pollMs ? setInterval(load, pollMs) : undefined;
    return () => { alive.current = false; if (t) clearInterval(t); };
  }, [load, pollMs]);

  return { data, error, loading, reload: load };
}

export type Summary = {
  owner: string; budget_total: string; reserved: string; spent: string; available: string; blocked_amount: string;
  pending_approvals: number; approval_threshold: string;
  settings: { per_tx_cap: number; velocity_per_hour: number; budget_period_days: number; allowed_categories: string[] };
};
export type Terms = {
  version: number; item: string; quantity: number; unit_price: string; total: string; deadline: string;
  deliverable_type: string; acceptance_criteria: string[]; accepted: boolean;
};
export type Check = { check: string; passed: boolean; detail: string };
export type DealRow = {
  id: string; state: string; vendor: string | null; created_at: string; reserved_amount: string; paid_amount: string;
  current_terms: Terms | null; accepted_terms: Terms | null;
  verification: { verdict: string; reasons: string[]; checks: Check[]; llm: { status: string } } | null;
};
export type DealDetail = DealRow & {
  messages: { id: string; from_name: string; role: string | null; type: string; text: string; flags: string[]; provenance: string; ts: string }[];
  timeline: { ts: string; event: string; payload: Record<string, any> }[];
};
export type Approval = { id: string; kind: string; deal_id: string | null; vendor: string | null; amount: string; reason: string; status: string; ts: string };
export type LedgerRow = {
  ts: string; payment_request_id: string; deal_id: string | null; vendor: string | null; phase: string; amount: string;
  payee: string | null; decision: string; decision_id: string; explanation: string;
  payout_status: string | null; paypal_status: string | null; paypal_batch_id: string | null;
};
export type Decision = {
  id: string; decision: string; explanation: string; rules: { rule: string; outcome: string; detail: string }[];
  ai: { risk: string; signals: string[]; explanation: string } | null;
  request: { id: string; phase: string; amount: string; payee: string | null; deal_id: string | null; provenance: Record<string, any> };
};
