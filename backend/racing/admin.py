from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Finish, Payment, Protest, Race, Series, SeriesEntry, Start

admin.site.register([Series, SeriesEntry, Race, Payment])
admin.site.register([Start, Finish, Protest], SimpleHistoryAdmin)
