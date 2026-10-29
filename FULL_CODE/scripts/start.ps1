# One-command local demo (Windows PowerShell). Run from the repository root.
# Requires the official dataset in .\Datasets (see README). No Docker needed.
$ErrorActionPreference = "Stop"
$be = "FULL_CODE/backend"; $fe = "FULL_CODE/frontend"
if (-not (Test-Path "$be/.venv")) { python -m venv "$be/.venv" }
& "$be/.venv/Scripts/python" -m pip install -q -r "$be/requirements.txt"
Push-Location $be; .venv/Scripts/python -m app.cli verify-dataset; $ok = $LASTEXITCODE; Pop-Location
if ($ok -ne 0) { Write-Error "Official dataset missing or incomplete - see README"; exit 1 }
if (-not (Test-Path "$fe/node_modules")) { Push-Location $fe; npm install --no-audit --no-fund; Pop-Location }
Push-Location $fe; npm run build; Pop-Location
& "$be/.venv/Scripts/python" -m uvicorn app.main:app --app-dir $be --host 127.0.0.1 --port 8000
