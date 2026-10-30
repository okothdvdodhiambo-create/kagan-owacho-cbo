"""Account tests: signing up, logging in, throttling, profile photos and password reset."""

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.forms import SignupForm
from apps.accounts.models import LoginAttempt, User
from apps.core.testing import MediaRootMixin, make_admin, png_upload


class SignupTests(TestCase):
    def test_valid_signup_creates_hashed_account(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "name": "Peter Odhiambo",
                "email": "Peter@Example.COM",
                "phone": "0712 345 678",
                "password1": "Kagan#Fees2026",
                "password2": "Kagan#Fees2026",
            },
        )
        self.assertRedirects(response, reverse("membership:register"))
        user = User.objects.get(email="peter@example.com")
        self.assertNotEqual(user.password, "Kagan#Fees2026")
        self.assertTrue(user.check_password("Kagan#Fees2026"))
        self.assertEqual(user.phone, "+254712345678")

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(email="dup@example.com", name="One", password="Strong#Pass1")
        form = SignupForm(
            {
                "name": "Two",
                "email": "dup@example.com",
                "password1": "Strong#Pass2",
                "password2": "Strong#Pass2",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("already has an account", form.errors["email"][0])

    def test_weak_password_is_rejected(self):
        form = SignupForm(
            {"name": "Weak", "email": "weak@example.com", "password1": "password", "password2": "password"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)

    def test_passwords_must_match(self):
        form = SignupForm(
            {
                "name": "Mismatch",
                "email": "mismatch@example.com",
                "password1": "First#Pass123",
                "password2": "Second#Pass123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("do not match", form.errors["password2"][0])

    def test_non_kenyan_phone_is_rejected(self):
        form = SignupForm(
            {
                "name": "Phone",
                "email": "phone@example.com",
                "phone": "12345",
                "password1": "Strong#Pass1",
                "password2": "Strong#Pass1",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Kenyan", form.errors["phone"][0])


class ProfilePhotoTests(MediaRootMixin, TestCase):
    def test_large_photo_is_resized_and_stored(self):
        self.enable_temp_media()
        big = png_upload(name="big.png", size=(1600, 1200))
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "name": "Photo Person",
                "email": "photo@example.com",
                "password1": "Strong#Pass1",
                "password2": "Strong#Pass1",
                "photo": big,
            },
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
        self.member = User.objects.create_user(
            email="member@example.com", name="Member", password="Member#2026"
        )
        self.admin = make_admin()

    def _login(self, email, password):
        return self.client.post(
            reverse("accounts:login"), {"username": email, "password": password}
        )

    def test_member_goes_home(self):
        response = self._login("member@example.com", "Member#2026")
        self.assertRedirects(response, reverse("core:home"))

    def test_email_is_matched_case_insensitively(self):
        response = self._login("MEMBER@example.com", "Member#2026")
        self.assertRedirects(response, reverse("core:home"))

    def test_admin_lands_on_the_admin_dashboard(self):
        response = self._login("committee@example.org", "Committee#2026")
        self.assertRedirects(response, reverse("admin_panel:dashboard"))

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
