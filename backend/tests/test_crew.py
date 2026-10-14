"""Crew board: roles stay separate, contact details stay private, anonymous writes are limited."""
import json
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client

from accounts.models import AccountProfile
from boats.models import Boat
from crew.models import BoatManager, CrewPosting, CrewSignup, PublicAction
from racing.models import Race, Series

pytestmark = pytest.mark.django_db
PASSWORD = "correct horse battery staple"


def client():
    c = Client(enforce_csrf_checks=True)
    c.csrf = c.get("/api/auth/csrf").json()["csrfToken"]
    return c


def call(c, method, url, body=None):
    kw = {"content_type": "application/json", "HTTP_X_CSRFTOKEN": c.csrf}
    return getattr(c, method)(url, json.dumps(body) if body is not None else None, **kw) if method != "get" \
        else c.get(url)


def sign_in(username, password=PASSWORD):
    c = client()
    r = call(c, "post", "/api/auth/login", {"username": username, "password": password})
    assert r.status_code == 200, r.content
    c.csrf = c.cookies["csrftoken"].value
    return c


def make_user(username, role, boats=()):
    u = User.objects.create_user(username=username, password=PASSWORD)
    AccountProfile.objects.update_or_create(user=u, defaults={"role": role})
    for b in boats:
        BoatManager.objects.create(user=u, boat=b)
    return u


@pytest.fixture
def world():
    ser = Series.objects.create(name="Wednesday Night", season=2026, status="active")
    race = Race.objects.create(series=ser, number=1, date=date.today() + timedelta(days=3))
    mine = Boat.objects.create(name="Alba", sail_number="12", skipper="Sam Skipper")
    other = Boat.objects.create(name="Brisa", sail_number="34", skipper="Olly Other")
    make_user("sam", "skipper", [mine])
    make_user("olly", "skipper", [other])
    make_user("rc", "rc")
    return {"race": race, "mine": mine, "other": other}


def signup(c, **kw):
    body = {"name": "Casey Crew", "email": "casey@example.org", "phone": "555-0100", "message": "hi", **kw}
    return call(c, "post", "/api/crew/signups", body)


# ---- roles ---------------------------------------------------------------------------------------------------
def test_skipper_and_crew_cannot_touch_race_committee_endpoints(world):
    make_user("cathy", "crew")
    for who in ("sam", "cathy"):
        c = sign_in(who)
        for method, url in [("get", "/api/manage/boats"), ("get", "/api/manage/series"),
                            ("get", "/api/manage/crew/signups"), ("get", "/api/manage/fleets")]:
            assert call(c, method, url).status_code == 403, (who, url)
        assert call(c, "post", "/api/manage/fleets", {"name": "x"}).status_code == 403


def test_race_committee_cannot_use_skipper_endpoints_and_can_use_manage(world):
    c = sign_in("rc")
    assert call(c, "get", "/api/crew/skipper/overview").status_code == 403
    assert call(c, "get", "/api/manage/crew/signups").status_code == 200


def test_crew_cannot_use_skipper_endpoints(world):
    make_user("cathy", "crew")
    assert call(sign_in("cathy"), "get", "/api/crew/skipper/overview").status_code == 403


def test_me_reports_role_and_badge(world):
    su = signup(client(), boat_id=world["mine"].id)
    assert su.status_code == 200
    me = call(sign_in("sam"), "get", "/api/auth/me").json()
    assert me["role"] == "skipper" and me["unseen_requests"] == 1 and me["is_admin"] is False


def test_skipper_with_temporary_password_is_blocked_until_changed(world):
    AccountProfile.objects.filter(user__username="sam").update(must_change_password=True)
    c = sign_in("sam")
    r = call(c, "get", "/api/crew/skipper/overview")
    assert r.status_code == 403 and "password_change_required" in r.content.decode()


# ---- skipper scope -------------------------------------------------------------------------------------------
def test_skipper_edits_only_own_boat(world):
    c = sign_in("sam")
    ok = call(c, "put", f"/api/crew/skipper/boats/{world['mine'].id}/info",
              {"notes": "Friendly crew", "contact_preference": "app"})
    assert ok.status_code == 200
    assert call(c, "put", f"/api/crew/skipper/boats/{world['other'].id}/info", {"notes": "hack"}).status_code == 404
    assert call(c, "post", f"/api/crew/skipper/boats/{world['other'].id}/postings", {"role": "x"}).status_code == 404


