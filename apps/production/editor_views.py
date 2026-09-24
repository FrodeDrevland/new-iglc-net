"""The editors' pages: papers of a production, uploads, versions, approval."""

import io
import re
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.archive.management.commands.group_authors import fold

from .access import is_publisher, productions_for, role, submissions_for
from .arrange import number_pages, save_order
from .checks import LEVELS
from .models import Event, MetadataCheck, Production, Submission
from . import publish as publishing
from .uploads import add_version, upload_batch

MAX_UPLOAD = 300 * 1024 * 1024


def _production(request, number):
    production = get_object_or_404(Production.objects.select_related("conference"), conference__number=number)
    if role(request.user, production) is None:
        raise PermissionDenied
    return production


def _submission(request, production, conftool_id):
    submission = submissions_for(request.user, production).filter(conftool_id=conftool_id).first()
    if submission is None:
        raise Http404
    return submission


@login_required
def production_list(request):
    """The productions this person works on. Superusers and publishers also start new ones: from
    ConfTool's export of accepted papers, or from a conference already published in the archive."""
    from apps.archive.models import Conference

    can_start = request.user.is_superuser or is_publisher(request.user)
    if request.method == "POST":
        if not can_start:
            raise PermissionDenied
        conference = Conference.objects.filter(pk=request.POST.get("conference")).first()
        if conference is None:
            messages.error(request, "Choose the conference.")
        elif request.POST.get("action") == "conftool":
            _import_conftool(request, conference)
        elif request.POST.get("action") == "adopt":
            from .adopt import AdoptError, adopt_published

            try:
                production, report = adopt_published(conference, request.user)
                messages.success(request, f"{production}: {report['added']} papers taken from the archive, "
                                          f"{report['updated']} updated.")
                return redirect("proceedings:production", number=conference.number)
            except AdoptError as error:
                messages.error(request, str(error))
        return redirect("proceedings:productions")
    return render(request, "production/editor/list.html", {
        "productions": productions_for(request.user), "can_start": can_start,
        "conferences": Conference.objects.order_by("-number"),
        "published": Conference.objects.filter(papers__isnull=False).distinct().order_by("-number"),
    })


def _import_conftool(request, conference):
    import tempfile
    from pathlib import Path

    from django.core.management import CommandError, call_command

    upload = request.FILES.get("file")
    if not upload or Path(upload.name).suffix.lower() not in (".xlsx", ".csv"):
        messages.error(request, "Choose ConfTool's export of accepted papers (.xlsx or .csv).")
        return
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"export{Path(upload.name).suffix.lower()}"
        path.write_bytes(upload.read())
        out = io.StringIO()
        try:
            call_command("import_conftool", conference.number, str(path), stdout=out)
            messages.success(request, " ".join(out.getvalue().split()))
        except CommandError as error:
            messages.error(request, str(error))


@login_required
def production_detail(request, number):
    production = _production(request, number)
    papers = submissions_for(request.user, production).prefetch_related("versions")
    track, status, mine = request.GET.get("track"), request.GET.get("status"), request.GET.get("mine")
    if track:
        papers = papers.filter(track_id=track)
    if status:
        papers = papers.filter(status=status)
    if mine:
        papers = papers.filter(editor=request.user)
    rows = []
    checks = {}
    for check in MetadataCheck.objects.filter(submission__production=production).order_by("created"):
        checks[check.submission_id] = check
    for paper in papers:
        versions = list(paper.versions.all())
        rows.append({"paper": paper, "current": versions[0] if versions else None, "count": len(versions),
                     "check": checks.get(paper.pk)})
    summary = [(label, production.submissions.filter(status=key).count()) for key, label in Submission.Status.choices]
    summary = [(label, n) for label, n in summary if n]
    return render(request, "production/editor/production.html", {
        "production": production, "rows": rows, "role": role(request.user, production),
        "tracks": production.conference.tracks.all(), "statuses": Submission.Status.choices,
        "summary": summary, "filters": {"track": track, "status": status, "mine": mine},
    })


