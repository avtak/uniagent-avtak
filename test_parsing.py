"""Tests for parsing.py, taken from real lines of the 61 practice PDFs
(the development notes (not included), section c)."""
import unittest
from datetime import date
from decimal import Decimal

from parsing import number_value, parse_amounts, parse_date, parse_dates


def amounts(text):
    return [(a.value, a.currency) for a in parse_amounts(text)]


class AmountTest(unittest.TestCase):
    def test_german_format(self):
        self.assertEqual([(Decimal("2667.00"), "EUR")], amounts("Summe netto 2.667,00 €"))

    def test_english_format_with_currency_before(self):
        self.assertEqual([(Decimal("94.40"), "EUR")], amounts("Invoice total €94.40"))

    def test_usd_and_exchange_rate(self):
        self.assertEqual([(Decimal("175.00"), "USD")], amounts("USD 175,00 Kurs 1,0912"))

    def test_percent_is_not_money(self):
        self.assertEqual([(Decimal("160.37"), "EUR")], amounts("1,75 % von 160,37 EUR"))

    def test_negative_booking(self):
        self.assertEqual([(Decimal("-229.00"), "EUR")], amounts("-229,00 EUR"))

    def test_currency_before_full_stop(self):
        self.assertEqual([(Decimal("210.00"), "EUR")], amounts("Hinflug Frankfurt, 210,00 EUR."))

    def test_room_numbers_are_not_money(self):
        self.assertEqual([], amounts("Raum B 0.14 und Labor E 3.12"))

    def test_whole_number_needs_a_currency(self):
        self.assertEqual([(Decimal("1200"), "USD")], amounts("bis zu 1.200 USD"))
        self.assertEqual([(Decimal("1000"), "EUR")], amounts("da der Auftragswert unter 1.000 € liegt"))
        self.assertEqual([], amounts("Stand 01/2027, Seite 2"))

    def test_special_spaces_from_model_output(self):
        self.assertEqual([(Decimal("20.00"), "EUR")], amounts("20,00 EUR"))
        self.assertEqual([(Decimal("2667.00"), "EUR")], amounts("2 667,00 €"))

    def test_amount_without_currency(self):
        self.assertEqual([(Decimal("19.86"), "EUR")], amounts("SUMME EUR 19,86"))

    def test_number_value(self):
        self.assertEqual(Decimal("2667.00"), number_value("2.667,00"))
        self.assertEqual(Decimal("2667.00"), number_value("2,667.00"))
        self.assertEqual(Decimal("1200"), number_value("1.200"))
        self.assertEqual(Decimal("94.40"), number_value("94,40"))
        self.assertEqual(Decimal("-69.02"), number_value("-69,02 €"))


class DateTest(unittest.TestCase):
    def test_single_dates(self):
        cases = {
            "Zuletzt geändert am: 20. Oktober 2026": date(2026, 10, 20),
            "Order date 2027-02-11": date(2027, 2, 11),
            "Datum: 12-FEB-2027": date(2027, 2, 12),
            "BON 4471 KASSE 03 13.03.27 10:42": date(2027, 3, 13),
            "Fr 21.08.2026 23:41": date(2026, 8, 21),
            "due 25 September 2026": date(2026, 9, 25),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, parse_date(text))

    def test_ranges_give_start_and_end(self):
        cases = {
            "10.–11. März 2026": [date(2026, 3, 10), date(2026, 3, 11)],
            "29 November – 4 December 2026": [date(2026, 11, 29), date(2026, 12, 4)],
            "07.09.–10.09.2026": [date(2026, 9, 7), date(2026, 9, 10)],
            "07.–10.09.2026": [date(2026, 9, 7), date(2026, 9, 10)],
            "10–11 November 2026": [date(2026, 11, 10), date(2026, 11, 11)],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, [d.value for d in parse_dates(text)])

    def test_not_dates(self):
        for text in ["Stand 01/2027", "Angebot KZ 27/1044", "RE 27-0612", "(07.–10.09.), à 80,00 €"]:
            with self.subTest(text=text):
                self.assertEqual([], parse_dates(text))

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            parse_date("irgendwann")


if __name__ == "__main__":
    unittest.main()
