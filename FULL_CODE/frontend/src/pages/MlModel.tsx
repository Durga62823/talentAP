import { useQuery } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Badge, Card, ErrorText, PageHeader, Spinner, Tabs } from "../components/ui";
import { api, fmtTime } from "../lib/api";

type Detect = { precision: number; recall: number; f1: number; missed_sensitive: number; false_alarms: number };
type Card = any;

const pct = (v: number | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

function Compare({ title, subtitle, rows }: { title: string; subtitle: string; rows: { label: string; accuracy: number; det: Detect; highlight?: boolean }[] }) {
  return (
    <Card title={title} subtitle={subtitle}>
      <table className="w-full">
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
            <tr key={r.label} className={r.highlight ? "bg-accent/5" : ""}>
              <td className="td font-medium">{r.label}</td>
              <td className="td text-right tabular-nums">{pct(r.accuracy)}</td>
              <td className="td text-right tabular-nums">{pct(r.det.recall)}</td>
              <td className="td text-right tabular-nums">
                <span className={r.det.missed_sensitive ? "text-rose-300" : "text-emerald-300"}>{r.det.missed_sensitive}</span>
              </td>
              <td className="td text-right tabular-nums text-fog-300">{r.det.false_alarms}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
        <Alert tone="warn" title="No trained model found">
          Train it with <code>python -m app.ml.train</code> in <code>FULL_CODE/backend</code>. Until then scans use the rule-based engine (and Gemini, if configured).
        </Alert>
      </div>
    );

  const syn = card.synthetic_test;
  const sf = card.saffron_evaluation;
  const calib = syn.calibration.bins.map((b: any) => ({ ...b, ideal: b.mean_confidence }));
  return (
    <div className="space-y-4">
      <PageHeader
        title={<span className="flex items-center gap-2"><BrainCircuit className="h-5 w-5 text-[#A8ADFF]" /> ML Model · {card.version}</span> as any}
        description="A PII column classifier trained on this server from fully synthetic data. It runs in-process: no API key, no network, and no data leaves the server."
      />
      {!q.data?.available && (
        <Alert tone="error" title="Model unavailable">{q.data?.error} Scans keep using the rule-based engine.</Alert>
      )}
      <Alert tone="info" title="How it is used">
        During a scan with "ML model" ticked, the model's verdict is applied <b>upgrade-only</b>: only when it is more sensitive than the current classification, its
        calibrated confidence is at least {Math.round((q.data?.min_confidence ?? 0.8) * 100)}%, and no human has reviewed the column. It can never weaken masking.
      </Alert>

      <div className="grid gap-4 xl:grid-cols-2">
        <Compare
          title="Unseen schemas (synthetic test)"
          subtitle={`${syn.per_class.reduce((a: number, c: any) => a + c.support, 0)} columns whose names never appear in training`}
          rows={[
            { label: "ML model", accuracy: syn.accuracy, det: syn.ml_sensitive_detection, highlight: true },
            { label: "Rule engine", accuracy: syn.rules.accuracy, det: syn.rules.sensitive_detection },
          ]}
        />
        <Compare
          title="Official Saffron Bank schema"
          subtitle={`${sf.columns} columns, hand-labelled; never used for training`}
          rows={[
            { label: "ML model alone", accuracy: sf.ml.accuracy, det: sf.ml.sensitive_detection },
            { label: "Rule engine", accuracy: sf.rules.accuracy, det: sf.rules.sensitive_detection },
            { label: "Rules + ML (upgrade-only, as deployed)", accuracy: sf.combined_upgrade_only.accuracy, det: sf.combined_upgrade_only.sensitive_detection, highlight: true },
          ]}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Calibration" subtitle={`Expected calibration error ${syn.calibration.expected_calibration_error} (synthetic test). On the diagonal = "90% confident" is right ~90% of the time.`}>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={calib} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#1f2a44" strokeDasharray="3 3" />
                <XAxis dataKey="mean_confidence" type="number" domain={[0, 1]} tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <YAxis domain={[0, 1]} tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #1f2a44", fontSize: 12 }} formatter={(v: any) => `${Math.round(Number(v) * 100)}%`} />
                <Line dataKey="ideal" name="perfect calibration" stroke="#64748b" strokeDasharray="4 4" dot={false} />
                <Line dataKey="accuracy" name="observed accuracy" stroke="#8b93ff" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="What the model relies on" subtitle="Permutation importance on the synthetic test (accuracy drop when a feature is shuffled)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={card.feature_importance.slice(0, 10)} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="#1f2a44" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis type="category" dataKey="feature" width={210} tick={{ fill: "#cbd5e1", fontSize: 11 }}
                  tickFormatter={(v: string) => v.replace(/_match_ratio$/, "").replace(/_/g, " ")} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #1f2a44", fontSize: 12 }} />
                <Bar dataKey="importance" fill="#8b93ff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card title="Per-category scores (synthetic test, unseen names)" subtitle={`Accuracy ${pct(syn.accuracy)} · macro-F1 ${syn.macro_f1}`}>
        <div className="grid gap-x-6 md:grid-cols-2">
          {[0, 1].map((half) => (
            <table key={half} className="w-full">
              <thead><tr><th className="th">Category</th><th className="th text-right">Precision</th><th className="th text-right">Recall</th><th className="th text-right">F1</th><th className="th text-right">Columns</th></tr></thead>
              <tbody>
                {syn.per_class.filter((_: any, i: number) => (i < Math.ceil(syn.per_class.length / 2)) === (half === 0)).map((c: any) => (
                  <tr key={c.category}>
                    <td className="td mono text-xs">{c.category}</td>
                    <td className="td text-right tabular-nums">{c.precision.toFixed(2)}</td>
                    <td className="td text-right tabular-nums">{c.recall.toFixed(2)}</td>
                    <td className="td text-right tabular-nums">{c.support ? c.f1.toFixed(2) : <span className="text-fog-500" title="No test columns for this category">n/a</span>}</td>
                    <td className="td text-right tabular-nums text-fog-400">{c.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
      </Card>

      <Card
        title="Saffron Bank columns: ML vs rules"
        subtitle="Labels are the team's own; ambiguous columns accept several categories"
        actions={<Tabs value={colFilter} onChange={setColFilter} items={[{ value: "wrong", label: "Disagreements" }, { value: "all", label: `All ${sf.columns}` }]} />}
      >
        <div className="-mx-5 -mb-5 max-h-[420px] overflow-auto">
          <table className="w-full">
            <thead><tr><th className="th">Column</th><th className="th">Label</th><th className="th">ML prediction</th><th className="th">Rule engine</th></tr></thead>
            <tbody>
              {cols.map((c: any) => (
                <tr key={`${c.table}.${c.column}`}>
                  <td className="td mono text-xs">{c.table}.<b className="text-fog-100">{c.column}</b></td>
                  <td className="td text-xs">{c.acceptable.join(" / ")}</td>
                  <td className="td text-xs">
                    <Badge tone={c.ml_correct ? "green" : "red"}>{c.ml}</Badge> <span className="text-fog-500">{Math.round(c.ml_confidence * 100)}%</span>
                  </td>
                  <td className="td text-xs"><Badge tone={c.rule_correct ? "green" : "red"}>{c.rule}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Training">
          <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
            <dt className="text-fog-400">Trained</dt><dd>{fmtTime(card.trained_at)} · scikit-learn {card.sklearn_version} · {card.training_seconds}s</dd>
            <dt className="text-fog-400">Data</dt><dd>{card.training_data.columns.toLocaleString()} columns, {card.training_data.source}</dd>
            <dt className="text-fog-400">Test split</dt><dd>{card.training_data.test_split}</dd>
            <dt className="text-fog-400">Held out</dt><dd>{card.training_data.excluded_names} (never seen verbatim in training)</dd>
            <dt className="text-fog-400">Algorithm</dt><dd className="text-fog-300">{card.algorithm}</dd>
          </dl>
        </Card>
        <Card title="Limitations">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-fog-300">
            {card.caveats.map((c: string) => <li key={c}>{c}</li>)}
          </ul>
        </Card>
      </div>
    </div>
  );
}
