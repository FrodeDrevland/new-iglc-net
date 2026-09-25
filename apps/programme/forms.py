"""Forms of the programme's back-office pages."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory
from wagtail.images.widgets import AdminImageChooser

from .models import Location, Part, Programme, Session, SessionItem, SessionPerson


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class TimeInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, **kwargs):
        super().__init__(format="%H:%M", **kwargs)


class ProgrammeForm(forms.ModelForm):
    class Meta:
        model = Programme
        fields = ["status", "time_zone", "first_day", "last_day"]
        widgets = {"first_day": DateInput(), "last_day": DateInput()}


class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ["name", "kind", "colour", "public", "description", "sort_order"]
        widgets = {"colour": forms.TextInput(attrs={"type": "color"}),
                   "description": forms.Textarea(attrs={"rows": 2}),
                   "sort_order": forms.NumberInput(attrs={"class": "narrow"})}


PartFormSet = inlineformset_factory(Programme, Part, form=PartForm, extra=1, can_delete=True)


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "building", "capacity", "map_url", "address", "accessibility", "floor_plan", "sort_order"]
        widgets = {"floor_plan": AdminImageChooser()}


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ["part", "kind", "code", "title", "date", "start", "end", "location", "plenary", "track",
                  "keynote", "notes"]
        widgets = {"date": DateInput(), "start": TimeInput(), "end": TimeInput(),
                   "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, programme, parts, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.programme = programme
        self.fields["part"].queryset = Part.objects.filter(pk__in=[p.pk for p in parts])
        self.fields["part"].empty_label = None
        self.fields["location"].queryset = programme.locations.all()
        self.fields["track"].queryset = programme.conference.tracks.all()
        from apps.conferences.models import Keynote

        self.fields["keynote"].queryset = Keynote.objects.filter(
            page__in=_keynote_pages(programme)).order_by("sort_order")
        days = [(d.isoformat(), f"{d:%A %d %B %Y}") for d in programme.days()]
        self.fields["date"].widget = forms.Select(choices=days)


def _keynote_pages(programme):
    from apps.conferences.models import ConferenceHomePage, KeynotesPage

    home = ConferenceHomePage.objects.filter(conference=programme.conference).first()
    return KeynotesPage.objects.descendant_of(home) if home else KeynotesPage.objects.none()


class PersonForm(forms.ModelForm):
    class Meta:
        model = SessionPerson
        fields = ["role", "name", "affiliation", "order"]
        widgets = {"order": forms.NumberInput(attrs={"class": "narrow"})}


PersonFormSet = inlineformset_factory(Session, SessionPerson, form=PersonForm, extra=2, can_delete=True)


class SubmissionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        title = obj.title if len(obj.title) <= 90 else obj.title[:88] + "…"
        return f"{obj.conftool_id}: {title}"


class ItemForm(forms.ModelForm):
    class Meta:
        model = SessionItem
        fields = ["order", "submission", "presentation", "presenter", "minutes", "board", "title", "speaker"]
        field_classes = {"submission": SubmissionChoiceField}
        widgets = {"order": forms.NumberInput(attrs={"class": "narrow"}),
                   "minutes": forms.NumberInput(attrs={"class": "narrow"}),
                   "board": forms.TextInput(attrs={"class": "narrow"})}

    def __init__(self, *args, submissions=None, **kwargs):
        super().__init__(*args, **kwargs)
        if submissions is not None:
            self.fields["submission"].queryset = submissions
        self.fields["submission"].required = False


class BaseItemFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, submissions=None, **kwargs):
        self.submissions = submissions
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["submissions"] = self.submissions
        return kwargs

    @property
    def empty_form(self):
        form = self.form(auto_id=self.auto_id, prefix=self.add_prefix("__prefix__"), empty_permitted=True,
                         use_required_attribute=False, submissions=self.submissions,
                         renderer=self.renderer)
        self.add_fields(form, None)
        return form

    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            submission = form.cleaned_data.get("submission")
            if submission is None:
                continue
            if submission.pk in seen:
                form.add_error("submission", "This paper is already in the session.")
            seen.add(submission.pk)


ItemFormSet = inlineformset_factory(Session, SessionItem, form=ItemForm, formset=BaseItemFormSet, extra=3,
                                    can_delete=True)


class StartForm(forms.Form):
    conference = forms.ModelChoiceField(queryset=None)
    time_zone = forms.CharField(help_text="Where the conference takes place, as Region/City, e.g. Europe/Berlin.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.archive.models import Conference

        self.fields["conference"].queryset = Conference.objects.filter(programme__isnull=True,
                                                                       start_date__isnull=False).order_by("-number")

    def clean_time_zone(self):
        from .models import validate_time_zone

        value = self.cleaned_data["time_zone"].strip()
        validate_time_zone(value)
        return value


class BackingEmailsForm(forms.ModelForm):
    class Meta:
        model = Programme
        fields = ["author_deadline", "request_subject", "request_body", "warning_subject", "warning_body"]
        widgets = {"author_deadline": DateInput(), "request_body": forms.Textarea(attrs={"rows": 14}),
                   "warning_body": forms.Textarea(attrs={"rows": 14})}

    def __init__(self, *args, **kwargs):
        from . import backing

        super().__init__(*args, **kwargs)
        for name, default in (("request_subject", backing.DEFAULT_REQUEST_SUBJECT),
                              ("request_body", backing.DEFAULT_REQUEST_BODY),
                              ("warning_subject", backing.DEFAULT_WARNING_SUBJECT),
                              ("warning_body", backing.DEFAULT_WARNING_BODY)):
            if not getattr(self.instance, name):
                self.initial[name] = default
            self.fields[name].help_text = ("Blank: the standard text. Filled in when sent: {title}, {paper_id}, "
                                           "{number}, {deadline}, {link} (the authors' page).")
