"""Create the content pages from the old site in Wagtail.

    python manage.py import_legacy_pages            # create pages that do not exist yet
    python manage.py import_legacy_pages --update   # also overwrite existing pages with the old content

The content comes from apps/pages/legacy_content/pages.json (made by tools/convert_legacy_pages.py).
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Page, Site

from apps.pages.models import StandardPage

CONTENT = Path(__file__).resolve().parents[2] / "legacy_content" / "pages.json"


class Command(BaseCommand):
    help = "Create Wagtail pages from the old site's content pages."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="overwrite pages that already exist")
        parser.add_argument("--only", nargs="+", metavar="SLUG",
                            help="only create or update these pages, for example call-for-papers")

    @transaction.atomic
    def handle(self, *args, update, only=None, **options):
        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            raise CommandError("There is no default Wagtail site. Run migrate first.")

        pages_by_slug = {}
        created = updated = skipped = 0
        for entry in json.loads(CONTENT.read_text(encoding="utf-8")):
            parent_id = pages_by_slug.get(entry["parent"]) if entry["parent"] else site.root_page_id
            if parent_id is None:  # its parent was left out (--only)
                continue
            parent = Page.objects.get(pk=parent_id)
            body = json.dumps([{"type": block["type"], "value": block["value"]} for block in entry["body"]])
            existing = parent.get_children().filter(slug=entry["slug"]).first()

            if existing is None and only and entry["slug"] not in only:
                continue  # with --only, pages removed from the site are not brought back
            if existing is None:
                page = StandardPage(title=entry["title"], slug=entry["slug"], body=body)
                parent.add_child(instance=page)
                page.save_revision().publish()
                created += 1
            else:
                page = existing.specific
                if update and isinstance(page, StandardPage) and (not only or entry["slug"] in only):
                    page.title, page.body = entry["title"], body
                    page.save_revision().publish()
                    updated += 1
                else:
                    skipped += 1
            pages_by_slug[entry["slug"]] = page.pk

        self.stdout.write(self.style.SUCCESS(
            f"Pages created: {created}, updated: {updated}, left unchanged: {skipped}."
        ))
