from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from wagtail.models import Site

from apps.archive.models import Conference, ConferenceTrack
from apps.production.models import Production, Submission

from .models import CommitteesPage, ImportantDate, ConferenceHomePage, ConferencePage, contrast
from .setup import seed, sync_site
from .templatetags.conference_tags import date_range

HOST = {"HTTP_HOST": "conference.localhost"}


class ConferenceSiteTests(TestCase):
    def setUp(self):
        sync_site()
        self.conference = Conference.objects.create(number=35, city="Munich", country="Germany",
                                                    start_date=date(2027, 7, 19), end_date=date(2027, 7, 23))
        self.home = seed(self.conference, current=True, publish=True)

    def get(self, path, **extra):
        return self.client.get(path, **HOST, **extra)

    def test_site_follows_the_setting(self):
        site = Site.objects.get(hostname="conference.localhost")
        self.assertEqual(site.root_page.specific.__class__.__name__, "ConferenceIndexPage")
        sync_site()
        self.assertEqual(Site.objects.filter(hostname="conference.localhost").count(), 1)

    def test_seed_makes_the_standard_pages_and_is_repeatable(self):
        slugs = set(self.home.get_children().values_list("slug", flat=True))
        self.assertTrue({"call-for-papers", "important-dates", "programme", "committees", "accepted-papers",
                         "venue-and-travel", "registration", "sponsors", "keynotes"} <= slugs)
        seed(self.conference)
        self.assertEqual(self.home.get_children().count(), len(slugs))
        self.assertEqual(self.home.slug, "2027")

    def test_current_conference_at_the_root_and_its_year(self):
        response = self.get("/")
        self.assertContains(response, "IGLC 35")
        self.assertContains(response, 'rel="canonical" href="http://conference.localhost:8000/2027/"')
        self.assertContains(response, "19–23 July 2027")
        self.assertContains(response, "<th scope=\"row\">Conference")
        self.assertEqual(self.get("/2027/").status_code, 200)
        self.assertEqual(self.get("/2027/call-for-papers/").status_code, 200)

    def test_short_addresses_go_to_the_current_conference(self):
        response = self.get("/call-for-papers/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/2027/call-for-papers/")

    def test_past_conference_stays_at_its_year(self):
        past = Conference.objects.create(number=34, city="Singapore", start_date=date(2026, 6, 22))
        seed(past, publish=True)
        self.assertContains(self.get("/2026/"), "IGLC 34")
        self.assertContains(self.get("/"), "IGLC 35")

    def test_only_one_current(self):
        past = Conference.objects.create(number=34, city="Singapore", start_date=date(2026, 6, 22))
        other = seed(past, current=True, publish=True)
        self.assertFalse(ConferenceHomePage.objects.get(pk=self.home.pk).is_current)
        self.assertContains(self.get("/"), "IGLC 34")
        self.assertTrue(ConferenceHomePage.objects.get(pk=other.pk).is_current)

    def test_main_site_is_unchanged(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/2027/").status_code, 404)

    def test_not_found_and_admin_on_the_conference_host(self):
        response = self.get("/2027/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        response = self.get("/manage/pages/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/manage/pages/"))

    @override_settings(SITE_NOINDEX=True)
    def test_preview_is_not_indexed(self):
        self.assertContains(self.get("/robots.txt"), "Disallow: /")

    def test_sitemaps_are_separate(self):
        self.assertContains(self.get("/sitemap.xml"), "/2027/call-for-papers/")
        main = self.client.get("/sitemap-pages.xml")
        self.assertNotContains(main, "call-for-papers")

    def test_colours_must_be_readable(self):
        self.home.primary_colour = "#f0e060"
        with self.assertRaises(ValidationError):
            self.home.full_clean()
        self.home.primary_colour = "blue"
        with self.assertRaises(ValidationError):
            self.home.full_clean()
        self.assertGreater(contrast("#365a91", "#ffffff"), 4.5)

    def test_home_needs_the_conference_dates(self):
        undated = Conference.objects.create(number=36, city="Santiago")
        self.home.conference = undated
        with self.assertRaises(ValidationError):
            self.home.full_clean()

    def test_important_dates_and_tracks(self):
        ConferenceTrack.objects.create(conference=self.conference, title="Digitalisation", order=1)
        ImportantDate.objects.create(page=self.home, label="Full papers due", date=date(2027, 1, 31),
                                         original_date=date(2027, 1, 15), sort_order=1)
        self.assertContains(self.get("/"), "Full papers due")
        self.assertContains(self.get("/"), "<del>15 January 2027</del>", html=False)
        self.assertContains(self.get("/2027/call-for-papers/"), "Digitalisation")

    def test_accepted_papers_from_the_production(self):
        track = ConferenceTrack.objects.create(conference=self.conference, title="Digitalisation", order=1)
        production = Production.objects.create(conference=self.conference)
        Submission.objects.create(production=production, conftool_id=1, title="Takt in Munich", track=track,
                                  registered_authors=[{"name": "Ann Smith", "email": "ann@example.org"}])
        Submission.objects.create(production=production, conftool_id=2, title="Withdrawn one",
                                  status=Submission.Status.WITHDRAWN)
        response = self.get("/2027/accepted-papers/")
        self.assertContains(response, "Takt in Munich")
        self.assertContains(response, "Ann Smith")
        self.assertNotContains(response, "ann@example.org")
        self.assertNotContains(response, "Withdrawn one")

    def test_committees(self):
        page = CommitteesPage.objects.get()
        page.members.create(committee="Scientific chairs", name="Kristen Parrish", role="Chair")
        page.save_revision().publish()
        self.assertContains(self.get("/2027/committees/"), "Kristen Parrish")

    def test_archive_links_to_the_website(self):
        self.conference.is_published = True
        self.conference.save()
        self.assertContains(self.client.get(self.conference.get_absolute_url()),
                            "http://conference.localhost:8000/2027/")


class OrganiserTests(TestCase):
    def setUp(self):
        sync_site()
        self.conference = Conference.objects.create(number=35, city="Munich", start_date=date(2027, 7, 19))
        self.home = seed(self.conference, current=True, publish=True)
        other = Conference.objects.create(number=34, city="Singapore", start_date=date(2026, 6, 22))
        self.other = seed(other, publish=True)
        self.organiser = User.objects.create_user("org", password="pw")
        self.organiser.groups.add(Group.objects.get(name="IGLC 35 organisers"))
        self.client.force_login(self.organiser)
        self.page = ConferencePage.objects.child_of(self.home).get(slug="call-for-papers")

    def test_organisers_edit_their_own_conference_only(self):
        self.assertEqual(self.client.get(f"/manage/pages/{self.page.pk}/edit/").status_code, 200)
        theirs = ConferencePage.objects.child_of(self.other).get(slug="call-for-papers")
        self.assertIn(self.client.get(f"/manage/pages/{theirs.pk}/edit/").status_code, (302, 403))

    def test_organisers_publish_their_own_pages(self):
        from wagtail.models import Page

        perms = Page.objects.get(pk=self.page.pk).permissions_for_user(self.organiser)
        self.assertTrue(perms.can_edit())
        self.assertTrue(perms.can_publish())
        self.assertTrue(perms.can_unpublish())
        theirs = ConferencePage.objects.child_of(self.other).get(slug="call-for-papers")
        self.assertFalse(Page.objects.get(pk=theirs.pk).permissions_for_user(self.organiser).can_publish())
        response = self.client.post(f"/manage/pages/{self.page.pk}/edit/", {
            "title": "Call for papers", "slug": "call-for-papers", "intro": "Now open.",
            "body-count": "0", "action-publish": "action-publish"})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get("/2027/call-for-papers/", **HOST), "Now open.")
        # no IGLC approval step on the conference sites (the main site keeps its workflow)
        self.assertIsNone(self.page.get_workflow())
        self.assertNotContains(self.client.get(f"/manage/pages/{self.page.pk}/edit/"), "action-submit")

    def test_frozen_site(self):
        self.home.frozen = True
        self.home.save_revision().publish()
        response = self.client.get(f"/manage/pages/{self.page.pk}/edit/")
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get("/", **HOST), "has taken place")
        admin = User.objects.create_superuser("root", password="pw")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(f"/manage/pages/{self.page.pk}/edit/").status_code, 200)

    def test_group_has_image_collection(self):
        from wagtail.models import Collection

        self.assertTrue(Collection.objects.filter(name="IGLC 35").exists())
        self.assertTrue(self.organiser.has_perm("wagtailadmin.access_admin"))


