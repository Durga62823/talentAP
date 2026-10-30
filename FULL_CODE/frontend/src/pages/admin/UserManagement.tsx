import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Minus, Search, ShieldCheck, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorText, Modal, PageHeader, Spinner } from "../../components/ui";
import { RoleChip } from "../../components/Layout";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useConnections } from "../../lib/connections";

function Grants() {
  const qc = useQueryClient();
  const { selected } = useConnections();
  const q = useQuery({ queryKey: ["grants", selected?.id], queryFn: () => api(`/api/grants?connection_id=${selected!.id}`), enabled: !!selected });
  const rolesQ = useQuery({ queryKey: ["roles"], queryFn: () => api("/api/roles") });
  const [draft, setDraft] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (q.data?.grants) setDraft(q.data.grants);
  }, [q.data]);

  const save = useMutation({
    mutationFn: (role: string) => api("/api/grants", { method: "PUT", body: { connection_id: selected!.id, role, tables: draft[role] ?? [] } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["grants"] });
      qc.invalidateQueries({ queryKey: ["perms"] });
    },
  });

  if (!selected) {
    return <p className="text-xs text-fog-400">Select a database connection to view and manage table grants.</p>;
  }
  if (q.isLoading || rolesQ.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;

  const roles: string[] = rolesQ.data?.roles?.map((r: any) => r.name) ?? ["admin", "support", "analyst", "compliance"];
  const tables: string[] = q.data?.tables ?? [];
  const toggle = (role: string, t: string) =>
    setDraft((d) => ({ ...d, [role]: (d[role] ?? []).includes(t) ? d[role].filter((x) => x !== t) : [...(d[role] ?? []), t] }));

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Table</th>
              {roles.map((r) => (
                <th key={r} className="th text-center">
                  <RoleChip role={r} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tables.map((t: string) => (
              <tr key={t}>
                <td className="td mono font-medium">{t}</td>
                {roles.map((r) => {
                  const on = (draft[r] ?? []).includes(t);
                  return (
                    <td key={r} className="td text-center">
                      <button
                        aria-label={`${on ? "Revoke" : "Grant"} ${t} for ${r}`}
                        onClick={() => toggle(r, t)}
                        className={`inline-grid h-6 w-6 place-items-center rounded-md border ${on ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300" : "border-ink-600 text-fog-500 hover:border-ink-500"
                          }`}
                      >
                        {on ? <Check className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {roles.map((r) => (
          <Button key={r} size="sm" loading={save.isPending && save.variables === r} onClick={() => save.mutate(r)}>
            Save {r} grants
          </Button>
        ))}
      </div>

    </div>
  );
}

export default function UserManagement() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<any[]>("/api/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api("/api/roles") });
  const [adding, setAdding] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [f, setF] = useState({ username: "", display_name: "", role: "support", password: "" });

  const create = useMutation({
    mutationFn: () => api("/api/users", { body: f }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setAdding(false);
      setF({ username: "", display_name: "", role: "support", password: "" });
    },
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: any }) => api(`/api/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  // Filtered users
  const filteredUsers = (users.data ?? []).filter((u) => {
    const matchesSearch =
      u.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      u.display_name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRole = roleFilter === "ALL" || u.role.toLowerCase() === roleFilter.toLowerCase();
    return matchesSearch && matchesRole;
  });

  // Map usernames to official demo emails
  const emailMap: Record<string, string> = {
    admin_anita: "admin_anita@saffronbank.example",
    admin_farhan: "admin_farhan@saffronbank.example",
    admin_meera: "admin_meera@saffronbank.example",
    support_ravi: "support_ravi@saffronbank.example",
    support_neha: "support_neha@saffronbank.example",
    support_joseph: "support_joseph@saffronbank.example",
    analyst_kavya: "analyst_kavya@saffronbank.example",
    analyst_arnab: "analyst_arnab@saffronbank.example",
    analyst_hetal: "analyst_hetal@saffronbank.example",
    compliance_lata: "compliance_lata@saffronbank.example",
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="User & Access Governance"

        actions={
          <Button variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add New User
          </Button>
        }
      />

      {/* Security Architecture Banner */}
      <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          <div className="text-xs leading-relaxed text-fog-300">
            <strong className="text-fog-100">Role-Based Access Control (RBAC):</strong> Demo identities are seeded with strict least-privilege configurations. Modifying a user's role or status immediately invalidates active sessions in the database.
          </div>
        </div>
      </div>

      {/* Users Section with Search & Filter */}
      <Card
        title="Demo Users & Service Accounts"
        subtitle="Manage authenticated identities across Admin, Support, and Analyst roles"
      >
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-fog-500" />
            <input
              type="text"
              className="input h-8 pl-8 text-xs"
              placeholder="Search user by name or username..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-fog-400">Filter Role:</span>
            <select
              className="input h-8 py-0 text-xs w-auto"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              <option value="ALL">All Roles</option>
              <option value="admin">Admin</option>
              <option value="support">Support</option>
              <option value="analyst">Analyst</option>
              <option value="compliance">Compliance</option>
            </select>
          </div>
        </div>

        {users.isLoading ? (
          <div className="py-12"><Spinner label="Loading identities..." /></div>
        ) : users.error ? (
          <ErrorText error={users.error} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-700 text-fog-400">
                <tr>
                  <th className="pb-2.5 font-medium">User & Display Name</th>
                  <th className="pb-2.5 font-medium">Official Email Address</th>
                  <th className="pb-2.5 font-medium">Role Assignment</th>
                  <th className="pb-2.5 font-medium">Account Status</th>
                  <th className="pb-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800 text-fog-200">
                {filteredUsers.map((u) => {
                  const email = emailMap[u.username] || `${u.username}@saffronbank.example`;
                  return (
                    <tr key={u.id} className="transition-colors hover:bg-ink-800/40">
                      <td className="py-3">
                        <div className="font-semibold text-fog-100">{u.display_name}</div>
                        <div className="font-mono text-[11px] text-fog-400">@{u.username}</div>
                      </td>
                      <td className="py-3 font-mono text-fog-300">
                        {email}
                      </td>
                      <td className="py-3">
                        <select
                          className="input h-7 w-auto py-0 text-xs"
                          value={u.role}
                          disabled={u.id === me?.id}
                          onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}
                          aria-label={`Role for ${u.username}`}
                        >
                          {roles.data?.roles?.map((r: any) => (
                            <option key={r.name} value={r.name}>
                              {r.name.toUpperCase()}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-3">
                        <Badge tone={u.active ? "green" : "neutral"}>
                          {u.active ? "ACTIVE" : "SUSPENDED"}
                        </Badge>
                      </td>
                      <td className="py-3 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={u.id === me?.id}
                          onClick={() => patch.mutate({ id: u.id, body: { active: !u.active } })}
                        >
                          {u.active ? "Suspend" : "Activate"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Role & Permission Summaries */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Role Permission Summaries" subtitle="Configured system access boundaries">
          <div className="space-y-3 text-xs">
            <div className="rounded-lg border border-ink-700 bg-ink-900/40 p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="admin" />
                  <span className="font-semibold text-fog-100">Data Protection Administrator</span>
                </div>
                <Badge tone="green">Full View + Break-Glass</Badge>
              </div>

            </div>

            <div className="rounded-lg border border-ink-700 bg-ink-900/40 p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="support" />
                  <span className="font-semibold text-fog-100">Customer Support Agent</span>
                </div>
                <Badge tone="amber">Partial Masking</Badge>
              </div>

            </div>

            <div className="rounded-lg border border-ink-700 bg-ink-900/40 p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="analyst" />
                  <span className="font-semibold text-fog-100">Data Analyst</span>
                </div>
                <Badge tone="cyan">k-Anonymity (k ≥ 5)</Badge>
              </div>

            </div>

            <div className="rounded-lg border border-ink-700 bg-ink-900/40 p-3.5">


            </div>
          </div>
        </Card>

        {/* Database Table Grants Matrix */}
        <Card title="Table Grants Matrix" subtitle="Database table access permissions by role">
          <Grants />
        </Card>
      </div>

      {/* Add User Modal */}
      {adding && (
        <Modal open={adding} title="Create Demo User" onClose={() => setAdding(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="space-y-3"
          >
            <div>
              <label className="label">Username</label>
              <input
                className="input"
                pattern="^[a-z][a-z0-9_.-]{2,31}$"
                value={f.username}
                onChange={(e) => setF({ ...f, username: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="label">Display Name</label>
              <input
                className="input"
                value={f.display_name}
                onChange={(e) => setF({ ...f, display_name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="label">Role</label>
              <select
                className="input"
                value={f.role}
                onChange={(e) => setF({ ...f, role: e.target.value })}
              >
                {roles.data?.roles?.map((r: any) => (
                  <option key={r.name} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password"
                className="input"
                value={f.password}
                onChange={(e) => setF({ ...f, password: e.target.value })}
                required
                minLength={10}
              />
            </div>
            <ErrorText error={create.error} />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setAdding(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={create.isPending} type="submit">
                Create User
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
