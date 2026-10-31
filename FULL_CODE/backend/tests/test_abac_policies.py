"""Feature 2: attribute-based (purpose / ticket / time-window) masking on top of role policies."""
from datetime import datetime, timezone

import pytest

from conftest import CUSTOMER, q
from app.metadb import Classification, Policy, SessionLocal
from app.policy import PolicyResolver
from app.security import AccessContext

FRAUD = {"X-DreamGuard-Purpose": "FRAUD_INVESTIGATION", "X-DreamGuard-Ticket-Id": "INC-8821"}
CONTACT_SQL = f"SELECT mob_no, emailid FROM customers WHERE customer_id = '{CUSTOMER}'"


def resolver(policies, ctx=None, sensitivity="PII_HIGH"):
    db = SessionLocal()
    r = PolicyResolver(db, "no-such-role", "conn", ctx)
    db.close()
    r.policies = policies
    r.classes = {("main", "t", "c"): Classification(schema_name="main", table_name="t", column_name="c", category="PHONE", sensitivity=sensitivity)}
    return r


def pol(pid, action, priority=0, **abac):
    return Policy(id=pid, name=f"p{pid}", role="support", category="PHONE", action=action, priority=priority, active=True, **abac)


def at(hh, mm=0, **kw):
    return AccessContext(at=datetime(2026, 10, 31, hh, mm, tzinfo=timezone.utc), **kw)


BASE = pol(1, "PARTIAL")
GRANT = pol(2, "ALLOW", 50, allowed_purposes=["FRAUD_INVESTIGATION"], require_ticket_id=True)


# ---- resolver semantics -------------------------------------------------------------------

def test_conditional_grant_applies_only_when_every_condition_holds(client):
    d = resolver([BASE, GRANT], AccessContext(purpose="FRAUD_INVESTIGATION", ticket_id="INC-1")).decide("main", "t", "c")
    assert (d.action, d.policy_id, d.abac_granted) == ("ALLOW", 2, True)
    for ctx in (AccessContext(), AccessContext(purpose="FRAUD_INVESTIGATION"), AccessContext(ticket_id="INC-1"),
                AccessContext(purpose="CUSTOMER_SUPPORT", ticket_id="INC-1")):
        d = resolver([BASE, GRANT], ctx).decide("main", "t", "c")
        assert (d.action, d.policy_id, d.abac_granted) == ("PARTIAL", 1, False), ctx
        assert "conditional policy #2 not applied" in d.reason


def test_unmet_condition_never_loosens_a_restriction(client):
    # A conditional policy stricter than the fallback keeps holding the column when unmet.
    strict = pol(3, "REDACT", 50, allowed_purposes=["SECURITY_AUDIT"])
    d = resolver([pol(1, "ALLOW"), strict]).decide("main", "t", "c")
    assert (d.action, d.policy_id) == ("REDACT", 3) and "held at REDACT" in d.reason
    # No unconditional fallback on a sensitive column -> fail-closed default, not the unmet grant.
    d = resolver([GRANT]).decide("main", "t", "c")
    assert (d.action, d.policy_name) == ("REDACT", "fail-closed default")
    # Worst-case evaluation (used by attestations) treats every grant as reachable.
    db = SessionLocal()
    worst = PolicyResolver(db, "no-such-role", "conn", assume_conditions_met=True)
    db.close()
    worst.policies, worst.classes = [BASE, GRANT], resolver([]).classes
    assert worst.decide("main", "t", "c").action == "ALLOW"


@pytest.mark.parametrize("window,hour,granted", [
    (("09:00", "17:00"), 10, True), (("09:00", "17:00"), 17, False), (("09:00", "17:00"), 8, False),
    (("22:00", "06:00"), 23, True), (("22:00", "06:00"), 5, True), (("22:00", "06:00"), 12, False),
])
def test_utc_time_windows_including_midnight_wrap(client, window, hour, granted):
    timed = pol(4, "ALLOW", 50, time_window_start=window[0], time_window_end=window[1])
    d = resolver([BASE, timed], at(hour)).decide("main", "t", "c")
    assert (d.action == "ALLOW") is granted


# ---- end to end through the query pipeline (seeded purpose-bound support policies) ---------

def test_purpose_and_ticket_unmask_permitted_columns_in_real_time(client, H, conn_id):
    raw = q(client, H["admin"], conn_id, CONTACT_SQL).json()["rows"][0]
    base = q(client, H["support"], conn_id, CONTACT_SQL).json()
    assert base["rows"][0][0] != raw[0] and base["rows"][0][1] != raw[1]
    assert base["access_context"]["abac_granted_columns"] == []

    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL}, headers=H["support"] | FRAUD).json()
    assert r["rows"][0] == raw
    assert r["access_context"] == {"purpose": "FRAUD_INVESTIGATION", "ticket_id": "INC-8821", "rejected_attributes": [],
                                   "abac_granted_columns": ["customers.mob_no", "customers.emailid"]}
    assert all(d["abac_granted"] for d in r["decisions"])

    # Inbound support may call back (phone) but not e-mail; no ticket -> baseline for everything.
    cs = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL},
                     headers=H["support"] | {"X-DreamGuard-Purpose": "customer_support", "X-DreamGuard-Ticket-Id": "inc-8821"}).json()
    assert cs["rows"][0][0] == raw[0] and cs["rows"][0][1] == base["rows"][0][1]
    no_ticket = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL},
                            headers=H["support"] | {"X-DreamGuard-Purpose": "FRAUD_INVESTIGATION"}).json()
    assert no_ticket["rows"] == base["rows"]


