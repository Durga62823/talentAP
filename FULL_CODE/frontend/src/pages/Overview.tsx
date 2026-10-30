import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Ban, Database, Fingerprint, Gauge, Radar, ShieldAlert, ShieldCheck, SlidersHorizontal, TerminalSquare } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, Empty, ErrorText, OutcomeBadge, PageHeader, Spinner, Stat } from "../components/ui";
import { api, fmtTime } from "../lib/api";
import { KIND_LABEL } from "../lib/connections";

const SENS_COLORS: Record<string, string> = {
  PII_HIGH: "#FB7185",
  PII_MEDIUM: "#FBBF24",
  FINANCIAL_CONFIDENTIAL: "#E879F9",
  INTERNAL: "#22D3EE",
  PUBLIC: "#64748B",
};
const tooltipStyle = { background: "#0F172A", border: "1px solid #26324F", borderRadius: 8, fontSize: 12, color: "#E7ECF5" };

export default function OverviewPage() {
  const q = useQuery({ queryKey: ["overview"], queryFn: () => api("/api/overview"), refetchInterval: 15_000 });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;
  const o = q.data;
  const sensData = Object.entries(o.by_sensitivity as Record<string, number>).map(([name, value]) => ({ name, value }));
  const catData = Object.entries(o.by_category as Record<string, number>)
    .map(([name, value]) => ({ name: name.replace(/_/g, " ").toLowerCase(), value }))
    .sort((a, b) => b.value - a.value);
  const risk = o.risk;

  return (
    <div>
      <PageHeader
        title="Security Overview"

        actions={
          <>
            <Link to="/discovery">
              <Button icon={<Radar className="h-4 w-4" />}>Run discovery</Button>
            </Link>
            <Link to="/playground">
              <Button variant="primary" icon={<TerminalSquare className="h-4 w-4" />}>
                Open query playground
              </Button>
            </Link>
          </>
        }
      />

      {o.tables_scanned === 0 ? (
        <Empty icon={<Radar className="h-8 w-8" />} title="No scans yet" action={<Link to="/connections"><Button variant="primary">Connect a database and scan</Button></Link>}>
          Register a database connection and run a PII scan to populate the overview.
        </Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Data sources" value={o.connections.total} hint={`${o.connections.healthy} healthy · ${o.connections.unhealthy} unhealthy`} icon={<Database className="h-4 w-4" />} />
            <Stat label="Tables scanned" value={o.tables_scanned} hint={`${o.columns_classified} columns classified`} icon={<Radar className="h-4 w-4" />} tone="cyan" />
            <Stat label="Sensitive columns" value={o.sensitive_columns} hint={`${o.high_sensitivity_columns} high sensitivity · ${o.pending_review} pending review`} icon={<ShieldAlert className="h-4 w-4" />} tone="amber" />
            <Stat label="Active policies" value={o.active_policies} hint={risk.policy_coverage_pct != null ? `${risk.policy_coverage_pct}% explicit coverage` : undefined} icon={<SlidersHorizontal className="h-4 w-4" />} tone="green" />
            <Stat label="Queries evaluated" value={o.queries_evaluated} hint="through the masking pipeline" icon={<ShieldCheck className="h-4 w-4" />} />
            <Stat label="Queries blocked" value={o.queries_blocked} hint={`${o.privilege_violations} privilege violations · ${o.failed_logins} failed logins`} icon={<Ban className="h-4 w-4" />} tone="red" />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Card title="Sensitivity distribution" subtitle="Effective labels after review">
              <div className="h-56">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={sensData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2} stroke="none">
                      {sensData.map((d) => (
                        <Cell key={d.name} fill={SENS_COLORS[d.name] ?? "#64748B"} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Detected categories" subtitle="Columns per PII category">
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={catData} layout="vertical" margin={{ left: 10, right: 10 }}>
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#8C97AF", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff08" }} />
                    <Bar dataKey="value" fill="#7C83FF" radius={[0, 4, 4, 0]} barSize={12} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card
              title={
                <span className="flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-fog-400" /> Exposure risk score
                </span>
              }

            >
              <div className="flex items-end gap-3">
                <div className="text-4xl font-semibold tabular-nums">{risk.score ?? "—"}</div>
                <div className="pb-1 text-xs text-fog-400">/ 100 · {risk.covered_columns}/{risk.sensitive_columns} sensitive columns have explicit policies</div>
              </div>
              <div className="mt-3 space-y-1.5">
                {risk.top_columns.slice(0, 5).map((c: any) => (
                  <div key={c.table + c.column} className="flex items-center gap-2 text-xs">
                    <span className="w-40 truncate font-mono text-fog-300">
                      {c.table}.{c.column}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700">
                      <div className="h-full rounded-full bg-gradient-to-r from-accent to-rose-400" style={{ width: `${Math.min(100, c.risk)}%` }} />
                    </div>
                    <span className="w-8 text-right tabular-nums text-fog-400">{c.risk}</span>
                  </div>
                ))}
              </div>
              <details className="mt-3 text-[11px] text-fog-500">
                <summary className="cursor-pointer text-fog-400">How is this calculated?</summary>
                <p className="mt-1 leading-relaxed">{risk.formula}</p>
              </details>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Card title="Access activity" subtitle="Protected queries and denials, last 14 days" className="xl:col-span-2">
              {o.timeline.length ? (
                <div className="h-56">
                  <ResponsiveContainer>
                    <AreaChart data={o.timeline}>
                      <defs>
                        <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0" stopColor="#7C83FF" stopOpacity={0.4} />
                          <stop offset="1" stopColor="#7C83FF" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0" stopColor="#FB7185" stopOpacity={0.4} />
                          <stop offset="1" stopColor="#FB7185" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1B2642" vertical={false} />
                      <XAxis dataKey="day" tick={{ fill: "#8C97AF", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fill: "#8C97AF", fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Area type="monotone" dataKey="success" name="Executed" stroke="#7C83FF" fill="url(#g1)" strokeWidth={2} />
                      <Area type="monotone" dataKey="denied" name="Blocked" stroke="#FB7185" fill="url(#g2)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <Empty title="No query activity yet">Run queries in the playground to see activity here.</Empty>
              )}
            </Card>
            <Card title="Connection health" actions={<Link to="/connections" className="text-xs text-[#A8ADFF] hover:underline">Manage</Link>}>
              <ul className="space-y-2">
                {o.connections.items.map((c: any) => (
                  <li key={c.id} className="flex items-center justify-between rounded-lg border border-ink-700 bg-ink-900/50 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">{c.name}</div>
                      <div className="text-[11px] text-fog-500">{KIND_LABEL[c.kind] ?? c.kind}</div>
                    </div>
                    <Badge tone={c.status === "healthy" ? "green" : c.status === "unhealthy" ? "red" : "neutral"}>{c.status}</Badge>
                  </li>
                ))}
              </ul>
              {o.last_integrity && (
                <Link to="/integrity" className="mt-3 flex items-center gap-2 rounded-lg border border-ink-700 px-3 py-2 text-xs text-fog-300 hover:border-ink-500">
                  <Fingerprint className="h-4 w-4 text-cyan" />
                  Last integrity check: <Badge tone={o.last_integrity.match ? "green" : "red"}>{o.last_integrity.match ? "unchanged" : "mismatch"}</Badge>
                  <span className="ml-auto text-fog-500">{fmtTime(o.last_integrity.created_at)}</span>
                </Link>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card title="Recent security events" subtitle="Denials, violations and errors" actions={<Link to="/audit" className="text-xs text-[#A8ADFF] hover:underline">Full audit</Link>}>
              {o.recent_security_events.length ? (
                <ul className="divide-y divide-ink-700/70">
                  {o.recent_security_events.map((e: any) => (
                    <li key={e.id} className="flex items-start gap-3 py-2">
                      <OutcomeBadge outcome={e.outcome} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px]">
                          <span className="font-medium">{e.action.replace(/_/g, " ")}</span>
                          <span className="text-fog-500"> · {e.actor ?? "anonymous"}{e.role ? ` (${e.role})` : ""}</span>
                        </div>
                        <div className="truncate text-xs text-fog-400">{e.reason}</div>
                      </div>
                      <span className="shrink-0 text-[11px] text-fog-500">{fmtTime(e.ts)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="No denied or failed events">Blocked queries and violations will appear here.</Empty>
              )}
            </Card>
            <Card title="Recent scans" actions={<Link to="/discovery" className="flex items-center gap-1 text-xs text-[#A8ADFF] hover:underline">Discovery <ArrowRight className="h-3 w-3" /></Link>}>
              <ul className="divide-y divide-ink-700/70">
                {o.recent_scans.map((s: any) => (
                  <li key={s.id} className="flex items-center gap-3 py-2 text-[13px]">
                    <Badge tone={s.status === "completed" ? "green" : s.status === "failed" ? "red" : "amber"}>{s.status}</Badge>
                    <span className="min-w-0 flex-1 truncate">{s.connection_name}</span>
                    <span className="text-xs text-fog-400">
                      {s.tables_scanned} tables · {s.sensitive_found} sensitive columns
                    </span>
                    <span className="w-32 text-right text-[11px] text-fog-500">{fmtTime(s.finished_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
