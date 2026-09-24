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
