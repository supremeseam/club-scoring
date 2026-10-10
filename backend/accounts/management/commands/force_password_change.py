from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts.admin import force_change


class Command(BaseCommand):
    help = "Make a user choose a new password at their next login"

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **o):
        user = User.objects.filter(username__iexact=o["username"]).first()
        if user is None:
            raise CommandError("No such user.")
        force_change(user, "password_change_forced_by_admin")
        self.stdout.write(self.style.SUCCESS(f"{user.username} must choose a new password at next login."))
