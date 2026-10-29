from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..metadb import (
    AuditEvent,
    AuthSession,
    Classification,
    DbConnection,
    IntegrityRun,
    Policy,
    Role,
    ScanRun,
    TableGrant,
    User,
    get_db,
    utcnow,
)
from ..policy import PolicyResolver
from ..scanner import SENSITIVE_LABELS
from ..security import PERMISSIONS, Principal, current_principal, hash_password, require
from .common import corr, iso

router = APIRouter(prefix="/api", tags=["admin"])

# ---------------------------------------------------------------- users & roles ------------


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,31}$")
    display_name: str = Field(min_length=2, max_length=128)
    role: str
    password: str = Field(min_length=10, max_length=128)


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active, "created_at": iso(u.created_at)}


def _password_ok(pw: str) -> bool:
    return bool(re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw) and re.search(r"\d", pw))


@router.get("/users")
def list_users(p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    return [user_dict(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    if db.get(Role, body.role) is None:
        raise HTTPException(status_code=400, detail="Unknown role")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    if not _password_ok(body.password):
        raise HTTPException(status_code=400, detail="Password needs upper, lower case letters and a digit")
    u = User(username=body.username, display_name=body.display_name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    audit.record(db, p, action="user_create", outcome="success", correlation_id=corr(request), details={"username": u.username, "role": u.role})
    return user_dict(u)


@router.patch("/users/{uid}")
def update_user(uid: str, body: UserPatch, request: Request, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    if u.id == p.user_id and (body.role or body.active is False):
        raise HTTPException(status_code=400, detail="You cannot change your own role or deactivate yourself")
    changes = {}
    if body.role:
        if db.get(Role, body.role) is None:
            raise HTTPException(status_code=400, detail="Unknown role")
        changes["role"] = (u.role, body.role)
        u.role = body.role
    if body.active is not None:
        changes["active"] = (u.active, body.active)
        u.active = body.active
    if body.password:
        if not _password_ok(body.password):
            raise HTTPException(status_code=400, detail="Password needs upper, lower case letters and a digit")
        u.password_hash = hash_password(body.password)
        changes["password"] = "reset"
    if changes:
        # Privilege changes take effect immediately: revoke existing sessions.
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))
    db.commit()
    audit.record(db, p, action="user_update", outcome="success", correlation_id=corr(request),
                 details={"username": u.username, "changes": {k: v for k, v in changes.items() if k != "password"},
                          "password_reset": "password" in changes})
    return user_dict(u)


@router.get("/roles")
def list_roles(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return {"roles": [{"name": r.name, "description": r.description, "permissions": r.permissions} for r in db.scalars(select(Role))],
            "permissions": PERMISSIONS}


class GrantsIn(BaseModel):
    connection_id: str
    role: str
    tables: list[str] = Field(max_length=500)


@router.get("/grants")
def list_grants(connection_id: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    out: dict[str, list[str]] = defaultdict(list)
    for g in db.scalars(select(TableGrant).where(TableGrant.connection_id == connection_id)):
        out[g.role].append(g.table_name)
    tables = sorted({c.table_name for c in db.scalars(select(Classification).where(Classification.connection_id == connection_id))})
    return {"grants": {k: sorted(v) for k, v in out.items()}, "tables": tables}


@router.put("/grants")
def set_grants(body: GrantsIn, request: Request, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    if db.get(Role, body.role) is None:
        raise HTTPException(status_code=400, detail="Unknown role")
    conn = db.get(DbConnection, body.connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    schema = "main" if conn.kind == "sqlite" else (conn.allowed_schemas or ["public"])[0]
    schema_of = {c.table_name: c.schema_name for c in db.scalars(select(Classification).where(Classification.connection_id == conn.id))}
    before = sorted(g.table_name for g in db.scalars(select(TableGrant).where(TableGrant.connection_id == conn.id, TableGrant.role == body.role)))
    db.execute(delete(TableGrant).where(TableGrant.connection_id == conn.id, TableGrant.role == body.role))
    for t in sorted(set(body.tables)):
        db.add(TableGrant(connection_id=conn.id, schema_name=schema_of.get(t, schema), table_name=t, role=body.role))
    db.commit()
    audit.record(db, p, action="grant_change", outcome="success", connection_id=conn.id, tables=body.tables, correlation_id=corr(request),
                 details={"role": body.role, "before": before, "after": sorted(set(body.tables))})
    return {"ok": True}


# ---------------------------------------------------------------- overview -----------------

EXPOSURE = {"ALLOW": 1.0, "BREAK_GLASS": 0.25, "PARTIAL": 0.2, "HASH": 0.1, "GENERALIZE": 0.1, "AGGREGATE_ONLY": 0.05, "REDACT": 0.0, "DENY": 0.0}
WEIGHT = {"PII_HIGH": 1.0, "FINANCIAL_CONFIDENTIAL": 0.8, "PII_MEDIUM": 0.6}
RISK_FORMULA = (
    "risk(column) = weight(sensitivity) x confidence x mean(exposure(action) over roles granted the table); "
    "weights PII_HIGH=1.0, FINANCIAL_CONFIDENTIAL=0.8, PII_MEDIUM=0.6; exposure ALLOW=1.0, BREAK_GLASS=0.25, "
    "PARTIAL=0.2, HASH/GENERALIZE=0.1, AGGREGATE_ONLY=0.05, REDACT/DENY=0. Overall = 100 x mean column risk."
)


def _risk(db: Session) -> dict:
    roles = [r.name for r in db.scalars(select(Role))]
    grants: dict[tuple[str, str], set[str]] = defaultdict(set)
    for g in db.scalars(select(TableGrant)):
        grants[(g.connection_id, g.table_name.lower())].add(g.role)
    resolvers: dict[tuple[str, str], PolicyResolver] = {}
    cols, covered, risks = 0, 0, []
    top: list[dict] = []
    for c in db.scalars(select(Classification).where(Classification.sensitivity.in_(list(SENSITIVE_LABELS)))):
        cols += 1
        granted = grants.get((c.connection_id, c.table_name.lower()), set())
        exposures, explicit = [], True
        for role in roles:
            key = (role, c.connection_id)
            if key not in resolvers:
                resolvers[key] = PolicyResolver(db, role, c.connection_id)
            r = resolvers[key]
            d = r.decide(c.schema_name, c.table_name, c.column_name)
            pol_action = "BREAK_GLASS" if "break-glass" in d.reason else d.action
            if d.policy_id is None:
                explicit = False
            if role in granted:
                exposures.append(EXPOSURE.get(pol_action, 0.0))
        covered += 1 if explicit else 0
        risk = WEIGHT.get(c.sensitivity, 0.5) * c.confidence * (sum(exposures) / len(exposures) if exposures else 0.0)
        risks.append(risk)
        top.append({"table": c.table_name, "column": c.column_name, "sensitivity": c.sensitivity, "risk": round(risk * 100, 1)})
    top.sort(key=lambda x: -x["risk"])
    return {
        "score": round(100 * sum(risks) / len(risks), 1) if risks else None,
        "policy_coverage_pct": round(100 * covered / cols, 1) if cols else None,
        "sensitive_columns": cols,
        "covered_columns": covered,
        "top_columns": top[:8],
        "formula": RISK_FORMULA,
    }


@router.get("/overview")
def overview(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    conns = list(db.scalars(select(DbConnection)))
    classes = list(db.scalars(select(Classification)))
    by_label = Counter(c.sensitivity for c in classes)
    by_category = Counter(c.category for c in classes if c.category != "NONE")
    tables = {(c.connection_id, c.table_name) for c in classes}
    since = utcnow() - timedelta(days=14)
    day = func.strftime("%Y-%m-%d", AuditEvent.ts)
    timeline_rows = db.execute(
        select(day, AuditEvent.outcome, func.count())
        .where(AuditEvent.ts >= since, AuditEvent.action.in_(["query_execute", "query_denied", "privilege_violation", "login_failed"]))
        .group_by(day, AuditEvent.outcome)
    ).all()
    timeline: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "denied": 0, "error": 0})
    for d, outcome, n in timeline_rows:
        timeline[d][outcome] = n
    recent_events = db.scalars(select(AuditEvent).where(AuditEvent.outcome != "success").order_by(AuditEvent.seq.desc()).limit(8))
    names = {c.id: c.name for c in conns}
    scans = db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(6))
    last_integrity = db.scalar(select(IntegrityRun).order_by(IntegrityRun.created_at.desc()).limit(1))
    return {
        "connections": {"total": len(conns), "healthy": sum(c.status == "healthy" for c in conns),
                        "unhealthy": sum(c.status == "unhealthy" for c in conns),
                        "items": [{"id": c.id, "name": c.name, "kind": c.kind, "status": c.status} for c in conns]},
        "tables_scanned": len(tables),
        "columns_classified": len(classes),
        "sensitive_columns": sum(by_label[x] for x in SENSITIVE_LABELS),
        "high_sensitivity_columns": by_label.get("PII_HIGH", 0),
        "pending_review": sum(1 for c in classes if c.review_status == "pending" and c.sensitivity in SENSITIVE_LABELS),
        "by_sensitivity": dict(by_label),
        "by_category": dict(by_category),
        "active_policies": db.scalar(select(func.count()).select_from(Policy).where(Policy.active.is_(True))) or 0,
        "queries_evaluated": audit.count_events(db, action="query_execute") + audit.count_events(db, action="query_denied"),
        "queries_blocked": audit.count_events(db, action="query_denied"),
        "privilege_violations": audit.count_events(db, action="privilege_violation"),
        "failed_logins": audit.count_events(db, action="login_failed"),
        "timeline": [{"day": d, **v} for d, v in sorted(timeline.items())],
        "recent_security_events": [
            {"id": e.id, "ts": iso(e.ts), "actor": e.actor_name, "role": e.role, "action": e.action, "outcome": e.outcome, "reason": e.reason}
            for e in recent_events
        ],
        "recent_scans": [
            {"id": s.id, "connection_name": names.get(s.connection_id, "(removed)"), "status": s.status, "finished_at": iso(s.finished_at),
             "tables_scanned": s.tables_scanned, "sensitive_found": s.sensitive_found}
            for s in scans
        ],
        "last_integrity": {"match": last_integrity.match, "created_at": iso(last_integrity.created_at), "tables": last_integrity.tables} if last_integrity else None,
        "risk": _risk(db),
    }


# ---------------------------------------------------------------- settings / demo ----------

@router.get("/settings")
def settings_info(p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    from .. import saffron
    from ..entities import jurisdictions
    from ..uploads import antiword_binary

    s = get_settings()
    conns = [
        {"name": c.name, "kind": c.kind, "status": c.status, "status_detail": c.status_detail,
         "target": c.params.get("file") if c.kind == "sqlite" else f"{c.params.get('username')}@{c.params.get('host')}:{c.params.get('port')}/{c.params.get('database')}",
         "schemas": c.allowed_schemas, "password_stored": bool(c.secret_enc)}
        for c in db.scalars(select(DbConnection).order_by(DbConnection.created_at))
    ]
    return {
        "dataset": {"name": "TalentAP Mega Hackathon 2026 - B1 Saffron Bank Ltd (synthetic, CC BY 4.0)",
                    "location": str(saffron.dataset_dir()), "available": saffron.dataset_available(),
                    "tables": len(saffron.TABLES), "official_rows": sum(saffron.EXPECTED_COUNTS.values())},
        "connections": conns,
        "mysql_import_configured": saffron.mysql_app_configured(),
        "environment": s.environment,
        "max_result_rows": s.max_result_rows,
        "query_timeout_ms": s.query_timeout_ms,
        "max_upload_bytes": s.max_upload_bytes,
        "upload_retention_minutes": s.upload_retention_minutes,
        "min_aggregate_group": s.min_aggregate_group,
        "allowed_db_hosts": s.allowed_db_hosts,
        "hmac_key_id": s.hmac_key_id,  # identifier only - the key itself never leaves the server
        "jurisdictions": sorted(jurisdictions()),
        "legacy_doc_support": antiword_binary() is not None,
        "session_hours": s.session_hours,
    }


@router.post("/demo/reset")
def demo_reset(request: Request, p: Principal = Depends(require("users:manage"))):
    if get_settings().environment == "production":
        raise HTTPException(status_code=403, detail="Demo reset is disabled in production")
    from ..seed import reset_all

    result = reset_all()
    return {"ok": True, "result": result, "note": "All sessions were cleared; please sign in again."}
