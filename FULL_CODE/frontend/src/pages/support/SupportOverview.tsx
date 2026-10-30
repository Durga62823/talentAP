import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Headphones, LifeBuoy, Search, UserCheck, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, Spinner, Stat } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useConnections } from "../../lib/connections";

export default function SupportOverview() {
  const { user } = useAuth();
  const { selected } = useConnections();
  const navigate = useNavigate();
  const [quickSearch, setQuickSearch] = useState("");

  // Real KPI stats from backend
  const statsQ = useQuery({
    queryKey: ["support-overview-stats", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return null;
      const count = async (sql: string) => {
        const res = await apiAllowDenied("/api/query/execute", { body: { connection_id: selected.id, sql } });
        return res.ok && res.body?.rows?.[0] ? Number(res.body.rows[0][0]) || 0 : null;
      };
      const [customers, tickets, openTickets] = await Promise.all([
        count("SELECT COUNT(*) AS n FROM customers"),
        count("SELECT COUNT(*) AS n FROM support_tickets"),
        count("SELECT COUNT(*) AS n FROM support_tickets WHERE status = 'OPEN'"),
      ]);
      return { customers, tickets, openTickets };
    },
    enabled: !!selected?.id,
  });

  // Recent Tickets preview
  const recentTicketsQ = useQuery({
    queryKey: ["support-overview-recent-tickets", selected?.id],
    queryFn: async () => {
      if (!selected?.id) return [];
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: "SELECT ticket_id, customer_id, channel, category, priority, status, ticket_text FROM support_tickets ORDER BY ticket_id DESC LIMIT 5",
        },
      });
      if (res.ok && res.body?.rows) {
        return res.body.rows.map((r: any[]) => ({
          id: r[0],
          customerId: r[1],
          channel: r[2],
          category: r[3],
          priority: r[4],
          status: r[5],
          preview: typeof r[6] === "string" ? r[6].slice(0, 80) : r[6],
        }));
      }
      return [];
    },
    enabled: !!selected?.id,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (quickSearch.trim()) {
      navigate(`/support/lookup?q=${encodeURIComponent(quickSearch.trim())}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="flex flex-col gap-4 rounded-xl border border-[#DCE5F0] bg-white p-4 sm:p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Customer Support Workspace
            </span>
            <span className="text-xs text-[#64748B]">· Saffron Bank Ltd</span>
          </div>
          <h1 className="mt-2 text-xl sm:text-2xl font-bold tracking-tight text-[#172B45]">
            Welcome back, {user?.display_name || "Support Agent"}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-[#64748B]">
            Secure customer assistance portal. Customer PII is protected with dynamic server-side masking.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-3">
          <Link to="/support/lookup">
            <Button variant="primary" icon={<Search className="h-4 w-4" />}>
              Customer Lookup
            </Button>
          </Link>
          <Link to="/support/tickets">
            <Button variant="secondary" icon={<LifeBuoy className="h-4 w-4" />}>
              View Tickets
            </Button>
          </Link>
        </div>
      </div>

      {/* Quick Search Card */}
      <Card title="Quick Customer Lookup" subtitle="Search customers by full or partial Customer ID">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
            <input
              type="text"
              className="input pl-9 text-sm"
              placeholder="e.g. CIF-00UKL72D or UKL72"
              value={quickSearch}
              onChange={(e) => setQuickSearch(e.target.value)}
            />
          </div>
          <Button variant="primary" type="submit" icon={<ArrowRight className="h-4 w-4" />}>
            Search Customer
          </Button>
        </form>
      </Card>

      {/* Real KPI Stats */}
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Total Customers"
          value={statsQ.isLoading ? "…" : statsQ.data?.customers?.toLocaleString() ?? "—"}
          hint="Saffron Bank CIF database"
          icon={<Users className="h-4 w-4" />}
          tone="cyan"
        />
        <Stat
          label="Total Support Tickets"
          value={statsQ.isLoading ? "…" : statsQ.data?.tickets?.toLocaleString() ?? "—"}
          hint="Multi-channel customer inquiries"
          icon={<LifeBuoy className="h-4 w-4" />}
          tone="indigo"
        />
        <Stat
          label="Pending / Open Tickets"
          value={statsQ.isLoading ? "…" : statsQ.data?.openTickets?.toLocaleString() ?? "—"}
          hint="Requires triage & resolution"
          icon={<Headphones className="h-4 w-4" />}
          tone="amber"
        />
        <Stat
          label="Privacy Mode"
          value="ENFORCED"
          hint="Dynamic partial masking"
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone="green"
        />
      </div>

      {/* Recent Support Tickets Table */}
      <Card
        title="Recent Customer Support Tickets"
        subtitle="Latest customer cases across UPI, Card, Net Banking, and Branch channels"
        actions={
          <Link to="/support/tickets" className="text-xs font-semibold text-[#1D5FA7] hover:underline">
            View all tickets →
          </Link>
        }
      >
        {recentTicketsQ.isLoading ? (
          <div className="py-8">
            <Spinner label="Loading tickets from Saffron Bank..." />
          </div>
        ) : recentTicketsQ.data && recentTicketsQ.data.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Ticket ID</th>
                  <th className="py-2.5 px-3 font-semibold">Customer ID</th>
                  <th className="py-2.5 px-3 font-semibold">Category</th>
                  <th className="py-2.5 px-3 font-semibold">Channel</th>
                  <th className="py-2.5 px-3 font-semibold">Priority</th>
                  <th className="py-2.5 px-3 font-semibold">Status</th>
                  <th className="py-2.5 px-3 font-semibold">Preview</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {recentTicketsQ.data.map((t: any) => (
                  <tr key={t.id} className="transition-colors hover:bg-[#F4F8FD]">
                    <td className="py-2.5 px-3 font-mono font-medium text-[#123B67]">{t.id}</td>
                    <td className="py-2.5 px-3 font-mono">
                      <Link
                        to={`/support/profiles?id=${encodeURIComponent(t.customerId)}`}
                        className="text-[#1D5FA7] font-semibold hover:underline"
                      >
                        {t.customerId}
                      </Link>
                    </td>
                    <td className="py-2.5 px-3 font-medium">{t.category}</td>
                    <td className="py-2.5 px-3 text-[#64748B]">{t.channel}</td>
                    <td className="py-2.5 px-3">
                      <Badge
                        tone={
                          t.priority === "HIGH"
                            ? "red"
                            : t.priority === "MEDIUM"
                              ? "amber"
                              : "neutral"
                        }
                      >
                        {t.priority}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge
                        tone={
                          t.status === "OPEN"
                            ? "amber"
                            : t.status === "RESOLVED" || t.status === "CLOSED"
                              ? "green"
                              : "cyan"
                        }
                      >
                        {t.status}
                      </Badge>
                    </td>
                    <td className="max-w-[280px] truncate py-2.5 px-3 text-[#64748B]" title={t.preview}>
                      {t.preview}…
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => navigate(`/support/profiles?id=${encodeURIComponent(t.customerId)}`)}
                      >
                        View Profile
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-6 text-center text-xs text-[#64748B]">
            No tickets found in the selected connection.
          </div>
        )}
      </Card>

      {/* Navigation Quick Links */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Link
          to="/support/lookup"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <Search className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">Customer Lookup</div>
              <div className="text-xs text-[#64748B]">Search customer records by Customer ID</div>
            </div>
          </div>
        </Link>

        <Link
          to="/support/tickets"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <LifeBuoy className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">Support Tickets</div>
              <div className="text-xs text-[#64748B]">Browse and triage 3,000 customer inquiries</div>
            </div>
          </div>
        </Link>

        <Link
          to="/support/activity"
          className="group rounded-xl border border-[#DCE5F0] bg-white p-5 transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7] group-hover:bg-[#1D5FA7] group-hover:text-white transition-colors">
              <UserCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#172B45]">My Activity Log</div>
              <div className="text-xs text-[#64748B]">Review your authenticated lookup history</div>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
