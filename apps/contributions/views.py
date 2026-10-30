"""Member-facing money pages: pay by M-Pesa or bank, see the transcript, download a PDF."""

import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.decorators import member_required
from apps.communications.services import notify_member_of_contribution_status
from apps.core.models import AuditLog, SiteSettings
from apps.core.utils import client_ip

from . import services
from .daraja import get_client
from .forms import BankContributionForm, MpesaManualForm, MpesaStkForm
from .models import Contribution
from .pdf import statement_pdf


@member_required
def choose_method(request):
    member = request.user.membership
    site = SiteSettings.load()
    return render(
        request,
        "contributions/choose.html",
        {
            "member": member,
            "site": site,
            "mpesa_ready": get_client().configured,
            "totals": Contribution.totals(member),
            "page_title": "Send a contribution",
            "active_section": "contribute",
        },
    )


@member_required
def mpesa_stk(request):
    """Start a Daraja STK Push, then show a waiting page that polls for the result."""
    member = request.user.membership
    form = MpesaStkForm(request.POST or None, initial={"phone": member.phone})
    if request.method == "POST" and form.is_valid():
        contribution = Contribution.objects.create(
            member=member,
            amount=form.cleaned_data["amount"],
            phone=form.cleaned_data["phone"],
            method=Contribution.Method.MPESA_STK,
            status=Contribution.Status.PENDING,
        )
        ok, note = services.initiate_stk(contribution)
        AuditLog.record(request.user, "contribution.stk", target=f"{contribution.pk} ({contribution.amount})", request=request)
        if ok:
            messages.info(request, note)
            return redirect("contributions:waiting", pk=contribution.pk)
        messages.warning(request, note + " You can still send by M-Pesa and record the code below.")
        return redirect("contributions:manual")
    return render(
        request,
        "contributions/mpesa_stk.html",
        {"form": form, "page_title": "Pay by M-Pesa", "active_section": "contribute"},
    )


@member_required
def waiting(request, pk):
    contribution = get_object_or_404(Contribution, pk=pk, member=request.user.membership)
    return render(
        request,
        "contributions/waiting.html",
        {"contribution": contribution, "page_title": "Confirm on your phone", "active_section": "contribute"},
    )


@member_required
def waiting_status(request, pk):
    """Polled by the waiting page's JavaScript."""
    contribution = get_object_or_404(Contribution, pk=pk, member=request.user.membership)
    status = services.refresh_status(contribution)
    return JsonResponse(
        {
            "status": status,
            "reference": contribution.reference,
            "message": contribution.result_message,
            "amount": str(contribution.amount),
        }
    )


@member_required
def mpesa_manual(request):
    """Fallback: the member pays from the phone and types the M-Pesa code."""
    member = request.user.membership
    site = SiteSettings.load()
    form = MpesaManualForm(request.POST or None, initial={"phone": member.phone})
    if request.method == "POST" and form.is_valid():
        contribution = Contribution.objects.create(
            member=member,
            amount=form.cleaned_data["amount"],
            phone=form.cleaned_data["phone"],
            reference=form.cleaned_data["reference"],
            payment_date=form.cleaned_data.get("payment_date"),
            note=form.cleaned_data.get("note", ""),
            method=Contribution.Method.MPESA_MANUAL,
            status=Contribution.Status.PENDING,
        )
        AuditLog.record(request.user, "contribution.manual", target=contribution.reference, request=request)
        messages.success(request, "Recorded. The treasurer will confirm it shortly; you will get an email.")
        return redirect("contributions:transcript")
    return render(
        request,
        "contributions/mpesa_manual.html",
        {"form": form, "site": site, "page_title": "Record an M-Pesa code", "active_section": "contribute"},
    )


@member_required
def bank(request):
    member = request.user.membership
    site = SiteSettings.load()
    form = BankContributionForm(request.POST or None, request.FILES or None, initial={"payment_date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        contribution = Contribution.objects.create(
            member=member,
            amount=form.cleaned_data["amount"],
            reference=form.cleaned_data["reference"],
            payment_date=form.cleaned_data["payment_date"],
            receipt=form.cleaned_data.get("receipt"),
            note=form.cleaned_data.get("note", ""),
            method=Contribution.Method.BANK,
            status=Contribution.Status.PENDING,
        )
        AuditLog.record(request.user, "contribution.bank", target=contribution.reference, request=request)
        messages.success(request, "Bank contribution submitted for verification.")
        return redirect("contributions:transcript")
    return render(
        request,
        "contributions/bank.html",
        {"form": form, "site": site, "page_title": "Pay by bank", "active_section": "contribute"},
    )


@member_required
def transcript(request):
    member = request.user.membership
    rows = Contribution.objects.filter(member=member)
    method = request.GET.get("method", "")
    status = request.GET.get("status", "")
    if method:
        rows = rows.filter(method=method)
    if status:
        rows = rows.filter(status=status)
    return render(
        request,
        "contributions/transcript.html",
        {
            "member": member,
            "contributions": rows.order_by("-created_at"),
            "totals": Contribution.totals(member),
            "methods": Contribution.Method.choices,
            "statuses": Contribution.Status.choices,
            "selected_method": method,
            "selected_status": status,
            "page_title": "My contribution history",
            "active_section": "transcript",
        },
    )


@member_required
def statement(request):
    """The signed, logo-stamped PDF the member can print or download."""
    member = request.user.membership
    rows = Contribution.objects.filter(member=member).order_by("created_at")
    return statement_pdf(member, rows, as_attachment=request.GET.get("download") == "1")


@csrf_exempt
def mpesa_callback(request):
    """Safaricom posts here after the member approves the prompt."""
    if request.method != "POST":
        return JsonResponse({"ResultCode": 1, "ResultDesc": "POST only"}, status=405)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Bad JSON"}, status=400)

    contribution = services.apply_callback_payload(payload, source_ip=client_ip(request))
    if contribution is not None and contribution.status == Contribution.Status.CONFIRMED:
        notify_member_of_contribution_status(contribution)
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})
