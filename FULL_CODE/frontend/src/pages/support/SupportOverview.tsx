import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Headphones, LifeBuoy, Search, Shield, UserCheck, Users } from "lucide-react";
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
      // Sub-queries are rejected by the SQL guard, so each count is its own query (run in parallel).
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
      <div className="flex flex-col gap-4 rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-ink-900/40 to-ink-900/80 p-6 backdrop-blur md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-xs font-semibold uppercase text-amber-300">
              Customer Support Workspace
            </span>
            <span className="text-xs text-fog-400">· Saffron Bank Ltd</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-fog-100">
            Welcome back, {user?.display_name || "Support Agent"}
          </h1>
          <p className="mt-1 text-sm text-fog-300">
            Secure customer assistance portal. Customer PII is protected with dynamic server-side masking.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
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

      {/* Privacy Policy Guardrail Notice */}
      <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
        <div className="flex items-start gap-3">
          <Shield className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <div className="text-xs leading-relaxed text-fog-300">
            <strong className="font-semibold text-fog-100">Support Privacy Protections Active:</strong> As an authorized Support agent, customer contact identifiers (phone, email, postal address) and credit cards (<code>4111-XXXX-XXXX-1111</code>) are partially masked for customer verification. Running account balances are <span className="text-rose-300">REDACTED</span> and unauthorized tables (e.g. loan applications) are <span className="text-rose-300">BLOCKED</span>. Server-side masking cannot be bypassed.
          </div>
        </div>
      </div>

      {/* Quick Search Card */}
      <Card title="Quick Customer Lookup" subtitle="Search customers by full or partial Customer ID">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-fog-500" />
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

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-fog-400">
          <span className="font-medium text-fog-300">Sample Customers:</span>
          {["CIF-00UKL72D", "CIF-007IS5OP", "CIF-0080J9GL", "CIF-007KK65R", "CIF-UGZKM7GD"].map((cif) => (
            <button
              key={cif}
              type="button"
              onClick={() => navigate(`/support/lookup?q=${encodeURIComponent(cif)}`)}
              className="rounded border border-ink-600 bg-ink-800 px-2 py-0.5 font-mono text-[11px] text-amber-200 transition-colors hover:border-amber-400 hover:bg-ink-700"
            >
              {cif}
            </button>
          ))}
        </div>
      </Card>

      {/* Real KPI Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <Link to="/support/tickets" className="text-xs text-amber-400 hover:underline">
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
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-700 text-fog-400">
                <tr>
                  <th className="pb-2 font-medium">Ticket ID</th>
                  <th className="pb-2 font-medium">Customer ID</th>
                  <th className="pb-2 font-medium">Category</th>
                  <th className="pb-2 font-medium">Channel</th>
                  <th className="pb-2 font-medium">Priority</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Preview</th>
                  <th className="pb-2 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800 text-fog-200">
                {recentTicketsQ.data.map((t: any) => (
                  <tr key={t.id} className="transition-colors hover:bg-ink-800/40">
                    <td className="py-2.5 font-mono text-amber-200">{t.id}</td>
                    <td className="py-2.5 font-mono text-fog-300">
                      <Link
                        to={`/support/profiles?id=${encodeURIComponent(t.customerId)}`}
                        className="text-cyan hover:underline"
                      >
                        {t.customerId}
                      </Link>
                    </td>
                    <td className="py-2.5 font-medium">{t.category}</td>
                    <td className="py-2.5 text-fog-400">{t.channel}</td>
                    <td className="py-2.5">
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
                    <td className="py-2.5">
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
                    <td className="max-w-[280px] truncate py-2.5 text-fog-400" title={t.preview}>
                      {t.preview}…
                    </td>
                    <td className="py-2.5 text-right">
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
          <div className="py-6 text-center text-xs text-fog-400">
            No tickets found in the selected connection.
          </div>
        )}
      </Card>

      {/* Navigation Quick Links */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Link
          to="/support/lookup"
          className="group rounded-xl border border-ink-700 bg-ink-900/60 p-5 transition-all hover:border-amber-400/50 hover:bg-ink-800/50"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-amber-400/10 text-amber-300 group-hover:bg-amber-400/20">
              <Search className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-fog-100">Customer Lookup</div>
              <div className="text-xs text-fog-400">Search customer records by Customer ID</div>
            </div>
          </div>
        </Link>

        <Link
          to="/support/tickets"
          className="group rounded-xl border border-ink-700 bg-ink-900/60 p-5 transition-all hover:border-amber-400/50 hover:bg-ink-800/50"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-cyan/10 text-cyan group-hover:bg-cyan/20">
              <LifeBuoy className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-fog-100">Support Tickets</div>
              <div className="text-xs text-fog-400">Browse and triage 3,000 customer inquiries</div>
            </div>
          </div>
        </Link>

        <Link
          to="/support/activity"
          className="group rounded-xl border border-ink-700 bg-ink-900/60 p-5 transition-all hover:border-amber-400/50 hover:bg-ink-800/50"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-emerald-400/10 text-emerald-300 group-hover:bg-emerald-400/20">
              <UserCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-fog-100">My Activity Log</div>
              <div className="text-xs text-fog-400">Review your authenticated lookup history</div>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
