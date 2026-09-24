"""Publishing the papers (stage 1): into the archive, with DOIs, page numbers and running heads.

    problems = readiness(production)        -> what stops publication (empty when ready)
    publish_next(production, user, n=10)    -> publishes up to n papers not yet published
    finish(production, user)                -> freezes the page numbers, shows the conference, builds the ZIP
    correct(submission, user, note)         -> publishes the current version of a published paper

Publishing is repeatable: a paper already published is left alone, so a batch that was cut
short is simply run again.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.archive.models import Author, Paper

from .arrange import number_pages
from .models import Correction, Event, Production, Submission, private_storage

FONT_FILES = ("times.ttf", "timesi.ttf", "timesbd.ttf")


class PublishError(Exception):
    pass


# ---------------------------------------------------------------- fonts

def fonts_folder() -> Path:
    """Times New Roman for the running heads. The fonts are licensed, so they are not in the
    repository: they are looked for in PRODUCTION_FONTS_DIR, then in private storage (fonts/)."""
    folder = Path(getattr(settings, "PRODUCTION_FONTS_DIR", settings.BASE_DIR / "_fonts"))
    if all((folder / name).exists() for name in FONT_FILES):
        return folder
    cache = Path(tempfile.gettempdir()) / "iglc-fonts"
    if all((cache / name).exists() for name in FONT_FILES):
        return cache
    storage = private_storage()
    if all(storage.exists(f"fonts/{name}") for name in FONT_FILES):
        cache.mkdir(exist_ok=True)
        for name in FONT_FILES:
            with storage.open(f"fonts/{name}", "rb") as source, open(cache / name, "wb") as target:
                shutil.copyfileobj(source, target)
        return cache
    raise PublishError("Times New Roman is missing on the server: put times.ttf, timesi.ttf and timesbd.ttf in the "
                       "private files under fonts/ (or in PRODUCTION_FONTS_DIR)")


# ---------------------------------------------------------------- the metadata as published

# Words that keep their capital in a sentence-case title (the editors correct the rest).
KEEP_CAPITAL = {"lean", "last", "planner", "system", "takt", "toyota", "kaizen", "kanban", "gemba", "obeya",
                "hoshin", "kanri", "a3", "i"}


def sentence_case(title: str) -> str:
    """A first guess at the title in sentence case, as IGLC proceedings print it: a capital
    only at the start (not after a colon), in acronyms and in names such as Lean Construction."""
    shouting = title.upper() == title
    out, start, previous = [], True, ""
    for word in re.split(r"(\s+)", title.strip()):
        if not word.strip():
            out.append(word)
            continue
        letters = re.sub(r"\W", "", word)
        if start:
            out.append(word[:1].upper() + (word[1:].lower() if shouting else word[1:]))
        elif not shouting and (sum(c.isupper() for c in letters) > 1 or re.search(r"[a-z][A-Z]", letters)):
            out.append(word)  # BIM, LPS, ObeyA
        elif letters.lower() in KEEP_CAPITAL or (previous == "lean" and not shouting and word[:1].isupper()):
            out.append(word[:1].upper() + word[1:].lower())
        else:
            out.append(word.lower())
        start, previous = word.endswith(("?", "!", ".")), letters.lower()
    return "".join(out)


def published_metadata(submission: Submission, version=None) -> dict:
    """What goes into the archive: the Word file's metadata with the editors' corrections.
    `title_confirmed` is false while nobody has given the title in sentence case."""
    version = version or submission.current
    meta = dict(version.metadata) if version else {}
    edits = submission.metadata_edits or {}
    word_title = meta.get("title") or submission.title
    title_edit = edits.get("title") or {}
    if title_edit.get("for") == word_title and title_edit.get("value"):
        meta["title"], meta["title_confirmed"] = title_edit["value"], True
    elif meta.get("citation_title"):
        meta["title"], meta["title_confirmed"] = meta["citation_title"], True  # the editors' header
    else:
        meta["title"], meta["title_confirmed"] = sentence_case(word_title), False
    meta["word_title"] = word_title
    names = edits.get("names") or {}
    authors = []
    for author in meta.get("authors", []):
        author = dict(author)
        if author.get("name") in names:
            author["first_name"], author["last_name"] = names[author["name"]]
        authors.append(author)
    meta["authors"] = authors
    return meta


def save_metadata_edits(submission: Submission, title: str, names: dict[str, tuple[str, str]], user=None):
    meta = published_metadata(submission)
    edits = dict(submission.metadata_edits or {})
    if title.strip():
        edits["title"] = {"for": meta["word_title"], "value": re.sub(r"\s+", " ", title).strip()}
    known = dict(edits.get("names") or {})
    for name, (first, last) in names.items():
        first, last = first.strip(), last.strip()
        if first and not last:
            first, last = "", first
        known[name] = [first, last]
    edits["names"] = known
    submission.metadata_edits = edits
    submission.save(update_fields=["metadata_edits"])
    Event.objects.create(submission=submission, user=user, action="title and names checked")


# ---------------------------------------------------------------- checks

def readiness(production: Production) -> list[str]:
    """What stops the papers from being published."""
    problems = []
    conference = production.conference
    if not (conference.start_date and conference.city):
        problems.append("The conference needs its dates and city (they are printed in the footers).")
    layout, unknown = number_pages(production)
    if unknown:
        problems.append(f"{len(unknown)} paper(s) have no PDF, so the page numbers are not known: "
                        + ", ".join(str(s.conftool_id) for s in unknown[:10]))
    waiting = [p.submission for _, placed in layout for p in placed
               if p.submission.status != Submission.Status.APPROVED and not p.submission.paper_id]
    if waiting:
        problems.append(f"{len(waiting)} paper(s) are not approved yet: "
                        + ", ".join(str(s.conftool_id) for s in waiting[:10]))
    unconfirmed = [p.submission for _, placed in layout for p in placed if not p.submission.paper_id
                   and p.submission.current and not published_metadata(p.submission)["title_confirmed"]]
    if unconfirmed:
        problems.append(f"{len(unconfirmed)} paper(s) need their title checked in sentence case (on the paper's "
                        "page): " + ", ".join(str(s.conftool_id) for s in unconfirmed[:10]))
    try:
        fonts_folder()
    except PublishError as error:
        problems.append(str(error))
    return problems


# ---------------------------------------------------------------- the archive record

def _authors(paper: Paper, read: list[dict]):
    """Update the paper's authors from the Word file, keeping the link to the person where
    the name is unchanged."""
    existing = list(paper.authors.all())
    for order, data in enumerate(read, 1):
        first, last = data.get("first_name", ""), data.get("last_name", "") or data.get("name", "")
        author = existing[order - 1] if order <= len(existing) else Author(paper=paper)
        if (author.first_name, author.last_name) != (first.strip(), last.strip()):
            author.person = None  # a new name: group_authors finds the person
        author.first_name, author.last_name, author.order = first, last, order
        author.title_and_contact = data.get("note") or data.get("affiliation", "")
        author.save()
    for author in existing[len(read):]:
        author.delete()


def _archive_record(submission: Submission, version, first_page: int, last_page: int) -> Paper:
    conference = submission.production.conference
    meta = published_metadata(submission, version)
    paper = submission.paper or Paper.objects.filter(conference=conference, doi=submission.doi).first() or \
        Paper(conference=conference)
    paper.title = meta.get("title") or submission.title
    paper.abstract = meta.get("abstract", "")
    paper.keywords = ", ".join(meta.get("keywords", []))
    paper.track = submission.track
    paper.first_page, paper.last_page = first_page, last_page
    paper.doi = submission.doi
    paper.status = Paper.Status.APPROVED
    paper.save()
    _authors(paper, meta.get("authors", []))
    paper.refresh_authors_text()
    return paper


# ---------------------------------------------------------------- the PDF

def build_pdf(version, paper: Paper, first_page: int) -> bytes:
    """The editors' PDF with Word's headers and footers replaced by the IGLC running heads."""
    from .pdf_running import add_running, register_fonts, strip_running
    from .running import running_text

    if not version.pdf:
        raise PublishError(f"Paper {version.submission.conftool_id} has no PDF")
    register_fonts(fonts_folder())
    with version.pdf.open("rb") as handle:
        writer, _ = strip_running(io.BytesIO(handle.read()))
    add_running(writer, running_text(paper), first_page)
    writer.add_metadata({"/Title": paper.title, "/Author": paper.full_author_string(),
                         "/Subject": f"https://doi.org/{paper.doi}",
                         "/Keywords": paper.keywords})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def public_url(name: str) -> str:
    url = default_storage.url(name)
    return settings.SITE_URL + url if url.startswith("/") else url


def _store_pdf(submission: Submission, data: bytes, suffix: str = "") -> str:
    base = f"papers/iglc{submission.production.conference.number}/{submission.conftool_id:04d}{suffix}.pdf"
    return default_storage.save(base, ContentFile(data))


# ---------------------------------------------------------------- publishing

def _publish(submission: Submission, placed, user) -> Paper:
    version = submission.current
    with transaction.atomic():
        paper = _archive_record(submission, version, placed.first_page, placed.last_page)
        name = _store_pdf(submission, build_pdf(version, paper, placed.first_page))
        paper.full_text_url = public_url(name)
        paper.save(update_fields=["full_text_url"])
        submission.paper, submission.published_version, submission.first_page = paper, version, placed.first_page
        submission.published_pdf.name = name
        submission.save(update_fields=["paper", "published_version", "first_page", "published_pdf"])
        Event.objects.create(submission=submission, user=user, action=f"published version {version.number}")
    return paper


def pending(production: Production):
    """Placed papers not published yet, in proceedings order."""
    layout, _ = number_pages(production)
    return [p for _, placed in layout for p in placed if not p.submission.published_version_id]


def publish_next(production: Production, user=None, n: int = 10) -> dict:
    """Publish up to n more papers. Returns {"published": [...], "left": count}."""
    if production.papers_published:
        raise PublishError("The papers are already published: use a correction to change one")
    problems = readiness(production)
    if problems:
        raise PublishError(problems[0])
    todo = pending(production)
    done = [_publish(p.submission, p, user).doi for p in todo[:n]]
    return {"published": done, "left": len(todo) - len(done)}


def _zip_name(submission: Submission) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', " ", submission.paper.file_name()).strip()
    return f"{submission.conftool_id:04d} {name[:120].strip()}.pdf"


def build_zip(production: Production) -> str:
    """A ZIP of every published paper, linked from the conference page. Returns its URL."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:  # PDFs are compressed already
        for submission in production.submissions.filter(published_version__isnull=False).select_related("paper"):
            with submission.published_pdf.open("rb") as handle:
                archive.writestr(_zip_name(submission), handle.read())
    name = default_storage.save(f"papers/iglc{production.conference.number}/IGLC{production.conference.number}"
                                f"-papers.zip", ContentFile(buffer.getvalue()))
    old = production.conference.papers_zip_url
    conference = production.conference
    conference.papers_zip_url = public_url(name)
    conference.save(update_fields=["papers_zip_url"])
    prefix = public_url("")
    if old and old.startswith(prefix) and old != conference.papers_zip_url:
        default_storage.delete(old[len(prefix):])
    return conference.papers_zip_url


