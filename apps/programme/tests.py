from datetime import date, time

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.archive.models import Author, Conference, Paper
from apps.conferences.models import ConferenceHomePage, ConferencePage
from apps.conferences.setup import seed, sync_site
from apps.production.models import Production, Submission

from . import checks
from .access import can_edit_locations, can_edit_part, can_view, programmes_for
from .models import Location, Part, Programme, Session, SessionItem, SessionPerson
from .setup import start

HOST = {"HTTP_HOST": "conference.localhost"}


class ProgrammeTestCase(TestCase):
    def setUp(self):
        sync_site()
        self.conference = Conference.objects.create(number=35, city="Munich", country="Germany",
                                                    start_date=date(2027, 7, 19), end_date=date(2027, 7, 23))
        self.home = seed(self.conference, current=True, publish=True)
        self.programme = start(self.conference, "Europe/Berlin")
        self.academic = self.programme.parts.get(kind=Part.Kind.ACADEMIC)
        self.industry = self.programme.parts.get(kind=Part.Kind.INDUSTRY)
        self.phd = self.programme.parts.get(kind=Part.Kind.PHD)
        # Tuesday holds three parts side by side, so that the tests can mix them on one day.
        from .models import ProgrammeDay

        ProgrammeDay.objects.create(programme=self.programme, date=date(2027, 7, 20)).parts.set(
            [self.academic, self.industry, self.phd])
        ProgrammeDay.objects.create(programme=self.programme, date=date(2027, 7, 17)).parts.set([self.phd])
        self.room_a = Location.objects.create(programme=self.programme, name="Room A", map_url="https://use.mazemap.com/x")
        self.room_b = Location.objects.create(programme=self.programme, name="Room B")
        production = Production.objects.create(conference=self.conference)
        self.p1 = Submission.objects.create(production=production, conftool_id=101, title="Takt in hospitals",
                                            registered_authors=[{"name": "Ann Smith"}, {"name": "Bo Jones"}])
        self.p2 = Submission.objects.create(production=production, conftool_id=102, title="Last Planner in Munich",
                                            registered_authors=[{"name": "Cy Lee"}])
        self.p3 = Submission.objects.create(production=production, conftool_id=103, title="Withdrawn one",
                                            registered_authors=[{"name": "Di Ray"}], status=Submission.Status.WITHDRAWN)

    def user(self, name, *groups, superuser=False):
        user = User.objects.create_user(name, password="pw", is_superuser=superuser)
        for group in groups:
            user.groups.add(group if isinstance(group, Group) else Group.objects.get(name=group))
        return user

    def session(self, part=None, day=date(2027, 7, 20), start_at=time(10), end_at=time(11), location="a", **kwargs):
        location = {"a": self.room_a, "b": self.room_b, None: None}[location]
        session = Session(programme=self.programme, part=part or self.academic, date=day, start=start_at, end=end_at,
                          location=location, **kwargs)
        session.full_clean()
        session.save()
        return session


class SetupTests(ProgrammeTestCase):
    def test_parts_and_groups(self):
        self.assertEqual(list(self.programme.parts.values_list("kind", flat=True)),
                         ["academic", "industry", "workshop", "phd"])
        self.assertEqual(self.programme.chairs.name, "IGLC 35 conference chairs")
        self.assertEqual(self.academic.editors.name, "IGLC 35 scientific chairs")
        self.assertEqual(self.industry.editors.name, "IGLC 35 industry day chairs")
        self.assertEqual(self.phd.editors.name, "IGLC 35 PhD summer school deans")
        self.assertFalse(self.phd.public)
        self.assertTrue(self.programme.chairs.permissions.filter(codename="access_admin").exists())

    def test_repeatable(self):
        start(self.conference, "Europe/Berlin")
        self.assertEqual(Programme.objects.count(), 1)
        self.assertEqual(self.programme.parts.count(), 4)