@login_required
@require_POST
def download(request, number):
    """The current Word files (and PDFs) of the chosen papers, as a ZIP named by ConfTool ID."""
    production = _production(request, number)
    ids = [int(i) for i in request.POST.getlist("paper") if i.isdigit()]
    papers = submissions_for(request.user, production)
    if ids:
        papers = papers.filter(conftool_id__in=ids)
    with_pdf = request.POST.get("with_pdf") == "1"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for paper in papers:
            current = paper.current
            if not current:
                continue
            with current.docx.open("rb") as handle:
                archive.writestr(f"{paper.conftool_id}.docx", handle.read())
            if with_pdf and current.pdf:
                with current.pdf.open("rb") as handle:
                    archive.writestr(f"{paper.conftool_id}.pdf", handle.read())
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="IGLC{number}-papers.zip"'
    return response


@login_required
def upload(request, number):
    production = _production(request, number)
    report = None
    if request.method == "POST":
        files = request.FILES.getlist("files")
        if not files:
            messages.error(request, "Choose the files to upload.")
        elif sum(f.size for f in files) > MAX_UPLOAD:
            messages.error(request, "At most 300 MB in one upload: upload in parts.")
        else:
            report = upload_batch(
                production, [(f.name, f.read()) for f in files], request.user, request.POST.get("comment", "").strip(),
                allowed=list(submissions_for(request.user, production)))
    return render(request, "production/editor/upload.html", {"production": production, "report": report})


def _compare_authors(read, registered):
    """Pair the authors read from the paper with those registered, by name."""
    def key(name):
        return fold(name).replace(" ", "")

    left = {key(a.get("name", "")): a for a in registered}
    rows = []
    for author in read:
        match = left.pop(key(author.get("name", "")), None)
        rows.append({"read": author, "registered": match, "same_name": match is not None})
    for rest in left.values():
        rows.append({"read": None, "registered": rest, "same_name": False})
    return rows


