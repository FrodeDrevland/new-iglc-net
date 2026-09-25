"""The authors' page, reached by the secret link in their email: will the paper be presented, by
whom, and which author is registered (no login). On the main site."""

from django.shortcuts import get_object_or_404, redirect, render

from . import backing
from .models import PaperPresentation, Programme


def confirm(request, token):
    presentation = get_object_or_404(PaperPresentation.objects.select_related(
        "submission__paper", "submission__production__conference"), token=token)
    submission = presentation.submission
    conference = submission.production.conference
    programme = get_object_or_404(Programme, conference=conference)
    authors = [a["name"] for a in backing.paper_authors(submission)]
    withdrawn = submission.status == submission.Status.WITHDRAWN
    errors = []
    data = {"answer": presentation.answer, "presenter": presentation.presenter, "backer": presentation.backer,
            "backer_email": presentation.backer_email, "comment": presentation.comment,
            "responder": presentation.responder}
    slides_error = ""
    if request.method == "POST" and request.POST.get("action") == "slides" and not withdrawn:
        from . import slides

        upload = request.FILES.get("slides")
        slides_error = slides.problem(upload)
        if not slides_error:
            slides.save(presentation, upload, request.POST.get("responder", "").strip()[:200])
            return redirect("programme_public:confirm", token=token)
    elif request.method == "POST" and not withdrawn:
        data = {key: request.POST.get(key, "").strip() for key in data}
        if data["answer"] not in PaperPresentation.Answer.values:
            errors.append("Please say whether the paper will be presented.")
        if data["answer"] == "present" and data["presenter"] not in authors:
            errors.append("Please choose who presents the paper.")
        if data["answer"] in ("present", "not_present") and data["backer"] not in authors:
            errors.append("Please choose the author whose registration backs the paper.")
        if data["backer_email"] and not backing.EMAIL.fullmatch(data["backer_email"]):
            errors.append("The email address does not look right.")
        if not data["responder"]:
            errors.append("Please give your name.")
        if not errors:
            backing.respond(presentation, data["responder"], data["answer"], data["presenter"], data["backer"],
                            data["backer_email"], data["comment"])
            return redirect("programme_public:confirm", token=token)
    row = next((r for r in backing.assess(programme) if r.submission.pk == submission.pk), None)
    return render(request, "programme/confirm.html", {
        "presentation": presentation, "submission": submission, "conference": conference, "programme": programme,
        "title": submission.paper.title if submission.paper_id else submission.title, "authors": authors,
        "data": data, "errors": errors, "answers": PaperPresentation.Answer.choices, "withdrawn": withdrawn,
        "backed": row is not None and row.status == "backed", "limit": backing.LIMIT, "slides_error": slides_error,
    })
