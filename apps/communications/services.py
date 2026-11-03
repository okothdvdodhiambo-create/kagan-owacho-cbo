"""One place that knows how to reach a member: SMS, email, or both."""

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.models import SiteSettings

from .mail import notify_admins, send_template_email, send_text_email
from .sms import send_sms, sms_configured


def _org():
    return SiteSettings.load().organization_name


def default_verification_channel():
    """Email is the default; SMS is only added when a real provider is configured."""
    return "both" if sms_configured() else "email"


def _member_context(member):
    return {
        "member": member,
        "org_name": _org(),
        "membership_no": member.membership_no or "pending",
        "year": timezone.localtime().year,
    }


def send_verification_code(member, plaintext, channel=None):
    """Deliver a 6-digit code by email, plus SMS when that channel is selected. Returns a report."""
    channel = channel or member.verification_channel or "email"
    report = {"sms": None, "email": 0}
    template_context = {**_member_context(member), "code": plaintext, "minutes": settings.VERIFICATION_TTL_MINUTES}

    if channel in ("email", "both") and member.email:
        subject = f"{_org()} - your verification code is {plaintext}"
        report["email"] = send_template_email(
            subject, "emails/verification_email.txt", template_context, [member.email]
        )

    if channel in ("sms", "both") and sms_configured():
        body = render_to_string("emails/verification_sms.txt", template_context).strip()
        report["sms"] = send_sms(member.phone, body)
    return report


def send_membership_confirmation(member):
    context = _member_context(member)
    subject = f"Welcome to {_org()} - membership {member.membership_no}"
    emailed = send_template_email(subject, "emails/membership_confirmed.txt", context, [member.email])
    sms = None
    if sms_configured():
        sms = send_sms(
            member.phone,
            render_to_string("emails/membership_confirmed_sms.txt", context).strip(),
        )
    return {"emailed": bool(emailed), "sms": bool(sms)}


def send_welcome_account_link(member, reset_url):
    """Sent when someone verifies a membership that has no login account yet."""
    context = {**_member_context(member), "reset_url": reset_url}
    return send_template_email(
        f"Set your password for {_org()}", "emails/account_created.txt", context, [member.email]
    )


def notify_admins_of_incident(incident):
    context = {"incident": incident, "org_name": _org(), "member": incident.member}
    subject = f"Incident report: {incident.title}"
    return notify_admins(subject, render_to_string("emails/admin_incident.txt", context))


def send_incident_reply(incident):
    reply = incident.responses.order_by("-created_at").first()
    if not reply:
        return 0
    context = {"incident": incident, "reply": reply, "org_name": _org(), "member": incident.member}
    return send_template_email(
        f"Update on your report '{incident.title}'", "emails/incident_reply.txt", context, [incident.member.email]
    )


def notify_member_of_contribution_status(contribution):
    context = {
        "contribution": contribution,
        "member": contribution.member,
        "org_name": _org(),
        "amount": contribution.amount,
    }
    emailed = send_template_email(
        f"Contribution {contribution.get_status_display().lower()}",
        "emails/contribution_status.txt",
        context,
        [contribution.member.email],
    )
    send_sms(
        contribution.member.phone,
        render_to_string("emails/contribution_status_sms.txt", context).strip(),
    )
    return bool(emailed)


def send_contact_message_to_admins(message):
    context = {"message": message, "org_name": _org()}
    return notify_admins(
        f"New message: {message.subject}",
        render_to_string("emails/admin_contact.txt", context),
    )


def broadcast_event_report(report):
    """Email a published report to every verified member; returns how many were accepted."""
    from apps.membership.models import Member

    context = {"report": report, "event": report.event, "org_name": _org()}
    sent = 0
    for member in Member.objects.filter(verified=True).exclude(email=""):
        sent += send_template_email(
            f"{_org()} report: {report.title}", "emails/event_report.txt", context, [member.email]
        )
    return sent


def deliver_campaign(campaign):
    """Send an EmailCampaign; returns (emails, sms, error_message)."""
    error = ""
    emails = sms = 0
    members = list(campaign.recipients())
    if not members:
        return 0, 0, "No members matched this audience."
    for member in members:
        if member.email:
            emails += send_text_email(campaign.subject, campaign.message, [member.email])
        if campaign.send_sms and member.phone:
            if send_sms(member.phone, f"{campaign.subject}: {campaign.message}"):
                sms += 1
    if emails == 0:
        error = "No email was accepted - check the SMTP settings in .env (codes/emails print to the console in development)."
    return emails, sms, error
