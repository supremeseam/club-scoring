from datetime import datetime
from decimal import Decimal as D

from scoring.low_point import RaceInput, Result, SeriesRules, score_guest, score_race, score_series
from scoring.phrf_tod import corrected_seconds, elapsed_seconds, format_hms, time_on_time


def fin(b, c):
    return Result(b, corrected=c)


def st(b, s):
    return Result(b, status=s)


# ---- time-on-distance ------------------------------------------------------
def test_corrected_basic():
    # 1:30:00 elapsed, rating 120 s/nm, 6.5 nm -> 5400 - 780
    assert corrected_seconds(5400, 120, D("6.5")) == 4620


def test_corrected_negative_rating_adds_time():
    assert corrected_seconds(5400, -12, D("6.5")) == 5400 + 78


def test_allowance_rounded_to_whole_second_first():
    assert corrected_seconds(1000, D("1.5"), D("1")) == 998   # allowance 1.5 -> 2
    assert corrected_seconds(1000, -3, D("11.7")) == 1035      # -35.1 -> -35


def test_after_midnight():
    s = datetime(2027, 7, 3, 23, 30)
    f = datetime(2027, 7, 4, 1, 15)
    assert elapsed_seconds(s, f) == 6300
    assert format_hms(6300) == "1:45:00"


# ---- single race ------------------------------------------------------------
def test_places_and_ties_average():
    r = RaceInput(1, [fin(1, 100), fin(2, 90), fin(3, 90), fin(4, 120)])
    s = score_race(r, [1, 2, 3, 4], SeriesRules())
    assert s[2].points == D("1.5") and s[3].points == D("1.5")
    assert s[1].points == 3 and s[4].points == 4


def test_penalty_codes_entries_basis():
    r = RaceInput(1, [fin(1, 100), st(2, "DNF"), st(3, "OCS")])  # boat 4 has no row -> DNC
    s = score_race(r, [1, 2, 3, 4], SeriesRules())
    assert s[1].points == 1
    assert s[2].points == s[3].points == s[4].points == 5


def test_starters_basis():
    r = RaceInput(1, [fin(1, 100), st(2, "DNF"), st(3, "DNS")])  # boat 4 DNC
    s = score_race(r, [1, 2, 3, 4], SeriesRules(basis="starters"))
    assert s[2].points == 4 and s[3].points == 4   # 3 came to the area, +1
    assert s[4].points == 5                        # DNC always entries + 1


def test_disqualified_boat_takes_no_place():
    r = RaceInput(1, [fin(1, 100), st(2, "DSQ"), fin(3, 110)])
    s = score_race(r, [1, 2, 3], SeriesRules())
    assert s[3].points == 2 and s[2].points == 4


def test_tle_scores_as_dnf():
    r = RaceInput(1, [fin(1, 100), st(2, "TLE")])
    s = score_race(r, [1, 2, 3], SeriesRules())
    assert s[2].code == "DNF" and s[2].points == 4


def test_scp_penalty_capped_at_dnf():
    rows = [fin(i, 100 + i) for i in range(1, 11)]
    rows[0] = Result(1, status="SCP", corrected=101, penalty_pct=D(20))
    s = score_race(RaceInput(1, rows), list(range(1, 11)), SeriesRules())
    assert s[1].points == 3          # place 1 + 20% of 10 boats
    rows[0] = Result(1, status="SCP", corrected=101, penalty_pct=D(100))
    s = score_race(RaceInput(1, rows), list(range(1, 11)), SeriesRules())
    assert s[1].points == 11         # capped at DNF


# ---- series -----------------------------------------------------------------
def make_races(table):
    """table: list of {boat: corrected | 'CODE'}"""
    out = []
    for n, row in enumerate(table, 1):
        out.append(RaceInput(n, [st(b, v) if isinstance(v, str) else fin(b, v)
                                 for b, v in row.items()]))
    return out


def test_discards_and_total():
    races = make_races([{1: 10, 2: 20, 3: 30}, {1: 30, 2: 10, 3: 20}, {1: 20, 2: 30, 3: 10}])
    a = score_series(races, [1, 2, 3], SeriesRules())
    assert [x.total for x in a] == [6, 6, 6]
    b = score_series(races, [1, 2, 3], SeriesRules(discard_thresholds=(3,)))
    assert all(x.total == 3 for x in b)
    assert all(sum(s.discarded for s in x.scores) == 1 for x in b)


def test_discard_threshold_not_met():
    races = make_races([{1: 10, 2: 20}, {1: 20, 2: 10}])
    out = score_series(races, [1, 2], SeriesRules(discard_thresholds=(3,)))
    assert not any(s.discarded for x in out for s in x.scores)


def test_dne_not_discardable():
    races = make_races([{1: "DNE", 2: 10}, {1: 10, 2: 20}, {1: 10, 2: 20}])
    out = {x.boat_id: x for x in score_series(races, [1, 2], SeriesRules(discard_thresholds=(3,)))}
    dne = out[1].scores[0]
    assert dne.points == 3 and not dne.discarded
    assert out[1].total == 3 + 1   # discarded one of the 1s... see below
    # boat 1: scores 3(DNE), 1, 1 -> discard a 1 -> total 4


