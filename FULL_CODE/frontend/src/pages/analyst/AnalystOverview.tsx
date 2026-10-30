import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Filter,
  TrendingUp,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Spinner, Stat } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useConnections } from "../../lib/connections";

export default function AnalystOverview() {
  const { user } = useAuth();
  const { selected } = useConnections();

  // Real aggregate figures from saffron_bank transactions
  const statsQ = useQuery({
    queryKey: ["analyst-overview-metrics", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return null;
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT COUNT(*) AS total_txns, SUM(amount_inr) AS total_vol, AVG(amount_inr) AS avg_amt FROM transactions",
        },
      });
      if (res.ok && res.body?.rows?.[0]) {
        return {
          totalTxns: Number(res.body.rows[0][0]) || 0,
          totalVol: Number(res.body.rows[0][1]) || 0,
          avgAmt: Number(res.body.rows[0][2]) || 0,
        };
      }
      return null;
    },
    enabled: !!selected?.id,
  });

  // Top channels distribution
  const channelsQ = useQuery({
    queryKey: ["analyst-overview-channels", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT channel, COUNT(*) AS cnt, SUM(amount_inr) AS vol FROM transactions GROUP BY channel ORDER BY cnt DESC LIMIT 6",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          channel: r[0],
          count: Number(r[1]) || 0,
          volume: Number(r[2]) || 0,
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="flex flex-col gap-4 rounded-xl border border-[#DCE5F0] bg-white p-4 sm:p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45]">
            Welcome, {user?.display_name || "Data Analyst"}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-[#64748B]">
            Aggregated intelligence & transactional insights with server-side k-anonymity guarantees (k ≥ 5).
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-3">
          <Link to="/analyst/analytics">
            <Button variant="primary" icon={<BarChart3 className="h-4 w-4" />}>
              Explore Charts
            </Button>
          </Link>
          <Link to="/analyst/explorer">
            <Button variant="secondary" icon={<Filter className="h-4 w-4" />}>
              Aggregate Explorer
            </Button>
          </Link>
        </div>
      </div>

      {/* Approved Analytics Metrics */}
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Total Transactions Analyzed"
          value={statsQ.isLoading ? "…" : statsQ.data?.totalTxns != null ? statsQ.data.totalTxns.toLocaleString() : "—"}
          hint="Saffron Bank core ledger"
          icon={<Database className="h-4 w-4" />}
          tone="cyan"
        />
        <Stat
          label="Total Settled Volume"
          value={
            statsQ.isLoading
              ? "…"
              : statsQ.data?.totalVol != null
                ? `₹${((statsQ.data.totalVol) / 10000000).toFixed(2)} Cr`
                : "—"
          }
          hint="Aggregate sum across all channels"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="green"
        />
        <Stat
          label="Average Transaction Size"
          value={
            statsQ.isLoading
              ? "…"
              : statsQ.data?.avgAmt != null
                ? `₹${Math.round(statsQ.data.avgAmt).toLocaleString()}`
                : "—"
          }
          hint="Calculated via server aggregate"
          icon={<BarChart3 className="h-4 w-4" />}
          tone="indigo"
        />
        <Stat
          label="k-Anonymity Status"
          value="ENFORCED (k ≥ 5)"
          hint="Small group inference blocked"
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone="cyan"
        />
      </div>

      {/* Channel Distribution Summary Card */}
      <Card
        title="Payment Channel Distribution (Top Channels)"
        subtitle="Aggregate volume and transaction count grouped by payment rail"
        actions={
          <Link to="/analyst/trends" className="text-xs font-semibold text-[#1D5FA7] hover:underline">
            View Transaction Trends →
          </Link>
        }
      >
        {channelsQ.isLoading ? (
          <div className="py-8"><Spinner label="Computing channel aggregates..." /></div>
        ) : channelsQ.data && channelsQ.data.length > 0 ? (
          <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
            {channelsQ.data.map((c: any) => (
              <div
                key={c.channel}
                className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-4 transition-all hover:border-[#1D5FA7] hover:bg-[#EAF2FB]/50"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-[#172B45]">{c.channel}</span>
                  <Badge tone="cyan">{c.count.toLocaleString()} txns</Badge>
                </div>
                <div className="mt-2 text-xl font-bold text-[#123B67]">
                  ₹{(c.volume / 100000).toFixed(2)} L
                </div>
                <div className="mt-1 text-[11px] text-[#64748B]">
                  Avg: ₹{Math.round(c.volume / (c.count || 1)).toLocaleString()} / txn
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-6 text-center text-xs text-[#64748B]">No transaction data loaded.</div>
        )}
      </Card>

      {/* Feature Navigation Cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Link
          to="/analyst/analytics"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">Visual Analytics</div>
              <div className="text-xs text-[#64748B]">Channel breakdown & volume distributions</div>
            </div>
          </div>
        </Link>

        <Link
          to="/analyst/explorer"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <Filter className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">Aggregate Explorer</div>
              <div className="text-xs text-[#64748B]">Query builder with server-enforced k ≥ 5 checks</div>
            </div>
          </div>
        </Link>

        <Link
          to="/analyst/reports"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <FileSpreadsheet className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">Privacy-Safe Reports</div>
              <div className="text-xs text-[#64748B]">Screened aggregate reports with CSV export</div>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
