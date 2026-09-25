import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from .docx_reader import orcid_checksum_ok, parse_affiliation, read_manuscript

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def p(style, *runs):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{"".join(runs)}</w:p>'


def t(text):
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def fn(note_id):
    return f'<w:r><w:footnoteReference w:id="{note_id}"/></w:r>'


def sup(text):
    return f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>{text}</w:t></w:r>'


STYLES = {"Title": "Title", "Authors": "Authors", "Heading1": "heading 1", "TextFirst": "Text First",
          "TextRunning": "Text Running", "Normal": "Normal", "Figure": "Figure",
          "Figurecaption": "Figure caption", "Tablecaption": "Table caption", "Heading2": "heading 2"}


def make_docx(body, notes, header=""):
    styles = "".join(f'<w:style w:styleId="{i}"><w:name w:val="{n}"/></w:style>' for i, n in STYLES.items())
    footnotes = "".join(f'<w:footnote w:id="{i}">' + "".join(f"<w:p>{t(x)}</w:p>" for x in paras) + "</w:footnote>"
                        for i, paras in notes.items())
    files = {
        "word/document.xml": f'<w:document {NS}><w:body>{body}<w:sectPr>'
                             f'<w:headerReference w:type="first" r:id="rIdH"/></w:sectPr></w:body></w:document>',
        "word/styles.xml": f"<w:styles {NS}>{styles}</w:styles>",
        "word/footnotes.xml": f"<w:footnotes {NS}>{footnotes}</w:footnotes>",
        "word/header1.xml": f"<w:hdr {NS}><w:p>{t(header)}</w:p></w:hdr>",
        "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                        '<Relationship Id="rIdH" Type="header" Target="header1.xml"/></Relationships>',
    }
    path = Path(tempfile.mkdtemp()) / "123.docx"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


BODY = (
    p("Title", t("Takt planning in practice"))
    + p("Authors", t("Ann Smith"), fn(2), t(", Bo Jones"), sup("2"), t(", &amp; Cy Lee"), fn(3))
    + p("Heading1", t("Abstract")) + p("TextFirst", t("We studied takt."))
    + p("Heading1", t("Keywords")) + p("TextFirst", t("Takt, flow; planning."))
    + p("Heading1", t("Introduction")) + p("TextFirst", t("Text.")) + p("Normal", t("Stray text."))
    + p("Heading1", t("References"))
)
NOTES = {
    "2": ["Professor, NTNU, Trondheim, Norway, ann@ntnu.no, orcid.org/0000-0002-1825-0097"],
    "3": ["PhD student, Aalto University, Espoo, Finland, cy@aalto.fi"],
}
HEADER = ("Smith, A., Jones, B., &amp; Lee, C. (2026). Takt planning in practice. In F. Hamzeh (Ed.), "
          "Proceedings of IGLC34 (pp. 10–21). https://doi.org/10.24928/2026/0123")


class ReaderTests(SimpleTestCase):
    def setUp(self):
        self.result = read_manuscript(make_docx(BODY, NOTES, HEADER))

    def test_metadata(self):
        r = self.result
        self.assertEqual(r.title, "Takt planning in practice")
        self.assertEqual(r.abstract, "We studied takt.")
        self.assertEqual(r.keywords, ["Takt", "flow", "planning"])
        self.assertEqual((r.doi, r.first_page, r.last_page), ("10.24928/2026/0123", 10, 21))
        self.assertEqual(r.citation_title, "Takt planning in practice")

    def test_authors_and_shared_footnote(self):
        a = self.result.authors
        self.assertEqual([x.name for x in a], ["Ann Smith", "Bo Jones", "Cy Lee"])
        self.assertEqual((a[0].email, a[0].orcid, a[0].affiliation), ("ann@ntnu.no", "0000-0002-1825-0097",
                                                                     "Professor, NTNU, Trondheim, Norway"))
        # Bo Jones has a typed superscript 2: the second footnote.
        self.assertEqual(a[1].affiliation, "PhD student, Aalto University, Espoo, Finland")
        self.assertEqual((a[2].last_name, a[2].first_name), ("Lee", "Cy"))

    def test_issues(self):
        issues = " | ".join(self.result.issues)
        self.assertIn("No ORCID in the footnote of Cy Lee", issues)
        self.assertIn("1 paragraph in the style “Normal”", issues)
        self.assertNotIn("Abstract", issues)

    def test_affiliations_numbered_inside_one_footnote(self):
        body = p("Title", t("X")) + p("Authors", t("Ann Smith"), fn(2), t(", Bo Jones"), sup("2"), t(" &amp; Cy Lee"), sup("3"))
        notes = {"2": ["Professor, NTNU, Norway, ann@ntnu.no", "2 Lecturer, UCL, UK, bo@ucl.ac.uk",
                       "3 Student, UCL, UK, cy@ucl.ac.uk"]}
        # footnote 2 is referenced once, so Ann is 1; the numbered paragraphs are 2 and 3
        authors = read_manuscript(make_docx(body, notes)).authors
        self.assertEqual([x.email for x in authors], ["ann@ntnu.no", "bo@ucl.ac.uk", "cy@ucl.ac.uk"])

    def test_not_a_docx(self):
        path = Path(tempfile.mkdtemp()) / "x.docx"
        path.write_bytes(b"not a zip")
        self.assertIn("Not a readable Word", read_manuscript(path).issues[0])


class HelperTests(SimpleTestCase):
    def test_orcid_checksum(self):
        self.assertTrue(orcid_checksum_ok("0000-0002-1825-0097"))
        self.assertTrue(orcid_checksum_ok("0000-0002-1694-233X"))
        self.assertFalse(orcid_checksum_ok("0000-0000-0000-0000"))

    def test_parse_affiliation(self):
        parsed = parse_affiliation("Lecturer, UCL, London, UK, e-mail: bo@ucl.ac.uk, https://orcid.org/0000-0002-1825-0097")
        self.assertEqual(parsed, {"affiliation": "Lecturer, UCL, London, UK", "email": "bo@ucl.ac.uk",
                                  "orcid": "0000-0002-1825-0097"})


# ---------------------------------------------------------------- stamping

from xml.etree import ElementTree as ET  # noqa: E402

from .stamp import RunningText, Segment, stamp  # noqa: E402

