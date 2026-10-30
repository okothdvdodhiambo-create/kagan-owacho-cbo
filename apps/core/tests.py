"""Tests for shared site content: settings singleton, uploads, home/about pages, bootstrap."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from apps.contributions.models import Contribution
from apps.core.context_processors import navigation, site_settings
from apps.core.models import AuditLog, NavItem, SiteSettings, SliderImage
from apps.core.testing import MediaRootMixin, make_member, png_upload
from apps.core.utils import kenyan_phone_to_254, validate_image_file
from apps.membership.models import DropdownOption, Member
from config import settings as project_settings


def request_for(path):
    return RequestFactory().get(path)


def image_upload(name="photo.jpg"):
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0jpeg-bytes", content_type="image/jpeg")


class SiteSettingsSingletonTests(TestCase):
    def setUp(self):
        SiteSettings.objects.all().delete()

    def test_load_creates_and_reuses_the_single_row(self):
        first = SiteSettings.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().organization_name, first.organization_name)

    def test_saving_a_second_instance_reuses_pk_one(self):
        SiteSettings.load()
        SiteSettings(organization_name="Second Name").save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().organization_name, "Second Name")

    def test_an_edit_is_visible_on_the_next_load(self):
        site = SiteSettings.load()
        site.motto = "A brand new motto"
        site.save()
        self.assertEqual(SiteSettings.load().motto, "A brand new motto")

    def test_whatsapp_links(self):
        cases = {
            "+254700111222": "https://wa.me/254700111222",
            "0700111222": "https://wa.me/254700111222",
            "254700111222": "https://wa.me/254700111222",
            "": "#",
        }
        for raw, expected in cases.items():
            self.assertEqual(SiteSettings(whatsapp_number=raw).whatsapp_url, expected, raw)

    def test_context_processor_exposes_the_site(self):
        SiteSettings.load()
        context = site_settings(request_for("/"))
        self.assertEqual(context["SITE"].pk, 1)
        self.assertEqual(context["ORG_NAME"], context["SITE"].organization_name)


class PhoneAndAuditHelperTests(TestCase):
    def test_kenyan_phone_normalisation(self):
        cases = {
            "0712345678": "+254712345678",
            "0112345678": "+254112345678",
            "+254 712 345 678": "+254712345678",
            "00254712345678": "+254712345678",
            "254712345678": "+254712345678",
            "0712345": None,
            "+12025550100": None,
            "": None,
            None: None,
        }
        for raw, expected in cases.items():
            self.assertEqual(kenyan_phone_to_254(raw), expected, raw)

    def test_audit_log_stores_the_client_ip_and_tolerates_no_actor(self):
        request = request_for("/admin-panel/")
        request.META["REMOTE_ADDR"] = "196.201.210.5"
        entry = AuditLog.record(None, "test.action", target="thing", details="note", request=request)
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.ip_address, "196.201.210.5")
        self.assertIsNone(AuditLog.record(None, "no.request").ip_address)

    def test_audit_log_prefers_the_forwarded_header(self):
        request = request_for("/admin-panel/")
        request.META["HTTP_X_FORWARDED_FOR"] = "200.1.2.3, 10.0.0.1"
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.assertEqual(AuditLog.record(None, "x", request=request).ip_address, "200.1.2.3")


class ImageValidationTests(TestCase):
    def test_allowed_images_pass(self):
        validate_image_file(png_upload("a.png"))
        validate_image_file(image_upload("b.jpg"))

    def test_disallowed_extension_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            validate_image_file(SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet"))
        self.assertIn("allowed", str(caught.exception))

    def test_file_that_is_not_an_image_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            validate_image_file(SimpleUploadedFile("fake.jpg", b"just text", content_type="image/jpeg"))
        self.assertIn("valid image", str(caught.exception).lower())

    def test_oversized_file_is_rejected(self):
        with override_settings(MAX_UPLOAD_SIZE_MB=0):
            with self.assertRaises(ValidationError):
                validate_image_file(png_upload("big.png"))


class HomePageTests(MediaRootMixin, TestCase):
    def add_slides(self, captions):
        for order, caption in enumerate(captions, start=1):
            slide = SliderImage.objects.create(caption=caption, order=order)
            slide.image.save(f"slide-{order}.png", png_upload(f"slide-{order}.png"), save=True)

    def test_home_shows_slider_captions_and_arrows(self):
        self.add_slides(["Paying school fees", "Youth events", "Thank you lunch"])
        SliderImage.objects.create(caption="Hidden slide", order=99, active=False)

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Paying school fees")
        self.assertContains(response, "Thank you lunch")
        self.assertNotContains(response, "Hidden slide")
        self.assertIn("koco-slider-dots", response.content.decode())

    def test_home_follows_the_site_settings_text(self):
        site = SiteSettings.load()
        site.motto = "Utu na elimu kwa Kagan."
        site.save()
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["SITE"].motto, "Utu na elimu kwa Kagan.")
        self.assertContains(response, "Utu na elimu kwa Kagan.")

    def test_home_without_photos_shows_the_placeholder_note(self):
        self.assertContains(self.client.get(reverse("core:home")), "No slider photos yet.")

    def test_home_counts_active_members_and_confirmed_money(self):
        member = make_member("active@example.org", "+254712345000", "Active#2026")
        suspended = make_member("gone@example.org", "+254712345001", "Active#2026")
        Member.objects.filter(pk=suspended.pk).update(status=Member.Status.SUSPENDED)
        for amount, status in (("1500.00", Contribution.Status.CONFIRMED), ("900.00", Contribution.Status.PENDING)):
            Contribution.objects.create(
                member=member,
                amount=Decimal(amount),
                method=Contribution.Method.BANK,
                reference=f"BANK-{status}",
                status=status,
            )
        stats = self.client.get(reverse("core:home")).context["stats"]
        self.assertEqual(stats["members"], 1)
        self.assertEqual(stats["contributions_ksh"], 1500.0)

    def test_navigation_highlights_the_current_page(self):
        NavItem.objects.all().delete()
        NavItem.objects.create(title="Home", url="/", order=1)
        NavItem.objects.create(title="Events Sponsored", url="/events/", order=2)
        NavItem.objects.create(title="InvisibleButton", url="/nope/", order=3, visible=False)

        items = navigation(request_for("/events/"))["NAV_ITEMS"]
        self.assertEqual([row["item"].title for row in items], ["Home", "Events Sponsored"])
        self.assertTrue(items[1]["active"])
        self.assertFalse(items[0]["active"])

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Events Sponsored")
        self.assertNotContains(response, "InvisibleButton")


class AboutPageTests(TestCase):
    def test_about_renders_the_admin_text(self):
        site = SiteSettings.load()
        site.about_mission = "To keep every child in class."
        site.about_vision = "A Kagan where nobody drops out."
        site.save()
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, "To keep every child in class.")
        self.assertContains(response, "A Kagan where nobody drops out.")


class BootstrapCommandTests(MediaRootMixin, TestCase):
    def setUp(self):
        self.enable_temp_media()

    def test_creates_both_admins_nav_and_options(self):
        from apps.accounts.models import User

        call_command("bootstrap_site", "--skip-demo")
        for email, _password in project_settings.ADMIN_ACCOUNTS:
            user = User.objects.get(email__iexact=email)
            self.assertTrue(user.is_admin and user.is_staff)
            self.assertTrue(user.has_usable_password())
        self.assertTrue(NavItem.objects.filter(url="/events/calendar/").exists())
        self.assertTrue(DropdownOption.objects.filter(field=DropdownOption.Field.GENDER).exists())
        self.assertEqual(SliderImage.objects.count(), 0)

    def test_is_idempotent(self):
        call_command("bootstrap_site", "--skip-demo")
        before = (NavItem.objects.count(), DropdownOption.objects.count())
        call_command("bootstrap_site", "--skip-demo")
        self.assertEqual((NavItem.objects.count(), DropdownOption.objects.count()), before)

    def test_demo_content_is_created_once(self):
        from apps.events.models import Event, EventReport

        call_command("bootstrap_site")
        self.assertEqual(SliderImage.objects.count(), 3)
        self.assertEqual(SliderImage.objects.exclude(image="").count(), 3)
        self.assertGreaterEqual(Event.objects.count(), 3)
        self.assertTrue(EventReport.objects.exists())
        call_command("bootstrap_site")
        self.assertEqual(SliderImage.objects.count(), 3)
        self.assertEqual(Event.objects.count(), 3)
