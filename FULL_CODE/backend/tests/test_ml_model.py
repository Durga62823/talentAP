"""Locally trained PII classifier: artifact, predictions, explanations, scan integration, RBAC."""
import pytest

from app.ml import featurize
from app.ml import model as ml_model
from app.ml.model import MlVerdict
from app.ml.synth import card, pan
from app.scanner import SENSITIVE_LABELS, classify_column

RANK = {"PUBLIC": 0, "INTERNAL": 1, "PII_MEDIUM": 3, "FINANCIAL_CONFIDENTIAL": 3, "PII_HIGH": 4}

needs_model = pytest.mark.skipif(ml_model.get_model() is None, reason="ML artifact not trained (python -m app.ml.train)")


def predict(table, column, dtype, values):
    rule = classify_column(column, dtype, values, table=table)
    return ml_model.get_model().predict([featurize.build(table, column, dtype, True, False, values, rule)])[0]


def scan(client, H, conn_id, **flags):
    r = client.post(f"/api/databases/{conn_id}/scan", json={"sample_size": 100, **flags}, headers={**H["admin"], "X-Sentinel-CSRF": "1"})
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    return r.json()


def classes(client, H, conn_id):
    return {f"{c['table']}.{c['column']}": c for c in client.get(f"/api/classifications?connection_id={conn_id}", headers=H["admin"]).json()}


# ---------------------------------------------------------------- the model itself ----------

@needs_model
def test_artifact_matches_runtime_and_has_a_model_card():
    import sklearn

    m = ml_model.get_model()
    assert m.version.startswith("pii-ml-") and "CREDIT_CARD" in m.classes and "NONE" in m.classes
    card_ = ml_model.model_card()
    assert card_["sklearn_version"] == sklearn.__version__
    assert {"synthetic_test", "saffron_evaluation", "feature_importance", "caveats"} <= card_.keys()


@needs_model
def test_reads_values_when_the_column_name_says_nothing():
    import random

    r = random.Random(3)
    cards = predict("misc", "col_9", "VARCHAR(20)", [card(r) for _ in range(80)])
    pans = predict("misc", "field_2", "VARCHAR(10)", [pan(r) for _ in range(80)])
    assert cards.category == "CREDIT_CARD" and cards.confidence >= 0.8
    assert pans.category == "NATIONAL_ID"
    assert any("Luhn" in x["evidence"] for x in cards.reasons)  # the explanation names the deciding signal


@needs_model
def test_reads_names_when_values_are_ambiguous():
    # Alphanumeric record IDs look the same whether they identify a customer or a ticket.
    import random

    from app.ml.synth import generic_id

    r = random.Random(5)
    ids = [generic_id(r) for _ in range(80)]
    assert predict("accounts", "cust_ref_no", "VARCHAR(16)", ids).category == "CUSTOMER_ID"
    assert predict("support_tickets", "ticket_ref", "VARCHAR(16)", ids).category == "NONE"


@needs_model
def test_predictions_are_deterministic():
    vals = ["Ravi Kumar", "Anita Rao", "Meera Iyer", "Farhan Qureshi"] * 20
    a, b = predict("customers", "holder_nm", "VARCHAR(80)", vals), predict("customers", "holder_nm", "VARCHAR(80)", vals)
    assert (a.category, a.confidence, a.reasons) == (b.category, b.confidence, b.reasons)


# ---------------------------------------------------------------- scan integration ----------

def test_ml_is_off_unless_requested(client, H, conn_id):
    scan(client, H, conn_id)  # existing API callers: no `ml` flag
    assert all(c["ml"] is None for c in classes(client, H, conn_id).values())


