"""Heuristic PII discovery for columns: name heuristics + data type + value validators +
pattern frequency -> category, sensitivity label, confidence and a safe evidence summary.

Automated classification is heuristic. It cannot guarantee every sensitive field is found,
which is why results go through a human review workflow and unknown columns of
un-scanned tables are never queryable.

Extending: append a `Detector` to DETECTORS. No core changes are required."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from . import entities as E

SENSITIVITY = {
    "CREDIT_CARD": "PII_HIGH",
    "NATIONAL_ID": "PII_HIGH",
    "BANK_ACCOUNT": "PII_HIGH",
    "EMAIL": "PII_MEDIUM",
    "PHONE": "PII_MEDIUM",
    "PERSON_NAME": "PII_MEDIUM",
    "POSTAL_ADDRESS": "PII_MEDIUM",
    "DATE_OF_BIRTH": "PII_MEDIUM",
    "FREE_TEXT_PII": "PII_MEDIUM",
    "UPI_ID": "PII_MEDIUM",
    "ACCOUNT_NUMBER": "FINANCIAL_CONFIDENTIAL",
    "FINANCIAL_AMOUNT": "FINANCIAL_CONFIDENTIAL",
    "CREDIT_SCORE": "FINANCIAL_CONFIDENTIAL",
    "CUSTOMER_ID": "INTERNAL",
    "ORG_CONTACT": "INTERNAL",
    "NONE": "PUBLIC",
}
CATEGORIES = list(SENSITIVITY.keys())
LABELS = ["PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL", "INTERNAL", "PUBLIC"]
SENSITIVE_LABELS = {"PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL"}

SUGGESTED = {
    "CREDIT_CARD": "PARTIAL",
    "NATIONAL_ID": "REDACT",
    "BANK_ACCOUNT": "PARTIAL",
    "EMAIL": "PARTIAL",
    "PHONE": "PARTIAL",
    "PERSON_NAME": "PARTIAL",
    "POSTAL_ADDRESS": "PARTIAL",
    "DATE_OF_BIRTH": "GENERALIZE",
    "FREE_TEXT_PII": "PARTIAL",
    "UPI_ID": "PARTIAL",
    "ACCOUNT_NUMBER": "PARTIAL",
    "FINANCIAL_AMOUNT": "GENERALIZE",
    "CREDIT_SCORE": "GENERALIZE",
    "CUSTOMER_ID": "ALLOW",
    "ORG_CONTACT": "ALLOW",
    "NONE": "ALLOW",
}

# Column-name hints. Tokens are matched against the snake/camel-split name.
# Includes the abbreviated, legacy and mixed-language names found in real banking schemas
# (e.g. Saffron Bank: mob_no, emailid, addr_line1, pita_nm, curr_bal, CARD_NO, NAME_ON_CARD).
NAME_HINTS: dict[str, list[str]] = {
    "EMAIL": ["email", "e_mail", "mail", "emailid", "email_id", "mail_id"],
    "PHONE": ["phone", "mobile", "mob", "mob_no", "mobile_no", "alt_mob", "cell", "tel", "telephone", "contact_no", "msisdn", "phone_no"],
    "CREDIT_CARD": ["card", "card_number", "card_no", "cc", "credit_card", "ccnum", "pan_card"],
    "NATIONAL_ID": ["ssn", "aadhaar", "aadhar", "aadhaar_no", "uid", "national_id", "nino", "pan", "pan_no", "tax_id", "passport", "nid", "tin"],
    "BANK_ACCOUNT": ["iban", "bank_account", "routing"],
    "ACCOUNT_NUMBER": ["account_number", "account_no", "acct_no", "acct_number", "acc_no", "account_num", "linked_acct", "linked_account"],
    "PERSON_NAME": ["name", "nm", "full_name", "first_name", "last_name", "surname", "given_name", "customer_name", "cust_nm",
                    "pita_nm", "father_name", "nominee_nm", "nominee_name", "name_on_card", "holder", "counterparty", "beneficiary", "payee"],
    "POSTAL_ADDRESS": ["address", "street", "addr", "postal_address", "address_line", "addr_line1", "addr_line2", "us_addr"],
    "DATE_OF_BIRTH": ["dob", "dob_dt", "date_of_birth", "birth_date", "birthdate", "birthday"],
    "FINANCIAL_AMOUNT": ["balance", "bal", "curr_bal", "bal_after", "amount", "amt", "inr", "salary", "income", "credit_limit",
                         "limit", "od_limit", "outstanding", "sanctioned", "net_worth", "loan_amount"],
    "CREDIT_SCORE": ["credit_score", "cibil", "cibil_score", "bureau_score"],
    "CUSTOMER_ID": ["customer_id", "cust_id", "client_id", "customerid", "clientid", "cif"],
    "UPI_ID": ["upi", "upi_id", "vpa"],
    "FREE_TEXT_PII": ["description", "notes", "note", "comment", "comments", "message", "body", "details", "narration",
                      "ticket_text", "remarks", "extra_info", "text", "memo"],
}
# Name tokens that look like a hint but are not personal data.
NAME_EXCLUSIONS = {"username", "filename", "file_name", "table_name", "product_name", "branch_name", "bank_name", "merchant_name", "name_id"}
# Column-name context that means capitalised multi-word values are NOT people.
NON_PERSON_CONTEXT = {"merchant", "product", "company", "bank", "branch", "city", "store", "vendor", "brand", "employer",
                      "addr", "address", "street", "locality", "area",
                      "team", "category", "street", "country", "region", "department", "org", "organisation", "organization"}
# Organisational context (column or table): contact details belong to the bank, not a person.
ORG_CONTEXT = {"branch", "branches", "merchant", "merchants", "store", "office", "bank"}
# Reference / transaction identifiers: digit runs here are references, not IDs or phones.
REFERENCE_CONTEXT = {"rrn", "ref", "utr", "reference", "txn", "stan", "arn"}
REFERENCE_SUPPRESSED = {"NATIONAL_ID", "PHONE", "ACCOUNT_NUMBER", "CUSTOMER_ID"}


def _split_name(col: str) -> tuple[str, set[str]]:
    snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", col).lower()
    tokens = set(t for t in re.split(r"[^a-z0-9]+", snake) if t)
    return snake, tokens


def name_hint(col: str, category: str) -> float:
    snake, tokens = _split_name(col)
    if snake in NAME_EXCLUSIONS:
        return 0.0
    best = 0.0
    for hint in NAME_HINTS.get(category, []):
        if snake == hint:
            best = max(best, 1.0)
        elif "_" in hint and hint in snake:
            best = max(best, 0.9)
        elif hint in tokens:
            best = max(best, 0.8)
    return best


@dataclass
class Detector:
    category: str
    value_check: Callable[[str], bool] | None = None
    type_check: Callable[[str, list[Any]], bool] | None = None
    min_fraction: float = 0.6
    contains: bool = False  # match anywhere in free text rather than the whole value
    description: str = ""


def _is_numeric_type(dtype: str, values: list[Any]) -> bool:
    if re.search(r"int|num|dec|real|float|double|money", dtype, re.I):
        return True
    return bool(values) and all(isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in values)


def _is_date(v: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?|\d{2}/\d{2}/\d{4}", v.strip()))


def _contains_pii(v: str) -> bool:
    """Free text with embedded entities - not a value that *is* a single entity."""
    text = v.strip()
    if len(text) <= 15:
        return False
    spans = E.find_spans(text)
    covered = sum(s.end - s.start for s in spans)
    return bool(spans) and covered < 0.8 * len(text)


DETECTORS: list[Detector] = [
    Detector("EMAIL", lambda v: bool(E.EMAIL_RE.fullmatch(v.strip())), description="RFC-style email format"),
    Detector("CREDIT_CARD", E.is_card, description="13-19 digits, issuer prefix, Luhn checksum"),
    Detector("NATIONAL_ID", lambda v: E.national_id_format(v) is not None, description="national-ID shape (SSN / Aadhaar / PAN / NINO)"),
    Detector("UPI_ID", lambda v: bool(E.UPI_RE.fullmatch(v.strip())), description="UPI handle format"),
    Detector("BANK_ACCOUNT", E.iban_ok, description="IBAN with mod-97 checksum"),
    Detector("PHONE", E.is_phone, description="10-15 digit phone format"),
    Detector("DATE_OF_BIRTH", _is_date, min_fraction=0.8, description="date values"),
    Detector("PERSON_NAME", lambda v: bool(E.NAME_RE.fullmatch(v.strip())), min_fraction=0.7, description="capitalised 2-4 word names"),
    Detector("POSTAL_ADDRESS", E.is_address, min_fraction=0.6, description="street / house / locality address shape"),
    Detector("ACCOUNT_NUMBER", lambda v: bool(re.fullmatch(r"[A-Z]{0,4}\d{8,18}", v.strip())), description="8-18 digit account format"),
    Detector("FINANCIAL_AMOUNT", lambda v: bool(re.fullmatch(r"-?\d{1,15}(\.\d{1,4})?", v.strip().replace(",", ""))), type_check=_is_numeric_type, description="numeric amounts"),
    Detector("CREDIT_SCORE", lambda v: bool(re.fullmatch(r"[3-9]\d{2}", v.strip())), description="300-999 score range"),
    Detector("CUSTOMER_ID", lambda v: bool(re.fullmatch(r"[A-Z]{0,5}-?[A-Z0-9]{1,16}", v.strip())), description="identifier shape"),
    Detector("FREE_TEXT_PII", _contains_pii, min_fraction=0.15, contains=True, description="embedded entities in free text"),
]

# Categories where value shape alone is too weak (numbers, dates, short ids) - a
# name hint is required, otherwise every numeric column would look sensitive.
NAME_REQUIRED = {"DATE_OF_BIRTH", "ACCOUNT_NUMBER", "FINANCIAL_AMOUNT", "CUSTOMER_ID", "CREDIT_SCORE"}
MIXED_CONTENT_MIN = 0.1  # share of values carrying a validated entity to flag a mixed column


@dataclass
class ColumnResult:
    column: str
    data_type: str
    category: str
    sensitivity: str
    confidence: float
    method: str
    evidence: str
    sample_count: int
    suggested_masking: str
    candidates: list[dict[str, Any]] = field(default_factory=list)


def _to_str(v: Any) -> str:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def _table_tokens(table: str | None) -> set[str]:
    if not table:
        return set()
    _, toks = _split_name(table)
    return toks | {t[:-1] for t in toks if t.endswith("s")}


def classify_column(column: str, data_type: str, samples: list[Any], table: str | None = None) -> ColumnResult:
    """Classify one column. `samples` are used transiently and never stored or returned."""
    values = [v for v in samples if v is not None and _to_str(v).strip() != ""]
    strs = [_to_str(v) for v in values]
    n = len(strs)
    scored: list[tuple[float, str, str, str]] = []  # (confidence, category, method, evidence)

    _, col_tokens = _split_name(column)
    reference_col = bool(col_tokens & REFERENCE_CONTEXT)
    for det in DETECTORS:
        if det.category == "PERSON_NAME" and col_tokens & NON_PERSON_CONTEXT:
            continue
        if reference_col and det.category in REFERENCE_SUPPRESSED:
            continue
        hint = name_hint(column, det.category)
        frac = 0.0
        if n and det.value_check:
            frac = sum(1 for s in strs if det.value_check(s)) / n
        type_ok = det.type_check(data_type, values) if det.type_check else None

        if det.category in NAME_REQUIRED:
            if hint == 0:
                continue
            if det.category == "FINANCIAL_AMOUNT" and type_ok is False and frac < 0.8:
                continue
            conf = 0.55 * hint + 0.45 * (frac if n else 0.5)
            method = "column-name + value-shape" if frac >= det.min_fraction else "column-name"
        else:
            if n == 0 and hint == 0:
                continue
            if frac < det.min_fraction and hint < 0.8:
                continue
            if n and frac < 0.2 and det.value_check and not det.contains:
                # name says one thing, data clearly says another: weak evidence only
                conf = 0.35 * hint
            elif n == 0:
                conf = 0.65 * hint
            else:
                conf = 0.7 * frac + 0.3 * hint if frac >= det.min_fraction else 0.4 * hint + 0.4 * frac
                if det.contains and frac >= det.min_fraction:
                    conf = min(0.95, 0.55 + frac * 0.4 + 0.1 * hint)
            if det.contains and hint >= 0.8 and 0.03 <= frac < det.min_fraction:
                # a named free-text column with occasional embedded entities is still free text with PII
                conf = 0.55 + frac
            parts = []
            if frac >= det.min_fraction:
                parts.append("value-pattern")
            if hint:
                parts.append("column-name")
            method = " + ".join(parts) or "column-name"
        evidence_bits = []
        if n and det.value_check:
            matched = round(frac * n)
            evidence_bits.append(f"{matched}/{n} samples match {det.description}")
        if hint:
            evidence_bits.append(f"column name suggests {det.category.lower().replace('_', ' ')}")
        scored.append((round(min(conf, 0.99), 3), det.category, method, "; ".join(evidence_bits)))

    scored.sort(key=lambda t: -t[0])
    candidates = [{"category": c, "confidence": conf} for conf, c, _, _ in scored[:3]]
    if scored and scored[0][0] >= 0.5:
        conf, cat, method, evidence = scored[0]
        org = (col_tokens | _table_tokens(table)) & ORG_CONTEXT
        if org and cat in ("PHONE", "EMAIL", "POSTAL_ADDRESS"):
            # e.g. branches.branch_phone - an organisational contact, not personal data
            return ColumnResult(column, data_type, "ORG_CONTACT", SENSITIVITY["ORG_CONTACT"], conf,
                                method + " + organisational context",
                                f"{evidence}; {'/'.join(sorted(org))} context -> business contact", n, "ALLOW", candidates)
        return ColumnResult(column, data_type, cat, SENSITIVITY[cat], conf, method, evidence, n, SUGGESTED[cat], candidates)

    if n and "id" not in col_tokens:
        # Mixed columns: a legacy field that sometimes carries a card number, phone, UPI ID...
        # (Identifier columns are excluded: random numeric IDs pass Luhn ~10% of the time.)
        hits: dict[str, int] = {}
        with_entity = 0
        for s in strs:
            spans = E.find_spans(s)
            if spans:
                with_entity += 1
                for sp in spans:
                    hits[sp.category] = hits.get(sp.category, 0) + 1
        frac = with_entity / n
        if frac >= MIXED_CONTENT_MIN:
            kinds = ", ".join(f"{k.lower().replace('_', ' ')} x{v}" for k, v in sorted(hits.items(), key=lambda x: -x[1]))
            return ColumnResult(column, data_type, "FREE_TEXT_PII", SENSITIVITY["FREE_TEXT_PII"], round(min(0.9, 0.5 + 0.4 * frac), 3),
                                "mixed-content value pattern",
                                f"{with_entity}/{n} samples contain validated entities ({kinds}); other values left readable by span masking",
                                n, "PARTIAL", candidates)

    snake, tokens = _split_name(column)
    internal = snake == "id" or "id" in tokens or tokens & ({"date", "time", "created", "updated", "at", "status", "code", "type",
                                                             "ts", "dt", "ref", "by", "to", "meta"} | REFERENCE_CONTEXT)
    label = "INTERNAL" if internal else "PUBLIC"
    return ColumnResult(
        column,
        data_type,
        "NONE",
        label,
        round(min(0.95, 1 - (scored[0][0] if scored else 0.0)), 3),
        "no detector above threshold",
        f"{n} samples inspected; no sensitive pattern above threshold",
        n,
        "ALLOW",
        candidates,
    )
