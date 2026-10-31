"""SentinelMask API."""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import metrics
from .api import admin, audit_api, auth, compliance_reports, databases, discovery, policies, query, scim, sso, uploads
from .config import ROOT_DIR, get_settings
from .connectors import _cache as _adapters
from .connectors import _cache_lock as _adapter_lock
from .metadb import SessionLocal
from .security import Principal, require
from .seed import ensure_initialised
from .sso import ensure_identity_providers
from .uploads import purge_expired

log = logging.getLogger("sentinelmask")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_initialised()
    db = SessionLocal()
    try:
        purge_expired(db)
        ensure_identity_providers(db)  # metadata DBs created before SSO existed get the mock IdP too
    finally:
        db.close()
    yield


app = FastAPI(
    title="SentinelMask API",
    description="Intelligent Data Protection Engine - PII discovery and role-based dynamic masking.",
    version="1.0.0",
    lifespan=lifespan,
)

# Credentialed CORS must name its origins: "*" or a catch-all regex would let any website
# act with a visitor's session. The Vercel frontend proxies /api, so it needs no CORS entry.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in get_settings().cors_origins if o != "*"],
    allow_origin_regex=os.environ.get("SENTINEL_CORS_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Sentinel-CSRF", "X-Correlation-ID",
                   "X-DreamGuard-Purpose", "X-DreamGuard-Ticket-Id"],
    expose_headers=["X-Correlation-ID", "Server-Timing", "X-Dossier-SHA256", "X-Dossier-Signature", "X-Audit-Event-Id",
                    "Content-Disposition"],
)
# JSON payloads (classification lists, result sets) compress 5-10x; the free Render tier is
# bandwidth-bound, so this is the cheapest latency win.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    cid = request.headers.get("x-correlation-id", "")
    request.state.correlation_id = cid if cid.isalnum() and len(cid) <= 64 else uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - started) * 1000
    if request.url.path.startswith("/api"):
        route = request.scope.get("route")
        metrics.observe(request.method, getattr(route, "path", "unmatched"), response.status_code, ms)
        response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"http_{exc.status_code}", "message": exc.detail}, "correlation_id": request.state.correlation_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Echo field locations and messages only - never the submitted values.
    issues = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg", "invalid")} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": "Request validation failed", "issues": issues},
                 "correlation_id": request.state.correlation_id},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled error type=%s path=%s cid=%s", type(exc).__name__, request.url.path, request.state.correlation_id)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal error"}, "correlation_id": request.state.correlation_id},
    )


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "service": "sentinelmask"}


@app.get("/api/metrics", tags=["health"])
def get_metrics(_: Principal = Depends(require("audit:read"))):
    snap = metrics.snapshot()
    with _adapter_lock:
        adapters = list(_adapters.values())
    hits = sum(a.cache_hits for a in adapters)
    misses = sum(a.cache_misses for a in adapters)
    snap["query_cache"] = {"hits": hits, "misses": misses, "hit_rate": round(hits / (hits + misses), 4) if hits + misses else 0.0}
    return snap


for r in (auth.router, sso.router, scim.router, databases.router, discovery.router, policies.router, query.router,
          uploads.router, audit_api.router, compliance_reports.router, admin.router):
    app.include_router(r)
# SCIM clients expect RFC 7644 error bodies, not the console's {"error": ...} shape.
app.add_exception_handler(scim.ScimError, scim.scim_error_handler)


# Serve the built frontend (frontend/dist) when present, so one process runs the demo.
_dist = ROOT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(Path(_dist / "index.html"))
