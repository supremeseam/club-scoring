import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from boats.models import Boat, Fleet, RatingType
from racing import services
from racing.models import Finish, Payment, Race, Series, SeriesEntry, Start

pytestmark = pytest.mark.django_db


def editor():
    u, _ = User.objects.get_or_create(username="editor")
    u.set_password("editor")
    u.save()
    c = Client(enforce_csrf_checks=True)
    tok = c.get("/api/auth/csrf").json()["csrfToken"]
    assert c.post("/api/auth/login", json.dumps({"username": "editor", "password": "editor"}),
                  content_type="application/json", HTTP_X_CSRFTOKEN=tok).status_code == 200
    c.csrf = c.cookies["csrftoken"].value
    return c


def send(c, method, url, body=None):
    return getattr(c, method)(url, json.dumps(body or {}), content_type="application/json",
                              HTTP_X_CSRFTOKEN=c.csrf)


def build(require_payment=True, members_free_race2=False):
    """4 boats finish 2 races. A paid the series, B paid race 1 only, C never paid, M is a member."""
    wl = RatingType.objects.get(code="WL")
    fleet = Fleet.objects.create(name="F")
    ser = Series.objects.create(name="S", season=2027, status="active", require_payment=require_payment,
                                series_fee=100, race_fee=40, member_race_fee=10)
    ser.fleets.add(fleet)
    boats = {}
    for name, member in (("A", False), ("B", False), ("C", False), ("M", True)):
        boats[name] = Boat.objects.create(name=name, sail_number=name, is_member=member)
        SeriesEntry.objects.create(series=ser, boat=boats[name], fleet=fleet)
    races = []
    for n in (1, 2):
        race = Race.objects.create(series=ser, number=n, date=date(2027, 6, n), status="sailed",
                                   members_free=(n == 2 and members_free_race2))
        st = Start.objects.create(race=race, fleet=fleet, rating_type=wl,
                                  start_time=datetime(2027, 6, n, 18, 0), distance_override=Decimal(4))
        # finishing order A, B, C, M (all rated 0, so elapsed = corrected)
        for i, name in enumerate("ABCM"):
            f = Finish(start=st, boat=boats[name], rating_type=wl,
                       finish_time=st.start_time + timedelta(minutes=60 + i))
            services.save_finish(f, manual_value=Decimal(0))
        races.append(race)
    return ser, boats, races


def standings(ser):
    out = services.series_standings(ser)["fleets"][0]["standings"]
    return {r["boat"]["name"]: r for r in out}


def pay(ser, boat, race=None, amount=40):
    Payment.objects.create(series=ser, boat=boat, race=race, amount=amount, paid_on=date(2027, 5, 1))


def test_without_require_payment_everyone_is_scored():
    ser, boats, races = build(require_payment=False)
    st = standings(ser)
    assert all(not r["guest"] for r in st.values()) and st["A"]["total"] == 2


def test_series_payer_scored_in_every_race_unpaid_boat_is_a_ranked_guest():
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    pay(ser, boats["B"], races[0])
    st = standings(ser)
    assert st["C"]["guest"] and st["M"]["guest"]               # never paid -> guests
    assert not st["A"]["guest"] and not st["B"]["guest"]
    # A is 1st in both races; entrants are A and B only, so DNC = 2 + 1 = 3
    assert [c["points"] for c in st["A"]["scores"]] == [1, 1] and st["A"]["total"] == 2
    # B paid only race 1: places 2nd (after A), then DNC (3) for the race it did not pay for
    assert [c["points"] for c in st["B"]["scores"]] == [2, 3]
    assert st["B"]["scores"][1]["code"] == "DNC"
    assert st["A"]["rank"] == 1 and st["B"]["rank"] == 2
    assert st["C"]["rank"] >= 2 and st["C"]["total"] > 0        # ranked as if entered, never shifts A or B


def test_unpaid_finisher_does_not_change_paid_boats_places():
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    pay(ser, boats["C"], None, 100)               # B and M unpaid; C is 3rd on the water
    st = standings(ser)
    assert [c["points"] for c in st["C"]["scores"]] == [2, 2]   # 2nd among paid boats (A, C)


def test_race_results_flag_unpaid_boats():
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    rows = {r["boat"]["name"]: r for r in services.race_results(races[0])["fleets"][0]["rows"]}
    assert rows["A"]["points"] == 1
    assert rows["B"]["code"] == "unpaid" and rows["B"]["points"] is None and rows["B"]["place"] == 2  # editors still see it


def test_members_race_free_in_members_free_races():
    ser, boats, races = build(members_free_race2=True)
    pay(ser, boats["A"], None, 100)
    st = standings(ser)
    assert not st["M"]["guest"]                                  # member, with a free race, is an entrant
    assert st["M"]["scores"][1]["points"] == 2                   # race 2 (members free): 2nd of A and M
    assert st["M"]["scores"][0]["code"] == "DNC"                 # race 1 not paid, not free
    assert st["B"]["guest"]                                      # a non-member who never paid is still a guest


