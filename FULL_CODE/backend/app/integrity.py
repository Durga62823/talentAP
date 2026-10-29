"""Source-data integrity verification: fingerprint -> run protected queries as every role ->
fingerprint again -> compare. Verifies only the selected tables at the time of the run;
it does not prove that every record in every database is immutable."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .connectors import get_adapter
from .metadb import DbConnection, IntegrityRun, Role, User
from .query_engine import granted_tables, run_query
from .security import PERMISSIONS, Principal


def principal_for_user(db: Session, user: User) -> Principal:
    role = db.get(Role, user.role)
    perms = {p for p in (role.permissions if role else []) if p in PERMISSIONS}
    return Principal(user.id, user.username, user.display_name, user.role, perms)


def combined(fps: dict[str, str]) -> str:
    h = hashlib.sha256()
    for t in sorted(fps):
        h.update(f"{t}={fps[t]}\n".encode())
    return h.hexdigest()


def verify(
    db: Session,
    principal: Principal,
    conn: DbConnection,
    tables: list[str] | None,
    correlation_id: str | None = None,
) -> IntegrityRun:
    started = time.perf_counter()
    adapter = get_adapter(conn)
    available = adapter.list_tables()
    selected = [(s, t) for s, t in available if not tables or t in tables]

    before: dict[str, str] = {}
    rows_covered = 0
    for s, t in selected:
        fp, n = adapter.fingerprint(s, t)
        before[t] = fp
        rows_covered += n

    executed: list[dict[str, Any]] = []
    users = list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.username)))
    seen_roles: set[str] = set()
    for u in users:
        if u.role in seen_roles:
            continue
        seen_roles.add(u.role)
        p = principal_for_user(db, u)
        grants = granted_tables(db, conn.id, u.role)
        for s, t in selected:
            if (s.lower(), t.lower()) not in grants:
                continue
            out = run_query(db, p, conn, f"SELECT * FROM {t}", correlation_id=correlation_id, context="integrity")
            masked = [d["name"] for d in out.body.get("decisions", []) if d["action"] != "ALLOW"]
            executed.append({
                "role": u.role,
                "user": u.username,
                "table": t,
                "ok": out.ok,
                "rows": out.body.get("row_count", 0),
                "masked_columns": masked,
                "audit_event_id": out.body.get("audit_event_id"),
            })

    after: dict[str, str] = {}
    for s, t in selected:
        fp, _ = adapter.fingerprint(s, t)
        after[t] = fp

    b, a = combined(before), combined(after)
    run = IntegrityRun(
        connection_id=conn.id,
        tables=[t for _, t in selected],
        rows_covered=rows_covered,
        before_fingerprint=b,
        after_fingerprint=a,
        table_fingerprints={t: {"before": before[t], "after": after[t], "match": before[t] == after[t]} for t in before},
        queries_executed=executed,
        match=(b == a),
        actor_id=principal.user_id,
    )
    db.add(run)
    db.commit()
    audit.record(
        db,
        principal,
        action="integrity_verify",
        outcome="success" if run.match else "error",
        connection_id=conn.id,
        tables=run.tables,
        reason="" if run.match else "fingerprint mismatch detected",
        duration_ms=(time.perf_counter() - started) * 1000,
        correlation_id=correlation_id,
        details={"run_id": run.id, "rows_covered": rows_covered, "queries": len(executed), "match": run.match,
                 "before": b, "after": a},
    )
    return run