def test_skipper_cannot_change_boat_data_or_other_postings(world):
    c = sign_in("sam")
    p = call(c, "post", f"/api/crew/skipper/boats/{world['mine'].id}/postings", {"role": "Bow", "spots": 2}).json()
    foreign = CrewPosting.objects.create(boat=world["other"], role="Trim")
    assert call(c, "put", f"/api/crew/skipper/postings/{foreign.id}", {"role": "owned"}).status_code == 404
    assert call(c, "delete", f"/api/crew/skipper/postings/{foreign.id}").status_code == 404
    assert call(c, "put", f"/api/crew/skipper/postings/{p['id']}", {"role": "Mast", "spots": 1}).status_code == 200
    world["mine"].refresh_from_db()
    assert (world["mine"].name, world["mine"].sail_number) == ("Alba", "12")


def test_skipper_sees_and_answers_only_their_boats_signups(world):
    anon = client()
    signup(anon, boat_id=world["mine"].id)
    signup(anon, boat_id=world["other"].id, email="b@example.org")
    c = sign_in("sam")
    rows = call(c, "get", "/api/crew/skipper/signups").json()
    assert [r["boat"] for r in rows] == ["Alba"] and rows[0]["email"] == "casey@example.org"
    foreign = CrewSignup.objects.get(boat=world["other"])
    assert call(c, "post", f"/api/crew/skipper/signups/{foreign.id}/respond", {"status": "accepted"}).status_code == 404
    mine = CrewSignup.objects.get(boat=world["mine"])
    assert call(c, "post", f"/api/crew/skipper/signups/{mine.id}/respond", {"status": "accepted"}).status_code == 200
    assert call(c, "get", "/api/auth/me").json()["unseen_requests"] == 0


def test_race_wide_volunteers_visible_only_with_open_posting_for_that_race(world):
    signup(client(), race_id=world["race"].id)
    sam = sign_in("sam")
    assert call(sam, "get", "/api/crew/skipper/signups").json() == []
    call(sam, "post", f"/api/crew/skipper/boats/{world['mine'].id}/postings", {"race_id": world["race"].id})
    assert len(call(sam, "get", "/api/crew/skipper/signups").json()) == 1
    assert call(sign_in("olly"), "get", "/api/crew/skipper/signups").json() == []


# ---- privacy ---------------------------------------------------------------------------------------------------
def test_public_board_never_leaks_sailor_details(world):
    CrewPosting.objects.create(boat=world["mine"], role="Bow", race=world["race"])
    signup(client(), boat_id=world["mine"].id, name="Secret Sailor", email="leak@example.org", phone="555-9999")
    body = client().get("/api/crew/board").content.decode()
    assert "Alba" in body and "Bow" in body
    for secret in ("Secret Sailor", "leak@example.org", "555-9999", "casey"):
        assert secret not in body
    assert "email" not in body and "phone" not in body


def test_status_check_needs_the_secret_token_and_reveals_contact_only_when_accepted(world):
    from crew.models import BoatCrewInfo
    BoatCrewInfo.objects.create(boat=world["mine"], contact_name="Sam", contact_email="sam@example.org",
                                contact_phone="555-1", contact_preference="email")
    anon = client()
    tok = signup(anon, boat_id=world["mine"].id).json()["token"]
    first = call(anon, "post", "/api/crew/signups/status", {"token": tok}).json()
    assert first["status"] == "pending" and "skipper_contact" not in first
    assert call(anon, "post", "/api/crew/signups/status", {"token": "not-a-token"}).status_code == 404
    CrewSignup.objects.update(status="accepted")
    got = call(anon, "post", "/api/crew/signups/status", {"token": tok}).json()
    assert got["skipper_contact"] == {"name": "Sam", "email": "sam@example.org"}      # the chosen route only


def test_withdraw_with_token(world):
    anon = client()
    tok = signup(anon, boat_id=world["mine"].id).json()["token"]
    assert call(anon, "post", "/api/crew/signups/withdraw", {"token": tok}).json()["status"] == "withdrawn"


