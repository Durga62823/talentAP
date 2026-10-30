import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, History, Plus, Power } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionBadge, Badge, Button, Card, ErrorText, Modal, PageHeader, Spinner, Tabs, Value } from "../components/ui";
import { RoleChip } from "../components/Layout";
import { api, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

type Policy = {
  id: number; name: string; role: string; action: string; connection_id: string | null; schema_name: string | null; table_name: string | null;
  column_name: string | null; category: string | null; sensitivity: string | null; priority: number; active: boolean; version: number;
  description: string; specificity: number; updated_by: string | null; updated_at: string;
};

function Scope({ p }: { p: Policy }) {
  const parts = [];
  if (p.table_name) parts.push(<span key="t" className="font-mono">{p.table_name}{p.column_name ? `.${p.column_name}` : ".*"}</span>);
  if (p.category) parts.push(<Badge key="c" tone="neutral">category {p.category}</Badge>);
  if (p.sensitivity) parts.push(<Badge key="s" tone="neutral">label {p.sensitivity}</Badge>);
  if (p.connection_id) parts.push(<Badge key="db" tone="indigo">one database</Badge>);
  return <div className="flex flex-wrap items-center gap-1.5 text-xs">{parts}</div>;
}

function Preview({ meta }: { meta: any }) {
  const [category, setCategory] = useState("CREDIT_CARD");
  const [action, setAction] = useState("PARTIAL");
  const [custom, setCustom] = useState("");
  const m = useMutation({ mutationFn: () => api("/api/policies/preview", { body: { category, action, values: custom.trim() ? custom.split("\n").slice(0, 20) : undefined } }) });
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="label">Category</label>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>{meta.categories.map((c: string) => <option key={c}>{c}</option>)}</select>
        </div>
        <div>
          <label className="label">Transformation</label>
          <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>{Object.keys(meta.actions).map((a) => <option key={a}>{a}</option>)}</select>
        </div>
      </div>
      <div>
        <label className="label">Synthetic inputs (optional, one per line)</label>
        <textarea className="input font-mono" rows={3} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Leave empty to use built-in synthetic samples" />
      </div>
      <Button size="sm" variant="primary" onClick={() => m.mutate()} loading={m.isPending}>Preview</Button>
      <p className="text-[11px] text-fog-500">{meta.actions[action]}</p>
      {m.data && (
        <table className="w-full">
          <thead><tr><th className="th">Input</th><th className="th">Output</th></tr></thead>
          <tbody>{m.data.results.map((r: any, i: number) => <tr key={i}><td className="td mono text-fog-400">{r.input}</td><td className="td mono"><Value v={r.output} /></td></tr>)}</tbody>
        </table>
      )}
    </div>
  );
}

