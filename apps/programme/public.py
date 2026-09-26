"""The programme as shown on the conference website (docs/programme.md, "Where it is shown").

- The "programme" block of a conference page: every day, as a grid of locations by time on large
  screens and a list on phones.
- Pages under /<year>/programme/ (conference_urls.py): a day, a session, a location, a part, and
  a part that is not public through its private link.

Hidden programmes are shown only in the page editor's preview, to people who work on them. Parts
that are not public are left out, except on their private link's pages.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from django.urls import reverse

from .models import Programme, Session

URLCONF = "config.conference_urls"


def url(name: str, *args) -> str:
    """A programme page on the conference site, whichever site is serving the request."""
    return reverse(f"conference_programme:{name}", args=args, urlconf=URLCONF)


def home_url(home) -> str:
    """The conference website's address, e.g. https://conference.iglc.net/2027/. Unlike
    home.full_url, this works on hosts whose URLs do not include Wagtail's (program.iglc.net)."""
    return f"{home.get_site().root_url}/{home.slug}/"


def visible(programme, request=None) -> bool:
    if programme is None:
        return False
    if programme.is_public:
        return True
    from .access import can_view

    return bool(request is not None and getattr(request, "is_preview", False) and can_view(request.user, programme))


def sessions_of(programme, parts):
    return (programme.sessions.filter(part__in=parts)
            .select_related("location", "part", "keynote")
            .prefetch_related("people", "items__submission__paper__authors", "items__submission__presentation", "items__contribution"))


def by_day(sessions) -> list:
    days = OrderedDict()
    for session in sessions:
        days.setdefault(session.date, []).append(session)
    return [Day(date, day_sessions) for date, day_sessions in days.items()]


def programme_days(conference, kind: str = "", request=None, parts=None):
    """{"programme", "days": [Day], "several_parts", "year"} or None."""
    if conference is None:
        return None
    programme = Programme.objects.filter(conference=conference).select_related("conference").first()
    if not visible(programme, request):
        return None
    if parts is None:
        parts = programme.parts.filter(public=True)
        if kind:
            parts = parts.filter(kind=kind)
    sessions = list(sessions_of(programme, parts))
    from django.conf import settings

    home = getattr(conference, "site_home", None)
    return {"programme": programme, "days": by_day(sessions), "year": conference.start_date.year,
            "several_parts": len({s.part_id for s in sessions}) > 1,
            "venue_url": settings.PROGRAMME_URL if home and home.is_current else ""}


# ---------------------------------------------------------------- the grid of a day

@dataclass
class Placed:
    session: Session
    row: str      # CSS grid-row, e.g. "3 / 6"
    column: str   # CSS grid-column


class Day:
    """One day's sessions, for the list and for the grid (locations as columns, time as rows).

    A session without location, or a plenary session or break with nothing beside it, spans every
    column. The rows are the day's distinct start and end times, so a session covers the rows
    between its start and its end."""

    def __init__(self, date, sessions):
        self.date, self.sessions = date, sessions

    def __iter__(self):  # {% for day, sessions in days %} keeps working
        return iter((self.date, self.sessions))

    def grid(self):
        """Lanes as columns (not rooms: a room may change during the day). A lane whose sessions
        are all in one room is headed by that room; otherwise each session names its own."""
        from . import lanes as lane_rules

        sessions = self.sessions
        spanning = {s.pk for s in sessions if self._spans(s)}
        others = [s for s in sessions if s.pk not in spanning]
        placed_lanes = lane_rules.assign([_Unspanned(s) for s in others])
        lane_of = {wrapped.session.pk: lane for wrapped, lane in placed_lanes.items()}
        used = sorted(set(lane_of.values()))
        column_of = {lane: n + 2 for n, lane in enumerate(used)}  # column 1 holds the times
        headings = []
        for lane in used:
            rooms = {s.location_id for s in others if lane_of[s.pk] == lane}
            first = next(s for s in others if lane_of[s.pk] == lane)
            headings.append(first.location.name if len(rooms) == 1 and first.location_id else "")
        times = sorted({s.start for s in sessions} | {s.end for s in sessions})
        row = {t: n + 2 for n, t in enumerate(times)}  # row 1 holds the headings
        placed = []
        for s in sessions:
            column = "2 / -1" if s.pk in spanning or not used else str(column_of[lane_of[s.pk]])
            placed.append(Placed(s, f"{row[s.start]} / {row[s.end]}", column))
        labels = [(t, row[t]) for t in times if any(s.start == t for s in sessions)]
        parts = sorted({s.part for s in sessions}, key=lambda part: (part.sort_order, part.pk))
        return {"columns": headings, "placed": placed, "labels": labels, "count": max(len(used), 1),
                "parts": parts, "named": any(headings)}

    def _spans(self, session) -> bool:
        from . import lanes as lane_rules

        if not lane_rules.spans(session):
            return False
        return not any(other is not session and other.overlaps(session) for other in self.sessions)


class _Unspanned:
    """A session as lanes.assign sees it, when it is drawn in a lane although it could span
    (a plenary session beside a session of another part)."""

    def __init__(self, session):
        self.session = session
        self.pk, self.date, self.start, self.end = session.pk, session.date, session.start, session.end
        self.kind, self.location_id, self.lane, self.plenary = "papers", session.location_id, session.lane, False
