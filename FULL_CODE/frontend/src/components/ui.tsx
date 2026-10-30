import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";

export function Card({
  className,
  children,
  title,
  subtitle,
  actions,
}: {
  className?: string;
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={clsx("card animate-fadein bg-white border border-[#DCE5F0] rounded-xl shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3 border-b border-[#DCE5F0] bg-white px-4 sm:px-5 py-3 sm:py-3.5 rounded-t-xl">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold tracking-tight text-[#172B45]">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-[#64748B]">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className="p-3.5 sm:p-5">{children}</div>
    </section>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1D5FA7] disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "min-h-[36px] px-3 py-1.5 text-xs" : "min-h-[42px] px-4 py-2 text-sm",
        variant === "primary" &&
          "bg-[#1D5FA7] text-white hover:bg-[#123B67] active:bg-[#0D2B4D] shadow-sm",
        variant === "secondary" &&
          "border border-[#DCE5F0] bg-white text-[#172B45] hover:bg-[#F4F8FD] hover:border-[#3478C8] shadow-sm",
        variant === "ghost" && "text-[#172B45] hover:bg-[#EAF2FB] hover:text-[#123B67]",
        variant === "danger" &&
          "border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 shadow-sm",
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin text-current" /> : icon}
      {children}
    </button>
  );
}

const TONES: Record<string, string> = {
  neutral: "border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]",
  indigo: "border-[#DCE5F0] bg-[#EAF2FB] text-[#123B67] font-semibold",
  cyan: "border-[#DCE5F0] bg-[#EEF3F9] text-[#1D5FA7] font-medium",
  green: "border-emerald-200 bg-emerald-50 text-emerald-800 font-medium",
  amber: "border-amber-200 bg-amber-50 text-amber-800 font-medium",
  red: "border-rose-200 bg-rose-50 text-rose-800 font-medium",
  violet: "border-[#DCE5F0] bg-[#EAF2FB] text-[#123B67] font-medium",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: keyof typeof TONES | string;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-medium leading-4 shadow-sm",
        TONES[tone] ?? TONES.neutral,
        className,
      )}
    >
      {children}
    </span>
  );
}

export const SENS_TONE: Record<string, string> = {
  PII_HIGH: "red",
  PII_MEDIUM: "amber",
  FINANCIAL_CONFIDENTIAL: "indigo",
  INTERNAL: "cyan",
  PUBLIC: "neutral",
};

export function SensBadge({ label }: { label?: string | null }) {
  if (!label) return <span className="text-[#64748B]">—</span>;
  return <Badge tone={SENS_TONE[label] ?? "neutral"}>{label.replace("_", " ")}</Badge>;
}

export const ACTION_TONE: Record<string, string> = {
  ALLOW: "green",
  PARTIAL: "amber",
  REDACT: "red",
  HASH: "indigo",
  GENERALIZE: "cyan",
  AGGREGATE_ONLY: "indigo",
  BREAK_GLASS: "amber",
  DENY: "red",
};

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return <span className="text-[#64748B]">—</span>;
  return <Badge tone={ACTION_TONE[action] ?? "neutral"}>{action.replace("_", " ")}</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return (
    <Badge tone={outcome === "success" ? "green" : outcome === "denied" ? "red" : "amber"}>
      {outcome}
    </Badge>
  );
}

