"""Pursuit starts: schedule, scoring by finishing order, and the format setting (series default, race override)."""
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from boats.models import Boat, BoatRating, Fleet, RatingType
from racing.models import Finish, Race, Series, SeriesEntry, Start

from .test_api import editor_client, post

pytestmark = pytest.mark.django_db
DAY = date(2026, 6, 10)


def at(h, m, s=0):
    return datetime(2026, 6, 10, h, m, s)


@pytest.fixture
def pursuit():
    wl = RatingType.objects.get_or_create(code="WL", defaults={"name": "Windward-Leeward", "method": "tod"})[0]
    fleet = Fleet.objects.get_or_create(name="Spin A")[0]
    ser = Series.objects.create(name="Pursuit Cup", season=2026, status="active", race_format="pursuit")
    ser.fleets.add(fleet)
    race = Race.objects.create(series=ser, number=1, date=DAY, status="sailed")
    start = Start.objects.create(race=race, fleet=fleet, start_time=at(12, 0), rating_type=wl,
                                 distance_override=Decimal("10"))
    boats = {}
    for name, rating in (("Slow", 180), ("Mid", 150), ("Fast", 96)):
        b = Boat.objects.create(name=name, sail_number=name[0])
        BoatRating.objects.create(boat=b, rating_type=wl, value=rating, effective_from=date(2026, 1, 1))
        SeriesEntry.objects.create(series=ser, boat=b, fleet=fleet)
        boats[name] = b
    return {"ser": ser, "race": race, "start": start, "boats": boats, "wl": wl, "fleet": fleet}


def schedule(c, start):
    r = c.get(f"/api/manage/starts/{start.id}/pursuit-schedule")
    assert r.status_code == 200, r.content
    return r.json()


def test_schedule_starts_slowest_first_and_spaces_the_rest_by_rating_gap(pursuit):
    sched = schedule(editor_client(), pursuit["start"])
    assert [r["boat"] for r in sched["rows"]] == ["Slow", "Mid", "Fast"]
    assert [r["offset_seconds"] for r in sched["rows"]] == [0, 300, 840]            # 30 x 10, 84 x 10
    assert sched["rows"][2]["offset"] == "0:14:00"
    assert sched["rows"][2]["start_time"].startswith("2026-06-10T12:14:00")
    assert sched["skipped"] == [] and sched["error"] is None


def test_fleet_format_race_has_no_schedule(pursuit):
    Race.objects.filter(pk=pursuit["race"].pk).update(race_format="fleet")        # race overrides the series
    sched = schedule(editor_client(), pursuit["start"])
    assert sched["is_pursuit"] is False and sched["rows"] == []


def test_race_can_be_pursuit_inside_a_fleet_series(pursuit):
    Series.objects.update(race_format="fleet")
    assert schedule(editor_client(), pursuit["start"])["is_pursuit"] is False
    Race.objects.update(race_format="pursuit")
    assert schedule(editor_client(), pursuit["start"])["is_pursuit"] is True


def test_results_are_placed_by_who_crosses_the_line_first(pursuit):
    c = editor_client()
    b = pursuit["boats"]
    # Fast starts 14 min after Slow and catches up: Fast then Mid then Slow cross the line
    items = [{"boat_id": b["Fast"].id, "finish_time": "2026-06-10T13:00:00"},
             {"boat_id": b["Mid"].id, "finish_time": "2026-06-10T13:00:30"},
             {"boat_id": b["Slow"].id, "finish_time": "2026-06-10T13:02:00"}]
    r = post(c, f"/api/manage/starts/{pursuit['start'].id}/finishes", items, "put")
    assert r.status_code == 200, r.content
    rows = {f["boat_id"]: f for f in r.json()}
    assert rows[b["Fast"].id]["corrected_seconds"] == 3600                        # time since the first gun
    assert rows[b["Fast"].id]["elapsed_seconds"] == 3600 - 840                    # time since its OWN start
    assert rows[b["Slow"].id]["elapsed_seconds"] == 3720
    res = c.get(f"/api/manage/races/{pursuit['race'].id}/results").json()
    order = [row["boat"]["name"] for row in res["fleets"][0]["rows"]]
    assert order == ["Fast", "Mid", "Slow"]
    assert [row["place"] for row in res["fleets"][0]["rows"]] == [1, 2, 3]


