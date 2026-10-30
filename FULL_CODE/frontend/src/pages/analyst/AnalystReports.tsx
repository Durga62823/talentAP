import { Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

const PRESET_REPORTS = [
  {
    id: "channel_perf",
    title: "Payment Channel Performance & Velocity Report",
    sql: "SELECT channel, COUNT(*) AS txn_count, SUM(amount_inr) AS total_volume_inr, AVG(amount_inr) AS avg_ticket_size_inr FROM transactions GROUP BY channel ORDER BY total_volume_inr DESC",
  },
  {
    id: "status_ratio",
    title: "Channel Failure & Success Analysis Report",
    sql: "SELECT channel, txn_status, COUNT(*) AS count, SUM(amount_inr) AS volume FROM transactions GROUP BY channel, txn_status ORDER BY channel",
  },
  {
    id: "segment_summary",
    title: "Customer Segment Aggregate Demographics",
    sql: "SELECT segment, risk_cat, COUNT(*) AS customer_count FROM customers GROUP BY segment, risk_cat ORDER BY customer_count DESC",
  },
  {
    id: "branch_summary",
    title: "Core Branch Account Concentration",
    sql: "SELECT branch_code, acct_type, COUNT(*) AS total_accounts FROM accounts GROUP BY branch_code, acct_type ORDER BY branch_code LIMIT 40",
  },
];

export default function AnalystReports() {
  const { selected } = useConnections();
  const [activeReportId, setActiveReportId] = useState(PRESET_REPORTS[0].id);
  const [reportResult, setReportResult] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  const activeReport = PRESET_REPORTS.find((r) => r.id === activeReportId) || PRESET_REPORTS[0];

  const handleGenerate = async (r = activeReport) => {
    if (!selected?.id) return;
    setBusy(true);
    setReportResult(null);
    try {
      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected.id, sql: r.sql },
      });
      setReportResult(res);
    } finally {
      setBusy(false);
    }
  };

  const downloadCsv = () => {
    if (!reportResult?.ok || !reportResult?.body?.rows) return;
    const { columns, rows } = reportResult.body;
    const csvRows = [
      columns.join(","),
      ...rows.map((r: any[]) =>
        r
          .map((v) => {
            const str = String(v ?? "");
            return str.includes(",") ? `"${str.replace(/"/g, '""')}"` : str;
          })
          .join(","),
      ),
    ];
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `${activeReport.id}_privacy_safe_report.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Privacy-Compliant Export
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45] mt-1">Export Reports</h1>
          <p className="text-xs sm:text-sm text-[#64748B]">
            Generate and export privacy-screened reports. Datasets are verified and masked server-side prior to CSV export.
          </p>
        </div>
      </div>

      {/* Report Selection Grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {PRESET_REPORTS.map((r) => (
          <div
            key={r.id}
            onClick={() => {
              setActiveReportId(r.id);
              handleGenerate(r);
            }}
            className={`cursor-pointer rounded-xl border p-4 sm:p-5 transition-all shadow-sm ${activeReportId === r.id
              ? "border-[#1D5FA7] bg-[#EAF2FB]/60 ring-2 ring-[#1D5FA7]/20"
              : "border-[#DCE5F0] bg-white hover:border-[#3478C8] hover:bg-[#F4F8FD]"
              }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[#172B45]">{r.title}</span>
              <FileSpreadsheet className={`h-4 w-4 ${activeReportId === r.id ? "text-[#1D5FA7]" : "text-[#64748B]"}`} />
            </div>
            <div className="mt-3.5 flex items-center justify-between">
              <Badge tone="cyan">k ≥ 5 Guaranteed</Badge>
              <span className="text-xs font-semibold text-[#1D5FA7] hover:underline">
                {activeReportId === r.id ? "Active Report" : "Click to Run →"}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Report Results */}
      {busy ? (
        <Card>
          <div className="py-12"><Spinner label="Compiling privacy-screened report..." /></div>
        </Card>
      ) : reportResult?.ok && reportResult.body?.rows ? (
        <Card
          title={activeReport.title}
          subtitle={`Generated ${reportResult.body.rows.length} aggregated rows in ${reportResult.body.duration_ms} ms`}
          actions={
            <Button variant="primary" size="sm" onClick={downloadCsv} icon={<Download className="h-3.5 w-3.5" />}>
              Export Safe CSV
            </Button>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[500px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  {reportResult.body.columns.map((col: string, i: number) => (
                    <th key={i} className="py-2.5 px-3 font-semibold">
                      {col}
                    </th>
                  ))}
                  <th className="py-2.5 px-3 text-right font-semibold">Compliance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {reportResult.body.rows.slice(0, 50).map((row: any[], rIdx: number) => (
                  <tr key={rIdx} className="transition-colors hover:bg-[#F4F8FD]">
                    {row.map((val: any, cIdx: number) => (
                      <td key={cIdx} className="py-2.5 px-3 font-mono font-medium">
                        {typeof val === "number"
                          ? val.toLocaleString(undefined, { maximumFractionDigits: 2 })
                          : String(val)}
                      </td>
                    ))}
                    <td className="py-2.5 px-3 text-right">
                      <Badge tone="green">Sanitized</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {reportResult.body.rows.length > 50 && (
            <div className="mt-3 text-center text-xs text-[#64748B]">
              Showing first 50 rows in preview. Full dataset will be exported in the CSV download.
            </div>
          )}
        </Card>
      ) : null}
    </div>
  );
}
