"""Crew board API. Four routers, mounted with different authentication in api/api.py:

  public_router   no login (CSRF still checked on writes); every write is rate limited and has a honeypot
  crew_router     a signed-in crew account: only its own sign-ups
  skipper_router  a signed-in skipper account: only the boats the race committee linked to it, crew info only
  manage_router   race committee moderation (mounted under /api/manage)
"""
import hashlib
import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from accounts.audit import log_event
from accounts.ip import client_ip
from accounts.models import AccountProfile
from boats.models import Boat
from racing.models import Race, Series

from .models import (BoatCrewInfo, BoatManager, CrewPosting, CrewSignup, PublicAction, SkipperRequest, hash_token)

public_router = Router()
crew_router = Router()
skipper_router = Router()
manage_router = Router()

# anonymous writes allowed per address per hour
LIMITS = {"signup": 6, "skipper_req": 3, "register": 3}
MAX_PENDING_PER_BOAT = 40


# ---- helpers ------------------------------------------------------------------------------------------------
def _upcoming_races():
    return Race.objects.filter(status=Race.Status.SCHEDULED).exclude(series__status=Series.Status.DRAFT) \
        .select_related("series")


def _race_label(r: Race) -> str:
    return f"{r.series.name} - Race {r.number} ({r.date:%b %d})"


def _ip_hash(request) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), client_ip(request).encode(), hashlib.sha256).hexdigest()


def _rate_limit(request, kind: str) -> None:
    """Raise 429 when this address has made too many anonymous writes of this kind in the last hour."""
    ip = _ip_hash(request)
    now = timezone.now()
    PublicAction.objects.filter(created_at__lt=now - timedelta(days=2)).delete()
    recent = PublicAction.objects.filter(kind=kind, ip_hash=ip, created_at__gte=now - timedelta(hours=1)).count()
    if recent >= LIMITS[kind]:
        log_event("crew_rate_limited", request, level=logging.WARNING, kind=kind)
        raise HttpError(429, "Too many requests from your address. Please try again in an hour.")
    PublicAction.objects.create(kind=kind, ip_hash=ip)


def _csrf(request):
    from api.api import _check_csrf      # imported late: api.api imports this module
    _check_csrf(request)


def _clean_email(value: str) -> str:
    value = value.strip()
    try:
        validate_email(value)
    except ValidationError:
        raise HttpError(422, "Enter a valid email address")
    return value


def _need(value: str, what: str) -> str:
    value = value.strip()
    if not value:
        raise HttpError(422, f"{what} is required")
    return value


def _contact_for(boat: Boat) -> dict:
    """What a sailor sees after being accepted: the skipper's chosen contact route."""
    info = BoatCrewInfo.objects.filter(boat=boat).first()
    if info is None:
        return {"note": "The skipper will contact you."}
    out = {"name": info.contact_name or boat.skipper}
    if info.contact_preference == "email" and info.contact_email:
        out["email"] = info.contact_email
    elif info.contact_preference == "phone" and info.contact_phone:
        out["phone"] = info.contact_phone
    else:
        out["note"] = "The skipper will contact you."
    return out


# ---- schemas ------------------------------------------------------------------------------------------------
class SignupIn(Schema):
    posting_id: int | None = None
    boat_id: int | None = None
    race_id: int | None = None
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    phone: str = Field("", max_length=30)
    experience: str = Field("", max_length=200)
    message: str = Field("", max_length=500)
    website: str = Field("", max_length=200)             # honeypot: real people never see or fill this


class TokenIn(Schema):
    token: str = Field(max_length=100)


class SkipperRequestIn(Schema):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    boat_id: int | None = None
    boat_text: str = Field("", max_length=120)
    message: str = Field("", max_length=300)
    website: str = Field("", max_length=200)


class RegisterIn(Schema):
    username: str = Field(max_length=150)
    password: str = Field(max_length=256)
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    website: str = Field("", max_length=200)


class InfoIn(Schema):
    notes: str = Field("", max_length=500)
    contact_name: str = Field("", max_length=80)
    contact_email: str = Field("", max_length=254)
    contact_phone: str = Field("", max_length=30)
    contact_preference: str = Field("app", pattern="^(app|email|phone)$")


class PostingIn(Schema):
    race_id: int | None = None
    role: str = Field("", max_length=60)
    spots: int = Field(1, ge=1, le=20)
    experience: str = Field("", max_length=120)
    notes: str = Field("", max_length=500)
    is_open: bool = True


class RespondIn(Schema):
    status: str = Field(pattern="^(pending|accepted|declined)$")


