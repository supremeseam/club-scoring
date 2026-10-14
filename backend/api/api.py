import csv
import io
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_login_failed
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_otp import login as otp_login
from django_otp import match_token
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.security import SessionAuth

from accounts.audit import log_event
from accounts.models import AccountProfile, account_role, must_change_password
from accounts.security import account_locked
from boats.models import Boat
from racing.models import Race, Series
from racing.services import race_results, series_standings
from results.csv_export import race_csv, standings_csv
from results.pdf import podium_pdf, standings_pdf

from . import schemas as s


class RoleAuth(SessionAuth):
    """A signed-in account with one of the allowed roles. CSRF is enforced on unsafe methods by SessionAuth.

    Three kinds of login stay apart: race committee ("rc", made by an admin) may use /api/manage/*; skipper and
    crew accounts can only reach their own small corner of /api/crew/*. A user who must change a temporary
    password is rejected with 403 "password_change_required" everywhere except the few routes that let them.
    """

    def __init__(self, roles: tuple[str, ...], allow_must_change: bool = False):
        super().__init__()
        self.roles = roles
        self.allow_must_change = allow_must_change

    def authenticate(self, request, key):
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return None
        if settings.REQUIRE_2FA and not user.is_verified():
            return None
        if account_role(user) not in self.roles:
            raise HttpError(403, "This account cannot do that")
        if not self.allow_must_change and must_change_password(user):
            raise HttpError(403, "password_change_required")
        return user


editor_auth = RoleAuth(("rc",))                       # race committee
skipper_auth = RoleAuth(("skipper",))
crew_auth = RoleAuth(("crew",))
account_auth = RoleAuth(("rc", "skipper", "crew"), allow_must_change=True)    # /auth/me, change-password, logout
api = NinjaAPI(title="Club Scoring API", version="1.0", auth=None, docs_url="/docs")


@api.exception_handler(PermissionDenied)
def _locked(request, exc):
    resp = api.create_response(request, {"detail": "Too many failed attempts. Try again later."}, status=429)
    resp["Retry-After"] = "900"
    return resp


# ---- auth ---------------------------------------------------------------------
def _check_csrf(request):
    reason = CsrfViewMiddleware(lambda r: None).process_view(request, None, (), {})
    if reason is not None:
        raise HttpError(403, "CSRF check failed")


def _me(user) -> dict:
    from crew.api import unseen_requests
    role = account_role(user)
    return {"username": user.get_username(), "is_admin": user.is_superuser and role == "rc", "role": role,
            "must_change_password": must_change_password(user),
            "unseen_requests": unseen_requests(user) if role == "skipper" else 0}


@api.get("/config", tags=["public"])
def site_config(request):
    """Per-club settings the SPA needs before login (all come from environment variables)."""
    colors = {"blue", "cyan", "teal", "green", "lime", "yellow", "orange", "red", "pink", "grape",
              "violet", "indigo"}
    import re
    hex_ok = re.fullmatch(r"#[0-9a-fA-F]{6}", settings.BRAND_COLOR_HEX or "")
    return {"club_name": settings.CLUB_NAME, "club_short_name": settings.CLUB_SHORT_NAME,
            "app_name": settings.APP_NAME, "burgee_url": settings.CLUB_BURGEE_URL,
            "brand_hex": settings.BRAND_COLOR_HEX if hex_ok else "",
            "tagline": settings.CLUB_TAGLINE, "website": settings.CLUB_WEBSITE,
            "logo_url": settings.CLUB_LOGO_URL,
            "brand_color": settings.BRAND_COLOR if settings.BRAND_COLOR in colors else "blue",
            "require_2fa": settings.REQUIRE_2FA,
            "password_min_length": settings.PASSWORD_MIN_LENGTH,
            "password_max_length": settings.PASSWORD_MAX_LENGTH}


@api.get("/auth/csrf", tags=["auth"])
def csrf(request):
    return {"csrfToken": get_token(request)}


@api.post("/auth/login", response=s.Me, tags=["auth"])
def login_view(request, data: s.LoginIn):
    _check_csrf(request)
    username = data.username.strip()
    if account_locked(username):                        # per-account backstop across all IP addresses
        log_event("account_locked", request, username, level=logging.WARNING)
        raise PermissionDenied
    user = authenticate(request=request, username=username, password=data.password)
    if user is None:
        raise HttpError(401, "Invalid credentials")
    device = None
    if settings.REQUIRE_2FA:
        device = match_token(user, data.otp.strip()) if data.otp.strip() else None
        if device is None:
            user_login_failed.send(sender=User, credentials={"username": username}, request=request)
            raise HttpError(401, "Invalid or missing authentication code")
    login(request, user)
    if device is not None:
        otp_login(request, device)
    return _me(user)


@api.post("/auth/logout", auth=account_auth, tags=["auth"])
def logout_view(request):
    logout(request)
    return {"ok": True}


@api.get("/auth/me", response=s.Me, auth=account_auth, tags=["auth"])
def me(request):
    return _me(request.user)


@api.post("/auth/change-password", auth=account_auth, tags=["auth"])
def change_password(request, data: s.ChangePasswordIn):
    """Change your own password (also how a temporary password is replaced). Needs the current password."""
    user = request.user
    if not user.check_password(data.current_password):
        # counts toward the lockouts, so a hijacked session can't be used to guess the current password
        user_login_failed.send(sender=User, credentials={"username": user.get_username()}, request=request)
        raise HttpError(400, "Your current password is incorrect")
    if data.new_password == data.current_password:
        raise HttpError(422, "Choose a password that is different from your current one")
    try:
        validate_password(data.new_password, user)
    except ValidationError as e:
        raise HttpError(422, " ".join(e.messages))
    user.set_password(data.new_password)
    user.save(update_fields=["password"])
    AccountProfile.objects.update_or_create(
        user=user, defaults={"must_change_password": False, "password_changed_at": timezone.now()})
    update_session_auth_hash(request, user)             # keep THIS session; every other one is signed out
    log_event("password_changed", request, user.get_username())
    return {"ok": True}


