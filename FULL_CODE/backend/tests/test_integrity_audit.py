import sqlite3

import pytest
from sqlalchemy import text

from conftest import CUSTOMER, q
from app.config import get_settings


def test_integrity_verification_runs_all_roles(client, H, conn_id):
    r = client.post("/api/integrity/verify", json={"connection_id": conn_id, "tables": ["customers", "accounts"]}, headers=H["admin"])
    assert r.status_code == 200
    run = r.json()
    assert run["match"] is True and run["before_fingerprint"] == run["after_fingerprint"]
    roles = {x["role"] for x in run["queries_executed"]}
    assert roles == {"admin", "support", "analyst", "compliance"}
    assert all(x["ok"] for x in run["queries_executed"])
    assert any(x["masked_columns"] for x in run["queries_executed"] if x["role"] == "analyst")
    assert run["rows_covered"] == 5000 + 8000  # official customers + accounts


def test_fingerprint_detects_changes(client, H, conn_id):
    from app.connectors import get_adapter
    from app.metadb import DbConnection, SessionLocal

    db = SessionLocal()
    adapter = get_adapter(db.get(DbConnection, conn_id))
    fp1, n = adapter.fingerprint("main", "customers")
    assert n == 5000
    con = sqlite3.connect(get_settings().targets_dir / "saffron_bank.db")
    original = con.execute("SELECT segment FROM customers WHERE customer_id = ?", (CUSTOMER,)).fetchone()[0]
    con.execute("UPDATE customers SET segment = 'tampered' WHERE customer_id = ?", (CUSTOMER,))
    con.commit()
    fp2, _ = adapter.fingerprint("main", "customers")
    con.execute("UPDATE customers SET segment = ? WHERE customer_id = ?", (original, CUSTOMER))
    con.commit()
    fp3, _ = adapter.fingerprint("main", "customers")
    con.close()
    db.close()
    assert fp1 != fp2 and fp1 == fp3


def test_queries_never_modify_source(client, H, conn_id):
    path = get_settings().targets_dir / "saffron_bank.db"
    before = path.read_bytes()
    for u in ("admin", "support", "analyst", "compliance"):
        q(client, H[u], conn_id, "SELECT * FROM customers")
        q(client, H[u], conn_id, "SELECT * FROM transactions")
        q(client, H[u], conn_id, "DELETE FROM customers")
        q(client, H[u], conn_id, "UPDATE accounts SET curr_bal = 0")
    assert path.read_bytes() == before


def test_audit_events_persist_without_secrets(client, H, conn_id):
    # generate one of each event type within this module
    client.post("/api/auth/login", json={"username": "admin_anita", "password": "wrong-password"})
    client.get("/api/policies", headers=H["support"])
    client.post("/api/uploads", files={"file": ("n.txt", b"mail me at someone@inbox.example", "text/plain")}, headers=H["admin"])
    cls = client.get("/api/classifications", params={"connection_id": conn_id}, headers=H["admin"]).json()
    client.patch(f"/api/classifications/{cls[0]['id']}", json={"decision": "approve"}, headers=H["admin"])
    raw_email = q(client, H["admin"], conn_id, f"SELECT emailid FROM customers WHERE customer_id = '{CUSTOMER}'").json()["rows"][0][0]
    q(client, H["support"], conn_id, f"SELECT customer_id FROM customers WHERE emailid = '{raw_email}'")
    events = client.get("/api/audit", params={"limit": 500}, headers=H["admin"]).json()
    blob = str(events)
    assert raw_email not in blob  # literals are redacted to '?'
    for secret in ("Admin@2026!", "Support@2026!", H["admin"]["Authorization"][7:]):
        assert secret not in blob
    from app.config import hmac_key
    assert hmac_key().hex() not in blob
    actions = set(events["facets"]["actions"])
    for a in ("login", "login_failed", "pii_scan", "query_execute", "query_denied", "file_upload", "document_scan",
              "integrity_verify", "classification_change", "privilege_violation"):
        assert a in actions, a


def test_audit_filters_and_detail(client, H):
    r = client.get("/api/audit", params={"role": "support", "outcome": "denied"}, headers=H["admin"]).json()
    assert r["total"] >= 1 and all(e["role"] == "support" and e["outcome"] == "denied" for e in r["events"])
    ev = client.get(f"/api/audit/{r['events'][0]['id']}", headers=H["admin"]).json()
    assert ev["correlation_id"] and ev["entry_hash"]


