import uuid

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
