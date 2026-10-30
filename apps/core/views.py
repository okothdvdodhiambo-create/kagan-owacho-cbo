"""Public pages: home and about."""

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

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
