"""Email diagnostics: what the settings say, what the log records, and what the command reports."""

import os
import smtplib
import socket
import ssl
from io import StringIO
from unittest import mock

from django.conf import settings as django_settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from config import settings as settings_module

from .mail import (
    email_configuration_lines,
    email_configuration_warnings,
    email_only_prints_on_a_live_site,
    email_reaches_the_outside_world,
    send_template_email,
    send_text_email,
    smtp_error_hint,
)

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
SECRET = "app-password-value-never-printed"

LIVE_SMTP = {
    "EMAIL_BACKEND": SMTP,
    "EMAIL_HOST": "smtp.example.com",
    "EMAIL_PORT": 587,
    "EMAIL_USE_TLS": True,
    "EMAIL_USE_SSL": False,
    "EMAIL_HOST_USER": "treasurer@example.com",
    "EMAIL_HOST_PASSWORD": SECRET,
    "DEFAULT_FROM_EMAIL": "treasurer@example.com",
}


class EnvironmentReadingTests(SimpleTestCase):
    """Render's Environment tab hands values over exactly as they were pasted."""

    def test_pasted_quotes_and_spaces_are_trimmed(self):
        with mock.patch.dict(os.environ, {"EMAIL_HOST": '  "smtp.gmail.com"  '}):
            self.assertEqual(settings_module._env_text("EMAIL_HOST"), "smtp.gmail.com")

    def test_a_missing_variable_uses_the_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings_module._env_text("KOCO_UNSET_TEST_KEY", "fallback"), "fallback")

    def test_flags_accept_the_words_people_actually_type(self):
        for raw in ("True", "true", " TRUE ", "1", "yes", "on"):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"EMAIL_USE_SSL": raw}):
                self.assertIs(settings_module._env_flag("EMAIL_USE_SSL", False), True)
        for raw in ("False", "false", "0", "no", "off"):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"EMAIL_USE_SSL": raw}):
                self.assertIs(settings_module._env_flag("EMAIL_USE_SSL", True), False)

    def test_an_empty_flag_falls_back_to_the_default(self):
        with mock.patch.dict(os.environ, {"EMAIL_USE_TLS": ""}):
            self.assertIs(settings_module._env_flag("EMAIL_USE_TLS", True), True)

    def test_environment_wins_over_the_env_file(self):
        with mock.patch.dict(os.environ, {"EMAIL_HOST": "smtp.from-render.com"}):
            self.assertEqual(settings_module._env_text("EMAIL_HOST"), "smtp.from-render.com")

    def test_ssl_is_a_real_setting(self):
        self.assertTrue(hasattr(django_settings, "EMAIL_USE_SSL"))


class BackendDetectionTests(SimpleTestCase):
    def test_only_a_delivering_backend_counts_as_live_email(self):
        for backend in (CONSOLE, LOCMEM, "django.core.mail.backends.dummy.EmailBackend"):
            with self.subTest(backend=backend), override_settings(EMAIL_BACKEND=backend):
                self.assertFalse(email_reaches_the_outside_world())
        with override_settings(EMAIL_BACKEND=SMTP):
            self.assertTrue(email_reaches_the_outside_world())

    def test_a_live_site_on_the_console_backend_is_flagged(self):
        with override_settings(DEBUG=False, EMAIL_BACKEND=CONSOLE):
            self.assertTrue(email_only_prints_on_a_live_site())

    def test_the_same_backend_is_fine_while_developing(self):
        with override_settings(DEBUG=True, EMAIL_BACKEND=CONSOLE):
            self.assertFalse(email_only_prints_on_a_live_site())

    def test_a_live_site_with_smtp_is_not_flagged(self):
        with override_settings(DEBUG=False, **LIVE_SMTP):
            self.assertFalse(email_only_prints_on_a_live_site())

    def test_the_test_backend_is_not_mistaken_for_a_broken_site(self):
        # The suite runs with DEBUG=False and locmem; that must not warn every member.
        with override_settings(DEBUG=False, EMAIL_BACKEND=LOCMEM):
            self.assertFalse(email_only_prints_on_a_live_site())


