"""Admin dashboard tests - most importantly, that nobody else can get in."""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.contributions.models import Contribution
from apps.core.models import AuditLog, NavItem
from apps.core.testing import make_admin, make_member, seed_dropdown_options
from apps.incidents.models import Incident, IncidentResponse
from apps.membership.models import DropdownOption, Member

ADMIN_PAGES = [
    "admin_panel:dashboard",
    "admin_panel:member_list",
    "admin_panel:campaign_list",
    "admin_panel:event_list",
    "admin_panel:report_list",
    "admin_panel:contribution_list",
    "admin_panel:incident_list",
    "admin_panel:settings_home",
    "admin_panel:settings_site",
    "admin_panel:audit_list",
]


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.member_user = make_member().user
        self.admin = make_admin()

    def test_anonymous_users_are_pushed_to_login(self):
        for name in ADMIN_PAGES:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response.headers["Location"], name)

    def test_logged_in_members_are_refused(self):
        self.client.force_login(self.member_user)
        for name in ADMIN_PAGES:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403, name)

    def test_a_staff_account_without_the_admin_flag_is_refused(self):
        helper = User.objects.create_user(email="helper@example.com", name="Helper", password="Helper#2026", is_staff=True)
        self.client.force_login(helper)
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 403)

    def test_admin_gets_in(self):
        self.client.force_login(self.admin)
        for name in ADMIN_PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_superuser_without_the_flag_still_gets_in(self):
        boss = User.objects.create_superuser(email="boss@example.com", password="Boss#2026", name="Boss")
        boss.is_admin = False
        boss.save(update_fields=["is_admin"])
        self.client.force_login(boss)
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 200)


class AdminListTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        seed_dropdown_options()
        self.rows = []
        for index, (name, phone) in enumerate(
            [("Jane Owacho", "+254712345001"), ("Peter Otieno", "+254712345002"), ("Mary Achieng", "+254712345003")],
            start=1,
        ):
            member = Member.objects.create(
                full_name=name, phone=phone, email=f"member{index}@example.com", gender="Female",
                role="Youth Member", location="Kagan Ward", sub_location="Rangwe", occupation="Farmer",
            )
            member.confirm_membership()
            self.rows.append(member)

    def test_search_filters_by_name(self):
        response = self.client.get(reverse("admin_panel:member_list"), {"q": "otieno"})
        self.assertEqual([m.full_name for m in response.context["members"]], ["Peter Otieno"])

    def test_status_filter_and_export(self):
        self.rows[0].status = Member.Status.SUSPENDED
        self.rows[0].save(update_fields=["status"])
        response = self.client.get(reverse("admin_panel:member_list"), {"status": Member.Status.SUSPENDED})
        self.assertEqual(response.context["members"].paginator.count, 1)
        csv_response = self.client.get(reverse("admin_panel:member_list"), {"export": "csv"})
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        body = csv_response.content.decode()
        self.assertIn("Membership no", body)
        self.assertIn("KOC-0001", body)
        xlsx = self.client.get(reverse("admin_panel:member_list"), {"export": "xlsx"})
        self.assertIn("spreadsheetml", xlsx["Content-Type"])

    def test_pagination_keeps_other_query_parameters(self):
        for index in range(4, 30):
            member = Member.objects.create(
                full_name=f"Extra Person {index}", phone=f"+2547123450{index:02d}",
                email=f"extra{index}@example.com", gender="Male", role="Elder", location="Kagan",
            )
            member.confirm_membership()
        response = self.client.get(reverse("admin_panel:member_list"), {"q": "Person", "page": 2})
        self.assertEqual(response.context["members"].number, 2)
        self.assertIn("q=Person", response.content.decode())

    def test_suspending_and_reactivating_a_member(self):
        member = self.rows[0]
        self.client.post(reverse("admin_panel:member_detail", kwargs={"pk": member.pk}), {"action": "suspend"})
        member.refresh_from_db()
        self.assertEqual(member.status, Member.Status.SUSPENDED)
        self.client.post(reverse("admin_panel:member_detail", kwargs={"pk": member.pk}), {"action": "activate"})
        member.refresh_from_db()
        self.assertEqual(member.status, Member.Status.ACTIVE)
        self.assertTrue(member.verified)

    def test_deleting_needs_the_confirmation_box(self):
        member = self.rows[-1]
        response = self.client.post(
            reverse("admin_panel:member_detail", kwargs={"pk": member.pk}), {"action": "delete"}, follow=True
        )
        self.assertIn("confirmation box", self._notes(response))
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())
        self.client.post(
            reverse("admin_panel:member_detail", kwargs={"pk": member.pk}), {"action": "delete", "confirm": "yes"}
        )
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="member.deleted").exists())

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])


class AdminMoneyAndIncidentTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        self.member = make_member()
        self.contribution = Contribution.objects.create(
            member=self.member, amount="900.00", method=Contribution.Method.BANK, reference="SLIP-77"
        )
        self.incident = Incident.objects.create(
            member=self.member, title="Books never arrived", description="The bursary books did not reach Kagan Primary.",
            occurred_on="2026-10-20",
        )

    def test_contribution_filters_and_total(self):
        response = self.client.get(reverse("admin_panel:contribution_list"), {"status": "pending"})
        self.assertEqual(response.context["contributions"].paginator.count, 1)
        self.assertEqual(response.context["filtered_total"], 900.0)

    def test_confirming_from_the_dashboard_writes_the_audit_log(self):
        response = self.client.post(
            reverse("admin_panel:contribution_decide", kwargs={"pk": self.contribution.pk}),
            {"decision": "confirmed", "reference": "SLIP-77", "reason": ""},
            follow=True,
        )
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, Contribution.Status.CONFIRMED)
        self.assertEqual(self.contribution.verified_by, self.admin)
        self.assertIn("contribution.confirmed", AuditLog.objects.values_list("action", flat=True))
        self.assertEqual(len(mail.outbox), 1)

    def test_rejecting_needs_the_member_to_be_told(self):
        self.client.post(
            reverse("admin_panel:contribution_decide", kwargs={"pk": self.contribution.pk}),
            {"decision": "rejected", "reference": "", "reason": "No such deposit at the bank"},
        )
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, Contribution.Status.REJECTED)

    def test_replying_to_an_incident_notifies_the_member(self):
        self.client.post(
            reverse("admin_panel:incident_detail", kwargs={"pk": self.incident.pk}),
            {"form": "reply", "body": "The committee will check with the supplier.", "notify_member": "on"},
        )
        reply = IncidentResponse.objects.get(incident=self.incident)
        self.assertEqual(reply.author, self.admin)
        self.assertEqual(len(mail.outbox), 1)

    def test_changing_incident_status(self):
        self.client.post(
            reverse("admin_panel:incident_detail", kwargs={"pk": self.incident.pk}),
            {"form": "status", "status": Incident.Status.RESOLVED, "handling_admin": self.admin.pk},
        )
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.RESOLVED)
        self.assertEqual(self.incident.handling_admin, self.admin)

    def test_audit_search(self):
        AuditLog.record(self.admin, "event.saved", target="Bursary day", request=None)
        response = self.client.get(reverse("admin_panel:audit_list"), {"q": "bursary"})
        self.assertEqual(response.context["entries"].paginator.count, 1)


class AdminSettingsTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_navigation_button_can_be_renamed_and_reordered(self):
        item = NavItem.objects.create(title="Events Sponsored", url="/events/", order=30)
        self.client.post(
            reverse("admin_panel:settings_nav") + f"?edit={item.pk}",
            {"title": "Sponsored Events", "url": "/events/", "order": 5, "visible": "on"},
            follow=True,
        )
        item.refresh_from_db()
        self.assertEqual(item.title, "Sponsored Events")
        self.assertEqual(item.order, 5)
        self.assertFalse(NavItem.objects.filter(title="Events Sponsored").exists())
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Sponsored Events")
        self.client.post(reverse("admin_panel:nav_delete", kwargs={"pk": item.pk}), follow=True)
        self.assertFalse(NavItem.objects.filter(pk=item.pk).exists())

    def test_dropdown_option_appears_on_the_registration_form(self):
        self.client.post(
            reverse("admin_panel:settings_options"),
            {"field": "role", "label": "Bursary Committee", "order": 5, "active": "on"},
        )
        response = self.client.get(reverse("membership:register"))
        self.assertContains(response, "Bursary Committee")

    def test_site_settings_are_saved_and_shown_in_the_header(self):
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        data = {
            "organization_name": "KAGAN OWACHO CBO", "motto": "Education first",
            "home_heading": site.home_heading, "home_subheading": site.home_subheading,
            "home_body": site.home_body, "home_call_to_action": site.home_call_to_action,
            "home_statistics_note": site.home_statistics_note, "about_mission": site.about_mission,
            "about_vision": site.about_vision, "about_history": site.about_history,
            "about_leadership": site.about_leadership, "footer_note": site.footer_note,
            "whatsapp_number": "+254700111222", "contact_email": site.contact_email,
            "postal_address": site.postal_address, "location_label": site.location_label,
            "map_embed_url": "", "bank_name": "Equity Bank", "bank_account_name": "Kagan Owacho CBO",
            "bank_account_number": "0123456789", "bank_branch": "Rangwe", "bank_notes": site.bank_notes,
            "mpesa_paybill": "400200", "mpesa_account_number": "KAGAN",
        }
        response = self.client.post(reverse("admin_panel:settings_site"), data, follow=True)
        self.assertIn("Site settings saved.", self._notes(response))
        site = SiteSettings.load()
        self.assertEqual(site.motto, "Education first")
        self.assertEqual(site.bank_name, "Equity Bank")
        self.assertContains(self.client.get(reverse("core:home")), "Education first")

    def _notes(self, response):
        return " ".join(str(message) for message in response.context["messages"])

    def test_announcement_emails_every_verified_member(self):
        make_member(email="one@example.com", phone="+254712345101")
        make_member(email="two@example.com", phone="+254712345102")
        Member.objects.create(full_name="Pending Person", phone="+254712345103", email="three@example.com",
                              location="Kagan")
        self.client.post(
            reverse("admin_panel:campaign_create"),
            {"subject": "Annual meeting", "message": "Come to Kagan Hall on the 20th.", "audience": "all"},
            follow=True,
        )
        self.assertEqual(len(mail.outbox), 2)


class AdminEventTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def _event_payload(self, **overrides):
        data = {
            "title": "Bursary handover", "category": "school_fees", "starts_at": "2026-11-14T09:00",
            "ends_at": "2026-11-14T12:00", "venue": "Kagan Primary Hall", "description": "Cheques for 40 students.",
            "published": "on",
        }
        data.update(overrides)
        return data

    def test_creating_an_event_shows_it_publicly(self):
        self.client.post(reverse("admin_panel:event_new"), self._event_payload(), follow=True)
        from apps.events.models import Event

        event = Event.objects.get(title="Bursary handover")
        self.assertTrue(event.published)
        self.assertContains(self.client.get(reverse("events:list")), "Bursary handover")
        self.assertContains(self.client.get(reverse("events:detail", kwargs={"pk": event.pk})), "Kagan Primary Hall")

    def test_event_end_before_start_is_rejected(self):
        response = self.client.post(
            reverse("admin_panel:event_new"),
            self._event_payload(ends_at="2026-11-14T08:00"),
        )
        self.assertIn("ends_at", response.context["form"].errors)

    def test_unpublished_event_stays_out_of_the_public_calendar(self):
        self.client.post(reverse("admin_panel:event_new"), self._event_payload(published=""), follow=True)
        response = self.client.get(reverse("events:feed"))
        self.assertNotContains(response, "Bursary handover")

    def test_deleting_an_event_needs_confirmation(self):
        from apps.events.models import Event

        self.client.post(reverse("admin_panel:event_new"), self._event_payload(), follow=True)
        event = Event.objects.get(title="Bursary handover")
        self.client.post(reverse("admin_panel:event_delete", kwargs={"pk": event.pk}), {"confirm": "no"}, follow=True)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())
        self.client.post(reverse("admin_panel:event_delete", kwargs={"pk": event.pk}), {"confirm": "yes"}, follow=True)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())
