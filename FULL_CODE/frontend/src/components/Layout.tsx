import clsx from "clsx";
import {
  Activity,
  BrainCircuit,
  BarChart3,
  Database,
  FileSpreadsheet,
  Fingerprint,
  History,
  Layers,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Menu,
  Radar,
  ScrollText,
  Search,
  Settings,
  SlidersHorizontal,
  TrendingUp,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { Suspense, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { getRoleHome, useAuth } from "../lib/auth";
import { Spinner } from "./ui";
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
  { to: "/admin/ml-model", label: "ML Model", icon: BrainCircuit },
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
  { to: "/admin/ml-model", label: "ML Model", icon: BrainCircuit },
  { to: "/admin/policies", label: "Masking Policies", icon: SlidersHorizontal },
  { to: "/admin/audit", label: "Audit Center", icon: ScrollText },
  { to: "/admin/integrity", label: "Integrity Verification", icon: Fingerprint },
];

const ROLE_TONE: Record<string, string> = {
  admin: "bg-[#EAF2FB] text-[#123B67] border-[#DCE5F0]",
  support: "bg-amber-50 text-amber-800 border-amber-200",
  analyst: "bg-[#EEF3F9] text-[#1D5FA7] border-[#DCE5F0]",
  compliance: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

export function RoleChip({ role }: { role: string }) {
  return (
    <span
      className={clsx(
        "rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide shadow-sm",
        ROLE_TONE[role] ?? "border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]",
      )}
    >
      {role}
    </span>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { connections, selected, select } = useConnections();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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

  const closeMobileMenu = () => setMobileMenuOpen(false);

  return (
    <div className="flex h-full bg-[#F5F8FC] text-[#172B45]">
      {/* Mobile Backdrop Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={closeMobileMenu}
          aria-hidden="true"
        />
      )}

      {/* Mobile Slide-in Drawer */}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-50 flex w-[280px] max-w-[85vw] flex-col bg-white border-r border-[#DCE5F0] shadow-modal transition-transform duration-200 ease-in-out lg:hidden",
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b border-[#DCE5F0] px-5 py-4">
          <Link to={roleHome} onClick={closeMobileMenu} className="flex items-center gap-3">
            <img
              src="/logo-emblem-128.png"
              alt="Dream Guard Shield"
              className="h-8 w-8 shrink-0 object-contain drop-shadow-[0_2px_8px_rgba(29,95,167,0.25)]"
            />
            <div>
              <div className="text-[15px] font-bold tracking-tight text-[#172B45]">Dream Guard</div>
              <div className="text-[11px] font-medium text-[#64748B]">Data Protection Engine</div>
            </div>
          </Link>
          <button
            onClick={closeMobileMenu}
            className="rounded-lg p-1.5 text-[#64748B] hover:bg-[#EAF2FB] hover:text-[#123B67]"
            aria-label="Close navigation menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Mobile Workspace info */}
        <div className="px-4 py-3 border-b border-[#DCE5F0] bg-[#F4F8FD]/50">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-[#64748B]">Active Role</span>
            <RoleChip role={role} />
          </div>
        </div>

        {/* Mobile Nav Links */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Main Mobile Navigation">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={closeMobileMenu}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                  isActive
                    ? "bg-[#EAF2FB] text-[#123B67] font-semibold border-l-4 border-[#1D5FA7]"
                    : "text-[#64748B] hover:bg-[#F4F8FD] hover:text-[#172B45]",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <n.icon
                    className={clsx(
                      "h-4 w-4 shrink-0",
                      isActive ? "text-[#1D5FA7]" : "text-[#64748B]",
                    )}
                  />
                  <span>{n.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Mobile Footer */}
        <div className="border-t border-[#DCE5F0] bg-[#F4F8FD]/50 p-4">
          <div className="flex items-center gap-2 text-xs text-[#64748B]">
            <Activity className="h-4 w-4 text-emerald-600 shrink-0" />
            <span className="truncate">{footerText}</span>
          </div>
        </div>
      </aside>

      {/* Desktop Permanent Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-[#DCE5F0] bg-white lg:flex shadow-sm">
        <Link to={roleHome} className="flex items-center gap-3 px-5 py-5 transition-opacity hover:opacity-95">
          <img
            src="/logo-emblem-128.png"
            alt="Dream Guard Shield"
            className="h-10 w-10 shrink-0 object-contain drop-shadow-[0_2px_8px_rgba(29,95,167,0.2)]"
          />
          <div>
            <div className="text-[15px] font-bold tracking-tight text-[#172B45]">Dream Guard</div>
            <div className="text-[11px] font-medium text-[#64748B]">Data Protection Engine</div>
          </div>
        </Link>

        {/* Role Workspace Badge */}
        <div className="px-4 pb-3">
          <div className="flex items-center justify-between rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] px-3.5 py-2.5 text-xs shadow-sm">
            <span className="font-medium text-[#64748B]">Workspace</span>
            <RoleChip role={role} />
          </div>
        </div>

        {/* Desktop Navigation Items */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4" aria-label="Main Desktop Navigation">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx(
                  "group flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-all",
                  isActive
                    ? "bg-[#EAF2FB] text-[#123B67] font-semibold border-l-4 border-[#1D5FA7] shadow-sm"
                    : "text-[#64748B] hover:bg-[#F4F8FD] hover:text-[#172B45]",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <n.icon
                    className={clsx(
                      "h-4 w-4 shrink-0 transition-colors",
                      isActive ? "text-[#1D5FA7]" : "text-[#64748B] group-hover:text-[#172B45]",
                    )}
                  />
                  <span>{n.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Sidebar Footer Status */}
        <div className="border-t border-[#DCE5F0] bg-[#F4F8FD]/50 p-4">
          <div className="flex items-center gap-2 text-[11px] font-medium text-[#64748B]">
            <Activity className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
            <span className="truncate">{footerText}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 sm:gap-3 border-b border-[#DCE5F0] bg-white/95 px-3 sm:px-6 lg:px-8 backdrop-blur shadow-sm">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            {/* Mobile Hamburger Button */}
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="rounded-lg p-1.5 sm:p-2 text-[#172B45] hover:bg-[#EAF2FB] focus:outline-none focus:ring-2 focus:ring-[#1D5FA7] lg:hidden shrink-0"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>

            {/* Mobile Logo Brand */}
            <Link to={roleHome} className="flex items-center gap-2 lg:hidden shrink-0" title="Dream Guard">
              <img src="/logo-emblem-128.png" alt="Dream Guard" className="h-6 w-6 sm:h-7 sm:w-7 object-contain drop-shadow-[0_1px_4px_rgba(29,95,167,0.2)]" />
            </Link>

            <label htmlFor="db-select" className="hidden text-xs font-semibold uppercase tracking-wider text-[#64748B] sm:block shrink-0">
              Database
            </label>
            <select
              id="db-select"
              className="input h-9 w-auto max-w-[125px] xs:max-w-[180px] sm:max-w-[240px] min-w-0 py-0 text-xs sm:text-[13px] border-[#DCE5F0] bg-white text-[#172B45] truncate"
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
                  "h-2 w-2 sm:h-2.5 sm:w-2.5 rounded-full shrink-0 shadow-sm",
                  selected.status === "healthy"
                    ? "bg-emerald-500"
                    : selected.status === "unhealthy"
                      ? "bg-rose-500"
                      : "bg-[#64748B]",
                )}
                title={`Status: ${selected.status}`}
              />
            )}
          </div>

          <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
            <div className="hidden text-right sm:block">
              <div className="text-[13px] font-semibold leading-4 text-[#172B45]">{user?.display_name}</div>
              <div className="text-[11px] text-[#64748B] font-mono">@{user?.username}</div>
            </div>
            {user && <RoleChip role={user.role} />}
            <button
              onClick={logout}
              className="rounded-lg p-1.5 sm:p-2 text-[#64748B] hover:bg-[#EAF2FB] hover:text-[#123B67] transition-colors shrink-0"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Page View Container */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-3 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
            <Suspense fallback={<div className="grid h-64 place-items-center"><Spinner label="Loading workspace…" /></div>}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}
