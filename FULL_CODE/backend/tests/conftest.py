import os
import tempfile

import pytest

# Isolated data directory per test session - never touches the real demo state.
# The official dataset is read (never modified) from SENTINEL_DATASET_DIR / <repo>/Datasets.
_tmp = tempfile.mkdtemp(prefix="sentinelmask-test-")
os.environ["SENTINEL_DATA_DIR"] = _tmp
for _k in ("SENTINEL_DEMO_PG_HOST", "SENTINEL_MYSQL_APP_PASSWORD"):
    os.environ.pop(_k, None)

from fastapi.testclient import TestClient  # noqa: E402

from app import saffron  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import reset_all  # noqa: E402

# Official sample users (Datasets/data/users.csv) + our compliance officer; demo passwords per role.
USERS = {"admin": "admin_anita", "support": "support_ravi", "analyst": "analyst_kavya", "compliance": "compliance_lata"}
PASSWORDS = {"admin": "Admin@2026!", "support": "Support@2026!", "analyst": "Analyst@2026!", "compliance": "Compliance@2026!"}
# A real customer in the official data with email, KYC (PAN + Aadhaar) and a linked card.
CUSTOMER = "CIF-00UKL72D"

needs_dataset = pytest.mark.skipif(not saffron.dataset_available(), reason="official Saffron Bank dataset not found")


@pytest.fixture(scope="module")
def client():
    if not saffron.dataset_available():
        pytest.skip("official Saffron Bank dataset not found (set SENTINEL_DATASET_DIR)")
    reset_all(with_external=False)
    with TestClient(app) as c:
        yield c


def login(client, role: str) -> dict:
    r = client.post("/api/auth/login", json={"username": USERS[role], "password": PASSWORDS[role], "mode": "bearer"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def H(client):
    return {role: login(client, role) for role in USERS}


@pytest.fixture(scope="module")
def conn_id(client, H):
    conns = client.get("/api/databases", headers=H["admin"]).json()
    return next(c["id"] for c in conns if c["kind"] == "sqlite")


def q(client, headers, conn_id, sql, **extra):
    return client.post("/api/query/execute", json={"connection_id": conn_id, "sql": sql, **extra}, headers=headers)
