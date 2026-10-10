"""Per-account brute-force backstop.

Axes locks out an IP address after a few failures. A botnet rotating addresses could still hammer one
account, so we also cap failures per ACCOUNT across all addresses (NIST allows at most 100 consecutive
failures). Failures since the account's last successful login count, inside a rolling window, so an
attacker can't keep a real user locked out for long once the attack stops.
"""
from datetime import timedelta

from axes.models import AccessAttempt, AccessFailureLog
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone


def recent_account_failures(username: str) -> int:
    since = timezone.now() - timedelta(minutes=settings.ACCOUNT_FAILURE_WINDOW_MINUTES)
    user = User.objects.filter(username__iexact=username).first()
    if user and user.last_login and user.last_login > since:
        since = user.last_login                          # a successful login resets the count
    return AccessFailureLog.objects.filter(username__iexact=username, attempt_time__gt=since).count()


def account_locked(username: str) -> bool:
    return bool(username) and recent_account_failures(username) >= settings.ACCOUNT_FAILURE_LIMIT


def clear_failures(username: str) -> int:
    """Forget an account's recorded failures (used by an admin unlocking someone)."""
    n = AccessFailureLog.objects.filter(username__iexact=username).delete()[0]
    n += AccessAttempt.objects.filter(username__iexact=username).delete()[0]
    return n
