"""The single enforcement path for every protected read:

authenticate -> resolve role -> authorise tables -> parse -> validate -> lineage ->
classifications -> policies -> execute (read-only, timeout, row cap) -> mask -> audit.

The frontend, direct API calls, integrity runs and imported datasets all go through
`run_query`. There is no other code path that returns target-table values."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlglot
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlglot import exp

from . import audit, masking
from .config import get_settings
from .connectors import ConnectorError, QueryTimeout, get_adapter
from .metadb import DbConnection, TableGrant
from .policy import PolicyResolver
from .security import Principal
from .sql_guard import QueryPlan, QueryRejected, plan_query


@dataclass
class QueryOutcome:
    ok: bool
    status_code: int
    body: dict[str, Any]


def redact_sql_literals(sql: str, dialect: str) -> str:
    """Audit-safe form of the statement: every literal becomes '?'."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
        return tree.transform(lambda n: exp.Placeholder() if isinstance(n, exp.Literal) else n).sql(dialect=dialect)[:2000]
    except Exception:  # noqa: BLE001
        return f"[unparseable statement sha256={hashlib.sha256(sql.encode()).hexdigest()[:16]}]"


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v
    if isinstance(v, Decimal):
        return float(v) if v == v.to_integral_value() or abs(v) < Decimal("1e15") else str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "[binary]"
    return str(v)


def granted_tables(db: Session, connection_id: str, role: str) -> set[tuple[str, str]]:
    return {
        (g.schema_name.lower(), g.table_name.lower())
        for g in db.scalars(select(TableGrant).where(TableGrant.connection_id == connection_id, TableGrant.role == role))
    }


def build_plan(
    db: Session,
    principal: Principal,
    conn: DbConnection,
    sql: str,
    justification: str | None,
) -> tuple[QueryPlan, Any]:
    settings = get_settings()
    adapter = get_adapter(conn)
    resolver = PolicyResolver(db, principal.role, conn.id)
    grants = granted_tables(db, conn.id, principal.role)
    available = adapter.list_tables()
    can_bg = principal.can("raw:break_glass")

    def lookup(schema: str | None, name: str):
        want_schema = (schema or adapter.default_schema).lower()
        match = [(s, t) for s, t in available if s.lower() == want_schema and t.lower() == name.lower()]
        if not match:
            return None
        s, t = match[0]
        if (s.lower(), t.lower()) not in grants:
            return None
        if not resolver.table_classified(s, t):
            raise QueryRejected(
                "not_classified",
                f"Table '{t}' has not been scanned/classified; protected queries fail closed until a scan completes",
            )
        return s, t, [c.name for c in adapter.columns(s, t)]

    def decide(schema: str, table: str, column: str):
        return resolver.decide(schema, table, column, can_break_glass=can_bg, justification=justification)

    plan = plan_query(
        sql,
        adapter.sqlglot_dialect,
        lookup,
        decide,
        max_rows=settings.max_result_rows,
        min_group=settings.min_aggregate_group,
        qualify_schema=adapter.kind != "sqlite",
    )
    return plan, adapter


