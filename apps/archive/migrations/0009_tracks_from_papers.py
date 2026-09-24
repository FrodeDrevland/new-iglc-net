"""Tracks for IGLC 20-22, 27, 28 and 33, read on the server from the running heads of the papers'
PDFs (read_tracks) and cleaned (apps/archive/data/tracks-server.csv): spelling variants and typos
merged; IGLC 28's sessions ("People, Culture, and Change: Lean Leadership ...") reduced to their
track; a paper listed under two sessions (IGLC 20) given the first; a paper without a readable
track between two papers of the same track given that track. IGLC 27 (2019) had sessions, not
tracks: its sessions are used. Papers that already have a track keep it."""

import importlib
from pathlib import Path

from django.db import migrations

CSV = Path(__file__).resolve().parent.parent / "data" / "tracks-server.csv"


def load(apps, schema_editor):
    earlier = importlib.import_module("apps.archive.migrations.0008_tracks_from_proceedings")
    earlier.load(apps, schema_editor, CSV)


class Migration(migrations.Migration):
    dependencies = [("archive", "0008_tracks_from_proceedings")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
