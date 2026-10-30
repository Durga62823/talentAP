import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Check, Download, PencilLine, Radar, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, Modal, PageHeader, SensBadge, Spinner, Tabs } from "../components/ui";
import { api, download, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

type Cls = {
  id: number; schema: string; table: string; column: string; data_type: string; category: string; sensitivity: string;
  detected_category: string; detected_sensitivity: string; confidence: number; detection_method: string; evidence: string;
  sample_count: number; suggested_masking: string; review_status: string; reviewed_by: string | null; source: string; last_scanned_at: string;
  ai: AiInfo | null;
  ml: MlInfo | null;
};

type MlInfo = {
  status: "APPLIED" | "AGREES" | "KEPT_RULE" | "LOW_CONFIDENCE" | "HUMAN_REVIEWED" | "ML_UNAVAILABLE";
  detected_by: "RULE" | "ML" | "BOTH" | "NONE"; category: string | null; sensitivity: string | null; confidence: number | null;
  top: { category: string; probability: number }[]; reasons: { feature: string; evidence: string; impact: number }[];
  rule_category: string; rule_sensitivity: string; error: string; model_version: string; updated_at: string | null;
};

const ML_STATUS: Record<MlInfo["status"], { tone: string; label: string; hint: string }> = {
  APPLIED: { tone: "indigo", label: "ML upgraded", hint: "The ML model found this column more sensitive than the rules, with high calibrated confidence; its classification is now active." },
  AGREES: { tone: "green", label: "Agrees", hint: "ML model and rules agree." },
  KEPT_RULE: { tone: "neutral", label: "Rule kept", hint: "The ML model suggested the same or lower sensitivity; models never lower protection." },
  LOW_CONFIDENCE: { tone: "amber", label: "Review required", hint: "The ML model suggests more protection but below the confidence threshold, so it was not applied. Use Override to apply it manually." },
  HUMAN_REVIEWED: { tone: "neutral", label: "Human decision", hint: "A reviewer decided this column; models do not change human decisions." },
  ML_UNAVAILABLE: { tone: "red", label: "ML unavailable", hint: "No ML result; the rule-based classification is in force." },
};

type AiInfo = {
  status: "APPLIED" | "AGREES" | "KEPT_RULE" | "LOW_CONFIDENCE" | "HUMAN_REVIEWED" | "AI_UNAVAILABLE";
  detected_by: "RULE" | "AI" | "BOTH" | "NONE"; category: string | null; sensitivity: string | null; pii_type: string | null;
  identifier_kind: string | null; confidence: number | null; reason: string; needs_review: boolean; rule_category: string;
  rule_sensitivity: string; error_code: string; model: string; prompt_version: string; features: Record<string, any>; updated_at: string | null;
};

const AI_STATUS: Record<AiInfo["status"], { tone: string; label: string; hint: string }> = {
  APPLIED: { tone: "indigo", label: "AI upgraded", hint: "AI found this column more sensitive than the rules; its classification is now active." },
  AGREES: { tone: "green", label: "Agrees", hint: "AI and rules agree." },
  KEPT_RULE: { tone: "neutral", label: "Rule kept", hint: "AI suggested the same or lower sensitivity; protection is never lowered by AI." },
  LOW_CONFIDENCE: { tone: "amber", label: "Review required", hint: "AI suggests more protection but is unsure, so it was not applied. Use Override to apply it manually." },
  HUMAN_REVIEWED: { tone: "neutral", label: "Human decision", hint: "A reviewer decided this column; AI does not change human decisions." },
  AI_UNAVAILABLE: { tone: "red", label: "AI unavailable", hint: "No AI result; the rule-based classification is in force." },
};
const DETECTED: Record<string, string> = { BOTH: "Both detected", AI: "AI detected", RULE: "Rule detected", NONE: "" };

const REVIEW_TONE: Record<string, string> = { pending: "amber", approved: "green", rejected: "neutral", overridden: "indigo" };

function Confidence({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-[#EEF3F9]">
        <div className={`h-full rounded-full ${pct >= 85 ? "bg-emerald-600" : pct >= 65 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium tabular-nums text-[#64748B]">{pct}%</span>
    </div>
  );
}

export default function DiscoveryPage() {
  const qc = useQueryClient();
  const { selected } = useConnections();
  const [filter, setFilter] = useState<"sensitive" | "pending" | "ai" | "all">("sensitive");
  const [table, setTable] = useState("");
  const [editing, setEditing] = useState<Cls | null>(null);
  const [evidence, setEvidence] = useState<Cls | null>(null);
  const [useAi, setUseAi] = useState(true);
  const [useMl, setUseMl] = useState(true);
  const [mlEvidence, setMlEvidence] = useState<Cls | null>(null);
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
    mutationFn: () => api(`/api/databases/${selected!.id}/scan`, { body: { sample_size: 100, ai: useAi, ml: useMl } }),
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
    if (filter === "ai") r = r.filter((c) => (c.ml && (c.ml.status === "APPLIED" || c.ml.status === "LOW_CONFIDENCE" || c.ml.detected_by === "ML")) || c.ai && (c.ai.status === "APPLIED" || c.ai.status === "LOW_CONFIDENCE" || c.ai.detected_by === "AI" || (!!c.ai.category && c.ai.category !== c.ai.rule_category)));
    if (table) r = r.filter((c) => c.table === table);
    return r;
  }, [q.data, filter, table]);
  const tables = [...new Set((q.data ?? []).map((c) => c.table))];

  return (
    <div>
      <PageHeader
        title="PII Discovery"
        description="Automated PII detection via regular expressions, heuristic rules, local ML models, and LLM contextual verification."
        actions={
          <>
            <Button icon={<Download className="h-4 w-4" />} onClick={() => download("/api/classifications/export.csv")}>
              Export CSV
            </Button>
            <label className="flex items-center gap-1.5 text-xs font-medium text-[#172B45] cursor-pointer" title="Classify with the locally trained ML model">
              <input type="checkbox" checked={useMl} onChange={(e) => setUseMl(e.target.checked)} className="rounded text-[#1D5FA7]" />
              <BrainCircuit className="h-3.5 w-3.5 text-[#1D5FA7]" /> ML model
            </label>
            <label className="flex items-center gap-1.5 text-xs font-medium text-[#172B45] cursor-pointer" title="Send sanitized column statistics to Gemini">
              <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} className="rounded text-[#1D5FA7]" />
              <Sparkles className="h-3.5 w-3.5 text-[#1D5FA7]" /> Gemini AI
            </label>
            <Button variant="primary" icon={<Radar className="h-4 w-4" />} onClick={() => scan.mutate()} loading={scan.isPending} disabled={!selected}>
              {scan.isPending && useAi ? "Scanning with AI…" : `Scan ${selected?.name ?? ""}`}
            </Button>
          </>
        }
      />

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
          <div className="flex flex-wrap items-center gap-2">
            <select className="input h-8 w-auto py-0 text-xs" value={table} onChange={(e) => setTable(e.target.value)} aria-label="Filter table">
              <option value="">All tables</option>
              {tables.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <Tabs value={filter} onChange={setFilter} items={[{ value: "sensitive", label: "Detected" }, { value: "pending", label: "Pending review" }, { value: "ai", label: "ML / AI findings" }, { value: "all", label: "All columns" }]} />
          </div>
        }
      >
        {q.isLoading ? (
          <Spinner />
        ) : !rows.length ? (
          <Empty icon={<Radar className="h-8 w-8 text-[#1D5FA7]" />} title="Nothing to show" action={<Button onClick={() => scan.mutate()}>Run a scan</Button>}>
            No columns match this filter yet.
          </Empty>
        ) : (
          <div className="-mx-4 sm:-mx-5 -mb-4 sm:-mb-5 max-h-[640px] overflow-x-auto">
            <table className="w-full min-w-[1200px]">
              <thead>
                <tr>
                  <th className="th">Table.column</th>
                  <th className="th">Category</th>
                  <th className="th">Sensitivity</th>
                  <th className="th">Confidence</th>
                  <th className="th">Method & evidence</th>
                  <th className="th">ML model</th>
                  <th className="th">Gemini AI</th>
                  <th className="th">Suggested</th>
                  <th className="th">Review</th>
                  <th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="hover:bg-[#F4F8FD] transition-colors">
                    <td className="td">
                      <div className="mono font-semibold text-[#172B45]">{c.table}.<b>{c.column}</b></div>
                      <div className="text-[11px] text-[#64748B]">{c.data_type} · {c.source}</div>
                    </td>
                    <td className="td text-xs font-medium text-[#172B45]">
                      {c.category}
                      {c.category !== c.detected_category && <div className="text-[11px] text-[#64748B]">detected: {c.detected_category}</div>}
                    </td>
                    <td className="td"><SensBadge label={c.sensitivity} /></td>
                    <td className="td"><Confidence v={c.confidence} /></td>
                    <td className="td max-w-[340px] text-xs text-[#64748B]">
                      <div className="font-semibold text-[#172B45]">{c.detection_method}</div>
                      <div className="truncate">{c.evidence}</div>
                    </td>
                    <td className="td min-w-[170px]"><MlCell c={c} onOpen={() => setMlEvidence(c)} /></td>
                    <td className="td min-w-[180px]"><AiCell c={c} onOpen={() => setEvidence(c)} /></td>
                    <td className="td"><ActionBadge action={c.suggested_masking} /></td>
                    <td className="td">
                      <Badge tone={REVIEW_TONE[c.review_status]}>{c.review_status}</Badge>
                      {c.reviewed_by && <div className="mt-0.5 text-[11px] text-[#64748B]">by {c.reviewed_by}</div>}
                    </td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" title="Approve" aria-label="Approve" onClick={() => review.mutate({ id: c.id, body: { decision: "approve" } })}>
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Reject (not sensitive)" aria-label="Reject" onClick={() => review.mutate({ id: c.id, body: { decision: "reject" } })}>
                          <X className="h-3.5 w-3.5 text-rose-600" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Correct category / sensitivity" aria-label="Override" onClick={() => setEditing(c)}>
                          <PencilLine className="h-3.5 w-3.5 text-[#1D5FA7]" />
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
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
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
                  <tr key={s.id} className="hover:bg-[#F4F8FD] transition-colors">
                    <td className="td text-xs text-[#64748B]">{fmtTime(s.finished_at)}</td>
                    <td className="td font-medium text-[#172B45]">{s.connection_name}</td>
                    <td className="td"><Badge tone={s.status === "completed" ? "green" : "red"}>{s.status}</Badge> <span className="text-xs text-rose-600">{s.error}</span></td>
                    <td className="td tabular-nums text-[#172B45]">{s.tables_scanned}</td>
                    <td className="td tabular-nums text-[#172B45]">{s.columns_scanned}</td>
                    <td className="td tabular-nums text-[#172B45]">{s.sensitive_found}</td>
                    <td className="td tabular-nums text-[#64748B]">≤ {s.sample_size} rows/table</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No scans yet" />
        )}
      </Card>

      <Modal open={!!mlEvidence} onClose={() => setMlEvidence(null)} title={`ML evidence · ${mlEvidence?.table}.${mlEvidence?.column}`}>
        {mlEvidence?.ml && <MlEvidence c={mlEvidence} />}
      </Modal>

      <Modal open={!!evidence} onClose={() => setEvidence(null)} title={`AI evidence · ${evidence?.table}.${evidence?.column}`}>
        {evidence?.ai && <AiEvidence c={evidence} />}
      </Modal>

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
      <p className="text-xs text-[#64748B]">Overrides are persisted, audited, and respected by later scans. Masking policies match on the effective category and label.</p>
      <ErrorText error={error} />
      <div className="flex justify-end">
        <Button variant="primary" loading={busy} onClick={() => onSave({ decision: "override", category, sensitivity })}>Save override</Button>
      </div>
    </div>
  );
}

function AiCell({ c, onOpen }: { c: Cls; onOpen: () => void }) {
  const a = c.ai;
  if (!a) return <span className="text-xs text-[#64748B]">not scanned with AI</span>;
  const st = AI_STATUS[a.status];
  return (
    <button type="button" onClick={onOpen} className="w-full text-left" title={st.hint}>
      <div className="flex flex-wrap items-center gap-1">
        <Badge tone={st.tone}>{st.label}</Badge>
        {DETECTED[a.detected_by] && <Badge tone="neutral">{DETECTED[a.detected_by]}</Badge>}
      </div>
      {a.category && (
        <div className="mt-1 text-xs text-[#172B45] font-medium">
          {a.category} <span className="text-[#64748B]">· {Math.round((a.confidence ?? 0) * 100)}% est.</span>
        </div>
      )}
      <div className="text-[11px] font-semibold text-[#1D5FA7] underline-offset-2 hover:underline">View evidence</div>
    </button>
  );
}

function AiEvidence({ c }: { c: Cls }) {
  const a = c.ai!;
  const st = AI_STATUS[a.status];
  const feats = Object.entries(a.features ?? {}).filter(([k]) => k !== "rule_engine");
  return (
    <div className="space-y-3.5 text-sm text-[#172B45]">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
          <div className="text-xs font-medium text-[#64748B]">Rule-based engine</div>
          <div className="mt-1 font-semibold text-[#172B45]">{a.rule_category || c.detected_category}</div>
          <div className="mt-1"><SensBadge label={a.rule_sensitivity || c.detected_sensitivity} /></div>
        </div>
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
          <div className="text-xs font-medium text-[#64748B]">Gemini AI</div>
          {a.category ? (
            <>
              <div className="mt-1 font-semibold text-[#172B45]">{a.category} {a.pii_type && a.pii_type !== "NONE" && <span className="text-xs text-[#64748B]">({a.pii_type})</span>}</div>
              <div className="mt-1"><SensBadge label={a.sensitivity ?? ""} /></div>
            </>
          ) : (
            <div className="mt-1 text-rose-700">No result ({a.error_code ? a.error_code.replace(/_/g, " ") : "unavailable"})</div>
          )}
        </div>
      </div>
      <Alert tone={a.status === "APPLIED" ? "success" : a.status === "AI_UNAVAILABLE" ? "error" : "info"} title={st.label}>{st.hint}</Alert>
      {a.category && (
        <div className="space-y-1.5 text-xs">
          <div><span className="font-semibold text-[#64748B]">Reason:</span> <span className="text-[#172B45]">{a.reason}</span></div>
          <div>
            <span className="font-semibold text-[#64748B]">Confidence:</span> <span className="font-bold text-[#172B45]">{Math.round((a.confidence ?? 0) * 100)}%</span>{" "}
            <span className="text-[#64748B]">(the model's estimate)</span>
          </div>
          <div><span className="font-semibold text-[#64748B]">Identifier kind:</span> <span className="text-[#172B45]">{a.identifier_kind}</span>{a.needs_review && <Badge tone="amber" className="ml-2">model asked for review</Badge>}</div>
        </div>
      )}
      <div>
        <div className="mb-1 text-xs font-semibold text-[#172B45]">{a.category ? "Sanitized features sent to model" : "Sanitized features prepared for model"} · no raw values</div>
        <div className="max-h-56 overflow-auto rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-2.5 font-mono text-[11px] text-[#172B45]">
          {feats.length ? feats.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 py-0.5 border-b border-[#DCE5F0]/50"><span className="text-[#64748B]">{k}</span><span className="font-medium">{String(v)}</span></div>
          )) : <span className="text-[#64748B]">No features (column could not be summarised safely).</span>}
        </div>
      </div>
      <div className="text-[11px] text-[#64748B]">Model {a.model} · prompt {a.prompt_version} · {a.updated_at ? fmtTime(a.updated_at) : ""}</div>
    </div>
  );
}

function MlCell({ c, onOpen }: { c: Cls; onOpen: () => void }) {
  const m = c.ml;
  if (!m) return <span className="text-xs text-[#64748B]">not scanned with ML</span>;
  const st = ML_STATUS[m.status];
  return (
    <button type="button" onClick={onOpen} className="w-full text-left" title={st.hint}>
      <div className="flex flex-wrap items-center gap-1">
        <Badge tone={st.tone}>{st.label}</Badge>
        {m.detected_by === "ML" && <Badge tone="neutral">ML detected</Badge>}
      </div>
      {m.category && (
        <div className="mt-1 text-xs text-[#172B45] font-medium">
          {m.category} <span className="text-[#64748B]">· {Math.round((m.confidence ?? 0) * 100)}%</span>
        </div>
      )}
      <div className="text-[11px] font-semibold text-[#1D5FA7] underline-offset-2 hover:underline">Why?</div>
    </button>
  );
}

function MlEvidence({ c }: { c: Cls }) {
  const m = c.ml!;
  const st = ML_STATUS[m.status];
  return (
    <div className="space-y-3.5 text-sm text-[#172B45]">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
          <div className="text-xs font-medium text-[#64748B]">Rule-based engine</div>
          <div className="mt-1 font-semibold text-[#172B45]">{m.rule_category || c.detected_category}</div>
          <div className="mt-1"><SensBadge label={m.rule_sensitivity || c.detected_sensitivity} /></div>
        </div>
        <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
          <div className="text-xs font-medium text-[#64748B]">ML model {m.model_version && `(${m.model_version})`}</div>
          {m.category ? (
            <>
              <div className="mt-1 font-semibold text-[#172B45]">{m.category}</div>
              <div className="mt-1"><SensBadge label={m.sensitivity ?? ""} /></div>
            </>
          ) : (
            <div className="mt-1 text-rose-700">No result: {m.error || "unavailable"}</div>
          )}
        </div>
      </div>
      <Alert tone={m.status === "APPLIED" ? "success" : m.status === "ML_UNAVAILABLE" ? "error" : "info"} title={st.label}>{st.hint}</Alert>
      {m.category && (
        <>
          <div>
            <div className="mb-1 text-xs font-semibold text-[#172B45]">Top predictions (calibrated probability)</div>
            {m.top.map((t) => (
              <div key={t.category} className="flex items-center gap-2 text-xs py-0.5">
                <span className="w-36 font-mono font-medium text-[#172B45]">{t.category}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#EEF3F9]"><div className="h-full rounded-full bg-[#1D5FA7]" style={{ width: `${t.probability * 100}%` }} /></div>
                <span className="w-10 text-right tabular-nums text-[#64748B] font-medium">{Math.round(t.probability * 100)}%</span>
              </div>
            ))}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-[#172B45]">Why: evidence that most supports "{m.category}"</div>
            {m.reasons.length ? (
              <ul className="space-y-1 text-xs">
                {m.reasons.map((r) => (
                  <li key={r.feature} className="flex justify-between gap-3 border-b border-[#DCE5F0]/50 py-0.5">
                    <span className="text-[#172B45]">{r.evidence}</span>
                    <span className="tabular-nums font-semibold text-emerald-700">+{Math.round(r.impact * 100)} pts</span>
                  </li>
                ))}
              </ul>
            ) : <div className="text-xs text-[#64748B]">No single feature dominates; the prediction comes from many weak signals.</div>}
            <div className="mt-1 text-[11px] text-[#64748B]">Impact = how much the probability drops when that signal is reset to a typical value.</div>
          </div>
        </>
      )}
      <div className="text-[11px] text-[#64748B]">Runs locally on this server; no raw data is sent externally. {m.updated_at ? fmtTime(m.updated_at) : ""}</div>
    </div>
  );
}
