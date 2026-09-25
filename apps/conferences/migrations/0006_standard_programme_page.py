"""The standard "programme" page shows the programme (the programme block) instead of placeholder text,
unless the text has been changed in the back office."""

import uuid

from django.db import migrations

PLACEHOLDER = "<p>The programme will be published here.</p>"


def forwards(apps, schema_editor):
    Template = apps.get_model("conferences", "StandardPageTemplate")
    template = Template.objects.filter(slug="programme").first()
    if template is None:
        return
    raw = list(template.body.raw_data) if template.body else []
    if len(raw) == 1 and raw[0].get("type") == "text" and raw[0].get("value") == PLACEHOLDER:
        template.body = [{"type": "programme", "value": {"part": ""}, "id": str(uuid.uuid4())}]
        template.save(update_fields=["body"])


def backwards(apps, schema_editor):
    Template = apps.get_model("conferences", "StandardPageTemplate")
    template = Template.objects.filter(slug="programme").first()
    if template is not None and [b.get("type") for b in template.body.raw_data] == ["programme"]:
        template.body = [{"type": "text", "value": PLACEHOLDER, "id": str(uuid.uuid4())}]
        template.save(update_fields=["body"])


class Migration(migrations.Migration):
    dependencies = [("conferences", "0005_programme_block")]
    operations = [migrations.RunPython(forwards, backwards)]
