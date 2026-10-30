import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Ban, ChevronDown, ChevronRight, Eye, Play, ShieldAlert, Timer, UserCheck } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { RoleChip } from "../components/Layout";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, PageHeader, SensBadge, Spinner, Tabs, Value } from "../components/ui";
import { api, apiAllowDenied } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConnections } from "../lib/connections";

type Decision = { name: string; kind: string; source: string | null; aggregate: string | null; action: string; category: string | null; sensitivity: string | null; policy_id: number | null; policy_name: string | null; reason: string };
type Result = {
  columns?: string[]; rows?: any[][]; row_count?: number; truncated?: boolean; decisions?: Decision[]; tables?: string[]; predicate_columns?: string[];
  executed_sql?: string; notes?: string[]; role: string; user?: string; duration_ms: number; audit_event_id: string; break_glass_columns?: string[];
  error?: { code: string; message: string };
};

function ResultTable({ r, compact }: { r: Result; compact?: boolean }) {
  if (!r.columns) return null;
  const actions = Object.fromEntries((r.decisions ?? []).map((d, i) => [i, d.action]));
  return (
    <div className={clsx("overflow-x-auto rounded-lg border border-[#DCE5F0]", compact ? "max-h-80" : "max-h-[420px]")}>
      <table className="w-full text-xs min-w-[600px]">
        <thead>
          <tr>
            {r.columns.map((c, i) => (
              <th key={i} className="th whitespace-nowrap">
                <div className="flex items-center gap-1.5">
                  {c} {actions[i] !== "ALLOW" && <ActionBadge action={actions[i]} />}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {r.rows!.map((row, i) => (
            <tr key={i} className="hover:bg-[#F4F8FD] transition-colors">
              {row.map((v, j) => (
                <td key={j} className="td mono whitespace-nowrap text-[#172B45]">
                  <Value v={v} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!r.rows!.length && <div className="p-4 text-center text-xs text-[#64748B]">Query returned no rows</div>}
    </div>
  );
}

function Denied({ r }: { r: Result }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-bold text-rose-900">
        <Ban className="h-4 w-4 text-rose-600" /> Blocked by the backend · <span className="font-mono text-xs">{r.error!.code}</span>
      </div>
      <p className="mt-1.5 text-xs text-rose-800 leading-relaxed font-medium">{r.error!.message}</p>
      <div className="mt-3 text-xs text-[#64748B]">
        Role <b>{r.role}</b> · {r.duration_ms} ms · audit event{" "}
        <Link className="font-mono text-[#1D5FA7] font-semibold hover:underline" to={`/admin/audit?event=${r.audit_event_id}`}>
          {r.audit_event_id.slice(0, 12)}
        </Link>
      </div>
    </div>
  );
}

function MetaStrip({ r }: { r: Result }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-[#64748B]">
      <span className="flex items-center gap-1.5 font-medium text-[#172B45]">
        <UserCheck className="h-3.5 w-3.5 text-[#1D5FA7]" /> {r.user} <RoleChip role={r.role} />
      </span>
      <span className="flex items-center gap-1.5"><Timer className="h-3.5 w-3.5" /> {r.duration_ms} ms</span>
      <span>{r.row_count} rows{r.truncated && " (truncated to row cap)"}</span>
      <span>tables: <span className="font-mono font-semibold text-[#172B45]">{r.tables?.join(", ")}</span></span>
      <span>
        audit:{" "}
        <Link className="font-mono text-[#1D5FA7] font-semibold hover:underline" to={`/admin/audit?event=${r.audit_event_id}`}>
          {r.audit_event_id.slice(0, 12)}
        </Link>
      </span>
      {!!r.break_glass_columns?.length && <Badge tone="amber">break-glass: {r.break_glass_columns.join(", ")}</Badge>}
    </div>
  );
}

function DecisionTable({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[#DCE5F0]">
      <table className="w-full text-xs min-w-[750px]">
        <thead>
          <tr>
            <th className="th">Output column</th>
            <th className="th">Lineage (source)</th>
            <th className="th">Category</th>
            <th className="th">Sensitivity</th>
            <th className="th">Transformation</th>
            <th className="th">Policy</th>
            <th className="th">Why</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((d, i) => (
            <tr key={i} className="hover:bg-[#F4F8FD]">
              <td className="td mono font-semibold text-[#172B45]">{d.name}</td>
              <td className="td mono text-[#64748B]">{d.aggregate ? `${d.aggregate}(${d.source ?? "*"})` : d.source}</td>
              <td className="td text-xs">{d.category ?? "—"}</td>
              <td className="td"><SensBadge label={d.sensitivity} /></td>
              <td className="td"><ActionBadge action={d.action} /></td>
              <td className="td text-xs font-semibold text-[#1D5FA7]">{d.policy_id ? `#${d.policy_id}` : "default"}</td>
              <td className="td text-xs text-[#64748B]">{d.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Compare({ connId, sql }: { connId: string; sql: string }) {
  const roles = ["admin", "support", "analyst"] as const;
  const q = useQuery({
    queryKey: ["compare-roles", connId, sql],
    queryFn: async () => {
      const results = await Promise.all(
        roles.map(async (role) => {
          const res = await apiAllowDenied("/api/query/execute", { body: { connection_id: connId, sql, as_role: role } });
          return { role, ...(res.ok ? res.body : { error: res.body?.error ?? { code: "error", message: "Failed" }, duration_ms: 0, audit_event_id: "" }) };
        }),
      );
      return results;
    },
  });
  if (q.isLoading) return <Spinner label="Running query under each role…" />;
  if (q.error) return <ErrorText error={q.error} />;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {q.data?.map((r: any) => (
          <Card key={r.role} title={<div className="flex items-center gap-2"><RoleChip role={r.role} /> <span className="text-xs text-[#64748B]">{r.duration_ms} ms</span></div>}>
            {r.error ? <Denied r={r} /> : <ResultTable r={r} compact />}
          </Card>
        ))}
      </div>
    </div>
  );
}

function Permissions({ connId, onInsert }: { connId: string; onInsert: (s: string) => void }) {
  const q = useQuery({ queryKey: ["grants", connId], queryFn: () => api<{ role: string; tables: { table: string; classified: boolean; columns: { column: string; action: string; category: string }[] }[] }>(`/api/grants?connection_id=${connId}`) });
  const [open, setOpen] = useState<string | null>(null);
  if (q.isLoading) return <Spinner label="Loading effective permissions…" />;
  if (q.error) return <ErrorText error={q.error} />;
  return (
    <div className="divide-y divide-[#DCE5F0] rounded-lg border border-[#DCE5F0] bg-white">
      {q.data?.tables.map((t) => (
        <div key={t.table}>
          <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[#F4F8FD] transition-colors" onClick={() => setOpen(open === t.table ? null : t.table)}>
            {open === t.table ? <ChevronDown className="h-3.5 w-3.5 text-[#64748B]" /> : <ChevronRight className="h-3.5 w-3.5 text-[#64748B]" />}
            <span className="font-mono font-semibold text-[#172B45]">{t.table}</span>
            {!t.classified && <Badge tone="red">unscanned · blocked</Badge>}
            <span className="ml-auto text-[11px] text-[#64748B]">{t.columns.filter((c: any) => c.action !== "ALLOW").length} protected</span>
          </button>
          {open === t.table && (
            <ul className="space-y-1.5 px-3 pb-3 border-t border-[#DCE5F0] bg-[#F4F8FD]/50 pt-2">
              <li>
                <button className="text-[11px] font-semibold text-[#1D5FA7] hover:underline" onClick={() => onInsert(`SELECT * FROM ${t.table} LIMIT 20`)}>
                  Insert SELECT * FROM {t.table}
                </button>
              </li>
              {t.columns.map((c: any) => (
                <li key={c.column} className="flex items-center justify-between gap-2 text-xs">
                  <button className="font-mono text-[#172B45] hover:text-[#1D5FA7] hover:underline" title="Insert column name" onClick={() => onInsert(c.column)}>
                    {c.column}
                  </button>
                  <ActionBadge action={c.action} />
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export default function PlaygroundPage() {
  const { user, can } = useAuth();
  const { selected } = useConnections();
  const [sql, setSql] = useState("SELECT * FROM customers LIMIT 20");
  const [justification, setJustification] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [risk, setRisk] = useState<any | null>(null);
  const [tab, setTab] = useState<"result" | "decisions" | "compare">("result");
  const editorRef = useRef<HTMLTextAreaElement>(null);

  const examples = [
    { id: "cust", title: "SELECT * FROM customers", sql: "SELECT * FROM customers LIMIT 20" },
    { id: "cards", title: "SELECT * FROM cards", sql: "SELECT CARD_REF, CARD_NO, NAME_ON_CARD, CREDIT_LIMIT FROM cards LIMIT 20" },
    { id: "txns", title: "SELECT * FROM transactions", sql: "SELECT txn_id, customer_id, channel, amount_inr, txn_status FROM transactions LIMIT 20" },
    { id: "unauthorized", title: "BLOCKED: loans table (support/analyst)", sql: "SELECT * FROM loan_applications LIMIT 20" },
    { id: "catalog", title: "BLOCKED: system catalog probe", sql: "SELECT table_name FROM information_schema.tables" },
    { id: "destructive", title: "BLOCKED: write statement", sql: "UPDATE customers SET cust_nm = 'Attacker' WHERE 1 = 1" },
    { id: "stacked", title: "BLOCKED: stacked queries", sql: "SELECT * FROM customers; DROP TABLE audit_events;" },
    { id: "inference", title: "BLOCKED: WHERE on masked phone", sql: "SELECT customer_id FROM customers WHERE mob_no LIKE '%999%'" },
  ];

  const exec = useMutation({
    mutationFn: async (sqlText: string) => {
      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected?.id, sql: sqlText, justification: justification.trim() || undefined },
      });
      return res.ok ? res.body : { error: res.body?.error ?? { code: "error", message: "Failed" }, duration_ms: 0, audit_event_id: "", role: user?.role ?? "" };
    },
    onSuccess: (data) => {
      setResult(data);
      setRisk(null);
    },
  });

  const assess = useMutation({
    mutationFn: (sqlText: string) => api("/api/query/risk", { body: { connection_id: selected?.id, sql: sqlText } }),
    onSuccess: (d) => setRisk(d),
  });

  const insertText = (t: string) => {
    setSql(t);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      exec.mutate(sql);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Query Playground"
        description="Run arbitrary SQL queries against connected databases. The server-side SQL guard rewrites queries to enforce role-based masking and blocks privilege violations."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" icon={<Eye className="h-4 w-4" />} onClick={() => assess.mutate(sql)} loading={assess.isPending} disabled={!selected}>
              Preview risk
            </Button>
            <Button variant="primary" icon={<Play className="h-4 w-4" />} onClick={() => exec.mutate(sql)} loading={exec.isPending} disabled={!selected}>
              Run query <span className="hidden sm:inline font-mono text-[11px] opacity-75">(Ctrl+Enter)</span>
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card title="SQL Editor" subtitle="Try approved queries or click red examples to test real server denials">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {examples.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => setSql(e.sql)}
                  className={clsx(
                    "rounded-md border px-2.5 py-1 text-[11.5px] transition-all font-medium",
                    ["unauthorized", "catalog", "destructive", "stacked", "inference"].includes(e.id)
                      ? "border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100"
                      : "border-[#DCE5F0] bg-[#F4F8FD] text-[#123B67] hover:border-[#1D5FA7] hover:bg-[#EAF2FB]",
                  )}
                >
                  {e.title}
                </button>
              ))}
            </div>
            <textarea
              ref={editorRef}
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              onKeyDown={onKey}
              spellCheck={false}
              aria-label="SQL query"
              rows={6}
              className="w-full resize-y rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3 font-mono text-[13px] leading-relaxed text-[#172B45] focus:border-[#1D5FA7] focus:outline-none focus:ring-2 focus:ring-[#1D5FA7]/20 shadow-inner"
            />
            {can("raw:break_glass") && (
              <div className="mt-3">
                <label className="label" htmlFor="just">Break-glass justification (optional)</label>
                <input id="just" className="input" placeholder="e.g. Fraud case FC-2026-114 chargeback review" value={justification} onChange={(e) => setJustification(e.target.value)} maxLength={300} />
              </div>
            )}
            {exec.error && <div className="mt-3"><ErrorText error={exec.error} /></div>}
          </Card>

          {risk && (
            <Card title="Risk preview (not executed)" actions={<Button size="sm" variant="ghost" onClick={() => setRisk(null)}>Dismiss</Button>}>
              {risk.permitted ? (
                <div className="space-y-3">
                  <Alert tone={risk.protected_columns.length ? "warn" : "success"} title={`Permitted for ${risk.role}`}>
                    {risk.protected_columns.length} of {risk.decisions.length} output columns are protected. Predicates use: {risk.predicate_columns.join(", ") || "none"}.
                  </Alert>
                  <DecisionTable decisions={risk.decisions} />
                </div>
              ) : (
                <Alert tone="error" title={`Would be blocked · ${risk.error.code}`}>{risk.error.message}</Alert>
              )}
            </Card>
          )}

          <Card
            title={
              <Tabs
                value={tab}
                onChange={setTab}
                items={[
                  { value: "result", label: "Result" },
                  { value: "decisions", label: "Masking decisions" },
                  { value: "compare", label: "Compare roles" },
                ]}
              />
            }
          >
            {tab === "compare" ? (
              selected ? <Compare connId={selected.id} sql={sql} /> : <Empty title="No database selected">Please select a database connection above to compare roles.</Empty>
            ) : !result ? (
              <Empty icon={<ShieldAlert className="h-8 w-8 text-[#1D5FA7]" />} title="Run a query">Pick an example above or write your own. Try the red ones to see real backend denials.</Empty>
            ) : result.error ? (
              <Denied r={result} />
            ) : tab === "result" ? (
              <div className="space-y-3">
                <MetaStrip r={result} />
                {result.notes?.map((n) => <Alert key={n} tone="info">{n}</Alert>)}
                <ResultTable r={result} />
                <details className="text-xs">
                  <summary className="cursor-pointer font-semibold text-[#1D5FA7] hover:underline">Validated & rewritten SQL actually executed</summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3 font-mono text-[12px] text-[#123B67] leading-relaxed">{result.executed_sql}</pre>
                </details>
              </div>
            ) : (
              <div className="space-y-3">
                <MetaStrip r={result} />
                <DecisionTable decisions={result.decisions ?? []} />
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Effective permissions" subtitle="Tables & columns loaded live from the server · click to insert">
            {selected ? (
              <Permissions connId={selected.id} onInsert={insertText} />
            ) : (
              <div className="p-4 text-center text-xs text-[#64748B]">Select a database connection above</div>
            )}
          </Card>
          <Card title="Legend">
            <div className="flex flex-wrap gap-1.5">
              {["ALLOW", "PARTIAL", "REDACT", "HASH", "GENERALIZE", "AGGREGATE_ONLY", "BREAK_GLASS", "DENY"].map((a) => <ActionBadge key={a} action={a} />)}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-[#64748B]">
              Filtering, sorting or grouping by a column you cannot see raw is rejected (inference protection). Aggregates over AGGREGATE_ONLY columns suppress groups smaller than k.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
