import io

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


class _Response(io.BytesIO):
    status = 202


@override_settings(EMAIL_REPLY_TO="IGLC General Secretary <webmaster@iglc.net>",
                   DEFAULT_FROM_EMAIL="IGLC.net <noreply@iglc.net>",
                   AZURE_EMAIL_ENDPOINT="https://iglc-acs.europe.communication.azure.com/")
class EmailBackendTests(TestCase):
    def setUp(self):
        from apps.core import mail

        mail._token_cache.update(token="", expires=0.0)

    def _message(self, **kwargs):
        from django.core.mail import EmailMultiAlternatives

        return EmailMultiAlternatives("Password reset", "Plain body", to=["Ann Smith <ann@example.org>"], **kwargs)

    def test_payload(self):
        from email.mime.text import MIMEText

        from apps.core.mail import acs_payload

        message = self._message(cc=["cc@example.org"], bcc=["bcc@example.org"], reply_to=["Ed <ed@example.org>"],
                                headers={"X-IGLC": "1", "Reply-To": "ignored@example.org"})
        message.attach_alternative("<p>HTML body</p>", "text/html")
        message.attach("notes.txt", "hello", "text/plain")
        message.attach(MIMEText("mime part"))
        payload = acs_payload(message)
        self.assertEqual(payload["senderAddress"], "noreply@iglc.net")
        self.assertEqual(payload["content"], {"subject": "Password reset", "plainText": "Plain body",
                                              "html": "<p>HTML body</p>"})
        self.assertEqual(payload["recipients"]["to"], [{"address": "ann@example.org", "displayName": "Ann Smith"}])
        self.assertEqual(payload["recipients"]["cc"], [{"address": "cc@example.org"}])
        self.assertEqual(payload["recipients"]["bcc"], [{"address": "bcc@example.org"}])
        self.assertEqual(payload["replyTo"], [{"address": "ed@example.org", "displayName": "Ed"}])
        self.assertEqual(payload["headers"], {"X-IGLC": "1"})
        self.assertTrue(payload["userEngagementTrackingDisabled"])
        self.assertEqual(payload["attachments"][0], {"name": "notes.txt", "contentType": "text/plain",
                                                     "contentInBase64": "aGVsbG8="})
        self.assertEqual(len(payload["attachments"]), 2)

    def test_html_only_message(self):
        from django.core.mail import EmailMessage

        from apps.core.mail import acs_payload

        message = EmailMessage("Hi", "<p>Hi</p>", to=["a@example.org"])
        message.content_subtype = "html"
        self.assertEqual(acs_payload(message)["content"], {"subject": "Hi", "html": "<p>Hi</p>"})

    def test_default_reply_to_only_when_missing(self):
        import io

        from apps.core.mail import ConsoleBackend

        plain, own = self._message(), self._message(reply_to=["ed@example.org"])
        ConsoleBackend(stream=io.StringIO()).send_messages([plain, own])
        self.assertEqual(plain.reply_to, ["IGLC General Secretary <webmaster@iglc.net>"])
        self.assertEqual(own.reply_to, ["ed@example.org"])

    def test_azure_send(self):
        import json
        from unittest import mock

        from apps.core.mail import AzureEmailBackend

        with mock.patch("apps.core.mail.managed_identity_token", return_value="tok"), \
                mock.patch("apps.core.mail.urlopen", return_value=_Response()) as urlopen:
            self.assertEqual(AzureEmailBackend().send_messages([self._message()]), 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://iglc-acs.europe.communication.azure.com/emails:send"
                                           "?api-version=2023-03-31")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        body = json.loads(request.data)
        self.assertEqual(body["replyTo"], [{"address": "webmaster@iglc.net", "displayName": "IGLC General Secretary"}])

    def test_azure_throttled(self):
        import io
        from unittest import mock
        from urllib.error import HTTPError

        from apps.core.mail import AzureEmailBackend, EmailSendError

        def throttled(*args, **kwargs):
            raise HTTPError("url", 429, "Too Many Requests", {"Retry-After": "60"}, io.BytesIO(b"quota"))

        with mock.patch("apps.core.mail.managed_identity_token", return_value="tok"), \
                mock.patch("apps.core.mail.urlopen", side_effect=throttled):
            with self.assertRaisesMessage(EmailSendError, "429"):
                AzureEmailBackend().send_messages([self._message()])
            with self.assertLogs("apps.core.mail", "ERROR"):
                self.assertEqual(AzureEmailBackend(fail_silently=True).send_messages([self._message()]), 0)

    def test_managed_identity_token_is_cached(self):
        import json
        import time
        from unittest import mock

        from apps.core.mail import managed_identity_token

        token = json.dumps({"access_token": "abc", "expires_on": str(int(time.time()) + 3600)}).encode()
        env = {"IDENTITY_ENDPOINT": "http://169.254.129.1:8081/msi/token", "IDENTITY_HEADER": "h"}
        with mock.patch.dict("os.environ", env), \
                mock.patch("apps.core.mail.urlopen", return_value=_Response(token)) as urlopen:
            self.assertEqual(managed_identity_token(), "abc")
            self.assertEqual(managed_identity_token(), "abc")
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertIn("resource=https%3A%2F%2Fcommunication.azure.com%2F", request.full_url)
        self.assertEqual(request.get_header("X-identity-header"), "h")

    def test_no_managed_identity(self):
        from unittest import mock

        from apps.core.mail import EmailSendError, managed_identity_token

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(EmailSendError, "managed identity"):
                managed_identity_token()
