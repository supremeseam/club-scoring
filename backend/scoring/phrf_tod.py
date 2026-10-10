"""PHRF time-on-distance corrected time calculation."""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol


def elapsed_seconds(start: datetime, finish: datetime) -> int:
    """Elapsed whole seconds between start and finish (finish may be after midnight)."""
    return int((finish - start).total_seconds())


def _round_half_away(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))   # ROUND_HALF_UP is away from zero


def corrected_seconds(elapsed: int, rating_spnm, distance_nm) -> int:
    """Time-on-distance: corrected = elapsed - allowance.

    The allowance (rating x distance) is rounded to a whole second first, as club scoring
    sheets do. The rating is in seconds per nautical mile and may be negative (adds time).
    """
    allowance = _round_half_away(Decimal(str(rating_spnm)) * Decimal(str(distance_nm)))
    return elapsed - allowance


def time_on_time(elapsed: int, tcf) -> int:
    """Time-on-time (e.g. ORCA): corrected = elapsed x time correction factor, to the second."""
    return _round_half_away(Decimal(elapsed) * Decimal(str(tcf)))


class HandicapSystem(Protocol):
    def corrected(self, elapsed: int, rating: Decimal, distance_nm: Decimal | None) -> int: ...


class TimeOnDistance:
    def corrected(self, elapsed: int, rating: Decimal, distance_nm: Decimal | None) -> int:
        if distance_nm is None:
            raise ValueError("time-on-distance needs a distance")
        return corrected_seconds(elapsed, rating, distance_nm)


class TimeOnTime:
    def corrected(self, elapsed: int, rating: Decimal, distance_nm: Decimal | None = None) -> int:
        return time_on_time(elapsed, rating)


SYSTEMS: dict[str, HandicapSystem] = {"tod": TimeOnDistance(), "tot": TimeOnTime()}


def format_hms(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    h, rem = divmod(abs(int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{sign}{h}:{m:02d}:{s:02d}"
