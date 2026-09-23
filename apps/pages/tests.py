from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class LegacyPagesTests(TestCase):
    def test_import_creates_pages_at_the_redirect_targets(self):
        call_command("import_legacy_pages", stdout=StringIO())
        for path in ("/about/", "/charter-and-operating-procedures/", "/for-authors/",
                     "/for-authors/templates/", "/community/mailing-list/", "/proceedings/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_old_urls_reach_the_new_pages(self):
        call_command("import_legacy_pages", stdout=StringIO())
        for old in ("/Home/About", "/ForAuthors?view=Templates", "/ForAuthors?view=About", "/Community/MailingList"):
            response = self.client.get(old, follow=True)
            self.assertEqual(response.status_code, 200, old)

    def test_import_is_repeatable(self):
        call_command("import_legacy_pages", stdout=StringIO())
        out = StringIO()
        call_command("import_legacy_pages", stdout=out)
        self.assertIn("Pages created: 0", out.getvalue())
