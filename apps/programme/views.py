"""The programme's pages in the back office, under /manage/programme/ (docs/programme.md)."""

from __future__ import annotations

from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import access, checks, setup
from .forms import (ItemFormSet, LocationForm, PartFormSet, PersonFormSet, ProgrammeForm, SessionForm,
                    StartForm)
from .models import Location, Programme, Session, SessionItem


def _programme(request, number) -> Programme:
    programme = get_object_or_404(Programme.objects.select_related("conference"), conference__number=number)
    if not access.can_view(request.user, programme):
        raise PermissionDenied
    return programme


def _submissions(programme):
    from apps.production.models import Submission

    return (Submission.objects.filter(production__conference=programme.conference)
            .exclude(status=Submission.Status.WITHDRAWN).order_by("conftool_id"))


@login_required
def programme_list(request):
    can_start = request.user.is_superuser
    form = StartForm(request.POST or None) if can_start else None
    if request.method == "POST":
        if not can_start:
            raise PermissionDenied
        if form.is_valid():
            try:
                programme = setup.start(form.cleaned_data["conference"], form.cleaned_data["time_zone"])
            except ValueError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, f"{programme} started, with its parts and groups. Add people to the "
                                          f"groups under Settings → Groups.")
                return redirect("programme:overview", number=programme.number)
    return render(request, "programme/list.html", {"programmes": access.programmes_for(request.user),
                                                   "form": form})


@login_required
def overview(request, number):
    programme = _programme(request, number)
    sessions = (programme.sessions.select_related("location", "part", "keynote")
                .prefetch_related("people", "items"))
    days = OrderedDict((day, []) for day in programme.days())
    for session in sessions:
        days.setdefault(session.date, []).append(session)
    editable = access.editable_parts(request.user, programme)
    parts = list(programme.parts.select_related("editors"))
    home = getattr(programme.conference, "site_home", None)
    for part in parts:
        from .public import home_url

        part.private_url = (f"{home_url(home)}programme/private/{part.token}/"
                            if home and not part.public and (part in editable or access.is_chair(request.user, programme))
                            else "")
    return render(request, "programme/overview.html", {
        "programme": programme, "days": days.items(), "parts": parts,
        "editable_ids": {p.pk for p in editable}, "can_add": bool(editable),
        "can_locations": access.can_edit_locations(request.user, programme),
        "can_settings": access.can_edit_settings(request.user, programme),
        "can_backing": access.can_see_backing(request.user, programme),
        "frozen": access.is_frozen(programme),
        "problems": checks.problems(programme),
        "unplaced": checks.unplaced(programme).count(),
    })


@login_required
def programme_settings(request, number):
    programme = _programme(request, number)
    if not access.can_edit_settings(request.user, programme):
        raise PermissionDenied
    form = ProgrammeForm(request.POST or None, instance=programme)
    parts = PartFormSet(request.POST or None, instance=programme, prefix="parts")
    if request.method == "POST" and form.is_valid() and parts.is_valid():
        from .builder import BuildError, set_day_parts

        try:
            with transaction.atomic():
                form.save()
                for part in parts.save():
                    setup.part_group(part)
                for day in programme.days():
                    chosen = request.POST.getlist(f"day-{day.isoformat()}")
                    if chosen and {int(c) for c in chosen if c.isdigit()} != {p.pk for p in programme.day_parts(day)}:
                        set_day_parts(programme, request.user, day, chosen)
        except ProtectedError:
            messages.error(request, "A part that still has sessions cannot be deleted: move or delete its sessions first.")
        except BuildError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Saved.")
            return redirect("programme:overview", number=number)
    days = [(day, {p.pk for p in programme.day_parts(day)}) for day in programme.days()]
    return render(request, "programme/settings.html", {"programme": programme, "form": form, "parts": parts,
                                                      "days": days, "all_parts": programme.parts.all()})


@login_required
def locations(request, number):
    programme = _programme(request, number)
    return render(request, "programme/locations.html", {
        "programme": programme, "locations": programme.locations.all(),
        "can_edit": access.can_edit_locations(request.user, programme)})


