from django.contrib import admin

from .models import Incident, IncidentResponse


class IncidentResponseInline(admin.TabularInline):
    model = IncidentResponse
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("title", "member", "occurred_on", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "description", "member__full_name")
    inlines = [IncidentResponseInline]


admin.site.register(IncidentResponse)
