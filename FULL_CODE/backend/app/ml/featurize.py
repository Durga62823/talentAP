"""Features for the ML classifier.

Numeric part: the scanner's sanitized statistics (ai_features.extract_features) plus a few more
aggregates that help separate look-alike classes (birth dates vs other dates, credit scores vs
amounts). Text part: table + column name, consumed by a character n-gram model so abbreviated
and legacy names (mob_no, pita_nm, acct_bal) are recognised.

The rule engine's verdict is deliberately NOT a feature: the model must be an independent
second opinion, not a copy of the rules."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..ai_features import extract_features
from ..scanner import ColumnResult

THIS_YEAR = 2026
DTYPES = ("int", "dec", "char", "text", "date", "time", "bool")
YEAR_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}")
EXCLUDED = {"table_name", "column_name", "data_type", "rule_engine", "sample_size"}


def _s(v: Any) -> str:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v).strip()


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def dtype_flags(data_type: str) -> dict[str, float]:
    t = (data_type or "").lower()
    return {
        "dtype_int": float("int" in t),
        "dtype_dec": float(any(k in t for k in ("dec", "num", "real", "float", "double", "money"))),
        "dtype_char": float("char" in t),
        "dtype_text": float("text" in t or "clob" in t),
        "dtype_date": float("date" in t and "time" not in t),
        "dtype_time": float("time" in t),
        "dtype_bool": float("bool" in t),
    }


def extra_aggregates(samples: list[Any]) -> dict[str, float]:
    vals = [v for v in samples if v is not None and _s(v) != ""]
    strs = [_s(v) for v in vals]
    n = len(strs) or 1
    years = [int(m.group(1)) for s in strs if (m := YEAR_RE.match(s))]
    nums = [x for x in (_num(v) for v in vals) if x is not None and math.isfinite(x)]
    chars = sum(len(s) for s in strs) or 1
    distinct = len(set(strs))
    return {
        "birth_year_ratio": sum(1 for y in years if 1930 <= y <= THIS_YEAR - 18) / n,
        "recent_year_ratio": sum(1 for y in years if y >= THIS_YEAR - 15) / n,
        "uppercase_char_ratio": sum(1 for s in strs for ch in s if ch.isupper()) / chars,
        "digit_char_ratio": sum(1 for s in strs for ch in s if ch.isdigit()) / chars,
        "distinct_count_log": math.log10(distinct + 1),
        "low_cardinality": float(distinct <= 12),
        "numeric_value_ratio": len(nums) / n,
        "integer_value_ratio": sum(1 for x in nums if x == int(x)) / n,
        "numeric_mean_log": math.log10(abs(sum(nums) / len(nums)) + 1) if nums else 0.0,
        "score_range_ratio": sum(1 for x in nums if 300 <= x <= 900 and x == int(x)) / n,
        "percent_range_ratio": sum(1 for x in nums if 0 < x <= 40 and x != int(x)) / n,
    }


def column_text(table: str, column: str) -> str:
    """Name text for the n-gram model: split snake/camel case, keep the raw form too."""
    def norm(s: str) -> str:
        return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", s or "").lower()
    return f"{norm(table)} {norm(column)}"


def build(table: str, column: str, data_type: str, nullable: bool, primary_key: bool,
          samples: list[Any], rule: ColumnResult, base: dict[str, Any] | None = None) -> tuple[dict[str, float], str]:
    """-> (numeric feature dict, name text). `base` reuses features the scan already computed."""
    feats = base if base is not None else extract_features(table, column, data_type, nullable, primary_key, samples, rule)
    numeric = {k: float(v) for k, v in feats.items() if k not in EXCLUDED and isinstance(v, (int, float, bool))}
    numeric.update(dtype_flags(data_type))
    numeric.update(extra_aggregates(samples))
    return numeric, column_text(table, column)
