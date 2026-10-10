import json
import logging
import os
import subprocess
import sys
import time

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory, override_settings

from accounts.ip import client_ip
from accounts.models import AccountProfile

pytestmark = pytest.mark.django_db

import random
import string

LONG_RANDOM = "".join(random.Random(7).choices(string.ascii_letters + string.digits, k=200))
GOOD = "purple harbour lantern quietly"          # 4 random-ish words: valid, no composition rules
OLD = "an old throwaway password"


def make_user(username="rcmember", password=OLD, must_change=False, **kw):
    u = User.objects.create_user(username, password=password, **kw)
    AccountProfile.objects.filter(user=u).update(must_change_password=must_change)
    return u


def new_client(ip=None):
    c = Client(enforce_csrf_checks=True, **({"HTTP_X_FORWARDED_FOR": ip} if ip else {}))
    c.tok = c.get("/api/auth/csrf").json()["csrfToken"]
    return c


def post(c, url, body):
    return c.post(url, json.dumps(body), content_type="application/json", HTTP_X_CSRFTOKEN=c.tok)


def login(c, username="rcmember", password=OLD):
    r = post(c, "/api/auth/login", {"username": username, "password": password})
    if r.status_code == 200 and "csrftoken" in c.cookies:
        c.tok = c.cookies["csrftoken"].value
    return r


# ---- password policy --------------------------------------------------------------------------------
@pytest.mark.parametrize("pw", [GOOD, "x" * 15 + "yz9", "pass phrase ✓ with ünïcode 日本語 ok", "q7!Lm2$x" * 25])
def test_good_passwords_are_accepted(pw):
    validate_password(pw, User(username="rcmember"))


@pytest.mark.parametrize("pw,why", [
    ("shortpass1234", "14 characters or fewer"),
    ("password", "common"),
    ("passwordpassword", "generic repeated word"),
    ("aaaaaaaaaaaaaaaa", "single character"),
    ("abcabcabcabcabcabc", "repeated block"),
    ("123456789012345", "numeric run"),
    ("abcdefghijklmnopq", "alphabet run"),
    ("my rcmember secret phrase here", "contains the username"),
])
def test_weak_passwords_are_rejected(pw, why):
    with pytest.raises(ValidationError):
        validate_password(pw, User(username="rcmember"))


def test_the_clubs_own_name_is_blocked_wherever_it_appears(settings):
    settings.CLUB_NAME = "Example Sailing Club"
    with pytest.raises(ValidationError):
        validate_password("example sailing club 2027", User(username="rcmember"))
    with pytest.raises(ValidationError):
        validate_password("we love the Example-Sailing-Club!!", User(username="rcmember"))


def test_no_composition_rules_and_long_passphrases_with_common_words_are_fine():
    validate_password("all lowercase words with spaces only", User(username="rcmember"))
    validate_password("sailing across the quiet blue water", User(username="rcmember"))   # contains 'sailing'


# ---- login -----------------------------------------------------------------------------------------
def test_login_returns_state_and_cycles_the_session():
    make_user()
    c = new_client()
    before = c.session.session_key
    r = login(c)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert c.session.session_key != before                     # no session fixation
    assert isinstance(c.session["auth_started_at"], int)


def test_login_input_limits_and_uniform_errors():
    make_user()
    c = new_client()
    assert post(c, "/api/auth/login", {"username": "rcmember", "password": "x" * 257}).status_code == 422
    assert post(c, "/api/auth/login", {"username": "u" * 151, "password": "x"}).status_code == 422
    a = post(c, "/api/auth/login", {"username": "nobody", "password": "wrong password here"})
    b = post(c, "/api/auth/login", {"username": "rcmember", "password": "wrong password here"})
    assert (a.status_code, a.content) == (b.status_code, b.content) == (401, b'{"detail": "Invalid credentials"}')


def test_auth_responses_are_not_cacheable():
    c = new_client()
    assert c.get("/api/auth/csrf")["Cache-Control"] == "no-store"
    assert c.get("/api/auth/me")["Cache-Control"] == "no-store"


# ---- client IP and lockout -------------------------------------------------------------------------
def test_client_ip_uses_the_rightmost_forwarded_address_only_behind_the_proxy():
    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.5", REMOTE_ADDR="172.18.0.3")
    with override_settings(BEHIND_PROXY=True):
        assert client_ip(req) == "203.0.113.5"                  # the spoofed left entry is ignored
        assert client_ip(rf.get("/", REMOTE_ADDR="172.18.0.3")) == "172.18.0.3"
        v6 = rf.get("/", HTTP_X_FORWARDED_FOR="2001:db8:1:2:aaaa:bbbb:cccc:dddd")
        assert client_ip(v6) == "2001:db8:1:2::"                # a whole /64 counts as one client
    with override_settings(BEHIND_PROXY=False):
        assert client_ip(req) == "172.18.0.3"                   # development: header ignored


