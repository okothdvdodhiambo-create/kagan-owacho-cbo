"""Outgoing messages: member blasts (email + optional SMS) and the contact form."""

from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    """'Email us' from the member dashboard / public site -> admin inbox."""

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=160)
    message = models.TextField()
    member = models.ForeignKey(
        "membership.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="contact_messages"
    )
    handled = models.BooleanField(default=False)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.email})"


class EmailCampaign(models.Model):
    class Audience(models.TextChoices):
        ALL = "all", "All verified members"
        ACTIVE = "active", "Active members only"
        SELECTED = "selected", "A group I pick"

    subject = models.CharField(max_length=200)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    members = models.ManyToManyField("membership.Member", blank=True, related_name="campaigns")
    send_sms = models.BooleanField(default=False, help_text="Also send the message by SMS.")
    status = models.CharField(
        max_length=10,
        choices=[("draft", "Draft"), ("sent", "Sent")],
        default="draft",
    )
    email_count = models.PositiveIntegerField(default=0)
    sms_count = models.PositiveIntegerField(default=0)
    error_note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.get_status_display()})"

    def recipients(self):
        from apps.membership.models import Member

        if self.audience == self.Audience.SELECTED:
            return self.members.filter(verified=True)
        if self.audience == self.Audience.ACTIVE:
            return Member.objects.filter(status=Member.Status.ACTIVE, verified=True)
        return Member.objects.filter(verified=True)

    def preview_count(self):
        return self.recipients().count()
