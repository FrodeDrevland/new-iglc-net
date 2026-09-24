"""The order of the proceedings, and the page numbers that follow from it."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from .models import Production, Submission


@dataclass
class Placed:
    submission: Submission
    pages: int | None
    first_page: int | None
    last_page: int | None


def ordered(production: Production):
    """(track or None, [submissions]) in proceedings order; withdrawn papers left out."""
    papers = (production.submissions.exclude(status=Submission.Status.WITHDRAWN)
              .select_related("track").prefetch_related("versions"))
    groups = {}
    for paper in papers:
        groups.setdefault(paper.track, []).append(paper)
    tracks = sorted((t for t in groups if t is not None), key=lambda t: (t.order, t.title))
    result = [(t, sorted(groups[t], key=lambda p: (p.position, p.conftool_id))) for t in tracks]
    if None in groups:
        result.append((None, sorted(groups[None], key=lambda p: (p.position, p.conftool_id))))
    return result


def number_pages(production: Production) -> tuple[list[tuple], list[Submission]]:
    """Page numbers in order. Papers follow each other directly (899–910, 911–921, ...).
    Returns [(track, [Placed])] and the papers whose page count is not known yet (no PDF);
    numbering stops being exact from the first of those."""
    page = production.first_page
    unknown, result = [], []
    for track, papers in ordered(production):
        placed = []
        for paper in papers:
            current = paper.current
            pages = current.pages if current else None
            if pages and page is not None:
                placed.append(Placed(paper, pages, page, page + pages - 1))
                page += pages
            else:
                placed.append(Placed(paper, pages, None, None))
                unknown.append(paper)
                page = None
        result.append((track, placed))
    return result, unknown


@transaction.atomic
def save_order(production: Production, layout: list[tuple[int | None, list[int]]]):
    """layout: [(track id or None, [ConfTool IDs in order])], tracks in proceedings order.
    Moves papers between tracks if needed, then stores the page numbers."""
    tracks = {t.pk: t for t in production.conference.tracks.all()}
    papers = {s.conftool_id: s for s in production.submissions.all()}
    for track_order, (track_id, ids) in enumerate(layout, 1):
        track = tracks.get(track_id) if track_id else None
        if track and track.order != track_order:
            track.order = track_order
            track.save(update_fields=["order"])
        for position, conftool_id in enumerate(ids, 1):
            paper = papers.get(conftool_id)
            if paper is None:
                continue
            paper.position, paper.track = position, track
            paper.save(update_fields=["position", "track"])
    store_page_numbers(production)


def store_page_numbers(production: Production):
    layout, _ = number_pages(production)
    for _, placed in layout:
        for item in placed:
            if item.submission.first_page != item.first_page:
                item.submission.first_page = item.first_page
                item.submission.save(update_fields=["first_page"])
