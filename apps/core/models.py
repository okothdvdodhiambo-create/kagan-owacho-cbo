"""Site-wide, admin-editable content: branding, page text, slider, nav, footer links."""

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.db import models

from .utils import validate_image_file


class SingletonModel(models.Model):
    """A model that always has exactly one row (pk = 1).

    Reads are not cached: an edited setting must show on the site the second the
    admin presses Save, and one primary-key lookup per request is cheaper than
    explaining a stale cache to a volunteer treasurer.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class SiteSettings(SingletonModel):
    # Branding
    organization_name = models.CharField(max_length=120, default=settings.ORGANIZATION_NAME)
    motto = models.CharField(
        max_length=220,
        blank=True,
        default="Tunawesa wanafunzi, tunaunga mkono jamii ya Kagan.",
    )
    logo = models.ImageField(upload_to="branding/", blank=True, null=True, validators=[validate_image_file])
    footer_note = models.TextField(
        blank=True,
        default="A community-based organisation registered to serve Kagan Ward, Rangwe.",
    )

    # Home page (left column)
    home_heading = models.CharField(max_length=160, default="Karibu Kagan Owacho CBO")
    home_subheading = models.CharField(max_length=220, default="Paying school fees. Supporting families. Building Kagan.")
    home_body = models.TextField(
        blank=True,
        default=(
            "Kagan Owacho CBO was formed by residents of Kagan Ward to pool resources for our "
            "children's education and other community needs. We pay school fees for needy "
            "students, sponsor events, and keep every shilling accountable to our members."
        ),
    )
    home_call_to_action = models.CharField(max_length=60, default="Become a member")
    home_statistics_note = models.CharField(max_length=160, blank=True, default="Students supported, events sponsored, members served.")

    # About page
    about_mission = models.TextField(blank=True, default="To mobilise community resources for education and welfare in Kagan Ward.")
    about_vision = models.TextField(blank=True, default="A Kagan where no bright child drops out because of school fees.")
    about_history = models.TextField(blank=True, default="Founded by volunteers in Kagan Ward, Rangwe Constituency, Homa Bay County.")
    about_leadership = models.TextField(blank=True, default="Chairperson, Secretary, Treasurer and elected committee members.")
    about_photo = models.ImageField(upload_to="about/", blank=True, null=True, validators=[validate_image_file])

    # Contact & location
    whatsapp_number = models.CharField(max_length=20, default="+254700000000", help_text="Format +2547XXXXXXXX")
    contact_email = models.EmailField(default=settings.ADMIN_INBOX_EMAIL)
    postal_address = models.CharField(max_length=160, blank=True, default="Kagan Ward, Rangwe Constituency")
    location_label = models.CharField(max_length=200, default="Kagan Ward, Rangwe Constituency, Homa Bay County, Kenya")
    map_embed_url = models.URLField(
        blank=True,
        help_text="Paste the 'src' of a Google Maps embed link (https://www.google.com/maps/embed?pb=...).",
    )

    # Bank details shown to members when contributing
    bank_name = models.CharField(max_length=120, blank=True, default="NCBA Bank - Homa Bay Branch")
    bank_account_name = models.CharField(max_length=120, blank=True, default="Kagan Owacho CBO")
    bank_account_number = models.CharField(max_length=40, blank=True, default="0000000000")
    bank_branch = models.CharField(max_length=120, blank=True, default="Homa Bay")
    bank_notes = models.TextField(blank=True, default="After depositing, submit the slip number below so the treasurer can confirm it.")

    # M-Pesa till / paybill shown on the manual-entry form
    mpesa_paybill = models.CharField(max_length=40, blank=True, default="")
    mpesa_account_number = models.CharField(max_length=40, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Site setting"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return self.organization_name

    @property
    def whatsapp_digits(self):
        return "".join(ch for ch in (self.whatsapp_number or "") if ch.isdigit()).lstrip("0")

    @property
    def whatsapp_url(self):
        digits = self.whatsapp_digits
        if not digits:
            return "#"
        if digits.startswith("254"):
            return f"https://wa.me/{digits}"
        return f"https://wa.me/254{digits.lstrip('0')}"

    @property
    def current_year(self):
        from django.utils import timezone

        return timezone.localtime().year

    @property
    def location_urlencode(self):
        from urllib.parse import quote

        return quote(self.location_label or "Kagan Ward, Rangwe, Homa Bay, Kenya")


class SliderImage(models.Model):
    image = models.ImageField(upload_to="slider/", validators=[validate_image_file])
    caption = models.CharField(max_length=140, blank=True)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Slider photo"
        verbose_name_plural = "Slider photos"

    def __str__(self):
        return self.caption or f"Slide {self.pk}"


class SocialLink(models.Model):
    PLATFORMS = [
        ("facebook", "Facebook"),
        ("x", "X (Twitter)"),
        ("instagram", "Instagram"),
        ("youtube", "YouTube"),
        ("whatsapp", "WhatsApp"),
        ("tiktok", "TikTok"),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORMS)
    url = models.URLField(max_length=300)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_platform_display()} - {self.url}"

    @property
    def icon(self):
        return {"x": "x-twitter", "whatsapp": "whatsapp", "youtube": "youtube", "tiktok": "tiktok", "facebook": "facebook-f", "instagram": "instagram"}[self.platform]


class NavItem(models.Model):
    title = models.CharField(max_length=60)
    url = models.CharField(max_length=200, help_text="Relative path such as /about/ or a full https:// link")
    order = models.PositiveIntegerField(default=0)
    visible = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=200, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Audit log"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"

    @classmethod
    def record(cls, actor, action, target="", details="", request=None):
        from .utils import client_ip

        return cls.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            action=action,
            target=str(target)[:200],
            details=details,
            ip_address=client_ip(request),
        )


class StoredFile(models.Model):
    """An uploaded file kept in the database instead of on the local disk.

    Used by apps.core.storage.DatabaseStorage when MEDIA_STORAGE=database, which is
    how Render keeps profile photos, slider photos, logos and receipt images between
    restarts and deploys when the instance has no persistent disk.
    """

    name = models.CharField(max_length=255, unique=True)
    data = models.BinaryField()
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Stored upload"
        verbose_name_plural = "Stored uploads"

    def __str__(self):
        return self.name

    def as_file(self):
        return File(ContentFile(bytes(self.data), name=self.name), name=self.name)
