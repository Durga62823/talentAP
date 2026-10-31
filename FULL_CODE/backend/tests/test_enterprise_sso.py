"""Feature 1: enterprise SSO (OIDC code flow + offline mock IdP) and SCIM 2.0 provisioning."""
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from conftest import USERS
from app import sso

MOCK = sso.MOCK_IDP_ID
PRIYA, SAM, VIKRAM, ARJUN = (f"{n}@saffronbank.example" for n in ("priya.nair", "sam.dsouza", "vikram.iyer", "arjun.mehta"))


def start(client, hint, idp=MOCK):
    """Login redirect -> mock IdP. Returns the IdP's redirect to our callback."""
    r = client.get(f"/api/auth/sso/login/{idp}", params={"login_hint": hint}, follow_redirects=False)
    assert r.status_code == 302 and sso.STATE_COOKIE in r.headers["set-cookie"]
    r = client.get(r.headers["location"], follow_redirects=False)
    assert r.status_code == 302
    return r.headers["location"]


def sso_login(client, hint):
    r = client.get(start(client, hint), follow_redirects=False)
    assert r.status_code == 302
    return r


def me(client):
    return client.get("/api/auth/me").json()["user"]


def audit_events(client, H, action):
    return client.get("/api/audit", params={"action": action, "limit": 50}, headers=H["admin"]).json()["events"]


@pytest.fixture(autouse=True)
def _fresh_cookies(client):
    client.cookies.clear()
    yield
    client.cookies.clear()


# ---- providers & mock IdP login ----------------------------------------------------------

def test_provider_list_is_public_and_secret_free(client):
    r = client.get("/api/auth/sso/providers")
    assert r.status_code == 200
    mock = next(p for p in r.json() if p["id"] == MOCK)
    assert mock["idp_type"] == "MOCK_SAML" and {p["login_hint"] for p in mock["personas"]} >= {PRIYA, SAM}
    assert "secret" not in r.text and sso.MOCK_CLIENT_ID not in r.text


def test_mock_sso_provisions_user_with_group_mapped_role(client, H):
    r = sso_login(client, PRIYA)
    assert r.headers["location"] == "/" and "sm_session=" in r.headers["set-cookie"]
    u = me(client)
    assert u["username"] == PRIYA and u["role"] == "support"
    first = audit_events(client, H, "sso_login")[0]
    assert first["actor"] == PRIYA and first["details"]["jit_provisioned"] is True

    client.cookies.clear()
    sso_login(client, PRIYA)  # second sign-in reuses the account
    assert me(client)["id"] == u["id"]
    assert audit_events(client, H, "sso_login")[0]["details"]["jit_provisioned"] is False
    users = client.get("/api/users", headers=H["admin"]).json()
    fed = [x for x in users if x["username"] == PRIYA]
    assert len(fed) == 1 and fed[0]["federated"] and fed[0]["idp_name"] and fed[0]["idp_linked"]
    local = next(x for x in users if x["username"] == USERS["admin"])
    assert local["federated"] is False and local["idp_name"] is None


def test_unmapped_directory_user_gets_idp_default_role(client):
    sso_login(client, SAM)
    assert me(client)["role"] == "analyst"


def test_idp_group_change_resyncs_role_on_next_login(client, H, monkeypatch):
    sso_login(client, PRIYA)
    assert me(client)["role"] == "support"
    monkeypatch.setitem(sso.MOCK_DIRECTORY, PRIYA, sso.MOCK_DIRECTORY[PRIYA] | {"groups": ["DG-Compliance"]})
    client.cookies.clear()
    sso_login(client, PRIYA)
    assert me(client)["role"] == "compliance"
    assert audit_events(client, H, "sso_login")[0]["details"]["role_change"] == ["support", "compliance"]
    monkeypatch.undo()
    client.cookies.clear()
    sso_login(client, PRIYA)
    assert me(client)["role"] == "support"


def test_callback_rejects_state_mismatch_and_foreign_browser(client, H):
    cb = start(client, PRIYA)
    forged = cb.replace("state=", "state=x")
    r = client.get(forged, follow_redirects=False)
    assert r.headers["location"] == "/login?sso_error=state_mismatch" and "sm_session" not in r.headers.get("set-cookie", "")
    cb = start(client, PRIYA)
    client.cookies.clear()  # the response lands in a browser that never started this sign-in (login CSRF)
    r = client.get(cb, follow_redirects=False)
    assert r.headers["location"] == "/login?sso_error=state_missing"
    assert client.get("/api/auth/me").status_code == 401
    fails = audit_events(client, H, "sso_login_failed")
    assert {f["reason"].split(":")[0] for f in fails[:2]} == {"state_mismatch", "state_missing"}


