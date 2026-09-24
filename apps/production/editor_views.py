"""The editors' pages: papers of a production, uploads, versions, approval."""

import io
import re
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.archive.management.commands.group_authors import fold

from .access import productions_for, role, submissions_for
from .checks import LEVELS
from .models import Event, Production, Submission
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
