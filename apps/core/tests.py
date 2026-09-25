from django.test import TestCase, override_settings


class HealthCheckTests(TestCase):
    def test_healthz_ignores_host_header(self):
        response = self.client.get("/healthz", HTTP_HOST="169.254.130.4:8000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok\n")


class HostRedirectTests(TestCase):
    @override_settings(HOST_REDIRECTS={"iglc.net": "www.iglc.net"}, ALLOWED_HOSTS=["iglc.net", "www.iglc.net"])
    def test_apex_goes_to_www(self):
        from django.test import Client

        response = Client(HTTP_HOST="iglc.net").get("/papers/details/2150?x=1")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://www.iglc.net/papers/details/2150?x=1")


class SitemapTests(TestCase):
    def setUp(self):
        from datetime import date

        from apps.archive.models import Author, AuthorPerson, Conference, Paper

        conference = Conference.objects.create(pk=25, number=30, start_date=date(2022, 7, 25), is_published=True)
        hidden = Conference.objects.create(pk=26, number=31, is_published=False)
        paper = Paper.objects.create(pk=2150, conference=conference, title="Takt")
        Paper.objects.create(pk=2151, conference=hidden, title="Unpublished")
        person = AuthorPerson.objects.create(first_name="Ann", last_name="Smith")
        Author.objects.create(paper=paper, person=person, first_name="Ann", last_name="Smith", order=1)
        self.person = person

    def test_index_and_sections(self):
        index = self.client.get("/sitemap.xml").content.decode()
        for section in ("pages", "listings", "conferences", "papers", "authors"):
            self.assertIn(f"http://testserver/sitemap-{section}.xml", index)
        papers = self.client.get("/sitemap-papers.xml").content.decode()
        self.assertIn("<loc>http://testserver/papers/details/2150</loc>", papers)
        self.assertNotIn("2151", papers)
        self.assertIn(f"/authors/{self.person.pk}</loc>", self.client.get("/sitemap-authors.xml").content.decode())
        self.assertIn("/about/committees</loc>", self.client.get("/sitemap-listings.xml").content.decode())
        self.assertEqual(self.client.get("/sitemap-pages.xml").status_code, 200)

    @override_settings(SITE_NOINDEX=False)  # a preview has it on
    def test_robots_points_to_sitemap(self):
        self.assertIn("Sitemap: http://testserver/sitemap.xml", self.client.get("/robots.txt").content.decode())


class LoginLogoutTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        self.user = User.objects.create_superuser("admin", "a@example.org", "pw")

    def test_login_link_for_visitors(self):
        self.assertContains(self.client.get("/robots.txt".replace("robots.txt", "links/")),
                            '/manage/login/?next=/links/')

    def test_logout_returns_to_the_page(self):
        self.client.login(username="admin", password="pw")
        response = self.client.post("/manage/logout/", {"next": "/links/"})
        self.assertRedirects(response, "/links/", fetch_redirect_response=False)

    def test_logout_from_admin_and_cms_goes_to_front_page(self):
        self.client.login(username="admin", password="pw")
        self.assertRedirects(self.client.post("/manage/logout/"), "/", fetch_redirect_response=False)
        # the old addresses of the back office lead to the new one
        self.assertRedirects(self.client.get("/cms/pages/"), "/manage/pages/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/production/35/"), "/manage/production/35/", fetch_redirect_response=False)

    def test_one_back_office(self):
        self.client.login(username="admin", password="pw")
        page = self.client.get("/manage/").content.decode()
        self.assertIn('"url": "/"', page)  # View site, in the sidebar
        self.assertIn("/manage/production/", page)
        # Django's admin is a fallback for superusers only
        self.assertEqual(self.client.get("/django-admin/").status_code, 200)


class SiteHelpTests(TestCase):
    """Help → Site documentation: docs/*.md in the back office, by audience."""

    def setUp(self):
        from django.contrib.auth.models import Group, Permission, User

        self.admin = User.objects.create_superuser("root", "r@example.org", "pw")
        self.organiser = User.objects.create_user("org", password="pw")
        group = Group.objects.create(name="Some organisers")
        group.permissions.add(Permission.objects.get(codename="access_admin"))
        self.organiser.groups.add(group)

    def test_every_document_exists(self):
        from django.conf import settings

        from .help import DOCS, title

        for doc in DOCS:
            self.assertTrue((settings.BASE_DIR / doc.path).exists(), doc.path)
            self.assertNotEqual(title(doc), doc.slug, doc.path)

    def test_superuser_reads_everything(self):
        from django.urls import reverse

        from .help import DOCS

        self.client.force_login(self.admin)
        index = self.client.get(reverse("site_help:index"))
        self.assertContains(index, "Production on Azure")
        for doc in DOCS:
            response = self.client.get(reverse("site_help:doc", args=[doc.slug]))
            self.assertEqual(response.status_code, 200, doc.slug)
        page = self.client.get(reverse("site_help:doc", args=["switch-over"]))
        self.assertContains(page, 'href="/manage/site-help/deploy-azure/"')

    def test_organiser_sees_only_general_documents(self):
        from django.urls import reverse

        self.client.force_login(self.organiser)
        index = self.client.get(reverse("site_help:index"))
        self.assertContains(index, "Conference websites")
        self.assertNotContains(index, "Production on Azure")
        self.assertNotContains(index, "Editors’ guide")
        self.assertEqual(self.client.get(reverse("site_help:doc", args=["conference-sites"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("site_help:doc", args=["deploy-azure"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("site_help:doc", args=["production-process"])).status_code, 404)

    def test_in_help_menu(self):
        self.client.force_login(self.organiser)
        self.assertContains(self.client.get("/manage/"), "Site documentation")
