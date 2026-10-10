"""Password rules in the spirit of NIST SP 800-63B: length and a blocklist, never composition rules.

Length is enforced by Django's MinimumLengthValidator (settings.PASSWORD_MIN_LENGTH); the common-password
list by CommonPasswordValidator. This validator adds the "context-specific" words NIST asks for.
"""
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

_WORDS = ("password", "passw0rd", "letmein", "welcome", "qwerty", "qwertyuiop", "iloveyou", "administrator")
_REPEATED = re.compile(r"(.{1,4}?)\1{2,}")      # 'abcabcabc', 'aaaa', '123123123'


def _norm(text: str) -> str:
    """Case-fold and keep letters/digits only, so 'Example-YC 2026!' compares as 'exampleyc2026'."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text or "").casefold())


def _is_run(s: str) -> bool:
    """A whole-password ascending/descending run such as 'abcdefghijklmno' or '987654321098765'."""
    if len(s) < 6:
        return False
    if s.isdigit():                       # digits wrap around: 1234567890123
        steps = {(int(b) - int(a)) % 10 for a, b in zip(s, s[1:])}
        return steps in ({1}, {9})
    steps = {ord(b) - ord(a) for a, b in zip(s, s[1:])}
    return steps in ({1}, {-1})


class ContextSpecificValidator:
    """Rejects passwords built from the account's own details, the club's name, or obvious patterns."""

    def validate(self, password, user=None):
        p = _norm(password)
        # Generic words only count when they ARE the password (optionally plus digits), so a long passphrase
        # that happens to contain "sailing" is fine.
        if any(re.fullmatch("(?:" + re.escape(w) + r")+\d*", p) for w in _WORDS):
            raise ValidationError("That password is too obvious.", code="password_common_word")
        # The club's own names and the account's details must not appear anywhere in it.
        context = [getattr(settings, name, "") for name in ("CLUB_NAME", "CLUB_SHORT_NAME", "APP_NAME")]
        if user is not None:
            context += [getattr(user, "username", ""), (getattr(user, "email", "") or "").split("@")[0],
                        getattr(user, "first_name", ""), getattr(user, "last_name", "")]
        for word in {_norm(w) for w in context}:
            if len(word) >= 4 and word in p:
                raise ValidationError("The password can't contain your username, your name, or the club's name.",
                                      code="password_context")
        if p and _REPEATED.fullmatch(p):
            raise ValidationError("The password can't be a repeated character or short pattern.", code="password_repeated")
        if _is_run(p):
            raise ValidationError("The password can't be a simple sequence of characters.", code="password_sequence")

    def password_changed(self, password, user=None):
        """Django calls this after a password is changed through its forms (e.g. the admin's own
        'change password' page): the temporary password is gone, so clear the must-change flag."""
        if user is not None and getattr(user, "pk", None):
            from .models import AccountProfile
            AccountProfile.objects.filter(user=user).update(must_change_password=False,
                                                            password_changed_at=timezone.now())

    def get_help_text(self):
        return ("Avoid your username, the club's name, and obvious words or patterns. "
                "Spaces and any characters are fine; a few random words make a good password.")
