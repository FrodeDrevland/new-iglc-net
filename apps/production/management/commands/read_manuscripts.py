"""Read the metadata of every Word file in a folder and report what does not follow the template.

    python manage.py read_manuscripts "C:/…/Papers" --out report.csv [--json all.json] [--conference 34]

With --conference, the result is also compared with the papers of that conference in the
archive (matched on DOI): titles, authors and pages that differ are listed.
The reports contain authors' email addresses: keep them out of the repository.
"""

import csv
import json
import re
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.production.docx_reader import read_manuscript


def _norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _number(path):
    digits = re.sub(r"\D", "", path.stem)
    return (int(digits) if digits else 0, path.name)


class Command(BaseCommand):
    help = "Read the metadata of the Word files in a folder and report problems."

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--out", default="manuscripts-report.csv", help="CSV with one row per problem")
        parser.add_argument("--json", help="also write everything that was read as JSON")
        parser.add_argument("--conference", type=int, help="compare with this conference in the archive")

    def handle(self, folder, out, json=None, conference=None, **options):
        files = sorted(Path(folder).glob("*.docx"), key=_number)
        files = [f for f in files if not f.name.startswith("~$")]
        if not files:
            raise CommandError(f"No .docx files in {folder}")
        results = [read_manuscript(f) for f in files]

        rows = [(r.file, r.doi, issue) for r in results for issue in r.issues]
        if conference:
            rows += self._compare(results, conference)

        with open(out, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "doi", "problem"])
            writer.writerows(rows)
        if json:
            import json as jsonlib

            Path(json).write_text(jsonlib.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=1),
                                  encoding="utf-8")

        authors = sum(len(r.authors) for r in results)
        clean = sum(1 for r in results if not r.issues)
        self.stdout.write(self.style.SUCCESS(
            f"{len(results)} files, {authors} authors; {clean} files without problems; "
            f"{len(rows)} problems listed in {out}"))

    def _compare(self, results, number):
        from apps.archive.models import Paper

        papers = {p.doi: p for p in Paper.objects.filter(conference__number=number).prefetch_related("authors")}
        rows = []
        for r in results:
            paper = papers.get(r.doi)
            if not paper:
                rows.append((r.file, r.doi, "Archive: no paper with this DOI"))
                continue
            title = r.citation_title or r.title
            if _norm(paper.title) != _norm(title):
                rows.append((r.file, r.doi, f"Archive title differs: “{paper.title}” / file: “{title}”"))
            archive_names = [_norm(f"{a.first_name} {a.last_name}") for a in paper.authors.all()]
            file_names = [_norm(a.name) for a in r.authors]
            if archive_names != file_names:
                rows.append((r.file, r.doi, "Archive authors differ: " + "; ".join(archive_names)
                             + " / file: " + "; ".join(file_names)))
            if r.first_page and (paper.first_page, paper.last_page) != (r.first_page, r.last_page):
                rows.append((r.file, r.doi, f"Archive pages {paper.first_page}–{paper.last_page}, "
                                            f"file {r.first_page}–{r.last_page}"))
        return rows
