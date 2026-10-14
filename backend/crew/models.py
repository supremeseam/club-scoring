"""Crew board: skippers say where they need crew, sailors offer to crew.

Privacy rule: a sailor's contact details (email, phone, message) are only ever shown to the race committee
and to the skipper of the boat they asked about. The public sees counts and the skipper's own posting text.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models


class BoatManager(models.Model):
    """Links a skipper login to a boat. Created by the race committee only."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="managed_boats")
    boat = models.ForeignKey("boats.Boat", on_delete=models.CASCADE, related_name="managers")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "boat"], name="uniq_boat_manager")]


class BoatCrewInfo(models.Model):
    """The skipper-editable, crew-related facts about a boat (everything else about a boat is race-committee data)."""
    boat = models.OneToOneField("boats.Boat", on_delete=models.CASCADE, related_name="crew_info")
    notes = models.CharField(max_length=500, blank=True)
    contact_name = models.CharField(max_length=80, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_preference = models.CharField(max_length=10, default="app", choices=[
        ("app", "Reply through this site"), ("email", "Email"), ("phone", "Phone / text")])
    updated_at = models.DateTimeField(auto_now=True)


class CrewPosting(models.Model):
    """An open position. race=None means "any race this season"."""
    boat = models.ForeignKey("boats.Boat", on_delete=models.CASCADE, related_name="crew_postings")
    race = models.ForeignKey("racing.Race", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="crew_postings")
    role = models.CharField(max_length=60, blank=True, help_text="e.g. Trimmer, Bow, Tactician")
    spots = models.PositiveSmallIntegerField(default=1)
    experience = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["boat__name", "race__date", "id"]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CrewSignup(models.Model):
    """A sailor offering to crew: on one posting, on a boat in general, or on any boat for a race."""

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        DECLINED = "declined"
        WITHDRAWN = "withdrawn"

    posting = models.ForeignKey(CrewPosting, null=True, blank=True, on_delete=models.CASCADE, related_name="signups")
    boat = models.ForeignKey("boats.Boat", null=True, blank=True, on_delete=models.CASCADE, related_name="crew_signups")
    race = models.ForeignKey("racing.Race", null=True, blank=True, on_delete=models.CASCADE, related_name="crew_signups")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="crew_signups")
    name = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    experience = models.CharField(max_length=200, blank=True)
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    seen_by_skipper = models.BooleanField(default=False)
    token_hash = models.CharField(max_length=64, blank=True)        # lets a no-account sailor check/withdraw
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(24)


class SkipperRequest(models.Model):
    """A skipper asking for a login. The race committee approves it (creating the account) or rejects it."""
    name = models.CharField(max_length=80)
    email = models.EmailField()
    boat = models.ForeignKey("boats.Boat", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    boat_text = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, default="pending",
                              choices=[("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PublicAction(models.Model):
    """One row per anonymous write (sign-up, skipper request, registration): the basis for rate limiting.
    Stores a salted hash of the address, never the address itself; old rows are deleted as new ones arrive."""
    kind = models.CharField(max_length=12)
    ip_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "ip_hash", "created_at"])]
