"""Give papers their tracks from a CSV (as written by read_tracks, after checking it).

Columns used: paper_id and track. Tracks are created per conference as needed; an empty track
leaves the paper as it is. Existing tracks with the same title are reused.

    python manage.py import_tracks tracks-34.csv
"""

import csv

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.archive.models import ConferenceTrack, Paper


class Command(BaseCommand):
    help = "Assign tracks to papers from a CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv")

    @transaction.atomic
    def handle(self, *args, csv=None, **options):
        import csv as csvlib

        assigned = created = 0
        with open(csv, encoding="utf-8-sig", newline="") as handle:
            for row in csvlib.DictReader(handle):
                title = (row.get("track") or "").strip()
                if not title:
                    continue
                paper = Paper.objects.select_related("conference").get(pk=int(row["paper_id"]))
                track, was_created = ConferenceTrack.objects.get_or_create(conference=paper.conference, title=title)
                created += was_created
                if paper.track_id != track.pk:
                    Paper.objects.filter(pk=paper.pk).update(track=track)
                    assigned += 1
        self.stdout.write(self.style.SUCCESS(f"{assigned} papers given a track; {created} tracks created."))
