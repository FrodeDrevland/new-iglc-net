from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from . import exports
from .models import Author, Conference, LinkCategory, Paper


def _papers():
    return Paper.objects.select_related("conference", "volume").prefetch_related(
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
    conference = get_object_or_404(Conference.objects.prefetch_related("editors", "volumes"), pk=pk)
    papers = _papers().filter(conference=conference)
    return render(request, "archive/conference_detail.html", {"conference": conference, "papers": papers})


def paper_detail(request, pk):
    # Deliberately not filtered on is_published: DOIs must always resolve.
    paper = get_object_or_404(_papers(), pk=pk)
    keywords = [k.strip() for k in paper.keywords.replace(";", ",").split(",") if k.strip()]
    return render(request, "archive/paper_detail.html", {"paper": paper, "keywords": keywords})


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


def _search(query: str):
    if not query:
        return Paper.objects.none()
    match = (
        Q(title__icontains=query) | Q(abstract__icontains=query) | Q(keywords__icontains=query)
        | Q(authors__last_name__icontains=query) | Q(authors__first_name__icontains=query)
    )
    ids = Paper.objects.filter(match, conference__is_published=True).values("pk")
    return _papers().filter(pk__in=ids).order_by("-conference__number", "first_page", "title")


@csrf_exempt  # read-only; the old site's search form posted here
def search(request):
    query = (request.GET.get("q") or request.POST.get("query") or "").strip()
    return render(request, "archive/search.html", {"query": query, "papers": _search(query)})


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
    return _export(_search((request.GET.get("query") or request.GET.get("q") or "").strip()), "IGLC-search", fmt)


def export_complete(request, fmt):
    return _export(_papers().filter(conference__is_published=True), "IGLC-complete", fmt)


def _export(papers, name, fmt):
    if fmt == "bibtex":
        return _download(exports.bibtex(papers, settings.SITE_URL), f"{name}.bib")
    return _download(exports.ris(papers, settings.SITE_URL), f"{name}.ris")


def links(request):
    categories = LinkCategory.objects.prefetch_related("links")
    return render(request, "archive/links.html", {"categories": categories})
