from datetime import date, time

from django.urls import reverse
from django.utils import timezone

from apps.conferences.models import ConferencePage

from . import checks
from .models import Programme, Session, SessionItem, SessionPerson
from .tests import HOST, ProgrammeTestCase

VENUE = {"HTTP_HOST": "program.localhost"}


class VenueTestCase(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        Programme.objects.update(status=Programme.Status.FINAL)
        self.programme.refresh_from_db()
        page = ConferencePage.objects.child_of(self.home).get(slug="programme")
        page.body = [("programme", {"part": ""})]
        page.save_revision().publish()
        self.opening = self.session(day=date(2027, 7, 20), start_at=time(9), end_at=time(10), title="Opening",
                                    kind=Session.Kind.KEYNOTE, plenary=True)
        self.a = self.session(code="1A", title="Takt", start_at=time(10, 30), end_at=time(12))
        self.b = self.session(code="1B", title="Last Planner", location="b", start_at=time(10, 30), end_at=time(12))
        self.lunch = self.session(start_at=time(12), end_at=time(13), kind=Session.Kind.BREAK, location=None,
                                  title="Lunch")
        self.day2 = self.session(day=date(2027, 7, 21), code="3A", title="Flow", start_at=time(9), end_at=time(10))
        SessionItem.objects.create(session=self.a, submission=self.p1, presenter="Ann Smith")
        SessionPerson.objects.create(session=self.a, name="Cy Lee")
        self.phd_session = self.session(part=self.phd, title="Doctoral colloquium", day=date(2027, 7, 20),
                                        start_at=time(14), end_at=time(15))

    def venue(self, path="/", **params):
        return self.client.get(path, params, **VENUE)


class NowTests(VenueTestCase):
    def test_now_and_next(self):
        response = self.venue(at="2027-07-20T10:45")
        self.assertContains(response, "Tuesday 20 July, 10:45")
        now = response.content.decode().split("<h2>Next")[0]
        self.assertIn("Takt", now)
        self.assertIn("Last Planner", now)
        self.assertIn("Lunch", response.content.decode().split("<h2>Next")[1])
        self.assertNotContains(response, "Doctoral colloquium")
        self.assertContains(response, f'href="http://conference.localhost:8000/2027/programme/session/{self.a.pk}/"')

    def test_between_sessions_and_days(self):
        response = self.venue(at="2027-07-20T10:15")
        self.assertContains(response, "Nothing on the programme right now.")
        self.assertContains(response, "Takt")
        response = self.venue(at="2027-07-20T18:00")
        self.assertContains(response, "Nothing more today.")

    def test_before_and_after(self):
        response = self.venue(at="2027-06-01T12:00")
        self.assertContains(response, "starts on Tuesday 20 July 2027")
        self.assertContains(response, "Opening")
        self.assertContains(self.venue(at="2027-08-01T12:00"), "has taken place")

    def test_real_time_works(self):
        self.assertEqual(self.venue().status_code, 200)

    def test_changes_and_notice(self):
        Session.objects.filter(pk=self.b.pk).update(change_note="Moved to Room A", changed=timezone.now())
        Session.objects.filter(pk=self.day2.pk).update(cancelled=True, changed=timezone.now())
        Programme.objects.update(notice="The dinner starts at 20:00.")
        response = self.venue(at="2027-07-20T10:45")
        self.assertContains(response, "The dinner starts at 20:00.")
        self.assertContains(response, "<strong>Changed:</strong> Moved to Room A")
        changes = response.content.decode().split("<h2>Changes</h2>")[1]
        self.assertIn("3A", changes)
        self.assertIn("cancelled", changes)
        self.assertContains(self.client.get(f"/2027/programme/session/{self.day2.pk}/", **HOST), "<strong>Cancelled</strong>")

    def test_only_current_and_public(self):
        Programme.objects.update(status=Programme.Status.HIDDEN)
        self.assertEqual(self.venue().status_code, 404)
        Programme.objects.update(status=Programme.Status.FINAL)
        self.home.is_current = False
        self.home.save_revision().publish()
        type(self.home).objects.filter(pk=self.home.pk).update(is_current=False)
        self.assertEqual(self.venue().status_code, 404)

    def test_also_on_the_conference_site(self):
        response = self.client.get("/2027/programme/now/", {"at": "2027-07-20T10:45"}, **HOST)
        self.assertContains(response, "Takt")
        self.assertContains(response, f'href="/2027/programme/session/{self.a.pk}/"')

    def test_robots(self):
        self.assertContains(self.venue("/robots.txt"), "Disallow: /")

    def test_main_site_unaffected(self):
        self.assertEqual(self.client.get("/").status_code, 200)


class DayAndMineTests(VenueTestCase):
    def test_day(self):
        response = self.venue("/today/", at="2027-07-21T08:00")
        self.assertContains(response, "Wednesday 21 July")
        self.assertContains(response, "Flow")
        response = self.venue("/today/", day="2027-07-20")
        self.assertContains(response, "Takt")
        self.assertContains(response, 'href="/today/?day=2027-07-21"')

    def test_my_programme(self):
        response = self.venue("/my/")
        self.assertContains(response, 'data-my-programme="2027"')
        self.assertContains(response, f'<li data-session="{self.a.pk}" hidden>')
        self.assertContains(response, f'data-star="{self.a.pk}"')
        self.assertNotContains(response, f'data-session="{self.lunch.pk}"')
        self.assertNotContains(response, "Doctoral colloquium")

    def test_stars_on_the_programme_page(self):
        response = self.client.get("/2027/programme/", **HOST)
        self.assertContains(response, f'data-star="{self.a.pk}"')
        self.assertContains(response, "/static/js/programme.js")
        self.assertContains(response, 'href="http://program.localhost:8000/"')
        self.assertContains(response, 'href="/2027/programme/calendar.ics"')


class CalendarTests(VenueTestCase):
    def ics(self, path="/2027/programme/calendar.ics", **params):
        response = self.client.get(path, params, **HOST)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        return response.content.decode()

    def test_whole_programme(self):
        body = self.ics()
        self.assertEqual(body.count("BEGIN:VEVENT"), 4)  # not the break, not the PhD school
        self.assertIn("DTSTART:20270720T070000Z", body)  # 09:00 in Munich, summer time
        self.assertIn(f"UID:iglc35-session-{self.a.pk}@iglc.net", body)
        self.assertIn("SUMMARY:1A Takt", body)
        self.assertIn("LOCATION:Room A", body)
        self.assertIn(f"URL:http://conference.localhost:8000/2027/programme/session/{self.a.pk}/", body)
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split("\r\n")))
        self.assertTrue(body.endswith("END:VCALENDAR\r\n"))

    def test_cancelled(self):
        Session.objects.filter(pk=self.a.pk).update(cancelled=True)
        body = self.ics()
        self.assertIn("STATUS:CANCELLED", body)
        self.assertIn("SUMMARY:CANCELLED: 1A Takt", body)

    def test_selection_parts_and_private(self):
        body = self.ics(sessions=f"{self.a.pk},{self.day2.pk},{self.phd_session.pk}")
        self.assertEqual(body.count("BEGIN:VEVENT"), 2)
        self.assertIn("my programme", body)
        self.assertNotIn("Doctoral", self.ics(part=self.academic.pk))
        body = self.ics(k=str(self.phd.token))
        self.assertIn("Doctoral colloquium", body)
        self.assertEqual(body.count("BEGIN:VEVENT"), 1)
        self.assertEqual(self.client.get("/2027/programme/calendar.ics", {"part": self.phd.pk}, **HOST).status_code, 404)

    def test_session_and_venue_host(self):
        body = self.ics(f"/2027/programme/session/{self.a.pk}/calendar.ics")
        self.assertEqual(body.count("BEGIN:VEVENT"), 1)
        path = f"/2027/programme/session/{self.phd_session.pk}/calendar.ics"
        self.assertEqual(self.client.get(path, **HOST).status_code, 404)
        self.assertIn("Doctoral", self.ics(path, k=str(self.phd.token)))
        self.assertIn("BEGIN:VCALENDAR", self.venue("/calendar.ics").content.decode())


