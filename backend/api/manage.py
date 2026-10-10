"""Editor-only endpoints (mounted under /api/manage, session auth + CSRF)."""
import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from boats.models import Boat, BoatRating, Fleet, RatingType
from courses.models import Course, CourseLeg, Mark
from racing import services
from datetime import date as date_cls

from racing.models import STATUS_CODES, Finish, Payment, Protest, Race, Series, SeriesEntry, Start
from racing.ratings import certificate_expired, resolve_rating

from . import schemas as s

router = Router()
MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 2000


def D(v):
    return None if v is None else Decimal(str(v))


def _save(obj):
    try:
        obj.save()
    except IntegrityError as e:
        raise HttpError(409, f"Conflicts with an existing record ({e.__class__.__name__})")
    return obj


# ---- rating types / fleets ----------------------------------------------------
@router.get("/rating-types", response=list[s.RatingTypeIO])
def rating_types(request):
    return list(RatingType.objects.all())


@router.post("/rating-types", response=s.RatingTypeIO)
def create_rating_type(request, data: s.RatingTypeIO):
    return _save(RatingType(**data.dict(exclude={"id"})))


@router.put("/rating-types/{pk}", response=s.RatingTypeIO)
def update_rating_type(request, pk: int, data: s.RatingTypeIO):
    obj = get_object_or_404(RatingType, pk=pk)
    for k, v in data.dict(exclude={"id"}).items():
        setattr(obj, k, v)
    return _save(obj)


@router.get("/fleets", response=list[s.FleetIO])
def fleets(request):
    return list(Fleet.objects.all())


@router.post("/fleets", response=s.FleetIO)
def create_fleet(request, data: s.FleetIO):
    return _save(Fleet(**data.dict(exclude={"id"})))


@router.put("/fleets/{pk}", response=s.FleetIO)
def update_fleet(request, pk: int, data: s.FleetIO):
    obj = get_object_or_404(Fleet, pk=pk)
    for k, v in data.dict(exclude={"id"}).items():
        setattr(obj, k, v)
    return _save(obj)


@router.delete("/fleets/{pk}")
def delete_fleet(request, pk: int):
    try:
        get_object_or_404(Fleet, pk=pk).delete()
    except Exception:
        raise HttpError(409, "Fleet is in use")
    return {"ok": True}


# ---- boats & ratings ----------------------------------------------------------
def _rating_out(r: BoatRating) -> dict:
    return {"id": r.id, "rating_type_id": r.rating_type_id, "rating_type": r.rating_type.code,
            "value": r.value, "effective_from": r.effective_from, "certificate": r.certificate,
            "expires": r.expires, "notes": r.notes}


def _boat_out(b: Boat) -> dict:
    return {"id": b.id, "name": b.name, "sail_number": b.sail_number, "design": b.design,
            "skipper": b.skipper, "home_club": b.home_club, "is_member": b.is_member,
            "default_fleet_id": b.default_fleet_id,
            "fixed_rating_type_id": b.fixed_rating_type_id,
            "contact_email": b.contact_email, "contact_phone": b.contact_phone, "active": b.active,
            "ratings": [_rating_out(r) for r in b.ratings.select_related("rating_type")]}


