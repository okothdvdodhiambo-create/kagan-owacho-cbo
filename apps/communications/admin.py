from django.contrib import admin

from .models import ContactMessage, EmailCampaign


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "created_at", "handled")
    list_filter = ("handled",)
    search_fields = ("subject", "name", "email", "message")
    readonly_fields = ("created_at",)


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "audience", "status", "email_count", "sms_count", "created_at")
    list_filter = ("status", "audience")
    readonly_fields = ("email_count", "sms_count", "sent_at", "created_at")
