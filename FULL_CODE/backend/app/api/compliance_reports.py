from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit
from .. import compliance_reporter as reporter
from ..metadb import get_db
from ..security import Principal, require
from .common import corr

router = APIRouter(prefix="/api/compliance/reports", tags=["compliance"])


class GenerateIn(BaseModel):
    framework: Literal["DPDP", "RBI", "PCI_DSS"]
    format: Literal["json", "pdf", "csv"] = "json"


class VerifyIn(BaseModel):
    dossier: dict[str, Any]
    certificate: dict[str, Any]


@router.get("/summary")
def summary(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return reporter.summary(db, p)


@router.get("/public-key")
def public_key(p: Principal = Depends(require("audit:read"))):
    return reporter.public_key_info()


@router.post("/generate")
def generate(body: GenerateIn, request: Request, p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    dossier = reporter.build_dossier(db, body.framework, p)
    cert = reporter.seal(dossier)
    ev = audit.record(db, p, action="compliance_report_generate", outcome="success", correlation_id=corr(request),
                      details={"framework": body.framework, "format": body.format, "status": dossier["status"],
                               "dossier_sha256": cert["dossier_sha256"], "key_id": cert["key_id"]})
    # The audit anchor is not part of the signed digest: it is created by signing the dossier.
    cert = cert | {"audit_event_id": ev.id, "audit_seq": str(ev.seq), "audit_entry_hash": ev.entry_hash}
    headers = {"X-Dossier-SHA256": cert["dossier_sha256"], "X-Dossier-Signature": cert["signature"], "X-Audit-Event-Id": ev.id}
    stem = f"dreamguard-{body.framework.lower().replace('_', '-')}-dossier-{cert['dossier_sha256'][:12]}"
    if body.format == "json":
        return JSONResponse({"dossier": dossier, "certificate": cert}, headers=headers)
    if body.format == "csv":
        content, media = reporter.to_csv(dossier, cert), "text/csv; charset=utf-8"
    else:
        content, media = reporter.to_pdf(dossier, cert), "application/pdf"
    headers["Content-Disposition"] = f'attachment; filename="{stem}.{body.format}"'
    return Response(content, media_type=media, headers=headers)


@router.post("/verify")
def verify(body: VerifyIn, p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    """Recompute the dossier digest, check the Ed25519 signature and find its generation event."""
    return reporter.verify(db, body.dossier, body.certificate)
