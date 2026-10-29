from __future__ import annotations

import time
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..metadb import User, get_db
from ..security import (
    COOKIE_NAME,
    PERMISSIONS,
    Principal,
    _extract_token,
    create_session,
    current_principal,
    dummy_verify,
    revoke_session,
    verify_password,
)
from .common import corr

router = APIRouter(prefix="/api/auth", tags=["auth"])

_failures: dict[str, list[float]] = defaultdict(list)
MAX_FAILURES, WINDOW_S = 5, 300


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    # "cookie": primary console session (HttpOnly cookie, token never exposed to JS).
    # "bearer": an additional identity for side-by-side role comparison; token kept in memory.
    mode: Literal["cookie", "bearer"] = "cookie"


def _me(p: Principal) -> dict:
    return {
        "id": p.user_id,
        "username": p.username,
        "display_name": p.display_name,
        "role": p.role,
        "permissions": sorted(p.permissions),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{body.username.lower()}|{request.client.host if request.client else '-'}"
    now = time.time()
    _failures[key] = [t for t in _failures[key] if now - t < WINDOW_S]
    if len(_failures[key]) >= MAX_FAILURES:
        audit.record(db, None, action="login_failed", outcome="denied", actor_name=body.username[:64],
                     reason="temporarily locked after repeated failures", correlation_id=corr(request))
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None:
        dummy_verify()
    ok = user is not None and user.active and verify_password(user.password_hash, body.password)
    if not ok:
        _failures[key].append(now)
        audit.record(db, None, action="login_failed", outcome="denied", actor_name=body.username[:64],
                     reason="invalid credentials or inactive account", correlation_id=corr(request))
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _failures.pop(key, None)
    token = create_session(db, user)
    from ..integrity import principal_for_user

    p = principal_for_user(db, user)
    audit.record(db, p, action="login", outcome="success", correlation_id=corr(request), details={"mode": body.mode})
    out = {"user": _me(p)}
    if body.mode == "cookie":
        is_prod = get_settings().environment == "production"
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="none" if is_prod else "lax",
            secure=is_prod,
            max_age=get_settings().session_hours * 3600,
            path="/",
        )
    else:
        out["token"] = token
    return out


@router.post("/logout")
def logout(request: Request, response: Response, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    token, _ = _extract_token(request)
    if token:
        revoke_session(db, token)
    response.delete_cookie(COOKIE_NAME, path="/")
    audit.record(db, p, action="logout", outcome="success", correlation_id=corr(request))
    return {"ok": True}


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    return {"user": _me(p), "all_permissions": PERMISSIONS}
