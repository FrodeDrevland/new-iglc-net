from datetime import date

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from . import citations, exports
from .models import Author, AuthorPerson, Conference, LinkCategory, Paper
from .management.commands.group_authors import fold
from .search import common_tracks, SORTS, matching_authors, search_papers


def _papers():
    return Paper.objects.select_related("conference", "volume", "track").prefetch_related(
        Prefetch("authors", queryset=Author.objects.order_by("order", "pk")),
        "conference__editors",
    )


def home(request):
    from wagtail.models import Page

    conferences = Conference.objects.filter(is_published=True).annotate(paper_count=Count("papers")).order_by("-number")
    first = Conference.objects.exclude(start_date=None).order_by("start_date").first()
    return render(request, "home.html", {
        "latest_conferences": conferences[:6],
        "paper_count": Paper.objects.filter(conference__is_published=True).count(),
        "conference_count": Conference.objects.count(),
        "first_year": first.year if first else None,
        "conference_page": Page.objects.live().filter(slug="active-conference").first(),
    })


def conference_list(request):
    conferences = Conference.objects.filter(is_published=True).annotate(paper_count=Count("papers")).order_by("-number")
    return render(request, "archive/conference_list.html", {"conferences": conferences})


def conference_detail(request, pk):
    conference = get_object_or_404(
        Conference.objects.prefetch_related("editors", "volumes", "proceedings_files"), pk=pk)
    papers = list(_papers().filter(conference=conference))
    if any(p.track_id for p in papers):
        # Tracks in the order they start in the proceedings; papers by page within each.
        start = {}
        for p in papers:
            if p.track_id and p.first_page:
                start[p.track_id] = min(start.get(p.track_id, p.first_page), p.first_page)
        order = {t.pk: t.order for t in conference.tracks.all()}
        papers.sort(key=lambda p: (p.track_id is None, order.get(p.track_id) or 10 ** 6, start.get(p.track_id, 10 ** 6),
                                   p.first_page or 10 ** 6, p.title))
    tracks = []
    for p in papers:
        if p.track and (not tracks or tracks[-1][0] != p.track):
            tracks.append([p.track, 0])
        if p.track:
            tracks[-1][1] += 1
    return render(request, "archive/conference_detail.html", {
        "conference": conference,
        "papers": papers,
        "tracks": tracks,
        "untracked": sum(1 for p in papers if not p.track_id) if tracks else 0,
        "show_paper_numbers": _show_paper_numbers(conference),
        "website": _conference_website(conference),
    })


def _conference_website(conference):
    """The conference's own website on the conference sites, if it is published."""
    from apps.conferences.models import ConferenceHomePage

    home = ConferenceHomePage.objects.live().filter(conference=conference).first()
    return home.full_url if home else ""


