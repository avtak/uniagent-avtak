"""Facts by code (facts.py) on real practice cases and on our variant cases."""
import os
import subprocess
import unittest
from pathlib import Path

from facts import compute_facts

DATASETS = Path(os.environ.get("UNIAGENT_DATASETS", Path.home() / "dev/uniagent-code/cikm26/datasets"))
VARIANTS = Path(__file__).parent / "experiments" / "variants"
EDGE = Path(__file__).parent / "experiments" / "edge-cases"
SETS = {"dienstreiseantrag": ("business-trip-spot-check", "business_trip"),
        "beschaffungsantrag": ("task-2-procurement-spot-check", "procurement"),
        "auslagenerstattung": ("task-2-expense-reimbursement-spot-check", "expense_reimbursement")}


def facts(case_id, root=DATASETS):
    folder, kind = SETS[case_id.split("-")[0]]
    case = root / folder / "inputs" / case_id
    docs = {f.name: subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True).stdout
            for f in sorted(case.glob("*.pdf"))}
    return "\n".join(compute_facts(kind, docs))


class TripFactsTest(unittest.TestCase):
    def test_request_after_trip_start(self):
        self.assertIn("Antrag vor Reisebeginn gestellt: NEIN", facts("dienstreiseantrag-01"))

    def test_no_a1_verdict_in_the_facts(self):
        for case in ["dienstreiseantrag-04", "dienstreiseantrag-05"]:
            with self.subTest(case=case):
                self.assertNotIn("A1-Bescheinigung erforderlich", facts(case))

    def test_third_party_funding_is_flagged(self):
        self.assertIn("Finanzierung durch Dritte (Stipendium, Zuschuss, Erasmus, Kostenübernahme): JA", facts("dienstreiseantrag-05"))


    def test_declared_scholarship_is_no_note(self):
        from facts import trip_facts
        form = ("Datum der Antragstellung: 01.02.2026\nStart: 10.03.2026\nReiseziel: Boston, USA\nReise ins Ausland: [X] ja [ ] nein\n"
                "Finanzierung: Lehrstuhlbudget; Reisestipendium DGMK 1.000 USD wird angerechnet\n")
        f = "\n".join(trip_facts({"antrag.pdf": form, "email-stipendienzusage.pdf": "Ihnen wurde ein Reisestipendium zuerkannt."}))
        self.assertIn("im Antrag angegeben oder angerechnet: JA", f)
        self.assertIn("keine Auffälligkeit erkannt", f)

    def test_destination_on_the_not_approved_list(self):
        self.assertIn("nicht genehmigt werden (Dienstreisemanagement): JA (Israel)", facts("dienstreiseantrag-05-e1", EDGE))
        for case in ["dienstreiseantrag-02", "dienstreiseantrag-05"]:
            with self.subTest(case=case):
                self.assertNotIn("bis auf Weiteres nicht genehmigt", facts(case))

    def test_evening_programme_cost_row(self):
        self.assertIn("Begleit- oder Abendprogramm beantragt: JA (Conference Dinner", facts("dienstreiseantrag-02-e1", EDGE))
        # The practice trip names the dinner only as "nicht gebucht", outside the cost rows.
        self.assertNotIn("Abendprogramm beantragt", facts("dienstreiseantrag-02"))


class ProcurementFactsTest(unittest.TestCase):
    def test_sentence_about_the_limit_is_not_the_order_value(self):
        f = facts("beschaffungsantrag-02")
        self.assertIn("Auftragswert netto: 673,00 €; netto ≥ 1.000 €: NEIN", f)

    def test_only_gross_under_limit(self):
        self.assertIn("Nettobetrag sicher unter 1.000 €: JA", facts("beschaffungsantrag-03"))

    def test_form_total_differs_from_every_offer(self):
        self.assertIn("Antragsbetrag netto passt zu einem Angebot (höchstens 10 % Abweichung oder eine Position): NEIN", facts("beschaffungsantrag-04"))

    def test_framework_words_singular(self):
        self.assertIn("Rahmenvertrags-Produktgruppe (Bürodrehstuhl)", facts("beschaffungsantrag-03-e1", EDGE))

    def test_framework_words(self):
        self.assertIn("Rahmenvertrags-Produktgruppe (PCs/Notebooks/Monitore, Bürostühle, Büromöbel, Kopiergeräte, Büropapier, Büromaterial, Microsoft, Gase): JA (Monitor", facts("beschaffungsantrag-03"))

    def test_framework_product_bought_elsewhere_is_noted(self):
        self.assertIn("eine Bestellung beim Rahmenvertragspartner ist nicht erkennbar", facts("beschaffungsantrag-03"))
        self.assertNotIn("PRÜFHINWEISE von Code (mögliche", facts("beschaffungsantrag-03-v1", VARIANTS))

    def test_no_notes_on_accepted_cases(self):
        for case in ["beschaffungsantrag-01", "beschaffungsantrag-02", "beschaffungsantrag-05", "beschaffungsantrag-08",
                     "dienstreiseantrag-02", "dienstreiseantrag-04", "auslagenerstattung-01", "auslagenerstattung-05"]:
            with self.subTest(case=case):
                self.assertIn("keine Auffälligkeit erkannt", facts(case))

    def test_supplier_against_framework_partner(self):
        self.assertIn("Lieferant ist der Rahmenvertragspartner: JA", facts("beschaffungsantrag-05"))
        self.assertIn("Lieferant ist der Rahmenvertragspartner: NEIN", facts("beschaffungsantrag-05-v1", VARIANTS))


