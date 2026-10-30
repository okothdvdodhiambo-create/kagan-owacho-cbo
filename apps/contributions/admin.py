from django.contrib import admin

from .models import Contribution, MpesaCallback


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "member", "amount", "method", "status", "reference", "verified_by")
    list_filter = ("status", "method")
    search_fields = ("member__full_name", "member__membership_no", "reference", "transaction_id")
    readonly_fields = ("created_at", "updated_at", "checkout_request_id", "transaction_id", "result_code", "result_message")


@admin.register(MpesaCallback)
class MpesaCallbackAdmin(admin.ModelAdmin):
    list_display = ("created_at", "checkout_request_id", "result_code", "mpesa_receipt_number", "amount", "contribution")
    search_fields = ("checkout_request_id", "mpesa_receipt_number")
    readonly_fields = [field.name for field in MpesaCallback._meta.fields]

    def has_add_permission(self, request):
        return False
