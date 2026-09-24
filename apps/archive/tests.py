from datetime import date

from django.test import TestCase, override_settings

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
        self.assertContains(response, "<mark>Takt</mark> Planning in Practice")

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
        self.assertMovedTo("/Admin/Papers", "/manage/")

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
        self.assertContains(response, "/manage/archive/paper/edit/2150/")
        self.assertContains(response, "/manage/")
        self.assertContains(self.client.get("/papers/conference/25"), "/manage/archive/conference/edit/25/")


@override_settings(SITE_NOINDEX=False)  # a preview has it on
class RobotsTests(TestCase):
    def test_robots(self):
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /django-admin/")

    @override_settings(SITE_NOINDEX=True)
    def test_preview_is_not_indexed(self):
        self.assertEqual(self.client.get("/robots.txt").content.decode().strip(), "User-agent: *\nDisallow: /")
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


class SearchTests(ArchiveTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = Paper.objects.create(
            pk=2151, conference=cls.conference, title="Flow in Design Management",
            abstract="We studied how takt time changes design work.", keywords="design", first_page=30,
        )
        Author.objects.create(paper=cls.other, first_name="Dee", last_name="Brown", order=1)

    def test_authors_text_follows_authors(self):
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.authors_text, "Ann Smith Bo Jones Cy Lee")
        Author.objects.filter(paper=self.paper, last_name="Lee").delete()
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.authors_text, "Ann Smith Bo Jones")

    def test_all_words_must_match_and_title_ranks_first(self):
        from .search import search_papers

        self.assertEqual(list(search_papers("takt").values_list("pk", flat=True)), [2150, 2151])
        self.assertEqual(list(search_papers("takt design").values_list("pk", flat=True)), [2151])
        self.assertEqual(list(search_papers("Brown takt").values_list("pk", flat=True)), [2151])

    def test_filters(self):
        response = self.client.get("/papers/search", {"q": "takt", "from": 2023})
        self.assertContains(response, "<strong>0</strong> papers found")
        response = self.client.get("/papers/search", {"conference": 30})
        self.assertContains(response, "<strong>2</strong> papers found")

    def test_highlight_escapes(self):
        from .templatetags.archive_tags import highlight, snippet

        self.assertEqual(highlight("<b>Takt</b> planning", "plan"), "&lt;b&gt;Takt&lt;/b&gt; <mark>plan</mark>ning")
        self.assertIn("<mark>takt</mark>", snippet("x " * 300 + "takt time " + "y " * 300, "takt"))

    def test_search_page_shows_snippet_and_export_keeps_filters(self):
        response = self.client.get("/papers/search", {"q": "takt", "sort": "oldest"})
        self.assertContains(response, "<mark>takt</mark> time")
        self.assertContains(response, "exportsearchbibtex?q=takt&amp;sort=oldest")
        bib = self.client.get("/papers/exportsearchbibtex", {"q": "design takt"}).content.decode()
        self.assertIn("Flow in Design Management", bib)
        self.assertNotIn("Takt Planning in Practice", bib)

    def test_pagination(self):
        for i in range(30):
            Paper.objects.create(conference=self.conference, title=f"Lean paper {i}", first_page=100 + i)
        response = self.client.get("/papers/search", {"q": "lean", "page": 2})
        self.assertContains(response, "Page 2 of 2")


