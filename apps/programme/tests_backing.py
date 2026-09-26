import tempfile
from datetime import date, time
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core import mail
from django.urls import reverse

from apps.production.models import Event, ProductionEditor, Submission

from . import backing, checks
from .models import PaperPresentation, Programme, Registration, Session, SessionItem
from .tests import ProgrammeTestCase

CSV = """Registration ID;First name;Last name;E-mail;Registration type;Payment status
R1;Ann;Smith;ann@example.org;Full conference;Paid
R2;Cy;Lee;cy@example.org;Full conference;Paid
R3;Eve;Unpaid;eve@example.org;Full conference;Open
R4;Fay;Industry;fay@example.org;Industry day only;Paid
"""


class BackingTestCase(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        for s, emails in ((self.p1, ["ann@example.org", "bo@example.org"]), (self.p2, ["cy@example.org"])):
            s.registered_authors = [dict(a, email=e) for a, e in zip(s.registered_authors, emails)]
            s.save()

    def upload(self, text=CSV):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reg.csv"
            path.write_text(text, encoding="utf-8")
            return backing.import_registrations(self.programme, path)

    def count(self, name, counts=True):
        self.programme.registration_types.filter(name=name).update(counts=counts, decided=True)

    def paper(self, conftool_id, *authors):
        return Submission.objects.create(production=self.p1.production, conftool_id=conftool_id,
                                         title=f"Paper {conftool_id}",
                                         registered_authors=[{"name": n, "email": e} for n, e in authors])

    def status(self):
        return {row.submission.conftool_id: (row.status, row.registration.name if row.registration else None)
                for row in backing.assess(self.programme)}


class ImportTests(BackingTestCase):
    def test_import_and_types(self):
        report = self.upload()
        self.assertEqual((report["created"], report["updated"]), (4, 0))
        ann = Registration.objects.get(reference="R1")
        self.assertEqual((ann.name, ann.email, ann.paid), ("Ann Smith", "ann@example.org", True))
        self.assertFalse(Registration.objects.get(reference="R3").paid)
        self.assertFalse(ann.counts)  # new types count only once ticked
        self.count("Full conference")
        self.assertTrue(Registration.objects.get(reference="R1").counts)

    def test_upload_again_updates_and_retires(self):
        self.upload()
        report = self.upload(CSV.replace("Open", "Paid").replace("R2;Cy;Lee;cy@example.org;Full conference;Paid\n", ""))
        self.assertEqual((report["created"], report["updated"], report["inactive"]), (0, 3, 1))
        self.assertTrue(Registration.objects.get(reference="R3").paid)
        self.assertFalse(Registration.objects.get(reference="R2").active)

    def test_no_payment_column_means_paid(self):
        report = self.upload("Name,Email,Type\nAnn Smith,ann@example.org,Full\n")
        self.assertTrue(report["no_paid_column"])
        self.assertTrue(Registration.objects.get().paid)


class MatchingTests(BackingTestCase):
    def setUp(self):
        super().setUp()
        self.upload()
        self.count("Full conference")

    def test_backed_by_email_and_name(self):
        self.assertEqual(self.status(), {101: ("backed", "Ann Smith"), 102: ("backed", "Cy Lee")})
        # by name when the email differs
        Registration.objects.filter(reference="R2").update(email="c.lee@uni.example")
        self.assertEqual(self.status()[102], ("backed", "Cy Lee"))

    def test_unpaid_and_wrong_type_do_not_count(self):
        self.paper(104, ("Eve Unpaid", "eve@example.org"))
        self.paper(105, ("Fay Industry", "fay@example.org"))
        self.paper(106, ("Nobody", "nobody@example.org"))
        status = self.status()
        self.assertEqual(status[104], ("unpaid", None))
        self.assertEqual(status[105], ("unpaid", None))
        self.assertEqual(status[106], ("none", None))

    def test_two_paper_limit(self):
        self.paper(104, ("Cy Lee", "cy@example.org"))
        self.paper(105, ("Cy Lee", "cy@example.org"))
        status = self.status()
        self.assertEqual(sorted(s for s, _ in (status[102], status[104], status[105])),
                         ["backed", "backed", "over_limit"])

    def test_co_author_takes_the_third_paper(self):
        # Ann is on three papers; the matching must let Cy back the one they share.
        self.paper(104, ("Ann Smith", "ann@example.org"))
        self.paper(105, ("Ann Smith", "ann@example.org"), ("Cy Lee", "cy@example.org"))
        Submission.objects.filter(pk=self.p2.pk).update(status=Submission.Status.WITHDRAWN)
        self.paper(106, ("Cy Lee", "cy@example.org"))
        status = self.status()
        self.assertEqual({k: v[0] for k, v in status.items()}, {101: "backed", 104: "backed", 105: "backed",
                                                                 106: "backed"})
        self.assertEqual(status[105][1], "Cy Lee")

    def test_editors_choice(self):
        p = self.paper(104, ("Dee Other", "dee@elsewhere.example"))
        PaperPresentation.objects.create(submission=p, registration=Registration.objects.get(reference="R1"))
        self.assertEqual(self.status()[104], ("backed", "Ann Smith"))

    def test_authors_name_the_backer_email(self):
        p = self.paper(104, ("Dee Other", "dee@elsewhere.example"))
        self.upload(CSV + "R5;Dee;Other-Name;dee.private@example.org;Full conference;Paid\n")
        self.assertEqual(self.status()[104][0], "none")
        PaperPresentation.objects.create(submission=p, backer="Dee Other", backer_email="dee.private@example.org",
                                         answer="present", presenter="Dee Other")
        self.assertEqual(self.status()[104], ("backed", "Dee Other-Name"))


class EmailTests(BackingTestCase):
    def setUp(self):
        super().setUp()
        self.upload()
        self.count("Full conference")
        self.programme.author_deadline = date(2027, 4, 30)
        self.programme.save()
        self.nobody = self.paper(104, ("Nobody", "nobody@example.org"))

    def test_requests_reminders_and_warnings(self):
        result = backing.send_batch(self.programme, "request", n=2)
        self.assertEqual((result["sent"], result["left"]), (2, 1))
        backing.send_batch(self.programme, "request", after=result["next"])
        self.assertEqual(len(mail.outbox), 3)
        first = mail.outbox[0]
        self.assertEqual(first.to, ["ann@example.org", "bo@example.org"])
        self.assertIn("30 April 2027", first.body)
        token = PaperPresentation.objects.get(submission=self.p1).token
        self.assertIn(f"/for-authors/confirm-presentation/{token}/", first.body)
        self.assertEqual(backing.send_batch(self.programme, "request")["sent"], 0)  # not twice
        mail.outbox.clear()
        self.assertEqual(backing.send_batch(self.programme, "reminder")["sent"], 3)
        self.assertTrue(mail.outbox[0].subject.startswith("Reminder: "))
        mail.outbox.clear()
        self.assertEqual(backing.send_batch(self.programme, "warning")["sent"], 1)
        self.assertEqual(mail.outbox[0].to, ["nobody@example.org"])
        self.assertIn("will be withdrawn", mail.outbox[0].body)
        self.assertTrue(Event.objects.filter(submission=self.nobody, action__contains="warned").exists())

    def test_edited_text(self):
        self.programme.warning_subject = "Paper {paper_id} needs a registration by {deadline}"
        self.programme.save()
        backing.send_batch(self.programme, "warning")
        self.assertEqual(mail.outbox[0].subject, "Paper 104 needs a registration by 30 April 2027")


class AuthorPageTests(BackingTestCase):
    def setUp(self):
        super().setUp()
        self.upload()
        self.count("Full conference")
        self.presentation = PaperPresentation.objects.create(submission=self.p1,
                                                             recipients=["ann@example.org", "bo@example.org"])
        self.url = reverse("programme_public:confirm", args=[self.presentation.token])

    def test_answer(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Takt in hospitals")
        self.assertContains(response, "We have found a registration")
        response = self.client.post(self.url, {"answer": "present", "presenter": "Bo Jones", "backer": "Ann Smith",
                                               "responder": "Bo Jones"})
        self.assertRedirects(response, self.url)
        self.presentation.refresh_from_db()
        self.assertEqual((self.presentation.answer, self.presentation.presenter, self.presentation.backer),
                         ("present", "Bo Jones", "Ann Smith"))
        self.assertEqual(mail.outbox[-1].to, ["ann@example.org", "bo@example.org"])

    def test_checks_the_answer(self):
        response = self.client.post(self.url, {"answer": "present", "presenter": "Someone", "responder": ""})
        self.assertContains(response, "Please choose who presents the paper.")
        self.assertContains(response, "Please give your name.")
        self.assertEqual(PaperPresentation.objects.get(pk=self.presentation.pk).answer, "")

    def test_withdrawal_goes_to_the_chief_editors(self):
        chief = User.objects.create_user("chief", email="chief@example.org")
        ProductionEditor.objects.create(production=self.p1.production, user=chief, role=ProductionEditor.Role.CHIEF)
        self.client.post(self.url, {"answer": "withdraw", "responder": "Ann Smith", "comment": "Sorry"})
        self.assertTrue(any(m.to == ["chief@example.org"] and "withdraw" in m.subject for m in mail.outbox))

    def test_unknown_token(self):
        self.assertEqual(self.client.get("/for-authors/confirm-presentation/00000000-0000-0000-0000-000000000000/")
                         .status_code, 404)


class BackOfficeTests(BackingTestCase):
    def setUp(self):
        super().setUp()
        self.upload()
        self.count("Full conference")
        self.chief = User.objects.create_user("chief")
        ProductionEditor.objects.create(production=self.p1.production, user=self.chief, role=ProductionEditor.Role.CHIEF)
        self.nobody = self.paper(104, ("Nobody", "nobody@example.org"))

    def test_chief_editor_sees_and_acts(self):
        self.client.force_login(self.chief)
        response = self.client.get(reverse("programme:backing", args=[35]))
        self.assertContains(response, "No registration")
        self.assertContains(response, "Warn 1 without backing")
        response = self.client.post(reverse("programme:backing", args=[35]), {"action": "warning", "after": "0"})
        self.assertEqual(response.json()["sent"], 1)
        self.client.post(reverse("programme:backing", args=[35]), {"action": "withdraw", "paper": [self.nobody.pk]})
        self.nobody.refresh_from_db()
        self.assertEqual(self.nobody.status, Submission.Status.WITHDRAWN)
        self.assertTrue(Event.objects.filter(submission=self.nobody, action="withdrawn").exists())

    def test_published_paper_is_not_withdrawn_here(self):
        from apps.archive.models import Paper

        paper = Paper.objects.create(title="Published", conference=self.conference)
        Submission.objects.filter(pk=self.nobody.pk).update(paper=paper)
        self.client.force_login(self.chief)
        self.client.post(reverse("programme:backing", args=[35]), {"action": "withdraw", "paper": [self.nobody.pk]})
        self.assertNotEqual(Submission.objects.get(pk=self.nobody.pk).status, Submission.Status.WITHDRAWN)

    def test_choose_backer(self):
        self.client.force_login(self.chief)
        cy = Registration.objects.get(reference="R2")
        self.client.post(reverse("programme:backing", args=[35]),
                         {"action": "backer", "paper": self.nobody.pk, "registration": cy.pk})
        self.assertEqual(self.status()[104], ("backed", "Cy Lee"))

    def test_organiser_uploads_but_does_not_send(self):
        organiser = self.user("org", "IGLC 35 organisers")
        self.client.force_login(organiser)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(CSV)
        with open(f.name, "rb") as handle:
            self.client.post(reverse("programme:registrations", args=[35]), {"action": "upload", "file": handle})
        Path(f.name).unlink()
        self.assertContains(self.client.get(reverse("programme:registrations", args=[35])), "Ann Smith")
        self.assertNotEqual(self.client.post(reverse("programme:backing", args=[35]),
                                             {"action": "warning"}).status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_scientific_chairs_are_chief_editors_and_assistants_are_not(self):
        self.client.force_login(self.user("sci", "IGLC 35 scientific chairs"))
        self.assertEqual(self.client.get(reverse("programme:backing", args=[35])).status_code, 200)
        self.client.force_login(self.user("assistant", Group.objects.create(name="IGLC 35 editorial assistants")))
        self.assertNotEqual(self.client.get(reverse("programme:backing", args=[35])).status_code, 200)

    def test_types_are_ticked(self):
        self.client.force_login(self.chief)
        industry = self.programme.registration_types.get(name="Industry day only")
        full = self.programme.registration_types.get(name="Full conference")
        self.client.post(reverse("programme:registrations", args=[35]), {"action": "types", "counts": [industry.pk]})
        industry.refresh_from_db(), full.refresh_from_db()
        self.assertTrue(industry.counts and industry.decided)
        self.assertFalse(full.counts)


class ProgrammeIntegrationTests(BackingTestCase):
    def test_answers_reach_the_programme(self):
        PaperPresentation.objects.create(submission=self.p2, answer="not_present")
        PaperPresentation.objects.create(submission=self.p1, answer="present", presenter="Bo Jones")
        self.assertEqual(list(checks.unplaced(self.programme)), [self.p1])
        session = self.session(kind=Session.Kind.PAPERS, code="1A")
        scientific = self.user("sci", "IGLC 35 scientific chairs")
        self.client.force_login(scientific)
        self.client.post(reverse("programme:papers", args=[35]), {"session": session.pk, "paper": [self.p1.pk]})
        self.assertEqual(session.items.get().presenter, "Bo Jones")
        SessionItem.objects.filter(session=session).update(presenter="Ann Smith")
        SessionItem.objects.create(session=session, submission=self.p2)
        texts = [p.text for p in checks.problems(self.programme)]
        self.assertTrue(any("the authors say Bo Jones presents" in t for t in texts))
        self.assertTrue(any("published, not presented" in t for t in texts))
