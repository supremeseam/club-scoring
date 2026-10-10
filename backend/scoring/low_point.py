"""Low Point scoring per RRS Appendix A: race points, penalty codes, discards, ties."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

D = Decimal

# Codes that score as (boats that came to the starting area, or entries) + 1.
PENALTY_CODES = {"DNS", "OCS", "DNF", "RET", "DSQ", "DNE", "UFD", "BFD"}
NON_DISCARDABLE = {"DNE"}


def r1(x: Decimal) -> Decimal:
    """Round to one decimal, half up."""
    return x.quantize(D("0.1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Result:
    """One boat's outcome in one race."""
    boat_id: int
    status: str | None = None              # None = finished normally
    corrected: int | None = None           # corrected seconds (finishers, SCP, ZFP)
    penalty_pct: Decimal = D(0)            # SCP percentage
    redress_points: Decimal | None = None  # RDG points entered by the protest committee


@dataclass(frozen=True)
class RaceInput:
    race_id: int
    results: Sequence[Result]
    counts: bool = True                    # False for abandoned / cancelled races


@dataclass(frozen=True)
class SeriesRules:
    discard_thresholds: tuple[int, ...] = ()  # (5,) = 1 discard once 5 races are sailed
    basis: str = "entries"                    # "entries" or "starters"
    rcd_method: str = "off"                   # "off", "all_other", "before"
    rcd_max_credits: int = 2
    tle_as: str = "DNF"
    zfp_pct: Decimal = D(20)
    entries_override: int | None = None   # penalty basis when scoring a guest "as if" entered
    system: str = "low"                   # "low" (1st = 1 point) or "high" (1st = most points)


@dataclass
class RaceScore:
    race_id: int
    boat_id: int
    place: Decimal | None
    points: Decimal
    code: str | None
    discarded: bool = False
    average_scored: bool = False           # RCD / RDG scored by average


@dataclass
class BoatStanding:
    boat_id: int
    scores: list[RaceScore]
    total: Decimal
    rank: int
    high: bool = False          # high point: a bigger total is better


def _penalty_points(code: str, entries: int, starters: int, rules: SeriesRules) -> Decimal:
    if rules.system == "high":
        return D(0)                       # high point: boats that do not finish score nothing
    if code == "DNC":
        return D(entries + 1)
    return D((entries if rules.basis == "entries" else starters) + 1)


def score_race(race: RaceInput, entry_ids: Sequence[int], rules: SeriesRules
               ) -> dict[int, RaceScore]:
    """Score one race for every series entry. Entries with no result row are DNC.

    RCD and average-RDG come back as placeholders (points -1) resolved at series level.
    """
    entries = rules.entries_override or len(entry_ids)
    by_boat = {r.boat_id: r for r in race.results}
    rows = {bid: by_boat.get(bid) or Result(bid, status="DNC") for bid in entry_ids}

    def code_of(r: Result) -> str | None:
        return rules.tle_as if r.status == "TLE" else r.status

    starters = sum(1 for r in rows.values() if r.status not in ("DNC", "RCD"))
    high = rules.system == "high"
    top = D(entries if rules.basis == "entries" else starters)    # high point: what 1st place scores

    def pts_for_place(place: Decimal) -> Decimal:
        return max(top - place + 1, D(0)) if high else place

    ranked = sorted((r for r in rows.values()
                     if code_of(r) in (None, "SCP", "ZFP") and r.corrected is not None),
                    key=lambda r: r.corrected)
    place_of: dict[int, Decimal] = {}
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1].corrected == ranked[i].corrected:
            j += 1
        avg = D(i + 1 + j + 1) / D(2)
        for k in range(i, j + 1):
            place_of[ranked[k].boat_id] = avg
        i = j + 1

    dnf_pts = _penalty_points("DNF", entries, starters, rules)
    out: dict[int, RaceScore] = {}
    for bid, r in rows.items():
        code = code_of(r)
        rid = race.race_id
        if code is None:
            if bid not in place_of:    # finisher without a time: treat as DNF
                out[bid] = RaceScore(rid, bid, None, dnf_pts, "DNF")
            else:
                out[bid] = RaceScore(rid, bid, place_of[bid], pts_for_place(place_of[bid]), None)
        elif code in ("SCP", "ZFP"):
            pct = r.penalty_pct if code == "SCP" else (r.penalty_pct or rules.zfp_pct)
            base = place_of.get(bid)
            if base is None:
                out[bid] = RaceScore(rid, bid, None, dnf_pts, code)
            else:
                pen = (pct / D(100) * D(starters)).quantize(D(1), rounding=ROUND_HALF_UP)
                worse = pts_for_place(base + pen) if high else min(base + pen, dnf_pts)
                out[bid] = RaceScore(rid, bid, base, worse, code)
        elif code in PENALTY_CODES or code == "DNC":
            out[bid] = RaceScore(rid, bid, None,
                                 _penalty_points(code, entries, starters, rules), code)
        elif code == "RDG":
            pts = r.redress_points if r.redress_points is not None else D(-1)
            out[bid] = RaceScore(rid, bid, None, pts, "RDG")
        elif code == "RCD":
            out[bid] = RaceScore(rid, bid, None, D(-1), "RCD")
        else:
            raise ValueError(f"Unknown status code {code!r}")
    return out


