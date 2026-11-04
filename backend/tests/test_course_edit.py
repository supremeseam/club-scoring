"""Editing a course changes the distance of races already sailed on it, so their results must follow."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from boats.models import Boat, BoatRating, Fleet, RatingType
from courses.models import Course, CourseLeg, Mark
from racing.models import Finish, Race, Series, SeriesEntry, Start

from .test_api import editor_client, post

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    wl = RatingType.objects.get(code="WL")
    a = Mark.objects.create(name="A", lat=34.0, lon=-119.0)
    b = Mark.objects.create(name="B", lat=34.1, lon=-119.0)
    fleet = Fleet.objects.get_or_create(name="F")[0]
    course = Course.objects.create(name="Loop", course_type=wl, description="A to B and back")
    for i, m in enumerate([a, b, a]):
        CourseLeg.objects.create(course=course, mark=m, order=i)
    ser = Series.objects.create(name="S", season=2026)
    ser.fleets.add(fleet)
    race = Race.objects.create(series=ser, number=1, date=date(2026, 6, 1), status="sailed")
    boat = Boat.objects.create(name="Boat", sail_number="1")
    BoatRating.objects.create(boat=boat, rating_type=wl, value=100, effective_from=date(2026, 1, 1))
    SeriesEntry.objects.create(series=ser, boat=boat, fleet=fleet)
    start = Start.objects.create(race=race, fleet=fleet, course=course, start_time=datetime(2026, 6, 1, 12, 0),
                                 rating_type=wl)
    fin = Finish.objects.create(start=start, boat=boat, rating_type=wl, rating_value=100,
                                finish_time=datetime(2026, 6, 1, 14, 0))
    return {"course": course, "start": start, "finish": fin, "a": a, "b": b, "wl": wl, "race": race}


def put(c, course, **over):
    body = {"name": course.name, "course_type_id": course.course_type_id,
            "mark_ids": [l.mark_id for l in course.legs.order_by("order")], "description": course.description, **over}
    return post(c, f"/api/manage/courses/{course.id}", body, "put")


def test_edit_changes_name_marks_and_keeps_the_description(world):
    c = editor_client()
    r = put(c, world["course"], name="Renamed", mark_ids=[world["a"].id, world["b"].id])
    assert r.status_code == 200 and r.json()["name"] == "Renamed"
    assert r.json()["mark_ids"] == [world["a"].id, world["b"].id]
    assert r.json()["description"] == "A to B and back"
    assert put(c, world["course"], name="").status_code == 422


def test_editing_the_distance_rescored_races_already_sailed(world):
    c = editor_client()
    f = world["finish"]
    f.elapsed_seconds = f.corrected_seconds = None
    f.save()
    assert put(c, world["course"], distance_override=10).status_code == 200
    f.refresh_from_db()
    # 2 h elapsed = 7200 s, allowance 100 s/nm x 10 nm = 1000 s
    assert (f.elapsed_seconds, f.corrected_seconds) == (7200, 6200)
    assert put(c, world["course"], distance_override=20).status_code == 200
    f.refresh_from_db()
    assert f.corrected_seconds == 5200


def test_a_start_with_its_own_distance_is_left_alone(world):
    c = editor_client()
    Start.objects.filter(pk=world["start"].pk).update(distance_override=Decimal("3"))
    f = world["finish"]
    f.corrected_seconds = 123
    f.save()
    assert put(c, world["course"], distance_override=10).status_code == 200
    f.refresh_from_db()
    assert f.corrected_seconds == 123


# ---- marks and deleting --------------------------------------------------------------------------------
def test_moving_a_mark_rescored_races_sailed_on_courses_through_it(world):
    c = editor_client()
    f = world["finish"]
    f.corrected_seconds = None
    f.save()
    far = post(c, f"/api/manage/marks/{world['b'].id}", {"name": "B", "lat": 34.2, "lon": -119.0}, "put")
    assert far.status_code == 200
    f.refresh_from_db()
    dist = float(Course.objects.get(pk=world["course"].pk).distance_nm)              # A-B-A, now twice as far
    assert dist > 11
    assert f.corrected_seconds == 7200 - round(100 * dist)


def test_mark_rename_and_duplicate_name(world):
    c = editor_client()
    assert post(c, f"/api/manage/marks/{world['b'].id}", {"name": "B2", "lat": 34.1, "lon": -119.0}, "put").status_code == 200
    assert post(c, f"/api/manage/marks/{world['b'].id}", {"name": "A", "lat": 34.1, "lon": -119.0}, "put").status_code == 409


def test_cannot_delete_a_mark_used_by_a_course_but_can_when_unused(world):
    c = editor_client()
    r = c.delete(f"/api/manage/marks/{world['a'].id}", HTTP_X_CSRFTOKEN=c.csrf)
    assert r.status_code == 409 and "Loop" in r.json()["detail"]
    spare = Mark.objects.create(name="Spare", lat=1, lon=1)
    assert c.delete(f"/api/manage/marks/{spare.id}", HTTP_X_CSRFTOKEN=c.csrf).status_code == 200
    assert not Mark.objects.filter(pk=spare.pk).exists()


def test_cannot_delete_a_course_used_by_a_race_but_can_when_unused(world):
    c = editor_client()
    r = c.delete(f"/api/manage/courses/{world['course'].id}", HTTP_X_CSRFTOKEN=c.csrf)
    assert r.status_code == 409 and "1 race" in r.json()["detail"]
    assert Course.objects.filter(pk=world["course"].pk).exists() and Finish.objects.count() == 1
    spare = Course.objects.create(name="Spare", course_type=world["wl"])
    assert c.delete(f"/api/manage/courses/{spare.id}", HTTP_X_CSRFTOKEN=c.csrf).status_code == 200


def test_delete_endpoints_need_race_committee_login(world):
    from django.test import Client
    anon = Client()
    assert anon.delete(f"/api/manage/marks/{world['a'].id}").status_code == 401
    assert anon.delete(f"/api/manage/courses/{world['course'].id}").status_code == 401


# ---- changing a boat's rating rescores its races -------------------------------------------------------
def test_changing_a_rating_rescored_every_race_the_boat_finished(world):
    c = editor_client()
    Start.objects.filter(pk=world["start"].pk).update(distance_override=Decimal("10"))
    boat = world["finish"].boat
    # race 2 on a later date, same boat
    race2 = Race.objects.create(series=world["race"].series, number=2, date=date(2026, 7, 1), status="sailed")
    st2 = Start.objects.create(race=race2, fleet=world["start"].fleet, start_time=datetime(2026, 7, 1, 12, 0),
                               rating_type=world["wl"], distance_override=Decimal("10"))
    f2 = Finish.objects.create(start=st2, boat=boat, rating_type=world["wl"], rating_value=100,
                               finish_time=datetime(2026, 7, 1, 14, 0))
    # a manual rating on a third race must survive
    race3 = Race.objects.create(series=world["race"].series, number=3, date=date(2026, 8, 1), status="sailed")
    st3 = Start.objects.create(race=race3, fleet=world["start"].fleet, start_time=datetime(2026, 8, 1, 12, 0),
                               rating_type=world["wl"], distance_override=Decimal("10"))
    f3 = Finish.objects.create(start=st3, boat=boat, rating_type=world["wl"], rating_value=77,
                               rating_source=Finish.Source.MANUAL, finish_time=datetime(2026, 8, 1, 14, 0))
    r = post(c, f"/api/manage/boats/{boat.id}/ratings",
             {"rating_type_id": world["wl"].id, "value": 110, "effective_from": "2026-01-01"})
    assert r.status_code == 200
    world["finish"].refresh_from_db(); f2.refresh_from_db(); f3.refresh_from_db()
    # 7200 s elapsed - 110 s/nm x 10 nm = 6100 s
    assert world["finish"].rating_value == 110 and world["finish"].corrected_seconds == 6100
    assert f2.rating_value == 110 and f2.corrected_seconds == 6100
    assert f3.rating_value == 77                      # a hand-entered rating is never overwritten
    # deleting the rating leaves no rating to resolve: the finish loses its value rather than keeping a stale one
    rid = BoatRating.objects.get(boat=boat, rating_type=world["wl"]).id
    assert c.delete(f"/api/manage/ratings/{rid}", HTTP_X_CSRFTOKEN=c.csrf).status_code == 200
    f2.refresh_from_db()
    assert f2.rating_value is None
