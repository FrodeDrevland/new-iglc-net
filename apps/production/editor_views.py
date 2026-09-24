"""The editors' pages: papers of a production, uploads, versions, approval."""

import io
import re
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.archive.management.commands.group_authors import fold

from .access import productions_for, role, submissions_for
from .arrange import number_pages, save_order
from .checks import LEVELS
from .models import Event, Production, Submission
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
    return render(request, "production/editor/list.html", {"productions": productions_for(request.user)})


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
    for paper in papers:
        versions = list(paper.versions.all())
        rows.append({"paper": paper, "current": versions[0] if versions else None, "count": len(versions)})
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
        elif action == "correct":
            if my_role != "chief":
                raise PermissionDenied
            try:
                publishing.correct(submission, request.user, comment)
                messages.success(request, "The correction is published.")
            except publishing.PublishError as error:
                messages.error(request, str(error))
        return redirect("production:paper", number=number, conftool_id=conftool_id)

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
        "correction_problems": publishing.correction_problems(submission) if submission.published_version_id else [],
        "corrections": submission.corrections.select_related("user", "version"),
    })


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
            return redirect("production:arrange", number=number)
        if first_page != production.first_page:
            production.first_page = max(1, first_page)
            production.save(update_fields=["first_page"])
        save_order(production, [(t or None, [int(i) for i in ids]) for t, ids in layout])
        messages.success(request, "Order and page numbers saved.")
        return redirect("production:arrange", number=number)
    layout, unknown = number_pages(production)
    return render(request, "production/editor/arrange.html", {
        "production": production, "layout": layout, "unknown": unknown, "role": my_role,
        "can_edit": my_role == "chief" and not production.pages_frozen,
    })


@login_required
def publish(request, number):
    """Stage 1: publish the papers on the site with DOIs and page numbers. The browser asks
    for a few papers at a time (each request stays short); the last step freezes the pages."""
    production = _production(request, number)
    my_role = role(request.user, production)
    if request.method == "POST":
        if my_role != "chief":
            raise PermissionDenied
        try:
            if request.POST.get("action") == "finish":
                publishing.finish(production, request.user)
                messages.success(request, "The papers are published, and the ZIP of all papers is on the conference page.")
                return redirect("production:publish", number=number)
            return JsonResponse(publishing.publish_next(production, request.user, n=10))
        except publishing.PublishError as error:
            if request.POST.get("action") == "finish":
                messages.error(request, str(error))
                return redirect("production:publish", number=number)
            return JsonResponse({"error": str(error)}, status=400)
    published = production.submissions.filter(published_version__isnull=False).select_related("paper")
    return render(request, "production/editor/publish.html", {
        "production": production, "role": my_role,
        "problems": [] if production.papers_published else publishing.readiness(production),
        "published": published, "left": 0 if production.papers_published else len(publishing.pending(production)),
        "corrections": publishing.Correction.objects.filter(submission__production=production)
                       .select_related("submission", "user"),
    })
