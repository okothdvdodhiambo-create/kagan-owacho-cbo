"""Money coming in: M-Pesa (Daraja STK or manual code) and bank deposits."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.utils import kenyan_phone_to_254, validate_image_file


class Contribution(models.Model):
    class Method(models.TextChoices):
        MPESA_STK = "mpesa_stk", "M-Pesa online (STK Push)"
        MPESA_MANUAL = "mpesa_manual", "M-Pesa code (verified by treasurer)"
        BANK = "bank", "Bank deposit / slip"

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for M-Pesa prompt"
        PENDING = "pending", "Awaiting verification"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    # Statuses that count as money actually received (used by totals & the home page).
    APPROVED_STATUSES = [Status.CONFIRMED]

    member = models.ForeignKey("membership.Member", on_delete=models.CASCADE, related_name="contributions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    reference = models.CharField(max_length=60, blank=True, help_text="M-Pesa code, slip or transfer reference")
    phone = models.CharField(max_length=20, blank=True)
    checkout_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    transaction_id = models.CharField(max_length=64, blank=True)
    result_code = models.CharField(max_length=20, blank=True)
    result_message = models.CharField(max_length=200, blank=True)

    payment_date = models.DateField(null=True, blank=True)
    receipt = models.ImageField(upload_to="receipts/", blank=True, null=True, validators=[validate_image_file])
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="contributions_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.member} - {self.amount} ({self.get_method_display()})"

    def save(self, *args, **kwargs):
        if self.phone:
            normalised = kenyan_phone_to_254(self.phone)
            if normalised:
                self.phone = normalised
        if self.receipt and getattr(self.receipt, "_committed", True) is False:
            from apps.core.utils import new_image_file, optimise_image

            processed = optimise_image(self.receipt, max_side=1400, quality=80)
            if processed:
                self.receipt = new_image_file(self.receipt.name, processed)
        if not self.payment_date and self.status == self.Status.CONFIRMED:
            self.payment_date = timezone.localdate()
        super().save(*args, **kwargs)

    @property
    def counts_towards_totals(self):
        return self.status == self.Status.CONFIRMED

    @property
    def status_css(self):
        return {
            self.Status.CONFIRMED: "success",
            self.Status.PENDING: "warning",
            self.Status.WAITING: "info",
            self.Status.REJECTED: "danger",
            self.Status.FAILED: "danger",
            self.Status.CANCELLED: "secondary",
        }.get(self.status, "secondary")

    @property
    def method_short(self):
        return {self.Method.MPESA_STK: "M-Pesa", self.Method.MPESA_MANUAL: "M-Pesa code", self.Method.BANK: "Bank"}[
            self.method
        ]

    @classmethod
    def totals(cls, member):
        rows = cls.objects.filter(member=member)
        confirmed = rows.filter(status=cls.Status.CONFIRMED)
        return {
            "confirmed_total": confirmed.aggregate(s=models.Sum("amount"))["s"] or Decimal("0.00"),
            "confirmed_count": confirmed.count(),
            "pending_count": rows.filter(status=cls.Status.PENDING).count(),
            "pending_total": rows.filter(status=cls.Status.PENDING).aggregate(s=models.Sum("amount"))["s"]
            or Decimal("0.00"),
            "all_count": rows.count(),
        }


class MpesaCallback(models.Model):
    """Raw Safaricom callback bodies, kept for troubleshooting."""

    contribution = models.ForeignKey(
        Contribution, null=True, blank=True, on_delete=models.SET_NULL, related_name="callbacks"
    )
    checkout_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    merchant_request_id = models.CharField(max_length=64, blank=True)
    result_code = models.CharField(max_length=20, blank=True)
    result_desc = models.CharField(max_length=200, blank=True)
    mpesa_receipt_number = models.CharField(max_length=30, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"callback {self.checkout_request_id or 'unknown'} ({self.result_code})"