class AuthorPageTests(ArchiveTestCase):
    def setUp(self):
        from django.core.management import call_command

        second = Paper.objects.create(conference=self.conference, title="Second Paper", first_page=50)
        Author.objects.create(paper=second, first_name="ann", last_name="Smith", order=1,
                              title_and_contact="Uni X, ann@example.org, ORCID 0000-0002-1825-0097")
        Author.objects.create(paper=second, first_name="Bo", last_name="Jones", order=2)
        call_command("group_authors", stdout=__import__("io").StringIO())

    def test_group_authors(self):
        from .models import AuthorPerson

        smith = AuthorPerson.objects.get(last_name="Smith")
        self.assertEqual(smith.authorships.count(), 2)
        self.assertEqual(smith.orcid, "0000-0002-1825-0097")
        self.assertEqual(AuthorPerson.objects.count(), 3)

    def test_author_page(self):
        from .models import AuthorPerson

        smith = AuthorPerson.objects.get(last_name="Smith")
        response = self.client.get(f"/authors/{smith.pk}")
        self.assertContains(response, "Takt Planning in Practice")
        self.assertContains(response, "Second Paper")
        self.assertContains(response, "https://orcid.org/0000-0002-1825-0097")
        self.assertContains(response, "Bo Jones</a> <span title=\"joint papers\">2</span>")
        self.assertContains(self.client.get("/papers/details/2150"), f'href="/authors/{smith.pk}"')

    def test_author_index_and_search_hint(self):
        self.assertContains(self.client.get("/authors/"), "Smith, Ann")
        self.assertContains(self.client.get("/authors/", {"letter": "J"}), "Jones, Bo")
        self.assertContains(self.client.get("/papers/search", {"q": "jones"}), 'class="author-hits"')

    def test_old_author_admin_paths(self):
        self.assertEqual(legacy_target("/Authors/CreateOrAssignAuthorPersons", {}), "/manage/")
        self.assertIsNone(legacy_target("/authors/12", {}))

    def test_merge_action(self):
        from django.contrib.auth.models import User

        from .models import AuthorPerson

        User.objects.create_superuser("admin", "a@example.org", "pw")
        self.client.login(username="admin", password="pw")
        ids = list(AuthorPerson.objects.filter(last_name__in=["Smith", "Lee"]).values_list("pk", flat=True))
        smith, lee = AuthorPerson.objects.get(last_name="Smith"), AuthorPerson.objects.get(last_name="Lee")
        page = self.client.get(f"/manage/archive/person/edit/{smith.pk}/")
        self.assertContains(page, "Merge another person into this one")
        response = self.client.post(f"/manage/archive/person/edit/{smith.pk}/", {
            "first_name": smith.first_name, "last_name": smith.last_name, "orcid": smith.orcid, "merge": lee.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AuthorPerson.objects.count(), 2)
        self.assertEqual(AuthorPerson.objects.get(last_name="Smith").authorships.count(), 3)


class SingleNameTests(ArchiveTestCase):
    def test_single_name_is_stored_as_last_name_and_cited_plainly(self):
        from . import citations

        author = Author.objects.create(paper=self.paper, first_name="Hermawan ", last_name="", order=4)
        author.refresh_from_db()
        self.assertEqual((author.first_name, author.last_name), ("", "Hermawan"))
        self.assertIn("Lee, C., & Hermawan. (2022)", citations.as_text(citations.apa7(self.paper)))
        page = self.client.get("/papers/details/2150").content.decode()
        self.assertIn('<meta name="citation_author" content="Hermawan">', page)

    def test_single_name_gets_an_author_page(self):
        from io import StringIO

        from django.core.management import call_command

        from .models import AuthorPerson

        Author.objects.create(paper=self.paper, last_name="Hermawan", order=4)
        call_command("group_authors", stdout=StringIO())
        self.assertTrue(AuthorPerson.objects.filter(last_name="Hermawan", first_name="").exists())


class TrackTests(ArchiveTestCase):
    def test_import_tracks_and_headings(self):
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        from .models import ConferenceTrack

        other = Paper.objects.create(conference=self.conference, title="Second", first_page=30)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("paper_id,track\n2150,Production Planning\n%d,Lean and Green\n" % other.pk)
        call_command("import_tracks", f.name, stdout=StringIO())
        self.assertEqual(ConferenceTrack.objects.filter(conference=self.conference).count(), 2)
        page = self.client.get("/papers/conference/25").content.decode()
        self.assertIn('<h2 class="track-heading">Production Planning</h2>', page)
        self.assertLess(page.index("Production Planning</h2>"), page.index("Lean and Green</h2>"))

    def test_track_candidates(self):
        from .management.commands.read_tracks import candidate

        self.assertEqual(candidate("People, Culture and Change899"), "People, Culture and Change")
        self.assertEqual(candidate("900 Proceedings IGLC34, 22–26 June 2026, Singapore"), "")


class TrackTests(ArchiveTestCase):
    def test_conference_page_and_search_by_track(self):
        from .models import ConferenceTrack

        planning = ConferenceTrack.objects.create(conference=self.conference, title="Production Planning and Control", order=1)
        Paper.objects.filter(pk=2150).update(track=planning)
        Paper.objects.create(pk=2152, conference=self.conference, title="Untracked", first_page=30, last_page=40)
        page = self.client.get("/papers/conference/25").content.decode()
        self.assertIn(f'href="#track-{planning.pk}"', page)
        self.assertIn("Other papers", page)
        self.assertLess(page.index("Takt Planning in Practice"), page.index("Untracked"))
        # words of the track name, in any spelling
        page = self.client.get("/papers/search/?track=planning+%26+control").content.decode()
        self.assertIn("Takt Planning in Practice", page)
        self.assertNotIn(">Untracked<", page)
        self.assertIn("Production Planning and Control", page)  # shown with the result, and suggested