@login_required
def paper(request, number, conftool_id):
    production = _production(request, number)
    submission = _submission(request, production, conftool_id)
    my_role = role(request.user, production)
    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("comment", "").strip()
        if action == "upload":
            docx, pdf = request.FILES.get("docx"), request.FILES.get("pdf")
            try:
                version = add_version(submission, (docx.name, docx.read()) if docx else None,
                                      (pdf.name, pdf.read()) if pdf else None, request.user, comment)
                messages.success(request, f"Version {version.number} added.")
            except ValueError as error:
                messages.error(request, str(error))
        elif action in ("approve", "send_back"):
            submission.status = Submission.Status.APPROVED if action == "approve" else Submission.Status.NEEDS_WORK
            submission.save(update_fields=["status"])
            Event.objects.create(submission=submission, user=request.user,
                                 action="approved" if action == "approve" else "needs more work", comment=comment)
        elif action == "assign":
            track = request.POST.get("track")
            submission.track = production.conference.tracks.filter(pk=track).first() if track else None
            editor = request.POST.get("editor")
            submission.editor = get_user_model().objects.filter(pk=editor).first() if editor else None
            submission.save(update_fields=["track", "editor"])
            Event.objects.create(submission=submission, user=request.user, action="track and editor set")
        elif action == "metadata":
            names = {}
            for index, name in enumerate(request.POST.getlist("author_name")):
                names[name] = (request.POST.get(f"first_{index}", ""), request.POST.get(f"last_{index}", ""))
            publishing.save_metadata_edits(submission, request.POST.get("published_title", ""), names, request.user)
            messages.success(request, "Title and names saved." + (
                " Publish a correction to put them on the site." if submission.published_version_id else ""))
        elif action == "stage_correction":
            if my_role != "chief":
                raise PermissionDenied
            problems = publishing.correction_problems(submission)
            if problems or not comment:
                messages.error(request, problems[0] if problems else "Say what was corrected.")
            else:
                submission.correction_note, submission.correction_requested_by = comment, request.user
                submission.correction_public = request.POST.get("public") == "1"
                submission.save(update_fields=["correction_note", "correction_requested_by", "correction_public"])
                Event.objects.create(submission=submission, user=request.user,
                                     action="correction sent to the publisher", comment=comment)
                messages.success(request, "The correction waits for the publisher's approval.")
        elif action in ("apply_check", "close_check"):
            from . import metadata_check as checks

            if my_role != "chief":
                raise PermissionDenied
            check = submission.metadata_checks.filter(pk=request.POST.get("check")).first()
            if check is None or check.status != MetadataCheck.Status.CORRECTIONS:
                messages.error(request, "There is nothing to handle.")
            elif action == "apply_check":
                changes = checks.apply(check, request.user, comment)
                messages.success(request, f"{len(changes)} change(s) made to the published record. Send a new Crossref "
                                          "deposit (publish page) so the DOI's record follows; if the change is printed "
                                          "in the paper, also publish a corrected version.")
            else:
                checks.close(check, request.user, comment)
                messages.success(request, "Marked as handled.")
        elif action == "stage_pdf":
            if my_role != "chief":
                raise PermissionDenied
            upload = request.FILES.get("pdf")
            data = upload.read() if upload else b""
            problems = publishing.pdf_correction_problems(submission, data) if data else ["Choose the PDF."]
            if not problems and not comment:
                problems = ["Say what was corrected."]
            if problems:
                messages.error(request, problems[0])
            else:
                if submission.correction_pdf:
                    submission.correction_pdf.delete(save=False)
                submission.correction_pdf.save("replacement.pdf", ContentFile(data), save=False)
                submission.correction_note, submission.correction_requested_by = comment, request.user
                submission.correction_public = request.POST.get("public") == "1"
                submission.save(update_fields=["correction_pdf", "correction_note", "correction_requested_by",
                                               "correction_public"])
                Event.objects.create(submission=submission, user=request.user,
                                     action="replacement PDF sent to the publisher", comment=comment)
                messages.success(request, "The replacement PDF waits for the publisher's approval.")
        elif action == "correct_pdf":
            if not is_publisher(request.user):
                raise PermissionDenied
            try:
                publishing.correct_pdf(submission, request.user, comment or submission.correction_note,
                                       public=request.POST.get("public") == "1")
                messages.success(request, "The corrected PDF is published.")
            except publishing.PublishError as error:
                messages.error(request, str(error))
        elif action == "correct":
            if not is_publisher(request.user):
                raise PermissionDenied
            try:
                publishing.correct(submission, request.user, comment or submission.correction_note,
                                   public=request.POST.get("public") == "1")
                submission.correction_note, submission.correction_requested_by = "", None
                submission.save(update_fields=["correction_note", "correction_requested_by"])
                messages.success(request, "The correction is published. If the title or authors changed, "
                                          "send a new Crossref deposit (publish page).")
            except publishing.PublishError as error:
                messages.error(request, str(error))
        return redirect("proceedings:paper", number=number, conftool_id=conftool_id)

    versions = list(submission.versions.select_related("uploaded_by"))
    current = versions[0] if versions else None
    groups = []
    if current:
        groups = [(LEVELS[level], [f for f in current.findings if f["level"] == level]) for level in LEVELS]
    return render(request, "production/editor/paper.html", {
        "production": production, "submission": submission, "versions": versions, "current": current,
        "groups": [g for g in groups if g[1]], "role": my_role,
        "authors": _compare_authors(current.metadata.get("authors", []) if current else [], submission.registered_authors),
        "tracks": production.conference.tracks.all(),
        "editors": [e.user for e in production.editors.select_related("user")],
        "events": submission.events.select_related("user")[:30],
        "published_meta": publishing.published_metadata(submission) if current else None,
        "check": _check_context(submission),
        "can_publish": is_publisher(request.user),
        "correction_problems": publishing.correction_problems(submission) if submission.published_version_id else [],
        "corrections": submission.corrections.select_related("user", "version"),
    })


