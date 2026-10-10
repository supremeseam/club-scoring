from django.db import migrations


def seed(apps, schema_editor):
    RatingType = apps.get_model("boats", "RatingType")
    RatingType.objects.get_or_create(
        code="ORCA", defaults={"name": "ORCA (time-on-time)", "display_order": 3, "method": "tot",
                               "description": "Time correction factor (TCF) multiplied by elapsed time"})


class Migration(migrations.Migration):
    dependencies = [("boats", "0003_boat_home_club_ratingtype_method_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
