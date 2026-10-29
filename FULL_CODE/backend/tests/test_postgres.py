"""PostgreSQL integration tests on the official Saffron Bank data. Skipped unless configured:

  SENTINEL_TEST_PG_HOST, SENTINEL_TEST_PG_PORT, SENTINEL_TEST_PG_DB, SENTINEL_TEST_PG_USER, SENTINEL_TEST_PG_PASSWORD

The database must hold the official dataset (python -m app.cli import-postgres) and the user should be a
least-privilege role (scripts/postgres_setup.sql)."""
import os

import pytest

from conftest import CUSTOMER, q

PG = {k: os.environ.get(f"SENTINEL_TEST_PG_{k.upper()}") for k in ("host", "port", "db", "user", "password")}
pytestmark = pytest.mark.skipif(not PG["host"], reason="SENTINEL_TEST_PG_HOST not set - PostgreSQL not available")


@pytest.fixture(scope="module")
def pg_id(client, H):
    r = client.post("/api/databases", json={
        "name": "PG integration", "kind": "postgresql", "host": PG["host"], "port": int(PG["port"] or 5432),
        "database": PG["db"], "username": PG["user"], "password": PG["password"]}, headers=H["admin"])
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert PG["password"] not in r.text
    assert client.post(f"/api/databases/{cid}/test", headers=H["admin"]).json()["status"] == "healthy"
    s = client.post(f"/api/databases/{cid}/scan", json={"sample_size": 300}, headers=H["admin"]).json()
    assert s["status"] == "completed" and s["tables_scanned"] == 9
    from app.seed import GRANTS
    for role, tables in GRANTS.items():
        client.put("/api/grants", json={"connection_id": cid, "role": role, "tables": tables}, headers=H["admin"])
    return cid


def test_pg_counts(client, H, pg_id):
    from app.saffron import EXPECTED_COUNTS
    for t, n in EXPECTED_COUNTS.items():
        assert q(client, H["admin"], pg_id, f"SELECT COUNT(*) FROM {t}").json()["rows"][0][0] == n, t


def test_pg_classification_matches_schema(client, H, pg_id):
    cls = {(c["table"], c["column"]): c["category"] for c in
           client.get("/api/classifications", params={"connection_id": pg_id}, headers=H["admin"]).json()}
    assert cls[("customers", "mob_no")] == "PHONE" and cls[("cards", "CARD_NO")] == "CREDIT_CARD"
    assert cls[("kyc_records", "aadhaar_no")] == "NATIONAL_ID" and cls[("loan_applications", "col_7")] == "NATIONAL_ID"


def test_pg_same_masked_output_as_sqlite(client, H, pg_id, conn_id):
    sql = ("SELECT c.cust_nm, c.emailid, c.mob_no, a.account_no, k.CARD_NO FROM customers c "
           "JOIN accounts a ON a.customer_id = c.customer_id JOIN cards k ON k.LINKED_ACCT = a.account_no "
           f"WHERE c.customer_id = '{CUSTOMER}' ORDER BY k.CARD_REF")
    for role in ("admin", "support", "analyst", "compliance"):
        pg, lite = q(client, H[role], pg_id, sql), q(client, H[role], conn_id, sql)
        assert pg.status_code == 200, pg.text
        assert pg.json()["rows"] == lite.json()["rows"], role


def test_pg_rejections(client, H, pg_id):
    for sql, code in [("DELETE FROM customers", "not_select"), ("SELECT * FROM pg_catalog.pg_user", "system_catalog"),
                      ("SELECT usename FROM pg_user", "system_catalog"), ("SELECT pg_read_file('x') FROM customers", "unsupported_function")]:
        assert q(client, H["admin"], pg_id, sql).json()["error"]["code"] == code, sql


def test_pg_read_only_second_line_of_defence(client, H, pg_id):
    from app.connectors import ConnectorError, get_adapter
    from app.metadb import DbConnection, SessionLocal

    db = SessionLocal()
    with pytest.raises(ConnectorError):
        get_adapter(db.get(DbConnection, pg_id)).execute_readonly("DELETE FROM transactions", 2000, 10)
    db.close()
    assert q(client, H["admin"], pg_id, "SELECT COUNT(*) FROM transactions").json()["rows"][0][0] == 100000


def test_pg_integrity(client, H, pg_id):
    run = client.post("/api/integrity/verify", json={"connection_id": pg_id, "tables": ["customers", "cards"]}, headers=H["admin"]).json()
    assert run["match"] is True and run["rows_covered"] == 11000
