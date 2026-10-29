"""Build upload-demo files from the OFFICIAL Saffron Bank CSVs (values copied unchanged).

Writes to <repo>/data/samples/ (git-ignored - dataset excerpts must not be committed):
  saffron_customers_extract.csv   first 50 customers.csv records (CSV import demo)
  saffron_ticket_notes.txt        ticket_text + notes of the first 40 tickets (TXT scan demo)
  saffron_ticket_digest.docx      the same tickets as paragraphs + a table (DOCX scan demo)
  saffron_ticket_digest.doc       legacy Word copy, only if Microsoft Word is available (Windows)

Usage (from FULL_CODE/backend):  .venv/Scripts/python ../scripts/make_samples.py
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "FULL_CODE" / "backend"))

from app.saffron import official_file  # noqa: E402

OUT = REPO / "data" / "samples"


def read_rows(name: str, limit: int) -> tuple[list[str], list[list[str]]]:
    with official_file("data", "csv", f"{name}.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= limit:
                break
    return header, rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    header, rows = read_rows("customers", 50)
    with (OUT / "saffron_customers_extract.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    th, tickets = read_rows("support_tickets", 40)
    idx = {c: th.index(c) for c in ("ticket_id", "category", "ticket_text", "notes")}
    lines = ["Saffron Bank - support ticket extract (official synthetic dataset)", ""]
    for t in tickets:
        lines.append(f"[{t[idx['ticket_id']]}] {t[idx['category']]}: {t[idx['ticket_text']]}")
        if t[idx["notes"]]:
            lines.append(f"    agent note: {t[idx['notes']]}")
    (OUT / "saffron_ticket_notes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    import docx

    d = docx.Document()
    d.add_heading("Saffron Bank - support ticket digest", 1)
    d.add_paragraph("Extract of the official TalentAP 2026 B1 synthetic dataset.")
    d.add_heading("Tickets", 2)
    for t in tickets[:25]:
        d.add_paragraph(f"{t[idx['ticket_id']]} ({t[idx['category']]}): {t[idx['ticket_text']]}")
    d.add_heading("Agent notes", 2)
    noted = [t for t in tickets if t[idx["notes"]]][:10]
    table = d.add_table(rows=len(noted), cols=2)
    for r, t in enumerate(noted):
        table.cell(r, 0).text = t[idx["ticket_id"]]
        table.cell(r, 1).text = t[idx["notes"]]
    docx_path = OUT / "saffron_ticket_digest.docx"
    d.save(docx_path)

    doc_path = OUT / "saffron_ticket_digest.doc"
    if sys.platform == "win32" and shutil.which("powershell"):
        ps = (
            "$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
            f"$d = $w.Documents.Open('{docx_path}'); $d.SaveAs([ref]'{doc_path}', [ref]0); $d.Close(); $w.Quit()"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
        print("legacy .doc:", "created" if doc_path.exists() else f"not created (Word unavailable: rc={res.returncode})")
    else:
        print("legacy .doc: skipped (needs Microsoft Word on Windows)")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name:34} {p.stat().st_size:>8} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