def test_authorization_code_is_single_use(client):
    cb = start(client, PRIYA)
    state_cookie = client.cookies.get(sso.STATE_COOKIE)
    assert client.get(cb, follow_redirects=False).headers["location"] == "/"
    client.cookies.clear()
    client.cookies.set(sso.STATE_COOKIE, state_cookie, path="/api/auth/sso")  # attacker replays code + state
    r = client.get(cb, follow_redirects=False)
    assert r.headers["location"] == "/login?sso_error=invalid_grant"


def test_mock_idp_enforces_pkce_s256_and_known_identities(client):
    r = client.get(f"/api/auth/sso/login/{MOCK}", params={"login_hint": PRIYA}, follow_redirects=False)
    downgraded = r.headers["location"].replace("code_challenge_method=S256", "code_challenge_method=plain")
    assert "error=invalid_request" in client.get(downgraded, follow_redirects=False).headers["location"]
    r = client.get(f"/api/auth/sso/login/{MOCK}", params={"login_hint": "mallory@evil.example"}, follow_redirects=False)
    cb = client.get(r.headers["location"], follow_redirects=False).headers["location"]
    assert client.get(cb, follow_redirects=False).headers["location"] == "/login?sso_error=idp_access_denied"
    # Without a hint the simulated IdP shows its directory picker.
    r = client.get(f"/api/auth/sso/login/{MOCK}", follow_redirects=False)
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and "Priya Nair" in page.text and "<script" not in page.text
    assert client.get("/api/auth/sso/login/no-such-idp", follow_redirects=False).headers["location"] == "/login?sso_error=unknown_provider"


def test_federated_users_have_no_local_password(client, H):
    sso_login(client, PRIYA)
    uid = me(client)["id"]
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": PRIYA, "password": "Anything@2026"}).status_code == 401
    r = client.patch(f"/api/users/{uid}", json={"password": "Backdoor@2026x"}, headers=H["admin"])
    assert r.status_code == 400 and "identity provider" in r.json()["error"]["message"]


# ---- ID token validation (the code every provider type goes through) ---------------------

def _claims(**over):
    now = int(time.time())
    return {"iss": sso.MOCK_ISSUER, "aud": sso.MOCK_CLIENT_ID, "sub": "u-1", "nonce": "n-1", "iat": now, "exp": now + 300} | over


def _validate(token):
    return sso.validate_id_token(token, jwks=sso.mock_idp.jwks(), issuer=sso.MOCK_ISSUER, audience=sso.MOCK_CLIENT_ID, nonce="n-1")


def test_id_token_validation_rejects_forgeries(client):
    good = sso.mock_idp.sign(_claims())
    assert _validate(good)["sub"] == "u-1"
    h, _, s = good.split(".")
    other = sso.MockIdP()
    other._key = rsa.generate_private_key(65537, 2048)
    b64 = lambda obj: sso._b64e(json.dumps(obj).encode())  # noqa: E731
    cases = {
        "token_issuer": sso.mock_idp.sign(_claims(iss="https://evil.example")),
        "token_audience": sso.mock_idp.sign(_claims(aud="some-other-app")),
        "token_expired": sso.mock_idp.sign(_claims(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)),
        "token_nonce": sso.mock_idp.sign(_claims(nonce="replayed-from-another-login")),
        "token_signature": f"{h}.{b64(_claims(sub='admin'))}.{s}",  # payload swapped under a valid signature
        "token_alg": f"{b64({'alg': 'none'})}.{b64(_claims())}.",
        "token_malformed": "not-a-jwt",
    }
    cases["token_key"] = other.sign(_claims())  # signed by a key the IdP never published
    for code, token in cases.items():
        with pytest.raises(sso.SsoError) as exc:
            _validate(token)
        assert exc.value.code == code, (code, exc.value.code)


