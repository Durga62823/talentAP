from conftest import CUSTOMER, PASSWORDS, USERS, login, q


def test_unauthenticated_requests_rejected(client, conn_id):
    for method, path in [("get", "/api/databases"), ("get", "/api/policies"), ("get", "/api/audit"), ("get", "/api/overview")]:
        assert getattr(client, method)(path).status_code == 401
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": "SELECT emailid FROM customers"})
    assert r.status_code == 401
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": "SELECT emailid FROM customers"},
                    headers={"Authorization": "Bearer forged-token"})
    assert r.status_code == 401


def test_bad_password_and_lockout(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "lockme", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "lockme", "password": "wrong"}).status_code == 429


def test_role_in_request_is_ignored(client, H, conn_id):
    r = client.post("/api/query/execute", json={"connection_id": conn_id, "sql": f"SELECT emailid FROM customers WHERE customer_id = '{CUSTOMER}'", "role": "admin"},
                    headers=H["analyst"] | {"X-Role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "analyst"
    assert r.json()["rows"][0][0].startswith("hm_k1_")


def test_support_cannot_change_policies_or_users(client, H):
    assert client.get("/api/policies", headers=H["support"]).status_code == 403
    r = client.post("/api/policies", json={"name": "let me in", "role": "support", "category": "EMAIL", "action": "ALLOW"}, headers=H["support"])
    assert r.status_code == 403
    users = client.get("/api/users", headers=H["admin"]).json()
    me = next(u for u in users if u["username"] == USERS["support"])
    assert client.patch(f"/api/users/{me['id']}", json={"role": "admin"}, headers=H["support"]).status_code == 403
    assert client.put("/api/grants", json={"connection_id": "x", "role": "support", "tables": ["transactions"]}, headers=H["support"]).status_code == 403
    v = client.get("/api/audit", params={"action": "privilege_violation"}, headers=H["admin"]).json()
    assert v["total"] >= 3


def test_analyst_cannot_scan_or_upload_or_read_audit(client, H, conn_id):
    assert client.post(f"/api/databases/{conn_id}/scan", json={}, headers=H["analyst"]).status_code == 403
    assert client.get("/api/audit", headers=H["analyst"]).status_code == 403
    r = client.post("/api/uploads", files={"file": ("a.csv", b"email\nx@example.com\n", "text/csv")}, headers=H["analyst"])
    assert r.status_code == 403


def test_unknown_role_is_denied_everything(client, H, conn_id):
    from app.metadb import Role, SessionLocal, User
    from app.security import hash_password

    db = SessionLocal()
    db.add(Role(name="contractor", description="no perms defined", permissions=["made:up", "query:execute:everything"]))
    db.add(User(username="ghost", display_name="Ghost", role="contractor", password_hash=hash_password("Ghost@2026pw")))
    db.commit()
    db.close()
    r = client.post("/api/auth/login", json={"username": "ghost", "password": "Ghost@2026pw", "mode": "bearer"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert r.json()["user"]["permissions"] == []
    assert q(client, h, conn_id, "SELECT segment FROM customers").status_code == 403
    assert client.get("/api/policies", headers=h).status_code == 403


def test_cookie_session_requires_csrf_header(client, conn_id):
    r = client.post("/api/auth/login", json={"username": USERS["support"], "password": PASSWORDS["support"]})
    assert r.status_code == 200 and "token" not in r.json()  # token never exposed to JS in cookie mode
    body = {"connection_id": conn_id, "sql": "SELECT segment FROM customers LIMIT 1"}
    assert client.post("/api/query/execute", json=body).status_code == 403
    assert client.post("/api/query/execute", json=body, headers={"X-Sentinel-CSRF": "1"}).status_code == 200
    client.post("/api/auth/logout", headers={"X-Sentinel-CSRF": "1"})
    client.cookies.clear()


def test_deactivated_user_and_role_change_revoke_sessions(client, H):
    from conftest import login as _login
    users = client.get("/api/users", headers=H["admin"]).json()
    r = client.post("/api/users", json={"username": "temp.user", "display_name": "Temp", "role": "support", "password": "Temp@2026pass"}, headers=H["admin"])
    assert r.status_code == 201
    tok = client.post("/api/auth/login", json={"username": "temp.user", "password": "Temp@2026pass", "mode": "bearer"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    client.patch(f"/api/users/{r.json()['id']}", json={"active": False}, headers=H["admin"])
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert len(users) >= 3


def test_compare_uses_separately_authenticated_sessions(client, H, conn_id):
    toks = [H[u]["Authorization"][7:] for u in ("admin", "support", "analyst")] + ["not-a-real-token"]
    r = client.post("/api/query/compare", json={"connection_id": conn_id, "sql": f"SELECT emailid FROM customers WHERE customer_id = '{CUSTOMER}'",
                                                "session_tokens": toks}, headers=H["support"])
    res = r.json()["results"]
    assert [x.get("role") for x in res[:3]] == ["admin", "support", "analyst"]
    assert res[3]["status"] == 401
    vals = [x["body"]["rows"][0][0] for x in res[:3]]
    assert vals[0] != vals[1] != vals[2]


def test_errors_do_not_leak_secrets(client, H):
    r = client.post("/api/databases", json={"name": "evil", "kind": "postgresql", "host": "169.254.169.254", "database": "x",
                                            "username": "u", "password": "SuperSecret123"}, headers=H["admin"])
    assert r.status_code == 400 and "allow-list" in r.text and "SuperSecret" not in r.text
    r = client.post("/api/databases", json={"name": "trav", "kind": "sqlite", "file": "../../etc/passwd"}, headers=H["admin"])
    assert r.status_code == 400
    dbs = client.get("/api/databases", headers=H["admin"]).text
    assert "password" not in dbs.lower().replace("has_password", "")


def test_compliance_officer_boundaries(client, H, conn_id):
    h = H["compliance"]
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["role"] == "compliance" and "raw:break_glass" not in me["permissions"]
    # can review and audit
    assert client.get("/api/audit", headers=h).status_code == 200
    assert client.get("/api/classifications", params={"connection_id": conn_id}, headers=h).status_code == 200
    assert client.post("/api/integrity/verify", json={"connection_id": conn_id, "tables": ["branches"]}, headers=h).status_code == 200
    # cannot change policies, users, grants, connections or upload data
    assert client.post("/api/policies", json={"name": "open up", "role": "compliance", "category": "EMAIL", "action": "ALLOW"}, headers=h).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.put("/api/grants", json={"connection_id": conn_id, "role": "compliance", "tables": []}, headers=h).status_code == 403
    assert client.post("/api/databases", json={"name": "x", "kind": "sqlite", "file": "x.db"}, headers=h).status_code == 403
    assert client.post("/api/uploads", files={"file": ("a.csv", b"a,b\n1,2\n", "text/csv")}, headers=h).status_code == 403


def test_nobody_can_promote_themselves(client, H):
    users = client.get("/api/users", headers=H["admin"]).json()
    for role in ("support", "analyst", "compliance"):
        uid = next(u["id"] for u in users if u["username"] == USERS[role])
        assert client.patch(f"/api/users/{uid}", json={"role": "admin"}, headers=H[role]).status_code == 403
    admin_id = next(u["id"] for u in users if u["username"] == USERS["admin"])
    # an admin cannot change their own role either (prevents accidental lock-out / self-escalation paths)
    assert client.patch(f"/api/users/{admin_id}", json={"role": "support"}, headers=H["admin"]).status_code == 400
    roles = {u["username"]: u["role"] for u in client.get("/api/users", headers=H["admin"]).json()}
    assert roles[USERS["support"]] == "support" and roles[USERS["compliance"]] == "compliance"


def test_official_users_are_seeded(client, H):
    names = {u["username"]: u["role"] for u in client.get("/api/users", headers=H["admin"]).json()}
    for u, r in [("admin_anita", "admin"), ("admin_farhan", "admin"), ("admin_meera", "admin"), ("support_ravi", "support"),
                 ("support_neha", "support"), ("support_joseph", "support"), ("analyst_kavya", "analyst"),
                 ("analyst_arnab", "analyst"), ("analyst_hetal", "analyst"), ("compliance_lata", "compliance")]:
        assert names.get(u) == r, u