@needs_model
def test_scan_with_ml_never_weakens_protection(client, H, conn_id):
    scan(client, H, conn_id, ml=True, ai=False)
    cls = classes(client, H, conn_id)
    assert all(c["ml"] is not None for c in cls.values())
    for c in cls.values():
        # Effective sensitivity is never below the rule result: the model can only raise it.
        assert RANK[c["sensitivity"]] >= RANK[c["detected_sensitivity"]]
        if c["ml"]["status"] == "APPLIED":
            assert RANK[c["ml"]["sensitivity"]] > RANK[c["detected_sensitivity"]] and c["ml"]["confidence"] >= ml_model.min_confidence()
    ev = client.get("/api/audit?action=ml_classification&limit=1", headers=H["admin"]).json()["events"][0]
    assert ev["outcome"] == "success" and ev["details"]["model_version"] == ml_model.get_model().version


def test_confident_ml_upgrade_changes_masking_and_source_stays_intact(client, H, conn_id, monkeypatch):
    """Forces one verdict to exercise the apply path end to end (the real model's output is
    covered above); the model's job ends at classification - masking stays deterministic."""
    from app.ml.model import PiiModel

    class Forced:
        version = "forced-test"

        def predict(self, rows, explain=True):
            out = []
            for _, text in rows:
                if text == "transactions channel":
                    out.append(MlVerdict("PERSON_NAME", "PII_MEDIUM", 0.97, [], [{"feature": "x", "evidence": "test", "impact": 0.5}]))
                else:
                    out.append(MlVerdict("NONE", "PUBLIC", 0.99))
            return out

    monkeypatch.setattr(ml_model, "get_model", lambda: Forced())
    sql = "SELECT txn_id, channel FROM transactions ORDER BY txn_id LIMIT 5"
    admin_before = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": sql}, headers={**H["admin"], "X-Sentinel-CSRF": "1"}).json()["rows"]
    scan(client, H, conn_id, ml=True, ai=False)
    ch = classes(client, H, conn_id)["transactions.channel"]
    assert ch["ml"]["status"] == "APPLIED" and ch["sensitivity"] == "PII_MEDIUM" and "+ ml" in ch["detection_method"]
    sup = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": sql}, headers={**H["support"], "X-Sentinel-CSRF": "1"}).json()["rows"]
    adm = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": sql}, headers={**H["admin"], "X-Sentinel-CSRF": "1"}).json()["rows"]
    assert all("*" in r[1] for r in sup) and adm == admin_before  # masked for Support, Admin unchanged
    # NONE verdicts on sensitive columns were refused, not applied.
    nm = classes(client, H, conn_id)["customers.cust_nm"]
    assert nm["ml"]["status"] == "KEPT_RULE" and nm["sensitivity"] in SENSITIVE_LABELS
    # A later scan without ML keeps the upgrade instead of silently reverting it.
    monkeypatch.undo()
    scan(client, H, conn_id)
    assert classes(client, H, conn_id)["transactions.channel"]["sensitivity"] == "PII_MEDIUM"
    assert PiiModel  # imported for type reference only


def test_missing_model_falls_back_to_rules(client, H, conn_id, monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_ML_MODEL", str(tmp_path / "nope.joblib"))
    ml_model.reset_model()
    try:
        scan(client, H, conn_id, ml=True, ai=False)
        cls = classes(client, H, conn_id)
        assert all(c["ml"]["status"] in ("ML_UNAVAILABLE",) for c in cls.values())
        ev = client.get("/api/audit?action=ml_classification&limit=1", headers=H["admin"]).json()["events"][0]
        assert ev["outcome"] == "error" and "rule-based results kept" in ev["reason"]
        card_ = client.get("/api/ml/model-card", headers=H["admin"]).json()
        assert card_["available"] is False and "not found" in card_["error"]
    finally:
        monkeypatch.delenv("SENTINEL_ML_MODEL")
        ml_model.reset_model()


def test_model_card_rbac(client, H):
    assert client.get("/api/ml/model-card", headers=H["admin"]).status_code == 200
    assert client.get("/api/ml/model-card", headers=H["compliance"]).status_code == 200
    assert client.get("/api/ml/model-card", headers=H["support"]).status_code == 403
    assert client.get("/api/ml/model-card", headers=H["analyst"]).status_code == 403
