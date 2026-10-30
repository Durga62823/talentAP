"""Schema discovery + PII scan orchestration and classification persistence."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai_classifier as ai
from . import audit
from .ai_features import extract_features, feature_hash
from .ml import featurize as ml_featurize
from .ml import model as ml_model
from .connectors import ConnectorError, get_adapter
from .metadb import AiClassification, Classification, DbConnection, MlClassification, ScanRun, TableGrant, utcnow
from .scanner import SENSITIVE_LABELS, SENSITIVITY, ColumnResult, classify_column
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
    use_ai: bool = False,
    use_ml: bool = False,
) -> ScanRun:
    started = time.perf_counter()
    run = ScanRun(connection_id=conn.id, sample_size=sample_size, actor_id=getattr(principal, "user_id", None))
    db.add(run)
    db.commit()
    adapter = get_adapter(conn)
    sensitive = 0
    scanned_tables: list[str] = []
    ai_items: list[tuple[Classification, dict[str, Any] | None]] = []
    ml_items: list[tuple[Classification, tuple[dict[str, float], str] | None]] = []
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
                if use_ai or use_ml:
                    # Sanitized statistics only; computed now because the samples are discarded below.
                    try:
                        feats = extract_features(table, col.name, col.type, col.nullable, col.primary_key, samples[col.name], r)
                    except ValueError:
                        feats = None
                    if use_ai:
                        ai_items.append((c, feats))
                    if use_ml:
                        ml_items.append((c, ml_featurize.build(table, col.name, col.type, col.nullable, col.primary_key,
                                                               samples[col.name], r, base=feats) if feats else None))
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
    db.flush()
    if use_ml and ml_items and run.status == "completed":
        sensitive += classify_with_ml(db, principal, conn, ml_items, correlation_id)
    if use_ai and ai_items and run.status == "completed":
        sensitive += classify_with_ai(db, principal, conn, ai_items, correlation_id)
    # A rescan without a model resets unreviewed columns to the rule result; keep that model's
    # earlier upgrades so a later scan never silently weakens protection.
    if not use_ml:
        sensitive += reapply_upgrades(db, conn.id, MlClassification)
    if not use_ai:
        sensitive += reapply_upgrades(db, conn.id, AiClassification)
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


def _cached_verdict(row: AiClassification | None, fhash: str, model: str) -> ai.AIColumnResult | None:
    """Reuse a previous verdict when the sanitized features, model and prompt are unchanged."""
    if not row or row.feature_hash != fhash or row.model != model or row.prompt_version != ai.PROMPT_VERSION or not row.ai_category:
        return None
    try:
        return ai.AIColumnResult(column_key="cached", is_sensitive=row.ai_sensitivity in SENSITIVE_LABELS, category=row.ai_category,
                                 pii_type=row.pii_type or "NONE", identifier_kind=row.identifier_kind or "NONE",
                                 confidence=row.confidence or 0.0, reason=row.reason, needs_review=row.needs_review)
    except ValueError:
        return None


def reapply_upgrades(db: Session, conn_id: str, table: type[AiClassification] | type[MlClassification]) -> int:
    """Re-apply a model's earlier APPLIED upgrades after a rescan that did not run that model."""
    restored = 0
    rows = db.execute(
        select(Classification, table)
        .join(table, table.classification_id == Classification.id)
        .where(Classification.connection_id == conn_id, table.status == "APPLIED")
    ).all()
    for c, m in rows:
        cat, sens = (m.ai_category, m.ai_sensitivity) if table is AiClassification else (m.category, m.sensitivity)
        if c.review_status in REVIEWED or not cat:
            continue
        if ai.RANK.get(sens or "", 0) > ai.RANK.get(c.sensitivity, 0):
            restored += int(c.sensitivity not in SENSITIVE_LABELS and sens in SENSITIVE_LABELS)
            c.category, c.sensitivity = cat, sens
            tag = " + gemini" if table is AiClassification else " + ml"
            c.detection_method = (c.detection_method + tag)[:128]
    return restored


