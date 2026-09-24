"""The authors' check of their published metadata.

    send_next(production, user)    asks the authors of up to n published papers (one link per paper)
    remind_next(production, user)  sends the link again where nobody has answered
    respond(check, ...)            the authors' answer: all correct, or corrections
    apply(check, user)             the editors put the corrections into the published record

The published record is what is on the site and deposited with Crossref: title, the authors'
names, affiliations and ORCID iDs. The PDF is not changed: if the corrections concern what is
printed, the editors also publish a corrected version.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .docx_reader import orcid_checksum_ok, parse_affiliation
from .models import Event, MetadataCheck, ProductionEditor, Submission

EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
ORCID = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")
DAYS = 14


def published_record(paper) -> dict:
    authors = []
    for author in paper.authors.all():
        parsed = parse_affiliation(author.title_and_contact or "")
        authors.append({"first_name": author.first_name, "last_name": author.last_name,
                        "affiliation": parsed["affiliation"], "email": parsed["email"], "orcid": parsed["orcid"]})
    return {"title": paper.title, "authors": authors}


def recipients(submission: Submission) -> list[str]:
    """The authors' addresses: those registered (ConfTool), and those in the paper's footnotes."""
    found = [a.get("email", "") for a in submission.registered_authors or []]
    if submission.paper_id:
        found += [EMAIL.search(a.title_and_contact or "").group(0) if EMAIL.search(a.title_and_contact or "") else ""
                  for a in submission.paper.authors.all()]
    unique = {}
    for address in found:
        address = address.strip().rstrip(".")
        if address and "@" in address:
            unique.setdefault(address.lower(), address)
    return list(unique.values())


def _editor_addresses(production) -> list[str]:
    return [e.user.email for e in production.editors.filter(role=ProductionEditor.Role.CHIEF).select_related("user")
            if e.user.email]


def _link(check: MetadataCheck) -> str:
    return settings.SITE_URL + reverse("production:metadata_check", args=[check.token])


def _email(check: MetadataCheck, reminder: bool = False) -> EmailMessage:
    submission = check.submission
    conference = submission.production.conference
    paper = submission.paper
    subject = (f"{'Reminder: ' if reminder else ''}Please check your paper's details in the IGLC{conference.number} "
               f"proceedings (IGLC{conference.number}-{submission.conftool_id})")
    body = f"""Dear author,

Your paper "{paper.title}" is published in the proceedings of IGLC{conference.number}:
{settings.SITE_URL}{paper.get_absolute_url()}

Its DOI, https://doi.org/{paper.doi}, is registered with Crossref together with the paper's title,
its authors' names, affiliations and ORCID iDs. Please check them on this page, and either confirm
that they are correct or tell us what should be changed:

{_link(check)}

Please answer by {check.deadline.day} {check.deadline:%B %Y}. One answer per paper is enough; the other authors
have received this message too.

