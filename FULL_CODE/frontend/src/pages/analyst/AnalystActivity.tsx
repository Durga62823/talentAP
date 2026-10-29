import { useQuery } from "@tanstack/react-query";
import { History, RefreshCw, Shield } from "lucide-react";
import { Button, Card, OutcomeBadge, Spinner } from "../../components/ui";
import { api, fmtTime } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export default function AnalystActivity() {
  const { user } = useAuth();

  const activityQ = useQuery({
    queryKey: ["analyst-self-activity"],
    queryFn: async () => {
      const res = await api<{ total: number; events: any[] }>("/api/audit/self?limit=50");
      return res;
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-cyan/40 bg-cyan/10 px-2 py-0.5 text-xs font-semibold uppercase text-cyan">
              Accountability & Audit
            </span>
            <span className="text-xs text-fog-400">· Principal: {user?.username}</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fog-100">My Analytics Activity</h1>
          <p className="text-sm text-fog-400">
            Audit history of your analytics requests, aggregate evaluations, and any rejected inference attempts.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => activityQ.refetch()}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
        >
          Refresh Log
        </Button>
      </div>

      {/* Security Privacy Notice */}
      <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
        <div className="flex items-start gap-3">
          <Shield className="h-5 w-5 shrink-0 text-cyan mt-0.5" />
          <div className="text-xs leading-relaxed text-fog-300">
            <strong className="text-fog-100">Isolated Audit Ledger:</strong> This view displays solely the operations executed by your authenticated session (<code>{user?.username}</code>). All queries and security enforcement decisions are cryptographically recorded in the SHA-256 tamper-evident audit log.
          </div>
        </div>
      </div>

      {/* Activity Table Card */}
      <Card
        title={`Audit Trail (${activityQ.data?.total ?? 0} total events)`}
        subtitle="Chronological list of analytical requests and policy outcomes"
      >
        {activityQ.isLoading ? (
          <div className="py-12">
            <Spinner label="Loading your activity trail..." />
          </div>
        ) : activityQ.data?.events && activityQ.data.events.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-700 text-fog-400">
                <tr>
                  <th className="pb-2.5 font-medium">Timestamp</th>
                  <th className="pb-2.5 font-medium">Action</th>
                  <th className="pb-2.5 font-medium">Outcome</th>
                  <th className="pb-2.5 font-medium">Tables Accessed</th>
                  <th className="pb-2.5 font-medium">Execution Duration</th>
                  <th className="pb-2.5 font-medium">Security Detail / Reason</th>
                  <th className="pb-2.5 text-right font-medium">Audit Seq</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800 text-fog-200">
                {activityQ.data.events.map((e) => (
                  <tr key={e.id} className="transition-colors hover:bg-ink-800/40">
                    <td className="whitespace-nowrap py-3 font-mono text-fog-300">
                      {fmtTime(e.ts)}
                    </td>
                    <td className="py-3 font-medium text-fog-100">
                      <div className="flex items-center gap-1.5">
                        <History className="h-3.5 w-3.5 text-cyan" />
                        {e.action}
                      </div>
                    </td>
                    <td className="py-3">
                      <OutcomeBadge outcome={e.outcome} />
                    </td>
                    <td className="py-3">
                      {e.tables && e.tables.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {e.tables.map((t: string) => (
                            <span
                              key={t}
                              className="rounded border border-ink-600 bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-cyan"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-fog-500">—</span>
                      )}
                    </td>
                    <td className="py-3 font-mono text-fog-400">
                      {e.duration_ms !== null && e.duration_ms !== undefined
                        ? `${Math.round(e.duration_ms)} ms`
                        : "—"}
                    </td>
                    <td className="max-w-[280px] truncate py-3 text-fog-400" title={e.reason || "Authorized query"}>
                      {e.reason || "Authorized query"}
                    </td>
                    <td className="py-3 text-right font-mono text-fog-500">
                      #{e.seq}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-fog-400">
            No activity recorded for this analyst session yet. Run queries or explore charts to record events.
          </div>
        )}
      </Card>
    </div>
  );
}
