"""Tracks for the papers of IGLC 23-27 and 29-34, read from the running heads, section pages
and tables of contents of the full proceedings (apps/archive/data/tracks.csv). Papers that
already have a track keep it. IGLC 27 (2019), 28 (2020), 33 (2025) and earlier conferences are
not covered: their books do not name tracks, or are not at hand (see read_tracks)."""

import csv
from pathlib import Path

from django.db import migrations

CSV = Path(__file__).resolve().parent.parent / "data" / "tracks.csv"


def load(apps, schema_editor):
    Paper = apps.get_model("archive", "Paper")
    Track = apps.get_model("archive", "ConferenceTrack")
    with open(CSV, encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["track"].strip()]
    papers = {p.pk: p for p in Paper.objects.filter(pk__in=[int(r["paper_id"]) for r in rows])}
    first_page = {}
    for row in rows:
        paper = papers.get(int(row["paper_id"]))
        if paper is None or paper.track_id:
            continue
        track, _ = Track.objects.get_or_create(conference_id=paper.conference_id, title=row["track"].strip())
        Paper.objects.filter(pk=paper.pk).update(track=track)
        page = paper.first_page or 0
        first_page[track.pk] = min(first_page.get(track.pk, page), page)
    # tracks in the order they appear in the book
    by_conference = {}
    for track in Track.objects.filter(pk__in=first_page):
        by_conference.setdefault(track.conference_id, []).append(track)
    for tracks in by_conference.values():
        if any(t.order for t in tracks):
            continue
        for order, track in enumerate(sorted(tracks, key=lambda t: (first_page[t.pk], t.pk)), 1):
            Track.objects.filter(pk=track.pk).update(order=order)


class Migration(migrations.Migration):
    dependencies = [("archive", "0007_track_order")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
