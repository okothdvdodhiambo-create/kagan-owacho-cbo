"""Tests for the public events pages and the calendar JSON feed."""

from datetime import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventReport


def eat(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute))


class EventFeedTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title="School fees support day",
            starts_at=eat(2026, 10, 29),
            ends_at=eat(2026, 10, 29, 13),
            venue="Kagan Primary School",
            description="We cleared term fees for 42 students.",
            published=True,
        )
        Event.objects.create(title="Hidden practice", starts_at=eat(2026, 11, 5), venue="Hall", published=False)

    def test_feed_is_a_bare_json_array_for_fullcalendar(self):
        payload = self.client.get(reverse("events:feed")).json()
        self.assertIsInstance(payload, list, "FullCalendar only renders a plain array, not an object wrapper")
        row = next(item for item in payload if item["title"] == "School fees support day")
        self.assertEqual(row["url"], self.event.get_absolute_url())
        self.assertEqual(row["venue"], "Kagan Primary School")

    def test_unpublished_events_are_not_in_the_feed(self):
        titles = [item["title"] for item in self.client.get(reverse("events:feed")).json()]
        self.assertNotIn("Hidden practice", titles)

    def test_feed_honours_a_range_sent_with_a_browser_offset(self):
        # 09:00 EAT on 29 Oct is 23:00 on 28 Oct in UTC-07:00, so a window that
        # starts at midnight UTC-07:00 on 29 Oct must not include it.
        response = self.client.get(
            reverse("events:feed"),
            {"start": "2026-10-29T00:00:00-07:00", "end": "2026-10-31T00:00:00-07:00"},
        )
        self.assertEqual(response.json(), [])

        response = self.client.get(
            reverse("events:feed"),
            {"start": "2026-10-28T00:00:00-07:00", "end": "2026-10-31T00:00:00-07:00"},
        )
        self.assertEqual([item["title"] for item in response.json()], ["School fees support day"])

    def test_feed_times_are_east_africa_time(self):
        row = self.client.get(reverse("events:feed")).json()[0]
        self.assertTrue(row["start"].endswith("+03:00"), row["start"])

    def test_garbage_range_is_ignored_instead_of_erroring(self):
        response = self.client.get(reverse("events:feed"), {"start": "not-a-date"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)


class PublicEventPageTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title="Mama Otila thank-you lunch",
            category=Event.Category.SUPPORT,
            starts_at=eat(2026, 9, 19),
            venue="Rangwe trading centre",
            published=True,
        )
        self.report = EventReport.objects.create(
            event=self.event,
            title="Report: thank-you lunch",
            body="First paragraph.\n\nSecond paragraph.",
            published=True,
        )
        Event.objects.create(title="Secret meeting", starts_at=eat(2026, 9, 20), venue="Office", published=False)

    def test_list_shows_published_events_and_hides_drafts(self):
        response = self.client.get(reverse("events:list"))
        self.assertContains(response, "Mama Otila thank-you lunch")
        self.assertNotContains(response, "Secret meeting")

    def test_list_filters_by_category(self):
        response = self.client.get(reverse("events:list"), {"category": Event.Category.SCHOOL_FEES})
        self.assertContains(response, "Nothing posted yet")
        self.assertNotContains(response, self.event.get_absolute_url())

    def test_detail_page_shows_the_report_and_a_past_event_is_still_readable(self):
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "Report: thank-you lunch")
        self.assertTrue(self.event.is_past)

    def test_report_page_splits_the_body_into_paragraphs(self):
        response = self.client.get(self.report.get_absolute_url())
        self.assertContains(response, "Second paragraph.")
        self.assertEqual(len(response.context["report"].body_paragraphs), 2)

    def test_unpublished_detail_and_report_return_404(self):
        self.assertEqual(self.client.get(reverse("events:detail", kwargs={"pk": 999})).status_code, 404)
        draft = EventReport.objects.create(event=self.event, title="Draft", body="x", published=False)
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_calendar_page_carries_the_feed_and_timezone(self):
        response = self.client.get(reverse("events:calendar"))
        self.assertContains(response, "/events/feed/")
        self.assertContains(response, 'data-timezone="Africa/Nairobi"')
