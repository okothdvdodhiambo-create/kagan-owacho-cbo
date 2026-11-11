"""One-step registration, code verification, and the member-facing pages."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.decorators import member_required
from apps.communications.forms import ContactMessageForm
from apps.communications.services import send_contact_message_to_admins
from apps.core.models import AuditLog, SiteSettings
from apps.incidents.models import Incident

from . import services
from .forms import CompleteMembershipForm, RegisterForm, VerificationCodeForm
from .models import Member


def register(request):
    """Create the account and the membership from a single form."""
    if request.user.is_authenticated:
        if request.user.is_administrator:
            return redirect("admin_panel:dashboard")
        return redirect("membership:complete")

    form = RegisterForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user, member = services.save_registration(form)
        _code, plaintext, report = services.issue_code(member)
        AuditLog.record(user, "account.created", target=user.email, request=request)
        AuditLog.record(user, "membership.registered", target=member.email, request=request)
        request.session["verification_member_pk"] = member.pk
        _announce_code(request, report, plaintext)
        return redirect("membership:verify")

    return render(
        request,
        "membership/register.html",
        {"form": form, "page_title": "Register as a Member"},
    )


@login_required
def complete(request):
    """Member details for an account that joined before the two steps merged."""
    user = request.user
    if user.is_administrator:
        return redirect("admin_panel:dashboard")

    member = Member.objects.filter(user=user).order_by("-created_at").first()
    if member is not None and member.verified:
        messages.info(request, "Your membership is already confirmed.")
        return redirect("membership:dashboard")

    form = CompleteMembershipForm(
        request.POST or None, member=member, initial={} if (member or request.POST) else {"phone": user.phone}
    )
    if request.method == "POST" and form.is_valid():
        member = services.save_membership_for_account(form, user, member)
        _code, plaintext, report = services.issue_code(member)
        AuditLog.record(user, "membership.registered", target=member.email, request=request)
        request.session["verification_member_pk"] = member.pk
        _announce_code(request, report, plaintext)
        return redirect("membership:verify")

    return render(
        request,
        "membership/complete.html",
        {"form": form, "member": member, "page_title": "Complete your membership"},
    )


def verify(request):
    """The member types the 6-digit code that was emailed to them."""
    member = _member_in_play(request)
    if member is None:
        messages.warning(request, "Start by filling the registration form.")
        return redirect("membership:register")
    if member.verified:
        return redirect("membership:pending")

    if request.method == "POST" and "resend" in request.POST:
        allowed, seconds = member.can_resend_code
        if not allowed:
            messages.error(request, f"Please wait {seconds} seconds before requesting another code.")
        else:
            _code, plaintext, report = services.issue_code(member)
            _announce_code(request, report, plaintext, resend=True)
        return redirect("membership:verify")

    form = VerificationCodeForm(request.POST or None)
    code = services.current_code(member)
    if request.method == "POST" and form.is_valid():
        ok, note = services.check_code(member, form.cleaned_data["code"])
        if not ok:
            messages.error(request, note)
            return render(
                request,
                "membership/verify.html",
                {"form": form, "member": member, "code": code, "page_title": "Confirm your code"},
            )
        result = services.confirm_membership(member, request)
        AuditLog.record(result["user"], "membership.verified", target=member.membership_no, request=request)
        _auto_login(request, result["user"])
        messages.success(
            request,
            f"Welcome to the CBO, {member.full_name}! Your membership number is {member.membership_no} "
            "and your account is now active.",
        )
        if result["created_account"]:
            messages.info(request, "We emailed you a link to set your password.")
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


def _announce_code(request, report, plaintext, resend=False):
    """Say where the code went, and say so plainly if it never left the server."""
    if services.email_not_configured():
        messages.error(request, services.EMAIL_NOT_CONFIGURED)
    elif services.email_failed(report):
        messages.error(
            request,
            "The verification email could not be sent right now. "
            + (
                "Please try 'Send the code again' in a moment, or contact the treasurer."
                if resend
                else "Your details are saved and your account stays inactive until it arrives - "
                "use 'Send the code again', or contact the treasurer if the problem continues."
            ),
        )
    else:
        prefix = "A new code is on its way. " if resend else "Almost done! "
        messages.success(request, prefix + _delivery_note(report))
    if settings.DEBUG:
        # Never depend on the mail server to know what the code was.
        messages.warning(request, f"Development mode - the code is {plaintext}.")


def _delivery_note(report):
    if (report or {}).get("email") and (report or {}).get("sms"):
        return "We sent a 6-digit code to your email and by SMS. It works for 10 minutes."
    if (report or {}).get("email"):
        return "We sent a 6-digit code to your email. It works for 10 minutes."
    return "Check your email for the 6-digit code. If it does not arrive, use 'Send the code again'."


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


def _auto_login(request, user):
    """The new member is signed in straight after the code; admins are left alone."""
    if request.user.is_authenticated or user is None or not user.is_active:
        return
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")


@login_required
def pending(request):
    """Landing page for anyone whose membership still needs confirming."""
    user = request.user
    if user.is_administrator:
        return redirect("admin_panel:dashboard")
    membership = Member.objects.filter(user=user).order_by("-created_at").first()
    if membership is None:
        return redirect("membership:complete")
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
