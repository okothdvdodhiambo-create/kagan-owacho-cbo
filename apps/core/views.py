"""Public pages: home, about, and uploads held in the database."""

from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.http import http_date

from .models import SiteSettings, SliderImage


def home(request):
    from apps.contributions.models import Contribution
    from apps.events.models import Event
    from apps.membership.models import Member

    approved = Contribution.objects.filter(status__in=Contribution.APPROVED_STATUSES)
    context = {
        "slider_images": list(SliderImage.objects.filter(active=True)[:6]),
        "stats": {
            "members": Member.objects.filter(status=Member.Status.ACTIVE).count(),
            "contributions_ksh": float(approved.aggregate(total=Sum("amount"))["total"] or 0),
            "events": Event.objects.count(),
        },
        "upcoming_events": list(Event.objects.filter(published=True, starts_at__gte=timezone.now()).order_by("starts_at")[:3]),
        "page_title": "Home",
    }
    return render(request, "core/home.html", context)


def about(request):
    site = SiteSettings.load()
    return render(
        request,
        "core/about.html",
        {"site": site, "page_title": "About us", "page_description": site.about_mission},
    )


def media(request, path):
    """Serve an upload stored in the database (see apps.core.storage.DatabaseStorage)."""

    from .models import StoredFile
    from .storage import INLINE_CONTENT_TYPES

    row = get_object_or_404(StoredFile, name=path)
    safe_name = "".join(c for c in row.name.rsplit("/", 1)[-1] if c.isalnum() or c in "._-") or "upload"
    disposition = "inline" if row.content_type in INLINE_CONTENT_TYPES else "attachment"

    response = FileResponse(
        row.as_file(), content_type=row.content_type, as_attachment=disposition == "attachment", filename=safe_name
    )
    response["Content-Length"] = str(row.size)
    response["X-Content-Type-Options"] = "nosniff"
    response["Last-Modified"] = http_date(row.uploaded_at.timestamp())
    response["Cache-Control"] = "public, max-age=86400"
    return response
