"""Membership registration and the 6-digit verification code rules."""

import importlib
from datetime import timedelta
from unittest import mock

from django.apps import apps as global_apps
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.communications.services import default_verification_channel
from apps.core.testing import (
    make_admin,
    make_member,
    member_details_payload,
    register_payload,
    seed_dropdown_options,
)
from apps.membership import services
from apps.membership.forms import CompleteMembershipForm
from apps.membership.models import DropdownOption, Member, VerificationCode

legacy_migration = importlib.import_module(
    "apps.membership.migrations.0003_give_every_account_a_membership"
)


class RegistrationViewTests(TestCase):
    def setUp(self):
        seed_dropdown_options()

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])

    def test_form_shows_only_active_options(self):
        DropdownOption.objects.create(field="role", label="Retired Role", active=False)
        response = self.client.get(reverse("membership:register"))
        self.assertContains(response, "Youth Member")
        self.assertNotContains(response, "Retired Role")

    def test_one_form_creates_the_account_and_the_membership(self):
        response = self.client.post(reverse("membership:register"), register_payload())
        self.assertRedirects(response, reverse("membership:verify"))
        user = User.objects.get(email="jane@example.com")
        self.assertFalse(user.is_active, "an account stays closed until the emailed code arrives")
        self.assertTrue(user.check_password("Member#2026"))
        self.assertEqual(user.phone, "+254712345678")
        member = Member.objects.get(email="jane@example.com")
        self.assertEqual(member.user, user)
        self.assertFalse(member.verified)
        self.assertEqual(member.status, Member.Status.PENDING)
        self.assertEqual(member.phone, "+254712345678")
        self.assertEqual(member.full_name, "Jane Owacho Adega")
        self.assertEqual(self.client.session["verification_member_pk"], member.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("jane@example.com", mail.outbox[0].to)

    def test_code_is_stored_hashed_not_plain(self):
        self.client.post(reverse("membership:register"), register_payload())
        member = Member.objects.get(email="jane@example.com")
        code = VerificationCode.objects.filter(member=member).first()
        self.assertEqual(len(mail.outbox), 1)
        plaintext = [word for word in mail.outbox[0].subject.split() if word.isdigit()]
        self.assertTrue(plaintext, "the emailed subject should carry the code")
        self.assertNotIn(plaintext[0], code.code_hash)
        self.assertTrue(code.is_valid_for(plaintext[0]))

    def test_the_code_is_emailed_without_any_sms_provider(self):
        with override_settings(SMS_PROVIDER="console", AFRICASTALKING_API_KEY="", AFRICASTALKING_USERNAME=""):
            self.assertEqual(default_verification_channel(), "email")
            self.client.post(reverse("membership:register"), register_payload())
        member = Member.objects.get(email="jane@example.com")
        self.assertEqual(member.verification_channel, "email")
        self.assertIn("verification code", mail.outbox[0].body.lower())

    def test_sms_is_only_added_when_a_real_provider_is_configured(self):
        with override_settings(
            SMS_PROVIDER="africastalking", AFRICASTALKING_API_KEY="secret", AFRICASTALKING_USERNAME="kagan"
        ):
            self.assertEqual(default_verification_channel(), "both")

    def test_occupation_is_optional_but_gender_and_role_are_not(self):
        payload = register_payload(gender="", role="")
        response = self.client.post(reverse("membership:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(email="jane@example.com").exists())
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_invented_role_is_rejected(self):
        payload = register_payload(role="Secret Society Leader")
        response = self.client.post(reverse("membership:register"), payload)
        self.assertIn("role", response.context["form"].errors)

    def test_bad_phone_is_rejected(self):
        payload = register_payload(phone="0712 345")
        response = self.client.post(reverse("membership:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("phone", response.context["form"].errors)

    def test_landline_or_foreign_number_is_rejected(self):
        response = self.client.post(reverse("membership:register"), register_payload(phone="+1 202 555 0100"))
        self.assertIn("phone", response.context["form"].errors)

    def test_weak_password_is_rejected(self):
        response = self.client.post(reverse("membership:register"), register_payload(password1="password", password2="password"))
        self.assertIn("password1", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_passwords_must_match(self):
        response = self.client.post(reverse("membership:register"), register_payload(password2="Different#2026"))
        self.assertIn("do not match", response.context["form"].errors["password2"][0])

    def test_a_taken_email_is_rejected(self):
        User.objects.create_user(email="jane@example.com", name="Someone Else", password="Strong#Pass1")
        response = self.client.post(reverse("membership:register"), register_payload(phone="0722 000 111"))
        self.assertIn("already registered", response.context["form"].errors["email"][0])

    def test_a_second_registration_reuses_the_pending_row(self):
        self.client.post(reverse("membership:register"), register_payload())
        self.client.post(reverse("membership:register"), register_payload(location="Kagan Town"))
        self.assertEqual(Member.objects.filter(email="jane@example.com").count(), 1)
        self.assertEqual(User.objects.filter(email="jane@example.com").count(), 1)
        self.assertEqual(Member.objects.get(email="jane@example.com").location, "Kagan Town")

    def test_existing_verified_email_cannot_register_again(self):
        Member.objects.create(**{
            "full_name": "Already Member", "phone": "+254712345678", "email": "jane@example.com",
            "gender": "Female", "role": "Elder", "location": "Kagan", "verified": True,
            "status": Member.Status.ACTIVE, "membership_no": "KOC-0009",
        })
        response = self.client.post(reverse("membership:register"), register_payload(phone="0722 000 111"))
        self.assertIn("email", response.context["form"].errors)

    def test_a_photo_uploads_with_the_rest_of_the_form(self):
        from apps.core.testing import png_upload

        response = self.client.post(
            reverse("membership:register"), register_payload(photo=png_upload(name="face.png", size=(1200, 900)))
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(email="jane@example.com").photo)

    def test_a_non_image_is_rejected(self):
        upload = SimpleUploadedFile("note.txt", b"not a picture", content_type="text/plain")
        response = self.client.post(reverse("membership:register"), register_payload(photo=upload))
        self.assertIn("photo", response.context["form"].errors)

    def test_the_old_account_only_page_points_at_the_combined_form(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertRedirects(response, reverse("membership:register"), fetch_redirect_response=False)

    def test_a_broken_mail_server_never_loses_the_registration(self):
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")):
            response = self.client.post(reverse("membership:register"), register_payload(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Member.objects.filter(email="jane@example.com").exists())
        self.assertIn("could not be sent", self._notes(response))


class VerificationCodeTests(TestCase):
    def setUp(self):
        seed_dropdown_options()
        self.client.post(reverse("membership:register"), register_payload())
        self.member = Member.objects.get(email="jane@example.com")

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])

    def test_correct_code_activates_membership_and_numbers_it(self):
        _code, plaintext, _report = services.issue_code(self.member)
        before = len(mail.outbox)
        response = self.client.post(reverse("membership:verify"), {"code": plaintext})
        self.assertRedirects(response, reverse("membership:dashboard"))
        self.member.refresh_from_db()
        self.assertTrue(self.member.verified)
        self.assertEqual(self.member.status, Member.Status.ACTIVE)
        self.assertEqual(self.member.membership_no, "KOC-0001")
        self.assertIsNotNone(self.member.user)
        self.assertTrue(self.member.user.is_active, "verifying the code opens the account")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), before + 1, "a confirmation email follows the code")

    def test_membership_numbers_keep_counting(self):
        second = Member.objects.create(
            full_name="Second Person", phone="+254722000111", email="second@example.com",
            gender="Male", role="Elder", location="Kagan",
        )
        first_code = services.issue_code(self.member)[1]
        self.client.post(reverse("membership:verify"), {"code": first_code})
        self.member.refresh_from_db()
        second.refresh_from_db()
        second.confirm_membership()
        self.assertEqual(self.member.membership_no, "KOC-0001")
        self.assertEqual(second.membership_no, "KOC-0002")

    def test_wrong_code_counts_down_and_blocks_after_the_limit(self):
        services.issue_code(self.member)
        for _ in range(settings.VERIFICATION_MAX_ATTEMPTS):
            response = self.client.post(reverse("membership:verify"), {"code": "000000"})
            self.assertEqual(response.status_code, 200)
        code = services.current_code(self.member)
        self.assertEqual(code.attempts, settings.VERIFICATION_MAX_ATTEMPTS)
        self.assertTrue(code.out_of_attempts)

    def test_the_real_code_is_refused_once_attempts_are_used_up(self):
        _code, plaintext, _report = services.issue_code(self.member)
        for _ in range(settings.VERIFICATION_MAX_ATTEMPTS):
            self.client.post(reverse("membership:verify"), {"code": "111111"})
        response = self.client.post(reverse("membership:verify"), {"code": plaintext})
        self.member.refresh_from_db()
        self.assertFalse(self.member.verified)
        self.assertIn("Too many wrong tries", self._notes(response))

    def test_code_expires_after_the_configured_minutes(self):
        code, plaintext = services.issue_code(self.member)[:2]
        ttl = code.expires_at - code.created_at
        self.assertGreater(ttl, timedelta(minutes=settings.VERIFICATION_TTL_MINUTES - 1))
        VerificationCode.objects.filter(pk=code.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post(reverse("membership:verify"), {"code": plaintext})
        self.assertIn("expired", self._notes(response).lower())

    def test_a_new_code_retires_the_previous_one(self):
        old_code, _old, _report = services.issue_code(self.member)
        new_code, _new, _report = services.issue_code(self.member)
        old_code.refresh_from_db()
        self.assertTrue(old_code.expired)
        self.assertFalse(new_code.expired)

    def test_resend_is_throttled_then_allowed(self):
        first = self.client.post(reverse("membership:verify"), {"resend": "1"})
        self.assertEqual(first.status_code, 302)
        self.member.refresh_from_db()
        allowed, seconds = self.member.can_resend_code
        self.assertFalse(allowed)
        self.assertGreater(seconds, 0)
        Member.objects.filter(pk=self.member.pk).update(
            last_code_sent_at=timezone.now() - timedelta(seconds=settings.VERIFICATION_RESEND_COOLDOWN_SECONDS + 1)
        )
        self.member.refresh_from_db()
        response = self.client.post(reverse("membership:verify"), {"resend": "1"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        allowed, _seconds = self.member.can_resend_code
        self.assertFalse(allowed)

    def test_resending_sends_another_email(self):
        Member.objects.filter(pk=self.member.pk).update(
            last_code_sent_at=timezone.now() - timedelta(seconds=settings.VERIFICATION_RESEND_COOLDOWN_SECONDS + 1)
        )
        before = len(mail.outbox)
        self.client.post(reverse("membership:verify"), {"resend": "1"})
        self.assertEqual(len(mail.outbox), before + 1)

    def test_five_digit_code_is_not_even_tried(self):
        services.issue_code(self.member)
        response = self.client.post(reverse("membership:verify"), {"code": "12345"})
        self.assertIn("code", response.context["form"].errors)

    def test_verify_without_a_session_goes_back_to_the_form(self):
        self.client.get(reverse("membership:register"))
        session = self.client.session
        session.pop("verification_member_pk", None)
        session.save()
        response = self.client.get(reverse("membership:verify"))
        self.assertRedirects(response, reverse("membership:register"))


class CompleteMembershipTests(TestCase):
    """Accounts that exist from before the merge are finished off after they log in."""

    def setUp(self):
        seed_dropdown_options()
        self.user = User.objects.create_user(
            email="old@example.com", name="Old Member", password="Member#2026", phone="+254712345678"
        )
        self.client.force_login(self.user)

    def test_an_account_without_a_membership_cannot_reach_the_dashboard(self):
        response = self.client.get(reverse("membership:dashboard"))
        self.assertRedirects(response, reverse("membership:pending"), fetch_redirect_response=False)
        final = self.client.get(response.headers["Location"])
        self.assertRedirects(final, reverse("membership:complete"))

    def test_the_form_asks_for_the_member_details_only(self):
        response = self.client.get(reverse("membership:complete"))
        self.assertContains(response, "Complete your membership")
        self.assertNotContains(response, "Confirm password")

    def test_submitting_the_details_sends_a_code(self):
        response = self.client.post(reverse("membership:complete"), member_details_payload())
        self.assertRedirects(response, reverse("membership:verify"))
        member = Member.objects.get(user=self.user)
        self.assertFalse(member.verified)
        self.assertEqual(member.email, "old@example.com")
        self.assertEqual(member.full_name, "Old Member")
        self.assertEqual(len(mail.outbox), 1)

    def test_verifying_the_code_finishes_the_membership(self):
        self.client.post(reverse("membership:complete"), member_details_payload())
        member = Member.objects.get(user=self.user)
        response = self.client.post(reverse("membership:verify"), {"code": services.issue_code(member)[1]})
        self.assertRedirects(response, reverse("membership:dashboard"))
        member.refresh_from_db()
        self.assertEqual(member.membership_no, "KOC-0001")

    def test_a_confirmed_member_is_bounced_back_to_the_dashboard(self):
        member = make_member(email="other@example.com", phone="+254712345678")
        member.user = self.user
        member.save()
        response = self.client.get(reverse("membership:complete"))
        self.assertRedirects(response, reverse("membership:dashboard"))

    def test_admins_never_see_the_membership_form(self):
        self.client.force_login(make_admin())
        response = self.client.get(reverse("membership:complete"))
        self.assertRedirects(response, reverse("admin_panel:dashboard"))


class MemberAreaAccessTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def create_member(self, verified=True):
        return make_member(email="jane@example.com", phone="+254712345678", verified=verified)

    def test_anonymous_member_pages_redirect_to_login(self):
        response = self.client.get(reverse("membership:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_unverified_member_is_sent_to_the_pending_page(self):
        self.create_member(verified=False)
        self.client.force_login(User.objects.get(email="jane@example.com"))
        response = self.client.get(reverse("membership:dashboard"))
        self.assertRedirects(response, reverse("membership:pending"))

    def test_verified_member_sees_the_dashboard(self):
        self.create_member()
        self.client.force_login(User.objects.get(email="jane@example.com"))
        response = self.client.get(reverse("membership:dashboard"))
        self.assertContains(response, "KOC-0001")

    def test_admins_are_not_members(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("membership:dashboard"))
        self.assertRedirects(response, reverse("membership:pending"), fetch_redirect_response=False)
        final = self.client.get(reverse("membership:pending"))
        self.assertRedirects(final, reverse("admin_panel:dashboard"))


class LegacyAccountMigrationTests(TestCase):
    """The data migration must not lock anybody out of the site they already joined."""

    def run_backfill(self):
        legacy_migration.give_every_account_a_membership(global_apps, None)

    def test_a_half_finished_legacy_account_can_still_log_in(self):
        User.objects.create_user(email="stuck@example.com", name="Stuck", password="Member#2026", is_active=False)
        self.run_backfill()
        self.assertTrue(User.objects.get(email="stuck@example.com").is_active)

    def test_verified_members_are_linked_to_the_account_with_their_email(self):
        user = User.objects.create_user(email="linked@example.com", name="Linked", password="Member#2026")
        member = Member.objects.create(
            full_name="Linked", phone="+254712345678", email="linked@example.com",
            location="Kagan", verified=True, status=Member.Status.ACTIVE, membership_no="KOC-0001",
        )
        self.run_backfill()
        member.refresh_from_db()
        self.assertEqual(member.user, user)
        self.assertEqual(member.membership_no, "KOC-0001")

    def test_an_account_without_a_membership_is_given_a_pending_one(self):
        user = User.objects.create_user(email="plain@example.com", name="Plain", password="Member#2026")
        self.run_backfill()
        member = Member.objects.get(user=user)
        self.assertFalse(member.verified)
        self.assertEqual(member.email, "plain@example.com")
        self.assertEqual(member.status, Member.Status.PENDING)

    def test_a_member_row_created_by_the_migration_asks_the_person_to_fix_the_phone(self):
        user = User.objects.create_user(email="nophone@example.com", name="No Phone", password="Member#2026")
        self.run_backfill()
        member = Member.objects.get(user=user)
        form = CompleteMembershipForm({}, member=member)
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_an_existing_phone_is_carried_over(self):
        User.objects.create_user(
            email="phone@example.com", name="Phone", password="Member#2026", phone="+254722000111"
        )
        self.run_backfill()
        self.assertEqual(Member.objects.get(email="phone@example.com").phone, "+254722000111")

    def test_administrators_are_left_as_they_were(self):
        admin = make_admin()
        self.run_backfill()
        self.assertIsNone(admin.membership)
