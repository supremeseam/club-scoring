"""Glue between the Django models and the pure scoring engine."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from boats.models import Fleet
from racing.models import Finish, Payment, Protest, Race, Series, Start
from racing.ratings import resolve_rating
from scoring.low_point import RaceInput, Result, SeriesRules, score_guest, score_series, standing_key
from scoring.phrf_tod import SYSTEMS, elapsed_seconds, format_hms
from scoring.pursuit import pursuit_offsets

NON_FINISH = {"DNC", "DNS", "OCS", "DNF", "RET", "DSQ", "DNE", "UFD", "BFD", "TLE", "RCD"}


# ---- finish calculation -----------------------------------------------------
def recalc_finish(f: Finish) -> None:
    """Compute elapsed/corrected from the start, the rating snapshot and the finish time."""
    f.elapsed_seconds = f.corrected_seconds = None
    if f.status in NON_FINISH or not f.finish_time:
        return
    if f.start.race.is_pursuit:
        # the handicap is already in the start times: placing is by who crosses the line first, so the
        # "corrected" figure is simply time since the first gun, and elapsed is time since the boat's own start
        since_gun = elapsed_seconds(f.start.start_time, f.finish_time)
        f.corrected_seconds = since_gun
        f.elapsed_seconds = since_gun - _start_offsets(f.start).get(f.boat_id, 0)
        return
    dist = f.start.distance_nm
    f.elapsed_seconds = elapsed_seconds(f.start.start_time, f.finish_time)
    system = SYSTEMS[f.rating_type.method]
    needs_distance = f.rating_type.method == "tod"
    if f.rating_value is not None and (dist is not None or not needs_distance):
        f.corrected_seconds = system.corrected(f.elapsed_seconds, f.rating_value, dist)


# ---- pursuit starts ---------------------------------------------------------
def pursuit_schedule(start: Start) -> dict:
    """When each boat in this start should start, if the race is a pursuit. Based on the boats entered in the
    fleet (plus any moved here), their ratings for the race date, the distance and, for time-on-time, the
    race's target length. Boats that can't be scheduled are listed in `skipped` with the reason."""
    race = start.race
    method = start.rating_type.method
    out = {"is_pursuit": race.is_pursuit, "method": method, "distance_nm": start.distance_nm,
           "target_minutes": race.pursuit_target_minutes, "first_gun": start.start_time,
           "rows": [], "skipped": [], "error": None}
    if not race.is_pursuit:
        return out
    here = {f.boat_id: f for f in start.finishes.select_related("boat", "rating_type")}
    elsewhere = set(Finish.objects.filter(start__race=race).exclude(start=start).values_list("boat_id", flat=True))
    boats = {e.boat_id: e.boat for e in race.series.entries.filter(fleet_id=start.fleet_id).select_related("boat")}
    boats.update({b: f.boat for b, f in here.items()})
    ratings, found = {}, {}
    for boat_id, boat in boats.items():
        if boat_id in elsewhere:
            continue
        rtype = effective_rating_type(boat, start)
        f = here.get(boat_id)
        value = f.rating_value if f is not None and f.rating_value is not None else None
        if value is None:
            hit = resolve_rating(boat, rtype, race.date)
            value = hit[0] if hit else None
        if rtype.method != method:
            out["skipped"].append({"boat_id": boat_id, "boat": boat.name,
                                   "reason": f"scored with {rtype.code}, which can't share a pursuit with {start.rating_type.code}"})
        elif value is None:
            out["skipped"].append({"boat_id": boat_id, "boat": boat.name, "reason": f"no {rtype.code} rating"})
        else:
            ratings[boat_id], found[boat_id] = value, boat
    try:
        offsets = pursuit_offsets(method, ratings, start.distance_nm,
                                  race.pursuit_target_minutes * 60 if race.pursuit_target_minutes else None)
    except ValueError as e:
        out["error"] = str(e)
        return out
    order = sorted(ratings, key=lambda b: (offsets[b], found[b].name.lower()))
    for i, boat_id in enumerate(order, 1):
        b = found[boat_id]
        out["rows"].append({"order": i, "boat_id": boat_id, "boat": b.name, "sail_number": b.sail_number,
                            "rating": ratings[boat_id], "offset_seconds": offsets[boat_id],
                            "offset": format_hms(offsets[boat_id]),
                            "start_time": start.start_time + timedelta(seconds=offsets[boat_id])})
    return out


def _start_offsets(start: Start) -> dict:
    cache = getattr(start, "_pursuit_offsets", None)
    if cache is None:
        cache = {r["boat_id"]: r["offset_seconds"] for r in pursuit_schedule(start)["rows"]}
        start._pursuit_offsets = cache
    return cache


@transaction.atomic
def refresh_pursuit(start: Start) -> None:
    """Recalculate every finish in a pursuit start (the schedule moves when boats or ratings change)."""
    start = Start.objects.select_related("race__series", "rating_type", "course").get(pk=start.pk)
    if not start.race.is_pursuit:
        return
    for f in start.finishes.select_related("boat", "rating_type"):
        f.start = start
        recalc_finish(f)
        f.save()


def refresh_pursuit_series(series: Series) -> None:
    for race in series.races.all():
        refresh_pursuit_race(race)


def refresh_pursuit_race(race: Race) -> None:
    for st in race.starts.all():
        refresh_pursuit(st)


def effective_rating_type(boat, start: Start):
    """A boat with a fixed rating type (e.g. ORCA) always uses it, whatever the start uses."""
    return boat.fixed_rating_type or start.rating_type


def snapshot_rating(f: Finish, manual_value: Decimal | None = None) -> bool:
    """Freeze the rating on a finish. Returns False if no rating could be found."""
    f.rating_type = effective_rating_type(f.boat, f.start)
    if manual_value is not None:
        f.rating_value, f.rating_source = manual_value, Finish.Source.MANUAL
        return True
    hit = resolve_rating(f.boat, f.rating_type, f.start.race.date)
    if hit:
        f.rating_value, f.rating_source = hit[0], hit[1]
        return True
    f.rating_value = None
    return False


@transaction.atomic
def save_finish(f: Finish, manual_value: Decimal | None = None, resnapshot: bool = True) -> Finish:
    if resnapshot and (f._state.adding or manual_value is not None):
        snapshot_rating(f, manual_value)
    recalc_finish(f)
    f.save()
    touch_race(f.start.race)
    return f


def touch_race(race: Race) -> None:
    Race.objects.filter(pk=race.pk).update(results_updated_at=timezone.now())


@transaction.atomic
def reresolve_start(start: Start) -> list[dict]:
    """Re-run rating resolution for every non-manual finish in a start; return what changed."""
    changes = []
    for f in start.finishes.select_related("boat", "start__race", "start__course").exclude(
            rating_source=Finish.Source.MANUAL):
        old = (f.rating_type_id, f.rating_value, f.rating_source)
        snapshot_rating(f)
        recalc_finish(f)
        f.save()
        if old != (f.rating_type_id, f.rating_value, f.rating_source):
            changes.append({"boat": f.boat.name, "old": old[1], "new": f.rating_value,
                            "source": f.rating_source})
    touch_race(start.race)
    refresh_pursuit(start)              # a rating change moves the start times, so recalculate the whole start
    return changes


# ---- scoring ----------------------------------------------------------------
def rules_for(series: Series) -> SeriesRules:
    return SeriesRules(discard_thresholds=tuple(series.discard_thresholds or ()),
                       basis=series.scoring_basis, system=series.scoring_system, rcd_method=series.rcd_method,
                       rcd_max_credits=series.rcd_max_credits, tle_as=series.tle_as)


def _result(f: Finish) -> Result:
    return Result(f.boat_id, status=f.status or None, corrected=f.corrected_seconds,
                  penalty_pct=Decimal(f.penalty_pct or 0), redress_points=f.redress_points)


def _boat(b) -> dict:
    return {"id": b.id, "name": b.name, "sail_number": b.sail_number,
            "design": b.design, "skipper": b.skipper, "home_club": b.home_club}


def payment_sets(series: Series):
    """(paid whole series, {race_id: paid that race}, paid anything) as sets of boat ids."""
    paid_series, paid_race = set(), {}
    for p in Payment.objects.filter(series=series):
        if p.race_id is None:
            paid_series.add(p.boat_id)
        else:
            paid_race.setdefault(p.race_id, set()).add(p.boat_id)
    anyone = paid_series | {b for s in paid_race.values() for b in s}
    return paid_series, paid_race, anyone


def is_eligible(series: Series, race: Race, boat, paid_series: set, paid_race: dict) -> bool:
    """May this boat be scored in this race? Without payments required, always yes."""
    if not series.require_payment:
        return True
    if boat.id in paid_series or boat.id in paid_race.get(race.id, ()):
        return True
    return boat.is_member and race.members_free          # members race free in members-free races


def _fleet_data(series: Series):
    entries = list(series.entries.select_related("boat", "fleet"))
    races = list(series.races.prefetch_related("starts__finishes__boat",
                                               "starts__course", "starts__rating_type"))
    return entries, races


def _standings_block(label, fleet_id, entries, races, finishes_by_race_boat, rules, starts_by_race,
                     eligible=lambda race_id, boat_id: True):
    all_entries = entries
    entries = [e for e in entries if getattr(e, "scored", e.in_series)]   # guests are not scored
    guests = [e for e in all_entries if not getattr(e, "scored", e.in_series)]
    boats = {e.boat_id: e.boat for e in entries}
    counted = [r for r in races if r.status == Race.Status.SAILED and r.id in starts_by_race]
    # A boat that hasn't paid for a race gets no result in it (so DNC), and doesn't affect others' places.
    inputs = [RaceInput(r.id, [_result(f) for f in finishes_by_race_boat.get(r.id, [])
                               if f.boat_id in boats and eligible(r.id, f.boat_id)]) for r in counted]
    standings = score_series(inputs, list(boats), rules)

    boats_all = {e.boat_id: e.boat for e in all_entries}

    def row_of(s, guest=False, rank=None):
        return {"rank": s.rank if rank is None else rank, "guest": guest,
                "boat": _boat(boats_all[s.boat_id]),
                "total": s.total,
                "scores": [{"race_id": sc.race_id, "points": sc.points, "code": sc.code,
                            "discarded": sc.discarded, "average": sc.average_scored} for sc in s.scores]}

    items = [(standing_key(s), 0, row_of(s)) for s in standings]
    for g in guests:    # guests are scored as if entered, but never change a series boat's score
        g_inputs = [RaceInput(r.id, [_result(f) for f in finishes_by_race_boat.get(r.id, [])
                                     if f.boat_id in boats or f.boat_id == g.boat_id]) for r in counted]
        gs = score_guest(g_inputs, list(boats), g.boat_id, rules)
        k = standing_key(gs)
        would = 1 + sum(1 for s in standings if standing_key(s) < k)   # where it would rank
        items.append((k, 1, row_of(gs, guest=True, rank=would)))
    items.sort(key=lambda x: (x[0], x[1]))
    return {
        "fleet_id": fleet_id, "fleet_name": label,
        "races": [{"id": r.id, "number": r.number, "date": r.date} for r in counted],
        "standings": [row for _, _, row in items],
        "_scored": standings, "_counted": counted,
    }


def series_standings(series: Series, public: bool = False) -> dict:
    """Standings per fleet. With public=True and payment required, boats that have not paid are left out."""
    entries, races = _fleet_data(series)
    rules = rules_for(series)
    finishes_by_race: dict[int, list[Finish]] = {}
    starts_by_race_fleet: dict[tuple[int, int], Start] = {}
    for r in races:
        for st in r.starts.all():
            starts_by_race_fleet[(r.id, st.fleet_id)] = st
            finishes_by_race.setdefault(r.id, []).extend(st.finishes.all())

    paid_series, paid_race, anyone = payment_sets(series)
    race_by_id = {r.id: r for r in races}
    if public and series.require_payment:
        free = any(r.members_free for r in races)
        entries = [e for e in entries if e.boat_id in anyone or (e.boat.is_member and free)]
    boat_by_id = {e.boat_id: e.boat for e in entries}
    free_races = any(r.members_free for r in races)
    for e in entries:   # in-memory: who is scored at all (with payments required, only boats that paid)
        e.scored = e.in_series and (not series.require_payment or e.boat_id in anyone
                                    or (e.boat.is_member and free_races))

    def eligible(race_id: int, boat_id: int) -> bool:
        return is_eligible(series, race_by_id[race_id], boat_by_id[boat_id], paid_series, paid_race)

    out = {"fleets": [], "combined": None, "warnings": []}
    fleets = Fleet.objects.filter(pk__in={e.fleet_id for e in entries}).order_by("display_order", "name")
    for fleet in fleets:
        fe = [e for e in entries if e.fleet_id == fleet.id]
        fleet_boats = {e.boat_id for e in fe}
        fin = {rid: [f for f in fs if f.boat_id in fleet_boats] for rid, fs in finishes_by_race.items()}
        # a race counts for the fleet if it had a start, or one of its boats raced in another fleet's start
        sbr = ({rid for (rid, fid) in starts_by_race_fleet if fid == fleet.id}
               | {rid for rid, fs in fin.items() if fs})
        blk = _standings_block(fleet.name, fleet.id, fe, races, fin, rules, sbr, eligible)
        blk.pop("_scored"), blk.pop("_counted")
        out["fleets"].append(blk)

    if series.combined_overall and entries:
        fleet_ids = {e.fleet_id for e in entries}
        ok_races, skipped = set(), []
        for r in races:
            if r.status != Race.Status.SAILED:
                continue
            starts = list(r.starts.all())
            same = (len({s.fleet_id for s in starts} & fleet_ids) == len(fleet_ids) and
                    len({s.course_id for s in starts}) == 1 and starts[0].course_id is not None)
            (ok_races.add(r.id) if same else skipped.append(r.number))
        if skipped:
            out["warnings"].append(
                "Combined overall skips races where fleets sailed different courses: "
                + ", ".join(f"R{n}" for n in skipped))
        blk = _standings_block("Overall", None, entries, races, finishes_by_race, rules, ok_races, eligible)
        blk.pop("_scored"), blk.pop("_counted")
        out["combined"] = blk
    return out


def race_results(race: Race, public: bool = False) -> dict:
    """Per-fleet results for one race, with points as scored in the series."""
    series = race.series
    standings = series_standings(series, public)
    pts = {}
    for blk in standings["fleets"]:
        for row in blk["standings"]:
            for sc in row["scores"]:
                if sc["race_id"] == race.id:
                    pts[row["boat"]["id"]] = sc
    entries = {e.boat_id: e for e in series.entries.select_related("boat", "fleet")}
    paid_series, paid_race, _ = payment_sets(series)
    blocks = []
    starts = sorted(race.starts.select_related("fleet", "course", "rating_type"),
                    key=lambda s: (s.fleet.display_order, s.fleet.name, s.start_time))
    all_finishes = {f.boat_id: f for s_ in starts for f in s_.finishes.select_related("boat", "rating_type")}
    for st in starts:
        finishes = {b: f for b, f in all_finishes.items() if f.start_id == st.id}
        rows = []
        for e in entries.values():
            # listed in the start it raced in; boats with no result yet sit in their own fleet's start
            if e.boat_id in all_finishes:
                if e.boat_id not in finishes:
                    continue
            elif e.fleet_id != st.fleet_id:
                continue
            f = finishes.get(e.boat_id)
            sc = pts.get(e.boat_id)
            if not is_eligible(series, race, e.boat, paid_series, paid_race):
                if public:
                    continue                            # not shown publicly until paid
                sc = {"points": None, "code": "unpaid"}     # editors see it, flagged
            rows.append({
                "boat": _boat(e.boat),
                "rating_type": (f.rating_type if f else effective_rating_type(e.boat, st)).code,
                "rating": f.rating_value if f else None,
                "rating_source": f.rating_source if f else None,
                "finish_time": f.finish_time if f else None,
                "elapsed": format_hms(f.elapsed_seconds) if f and f.elapsed_seconds is not None else None,
                "corrected": format_hms(f.corrected_seconds) if f and f.corrected_seconds is not None else None,
                "corrected_seconds": f.corrected_seconds if f else None,
                "status": (f.status or None) if f else "DNC",
                "note": f.note if f else "",
                "points": sc["points"] if sc else None,
                "code": sc["code"] if sc else None,
                "place": None,
            })
        fin = sorted((r for r in rows if r["corrected_seconds"] is not None
                      and r["code"] in (None, "SCP", "ZFP", "unpaid")), key=lambda r: r["corrected_seconds"])
        for i, r in enumerate(fin, 1):
            r["place"] = i
        for i, r in enumerate(fin):   # tied corrected times share the lower place number
            if i and r["corrected_seconds"] == fin[i - 1]["corrected_seconds"]:
                r["place"] = fin[i - 1]["place"]
        rows.sort(key=lambda r: (r["place"] is None, r["place"] or 0,
                                 Decimal(r["points"] if r["points"] is not None else 999)))
        blocks.append({
            "fleet_id": st.fleet_id, "fleet_name": st.fleet.name,
            "course": st.course.name if st.course else None,
            "distance_nm": st.distance_nm, "rating_type": st.rating_type.code,
            "start_time": st.start_time, "rows": rows,
        })
    return {"race_id": race.id, "number": race.number, "date": race.date,
            "status": race.status, "final": race.results_final,
            "updated_at": race.results_updated_at,
            "series_id": series.id, "series_name": str(series), "fleets": blocks, "is_pursuit": race.is_pursuit,
            "protests_pending": Protest.objects.filter(race=race, status__in=Protest.PENDING).count()}
