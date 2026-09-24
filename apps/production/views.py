import hashlib
import io
import tempfile
from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .checks import LEVELS, STAGES, check_paper
from .forms import PaperCheckForm
from .models import PaperCheck


def _sha256(uploaded) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    return digest.hexdigest()


@require_http_methods(["GET", "POST"])
def check_form(request):
    form = PaperCheckForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        paper, pdf = form.cleaned_data["paper"], form.cleaned_data.get("pdf")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.docx"
            path.write_bytes(b"".join(paper.chunks()))
            pdf_file = None
            if pdf:
                pdf_file = io.BytesIO(b"".join(pdf.chunks()))
            result = check_paper(path, form.cleaned_data["stage"], pdf_file)
        check = PaperCheck.objects.create(
            stage=result.stage, file_name=paper.name[:255], sha256=_sha256(paper),
            pdf_sha256=_sha256(pdf) if pdf else "", title=result.manuscript.title[:500],
            passed=result.passed,
            findings=[{"level": f.level, "code": f.code, "message": f.message} for f in result.findings],
        )
        return redirect("production:check_report", pk=check.pk)
    return render(request, "production/check_form.html", {"form": form})


def check_report(request, pk):
    check = get_object_or_404(PaperCheck, pk=pk)
    groups = [(LEVELS[level], [f for f in check.findings if f["level"] == level]) for level in LEVELS]
    return render(request, "production/check_report.html", {
        "check": check, "groups": [g for g in groups if g[1]], "stage": STAGES.get(check.stage, check.stage),
        "report_url": request.build_absolute_uri(),
    })


def check_report_pdf(request, pk):
    from .report_pdf import report_pdf

    check = get_object_or_404(PaperCheck, pk=pk)
    url = request.build_absolute_uri(check_report_url(check))
    response = HttpResponse(report_pdf(check, STAGES.get(check.stage, check.stage), url), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="IGLC-template-check-{check.short_id}.pdf"'
    return response


def check_report_url(check):
    from django.urls import reverse

    return reverse("production:check_report", args=[check.pk])
