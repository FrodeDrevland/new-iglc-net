"""The programme builder: one day at a time, sessions drawn as blocks in a grid of rooms by time,
and papers and contributions dragged into them (templates/programme/builder.html,
static/js/programme-builder.js). The page talks to this module through one JSON address:

    state(programme, user, day)          what the page draws
    apply(programme, user, day, data)    one change; returns the new state, or raises BuildError

Every change is checked like the forms (the model's clean) and the permissions (access.py): a
person changes only the sessions of the parts they edit, and rooms only if they keep the rooms.
"""

from __future__ import annotations

from datetime import date as Date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from . import access, checks, lanes
from .models import Contribution, Location, Part, Session, SessionItem, SessionPerson

STEP = 15  # minutes
SPANNING_KINDS = {Session.Kind.BREAK, Session.Kind.MEAL}
PARALLEL_KINDS = {Session.Kind.PAPERS, Session.Kind.POSTERS, Session.Kind.WORKSHOP, Session.Kind.INDUSTRY,
                  Session.Kind.PANEL}
PREFIX = {Part.Kind.ACADEMIC: "", Part.Kind.INDUSTRY: "I", Part.Kind.WORKSHOP: "W", Part.Kind.PHD: "P",
          Part.Kind.OTHER: "X"}


class BuildError(Exception):
    pass


def _hm(value: time) -> str:
    return value.strftime("%H:%M")


def _time(text) -> time:
    try:
        hours, minutes = (int(x) for x in str(text).split(":")[:2])
        return time(hours, minutes)
    except (TypeError, ValueError):
        raise BuildError(f"Not a time: {text}")


def _date(text) -> Date:
    try:
        return Date.fromisoformat(str(text))
    except ValueError:
        raise BuildError(f"Not a date: {text}")