def test_default_amounts_and_member_price_and_dates():
    ser, boats, races = build()
    c = editor()
    r = send(c, "post", f"/api/manage/series/{ser.id}/payments", {"boat_id": boats["A"].id}).json()
    assert r["amount"] == 100 and r["race_id"] is None and r["paid_on"] == date.today().isoformat()
    r = send(c, "post", f"/api/manage/series/{ser.id}/payments", {"boat_id": boats["A"].id, "race_id": races[0].id}).json()
    assert r["amount"] == 40                                     # race fee
    r = send(c, "post", f"/api/manage/series/{ser.id}/payments", {"boat_id": boats["M"].id, "race_id": races[0].id}).json()
    assert r["amount"] == 10                                     # member race fee
    r = send(c, "post", f"/api/manage/series/{ser.id}/payments", {
        "boat_id": boats["B"].id, "amount": 95, "paid_on": "2027-04-02", "method": "check"}).json()
    assert r["amount"] == 95 and r["paid_on"] == "2027-04-02" and r["method"] == "check"
    # recording the same payment again corrects it instead of duplicating
    send(c, "post", f"/api/manage/series/{ser.id}/payments", {"boat_id": boats["B"].id, "amount": 100})
    assert Payment.objects.filter(series=ser, boat=boats["B"], race=None).count() == 1
    assert Payment.objects.get(series=ser, boat=boats["B"], race=None).amount == 100
    assert len(c.get(f"/api/manage/series/{ser.id}/payments").json()) == 4


def test_payments_require_editor_and_never_public():
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    assert Client().get(f"/api/manage/series/{ser.id}/payments").status_code == 401
    pub = Client()
    body = (pub.get(f"/api/series/{ser.id}/standings").content.decode()
            + pub.get(f"/api/races/{races[0].id}/results").content.decode()
            + pub.get(f"/api/boats/{boats['A'].id}/history").content.decode())
    for word in ("amount", "paid_on", "is_member", "series_fee", "race_fee", "method"):
        assert word not in body


def test_single_race_fee_applies_to_that_race():
    wl = RatingType.objects.get(code="WL")
    fleet = Fleet.objects.create(name="F")
    boat = Boat.objects.create(name="X", sail_number="1")
    c = editor()
    race = send(c, "post", "/api/manage/single-races", {
        "name": "One-off", "date": "2027-07-04", "fleet_ids": [fleet.id], "require_payment": True, "race_fee": 40}).json()
    send(c, "post", f"/api/manage/series/{race['series_id']}/entries/add", {"boat_id": boat.id, "fleet_id": fleet.id})
    p = send(c, "post", f"/api/manage/series/{race['series_id']}/payments", {"boat_id": boat.id}).json()
    assert p["amount"] == 40 and p["race_id"] == race["id"]
    assert wl  # rating type exists for the race flow


def test_public_pages_hide_boats_that_have_not_paid():
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    pay(ser, boats["C"], races[0])               # C paid race 1 only; B and M never paid
    pub = Client()
    race1 = pub.get(f"/api/races/{races[0].id}/results").json()["fleets"][0]["rows"]
    assert [r["boat"]["name"] for r in race1] == ["A", "C"]            # B and M are not listed
    assert [r["place"] for r in race1] == [1, 2]                       # places recomputed without them
    race2 = pub.get(f"/api/races/{races[1].id}/results").json()["fleets"][0]["rows"]
    assert [r["boat"]["name"] for r in race2] == ["A"]                 # C did not pay for race 2
    st = pub.get(f"/api/series/{ser.id}/standings").json()["fleets"][0]["standings"]
    assert {r["boat"]["name"] for r in st} == {"A", "C"} and not any(r["guest"] for r in st)
    standings_csv = pub.get(f"/api/series/{ser.id}/standings.csv").content.decode()
    assert "A" in standings_csv and ",B," not in standings_csv and ",M," not in standings_csv
    history = pub.get(f"/api/boats/{boats['B'].id}/history").json()["rows"]
    assert history == []                                               # nothing public for a boat that never paid
    # editors still see everyone, flagged
    c = editor()
    rows = c.get(f"/api/manage/races/{races[0].id}/results").json()["fleets"][0]["rows"]
    assert {r["boat"]["name"] for r in rows} == {"A", "B", "C", "M"}
    assert {r["boat"]["name"]: r["code"] for r in rows}["B"] == "unpaid"


def test_public_pdf_and_csv_omit_unpaid_boats():
    from io import BytesIO
    from pypdf import PdfReader
    ser, boats, races = build()
    pay(ser, boats["A"], None, 100)
    pub = Client()
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pub.get(f"/api/races/{races[0].id}/podium.pdf").content)).pages)
    assert "A" in text and "Boat" in text
    body = pub.get(f"/api/races/{races[0].id}/results.csv").content.decode().splitlines()
    names = [line.split(",")[2] for line in body[1:]]
    assert names == ["A"]