def test_real_oidc_provider_code_flow(client, H, monkeypatch):
    """A non-mock OIDC provider: discovery, PKCE code exchange and JWKS are faked at the HTTP layer."""
    from app.metadb import IdentityProvider, SessionLocal
    from app.security import encrypt_secret

    issuer = "https://login.okta.example/oauth2/default"
    db = SessionLocal()
    db.add(IdentityProvider(id="okta_test", name="Okta (test)", issuer_url=issuer, client_id="dg-okta", idp_type="OIDC",
                            client_secret_enc=encrypt_secret("okta-client-secret"), default_role="", group_role_map={"DG-Support": "support"}))
    db.commit()
    db.close()
    idp_key = sso.MockIdP()
    idp_key._key = rsa.generate_private_key(65537, 2048)
    seen: dict = {}

    def fake_http(method, url, **kw):
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": issuer, "authorization_endpoint": f"{issuer}/v1/authorize", "token_endpoint": f"{issuer}/v1/token",
                    "jwks_uri": f"{issuer}/v1/keys"}
        if url.endswith("/v1/keys"):
            return idp_key.jwks()
        data = kw["data"]
        assert method == "POST" and data["client_secret"] == "okta-client-secret" and data["grant_type"] == "authorization_code"
        assert sso.pkce_challenge(data["code_verifier"]) == seen["challenge"]
        now = int(time.time())
        return {"id_token": idp_key.sign({"iss": issuer, "aud": "dg-okta", "sub": "00u-okta-77", "nonce": seen["nonce"], "iat": now,
                                          "exp": now + 300, "email": "meera.okta@saffronbank.example", "groups": seen["groups"]})}

    monkeypatch.setattr(sso, "_http_json", fake_http)

    def run(groups):
        r = client.get("/api/auth/sso/login/okta_test", follow_redirects=False)
        loc = urlparse(r.headers["location"])
        qs = {k: v[0] for k, v in parse_qs(loc.query).items()}
        assert loc.netloc == "login.okta.example" and qs["code_challenge_method"] == "S256"
        assert qs["redirect_uri"] == "http://testserver/api/auth/sso/callback" and "code_verifier" not in qs
        seen.update(nonce=qs["nonce"], challenge=qs["code_challenge"], groups=groups)
        return client.get("/api/auth/sso/callback", params={"code": "okta-code", "state": qs["state"]}, follow_redirects=False)

    assert run(["DG-Support"]).headers["location"] == "/"
    assert me(client)["role"] == "support"
    client.cookies.clear()
    # This provider has no default role: users whose groups map to nothing are refused (fail closed).
    assert run(["Everyone"]).headers["location"] == "/login?sso_error=no_role"


# ---- SCIM 2.0 -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scim(client, H):
    r = client.post("/api/scim/tokens", json={"description": "Entra ID provisioning", "idp_id": MOCK}, headers=H["admin"])
    assert r.status_code == 201
    tok = r.json()
    assert tok["token"].startswith("dgscim_") and tok["status"] == "active"
    return {"Authorization": f"Bearer {tok['token']}", "Content-Type": "application/scim+json", "_id": tok["id"]}


def S(scim):
    return {k: v for k, v in scim.items() if not k.startswith("_")}


def test_scim_token_admin_is_privileged_and_never_echoed(client, H, scim):
    assert client.post("/api/scim/tokens", json={"description": "x-token"}, headers=H["support"]).status_code == 403
    assert client.get("/api/scim/tokens", headers=H["compliance"]).status_code == 403
    listed = client.get("/api/scim/tokens", headers=H["admin"])
    assert listed.status_code == 200 and S(scim)["Authorization"][7:] not in listed.text and "token_hash" not in listed.text
    blob = str(client.get("/api/audit", params={"action": "scim_token_create"}, headers=H["admin"]).json())
    assert S(scim)["Authorization"][7:] not in blob


def test_scim_authentication_boundaries(client, H, scim):
    r = client.get("/api/scim/v2/Users")
    assert r.status_code == 401 and r.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    assert client.get("/api/scim/v2/Users", headers=H["admin"]).status_code == 401  # console session is not a SCIM credential
    assert client.get("/api/users", headers=S(scim)).status_code == 401  # SCIM token is not a console session
    spc = client.get("/api/scim/v2/ServiceProviderConfig", headers=S(scim)).json()
    assert spc["patch"]["supported"] is True and spc["bulk"]["supported"] is False


