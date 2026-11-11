"""Email helpers. Every send writes its outcome to the log.

On a free Render instance the Logs tab is the only place a live SMTP failure can be
read, so success and failure both name the backend, the server, and what it said.
The password is never logged, never printed, and never included in an exception hint.
"""

import logging
import re
import smtplib
import socket
import ssl
import time
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# These backends print or store the message on the server itself. They report success,
# but no mail ever reaches an inbox - the classic "it said sent, nothing arrived" trap.
LOCAL_BACKENDS = ("console", "locmem", "dummy", "filebased")


def email_reaches_the_outside_world():
    """False when the configured backend cannot deliver mail to a real inbox."""
    return not any(f".{name}." in settings.EMAIL_BACKEND for name in LOCAL_BACKENDS)


def email_only_prints_on_a_live_site():
    """True when a live site fell back to the console backend because EMAIL_HOST is empty.

    That backend returns 1, so every caller believes the code was sent. Only DEBUG keeps
    it honest locally; on Render it is the reason "it said sent" and "nothing arrived"
    can both be true.
    """
    return not settings.DEBUG and ".console." in settings.EMAIL_BACKEND


def email_configuration_lines():
    """The effective settings, safe to show: the password is reported, never revealed."""
    password = settings.EMAIL_HOST_PASSWORD or ""
    shown = f"set, {len(password)} characters" if password else "NOT SET"
    return [
        f"EMAIL_BACKEND       = {settings.EMAIL_BACKEND}",
        f"EMAIL_HOST          = {settings.EMAIL_HOST}",
        f"EMAIL_PORT          = {settings.EMAIL_PORT}",
        f"EMAIL_USE_TLS       = {settings.EMAIL_USE_TLS}",
        f"EMAIL_USE_SSL       = {settings.EMAIL_USE_SSL}",
        f"EMAIL_TIMEOUT       = {settings.EMAIL_TIMEOUT} seconds",
        f"EMAIL_HOST_USER     = {settings.EMAIL_HOST_USER or 'NOT SET'}",
        f"EMAIL_HOST_PASSWORD = {shown}",
        f"DEFAULT_FROM_EMAIL  = {settings.DEFAULT_FROM_EMAIL}",
        f"DEBUG               = {settings.DEBUG}",
    ]


def email_configuration_warnings():
    """Plain-English problems with the current settings, checked before anything is sent."""
    warnings = []
    if not email_reaches_the_outside_world():
        warnings.append(
            f"{settings.EMAIL_BACKEND} does not deliver mail. It only prints or stores it on the "
            "server, so the site can report success while no inbox ever receives anything. "
            "Set EMAIL_HOST (and the credentials) to switch to SMTP."
        )
    if settings.EMAIL_HOST in ("", "localhost"):
        warnings.append("EMAIL_HOST is empty, so it fell back to 'localhost'. Nothing will be delivered.")
    if "smtp" in settings.EMAIL_BACKEND:
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            warnings.append(
                "EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is empty. Django skips login entirely when "
                "either is missing, and Gmail then refuses the message with 'Authentication required'."
            )
        if settings.EMAIL_PORT == 465 and not settings.EMAIL_USE_SSL:
            warnings.append("Port 465 needs EMAIL_USE_SSL=True and EMAIL_USE_TLS=False.")
        if settings.EMAIL_PORT == 587 and not settings.EMAIL_USE_TLS:
            warnings.append("Port 587 needs EMAIL_USE_TLS=True and EMAIL_USE_SSL=False.")
        if settings.EMAIL_PORT == 25:
            warnings.append("Port 25 is blocked by most hosts, including Render. Use 587 or 465.")
        sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].lower()
        user = settings.EMAIL_HOST_USER.lower()
        if sender and user and sender != user:
            warnings.append(
                f"DEFAULT_FROM_EMAIL ({sender}) is not EMAIL_HOST_USER ({user}). Gmail rewrites or "
                "refuses a From address it does not own, so the mail can be accepted and still never "
                "arrive. Make them the same address, or add the sender as a verified alias."
            )
    return warnings


