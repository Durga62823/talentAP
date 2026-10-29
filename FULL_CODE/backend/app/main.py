"""SentinelMask API."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, audit_api, auth, databases, discovery, policies, query, uploads
from .config import ROOT_DIR, get_settings
from .metadb import SessionLocal
from .seed import ensure_initialised
from .uploads import purge_expired

log = logging.getLogger("sentinelmask")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_initialised()
    db = SessionLocal()
    try:
        purge_expired(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="SentinelMask API",
    description="Intelligent Data Protection Engine - PII discovery and role-based dynamic masking.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Sentinel-CSRF", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    cid = request.headers.get("x-correlation-id", "")
    request.state.correlation_id = cid if cid.isalnum() and len(cid) <= 64 else uuid.uuid4().hex
    response = await call_next(request)
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


for r in (auth.router, databases.router, discovery.router, policies.router, query.router, uploads.router, audit_api.router, admin.router):
    app.include_router(r)


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
