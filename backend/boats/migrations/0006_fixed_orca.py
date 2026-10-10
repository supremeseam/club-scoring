from django.db import migrations


def fix(apps, schema_editor):
    Boat = apps.get_model("boats", "Boat")
    BoatRating = apps.get_model("boats", "BoatRating")
    for br in BoatRating.objects.filter(rating_type__method="tot").select_related("rating_type"):
        Boat.objects.filter(pk=br.boat_id, fixed_rating_type__isnull=True).update(
            fixed_rating_type=br.rating_type)


class Migration(migrations.Migration):
    dependencies = [("boats", "0005_boat_fixed_rating_type")]
    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