@login_required
def location_edit(request, number, pk=None):
    programme = _programme(request, number)
    if not access.can_edit_locations(request.user, programme):
        raise PermissionDenied
    location = get_object_or_404(Location, pk=pk, programme=programme) if pk else Location(programme=programme)
    if request.method == "POST" and request.POST.get("delete") and pk:
        try:
            location.delete()
        except ProtectedError:
            messages.error(request, f"{location} is used by sessions: give them another location first.")
            return redirect("programme:location", number=number, pk=pk)
        messages.success(request, f"{location} deleted.")
        return redirect("programme:locations", number=number)
    form = LocationForm(request.POST or None, instance=location)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{location} saved.")
        return redirect("programme:locations", number=number)
    return render(request, "programme/location.html", {"programme": programme, "form": form, "location": location})


@login_required
def session_edit(request, number, pk=None):
    programme = _programme(request, number)
    parts = access.editable_parts(request.user, programme)
    if pk:
        session = get_object_or_404(Session.objects.select_related("part"), pk=pk, programme=programme)
        if session.part not in parts:
            return render(request, "programme/session_view.html", {"programme": programme, "session": session})
    else:
        if not parts:
            raise PermissionDenied
        session = Session(programme=programme)
        wanted = request.GET.get("part")
        session.part = next((p for p in parts if str(p.pk) == wanted), parts[0])
        if request.GET.get("date"):
            session.date = request.GET["date"]
    if request.method == "POST" and request.POST.get("delete") and pk:
        session.delete()
        messages.success(request, "Session deleted.")
        return redirect("programme:overview", number=number)
    data = request.POST or None
    form = SessionForm(data, instance=session, programme=programme, parts=parts)
    people = PersonFormSet(data, instance=session, prefix="people")
    items = ItemFormSet(data, instance=session, prefix="items", submissions=_submissions(programme))
    if request.method == "POST" and form.is_valid() and people.is_valid() and items.is_valid():
        with transaction.atomic():
            if {"cancelled", "change_note"} & set(form.changed_data) and (form.instance.cancelled or form.instance.change_note):
                from django.utils import timezone

                form.instance.changed = timezone.now()
            session = form.save()
            people.instance = items.instance = session
            people.save()
            items.save()
            _renumber(session)
        messages.success(request, f"{session} saved.")
        if request.POST.get("again"):
            return redirect("programme:session", number=number, pk=session.pk)
        return redirect("programme:overview", number=number)
    return render(request, "programme/session.html", {
        "programme": programme, "session": session, "form": form, "people": people, "items": items,
        "authors": _author_lists(programme)})


def _renumber(session):
    for order, item in enumerate(session.items.order_by("order", "pk"), start=1):
        if item.order != order:
            SessionItem.objects.filter(pk=item.pk).update(order=order)
    for order, person in enumerate(session.people.order_by("order", "pk"), start=1):
        if person.order != order:
            type(person).objects.filter(pk=person.pk).update(order=order)


def _author_lists(programme):
    """{submission id: [author names]}, for choosing the presenter."""
    lists = {}
    for s in _submissions(programme).select_related("paper").prefetch_related("paper__authors"):
        if s.paper_id:
            names = [f"{a.first_name} {a.last_name}".strip() for a in s.paper.authors.all()]
        else:
            names = [a.get("name", "") for a in s.registered_authors if a.get("name")]
        lists[s.pk] = names
    return lists


