"""Rating resolution: which rating does a boat use for a given rating type on a given date?"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from boats.models import Boat, BoatRating, RatingType


def _latest(boat: Boat, rating_type: RatingType, on_date: date) -> BoatRating | None:
    return (BoatRating.objects
            .filter(boat=boat, rating_type=rating_type, effective_from__lte=on_date)
            .order_by("-effective_from").first())


def resolve_rating(boat: Boat, rating_type: RatingType, on_date: date
                   ) -> tuple[Decimal, str] | None:
    """Return (value, source) or None if the boat has no usable rating.

    1. Latest rating of that type effective on or before the date  -> "exact"
    2. The type's fallback (type X, plus an offset)                 -> "fallback"
    3. None: the RC must enter a manual rating.
    """
    exact = _latest(boat, rating_type, on_date)
    if exact:
        return exact.value, "exact"
    seen = {rating_type.pk}
    current = rating_type
    offset = Decimal(0)
    while current.fallback_type_id and current.fallback_type_id not in seen:
        offset += current.fallback_offset
        seen.add(current.fallback_type_id)
        current = current.fallback_type
        hit = _latest(boat, current, on_date)
        if hit:
            return hit.value + offset, "fallback"
    return None


def certificate_expired(boat: Boat, rating_type: RatingType, on_date: date) -> bool:
    r = _latest(boat, rating_type, on_date)
    return bool(r and r.expires and r.expires < on_date)
