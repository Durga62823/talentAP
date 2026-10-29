import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, RotateCcw } from "lucide-react";
import { Alert, Badge, Button, Card, ErrorText, PageHeader, Spinner } from "../components/ui";
import { api, fmtBytes } from "../lib/api";
import { DEMO_ACCOUNTS, useAuth } from "../lib/auth";
import { KIND_LABEL } from "../lib/connections";

export default function SettingsPage() {
  const { refresh } = useAuth();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/settings") });
  const reset = useMutation({ mutationFn: () => api("/api/demo/reset", { method: "POST" }), onSuccess: () => setTimeout(() => refresh(), 400) });
  const s = q.data;
  return (
    <div>
      <PageHeader title="Settings & Demo Setup" description="Live server configuration. Secrets (HMAC key, credential key, database passwords) are never exposed — only identifiers and whether one is stored." />
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
                  Put SENTINEL_MYSQL_ADMIN_USER / SENTINEL_MYSQL_ADMIN_PASSWORD in the repository .env, run <span className="font-mono">python -m app.cli import-mysql</span> from FULL_CODE/backend, then reset below. Backends are never substituted for one another.
                </Alert>
              </div>
            )}
          </Card>
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
            <Card title="Demo setup">
              <div className="space-y-3 text-sm">
                <p className="text-fog-300">Reset rebuilds Dream Guard's own state on the official dataset: a fresh copy of the organisers' SQLite database (the shipped file is never modified), MySQL/PostgreSQL connections if configured, a real PII scan, default policies, grants and the official sample users.</p>
                <Alert tone="warn">Deletes audit events, uploads, imported tables in the SQLite copy, custom policies and sessions. Never touches the MySQL/PostgreSQL data. Disabled when SENTINEL_ENV=production.</Alert>
                <Button variant="danger" icon={<RotateCcw className="h-4 w-4" />} loading={reset.isPending} onClick={() => confirm("Reset all demo state?") && reset.mutate()}>Reset demo environment</Button>
                <ErrorText error={reset.error} />
                {reset.data && <Alert tone="success">Demo reset complete. Signing you out…</Alert>}
                <div className="border-t border-ink-700 pt-3 text-xs text-fog-400">
                  Demo identities (official users.csv + compliance officer; local demo passwords):
                  <ul className="mt-1 space-y-0.5 font-mono">
                    {DEMO_ACCOUNTS.map((a) => <li key={a.username}>{a.username} / {a.password}</li>)}
                  </ul>
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
