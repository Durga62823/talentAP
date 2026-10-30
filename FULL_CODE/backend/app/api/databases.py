from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..connectors import IDENT_RE, ConnectorError, drop_adapter, get_adapter, validate_pg_host, validate_sqlite_file
from ..discovery import classification_dict, scan_connection
from ..metadb import Classification, DbConnection, Policy, ScanRun, TableGrant, get_db, utcnow
from ..security import Principal, current_principal, encrypt_secret, require
from .common import corr, get_conn, iso

router = APIRouter(prefix="/api/databases", tags=["databases"])


class ConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    kind: Literal["sqlite", "postgresql", "mysql"]
    file: str | None = Field(default=None, max_length=80)
    host: str | None = Field(default=None, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=63)
    username: str | None = Field(default=None, max_length=63)
    password: str | None = Field(default=None, max_length=256)
    allowed_schemas: list[str] = Field(default_factory=list, max_length=10)
    # MySQL only: separate writable database for reviewed CSV imports (must be in allowed_schemas)
    import_database: str | None = Field(default=None, max_length=63)

    @field_validator("allowed_schemas")
    @classmethod
    def _schemas(cls, v: list[str]) -> list[str]:
        for s in v:
            if not IDENT_RE.fullmatch(s) or s.lower() in ("information_schema", "pg_catalog", "pg_toast", "mysql", "performance_schema", "sys"):
                raise ValueError(f"invalid or forbidden schema '{s}'")
        return [s.lower() for s in v]


def conn_dict(c: DbConnection, db: Session) -> dict:
    tables = db.scalar(
        select(func.count(func.distinct(Classification.table_name))).where(Classification.connection_id == c.id)
    ) or 0
    last_scan = db.scalar(select(ScanRun).where(ScanRun.connection_id == c.id).order_by(ScanRun.started_at.desc()).limit(1))
    public = {k: v for k, v in (c.params or {}).items() if k in ("host", "port", "database", "username", "file", "import_database")}
    return {
        "id": c.id,
        "name": c.name,
        "kind": c.kind,
        "params": public,  # never includes the password
        "has_password": bool(c.secret_enc),
        "allowed_schemas": c.allowed_schemas,
        "status": c.status,
        "status_detail": c.status_detail,
        "last_tested_at": iso(c.last_tested_at),
        "tables_classified": tables,
        "last_scan": {"id": last_scan.id, "status": last_scan.status, "finished_at": iso(last_scan.finished_at)} if last_scan else None,
        "created_at": iso(c.created_at),
    }


