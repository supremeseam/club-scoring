"""Optional Cognito sign-in: tokens are checked on every request, accounts follow Cognito, passwords are off."""
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import User
from django.test import Client

from accounts import cognito
from accounts.models import AccountProfile, ExternalIdentity
from boats.models import Boat
from crew.models import BoatManager
from racing.models import Race, Series

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parent.parent
POOL, CLIENT = "us-west-2_AbCdEf123", "clientmembers1a2b3c"
ADMIN_POOL, ADMIN_CLIENT = "us-west-2_AdminPool9", "clientadmins4d5e6f"
ISSUER = f"https://cognito-idp.us-west-2.amazonaws.com/{POOL}"
ADMIN_ISSUER = f"https://cognito-idp.us-west-2.amazonaws.com/{ADMIN_POOL}"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEYS = {"k1": _key(), "other": _key()}


def _jwks(*kids):
    out = []
    for kid in kids:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(KEYS[kid].public_key(), as_dict=True)
        out.append({**jwk, "kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": out}


@pytest.fixture(autouse=True)
def cognito_mode(settings, monkeypatch):
    settings.AUTH_MODE = "cognito"
    settings.COGNITO_POOLS = [(POOL, CLIENT), (ADMIN_POOL, ADMIN_CLIENT)]
    settings.COGNITO_RC_GROUPS = ["admins"]
    settings.COGNITO_SIGN_IN_URL = "/members/"
    settings.COGNITO_TOKEN_STORAGE_KEYS = ["ayc.admin.session", "ayc.member.session"]
    cognito.reset_cache()
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return _jwks("k1")

    monkeypatch.setattr(cognito, "fetch_jwks", fake_fetch)
    return calls


def token(sub="11111111-aaaa-bbbb-cccc-000000000001", *, kid="k1", signing="k1", iss=ISSUER, aud=CLIENT, use="id",
          groups=None, exp=3600, email="sam@example.org", name="Sam Sailor", alg="RS256", **extra):
    now = int(time.time())
    claims = {"sub": sub, "iss": iss, "aud": aud, "token_use": use, "iat": now, "exp": now + exp,
              "email": email, "email_verified": True, "name": name, **extra}
    if groups is not None:
        claims["cognito:groups"] = groups
    return jwt.encode(claims, KEYS[signing], algorithm=alg, headers={"kid": kid})


def get(path, tok=None, client=None):
    c = client or Client()
    return c.get(path, HTTP_AUTHORIZATION=f"Bearer {tok}") if tok else c.get(path)


def post(path, body=None, tok=None, client=None):
    c = client or Client()
    extra = {"HTTP_AUTHORIZATION": f"Bearer {tok}"} if tok else {}
    return c.post(path, json.dumps(body or {}), content_type="application/json", **extra)


# ---- a valid sign-in ------------------------------------------------------------------------------------------
def test_valid_id_token_creates_a_crew_account_once(cognito_mode):
    me = get("/api/auth/me", token()).json()
    assert me["role"] == "crew" and me["is_admin"] is False and me["manages_boats"] is False
    assert me["display_name"] == "Sam Sailor"
    assert get("/api/auth/me", token()).status_code == 200
    assert User.objects.count() == 1
    u = User.objects.get()
    assert u.email == "sam@example.org" and u.first_name == "Sam Sailor" and not u.has_usable_password()
    ident = ExternalIdentity.objects.get(user=u)
    assert ident.subject == "11111111-aaaa-bbbb-cccc-000000000001" and ident.issuer == ISSUER


def test_both_pools_are_accepted_and_keep_separate_accounts():
    a = token(sub="m-1", iss=ISSUER, aud=CLIENT)
    b = token(sub="m-1", iss=ADMIN_ISSUER, aud=ADMIN_CLIENT, groups=["admins"])
    assert get("/api/auth/me", a).status_code == 200 and get("/api/auth/me", b).status_code == 200
    assert User.objects.count() == 2


def test_keys_are_fetched_once_and_again_only_for_an_unknown_key_id(cognito_mode, monkeypatch):
    get("/api/auth/me", token())
    get("/api/auth/me", token())
    assert len(cognito_mode) == 1
    KEYS["k2"] = _key()
    monkeypatch.setattr(cognito, "MIN_REFETCH_SECONDS", 0)
    monkeypatch.setattr(cognito, "fetch_jwks", lambda url: (cognito_mode.append(url), _jwks("k1", "k2"))[1])
    assert get("/api/auth/me", token(kid="k2", signing="k2")).status_code == 200
    assert len(cognito_mode) == 2


# ---- rejected tokens -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label, kw", [
    ("expired", {"exp": -10}),
    ("wrong audience", {"aud": "someone-else"}),
    ("wrong issuer", {"iss": "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_Unknown"}),
    ("signed by another key", {"signing": "other"}),
    ("unknown key id", {"kid": "nope", "signing": "other"}),
    ("access token", {"use": "access"}),
    ("no subject", {"sub": ""}),
])
def test_bad_tokens_are_refused(label, kw):
    assert get("/api/auth/me", token(**kw)).status_code == 401, label
    assert User.objects.count() == 0


