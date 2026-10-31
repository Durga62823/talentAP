"""Feature 3: signed regulatory dossiers (DPDP, RBI CSF, PCI-DSS v4.0 Req 3) from the audit ledger."""
import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization

from conftest import CUSTOMER, q
from app import compliance_reporter

FRAUD = {"X-DreamGuard-Purpose": "FRAUD_INVESTIGATION", "X-DreamGuard-Ticket-Id": "INC-8821"}
CARD_SQL = f"SELECT k.CARD_REF, k.CARD_NO FROM cards k WHERE k.CUSTOMER_ID = '{CUSTOMER}'"


def gen(client, h, framework, fmt="json"):
    return client.post("/api/compliance/reports/generate", json={"framework": framework, "format": fmt}, headers=h)


def section(dossier, sid):
    return compliance_reporter.section_data(dossier, sid)


def test_reports_require_audit_permission(client, H):
    for role in ("support", "analyst"):
        assert client.get("/api/compliance/reports/summary", headers=H[role]).status_code == 403
        assert gen(client, H[role], "DPDP").status_code == 403
    assert client.get("/api/compliance/reports/summary").status_code == 401
    assert client.get("/api/compliance/reports/summary", headers=H["compliance"]).status_code == 200


def test_summary_reflects_live_evidence(client, H, conn_id):
    client.post("/api/query/execute", json={"connection_id": conn_id, "sql": f"SELECT mob_no FROM customers WHERE customer_id = '{CUSTOMER}'"},
                headers=H["support"] | FRAUD)
    s = client.get("/api/compliance/reports/summary", headers=H["compliance"]).json()
    assert s["ledger"]["chain_valid"] is True and s["ledger"]["events"] > 0
    assert s["purpose_distribution"]["FRAUD_INVESTIGATION"] >= 1 and s["purpose_bound_elevations"] >= 1
    assert s["pci"]["pan_columns"] >= 1 and s["pci"]["non_privileged_cleartext_egress"] == 0
    assert {f["id"]: f["status"] for f in s["frameworks"]} == {"DPDP": "PASS", "RBI": "PASS", "PCI_DSS": "PASS"}


def test_dossier_is_signed_verifiable_and_anchored_in_the_ledger(client, H):
    r = gen(client, H["compliance"], "DPDP")
    assert r.status_code == 200
    dossier, cert = r.json()["dossier"], r.json()["certificate"]
    digest = hashlib.sha256(compliance_reporter.canonical(dossier)).hexdigest()
    assert cert["dossier_sha256"] == digest == r.headers["x-dossier-sha256"]
    # Independent offline check with only the published public key.
    pub = serialization.load_pem_public_key(client.get("/api/compliance/reports/public-key", headers=H["compliance"]).json()["public_key_pem"].encode())
    pub.verify(base64.b64decode(cert["signature"]), digest.encode())  # raises if invalid
    ev = client.get(f"/api/audit/{cert['audit_event_id']}", headers=H["admin"]).json()
    assert ev["action"] == "compliance_report_generate" and ev["details"]["dossier_sha256"] == digest
    assert ev["entry_hash"] == cert["audit_entry_hash"]

    ok = client.post("/api/compliance/reports/verify", json={"dossier": dossier, "certificate": cert}, headers=H["compliance"]).json()
    assert ok == {"valid": True, "sha256_matches": True, "signature_valid": True, "anchored_in_audit_ledger": True, "recomputed_sha256": digest}
    tampered = json.loads(json.dumps(dossier))
    tampered["status"] = "PASS" if dossier["status"] != "PASS" else "FORGED"
    bad = client.post("/api/compliance/reports/verify", json={"dossier": tampered, "certificate": cert}, headers=H["compliance"]).json()
    assert bad["valid"] is False and bad["sha256_matches"] is False
    assert client.get("/api/audit/verify-chain", headers=H["admin"]).json()["valid"] is True


def test_dpdp_pack_covers_purpose_exceptions_and_zero_mutation(client, H, conn_id):
    client.post("/api/integrity/verify", json={"connection_id": conn_id, "tables": ["branches"]}, headers=H["admin"])
    q(client, H["support"], conn_id, "UPDATE accounts SET curr_bal = 0")
    q(client, H["admin"], conn_id, f"SELECT pan_no FROM kyc_records WHERE customer_id = '{CUSTOMER}'",
      justification="Regulator request REG-2026-17 for KYC verification")
    d = gen(client, H["admin"], "DPDP").json()["dossier"]
    assert [s["id"] for s in d["sections"]] == ["data_principal_access", "purpose_distribution", "exceptional_access", "zero_mutation"]
    assert section(d, "purpose_distribution")["queries_by_purpose"]["FRAUD_INVESTIGATION"] >= 1
    bg = section(d, "exceptional_access")
    assert bg["break_glass_total"] >= 1 and "REG-2026-17" in bg["break_glass_events"][-1]["justification"]
    zm = section(d, "zero_mutation")
    assert zm["integrity_runs"]["all_match"] is True and zm["write_statements_blocked"] >= 1
    assert "customers" in section(d, "data_principal_access")["reads_by_table"]