class FalseAlarmTest(unittest.TestCase):
    """rules-review.md section 4: words that must not trigger a check note."""

    def test_framework_words_only_for_the_item_itself(self):
        from facts import framework_items
        self.assertEqual([], framework_items("PC-Schnittstelle USB                1   45,00 €"))
        self.assertEqual([], framework_items("Software für Windows 11            1   99,00 €"))
        self.assertEqual([], framework_items("Mikroskop inkl. Bildschirm        1  2.400,00 €"))
        self.assertEqual([], framework_items("Lab Notebook A4, 10 Stück          1   35,00 €"))
        self.assertEqual([], framework_items("Kategorie: Büromaterial"))
        self.assertEqual(["Monitor"], framework_items("2 × Monitor 27 Zoll, WQHD          2   189,00 €"))

    def test_sap_order_number_is_no_duplicate(self):
        from facts import expense_facts
        docs = {"rechnung-1.pdf": "Universität Kassel\nAuftragsnummer 2140112\nRechnungsbetrag 10,00 €",
                "rechnung-2.pdf": "Universität Kassel\nAuftragsnummer 2140112\nRechnungsbetrag 12,00 €"}
        self.assertIn("in mehreren Belegen: NEIN", "\n".join(expense_facts(docs)))

    def test_scholarship_holder_word_is_no_funding(self):
        from facts import trip_facts
        form = "Datum der Antragstellung: 01.02.2026\nStart: 10.03.2026\nReiseziel: Berlin\nReise ins Ausland: [ ] ja [X] nein\nAnmerkung: Stipendiatin des Graduiertenkollegs"
        self.assertIn("Finanzierung durch Dritte (Stipendium, Zuschuss, Erasmus, Kostenübernahme): NEIN", "\n".join(trip_facts({"antrag.pdf": form})))


class ExpenseFactsTest(unittest.TestCase):
    def test_two_invoices_in_one_pdf_and_a_credit_note(self):
        self.assertIn("Rechnungen minus Gutschriften = 135,68 €; stimmt überein: JA", facts("auslagenerstattung-05"))
        self.assertIn("stimmt überein: NEIN", facts("auslagenerstattung-05-v1", VARIANTS))

    def test_hospitality_for_staff_only(self):
        self.assertIn("nur für Beschäftigte (ohne externe Gäste) laut Beleg: JA", facts("auslagenerstattung-02-e1", EDGE))
        self.assertIn("nur für Beschäftigte (ohne externe Gäste) laut Beleg: JA", facts("auslagenerstattung-07"))
        # Same receipt, guests of a colloquium: courtesies for guests are allowed.
        self.assertNotIn("nur für Beschäftigte", facts("auslagenerstattung-02-e2", EDGE))

    def test_restaurant_meal_needs_a_guest_list(self):
        self.assertIn("Teilnehmerliste mit Kennzeichnung der Gäste vorhanden: NEIN", facts("auslagenerstattung-07-e2", EDGE))
        f = facts("auslagenerstattung-07-e1", EDGE)
        self.assertIn("Teilnehmerliste mit Kennzeichnung der Gäste vorhanden: JA", f)
        self.assertIn("keine Auffälligkeit erkannt", f)

    def test_duplicate_order_number(self):
        self.assertIn("Dieselbe Rechnung oder Bestellung (gleicher Betrag) in mehreren Belegen: JA", facts("auslagenerstattung-06"))

    def test_receipt_addressee_is_unclear_not_guessed(self):
        self.assertIn("beleg-1.pdf: Kassenbon ohne Adressat; dienstlicher Vermerk auf dem Beleg: JA ('für Versuchsstand Labor E 3.12')", facts("auslagenerstattung-02"))


if __name__ == "__main__":
    unittest.main()