def _average(scores: list[RaceScore], idx: int, method: str) -> Decimal | None:
    """Average of a boat's regular scores (excluding RCD / average-RDG), per method."""
    regular = [(n, s) for n, s in enumerate(scores)
               if s.code != "RCD" and not (s.code == "RDG" and s.points < 0)]
    if method == "before":
        pool = [s.points for n, s in regular if n < idx]
        if pool:
            return r1(sum(pool) / D(len(pool)))
    pool = [s.points for n, s in regular if n != idx]
    return r1(sum(pool) / D(len(pool))) if pool else None


def _resolve_averages(per_boat: dict[int, list[RaceScore]], entries: int,
                      rules: SeriesRules) -> None:
    for scores in per_boat.values():
        used = 0
        # Resolve against the raw (pre-average) scores so results don't depend on order.
        raw = [RaceScore(s.race_id, s.boat_id, s.place, s.points, s.code) for s in scores]
        for idx, s in enumerate(scores):
            if s.code == "RCD":
                if rules.rcd_method != "off" and used < rules.rcd_max_credits:
                    avg = _average(raw, idx, rules.rcd_method)
                    if avg is not None:
                        s.points, s.average_scored = avg, True
                        used += 1
                        continue
                s.points, s.code = _penalty_points("DNC", entries, entries, rules), "DNC"
            elif s.code == "RDG" and s.points < 0:
                method = rules.rcd_method if rules.rcd_method != "off" else "all_other"
                avg = _average(raw, idx, method)
                s.points = avg if avg is not None else _penalty_points("DNC", entries, entries, rules)
                s.average_scored = True


def score_series(races: Sequence[RaceInput], entry_ids: Sequence[int],
                 rules: SeriesRules) -> list[BoatStanding]:
    """Score a series. `races` must be in race order. Returns standings sorted by rank."""
    counted = [r for r in races if r.counts]
    entries = rules.entries_override or len(entry_ids)
    per_boat: dict[int, list[RaceScore]] = {b: [] for b in entry_ids}
    for race in counted:
        scored = score_race(race, entry_ids, rules)
        for bid in entry_ids:
            per_boat[bid].append(scored[bid])
    _resolve_averages(per_boat, entries, rules)

    n_discards = sum(1 for t in rules.discard_thresholds if len(counted) >= t)
    for scores in per_boat.values():
        if n_discards:
            # Worst first (highest points in low point, lowest in high point). Credit (RCD-average)
            # scores are discarded only after sailed races.
            sign = -1 if rules.system == "high" else 1
            cands = sorted((s for s in scores if s.code not in NON_DISCARDABLE),
                           key=lambda s: (0 if s.average_scored else 1, sign * s.points), reverse=True)
            for s in cands[:n_discards]:
                s.discarded = True

    standings = [BoatStanding(bid, sc, sum((s.points for s in sc if not s.discarded), D(0)), 0,
                              high=rules.system == "high")
                 for bid, sc in per_boat.items()]

    key = standing_key
    standings.sort(key=key)
    for i, st in enumerate(standings):
        same = i > 0 and key(st) == key(standings[i - 1])
        st.rank = standings[i - 1].rank if same else i + 1
    return standings


def standing_key(st: BoatStanding):
    """Sort key: total, then A8.1 (best scores), then A8.2 (most recent race). Lower is better
    (high point negates the points so the same ordering logic applies)."""
    sign = -1 if st.high else 1
    kept = sorted(sign * s.points for s in st.scores if not s.discarded)  # A8.1
    last_first = [sign * s.points for s in reversed(st.scores)]            # A8.2
    return (sign * st.total, kept, last_first)


def score_guest(races: Sequence[RaceInput], entry_ids: Sequence[int], guest_id: int,
                rules: SeriesRules) -> BoatStanding:
    """Score a guest as if it had been entered, without changing anyone else's score.

    The guest takes a place among the series boats' results (series boats keep theirs) and
    penalties use the series' own entry count. `races` must include the guest's results.
    """
    virtual = SeriesRules(**{**rules.__dict__, "entries_override": len(entry_ids)})
    standings = score_series(races, [*entry_ids, guest_id], virtual)
    return next(s for s in standings if s.boat_id == guest_id)