class ConfigurationReportTests(SimpleTestCase):
    def test_the_password_is_reported_but_never_shown(self):
        with override_settings(**LIVE_SMTP):
            report = "\n".join(email_configuration_lines())
        self.assertNotIn(SECRET, report)
        self.assertIn(f"set, {len(SECRET)} characters", report)
        self.assertIn("smtp.example.com", report)

    def test_an_unset_password_says_so(self):
        with override_settings(EMAIL_HOST_PASSWORD=""):
            self.assertIn("NOT SET", "\n".join(email_configuration_lines()))

    def test_port_465_without_ssl_is_reported(self):
        with override_settings(**{**LIVE_SMTP, "EMAIL_PORT": 465, "EMAIL_USE_TLS": False}):
            warnings = " ".join(email_configuration_warnings())
        self.assertIn("465 needs EMAIL_USE_SSL=True", warnings)

    def test_port_587_without_tls_is_reported(self):
        with override_settings(**{**LIVE_SMTP, "EMAIL_USE_TLS": False}):
            self.assertIn("587 needs EMAIL_USE_TLS=True", " ".join(email_configuration_warnings()))

    def test_missing_credentials_are_reported(self):
        with override_settings(**{**LIVE_SMTP, "EMAIL_HOST_PASSWORD": ""}):
            self.assertIn("skips login entirely", " ".join(email_configuration_warnings()))

    def test_a_from_address_the_server_does_not_own_is_reported(self):
        with override_settings(**{**LIVE_SMTP, "DEFAULT_FROM_EMAIL": "Kagan <no-reply@kaganowacho.org>"}):
            warnings = " ".join(email_configuration_warnings())
        self.assertIn("no-reply@kaganowacho.org", warnings)
        self.assertIn("rewrites or refuses", warnings)

    def test_a_matching_from_address_is_not_reported(self):
        with override_settings(**LIVE_SMTP):
            self.assertEqual(email_configuration_warnings(), [])

    def test_the_console_fallback_is_reported_as_non_delivering(self):
        with override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="localhost"):
            warnings = " ".join(email_configuration_warnings())
        self.assertIn("does not deliver mail", warnings)
        self.assertIn("fell back to 'localhost'", warnings)