@router.post("/boats/import", response=s.ImportOut)
def import_boats(request, effective_from: Form[str], file: File[UploadedFile]):
    """CSV: sail,name[,design,skipper,club,email,phone,fleet] plus one column per rating type code."""
    from datetime import date
    if file.size > MAX_IMPORT_BYTES:
        raise HttpError(413, "File too large")
    try:
        eff = date.fromisoformat(effective_from)
        text = file.read().decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError):
        raise HttpError(422, "Bad effective_from date or file encoding (use UTF-8 CSV)")
    reader = csv.DictReader(io.StringIO(text))
    cols = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
    if "sail" not in cols or "name" not in cols:
        raise HttpError(422, "CSV needs 'sail' and 'name' columns")
    types = {t.code.lower(): t for t in RatingType.objects.all()}
    fleets_by_name = {f.name.lower(): f for f in Fleet.objects.all()}
    out = {"boats_created": 0, "boats_updated": 0, "ratings_saved": 0, "errors": []}
    with transaction.atomic():
        for n, row in enumerate(reader, start=2):
            if n > MAX_IMPORT_ROWS:
                out["errors"].append("Row limit reached; remaining rows ignored")
                break
            g = lambda k: (row.get(cols[k]) or "").strip() if k in cols else ""  # noqa: E731
            sail, name = g("sail"), g("name")
            if not sail or not name:
                out["errors"].append(f"Row {n}: sail and name are required")
                continue
            defaults = {k: g(k) for k in ("design", "skipper") if k in cols}
            for src, dst in (("club", "home_club"), ("email", "contact_email"), ("phone", "contact_phone")):
                if src in cols:
                    defaults[dst] = g(src)
            if g("fleet"):
                fl = fleets_by_name.get(g("fleet").lower())
                if fl:
                    defaults["default_fleet"] = fl
                else:
                    out["errors"].append(f"Row {n}: unknown fleet {g('fleet')!r}")
            boat, created = Boat.objects.update_or_create(sail_number=sail, name=name,
                                                          defaults=defaults)
            out["boats_created" if created else "boats_updated"] += 1
            for code, rt in types.items():
                if code in cols and g(code):
                    try:
                        val = Decimal(g(code))
                    except Exception:
                        out["errors"].append(f"Row {n}: bad {rt.code} rating {g(code)!r}")
                        continue
                    BoatRating.objects.update_or_create(
                        boat=boat, rating_type=rt, effective_from=eff, defaults={"value": val})
                    out["ratings_saved"] += 1
    return out


@router.get("/boats", response=list[s.BoatOut])
def boats(request):
    return [_boat_out(b) for b in Boat.objects.prefetch_related("ratings__rating_type")]


@router.post("/boats", response=s.BoatOut)
def create_boat(request, data: s.BoatIn):
    return _boat_out(_save(Boat(**data.dict())))


@router.put("/boats/{pk}", response=s.BoatOut)
def update_boat(request, pk: int, data: s.BoatIn):
    obj = get_object_or_404(Boat, pk=pk)
    for k, v in data.dict().items():
        setattr(obj, k, v)
    return _boat_out(_save(obj))


@router.post("/boats/{pk}/ratings", response=s.RatingOut)
def add_rating(request, pk: int, data: s.RatingIn):
    boat = get_object_or_404(Boat, pk=pk)
    rt = get_object_or_404(RatingType, pk=data.rating_type_id)
    if rt.method == "tot" and data.value <= 0:
        raise HttpError(422, f"A {rt.code} rating (TCF) must be greater than zero")
    obj, _ = BoatRating.objects.update_or_create(
        boat=boat, rating_type=rt, effective_from=data.effective_from,
        defaults={"value": D(data.value), "certificate": data.certificate,
                  "expires": data.expires, "notes": data.notes})
    return _rating_out(obj)


@router.delete("/ratings/{pk}")
def delete_rating(request, pk: int):
    get_object_or_404(BoatRating, pk=pk).delete()
    return {"ok": True}


# ---- marks & courses ------------------------------------------------------------
@router.get("/marks", response=list[s.MarkIO])
def marks(request):
    return list(Mark.objects.all())


@router.post("/marks", response=s.MarkIO)
def create_mark(request, data: s.MarkIO):
    return _save(Mark(**data.dict(exclude={"id"})))


@router.put("/marks/{pk}", response=s.MarkIO)
def update_mark(request, pk: int, data: s.MarkIO):
    obj = get_object_or_404(Mark, pk=pk)
    for k, v in data.dict(exclude={"id"}).items():
        setattr(obj, k, v)
    return _save(obj)


def _course_out(c: Course) -> dict:
    return {"id": c.id, "name": c.name, "course_type_id": c.course_type_id,
            "course_type": c.course_type.code,
            "mark_ids": [leg.mark_id for leg in c.legs.order_by("order")],
            "computed_distance_nm": c.computed_distance_nm, "distance_nm": c.distance_nm,
            "distance_override": c.distance_override, "description": c.description}


