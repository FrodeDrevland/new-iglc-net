from django.conf import settings
from django.db import models


class Deposit(models.Model):
    """One deposit of a conference's metadata to Crossref: the XML sent and what came back."""

    class Status(models.TextChoices):
        MADE = "made", "Made, not sent"
        SENT = "sent", "Sent, waiting for Crossref"
        SUCCESS = "success", "Registered"
        WARNING = "warning", "Registered with warnings"
        FAILED = "failed", "Failed"

    conference = models.ForeignKey("archive.Conference", on_delete=models.CASCADE, related_name="crossref_deposits")
    batch_id = models.CharField(max_length=100, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    test = models.BooleanField(help_text="Sent to Crossref's test system (nothing is registered).")
    xml = models.TextField()
    papers = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.MADE)
    sent = models.DateTimeField(null=True, blank=True)
    checked = models.DateTimeField(null=True, blank=True)
    response = models.TextField(blank=True, help_text="Crossref's answer to the upload.")
    result = models.TextField(blank=True, help_text="Crossref's result (the submission log).")
    successes = models.PositiveIntegerField(default=0)
    warnings = models.PositiveIntegerField(default=0)
    failures = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.conference}: {self.batch_id}"

    @property
    def file_name(self):
        return f"{self.batch_id}.xml"
