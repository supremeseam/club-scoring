from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from boats.models import Boat, BoatRating, Fleet, RatingType
from crew.models import CrewPosting, CrewSignup
from racing.models import Finish, Race, Series, SeriesEntry, Start

pytestmark = pytest.mark.django_db


def build():
    wl = RatingType.objects.get_or_create(code="WL", defaults={"name": "WL", "method": "tod"})[0]
    fleet = Fleet.objects.get_or_create(name="Spin A")[0]
    boat = Boat.objects.create(name="Keeper", sail_number="1")
    BoatRating.objects.create(boat=boat, rating_type=wl, value=100, effective_from=date(2026, 1, 1))
    ser = Series.objects.create(name="Demo", season=2026)
    ser.fleets.add(fleet)
    SeriesEntry.objects.create(series=ser, boat=boat, fleet=fleet)
    race = Race.objects.create(series=ser, number=1, date=date(2026, 6, 1))
    st = Start.objects.create(race=race, fleet=fleet, start_time="2026-06-01T12:00:00", rating_type=wl,
                              distance_override=5)
    Finish.objects.create(start=st, boat=boat, rating_type=wl, rating_value=100)
    CrewPosting.objects.create(boat=boat, role="Bow")
    CrewSignup.objects.create(boat=boat, name="N", email="n@example.org")
    User.objects.create_user("keepme", password="x" * 20)
    return boat


def test_dry_run_changes_nothing():
    build()
    call_command("clear_season_data")
    assert Series.objects.count() == 1 and CrewSignup.objects.count() == 1


def test_yes_removes_race_and_crew_data_but_keeps_boats_ratings_accounts():
    boat = build()
    call_command("clear_season_data", "--yes")
    assert Series.objects.count() == Race.objects.count() == Start.objects.count() == Finish.objects.count() == 0
    assert SeriesEntry.objects.count() == CrewPosting.objects.count() == CrewSignup.objects.count() == 0
    assert Finish.history.count() == 0 and Start.history.count() == 0
    assert Boat.objects.filter(pk=boat.pk).exists() and BoatRating.objects.count() == 1
    assert User.objects.filter(username="keepme").exists()