def test_simultaneous_finish_is_a_tie(pursuit):
    c = editor_client()
    b = pursuit["boats"]
    items = [{"boat_id": b["Fast"].id, "finish_time": "2026-06-10T13:00:00"},
             {"boat_id": b["Mid"].id, "finish_time": "2026-06-10T13:00:00"}]
    assert post(c, f"/api/manage/starts/{pursuit['start'].id}/finishes", items, "put").status_code == 200
    rows = c.get(f"/api/manage/races/{pursuit['race'].id}/results").json()["fleets"][0]["rows"]
    assert [r["place"] for r in rows if r["boat"]["name"] in ("Fast", "Mid")] == [1, 1]


def test_adding_a_slower_boat_moves_everyones_start_but_not_the_order(pursuit):
    c = editor_client()
    b = pursuit["boats"]
    items = [{"boat_id": b["Fast"].id, "finish_time": "2026-06-10T13:00:00"}]
    post(c, f"/api/manage/starts/{pursuit['start'].id}/finishes", items, "put")
    slower = Boat.objects.create(name="Slowest", sail_number="X")
    BoatRating.objects.create(boat=slower, rating_type=pursuit["wl"], value=200, effective_from=date(2026, 1, 1))
    post(c, f"/api/manage/series/{pursuit['ser'].id}/entries/add", {"boat_id": slower.id, "fleet_id": pursuit["fleet"].id}, "post")
    sched = schedule(c, pursuit["start"])
    assert sched["rows"][0]["boat"] == "Slowest" and sched["rows"][-1]["offset_seconds"] == 1040
    f = Finish.objects.get(boat=b["Fast"])
    assert f.corrected_seconds == 3600 and f.elapsed_seconds == 3600 - 1040       # elapsed refreshed, order unchanged


def test_boat_without_a_rating_is_listed_not_scheduled(pursuit):
    Boat.objects.create(name="NoRating", sail_number="N")
    SeriesEntry.objects.create(series=pursuit["ser"], boat=Boat.objects.get(name="NoRating"), fleet=pursuit["fleet"])
    sched = schedule(editor_client(), pursuit["start"])
    assert [s["boat"] for s in sched["skipped"]] == ["NoRating"] and len(sched["rows"]) == 3


def test_time_on_time_pursuit_needs_a_target_length(pursuit):
    tot = RatingType.objects.get_or_create(code="ORCA", defaults={"name": "ORCA", "method": "tot"})[0]
    Start.objects.filter(pk=pursuit["start"].pk).update(rating_type=tot)
    for b, v in zip(pursuit["boats"].values(), ("0.8", "0.9", "1.2")):
        BoatRating.objects.create(boat=b, rating_type=tot, value=v, effective_from=date(2026, 1, 1))
    c = editor_client()
    assert "target" in schedule(c, pursuit["start"])["error"]
    r = post(c, f"/api/manage/races/{pursuit['race'].id}", {"date": "2026-06-10", "status": "sailed", "race_format": "",
                                                              "pursuit_target_minutes": 60}, "put")
    assert r.status_code == 200 and r.json()["is_pursuit"] is True
    rows = schedule(c, pursuit["start"])["rows"]
    assert [x["offset_seconds"] for x in rows] == [0, 400, 1200]                  # 3600 x (1 - 0.8/TCF)


def test_format_is_validated_and_clone_keeps_it(pursuit):
    c = editor_client()
    base = {"name": "X", "season": 2030, "fleet_ids": [pursuit["fleet"].id]}
    assert post(c, "/api/manage/series", {**base, "race_format": "regatta"}).status_code == 422
    ok = post(c, "/api/manage/series", {**base, "race_format": "pursuit"})
    assert ok.status_code == 200 and ok.json()["race_format"] == "pursuit"
    cl = post(c, f"/api/manage/series/{pursuit['ser'].id}/clone", {"season": 2027})
    assert cl.status_code == 200 and cl.json()["race_format"] == "pursuit"