def _show_paper_numbers(conference) -> bool:
    """During the conference and one month after, show each paper's number (the end of its DOI),
    which the programme uses to refer to papers. As on the old site."""
    end = conference.end_date
    if not end:
        return False
    month, year = (end.month % 12) + 1, end.year + (end.month == 12)
    day = min(end.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
                        31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date.today() < end.replace(year=year, month=month, day=day)


def paper_detail(request, pk):
    # Deliberately not filtered on is_published: DOIs must always resolve.
    paper = get_object_or_404(_papers(), pk=pk)
    keywords = [k.strip() for k in paper.keywords.replace(";", ",").split(",") if k.strip()]
    return render(request, "archive/paper_detail.html", {
        "paper": paper,
        "keywords": keywords,
        "apa": citations.apa7(paper),
        "short": citations.iglc_short(paper),
        "corrections": _corrections(paper),
    })


def _corrections(paper):
    from apps.production.models import Correction

    return list(Correction.objects.filter(submission__paper=paper, public=True).order_by("time"))


def paper_pdf(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    if not paper.full_text_url:
        raise Http404("No full text for this paper.")
    return redirect(paper.full_text_url)


def paper_presentation(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    if not paper.presentation_url:
        raise Http404("No presentation for this paper.")
    return redirect(paper.presentation_url)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _search_params(request):
    data = request.GET
    sort = data.get("sort", "relevance")
    return {
        "query": (data.get("q") or data.get("query") or request.POST.get("query") or "").strip()[:200],
        "year_from": _int(data.get("from")),
        "year_to": _int(data.get("to")),
        "conference": _int(data.get("conference")),
        "track": (data.get("track") or "").strip()[:100],
        "sort": sort if sort in SORTS else "relevance",
    }


@csrf_exempt  # read-only; the old site's search form posted here
def search(request):
    params = _search_params(request)
    searched = bool(params["query"] or params["year_from"] or params["year_to"] or params["conference"]
                    or params["track"])
    page = None
    if searched:
        ids = list(search_papers(**params).values_list("pk", flat=True))
        page = Paginator(ids, 25).get_page(request.GET.get("page"))
        by_id = _papers().in_bulk(list(page.object_list))
        page.object_list = [by_id[pk] for pk in page.object_list if pk in by_id]
    query_string = request.GET.copy()
    query_string.pop("page", None)
    if params["query"] and "q" not in query_string:
        query_string["q"] = params["query"]
    years = Conference.objects.filter(is_published=True).exclude(start_date=None).aggregate(
        first=Min("start_date__year"), last=Max("start_date__year"))
    return render(request, "archive/search.html", {
        **params,
        "searched": searched,
        "page": page,
        "query_string": query_string.urlencode(),
        "authors": matching_authors(params["query"]) if params["query"] and (not page or page.number == 1) else [],
        "conferences": Conference.objects.filter(is_published=True).order_by("-number"),
        "years": range(years["last"] or date.today().year, (years["first"] or 1993) - 1, -1),
        "sorts": [("relevance", "Relevance"), ("newest", "Newest first"), ("oldest", "Oldest first")],
        "common_tracks": common_tracks(),
    })


def _initial(name):
    folded = fold(name)
    return folded[0].upper() if folded[:1].isalpha() else ""


def author_list(request):
    people = AuthorPerson.objects.annotate(paper_count=Count("authorships__paper", distinct=True)).filter(
        paper_count__gt=0)
    query = (request.GET.get("q") or "").strip()[:100]
    letter = (request.GET.get("letter") or "").strip()[:1].upper()
    if query:
        people = matching_authors(query, limit=500)
    elif letter:
        # Letters are compared without accents, so Ø and Ö are listed under O.
        people = sorted((p for p in people if _initial(p.last_name) == letter), key=lambda p: fold(p.last_name))
    else:
        people = people.order_by("-paper_count", "last_name")[:60]
    letters = sorted({_initial(name) for name in AuthorPerson.objects.values_list("last_name", flat=True)} - {""})
    return render(request, "archive/author_list.html", {
        "people": people, "query": query, "letter": letter, "letters": letters,
        "person_count": AuthorPerson.objects.filter(authorships__isnull=False).distinct().count(),
    })


def author_detail(request, pk):
    person = get_object_or_404(AuthorPerson, pk=pk)
    papers = list(_papers().filter(authors__person=person, conference__is_published=True).distinct().order_by(
        "-conference__number", "first_page"))
    coauthors = (
        AuthorPerson.objects.filter(authorships__paper__in=[p.pk for p in papers]).exclude(pk=person.pk)
        .annotate(joint=Count("authorships__paper", distinct=True)).order_by("-joint", "last_name")[:12]
    )
    names = (Author.objects.filter(person=person).values("first_name", "last_name")
             .annotate(n=Count("pk")).order_by("-n"))
    variants = [f"{n['first_name']} {n['last_name']}".strip() for n in names]
    years = [p.year for p in papers if p.year]
    return render(request, "archive/author_detail.html", {
        "person": person,
        "papers": papers,
        "coauthors": coauthors,
        "other_names": [v for v in variants if v != person.full_name],
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
        "conference_count": len({p.conference_id for p in papers}),
    })


def find_by_conftool_id(request, conftool_id=None):
    """Old helper: find a paper from its year and ConfTool submission number."""
    year = request.GET.get("year", "")
    conftool_id = conftool_id or request.GET.get("id", "")
    if not (year.isdigit() and conftool_id):
        return HttpResponseBadRequest("year and id are required")
    paper = Paper.objects.filter(
        conference__start_date__year=int(year), doi__endswith=conftool_id[:3]
    ).first()
    if paper is None:
        raise Http404("No matching paper.")
    return redirect(paper)


def _download(content: str, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Robots-Tag"] = "noindex"
    return response


def export_paper(request, pk, fmt):
    paper = get_object_or_404(_papers(), pk=pk)
    return _export([paper], f"IGLC-paper-{pk}", fmt)


def export_conference(request, pk, fmt):
    conference = get_object_or_404(Conference, pk=pk)
    return _export(_papers().filter(conference=conference), f"IGLC-{conference.number}", fmt)


def export_search(request, fmt):
    params = _search_params(request)
    if not (params["query"] or params["year_from"] or params["year_to"] or params["conference"]):
        return HttpResponseBadRequest("Nothing to export: give a search.")
    ids = list(search_papers(**params).values_list("pk", flat=True)[:5000])
    order = {pk: i for i, pk in enumerate(ids)}
    papers = sorted(_papers().filter(pk__in=ids), key=lambda p: order[p.pk])
    return _export(papers, "IGLC-search", fmt)


def export_complete(request, fmt):
    return _export(_papers().filter(conference__is_published=True), "IGLC-complete", fmt)


def _export(papers, name, fmt):
    if fmt == "bibtex":
        return _download(exports.bibtex(papers, settings.SITE_URL), f"{name}.bib")
    return _download(exports.ris(papers, settings.SITE_URL), f"{name}.ris")


def links(request):
    categories = LinkCategory.objects.prefetch_related("links")
    return render(request, "archive/links.html", {"categories": categories})
