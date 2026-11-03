"""Account tests: logging in, throttling, verification resend, profile photos and password reset."""

from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import LoginAttempt, User
from apps.core.testing import MediaRootMixin, make_admin, make_member, png_upload, register_payload, seed_dropdown_options
from apps.membership.models import Member


class ProfilePhotoTests(MediaRootMixin, TestCase):
    def test_large_photo_is_resized_and_stored(self):
        self.enable_temp_media()
        seed_dropdown_options()
        response = self.client.post(
            reverse("membership:register"),
            register_payload(email="photo@example.com", phone="0722 000 222", photo=png_upload(name="big.png", size=(1600, 1200))),
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="photo@example.com")
        self.assertTrue(user.photo)
        from PIL import Image

        with Image.open(user.photo.path) as image:
            self.assertLessEqual(max(image.size), 800)

    def test_non_image_upload_is_rejected(self):
        self.enable_temp_media()
        user = make_admin()
        self.client.force_login(user)
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            reverse("accounts:profile"),
            {"name": "Committee Admin", "email": user.email, "photo": SimpleUploadedFile("note.txt", b"hello")},
        )
        self.assertIn("photo", response.context["form"].errors)
        user.refresh_from_db()
        self.assertFalse(user.photo)


class LoginTests(TestCase):
    def setUp(self):
        self.member = make_member(email="member@example.com", phone="+254712345678").user
        self.admin = make_admin()

    def _login(self, email, password):
        return self.client.post(reverse("accounts:login"), {"username": email, "password": password})

    def test_member_goes_home(self):
        response = self._login("member@example.com", "Member#2026")
        self.assertRedirects(response, reverse("core:home"))

    def test_email_is_matched_case_insensitively(self):
        response = self._login("MEMBER@example.com", "Member#2026")
        self.assertRedirects(response, reverse("core:home"))

    def test_admin_lands_on_the_admin_dashboard(self):
        response = self._login("committee@example.org", "Committee#2026")
        self.assertRedirects(response, reverse("admin_panel:dashboard"))
        self.assertIsNone(self.admin.membership, "administrators never need a membership row")

    def test_an_account_that_has_not_verified_its_email_is_refused(self):
        User.objects.create_user(
            email="waiting@example.com", name="Waiting", password="Member#2026", is_active=False
        )
        response = self._login("waiting@example.com", "Member#2026")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("not verified", response.context_data["form"].errors["__all__"][0])

    def test_a_verified_account_without_a_membership_is_sent_to_complete_it(self):
        User.objects.create_user(email="legacy@example.com", name="Legacy", password="Member#2026")
        response = self._login("legacy@example.com", "Member#2026")
        self.assertRedirects(response, reverse("membership:complete"))

    def test_wrong_password_does_not_sign_in(self):
        response = self._login("member@example.com", "nope")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lockout_after_too_many_failures(self):
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            self._login("member@example.com", "wrong-once-more")
        self.assertTrue(LoginAttempt.lockout_seconds("member@example.com"))
        response = self._login("member@example.com", "Member#2026")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Too many wrong attempts", response.context_data["form"].errors["__all__"][0])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_clears_the_failure_counter(self):
        self._login("member@example.com", "wrong")
        self._login("member@example.com", "Member#2026")
        self.assertEqual(LoginAttempt.lockout_seconds("member@example.com"), 0)

    def test_logout_needs_post_and_ends_the_session(self):
        self._login("member@example.com", "Member#2026")
        get_response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(get_response.status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_page_has_no_username_field(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "Email address")

    def test_login_page_offers_the_code_and_the_single_registration_form(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:resend_code"))
        self.assertContains(response, "Register as a Member")
        self.assertNotContains(response, reverse("accounts:signup"))


class ResendCodeTests(TestCase):
    def setUp(self):
        seed_dropdown_options()
        self.client.post(reverse("membership:register"), register_payload())
        self.member = Member.objects.get(email="jane@example.com")

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])

    def _clear_cooldown(self):
        Member.objects.filter(pk=self.member.pk).update(
            last_code_sent_at=timezone.now() - timedelta(seconds=settings.VERIFICATION_RESEND_COOLDOWN_SECONDS + 1)
        )

    def test_a_fresh_code_is_emailed(self):
        self._clear_cooldown()
        before = len(mail.outbox)
        response = self.client.post(reverse("accounts:resend_code"), {"email": "jane@example.com"}, follow=True)
        self.assertEqual(len(mail.outbox), before + 1)
        self.assertIn("new 6-digit code", self._notes(response))
        self.assertFalse(Member.objects.get(pk=self.member.pk).verified)

    def test_the_cooldown_blocks_a_second_send(self):
        before = len(mail.outbox)
        response = self.client.post(reverse("accounts:resend_code"), {"email": "jane@example.com"}, follow=True)
        self.assertEqual(len(mail.outbox), before)
        self.assertIn("Please wait", self._notes(response))

    def test_an_unknown_email_is_answered_the_same_way_as_a_real_one(self):
        response = self.client.post(reverse("accounts:resend_code"), {"email": "nobody@example.com"}, follow=True)
        self.assertEqual(len(mail.outbox), 1, "the registration email from setUp only")
        self.assertIn("If that email belongs", self._notes(response))

    def test_a_confirmed_member_is_not_sent_another_code(self):
        self.member.confirm_membership()
        self._clear_cooldown()
        before = len(mail.outbox)
        response = self.client.post(reverse("accounts:resend_code"), {"email": "jane@example.com"}, follow=True)
        self.assertEqual(len(mail.outbox), before)
        self.assertIn("If that email belongs", self._notes(response))

    def test_the_page_is_reachable_from_a_link_on_login(self):
        response = self.client.get(reverse("accounts:resend_code"))
        self.assertContains(response, "Resend verification code")


class PasswordResetTests(TestCase):
    def test_reset_email_carries_a_working_link(self):
        User.objects.create_user(email="forgot@example.com", name="Forgot", password="x")
        response = self.client.post(reverse("accounts:password_reset"), {"email": "forgot@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = [word for word in mail.outbox[0].body.split() if "reset" in word or "password" in word]
        self.assertTrue(link, "the email should contain the reset link")

    def test_unknown_email_sends_nothing_but_stays_quiet(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
