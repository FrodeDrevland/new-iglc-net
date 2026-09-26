"""Tracks in the conference workspace (/manage/<number>/tracks/): the scientific chairs decide the
conference's tracks. They are kept in the archive's conference record (archive.ConferenceTrack), which the
website ("tracks" block), the programme and the proceedings all use, so a change shows at once.

A track that papers, sessions or editors already use cannot be removed here (the IGLC can move them
first); renaming it is fine.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from apps.archive.models import Conference, ConferenceTrack

from . import roles


class TrackForm(forms.ModelForm):
    class Meta:
        model = ConferenceTrack
        fields = ("title", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False  # an empty new row is ignored

    def has_changed(self):
        # a new row counts only once it has a title
        return super().has_changed() and bool(self.instance.pk or self.data.get(self.add_prefix("title"), "").strip())


def uses(track) -> int:
    """How many papers, submissions, sessions, track chairs and editors use this track."""
    count = 0
    for relation in ConferenceTrack._meta.get_fields(include_hidden=True):
        if not (relation.auto_created and not relation.concrete) or relation.related_model is None:
            continue
        if getattr(relation.related_model._meta, "auto_created", False):
            continue  # the table behind a many-to-many field; the field's own model is counted
        count += relation.related_model._default_manager.filter(**{relation.field.name: track}).count()
    return count


class BaseTracks(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.instance.pk and form.cleaned_data.get("DELETE") and uses(form.instance):
                raise forms.ValidationError(
                    f"'{form.instance.title}' is in use (by papers, sessions or editors), so it cannot be removed. "
                    "Rename it instead, or ask the webmaster.")
            if form.has_changed() and not form.cleaned_data.get("DELETE") and not form.cleaned_data.get("title"):
                form.add_error("title", "Give the track a title (or tick Remove).")


def track_formset():
    return forms.inlineformset_factory(Conference, ConferenceTrack, form=TrackForm, formset=BaseTracks,
                                       extra=1, can_delete=True)


def tracks(request, number):
    from .workspace_views import _context

    conference, context = _context(request, number)
    can_edit = roles.can_edit_tracks(request.user, conference)
    if request.method == "POST" and not can_edit:
        raise PermissionDenied
    Formset = track_formset()
    queryset = conference.tracks.order_by("order", "title")
    formset = Formset(request.POST or None, instance=conference, prefix="tracks", queryset=queryset)
    if not can_edit:
        for form in formset.forms:
            for field in form.fields.values():
                field.disabled = True
    if request.method == "POST" and formset.is_valid():
        formset.save(commit=False)
        for gone in formset.deleted_objects:
            gone.delete()
        kept = []
        for form in formset.forms:
            if form in formset.deleted_forms or not form.cleaned_data.get("title"):
                continue
            track = form.save(commit=False)
            track.conference = conference
            kept.append(track)
        move = request.POST.get("move", "")
        if ":" in move:
            prefix, direction = move.rsplit(":", 1)
            at = next((i for i, track in enumerate(kept) if _prefix_of(formset, track) == prefix), None)
            other = None if at is None else (at - 1 if direction == "up" else at + 1)
            if at is not None and 0 <= other < len(kept):
                kept[at], kept[other] = kept[other], kept[at]
        for order, track in enumerate(kept, 1):
            track.order = order
            track.save()
        if not move:
            messages.success(request, "The tracks are saved. The website, the programme and the proceedings "
                                      "use them at once.")
        return redirect("conference:tracks", number)
    rows = [(form, uses(form.instance) if form.instance.pk else 0) for form in formset.forms]
    context.update({"tab": "tracks", "formset": formset, "rows": rows, "can_edit_tracks": can_edit})
    return render(request, "conferences/admin/tracks.html", context)


def _prefix_of(formset, track):
    for form in formset.forms:
        if form.instance is track:
            return form.prefix
    return None