class AccessTests(ProgrammeTestCase):
    def test_who_edits_what(self):
        chair = self.user("chair", "IGLC 35 conference chairs")
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        industry = self.user("ind", "IGLC 35 industry day chairs")
        dean = self.user("dean", "IGLC 35 PhD summer school deans")
        organiser = self.user("org", "IGLC 35 organisers")
        outsider = self.user("out")
        workshop = self.programme.parts.get(kind=Part.Kind.WORKSHOP)
        self.assertTrue(all(can_edit_part(chair, p) for p in self.programme.parts.all()))
        self.assertTrue(can_edit_part(scientific, self.academic))
        self.assertFalse(can_edit_part(scientific, self.industry))
        self.assertFalse(can_edit_part(scientific, workshop))
        self.assertTrue(can_edit_part(industry, self.industry))
        self.assertFalse(can_edit_part(industry, self.academic))
        self.assertTrue(can_edit_part(dean, self.phd))
        self.assertFalse(can_edit_part(dean, self.academic))
        self.assertFalse(any(can_edit_part(organiser, p) for p in self.programme.parts.all()))
        self.assertTrue(can_edit_locations(organiser, self.programme))
        self.assertTrue(can_edit_locations(chair, self.programme))
        self.assertFalse(can_edit_locations(scientific, self.programme))
        for user in (chair, scientific, industry, dean, organiser):
            self.assertTrue(can_view(user, self.programme))
            self.assertEqual(list(programmes_for(user)), [self.programme])
        self.assertFalse(can_view(outsider, self.programme))
        self.assertFalse(programmes_for(outsider).exists())

    def test_other_conference_is_out_of_reach(self):
        other = Conference.objects.create(number=34, city="Singapore", start_date=date(2026, 6, 22))
        start(other, "Asia/Singapore")
        scientific = self.user("sci", "IGLC 34 scientific chairs")
        self.assertFalse(can_view(scientific, self.programme))
        self.client.force_login(scientific)
        self.assertNotEqual(self.client.get(reverse("programme:overview", args=[35])).status_code, 200)
        self.assertEqual(self.client.get(reverse("programme:overview", args=[34])).status_code, 200)

    def test_frozen(self):
        chair = self.user("chair", "IGLC 35 conference chairs")
        ConferenceHomePage.objects.filter(pk=self.home.pk).update(frozen=True)
        programme = Programme.objects.get(pk=self.programme.pk)
        self.assertFalse(can_edit_part(chair, programme.parts.first()))
        self.assertFalse(can_edit_locations(chair, programme))
        self.assertTrue(can_view(chair, programme))
        admin = self.user("admin", superuser=True)
        self.assertTrue(can_edit_part(admin, programme.parts.first()))


class SessionRuleTests(ProgrammeTestCase):
    def test_plenary_needs_a_location(self):
        with self.assertRaises(ValidationError) as caught:
            self.session(location=None, plenary=True, kind=Session.Kind.KEYNOTE)
        self.assertIn("A plenary session needs a location", str(caught.exception))

    def test_break_needs_no_location(self):
        self.session(location=None, kind=Session.Kind.BREAK)

    def test_times_and_days(self):
        with self.assertRaises(ValidationError):
            self.session(start_at=time(11), end_at=time(10))
        with self.assertRaises(ValidationError):
            self.session(day=date(2027, 7, 17))
        self.programme.first_day = date(2027, 7, 17)
        self.programme.save()
        self.session(day=date(2027, 7, 17), part=self.phd)


