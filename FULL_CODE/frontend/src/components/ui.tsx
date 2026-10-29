import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";

export function Card({ className, children, title, subtitle, actions }: { className?: string; children: ReactNode; title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={clsx("card animate-fadein", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-ink-700/80 px-5 py-3.5">
          <div>
            {title && <h2 className="text-sm font-semibold text-fog-100">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-fog-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode };

export function Button({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-accent-strong text-white hover:bg-[#5558e8]",
        variant === "secondary" && "border border-ink-600 bg-ink-800 text-fog-100 hover:border-ink-500 hover:bg-ink-700",
        variant === "ghost" && "text-fog-300 hover:bg-ink-800 hover:text-fog-100",
        variant === "danger" && "border border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20",
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

const TONES: Record<string, string> = {
  neutral: "border-ink-500/60 bg-ink-700/60 text-fog-300",
  indigo: "border-accent/40 bg-accent/10 text-[#A8ADFF]",
  cyan: "border-cyan/40 bg-cyan/10 text-cyan",
  green: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  amber: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  red: "border-rose-400/40 bg-rose-400/10 text-rose-300",
  violet: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300",
};

export function Badge({ tone = "neutral", children, className, title }: { tone?: keyof typeof TONES | string; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4", TONES[tone] ?? TONES.neutral, className)}>
      {children}
    </span>
  );
}

export const SENS_TONE: Record<string, string> = {
  PII_HIGH: "red",
  PII_MEDIUM: "amber",
  FINANCIAL_CONFIDENTIAL: "violet",
  INTERNAL: "cyan",
  PUBLIC: "neutral",
};

export function SensBadge({ label }: { label?: string | null }) {
  if (!label) return <span className="text-fog-500">—</span>;
  return <Badge tone={SENS_TONE[label] ?? "neutral"}>{label.replace("_", " ")}</Badge>;
}

export const ACTION_TONE: Record<string, string> = {
  ALLOW: "green",
  PARTIAL: "amber",
  REDACT: "red",
  HASH: "indigo",
  GENERALIZE: "cyan",
  AGGREGATE_ONLY: "violet",
  BREAK_GLASS: "amber",
  DENY: "red",
};

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return <span className="text-fog-500">—</span>;
  return <Badge tone={ACTION_TONE[action] ?? "neutral"}>{action.replace("_", " ")}</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <Badge tone={outcome === "success" ? "green" : outcome === "denied" ? "red" : "amber"}>{outcome}</Badge>;
}

export function Stat({ label, value, hint, icon, tone = "indigo" }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "indigo" | "cyan" | "red" | "green" | "amber" }) {
  const ring = { indigo: "text-[#A8ADFF] bg-accent/10", cyan: "text-cyan bg-cyan/10", red: "text-rose-300 bg-rose-400/10", green: "text-emerald-300 bg-emerald-400/10", amber: "text-amber-300 bg-amber-400/10" }[tone];
  return (
    <div className="card animate-fadein p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-fog-400">{label}</span>
        {icon && <span className={clsx("grid h-7 w-7 place-items-center rounded-lg", ring)}>{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-fog-500">{hint}</div>}
    </div>
  );
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-ink-600 px-6 py-10 text-center">
      {icon && <div className="mb-3 text-fog-500">{icon}</div>}
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="mt-1 max-w-md text-xs text-fog-400">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-fog-400">
      <Loader2 className="h-4 w-4 animate-spin" /> {label ?? "Loading…"}
    </div>
  );
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "error" | "success" | "warn"; title?: ReactNode; children?: ReactNode }) {
  const map = {
    info: ["border-accent/30 bg-accent/5 text-[#C5C8FF]", <Info key="i" className="h-4 w-4" />],
    error: ["border-rose-400/30 bg-rose-500/5 text-rose-200", <AlertTriangle key="e" className="h-4 w-4" />],
    warn: ["border-amber-400/30 bg-amber-400/5 text-amber-200", <AlertTriangle key="w" className="h-4 w-4" />],
    success: ["border-emerald-400/30 bg-emerald-400/5 text-emerald-200", <CheckCircle2 key="s" className="h-4 w-4" />],
  } as const;
  const [cls, icon] = map[tone];
  return (
    <div className={clsx("flex gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm", cls)} role={tone === "error" ? "alert" : "status"}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={clsx(title && "mt-0.5", "text-[13px] opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" className={clsx("card w-full animate-fadein", wide ? "max-w-4xl" : "max-w-lg")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
          <h3 className="text-sm font-semibold">{title}</h3>
          <button aria-label="Close" onClick={onClose} className="rounded-md p-1 text-fog-400 hover:bg-ink-700 hover:text-fog-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[] }) {
  return (
    <div role="tablist" className="inline-flex rounded-lg border border-ink-600 bg-ink-900 p-0.5">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx("rounded-md px-3 py-1.5 text-xs font-medium transition-colors", value === it.value ? "bg-ink-700 text-fog-100" : "text-fog-400 hover:text-fog-100")}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-fog-400">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Value({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="text-fog-500 italic">null</span>;
  const s = String(v);
  if (s === "[REDACTED]") return <span className="rounded bg-rose-400/10 px-1 text-rose-300">[REDACTED]</span>;
  if (s.startsWith("hm_k")) return <span className="text-[#A8ADFF]">{s}</span>;
  if (/[*X]{3,}/.test(s)) return <span className="text-amber-200">{s}</span>;
  return <span>{s}</span>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <Alert tone="error">{msg}</Alert>;
}