class SkipperAccountIn(Schema):
    username: str = Field(max_length=150)
    password: str = Field(max_length=256)
    name: str = Field("", max_length=80)
    email: str = Field("", max_length=254)
    boat_ids: list[int] = Field(min_length=1, max_length=20)


class LinkIn(Schema):
    user_id: int
    boat_id: int


class ApproveIn(Schema):
    username: str = Field(max_length=150)
    password: str = Field(max_length=256)
    boat_ids: list[int] = Field(min_length=1, max_length=20)


# ---- public: browse -----------------------------------------------------------------------------------------
@public_router.get("/board")
def board(request):
    """Who needs crew. Counts and the skipper's own posting text only: no sailor's name or contact detail."""
    postings = (CrewPosting.objects.filter(is_open=True)
                .select_related("boat", "boat__default_fleet", "race", "race__series")
                .filter(Q(race__isnull=True) | Q(race__status=Race.Status.SCHEDULED))
                .exclude(race__series__status=Series.Status.DRAFT)
                .annotate(interested=Count("signups", filter=Q(signups__status="pending")),
                          filled=Count("signups", filter=Q(signups__status="accepted"))))
    notes = {i.boat_id: i.notes for i in BoatCrewInfo.objects.all()}
    boats: dict[int, dict] = {}
    for p in postings:
        if p.filled >= p.spots:                           # every spot is taken: nothing left to offer publicly
            continue
        b = boats.setdefault(p.boat_id, {
            "boat_id": p.boat_id, "name": p.boat.name, "sail_number": p.boat.sail_number, "design": p.boat.design,
            "fleet": p.boat.default_fleet.name if p.boat.default_fleet else "",
            "notes": notes.get(p.boat_id, ""), "postings": []})
        b["postings"].append({"id": p.id, "race_id": p.race_id, "race": _race_label(p.race) if p.race else "",
                              "race_date": p.race.date if p.race else None, "role": p.role, "spots": p.spots - p.filled,
                              "experience": p.experience, "notes": p.notes, "interested": p.interested})
    volunteers = {r["race_id"]: r["n"] for r in CrewSignup.objects.filter(
        boat__isnull=True, status__in=["pending", "accepted"]).values("race_id").annotate(n=Count("id"))}
    races = [{"race_id": r.id, "label": _race_label(r), "date": r.date, "volunteers": volunteers.get(r.id, 0)}
             for r in _upcoming_races().order_by("date")]
    anywhere = CrewSignup.objects.filter(boat__isnull=True, race__isnull=True, status="pending").count()
    return {"boats": sorted(boats.values(), key=lambda x: x["name"].lower()), "races": races,
            "open_to_any": anywhere}


@public_router.get("/options")
def options(request):
    """Choices for the sign-up form."""
    registered = Boat.objects.filter(managers__isnull=False).distinct().order_by("name")
    return {"boats": list(registered.values("id", "name", "sail_number")),       # boats with a skipper login
            "all_boats": list(Boat.objects.order_by("name").values("id", "name", "sail_number")),
            "races": [{"id": r.id, "label": _race_label(r)} for r in _upcoming_races().order_by("date")]}


# ---- public: sign up to crew --------------------------------------------------------------------------------
def _signup_out(su: CrewSignup) -> dict:
    out = {"id": su.id, "status": su.status, "created": su.created_at,
           "boat": su.boat.name if su.boat else "", "boat_id": su.boat_id,
           "race": _race_label(su.race) if su.race else "", "race_id": su.race_id,
           "role": su.posting.role if su.posting else "", "message": su.message}
    if su.status == CrewSignup.Status.ACCEPTED and su.boat:
        out["skipper_contact"] = _contact_for(su.boat)
    return out


@public_router.post("/signups")
def create_signup(request, data: SignupIn):
    _csrf(request)
    if data.website.strip():                              # a bot filled the hidden field: pretend it worked
        return {"id": 0, "token": "", "status": "pending"}
    name, email = _need(data.name, "Your name"), _clean_email(data.email)
    posting = None
    if data.posting_id is not None:
        posting = get_object_or_404(CrewPosting, pk=data.posting_id, is_open=True)
        boat, race = posting.boat, posting.race
    else:
        boat = get_object_or_404(Boat.objects.filter(managers__isnull=False).distinct(), pk=data.boat_id)             if data.boat_id else None
        race = get_object_or_404(_upcoming_races(), pk=data.race_id) if data.race_id else None
    dup = CrewSignup.objects.filter(email__iexact=email, boat=boat, race=race, posting=posting) \
        .exclude(status__in=["withdrawn", "declined"])
    if dup.exists():
        raise HttpError(409, "You have already signed up for this")
    if boat and CrewSignup.objects.filter(boat=boat, status="pending").count() >= MAX_PENDING_PER_BOAT:
        raise HttpError(409, "This boat has plenty of requests waiting. Try another boat or a race.")
    _rate_limit(request, "signup")
    token = CrewSignup.new_token()
    user = request.user if request.user.is_authenticated else None
    su = CrewSignup.objects.create(
        posting=posting, boat=boat, race=race, user=user, name=name, email=email, phone=data.phone.strip(),
        experience=data.experience.strip(), message=data.message.strip(), token_hash=hash_token(token))
    log_event("crew_signup", request, boat=boat.id if boat else "-", race=race.id if race else "-")
    return {"id": su.id, "token": token, "status": su.status}


