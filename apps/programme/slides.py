"""The authors' slides: uploaded on the page of their paper's secret link (public_views.confirm),
shown with the paper in the programme, and put on the published paper's page in the archive
(its "Presentation" button)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.utils import timezone

MAX_BYTES = 50 * 1024 * 1024
KINDS = {".pdf": b"%PDF", ".pptx": b"PK\x03\x04"}


def problem(upload) -> str:
    """Why the file cannot be taken, or ''."""
    if upload is None:
        return "Choose the file."
    suffix = Path(upload.name).suffix.lower()
    if suffix not in KINDS:
        return "The slides must be a PDF or a PowerPoint file (.pptx)."
    if upload.size > MAX_BYTES:
        return f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB."
    head = upload.read(4)
    upload.seek(0)
    if head != KINDS[suffix]:
        return f"The file is not a real {suffix[1:].upper()} file."
    return ""


def public_url(presentation) -> str:
    url = presentation.slides.url
    return url if url.startswith(("http://", "https://")) else settings.SITE_URL + url


def save(presentation, upload, responder: str = ""):
    from apps.production.models import Event

    if presentation.slides:
        presentation.slides.delete(save=False)
    presentation.slides.save(upload.name, upload, save=False)
    presentation.slides_uploaded = timezone.now()
    presentation.save(update_fields=["slides", "slides_uploaded"])
    Event.objects.create(submission=presentation.submission, action="slides uploaded by the authors",
                         comment=responder)
    link_to_paper(presentation)


def link_to_paper(presentation) -> bool:
    """Put the slides on the published paper's page. Returns whether there was a paper."""
    from apps.archive.models import Paper

    submission = presentation.submission
    if not (submission.paper_id and presentation.slides):
        return False
    Paper.objects.filter(pk=submission.paper_id).update(presentation_url=public_url(presentation))
    return True


def link_all(programme) -> int:
    """For papers published after their slides were uploaded."""
    from .models import PaperPresentation

    count = 0
    for presentation in (PaperPresentation.objects.filter(submission__production__conference=programme.conference)
                         .exclude(slides="").select_related("submission")):
        count += link_to_paper(presentation)
    return count
