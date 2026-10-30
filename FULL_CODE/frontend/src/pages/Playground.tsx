import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Ban, ChevronDown, ChevronRight, Columns3, Eye, KeyRound, Play, ShieldAlert, ShieldCheck, Timer, UserCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { RoleChip } from "../components/Layout";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, SensBadge, Spinner, Tabs, Value } from "../components/ui";
import { api, apiAllowDenied } from "../lib/api";
import { DEMO_ACCOUNTS, useAuth } from "../lib/auth";
import { KIND_LABEL, useConnections } from "../lib/connections";

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
    <div className={clsx("overflow-auto rounded-lg border border-ink-700", compact ? "max-h-80" : "max-h-[420px]")}>
      <table className="w-full">
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
            <tr key={i} className="hover:bg-ink-800/40">
              {row.map((v, j) => (
                <td key={j} className="td mono whitespace-nowrap">
                  <Value v={v} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!r.rows!.length && <div className="p-4 text-center text-xs text-fog-500">Query returned no rows</div>}
    </div>
  );
}

function Denied({ r }: { r: Result }) {
  return (
    <div className="rounded-xl border border-rose-400/30 bg-rose-500/5 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-rose-200">
        <Ban className="h-4 w-4" /> Blocked by the backend · <span className="font-mono text-xs">{r.error!.code}</span>
      </div>
      <p className="mt-1.5 text-sm text-rose-100/90">{r.error!.message}</p>
      <div className="mt-2 text-xs text-fog-400">
        Role <b>{r.role}</b> · {r.duration_ms} ms · audit event{" "}
        <Link className="font-mono text-[#A8ADFF] hover:underline" to={`/audit?event=${r.audit_event_id}`}>
          {r.audit_event_id.slice(0, 12)}
        </Link>
      </div>
    </div>
  );
}

function MetaStrip({ r }: { r: Result }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-fog-400">
      <span className="flex items-center gap-1.5">
        <UserCheck className="h-3.5 w-3.5" /> {r.user} <RoleChip role={r.role} />
      </span>
      <span className="flex items-center gap-1.5"><Timer className="h-3.5 w-3.5" /> {r.duration_ms} ms</span>
      <span>{r.row_count} rows{r.truncated && " (truncated to row cap)"}</span>
      <span>tables: <span className="font-mono">{r.tables?.join(", ")}</span></span>
      <span>
        audit:{" "}
        <Link className="font-mono text-[#A8ADFF] hover:underline" to={`/audit?event=${r.audit_event_id}`}>
          {r.audit_event_id.slice(0, 12)}
        </Link>
      </span>
      {!!r.break_glass_columns?.length && <Badge tone="amber">break-glass: {r.break_glass_columns.join(", ")}</Badge>}
    </div>
  );
}

