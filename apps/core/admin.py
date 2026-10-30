from django.contrib import admin

from .models import AuditLog, NavItem, SiteSettings, SliderImage, SocialLink


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization_name", "motto", "whatsapp_number", "contact_email", "updated_at")
    fieldsets = (
        ("Branding", {"fields": ("organization_name", "motto", "logo", "footer_note")}),
        ("Home page text", {"fields": ("home_heading", "home_subheading", "home_body", "home_call_to_action", "home_statistics_note")}),
        ("About page", {"fields": ("about_mission", "about_vision", "about_history", "about_leadership", "about_photo")}),
        ("Contact & location", {"fields": ("whatsapp_number", "contact_email", "postal_address", "location_label", "map_embed_url")}),
        ("Bank & M-Pesa", {"fields": ("bank_name", "bank_account_name", "bank_account_number", "bank_branch", "bank_notes", "mpesa_paybill", "mpesa_account_number")}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user if request.user.is_authenticated else None
        super().save_model(request, obj, form, change)


@admin.register(SliderImage)
class SliderImageAdmin(admin.ModelAdmin):
    list_display = ("thumbnail", "caption", "order", "active")
    list_editable = ("order", "active")

    @admin.display(description="Photo")
    def thumbnail(self, obj):
        return obj.image and f"slide #{obj.pk}" or "no image"


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("platform", "url", "order", "active")
    list_editable = ("url", "order", "active")


@admin.register(NavItem)
class NavItemAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "order", "visible")
    list_editable = ("url", "order", "visible")
    ordering = ("order", "id")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target")
    list_filter = ("action",)
    search_fields = ("actor__email", "action", "target", "details")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
