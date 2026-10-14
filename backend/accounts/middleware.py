import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect, JsonResponse

from .audit import log_event
from .models import must_change_password

# Admin pages a user who must change their password may still reach.
_ADMIN_ALLOWED = ("logout/", "password_change/", "password_change/done/", "jsi18n/")


class AccountSecurityMiddleware:
    """Three small jobs, kept in one place and placed after AuthenticationMiddleware:

    1. Absolute session limit: a login older than SESSION_ABSOLUTE_MAX_SECONDS is ended, however recently it
       was used. (The idle limit is Django's SESSION_COOKIE_AGE with SESSION_SAVE_EVERY_REQUEST.) A session
       without a start marker is treated as expired.
    2. Keeps a user who must change their password out of the Django admin, except the pages needed to do so.
       (The API enforces the same rule in RoleAuth.)
    3. Marks /api/auth/* responses as never cacheable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            started = request.session.get("auth_started_at")
            if not isinstance(started, int) or time.time() - started > settings.SESSION_ABSOLUTE_MAX_SECONDS:
                log_event("session_expired_absolute", request, user.get_username())
                logout(request)
            elif must_change_password(user):
                admin = "/" + settings.ADMIN_URL
                if request.path.startswith(admin) and not request.path.removeprefix(admin) in _ADMIN_ALLOWED:
                    if request.path.startswith("/api/"):
                        return JsonResponse({"detail": "password_change_required"}, status=403)
                    return HttpResponseRedirect(admin + "password_change/")
        response = self.get_response(request)
        if request.path.startswith("/api/auth/"):
            response["Cache-Control"] = "no-store"
        return response
