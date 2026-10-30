import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
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

export default function AnalystAnalytics() {
  const { selected } = useConnections();

  // Channel volume & count query
  const channelDataQ = useQuery({
    queryKey: ["analyst-analytics-channels", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT channel, COUNT(*) AS txn_count, SUM(amount_inr) AS total_vol, AVG(amount_inr) AS avg_amt FROM transactions GROUP BY channel ORDER BY total_vol DESC",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          channel: r[0],
          count: Number(r[1]) || 0,
          volume: Math.round(Number(r[2]) || 0),
          volumeLakhs: Number(((Number(r[2]) || 0) / 100000).toFixed(2)),
          avgAmount: Math.round(Number(r[3]) || 0),
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  // Transaction status breakdown (Success vs Failed)
  const statusDataQ = useQuery({
    queryKey: ["analyst-analytics-status", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT txn_status, COUNT(*) AS cnt, SUM(amount_inr) AS vol FROM transactions GROUP BY txn_status",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          status: r[0],
          count: Number(r[1]) || 0,
          volume: Math.round(Number(r[2]) || 0),
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  // Debit vs Credit breakdown
  const drcrDataQ = useQuery({
    queryKey: ["analyst-analytics-drcr", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT dr_cr, COUNT(*) AS cnt, SUM(amount_inr) AS vol FROM transactions GROUP BY dr_cr",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          type: r[0] === "DR" ? "Debit" : "Credit",
          count: Number(r[1]) || 0,
          volume: Math.round(Number(r[2]) || 0),
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Transaction Intelligence
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45] mt-1">Analytics Dashboard</h1>
          <p className="text-xs sm:text-sm text-[#64748B]">
            Privacy-preserving aggregations across 100,000 transactions. Zero individual identities exposed.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            channelDataQ.refetch();
            statusDataQ.refetch();
            drcrDataQ.refetch();
          }}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
          className="self-start sm:self-auto"
        >
          Refresh Figures
        </Button>
      </div>

      {/* Primary Chart: Channel Volume (Bar Chart) */}
      <Card
        title="Transaction Volume by Channel (₹ Lakhs)"
        subtitle="Total settled volume across Saffron Bank payment rails"
      >
        {channelDataQ.isLoading ? (
          <div className="py-16"><Spinner label="Aggregating channel volume..." /></div>
        ) : channelDataQ.data && channelDataQ.data.length > 0 ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={channelDataQ.data} margin={{ top: 10, right: 10, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#DCE5F0" />
                <XAxis
                  dataKey="channel"
                  stroke="#64748B"
                  fontSize={11}
                  angle={-20}
                  textAnchor="end"
                />
                <YAxis stroke="#64748B" fontSize={11} tickFormatter={(v) => `₹${v}L`} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: any) => [`₹${Number(value).toLocaleString()} Lakhs`, "Volume"]}
                />
                <Bar dataKey="volumeLakhs" fill="#1D5FA7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-[#64748B]">No channel data available.</div>
        )}
      </Card>

      {/* Secondary Charts: Status & DR/CR breakdown */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Status Pie Chart */}
        <Card
          title="Transaction Success vs Failure"
          subtitle="System-wide completion rate across channels"
        >
          {statusDataQ.isLoading ? (
            <div className="py-12"><Spinner label="Calculating status distribution..." /></div>
          ) : statusDataQ.data && statusDataQ.data.length > 0 ? (
            <div className="flex flex-col items-center sm:flex-row sm:justify-around gap-4 py-2">
              <div className="h-52 w-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={statusDataQ.data}
                      dataKey="count"
                      nameKey="status"
                      cx="50%"
                      cy="50%"
                      outerRadius={75}
                      innerRadius={45}
                    >
                      {statusDataQ.data.map((entry: any, index: number) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.status === "SUCCESS" ? "#10B981" : "#E11D48"}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(val: any) => [Number(val).toLocaleString(), "Count"]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-3 text-xs">
                {statusDataQ.data.map((item: any) => (
                  <div key={item.status} className="flex items-center gap-3">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: item.status === "SUCCESS" ? "#10B981" : "#E11D48" }}
                    />
                    <div>
                      <div className="font-semibold text-[#172B45]">{item.status}</div>
                      <div className="text-[#64748B]">
                        {item.count.toLocaleString()} txns (₹{(item.volume / 10000000).toFixed(2)} Cr)
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-6 text-center text-xs text-[#64748B]">No status data available.</div>
          )}
        </Card>

        {/* Debit vs Credit Ratio */}
        <Card
          title="Debit vs Credit Distribution"
          subtitle="Fund flow direction across core accounts"
        >
          {drcrDataQ.isLoading ? (
            <div className="py-12"><Spinner label="Calculating fund flow..." /></div>
          ) : drcrDataQ.data && drcrDataQ.data.length > 0 ? (
            <div className="flex flex-col items-center sm:flex-row sm:justify-around gap-4 py-2">
              <div className="h-52 w-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={drcrDataQ.data}
                      dataKey="count"
                      nameKey="type"
                      cx="50%"
                      cy="50%"
                      outerRadius={75}
                      innerRadius={45}
                    >
                      {drcrDataQ.data.map((_: any, index: number) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={index === 0 ? "#123B67" : "#3478C8"}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(val: any) => [Number(val).toLocaleString(), "Count"]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-3 text-xs">
                {drcrDataQ.data.map((item: any, i: number) => (
                  <div key={item.type} className="flex items-center gap-3">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: i === 0 ? "#123B67" : "#3478C8" }}
                    />
                    <div>
                      <div className="font-semibold text-[#172B45]">{item.type}</div>
                      <div className="text-[#64748B]">
                        {item.count.toLocaleString()} txns (₹{(item.volume / 10000000).toFixed(2)} Cr)
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-6 text-center text-xs text-[#64748B]">No DR/CR data available.</div>
          )}
        </Card>
      </div>

      {/* Aggregate Table */}
      <Card
        title="Channel Breakdown Summary Table"
        subtitle="Audited aggregate metrics for all payment rails"
      >
        {channelDataQ.data && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[550px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Payment Rail / Channel</th>
                  <th className="py-2.5 px-3 font-semibold">Transaction Count</th>
                  <th className="py-2.5 px-3 font-semibold">Total Volume (INR)</th>
                  <th className="py-2.5 px-3 font-semibold">Average Ticket Size</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Privacy Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {channelDataQ.data.map((c: any) => (
                  <tr key={c.channel} className="transition-colors hover:bg-[#F4F8FD]">
                    <td className="py-2.5 px-3 font-semibold text-[#172B45]">{c.channel}</td>
                    <td className="py-2.5 px-3 font-mono font-medium text-[#1D5FA7]">{c.count.toLocaleString()}</td>
                    <td className="py-2.5 px-3 font-mono">₹{c.volume.toLocaleString()}</td>
                    <td className="py-2.5 px-3 font-mono font-medium text-emerald-700">₹{c.avgAmount.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right">
                      <Badge tone="cyan">k ≥ 5 Enforced</Badge>
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
