import { KeyRound, Lock } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button } from "../components/ui";
import { RoleChip } from "../components/Layout";
import { DEMO_ACCOUNTS, getRoleHome, useAuth } from "../lib/auth";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeRoleTab, setActiveRoleTab] = useState<string>("all");

  useEffect(() => {
    if (user) {
      navigate(getRoleHome(user.role), { replace: true });
    }
  }, [user, navigate]);

  const submit = async (e?: FormEvent, u = username, p = password) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(u, p);
      // AuthProvider updates user state, which triggers useEffect navigation
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  const filteredDemoAccounts = DEMO_ACCOUNTS.filter(
    (a) => activeRoleTab === "all" || a.role === activeRoleTab,
  );

  return (
    <div className="relative grid min-h-full place-items-center overflow-y-auto px-4 py-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(99,102,241,0.18),transparent_70%)]" />
      <div className="relative w-full max-w-[1020px] animate-fadein">
        <div className="grid gap-6 md:grid-cols-[1.05fr_1.15fr]">
          {/* Left Column: Product Branding & Features */}
          <div className="flex flex-col justify-center">
            <div className="mb-6 flex items-center gap-3.5">
              <img
                src="/logo-emblem.png"
                alt="Dream Guard Shield"
                className="h-14 w-14 shrink-0 object-contain drop-shadow-[0_4px_16px_rgba(249,115,22,0.35)]"
              />
              <div>
                <div className="text-2xl font-bold tracking-tight text-fog-100">Dream Guard</div>
                <div className="text-xs text-fog-400">Intelligent Role-Based Data Protection Platform</div>
              </div>
            </div>

            <h1 className="text-3xl font-bold leading-tight tracking-tight text-fog-100">
              Role-Specific Workspaces.
              <br />
              Server-Side Lineage Masking.
              <br />
              <span className="bg-gradient-to-r from-[#A8ADFF] to-cyan bg-clip-text text-transparent">
                Differential Privacy & Audit Integrity.
              </span>
            </h1>

            <div className="mt-6 space-y-3 text-xs text-fog-300">
              <div className="flex items-start gap-2.5 rounded-lg border border-ink-800 bg-ink-900/40 p-2.5">
                <span className="font-semibold text-accent uppercase text-[11px] w-16 shrink-0">Admin:</span>
                <span>Full security governance, PII discovery, policy lifecycle, and tamper-evident audit ledger.</span>
              </div>
              <div className="flex items-start gap-2.5 rounded-lg border border-ink-800 bg-ink-900/40 p-2.5">
                <span className="font-semibold text-amber-300 uppercase text-[11px] w-16 shrink-0">Support:</span>
                <span>Customer 360 lookup & support tickets with automated partial masking (<code>4111-XXXX-XXXX-1111</code>).</span>
              </div>
              <div className="flex items-start gap-2.5 rounded-lg border border-ink-800 bg-ink-900/40 p-2.5">
                <span className="font-semibold text-cyan uppercase text-[11px] w-16 shrink-0">Analyst:</span>
                <span>Transaction trends and aggregate explorer with strict k-anonymity guarantees ($k \ge 5$).</span>
              </div>
            </div>

            <p className="mt-4 text-[11px] text-fog-500">
              Backed by official Saffron Bank Ltd synthetic dataset (9 tables, 129,260 rows) across SQLite, MySQL, and PostgreSQL.
            </p>
          </div>

          {/* Right Column: Credentials Login + Demo Identities */}
          <div className="card p-6">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-fog-100">
              <Lock className="h-4 w-4 text-fog-400" /> Sign In to Workspace
            </h2>

            <form onSubmit={submit} className="mt-4 space-y-3">
              <div>
                <label className="label text-xs" htmlFor="u">Username</label>
                <input
                  id="u"
                  className="input text-xs"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. admin_anita or support_ravi"
                  required
                />
              </div>
              <div>
                <label className="label text-xs" htmlFor="p">Password</label>
                <input
                  id="p"
                  type="password"
                  className="input text-xs"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                />
              </div>

              {error && <Alert tone="error">{error}</Alert>}

              <Button variant="primary" className="w-full text-xs" loading={busy} type="submit">
                Sign In
              </Button>
            </form>

            {/* Demo Identities Section */}
            <div className="mt-5 border-t border-ink-700/80 pt-4">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-fog-300">
                  <KeyRound className="h-3.5 w-3.5 text-amber-400" /> Click to Test Demo Account
                </span>
                <span className="text-[10px] text-fog-500 font-mono">9 Demo Users</span>
              </div>

              {/* Role Filter Tabs */}
              <div className="mb-2 flex gap-1 rounded-lg border border-ink-700 bg-ink-950 p-1">
                {[
                  { id: "all", label: "All" },
                  { id: "admin", label: "Admin (3)" },
                  { id: "support", label: "Support (3)" },
                  { id: "analyst", label: "Analyst (3)" },
                ].map((t) => (
                  <button
                    type="button"
                    key={t.id}
                    onClick={() => setActiveRoleTab(t.id)}
                    className={`flex-1 rounded-md py-1 text-[11px] font-medium transition-colors ${
                      activeRoleTab === t.id
                        ? "bg-ink-700 text-fog-100 shadow-sm"
                        : "text-fog-400 hover:text-fog-200"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Demo Accounts List */}
              <div className="max-h-[250px] space-y-1.5 overflow-y-auto pr-1">
                {filteredDemoAccounts.map((a) => (
                  <button
                    type="button"
                    key={a.username}
                    disabled={busy}
                    onClick={() => {
                      setUsername(a.username);
                      setPassword(a.password);
                      submit(undefined, a.username, a.password);
                    }}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2 text-left transition-all hover:border-accent/50 hover:bg-ink-800/80"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold text-fog-100">{a.label}</span>
                        <span className="font-mono text-[10px] text-fog-500">@{a.username}</span>
                      </div>
                      <div className="truncate text-[11px] text-fog-400">{a.blurb}</div>
                    </div>
                    <RoleChip role={a.role} />
                  </button>
                ))}
              </div>

              <div className="mt-3 text-[11px] text-fog-500">
                Default demo passwords: <code>Admin@2026!</code>, <code>Support@2026!</code>, <code>Analyst@2026!</code>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
