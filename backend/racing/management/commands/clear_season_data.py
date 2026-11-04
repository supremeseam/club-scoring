"""Remove demo or test race data so a club can start its real season.

Deletes every series (with its races, starts, finishes, entries, payments and protests), their change history,
and everything on the crew board (postings, sign-ups, skipper requests). KEEPS boats, ratings, fleets, rating
types, courses, marks and all login accounts. Shows counts and changes nothing unless --yes is given.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import AccountProfile
from boats.models import Boat, BoatRating
from crew.models import CrewPosting, CrewSignup, PublicAction, SkipperRequest
from racing.models import Finish, Payment, Protest, Race, Series, SeriesEntry, Start


class Command(BaseCommand):
    help = "Delete all series/race/results data and crew board data, keeping boats, ratings, courses and accounts."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="actually delete (otherwise just show what would go)")

    def handle(self, *args, yes=False, **opts):
        gone = [("series", Series), ("races", Race), ("starts", Start), ("finishes", Finish),
                ("series entries", SeriesEntry), ("payments", Payment), ("protests", Protest),
                ("crew postings", CrewPosting), ("crew sign-ups", CrewSignup), ("skipper requests", SkipperRequest)]
        kept = [("boats", Boat), ("boat ratings", BoatRating)]
        self.stdout.write("Would delete:" if not yes else "Deleting:")
        for label, model in gone:
            self.stdout.write(f"  {model.objects.count():>6}  {label}")
        self.stdout.write("Keeping:")
        for label, model in kept:
            self.stdout.write(f"  {model.objects.count():>6}  {label}")
        self.stdout.write(f"  (fleets, rating types, courses, marks and all {AccountProfile.objects.count()} login accounts)")
        if not yes:
            self.stdout.write(self.style.WARNING("Nothing changed. Re-run with --yes after taking a backup."))
            return
        with transaction.atomic():
            CrewSignup.objects.all().delete()
            CrewPosting.objects.all().delete()
            SkipperRequest.objects.all().delete()
            PublicAction.objects.all().delete()
            Series.objects.all().delete()            # cascades to races, starts, finishes, entries, payments, protests
            for model in (Start, Finish, Protest):
                model.history.all().delete()         # the audit trail of deleted rows
        self.stdout.write(self.style.SUCCESS("Done. Boats, ratings, courses and accounts were kept."))
