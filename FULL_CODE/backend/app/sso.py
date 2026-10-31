"""Enterprise identity federation: OIDC authorization-code flow (PKCE + state + nonce), ID-token
validation, just-in-time provisioning and IdP group -> role mapping.

ID tokens must be RS256-signed; the algorithm is pinned, which rejects `alg: none` and HS/RS
key-confusion. A real OIDC provider is reached over HTTPS for discovery, code exchange and JWKS.
The MOCK_SAML provider ("mock_enterprise_idp") runs the same flow in-process for offline
evaluation and signs with a locally generated RSA key, so the identical validation code runs
either way. It simulates an enterprise IdP (Entra ID / Okta style); it does not parse SAML XML."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import credential_key, secret_file
from .metadb import IdentityProvider, Role, User
from .security import decrypt_secret, encrypt_secret, hash_password

MOCK_IDP_ID = "mock_enterprise_idp"
MOCK_ISSUER = "https://idp.saffronbank.example/mock-enterprise"
MOCK_CLIENT_ID = "dreamguard-console"
MOCK_AUTHORIZE_PATH = "/api/auth/sso/mock-idp/authorize"
CALLBACK_PATH = "/api/auth/sso/callback"
STATE_COOKIE = "sm_sso_state"
STATE_TTL_S = 600
_LEEWAY_S = 60

# The mock IdP's directory. Groups map to DreamGuard roles through the IdP's group_role_map; the
# contractor belongs to no mapped group and lands in the IdP's default role.
MOCK_DIRECTORY: dict[str, dict[str, Any]] = {
    "priya.nair@saffronbank.example": {"sub": "mock-7d1f-priya", "name": "Priya Nair", "groups": ["DG-Support"]},
    "arjun.mehta@saffronbank.example": {"sub": "mock-3a9c-arjun", "name": "Arjun Mehta", "groups": ["DG-Analysts"]},
    "vikram.iyer@saffronbank.example": {"sub": "mock-5e2b-vikram", "name": "Vikram Iyer", "groups": ["DG-Compliance"]},
    "rohan.kapoor@saffronbank.example": {"sub": "mock-9b4e-rohan", "name": "Rohan Kapoor", "groups": ["DG-Platform-Admins"]},
    "sam.dsouza@saffronbank.example": {"sub": "mock-1c8d-sam", "name": "Sam D'Souza (Contractor)", "groups": []},
}
MOCK_GROUP_ROLE_MAP = {"DG-Platform-Admins": "admin", "DG-Support": "support", "DG-Analysts": "analyst", "DG-Compliance": "compliance"}


class SsoError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _int_b64(n: int) -> str:
    return _b64e(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def pkce_challenge(verifier: str) -> str:
    return _b64e(hashlib.sha256(verifier.encode()).digest())


# ---- login state (encrypted, browser-bound, short-lived cookie) ---------------------------

def _state_fernet() -> Fernet:
    # Domain-separated from the key that encrypts stored database credentials.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"dreamguard-sso-state|" + credential_key()).digest()))


def seal_state(flow: dict[str, str]) -> str:
    return _state_fernet().encrypt(json.dumps(flow).encode()).decode()


def open_state(sealed: str | None) -> dict[str, str]:
    if not sealed:
        raise SsoError("state_missing", "Sign-in session expired or was started in another browser")
    try:
        return json.loads(_state_fernet().decrypt(sealed.encode(), ttl=STATE_TTL_S))
    except (InvalidToken, ValueError) as exc:
        raise SsoError("state_invalid", "Sign-in session expired or was tampered with") from exc


# ---- ID token validation ------------------------------------------------------------------

def _jwk_public_key(jwks: dict[str, Any], kid: str | None) -> rsa.RSAPublicKey:
    keys = [k for k in (jwks or {}).get("keys", []) if isinstance(k, dict) and k.get("kty") == "RSA" and k.get("use", "sig") == "sig"]
    if kid is not None:
        keys = [k for k in keys if k.get("kid") == kid]
    if len(keys) != 1:
        raise SsoError("token_key", "No unique signing key matches the ID token")
    try:
        e, n = (int.from_bytes(_b64d(keys[0][x]), "big") for x in ("e", "n"))
        return rsa.RSAPublicNumbers(e, n).public_key()
    except (KeyError, ValueError, TypeError) as exc:
        raise SsoError("token_key", "Signing key is malformed") from exc


def validate_id_token(token: str, *, jwks: dict[str, Any], issuer: str, audience: str, nonce: str, now: float | None = None) -> dict[str, Any]:
    try:
        h64, p64, s64 = token.split(".")
        header, claims, sig = json.loads(_b64d(h64)), json.loads(_b64d(p64)), _b64d(s64)
    except (ValueError, TypeError, AttributeError) as exc:
        raise SsoError("token_malformed", "ID token is malformed") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise SsoError("token_malformed", "ID token is malformed")
    if header.get("alg") != "RS256":
        raise SsoError("token_alg", "ID token must be signed with RS256")
    try:
        _jwk_public_key(jwks, header.get("kid")).verify(sig, f"{h64}.{p64}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise SsoError("token_signature", "ID token signature is invalid") from exc
    now = time.time() if now is None else now
    if claims.get("iss") != issuer:
        raise SsoError("token_issuer", "ID token issuer does not match the provider")
    auds = claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]
    if audience not in auds or (len(auds) > 1 and claims.get("azp") != audience):
        raise SsoError("token_audience", "ID token was not issued for DreamGuard")
    exp, iat = claims.get("exp"), claims.get("iat")
    if not isinstance(exp, (int, float)) or exp + _LEEWAY_S < now:
        raise SsoError("token_expired", "ID token has expired")
    if not isinstance(iat, (int, float)) or iat - _LEEWAY_S > now:
        raise SsoError("token_not_yet_valid", "ID token is not valid yet")
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise SsoError("token_nonce", "ID token nonce does not match this sign-in")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not 0 < len(sub) <= 255:
        raise SsoError("token_subject", "ID token has no usable subject")
    return claims


# ---- offline mock IdP ---------------------------------------------------------------------

class MockIdP:
    """In-process stand-in for an enterprise IdP: authorization codes are single-use, bound to
    client, redirect URI and PKCE challenge, and expire after 60 seconds."""

    def __init__(self) -> None:
        self._codes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._key: rsa.RSAPrivateKey | None = None

    def private_key(self) -> rsa.RSAPrivateKey:
        if self._key is None:
            pem = secret_file("mock_idp_rsa.pem", lambda: rsa.generate_private_key(65537, 2048).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            self._key = serialization.load_pem_private_key(pem, None)  # type: ignore[assignment]
        return self._key  # type: ignore[return-value]

    @staticmethod
    def client_secret() -> str:
        return secret_file("mock_idp_client.secret", lambda: secrets.token_urlsafe(32).encode()).decode().strip()

    def kid(self) -> str:
        return hashlib.sha256(_int_b64(self.private_key().public_key().public_numbers().n).encode()).hexdigest()[:16]

    def jwks(self) -> dict[str, Any]:
        pub = self.private_key().public_key().public_numbers()
        return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": self.kid(), "n": _int_b64(pub.n), "e": _int_b64(pub.e)}]}

    def sign(self, claims: dict[str, Any], header: dict[str, Any] | None = None) -> str:
        h = _b64e(json.dumps(header or {"alg": "RS256", "typ": "JWT", "kid": self.kid()}).encode())
        p = _b64e(json.dumps(claims).encode())
        sig = self.private_key().sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{h}.{p}.{_b64e(sig)}"

    def authorize(self, *, client_id: str, redirect_uri: str, nonce: str, code_challenge: str,
                  code_challenge_method: str, response_type: str, login_hint: str) -> str:
        if client_id != MOCK_CLIENT_ID:
            raise SsoError("unauthorized_client", "Unknown client")
        if response_type != "code" or code_challenge_method != "S256" or not code_challenge or not nonce:
            raise SsoError("invalid_request", "Authorization request must use the code flow with PKCE S256 and a nonce")
        if urlparse(redirect_uri).path != CALLBACK_PATH:
            raise SsoError("invalid_request", "redirect_uri is not registered")
        hint = login_hint.strip().lower()
        if hint not in MOCK_DIRECTORY:
            raise SsoError("access_denied", "No such account in the enterprise directory")
        code = secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            self._codes = {k: v for k, v in self._codes.items() if v["exp"] > now}
            self._codes[code] = {"client_id": client_id, "redirect_uri": redirect_uri, "nonce": nonce,
                                 "challenge": code_challenge, "login_hint": hint, "exp": now + 60}
        return code

    def exchange(self, *, code: str, client_id: str, client_secret: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
        with self._lock:
            grant = self._codes.pop(code, None)  # single use, even when the exchange then fails
        if grant is None or grant["exp"] < time.time():
            raise SsoError("invalid_grant", "Authorization code is invalid, expired or already used")
        if client_id != grant["client_id"] or not hmac.compare_digest(client_secret, self.client_secret()):
            raise SsoError("invalid_client", "Client authentication failed")
        if redirect_uri != grant["redirect_uri"] or not hmac.compare_digest(pkce_challenge(code_verifier), grant["challenge"]):
            raise SsoError("invalid_grant", "redirect_uri or PKCE verifier mismatch")
        person = MOCK_DIRECTORY[grant["login_hint"]]
        now = int(time.time())
        claims = {"iss": MOCK_ISSUER, "aud": client_id, "sub": person["sub"], "iat": now, "exp": now + 300,
                  "nonce": grant["nonce"], "email": grant["login_hint"], "preferred_username": grant["login_hint"],
                  "name": person["name"], "groups": list(person["groups"])}
        return {"token_type": "Bearer", "id_token": self.sign(claims)}


mock_idp = MockIdP()


# ---- protocol -----------------------------------------------------------------------------

def _require_https(url: str) -> None:
    u = urlparse(url)
    if u.scheme != "https" and u.hostname not in ("localhost", "127.0.0.1"):
        raise SsoError("idp_config", "Identity provider endpoints must use HTTPS")


def _http_json(method: str, url: str, **kw: Any) -> dict[str, Any]:
    _require_https(url)
    try:
        r = httpx.request(method, url, timeout=10.0, headers={"Accept": "application/json"}, **kw)
    except httpx.HTTPError as exc:
        raise SsoError("idp_unreachable", "Identity provider could not be reached") from exc
    if r.status_code >= 400:
        raise SsoError("idp_rejected", f"Identity provider rejected the request ({r.status_code})")
    try:
        return r.json()
    except ValueError as exc:
        raise SsoError("idp_unreachable", "Identity provider returned an invalid response") from exc


def discover(idp: IdentityProvider) -> dict[str, Any]:
    meta = _http_json("GET", idp.issuer_url.rstrip("/") + "/.well-known/openid-configuration")
    if meta.get("issuer") != idp.issuer_url:  # IdP mix-up protection
        raise SsoError("idp_config", "Discovery document issuer does not match the configured issuer")
    return meta


def begin_login(idp: IdentityProvider, redirect_uri: str, login_hint: str | None) -> tuple[str, str]:
    """Returns (authorization URL, sealed state for the browser cookie)."""
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    params = {"response_type": "code", "client_id": idp.client_id, "redirect_uri": redirect_uri,
              "scope": "openid profile email", "state": state, "nonce": nonce,
              "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"}
    if login_hint:
        params["login_hint"] = login_hint
    endpoint = MOCK_AUTHORIZE_PATH if idp.idp_type == "MOCK_SAML" else discover(idp)["authorization_endpoint"]
    sealed = seal_state({"idp": idp.id, "state": state, "nonce": nonce, "verifier": verifier, "redirect_uri": redirect_uri})
    return f"{endpoint}?{urlencode(params)}", sealed


def complete_login(idp: IdentityProvider, flow: dict[str, str], code: str) -> dict[str, Any]:
    """Exchange the code and return the validated ID-token claims."""
    secret = decrypt_secret(idp.client_secret_enc) if idp.client_secret_enc else ""
    if idp.idp_type == "MOCK_SAML":
        tokens = mock_idp.exchange(code=code, client_id=idp.client_id, client_secret=secret,
                                   redirect_uri=flow["redirect_uri"], code_verifier=flow["verifier"])
        jwks = mock_idp.jwks()
    else:
        meta = discover(idp)
        tokens = _http_json("POST", meta["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": flow["redirect_uri"],
            "client_id": idp.client_id, "client_secret": secret, "code_verifier": flow["verifier"]})
        jwks = _http_json("GET", meta["jwks_uri"])
    if not isinstance(tokens.get("id_token"), str):
        raise SsoError("token_missing", "Identity provider returned no ID token")
    return validate_id_token(tokens["id_token"], jwks=jwks, issuer=idp.issuer_url, audience=idp.client_id, nonce=flow["nonce"])


# ---- account resolution -------------------------------------------------------------------

def pick_role(db: Session, candidates: list[str]) -> str | None:
    """Deterministic choice among mapped roles: the one with the most permissions, then by name."""
    roles = [r for r in (db.get(Role, c) for c in set(candidates)) if r is not None]
    return min(roles, key=lambda r: (-len(r.permissions or []), r.name)).name if roles else None


def role_for_groups(db: Session, idp: IdentityProvider, groups: list[str] | None) -> str | None:
    mapping = idp.group_role_map or {}
    return pick_role(db, [mapping[g] for g in (groups or []) if isinstance(g, str) and g in mapping])


def _unique_username(db: Session, base: str) -> str:
    base = base.strip().lower()[:60] or "sso-user"
    name, n = base, 1
    while db.scalar(select(User.id).where(User.username == name)) is not None:
        n += 1
        name = f"{base}-{n}"
    return name


def resolve_user(db: Session, idp: IdentityProvider, claims: dict[str, Any]) -> tuple[User, dict[str, Any]]:
    """Find or just-in-time provision the local account for validated claims.

    Accounts are matched on (idp, sub) only - never on an e-mail that a local account happens to
    share, which would let an IdP take over local users. A SCIM-provisioned account of the same IdP
    that has not signed in yet is linked by its userName."""
    sub = claims["sub"]
    login = next((v.strip().lower() for v in (claims.get("preferred_username"), claims.get("email"), claims.get("upn"))
                  if isinstance(v, str) and v.strip()), "")
    groups = claims.get("groups") if isinstance(claims.get("groups"), list) else None
    mapped = role_for_groups(db, idp, groups)
    changes: dict[str, Any] = {}
    user = db.scalar(select(User).where(User.idp_id == idp.id, User.external_sub == sub))
    if user is None and login:
        user = db.scalar(select(User).where(User.idp_id == idp.id, User.external_sub.is_(None), User.username == login))
        if user is not None:
            user.external_sub = sub
            changes["linked"] = True
    if user is None:
        role = mapped or idp.default_role
        if not role or db.get(Role, role) is None:
            raise SsoError("no_role", "Your directory groups do not grant access to DreamGuard")
        name = claims.get("name") if isinstance(claims.get("name"), str) else ""
        user = User(username=_unique_username(db, login or f"sso-{sub[:24]}"), display_name=(name or login or sub)[:128],
                    role=role, password_hash=hash_password(secrets.token_urlsafe(32)), idp_id=idp.id, external_sub=sub)
        db.add(user)
        changes["provisioned"] = True
    elif groups is not None:
        # The IdP is the source of truth for federated roles: re-sync on every sign-in.
        role = mapped or idp.default_role
        if not role or db.get(Role, role) is None:
            raise SsoError("no_role", "Your directory groups no longer grant access to DreamGuard")
        if role != user.role:
            changes["role"] = [user.role, role]
            user.role = role
    db.commit()
    return user, changes


def ensure_identity_providers(db: Session) -> None:
    """Idempotent: the offline mock IdP always exists; an OIDC provider is registered (or updated)
    from SENTINEL_OIDC_* environment variables when SENTINEL_OIDC_ISSUER is set."""
    if db.get(IdentityProvider, MOCK_IDP_ID) is None:
        db.add(IdentityProvider(
            id=MOCK_IDP_ID, name="Saffron Bank Entra ID (offline simulation)", issuer_url=MOCK_ISSUER,
            client_id=MOCK_CLIENT_ID, client_secret_enc=encrypt_secret(MockIdP.client_secret()), idp_type="MOCK_SAML",
            default_role="analyst", group_role_map=MOCK_GROUP_ROLE_MAP))
    issuer = os.environ.get("SENTINEL_OIDC_ISSUER")
    if issuer:
        idp = db.scalar(select(IdentityProvider).where(IdentityProvider.issuer_url == issuer)) or IdentityProvider(issuer_url=issuer, idp_type="OIDC")
        idp.name = os.environ.get("SENTINEL_OIDC_NAME", "Enterprise SSO")
        idp.client_id = os.environ.get("SENTINEL_OIDC_CLIENT_ID", "")
        idp.client_secret_enc = encrypt_secret(os.environ.get("SENTINEL_OIDC_CLIENT_SECRET", ""))
        # No default role unless configured: unmapped directory users are refused (fail closed).
        idp.default_role = os.environ.get("SENTINEL_OIDC_DEFAULT_ROLE", "")
        idp.group_role_map = json.loads(os.environ.get("SENTINEL_OIDC_GROUP_ROLE_MAP", "{}"))
        db.add(idp)
    db.commit()