class CheckTests(ProgrammeTestCase):
    def texts(self, level=None):
        return [p.text for p in checks.problems(self.programme) if level is None or p.level == level]

    def test_location_clash(self):
        self.session(code="1A")
        self.session(code="1B", start_at=time(10, 30), end_at=time(12))
        self.assertIn("Two sessions in Room A at the same time.", self.texts(checks.ERROR))

    def test_back_to_back_is_fine(self):
        self.session(code="1A")
        self.session(code="2A", start_at=time(11), end_at=time(12))
        self.assertFalse(self.texts(checks.ERROR))

    def test_parallel_with_plenary(self):
        self.session(kind=Session.Kind.KEYNOTE, plenary=True, title="Opening")
        self.session(location="b", title="Side")
        self.assertTrue(any("in parallel with the plenary" in t for t in self.texts(checks.WARNING)))
        # another part may run alongside (industry day, PhD school)
        Session.objects.filter(title="Side").update(part=self.industry)
        self.assertFalse(any("plenary" in t for t in self.texts()))

    def test_chair_presenting_in_parallel_session(self):
        a = self.session(code="1A")
        b = self.session(code="1B", location="b")
        SessionPerson.objects.create(session=a, name="Ann Smith")
        SessionItem.objects.create(session=b, submission=self.p1, presenter="Ann Smith")
        self.assertTrue(any("Ann Smith is in two sessions" in t for t in self.texts(checks.WARNING)))

    def test_chair_presenting_in_own_session_is_only_a_note(self):
        a = self.session(code="1A")
        SessionPerson.objects.create(session=a, name="Ann Smith")
        SessionItem.objects.create(session=a, submission=self.p1, presenter="Ann Smith")
        self.assertFalse(self.texts(checks.WARNING))
        self.assertTrue(any("chairs the session and presents in it" in t for t in self.texts(checks.NOTE)))

    def test_papers(self):
        a = self.session(code="1A")
        b = self.session(code="2A", start_at=time(13), end_at=time(14))
        SessionItem.objects.create(session=a, submission=self.p1, presenter="Someone Else")
        SessionItem.objects.create(session=b, submission=self.p1)
        SessionItem.objects.create(session=b, submission=self.p3)
        errors = self.texts(checks.ERROR)
        self.assertIn("Paper 101 is placed 2 times.", errors)
        self.assertIn("Paper 103 is withdrawn but still in the programme.", errors)
        self.assertTrue(any("is not an author" in t for t in self.texts(checks.WARNING)))
        self.assertEqual(list(checks.unplaced(self.programme)), [self.p2])

    def test_too_many_minutes(self):
        a = self.session()
        SessionItem.objects.create(session=a, submission=self.p1, minutes=40)
        SessionItem.objects.create(session=a, submission=self.p2, minutes=30)
        self.assertIn("The items take 70 minutes; the session has 60.", self.texts(checks.WARNING))


