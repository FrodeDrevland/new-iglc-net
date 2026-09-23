"""Load committee seats from a CSV file (default: apps/governance/data/members.csv).

Columns: committee (slug), role, chair (yes/blank), first_name, last_name, affiliation, country,
url, start_date, end_date (YYYY-MM-DD, may be blank). A seat is matched on committee, name and
start date, so running it again updates rather than duplicates. Names are linked to the
author page of the most published author with that name.
"""

from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from django.db.models import Count

from apps.archive.management.commands.group_authors import fold, name_key
from apps.archive.models import AuthorPerson
from apps.governance.models import Committee, Seat

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "members.csv"


def _short_key(first, last):
    words = fold(last).replace("-", " ").split()
    return name_key(first, words[0]) if words else None


def _date(value):
    return date.fromisoformat(value) if value.strip() else None


class Command(BaseCommand):
    help = "Load committee members from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv", nargs="?", default=str(DEFAULT))

    def handle(self, *args, csv=None, **options):
        import csv as csvlib

        # Match on the full name first, then on the first surname only ("Forcael Durán" is
        # "Forcael" in the proceedings); if several people match, take the most published.
        people, short = {}, {}
        for person in AuthorPerson.objects.annotate(n=Count("authorships")).order_by("-n"):
            people.setdefault(name_key(person.first_name, person.last_name), []).append(person)
            short.setdefault(_short_key(person.first_name, person.last_name), []).append(person)

        created = updated = 0
        with open(csv, encoding="utf-8", newline="") as handle:
            for row in csvlib.DictReader(handle):
                try:
                    committee = Committee.objects.get(slug=row["committee"])
                except Committee.DoesNotExist:
                    raise CommandError(f"No committee with slug {row['committee']!r}")
                if row["role"] not in Seat.Role.values:
                    raise CommandError(f"Unknown role {row['role']!r}")
                matches = (people.get(name_key(row["first_name"], row["last_name"]))
                           or short.get(_short_key(row["first_name"], row["last_name"])) or [])
                _, was_created = Seat.objects.update_or_create(
                    committee=committee, first_name=row["first_name"], last_name=row["last_name"],
                    start_date=_date(row["start_date"]),
                    defaults={
                        "role": row["role"], "is_chair": row["chair"].strip().lower() == "yes",
                        "affiliation": row["affiliation"], "country": row["country"], "url": row["url"],
                        "end_date": _date(row["end_date"]),
                        "person": matches[0] if matches else None,
                    },
                )
                created += was_created
                updated += not was_created
        self.stdout.write(self.style.SUCCESS(f"{created} seats created, {updated} updated."))