With best regards,
The editors of the IGLC{conference.number} proceedings
"""
    return EmailMessage(subject, body, to=check.recipients, reply_to=_editor_addresses(submission.production))


def _published(production):
    return (production.submissions.filter(paper__isnull=False).exclude(status=Submission.Status.WITHDRAWN)
            .select_related("paper", "production__conference").order_by("conftool_id"))


def pending(production) -> list[Submission]:
    """Published papers whose authors have not been asked yet."""
    return [s for s in _published(production) if not s.metadata_checks.exists()]


def send_next(production, user=None, n: int = 10, after: int = 0) -> dict:
    todo = [s for s in pending(production) if s.conftool_id > after]
    batch, sent, problems = todo[:n], 0, []
    for submission in batch:
        addresses = recipients(submission)
        if not addresses:
            problems.append(f"{submission.conftool_id}: no email address for its authors")
            continue
        check = MetadataCheck.objects.create(submission=submission, sent_by=user, recipients=addresses,
                                             deadline=timezone.localdate() + timedelta(days=DAYS))
        try:
            _email(check).send()
        except Exception as error:  # noqa: BLE001 - reported; the check is removed so it can be sent again
            check.delete()
            problems.append(f"{submission.conftool_id}: the email could not be sent ({error})")
            continue
        Event.objects.create(submission=submission, user=user, action="authors asked to check the metadata",
                             comment=", ".join(addresses))
        sent += 1
    return {"sent": sent, "left": len(todo) - len(batch), "next": batch[-1].conftool_id if batch else after,
            "problems": problems}


def remind_next(production, user=None, n: int = 10, after: int = 0) -> dict:
    todo = [c for c in MetadataCheck.objects.filter(submission__production=production, status=MetadataCheck.Status.SENT)
            .select_related("submission__paper", "submission__production__conference").order_by("submission__conftool_id")
            if c.submission.conftool_id > after]
    batch, sent, problems = todo[:n], 0, []
    for check in batch:
        check.deadline = max(check.deadline, timezone.localdate() + timedelta(days=7))
        try:
            _email(check, reminder=True).send()
        except Exception as error:  # noqa: BLE001
            problems.append(f"{check.submission.conftool_id}: the email could not be sent ({error})")
            continue
        check.reminded = timezone.now()
        check.save(update_fields=["deadline", "reminded"])
        sent += 1
    return {"sent": sent, "left": len(todo) - len(batch), "next": batch[-1].submission.conftool_id if batch else after,
            "problems": problems}


def clean_proposal(record: dict, data: dict) -> tuple[dict, list[str]]:
    """The proposed record, and what is wrong with it (ORCID iDs are checked)."""
    errors, authors = [], []
    for index, published in enumerate(record["authors"]):
        author = {key: (data.get(f"{key}_{index}", published[key]) or "").strip()
                  for key in ("first_name", "last_name", "affiliation", "orcid")}
        match = ORCID.search(author["orcid"])
        author["orcid"] = match.group(1) if match else ""
        if match and not orcid_checksum_ok(author["orcid"]):
            errors.append(f"The ORCID iD {author['orcid']} is not valid (its check digit does not match).")
        elif data.get(f"orcid_{index}", "").strip() and not match:
            errors.append(f"“{data.get(f'orcid_{index}')}” is not an ORCID iD (0000-0000-0000-0000).")
        if not author["last_name"]:
            errors.append("Every author needs a last name.")
        author["email"] = published["email"]
        authors.append(author)
    proposal = {"title": (data.get("title") or record["title"]).strip(), "authors": authors,
                "comment": (data.get("comment") or "").strip()}
    return proposal, errors


def differences(record: dict, proposal: dict) -> list[tuple[str, str, str]]:
    """(what, published, proposed) for everything that differs."""
    found = []
    if proposal.get("title") and proposal["title"] != record["title"]:
        found.append(("Title", record["title"], proposal["title"]))
    for index, (old, new) in enumerate(zip(record["authors"], proposal.get("authors", [])), 1):
        for key, label in (("first_name", "first name"), ("last_name", "last name"), ("affiliation", "affiliation"),
                           ("orcid", "ORCID")):
            if (old.get(key) or "") != (new.get(key) or ""):
                found.append((f"Author {index}, {label}", old.get(key) or "", new.get(key) or ""))
    return found


def respond(check: MetadataCheck, responder: str, confirmed: bool, proposal: dict | None = None):
    record = published_record(check.submission.paper)
    changes = differences(record, proposal or {}) if not confirmed else []
    comment = (proposal or {}).get("comment", "")
    check.responder, check.responded = responder[:200], timezone.now()
    check.proposal = proposal or {}
    check.status = MetadataCheck.Status.CONFIRMED if confirmed or not (changes or comment) else MetadataCheck.Status.CORRECTIONS
    check.save()
    Event.objects.create(submission=check.submission, action="authors " + (
        "confirmed the metadata" if check.status == MetadataCheck.Status.CONFIRMED else "proposed corrections"),
        comment=responder)
    if check.status == MetadataCheck.Status.CORRECTIONS:
        editors = _editor_addresses(check.submission.production)
        if editors:
            submission = check.submission
            number = submission.production.conference.number
            lines = "\n".join(f"- {what}: “{old}” → “{new}”" for what, old, new in changes)
            EmailMessage(
                f"IGLC{number}-{submission.conftool_id}: the authors propose corrections",
                f"{responder} proposes corrections to “{submission.paper.title}”:\n\n{lines or '(no field changed)'}"
                f"{chr(10) + chr(10) + 'Comment: ' + comment if comment else ''}\n\n"
                f"{settings.SITE_URL}{reverse('proceedings:paper', args=[number, submission.conftool_id])}\n",
                to=editors).send(fail_silently=True)
    return check


@transaction.atomic
def apply(check: MetadataCheck, user, note: str = "") -> list[tuple[str, str, str]]:
    """Put the proposed title, names, affiliations and ORCID iDs into the published record."""
    submission, paper = check.submission, check.submission.paper
    record = published_record(paper)
    changes = differences(record, check.proposal)
    if check.proposal.get("title"):
        paper.title = check.proposal["title"]
        paper.save(update_fields=["title"])
    edits = dict(submission.metadata_edits or {})
    names = dict(edits.get("names") or {})
    for author, new in zip(paper.authors.all(), check.proposal.get("authors", [])):
        old_name = f"{author.first_name} {author.last_name}".strip()
        if (author.first_name, author.last_name) != (new["first_name"], new["last_name"]):
            author.person = None  # the person is found again by name/ORCID
            names[old_name] = [new["first_name"], new["last_name"]]
        author.first_name, author.last_name = new["first_name"], new["last_name"]
        parts = [new["affiliation"], new.get("email", "")] + ([f"https://orcid.org/{new['orcid']}"] if new["orcid"] else [])
        author.title_and_contact = ", ".join(p for p in parts if p)
        author.save()
    edits["names"] = names
    submission.metadata_edits = edits
    submission.save(update_fields=["metadata_edits"])
    paper.refresh_authors_text()
    check.status, check.handled, check.handled_by, check.handled_note = (
        MetadataCheck.Status.HANDLED, timezone.now(), user, note)
    check.save()
    Event.objects.create(submission=submission, user=user, action="authors' corrections applied to the record",
                         comment="; ".join(f"{w}: {n}" for w, _, n in changes)[:1000])
    return changes


def close(check: MetadataCheck, user, note: str):
    check.status, check.handled, check.handled_by, check.handled_note = (
        MetadataCheck.Status.HANDLED, timezone.now(), user, note)
    check.save()
    Event.objects.create(submission=check.submission, user=user, action="authors' corrections handled", comment=note)
