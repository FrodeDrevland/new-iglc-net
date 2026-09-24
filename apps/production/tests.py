import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

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
          "TextRunning": "Text Running", "Normal": "Normal"}


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
        self.assertIn("1 paragraph in style “normal”", issues)
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
