// Thin fetch wrapper. The console session is an HttpOnly cookie (never readable here);
// mutating requests carry the CSRF header the backend requires for cookie sessions.

export class ApiError extends Error {
  status: number;
  code: string;
  body: any;
  constructor(status: number, code: string, message: string, body: any) {
    super(message);
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

type Opts = { method?: string; body?: unknown; bearer?: string; form?: FormData; signal?: AbortSignal; headers?: Record<string, string> };

// Empty by default: /api is same-origin (Vite proxy in dev, vercel.json rewrite in prod), so the
// session cookie stays first-party. Calling Render directly makes it a third-party cookie, which
// Safari and privacy-mode browsers drop, breaking login.
export const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

async function send(path: string, opts: Opts): Promise<Response> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { ...opts.headers };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-Sentinel-CSRF"] = "1";
  const token = opts.bearer || (typeof localStorage !== "undefined" ? localStorage.getItem("sm_token") : null);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  return fetch(url, {
    method,
    headers,
    credentials: "include",
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    signal: opts.signal,
  });
}

async function fail(res: Response): Promise<never> {
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  const err = (data && data.error) || {};
  const msg = typeof err.message === "string" ? err.message : typeof data === "string" ? data : `Request failed (${res.status})`;
  throw new ApiError(res.status, err.code ?? `http_${res.status}`, msg, data);
}

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const res = await send(path, opts);
  if (!res.ok) return fail(res);
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? await res.json() : await res.text()) as T;
}

/** For endpoints that answer with a file (e.g. signed dossiers): the body as a Blob plus response headers. */
export async function apiBlob(path: string, opts: Opts = {}): Promise<{ blob: Blob; headers: Headers }> {
  const res = await send(path, opts);
  if (!res.ok) return fail(res);
  return { blob: await res.blob(), headers: res.headers };
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---- enterprise features: SSO / SCIM, ABAC purpose binding, compliance dossiers ------------

export type SsoPersona = { login_hint: string; name: string; groups: string[]; role: string };
export type SsoProvider = { id: string; name: string; idp_type: "OIDC" | "MOCK_SAML"; issuer_host: string | null; personas?: SsoPersona[] };
export type ScimToken = {
  id: string; description: string; idp_id: string; idp_name: string | null; created_at: string; expires_at: string;
  last_used_at: string | null; status: "active" | "revoked" | "expired";
};
export type ScimTokenCreated = ScimToken & { token: string; scim_base_url: string };

export type Purpose = "CUSTOMER_SUPPORT" | "FRAUD_INVESTIGATION" | "DISPUTE_RESOLUTION" | "ANALYTICS_REPORTING" | "SECURITY_AUDIT";
export type AccessContextResult = { purpose: Purpose | null; ticket_id: string | null; rejected_attributes: string[]; abac_granted_columns: string[] };
export type ColumnDecision = {
  name: string; source: string | null; action: string; policy_id: number | null; policy_name: string | null; reason: string; abac_granted: boolean;
};

export type Framework = "DPDP" | "RBI" | "PCI_DSS";
export type DossierFormat = "pdf" | "csv" | "json";
export type ComplianceSummary = {
  generated_at: string;
  ledger: { events: number; chain_valid: boolean; head_seq: number | null; head_entry_hash: string | null; broken_at_seq: number | null };
  queries: { executed: number; denied: number };
  failed_access: number;
  privilege_violations: number;
  break_glass: number;
  purpose_distribution: Record<string, number>;
  purpose_bound_elevations: number;
  sso_logins: number;
  integrity: { runs: number; all_match: boolean | null };
  pci: { pan_columns: number; non_privileged_cleartext_egress: number; non_privileged_raw_reachable: number };
  frameworks: { id: Framework; title: string; status: "PASS" | "ATTENTION_REQUIRED"; findings: string[] }[];
  recent_dossiers: { seq: number; ts: string; actor: string; framework: Framework; dossier_sha256: string }[];
};
export type DossierReceipt = { framework: Framework; format: DossierFormat; sha256: string; signature: string; auditEventId: string; filename: string; at: string };

/** Like api() but resolves with the JSON body for 4xx query denials, which are real results. */
export async function apiAllowDenied<T = any>(path: string, opts: Opts = {}): Promise<{ ok: boolean; status: number; body: T }> {
  try {
    const body = await api<T>(path, opts);
    return { ok: true, status: 200, body };
  } catch (e) {
    if (e instanceof ApiError && e.status !== 401 && e.body && typeof e.body === "object") {
      return { ok: false, status: e.status, body: e.body as T };
    }
    throw e;
  }
}

export function download(path: string) {
  const a = document.createElement("a");
  a.href = path.startsWith("http") ? path : `${API_BASE}${path}`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function fmtTime(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