def classify_with_ml(
    db: Session, principal: Principal | None, conn: DbConnection,
    items: list[tuple[Classification, tuple[dict[str, float], str] | None]], correlation_id: str | None = None,
) -> int:
    """Run the local classifier and apply upgrade-only results. Never raises; if the model is
    missing the rule-based classification stays in force. Returns columns newly made sensitive."""
    started = time.perf_counter()
    model = ml_model.get_model()
    min_conf = ml_model.min_confidence()
    usable = [(c, f) for c, f in items if f is not None]
    verdicts: dict[int, Any] = {}
    error = "" if model else ml_model.model_error()
    if model and usable:
        try:
            for (c, _), v in zip(usable, model.predict([f for _, f in usable])):
                verdicts[c.id] = v
        except Exception as exc:  # noqa: BLE001 - a model failure must never break the scan
            error = f"prediction failed ({type(exc).__name__})"
            verdicts = {}
    existing = {r.classification_id: r for r in db.scalars(
        select(MlClassification).where(MlClassification.classification_id.in_([c.id for c, _ in items])))}
    counts: dict[str, int] = {}
    applied: list[str] = []
    newly_sensitive = 0
    for c, _ in items:
        v = verdicts.get(c.id)
        if v is None:
            status, apply = "ML_UNAVAILABLE", False
        else:
            status, apply = ai.upgrade_decision(c.category, c.sensitivity, c.review_status in REVIEWED,
                                                v.category, v.confidence, False, min_conf)
        row = existing.get(c.id) or MlClassification(classification_id=c.id)
        if row.id is None:
            db.add(row)
        row.status = status
        row.rule_category, row.rule_sensitivity = c.detected_category, c.detected_sensitivity
        rule_s = c.detected_sensitivity in SENSITIVE_LABELS
        ml_s = v is not None and v.sensitivity in SENSITIVE_LABELS
        row.detected_by = "BOTH" if rule_s and ml_s else "RULE" if rule_s else "ML" if ml_s else "NONE"
        row.category = v.category if v else None
        row.sensitivity = v.sensitivity if v else None
        row.confidence = v.confidence if v else None
        row.top, row.reasons = (v.top, v.reasons) if v else ([], [])
        row.error = "" if v else (error or "column could not be featurized")[:160]
        row.model_version = model.version if model else ""
        row.updated_at = utcnow()
        if apply:
            was_sensitive = c.sensitivity in SENSITIVE_LABELS
            c.category, c.sensitivity = v.category, v.sensitivity
            c.detection_method = (c.detection_method + " + ml")[:128]
            newly_sensitive += int(not was_sensitive and c.sensitivity in SENSITIVE_LABELS)
            applied.append(f"{c.table_name}.{c.column_name}")
        counts[status] = counts.get(status, 0) + 1
    db.commit()
    audit.record(
        db, principal, action="ml_classification", outcome="success" if verdicts else "error",
        connection_id=conn.id, columns=applied[:200], correlation_id=correlation_id,
        duration_ms=(time.perf_counter() - started) * 1000,
        reason="" if verdicts else f"ML model unavailable: {error}; rule-based results kept",
        details={"model_version": model.version if model else None, "columns": len(items), "status_counts": counts,
                 "applied": len(applied), "min_confidence": min_conf},
    )
    return newly_sensitive


