"""Masking policy resolution.

Precedence (deterministic): among active policies for the caller's role whose non-empty
scope fields all match the column, the one with the highest specificity wins:
    column +16, table +8, category +4, sensitivity +2, schema +1, connection +1
Ties break on higher `priority`, then lower policy id.

Fail-closed rules:
  * column without classification metadata  -> DENY (table must be scanned first)
  * sensitive label with no matching policy   -> REDACT
  * unknown/invalid action                    -> REDACT
  * BREAK_GLASS without permission + reason   -> PARTIAL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .masking import ACTIONS
from .metadb import Classification, Policy
from .scanner import SENSITIVE_LABELS


@dataclass
class Decision:
    action: str
    category: str
    sensitivity: str
    policy_id: int | None
    policy_name: str
    reason: str
    classified: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category,
            "sensitivity": self.sensitivity,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "reason": self.reason,
        }


def _eq(a: str | None, b: str | None) -> bool:
    return (a or "").lower() == (b or "").lower()


def specificity(p: Policy) -> int:
    return (
        (16 if p.column_name else 0)
        + (8 if p.table_name else 0)
        + (4 if p.category else 0)
        + (2 if p.sensitivity else 0)
        + (1 if p.schema_name else 0)
        + (1 if p.connection_id else 0)
    )


def policy_matches(p: Policy, conn_id: str, schema: str, table: str, column: str, category: str, sensitivity: str) -> bool:
    checks = [
        (p.connection_id, conn_id),
        (p.schema_name, schema),
        (p.table_name, table),
        (p.column_name, column),
        (p.category, category),
        (p.sensitivity, sensitivity),
    ]
    return all(scope is None or scope == "" or _eq(scope, actual) for scope, actual in checks)


class PolicyResolver:
    def __init__(self, db: Session, role: str, connection_id: str):
        self.role = role
        self.connection_id = connection_id
        self.policies = list(
            db.scalars(select(Policy).where(Policy.active.is_(True), Policy.role == role).order_by(Policy.id))
        )
        self.classes = {
            (c.schema_name.lower(), c.table_name.lower(), c.column_name.lower()): c
            for c in db.scalars(select(Classification).where(Classification.connection_id == connection_id))
        }

    def classification(self, schema: str, table: str, column: str) -> Classification | None:
        return self.classes.get((schema.lower(), table.lower(), column.lower()))

    def table_classified(self, schema: str, table: str) -> bool:
        return any(k[0] == schema.lower() and k[1] == table.lower() for k in self.classes)

    def decide(
        self,
        schema: str,
        table: str,
        column: str,
        *,
        can_break_glass: bool = False,
        justification: str | None = None,
    ) -> Decision:
        c = self.classification(schema, table, column)
        if c is None:
            return Decision("DENY", "UNKNOWN", "UNKNOWN", None, "fail-closed", "column has no classification metadata", False)
        category, sensitivity = c.category, c.sensitivity
        candidates = [
            p
            for p in self.policies
            if policy_matches(p, self.connection_id, schema, table, column, category, sensitivity)
        ]
        if not candidates:
            if sensitivity in SENSITIVE_LABELS:
                return Decision("REDACT", category, sensitivity, None, "fail-closed default", "sensitive column with no matching policy")
            return Decision("ALLOW", category, sensitivity, None, "non-sensitive default", f"classified {sensitivity}")
        best = sorted(candidates, key=lambda p: (-specificity(p), -p.priority, p.id))[0]
        action = best.action if best.action in ACTIONS else "REDACT"
        reason = f"policy #{best.id} (specificity {specificity(best)})"
        if action == "BREAK_GLASS":
            if can_break_glass and justification and len(justification.strip()) >= 10:
                return Decision("ALLOW", category, sensitivity, best.id, best.name, reason + "; break-glass justification recorded")
            action = "PARTIAL"
            reason += "; break-glass not invoked -> partial"
        return Decision(action, category, sensitivity, best.id, best.name, reason)