def test_invalid_attributes_are_ignored_and_flagged(client, H, conn_id):
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL},
                    headers=H["support"] | {"X-DreamGuard-Purpose": "GOD_MODE", "X-DreamGuard-Ticket-Id": "1; DROP TABLE x"}).json()
    base = q(client, H["support"], conn_id, CONTACT_SQL).json()
    assert r["rows"] == base["rows"]
    assert r["access_context"]["purpose"] is None and r["access_context"]["rejected_attributes"] == ["purpose", "ticket_id"]


def test_purpose_and_ticket_are_hash_chained_in_the_audit_log(client, H, conn_id):
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL}, headers=H["support"] | FRAUD).json()
    ev = client.get(f"/api/audit/{r['audit_event_id']}", headers=H["admin"]).json()
    ctx = ev["details"]["access_context"]
    assert ctx["purpose"] == "FRAUD_INVESTIGATION" and ctx["ticket_id"] == "INC-8821" and ctx["ip_address"]
    assert ev["details"]["abac_granted_columns"] == ["customers.mob_no", "customers.emailid"]
    # Denials carry the attestation too.
    client.post("/api/query/execute", json={"connection_id": conn_id, "sql": "SELECT app_id FROM loan_applications"}, headers=H["support"] | FRAUD)
    denied = client.get("/api/audit", params={"action": "query_denied", "limit": 1}, headers=H["admin"]).json()["events"][0]
    assert denied["details"]["access_context"]["ticket_id"] == "INC-8821"
    assert client.get("/api/audit/verify-chain", headers=H["admin"]).json()["valid"] is True


def test_card_numbers_stay_masked_for_support_whatever_the_purpose(client, H, conn_id):
    sql = f"SELECT k.CARD_NO FROM cards k WHERE k.CUSTOMER_ID = '{CUSTOMER}'"
    for purpose in ("CUSTOMER_SUPPORT", "FRAUD_INVESTIGATION", "DISPUTE_RESOLUTION", "SECURITY_AUDIT", "ANALYTICS_REPORTING"):
        r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": sql},
                        headers=H["support"] | {"X-DreamGuard-Purpose": purpose, "X-DreamGuard-Ticket-Id": "INC-1"}).json()
        assert r["rows"] and all("-XXXX-" in row[0] for row in r["rows"]), purpose


def test_other_roles_are_unaffected_by_purpose_headers(client, H, conn_id):
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CONTACT_SQL}, headers=H["analyst"] | FRAUD).json()
    assert r["rows"][0][0] == "[REDACTED]" and r["rows"][0][1].startswith("hm_k1_")
    perms = client.get("/api/query/permissions", params={"connection_id": conn_id}, headers=H["support"] | FRAUD).json()
    cust = next(t for t in perms["tables"] if t["table"] == "customers")
    assert next(c for c in cust["columns"] if c["column"] == "mob_no")["action"] == "ALLOW"


# ---- policy administration ---------------------------------------------------------------

def test_abac_policy_crud_validation_and_versioning(client, H):
    base = {"name": "analyst emails for reporting", "role": "analyst", "category": "EMAIL", "action": "PARTIAL", "priority": 50}
    for bad in ({"allowed_purposes": ["WHATEVER"]}, {"time_window_start": "25:00", "time_window_end": "06:00"},
                {"time_window_start": "09:00"}, {"time_window_start": "09:00", "time_window_end": "09:00"}):
        assert client.post("/api/policies", json=base | bad, headers=H["admin"]).status_code == 422, bad
    r = client.post("/api/policies", json=base | {"allowed_purposes": ["ANALYTICS_REPORTING"], "require_ticket_id": True,
                                                  "time_window_start": "03:30", "time_window_end": "12:30"}, headers=H["admin"])
    assert r.status_code == 201
    p = r.json()
    assert p["conditional"] and p["allowed_purposes"] == ["ANALYTICS_REPORTING"] and p["time_window_end"] == "12:30"
    r = client.patch(f"/api/policies/{p['id']}", json={"allowed_purposes": [], "time_window_start": "", "time_window_end": ""}, headers=H["admin"])
    assert r.json()["allowed_purposes"] == [] and r.json()["time_window_start"] is None and r.json()["require_ticket_id"] is True
    assert client.patch(f"/api/policies/{p['id']}", json={"time_window_start": "10:00"}, headers=H["admin"]).status_code == 400
    vers = client.get(f"/api/policies/{p['id']}/versions", headers=H["admin"]).json()
    assert vers[0]["snapshot"]["allowed_purposes"] is None and vers[1]["snapshot"]["allowed_purposes"] == ["ANALYTICS_REPORTING"]
    assert client.patch(f"/api/policies/{p['id']}", json={"active": False}, headers=H["admin"]).status_code == 200
    assert "FRAUD_INVESTIGATION" in client.get("/api/policies/actions", headers=H["admin"]).json()["purposes"]


def test_simulation_can_evaluate_under_a_purpose(client, H, conn_id):
    proposed = {"name": "analyst emails for reporting", "role": "analyst", "category": "EMAIL", "action": "PARTIAL", "priority": 60,
                "allowed_purposes": ["ANALYTICS_REPORTING"], "require_ticket_id": True}
    plain = client.post("/api/policies/simulate", json={"connection_id": conn_id, "proposed": proposed}, headers=H["admin"]).json()
    assert not any(c["column"] == "emailid" for c in plain["changes"])
    bound = client.post("/api/policies/simulate", json={"connection_id": conn_id, "proposed": proposed,
                        "context": {"purpose": "ANALYTICS_REPORTING", "ticket_id": "RPT-42"}}, headers=H["admin"]).json()
    assert any(c["column"] == "emailid" and c["proposed"] == "PARTIAL" for c in bound["changes"])
    assert bound["context"] == {"purpose": "ANALYTICS_REPORTING", "ticket_id": "RPT-42"} and bound["saved"] is False
