"""The programme's pages in the back office, under /manage/programme/ (docs/programme.md)."""

from __future__ import annotations

from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
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
    return render(request, "programme/overview.html", {
        "programme": programme, "days": days.items(), "parts": programme.parts.select_related("editors"),
        "editable_ids": {p.pk for p in editable}, "can_add": bool(editable),
        "can_locations": access.can_edit_locations(request.user, programme),
        "can_settings": access.can_edit_settings(request.user, programme),
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
        try:
            with transaction.atomic():
                form.save()
                for part in parts.save():
                    setup.part_group(part)
        except ProtectedError:
            messages.error(request, "A part that still has sessions cannot be deleted: move or delete its sessions first.")
        else:
            messages.success(request, "Saved.")
            return redirect("programme:overview", number=number)
    return render(request, "programme/settings.html", {"programme": programme, "form": form, "parts": parts})


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
        chosen = checks.unplaced(programme).filter(pk__in=request.POST.getlist("paper"))
        presentation = (SessionItem.Presentation.POSTER if session.kind == Session.Kind.POSTERS
                        else SessionItem.Presentation.TALK)
        last = session.items.count()
        added = 0
        for added, submission in enumerate(chosen, start=1):
            SessionItem.objects.create(session=session, submission=submission, order=last + added,
                                       presentation=presentation)
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
