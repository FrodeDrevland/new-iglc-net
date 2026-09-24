import uuid

from django.conf import settings
from django.db import models
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel


class PaperCheck(models.Model):
    """The result of an author's template check. The file itself is not kept: only its name,
    fingerprint (SHA-256) and the findings, so the report can be verified later."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    stage = models.CharField(max_length=20)
    file_name = models.CharField(max_length=255)
    sha256 = models.CharField("SHA-256 of the Word file", max_length=64)
    pdf_sha256 = models.CharField("SHA-256 of the PDF", max_length=64, blank=True)
    title = models.CharField(max_length=500, blank=True)
    passed = models.BooleanField()
    findings = models.JSONField(default=list)

    class Meta:
        ordering = ["-created"]
        verbose_name = "paper check"

    def __str__(self):
        return f"{self.file_name} ({self.created:%Y-%m-%d %H:%M})"

    @property
    def short_id(self):
        return str(self.id).split("-")[0].upper()



# ---------------------------------------------------------------- proceedings production

class Production(ClusterableModel):
    """The making of one conference's proceedings: collecting, editing and arranging the papers.

    Not to be confused with archive.Volume, a published book (older proceedings were printed
    in several). When published, the papers go into the conference's volume(s) by page."""

    class Status(models.TextChoices):
        COLLECTING = "collecting", "Collecting and editing papers"
        ARRANGING = "arranging", "Arranging (order and page numbers)"
        PAPERS_PUBLISHED = "papers_published", "Papers published"
        COMPLETE = "complete", "Full proceedings published"

    conference = models.OneToOneField("archive.Conference", on_delete=models.CASCADE, related_name="production")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COLLECTING)
    first_page = models.PositiveIntegerField(default=1, help_text="Page number of the first paper.")
    created = models.DateTimeField(auto_now_add=True)
    # The full proceedings (the book)
    conference_chair = models.CharField(max_length=300, blank=True, help_text="Printed on the title page.")
    copyright_holders = models.CharField(
        max_length=500, blank=True, help_text="For the colophon; the editors if empty.")
    issn_print = models.CharField("ISSN (printed)", max_length=20, blank=True, default="2309-0979")
    issn_electronic = models.CharField("ISSN (electronic)", max_length=20, blank=True, default="2789-0015")
    isbn_print = models.CharField("ISBN (printed)", max_length=30, blank=True)
    isbn_pdf = models.CharField("ISBN (PDF)", max_length=30, blank=True)
    book = models.FileField(upload_to="proceedings/", blank=True, max_length=300,
                            help_text="The published full proceedings PDF.")
    # Chief editors stage publication; a publisher approves it.
    papers_requested_at = models.DateTimeField(null=True, blank=True)
    papers_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                            on_delete=models.SET_NULL, related_name="+")
    book_requested_at = models.DateTimeField(null=True, blank=True)
    book_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name="+")
    draft_built = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-conference__number"]
        verbose_name = "proceedings production"
        permissions = [("publish_production",
                        "Can approve publication and set ISBNs (publisher)")]

    def __str__(self):
        return f"Proceedings IGLC {self.conference.number}"

    @property
    def pages_frozen(self):
        """Once papers are published (even some of them), their page numbers are cited and never change."""
        return self.papers_published or self.submissions.filter(published_version__isnull=False).exists()

    @property
    def papers_published(self):
        return self.status in (self.Status.PAPERS_PUBLISHED, self.Status.COMPLETE)

    @property
    def doi_year(self):
        return self.conference.year


class ProductionEditor(ClusterableModel):
    """A person working on a production. Chief editors see and arrange everything; editors
    see the papers of their tracks (or all papers when no tracks are given)."""

    class Role(models.TextChoices):
        CHIEF = "chief", "Chief editor"
        EDITOR = "editor", "Editor"

    production = ParentalKey(Production, on_delete=models.CASCADE, related_name="editors")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="production_roles")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EDITOR)
    tracks = ParentalManyToManyField("archive.ConferenceTrack", blank=True)

    class Meta:
        unique_together = [("production", "user")]

    def __str__(self):
        return f"{self.user} ({self.get_role_display()}, {self.production})"


