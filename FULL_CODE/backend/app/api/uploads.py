from __future__ import annotations

import re
import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..connectors import ConnectorError, get_adapter
from ..discovery import upsert_classification
from ..metadb import Classification, DbConnection, Role, TableGrant, Upload, get_db, utcnow
from ..scanner import CATEGORIES, LABELS, SENSITIVITY, ColumnResult
from ..security import Principal, require
from ..uploads import UploadError, delete_temp, load_csv_rows, purge_expired, scan_upload, store, upload_dict
from .common import corr, get_conn

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _get(db: Session, uid: str) -> Upload:
    if not re.fullmatch(r"[0-9a-f]{32}", uid):
        raise HTTPException(status_code=404, detail="Upload not found")
    up = db.get(Upload, uid)
    if up is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return up


@router.get("/limits")
def limits(p: Principal = Depends(require("upload:manage"))):
    from ..uploads import antiword_binary

    s = get_settings()
    return {
        "max_bytes": s.max_upload_bytes,
        "retention_minutes": s.upload_retention_minutes,
        "formats": [
            {"ext": ".csv", "supported": True, "notes": "Scanned, previewed (masked) and importable as a table"},
            {"ext": ".txt", "supported": True, "notes": "Entity scan with locations; raw text discarded after scan"},
            {"ext": ".docx", "supported": True, "notes": "Paragraph + table extraction via python-docx; macros rejected"},
            {"ext": ".doc", "supported": antiword_binary() is not None,
             "notes": "Legacy Word via antiword" if antiword_binary() else "antiword not installed - convert to .docx"},
        ],
    }


