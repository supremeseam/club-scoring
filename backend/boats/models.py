from django.db import models


class RatingType(models.Model):
    """A kind of PHRF rating (WL, RL, ...). Data, not code, so the club can add more."""
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    fallback_type = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")
    fallback_offset = models.IntegerField(default=0, help_text="sec/nm added to the fallback rating")
    method = models.CharField(max_length=3, default="tod", choices=[
        ("tod", "Time-on-distance (rating in seconds per nautical mile)"),
        ("tot", "Time-on-time (rating is a correction factor, e.g. ORCA TCF)")])

    class Meta:
        ordering = ["display_order", "code"]

    def __str__(self):
        return self.code


class Fleet(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=200, blank=True)
    rating_min = models.IntegerField(null=True, blank=True)
    rating_max = models.IntegerField(null=True, blank=True)
    # Start order: fleets are listed in this order everywhere (results, standings, RC screen, PDFs).
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Boat(models.Model):
    name = models.CharField(max_length=80)
    sail_number = models.CharField(max_length=20)
    design = models.CharField(max_length=60, blank=True)
    skipper = models.CharField(max_length=80, blank=True)
    home_club = models.CharField(max_length=20, blank=True)
    # Member of the club running the app: members can be exempt from some race fees.
    is_member = models.BooleanField(default=False)
    default_fleet = models.ForeignKey(Fleet, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="boats")
    # e.g. ORCA multihulls: this boat is always scored with this rating type, whatever the start uses.
    fixed_rating_type = models.ForeignKey(RatingType, null=True, blank=True, on_delete=models.SET_NULL,
                                          related_name="+")
    # Editor-only: never exposed through public API schemas.
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["sail_number", "name"], name="uniq_boat_sail_name")]

    def __str__(self):
        return f"{self.name} ({self.sail_number})"


class BoatRating(models.Model):
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name="ratings")
    rating_type = models.ForeignKey(RatingType, on_delete=models.PROTECT, related_name="ratings")
    value = models.DecimalField(max_digits=8, decimal_places=4, help_text="s/nm, or TCF for time-on-time")
    effective_from = models.DateField()
    certificate = models.CharField(max_length=40, blank=True)
    expires = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["boat", "rating_type", "-effective_from"]
        constraints = [models.UniqueConstraint(fields=["boat", "rating_type", "effective_from"],
                                               name="uniq_boat_rating")]

    def __str__(self):
        return f"{self.boat} {self.rating_type} {self.value}"
