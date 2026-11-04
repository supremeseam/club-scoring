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