def _check_context(submission):
    from . import metadata_check as checks

    check = submission.metadata_checks.first()
    if check is None or not submission.paper_id:
        return None
    record = checks.published_record(submission.paper)
    return {"check": check, "changes": checks.differences(record, check.proposal) if check.proposal else [],
            "comment": (check.proposal or {}).get("comment", "")}


@login_required
def correction_file(request, number, conftool_id):
    """The replacement PDF waiting for the publisher."""
    production = _production(request, number)
    submission = _submission(request, production, conftool_id)
    if not submission.correction_pdf:
        raise Http404
    return FileResponse(submission.correction_pdf.open("rb"), as_attachment=True,
                        filename=f"{conftool_id}-replacement.pdf")


@login_required
def version_file(request, number, conftool_id, version, kind):
    production = _production(request, number)
    submission = _submission(request, production, conftool_id)
    item = get_object_or_404(submission.versions, number=version)
    field = item.docx if kind == "docx" else item.pdf
    if not field:
        raise Http404
    return FileResponse(field.open("rb"), as_attachment=True, filename=f"{conftool_id}-v{version}.{kind}")


@login_required
def arrange(request, number):
    """Order of tracks and papers, and the page numbers. Chief editors change it; editors see it."""
    import json

    production = _production(request, number)
    my_role = role(request.user, production)
    if request.method == "POST":
        if my_role != "chief" or production.pages_frozen:
            raise PermissionDenied
        try:
            layout = json.loads(request.POST.get("layout", "[]"))
            first_page = int(request.POST.get("first_page") or 1)
        except (ValueError, TypeError):
            messages.error(request, "The order could not be read; nothing was changed.")
            return redirect("proceedings:arrange", number=number)
        if first_page != production.first_page:
            production.first_page = max(1, first_page)
            production.save(update_fields=["first_page"])
        save_order(production, [(t or None, [int(i) for i in ids]) for t, ids in layout])
        messages.success(request, "Order and page numbers saved.")
        return redirect("proceedings:arrange", number=number)
    layout, unknown = number_pages(production)
    return render(request, "production/editor/arrange.html", {
        "production": production, "layout": layout, "unknown": unknown, "role": my_role,
        "can_edit": my_role == "chief" and not production.pages_frozen,
    })


@login_required
def publish(request, number):
    """Stage 1: publish the papers on the site with DOIs and page numbers. A chief editor asks for
    it; a publisher approves, and the browser then asks for a few papers at a time (each request
    stays short); the last step freezes the pages."""
    from django.utils import timezone

    production = _production(request, number)
    my_role = role(request.user, production)
    action = request.POST.get("action")
    if request.method == "POST" and action and action.startswith("crossref_"):
        return _crossref_action(request, production, action)
    if request.method == "POST" and action == "make_zip":
        if my_role != "chief" and not is_publisher(request.user):
            raise PermissionDenied
        try:
            publishing.build_zip(production)
            messages.success(request, "The ZIP of all papers is made and linked from the conference page.")
        except publishing.PublishError as error:
            messages.error(request, str(error))
        return redirect("proceedings:publish", number=number)
    if request.method == "POST" and action in ("metadata_send", "metadata_remind"):
        from . import metadata_check as checks

        if my_role != "chief" and not is_publisher(request.user):
            raise PermissionDenied
        after = request.POST.get("after", "0")
        step = checks.send_next if action == "metadata_send" else checks.remind_next
        return JsonResponse(step(production, request.user, n=10, after=int(after) if after.isdigit() else 0))
    if request.method == "POST" and action == "request":
        if my_role != "chief":
            raise PermissionDenied
        problems = publishing.readiness(production)
        if problems:
            messages.error(request, problems[0])
        else:
            production.papers_requested_at, production.papers_requested_by = timezone.now(), request.user
            production.save(update_fields=["papers_requested_at", "papers_requested_by"])
            messages.success(request, "The publisher is asked to publish the papers.")
        return redirect("proceedings:publish", number=number)
    if request.method == "POST":
        if not is_publisher(request.user):
            raise PermissionDenied
        try:
            if not production.papers_requested_at:
                raise publishing.PublishError("A chief editor has not asked for publication yet")
            if action == "finish":
                publishing.finish(production, request.user)
                messages.success(request, "The papers are published, and the ZIP of all papers is on the conference page.")
                return redirect("proceedings:publish", number=number)
            return JsonResponse(publishing.publish_next(production, request.user, n=10))
        except publishing.PublishError as error:
            if action == "finish":
                messages.error(request, str(error))
                return redirect("proceedings:publish", number=number)
            return JsonResponse({"error": str(error)}, status=400)
    published = production.submissions.filter(published_version__isnull=False).select_related("paper")
    return render(request, "production/editor/publish.html", {
        "production": production, "role": my_role, "can_publish": is_publisher(request.user),
        "problems": [] if production.papers_published else publishing.readiness(production),
        "published": published, "left": 0 if production.papers_published else len(publishing.pending(production)),
        "corrections": publishing.Correction.objects.filter(submission__production=production)
                       .select_related("submission", "user"),
        "waiting_corrections": production.submissions.exclude(correction_note="").select_related("correction_requested_by"),
        "deposits": production.conference.crossref_deposits.select_related("user")[:10],
        "metadata": _metadata_summary(production),
        "crossref": _crossref_settings(),
    })