def _by_token(token: str) -> CrewSignup:
    token = token.strip()
    su = CrewSignup.objects.filter(token_hash=hash_token(token)).select_related(
        "boat", "race", "race__series", "posting").first() if token else None
    if su is None:
        raise HttpError(404, "Sign-up not found")
    return su


@public_router.post("/signups/status")
def signup_status(request, data: TokenIn):
    _csrf(request)
    return _signup_out(_by_token(data.token))


@public_router.post("/signups/withdraw")
def signup_withdraw(request, data: TokenIn):
    _csrf(request)
    su = _by_token(data.token)
    su.status = CrewSignup.Status.WITHDRAWN
    su.save(update_fields=["status"])
    return _signup_out(su)


@public_router.post("/skipper-requests")
def skipper_request(request, data: SkipperRequestIn):
    _csrf(request)
    if data.website.strip():
        return {"ok": True}
    name, email = _need(data.name, "Your name"), _clean_email(data.email)
    boat = Boat.objects.filter(pk=data.boat_id).first() if data.boat_id else None
    if boat is None and not data.boat_text.strip():
        raise HttpError(422, "Tell us which boat you skipper")
    if SkipperRequest.objects.filter(email__iexact=email, status="pending").exists():
        raise HttpError(409, "You already have a request waiting for the race committee")
    _rate_limit(request, "skipper_req")
    SkipperRequest.objects.create(name=name, email=email, boat=boat, boat_text=data.boat_text.strip(),
                                  message=data.message.strip())
    log_event("skipper_request", request)
    return {"ok": True}


@public_router.post("/register")
def register_crew(request, data: RegisterIn):
    """Optional crew account: lets a sailor see and withdraw their sign-ups without keeping a link."""
    _csrf(request)
    if data.website.strip():
        return {"ok": True}
    username, name, email = _need(data.username, "Username"), _need(data.name, "Your name"), _clean_email(data.email)
    if User.objects.filter(username__iexact=username).exists():
        raise HttpError(409, "That username is taken")
    try:
        validate_password(data.password, User(username=username, first_name=name[:150], email=email))
    except ValidationError as e:
        raise HttpError(422, " ".join(e.messages))
    _rate_limit(request, "register")
    with transaction.atomic():
        user = User.objects.create_user(username=username, email=email, first_name=name[:150],
                                        password=data.password, is_staff=False, is_superuser=False)
        AccountProfile.objects.update_or_create(user=user, defaults={"role": "crew", "must_change_password": False})
    log_event("crew_registered", request, username)
    user = authenticate(request=request, username=username, password=data.password)
    if user is not None:
        login(request, user)
    return {"ok": True}


# ---- crew account ---------------------------------------------------------------------------------------------
@crew_router.get("/my/signups")
def my_signups(request):
    qs = CrewSignup.objects.filter(user=request.user).select_related("boat", "race", "race__series", "posting")
    return [_signup_out(x) for x in qs]


@crew_router.post("/my/signups/{pk}/withdraw")
def my_withdraw(request, pk: int):
    su = get_object_or_404(CrewSignup, pk=pk, user=request.user)
    su.status = CrewSignup.Status.WITHDRAWN
    su.save(update_fields=["status"])
    return {"ok": True}


# ---- skipper -------------------------------------------------------------------------------------------------
def _my_boats(user):
    return Boat.objects.filter(managers__user=user).select_related("default_fleet").distinct()


def _my_boat(user, boat_id: int) -> Boat:
    return get_object_or_404(_my_boats(user), pk=boat_id)


def _info_out(boat: Boat) -> dict:
    i = BoatCrewInfo.objects.filter(boat=boat).first()
    return {"notes": i.notes if i else "", "contact_name": i.contact_name if i else "",
            "contact_email": i.contact_email if i else "", "contact_phone": i.contact_phone if i else "",
            "contact_preference": i.contact_preference if i else "app"}


