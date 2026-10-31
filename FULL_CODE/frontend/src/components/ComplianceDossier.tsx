import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCheck2, Fingerprint, ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { apiBlob, api, fmtTime, saveBlob, type ComplianceSummary, type DossierFormat, type DossierReceipt, type Framework } from "../lib/api";
import { Badge, Button, Card, ErrorText, Spinner, Tabs } from "./ui";

const PACKS: { id: Framework; title: string; covers: string }[] = [
  { id: "DPDP", title: "DPDP Act 2023 Compliance Pack", covers: "Data Principal access summary · purpose distribution · break-glass log · zero-mutation proof" },
  { id: "RBI", title: "RBI Cyber Security Annexure", covers: "Administrator actions · failed access attempts · break-glass justifications · hash-chain certificate" },
  { id: "PCI_DSS", title: "PCI-DSS v4.0 Card Masking Attestation", covers: "PAN egress masking per role (worst case, incl. purpose grants) · observed egress · zero-cleartext check" },
];

function Kpi({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#64748B]">{label}</div>
      <div className={`mt-0.5 text-sm font-bold tabular-nums ${tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-rose-700" : "text-[#172B45]"}`}>{value}</div>
    </div>
  );
}

/** One-click signed regulatory dossiers. Each download is SHA-256 hashed, Ed25519 signed and
 *  recorded in the audit chain; the receipt links to that ledger entry. */
export function ComplianceDossier({ onOpenEvent }: { onOpenEvent: (id: string) => void }) {
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ["compliance-summary"], queryFn: () => api<ComplianceSummary>("/api/compliance/reports/summary") });
  const [format, setFormat] = useState<DossierFormat>("pdf");
  const [receipt, setReceipt] = useState<DossierReceipt | null>(null);

  const generate = useMutation({
    mutationFn: async (framework: Framework): Promise<DossierReceipt> => {
      const { blob, headers } = await apiBlob("/api/compliance/reports/generate", { body: { framework, format } });
      const sha256 = headers.get("x-dossier-sha256") ?? "";
      const named = /filename="([^"]+)"/.exec(headers.get("content-disposition") ?? "")?.[1];
      const filename = named ?? `dreamguard-${framework.toLowerCase().replace("_", "-")}-dossier-${sha256.slice(0, 12)}.${format}`;
      saveBlob(blob, filename);
      return { framework, format, sha256, signature: headers.get("x-dossier-signature") ?? "", auditEventId: headers.get("x-audit-event-id") ?? "", filename, at: new Date().toISOString() };
    },
    onSuccess: (r) => {
      setReceipt(r);
      qc.invalidateQueries({ queryKey: ["compliance-summary"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const s = summary.data;
  const status = Object.fromEntries((s?.frameworks ?? []).map((f) => [f.id, f]));

  return (
    <Card
      className="mb-4"
      title="Export Regulatory Compliance Dossier"
      subtitle="Signed evidence packs built from the hash-chained audit ledger, integrity runs and the live policy set"
      actions={<Tabs value={format} onChange={setFormat} items={[{ value: "pdf", label: "PDF" }, { value: "csv", label: "CSV" }, { value: "json", label: "JSON" }]} />}
    >
      {summary.isLoading ? <Spinner label="Collecting evidence…" /> : summary.error ? <ErrorText error={summary.error} /> : s && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <Kpi label="Audit chain" tone={s.ledger.chain_valid ? "good" : "bad"}
               value={s.ledger.chain_valid ? `Intact · ${s.ledger.events}` : `Broken at #${s.ledger.broken_at_seq}`} />
          <Kpi label="PAN cleartext (non-admin)" tone={s.pci.non_privileged_cleartext_egress ? "bad" : "good"} value={s.pci.non_privileged_cleartext_egress} />
          <Kpi label="Failed access attempts" value={s.failed_access} />
          <Kpi label="Break-glass events" value={s.break_glass} />
          <Kpi label="Purpose-bound unmasking" value={s.purpose_bound_elevations} />
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        {PACKS.map((p) => {
          const st = status[p.id];
          return (
            <div key={p.id} className="flex flex-col justify-between gap-3 rounded-lg border border-[#DCE5F0] bg-white p-3.5">
              <div>
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[13px] font-semibold text-[#172B45]">{p.title}</span>
                  {st && (
                    <Badge tone={st.status === "PASS" ? "green" : "red"} title={st.findings.join("\n") || "No findings"}>
                      {st.status === "PASS" ? "Pass" : "Attention"}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-[#64748B]">{p.covers}</p>
                {st?.findings.length ? <ul className="mt-1.5 list-disc pl-4 text-[11px] text-rose-700">{st.findings.map((f) => <li key={f}>{f}</li>)}</ul> : null}
              </div>
              <Button variant="primary" size="sm" icon={<Download className="h-3.5 w-3.5" />}
                      loading={generate.isPending && generate.variables === p.id} disabled={generate.isPending}
                      onClick={() => generate.mutate(p.id)}>
                Generate {format.toUpperCase()}
              </Button>
            </div>
          );
        })}
      </div>
      <ErrorText error={generate.error} />

      {receipt && (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-900">
          <div className="flex flex-wrap items-center gap-2 font-semibold">
            <FileCheck2 className="h-4 w-4 text-emerald-700" /> {receipt.filename}
            <Badge tone="green"><ShieldCheck className="h-3 w-3" /> SHA-256 · Ed25519 signed</Badge>
            <span className="font-normal text-emerald-800">{fmtTime(receipt.at)}</span>
          </div>
          <div className="mt-2 flex items-start gap-1.5">
            <Fingerprint className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-700" />
            <code className="break-all font-mono text-[11px]">{receipt.sha256}</code>
          </div>
          <div className="mt-1.5 text-[11px] text-emerald-800">
            The hash covers the dossier's canonical JSON and is recorded in{" "}
            <button type="button" className="font-semibold underline" onClick={() => onOpenEvent(receipt.auditEventId)}>its audit ledger entry</button>;
            verify any copy offline with the public key from <code className="font-mono">/api/compliance/reports/public-key</code>.
          </div>
        </div>
      )}
      {s && !s.ledger.chain_valid && (
        <div className="mt-3 flex items-center gap-1.5 text-[11px] text-rose-700"><ShieldX className="h-3.5 w-3.5" /> Dossiers generated now will report the broken chain as a finding.</div>
      )}
    </Card>
  );
}