def run_query(
    db: Session,
    principal: Principal,
    conn: DbConnection,
    sql: str,
    *,
    justification: str | None = None,
    correlation_id: str | None = None,
    context: str = "playground",
) -> QueryOutcome:
    settings = get_settings()
    started = time.perf_counter()
    dialect = {"postgresql": "postgres", "mysql": "mysql"}.get(conn.kind, "sqlite")
    safe_sql = redact_sql_literals(sql, dialect)
    base_details: dict[str, Any] = {"statement": safe_sql, "context": context, "database_kind": conn.kind}

    def deny(code: str, message: str, status: int, tables: list[str] | None = None) -> QueryOutcome:
        ms = (time.perf_counter() - started) * 1000
        ev = audit.record(
            db,
            principal,
            action="query_denied",
            outcome="denied",
            connection_id=conn.id,
            tables=tables,
            reason=f"{code}: {message}",
            duration_ms=ms,
            correlation_id=correlation_id,
            details=base_details | {"code": code},
        )
        return QueryOutcome(
            False,
            status,
            {"error": {"code": code, "message": message}, "audit_event_id": ev.id, "role": principal.role, "duration_ms": round(ms, 2)},
        )

    if not principal.can("query:execute"):
        return deny("forbidden", "Your role is not permitted to run queries", 403)

    try:
        plan, adapter = build_plan(db, principal, conn, sql, justification)
    except QueryRejected as rej:
        status = 403 if rej.code in ("unauthorized_table", "system_catalog", "column_denied", "predicate_on_protected", "aggregate_denied") else 400
        return deny(rej.code, rej.message, status)
    except ConnectorError as exc:
        return deny("connection_error", str(exc), 502)

    try:
        names, rows, cache_hit = adapter.execute_cached(plan.sql, settings.query_timeout_ms, settings.max_result_rows)
    except QueryTimeout as exc:
        return deny("timeout", str(exc), 408, plan.tables)
    except ConnectorError as exc:
        return deny("execution_error", str(exc), 400, plan.tables)

    if len(names) != len(plan.outputs):
        # Should be impossible after rewriting; fail closed rather than guess lineage.
        return deny("lineage_mismatch", "Result shape did not match the validated plan", 500, plan.tables)

    truncated = len(rows) > settings.max_result_rows
    rows = rows[: settings.max_result_rows]
    masked_rows = []
    for r in rows:
        out_row = []
        for value, oc in zip(r, plan.outputs):
            category = oc.decision.category if oc.decision else "NONE"
            out_row.append(_jsonable(masking.apply(oc.action, value, category)))
        masked_rows.append(out_row)

    ms = (time.perf_counter() - started) * 1000
    break_glass_cols = [
        f"{o.table}.{o.column}" for o in plan.outputs if o.decision and "break-glass justification recorded" in o.decision.reason
    ]
    decisions = [o.as_dict() for o in plan.outputs]
    ev = audit.record(
        db,
        principal,
        action="query_execute",
        outcome="success",
        connection_id=conn.id,
        tables=plan.tables,
        columns=plan.referenced_columns,
        reason=("break-glass raw access: " + ", ".join(break_glass_cols)) if break_glass_cols else "",
        duration_ms=ms,
        correlation_id=correlation_id,
        details=base_details
        | {
            "row_count": len(masked_rows),
            "truncated": truncated,
            "decisions": [{k: d[k] for k in ("name", "source", "action", "policy_id")} for d in decisions],
            "predicate_columns": plan.predicate_columns,
            "break_glass": bool(break_glass_cols),
            "justification": (justification or "")[:300] if break_glass_cols else "",
            "min_group_enforced": plan.min_group_enforced,
            "cache_hit": cache_hit,
        },
    )
    return QueryOutcome(
        True,
        200,
        {
            "columns": [o.name for o in plan.outputs],
            "rows": masked_rows,
            "row_count": len(masked_rows),
            "truncated": truncated,
            "decisions": decisions,
            "tables": plan.tables,
            "predicate_columns": plan.predicate_columns,
            "executed_sql": plan.sql,
            "notes": plan.notes,
            "role": principal.role,
            "user": principal.username,
            "duration_ms": round(ms, 2),
            "cache_hit": cache_hit,
            "audit_event_id": ev.id,
            "break_glass_columns": break_glass_cols,
        },
    )


def analyze_query(db: Session, principal: Principal, conn: DbConnection, sql: str, justification: str | None = None) -> dict[str, Any]:
    """Risk preview: validate and resolve policies without executing anything."""
    try:
        plan, _ = build_plan(db, principal, conn, sql, justification)
    except QueryRejected as rej:
        return {"permitted": False, "error": {"code": rej.code, "message": rej.message}, "role": principal.role}
    except ConnectorError as exc:
        return {"permitted": False, "error": {"code": "connection_error", "message": str(exc)}, "role": principal.role}
    protected = [o.as_dict() for o in plan.outputs if o.action != "ALLOW" or (o.decision and o.decision.sensitivity not in ("PUBLIC", "INTERNAL"))]
    return {
        "permitted": True,
        "role": principal.role,
        "tables": plan.tables,
        "decisions": [o.as_dict() for o in plan.outputs],
        "protected_columns": protected,
        "predicate_columns": plan.predicate_columns,
        "executed_sql": plan.sql,
        "notes": plan.notes,
    }