def test_scim_provisioning_lifecycle(client, H, scim):
    body = {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": VIKRAM, "externalId": "mock-5e2b-vikram",
            "name": {"givenName": "Vikram", "familyName": "Iyer"}, "active": True, "roles": [{"value": "Compliance", "primary": True}]}
    r = client.post("/api/scim/v2/Users", json=body, headers=S(scim))
    assert r.status_code == 201 and r.headers["content-type"].startswith("application/scim+json")
    u = r.json()
    assert u["roles"][0]["value"] == "Compliance" and u["displayName"] == "Vikram Iyer" and r.headers["location"].endswith(u["id"])
    assert client.post("/api/scim/v2/Users", json=body, headers=S(scim)).json()["scimType"] == "uniqueness"
    # A SCIM client can never claim (and so take over) a local account.
    r = client.post("/api/scim/v2/Users", json=body | {"userName": USERS["admin"], "externalId": "x"}, headers=S(scim))
    assert r.status_code == 409

    found = client.get("/api/scim/v2/Users", params={"filter": f'userName eq "{VIKRAM.upper()}"'}, headers=S(scim)).json()
    assert found["totalResults"] == 1 and found["Resources"][0]["id"] == u["id"]
    everyone = client.get("/api/scim/v2/Users", headers=S(scim)).json()["Resources"]
    assert USERS["admin"] not in {x["userName"] for x in everyone}
    local_id = next(x["id"] for x in client.get("/api/users", headers=H["admin"]).json() if x["username"] == USERS["admin"])
    assert client.get(f"/api/scim/v2/Users/{local_id}", headers=S(scim)).status_code == 404
    assert client.patch(f"/api/scim/v2/Users/{local_id}", json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
                        headers=S(scim)).status_code == 404

    # First SSO sign-in lands on the provisioned account (matched on externalId == sub).
    sso_login(client, VIKRAM)
    assert me(client)["id"] == u["id"] and me(client)["role"] == "compliance"

    # Entra ID style deprovisioning: string boolean, Replace with a path.
    r = client.patch(f"/api/scim/v2/Users/{u['id']}", json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                     "Operations": [{"op": "Replace", "path": "active", "value": "False"}]}, headers=S(scim))
    assert r.status_code == 200 and r.json()["active"] is False
    assert client.get("/api/auth/me").status_code == 401  # session revoked immediately
    client.cookies.clear()
    assert sso_login(client, VIKRAM).headers["location"] == "/login?sso_error=account_disabled"

    r = client.put(f"/api/scim/v2/Users/{u['id']}", json={"userName": VIKRAM, "displayName": "Vikram R. Iyer", "active": True,
                   "roles": [{"value": "Support"}]}, headers=S(scim))
    assert r.json()["displayName"] == "Vikram R. Iyer" and r.json()["roles"][0]["value"] == "Support" and r.json()["active"]
    updates = audit_events(client, H, "scim_user_update")
    assert updates[0]["actor"].startswith("scim:") and updates[0]["details"]["changes"]["role"] == ["compliance", "support"]


def test_scim_user_without_external_id_links_on_first_sso(client, H, scim):
    r = client.post("/api/scim/v2/Users", json={"userName": ARJUN, "displayName": "Arjun Mehta", "roles": [{"value": "Analyst"}]},
                    headers=S(scim))
    assert r.status_code == 201
    sso_login(client, ARJUN)
    assert me(client)["id"] == r.json()["id"]
    assert audit_events(client, H, "sso_login")[0]["details"]["linked_scim_account"] is True
    assert [x["username"] for x in client.get("/api/users", headers=H["admin"]).json()].count(ARJUN) == 1


def test_scim_validation_errors(client, scim):
    r = client.get("/api/scim/v2/Users", params={"filter": "userName regex \".*\""}, headers=S(scim))
    assert r.status_code == 400 and r.json()["scimType"] == "invalidFilter"
    r = client.post("/api/scim/v2/Users", json={"userName": "new.hire@saffronbank.example", "roles": [{"value": "SuperUser"}]}, headers=S(scim))
    assert r.status_code == 400 and r.json()["scimType"] == "invalidValue"
    r = client.post("/api/scim/v2/Users", json={"userName": "new.hire@saffronbank.example", "active": "maybe"}, headers=S(scim))
    assert r.status_code == 400


def test_revoked_and_expired_scim_tokens_are_rejected(client, H, scim):
    from app.metadb import SCIMToken, SessionLocal, utcnow
    from datetime import timedelta

    extra = client.post("/api/scim/tokens", json={"description": "Okta sync", "expires_in_days": 1}, headers=H["admin"]).json()
    h = {"Authorization": f"Bearer {extra['token']}"}
    assert client.get("/api/scim/v2/Users", headers=h).status_code == 200
    db = SessionLocal()
    db.get(SCIMToken, extra["id"]).expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()
    assert client.get("/api/scim/v2/Users", headers=h).status_code == 401
    assert client.delete(f"/api/scim/tokens/{scim['_id']}", headers=H["admin"]).json() == {"ok": True}
    assert client.get("/api/scim/v2/Users", headers=S(scim)).status_code == 401
    statuses = {t["id"]: t["status"] for t in client.get("/api/scim/tokens", headers=H["admin"]).json()}
    assert statuses[scim["_id"]] == "revoked" and statuses[extra["id"]] == "expired"
    assert len(audit_events(client, H, "scim_auth_failed")) >= 2
    assert client.get("/api/audit/verify-chain", headers=H["admin"]).json()["valid"] is True
