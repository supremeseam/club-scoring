from django.contrib import admin

from .models import Boat, BoatRating, Fleet, RatingType

admin.site.register([Boat, BoatRating, Fleet, RatingType])