class BackOfficeTests(VenueTestCase):
    def test_change_note_is_dated_when_set(self):
        chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(chair)
        data = {"part": self.academic.pk, "kind": "papers", "code": "1B", "title": "Last Planner",
                "date": "2027-07-20", "start": "10:30", "end": "12:00", "location": self.room_b.pk, "notes": "",
                "change_note": "Moved to Room 102", "people-TOTAL_FORMS": "0", "people-INITIAL_FORMS": "0",
                "items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0"}
        self.client.post(reverse("programme:session", args=[35, self.b.pk]), data)
        self.b.refresh_from_db()
        self.assertEqual(self.b.change_note, "Moved to Room 102")
        self.assertIsNotNone(self.b.changed)

    def test_cancelled_sessions_do_not_clash(self):
        clash = self.session(code="1C", title="Clash", start_at=time(11), end_at=time(12))
        self.assertTrue(any("Two sessions in Room A" in p.text for p in checks.problems(self.programme)))
        Session.objects.filter(pk=clash.pk).update(cancelled=True)
        self.assertFalse(any("Two sessions in Room A" in p.text for p in checks.problems(self.programme)))

    def test_room_signs(self):
        organiser = self.user("org", "IGLC 35 organisers")
        self.client.force_login(organiser)
        response = self.client.get(reverse("programme:room_signs", args=[35]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertContains(self.client.get(reverse("programme:locations", args=[35])), "Room signs (PDF)")
