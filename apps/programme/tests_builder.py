import io
import json
import tempfile
from datetime import date, time
from pathlib import Path

from django.urls import reverse

from apps.conferences.models import Speaker

from . import spreadsheet
from .models import Contribution, Location, Session, SessionItem
from .tests import ProgrammeTestCase


class BuilderTestCase(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(self.chair)
        self.url = reverse("programme:build", args=[35]) + "?day=2027-07-20"

    def send(self, **data):
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        return response.status_code, response.json()

    def ok(self, **data):
        status, answer = self.send(**data)
        self.assertEqual(status, 200, answer)
        return answer

    def state(self):
        return self.client.get(self.url + "&format=json").json()


class DrawingTests(BuilderTestCase):
    def test_page_and_state(self):
        self.assertContains(self.client.get(self.url), "builder-config")
        state = self.state()
        self.assertEqual(state["day"], "2027-07-20")
        self.assertEqual([r["name"] for r in state["rooms"]], ["Room A", "Room B"])
        self.assertEqual({p["name"]: p["editable"] for p in state["parts"]}["Industry day"], True)
        self.assertEqual([p["label"] for p in state["pool"]["papers"]], ["101", "102"])

    def test_draw_in_a_room_across_all_and_parallel(self):
        answer = self.ok(action="create", part=self.academic.pk, kind="papers", start="10:30", end="12:00",
                         mode="room", location=self.room_b.pk)
        self.assertEqual(answer["note"], "1 session added.")
        self.ok(action="create", part=self.academic.pk, kind="keynote", title="Opening", start="09:00", end="10:00",
                mode="all", location=self.room_a.pk)
        self.ok(action="create", part=self.academic.pk, kind="break", start="10:00", end="10:30", mode="all",
                location=None)
        answer = self.ok(action="create", part=self.academic.pk, kind="papers", start="13:00", end="14:30",
                         mode="parallel")
        self.assertEqual(answer["note"], "2 sessions added.")
        sessions = {(s["start"], s["kind"], s["location"]): s for s in answer["sessions"]}
        self.assertTrue(sessions[("09:00", "keynote", self.room_a.pk)]["plenary"])
        self.assertTrue(sessions[("09:00", "keynote", self.room_a.pk)]["spans"])
        self.assertTrue(sessions[("10:00", "break", None)]["spans"])
        self.assertFalse(sessions[("10:30", "papers", self.room_b.pk)]["spans"])

    def test_refused(self):
        status, answer = self.send(action="create", part=self.academic.pk, kind="papers", start="12:00", end="11:00",
                                   mode="room", location=self.room_a.pk)
        self.assertEqual(status, 400)
        self.assertIn("end after it starts", answer["error"])
        status, answer = self.send(action="create", part=self.academic.pk, kind="keynote", start="09:00", end="10:00",
                                   mode="all", location=None)
        self.assertIn("plenary session needs a location", answer["error"])

    def test_move_resize_and_details(self):
        s = self.session(code="1A")
        self.ok(action="update", id=s.pk, start="10:15", end="11:15", location=self.room_b.pk)
        self.ok(action="update", id=s.pk, end="11:45")
        s.refresh_from_db()
        self.assertEqual((s.start, s.end, s.location_id), (time(10, 15), time(11, 45), self.room_b.pk))
        self.ok(action="update", id=s.pk, title="Takt", people=[{"role": "chair", "name": "Cy Lee", "affiliation": "NTNU"},
                                                               {"role": "chair", "name": ""}], change_note="Moved")
        s.refresh_from_db()
        self.assertEqual((s.title, [p.name for p in s.people.all()]), ("Takt", ["Cy Lee"]))
        self.assertIsNotNone(s.changed)
        self.ok(action="update", id=s.pk, date="2027-07-21")
        self.assertEqual(Session.objects.get(pk=s.pk).date, date(2027, 7, 21))
        self.ok(action="delete", id=s.pk)
        self.assertFalse(Session.objects.filter(pk=s.pk).exists())


class PlacingTests(BuilderTestCase):
    def test_papers_and_contributions(self):
        a = self.session(code="1A")
        posters = self.session(code="P", kind=Session.Kind.POSTERS, location="b")
        welcome = Contribution.objects.create(programme=self.programme, part=self.academic, kind="welcome",
                                              title="Welcome by the dean", speakers="Dee Dean (TUM)", minutes=10)
        self.ok(action="place", session=a.pk, entry=f"s{self.p1.pk}")
        answer = self.ok(action="place", session=a.pk, entry=f"c{welcome.pk}", index=0)
        items = next(s for s in answer["sessions"] if s["id"] == a.pk)["items"]
        self.assertEqual([i["title"] for i in items], ["Welcome by the dean", "Takt in hospitals"])
        self.assertEqual(answer["pool"]["contributions"], [])
        item = SessionItem.objects.get(submission=self.p1)
        self.ok(action="place", session=posters.pk, entry=f"i{item.pk}")
        item.refresh_from_db()
        self.assertEqual((item.session_id, item.presentation), (posters.pk, "poster"))
        self.ok(action="item", item=item.pk, presenter="Bo Jones", minutes="5")
        item.refresh_from_db()
        self.assertEqual((item.presenter, item.minutes), ("Bo Jones", 5))
        answer = self.ok(action="unplace", item=item.pk)
        self.assertIn(f"s{self.p1.pk}", [p["entry"] for p in answer["pool"]["papers"]])
        status, answer = self.send(action="place", session=a.pk, entry=f"s{self.p3.pk}")  # withdrawn
        self.assertEqual(status, 400)

    def test_contribution_is_not_an_empty_item(self):
        from . import checks

        a = self.session(code="1A", kind=Session.Kind.KEYNOTE)
        welcome = Contribution.objects.create(programme=self.programme, part=self.academic, title="Welcome")
        SessionItem.objects.create(session=a, contribution=welcome)
        self.assertFalse([p for p in checks.problems(self.programme) if p.level == checks.ERROR])
        self.assertEqual(next(s for s in self.state()["sessions"] if s["id"] == a.pk)["problems"], [])

    def test_add_contribution(self):
        answer = self.ok(action="contribution", part=self.industry.pk, kind="talk", title="Site logistics at BMW",
                         speakers="Eve Engineer")
        self.assertEqual(answer["pool"]["contributions"][0]["title"], "Site logistics at BMW")


class PermissionTests(BuilderTestCase):
    def test_part_editors(self):
        industry = self.user("ind", "IGLC 35 industry day chairs")
        self.client.force_login(industry)
        status, answer = self.send(action="create", part=self.academic.pk, kind="papers", start="10:00", end="11:00",
                                   mode="room", location=self.room_a.pk)
        self.assertEqual(status, 400)
        self.assertIn("cannot edit that part", answer["error"])
        a = self.session(code="1A")
        status, _ = self.send(action="update", id=a.pk, start="09:00")
        self.assertEqual(status, 400)
        self.assertEqual(self.send(action="room", name="Aula")[0], 400)
        self.ok(action="create", part=self.industry.pk, kind="industry", start="10:00", end="11:00", mode="room",
                location=self.room_b.pk)

    def test_organisers_add_rooms_only(self):
        self.client.force_login(self.user("org", "IGLC 35 organisers"))
        self.ok(action="room", name="Aula")
        self.assertTrue(Location.objects.filter(name="Aula").exists())
        self.assertEqual(self.send(action="create", part=self.academic.pk, kind="papers", start="10:00", end="11:00",
                                   mode="room", location=self.room_a.pk)[0], 400)


class DayTests(BuilderTestCase):
    def test_copy_day_and_numbering(self):
        self.ok(action="create", part=self.academic.pk, kind="keynote", start="09:00", end="10:00", mode="all",
                location=self.room_a.pk)
        self.ok(action="create", part=self.academic.pk, kind="papers", start="10:30", end="12:00", mode="parallel")
        a = Session.objects.get(start=time(10, 30), location=self.room_a)
        SessionItem.objects.create(session=a, submission=self.p1)
        answer = self.ok(action="copy_day", to="2027-07-21")
        self.assertEqual(answer["note"], "3 sessions copied to Wednesday 21 July.")
        copied = Session.objects.filter(date=date(2027, 7, 21))
        self.assertEqual(copied.count(), 3)
        self.assertFalse(SessionItem.objects.filter(session__in=copied).exists())
        self.session(part=self.industry, kind=Session.Kind.INDUSTRY, start_at=time(14), end_at=time(15))
        self.session(part=self.industry, kind=Session.Kind.INDUSTRY, start_at=time(14), end_at=time(15), location="b")
        self.ok(action="renumber")
        codes = {(s.date.day, s.start.hour, s.location.name if s.location else "", s.part.kind): s.code
                 for s in Session.objects.select_related("location", "part")}
        self.assertEqual(codes[(20, 9, "Room A", "academic")], "")
        self.assertEqual(codes[(20, 10, "Room A", "academic")], "1A")
        self.assertEqual(codes[(20, 10, "Room B", "academic")], "1B")
        self.assertEqual(codes[(21, 10, "Room B", "academic")], "2B")
        self.assertEqual(codes[(20, 14, "Room A", "industry")], "I1A")


class SpreadsheetTests(BuilderTestCase):
    def test_export_then_import(self):
        a = self.session(code="1A", title="Takt")
        SessionItem.objects.create(session=a, submission=self.p1)
        a.people.create(name="Cy Lee", affiliation="NTNU")
        response = self.client.get(reverse("programme:spreadsheet", args=[35]))
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        data = response.content
        Session.objects.all().delete()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p.xlsx"
            path.write_bytes(data)
            report = spreadsheet.import_sheet(self.programme, self.chair, path)
        self.assertEqual((report["added"], report["updated"], report["problems"]), (1, 0, []))
        s = Session.objects.get()
        self.assertEqual((s.code, s.title, s.location, s.start), ("1A", "Takt", self.room_a, time(10)))
        self.assertEqual([p.name for p in s.people.all()], ["Cy Lee"])
        self.assertEqual([i.submission_id for i in s.items.all()], [self.p1.pk])

    def test_draft_from_excel(self):
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["Day", "Start", "End", "Room", "Part", "Kind", "Title", "Plenary", "Papers", "Contributions"])
        sheet.append(["2027-07-20", "09:00", "10:00", "Aula", "Academic conference", "Keynote", "Opening", "yes", "",
                      "Welcome by the dean"])
        sheet.append(["20.07.2027", time(10, 30), time(12), "Room B", "", "Paper session", "", "", "101, 102", ""])
        sheet.append(["2027-07-20", "12:00", "13:00", "", "", "Lunch", "", "", "", ""])
        sheet.append(["2027-07-20", "14:00", "15:00", "Room A", "Nonsense part", "", "", "", "", ""])
        sheet.append(["2027-07-20", "15:00", "16:00", "Room A", "", "", "", "", "999", ""])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "draft.xlsx"
            book.save(path)
            report = spreadsheet.import_sheet(self.programme, self.chair, path)
        self.assertEqual(report["added"], 3, report)
        self.assertEqual(len(report["problems"]), 2, report)
        self.assertIn("Row 5", report["problems"][0])
        self.assertIn("No paper 999", report["problems"][1])
        opening = Session.objects.get(title="Opening")
        self.assertTrue(opening.plenary)
        self.assertEqual(opening.location.name, "Aula")
        self.assertEqual(opening.items.get().contribution.title, "Welcome by the dean")
        self.assertEqual(Session.objects.get(location=self.room_b).items.count(), 2)
        self.assertEqual(Session.objects.get(kind="meal").location, None)
        self.assertFalse(Session.objects.filter(start=time(15)).exists())  # the whole row is left out

    def test_upload_through_the_page(self):
        from openpyxl import Workbook

        book = Workbook()
        book.active.append(["Day", "Start", "End", "Room"])
        book.active.append(["2027-07-20", "10:00", "11:00", "Room A"])
        buffer = io.BytesIO()
        book.save(buffer)
        buffer.name = "draft.xlsx"
        buffer.seek(0)
        response = self.client.post(reverse("programme:spreadsheet", args=[35]), {"file": buffer})
        self.assertRedirects(response, reverse("programme:build", args=[35]))
        self.assertEqual(Session.objects.count(), 1)