# ---- abuse protection --------------------------------------------------------------------------------------------
def test_signup_requires_csrf(world):
    c = Client(enforce_csrf_checks=True)
    r = c.post("/api/crew/signups", json.dumps({"name": "a", "email": "a@b.co", "boat_id": world["mine"].id}),
               content_type="application/json")
    assert r.status_code == 403 and CrewSignup.objects.count() == 0


def test_honeypot_stores_nothing(world):
    r = signup(client(), boat_id=world["mine"].id, website="http://spam.example")
    assert r.status_code == 200 and CrewSignup.objects.count() == 0


def test_signup_rate_limited_per_address(world):
    c = client()
    for i in range(6):
        assert signup(c, boat_id=world["mine"].id, email=f"p{i}@example.org").status_code == 200
    assert signup(c, boat_id=world["mine"].id, email="late@example.org").status_code == 429
    assert PublicAction.objects.filter(kind="signup").count() == 6


def test_validation_and_duplicates(world):
    c = client()
    assert signup(c, boat_id=world["mine"].id, email="not-an-email").status_code == 422
    assert signup(c, boat_id=world["mine"].id, name="  ").status_code == 422
    assert signup(c, boat_id=9999).status_code == 404
    assert signup(c, boat_id=world["mine"].id).status_code == 200
    assert signup(c, boat_id=world["mine"].id).status_code == 409


def test_cannot_sign_up_to_a_closed_posting_or_draft_race(world):
    closed = CrewPosting.objects.create(boat=world["mine"], is_open=False)
    assert signup(client(), posting_id=closed.id).status_code == 404
    Series.objects.update(status="draft")
    assert signup(client(), race_id=world["race"].id).status_code == 404


# ---- accounts ------------------------------------------------------------------------------------------------------
def test_crew_registration_makes_a_crew_role_never_rc(world):
    c = client()
    r = call(c, "post", "/api/crew/register", {"username": "casey", "password": PASSWORD, "name": "Casey",
                                               "email": "casey@example.org"})
    assert r.status_code == 200
    u = User.objects.get(username="casey")
    assert u.auth_profile.role == "crew" and not u.is_staff and not u.is_superuser
    assert call(c, "get", "/api/auth/me").json()["role"] == "crew"
    assert call(c, "get", "/api/manage/boats").status_code == 403


def test_crew_registration_enforces_password_policy_and_unique_names(world):
    c = client()
    base = {"username": "casey", "name": "Casey", "email": "casey@example.org"}
    assert call(c, "post", "/api/crew/register", {**base, "password": "short"}).status_code == 422
    assert call(c, "post", "/api/crew/register", {**base, "username": "SAM", "password": PASSWORD}).status_code == 409


def test_crew_account_sees_and_withdraws_only_own_signups(world):
    c = client()
    call(c, "post", "/api/crew/register", {"username": "casey", "password": PASSWORD, "name": "Casey",
                                           "email": "casey@example.org"})
    c.csrf = c.cookies["csrftoken"].value
    signup(c, boat_id=world["mine"].id)
    signup(client(), boat_id=world["other"].id, email="x@example.org")               # someone else's
    rows = call(c, "get", "/api/crew/my/signups").json()
    assert len(rows) == 1 and rows[0]["boat"] == "Alba"
    stranger = CrewSignup.objects.get(boat=world["other"])
    assert call(c, "post", f"/api/crew/my/signups/{stranger.id}/withdraw").status_code == 404
    assert call(c, "post", f"/api/crew/my/signups/{rows[0]['id']}/withdraw").status_code == 200


# ---- race committee ---------------------------------------------------------------------------------------------------
def test_rc_creates_skipper_with_temporary_password_and_boat_link(world):
    c = sign_in("rc")
    r = call(c, "post", "/api/manage/crew/skippers",
             {"username": "newskip", "password": PASSWORD, "boat_ids": [world["other"].id]})
    assert r.status_code == 200, r.content
    u = User.objects.get(username="newskip")
    assert u.auth_profile.role == "skipper" and u.auth_profile.must_change_password
    assert list(BoatManager.objects.filter(user=u).values_list("boat_id", flat=True)) == [world["other"].id]
    weak = call(c, "post", "/api/manage/crew/skippers", {"username": "w", "password": "short", "boat_ids": [1]})
    assert weak.status_code == 422


