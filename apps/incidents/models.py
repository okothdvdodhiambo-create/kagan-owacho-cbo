"""Incident reports raised by members and answered by the admin team."""

from django.conf import settings
from django.db import models

from apps.core.utils import validate_document_file


class Incident(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        UNDER_REVIEW = "under_review", "Under review"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    member = models.ForeignKey("membership.Member", on_delete=models.CASCADE, related_name="incidents")
    title = models.CharField(max_length=160)
    description = models.TextField()
    occurred_on = models.DateField()
    attachment = models.FileField(
        upload_to="incidents/", blank=True, null=True, validators=[validate_document_file]
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    handling_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="incidents_handled"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def status_css(self):
        return {
            "new": "danger",
            "under_review": "warning",
            "resolved": "success",
            "closed": "secondary",
        }.get(self.status, "secondary")

    @property
    def latest_reply(self):
        return self.responses.order_by("-created_at").first()


class IncidentResponse(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="responses")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    notify_member = models.BooleanField(default=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"reply on {self.incident.title}"
