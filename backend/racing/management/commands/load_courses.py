"""Load marks and numbered courses from a JSON file (e.g. a club's course chart).

{
  "marks":   [{"name": "CM1", "lat": 34.154, "lon": -119.230}],
  "courses": [{"name": "1", "type": "RL", "distance": 1.0, "route": ["Start", "CM1", "Finish"],
               "description": "Start (S) => CM1 (P) => Finish"}]
}
`route` entries without a mark of that name are kept only in the description. `distance` is the
chart distance in nm and is used for scoring (it overrides distance computed from mark positions).
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from boats.models import RatingType
from courses.models import Course, CourseLeg, Mark


class Command(BaseCommand):
    help = "Load marks and courses from a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("path")

    @transaction.atomic
    def handle(self, *args, **o):
        with open(o["path"], encoding="utf-8") as fh:
            data = json.load(fh)
        marks = {}
        for m in data.get("marks", []):
            marks[m["name"]], _ = Mark.objects.update_or_create(
                name=m["name"], defaults={"lat": m["lat"], "lon": m["lon"]})
        marks.update({m.name: m for m in Mark.objects.all()})
        n = 0
        for c in data.get("courses", []):
            try:
                rt = RatingType.objects.get(code=c["type"])
            except RatingType.DoesNotExist:
                raise CommandError(f"Unknown rating type {c['type']!r} for course {c['name']}")
            course, _ = Course.objects.update_or_create(name=str(c["name"]), defaults={
                "course_type": rt, "description": c.get("description", ""),
                "distance_override": Decimal(str(c["distance"])) if c.get("distance") is not None else None})
            course.legs.all().delete()
            legs = [marks[m] for m in c.get("route", []) if m in marks]
            CourseLeg.objects.bulk_create([CourseLeg(course=course, mark=m, order=i) for i, m in enumerate(legs)])
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(marks)} marks and {n} courses."))
