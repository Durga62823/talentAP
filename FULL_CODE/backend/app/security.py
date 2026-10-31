"""Authentication, authorization and secret handling."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import credential_key, get_settings
from .metadb import AuthSession, Role, User, get_db, utcnow

_hasher = PasswordHasher()  # Argon2id with library defaults

# Every permission the application understands. Roles hold a subset; anything else is denied.
PERMISSIONS = {
    "connections:manage": "Register, test and remove database connections",
    "scan:run": "Run schema discovery and PII scans",
    "classification:review": "Approve, reject or override classifications",
    "policy:manage": "Create, edit and (de)activate masking policies",
    "users:manage": "Manage user accounts and table grants",
    "audit:read": "Read the security audit log",
    "integrity:run": "Run source-data integrity verification",
    "upload:manage": "Upload, scan and import files",
    "query:execute": "Run protected read-only queries",
    "raw:break_glass": "Request raw values for BREAK_GLASS columns with a recorded justification",
}

COOKIE_NAME = "sm_session"
CSRF_HEADER = "x-sentinel-csrf"

# Purposes a request may be bound to (ABAC). Anything else is treated as "no purpose", which can
# only ever resolve to the caller's baseline masking - never to more access.
PURPOSES = {
    "CUSTOMER_SUPPORT": "Customer inbound support",
    "FRAUD_INVESTIGATION": "Fraud triage / investigation",
    "DISPUTE_RESOLUTION": "Transaction dispute resolution",
    "ANALYTICS_REPORTING": "Analytics and reporting",
    "SECURITY_AUDIT": "Security / compliance audit",
}
PURPOSE_HEADER = "x-dreamguard-purpose"
TICKET_HEADER = "x-dreamguard-ticket-id"
_TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}-\d{1,12}$")  # INC-8821, TICKET-10492, SR2-77


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# A fixed dummy hash keeps failed-login timing similar for unknown usernames.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-password")


def dummy_verify() -> None:
    verify_password(_DUMMY_HASH, "x")


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_token_digest(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=get_settings().session_hours),
        )
    )
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    s = db.get(AuthSession, _token_digest(token))
    if s:
        s.revoked = True
        db.commit()


# ---- credential encryption ---------------------------------------------------------------

def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(credential_key()))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:  # key rotated or data corrupted
        raise RuntimeError("stored credential cannot be decrypted") from exc


# ---- request identity ------------------------------------------------------------------

@dataclass(frozen=True)
class AccessContext:
    """ABAC attributes of one request. `purpose` and `ticket_id` are the caller's attestation:
    they are format-checked here and recorded in the audit chain, not verified against a
    ticketing system. `rejected` names attributes that were supplied but invalid."""

    purpose: str | None = None
    ticket_id: str | None = None
    ip_address: str | None = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rejected: tuple[str, ...] = ()

    def as_audit(self) -> dict:
        return {
            "purpose": self.purpose,
            "ticket_id": self.ticket_id,
            "ip_address": self.ip_address,
            "evaluated_at_utc": self.at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rejected_attributes": list(self.rejected),
        }


def normalise_purpose(raw: str | None) -> str | None:
    v = (raw or "").strip().upper()
    return v if v in PURPOSES else None


def normalise_ticket(raw: str | None) -> str | None:
    v = (raw or "").strip().upper()
    return v if _TICKET_RE.match(v) else None


def access_context(request: Request) -> AccessContext:
    raw_purpose, raw_ticket = request.headers.get(PURPOSE_HEADER, "").strip(), request.headers.get(TICKET_HEADER, "").strip()
    purpose, ticket = normalise_purpose(raw_purpose), normalise_ticket(raw_ticket)
    rejected = tuple(name for name, raw, ok in (("purpose", raw_purpose, purpose), ("ticket_id", raw_ticket, ticket)) if raw and not ok)
    return AccessContext(purpose, ticket, request.client.host if request.client else None, rejected=rejected)


@dataclass
class Principal:
    user_id: str
    username: str
    display_name: str
    role: str
    permissions: set[str] = field(default_factory=set)
    context: AccessContext = field(default_factory=AccessContext)

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def _extract_token(request: Request) -> tuple[str | None, bool]:
    """Returns (token, from_cookie). Bearer tokens are used for side-by-side role
    comparison; the primary console session uses an HttpOnly cookie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None, False
    return request.cookies.get(COOKIE_NAME), True


def resolve_principal(db: Session, token: str) -> Principal | None:
    s = db.get(AuthSession, _token_digest(token))
    if s is None or s.revoked:
        return None
    expires = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    user = db.get(User, s.user_id)
    if user is None or not user.active:
        return None
    role = db.get(Role, user.role)
    # Unknown roles resolve to an empty permission set: deny by default.
    perms = {p for p in (role.permissions if role else []) if p in PERMISSIONS}
    return Principal(user.id, user.username, user.display_name, user.role, perms)


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token, from_cookie = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    if from_cookie and request.method not in ("GET", "HEAD", "OPTIONS"):
        # Cookie sessions must prove same-origin intent (SameSite=Strict is the first layer).
        if request.headers.get(CSRF_HEADER) != "1":
            raise HTTPException(status_code=403, detail="Missing CSRF header")
    principal = resolve_principal(db, token)
    if principal is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    principal.context = access_context(request)
    request.state.principal = principal
    return principal


def require(perm: str):
    if perm not in PERMISSIONS:
        raise ValueError(f"unknown permission {perm}")

    def dep(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.can(perm):
            from .audit import record  # local import avoids a cycle

            db = next(get_db())
            try:
                record(
                    db,
                    principal,
                    action="privilege_violation",
                    outcome="denied",
                    reason=f"missing permission {perm} for {request.method} {request.url.path}",
                    correlation_id=getattr(request.state, "correlation_id", None),
                )
            finally:
                db.close()
            raise HTTPException(status_code=403, detail=f"Permission '{perm}' required")
        return principal

    return dep
