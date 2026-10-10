from datetime import date, datetime
from decimal import Decimal

import pytest

from boats.models import Boat, BoatRating, Fleet, RatingType
from courses.models import Course, Mark
from racing.models import Race, Series, SeriesEntry
from tests.test_move_remove import two_fleets
from tests.test_payments import editor, send

pytestmark = pytest.mark.django_db


def setup_race():
    wl = RatingType.objects.get(code="WL")
    fleet = Fleet.objects.create(name="F")
    ser = Series.objects.create(name="S", season=2027, status="active")
    ser.fleets.add(fleet)
    boat = Boat.objects.create(name="X", sail_number="1")
    SeriesEntry.objects.create(series=ser, boat=boat, fleet=fleet)
    race = Race.objects.create(series=ser, number=1, date=date(2027, 6, 2), status="sailed")
    return wl, fleet, ser, boat, race


def start_body(fleet, wl, **kw):
    return {"fleet_id": fleet.id, "start_time": "2027-06-02T18:00:00", "rating_type_id": wl.id, **kw}


def test_time_on_distance_start_needs_a_distance():
    wl, fleet, ser, boat, race = setup_race()
    c = editor()
    r = send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl))
    assert r.status_code == 422 and "distance is required" in r.json()["detail"].lower()
    assert send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl, distance_override=0)).status_code == 422
    assert send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl, distance_override=4)).status_code == 200


def test_course_without_a_distance_is_not_enough():
    wl, fleet, ser, boat, race = setup_race()
    course = Course.objects.create(name="Empty", course_type=wl)            # no marks, no override
    c = editor()
    r = send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl, course_id=course.id))
    assert r.status_code == 422
    course.distance_override = Decimal("3.5")
    course.save()
    assert send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl, course_id=course.id)).status_code == 200


def test_time_on_time_start_needs_no_distance():
    wl, fleet, ser, boat, race = setup_race()
    orca = RatingType.objects.get(code="ORCA")
    c = editor()
    assert send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, orca)).status_code == 200


def test_a_finish_time_needs_a_rating_even_when_edited_later():
    wl, fleet, ser, boat, race = setup_race()
    c = editor()
    sid = send(c, "put", f"/api/manage/races/{race.id}/starts", start_body(fleet, wl, distance_override=4)).json()["id"]
    # first save: a status only (no rating needed)
    assert send(c, "put", f"/api/manage/starts/{sid}/finishes", [{"boat_id": boat.id, "status": "DNS"}]).status_code == 200
    # later the RC adds a time but the boat still has no rating: blocked, with a clear message
    r = send(c, "put", f"/api/manage/starts/{sid}/finishes",
             [{"boat_id": boat.id, "finish_time": "2027-06-02T19:00:00"}])
    assert r.status_code == 422 and "no WL rating" in r.json()["detail"]
    BoatRating.objects.create(boat=boat, rating_type=wl, value=100, effective_from=date(2027, 1, 1))
    ok = send(c, "put", f"/api/manage/starts/{sid}/finishes",
              [{"boat_id": boat.id, "finish_time": "2027-06-02T19:00:00", "manual_rating": 100}])
    assert ok.status_code == 200 and ok.json()[0]["corrected_seconds"] == 3600 - 400


def test_time_on_time_rating_must_be_positive():
    wl, fleet, ser, boat, race = setup_race()
    orca = RatingType.objects.get(code="ORCA")
    c = editor()
    r = send(c, "post", f"/api/manage/boats/{boat.id}/ratings",
             {"rating_type_id": orca.id, "value": 0, "effective_from": "2027-01-01"})
    assert r.status_code == 422
    r = send(c, "post", f"/api/manage/boats/{boat.id}/ratings",
             {"rating_type_id": orca.id, "value": 0.9467, "effective_from": "2027-01-01"})
    assert r.status_code == 200


def test_course_needs_marks_or_a_distance():
    wl = RatingType.objects.get(code="WL")
    m = Mark.objects.create(name="M", lat=34.1, lon=-119.2)
    c = editor()
    assert send(c, "post", "/api/manage/courses", {"name": "C", "course_type_id": wl.id, "mark_ids": [m.id]}).status_code == 422
    assert send(c, "post", "/api/manage/courses", {"name": "C", "course_type_id": wl.id, "mark_ids": []}).status_code == 422
    assert send(c, "post", "/api/manage/courses", {"name": "C", "course_type_id": wl.id, "mark_ids": [],
                                                   "distance_override": 3}).status_code == 200


def test_series_needs_a_name_a_fleet_and_a_fee_when_payment_is_required():
    f = Fleet.objects.create(name="F")
    c = editor()
    assert send(c, "post", "/api/manage/series", {"name": "S", "season": 2027, "fleet_ids": []}).status_code == 422
    assert send(c, "post", "/api/manage/series", {"name": "  ", "season": 2027, "fleet_ids": [f.id]}).status_code == 422
    r = send(c, "post", "/api/manage/series", {"name": "S", "season": 2027, "fleet_ids": [f.id], "require_payment": True})
    assert r.status_code == 422 and "fee" in r.json()["detail"]
    assert send(c, "post", "/api/manage/series", {"name": "S", "season": 2027, "fleet_ids": [f.id],
                                                  "require_payment": True, "race_fee": 40}).status_code == 200


def test_a_boat_moved_to_another_fleet_can_still_be_saved_there():
    ser, boats, races, g, f_start = two_fleets()
    c = editor()
    send(c, "post", f"/api/manage/starts/{f_start.id}/move-boat",
         {"boat_id": boats["B"].id, "to_fleet_id": g.id, "scope": "race"})
    g_start = races[0].starts.get(fleet=g)
    r = send(c, "put", f"/api/manage/starts/{g_start.id}/finishes", [
        {"boat_id": boats["B"].id, "finish_time": "2027-06-01T19:30:00", "manual_rating": 0}])
    assert r.status_code == 200, r.content
    assert datetime(2027, 6, 1, 19, 30) == races[0].starts.get(fleet=g).finishes.get(boat=boats["B"]).finish_time
