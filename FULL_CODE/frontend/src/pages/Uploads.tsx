import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, FileUp, Table2, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ActionBadge, Alert, Badge, Button, Card, Empty, ErrorText, PageHeader, SensBadge, Spinner, Value } from "../components/ui";
import { API_BASE, api, fmtBytes, fmtTime } from "../lib/api";
import { useConnections } from "../lib/connections";

const STATUS_TONE: Record<string, string> = { scanned: "cyan", imported: "green", failed: "red", deleted: "neutral", expired: "neutral", uploaded: "amber" };
const CATS = ["NONE", "EMAIL", "PHONE", "CREDIT_CARD", "NATIONAL_ID", "BANK_ACCOUNT", "ACCOUNT_NUMBER", "PERSON_NAME", "POSTAL_ADDRESS", "DATE_OF_BIRTH", "FINANCIAL_AMOUNT", "CREDIT_SCORE", "UPI_ID", "CUSTOMER_ID", "ORG_CONTACT", "FREE_TEXT_PII"];

function upload(file: File, onProgress: (p: number) => void): Promise<any> {
  // XHR for upload progress; same CSRF + cookie rules as fetch().
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/uploads`);
    xhr.withCredentials = true;
    const token = typeof localStorage !== "undefined" ? localStorage.getItem("sm_token") : null;
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("X-Sentinel-CSRF", "1");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.error?.message ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

function CsvReview({ up, onDone }: { up: any; onDone: () => void }) {
  const { connections, selected } = useConnections();
  const res = up.result;
  const base = up.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^[^a-z]+/, "").slice(0, 30) || "dataset";
  const [conn, setConn] = useState(selected?.id ?? "");
  const [tableName, setTableName] = useState(base);
  const [roles, setRoles] = useState<string[]>(["support", "analyst"]);
  const [cats, setCats] = useState<Record<string, string>>(Object.fromEntries(res.columns.map((c: any) => [c.name, c.category])));
  const m = useMutation({
    mutationFn: () =>
      api(`/api/uploads/${up.id}/import`, {
        body: { connection_id: conn, table_name: tableName, roles: ["admin", ...roles], columns: res.columns.map((c: any) => ({ name: c.name, category: cats[c.name] })) },
      }),
    onSuccess: onDone,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <Badge tone="cyan">{res.row_count} valid rows</Badge>
        <Badge tone={res.skipped_count ? "amber" : "neutral"}>{res.skipped_count} skipped</Badge>
        <Badge tone="amber">{res.sensitive_columns} sensitive columns</Badge>
        <Badge>delimiter “{res.delimiter === "\t" ? "tab" : res.delimiter}”</Badge>
      </div>
      {res.renamed_columns?.length > 0 && (
        <Alert tone="info" title="Column names normalised">
          {res.renamed_columns.map((r: any) => `${r.original} → ${r.name}`).join(" · ")}
        </Alert>
      )}
      {res.skipped?.length > 0 && (
        <Alert tone="warn" title="Malformed rows skipped">
          {res.skipped.slice(0, 6).map((s: any) => `line ${s.line}: ${s.reason}`).join(" · ")}
          {res.skipped.length > 6 && " …"}
        </Alert>
      )}
      <div className="overflow-x-auto rounded-lg border border-ink-700">
        <table className="w-full min-w-[900px]">
          <thead>
            <tr>
              <th className="th">Column</th>
              <th className="th">Type</th>
              <th className="th">Detected</th>
              <th className="th">Sensitivity</th>
              <th className="th">Confidence</th>
              <th className="th">Evidence</th>
              <th className="th">Reviewed category</th>
            </tr>
          </thead>
          <tbody>
            {res.columns.map((c: any) => (
              <tr key={c.name}>
                <td className="td mono">{c.name}</td>
                <td className="td mono text-fog-400">{c.type}</td>
                <td className="td text-xs">{c.category}</td>
                <td className="td"><SensBadge label={c.sensitivity} /></td>
                <td className="td text-xs tabular-nums">{Math.round(c.confidence * 100)}%</td>
                <td className="td max-w-[260px] text-xs text-fog-400">{c.evidence}</td>
                <td className="td">
                  <select className="input h-8 py-0 text-xs" value={cats[c.name]} onChange={(e) => setCats({ ...cats, [c.name]: e.target.value })} aria-label={`Category for ${c.name}`}>
                    {CATS.map((x) => <option key={x}>{x}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <div className="mb-1.5 text-xs text-fog-400">{res.preview_note}</div>
        <div className="max-h-72 overflow-auto rounded-lg border border-ink-700">
          <table className="w-full">
            <thead>
              <tr>{res.columns.map((c: any) => <th key={c.name} className="th">{c.name} <ActionBadge action={c.sensitivity === "PUBLIC" || c.sensitivity === "INTERNAL" ? "ALLOW" : c.suggested_masking} /></th>)}</tr>
            </thead>
            <tbody>
              {res.preview.map((r: any[], i: number) => (
                <tr key={i}>{r.map((v, j) => <td key={j} className="td mono"><Value v={v} /></td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {up.status === "scanned" && (
        <div className="rounded-lg border border-ink-700 bg-ink-900/50 p-4">
          <div className="mb-3 text-sm font-medium">Import into database</div>
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="label">Destination database</label>
              <select className="input" value={conn} onChange={(e) => setConn(e.target.value)}>
                {connections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Table name (prefixed imp_)</label>
              <input className="input font-mono" value={tableName} onChange={(e) => setTableName(e.target.value)} pattern="^[a-z][a-z0-9_]{0,40}$" />
            </div>
            <div>
              <label className="label">Grant query access to</label>
              <div className="flex gap-3 pt-2 text-sm">
                <label className="flex items-center gap-1.5 text-fog-400"><input type="checkbox" checked disabled /> admin</label>
                {["support", "analyst"].map((r) => (
                  <label key={r} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={roles.includes(r)} onChange={(e) => setRoles(e.target.checked ? [...roles, r] : roles.filter((x) => x !== r))} /> {r}
                  </label>
                ))}
              </div>
            </div>
          </div>
          <p className="mt-3 text-xs text-fog-400">Values are inserted with bound parameters into a new table. The same classification + masking policies used for database-native data protect it immediately.</p>
          <ErrorText error={m.error} />
          <div className="mt-3 flex justify-end">
            <Button variant="primary" icon={<Table2 className="h-4 w-4" />} loading={m.isPending} onClick={() => m.mutate()} disabled={!conn || !/^[a-z][a-z0-9_]{0,40}$/.test(tableName)}>
              Import {res.row_count} rows
            </Button>
          </div>
        </div>
      )}
      {up.status === "imported" && (
        <Alert tone="success" title={`Imported into ${up.imported_table}`}>
          {res.imported_rows} rows imported, {res.skipped_rows} skipped. Temporary file deleted.{" "}
          <Link to="/playground" className="underline">Query it in the playground</Link> as each role to see policy-enforced masking.
        </Alert>
      )}
    </div>
  );
}

function DocResult({ up }: { up: any }) {
  const r = up.result;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Badge tone="cyan">{r.finding_count} findings</Badge>
        {Object.entries(r.category_counts).map(([k, v]) => <Badge key={k} tone="amber">{k}: {String(v)}</Badge>)}
        {r.paragraphs !== undefined && <Badge>{r.paragraphs} paragraphs · {r.tables} tables</Badge>}
        {r.extractor && <Badge tone="indigo">extracted with {r.extractor}</Badge>}
      </div>
      {r.findings.length > 0 && (
        <div className="max-h-64 overflow-auto rounded-lg border border-ink-700">
          <table className="w-full">
            <thead>
              <tr><th className="th">Location</th><th className="th">Category</th><th className="th">Sensitivity</th><th className="th">Masked value</th><th className="th">Confidence</th></tr>
            </thead>
            <tbody>
              {r.findings.map((f: any, i: number) => (
                <tr key={i}>
                  <td className="td text-xs">{f.location} <span className="text-fog-500">@{f.offset}</span></td>
                  <td className="td text-xs">{f.category} <span className="text-fog-500">({f.subtype})</span></td>
                  <td className="td"><SensBadge label={f.sensitivity} /></td>
                  <td className="td mono"><Value v={f.masked_value} /></td>
                  <td className="td text-xs tabular-nums">{Math.round(f.confidence * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div>
        <div className="mb-1.5 text-xs text-fog-400">{r.preview_note}</div>
        <div className="max-h-72 space-y-1 overflow-auto rounded-lg border border-ink-700 bg-ink-950/60 p-3">
          {r.masked_preview.map((p: any, i: number) => (
            <div key={i} className="grid grid-cols-[150px_1fr] gap-3 text-[12.5px]">
              <span className="truncate text-fog-500">{p.location}</span>
              <span className="whitespace-pre-wrap font-mono">{p.text}</span>
            </div>
          ))}
        </div>
      </div>
      <p className="text-xs text-fog-500">Unstructured documents are not converted into relational tables. Only masked findings are retained; the original file was deleted after extraction.</p>
    </div>
  );
}

export default function UploadsPage() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const limits = useQuery({ queryKey: ["upload-limits"], queryFn: () => api("/api/uploads/limits") });
  const list = useQuery({ queryKey: ["uploads"], queryFn: () => api<any[]>("/api/uploads") });
  const del = useMutation({ mutationFn: (id: string) => api(`/api/uploads/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["uploads"] }) });

  const handle = async (file?: File) => {
    if (!file) return;
    setError(null);
    if (limits.data && file.size > limits.data.max_bytes) {
      setError(`File exceeds ${fmtBytes(limits.data.max_bytes)} limit`);
      return;
    }
    setProgress(0);
    try {
      const up = await upload(file, setProgress);
      setActive(up.id);
      qc.invalidateQueries({ queryKey: ["uploads"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setProgress(null);
    }
  };

  const current = list.data?.find((u) => u.id === active) ?? null;

  return (
    <div>
      <PageHeader title="File Upload & Data Import" description="Scan CSV, TXT, DOCX and legacy DOC files for sensitive data. Structured CSV data can be reviewed and imported; it is then protected by the same policies as every other table." />

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files[0]); }}
          className={`card flex flex-col items-center justify-center border-2 border-dashed px-6 py-12 text-center transition-colors ${drag ? "border-accent bg-accent/5" : "border-ink-600"}`}
        >
          <UploadCloud className="h-10 w-10 text-fog-500" />
          <div className="mt-3 text-sm font-medium">Drag a file here, or</div>
          <Button className="mt-3" variant="primary" icon={<FileUp className="h-4 w-4" />} onClick={() => input.current?.click()} loading={progress !== null}>
            Choose file
          </Button>
          <input ref={input} type="file" className="hidden" accept=".csv,.txt,.docx,.doc" onChange={(e) => { handle(e.target.files?.[0]); e.target.value = ""; }} />
          {progress !== null && (
            <div className="mt-4 w-64">
              <div className="h-1.5 overflow-hidden rounded-full bg-ink-700"><div className="h-full bg-accent transition-all" style={{ width: `${progress}%` }} /></div>
              <div className="mt-1 text-xs text-fog-400">{progress < 100 ? `Uploading ${progress}%` : "Validating, extracting and scanning…"}</div>
            </div>
          )}
          {error && <div className="mt-4 w-full max-w-lg"><Alert tone="error">{error}</Alert></div>}
        </div>
        <Card title="Supported formats">
          {limits.data ? (
            <ul className="space-y-2 text-sm">
              {limits.data.formats.map((f: any) => (
                <li key={f.ext} className="flex items-start gap-2">
                  {f.supported ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" /> : <FileText className="mt-0.5 h-4 w-4 shrink-0 text-fog-500" />}
                  <div>
                    <span className="font-mono">{f.ext}</span>
                    <div className="text-xs text-fog-400">{f.notes}</div>
                  </div>
                </li>
              ))}
              <li className="border-t border-ink-700 pt-2 text-xs text-fog-400">
                Max {fmtBytes(limits.data.max_bytes)} · CSV kept ≤ {limits.data.retention_minutes} min until import · content, MIME and size validated · ZIP-bomb and macro checks · nothing leaves this server.
              </li>
            </ul>
          ) : <Spinner />}
        </Card>
      </div>

      {current && current.result && (
        <Card className="mt-4" title={<span className="flex items-center gap-2">{current.name} <Badge tone={STATUS_TONE[current.status]}>{current.status}</Badge></span>} subtitle={`${current.kind.toUpperCase()} · ${fmtBytes(current.size_bytes)} · sha256 ${current.sha256.slice(0, 16)}…`}>
          {current.kind === "csv" ? <CsvReview up={current} onDone={() => qc.invalidateQueries({ queryKey: ["uploads"] })} /> : <DocResult up={current} />}
        </Card>
      )}
      {current && current.status === "failed" && <div className="mt-4"><Alert tone="error" title={`${current.name} could not be processed`}>{current.detail}</Alert></div>}

      <Card className="mt-4" title="Upload history">
        {list.isLoading ? <Spinner /> : !list.data?.length ? (
          <Empty icon={<FileUp className="h-8 w-8" />} title="No uploads yet">Generate upload samples from the official dataset with FULL_CODE/scripts/make_samples.py (written to data/samples/).</Empty>
        ) : (
          <table className="w-full">
            <thead>
              <tr><th className="th">File</th><th className="th">Type</th><th className="th">Status</th><th className="th">Result</th><th className="th">Uploaded</th><th className="th">Temp file</th><th className="th" /></tr>
            </thead>
            <tbody>
              {list.data.map((u) => (
                <tr key={u.id} className={`cursor-pointer hover:bg-ink-800/40 ${u.id === active ? "bg-ink-800/60" : ""}`} onClick={() => setActive(u.id)}>
                  <td className="td">{u.name}<div className="text-[11px] text-fog-500">{fmtBytes(u.size_bytes)}</div></td>
                  <td className="td mono uppercase">{u.kind}</td>
                  <td className="td"><Badge tone={STATUS_TONE[u.status]}>{u.status}</Badge>{u.status === "failed" && <div className="mt-0.5 max-w-xs text-[11px] text-rose-300">{u.detail}</div>}</td>
                  <td className="td text-xs text-fog-400">
                    {u.result?.type === "table" && `${u.result.row_count} rows · ${u.result.sensitive_columns} sensitive cols`}
                    {u.result?.type === "document" && `${u.result.finding_count} findings`}
                    {u.imported_table && <div className="text-emerald-300">→ {u.imported_table}</div>}
                  </td>
                  <td className="td text-xs text-fog-400">{fmtTime(u.created_at)}</td>
                  <td className="td text-xs">{u.temp_file_retained ? <span className="text-amber-200">retained until {fmtTime(u.expires_at)}</span> : <span className="text-fog-500">deleted</span>}</td>
                  <td className="td text-right">
                    {u.status !== "deleted" && (
                      <Button size="sm" variant="ghost" aria-label="Delete upload" onClick={(e) => { e.stopPropagation(); del.mutate(u.id); }}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
