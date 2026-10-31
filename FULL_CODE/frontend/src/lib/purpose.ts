// Session purpose & ticket binding (ABAC). Kept per browser tab in sessionStorage so it follows the
// agent from Customer Lookup to the 360° profile, and sent with protected queries as request headers.
// The server format-checks both, applies purpose-bound policies, and hash-chains them into the audit log.
import { useSyncExternalStore } from "react";
import type { Purpose } from "./api";

export type PurposeBinding = { purpose: Purpose | ""; ticketId: string };

export const SUPPORT_PURPOSES: { value: Purpose; label: string }[] = [
  { value: "CUSTOMER_SUPPORT", label: "Customer Inbound Support" },
  { value: "FRAUD_INVESTIGATION", label: "Fraud Triage" },
  { value: "DISPUTE_RESOLUTION", label: "Dispute Resolution" },
];

// Mirrors the server's check; anything else is ignored there and flagged in the audit entry.
export const TICKET_RE = /^[A-Z][A-Z0-9]{1,15}-\d{1,12}$/;

const KEY = "dg_purpose_binding";
const EMPTY: PurposeBinding = { purpose: "", ticketId: "" };
const listeners = new Set<() => void>();

function read(): PurposeBinding {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

let current = read();

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function setPurposeBinding(next: PurposeBinding) {
  current = { purpose: next.purpose, ticketId: next.ticketId.trim().toUpperCase() };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // storage unavailable (private mode): the binding still lives for this page view
  }
  listeners.forEach((l) => l());
}

export function clearPurposeBinding() {
  setPurposeBinding(EMPTY);
}

export function usePurposeBinding(): PurposeBinding {
  return useSyncExternalStore(subscribe, () => current);
}

export function purposeHeaders(b: PurposeBinding): Record<string, string> {
  const h: Record<string, string> = {};
  if (b.purpose) h["X-DreamGuard-Purpose"] = b.purpose;
  if (b.ticketId) h["X-DreamGuard-Ticket-Id"] = b.ticketId;
  return h;
}

export function purposeLabel(p: string | null | undefined) {
  return SUPPORT_PURPOSES.find((x) => x.value === p)?.label ?? p ?? "";
}
