"""Gemini-assisted classification: validation, failure fallback, upgrade-only rule, privacy.
Gemini is always mocked; no network call or API key is needed."""
import hashlib
import json
import sqlite3

import httpx
import pytest
from google.genai import errors

from app import ai_classifier as ai
from app.ai_features import assert_sanitized, extract_features
from app.config import get_settings
from app.scanner import classify_column
from conftest import q


# ---------------------------------------------------------------- fake Gemini client ----------

class _Resp:
    def __init__(self, text):
        self.text = text


class FakeGemini:
    """Stands in for google.genai.Client. `answer(items)` decides the reply per call."""

    def __init__(self, answer=None, raise_exc=None):
        self.calls: list[dict] = []
        self.answer = answer
        self.raise_exc = raise_exc
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "system": config.system_instruction})
        if self.raise_exc:
            raise self.raise_exc
        items = json.loads(contents)["columns"]
        return _Resp(self.answer(items) if self.answer else json.dumps({"results": []}))


def verdict(key, category, confidence=0.95, needs_review=False, **kw):
    return {"column_key": key, "is_sensitive": category not in ("NONE", "CUSTOMER_ID", "ORG_CONTACT"), "category": category,
            "pii_type": kw.get("pii_type", "OTHER"), "identifier_kind": kw.get("identifier_kind", "DIRECT"),
            "confidence": confidence, "reason": kw.get("reason", "test verdict"), "needs_review": needs_review}


def agree_with_rules(overrides=None):
    """Echo the rule engine's category for every column, except explicit overrides by column name."""
    overrides = overrides or {}

    def answer(items):
        out = []
        for it in items:
            f = it["features"]
            name = f"{f['table_name']}.{f['column_name']}"
            out.append(verdict(it["column_key"], overrides.get(name, f["rule_engine"]["category"])))
        return json.dumps({"results": out})

    return answer


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(ai, "_sleep", lambda s: None)


