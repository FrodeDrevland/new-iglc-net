"""Registration backing of papers (docs/programme.md, "Registration backing and confirmation").

The IGLC rule: every paper must be backed by a registered author, and one registration backs at
most two papers. Only paid registrations of the types that count (the technical/academic
conference) back papers. A backed paper is published even if it is not presented.

    import_registrations(programme, path)   the organisers' export (CSV or Excel), repeatable
    assess(programme)                       every paper's backing, found by matching
    send_requests / send_reminders / send_warnings   emails to the authors, in batches
    respond(presentation, ...)              the authors' answer through their link
    withdraw(submission, user)              a chief editor withdraws a paper
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.archive.management.commands.group_authors import fold

from .models import PaperPresentation, Programme, Registration, RegistrationType

LIMIT = 2  # papers per registration
EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def name_key(name: str) -> str:
    return " ".join(fold(name).split())


# ---------------------------------------------------------------- the organisers' export

COLUMNS = {
    "reference": ["registration id", "participant id", "id", "registration number", "booking id", "order id"],
    "name": ["name", "full name", "participant", "participant name", "attendee", "attendee name"],
    "first": ["first name", "firstname", "given name", "forename"],
    "last": ["last name", "lastname", "surname", "family name"],
    "email": ["email", "e mail", "email address", "e mail address", "mail"],
    "type": ["registration type", "type", "ticket", "ticket type", "category", "registration category", "fee"],
    "paid": ["paid", "payment status", "payment", "status", "payment state"],
}
PAID = {"yes", "y", "paid", "true", "1", "x", "completed", "complete", "confirmed", "received", "ok"}


def _norm(heading) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(heading or "").lower()).strip()


def find_columns(headings) -> dict:
    by_norm = {_norm(h): h for h in headings}
    return {key: next((by_norm[n] for n in names if n in by_norm), None) for key, names in COLUMNS.items()}


@transaction.atomic
def import_registrations(programme: Programme, path) -> dict:
    """Create or update the registrations from an export. Registrations missing from it are kept
    but no longer count (inactive). Returns counts and the columns used."""
    from apps.production.conftool import read_table

    rows = read_table(path)
    if not rows:
        raise ValueError("The file has no rows.")
    columns = find_columns(rows[0].keys())
    if not columns["email"] or not (columns["name"] or columns["last"]):
        raise ValueError("No email or name column found among: " + ", ".join(rows[0].keys()))
    seen, created, updated = set(), 0, 0
    types = {t.name: t for t in programme.registration_types.all()}
    for row in rows:
        cell = lambda key: str(row.get(columns[key] or "", "") or "").strip()  # noqa: E731
        name = cell("name") or " ".join(filter(None, [cell("first"), cell("last")]))
        email = (EMAIL.search(cell("email")) or [""])[0] if cell("email") else ""
        if not name and not email:
            continue
        reference = cell("reference")
        key = reference or email.lower() or name_key(name)
        type_name = cell("type") or "Registration"
        if type_name not in types:
            types[type_name] = RegistrationType.objects.create(programme=programme, name=type_name)
        paid = _norm(cell("paid")) in PAID if columns["paid"] else True
        registration, is_new = Registration.objects.update_or_create(
            programme=programme, key=key[:200],
            defaults={"reference": reference[:100], "name": name[:300] or email, "email": email,
                      "type": types[type_name], "paid": paid, "active": True})
        seen.add(registration.pk)
        created += is_new
        updated += not is_new
    inactive = programme.registrations.filter(active=True).exclude(pk__in=seen).update(active=False)
    return {"created": created, "updated": updated, "inactive": inactive, "columns": columns,
            "no_paid_column": not columns["paid"]}


# ---------------------------------------------------------------- who backs which paper

@dataclass
class Backing:
    submission: object
    presentation: PaperPresentation | None
    authors: list[dict]                       # name, email
    candidates: list = field(default_factory=list)   # registrations that could back it
    unpaid: list = field(default_factory=list)       # registered authors who have not paid / wrong type
    registration: Registration | None = None
    status: str = ""                          # backed, over_limit, unpaid, none
    presenter_registered: bool | None = None

    LABELS = {"backed": "Backed", "over_limit": "Over the two-paper limit", "unpaid": "Registered, does not count yet",
              "none": "No registration"}

    @property
    def label(self):
        return self.LABELS[self.status]

    @property
    def answer(self):
        return self.presentation.answer if self.presentation else ""


def paper_authors(submission) -> list[dict]:
    """Name and email of each author: the published paper's, else as registered (ConfTool)."""
    registered = [{"name": a.get("name", ""), "email": (a.get("email") or "").strip().lower()}
                  for a in submission.registered_authors or [] if a.get("name")]
    if submission.paper_id:
        by_name = {name_key(a["name"]): a["email"] for a in registered}
        authors = []
        for a in submission.paper.authors.all():
            name = f"{a.first_name} {a.last_name}".strip()
            found = EMAIL.search(a.title_and_contact or "")
            email = (found.group(0).lower() if found else "") or by_name.get(name_key(name), "")
            authors.append({"name": name, "email": email})
        return authors
    return registered