export function Stat({
  label,
  value,
  hint,
  icon,
  tone = "indigo",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "indigo" | "cyan" | "red" | "green" | "amber";
}) {
  const ring = {
    indigo: "text-[#123B67] bg-[#EAF2FB] border border-[#DCE5F0]",
    cyan: "text-[#1D5FA7] bg-[#EEF3F9] border border-[#DCE5F0]",
    red: "text-rose-700 bg-rose-50 border border-rose-200",
    green: "text-emerald-700 bg-emerald-50 border border-emerald-200",
    amber: "text-amber-700 bg-amber-50 border border-amber-200",
  }[tone];

  return (
    <div className="card animate-fadein p-4 sm:p-5 bg-white border border-[#DCE5F0] rounded-xl shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-[#64748B]">{label}</span>
        {icon && <span className={clsx("grid h-8 w-8 place-items-center rounded-lg shadow-sm", ring)}>{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-[#172B45]">{value}</div>
      {hint && <div className="mt-1 text-xs text-[#64748B]">{hint}</div>}
    </div>
  );
}

export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[#DCE5F0] bg-[#F4F8FD]/50 px-6 py-12 text-center">
      {icon && <div className="mb-3 text-[#1D5FA7]">{icon}</div>}
      <div className="text-sm font-semibold text-[#172B45]">{title}</div>
      {children && <div className="mt-1 max-w-md text-xs text-[#64748B]">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm font-medium text-[#1D5FA7]">
      <Loader2 className="h-4 w-4 animate-spin text-[#1D5FA7]" /> {label ?? "Loading…"}
    </div>
  );
}

export function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "error" | "success" | "warn";
  title?: ReactNode;
  children?: ReactNode;
}) {
  const map = {
    info: [
      "border-[#DCE5F0] bg-[#EAF2FB] text-[#123B67]",
      <Info key="i" className="h-4 w-4 text-[#1D5FA7]" />,
    ],
    error: [
      "border-rose-200 bg-rose-50 text-rose-800",
      <AlertTriangle key="e" className="h-4 w-4 text-rose-600" />,
    ],
    warn: [
      "border-amber-200 bg-amber-50 text-amber-800",
      <AlertTriangle key="w" className="h-4 w-4 text-amber-600" />,
    ],
    success: [
      "border-emerald-200 bg-emerald-50 text-emerald-800",
      <CheckCircle2 key="s" className="h-4 w-4 text-emerald-600" />,
    ],
  } as const;
  const [cls, icon] = map[tone];
  return (
    <div
      className={clsx("flex gap-3 rounded-lg border px-4 py-3 text-sm shadow-sm", cls)}
      role={tone === "error" ? "alert" : "status"}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={clsx(title && "mt-0.5", "text-[13px] leading-relaxed")}>{children}</div>}
      </div>
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-3 sm:p-4 pt-4 sm:pt-[6vh] backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          "card w-full max-h-[92vh] flex flex-col animate-fadein bg-white border border-[#DCE5F0] rounded-xl shadow-modal overflow-hidden",
          wide ? "max-w-4xl" : "max-w-lg",
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[#DCE5F0] bg-[#F4F8FD]/50 px-4 sm:px-5 py-3 sm:py-3.5 rounded-t-xl">
          <h3 className="text-sm font-semibold tracking-tight text-[#172B45] truncate pr-2">{title}</h3>
          <button
            aria-label="Close"
            onClick={onClose}
            className="rounded-lg p-1.5 text-[#64748B] hover:bg-[#EAF2FB] hover:text-[#123B67] transition-colors shrink-0"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-4 sm:p-5 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: ReactNode }[];
}) {
  return (
    <div
      role="tablist"
      className="inline-flex max-w-full flex-wrap gap-0.5 rounded-lg border border-[#DCE5F0] bg-[#EEF3F9] p-1"
    >
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "rounded-md px-2.5 sm:px-3.5 py-1 text-xs font-medium transition-all whitespace-nowrap",
            value === it.value
              ? "bg-white text-[#123B67] font-semibold shadow-sm"
              : "text-[#64748B] hover:text-[#172B45]",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 sm:mb-6 flex flex-col sm:flex-row sm:items-end justify-between gap-3 sm:gap-4 border-b border-[#DCE5F0] pb-4">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-xs sm:text-sm text-[#64748B] leading-relaxed">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:gap-2.5 shrink-0">{actions}</div>}
    </div>
  );
}

export function Value({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="text-[#64748B] italic">null</span>;
  const s = String(v);
  if (s === "[REDACTED]")
    return (
      <span className="rounded bg-rose-50 border border-rose-200 px-1.5 py-0.5 text-xs font-mono font-semibold text-rose-700">
        [REDACTED]
      </span>
    );
  if (s.startsWith("hm_k"))
    return (
      <span className="rounded bg-[#EAF2FB] border border-[#DCE5F0] px-1.5 py-0.5 text-xs font-mono font-medium text-[#123B67]">
        {s}
      </span>
    );
  if (/[*X]{3,}/.test(s))
    return (
      <span className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-xs font-mono font-semibold text-amber-800">
        {s}
      </span>
    );
  return <span className="text-[#172B45]">{s}</span>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <Alert tone="error">{msg}</Alert>;
}
