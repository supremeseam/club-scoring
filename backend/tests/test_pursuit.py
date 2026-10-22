from decimal import Decimal

import pytest

from scoring.pursuit import pursuit_offsets


def test_tod_slowest_boat_starts_first_and_gaps_are_rating_difference_times_distance():
    ratings = {"slow": Decimal("180"), "mid": Decimal("150"), "fast": Decimal("96")}
    out = pursuit_offsets("tod", ratings, distance_nm=Decimal("10.5"))
    assert out == {"slow": 0, "mid": 315, "fast": 882}            # 30 x 10.5, 84 x 10.5


def test_tod_offsets_make_a_boat_sailing_to_its_rating_finish_with_the_slowest():
    ratings = {"a": Decimal("201"), "b": Decimal("132"), "c": Decimal("87")}
    dist = Decimal("7.3")
    off = pursuit_offsets("tod", ratings, dist)
    finish = {k: off[k] + ratings[k] * dist + 3600 for k in ratings}      # same base time + own allowance
    # elapsed time to finish for a boat on its rating = base + rating x distance; arriving together means
    # start + elapsed is equal for all (within the whole-second rounding)
    assert max(finish.values()) - min(finish.values()) <= 1


def test_tod_rounds_to_whole_seconds_half_away_from_zero():
    assert pursuit_offsets("tod", {"s": Decimal("100"), "f": Decimal("99.5")}, Decimal("1"))["f"] == 1    # 0.5 -> 1


def test_tod_equal_ratings_start_together_and_negative_ratings_work():
    assert pursuit_offsets("tod", {"a": Decimal("120"), "b": Decimal("120")}, 5) == {"a": 0, "b": 0}
    assert pursuit_offsets("tod", {"a": Decimal("-6"), "b": Decimal("30")}, 2) == {"a": 72, "b": 0}


def test_tot_uses_target_duration_and_tcf_ratio():
    out = pursuit_offsets("tot", {"slow": Decimal("0.8"), "fast": Decimal("1.2")}, target_seconds=3600)
    assert out == {"slow": 0, "fast": 1200}                       # 3600 x (1 - 0.8/1.2)
    assert pursuit_offsets("tot", {"a": Decimal("1.0")}, target_seconds=3600) == {"a": 0}


def test_missing_inputs_are_explained():
    with pytest.raises(ValueError, match="distance"):
        pursuit_offsets("tod", {"a": Decimal("1")}, None)
    with pytest.raises(ValueError, match="target"):
        pursuit_offsets("tot", {"a": Decimal("1")}, target_seconds=None)
    with pytest.raises(ValueError, match="greater than zero"):
        pursuit_offsets("tot", {"a": Decimal("0")}, target_seconds=3600)
    assert pursuit_offsets("tod", {}, 1) == {}
