import io
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, override_settings
from pypdf import PdfReader

from boats.models import Boat, BoatRating, Fleet, RatingType
from racing.models import Finish, Race, Series, SeriesEntry, Start
from racing.ratings import resolve_rating

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    call_command("seed_demo")


def editor_client():
    User.objects.get_or_create(username="editor", defaults={"password": ""})[0]         .set_password("editor")
    u = User.objects.get(username="editor")
    u.set_password("editor")
    u.save()
    c = Client(enforce_csrf_checks=True)
    tok = c.get("/api/auth/csrf").json()["csrfToken"]
    r = c.post("/api/auth/login", json.dumps({"username": "editor", "password": "editor"}),
               content_type="application/json", HTTP_X_CSRFTOKEN=tok)
    assert r.status_code == 200, r.content
    c.csrf = c.cookies["csrftoken"].value
    return c


def post(c, url, body, method="post"):
    return getattr(c, method)(url, json.dumps(body), content_type="application/json",
                              HTTP_X_CSRFTOKEN=c.csrf)


# ---- public & auth ---------------------------------------------------------------
def test_public_endpoints_work_logged_out(seeded):
    c = Client()
    series = c.get("/api/series").json()
    assert {s["name"] for s in series} == {"Wet Wednesdays", "Island Series"}
    sid = next(s["id"] for s in series if s["name"] == "Wet Wednesdays")
    st = c.get(f"/api/series/{sid}/standings").json()
    assert [f["fleet_name"] for f in st["fleets"]] == ["PHRF A", "PHRF B"]
    race = Race.objects.filter(series_id=sid, status="sailed").first()
    assert c.get(f"/api/races/{race.id}/results").status_code == 200
    assert c.get(f"/api/races/{race.id}/results.csv").status_code == 200
    assert c.get(f"/api/series/{sid}/standings.csv").status_code == 200
    boat = Boat.objects.get(name="Zephyr")
    assert c.get(f"/api/boats/{boat.id}/history").json()["rows"]


def test_editor_endpoints_require_login(seeded):
    c = Client()
    for url in ("/api/manage/boats", "/api/manage/series", "/api/auth/me"):
        assert c.get(url).status_code == 401


def test_writes_without_csrf_rejected(seeded):
    c = editor_client()
    r = c.post("/api/manage/fleets", json.dumps({"name": "X"}), content_type="application/json")
    assert r.status_code in (401, 403)
    assert not Fleet.objects.filter(name="X").exists()
    assert post(c, "/api/manage/fleets", {"name": "X"}).status_code == 200


def test_public_schema_has_no_contact_info(seeded):
    c = Client()
    sid = Series.objects.get(name="Wet Wednesdays").id
    body = c.get(f"/api/series/{sid}/standings").content.decode()
    assert "@example.org" not in body and "contact" not in body
    rid = Race.objects.filter(series_id=sid, status="sailed").first().id
    assert "@example.org" not in c.get(f"/api/races/{rid}/results").content.decode()
    assert "contact" not in c.get("/api/boats/1/history").content.decode()


def test_draft_series_hidden(seeded):
    s = Series.objects.get(name="Island Series")
    s.status = "draft"
    s.save()
    c = Client()
    assert c.get(f"/api/series/{s.id}").status_code == 404
    assert all(x["id"] != s.id for x in c.get("/api/series").json())


@override_settings(REQUIRE_2FA=True)
def test_login_requires_totp(seeded):
    from django_otp.plugins.otp_totp.models import TOTPDevice
    from django_otp.oath import TOTP
    user = User.objects.get(username="editor")
    dev = TOTPDevice.objects.create(user=user, name="d", confirmed=True)
    c = Client(enforce_csrf_checks=True)
    tok = c.get("/api/auth/csrf").json()["csrfToken"]

    def login(otp):
        return c.post("/api/auth/login", json.dumps(
            {"username": "editor", "password": "editor", "otp": otp}),
            content_type="application/json", HTTP_X_CSRFTOKEN=tok)

    assert login("").status_code == 401
    assert login("000000").status_code == 401
    dev.refresh_from_db()
    dev.throttling_failure_count, dev.throttling_failure_timestamp = 0, None
    dev.save()
    t = TOTP(dev.bin_key, step=dev.step, t0=dev.t0, digits=dev.digits)
    t.time = __import__("time").time()
    assert login(f"{t.token():06d}").status_code == 200
    assert c.get("/api/manage/boats").status_code == 200


