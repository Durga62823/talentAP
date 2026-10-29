"""SQL safety, lineage and masking-bypass tests on the official Saffron Bank data (real HTTP pipeline)."""
import pytest

from conftest import CUSTOMER, q


def _rows(r):
    assert r.status_code == 200, r.text
    b = r.json()
    return b["columns"], b["rows"], b


def test_same_record_differs_per_role(client, H, conn_id):
    sql = f"SELECT customer_id, cust_nm, mob_no, emailid, dob_dt FROM customers WHERE customer_id = '{CUSTOMER}'"
    a = _rows(q(client, H["admin"], conn_id, sql))[1][0]
    s = _rows(q(client, H["support"], conn_id, sql))[1][0]
    n = _rows(q(client, H["analyst"], conn_id, sql))[1][0]
    c = _rows(q(client, H["compliance"], conn_id, sql))[1][0]
    assert a[0] == s[0] == n[0] == c[0] == CUSTOMER
    assert "@" in a[3] and not a[1].count("*")                          # admin: full view
    assert s[1].count("*") >= 4 and s[2].startswith("*") and s[3].split("@")[0].endswith("***")  # support partial
    assert n[1] == "[REDACTED]" and n[2] == "[REDACTED]" and n[3].startswith("hm_k1_") and len(n[4]) == 4  # analyst
    assert c[1] == s[1] and a[2] not in str(c)                          # compliance never raw


def test_card_partial_masking_matches_problem_statement(client, H, conn_id):
    raw =_rows(q(client, H["admin"], conn_id, "SELECT CARD_REF, CARD_NO FROM cards ORDER BY CARD_REF LIMIT 5"))[1]
    sup = _rows(q(client, H["support"], conn_id, "SELECT CARD_REF, CARD_NO FROM cards ORDER BY CARD_REF LIMIT 5"))[1]
    ana = _rows(q(client, H["analyst"], conn_id, "SELECT CARD_REF, CARD_NO FROM cards ORDER BY CARD_REF LIMIT 5"))[1]
    for (ref, card), (ref2, masked), (_, hashed) in zip(raw, sup, ana):
        digits = "".join(ch for ch in card if ch.isdigit())
        assert ref == ref2 and masked.startswith(digits[:4]) and masked.endswith(digits[-4:]) and "-XXXX-" in masked
        assert hashed.startswith("hm_k1_")


def test_wildcard_expands_and_column_policy_wins(client, H, conn_id):
    cols, rows, body = _rows(q(client, H["support"], conn_id, "SELECT * FROM cards ORDER BY CARD_REF LIMIT 3"))
    assert cols[:4] == ["CARD_REF", "CUSTOMER_ID", "LINKED_ACCT", "CARD_NO"]
    actions = {d["name"]: d["action"] for d in body["decisions"]}
    assert actions["CARD_NO"] == "PARTIAL" and actions["NAME_ON_CARD"] == "PARTIAL"
    assert actions["CREDIT_LIMIT"] == "ALLOW"  # column policy beats the FINANCIAL_AMOUNT category policy
    assert actions["OUTSTANDING_AMT"] == "GENERALIZE"


def test_aliases_do_not_bypass_masking(client, H, conn_id):
    cols, rows, body = _rows(q(client, H["analyst"], conn_id, "SELECT c.emailid AS harmless_label FROM customers AS c ORDER BY c.customer_id LIMIT 5"))
    assert cols == ["harmless_label"]
    assert all(v is None or v.startswith("hm_k1_") for (v,) in rows)
    assert body["decisions"][0]["source"] == "customers.emailid"


def test_case_insensitive_identifiers(client, H, conn_id):
    _, rows, body = _rows(q(client, H["analyst"], conn_id, "select K.card_no, K.name_on_card from CARDS k order by K.card_ref limit 2"))
    assert rows[0][0].startswith("hm_k1_") and rows[0][1] == "[REDACTED]"
    assert body["decisions"][0]["source"] == "cards.CARD_NO"


