import io
from datetime import date
from xml.etree import ElementTree as ET

from django.test import TestCase, override_settings

from apps.archive.models import Author, Conference, Paper

from . import deposit as crossref
from .xml import NS, conference_xml, institutions

N = {"c": NS, "jats": "http://www.ncbi.nlm.nih.gov/JATS1"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class CrossrefTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(pk=50, number=35, start_date=date(2027, 7, 12),
                                                    end_date=date(2027, 7, 16), city="Oslo", country="Norway")
        self.paper = Paper.objects.create(conference=self.conference, title="Takt & flow", doi="10.24928/2027/0123",
                                          first_page=1, last_page=12, abstract="First.\n\nSecond.")
        Author.objects.create(paper=self.paper, first_name="Ann", last_name="Smith", order=1,
                              title_and_contact="Professor, Dept. of X, NTNU, Trondheim, Norway, ann@ntnu.no, "
                                                "https://orcid.org/0000-0002-1825-0097")
        Author.objects.create(paper=self.paper, first_name="", last_name="Gunadi", order=2)

    def test_xml(self):
        batch_id, xml = conference_xml(self.conference, [self.paper], depositor=("IGLC", "x@example.org"))
        root = ET.fromstring(xml)
        self.assertEqual(root.get("version"), "5.3.1")
        paper = root.find(".//c:conference_paper", N)
        # schema order: contributors, titles, abstract, publication_date, pages, doi_data
        self.assertEqual([child.tag.split("}")[1] for child in paper],
                         ["contributors", "titles", "abstract", "publication_date", "pages", "doi_data"])
        first, second = paper.findall(".//c:person_name", N)
        self.assertEqual([c.tag.split("}")[1] for c in first], ["given_name", "surname", "affiliations", "ORCID"])
        self.assertEqual(first.find(".//c:institution_name", N).text, "Dept. of X, NTNU, Trondheim, Norway")
        self.assertEqual(first.find("c:ORCID", N).text, "https://orcid.org/0000-0002-1825-0097")
        self.assertEqual((second.get("sequence"), second.find("c:surname", N).text), ("additional", "Gunadi"))
        self.assertIsNone(second.find("c:given_name", N))
        self.assertEqual(len(paper.findall(".//jats:p", N)), 2)
        self.assertEqual(paper.find("c:doi_data/c:resource", N).text, "https://www.iglc.net/papers/details/%d" % self.paper.pk)
        self.assertEqual(root.find(".//c:proceedings_series_metadata/c:doi_data/c:doi", N).text, "10.24928/2027")
        self.assertIsNotNone(root.find(".//c:noisbn", N))
        _, with_isbn = conference_xml(self.conference, [self.paper], isbn="978-82-692499-5-8", depositor=("a", "b"))
        self.assertIn(b'<isbn media_type="electronic">978-82-692499-5-8</isbn>', with_isbn)

    def test_institutions(self):
        self.assertEqual(institutions("PhD Candidate, Dept. A, University B, Oslo, Norway / Engineer, Company C AS, Oslo"),
                         ["Dept. A, University B, Oslo, Norway", "Company C AS, Oslo"])
        self.assertEqual(institutions("University of Cambridge, UK"), ["University of Cambridge, UK"])

    @override_settings(CROSSREF_LOGIN="iglc/role", CROSSREF_PASSWORD="pw", CROSSREF_TEST=True)
    def test_send_and_check(self):
        item = crossref.make(self.conference, [self.paper])
        sent = []

        def opener(request, timeout=None):
            sent.append(request)
            if getattr(request, "full_url", request).startswith("https://test.crossref.org/servlet/deposit"):
                return FakeResponse(b"<html>SUCCESS</html>")
            return FakeResponse(b'<?xml version="1.0"?><doi_batch_diagnostic status="completed"><record_diagnostic '
                                b'status="Success"><doi>10.24928/2027/0123</doi><msg>Successfully added</msg>'
                                b'</record_diagnostic><record_diagnostic status="Failure"><doi>10.24928/2027</doi>'
                                b'<msg>Bad</msg></record_diagnostic></doi_batch_diagnostic>')

        crossref.send(item, opener=opener)
        self.assertIn(b'name="login_id"\r\n\r\niglc/role', sent[0].data)
        self.assertEqual(item.status, "sent")
        crossref.check(item, opener=opener)
        self.assertEqual((item.status, item.successes, item.failures), ("failed", 1, 1))
        self.assertEqual(crossref.problems(item.result), [("10.24928/2027", "Bad")])
        with self.assertRaises(crossref.DepositError):
            crossref.send(item, opener=opener)  # sent already

    def test_not_configured(self):
        item = crossref.make(self.conference, [self.paper])
        with self.assertRaises(crossref.DepositError):
            crossref.send(item)
