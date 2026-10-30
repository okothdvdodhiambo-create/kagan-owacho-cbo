from django.contrib import admin

from .models import DropdownOption, Member, VerificationCode


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("membership_no", "full_name", "phone", "email", "role", "status", "created_at")
    list_filter = ("status", "verified", "gender", "role")
    search_fields = ("full_name", "email", "phone", "membership_no", "location")
    readonly_fields = ("membership_no", "verified_at", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(DropdownOption)
class DropdownOptionAdmin(admin.ModelAdmin):
    list_display = ("field", "label", "order", "active")
    list_filter = ("field", "active")
    list_editable = ("order", "active")
    search_fields = ("label",)


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("member", "channel", "attempts", "expires_at", "confirmed_at", "created_at")
    readonly_fields = [field.name for field in VerificationCode._meta.fields]

    def has_add_permission(self, request):
        return False
