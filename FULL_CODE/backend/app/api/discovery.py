from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..discovery import classification_dict
from ..masking import ACTIONS
from ..metadb import Classification, DbConnection, ScanRun, get_db, utcnow
from ..scanner import CATEGORIES, LABELS, SENSITIVITY
from ..security import Principal, require
from .common import corr, csv_safe, iso

router = APIRouter(prefix="/api", tags=["discovery"])


@router.get("/scans")
def list_scans(limit: int = 50, p: Principal = Depends(require("scan:run")), db: Session = Depends(get_db)):
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    runs = db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(min(limit, 200)))
    return [
        {
            "id": r.id,
            "connection_id": r.connection_id,
            "connection_name": names.get(r.connection_id, "(removed)"),
            "started_at": iso(r.started_at),
            "finished_at": iso(r.finished_at),
            "status": r.status,
            "tables_scanned": r.tables_scanned,
            "columns_scanned": r.columns_scanned,
            "sensitive_found": r.sensitive_found,
            "sample_size": r.sample_size,
            "error": r.error,
        }
        for r in runs
    ]


@router.get("/classifications/meta")
def classification_meta(p: Principal = Depends(require("scan:run"))):
    return {"categories": CATEGORIES, "labels": LABELS, "default_sensitivity": SENSITIVITY, "actions": ACTIONS}


@router.get("/classifications")
def list_classifications(
    connection_id: str | None = None,
    table: str | None = None,
    sensitivity: str | None = None,
    review_status: str | None = None,
    p: Principal = Depends(require("scan:run")),
    db: Session = Depends(get_db),
):
    q = select(Classification).order_by(Classification.table_name, Classification.id)
    if connection_id:
        q = q.where(Classification.connection_id == connection_id)
    if table:
        q = q.where(Classification.table_name == table)
    if sensitivity:
        q = q.where(Classification.sensitivity == sensitivity)
    if review_status:
        q = q.where(Classification.review_status == review_status)
    return [classification_dict(c) for c in db.scalars(q)]


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject", "override"]
    category: str | None = None
    sensitivity: str | None = None


@router.patch("/classifications/{cid}")
def review_classification(cid: int, body: ReviewIn, request: Request, p: Principal = Depends(require("classification:review")), db: Session = Depends(get_db)):
    c = db.get(Classification, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Classification not found")
    before = {"category": c.category, "sensitivity": c.sensitivity, "review_status": c.review_status}
    if body.decision == "approve":
        c.review_status = "approved"
    elif body.decision == "reject":
        # Reviewer asserts the column is not sensitive.
        c.category, c.sensitivity, c.review_status = "NONE", "PUBLIC", "rejected"
    else:
        if body.category and body.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail="Unknown category")
        if body.sensitivity and body.sensitivity not in LABELS:
            raise HTTPException(status_code=400, detail="Unknown sensitivity label")
        if not body.category and not body.sensitivity:
            raise HTTPException(status_code=400, detail="Override requires a category and/or sensitivity")
        if body.category:
            c.category = body.category
            c.sensitivity = body.sensitivity or SENSITIVITY[body.category]
        if body.sensitivity:
            c.sensitivity = body.sensitivity
        c.review_status = "overridden"
    c.reviewed_by = p.username
    c.reviewed_at = utcnow()
    db.commit()
    audit.record(
        db, p, action="classification_change", outcome="success", connection_id=c.connection_id,
        tables=[c.table_name], columns=[f"{c.table_name}.{c.column_name}"], correlation_id=corr(request),
        details={"before": before, "after": {"category": c.category, "sensitivity": c.sensitivity, "review_status": c.review_status}},
    )
    return classification_dict(c)


@router.get("/classifications/export.csv")
def export_classifications(request: Request, p: Principal = Depends(require("scan:run")), db: Session = Depends(get_db)):
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["database", "schema", "table", "column", "category", "sensitivity", "confidence", "method", "evidence",
                "suggested_masking", "review_status", "source", "last_scanned_at"])
    for c in db.scalars(select(Classification).order_by(Classification.connection_id, Classification.table_name, Classification.id)):
        w.writerow([csv_safe(x) for x in [names.get(c.connection_id, c.connection_id), c.schema_name, c.table_name, c.column_name,
                                           c.category, c.sensitivity, c.confidence, c.detection_method, c.evidence,
                                           c.suggested_masking, c.review_status, c.source, iso(c.last_scanned_at)]])
    audit.record(db, p, action="report_export", outcome="success", correlation_id=corr(request), details={"report": "classifications"})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sentinelmask-classifications.csv"'})