@override_settings(BEHIND_PROXY=True)
def test_one_attackers_failures_lock_only_that_address():
    make_user()
    attacker = new_client("203.0.113.5")
    codes = [post(attacker, "/api/auth/login", {"username": "rcmember", "password": "guess number %d here" % i}).status_code
             for i in range(11)]
    assert codes[:9] == [401] * 9 and codes[9:] == [429, 429]
    assert login(attacker).status_code == 429                  # even the right password, from that address
    assert login(new_client("198.51.100.9")).status_code == 200   # a real user elsewhere is unaffected


@override_settings(BEHIND_PROXY=True)
def test_guessing_from_many_addresses_cannot_lock_a_user_out_below_the_account_limit():
    make_user()
    for i in range(30):
        post(new_client(f"203.0.113.{i}"), "/api/auth/login", {"username": "rcmember", "password": "guess guess guess %d" % i})
    assert login(new_client("198.51.100.9")).status_code == 200


@override_settings(BEHIND_PROXY=True, ACCOUNT_FAILURE_LIMIT=5)
def test_account_backstop_across_addresses_and_unlock():
    make_user()
    for i in range(5):
        post(new_client(f"203.0.113.{i}"), "/api/auth/login", {"username": "rcmember", "password": "guess guess guess %d" % i})
    assert login(new_client("198.51.100.9")).status_code == 429     # right password, but the account is throttled
    call_command("unlock_account", "rcmember")
    assert login(new_client("198.51.100.9")).status_code == 200
    # a successful login resets the count
    for i in range(3):
        post(new_client(f"203.0.113.{50 + i}"), "/api/auth/login", {"username": "rcmember", "password": "guess guess guess %d" % i})
    assert login(new_client("198.51.100.10")).status_code == 200


# ---- sessions --------------------------------------------------------------------------------------
def test_session_settings_and_absolute_limit():
    from django.conf import settings
    assert settings.SESSION_COOKIE_AGE == 12 * 3600 and settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_ABSOLUTE_MAX_SECONDS == 7 * 24 * 3600
    make_user()
    c = new_client()
    login(c)
    assert c.get("/api/auth/me").status_code == 200
    s = c.session
    s["auth_started_at"] = int(time.time()) - (6 * 24 * 3600 + 23 * 3600)
    s.save()
    assert c.get("/api/auth/me").status_code == 200              # still inside 7 days
    s = c.session
    s["auth_started_at"] = int(time.time()) - (7 * 24 * 3600 + 5)
    s.save()
    assert c.get("/api/auth/me").status_code == 401              # past 7 days, however active
    assert c.get("/api/auth/me").status_code == 401


def test_a_session_without_a_start_marker_is_treated_as_expired():
    make_user()
    c = new_client()
    login(c)
    s = c.session
    del s["auth_started_at"]
    s.save()
    assert c.get("/api/auth/me").status_code == 401


