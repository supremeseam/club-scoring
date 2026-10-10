from django.db import migrations


def create_profiles(apps, schema_editor):
    """Existing accounts keep working: they get a profile with must_change_password=False."""
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("accounts", "AccountProfile")
    Profile.objects.bulk_create([Profile(user_id=u.pk) for u in User.objects.filter(auth_profile__isnull=True)])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(create_profiles, migrations.RunPython.noop)]
