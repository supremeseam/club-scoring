"""Load realistic demo data: boats, fleets, courses and two complete series."""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from boats.models import Boat, BoatRating, Fleet, RatingType
from courses.models import Course, CourseLeg, Mark
from racing import services
from racing.models import Finish, Race, Series, SeriesEntry, Start
from racing.ratings import resolve_rating

# name, sail, design, skipper, WL, RL (None = no RL rating), fleet
BOATS = [
    ("Zephyr", "101", "J/105", "A. Morgan", 84, 80, "PHRF A"),
    ("Blue Heron", "112", "Farr 40", "B. Castillo", 30, 27, "PHRF A"),
    ("Tempest", "118", "J/109", "C. Dunn", 72, 69, "PHRF A"),
    ("Windchaser", "127", "Beneteau 36.7", "D. Evans", 96, 93, "PHRF A"),
    ("Gannet", "133", "Sydney 38", "E. Frost", 54, 51, "PHRF A"),
    ("Halcyon", "140", "J/92", "F. Garza", 108, None, "PHRF A"),
    ("Starling", "152", "Tartan 10", "G. Hill", 117, 114, "PHRF A"),
    ("Kestrel", "161", "Melges 24", "H. Ito", -12, -15, "PHRF A"),
    ("Mariner", "204", "Catalina 34", "I. Jones", 150, 147, "PHRF B"),
    ("Sea Biscuit", "211", "Pearson 35", "J. Kim", 162, 159, "PHRF B"),
    ("Odyssey", "219", "C&C 33", "K. Lopez", 138, 135, "PHRF B"),
    ("Pelican", "226", "Hunter 356", "L. Moore", 171, None, "PHRF B"),
    ("Driftwood", "233", "Catalina 30", "M. Nash", 186, 183, "PHRF B"),
    ("Albatross", "245", "Ericson 35", "N. Ortiz", 144, 141, "PHRF B"),
    ("Sandpiper", "252", "S2 9.1", "O. Park", 156, 153, "PHRF B"),
    ("Wanderer", "260", "Islander 36", "P. Quinn", 168, 165, "PHRF B"),
    ("Cormorant", "301", "Catalina 320", "Q. Reyes", 192, 189, "Non-Spinnaker"),
    ("Dolphin", "308", "Hunter 31", "R. Singh", 201, 198, "Non-Spinnaker"),
    ("Nautilus", "315", "Pearson 30", "S. Tran", 210, None, "Non-Spinnaker"),
    ("Merlin", "322", "Beneteau 321", "T. Usher", 183, 180, "Non-Spinnaker"),
]

MARKS = {"Start (A)": (41.4800, -71.3200), "Windward (W)": (41.5133, -71.3200),
         "Leeward (L)": (41.4850, -71.3200), "Gong 7": (41.5400, -71.2500),
         "Hog Island": (41.5800, -71.2900), "Can 3": (41.5300, -71.3600),
         "Fort Pt": (41.4600, -71.3600)}


