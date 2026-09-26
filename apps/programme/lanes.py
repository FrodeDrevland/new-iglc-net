"""Parallel lanes: the columns a day's sessions are drawn in (the builder, the public grid).

A lane is not a room. A day has a number of lanes (how many sessions can run at the same time);
each session is drawn in one of them, and is given a room separately, which may change during
the day. Plenary sessions, and breaks and meals without a room, span every lane.

Pure functions on objects with date, start, end, kind, plenary, location_id and lane, so that the
migrations can use them too.
"""

from __future__ import annotations

SPANNING = {"break", "meal"}


def spans(session) -> bool:
    return bool(session.plenary) or (session.kind in SPANNING and not session.location_id)


def overlap(a, b) -> bool:
    return a.date == b.date and a.start < b.end and b.start < a.end


def assign(sessions) -> dict:
    """{session: lane} for one day's sessions that do not span: their own lane where they have one,
    else the lane their room last had, else the first lane free at that time."""
    placed = {}
    room_lane = {}
    ordered = sorted((s for s in sessions if not spans(s)), key=lambda s: (s.start, s.end, s.pk or 0))
    for s in ordered:
        if s.lane:
            placed[s] = s.lane
            if s.location_id:
                room_lane[s.location_id] = s.lane
    for s in ordered:
        if s in placed:
            continue
        busy = {lane for other, lane in placed.items() if overlap(other, s)}
        wanted = room_lane.get(s.location_id) if s.location_id else None
        lane = wanted if wanted and wanted not in busy else next(n for n in range(1, len(ordered) + 2) if n not in busy)
        placed[s] = lane
        if s.location_id:
            room_lane[s.location_id] = lane
    return placed