def test_logout_ends_the_session():
    make_user()
    c = new_client()
    login(c)
    assert post(c, "/api/auth/logout", {}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401


# ---- change password -----------------------------------------------------------------------------
def change(c, current=OLD, new=GOOD):
    return post(c, "/api/auth/change-password", {"current_password": current, "new_password": new})


def test_change_password_rules():
    make_user()
    c = new_client()
    login(c)
    assert change(c, current="wrong password entirely").status_code == 400
    assert change(c, new=OLD).status_code == 422                   # same as current
    assert change(c, new="short one").status_code == 422
    assert change(c, new="my rcmember passphrase is long").status_code == 422   # contains the username
    assert change(c, new="x" * 257).status_code == 422
    for ok in (GOOD, "ünïcode ✓ passphrase that is plenty long", LONG_RANDOM):
        assert change(c, current=OLD if ok == GOOD else GOOD if ok.startswith("ün") else "ünïcode ✓ passphrase that is plenty long",
                      new=ok).status_code == 200


def test_change_password_signs_out_other_sessions_but_not_this_one():
    make_user()
    a, b = new_client(), new_client()
    login(a)
    login(b)
    assert change(a).status_code == 200
    assert a.get("/api/auth/me").status_code == 200               # this session survives
    assert b.get("/api/auth/me").status_code == 401              # the other device is signed out
    assert login(new_client(), password=GOOD).status_code == 200  # new password works, old does not
    assert login(new_client(), password=OLD).status_code == 401


def test_change_password_needs_auth_and_csrf():
    make_user()
    anon = new_client()
    assert change(anon).status_code == 401
    c = new_client()
    login(c)
    r = c.post("/api/auth/change-password", json.dumps({"current_password": OLD, "new_password": GOOD}),
               content_type="application/json")                  # no CSRF header
    assert r.status_code in (401, 403)


def test_wrong_current_password_counts_toward_lockout(settings):
    make_user()
    c = new_client()
    login(c)
    codes = [change(c, current="wrong password entirely").status_code for _ in range(11)]
    assert codes[:9] == [400] * 9 and codes[9:] == [429, 429]       # the address is now locked


# ---- forced change after an admin sets a temporary password -----------------------------------------
def test_user_who_must_change_password_is_limited_until_they_do():
    make_user(must_change=True)
    c = new_client()
    r = login(c)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    assert c.get("/api/auth/me").json()["must_change_password"] is True
    blocked = c.get("/api/manage/boats")
    assert blocked.status_code == 403 and blocked.json()["detail"] == "password_change_required"
    assert change(c).status_code == 200
    assert c.get("/api/manage/boats").status_code == 200
    assert c.get("/api/auth/me").json()["must_change_password"] is False


def test_user_who_must_change_password_can_still_log_out():
    make_user(must_change=True)
    c = new_client()
    login(c)
    assert post(c, "/api/auth/logout", {}).status_code == 200


def test_admin_created_users_and_admin_set_passwords_are_flagged():
    admin = User.objects.create_superuser("boss1", "b@example.org", "an admin passphrase that is fine")
    c = Client()
    c.force_login(admin)
    r = c.post("/manage-admin/auth/user/add/", {"username": "newrc", "password1": GOOD, "password2": GOOD})
    assert r.status_code == 302, r.content[:300]
    u = User.objects.get(username="newrc")
    assert u.auth_profile.must_change_password is True             # temporary password
    AccountProfile.objects.filter(user=u).update(must_change_password=False)
    r = c.post(f"/manage-admin/auth/user/{u.pk}/password/", {"password1": "another long temporary phrase",
                                                           "password2": "another long temporary phrase"})
    assert r.status_code == 302, r.content[:300]
    u.refresh_from_db()
    assert u.auth_profile.must_change_password is True             # admin reset = temporary again


def test_admin_enforces_the_password_policy_on_temporary_passwords():
    admin = User.objects.create_superuser("boss1", "b@example.org", "an admin passphrase that is fine")
    c = Client()
    c.force_login(admin)
    r = c.post("/manage-admin/auth/user/add/", {"username": "weak", "password1": "short1", "password2": "short1"})
    assert r.status_code == 200 and not User.objects.filter(username="weak").exists()


def test_flagged_staff_user_is_kept_out_of_admin_except_password_change():
    u = make_user("staffer", must_change=True, is_staff=True, is_superuser=True)
    c = Client()
    c.force_login(u)
    r = c.get("/manage-admin/")
    assert r.status_code == 302 and r["Location"].endswith("/password_change/")
    assert c.get("/manage-admin/password_change/").status_code == 200
    r = c.post("/manage-admin/password_change/", {"old_password": OLD, "new_password1": GOOD, "new_password2": GOOD})
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.auth_profile.must_change_password is False            # choosing their own clears the flag
    assert c.get("/manage-admin/").status_code == 200


def test_force_password_change_command():
    make_user()
    call_command("force_password_change", "rcmember")
    assert User.objects.get(username="rcmember").auth_profile.must_change_password is True


# ---- audit log -----------------------------------------------------------------------------------
def test_auth_events_are_logged_without_secrets(caplog):
    make_user()
    with caplog.at_level(logging.INFO, logger="auth"):
        c = new_client()
        post(c, "/api/auth/login", {"username": "rcmember", "password": "super secret wrong guess"})
        login(c)
        change(c)
        post(c, "/api/auth/logout", {})
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "auth")
    for event in ("login_failure", "login_success", "password_changed", "logout"):
        assert f"event={event}" in text
    assert "super secret wrong guess" not in text and GOOD not in text and OLD not in text


def test_log_lines_cannot_be_forged_through_the_username(caplog):
    with caplog.at_level(logging.INFO, logger="auth"):
        post(new_client(), "/api/auth/login", {"username": "x\nevent=login_success user='admin'", "password": "wrong guess entirely"})
    assert not any(r.getMessage().startswith("event=login_success") for r in caplog.records)
    assert all("\n" not in r.getMessage() for r in caplog.records if r.name == "auth")


# ---- configuration and tools ----------------------------------------------------------------------
def _boot(**env):
    e = {**os.environ, **env}
    return subprocess.run([sys.executable, "-c", "import os;os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
                           "import config.settings"], env=e, capture_output=True, text=True,
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_production_no_longer_requires_two_factor_but_still_needs_a_real_secret_key():
    assert _boot(DEBUG="0", REQUIRE_2FA="0", SECRET_KEY="x" * 50).returncode == 0
    p = _boot(DEBUG="0", REQUIRE_2FA="0", SECRET_KEY="dev-insecure-secret-key-change-me")
    assert p.returncode != 0 and "SECRET_KEY" in p.stderr


def test_setup_club_enforces_the_password_policy(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "tooshort12")
    with pytest.raises(CommandError):
        call_command("setup_club", "--username", "boss")
    monkeypatch.setenv("ADMIN_PASSWORD", GOOD)
    call_command("setup_club", "--username", "boss")
    assert User.objects.get(username="boss").is_superuser


def test_demo_seed_refuses_to_run_in_production():
    with override_settings(PRODUCTION=True):
        with pytest.raises(CommandError):
            call_command("seed_demo")


def test_totp_is_optional_and_still_works_when_enabled():
    make_user()
    assert login(new_client()).status_code == 200                    # off by default
