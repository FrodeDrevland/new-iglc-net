"""The programme at the venue: now and next, today, my programme, and calendar files.

Served on program.iglc.net for the current conference (config/programme_urls.py), and on the
conference site under /<year>/programme/ for any conference (conference_urls.py). The pages are
made for phones; the sessions link to their pages on the conference site."""

from __future__ import annotations

from datetime import date as Date, datetime

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.conferences.models import ConferenceHomePage

from . import ics, public
from .models import Programme, Session


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


def _setup(request, year=None):
    homes = ConferenceHomePage.objects.live().select_related("conference")
    home = homes.filter(slug=str(year)).first() if year else homes.filter(is_current=True).first()
    if home is None:
        raise Http404
    programme = Programme.objects.filter(conference=home.conference).select_related("conference").first()
    if programme is None or not programme.is_public:
        raise Http404
    year = home.conference.start_date.year
    on_programme_host = getattr(request, "programme_host", False)
    site_root = home.get_site().root_url if on_programme_host else ""
    if on_programme_host:
        links = {"now": "/", "today": "/today/", "my": "/my/", "calendar": "/calendar.ics"}
    else:
        links = {name: public.url(name, year) for name in ("now", "today", "my", "calendar")}
    context = {"home": home, "conference": home.conference, "programme": programme, "year": year,
               "base": site_root, "links": links, "main_site_url": settings.SITE_URL,
               "home_url": public.home_url(home), "programme_page_url": f"{public.home_url(home)}programme/",
               "venue_url": settings.PROGRAMME_URL,
               "on_programme_host": on_programme_host}
    return programme, context


def _public_sessions(programme):
    return public.sessions_of(programme, programme.parts.filter(public=True))


def _moment(request, programme):
    """Now in the conference's time zone; ?at=2027-07-20T10:45 shows another moment (for trying out)."""
    at = request.GET.get("at", "")
    if at:
        try:
            return datetime.fromisoformat(at).replace(tzinfo=programme.tz), True
        except ValueError:
            pass
    return timezone.now().astimezone(programme.tz), False


def now(request, year=None):
    programme, context = _setup(request, year)
    moment, chosen = _moment(request, programme)
    sessions = list(_public_sessions(programme))
    days = sorted({s.date for s in sessions})
    today, clock = moment.date(), moment.time().replace(tzinfo=None)
    state = "during" if today in days else ("before" if not days or today < days[0] else
                                              ("after" if today > days[-1] else "between"))
    current, upcoming = [], []
    if state == "during":
        todays = [s for s in sessions if s.date == today]
        current = [s for s in todays if s.start <= clock < s.end]
        later = [s for s in todays if s.start > clock]
        if later:
            first = min(s.start for s in later)
            upcoming = [s for s in later if s.start == first]
    elif state in ("before", "between"):
        following = [d for d in days if d > today]
        if following:
            first_day = [s for s in sessions if s.date == following[0]]
            first = min(s.start for s in first_day)
            upcoming = [s for s in first_day if s.start == first]
    changes = sorted([s for s in sessions if s.changed and (s.change_note or s.cancelled)],
                     key=lambda s: s.changed, reverse=True)[:8]
    context.update({"tab": "now", "moment": moment.replace(tzinfo=None), "chosen": chosen, "state": state, "current": current,
                    "upcoming": upcoming, "changes": changes, "days": days})
    return render(request, "programme/venue/now.html", context)


def today(request, year=None):
    programme, context = _setup(request, year)
    moment, _ = _moment(request, programme)
    sessions = list(_public_sessions(programme))
    days = sorted({s.date for s in sessions})
    wanted = request.GET.get("day", "")
    try:
        day = Date.fromisoformat(wanted) if wanted else None
    except ValueError:
        day = None
    if day not in days:
        day = moment.date() if moment.date() in days else next((d for d in days if d > moment.date()),
                                                               days[-1] if days else None)
    context.update({"tab": "today", "days": days, "day": public.by_day([s for s in sessions if s.date == day])[0]
                    if day else None, "today": moment.date()})
    return render(request, "programme/venue/today.html", context)


def my(request, year=None):
    programme, context = _setup(request, year)
    context.update({"tab": "my", "all_days": public.by_day(list(_public_sessions(programme)))})
    return render(request, "programme/venue/my.html", context)


def _session_url(context):
    home = context["home"]
    root = public.home_url(home)
    return lambda s: f"{root}programme/session/{s.pk}/"


def _calendar_response(programme, sessions, name, context, filename):
    body = ics.calendar(programme, sessions, name, _session_url(context))
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def calendar(request, year=None):
    """The public programme; ?part=<id> one public part; ?k=<private link> a private part;
    ?sessions=1,2,3 a visitor's own selection."""
    programme, context = _setup(request, year)
    number = programme.conference.number
    parts = programme.parts.filter(public=True)
    name = f"IGLC {number} programme"
    if request.GET.get("k"):
        try:
            parts = programme.parts.filter(token=request.GET["k"])
        except Exception:  # noqa: BLE001 - not a UUID
            parts = programme.parts.none()
        if not parts:
            raise Http404
        name = f"IGLC {number}: {parts[0].name}"
    elif request.GET.get("part", "").isdigit():
        parts = parts.filter(pk=request.GET["part"])
        if not parts:
            raise Http404
        name = f"IGLC {number}: {parts[0].name}"
    sessions = public.sessions_of(programme, parts).exclude(kind__in=[Session.Kind.BREAK])
    if "sessions" in request.GET:
        ids = [int(i) for i in request.GET["sessions"].split(",") if i.strip().isdigit()]
        sessions = sessions.filter(pk__in=ids)
        name = f"IGLC {number}: my programme"
    return _calendar_response(programme, sessions, name, context, f"iglc{number}-programme.ics")


def session_calendar(request, year, pk):
    programme, context = _setup(request, year)
    session = get_object_or_404(public.sessions_of(programme, programme.parts.all()), pk=pk)
    if not session.part.public and request.GET.get("k", "") != str(session.part.token):
        raise Http404
    return _calendar_response(programme, [session], f"IGLC {programme.conference.number}", context,
                              f"iglc{programme.conference.number}-session-{session.pk}.ics")
