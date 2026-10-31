import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Minus, RefreshCcw, Search, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, ErrorText, Modal, PageHeader, Spinner } from "../../components/ui";
import { RoleChip } from "../../components/Layout";
import { API_BASE, api, fmtTime, type ScimToken, type ScimTokenCreated, type SsoProvider } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useConnections } from "../../lib/connections";

const TOKEN_TONE: Record<ScimToken["status"], string> = { active: "green", expired: "amber", revoked: "neutral" };

function DirectorySync() {
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["sso-providers"], queryFn: () => api<SsoProvider[]>("/api/auth/sso/providers") });
  const tokens = useQuery({ queryKey: ["scim-tokens"], queryFn: () => api<ScimToken[]>("/api/scim/tokens") });
  const [f, setF] = useState({ description: "", idp_id: "", expires_in_days: 90 });
  const [created, setCreated] = useState<ScimTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const idpId = f.idp_id || providers.data?.[0]?.id || "";
  const scimUrl = `${API_BASE || window.location.origin}/api/scim/v2`;

  const create = useMutation({
    mutationFn: () => api<ScimTokenCreated>("/api/scim/tokens", { body: { ...f, idp_id: idpId } }),
    onSuccess: (t) => {
      setCreated(t);
      setCopied(false);
      setF({ ...f, description: "" });
      qc.invalidateQueries({ queryKey: ["scim-tokens"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/scim/tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scim-tokens"] }),
  });

  return (
    <div className="space-y-4 text-xs">
      <p className="text-[#64748B] leading-relaxed">
        Your identity provider (Entra ID, Okta, …) pushes joiners, movers and leavers to DreamGuard over SCIM 2.0. Each token is bound to one
        identity provider and can only see or change that provider's users — local accounts, including break-glass administrators, are invisible to it.
      </p>
      <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3">
        <div className="label">SCIM base URL</div>
        <code className="block break-all font-mono text-[11px] text-[#123B67]">{scimUrl}</code>
      </div>

      <form
        className="grid gap-2.5 sm:grid-cols-[1.4fr_1fr_0.8fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div>
          <label className="label">Description</label>
          <input className="input" required minLength={3} maxLength={128} placeholder="e.g. Entra ID provisioning" value={f.description}
                 onChange={(e) => setF({ ...f, description: e.target.value })} />
        </div>
        <div>
          <label className="label">Identity provider</label>
          <select className="input" value={idpId} onChange={(e) => setF({ ...f, idp_id: e.target.value })}>
            {providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Expires in</label>
          <select className="input" value={f.expires_in_days} onChange={(e) => setF({ ...f, expires_in_days: Number(e.target.value) })}>
            {[30, 90, 180, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </div>
        <Button variant="primary" type="submit" loading={create.isPending} disabled={!idpId} icon={<KeyRound className="h-4 w-4" />}>Generate</Button>
      </form>
      <ErrorText error={create.error} />

      {created && (
        <Alert tone="warn" title="Copy this token now — it is shown only once">
          <div className="mt-1 flex items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded border border-amber-200 bg-white px-2 py-1 font-mono text-[11px] text-[#172B45]">{created.token}</code>
            <Button size="sm" icon={<Copy className="h-3.5 w-3.5" />} onClick={() => navigator.clipboard?.writeText(created.token).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <div className="mt-1 text-[11px]">DreamGuard stores only its SHA-256. Paste it as the bearer secret in your IdP's provisioning settings.</div>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-lg border border-[#DCE5F0]">
        {tokens.isLoading ? <Spinner /> : tokens.error ? <ErrorText error={tokens.error} /> : !tokens.data?.length ? (
          <p className="p-3 text-[#64748B]">No SCIM tokens yet.</p>
        ) : (
          <table className="w-full min-w-[560px] text-xs">
            <thead><tr><th className="th">Token</th><th className="th">Identity provider</th><th className="th">Expires</th><th className="th">Last sync</th><th className="th">Status</th><th className="th" /></tr></thead>
            <tbody>
              {tokens.data.map((t) => (
                <tr key={t.id} className="hover:bg-[#F4F8FD]">
                  <td className="td font-medium text-[#172B45]">{t.description}<div className="font-mono text-[10px] text-[#64748B]">{t.id.slice(0, 8)}</div></td>
                  <td className="td text-[#64748B]">{t.idp_name ?? t.idp_id}</td>
                  <td className="td text-[#64748B]">{fmtTime(t.expires_at)}</td>
                  <td className="td text-[#64748B]">{t.last_used_at ? fmtTime(t.last_used_at) : "never"}</td>
                  <td className="td"><Badge tone={TOKEN_TONE[t.status]}>{t.status}</Badge></td>
                  <td className="td text-right">
                    {t.status === "active" && (
                      <Button size="sm" variant="danger" loading={revoke.isPending && revoke.variables === t.id} onClick={() => revoke.mutate(t.id)}>Revoke</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

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
    return <p className="text-xs text-[#64748B]">Select a database connection to view and manage table grants.</p>;
  }
  if (q.isLoading || rolesQ.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;

  const roles: string[] = rolesQ.data?.roles?.map((r: any) => r.name) ?? ["admin", "support", "analyst", "compliance"];
  const tables: string[] = q.data?.tables ?? [];
  const toggle = (role: string, t: string) =>
    setDraft((d) => ({ ...d, [role]: (d[role] ?? []).includes(t) ? d[role].filter((x) => x !== t) : [...(d[role] ?? []), t] }));

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-[#DCE5F0]">
        <table className="w-full text-xs min-w-[500px]">
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
              <tr key={t} className="hover:bg-[#F4F8FD]">
                <td className="td mono font-semibold text-[#172B45]">{t}</td>
                {roles.map((r) => {
                  const on = (draft[r] ?? []).includes(t);
                  return (
                    <td key={r} className="td text-center">
                      <button
                        aria-label={`${on ? "Revoke" : "Grant"} ${t} for ${r}`}
                        onClick={() => toggle(r, t)}
                        className={`inline-grid h-6 w-6 place-items-center rounded-md border transition-all ${on
                          ? "border-emerald-300 bg-emerald-50 text-emerald-800 shadow-sm"
                          : "border-[#DCE5F0] bg-white text-[#64748B] hover:border-[#3478C8]"
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
      <div className="flex flex-wrap justify-end gap-2 pt-1">
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
  const [syncing, setSyncing] = useState(false);
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
        description="Manage authenticated user identities, role assignments, database table grant matrices, and security privileges."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button icon={<RefreshCcw className="h-4 w-4" />} onClick={() => setSyncing(true)}>
              Directory Sync (SCIM)
            </Button>
            <Button variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setAdding(true)}>
              Add New User
            </Button>
          </div>
        }
      />

      {/* Users Section with Search & Filter */}
      <Card
        title="Demo Users & Service Accounts"
        subtitle="Manage authenticated identities across Admin, Support, and Analyst roles"
      >
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#64748B]" />
            <input
              type="text"
              className="input h-9 pl-8 text-xs"
              placeholder="Search user by name or username..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2 text-xs w-full sm:w-auto">
            <span className="text-[#64748B] font-semibold shrink-0">Filter Role:</span>
            <select
              className="input h-9 py-0 text-xs flex-1 sm:w-auto"
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
            <table className="w-full text-left text-xs min-w-[650px]">
              <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">User & Display Name</th>
                  <th className="py-2.5 px-3 font-semibold">Official Email Address</th>
                  <th className="py-2.5 px-3 font-semibold">Role Assignment</th>
                  <th className="py-2.5 px-3 font-semibold">Account Status</th>
                  <th className="py-2.5 px-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                {filteredUsers.map((u) => {
                  const email = emailMap[u.username] || (u.username.includes("@") ? u.username : `${u.username}@saffronbank.example`);
                  return (
                    <tr key={u.id} className="transition-colors hover:bg-[#F4F8FD]">
                      <td className="py-3 px-3">
                        <div className="font-semibold text-[#172B45]">{u.display_name}</div>
                        <div className="font-mono text-[11px] text-[#64748B]">@{u.username}</div>
                        {u.federated ? (
                          <Badge tone="violet" className="mt-1 text-[10px]" title="Signs in through the identity provider; role synced from directory groups">
                            SSO · {u.idp_name ?? u.idp_id}{u.idp_linked ? "" : " · awaiting first sign-in"}
                          </Badge>
                        ) : (
                          <Badge tone="neutral" className="mt-1 text-[10px]">Local account</Badge>
                        )}
                      </td>
                      <td className="py-3 px-3 font-mono text-[#64748B]">
                        {email}
                      </td>
                      <td className="py-3 px-3">
                        <select
                          className="input h-8 w-auto py-0 text-xs font-semibold"
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
                      <td className="py-3 px-3">
                        <Badge tone={u.active ? "green" : "neutral"}>
                          {u.active ? "ACTIVE" : "SUSPENDED"}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-right">
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
            <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="admin" />
                  <span className="font-semibold text-[#172B45]">Data Protection Administrator</span>
                </div>
                <Badge tone="green">Full View + Break-Glass</Badge>
              </div>
            </div>

            <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="support" />
                  <span className="font-semibold text-[#172B45]">Customer Support Agent</span>
                </div>
                <Badge tone="amber">Partial Masking</Badge>
              </div>
            </div>

            <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RoleChip role="analyst" />
                  <span className="font-semibold text-[#172B45]">Data Analyst</span>
                </div>
                <Badge tone="cyan">k-Anonymity (k ≥ 5)</Badge>
              </div>
            </div>
          </div>
        </Card>

        {/* Database Table Grants Matrix */}
        <Card title="Table Grants Matrix" subtitle="Database table access permissions by role">
          <Grants />
        </Card>
      </div>

      <Modal open={syncing} title="Directory Sync · SCIM 2.0 provisioning tokens" onClose={() => setSyncing(false)} wide>
        {syncing && <DirectorySync />}
      </Modal>

      {/* Add User Modal */}
      {adding && (
        <Modal open={adding} title="Create Demo User" onClose={() => setAdding(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="space-y-3.5"
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
            <div className="flex justify-end gap-2 pt-2 border-t border-[#DCE5F0]">
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