def _index(programme):
    by_email, by_name = defaultdict(list), defaultdict(list)
    for r in programme.registrations.filter(active=True).select_related("type"):
        if r.email:
            by_email[r.email.lower()].append(r)
        by_name[name_key(r.name)].append(r)
    return by_email, by_name


def _registrations_of(author: dict, by_email, by_name) -> list[Registration]:
    found = list(by_email.get(author["email"], [])) if author.get("email") else []
    if not found:
        found = list(by_name.get(name_key(author["name"]), []))
    return found


def assess(programme: Programme) -> list[Backing]:
    """Every accepted paper (not withdrawn) with its backing, in ConfTool ID order.

    Registrations are assigned by a matching in which no registration backs more than LIMIT
    papers: an author on three papers is fine if a co-author backs one of them. An editors'
    choice, or the backer the authors named, is tried first."""
    from apps.production.models import Submission

    submissions = (Submission.objects.filter(production__conference=programme.conference)
                   .exclude(status=Submission.Status.WITHDRAWN)
                   .select_related("paper", "presentation__registration__type").prefetch_related("paper__authors")
                   .order_by("conftool_id"))
    by_email, by_name = _index(programme)
    rows = []
    for s in submissions:
        presentation = getattr(s, "presentation", None)
        authors = paper_authors(s)
        row = Backing(submission=s, presentation=presentation, authors=authors)
        preferred = []
        if presentation and presentation.registration_id and presentation.registration.counts:
            preferred = [presentation.registration]
        elif presentation and presentation.backer:
            named = {"name": presentation.backer, "email": (presentation.backer_email or "").lower()}
            if not named["email"]:
                named["email"] = next((a["email"] for a in authors if name_key(a["name"]) == name_key(named["name"])), "")
            preferred = [r for r in _registrations_of(named, by_email, by_name) if r.counts]
        seen = set()
        for r in preferred:
            seen.add(r.pk)
            row.candidates.append(r)
        for author in authors:
            for r in _registrations_of(author, by_email, by_name):
                if r.pk in seen:
                    continue
                seen.add(r.pk)
                (row.candidates if r.counts else row.unpaid).append(r)
        if presentation and presentation.backer_email:
            for r in by_email.get(presentation.backer_email.lower(), []):
                if r.pk not in seen and r.counts:
                    seen.add(r.pk)
                    row.candidates.append(r)
        rows.append(row)

    _match(rows)
    counting = {r.pk for rs in by_name.values() for r in rs if r.counts}
    for row in rows:
        if row.registration:
            row.status = "backed"
        elif row.candidates:
            row.status = "over_limit"
        elif row.unpaid:
            row.status = "unpaid"
        else:
            row.status = "none"
        presenter = row.presentation.presenter if row.presentation else ""
        if presenter and counting:
            email = next((a["email"] for a in row.authors if name_key(a["name"]) == name_key(presenter)), "")
            row.presenter_registered = any(r.pk in counting for r in
                                           _registrations_of({"name": presenter, "email": email}, by_email, by_name))
    return rows