def finish(production: Production, user=None) -> str:
    """After the last paper: freeze the page numbers, show the conference, build the ZIP."""
    if pending(production):
        raise PublishError("Not every paper is published yet")
    from django.core.management import call_command

    call_command("group_authors", verbosity=0, stdout=io.StringIO())  # link new authors to the people in the archive
    production.status = Production.Status.PAPERS_PUBLISHED
    production.save(update_fields=["status"])
    conference = production.conference
    conference.is_published = True
    conference.save(update_fields=["is_published"])
    return build_zip(production)


# ---------------------------------------------------------------- corrections

def correction_problems(submission: Submission) -> list[str]:
    current = submission.current
    if not submission.published_version_id:
        return ["The paper is not published yet."]
    if current is None or current.pk == submission.published_version_id:
        return ["Upload the corrected Word file and PDF first."]
    problems = []
    if not current.pdf or not current.pages:
        problems.append("The corrected version needs its PDF.")
    elif current.pages > submission.published_pages:
        problems.append(f"The corrected paper has {current.pages} pages, but its published page range has "
                        f"{submission.published_pages}: it must fit, since the page numbers of the papers "
                        f"after it are already cited. Shorten it to {submission.published_pages} pages.")
    return problems


def correct(submission: Submission, user, note: str) -> Correction:
    """Publish the current version of a published paper. The DOI and first page stay; the last
    page follows the corrected PDF (which may be shorter). The old PDF is kept."""
    problems = correction_problems(submission)
    if problems:
        raise PublishError(problems[0])
    if not note.strip():
        raise PublishError("Say what was corrected: it is shown on the paper's page")
    version, first = submission.current, submission.paper.first_page
    with transaction.atomic():
        count = submission.corrections.count() + 1
        correction = Correction.objects.create(
            submission=submission, user=user, version=version, note=note.strip(),
            previous_version_id=submission.published_version_id, previous_pdf=submission.published_pdf.name)
        paper = _archive_record(submission, version, first, first + version.pages - 1)
        name = _store_pdf(submission, build_pdf(version, paper, first), suffix=f"-corrected-{count}")
        paper.full_text_url = public_url(name)
        paper.save(update_fields=["full_text_url"])
        submission.published_version, submission.status = version, Submission.Status.APPROVED
        submission.published_pdf.name = name
        submission.save(update_fields=["published_version", "published_pdf", "status"])
        Event.objects.create(submission=submission, user=user,
                             action=f"correction published (version {version.number})", comment=note.strip())
    from django.core.management import call_command

    call_command("group_authors", verbosity=0, stdout=io.StringIO())
    if submission.production.conference.papers_zip_url:
        build_zip(submission.production)
    return correction
