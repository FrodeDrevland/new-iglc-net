from datetime import date

from django.test import TestCase

from .legacy import legacy_target
from .models import Author, Conference, Editor, Paper, Volume


class ArchiveTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(
            pk=25, number=30, start_date=date(2022, 7, 25), city="Edmonton", country="Canada",
            proceedings_title="Proceedings of the 30th Annual Conference of the IGLC", issn="2309-0979",
            is_published=True,
        )
        Editor.objects.create(conference=cls.conference, first_name="Erin", last_name="Example", order=1)
        volume = Volume.objects.create(conference=cls.conference, number=1, first_page=1, last_page=900,
                                       isbn="978-0-00-000000-0")
        cls.paper = Paper.objects.create(
            pk=2150, conference=cls.conference, volume=volume, title="Takt Planning in Practice",
            abstract="An abstract.", keywords="takt planning, flow", first_page=10, last_page=21,
            doi="10.24928/2022/0123", full_text_url="https://storage.example.net/papers/2150.pdf",
        )
        for order, (first, last) in enumerate([("Ann", "Smith"), ("Bo", "Jones"), ("Cy", "Lee")], 1):
            Author.objects.create(paper=cls.paper, first_name=first, last_name=last, order=order)


class PaperPagesTests(ArchiveTestCase):
    def test_paper_detail_keeps_old_path(self):
        for path in ("/papers/details/2150", "/papers/details/2150/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, "Takt Planning in Practice")
            self.assertContains(response, 'name="citation_doi" content="10.24928/2022/0123"')

    def test_missing_paper_is_404(self):
        self.assertEqual(self.client.get("/papers/details/999999").status_code, 404)

    def test_pdf_redirects_to_file(self):
        response = self.client.get("/papers/details/2150/pdf")
        self.assertRedirects(response, self.paper.full_text_url, fetch_redirect_response=False)

    def test_conference_page_lists_papers(self):
        response = self.client.get("/papers/conference/25")
        self.assertContains(response, "Takt Planning in Practice")

    def test_search_by_author(self):
        response = self.client.get("/papers/search", {"q": "Jones"})
        self.assertContains(response, "Takt Planning in Practice")

    def test_old_search_form_post(self):
        response = self.client.post("/papers/search", {"query": "takt"})
        self.assertContains(response, "Takt Planning in Practice")

    def test_exports(self):
        bib = self.client.get("/papers/exportbibtex/2150").content.decode()
        self.assertIn("@inproceedings{Smith2022_2150,", bib)
        self.assertIn("doi = {10.24928/2022/0123}", bib)
        ris = self.client.get("/papers/exportconferenceris/25").content.decode()
        self.assertIn("TY  - CONF", ris)
        self.assertIn("AU  - Jones, Bo", ris)
        self.assertIn("SN  - 978-0-00-000000-0 (ISBN)", ris)

    def test_find_by_conftool_id(self):
        response = self.client.get("/papers/findbyconftoolid", {"year": 2022, "id": "123"})
        self.assertRedirects(response, "/papers/details/2150", fetch_redirect_response=False)


class LegacyUrlTests(ArchiveTestCase):
    def assertMovedTo(self, old, new):
        response = self.client.get(old)
        self.assertEqual(response.status_code, 301, old)
        self.assertEqual(response["Location"], new, old)

    def test_crossref_style_urls(self):
        self.assertMovedTo("/Papers/Details/2150", "/papers/details/2150")
        self.assertMovedTo("/Papers/Conference/25", "/papers/conference/25")
        self.assertMovedTo("/Papers/Details/2150/pdf", "/papers/details/2150/pdf")

    def test_id_in_query_string(self):
        self.assertMovedTo("/Papers/Details?id=2150", "/papers/details/2150")
        self.assertMovedTo("/Papers/PDF/2150", "/papers/details/2150/pdf")

    def test_static_pages(self):
        self.assertMovedTo("/Home/CharterAndOperatingProcedures", "/charter-and-operating-procedures/")
        self.assertMovedTo("/Home/important-links", "/links/")
        self.assertMovedTo("/Admin/Papers", "/cms/")

    def test_for_authors_view_parameter(self):
        self.assertEqual(
            legacy_target("/ForAuthors", {"view": "PaperSubmissionAndReviewProcess"}),
            "/for-authors/paper-submission-and-review-process/",
        )
        self.assertEqual(legacy_target("/ForAuthors/Index", {}), "/for-authors/")

    def test_new_urls_are_not_redirected(self):
        self.assertIsNone(legacy_target("/papers/details/2150", {}))
        self.assertEqual(self.client.get("/papers").status_code, 200)


class PaperModelTests(ArchiveTestCase):
    def test_author_strings(self):
        self.assertEqual(self.paper.short_author_string(), "Smith et al.")
        self.assertEqual(self.paper.full_author_string(), "Ann Smith, Bo Jones and Cy Lee")
        self.assertEqual(self.paper.file_name(), "Smith et al. 2022 - Takt Planning in Practice")


class LegacyImportTests(TestCase):
    def test_clean_doi(self):
        from .legacy_import import clean_doi

        self.assertEqual(clean_doi("https://10.24928/2019/0123"), "10.24928/2019/0123")
        self.assertEqual(clean_doi("https://doi.org/10.24928/2019/0123"), "10.24928/2019/0123")
        self.assertEqual(clean_doi("10.24928/2019/0174."), "10.24928/2019/0174.")  # registered like this
        self.assertEqual(clean_doi(" 10.24928/2019/0123 "), "10.24928/2019/0123")
        self.assertEqual(clean_doi(None), "")



class AdminBarTests(ArchiveTestCase):
    def test_staff_see_edit_links(self):
        from django.contrib.auth import get_user_model

        self.assertNotContains(self.client.get("/papers/details/2150"), "Edit this paper")
        staff = get_user_model().objects.create_user("editor", password="x", is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        response = self.client.get("/papers/details/2150")
        self.assertContains(response, "/manage/archive/paper/2150/change/")
        self.assertContains(response, "/cms/")
        self.assertContains(self.client.get("/papers/conference/25"), "/manage/archive/conference/25/change/")


class RobotsTests(TestCase):
    def test_robots(self):
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /cms/")
        with self.settings(SITE_NOINDEX=True):
            self.assertContains(self.client.get("/robots.txt"), "Disallow: /\n")


class LinksAndContentTests(TestCase):
    def test_links_page(self):
        from .models import Link, LinkCategory

        category = LinkCategory.objects.create(name="Journals", sort_order=1)
        Link.objects.create(category=category, name="Lean Construction Journal", url="https://example.org/lcj")
        self.assertContains(self.client.get("/links/"), "Lean Construction Journal")
        self.assertEqual(self.client.get("/links", follow=True).status_code, 200)
        self.assertEqual(self.client.get("/Links", follow=True).status_code, 200)

    def test_old_content_files_go_to_blob_storage(self):
        with self.settings(LEGACY_CONTENT_URL="https://store.example.net/content"):
            response = self.client.get("/Content/Proceedings/IGLC-2015-Proceedings.pdf")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "https://store.example.net/content/Proceedings/IGLC-2015-Proceedings.pdf")
            response = self.client.get("/Content/Documents/IGLC33 Paper Template.docx")
            self.assertEqual(response["Location"], "https://store.example.net/content/Documents/IGLC33%20Paper%20Template.docx")


class CitationTests(ArchiveTestCase):
    def test_initials(self):
        from .citations import initials

        self.assertEqual(initials("Jean-Pierre da Silva"), "J.-P. S.")
        self.assertEqual(initials("Iris D."), "I. D.")
        self.assertEqual(initials(""), "")

    def test_apa7_and_short(self):
        from .citations import apa7, as_text, iglc_short

        apa = as_text(apa7(self.paper))
        self.assertEqual(
            apa,
            "Smith, A., Jones, B., & Lee, C. (2022). Takt Planning in Practice. In E. Example (Ed.), "
            "Proceedings of the 30th Annual Conference of the IGLC (pp. 10–21). "
            "https://doi.org/10.24928/2022/0123",
        )
        self.assertEqual(
            as_text(iglc_short(self.paper)),
            "Smith, A., Jones, B., & Lee, C. (2022). Takt Planning in Practice. IGLC30. https://doi.org/10.24928/2022/0123",
        )
        self.assertContains(self.client.get("/papers/details/2150"), "Shortened reference for IGLC papers")


class BlobFileTests(ArchiveTestCase):
    def test_link_blob_files(self):
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        base = "https://store.example.net"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(f"{base}/papers-zipped/IGLC30_Papers.zip\n"
                    f"{base}/proceedings/Proceedings-IGLC30-Vol1.pdf\n"
                    f"{base}/proceedings/Proceedings-IGLC30-Vol2.pdf\n"
                    f"{base}/proceedings/Proceedings-IGLC3-old.pdf\n")
        call_command("link_blob_files", f.name, stdout=StringIO())
        response = self.client.get("/papers/conference/25")
        self.assertContains(response, "All papers (ZIP)")
        self.assertContains(response, "Volume 2 (PDF)")
        self.assertEqual(self.conference.proceedings_files.count(), 2)


class FullProceedingsTests(ArchiveTestCase):
    def test_link_full_proceedings_from_page(self):
        import json
        from io import StringIO

        from django.core.management import call_command
        from wagtail.models import Site

        from apps.pages.models import StandardPage

        root = Site.objects.get(is_default_site=True).root_page
        page = StandardPage(title="Full proceedings", slug="proceedings", body=json.dumps([{
            "type": "html",
            "value": '<table><tr><td>IGLC 30</td><td>2022</td><td><a href="/Content/Proceedings/IGLC-2022 Proceedings.pdf">'
                     'Volume I</a></td></tr><tr><td>IGLC 99</td><td><a href="/x.pdf">Volume I</a></td></tr></table>',
        }]))
        root.add_child(instance=page)
        with self.settings(LEGACY_CONTENT_URL="https://store.example.net/content"):
            call_command("link_full_proceedings", stdout=StringIO())
        files = list(self.conference.proceedings_files.all())
        self.assertEqual([(f.label, f.url) for f in files],
                         [("Full proceedings", "https://store.example.net/content/Proceedings/IGLC-2022%20Proceedings.pdf")])
