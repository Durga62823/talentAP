"""Demo initialisation on the OFFICIAL TalentAP 2026 B1 dataset (Saffron Bank Ltd, synthetic).

Creates roles, the official sample users (data/users.csv) plus a Compliance Officer, registers
the official SQLite database (copied into data/targets), registers MySQL/PostgreSQL only when
they were explicitly configured, runs a real PII scan, and seeds grants and default policies.

No records are generated here. Demo passwords are per role, for local demonstration only."""
from __future__ import annotations

import logging
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import audit, saffron
from .config import get_settings
from .connectors import clear_adapters, get_adapter
from .discovery import scan_connection
from .metadb import Base, DbConnection, Policy, PolicyVersion, Role, SessionLocal, TableGrant, User, get_engine, reset_engine
from .security import PERMISSIONS, encrypt_secret, hash_password

log = logging.getLogger("sentinelmask.seed")

ROLES = {
    "admin": ("Data protection administrator - full view, government IDs via break-glass", sorted(PERMISSIONS)),
    "support": ("Customer support agent - partial masking for permitted fields", ["query:execute"]),
    "analyst": ("Data analyst - redaction / keyed pseudonyms; balances aggregate-only", ["query:execute"]),
    "compliance": (
        "Compliance officer - reviews classifications, audit and integrity; never sees raw PII",
        ["query:execute", "audit:read", "scan:run", "classification:review", "integrity:run"],
    ),
}

# Demo-only passwords, one per role (the official users.csv carries no passwords).
ROLE_PASSWORDS = {"admin": "Admin@2026!", "support": "Support@2026!", "analyst": "Analyst@2026!", "compliance": "Compliance@2026!"}
# users.csv defines Admin/Support/Analyst only; this account is our own addition.
EXTRA_USERS = [("compliance_lata", "Lata Menon (Compliance Officer)", "compliance")]

ALL_TABLES = saffron.TABLES
GRANTS = {
    "admin": ALL_TABLES,
    "compliance": ALL_TABLES,
    "support": ["branches", "customers", "kyc_records", "accounts", "cards", "transactions", "support_tickets"],
    "analyst": ["branches", "customers", "accounts", "cards", "transactions", "loan_applications"],
}

# role -> category -> action (category-scoped defaults). Admin gets the full view required by the
# problem statement, except government identifiers which need break-glass justification.
CATEGORY_POLICIES: dict[str, dict[str, str]] = {
    "admin": {
        "PERSON_NAME": "ALLOW", "EMAIL": "ALLOW", "PHONE": "ALLOW", "POSTAL_ADDRESS": "ALLOW", "DATE_OF_BIRTH": "ALLOW",
        "CREDIT_CARD": "ALLOW", "NATIONAL_ID": "BREAK_GLASS", "BANK_ACCOUNT": "ALLOW", "ACCOUNT_NUMBER": "ALLOW",
        "FINANCIAL_AMOUNT": "ALLOW", "CREDIT_SCORE": "ALLOW", "FREE_TEXT_PII": "ALLOW", "UPI_ID": "ALLOW",
        "CUSTOMER_ID": "ALLOW", "ORG_CONTACT": "ALLOW",
    },
    "support": {
        "PERSON_NAME": "PARTIAL", "EMAIL": "PARTIAL", "PHONE": "PARTIAL", "POSTAL_ADDRESS": "PARTIAL", "DATE_OF_BIRTH": "GENERALIZE",
        "CREDIT_CARD": "PARTIAL", "NATIONAL_ID": "PARTIAL", "BANK_ACCOUNT": "PARTIAL", "ACCOUNT_NUMBER": "PARTIAL",
        "FINANCIAL_AMOUNT": "GENERALIZE", "CREDIT_SCORE": "REDACT", "FREE_TEXT_PII": "PARTIAL", "UPI_ID": "PARTIAL",
        "CUSTOMER_ID": "ALLOW", "ORG_CONTACT": "ALLOW",
    },
    "analyst": {
        "PERSON_NAME": "REDACT", "EMAIL": "HASH", "PHONE": "REDACT", "POSTAL_ADDRESS": "REDACT", "DATE_OF_BIRTH": "GENERALIZE",
        "CREDIT_CARD": "HASH", "NATIONAL_ID": "REDACT", "BANK_ACCOUNT": "REDACT", "ACCOUNT_NUMBER": "HASH",
        "FINANCIAL_AMOUNT": "AGGREGATE_ONLY", "CREDIT_SCORE": "GENERALIZE", "FREE_TEXT_PII": "REDACT", "UPI_ID": "HASH",
        "CUSTOMER_ID": "ALLOW", "ORG_CONTACT": "ALLOW",
    },
    "compliance": {
        "PERSON_NAME": "PARTIAL", "EMAIL": "PARTIAL", "PHONE": "PARTIAL", "POSTAL_ADDRESS": "PARTIAL", "DATE_OF_BIRTH": "GENERALIZE",
        "CREDIT_CARD": "PARTIAL", "NATIONAL_ID": "PARTIAL", "BANK_ACCOUNT": "PARTIAL", "ACCOUNT_NUMBER": "PARTIAL",
        "FINANCIAL_AMOUNT": "GENERALIZE", "CREDIT_SCORE": "GENERALIZE", "FREE_TEXT_PII": "PARTIAL", "UPI_ID": "PARTIAL",
        "CUSTOMER_ID": "ALLOW", "ORG_CONTACT": "ALLOW",
    },
}