def test_three_way_join_masks_every_source(client, H, conn_id):
    sql = ("SELECT c.cust_nm, a.account_no, a.curr_bal, k.CARD_NO FROM customers c "
           "JOIN accounts a ON a.customer_id = c.customer_id JOIN cards k ON k.LINKED_ACCT = a.account_no "
           f"WHERE c.customer_id = '{CUSTOMER}'")
    _, rows, _ = _rows(q(client, H["analyst"], conn_id, sql))
    assert rows
    for name, acct, bal, card in rows:
        assert name == "[REDACTED]" and acct.startswith("hm_k1_") and bal == "[REDACTED]" and card.startswith("hm_k1_")


def test_pseudonyms_consistent_across_tables(client, H, conn_id):
    # Equality joins on pseudonymised keys are allowed; same key + category -> same pseudonym.
    _, rows, _ = _rows(q(client, H["analyst"], conn_id,
                         "SELECT a.account_no, t.account_no FROM transactions t JOIN accounts a ON a.account_no = t.account_no LIMIT 100"))
    assert rows and all(x == y and x.startswith("hm_k1_") for x, y in rows)
    _, cards, _ = _rows(q(client, H["analyst"], conn_id,
                          "SELECT k.LINKED_ACCT, a.account_no FROM cards k JOIN accounts a ON a.account_no = k.LINKED_ACCT LIMIT 50"))
    assert cards and all(x == y for x, y in cards)


@pytest.mark.parametrize("sql,code", [
    ("INSERT INTO customers (customer_id) VALUES ('X')", "not_select"),
    ("UPDATE accounts SET curr_bal = 0", "not_select"),
    ("DELETE FROM transactions", "not_select"),
    ("DROP TABLE cards", "not_select"),
    ("ALTER TABLE customers ADD COLUMN x TEXT", "not_select"),
    ("CREATE TABLE x (a int)", "not_select"),
    ("SELECT 1; DROP TABLE customers", "multiple_statements"),
    ("SELECT cust_nm FROM customers; SELECT emailid FROM customers", "multiple_statements"),
    ("PRAGMA table_info(customers)", "not_select"),
    ("SELECT name FROM sqlite_master", "system_catalog"),
    ("SELECT * FROM information_schema.tables", "system_catalog"),
    ("SELECT cust_nm FROM customers WHERE customer_id IN (SELECT customer_id FROM accounts)", "nested_query"),
    ("WITH x AS (SELECT emailid FROM customers) SELECT * FROM x", "nested_query"),
    ("SELECT emailid FROM customers UNION SELECT cust_nm FROM customers", "not_select"),
    ("SELECT LOWER(emailid) FROM customers", "unsupported_function"),
    ("SELECT emailid || '' FROM customers", "unsupported_expression"),
    ("SELECT CASE WHEN 1=1 THEN emailid END FROM customers", "unsupported_function"),
    ("SELECT SUBSTR(CARD_NO, 1, 16) FROM cards", "unsupported_function"),
    ("SELECT CAST(CARD_NO AS TEXT) FROM cards", "unsupported_function"),
    ("SELECT JSON_EXTRACT(kyc_meta, '$.uid') FROM kyc_records", "unsupported_function"),
    ("SELECT 'x' FROM customers", "computed_expression"),
    ("SELECT customer_id FROM customers c JOIN accounts a ON a.customer_id = c.customer_id", "ambiguous_column"),
    ("SELECT nope FROM customers", "unknown_column"),
    ("SELECT * FROM customers JOIN accounts USING (customer_id)", "join_using"),
    ("SELECT load_extension('x') FROM customers", "unsupported_function"),
])
def test_rejected_statements(client, H, conn_id, sql, code):
    r = q(client, H["admin"], conn_id, sql)
    assert r.status_code in (400, 403), r.text
    body = r.json()
    assert body["error"]["code"] == code, body
    assert body.get("audit_event_id")


def test_sql_injection_in_literal_is_inert(client, H, conn_id):
    r = q(client, H["support"], conn_id, "SELECT ticket_id FROM support_tickets WHERE status = 'OPEN''; DROP TABLE customers; --'")
    assert r.status_code == 200
    assert q(client, H["admin"], conn_id, "SELECT COUNT(*) FROM customers").json()["rows"][0][0] == 5000


