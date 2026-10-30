"""Membership registration, verification codes and membership numbers."""

import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.core.utils import kenyan_phone_to_254


class DropdownOption(models.Model):
    """Admin-editable choices for the registration form's dropdowns."""

    class Field(models.TextChoices):
        GENDER = "gender", "Gender"
        ROLE = "role", "Role"
        OCCUPATION = "occupation", "Occupation"

    field = models.CharField(max_length=20, choices=Field.choices)
    label = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["field", "order", "label"]
        constraints = [models.UniqueConstraint(fields=["field", "label"], name="unique_option_per_field")]

    def __str__(self):
        return f"{self.get_field_display()}: {self.label}"


class MemberQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Member.Status.ACTIVE, verified=True)


class Member(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending_verification", "Waiting for verification"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="profile"
    )
    full_name = models.CharField("Full name (as on the national ID)", max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(unique=True)
    gender = models.CharField(max_length=40, blank=True)
    role = models.CharField(max_length=60, blank=True)
    location = models.CharField(max_length=120)
    sub_location = models.CharField(max_length=120, blank=True)
    occupation = models.CharField(max_length=80, blank=True)

    # NULL until verification, so many pending members can coexist under the unique index.
    membership_no = models.CharField(max_length=20, unique=True, blank=True, null=True, editable=False)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    verified = models.BooleanField(default=False)
    verification_channel = models.CharField(max_length=10, default="both")
    last_code_sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MemberQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.membership_no or 'not yet numbered'})"

    def clean(self):
        super().clean()
        self.email = (self.email or "").strip().lower()
        normalised = kenyan_phone_to_254(self.phone)
        if not normalised:
            raise ValidationError({"phone": "Enter a valid Kenyan phone number (07XX... or +2547XX...)."})
        self.phone = normalised

    # ------------------------------------------------------------------ numbers
    @classmethod
    def next_membership_no(cls):
        prefix = settings.MEMBERSHIP_PREFIX.upper()
        last = (
            cls.objects.filter(membership_no__startswith=f"{prefix}-")
            .order_by("-membership_no")
            .values_list("membership_no", flat=True)
            .first()
        )
        sequence = int(last.split("-")[-1]) + 1 if last else 1
        return f"{prefix}-{sequence:04d}"

    @transaction.atomic
    def confirm_membership(self):
        """Called once the SMS/email code has been verified."""
        if not self.membership_no:
            for _attempt in range(5):
                try:
                    # Nested atomic = savepoint, so a clash on the unique number
                    # only rolls back this insert and the retry can allocate again.
                    with transaction.atomic():
                        self.membership_no = Member.next_membership_no()
                        self.save(update_fields=["membership_no"])
                    break
                except IntegrityError:
                    continue
        self.verified = True
        self.status = Member.Status.ACTIVE
        self.verified_at = timezone.now()
        self.save(update_fields=["verified", "status", "verified_at", "membership_no"])
        return self

    # ------------------------------------------------------------------- helpers
    @property
    def can_resend_code(self):
        cooldown = settings.VERIFICATION_RESEND_COOLDOWN_SECONDS
        if not self.last_code_sent_at:
            return True, 0
        elapsed = (timezone.now() - self.last_code_sent_at).total_seconds()
        return elapsed >= cooldown, max(0, int(cooldown - elapsed))

    @property
    def total_given(self):
        from apps.contributions.models import Contribution

        total = self.contributions.filter(status=Contribution.Status.CONFIRMED).aggregate(
            s=models.Sum("amount")
        )["s"]
        return float(total or 0)


class VerificationCode(models.Model):
    """A 6-digit code that expires after 10 minutes with at most 5 guesses."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="codes")
    code_hash = models.CharField(max_length=64)
    channel = models.CharField(max_length=10, default="both")
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"code for {self.member.email}"

    @staticmethod
    def _hash(raw):
        secret = f"{settings.SECRET_KEY}:{raw}".encode("utf-8")
        return hashlib.sha256(secret).hexdigest()

    @classmethod
    def issue(cls, member, channel="both"):
        """Expire outstanding codes and return (code_obj, plaintext_6_digits)."""
        cls.objects.filter(member=member, confirmed_at__isnull=True).update(expires_at=timezone.now())
        plaintext = f"{secrets.randbelow(900000) + 100000}"
        code = cls.objects.create(
            member=member,
            code_hash=cls._hash(plaintext),
            channel=channel,
            expires_at=timezone.now() + timezone.timedelta(minutes=settings.VERIFICATION_TTL_MINUTES),
        )
        member.last_code_sent_at = timezone.now()
        member.save(update_fields=["last_code_sent_at", "updated_at"])
        return code, plaintext

    @property
    def expired(self):
        return timezone.now() > self.expires_at

    @property
    def out_of_attempts(self):
        return self.attempts >= settings.VERIFICATION_MAX_ATTEMPTS

    def is_valid_for(self, raw):
        return self.code_hash == self._hash(str(raw).strip())

    def register_attempt(self):
        self.attempts += 1
        self.save(update_fields=["attempts"])

    def mark_confirmed(self):
        self.confirmed_at = timezone.now()
        self.save(update_fields=["confirmed_at"])