@router.get("")
def list_connections(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    conns = list(db.scalars(select(DbConnection).order_by(DbConnection.created_at)))
    if not p.can("connections:manage"):
        # Non-admins only see connections where their role holds a grant.
        allowed = {g.connection_id for g in db.scalars(select(TableGrant).where(TableGrant.role == p.role))}
        conns = [c for c in conns if c.id in allowed]
    return [conn_dict(c, db) for c in conns]


@router.post("", status_code=201)
def create_connection(body: ConnectionIn, request: Request, p: Principal = Depends(require("connections:manage")), db: Session = Depends(get_db)):
    if db.scalar(select(DbConnection).where(DbConnection.name == body.name)):
        raise HTTPException(status_code=409, detail="A connection with this name already exists")
    try:
        if body.kind == "sqlite":
            validate_sqlite_file(body.file or "")
            conn = DbConnection(name=body.name, kind="sqlite", params={"file": body.file}, allowed_schemas=["main"])
        else:
            validate_pg_host(body.host or "")
            if not (body.database and body.username):
                raise ConnectorError("database and username are required")
            if not IDENT_RE.fullmatch(body.username) or not IDENT_RE.fullmatch(body.database):
                raise ConnectorError("database/username contain invalid characters")
            default_port = 5432 if body.kind == "postgresql" else 3306
            default_schemas = ["public"] if body.kind == "postgresql" else [body.database.lower()]
            conn = DbConnection(
                name=body.name,
                kind=body.kind,
                params={"host": body.host.lower(), "port": body.port or default_port, "database": body.database, "username": body.username,
                        **({"import_database": body.import_database.lower()} if body.kind == "mysql" and body.import_database
                           and IDENT_RE.fullmatch(body.import_database) else {})},
                secret_enc=encrypt_secret(body.password) if body.password else None,
                allowed_schemas=body.allowed_schemas or default_schemas,
            )
    except ConnectorError as exc:
        audit.record(db, p, action="connection_create", outcome="denied", reason=str(exc), correlation_id=corr(request))
        raise HTTPException(status_code=400, detail=str(exc)) from None
    db.add(conn)
    db.commit()
    audit.record(db, p, action="connection_create", outcome="success", connection_id=conn.id, correlation_id=corr(request),
                 details={"kind": conn.kind, "name": conn.name})
    return conn_dict(conn, db)


@router.post("/{conn_id}/test")
def test_connection(conn_id: str, request: Request, p: Principal = Depends(require("connections:manage")), db: Session = Depends(get_db)):
    conn = get_conn(db, conn_id)
    started = time.perf_counter()
    drop_adapter(conn.id)
    try:
        get_adapter(conn).test()
        conn.status, conn.status_detail = "healthy", "connected"
    except ConnectorError as exc:
        conn.status, conn.status_detail = "unhealthy", str(exc)[:250]
    except Exception:  # noqa: BLE001 - never echo driver errors (may include host/user details)
        conn.status, conn.status_detail = "unhealthy", "connection failed (check host, credentials and network)"
    conn.last_tested_at = utcnow()
    db.commit()
    audit.record(db, p, action="connection_test", outcome="success" if conn.status == "healthy" else "error",
                 connection_id=conn.id, reason=conn.status_detail, duration_ms=(time.perf_counter() - started) * 1000,
                 correlation_id=corr(request))
    return conn_dict(conn, db)


@router.get("/{conn_id}/schema")
def get_schema(conn_id: str, p: Principal = Depends(require("connections:manage")), db: Session = Depends(get_db)):
    conn = get_conn(db, conn_id)
    try:
        adapter = get_adapter(conn)
        classes = {
            (c.table_name.lower(), c.column_name.lower()): c
            for c in db.scalars(select(Classification).where(Classification.connection_id == conn.id))
        }
        tables = []
        for schema, t in adapter.list_tables():
            cols = adapter.columns(schema, t)
            tables.append({
                "schema": schema,
                "table": t,
                "row_count": adapter.row_count(schema, t),
                "columns": [
                    {
                        "name": c.name,
                        "type": c.type,
                        "nullable": c.nullable,
                        "primary_key": c.primary_key,
                        "classification": classification_dict(classes[(t.lower(), c.name.lower())]) if (t.lower(), c.name.lower()) in classes else None,
                    }
                    for c in cols
                ],
            })
    except ConnectorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Could not read schema from the target database") from None
    return {"connection_id": conn.id, "kind": conn.kind, "tables": tables}


class ScanIn(BaseModel):
    sample_size: int = Field(default=300, ge=10, le=2000)
    tables: list[str] | None = None
    ai: bool = True  # also classify with Gemini (sanitized features only); falls back to rules if unavailable
    ml: bool = False  # also classify with the local ML model (app/ml); off unless requested


@router.post("/{conn_id}/scan")
def run_scan(conn_id: str, body: ScanIn, request: Request, p: Principal = Depends(require("scan:run")), db: Session = Depends(get_db)):
    conn = get_conn(db, conn_id)
    run = scan_connection(db, p, conn, sample_size=body.sample_size, tables=body.tables, correlation_id=corr(request), use_ai=body.ai, use_ml=body.ml)
    if run.status == "completed" and conn.status != "healthy":
        conn.status, conn.status_detail = "healthy", "connected"
        db.commit()
    return {
        "id": run.id,
        "status": run.status,
        "tables_scanned": run.tables_scanned,
        "columns_scanned": run.columns_scanned,
        "sensitive_found": run.sensitive_found,
        "error": run.error,
    }


@router.delete("/{conn_id}")
def delete_connection(conn_id: str, request: Request, p: Principal = Depends(require("connections:manage")), db: Session = Depends(get_db)):
    conn = get_conn(db, conn_id)
    drop_adapter(conn.id)
    db.execute(delete(Classification).where(Classification.connection_id == conn.id))
    db.execute(delete(TableGrant).where(TableGrant.connection_id == conn.id))
    db.execute(delete(ScanRun).where(ScanRun.connection_id == conn.id))
    for pol in db.scalars(select(Policy).where(Policy.connection_id == conn.id)):
        pol.active = False
    name = conn.name
    db.delete(conn)
    db.commit()
    audit.record(db, p, action="connection_delete", outcome="success", connection_id=conn_id, correlation_id=corr(request),
                 details={"name": name})
    return {"ok": True}
