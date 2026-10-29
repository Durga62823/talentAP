"""Target database adapters. Each registered connection is addressed by a stable id; the
frontend never sees connection strings or passwords.

Dialect-specific behaviour (read-only sessions, timeouts, catalog names) lives here."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import URL, Engine

from .config import get_settings
from .metadb import DbConnection
from .security import decrypt_secret

SQLITE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}\.(db|sqlite|sqlite3)$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "sqlite_master", "sqlite_temp_master", "sqlite_schema", "temp",
                  "mysql", "performance_schema", "sys"}


class ConnectorError(Exception):
    """Safe-to-display error. Never include credentials or internal driver output."""


class QueryTimeout(ConnectorError):
    pass


def validate_sqlite_file(name: str) -> Path:
    if not SQLITE_NAME_RE.fullmatch(name or ""):
        raise ConnectorError("SQLite file must be a plain file name like 'bank.db' inside the data/targets directory")
    base = get_settings().targets_dir.resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise ConnectorError("SQLite path escapes the allowed directory")
    return path


def validate_pg_host(host: str) -> str:
    """SSRF guard: only explicitly allow-listed hosts (SENTINEL_ALLOWED_DB_HOSTS)."""
    h = (host or "").strip().lower()
    if not h or len(h) > 253 or not re.fullmatch(r"[a-z0-9.\-:\[\]]+", h):
        raise ConnectorError("Invalid host")
    allowed = get_settings().allowed_db_hosts
    if h not in allowed:
        raise ConnectorError(f"Host '{h}' is not in the server allow-list (SENTINEL_ALLOWED_DB_HOSTS)")
    try:
        ip = ipaddress.ip_address(h.strip("[]"))
        if ip.is_multicast or ip.is_unspecified or ip.is_reserved or ip.is_link_local:
            raise ConnectorError("Host address class not permitted")
    except ValueError:
        pass
    return h


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool


class TargetAdapter:
    kind: str
    sqlglot_dialect: str
    default_schema: str
    import_schema: str | None = None  # where reviewed CSV imports are created (default_schema if None)

    def __init__(self, conn: DbConnection):
        self.conn = conn
        self.allowed_schemas = [s.lower() for s in (conn.allowed_schemas or [self.default_schema])]
        self._read_engine: Engine | None = None
        self._write_engine: Engine | None = None

    # --- engines -------------------------------------------------------------------------
    def read_engine(self) -> Engine:
        raise NotImplementedError

    def write_engine(self) -> Engine:
        raise NotImplementedError

    def dispose(self) -> None:
        for e in (self._read_engine, self._write_engine):
            if e is not None:
                e.dispose()

    # --- metadata ------------------------------------------------------------------------
    def test(self) -> str:
        with self.read_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return "ok"

    def list_tables(self) -> list[tuple[str, str]]:
        insp = inspect(self.read_engine())
        out = []
        for schema in self.allowed_schemas:
            if schema in SYSTEM_SCHEMAS:
                continue
            for t in insp.get_table_names(schema=self._schema_arg(schema)):
                if t.startswith("sqlite_"):
                    continue
                out.append((schema, t))
        return sorted(out)

    def columns(self, schema: str, table: str) -> list[ColumnInfo]:
        self._check_scope(schema, table)
        insp = inspect(self.read_engine())
        pk = set((insp.get_pk_constraint(table, schema=self._schema_arg(schema)) or {}).get("constrained_columns") or [])
        return [
            ColumnInfo(c["name"], str(c["type"]), bool(c.get("nullable", True)), c["name"] in pk)
            for c in insp.get_columns(table, schema=self._schema_arg(schema))
        ]

    def row_count(self, schema: str, table: str) -> int:
        t = self._table(schema, table)
        from sqlalchemy import func

        with self.read_engine().connect() as c:
            return int(c.execute(select(func.count()).select_from(t)).scalar() or 0)

    def sample(self, schema: str, table: str, column_names: list[str], limit: int) -> dict[str, list[Any]]:
        """Bounded RANDOM sample for classification (the first N rows of a table are often
        one batch / channel and hide PII that appears later). Values stay in memory only."""
        from sqlalchemy import func

        t = self._table(schema, table)
        cols = [t.c[name] for name in column_names]
        rnd = func.rand() if self.kind == "mysql" else func.random()
        with self.read_engine().connect() as c:
            rows = c.execute(select(*cols).order_by(rnd).limit(limit)).fetchall()
        return {name: [r[i] for r in rows] for i, name in enumerate(column_names)}

    def _schema_arg(self, schema: str) -> str | None:
        return schema

    def _check_scope(self, schema: str, table: str) -> None:
        if schema.lower() not in self.allowed_schemas or schema.lower() in SYSTEM_SCHEMAS:
            raise ConnectorError("Schema not permitted for this connection")
        if not IDENT_RE.fullmatch(table) and not re.fullmatch(r"[A-Za-z0-9_ \-]{1,128}", table):
            raise ConnectorError("Invalid table name")

    def _table(self, schema: str, table: str) -> Table:
        self._check_scope(schema, table)
        md = MetaData()
        return Table(table, md, autoload_with=self.read_engine(), schema=self._schema_arg(schema))

    # --- protected execution ---------------------------------------------------------------
    def execute_readonly(self, sql: str, timeout_ms: int, max_rows: int) -> tuple[list[str], list[tuple[Any, ...]]]:
        raise NotImplementedError

    # --- integrity -------------------------------------------------------------------------
    def fingerprint(self, schema: str, table: str) -> tuple[str, int]:
        """SHA-256 over a canonical serialisation of every row, ordered by all columns."""
        t = self._table(schema, table)
        h = hashlib.sha256()
        h.update(json.dumps([c.name for c in t.columns]).encode())
        n = 0
        with self.read_engine().connect() as c:
            result = c.execution_options(stream_results=True).execute(select(t).order_by(*t.columns))
            for row in result:
                h.update(json.dumps([_canon(v) for v in row], separators=(",", ":")).encode())
                h.update(b"\n")
                n += 1
        return h.hexdigest(), n

    # --- import ----------------------------------------------------------------------------
    def create_and_load(self, table: str, columns: list[tuple[str, str]], rows: list[list[Any]]) -> int:
        """Create a new table and insert rows with bound parameters (never string-built SQL)."""
        if not IDENT_RE.fullmatch(table):
            raise ConnectorError("Invalid destination table name")
        schema = self.import_schema or self.default_schema
        md = MetaData()
        type_map = {"INTEGER": Integer, "REAL": Float, "TEXT": Text}
        t = Table(
            table,
            md,
            Column("_row_id", Integer, primary_key=True, autoincrement=True),
            *[Column(name, type_map.get(typ, Text)) for name, typ in columns],
            schema=self._schema_arg(schema),
        )
        eng = self.write_engine()
        if inspect(eng).has_table(table, schema=self._schema_arg(schema)):
            raise ConnectorError(f"Table '{table}' already exists; choose another name")
        with eng.begin() as c:
            t.create(c)
            if rows:
                names = [n for n, _ in columns]
                c.execute(t.insert(), [dict(zip(names, r)) for r in rows])
        return len(rows)


def _canon(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v.normalize())
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(v)).hexdigest()
    return v


class SQLiteAdapter(TargetAdapter):
    kind = "sqlite"
    sqlglot_dialect = "sqlite"
    default_schema = "main"

    def __init__(self, conn: DbConnection):
        super().__init__(conn)
        self.path = validate_sqlite_file(conn.params.get("file", ""))
        self.allowed_schemas = ["main"]

    def _schema_arg(self, schema: str) -> str | None:
        return None

    def read_engine(self) -> Engine:
        if self._read_engine is None:
            if not self.path.exists():
                raise ConnectorError("SQLite database file not found")
            uri = f"file:{self.path.as_posix()}?mode=ro"
            self._read_engine = create_engine(
                "sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False)
            )
        return self._read_engine

    def write_engine(self) -> Engine:
        if self._write_engine is None:
            self._write_engine = create_engine(f"sqlite:///{self.path.as_posix()}")
        return self._write_engine

    def execute_readonly(self, sql: str, timeout_ms: int, max_rows: int):
        eng = self.read_engine()
        with eng.connect() as c:
            raw = c.connection.dbapi_connection
            deadline = time.monotonic() + timeout_ms / 1000
            timed_out = threading.Event()

            def handler() -> int:
                if time.monotonic() > deadline:
                    timed_out.set()
                    return 1
                return 0

            raw.set_progress_handler(handler, 2000)
            try:
                cur = raw.cursor()
                cur.execute("PRAGMA query_only = ON")
                cur.execute(sql)
                names = [d[0] for d in cur.description or []]
                rows = cur.fetchmany(max_rows + 1)
                cur.close()
            except sqlite3.OperationalError as exc:
                if timed_out.is_set():
                    raise QueryTimeout(f"Query exceeded {timeout_ms} ms timeout") from exc
                raise ConnectorError("Query failed during execution") from exc
            finally:
                raw.set_progress_handler(None, 0)
        return names, [tuple(r) for r in rows]


class PostgresAdapter(TargetAdapter):
    kind = "postgresql"
    sqlglot_dialect = "postgres"
    default_schema = "public"

    def _url(self) -> URL:
        p = self.conn.params
        host = validate_pg_host(p.get("host", ""))
        port = int(p.get("port", 5432))
        if not 1 <= port <= 65535:
            raise ConnectorError("Invalid port")
        password = decrypt_secret(self.conn.secret_enc) if self.conn.secret_enc else None
        return URL.create(
            "postgresql+psycopg",
            username=p.get("username"),
            password=password,
            host=host,
            port=port,
            database=p.get("database"),
        )

    def _make(self) -> Engine:
        return create_engine(
            self._url(),
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=2,
            connect_args={"connect_timeout": 5, "application_name": "sentinelmask"},
            hide_parameters=True,
        )

    def read_engine(self) -> Engine:
        if self._read_engine is None:
            self._read_engine = self._make()
        return self._read_engine

    def write_engine(self) -> Engine:
        return self.read_engine()

    def execute_readonly(self, sql: str, timeout_ms: int, max_rows: int):
        import psycopg

        eng = self.read_engine()
        with eng.connect() as c:
            try:
                c.exec_driver_sql("SET TRANSACTION READ ONLY")
                c.exec_driver_sql(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                c.exec_driver_sql("SET LOCAL search_path = " + ", ".join(f'"{s}"' for s in self.allowed_schemas if IDENT_RE.fullmatch(s)))
                result = c.exec_driver_sql(sql)
                names = list(result.keys())
                rows = result.fetchmany(max_rows + 1)
                c.rollback()
            except Exception as exc:  # noqa: BLE001 - mapped to safe messages
                c.rollback()
                orig = getattr(exc, "orig", exc)
                if isinstance(orig, psycopg.errors.QueryCanceled):
                    raise QueryTimeout(f"Query exceeded {timeout_ms} ms timeout") from exc
                raise ConnectorError("Query failed during execution") from exc
        return names, [tuple(r) for r in rows]


class MySQLAdapter(TargetAdapter):
    """MySQL 8+/9 via PyMySQL. The database name plays the role of the schema."""

    kind = "mysql"
    sqlglot_dialect = "mysql"

    def __init__(self, conn: DbConnection):
        self.default_schema = (conn.params.get("database") or "saffron_bank").lower()
        super().__init__(conn)
        imp = (conn.params.get("import_database") or "").lower()
        self.import_schema = imp if imp and imp in self.allowed_schemas else None

    def _url(self) -> URL:
        p = self.conn.params
        host = validate_pg_host(p.get("host", ""))
        port = int(p.get("port", 3306))
        if not 1 <= port <= 65535:
            raise ConnectorError("Invalid port")
        password = decrypt_secret(self.conn.secret_enc) if self.conn.secret_enc else None
        return URL.create(
            "mysql+pymysql",
            username=p.get("username"),
            password=password,
            host=host,
            port=port,
            database=p.get("database"),
            query={"charset": "utf8mb4"},
        )

    def read_engine(self) -> Engine:
        if self._read_engine is None:
            self._read_engine = create_engine(
                self._url(),
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_size=3,
                max_overflow=2,
                connect_args={"connect_timeout": 5, "local_infile": False},
                hide_parameters=True,
            )
        return self._read_engine

    def write_engine(self) -> Engine:
        return self.read_engine()

    def execute_readonly(self, sql: str, timeout_ms: int, max_rows: int):
        import pymysql

        eng = self.read_engine()
        with eng.connect() as c:
            raw = c.connection.dbapi_connection
            cur = raw.cursor()
            try:
                cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
                cur.execute("START TRANSACTION READ ONLY")
                cur.execute(sql)
                names = [d[0] for d in cur.description or []]
                rows = cur.fetchmany(max_rows + 1)
            except pymysql.err.OperationalError as exc:
                raw.rollback()
                if exc.args and exc.args[0] in (3024, 1317):  # max execution time exceeded / interrupted
                    raise QueryTimeout(f"Query exceeded {timeout_ms} ms timeout") from exc
                raise ConnectorError("Query failed during execution") from exc
            except Exception as exc:  # noqa: BLE001 - mapped to safe messages
                raw.rollback()
                raise ConnectorError("Query failed during execution") from exc
            else:
                raw.rollback()
            finally:
                cur.close()
        return names, [tuple(r) for r in rows]


_cache: dict[str, TargetAdapter] = {}
_cache_lock = threading.Lock()


def get_adapter(conn: DbConnection) -> TargetAdapter:
    with _cache_lock:
        a = _cache.get(conn.id)
        if a is None:
            if conn.kind == "sqlite":
                a = SQLiteAdapter(conn)
            elif conn.kind == "postgresql":
                a = PostgresAdapter(conn)
            elif conn.kind == "mysql":
                a = MySQLAdapter(conn)
            else:
                raise ConnectorError("Unsupported database kind")
            _cache[conn.id] = a
        return a


def drop_adapter(conn_id: str) -> None:
    with _cache_lock:
        a = _cache.pop(conn_id, None)
    if a:
        a.dispose()


def clear_adapters() -> None:
    with _cache_lock:
        items = list(_cache.values())
        _cache.clear()
    for a in items:
        a.dispose()
