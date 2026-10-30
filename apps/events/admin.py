from django.contrib import admin

from .models import Event, EventReport, EventReportPhoto


class EventReportPhotoInline(admin.TabularInline):
    model = EventReportPhoto
    extra = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "venue", "category", "published")
    list_filter = ("published", "category")
    search_fields = ("title", "venue", "description")
    date_hierarchy = "starts_at"


@admin.register(EventReport)
class EventReportAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "published", "created_at")
    list_filter = ("published",)
    search_fields = ("title", "body")
    inlines = [EventReportPhotoInline]


admin.site.register(EventReportPhoto)