@pytest.fixture
def gemini(monkeypatch):
    """Install a fake Gemini; yields a setter. Always restores the real classifier afterwards."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    def install(fake):
        ai.set_classifier(ai.GeminiClassifier(ai.ai_settings(), client=fake))
        return fake

    yield install
    ai.set_classifier(None)


def scan(client, H, conn_id, use_ai=True):
    r = client.post(f"/api/databases/{conn_id}/scan", json={"sample_size": 100, "ai": use_ai}, headers={**H["admin"], "X-Sentinel-CSRF": "1"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    return r.json()


def classes(client, H, conn_id):
    return {f"{c['table']}.{c['column']}": c for c in client.get(f"/api/classifications?connection_id={conn_id}", headers=H["admin"]).json()}


# ---------------------------------------------------------------- response validation ----------

def test_valid_response_is_parsed():
    out = ai.parse_response(json.dumps({"results": [verdict("col_1", "NATIONAL_ID", pii_type="PAN")]}), {"col_1"})
    assert out["col_1"].category.value == "NATIONAL_ID" and out["col_1"].pii_type.value == "PAN"


def test_invalid_json_is_rejected():
    with pytest.raises(ai.AIUnavailable) as e:
        ai.parse_response("not json {", {"col_1"})
    assert e.value.code == "invalid_response"


def test_unknown_category_and_unrequested_keys_are_dropped():
    text = json.dumps({"results": [verdict("col_1", "SUPER_SECRET"), verdict("col_9", "EMAIL"), verdict("col_2", "EMAIL"),
                                   {**verdict("col_3", "EMAIL"), "confidence": 7}]})
    out = ai.parse_response(text, {"col_1", "col_2", "col_3"})
    assert set(out) == {"col_2"}  # unknown enum, unrequested key and out-of-range confidence all dropped
    with pytest.raises(ai.AIUnavailable):
        ai.parse_response(json.dumps({"results": [verdict("col_1", "SUPER_SECRET")]}), {"col_1"})


def test_response_schema_is_flat_and_restricted_to_existing_categories():
    schema = json.dumps(ai.response_schema())
    assert "$ref" not in schema and "$defs" not in schema
    item = ai.response_schema()["properties"]["results"]["items"]
    assert set(item["properties"]["category"]["enum"]) == set(ai.CATEGORIES)


# ---------------------------------------------------------------- upgrade-only decision ----------

def _v(category, confidence=0.95, needs_review=False):
    return ai.AIColumnResult.model_validate(verdict("k", category, confidence, needs_review))


@pytest.mark.parametrize("current,sens,reviewed,v,expected", [
    ("NONE", "PUBLIC", False, _v("NATIONAL_ID"), ("APPLIED", True)),           # upgrade applied
    ("NONE", "PUBLIC", False, _v("NATIONAL_ID", 0.5), ("LOW_CONFIDENCE", False)),
    ("NONE", "PUBLIC", False, _v("NATIONAL_ID", needs_review=True), ("LOW_CONFIDENCE", False)),
    ("CREDIT_CARD", "PII_HIGH", False, _v("NONE"), ("KEPT_RULE", False)),      # AI says not sensitive: never downgrade
    ("EMAIL", "PII_MEDIUM", False, _v("PHONE"), ("KEPT_RULE", False)),         # lateral change: keep rule
    ("NONE", "PUBLIC", True, _v("EMAIL"), ("HUMAN_REVIEWED", False)),          # a human decision always wins
    ("EMAIL", "PII_MEDIUM", False, _v("EMAIL"), ("AGREES", False)),
    ("EMAIL", "PII_MEDIUM", False, None, ("AI_UNAVAILABLE", False)),
])
def test_decide_is_upgrade_only(current, sens, reviewed, v, expected):
    assert ai.decide(current, sens, reviewed, v, 0.75) == expected


# ---------------------------------------------------------------- failure handling ----------

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ai.AIUnavailable) as e:
        ai.GeminiClassifier(ai.ai_settings()).classify_batch([{"column_key": "col_1", "features": {}}])
    assert e.value.code == "not_configured"


def test_timeout_is_retried_then_reported(no_sleep, monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "2")
    fake = FakeGemini(raise_exc=httpx.ReadTimeout("slow"))
    with pytest.raises(ai.AIUnavailable) as e:
        ai.GeminiClassifier(ai.ai_settings(), client=fake).classify_batch([{"column_key": "col_1", "features": {}}])
    assert e.value.code == "timeout" and len(fake.calls) == 3


def test_quota_exhaustion(no_sleep, monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "1")
    fake = FakeGemini(raise_exc=errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}))
    with pytest.raises(ai.AIUnavailable) as e:
        ai.GeminiClassifier(ai.ai_settings(), client=fake).classify_batch([{"column_key": "col_1", "features": {}}])
    assert e.value.code == "quota_exhausted" and len(fake.calls) == 2


def test_bad_key_is_not_retried(no_sleep):
    fake = FakeGemini(raise_exc=errors.ClientError(403, {"error": {"code": 403, "message": "denied", "status": "PERMISSION_DENIED"}}))
    with pytest.raises(ai.AIUnavailable) as e:
        ai.GeminiClassifier(ai.ai_settings(), client=fake).classify_batch([{"column_key": "col_1", "features": {}}])
    assert e.value.code == "auth_failed" and len(fake.calls) == 1


# ---------------------------------------------------------------- sanitization ----------

def test_features_never_contain_sample_values():
    samples = ["priya.nair@example.com", "rahul.k@example.in", None, "a.b@example.org"]
    feats = extract_features("customers", "emailid", "TEXT", True, False, samples, classify_column("emailid", "TEXT", samples))
    blob = json.dumps(feats)
    assert feats["email_match_ratio"] == 1.0
    assert not any(s and s in blob for s in samples)
    with pytest.raises(ValueError):
        assert_sanitized({**feats, "leak": "priya.nair@example.com"}, samples)


# ---------------------------------------------------------------- end-to-end through the scan ----------

def _target_hash():
    db = next(get_settings().targets_dir.glob("saffron_bank.db"))
    return hashlib.sha256(db.read_bytes()).hexdigest()


def test_scan_without_key_falls_back_to_rules(client, H, conn_id, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    scan(client, H, conn_id)
    after = classes(client, H, conn_id)
    # Nothing came from the AI: every effective classification is exactly the rule result.
    # (Compared within one scan; the rule scanner samples random rows, so two scans can differ.)
    assert all((c["category"], c["sensitivity"]) == (c["detected_category"], c["detected_sensitivity"])
               and "gemini" not in c["detection_method"] for c in after.values())
    assert all(c["ai"]["status"] == "AI_UNAVAILABLE" and c["ai"]["error_code"] == "not_configured" for c in after.values())
    ev = client.get("/api/audit?action=ai_classification&limit=1", headers=H["admin"]).json()["events"][0]
    assert ev["outcome"] == "error" and "rule-based results kept" in ev["reason"]


def test_ai_upgrade_applies_and_changes_masking(client, H, conn_id, gemini):
    cls = classes(client, H, conn_id)
    assert cls["transactions.channel"]["sensitivity"] in ("PUBLIC", "INTERNAL")
    sql = "SELECT txn_id, channel FROM transactions ORDER BY txn_id LIMIT 5"
    support_before = q(client, H["support"], conn_id, sql).json()["rows"]
    source_before = _target_hash()

    # AI disagrees with the rules twice: it upgrades `channel`, and tries to downgrade `cust_nm`.
    fake = gemini(FakeGemini(agree_with_rules({"transactions.channel": "PERSON_NAME", "customers.cust_nm": "NONE"})))
    scan(client, H, conn_id)
    cls = classes(client, H, conn_id)

    ch = cls["transactions.channel"]
    assert ch["ai"]["status"] == "APPLIED" and ch["ai"]["detected_by"] == "AI"
    assert (ch["category"], ch["sensitivity"]) == ("PERSON_NAME", "PII_MEDIUM")
    assert ch["detected_category"] == "NONE"  # the rule result stays visible next to the AI result
    nm = cls["customers.cust_nm"]
    assert nm["ai"]["status"] == "KEPT_RULE" and nm["sensitivity"] == "PII_MEDIUM"  # downgrade refused

    support_after = q(client, H["support"], conn_id, sql).json()["rows"]
    assert support_after != support_before and all("*" in r[1] for r in support_after)  # now masked for Support
    assert q(client, H["admin"], conn_id, sql).json()["rows"] == support_before  # Admin still sees the full value
    assert _target_hash() == source_before  # source database untouched
    assert len(fake.calls) >= 1 and all(c["model"] == ai.ai_settings().model for c in fake.calls)

    ev = client.get("/api/audit?action=ai_classification&limit=1", headers=H["admin"]).json()["events"][0]
    assert ev["outcome"] == "success" and "transactions.channel" in ev["columns"]
    assert ev["details"]["prompt_version"] == ai.PROMPT_VERSION and ev["details"]["status_counts"]["APPLIED"] >= 1


def test_unchanged_features_are_served_from_cache(client, H, conn_id, gemini):
    fake = gemini(FakeGemini(agree_with_rules({"transactions.channel": "PERSON_NAME", "customers.cust_nm": "NONE"})))
    scan(client, H, conn_id)
    ev = client.get("/api/audit?action=ai_classification&limit=1", headers=H["admin"]).json()["events"][0]
    # Unchanged columns are answered from the cache; only columns whose sampled statistics moved
    # across a rounding boundary (sparse columns, random sampling) are asked again.
    asked = sum(len(json.loads(c["contents"])["columns"]) for c in fake.calls)
    assert ev["details"]["cache_hits"] >= 0.9 * ev["details"]["columns"]
    assert asked == ev["details"]["columns"] - ev["details"]["cache_hits"]


def test_rescan_without_ai_keeps_ai_upgrade(client, H, conn_id):
    scan(client, H, conn_id, use_ai=False)
    assert classes(client, H, conn_id)["transactions.channel"]["sensitivity"] == "PII_MEDIUM"


def test_human_review_overrides_ai(client, H, conn_id, gemini):
    cid = classes(client, H, conn_id)["transactions.channel"]["id"]
    r = client.patch(f"/api/classifications/{cid}", json={"decision": "override", "category": "NONE", "sensitivity": "PUBLIC"},
                     headers={**H["admin"], "X-Sentinel-CSRF": "1"})
    assert r.status_code == 200
    gemini(FakeGemini(agree_with_rules({"transactions.channel": "CREDIT_CARD"})))
    scan(client, H, conn_id)
    ch = classes(client, H, conn_id)["transactions.channel"]
    assert ch["sensitivity"] == "PUBLIC" and ch["ai"]["status"] == "HUMAN_REVIEWED"


def test_no_raw_pii_is_ever_sent_to_gemini(client, H, conn_id, gemini):
    fake = gemini(FakeGemini(agree_with_rules()))
    # Force fresh calls: change the model name so the cache cannot answer.
    import os
    os.environ["GEMINI_MODEL"] = "gemini-test-privacy"
    try:
        scan(client, H, conn_id)
    finally:
        os.environ.pop("GEMINI_MODEL", None)
    payload = "\n".join(c["contents"] for c in fake.calls)
    assert payload, "the fake should have been called"
    db = sqlite3.connect(f"file:{next(get_settings().targets_dir.glob('saffron_bank.db')).as_posix()}?mode=ro", uri=True)
    raw = set()
    for sql in ["SELECT cust_nm, emailid, mob_no, addr_line1, dob_dt FROM customers LIMIT 300",
                "SELECT CARD_NO, NAME_ON_CARD FROM cards LIMIT 300", "SELECT account_no, curr_bal FROM accounts LIMIT 300",
                "SELECT * FROM kyc_records LIMIT 300"]:
        for row in db.execute(sql):
            raw.update(str(v) for v in row if v is not None and len(str(v)) >= 6)
    leaked = [v for v in raw if v in payload]
    assert leaked == [], f"raw values found in AI payload: {leaked[:3]}"
    for c in fake.calls:
        for item in json.loads(c["contents"])["columns"]:
            assert set(item) == {"column_key", "features"}


def test_rbac_on_ai_endpoints(client, H, conn_id):
    assert client.post(f"/api/databases/{conn_id}/scan", json={"ai": True}, headers={**H["support"], "X-Sentinel-CSRF": "1"}).status_code == 403
    assert client.get("/api/ai/status", headers=H["analyst"]).status_code == 403
    status = client.get("/api/ai/status", headers=H["admin"]).json()
    assert "key" not in json.dumps(status).lower().replace("api key", "")