def _match(rows: list[Backing]):
    """Kuhn's augmenting paths, each registration with LIMIT slots."""
    holders: dict[int, list[Backing]] = defaultdict(list)

    def place(row, visited) -> bool:
        for r in row.candidates:
            if r.pk in visited:
                continue
            visited.add(r.pk)
            if len(holders[r.pk]) < LIMIT:
                holders[r.pk].append(row)
                row.registration = r
                return True
            for other in list(holders[r.pk]):
                if place(other, visited):  # r is visited, so `other` moves to another registration
                    holders[r.pk].remove(other)
                    holders[r.pk].append(row)
                    row.registration = r
                    return True
        return False

    for row in sorted(rows, key=lambda r: len(r.candidates)):
        if row.candidates:
            place(row, set())


def backers(rows: list[Backing]) -> dict[int, list[Backing]]:
    """Registration id -> the papers it backs."""
    found = defaultdict(list)
    for row in rows:
        if row.registration:
            found[row.registration.pk].append(row)
    return found


# ---------------------------------------------------------------- emails

DEFAULT_REQUEST_SUBJECT = "IGLC{number}-{paper_id}: will your paper be presented, and who is registered?"
DEFAULT_REQUEST_BODY = """Dear author,

Your paper "{title}" (IGLC{number}-{paper_id}) is accepted for IGLC{number}.

Every paper must be backed by a registration for the technical/academic conference of one of its
authors, and one registration backs at most two papers. A backed paper is published in the
proceedings even if it is not presented.

Please tell us on this page whether the paper will be presented, by whom, and which author is
registered:

{link}

Please answer by {deadline}. One answer per paper is enough; the other authors have received this
message too.

With best regards,
The IGLC{number} scientific chairs
"""
DEFAULT_WARNING_SUBJECT = "IGLC{number}-{paper_id}: no registration backs your paper"
DEFAULT_WARNING_BODY = """Dear author,

We have not found a registration for the technical/academic conference of IGLC{number} that
backs your paper "{title}" (IGLC{number}-{paper_id}). One registration backs at most two papers.

If none of the authors is registered (and has paid) by {deadline}, the paper will be withdrawn from
the conference and the proceedings.

If an author has registered, please tell us who, and with which email address, on this page:

{link}

With best regards,
The IGLC{number} scientific chairs
"""


