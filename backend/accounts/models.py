from django.conf import settings
from django.db import models


class AccountProfile(models.Model):
    """Security state for a login account (kept separate so the stock User model is untouched)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_profile")
    # True after an administrator creates the account or sets a temporary password: the person must
    # choose their own password before they can do anything else.
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} (must change: {self.must_change_password})"


def must_change_password(user) -> bool:
    profile = getattr(user, "auth_profile", None)      # a missing profile just means "no"
    return bool(profile and profile.must_change_password)
