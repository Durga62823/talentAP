import { ShieldCheck, Ticket, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { AccessContextResult, ColumnDecision, Purpose } from "../lib/api";
import { SUPPORT_PURPOSES, TICKET_RE, clearPurposeBinding, purposeLabel, setPurposeBinding, usePurposeBinding } from "../lib/purpose";
import { Badge, Button } from "./ui";

const MASK_LABEL: Record<string, [string, string]> = {
  ALLOW: ["Visible", "green"],
  PARTIAL: ["Partially Masked", "amber"],
  GENERALIZE: ["Generalized", "cyan"],
  HASH: ["Pseudonymised", "violet"],
  REDACT: ["Redacted", "red"],
  AGGREGATE_ONLY: ["Aggregate only", "red"],
};

/** The masking actually applied to a column in a query result (server decision, not an assumption). */
export function MaskBadge({ d, className }: { d?: ColumnDecision; className?: string }) {
  if (!d) return null;
  if (d.abac_granted) {
    return <Badge tone="green" className={className} title={d.reason}>Unmasked · purpose-bound</Badge>;
  }
  const [label, tone] = MASK_LABEL[d.action] ?? [d.action, "neutral"];
  return <Badge tone={tone} className={className} title={`${d.policy_name ?? "default"} — ${d.reason}`}>{label}</Badge>;
}

export function decisionOf(body: any, column: string): ColumnDecision | undefined {
  return (body?.decisions as ColumnDecision[] | undefined)?.find((d) => d.name === column);
}

/** "Session Purpose & Ticket Binding" banner. Applying the binding re-runs the page's queries with
 *  the purpose headers; `results` are the access contexts those queries came back with. */
export function PurposeBanner({ results }: { results: (AccessContextResult | null | undefined)[] }) {
  const binding = usePurposeBinding();
  const [draft, setDraft] = useState(binding);
  useEffect(() => setDraft(binding), [binding]);

  const ticket = draft.ticketId.trim().toUpperCase();
  const ticketOk = !ticket || TICKET_RE.test(ticket);
  const dirty = draft.purpose !== binding.purpose || ticket !== binding.ticketId;
  const bound = !!binding.purpose && !!binding.ticketId;
  const ctxs = results.filter(Boolean) as AccessContextResult[];
  const granted = [...new Set(ctxs.flatMap((c) => c.abac_granted_columns))];
  const rejected = [...new Set(ctxs.flatMap((c) => c.rejected_attributes))];

  return (
    <div className="rounded-xl border border-[#DCE5F0] bg-white p-4 shadow-card">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-[#1D5FA7]" />
          <span className="text-sm font-semibold text-[#172B45]">Session Purpose & Ticket Binding</span>
        </div>
        {bound ? (
          <Badge tone="green">Bound · {purposeLabel(binding.purpose)} · {binding.ticketId}</Badge>
        ) : (
          <Badge tone="neutral">Baseline role masking</Badge>
        )}
      </div>

      <form
        className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          if (ticketOk) setPurposeBinding({ purpose: draft.purpose, ticketId: ticket });
        }}
      >
        <select
          className="input text-xs"
          aria-label="Purpose"
          value={draft.purpose}
          onChange={(e) => setDraft({ ...draft, purpose: e.target.value as Purpose | "" })}
        >
          <option value="">No purpose declared</option>
          {SUPPORT_PURPOSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <div className="relative">
          <Ticket className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#64748B]" />
          <input
            className={`input pl-8 font-mono text-xs uppercase ${ticketOk ? "" : "border-rose-300"}`}
            aria-label="Support Ticket ID"
            placeholder="Support Ticket ID, e.g. INC-8821"
            maxLength={32}
            value={draft.ticketId}
            onChange={(e) => setDraft({ ...draft, ticketId: e.target.value })}
          />
        </div>
        <Button size="sm" variant="primary" type="submit" disabled={!dirty || !ticketOk}>Apply binding</Button>
        <Button size="sm" variant="ghost" type="button" disabled={!binding.purpose && !binding.ticketId}
                icon={<X className="h-3.5 w-3.5" />} onClick={clearPurposeBinding}>Clear</Button>
      </form>

      <div className="mt-2.5 text-[11px] leading-relaxed text-[#64748B]">
        {!ticketOk ? (
          <span className="text-rose-700">Ticket IDs look like INC-8821 or TICKET-10492.</span>
        ) : granted.length ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-emerald-800">Purpose-based unmasking active on:</span>
            {granted.map((c) => <Badge key={c} tone="green" className="font-mono">{c}</Badge>)}
          </span>
        ) : bound ? (
          "No column in this view is unmasked for this purpose; your role's baseline masking applies."
        ) : (
          "Declare why you are accessing this customer and the ticket you are working. Permitted fields are unmasked only while both are bound, and every query records them in the tamper-evident audit chain."
        )}
        {rejected.length > 0 && <span className="ml-1 text-rose-700">Ignored by the server: {rejected.join(", ")}.</span>}
      </div>
    </div>
  );
}
