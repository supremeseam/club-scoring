import re

from django.db import migrations

# Sensible defaults for the usual class names; anything else keeps order 0 and sorts by name.
ORDER = {"SPIN A": 1, "SPIN B": 2, "NON-SPIN": 3, "NON SPIN": 3, "NONSPIN": 3, "ORCA": 4}


def key(name: str) -> str:
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", name.strip())).upper()


def order(apps, schema_editor):
    Fleet = apps.get_model("boats", "Fleet")
    for f in Fleet.objects.all():
        n = ORDER.get(key(f.name))
        if n and f.display_order == 0:
            f.display_order = n
            f.save(update_fields=["display_order"])


class Migration(migrations.Migration):
    dependencies = [("boats", "0008_alter_fleet_options_fleet_display_order")]
    operations = [migrations.RunPython(order, migrations.RunPython.noop)]
