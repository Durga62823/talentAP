"""Official TalentAP Mega Hackathon 2026 B1 dataset (Saffron Bank Ltd, synthetic).

The dataset itself is NOT part of this repository. It is read from SENTINEL_DATASET_DIR
(default: <repo>/Datasets), exactly as supplied by the organisers. Nothing here generates or
alters records: SQLite is copied from the official .db, MySQL/PostgreSQL are loaded by
executing the official schema + data scripts statement by statement.

Safety rules implemented here:
  * row counts are verified against the official figures after every load
  * an existing `saffron_bank` MySQL database is never dropped. If it holds tables it is
    only replaced with --replace, only when every table in it is one of the nine official
    tables, and only after those tables are moved (RENAME TABLE, reversible) into a
    timestamped backup database
  * the application connects with a separate least-privilege account (SELECT on
    saffron_bank; full rights only on the separate saffron_imports schema used by
    reviewed CSV imports)"""
from __future__ import annotations

import csv
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config import get_settings

TABLES = [
    "branches", "customers", "kyc_records", "international_customers", "accounts",
    "cards", "transactions", "support_tickets", "loan_applications",
]
# Official row counts from the dataset README (129,260 rows in total).
EXPECTED_COUNTS = {
    "branches": 60, "customers": 5000, "kyc_records": 5400, "international_customers": 300,
    "accounts": 8000, "cards": 6000, "transactions": 100000, "support_tickets": 3000,
    "loan_applications": 1500,
}
assert sum(EXPECTED_COUNTS.values()) == 129_260

SQLITE_TARGET = "saffron_bank.db"
MYSQL_DB = "saffron_bank"
MYSQL_IMPORT_DB = "saffron_imports"
MYSQL_APP_USER = "sentinel_app"


class DatasetError(Exception):
    pass


def dataset_dir() -> Path:
    return get_settings().dataset_dir


def official_file(*parts: str) -> Path:
    p = dataset_dir().joinpath(*parts)
    if not p.exists():
        raise DatasetError(
            f"Official dataset file not found: {p}. Place the organisers' B1 pack in "
            f"{dataset_dir()} or set SENTINEL_DATASET_DIR."
        )
    return p


def dataset_available() -> bool:
    return (dataset_dir() / "sql" / "sqlite" / "saffron_bank.db").exists()


def demo_users() -> list[dict[str, str]]:
    """Official sample users (data/users.csv). Roles are lower-cased to match RBAC role names."""
    with official_file("data", "users.csv").open(encoding="utf-8", newline="") as f:
        return [{**row, "role": row["role"].strip().lower()} for row in csv.DictReader(f)]


def sqlite_counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLES}
    finally:
        con.close()


def verify_counts(counts: dict[str, int]) -> None:
    bad = {t: (counts.get(t), n) for t, n in EXPECTED_COUNTS.items() if counts.get(t) != n}
    if bad:
        raise DatasetError("Row counts do not match the official dataset: " +
                           ", ".join(f"{t} {got} != {exp}" for t, (got, exp) in bad.items()))


def install_sqlite_target() -> dict[str, int]:
    """Copy the official SQLite database into data/targets (the shipped file is never
    modified). Uses the SQLite backup API so an existing copy is replaced in place, which
    also works on Windows while read-only handles exist."""
    src_path = official_file("sql", "sqlite", "saffron_bank.db")
    verify_counts(sqlite_counts(src_path))
    dst_path = get_settings().targets_dir / SQLITE_TARGET
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    counts = sqlite_counts(dst_path)
    verify_counts(counts)
    return counts


# ------------------------------------------------------------------ SQL script execution ---

def split_sql(text: str) -> Iterator[str]:
    """Split a SQL script into statements. Handles '...' literals with '' escaping (as used
    by the official dumps), "..." / `...` identifiers, -- line comments and newlines inside
    string literals."""
    buf: list[str] = []
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                if quote == "'" and i + 1 < n and text[i + 1] == "'":
                    buf.append("'")
                    i += 1
                else:
                    quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                yield stmt
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        yield tail


