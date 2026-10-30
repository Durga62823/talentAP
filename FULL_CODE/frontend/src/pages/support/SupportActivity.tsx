import { useQuery } from "@tanstack/react-query";
import { History, RefreshCw } from "lucide-react";
import { Button, Card, OutcomeBadge, Spinner } from "../../components/ui";
import { api, fmtTime } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export default function SupportActivity() {
  const { user } = useAuth();

  const activityQ = useQuery({
    queryKey: ["support-self-activity"],
    queryFn: async () => {
      const res = await api<{ total: number; events: any[] }>("/api/audit/self?limit=50");
      return res;
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Audit & Accountability
            </span>
            <span className="text-xs text-[#64748B]">· Principal: @{user?.username}</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45] mt-1">My Support Activity</h1>
          <p className="text-xs sm:text-sm text-[#64748B]">
            Audit history of your customer lookups, profile visits, and query outcomes.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => activityQ.refetch()}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
          className="self-start sm:self-auto"
        >
          Refresh Log
        </Button>
      </div>



      {/* Activity Table Card */}
      <Card
        title={`Audit Events (${activityQ.data?.total ?? 0} total recorded)`}
        subtitle="Chronological trail of lookups and outcomes"
      >
        {activityQ.isLoading ? (
          <div className="py-12">
            <Spinner label="Loading your audit trail..." />
          </div>
        ) : activityQ.data?.events && activityQ.data.events.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Timestamp</th>
                  <th className="py-2.5 px-3 font-semibold">Action</th>
                  <th className="py-2.5 px-3 font-semibold">Outcome</th>
                  <th className="py-2.5 px-3 font-semibold">Tables Queried</th>
                  <th className="py-2.5 px-3 font-semibold">Duration</th>
                  <th className="py-2.5 px-3 font-semibold">Reason / Details</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Audit Seq</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {activityQ.data.events.map((e) => (
                  <tr key={e.id} className="transition-colors hover:bg-[#F4F8FD]">
                    <td className="whitespace-nowrap py-3 px-3 font-mono text-[#64748B]">
                      {fmtTime(e.ts)}
                    </td>
                    <td className="py-3 px-3 font-semibold text-[#172B45]">
                      <div className="flex items-center gap-1.5">
                        <History className="h-3.5 w-3.5 text-[#1D5FA7]" />
                        {e.action}
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <OutcomeBadge outcome={e.outcome} />
                    </td>
                    <td className="py-3 px-3">
                      {e.tables && e.tables.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {e.tables.map((t: string) => (
                            <span
                              key={t}
                              className="rounded border border-[#DCE5F0] bg-[#EAF2FB] px-1.5 py-0.5 font-mono text-[10px] text-[#123B67] font-medium"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[#64748B]">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 font-mono text-[#64748B]">
                      {e.duration_ms !== null && e.duration_ms !== undefined
                        ? `${Math.round(e.duration_ms)} ms`
                        : "—"}
                    </td>
                    <td className="max-w-[240px] truncate py-3 px-3 text-[#64748B]" title={e.reason || "Authorized request"}>
                      {e.reason || "Authorized request"}
                    </td>
                    <td className="py-3 px-3 text-right font-mono font-medium text-[#123B67]">
                      #{e.seq}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-[#64748B]">
            No audit events found for your account yet. Perform customer lookups to record activity.
          </div>
        )}
      </Card>
    </div>
  );
}