def test_abandoned_races_ignored():
    races = make_races([{1: 10, 2: 20}, {1: 20, 2: 10}, {1: 10, 2: 20}])
    races[1] = RaceInput(2, races[1].results, counts=False)
    out = score_series(races, [1, 2], SeriesRules(discard_thresholds=(3,)))
    assert not any(s.discarded for x in out for s in x.scores)   # only 2 counted
    assert len(out[0].scores) == 2


def test_late_entry_scores_dnc_for_missed():
    races = make_races([{1: 10, 2: 20}, {1: 10, 2: 20, 3: 30}])
    out = {x.boat_id: x for x in score_series(races, [1, 2, 3], SeriesRules())}
    assert out[3].scores[0].code == "DNC" and out[3].scores[0].points == 4


def test_tiebreak_a81_then_a82():
    # boat1: 1,3  boat2: 2,2  boat3: 3,1 -> all total 4.
    # A8.1: sorted scores [1,3] (boats 1 and 3) beat [2,2] (boat 2).
    # A8.2: boats 1 and 3 still tied, so the better score in the last race wins: boat 3.
    races = make_races([{1: 10, 2: 20, 3: 99}, {1: 30, 2: 20, 3: 10}])
    out = score_series(races, [1, 2, 3], SeriesRules())
    assert [x.boat_id for x in out] == [3, 1, 2]
    assert [x.rank for x in out] == [1, 2, 3]


def test_true_tie_shares_rank():
    races = make_races([{1: 10, 2: 10}])
    out = score_series(races, [1, 2], SeriesRules())
    assert [x.rank for x in out] == [1, 1]


# ---- RC duty & redress ------------------------------------------------------
def rcd_races():
    return make_races([{1: 10, 2: 20, 3: 30}, {1: 20, 2: 10, 3: 30}, {1: "RCD", 2: 10, 3: 20}])


def test_rcd_off_scores_dnc():
    out = {x.boat_id: x for x in score_series(rcd_races(), [1, 2, 3], SeriesRules())}
    assert out[1].scores[2].points == 4 and out[1].scores[2].code == "DNC"


def test_rcd_all_other_average():
    out = {x.boat_id: x for x in score_series(rcd_races(), [1, 2, 3], SeriesRules(rcd_method="all_other"))}
    assert out[1].scores[2].points == D("1.5")      # avg of 1 and 2


def test_rcd_before_average():
    races = make_races([{1: 10, 2: 20, 3: 30}, {1: "RCD", 2: 10, 3: 30}, {1: 20, 2: 10, 3: 30}])
    out = {x.boat_id: x for x in score_series(races, [1, 2, 3], SeriesRules(rcd_method="before"))}
    assert out[1].scores[1].points == 1             # only race 1 (place 1) is before


def test_rcd_cap():
    races = make_races([{1: "RCD", 2: 10}, {1: "RCD", 2: 10}, {1: "RCD", 2: 10}, {1: 10, 2: 20}])
    out = {x.boat_id: x for x in score_series(races, [1, 2], SeriesRules(rcd_method="all_other", rcd_max_credits=2))}
    pts = [s.points for s in out[1].scores]
    assert pts == [1, 1, 3, 1]                       # third RCD over cap -> DNC (entries+1)


def test_rcd_not_discarded_before_sailed():
    races = make_races([{1: 10, 2: 20}, {1: "RCD", 2: 10}, {1: 20, 2: 10}, {1: 20, 2: 10}])
    out = {x.boat_id: x for x in score_series(
        races, [1, 2], SeriesRules(rcd_method="all_other", discard_thresholds=(4,)))}
    s = out[1].scores
    assert s[1].average_scored and not s[1].discarded
    assert s[2].discarded or s[3].discarded            # a sailed 2 was discarded instead


def test_rdg_entered_points():
    races = [RaceInput(1, [fin(1, 10), fin(2, 20)]),
             RaceInput(2, [Result(1, status="RDG", redress_points=D("1.5")), fin(2, 10)])]
    out = {x.boat_id: x for x in score_series(races, [1, 2], SeriesRules())}
    assert out[1].scores[1].points == D("1.5")


def test_rdg_average_when_no_points():
    races = [RaceInput(1, [fin(1, 10), fin(2, 20)]), RaceInput(2, [fin(1, 10), fin(2, 20)]),
             RaceInput(3, [Result(1, status="RDG"), fin(2, 10)])]
    out = {x.boat_id: x for x in score_series(races, [1, 2], SeriesRules())}
    assert out[1].scores[2].points == 1


# ---- golden: one race from a real club scoring spreadsheet, 11.7 nm -----------------------
def hms(s):
    h, m, sec = map(int, s.split(":"))
    return h * 3600 + m * 60 + sec


TWO_HARBORS_R1 = [  # rating, elapsed, expected corrected from the club's spreadsheet
    (75, "02:06:42", "01:52:04"), (102, "02:17:17", "01:57:24"), (-3, "02:03:15", "02:03:50"),
    (39, "02:12:23", "02:04:47"), (184, "03:02:10", "02:26:17"),
    (136, "02:27:27", "02:00:56"), (234, "02:48:02", "02:02:24"),
]


