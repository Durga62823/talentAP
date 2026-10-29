#!/usr/bin/env bash
# One-command local demo (macOS/Linux). Run from the repository root.
# Requires the official dataset in ./Datasets (see README). No Docker needed.
set -euo pipefail
BE=FULL_CODE/backend; FE=FULL_CODE/frontend
[ -d $BE/.venv ] || python3 -m venv $BE/.venv
$BE/.venv/bin/python -m pip install -q -r $BE/requirements.txt
(cd $BE && .venv/bin/python -m app.cli verify-dataset)
[ -d $FE/node_modules ] || (cd $FE && npm install --no-audit --no-fund)
(cd $FE && npm run build)
exec $BE/.venv/bin/python -m uvicorn app.main:app --app-dir $BE --host 127.0.0.1 --port 8000
