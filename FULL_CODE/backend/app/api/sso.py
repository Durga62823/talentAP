"""Browser-facing SSO endpoints: provider list, login redirect, the offline mock IdP's
authorization endpoint, and the OIDC callback that establishes the console session."""
from __future__ import annotations

import hmac
import html
import os
import re
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, sso
from ..config import get_settings
from ..integrity import principal_for_user
from ..metadb import IdentityProvider, get_db
from ..security import create_session
from .auth import set_session_cookie
from .common import corr

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])


def _redirect_uri(request: Request) -> str:
    # Behind a proxy that rewrites Host, set SENTINEL_PUBLIC_URL to the URL users browse to.
    base = os.environ.get("SENTINEL_PUBLIC_URL") or str(request.base_url)
    return base.rstrip("/") + sso.CALLBACK_PATH


def _to_console(path: str) -> str:
    return os.environ.get("SENTINEL_FRONTEND_URL", "").rstrip("/") + path


def _fail(code: str) -> RedirectResponse:
    resp = RedirectResponse(_to_console(f"/login?{urlencode({'sso_error': code})}"), status_code=302)
    resp.delete_cookie(sso.STATE_COOKIE, path="/api/auth/sso")
    return resp


@router.get("/providers")
def providers(db: Session = Depends(get_db)):
    """Public (the login page needs it). No secrets, no client ids."""
    out = []
    for idp in db.scalars(select(IdentityProvider).where(IdentityProvider.is_active.is_(True)).order_by(IdentityProvider.created_at)):
        item = {"id": idp.id, "name": idp.name, "idp_type": idp.idp_type, "issuer_host": urlparse(idp.issuer_url).hostname}
        if idp.idp_type == "MOCK_SAML":
            item["personas"] = [
                {"login_hint": hint, "name": p["name"], "groups": p["groups"],
                 "role": sso.role_for_groups(db, idp, p["groups"]) or idp.default_role}
                for hint, p in sso.MOCK_DIRECTORY.items()
            ]
        out.append(item)
    return out


@router.get("/login/{idp_id}")
def sso_login(idp_id: str, request: Request, login_hint: str | None = Query(default=None, max_length=254), db: Session = Depends(get_db)):
    idp = db.get(IdentityProvider, idp_id)
    if idp is None or not idp.is_active:
        return _fail("unknown_provider")
    try:
        url, sealed = sso.begin_login(idp, _redirect_uri(request), login_hint)
    except sso.SsoError as exc:
        return _fail(exc.code)
    resp = RedirectResponse(url, status_code=302)
    # Binds the callback to this browser (login CSRF); Lax is still sent on the IdP's top-level redirect back.
    resp.set_cookie(sso.STATE_COOKIE, sealed, max_age=sso.STATE_TTL_S, httponly=True, samesite="lax",
                    secure=get_settings().environment == "production", path="/api/auth/sso")
    return resp


@router.get("/mock-idp/authorize", include_in_schema=False)
def mock_authorize(
    request: Request,
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    nonce: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    response_type: str = "",
    login_hint: str | None = Query(default=None, max_length=254),
):
    """The offline IdP's sign-in. With a login_hint it behaves like an already-authenticated
    enterprise session; without one it shows a directory picker."""
    if not login_hint:
        links = "".join(
            f'<li><a href="{html.escape(str(request.url.include_query_params(login_hint=hint)))}">{html.escape(p["name"])}</a>'
            f" &middot; {html.escape(hint)} &middot; groups: {html.escape(', '.join(p['groups']) or 'none')}</li>"
            for hint, p in sso.MOCK_DIRECTORY.items()
        )
        return HTMLResponse(f"<!doctype html><title>Enterprise sign-in (simulation)</title>"
                            f"<h1>Saffron Bank enterprise sign-in</h1><p>Offline IdP simulation. Choose an identity:</p><ul>{links}</ul>")
    try:
        code = sso.mock_idp.authorize(client_id=client_id, redirect_uri=redirect_uri, nonce=nonce, code_challenge=code_challenge,
                                      code_challenge_method=code_challenge_method, response_type=response_type, login_hint=login_hint)
        query = {"code": code, "state": state}
    except sso.SsoError as exc:
        query = {"error": exc.code, "state": state}
    # Path-only redirect: the simulated IdP is served from the console's own origin.
    return RedirectResponse(f"{sso.CALLBACK_PATH}?{urlencode(query)}", status_code=302)


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             db: Session = Depends(get_db)):
    idp_id = None
    claims: dict = {}
    try:
        flow = sso.open_state(request.cookies.get(sso.STATE_COOKIE))
        idp_id = flow["idp"]
        if not state or not hmac.compare_digest(state, flow["state"]):
            raise sso.SsoError("state_mismatch", "Sign-in response does not belong to this browser session")
        if error:
            raise sso.SsoError("idp_" + re.sub(r"[^a-z_]", "", error.lower())[:40], "Identity provider refused the sign-in")
        idp = db.get(IdentityProvider, idp_id)
        if idp is None or not idp.is_active:
            raise sso.SsoError("unknown_provider", "Identity provider is not active")
        if not code:
            raise sso.SsoError("code_missing", "No authorization code returned")
        claims = sso.complete_login(idp, flow, code)
        user, changes = sso.resolve_user(db, idp, claims)
        if not user.active:
            raise sso.SsoError("account_disabled", "Account is deactivated")
    except sso.SsoError as exc:
        db.rollback()
        who = claims.get("preferred_username") or claims.get("email")
        audit.record(db, None, action="sso_login_failed", outcome="denied", actor_name=who[:64] if isinstance(who, str) else None,
                     reason=f"{exc.code}: {exc.message}", correlation_id=corr(request), details={"idp_id": idp_id})
        return _fail(exc.code)

    token = create_session(db, user)
    p = principal_for_user(db, user)
    audit.record(db, p, action="sso_login", outcome="success", correlation_id=corr(request),
                 details={"idp_id": idp.id, "idp_type": idp.idp_type, "jit_provisioned": bool(changes.get("provisioned")),
                          "linked_scim_account": bool(changes.get("linked")), "role_change": changes.get("role"),
                          "groups": len(claims.get("groups") or [])})
    resp = RedirectResponse(_to_console("/"), status_code=302)
    set_session_cookie(resp, token)
    resp.delete_cookie(sso.STATE_COOKIE, path="/api/auth/sso")
    return resp