def test_audit_is_append_only_and_chained(client, H):
    from app.metadb import get_engine

    assert client.get("/api/audit/verify-chain", headers=H["admin"]).json()["valid"] is True
    with pytest.raises(Exception):
        with get_engine().begin() as c:
            c.execute(text("UPDATE audit_events SET outcome = 'success'"))
    with pytest.raises(Exception):
        with get_engine().begin() as c:
            c.execute(text("DELETE FROM audit_events"))
    # Tamper with triggers dropped: the hash chain must expose it.
    with get_engine().begin() as c:
        c.execute(text("DROP TRIGGER audit_no_update"))
        c.execute(text("UPDATE audit_events SET reason = 'nothing to see' WHERE seq = 3"))
    v = client.get("/api/audit/verify-chain", headers=H["admin"]).json()
    assert v["valid"] is False and v["broken_at_seq"] == 3


def test_policy_change_is_versioned_and_effective(client, H, conn_id):
    pols = client.get("/api/policies", headers=H["admin"]).json()
    p = next(x for x in pols if x["role"] == "support" and x["category"] == "EMAIL" and not x["table_name"])
    r = client.patch(f"/api/policies/{p['id']}", json={"action": "REDACT"}, headers=H["admin"])
    assert r.json()["version"] == p["version"] + 1
    assert q(client, H["support"], conn_id, f"SELECT emailid FROM customers WHERE customer_id = '{CUSTOMER}'").json()["rows"][0][0] == "[REDACTED]"
    vers = client.get(f"/api/policies/{p['id']}/versions", headers=H["admin"]).json()
    assert [v["snapshot"]["action"] for v in vers[:2]] == ["REDACT", "PARTIAL"]
    client.patch(f"/api/policies/{p['id']}", json={"active": False}, headers=H["admin"])
    # deactivated + no other matching policy for a sensitive column -> fail closed to REDACT
    d = client.post("/api/query/analyze", json={"connection_id": conn_id, "sql": "SELECT emailid FROM customers"}, headers=H["support"]).json()
    assert d["decisions"][0]["action"] == "REDACT" and d["decisions"][0]["policy_name"] == "fail-closed default"
    client.patch(f"/api/policies/{p['id']}", json={"active": True, "action": "PARTIAL"}, headers=H["admin"])


def test_policy_simulation_does_not_change_active_policies(client, H, conn_id):
    r = client.post("/api/policies/simulate", json={"connection_id": conn_id, "proposed": {
        "name": "analyst sees emails partially", "role": "analyst", "category": "EMAIL", "action": "PARTIAL", "priority": 50}},
        headers=H["admin"]).json()
    assert r["saved"] is False and any(c["column"] == "emailid" and c["proposed"] == "PARTIAL" for c in r["changes"])
    v = q(client, H["analyst"], conn_id, f"SELECT emailid FROM customers WHERE customer_id = '{CUSTOMER}'").json()["rows"][0][0]
    assert v.startswith("hm_k1_")


def test_policy_preview_and_validation(client, H):
    r = client.post("/api/policies/preview", json={"action": "PARTIAL", "category": "CREDIT_CARD"}, headers=H["admin"]).json()
    assert r["synthetic"] and r["results"][0]["output"] == "4111-XXXX-XXXX-1111"
    bad = client.post("/api/policies", json={"name": "bad", "role": "support", "action": "SHOW_EVERYTHING", "category": "EMAIL"}, headers=H["admin"])
    assert bad.status_code == 422
    unscoped = client.post("/api/policies", json={"name": "global allow", "role": "support", "action": "ALLOW"}, headers=H["admin"])
    assert unscoped.status_code == 422


def test_overview_uses_real_counts(client, H):
    o = client.get("/api/overview", headers=H["admin"]).json()
    assert o["queries_evaluated"] > 0 and o["queries_blocked"] > 0 and o["tables_scanned"] == 9
    assert o["columns_classified"] == 120 and o["sensitive_columns"] >= 35
    assert o["risk"]["formula"] and 0 <= o["risk"]["score"] <= 100
