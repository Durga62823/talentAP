import { useQuery } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Badge, Card, ErrorText, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";

type Detect = { precision: number; recall: number; f1: number; missed_sensitive: number; false_alarms: number };
type Card = any;

const pct = (v: number | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

function Compare({ title, subtitle, rows }: { title: string; subtitle: string; rows: { label: string; accuracy: number; det: Detect; highlight?: boolean }[] }) {
  return (
    <Card title={title} subtitle={subtitle}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[500px]">
          <thead>
            <tr>
              <th className="th">Engine</th>
              <th className="th text-right">Category accuracy</th>
              <th className="th text-right">Sensitive recall</th>
              <th className="th text-right">Sensitive missed</th>
              <th className="th text-right">False alarms</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className={r.highlight ? "bg-[#EAF2FB]/60" : "hover:bg-[#F4F8FD]"}>
                <td className="td font-semibold text-[#172B45]">{r.label}</td>
                <td className="td text-right tabular-nums text-[#172B45]">{pct(r.accuracy)}</td>
                <td className="td text-right tabular-nums text-[#172B45]">{pct(r.det.recall)}</td>
                <td className="td text-right tabular-nums">
                  <span className={r.det.missed_sensitive ? "text-rose-700 font-semibold" : "text-emerald-700 font-semibold"}>{r.det.missed_sensitive}</span>
                </td>
                <td className="td text-right tabular-nums text-[#64748B]">{r.det.false_alarms}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function MlModelPage() {
  const q = useQuery({ queryKey: ["ml-model-card"], queryFn: () => api<{ available: boolean; error: string; min_confidence: number; card: Card | null }>("/api/ml/model-card") });
  const [colFilter, setColFilter] = useState<"wrong" | "all">("wrong");
  const card = q.data?.card;
  const cols = useMemo(() => {
    const all = card?.saffron_evaluation?.columns_detail ?? [];
    return colFilter === "wrong" ? all.filter((c: any) => !c.ml_correct || !c.rule_correct) : all;
  }, [card, colFilter]);

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorText error={q.error} />;
  if (!card)
    return (
      <div>
        <PageHeader title="ML Model" description="Locally trained PII column classifier." />
      </div>
    );

  const syn = card.synthetic_test;
  const sf = card.saffron_evaluation;
  const calib = syn.calibration.bins.map((b: any) => ({ ...b, ideal: b.mean_confidence }));
  const tooltipStyle = {
    background: "#FFFFFF",
    border: "1px solid #DCE5F0",
    borderRadius: 8,
    fontSize: 12,
    color: "#172B45",
    boxShadow: "0 4px 12px rgba(18,59,103,0.08)",
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title={<span className="flex items-center gap-2"><BrainCircuit className="h-6 w-6 text-[#1D5FA7]" /> ML Model · {card.version}</span> as any}
      />
      {!q.data?.available && (
        <Alert tone="error" title="Model unavailable">{q.data?.error} Scans keep using the rule-based engine.</Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Compare
          title="Unseen schemas (synthetic test)"
          subtitle={`${syn.per_class.reduce((a: number, c: any) => a + c.support, 0)} columns whose names never appeared in training`}
          rows={[
            { label: "ML model", accuracy: syn.accuracy, det: syn.ml_sensitive_detection, highlight: true },
            { label: "Rule engine", accuracy: syn.rules.accuracy, det: syn.rules.sensitive_detection },
          ]}
        />
        <Compare
          title="Official Saffron Bank schema"
          subtitle={`${sf.columns} columns, hand-labelled; never used during training`}
          rows={[
            { label: "ML model alone", accuracy: sf.ml.accuracy, det: sf.ml.sensitive_detection },
            { label: "Rule engine", accuracy: sf.rules.accuracy, det: sf.rules.sensitive_detection },
            { label: "Rules + ML (upgrade-only)", accuracy: sf.combined_upgrade_only.accuracy, det: sf.combined_upgrade_only.sensitive_detection, highlight: true },
          ]}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Calibration" subtitle={`Expected calibration error ${syn.calibration.expected_calibration_error}. Diagonal indicates ideal statistical calibration.`}>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={calib} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#DCE5F0" strokeDasharray="3 3" />
                <XAxis dataKey="mean_confidence" type="number" domain={[0, 1]} tick={{ fill: "#64748B", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <YAxis domain={[0, 1]} tick={{ fill: "#64748B", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => `${Math.round(Number(v) * 100)}%`} />
                <Line dataKey="ideal" name="perfect calibration" stroke="#64748B" strokeDasharray="4 4" dot={false} />
                <Line dataKey="accuracy" name="observed accuracy" stroke="#1D5FA7" strokeWidth={2.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Feature importance" subtitle="Permutation importance on synthetic test (accuracy drop when feature is shuffled)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={card.feature_importance.slice(0, 10)} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="#DCE5F0" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#64748B", fontSize: 11 }} />
                <YAxis type="category" dataKey="feature" width={180} tick={{ fill: "#172B45", fontSize: 11 }}
                  tickFormatter={(v: string) => v.replace(/_match_ratio$/, "").replace(/_/g, " ")} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="importance" fill="#1D5FA7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card title="Per-category scores (synthetic test, unseen names)" subtitle={`Accuracy ${pct(syn.accuracy)} · macro-F1 ${syn.macro_f1}`}>
        <div className="grid gap-6 md:grid-cols-2">
          {[0, 1].map((half) => (
            <div key={half} className="overflow-x-auto">
              <table className="w-full min-w-[320px]">
                <thead><tr><th className="th">Category</th><th className="th text-right">Precision</th><th className="th text-right">Recall</th><th className="th text-right">F1</th><th className="th text-right">Columns</th></tr></thead>
                <tbody>
                  {syn.per_class.filter((_: any, i: number) => (i < Math.ceil(syn.per_class.length / 2)) === (half === 0)).map((c: any) => (
                    <tr key={c.category} className="hover:bg-[#F4F8FD]">
                      <td className="td mono text-xs font-semibold text-[#172B45]">{c.category}</td>
                      <td className="td text-right tabular-nums text-[#172B45]">{c.precision.toFixed(2)}</td>
                      <td className="td text-right tabular-nums text-[#172B45]">{c.recall.toFixed(2)}</td>
                      <td className="td text-right tabular-nums text-[#172B45]">{c.support ? c.f1.toFixed(2) : <span className="text-[#64748B]" title="No test columns">n/a</span>}</td>
                      <td className="td text-right tabular-nums text-[#64748B]">{c.support}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </Card>

      <Card
        title="Saffron Bank columns: ML vs rules"
        subtitle="Validation against official Saffron Bank reference ground-truth labels"
        actions={<Tabs value={colFilter} onChange={setColFilter} items={[{ value: "wrong", label: "Disagreements" }, { value: "all", label: `All ${sf.columns}` }]} />}
      >
        <div className="-mx-4 sm:-mx-5 -mb-4 sm:-mb-5 max-h-[420px] overflow-x-auto">
          <table className="w-full min-w-[650px]">
            <thead><tr><th className="th">Column</th><th className="th">Label</th><th className="th">ML prediction</th><th className="th">Rule engine</th></tr></thead>
            <tbody>
              {cols.map((c: any) => (
                <tr key={`${c.table}.${c.column}`} className="hover:bg-[#F4F8FD]">
                  <td className="td mono text-xs text-[#172B45]">{c.table}.<b className="font-semibold text-[#1D5FA7]">{c.column}</b></td>
                  <td className="td text-xs text-[#172B45]">{c.acceptable.join(" / ")}</td>
                  <td className="td text-xs">
                    <Badge tone={c.ml_correct ? "green" : "red"}>{c.ml}</Badge> <span className="text-[#64748B] font-medium ml-1">{Math.round(c.ml_confidence * 100)}%</span>
                  </td>
                  <td className="td text-xs"><Badge tone={c.rule_correct ? "green" : "red"}>{c.rule}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
