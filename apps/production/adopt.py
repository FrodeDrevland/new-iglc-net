"""A production for a conference whose papers are already published (from before the
production tools, e.g. IGLC 28 or IGLC 34), so its full proceedings can be made here.

The papers come from the archive as they are: published, with their page numbers, tracks and
PDFs. Nothing is renumbered or republished."""

from __future__ import annotations

import re

from django.db import transaction

from apps.archive.models import Conference

from .models import Event, Production, Submission


class AdoptError(Exception):
    pass


def number_of(paper) -> int | None:
    """The paper number: the end of its DOI (10.24928/2026/0183 -> 183)."""
    digits = re.sub(r"\D", "", (paper.doi or "").rsplit("/", 1)[-1])
    return int(digits) if digits else None


@transaction.atomic
def adopt_published(conference: Conference, user=None) -> tuple[Production, dict]:
    papers = list(conference.papers.select_related("track").prefetch_related("authors")
                  .order_by("first_page", "pk"))
    if not papers:
        raise AdoptError(f"{conference} has no papers in the archive")
    missing = [p for p in papers if not (p.first_page and p.last_page)]
    if missing:
        raise AdoptError(f"{len(missing)} paper(s) have no page numbers, e.g. “{missing[0].title[:60]}”")
    production, created = Production.objects.get_or_create(conference=conference)
    if not created and production.submissions.filter(published_version__isnull=False).exists():
        raise AdoptError(f"{production} was made with the production tools; it is not adopted from the archive")
    report = {"added": 0, "updated": 0, "without_number": [], "without_pdf": 0}
    positions = {}
    for paper in papers:
        number = number_of(paper)
        if number is None:
            report["without_number"].append(paper.title[:60])
            continue
        report["without_pdf"] += not paper.full_text_url
        position = positions[paper.track_id] = positions.get(paper.track_id, 0) + 1
        submission, was_created = Submission.objects.update_or_create(
            production=production, conftool_id=number,
            defaults={
                "title": paper.title[:500], "track": paper.track, "paper": paper, "position": position,
                "first_page": paper.first_page, "status": Submission.Status.APPROVED,
                "registered_authors": [{"name": f"{a.first_name} {a.last_name}".strip(), "organisation": "",
                                        "email": ""} for a in paper.authors.all()],
            })
        report["added" if was_created else "updated"] += 1
        if was_created:
            Event.objects.create(submission=submission, user=user, action="taken from the archive (published before)")
    # tracks in the order of their first page
    firsts = {}
    for paper in papers:
        if paper.track_id:
            firsts.setdefault(paper.track_id, paper.first_page)
    for order, track in enumerate(sorted(conference.tracks.all(), key=lambda t: firsts.get(t.pk, 10**9)), 1):
        if track.order != order:
            track.order = order
            track.save(update_fields=["order"])
    production.first_page = papers[0].first_page
    production.status = Production.Status.PAPERS_PUBLISHED
    production.save(update_fields=["first_page", "status"])
    return production, report
