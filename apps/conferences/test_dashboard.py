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
        base = f"/manage/{self.conference.number}/"
        return f"{base}do/{action}/" if action else base

    # --- menu and list

    def test_menu_has_the_conferences_section(self):
        page = self.client.get("/manage/").content.decode()
        for label in ("Conferences", "All conferences", "Programmes", "Proceedings production",
                      "Website standard pages"):
            self.assertIn(label, page)

    def test_list_links_rows_to_the_dashboard(self):
        page = self.client.get("/manage/conferences/").content.decode()
        self.assertIn('href="/manage/99/"', page)
        self.assertIn("22–26 Jun 2099", page)
        self.assertIn("No website", page)

    def test_list_filters(self):
        seed(self.conference)
        other = Conference.objects.create(number=98, start_date=date(2001, 1, 1))
        page = self.client.get("/manage/conferences/?website=draft").content.decode()
        self.assertIn('href="/manage/99/"', page)
        self.assertNotIn('href="/manage/98/"', page)
        page = self.client.get("/manage/conferences/?when=past").content.decode()
        self.assertIn('href="/manage/98/"', page)
        self.assertNotIn('href="/manage/99/"', page)

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
        self.client.post("/manage/97/do/create-website/")
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

    # --- people and roles

    def test_add_and_remove_people_by_email(self):
        seed(self.conference)
        someone = User.objects.create_user("someone", "someone@example.com", "pw")
        self.client.post(self.url("add-person"), {"role": "organisers", "email": "SOMEONE@example.com"})
        self.assertTrue(someone.groups.filter(name="IGLC 99 organisers").exists())
        self.assertEqual(len(mail.outbox), 0)  # an existing account gets no e-mail
        self.client.post(self.url("add-person"), {"role": "chairs", "email": "Ada@Example.com",
                                                  "first_name": "Ada", "last_name": "Lovelace"})
        ada = User.objects.get(username="ada@example.com")
        self.assertTrue(ada.groups.filter(name="IGLC 99 conference chairs").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("IGLC 99", mail.outbox[0].subject)
        self.assertIn("conference chairs", mail.outbox[0].body)
        self.assertIn("/manage/password_reset/confirm/", mail.outbox[0].body)
        self.client.post(self.url("remove-person"), {"role": "organisers", "user": someone.pk})
        self.assertFalse(someone.groups.filter(name="IGLC 99 organisers").exists())

    def _person(self, name, role):
        user = User.objects.create_user(name, f"{name}@example.com", "pw")
        user.groups.add(Group.objects.get(name=f"IGLC 99 {role}"))
        return user

    def test_chairs_and_organisers_edit_the_website_and_see_the_dashboard(self):
        home = seed(self.conference)
        from apps.programme import setup as programme_setup

        programme_setup.start(self.conference, "Europe/Oslo")
        chair, organiser = self._person("chair", "conference chairs"), self._person("org", "organisers")
        scientific = self._person("sci", "scientific chairs")
        cfp = home.get_children().get(slug="call-for-papers")
        for user in (chair, organiser):
            self.assertTrue(cfp.permissions_for_user(user).can_publish(), user)
        self.assertFalse(cfp.permissions_for_user(scientific).can_edit())

        for user in (chair, organiser, scientific):
            self.client.force_login(user)
            page = self.client.get(self.url())
            self.assertEqual(page.status_code, 200, user)
            self.assertNotContains(page, "Delete IGLC 99")
            self.assertNotContains(self.client.get(self.url() + "people/"), "Mark as current")
            # /manage/ leads to the conference
            self.assertRedirects(self.client.get("/manage/"), self.url())
            # never the IGLC's own actions
            self.client.post(self.url("freeze"))
            self.assertFalse(ConferenceHomePage.objects.get(pk=home.pk).frozen)

        self.client.force_login(organiser)
        self.assertContains(self.client.get(self.url() + "website/"), "Save draft")
        self.assertNotContains(self.client.get(self.url() + "website/"), "Mark as current")
        self.client.post(self.url("add-person"), {"role": "organisers", "email": "x@example.com"})
        self.assertFalse(User.objects.filter(email="x@example.com").exists())  # organisers do not add people
        self.client.post(self.url("publish-website"), {"page": [cfp.pk]})
        cfp.refresh_from_db()
        self.assertTrue(cfp.live)

        self.client.force_login(chair)
        self.client.post(self.url("add-person"), {"role": "organisers", "email": "new@example.com"})
        self.assertTrue(User.objects.get(email="new@example.com").groups.filter(name="IGLC 99 organisers").exists())
        self.client.post(self.url("add-person"), {"role": "chairs", "email": "chair2@example.com"})
        self.assertFalse(User.objects.filter(email="chair2@example.com").exists())  # only the IGLC adds chairs
        part = self.conference.programme.parts.get(kind="industry")
        self.client.post(self.url("add-person"), {"role": f"part-{part.pk}", "email": "ind@example.com"})
        self.assertTrue(User.objects.get(email="ind@example.com").groups.filter(
            name="IGLC 99 industry day chairs").exists())

        self.client.force_login(scientific)
        self.client.post(self.url("publish-website"), {"page": [home.get_children().get(slug="sponsors").pk]})
        self.assertFalse(home.get_children().get(slug="sponsors").live)

    def test_other_conferences_stay_closed(self):
        seed(self.conference)
        other = Conference.objects.create(number=98, start_date=date(2098, 6, 1))
        seed(other)
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        self.assertNotEqual(self.client.get("/manage/98/").status_code, 200)
        self.assertNotEqual(self.client.get("/manage/conferences/").status_code, 200)

    def test_the_page_tree_leads_to_the_website_page(self):
        home = seed(self.conference)
        cfp = home.get_children().get(slug="call-for-papers")
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        for page in (cfp, home):
            self.assertRedirects(self.client.get(f"/manage/pages/{page.pk}/"), "/manage/99/website/")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f"/manage/pages/{cfp.pk}/").status_code, 200)  # superusers: the tree

    def test_publishing_in_the_editor_comes_back_to_the_website_page(self):
        home = seed(self.conference)
        cfp = home.get_children().get(slug="call-for-papers").specific
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        form = self.client.get(f"/manage/pages/{cfp.pk}/edit/")
        self.assertEqual(form.status_code, 200)
        from wagtail.test.utils.form_data import inline_formset, nested_form_data, rich_text, streamfield

        data = nested_form_data({"title": "Call for papers", "slug": "call-for-papers", "intro": "Topics.",
                                 "body": streamfield([("text", rich_text("<p>Send us papers.</p>"))]),
                                 "comments": inline_formset([]), "action-publish": "action-publish"})
        response = self.client.post(f"/manage/pages/{cfp.pk}/edit/", data)
        self.assertRedirects(response, "/manage/99/website/", fetch_redirect_response=False)
        cfp.refresh_from_db()
        self.assertTrue(cfp.live)

    def test_the_sidebar_inside_a_conference(self):
        seed(self.conference)
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        page = self.client.get(self.url()).content.decode()
        for label in ("Overview", "Website", "Branding", "People", "IGLC 99: Sandbox"):
            self.assertIn(label, page)
        for label in ('"Reports"', '"Settings"', "IGLC admin", "All conferences"):
            self.assertNotIn(label, page)
        self.client.force_login(self.admin)
        page = self.client.get(self.url()).content.decode()
        self.assertIn("IGLC admin", page)  # the way back to the full menu
        page = self.client.get("/manage/").content.decode()
        self.assertIn("All conferences", page)
        self.assertLess(page.index('"Pages"'), page.index('"Images"'))  # the full menu in its own order

    def test_branding(self):
        home = seed(self.conference, publish=True)
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        self.assertContains(self.client.get(self.url() + "branding/"), "Save and publish")
        data = {"primary_colour": "#ffff00", "accent_colour": "#d4772a", "heading_font": "sans"}
        self.assertContains(self.client.post(self.url() + "branding/", data), "hard to read")
        data["primary_colour"] = "#204060"
        self.client.post(self.url() + "branding/", data)  # a draft
        home.refresh_from_db()
        self.assertEqual(home.primary_colour, "#365a91")
        self.assertEqual(home.get_latest_revision_as_object().primary_colour, "#204060")
        self.client.post(self.url() + "branding/", dict(data, publish="1"))
        home.refresh_from_db()
        self.assertEqual((home.primary_colour, home.heading_font), ("#204060", "sans"))

    def test_scientific_chairs_edit_the_proceedings(self):
        from apps.production.access import productions_for, role
        from apps.production.models import Production

        production = Production.objects.create(conference=self.conference)
        other = Production.objects.create(conference=Conference.objects.create(number=98, start_date=date(2098, 1, 1)))
        self.client.post(self.url("add-person"), {"role": "scientific", "email": "sci@example.com"})
        sci = User.objects.get(email="sci@example.com")
        self.assertEqual(role(sci, production), "chief")
        self.assertIsNone(role(sci, other))
        self.assertEqual(list(productions_for(sci)), [production])
        self.client.force_login(sci)
        self.assertEqual(self.client.get("/manage/production/99/").status_code, 200)
        self.assertNotEqual(self.client.get("/manage/production/98/").status_code, 200)
        self.assertIn("Proceedings", self.client.get(self.url()).content.decode())

    def test_existing_sites_get_chairs_with_website_rights(self):
        """What migration 0007 does, through the setup code: both groups edit the website."""
        home = seed(self.conference)
        chairs = Group.objects.get(name="IGLC 99 conference chairs")
        from wagtail.models import GroupPagePermission

        self.assertEqual(set(GroupPagePermission.objects.filter(group=chairs, page=home)
                             .values_list("permission__codename", flat=True)),
                         {"add_page", "change_page", "publish_page"})

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
        self.assertFalse(Group.objects.filter(name__startswith="IGLC 99 ").exists())
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
