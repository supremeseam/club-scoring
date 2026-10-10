"""First-run setup for a new club: first admin account and starter fleets."""
import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from boats.models import Fleet


class Command(BaseCommand):
    help = "Create the first admin account (and optional fleets) for a new club"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="")
        parser.add_argument("--fleets", default="", help='Comma-separated, e.g. "PHRF A,PHRF B,Non-Spinnaker"')

    def handle(self, *args, **o):
        if User.objects.filter(username=o["username"]).exists():
            self.stdout.write(f"User {o['username']!r} already exists; leaving it alone.")
        else:
            pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password for new admin: ")
            try:
                validate_password(pw, User(username=o["username"], email=o["email"]))
            except ValidationError as e:
                raise CommandError(" ".join(e.messages))
            User.objects.create_superuser(o["username"], o["email"], pw)
            self.stdout.write(self.style.SUCCESS(f"Created admin {o['username']!r}."))
        for name in [f.strip() for f in o["fleets"].split(",") if f.strip()]:
            Fleet.objects.get_or_create(name=name)
        self.stdout.write("Next: log in, add boats/ratings, courses and a series under Manage.")