def _posting_out(p: CrewPosting) -> dict:
    return {"id": p.id, "race_id": p.race_id, "race": _race_label(p.race) if p.race else "",
            "role": p.role, "spots": p.spots, "experience": p.experience, "notes": p.notes, "is_open": p.is_open}


def unseen_requests(user) -> int:
    return CrewSignup.objects.filter(boat__managers__user=user, status="pending", seen_by_skipper=False).count()


@skipper_router.get("/skipper/overview")
def skipper_overview(request):
    boats = []
    for b in _my_boats(request.user):
        boats.append({"id": b.id, "name": b.name, "sail_number": b.sail_number, "design": b.design,
                      "info": _info_out(b),
                      "postings": [_posting_out(p) for p in b.crew_postings.select_related("race", "race__series")]})
    return {"boats": boats, "unseen": unseen_requests(request.user),
            "races": [{"id": r.id, "label": _race_label(r)} for r in _upcoming_races().order_by("date")]}


@skipper_router.put("/skipper/boats/{boat_id}/info")
def skipper_info(request, boat_id: int, data: InfoIn):
    boat = _my_boat(request.user, boat_id)
    if data.contact_email.strip():
        _clean_email(data.contact_email)
    if data.contact_preference == "email" and not data.contact_email.strip():
        raise HttpError(422, "Add an email address, or choose another contact option")
    if data.contact_preference == "phone" and not data.contact_phone.strip():
        raise HttpError(422, "Add a phone number, or choose another contact option")
    BoatCrewInfo.objects.update_or_create(boat=boat, defaults={
        "notes": data.notes.strip(), "contact_name": data.contact_name.strip(),
        "contact_email": data.contact_email.strip(), "contact_phone": data.contact_phone.strip(),
        "contact_preference": data.contact_preference})
    return _info_out(boat)


def _apply_posting(p: CrewPosting, data: PostingIn) -> CrewPosting:
    p.race = get_object_or_404(_upcoming_races(), pk=data.race_id) if data.race_id else None
    p.role, p.spots, p.is_open = data.role.strip(), data.spots, data.is_open
    p.experience, p.notes = data.experience.strip(), data.notes.strip()
    p.save()
    return p


@skipper_router.post("/skipper/boats/{boat_id}/postings")
def skipper_add_posting(request, boat_id: int, data: PostingIn):
    boat = _my_boat(request.user, boat_id)
    if boat.crew_postings.count() >= 30:
        raise HttpError(409, "That is a lot of postings. Close some first.")
    return _posting_out(_apply_posting(CrewPosting(boat=boat), data))


def _my_posting(user, pk: int) -> CrewPosting:
    return get_object_or_404(CrewPosting.objects.filter(boat__managers__user=user).distinct(), pk=pk)


@skipper_router.put("/skipper/postings/{pk}")
def skipper_edit_posting(request, pk: int, data: PostingIn):
    return _posting_out(_apply_posting(_my_posting(request.user, pk), data))


@skipper_router.delete("/skipper/postings/{pk}")
def skipper_delete_posting(request, pk: int):
    _my_posting(request.user, pk).delete()
    return {"ok": True}


def _signup_full(su: CrewSignup) -> dict:
    """Everything the skipper may see about a sailor, contact included."""
    return {**_signup_out(su), "name": su.name, "email": su.email, "phone": su.phone,
            "experience": su.experience, "seen": su.seen_by_skipper}


@skipper_router.get("/skipper/signups")
def skipper_signups(request):
    mine = _my_boats(request.user)
    # sailors who offered to crew on ANY boat in a race are visible to skippers with an open posting for that race
    open_races = CrewPosting.objects.filter(boat__in=mine, is_open=True, race__isnull=False).values("race_id")
    # sailors open to ANY boat and race are visible to skippers who have at least one open posting
    any_open = CrewPosting.objects.filter(boat__in=mine, is_open=True).exists()
    general = Q(boat__isnull=True, race__isnull=True) if any_open else Q(pk__in=[])
    qs = (CrewSignup.objects.filter(Q(boat__in=mine) | Q(boat__isnull=True, race_id__in=open_races) | general)
          .exclude(status="withdrawn").select_related("boat", "race", "race__series", "posting").distinct())
    return [_signup_full(x) for x in qs]


@skipper_router.post("/skipper/signups/{pk}/respond")
def skipper_respond(request, pk: int, data: RespondIn):
    su = get_object_or_404(CrewSignup.objects.filter(boat__managers__user=request.user).distinct(), pk=pk)
    su.status, su.seen_by_skipper = data.status, True
    su.save(update_fields=["status", "seen_by_skipper"])
    return {"ok": True}