function DecisionTable({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="overflow-auto rounded-lg border border-ink-700">
      <table className="w-full min-w-[820px]">
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
            <tr key={i}>
              <td className="td mono">{d.name}</td>
              <td className="td mono text-fog-300">{d.aggregate ? `${d.aggregate}(${d.source ?? "*"})` : d.source}</td>
              <td className="td text-xs">{d.category ?? "—"}</td>
              <td className="td"><SensBadge label={d.sensitivity} /></td>
              <td className="td"><ActionBadge action={d.action} /></td>
              <td className="td text-xs">{d.policy_id ? <span>#{d.policy_id} {d.policy_name}</span> : <span className="text-fog-400">{d.policy_name ?? "—"}</span>}</td>
              <td className="td text-xs text-fog-400">{d.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Permissions({ connId, onInsert }: { connId: string; onInsert: (text: string) => void }) {
  const q = useQuery({ queryKey: ["perms", connId], queryFn: () => api(`/api/query/permissions?connection_id=${connId}`) });
  const [open, setOpen] = useState<string | null>(null);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;
  const p = q.data;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        Signed in as <b>{p.user}</b> <RoleChip role={p.role} />
      </div>
      {p.break_glass_available && (
        <Alert tone="warn">Break-glass available: BREAK_GLASS columns show partial values unless you enter a justification (≥ 10 chars). Every use is audited.</Alert>
      )}
      <div className="divide-y divide-ink-700/70 rounded-lg border border-ink-700">
        {p.tables.map((t: any) => (
          <div key={t.table}>
            <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-ink-800/50" onClick={() => setOpen(open === t.table ? null : t.table)}>
              {open === t.table ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              <span className="font-mono">{t.table}</span>
              {!t.classified && <Badge tone="red">unscanned · blocked</Badge>}
              <span className="ml-auto text-[11px] text-fog-500">{t.columns.filter((c: any) => c.action !== "ALLOW").length} protected</span>
            </button>
            {open === t.table && (
              <ul className="space-y-1 px-3 pb-3">
                <li>
                  <button className="text-[11px] text-[#A8ADFF] hover:underline" onClick={() => onInsert(`SELECT * FROM ${t.table} LIMIT 20`)}>
                    Insert SELECT * FROM {t.table}
                  </button>
                </li>
                {t.columns.map((c: any) => (
                  <li key={c.column} className="flex items-center justify-between gap-2 text-xs">
                    <button className="font-mono text-fog-300 hover:text-fog-100 hover:underline" title="Insert column name" onClick={() => onInsert(c.column)}>
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
      <p className="text-[11px] text-fog-500">Tables not listed are not granted to this role and are rejected server-side.</p>
    </div>
  );
}

type Ident = { username: string; role: string; token: string };

function Compare({ connId, sql }: { connId: string; sql: string }) {
  // Tokens of separately authenticated sessions, held in memory only.
  const [idents, setIdents] = useState<Ident[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const signIn = async (a: (typeof DEMO_ACCOUNTS)[number]) => {
    setErr(null);
    try {
      const r = await api<{ token: string; user: { username: string; role: string } }>("/api/auth/login", { body: { username: a.username, password: a.password, mode: "bearer" } });
      setIdents((x) => [...x.filter((i) => i.username !== a.username), { username: r.user.username, role: r.user.role, token: r.token }]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Login failed");
    }
  };
  const run = useMutation({
    mutationFn: () => api<{ results: any[] }>("/api/query/compare", { body: { connection_id: connId, sql, session_tokens: idents.map((i) => i.token) } }),
  });
  const ordered = DEMO_ACCOUNTS.map((a) => idents.find((i) => i.username === a.username)).filter(Boolean) as Ident[];
  useEffect(() => () => setIdents([]), []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {DEMO_ACCOUNTS.map((a) => {
          const on = idents.some((i) => i.username === a.username);
          return (
            <Button key={a.username} size="sm" variant={on ? "secondary" : "ghost"} icon={on ? <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" /> : <KeyRound className="h-3.5 w-3.5" />} onClick={() => signIn(a)}>
              {on ? `${a.username} authenticated` : `Sign in as ${a.username}`}
            </Button>
          );
        })}
        <Button size="sm" variant="primary" icon={<Columns3 className="h-3.5 w-3.5" />} disabled={!ordered.length} loading={run.isPending} onClick={() => run.mutate()}>
          Run as {ordered.length || "…"} identities
        </Button>
      </div>
      <p className="text-xs text-fog-500">
        Each identity performs its own real login; its session token stays in this tab's memory. The server resolves each token to its user and role — the role is never sent by the browser.
      </p>
      {err && <Alert tone="error">{err}</Alert>}
      <ErrorText error={run.error} />
      {run.data && (
        <div className="grid gap-4 2xl:grid-cols-2">
          {run.data.results.map((res, i) => (
            <div key={i} className="min-w-0 space-y-2 rounded-xl border border-ink-700 bg-ink-900/40 p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-medium">{res.user ?? "invalid session"} {res.role && <RoleChip role={res.role} />}</span>
                {res.ok ? <Badge tone="green">{res.body.row_count} rows · {res.body.duration_ms} ms</Badge> : <Badge tone="red">blocked</Badge>}
              </div>
              {res.ok ? <ResultTable r={res.body} compact /> : res.body?.error ? <Denied r={{ ...res.body, role: res.role }} /> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PlaygroundPage() {
  const { selected } = useConnections();
  const { can } = useAuth();
  const examples = useQuery({ queryKey: ["examples"], queryFn: () => api<any[]>("/api/query/examples"), staleTime: Infinity });
  const [sql, setSql] = useState("SELECT c.customer_id, c.cust_nm, c.mob_no, c.emailid, c.dob_dt,\n       a.account_no, a.curr_bal, k.CARD_NO, k.NAME_ON_CARD\nFROM customers c\nJOIN accounts a ON a.customer_id = c.customer_id\nJOIN cards k ON k.LINKED_ACCT = a.account_no\nWHERE c.customer_id = 'CIF-00UKL72D'");
  const [justification, setJustification] = useState("");
  const [tab, setTab] = useState<"result" | "decisions" | "compare">("result");
  const [result, setResult] = useState<Result | null>(null);
  const [risk, setRisk] = useState<any>(null);

  const exec = useMutation({
    mutationFn: () => apiAllowDenied<Result>("/api/query/execute", { body: { connection_id: selected!.id, sql, justification: justification || undefined } }),
    onSuccess: (r) => {
      setResult(r.body);
      setRisk(null);
      if (tab === "compare") setTab("result");
    },
  });
  const analyze = useMutation({
    mutationFn: () => api("/api/query/analyze", { body: { connection_id: selected!.id, sql, justification: justification || undefined } }),
    onSuccess: (r) => setRisk(r),
  });

  const editorRef = useRef<HTMLTextAreaElement>(null);
  const insertText = (text: string) => {
    const el = editorRef.current;
    if (!el || text.startsWith("SELECT")) {
      setSql(text);
      return;
    }
    const { selectionStart: a, selectionEnd: b } = el;
    setSql(sql.slice(0, a) + text + sql.slice(b));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(a + text.length, a + text.length);
    });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      if (selected) exec.mutate();
    }
  };

  if (!selected) return <Empty title="No database available">Your role has no granted databases yet.</Empty>;

  return (
    <div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-4">
          <Card
            title="SQL"
            subtitle={`${selected.name} · ${KIND_LABEL[selected.kind] ?? selected.kind} dialect · read-only SELECT`}
            actions={
              <>
                <Button size="sm" icon={<Eye className="h-3.5 w-3.5" />} onClick={() => analyze.mutate()} loading={analyze.isPending}>
                  Risk preview
                </Button>
                <Button size="sm" variant="primary" icon={<Play className="h-3.5 w-3.5" />} onClick={() => exec.mutate()} loading={exec.isPending}>
                  Run <kbd className="ml-1 rounded bg-white/10 px-1 text-[10px]">Ctrl ↵</kbd>
                </Button>
              </>
            }
          >
            <div className="mb-3 flex flex-wrap gap-1.5">
              {examples.data?.map((e) => (
                <button
                  key={e.id}
                  onClick={() => setSql(e.sql)}
                  className={clsx(
                    "rounded-md border px-2 py-1 text-[11.5px] transition-colors",
                    ["unauthorized", "catalog", "destructive", "stacked", "inference", "expression", "subquery"].includes(e.id)
                      ? "border-rose-400/25 text-rose-200/90 hover:bg-rose-500/10"
                      : "border-ink-600 text-fog-300 hover:border-accent/50 hover:bg-ink-800",
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
              className="w-full resize-y rounded-lg border border-ink-600 bg-ink-950 p-3 font-mono text-[13px] leading-relaxed text-[#D7DCFF] focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
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
              <Compare connId={selected.id} sql={sql} />
            ) : !result ? (
              <Empty icon={<ShieldAlert className="h-8 w-8" />} title="Run a query">Pick an example above or write your own. Try the red ones to see real backend denials.</Empty>
            ) : result.error ? (
              <Denied r={result} />
            ) : tab === "result" ? (
              <div className="space-y-3">
                <MetaStrip r={result} />
                {result.notes?.map((n) => <Alert key={n} tone="info">{n}</Alert>)}
                <ResultTable r={result} />
                <details className="text-xs">
                  <summary className="cursor-pointer text-fog-400">Validated & rewritten SQL actually executed</summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg border border-ink-700 bg-ink-950 p-3 font-mono text-[12px] text-fog-300">{result.executed_sql}</pre>
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
            <Permissions connId={selected.id} onInsert={insertText} />
          </Card>
          <Card title="Legend">
            <div className="flex flex-wrap gap-1.5">
              {["ALLOW", "PARTIAL", "REDACT", "HASH", "GENERALIZE", "AGGREGATE_ONLY", "BREAK_GLASS", "DENY"].map((a) => <ActionBadge key={a} action={a} />)}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-fog-500">
              Filtering, sorting or grouping by a column you can't see raw is rejected (inference protection). Aggregates over AGGREGATE_ONLY columns suppress groups smaller than k.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