def test_two_harbors_race1_matches_club_spreadsheet():
    for rating, elapsed, expected in TWO_HARBORS_R1:
        assert corrected_seconds(hms(elapsed), rating, D("11.7")) == hms(expected)


def test_orca_time_on_time_matches_club_spreadsheet():
    assert format_hms(time_on_time(hms("02:11:00"), D("0.9467"))) == "2:04:01"   # sheet 02:04:01.062
    assert format_hms(time_on_time(hms("01:54:11"), D("1.2017"))) == "2:17:13"   # sheet 02:17:12.847


# ---- guests -----------------------------------------------------------------
def test_guest_ranked_without_changing_series_scores():
    races = make_races([{1: 10, 2: 30, 9: 20}, {1: 10, 2: 30, 9: 40}])      # boat 9 is the guest
    base = {x.boat_id: x for x in score_series([RaceInput(r.race_id, [x for x in r.results if x.boat_id != 9])
                                                for r in races], [1, 2], SeriesRules())}
    g = score_guest(races, [1, 2], 9, SeriesRules())
    assert [s.points for s in g.scores] == [2, 3]                 # 2nd (between 1 and 2), then 3rd
    assert g.total == 5
    assert base[1].total == 2 and base[2].total == 4              # series scores untouched


def test_guest_penalty_uses_series_entry_count():
    races = make_races([{1: 10, 2: 30}])
    races[0] = RaceInput(1, [fin(1, 10), fin(2, 30), st(9, "DNF")])
    g = score_guest(races, [1, 2], 9, SeriesRules())
    assert g.scores[0].points == 3                                # entries (2) + 1, not 4


# ---- high point scoring ---------------------------------------------------------------------
HIGH = SeriesRules(system="high")


def test_high_point_first_place_scores_the_most():
    r = RaceInput(1, [fin(1, 100), fin(2, 90), fin(3, 120), fin(4, 110)])
    s = score_race(r, [1, 2, 3, 4], HIGH)
    assert [s[b].points for b in (2, 1, 4, 3)] == [4, 3, 2, 1]        # 1st = number of boats


def test_high_point_two_boats_like_the_podium_sheet():
    s = score_race(RaceInput(1, [fin(1, 974), fin(2, 976)]), [1, 2], HIGH)
    assert (s[1].points, s[2].points) == (2, 1)


def test_high_point_ties_share_the_average_and_non_finishers_score_zero():
    r = RaceInput(1, [fin(1, 90), fin(2, 90), fin(3, 100), st(4, "DNF")])    # boat 5 has no row -> DNC
    s = score_race(r, [1, 2, 3, 4, 5], HIGH)
    assert s[1].points == s[2].points == D("4.5")                    # places 1 and 2 -> 5 and 4, averaged
    assert s[3].points == 3 and s[4].points == 0 and s[5].points == 0


def test_high_point_basis_starters():
    r = RaceInput(1, [fin(1, 90), fin(2, 100)])                       # 4 entered, only 2 came to the start
    s = score_race(r, [1, 2, 3, 4], SeriesRules(system="high", basis="starters"))
    assert (s[1].points, s[2].points) == (2, 1)
    s = score_race(r, [1, 2, 3, 4], HIGH)
    assert (s[1].points, s[2].points) == (4, 3)


def test_high_point_series_highest_total_wins_and_discards_drop_the_lowest():
    races = make_races([{1: 10, 2: 20, 3: 30}, {1: 30, 2: 10, 3: 20}, {1: 10, 2: 30, 3: 20}])
    out = score_series(races, [1, 2, 3], SeriesRules(system="high"))
    assert [x.boat_id for x in out][0] == 1 and out[0].total == 3 + 1 + 3
    assert out[0].rank == 1 and out[0].total > out[-1].total
    d = score_series(races, [1, 2, 3], SeriesRules(system="high", discard_thresholds=(3,)))
    best = next(x for x in d if x.boat_id == 1)
    assert best.total == 6 and sum(s.discarded for s in best.scores) == 1   # its worst (1 point) was dropped
    assert [s.points for s in best.scores if s.discarded] == [1]


def test_high_point_late_entrant_gets_zero_for_missed_races():
    races = make_races([{1: 10, 2: 20}, {1: 10, 2: 20, 3: 30}])
    out = {x.boat_id: x for x in score_series(races, [1, 2, 3], SeriesRules(system="high"))}
    assert out[3].scores[0].points == 0


def test_high_point_guest_ranks_without_changing_series_scores():
    races = make_races([{1: 10, 2: 30, 9: 20}])
    g = score_guest(races, [1, 2], 9, HIGH)
    assert g.scores[0].points == 1                                    # finishes 2nd of 3: 2 - 2 + 1 (2 series boats)
    base = score_series([RaceInput(1, [x for x in races[0].results if x.boat_id != 9])], [1, 2], HIGH)
    assert {x.boat_id: x.total for x in base} == {1: 2, 2: 1}
