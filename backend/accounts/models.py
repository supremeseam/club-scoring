from django.conf import settings
from django.db import models


class AccountProfile(models.Model):
    """Security state for a login account (kept separate so the stock User model is untouched)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_profile")
    # True after an administrator creates the account or sets a temporary password: the person must
    # choose their own password before they can do anything else.
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    # What this login may do. Everyone created in the Django admin is race committee (the default). Skipper and
    # crew accounts can NEVER reach /api/manage/*: RoleAuth refuses anyone whose role is not "rc".
    role = models.CharField(max_length=8, default="rc", choices=[
        ("rc", "Race committee"), ("skipper", "Skipper (own boat's crew info only)"),
        ("crew", "Crew (own sign-ups only)")])

    def __str__(self):
        return f"{self.user} (must change: {self.must_change_password})"


class ExternalIdentity(models.Model):
    """A person who signs in through an external identity provider (Amazon Cognito) rather than a local password."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identity")
    issuer = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)        # the provider's permanent id for the person (Cognito "sub")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issuer", "subject"], name="uniq_external_identity")]

    def __str__(self):
        return f"{self.user} ({self.issuer.rsplit('/', 1)[-1]})"


def must_change_password(user) -> bool:
    profile = getattr(user, "auth_profile", None)      # a missing profile just means "no"
    return bool(profile and profile.must_change_password)


def account_role(user) -> str:
    profile = getattr(user, "auth_profile", None)
    return profile.role if profile else "rc"
