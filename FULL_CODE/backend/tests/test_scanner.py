from app.entities import find_spans, iban_ok, is_card, is_phone, luhn_ok, national_id_match, verhoeff_check_digit, verhoeff_ok
from app.scanner import classify_column

EMAILS = ["asha.verma@inbox.example", "j.doe+tag@example.org", "a@example.net", "x_y@sub.example.com"]


def test_valid_and_invalid_emails():
    r = classify_column("contact", "VARCHAR", EMAILS * 5)
    assert r.category == "EMAIL" and r.sensitivity == "PII_MEDIUM"
    bad = classify_column("contact", "VARCHAR", ["not-an-email", "a@b", "@example.com", "foo@"] * 5)
    assert bad.category != "EMAIL"


def test_phone_patterns():
    assert is_phone("+1-202-555-0143")
    assert is_phone("(202) 555-0143")
    assert is_phone("2025550143")
    assert not is_phone("12345")
    assert not is_phone("4111 1111 1111 1111")  # card, not phone
    r = classify_column("mobile", "TEXT", ["+1-202-555-01%02d" % i for i in range(30)])
    assert r.category == "PHONE"


def test_credit_card_luhn():
    assert luhn_ok("4111111111111111") and is_card("4111 1111 1111 1111")
    assert not is_card("4111111111111112")  # bad checksum
    assert not is_card("1234567812345670")  # Luhn-valid but no issuer prefix
    assert not is_card("0000000000000000")
    r = classify_column("cc", "TEXT", ["4111111111111111", "5555555555554444", "378282246310005"] * 10)
    assert r.category == "CREDIT_CARD" and r.sensitivity == "PII_HIGH"


def test_numeric_ids_are_not_cards():
    # Sequential numeric identifiers occasionally pass Luhn by chance; frequency must stop that.
    ids = [str(4000000000000000 + i) for i in range(100)]
    r = classify_column("ref", "TEXT", ids)
    assert r.category != "CREDIT_CARD"
    r2 = classify_column("order_id", "INTEGER", list(range(1, 200)))
    assert r2.category == "NONE"


def test_amounts_need_name_hint():
    vals = [12.5, 990.0, 15000.25, 7.0] * 10
    assert classify_column("balance", "NUMERIC(14,2)", vals).category == "FINANCIAL_AMOUNT"
    assert classify_column("quantity", "NUMERIC(14,2)", vals).category == "NONE"


def test_sensitive_column_names_with_no_samples():
    r = classify_column("customer_email", "TEXT", [])
    assert r.category == "EMAIL" and r.method == "column-name"
    assert classify_column("date_of_birth", "DATE", []).category == "DATE_OF_BIRTH"


def test_confidence_scores_are_ordered():
    strong = classify_column("email", "TEXT", EMAILS * 5)
    weak = classify_column("email", "TEXT", EMAILS + ["n/a"] * 6)  # name says email, data mostly not
    assert strong.confidence > weak.confidence
    assert 0 <= weak.confidence <= 1


def test_malformed_and_null_values():
    r = classify_column("email", "TEXT", [None, None, "", "   ", None])
    assert r.sample_count == 0
    r2 = classify_column("notes", "TEXT", [None, 12, b"\x00\x01", "plain"])
    assert r2.category in ("NONE", "FREE_TEXT_PII")


def test_names_vs_merchants():
    names = ["Asha Verma", "José Núñez", "Kenji Tanaka", "Lena Varga"] * 5
    assert classify_column("full_name", "TEXT", names).category == "PERSON_NAME"
    assert classify_column("merchant_name", "TEXT", ["Northwind Grocers", "Contoso Fuel"] * 10).category == "NONE"


def test_jurisdiction_rules_are_distinct():
    base = "23412341234"
    aadhaar = base + verhoeff_check_digit(base)
    assert verhoeff_ok(aadhaar) and national_id_match(aadhaar) == "IN_AADHAAR"
    assert national_id_match(base + str((int(verhoeff_check_digit(base)) + 1) % 10)) is None
    assert national_id_match("123-45-6789") == "US_SSN"
    assert national_id_match("666-45-6789") is None  # invalid SSN area
    assert national_id_match("AB123456C") == "UK_NINO"
    assert national_id_match("ABCPE1234F") == "IN_PAN"


def test_iban_checksum():
    assert iban_ok("GB82WEST12345698765432")
    assert not iban_ok("GB83WEST12345698765432")


def test_free_text_spans():
    text = "Call +1-202-555-0143 or mail asha@inbox.example; card 4111 1111 1111 1111."
    cats = [s.category for s in find_spans(text)]
    assert cats == ["PHONE", "EMAIL", "CREDIT_CARD"]


def test_manual_override_survives_rescan(client, H, conn_id):
    cls = client.get("/api/classifications", params={"connection_id": conn_id, "table": "customers"}, headers=H["admin"]).json()
    seg = next(c for c in cls if c["column"] == "segment")
    r = client.patch(f"/api/classifications/{seg['id']}", json={"decision": "override", "category": "PERSON_NAME"}, headers=H["admin"])
    assert r.status_code == 200 and r.json()["review_status"] == "overridden"
    r = client.post(f"/api/databases/{conn_id}/scan", json={"sample_size": 50}, headers=H["admin"])
    assert r.json()["status"] == "completed"
    after = client.get("/api/classifications", params={"connection_id": conn_id, "table": "customers"}, headers=H["admin"]).json()
    seg2 = next(c for c in after if c["column"] == "segment")
    assert seg2["category"] == "PERSON_NAME" and seg2["detected_category"] == "NONE"
    # restore
    client.patch(f"/api/classifications/{seg['id']}", json={"decision": "reject"}, headers=H["admin"])


