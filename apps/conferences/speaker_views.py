"""Speakers in the conference workspace (/manage/<number>/speakers/): keynote speakers and others, each
entered once. A Speakers block on any website page shows them (one group, or all), and programme sessions
link to them.

Speakers are not part of a page, so a change shows on the published website at once; "Not yet announced"
keeps a speaker off it until they may be named.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .models import Speaker


class SpeakerForm(forms.ModelForm):
    class Meta:
        model = Speaker
        fields = ("group", "name", "affiliation", "photo", "talk_title", "biography", "url", "hidden")
        labels = {"photo": "Portrait", "talk_title": "Title of the talk"}
        help_texts = {"photo": "At least 400 × 400 pixels; shown round, cut to a square around the picture's "
                               "focal point.",
                      "url": "Their page at their university or company, or on LinkedIn."}
        widgets = {"group": forms.TextInput(attrs={"list": "speaker-groups"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from wagtail.images.widgets import AdminImageChooser

        self.fields["photo"].widget = AdminImageChooser()


def grouped(speakers):
    groups: dict[str, list] = {}
    for speaker in speakers:
        groups.setdefault(speaker.group, []).append(speaker)
    return list(groups.items())


def _renumber(speakers):
    for order, speaker in enumerate(speakers):
        if speaker.sort_order != order:
            speaker.sort_order = order
            speaker.save(update_fields=["sort_order"])


def _context(request, number):
    from .workspace_views import _context as workspace_context

    conference, context = workspace_context(request, number, need="website")
    home = context["home"]
    frozen = bool(home and home.frozen) and not request.user.is_superuser
    return conference, context, frozen


def speakers(request, number):
    conference, context, frozen = _context(request, number)
    all_speakers = list(conference.speakers.select_related("photo").order_by("sort_order", "pk"))
    form = SpeakerForm(prefix="add")
    if request.method == "POST":
        if frozen:
            raise PermissionDenied
        action = request.POST.get("action", "")
        if action == "add":
            form = SpeakerForm(request.POST, prefix="add")
            if form.is_valid():
                speaker = form.save(commit=False)
                speaker.conference = conference
                same = [i for i, s in enumerate(all_speakers) if s.group == speaker.group]
                all_speakers.insert(same[-1] + 1 if same else len(all_speakers), speaker)
                speaker.sort_order = 0
                speaker.save()
                _renumber(all_speakers)
                messages.success(request, f"{speaker.name} was added"
                                          + (" (not yet announced)." if speaker.hidden else "."))
                return redirect("conference:speakers", number)
        else:
            speaker = next((s for s in all_speakers if str(s.pk) == request.POST.get("speaker")), None)
            if speaker is not None and action in ("up", "down"):
                same = [i for i, s in enumerate(all_speakers) if s.group == speaker.group]
                at = same.index(all_speakers.index(speaker))
                other = at - 1 if action == "up" else at + 1
                if 0 <= other < len(same):
                    a, b = same[at], same[other]
                    all_speakers[a], all_speakers[b] = all_speakers[b], all_speakers[a]
                    _renumber(all_speakers)
            elif speaker is not None and action == "remove":
                speaker.delete()
                messages.success(request, f"{speaker.name} was removed.")
            elif action in ("group-up", "group-down"):
                names = list(dict.fromkeys(s.group for s in all_speakers))
                name = request.POST.get("group", "")
                if name in names:
                    at = names.index(name)
                    swap = at - 1 if action == "group-up" else at + 1
                    if 0 <= swap < len(names):
                        names[at], names[swap] = names[swap], names[at]
                        _renumber([s for n in names for s in all_speakers if s.group == n])
            return redirect("conference:speakers", number)
    context.update({"tab": "speakers", "groups": grouped(all_speakers), "count": len(all_speakers),
                    "form": form, "frozen": frozen,
                    "group_names": list(dict.fromkeys(s.group for s in all_speakers if s.group))})
    return render(request, "conferences/admin/speakers.html", context)


def speaker_edit(request, number, pk):
    conference, context, frozen = _context(request, number)
    speaker = get_object_or_404(Speaker, pk=pk, conference=conference)
    form = SpeakerForm(request.POST or None, instance=speaker)
    if request.method == "POST":
        if frozen:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, f"{speaker.name} was saved.")
            return redirect("conference:speakers", number)
    context.update({"tab": "speakers", "form": form, "speaker": speaker, "frozen": frozen,
                    "group_names": list(dict.fromkeys(conference.speakers.values_list("group", flat=True)))})
    return render(request, "conferences/admin/speaker.html", context)