@login_required
def papers(request, number):
    """The papers not yet placed, to add to sessions in batches; and where the others are."""
    programme = _programme(request, number)
    parts = access.editable_parts(request.user, programme)
    targets = (programme.sessions.filter(part__in=parts, kind__in=Session.WITH_PAPERS)
               .select_related("location").order_by("date", "start", "code"))
    if request.method == "POST":
        session = get_object_or_404(targets, pk=request.POST.get("session"))
        chosen = checks.unplaced(programme).filter(pk__in=request.POST.getlist("paper")).select_related("presentation")
        presentation = (SessionItem.Presentation.POSTER if session.kind == Session.Kind.POSTERS
                        else SessionItem.Presentation.TALK)
        last = session.items.count()
        added = 0
        for added, submission in enumerate(chosen, start=1):
            answer = getattr(submission, "presentation", None)
            SessionItem.objects.create(session=session, submission=submission, order=last + added,
                                       presentation=presentation, presenter=answer.presenter if answer else "")
        if added:
            messages.success(request, f"{added} paper{'s' if added != 1 else ''} added to {session}.")
        else:
            messages.warning(request, "Tick the papers to add.")
        return redirect("programme:papers", number=number)
    placed = (SessionItem.objects.filter(session__programme=programme, submission__isnull=False)
              .select_related("submission__track", "session__location").order_by("session__date", "session__start",
                                                                                  "session__code", "order"))
    return render(request, "programme/papers.html", {
        "programme": programme, "unplaced": checks.unplaced(programme), "placed": placed, "targets": targets})


# ---------------------------------------------------------------- registrations and backing

@login_required
def registrations(request, number):
    """The organisers' export of registrations, and which registration types back papers."""
    import tempfile
    from pathlib import Path

    from . import backing
    from .models import RegistrationType

    programme = _programme(request, number)
    if not access.can_see_backing(request.user, programme):
        raise PermissionDenied
    can_manage = access.can_manage_registrations(request.user, programme)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        if request.POST.get("action") == "upload":
            upload = request.FILES.get("file")
            if not upload or Path(upload.name).suffix.lower() not in (".xlsx", ".csv"):
                messages.error(request, "Choose the export of registrations (.xlsx or .csv).")
            else:
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / f"registrations{Path(upload.name).suffix.lower()}"
                    path.write_bytes(upload.read())
                    try:
                        report = backing.import_registrations(programme, path)
                    except ValueError as error:
                        messages.error(request, str(error))
                    else:
                        messages.success(request, f"{report['created']} new, {report['updated']} updated, "
                                                  f"{report['inactive']} no longer in the export.")
                        if report["no_paid_column"]:
                            messages.warning(request, "The export has no payment column: every registration in it "
                                                      "is taken as paid.")
        elif request.POST.get("action") == "types":
            ticked = set(request.POST.getlist("counts"))
            for rtype in programme.registration_types.all():
                rtype.counts, rtype.decided = str(rtype.pk) in ticked, True
                rtype.save(update_fields=["counts", "decided"])
            messages.success(request, "Saved.")
        return redirect("programme:registrations", number=number)
    rows = backing.assess(programme)
    backs = backing.backers(rows)
    regs = list(programme.registrations.select_related("type"))
    for r in regs:
        r.backs = [row.submission.conftool_id for row in backs.get(r.pk, [])]
    types = list(programme.registration_types.all())
    return render(request, "programme/registrations.html", {
        "programme": programme, "registrations": regs, "types": types, "can_manage": can_manage,
        "undecided": [t for t in types if not t.decided],
        "counting": sum(1 for r in regs if r.counts)})


