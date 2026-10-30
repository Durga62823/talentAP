import { useQuery } from "@tanstack/react-query";
import { Database, Gauge } from "lucide-react";
import { Alert, Badge, Card, ErrorText, PageHeader, Spinner } from "../components/ui";
import { api, fmtBytes } from "../lib/api";

import { KIND_LABEL } from "../lib/connections";

export default function SettingsPage() {

  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/settings") });

  const s = q.data;
  return (
    <div>
      <PageHeader title="Settings & Demo Setup" />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorText error={q.error} /> : (
        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-2"><Database className="h-4 w-4 text-fog-400" /> Dataset & database configuration</span>}>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{s.dataset.name}</span>
              <Badge tone={s.dataset.available ? "green" : "red"}>{s.dataset.available ? "found" : "missing"}</Badge>
              <span className="text-xs text-fog-400">{s.dataset.tables} tables · {s.dataset.official_rows.toLocaleString()} official rows · <span className="font-mono">{s.dataset.location}</span></span>
            </div>
            <table className="w-full">
              <thead><tr><th className="th">Connection</th><th className="th">Backend</th><th className="th">Target</th><th className="th">Schemas</th><th className="th">Credential</th><th className="th">Status</th></tr></thead>
              <tbody>
                {s.connections.map((c: any) => (
                  <tr key={c.name}>
                    <td className="td">{c.name}</td>
                    <td className="td"><Badge tone={c.kind === "sqlite" ? "cyan" : c.kind === "mysql" ? "amber" : "indigo"}>{KIND_LABEL[c.kind] ?? c.kind}</Badge></td>
                    <td className="td mono">{c.target}</td>
                    <td className="td mono text-xs">{c.schemas.join(", ")}</td>
                    <td className="td text-xs">{c.kind === "sqlite" ? "file" : c.password_stored ? "stored (encrypted)" : "none"}</td>
                    <td className="td"><Badge tone={c.status === "healthy" ? "green" : c.status === "unhealthy" ? "red" : "neutral"}>{c.status}</Badge>{c.status === "unhealthy" && <div className="mt-0.5 text-[11px] text-rose-300">{c.status_detail}</div>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!s.mysql_import_configured && (
              <div className="mt-3">
                <Alert tone="info" title="MySQL not configured yet">
                  Put SENTINEL_MYSQL_ADMIN_USER / SENTINEL_MYSQL_ADMIN_PASSWORD in the repository .env, and run <span className="font-mono">python -m app.cli import-mysql</span> from FULL_CODE/backend.
                </Alert>
              </div>
            )}
          </Card>
          <PerformanceCard />
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Enforcement settings">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                {[
                  ["Environment", <Badge tone="amber">{s.environment}</Badge>],
                  ["Max rows per query", s.max_result_rows],
                  ["Query timeout", `${s.query_timeout_ms} ms`],
                  ["Aggregate k-threshold", `groups < ${s.min_aggregate_group} suppressed`],
                  ["Max upload", fmtBytes(s.max_upload_bytes)],
                  ["Upload retention", `${s.upload_retention_minutes} min (CSV only)`],
                  ["Allowed DB hosts", s.allowed_db_hosts.join(", ")],
                  ["HMAC key id", <span className="font-mono">{s.hmac_key_id}</span>],
                  ["National-ID jurisdictions", s.jurisdictions.join(", ")],
                  ["Legacy .doc support", s.legacy_doc_support ? <Badge tone="green">antiword available</Badge> : <Badge tone="red">not available</Badge>],
                  ["Session lifetime", `${s.session_hours} h`],
                ].map(([k, v], i) => (
                  <div key={i}><dt className="label">{k}</dt><dd>{v}</dd></div>
                ))}
              </dl>
            </Card>

          </div>
        </div>
      )}
    </div>
  );
}

function PerformanceCard() {
  // Live request metrics from the server (in-memory; reset on restart). Refreshes every 15 s.
  const m = useQuery({ queryKey: ["metrics"], queryFn: () => api("/api/metrics"), refetchInterval: 15_000 });
  const d = m.data;
  return (
    <Card title={<span className="flex items-center gap-2"><Gauge className="h-4 w-4 text-fog-400" /> Performance</span>} subtitle="Server-side latency per endpoint since the last restart">
      {m.isLoading ? <Spinner /> : m.error ? <ErrorText error={m.error} /> : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <Metric label="Requests" value={d.requests.toLocaleString()} />
            <Metric label="Server error rate" value={`${(d.server_error_rate * 100).toFixed(2)}%`} />
            <Metric label="Query cache hit rate" value={`${(d.query_cache.hit_rate * 100).toFixed(1)}%`} hint={`${d.query_cache.hits} hits · ${d.query_cache.misses} misses`} />
            <Metric label="Uptime" value={`${Math.floor(d.uptime_s / 3600)}h ${Math.floor((d.uptime_s % 3600) / 60)}m`} />
          </div>
          <table className="w-full">
            <thead><tr><th className="th">Endpoint</th><th className="th text-right">Calls</th><th className="th text-right">p50</th><th className="th text-right">p95</th><th className="th text-right">p99</th><th className="th text-right">Errors</th></tr></thead>
            <tbody>
              {d.routes.slice(0, 12).map((r: any) => (
                <tr key={r.route}>
                  <td className="td mono text-xs">{r.route}</td>
                  <td className="td text-right">{r.count}</td>
                  <td className="td text-right mono">{r.p50_ms} ms</td>
                  <td className="td text-right mono">{r.p95_ms} ms</td>
                  <td className="td text-right mono">{r.p99_ms} ms</td>
                  <td className="td text-right">{r.server_errors ? <Badge tone="red">{r.server_errors}</Badge> : r.client_errors ? <Badge tone="amber">{r.client_errors} 4xx</Badge> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
      <div className="text-xs text-fog-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-fog-100">{value}</div>
      {hint && <div className="text-[11px] text-fog-500">{hint}</div>}
    </div>
  );
}
