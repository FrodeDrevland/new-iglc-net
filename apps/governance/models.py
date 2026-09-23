"""IGLC committees and officers, as set out in the Charter and Operating Procedures.

A seat has a start and an end date, so the site lists who serves now and keeps the history.
Phase 4 (membership and online votes) will fill these records from elections.
"""

from datetime import date

from django.db import models
from django.db.models import Q


class Committee(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, help_text="Shown above the members. Blank lines start new paragraphs.")
    charter_section = models.CharField(max_length=20, blank=True, help_text="For example §9.2")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def current_seats(self, on=None):
        return self.seats.current(on).select_related("person")

    def past_seats(self, on=None):
        on = on or date.today()
        return self.seats.filter(end_date__lte=on).select_related("person").order_by("-end_date", "last_name")


class SeatQuerySet(models.QuerySet):
    def current(self, on=None):
        on = on or date.today()
        return self.filter(Q(start_date__isnull=True) | Q(start_date__lte=on)).filter(
            Q(end_date__isnull=True) | Q(end_date__gt=on))


class Seat(models.Model):
    """One person's term in a role on a committee."""

    class Role(models.TextChoices):
        GENERAL_SECRETARY = "general_secretary", "General Secretary"
        FORMER_GENERAL_SECRETARY = "former_general_secretary", "Former General Secretary"
        MODERATOR = "moderator", "Moderator"
        ELECTED = "elected", "Elected member"
        SPARE = "spare", "Spare"
        MEMBER = "member", "Member"

    ROLE_ORDER = {r: i for i, r in enumerate(Role.values)}

    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="seats")
    role = models.CharField(max_length=40, choices=Role.choices, default=Role.ELECTED)
    is_chair = models.BooleanField("chair", default=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    affiliation = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=100, blank=True)
    person = models.ForeignKey(
        "archive.AuthorPerson", null=True, blank=True, on_delete=models.SET_NULL, related_name="seats",
        help_text="Links the name to the person's author page, if they have one.",
    )
    start_date = models.DateField(null=True, blank=True, help_text="Usually the Annual Business Meeting that elected them.")
    end_date = models.DateField(
        null=True, blank=True,
        help_text="The day the term ends (for elected members usually the Annual Business Meeting three years "
                  "later). Leave blank if open-ended.",
    )
    note = models.CharField(max_length=200, blank=True, help_text="Shown with the name, e.g. 'interim, filling a vacancy'.")

    objects = SeatQuerySet.as_manager()

    class Meta:
        ordering = ["committee", "-is_chair", "last_name", "first_name"]

    def __str__(self):
        return f"{self.full_name}, {self.get_role_display()} ({self.committee})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def term(self):
        start = self.start_date.year if self.start_date else None
        end = self.end_date.year if self.end_date else None
        if start and end:
            return f"{start}–{end}"
        if start:
            return f"since {start}"
        return f"until {end}" if end else ""

    @property
    def sort_key(self):
        return (not self.is_chair, self.ROLE_ORDER.get(self.role, 99), self.last_name, self.first_name)