def mysql_admin_params() -> dict:
    import os

    user = os.environ.get("SENTINEL_MYSQL_ADMIN_USER")
    password = os.environ.get("SENTINEL_MYSQL_ADMIN_PASSWORD")
    if not user or password is None:
        raise DatasetError("Set SENTINEL_MYSQL_ADMIN_USER and SENTINEL_MYSQL_ADMIN_PASSWORD in .env (used only by the importer)")
    return {
        "host": os.environ.get("SENTINEL_MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("SENTINEL_MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
    }


def mysql_app_password_file() -> Path:
    return get_settings().secrets_dir / "mysql_app.pw"


def import_mysql(replace: bool = False, log=print) -> dict[str, int]:
    import pymysql

    params = mysql_admin_params()
    con = pymysql.connect(**params, charset="utf8mb4", autocommit=True, client_flag=0)
    try:
        cur = con.cursor()
        cur.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (MYSQL_DB,))
        exists = cur.fetchone() is not None
        if exists:
            cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (MYSQL_DB,))
            present = sorted(r[0] for r in cur.fetchall())
            unexpected = [t for t in present if t not in TABLES]
            if unexpected:
                raise DatasetError(f"`{MYSQL_DB}` contains tables that are not part of the official dataset "
                                   f"({', '.join(unexpected)}). Refusing to touch it.")
            if present and not replace:
                raise DatasetError(f"`{MYSQL_DB}` already contains {len(present)} official tables. "
                                   "Re-run with --replace to back them up and reload.")
            if present:
                backup = f"{MYSQL_DB}_backup_{datetime.now():%Y%m%d_%H%M%S}"
                cur.execute(f"CREATE DATABASE `{backup}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
                cur.execute("SET FOREIGN_KEY_CHECKS = 0")
                cur.execute("RENAME TABLE " + ", ".join(f"`{MYSQL_DB}`.`{t}` TO `{backup}`.`{t}`" for t in present))
                cur.execute("SET FOREIGN_KEY_CHECKS = 1")
                log(f"Existing tables moved to backup database `{backup}` (reversible with RENAME TABLE)")
        for name in ("01_schema.sql", "02_data.sql"):
            path = official_file("sql", "mysql", name)
            log(f"Executing official {path.name} ...")
            for stmt in split_sql(path.read_text(encoding="utf-8")):
                cur.execute(stmt)
        cur.execute(f"USE `{MYSQL_DB}`")
        counts = {}
        for t in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM `{t}`")
            counts[t] = cur.fetchone()[0]
        verify_counts(counts)

        # Least-privilege application account.
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_IMPORT_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        pw_file = mysql_app_password_file()
        if pw_file.exists():
            app_pw = pw_file.read_text(encoding="utf-8").strip()
        else:
            app_pw = secrets.token_urlsafe(24)
            pw_file.write_text(app_pw, encoding="utf-8")
        cur.execute("CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s", (MYSQL_APP_USER, app_pw))
        cur.execute("ALTER USER %s@'localhost' IDENTIFIED BY %s", (MYSQL_APP_USER, app_pw))
        cur.execute(f"GRANT SELECT ON `{MYSQL_DB}`.* TO %s@'localhost'", (MYSQL_APP_USER,))
        cur.execute(f"GRANT SELECT, CREATE, INSERT, DROP ON `{MYSQL_IMPORT_DB}`.* TO %s@'localhost'", (MYSQL_APP_USER,))
        log(f"Application account {MYSQL_APP_USER}@localhost: SELECT on {MYSQL_DB}, write only on {MYSQL_IMPORT_DB} "
            f"(password stored in {pw_file})")
        return counts
    finally:
        con.close()


def mysql_app_configured() -> bool:
    import os

    return mysql_app_password_file().exists() or bool(os.environ.get("SENTINEL_MYSQL_APP_PASSWORD"))


def mysql_app_password() -> str:
    import os

    if os.environ.get("SENTINEL_MYSQL_APP_PASSWORD"):
        return os.environ["SENTINEL_MYSQL_APP_PASSWORD"]
    return mysql_app_password_file().read_text(encoding="utf-8").strip()


def import_postgres(dsn_params: dict, log=print) -> dict[str, int]:
    """Load the official PostgreSQL scripts into an existing, empty database."""
    import psycopg

    with psycopg.connect(**dsn_params, autocommit=True) as con:
        present = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()]
        unexpected = [t for t in present if t not in TABLES]
        if unexpected:
            raise DatasetError(f"Target database has non-dataset tables ({', '.join(unexpected)}); refusing.")
        for name in ("01_schema.sql", "02_data.sql"):
            path = official_file("sql", "postgres", name)
            log(f"Executing official {path.name} ...")
            for stmt in split_sql(path.read_text(encoding="utf-8")):
                con.execute(stmt)
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLES}
    verify_counts(counts)
    return counts