@pytest.mark.parametrize("sql", [
    "SELECT CARD_REF FROM cards WHERE CARD_NO LIKE '4111%'",
    "SELECT customer_id FROM customers WHERE emailid = 'someone@inbox.example'",
    "SELECT customer_id FROM customers WHERE mob_no LIKE '%7462'",
    "SELECT account_no FROM accounts ORDER BY curr_bal DESC",
    "SELECT cust_nm, COUNT(*) FROM customers GROUP BY cust_nm",
    "SELECT c.customer_id FROM customers c JOIN accounts a ON a.customer_id = c.customer_id AND a.curr_bal > 100000",
])
def test_inference_through_predicates_is_blocked(client, H, conn_id, sql):
    r = q(client, H["support"], conn_id, sql)
    assert r.status_code == 403 and r.json()["error"]["code"] == "predicate_on_protected", r.text


def test_k_anonymity_aggregates(client, H, conn_id):
    r = q(client, H["analyst"], conn_id, "SELECT MAX(curr_bal) FROM accounts")
    assert r.status_code == 403 and r.json()["error"]["code"] == "aggregate_denied"
    cols, rows, body = _rows(q(client, H["analyst"], conn_id, "SELECT branch_code, AVG(curr_bal) FROM accounts GROUP BY branch_code"))
    assert body["notes"] and "HAVING" in body["executed_sql"].upper()
    counts = dict(q(client, H["admin"], conn_id, "SELECT branch_code, COUNT(*) FROM accounts GROUP BY branch_code").json()["rows"])
    assert rows and all(counts[b] >= 5 for b, _ in rows)
    # support's FINANCIAL_AMOUNT action is GENERALIZE, not AGGREGATE_ONLY -> no averages
    assert q(client, H["support"], conn_id, "SELECT AVG(amount_inr) FROM transactions").json()["error"]["code"] == "aggregate_denied"


def test_unauthorized_tables_by_role(client, H, conn_id):
    assert q(client, H["support"], conn_id, "SELECT app_id FROM loan_applications").status_code == 403
    assert q(client, H["support"], conn_id, "SELECT customer_id FROM international_customers").status_code == 403
    assert q(client, H["analyst"], conn_id, "SELECT ticket_id FROM support_tickets").status_code == 403
    assert q(client, H["analyst"], conn_id, "SELECT kyc_id FROM kyc_records").status_code == 403
    assert q(client, H["analyst"], conn_id, "SELECT app_id FROM loan_applications LIMIT 1").status_code == 200
    assert q(client, H["compliance"], conn_id, "SELECT app_id FROM loan_applications LIMIT 1").status_code == 200


def test_row_cap_on_100k_transactions(client, H, conn_id):
    _, rows, body = _rows(q(client, H["admin"], conn_id, "SELECT txn_id FROM transactions"))
    assert len(rows) == 500 and body["truncated"] is True


def test_break_glass_for_government_ids(client, H, conn_id):
    sql = f"SELECT pan_no, aadhaar_no FROM kyc_records WHERE customer_id = '{CUSTOMER}'"
    plain = q(client, H["admin"], conn_id, sql).json()
    assert plain["rows"][0][0].startswith("XXXX") and plain["break_glass_columns"] == []
    short = q(client, H["admin"], conn_id, sql, justification="because").json()
    assert short["rows"][0][0].startswith("XXXX")
    raw = q(client, H["admin"], conn_id, sql, justification="KYC re-verification case KYC-2026-0412").json()
    assert not raw["rows"][0][0].startswith("XXXX")
    assert sorted(raw["break_glass_columns"]) == ["kyc_records.aadhaar_no", "kyc_records.pan_no"]
    ev = client.get(f"/api/audit/{raw['audit_event_id']}", headers=H["admin"]).json()
    assert ev["details"]["break_glass"] is True and "KYC-2026-0412" in ev["details"]["justification"]
    assert raw["rows"][0][0] not in str(ev)
    for role in ("support", "compliance"):
        r = q(client, H[role], conn_id, sql, justification="I really need the full identifiers").json()
        assert r["rows"][0][0].startswith("XXXX") and r["break_glass_columns"] == []


