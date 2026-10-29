"""MySQL integration tests on the official Saffron Bank data. Skipped unless configured:

  SENTINEL_TEST_MYSQL_PASSWORD  password of the least-privilege `sentinel_app` account
                                (created by `python -m app.cli import-mysql`, stored in data/secrets/mysql_app.pw)
  SENTINEL_TEST_MYSQL_HOST / SENTINEL_TEST_MYSQL_PORT   (default localhost / 3306)
"""
import os
import secrets

import pytest

from conftest import CUSTOMER, q

PW = os.environ.get("SENTINEL_TEST_MYSQL_PASSWORD")
pytestmark = pytest.mark.skipif(not PW, reason="SENTINEL_TEST_MYSQL_PASSWORD not set - MySQL not configured")


@pytest.fixture(scope="module")
def my_id(client, H):
    r = client.post("/api/databases", json={
        "name": "MySQL integration", "kind": "mysql", "host": os.environ.get("SENTINEL_TEST_MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("SENTINEL_TEST_MYSQL_PORT", "3306")), "database": "saffron_bank",
        "username": "sentinel_app", "password": PW, "allowed_schemas": ["saffron_bank", "saffron_imports"],
        "import_database": "saffron_imports"}, headers=H["admin"])
    assert r.status_code == 201, r.text
    assert PW not in r.text
    cid = r.json()["id"]
    assert client.post(f"/api/databases/{cid}/test", headers=H["admin"]).json()["status"] == "healthy"
    s = client.post(f"/api/databases/{cid}/scan", json={"sample_size": 300}, headers=H["admin"]).json()
    assert s["status"] == "completed" and s["tables_scanned"] == 9, s
    from app.seed import GRANTS
    for role, tables in GRANTS.items():
        client.put("/api/grants", json={"connection_id": cid, "role": role, "tables": tables}, headers=H["admin"])
    return cid


def test_mysql_nine_tables_and_official_counts(client, H, my_id):
    from app.saffron import EXPECTED_COUNTS
    for t, n in EXPECTED_COUNTS.items():
        assert q(client, H["admin"], my_id, f"SELECT COUNT(*) FROM {t}").json()["rows"][0][0] == n, t


def test_mysql_dynamic_schema_and_classification(client, H, my_id):
    schema = client.get(f"/api/databases/{my_id}/schema", headers=H["admin"]).json()
    tables = {t["table"]: [c["name"] for c in t["columns"]] for t in schema["tables"]}
    assert set(tables) >= {"branches", "customers", "kyc_records", "international_customers", "accounts", "cards",
                           "transactions", "support_tickets", "loan_applications"}
    assert "CARD_NO" in tables["cards"] and "mob_no" in tables["customers"]
    cls = {(c["table"], c["column"]): c["category"] for c in
           client.get("/api/classifications", params={"connection_id": my_id}, headers=H["admin"]).json()}
    assert cls[("customers", "mob_no")] == "PHONE" and cls[("cards", "CARD_NO")] == "CREDIT_CARD"
    assert cls[("kyc_records", "aadhaar_no")] == "NATIONAL_ID" and cls[("loan_applications", "col_7")] == "NATIONAL_ID"


def test_mysql_same_masked_output_as_sqlite(client, H, my_id, conn_id):
    sql = ("SELECT c.cust_nm, c.emailid, c.mob_no, c.dob_dt, a.account_no, a.curr_bal, k.CARD_NO FROM customers c "
           "JOIN accounts a ON a.customer_id = c.customer_id JOIN cards k ON k.LINKED_ACCT = a.account_no "
           f"WHERE c.customer_id = '{CUSTOMER}' ORDER BY k.CARD_REF")
    for role in ("admin", "support", "analyst", "compliance"):
        my, lite = q(client, H[role], my_id, sql), q(client, H[role], conn_id, sql)
        assert my.status_code == 200, my.text
        assert my.json()["rows"] == lite.json()["rows"], role


def test_mysql_rejections(client, H, my_id):
    for sql, code in [("DELETE FROM customers", "not_select"), ("SELECT * FROM mysql.user", "system_catalog"),
                      ("SELECT * FROM information_schema.tables", "system_catalog"),
                      ("SELECT SLEEP(10) FROM customers", "unsupported_function"),
                      ("SELECT LOAD_FILE('/etc/passwd') FROM customers", "unsupported_function"),
                      ("SELECT cust_nm FROM customers INTO OUTFILE '/tmp/x'", "unsupported_clause")]:
        r = q(client, H["admin"], my_id, sql).json()
        assert r["error"]["code"] in (code, "parse_error"), (sql, r)


def test_mysql_read_only_second_line_of_defence(client, H, my_id):
    from app.connectors import ConnectorError, get_adapter
    from app.metadb import DbConnection, SessionLocal

    db = SessionLocal()
    with pytest.raises(ConnectorError):
        get_adapter(db.get(DbConnection, my_id)).execute_readonly("DELETE FROM transactions", 2000, 10)
    db.close()
    assert q(client, H["admin"], my_id, "SELECT COUNT(*) FROM transactions").json()["rows"][0][0] == 100000


def test_mysql_integrity(client, H, my_id):
    run = client.post("/api/integrity/verify", json={"connection_id": my_id, "tables": ["customers", "cards"]}, headers=H["admin"]).json()
    assert run["match"] is True and run["rows_covered"] == 11000


def test_mysql_csv_import_into_separate_schema(client, H, my_id):
    r = client.post("/api/uploads", files={"file": ("my.csv", b"cust_nm,emailid\nAsha Verma,asha.my@inbox.example\n", "text/csv")}, headers=H["admin"])
    up = r.json()
    table = f"mysql_contacts_{secrets.token_hex(3)}"
    r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": my_id, "table_name": table}, headers=H["admin"])
    assert r.status_code == 200, r.text
    rows = q(client, H["support"], my_id, f"SELECT cust_nm, emailid FROM saffron_imports.imp_{table}").json()["rows"]
    assert rows == [["A*** V****", "a***@inbox.example"]]
