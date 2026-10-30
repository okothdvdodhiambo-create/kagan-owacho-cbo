"""Public event pages: sponsored list, monthly calendar, detail, reports."""

from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Event, EventReport


def event_list(request):
    """'Events Sponsored' - what we paid for, with photos and the admin's reports."""
    category = request.GET.get("category", "")
    events = Event.objects.filter(published=True).prefetch_related("reports__photos")
    if category:
        events = events.filter(category=category)
    context = {
        "events": list(events.order_by("-starts_at")),
        "reports": EventReport.objects.filter(published=True).select_related("event", "created_by")[:12],
        "categories": Event.Category.choices,
        "selected_category": category,
        "page_title": "Events Sponsored",
    }
    return render(request, "events/list.html", context)


def calendar(request):
    context = {
        "page_title": "Event Calendar",
        "today": timezone.localdate(),
        "feed_url": "/events/feed/",
        "calendar_timezone": settings.TIME_ZONE,
    }
    return render(request, "events/calendar.html", context)


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk, published=True)
    reports = event.reports.filter(published=True).prefetch_related("photos")
    return render(
        request,
        "events/detail.html",
        {"event": event, "reports": reports, "page_title": event.title},
    )


def report_detail(request, pk):
    report = get_object_or_404(EventReport.objects.select_related("event"), pk=pk, published=True)
    return render(request, "events/report.html", {"report": report, "page_title": report.title})


def event_feed(request):
    """JSON feed the FullCalendar month view reads (optional ?start=&end=)."""
    events = Event.objects.filter(published=True)
    for key, compare in (("start", "starts_at__gte"), ("end", "starts_at__lt")):
        raw = (request.GET.get(key) or "").replace("Z", "+00:00")
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment)
        events = events.filter(**{compare: moment})
    # FullCalendar's JSON feed must be a bare array, not an object wrapper.
    return JsonResponse(
        [event.for_calendar() for event in events.order_by("starts_at")[:500]],
        safe=False,
    )
