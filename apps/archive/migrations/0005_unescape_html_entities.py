"""Some titles, abstracts, keywords and affiliations were stored with HTML entities
("Takt &amp; LPS"), which the site then showed literally. Store the plain characters."""

import html
import re

from django.db import migrations

ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+\d*);")
FIELDS = {"Paper": ("title", "abstract", "keywords"), "Author": ("first_name", "last_name", "title_and_contact")}


def unescape(apps, schema_editor):
    for model_name, fields in FIELDS.items():
        model = apps.get_model("archive", model_name)
        for obj in model.objects.all().only("pk", *fields):
            changed = {f: html.unescape(getattr(obj, f)) for f in fields
                       if getattr(obj, f) and ENTITY.search(getattr(obj, f))}
            if changed:
                model.objects.filter(pk=obj.pk).update(**changed)


class Migration(migrations.Migration):
    dependencies = [("archive", "0004_fill_authors_text")]
    operations = [migrations.RunPython(unescape, migrations.RunPython.noop)]
