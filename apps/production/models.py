import uuid

from django.conf import settings
from django.db import models


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

class ProceedingsVolume(models.Model):
    """The proceedings of one conference while they are being made."""

    class Status(models.TextChoices):
        COLLECTING = "collecting", "Collecting and editing papers"
        ARRANGING = "arranging", "Arranging (order and page numbers)"
        PUBLISHED = "published", "Published"

    conference = models.OneToOneField("archive.Conference", on_delete=models.CASCADE, related_name="production")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COLLECTING)
    first_page = models.PositiveIntegerField(default=1, help_text="Page number of the first paper.")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-conference__number"]
        verbose_name = "proceedings volume"

    def __str__(self):
        return f"Proceedings IGLC {self.conference.number}"

    @property
    def doi_year(self):
        return self.conference.year


class VolumeEditor(models.Model):
    """A person working on a volume. Chief editors see and arrange everything; editors
    see the papers of their tracks (or all papers when no tracks are given)."""

    class Role(models.TextChoices):
        CHIEF = "chief", "Chief editor"
        EDITOR = "editor", "Editor"

    volume = models.ForeignKey(ProceedingsVolume, on_delete=models.CASCADE, related_name="editors")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volume_roles")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EDITOR)
    tracks = models.ManyToManyField("archive.ConferenceTrack", blank=True)

    class Meta:
        unique_together = [("volume", "user")]

    def __str__(self):
        return f"{self.user} ({self.get_role_display()}, {self.volume})"


class Submission(models.Model):
    """An accepted paper on its way into the proceedings."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for the edited paper"
        UPLOADED = "uploaded", "Uploaded, to be checked"
        NEEDS_WORK = "needs_work", "Needs more work"
        APPROVED = "approved", "Approved"
        WITHDRAWN = "withdrawn", "Withdrawn"

    volume = models.ForeignKey(ProceedingsVolume, on_delete=models.CASCADE, related_name="submissions")
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

    class Meta:
        unique_together = [("volume", "conftool_id")]
        ordering = ["volume", "track__order", "position", "conftool_id"]

    def __str__(self):
        return f"{self.conftool_id}: {self.title}"

    @property
    def doi(self):
        year = self.volume.doi_year
        return f"10.24928/{year}/{self.conftool_id:04d}" if year else ""

    @property
    def current(self):
        return self.versions.order_by("-number").first()


def _version_path(instance, filename):
    submission = instance.submission
    return (f"production/iglc{submission.volume.conference.number}/{submission.conftool_id}/"
            f"v{instance.number}-{filename}")


class PaperVersion(models.Model):
    """One upload of a paper: the Word file, and the PDF Word made of it."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    uploaded = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    comment = models.TextField(blank=True)
    docx = models.FileField(upload_to=_version_path)
    docx_sha256 = models.CharField(max_length=64)
    pdf = models.FileField(upload_to=_version_path, blank=True)
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
