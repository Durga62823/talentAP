import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { ApiError } from "./lib/api";
import { AuthProvider, getRoleHome, useAuth } from "./lib/auth";
import { ConnectionProvider } from "./lib/connections";

// Admin Pages
import AuditPage from "./pages/Audit";
import ConnectionsPage from "./pages/Connections";
import DiscoveryPage from "./pages/Discovery";
import IntegrityPage from "./pages/Integrity";
import OverviewPage from "./pages/Overview";
import PlaygroundPage from "./pages/Playground";
import PoliciesPage from "./pages/Policies";
import SettingsPage from "./pages/Settings";
import UploadsPage from "./pages/Uploads";
import UserManagement from "./pages/admin/UserManagement";

// Support Pages
import CustomerLookup from "./pages/support/CustomerLookup";
import CustomerProfiles from "./pages/support/CustomerProfiles";
import SupportActivity from "./pages/support/SupportActivity";
import SupportOverview from "./pages/support/SupportOverview";
import SupportTickets from "./pages/support/SupportTickets";

// Analyst Pages
import AggregateExplorer from "./pages/analyst/AggregateExplorer";
import AnalystActivity from "./pages/analyst/AnalystActivity";
import AnalystAnalytics from "./pages/analyst/AnalystAnalytics";
import AnalystOverview from "./pages/analyst/AnalystOverview";
import AnalystReports from "./pages/analyst/AnalystReports";
import AnalystTrends from "./pages/analyst/AnalystTrends";

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