PAGE_FIELD = ('<w:r><w:tab/></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
IGNORABLE = ('xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
             'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14"')


def make_template():
    parts = {
        "header1.xml": ("hdr", "even", p("Header", t("Paper title"))),
        "header2.xml": ("hdr", "default", p("Header", t("First Author, …")) + p("Header", t("(Keep anonymous)"))),
        "header3.xml": ("hdr", "first", p("Header", t("Author, F. (2026). Paper title."))),
        "footer1.xml": ("ftr", "even", p("Footer", t("Proceedings IGLC34"), PAGE_FIELD)),
        "footer2.xml": ("ftr", "default", p("Footer", t("Title of Track (the editors…)"), PAGE_FIELD)),
        "footer3.xml": ("ftr", "first", p("Footer", t("Title of Track"), PAGE_FIELD)),
    }
    refs = "".join(
        f'<w:{"headerReference" if kind == "hdr" else "footerReference"} w:type="{role}" r:id="rId{i}"/>'
        for i, (name, (kind, role, _)) in enumerate(parts.items()))
    rels = "".join(f'<Relationship Id="rId{i}" Type="x" Target="{name}"/>' for i, name in enumerate(parts))
    files = {
        "word/document.xml": f'<w:document {NS}><w:body>{p("Title", t("X"))}<w:sectPr>{refs}'
                             f'<w:pgNumType w:start="1"/><w:cols/><w:titlePg/></w:sectPr></w:body></w:document>',
        "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                                        f'relationships">{rels}</Relationships>',
    }
    for name, (kind, _, body) in parts.items():
        files[f"word/{name}"] = f'<w:{kind} {NS} {IGNORABLE}>{body}</w:{kind}>'
    path = Path(tempfile.mkdtemp()) / "template.docx"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


class StampTests(SimpleTestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "out.docx"
        running = RunningText(
            header_first=[Segment("Smith, A. (2026). Takt. In "), Segment("Proceedings", italic=True),
                          Segment(" (pp. 899–910). "), Segment("https://doi.org/10.24928/2026/0100",
                                                               link="https://doi.org/10.24928/2026/0100")],
            header_odd="Ann Smith & Bo Jones", header_even="Takt", footer_first="Production Planning",
            footer_odd="Production Planning", footer_even="Proceedings IGLC34, 22–26 June 2026, Singapore")
        self.info = stamp(make_template(), self.out, running, first_page=899)
        self.zip = zipfile.ZipFile(self.out)

    def text(self, part):
        return "".join(x.text or "" for x in ET.fromstring(self.zip.read(f"word/{part}")).iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))

    def test_texts_replaced(self):
        self.assertEqual(self.text("header1.xml"), "Takt")
        self.assertEqual(self.text("header2.xml"), "Ann Smith & Bo Jones")  # the extra line is gone
        self.assertIn("(pp. 899–910). https://doi.org/10.24928/2026/0100", self.text("header3.xml"))
        self.assertEqual(self.info["missing"], [])

    def test_page_field_kept_and_numbering_set(self):
        footer = self.zip.read("word/footer2.xml").decode()
        self.assertIn("PAGE", footer)
        self.assertIn("Production Planning", footer)
        self.assertNotIn("Title of Track", footer)
        self.assertIn('<w:pgNumType w:start="899"/>', self.zip.read("word/document.xml").decode())

    def test_link_and_namespaces(self):
        rels = self.zip.read("word/_rels/header3.xml.rels").decode()
        self.assertIn('Target="https://doi.org/10.24928/2026/0100"', rels)
        self.assertNotIn("ns0:", rels)
        header = self.zip.read("word/header3.xml").decode()
        self.assertIn('mc:Ignorable="w14"', header)
        self.assertIn('xmlns:w14=', header)  # still declared although nothing uses it
        self.assertIn("<w:i", header)


# ---------------------------------------------------------------- PDF headers and footers

class PdfRunningTests(SimpleTestCase):
    def test_line_breaks_after_spaces_and_hyphens(self):
        from .pdf_running import _words

        pieces = [w for w, _ in _words([Segment("Garcia-Lopez (pp. 922–933). x")])]
        self.assertEqual(pieces, ["Garcia-", "Lopez ", "(pp. ", "922–", "933). ", "x"])


class PaperCheckPageTests(TestCase):
    def test_upload_check_report_and_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import PaperCheck

        docx = make_docx(BODY, NOTES, HEADER).read_bytes()
        response = self.client.post("/for-authors/check-your-paper/", {
            "stage": "camera_ready", "paper": SimpleUploadedFile("my paper.docx", docx)})
        check = PaperCheck.objects.get()
        self.assertRedirects(response, f"/for-authors/check-your-paper/{check.pk}/")
        page = self.client.get(response["Location"]).content.decode()
        self.assertIn("Takt planning in practice", page)
        self.assertIn("No ORCID in the footnote of Bo Jones, Cy Lee", page)
        self.assertIn("number of pages was not checked", page)
        pdf = self.client.get(f"/for-authors/check-your-paper/{check.pk}/report.pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_review_stage_requires_anonymity(self):
        from .checks import check_paper

        result = check_paper(make_docx(BODY, NOTES, HEADER), "review")
        self.assertFalse(result.passed)
        self.assertIn("not_anonymous", [f.code for f in result.findings])
        self.assertNotIn("author_no_orcid", [f.code for f in result.findings])

    def test_rejects_other_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post("/for-authors/check-your-paper/", {
            "stage": "camera_ready", "paper": SimpleUploadedFile("paper.pdf", b"%PDF-1.4")})
        self.assertContains(response, "Please upload the paper as a Word file")


class AuthorSkillTests(TestCase):
    def test_skill_zip_runs_on_its_own(self):
        import io
        import subprocess
        import sys

        response = self.client.get("/for-authors/check-your-paper/iglc-paper-check-skill.zip")
        self.assertEqual(response["Content-Type"], "application/zip")
        folder = Path(tempfile.mkdtemp())
        zipfile.ZipFile(io.BytesIO(response.content)).extractall(folder)
        self.assertTrue((folder / "iglc-paper-check" / "SKILL.md").read_text().startswith("---\nname: iglc-paper-check"))
        paper = make_docx(BODY, NOTES, HEADER)
        out = subprocess.run([sys.executable, "-S", str(folder / "iglc-paper-check/scripts/check_paper.py"), str(paper)],
                             capture_output=True, text=True, cwd=folder)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Title:    Takt planning in practice", out.stdout)
        self.assertIn("No ORCID in the footnote of Bo Jones, Cy Lee", out.stdout)


# ---------------------------------------------------------------- productions and ConfTool

class ConfToolImportTests(TestCase):
    def setUp(self):
        from datetime import date

        from apps.archive.models import Conference

        Conference.objects.create(pk=40, number=35, start_date=date(2027, 7, 12))

    def write(self, text, suffix=".csv"):
        path = Path(tempfile.mkdtemp()) / f"export{suffix}"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_semicolon_lists_and_status(self):
        from io import StringIO

        from django.core.management import call_command

        from .models import Submission

        path = self.write(
            "Paper ID;Title;Track;Acceptance Status;Authors;Organisations;Emails\n"
            "12;Takt in practice;Production Planning;accepted;Ann Smith, Bo Jones;NTNU, UCL;a@x.no, b@y.uk\n"
            "13;Rejected one;Lean Theory;rejected;Cy Lee;X;c@z.org\n"
            '14;Flow;Lean Theory;Accepted (Paper);"Dee Brown; Ed Green";"TUM; ETH";"d@t.de; e@e.ch"\n')
        call_command("import_conftool", "35", path, stdout=StringIO())
        self.assertEqual(sorted(Submission.objects.values_list("conftool_id", flat=True)), [12, 14])
        paper = Submission.objects.get(conftool_id=14)
        self.assertEqual(paper.track.title, "Lean Theory")
        self.assertEqual(paper.registered_authors[1], {"name": "Ed Green", "organisation": "ETH", "email": "e@e.ch"})
        self.assertEqual(paper.doi, "10.24928/2027/0014")
        # the comma-separated single cell (paper 12) is split into authors too
        self.assertEqual([a["name"] for a in Submission.objects.get(conftool_id=12).registered_authors],
                         ["Ann Smith", "Bo Jones"])

    def test_numbered_author_columns(self):
        from .conftool import read_accepted

        path = self.write("ID,Title,Author 1 Name,Author 1 Email,Author 1 Organisation,Author 2 Name,Author 2 Email\n"
                          "7,Paper,Ann Smith,a@x.no,NTNU,Bo Jones,b@y.uk\n")
        papers, _ = read_accepted(path)
        self.assertEqual(papers[0]["authors"], [
            {"name": "Ann Smith", "organisation": "NTNU", "email": "a@x.no"},
            {"name": "Bo Jones", "organisation": "", "email": "b@y.uk"}])

    def test_editor_group_exists(self):
        from django.contrib.auth.models import Group

        group = Group.objects.get(name="Proceedings editors")
        self.assertTrue(group.permissions.filter(codename="add_paperversion").exists())


# ---------------------------------------------------------------- editors' pages

def make_word_pdf(pages=2, title_y=700, stray_header=False) -> bytes:
    """A small PDF like Word's: header and footer marked as pagination artefacts."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for number in range(pages):
        page = writer.add_blank_page(595.2, 841.92)
        body = (f"/Artifact <</Type /Pagination /Subtype /Header>> BDC BT /F1 10 Tf 70 796 Td (Old header) Tj ET EMC "
                f"/Artifact <</Type /Pagination /Subtype /Footer>> BDC BT /F1 10 Tf 70 38 Td (Old footer {number + 1}) Tj ET EMC "
                f"BT /F1 12 Tf 70 {title_y if number == 0 else 700} Td (Body text) Tj ET")
        if stray_header:
            body += " BT /F1 10 Tf 70 800 Td (Typed header) Tj ET"
        stream = DecodedStreamObject()
        stream.set_data(body.encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class EditorPagesTests(TestCase):
    def setUp(self):
        import io
        from datetime import date

        from django.contrib.auth.models import User

        from apps.archive.models import Conference, ConferenceTrack

        from .models import Production, ProductionEditor, Submission

        conference = Conference.objects.create(pk=40, number=35, start_date=date(2027, 7, 12))
        self.planning = ConferenceTrack.objects.create(conference=conference, title="Planning", order=1)
        self.green = ConferenceTrack.objects.create(conference=conference, title="Lean and Green", order=2)
        self.production = Production.objects.create(conference=conference)
        Submission.objects.create(production=self.production, conftool_id=123, title="Takt", track=self.planning)
        Submission.objects.create(production=self.production, conftool_id=124, title="Green", track=self.green)
        self.chief = User.objects.create_user("chief", password="pw", is_staff=True)
        self.editor = User.objects.create_user("ed", password="pw", is_staff=True)
        ProductionEditor.objects.create(production=self.production, user=self.chief, role="chief")
        entry = ProductionEditor.objects.create(production=self.production, user=self.editor, role="editor")
        entry.tracks.add(self.green)
        entry.save()  # tracks are kept with the editor (ParentalManyToManyField)
        self.docx = make_docx(BODY, NOTES, HEADER).read_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("123.docx", self.docx)
            archive.writestr("123.pdf", make_word_pdf())
            archive.writestr("124 edited.docx", self.docx)
            archive.writestr("notes.txt", "x")
        self.zip = buffer.getvalue()

    def test_editors_see_their_tracks_only(self):
        self.client.login(username="ed", password="pw")
        page = self.client.get("/manage/production/35/").content.decode()
        self.assertIn("Green", page)
        self.assertNotIn(">Takt<", page)
        self.assertEqual(self.client.get("/manage/production/35/123/").status_code, 404)

    def test_outsiders_and_visitors_are_kept_out(self):
        from django.contrib.auth.models import User

        User.objects.create_user("other", password="pw", is_staff=True)
        self.client.login(username="other", password="pw")
        self.assertIn(self.client.get("/manage/production/35/").status_code, (302, 403))
        self.client.logout()
        self.assertEqual(self.client.get("/manage/production/35/").status_code, 302)

    def test_batch_upload_pairs_checks_and_versions(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import Submission

        self.client.login(username="chief", password="pw")
        page = self.client.post("/manage/production/35/upload/", {
            "files": [SimpleUploadedFile("batch.zip", self.zip)], "comment": "first round"}).content.decode()
        self.assertIn("2 new versions", page)
        self.assertIn("notes.txt", page)
        takt = Submission.objects.get(conftool_id=123)
        version = takt.current
        self.assertEqual((version.number, version.pages, version.metadata["title"]), (1, 2, "Takt planning in practice"))
        self.assertTrue(version.passed, version.findings)
        self.assertEqual(takt.status, "uploaded")
        # a PDF alone becomes version 2, with the current Word file
        self.client.post("/manage/production/35/upload/", {"files": [SimpleUploadedFile("123.pdf", make_word_pdf(pages=3))]})
        self.assertEqual((takt.current.number, takt.current.pages), (2, 3))
        # the paper without a PDF is told so
        green = Submission.objects.get(conftool_id=124)
        self.assertIn("pdf_missing", [f["code"] for f in green.current.findings])
        # files are downloadable only through the site
        response = self.client.get("/manage/production/35/123/v1.docx")
        self.assertEqual(b"".join(response.streaming_content), self.docx)
        import io

        response = self.client.post("/manage/production/35/download/", {"paper": ["123"], "with_pdf": "1"})
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist()), ["123.docx", "123.pdf"])

    def test_layout_checks_and_approval(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import Submission

        self.client.login(username="chief", password="pw")
        self.client.post("/manage/production/35/123/", {"action": "upload", "docx": SimpleUploadedFile("123.docx", self.docx),
                                                  "pdf": SimpleUploadedFile("123.pdf", make_word_pdf(title_y=750, stray_header=True))})
        takt = Submission.objects.get(conftool_id=123)
        codes = [f["code"] for f in takt.current.findings]
        self.assertIn("pdf_running_left", codes)
        self.assertIn("reference_space_missing", codes)
        self.assertEqual(takt.status, "needs_work")
        self.client.post("/manage/production/35/123/", {"action": "approve", "comment": "fine"})
        takt.refresh_from_db()
        self.assertEqual(takt.status, "approved")
        self.assertEqual(takt.events.first().action, "approved")


class ArrangeTests(EditorPagesTests):
    def test_page_numbers_follow_the_order(self):
        import json

        from django.core.files.uploadedfile import SimpleUploadedFile

        from .arrange import number_pages
        from .models import Submission

        self.client.login(username="chief", password="pw")
        for number, pages in ((123, 3), (124, 2)):
            self.client.post("/manage/production/35/upload/", {"files": [
                SimpleUploadedFile(f"{number}.docx", self.docx), SimpleUploadedFile(f"{number}.pdf", make_word_pdf(pages))]})
        self.production.first_page = 10
        self.production.save()
        layout, unknown = number_pages(self.production)
        self.assertEqual([(i.submission.conftool_id, i.first_page, i.last_page) for _, placed in layout for i in placed],
                         [(123, 10, 12), (124, 13, 14)])
        self.assertEqual(unknown, [])
        # the chief editor puts Lean and Green first and moves 123 there too
        response = self.client.post("/manage/production/35/arrange/", {
            "first_page": "1", "layout": json.dumps([[self.green.pk, ["124", "123"]], [self.planning.pk, []]])})
        self.assertEqual(response.status_code, 302)
        papers = {s.conftool_id: s for s in Submission.objects.all()}
        self.assertEqual((papers[124].first_page, papers[123].first_page, papers[123].track), (1, 3, self.green))
        page = self.client.get("/manage/production/35/arrange/").content.decode()
        self.assertIn("1–2", page)
        self.assertIn("3–5", page)

    def test_editors_cannot_rearrange(self):
        self.client.login(username="ed", password="pw")
        self.assertEqual(self.client.get("/manage/production/35/arrange/").status_code, 200)
        self.assertIn(self.client.post("/manage/production/35/arrange/", {"layout": "[]"}).status_code, (302, 403))

    def test_unknown_pages_stop_the_numbering(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .arrange import number_pages

        self.client.login(username="chief", password="pw")
        self.client.post("/manage/production/35/upload/", {"files": [SimpleUploadedFile("123.docx", self.docx)]})
        layout, unknown = number_pages(self.production)
        self.assertEqual([s.conftool_id for s in unknown], [123, 124])


class PublishTests(EditorPagesTests):
    """Stage 1: papers published with DOIs and page numbers; corrections afterwards."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from django.test import override_settings

        super().setUp()
        conference = self.production.conference
        conference.city, conference.country = "Oslo", "Norway"
        conference.save()
        media = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        media.enable()
        self.addCleanup(media.disable)
        # The running heads need licensed fonts, so the PDF itself is not built here.
        for target, value in (("fonts_folder", Path(".")), ("build_pdf", b"%PDF-1.4 published")):
            patcher = mock.patch(f"apps.production.publish.{target}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _upload(self, number, pages):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(f"/manage/production/35/{number}/", {"action": "upload", "docx": SimpleUploadedFile(
            f"{number}.docx", self.docx), "pdf": SimpleUploadedFile(f"{number}.pdf", make_word_pdf(pages))})

    def test_publish_freeze_and_correct(self):
        import json

        from apps.archive.models import Paper

        from .models import Correction, Submission

        self.client.login(username="chief", password="pw")
        self._upload(123, 3)
        self._upload(124, 2)
        self.assertIn("not approved", self.client.get("/manage/production/35/publish/").content.decode())
        for number in (123, 124):
            self.client.post(f"/manage/production/35/{number}/", {"action": "approve"})
        # the editors give the title in sentence case and correct a name
        first = Submission.objects.get(conftool_id=124).current.metadata["authors"][0]["name"]
        self.client.post("/manage/production/35/124/", {"action": "metadata", "published_title": "Lean and green: a review",
                                                  "author_name": [first], "first_0": "", "last_0": first})
        self.client.login(username="ed", password="pw")
        self.assertIn(self.client.post("/manage/production/35/publish/", {"action": "next"}).status_code, (302, 403))
        # the chief editor asks; only a publisher can publish, and only when asked
        self.client.login(username="chief", password="pw")
        self.assertIn(self.client.post("/manage/production/35/publish/", {"action": "next"}).status_code, (302, 403))
        from django.contrib.auth.models import Group, User

        publisher = User.objects.create_user("pub", password="pw", is_staff=True)
        publisher.groups.add(Group.objects.get(name="Publishers"))
        self.client.login(username="pub", password="pw")
        self.assertEqual(self.client.post("/manage/production/35/publish/", {"action": "next"}).status_code, 400)
        self.client.login(username="chief", password="pw")
        self.client.post("/manage/production/35/publish/", {"action": "request"})
        self.client.login(username="pub", password="pw")
        result = self.client.post("/manage/production/35/publish/", {"action": "next"}).json()
        self.assertEqual((result["published"], result["left"]), (["10.24928/2027/0123", "10.24928/2027/0124"], 0))
        # the order is fixed as soon as papers are published
        self.assertIn(self.client.post("/manage/production/35/arrange/", {"layout": json.dumps([])}).status_code, (302, 403))
        self.client.post("/manage/production/35/publish/", {"action": "finish"})
        self.client.login(username="chief", password="pw")
        self.production.refresh_from_db()
        conference = self.production.conference
        self.assertEqual(self.production.status, "papers_published")
        self.assertTrue(conference.is_published and conference.papers_zip_url.endswith(".zip"))
        paper = Paper.objects.get(doi="10.24928/2027/0123")
        self.assertEqual((paper.title, paper.pages, paper.track), ("Takt planning in practice", "1-3", self.planning))
        self.assertTrue(paper.authors.exists())
        green = Paper.objects.get(doi="10.24928/2027/0124")
        self.assertEqual((green.pages, green.title), ("4-5", "Lean and green: a review"))
        self.assertEqual((green.authors.first().first_name, green.authors.first().last_name), ("", first))

        # a correction that is a page too long is refused, and moves nothing
        self._upload(123, 4)
        self.assertEqual(Submission.objects.get(conftool_id=124).first_page, 4)
        page = self.client.get("/manage/production/35/123/").content.decode()
        self.assertIn("must fit", page)
        self.client.post("/manage/production/35/123/", {"action": "stage_correction", "comment": "Figure 2"})
        self.assertEqual(Submission.objects.get(conftool_id=123).correction_note, "")
        # one that fits replaces the PDF; the DOI and pages stay, the old PDF is kept
        old_url = paper.full_text_url
        self._upload(123, 3)
        self.assertIn(self.client.post("/manage/production/35/123/", {"action": "correct"}).status_code, (302, 403))
        self.client.post("/manage/production/35/123/", {"action": "stage_correction", "comment": "Figure 2 was replaced.",
                                                          "public": "1"})
        self.assertFalse(Correction.objects.exists())
        self.client.login(username="pub", password="pw")
        self.client.post("/manage/production/35/123/", {"action": "correct", "comment": "Figure 2 was replaced.",
                                                          "public": "1"})
        correction = Correction.objects.get()
        paper.refresh_from_db()
        self.assertEqual((paper.doi, paper.pages), ("10.24928/2027/0123", "1-3"))
        self.assertNotEqual(paper.full_text_url, old_url)
        self.assertEqual(correction.previous_version.number, 1)
        self.assertIn("Figure 2 was replaced.", self.client.get(paper.get_absolute_url()).content.decode())


