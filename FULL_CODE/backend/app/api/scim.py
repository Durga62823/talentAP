"""SCIM 2.0 user provisioning (RFC 7643 / 7644) for federated identity providers.

Each SCIM token is bound to one identity provider and can only see or change users bound to that
provider: local accounts - including break-glass administrators - are invisible to SCIM.
Supported: /Users list + filter (eq ne co sw ew pr on userName, externalId, displayName, id,
active), GET / POST / PUT / PATCH, and /ServiceProviderConfig. There is no DELETE: deprovisioning
is `active: false`, which revokes sessions and keeps audit-log actor references intact."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..metadb import AuthSession, IdentityProvider, Role, SCIMToken, User, get_db, new_id, utcnow
from ..security import Principal, _token_digest, hash_password, require
from ..sso import MOCK_IDP_ID, pick_role, role_for_groups
from .common import corr, iso

router = APIRouter(prefix="/api/scim", tags=["scim"])

SCIM_JSON = "application/scim+json"
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
TOKEN_PREFIX = "dgscim_"  # recognisable by secret scanners
MAX_PAGE = 200


class ScimError(Exception):
    def __init__(self, status: int, detail: str, scim_type: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.scim_type = status, detail, scim_type


async def scim_error_handler(request: Request, exc: ScimError) -> JSONResponse:
    body = {"schemas": [ERROR_SCHEMA], "status": str(exc.status), "detail": exc.detail}
    if exc.scim_type:
        body["scimType"] = exc.scim_type
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return JSONResponse(body, status_code=exc.status, media_type=SCIM_JSON, headers=headers)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo on read-back


@dataclass
class ScimClient:
    token: SCIMToken
    idp: IdentityProvider

    @property
    def actor(self) -> str:
        return f"scim:{self.token.id[:8]}"


def scim_client(request: Request, db: Session = Depends(get_db)) -> ScimClient:
    auth = request.headers.get("authorization", "")
    raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    tok = db.scalar(select(SCIMToken).where(SCIMToken.token_hash == _token_digest(raw))) if raw.startswith(TOKEN_PREFIX) else None
    idp = db.get(IdentityProvider, tok.idp_id) if tok is not None else None
    if tok is None or not tok.is_active or _aware(tok.expires_at) < utcnow() or idp is None or not idp.is_active:
        audit.record(db, None, action="scim_auth_failed", outcome="denied", actor_name="scim",
                     reason="missing, unknown, revoked or expired SCIM token", correlation_id=corr(request),
                     details={"path": request.url.path})
        raise ScimError(401, "A valid SCIM bearer token is required")
    tok.last_used_at = utcnow()
    db.commit()
    return ScimClient(tok, idp)


# ---- representation -----------------------------------------------------------------------

def to_resource(u: User) -> dict[str, Any]:
    return {
        "schemas": [USER_SCHEMA],
        "id": u.id,
        "externalId": u.external_sub,
        "userName": u.username,
        "displayName": u.display_name,
        "name": {"formatted": u.display_name},
        "active": u.active,
        "roles": [{"value": u.role.title(), "primary": True}],
        "meta": {"resourceType": "User", "created": iso(u.created_at), "location": f"/api/scim/v2/Users/{u.id}"},
    }


def _scim(body: dict[str, Any], status: int = 200, **headers: str) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=SCIM_JSON, headers=headers or None)


def _bool(v: Any) -> bool:
    # Entra ID sends "True"/"False" strings in PATCH operations.
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    raise ScimError(400, "active must be a boolean", "invalidValue")


def _user_name(v: Any) -> str:
    if not isinstance(v, str) or not 3 <= len(v.strip()) <= 64:
        raise ScimError(400, "userName must be 3-64 characters", "invalidValue")
    return v.strip().lower()  # userName is caseExact=false (RFC 7643 4.1.1)


def _display_name(attrs: dict[str, Any]) -> str | None:
    name = attrs.get("name") if isinstance(attrs.get("name"), dict) else {}
    for v in (attrs.get("displayName"), attrs.get("name.formatted"), name.get("formatted"),
              " ".join(x for x in (name.get("givenName"), name.get("familyName")) if isinstance(x, str))):
        if isinstance(v, str) and v.strip():
            return v.strip()[:128]
    return None


def _role(db: Session, idp: IdentityProvider, attrs: dict[str, Any]) -> str | None:
    """roles[] (primary first) -> DreamGuard role; else IdP group mapping. Unknown roles are an error."""
    roles = attrs.get("roles")
    if isinstance(roles, list) and roles:
        primary = [r for r in roles if isinstance(r, dict) and str(r.get("primary", "")).lower() == "true"]
        values = [(r.get("value") if isinstance(r, dict) else r) for r in (primary or roles)]
        wanted = [v.strip().lower() for v in values if isinstance(v, str)]
        role = pick_role(db, wanted)
        if role is None:
            raise ScimError(400, f"Unknown role(s): {', '.join(map(str, values))}", "invalidValue")
        return role
    groups = attrs.get("groups")
    if isinstance(groups, list):
        return role_for_groups(db, idp, [g.get("display") if isinstance(g, dict) else g for g in groups])
    return None


def _owned(db: Session, c: ScimClient, uid: str) -> User:
    u = db.get(User, uid)
    if u is None or u.idp_id != c.idp.id:  # other IdPs' and local users are indistinguishable from absent ones
        raise ScimError(404, "User not found", None)
    return u


def _apply(db: Session, c: ScimClient, u: User, attrs: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "userName" in attrs:
        name = _user_name(attrs["userName"])
        if name != u.username:
            if db.scalar(select(User.id).where(func.lower(User.username) == name, User.id != u.id)):
                raise ScimError(409, "userName already exists", "uniqueness")
            changes["userName"] = [u.username, name]
            u.username = name
    display = _display_name(attrs)
    if display and display != u.display_name:
        changes["displayName"] = "updated"
        u.display_name = display
    if "externalId" in attrs:
        ext = attrs["externalId"] if isinstance(attrs["externalId"], str) and attrs["externalId"] else None
        if ext != u.external_sub:
            if ext and db.scalar(select(User.id).where(User.idp_id == c.idp.id, User.external_sub == ext, User.id != u.id)):
                raise ScimError(409, "externalId already bound to another user", "uniqueness")
            changes["externalId"] = "updated"
            u.external_sub = ext
    if "active" in attrs:
        active = _bool(attrs["active"])
        if active != u.active:
            changes["active"] = [u.active, active]
            u.active = active
    if "roles" in attrs or "groups" in attrs:
        role = _role(db, c.idp, attrs) or c.idp.default_role
        if not role:
            raise ScimError(400, "No role mapped and the identity provider has no default role", "invalidValue")
        if role != u.role:
            changes["role"] = [u.role, role]
            u.role = role
    if "active" in changes or "role" in changes:
        # Deprovisioning and privilege changes take effect immediately.
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))
    return changes


# ---- filter -------------------------------------------------------------------------------

_FILTER = re.compile(r'^\s*([A-Za-z.]+)\s+(eq|ne|co|sw|ew|pr)\b\s*(?:"((?:[^"\\]|\\.)*)"|(true|false))?\s*$', re.I)
_ATTRS = {"username": (User.username, False), "externalid": (User.external_sub, True), "displayname": (User.display_name, False),
          "id": (User.id, True), "active": (User.active, True)}


def _filter_clause(expr: str):
    m = _FILTER.match(expr)
    if not m or m.group(1).lower() not in _ATTRS:
        raise ScimError(400, "Unsupported filter; use e.g. userName eq \"x\"", "invalidFilter")
    attr, op = m.group(1).lower(), m.group(2).lower()
    col, case_exact = _ATTRS[attr]
    if op == "pr":
        return col.is_not(None)
    if attr == "active":
        if m.group(4) is None or op not in ("eq", "ne"):
            raise ScimError(400, "active supports eq/ne with true or false", "invalidFilter")
        value = m.group(4).lower() == "true"
        return col == value if op == "eq" else col != value
    if m.group(3) is None:
        raise ScimError(400, "Filter value must be a quoted string", "invalidFilter")
    value = m.group(3).replace('\\"', '"')
    target = col if case_exact else func.lower(col)
    value = value if case_exact else value.lower()
    return {"eq": target == value, "ne": target != value,
            "co": target.contains(value, autoescape=True), "sw": target.startswith(value, autoescape=True),
            "ew": target.endswith(value, autoescape=True)}[op]


# ---- SCIM protocol endpoints ---------------------------------------------------------------

@router.get("/v2/ServiceProviderConfig")
def service_provider_config(c: ScimClient = Depends(scim_client)):
    return _scim({
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True}, "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": MAX_PAGE}, "changePassword": {"supported": False},
        "sort": {"supported": False}, "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "description": "Per-IdP SCIM token issued in DreamGuard"}],
    })


@router.get("/v2/Users")
def list_users(filter: str | None = None, startIndex: int = 1, count: int = 100,  # noqa: A002 - RFC parameter names
               c: ScimClient = Depends(scim_client), db: Session = Depends(get_db)):
    q = select(User).where(User.idp_id == c.idp.id)
    if filter:
        q = q.where(_filter_clause(filter))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    start, count = max(startIndex, 1), min(max(count, 0), MAX_PAGE)
    rows = list(db.scalars(q.order_by(User.created_at, User.id).offset(start - 1).limit(count)))
    return _scim({"schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": start, "itemsPerPage": len(rows),
                  "Resources": [to_resource(u) for u in rows]})


@router.get("/v2/Users/{uid}")
def get_user(uid: str, c: ScimClient = Depends(scim_client), db: Session = Depends(get_db)):
    return _scim(to_resource(_owned(db, c, uid)))


@router.post("/v2/Users")
def create_user(request: Request, payload: dict[str, Any] = Body(...), c: ScimClient = Depends(scim_client), db: Session = Depends(get_db)):
    name = _user_name(payload.get("userName"))
    if db.scalar(select(User.id).where(func.lower(User.username) == name)):
        raise ScimError(409, "userName already exists", "uniqueness")
    role = _role(db, c.idp, payload) or c.idp.default_role
    if not role or db.get(Role, role) is None:
        raise ScimError(400, "No role mapped and the identity provider has no default role", "invalidValue")
    u = User(id=new_id(), username=name, display_name=_display_name(payload) or name, role=role, idp_id=c.idp.id, active=True,
             password_hash=hash_password(secrets.token_urlsafe(32)))  # unusable: federated users sign in at their IdP
    _apply(db, c, u, {k: v for k, v in payload.items() if k in ("externalId", "active")})
    db.add(u)
    db.commit()
    audit.record(db, None, action="scim_user_create", outcome="success", actor_name=c.actor, correlation_id=corr(request),
                 details={"user_id": u.id, "username": u.username, "role": u.role, "active": u.active, "idp_id": c.idp.id})
    return _scim(to_resource(u), 201, Location=f"/api/scim/v2/Users/{u.id}")


def _update(request: Request, db: Session, c: ScimClient, u: User, attrs: dict[str, Any], kind: str) -> JSONResponse:
    changes = _apply(db, c, u, attrs)
    db.commit()
    if changes:
        audit.record(db, None, action="scim_user_update", outcome="success", actor_name=c.actor, correlation_id=corr(request),
                     details={"user_id": u.id, "username": u.username, "operation": kind, "changes": changes, "idp_id": c.idp.id})
    return _scim(to_resource(u))


@router.put("/v2/Users/{uid}")
def replace_user(uid: str, request: Request, payload: dict[str, Any] = Body(...), c: ScimClient = Depends(scim_client),
                 db: Session = Depends(get_db)):
    u = _owned(db, c, uid)
    if "userName" not in payload:
        raise ScimError(400, "userName is required", "invalidValue")
    return _update(request, db, c, u, payload, "put")


_PATHS = {"active": "active", "username": "userName", "displayname": "displayName", "name.formatted": "name.formatted",
          "externalid": "externalId", "roles": "roles"}


@router.patch("/v2/Users/{uid}")
def patch_user(uid: str, request: Request, payload: dict[str, Any] = Body(...), c: ScimClient = Depends(scim_client),
               db: Session = Depends(get_db)):
    u = _owned(db, c, uid)
    ops = payload.get("Operations")
    if not isinstance(ops, list) or not ops:
        raise ScimError(400, "PatchOp needs a non-empty Operations list", "invalidSyntax")
    attrs: dict[str, Any] = {}
    for op in ops:
        kind = str(op.get("op", "")).lower() if isinstance(op, dict) else ""
        if kind not in ("add", "replace", "remove"):
            raise ScimError(400, "op must be add, replace or remove", "invalidSyntax")
        path, value = op.get("path"), op.get("value")
        if path is None:
            if kind == "remove" or not isinstance(value, dict):
                raise ScimError(400, "Operations without a path need an object value", "noTarget")
            attrs.update(value)  # Entra ID style: {"op": "Replace", "value": {"active": false}}
            continue
        key = _PATHS.get(str(path).lower())
        if key is None:
            continue  # attributes DreamGuard does not store (emails, title, ...) are ignored
        if kind == "remove":
            if key != "externalId":
                raise ScimError(400, f"{path} cannot be removed", "mutability")
            value = None
        attrs[key] = value
    return _update(request, db, c, u, attrs, "patch")


# ---- token administration (console session, users:manage) ---------------------------------

class TokenIn(BaseModel):
    description: str = Field(min_length=3, max_length=128)
    idp_id: str = MOCK_IDP_ID
    expires_in_days: int = Field(default=90, ge=1, le=365)


def token_dict(t: SCIMToken, idp_names: dict[str, str]) -> dict[str, Any]:
    status = "revoked" if not t.is_active else "expired" if _aware(t.expires_at) < utcnow() else "active"
    return {"id": t.id, "description": t.description, "idp_id": t.idp_id, "idp_name": idp_names.get(t.idp_id),
            "created_at": iso(t.created_at), "expires_at": iso(t.expires_at), "last_used_at": iso(t.last_used_at), "status": status}


@router.get("/tokens")
def list_tokens(p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    names = {i.id: i.name for i in db.scalars(select(IdentityProvider))}
    return [token_dict(t, names) for t in db.scalars(select(SCIMToken).order_by(SCIMToken.created_at.desc()))]


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, request: Request, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    idp = db.get(IdentityProvider, body.idp_id)
    if idp is None or not idp.is_active:
        raise HTTPException(status_code=400, detail="Unknown or inactive identity provider")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    t = SCIMToken(token_hash=_token_digest(raw), description=body.description, idp_id=idp.id,
                  expires_at=utcnow() + timedelta(days=body.expires_in_days))
    db.add(t)
    db.commit()
    audit.record(db, p, action="scim_token_create", outcome="success", correlation_id=corr(request),
                 details={"token_id": t.id, "idp_id": idp.id, "expires_at": iso(t.expires_at)})
    # The only time the token is ever returned; DreamGuard keeps its SHA-256 alone.
    return token_dict(t, {idp.id: idp.name}) | {"token": raw, "scim_base_url": "/api/scim/v2"}


@router.delete("/tokens/{tid}")
def revoke_token(tid: str, request: Request, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    t = db.get(SCIMToken, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="SCIM token not found")
    t.is_active = False
    db.commit()
    audit.record(db, p, action="scim_token_revoke", outcome="success", correlation_id=corr(request), details={"token_id": t.id})
    return {"ok": True}
