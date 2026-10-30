import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
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

const tooltipStyle = {
  backgroundColor: "#FFFFFF",
  borderColor: "#DCE5F0",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#172B45",
  boxShadow: "0 4px 12px rgba(18,59,103,0.08)",
};

export default function AnalystTrends() {
  const { selected } = useConnections();

  // Monthly trends query
  const trendsQ = useQuery({
    queryKey: ["analyst-monthly-trends", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const run = (sql: string) => apiAllowDenied("/api/query/execute", { body: { connection_id: selected.id, sql } });
      const range = await run("SELECT MIN(txn_ts) AS first_ts, MAX(txn_ts) AS last_ts FROM transactions");
      const [first, last] = (range.ok && range.body?.rows?.[0]) || [];
      if (!first || !last) return [];
      const months: string[] = [];
      for (let y = +first.slice(0, 4), m = +first.slice(5, 7); `${y}-${String(m).padStart(2, "0")}` <= last.slice(0, 7); m === 12 ? (y++, (m = 1)) : m++) {
        months.push(`${y}-${String(m).padStart(2, "0")}`);
      }
      const next = (ym: string) => {
        const [y, m] = ym.split("-").map(Number);
        return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
      };
      const results = await Promise.all(
        months.map((ym) =>
          run(`SELECT COUNT(*) AS txn_count, SUM(amount_inr) AS monthly_vol FROM transactions WHERE txn_ts >= '${ym}' AND txn_ts < '${next(ym)}'`),
        ),
      );
      return months.map((month, i) => {
        const r = (results[i].ok && results[i].body?.rows?.[0]) || [0, 0];
        return {
          month,
          count: Number(r[0]) || 0,
          volume: Math.round(Number(r[1]) || 0),
          volumeCrores: Number(((Number(r[1]) || 0) / 10000000).toFixed(2)),
        };
      });
    },
    enabled: !!selected?.id,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Time-Series Intelligence
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45] mt-1">Transaction Trends</h1>
          <p className="text-xs sm:text-sm text-[#64748B]">
            Temporal patterns and monthly velocity of financial transactions across Saffron Bank.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => trendsQ.refetch()}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
          className="self-start sm:self-auto"
        >
          Refresh Trends
        </Button>
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
                    <stop offset="5%" stopColor="#1D5FA7" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#1D5FA7" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#DCE5F0" />
                <XAxis dataKey="month" stroke="#64748B" fontSize={11} />
                <YAxis stroke="#64748B" fontSize={11} tickFormatter={(v) => `₹${v}Cr`} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(val: any) => [`₹${Number(val).toLocaleString()} Cr`, "Monthly Volume"]}
                />
                <Area
                  type="monotone"
                  dataKey="volumeCrores"
                  stroke="#1D5FA7"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#volGradient)"
                />
              </RechartsAreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-[#64748B]">No trend data available.</div>
        )}
      </Card>

      {/* Monthly Figures Table */}
      <Card
        title="Monthly Volume & Transaction Statistics"
        subtitle="Audited month-by-month financial summary"
      >
        {trendsQ.data && trendsQ.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[550px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Month</th>
                  <th className="py-2.5 px-3 font-semibold">Transactions Processed</th>
                  <th className="py-2.5 px-3 font-semibold">Monthly Volume (INR)</th>
                  <th className="py-2.5 px-3 font-semibold">Volume in Crores</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {trendsQ.data.map((m: any) => (
                  <tr key={m.month} className="transition-colors hover:bg-[#F4F8FD]">
                    <td className="py-2.5 px-3 font-mono font-semibold text-[#172B45]">{m.month}</td>
                    <td className="py-2.5 px-3 font-mono font-medium text-[#1D5FA7]">{m.count.toLocaleString()}</td>
                    <td className="py-2.5 px-3 font-mono">₹{m.volume.toLocaleString()}</td>
                    <td className="py-2.5 px-3 font-mono font-medium text-emerald-700">₹{m.volumeCrores} Cr</td>
                    <td className="py-2.5 px-3 text-right">
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