def test_rbi_annexure_lists_admin_actions_failures_and_chain_certificate(client, H):
    client.post("/api/auth/login", json={"username": "admin_anita", "password": "definitely-wrong"})
    client.get("/api/users", headers=H["analyst"])  # privilege violation
    pols = client.get("/api/policies", headers=H["admin"]).json()
    pid = next(p["id"] for p in pols if p["role"] == "analyst" and p["category"] == "PHONE")
    client.patch(f"/api/policies/{pid}", json={"description": "reviewed for RBI annexure"}, headers=H["admin"])
    d = gen(client, H["compliance"], "RBI").json()["dossier"]
    assert section(d, "admin_actions")["counts"]["policy_change"] >= 1
    failed = section(d, "failed_access")["counts"]
    assert failed["login_failed"] >= 1 and failed["privilege_violation"] >= 1
    chain = section(d, "chain_certificate")
    assert chain["chain_valid"] is True and len(chain["head_entry_hash"]) == 64 and chain["events_recomputed"] == chain["events"]


def test_pdf_and_csv_renderings(client, H):
    r = gen(client, H["compliance"], "RBI", "pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    body = r.content
    assert body.startswith(b"%PDF-1.4") and body.rstrip().endswith(b"%%EOF") and len(r.headers["x-dossier-sha256"]) == 64
    xref_at = int(body.rsplit(b"startxref", 1)[1].split()[0])
    assert body[xref_at:xref_at + 4] == b"xref"
    assert r.headers["x-dossier-sha256"][:16].encode() in body and "attachment" in r.headers["content-disposition"]

    r = gen(client, H["compliance"], "PCI_DSS", "csv")
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert text.splitlines()[0] == "section,field,value" and f"certificate,dossier_sha256,{r.headers['x-dossier-sha256']}" in text
    events = client.get("/api/audit", params={"action": "compliance_report_generate"}, headers=H["admin"]).json()["events"]
    assert {e["details"]["format"] for e in events} >= {"json", "pdf", "csv"}


def test_dossiers_never_contain_protected_values(client, H, conn_id):
    raw_email, raw_card = q(client, H["admin"], conn_id,
                            f"SELECT c.emailid, k.CARD_NO FROM customers c JOIN cards k ON k.CUSTOMER_ID = c.customer_id "
                            f"WHERE c.customer_id = '{CUSTOMER}'").json()["rows"][0]
    for fw in ("DPDP", "RBI", "PCI_DSS"):
        blob = gen(client, H["admin"], fw).text
        assert raw_email not in blob and raw_card not in blob and "".join(ch for ch in raw_card if ch.isdigit()) not in blob


def test_pci_attestation_masked_egress_by_role(client, H, conn_id):
    q(client, H["support"], conn_id, CARD_SQL)
    q(client, H["analyst"], conn_id, "SELECT COUNT(CARD_NO) AS n FROM cards")  # counting PANs is not egress of a PAN
    d = gen(client, H["compliance"], "PCI_DSS").json()["dossier"]
    assert d["status"] == "PASS" and d["findings"] == []
    card = next(c for c in section(d, "pan_policy")["pan_columns"] if c["column"] == "cards.CARD_NO")
    assert card["roles"]["support"]["egress_example"] == "4111-XXXX-XXXX-1111"
    assert card["roles"]["analyst"]["worst_case_action"] == "HASH" and card["roles"]["analyst"]["raw_reachable"] is False
    assert card["roles"]["admin"]["raw_reachable"] is True  # documented business need, not a finding
    observed = section(d, "pan_egress_observed")
    assert observed["by_role"]["support"]["masked"] >= 1 and observed["non_privileged_cleartext_instances"] == 0


def test_pci_worst_case_catches_purpose_gated_pan_exposure(client, H, conn_id):
    """Runs last: it leaves a (deliberate) cleartext egress in the immutable ledger."""
    r = client.post("/api/policies", json={"name": "fraud desk sees full card", "role": "support", "category": "CREDIT_CARD",
                                           "action": "ALLOW", "priority": 90, "allowed_purposes": ["FRAUD_INVESTIGATION"],
                                           "require_ticket_id": True}, headers=H["admin"])
    pid = r.json()["id"]
    # Without the purpose nothing leaks yet, but the grant is reachable: the attestation must fail.
    d = gen(client, H["compliance"], "PCI_DSS").json()["dossier"]
    assert d["status"] == "ATTENTION_REQUIRED"
    assert any(x["role"] == "support" and x["policy_id"] == pid for x in section(d, "pan_policy")["non_privileged_raw_reachable"])

    client.post("/api/query/execute", json={"connection_id": conn_id, "sql": CARD_SQL}, headers=H["support"] | FRAUD)
    client.patch(f"/api/policies/{pid}", json={"active": False}, headers=H["admin"])
    d = gen(client, H["compliance"], "PCI_DSS").json()["dossier"]
    assert section(d, "pan_policy")["non_privileged_raw_reachable"] == []
    observed = section(d, "pan_egress_observed")
    assert observed["non_privileged_cleartext_instances"] >= 1 and observed["instances"][-1]["source"] == "cards.CARD_NO"
    assert d["status"] == "ATTENTION_REQUIRED"  # the ledger keeps proving the exposure happened