@login_required
def backing_report(request, number):
    """Every paper's backing and the authors' answer; emails, backers and withdrawals."""
    from django.http import JsonResponse

    from . import backing
    from .forms import BackingEmailsForm
    from .models import PaperPresentation

    programme = _programme(request, number)
    if not access.can_see_backing(request.user, programme):
        raise PermissionDenied
    can_manage = access.can_manage_backing(request.user, programme)
    action = request.POST.get("action") if request.method == "POST" else None
    if action and not can_manage:
        raise PermissionDenied
    if action in ("request", "reminder", "warning"):
        after = request.POST.get("after", "0")
        return JsonResponse(backing.send_batch(programme, action, request.user, n=10,
                                               after=int(after) if after.isdigit() else 0))
    emails = BackingEmailsForm(request.POST if action == "emails" else None, instance=programme)
    if action == "emails":
        if emails.is_valid():
            emails.save()
            messages.success(request, "Saved.")
            return redirect("programme:backing", number=number)
    elif action == "backer":
        submission = _submissions(programme).filter(pk=request.POST.get("paper")).first()
        registration = programme.registrations.filter(pk=request.POST.get("registration")).first()
        if submission is None:
            messages.error(request, "Choose the paper.")
        else:
            presentation, _ = PaperPresentation.objects.get_or_create(submission=submission)
            presentation.registration = registration
            presentation.save(update_fields=["registration"])
            from apps.production.models import Event

            Event.objects.create(submission=submission, user=request.user,
                                 action=f"backer chosen by the editors: {registration}" if registration
                                 else "the editors' choice of backer removed")
            messages.success(request, f"Paper {submission.conftool_id}: "
                                      + (f"backed by {registration}." if registration else "backer left to the matching."))
        return redirect("programme:backing", number=number)
    elif action == "link_slides":
        from . import slides

        count = slides.link_all(programme)
        messages.success(request, f"Slides are on the pages of {count} published paper{'s' if count != 1 else ''}.")
        return redirect("programme:backing", number=number)
    elif action == "withdraw":
        done, refused = [], []
        for submission in _submissions(programme).filter(pk__in=request.POST.getlist("paper")):
            try:
                backing.withdraw(submission, request.user, request.POST.get("reason") or "no registration backs the paper")
                done.append(str(submission.conftool_id))
            except ValueError as error:
                refused.append(str(error))
        if done:
            messages.success(request, f"Withdrawn: {', '.join(done)}.")
        for text in refused:
            messages.error(request, text)
        return redirect("programme:backing", number=number)
    rows = backing.assess(programme)
    placed = {}
    for item in SessionItem.objects.filter(session__programme=programme, submission__isnull=False).select_related("session"):
        placed.setdefault(item.submission_id, []).append(item.session)
    for row in rows:
        row.sessions = placed.get(row.submission.pk, [])
    wanted = request.GET.get("status", "")
    shown = [r for r in rows if not wanted or r.status == wanted or r.answer == wanted
             or (wanted == "unanswered" and not r.answer)]
    from collections import Counter

    counts = Counter(r.status for r in rows)
    answers = Counter(r.answer or "unanswered" for r in rows)
    return render(request, "programme/backing.html", {
        "programme": programme, "rows": shown, "all_rows": rows, "can_manage": can_manage, "emails": emails,
        "wanted": wanted, "counts": [(key, label, counts.get(key, 0)) for key, label in backing.Backing.LABELS.items()],
        "answers": [(key, label, answers.get(key, 0)) for key, label in
                    [("unanswered", "No answer yet")] + list(PaperPresentation.Answer.choices)],
        "registrations": programme.registrations.filter(active=True).select_related("type"),
        "to_request": len(backing.to_request(programme)), "to_remind": len(backing.to_remind(programme)),
        "to_warn": len(backing.to_warn(programme)),
        "no_registrations": not programme.registrations.exists(),
        "slides": PaperPresentation.objects.filter(submission__production__conference=programme.conference)
                  .exclude(slides="").count(),
        "defaults": {"request_subject": backing.DEFAULT_REQUEST_SUBJECT, "warning_subject": backing.DEFAULT_WARNING_SUBJECT},
    })