def classify_with_ai(
    db: Session, principal: Principal | None, conn: DbConnection,
    items: list[tuple[Classification, dict[str, Any] | None]], correlation_id: str | None = None,
) -> int:
    """Run Gemini over sanitized features and apply upgrade-only results. Never raises: any AI
    failure leaves the rule-based classification in force. Returns how many columns became
    sensitive because of the AI (for the scan summary)."""
    started = time.perf_counter()
    cfg = ai.ai_settings()
    existing = {r.classification_id: r for r in db.scalars(
        select(AiClassification).where(AiClassification.classification_id.in_([c.id for c, _ in items])))}
    verdicts: dict[int, ai.AIColumnResult] = {}
    errors: dict[int, str] = {}
    to_ask: list[tuple[Classification, dict[str, Any]]] = []
    cache_hits = 0
    for c, feats in items:
        if feats is None:
            errors[c.id] = "feature_rejected"
            continue
        cached = _cached_verdict(existing.get(c.id), feature_hash(feats), cfg.model)
        if cached:
            verdicts[c.id] = cached
            cache_hits += 1
        else:
            to_ask.append((c, feats))

    stop_code = "" if ai.ai_configured() else "not_configured"
    for i in range(0, len(to_ask), cfg.batch_size):
        batch = to_ask[i:i + cfg.batch_size]
        if stop_code:
            errors.update({c.id: stop_code for c, _ in batch})
            continue
        try:
            got = ai.get_classifier().classify_batch([{"column_key": f"col_{c.id}", "features": f} for c, f in batch])
        except ai.AIUnavailable as exc:
            errors.update({c.id: exc.code for c, _ in batch})
            if exc.code in ("not_configured", "quota_exhausted", "auth_failed", "model_not_found"):
                stop_code = exc.code  # no point calling again during this scan
            continue
        for c, _ in batch:
            if f"col_{c.id}" in got:
                verdicts[c.id] = got[f"col_{c.id}"]
            else:
                errors[c.id] = "missing_in_response"

    counts: dict[str, int] = {}
    applied: list[str] = []
    newly_sensitive = 0
    for c, feats in items:
        verdict = verdicts.get(c.id)
        status, apply = ai.decide(c.category, c.sensitivity, c.review_status in REVIEWED, verdict, cfg.min_confidence)
        row = existing.get(c.id) or AiClassification(classification_id=c.id)
        if row.id is None:
            db.add(row)
        row.feature_hash = feature_hash(feats) if feats else ""
        row.features = feats or {}
        row.status = status
        row.rule_category, row.rule_sensitivity = c.detected_category, c.detected_sensitivity
        row.detected_by = ai.detected_by(c.detected_sensitivity, verdict)
        row.model, row.prompt_version = cfg.model, ai.PROMPT_VERSION
        row.error_code = errors.get(c.id, "")
        row.updated_at = utcnow()
        if verdict:
            row.ai_category = verdict.category.value
            row.ai_sensitivity = SENSITIVITY[verdict.category.value]
            row.pii_type, row.identifier_kind = verdict.pii_type.value, verdict.identifier_kind
            row.confidence, row.reason, row.needs_review = verdict.confidence, verdict.reason, verdict.needs_review
        else:
            row.ai_category = row.ai_sensitivity = row.pii_type = row.identifier_kind = None
            row.confidence, row.reason, row.needs_review = None, "", False
        if apply:
            was_sensitive = c.sensitivity in SENSITIVE_LABELS
            c.category, c.sensitivity = verdict.category.value, SENSITIVITY[verdict.category.value]
            c.detection_method = (c.detection_method + " + gemini")[:128]
            newly_sensitive += int(not was_sensitive and c.sensitivity in SENSITIVE_LABELS)
            applied.append(f"{c.table_name}.{c.column_name}")
        counts[status] = counts.get(status, 0) + 1
    db.commit()
    audit.record(
        db, principal, action="ai_classification",
        outcome="success" if verdicts else "error",
        connection_id=conn.id, columns=applied[:200], correlation_id=correlation_id,
        duration_ms=(time.perf_counter() - started) * 1000,
        reason="" if verdicts else f"AI unavailable: {sorted(set(errors.values()))}; rule-based results kept",
        details={"model": cfg.model, "prompt_version": ai.PROMPT_VERSION, "columns": len(items), "status_counts": counts,
                 "applied": len(applied), "cache_hits": cache_hits, "errors": sorted(set(errors.values()))},
    )
    return newly_sensitive


def ai_dict(a: AiClassification | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "status": a.status, "detected_by": a.detected_by, "category": a.ai_category, "sensitivity": a.ai_sensitivity,
        "pii_type": a.pii_type, "identifier_kind": a.identifier_kind, "confidence": a.confidence, "reason": a.reason,
        "needs_review": a.needs_review, "rule_category": a.rule_category, "rule_sensitivity": a.rule_sensitivity,
        "error_code": a.error_code, "model": a.model, "prompt_version": a.prompt_version, "features": a.features,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def ml_dict(m: MlClassification | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {"status": m.status, "detected_by": m.detected_by, "category": m.category, "sensitivity": m.sensitivity,
            "confidence": m.confidence, "top": m.top, "reasons": m.reasons, "rule_category": m.rule_category,
            "rule_sensitivity": m.rule_sensitivity, "error": m.error, "model_version": m.model_version,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None}


def classification_dict(c: Classification, a: AiClassification | None = None, m: MlClassification | None = None) -> dict[str, Any]:
    return {
        "ai": ai_dict(a),
        "ml": ml_dict(m),
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