def _messages(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        return " ".join(m for messages in error.message_dict.values() for m in messages)
    return " ".join(error.messages)


# ---------------------------------------------------------------- what the page draws

def days_of(programme) -> list[Date]:
    return programme.days()


def _item_json(item) -> dict:
    if item.submission_id:
        entry = f"s{item.submission_id}"
        sub = ", ".join(item.author_names())
        label = f"{item.submission.conftool_id}"
    elif item.contribution_id:
        entry = f"c{item.contribution_id}"
        sub = item.contribution.speakers
        label = item.contribution.get_kind_display()
    else:
        entry, sub, label = f"i{item.pk}", item.speaker, ""
    return {"id": item.pk, "entry": entry, "label": label, "title": item.display_title, "sub": sub,
            "presenter": item.presenter, "minutes": item.minutes, "presentation": item.presentation,
            "paper": bool(item.submission_id)}


def _pool(programme) -> dict:
    papers = [{"entry": f"s{s.pk}", "label": str(s.conftool_id), "title": s.title,
               "sub": ", ".join(a.get("name", "") for a in s.registered_authors if a.get("name")),
               "track": s.track.title if s.track_id else "", "track_id": s.track_id or ""}
              for s in checks.unplaced(programme).select_related("track")]
    contributions = [{"entry": f"c{c.pk}", "label": c.get_kind_display(), "title": c.title, "sub": c.speakers,
                      "part": c.part_id, "kind": c.kind, "minutes": c.minutes}
                     for c in programme.contributions.filter(programme_items__isnull=True).select_related("part")]
    return {"papers": papers, "contributions": contributions}


def spans(session, day_sessions=None) -> bool:
    """Drawn across every lane: plenary sessions, and breaks and meals without a room of their own."""
    return lanes.spans(session)


def _fill_lanes(programme, day):
    """Sessions of the day without a lane (from the form, a spreadsheet, a copy) get one."""
    sessions = list(programme.sessions.filter(date=day))
    for session, lane in lanes.assign(sessions).items():
        if session.lane != lane:
            Session.objects.filter(pk=session.pk).update(lane=lane)


def state(programme, user, day: Date) -> dict:
    editable = {p.pk for p in access.editable_parts(user, programme)}
    _fill_lanes(programme, day)
    sessions = list(programme.sessions.filter(date=day).select_related("location", "part", "track")
                    .prefetch_related("people", "items__submission__paper__authors", "items__contribution"))
    flagged = {}
    for problem in checks.problems(programme):
        if problem.level == checks.NOTE:
            continue
        for s in problem.sessions:
            if s.date == day:
                flagged.setdefault(s.pk, []).append(problem.text)
    times = [s.start for s in sessions] + [s.end for s in sessions]
    first = min([t.hour for t in times] + [8])
    last = max([t.hour + (1 if t.minute else 0) for t in times] + [18])
    return {
        "day": day.isoformat(),
        "days": [{"date": d.isoformat(), "label": f"{d:%a} {d.day} {d:%b}",
                  "count": programme.sessions.filter(date=d).count(),
                  "parts": [p.pk for p in programme.day_parts(d)]} for d in days_of(programme)],
        "day_parts": [p.pk for p in programme.day_parts(day)],
        "can_days": access.can_edit_settings(user, programme),
        "range": {"start": f"{max(first - 1, 0):02d}:00", "end": f"{min(last + 1, 24):02d}:00"},
        "rooms": [{"id": loc.pk, "name": loc.name} for loc in programme.locations.all()],
        "lanes": programme.day_lanes(day),
        "can_rooms": access.can_edit_locations(user, programme),
        "parts": [{"id": p.pk, "name": p.name, "colour": p.colour, "kind": p.kind, "editable": p.pk in editable}
                  for p in programme.parts.all()],
        "kinds": [[k, label] for k, label in Session.Kind.choices],
        "contribution_kinds": [[k, label] for k, label in Contribution.Kind.choices],
        "roles": [[k, label] for k, label in SessionPerson.Role.choices],
        "tracks": [{"id": t.pk, "title": t.title} for t in programme.conference.tracks.all()],
        "sessions": [{
            "id": s.pk, "part": s.part_id, "kind": s.kind, "kind_label": s.get_kind_display(), "code": s.code,
            "title": s.title, "display": s.display_title, "start": _hm(s.start), "end": _hm(s.end),
            "location": s.location_id, "room": s.location.name if s.location_id else "",
            "lane": s.lane, "plenary": s.plenary, "spans": spans(s, sessions),
            "editable": s.part_id in editable, "cancelled": s.cancelled, "change_note": s.change_note,
            "notes": s.notes, "track": s.track_id or "",
            "people": [{"role": p.role, "name": p.name, "affiliation": p.affiliation} for p in s.people.all()],
            "items": [_item_json(i) for i in s.items.all()],
            "problems": flagged.get(s.pk, []),
        } for s in sessions],
        "pool": _pool(programme),
    }


# ---------------------------------------------------------------- changes

def _editable_part(user, programme, part_id) -> Part:
    part = programme.parts.filter(pk=part_id).first()
    if part is None or not access.can_edit_part(user, part):
        raise BuildError("You cannot edit that part of the programme.")
    return part


def _session(user, programme, session_id) -> Session:
    session = programme.sessions.select_related("part").filter(pk=session_id).first()
    if session is None:
        raise BuildError("That session no longer exists. Reload the page.")
    if not access.can_edit_part(user, session.part):
        raise BuildError("That session belongs to a part you do not edit.")
    return session


def _save(session):
    try:
        session.full_clean()
    except ValidationError as error:
        raise BuildError(_messages(error))
    session.save()


def _location(programme, value):
    if value in (None, "", "null"):
        return None
    location = programme.locations.filter(pk=value).first()
    if location is None:
        raise BuildError("Unknown room.")
    return location


def _day_part(user, programme, day, wanted=None) -> Part:
    """The part a session on this day belongs to: the day's own, or the one chosen among the day's
    parts when it has several."""
    parts = programme.day_parts(day)
    if wanted not in (None, ""):
        part = next((p for p in parts if str(p.pk) == str(wanted)), None)
        if part is None:
            raise BuildError(f"{day:%A %d %B} belongs to {' and '.join(p.name for p in parts)}.")
        if not access.can_edit_part(user, part):
            raise BuildError(f"You do not edit the {part.name.lower()}.")
    else:
        part = next((p for p in parts if access.can_edit_part(user, p)), parts[0] if parts else None)
    if part is None or not access.can_edit_part(user, part):
        raise BuildError(f"{day:%A %d %B} belongs to {' and '.join(p.name for p in parts)}, "
                         f"which you do not edit.")
    return part


def create(programme, user, day, data) -> list[Session]:
    part = _day_part(user, programme, day, data.get("part"))
    kind = data.get("kind") or Session.Kind.PAPERS
    if kind not in Session.Kind.values:
        raise BuildError("Unknown kind of session.")
    start, end = _time(data.get("start")), _time(data.get("end"))
    mode = data.get("mode", "lane")
    base = dict(programme=programme, part=part, date=day, start=start, end=end, kind=kind,
                title=(data.get("title") or "").strip()[:300])
    if mode == "parallel":  # one in every lane that is free at that time
        probe = Session(date=day, start=start, end=end)
        busy = {o.lane for o in programme.sessions.filter(date=day) if o.lane and o.overlaps(probe)}
        made = []
        for lane in range(1, programme.day_lanes(day) + 1):
            if lane in busy:
                continue
            session = Session(lane=lane, **base)
            _save(session)
            made.append(session)
        if not made:
            raise BuildError("Every lane is taken at that time: add a lane first.")
        return made
    location = _location(programme, data.get("location"))
    plenary = mode == "all" and kind not in SPANNING_KINDS
    lane = None if mode == "all" else _lane(programme, day, data.get("lane"))
    session = Session(location=location, plenary=plenary, lane=lane, **base)
    _save(session)
    return [session]


def _lane(programme, day, value):
    try:
        lane = int(value)
    except (TypeError, ValueError):
        return None
    if not 1 <= lane <= programme.day_lanes(day):
        raise BuildError("No such lane.")
    return lane


FIELDS = {"title", "code", "kind", "notes", "change_note"}


def update(programme, user, data):
    from django.utils import timezone

    session = _session(user, programme, data.get("id"))
    before = (session.cancelled, session.change_note)
    for name in FIELDS & data.keys():
        setattr(session, name, (data[name] or "").strip() if isinstance(data[name], str) else data[name])
    if "start" in data:
        session.start = _time(data["start"])
    if "end" in data:
        session.end = _time(data["end"])
    if "date" in data:
        session.date = _date(data["date"])
    if "location" in data:
        session.location = _location(programme, data["location"])
    if "lane" in data:
        session.lane = _lane(programme, session.date, data["lane"])
    if "plenary" in data:
        session.plenary = bool(data["plenary"])
    if "cancelled" in data:
        session.cancelled = bool(data["cancelled"])
    if "track" in data:
        session.track = programme.conference.tracks.filter(pk=data["track"]).first() if data["track"] else None
    if "part" in data and str(data["part"]) != str(session.part_id):
        session.part = _day_part(user, programme, session.date, data["part"])
    elif session.part not in programme.day_parts(session.date):  # moved to a day of another part
        session.part = _day_part(user, programme, session.date)
    if (session.cancelled, session.change_note) != before and (session.cancelled or session.change_note):
        session.changed = timezone.now()
    _save(session)
    if "people" in data:
        session.people.all().delete()
        for order, person in enumerate(data["people"] or [], start=1):
            name = (person.get("name") or "").strip()
            if name:
                role = person.get("role") if person.get("role") in SessionPerson.Role.values else "chair"
                SessionPerson.objects.create(session=session, role=role, name=name[:200],
                                             affiliation=(person.get("affiliation") or "").strip()[:300], order=order)
    return session


def place(programme, user, data):
    """Put a paper (s<id>), a contribution (c<id>) or an existing item (i<id>) into a session at a position."""
    from .models import PaperPresentation

    session = _session(user, programme, data.get("session"))
    entry = str(data.get("entry", ""))
    kind, pk = entry[:1], entry[1:]
    if not pk.isdigit():
        raise BuildError("Unknown item.")
    pk = int(pk)
    item = None
    if kind == "i":
        item = SessionItem.objects.select_related("session__part").filter(pk=pk, session__programme=programme).first()
    elif kind == "s":
        item = SessionItem.objects.select_related("session__part").filter(
            submission_id=pk, session__programme=programme).first()
        if item is None:
            submission = checks.unplaced(programme).filter(pk=pk).first()
            if submission is None:
                raise BuildError("That paper is withdrawn, or no longer in the list.")
            answer = PaperPresentation.objects.filter(submission=submission).first()
            item = SessionItem(submission=submission, presenter=answer.presenter if answer else "")
    elif kind == "c":
        contribution = programme.contributions.filter(pk=pk).first()
        if contribution is None:
            raise BuildError("That contribution no longer exists.")
        item = contribution.programme_items.select_related("session__part").first() or SessionItem(
            contribution=contribution, minutes=contribution.minutes)
    if item is None:
        raise BuildError("Unknown item.")
    if item.pk and not access.can_edit_part(user, item.session.part):
        raise BuildError("That item is in a session you do not edit.")
    if item.submission_id:
        item.presentation = (SessionItem.Presentation.POSTER if session.kind == Session.Kind.POSTERS
                             else SessionItem.Presentation.TALK)
    item.session = session
    others = [i for i in session.items.exclude(pk=item.pk or 0).order_by("order", "pk")]
    index = max(0, min(int(data.get("index", len(others)) or 0), len(others)))
    others.insert(index, item)
    for order, each in enumerate(others, start=1):
        each.order = order
        each.save()


# A contribution dropped where there is no session gets a session of its own, as long as the
# contribution: its kind follows the contribution's, and the ones for everyone span the lanes.
SESSION_FOR = {Contribution.Kind.KEYNOTE: Session.Kind.KEYNOTE, Contribution.Kind.WORKSHOP: Session.Kind.WORKSHOP,
               Contribution.Kind.PANEL: Session.Kind.PANEL}
FOR_EVERYONE = {Contribution.Kind.WELCOME, Contribution.Kind.KEYNOTE, Contribution.Kind.AWARDS,
                Contribution.Kind.CLOSING}
DEFAULT_MINUTES = 60


def session_for(programme, user, day, data) -> Session:
    """A new session for a contribution dropped at a time (and lane) where there is none."""
    entry = str(data.get("entry", ""))
    if entry[:1] != "c" or not entry[1:].isdigit():
        raise BuildError("Only contributions get a session of their own; drop papers into a session.")
    contribution = programme.contributions.select_related("part").filter(pk=int(entry[1:])).first()
    if contribution is None:
        raise BuildError("That contribution no longer exists.")
    if contribution.programme_items.exists():
        raise BuildError("That contribution is already in a session.")
    parts = programme.day_parts(day)
    wanted = contribution.part_id if contribution.part in parts else None
    part = _day_part(user, programme, day, wanted)
    start = _time(data.get("start"))
    minutes = contribution.minutes or DEFAULT_MINUTES
    ends = datetime.combine(day, start) + timedelta(minutes=minutes)
    if ends.date() != day:
        raise BuildError("The session would end after midnight.")
    kind = SESSION_FOR.get(contribution.kind)
    if kind is None:
        kind = Session.Kind.INDUSTRY if part.kind == Part.Kind.INDUSTRY and contribution.kind == "talk" else Session.Kind.OTHER
    plenary = contribution.kind in FOR_EVERYONE
    session = Session(programme=programme, part=part, date=day, start=start, end=ends.time(), kind=kind,
                      title=contribution.title[:300], plenary=plenary,
                      lane=None if plenary else _lane(programme, day, data.get("lane")))
    for other in programme.sessions.filter(date=day, cancelled=False):
        if other.overlaps(session) and (plenary or lanes.spans(other) or other.lane in (None, session.lane)):
            raise BuildError(f"{other.display_title} is already there at {_hm(other.start)}–{_hm(other.end)}.")
    _save(session)
    SessionItem.objects.create(session=session, contribution=contribution, minutes=contribution.minutes, order=1)
    return session


def unplace(programme, user, data):
    item = SessionItem.objects.select_related("session__part").filter(pk=data.get("item"),
                                                                     session__programme=programme).first()
    if item is None:
        return
    if not access.can_edit_part(user, item.session.part):
        raise BuildError("That item is in a session you do not edit.")
    item.delete()


def item_details(programme, user, data):
    item = SessionItem.objects.select_related("session__part").filter(pk=data.get("item"),
                                                                     session__programme=programme).first()
    if item is None or not access.can_edit_part(user, item.session.part):
        raise BuildError("That item is in a session you do not edit.")
    if "presenter" in data:
        item.presenter = (data["presenter"] or "").strip()[:200]
    if "minutes" in data:
        item.minutes = int(data["minutes"]) if str(data["minutes"] or "").isdigit() else None
    item.save()


def add_room(programme, user, data):
    if not access.can_edit_locations(user, programme):
        raise BuildError("Only the organisers and the conference chairs add rooms.")
    name = (data.get("name") or "").strip()
    if not name:
        raise BuildError("Give the room a name.")
    last = programme.locations.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    Location.objects.create(programme=programme, name=name[:200], sort_order=last + 1)


def copy_day(programme, user, source: Date, target: Date, replace: bool = False) -> int:
    """The sessions of the parts one edits, without their papers and people, to another day."""
    parts = access.editable_parts(user, programme)
    if not (programme.first_day <= target <= programme.last_day):
        raise BuildError("That day is outside the programme's days.")
    from .models import ProgrammeDay

    target_parts = programme.day_parts(target)
    if not programme.days_set.filter(date=target).exists() and not programme.sessions.filter(date=target).exists():
        # an empty day that was never set takes the parts of the day it is copied from
        target_parts = programme.day_parts(source)
        ProgrammeDay.objects.get_or_create(programme=programme, date=target)[0].parts.set(target_parts)
    if replace:
        programme.sessions.filter(date=target, part__in=parts).delete()
    count = 0
    for s in programme.sessions.filter(date=source, part__in=parts):
        part = s.part if s.part in target_parts else next((p for p in target_parts if p in parts), None)
        if part is None:
            raise BuildError(f"{target:%A %d %B} belongs to {' and '.join(p.name for p in target_parts)}, "
                             f"which you do not edit.")
        copy = Session(programme=programme, part=part, date=target, start=s.start, end=s.end, location=s.location,
                       kind=s.kind, title=s.title, plenary=s.plenary, track=s.track, lane=s.lane)
        _save(copy)
        count += 1
    return count


def set_day_parts(programme, user, day, part_ids) -> str:
    """What the day belongs to (the conference chairs). A part that still has sessions on the day
    cannot be taken off it."""
    from .models import ProgrammeDay

    if not access.can_edit_settings(user, programme):
        raise BuildError("Only the conference chairs decide what a day belongs to.")
    parts = list(programme.parts.filter(pk__in=[p for p in part_ids or [] if str(p).isdigit()]))
    if not parts:
        raise BuildError("A day belongs to at least one part.")
    busy = [p for p in programme.parts.filter(sessions__date=day).distinct() if p not in parts]
    if busy:
        raise BuildError(f"The {busy[0].name.lower()} still has sessions on this day: move or delete them first.")
    ProgrammeDay.objects.get_or_create(programme=programme, date=day)[0].parts.set(parts)
    return f"{day:%A %d %B}: {' and '.join(p.name for p in parts)}."


def set_lanes(programme, user, day, count) -> str:
    """How many parallel lanes the day has (anyone who edits the day)."""
    from .models import ProgrammeDay

    if not any(access.can_edit_part(user, p) for p in programme.day_parts(day)):
        raise BuildError("You do not edit this day.")
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise BuildError("Not a number.")
    used = max([s.lane or 0 for s in programme.sessions.filter(date=day)] + [0])
    if count < max(used, 1):
        raise BuildError(f"Lane {used} still has sessions: move them first.")
    if count > 12:
        raise BuildError("At most twelve lanes.")
    row, _ = ProgrammeDay.objects.get_or_create(programme=programme, date=day)
    row.lanes = count
    row.save(update_fields=["lanes"])
    return f"{count} parallel lanes on {day:%A %d %B}."


def lane_room(programme, user, day, lane, location_id) -> str:
    """Give a room to the sessions of a lane on the day that have none yet (and that one edits).
    Sessions that already have a room keep it: rooms may change during the day."""
    location = _location(programme, location_id)
    if location is None:
        raise BuildError("Choose a room.")
    count = 0
    for s in programme.sessions.filter(date=day, lane=lane, location__isnull=True).select_related("part"):
        if access.can_edit_part(user, s.part):
            s.location = location
            _save(s)
            count += 1
    return f"{location} given to {count} session{'s' if count != 1 else ''} without a room."


def renumber(programme, user) -> int:
    """Codes by time slot, per part: 1A, 1B ... in lane order; the industry day I1A, the workshop day
    W1A and so on. Only sessions that run beside others get a code; plenary sessions and breaks lose it."""
    changed = 0
    for part in access.editable_parts(user, programme):
        sessions = list(part.sessions.select_related("location").order_by("date", "start", "lane", "pk"))
        slots = []
        for s in sessions:
            parallel = (not s.plenary and s.kind not in SPANNING_KINDS
                        and (s.kind in PARALLEL_KINDS or any(o is not s and o.overlaps(s) for o in sessions)))
            if not parallel:
                code = ""
            else:
                key = (s.date, s.start)
                if key not in slots:
                    slots.append(key)
                letters = [o for o in sessions if (o.date, o.start) == key and not o.plenary
                           and o.kind not in SPANNING_KINDS]
                letter = chr(ord("A") + letters.index(s)) if len(letters) > 1 else ""
                code = f"{PREFIX.get(part.kind, '')}{slots.index(key) + 1}{letter}"
            if s.code != code:
                Session.objects.filter(pk=s.pk).update(code=code)
                changed += 1
    return changed


@transaction.atomic
def apply(programme, user, day: Date, data: dict) -> dict:
    if access.is_frozen(programme) and not user.is_superuser:
        raise BuildError("The conference has taken place: the programme is frozen.")
    action = data.get("action")
    note = ""
    if action == "create":
        made = create(programme, user, day, data)
        note = f"{len(made)} session{'s' if len(made) != 1 else ''} added."
    elif action == "update":
        update(programme, user, data)
    elif action == "delete":
        _session(user, programme, data.get("id")).delete()
        note = "Session deleted."
    elif action == "place":
        place(programme, user, data)
    elif action == "new_session":
        made = session_for(programme, user, day, data)
        minutes = (made.items.first().contribution.minutes or 0)
        note = (f"Session added, {_hm(made.start)}–{_hm(made.end)}."
                + ("" if minutes else f" The contribution has no length, so it got {DEFAULT_MINUTES} minutes."))
    elif action == "unplace":
        unplace(programme, user, data)
    elif action == "item":
        item_details(programme, user, data)
    elif action == "room":
        add_room(programme, user, data)
    elif action == "copy_day":
        count = copy_day(programme, user, day, _date(data.get("to")), bool(data.get("replace")))
        note = f"{count} session{'s' if count != 1 else ''} copied to {_date(data.get('to')):%A %d %B}."
    elif action == "lanes":
        note = set_lanes(programme, user, day, data.get("count"))
    elif action == "lane_room":
        note = lane_room(programme, user, day, _lane(programme, day, data.get("lane")), data.get("location"))
    elif action == "day_parts":
        note = set_day_parts(programme, user, day, data.get("parts"))
    elif action == "renumber":
        note = f"{renumber(programme, user)} codes changed."
    elif action == "contribution":
        part = _editable_part(user, programme, data.get("part"))
        contribution = Contribution(programme=programme, part=part, kind=data.get("kind") or "talk",
                                    title=(data.get("title") or "").strip()[:300],
                                    speakers=(data.get("speakers") or "").strip()[:300],
                                    minutes=int(data["minutes"]) if str(data.get("minutes") or "").isdigit() else None)
        try:
            contribution.full_clean()
        except ValidationError as error:
            raise BuildError(_messages(error))
        contribution.save()
        note = "Added to the list."
    else:
        raise BuildError("Unknown action.")
    result = state(programme, user, day)
    result["note"] = note
    return result
