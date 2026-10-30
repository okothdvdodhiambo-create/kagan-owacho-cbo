"""Members raise incident reports; the admin team answers from the dashboard."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import member_required
from apps.communications.services import notify_admins_of_incident
from apps.core.models import AuditLog

from .forms import IncidentForm
from .models import Incident


@member_required
def report_new(request):
    member = request.user.membership
    form = IncidentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        incident = form.save(commit=False)
        incident.member = member
        incident.save()
        notify_admins_of_incident(incident)
        AuditLog.record(request.user, "incident.created", target=incident.title, request=request)
        messages.success(request, "Thank you. The committee has received your report and will follow up.")
        return redirect("incidents:detail", pk=incident.pk)
    return render(request, "incidents/form.html", {"form": form, "page_title": "Report an incident", "active_section": "incidents"})


@member_required
def report_list(request):
    member = request.user.membership
    incidents = Incident.objects.filter(member=member)
    return render(
        request,
        "incidents/list.html",
        {"incidents": incidents, "page_title": "My incident reports", "active_section": "incidents"},
    )


@member_required
def report_detail(request, pk):
    incident = get_object_or_404(Incident.objects.prefetch_related("responses"), pk=pk, member=request.user.membership)
    return render(
        request,
        "incidents/detail.html",
        {"incident": incident, "page_title": incident.title, "active_section": "incidents"},
    )
