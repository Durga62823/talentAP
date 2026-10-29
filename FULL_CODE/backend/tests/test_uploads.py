import io
import zipfile

import docx

from conftest import q
from app.config import get_settings
from app.uploads import OLE_MAGIC

CSV = (
    "Customer Name,E-mail,Phone,Card Number,Balance,Segment,Customer Name\n"
    "Asha Verma,asha.verma@inbox.example,+1-202-555-0143,4111111111111111,1520.75,retail,dup1\n"
    "José Núñez,jose.nunez@quickmail.example,+1-303-555-0188,5555555555554444,98000,premier,dup2\n"
    "Kenji Tanaka,kenji.t@postmail.example,+1-404-555-0101,378282246310005,15.00,retail,dup3\n"
    "broken,row\n"
    "Lena Varga,,+1-505-555-0110,6011111111111117,,business,dup4\n"
    "Omar Brennan,omar.b@inbox.example,+1-606-555-0122,4000056655665556,7000,retail,dup5\n"
)


def upload(client, h, name, data, mime):
    return client.post("/api/uploads", files={"file": (name, data, mime)}, headers=h)


def test_csv_scan_preview_import_and_masked_access(client, H, conn_id):
    r = upload(client, H["admin"], "crm_export.csv", CSV.encode(), "text/csv")
    assert r.status_code == 201, r.text
    up = r.json()
    res = up["result"]
    assert up["status"] == "scanned" and res["row_count"] == 5 and res["skipped_count"] == 1
    names = [c["name"] for c in res["columns"]]
    assert names == ["customer_name", "e_mail", "phone", "card_number", "balance", "segment", "customer_name_2"]
    cats = {c["name"]: c["category"] for c in res["columns"]}
    assert cats["e_mail"] == "EMAIL" and cats["card_number"] == "CREDIT_CARD" and cats["phone"] == "PHONE"
    # preview is masked
    flat = str(res["preview"])
    assert "asha.verma@inbox.example" not in flat and "4111111111111111" not in flat
    assert up["temp_file_retained"] is True

    r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": conn_id, "table_name": "crm_contacts",
                                                            "columns": [{"name": "segment", "category": "NONE"}]}, headers=H["admin"])
    assert r.status_code == 200, r.text
    imp = r.json()
    assert imp["table"] == "imp_crm_contacts" and imp["rows_imported"] == 5 and imp["temp_file_retained"] is False
    assert not list(get_settings().uploads_dir.glob(f"{up['id']}*"))

    sql = "SELECT customer_name, e_mail, card_number, balance FROM imp_crm_contacts"
    sup = q(client, H["support"], conn_id, sql).json()
    ana = q(client, H["analyst"], conn_id, sql).json()
    adm = q(client, H["admin"], conn_id, sql).json()
    assert sup["rows"][0][0] == "A*** V****" and sup["rows"][0][1] == "a***@inbox.example"
    assert sup["rows"][0][2] == "4111-XXXX-XXXX-1111"
    assert ana["rows"][0][1].startswith("hm_k1_") and ana["rows"][0][3] == "[REDACTED]"
    assert adm["rows"][0][1] == "asha.verma@inbox.example"
    # same HMAC key as database-native data -> same pseudonym for the same email
    assert "asha.verma" not in str(ana)


def test_import_rejects_unsafe_table_names(client, H, conn_id):
    up = upload(client, H["admin"], "x.csv", b"a,b\n1,2\n", "text/csv").json()
    for bad in ["customers; DROP TABLE customers", "Robert'); --", "../x", "CamelCase"]:
        r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": conn_id, "table_name": bad}, headers=H["admin"])
        assert r.status_code == 422
    r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": conn_id, "table_name": "crm_contacts"}, headers=H["admin"])
    assert r.status_code == 400 and "already exists" in r.text


def test_csv_values_are_data_not_sql(client, H, conn_id):
    evil = b"note,amount\n\"'); DROP TABLE customers; --\",1\n=HYPERLINK(\"http://x\"),2\n"
    up = upload(client, H["admin"], "evil.csv", evil, "text/csv").json()
    r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": conn_id, "table_name": "evil_notes"}, headers=H["admin"])
    assert r.status_code == 200
    assert q(client, H["admin"], conn_id, "SELECT COUNT(*) FROM customers").json()["rows"][0][0] == 5000
    rows = q(client, H["admin"], conn_id, "SELECT note FROM imp_evil_notes").json()["rows"]
    assert rows[0][0].startswith("');")


def test_csv_formula_injection_neutralised_in_exports(client, H):
    from app.api.common import csv_safe

    assert csv_safe("=1+1") == "'=1+1" and csv_safe("@SUM(A1)") == "'@SUM(A1)" and csv_safe("-2") == "'-2"
    r = client.get("/api/audit/export.csv", headers=H["admin"])
    assert r.status_code == 200
    for line in r.text.splitlines()[1:]:
        for cell in line.split(","):
            assert not cell.startswith(("=", "+", "@"))


def test_invalid_encoding_and_binary(client, H):
    r = upload(client, H["admin"], "latin.csv", "name\nJos\xe9\n".encode("latin-1"), "text/csv")
    assert r.status_code == 400 and "UTF-8" in r.text
    r = upload(client, H["admin"], "bin.txt", b"MZ\x90\x00binary", "text/plain")
    assert r.status_code == 400


