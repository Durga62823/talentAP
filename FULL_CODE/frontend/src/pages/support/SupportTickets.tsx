import { useQuery } from "@tanstack/react-query";
import {
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

export default function SupportTickets() {
  const { selected } = useConnections();
  const [category, setCategory] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [priority, setPriority] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedTicket, setSelectedTicket] = useState<any | null>(null);

  const ticketsQ = useQuery({
    queryKey: ["support-tickets-list", selected?.id, category, status, priority, searchTerm],
    queryFn: async () => {
      if (!selected?.id) return null;

      const conditions: string[] = [];
      if (category !== "ALL") conditions.push(`category = '${category.replace(/['"\\]/g, "")}'`);
      if (status !== "ALL") conditions.push(`status = '${status.replace(/['"\\]/g, "")}'`);
      if (priority !== "ALL") conditions.push(`priority = '${priority.replace(/['"\\]/g, "")}'`);
      if (searchTerm.trim()) {
        const clean = searchTerm.trim().replace(/['"\\]/g, "");
        conditions.push(`(ticket_id LIKE '%${clean}%' OR customer_id LIKE '%${clean}%' OR ticket_text LIKE '%${clean}%')`);
      }

      const whereClause = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
      const sql = `SELECT ticket_id, customer_id, channel, category, priority, status, created_ts, ticket_text, notes, assigned_to FROM support_tickets ${whereClause} ORDER BY created_ts DESC LIMIT 50`;

      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected.id, sql },
      });

      return res;
    },
    enabled: !!selected?.id,
  });

  const categories = [
    "ALL",
    "Branch Service",
    "Card - Lost/Stolen",
    "Fraud Report",
    "UPI - Failed Transaction",
    "KYC - Update",
    "Net Banking/App",
    "ATM - Cash Not Dispensed",
    "Credit Card - Dispute",
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Customer Operations
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[#172B45] mt-1">Support Tickets Center</h1>
          <p className="text-sm text-[#64748B]">
            Triage and resolve customer tickets across Saffron Bank channels (3,000 cases).
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => ticketsQ.refetch()}
          icon={<RefreshCw className="h-3.5 w-3.5" />}
        >
          Refresh Cases
        </Button>
      </div>

      {/* Filter Bar */}
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label text-xs">Search Ticket or Customer</label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#64748B]" />
              <input
                type="text"
                className="input h-9 pl-8 text-xs"
                placeholder="TKT-... or CIF-..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="label text-xs">Category</label>
            <select
              className="input h-9 py-0 text-xs"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label text-xs">Status</label>
            <select
              className="input h-9 py-0 text-xs"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="IN PROGRESS">In Progress</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>

          <div>
            <label className="label text-xs">Priority</label>
            <select
              className="input h-9 py-0 text-xs"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="ALL">All Priorities</option>
              <option value="HIGH">High Priority</option>
              <option value="MEDIUM">Medium Priority</option>
              <option value="LOW">Low Priority</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Tickets Table */}
      {ticketsQ.isLoading ? (
        <Card>
          <div className="py-12">
            <Spinner label="Loading support tickets from Saffron Bank..." />
          </div>
        </Card>
      ) : ticketsQ.data?.ok && ticketsQ.data?.body?.rows ? (
        <Card
          title={`Tickets (${ticketsQ.data.body.rows.length} cases)`}
          subtitle="Showing latest cases matching your filters. Free-text PII is sanitized server-side."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[750px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Ticket ID</th>
                  <th className="py-2.5 px-3 font-semibold">Customer ID</th>
                  <th className="py-2.5 px-3 font-semibold">Category</th>
                  <th className="py-2.5 px-3 font-semibold">Channel</th>
                  <th className="py-2.5 px-3 font-semibold">Priority</th>
                  <th className="py-2.5 px-3 font-semibold">Status</th>
                  <th className="py-2.5 px-3 font-semibold">Subject / Inquiry</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {ticketsQ.data.body.rows.map((row: any[]) => {
                  const [tktId, cif, chan, cat, pri, st, created, text, notes, assigned] = row;
                  return (
                    <tr key={tktId} className="transition-colors hover:bg-[#F4F8FD]">
                      <td className="py-2.5 px-3 font-mono font-semibold text-[#123B67]">{tktId}</td>
                      <td className="py-2.5 px-3 font-mono font-medium">
                        <Link to={`/support/profiles?id=${encodeURIComponent(cif)}`} className="text-[#1D5FA7] hover:underline">
                          {cif}
                        </Link>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-[#172B45]">{cat}</td>
                      <td className="py-2.5 px-3 text-[#64748B]">{chan}</td>
                      <td className="py-2.5 px-3">
                        <Badge
                          tone={pri === "HIGH" ? "red" : pri === "MEDIUM" ? "amber" : "neutral"}
                        >
                          {pri}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3">
                        <Badge
                          tone={
                            st === "OPEN"
                              ? "amber"
                              : st === "RESOLVED" || st === "CLOSED"
                              ? "green"
                              : "cyan"
                          }
                        >
                          {st}
                        </Badge>
                      </td>
                      <td className="max-w-[260px] truncate py-2.5 px-3 text-[#64748B]" title={text}>
                        {text}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setSelectedTicket({
                              id: tktId,
                              cif,
                              channel: chan,
                              category: cat,
                              priority: pri,
                              status: st,
                              created,
                              text,
                              notes,
                              assigned,
                            })
                          }
                        >
                          Details
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <Card>
          <div className="py-8 text-center text-xs text-[#64748B]">
            {ticketsQ.data?.body?.error?.message || "No tickets found matching the specified filters."}
          </div>
        </Card>
      )}

      {/* Ticket Details Modal */}
      {selectedTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="card w-full max-w-lg animate-fadein bg-white border border-[#DCE5F0] rounded-xl p-6 shadow-modal">
            <div className="flex items-start justify-between border-b border-[#DCE5F0] pb-3.5">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-base font-bold text-[#123B67]">
                    {selectedTicket.id}
                  </span>
                  <Badge tone={selectedTicket.status === "OPEN" ? "amber" : "green"}>
                    {selectedTicket.status}
                  </Badge>
                  <Badge tone={selectedTicket.priority === "HIGH" ? "red" : "neutral"}>
                    {selectedTicket.priority} Priority
                  </Badge>
                </div>
                <div className="mt-1 text-xs text-[#64748B]">
                  Channel: {selectedTicket.channel} · Category: {selectedTicket.category}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedTicket(null)}
                className="rounded-lg p-1 text-[#64748B] hover:bg-[#EAF2FB] hover:text-[#123B67] transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div className="flex items-center justify-between rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
                <span className="text-[#64748B] font-medium">Associated Customer</span>
                <Link
                  to={`/support/profiles?id=${encodeURIComponent(selectedTicket.cif)}`}
                  className="font-mono font-semibold text-[#1D5FA7] hover:underline"
                >
                  {selectedTicket.cif} → Open Profile
                </Link>
              </div>

              <div>
                <label className="font-semibold text-[#172B45]">Customer Issue Description</label>
                <div className="mt-1.5 rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3 leading-relaxed text-[#172B45]">
                  {selectedTicket.text}
                </div>
              </div>

              {selectedTicket.notes && (
                <div>
                  <label className="font-semibold text-[#172B45]">Internal Agent Notes</label>
                  <div className="mt-1.5 rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3 text-[#64748B]">
                    {selectedTicket.notes}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2 text-[11px] text-emerald-700 font-medium">
                <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600" />
                <span>Masking policy active: Sensitive customer account identifiers are redacted or masked.</span>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2 border-t border-[#DCE5F0] pt-3">
              <Button variant="secondary" size="sm" onClick={() => setSelectedTicket(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
