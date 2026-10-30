import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Minus, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, ErrorText, Modal, PageHeader, Spinner } from "../components/ui";
import { RoleChip } from "../components/Layout";
import { api, fmtTime } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConnections } from "../lib/connections";

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
                        className={`inline-grid h-6 w-6 place-items-center rounded-md border transition-all ${
                          on
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
      <ErrorText error={save.error} />
      <p className="text-[11px] text-[#64748B]">
        Default deny: a role can only query tables granted here. Grants never bypass masking — they only decide whether a table is reachable at all.
      </p>
    </div>
  );
}

export default function AccessPage() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<any[]>("/api/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api("/api/roles") });
  const [adding, setAdding] = useState(false);
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

  return (
    <div>
      <PageHeader
        title="Role & Access Management"
        description="Configure table-level permissions, role memberships, and least-privilege security boundaries."
        actions={
          <Button variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add user
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Users">
          {users.isLoading ? (
            <Spinner />
          ) : users.error ? (
            <ErrorText error={users.error} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs min-w-[450px]">
                <thead>
                  <tr>
                    <th className="th">User</th>
                    <th className="th">Role</th>
                    <th className="th">Status</th>
                    <th className="th">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {(users.data ?? []).map((u) => (
                    <tr key={u.id} className="hover:bg-[#F4F8FD]">
                      <td className="td">
                        <div className="text-[13px] font-semibold text-[#172B45]">{u.display_name}</div>
                        <div className="text-[11px] text-[#64748B]">@{u.username}</div>
                      </td>
                      <td className="td">
                        <select
                          className="input h-8 w-auto py-0 text-xs font-semibold"
                          value={u.role}
                          disabled={u.id === me?.id}
                          onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}
                          aria-label={`Role for ${u.username}`}
                        >
                          {roles.data?.roles?.map((r: any) => (
                            <option key={r.name}>{r.name}</option>
                          ))}
                        </select>
                      </td>
                      <td className="td">
                        <button
                          disabled={u.id === me?.id}
                          onClick={() => patch.mutate({ id: u.id, body: { active: !u.active } })}
                          className="disabled:cursor-not-allowed"
                        >
                          <Badge tone={u.active ? "green" : "neutral"}>{u.active ? "active" : "disabled"}</Badge>
                        </button>
                      </td>
                      <td className="td text-xs text-[#64748B]">{fmtTime(u.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <ErrorText error={patch.error} />
        </Card>
        <Card title="Roles & permissions">
          {roles.data ? (
            <div className="space-y-3">
              {roles.data.roles?.map((r: any) => (
                <div key={r.name} className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center gap-2">
                    <RoleChip role={r.name} />
                    <span className="text-xs text-[#64748B]">{r.description}</span>
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-1">
                    {Object.keys(roles.data.permissions ?? {}).map((p) => (
                      <Badge
                        key={p}
                        tone={r.permissions?.includes(p) ? "indigo" : "neutral"}
                        className={r.permissions?.includes(p) ? "" : "opacity-40 line-through"}
                        title={roles.data.permissions[p]}
                      >
                        {p}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
              <Alert tone="info">
                Unknown roles receive no permissions (deny by default). Admin is not exempt: its reads are policy-masked and audited, and raw card/balance values require break-glass justification.
              </Alert>
            </div>
          ) : (
            <Spinner />
          )}
        </Card>
      </div>
      <Card className="mt-4" title="Table grants" subtitle="Per database, per role">
        <Grants />
      </Card>
      <Modal open={adding} onClose={() => setAdding(false)} title="Add user">
        <form
          className="space-y-3.5"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div>
            <label className="label">Username</label>
            <input
              className="input"
              value={f.username}
              onChange={(e) => setF({ ...f, username: e.target.value })}
              pattern="^[a-z][a-z0-9_.\-]{2,31}$"
              required
              autoComplete="off"
            />
          </div>
          <div>
            <label className="label">Display name</label>
            <input className="input" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} required />
          </div>
          <div>
            <label className="label">Role</label>
            <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
              {roles.data?.roles?.map((r: any) => (
                <option key={r.name}>{r.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Initial password</label>
            <input
              className="input"
              type="password"
              value={f.password}
              onChange={(e) => setF({ ...f, password: e.target.value })}
              minLength={10}
              required
              autoComplete="new-password"
            />
            <p className="mt-1 text-[11px] text-[#64748B]">≥ 10 chars with upper, lower case and a digit. Stored as Argon2id.</p>
          </div>
          <ErrorText error={create.error} />
          <div className="flex justify-end gap-2 pt-2 border-t border-[#DCE5F0]">
            <Button variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" loading={create.isPending}>
              Create user
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
