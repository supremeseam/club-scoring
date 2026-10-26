from datetime import date, datetime

from ninja import Schema
from pydantic import Field


# ---- public (read-only) ------------------------------------------------------
class PublicBoat(Schema):
    """Only boat, sail number, design and skipper are ever public."""
    id: int
    name: str
    sail_number: str
    design: str
    skipper: str
    home_club: str = ""


class SeriesSummary(Schema):
    id: int
    name: str
    season: int
    status: str
    description: str
    race_count: int
    kind: str = "series"
    race_id: int | None = None   # the one race, for single races


class RaceSummary(Schema):
    id: int
    number: int
    date: date
    status: str
    final: bool


class SeriesDetail(SeriesSummary):
    combined_overall: bool
    discard_thresholds: list[int]
    races: list[RaceSummary]


class RaceRef(Schema):
    id: int
    number: int
    date: date


class ScoreCell(Schema):
    race_id: int
    points: float
    code: str | None
    discarded: bool
    average: bool


class StandingRow(Schema):
    rank: int          # 0 for guests (shown, not ranked)
    guest: bool = False
    boat: PublicBoat
    total: float
    scores: list[ScoreCell]


class FleetStandings(Schema):
    fleet_id: int | None
    fleet_name: str
    races: list[RaceRef]
    standings: list[StandingRow]


class SeriesStandings(Schema):
    series: SeriesSummary
    fleets: list[FleetStandings]
    combined: FleetStandings | None
    warnings: list[str]


class ResultRow(Schema):
    boat: PublicBoat
    rating_type: str
    rating: float | None
    rating_source: str | None
    finish_time: datetime | None
    elapsed: str | None
    corrected: str | None
    status: str | None
    points: float | None
    code: str | None
    place: int | None
    note: str = ""


class FleetResults(Schema):
    fleet_id: int
    fleet_name: str
    course: str | None
    distance_nm: float | None
    rating_type: str
    start_time: datetime
    rows: list[ResultRow]


class RaceResults(Schema):
    race_id: int
    number: int
    date: date
    status: str
    final: bool
    updated_at: datetime | None
    series_id: int
    series_name: str
    protests_pending: int = 0
    is_pursuit: bool = False
    fleets: list[FleetResults]


class BoatHistoryRow(Schema):
    series_id: int
    series_name: str
    race_id: int
    race_number: int
    date: date
    fleet: str
    rating_type: str
    rating: float | None
    elapsed: str | None
    corrected: str | None
    status: str | None
    points: float | None
    note: str = ""


class BoatHistory(Schema):
    boat: PublicBoat
    rows: list[BoatHistoryRow]


# ---- auth ---------------------------------------------------------------------
class LoginIn(Schema):
    # Length limits stop huge inputs from burning CPU in the password hasher; 256 is far above NIST's 64.
    username: str = Field(max_length=150)
    password: str = Field(max_length=256)
    otp: str = Field("", max_length=16)


class ChangePasswordIn(Schema):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class Me(Schema):
    username: str
    is_admin: bool
    must_change_password: bool = False
    role: str = "rc"
    manages_boats: bool = False
    unseen_requests: int = 0


# ---- editor ---------------------------------------------------------------------
class RatingTypeIO(Schema):
    id: int | None = None
    code: str
    name: str
    description: str = ""
    display_order: int = 0
    fallback_type_id: int | None = None
    fallback_offset: int = 0
    method: str = "tod"


class FleetIO(Schema):
    id: int | None = None
    name: str
    description: str = ""
    rating_min: int | None = None
    rating_max: int | None = None
    display_order: int = 0


class RatingOut(Schema):
    id: int
    rating_type_id: int
    rating_type: str
    value: float
    effective_from: date
    certificate: str
    expires: date | None
    notes: str


class RatingIn(Schema):
    rating_type_id: int
    value: float
    effective_from: date
    certificate: str = ""
    expires: date | None = None
    notes: str = ""


class BoatIn(Schema):
    name: str
    sail_number: str
    design: str = ""
    skipper: str = ""
    home_club: str = ""
    is_member: bool = False
    default_fleet_id: int | None = None
    fixed_rating_type_id: int | None = None   # e.g. ORCA boats always use ORCA
    contact_email: str = ""
    contact_phone: str = ""
    active: bool = True


class BoatOut(BoatIn):
    id: int
    ratings: list[RatingOut] = []


class MarkIO(Schema):
    id: int | None = None
    name: str
    lat: float
    lon: float


class CourseIn(Schema):
    name: str
    course_type_id: int
    mark_ids: list[int]
    distance_override: float | None = None
    description: str = ""


class CourseOut(Schema):
    id: int
    name: str
    course_type_id: int
    course_type: str
    mark_ids: list[int]
    computed_distance_nm: float
    distance_nm: float
    distance_override: float | None
    description: str = ""