def smtp_error_hint(exc):
    """Turn the exception the mail server produced into the setting that fixes it."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            "The server rejected the login. For Gmail, EMAIL_HOST_PASSWORD must be a 16-character "
            "App Password (myaccount.google.com -> Security -> 2-Step Verification -> App passwords), "
            "not the account password, and EMAIL_HOST_USER must be the full address."
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The server refused the From address. Make DEFAULT_FROM_EMAIL the authenticated account."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The server refused the recipient address. Check it for typos."
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "The server closed the connection, usually a TLS/SSL mismatch: port 465 needs "
            "EMAIL_USE_SSL=True, port 587 needs EMAIL_USE_TLS=True."
        )
    if isinstance(exc, smtplib.SMTPConnectError):
        return "The server refused the connection. Check EMAIL_HOST and EMAIL_PORT."
    if isinstance(exc, smtplib.SMTPException):
        return f"SMTP error {getattr(exc, 'smtp_code', '?')}: check EMAIL_HOST, EMAIL_PORT and the TLS/SSL flags."
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "The server's certificate could not be verified. Check EMAIL_HOST matches the certificate."
    if isinstance(exc, ssl.SSLError):
        return "TLS/SSL handshake failed. Port 465 needs EMAIL_USE_SSL=True; port 587 needs EMAIL_USE_TLS=True."
    if isinstance(exc, socket.gaierror):
        return (
            "EMAIL_HOST could not be resolved. Look for a typo, stray quotes or a trailing space "
            "in the value stored in Render's Environment tab."
        )
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return (
            f"No answer within EMAIL_TIMEOUT ({settings.EMAIL_TIMEOUT}s). The port is probably wrong "
            "or outbound SMTP is blocked: 465 -> EMAIL_USE_SSL=True, 587 -> EMAIL_USE_TLS=True."
        )
    if isinstance(exc, ConnectionRefusedError):
        return f"Nothing is listening on {settings.EMAIL_HOST}:{settings.EMAIL_PORT}. Check EMAIL_PORT."
    if isinstance(exc, ValueError) and "mutually exclusive" in str(exc):
        return "Set only one of EMAIL_USE_TLS / EMAIL_USE_SSL to True."
    if isinstance(exc, OSError):
        return "Network error reaching the mail server. Check EMAIL_HOST, EMAIL_PORT and the TLS/SSL flags."
    return "Unexpected error - the traceback above names the cause."


def _safe_label(subject):
    """The verification subject carries the code itself; a log must not become a way to read it."""
    return re.sub(r"\b\d{6}\b", "[code redacted]", subject)


def _deliver(message, recipients, label):
    """Send one message and log exactly what happened. Returns the number accepted."""
    started = time.monotonic()
    label = _safe_label(label)
    server = f"{settings.EMAIL_HOST}:{settings.EMAIL_PORT}"
    flags = f"tls={settings.EMAIL_USE_TLS} ssl={settings.EMAIL_USE_SSL}"
    try:
        sent = message.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Email FAILED [%s] to %s via %s (%s %s) after %.2fs - %s: %s | Fix: %s",
            label,
            ", ".join(recipients),
            settings.EMAIL_BACKEND,
            server,
            flags,
            time.monotonic() - started,
            type(exc).__name__,
            exc,
            smtp_error_hint(exc),
            exc_info=True,
        )
        return 0

    elapsed = time.monotonic() - started
    if not email_reaches_the_outside_world():
        logger.warning(
            "Email [%s] to %s was handled by %s, which does not deliver mail. "
            "It was printed/stored on the server only, after %.2fs.",
            label,
            ", ".join(recipients),
            settings.EMAIL_BACKEND,
            elapsed,
        )
    elif sent:
        logger.info(
            "Email sent [%s] to %s via %s (%s %s) - %s accepted in %.2fs",
            label, ", ".join(recipients), settings.EMAIL_BACKEND, server, flags, sent, elapsed,
        )
    else:
        logger.error(
            "Email NOT accepted [%s] to %s via %s (%s %s) after %.2fs - the backend returned 0",
            label, ", ".join(recipients), settings.EMAIL_BACKEND, server, flags, elapsed,
        )
    return sent


def send_text_email(subject, message, recipients):
    """Return the number of addresses accepted (0 with a failure)."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return 0
    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    return _deliver(email, recipients, subject)


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
    return _deliver(email, recipients, subject)


def notify_admins(subject, message):
    """Admin inbox is a single address from .env (ADMIN_INBOX_EMAIL)."""
    return send_text_email(f"[{settings.ORGANIZATION_NAME}] {subject}", message, [settings.ADMIN_INBOX_EMAIL])