import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Fingerprint, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Empty, ErrorText, PageHeader, Spinner } from "../components/ui";
import { RoleChip } from "../components/Layout";
import { api, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

function Hash({ h }: { h: string }) {
  return <span className="break-all font-mono text-[11.5px] text-[#123B67]">{h}</span>;
}

function RunView({ run }: { run: any }) {
  return (
    <div className="space-y-4">
      <div className={`flex items-center gap-3 rounded-xl border p-4 ${run.match ? "border-emerald-200 bg-emerald-50/70" : "border-rose-200 bg-rose-50/70"}`}>
        {run.match ? <CheckCircle2 className="h-8 w-8 text-emerald-600 shrink-0" /> : <XCircle className="h-8 w-8 text-rose-600 shrink-0" />}
        <div>
          <div className="font-bold text-[#172B45]">{run.match ? "Source records unchanged" : "Fingerprint mismatch — source data changed during the run"}</div>
          <div className="text-xs text-[#64748B]">{run.tables.length} tables · {run.rows_covered.toLocaleString()} rows verified · {fmtTime(run.created_at)}</div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3"><div className="label">Before (SHA-256)</div><Hash h={run.before_fingerprint} /></div>
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3"><div className="label">After (SHA-256)</div><Hash h={run.after_fingerprint} /></div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-x-auto rounded-lg border border-[#DCE5F0]">
          <div className="label p-2.5 bg-[#F4F8FD] border-b border-[#DCE5F0] mb-0">Per-table fingerprints</div>
          <table className="w-full text-xs min-w-[340px]">
            <thead><tr><th className="th">Table</th><th className="th">Before → after</th><th className="th">Match</th></tr></thead>
            <tbody>{Object.entries(run.table_fingerprints).map(([t, v]: [string, any]) => (
              <tr key={t} className="hover:bg-[#F4F8FD]"><td className="td mono font-semibold text-[#172B45]">{t}</td><td className="td"><Hash h={`${v.before.slice(0, 16)}… → ${v.after.slice(0, 16)}…`} /></td><td className="td">{v.match ? <Badge tone="green">match</Badge> : <Badge tone="red">changed</Badge>}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className="overflow-x-auto rounded-lg border border-[#DCE5F0]">
          <div className="label p-2.5 bg-[#F4F8FD] border-b border-[#DCE5F0] mb-0">Protected queries executed between fingerprints</div>
          <table className="w-full text-xs min-w-[340px]">
            <thead><tr><th className="th">Role</th><th className="th">Query</th><th className="th">Rows</th><th className="th">Masked columns</th></tr></thead>
            <tbody>{run.queries_executed.map((x: any, i: number) => (
              <tr key={i} className="hover:bg-[#F4F8FD]">
                <td className="td"><RoleChip role={x.role} /></td>
                <td className="td mono text-xs font-semibold text-[#172B45]">SELECT * FROM {x.table}</td>
                <td className="td tabular-nums text-[#172B45]">{x.ok ? x.rows : <Badge tone="red">denied</Badge>}</td>
                <td className="td text-xs text-[#64748B]">{x.masked_columns.length} {x.audit_event_id && <Link className="ml-1 text-[#1D5FA7] font-semibold hover:underline" to={`/admin/audit?event=${x.audit_event_id}`}>audit</Link>}</td>
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
        description="Verify cryptographic zero-modification guarantees by computing SHA-256 database fingerprints before and after protected queries."
      />
      <Card title="Run verification">
        <div className="flex flex-wrap items-center gap-2">
          {schema.data?.tables.map((t: string) => (
            <label key={t} className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-all ${tables.includes(t) ? "border-[#1D5FA7] bg-[#EAF2FB] text-[#123B67] shadow-sm" : "border-[#DCE5F0] bg-white text-[#172B45] hover:bg-[#F4F8FD]"}`}>
              <input type="checkbox" className="sr-only" checked={tables.includes(t)} onChange={() => setTables(tables.includes(t) ? tables.filter((x) => x !== t) : [...tables, t])} />
              {t}
            </label>
          ))}
          <span className="text-xs text-[#64748B] font-medium">{tables.length ? `${tables.length} selected` : "all tables"}</span>
          <Button className="ml-auto" variant="primary" icon={<Fingerprint className="h-4 w-4" />} loading={verify.isPending} onClick={() => verify.mutate()} disabled={!selected}>Verify now</Button>
        </div>
        <ErrorText error={verify.error} />
      </Card>
      <div className="mt-4">
        {runs.isLoading ? <Spinner /> : latest ? <Card title="Latest result"><RunView run={latest} /></Card> : <Empty icon={<Fingerprint className="h-8 w-8 text-[#1D5FA7]" />} title="No verification has run yet">Results appear only after a comparison actually executes.</Empty>}
      </div>
      {!!runs.data?.length && (
        <Card className="mt-4" title="Verification History">
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[700px]">
              <thead><tr><th className="th">When</th><th className="th">Database</th><th className="th">Tables</th><th className="th">Rows</th><th className="th">Fingerprint</th><th className="th">Outcome</th></tr></thead>
              <tbody>{runs.data.map((r) => (
                <tr key={r.id} className="hover:bg-[#F4F8FD]">
                  <td className="td text-xs text-[#64748B]">{fmtTime(r.created_at)}</td>
                  <td className="td font-medium text-[#172B45]">{r.connection_name}</td>
                  <td className="td text-xs text-[#64748B]">{r.tables.join(", ")}</td>
                  <td className="td tabular-nums text-[#172B45]">{r.rows_covered.toLocaleString()}</td>
                  <td className="td"><Hash h={r.after_fingerprint.slice(0, 24) + "…"} /></td>
                  <td className="td">{r.match ? <Badge tone="green">unchanged</Badge> : <Badge tone="red">mismatch</Badge>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
