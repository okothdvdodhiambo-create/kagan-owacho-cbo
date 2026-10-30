"""Membership registration and the 6-digit verification code rules."""

from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.testing import make_admin, make_member, register_payload, seed_dropdown_options
from apps.membership import services
from apps.membership.models import DropdownOption, Member, VerificationCode


class RegistrationViewTests(TestCase):
    def setUp(self):
        seed_dropdown_options()

    def test_form_shows_only_active_options(self):
        DropdownOption.objects.create(field="role", label="Retired Role", active=False)
        response = self.client.get(reverse("membership:register"))
        self.assertContains(response, "Youth Member")
        self.assertNotContains(response, "Retired Role")

    def test_registering_creates_a_pending_membership_and_sends_a_code(self):
        response = self.client.post(reverse("membership:register"), register_payload())
        self.assertRedirects(response, reverse("membership:verify"))
        member = Member.objects.get(email="jane@example.com")
        self.assertFalse(member.verified)
        self.assertEqual(member.status, Member.Status.PENDING)
        self.assertEqual(member.phone, "+254712345678")
        self.assertEqual(self.client.session["verification_member_pk"], member.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_code_is_stored_hashed_not_plain(self):
        self.client.post(reverse("membership:register"), register_payload())
        member = Member.objects.get(email="jane@example.com")
        code = VerificationCode.objects.filter(member=member).first()
        self.assertEqual(len(mail.outbox), 1)
        plaintext = [word for word in mail.outbox[0].subject.split() if word.isdigit()]
        self.assertTrue(plaintext, "the emailed subject should carry the code")
        self.assertNotIn(plaintext[0], code.code_hash)
        self.assertTrue(code.is_valid_for(plaintext[0]))

    def test_occupation_is_optional_but_gender_and_role_are_not(self):
        payload = register_payload(gender="", role="")
        response = self.client.post(reverse("membership:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(email="jane@example.com").exists())

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

    def test_a_second_registration_reuses_the_pending_row(self):
        self.client.post(reverse("membership:register"), register_payload())
        self.client.post(reverse("membership:register"), register_payload(location="Kagan Town"))
        self.assertEqual(Member.objects.filter(email="jane@example.com").count(), 1)

    def test_existing_verified_email_cannot_register_again(self):
        Member.objects.create(**{
            "full_name": "Already Member", "phone": "+254712345678", "email": "jane@example.com",
            "gender": "Female", "role": "Elder", "location": "Kagan", "verified": True,
            "status": Member.Status.ACTIVE, "membership_no": "KOC-0009",
        })
        response = self.client.post(reverse("membership:register"), register_payload(phone="0722 000 111"))
        self.assertIn("email", response.context["form"].errors)


class VerificationCodeTests(TestCase):
    def setUp(self):
        seed_dropdown_options()
        self.client.post(reverse("membership:register"), register_payload())
        self.member = Member.objects.get(email="jane@example.com")

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])

    def test_correct_code_activates_membership_and_numbers_it(self):
        _code, plaintext, _report = services.issue_code(self.member)
        response = self.client.post(reverse("membership:verify"), {"code": plaintext})
        self.assertRedirects(response, reverse("membership:dashboard"))
        self.member.refresh_from_db()
        self.assertTrue(self.member.verified)
        self.assertEqual(self.member.status, Member.Status.ACTIVE)
        self.assertEqual(self.member.membership_no, "KOC-0001")
        self.assertIsNotNone(self.member.user)
        self.assertIn("_auth_user_id", self.client.session)

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
        self.assertRedirects(final, reverse("membership:register"))
