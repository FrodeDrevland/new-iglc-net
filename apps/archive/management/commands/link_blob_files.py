"""Link full proceedings PDFs and ZIPs of papers in blob storage to their conferences.

The old site looked these up in Azure Blob Storage on every page view. Here they are stored on
each conference instead. Make a list of the files with the Azure CLI (see docs/content-files.md),
one URL per line, then:

    python manage.py link_blob_files inventory/blob-files.txt

Files recognised (by name, as the old site did):
    papers-zipped/IGLC<number>_Papers.zip         -> ZIP of all papers
    proceedings/Proceedings-IGLC<number>*.pdf      -> full proceedings (several files become volumes)
"""

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.archive.models import Conference, ProceedingsFile


class Command(BaseCommand):
    help = "Link proceedings PDFs and paper ZIPs in blob storage to conferences."

    def add_arguments(self, parser):
        parser.add_argument("listing", help="text file with one blob URL per line")

    @transaction.atomic
    def handle(self, *args, listing, **options):
        zips, pdfs = {}, defaultdict(list)
        for line in Path(listing).read_text(encoding="utf-8-sig").splitlines():
            url = line.strip()
            if not url:
                continue
            name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            if match := re.fullmatch(r"IGLC(\d+)_Papers\.zip", name, re.IGNORECASE):
                zips[int(match.group(1))] = url
            elif match := re.match(r"Proceedings-IGLC(\d+)\D.*\.pdf$|Proceedings-IGLC(\d+)\.pdf$", name, re.IGNORECASE):
                pdfs[int(match.group(1) or match.group(2))].append(url)

        conferences = {c.number: c for c in Conference.objects.all()}
        for number, url in sorted(zips.items()):
            if number in conferences:
                Conference.objects.filter(pk=conferences[number].pk).update(papers_zip_url=url)
        for number, urls in sorted(pdfs.items()):
            if number not in conferences:
                continue
            conference = conferences[number]
            conference.proceedings_files.all().delete()
            urls.sort()
            for order, url in enumerate(urls, 1):
                label = "Full proceedings" if len(urls) == 1 else f"Volume {order}"
                ProceedingsFile.objects.create(conference=conference, label=label, url=url, order=order)

        unknown = sorted((set(zips) | set(pdfs)) - set(conferences))
        self.stdout.write(self.style.SUCCESS(
            f"ZIPs linked for {len(set(zips) & set(conferences))} conferences, "
            f"proceedings PDFs for {len(set(pdfs) & set(conferences))} conferences."
        ))
        if unknown:
            self.stdout.write(f"No conference with number: {', '.join(map(str, unknown))}")