class Command(BaseCommand):
    help = "Load demo data (use --reset to wipe and reseed)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        if settings.PRODUCTION:
            raise CommandError("seed_demo creates accounts with well-known passwords; it is for development only (DEBUG=1). "
                               "Use `manage.py setup_club` to create a real admin.")
        if opts["reset"]:
            call_command("flush", interactive=False, verbosity=0)
        if Series.objects.exists():
            self.stdout.write("Demo data already present (use --reset to reload).")
            return
        rnd = random.Random(2026)

        wl, _ = RatingType.objects.get_or_create(
            code="WL", defaults={"name": "Windward/Leeward", "display_order": 1})
        rl, _ = RatingType.objects.get_or_create(
            code="RL", defaults={"name": "Random Leg", "display_order": 2,
                                 "fallback_type": wl, "fallback_offset": -6})
        RatingType.objects.get_or_create(code="ORCA", defaults={"name": "ORCA (time-on-time)", "display_order": 3, "method": "tot"})
        fleets = {n: Fleet.objects.create(name=n) for n in ("PHRF A", "PHRF B", "Non-Spinnaker")}

        boats = {}
        for name, sail, design, skipper, w, r, fl in BOATS:
            b = Boat.objects.create(name=name, sail_number=sail, design=design, skipper=skipper,
                                    default_fleet=fleets[fl], contact_email=f"{sail}@example.org")
            BoatRating.objects.create(boat=b, rating_type=wl, value=w, effective_from=date(2026, 1, 1),
                                      certificate=f"WL-{sail}", expires=date(2026, 12, 31))
            if r is not None:
                BoatRating.objects.create(boat=b, rating_type=rl, value=r,
                                          effective_from=date(2026, 1, 1), certificate=f"RL-{sail}")
            boats[name] = b
        # Mid-season re-rate: Gannet gets faster from 17 June 2026.
        BoatRating.objects.create(boat=boats["Gannet"], rating_type=wl, value=48,
                                  effective_from=date(2026, 6, 17), notes="re-rated after survey")

        marks = {n: Mark.objects.create(name=n, lat=lat, lon=lon) for n, (lat, lon) in MARKS.items()}
        wl2 = Course.objects.create(name="W/L 2 laps", course_type=wl, distance_override=Decimal("4.0"))
        wl3 = Course.objects.create(name="W/L 3 laps", course_type=wl, distance_override=Decimal("6.0"))
        for c, names in ((wl2, ["Start (A)", "Windward (W)", "Leeward (L)"]),
                         (wl3, ["Start (A)", "Windward (W)", "Leeward (L)"]),
                         (Course.objects.create(name="Island Loop", course_type=rl),
                          ["Start (A)", "Gong 7", "Hog Island", "Can 3", "Start (A)"])):
            CourseLeg.objects.bulk_create(
                [CourseLeg(course=c, mark=marks[n], order=i) for i, n in enumerate(names)])
        island = Course.objects.get(name="Island Loop")

        User.objects.create_superuser("admin", "admin@example.org", "admin")
        User.objects.create_user("editor", "editor@example.org", "editor")

        self._wet_wednesdays(rnd, fleets, boats, wl, wl2, wl3)
        self._island(rnd, fleets, boats, rl, island)
        self.stdout.write(self.style.SUCCESS(
            "Demo data loaded. Logins: editor / editor, admin / admin"))

    # ------------------------------------------------------------------
    def _sail(self, rnd, start, entries, plan, dist_override=None):
        """Create finishes. plan[boat_name] = status code | ('tie_with', name) | None."""
        dist = start.distance_nm
        done = {}
        for e in entries:
            spec = plan.get(e.boat.name, "")
            if spec == "DNC_ROW":          # no finish row at all
                continue
            f = Finish(start=start, boat=e.boat, rating_type=start.rating_type)
            if isinstance(spec, str) and spec:
                f.status = spec
                if spec == "RDG":
                    f.redress_points = Decimal("2.0")
                if spec in ("DNF", "DSQ", "OCS", "RET", "DNS", "RCD"):
                    pass
            else:
                hit = resolve_rating(e.boat, start.rating_type, start.race.date)
                rating = hit[0] if hit else Decimal(150)
                elapsed = int(Decimal(str(dist)) * (Decimal(540) + rating)
                              * Decimal(str(round(rnd.uniform(0.97, 1.03), 4))))
                if isinstance(spec, tuple):        # force a tie with another boat
                    other = done[spec[1]]
                    elapsed = int(other.corrected_seconds + rating * Decimal(str(dist)))
                f.finish_time = start.start_time + timedelta(seconds=elapsed)
            services.save_finish(f)
            done[e.boat.name] = f

    def _wet_wednesdays(self, rnd, fleets, boats, wl, wl2, wl3):
        ser = Series.objects.create(
            name="Wet Wednesdays", season=2026, status="complete",
            description="Wednesday-night windward/leeward racing.",
            discard_thresholds=[5], rcd_method="all_other", rcd_max_credits=2)
        use = [fleets["PHRF A"], fleets["PHRF B"]]
        ser.fleets.set(use)
        for b in BOATS:
            if b[6] in ("PHRF A", "PHRF B"):
                SeriesEntry.objects.create(series=ser, boat=boats[b[0]], fleet=fleets[b[6]])
        entries = list(ser.entries.select_related("boat", "fleet"))
        d0 = date(2026, 5, 6)
        plans = {
            2: {"Windchaser": "DNC_ROW", "Mariner": "DNC_ROW", "Tempest": ("tie", "Zephyr")},
            3: {"Halcyon": "DNF", "Starling": "OCS", "Pelican": "DNF"},
            5: {"Zephyr": "RCD", "Odyssey": "RCD", "Kestrel": "DNS"},
            7: {"Gannet": "RDG", "Driftwood": "DSQ"},
            8: {"Sea Biscuit": "DNC_ROW"},
        }
        for n in range(1, 10):
            race = Race.objects.create(series=ser, number=n, date=d0 + timedelta(days=7 * (n - 1)),
                                       status="abandoned" if n == 4 else "sailed",
                                       results_final=n < 9)
            if n == 4:
                continue
            course = wl3 if n % 3 == 0 else wl2
            for fl in use:
                st = Start.objects.create(race=race, fleet=fl, course=course, rating_type=wl,
                                          start_time=datetime.combine(race.date, time(18, 0)) +
                                          timedelta(minutes=5 * (fl.name == "PHRF B")))
                self._sail(rnd, st, [e for e in entries if e.fleet_id == fl.id],
                           plans.get(n, {}))

    def _island(self, rnd, fleets, boats, rl, island):
        ser = Series.objects.create(
            name="Island Series", season=2026, status="active", combined_overall=True,
            description="Distance races around the island.", discard_thresholds=[])
        use = list(fleets.values())
        ser.fleets.set(use)
        for b in BOATS:
            SeriesEntry.objects.create(series=ser, boat=boats[b[0]], fleet=fleets[b[6]])
        entries = list(ser.entries.select_related("boat", "fleet"))
        for n, (d, hour, status) in enumerate([(date(2026, 7, 11), 10, "sailed"),
                                               (date(2026, 8, 8), 21, "sailed"),
                                               (date(2026, 9, 5), 10, "sailed")], 1):
            race = Race.objects.create(series=ser, number=n, date=d, status=status,
                                       results_final=n < 3)
            for fl in use:
                st = Start.objects.create(race=race, fleet=fl, course=island, rating_type=rl,
                                          start_time=datetime.combine(d, time(hour, 30)))
                plan = {"Nautilus": "DNF"} if n == 3 else {}
                self._sail(rnd, st, [e for e in entries if e.fleet_id == fl.id], plan)
