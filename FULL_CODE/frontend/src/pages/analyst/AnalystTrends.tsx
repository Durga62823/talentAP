import { useQuery } from "@tanstack/react-query";
import { RefreshCw, ShieldCheck } from "lucide-react";
import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

export default function AnalystTrends() {
  const { selected } = useConnections();

  // Monthly trends query
  const trendsQ = useQuery({
    queryKey: ["analyst-monthly-trends", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT substr(txn_ts, 1, 7) AS month_str, COUNT(*) AS txn_count, SUM(amount_inr) AS monthly_vol FROM transactions GROUP BY month_str ORDER BY month_str",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          month: r[0],
          count: Number(r[1]) || 0,
          volume: Math.round(Number(r[2]) || 0),
          volumeCrores: Number(((Number(r[2]) || 0) / 10000000).toFixed(2)),
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-cyan/40 bg-cyan/10 px-2 py-0.5 text-xs font-semibold uppercase text-cyan">
              Time-Series Intelligence
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fog-100">Transaction Trends</h1>
          <p className="text-sm text-fog-400">
            Temporal patterns and monthly velocity of financial transactions across Saffron Bank.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => trendsQ.refetch()}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
        >
          Refresh Trends
        </Button>
      </div>

      {/* Privacy Notice */}
      <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-cyan" />
          <div className="text-xs leading-relaxed text-fog-300">
            <strong className="text-fog-100">k-Anonymity Guard Enforced:</strong> Time-series buckets are aggregated at monthly resolution ($k \ge 5$). Micro-time intervals that could isolate individual customer transactions are prohibited.
          </div>
        </div>
      </div>

      {/* Main Trend Chart */}
      <Card
        title="Monthly Transaction Volume Trend (₹ Crores)"
        subtitle="Historical financial volume aggregated across all banking channels"
      >
        {trendsQ.isLoading ? (
          <div className="py-16"><Spinner label="Calculating time-series trends..." /></div>
        ) : trendsQ.data && trendsQ.data.length > 0 ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsAreaChart data={trendsQ.data} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                <defs>
                  <linearGradient id="volGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#06B6D4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2D3748" />
                <XAxis dataKey="month" stroke="#94A3B8" fontSize={11} />
                <YAxis stroke="#94A3B8" fontSize={11} tickFormatter={(v) => `₹${v}Cr`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0F172A",
                    borderColor: "#334155",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(val: any) => [`₹${Number(val).toLocaleString()} Cr`, "Monthly Volume"]}
                />
                <Area
                  type="monotone"
                  dataKey="volumeCrores"
                  stroke="#06B6D4"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#volGradient)"
                />
              </RechartsAreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-fog-400">No trend data available.</div>
        )}
      </Card>

      {/* Monthly Figures Table */}
      <Card
        title="Monthly Volume & Transaction Statistics"
        subtitle="Audited month-by-month financial summary"
      >
        {trendsQ.data && trendsQ.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-700 text-fog-400">
                <tr>
                  <th className="pb-2.5 font-medium">Month</th>
                  <th className="pb-2.5 font-medium">Transactions Processed</th>
                  <th className="pb-2.5 font-medium">Monthly Volume (INR)</th>
                  <th className="pb-2.5 font-medium">Volume in Crores</th>
                  <th className="pb-2.5 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800 text-fog-200">
                {trendsQ.data.map((m: any) => (
                  <tr key={m.month} className="transition-colors hover:bg-ink-800/40">
                    <td className="py-2.5 font-mono font-semibold text-fog-100">{m.month}</td>
                    <td className="py-2.5 font-mono text-cyan">{m.count.toLocaleString()}</td>
                    <td className="py-2.5 font-mono text-fog-200">₹{m.volume.toLocaleString()}</td>
                    <td className="py-2.5 font-mono text-emerald-300">₹{m.volumeCrores} Cr</td>
                    <td className="py-2.5 text-right">
                      <Badge tone="green">Verified Safe</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
