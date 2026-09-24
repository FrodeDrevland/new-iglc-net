"""The proceedings archive, ported from the 2014 ASP.NET site.

Primary keys keep the values from the old database, because every DOI points to
/papers/details/<paper id> and conference pages to /papers/conference/<conference id>.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse


class EditTracking(models.Model):
    last_edited_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


class Conference(EditTracking):
    number = models.PositiveIntegerField("conference number", unique=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    city = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=200, blank=True)
    conference_title = models.CharField(max_length=500, blank=True)
    proceedings_title = models.CharField(max_length=500, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    publication_location = models.CharField(max_length=300, blank=True)
    issn = models.CharField("ISSN", max_length=20, blank=True)
    is_published = models.BooleanField("published on website", default=False)
    papers_zip_url = models.URLField(
        "ZIP of all papers", max_length=1000, blank=True,
        help_text="Link to a ZIP file with every paper, shown on the conference page.",
    )

    class Meta:
        ordering = ["-number"]

    def __str__(self):
        parts = [f"IGLC {self.number}", self.city, str(self.year or "")]
        return " ".join(part for part in parts if part)

    @property
    def year(self):
        return self.start_date.year if self.start_date else None

    @property
    def location(self):
        return ", ".join(part for part in (self.city, self.country) if part)

    def get_absolute_url(self):
        return reverse("archive:conference", args=[self.pk])


class ProceedingsFile(models.Model):
    """A full proceedings PDF for a conference, possibly one of several volumes."""

    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name="proceedings_files")
    label = models.CharField(max_length=100, help_text="For example 'Full proceedings' or 'Volume 1'.")
    url = models.URLField(max_length=1000)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["conference", "order"]

    def __str__(self):
        return f"{self.conference}: {self.label}"


class ConferenceTrack(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name="tracks")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["conference", "title"]

    def __str__(self):
        return self.title


class Volume(EditTracking):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name="volumes")
    number = models.PositiveIntegerField("volume number")
    first_page = models.PositiveIntegerField()
    last_page = models.PositiveIntegerField()
    isbn = models.CharField("ISBN", max_length=30, blank=True)

    class Meta:
        ordering = ["conference", "number"]

    def __str__(self):
        return f"Vol {self.number}: pages {self.first_page}-{self.last_page}"


class PersonName(models.Model):
    """First and last name. A single name (mononym) is stored as the last name, which is how
    APA and the citation formats treat it."""

    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(
        max_length=200, blank=True, help_text="For a person with a single name, put it here and leave the first name empty.")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.first_name, self.last_name = self.first_name.strip(), self.last_name.strip()
        if self.first_name and not self.last_name:
            self.first_name, self.last_name = "", self.first_name
        super().save(*args, **kwargs)


class Editor(PersonName):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name="editors")
    title_and_contact = models.TextField(blank=True)
    order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class AuthorPerson(PersonName):
    """One real person across all their papers."""

    orcid = models.CharField("ORCID", max_length=40, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "author (person)"
        verbose_name_plural = "authors (people)"

    def __str__(self):
        return f"{self.last_name}, {self.first_name}".strip(", ")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("archive:author", args=[self.pk])


class Paper(EditTracking):
    class Status(models.IntegerChoices):
        # Values match the old PaperStatus enum, so migrated rows keep their meaning.
        NEW = 0, "New"
        IMPORTED = 1, "Imported"
        EDITING = 2, "Editing"
        FINALISED = 3, "Finalised"
        APPROVED = 4, "Approved"

    title = models.TextField()
    abstract = models.TextField(blank=True)
    keywords = models.TextField(blank=True)
    conference = models.ForeignKey(Conference, on_delete=models.PROTECT, related_name="papers")
    track = models.ForeignKey(
        ConferenceTrack, null=True, blank=True, on_delete=models.SET_NULL, related_name="papers"
    )
    volume = models.ForeignKey(Volume, null=True, blank=True, on_delete=models.SET_NULL, related_name="papers")
    first_page = models.PositiveIntegerField(null=True, blank=True)
    last_page = models.PositiveIntegerField(null=True, blank=True)
    doi = models.CharField("DOI", max_length=200, blank=True)
    full_text_url = models.URLField("full text (PDF) URL", max_length=1000, blank=True)
    a3_url = models.URLField("A3 URL", max_length=1000, blank=True)
    presentation_url = models.URLField(max_length=1000, blank=True)
    status = models.IntegerField(choices=Status.choices, default=Status.NEW)
    authors_text = models.TextField(
        blank=True, editable=False,
        help_text="All author names, kept up to date automatically, used by search.",
    )

    class Meta:
        ordering = ["conference", models.F("first_page").asc(nulls_last=True), "title"]
        indexes = [models.Index(fields=["doi"])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("archive:paper", args=[self.pk])

    @property
    def year(self):
        return self.conference.year

    @property
    def pages(self):
        if self.first_page and self.last_page:
            return f"{self.first_page}-{self.last_page}"
        return ""

    @property
    def doi_url(self):
        return f"https://doi.org/{self.doi}" if self.doi else ""

    def short_author_string(self):
        """'Smith', 'Smith and Jones' or 'Smith et al.', as on the old site."""
        names = [author.last_name for author in self.authors.all()]
        if not names:
            return "Unknown"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return f"{names[0]} et al."

    def full_author_string(self):
        """'Ann Smith, Bo Jones and Cy Lee'."""
        names = [f"{a.first_name} {a.last_name}".strip() for a in self.authors.all()]
        if not names:
            return "Unknown"
        if len(names) == 1:
            return names[0]
        return f"{', '.join(names[:-1])} and {names[-1]}"

    def refresh_authors_text(self, save=True):
        self.authors_text = " ".join(f"{a.first_name} {a.last_name}" for a in self.authors.all())
        if save:
            Paper.objects.filter(pk=self.pk).update(authors_text=self.authors_text)

    def file_name(self):
        """Friendly PDF file name, for example 'Smith et al. 2024 - Title'."""
        if not self.authors.exists():
            return self.title
        year = f" {self.year}" if self.year else ""
        return f"{self.short_author_string()}{year} - {self.title}"


class Author(PersonName):
    """An author as printed on one paper."""

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="authors")
    person = models.ForeignKey(
        AuthorPerson, null=True, blank=True, on_delete=models.SET_NULL, related_name="authorships"
    )
    title_and_contact = models.TextField("affiliation and contact", blank=True)
    order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class LinkCategory(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "link categories"

    def __str__(self):
        return self.name


class Link(models.Model):
    category = models.ForeignKey(LinkCategory, on_delete=models.CASCADE, related_name="links")
    name = models.CharField(max_length=300)
    url = models.URLField(max_length=1000)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
