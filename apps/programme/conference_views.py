"""The programme's own pages on the conference site, under /<year>/programme/ (public.py).

They are drawn in the conference site's layout, as if they were below its programme page (the
page with the slug "programme", else the home page)."""

from __future__ import annotations

from datetime import date as Date

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.conferences.models import ConferenceHomePage

from . import public
from .models import Location, Part, Programme, Session


def _setup(request, year):
    home = ConferenceHomePage.objects.live().filter(slug=str(year)).select_related("conference").first()
    if home is None:
        raise Http404
    programme = Programme.objects.filter(conference=home.conference).select_related("conference").first()
    if programme is None or not programme.is_public:
        raise Http404
    page = home.get_children().live().filter(slug="programme").specific().first() or home
    context = page.get_context(request)
    context.update({"programme": programme, "year": year, "programme_page": page})
    return programme, context


def _key_part(request, programme):
    """The part whose private link was followed (?k=...), if any."""
    key = request.GET.get("k", "")
    if not key:
        return None
    try:
        return programme.parts.filter(token=key).first()
    except Exception:  # noqa: BLE001 - not a UUID
        return None


def _may_see(part, request, programme) -> bool:
    return part.public or _key_part(request, programme) == part


def day(request, year, day):
    programme, context = _setup(request, year)
    try:
        wanted = Date.fromisoformat(day)
    except ValueError:
        raise Http404
    sessions = list(public.sessions_of(programme, programme.parts.filter(public=True)).filter(date=wanted))
    if not sessions:
        raise Http404
    days = public.by_day(sessions)
    all_days = sorted(set(programme.sessions.filter(part__public=True).values_list("date", flat=True)))
    context.update({"day": days[0], "all_days": all_days,
                    "several_parts": len({s.part_id for s in sessions}) > 1})
    return render(request, "programme/public/day.html", context)


def session(request, year, pk):
    programme, context = _setup(request, year)
    session = get_object_or_404(Session.objects.select_related("location", "part", "keynote", "track")
                                .prefetch_related("people", "items__submission__paper__authors"),
                                pk=pk, programme=programme)
    if not _may_see(session.part, request, programme):
        raise Http404
    key_part = _key_part(request, programme)
    parallel = [s for s in programme.sessions.filter(date=session.date, part=session.part)
                .select_related("location") if s.pk != session.pk and s.overlaps(session)]
    context.update({"session": session, "parallel": parallel, "key": key_part.token if key_part else "",
                    "private": not session.part.public})
    return render(request, "programme/public/session.html", context)


def location(request, year, pk):
    programme, context = _setup(request, year)
    location = get_object_or_404(Location.objects.select_related("floor_plan"), pk=pk, programme=programme)
    sessions = list(public.sessions_of(programme, programme.parts.filter(public=True)).filter(location=location))
    context.update({"location": location, "days": public.by_day(sessions)})
    return render(request, "programme/public/location.html", context)


def part(request, year, pk):
    programme, context = _setup(request, year)
    part = get_object_or_404(Part, pk=pk, programme=programme, public=True)
    return _part_page(request, programme, context, part, key="")


def private(request, year, token):
    programme, context = _setup(request, year)
    part = get_object_or_404(Part, token=token, programme=programme)
    return _part_page(request, programme, context, part, key=part.token)


def _part_page(request, programme, context, part, key):
    sessions = list(public.sessions_of(programme, [part]))
    context.update({"part": part, "days": public.by_day(sessions), "key": key, "private": not part.public})
    return render(request, "programme/public/part.html", context)
