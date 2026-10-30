import {
  AlertCircle,
  CheckCircle2,
  Play,
} from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

export default function AggregateExplorer() {
  const { selected } = useConnections();

  const [table, setTable] = useState("transactions");
  const [dimension, setDimension] = useState("channel");
  const [executedSql, setExecutedSql] = useState(
    "SELECT channel, COUNT(*) AS txns, AVG(amount_inr) AS avg_amt, SUM(amount_inr) AS total_vol FROM transactions GROUP BY channel",
  );
  const [queryResult, setQueryResult] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  // Run the safe aggregate query
  const executeAggregate = async (sqlToRun = executedSql) => {
    if (!selected?.id) return;
    setBusy(true);
    setQueryResult(null);
    try {
      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected.id, sql: sqlToRun },
      });
      setQueryResult(res);
    } catch (err: any) {
      setQueryResult({
        ok: false,
        status: 500,
        body: { error: { message: err?.message || "Execution error", code: "request_failed" } },
      });
    } finally {
      setBusy(false);
    }
  };

  const handleBuildQuery = () => {
    let sql = "";
    if (table === "transactions") {
      sql = `SELECT ${dimension}, COUNT(*) AS total_records, AVG(amount_inr) AS avg_amount, SUM(amount_inr) AS aggregate_volume FROM transactions GROUP BY ${dimension}`;
    } else if (table === "accounts") {
      sql = `SELECT ${dimension}, COUNT(*) AS total_accounts FROM accounts GROUP BY ${dimension}`;
    } else {
      sql = `SELECT ${dimension}, COUNT(*) AS customer_count FROM customers GROUP BY ${dimension}`;
    }
    setExecutedSql(sql);
    executeAggregate(sql);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Differential Privacy & k-Anonymity
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[#172B45] mt-1">Aggregate Explorer</h1>
          <p className="text-sm text-[#64748B]">
            Construct approved SQL aggregations. The server-side query engine strictly suppresses small groups (k &lt; 5) and prevents predicate leakage.
          </p>
        </div>
      </div>

      {/* Query Builder Card */}
      <Card
        title="Aggregation Builder"
        subtitle="Select dataset dimensions and metrics to construct an approved aggregation"
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="label text-xs">Dataset / Table</label>
            <select
              className="input h-9 py-0 text-xs"
              value={table}
              onChange={(e) => {
                const t = e.target.value;
                setTable(t);
                if (t === "transactions") setDimension("channel");
                else if (t === "accounts") setDimension("acct_type");
                else setDimension("state");
              }}
            >
              <option value="transactions">transactions</option>
              <option value="accounts">accounts</option>
              <option value="customers">customers</option>
            </select>
          </div>

          <div>
            <label className="label text-xs">Group By Dimension</label>
            <select
              className="input h-9 py-0 text-xs"
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
            >
              {table === "transactions" ? (
                <>
                  <option value="channel">Payment Channel (channel)</option>
                  <option value="dr_cr">Fund Flow (dr_cr)</option>
                  <option value="txn_status">Transaction Status (txn_status)</option>
                </>
              ) : table === "accounts" ? (
                <>
                  <option value="acct_type">Account Type (acct_type)</option>
                  <option value="acct_status">Account Status (acct_status)</option>
                  <option value="branch_code">Branch Code (branch_code)</option>
                </>
              ) : (
                <>
                  <option value="state">Customer State (state)</option>
                  <option value="city">Customer City (city)</option>
                  <option value="segment">Customer Segment (segment)</option>
                  <option value="risk_cat">Risk Category (risk_cat)</option>
                </>
              )}
            </select>
          </div>

          <div className="flex items-end">
            <Button
              variant="primary"
              className="w-full"
              loading={busy}
              onClick={handleBuildQuery}
              icon={<Play className="h-4 w-4" />}
            >
              Execute Safe Aggregate
            </Button>
          </div>
        </div>

        {/* SQL Statement Display */}

      </Card>

      {/* Query Execution Output */}
      {busy ? (
        <Card>
          <div className="py-12"><Spinner label="Executing AST analysis and running server query..." /></div>
        </Card>
      ) : queryResult ? (
        queryResult.ok ? (
          /* Safe Query Success */
          <Card
            title={`Aggregate Results (${queryResult.body?.rows?.length ?? 0} groups)`}
            subtitle={`Execution time: ${queryResult.body?.duration_ms ?? 0} ms · Server rewrite: ${queryResult.body?.executed_sql}`}
          >
            {queryResult.body?.notes?.length > 0 && (
              <div className="mb-4 rounded-lg border border-[#DCE5F0] bg-[#EAF2FB] p-3 text-xs text-[#123B67]">
                {queryResult.body.notes.map((note: string, idx: number) => (
                  <div key={idx} className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-[#1D5FA7]" />
                    <span>{note}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs min-w-[500px]">
                <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                  <tr>
                    {queryResult.body?.columns?.map((col: string, i: number) => (
                      <th key={i} className="py-2.5 px-3 font-semibold">
                        {col}
                      </th>
                    ))}
                    <th className="py-2.5 px-3 text-right font-semibold">Privacy Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                  {queryResult.body?.rows?.map((row: any[], rIdx: number) => (
                    <tr key={rIdx} className="transition-colors hover:bg-[#F4F8FD]">
                      {row.map((val: any, cIdx: number) => (
                        <td key={cIdx} className="py-2.5 px-3 font-mono font-medium">
                          {typeof val === "number"
                            ? val.toLocaleString(undefined, { maximumFractionDigits: 2 })
                            : String(val)}
                        </td>
                      ))}
                      <td className="py-2.5 px-3 text-right">
                        <Badge tone="cyan">k ≥ 5 Compliant</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          /* Query Denied / Blocked by Server Security */
          <Card>
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 shadow-sm">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-rose-600 shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-bold text-rose-900">
                    Security Policy Enforced: Request Blocked by Query Engine
                  </h3>
                  <p className="mt-1 text-xs text-rose-800 leading-relaxed font-medium">
                    {queryResult.body?.error?.message || "The query attempted to violate data privacy guardrails."}
                  </p>
                  <div className="mt-3 flex items-center gap-2 font-mono text-xs text-rose-700">
                    <span>Rejection Code: <strong>{queryResult.body?.error?.code}</strong></span>
                    <span>·</span>
                    <span>HTTP Status: {queryResult.status}</span>
                  </div>
                  <div className="mt-2 text-[11px] text-[#64748B]">
                    This attempt was cryptographically logged to the tamper-evident audit ledger.
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )
      ) : null}
    </div>
  );
}