def test_oversized_and_wrong_types(client, H):
    big = b"a" * (get_settings().max_upload_bytes + 10)
    assert upload(client, H["admin"], "big.txt", big, "text/plain").status_code == 400
    assert upload(client, H["admin"], "x.exe", b"MZ", "application/octet-stream").status_code == 400
    assert upload(client, H["admin"], "fake.docx", b"just text", "application/octet-stream").status_code == 400
    assert upload(client, H["admin"], "empty.txt", b"", "text/plain").status_code == 400
    assert upload(client, H["admin"], "mime.csv", b"a,b\n1,2", "image/png").status_code == 400


def test_txt_findings_and_cleanup(client, H):
    text = ("Ticket 4411\nCustomer emailed from asha@inbox.example about card 4111 1111 1111 1111.\n"
            "Callback on +1-202-555-0143. SSN on file 123-45-6789.\n")
    r = upload(client, H["admin"], "notes.txt", text.encode(), "text/plain")
    up = r.json()
    res = up["result"]
    assert up["status"] == "scanned" and res["category_counts"] == {"EMAIL": 1, "CREDIT_CARD": 1, "PHONE": 1, "NATIONAL_ID": 1}
    assert {f["location"] for f in res["findings"]} == {"line 2", "line 3"}
    assert "asha@inbox.example" not in r.text and "123-45-6789" not in r.text and "4111 1111 1111 1111" not in r.text
    assert up["temp_file_retained"] is False
    r = client.post(f"/api/uploads/{up['id']}/import", json={"connection_id": "x", "table_name": "t"}, headers=H["admin"])
    assert r.status_code in (400, 404)


def _docx_bytes() -> bytes:
    d = docx.Document()
    d.add_heading("Escalation summary", 1)
    d.add_paragraph("Customer Asha Verma (asha@inbox.example) disputed a charge.")
    d.add_paragraph("Card on file: 5555 5555 5555 4444")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Phone"
    t.cell(0, 1).text = "+1-202-555-0143"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_docx_extraction(client, H):
    r = upload(client, H["admin"], "escalation.docx", _docx_bytes(),
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    up = r.json()
    assert up["status"] == "scanned", up
    res = up["result"]
    assert res["category_counts"] == {"EMAIL": 1, "CREDIT_CARD": 1, "PHONE": 1}
    locs = {f["location"] for f in res["findings"]}
    assert any("section: Escalation summary" in loc for loc in locs) and "table 1, row 1, cell 2" in locs
    assert "5555 5555 5555 4444" not in r.text


def test_malformed_docx_and_macro_docx(client, H):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("random.txt", "hello")
    assert upload(client, H["admin"], "bad.docx", buf.getvalue(), "application/octet-stream").status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("word/document.xml", "<x/>")
        z.writestr("word/vbaProject.bin", "macro")
    r = upload(client, H["admin"], "macro.docx", buf.getvalue(), "application/octet-stream")
    assert r.status_code == 400 and "Macro" in r.text


def test_decompression_bomb_rejected(client, H):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("word/document.xml", "A" * 60_000_000)
    r = upload(client, H["admin"], "bomb.docx", buf.getvalue(), "application/octet-stream")
    assert r.status_code == 400 and ("ratio" in r.text or "size" in r.text)


def test_legacy_doc_reports_honestly(client, H):
    # An OLE container that is not a Word document must never report success.
    r = upload(client, H["admin"], "legacy.doc", OLE_MAGIC + b"\x00" * 600, "application/msword")
    up = r.json()
    assert r.status_code == 201 and up["status"] == "failed"
    assert ".docx" in up["detail"]
    assert up["temp_file_retained"] is False


def test_delete_upload_removes_temp_file(client, H):
    up = upload(client, H["admin"], "temp.csv", b"email\nz@inbox.example\n", "text/csv").json()
    assert list(get_settings().uploads_dir.glob(f"{up['id']}.bin"))
    assert client.delete(f"/api/uploads/{up['id']}", headers=H["admin"]).status_code == 200
    assert not list(get_settings().uploads_dir.glob(f"{up['id']}.bin"))
    assert client.get(f"/api/uploads/{up['id']}", headers=H["admin"]).json()["result"] is None


def test_expired_upload_is_purged(client, H):
    from datetime import timedelta

    from app.metadb import SessionLocal, Upload, utcnow
    from app.uploads import purge_expired

    up = upload(client, H["admin"], "old.csv", b"a\n1\n", "text/csv").json()
    db = SessionLocal()
    row = db.get(Upload, up["id"])
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert purge_expired(db) >= 1
    db.close()
    assert not list(get_settings().uploads_dir.glob(f"{up['id']}.bin"))


def test_legacy_doc_real_extraction(client, H):
    """Runs only where antiword is installed (verified on Windows with Git-for-Windows antiword)."""
    import pytest

    from app.uploads import antiword_binary

    from app.config import REPO_DIR

    sample = REPO_DIR / "data" / "samples" / "saffron_ticket_digest.doc"  # generated by scripts/make_samples.py
    if not antiword_binary() or not sample.exists():
        pytest.skip("antiword or generated sample .doc not available")
    r = upload(client, H["admin"], "saffron_ticket_digest.doc", sample.read_bytes(), "application/msword")
    up = r.json()
    assert up["status"] == "scanned", up
    assert up["result"]["extractor"] == "antiword"
    counts = up["result"]["category_counts"]
    assert counts.get("CREDIT_CARD", 0) >= 1 and counts.get("PHONE", 0) >= 1
