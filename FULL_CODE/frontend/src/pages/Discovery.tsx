import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, PencilLine, Radar, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, Modal, PageHeader, SensBadge, Spinner, Tabs } from "../components/ui";
import { api, download, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

type Cls = {
  id: number; schema: string; table: string; column: string; data_type: string; category: string; sensitivity: string;
  detected_category: string; detected_sensitivity: string; confidence: number; detection_method: string; evidence: string;
  sample_count: number; suggested_masking: string; review_status: string; reviewed_by: string | null; source: string; last_scanned_at: string;
};

const REVIEW_TONE: Record<string, string> = { pending: "amber", approved: "green", rejected: "neutral", overridden: "indigo" };

function Confidence({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-ink-700">
        <div className={`h-full rounded-full ${pct >= 85 ? "bg-emerald-400" : pct >= 65 ? "bg-amber-400" : "bg-rose-400"}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-fog-400">{pct}%</span>
    </div>
  );
}

export default function DiscoveryPage() {
  const qc = useQueryClient();
  const { selected } = useConnections();
  const [filter, setFilter] = useState<"sensitive" | "pending" | "all">("sensitive");
  const [table, setTable] = useState("");
  const [editing, setEditing] = useState<Cls | null>(null);
  const meta = useQuery({ queryKey: ["cls-meta"], queryFn: () => api("/api/classifications/meta"), staleTime: Infinity });
  const q = useQuery({
    queryKey: ["classifications", selected?.id],
    queryFn: () => api<Cls[]>(`/api/classifications?connection_id=${selected!.id}`),
    enabled: !!selected,
  });
  const scans = useQuery({ queryKey: ["scans"], queryFn: () => api("/api/scans?limit=10") });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["classifications"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
  const scan = useMutation({
    mutationFn: () => api(`/api/databases/${selected!.id}/scan`, { body: { sample_size: 100 } }),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["connections"] });
    },
  });
  const review = useMutation({
    mutationFn: ({ id, body }: { id: number; body: any }) => api(`/api/classifications/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
  });

  const rows = useMemo(() => {
    let r = q.data ?? [];
    if (filter === "sensitive") r = r.filter((c) => ["PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL"].includes(c.sensitivity) || c.category !== "NONE");
    if (filter === "pending") r = r.filter((c) => c.review_status === "pending" && c.category !== "NONE");
    if (table) r = r.filter((c) => c.table === table);
    return r;
  }, [q.data, filter, table]);
  const tables = [...new Set((q.data ?? []).map((c) => c.table))];

  return (
    <div>
      <PageHeader
        title="PII Discovery"
        description="Column-name heuristics, data types, validated value patterns (Luhn, Verhoeff, IBAN mod-97, SSN rules) and pattern frequency over bounded samples. Raw samples are never stored or displayed."
        actions={
          <>
            <Button icon={<Download className="h-4 w-4" />} onClick={() => download("/api/classifications/export.csv")}>
              Export CSV
            </Button>
            <Button variant="primary" icon={<Radar className="h-4 w-4" />} onClick={() => scan.mutate()} loading={scan.isPending} disabled={!selected}>
              Scan {selected?.name ?? ""}
            </Button>
          </>
        }
      />
      <div className="mb-4">
        <Alert tone="info" title="Automated classification is heuristic">
          It cannot guarantee every sensitive field is found. Review results below; approvals and overrides persist and survive rescans. Tables never scanned are not queryable (fail closed).
        </Alert>
      </div>
      {scan.data && (
        <div className="mb-4">
          <Alert tone={(scan.data as any).status === "completed" ? "success" : "error"}>
            Scan {(scan.data as any).status}: {(scan.data as any).tables_scanned} tables, {(scan.data as any).columns_scanned} columns, {(scan.data as any).sensitive_found} sensitive.
          </Alert>
        </div>
      )}
      <ErrorText error={scan.error} />

      <Card
        title="Classifications"
        subtitle={selected ? `${selected.name} · ${rows.length} columns shown` : "Select a database"}
        actions={
          <>
            <select className="input h-8 w-auto py-0 text-xs" value={table} onChange={(e) => setTable(e.target.value)} aria-label="Filter table">
              <option value="">All tables</option>
              {tables.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <Tabs value={filter} onChange={setFilter} items={[{ value: "sensitive", label: "Detected" }, { value: "pending", label: "Pending review" }, { value: "all", label: "All columns" }]} />
          </>
        }
      >
        {q.isLoading ? (
          <Spinner />
        ) : !rows.length ? (
          <Empty icon={<Radar className="h-8 w-8" />} title="Nothing to show" action={<Button onClick={() => scan.mutate()}>Run a scan</Button>}>
            No columns match this filter yet.
          </Empty>
        ) : (
          <div className="-mx-5 -mb-5 max-h-[640px] overflow-auto">
            <table className="w-full min-w-[1100px]">
              <thead>
                <tr>
                  <th className="th">Table.column</th>
                  <th className="th">Category</th>
                  <th className="th">Sensitivity</th>
                  <th className="th">Confidence</th>
                  <th className="th">Method & evidence (no raw values)</th>
                  <th className="th">Suggested</th>
                  <th className="th">Review</th>
                  <th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="hover:bg-ink-800/40">
                    <td className="td">
                      <div className="mono">{c.table}.<b className="font-semibold text-fog-100">{c.column}</b></div>
                      <div className="text-[11px] text-fog-500">{c.data_type} · {c.source}</div>
                    </td>
                    <td className="td text-xs">
                      {c.category}
                      {c.category !== c.detected_category && <div className="text-[11px] text-fog-500">detected: {c.detected_category}</div>}
                    </td>
                    <td className="td"><SensBadge label={c.sensitivity} /></td>
                    <td className="td"><Confidence v={c.confidence} /></td>
                    <td className="td max-w-[340px] text-xs text-fog-400">
                      <div className="text-fog-300">{c.detection_method}</div>
                      <div>{c.evidence}</div>
                    </td>
                    <td className="td"><ActionBadge action={c.suggested_masking} /></td>
                    <td className="td">
                      <Badge tone={REVIEW_TONE[c.review_status]}>{c.review_status}</Badge>
                      {c.reviewed_by && <div className="mt-0.5 text-[11px] text-fog-500">by {c.reviewed_by}</div>}
                    </td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" title="Approve" aria-label="Approve" onClick={() => review.mutate({ id: c.id, body: { decision: "approve" } })}>
                          <Check className="h-3.5 w-3.5 text-emerald-300" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Reject (not sensitive)" aria-label="Reject" onClick={() => review.mutate({ id: c.id, body: { decision: "reject" } })}>
                          <X className="h-3.5 w-3.5 text-rose-300" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Correct category / sensitivity" aria-label="Override" onClick={() => setEditing(c)}>
                          <PencilLine className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Scan history" className="mt-4">
        {scans.data?.length ? (
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Finished</th>
                <th className="th">Database</th>
                <th className="th">Status</th>
                <th className="th">Tables</th>
                <th className="th">Columns</th>
                <th className="th">Sensitive</th>
                <th className="th">Sample size</th>
              </tr>
            </thead>
            <tbody>
              {scans.data.map((s: any) => (
                <tr key={s.id}>
                  <td className="td text-xs text-fog-400">{fmtTime(s.finished_at)}</td>
                  <td className="td">{s.connection_name}</td>
                  <td className="td"><Badge tone={s.status === "completed" ? "green" : "red"}>{s.status}</Badge> <span className="text-xs text-rose-300">{s.error}</span></td>
                  <td className="td tabular-nums">{s.tables_scanned}</td>
                  <td className="td tabular-nums">{s.columns_scanned}</td>
                  <td className="td tabular-nums">{s.sensitive_found}</td>
                  <td className="td tabular-nums text-fog-400">≤ {s.sample_size} rows/table</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title="No scans yet" />
        )}
      </Card>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Override ${editing?.table}.${editing?.column}`}>
        {editing && meta.data && <OverrideForm c={editing} meta={meta.data} busy={review.isPending} error={review.error} onSave={(body) => review.mutate({ id: editing.id, body })} />}
      </Modal>
    </div>
  );
}

function OverrideForm({ c, meta, onSave, busy, error }: { c: Cls; meta: any; onSave: (b: any) => void; busy: boolean; error: unknown }) {
  const [category, setCategory] = useState(c.category);
  const [sensitivity, setSensitivity] = useState(c.sensitivity);
  return (
    <div className="space-y-3">
      <div>
        <label className="label">Category</label>
        <select className="input" value={category} onChange={(e) => { setCategory(e.target.value); setSensitivity(meta.default_sensitivity[e.target.value]); }}>
          {meta.categories.map((x: string) => <option key={x}>{x}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Sensitivity label</label>
        <select className="input" value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
          {meta.labels.map((x: string) => <option key={x}>{x}</option>)}
        </select>
      </div>
      <p className="text-xs text-fog-400">Overrides are persisted, audited, and respected by later scans. Masking policies match on the effective category and label.</p>
      <ErrorText error={error} />
      <div className="flex justify-end">
        <Button variant="primary" loading={busy} onClick={() => onSave({ decision: "override", category, sensitivity })}>Save override</Button>
      </div>
    </div>
  );
}
