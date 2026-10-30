import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Database, KeyRound, Plug, Plus, Radar, Trash2 } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Button, Card, Empty, ErrorText, Modal, PageHeader, SensBadge, Spinner } from "../components/ui";
import { api, fmtTime } from "../lib/api";
import { KIND_LABEL, useConnections, type Conn } from "../lib/connections";

function AddConnection({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"sqlite" | "postgresql" | "mysql">("mysql");
  const [f, setF] = useState({ name: "", file: "", host: "localhost", port: "3306", database: "saffron_bank", username: "sentinel_app", password: "", schemas: "saffron_bank, saffron_imports", importDb: "saffron_imports" });
  const pick = (k: "sqlite" | "postgresql" | "mysql") => {
    setKind(k);
    if (k === "mysql") setF((x) => ({ ...x, port: "3306", schemas: "saffron_bank, saffron_imports", importDb: "saffron_imports" }));
    if (k === "postgresql") setF((x) => ({ ...x, port: "5432", schemas: "public", importDb: "" }));
  };
  const m = useMutation({
    mutationFn: () =>
      api("/api/databases", {
        body:
          kind === "sqlite"
            ? { name: f.name, kind, file: f.file }
            : {
              name: f.name, kind, host: f.host, port: Number(f.port), database: f.database, username: f.username, password: f.password || undefined,
              allowed_schemas: f.schemas.split(",").map((s) => s.trim()).filter(Boolean),
              import_database: kind === "mysql" && f.importDb ? f.importDb : undefined,
            },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      setF((x) => ({ ...x, password: "" }));
      onClose();
    },
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title="Register database connection">
      <form
        className="space-y-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          m.mutate();
        }}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {(["mysql", "postgresql", "sqlite"] as const).map((k) => (
            <button
              type="button"
              key={k}
              onClick={() => pick(k)}
              className={`rounded-lg border px-3 py-2 text-sm font-semibold transition-all ${
                kind === k
                  ? "border-[#1D5FA7] bg-[#EAF2FB] text-[#123B67] shadow-sm"
                  : "border-[#DCE5F0] bg-white text-[#64748B] hover:bg-[#F4F8FD] hover:text-[#172B45]"
              }`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <div>
          <label className="label">Display name</label>
          <input className="input" value={f.name} onChange={set("name")} required minLength={2} />
        </div>
        {kind === "sqlite" ? (
          <div>
            <label className="label">Database file (inside data/targets)</label>
            <input className="input font-mono" placeholder="bank.db" value={f.file} onChange={set("file")} required />
            <p className="mt-1 text-[11px] text-[#64748B]">Plain file names only — paths and traversal are rejected server-side.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_100px] gap-2.5">
              <div>
                <label className="label">Host</label>
                <input className="input" value={f.host} onChange={set("host")} required />
              </div>
              <div>
                <label className="label">Port</label>
                <input className="input" value={f.port} onChange={set("port")} inputMode="numeric" required />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="label">Database</label>
                <input className="input" value={f.database} onChange={set("database")} required />
              </div>
              <div>
                <label className="label">Username</label>
                <input className="input" value={f.username} onChange={set("username")} required autoComplete="off" />
              </div>
            </div>
            <div>
              <label className="label">Password</label>
              <input className="input" type="password" value={f.password} onChange={set("password")} autoComplete="new-password" />
              <p className="mt-1 flex items-center gap-1 text-[11px] text-[#64748B]">
                <KeyRound className="h-3 w-3 text-[#1D5FA7]" /> Encrypted at rest on the server and never returned to the browser.
              </p>
            </div>
            <div>
              <label className="label">Allowed {kind === "mysql" ? "databases" : "schemas"}</label>
              <input className="input" value={f.schemas} onChange={set("schemas")} />
            </div>
            {kind === "mysql" && (
              <div>
                <label className="label">Import database (writable, separate)</label>
                <input className="input" value={f.importDb} onChange={set("importDb")} />
              </div>
            )}
            <Alert tone="info">Hosts must be on the server allow-list (SENTINEL_ALLOWED_DB_HOSTS) — this blocks SSRF to internal services. Use a least-privilege role.</Alert>
          </>
        )}
        <ErrorText error={m.error} />
        <div className="flex justify-end gap-2 pt-2 border-t border-[#DCE5F0]">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={m.isPending}>
            Save connection
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function SchemaView({ conn }: { conn: Conn }) {
  const q = useQuery({ queryKey: ["schema", conn.id], queryFn: () => api(`/api/databases/${conn.id}/schema`) });
  const [open, setOpen] = useState<string | null>(null);
  if (q.isLoading) return <Spinner label="Reading schema…" />;
  if (q.error) return <ErrorText error={q.error} />;
  return (
    <div className="divide-y divide-[#DCE5F0] rounded-lg border border-[#DCE5F0] bg-white overflow-hidden shadow-sm">
      {q.data.tables.map((t: any) => (
        <div key={t.table}>
          <button className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm hover:bg-[#F4F8FD] transition-colors" onClick={() => setOpen(open === t.table ? null : t.table)}>
            {open === t.table ? <ChevronDown className="h-4 w-4 text-[#64748B]" /> : <ChevronRight className="h-4 w-4 text-[#64748B]" />}
            <span className="font-mono font-semibold text-[#172B45]">{t.schema}.{t.table}</span>
            <span className="text-xs text-[#64748B]">{t.row_count} rows · {t.columns.length} columns</span>
            <span className="ml-auto flex gap-1">
              {(() => {
                const n = t.columns.filter((c: any) => ["PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL"].includes(c.classification?.sensitivity)).length;
                const un = t.columns.filter((c: any) => !c.classification).length;
                return (
                  <>
                    {n > 0 && <Badge tone="amber">{n} sensitive</Badge>}
                    {un > 0 && <Badge tone="red">not scanned</Badge>}
                  </>
                );
              })()}
            </span>
          </button>
          {open === t.table && (
            <div className="overflow-x-auto border-t border-[#DCE5F0]">
              <table className="w-full text-xs min-w-[500px]">
                <thead>
                  <tr>
                    <th className="th">Column</th>
                    <th className="th">Type</th>
                    <th className="th">Category</th>
                    <th className="th">Sensitivity</th>
                  </tr>
                </thead>
                <tbody>
                  {t.columns.map((c: any) => (
                    <tr key={c.name} className="hover:bg-[#F4F8FD]">
                      <td className="td mono font-semibold text-[#172B45]">
                        {c.name} {c.primary_key && <Badge tone="indigo">PK</Badge>}
                      </td>
                      <td className="td mono text-[#64748B]">{c.type}</td>
                      <td className="td text-xs font-medium text-[#172B45]">{c.classification?.category ?? <span className="text-rose-700">unclassified</span>}</td>
                      <td className="td">
                        <SensBadge label={c.classification?.sensitivity} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ConnectionsPage() {
  const qc = useQueryClient();
  const { connections, isLoading, select } = useConnections();
  const [adding, setAdding] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["connections"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
  const test = useMutation({
    mutationFn: (id: string) => api<Conn>(`/api/databases/${id}/test`, { method: "POST" }),
    onSuccess: (c) => {
      setMsg({ tone: c.status === "healthy" ? "success" : "error", text: `${c.name}: ${c.status_detail}` });
      refresh();
    },
    onError: (e: Error) => setMsg({ tone: "error", text: e.message }),
  });
  const scan = useMutation({
    mutationFn: (id: string) => api(`/api/databases/${id}/scan`, { body: { sample_size: 100 } }),
    onSuccess: (r: any) => {
      setMsg({ tone: r.status === "completed" ? "success" : "error", text: r.status === "completed" ? `Scan completed: ${r.tables_scanned} tables, ${r.columns_scanned} columns, ${r.sensitive_found} sensitive.` : `Scan failed: ${r.error}` });
      refresh();
      qc.invalidateQueries({ queryKey: ["schema"] });
      qc.invalidateQueries({ queryKey: ["classifications"] });
    },
    onError: (e: Error) => setMsg({ tone: "error", text: e.message }),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/api/databases/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setMsg({ tone: "success", text: "Connection removed (its classifications and grants were deleted)." });
      refresh();
    },
  });

  return (
    <div>
      <PageHeader
        title="Database Connections"
        description="Register and manage external SQLite, PostgreSQL, and MySQL data sources with health checks and automated schema introspection."
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add connection
          </Button>
        }
      />
      {msg && (
        <div className="mb-4">
          <Alert tone={msg.tone}>{msg.text}</Alert>
        </div>
      )}
      {isLoading ? (
        <Spinner />
      ) : connections.length === 0 ? (
        <Empty icon={<Database className="h-8 w-8 text-[#1D5FA7]" />} title="No connections" action={<Button onClick={() => setAdding(true)}>Add connection</Button>}>
          Register SQLite, MySQL or PostgreSQL to begin discovery.
        </Empty>
      ) : (
        <div className="space-y-4">
          {connections.map((c) => (
            <Card
              key={c.id}
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <Database className="h-4 w-4 text-[#1D5FA7]" /> {c.name}
                  <Badge tone={c.kind === "sqlite" ? "cyan" : c.kind === "mysql" ? "amber" : "indigo"}>{KIND_LABEL[c.kind] ?? c.kind}</Badge>
                  <Badge tone={c.status === "healthy" ? "green" : c.status === "unhealthy" ? "red" : "neutral"}>{c.status}</Badge>
                </span>
              }
              subtitle={
                c.kind === "sqlite"
                  ? `file: ${c.params.file}`
                  : `${c.params.username}@${c.params.host}:${c.params.port}/${c.params.database} · schemas: ${c.allowed_schemas.join(", ")} · password ${c.has_password ? "stored (encrypted)" : "none"}`
              }
              actions={
                <div className="flex flex-wrap items-center gap-1.5">
                  <Button size="sm" icon={<Plug className="h-3.5 w-3.5" />} loading={test.isPending && test.variables === c.id} onClick={() => test.mutate(c.id)}>
                    Test
                  </Button>
                  <Button size="sm" icon={<Radar className="h-3.5 w-3.5" />} loading={scan.isPending && scan.variables === c.id} onClick={() => scan.mutate(c.id)}>
                    Scan for PII
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { select(c.id); setExpanded(expanded === c.id ? null : c.id); }}>
                    {expanded === c.id ? "Hide schema" : "Inspect schema"}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    onClick={() => confirm(`Remove "${c.name}"? Its classifications and grants are deleted; the database itself is not touched.`) && del.mutate(c.id)}
                  >
                    Remove
                  </Button>
                </div>
              }
            >
              <div className="flex flex-wrap gap-x-8 gap-y-1 text-xs text-[#64748B]">
                <span>Tables classified: <b className="text-[#172B45] font-semibold">{c.tables_classified}</b></span>
                <span>Last test: {fmtTime(c.last_tested_at)}</span>
                <span>Last scan: {c.last_scan ? `${c.last_scan.status} · ${fmtTime(c.last_scan.finished_at)}` : "never"}</span>
                {c.status === "unhealthy" && <span className="text-rose-700 font-medium">{c.status_detail}</span>}
              </div>
              {expanded === c.id && (
                <div className="mt-4">
                  <SchemaView conn={c} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      <AddConnection open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}