def _check_course(data: s.CourseIn):
    if not data.name.strip():
        raise HttpError(422, "A course needs a name")
    if data.distance_override is not None and data.distance_override <= 0:
        raise HttpError(422, "Distance must be greater than zero")
    if data.distance_override is None and len(data.mark_ids) < 2:
        raise HttpError(422, "Add at least two marks, or enter the course distance")


def _set_legs(c: Course, mark_ids: list[int]):
    c.legs.all().delete()
    found = {m.id for m in Mark.objects.filter(pk__in=mark_ids)}
    if set(mark_ids) - found:
        raise HttpError(422, "Unknown mark")
    CourseLeg.objects.bulk_create(
        [CourseLeg(course=c, mark_id=m, order=i) for i, m in enumerate(mark_ids)])


@router.get("/courses", response=list[s.CourseOut])
def courses(request):
    return [_course_out(c) for c in Course.objects.select_related("course_type")]


@router.post("/courses", response=s.CourseOut)
@transaction.atomic
def create_course(request, data: s.CourseIn):
    _check_course(data)
    c = _save(Course(name=data.name, course_type_id=data.course_type_id,
                     distance_override=D(data.distance_override), description=data.description))
    _set_legs(c, data.mark_ids)
    return _course_out(c)


@router.put("/courses/{pk}", response=s.CourseOut)
@transaction.atomic
def update_course(request, pk: int, data: s.CourseIn):
    _check_course(data)
    c = get_object_or_404(Course, pk=pk)
    c.name, c.course_type_id = data.name, data.course_type_id
    c.distance_override = D(data.distance_override)
    c.description = data.description
    _save(c)
    _set_legs(c, data.mark_ids)
    return _course_out(c)


# ---- series ---------------------------------------------------------------------
def _series_out(x: Series) -> dict:
    return {"id": x.id, "name": x.name, "season": x.season, "description": x.description,
            "fleet_ids": list(x.fleets.values_list("id", flat=True)),
            "discard_thresholds": x.discard_thresholds, "scoring_basis": x.scoring_basis,
            "scoring_system": x.scoring_system,
            "rcd_method": x.rcd_method, "rcd_max_credits": x.rcd_max_credits,
            "tle_as": x.tle_as, "combined_overall": x.combined_overall, "status": x.status,
            "kind": x.kind, "require_payment": x.require_payment,
            "series_fee": x.series_fee, "race_fee": x.race_fee,
            "member_series_fee": x.member_series_fee, "member_race_fee": x.member_race_fee}


def _validate_series(data: s.SeriesIn):
    if data.scoring_basis not in ("entries", "starters"):
        raise HttpError(422, "scoring_basis must be entries or starters")
    if data.scoring_system not in ("low", "high"):
        raise HttpError(422, "scoring_system must be low or high")
    if data.rcd_method not in ("off", "all_other", "before"):
        raise HttpError(422, "bad rcd_method")
    if data.tle_as not in ("DNF", "DNC", "DSQ"):
        raise HttpError(422, "tle_as must be DNF, DNC or DSQ")
    if data.status not in ("draft", "active", "complete"):
        raise HttpError(422, "bad status")
    if any(t < 1 for t in data.discard_thresholds):
        raise HttpError(422, "discard thresholds must be >= 1")
    if not data.name.strip():
        raise HttpError(422, "A series needs a name")
    if not data.fleet_ids:
        raise HttpError(422, "Pick at least one fleet")
    if data.require_payment and data.series_fee <= 0 and data.race_fee <= 0:
        raise HttpError(422, "Set a series fee or a race fee when payment is required")


@router.get("/series", response=list[s.SeriesEditor])
def all_series(request):
    return [_series_out(x) for x in Series.objects.prefetch_related("fleets")]


@router.post("/series", response=s.SeriesEditor)
@transaction.atomic
def create_series(request, data: s.SeriesCreate):
    _validate_series(data)
    fields = data.dict(exclude={"fleet_ids", "schedule"})
    ser = _save(Series(**fields))
    ser.fleets.set(Fleet.objects.filter(pk__in=data.fleet_ids))
    if data.schedule:
        sc, d, n = data.schedule, data.schedule.first_date, 1
        if sc.interval_days < 1:
            raise HttpError(422, "interval_days must be >= 1")
        while d <= sc.last_date and n <= 200:
            Race.objects.create(series=ser, number=n, date=d)
            d += timedelta(days=sc.interval_days)
            n += 1
    return _series_out(ser)


