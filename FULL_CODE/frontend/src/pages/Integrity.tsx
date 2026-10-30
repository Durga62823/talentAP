import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Fingerprint, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Empty, ErrorText, PageHeader, Spinner } from "../components/ui";
import { RoleChip } from "../components/Layout";
import { api, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

function Hash({ h }: { h: string }) {
  return <span className="break-all font-mono text-[11.5px] text-fog-300">{h}</span>;
}

function RunView({ run }: { run: any }) {
  return (
    <div className="space-y-4">
      <div className={`flex items-center gap-3 rounded-xl border p-4 ${run.match ? "border-emerald-400/30 bg-emerald-400/5" : "border-rose-400/30 bg-rose-500/5"}`}>
        {run.match ? <CheckCircle2 className="h-8 w-8 text-emerald-400" /> : <XCircle className="h-8 w-8 text-rose-400" />}
        <div>
          <div className="font-semibold">{run.match ? "Source records unchanged" : "Fingerprint mismatch — source data changed during the run"}</div>
          <div className="text-xs text-fog-400">{run.tables.length} tables · {run.rows_covered.toLocaleString()} rows verified · {fmtTime(run.created_at)}</div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-ink-700 p-3"><div className="label">Before (SHA-256)</div><Hash h={run.before_fingerprint} /></div>
        <div className="rounded-lg border border-ink-700 p-3"><div className="label">After (SHA-256)</div><Hash h={run.after_fingerprint} /></div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="label">Per-table fingerprints</div>
          <table className="w-full"><thead><tr><th className="th">Table</th><th className="th">Before → after</th><th className="th">Match</th></tr></thead>
            <tbody>{Object.entries(run.table_fingerprints).map(([t, v]: [string, any]) => (
              <tr key={t}><td className="td mono">{t}</td><td className="td"><Hash h={`${v.before.slice(0, 16)}… → ${v.after.slice(0, 16)}…`} /></td><td className="td">{v.match ? <Badge tone="green">match</Badge> : <Badge tone="red">changed</Badge>}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div>
          <div className="label">Protected queries executed between fingerprints</div>
          <table className="w-full"><thead><tr><th className="th">Role</th><th className="th">Query</th><th className="th">Rows</th><th className="th">Masked columns</th></tr></thead>
            <tbody>{run.queries_executed.map((x: any, i: number) => (
              <tr key={i}>
                <td className="td"><RoleChip role={x.role} /></td>
                <td className="td mono text-xs">SELECT * FROM {x.table}</td>
                <td className="td tabular-nums">{x.ok ? x.rows : <Badge tone="red">denied</Badge>}</td>
                <td className="td text-xs text-fog-400">{x.masked_columns.length} {x.audit_event_id && <Link className="ml-1 text-[#A8ADFF] hover:underline" to={`/audit?event=${x.audit_event_id}`}>audit</Link>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function IntegrityPage() {
  const qc = useQueryClient();
  const { selected } = useConnections();
  const runs = useQuery({ queryKey: ["integrity-runs"], queryFn: () => api<any[]>("/api/integrity/runs") });
  const schema = useQuery({ queryKey: ["grants", selected?.id], queryFn: () => api(`/api/grants?connection_id=${selected!.id}`), enabled: !!selected });
  const [tables, setTables] = useState<string[]>([]);
  useEffect(() => { setTables([]); }, [selected?.id]);
  const verify = useMutation({
    mutationFn: () => api("/api/integrity/verify", { body: { connection_id: selected!.id, tables: tables.length ? tables : null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["integrity-runs"] }); qc.invalidateQueries({ queryKey: ["overview"] }); },
  });
  const latest = verify.data ?? runs.data?.[0];

  return (
    <div>
      <PageHeader
        title="Integrity Verification"

      />
      <Card title="Run verification">
        <div className="flex flex-wrap items-center gap-2">
          {schema.data?.tables.map((t: string) => (
            <label key={t} className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${tables.includes(t) ? "border-accent bg-accent/10" : "border-ink-600 text-fog-300"}`}>
              <input type="checkbox" className="sr-only" checked={tables.includes(t)} onChange={() => setTables(tables.includes(t) ? tables.filter((x) => x !== t) : [...tables, t])} />
              {t}
            </label>
          ))}
          <span className="text-xs text-fog-500">{tables.length ? `${tables.length} selected` : "all tables"}</span>
          <Button className="ml-auto" variant="primary" icon={<Fingerprint className="h-4 w-4" />} loading={verify.isPending} onClick={() => verify.mutate()} disabled={!selected}>Verify now</Button>
        </div>
        <ErrorText error={verify.error} />
      </Card>
      <div className="mt-4">
        {runs.isLoading ? <Spinner /> : latest ? <Card title="Latest result"><RunView run={latest} /></Card> : <Empty icon={<Fingerprint className="h-8 w-8" />} title="No verification has run yet">Results appear only after a comparison actually executes.</Empty>}
      </div>
      {!!runs.data?.length && (
        <Card className="mt-4" title="History">
          <table className="w-full"><thead><tr><th className="th">When</th><th className="th">Database</th><th className="th">Tables</th><th className="th">Rows</th><th className="th">Fingerprint</th><th className="th">Outcome</th></tr></thead>
            <tbody>{runs.data.map((r) => (
              <tr key={r.id}><td className="td text-xs text-fog-400">{fmtTime(r.created_at)}</td><td className="td">{r.connection_name}</td><td className="td text-xs">{r.tables.join(", ")}</td><td className="td tabular-nums">{r.rows_covered.toLocaleString()}</td><td className="td"><Hash h={r.after_fingerprint.slice(0, 24) + "…"} /></td><td className="td">{r.match ? <Badge tone="green">unchanged</Badge> : <Badge tone="red">mismatch</Badge>}</td></tr>
            ))}</tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