@router.get("")
def list_uploads(p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    purge_expired(db)
    return [upload_dict(u) for u in db.scalars(select(Upload).order_by(Upload.created_at.desc()).limit(100))]


@router.post("", status_code=201)
async def upload_file(request: Request, file: UploadFile = File(...), p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    purge_expired(db)
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    try:
        up = store(db, file.filename or "", file.content_type or "", data, p.user_id)
    except UploadError as exc:
        audit.record(db, p, action="file_upload", outcome="denied", reason=str(exc), correlation_id=corr(request),
                     details={"size_bytes": len(data)})
        raise HTTPException(status_code=400, detail=str(exc)) from None
    audit.record(db, p, action="file_upload", outcome="success", correlation_id=corr(request),
                 details={"upload_id": up.id, "kind": up.kind, "size_bytes": up.size_bytes, "sha256": up.sha256})
    return await_scan(db, p, up, request)


def await_scan(db: Session, p: Principal, up: Upload, request: Request) -> dict:
    """Scan immediately after upload (files are small and bounded)."""
    started = time.perf_counter()
    try:
        result = scan_upload(up)
        up.result = result
        up.status = "scanned"
        up.detail = ""
        outcome, reason = "success", ""
    except UploadError as exc:
        up.status, up.detail = "failed", str(exc)
        outcome, reason = "error", str(exc)
    except Exception:  # noqa: BLE001
        up.status, up.detail = "failed", "File could not be processed"
        outcome, reason = "error", "processing error"
    if up.kind != "csv" or up.status == "failed":
        delete_temp(up)  # raw documents are not retained after extraction
    db.commit()
    res = up.result or {}
    audit.record(db, p, action="document_scan", outcome=outcome, reason=reason, correlation_id=corr(request),
                 duration_ms=(time.perf_counter() - started) * 1000,
                 details={"upload_id": up.id, "kind": up.kind,
                          "findings": res.get("finding_count", res.get("sensitive_columns")),
                          "categories": res.get("category_counts") or sorted({c["category"] for c in res.get("columns", []) if c["category"] != "NONE"})})
    return upload_dict(up)


@router.get("/{uid}")
def get_upload(uid: str, p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    return upload_dict(_get(db, uid))


@router.post("/{uid}/scan")
def rescan(uid: str, request: Request, p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    up = _get(db, uid)
    if not up.temp_path:
        raise HTTPException(status_code=409, detail="Raw file no longer retained; upload it again to rescan")
    return await_scan(db, p, up, request)


class ColumnReview(BaseModel):
    name: str
    category: str
    sensitivity: str | None = None


class ImportIn(BaseModel):
    connection_id: str
    table_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    roles: list[str] = Field(default_factory=lambda: ["admin", "support", "analyst"])
    columns: list[ColumnReview] = Field(default_factory=list)


@router.post("/{uid}/import")
def import_upload(uid: str, body: ImportIn, request: Request, p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    up = _get(db, uid)
    conn: DbConnection = get_conn(db, body.connection_id)
    started = time.perf_counter()
    if up.kind != "csv":
        raise HTTPException(status_code=400, detail="Only CSV uploads can be imported as tables; document scans produce findings only")
    if up.status != "scanned":
        raise HTTPException(status_code=409, detail=f"Upload is '{up.status}', expected 'scanned'")
    for r in body.roles:
        if db.get(Role, r) is None:
            raise HTTPException(status_code=400, detail=f"Unknown role {r}")
    table = body.table_name if body.table_name.startswith("imp_") else f"imp_{body.table_name}"
    try:
        loaded = load_csv_rows(up)
        adapter = get_adapter(conn)
        inserted = adapter.create_and_load(table, loaded["columns"], loaded["rows"])
    except (UploadError, ConnectorError) as exc:
        audit.record(db, p, action="data_import", outcome="error", connection_id=conn.id, tables=[table], reason=str(exc),
                     correlation_id=corr(request), details={"upload_id": up.id})
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:  # noqa: BLE001
        audit.record(db, p, action="data_import", outcome="error", connection_id=conn.id, tables=[table], reason="import failed",
                     correlation_id=corr(request), details={"upload_id": up.id})
        raise HTTPException(status_code=500, detail="Import failed; no partial table was kept") from None

    # Persist classification metadata using the scan results + reviewer overrides.
    reviews = {c.name: c for c in body.columns}
    schema = adapter.import_schema or adapter.default_schema
    scanned = {c["name"]: c for c in (up.result or {}).get("columns", [])}
    from ..scanner import classify_column

    upsert_classification(db, conn.id, schema, table, classify_column("_row_id", "INTEGER", []), source="upload")
    for name, typ in loaded["columns"]:
        s = scanned.get(name)
        r = ColumnResult(name, typ, s["category"], s["sensitivity"], s["confidence"], s["detection_method"], s["evidence"],
                         s["sample_count"], s["suggested_masking"]) if s else classify_column(name, typ, [])
        c = upsert_classification(db, conn.id, schema, table, r, source="upload")
        rv = reviews.get(name)
        if rv and rv.category in CATEGORIES and (rv.category != c.category or (rv.sensitivity and rv.sensitivity != c.sensitivity)):
            c.category = rv.category
            c.sensitivity = rv.sensitivity if rv.sensitivity in LABELS else SENSITIVITY[rv.category]
            c.review_status, c.reviewed_by, c.reviewed_at = "overridden", p.username, utcnow()
        elif rv:
            c.review_status, c.reviewed_by, c.reviewed_at = "approved", p.username, utcnow()
    for role in set(body.roles) | {"admin"}:
        db.add(TableGrant(connection_id=conn.id, schema_name=schema, table_name=table, role=role))
    up.status, up.imported_connection_id, up.imported_table = "imported", conn.id, table
    up.result = (up.result or {}) | {"imported_rows": inserted, "skipped_rows": loaded["skipped"]}
    delete_temp(up)
    db.commit()
    sensitive = [f"{table}.{c.column_name}" for c in db.scalars(select(Classification).where(
        Classification.connection_id == conn.id, Classification.table_name == table, Classification.sensitivity.in_(["PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL"])))]
    audit.record(db, p, action="data_import", outcome="success", connection_id=conn.id, tables=[table], columns=sensitive,
                 duration_ms=(time.perf_counter() - started) * 1000, correlation_id=corr(request),
                 details={"upload_id": up.id, "rows_imported": inserted, "rows_skipped": loaded["skipped"], "granted_roles": sorted(set(body.roles) | {"admin"})})
    return upload_dict(up) | {"table": table, "rows_imported": inserted}


@router.delete("/{uid}")
def delete_upload(uid: str, request: Request, p: Principal = Depends(require("upload:manage")), db: Session = Depends(get_db)):
    up = _get(db, uid)
    delete_temp(up)
    up.result = {}
    up.status = "deleted"
    db.commit()
    audit.record(db, p, action="upload_delete", outcome="success", correlation_id=corr(request), details={"upload_id": up.id})
    return {"ok": True}
