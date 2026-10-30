import { ArrowRight, KeyRound, Lock, User } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Alert } from "../components/ui";
import { DEMO_ACCOUNTS, getRoleHome, useAuth } from "../lib/auth";

const ROLE_OUTLINE: Record<string, string> = {
  admin: "border-[#1D5FA7] text-[#1D5FA7]",
  support: "border-amber-400 text-amber-700",
  analyst: "border-sky-400 text-sky-700",
  compliance: "border-purple-400 text-purple-700",
};

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
    <div className="relative min-h-screen w-full flex items-center justify-center bg-[#F5F8FC] p-2.5 sm:p-6 md:p-8 overflow-x-hidden">
      {/* Background Decorative Radial Gradient */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-15%,rgba(29,95,167,0.12),transparent_70%)]" />

      {/* Main Split-Screen Container Card inspired by Image 1 */}
      <div className="relative w-full max-w-[1080px] overflow-hidden rounded-2xl sm:rounded-3xl bg-white border border-[#DCE5F0] shadow-[0_20px_50px_-15px_rgba(18,59,103,0.18)] transition-all animate-fadein">
        <div className="flex flex-col lg:flex-row">

          {/* ================= LEFT PANEL: BLUE WELCOME & BRANDING ================= */}
          <div className="relative w-full lg:w-[48%] xl:w-[47%] bg-gradient-to-br from-[#123B67] via-[#1D5FA7] to-[#14477c] p-5 sm:p-8 lg:p-12 text-white flex flex-col justify-center items-center text-center overflow-hidden min-h-[220px] sm:min-h-[280px] lg:min-h-[580px]">
            {/* Subtle background glow orbs */}
            <div className="pointer-events-none absolute -top-20 -left-20 h-64 w-64 rounded-full bg-white/5 blur-2xl" />
            <div className="pointer-events-none absolute -bottom-20 -right-20 h-64 w-64 rounded-full bg-[#3478C8]/25 blur-2xl" />

            {/* Centered Brand Presentation: Logo in middle with clean restored typography */}
            <div className="relative z-10 flex flex-col items-center justify-center space-y-3 sm:space-y-6 w-full max-w-[360px] my-auto">
              <div className="text-center">
                <span className="inline-block text-[11px] sm:text-xs font-semibold tracking-widest text-[#EAF2FB]/80 uppercase mb-0.5 sm:mb-1">
                  Welcome to
                </span>
                <h1 className="text-2xl sm:text-4xl lg:text-[42px] font-extrabold tracking-tight text-white leading-tight">
                  Dream Guard
                </h1>
              </div>

              {/* Logo in the middle */}
              <div className="flex items-center justify-center py-1 sm:py-2">
                <img
                  src="/dreamguard-brand.png"
                  alt="Dream Guard"
                  className="h-28 sm:h-44 lg:h-64 w-auto max-w-[180px] sm:max-w-[320px] object-contain drop-shadow-[0_20px_40px_rgba(18,59,103,0.5)] transition-transform hover:scale-105 duration-300"
                />
              </div>
            </div>

            {/* Desktop Scalloped Wave Boundary on the Right Edge (Image 1 style) */}
            <div className="hidden lg:block absolute top-0 bottom-0 -right-[1px] h-full w-24 xl:w-28 pointer-events-none overflow-hidden z-20">
              <svg
                className="h-full w-full"
                viewBox="0 0 120 900"
                preserveAspectRatio="none"
                fill="none"
              >
                {/* Shaded Layer 1 (Deep translucent blue ripple) */}
                <path
                  d="M 120 0 L 61 0 C 11 30.0, 11 120.0, 61 150 C -4 184.0, -4 286.0, 66 320 C 6 354.0, 6 456.0, 61 490 C -6 524.0, -6 626.0, 64 660 C 8 688.0, 8 772.0, 68 800 C -2 820.0, -2 880.0, 61 900 L 120 900 Z"
                  fill="#3478C8"
                  fillOpacity="0.35"
                />
                {/* Shaded Layer 2 (Light pale blue ripple) */}
                <path
                  d="M 120 0 L 73 0 C 23 30.0, 23 120.0, 73 150 C 8 184.0, 8 286.0, 78 320 C 18 354.0, 18 456.0, 73 490 C 6 524.0, 6 626.0, 76 660 C 20 688.0, 20 772.0, 80 800 C 10 820.0, 10 880.0, 73 900 L 120 900 Z"
                  fill="#EAF2FB"
                  fillOpacity="0.5"
                />
                {/* Front Layer 3 (Solid pure white scallops transitioning seamlessly into right panel) */}
                <path
                  d="M 120 0 L 85 0 C 35 30.0, 35 120.0, 85 150 C 20 184.0, 20 286.0, 90 320 C 30 354.0, 30 456.0, 85 490 C 18 524.0, 18 626.0, 88 660 C 32 688.0, 32 772.0, 92 800 C 22 820.0, 22 880.0, 85 900 L 120 900 Z"
                  fill="#FFFFFF"
                />
              </svg>
            </div>

            {/* Mobile Wave Boundary on the Bottom Edge (visible only on < lg screens) */}
            <div className="block lg:hidden absolute -bottom-[1px] left-0 right-0 w-full h-7 sm:h-10 pointer-events-none overflow-hidden z-20">
              <svg
                className="h-full w-full"
                viewBox="0 0 400 30"
                preserveAspectRatio="none"
                fill="none"
              >
                <path
                  d="M 0 10 Q 50 25, 100 10 T 200 10 T 300 10 T 400 10 L 400 30 L 0 30 Z"
                  fill="#3478C8"
                  fillOpacity="0.3"
                />
                <path
                  d="M 0 16 Q 50 30, 100 16 T 200 16 T 300 16 T 400 16 L 400 30 L 0 30 Z"
                  fill="#FFFFFF"
                />
              </svg>
            </div>
          </div>

          {/* ================= RIGHT PANEL: LOGIN & DEMO IDENTITIES ================= */}
          <div className="w-full lg:w-[52%] xl:w-[53%] bg-white p-5 sm:p-8 lg:p-11 flex flex-col justify-center">
            <div className="max-w-[440px] w-full mx-auto space-y-4 sm:space-y-5">

              {/* Header */}
              <div>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45]">
                  Sign In to Workspace
                </h2>
                <p className="mt-1 text-xs text-[#64748B]">
                  Enter your credentials
                </p>
              </div>

              {/* Login Form */}
              <form onSubmit={submit} className="space-y-3.5 sm:space-y-4">
                <div>
                  <label className="block text-[11px] font-bold tracking-wider text-[#172B45] uppercase mb-1.5 ml-2" htmlFor="u">
                    Username
                  </label>
                  <div className="relative">
                    <input
                      id="u"
                      className="w-full rounded-full border border-[#1D5FA7]/70 hover:border-[#1D5FA7] focus:border-[#1D5FA7] bg-white px-4 sm:px-5 py-2.5 pr-11 text-xs text-[#172B45] font-medium placeholder-[#64748B]/60 shadow-[0_0_10px_rgba(29,95,167,0.18)] focus:shadow-[0_0_16px_rgba(29,95,167,0.32)] focus:ring-2 focus:ring-[#1D5FA7]/20 outline-none transition-all [&:-webkit-autofill]:[box-shadow:0_0_0_1000px_white_inset] [&:-webkit-autofill]:[-webkit-text-fill-color:#172B45]"
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="e.g. admin_anita or support_ravi"
                      required
                    />
                    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-[#1D5FA7]">
                      <User className="h-4 w-4" />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-bold tracking-wider text-[#172B45] uppercase mb-1.5 ml-2" htmlFor="p">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="p"
                      type="password"
                      className="w-full rounded-full border border-[#1D5FA7]/70 hover:border-[#1D5FA7] focus:border-[#1D5FA7] bg-white px-4 sm:px-5 py-2.5 pr-11 text-xs text-[#172B45] font-medium placeholder-[#64748B]/60 shadow-[0_0_10px_rgba(29,95,167,0.18)] focus:shadow-[0_0_16px_rgba(29,95,167,0.32)] focus:ring-2 focus:ring-[#1D5FA7]/20 outline-none transition-all [&:-webkit-autofill]:[box-shadow:0_0_0_1000px_white_inset] [&:-webkit-autofill]:[-webkit-text-fill-color:#172B45]"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      required
                    />
                    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-[#1D5FA7]">
                      <Lock className="h-4 w-4" />
                    </div>
                  </div>
                </div>

                {error && <Alert tone="error">{error}</Alert>}

                {/* Pill-shaped Prominent Sign In Button */}
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-full bg-gradient-to-r from-[#123B67] via-[#1D5FA7] to-[#3478C8] hover:from-[#0f3054] hover:to-[#1D5FA7] py-2.5 px-6 text-xs font-semibold text-white shadow-md shadow-[#1D5FA7]/25 transition-all transform active:scale-[0.99] flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {busy ? (
                    <span className="flex items-center gap-2">
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Signing in...
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      Sign In <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  )}
                </button>
              </form>

              {/* Instant Demo Access Section */}
              <div className="border-t border-[#DCE5F0] pt-3.5 sm:pt-4 space-y-2.5 sm:space-y-3">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-xs font-bold text-[#172B45]">
                    <KeyRound className="h-3.5 w-3.5 text-[#1D5FA7]" /> Instant Demo Access
                  </span>
                </div>

                <div className="flex gap-1 rounded-full border border-[#DCE5F0] bg-[#EEF3F9] p-1">
                  {[
                    { id: "admin", label: "Admin" },
                    { id: "support", label: "Support" },
                    { id: "analyst", label: "Analyst" },
                  ].map((t) => (
                    <button
                      type="button"
                      key={t.id}
                      onClick={() => setActiveRoleTab(activeRoleTab === t.id ? "all" : t.id)}
                      className={`flex-1 rounded-full py-1 text-[11px] font-medium transition-all ${activeRoleTab === t.id
                          ? "bg-white text-[#123B67] shadow-sm font-bold"
                          : "text-[#64748B] hover:text-[#172B45]"
                        }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                <div className="space-y-2 pr-0.5">
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
                      className="flex min-h-[48px] w-full items-center justify-between gap-2 sm:gap-3 rounded-full border border-[#DCE5F0] bg-white px-3.5 sm:px-4 py-2 text-left transition-all hover:border-[#1D5FA7] hover:bg-[#F4F8FD] hover:shadow-[0_0_10px_rgba(29,95,167,0.18)] group cursor-pointer"
                    >
                      <div className="min-w-0 flex-1 pl-0.5">
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="text-[12px] font-bold text-[#172B45] group-hover:text-[#1D5FA7] transition-colors leading-tight truncate">
                            {a.label}
                          </span>
                          <span className="font-mono text-[9.5px] text-[#64748B] shrink-0">@{a.username}</span>
                        </div>
                        <div className="truncate text-[10px] text-[#64748B]">{a.email}</div>
                      </div>
                      <div className="shrink-0 pr-0.5">
                        <span
                          className={`rounded-full border px-2 sm:px-2.5 py-0.5 text-[9.5px] sm:text-[10px] font-bold uppercase tracking-wider bg-transparent ${ROLE_OUTLINE[a.role] ?? "border-[#1D5FA7] text-[#1D5FA7]"
                            }`}
                        >
                          {a.role}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

            </div>
          </div>

        </div>
      </div>
    </div>
  );
}