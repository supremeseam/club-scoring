"""Amazon Cognito sign-in (AUTH_MODE=cognito): check the ID token on every request and map it to a local account.

The browser signs in with the club's Cognito user pool(s) and sends the ID token as `Authorization: Bearer ...`.
Nothing here trusts a token until its RS256 signature, issuer, audience (our app clients), expiry and `token_use`
all check out against the pool's published keys. This app stores no passwords for these accounts.
"""
import hashlib
import json
import logging
import threading
import time
import urllib.request

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from ninja.errors import HttpError

from .models import AccountProfile, ExternalIdentity

log = logging.getLogger("auth")

KEYS_MAX_AGE = 3600          # seconds a pool's published keys are reused
MIN_REFETCH_SECONDS = 10     # an unknown key id may not make us fetch more often than this (no amplification)
LEEWAY = 5                   # seconds of clock skew tolerated on exp/iat
MAX_TOKEN_LENGTH = 8192

_lock = threading.Lock()
_keys: dict[str, tuple[float, dict[str, dict]]] = {}      # issuer -> (fetched_at, {kid: jwk})
_attempted: dict[str, float] = {}                         # issuer -> last fetch attempt (success or not)


def require_password_mode() -> None:
    """Called first by every endpoint that creates or checks a local password: not available when Cognito signs people in."""
    if settings.AUTH_MODE == "cognito":
        raise HttpError(404, "Not available: accounts are managed through the club's sign-in")


class TokenError(Exception):
    """The token is not acceptable. The message is for the log, never for the caller."""


def issuer_for(pool_id: str) -> str:
    return f"https://cognito-idp.{pool_id.split('_', 1)[0]}.amazonaws.com/{pool_id}"


def fetch_jwks(issuer: str) -> dict:
    """The pool's published signing keys. Replaced in tests."""
    req = urllib.request.Request(f"{issuer}/.well-known/jwks.json", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:            # noqa: S310 (https URL built from our settings)
        return json.loads(resp.read(200_000))


def reset_cache() -> None:
    with _lock:
        _keys.clear()
        _attempted.clear()


def _signing_key(issuer: str, kid: str):
    now = time.time()
    with _lock:
        fetched_at, keys = _keys.get(issuer, (0.0, {}))
        if kid in keys and now - fetched_at < KEYS_MAX_AGE:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(keys[kid]))
        if now - _attempted.get(issuer, 0.0) < MIN_REFETCH_SECONDS:
            raise TokenError("unknown signing key")
        _attempted[issuer] = now
    try:
        fresh = {k["kid"]: k for k in fetch_jwks(issuer).get("keys", []) if k.get("kty") == "RSA" and k.get("kid")}
    except Exception as exc:                                         # network, JSON, anything: never trust on failure
        raise TokenError(f"could not fetch signing keys ({type(exc).__name__})") from exc
    with _lock:
        _keys[issuer] = (time.time(), fresh)
    if kid not in fresh:
        raise TokenError("unknown signing key")
    return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(fresh[kid]))


def verify_id_token(token: str) -> dict:
    """The verified claims of a Cognito ID token from one of the configured app clients, or TokenError."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise TokenError("missing or oversized token")
    try:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise TokenError("not a JWT") from exc
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise TokenError("unexpected algorithm or key id")
    issuer = unverified.get("iss")
    clients = [client for pool_id, client in settings.COGNITO_POOLS if issuer_for(pool_id) == issuer]
    if not clients:
        raise TokenError("issuer is not one of our pools")
    key = _signing_key(issuer, header["kid"])
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer, audience=clients, leeway=LEEWAY,
                            options={"require": ["exp", "iss", "aud", "sub"]})
    except jwt.PyJWTError as exc:
        raise TokenError(f"rejected ({type(exc).__name__})") from exc
    if claims.get("token_use") != "id":
        raise TokenError("not an ID token")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise TokenError("no subject")
    return claims


def _role_for(user: User, groups: list) -> str:
    if set(groups) & set(settings.COGNITO_RC_GROUPS):
        return "rc"
    return "skipper" if user.managed_boats.exists() else "crew"


def account_for(claims: dict) -> User | None:
    """The local account for a verified token, created on first sign-in. Its role follows Cognito groups and boat links.

    None when the account has been disabled here (an administrator can switch a person off in the site admin)."""
    issuer, sub = claims["iss"], claims["sub"]
    groups = claims.get("cognito:groups") or []
    if not isinstance(groups, list):
        groups = []
    ident = ExternalIdentity.objects.select_related("user").filter(issuer=issuer, subject=sub).first()
    if ident is None:
        username = f"cognito-{hashlib.sha256(issuer.encode()).hexdigest()[:6]}-{sub}"[:150]
        try:
            with transaction.atomic():
                user = User(username=username)
                user.set_unusable_password()
                user.save()
                ident = ExternalIdentity.objects.create(user=user, issuer=issuer, subject=sub)
        except IntegrityError:                                       # two first requests at once: the other one won
            ident = ExternalIdentity.objects.select_related("user").get(issuer=issuer, subject=sub)
    user = ident.user
    if not user.is_active:
        return None
    email = str(claims.get("email") or "")[:254]
    name = str(claims.get("name") or " ".join(filter(None, [claims.get("given_name"), claims.get("family_name")])))[:150]
    if (user.email, user.first_name) != (email, name):
        user.email, user.first_name = email, name
        user.save(update_fields=["email", "first_name"])
    role = _role_for(user, groups)
    profile, _ = AccountProfile.objects.get_or_create(user=user, defaults={"role": role})
    if profile.role != role or profile.must_change_password:
        profile.role, profile.must_change_password = role, False
        profile.save(update_fields=["role", "must_change_password"])
    user.auth_profile = profile       # the signal that made a new user's default profile left a stale copy cached
    return user


def user_from_request(request) -> User | None:
    """The account behind `Authorization: Bearer <ID token>`, or None for anything else."""
    parts = (request.headers.get("Authorization") or "").split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        return account_for(verify_id_token(parts[1]))
    except TokenError as exc:
        log.info("event=cognito_token_refused reason=%s", exc)
        return None