def test_symmetric_and_unsigned_tokens_are_refused():
    claims = {"sub": "x", "iss": ISSUER, "aud": CLIENT, "token_use": "id", "exp": int(time.time()) + 600}
    assert get("/api/auth/me", jwt.encode(claims, "secret" * 8, algorithm="HS256", headers={"kid": "k1"})).status_code == 401
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"})
    assert get("/api/auth/me", unsigned).status_code == 401


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer not.a.jwt", "Basic abc", "Bearer a b"])
def test_malformed_authorization_headers_are_refused(header):
    r = Client().get("/api/auth/me", HTTP_AUTHORIZATION=header) if header else Client().get("/api/auth/me")
    assert r.status_code == 401


def test_a_network_failure_fetching_keys_refuses_rather_than_trusts(monkeypatch):
    def boom(url):
        raise OSError("down")
    monkeypatch.setattr(cognito, "fetch_jwks", boom)
    assert get("/api/auth/me", token()).status_code == 401


# ---- roles ---------------------------------------------------------------------------------------------------
def test_admins_group_is_race_committee_and_others_are_not():
    boss = token(sub="boss", groups=["admins"])
    assert get("/api/auth/me", boss).json()["role"] == "rc"
    assert get("/api/manage/boats", boss).status_code == 200
    assert get("/api/manage/boats", token(sub="plain")).status_code == 403
    assert get("/api/manage/boats", token(sub="other", groups=["members"])).status_code == 403


def test_losing_the_admins_group_loses_committee_access_on_the_next_request():
    assert get("/api/manage/boats", token(sub="boss", groups=["admins"])).status_code == 200
    assert get("/api/manage/boats", token(sub="boss", groups=[])).status_code == 403
    assert get("/api/auth/me", token(sub="boss")).json()["role"] == "crew"


def test_committee_links_a_boat_to_a_signed_in_person_who_then_manages_its_crew():
    Boat.objects.create(name="Alba", sail_number="12", skipper="Sam")
    boat = Boat.objects.get(name="Alba")
    sam = token(sub="sam")
    assert get("/api/auth/me", sam).json()["role"] == "crew"
    assert get("/api/crew/skipper/overview", sam).status_code == 403
    boss = token(sub="boss", groups=["admins"])
    sam_id = User.objects.get(external_identity__subject="sam").id
    r = post("/api/manage/crew/skippers/link", {"user_id": sam_id, "boat_id": boat.id}, boss)
    assert r.status_code == 200, r.content
    me = get("/api/auth/me", sam).json()
    assert me["role"] == "skipper" and me["manages_boats"] is True
    assert [b["name"] for b in get("/api/crew/skipper/overview", sam).json()["boats"]] == ["Alba"]
    assert get("/api/manage/boats", sam).status_code == 403


