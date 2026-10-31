from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..metadb import TableGrant, get_db
from ..policy import PolicyResolver
from ..query_engine import analyze_query, run_query
from ..security import Principal, current_principal, resolve_principal
from .common import corr, get_conn

router = APIRouter(prefix="/api/query", tags=["query"])

EXAMPLES = [
    {"id": "contact", "title": "Customer contact details", "sql": "SELECT customer_id, cust_nm, mob_no, emailid, addr_line1, dob_dt\nFROM customers\nORDER BY customer_id LIMIT 10"},
    {"id": "same_record", "title": "One customer, every role (comparison)", "sql": "SELECT c.customer_id, c.cust_nm, c.mob_no, c.emailid, c.dob_dt,\n       a.account_no, a.curr_bal, k.CARD_NO, k.NAME_ON_CARD\nFROM customers c\nJOIN accounts a ON a.customer_id = c.customer_id\nJOIN cards k ON k.LINKED_ACCT = a.account_no\nWHERE c.customer_id = 'CIF-00UKL72D'"},
    {"id": "kyc", "title": "KYC identifiers (PAN / Aadhaar / JSON meta)", "sql": "SELECT kyc_id, customer_id, pan_no, aadhaar_no, kyc_status, kyc_meta\nFROM kyc_records WHERE customer_id = 'CIF-00UKL72D'"},
    {"id": "cards", "title": "Card numbers (UPPER-CASE columns)", "sql": "SELECT CARD_REF, CARD_NO, NAME_ON_CARD, CARD_NETWORK, CREDIT_LIMIT\nFROM cards ORDER BY CARD_REF LIMIT 10"},
    {"id": "balances", "title": "Account balances", "sql": "SELECT account_no, customer_id, acct_type, curr_bal, od_limit_inr\nFROM accounts ORDER BY account_no LIMIT 10"},
    {"id": "join", "title": "Customer + account + card join", "sql": "SELECT c.cust_nm, a.account_no, a.curr_bal, k.CARD_NO\nFROM customers c\nJOIN accounts a ON a.customer_id = c.customer_id\nJOIN cards k ON k.LINKED_ACCT = a.account_no\nWHERE a.acct_status = 'ACTIVE' ORDER BY a.account_no LIMIT 10"},
    {"id": "wildcard", "title": "SELECT * wildcard", "sql": "SELECT * FROM customers ORDER BY customer_id LIMIT 5"},
    {"id": "aggregate", "title": "Avg transaction by channel (k-anonymity)", "sql": "SELECT channel, COUNT(*) AS txns, AVG(amount_inr) AS avg_amount\nFROM transactions GROUP BY channel"},
    {"id": "narration", "title": "Transaction narration (UPI IDs in free text)", "sql": "SELECT txn_id, channel, amount_inr, counterparty, narration, ref_no\nFROM transactions WHERE channel = 'UPI' ORDER BY txn_id LIMIT 10"},
    {"id": "tickets", "title": "Support tickets (Hinglish free text)", "sql": "SELECT ticket_id, category, ticket_text, notes\nFROM support_tickets ORDER BY ticket_id LIMIT 10"},
    {"id": "nri", "title": "NRI customers (SSN, US phone)", "sql": "SELECT customer_id, ssn, us_addr, us_phone, residency_status\nFROM international_customers ORDER BY customer_id LIMIT 10"},
    {"id": "loans", "title": "Loan applications (unlabelled col_7)", "sql": "SELECT app_id, loan_type, declared_income_inr, credit_score, col_7, remarks\nFROM loan_applications ORDER BY app_id LIMIT 10"},
    {"id": "unauthorized", "title": "Unauthorized table (role-dependent)", "sql": "SELECT app_id, declared_income_inr FROM loan_applications LIMIT 5"},
    {"id": "catalog", "title": "System catalog probe", "sql": "SELECT table_name FROM information_schema.tables"},
    {"id": "destructive", "title": "Destructive statement", "sql": "UPDATE accounts SET curr_bal = 0 WHERE account_no = '00000000000000'"},
    {"id": "stacked", "title": "Stacked statements (injection)", "sql": "SELECT cust_nm FROM customers; DROP TABLE customers"},
    {"id": "inference", "title": "Inference attack via predicate", "sql": "SELECT CARD_REF FROM cards WHERE CARD_NO LIKE '4111%'"},
    {"id": "expression", "title": "Masking bypass via expression", "sql": "SELECT LOWER(emailid) AS e FROM customers"},
    {"id": "subquery", "title": "Nested sub-query", "sql": "SELECT cust_nm FROM customers WHERE customer_id IN (SELECT customer_id FROM accounts)"},
]


