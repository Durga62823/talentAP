"""Append-only, hash-chained security audit log.

Callers must only pass safe metadata: never passwords, tokens, keys, connection strings,
raw PII or protected result values. `_scrub` is a last line of defence for key names."""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .metadb import AuditEvent, new_id, utcnow

_lock = threading.Lock()
_FORBIDDEN_KEYS = {"password", "token", "secret", "hmac_key", "key", "connection_string", "raw", "rows"}


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[omitted]" if k.lower() in _FORBIDDEN_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _entry_hash(prev_hash: str, ev: AuditEvent) -> str:
    payload = json.dumps(
        {
            "prev": prev_hash,
            "id": ev.id,
            "seq": ev.seq,
            # SQLite drops tzinfo on read-back; hash the naive UTC value so it round-trips.
            "ts": ev.ts.replace(tzinfo=None).isoformat(),
            "actor": ev.actor_id,
            "role": ev.role,
            "action": ev.action,
            "outcome": ev.outcome,
            "conn": ev.connection_id,
            "tables": ev.tables,
            "columns": ev.columns,
            "reason": ev.reason,
            "details": ev.details,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def record(
    db: Session,
    principal: Any | None,
    *,
    action: str,
    outcome: str,
    connection_id: str | None = None,
    tables: list[str] | None = None,
    columns: list[str] | None = None,
    reason: str = "",
    duration_ms: float | None = None,
    correlation_id: str | None = None,
    details: dict[str, Any] | None = None,
    actor_name: str | None = None,
) -> AuditEvent:
    with _lock:
        last = db.execute(
            select(AuditEvent.seq, AuditEvent.entry_hash).order_by(AuditEvent.seq.desc()).limit(1)
        ).first()
        seq = (last[0] + 1) if last else 1
        prev_hash = last[1] if last else "0" * 64
        ev = AuditEvent(
            id=new_id(),
            seq=seq,
            ts=utcnow(),
            actor_id=getattr(principal, "user_id", None),
            actor_name=getattr(principal, "username", None) or actor_name,
            role=getattr(principal, "role", None),
            action=action,
            outcome=outcome,
            connection_id=connection_id,
            tables=sorted(set(tables or [])),
            columns=sorted(set(columns or [])),
            reason=reason[:500],
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            correlation_id=correlation_id,
            details=_scrub(details or {}),
            prev_hash=prev_hash,
        )
        ev.entry_hash = _entry_hash(prev_hash, ev)
        db.add(ev)
        db.commit()
        return ev


def verify_chain(db: Session) -> dict[str, Any]:
    """Recompute the hash chain. Detects edits made outside the application (e.g. with
    triggers dropped). It is tamper-evident, not tamper-proof: an attacker with DB write
    access could rewrite the entire chain, so production should ship events to external
    WORM storage."""
    prev = "0" * 64
    count = 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        if ev.prev_hash != prev or _entry_hash(prev, ev) != ev.entry_hash:
            return {"valid": False, "checked": count, "broken_at_seq": ev.seq}
        prev = ev.entry_hash
        count += 1
    return {"valid": True, "checked": count, "broken_at_seq": None}


def count_events(db: Session, **filters: Any) -> int:
    q = select(func.count()).select_from(AuditEvent)
    for k, v in filters.items():
        q = q.where(getattr(AuditEvent, k) == v)
    return db.scalar(q) or 0
