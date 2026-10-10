from datetime import datetime
from decimal import Decimal

import pytest
from django.test import Client

from boats.models import Fleet, RatingType
from racing import services
from racing.models import Finish, SeriesEntry, Start
from tests.test_payments import build, editor, send

pytestmark = pytest.mark.django_db


def two_fleets():
    """Series from build(): fleet F with boats A,B,C,M racing 2 races. Add fleet G with its own starts."""
    ser, boats, races = build(require_payment=False)
    wl = RatingType.objects.get(code="WL")
    g = Fleet.objects.create(name="G", display_order=2)
    ser.fleets.add(g)
    for r in races:
        Start.objects.create(race=r, fleet=g, rating_type=wl, start_time=datetime(2027, 6, r.number, 18, 5),
                             distance_override=Decimal(4))
    f_start = races[0].starts.get(fleet__name="F")
    return ser, boats, races, g, f_start


def rows(race_id, public=True):
    url = f"/api/races/{race_id}/results" if public else f"/api/manage/races/{race_id}/results"
    return {b["fleet_name"]: [r["boat"]["name"] for r in b["rows"]]
            for b in (Client() if public else editor()).get(url).json()["fleets"]}


def test_move_boat_for_this_race_only():
    ser, boats, races, g, f_start = two_fleets()
    c = editor()
    r = send(c, "post", f"/api/manage/starts/{f_start.id}/move-boat",
             {"boat_id": boats["B"].id, "to_fleet_id": g.id, "scope": "race"})
    assert r.status_code == 200 and r.json()["moved_result"] is True, r.content
    # race 1: B is listed in G's start; race 2 is untouched
    assert "B" in rows(races[0].id)["G"] and "B" not in rows(races[0].id)["F"]
    assert "B" in rows(races[1].id)["F"]
    # the entry stays in F, so the series standings still list B under F with a score for race 1
    st = {b["fleet_name"]: b for b in Client().get(f"/api/series/{ser.id}/standings").json()["fleets"]}
    b_row = next(x for x in st["F"]["standings"] if x["boat"]["name"] == "B")
    assert len(b_row["scores"]) == 2 and b_row["scores"][0]["code"] is None
    # the RC screen puts B on G's panel for race 1 and on F's panel for race 2
    lineup1 = {x["fleet_id"]: x["boat_ids"] for x in c.get(f"/api/manage/races/{races[0].id}/lineup").json()}
    assert boats["B"].id in lineup1[g.id] and boats["B"].id not in lineup1[f_start.fleet_id]
    lineup2 = {x["fleet_id"]: x["boat_ids"] for x in c.get(f"/api/manage/races/{races[1].id}/lineup").json()}
    assert boats["B"].id in lineup2[f_start.fleet_id]


def test_move_needs_a_target_start_and_a_result():
    ser, boats, races, g, f_start = two_fleets()
    Start.objects.filter(race=races[0], fleet=g).delete()
    c = editor()
    r = send(c, "post", f"/api/manage/starts/{f_start.id}/move-boat",
             {"boat_id": boats["B"].id, "to_fleet_id": g.id, "scope": "race"})
    assert r.status_code == 422 and "Set the start for G" in r.json()["detail"]
    Finish.objects.filter(start=f_start, boat=boats["B"]).delete()
    Start.objects.create(race=races[0], fleet=g, rating_type=RatingType.objects.get(code="WL"),
                         start_time=datetime(2027, 6, 1, 18, 5), distance_override=Decimal(4))
    r = send(c, "post", f"/api/manage/starts/{f_start.id}/move-boat",
             {"boat_id": boats["B"].id, "to_fleet_id": g.id, "scope": "race"})
    assert r.status_code == 422 and "finish time or status first" in r.json()["detail"]


def test_moved_result_is_rescored_for_the_new_start():
    ser, boats, races, g, f_start = two_fleets()
    rl = RatingType.objects.get(code="RL")
    g_start = races[0].starts.get(fleet=g)
    g_start.rating_type = rl
    g_start.start_time = datetime(2027, 6, 1, 17, 0)           # started an hour earlier
    g_start.save()
    c = editor()
    fin = Finish.objects.get(start=f_start, boat=boats["A"])
    before = fin.elapsed_seconds
    send(c, "post", f"/api/manage/starts/{f_start.id}/move-boat",
         {"boat_id": boats["A"].id, "to_fleet_id": g.id, "scope": "race"})
    fin.refresh_from_db()
    assert fin.start_id == g_start.id and fin.elapsed_seconds == before + 3600
    assert fin.rating_type.code == "RL"


def test_change_fleet_for_the_series_keeps_earlier_results_where_they_raced():
    ser, boats, races, g, f_start = two_fleets()
    c = editor()
    r = send(c, "post", f"/api/manage/starts/{races[1].starts.get(fleet__name='F').id}/move-boat",
             {"boat_id": boats["C"].id, "to_fleet_id": g.id, "scope": "series", "move_this_race": True})
    assert r.status_code == 200 and r.json()["moved_result"] is True
    assert SeriesEntry.objects.get(series=ser, boat=boats["C"]).fleet_id == g.id
    assert "C" in rows(races[0].id)["F"]                    # race 1 result stays where C raced
    assert "C" in rows(races[1].id)["G"]                    # race 2 result moved with it
    st = {b["fleet_name"]: b for b in Client().get(f"/api/series/{ser.id}/standings").json()["fleets"]}
    assert "C" in [x["boat"]["name"] for x in st["G"]["standings"]]
    assert "C" not in [x["boat"]["name"] for x in st["F"]["standings"]]


def test_remove_boat_from_race_and_from_series():
    ser, boats, races, g, f_start = two_fleets()
    c = editor()
    r = c.delete(f"/api/manage/starts/{f_start.id}/boats/{boats['B'].id}", HTTP_X_CSRFTOKEN=c.csrf)
    assert r.json() == {"cleared_result": True, "removed_entry": False}
    assert not Finish.objects.filter(start=f_start, boat=boats["B"]).exists()
    assert SeriesEntry.objects.filter(series=ser, boat=boats["B"]).exists()
    # removing the entry is refused while the boat has results in another race
    r = c.delete(f"/api/manage/starts/{f_start.id}/boats/{boats['B'].id}?remove_entry=true", HTTP_X_CSRFTOKEN=c.csrf)
    assert r.status_code == 409
    Finish.objects.filter(boat=boats["B"]).delete()
    r = c.delete(f"/api/manage/starts/{f_start.id}/boats/{boats['B'].id}?remove_entry=true", HTTP_X_CSRFTOKEN=c.csrf)
    assert r.json()["removed_entry"] is True
    assert not SeriesEntry.objects.filter(series=ser, boat=boats["B"]).exists()
    assert "B" not in [x["boat"]["name"] for b in services.series_standings(ser)["fleets"] for x in b["standings"]]


def test_move_and_remove_require_an_editor():
    ser, boats, races, g, f_start = two_fleets()
    anon = Client()
    assert anon.post(f"/api/manage/starts/{f_start.id}/move-boat", "{}", content_type="application/json").status_code == 401
    assert anon.delete(f"/api/manage/starts/{f_start.id}/boats/{boats['B'].id}").status_code == 401