def test_lockout_after_failures(seeded):
    c = Client(enforce_csrf_checks=True)
    tok = c.get("/api/auth/csrf").json()["csrfToken"]
    codes = []
    for _ in range(12):
        r = c.post("/api/auth/login", json.dumps({"username": "editor", "password": "bad"}),
                   content_type="application/json", HTTP_X_CSRFTOKEN=tok)
        codes.append(r.status_code)
    assert codes[:9] == [401] * 9 and codes[9:] == [429, 429, 429]     # this address waits; see test_auth_hardening


# ---- rating resolution --------------------------------------------------------------
def test_rating_resolution(seeded):
    wl, rl = RatingType.objects.get(code="WL"), RatingType.objects.get(code="RL")
    halcyon = Boat.objects.get(name="Halcyon")          # no RL rating
    assert resolve_rating(halcyon, rl, date(2026, 7, 1)) == (Decimal("102.0"), "fallback")  # 108-6
    zephyr = Boat.objects.get(name="Zephyr")
    assert resolve_rating(zephyr, rl, date(2026, 7, 1)) == (Decimal("80.0"), "exact")
    assert resolve_rating(zephyr, wl, date(2026, 7, 1)) == (Decimal("84.0"), "exact")
    # mid-season re-rate only applies on/after effective date
    gannet = Boat.objects.get(name="Gannet")
    assert resolve_rating(gannet, wl, date(2026, 6, 10))[0] == 54
    assert resolve_rating(gannet, wl, date(2026, 6, 17))[0] == 48
    # no rating at all before any effective date -> None
    assert resolve_rating(zephyr, wl, date(2025, 1, 1)) is None


def test_old_results_keep_snapshot_after_rerate(seeded):
    f = Finish.objects.filter(boat__name="Gannet", start__race__date=date(2026, 5, 13)).first()
    assert f.rating_value == 54
    BoatRating.objects.filter(boat__name="Gannet").update(value=1)
    f.refresh_from_db()
    assert f.rating_value == 54


def test_change_start_rating_type_reresolves(seeded):
    c = editor_client()
    race = Race.objects.get(series__name="Wet Wednesdays", number=1)
    st = race.starts.get(fleet__name="PHRF A")
    rl = RatingType.objects.get(code="RL")
    before = st.finishes.get(boat__name="Zephyr")
    assert before.rating_value == 84
    r = post(c, f"/api/manage/races/{race.id}/starts",
             {"fleet_id": st.fleet_id, "course_id": st.course_id, "start_time": "2026-05-06T18:00:00",
              "rating_type_id": rl.id}, method="put")
    assert r.status_code == 200 and r.json()["rating_changes"] > 0
    assert st.finishes.get(boat__name="Zephyr").rating_value == 80


def test_two_fleets_different_rating_types_same_race(seeded):
    race = Race.objects.get(series__name="Wet Wednesdays", number=1)
    rl = RatingType.objects.get(code="RL")
    b = race.starts.get(fleet__name="PHRF B")
    b.rating_type = rl
    b.save()
    from racing.services import reresolve_start
    reresolve_start(b)
    a = race.starts.get(fleet__name="PHRF A")
    assert a.finishes.get(boat__name="Zephyr").rating_value == 84      # WL
    assert b.finishes.get(boat__name="Mariner").rating_value == 147    # RL


def test_rating_preview_flags_missing_and_fallback(seeded):
    c = editor_client()
    rl = RatingType.objects.get(code="RL")
    race = Race.objects.get(series__name="Wet Wednesdays", number=1)
    st = race.starts.get(fleet__name="PHRF A")
    st.rating_type = rl
    st.save()
    rows = {r["boat"]: r for r in c.get(f"/api/manage/starts/{st.id}/rating-preview").json()}
    assert rows["Halcyon"]["source"] == "fallback"
    assert rows["Zephyr"]["source"] == "exact"
    rl.fallback_type = None
    rl.save()
    rows = {r["boat"]: r for r in c.get(f"/api/manage/starts/{st.id}/rating-preview").json()}
    assert rows["Halcyon"]["missing"] is True


