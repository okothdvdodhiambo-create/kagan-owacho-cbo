"""Send one real test email and report exactly what the mail server said.

    python manage.py send_test_email you@example.com

Prints the effective settings (the password is reported as set/not set, never shown),
then attempts a delivery and prints the exception type, the SMTP response code and the
server's own words. Exits non-zero when nothing was delivered, so it can be scripted.
"""

import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.utils import timezone

from apps.communications.mail import (
    email_configuration_lines,
    email_configuration_warnings,
    email_reaches_the_outside_world,
    smtp_error_hint,
)


class Command(BaseCommand):
    help = "Send a test email and print the effective SMTP settings plus the exact error, if any."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Address to send the test message to.")

    def handle(self, *args, **options):
        recipient = options["recipient"].strip()
        try:
            validate_email(recipient)
        except ValidationError:
            raise CommandError(f"'{recipient}' is not a valid email address.")

        self.stdout.write(self.style.MIGRATE_HEADING("Effective email configuration"))
        for line in email_configuration_lines():
            self.stdout.write(f"  {line}")

        warnings = email_configuration_warnings()
        if warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Problems found before sending:"))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"  - {warning}"))

        self.stdout.write("")
        self.stdout.write(f"Sending a test message to {recipient} ...")
        message = EmailMessage(
            subject=f"{settings.ORGANIZATION_NAME} - SMTP test",
            body=(
                f"This is a test message from {settings.ORGANIZATION_NAME}.\n\n"
                f"Sent at {timezone.localtime().strftime('%d %b %Y %H:%M:%S %Z')}.\n"
                f"Mail server: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
                f"(TLS={settings.EMAIL_USE_TLS}, SSL={settings.EMAIL_USE_SSL}).\n\n"
                "If you can read this, the server accepted the message. Check the spam folder "
                "before concluding that verification codes are broken."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )

        started = time.monotonic()
        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:
            elapsed = time.monotonic() - started
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"FAILED after {elapsed:.2f}s"))
            for line in self._describe(exc):
                self.stdout.write(self.style.ERROR(f"  {line}"))
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"Likely fix: {smtp_error_hint(exc)}"))
            raise CommandError(f"The test email to {recipient} was not sent. See the error above.")

        elapsed = time.monotonic() - started
        if not email_reaches_the_outside_world():
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"The {settings.EMAIL_BACKEND} backend handled the message in {elapsed:.2f}s but "
                    "does not deliver mail - it was only printed or stored on this server. "
                    "Nothing was sent to the recipient."
                )
            )
            raise CommandError(
                "No mail left the server. Set EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, "
                "EMAIL_HOST_PASSWORD and DEFAULT_FROM_EMAIL, then run this command again."
            )
        if not sent:
            raise CommandError(f"The backend accepted 0 messages for {recipient} without raising an error.")

        self.stdout.write(self.style.SUCCESS(f"ACCEPTED by {settings.EMAIL_HOST}:{settings.EMAIL_PORT} in {elapsed:.2f}s"))
        self.stdout.write(
            "Accepted is not the same as delivered: the receiving provider can still spam-folder or "
            "silently drop it. If this test arrives but verification codes do not, the code path is "
            "fine and the problem is the recipient's mailbox."
        )

    def _describe(self, exc):
        """The exception's own words, with the password redacted in case a server echoes it."""
        lines = [f"{type(exc).__module__}.{type(exc).__name__}: {self._redact(str(exc))}"]
        code = getattr(exc, "smtp_code", None)
        if code is not None:
            lines.append(f"SMTP response code: {code}")
        response = getattr(exc, "smtp_error", None)
        if response:
            text = response.decode("utf-8", "replace") if isinstance(response, bytes) else str(response)
            lines.append(f"Server said: {self._redact(text)}")
        refused = getattr(exc, "recipients", None)
        if isinstance(refused, dict):
            for address, (rcode, rtext) in refused.items():
                text = rtext.decode("utf-8", "replace") if isinstance(rtext, bytes) else str(rtext)
                lines.append(f"Refused {address}: {rcode} {self._redact(text)}")
        if exc.__cause__ is not None:
            lines.append(f"Caused by: {type(exc.__cause__).__name__}: {self._redact(str(exc.__cause__))}")
        return lines

    @staticmethod
    def _redact(text):
        password = settings.EMAIL_HOST_PASSWORD or ""
        return text.replace(password, "[redacted]") if password else text