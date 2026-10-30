"""Sanitized per-column features for AI classification.

Everything here runs locally on the transient scan samples. The output contains only schema
metadata and aggregate statistics (lengths, ratios, pattern-match rates) - never a sample value,
a min/max, a most-common value or any substring of the data - so it is safe to send to an
external model. `assert_sanitized` enforces that structurally before anything leaves the server."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import entities as E
from .scanner import ColumnResult

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PASSPORT_IN_RE = re.compile(r"^[A-PR-WY][1-9]\d\s?\d{4}[1-9]$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T].*)?$|^\d{2}/\d{2}/\d{4}$")
AMOUNT_RE = re.compile(r"^-?\d{1,15}(\.\d{1,4})?$")
DIGITS_RE = re.compile(r"^\d+$")

# Pattern checks: feature name -> predicate over one stringified value. Reuses the scanner's
# validators so the AI sees exactly the evidence the rule engine computed.
PATTERNS = {
    "email": lambda v: bool(E.EMAIL_RE.fullmatch(v)),
    "phone": E.is_phone,
    "pan": lambda v: bool(E.PAN_RE.fullmatch(v.upper())),
    "aadhaar_format": lambda v: bool(E.AADHAAR_RE.fullmatch(v) or E.AADHAAR_FORMAT_RE.fullmatch(v)),
    "aadhaar_checksum_valid": lambda v: bool(E.AADHAAR_RE.fullmatch(v)) and E.verhoeff_ok(v),
    "ssn_format": lambda v: bool(E.SSN_FORMAT_RE.fullmatch(v)),
    "passport_in": lambda v: bool(PASSPORT_IN_RE.fullmatch(v.upper())),
    "credit_card_luhn": E.is_card,
    "iban_checksum_valid": E.iban_ok,
    "ifsc": lambda v: bool(IFSC_RE.fullmatch(v.upper())),
    "upi_handle": lambda v: bool(E.UPI_RE.fullmatch(v)),
    "date": lambda v: bool(DATE_RE.fullmatch(v)),
    "person_name_shape": lambda v: bool(E.NAME_RE.fullmatch(v)),
    "address_shape": E.is_address,
    "decimal_amount": lambda v: bool(AMOUNT_RE.fullmatch(v.replace(",", ""))),
}

ALLOWED_TYPES = (str, int, float, bool, type(None))


def _s(v: Any) -> str:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v).strip()


def _ratio(n: int, d: int) -> float:
    return round(n / d, 2) if d else 0.0


def extract_features(table: str, column: str, data_type: str, nullable: bool, primary_key: bool,
                     samples: list[Any], rule: ColumnResult) -> dict[str, Any]:
    total = len(samples)
    vals = [_s(v) for v in samples if v is not None and _s(v) != ""]
    n = len(vals)
    lengths = [len(v) for v in vals]
    feats: dict[str, Any] = {
        "table_name": table,
        "column_name": column,
        "data_type": (data_type or "")[:40],
        "nullable": bool(nullable),
        "primary_key": bool(primary_key),
        "sample_size": total,
        "null_or_empty_ratio": _ratio(total - n, total),
        "average_length": round(sum(lengths) / n, 1) if n else 0.0,
        "maximum_length": max(lengths) if n else 0,
        "minimum_length": min(lengths) if n else 0,
        "unique_ratio": _ratio(len(set(vals)), n),
        "numeric_ratio": _ratio(sum(1 for v in vals if DIGITS_RE.fullmatch(v.replace(" ", "").replace("-", ""))), n),
        "alphabetic_ratio": _ratio(sum(1 for v in vals if v.replace(" ", "").isalpha()), n),
        "contains_space_ratio": _ratio(sum(1 for v in vals if " " in v), n),
        "free_text_with_embedded_entities_ratio": _ratio(sum(1 for v in vals if len(v) > 15 and E.find_spans(v)), n),
    }
    for name, check in PATTERNS.items():
        hits = 0
        for v in vals:
            try:
                hits += bool(check(v))
            except Exception:  # noqa: BLE001 - a validator must never break feature extraction
                pass
        feats[f"{name}_match_ratio"] = _ratio(hits, n)
    # The deterministic engine's verdict, so the model can agree, refine or flag it.
    feats["rule_engine"] = {
        "category": rule.category,
        "sensitivity": rule.sensitivity,
        "confidence": round(rule.confidence, 2),
        "method": rule.method[:80],
    }
    assert_sanitized(feats, samples)
    return feats


def assert_sanitized(feats: dict[str, Any], samples: list[Any]) -> None:
    """Fail closed if a feature object could carry raw data: only scalar metadata/statistics are
    allowed, and no string feature (other than schema names) may equal a sampled value."""
    raw = {_s(v) for v in samples if v is not None and len(_s(v)) >= 3}
    schema_strings = {feats.get("table_name"), feats.get("column_name"), feats.get("data_type")}

    def walk(obj: Any, check_raw: bool = True) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                # rule_engine strings are fixed enum labels produced by our own scanner
                walk(v, check_raw and k != "rule_engine")
        elif not isinstance(obj, ALLOWED_TYPES):
            raise ValueError("feature object contains a non-scalar value")
        elif check_raw and isinstance(obj, str) and obj not in schema_strings and obj in raw:
            raise ValueError("feature object contains a sampled value")

    walk(feats)


def feature_hash(feats: dict[str, Any]) -> str:
    """Cache key for an AI verdict. Scans sample random rows, so descriptive statistics (nulls,
    uniqueness, lengths) jitter between scans. The key therefore covers only what drives the
    classification: schema, the rule verdict, and each pattern's match level bucketed at the
    scanner's own thresholds (none / some / >= 0.6). A real change still triggers a new call."""
    def level(r: float) -> int:
        return 0 if r == 0 else 2 if r >= 0.6 else 1

    rule = feats.get("rule_engine", {})
    sig = {
        "schema": [feats.get(k) for k in ("table_name", "column_name", "data_type", "nullable", "primary_key")],
        "rule": [rule.get("category"), rule.get("sensitivity")],
        "patterns": {k: level(v) for k, v in feats.items() if k.endswith("_match_ratio")},
    }
    return hashlib.sha256(json.dumps(sig, sort_keys=True, default=str).encode()).hexdigest()
