"""Events sponsored by the CBO and the written reports the admin publishes."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.utils import validate_image_file


class Event(models.Model):
    class Category(models.TextChoices):
        EVENT = "event", "Community event"
        SCHOOL_FEES = "school_fees", "School fees support"
        SUPPORT = "support", "Other support"

    title = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.EVENT)
    starts_at = models.DateTimeField("Date & time")
    ends_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="events/", blank=True, null=True, validators=[validate_image_file])
    published = models.BooleanField(default=True, help_text="Show on the public pages and calendar.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.title} ({self.starts_at:%d/%m/%Y})"

    def save(self, *args, **kwargs):
        if self.photo and getattr(self.photo, "_committed", True) is False:
            from apps.core.utils import new_image_file, optimise_image

            processed = optimise_image(self.photo, max_side=1400)
            if processed:
                self.photo = new_image_file(self.photo.name, processed)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("events:detail", kwargs={"pk": self.pk})

    @property
    def is_past(self):
        reference = self.ends_at or self.starts_at
        return reference and reference < timezone.now()

    @property
    def date_line(self):
        local = timezone.localtime(self.starts_at)
        return f"{local:%a %d %b %Y, %I:%M %p}"

    def for_calendar(self):
        return {
            "id": str(self.pk),
            "title": self.title,
            "start": timezone.localtime(self.starts_at).isoformat(),
            "end": timezone.localtime(self.ends_at).isoformat() if self.ends_at else None,
            "url": self.get_absolute_url(),
            "venue": self.venue,
            "description": self.description[:200],
            "backgroundColor": "#0f6b4f",
            "borderColor": "#0b4d39",
        }


class EventReport(models.Model):
    """A write-up posted by an admin; visible on the public Events Sponsored page."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reports")
    title = models.CharField(max_length=160)
    body = models.TextField()
    published = models.BooleanField(default=True)
    emailed_at = models.DateTimeField(null=True, blank=True, help_text="Set when the report was mailed to all members.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_written"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:report_detail", kwargs={"pk": self.pk})

    @property
    def body_paragraphs(self):
        return [p.strip() for p in (self.body or "").split("\n\n") if p.strip()]


class EventReportPhoto(models.Model):
    report = models.ForeignKey(EventReport, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="reports/", validators=[validate_image_file])
    caption = models.CharField(max_length=140, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.caption or f"photo {self.pk}"