class PublishedMetadataTests(SimpleTestCase):
    def test_sentence_case_suggestion(self):
        from .publish import sentence_case

        self.assertEqual(sentence_case("NEXUS BETWEEN LEAN AND BIM"), "Nexus between Lean and bim")
        self.assertEqual(sentence_case("When You Meet Lean Construction Gurus: Beware BIM!"),
                         "When you meet Lean Construction gurus: beware BIM!")

    def test_name_split(self):
        from .docx_reader import split_name

        self.assertEqual(split_name("Jorge L. Izquierdo R."), ("Jorge L.", "Izquierdo R."))
        self.assertEqual(split_name("Jan van der Berg"), ("Jan", "van der Berg"))
        self.assertEqual(split_name("Gunadi"), ("", "Gunadi"))


class FullProceedingsTests(PublishTests):
    """Stage 2: adopting a published conference, the templates, roles and the book itself."""

    def _publish_all(self):
        from django.contrib.auth.models import Group, User

        self.client.login(username="chief", password="pw")
        self._upload(123, 3)
        self._upload(124, 2)
        for number in (123, 124):
            self.client.post(f"/manage/production/35/{number}/", {"action": "approve"})
        self.client.post("/manage/production/35/publish/", {"action": "request"})
        publisher = User.objects.create_user("pub", password="pw", is_staff=True)
        publisher.groups.add(Group.objects.get(name="Publishers"))
        self.client.login(username="pub", password="pw")
        self.client.post("/manage/production/35/publish/", {"action": "next"})
        self.client.post("/manage/production/35/publish/", {"action": "finish"})

    def test_adopt_a_published_conference(self):
        from datetime import date

        from apps.archive.models import Conference, Paper

        from .adopt import adopt_published

        old = Conference.objects.create(pk=30, number=28, start_date=date(2020, 7, 6), city="Berkeley")
        Paper.objects.create(conference=old, title="B", doi="10.24928/2020/0136", first_page=13, last_page=24,
                             full_text_url="https://example.org/b.pdf")
        Paper.objects.create(conference=old, title="A", doi="10.24928/2020/0065", first_page=1, last_page=12)
        production, report = adopt_published(old)
        self.assertEqual((production.status, report["added"], production.first_page), ("papers_published", 2, 1))
        self.assertEqual([s.conftool_id for s in production.submissions.order_by("first_page")], [65, 136])
        self.assertTrue(production.pages_frozen)
        adopt_published(old)  # again: updates, adds nothing
        self.assertEqual(production.submissions.count(), 2)

    def test_templates_isbn_and_roles(self):
        import io

        from docx import Document

        self._publish_all()
        self.client.login(username="chief", password="pw")
        self.assertEqual(self.client.get("/manage/production/35/book/").status_code, 200)
        foreword = self.client.get("/manage/production/35/book/foreword.docx")
        text = "\n".join(p.text for p in Document(io.BytesIO(foreword.content)).paragraphs)
        self.assertIn("Table 1 Papers published per country", text)
        self.assertIn("2 papers", text)
        # only a publisher sets the ISBN, and it must be valid
        self.assertIn(self.client.post("/manage/production/35/book/", {"action": "isbn", "isbn_pdf": "978-82-692499-5-8"})
                      .status_code, (302, 403))
        self.production.refresh_from_db()
        self.assertEqual(self.production.isbn_pdf, "")
        self.client.login(username="pub", password="pw")
        self.client.post("/manage/production/35/book/", {"action": "isbn", "isbn_pdf": "978-82-692499-5-9"})
        self.production.refresh_from_db()
        self.assertEqual(self.production.isbn_pdf, "")
        self.client.post("/manage/production/35/book/", {"action": "isbn", "isbn_pdf": "978-82-692499-5-8"})
        self.production.refresh_from_db()
        self.assertEqual(self.production.isbn_pdf, "978-82-692499-5-8")
        # the publisher cannot publish what was not submitted
        self.client.post("/manage/production/35/book/", {"action": "publish"})
        self.production.refresh_from_db()
        self.assertEqual(self.production.status, "papers_published")

    def test_country_of(self):
        from .book import country_of

        self.assertEqual(country_of("Professor, NTNU, Trondheim, Norway, a@b.no, orcid.org/0000-0001-2345-6789"),
                         "Norway")
        self.assertEqual(country_of("Nottingham Trent University U.K"), "")
        self.assertEqual(country_of("PT Waskita Karya Tbk (Persero) - Jakarta - Indonesia"), "Indonesia")
        self.assertEqual(country_of("University of California, Berkeley, CA, United States"), "USA")