def _metadata_summary(production):
    from collections import Counter

    from . import metadata_check as checks

    latest = {}
    for check in MetadataCheck.objects.filter(submission__production=production).order_by("created"):
        latest[check.submission_id] = check.status
    counts = Counter(latest.values())
    return {"not_asked": len(checks.pending(production)),
            "counts": [(label, counts.get(key, 0)) for key, label in MetadataCheck.Status.choices],
            "waiting": counts.get(MetadataCheck.Status.SENT, 0)}


def _crossref_settings():
    from django.conf import settings

    from apps.crossref.deposit import configured

    return {"configured": configured(), "test": settings.CROSSREF_TEST, "site": settings.CROSSREF_SITE_URL}


def _crossref_action(request, production, action):
    """Register (or update) the DOIs of the production's papers with Crossref. Publishers only."""
    from apps.crossref import deposit as crossref

    if not is_publisher(request.user):
        raise PermissionDenied
    number = production.conference.number
    try:
        if action == "crossref_make":
            papers = [s.paper for s in production.submissions.filter(paper__isnull=False)
                      .select_related("paper").order_by("paper__first_page")]
            if not papers:
                raise crossref.DepositError("No published papers yet")
            made = crossref.make(production.conference, papers, request.user, isbn=production.isbn_pdf)
            messages.success(request, f"Deposit made for {made.papers} papers. Download the XML to look at it, then send it.")
        else:
            item = production.conference.crossref_deposits.get(pk=request.POST.get("deposit"))
            if action == "crossref_send":
                crossref.send(item)
                messages.success(request, "Sent. Crossref processes deposits in a queue: check the result in a few minutes.")
            elif action == "crossref_check":
                crossref.check(item)
                messages.info(request, f"{item.get_status_display()}.")
    except crossref.DepositError as error:
        messages.error(request, str(error))
    except Exception as error:  # noqa: BLE001 - e.g. missing conference dates
        messages.error(request, f"Could not make the deposit: {error}")
    return redirect("proceedings:publish", number=number)