@skipper_router.post("/skipper/signups/mark-seen")
def skipper_mark_seen(request):
    CrewSignup.objects.filter(boat__managers__user=request.user, seen_by_skipper=False).update(seen_by_skipper=True)
    return {"ok": True}


# ---- race committee ---------------------------------------------------------------------------------------------
def _make_skipper(username: str, password: str, boat_ids: list[int], name: str = "", email: str = "") -> User:
    username = _need(username, "Username")
    if User.objects.filter(username__iexact=username).exists():
        raise HttpError(409, "That username is taken")
    boats = list(Boat.objects.filter(pk__in=set(boat_ids)))
    if len(boats) != len(set(boat_ids)):
        raise HttpError(404, "Boat not found")
    try:
        validate_password(password, User(username=username, first_name=name[:150], email=email))
    except ValidationError as e:
        raise HttpError(422, " ".join(e.messages))
    with transaction.atomic():
        user = User.objects.create_user(username=username, email=email, first_name=name[:150], password=password,
                                        is_staff=False, is_superuser=False)
        # a temporary password: the skipper must choose their own at first sign-in
        AccountProfile.objects.update_or_create(user=user, defaults={"role": "skipper", "must_change_password": True})
        BoatManager.objects.bulk_create([BoatManager(user=user, boat=b) for b in boats])
    return user


def _skipper_out(u: User) -> dict:
    return {"user_id": u.id, "username": u.username, "name": u.first_name, "email": u.email,
            "active": u.is_active, "boats": [{"id": m.boat_id, "name": m.boat.name} for m in u.managed_boats.all()]}


@manage_router.get("/crew/skippers")
def rc_skippers(request):
    qs = User.objects.filter(auth_profile__role="skipper").prefetch_related("managed_boats__boat").order_by("username")
    return [_skipper_out(u) for u in qs]


@manage_router.post("/crew/skippers")
def rc_create_skipper(request, data: SkipperAccountIn):
    user = _make_skipper(data.username, data.password, data.boat_ids, data.name, data.email)
    log_event("skipper_created", request, user.get_username(), by=request.user.get_username())
    return _skipper_out(user)


@manage_router.post("/crew/skippers/link")
def rc_link(request, data: LinkIn):
    user = get_object_or_404(User, pk=data.user_id, auth_profile__role="skipper")
    BoatManager.objects.get_or_create(user=user, boat=get_object_or_404(Boat, pk=data.boat_id))
    return _skipper_out(user)


@manage_router.post("/crew/skippers/unlink")
def rc_unlink(request, data: LinkIn):
    user = get_object_or_404(User, pk=data.user_id, auth_profile__role="skipper")
    BoatManager.objects.filter(user=user, boat_id=data.boat_id).delete()
    return _skipper_out(user)


@manage_router.get("/crew/skipper-requests")
def rc_requests(request):
    return [{"id": r.id, "name": r.name, "email": r.email, "boat_id": r.boat_id,
             "boat": r.boat.name if r.boat else r.boat_text, "message": r.message, "created": r.created_at}
            for r in SkipperRequest.objects.filter(status="pending").select_related("boat")]


@manage_router.post("/crew/skipper-requests/{pk}/approve")
def rc_approve(request, pk: int, data: ApproveIn):
    req = get_object_or_404(SkipperRequest, pk=pk, status="pending")
    user = _make_skipper(data.username, data.password, data.boat_ids, req.name, req.email)
    req.status = "approved"
    req.save(update_fields=["status"])
    log_event("skipper_approved", request, user.get_username(), by=request.user.get_username())
    return _skipper_out(user)


@manage_router.post("/crew/skipper-requests/{pk}/reject")
def rc_reject(request, pk: int):
    req = get_object_or_404(SkipperRequest, pk=pk, status="pending")
    req.status = "rejected"
    req.save(update_fields=["status"])
    return {"ok": True}


@manage_router.get("/crew/signups")
def rc_signups(request):
    qs = CrewSignup.objects.select_related("boat", "race", "race__series", "posting")[:500]
    return [_signup_full(x) for x in qs]


@manage_router.delete("/crew/signups/{pk}")
def rc_delete_signup(request, pk: int):
    get_object_or_404(CrewSignup, pk=pk).delete()
    return {"ok": True}


@manage_router.get("/crew/postings")
def rc_postings(request):
    return [{**_posting_out(p), "boat": p.boat.name, "boat_id": p.boat_id}
            for p in CrewPosting.objects.select_related("boat", "race", "race__series")]


@manage_router.delete("/crew/postings/{pk}")
def rc_delete_posting(request, pk: int):
    get_object_or_404(CrewPosting, pk=pk).delete()
    return {"ok": True}