# Column-specific overrides demonstrating precedence (column beats category).
COLUMN_POLICIES = [
    ("support", "cards", "CREDIT_LIMIT", "ALLOW", "Support may quote a card's credit limit to its holder"),
    ("support", "transactions", "bal_after", "REDACT", "Running balances are not needed for support"),
]


def snapshot(p: Policy) -> dict:
    return {
        k: getattr(p, k)
        for k in ("name", "role", "connection_id", "schema_name", "table_name", "column_name", "category",
                  "sensitivity", "action", "priority", "active", "version", "description")
    }


def add_policy(db: Session, p: Policy, actor: str = "system-seed") -> Policy:
    p.updated_by = actor
    db.add(p)
    db.flush()
    db.add(PolicyVersion(policy_id=p.id, version=p.version, snapshot=snapshot(p), changed_by=actor, change_type="create"))
    return p


def demo_accounts() -> list[tuple[str, str, str]]:
    """(username, display_name, role) - official users.csv first, then our additions."""
    users = []
    if saffron.dataset_available():
        users = [(u["username"], u["display_name"], u["role"]) for u in saffron.demo_users()]
    return users + EXTRA_USERS


def seed_roles_and_users(db: Session) -> None:
    for name, (desc, perms) in ROLES.items():
        r = db.get(Role, name) or Role(name=name)
        r.description, r.permissions = desc, perms
        db.merge(r)
    db.flush()
    for username, display, role in demo_accounts():
        if role not in ROLES:
            log.warning("skipping user %s with unknown role %s", username, role)
            continue
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, display_name=display, role=role, password_hash=hash_password(ROLE_PASSWORDS[role])))
    db.commit()


def seed_policies(db: Session) -> None:
    for role, mapping in CATEGORY_POLICIES.items():
        for category, action in mapping.items():
            add_policy(db, Policy(name=f"{role}: {category.lower().replace('_', ' ')}", role=role, category=category,
                                  action=action, priority=0, description="Default category policy"))
    for role, table, column, action, desc in COLUMN_POLICIES:
        add_policy(db, Policy(name=f"{role}: {table}.{column}", role=role, table_name=table, column_name=column,
                              action=action, priority=10, description=desc))
    db.commit()


def seed_grants(db: Session, conn: DbConnection, schema: str) -> None:
    for role, tables in GRANTS.items():
        for t in tables:
            exists = db.scalar(select(TableGrant).where(
                TableGrant.connection_id == conn.id, TableGrant.table_name == t, TableGrant.role == role))
            if not exists:
                db.add(TableGrant(connection_id=conn.id, schema_name=schema, table_name=t, role=role))
    db.commit()


def register_mysql(db: Session) -> DbConnection | None:
    """Registered only after `python -m app.cli import-mysql` created the app account."""
    if not saffron.mysql_app_configured():
        return None
    conn = DbConnection(
        name="Saffron Bank (MySQL)",
        kind="mysql",
        params={
            "host": os.environ.get("SENTINEL_MYSQL_HOST", "localhost"),
            "port": int(os.environ.get("SENTINEL_MYSQL_PORT", "3306")),
            "database": saffron.MYSQL_DB,
            "username": saffron.MYSQL_APP_USER,
            "import_database": saffron.MYSQL_IMPORT_DB,
        },
        secret_enc=encrypt_secret(saffron.mysql_app_password()),
        allowed_schemas=[saffron.MYSQL_DB, saffron.MYSQL_IMPORT_DB],
    )
    db.add(conn)
    db.commit()
    return conn


