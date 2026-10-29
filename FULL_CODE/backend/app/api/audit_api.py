from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..integrity import verify
from ..metadb import AuditEvent, DbConnection, IntegrityRun, get_db
from ..security import Principal, current_principal, require
from .common import corr, csv_safe, get_conn, iso

router = APIRouter(prefix="/api", tags=["audit", "integrity"])


def ev_dict(e: AuditEvent, names: dict[str, str] | None = None) -> dict:
    return {
        "id": e.id, "seq": e.seq, "ts": iso(e.ts), "actor_id": e.actor_id, "actor": e.actor_name, "role": e.role,
        "action": e.action, "outcome": e.outcome, "connection_id": e.connection_id,
        "connection_name": (names or {}).get(e.connection_id or "", None),
        "tables": e.tables, "columns": e.columns, "reason": e.reason, "duration_ms": e.duration_ms,
        "correlation_id": e.correlation_id, "details": e.details, "entry_hash": e.entry_hash, "prev_hash": e.prev_hash,
    }


def _filtered(actor: str | None, role: str | None, action: str | None, outcome: str | None, since: str | None, until: str | None):
    q = select(AuditEvent)
    if actor:
        q = q.where(AuditEvent.actor_name == actor)
    if role:
        q = q.where(AuditEvent.role == role)
    if action:
        q = q.where(AuditEvent.action == action)
    if outcome:
        q = q.where(AuditEvent.outcome == outcome)
    try:
        if since:
            q = q.where(AuditEvent.ts >= datetime.fromisoformat(since))
        if until:
            q = q.where(AuditEvent.ts <= datetime.fromisoformat(until))
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be ISO-8601") from None
    return q


@router.get("/audit")
def list_audit(actor: str | None = None, role: str | None = None, action: str | None = None, outcome: str | None = None,
               since: str | None = None, until: str | None = None, limit: int = 100, offset: int = 0,
               p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    q = _filtered(actor, role, action, outcome, since, until)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    rows = db.scalars(q.order_by(AuditEvent.seq.desc()).limit(min(limit, 500)).offset(max(offset, 0)))
    facets = {
        "actions": sorted(x for x in db.scalars(select(AuditEvent.action).distinct()) if x),
        "actors": sorted(x for x in db.scalars(select(AuditEvent.actor_name).distinct()) if x),
        "roles": sorted(x for x in db.scalars(select(AuditEvent.role).distinct()) if x),
    }
    return {"total": total, "events": [ev_dict(e, names) for e in rows], "facets": facets}


@router.get("/audit/verify-chain")
def verify_chain(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return audit.verify_chain(db)


@router.get("/audit/export.csv")
def export_audit(request: Request, actor: str | None = None, role: str | None = None, action: str | None = None,
                 outcome: str | None = None, p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "id", "timestamp", "actor", "role", "action", "outcome", "connection_id", "tables", "columns", "reason", "duration_ms", "correlation_id"])
    for e in db.scalars(_filtered(actor, role, action, outcome, None, None).order_by(AuditEvent.seq)):
        w.writerow([csv_safe(x) for x in [e.seq, e.id, iso(e.ts), e.actor_name, e.role, e.action, e.outcome, e.connection_id,
                                           ";".join(e.tables or []), ";".join(e.columns or []), e.reason, e.duration_ms, e.correlation_id]])
    audit.record(db, p, action="report_export", outcome="success", correlation_id=corr(request), details={"report": "audit"})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sentinelmask-audit.csv"'})


@router.get("/audit/self")
def list_my_audit(
    limit: int = 50,
    offset: int = 0,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Activity stream strictly for the currently authenticated principal (no audit:read permission required)."""
    q = select(AuditEvent).where(AuditEvent.actor_name == p.username)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    rows = db.scalars(q.order_by(AuditEvent.seq.desc()).limit(min(limit, 100)).offset(max(offset, 0)))
    return {"total": total, "events": [ev_dict(e, names) for e in rows]}


@router.get("/audit/{eid}")
def get_event(eid: str, p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    e = db.get(AuditEvent, eid)
    if e is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    return ev_dict(e, names)


class IntegrityIn(BaseModel):
    connection_id: str
    tables: list[str] | None = Field(default=None, max_length=50)


def run_dict(r: IntegrityRun, names: dict[str, str]) -> dict:
    return {
        "id": r.id, "connection_id": r.connection_id, "connection_name": names.get(r.connection_id, "(removed)"),
        "tables": r.tables, "rows_covered": r.rows_covered, "before_fingerprint": r.before_fingerprint,
        "after_fingerprint": r.after_fingerprint, "table_fingerprints": r.table_fingerprints,
        "queries_executed": r.queries_executed, "match": r.match, "created_at": iso(r.created_at),
    }


@router.post("/integrity/verify")
def integrity_verify(body: IntegrityIn, request: Request, p: Principal = Depends(require("integrity:run")), db: Session = Depends(get_db)):
    conn = get_conn(db, body.connection_id)
    run = verify(db, p, conn, body.tables, corr(request))
    return run_dict(run, {conn.id: conn.name})


@router.get("/integrity/runs")
def integrity_runs(p: Principal = Depends(require("integrity:run")), db: Session = Depends(get_db)):
    names = {c.id: c.name for c in db.scalars(select(DbConnection))}
    return [run_dict(r, names) for r in db.scalars(select(IntegrityRun).order_by(IntegrityRun.created_at.desc()).limit(50))]