def test_a_committee_member_with_a_linked_boat_stays_committee():
    boat = Boat.objects.create(name="Cygnus", sail_number="56", skipper="Rae")
    boss = token(sub="boss", groups=["admins"])
    get("/api/auth/me", boss)
    BoatManager.objects.create(user=User.objects.get(), boat=boat)
    me = get("/api/auth/me", boss).json()
    assert me["role"] == "rc" and me["manages_boats"] is True
    assert get("/api/crew/skipper/overview", boss).status_code == 200


def test_the_signed_in_person_sees_only_their_own_signups():
    ser = Series.objects.create(name="Wed", season=2026, status="active")
    Race.objects.create(series=ser, number=1, date=date.today() + timedelta(days=3))
    assert get("/api/crew/my/signups", token(sub="sam")).json() == []


# ---- no cookies, no passwords --------------------------------------------------------------------------------
def test_django_session_logins_do_not_work_in_cognito_mode():
    u = User.objects.create_user("legacy", password="x" * 20)
    AccountProfile.objects.update_or_create(user=u, defaults={"role": "rc"})
    c = Client()
    c.force_login(u)
    assert c.get("/api/manage/boats").status_code == 401


def test_password_endpoints_are_switched_off():
    boss = token(sub="boss", groups=["admins"])
    for url, body, tok in [
        ("/api/auth/login", {"username": "a", "password": "b"}, None),
        ("/api/auth/change-password", {"current_password": "a", "new_password": "b"}, token()),
        ("/api/crew/register", {"username": "x", "password": "y" * 20, "name": "n", "email": "a@b.org"}, None),
        ("/api/manage/crew/skippers", {"username": "s", "password": "p" * 20, "boat_ids": [1]}, boss),
        ("/api/manage/crew/skipper-requests/1/approve", {"username": "s", "password": "p" * 20, "boat_ids": [1]}, boss),
    ]:
        r = post(url, body, tok)
        assert r.status_code == 404 and "sign-in" in r.json()["detail"], url


def test_bearer_tokens_are_ignored_in_password_mode(settings):
    settings.AUTH_MODE = "password"
    assert get("/api/auth/me", token()).status_code == 401
    assert User.objects.count() == 0


# ---- what the app tells the browser -----------------------------------------------------------------------------
def test_config_tells_the_browser_how_to_sign_in(settings):
    cfg = Client().get("/api/config").json()
    assert cfg["auth_mode"] == "cognito" and cfg["sign_in_url"] == "/members/"
    assert cfg["token_storage_keys"] == ["ayc.admin.session", "ayc.member.session"]
    settings.AUTH_MODE = "password"
    assert Client().get("/api/config").json()["auth_mode"] == "password"


# ---- configuration is validated at start-up -----------------------------------------------------------------------
def _settings_with(**env) -> subprocess.CompletedProcess:
    full = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **env}
    code = "from django.conf import settings as s; print(s.AUTH_MODE, s.COGNITO_POOLS, s.COGNITO_RC_GROUPS)"
    return subprocess.run([sys.executable, "-c", code], env=full, cwd=BACKEND, capture_output=True, text=True)


def test_settings_parse_pools_and_groups():
    out = _settings_with(AUTH_MODE="cognito", COGNITO_POOLS=f"{POOL}:{CLIENT}, {ADMIN_POOL}:{ADMIN_CLIENT}",
                         COGNITO_RC_GROUPS="admins,rc")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == f"cognito [('{POOL}', '{CLIENT}'), ('{ADMIN_POOL}', '{ADMIN_CLIENT}')] ['admins', 'rc']"


@pytest.mark.parametrize("env", [
    {"AUTH_MODE": "cognito"},
    {"AUTH_MODE": "cognito", "COGNITO_POOLS": "not-a-pool-id:client"},
    {"AUTH_MODE": "cognito", "COGNITO_POOLS": f"{POOL}"},
    {"AUTH_MODE": "magic"},
])
def test_settings_refuse_incomplete_or_unknown_auth_configuration(env):
    assert _settings_with(**env).returncode != 0


def test_password_mode_is_the_default():
    out = _settings_with(AUTH_MODE="")
    assert out.returncode == 0 and out.stdout.startswith("password")