# ---- finishes & scoring through the API --------------------------------------------------
def make_series():
    wl = RatingType.objects.get(code="WL")
    fleet = Fleet.objects.create(name="F")
    ser = Series.objects.create(name="S", season=2027, status="active", discard_thresholds=[])
    ser.fleets.add(fleet)
    boats = []
    for i, r in enumerate([100, 120, -12]):
        b = Boat.objects.create(name=f"B{i}", sail_number=str(i))
        BoatRating.objects.create(boat=b, rating_type=wl, value=r, effective_from=date(2027, 1, 1))
        SeriesEntry.objects.create(series=ser, boat=b, fleet=fleet)
        boats.append(b)
    race = Race.objects.create(series=ser, number=1, date=date(2027, 6, 2), status="sailed")
    return ser, fleet, boats, race, wl


def test_finish_entry_after_midnight_and_corrected_time():
    ser, fleet, boats, race, wl = make_series()
    c = editor_client()
    r = post(c, f"/api/manage/races/{race.id}/starts", {
        "fleet_id": fleet.id, "start_time": "2027-06-02T23:30:00", "distance_override": 10,
        "rating_type_id": wl.id}, method="put")
    sid = r.json()["id"]
    r = post(c, f"/api/manage/starts/{sid}/finishes", [
        {"boat_id": boats[0].id, "finish_time": "2027-06-03T01:30:00"},
        {"boat_id": boats[2].id, "finish_time": "2027-06-03T01:40:00"}], method="put")
    assert r.status_code == 200, r.content
    rows = {x["boat_id"]: x for x in r.json()}
    assert rows[boats[0].id]["elapsed_seconds"] == 7200
    assert rows[boats[0].id]["corrected_seconds"] == 7200 - 1000
    # negative rating adds time: 7800 + 120
    assert rows[boats[2].id]["corrected_seconds"] == 7800 + 120


def test_finish_before_start_rejected():
    ser, fleet, boats, race, wl = make_series()
    c = editor_client()
    sid = post(c, f"/api/manage/races/{race.id}/starts", {
        "fleet_id": fleet.id, "start_time": "2027-06-02T18:00:00", "distance_override": 4,
        "rating_type_id": wl.id}, method="put").json()["id"]
    r = post(c, f"/api/manage/starts/{sid}/finishes",
             [{"boat_id": boats[0].id, "finish_time": "2027-06-02T17:00:00"}], method="put")
    assert r.status_code == 422


def test_missing_rating_blocks_entry_until_manual():
    ser, fleet, boats, race, wl = make_series()
    rl = RatingType.objects.get(code="RL")
    rl.fallback_type = None
    rl.save()
    c = editor_client()
    sid = post(c, f"/api/manage/races/{race.id}/starts", {
        "fleet_id": fleet.id, "start_time": "2027-06-02T18:00:00", "distance_override": 4,
        "rating_type_id": rl.id}, method="put").json()["id"]
    body = [{"boat_id": boats[0].id, "finish_time": "2027-06-02T19:00:00"}]
    assert post(c, f"/api/manage/starts/{sid}/finishes", body, method="put").status_code == 422
    body[0]["manual_rating"] = 90
    r = post(c, f"/api/manage/starts/{sid}/finishes", body, method="put")
    assert r.status_code == 200 and r.json()[0]["rating_source"] == "manual"


def test_abandoned_race_not_counted_and_discards(seeded):
    sid = Series.objects.get(name="Wet Wednesdays").id
    st = Client().get(f"/api/series/{sid}/standings").json()
    a = st["fleets"][0]
    assert len(a["races"]) == 8                       # 9 scheduled, R4 abandoned
    assert all(r["number"] != 4 for r in a["races"])
    for row in a["standings"]:
        assert sum(c["discarded"] for c in row["scores"]) == 1   # 8 races >= 5 threshold


