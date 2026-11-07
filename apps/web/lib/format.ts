export const money = (v: string | number | null | undefined) =>
  v == null ? "-" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(v));

export const when = (iso: string) => {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z"); // API timestamps are naive UTC
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

export const day = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

export type Tone = "done" | "wait" | "review" | "stop" | "quiet";

/** Plain-language state and its position on the tracking line (0..5). */
export const STATES: Record<string, { label: string; step: number; tone: Tone; hint: string }> = {
  DRAFT: { label: "Draft", step: 0, tone: "quiet", hint: "" },
  NEGOTIATING: { label: "Haggling", step: 0, tone: "wait", hint: "The agents are still agreeing on terms." },
  AGREED: { label: "Agreed", step: 1, tone: "wait", hint: "Terms are locked. Budget isn't reserved yet." },
  BLOCKED_AT_COMMIT: { label: "Blocked", step: 1, tone: "stop", hint: "Handshake refused to commit money to this deal." },
  RESERVED: { label: "Money reserved", step: 2, tone: "wait", hint: "Budget is set aside. Waiting for the seller to deliver." },
  DELIVERY_CLAIMED: { label: "Checking delivery", step: 3, tone: "wait", hint: "" },
  VERIFYING: { label: "Checking delivery", step: 3, tone: "wait", hint: "" },
  RELEASE_CHECK: { label: "Delivery verified", step: 4, tone: "wait", hint: "Delivery matches the agreement. Waiting for the release check." },
  OWNER_REVIEW: { label: "Needs your review", step: 3, tone: "review", hint: "Handshake wants a person to look at this one." },
  HELD_DISPUTED: { label: "On hold", step: 3, tone: "stop", hint: "No money moves until you decide." },
  RELEASING: { label: "Paying out", step: 5, tone: "wait", hint: "PayPal is processing the payout." },
  PAID: { label: "Paid", step: 5, tone: "done", hint: "" },
  PAYOUT_HELD: { label: "Payout held by PayPal", step: 5, tone: "review", hint: "PayPal is holding the payout." },
  PAYOUT_UNCLAIMED: { label: "Payout unclaimed", step: 5, tone: "review", hint: "The recipient hasn't claimed it yet." },
  PAYOUT_FAILED: { label: "Payout failed", step: 5, tone: "stop", hint: "Your budget is still reserved. Retry or cancel." },
  PAYOUT_RETURNED: { label: "Payout returned", step: 5, tone: "quiet", hint: "The money came back to you." },
  EXPIRED: { label: "Expired", step: 2, tone: "quiet", hint: "The seller didn't deliver in time. Budget returned." },
  CANCELLED: { label: "Cancelled", step: 0, tone: "quiet", hint: "" },
};
export const stateInfo = (s: string) => STATES[s] || { label: s, step: 0, tone: "quiet" as Tone, hint: "" };

const CHECK: Record<string, string> = {
  tracking_found: "Tracking number found", carrier_delivered: "Carrier shows delivered", proof_unused: "Proof not used in another deal",
  quantity_sku: "Right item and quantity", on_time: "Delivered on time", destination: "Right address", file_count: "Number of files",
};
export function checkLabel(name: string): string {
  if (CHECK[name]) return CHECK[name];
  const [k, rest] = name.split(":");
  const m: Record<string, string> = { type: "File type", name: "File name", size: "File size", svg_parses: "SVG opens", dimensions: "Image size" };
  if (m[k] && rest) return `${m[k]}: ${rest}`;
  if (k.startsWith("has_")) return `Includes a .${k.slice(4)} file`;
  return name;
}

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const MOVED_TO: Record<string, string> = {
  NEGOTIATING: "Negotiation started", AGREED: "Both sides agreed", RESERVED: "Budget reserved",
  DELIVERY_CLAIMED: "Seller claimed delivery", VERIFYING: "Checking the delivery", RELEASE_CHECK: "Delivery verified",
  OWNER_REVIEW: "Sent to you for review", HELD_DISPUTED: "Put on hold", BLOCKED_AT_COMMIT: "Blocked before any money was reserved",
  RELEASING: "Payout sent to PayPal", PAID: "Paid", PAYOUT_FAILED: "Payout failed", PAYOUT_HELD: "PayPal is holding the payout",
  PAYOUT_UNCLAIMED: "Payout waiting to be claimed", PAYOUT_RETURNED: "Payout returned", EXPIRED: "Expired", CANCELLED: "Cancelled",
};

export const TRACK = ["Haggling", "Agreed", "Reserved", "Checking", "Verified", "Paid"];

export const RULE_NAMES: Record<string, string> = {
  per_transaction_cap: "Per-payment limit", budget_window: "Weekly budget", vendor_allowlist: "Verified payee",
  category: "Allowed category", velocity: "Payment frequency", new_payee: "New payee", approval_threshold: "Approval threshold",
  payee_change: "Payee unchanged", terms_drift: "Terms unchanged since accept", deal_match: "Matches the agreement",
  delivery_required: "Delivery verified", proof_consumed: "Proof not reused", deadline: "On time",
  duplicate: "Not already paid", deposit_pressure: "No pressure for a deposit", provenance: "Instruction source",
};
export const ruleName = (r: string) => RULE_NAMES[r] || r;
