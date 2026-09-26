"""Checks across a programme's sessions, shown to its editors (docs/programme.md).

Errors must be fixed before the programme is final; warnings and notes are for the editors to
judge. The checks never block saving: while sessions are being moved, clashes come and go.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from apps.archive.management.commands.group_authors import fold

from .models import PaperPresentation, Session, SessionItem

ERROR, WARNING, NOTE = "error", "warning", "note"


@dataclass
class Problem:
    level: str
    text: str
    sessions: list = field(default_factory=list)


def _key(name: str) -> str:
    return " ".join(fold(name).split())


def _sessions(programme):
    return list(programme.sessions.select_related("location", "part", "keynote")
                .prefetch_related("people", "items__submission__paper__authors"))


def _pairs(sessions):
    by_date = defaultdict(list)
    for s in sessions:
        by_date[s.date].append(s)
    for day in by_date.values():
        day.sort(key=lambda s: s.start)
        for i, a in enumerate(day):
            for b in day[i + 1:]:
                if b.start >= a.end:
                    break
                yield a, b


def problems(programme) -> list[Problem]:
    sessions = _sessions(programme)
    found: list[Problem] = []

    for a, b in _pairs([s for s in sessions if not s.cancelled]):
        if a.location_id and a.location_id == b.location_id:
            found.append(Problem(ERROR, f"Two sessions in {a.location} at the same time.", [a, b]))
        if a.part_id == b.part_id and (a.plenary or b.plenary):
            plenary, other = (a, b) if a.plenary else (b, a)
            found.append(Problem(WARNING, f"{other.display_title} runs in parallel with the plenary "
                                          f"{plenary.display_title}.", [plenary, other]))
        people_a, people_b = _people(a), _people(b)
        for key in sorted(people_a.keys() & people_b.keys()):
            found.append(Problem(WARNING, f"{people_a[key][0]} is in two sessions at the same time "
                                          f"({people_a[key][1]} and {people_b[key][1]}).", [a, b]))

    for s in sessions:
        chairs = {_key(p.name) for p in s.people.all() if p.role in ("chair", "co_chair")}
        for item in s.items.all():
            if item.presenter and _key(item.presenter) in chairs:
                found.append(Problem(NOTE, f"{item.presenter} chairs the session and presents in it: "
                                           f"a co-chair could chair that paper.", [s]))
            if item.submission_id and item.presenter:
                authors = {_key(n) for n in item.author_names()}
                if _key(item.presenter) not in authors:
                    found.append(Problem(WARNING, f"{item.presenter} is not an author of "
                                                  f"“{item.display_title}”.", [s]))
            if item.submission_id is None and item.contribution_id is None and not item.title:
                found.append(Problem(ERROR, "An item with neither paper nor title.", [s]))
        planned = sum(i.minutes or 0 for i in s.items.all())
        if planned > s.minutes:
            found.append(Problem(WARNING, f"The items take {planned} minutes; the session has {s.minutes}.", [s]))
        if s.kind in Session.WITH_PAPERS and not s.items.all():
            found.append(Problem(NOTE, "No papers yet.", [s]))

    roomless = [s for s in sessions if not s.location_id and s.kind not in (Session.Kind.BREAK, Session.Kind.MEAL)
                and not s.cancelled]
    if roomless:
        found.append(Problem(NOTE, f"{len(roomless)} session{'s have' if len(roomless) != 1 else ' has'} "
                                   f"no room yet.", roomless[:12]))
    found += paper_problems(programme)
    order = {ERROR: 0, WARNING: 1, NOTE: 2}
    return sorted(found, key=lambda p: order[p.level])


def _people(session) -> dict[str, tuple[str, str]]:
    """Folded name -> (name, what they do in the session)."""
    people = {}
    for p in session.people.all():
        people[_key(p.name)] = (p.name, f"{p.get_role_display().lower()} of {session.code or session.display_title}")
    for item in session.items.all():
        if item.presenter:
            people.setdefault(_key(item.presenter),
                              (item.presenter, f"presenting in {session.code or session.display_title}"))
    return people


def paper_problems(programme) -> list[Problem]:
    from apps.production.models import Submission

    found = []
    items = (SessionItem.objects.filter(session__programme=programme, submission__isnull=False)
             .select_related("submission", "session"))
    by_paper = defaultdict(list)
    for item in items:
        by_paper[item.submission_id].append(item)
    answers = {p.submission_id: p for p in PaperPresentation.objects.filter(submission_id__in=by_paper.keys())}
    for placed in by_paper.values():
        submission = placed[0].submission
        answer = answers.get(submission.pk)
        if answer and answer.answer in (PaperPresentation.Answer.NOT_PRESENT, PaperPresentation.Answer.WITHDRAW):
            found.append(Problem(WARNING, f"The authors of paper {submission.conftool_id} say: "
                                          f"{answer.get_answer_display().lower()}.", [i.session for i in placed]))
        elif answer and answer.presenter:
            for item in placed:
                if item.presenter and _key(item.presenter) != _key(answer.presenter):
                    found.append(Problem(WARNING, f"Paper {submission.conftool_id}: the authors say {answer.presenter} "
                                                  f"presents, the session says {item.presenter}.", [item.session]))
        if len(placed) > 1:
            found.append(Problem(ERROR, f"Paper {submission.conftool_id} is placed {len(placed)} times.",
                                 [i.session for i in placed]))
        if submission.status == Submission.Status.WITHDRAWN:
            found.append(Problem(ERROR, f"Paper {submission.conftool_id} is withdrawn but still in the programme.",
                                 [i.session for i in placed]))
    missing = len(unplaced(programme))
    if missing:
        found.append(Problem(NOTE, f"{missing} paper{'s' if missing != 1 else ''} not placed in a session yet."))
    return found


def unplaced(programme):
    """Papers of the conference (not withdrawn) that are in no session, leaving out those whose
    authors say they will not be presented."""
    from apps.production.models import Submission

    return (Submission.objects.filter(production__conference=programme.conference)
            .exclude(status=Submission.Status.WITHDRAWN)
            .exclude(programme_items__session__programme=programme)
            .exclude(presentation__answer__in=[PaperPresentation.Answer.NOT_PRESENT, PaperPresentation.Answer.WITHDRAW])
            .select_related("track").order_by("track__order", "position", "conftool_id"))
