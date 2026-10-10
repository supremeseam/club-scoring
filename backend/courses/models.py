import math
from decimal import Decimal

from django.db import models

from boats.models import RatingType


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_nm * math.asin(math.sqrt(a))


class Mark(models.Model):
    name = models.CharField(max_length=60, unique=True)
    lat = models.FloatField()
    lon = models.FloatField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=80, unique=True)
    course_type = models.ForeignKey(RatingType, on_delete=models.PROTECT, related_name="courses")
    marks = models.ManyToManyField(Mark, through="CourseLeg")
    distance_override = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    description = models.CharField(max_length=300, blank=True, help_text="Route, e.g. Start (S) => Wes (P) => Finish")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def computed_distance_nm(self) -> Decimal:
        legs = list(self.legs.select_related("mark").order_by("order"))
        total = sum(haversine_nm(a.mark.lat, a.mark.lon, b.mark.lat, b.mark.lon)
                    for a, b in zip(legs, legs[1:]))
        return Decimal(str(round(total, 2)))

    @property
    def distance_nm(self) -> Decimal:
        return self.distance_override if self.distance_override is not None else self.computed_distance_nm


class CourseLeg(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="legs")
    mark = models.ForeignKey(Mark, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["course", "order"]
        constraints = [models.UniqueConstraint(fields=["course", "order"], name="uniq_course_leg_order")]
