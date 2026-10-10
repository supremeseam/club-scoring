from django.db import migrations


def seed(apps, schema_editor):
    RatingType = apps.get_model("boats", "RatingType")
    wl, _ = RatingType.objects.get_or_create(
        code="WL", defaults={"name": "Windward/Leeward", "display_order": 1,
                             "description": "Windward/leeward (buoy) racing"})
    RatingType.objects.get_or_create(
        code="RL", defaults={"name": "Random Leg", "display_order": 2, "fallback_type": wl,
                             "fallback_offset": -6,
                             "description": "Distance / random-leg racing"})


class Migration(migrations.Migration):
    dependencies = [("boats", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
