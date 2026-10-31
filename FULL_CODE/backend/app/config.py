"""Runtime configuration. All secrets come from the environment or from files under
data/secrets (git-ignored). Nothing secret is ever returned by the API."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]  # FULL_CODE/
REPO_DIR = ROOT_DIR.parent  # repository root (holds .env, data/, Datasets/)


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win; repo-root .env
    is read first, then FULL_CODE/.env."""
    for env_file in (REPO_DIR / ".env", ROOT_DIR / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


class Settings(BaseModel):
    data_dir: Path
    dataset_dir: Path
    meta_db_path: Path
    targets_dir: Path
    uploads_dir: Path
    secrets_dir: Path
    session_hours: int = 8
    max_result_rows: int = 500
    query_timeout_ms: int = 5000
    max_upload_bytes: int = 5 * 1024 * 1024
    upload_retention_minutes: int = 60
    min_aggregate_group: int = 5
    allowed_db_hosts: list[str]
    hmac_key_id: str = "k1"
    antiword_path: str | None = None
    cors_origins: list[str]
    environment: str = "demo"


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("SENTINEL_DATA_DIR", REPO_DIR / "data")).resolve()
    s = Settings(
        data_dir=data_dir,
        dataset_dir=Path(os.environ.get("SENTINEL_DATASET_DIR", REPO_DIR / "Datasets")).resolve(),
        meta_db_path=data_dir / "sentinel_meta.db",
        targets_dir=data_dir / "targets",
        uploads_dir=data_dir / "uploads",
        secrets_dir=data_dir / "secrets",
        session_hours=int(os.environ.get("SENTINEL_SESSION_HOURS", 8)),
        max_result_rows=int(os.environ.get("SENTINEL_MAX_ROWS", 500)),
        query_timeout_ms=int(os.environ.get("SENTINEL_QUERY_TIMEOUT_MS", 5000)),
        max_upload_bytes=int(os.environ.get("SENTINEL_MAX_UPLOAD_BYTES", 5 * 1024 * 1024)),
        upload_retention_minutes=int(os.environ.get("SENTINEL_UPLOAD_RETENTION_MIN", 60)),
        min_aggregate_group=int(os.environ.get("SENTINEL_MIN_GROUP_SIZE", 5)),
        allowed_db_hosts=[
            h.strip().lower()
            for h in os.environ.get("SENTINEL_ALLOWED_DB_HOSTS", "localhost,127.0.0.1").split(",")
            if h.strip()
        ],
        hmac_key_id=os.environ.get("SENTINEL_HMAC_KEY_ID", "k1"),
        antiword_path=os.environ.get("SENTINEL_ANTIWORD_PATH") or None,
        cors_origins=[
            o.strip()
            for o in os.environ.get(
                "SENTINEL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ],
        environment=os.environ.get("SENTINEL_ENV", "demo"),
    )
    for d in (s.data_dir, s.targets_dir, s.uploads_dir, s.secrets_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


def secret_file(file_name: str, create: Callable[[], bytes]) -> bytes:
    """Read a server-side secret (key material) from data/secrets, creating it on first use."""
    path = get_settings().secrets_dir / file_name
    if not path.exists():
        path.write_bytes(create())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_bytes()


def _secret_from_env_or_file(env_name: str, file_name: str, nbytes: int = 32) -> bytes:
    """Read a hex secret from the environment, or create one in data/secrets on first use."""
    value = os.environ.get(env_name)
    if value:
        return bytes.fromhex(value)
    return bytes.fromhex(secret_file(file_name, lambda: secrets.token_hex(nbytes).encode()).decode().strip())


@lru_cache
def hmac_key() -> bytes:
    """Pseudonymisation key. Server-side only; never logged or serialised."""
    return _secret_from_env_or_file("SENTINEL_HMAC_KEY", "hmac.key")


@lru_cache
def credential_key() -> bytes:
    """Key used to encrypt stored database passwords (Fernet, 32 raw bytes)."""
    return _secret_from_env_or_file("SENTINEL_CREDENTIAL_KEY", "credential.key")