class QueryIn(BaseModel):
    connection_id: str
    sql: str = Field(min_length=1, max_length=10_000)
    justification: str | None = Field(default=None, max_length=300)


@router.get("/examples")
def examples(p: Principal = Depends(current_principal)):
    return EXAMPLES


@router.post("/execute")
def execute(body: QueryIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    conn = get_conn(db, body.connection_id)
    out = run_query(db, p, conn, body.sql, justification=body.justification, correlation_id=corr(request))
    return JSONResponse(status_code=out.status_code, content=out.body)


@router.post("/analyze")
def analyze(body: QueryIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Query risk preview - nothing is executed."""
    conn = get_conn(db, body.connection_id)
    return analyze_query(db, p, conn, body.sql, body.justification)


class CompareIn(BaseModel):
    connection_id: str
    sql: str = Field(min_length=1, max_length=10_000)
    # Bearer tokens of separately authenticated sessions (obtained via /api/auth/login mode=bearer).
    # Each run executes as the identity behind its token; roles are never taken from the request.
    session_tokens: list[str] = Field(min_length=1, max_length=5)


@router.post("/compare")
def compare(body: CompareIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    conn = get_conn(db, body.connection_id)
    results = []
    for tok in body.session_tokens:
        who = resolve_principal(db, tok)
        if who is None:
            results.append({"ok": False, "status": 401, "body": {"error": {"code": "unauthenticated", "message": "Session invalid or expired"}}})
            continue
        out = run_query(db, who, conn, body.sql, correlation_id=corr(request), context="compare")
        results.append({"ok": out.ok, "status": out.status_code, "user": who.username, "role": who.role, "body": out.body})
    return {"results": results}


@router.get("/permissions")
def effective_permissions(connection_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The caller's effective table grants and per-column actions (no data values)."""
    conn = get_conn(db, connection_id)
    grants = list(db.scalars(select(TableGrant).where(TableGrant.connection_id == conn.id, TableGrant.role == p.role)))
    resolver = PolicyResolver(db, p.role, conn.id, p.context)
    tables = []
    for g in sorted(grants, key=lambda g: g.table_name):
        cols = [c for c in resolver.classes.values() if c.table_name.lower() == g.table_name.lower()]
        tables.append({
            "table": g.table_name,
            "classified": bool(cols),
            "columns": [
                {"column": c.column_name, "category": c.category, "sensitivity": c.sensitivity,
                 **{k: v for k, v in resolver.decide(c.schema_name, c.table_name, c.column_name,
                                                       can_break_glass=False).as_dict().items() if k in ("action", "policy_id", "policy_name")}}
                for c in sorted(cols, key=lambda c: c.id)
            ],
        })
    return {"role": p.role, "user": p.username, "permissions": sorted(p.permissions), "tables": tables,
            "break_glass_available": p.can("raw:break_glass")}


@router.get("/catalog")
def catalog(connection_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    conn = get_conn(db, connection_id)
    if not p.can("query:execute"):
        raise HTTPException(status_code=403, detail="Query permission required")
    grants = db.scalars(select(TableGrant).where(TableGrant.connection_id == conn.id, TableGrant.role == p.role))
    return sorted({g.table_name for g in grants})
