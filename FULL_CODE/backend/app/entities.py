"""Value-level PII detectors with format validation (Luhn, Verhoeff, IBAN mod-97, SSN area
rules). Used for column sampling, free-text span masking and document scanning.

Jurisdiction-specific national identifier rules are opt-in via SENTINEL_JURISDICTIONS
(default "US,IN,UK"); identifiers are never assumed to share one format across countries.

Two levels are distinguished on purpose:
  * `valid`  - passes the real-world check (Verhoeff for Aadhaar, issued SSN areas, ...)
  * `format` - has the identifier's shape. For PROTECTION, shape is enough: synthetic or
    mistyped identifiers must still be masked. Validity only raises confidence. (The
    official hackathon data deliberately uses Aadhaar numbers that fail Verhoeff and SSNs
    in the never-issued 9xx area.)"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
EMAIL_SPAN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
CARD_SPAN = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
PHONE_SPAN = re.compile(r"(?<![\w+])(\+?\(?\d[\d\s().-]{7,18}\d)(?!\w)")
SSN_RE = re.compile(r"^(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}$")
SSN_SPAN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")
AADHAAR_RE = re.compile(r"^[2-9]\d{3}\s?\d{4}\s?\d{4}$")
AADHAAR_SPAN = re.compile(r"(?<!\d)[2-9]\d{3}\s\d{4}\s\d{4}(?!\d)")
PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]$")
PAN_SPAN = re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")
NINO_RE = re.compile(r"^(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\d{6}[A-D]$")
NINO_SPAN = re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\d{6}[A-D]\b")
SSN_FORMAT_RE = re.compile(r"^\d{3}[- ]\d{2}[- ]\d{4}$")
SSN_FORMAT_SPAN = re.compile(r"(?<![\d-])\d{3}[- ]\d{2}[- ]\d{4}(?![\d-])")
# Aadhaar shape: needs separators or masking (plain 12-digit runs are too ambiguous - RRNs,
# reference numbers - unless the Verhoeff check passes).
AADHAAR_FORMAT_RE = re.compile(r"^(?:[2-9]\d{3}|[xX*]{4})[ -](?:\d{4}|[xX*]{4})[ -]\d{4}$")
AADHAAR_FORMAT_SPAN = re.compile(r"(?<![\w-])(?:[2-9]\d{3}|[xX*]{4})[ -](?:\d{4}|[xX*]{4})[ -]\d{4}(?![\w-])")
KEYED_ID_SPAN = re.compile(
    r"[\"']?(uid|aadhaar|aadhaar_no|aadhar|ssn|pan|pan_no|national_id|tax_id)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9][A-Za-z0-9 \-]{6,18}[A-Za-z0-9])",
    re.IGNORECASE,
)
# Party-name segment of structured payment narrations (UPI/CR/<rrn>/<NAME>/..., IMPS/P2A/<rrn>/<NAME>/...,
# NEFT/<utr>/<NAME>/...). Names in arbitrary prose are NOT reliably detectable - see README limitations.
NARRATION_PARTY_SPAN = re.compile(r"^(?:UPI/(?:CR|DR)/\d{6,}|IMPS/P2[AM]/\d{6,}|NEFT/[A-Z0-9]{6,})/([A-Z][A-Z .&'\-]{1,60}?)(?=/|$)")
UPI_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{1,63}@[A-Za-z][A-Za-z0-9]{2,24}$")
UPI_SPAN = re.compile(r"(?<![\w.\-@])[A-Za-z0-9][A-Za-z0-9._\-]{1,63}@[A-Za-z][A-Za-z0-9]{2,24}(?![\w.@\-])")
IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
IBAN_SPAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
NAME_RE = re.compile(r"^[A-Z][a-zA-Z'’\-]+(?: [A-Z][a-zA-Z'’\-]+){1,3}$")
ADDRESS_RE = re.compile(
    r"^\d{1,6}[A-Za-z]?\s+[\w .'\-]+\b(St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Blvd|Boulevard|Dr|Drive|"
    r"Way|Ct|Court|Pl|Place|Terrace|Nagar|Marg|Crescent|Close)\b",
    re.IGNORECASE,
)
# Indian address forms: "H.No 20-50/12, Road 11", "Flat 408, Pragati Towers", "Plot 7, Sector 4"
ADDRESS_IN_RE = re.compile(
    r"^(H\.?\s?No\.?|House\s+No\.?|Flat|Plot|Door\s+No\.?|Shop|Apt\.?|Unit|Block|Bldg|#)\s*[\w/\-]+",
    re.IGNORECASE,
)
# Locality lines: "Sundar Township", "Mogra Extension", "Pragati Puram"
LOCALITY_RE = re.compile(
    r"\b(Nagar|Colony|Society|Township|Extension|Residency|Puram|Heights|Apartments?|Towers?|Layout|Enclave|Vihar|"
    r"Bagh|Park|Sector|Phase|Gardens?|Complex|Chowk|Marg|Road|Street|Lane|Cross|Main)\b",
    re.IGNORECASE,
)


def is_address(v: str) -> bool:
    v = v.strip()
    return bool(ADDRESS_RE.match(v) or ADDRESS_IN_RE.match(v) or (len(v.split()) <= 6 and LOCALITY_RE.search(v)))


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def luhn_ok(number: str) -> bool:
    d = _digits(number)
    if not d:
        return False
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_card(value: str) -> bool:
    if not re.fullmatch(r"[\d \-]+", value.strip()):
        return False
    d = _digits(value)
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    # Issuer prefix (Visa 4, Mastercard 2/5, Amex 34/37, Discover/RuPay 6, JCB/Diners 3)
    if d[0] not in "23456":
        return False
    return luhn_ok(d)


_V_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_V_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_ok(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(_digits(number))):
        c = _V_D[c][_V_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(number: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(_digits(number))):
        c = _V_D[c][_V_P[(i + 1) % 8][int(ch)]]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    return str(inv[c])


def iban_ok(value: str) -> bool:
    v = value.replace(" ", "").upper()
    if not IBAN_RE.fullmatch(v):
        return False
    rearranged = v[4:] + v[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def is_phone(value: str) -> bool:
    v = value.strip()
    if not re.fullmatch(r"\+?[\d\s().\-]{7,22}", v):
        return False
    d = _digits(v)
    if not 10 <= len(d) <= 15:
        return False
    formatted = v.startswith("+") or any(c in v for c in " -().")
    if formatted:
        return not is_card(v)
    # Bare digits: typical national formats only - 10 digits (NANP / Indian mobile),
    # trunk-prefixed Indian mobile (0 + 10 digits) or 91 + 10 digits.
    if len(d) == 10:
        return d[0] in "2346789"
    if len(d) == 11:
        return d[0] == "0" and d[1] in "6789"
    if len(d) == 12:
        return d.startswith("91") and d[2] in "6789"
    return False


def jurisdictions() -> set[str]:
    return {j.strip().upper() for j in os.environ.get("SENTINEL_JURISDICTIONS", "US,IN,UK").split(",") if j.strip()}


@dataclass(frozen=True)
class NationalIdRule:
    code: str
    jurisdiction: str
    label: str
    validate: Callable[[str], bool]
    span: re.Pattern[str]


NATIONAL_ID_RULES: list[NationalIdRule] = [
    NationalIdRule("US_SSN", "US", "US Social Security Number", lambda v: bool(SSN_RE.fullmatch(v.strip())), SSN_SPAN),
    NationalIdRule(
        "IN_AADHAAR",
        "IN",
        "India Aadhaar (Verhoeff-validated)",
        lambda v: bool(AADHAAR_RE.fullmatch(v.strip())) and verhoeff_ok(v),
        AADHAAR_SPAN,
    ),
    NationalIdRule("IN_PAN", "IN", "India PAN", lambda v: bool(PAN_RE.fullmatch(v.strip())), PAN_SPAN),
    NationalIdRule("UK_NINO", "UK", "UK National Insurance Number", lambda v: bool(NINO_RE.fullmatch(v.strip().upper().replace(" ", ""))), NINO_SPAN),
]


def national_id_match(value: str) -> str | None:
    """Strict: passes the real-world validity rules."""
    active = jurisdictions()
    for rule in NATIONAL_ID_RULES:
        if rule.jurisdiction in active and rule.validate(value):
            return rule.code
    return None


def national_id_format(value: str) -> str | None:
    """Shape-level match used for protection (see module docstring)."""
    strict = national_id_match(value)
    if strict:
        return strict
    v = value.strip()
    active = jurisdictions()
    if "US" in active and SSN_FORMAT_RE.fullmatch(v):
        return "US_SSN_FORMAT"
    if "IN" in active and AADHAAR_FORMAT_RE.fullmatch(v):
        return "IN_AADHAAR_FORMAT"
    if "IN" in active and PAN_RE.fullmatch(v.upper()):
        return "IN_PAN"
    return None


# ---- span detection for free text ---------------------------------------------------------

@dataclass
class Span:
    start: int
    end: int
    category: str
    subtype: str
    confidence: float


def find_spans(text: str) -> list[Span]:
    """Locate sensitive entities in free text. Overlaps resolve by detection order
    (most specific validators first)."""
    found: list[Span] = []

    def add(start: int, end: int, cat: str, sub: str, conf: float) -> None:
        if any(not (end <= s.start or start >= s.end) for s in found):
            return
        found.append(Span(start, end, cat, sub, conf))

    m = NARRATION_PARTY_SPAN.match(text)
    if m:
        add(m.start(1), m.end(1), "PERSON_NAME", "payment-party", 0.8)
    # Key-aware: identifiers inside JSON / key=value text, e.g. {"uid": "402850429751"}
    for m in KEYED_ID_SPAN.finditer(text):
        add(m.start(2), m.end(2), "NATIONAL_ID", f"keyed:{m.group(1).lower()}", 0.85)
    for m in EMAIL_SPAN.finditer(text):
        add(m.start(), m.end(), "EMAIL", "email", 0.97)
    for m in UPI_SPAN.finditer(text):
        add(m.start(), m.end(), "UPI_ID", "upi", 0.9)
    for m in IBAN_SPAN.finditer(text):
        if iban_ok(m.group()):
            add(m.start(), m.end(), "BANK_ACCOUNT", "IBAN", 0.95)
    active = jurisdictions()
    for rule in NATIONAL_ID_RULES:
        if rule.jurisdiction not in active:
            continue
        for m in rule.span.finditer(text):
            if rule.validate(m.group()):
                add(m.start(), m.end(), "NATIONAL_ID", rule.code, 0.9)
    for m in CARD_SPAN.finditer(text):
        if is_card(m.group()):
            add(m.start(), m.end(), "CREDIT_CARD", "luhn-valid", 0.95)
    if "US" in active:
        for m in SSN_FORMAT_SPAN.finditer(text):
            add(m.start(), m.end(), "NATIONAL_ID", "US_SSN_FORMAT", 0.75)
    if "IN" in active:
        for m in AADHAAR_FORMAT_SPAN.finditer(text):
            sub = "IN_AADHAAR" if verhoeff_ok(m.group()) else "IN_AADHAAR_FORMAT"
            add(m.start(), m.end(), "NATIONAL_ID", sub, 0.9 if sub == "IN_AADHAAR" else 0.75)
    for m in PHONE_SPAN.finditer(text):
        val = m.group(1)
        if is_phone(val):
            add(m.start(1), m.end(1), "PHONE", "phone", 0.8)
    return sorted(found, key=lambda s: s.start)


def mask_text(text: str, spans: list[Span] | None = None) -> str:
    """Replace each detected span with a category-aware partial mask."""
    from .masking import partial  # local import: masking imports this module lazily too

    spans = find_spans(text) if spans is None else spans
    out, pos = [], 0
    for s in spans:
        out.append(text[pos : s.start])
        original = text[s.start : s.end]
        out.append("[NATIONAL-ID]" if s.category == "NATIONAL_ID" else str(partial(original, s.category)))
        pos = s.end
    out.append(text[pos:])
    return "".join(out)
