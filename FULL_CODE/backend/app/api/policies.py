from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, masking
from ..metadb import Classification, Policy, PolicyVersion, Role, get_db, utcnow
from ..policy import PolicyResolver, specificity
from ..scanner import CATEGORIES, LABELS
from ..security import Principal, require
from ..seed import snapshot
from .common import corr, iso

router = APIRouter(prefix="/api/policies", tags=["policies"])

SYNTHETIC_SAMPLES = {
    # Format illustrations for policy preview (not dataset records): published test-card prefixes,
    # fiction-reserved phone ranges, .example domains and deliberately invalid ID shapes.
    "EMAIL": ["sample.user@inbox.example", "a@quickmail.example"],
    "CREDIT_CARD": ["4111111111111111", "5555 5555 5555 4444", "378282246310005"],
    "PHONE": ["+91 90000 00000", "09999900000", "+1 (312) 555-0100", "12"],
    "PERSON_NAME": ["Sample Person", "SAMPLE CARDHOLDER", "Li"],
    "NATIONAL_ID": ["XXXX XXXX 0000", "AAAPA0000A", "900-00-0000"],
    "ACCOUNT_NUMBER": ["00000000000000", "987"],
    "BANK_ACCOUNT": ["GB82WEST12345698765432"],
    "POSTAL_ADDRESS": ["Flat 000, Sample Towers", "H.No 0-00/0, Road 0"],
    "DATE_OF_BIRTH": ["1990-01-01"],
    "FINANCIAL_AMOUNT": ["13652.30", "250000", "-40.10"],
    "CREDIT_SCORE": ["742", "655"],
    "UPI_ID": ["sample.user@saffronupi"],
    "CUSTOMER_ID": ["CIF-SAMPLE00"],
    "ORG_CONTACT": ["branch@saffronbank.example"],
    "FREE_TEXT_PII": ["card 4111 1111 1111 1111 block karo, call +91 90000 00000"],
    "NONE": ["Savings", "VERIFIED"],
}


class PolicyIn(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    role: str = Field(min_length=1, max_length=32)
    action: str
    connection_id: str | None = None
    schema_name: str | None = Field(default=None, max_length=64)
    table_name: str | None = Field(default=None, max_length=128)
    column_name: str | None = Field(default=None, max_length=128)
    category: str | None = None
    sensitivity: str | None = None
    priority: int = Field(default=0, ge=-100, le=100)
    active: bool = True
    description: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def _validate(self):
        if self.action not in masking.ACTIONS:
            raise ValueError(f"unknown action {self.action}")
        if self.category and self.category not in CATEGORIES:
            raise ValueError("unknown category")
        if self.sensitivity and self.sensitivity not in LABELS:
            raise ValueError("unknown sensitivity")
        if self.column_name and not self.table_name:
            raise ValueError("column-scoped policies must also name the table")
        if not any([self.category, self.sensitivity, self.table_name, self.column_name]):
            raise ValueError("policy must be scoped by category, sensitivity, table or column")
        for f in ("connection_id", "schema_name", "table_name", "column_name", "category", "sensitivity"):
            if getattr(self, f) == "":
                setattr(self, f, None)
        return self


class PolicyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=128)
    action: str | None = None
    priority: int | None = Field(default=None, ge=-100, le=100)
    active: bool | None = None
    description: str | None = Field(default=None, max_length=255)


def policy_dict(p: Policy) -> dict:
    return {
        "id": p.id, "name": p.name, "role": p.role, "action": p.action,
        "connection_id": p.connection_id, "schema_name": p.schema_name, "table_name": p.table_name,
        "column_name": p.column_name, "category": p.category, "sensitivity": p.sensitivity,
        "priority": p.priority, "active": p.active, "version": p.version, "description": p.description,
        "specificity": specificity(p), "updated_by": p.updated_by, "updated_at": iso(p.updated_at),
    }


@router.get("")
def list_policies(p: Principal = Depends(require("policy:manage")), db: Session = Depends(get_db)):
    return [policy_dict(x) for x in db.scalars(select(Policy).order_by(Policy.role, Policy.id))]


@router.get("/actions")
def actions(p: Principal = Depends(require("policy:manage"))):
    return {"actions": masking.ACTIONS, "categories": CATEGORIES, "labels": LABELS}