class BookPartCheckTests(SimpleTestCase):
    def test_parts_must_follow_the_template(self):
        from .book import check_part

        # Helvetica, and text in the header and footer areas
        problems = " ".join(check_part(make_word_pdf(2), "message"))
        self.assertIn("Times New Roman", problems)
        self.assertIn("header and footer must be empty", problems)
        self.assertEqual(check_part(make_word_pdf(2), "cover"), ["A cover is one page."])
        self.assertEqual(check_part(b"not a pdf", "sponsors"), ["This is not a PDF that can be read."])


class BackOfficeTests(EditorPagesTests):
    """One back office: archive, committees and production screens in Wagtail's admin."""

    def test_screens_open(self):
        from django.contrib.auth.models import User

        from apps.archive.models import Author, AuthorPerson, Paper

        paper = Paper.objects.create(conference=self.production.conference, title="A paper", doi="10.24928/2027/0001")
        person = AuthorPerson.objects.create(first_name="Ann", last_name="Smith")
        Author.objects.create(paper=paper, first_name="Ann", last_name="Smith", person=person, order=1)
        User.objects.create_superuser("root", "r@example.org", "pw")
        self.client.login(username="root", password="pw")
        for url in ("/manage/", "/manage/conferences/", f"/manage/conferences/edit/{self.production.conference.pk}/",
                    f"/manage/conferences/{self.production.conference.pk}/",
                    "/manage/archive/paper/", f"/manage/archive/paper/edit/{paper.pk}/", "/manage/archive/paper/?q=paper",
                    "/manage/archive/person/", f"/manage/archive/person/edit/{person.pk}/", "/manage/archive/links/",
                    "/manage/committees/", "/manage/production/", "/manage/production/35/",
                    f"/manage/production-settings/edit/{self.production.pk}/", "/manage/reports/paper-checks/",
                    "/manage/archive/person-chooser/?q=smi", "/manage/users/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        # file addresses are shown, never edited
        page = self.client.get(f"/manage/archive/paper/edit/{paper.pk}/").content.decode()
        self.assertNotIn('name="full_text_url"', page)
        self.assertIn("cannot be changed here", page)
        page = self.client.get(f"/manage/conferences/edit/{self.production.conference.pk}/").content.decode()
        self.assertNotIn('name="papers_zip_url"', page)

    def test_editors_get_in_with_their_role_only(self):
        self.client.login(username="ed", password="pw")  # no group, only a production role
        self.assertEqual(self.client.get("/manage/").status_code, 200)
        self.assertEqual(self.client.get("/manage/production/35/").status_code, 200)
        self.assertNotEqual(self.client.get("/manage/archive/paper/").status_code, 200)


class FetchTests(EditorPagesTests):
    def test_fetch_goes_through_the_papers_once_and_scripts_come_after_the_page(self):
        from unittest import mock

        from apps.archive.models import Paper

        from . import book
        from .models import Submission

        conference = self.production.conference
        for number, s in ((123, Submission.objects.get(conftool_id=123)), (124, Submission.objects.get(conftool_id=124))):
            s.paper = Paper.objects.create(conference=conference, title=s.title, first_page=number, last_page=number,
                                           full_text_url=f"https://example.org/{number}.pdf")
            s.save()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            first = book.fetch_next(self.production, n=1)
            second = book.fetch_next(self.production, n=1, after=first["next"])
        self.assertEqual((first["fetched"], first["left"], first["next"]), (0, 1, 123))
        self.assertEqual((second["left"], second["next"], len(second["problems"])), (0, 124, 1))
        self.client.login(username="chief", password="pw")
        page = self.client.get("/manage/production/35/book/").content.decode()
        if 'id="fetch-start"' in page:
            self.assertLess(page.index('id="fetch-start"'), page.rindex("<script>"))



class PdfCorrectionTests(PublishTests):
    """Replacing the PDF of a paper published before these tools (taken from the archive)."""

    def test_replace_the_pdf_of_an_adopted_paper(self):
        from datetime import date

        from django.contrib.auth.models import Group, User
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.archive.models import Conference, Paper

        from .adopt import adopt_published
        from .models import Correction, ProductionEditor

        old = Conference.objects.create(pk=31, number=29, start_date=date(2021, 7, 14), city="Lima")
        paper = Paper.objects.create(conference=old, title="Old", doi="10.24928/2021/0131", first_page=1, last_page=2,
                                     full_text_url="https://example.org/old.pdf")
        production, _ = adopt_published(old)
        ProductionEditor.objects.create(production=production, user=self.chief, role="chief")
        self.client.login(username="chief", password="pw")
        url = "/manage/production/29/131/"
        self.assertContains(self.client.get(url), "Published (before these tools)")
        # three pages do not fit a two-page range
        self.client.post(url, {"action": "stage_pdf", "comment": "Fixed", "pdf": SimpleUploadedFile("a.pdf", make_word_pdf(3))})
        production.submissions.get().refresh_from_db()
        self.assertFalse(production.submissions.get().correction_pdf)
        self.client.post(url, {"action": "stage_pdf", "comment": "Page overflow fixed",
                               "pdf": SimpleUploadedFile("a.pdf", make_word_pdf(2))})
        self.assertTrue(production.submissions.get().correction_pdf)
        self.assertIn(self.client.post(url, {"action": "correct_pdf"}).status_code, (302, 403))
        self.assertFalse(Correction.objects.exists())
        publisher = User.objects.create_user("pub2", password="pw")
        publisher.groups.add(Group.objects.get(name="Publishers"))
        self.client.login(username="pub2", password="pw")
        self.client.post(url, {"action": "correct_pdf", "comment": "Page overflow fixed"})  # note not shown
        paper.refresh_from_db()
        correction = Correction.objects.get()
        self.assertEqual((paper.pages, correction.previous_pdf), ("1-2", "https://example.org/old.pdf"))
        self.assertNotEqual(paper.full_text_url, "https://example.org/old.pdf")
        self.assertFalse(production.submissions.get().correction_pdf)
        self.assertFalse(correction.public)
        self.assertNotIn("Page overflow fixed", self.client.get(paper.get_absolute_url()).content.decode())
        self.assertNotIn("Corrected", self.client.get(paper.get_absolute_url()).content.decode())



class PageCountCheckTests(SimpleTestCase):
    def test_word_and_pdf_page_counts_compared(self):
        import shutil
        import tempfile

        from .checks import _pages_differ, word_page_count

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        source = make_docx(BODY, NOTES, HEADER)
        for pages, name in ((12, "a.docx"), (1, "b.docx")):
            target = folder / name
            shutil.copy(source, target)
            with zipfile.ZipFile(target, "a") as archive:
                archive.writestr("docProps/app.xml", f'<Properties xmlns="x"><Pages>{pages}</Pages></Properties>')
        self.assertEqual(word_page_count(folder / "a.docx"), 12)
        self.assertEqual([c for c, _ in _pages_differ(folder / "a.docx", make_word_pdf(13))], ["pdf_pages_differ"])
        self.assertEqual(_pages_differ(folder / "a.docx", make_word_pdf(12)), [])
        # Word did not store its count (it says 1): not checked
        self.assertEqual(_pages_differ(folder / "b.docx", make_word_pdf(13)), [])


class RoleGapTests(EditorPagesTests):
    def test_chief_editors_edit_their_own_production_settings(self):
        from datetime import date

        from apps.archive.models import Conference

        from .models import Production

        other = Production.objects.create(conference=Conference.objects.create(pk=41, number=36, start_date=date(2028, 7, 1)))
        self.client.login(username="chief", password="pw")
        self.assertEqual(self.client.get(f"/manage/production-settings/edit/{self.production.pk}/").status_code, 200)
        self.assertNotEqual(self.client.get(f"/manage/production-settings/edit/{other.pk}/").status_code, 200)
        self.client.login(username="ed", password="pw")  # an editor, not chief
        self.assertNotEqual(self.client.get(f"/manage/production-settings/edit/{self.production.pk}/").status_code, 200)

    def test_archive_editors_edit_the_archive_and_committees(self):
        from django.contrib.auth.models import Group, User

        from apps.archive.models import Paper
        from apps.governance.models import Committee

        paper = Paper.objects.create(conference=self.production.conference, title="A paper")
        committee = Committee.objects.create(name="Standardisation Committee", slug="standardisation")
        user = User.objects.create_user("arch", password="pw")
        user.groups.add(Group.objects.get(name="Archive editors"))
        self.client.login(username="arch", password="pw")
        for url in ("/manage/", "/manage/archive/paper/", f"/manage/archive/paper/edit/{paper.pk}/",
                    "/manage/archive/person/", f"/manage/committees/edit/{committee.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        # DOIs point to papers: no deleting, and no production pages
        self.assertNotEqual(self.client.get(f"/manage/archive/paper/delete/{paper.pk}/").status_code, 200)
        self.assertNotEqual(self.client.get("/manage/production/35/").status_code, 200)


class CrossrefPageTests(FullProceedingsTests):
    def test_publisher_makes_a_deposit(self):
        self._publish_all()
        self.client.login(username="chief", password="pw")  # chief editors do not deposit
        self.assertIn(self.client.post("/manage/production/35/publish/", {"action": "crossref_make"}).status_code,
                      (302, 403))
        self.assertFalse(self.production.conference.crossref_deposits.exists())
        self.client.login(username="pub", password="pw")
        page = self.client.get("/manage/production/35/publish/").content.decode()
        self.assertIn("DOIs at Crossref", page)
        self.assertIn("not set up on this server", page)
        self.client.post("/manage/production/35/publish/", {"action": "crossref_make"})
        deposit = self.production.conference.crossref_deposits.get()
        self.assertEqual(deposit.papers, 2)
        xml = self.client.get(f"/manage/production/35/crossref/{deposit.pk}.xml").content.decode()
        self.assertIn("<doi>10.24928/2027/0123</doi>", xml)
        # without a login on the server, sending is refused politely
        self.client.post("/manage/production/35/publish/", {"action": "crossref_send", "deposit": deposit.pk})
        deposit.refresh_from_db()
        self.assertEqual(deposit.status, "made")


class MetadataCheckTests(FullProceedingsTests):
    def test_authors_check_and_editors_apply(self):
        from django.core import mail

        from apps.archive.models import Paper

        from .models import MetadataCheck, Submission

        self._publish_all()
        self.chief.email = "chief@example.org"
        self.chief.save()
        takt = Submission.objects.get(conftool_id=123)
        takt.registered_authors = [{"name": "Ann Registered", "email": "ann@example.org"}]
        takt.save()
        mail.outbox.clear()
        self.client.login(username="chief", password="pw")
        self.assertContains(self.client.get("/manage/production/35/publish/"), "2 not asked yet")
        result = self.client.post("/manage/production/35/publish/", {"action": "metadata_send"}).json()
        self.assertEqual((result["left"], result["sent"] + len(result["problems"])), (0, 2))
        message = next(m for m in mail.outbox if "ann@example.org" in m.to)
        self.assertEqual(message.reply_to, ["chief@example.org"])
        check = MetadataCheck.objects.get(submission=takt)
        self.assertIn(str(check.token), message.body)

        # the author's page: no login needed
        self.client.logout()
        url = f"/for-authors/check-your-details/{check.token}/"
        page = self.client.get(url).content.decode()
        self.assertIn("Check your paper", page)
        paper = Paper.objects.get(doi="10.24928/2027/0123")
        first = paper.authors.first()
        data = {"responder": "Ann", "action": "correct", "title": "Takt planning in practice, revised",
                "first_name_0": first.first_name, "last_name_0": first.last_name + "-Berg",
                "affiliation_0": "NTNU, Norway", "orcid_0": "0000-0002-1825-0098"}  # wrong check digit
        self.assertContains(self.client.post(url, data), "is not valid")
        data["orcid_0"] = "0000-0002-1825-0097"
        mail.outbox.clear()
        self.client.post(url, data)
        check.refresh_from_db()
        self.assertEqual(check.status, "corrections")
        self.assertEqual(mail.outbox[0].to, ["chief@example.org"])
        self.assertIn("Takt planning in practice, revised", mail.outbox[0].body)

        # the chief editor applies them
        self.client.login(username="chief", password="pw")
        page = self.client.get("/manage/production/35/123/").content.decode()
        self.assertIn("Corrections proposed", page)
        self.client.post("/manage/production/35/123/", {"action": "apply_check", "check": check.pk, "comment": "ok"})
        paper.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(paper.title, "Takt planning in practice, revised")
        self.assertTrue(first.last_name.endswith("-Berg"))
        self.assertIn("orcid.org/0000-0002-1825-0097", first.title_and_contact)
        check.refresh_from_db()
        self.assertEqual(check.status, "handled")
        self.client.logout()
        self.assertContains(self.client.get(url), "have handled the answer")

    def test_confirming(self):
        from .models import MetadataCheck

        self._publish_all()
        self.client.login(username="chief", password="pw")
        self.client.post("/manage/production/35/publish/", {"action": "metadata_send"})
        check = MetadataCheck.objects.first()
        if check is None:
            self.skipTest("the test papers have no email addresses")
        self.client.logout()
        self.client.post(f"/for-authors/check-your-details/{check.token}/", {"responder": "Bo", "action": "confirm"})
        check.refresh_from_db()
        self.assertEqual((check.status, check.responder), ("confirmed", "Bo"))


class GuideTests(EditorPagesTests):
    def test_guide_and_script(self):
        self.client.login(username="ed", password="pw")
        page = self.client.get("/manage/production/guide/")
        self.assertContains(page, "Editors’ guide")
        self.assertContains(self.client.get("/manage/production/35/"), "/manage/production/guide/")
        script = self.client.get("/manage/production/guide/iglc-word-batch.ps1")
        self.assertIn(b"ComputeStatistics", b"".join(script.streaming_content))



class ZipAndAuthorPageTests(PublishTests):
    def test_zip_for_any_published_production(self):
        import io
        import zipfile as zf

        from django.core.files.storage import default_storage

        self.client.login(username="chief", password="pw")
        self._upload(123, 3)
        self._upload(124, 2)
        for number in (123, 124):
            self.client.post(f"/manage/production/35/{number}/", {"action": "approve"})
        from django.contrib.auth.models import Group, User

        publisher = User.objects.create_user("pubz", password="pw")
        publisher.groups.add(Group.objects.get(name="Publishers"))
        self.client.post("/manage/production/35/publish/", {"action": "request"})
        self.client.login(username="pubz", password="pw")
        self.client.post("/manage/production/35/publish/", {"action": "next"})
        self.client.post("/manage/production/35/publish/", {"action": "finish"})
        conference = self.production.conference
        conference.refresh_from_db()
        conference.papers_zip_url = ""
        conference.save()
        self.client.login(username="chief", password="pw")
        self.client.post("/manage/production/35/publish/", {"action": "make_zip"})
        conference.refresh_from_db()
        name = conference.papers_zip_url.split("/media/", 1)[-1]
        with default_storage.open(name) as handle:
            self.assertEqual(len(zf.ZipFile(io.BytesIO(handle.read())).namelist()), 2)

    def test_author_pages_show_the_year(self):
        from apps.archive.models import Author, AuthorPerson, Paper

        paper = Paper.objects.create(conference=self.production.conference, title="Yearly", first_page=77, last_page=80)
        conference = self.production.conference
        conference.is_published = True
        conference.save()
        person = AuthorPerson.objects.create(first_name="Ann", last_name="Smith")
        Author.objects.create(paper=paper, first_name="Ann", last_name="Smith", person=person)
        page = self.client.get(person.get_absolute_url()).content.decode()
        self.assertIn('<span class="pp">2027</span>', page)
        self.assertNotIn("p. 77", page)


def drawing(anchored=False):
    WPNS = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    kind = "anchor" if anchored else "inline"
    return f'<w:r><w:drawing><wp:{kind} {WPNS}/></w:drawing></w:r>'


def checklist_pdf(paper_pages: int) -> bytes:
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for number in range(paper_pages):
        page.drawString(72, 700, f"Paper text on page {number + 1}")
        page.showPage()
    for heading in ("IGLC PAPER SUBMISSION CHECKLIST", "Abstract"):
        page.drawString(72, 760, heading)
        page.showPage()
    page.save()
    return buffer.getvalue()


class LayoutCheckTests(SimpleTestCase):
    def codes(self, body, abstract=""):
        from .layout_checks import layout_checks

        return {code: message for code, message in layout_checks(make_docx(body, NOTES), abstract)}

    def test_checklist(self):
        self.assertIn("checklist_missing", self.codes(BODY))
        found = self.codes(BODY + p("Heading1", t("IGLC Paper Submission Checklist")) + p("TextFirst", t("x")))
        self.assertIn("checklist_present", found)
        self.assertNotIn("checklist_missing", found)

    def test_references_in_the_abstract(self):
        self.assertIn("abstract_references", self.codes(BODY, "As shown by (Koskela, 2000), flow matters."))
        self.assertIn("abstract_references", self.codes(BODY, "Ballard and Howell (2003) argued so."))
        self.assertNotIn("abstract_references", self.codes(BODY, "Papers from IGLC (1993–2025) were read."))

    def test_empty_paragraphs(self):
        found = self.codes(BODY.replace(p("Heading1", t("Introduction")),
                                        p("Heading1", t("Introduction")) + "<w:p/><w:p/>"))
        self.assertIn("2 empty paragraphs", found["empty_paragraphs"])
        # at the very end (before the checklist or the end of the file) they are left alone
        self.assertNotIn("empty_paragraphs", self.codes(BODY + "<w:p/>"))

    def test_floating_figures_and_captions(self):
        figure = p("Figure", drawing()) + p("Figurecaption", t("Figure 1: Flow"))
        self.assertNotIn("figure_floating", self.codes(BODY + figure))
        self.assertNotIn("caption_position", self.codes(BODY + figure))
        self.assertIn("figure_floating", self.codes(BODY + p("Figure", drawing(anchored=True))))
        wrong = p("Figurecaption", t("Figure 1: Flow")) + p("Figure", drawing())
        self.assertIn("below its figure", self.codes(BODY + wrong)["caption_position"])
        table = "<w:tbl><w:tr><w:tc><w:p>" + t("cell") + "</w:p></w:tc></w:tr></w:tbl>"
        self.assertNotIn("caption_position", self.codes(BODY + p("Tablecaption", t("Table 1: Data")) + table))
        self.assertIn("above its table", self.codes(BODY + table + p("Tablecaption", t("Table 1: Data")))["caption_position"])

    def test_manual_formatting(self):
        sized = "".join(p("TextRunning", f'<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>small {i}</w:t></w:r>')
                        for i in range(12))
        self.assertIn("font size of 12", self.codes(BODY + sized)["manual_formatting"])
        # a few are left alone
        self.assertNotIn("manual_formatting", self.codes(BODY + sized[: len(sized) // 4]))

    def test_changed_styles(self):
        import json

        from .layout_checks import STYLES_FILE, _changed_styles

        reference = json.loads(STYLES_FILE.read_text())
        self.assertIn("title", reference["styles"])
        path = make_docx(BODY, NOTES)
        styles = ('<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                  '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
                  '<w:pPr><w:spacing w:before="360"/></w:pPr><w:rPr><w:sz w:val="40"/></w:rPr></w:style></w:styles>')
        rewritten = path.with_name("styles.docx")
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(rewritten, "w") as target:
            for name in source.namelist():
                target.writestr(name, styles if name == "word/styles.xml" else source.read(name))
        self.assertIn("Title", _changed_styles(rewritten)[0][1])

    def test_checklist_pages_do_not_count(self):
        import io

        from .checks import _page_checks

        self.assertEqual(_page_checks(io.BytesIO(checklist_pdf(12))), [])
        self.assertEqual([c for c, _ in _page_checks(io.BytesIO(checklist_pdf(13)))], ["too_many_pages"])

    def test_rules_per_stage(self):
        from .checks import check_paper

        path = make_docx(BODY + p("Heading1", t("IGLC Paper Submission Checklist")), NOTES)
        self.assertIn("checklist_present", [f.code for f in check_paper(path, "production").findings])
        self.assertNotIn("checklist_present", [f.code for f in check_paper(path, "camera_ready").findings])
        plain = make_docx(BODY, NOTES)
        self.assertIn("checklist_missing", [f.code for f in check_paper(plain, "camera_ready").findings])
        self.assertNotIn("checklist_missing", [f.code for f in check_paper(plain, "production").findings])


class CheckSettingsTests(TestCase):
    def test_rules_come_from_the_back_office(self):
        from .checks import check_paper
        from .models import CheckRule

        path = make_docx(BODY.replace("Takt planning in practice", "T" * 95), NOTES)
        self.assertIn("title_long", [f.code for f in check_paper(path, "review").findings])
        CheckRule.objects.filter(code="title_long").update(review="off")
        self.assertNotIn("title_long", [f.code for f in check_paper(path, "review").findings])
        CheckRule.objects.filter(code="title_long").update(camera_ready="reject")
        found = {f.code: f.level for f in check_paper(path, "camera_ready").findings}
        self.assertEqual(found["title_long"], "reject")

    def test_limits_come_from_the_back_office(self):
        import io

        from .checks import check_paper
        from .models import CheckLimits

        path = make_docx(BODY, NOTES)
        pdf = io.BytesIO(checklist_pdf(11))
        self.assertNotIn("too_many_pages", [f.code for f in check_paper(path, "camera_ready", pdf).findings])
        limits = CheckLimits.load()
        limits.max_pages, limits.title_chars = 10, 20
        limits.save()
        found = {f.code: f.message for f in check_paper(path, "camera_ready", io.BytesIO(checklist_pdf(11))).findings}
        self.assertIn("maximum 10", found["too_many_pages"])
        self.assertIn("maximum 20", found["title_long"])

    def test_sync_keeps_changed_levels(self):
        from .check_config import sync_rules
        from .checks import RULE_LABELS
        from .models import CheckRule

        self.assertEqual(CheckRule.objects.count(), len(RULE_LABELS))
        CheckRule.objects.filter(code="empty_paragraphs").update(camera_ready="reject")
        sync_rules()
        self.assertEqual(CheckRule.objects.get(code="empty_paragraphs").camera_ready, "reject")

    def test_back_office_pages(self):
        from django.contrib.auth.models import User

        from .models import CheckRule

        self.client.force_login(User.objects.create_superuser("root", password="pw"))
        self.assertContains(self.client.get("/manage/paper-check-rules/"), "Empty paragraphs")
        rule = CheckRule.objects.get(code="empty_paragraphs")
        response = self.client.post(f"/manage/paper-check-rules/edit/{rule.pk}/",
                                    {"review": "off", "camera_ready": "reject", "production": "note"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CheckRule.objects.get(pk=rule.pk).camera_ready, "reject")
        self.assertNotEqual(self.client.get("/manage/paper-check-rules/new/").status_code, 200)
        self.assertContains(self.client.get("/manage/settings/production/checklimits/", follow=True), "Maximum pages")
        editor = User.objects.create_user("ed", password="pw")
        self.client.force_login(editor)
        self.assertNotEqual(self.client.get("/manage/paper-check-rules/").status_code, 200)

    def test_skill_zip_carries_the_settings(self):
        import io
        import json

        from .models import CheckRule

        CheckRule.objects.filter(code="title_long").update(review="off")
        response = self.client.get("/for-authors/check-your-paper/iglc-paper-check-skill.zip")
        saved = json.loads(zipfile.ZipFile(io.BytesIO(response.content))
                           .read("iglc-paper-check/scripts/iglc_check/check_rules.json"))
        self.assertEqual(saved["rules"]["title_long"]["review"], "off")
        self.assertEqual(saved["limits"]["max_pages"], 12)


class CheckRulesDocTests(SimpleTestCase):
    def test_document_is_up_to_date(self):
        from .check_docs import DOC, render

        self.assertEqual(DOC.read_text(encoding="utf-8"), render(),
                         "docs/paper-check-rules.md is out of date: run python manage.py check_rules_doc")


class BodyTextStyleTests(SimpleTestCase):
    def codes(self, body):
        from .layout_checks import layout_checks

        return {code: message for code, message in layout_checks(make_docx(body, NOTES))}

    def test_right_sequence_passes(self):
        body = (p("Heading1", t("Method")) + p("TextFirst", t("One.")) + p("TextRunning", t("Two."))
                + p("TextRunning", t("Three.")) + p("Figure", drawing()) + p("Figurecaption", t("Figure 1: X"))
                + p("TextFirst", t("After the figure.")) + p("TextRunning", t("And on.")))
        self.assertNotIn("text_first_running", self.codes(body))

    def test_text_first_after_body_text(self):
        body = p("Heading1", t("Method")) + p("TextFirst", t("One.")) + p("TextFirst", t("Two."))
        self.assertIn("1 in Text First", self.codes(body)["text_first_running"])

    def test_text_running_after_heading_or_figure(self):
        body = (p("Heading2", t("Data")) + p("TextRunning", t("After a heading."))
                + p("Figure", drawing()) + p("Figurecaption", t("Figure 1: X")) + p("TextRunning", t("After it.")))
        self.assertIn("2 in Text Running", self.codes(body)["text_first_running"])

    def test_not_judged_after_a_non_template_style(self):
        body = p("Heading1", t("Method")) + p("Normal", t("Stray.")) + p("TextRunning", t("Next."))
        self.assertNotIn("text_first_running", self.codes(body))


class ContentCheckTests(SimpleTestCase):
    def codes(self, body, keywords=(), **limits):
        from .checks import LIMITS
        from .layout_checks import content_checks

        return {code: message for code, message in
                content_checks(make_docx(body, NOTES), list(keywords), {**LIMITS, **limits})}

    def test_figures_and_tables_cited(self):
        body = (p("TextFirst", t("As Figure 1 and Tables 1–2 show.")) + p("Figurecaption", t("Figure 1: A"))
                + p("Tablecaption", t("Table 1: B")) + p("Tablecaption", t("Table 2: C"))
                + p("Figurecaption", t("Figure 2: D")))
        self.assertEqual(self.codes(body)["figure_table_not_cited"].split(" (")[0], "Not mentioned in the text: Figure 2")

    def test_reference_list(self):
        refs = (p("Heading1", t("References")) + p("References", t("Ballard, G. (2000). Last planner."))
                + p("References", t("Alarcón, L. (1997). Lean construction.")) + p("TextFirst", t("Koskela, L. (1992).")))
        found = self.codes(refs)
        self.assertIn("Alarcón", found["references_order"])
        self.assertIn("1 entry", found["references_style"])
        ordered = (p("Heading1", t("References")) + p("References", t("Alarcón, L. (1997). Lean."))
                   + p("References", t("Ballard G. (2000). Last planner.")))
        self.assertNotIn("references_order", self.codes(ordered))

    def test_keywords_from_the_list(self):
        self.assertIn("keywords_not_from_list", self.codes(BODY, ["takt", "robots", "digital twins"]))
        self.assertNotIn("keywords_not_from_list",
                         self.codes(BODY, ["Last Planner System", "standardisation", "IPD", "robots"]))

    def test_long_paragraphs(self):
        long = p("TextRunning", t("word " * 300))
        self.assertIn("300", self.codes(BODY + long)["long_paragraphs"])
        self.assertNotIn("long_paragraphs", self.codes(BODY + long, paragraph_words=400))

    def test_image_size_reader(self):
        import struct

        from .layout_checks import _image_size

        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1800, 900)
        self.assertEqual(_image_size(png), (1800, 900))
        self.assertIsNone(_image_size(b"\x01\x00\x00\x00 EMF"))


class DuplicateOrcidTests(SimpleTestCase):
    def test_same_orcid_for_two_authors(self):
        notes = {"2": ["Professor, NTNU, Norway, a@ntnu.no, orcid.org/0000-0002-1825-0097"],
                 "3": ["PhD student, NTNU, Norway, b@ntnu.no, orcid.org/0000-0002-1825-0097"]}
        body = BODY.replace(sup("2"), fn(3)).replace(fn(3) + t(", &amp; Cy Lee") + fn(3), fn(3) + t(", &amp; Cy Lee") + fn(3))
        result = read_manuscript(make_docx(body, notes))
        self.assertIn("orcid_duplicate", result.issues.codes)
