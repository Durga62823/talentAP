"""Secure file ingestion: CSV, TXT, DOCX and legacy DOC (via antiword when available).

Pipeline: size/extension/MIME/content validation -> random server-side id -> restricted temp
storage -> parse -> detect -> masked preview -> (CSV) review + import with bound
parameters -> classification + grants -> audit -> temp file deletion.

Raw document text is never persisted: TXT/DOCX/DOC files are deleted right after the scan and
only masked snippets and finding metadata are stored. CSV files are kept until import,
deletion or expiry (SENTINEL_UPLOAD_RETENTION_MIN). Nothing is sent to external services."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import entities, masking
from .config import get_settings
from .metadb import Upload, new_id, utcnow
from .scanner import SENSITIVE_LABELS, classify_column

ALLOWED_EXT = {".csv": "csv", ".txt": "txt", ".docx": "docx", ".doc": "doc"}
ALLOWED_MIME = {
    "csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel", "application/octet-stream", ""},
    "txt": {"text/plain", "application/octet-stream", ""},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", "application/octet-stream", ""},
    "doc": {"application/msword", "application/octet-stream", ""},
}
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
MAX_CSV_ROWS = 50_000
MAX_CSV_COLS = 200
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ZIP_RATIO = 100
MAX_FINDINGS = 500
PREVIEW_ROWS = 25


class UploadError(Exception):
    """Safe, user-facing validation error."""


def safe_display_name(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^\w.\- ()]", "_", base)[:200]
    return base or "upload"


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            raise UploadError("File is not valid UTF-16 text") from None
    if b"\x00" in data[:8192]:
        raise UploadError("File contains binary data; expected UTF-8 text")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UploadError("File is not valid UTF-8. Re-save it as UTF-8 (or UTF-16 with BOM) and retry") from None


def check_docx_archive(data: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UploadError("Malformed DOCX: not a valid ZIP container") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UploadError("DOCX contains too many parts")
    total = 0
    names = set()
    for i in infos:
        if i.filename.startswith("/") or ".." in i.filename.split("/"):
            raise UploadError("DOCX contains unsafe part paths")
        total += i.file_size
        if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_ZIP_RATIO and i.file_size > 1_000_000:
            raise UploadError("DOCX rejected: suspicious compression ratio (possible decompression bomb)")
        names.add(i.filename.lower())
    if total > MAX_ZIP_UNCOMPRESSED:
        raise UploadError("DOCX rejected: uncompressed size exceeds limit")
    if "word/document.xml" not in names or "[content_types].xml" not in names:
        raise UploadError("Malformed DOCX: missing word/document.xml")
    if any(n.endswith("vbaproject.bin") for n in names):
        raise UploadError("Macro-enabled documents are not accepted")


def validate(filename: str, content_type: str, data: bytes) -> str:
    s = get_settings()
    if len(data) == 0:
        raise UploadError("File is empty")
    if len(data) > s.max_upload_bytes:
        raise UploadError(f"File exceeds the {s.max_upload_bytes // (1024 * 1024)} MB limit")
    ext = Path(filename or "").suffix.lower()
    kind = ALLOWED_EXT.get(ext)
    if kind is None:
        raise UploadError("Unsupported file type. Allowed: .csv, .txt, .docx, .doc")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME[kind]:
        raise UploadError(f"Declared content type '{mime}' does not match a {ext} file")
    if kind == "docx":
        if not data.startswith(b"PK\x03\x04"):
            raise UploadError("File content is not a DOCX document")
        check_docx_archive(data)
    elif kind == "doc":
        if not data.startswith(OLE_MAGIC):
            raise UploadError("File content is not a legacy Word (.doc) document")
    else:
        if data.startswith((b"PK\x03\x04", OLE_MAGIC, b"%PDF", b"MZ")):
            raise UploadError("File content is binary, not text")
        decode_text(data)
    return kind


def store(db: Session, filename: str, content_type: str, data: bytes, user_id: str) -> Upload:
    kind = validate(filename, content_type, data)
    s = get_settings()
    uid = new_id()
    path = s.uploads_dir / f"{uid}.bin"  # never derived from the user-supplied name
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    up = Upload(
        id=uid,
        original_name=safe_display_name(filename),
        kind=kind,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status="uploaded",
        temp_path=str(path),
        uploaded_by=user_id,
        expires_at=utcnow() + timedelta(minutes=s.upload_retention_minutes),
    )
    db.add(up)
    db.commit()
    return up


def delete_temp(up: Upload) -> None:
    if up.temp_path:
        p = Path(up.temp_path)
        base = get_settings().uploads_dir.resolve()
        if p.resolve().parent == base and p.exists():
            p.unlink()
    up.temp_path = None


def purge_expired(db: Session) -> int:
    n = 0
    now = utcnow()
    for up in db.scalars(select(Upload).where(Upload.temp_path.is_not(None))):
        exp = up.expires_at if up.expires_at.tzinfo else up.expires_at.replace(tzinfo=now.tzinfo)
        if exp < now:
            delete_temp(up)
            if up.status not in ("imported", "failed"):
                up.status = "expired"
            n += 1
    # Remove orphan temp files with no DB row
    known = {Path(u.temp_path).name for u in db.scalars(select(Upload).where(Upload.temp_path.is_not(None)))}
    for f in get_settings().uploads_dir.glob("*.bin"):
        if f.name not in known:
            f.unlink(missing_ok=True)
    db.commit()
    return n


# ---------------------------------------------------------------- CSV -----------------------

def normalise_column(name: str, idx: int, seen: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", (name or "").strip().lower()).strip("_")[:48]
    if not base:
        base = f"col_{idx + 1}"
    if base[0].isdigit():
        base = f"c_{base}"
    if base in {"_row_id", "select", "from", "where", "table", "order", "group", "index", "user"}:
        base = f"{base}_col"
    candidate, k = base, 2
    while candidate in seen:
        candidate = f"{base}_{k}"
        k += 1
    seen.add(candidate)
    return candidate


def infer_type(values: list[str]) -> str:
    vals = [v.strip() for v in values if v is not None and v.strip() != ""]
    if not vals:
        return "TEXT"
    if all(re.fullmatch(r"-?(0|[1-9]\d{0,14})", v) for v in vals):
        return "INTEGER"
    if all(re.fullmatch(r"-?\d{1,15}(\.\d+)?", v) for v in vals):
        return "REAL"
    return "TEXT"


def parse_csv(data: bytes) -> dict[str, Any]:
    text = decode_text(data)
    sample = text[:20_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise UploadError("CSV has no header row") from None
    except csv.Error:
        raise UploadError("CSV header could not be parsed") from None
    if len(header) > MAX_CSV_COLS:
        raise UploadError(f"CSV has more than {MAX_CSV_COLS} columns")
    seen: set[str] = set()
    columns = [normalise_column(h, i, seen) for i, h in enumerate(header)]
    renamed = [{"original": safe_display_name(h)[:64], "name": c} for h, c in zip(header, columns) if h.strip().lower() != c]
    rows: list[list[str]] = []
    skipped: list[dict[str, Any]] = []
    line = 1
    while True:
        try:
            r = next(reader)
        except StopIteration:
            break
        except csv.Error:
            line += 1
            skipped.append({"line": line, "reason": "malformed CSV record"})
            continue
        line += 1
        if not r or all(c.strip() == "" for c in r):
            continue
        if len(r) != len(columns):
            skipped.append({"line": line, "reason": f"expected {len(columns)} fields, found {len(r)}"})
            continue
        rows.append(r)
        if len(rows) > MAX_CSV_ROWS:
            raise UploadError(f"CSV exceeds {MAX_CSV_ROWS} data rows")
    types = [infer_type([r[i] for r in rows]) for i in range(len(columns))]
    return {"columns": columns, "types": types, "rows": rows, "skipped": skipped, "renamed": renamed, "delimiter": delimiter}


def _typed(value: str, typ: str) -> Any:
    v = value.strip()
    if v == "":
        return None
    if typ == "INTEGER":
        return int(v)
    if typ == "REAL":
        return float(v)
    return value


def scan_csv(data: bytes) -> dict[str, Any]:
    parsed = parse_csv(data)
    cols_out = []
    for i, (name, typ) in enumerate(zip(parsed["columns"], parsed["types"])):
        values = [_typed(r[i], typ) for r in parsed["rows"][:200]]
        res = classify_column(name, typ, values)
        cols_out.append({
            "name": name,
            "type": typ,
            "category": res.category,
            "sensitivity": res.sensitivity,
            "confidence": res.confidence,
            "detection_method": res.method,
            "evidence": res.evidence,
            "suggested_masking": res.suggested_masking,
            "sample_count": res.sample_count,
        })
    preview = []
    for r in parsed["rows"][:PREVIEW_ROWS]:
        out = []
        for i, c in enumerate(cols_out):
            v = _typed(r[i], c["type"])
            action = c["suggested_masking"] if c["sensitivity"] in SENSITIVE_LABELS else "ALLOW"
            if action in ("BREAK_GLASS", "AGGREGATE_ONLY", "DENY"):
                action = "REDACT"
            out.append(masking.apply(action, v, c["category"]))
        preview.append(out)
    return {
        "type": "table",
        "columns": cols_out,
        "preview": preview,
        "preview_note": "Preview values are masked with each column's suggested method; raw values are not displayed.",
        "row_count": len(parsed["rows"]),
        "skipped_count": len(parsed["skipped"]),
        "skipped": parsed["skipped"][:50],
        "renamed_columns": parsed["renamed"],
        "delimiter": parsed["delimiter"],
        "sensitive_columns": sum(1 for c in cols_out if c["sensitivity"] in SENSITIVE_LABELS),
    }


# ------------------------------------------------------------- documents ------------------

def _scan_segments(segments: list[tuple[str, str]]) -> dict[str, Any]:
    """segments: (location label, text). Returns findings + masked preview."""
    findings: list[dict[str, Any]] = []
    preview: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    total_chars = 0
    for loc, text in segments:
        total_chars += len(text)
        spans = entities.find_spans(text)
        for sp in spans:
            counts[sp.category] += 1
            if len(findings) < MAX_FINDINGS:
                original = text[sp.start : sp.end]
                findings.append({
                    "category": sp.category,
                    "subtype": sp.subtype,
                    "sensitivity": {"CREDIT_CARD": "PII_HIGH", "NATIONAL_ID": "PII_HIGH", "BANK_ACCOUNT": "PII_HIGH"}.get(sp.category, "PII_MEDIUM"),
                    "location": loc,
                    "offset": sp.start,
                    "length": sp.end - sp.start,
                    "confidence": sp.confidence,
                    "masked_value": "[NATIONAL-ID]" if sp.category == "NATIONAL_ID" else masking.partial(original, sp.category),
                })
        if len(preview) < 200 and text.strip():
            preview.append({"location": loc, "text": entities.mask_text(text, spans)[:2000]})
    return {
        "type": "document",
        "segments": len(segments),
        "characters": total_chars,
        "finding_count": sum(counts.values()),
        "category_counts": dict(counts),
        "findings": findings,
        "findings_truncated": sum(counts.values()) > MAX_FINDINGS,
        "masked_preview": preview,
        "preview_note": "Sensitive spans are masked. Original text is not retained after scanning.",
    }


def scan_txt(data: bytes) -> dict[str, Any]:
    text = decode_text(data)
    return _scan_segments([(f"line {i + 1}", line) for i, line in enumerate(text.splitlines())])


def scan_docx(data: bytes) -> dict[str, Any]:
    check_docx_archive(data)
    try:
        import docx  # python-docx

        d = docx.Document(io.BytesIO(data))
    except Exception:  # noqa: BLE001
        raise UploadError("DOCX could not be parsed (malformed document)") from None
    segments: list[tuple[str, str]] = []
    heading = None
    for i, p in enumerate(d.paragraphs):
        style = (p.style.name if p.style is not None else "") or ""
        if style.lower().startswith("heading") and p.text.strip():
            heading = p.text.strip()[:60]
        loc = f"paragraph {i + 1}" + (f" (section: {heading})" if heading else "")
        segments.append((loc, p.text))
    for ti, table in enumerate(d.tables):
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                segments.append((f"table {ti + 1}, row {ri + 1}, cell {ci + 1}", cell.text))
    result = _scan_segments(segments)
    result["paragraphs"] = len(d.paragraphs)
    result["tables"] = len(d.tables)
    return result


def antiword_binary() -> str | None:
    configured = get_settings().antiword_path
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("antiword")


def scan_doc(path: Path) -> dict[str, Any]:
    exe = antiword_binary()
    if not exe:
        raise UploadError(
            "Legacy .doc extraction is not available on this server (antiword not installed). "
            "Convert the document to .docx and upload again."
        )
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    home = os.environ.get("ANTIWORDHOME")
    if home:
        env["ANTIWORDHOME"] = home
        env["HOME"] = home
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, server-generated path
            [exe, "-w", "0", str(path)],
            capture_output=True,
            timeout=20,
            env=env,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UploadError("Legacy .doc extraction timed out") from None
    if proc.returncode != 0 or not proc.stdout.strip():
        raise UploadError("Legacy .doc extraction failed: the document could not be converted. Convert it to .docx and retry.")
    text = proc.stdout.decode("utf-8", errors="replace")
    result = _scan_segments([(f"paragraph {i + 1}", t) for i, t in enumerate(text.split("\n\n"))])
    result["extractor"] = "antiword"
    return result


def scan_upload(up: Upload) -> dict[str, Any]:
    if not up.temp_path or not Path(up.temp_path).exists():
        raise UploadError("Uploaded file is no longer available (expired or deleted)")
    path = Path(up.temp_path)
    data = path.read_bytes()
    if up.kind == "csv":
        return scan_csv(data)
    if up.kind == "txt":
        return scan_txt(data)
    if up.kind == "docx":
        return scan_docx(data)
    if up.kind == "doc":
        return scan_doc(path)
    raise UploadError("Unsupported upload kind")


def load_csv_rows(up: Upload) -> dict[str, Any]:
    if not up.temp_path or not Path(up.temp_path).exists():
        raise UploadError("Uploaded file is no longer available (expired or deleted)")
    parsed = parse_csv(Path(up.temp_path).read_bytes())
    typed = [[_typed(v, t) for v, t in zip(r, parsed["types"])] for r in parsed["rows"]]
    return {"columns": list(zip(parsed["columns"], parsed["types"])), "rows": typed, "skipped": len(parsed["skipped"])}


def upload_dict(up: Upload) -> dict[str, Any]:
    return {
        "id": up.id,
        "name": up.original_name,
        "kind": up.kind,
        "size_bytes": up.size_bytes,
        "sha256": up.sha256,
        "status": up.status,
        "detail": up.detail,
        "result": up.result or None,
        "created_at": up.created_at.isoformat() if up.created_at else None,
        "expires_at": up.expires_at.isoformat() if up.expires_at else None,
        "temp_file_retained": bool(up.temp_path),
        "imported_connection_id": up.imported_connection_id,
        "imported_table": up.imported_table,
    }
