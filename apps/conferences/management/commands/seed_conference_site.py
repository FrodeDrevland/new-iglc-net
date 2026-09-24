from django.core.management.base import BaseCommand, CommandError

from apps.archive.models import Conference
from apps.conferences.setup import seed, sync_site


class Command(BaseCommand):
    help = ("Create a conference's website (home page and the standard pages, as drafts) at "
            "CONFERENCE_HOST/<year>/, and the group for its organisers. Repeatable.")

    def add_arguments(self, parser):
        parser.add_argument("number", type=int, help="The conference number, e.g. 35")
        parser.add_argument("--current", action="store_true", help="Serve it at the site's main address")
        parser.add_argument("--publish", action="store_true", help="Publish the pages at once (for the preview)")

    def handle(self, number, current, publish, **options):
        conference = Conference.objects.filter(number=number).first()
        if conference is None:
            raise CommandError(f"There is no IGLC {number} in the archive: add the conference first")
        if not conference.start_date:
            raise CommandError(f"IGLC {number} needs its dates first: the year is the site's address")
        sync_site()
        home = seed(conference, current=current, publish=publish)
        self.stdout.write(f"{home.title}: {home.full_url} (group 'IGLC {number} organisers')")
