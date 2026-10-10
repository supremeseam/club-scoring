from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from accounts.audit import log_event
from accounts.security import clear_failures


class Command(BaseCommand):
    help = "Clear an account's recorded failed logins (unlock it after a lockout)"

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **o):
        if not User.objects.filter(username__iexact=o["username"]).exists():
            raise CommandError("No such user.")
        n = clear_failures(o["username"])
        log_event("account_unlocked_by_admin", username=o["username"])
        self.stdout.write(self.style.SUCCESS(f"Cleared {n} recorded failures for {o['username']}."))
        self.stdout.write("To unblock an IP address instead, run: manage.py axes_reset_ip <ip>   (or: manage.py axes_reset)")
