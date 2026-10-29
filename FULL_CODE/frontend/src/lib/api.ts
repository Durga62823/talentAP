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

type Opts = { method?: string; body?: unknown; bearer?: string; form?: FormData; signal?: AbortSignal };

export const API_BASE = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_BACKEND_URL ||
  import.meta.env.API_URL ||
  (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1"
    ? "https://talentap-backend.onrender.com"
    : "")
).replace(/\/$/, "");

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-Sentinel-CSRF"] = "1";
  const token = opts.bearer || (typeof localStorage !== "undefined" ? localStorage.getItem("sm_token") : null);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    signal: opts.signal,
  });
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const err = (data && data.error) || {};
    const msg = typeof err.message === "string" ? err.message : typeof data === "string" ? data : `Request failed (${res.status})`;
    throw new ApiError(res.status, err.code ?? `http_${res.status}`, msg, data);
  }
  return data as T;
}

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
