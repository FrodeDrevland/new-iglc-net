"""The For Authors pages rewritten for the 2027 process (check your paper, the revised template).

Rewrites those pages once with the text in legacy_content/pages.json, the same as
    python manage.py import_legacy_pages --update --only <the slugs below>
Hand edits made to these pages before this migration are replaced. On a new, empty database
(tests, a fresh install) nothing happens: the pages come with import_legacy_pages.
"""

from django.core.management import call_command
from django.db import migrations

SLUGS = [
    "for-authors", "paper-submission-and-review-process", "content-requirements",
    "formatting-requirements", "paper-structure", "templates", "publication",
    "publication-schedule", "call-for-papers",
]


def rewrite(apps, schema_editor):
    Page = apps.get_model("wagtailcore", "Page")
    if not Page.objects.filter(slug="for-authors").exists():
        return
    call_command("import_legacy_pages", update=True, only=SLUGS, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0002_streamfield_body"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [migrations.RunPython(rewrite, migrations.RunPython.noop)]
