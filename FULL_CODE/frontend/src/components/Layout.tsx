import clsx from "clsx";
import {
  Activity,
  BarChart3,
  Database,
  FileSpreadsheet,
  Fingerprint,
  History,
  Layers,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Radar,
  ScrollText,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  TerminalSquare,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { getRoleHome, useAuth } from "../lib/auth";
import { KIND_LABEL, useConnections } from "../lib/connections";

export type NavItem = {
  to: string;
  label: string;
  icon: any;
  end?: boolean;
};

export const ADMIN_NAV: NavItem[] = [
  { to: "/admin/overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "User Management", icon: Users },
  { to: "/admin/discovery", label: "Data Discovery", icon: Radar },
  { to: "/admin/policies", label: "Masking Policies", icon: SlidersHorizontal },
  { to: "/admin/connections", label: "Database & Tables", icon: Database },
  { to: "/admin/audit", label: "Audit Center", icon: ScrollText },
  { to: "/admin/integrity", label: "Integrity Verification", icon: Fingerprint },
  { to: "/admin/settings", label: "Settings", icon: Settings },
];

export const SUPPORT_NAV: NavItem[] = [
  { to: "/support/overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/support/lookup", label: "Customer Lookup", icon: Search },
  { to: "/support/profiles", label: "Customer Profiles", icon: UserCheck },
  { to: "/support/tickets", label: "Support Tickets", icon: LifeBuoy },
  { to: "/support/activity", label: "Recent Activity", icon: History },
];

export const ANALYST_NAV: NavItem[] = [
  { to: "/analyst/overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/analyst/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/analyst/trends", label: "Transaction Trends", icon: TrendingUp },
  { to: "/analyst/explorer", label: "Aggregate Explorer", icon: Layers },
  { to: "/analyst/reports", label: "Reports", icon: FileSpreadsheet },
  { to: "/analyst/activity", label: "My Activity", icon: History },
];

export const COMPLIANCE_NAV: NavItem[] = [
  { to: "/admin/overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/discovery", label: "Data Discovery", icon: Radar },
  { to: "/admin/policies", label: "Masking Policies", icon: SlidersHorizontal },
  { to: "/admin/audit", label: "Audit Center", icon: ScrollText },
  { to: "/admin/integrity", label: "Integrity Verification", icon: Fingerprint },
];

const ROLE_TONE: Record<string, string> = {
  admin: "bg-accent/15 text-[#B6BAFF] border-accent/30",
  support: "bg-amber-400/10 text-amber-200 border-amber-400/30",
  analyst: "bg-cyan/10 text-cyan border-cyan/30",
  compliance: "bg-emerald-400/10 text-emerald-300 border-emerald-400/30",
};

export function RoleChip({ role }: { role: string }) {
  return (
    <span
      className={clsx(
        "rounded-md border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        ROLE_TONE[role] ?? "border-ink-500 text-fog-300",
      )}
    >
      {role}
    </span>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { connections, selected, select } = useConnections();

  const role = user?.role || "admin";
  const items: NavItem[] =
    role === "support"
      ? SUPPORT_NAV
      : role === "analyst"
      ? ANALYST_NAV
      : role === "compliance"
      ? COMPLIANCE_NAV
      : ADMIN_NAV;

  const roleHome = getRoleHome(role);

  const footerText =
    role === "support"
      ? "Customer Privacy Mode · PII Masked"
      : role === "analyst"
      ? "Differential Privacy & k ≥ 5 Enforced"
      : role === "compliance"
      ? "Audit & Integrity Review Mode"
      : "Server-side masking active · Audit chain intact";

  return (
    <div className="flex h-full">
      {/* Sidebar Desktop */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-700/80 bg-ink-900/80 lg:flex">
        <Link to={roleHome} className="flex items-center gap-2.5 px-5 py-5 transition-opacity hover:opacity-90">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent-strong to-[#4338CA] shadow-lg shadow-accent/20">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="text-[15px] font-semibold tracking-tight text-fog-100">Dream Guard</div>
            <div className="text-[11px] text-fog-500">Data Protection Engine</div>
          </div>
        </Link>

        {/* Role Workspace Badge */}
        <div className="px-4 pb-3">
          <div className="flex items-center justify-between rounded-lg border border-ink-700 bg-ink-800/40 px-3 py-2 text-xs">
            <span className="text-fog-400">Workspace</span>
            <RoleChip role={role} />
          </div>
        </div>

        {/* Dynamic Role Navigation Items */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4" aria-label="Main">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx(
                  "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                  isActive
                    ? role === "support"
                      ? "bg-amber-400/10 text-amber-200 ring-1 ring-inset ring-amber-400/30"
                      : role === "analyst"
                      ? "bg-cyan/10 text-cyan ring-1 ring-inset ring-cyan/30"
                      : "bg-accent/10 text-fog-100 ring-1 ring-inset ring-accent/30"
                    : "text-fog-400 hover:bg-ink-800 hover:text-fog-100",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <n.icon
                    className={clsx(
                      "h-4 w-4",
                      isActive
                        ? role === "support"
                          ? "text-amber-300"
                          : role === "analyst"
                          ? "text-cyan"
                          : "text-[#A8ADFF]"
                        : "text-fog-500 group-hover:text-fog-300",
                    )}
                  />
                  {n.label}
                </>
              )}
            </NavLink>
          ))}

          {/* Internal Console Link ONLY for Admin (discrete, at bottom of nav) */}
          {role === "admin" && (
            <div className="pt-4 mt-4 border-t border-ink-800">
              <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-fog-500">
                Internal Developer Utility
              </div>
              <NavLink
                to="/admin/playground"
                className={({ isActive }) =>
                  clsx(
                    "group flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[12px] font-medium text-fog-400 hover:bg-ink-800 hover:text-fog-200",
                    isActive && "bg-ink-800 text-fog-100",
                  )
                }
              >
                <TerminalSquare className="h-3.5 w-3.5 text-fog-500 group-hover:text-fog-300" />
                Raw SQL Console (Internal)
              </NavLink>
            </div>
          )}
        </nav>

        {/* Sidebar Footer Status */}
        <div className="border-t border-ink-700/80 p-4">
          <div className="flex items-center gap-2 text-[11px] text-fog-500">
            <Activity className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
            <span className="truncate">{footerText}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header */}
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-ink-700/80 bg-ink-900/60 px-4 backdrop-blur lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <label htmlFor="db-select" className="hidden text-xs text-fog-500 sm:block">
              Database
            </label>
            <select
              id="db-select"
              className="input h-8 w-auto min-w-[220px] py-0 text-[13px]"
              value={selected?.id ?? ""}
              onChange={(e) => select(e.target.value)}
              disabled={!connections.length}
            >
              {!connections.length && <option>No connections</option>}
              {connections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {KIND_LABEL[c.kind] ?? c.kind}
                </option>
              ))}
            </select>
            {selected && (
              <span
                className={clsx(
                  "h-2 w-2 rounded-full",
                  selected.status === "healthy"
                    ? "bg-emerald-400"
                    : selected.status === "unhealthy"
                    ? "bg-rose-400"
                    : "bg-fog-500",
                )}
                title={`Status: ${selected.status}`}
              />
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-[13px] font-medium leading-4 text-fog-100">{user?.display_name}</div>
              <div className="text-[11px] text-fog-500 font-mono">@{user?.username}</div>
            </div>
            {user && <RoleChip role={user.role} />}
            <button
              onClick={logout}
              className="rounded-lg p-2 text-fog-400 hover:bg-ink-800 hover:text-fog-100"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Mobile Sub-Navigation Bar */}
        <nav className="flex gap-1 overflow-x-auto border-b border-ink-700/80 px-3 py-2 lg:hidden" aria-label="Main (mobile)">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs",
                  isActive ? "bg-ink-700 text-fog-100 font-medium" : "text-fog-400",
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>

        {/* Page View Container */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
