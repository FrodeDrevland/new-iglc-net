"""Create a small set of clearly fictional conferences and papers for local development."""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.archive.models import Author, Conference, Editor, Paper, Volume

DEMO_CONFERENCES = [
    (901, date(2031, 7, 14), "Demo City", "Norway"),
    (902, date(2032, 7, 12), "Sample Town", "Chile"),
]


class Command(BaseCommand):
    help = "Load fictional demo data (conference numbers 901 and 902). Safe to run more than once."

    @transaction.atomic
    def handle(self, *args, **options):
        for number, start, city, country in DEMO_CONFERENCES:
            conference, _ = Conference.objects.update_or_create(
                number=number,
                defaults={
                    "start_date": start, "city": city, "country": country, "is_published": True,
                    "proceedings_title": f"Proceedings of the {number}th Annual Conference of the IGLC (demo)",
                    "publisher": "IGLC", "issn": "0000-0000",
                },
            )
            conference.editors.all().delete()
            Editor.objects.create(conference=conference, first_name="Erin", last_name="Example", order=1)
            volume, _ = Volume.objects.get_or_create(
                conference=conference, number=1, defaults={"first_page": 1, "last_page": 120}
            )
            conference.papers.all().delete()
            for i in range(1, 6):
                paper = Paper.objects.create(
                    conference=conference, volume=volume,
                    title=f"Demo paper {i}: flow and variability in {city}",
                    abstract="This is fictional demo content for testing the new site.",
                    keywords="takt planning, last planner system, demo",
                    first_page=(i - 1) * 10 + 1, last_page=i * 10,
                    doi=f"10.24928/{start.year}/demo{i:04d}",
                    status=Paper.Status.APPROVED,
                )
                for order, (first, last) in enumerate([("Ann", "Author"), ("Bo", "Builder")][: 1 + i % 2], 1):
                    Author.objects.create(paper=paper, first_name=first, last_name=last, order=order,
                                          title_and_contact="Demo University, Norway")
        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
