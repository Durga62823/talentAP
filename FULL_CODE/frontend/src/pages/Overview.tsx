import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Ban, Database, Fingerprint, Gauge, Radar, ShieldAlert, ShieldCheck, SlidersHorizontal, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, Empty, ErrorText, OutcomeBadge, PageHeader, Spinner, Stat } from "../components/ui";
import { api, fmtTime } from "../lib/api";
import { KIND_LABEL } from "../lib/connections";

const SENS_COLORS: Record<string, string> = {
  PII_HIGH: "#E11D48",
  PII_MEDIUM: "#D97706",
  FINANCIAL_CONFIDENTIAL: "#1D5FA7",
  INTERNAL: "#3478C8",
  PUBLIC: "#64748B",
};

const tooltipStyle = {
  background: "#FFFFFF",
  border: "1px solid #DCE5F0",
  borderRadius: 8,
  fontSize: 12,
  color: "#172B45",
  boxShadow: "0 4px 12px rgba(18,59,103,0.08)",
};

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
        description="Comprehensive dashboard of database connections, automated PII classifications, and query protection activity."
        actions={
          <>
            <Link to="/admin/uploads">
              <Button icon={<UploadCloud className="h-4 w-4" />}>Upload files</Button>
            </Link>


          </>
        }
      />

      {o.tables_scanned === 0 ? (
        <Empty
          icon={<Radar className="h-8 w-8 text-[#1D5FA7]" />}
          title="No scans yet"
          action={
            <div className="flex flex-wrap gap-2">
              <Link to="/admin/connections">
                <Button variant="primary">Connect a database and scan</Button>
              </Link>
              <Link to="/admin/uploads">
                <Button icon={<UploadCloud className="h-4 w-4" />}>Upload files</Button>
              </Link>
            </div>
          }
        >
          Register a database connection and run a PII scan, or upload files to populate the overview.
        </Empty>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3.5">
            <Stat label="Data sources" value={o.connections.total} hint={`${o.connections.healthy} healthy · ${o.connections.unhealthy} unhealthy`} icon={<Database className="h-4 w-4" />} />
            <Stat label="Tables scanned" value={o.tables_scanned} hint={`${o.columns_classified} columns classified`} icon={<Radar className="h-4 w-4" />} tone="cyan" />
            <Stat label="Sensitive columns" value={o.sensitive_columns} hint={`${o.high_sensitivity_columns} high · ${o.pending_review} pending`} icon={<ShieldAlert className="h-4 w-4" />} tone="amber" />
            <Stat label="Active policies" value={o.active_policies} hint={risk.policy_coverage_pct != null ? `${risk.policy_coverage_pct}% coverage` : undefined} icon={<SlidersHorizontal className="h-4 w-4" />} tone="green" />
            <Stat label="Queries evaluated" value={o.queries_evaluated} hint="through masking pipeline" icon={<ShieldCheck className="h-4 w-4" />} />
            <Stat label="Queries blocked" value={o.queries_blocked} hint={`${o.privilege_violations} violations · ${o.failed_logins} failed`} icon={<Ban className="h-4 w-4" />} tone="red" />
          </div>

          <div className="mt-8 m-4 grid gap-4 lg:grid-cols-3">
            <Card title="Sensitivity distribution" subtitle="Effective labels after review">
              <div className="h-64">
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
                    <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#64748B", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#1D5FA710" }} />
                    <Bar dataKey="value" fill="#1D5FA7" radius={[0, 4, 4, 0]} barSize={12} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card
              title={
                <span className="flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-[#1D5FA7]" /> Exposure risk score
                </span>
              }
            >
              <div className="flex items-end gap-3">
                <div className="text-4xl font-bold tabular-nums text-[#172B45]">{risk.score ?? "—"}</div>
                <div className="pb-1 text-xs text-[#64748B]">/ 100 · {risk.covered_columns}/{risk.sensitive_columns} sensitive columns covered</div>
              </div>
              <div className="mt-3.5 space-y-2">
                {risk.top_columns.slice(0, 5).map((c: any) => (
                  <div key={c.table + c.column} className="flex items-center gap-2 text-xs">
                    <span className="w-24 sm:w-36 truncate font-mono text-[#172B45]">
                      {c.table}.{c.column}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#EEF3F9]">
                      <div className="h-full rounded-full bg-gradient-to-r from-[#1D5FA7] to-rose-500" style={{ width: `${Math.min(100, c.risk)}%` }} />
                    </div>
                    <span className="w-8 text-right tabular-nums text-[#64748B] font-medium">{c.risk}</span>
                  </div>
                ))}
              </div>
              <details className="mt-3 text-[11px] text-[#64748B]">
                <summary className="cursor-pointer font-medium text-[#1D5FA7] hover:underline">How is this calculated?</summary>
                <p className="mt-1 leading-relaxed bg-[#F4F8FD] p-2 rounded border border-[#DCE5F0]">{risk.formula}</p>
              </details>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Access activity" subtitle="Protected queries and denials, last 14 days" className="lg:col-span-2">
              {o.timeline.length ? (
                <div className="h-56">
                  <ResponsiveContainer>
                    <AreaChart data={o.timeline}>
                      <defs>
                        <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0" stopColor="#1D5FA7" stopOpacity={0.35} />
                          <stop offset="1" stopColor="#1D5FA7" stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0" stopColor="#E11D48" stopOpacity={0.35} />
                          <stop offset="1" stopColor="#E11D48" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#DCE5F0" vertical={false} strokeDasharray="3 3" />
                      <XAxis dataKey="day" tick={{ fill: "#64748B", fontSize: 11 }} axisLine={{ stroke: "#DCE5F0" }} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fill: "#64748B", fontSize: 11 }} axisLine={{ stroke: "#DCE5F0" }} tickLine={false} width={30} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Area type="monotone" dataKey="success" name="Executed" stroke="#1D5FA7" fill="url(#g1)" strokeWidth={2} />
                      <Area type="monotone" dataKey="denied" name="Blocked" stroke="#E11D48" fill="url(#g2)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <Empty title="No query activity yet">Run queries in the playground to see activity here.</Empty>
              )}
            </Card>

            <Card title="Connection health" actions={<Link to="/admin/connections" className="text-xs text-[#1D5FA7] font-semibold hover:underline">Manage</Link>}>
              <ul className="space-y-2">
                {o.connections.items.map((c: any) => (
                  <li key={c.id} className="flex items-center justify-between rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-[#172B45]">{c.name}</div>
                      <div className="text-[11px] text-[#64748B]">{KIND_LABEL[c.kind] ?? c.kind}</div>
                    </div>
                    <Badge tone={c.status === "healthy" ? "green" : c.status === "unhealthy" ? "red" : "neutral"}>{c.status}</Badge>
                  </li>
                ))}
              </ul>
              {o.last_integrity && (
                <Link to="/admin/integrity" className="mt-3 flex items-center gap-2 rounded-lg border border-[#DCE5F0] bg-white px-3 py-2 text-xs text-[#172B45] hover:border-[#1D5FA7] hover:bg-[#EAF2FB] transition-colors">
                  <Fingerprint className="h-4 w-4 text-[#1D5FA7]" />
                  <span>Last integrity check:</span>
                  <Badge tone={o.last_integrity.match ? "green" : "red"}>{o.last_integrity.match ? "unchanged" : "mismatch"}</Badge>
                  <span className="ml-auto text-[11px] text-[#64748B]">{fmtTime(o.last_integrity.created_at)}</span>
                </Link>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Recent security events" subtitle="Denials, violations and errors" actions={<Link to="/admin/audit" className="text-xs text-[#1D5FA7] font-semibold hover:underline">Full audit</Link>}>
              {o.recent_security_events.length ? (
                <ul className="divide-y divide-[#DCE5F0]">
                  {o.recent_security_events.map((e: any) => (
                    <li key={e.id} className="flex items-start gap-3 py-2.5">
                      <OutcomeBadge outcome={e.outcome} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-[#172B45]">
                          <span className="font-semibold">{e.action.replace(/_/g, " ")}</span>
                          <span className="text-[#64748B]"> · {e.actor ?? "anonymous"}{e.role ? ` (${e.role})` : ""}</span>
                        </div>
                        <div className="truncate text-xs text-[#64748B]">{e.reason}</div>
                      </div>
                      <span className="shrink-0 text-[11px] text-[#64748B]">{fmtTime(e.ts)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="No denied or failed events">Blocked queries and violations will appear here.</Empty>
              )}
            </Card>

            <Card title="Recent scans" actions={<Link to="/admin/discovery" className="flex items-center gap-1 text-xs text-[#1D5FA7] font-semibold hover:underline">Discovery <ArrowRight className="h-3 w-3" /></Link>}>
              <ul className="divide-y divide-[#DCE5F0]">
                {o.recent_scans.map((s: any) => (
                  <li key={s.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-3 py-2.5 text-[13px]">
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge tone={s.status === "completed" ? "green" : s.status === "failed" ? "red" : "amber"}>{s.status}</Badge>
                      <span className="min-w-0 truncate font-medium text-[#172B45]">{s.connection_name}</span>
                    </div>
                    <div className="flex items-center justify-between sm:justify-end gap-3 text-xs text-[#64748B]">
                      <span>{s.tables_scanned} tables · {s.sensitive_found} sensitive</span>
                      <span className="w-24 text-right text-[11px] shrink-0">{fmtTime(s.finished_at)}</span>
                    </div>
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
