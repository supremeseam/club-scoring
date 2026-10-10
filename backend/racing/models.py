from django.db import models
from simple_history.models import HistoricalRecords

from boats.models import Boat, Fleet, RatingType
from courses.models import Course

STATUS_CODES = ["DNC", "DNS", "OCS", "DNF", "RET", "DSQ", "DNE", "UFD", "BFD", "TLE",
                "RDG", "SCP", "ZFP", "RCD"]


class Series(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        ACTIVE = "active"
        COMPLETE = "complete"

    class Kind(models.TextChoices):
        SERIES = "series"
        SINGLE = "single"       # a standalone race that is not part of a series

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SERIES)
    name = models.CharField(max_length=100)
    season = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    fleets = models.ManyToManyField(Fleet, related_name="series", blank=True)
    discard_thresholds = models.JSONField(default=list, blank=True,
                                          help_text="e.g. [5] = 1 discard after 5 races")
    scoring_system = models.CharField(max_length=4, default="low", choices=[
        ("low", "Low point (1st place = 1 point)"), ("high", "High point (1st place = most points)")])
    scoring_basis = models.CharField(max_length=10, default="entries",
                                     choices=[("entries", "Series entries + 1"),
                                              ("starters", "Boats that came to the start + 1")])
    rcd_method = models.CharField(max_length=10, default="off",
                                  choices=[("off", "Off"), ("all_other", "Average of all other races"),
                                           ("before", "Average of races before")])
    rcd_max_credits = models.PositiveIntegerField(default=2)
    tle_as = models.CharField(max_length=3, default="DNF")
    combined_overall = models.BooleanField(default=False)
    # Optional entry fees. With require_payment on, a boat is scored in a race only if it has paid for
    # the whole series or for that race; everyone else is shown as a (ranked) guest.
    require_payment = models.BooleanField(default=False)
    series_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    race_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    # Optional lower fees for members (blank = members pay the normal fee).
    member_series_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    member_race_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-season", "name"]
        verbose_name_plural = "series"
        constraints = [models.UniqueConstraint(fields=["name", "season"], name="uniq_series_name_season")]

    def __str__(self):
        return f"{self.name} {self.season}"


class SeriesEntry(models.Model):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="entries")
    boat = models.ForeignKey(Boat, on_delete=models.PROTECT, related_name="series_entries")
    fleet = models.ForeignKey(Fleet, on_delete=models.PROTECT)
    # Guests race and appear in race results but are not scored in the series.
    in_series = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["series", "boat"], name="uniq_series_boat")]
        verbose_name_plural = "series entries"


class Race(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        SAILED = "sailed"
        ABANDONED = "abandoned"
        CANCELLED = "cancelled"

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="races")
    number = models.PositiveIntegerField()
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    results_final = models.BooleanField(default=False)
    members_free = models.BooleanField(default=False, help_text="Members do not pay the fee for this race")
    results_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["series", "number"]
        constraints = [models.UniqueConstraint(fields=["series", "number"], name="uniq_race_number")]

    def __str__(self):
        return f"{self.series} R{self.number}"


class Start(models.Model):
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="starts")
    fleet = models.ForeignKey(Fleet, on_delete=models.PROTECT)
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.PROTECT)
    start_time = models.DateTimeField()
    distance_override = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rating_type = models.ForeignKey(RatingType, on_delete=models.PROTECT)
    history = HistoricalRecords()

    class Meta:
        ordering = ["race", "start_time"]
        constraints = [models.UniqueConstraint(fields=["race", "fleet"], name="uniq_start_fleet")]

    @property
    def distance_nm(self):
        if self.distance_override is not None:
            return self.distance_override
        return self.course.distance_nm if self.course else None


class Finish(models.Model):
    class Source(models.TextChoices):
        EXACT = "exact"
        FALLBACK = "fallback"
        MANUAL = "manual"

    start = models.ForeignKey(Start, on_delete=models.CASCADE, related_name="finishes")
    boat = models.ForeignKey(Boat, on_delete=models.PROTECT, related_name="finishes")
    rating_type = models.ForeignKey(RatingType, on_delete=models.PROTECT)
    rating_value = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    rating_source = models.CharField(max_length=10, choices=Source.choices, default=Source.EXACT)
    finish_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=3, blank=True)
    penalty_pct = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    redress_points = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, help_text="Reason for a penalty or score change; shown publicly")
    elapsed_seconds = models.IntegerField(null=True, blank=True)
    corrected_seconds = models.IntegerField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["start", "boat"], name="uniq_finish_boat")]


class Payment(models.Model):
    """Entry fee paid by a boat: for the whole series (race is null) or for one race. Editor-only."""
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="payments")
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name="payments")
    race = models.ForeignKey(Race, null=True, blank=True, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=30, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-paid_on", "id"]
        constraints = [
            models.UniqueConstraint(fields=["series", "boat"], condition=models.Q(race__isnull=True),
                                    name="uniq_series_payment"),
            models.UniqueConstraint(fields=["series", "boat", "race"], condition=models.Q(race__isnull=False),
                                    name="uniq_race_payment"),
        ]


class Protest(models.Model):
    """A protest or request for redress heard for a race. Editor-only; the public sees only 'pending'."""
    class Status(models.TextChoices):
        FILED = "filed"
        HEARD = "heard"
        DECIDED = "decided"
        WITHDRAWN = "withdrawn"

    PENDING = ("filed", "heard")

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="protests")
    filed_on = models.DateField()
    protestor = models.ForeignKey(Boat, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="protests_filed", help_text="Empty = race committee")
    protestees = models.ManyToManyField(Boat, blank=True, related_name="protests_against")
    rules = models.CharField(max_length=200, blank=True, help_text="Rules alleged broken, e.g. 'RRS 10'")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FILED)
    decision = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["race", "filed_on", "id"]