@login_required
def deposit_file(request, number, pk, kind):
    """A deposit's XML, or Crossref's result for it."""
    production = _production(request, number)
    if not is_publisher(request.user):
        raise PermissionDenied
    item = get_object_or_404(production.conference.crossref_deposits, pk=pk)
    content = item.xml if kind == "xml" else item.result
    response = HttpResponse(content, content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="{item.batch_id}{"" if kind == "xml" else "-result"}.xml"'
    return response


# ---------------------------------------------------------------- the full proceedings

def _isbn_ok(value: str) -> bool:
    digits = re.sub(r"[^0-9X]", "", value.upper())
    if len(digits) == 13 and digits.isdigit():
        return sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10 == 0
    if len(digits) == 10:
        total = sum((10 - i) * (10 if d == "X" else int(d)) for i, d in enumerate(digits) if d.isdigit() or i == 9)
        return total % 11 == 0
    return False


def _save_track_chairs(production, post):
    from .models import TrackChair

    for track in production.conference.tracks.all():
        field = f"chairs_{track.pk}"
        if field not in post:
            continue
        TrackChair.objects.filter(production=production, track=track).delete()
        for order, line in enumerate([l.strip() for l in post[field].splitlines() if l.strip()], 1):
            name, _, affiliation = line.partition(",")
            TrackChair.objects.create(production=production, track=track, name=name.strip(),
                                      affiliation=affiliation.strip(), order=order)


@login_required
def book(request, number):
    """Stage 2: the full proceedings. Chief editors prepare it and submit it; a publisher enters
    the ISBNs, approves and publishes it."""
    from django.utils import timezone
    from pypdf import PdfReader

    from . import book as books
    from .models import BookPart

    production = _production(request, number)
    my_role = role(request.user, production)
    can_publish = is_publisher(request.user)
    can_edit = my_role == "chief" or can_publish
    if request.method == "POST":
        action = request.POST.get("action")
        if not can_edit or (action in ("isbn", "publish") and not can_publish):
            raise PermissionDenied
        try:
            if action == "fetch":
                after = request.POST.get("after", "0")
                return JsonResponse(books.fetch_next(production, n=10, after=int(after) if after.isdigit() else 0))
            if action == "settings":
                production.conference_chair = request.POST.get("conference_chair", "").strip()
                production.copyright_holders = request.POST.get("copyright_holders", "").strip()
                production.save(update_fields=["conference_chair", "copyright_holders"])
                _save_track_chairs(production, request.POST)
                messages.success(request, "Saved.")
            elif action == "isbn":
                values = {f: request.POST.get(f, "").strip() for f in ("isbn_print", "isbn_pdf", "issn_print",
                                                                       "issn_electronic")}
                bad = [v for f, v in values.items() if f.startswith("isbn") and v and not _isbn_ok(v)]
                if bad:
                    raise books.BookError(f"Not a valid ISBN: {bad[0]}")
                for field, value in values.items():
                    setattr(production, field, value)
                production.save(update_fields=list(values))
                messages.success(request, "ISBN and ISSN saved.")
            elif action == "upload":
                upload = request.FILES.get("pdf")
                kind = request.POST.get("kind")
                if not upload or kind not in BookPart.Kind.values:
                    raise books.BookError("Choose the part and its PDF")
                data = upload.read()
                found = books.check_part(data, kind)
                if found:
                    raise books.BookError("Not uploaded: it does not follow the template. " + " ".join(found))
                if kind in BookPart.COVERS or kind in (BookPart.Kind.FOREWORD, BookPart.Kind.ORGANISATION,
                                                       BookPart.Kind.REVIEWERS):
                    production.book_parts.filter(kind=kind).delete()  # a new version replaces the old
                placement = request.POST.get("placement")
                if placement not in BookPart.Placement.values:
                    placement = BookPart.Placement.FRONT
                last = production.book_parts.filter(placement=placement).order_by("-order").first()
                part = BookPart(production=production, kind=kind, title=request.POST.get("title", "").strip(),
                                placement=placement, uploaded_by=request.user,
                                order=BookPart.DEFAULT_ORDER.get(kind, (last.order + 10) if last else 10),
                                pages=len(PdfReader(io.BytesIO(data)).pages))
                part.pdf.save(f"{kind}.pdf", ContentFile(data), save=False)
                part.save()
                messages.success(request, f"{part.label} uploaded ({part.pages} page{'s' if part.pages != 1 else ''}).")
            elif action == "arrange_parts":
                for part in production.book_parts.all():
                    order = request.POST.get(f"order_{part.pk}", "")
                    placement = request.POST.get(f"placement_{part.pk}", part.placement)
                    if order.isdigit():
                        part.order = int(order)
                    if placement in BookPart.Placement.values:
                        part.placement = placement
                    part.save(update_fields=["order", "placement"])
                messages.success(request, "Order saved.")
            elif action == "delete_part":
                production.book_parts.filter(pk=request.POST.get("part")).delete()
            elif action == "draft":
                size = books.save_draft(production)
                production.draft_built = timezone.now()
                production.save(update_fields=["draft_built"])
                messages.success(request, f"Draft made ({size / 1e6:.0f} MB). Download it below.")
            elif action == "submit":
                if my_role != "chief":
                    raise PermissionDenied
                if not production.draft_built:
                    raise books.BookError("Make a draft and check it first")
                production.book_requested_at, production.book_requested_by = timezone.now(), request.user
                production.save(update_fields=["book_requested_at", "book_requested_by"])
                messages.success(request, "Sent to the publisher for approval.")
            elif action == "publish":
                if not production.book_requested_at:
                    raise books.BookError("A chief editor has not submitted the proceedings yet")
                books.publish_book(production, request.user)
                messages.success(request, "The full proceedings are published and linked from the conference page. "
                                          "Send a new Crossref deposit (publish page) to register the ISBN.")
        except books.BookError as error:
            if action == "fetch":
                return JsonResponse({"error": str(error)}, status=400)
            messages.error(request, str(error))
        return redirect("proceedings:book", number=number)

    parts = books.parts_of(production)
    chairs = {}
    for chair in production.track_chairs.all():
        chairs.setdefault(chair.track_id, []).append(f"{chair.name}, {chair.affiliation}".strip(", "))
    stats = books.statistics(production)
    return render(request, "production/editor/book.html", {
        "production": production, "role": my_role, "can_edit": can_edit, "can_publish": can_publish,
        "problems": books.problems(production), "final_problems": books.problems(production, final=True),
        "missing": len(books.missing_pdfs(production)), "stats": stats,
        "covers": [(kind, parts.get(kind, [])) for kind in BookPart.COVERS],
        "sections": production.book_parts.exclude(kind__in=BookPart.COVERS),
        "kinds": BookPart.Kind.choices, "placements": BookPart.Placement.choices,
        "templates": [(k, l) for k, l in BookPart.Kind.choices if k not in BookPart.COVERS],
        "tracks": [(t, "\n".join(chairs.get(t.pk, []))) for t in production.conference.tracks.all()],
        "editors": books.editors_of(production),
    })


@login_required
def book_file(request, number, name):
    """The draft of the full proceedings, and the Word templates for its parts."""
    from . import book as books
    from .models import BookPart, private_storage

    production = _production(request, number)
    if name == "draft.pdf":
        storage = private_storage()
        if not storage.exists(books.draft_name(production)):
            raise Http404
        return FileResponse(storage.open(books.draft_name(production), "rb"), as_attachment=True,
                            filename=f"IGLC{number}-Proceedings-DRAFT.pdf")
    kind = name.removesuffix(".docx")
    if kind not in BookPart.Kind.values or kind in (BookPart.Kind.COVER, BookPart.Kind.BACK_COVER):
        raise Http404
    response = HttpResponse(books.template(production, kind), content_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
    response["Content-Disposition"] = f'attachment; filename="IGLC{number}-{kind}.docx"'
    return response


@login_required
def guide(request):
    """The editors' guide to proceedings production."""
    from .checks import configuration

    if not productions_for(request.user).exists() and not request.user.is_superuser:
        raise PermissionDenied
    return render(request, "production/editor/guide.html", {"max_pages": configuration()[1]["max_pages"]})


@login_required
def conversion_script(request):
    """tools/word_batch.ps1: page counts and PDFs of many papers with Word for Windows."""
    from django.conf import settings

    path = settings.BASE_DIR / "tools" / "word_batch.ps1"
    return FileResponse(open(path, "rb"), as_attachment=True, filename="iglc-word-batch.ps1")
