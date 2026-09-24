"""Suggest each paper's track from the running footer of its PDF.

In recent proceedings the footer of odd pages names the track ("People, Culture and Change").
This reads the footers of each paper's PDF, drops page numbers and the conference line, and
writes a CSV with the most likely track per paper and how many papers of the conference share
it. Check and correct the CSV, then load it with `import_tracks`.

    python manage.py read_tracks --conference 34 --out tracks-34.csv
    python manage.py read_tracks --out tracks.csv                  # all conferences
    python manage.py read_tracks --conference 34 --folder pdfs/    # local PDFs named by DOI number (0100.pdf or 100.pdf)
"""

import csv
import io
import re
import urllib.request
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand
from pypdf import PdfReader

from apps.archive.models import Paper

FOOTER_ZONE = 65  # points from the bottom edge
NOT_A_TRACK = re.compile(r"IGLC|Proceedings|Conference|\b(19|20)\d\d\b|^\W*$|^page\b", re.I)


def footer_lines(reader, pages=(0, 2, 4)) -> list[str]:
    lines = []
    for index in pages:
        if index >= len(reader.pages):
            continue
        rows = {}

        def visit(text, cm, tm, font, size):
            y = tm[5] * cm[3] + cm[5]
            if text.strip() and y < FOOTER_ZONE:
                rows.setdefault(round(y), []).append(text)

        reader.pages[index].extract_text(visitor_text=visit)
        for _, parts in sorted(rows.items(), reverse=True):
            lines.append(re.sub(r"\s+", " ", "".join(parts)).strip())
    return lines


def candidate(line: str) -> str:
    # the page number, at either end, often run together with the text by the extraction
    line = re.sub(r"^\d{1,4}(?=[\sA-Za-z])|(?<=[A-Za-z)\s])\d{1,4}$", "", line).strip(" -–|")
    return "" if NOT_A_TRACK.search(line) or len(line) < 4 else line


class Command(BaseCommand):
    help = "Suggest tracks from the footers of the papers' PDFs, as a CSV to check."

    def add_arguments(self, parser):
        parser.add_argument("--conference", type=int)
        parser.add_argument("--folder", help="read local PDFs named by DOI number instead of downloading")
        parser.add_argument("--out", default="tracks.csv")

    def _pdf(self, paper, folder):
        if folder:
            number = paper.doi.rsplit("/", 1)[-1] if paper.doi else str(paper.pk)
            for name in (number, number.lstrip("0"), str(paper.pk)):
                path = Path(folder) / f"{name}.pdf"
                if path.exists():
                    return path.read_bytes()
            return None
        if not paper.full_text_url:
            return None
        with urllib.request.urlopen(paper.full_text_url, timeout=60) as response:
            return response.read()

    def handle(self, *args, conference=None, folder=None, out="tracks.csv", **options):
        papers = Paper.objects.select_related("conference").order_by("conference__number", "first_page", "pk")
        if conference:
            papers = papers.filter(conference__number=conference)
        found = []
        for paper in papers:
            try:
                data = self._pdf(paper, folder)
                lines = footer_lines(PdfReader(io.BytesIO(data))) if data else []
                note = "" if data else "no PDF"
            except Exception as error:  # noqa: BLE001 - note it and carry on
                lines, note = [], f"{type(error).__name__}: {error}"
            counts = Counter(filter(None, map(candidate, lines)))
            track = counts.most_common(1)[0][0] if counts else ""
            found.append([paper.conference.number, paper.pk, paper.doi, paper.first_page, track, note])
            self.stdout.write(f"IGLC {paper.conference.number} {paper.pk}: {track or '-'} {note}")

        # Spelling variants within a conference ("Health, Safety, and Quality", other capitals)
        # take the most common spelling.
        def key(title):
            return re.sub(r"[^a-z]+", " ", title.lower().replace(" and ", " ")).strip()

        spellings = Counter((row[0], row[4]) for row in found if row[4])
        best = {}
        for (number, title), count in spellings.most_common():
            best.setdefault((number, key(title)), title)
        for row in found:
            if row[4]:
                row[4] = best[(row[0], key(row[4]))]
        shared = Counter((row[0], row[4]) for row in found if row[4])
        with open(out, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["conference", "paper_id", "doi", "first_page", "track", "papers_with_this_track", "note"])
            for row in found:
                writer.writerow(row[:5] + [shared.get((row[0], row[4]), 0) if row[4] else 0, row[5]])
        self.stdout.write(self.style.SUCCESS(
            f"{len(found)} papers, {sum(1 for r in found if r[4])} with a suggested track; written to {out}"))
