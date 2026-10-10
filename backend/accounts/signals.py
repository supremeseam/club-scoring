import logging
import time

from axes.signals import user_locked_out
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from .audit import log_event
from .models import AccountProfile


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        AccountProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session["auth_started_at"] = int(time.time())     # start of the 7-day absolute limit
    log_event("login_success", request, user.get_username())


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    log_event("login_failure", request, (credentials or {}).get("username"), level=logging.WARNING)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        log_event("logout", request, user.get_username())


@receiver(user_locked_out)
def on_locked_out(sender, request=None, username=None, ip_address=None, **kwargs):
    log_event("lockout", request, username, level=logging.WARNING, locked_ip=ip_address)