# ---- public ---------------------------------------------------------------------
def _public_series(series_id: int) -> Series:
    return get_object_or_404(Series.objects.exclude(status=Series.Status.DRAFT), pk=series_id)


def _summary(ser: Series) -> dict:
    return {"id": ser.id, "name": ser.name, "season": ser.season, "status": ser.status,
            "description": ser.description,
            "race_count": ser.races.filter(status=Race.Status.SAILED).count(),
            "kind": ser.kind,
            "race_id": ser.races.values_list("id", flat=True).first() if ser.kind == "single" else None}


@api.get("/series", response=list[s.SeriesSummary], tags=["public"])
def list_series(request):
    return [_summary(x) for x in Series.objects.exclude(status=Series.Status.DRAFT)]


@api.get("/series/{series_id}", response=s.SeriesDetail, tags=["public"])
def series_detail(request, series_id: int):
    ser = _public_series(series_id)
    races = ser.races.exclude(status=Race.Status.SCHEDULED)
    return {**_summary(ser), "combined_overall": ser.combined_overall,
            "discard_thresholds": ser.discard_thresholds,
            "races": [{"id": r.id, "number": r.number, "date": r.date, "status": r.status,
                       "final": r.results_final} for r in races]}


@api.get("/series/{series_id}/standings", response=s.SeriesStandings, tags=["public"])
def standings(request, series_id: int):
    ser = _public_series(series_id)
    return {"series": _summary(ser), **series_standings(ser, public=True)}


def _public_race(race_id: int) -> Race:
    return get_object_or_404(
        Race.objects.select_related("series").exclude(series__status=Series.Status.DRAFT)
        .exclude(status=Race.Status.SCHEDULED), pk=race_id)


@api.get("/races/{race_id}/results", response=s.RaceResults, tags=["public"])
def results(request, race_id: int):
    return race_results(_public_race(race_id), public=True)


@api.get("/boats/{boat_id}/history", response=s.BoatHistory, tags=["public"])
def boat_history(request, boat_id: int):
    boat = get_object_or_404(Boat, pk=boat_id)
    rows = []
    for ser in Series.objects.exclude(status=Series.Status.DRAFT).filter(entries__boat=boat):
        st = series_standings(ser, public=True)
        for blk in st["fleets"]:
            mine = next((r for r in blk["standings"] if r["boat"]["id"] == boat.id), None)
            if not mine:
                continue
            races = {r["id"]: r for r in blk["races"]}
            for sc in mine["scores"]:
                race = Race.objects.get(pk=sc["race_id"])
                res = race_results(race, public=True)
                fl = row = None
                for cand in res["fleets"]:          # the start the boat actually raced in
                    row = next((r for r in cand["rows"] if r["boat"]["id"] == boat.id), None)
                    if row:
                        fl = cand
                        break
                rows.append({
                    "series_id": ser.id, "series_name": str(ser), "race_id": race.id,
                    "race_number": race.number, "date": races[race.id]["date"],
                    "fleet": blk["fleet_name"], "rating_type": fl["rating_type"] if fl else "",
                    "rating": row["rating"] if row else None,
                    "elapsed": row["elapsed"] if row else None,
                    "corrected": row["corrected"] if row else None,
                    "status": sc["code"], "points": sc["points"],
                    "note": row["note"] if row else ""})
    rows.sort(key=lambda r: (r["date"], r["race_number"]), reverse=True)
    return {"boat": boat, "rows": rows}


def _file(content: bytes, ctype: str, name: str) -> HttpResponse:
    resp = HttpResponse(content, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@api.get("/races/{race_id}/results.csv", tags=["public"])
def results_csv(request, race_id: int):
    race = _public_race(race_id)
    return _file(race_csv(race_results(race, public=True)).encode(), "text/csv", f"race-{race.number}.csv")


@api.get("/series/{series_id}/standings.csv", tags=["public"])
def standings_csv_view(request, series_id: int):
    ser = _public_series(series_id)
    return _file(standings_csv(series_standings(ser, public=True)).encode(), "text/csv", f"series-{ser.id}.csv")


@api.get("/races/{race_id}/podium.pdf", tags=["public"])
def podium(request, race_id: int):
    return _file(podium_pdf(_public_race(race_id)), "application/pdf", f"podium-{race_id}.pdf")


@api.get("/series/{series_id}/standings.pdf", tags=["public"])
def standings_pdf_view(request, series_id: int):
    return _file(standings_pdf(_public_series(series_id)), "application/pdf", f"series-{series_id}.pdf")


from .manage import router as manage_router  # noqa: E402

api.add_router("/manage", manage_router, auth=editor_auth, tags=["manage"])

from crew.api import crew_router, skipper_router  # noqa: E402
from crew.api import manage_router as crew_manage_router, public_router as crew_public_router  # noqa: E402

api.add_router("/crew", crew_public_router, auth=None, tags=["crew"])
api.add_router("/crew", skipper_router, auth=skipper_auth, tags=["crew-skipper"])
api.add_router("/crew", crew_router, auth=crew_auth, tags=["crew-account"])
api.add_router("/manage", crew_manage_router, auth=editor_auth, tags=["manage"])
