"""Make a production for a conference already published in the archive, for its full proceedings.

    python manage.py adopt_published 34
"""

from django.core.management.base import BaseCommand, CommandError

from apps.archive.models import Conference
from apps.production.adopt import AdoptError, adopt_published


class Command(BaseCommand):
    help = "Create a proceedings production from a conference already published in the archive."

    def add_arguments(self, parser):
        parser.add_argument("conference", type=int)

    def handle(self, *args, conference, **options):
        try:
            production, report = adopt_published(Conference.objects.get(number=conference))
        except Conference.DoesNotExist:
            raise CommandError(f"No conference {conference} in the archive")
        except AdoptError as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(
            f"{production}: {report['added']} papers added, {report['updated']} updated."))
        if report["without_number"]:
            self.stdout.write(self.style.WARNING("No paper number in the DOI: " + "; ".join(report["without_number"])))
        if report["without_pdf"]:
            self.stdout.write(self.style.WARNING(f"{report['without_pdf']} paper(s) have no PDF."))