def test_skipper_request_then_approval(world):
    anon = client()
    r = call(anon, "post", "/api/crew/skipper-requests",
             {"name": "New Skip", "email": "ns@example.org", "boat_id": world["other"].id})
    assert r.status_code == 200
    again = call(anon, "post", "/api/crew/skipper-requests", {"name": "N", "email": "ns@example.org", "boat_id": 1})
    assert again.status_code == 409
    rc = sign_in("rc")
    req = call(rc, "get", "/api/manage/crew/skipper-requests").json()[0]
    ok = call(rc, "post", f"/api/manage/crew/skipper-requests/{req['id']}/approve",
              {"username": "ns", "password": PASSWORD, "boat_ids": [world["other"].id]})
    assert ok.status_code == 200
    assert call(rc, "get", "/api/manage/crew/skipper-requests").json() == []


def test_rc_sees_contact_details_and_can_moderate(world):
    signup(client(), boat_id=world["mine"].id)
    rc = sign_in("rc")
    rows = call(rc, "get", "/api/manage/crew/signups").json()
    assert rows[0]["email"] == "casey@example.org"
    assert call(rc, "delete", f"/api/manage/crew/signups/{rows[0]['id']}").status_code == 200
    assert CrewSignup.objects.count() == 0


def test_anonymous_cannot_reach_protected_crew_endpoints(world):
    c = client()
    for url in ("/api/crew/skipper/overview", "/api/crew/my/signups", "/api/manage/crew/signups"):
        assert call(c, "get", url).status_code == 401


def test_accepted_requests_fill_spots_on_the_public_board(world):
    p = CrewPosting.objects.create(boat=world["mine"], role="Bow", spots=2)
    anon = client()
    signup(anon, posting_id=p.id)
    signup(anon, posting_id=p.id, email="two@example.org")
    row = client().get("/api/crew/board").json()["boats"][0]["postings"][0]
    assert (row["interested"], row["spots"]) == (2, 2)
    sam = sign_in("sam")
    for su in CrewSignup.objects.all():
        call(sam, "post", f"/api/crew/skipper/signups/{su.id}/respond", {"status": "accepted"})
    assert client().get("/api/crew/board").json()["boats"] == []            # full: no longer listed
    CrewSignup.objects.filter(email="two@example.org").update(status="declined")
    row = client().get("/api/crew/board").json()["boats"][0]["postings"][0]
    assert (row["interested"], row["spots"]) == (0, 1)


def test_offer_to_crew_anywhere_is_visible_only_to_skippers_with_an_open_posting(world):
    assert signup(client()).status_code == 200                                    # any boat, any race
    assert client().get("/api/crew/board").json()["open_to_any"] == 1
    assert "casey@example.org" not in client().get("/api/crew/board").content.decode()
    assert call(sign_in("sam"), "get", "/api/crew/skipper/signups").json() == []
    sam = sign_in("sam")
    call(sam, "post", f"/api/crew/skipper/boats/{world['mine'].id}/postings", {"role": "Bow"})
    assert len(call(sam, "get", "/api/crew/skipper/signups").json()) == 1
    assert call(sign_in("olly"), "get", "/api/crew/skipper/signups").json() == []


def test_only_boats_with_a_skipper_login_can_be_signed_up_to(world):
    lone = Boat.objects.create(name="Unregistered", sail_number="99")
    opts = client().get("/api/crew/options").json()
    assert {b["name"] for b in opts["boats"]} == {"Alba", "Brisa"}
    assert "Unregistered" in {b["name"] for b in opts["all_boats"]}               # still pickable by a new skipper
    assert signup(client(), boat_id=lone.id).status_code == 404


def test_spots_left_updates_for_boat_level_signups_too(world):
    sam = sign_in("sam")
    p = call(sam, "post", f"/api/crew/skipper/boats/{world['mine'].id}/postings", {"role": "Bow", "spots": 2}).json()
    su = CrewSignup.objects.create(boat=world["mine"], name="N", email="n@example.org")   # no opening chosen
    call(sam, "post", f"/api/crew/skipper/signups/{su.id}/respond", {"status": "accepted"})
    assert client().get("/api/crew/board").json()["boats"][0]["postings"][0]["spots"] == 1
    mine = call(sam, "get", "/api/crew/skipper/overview").json()["boats"][0]["postings"][0]
    assert (mine["spots"], mine["filled"]) == (2, 1)
    assert p["filled"] == 0
