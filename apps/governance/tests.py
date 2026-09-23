from datetime import date

from django.test import TestCase

from .models import Committee, Seat


class CommitteePageTests(TestCase):
    def setUp(self):
        self.sc = Committee.objects.get(slug="standardisation-committee")
        Seat.objects.create(committee=self.sc, first_name="Gina", last_name="Secretary", is_chair=True,
                            role=Seat.Role.GENERAL_SECRETARY, start_date=date(2023, 7, 1), end_date=None)
        Seat.objects.create(committee=self.sc, first_name="Ada", last_name="Current", affiliation="NTNU",
                            country="Norway", start_date=date(2024, 7, 1), end_date=date(2099, 7, 1))
        Seat.objects.create(committee=self.sc, first_name="Old", last_name="Timer",
                            start_date=date(2019, 7, 1), end_date=date(2022, 7, 1))

    def test_current_and_past(self):
        current = list(self.sc.current_seats(on=date(2026, 9, 1)).values_list("last_name", flat=True))
        self.assertCountEqual(current, ["Secretary", "Current"])
        self.assertEqual([s.last_name for s in self.sc.past_seats(on=date(2026, 9, 1))], ["Timer"])

    def test_term_ends_on_its_end_date(self):
        seat = Seat.objects.get(last_name="Timer")
        self.assertIn(seat, Seat.objects.current(on=date(2022, 6, 30)))
        self.assertNotIn(seat, Seat.objects.current(on=date(2022, 7, 1)))

    def test_page(self):
        response = self.client.get("/about/committees/")
        self.assertContains(response, "Standardisation Committee")
        self.assertContains(response, "Chair, General Secretary")
        self.assertContains(response, "NTNU, Norway")
        self.assertContains(response, "Former members")
        body = response.content.decode()
        self.assertLess(body.index("Gina Secretary"), body.index("Ada Current"))
        self.assertContains(response, "Control Committee")
