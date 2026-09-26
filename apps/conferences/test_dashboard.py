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
        for label in ("Overview", "Website", "Dates and links", "Committees", "Branding", "People", "IGLC 99: Sandbox"):
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
        data = {"primary_colour": "#12345g", "accent_colour": "#d4772a", "heading_font": "sans"}
        self.assertContains(self.client.post(self.url() + "branding/", data), "six hexadecimal digits")
        data["primary_colour"] = "#204060"
        self.client.post(self.url() + "branding/", data)  # a draft
        home.refresh_from_db()
        self.assertEqual(home.primary_colour, "#365a91")
        self.assertEqual(home.get_latest_revision_as_object().primary_colour, "#204060")
        self.client.post(self.url() + "branding/", dict(data, publish="1"))
        home.refresh_from_db()
        self.assertEqual((home.primary_colour, home.heading_font), ("#204060", "sans"))

    def test_previews(self):
        home = seed(self.conference)  # all drafts
        cfp = home.get_children().get(slug="call-for-papers")
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        self.assertContains(self.client.get(self.url() + "website/"), f"/manage/pages/{cfp.pk}/view_draft/")
        draft = self.client.get(f"/manage/pages/{home.pk}/view_draft/").content.decode()
        # the draft pages are in the menu, linking to their drafts
        self.assertIn("Call for papers", draft)
        self.assertIn(f"/manage/pages/{cfp.pk}/view_draft/", draft)
        self.assertIn("iglc-logo-symbol-white.svg", draft)  # no conference logo yet
        # branding: the home page with unsaved settings
        data = {"primary_colour": "#204060", "accent_colour": "#d4772a", "heading_font": "sans"}
        self.assertContains(self.client.post(self.url() + "branding/preview/", data), "#204060")
        self.assertEqual(home.get_latest_revision_as_object().primary_colour, "#365a91")  # nothing saved
        self.assertContains(self.client.post(self.url() + "branding/preview/", dict(data, primary_colour="#1234")),
                            "cannot be shown")
        # a light main colour: black text and the black IGLC symbol in the header
        light = self.client.post(self.url() + "branding/preview/", dict(data, primary_colour="#f0e060")).content.decode()
        self.assertIn("--conf-on-primary: #000000", light)
        self.assertIn("iglc-logo-symbol-black.svg", light)

    def test_the_live_menu_has_only_published_pages(self):
        home = seed(self.conference)
        cfp = home.get_children().get(slug="call-for-papers")
        home.save_revision().publish()
        cfp.specific.save_revision().publish()
        page = self.client.get("/2099/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn('href="/2099/call-for-papers/"', page)
        self.assertNotIn("Sponsors", page)
        self.assertNotIn("view_draft", page)

    def test_photograph_size(self):
        from wagtail.images import get_image_model
        from wagtail.images.tests.utils import get_test_image_file

        from .workspace_views import hero_note

        home = seed(self.conference, publish=True)
        page = self.client.get(self.url() + "branding/").content.decode()
        self.assertIn("1600 × 600 pixels", page)
        Image = get_image_model()
        tall = Image.objects.create(title="Tall", file=get_test_image_file(size=(800, 800)))
        self.assertIn("taller than 8:3", hero_note(tall))
        self.assertIn("narrower than 1600", hero_note(tall))
        right = Image.objects.create(title="Right", file=get_test_image_file(size=(1600, 600)))
        self.assertEqual(hero_note(right), "")
        right.focal_point_x, right.focal_point_y, right.focal_point_width, right.focal_point_height = 400, 300, 10, 10
        right.save()
        self.client.post(self.url() + "branding/", {"hero_image": right.pk, "primary_colour": "#365a91",
                                                     "accent_colour": "#d4772a", "heading_font": "serif",
                                                     "publish": "1"})
        page = self.client.get("/2099/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("object-position: 25% 50%", page)

    def test_dates_and_links(self):
        home = seed(self.conference, publish=True)
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        page = self.client.get(self.url() + "dates/")
        self.assertContains(page, "Conference")
        existing = home.important_dates.get()
        data = {"dates-TOTAL_FORMS": "4", "dates-INITIAL_FORMS": "1", "dates-MIN_NUM_FORMS": "0",
                "dates-MAX_NUM_FORMS": "1000",
                "dates-0-id": existing.pk, "dates-0-label": "Conference", "dates-0-date": "2099-06-22",
                "dates-0-end_date": "2099-06-26",
                "dates-1-label": "Full papers due", "dates-1-date": "2099-02-01", "dates-1-original_date": "2099-01-15",
                "dates-2-label": "", "dates-3-label": "",
                "registration_url": "https://example.org/register", "contact_email": "iglc99@example.org"}
        self.client.post(self.url() + "dates/", data)  # a draft
        home.refresh_from_db()
        self.assertEqual(home.registration_url, "")
        draft = home.get_latest_revision_as_object()
        self.assertEqual([d.label for d in draft.important_dates.all()], ["Full papers due", "Conference"])
        self.client.post(self.url() + "dates/", dict(data, publish="1"))
        site = self.client.get("/2099/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("Full papers due", site)
        self.assertIn("https://example.org/register", site)
        # the contact is the conference's, above the IGLC's footer
        self.assertIn("Write to the organisers", site)
        self.assertLess(site.index("iglc99@example.org"), site.index('class="conf-footer"'))
        # and no longer in the home page's editor
        editor = self.client.get(f"/manage/pages/{home.pk}/edit/").content.decode()
        self.assertNotIn('name="registration_url"', editor)
        self.assertNotIn("important_dates-TOTAL_FORMS", editor)
        self.assertIn("Dates and links", editor)

    def test_preview_buttons_only_for_unpublished_changes(self):
        home = seed(self.conference)
        cfp = home.get_children().get(slug="call-for-papers")
        home.save_revision().publish()
        cfp.specific.save_revision().publish()
        page = self.client.get(self.url() + "website/").content.decode()
        self.assertNotIn(f"/manage/pages/{cfp.pk}/view_draft/", page)
        self.assertNotIn(f"/manage/pages/{home.pk}/view_draft/", page)
        sponsors = home.get_children().get(slug="sponsors")
        self.assertIn(f"/manage/pages/{sponsors.pk}/view_draft/", page)

    def test_logos(self):
        from wagtail.images import get_image_model
        from wagtail.images.tests.utils import get_test_image_file

        Image = get_image_model()
        wide = Image.objects.create(title="Header logo", file=get_test_image_file(size=(600, 160)))
        stacked = Image.objects.create(title="Stacked logo", file=get_test_image_file(size=(500, 400)))
        light = Image.objects.create(title="Colour logo", file=get_test_image_file(size=(600, 160)))
        icon = Image.objects.create(title="Icon", file=get_test_image_file(size=(300, 200)))
        photo = Image.objects.create(title="Photo", file=get_test_image_file(size=(1600, 600)))
        home = seed(self.conference, publish=True)
        site = self.client.get("/2099/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("iglc-logo-symbol-white.svg", site)
        self.assertIn('class="conf-name"', site)
        self.assertIn("<h1>", site)
        page = self.client.get(self.url() + "branding/").content.decode()
        for label in ("Logo on the photograph", "Logo in the header", "Logo on light backgrounds", "Icon",
                      "Darken the photograph"):
            self.assertIn(label, page)
        data = {"hero_image": photo.pk, "hero_logo": stacked.pk, "logo": wide.pk, "logo_on_light": light.pk,
                "icon": icon.pk, "primary_colour": "#365a91", "accent_colour": "#d4772a", "heading_font": "serif",
                "publish": "1"}  # "darken" left unticked
        self.client.post(self.url() + "branding/", data)
        self.assertIn("not square", self.client.get(self.url() + "branding/").content.decode())
        site = self.client.get("/2099/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("conf-hero-logo", site)
        self.assertIn('<h1 class="visually-hidden">', site)
        self.assertNotIn("darkened", site)
        self.assertNotIn('class="conf-name"', site)  # the header logo carries the name
        self.assertIn('rel="apple-touch-icon"', site)
        self.assertIn('property="og:image"', site)
        self.conference.is_published = True
        self.conference.save()
        archive = self.client.get(f"/papers/conference/{self.conference.pk}").content.decode()
        self.assertIn("conf-head-logo", archive)

    def test_committees_with_portraits(self):
        from wagtail.images import get_image_model
        from wagtail.images.tests.utils import get_test_image_file

        from .models import CommitteeMember

        home = seed(self.conference, publish=True)
        page = home.get_children().get(slug="committees").specific
        photo = get_image_model().objects.create(title="Portrait", file=get_test_image_file(size=(400, 400)))
        page.members = [
            CommitteeMember(committee="Organising committee", name="Anna Müller", role="Chair", photo=photo),
            CommitteeMember(committee="Organising committee", name="Jonas Weber", url="https://example.org/jw"),
            CommitteeMember(committee="Scientific committee", name="Lauri Koskela", affiliation="Huddersfield"),
        ]
        page.save_revision().publish()
        html = self.client.get("/2099/committees/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn('class="conf-portraits"', html)          # a committee with a photograph: cards
        self.assertIn(">JW<", html)                              # initials for the one without
        self.assertIn('href="https://example.org/jw"', html)
        self.assertIn('class="conf-members"', html)             # nobody with a photograph: a compact list
        self.assertLess(html.index("Organising committee"), html.index("Scientific committee"))

    def test_committees_in_the_workspace(self):
        home = seed(self.conference, publish=True)
        page = home.get_children().get(slug="committees").specific
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        url = self.url() + "committees/"
        self.assertContains(self.client.get(url), "No members yet")
        self.client.post(url, {"action": "add", "add-committee": "Organising committee", "add-name": "Anna Müller",
                               "add-role": "Conference chair", "add-affiliation": "TUM", "add-country": "Germany"})
        self.client.post(url, {"action": "bulk", "bulk-committee": "Scientific committee",
                               "bulk-lines": "Lauri Koskela; University of Huddersfield; UK\n"
                                             "Glenn Ballard\tUC Berkeley\tUSA\n\nIris Tommelein"})
        self.client.post(url, {"action": "add", "add-committee": "Organising committee", "add-name": "Jonas Weber"})
        from .models import CommitteesPage

        def draft():
            return CommitteesPage.objects.get(pk=page.pk).get_latest_revision_as_object()

        names = lambda: [m.name for m in draft().members.all()]  # noqa: E731
        # Jonas goes to the end of his committee, before the scientific committee
        self.assertEqual(names(), ["Anna Müller", "Jonas Weber", "Lauri Koskela", "Glenn Ballard", "Iris Tommelein"])
        members = draft().members.all()
        self.assertEqual((members[3].affiliation, members[3].country), ("UC Berkeley", "USA"))
        self.client.post(url, {"action": "up", "index": 1, "name_was": "Jonas Weber"})
        self.assertEqual(names()[:2], ["Jonas Weber", "Anna Müller"])
        self.client.post(url, {"action": "remove", "index": 4, "name_was": "Someone else"})  # stale: nothing
        self.assertEqual(len(names()), 5)
        self.client.post(url, {"action": "remove", "index": 4, "name_was": "Iris Tommelein"})
        self.client.post(url, {"action": "committee-up", "committee": "Scientific committee"})
        self.assertEqual(names(), ["Lauri Koskela", "Glenn Ballard", "Jonas Weber", "Anna Müller"])
        self.client.post(url + "1/", {"name_was": "Glenn Ballard", "committee": "Scientific committee",
                                      "name": "Glenn Ballard", "role": "Honorary member", "affiliation": "UC Berkeley"})
        self.assertEqual(draft().members.all()[1].role, "Honorary member")
        # all drafts until published
        live = self.client.get("/2099/committees/", HTTP_HOST="conference.localhost").content.decode()
        self.assertNotIn("Glenn Ballard", live)
        overview = self.client.get(url).content.decode()
        self.assertIn("Changes not yet published", overview)
        self.client.post(url, {"action": "publish"})
        live = self.client.get("/2099/committees/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("Honorary member", live)
        self.assertLess(live.index("Scientific committee"), live.index("Organising committee"))
        # layouts
        self.assertNotIn("conf-committee-columns", live)
        self.client.post(url, {"action": "layout", "layout": "columns"})
        self.client.post(url, {"action": "publish"})
        live = self.client.get("/2099/committees/", HTTP_HOST="conference.localhost").content.decode()
        self.assertIn("conf-committee-columns", live)
        self.assertIn("conf-row-photo", live)
        self.client.post(url, {"action": "layout", "layout": "compact"})
        self.client.post(url, {"action": "publish"})
        live = self.client.get("/2099/committees/", HTTP_HOST="conference.localhost").content.decode()
        self.assertNotIn("conf-row-photo", live)
        self.assertIn("Honorary member", live)
        # the page editor no longer has the long list
        self.assertNotIn("members-TOTAL_FORMS", self.client.get(f"/manage/pages/{page.pk}/edit/").content.decode())
        # part chairs do not edit the website
        from . import roles as conference_roles

        conference_roles.group(self.conference, conference_roles.SCIENTIFIC, create=True)
        self.client.force_login(self._person("sci", "scientific chairs"))
        self.assertNotEqual(self.client.get(url).status_code, 200)

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

    def test_editorial_assistants(self):
        from apps.production.access import chief_editors, productions_for, role, submissions_for
        from apps.production.models import Production

        production = Production.objects.create(conference=self.conference)
        self.client.post(self.url("add-person"), {"role": "scientific", "email": "sci@example.com"})
        self.client.post(self.url("add-person"), {"role": "chairs", "email": "chair@example.com"})
        sci = User.objects.get(email="sci@example.com")
        chair = User.objects.get(email="chair@example.com")
        self.assertEqual(list(chief_editors(production)), [sci])

        # the conference chairs cannot add editorial assistants; the scientific chairs can
        self.client.force_login(chair)
        self.client.post(self.url("add-person"), {"role": "assistants", "email": "x@example.com"})
        self.assertFalse(User.objects.filter(email="x@example.com").exists())
        self.client.force_login(sci)
        people = self.client.get(self.url() + "people/").content.decode()
        self.assertIn("Editorial assistants", people)
        self.assertNotIn("Proceedings editors", people)
        self.client.post(self.url("add-person"), {"role": "assistants", "email": "assistant@example.com"})
        assistant = User.objects.get(email="assistant@example.com")
        self.assertTrue(assistant.groups.filter(name="IGLC 99 editorial assistants").exists())
        self.assertIn("editorial assistants", mail.outbox[-1].body)
        # scientific chairs cannot add organisers
        self.client.post(self.url("add-person"), {"role": "organisers", "email": "y@example.com"})
        self.assertFalse(User.objects.filter(email="y@example.com").exists())

        # the assistant edits the papers, but is not a chief editor and not a scientific chair
        self.assertEqual(role(assistant, production), "editor")
        self.assertEqual(list(productions_for(assistant)), [production])
        self.assertEqual(submissions_for(assistant, production).query.__str__(),
                         production.submissions.select_related("track", "editor").query.__str__())
        self.assertNotIn(assistant, chief_editors(production))
        self.client.force_login(assistant)
        self.assertEqual(self.client.get("/manage/production/99/").status_code, 200)
        self.assertNotIn('"url": "/manage/99/tracks/"', self.client.get(self.url()).content.decode())

    def test_scientific_chairs_decide_the_tracks(self):
        from apps.production.models import Production, Submission

        seed(self.conference)
        self.client.post(self.url("add-person"), {"role": "scientific", "email": "sci@example.com"})
        sci = User.objects.get(email="sci@example.com")
        planning = self.conference.tracks.get()
        used = ConferenceTrack.objects.create(conference=self.conference, title="Used", order=2)
        production = Production.objects.create(conference=self.conference)
        Submission.objects.create(production=production, conftool_id=1, title="A paper", track=used)

        # organisers see the tracks but cannot change them
        organiser = self._person("org", "organisers")
        self.client.force_login(organiser)
        self.assertEqual(self.client.get(self.url() + "tracks/").status_code, 200)
        self.assertNotEqual(self.client.post(self.url() + "tracks/", {}).status_code, 200)

        self.client.force_login(sci)
        page = self.client.get(self.url() + "tracks/").content.decode()
        self.assertIn('"url": "/manage/99/tracks/"', page)  # in the sidebar
        self.assertIn("in use", page)

        def data(rows, **extra):
            post = {"tracks-TOTAL_FORMS": str(len(rows)), "tracks-INITIAL_FORMS": str(sum(1 for r in rows if r.get("id"))),
                    "tracks-MIN_NUM_FORMS": "0", "tracks-MAX_NUM_FORMS": "1000"}
            for i, row in enumerate(rows):
                for key, value in row.items():
                    post[f"tracks-{i}-{key}"] = value
            post.update(extra)
            return post

        rows = [{"id": planning.pk, "title": "Planning and control", "description": ""},
                {"id": used.pk, "title": "Used", "description": ""},
                {"title": "Digital construction", "description": "BIM and more"},
                {"title": "", "description": ""}]
        self.client.post(self.url() + "tracks/", data(rows))
        titles = list(self.conference.tracks.order_by("order").values_list("title", flat=True))
        self.assertEqual(titles, ["Planning and control", "Used", "Digital construction"])

        new = self.conference.tracks.get(title="Digital construction")
        rows = [{"id": planning.pk, "title": "Planning and control"}, {"id": used.pk, "title": "Used"},
                {"id": new.pk, "title": "Digital construction"}]
        self.client.post(self.url() + "tracks/", data(rows, move="tracks-2:up"))
        titles = list(self.conference.tracks.order_by("order").values_list("title", flat=True))
        self.assertEqual(titles, ["Planning and control", "Digital construction", "Used"])

        # a track in use cannot be removed; an unused one can
        rows[1]["DELETE"] = "on"
        response = self.client.post(self.url() + "tracks/", data(rows))
        self.assertContains(response, "cannot be removed")
        self.assertTrue(ConferenceTrack.objects.filter(pk=used.pk).exists())
        del rows[1]["DELETE"]
        rows[2]["DELETE"] = "on"
        self.client.post(self.url() + "tracks/", data(rows))
        self.assertFalse(ConferenceTrack.objects.filter(pk=new.pk).exists())

        # not after the proceedings are in the archive
        Conference.objects.filter(pk=self.conference.pk).update(is_published=True)
        rows[0]["title"] = "Too late"
        self.client.post(self.url() + "tracks/", data(rows[:2]))
        self.assertFalse(ConferenceTrack.objects.filter(title="Too late").exists())

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