@router.post("", status_code=201)
def create_policy(body: PolicyIn, request: Request, p: Principal = Depends(require("policy:manage")), db: Session = Depends(get_db)):
    if db.get(Role, body.role) is None:
        raise HTTPException(status_code=400, detail="Unknown role")
    pol = Policy(**body.model_dump(), updated_by=p.username, updated_at=utcnow())
    db.add(pol)
    db.flush()
    db.add(PolicyVersion(policy_id=pol.id, version=1, snapshot=snapshot(pol), changed_by=p.username, change_type="create"))
    db.commit()
    audit.record(db, p, action="policy_change", outcome="success", correlation_id=corr(request),
                 details={"policy_id": pol.id, "change": "create", "after": snapshot(pol)})
    return policy_dict(pol)


@router.patch("/{pid}")
def update_policy(pid: int, body: PolicyPatch, request: Request, p: Principal = Depends(require("policy:manage")), db: Session = Depends(get_db)):
    pol = db.get(Policy, pid)
    if pol is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    if body.action is not None and body.action not in masking.ACTIONS:
        raise HTTPException(status_code=400, detail="Unknown action")
    before = snapshot(pol)
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes supplied")
    for k, v in changes.items():
        setattr(pol, k, v)
    pol.version += 1
    pol.updated_by, pol.updated_at = p.username, utcnow()
    change_type = "activate" if changes == {"active": True} else "deactivate" if changes == {"active": False} else "update"
    db.add(PolicyVersion(policy_id=pol.id, version=pol.version, snapshot=snapshot(pol), changed_by=p.username, change_type=change_type))
    db.commit()
    audit.record(db, p, action="policy_change", outcome="success", correlation_id=corr(request),
                 details={"policy_id": pol.id, "change": change_type, "before": before, "after": snapshot(pol)})
    return policy_dict(pol)


@router.get("/{pid}/versions")
def versions(pid: int, p: Principal = Depends(require("policy:manage")), db: Session = Depends(get_db)):
    return [
        {"version": v.version, "change_type": v.change_type, "changed_by": v.changed_by, "changed_at": iso(v.changed_at), "snapshot": v.snapshot}
        for v in db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == pid).order_by(PolicyVersion.version.desc()))
    ]


class PreviewIn(BaseModel):
    action: str
    category: str
    values: list[str] | None = Field(default=None, max_length=20)


@router.post("/preview")
def preview(body: PreviewIn, p: Principal = Depends(require("policy:manage"))):
    if body.action not in masking.ACTIONS or body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown action or category")
    values = body.values or SYNTHETIC_SAMPLES.get(body.category, ["sample"])
    action = "PARTIAL" if body.action == "BREAK_GLASS" else body.action
    out = []
    for v in values:
        v = v[:200]
        if action == "DENY":
            out.append({"input": v, "output": "(query rejected)"})
        else:
            out.append({"input": v, "output": masking.apply(action, v, body.category)})
    return {"action": body.action, "category": body.category, "synthetic": body.values is None, "results": out}


class SimulateIn(BaseModel):
    connection_id: str
    proposed: PolicyIn


@router.post("/simulate")
def simulate(body: SimulateIn, p: Principal = Depends(require("policy:manage")), db: Session = Depends(get_db)):
    """Compare current vs proposed decisions for one role without changing active policies."""
    role = body.proposed.role
    current = PolicyResolver(db, role, body.connection_id)
    proposed = PolicyResolver(db, role, body.connection_id)
    draft = Policy(id=10**9, **body.proposed.model_dump())
    proposed.policies = proposed.policies + [draft]
    changes = []
    for c in db.scalars(select(Classification).where(Classification.connection_id == body.connection_id).order_by(Classification.table_name, Classification.id)):
        a = current.decide(c.schema_name, c.table_name, c.column_name)
        b = proposed.decide(c.schema_name, c.table_name, c.column_name)
        if a.action != b.action:
            sample = SYNTHETIC_SAMPLES.get(c.category, ["sample"])[0]
            changes.append({
                "table": c.table_name, "column": c.column_name, "category": c.category,
                "current": a.action, "proposed": b.action,
                "synthetic_example": {
                    "input": sample,
                    "current": masking.apply("PARTIAL" if a.action == "BREAK_GLASS" else a.action, sample, c.category) if a.action != "DENY" else "(denied)",
                    "proposed": masking.apply(b.action, sample, c.category) if b.action != "DENY" else "(denied)",
                },
            })
    return {"role": role, "affected_columns": len(changes), "changes": changes, "saved": False}