def register_postgres_from_env(db: Session) -> DbConnection | None:
    host = os.environ.get("SENTINEL_DEMO_PG_HOST")
    if not host:
        return None
    conn = DbConnection(
        name="Saffron Bank (PostgreSQL)",
        kind="postgresql",
        params={
            "host": host,
            "port": int(os.environ.get("SENTINEL_DEMO_PG_PORT", 5432)),
            "database": os.environ.get("SENTINEL_DEMO_PG_DB", "saffron_bank"),
            "username": os.environ.get("SENTINEL_DEMO_PG_USER", "sentinel_app"),
        },
        secret_enc=encrypt_secret(os.environ.get("SENTINEL_DEMO_PG_PASSWORD", "")),
        allowed_schemas=["public"],
    )
    db.add(conn)
    db.commit()
    return conn


def _activate(db: Session, conn: DbConnection, schema: str, result: dict, key: str) -> None:
    """Test -> scan -> grant. A failing backend is marked unhealthy; nothing is substituted."""
    try:
        get_adapter(conn).test()
        conn.status, conn.status_detail = "healthy", "connected"
        db.commit()
        run = scan_connection(db, None, conn, sample_size=300)
        seed_grants(db, conn, schema)
        result[key] = f"registered, scan {run.status} ({run.tables_scanned} tables)"
    except Exception as exc:  # noqa: BLE001
        conn.status, conn.status_detail = "unhealthy", "connection failed - check server and credentials"
        db.commit()
        result[key] = f"registered but unreachable ({type(exc).__name__})"


def reset_all(with_external: bool = True) -> dict:
    """Rebuild application state on the official dataset. Only SentinelMask's own metadata
    and its private copy of the official SQLite DB are replaced."""
    s = get_settings()
    clear_adapters()
    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("DROP TRIGGER IF EXISTS audit_no_update"))
        c.execute(text("DROP TRIGGER IF EXISTS audit_no_delete"))
    Base.metadata.drop_all(eng)
    reset_engine()
    for f in s.uploads_dir.glob("*"):
        if f.is_file():
            f.unlink(missing_ok=True)
    legacy = s.targets_dir / "fincorp_demo.db"  # previous synthetic demo target (backed up before removal)
    legacy.unlink(missing_ok=True)

    counts = saffron.install_sqlite_target()
    get_engine()
    db = SessionLocal()
    try:
        seed_roles_and_users(db)
        seed_policies(db)
        conn = DbConnection(name="Saffron Bank (SQLite)", kind="sqlite", params={"file": saffron.SQLITE_TARGET},
                            allowed_schemas=["main"], status="healthy", status_detail="connected")
        db.add(conn)
        db.commit()
        audit.record(db, None, action="demo_reset", outcome="success", actor_name="system-seed",
                     details={"dataset": "TalentAP 2026 B1 Saffron Bank", "sqlite_rows": counts})
        result: dict = {"sqlite_rows": counts, "mysql": "not configured", "postgres": "not configured"}
        _activate(db, conn, "main", result, "sqlite")
        if with_external:
            my = register_mysql(db)
            if my is not None:
                _activate(db, my, saffron.MYSQL_DB, result, "mysql")
            pg = register_postgres_from_env(db)
            if pg is not None:
                _activate(db, pg, "public", result, "postgres")
        return result
    finally:
        db.close()


def ensure_initialised() -> None:
    """On first start, build demo state if the meta DB has no users."""
    s = get_settings()
    if s.meta_db_path.exists():
        db = SessionLocal()
        try:
            if db.scalar(select(User).limit(1)) is not None:
                return
        finally:
            db.close()
    try:
        reset_all()
    except saffron.DatasetError as exc:
        log.error("Official dataset unavailable: %s", exc)
        db = SessionLocal()
        try:
            seed_roles_and_users(db)
            seed_policies(db)
        finally:
            db.close()
