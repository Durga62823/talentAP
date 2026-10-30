import React, { lazy } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { ApiError } from "./lib/api";
import { AuthProvider, getRoleHome, useAuth } from "./lib/auth";
import { ConnectionProvider } from "./lib/connections";

// Pages are code-split per route so a role only downloads the screens it opens.
// Admin Pages
const AuditPage = lazy(() => import("./pages/Audit"));
const ConnectionsPage = lazy(() => import("./pages/Connections"));
const DiscoveryPage = lazy(() => import("./pages/Discovery"));
const IntegrityPage = lazy(() => import("./pages/Integrity"));
const MlModelPage = lazy(() => import("./pages/MlModel"));
const OverviewPage = lazy(() => import("./pages/Overview"));
const PlaygroundPage = lazy(() => import("./pages/Playground"));
const PoliciesPage = lazy(() => import("./pages/Policies"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const UploadsPage = lazy(() => import("./pages/Uploads"));
const UserManagement = lazy(() => import("./pages/admin/UserManagement"));

// Support Pages
const CustomerLookup = lazy(() => import("./pages/support/CustomerLookup"));
const CustomerProfiles = lazy(() => import("./pages/support/CustomerProfiles"));
const SupportActivity = lazy(() => import("./pages/support/SupportActivity"));
const SupportOverview = lazy(() => import("./pages/support/SupportOverview"));
const SupportTickets = lazy(() => import("./pages/support/SupportTickets"));

// Analyst Pages
const AggregateExplorer = lazy(() => import("./pages/analyst/AggregateExplorer"));
const AnalystActivity = lazy(() => import("./pages/analyst/AnalystActivity"));
const AnalystAnalytics = lazy(() => import("./pages/analyst/AnalystAnalytics"));
const AnalystOverview = lazy(() => import("./pages/analyst/AnalystOverview"));
const AnalystReports = lazy(() => import("./pages/analyst/AnalystReports"));
const AnalystTrends = lazy(() => import("./pages/analyst/AnalystTrends"));

import LoginPage from "./pages/Login";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2,
    },
  },
});

function RoleGuard({
  allowedRoles,
  children,
}: {
  allowedRoles: string[];
  children: React.ReactElement;
}) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;

  if (!allowedRoles.includes(user.role)) {
    // Redirect unauthorized navigation attempt to the user's role landing page
    return <Navigate to={getRoleHome(user.role)} replace />;
  }

  return children;
}

function RoleHomeRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={getRoleHome(user.role)} replace />;
}

function Root() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner label="Starting Dream Guard…" />
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <ConnectionProvider>
      <Routes>
        <Route path="/login" element={<RoleHomeRedirect />} />

        <Route element={<Layout />}>
          {/* Root dynamic redirector */}
          <Route index element={<RoleHomeRedirect />} />

          {/* -------------------- Admin Workspace Routes -------------------- */}
          <Route
            path="admin/overview"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <OverviewPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/users"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <UserManagement />
              </RoleGuard>
            }
          />
          <Route
            path="admin/discovery"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <DiscoveryPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/policies"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <PoliciesPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/connections"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <ConnectionsPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/audit"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <AuditPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/ml-model"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <MlModelPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/integrity"
            element={
              <RoleGuard allowedRoles={["admin", "compliance"]}>
                <IntegrityPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/settings"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <SettingsPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/uploads"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <UploadsPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/playground"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <PlaygroundPage />
              </RoleGuard>
            }
          />

          {/* -------------------- Support Workspace Routes -------------------- */}
          <Route
            path="support/overview"
            element={
              <RoleGuard allowedRoles={["support", "admin"]}>
                <SupportOverview />
              </RoleGuard>
            }
          />
          <Route
            path="support/lookup"
            element={
              <RoleGuard allowedRoles={["support", "admin"]}>
                <CustomerLookup />
              </RoleGuard>
            }
          />
          <Route
            path="support/profiles"
            element={
              <RoleGuard allowedRoles={["support", "admin"]}>
                <CustomerProfiles />
              </RoleGuard>
            }
          />
          <Route
            path="support/tickets"
            element={
              <RoleGuard allowedRoles={["support", "admin"]}>
                <SupportTickets />
              </RoleGuard>
            }
          />
          <Route
            path="support/activity"
            element={
              <RoleGuard allowedRoles={["support", "admin"]}>
                <SupportActivity />
              </RoleGuard>
            }
          />

          {/* -------------------- Analyst Workspace Routes -------------------- */}
          <Route
            path="analyst/overview"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AnalystOverview />
              </RoleGuard>
            }
          />
          <Route
            path="analyst/analytics"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AnalystAnalytics />
              </RoleGuard>
            }
          />
          <Route
            path="analyst/trends"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AnalystTrends />
              </RoleGuard>
            }
          />
          <Route
            path="analyst/explorer"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AggregateExplorer />
              </RoleGuard>
            }
          />
          <Route
            path="analyst/reports"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AnalystReports />
              </RoleGuard>
            }
          />
          <Route
            path="analyst/activity"
            element={
              <RoleGuard allowedRoles={["analyst", "admin"]}>
                <AnalystActivity />
              </RoleGuard>
            }
          />

          {/* Legacy & Shortcut Aliases */}
          <Route path="access" element={<Navigate to="/admin/users" replace />} />
          <Route path="connections" element={<Navigate to="/admin/connections" replace />} />
          <Route path="discovery" element={<Navigate to="/admin/discovery" replace />} />
          <Route path="policies" element={<Navigate to="/admin/policies" replace />} />
          <Route path="audit" element={<Navigate to="/admin/audit" replace />} />
          <Route path="integrity" element={<Navigate to="/admin/integrity" replace />} />
          <Route path="settings" element={<Navigate to="/admin/settings" replace />} />
          <Route path="uploads" element={<Navigate to="/admin/uploads" replace />} />
          <Route path="playground" element={<Navigate to="/admin/playground" replace />} />

          {/* Catch-all */}
          <Route path="*" element={<RoleHomeRedirect />} />
        </Route>
      </Routes>
    </ConnectionProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Root />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
