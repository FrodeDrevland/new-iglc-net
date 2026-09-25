"""The programme of a conference: parts, locations, sessions, the people in them and the papers.

    Programme           one per conference (the archive's record), with its days and time zone
      Part              academic conference, industry day, workshop day, PhD summer school ...;
                        each has its own group of editors and may be public or not
      Location          rooms at the venue and places elsewhere, with a map link
      Session           a time slot in a part, at a location
        SessionPerson   chairs, facilitators, speakers ...
        SessionItem     a paper (from the proceedings production) presented as a talk or a poster,
                        or a free item

    RegistrationType, Registration     the organisers' export of registrations; only some types
                                       (the technical/academic conference) back papers
    PaperPresentation                  per paper: the authors' answer (presented, by whom, backed by
                                       whom), the emails sent, and the editors' choice of backer

Who may edit what is in access.py; the checks across sessions (clashes, papers placed twice)
in checks.py; the registration backing in backing.py. See docs/programme.md.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models
from wagtail.images import get_image_model_string

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_time_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Not a time zone. Give it as Region/City, e.g. Europe/Berlin.")


def validate_colour(value):
    if not HEX.match(value or ""):
        raise ValidationError("Give the colour as # and six hexadecimal digits, e.g. #365a91.")


class Programme(models.Model):
    class Status(models.TextChoices):
        HIDDEN = "hidden", "Hidden (being prepared)"
        PROVISIONAL = "provisional", "Provisional (public, may change)"
        FINAL = "final", "Final"

    conference = models.OneToOneField("archive.Conference", on_delete=models.CASCADE, related_name="programme")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.HIDDEN,
                              help_text="Hidden: only the editors see it. Provisional: public, marked as such.")
    time_zone = models.CharField(max_length=60, validators=[validate_time_zone],
                                 help_text="Where the conference takes place, e.g. Europe/Berlin. Used for "
                                           "calendar files.")
    first_day = models.DateField(help_text="The first day with a session, e.g. of the PhD summer school.")
    last_day = models.DateField()
    chairs = models.ForeignKey("auth.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                               help_text="The conference chairs: they edit every part and the locations.")
    notice = models.CharField(max_length=300, blank=True,
                              help_text="A short notice at the top of every programme page, e.g. about a late change.")
    author_deadline = models.DateField(
        "deadline for authors", null=True, blank=True,
        help_text="By when every paper must be backed by a registration and its presentation confirmed.")
    request_subject = models.CharField("confirmation email: subject", max_length=300, blank=True)
    request_body = models.TextField("confirmation email: text", blank=True)
    warning_subject = models.CharField("warning email: subject", max_length=300, blank=True)
    warning_body = models.TextField("warning email: text", blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-conference__number"]

    def __str__(self):
        return f"Programme IGLC {self.conference.number}"

    def clean(self):
        if self.first_day and self.last_day and self.last_day < self.first_day:
            raise ValidationError({"last_day": "The last day is before the first."})

    @property
    def number(self):
        return self.conference.number

    @property
    def is_public(self):
        return self.status != self.Status.HIDDEN

    @property
    def tz(self):
        return ZoneInfo(self.time_zone)

    def days(self):
        day, days = self.first_day, []
        while day <= self.last_day:
            days.append(day)
            day += timedelta(days=1)
        return days

    def organiser_group_name(self):
        return f"IGLC {self.conference.number} organisers"


class Part(models.Model):
    class Kind(models.TextChoices):
        ACADEMIC = "academic", "Academic conference"
        INDUSTRY = "industry", "Industry day"
        WORKSHOP = "workshop", "Workshop day"
        PHD = "phd", "PhD summer school"
        OTHER = "other", "Other"

    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="parts")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    name = models.CharField(max_length=120)
    colour = models.CharField(max_length=7, default="#365a91", validators=[validate_colour],
                              help_text="Marks the part's sessions, as #rrggbb.")
    description = models.TextField(blank=True)
    public = models.BooleanField(default=True, help_text="Untick to show the part only through its private link "
                                                         "(e.g. the PhD summer school).")
    editors = models.ForeignKey("auth.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="The people who edit this part (besides the conference chairs).")
    sort_order = models.PositiveIntegerField(default=0)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False,
                             help_text="The private link of a part that is not public.")

    class Meta:
        ordering = ["programme", "sort_order", "pk"]

    def __str__(self):
        return self.name


class Location(models.Model):
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=200, help_text="For example 'Room A 101' or 'Hofbräuhaus'.")
    building = models.CharField("building or floor", max_length=200, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    map_url = models.URLField("map link", max_length=1000, blank=True,
                              help_text="Mazemap, Google Maps or the venue's own map.")
    floor_plan = models.ForeignKey(get_image_model_string(), null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    address = models.CharField(max_length=300, blank=True, help_text="For places away from the venue.")
    accessibility = models.CharField(max_length=300, blank=True, help_text="For example 'Step-free via the lift'.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Position in lists and in the grid.")

    class Meta:
        ordering = ["programme", "sort_order", "name"]

    def __str__(self):
        return self.name


class Session(models.Model):
    class Kind(models.TextChoices):
        PAPERS = "papers", "Paper session"
        POSTERS = "posters", "Poster session"
        KEYNOTE = "keynote", "Keynote"
        PANEL = "panel", "Panel"
        WORKSHOP = "workshop", "Workshop"
        INDUSTRY = "industry", "Industry session"
        BREAK = "break", "Break"
        MEAL = "meal", "Meal"
        SOCIAL = "social", "Social event"
        MEETING = "meeting", "Meeting (e.g. the Annual Business Meeting)"
        OTHER = "other", "Other"

    WITH_PAPERS = {Kind.PAPERS, Kind.POSTERS}

    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="sessions")
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="sessions")
    date = models.DateField()
    start = models.TimeField()
    end = models.TimeField()
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name="sessions",
                                 help_text="Required, except for breaks.")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PAPERS)
    code = models.CharField(max_length=20, blank=True, help_text="Short name, e.g. 3B.")
    title = models.CharField(max_length=300, blank=True, help_text="Blank: the kind of session, e.g. 'Break'.")
    plenary = models.BooleanField(default=False, help_text="For everyone in the part: nothing runs in parallel.")
    track = models.ForeignKey("archive.ConferenceTrack", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    keynote = models.ForeignKey("conferences.Keynote", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+", help_text="A speaker from the keynotes page.")
    notes = models.TextField(blank=True, help_text="Shown with the session.")
    cancelled = models.BooleanField(default=False, help_text="Shown struck through, and cancelled in calendars.")
    change_note = models.CharField(
        max_length=200, blank=True,
        help_text="A late change visitors should notice, e.g. 'Moved to Room 102' or 'Starts at 14:15'.")
    changed = models.DateTimeField(null=True, blank=True, editable=False,
                                   help_text="When the change note or cancellation was last set.")
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start", "end", "location__sort_order", "code", "pk"]

    def __str__(self):
        label = f"{self.code} " if self.code else ""
        return f"{label}{self.display_title} ({self.date:%a %d %b} {self.start:%H:%M})"

    @property
    def display_title(self):
        if self.title:
            return self.title
        if self.kind == self.Kind.KEYNOTE and self.keynote_id:
            return f"Keynote: {self.keynote.name}"
        return self.get_kind_display()

    @property
    def minutes(self):
        start = datetime.combine(self.date, self.start)
        return int((datetime.combine(self.date, self.end) - start).total_seconds() // 60)

    def overlaps(self, other) -> bool:
        return self.date == other.date and self.start < other.end and other.start < self.end

    def starts_at(self):
        return datetime.combine(self.date, self.start, tzinfo=self.programme.tz)

    def ends_at(self):
        return datetime.combine(self.date, self.end, tzinfo=self.programme.tz)

    def clean(self):
        errors = {}
        if self.start and self.end and self.end <= self.start:
            errors["end"] = "The session must end after it starts."
        programme = self.programme if self.programme_id else None
        if programme and self.date and not (programme.first_day <= self.date <= programme.last_day):
            errors["date"] = (f"Outside the programme's days ({programme.first_day:%d %b} to "
                              f"{programme.last_day:%d %b %Y}). The conference chairs can extend them.")
        if not self.location_id and self.kind != self.Kind.BREAK:
            errors["location"] = ("A plenary session needs a location." if self.plenary
                                  else "Every session except breaks needs a location.")
        if programme:
            if self.part_id and self.part.programme_id != programme.pk:
                errors["part"] = "Not a part of this programme."
            if self.location_id and self.location.programme_id != programme.pk:
                errors["location"] = "Not a location of this programme."
            if self.track_id and self.track.conference_id != programme.conference_id:
                errors["track"] = "Not a track of this conference."
        if errors:
            raise ValidationError(errors)


class SessionPerson(models.Model):
    class Role(models.TextChoices):
        CHAIR = "chair", "Chair"
        CO_CHAIR = "co_chair", "Co-chair"
        FACILITATOR = "facilitator", "Facilitator"
        MODERATOR = "moderator", "Moderator"
        PANELLIST = "panellist", "Panellist"
        SPEAKER = "speaker", "Speaker"

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="people")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CHAIR)
    name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=300, blank=True)
    person = models.ForeignKey("archive.AuthorPerson", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", help_text="Links the name to the person's author page.")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["session", "order", "pk"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


class SessionItem(models.Model):
    class Presentation(models.TextChoices):
        TALK = "talk", "Talk"
        POSTER = "poster", "Poster"

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=0)
    submission = models.ForeignKey("production.Submission", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="programme_items", verbose_name="paper")
    presentation = models.CharField(max_length=10, choices=Presentation.choices, default=Presentation.TALK)
    presenter = models.CharField(max_length=200, blank=True, help_text="One of the paper's authors.")
    title = models.CharField(max_length=300, blank=True, help_text="For an item that is not a paper.")
    speaker = models.CharField(max_length=200, blank=True, help_text="For an item that is not a paper.")
    minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    board = models.CharField("poster board", max_length=20, blank=True)

    class Meta:
        ordering = ["session", "order", "pk"]

    def __str__(self):
        return self.display_title

    def clean(self):
        if not self.submission_id and not self.title:
            raise ValidationError("Choose a paper or give a title.")
        if self.submission_id and self.session_id and (
                self.submission.production.conference_id != self.session.programme.conference_id):
            raise ValidationError({"submission": "Not a paper of this conference."})

    @property
    def paper(self):
        """The published paper in the archive, once published."""
        return self.submission.paper if self.submission_id and self.submission.paper_id else None

    @property
    def display_title(self):
        if self.paper:
            return self.paper.title
        if self.submission_id:
            return self.submission.title
        return self.title

    def author_names(self) -> list[str]:
        if self.paper:
            return [f"{a.first_name} {a.last_name}".strip() for a in self.paper.authors.all()]
        if self.submission_id:
            return [a.get("name", "") for a in self.submission.registered_authors if a.get("name")]
        return [self.speaker] if self.speaker else []

    @property
    def url(self):
        return self.paper.get_absolute_url() if self.paper else ""


# ---------------------------------------------------------------- registrations and backing

class RegistrationType(models.Model):
    """A registration type from the organisers' export. Only types for the technical/academic
    conference back papers; new types start as not counting, until someone ticks them."""

    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="registration_types")
    name = models.CharField(max_length=200)
    counts = models.BooleanField("backs papers", default=False,
                                 help_text="A registration for the technical/academic conference.")
    decided = models.BooleanField(default=False, editable=False, help_text="Someone has looked at it.")

    class Meta:
        ordering = ["programme", "name"]
        unique_together = [("programme", "name")]

    def __str__(self):
        return self.name


class Registration(models.Model):
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="registrations")
    key = models.CharField(max_length=200, help_text="The registration's ID in the export, or its email address.")
    reference = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=300)
    email = models.EmailField(blank=True)
    type = models.ForeignKey(RegistrationType, null=True, blank=True, on_delete=models.SET_NULL, related_name="registrations")
    paid = models.BooleanField(default=False)
    active = models.BooleanField(default=True, help_text="In the latest export.")
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["programme", "name"]
        unique_together = [("programme", "key")]

    def __str__(self):
        return self.name

    @property
    def counts(self):
        return self.active and self.paid and self.type_id is not None and self.type.counts


class PaperPresentation(models.Model):
    """One accepted paper: will it be presented, by whom, and which registered author backs it.
    The authors answer through a secret link; the editors can choose the backer themselves."""

    class Answer(models.TextChoices):
        PRESENT = "present", "Will be presented"
        NOT_PRESENT = "not_present", "Published, not presented"
        WITHDRAW = "withdraw", "The authors withdraw it"

    submission = models.OneToOneField("production.Submission", on_delete=models.CASCADE, related_name="presentation")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    recipients = models.JSONField(default=list, blank=True)
    requested = models.DateTimeField(null=True, blank=True)
    reminded = models.DateTimeField(null=True, blank=True)
    warned = models.DateTimeField(null=True, blank=True)
    answer = models.CharField(max_length=20, choices=Answer.choices, blank=True)
    presenter = models.CharField(max_length=200, blank=True)
    backer = models.CharField("backed by", max_length=200, blank=True, help_text="The author who is registered.")
    backer_email = models.EmailField(blank=True, help_text="The address the backer registered with, if different.")
    comment = models.TextField(blank=True)
    responder = models.CharField(max_length=200, blank=True)
    responded = models.DateTimeField(null=True, blank=True)
    registration = models.ForeignKey(Registration, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="Chosen by the editors: this registration backs the paper.")

    class Meta:
        ordering = ["submission__conftool_id"]

    def __str__(self):
        return f"{self.submission.conftool_id}: {self.get_answer_display() or 'no answer'}"