class ContributionPageTests(BuilderTestCase):
    def test_add_and_from_speakers(self):
        url = reverse("programme:contributions", args=[35])
        self.client.post(url, {"part": self.industry.pk, "kind": "talk", "title": "Prefabrication at scale",
                               "speakers": "Eve"})
        Speaker.objects.create(conference=self.conference, name="Glenn Keynote", affiliation="UC Berkeley",
                               talk_title="Lean at 30", group="Keynote speakers")
        Speaker.objects.create(conference=self.conference, name="Ina Industry", group="Industry day speakers")
        self.client.post(url, {"action": "speakers"})
        self.client.post(url, {"action": "speakers"})  # not twice
        found = {c.title: (c.part.kind, c.kind) for c in Contribution.objects.all()}
        self.assertEqual(found, {"Prefabrication at scale": ("industry", "talk"), "Lean at 30": ("academic", "keynote"),
                                 "Ina Industry": ("industry", "talk")})
        self.assertContains(self.client.get(url), "Lean at 30")


class DaysTests(BuilderTestCase):
    def test_opens_on_the_conference_start(self):
        self.programme.first_day = date(2027, 7, 17)
        self.programme.save()
        self.assertEqual(self.state()["day"], "2027-07-20")  # the ?day= of the test URL
        response = self.client.get(reverse("programme:build", args=[35]) + "?format=json")
        self.assertEqual(response.json()["day"], "2027-07-19")

    def test_days_follow_the_conference(self):
        from .models import Programme

        self.session(part=self.phd, day=date(2027, 7, 20))
        self.conference.start_date, self.conference.end_date = date(2027, 7, 12), date(2027, 7, 16)
        self.conference.save()
        programme = Programme.objects.get()
        self.assertEqual((programme.first_day, programme.last_day), (date(2027, 7, 12), date(2027, 7, 20)))
        self.conference.city = "München"
        self.conference.save()  # dates unchanged: nothing happens
        self.assertEqual(Programme.objects.get().last_day, date(2027, 7, 20))

    def test_days_far_from_the_conference_are_refused(self):
        from django.core.exceptions import ValidationError

        self.programme.first_day = date(2026, 9, 26)
        with self.assertRaises(ValidationError):
            self.programme.full_clean()
