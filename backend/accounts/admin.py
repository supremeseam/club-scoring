from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.contrib.auth.models import User

from .audit import log_event
from .models import AccountProfile


def force_change(user, reason: str) -> None:
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.must_change_password = True
    profile.save(update_fields=["must_change_password"])
    log_event(reason, username=user.get_username())


class FlaggingAdminPasswordChangeForm(AdminPasswordChangeForm):
    """An administrator setting someone's password is giving them a TEMPORARY one: they must replace it."""

    def save(self, commit=True):
        user = super().save(commit)
        force_change(user, "password_reset_by_admin")
        return user


class ProfileInline(admin.StackedInline):
    model = AccountProfile
    can_delete = False
    verbose_name_plural = "Password status"


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    change_password_form = FlaggingAdminPasswordChangeForm

    def get_inlines(self, request, obj):
        return [ProfileInline] if obj is not None else []       # the profile is created with the user

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:                                           # new account: temporary password
            force_change(obj, "account_created_by_admin")