def _correction_path(instance, filename):
    return f"production/iglc{instance.production.conference.number}/{instance.conftool_id}/correction-{filename}"


def private_storage():
    from django.core.files.storage import storages

    return storages["private"]


class Submission(models.Model):
    """An accepted paper on its way into the proceedings."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for the edited paper"
        UPLOADED = "uploaded", "Uploaded, to be checked"
        NEEDS_WORK = "needs_work", "Needs more work"
        APPROVED = "approved", "Approved"
        WITHDRAWN = "withdrawn", "Withdrawn"

    production = models.ForeignKey(Production, on_delete=models.CASCADE, related_name="submissions")
    conftool_id = models.PositiveIntegerField("ConfTool ID")
    title = models.CharField(max_length=500, help_text="As registered (ConfTool); the published title comes from the paper.")
    track = models.ForeignKey("archive.ConferenceTrack", null=True, blank=True, on_delete=models.SET_NULL)
    registered_authors = models.JSONField(
        default=list, blank=True,
        help_text="Authors as registered (ConfTool): name, organisation, email. Used to contact them.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="edited_submissions")
    position = models.PositiveIntegerField(default=0, help_text="Order within the track.")
    first_page = models.PositiveIntegerField(null=True, blank=True)
    paper = models.OneToOneField("archive.Paper", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="submission", help_text="The published paper, once published.")
    note = models.TextField(blank=True)
    metadata_edits = models.JSONField(
        default=dict, blank=True,
        help_text="The editors' corrections to what is read from the Word file: the title in sentence case "
                  "and how names split into first and last name.")
    correction_note = models.TextField(blank=True, help_text="A correction waiting for the publisher.")
    correction_public = models.BooleanField(default=False, help_text="Whether its note is to be shown on the paper's page.")
    correction_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                                on_delete=models.SET_NULL, related_name="+")
    correction_pdf = models.FileField(
        upload_to=_correction_path, storage=private_storage, blank=True, max_length=300,
        help_text="For a paper published before these tools: the replacement PDF, waiting for the publisher.")
    published_version = models.ForeignKey(
        "PaperVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="The version whose PDF is on the site.")
    published_pdf = models.FileField(upload_to="papers/", blank=True, max_length=300,
                                     help_text="The published PDF (public), with running headers and page numbers.")

    class Meta:
        unique_together = [("production", "conftool_id")]
        ordering = ["production", "track__order", "position", "conftool_id"]

    def __str__(self):
        return f"{self.conftool_id}: {self.title}"

    @property
    def doi(self):
        year = self.production.doi_year
        return f"10.24928/{year}/{self.conftool_id:04d}" if year else ""

    @property
    def current(self):
        return self.versions.order_by("-number").first()

    @property
    def published_pages(self):
        if self.paper_id and self.paper.first_page and self.paper.last_page:
            return self.paper.last_page - self.paper.first_page + 1
        return None


def _version_path(instance, filename):
    submission = instance.submission
    return (f"production/iglc{submission.production.conference.number}/{submission.conftool_id}/"
            f"v{instance.number}-{filename}")


class PaperVersion(models.Model):
    """One upload of a paper: the Word file, and the PDF Word made of it."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    uploaded = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    comment = models.TextField(blank=True)
    docx = models.FileField(upload_to=_version_path, storage=private_storage)
    docx_sha256 = models.CharField(max_length=64)
    pdf = models.FileField(upload_to=_version_path, storage=private_storage, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True, help_text="From the PDF.")
    metadata = models.JSONField(default=dict, help_text="What was read from the Word file.")
    findings = models.JSONField(default=list, help_text="The template check.")
    passed = models.BooleanField(default=False)

    class Meta:
        ordering = ["submission", "-number"]
        unique_together = [("submission", "number")]

    def __str__(self):
        return f"{self.submission.conftool_id} v{self.number}"


