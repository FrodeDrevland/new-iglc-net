"""Search in the proceedings archive.

On PostgreSQL: full-text search with stemming ("planning" finds "planned") and ranking, where
title and author names weigh most, then keywords, then the abstract. If that finds nothing (for
example a part of a word), and on SQLite, every word must appear somewhere in the paper, and
results are ranked by where the words were found.
"""

import re

from django.db import connection
from django.db.models import Case, F, FloatField, IntegerField, Q, Value, When

from .models import AuthorPerson, Paper

SORTS = {
    "relevance": None,
    "newest": ("-conference__number", "first_page"),
    "oldest": ("conference__number", "first_page"),
}


def terms(query: str) -> list[str]:
    return [t for t in re.findall(r"[\w][\w'-]*", query) if len(t) > 1][:12]


def filtered(year_from=None, year_to=None, conference=None, track=""):
    papers = Paper.objects.filter(conference__is_published=True)
    if track:
        # Track names vary between conferences ("People, Culture and Change", "People, Culture, & Change"):
        # every word must be in the track's name.
        for word in re.findall(r"\w{2,}", track.lower()):
            if word not in ("and", "the", "of", "with"):
                papers = papers.filter(track__title__icontains=word)
    if year_from:
        papers = papers.filter(conference__start_date__year__gte=year_from)
    if year_to:
        papers = papers.filter(conference__start_date__year__lte=year_to)
    if conference:
        papers = papers.filter(conference__number=conference)
    return papers


def _full_text(papers, query):
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    vector = (
        SearchVector("title", weight="A", config="english")
        + SearchVector("authors_text", weight="A", config="english")
        + SearchVector("keywords", weight="B", config="english")
        + SearchVector("abstract", weight="C", config="english")
    )
    search_query = SearchQuery(query, config="english", search_type="websearch")
    # Filter on the match itself: the rank alone is above 0 when only some of the words match.
    return papers.annotate(document=vector, rank=SearchRank(vector, search_query)).filter(document=search_query)


def _contains(papers, words):
    fields = {"title": 3, "authors_text": 3, "keywords": 2, "abstract": 1}
    for word in words:
        papers = papers.filter(Q(*[Q(**{f"{f}__icontains": word}) for f in fields], _connector=Q.OR))
    score = Value(0, output_field=IntegerField())
    for word in words:
        for field, weight in fields.items():
            score = score + Case(When(**{f"{field}__icontains": word}, then=Value(weight)),
                                 default=Value(0), output_field=IntegerField())
    if len(words) > 1:  # the whole phrase counts extra
        phrase = " ".join(words)
        score = score + Case(When(title__icontains=phrase, then=Value(6)), default=Value(0),
                             output_field=IntegerField())
        score = score + Case(When(abstract__icontains=phrase, then=Value(2)), default=Value(0),
                             output_field=IntegerField())
    return papers.annotate(rank=score)


def search_papers(query="", year_from=None, year_to=None, conference=None, sort="relevance", track=""):
    papers = filtered(year_from, year_to, conference, track)
    words = terms(query)
    if words:
        found = None
        if connection.vendor == "postgresql":
            found = _full_text(papers, query)
            if not found.exists():
                found = None
        papers = found if found is not None else _contains(papers, words)
    elif not (year_from or year_to or conference or track):
        return Paper.objects.none()

    order = SORTS.get(sort)
    if order is None and words:
        return papers.order_by(F("rank").desc(nulls_last=True), "-conference__number", "first_page")
    return papers.order_by(*(order or SORTS["newest"]))


def matching_authors(query: str, limit=8):
    words = terms(query)
    if not words:
        return AuthorPerson.objects.none()
    people = AuthorPerson.objects.all()
    for word in words:
        people = people.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word))
    from django.db.models import Count

    return people.annotate(paper_count=Count("authorships__paper", distinct=True)).order_by(
        "-paper_count", "last_name")[:limit]


def common_tracks(limit=30) -> list[str]:
    """The track names used most (by number of papers), for the search form's suggestions."""
    from django.db.models import Count

    from .models import ConferenceTrack

    counts = {}
    for title, n in (ConferenceTrack.objects.filter(conference__is_published=True)
                     .annotate(n=Count("papers")).values_list("title", "n")):
        counts[title] = counts.get(title, 0) + n
    return [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]
