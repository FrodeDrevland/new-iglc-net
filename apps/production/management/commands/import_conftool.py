"""Create or update a conference's proceedings volume from ConfTool's accepted papers.

    python manage.py import_conftool 35 accepted.xlsx            # ConfTool export (xlsx or csv)
    python manage.py import_conftool 35 accepted.csv --column track="Track / Topic"
    python manage.py import_conftool 34 --from-archive           # from the archive (for trying out)

Papers are matched on ConfTool ID. Titles, tracks and registered authors are updated; the
status, editor, order and uploaded versions of existing papers are left alone. Tracks are
created as needed. Papers no longer in the list are reported, not deleted.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.archive.models import Conference, ConferenceTrack
from apps.production.conftool import read_accepted
from apps.production.models import ProceedingsVolume, Submission

EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def papers_from_archive(conference):
    papers = []
    for paper in conference.papers.prefetch_related("authors").select_related("track"):
        number = re.sub(r"\D", "", (paper.doi or "").rsplit("/", 1)[-1])
        if not number:
            continue
        papers.append({
            "conftool_id": int(number), "title": paper.title, "track": paper.track.title if paper.track else "",
            "authors": [{"name": f"{a.first_name} {a.last_name}".strip(), "organisation": "",
                         "email": (EMAIL.search(a.title_and_contact or "") or [""])[0]} for a in paper.authors.all()],
        })
    return papers


class Command(BaseCommand):
    help = "Create or update a proceedings volume from ConfTool's export of accepted papers."

    def add_arguments(self, parser):
        parser.add_argument("conference", type=int, help="conference number, e.g. 35")
        parser.add_argument("file", nargs="?", help="ConfTool export (.xlsx or .csv)")
        parser.add_argument("--from-archive", action="store_true", help="take the papers from the archive instead")
        parser.add_argument("--column", action="append", default=[], metavar="FIELD=HEADING",
                            help="name a column explicitly: id, title, track, status, authors, organisations, emails")
        parser.add_argument("--all", action="store_true", help="also papers that are not marked accepted")

    @transaction.atomic
    def handle(self, *args, conference, file=None, from_archive=False, column=(), all=False, **options):
        try:
            conf = Conference.objects.get(number=conference)
        except Conference.DoesNotExist:
            raise CommandError(f"No conference {conference} in the archive; add it under Manage first.")
        if from_archive:
            papers = papers_from_archive(conf)
        elif file:
            explicit = dict(item.split("=", 1) for item in column)
            try:
                papers, columns = read_accepted(file, explicit, accepted_only=not all)
            except ValueError as error:
                raise CommandError(str(error))
            self.stdout.write("Columns used: " + ", ".join(f"{k} = {v!r}" for k, v in columns.items() if v))
        else:
            raise CommandError("Give a ConfTool export file, or --from-archive.")

        volume, created = ProceedingsVolume.objects.get_or_create(conference=conf)
        tracks = {t.title: t for t in conf.tracks.all()}
        new = updated = 0
        for index, data in enumerate(papers):
            track = None
            if data["track"]:
                track = tracks.get(data["track"])
                if track is None:
                    track = tracks[data["track"]] = ConferenceTrack.objects.create(
                        conference=conf, title=data["track"], order=len(tracks) + 1)
            submission, was_created = Submission.objects.update_or_create(
                volume=volume, conftool_id=data["conftool_id"],
                defaults={"title": data["title"][:500], "track": track, "registered_authors": data["authors"]})
            new += was_created
            updated += not was_created
        ids = {p["conftool_id"] for p in papers}
        missing = volume.submissions.exclude(conftool_id__in=ids).exclude(status=Submission.Status.WITHDRAWN)
        self.stdout.write(self.style.SUCCESS(
            f"{volume}{' (new)' if created else ''}: {new} papers added, {updated} updated, {len(tracks)} tracks."))
        if missing.exists():
            self.stdout.write(self.style.WARNING(
                "Not in the list any more (mark them withdrawn if so): "
                + ", ".join(str(s.conftool_id) for s in missing)))
