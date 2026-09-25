from django.core.management.base import BaseCommand

from apps.production.check_docs import write


class Command(BaseCommand):
    help = "Write docs/paper-check-rules.md from the checks in the code."

    def handle(self, **options):
        self.stdout.write(f"Written {write()}")
