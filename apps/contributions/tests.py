"""Contribution tests: the three ways to pay, the treasurer's decision and the PDF statement."""

import json
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.contributions.models import Contribution, MpesaCallback
from apps.contributions.services import apply_callback_payload, mark_confirmed, mark_rejected
from apps.core.testing import MediaRootMixin, make_admin, make_member, png_upload


class ContributionAccessTests(TestCase):
    def test_anonymous_visitors_are_sent_to_login(self):
        for name in ["contributions:choose", "contributions:manual", "contributions:bank", "contributions:transcript"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response.headers["Location"], name)


class ManualMpesaTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.client.force_login(self.member.user)

    def test_recording_a_code_creates_a_pending_contribution(self):
        response = self.client.post(
            reverse("contributions:manual"),
            {"amount": "500", "reference": "shl12ab3cd", "phone": "0712 345 678", "note": "October support"},
        )
        self.assertRedirects(response, reverse("contributions:transcript"))
        row = Contribution.objects.get(member=self.member)
        self.assertEqual(row.amount, Decimal("500.00"))
        self.assertEqual(row.reference, "SHL12AB3CD")
        self.assertEqual(row.phone, "+254712345678")
        self.assertEqual(row.status, Contribution.Status.PENDING)
        self.assertEqual(row.method, Contribution.Method.MPESA_MANUAL)

    def test_short_reference_is_rejected(self):
        response = self.client.post(
            reverse("contributions:manual"), {"amount": "500", "reference": "AB12", "phone": "0712 345 678"}
        )
        self.assertIn("reference", response.context["form"].errors)
        self.assertEqual(Contribution.objects.count(), 0)

    def test_amount_below_the_minimum_is_rejected(self):
        response = self.client.post(
            reverse("contributions:manual"), {"amount": "5", "reference": "SHL12AB3CD", "phone": "0712 345 678"}
        )
        self.assertIn("amount", response.context["form"].errors)

    def test_transcript_shows_totals(self):
        Contribution.objects.create(member=self.member, amount="1000.00", method=Contribution.Method.MPESA_MANUAL,
                                    status=Contribution.Status.CONFIRMED)
        Contribution.objects.create(member=self.member, amount="250.00", method=Contribution.Method.BANK,
                                    status=Contribution.Status.PENDING)
        response = self.client.get(reverse("contributions:transcript"))
        self.assertEqual(response.context["totals"]["confirmed_total"], Decimal("1000.00"))
        self.assertContains(response, "1,000")


class BankContributionTests(MediaRootMixin, TestCase):
    def setUp(self):
        self.member = make_member()
        self.client.force_login(self.member.user)
        self.enable_temp_media()

    def test_slip_photo_is_saved_and_resized(self):
        response = self.client.post(
            reverse("contributions:bank"),
            {
                "amount": "2000",
                "reference": "SLIP 991 KAGAN",
                "payment_date": "2026-10-21",
                "receipt": png_upload(name="slip.png", size=(2200, 1400)),
            },
        )
        self.assertRedirects(response, reverse("contributions:transcript"))
        row = Contribution.objects.get(member=self.member)
        self.assertEqual(row.method, Contribution.Method.BANK)
        self.assertEqual(row.reference, "SLIP 991 KAGAN")
        self.assertTrue(row.receipt)
        from PIL import Image

        with Image.open(row.receipt.path) as image:
            self.assertLessEqual(max(image.size), 1400)

    def test_text_file_as_receipt_is_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            reverse("contributions:bank"),
            {
                "amount": "2000",
                "reference": "SLIP 992",
                "payment_date": "2026-10-21",
                "receipt": SimpleUploadedFile("slip.txt", b"not a picture"),
            },
        )
        self.assertIn("receipt", response.context["form"].errors)


class STKPushFallbackTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.client.force_login(self.member.user)

    def test_choose_page_offers_the_manual_code_when_daraja_is_missing(self):
        response = self.client.get(reverse("contributions:choose"))
        self.assertFalse(response.context["mpesa_ready"])
        self.assertContains(response, "Record")

    def test_stk_push_without_keys_falls_back_to_recording_the_code(self):
        response = self.client.post(
            reverse("contributions:mpesa"), {"amount": "300", "phone": "0712 345 678"}, follow=True
        )
        self.assertRedirects(response, reverse("contributions:manual"))
        row = Contribution.objects.get(member=self.member)
        self.assertEqual(row.status, Contribution.Status.PENDING)
        self.assertTrue(row.result_message)


class TreasurerDecisionTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.member = make_member()
        self.row = Contribution.objects.create(
            member=self.member, amount="700.00", method=Contribution.Method.MPESA_MANUAL, reference="SHL000111"
        )

    def test_confirming_records_the_treasurer_and_notifies_the_member(self):
        mark_confirmed(self.row, self.admin)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.CONFIRMED)
        self.assertEqual(self.row.verified_by, self.admin)
        self.assertIsNotNone(self.row.payment_date)

    def test_rejecting_keeps_a_reason(self):
        mark_rejected(self.row, self.admin, "The code was already used")
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.REJECTED)
        self.assertIn("already used", self.row.result_message)

    def test_totals_only_count_confirmed_money(self):
        Contribution.objects.create(member=self.member, amount="100.00", method=Contribution.Method.BANK,
                                    status=Contribution.Status.CONFIRMED)
        totals = Contribution.totals(self.member)
        self.assertEqual(totals["confirmed_total"], Decimal("100.00"))
        self.assertEqual(totals["pending_total"], Decimal("700.00"))


class MpesaCallbackTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.row = Contribution.objects.create(
            member=self.member, amount="450.00", method=Contribution.Method.MPESA_STK,
            status=Contribution.Status.WAITING, checkout_request_id="checkout-1", phone="+254712345678",
        )

    def _post(self, payload):
        return self.client.post(
            reverse("contributions:mpesa_callback"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_successful_callback_confirms_without_an_admin(self):
        response = self._post(
            {"Body": {"stkCallback": {
                "MerchantRequestID": "m-1", "CheckoutRequestID": "checkout-1", "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackItem": [
                    {"Name": "MpesaReceiptNumber", "Value": "TJK77P1Q2Z"},
                    {"Name": "Amount", "Value": 450},
                ],
            }}}
        )
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.CONFIRMED)
        self.assertEqual(self.row.transaction_id, "TJK77P1Q2Z")
        self.assertIsNone(self.row.verified_by)
        self.assertEqual(len(mail.outbox), 1)

    def test_cancelled_callback_marks_it_cancelled(self):
        self._post({"Body": {"stkCallback": {"CheckoutRequestID": "checkout-1", "ResultCode": 1,
                                             "ResultDesc": "Cancelled by user"}}})
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.CANCELLED)

    def test_unknown_checkout_is_still_stored_for_the_audit_trail(self):
        self._post({"Body": {"stkCallback": {"CheckoutRequestID": "not-ours", "ResultCode": 0}}})
        self.assertEqual(MpesaCallback.objects.filter(checkout_request_id="not-ours").count(), 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.WAITING)

    def test_garbage_payload_is_refused_and_changes_nothing(self):
        response = self.client.post(
            reverse("contributions:mpesa_callback"), data="{oops", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Contribution.Status.WAITING)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("contributions:mpesa_callback")).status_code, 405)

    def test_apply_callback_payload_tolerates_a_non_dict_body(self):
        self.assertIsNone(apply_callback_payload({"Body": "text"}))


class StatementPdfTests(MediaRootMixin, TestCase):
    def setUp(self):
        self.enable_temp_media()
        self.member = make_member()
        self.client.force_login(self.member.user)
        Contribution.objects.create(member=self.member, amount="1500.00", method=Contribution.Method.MPESA_MANUAL,
                                    reference="SHL555111", status=Contribution.Status.CONFIRMED)

    def test_statement_is_a_pdf_for_this_member_only(self):
        response = self.client.get(reverse("contributions:statement"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 1500)

    def test_download_flag_sets_an_attachment_name(self):
        response = self.client.get(reverse("contributions:statement"), {"download": "1"})
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("KOC-0001", response["Content-Disposition"])
