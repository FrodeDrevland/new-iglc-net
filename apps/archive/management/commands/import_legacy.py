"""Import the old iglc.net database from a .bacpac export, keeping all IDs.

    python manage.py import_legacy inventory/iglc_db-....bacpac --replace

Run it as often as needed; with --replace it empties the archive tables first.
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

from apps.archive import legacy_import
from apps.archive.models import (
    Author, AuthorPerson, Conference, ConferenceTrack, Editor, Link, LinkCategory, Paper, Volume,
)

# In dependency order: parents before children.
MODELS = [
    (Conference, "conferences"), (Volume, "volumes"), (Editor, "editors"), (ConferenceTrack, "tracks"),
    (AuthorPerson, "persons"), (Paper, "papers"), (Author, "authors"),
    (LinkCategory, "link_categories"), (Link, "links"),
]


class Command(BaseCommand):
    help = "Import conferences, papers, authors and links from a .bacpac export of the old site."

    def add_arguments(self, parser):
        parser.add_argument("bacpac")
        parser.add_argument("--replace", action="store_true", help="delete existing archive data first")

    def handle(self, *args, bacpac, replace, **options):
        data = legacy_import.load(bacpac)
        self.stdout.write(legacy_import.summary(data))

        with transaction.atomic():
            if any(model.objects.exists() for model, _ in MODELS):
                if not replace:
                    raise CommandError("The archive already has data. Use --replace to overwrite it.")
                for model, _ in reversed(MODELS):
                    model.objects.all().delete()

            for model, key in MODELS:
                model.objects.bulk_create([model(**row) for row in getattr(data, key)], batch_size=500)

            # New rows must get IDs after the imported ones (PostgreSQL sequences).
            with connection.cursor() as cursor:
                for sql in connection.ops.sequence_reset_sql(no_style(), [model for model, _ in MODELS]):
                    cursor.execute(sql)

            from apps.archive.signals import refresh_all_authors_text

            refresh_all_authors_text()

            problems = [
                f"{model.__name__}: expected {len(getattr(data, key))}, found {model.objects.count()}"
                for model, key in MODELS if model.objects.count() != len(getattr(data, key))
            ]
            if problems:
                raise CommandError("Counts do not match; nothing was saved.\n" + "\n".join(problems))

        self.stdout.write(self.style.SUCCESS("Import finished; all counts match."))
