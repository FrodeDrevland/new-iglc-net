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
        self.assertEqual(answer["note"], "3 sessions added.")  # one in each of the day's three lanes
        self.assertEqual(sorted(s["lane"] for s in answer["sessions"] if s["start"] == "13:00"), [1, 2, 3])
        self.assertEqual({s["location"] for s in answer["sessions"] if s["start"] == "13:00"}, {None})
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
        status, answer = self.send(action="create", part=self.academic.pk, kind="papers", start="09:00", end="10:00",
                                   mode="lane", lane=7)
        self.assertEqual(answer["error"], "No such lane.")

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
        self.assertIn("You do not edit the academic conference", answer["error"])
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
        a = Session.objects.get(start=time(10, 30), lane=1)
        SessionItem.objects.create(session=a, submission=self.p1)
        answer = self.ok(action="copy_day", to="2027-07-21")
        self.assertEqual(answer["note"], "4 sessions copied to Wednesday 21 July.")
        copied = Session.objects.filter(date=date(2027, 7, 21))
        self.assertEqual(copied.count(), 4)
        self.assertEqual(sorted(s.lane for s in copied if s.lane), [1, 2, 3])
        self.assertFalse(SessionItem.objects.filter(session__in=copied).exists())
        self.ok(action="create", part=self.industry.pk, kind="industry", start="14:00", end="15:00", mode="parallel")
        self.ok(action="renumber")
        codes = {(s.date.day, s.start.hour, s.lane, s.part.kind): s.code for s in Session.objects.select_related("part")}
        self.assertEqual(codes[(20, 9, None, "academic")], "")
        self.assertEqual(codes[(20, 10, 1, "academic")], "1A")
        self.assertEqual(codes[(20, 10, 3, "academic")], "1C")
        self.assertEqual(codes[(21, 10, 2, "academic")], "2B")
        self.assertEqual(codes[(20, 14, 1, "industry")], "I1A")


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


