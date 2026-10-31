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

ABAC (attribute-based) conditions are *grant* conditions. A policy carrying allowed_purposes,
require_ticket_id or a UTC time window only takes effect while all of them hold for the request.
Otherwise it is skipped and the next policy in precedence order decides - but the result is never
less protective than the skipped policy's own action (STRICTNESS), so a missing ticket or purpose
can withhold an elevation but can never loosen a restriction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .masking import ACTIONS
from .metadb import Classification, Policy
from .scanner import SENSITIVE_LABELS
from .security import AccessContext

# Least -> most protective; the same order as the exposure weights behind the overview risk score.
STRICTNESS = ["ALLOW", "BREAK_GLASS", "PARTIAL", "GENERALIZE", "HASH", "AGGREGATE_ONLY", "REDACT", "DENY"]
_RANK = {a: i for i, a in enumerate(STRICTNESS)}


def stricter(a: str, b: str) -> str:
    return a if _RANK.get(a, len(STRICTNESS)) >= _RANK.get(b, len(STRICTNESS)) else b


@dataclass
class Decision:
    action: str
    category: str
    sensitivity: str
    policy_id: int | None
    policy_name: str
    reason: str
    classified: bool = True
    abac_granted: bool = False  # the deciding policy is conditional and its conditions held

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category,
            "sensitivity": self.sensitivity,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "reason": self.reason,
            "abac_granted": self.abac_granted,
        }


def is_conditional(p: Policy) -> bool:
    return bool(p.allowed_purposes) or bool(p.require_ticket_id) or bool(p.time_window_start and p.time_window_end)


def _in_window(start: str, end: str, ctx: AccessContext) -> bool:
    t = ctx.at.astimezone(timezone.utc).strftime("%H:%M")
    return start <= t < end if start <= end else (t >= start or t < end)  # windows may wrap midnight


def unmet_conditions(p: Policy, ctx: AccessContext) -> list[str]:
    """Empty list = every ABAC condition on the policy holds for this request."""
    unmet = []
    if p.allowed_purposes and ctx.purpose not in p.allowed_purposes:
        unmet.append(f"purpose {ctx.purpose or 'none'} not in {'/'.join(p.allowed_purposes)}")
    if p.require_ticket_id and not ctx.ticket_id:
        unmet.append("ticket id required")
    if p.time_window_start and p.time_window_end and not _in_window(p.time_window_start, p.time_window_end, ctx):
        unmet.append(f"outside {p.time_window_start}-{p.time_window_end} UTC")
    return unmet


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
    def __init__(
        self,
        db: Session,
        role: str,
        connection_id: str,
        context: AccessContext | None = None,
        *,
        assume_conditions_met: bool = False,
    ):
        self.role = role
        self.connection_id = connection_id
        self.context = context or AccessContext()
        # Worst-case evaluation for attestations: every ABAC grant is treated as reachable.
        self.assume_conditions_met = assume_conditions_met
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
        best, skipped = None, []
        for p in sorted(candidates, key=lambda p: (-specificity(p), -p.priority, p.id)):
            unmet = [] if self.assume_conditions_met else unmet_conditions(p, self.context)
            if not unmet:
                best = p
                break
            skipped.append((p, unmet))
        if best is None:
            policy_id, name = None, "fail-closed default" if sensitivity in SENSITIVE_LABELS else "non-sensitive default"
            action = "REDACT" if sensitivity in SENSITIVE_LABELS else "ALLOW"
            reason = "sensitive column with no matching policy" if sensitivity in SENSITIVE_LABELS else f"classified {sensitivity}"
        else:
            policy_id, name = best.id, best.name
            action = best.action if best.action in ACTIONS else "REDACT"
            reason = f"policy #{best.id} (specificity {specificity(best)})"
        abac_granted = best is not None and is_conditional(best)
        if abac_granted:
            reason += f"; ABAC conditions met (purpose {self.context.purpose or 'n/a'}, ticket {self.context.ticket_id or 'n/a'})"
        for p, unmet in skipped:
            reason += f"; conditional policy #{p.id} not applied ({', '.join(unmet)})"
            floor = p.action if p.action in ACTIONS else "REDACT"
            if stricter(action, floor) != action:
                action, policy_id, name, abac_granted = floor, p.id, p.name, False
                reason += f" -> held at {floor}"
        if action == "BREAK_GLASS":
            if can_break_glass and justification and len(justification.strip()) >= 10:
                return Decision("ALLOW", category, sensitivity, policy_id, name, reason + "; break-glass justification recorded", abac_granted=abac_granted)
            action = "PARTIAL"
            reason += "; break-glass not invoked -> partial"
        return Decision(action, category, sensitivity, policy_id, name, reason, abac_granted=abac_granted)
