import io
import json
import shutil
import tempfile
from datetime import time

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from pypdf import PdfReader

from apps.archive.models import Author, Paper
from apps.production.models import Submission

from .models import PaperPresentation, Programme, Session, SessionItem
from .tests import HOST
from .tests_venue import VENUE, VenueTestCase

MEDIA = tempfile.mkdtemp()


def pdf_text(data: bytes) -> str:
    return " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


@override_settings(MEDIA_ROOT=MEDIA)
class SlidesTests(VenueTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.presentation = PaperPresentation.objects.create(submission=self.p1)
        self.url = reverse("programme_public:confirm", args=[self.presentation.token])

    def upload(self, name, content):
        return self.client.post(self.url, {"action": "slides", "responder": "Ann Smith",
                                           "slides": SimpleUploadedFile(name, content)})

    def test_upload_and_show(self):
        self.assertRedirects(self.upload("talk.pdf", b"%PDF-1.4 slides"), self.url)
        self.presentation.refresh_from_db()
        self.assertIn("presentations/iglc35/iglc35-101-slides", self.presentation.slides.name)
        self.assertContains(self.client.get(f"/2027/programme/session/{self.a.pk}/", **HOST), "Slides")
        self.assertContains(self.client.get(self.url), "the current slides")

    def test_refused(self):
        self.assertContains(self.upload("talk.key", b"whatever"), "must be a PDF or a PowerPoint")
        self.assertContains(self.upload("talk.pdf", b"not a pdf"), "not a real PDF")
        self.assertFalse(PaperPresentation.objects.get(pk=self.presentation.pk).slides)

    def test_published_paper_gets_the_slides(self):
        paper = Paper.objects.create(title="Takt in hospitals", conference=self.conference)
        Submission.objects.filter(pk=self.p1.pk).update(paper=paper)
        self.upload("talk.pptx", b"PK\x03\x04 pptx")
        paper.refresh_from_db()
        self.assertIn("iglc35-101-slides", paper.presentation_url)

    def test_published_later(self):
        self.upload("talk.pdf", b"%PDF-1.4 slides")
        paper = Paper.objects.create(title="Takt in hospitals", conference=self.conference)
        Submission.objects.filter(pk=self.p1.pk).update(paper=paper)
        chair = self.user("chair", "IGLC 35 conference chairs")
        self.client.force_login(chair)
        self.client.post(reverse("programme:backing", args=[35]), {"action": "link_slides"})
        paper.refresh_from_db()
        self.assertTrue(paper.presentation_url.startswith("http://localhost:8000/media/presentations/iglc35/"))


class BookletTests(VenueTestCase):
    def test_public_booklet(self):
        paper = Paper.objects.create(title="Takt in hospitals, published", conference=self.conference)
        Author.objects.create(paper=paper, first_name="Ann", last_name="Smith", order=1)
        Submission.objects.filter(pk=self.p1.pk).update(paper=paper)
        Session.objects.filter(pk=self.b.pk).update(change_note="Moved to Room A")
        response = self.client.get("/2027/programme/programme.pdf", **HOST)
        self.assertEqual(response["Content-Type"], "application/pdf")
        text = pdf_text(response.content)
        for expected in ("IGLC 35", "Munich", "1A Takt", "Takt in hospitals, published", "Changed: Moved to Room A",
                         "Chair: Cy Lee", "Room A", "People"):
            self.assertIn(expected, text)
        self.assertNotIn("Doctoral colloquium", text)
        self.assertTrue(self.venue("/programme.pdf").content.startswith(b"%PDF"))

    def test_hidden_programme(self):
        Programme.objects.update(status=Programme.Status.HIDDEN)
        self.assertEqual(self.client.get("/2027/programme/programme.pdf", **HOST).status_code, 404)
        self.client.force_login(self.user("chair", "IGLC 35 conference chairs"))
        response = self.client.get(reverse("programme:booklet", args=[35]))
        self.assertIn("1A Takt", pdf_text(response.content))


class OfflineTests(VenueTestCase):
    def test_conference_site_worker(self):
        response = self.client.get("/2027/programme/sw.js", **HOST)
        self.assertEqual(response["Content-Type"], "application/javascript; charset=utf-8")
        body = response.content.decode()
        self.assertIn(f'"/2027/programme/session/{self.a.pk}/"', body)
        self.assertIn('"/2027/programme/day/2027-07-20/"', body)
        self.assertIn("/static/css/conference.css", body)
        self.assertNotIn(f"/session/{self.phd_session.pk}/", body)
        self.assertContains(self.client.get("/2027/programme/", **HOST), 'data-sw="/2027/programme/sw.js"')

    def test_venue_worker_and_version(self):
        body = self.venue("/sw.js").content.decode()
        self.assertIn('"/today/?day=2027-07-21"', body)
        self.assertContains(self.venue(at="2027-07-20T10:45"), 'data-sw="/sw.js"')
        before = body.split("\n")[1]
        Session.objects.filter(pk=self.a.pk).update(updated=self.a.updated.replace(year=2030))
        self.assertNotEqual(self.venue("/sw.js").content.decode().split("\n")[1], before)


class PlanTests(VenueTestCase):
    def setUp(self):
        super().setUp()
        self.posters = self.session(code="P", title="Posters", kind=Session.Kind.POSTERS, start_at=time(13),
                                    end_at=time(14))
        self.free = SessionItem.objects.create(session=self.a, title="Introduction", order=0)
        self.scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(self.scientific)
        self.url = reverse("programme:plan", args=[35]) + "?day=2027-07-20"

    def post(self, sessions):
        return self.client.post(self.url, json.dumps({"sessions": sessions}), content_type="application/json")

    def test_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'data-entry="s{self.p2.pk}"')  # not placed yet
        self.assertContains(response, f'data-session="{self.posters.pk}"')

    def test_drag_in_move_and_back(self):
        response = self.post({str(self.a.pk): [f"s{self.p1.pk}", f"i{self.free.pk}"],
                              str(self.b.pk): [], str(self.posters.pk): [f"s{self.p2.pk}"]})
        self.assertEqual(response.json(), {"ok": True})
        placed = SessionItem.objects.get(submission=self.p2)
        self.assertEqual((placed.session_id, placed.presentation), (self.posters.pk, "poster"))
        self.assertEqual([i.pk for i in self.a.items.order_by("order")][1], self.free.pk)
        # move paper 1 to 1B, and paper 2 back to the list
        self.post({str(self.a.pk): [f"i{self.free.pk}"], str(self.b.pk): [f"s{self.p1.pk}"],
                   str(self.posters.pk): []})
        moved = SessionItem.objects.get(submission=self.p1)
        self.assertEqual((moved.session_id, moved.presenter), (self.b.pk, "Ann Smith"))
        self.assertFalse(SessionItem.objects.filter(submission=self.p2).exists())
        self.assertTrue(SessionItem.objects.filter(pk=self.free.pk).exists())

    def test_refusals(self):
        self.assertEqual(self.post({str(self.a.pk): [f"s{self.p3.pk}"]}).status_code, 400)  # withdrawn
        industry = self.session(part=self.industry, kind=Session.Kind.PAPERS, title="Industry papers",
                                start_at=time(16), end_at=time(17))
        self.assertEqual(self.post({str(industry.pk): [f"s{self.p2.pk}"]}).status_code, 400)
        self.assertFalse(SessionItem.objects.filter(submission=self.p2).exists())
