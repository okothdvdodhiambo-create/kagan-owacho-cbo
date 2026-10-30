from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.utils import kenyan_phone_to_254, new_image_file, optimise_image, validate_image_file


class UserManager(BaseUserManager):
    """Accounts are identified by email - there is no separate username."""

    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValidationError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_admin", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_admin", True)
        extra.setdefault("is_superuser", True)
        return self._create(email, password, **extra)

    def admins(self):
        return self.filter(is_admin=True)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", unique=True, db_index=True)
    name = models.CharField(max_length=150)
    photo = models.ImageField(
        upload_to="avatars/", blank=True, null=True, validators=[validate_image_file]
    )
    phone = models.CharField(max_length=20, blank=True)
    is_admin = models.BooleanField(default=False, help_text="Can open the admin dashboard.")
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def get_full_name(self):
        return self.name or self.email

    def get_short_name(self):
        return (self.name or self.email).split()[0]

    def get_absolute_url(self):
        return reverse("accounts:profile")

    def clean(self):
        super().clean()
        self.email = (self.email or "").strip().lower()
        if self.phone:
            normalised = kenyan_phone_to_254(self.phone)
            if normalised:
                self.phone = normalised

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.photo and getattr(self.photo, "_committed", True) is False:
            processed = optimise_image(self.photo, max_side=800, quality=85)
            if processed:
                self.photo = new_image_file(self.photo.name, processed)
        super().save(*args, **kwargs)

    @property
    def is_administrator(self):
        return self.is_admin or self.is_superuser

    @property
    def membership(self):
        """The verified (or pending) membership row for this account, if any."""
        from apps.membership.models import Member

        return Member.objects.filter(user=self).first()

    @property
    def avatar_url(self):
        if self.photo:
            return self.photo.url
        return ""


class LoginAttempt(models.Model):
    """Blocks an email address after too many failed passwords."""

    email = models.CharField(max_length=254, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "Login attempts"

    def __str__(self):
        return f"{self.email} ({self.failures} failed)"

    @classmethod
    def lockout_seconds(cls, email):
        record = cls.objects.filter(email=(email or "").strip().lower() or "unknown").order_by("-updated_at").first()
        if record and record.locked_until and record.locked_until > timezone.now():
            return int((record.locked_until - timezone.now()).total_seconds())
        return 0

    @classmethod
    def register_failure(cls, email):
        email = (email or "").strip().lower() or "unknown"
        record, _ = cls.objects.get_or_create(email=email, defaults={"ip_address": None})
        record.failures += 1
        if record.failures >= settings.LOGIN_MAX_ATTEMPTS:
            record.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            record.failures = 0
        record.save()
        return record

    @classmethod
    def clear(cls, email):
        cls.objects.filter(email=(email or "").strip().lower() or "unknown").update(
            failures=0, locked_until=None
        )
