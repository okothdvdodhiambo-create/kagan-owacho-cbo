"""Public registration flow plus the member-facing dashboard pages."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from apps.accounts.decorators import member_required
from apps.communications.forms import ContactMessageForm
from apps.communications.services import send_contact_message_to_admins
from apps.core.models import AuditLog, SiteSettings
from apps.incidents.models import Incident

from . import services
from .forms import MemberRegisterForm, VerificationCodeForm
from .models import Member


def register(request):
    """Step 1: the 'Register as a Member' form."""
    user = request.user
    membership = user.membership if user.is_authenticated else None
    if membership is not None and membership.verified:
        messages.info(request, "You are already a verified member.")
        return redirect("membership:dashboard")

    form = MemberRegisterForm(request.POST or None, instance=Member(user=user if user.is_authenticated else None))
    if request.method == "POST" and form.is_valid():
        member = services.save_registration(form, request=request, user=user)
        _code, plaintext, report = services.issue_code(member)
        request.session["verification_member_pk"] = member.pk
        AuditLog.record(user if user.is_authenticated else None, "membership.registered", target=member.email, request=request)
        messages.success(request, "Almost done! We sent a 6-digit code to verify you. " + _delivery_note(report))
        if settings.DEBUG:
            messages.warning(request, f"Development mode - the code is {plaintext}.")
        return redirect("membership:verify")

    return render(
        request,
        "membership/register.html",
        {
            "form": form,
            "page_title": "Register as a Member",
            "logged_in_membership": membership,
        },
    )


def _delivery_note(report):
    sms = report.get("sms")
    email = report.get("email")
    parts = []
    if sms and sms.sent:
        parts.append("by SMS")
    if email:
        parts.append("by email")
    if not parts:
        return "If it does not arrive within a few minutes, use 'Send the code again'."
    return "It was sent " + " and ".join(parts) + "."


def verify(request):
    """Step 2: the member types the 6-digit code."""
    member = _member_in_play(request)
    if member is None:
        messages.warning(request, "Start by filling the membership form.")
        return redirect("membership:register")
    if member.verified:
        return redirect("membership:dashboard")

    if request.method == "POST" and "resend" in request.POST:
        allowed, seconds = member.can_resend_code
        if not allowed:
            messages.error(request, f"Please wait {seconds} seconds before requesting another code.")
        else:
            _code, plaintext, report = services.issue_code(member)
            messages.info(request, "A new code is on its way. " + _delivery_note(report))
            if settings.DEBUG:
                messages.warning(request, f"Development mode - the code is {plaintext}.")
        return redirect("membership:verify")

    form = VerificationCodeForm(request.POST or None)
    code = services.current_code(member)
    if request.method == "POST" and form.is_valid():
        ok, message = services.check_code(member, form.cleaned_data["code"])
        if not ok:
            messages.error(request, message)
            return render(
                request,
                "membership/verify.html",
                {"form": form, "member": member, "code": code, "page_title": "Confirm your code"},
            )
        result = services.confirm_membership(member, request)
        AuditLog.record(result["user"], "membership.verified", target=member.membership_no, request=request)
        _auto_login(request, result)
        messages.success(
            request,
            f"Welcome to Kagan Owacho CBO, {member.full_name}! Your membership number is {member.membership_no}.",
        )
        if result["created_account"]:
            messages.info(request, "Please set your password from the dashboard (check your email too).")
        request.session.pop("verification_member_pk", None)
        return redirect("membership:dashboard")

    return render(
        request,
        "membership/verify.html",
        {
            "form": form,
            "member": member,
            "code": code,
            "page_title": "Confirm your code",
            "cooldown_seconds": max(0, settings.VERIFICATION_RESEND_COOLDOWN_SECONDS - _seconds_since(member)),
        },
    )


def _seconds_since(member):
    if not member.last_code_sent_at:
        return 0
    from django.utils import timezone

    return int((timezone.now() - member.last_code_sent_at).total_seconds())


def _member_in_play(request):
    pk = request.session.get("verification_member_pk")
    if pk:
        member = Member.objects.filter(pk=pk).first()
        if member:
            return member
    if request.user.is_authenticated:
        return Member.objects.filter(user=request.user, verified=False).order_by("-created_at").first()
    return None


def _auto_login(request, result):
    """Members who came from the public form get signed in; admins stay where they are."""
    user = result["user"]
    if request.user.is_authenticated or user is None:
        return
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")


def pending(request):
    """Shown when a logged-in account has not finished membership verification."""
    membership = Member.objects.filter(user=request.user).order_by("-created_at").first() if request.user.is_authenticated else None
    if membership is None:
        return redirect("membership:register")
    if membership.verified:
        return redirect("membership:dashboard")
    request.session["verification_member_pk"] = membership.pk
    return render(
        request,
        "membership/pending.html",
        {"member": membership, "page_title": "Finish your membership"},
    )


@member_required
def dashboard(request):
    from apps.contributions.models import Contribution
    from apps.events.models import Event

    member = request.user.membership
    site = SiteSettings.load()
    totals = Contribution.totals(member)
    return render(
        request,
        "membership/dashboard.html",
        {
            "member": member,
            "site": site,
            "totals": totals,
            "recent_contributions": Contribution.objects.filter(member=member).order_by("-created_at")[:5],
            "incidents": Incident.objects.filter(member=member).order_by("-created_at")[:5],
            "upcoming_events": Event.objects.filter(published=True).order_by("starts_at")[:3],
            "page_title": "My dashboard",
            "active_section": "dashboard",
        },
    )


@member_required
def location(request):
    site = SiteSettings.load()
    return render(
        request,
        "membership/location.html",
        {"site": site, "page_title": "Where to find us", "active_section": "location"},
    )


@member_required
def contact_us(request):
    member = request.user.membership
    initial = {"name": member.full_name, "email": member.email, "phone": member.phone}
    form = ContactMessageForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        message = form.save(commit=False)
        message.member = member
        message.save()
        send_contact_message_to_admins(message)
        AuditLog.record(request.user, "contact.message", target=message.subject, request=request)
        messages.success(request, "Your message reached the admin team. They will reply by email.")
        return redirect("membership:dashboard")
    return render(
        request,
        "membership/contact.html",
        {"form": form, "site": SiteSettings.load(), "page_title": "Email us", "active_section": "contact"},
    )
