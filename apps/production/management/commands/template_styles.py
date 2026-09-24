import json

from django.core.management.base import BaseCommand

from apps.production.layout_checks import STYLES_FILE, style_snapshot


class Command(BaseCommand):
    help = ("Take the paragraph styles of a new IGLC paper template (.dotx or .docx) as the reference "
            "for the 'style definitions changed' check (apps/production/template_styles.json).")

    def add_arguments(self, parser):
        parser.add_argument("template")

    def handle(self, template, **options):
        snapshot = style_snapshot(template)
        STYLES_FILE.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
        self.stdout.write(f"{len(snapshot['styles'])} styles written to {STYLES_FILE}")