class Event(models.Model):
    """What happened to a paper, by whom: uploads, approvals, papers sent back."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="events")
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=200)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-time"]

    def __str__(self):
        return f"{self.submission.conftool_id}: {self.action}"


class Correction(models.Model):
    """A correction to a paper after it was published. The DOI and the page numbers stay;
    the PDF (and the metadata) are replaced, and the paper's page says it was corrected."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="corrections")
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    version = models.ForeignKey(PaperVersion, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                help_text="Empty for a paper published before these tools (its PDF was replaced).")
    note = models.TextField(help_text="What was corrected (kept for the record).")
    public = models.BooleanField(
        default=False, help_text="Show the note on the paper's page. Worth it for a substantial change long after "
                                 "publication; noise for a small fix soon after.")
    previous_version = models.ForeignKey(PaperVersion, null=True, on_delete=models.PROTECT, related_name="+")
    previous_pdf = models.CharField(max_length=300, blank=True, help_text="The PDF that was replaced (kept).")

    class Meta:
        ordering = ["time"]

    def __str__(self):
        return f"{self.submission.conftool_id}: corrected {self.time:%Y-%m-%d}"


class TrackChair(models.Model):
    """A track's chair(s), for the table of contents and the foreword."""

    production = models.ForeignKey(Production, on_delete=models.CASCADE, related_name="track_chairs")
    track = models.ForeignKey("archive.ConferenceTrack", on_delete=models.CASCADE, related_name="chairs")
    name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["track__order", "order", "name"]

    def __str__(self):
        return f"{self.name} ({self.track})"


def _part_path(instance, filename):
    return f"production/iglc{instance.production.conference.number}/book/{instance.kind}-{filename}"


class BookPart(models.Model):
    """A part of the full proceedings made outside the system from an IGLC template (a message
    from the conference chair, the foreword, sponsors, ...) or a cover, uploaded as a PDF and
    checked against the template. The system makes the colophon, title page, contents and
    author index. Sections go in the front matter or at the back, in the order given."""

    class Kind(models.TextChoices):
        COVER = "cover", "Front cover"
        ORGANISATION = "organisation", "Conference organisation"
        MESSAGE = "message", "Message (e.g. from the conference chair)"
        FOREWORD = "foreword", "Foreword"
        REVIEWERS = "reviewers", "List of reviewers"
        SPONSORS = "sponsors", "Sponsors"
        OTHER = "other", "Other section"
        BACK_COVER = "back_cover", "Back cover"

    class Placement(models.TextChoices):
        FRONT = "front", "Front matter (before the contents)"
        BACK = "back", "Back matter (after the author index)"

    COVERS = (Kind.COVER, Kind.BACK_COVER)
    DEFAULT_ORDER = {Kind.ORGANISATION: 10, Kind.MESSAGE: 20, Kind.FOREWORD: 30, Kind.REVIEWERS: 40,
                     Kind.SPONSORS: 50, Kind.OTHER: 60}

    production = models.ForeignKey(Production, on_delete=models.CASCADE, related_name="book_parts")
    kind = models.CharField(max_length=20, choices=Kind.choices, help_text="Which template it is made from.")
    title = models.CharField(max_length=200, blank=True, help_text="The heading, for the bookmarks.")
    placement = models.CharField(max_length=10, choices=Placement.choices, default=Placement.FRONT)
    order = models.PositiveIntegerField(default=0)
    pdf = models.FileField(upload_to=_part_path, storage=private_storage)
    pages = models.PositiveIntegerField(default=0)
    uploaded = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["production", "placement", "order", "uploaded"]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return self.title or self.get_kind_display().split(" (")[0]