@login_required
def room_signs(request, number):
    from django.http import HttpResponse

    from .signs import room_signs as make

    programme = _programme(request, number)
    home = getattr(programme.conference, "site_home", None)
    if home is None:
        messages.error(request, "The conference has no website yet, so the signs have nothing to link to.")
        return redirect("programme:locations", number=number)
    locations = programme.locations.all()
    wanted = request.GET.get("location")
    if wanted:
        locations = locations.filter(pk=wanted)
    response = HttpResponse(make(programme, locations, home), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="iglc{number}-room-signs.pdf"'
    return response


@login_required
def booklet(request, number):
    """The booklet also while the programme is hidden, for the people who work on it."""
    from django.http import HttpResponse

    from .booklet import booklet as make

    programme = _programme(request, number)
    response = HttpResponse(make(programme, getattr(programme.conference, "site_home", None)),
                            content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="iglc{number}-programme.pdf"'
    return response


@login_required
def plan(request, number):
    """Drag and drop: papers into sessions, between sessions and in order, one day at a time."""
    import json
    from collections import OrderedDict

    from django.http import JsonResponse

    programme = _programme(request, number)
    parts = access.editable_parts(request.user, programme)
    sessions_all = programme.sessions.filter(kind__in=Session.WITH_PAPERS).select_related("location", "part")
    days = sorted(set(sessions_all.values_list("date", flat=True)))
    wanted = request.GET.get("day") or request.POST.get("day") or ""
    day = next((d for d in days if d.isoformat() == wanted), days[0] if days else None)
    shown = [s for s in sessions_all.filter(date=day, part__in=parts).prefetch_related(
        "items__submission__track", "items__submission__presentation")] if day else []
    if request.method == "POST":
        try:
            layout = json.loads(request.body.decode("utf-8")).get("sessions", {})
            _save_plan(programme, shown, layout)
        except (ValueError, KeyError, SessionItem.DoesNotExist) as error:
            return JsonResponse({"error": f"Not saved: {error}"}, status=400)
        return JsonResponse({"ok": True})
    slots = OrderedDict()
    for s in shown:
        slots.setdefault((s.start, s.end), []).append(s)
    return render(request, "programme/plan.html", {
        "programme": programme, "days": days, "day": day, "slots": slots.items(), "parts": parts,
        "unplaced": checks.unplaced(programme).select_related("presentation"),
        "tracks": programme.conference.tracks.all()})


def _save_plan(programme, shown, layout):
    from .models import PaperPresentation

    shown_ids = {s.pk: s for s in shown}
    items = {i.pk: i for i in SessionItem.objects.filter(session__in=shown).select_related("submission")}
    by_paper = {i.submission_id: i for i in items.values() if i.submission_id}
    pool = {s.pk: s for s in checks.unplaced(programme)}
    seen = set()
    with transaction.atomic():
        for session_id, entries in layout.items():
            session = shown_ids.get(int(session_id))
            if session is None:
                raise ValueError("a session that cannot be edited here")
            for order, entry in enumerate(entries, start=1):
                kind, pk = entry[0], int(entry[1:])
                if kind == "i":
                    item = items[pk]
                elif pk in by_paper:
                    item = by_paper[pk]
                elif pk in pool:
                    answer = PaperPresentation.objects.filter(submission_id=pk).first()
                    item = SessionItem(submission=pool[pk], presenter=answer.presenter if answer else "")
                else:
                    raise ValueError(f"paper {pk} is placed elsewhere or withdrawn")
                if item.session_id != session.pk and item.submission_id:
                    item.presentation = (SessionItem.Presentation.POSTER if session.kind == Session.Kind.POSTERS
                                         else SessionItem.Presentation.TALK)
                item.session, item.order = session, order
                item.save()
                seen.add(item.pk)
        for item in items.values():
            if item.pk not in seen and item.submission_id:
                item.delete()  # dragged back to the papers not placed


# ---------------------------------------------------------------- the builder (builder.py)

@login_required
def build(request, number):
    import json

    from django.http import JsonResponse

    from . import builder

    programme = _programme(request, number)
    days = programme.days()
    wanted = request.GET.get("day", "")
    day = next((d for d in days if d.isoformat() == wanted), None)
    if day is None:  # the conference's first day, else the first day with sessions
        with_sessions = sorted(set(programme.sessions.values_list("date", flat=True)))
        start = programme.conference.start_date
        day = (start if start in days else
               with_sessions[0] if with_sessions and with_sessions[0] in days else days[0])
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            return JsonResponse(builder.apply(programme, request.user, day, data))
        except (ValueError, builder.BuildError) as error:
            return JsonResponse({"error": str(error)}, status=400)
    if request.GET.get("format") == "json":
        return JsonResponse(builder.state(programme, request.user, day))
    from django.middleware.csrf import get_token

    return render(request, "programme/builder.html", {
        "programme": programme, "day": day,
        "can_edit": bool(access.editable_parts(request.user, programme)),
        "config": {"url": request.path, "day": day.isoformat(), "csrf": get_token(request),
                   "session_url": reverse("programme:session", args=[number, 0]),
                   "contributions_url": reverse("programme:contributions", args=[number])},
    })


@login_required
def spreadsheet(request, number):
    """Export the programme to Excel (GET), or import a sheet (POST)."""
    import tempfile
    from pathlib import Path

    from django.http import HttpResponse

    from . import builder
    from . import spreadsheet as sheets

    programme = _programme(request, number)
    if request.method == "GET":
        response = HttpResponse(sheets.export(programme), content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        response["Content-Disposition"] = f'attachment; filename="iglc{number}-programme.xlsx"'
        return response
    upload = request.FILES.get("file")
    if not upload or Path(upload.name).suffix.lower() not in (".xlsx", ".xlsm"):
        messages.error(request, "Choose an Excel file (.xlsx).")
        return redirect("programme:build", number=number)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "programme.xlsx"
        path.write_bytes(upload.read())
        try:
            report = sheets.import_sheet(programme, request.user, path, bool(request.POST.get("replace")))
        except builder.BuildError as error:
            messages.error(request, str(error))
            return redirect("programme:build", number=number)
    messages.success(request, f"{report['added']} sessions added, {report['updated']} updated.")
    for problem in report["problems"][:20]:
        messages.warning(request, problem)
    return redirect("programme:build", number=number)


# ---------------------------------------------------------------- contributions

@login_required
def contributions(request, number):
    from .forms import ContributionForm
    from .models import Contribution

    programme = _programme(request, number)
    parts = access.editable_parts(request.user, programme)
    if request.method == "POST":
        if not parts:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "speakers":
            count = _contributions_from_speakers(programme, parts)
            messages.success(request, f"{count} added from Speakers.")
        elif action == "delete":
            contribution = get_object_or_404(Contribution, pk=request.POST.get("id"), programme=programme,
                                             part__in=parts)
            contribution.delete()
            messages.success(request, "Deleted.")
        else:
            instance = (get_object_or_404(Contribution, pk=request.POST.get("id"), programme=programme, part__in=parts)
                        if request.POST.get("id") else Contribution(programme=programme))
            form = ContributionForm(request.POST, instance=instance, parts=parts)
            if form.is_valid():
                form.save()
                messages.success(request, "Saved.")
            else:
                for field, errors in form.errors.items():
                    messages.error(request, f"{field}: {' '.join(errors)}")
        return redirect("programme:contributions", number=number)
    items = programme.contributions.select_related("part", "speaker").prefetch_related("programme_items__session")
    return render(request, "programme/contributions.html", {
        "programme": programme, "contributions": items, "can_edit": bool(parts),
        "form": ContributionForm(parts=parts) if parts else None, "editable_ids": {p.pk for p in parts},
        "kinds": Contribution.Kind.choices, "parts": parts})


def _contributions_from_speakers(programme, parts) -> int:
    """A contribution for every speaker (under Speakers) who has none yet."""
    from apps.conferences.models import Speaker

    from .models import Contribution, Part

    by_kind = {p.kind: p for p in parts}
    taken = set(programme.contributions.exclude(speaker=None).values_list("speaker_id", flat=True))
    count = 0
    for speaker in Speaker.objects.filter(conference=programme.conference).exclude(pk__in=taken):
        group = (speaker.group or "").lower()
        part = (by_kind.get(Part.Kind.INDUSTRY) if "industry" in group else
                by_kind.get(Part.Kind.WORKSHOP) if "workshop" in group else
                by_kind.get(Part.Kind.PHD) if "phd" in group or "doctoral" in group else
                by_kind.get(Part.Kind.ACADEMIC)) or parts[0]
        kind = Contribution.Kind.KEYNOTE if "keynote" in group else Contribution.Kind.TALK
        speakers = f"{speaker.name} ({speaker.affiliation})" if speaker.affiliation else speaker.name
        Contribution.objects.create(programme=programme, part=part, kind=kind, speaker=speaker,
                                    title=(speaker.talk_title or f"{speaker.name}")[:300], speakers=speakers[:300])
        count += 1
    return count
