from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ..metadb import DbConnection


def corr(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def get_conn(db: Session, conn_id: str) -> DbConnection:
    conn = db.get(DbConnection, conn_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Database connection not found")
    return conn


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection in exported CSV cells."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s
