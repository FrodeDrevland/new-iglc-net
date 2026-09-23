"""Link the full proceedings PDFs listed on the "Full proceedings" page to their conference pages.

The old site's Proceedings page has a table with one row per conference ("IGLC 27") and links to
its volumes. This reads that table from the Wagtail page (slug "proceedings") and stores the links
on each conference, so every conference page shows its full proceedings.

    python manage.py link_full_proceedings

Links to /Content/... are stored as their blob storage address (LEGACY_CONTENT_URL).
Existing proceedings links on those conferences are replaced.
"""

import re
from html import unescape
from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.archive.models import Conference, ProceedingsFile

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


def _absolute(href: str) -> str:
    href = unescape(href).strip()
    if href.lower().startswith("/content/"):
        return f"{settings.LEGACY_CONTENT_URL}/{quote(href[len('/content/'):])}"
    return href


def _label(text: str, count: int) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(text))).strip()
    if count == 1 and text in ("Volume I", "Volume I and II", ""):
        return "Full proceedings" if text != "Volume I and II" else "Volumes I and II"
    return text or "Full proceedings"


class Command(BaseCommand):
    help = "Link the PDFs on the Full proceedings page to their conferences."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.pages.models import StandardPage

        page = StandardPage.objects.filter(slug="proceedings").first()
        if page is None:
            raise CommandError('No page with the slug "proceedings". Run import_legacy_pages first.')

        html = "".join(str(block.value) for block in page.body)
        conferences = {c.number: c for c in Conference.objects.all()}
        linked = []
        for row in re.findall(r"<tr.*?</tr>", html, re.S | re.I):
            number = re.search(r"IGLC\s*(\d+)", re.sub(r"<[^>]+>", " ", row))
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', row, re.S | re.I)
            if not number or not links or int(number.group(1)) not in conferences:
                continue
            conference = conferences[int(number.group(1))]
            conference.proceedings_files.all().delete()
            for order, (href, text) in enumerate(links, 1):
                ProceedingsFile.objects.create(
                    conference=conference, label=_label(text, len(links)), url=_absolute(href), order=order,
                )
            linked.append(conference.number)

        self.stdout.write(self.style.SUCCESS(
            f"Full proceedings linked for {len(linked)} conferences: "
            + ", ".join(f"IGLC {n}" for n in sorted(linked))
        ))
