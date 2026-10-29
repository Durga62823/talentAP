"""Schema discovery + PII scan orchestration and classification persistence."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .connectors import ConnectorError, get_adapter
from .metadb import Classification, DbConnection, ScanRun, TableGrant, utcnow
from .scanner import SENSITIVE_LABELS, ColumnResult, classify_column
from .security import Principal

REVIEWED = {"approved", "rejected", "overridden"}


def upsert_classification(
    db: Session, conn_id: str, schema: str, table: str, r: ColumnResult, source: str = "database"
) -> Classification:
    c = db.scalar(
        select(Classification).where(
            Classification.connection_id == conn_id,
            Classification.schema_name == schema,
            Classification.table_name == table,
            Classification.column_name == r.column,
        )
    )
    if c is None:
        c = Classification(
            connection_id=conn_id, schema_name=schema, table_name=table, column_name=r.column, source=source
        )
        db.add(c)
    c.data_type = r.data_type[:64]
    c.detected_category = r.category
    c.detected_sensitivity = r.sensitivity
    c.confidence = r.confidence
    c.detection_method = r.method[:128]
    c.evidence = r.evidence[:500]
    c.sample_count = r.sample_count
    c.suggested_masking = r.suggested_masking
    c.last_scanned_at = utcnow()
    if c.review_status not in REVIEWED:
        # Manual decisions survive rescans; only unreviewed rows follow the scanner.
        c.category = r.category
        c.sensitivity = r.sensitivity
        c.review_status = "pending"
    return c


def ensure_admin_grant(db: Session, conn_id: str, schema: str, table: str) -> None:
    exists = db.scalar(
        select(TableGrant).where(
            TableGrant.connection_id == conn_id,
            TableGrant.schema_name == schema,
            TableGrant.table_name == table,
            TableGrant.role == "admin",
        )
    )
    if not exists:
        db.add(TableGrant(connection_id=conn_id, schema_name=schema, table_name=table, role="admin"))


def scan_connection(
    db: Session,
    principal: Principal | None,
    conn: DbConnection,
    *,
    sample_size: int = 100,
    tables: list[str] | None = None,
    correlation_id: str | None = None,
) -> ScanRun:
    started = time.perf_counter()
    run = ScanRun(connection_id=conn.id, sample_size=sample_size, actor_id=getattr(principal, "user_id", None))
    db.add(run)
    db.commit()
    adapter = get_adapter(conn)
    sensitive = 0
    scanned_tables: list[str] = []
    try:
        for schema, table in adapter.list_tables():
            if tables and table not in tables:
                continue
            cols = adapter.columns(schema, table)
            samples = adapter.sample(schema, table, [c.name for c in cols], sample_size)
            for col in cols:
                r = classify_column(col.name, col.type, samples[col.name], table=table)
                c = upsert_classification(db, conn.id, schema, table, r)
                if c.sensitivity in SENSITIVE_LABELS:
                    sensitive += 1
                run.columns_scanned += 1
            del samples  # raw sample values are never retained
            ensure_admin_grant(db, conn.id, schema, table)
            run.tables_scanned += 1
            scanned_tables.append(table)
        run.status = "completed"
    except ConnectorError as exc:
        run.status = "failed"
        run.error = str(exc)[:250]
    except Exception:  # noqa: BLE001
        run.status = "failed"
        run.error = "scan failed (see server log)"
    run.sensitive_found = sensitive
    run.finished_at = utcnow()
    db.commit()
    audit.record(
        db,
        principal,
        action="pii_scan",
        outcome="success" if run.status == "completed" else "error",
        connection_id=conn.id,
        tables=scanned_tables,
        reason=run.error,
        duration_ms=(time.perf_counter() - started) * 1000,
        correlation_id=correlation_id,
        actor_name=None if principal else "system-seed",
        details={
            "scan_id": run.id,
            "tables_scanned": run.tables_scanned,
            "columns_scanned": run.columns_scanned,
            "sensitive_found": sensitive,
            "sample_size": sample_size,
        },
    )
    return run


def classification_dict(c: Classification) -> dict[str, Any]:
    return {
        "id": c.id,
        "connection_id": c.connection_id,
        "schema": c.schema_name,
        "table": c.table_name,
        "column": c.column_name,
        "data_type": c.data_type,
        "category": c.category,
        "sensitivity": c.sensitivity,
        "detected_category": c.detected_category,
        "detected_sensitivity": c.detected_sensitivity,
        "confidence": c.confidence,
        "detection_method": c.detection_method,
        "evidence": c.evidence,
        "sample_count": c.sample_count,
        "suggested_masking": c.suggested_masking,
        "review_status": c.review_status,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "source": c.source,
        "last_scanned_at": c.last_scanned_at.isoformat() if c.last_scanned_at else None,
    }
