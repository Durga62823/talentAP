"""Command line (run from FULL_CODE/backend):

  python -m app.cli verify-dataset          check the official files and their row counts
  python -m app.cli reset                   rebuild app state on the official dataset (SQLite copy + scan)
  python -m app.cli import-mysql [--replace] load official MySQL scripts into `saffron_bank`
  python -m app.cli import-postgres --database saffron_bank --user postgres
  python -m app.cli verify-audit            recompute the audit hash chain
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(prog="sentinelmask", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-dataset", help="Verify the official dataset files and row counts")
    sub.add_parser("reset", help="Rebuild demo state on the official dataset")
    my = sub.add_parser("import-mysql", help="Load the official MySQL scripts (needs SENTINEL_MYSQL_ADMIN_* in .env)")
    my.add_argument("--replace", action="store_true",
                    help="If saffron_bank already holds the official tables, move them to a backup database and reload")
    pg = sub.add_parser("import-postgres", help="Load the official PostgreSQL scripts into an existing empty database")
    pg.add_argument("--host", default=os.environ.get("PGHOST", "localhost"))
    pg.add_argument("--port", type=int, default=int(os.environ.get("PGPORT", 5432)))
    pg.add_argument("--database", default=os.environ.get("PGDATABASE", "saffron_bank"))
    pg.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    sub.add_parser("verify-audit", help="Recompute the audit hash chain")
    args = ap.parse_args()

    from . import saffron

    try:
        if args.cmd == "verify-dataset":
            counts = saffron.sqlite_counts(saffron.official_file("sql", "sqlite", "saffron_bank.db"))
            saffron.verify_counts(counts)
            for name in ("01_schema.sql", "02_data.sql"):
                saffron.official_file("sql", "mysql", name)
            for t in saffron.TABLES:
                saffron.official_file("data", "csv", f"{t}.csv")
            print(json.dumps({"dataset_dir": str(saffron.dataset_dir()), "counts": counts, "total": sum(counts.values())}, indent=2))
        elif args.cmd == "reset":
            from .seed import reset_all

            print(json.dumps(reset_all(), indent=2))
        elif args.cmd == "import-mysql":
            counts = saffron.import_mysql(replace=args.replace)
            print(json.dumps({"mysql_rows": counts, "total": sum(counts.values())}, indent=2))
            print("Next: run `python -m app.cli reset` (or Settings > Reset) to register and scan the MySQL connection.")
        elif args.cmd == "import-postgres":
            counts = saffron.import_postgres({"host": args.host, "port": args.port, "dbname": args.database,
                                              "user": args.user, "password": os.environ.get("PGPASSWORD")})
            print(json.dumps({"postgres_rows": counts}, indent=2))
        elif args.cmd == "verify-audit":
            from .audit import verify_chain
            from .metadb import SessionLocal

            print(json.dumps(verify_chain(SessionLocal()), indent=2))
    except saffron.DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