class DayPartTests(BuilderTestCase):
    def test_sessions_take_the_day_s_part(self):
        from .models import ProgrammeDay

        ProgrammeDay.objects.create(programme=self.programme, date=date(2027, 7, 23)).parts.set([self.industry])
        url = reverse("programme:build", args=[35]) + "?day=2027-07-23"
        state = self.client.get(url + "&format=json").json()
        self.assertEqual(state["day_parts"], [self.industry.pk])
        answer = self.client.post(url, json.dumps({"action": "create", "kind": "industry", "start": "10:00",
                                                  "end": "11:00", "mode": "room", "location": self.room_a.pk}),
                                  content_type="application/json").json()
        self.assertEqual(answer["sessions"][0]["part"], self.industry.pk)
        # a day of the academic conference by default
        self.assertEqual(self.client.get(reverse("programme:build", args=[35]) + "?day=2027-07-21&format=json")
                         .json()["day_parts"], [self.academic.pk])

    def test_moving_to_another_day_changes_the_part(self):
        from .models import ProgrammeDay

        ProgrammeDay.objects.create(programme=self.programme, date=date(2027, 7, 23)).parts.set([self.industry])
        s = self.session(code="1A")
        self.ok(action="update", id=s.pk, date="2027-07-23")
        self.assertEqual(Session.objects.get(pk=s.pk).part, self.industry)
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        s2 = self.session(code="1B")
        status, answer = self.send(action="update", id=s2.pk, date="2027-07-23")
        self.assertEqual(status, 400)
        self.assertIn("which you do not edit", answer["error"])

    def test_the_part_must_be_the_day_s(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as caught:
            self.session(part=self.industry, day=date(2027, 7, 21))
        self.assertIn("belongs to Academic conference", str(caught.exception))

    def test_chairs_set_what_a_day_belongs_to(self):
        url = reverse("programme:build", args=[35]) + "?day=2027-07-22"
        post = lambda parts: self.client.post(url, json.dumps({"action": "day_parts", "parts": parts}),  # noqa: E731
                                              content_type="application/json")
        answer = post([self.industry.pk]).json()
        self.assertEqual(answer["day_parts"], [self.industry.pk])
        self.assertEqual(answer["note"], "Thursday 22 July: Industry day.")
        self.assertEqual(post([]).status_code, 400)
        Session.objects.create(programme=self.programme, part=self.industry, date=date(2027, 7, 22), start=time(9),
                               end=time(10), location=self.room_a)
        response = post([self.academic.pk])
        self.assertEqual(response.status_code, 400)
        self.assertIn("still has sessions", response.json()["error"])
        self.client.force_login(self.user("sci", "IGLC 35 scientific chairs"))
        self.assertEqual(post([self.academic.pk, self.industry.pk]).status_code, 400)

    def test_copying_to_an_unset_day_copies_its_parts(self):
        from .models import ProgrammeDay

        ProgrammeDay.objects.create(programme=self.programme, date=date(2027, 7, 22)).parts.set([self.industry])
        Session.objects.create(programme=self.programme, part=self.industry, date=date(2027, 7, 22), start=time(9),
                               end=time(10), location=self.room_a)
        url = reverse("programme:build", args=[35]) + "?day=2027-07-22"
        self.client.post(url, json.dumps({"action": "copy_day", "to": "2027-07-23"}), content_type="application/json")
        self.assertEqual([p.pk for p in self.programme.day_parts(date(2027, 7, 23))], [self.industry.pk])
        self.assertEqual(Session.objects.get(date=date(2027, 7, 23)).part, self.industry)


class SettingsDaysTests(BuilderTestCase):
    def test_days_on_the_settings_page(self):
        url = reverse("programme:settings", args=[35])
        response = self.client.get(url)
        self.assertContains(response, 'name="day-2027-07-23"')
        parts = list(self.programme.parts.all())
        data = {"status": "hidden", "time_zone": "Europe/Berlin", "first_day": "2027-07-17", "last_day": "2027-07-23",
                "notice": "", "parts-TOTAL_FORMS": str(len(parts)), "parts-INITIAL_FORMS": str(len(parts)),
                "day-2027-07-23": [str(self.industry.pk)]}
        for i, part in enumerate(parts):
            data.update({f"parts-{i}-id": part.pk, f"parts-{i}-name": part.name, f"parts-{i}-kind": part.kind,
                         f"parts-{i}-colour": part.colour, f"parts-{i}-sort_order": part.sort_order,
                         f"parts-{i}-description": ""})
            if part.public:
                data[f"parts-{i}-public"] = "on"
        self.assertRedirects(self.client.post(url, data), reverse("programme:overview", args=[35]))
        self.assertEqual([p.pk for p in self.programme.day_parts(date(2027, 7, 23))], [self.industry.pk])


class LaneTests(BuilderTestCase):
    def test_lanes_and_rooms(self):
        answer = self.ok(action="lanes", count=2)
        self.assertEqual((answer["lanes"], answer["note"]), (2, "2 parallel lanes on Tuesday 20 July."))
        self.ok(action="create", part=self.academic.pk, kind="papers", start="10:00", end="11:00", mode="parallel")
        self.ok(action="create", part=self.academic.pk, kind="papers", start="11:00", end="12:00", mode="lane", lane=2,
                location=self.room_b.pk)
        status, answer = self.send(action="lanes", count=1)
        self.assertIn("Lane 2 still has sessions", answer["error"])
        # a room for the sessions in lane 2 without one; the one with a room keeps it
        answer = self.ok(action="lane_room", lane=2, location=self.room_a.pk)
        self.assertEqual(answer["note"], "Room A given to 1 session without a room.")
        rooms = {(s["start"], s["lane"]): s["room"] for s in answer["sessions"]}
        self.assertEqual(rooms, {("10:00", 1): "", ("10:00", 2): "Room A", ("11:00", 2): "Room B"})

    def test_drag_to_another_lane(self):
        answer = self.ok(action="create", part=self.academic.pk, kind="papers", start="10:00", end="11:00", mode="lane",
                         lane=1)
        s = answer["sessions"][0]
        self.ok(action="update", id=s["id"], lane=3)
        self.assertEqual(Session.objects.get(pk=s["id"]).lane, 3)

    def test_sessions_without_lane_get_one(self):
        self.session(code="1A")
        self.session(code="1B", location="b")
        lanes = sorted(s["lane"] for s in self.state()["sessions"])
        self.assertEqual(lanes, [1, 2])

    def test_room_clash_is_still_an_error(self):
        from . import checks

        self.session(code="1A")
        self.session(code="1B", start_at=time(10, 30), end_at=time(11, 30))
        self.assertIn("Two sessions in Room A at the same time.",
                      [p.text for p in checks.problems(self.programme) if p.level == checks.ERROR])
