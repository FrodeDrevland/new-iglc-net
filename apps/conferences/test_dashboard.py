"""The Conferences section of the back office: menu, list, dashboard, actions and deleting."""

from datetime import date

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase

from apps.archive.models import Conference, ConferenceTrack, Paper

from . import dashboard
from .models import ConferenceHomePage
from .setup import seed, sync_site


class DashboardTests(TestCase):
    def setUp(self):
        sync_site()
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)
        self.conference = Conference.objects.create(number=99, city="Sandbox", country="Norway",
                                                    start_date=date(2099, 6, 22), end_date=date(2099, 6, 26))
        ConferenceTrack.objects.create(conference=self.conference, title="Production planning", order=1)

    def url(self, action=None):
        base = f"/manage/conferences/{self.conference.pk}/"
        return f"{base}do/{action}/" if action else base

    # --- menu and list

    def test_menu_has_the_conferences_section(self):
        page = self.client.get("/manage/").content.decode()
        for label in ("Conferences", "All conferences", "Programmes", "Proceedings production",
                      "Website standard pages"):
            self.assertIn(label, page)

    def test_list_links_rows_to_the_dashboard(self):
        page = self.client.get("/manage/conferences/").content.decode()
        self.assertIn(f'href="/manage/conferences/{self.conference.pk}/"', page)
        self.assertIn("22–26 Jun 2099", page)
        self.assertIn("No website", page)

    def test_list_filters(self):
        seed(self.conference)
        other = Conference.objects.create(number=98, start_date=date(2001, 1, 1))
        page = self.client.get("/manage/conferences/?website=draft").content.decode()
        self.assertIn("IGLC 99", page)
        self.assertNotIn("IGLC 98", page)
        page = self.client.get("/manage/conferences/?when=past").content.decode()
        self.assertIn(f"/manage/conferences/{other.pk}/", page)
        self.assertNotIn(f"/manage/conferences/{self.conference.pk}/", page)

    def test_old_archive_urls_redirect(self):
        response = self.client.get(f"/manage/archive/conference/edit/{self.conference.pk}/")
        self.assertRedirects(response, f"/manage/conferences/edit/{self.conference.pk}/", status_code=301)

    # --- dashboard

    def test_dashboard_without_a_website(self):
        page = self.client.get(self.url()).content.decode()
        self.assertIn("IGLC 99: Sandbox, Norway", page)
        self.assertIn("Production planning", page)
        self.assertIn("Create the website", page)

    def test_dashboard_needs_permission(self):
        editor = User.objects.create_user("ed", "ed@example.com", "pw")
        editor.groups.add(Group.objects.get(name="Editors"))
        self.client.force_login(editor)
        # Wagtail's admin turns PermissionDenied into a redirect to its dashboard, with a message
        self.assertNotEqual(self.client.get(self.url()).status_code, 200)
        self.client.post(self.url("create-website"))
        self.assertFalse(ConferenceHomePage.objects.filter(conference=self.conference).exists())

    # --- the website

    def test_create_publish_current_freeze_unpublish(self):
        self.assertContains(self.client.get(self.url("create-website")), "Create the website")
        self.client.post(self.url("create-website"))
        home = ConferenceHomePage.objects.get(conference=self.conference)
        self.assertFalse(home.live)
        self.assertEqual(home.slug, "2099")
        self.assertTrue(Group.objects.filter(name="IGLC 99 organisers").exists())
        self.assertEqual(dashboard.website_state(home), "draft")

        # publish only the home page and the call for papers
        cfp = home.get_children().get(slug="call-for-papers")
        page = self.client.get(self.url("publish-website")).content.decode()
        self.assertIn("Call for papers", page)
        self.client.post(self.url("publish-website"), {"page": [cfp.pk]})  # the home page comes with it
        home.refresh_from_db()
        cfp.refresh_from_db()
        self.assertTrue(home.live and cfp.live)
        self.assertFalse(home.get_children().get(slug="sponsors").live)

        # current: on the page and on its revisions, so publishing a draft later keeps it
        older = Conference.objects.create(number=98, start_date=date(2098, 6, 1))
        older_home = seed(older, current=True, publish=True)
        self.client.post(self.url("make-current"))
        home.refresh_from_db()
        older_home.refresh_from_db()
        self.assertTrue(home.is_current)
        self.assertFalse(older_home.is_current)
        self.assertTrue(home.latest_revision.content["is_current"])
        older_home.latest_revision.publish()
        self.assertTrue(ConferenceHomePage.objects.get(pk=home.pk).is_current)

        self.client.post(self.url("freeze"))
        home.refresh_from_db()
        self.assertTrue(home.frozen)
        self.assertEqual(self.client.post(self.url("unpublish-website")).status_code, 302)
        home.refresh_from_db()
        self.assertTrue(home.live)  # refused while frozen
        self.client.post(self.url("unfreeze"))
        self.client.post(self.url("unpublish-website"))
        home.refresh_from_db()
        cfp.refresh_from_db()
        self.assertFalse(home.live or cfp.live)

    def test_create_website_needs_dates(self):
        undated = Conference.objects.create(number=97)
        self.client.post(f"/manage/conferences/{undated.pk}/do/create-website/")
        self.assertFalse(ConferenceHomePage.objects.filter(conference=undated).exists())

    def test_archive_toggle(self):
        self.client.post(self.url("show-in-archive"))
        self.conference.refresh_from_db()
        self.assertTrue(self.conference.is_published)
        self.client.post(self.url("hide-in-archive"))
        self.conference.refresh_from_db()
        self.assertFalse(self.conference.is_published)

    def test_start_programme(self):
        response = self.client.post(self.url("start-programme"), {"time_zone": "Nowhere/Nothing"})
        self.assertEqual(response.status_code, 200)  # the form again, with the error
        self.client.post(self.url("start-programme"), {"time_zone": "Europe/Oslo"})
        self.assertEqual(self.conference.programme.time_zone, "Europe/Oslo")

    # --- organisers

    def test_add_invite_and_remove_organisers(self):
        seed(self.conference)
        someone = User.objects.create_user("someone", "someone@example.com", "pw")
        self.client.post(self.url("add-organiser"), {"user": someone.pk})
        self.assertTrue(someone.groups.filter(name="IGLC 99 organisers").exists())
        self.client.post(self.url("invite-organiser"),
                         {"first_name": "Ada", "last_name": "Lovelace", "email": "Ada@Example.com"})
        ada = User.objects.get(username="ada@example.com")
        self.assertTrue(ada.groups.filter(name="IGLC 99 organisers").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("IGLC 99", mail.outbox[0].subject)
        self.assertIn("/manage/password_reset/confirm/", mail.outbox[0].body)
        # the same address again is refused
        self.client.post(self.url("invite-organiser"),
                         {"first_name": "Ada", "last_name": "L", "email": "ada@example.com"})
        self.assertEqual(User.objects.filter(email__iexact="ada@example.com").count(), 1)
        self.client.post(self.url("remove-organiser"), {"user": someone.pk})
        self.assertFalse(someone.groups.filter(name="IGLC 99 organisers").exists())

    # --- deleting

    def test_delete_takes_the_draft_website_with_it(self):
        seed(self.conference)
        from apps.programme import setup as programme_setup
        from apps.programme.models import Session

        programme = programme_setup.start(self.conference, "Europe/Oslo")
        Session.objects.create(programme=programme, part=programme.parts.first(), date=date(2099, 6, 22),
                               start="09:00", end="10:00", title="Opening")
        page = self.client.get(f"/manage/conferences/delete/{self.conference.pk}/").content.decode()
        self.assertIn("also deletes", page)
        self.assertIn("1 session", page)
        response = self.client.post(f"/manage/conferences/delete/{self.conference.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Conference.objects.filter(number=99).exists())
        self.assertFalse(ConferenceHomePage.objects.filter(slug="2099").exists())
        self.assertFalse(Group.objects.filter(name="IGLC 99 organisers").exists())
        from wagtail.models import Page

        self.assertFalse(any(Page.find_problems()))  # the page tree is consistent
        self.assertFalse(Page.objects.filter(slug="call-for-papers", url_path__contains="/2099/").exists())

    def test_delete_is_refused_with_papers_or_a_published_site(self):
        seed(self.conference, publish=True)
        page = self.client.get(f"/manage/conferences/delete/{self.conference.pk}/").content.decode()
        self.assertIn("cannot be deleted", page)
        self.assertIn("Unpublish it first", page)
        self.client.post(f"/manage/conferences/delete/{self.conference.pk}/")
        self.assertTrue(Conference.objects.filter(number=99).exists())

        other = Conference.objects.create(number=96, start_date=date(2096, 1, 1))
        Paper.objects.create(conference=other, title="A paper")
        self.client.post(f"/manage/conferences/delete/{other.pk}/")
        self.assertTrue(Conference.objects.filter(number=96).exists())
