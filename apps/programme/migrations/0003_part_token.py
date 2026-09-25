import uuid

from django.db import migrations, models


def fill(apps, schema_editor):
    Part = apps.get_model("programme", "Part")
    for part in Part.objects.all():
        part.token = uuid.uuid4()
        part.save(update_fields=["token"])


class Migration(migrations.Migration):
    dependencies = [("programme", "0002_registration_backing")]
    operations = [
        migrations.AddField("part", "token", models.UUIDField(null=True, editable=False)),
        migrations.RunPython(fill, migrations.RunPython.noop),
        migrations.AlterField("part", "token", models.UUIDField(
            default=uuid.uuid4, unique=True, editable=False, help_text="The private link of a part that is not public.")),
    ]