@router.put("/series/{pk}", response=s.SeriesEditor)
@transaction.atomic
def update_series(request, pk: int, data: s.SeriesIn):
    _validate_series(data)
    ser = get_object_or_404(Series, pk=pk)
    for k, v in data.dict(exclude={"fleet_ids"}).items():
        setattr(ser, k, v)
    _save(ser)
    ser.fleets.set(Fleet.objects.filter(pk__in=data.fleet_ids))
    return _series_out(ser)


@router.get("/series/{pk}/entries", response=list[s.EntryIO])
def get_entries(request, pk: int):
    return list(SeriesEntry.objects.filter(series_id=pk).values("boat_id", "fleet_id", "in_series"))


@router.put("/series/{pk}/entries", response=list[s.EntryIO])
@transaction.atomic
def set_entries(request, pk: int, data: list[s.EntryIO]):
    """Replace the entry list. Boats with recorded finishes can't be removed."""
    ser = get_object_or_404(Series, pk=pk)
    wanted = {e.boat_id: (e.fleet_id, e.in_series) for e in data}
    for e in ser.entries.all():
        if e.boat_id not in wanted:
            if Finish.objects.filter(boat_id=e.boat_id, start__race__series=ser).exists():
                raise HttpError(409, f"{e.boat} has results in this series")
            e.delete()
    for boat_id, (fleet_id, in_series) in wanted.items():
        SeriesEntry.objects.update_or_create(series=ser, boat_id=boat_id,
                                             defaults={"fleet_id": fleet_id, "in_series": in_series})
    return get_entries(request, pk)


@router.post("/series/{pk}/entries/add", response=s.EntryIO)
def add_entry(request, pk: int, data: s.EntryIO):
    """Add (or update) one boat's entry, e.g. a boat joining a single race on the day."""
    ser = get_object_or_404(Series, pk=pk)
    get_object_or_404(Boat, pk=data.boat_id)
    if not ser.fleets.filter(pk=data.fleet_id).exists():
        ser.fleets.add(get_object_or_404(Fleet, pk=data.fleet_id))
    SeriesEntry.objects.update_or_create(series=ser, boat_id=data.boat_id,
                                         defaults={"fleet_id": data.fleet_id, "in_series": data.in_series})
    return data


@router.post("/single-races", response=s.RaceEditor)
@transaction.atomic
def create_single_race(request, data: s.SingleRaceIn):
    """A standalone race that is not part of a series (stored as a one-race 'single' series)."""
    if not data.fleet_ids:
        raise HttpError(422, "Pick at least one fleet")
    ser = _save(Series(name=data.name, season=data.date.year, description=data.description,
                       kind=Series.Kind.SINGLE, status=Series.Status.ACTIVE,
                       require_payment=data.require_payment,
                       series_fee=D(data.race_fee), race_fee=D(data.race_fee)))
    ser.fleets.set(Fleet.objects.filter(pk__in=data.fleet_ids))
    return _race_out(Race.objects.create(series=ser, number=1, date=data.date))


@router.post("/series/{pk}/clone", response=s.SeriesEditor)
@transaction.atomic
def clone_series(request, pk: int, data: s.CloneIn):
    """Season rollover: copy setup, entry list and a shifted schedule, but no results."""
    src = get_object_or_404(Series, pk=pk)
    new = _save(Series(
        name=data.name or src.name, season=data.season, description=src.description,
        discard_thresholds=src.discard_thresholds, scoring_basis=src.scoring_basis,
        scoring_system=src.scoring_system,
        rcd_method=src.rcd_method, rcd_max_credits=src.rcd_max_credits, tle_as=src.tle_as,
        combined_overall=src.combined_overall, status=Series.Status.DRAFT))
    new.fleets.set(src.fleets.all())
    SeriesEntry.objects.bulk_create(
        [SeriesEntry(series=new, boat_id=e.boat_id, fleet_id=e.fleet_id, in_series=e.in_series)
         for e in src.entries.all()])
    Race.objects.bulk_create(
        [Race(series=new, number=r.number, date=r.date + timedelta(days=data.shift_days),
              time_limit_minutes=r.time_limit_minutes) for r in src.races.all()])
    return _series_out(new)