class ErrorHintTests(SimpleTestCase):
    def test_authentication_failure_points_at_the_app_password(self):
        hint = smtp_error_hint(smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted"))
        self.assertIn("App Password", hint)

    def test_a_refused_sender_points_at_default_from_email(self):
        hint = smtp_error_hint(smtplib.SMTPSenderRefused(555, b"bad sender", "no-reply@example.org"))
        self.assertIn("DEFAULT_FROM_EMAIL", hint)

    def test_an_unresolvable_host_points_at_the_pasted_value(self):
        self.assertIn("trailing space", smtp_error_hint(socket.gaierror(8, "nodename nor servname provided")))

    def test_a_timeout_points_at_the_port_and_the_flags(self):
        with override_settings(**LIVE_SMTP):
            hint = smtp_error_hint(TimeoutError("timed out"))
        self.assertIn("EMAIL_USE_SSL=True", hint)
        self.assertIn("587", hint)

    def test_a_disconnection_points_at_the_tls_mismatch(self):
        self.assertIn("TLS/SSL mismatch", smtp_error_hint(smtplib.SMTPServerDisconnected("Connection unexpectedly closed")))

    def test_a_certificate_problem_is_named(self):
        self.assertIn("certificate", smtp_error_hint(ssl.SSLCertVerificationError("certificate verify failed")))


class SendLoggingTests(TestCase):
    def test_a_successful_send_is_logged_with_the_server_and_the_count(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=1) as send:
                with self.assertLogs("apps.communications.mail", level="INFO") as captured:
                    sent = send_text_email("Your code", "123456", ["jane@example.com"])
        self.assertEqual(sent, 1)
        send.assert_called_once()
        line = "\n".join(captured.output)
        self.assertIn("Email sent", line)
        self.assertIn("jane@example.com", line)
        self.assertIn("smtp.example.com:587", line)
        self.assertNotIn(SECRET, line)

    def test_a_failure_is_logged_with_the_exact_exception_and_returns_zero(self):
        error = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", side_effect=error):
                with self.assertLogs("apps.communications.mail", level="ERROR") as captured:
                    sent = send_text_email("Your code", "123456", ["jane@example.com"])
        self.assertEqual(sent, 0)
        line = "\n".join(captured.output)
        self.assertIn("Email FAILED", line)
        self.assertIn("SMTPAuthenticationError", line)
        self.assertIn("535", line)
        self.assertIn("App Password", line)
        self.assertNotIn(SECRET, line)

    def test_a_verification_code_in_the_subject_is_never_written_to_the_log(self):
        subject = "KAGAN OWACHO CBO - your verification code is 208201"
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", side_effect=OSError("smtp is down")):
                with self.assertLogs("apps.communications.mail", level="ERROR") as captured:
                    send_text_email(subject, "208201", ["jane@example.com"])
        line = "\n".join(captured.output)
        self.assertNotIn("208201", line)
        self.assertIn("[code redacted]", line)

    def test_a_code_is_redacted_on_a_successful_send_too(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=1):
                with self.assertLogs("apps.communications.mail", level="INFO") as captured:
                    send_text_email("Your verification code is 481920", "481920", ["jane@example.com"])
        line = "\n".join(captured.output)
        self.assertNotIn("481920", line)
        self.assertIn("Email sent", line)

    def test_a_membership_number_is_still_readable_in_the_log(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=1):
                with self.assertLogs("apps.communications.mail", level="INFO") as captured:
                    send_text_email("Welcome - membership KOC-0001", "body", ["jane@example.com"])
        self.assertIn("KOC-0001", "\n".join(captured.output))

    def test_a_backend_that_only_stores_mail_says_so_out_loud(self):
        with override_settings(EMAIL_BACKEND=LOCMEM):
            with self.assertLogs("apps.communications.mail", level="WARNING") as captured:
                send_text_email("Your code", "123456", ["jane@example.com"])
        self.assertIn("does not deliver mail", "\n".join(captured.output))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_templated_email_is_logged_too(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=1):
                with self.assertLogs("apps.communications.mail", level="INFO") as captured:
                    sent = send_template_email(
                        "Code", "emails/verification_email.txt", {"code": "123456", "minutes": 10}, ["jane@example.com"]
                    )
        self.assertEqual(sent, 1)
        self.assertIn("Email sent", "\n".join(captured.output))

    def test_no_recipients_means_no_send_and_no_log(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send") as send:
                self.assertEqual(send_text_email("Subject", "Body", ["", None]), 0)
        send.assert_not_called()


class SendTestEmailCommandTests(TestCase):
    def call(self, recipient="jane@example.com"):
        out = StringIO()
        call_command("send_test_email", recipient, stdout=out, stderr=out)
        return out.getvalue()

    def test_an_invalid_address_is_refused_before_anything_is_sent(self):
        with mock.patch.object(mail.EmailMessage, "send") as send:
            with self.assertRaises(CommandError) as raised:
                self.call("not-an-address")
        self.assertIn("not a valid email address", str(raised.exception))
        send.assert_not_called()

    def test_the_console_backend_reports_that_nothing_left_the_server(self):
        with override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="localhost", EMAIL_HOST_PASSWORD=SECRET):
            with self.assertRaises(CommandError) as raised:
                self.call()
        self.assertIn("No mail left the server", str(raised.exception))

    def test_the_configuration_is_printed_without_the_password(self):
        out = StringIO()
        with override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_HOST_PASSWORD=SECRET):
            with self.assertRaises(CommandError):
                call_command("send_test_email", "jane@example.com", stdout=out, stderr=out)
        text = out.getvalue()
        self.assertIn("EMAIL_HOST_PASSWORD", text)
        self.assertIn(f"set, {len(SECRET)} characters", text)
        self.assertNotIn(SECRET, text)

    def test_a_live_smtp_send_reports_success(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=1):
                out = self.call()
        self.assertIn("ACCEPTED by smtp.example.com:587", out)
        self.assertIn("Accepted is not the same as delivered", out)

    def test_the_exact_smtp_error_is_reported(self):
        error = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", side_effect=error):
                out = StringIO()
                with self.assertRaises(CommandError) as raised:
                    call_command("send_test_email", "jane@example.com", stdout=out, stderr=out)
        text = out.getvalue()
        self.assertIn("SMTPAuthenticationError", text)
        self.assertIn("SMTP response code: 535", text)
        self.assertIn("Username and Password not accepted", text)
        self.assertIn("App Password", text)
        self.assertIn("was not sent", str(raised.exception))
        self.assertNotIn(SECRET, text)

    def test_a_server_that_echoes_the_password_is_redacted(self):
        error = smtplib.SMTPAuthenticationError(535, f"rejected {SECRET}".encode())
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", side_effect=error):
                out = StringIO()
                with self.assertRaises(CommandError):
                    call_command("send_test_email", "jane@example.com", stdout=out, stderr=out)
        text = out.getvalue()
        self.assertNotIn(SECRET, text)
        self.assertIn("[redacted]", text)

    def test_a_timeout_reports_the_port_and_the_fix(self):
        with override_settings(**{**LIVE_SMTP, "EMAIL_PORT": 465, "EMAIL_USE_TLS": False}):
            with mock.patch.object(mail.EmailMessage, "send", side_effect=TimeoutError("timed out")):
                out = StringIO()
                with self.assertRaises(CommandError):
                    call_command("send_test_email", "jane@example.com", stdout=out, stderr=out)
        text = out.getvalue()
        self.assertIn("TimeoutError", text)
        self.assertIn("465 needs EMAIL_USE_SSL=True", text)

    def test_a_backend_that_accepts_nothing_is_a_failure(self):
        with override_settings(**LIVE_SMTP):
            with mock.patch.object(mail.EmailMessage, "send", return_value=0):
                with self.assertRaises(CommandError) as raised:
                    self.call()
        self.assertIn("accepted 0 messages", str(raised.exception))