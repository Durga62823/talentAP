"""Result cache, response compression and request metrics."""
from conftest import CUSTOMER, q


def test_cache_never_bypasses_masking_or_audit(client, H, conn_id):
    sql = f"SELECT customer_id, cust_nm, mob_no FROM customers WHERE customer_id = '{CUSTOMER}'"
    admin = q(client, H["admin"], conn_id, sql).json()
    # Same SQL from a lower-privileged role: may reuse the cached raw rows, must still be masked.
    sup = q(client, H["support"], conn_id, sql).json()
    again = q(client, H["support"], conn_id, sql).json()
    assert again["cache_hit"] is True
    assert sup["rows"] == again["rows"] and sup["rows"] != admin["rows"]
    assert admin["rows"][0][1] not in str(again["rows"]) and again["rows"][0][1].count("*") >= 4
    # Every request is still audited, cached or not.
    assert len({admin["audit_event_id"], sup["audit_event_id"], again["audit_event_id"]}) == 3


def test_cache_still_enforces_authorisation(client, H, conn_id):
    sql = "SELECT cust_nm FROM customers WHERE cust_nm LIKE 'A%' LIMIT 3"
    assert q(client, H["admin"], conn_id, sql).status_code == 200
    # Support may not filter on a masked column; a warm cache must not change that.
    assert q(client, H["support"], conn_id, sql).status_code == 403


def test_parallel_queries_do_not_close_each_others_connections(client, conn_id):
    # Regression: the SQLite read engine used SingletonThreadPool, which closed connections in
    # use by other threads once more than 5 threads queried at once ("closed database" -> 500).
    from concurrent.futures import ThreadPoolExecutor

    from app.connectors import get_adapter
    from app.metadb import DbConnection, SessionLocal

    db = SessionLocal()
    try:
        adapter = get_adapter(db.get(DbConnection, conn_id))
    finally:
        db.close()
    # Distinct SQL per call so nothing is served from the result cache.
    sqls = [f"SELECT COUNT(*) FROM transactions WHERE amount_inr > {i}" for i in range(24)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda s: adapter.execute_readonly(s, 10_000, 10), sqls))
    assert all(rows and rows[0][0] >= 0 for _, rows in results)


def test_large_responses_are_gzipped(client, H):
    r = client.get("/api/classifications", headers={**H["admin"], "Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"


def test_metrics_endpoint(client, H, conn_id):
    q(client, H["analyst"], conn_id, "SELECT COUNT(*) AS n FROM transactions")
    r = client.get("/api/metrics", headers=H["admin"])
    assert r.status_code == 200
    body = r.json()
    routes = {x["route"]: x for x in body["routes"]}
    assert routes["POST /api/query/execute"]["count"] >= 1
    assert routes["POST /api/query/execute"]["p95_ms"] >= routes["POST /api/query/execute"]["p50_ms"] >= 0
    assert not any("CIF-" in k for k in routes)  # path templates only, never concrete values
    assert {"hits", "misses", "hit_rate"} <= body["query_cache"].keys()
    assert "app;dur=" in r.headers["server-timing"]
    assert client.get("/api/metrics", headers=H["support"]).status_code == 403
    assert client.get("/api/metrics", headers=H["compliance"]).status_code == 200