function PolicyForm({ meta, onClose, initial }: { meta: any; onClose: () => void; initial?: Policy }) {
  const qc = useQueryClient();
  const { connections, selected } = useConnections();
  const [f, setF] = useState({
    name: initial?.name ?? "", role: initial?.role ?? "support", action: initial?.action ?? "PARTIAL", connection_id: initial?.connection_id ?? "",
    table_name: initial?.table_name ?? "", column_name: initial?.column_name ?? "", category: initial?.category ?? "", sensitivity: initial?.sensitivity ?? "",
    priority: initial?.priority ?? 0, description: initial?.description ?? "",
  });
  const body = { ...f, priority: Number(f.priority), connection_id: f.connection_id || null, table_name: f.table_name || null, column_name: f.column_name || null, category: f.category || null, sensitivity: f.sensitivity || null };
  const save = useMutation({
    mutationFn: () => (initial ? api(`/api/policies/${initial.id}`, { method: "PATCH", body: { name: f.name, action: f.action, priority: Number(f.priority), description: f.description } }) : api("/api/policies", { body })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["policies"] }); qc.invalidateQueries({ queryKey: ["overview"] }); onClose(); },
  });
  const sim = useMutation({ mutationFn: () => api("/api/policies/simulate", { body: { connection_id: selected?.id, proposed: body } }) });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const locked = !!initial;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2"><label className="label">Name</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">Role</label>
          <select className="input" value={f.role} onChange={set("role")} disabled={locked}>{["admin", "support", "analyst", "compliance"].map((r) => <option key={r}>{r}</option>)}</select></div>
        <div><label className="label">Transformation</label>
          <select className="input" value={f.action} onChange={set("action")}>{Object.keys(meta.actions).map((a) => <option key={a}>{a}</option>)}</select></div>
        <div><label className="label">Database (empty = any)</label>
          <select className="input" value={f.connection_id} onChange={set("connection_id")} disabled={locked}><option value="">Any</option>{connections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <div><label className="label">Priority (tie-break)</label><input className="input" type="number" min={-100} max={100} value={f.priority} onChange={set("priority")} /></div>
        <div><label className="label">Table</label><input className="input font-mono" value={f.table_name} onChange={set("table_name")} disabled={locked} /></div>
        <div><label className="label">Column</label><input className="input font-mono" value={f.column_name} onChange={set("column_name")} disabled={locked} /></div>
        <div><label className="label">Category</label>
          <select className="input" value={f.category} onChange={set("category")} disabled={locked}><option value="">Any</option>{meta.categories.map((c: string) => <option key={c}>{c}</option>)}</select></div>
        <div><label className="label">Sensitivity</label>
          <select className="input" value={f.sensitivity} onChange={set("sensitivity")} disabled={locked}><option value="">Any</option>{meta.labels.map((c: string) => <option key={c}>{c}</option>)}</select></div>
        <div className="col-span-2"><label className="label">Description</label><input className="input" value={f.description} onChange={set("description")} /></div>
      </div>
      <p className="text-[11px] text-fog-500">{meta.actions[f.action]}</p>
      {!locked && (
        <div className="rounded-lg border border-ink-700 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-fog-400">Simulate against {selected?.name} without saving</span>
            <Button size="sm" icon={<FlaskConical className="h-3.5 w-3.5" />} onClick={() => sim.mutate()} loading={sim.isPending}>Simulate</Button>
          </div>
          <ErrorText error={sim.error} />
          {sim.data && (
            <div className="mt-2 text-xs">
              <div className="mb-1 text-fog-300">{sim.data.affected_columns} column(s) would change for role {sim.data.role}:</div>
              <ul className="space-y-1">
                {sim.data.changes.map((c: any) => (
                  <li key={c.table + c.column} className="flex flex-wrap items-center gap-2">
                    <span className="font-mono">{c.table}.{c.column}</span> <ActionBadge action={c.current} /> → <ActionBadge action={c.proposed} />
                    <span className="font-mono text-fog-500">“{c.synthetic_example.input}” → <Value v={c.synthetic_example.proposed} /></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <ErrorText error={save.error} />
      <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>{initial ? "Save new version" : "Create policy"}</Button></div>
    </div>
  );
}

function Versions({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["versions", id], queryFn: () => api(`/api/policies/${id}/versions`) });
  if (q.isLoading) return <Spinner />;
  return (
    <table className="w-full">
      <thead><tr><th className="th">Version</th><th className="th">Change</th><th className="th">Action</th><th className="th">Active</th><th className="th">By</th><th className="th">When</th></tr></thead>
      <tbody>
        {q.data.map((v: any) => (
          <tr key={v.version}>
            <td className="td">v{v.version}</td><td className="td"><Badge>{v.change_type}</Badge></td><td className="td"><ActionBadge action={v.snapshot.action} /></td>
            <td className="td">{v.snapshot.active ? "yes" : "no"}</td><td className="td">{v.changed_by}</td><td className="td text-xs text-fog-400">{fmtTime(v.changed_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function PoliciesPage() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["policy-meta"], queryFn: () => api("/api/policies/actions"), staleTime: Infinity });
  const q = useQuery({ queryKey: ["policies"], queryFn: () => api<Policy[]>("/api/policies") });
  const [role, setRole] = useState<"all" | "admin" | "support" | "analyst" | "compliance">("all");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Policy | null>(null);
  const [history, setHistory] = useState<Policy | null>(null);
  const toggle = useMutation({
    mutationFn: (p: Policy) => api(`/api/policies/${p.id}`, { method: "PATCH", body: { active: !p.active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
  const rows = useMemo(() => (q.data ?? []).filter((p) => role === "all" || p.role === role).sort((a, b) => a.role.localeCompare(b.role) || b.specificity - a.specificity || a.id - b.id), [q.data, role]);

  return (
    <div>
      <PageHeader
        title="Masking Policy Studio"
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>New policy</Button>}
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card title="Policies" subtitle={`${rows.length} shown · every change creates a new version and an audit event`} actions={<Tabs value={role} onChange={setRole} items={[{ value: "all", label: "All" }, { value: "admin", label: "Admin" }, { value: "support", label: "Support" }, { value: "analyst", label: "Analyst" }, { value: "compliance", label: "Compliance" }]} />}>
          {q.isLoading ? <Spinner /> : (
            <div className="-mx-5 -mb-5 max-h-[720px] overflow-auto">
              <table className="w-full min-w-[820px]">
                <thead><tr><th className="th">Role</th><th className="th">Scope</th><th className="th">Transformation</th><th className="th">Specificity</th><th className="th">Version</th><th className="th">Status</th><th className="th text-right">Actions</th></tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} className={p.active ? "" : "opacity-50"}>
                      <td className="td"><RoleChip role={p.role} /></td>
                      <td className="td"><div className="text-[13px]">{p.name}</div><Scope p={p} />{p.description && <div className="mt-0.5 text-[11px] text-fog-500">{p.description}</div>}</td>
                      <td className="td"><ActionBadge action={p.action} /></td>
                      <td className="td tabular-nums text-fog-400">{p.specificity}{p.priority ? ` · p${p.priority}` : ""}</td>
                      <td className="td text-xs text-fog-400">v{p.version}<div>{p.updated_by}</div></td>
                      <td className="td">{p.active ? <Badge tone="green">active</Badge> : <Badge>inactive</Badge>}</td>
                      <td className="td"><div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(p)}>Edit</Button>
                        <Button size="sm" variant="ghost" aria-label="History" onClick={() => setHistory(p)}><History className="h-3.5 w-3.5" /></Button>
                        <Button size="sm" variant="ghost" aria-label={p.active ? "Deactivate" : "Activate"} onClick={() => toggle.mutate(p)}><Power className={`h-3.5 w-3.5 ${p.active ? "text-emerald-300" : ""}`} /></Button>
                      </div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <div className="space-y-4">
          <Card title="Preview a transformation" subtitle="Synthetic data only">{meta.data ? <Preview meta={meta.data} /> : <Spinner />}</Card>



        </div>
      </div>
      <Modal open={creating} onClose={() => setCreating(false)} title="New masking policy" wide>{meta.data && <PolicyForm meta={meta.data} onClose={() => setCreating(false)} />}</Modal>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Edit policy #${editing?.id}`} wide>{meta.data && editing && <PolicyForm meta={meta.data} initial={editing} onClose={() => setEditing(null)} />}</Modal>
      <Modal open={!!history} onClose={() => setHistory(null)} title={`Version history · ${history?.name}`} wide>{history && <Versions id={history.id} />}</Modal>
    </div>
  );
}