def test_mislabelled_and_mixed_columns_are_protected(client, H, conn_id):
    # loan_applications.col_7 is undocumented but holds PAN numbers -> detected by value shape
    rows = q(client, H["analyst"], conn_id, "SELECT col_7 FROM loan_applications").json()["rows"]
    assert any(v == "[REDACTED]" for (v,) in rows) and not any(v and v[-5:-1] == "0000" for (v,) in rows)
    # transactions.ref_no mixes internal references with card numbers: cards masked, refs readable
    admin = q(client, H["admin"], conn_id, "SELECT txn_id, ref_no FROM transactions WHERE channel = 'POS' ORDER BY txn_id LIMIT 200").json()["rows"]
    sup = dict(q(client, H["support"], conn_id, "SELECT txn_id, ref_no FROM transactions WHERE channel = 'POS' ORDER BY txn_id LIMIT 200").json()["rows"])
    cards = [(t, r) for t, r in admin if r and r.isdigit() and len(r) == 16]
    refs = [(t, r) for t, r in admin if r and r.startswith("SAFF")]
    assert cards, "expected card numbers inside ref_no"
    assert all("-XXXX-" in sup[t] for t, _ in cards)
    assert all(sup[t] == r for t, r in refs)


def test_free_text_and_narration_span_masking(client, H, conn_id):
    rows = q(client, H["support"], conn_id, "SELECT narration FROM transactions WHERE channel = 'UPI' ORDER BY txn_id LIMIT 300").json()["rows"]
    named = [v for (v,) in rows if v.startswith("UPI/CR/")]
    assert named and all("***" in v.split("/")[3] for v in named)          # payer name segment masked
    assert all("***@" in v for (v,) in rows if "@" in v)                   # UPI handles masked
    meta = q(client, H["support"], conn_id, "SELECT kyc_meta FROM kyc_records WHERE kyc_meta LIKE '%uid%' LIMIT 20")
    assert meta.status_code == 403  # predicate on protected free-text column is blocked for support
    meta = q(client, H["admin"], conn_id, "SELECT kyc_id FROM kyc_records WHERE kyc_meta LIKE '%\"uid\"%' LIMIT 5").json()["rows"]
    kid = meta[0][0]
    sup = q(client, H["support"], conn_id, f"SELECT kyc_meta FROM kyc_records WHERE kyc_id = '{kid}'").json()["rows"][0][0]
    assert '"uid": "[NATIONAL-ID]"' in sup


def test_analyze_does_not_execute(client, H, conn_id):
    before = client.get("/api/audit", params={"action": "query_execute"}, headers=H["admin"]).json()["total"]
    r = client.post("/api/query/analyze", json={"connection_id": conn_id, "sql": "SELECT emailid FROM customers"}, headers=H["support"])
    assert r.json()["permitted"] and r.json()["decisions"][0]["action"] == "PARTIAL"
    after = client.get("/api/audit", params={"action": "query_execute"}, headers=H["admin"]).json()["total"]
    assert after == before


def test_unclassified_table_fails_closed(client, H, conn_id):
    import sqlite3

    from app.config import get_settings
    con = sqlite3.connect(get_settings().targets_dir / "saffron_bank.db")
    con.execute("CREATE TABLE IF NOT EXISTS shadow_copy (emailid TEXT)")
    con.execute("INSERT INTO shadow_copy SELECT emailid FROM customers LIMIT 3")
    con.commit()
    con.close()
    client.put("/api/grants", json={"connection_id": conn_id, "role": "support",
                                   "tables": ["customers", "accounts", "support_tickets", "shadow_copy"]}, headers=H["admin"])
    r = q(client, H["support"], conn_id, "SELECT emailid FROM shadow_copy")
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_classified"
    assert "@" not in r.text


def test_masking_happens_before_response(client, H, conn_id):
    raw = q(client, H["admin"], conn_id, f"SELECT emailid, mob_no FROM customers WHERE customer_id = '{CUSTOMER}'").json()["rows"][0]
    resp = q(client, H["support"], conn_id, f"SELECT emailid, mob_no FROM customers WHERE customer_id = '{CUSTOMER}'")
    assert raw[0] not in resp.text and raw[1] not in resp.text