class ViewTests(ProgrammeTestCase):
    def test_start_programme(self):
        admin = self.user("admin", superuser=True)
        other = Conference.objects.create(number=36, city="X", start_date=date(2028, 7, 1), end_date=date(2028, 7, 5))
        self.client.force_login(admin)
        response = self.client.post(reverse("programme:list"), {"conference": other.pk, "time_zone": "Nowhere/City"})
        self.assertContains(response, "Not a time zone")
        response = self.client.post(reverse("programme:list"), {"conference": other.pk, "time_zone": "Europe/Oslo"})
        self.assertRedirects(response, reverse("programme:overview", args=[36]))
        self.assertTrue(Group.objects.filter(name="IGLC 36 scientific chairs").exists())

    def test_only_superusers_start(self):
        chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(chair)
        self.client.post(reverse("programme:list"), {"conference": 1, "time_zone": "UTC"})
        self.assertFalse(Programme.objects.filter(conference_id=1).exclude(pk=self.programme.pk).exists())
        self.assertEqual(Programme.objects.count(), 1)

    def session_data(self, **extra):
        data = {"part": self.academic.pk, "kind": "papers", "code": "3B", "title": "Takt", "date": "2027-07-21",
                "start": "14:00", "end": "15:30", "location": self.room_a.pk, "notes": "",
                "people-TOTAL_FORMS": "1", "people-INITIAL_FORMS": "0",
                "people-0-role": "chair", "people-0-name": "Ann Smith", "people-0-affiliation": "NTNU",
                "people-0-order": "1",
                "items-TOTAL_FORMS": "2", "items-INITIAL_FORMS": "0",
                "items-0-order": "1", "items-0-submission": self.p1.pk, "items-0-presentation": "talk",
                "items-0-presenter": "Ann Smith", "items-0-minutes": "20",
                "items-1-order": "2", "items-1-submission": self.p2.pk, "items-1-presentation": "poster",
                "items-1-presenter": "Cy Lee"}
        data.update(extra)
        return data

    def test_scientific_chair_builds_a_session(self):
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        self.assertEqual(self.client.get(reverse("programme:session_add", args=[35])).status_code, 200)
        response = self.client.post(reverse("programme:session_add", args=[35]), self.session_data())
        self.assertRedirects(response, reverse("programme:overview", args=[35]))
        session = Session.objects.get(code="3B")
        self.assertEqual([i.submission_id for i in session.items.all()], [self.p1.pk, self.p2.pk])
        self.assertEqual(session.people.get().name, "Ann Smith")
        self.assertContains(self.client.get(reverse("programme:overview", args=[35])), "Takt")

    def test_scientific_chair_cannot_use_the_industry_day(self):
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        response = self.client.post(reverse("programme:session_add", args=[35]),
                                    self.session_data(part=self.industry.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.exists())
        industry_session = self.session(part=self.industry, title="Site visit")
        response = self.client.get(reverse("programme:session", args=[35, industry_session.pk]))
        self.assertContains(response, "You can see this session but not edit it")
        self.client.post(reverse("programme:session", args=[35, industry_session.pk]), {"delete": "1"})
        self.assertTrue(Session.objects.filter(pk=industry_session.pk).exists())

    def test_organiser_keeps_locations_but_not_sessions(self):
        organiser = self.user("org", "IGLC 35 organisers")
        self.client.force_login(organiser)
        response = self.client.post(reverse("programme:location_add", args=[35]),
                                    {"name": "Aula", "map_url": "https://use.mazemap.com/#v=1", "sort_order": "0"})
        self.assertRedirects(response, reverse("programme:locations", args=[35]))
        self.assertTrue(Location.objects.filter(name="Aula").exists())
        self.assertNotEqual(self.client.get(reverse("programme:session_add", args=[35])).status_code, 200)

    def test_location_in_use_is_not_deleted(self):
        self.session()
        chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(chair)
        self.client.post(reverse("programme:location", args=[35, self.room_a.pk]), {"delete": "1"})
        self.assertTrue(Location.objects.filter(pk=self.room_a.pk).exists())
        self.client.post(reverse("programme:location", args=[35, self.room_b.pk]), {"delete": "1"})
        self.assertFalse(Location.objects.filter(pk=self.room_b.pk).exists())

    def test_add_papers_in_a_batch(self):
        session = self.session(kind=Session.Kind.POSTERS, code="P")
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        response = self.client.get(reverse("programme:papers", args=[35]))
        self.assertContains(response, "Takt in hospitals")
        self.assertNotContains(response, "Withdrawn one")
        self.client.post(reverse("programme:papers", args=[35]),
                         {"session": session.pk, "paper": [self.p1.pk, self.p2.pk, self.p3.pk]})
        items = list(session.items.all())
        self.assertEqual([i.submission_id for i in items], [self.p1.pk, self.p2.pk])
        self.assertEqual({i.presentation for i in items}, {"poster"})

    def test_settings_new_part_gets_a_group(self):
        chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(chair)
        parts = list(self.programme.parts.all())
        data = {"status": "provisional", "time_zone": "Europe/Berlin", "first_day": "2027-07-18",
                "last_day": "2027-07-23", "parts-TOTAL_FORMS": str(len(parts) + 1),
                "parts-INITIAL_FORMS": str(len(parts))}
        for i, part in enumerate(parts):
            data.update({f"parts-{i}-id": part.pk, f"parts-{i}-name": part.name, f"parts-{i}-kind": part.kind,
                         f"parts-{i}-colour": part.colour, f"parts-{i}-sort_order": part.sort_order,
                         f"parts-{i}-description": ""})
            if part.public:
                data[f"parts-{i}-public"] = "on"
        n = len(parts)
        data.update({f"parts-{n}-name": "Study tour", f"parts-{n}-kind": "other", f"parts-{n}-colour": "#123456",
                     f"parts-{n}-sort_order": "9", f"parts-{n}-description": ""})
        response = self.client.post(reverse("programme:settings", args=[35]), data)
        self.assertRedirects(response, reverse("programme:overview", args=[35]))
        self.assertEqual(Part.objects.get(name="Study tour").editors.name, "IGLC 35 Study tour editors")
        self.assertEqual(Programme.objects.get().status, "provisional")

    def test_scientific_chair_has_no_settings(self):
        self.client.force_login(self.user("sci", "IGLC 35 scientific chairs"))
        self.assertNotEqual(self.client.get(reverse("programme:settings", args=[35])).status_code, 200)


class PublicTests(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.page = ConferencePage.objects.child_of(self.home).get(slug="programme")
        self.page.body = [("programme", {"part": ""})]
        self.page.save_revision().publish()
        session = self.session(code="1A", title="Opening session")
        SessionItem.objects.create(session=session, submission=self.p1, presenter="Ann Smith")
        self.session(part=self.phd, title="Doctoral colloquium", location="b")

    def get(self):
        return self.client.get("/2027/programme/", **HOST)

    def test_hidden_until_published(self):
        response = self.get()
        self.assertNotContains(response, "Opening session")
        self.assertContains(response, "The programme will be published here.")

    def test_provisional_public_parts(self):
        Programme.objects.update(status=Programme.Status.PROVISIONAL)
        response = self.get()
        self.assertContains(response, "provisional")
        self.assertContains(response, "Opening session")
        self.assertContains(response, "Takt in hospitals")
        self.assertContains(response, "https://use.mazemap.com/x")
        self.assertNotContains(response, "Doctoral colloquium")

    def test_published_paper_is_linked(self):
        Programme.objects.update(status=Programme.Status.FINAL)
        paper = Paper.objects.create(title="Takt in Hospitals (published)", conference=self.conference)
        Author.objects.create(paper=paper, first_name="Ann", last_name="Smith", order=1)
        Submission.objects.filter(pk=self.p1.pk).update(paper=paper)
        response = self.get()
        self.assertContains(response, paper.get_absolute_url())
        self.assertContains(response, "Takt in Hospitals (published)")
        self.assertNotContains(response, "provisional")

    def test_standard_page_template_has_the_block(self):
        from apps.conferences.models import StandardPageTemplate

        template = StandardPageTemplate.objects.get(slug="programme")
        self.assertEqual([b.block_type for b in template.body], ["programme"])


class PublicPageTests(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        Programme.objects.update(status=Programme.Status.FINAL)
        self.page = ConferencePage.objects.child_of(self.home).get(slug="programme")
        self.page.body = [("programme", {"part": ""})]
        self.page.save_revision().publish()
        self.opening = self.session(start_at=time(9), end_at=time(10), title="Opening", kind=Session.Kind.KEYNOTE,
                                    plenary=True)
        self.a = self.session(code="1A", title="Takt", start_at=time(10, 30), end_at=time(12))
        self.b = self.session(code="1B", title="Last Planner", location="b", start_at=time(10, 30), end_at=time(12))
        SessionItem.objects.create(session=self.a, submission=self.p1, presenter="Ann Smith")
        SessionPerson.objects.create(session=self.a, name="Cy Lee", affiliation="NTNU")
        self.phd_session = self.session(part=self.phd, title="Doctoral colloquium", start_at=time(14), end_at=time(15))

    def get(self, path):
        return self.client.get(path, **HOST)

    def test_block_links_to_the_pages(self):
        response = self.get("/2027/programme/")
        self.assertContains(response, f'href="/2027/programme/session/{self.a.pk}/"')
        self.assertContains(response, 'href="/2027/programme/day/2027-07-20/"')
        self.assertContains(response, "conf-grid")
        self.assertNotContains(response, "Doctoral colloquium")

    def test_day(self):
        response = self.get("/2027/programme/day/2027-07-20/")
        self.assertContains(response, "Tuesday 20 July 2027")
        self.assertContains(response, "Last Planner")
        self.assertNotContains(response, "Doctoral colloquium")
        self.assertEqual(self.get("/2027/programme/day/2027-07-21/").status_code, 404)
        self.assertEqual(self.get("/2027/programme/day/nonsense/").status_code, 404)

    def test_session(self):
        response = self.get(f"/2027/programme/session/{self.a.pk}/")
        self.assertContains(response, "Takt in hospitals")
        self.assertContains(response, "Cy Lee, NTNU")
        self.assertContains(response, "https://use.mazemap.com/x")
        self.assertContains(response, "At the same time")
        self.assertContains(response, f'href="/2027/programme/session/{self.b.pk}/"')
        self.assertContains(response, "<title>1A Takt | IGLC 35</title>", html=False)

    def test_location(self):
        response = self.get(f"/2027/programme/location/{self.room_a.pk}/")
        self.assertContains(response, "Room A")
        self.assertContains(response, "Takt")
        self.assertContains(response, "Find it on the map")

    def test_private_part(self):
        self.assertEqual(self.get(f"/2027/programme/session/{self.phd_session.pk}/").status_code, 404)
        self.assertEqual(self.get(f"/2027/programme/part/{self.phd.pk}/").status_code, 404)
        response = self.get(f"/2027/programme/private/{self.phd.token}/")
        self.assertContains(response, "Doctoral colloquium")
        self.assertContains(response, '<meta name="robots" content="noindex">')
        self.assertNotContains(response, "Last Planner")
        link = f"/2027/programme/session/{self.phd_session.pk}/?k={self.phd.token}"
        self.assertContains(response, link)
        self.assertContains(self.get(link), "Doctoral colloquium")
        other = self.industry.token
        self.assertEqual(self.get(f"/2027/programme/session/{self.phd_session.pk}/?k={other}").status_code, 404)
        self.assertEqual(self.get(f"/2027/programme/session/{self.phd_session.pk}/?k=nonsense").status_code, 404)

    def test_public_part(self):
        industry = self.session(part=self.industry, title="Site visit", start_at=time(16), end_at=time(17))
        response = self.get(f"/2027/programme/part/{self.industry.pk}/")
        self.assertContains(response, "Site visit")
        self.assertNotContains(response, "Takt")
        self.assertContains(self.get(f"/2027/programme/session/{industry.pk}/"), "Site visit")

    def test_hidden_programme(self):
        Programme.objects.update(status=Programme.Status.HIDDEN)
        self.assertEqual(self.get(f"/2027/programme/session/{self.a.pk}/").status_code, 404)
        self.assertEqual(self.get("/2027/programme/day/2027-07-20/").status_code, 404)

    def test_grid(self):
        from .public import by_day

        day = by_day([self.opening, self.a, self.b])[0]
        grid = day.grid()
        self.assertEqual([loc.name for loc in grid["columns"]], ["Room A", "Room B"])
        placed = {p.session.pk: p for p in grid["placed"]}
        self.assertEqual(placed[self.opening.pk].column, "2 / -1")  # plenary, nothing beside it
        self.assertEqual(placed[self.a.pk].column, "2")
        self.assertEqual(placed[self.b.pk].column, "3")
        self.assertEqual(placed[self.a.pk].row, "4 / 5")  # rows: 09:00, 10:00, 10:30, 12:00

    def test_private_link_in_the_back_office(self):
        dean = self.user("dean", "IGLC 35 PhD summer school deans")
        self.client.force_login(dean)
        response = self.client.get(reverse("programme:overview", args=[35]))
        self.assertContains(response, f"/2027/programme/private/{self.phd.token}/")
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        self.assertNotContains(self.client.get(reverse("programme:overview", args=[35])), str(self.phd.token))