class DateRangeTests(TestCase):
    def test_ranges(self):
        self.assertEqual(date_range(date(2027, 7, 19), date(2027, 7, 23)), "19–23 July 2027")
        self.assertEqual(date_range(date(2027, 6, 30), date(2027, 7, 2)), "30 June – 2 July 2027")
        self.assertEqual(date_range(date(2027, 12, 31), date(2028, 1, 2)), "31 December 2027 – 2 January 2028")
        self.assertEqual(date_range(date(2027, 7, 19)), "19 July 2027")


class StandardPageTemplateTests(TestCase):
    def setUp(self):
        sync_site()
        self.conference = Conference.objects.create(number=35, city="Munich", start_date=date(2027, 7, 19))

    def test_new_sites_follow_the_edited_list(self):
        from .models import StandardPageTemplate

        StandardPageTemplate.objects.filter(slug="sponsors").update(active=False)
        StandardPageTemplate.objects.create(page_type="ConferencePage", title="Industry day", slug="industry-day",
                                            intro="For practitioners.", sort_order=99,
                                            body=[("text", "<p>Site visits.</p>")])
        home = seed(self.conference, publish=True)
        slugs = list(home.get_children().values_list("slug", flat=True))
        self.assertNotIn("sponsors", slugs)
        self.assertEqual(slugs[-1], "industry-day")
        self.assertEqual(slugs[0], "call-for-papers")
        self.assertContains(self.client.get("/2027/industry-day/", **HOST), "Site visits.")

    def test_rules(self):
        from .models import StandardPageTemplate

        with self.assertRaises(ValidationError):
            StandardPageTemplate(page_type="ConferencePage", title="x", slug="2027").full_clean()
        with self.assertRaises(ValidationError):
            StandardPageTemplate(page_type="AcceptedPapersPage", title="x", slug="more-papers").full_clean()
        with self.assertRaises(ValidationError):
            StandardPageTemplate(page_type="KeynotesPage", title="x", slug="talks",
                                 body=[("text", "<p>x</p>")]).full_clean()

    def test_admin_for_superusers_only(self):
        self.client.force_login(User.objects.create_superuser("root", password="pw"))
        response = self.client.get("/manage/conference_standard_pages/")
        self.assertContains(response, "Call for papers")
        from .models import StandardPageTemplate

        pk = StandardPageTemplate.objects.get(slug="programme").pk
        self.assertEqual(self.client.get(f"/manage/conference_standard_pages/edit/{pk}/").status_code, 200)
        organiser = User.objects.create_user("org", password="pw")
        self.client.force_login(organiser)
        self.assertIn(self.client.get("/manage/conference_standard_pages/").status_code, (302, 403))
