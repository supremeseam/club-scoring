from django.contrib import admin

from .models import Course, CourseLeg, Mark


class LegInline(admin.TabularInline):
    model = CourseLeg


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = [LegInline]


admin.site.register(Mark)