class SeriesIn(Schema):
    race_format: str = "fleet"
    name: str
    season: int
    description: str = ""
    fleet_ids: list[int] = []
    discard_thresholds: list[int] = []
    scoring_basis: str = "entries"
    scoring_system: str = "low"
    rcd_method: str = "off"
    rcd_max_credits: int = 2
    tle_as: str = "DNF"
    combined_overall: bool = False
    status: str = "draft"
    require_payment: bool = False
    series_fee: float = 0
    race_fee: float = 0
    member_series_fee: float | None = None
    member_race_fee: float | None = None


class ScheduleIn(Schema):
    first_date: date
    last_date: date
    interval_days: int = 7


class SeriesCreate(SeriesIn):
    schedule: ScheduleIn | None = None


class SeriesEditor(SeriesIn):
    id: int
    kind: str = "series"


class SingleRaceIn(Schema):
    race_format: str = "fleet"
    pursuit_target_minutes: int | None = None
    name: str
    date: date
    fleet_ids: list[int]
    description: str = ""
    require_payment: bool = False
    race_fee: float = 0


class EntryIO(Schema):
    boat_id: int
    fleet_id: int
    in_series: bool = True


class CloneIn(Schema):
    season: int
    name: str | None = None
    shift_days: int = 364


class RaceIn(Schema):
    race_format: str = ""
    pursuit_target_minutes: int | None = None
    number: int | None = None
    date: date
    status: str = "scheduled"
    time_limit_minutes: int | None = None
    results_final: bool = False
    members_free: bool = False


class RaceEditor(RaceIn):
    is_pursuit: bool = False
    id: int
    series_id: int
    number: int


class StartIn(Schema):
    fleet_id: int
    course_id: int | None = None
    start_time: datetime
    distance_override: float | None = None
    rating_type_id: int | None = None


class StartOut(Schema):
    id: int
    race_id: int
    fleet_id: int
    course_id: int | None
    start_time: datetime
    distance_override: float | None
    distance_nm: float | None
    rating_type_id: int
    rating_changes: int = 0


class FinishIn(Schema):
    boat_id: int
    finish_time: datetime | None = None
    status: str = ""
    penalty_pct: float = 0
    redress_points: float | None = None
    manual_rating: float | None = None
    note: str = ""


class FinishOut(Schema):
    id: int
    boat_id: int
    finish_time: datetime | None
    status: str
    penalty_pct: float
    redress_points: float | None
    rating_type: str
    rating_value: float | None
    rating_source: str
    elapsed_seconds: int | None
    corrected_seconds: int | None
    note: str = ""


class RatingPreviewRow(Schema):
    boat_id: int
    boat: str
    rating: float | None
    source: str | None
    expired: bool
    missing: bool


class ReresolveOut(Schema):
    changes: list[dict]


class ImportOut(Schema):
    boats_created: int
    boats_updated: int
    ratings_saved: int
    errors: list[str]


class PaymentIn(Schema):
    boat_id: int
    race_id: int | None = None       # None = the whole series
    amount: float | None = None      # default: the series fee, or the race fee for a race payment
    paid_on: date | None = None      # default: today
    method: str = ""
    note: str = ""


class PaymentOut(Schema):
    id: int
    boat_id: int
    boat: str
    race_id: int | None
    race_number: int | None
    amount: float
    paid_on: date
    method: str
    note: str


class ProtestIn(Schema):
    filed_on: date | None = None
    protestor_id: int | None = None          # None = race committee
    protestee_ids: list[int] = []
    rules: str = ""
    status: str = "filed"
    decision: str = ""


class ProtestOut(Schema):
    id: int
    race_id: int
    filed_on: date
    protestor_id: int | None
    protestor: str
    protestee_ids: list[int]
    protestees: list[str]
    rules: str
    status: str
    decision: str


class MoveBoatIn(Schema):
    boat_id: int
    to_fleet_id: int
    scope: str = "race"            # "race" = this race only; "series" = change the boat's fleet for the series
    move_this_race: bool = True    # with scope "series": also move this race's result


class MoveBoatOut(Schema):
    moved_result: bool
    warnings: list[str] = []


class RemoveBoatOut(Schema):
    cleared_result: bool
    removed_entry: bool


class LineupRow(Schema):
    fleet_id: int
    boat_ids: list[int]


class PursuitRow(Schema):
    order: int
    boat_id: int
    boat: str
    sail_number: str
    rating: float
    offset_seconds: int
    offset: str
    start_time: datetime


class PursuitSkipped(Schema):
    boat_id: int
    boat: str
    reason: str


class PursuitSchedule(Schema):
    is_pursuit: bool
    method: str
    distance_nm: float | None
    target_minutes: int | None
    first_gun: datetime
    rows: list[PursuitRow]
    skipped: list[PursuitSkipped]
    error: str | None = None
