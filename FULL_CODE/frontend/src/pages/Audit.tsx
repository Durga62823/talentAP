import { useQuery } from "@tanstack/react-query";
import { Download, Link2, ShieldCheck, ShieldX } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, Modal, OutcomeBadge, PageHeader, Spinner } from "../components/ui";
import { api, download, fmtTime } from "../lib/api";

function Detail({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["audit-event", id], queryFn: () => api(`/api/audit/${id}`) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;
  const e = q.data;
  const d = e.details ?? {};
  return (
    <div className="space-y-4 text-sm">
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-3">
        {[
          ["Event", <span className="font-mono text-xs">{e.id}</span>],
          ["Sequence", `#${e.seq}`],
          ["Timestamp", fmtTime(e.ts)],
          ["Actor", `${e.actor ?? "anonymous"}`],
          ["Effective role", e.role ?? "—"],
          ["Action", e.action],
          ["Outcome", <OutcomeBadge outcome={e.outcome} />],
          ["Database", e.connection_name ?? e.connection_id ?? "—"],
          ["Duration", e.duration_ms != null ? `${e.duration_ms} ms` : "—"],
          ["Correlation id", <span className="font-mono text-xs">{e.correlation_id ?? "—"}</span>],
        ].map(([k, v], i) => (
          <div key={i}><div className="label">{k}</div><div>{v}</div></div>
        ))}
      </div>
      {e.reason && <Alert tone={e.outcome === "success" ? "info" : "error"} title="Decision reason">{e.reason}</Alert>}
      {e.tables?.length > 0 && <div><div className="label">Tables</div><div className="flex flex-wrap gap-1">{e.tables.map((t: string) => <Badge key={t}>{t}</Badge>)}</div></div>}
      {e.columns?.length > 0 && <div><div className="label">Columns referenced</div><div className="flex flex-wrap gap-1">{e.columns.map((t: string) => <Badge key={t}>{t}</Badge>)}</div></div>}
      {d.statement && <div><div className="label">Statement (literals redacted)</div><pre className="overflow-x-auto rounded-lg border border-ink-700 bg-ink-950 p-3 font-mono text-xs text-fog-300">{d.statement}</pre></div>}
      {Array.isArray(d.decisions) && (
        <div>
          <div className="label">Masking decisions</div>
          <table className="w-full"><thead><tr><th className="th">Output</th><th className="th">Source</th><th className="th">Action</th><th className="th">Policy</th></tr></thead>
            <tbody>{d.decisions.map((x: any, i: number) => <tr key={i}><td className="td mono">{x.name}</td><td className="td mono text-fog-400">{x.source ?? "—"}</td><td className="td"><ActionBadge action={x.action} /></td><td className="td text-xs">{x.policy_id ? `#${x.policy_id}` : "default"}</td></tr>)}</tbody>
          </table>
        </div>
      )}
      <details>
        <summary className="cursor-pointer text-xs text-fog-400">Raw event metadata & hash chain</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded-lg border border-ink-700 bg-ink-950 p-3 font-mono text-[11px] text-fog-300">{JSON.stringify({ details: d, prev_hash: e.prev_hash, entry_hash: e.entry_hash }, null, 2)}</pre>
      </details>
    </div>
  );
}

export default function AuditPage() {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ actor: "", role: "", action: "", outcome: "", since: "", until: "" });
  const [page, setPage] = useState(0);
  const openId = params.get("event");
  const qs = new URLSearchParams(Object.entries({ ...f, since: f.since ? new Date(f.since).toISOString().slice(0, 19) : "", until: f.until ? new Date(f.until).toISOString().slice(0, 19) : "" }).filter(([, v]) => v) as [string, string][]);
  qs.set("limit", "50");
  qs.set("offset", String(page * 50));
  const q = useQuery({ queryKey: ["audit", qs.toString()], queryFn: () => api(`/api/audit?${qs}`) });
  const chain = useQuery({ queryKey: ["chain"], queryFn: () => api("/api/audit/verify-chain"), enabled: false });
  useEffect(() => setPage(0), [f]);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  return (
    <div>
      <PageHeader
        title="Security Audit"

        actions={
          <>
            <Button icon={<Link2 className="h-4 w-4" />} onClick={() => chain.refetch()} loading={chain.isFetching}>Verify hash chain</Button>
            <Button icon={<Download className="h-4 w-4" />} onClick={() => download(`/api/audit/export.csv?${new URLSearchParams(Object.entries(f).filter(([k, v]) => v && ["actor", "role", "action", "outcome"].includes(k)) as [string, string][])}`)}>Export CSV</Button>
          </>
        }
      />
      {chain.data && (
        <div className="mb-4">
          {chain.data.valid ? (
            <Alert tone="success" title={<span className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4" /> Hash chain intact</span>}>{chain.data.checked} events recomputed; every entry links to its predecessor.</Alert>
          ) : (
            <Alert tone="error" title={<span className="flex items-center gap-1.5"><ShieldX className="h-4 w-4" /> Chain broken</span>}>Tampering detected at sequence #{chain.data.broken_at_seq}.</Alert>
          )}
        </div>
      )}
      <Card>
        <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-6">
          <select className="input" value={f.actor} onChange={set("actor")} aria-label="Actor"><option value="">All actors</option>{q.data?.facets.actors.map((a: string) => <option key={a}>{a}</option>)}</select>
          <select className="input" value={f.role} onChange={set("role")} aria-label="Role"><option value="">All roles</option>{q.data?.facets.roles.map((a: string) => <option key={a}>{a}</option>)}</select>
          <select className="input" value={f.action} onChange={set("action")} aria-label="Action"><option value="">All actions</option>{q.data?.facets.actions.map((a: string) => <option key={a}>{a}</option>)}</select>
          <select className="input" value={f.outcome} onChange={set("outcome")} aria-label="Outcome"><option value="">All outcomes</option><option>success</option><option>denied</option><option>error</option></select>
          <input className="input" type="datetime-local" value={f.since} onChange={set("since")} aria-label="From" />
          <input className="input" type="datetime-local" value={f.until} onChange={set("until")} aria-label="Until" />
        </div>
        {q.isLoading ? <Spinner /> : q.error ? <ErrorText error={q.error} /> : !q.data.events.length ? <Empty title="No events match" /> : (
          <>
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead><tr><th className="th">#</th><th className="th">Time</th><th className="th">Actor</th><th className="th">Action</th><th className="th">Outcome</th><th className="th">Target</th><th className="th">Reason</th><th className="th">ms</th></tr></thead>
                <tbody>
                  {q.data.events.map((e: any) => (
                    <tr key={e.id} className="cursor-pointer hover:bg-ink-800/40" onClick={() => setParams({ event: e.id })}>
                      <td className="td tabular-nums text-fog-500">{e.seq}</td>
                      <td className="td whitespace-nowrap text-xs text-fog-400">{fmtTime(e.ts)}</td>
                      <td className="td text-[13px]">{e.actor ?? <span className="text-fog-500">anonymous</span>}{e.role && <span className="text-fog-500"> · {e.role}</span>}</td>
                      <td className="td mono">{e.action}</td>
                      <td className="td"><OutcomeBadge outcome={e.outcome} /></td>
                      <td className="td text-xs text-fog-400">{e.tables?.join(", ") || "—"}</td>
                      <td className="td max-w-[320px] truncate text-xs text-fog-400">{e.reason}</td>
                      <td className="td tabular-nums text-xs text-fog-500">{e.duration_ms ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-fog-400">
              <span>{q.data.total} events</span>
              <div className="flex gap-2">
                <Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" disabled={(page + 1) * 50 >= q.data.total} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          </>
        )}
      </Card>
      <Modal open={!!openId} onClose={() => setParams({})} title="Audit event detail" wide>{openId && <Detail id={openId} />}</Modal>
    </div>
  );
}
