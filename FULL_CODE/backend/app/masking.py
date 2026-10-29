"""Masking transformations. Pure functions: value + category -> protected value.

Masking happens on the server after execution and before serialisation; the source
database is never modified."""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .config import get_settings, hmac_key

REDACTED = "[REDACTED]"

ACTIONS = {
    "ALLOW": "Return the value unchanged",
    "PARTIAL": "Category-aware partial masking (e.g. last 4 digits visible)",
    "REDACT": "Replace with [REDACTED]",
    "HASH": "Deterministic HMAC-SHA-256 pseudonym (server-side key)",
    "GENERALIZE": "Amounts to ranges, dates to year; other types are redacted",
    "AGGREGATE_ONLY": "Redacted per row; SUM/AVG/COUNT allowed over groups of at least k rows",
    "BREAK_GLASS": "Partial by default; raw only with permission + recorded justification",
    "DENY": "Any query referencing the column is rejected",
}

# Actions that return the raw value (used by the SQL guard to decide whether a column may
# appear in predicates without enabling inference attacks).
RAW_ACTIONS = {"ALLOW"}


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _mask_keep_last(s: str, keep: int = 4, mask_char: str = "*") -> str:
    """Mask alphanumerics except the last `keep`, preserving separators."""
    alnum_positions = [i for i, ch in enumerate(s) if ch.isalnum()]
    if len(alnum_positions) <= keep:
        return mask_char * max(len(s), 4)
    visible = set(alnum_positions[-keep:])
    return "".join(ch if (i in visible or not ch.isalnum()) else mask_char for i, ch in enumerate(s))


def mask_email(s: str) -> str:
    if s.count("@") != 1:
        return _mask_keep_last(s)
    local, domain = s.split("@")
    if not local or not domain:
        return REDACTED
    return f"{local[0]}***@{domain}"


def mask_upi(s: str) -> str:
    if s.count("@") != 1:
        return _mask_keep_last(s)
    local, handle = s.split("@")
    return f"{local[:1]}***@{handle}" if local else REDACTED


def score_band(v: Any) -> str:
    try:
        x = int(Decimal(str(v).strip()))
    except (InvalidOperation, ValueError):
        return REDACTED
    lo = (x // 50) * 50
    return f"{lo}–{lo + 49}"


def mask_card(s: str) -> str:
    d = _digits(s)
    if not 12 <= len(d) <= 19:
        return _mask_keep_last(s)
    middle = "X" * (len(d) - 8)
    groups = [d[:4]] + [middle[i : i + 4] for i in range(0, len(middle), 4)] + [d[-4:]]
    return "-".join(groups)


def mask_phone(s: str) -> str:
    d = _digits(s)
    if len(d) < 7:
        return "*" * max(len(s), 4)
    return "*" * (len(d) - 4) + d[-4:]


def mask_name(s: str) -> str:
    parts = [p for p in re.split(r"\s+", s.strip()) if p]
    if not parts:
        return REDACTED
    return " ".join(p[0] + "*" * max(len(p) - 1, 3) for p in parts)


def mask_address(s: str) -> str:
    # Keep only the final locality component; drop street-level detail.
    if "," in s:
        tail = s.rsplit(",", 1)[1].strip()
        if tail:
            return f"*** {tail}"
    return "[ADDRESS]"


def _parse_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def mask_dob(v: Any) -> str:
    d = _parse_date(v)
    return f"{d.year}-**-**" if d else REDACTED


_BANDS = [0, 100, 1_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]


def amount_band(v: Any) -> str:
    try:
        x = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return REDACTED
    if x < 0:
        return "< 0"
    for lo, hi in zip(_BANDS, _BANDS[1:]):
        if lo <= x < hi:
            return f"{lo:,}–{hi:,}"
    return f"≥ {_BANDS[-1]:,}"


def pseudonym(value: Any, category: str) -> str:
    """HMAC-SHA-256 keyed pseudonym. Same input + same key -> same output. The category is
    part of the message for domain separation. Pseudonymisation is NOT anonymisation:
    whoever holds the key can confirm guesses."""
    s = str(value).strip()
    if category in ("EMAIL",):
        s = s.lower()
    elif category in ("CREDIT_CARD", "PHONE"):
        s = _digits(s) or s
    msg = f"{category}:{s}".encode("utf-8")
    digest = hmac.new(hmac_key(), msg, hashlib.sha256).hexdigest()
    return f"hm_{get_settings().hmac_key_id}_{digest[:16]}"


def partial(value: Any, category: str) -> Any:
    s = str(value)
    match category:
        case "EMAIL":
            return mask_email(s)
        case "CREDIT_CARD":
            return mask_card(s)
        case "PHONE":
            return mask_phone(s)
        case "PERSON_NAME":
            return mask_name(s)
        case "POSTAL_ADDRESS":
            return mask_address(s)
        case "DATE_OF_BIRTH":
            return mask_dob(value)
        case "FINANCIAL_AMOUNT":
            # Never replace digits of an amount: that would produce a misleading number.
            return amount_band(value)
        case "FREE_TEXT_PII":
            from .entities import mask_text

            return mask_text(s)
        case "NATIONAL_ID":
            return _mask_keep_last(s, keep=4, mask_char="X")
        case "UPI_ID":
            return mask_upi(s)
        case "CREDIT_SCORE":
            return score_band(value)
        case _:
            return _mask_keep_last(s)


def generalize(value: Any, category: str) -> Any:
    if category == "CREDIT_SCORE":
        return score_band(value)
    if category == "FINANCIAL_AMOUNT" or isinstance(value, (int, float, Decimal)) and category not in (
        "CREDIT_CARD",
        "PHONE",
        "ACCOUNT_NUMBER",
        "CUSTOMER_ID",
    ):
        return amount_band(value)
    if category == "DATE_OF_BIRTH":
        d = _parse_date(value)
        return str(d.year) if d else REDACTED
    return REDACTED


def apply(action: str, value: Any, category: str) -> Any:
    """Apply a masking action. Unknown actions fail closed to redaction."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):  # JSON/JSONB columns (PostgreSQL, MySQL) -> canonical JSON text
        import json

        value = json.dumps(value, ensure_ascii=False)
    if action == "ALLOW":
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return REDACTED
    if isinstance(value, str) and value == "":
        return ""
    if action == "PARTIAL":
        return partial(value, category)
    if action == "HASH":
        return pseudonym(value, category)
    if action == "GENERALIZE":
        return generalize(value, category)
    # REDACT, AGGREGATE_ONLY (row level), DENY (never reached), anything unknown
    return REDACTED