# ---- races, starts, finishes ----------------------------------------------------
def _race_out(r: Race) -> dict:
    return {"id": r.id, "series_id": r.series_id, "number": r.number, "date": r.date,
            "status": r.status, "time_limit_minutes": r.time_limit_minutes,
            "results_final": r.results_final, "members_free": r.members_free}


def _check_race(data: s.RaceIn):
    if data.status not in ("scheduled", "sailed", "abandoned", "cancelled"):
        raise HttpError(422, "bad race status")


@router.get("/series/{pk}/races", response=list[s.RaceEditor])
def series_races(request, pk: int):
    return [_race_out(r) for r in Race.objects.filter(series_id=pk)]


@router.post("/series/{pk}/races", response=s.RaceEditor)
def create_race(request, pk: int, data: s.RaceIn):
    _check_race(data)
    ser = get_object_or_404(Series, pk=pk)
    number = data.number or (ser.races.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    return _race_out(_save(Race(series=ser, number=number, date=data.date, status=data.status,
                                time_limit_minutes=data.time_limit_minutes,
                                results_final=data.results_final, members_free=data.members_free)))


@router.put("/races/{pk}", response=s.RaceEditor)
def update_race(request, pk: int, data: s.RaceIn):
    _check_race(data)
    r = get_object_or_404(Race, pk=pk)
    if data.results_final and not r.results_final and r.protests.filter(status__in=Protest.PENDING).exists():
        raise HttpError(422, "Resolve the pending protests before marking results final")
    r.date, r.status = data.date, data.status
    r.time_limit_minutes, r.results_final = data.time_limit_minutes, data.results_final
    r.members_free = data.members_free
    if data.number:
        r.number = data.number
    _save(r)
    services.touch_race(r)
    return _race_out(r)


def _start_out(st: Start) -> dict:
    return {"id": st.id, "race_id": st.race_id, "fleet_id": st.fleet_id, "course_id": st.course_id,
            "start_time": st.start_time, "distance_override": st.distance_override,
            "distance_nm": st.distance_nm, "rating_type_id": st.rating_type_id}


@router.get("/races/{pk}/starts", response=list[s.StartOut])
def race_starts(request, pk: int):
    return [_start_out(x) for x in Start.objects.filter(race_id=pk).select_related("course")]


@router.put("/races/{pk}/starts", response=s.StartOut)
@transaction.atomic
def upsert_start(request, pk: int, data: s.StartIn):
    """Create or update a fleet's start. Changing course/rating type re-resolves ratings."""
    race = get_object_or_404(Race, pk=pk)
    course = get_object_or_404(Course, pk=data.course_id) if data.course_id else None
    rt_id = data.rating_type_id or (course.course_type_id if course else None)
    if rt_id is None:
        raise HttpError(422, "Pick a course or a rating type")
    rtype = get_object_or_404(RatingType, pk=rt_id)
    if data.distance_override is not None and data.distance_override <= 0:
        raise HttpError(422, "Distance must be greater than zero")
    distance = D(data.distance_override) if data.distance_override is not None else (
        course.distance_nm if course else None)
    if rtype.method == "tod" and (distance is None or distance <= 0):
        raise HttpError(422, f"A distance is required for {rtype.code} scoring: pick a course that has one, "
                             "or enter the distance")
    start, _ = Start.objects.get_or_create(
        race=race, fleet_id=data.fleet_id,
        defaults={"start_time": data.start_time, "rating_type_id": rt_id})
    start.course, start.start_time = course, data.start_time
    start.distance_override, start.rating_type_id = D(data.distance_override), rt_id
    start.save()
    changes = services.reresolve_start(start)
    resp = _start_out(start)
    resp["rating_changes"] = len(changes)
    return resp


@router.get("/starts/{pk}/rating-preview", response=list[s.RatingPreviewRow])
def rating_preview(request, pk: int):
    start = get_object_or_404(Start.objects.select_related("race__series", "rating_type"), pk=pk)
    rows = []
    for e in start.race.series.entries.filter(fleet_id=start.fleet_id).select_related("boat"):
        rtype = services.effective_rating_type(e.boat, start)
        hit = resolve_rating(e.boat, rtype, start.race.date)
        rows.append({"boat_id": e.boat_id, "boat": e.boat.name,
                     "rating": hit[0] if hit else None, "source": hit[1] if hit else None,
                     "expired": certificate_expired(e.boat, rtype, start.race.date),
                     "missing": hit is None})
    return rows


@router.post("/starts/{pk}/reresolve", response=s.ReresolveOut)
def reresolve(request, pk: int):
    changes = services.reresolve_start(get_object_or_404(Start, pk=pk))
    return {"changes": [{**c, "old": str(c["old"]), "new": str(c["new"])} for c in changes]}


def _finish_out(f: Finish) -> dict:
    return {"id": f.id, "boat_id": f.boat_id, "finish_time": f.finish_time, "status": f.status,
            "penalty_pct": f.penalty_pct, "redress_points": f.redress_points,
            "rating_type": f.rating_type.code, "rating_value": f.rating_value,
            "rating_source": f.rating_source, "elapsed_seconds": f.elapsed_seconds,
            "corrected_seconds": f.corrected_seconds, "note": f.note}


@router.get("/starts/{pk}/finishes", response=list[s.FinishOut])
def get_finishes(request, pk: int):
    return [_finish_out(f) for f in Finish.objects.filter(start_id=pk).select_related("rating_type")]


@router.put("/starts/{pk}/finishes", response=list[s.FinishOut])
@transaction.atomic
def upsert_finishes(request, pk: int, data: list[s.FinishIn]):
    start = get_object_or_404(Start.objects.select_related("race__series", "course", "rating_type"),
                              pk=pk)
    entries = ({e.boat_id for e in start.race.series.entries.filter(fleet_id=start.fleet_id)}
               | set(start.finishes.values_list("boat_id", flat=True)))      # incl. boats moved here
    for item in data:
        if item.boat_id not in entries:
            raise HttpError(422, f"Boat {item.boat_id} is not entered in this fleet")
        if item.status and item.status not in STATUS_CODES:
            raise HttpError(422, f"Unknown status code {item.status!r}")
        if item.finish_time and item.finish_time < start.start_time:
            raise HttpError(422, "Finish time is before the start (after midnight? use next day's date)")
        f = Finish.objects.filter(start=start, boat_id=item.boat_id).first()
        creating = f is None
        if creating:
            f = Finish(start=start, boat_id=item.boat_id, rating_type=start.rating_type)
        f.finish_time, f.status, f.note = item.finish_time, item.status, item.note.strip()[:300]
        f.penalty_pct, f.redress_points = D(item.penalty_pct) or Decimal(0), D(item.redress_points)
        manual = D(item.manual_rating)
        if creating or manual is not None:
            services.snapshot_rating(f, manual)
        if item.finish_time and item.status in ("", "SCP", "ZFP", "TLE"):
            # a finish can only be calculated with a rating (and the start has a distance if it needs one)
            if f.rating_value is None:
                raise HttpError(422, f"{Boat.objects.get(pk=item.boat_id).name} has no {f.rating_type.code} rating: "
                                     "add one to the boat or enter one manually")
            if f.rating_type.method == "tot" and f.rating_value <= 0:
                raise HttpError(422, "A time-on-time rating (TCF) must be greater than zero")
        services.save_finish(f, resnapshot=False)
    return get_finishes(request, pk)


@router.delete("/finishes/{pk}")
def delete_finish(request, pk: int):
    f = get_object_or_404(Finish.objects.select_related("start__race"), pk=pk)
    race = f.start.race
    f.delete()
    services.touch_race(race)
    return {"ok": True}


# ---- previews (include draft series and unsailed races) ----------------------------------
@router.get("/races/{pk}/results", response=s.RaceResults)
def preview_race_results(request, pk: int):
    return services.race_results(get_object_or_404(Race.objects.select_related("series"), pk=pk))


@router.get("/series/{pk}/standings", response=s.SeriesStandings)
def preview_standings(request, pk: int):
    ser = get_object_or_404(Series, pk=pk)
    summary = {"id": ser.id, "name": ser.name, "season": ser.season, "status": ser.status,
               "description": ser.description,
               "race_count": ser.races.filter(status=Race.Status.SAILED).count()}
    return {"series": summary, **services.series_standings(ser)}


@router.get("/races/{pk}", response=s.RaceEditor)
def get_race(request, pk: int):
    return _race_out(get_object_or_404(Race, pk=pk))


# ---- payments (editor-only; never exposed publicly) -----------------------------------------
def _payment_out(p: Payment) -> dict:
    return {"id": p.id, "boat_id": p.boat_id, "boat": p.boat.name, "race_id": p.race_id,
            "race_number": p.race.number if p.race_id else None, "amount": p.amount,
            "paid_on": p.paid_on, "method": p.method, "note": p.note}


def _default_fee(ser: Series, boat: Boat, race) -> Decimal:
    """The fee a boat owes: the member price for members when the series sets one."""
    if race is not None:
        return ser.member_race_fee if boat.is_member and ser.member_race_fee is not None else ser.race_fee
    return ser.member_series_fee if boat.is_member and ser.member_series_fee is not None else ser.series_fee


@router.get("/series/{pk}/payments", response=list[s.PaymentOut])
def list_payments(request, pk: int):
    return [_payment_out(p) for p in Payment.objects.filter(series_id=pk).select_related("boat", "race")]


@router.post("/series/{pk}/payments", response=s.PaymentOut)
@transaction.atomic
def record_payment(request, pk: int, data: s.PaymentIn):
    """Record (or correct) a payment. Amount defaults to the series fee, or the race fee for one race."""
    ser = get_object_or_404(Series, pk=pk)
    boat = get_object_or_404(Boat, pk=data.boat_id)
    race = get_object_or_404(Race, pk=data.race_id, series=ser) if data.race_id else None
    if ser.kind == Series.Kind.SINGLE and race is None:
        race = ser.races.first()                 # a single race has only its own fee
    amount = D(data.amount) if data.amount is not None else _default_fee(ser, boat, race)
    p, _ = Payment.objects.update_or_create(
        series=ser, boat_id=data.boat_id, race=race,
        defaults={"amount": amount, "paid_on": data.paid_on or date_cls.today(),
                  "method": data.method, "note": data.note})
    return _payment_out(Payment.objects.select_related("boat", "race").get(pk=p.pk))


@router.delete("/payments/{pk}")
def delete_payment(request, pk: int):
    get_object_or_404(Payment, pk=pk).delete()
    return {"ok": True}


# ---- protests (editor-only details; the public only sees "protest pending") ---------------------------------
def _protest_out(p: Protest) -> dict:
    return {"id": p.id, "race_id": p.race_id, "filed_on": p.filed_on, "protestor_id": p.protestor_id,
            "protestor": p.protestor.name if p.protestor_id else "Race committee",
            "protestee_ids": [b.id for b in p.protestees.all()],
            "protestees": [b.name for b in p.protestees.all()],
            "rules": p.rules, "status": p.status, "decision": p.decision}


def _save_protest(p: Protest, data: s.ProtestIn) -> Protest:
    if data.status not in {c for c, _ in Protest.Status.choices}:
        raise HttpError(422, "bad protest status")
    p.filed_on = data.filed_on or p.filed_on or date_cls.today()
    p.protestor_id, p.rules, p.status, p.decision = data.protestor_id, data.rules[:200], data.status, data.decision
    p.save()
    p.protestees.set(Boat.objects.filter(pk__in=data.protestee_ids))
    return p


@router.get("/races/{pk}/protests", response=list[s.ProtestOut])
def list_protests(request, pk: int):
    return [_protest_out(p) for p in Protest.objects.filter(race_id=pk).select_related("protestor")
            .prefetch_related("protestees")]


@router.post("/races/{pk}/protests", response=s.ProtestOut)
@transaction.atomic
def create_protest(request, pk: int, data: s.ProtestIn):
    race = get_object_or_404(Race, pk=pk)
    p = _save_protest(Protest(race=race, filed_on=data.filed_on or date_cls.today()), data)
    services.touch_race(race)
    return _protest_out(p)


@router.put("/protests/{pk}", response=s.ProtestOut)
@transaction.atomic
def update_protest(request, pk: int, data: s.ProtestIn):
    p = _save_protest(get_object_or_404(Protest, pk=pk), data)
    services.touch_race(p.race)
    return _protest_out(p)


@router.delete("/protests/{pk}")
def delete_protest(request, pk: int):
    p = get_object_or_404(Protest, pk=pk)
    race = p.race
    p.delete()
    services.touch_race(race)
    return {"ok": True}


# ---- fleet changes and removing boats from a race -------------------------------------------------------
@router.get("/races/{pk}/lineup", response=list[s.LineupRow])
def lineup(request, pk: int):
    """Which boats belong on which fleet's panel for this race: a boat sits in the start it raced in."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    raced = {f.boat_id: f.start.fleet_id
             for f in Finish.objects.filter(start__race=race).select_related("start")}
    out: dict[int, list[int]] = {}
    for e in race.series.entries.all():
        out.setdefault(raced.get(e.boat_id, e.fleet_id), []).append(e.boat_id)
    return [{"fleet_id": fid, "boat_ids": ids} for fid, ids in out.items()]


@router.post("/starts/{pk}/move-boat", response=s.MoveBoatOut)
@transaction.atomic
def move_boat(request, pk: int, data: s.MoveBoatIn):
    """Put a boat in another fleet, for this race only or for the rest of the series.

    Earlier results stay in the starts where the boat actually raced; only this race's result moves
    (when asked), and its rating is re-resolved for the new start.
    """
    start = get_object_or_404(Start.objects.select_related("race__series", "fleet"), pk=pk)
    ser = start.race.series
    to = get_object_or_404(Fleet, pk=data.to_fleet_id)
    if data.scope not in ("race", "series"):
        raise HttpError(422, "scope must be race or series")
    entry = SeriesEntry.objects.filter(series=ser, boat_id=data.boat_id).first()
    if entry is None:
        raise HttpError(422, "That boat is not entered")
    finish = (Finish.objects.filter(start=start, boat_id=data.boat_id)
              .select_related("boat", "start__race", "rating_type").first())
    target = Start.objects.filter(race=start.race, fleet=to).first()
    if to.id == start.fleet_id and data.scope == "race":
        raise HttpError(422, "The boat is already in that fleet for this race")
    moves = finish is not None and to.id != start.fleet_id and (data.scope == "race" or data.move_this_race)
    if data.scope == "race" and finish is None:
        raise HttpError(422, "Enter this boat's finish time or status first, then move it")
    if moves and target is None:
        raise HttpError(422, f"Set the start for {to.name} in this race first")
    warnings: list[str] = []
    if data.scope == "series":
        entry.fleet = to
        entry.save()
    ser.fleets.add(to)
    if moves:
        finish.start = target
        if finish.rating_source != Finish.Source.MANUAL:
            if not services.snapshot_rating(finish):
                warnings.append(f"{finish.boat.name} has no {target.rating_type.code} rating; enter one manually")
        else:
            finish.rating_type = services.effective_rating_type(finish.boat, target)
        services.recalc_finish(finish)
        finish.save()
    services.touch_race(start.race)
    return {"moved_result": moves, "warnings": warnings}


@router.delete("/starts/{pk}/boats/{boat_id}", response=s.RemoveBoatOut)
@transaction.atomic
def remove_boat(request, pk: int, boat_id: int, remove_entry: bool = False):
    """Clear a boat's result in this race; optionally take it out of the series entirely.

    Removing the entry is refused while the boat has results in other races. Payments are kept.
    """
    start = get_object_or_404(Start.objects.select_related("race__series"), pk=pk)
    ser = start.race.series
    cleared = Finish.objects.filter(start=start, boat_id=boat_id).delete()[0] > 0
    removed = False
    if remove_entry:
        if Finish.objects.filter(start__race__series=ser, boat_id=boat_id).exists():
            raise HttpError(409, "This boat has results in other races of the series. "
                                 "Clear those first, or just clear this race's result.")
        removed = SeriesEntry.objects.filter(series=ser, boat_id=boat_id).delete()[0] > 0
    services.touch_race(start.race)
    return {"cleared_result": cleared, "removed_entry": removed}
