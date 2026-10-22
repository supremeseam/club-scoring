"""Pursuit-race start offsets (pure Python, no Django).

In a pursuit race each boat starts at a time worked out from its handicap, so that if every boat sails exactly
to its rating they all reach the finish together. The first boat across the finish line wins; no corrected time
is calculated afterwards. The slowest boat starts first, at the first gun, and every other boat waits.

  Time-on-distance (PHRF, rating = seconds per nautical mile):
      offset = (slowest rating - boat rating) x distance            (rounded to a whole second)
  Time-on-time (ORCA, rating = TCF, higher = faster):
      offset = target duration of the slowest boat x (1 - slowest TCF / boat TCF)
"""
from decimal import Decimal

from .phrf_tod import _round_half_away


def pursuit_offsets(method: str, ratings: dict, distance_nm=None, target_seconds=None) -> dict:
    """Seconds after the first gun at which each boat starts. `ratings` maps boat id -> rating."""
    if not ratings:
        return {}
    values = {k: Decimal(str(v)) for k, v in ratings.items()}
    if method == "tod":
        if distance_nm is None or Decimal(str(distance_nm)) <= 0:
            raise ValueError("A distance is needed to work out time-on-distance start times")
        slowest, dist = max(values.values()), Decimal(str(distance_nm))
        return {k: _round_half_away((slowest - v) * dist) for k, v in values.items()}
    if method == "tot":
        if not target_seconds or target_seconds <= 0:
            raise ValueError("A target race length is needed to work out time-on-time start times")
        if any(v <= 0 for v in values.values()):
            raise ValueError("Every time-on-time rating (TCF) must be greater than zero")
        slowest = min(values.values())
        return {k: _round_half_away(Decimal(target_seconds) * (1 - slowest / v)) for k, v in values.items()}
    raise ValueError(f"Unknown rating method {method!r}")