class _Values(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _link(presentation) -> str:
    return settings.SITE_URL + reverse("programme_public:confirm", args=[presentation.token])


def _values(programme, presentation) -> dict:
    submission = presentation.submission
    deadline = programme.author_deadline
    return _Values(number=programme.conference.number, paper_id=submission.conftool_id,
                   title=submission.paper.title if submission.paper_id else submission.title,
                   link=_link(presentation),
                   deadline=f"{deadline.day} {deadline:%B %Y}" if deadline else "the date given by the organisers")


def recipients(submission) -> list[str]:
    from apps.production.metadata_check import recipients as author_addresses

    return author_addresses(submission)


def _reply_to(programme) -> list[str]:
    from apps.production.models import ProductionEditor

    production = getattr(programme.conference, "production", None)
    if production is None:
        return []
    return [e.user.email for e in production.editors.filter(role=ProductionEditor.Role.CHIEF).select_related("user")
            if e.user.email]


def compose(programme, presentation, kind: str) -> EmailMessage:
    if kind == "warning":
        subject, body = (programme.warning_subject or DEFAULT_WARNING_SUBJECT,
                         programme.warning_body or DEFAULT_WARNING_BODY)
    else:
        subject, body = (programme.request_subject or DEFAULT_REQUEST_SUBJECT,
                         programme.request_body or DEFAULT_REQUEST_BODY)
        if kind == "reminder":
            subject = "Reminder: " + subject
    values = _values(programme, presentation)
    return EmailMessage(subject.format_map(values), body.format_map(values), to=presentation.recipients,
                        reply_to=_reply_to(programme))


def _presentation(submission) -> PaperPresentation:
    presentation, _ = PaperPresentation.objects.get_or_create(submission=submission)
    return presentation


def to_request(programme) -> list:
    return [row for row in assess(programme) if not (row.presentation and row.presentation.requested)]


def to_remind(programme) -> list:
    return [row for row in assess(programme)
            if row.presentation and row.presentation.requested and not row.presentation.answer]


def to_warn(programme) -> list:
    return [row for row in assess(programme) if row.status != "backed" and row.answer != "withdraw"]


def send_batch(programme, kind: str, user=None, n: int = 10, after: int = 0) -> dict:
    """Send one kind of email ("request", "reminder", "warning") to the next n papers after the
    ConfTool ID `after`. Called repeatedly by the page, so that no request takes long."""
    from apps.production.models import Event

    todo = {"request": to_request, "reminder": to_remind, "warning": to_warn}[kind](programme)
    todo = [row for row in todo if row.submission.conftool_id > after]
    batch, sent, problems = todo[:n], 0, []
    for row in batch:
        submission = row.submission
        addresses = recipients(submission)
        if not addresses:
            problems.append(f"{submission.conftool_id}: no email address for its authors")
            continue
        presentation = row.presentation or _presentation(submission)
        presentation.recipients = addresses
        try:
            compose(programme, presentation, kind).send()
        except Exception as error:  # noqa: BLE001 - reported, and can be sent again
            problems.append(f"{submission.conftool_id}: the email could not be sent ({error})")
            continue
        now = timezone.now()
        field_name = {"request": "requested", "reminder": "reminded", "warning": "warned"}[kind]
        setattr(presentation, field_name, now)
        presentation.save()
        Event.objects.create(submission=submission, user=user, action={
            "request": "authors asked to confirm the presentation and registration",
            "reminder": "authors reminded to confirm the presentation and registration",
            "warning": "authors warned: no registration backs the paper"}[kind], comment=", ".join(addresses))
        sent += 1
    return {"sent": sent, "left": len(todo) - len(batch),
            "next": batch[-1].submission.conftool_id if batch else after, "problems": problems}


# ---------------------------------------------------------------- the authors' answer

def respond(presentation: PaperPresentation, responder: str, answer: str, presenter: str = "", backer: str = "",
            backer_email: str = "", comment: str = ""):
    from apps.production.models import Event

    presentation.responder, presentation.responded = responder[:200], timezone.now()
    presentation.answer = answer
    presentation.presenter = presenter[:200] if answer == PaperPresentation.Answer.PRESENT else ""
    presentation.backer = backer[:200] if answer != PaperPresentation.Answer.WITHDRAW else ""
    presentation.backer_email = backer_email if answer != PaperPresentation.Answer.WITHDRAW else ""
    presentation.comment = comment
    presentation.save()
    submission = presentation.submission
    details = {"present": f"presented by {presentation.presenter}", "not_present": "published, not presented",
               "withdraw": "the authors withdraw the paper"}[answer]
    backed = f"; backed by {presentation.backer}" if presentation.backer else ""
    Event.objects.create(submission=submission, action=f"authors answered: {details}{backed}",
                         comment=f"{responder}{': ' + comment if comment else ''}")
    number = submission.production.conference.number
    title = submission.paper.title if submission.paper_id else submission.title
    text = (f"{responder} answered for the paper “{title}” (IGLC{number}-{submission.conftool_id}):\n\n"
            f"- {details}\n" + (f"- backed by {presentation.backer}"
                                f"{' (' + presentation.backer_email + ')' if presentation.backer_email else ''}\n"
                                if presentation.backer else "")
            + (f"\nComment: {comment}\n" if comment else "")
            + f"\nThe answer can be changed on the same page:\n{_link(presentation)}\n")
    others = presentation.recipients or recipients(submission)
    if others:
        EmailMessage(f"IGLC{number}-{submission.conftool_id}: your co-author's answer", text,
                     to=others).send(fail_silently=True)
    if answer == PaperPresentation.Answer.WITHDRAW or comment:
        editors = _reply_to(Programme.objects.get(conference=submission.production.conference))
        if editors:
            EmailMessage(f"IGLC{number}-{submission.conftool_id}: "
                         + ("the authors withdraw the paper" if answer == "withdraw" else "a comment from the authors"),
                         text, to=editors).send(fail_silently=True)
    return presentation


@transaction.atomic
def withdraw(submission, user, reason: str = "no registration backs the paper"):
    from apps.production.models import Event, Submission

    if submission.published_version_id or submission.paper_id:
        raise ValueError(f"{submission.conftool_id} is published: it cannot be withdrawn here.")
    submission.status = Submission.Status.WITHDRAWN
    submission.save(update_fields=["status"])
    Event.objects.create(submission=submission, user=user, action="withdrawn", comment=reason)