def test_scan_results_contain_no_raw_values(client, H, conn_id):
    text = client.get("/api/classifications", params={"connection_id": conn_id}, headers=H["admin"]).text
    assert "@example." not in text and "555-01" not in text


# ---------------------------------------------------------------- official Saffron Bank schema
import sqlite3  # noqa: E402

import pytest  # noqa: E402

from app import saffron  # noqa: E402

SAFFRON_EXPECTED = {
    ("customers", "cust_nm"): "PERSON_NAME", ("customers", "mob_no"): "PHONE", ("customers", "emailid"): "EMAIL",
    ("customers", "addr_line1"): "POSTAL_ADDRESS", ("customers", "addr_line2"): "POSTAL_ADDRESS",
    ("customers", "dob_dt"): "DATE_OF_BIRTH", ("customers", "pita_nm"): "PERSON_NAME", ("customers", "alt_mob"): "PHONE",
    ("customers", "customer_id"): "CUSTOMER_ID", ("customers", "segment"): "NONE", ("customers", "city"): "NONE",
    ("kyc_records", "pan_no"): "NATIONAL_ID", ("kyc_records", "aadhaar_no"): "NATIONAL_ID", ("kyc_records", "kyc_meta"): "FREE_TEXT_PII",
    ("kyc_records", "verified_by"): "NONE",
    ("international_customers", "ssn"): "NATIONAL_ID", ("international_customers", "us_phone"): "PHONE",
    ("international_customers", "us_addr"): "POSTAL_ADDRESS",
    ("accounts", "account_no"): "ACCOUNT_NUMBER", ("accounts", "curr_bal"): "FINANCIAL_AMOUNT", ("accounts", "nominee_nm"): "PERSON_NAME",
    ("accounts", "int_rate_pct"): "NONE", ("accounts", "acct_type"): "NONE",
    ("cards", "CARD_NO"): "CREDIT_CARD", ("cards", "NAME_ON_CARD"): "PERSON_NAME", ("cards", "CREDIT_LIMIT"): "FINANCIAL_AMOUNT",
    ("cards", "LINKED_ACCT"): "ACCOUNT_NUMBER", ("cards", "CARD_REF"): "NONE", ("cards", "CARD_NETWORK"): "NONE",
    ("transactions", "amount_inr"): "FINANCIAL_AMOUNT", ("transactions", "narration"): "FREE_TEXT_PII",
    ("transactions", "ref_no"): "FREE_TEXT_PII", ("transactions", "rrn"): "NONE", ("transactions", "txn_id"): "NONE",
    ("transactions", "counterparty"): "PERSON_NAME",
    ("support_tickets", "ticket_text"): "FREE_TEXT_PII", ("support_tickets", "notes"): "FREE_TEXT_PII",
    ("loan_applications", "declared_income_inr"): "FINANCIAL_AMOUNT", ("loan_applications", "sanctioned_amt_inr"): "FINANCIAL_AMOUNT",
    ("loan_applications", "credit_score"): "CREDIT_SCORE", ("loan_applications", "col_7"): "NATIONAL_ID",
    ("loan_applications", "roi_pct"): "NONE",
    ("branches", "branch_phone"): "ORG_CONTACT", ("branches", "branch_email"): "ORG_CONTACT", ("branches", "ifsc"): "NONE",
}


@pytest.mark.skipif(not saffron.dataset_available(), reason="official dataset not found")
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_official_schema_classification(seed):
    """Classify the real columns from three different random samples; results must be stable."""
    con = sqlite3.connect(f"file:{saffron.official_file('sql', 'sqlite', 'saffron_bank.db').as_posix()}?mode=ro", uri=True)
    import random
    rng = random.Random(seed)
    by_table: dict[str, list[str]] = {}
    for t, c in SAFFRON_EXPECTED:
        by_table.setdefault(t, []).append(c)
    for t, cols in by_table.items():
        total = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        offsets = sorted(rng.sample(range(total), min(300, total)))
        info = {r[1]: r[2] for r in con.execute(f'PRAGMA table_info("{t}")')}
        rows = [con.execute(f'SELECT * FROM "{t}" LIMIT 1 OFFSET {o}').fetchone() for o in offsets]
        names = list(info)
        for col in cols:
            vals = [r[names.index(col)] for r in rows]
            got = classify_column(col, info[col], vals, table=t).category
            assert got == SAFFRON_EXPECTED[(t, col)], f"{t}.{col}: {got}"
    con.close()


def test_synthetic_identifier_shapes_are_still_protected():
    from app.entities import national_id_format, verhoeff_ok
    assert not verhoeff_ok("726113654858") and national_id_format("7261 1365 4858") == "IN_AADHAAR_FORMAT"
    assert national_id_format("xxxx-xxxx-5336") == "IN_AADHAAR_FORMAT"
    assert national_id_format("958-36-0218") == "US_SSN_FORMAT" and national_id_format("910 36 8698") == "US_SSN_FORMAT"
    assert national_id_format("ZXIPY0000H") == "IN_PAN"
    assert national_id_format("614403139086") is None  # bare 12-digit RRN is not treated as Aadhaar


def test_structured_narration_and_keyed_json():
    from app.entities import mask_text
    assert mask_text("UPI/CR/527407519132/ANOOP MENON/9999960427@pragatiupi/dinner") == "UPI/CR/527407519132/A**** M****/9***@pragatiupi/dinner"
    assert mask_text('{"src": "X", "uid": "402850429751", "dms_ref": "509587093577"}') == '{"src": "X", "uid": "[NATIONAL-ID]", "dms_ref": "509587093577"}'
    assert mask_text("INT.PD:01-10-2025 TO 31-03-2026") == "INT.PD:01-10-2025 TO 31-03-2026"