def test_rcd_credit_in_demo(seeded):
    sid = Series.objects.get(name="Wet Wednesdays").id
    st = Client().get(f"/api/series/{sid}/standings").json()
    zeph = next(r for r in st["fleets"][0]["standings"] if r["boat"]["name"] == "Zephyr")
    credit = [c for c in zeph["scores"] if c["average"]]
    assert len(credit) == 1


def test_combined_overall_only_same_course(seeded):
    sid = Series.objects.get(name="Island Series").id
    st = Client().get(f"/api/series/{sid}/standings").json()
    assert st["combined"] is not None and len(st["combined"]["races"]) == 3
    # make fleet B sail a different course in race 3 -> excluded with warning
    from courses.models import Course
    other = Course.objects.exclude(name="Island Loop").first()
    stt = Start.objects.get(race__series_id=sid, race__number=3, fleet__name="PHRF B")
    stt.course = other
    stt.save()
    st = Client().get(f"/api/series/{sid}/standings").json()
    assert len(st["combined"]["races"]) == 2 and st["warnings"]


def test_clone_series_copies_setup_not_results(seeded):
    c = editor_client()
    src = Series.objects.get(name="Wet Wednesdays")
    r = post(c, f"/api/manage/series/{src.id}/clone", {"season": 2027, "shift_days": 364})
    assert r.status_code == 200
    new = Series.objects.get(pk=r.json()["id"])
    assert new.status == "draft" and new.entries.count() == src.entries.count()
    assert new.races.count() == src.races.count()
    assert not Finish.objects.filter(start__race__series=new).exists()
    assert new.races.get(number=1).date == date(2027, 5, 5)
    assert new.rcd_method == src.rcd_method


def test_series_schedule_creation():
    c = editor_client()
    fl = Fleet.objects.create(name="Z")
    r = post(c, "/api/manage/series", {
        "name": "Wed", "season": 2027, "fleet_ids": [fl.id],
        "schedule": {"first_date": "2027-05-05", "last_date": "2027-08-25", "interval_days": 7}})
    assert r.status_code == 200
    assert Race.objects.filter(series_id=r.json()["id"]).count() == 17


def test_boat_csv_import():
    c = editor_client()
    csv_bytes = b"sail,name,design,WL,RL\n55,Test,J/24,150,147\n56,NoRl,J/22,160,\n,bad,x,1,1\n"
    from django.core.files.uploadedfile import SimpleUploadedFile
    r = c.post("/api/manage/boats/import",
               {"effective_from": "2027-01-01", "file": SimpleUploadedFile("b.csv", csv_bytes)},
               HTTP_X_CSRFTOKEN=c.csrf)
    assert r.status_code == 200, r.content
    out = r.json()
    assert out["boats_created"] == 2 and out["ratings_saved"] == 3 and len(out["errors"]) == 1


def test_csv_export_neutralises_formulas(seeded):
    Boat.objects.filter(name="Zephyr").update(name="=HYPERLINK(1)")
    sid = Series.objects.get(name="Wet Wednesdays").id
    body = Client().get(f"/api/series/{sid}/standings.csv").content.decode()
    assert "'=HYPERLINK(1)" in body


# ---- PDF ----------------------------------------------------------------------
def pdf_text(content):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_podium_pdf(seeded):
    race = Race.objects.get(series__name="Wet Wednesdays", number=2)
    resp = Client().get(f"/api/races/{race.id}/podium.pdf")
    assert resp["Content-Type"] == "application/pdf"
    text = pdf_text(resp.content)
    assert "FINAL" in text and "Wet Wednesdays" in text and "Zephyr" in text
    assert "Series standings after this race" in text and "Total" in text
    last = Race.objects.get(series__name="Wet Wednesdays", number=9)
    assert "PROVISIONAL" in pdf_text(Client().get(f"/api/races/{last.id}/podium.pdf").content)


def test_standings_pdf(seeded):
    sid = Series.objects.get(name="Island Series").id
    text = pdf_text(Client().get(f"/api/series/{sid}/standings.pdf").content)
    assert "Island Series" in text and "Overall" in text
