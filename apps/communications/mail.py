"""Email helpers. Falls back to the console backend when SMTP is not configured."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_text_email(subject, message, recipients):
    """Return the number of addresses accepted (0 with a failure)."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return 0
    try:
        return send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:  # pragma: no cover - depends on the mail server
        logger.warning("Email to %s failed: %s", recipients, exc)
        return 0


def send_template_email(subject, template_name, context, recipients, html_template=None):
    body = render_to_string(template_name, context)
    recipients = [r for r in recipients if r]
    if not recipients:
        return 0
    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    if html_template:
        email.attach_alternative(render_to_string(html_template, context), "text/html")
    try:
        return email.send()
    except Exception as exc:  # pragma: no cover
        logger.warning("Templated email failed: %s", exc)
        return 0


def notify_admins(subject, message):
    """Admin inbox is a single address from .env (ADMIN_INBOX_EMAIL)."""
    return send_text_email(f"[{settings.ORGANIZATION_NAME}] {subject}", message, [settings.ADMIN_INBOX_EMAIL])
