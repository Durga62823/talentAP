"""Application metadata store (users, sessions, connections, classifications, policies,
audit). This is separate from the protected target databases."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), ForeignKey("roles.name"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class DbConnection(Base):
    __tablename__ = "connections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # sqlite | postgresql
    # sqlite: file name inside data/targets. postgresql: host/port/database/username
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted password
    allowed_schemas: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    status_detail: Mapped[str] = mapped_column(String(255), default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TableGrant(Base):
    """Which role may query which table on which connection (default deny)."""

    __tablename__ = "table_grants"
    __table_args__ = (UniqueConstraint("connection_id", "schema_name", "table_name", "role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(32), ForeignKey("connections.id"))
    schema_name: Mapped[str] = mapped_column(String(64), default="")
    table_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32))


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(String(32), ForeignKey("connections.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    tables_scanned: Mapped[int] = mapped_column(Integer, default=0)
    columns_scanned: Mapped[int] = mapped_column(Integer, default=0)
    sensitive_found: Mapped[int] = mapped_column(Integer, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str] = mapped_column(String(255), default="")


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (UniqueConstraint("connection_id", "schema_name", "table_name", "column_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(32), ForeignKey("connections.id"))
    schema_name: Mapped[str] = mapped_column(String(64), default="")
    table_name: Mapped[str] = mapped_column(String(128))
    column_name: Mapped[str] = mapped_column(String(128))
    data_type: Mapped[str] = mapped_column(String(64), default="")
    # detected by scanner
    detected_category: Mapped[str] = mapped_column(String(32))
    detected_sensitivity: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    detection_method: Mapped[str] = mapped_column(String(128), default="")
    evidence: Mapped[str] = mapped_column(String(512), default="")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    suggested_masking: Mapped[str] = mapped_column(String(32), default="REDACT")
    # effective values (scanner result unless overridden by a reviewer)
    category: Mapped[str] = mapped_column(String(32))
    sensitivity: Mapped[str] = mapped_column(String(32))
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected|overridden
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="database")  # database | upload
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiClassification(Base):
    """Latest Gemini verdict for a classification, computed from sanitized features only.
    Kept beside the classification so the rule result and the AI result stay separately visible;
    the AI only changes the effective classification when decide() returns APPLIED."""
    __tablename__ = "ai_classifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    classification_id: Mapped[int] = mapped_column(Integer, ForeignKey("classifications.id", ondelete="CASCADE"), unique=True)
    feature_hash: Mapped[str] = mapped_column(String(64), index=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # sanitized statistics, no values
    status: Mapped[str] = mapped_column(String(20))  # APPLIED|AGREES|KEPT_RULE|LOW_CONFIDENCE|HUMAN_REVIEWED|AI_UNAVAILABLE
    detected_by: Mapped[str] = mapped_column(String(8), default="NONE")  # RULE|AI|BOTH|NONE
    ai_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pii_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identifier_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(400), default="")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_category: Mapped[str] = mapped_column(String(32), default="")
    rule_sensitivity: Mapped[str] = mapped_column(String(32), default="")
    error_code: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MlClassification(Base):
    """Latest verdict of the locally trained classifier (app/ml) for a classification. Same
    upgrade-only contract as AiClassification; the model never leaves the server."""
    __tablename__ = "ml_classifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    classification_id: Mapped[int] = mapped_column(Integer, ForeignKey("classifications.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20))  # APPLIED|AGREES|KEPT_RULE|LOW_CONFIDENCE|HUMAN_REVIEWED|ML_UNAVAILABLE
    detected_by: Mapped[str] = mapped_column(String(8), default="NONE")  # RULE|ML|BOTH|NONE
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    top: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)       # top-3 classes
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)   # evidence for the prediction
    rule_category: Mapped[str] = mapped_column(String(32), default="")
    rule_sensitivity: Mapped[str] = mapped_column(String(32), default="")
    error: Mapped[str] = mapped_column(String(160), default="")
    model_version: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32))
    # scope (None = wildcard)
    connection_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(String(255), default="")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(Integer, ForeignKey("policies.id"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    changed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    change_type: Mapped[str] = mapped_column(String(16))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(48))
    outcome: Mapped[str] = mapped_column(String(16))  # success | denied | error
    connection_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tables: Mapped[list[str]] = mapped_column(JSON, default=list)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(String(512), default="")
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64), default="")


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    original_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(8))  # csv | txt | docx | doc
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))  # uploaded|scanned|imported|failed|deleted
    detail: Mapped[str] = mapped_column(String(512), default="")
    # Safe, already-masked results only. Raw content is never persisted here.
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    temp_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_connection_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    imported_table: Mapped[str | None] = mapped_column(String(128), nullable=True)


class IntegrityRun(Base):
    __tablename__ = "integrity_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(String(32))
    tables: Mapped[list[str]] = mapped_column(JSON, default=list)
    rows_covered: Mapped[int] = mapped_column(Integer, default=0)
    before_fingerprint: Mapped[str] = mapped_column(String(64))
    after_fingerprint: Mapped[str] = mapped_column(String(64))
    table_fingerprints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    queries_executed: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    match: Mapped[bool] = mapped_column(Boolean)
    actor_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _install_audit_guards(conn) -> None:
    """Database-level append-only enforcement for the audit table."""
    conn.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;"
        )
    )
    conn.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;"
        )
    )


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        path = get_settings().meta_db_path
        _engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            # WAL + NORMAL never corrupts the file; it only skips the fsync per commit, which
            # dominated the per-query audit write.
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

        Base.metadata.create_all(_engine)
        with _engine.begin() as conn:
            _install_audit_guards(conn)
            # Audit filters/facets and the per-user activity stream; the table grows with every query.
            # IF NOT EXISTS also upgrades metadata DBs created before these indexes existed.
            for col in ("actor_name", "action", "role", "ts"):
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_audit_events_{col} ON audit_events ({col})"))
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
