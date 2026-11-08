#!/usr/bin/env python3
"""Build the CheckList-style variant cases for UniAgent Task 2.

A variant is a copy of a practice case in which exactly ONE fact is changed, so
that the correct label flips (or provably stays). Variants test whether our
rule cards and code facts generalise. They are never used to tune prompts.

    python3 experiments/variants/tools/make_variants.py            # build everything
    python3 experiments/variants/tools/make_variants.py --check    # build + verify, exit 1 on problems
    python3 experiments/variants/tools/make_variants.py --table    # print the markdown table

Needs only python3 (standard library) and `pdftotext`/`pdfinfo` (poppler). Nothing is
installed or downloaded. The organisers' PDFs are made with ReportLab with embedded
font subsets, which cannot be edited in place; so each CHANGED document is rebuilt
from its `pdftotext -layout` text, with the edited line(s), in a small pure-Python PDF
writer (Courier, WinAnsi, one text line per line). Unchanged PDFs are copied byte for
byte. Layout is monospace; the text layer is what our solver reads.

Source data: $UNIAGENT_DATASETS (default ~/dev/uniagent-code/cikm26/datasets), read only.
Output: experiments/variants/<set>/{inputs/<case>-v<N>/*.pdf, ground-truth.jsonl}.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
DATASETS = pathlib.Path(
    os.environ.get("UNIAGENT_DATASETS", pathlib.Path.home() / "dev/uniagent-code/cikm26/datasets")
)
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

# --------------------------------------------------------------------------- #
# Variant definitions
#
# ops on one document (applied in order to its `pdftotext -layout` text):
#   ("sub", regex, new)        regex has a named group `x`; that group is replaced by `new`,
#                              the column alignment of the line is kept. Must match once.
#   ("drop", regex)            delete the one line matching regex
#   ("drop_range", a, b)       delete the lines from the one matching a to the one matching b
#   ("merge_pages",)           join all pages into one
# A document name in `drop_docs` is left out of the variant folder.
# Use [ ]+ (not \s) in regexes: a pattern must stay inside one line.
# --------------------------------------------------------------------------- #
V = []


def variant(set_, base, n, result, changed, rule, how, risk, edits=None, drop_docs=(), reason=""):
    V.append(dict(set=set_, base=base, n=n, id=f"{base}-v{n}", result=result, changed=changed,
                  rule=rule, how=how, risk=risk, edits=edits or {}, drop_docs=list(drop_docs),
                  reason=reason))


ANTRAG = "antrag-dienstreisegenehmigung.pdf"

# ---- Business trips -------------------------------------------------------- #
variant(
    TRIP, "dienstreiseantrag-02", 1, "abgelehnt",
    "Datum der Antragstellung 02.09.2026 → 11.11.2026 (trip starts 09.11.2026)",
    "Request must be submitted and approved before the trip; later approval needs a separate exception procedure "
    "(trip 01 ground truth; policy `advance_approval`)",
    "Antrag: 3 dates changed (Zuletzt geändert, Datum der Antragstellung, signature date); other documents unchanged",
    "A1 line still says 'beantragt am 02.09.2026'; the booking and registration dated 05.09./08.09. predate the new request date, "
    "which is fine for a late request but a model may call it a contradiction",
    {ANTRAG: [
        ("sub", r"Zuletzt geändert am: (?P<x>2\. September 2026)", "11. November 2026"),
        ("sub", r"Datum der Antragstellung:[ ]+(?P<x>02\.09\.2026)", "11.11.2026"),
        ("sub", r"^Datum: (?P<x>02\.09\.2026)", "11.11.2026"),
    ]},
    reason=("Der Antrag wurde am 11.11.2026 gestellt, die Reise begann aber schon am 09.11.2026 (Start 06:30 Uhr, "
            "Dienstgeschaeft ab 10.11.2026). Dienstreisen sind vor Reiseantritt zu beantragen und zu genehmigen; eine "
            "nachtraegliche Genehmigung braucht ein gesondertes Ausnahmeverfahren, das hier nicht beantragt ist. "
            "Geaendert gegenueber dienstreiseantrag-02: nur das Antragsdatum (vorher 02.09.2026, zehn Wochen vor Reisebeginn)."),
)
variant(
    TRIP, "dienstreiseantrag-02", 2, "abgelehnt",
    "A1-Bescheinigung 'beantragt am 02.09.2026 (Vorlauf > 8 Wochen)' → 'beantragt am 20.10.2026 (Vorlauf 20 Tage)'",
    "Foreign trip: A1 certificate must be requested with enough lead time, 8 weeks (business-trip README rule list; "
    "policy `foreign_travel`)",
    "Antrag: the A1 line only; the lead-time remark is rewritten as a plain number of days so it does not give the verdict away",
    "The A1 request now falls after the date of the trip request (02.09.2026), odd but not impossible; the 8-week figure comes "
    "from the README, not from a page of the university corpus",
    {ANTRAG: [
        ("sub", r"A1-Bescheinigung:[ ]+(?P<x>beantragt am 02\.09\.2026 \(Vorlauf > 8 Wochen\))",
         "beantragt am 20.10.2026 (Vorlauf 20 Tage)"),
    ]},
    reason=("Auslandsreise nach Rotterdam: Die A1-Bescheinigung wurde erst am 20.10.2026 beantragt, 20 Tage vor Reisebeginn "
            "am 09.11.2026. Verlangt ist ein Vorlauf von 8 Wochen. Geaendert gegenueber dienstreiseantrag-02: nur das "
            "A1-Antragsdatum (vorher 02.09.2026, Vorlauf ueber 8 Wochen)."),
)
variant(
    TRIP, "dienstreiseantrag-04", 1, "abgelehnt",
    "Private nights not separated: claim 1.060,00 € (3 nights, return flight 195 €) → 1.580,00 € (9 nights, return flight 235 €); "
    "'Hinweis' about self-paid private part removed",
    "Private extension: no extra cost for the university; private nights and extra fare must be shown separately and paid by "
    "the traveller (trip 04 ground truth; policy `private_extension`)",
    "Antrag: cost table rows (return flight, accommodation, total) and the Hinweis paragraph; Seite 1 von 2 → 1 von 1; "
    "hotel booking and flight comparison unchanged (they still show the two separate bookings)",
    "Several lines change for one fact; a model may also reject because the Antrag contradicts the hotel booking, which is the "
    "same label for the same reason",
    {ANTRAG: [
        ("sub", r"Seite 1 von (?P<x>2)", "1"),
        ("sub", r"Rückflug Barcelona–Frankfurt, (?P<x>Vergleichstarif zum dienstlichen)", "17.09.2026, Economy"),
        ("drop", r"^[ ]*Rückreisetag 10\.09\.2026 \(erstattungsfähiger Anteil\)"),
        ("sub", r"Rückflug Barcelona–Frankfurt.*?[ ]1[ ]+(?P<x>195,00) €", "235,00"),
        ("sub", r"Unterkunft Konferenzhotel, (?P<x>3 Nächte \(07\.–10\.09\.\)), à 80,00 €", "9 Nächte (07.–16.09.)"),
        ("sub", r"à 80,00 €[ ]+(?P<x>3)[ ]+240,00 €", "9"),
        ("sub", r"à 80,00 €[ ]+\d[ ]+(?P<x>240,00) €", "720,00"),
        ("sub", r"(?P<x>Summe der dienstlich veranlassten Kosten \(zur Erstattung)", "Summe (Schätzung), zur vollständigen Erstattung beantragt"),
        ("drop", r"^[ ]*beantragt\)[ ]*$"),
        ("sub", r"(?P<x>1\.060,00) €", "1.580,00"),
        ("drop_range", r"^Hinweis der/des Antragsteller:in:", r"der Preisvergleich liegt bei\."),
        ("merge_pages",),
    ]},
    reason=("Der private Anschlussaufenthalt (11.-16.09.2026, 6 Arbeitstage) uebersteigt 5 Arbeitstage. Der Antrag beantragt "
            "aber die vollen Kosten von 1.580,00 EUR: alle 9 Uebernachtungen (720,00 EUR, davon 6 private Naechte) und den "
            "Rueckflug am 17.09. zu 235,00 EUR statt des Vergleichstarifs 195,00 EUR. Private Naechte und Mehrpreis sind nicht "
            "getrennt ausgewiesen, der Universitaet entstehen Mehrkosten. Geaendert gegenueber dienstreiseantrag-04: die "
            "Kostenaufstellung (vorher nur dienstlicher Anteil 1.060,00 EUR)."),
)
variant(
    TRIP, "dienstreiseantrag-05", 1, "angenommen",
    "Scholarship confirmation email removed (no scholarship exists, so nothing is paid twice)",
    "Double funding applies only if a scholarship or third party covers the same cost items (trip 05 ground truth; "
    "policy `double_funding`)",
    "Folder without email-stipendienzusage.pdf; the other three PDFs copied byte for byte",
    "Medium: the gold reason for the original also says the Antrag does not mention the scholarship; with no scholarship "
    "document there is nothing to mention, but the rest of trip 05 was never judged on its own by the organisers",
    {}, drop_docs=["email-stipendienzusage.pdf"],
    reason=("Es liegt keine Stipendienzusage und keine andere Drittfinanzierung vor; die beantragten 1.910,00 EUR aus dem "
            "Lehrstuhlbudget (Flug 780,00, Registrierung 420,00, Unterkunft 650,00, Transfer 60,00) werden nirgends doppelt "
            "gedeckt. Rechtzeitig beantragt (14.07. fuer 29.11.), A1/Auslandsfeld in Ordnung, Angebot und Rechnung liegen bei. "
            "Geaendert gegenueber dienstreiseantrag-05: die Stipendienzusage fehlt."),
)

# ---- Procurement ----------------------------------------------------------- #
OFFER = "angebot-1.pdf"
MAIL = "email-beschaffungsantrag.pdf"
variant(
    PROC, "beschaffungsantrag-02", 1, "abgelehnt",
    "Single offer 673,00 € net (800,87 € gross) → 1.200,00 € net (1.428,00 € gross); unit prices 189→400 and 245→350",
    "Orders from 1.000 EUR net need at least three comparison offers, or a documented reason; direct award only up to 1.000 EUR "
    "(policies `direct_award_threshold`, `comparison_offers_required`; Lötstationen are not a framework product)",
    "Angebot and E-Mail: unit prices, line totals and sums. The sentence 'Da der Auftragswert unter 1.000 € liegt' is replaced by "
    "'Ich habe nur dieses eine Angebot', so the mail does not contain a false claim",
    "The mail no longer states a reason for the single offer; that is intended",
    {OFFER: [
        ("sub", r"mit Ablage[ ]+2[ ]+(?P<x>189,00 €)", "400,00 €"),
        ("sub", r"mit Ablage[ ]+2[ ]+400,00 €[ ]+(?P<x>378,00 €)", "800,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+(?P<x>245,00 €)", "350,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+350,00 €[ ]+(?P<x>245,00 €)", "350,00 €"),
        ("sub", r"Summe netto[ ]+(?P<x>673,00 €)", "1.200,00 €"),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>127,87 €)", "228,00 €"),
        ("sub", r"Angebotssumme brutto[ ]+(?P<x>800,87 €)", "1.428,00 €"),
    ], MAIL: [
        ("sub", r"Lötstation digital 80 W mit Ablage, je (?P<x>189,00 €) netto", "400,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W, je (?P<x>245,00 €) netto", "350,00 €"),
        ("sub", r"Summe (?P<x>673,00 € netto, 800,87 €) brutto\.", "1.200,00 € netto, 1.428,00 €"),
        ("sub", r"brutto\. (?P<x>Da der Auftragswert unter 1\.000 € liegt, habe ich nur dieses eine Angebot)", "Ich habe nur dieses eine Angebot"),
    ]},
    reason=("Bestellung per E-Mail vom 08.03.2027 auf Grundlage eines einzigen Angebots (DW-A-5518) ueber 1.200,00 EUR netto "
            "(1.428,00 EUR brutto). Ab 1.000 EUR netto sind mindestens drei Vergleichsangebote einzuholen, ein Grund fuer das "
            "Fehlen ist nicht genannt, eine Direktvergabe ist nur bis 1.000 EUR netto moeglich. Loetstationen sind kein "
            "Rahmenvertragsprodukt. Geaendert gegenueber beschaffungsantrag-02: der Nettobetrag (vorher 673,00 EUR)."),
)
variant(
    PROC, "beschaffungsantrag-02", 2, "angenommen",
    "Single offer 673,00 € net → 990,00 € net, which is 1.178,10 € gross (net just under 1.000, gross over)",
    "The 1.000 EUR threshold is on the NET amount (policy `direct_award_threshold`); direct award with one offer is allowed",
    "Angebot and E-Mail: unit prices 189→300 and 245→340, line totals and sums; the mail keeps its original sentence "
    "'Da der Auftragswert unter 1.000 € liegt', which is true for the net amount",
    "Tests net against gross. A model that compares the gross 1.178,10 € with 1.000 € will reject",
    {OFFER: [
        ("sub", r"mit Ablage[ ]+2[ ]+(?P<x>189,00 €)", "300,00 €"),
        ("sub", r"mit Ablage[ ]+2[ ]+300,00 €[ ]+(?P<x>378,00 €)", "600,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+(?P<x>245,00 €)", "340,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+340,00 €[ ]+(?P<x>245,00 €)", "340,00 €"),
        ("sub", r"Summe netto[ ]+(?P<x>673,00 €)", "990,00 €"),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>127,87 €)", "188,10 €"),
        ("sub", r"Angebotssumme brutto[ ]+(?P<x>800,87 €)", "1.178,10 €"),
    ], MAIL: [
        ("sub", r"Lötstation digital 80 W mit Ablage, je (?P<x>189,00 €) netto", "300,00 €"),
        ("sub", r"Heißluft-Rework-Station 700 W, je (?P<x>245,00 €) netto", "340,00 €"),
        ("sub", r"Summe (?P<x>673,00 € netto, 800,87 €) brutto\.", "990,00 € netto, 1.178,10 €"),
    ]},
    reason=("Die Bestellung per E-Mail vom 08.03.2027 stuetzt sich auf ein einziges Angebot ueber 990,00 EUR netto (1.178,10 EUR "
            "brutto). Die Grenze von 1.000 EUR gilt fuer den Nettobetrag; darunter ist eine Direktvergabe ohne Vergleichsangebote "
            "moeglich. Loetstationen sind kein Rahmenvertragsprodukt, die Kostenstellenbevollmaechtigte hat in Kopie beauftragt. "
            "Geaendert gegenueber beschaffungsantrag-02: der Nettobetrag (vorher 673,00 EUR), er bleibt unter 1.000 EUR."),
)
variant(
    PROC, "beschaffungsantrag-03", 1, "angenommen",
    "Position 9: '2 × Monitor 27 Zoll, WQHD' from bildschirmlager-vogtland.de → '2 × Lötstation digital 80 W mit Ablage' from "
    "shop.messwerk-oderbruch.de, same price 169,00 € gross each (338,00 €), total 926,93 € unchanged",
    "Only products with a framework contract (PCs, notebooks, monitors) must be ordered from the framework partner; everything "
    "else may be bought on the web under 1.000 EUR net by direct award (3: ground truth; Lötstationen are not a framework "
    "product, 02: ground truth)",
    "E-Mail: item 9 text, its URL, and the sentence 'Die Monitore sind für die zwei neuen Messplätze' → 'Die Lötstationen …'",
    "The other eight items are not framework products according to the organisers' reason for the original; if the hidden "
    "rule set counted another of them, the original would have said so",
    {MAIL: [
        ("sub", r"9\. 2 × (?P<x>Monitor 27 Zoll, WQHD, höhenverstellbar), je 169,00", "Lötstation digital 80 W mit Ablage"),
        ("sub", r"(?P<x>https://www\.bildschirmlager-vogtland\.de/produkt/27-wqhd-hv-2207)", "https://shop.messwerk-oderbruch.de/p/40318"),
        ("sub", r"^[ ]*Die (?P<x>Monitore) sind für die zwei neuen Messplätze", "Lötstationen"),
    ]},
    reason=("Sammelbestellung vom 15.04.2027 mit neun Positionen ueber zusammen 926,93 EUR brutto (unter 1.000 EUR netto, "
            "Direktvergabe). Keine der Positionen, auch nicht die Loetstationen in Position 9, ist ein Rahmenvertragsprodukt "
            "(Rahmenvertrag nur fuer PCs, Notebooks und Monitore), daher ist der Webshop-Kauf zulaessig. Geaendert gegenueber "
            "beschaffungsantrag-03: Position 9 (vorher zwei Monitore vom Webshop)."),
)
variant(
    PROC, "beschaffungsantrag-04", 1, "angenommen",
    "Stated net total of the form 3.384,00 € → 2.400,00 € (= sum of its own positions, = offer = award note); VAT 642,96 → 456,00 €, "
    "gross 4.026,96 → 2.856,00 €",
    "Amounts in the request must equal the sum of the positions and the offer and award documents (policy `consistency_check`); "
    "three offers were obtained and the cheapest won",
    "Beschaffungsantrag: the three summary lines (net, VAT, gross); the other four PDFs copied byte for byte",
    "The offer PDFs are not re-read by us here; gold for the original names the total as the only defect",
    {"beschaffungsantrag.pdf": [
        ("sub", r"Summe netto[ ]+(?P<x>3\.384,00 €)", "2.400,00 €"),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>642,96 €)", "456,00 €"),
        ("sub", r"Gesamtbetrag brutto[ ]+(?P<x>4\.026,96 €)", "2.856,00 €"),
    ]},
    reason=("Die Positionen (3 Netzgeraete zu 740,00 EUR und 3 Schnittstellenmodule zu 60,00 EUR) ergeben 2.400,00 EUR netto; "
            "diesen Betrag nennen auch Antrag (Summe netto 2.400,00 EUR), Angebot HB-270512 und Vergabevermerk. Drei Angebote "
            "liegen vor, das guenstigste erhaelt den Zuschlag. Geaendert gegenueber beschaffungsantrag-04: die Summe im Antrag "
            "(vorher 3.384,00 EUR, 41 % ueber der Positionssumme)."),
)
variant(
    PROC, "beschaffungsantrag-05", 1, "abgelehnt",
    "Intended supplier 'Tessmer & Kolb Systemhaus GmbH, Offenbach' (the framework partner) → 'Datenwerk Nordhessen GmbH, Kassel'; "
    "the WPS cart still names Tessmer & Kolb as framework partner",
    "Products with a framework contract must be ordered only from the framework partner (3: ground truth; policy `framework_contracts`)",
    "Beschaffungsantrag: the line 'Vorgesehener Lieferant'; the WPS cart copied byte for byte",
    "The Antrag still says 'Abruf aus Rahmenvertrag über WPS'; the contradiction with the new supplier is the defect. "
    "A model may see it as an inconsistency rather than as the framework rule: same label, different reason",
    {"beschaffungsantrag.pdf": [
        ("sub", r"Vorgesehener Lieferant[ ]+(?P<x>Tessmer & Kolb Systemhaus GmbH, Offenbach)", "Datenwerk Nordhessen GmbH, Kassel"),
    ]},
    reason=("Notebooks, Monitore und Dockingstationen sind Rahmenvertragsprodukte (WPS-Warenkorb WK-0027-18834, Rahmenvertragspartner "
            "Tessmer & Kolb Systemhaus GmbH). Als Lieferant ist aber die Datenwerk Nordhessen GmbH vorgesehen; Rahmenvertragsprodukte "
            "sind ausschliesslich beim Rahmenvertragspartner zu bestellen. Geaendert gegenueber beschaffungsantrag-05: der "
            "vorgesehene Lieferant."),
)

# ---- Expense reimbursement ------------------------------------------------- #
variant(
    EXP, "auslagenerstattung-01", 1, "abgelehnt",
    "Bill-to and deliver-to: Universität Wernstadt / Lehrstuhl → a private person at a private address (Henrike Salzmann, Marburg)",
    "An invoice to a private person with no business reference anywhere is not reimbursable (expense 03 ground truth; "
    "policy `invoice_recipient`)",
    "Rechnung: the 'Bill to' block (4 lines) and the 'Deliver to' block (5 lines → 4); amounts, order, card unchanged",
    "The book is a specialist title, a model may argue business relevance from the topic; the invoice itself has none. "
    "The name is invented",
    {"rechnung-fachbuch.pdf": [
        ("sub", r"^(?P<x>Universität Wernstadt)$", "Henrike Salzmann"),
        ("sub", r"^(?P<x>Zentraler Rechnungseingang)", "Gartenstraße 11"),
        ("sub", r"^(?P<x>Am Lindenhang 40)[ ]+VAT ID", "35037 Marburg"),
        ("sub", r"^(?P<x>35291 Wernstadt)[ ]+support@", "Deutschland"),
        ("sub", r"^(?P<x>Universität Wernstadt, Fachbereich 71 Elektrotechnik und)$", "Henrike Salzmann"),
        ("sub", r"^(?P<x>Informatik)$", "Gartenstraße 11"),
        ("sub", r"^(?P<x>Lehrstuhl für Stochastische Systeme, Prof\. Dr\. Ysolde Brammertz)$", "35037 Marburg"),
        ("sub", r"^(?P<x>Am Lindenhang 40, Geb\. F, Raum 2\.107)$", "Germany"),
        ("drop", r"^35291 Wernstadt, Germany$"),
    ]},
    reason=("Rechnung und Lieferadresse lauten auf Henrike Salzmann, Gartenstrasse 11, Marburg; die Universitaet, eine Einrichtung "
            "oder ein dienstlicher Zweck kommen auf dem Beleg nicht vor. Eine Rechnung an eine Privatperson ohne jeden "
            "dienstlichen Bezug ist nicht erstattungsfaehig. Geaendert gegenueber auslagenerstattung-01: Rechnungs- und "
            "Lieferempfaenger (vorher Universitaet Wernstadt, Lehrstuhl fuer Stochastische Systeme)."),
)
variant(
    EXP, "auslagenerstattung-02", 1, "abgelehnt",
    "Handwritten note 'Kabelbinder + Schrumpfschlauch für Versuchsstand Labor E 3.12 (F. Kallweit-Omondi)' removed from the till receipt",
    "A till receipt without article names is acceptable only if the purpose is noted by hand or otherwise traceable "
    "(policy `proof_of_purchase`; expense 02 ground truth)",
    "Beleg: the three note lines deleted; shop, article numbers, amounts, date unchanged",
    "The README shows no ground truth for 'receipt without note'; the label follows the rule text. Receipt page size kept",
    {"beleg-1.pdf": [
        ("drop_range", r"^[ ]*Kabelbinder \+ Schrumpfschlauch", r"\(F\. Kallweit-Omondi\)"),
    ]},
    reason=("Der Kassenbon eines Baufachmarkts vom 13.03.27 ueber 19,86 EUR nennt nur Artikelnummern. Es fehlt jeder Vermerk, "
            "wofuer die Ware gekauft wurde. Ohne Artikelbezeichnung und ohne handschriftlichen oder anderweitig "
            "nachvollziehbaren Verwendungszweck ist der Beleg kein ordnungsgemaesser Zahlungsbeleg. Geaendert gegenueber "
            "auslagenerstattung-02: der handschriftliche Vermerk fehlt."),
)
variant(
    EXP, "auslagenerstattung-04", 1, "angenommen",
    "Pro-forma invoice PF-27-0934 stamped 'bezahlt' → final invoice RE-27-0934 (header, number, intro and closing sentences "
    "rewritten; same items, amounts, date, BEZAHLT stamp)",
    "A pro-forma document is not a receipt; the actual invoice marked as paid is required (policy `proforma_documents`). "
    "Here the document is the actual paid invoice",
    "Rechnung: 'Pro-forma-Nr.' line, heading, the 'bitte überweisen' sentence, and the 'keine Rechnung' sentence",
    "Medium: no delivery note is attached and the invoice date is the pro-forma date; the original gold names only the "
    "pro-forma status as the defect",
    {"rechnung-laborbedarf.pdf": [
        ("sub", r"(?P<x>Pro-forma-Nr\.: PF-27-0934)", "Rechnung Nr.: RE-27-0934"),
        ("sub", r"^(?P<x>Pro-forma-Rechnung)$", "Rechnung"),
        ("sub", r"^(?P<x>Bitte überweisen Sie den Betrag vorab; die Ware wird nach Zahlungseingang versandt\.)$",
         "Der Betrag wurde vorab überwiesen; die Ware wurde nach Zahlungseingang versandt."),
        ("sub", r"^(?P<x>Dieses Dokument ist keine Rechnung im umsatzsteuerlichen Sinn\. Die Rechnung erhalten Sie mit der Lieferung\.)",
         "Vielen Dank für Ihre Bestellung."),
    ]},
    reason=("Eingereicht ist die Rechnung RE-27-0934 vom 02.06.2027 ueber 88,93 EUR fuer Pipettenspitzen und Handschuhe, adressiert "
            "an das Fachgebiet Biosensorik der Universitaet Wernstadt, mit dem Vermerk bezahlt vom 03.06.2027. Es ist eine "
            "tatsaechliche, als bezahlt gekennzeichnete Rechnung mit Artikelbezeichnungen, kein Pro-forma-Dokument. Geaendert "
            "gegenueber auslagenerstattung-04: das Dokument ist die endgueltige Rechnung (vorher Pro-forma-Rechnung PF-27-0934)."),
)
variant(
    EXP, "auslagenerstattung-05", 1, "abgelehnt",
    "Claim 'zu erstatten: 121,38 € + 83,32 € ./. 69,02 € = 135,68 €' (net of credit note) → '121,38 € + 83,32 € = 204,70 €' "
    "(credit note not deducted)",
    "If part of an order is credited, only the amount after deducting the credit note is reimbursable (policy `credit_notes`)",
    "Gutschrift (the page carrying the handwritten claim): the claim line and the reference line (', GS 27-0031' dropped)",
    "A human reviewer might reimburse the correct net amount instead of rejecting; the task prescribes a binary label, "
    "and a claim above the net amount is the defect",
    {"gutschrift-druckerei.pdf": [
        ("sub", r"zu erstatten: (?P<x>121,38 € \+ 83,32 € \./\. 69,02 € = 135,68 €)", "121,38 € + 83,32 € = 204,70 €"),
        ("sub", r"\(RE 27-0612, RE 27-0618(?P<x>, GS 27-0031)\) W\.A\.", ""),
    ]},
    reason=("Handschriftlich werden 204,70 EUR geltend gemacht (RE 27-0612 ueber 121,38 EUR plus RE 27-0618 ueber 83,32 EUR). "
            "Die Gutschrift GS 27-0031 ueber 69,02 EUR fuer zwei Fehldrucke ist nicht abgezogen. Erstattungsfaehig ist nur der "
            "Betrag nach Abzug der Gutschrift, 135,68 EUR. Geaendert gegenueber auslagenerstattung-05: der beantragte Betrag "
            "(vorher 135,68 EUR)."),
)


# --------------------------------------------------------------------------- #
# Text editing
# --------------------------------------------------------------------------- #
def pdftotext(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True,
                          text=True).stdout


def page_size(path):
    out = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout
    m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", out)
    return float(m.group(1)), float(m.group(2))


def _realign(line, a, b, new):
    """Replace line[a:b] by `new`, keeping the right edge of a right-aligned field or the
    start of the next column when the lengths differ."""
    d = len(new) - (b - a)
    before, after = line[:a], line[b:]
    if d == 0:
        return before + new + after
    if after.strip() == "":  # field ends the line: keep its right edge
        if d < 0:
            before += " " * (-d)
        else:
            trail = len(before) - len(before.rstrip(" "))
            if trail >= d + 1:
                before = before[:-d]
        return before + new + after
    lead = len(after) - len(after.lstrip(" "))
    if lead >= 2:  # a gap follows: keep the next column where it was
        if d < 0:
            after = " " * (-d) + after
        elif lead >= d + 1:
            after = after[d:]
    return before + new + after


def apply_ops(text, ops, label):
    for op in ops:
        kind = op[0]
        if kind == "merge_pages":
            text = "\n".join(p.rstrip("\n") for p in text.split("\f") if p.strip()) + "\n"
            continue
        lines = text.split("\n")
        if kind == "sub":
            _, pattern, new = op
            rx = re.compile(pattern)
            hits = [(i, rx.search(l)) for i, l in enumerate(lines)]
            hits = [(i, m) for i, m in hits if m]
            if len(hits) != 1:
                raise SystemExit(f"{label}: pattern {pattern!r} matched {len(hits)} lines, need exactly 1")
            i, m = hits[0]
            lines[i] = _realign(lines[i], m.start("x"), m.end("x"), new)
        elif kind == "drop":
            rx = re.compile(op[1])
            idx = [i for i, l in enumerate(lines) if rx.search(l)]
            if len(idx) != 1:
                raise SystemExit(f"{label}: drop {op[1]!r} matched {len(idx)} lines, need exactly 1")
            del lines[idx[0]]
        elif kind == "drop_range":
            ra, rb = re.compile(op[1]), re.compile(op[2])
            ia = [i for i, l in enumerate(lines) if ra.search(l)]
            ib = [i for i, l in enumerate(lines) if rb.search(l)]
            if len(ia) != 1 or len(ib) != 1 or ib[0] < ia[0]:
                raise SystemExit(f"{label}: drop_range {op[1]!r}..{op[2]!r} not unique/ordered")
            del lines[ia[0]:ib[0] + 1]
        else:
            raise SystemExit(f"{label}: unknown op {kind}")
        text = "\n".join(lines)
    return text


# --------------------------------------------------------------------------- #
# Minimal PDF writer: Courier, WinAnsi, text lines only
# --------------------------------------------------------------------------- #
def _pdf_str(s):
    raw = s.encode("cp1252")  # raises if a character is not in WinAnsi
    out = bytearray()
    for byte in raw:
        ch = chr(byte)
        if ch in "\\()":
            out += b"\\" + ch.encode()
        elif 32 <= byte < 127:
            out.append(byte)
        else:
            out += b"\\%03o" % byte
    return bytes(out)


def write_pdf(path, text, size, title):
    w, h = size
    margin = 28.0
    pages = [p.rstrip("\n").split("\n") for p in text.split("\f") if p.strip()]
    longest = max(len(l.rstrip()) for p in pages for l in p)
    fs = min(9.0, (w - 2 * margin) / (0.6 * max(longest, 1)))
    lead = fs * 1.25
    cap = int((h - 2 * margin) / lead)
    chunks = []
    for p in pages:
        for k in range(0, len(p), cap):
            chunks.append(p[k:k + cap])
    objs = []  # bytes of each object body, 1-based ids
    n_pages = len(chunks)
    # ids: 1 catalog, 2 pages, 3 font, 4 info, then (page, content) pairs
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Title (" + _pdf_str(title) + b") /Author () /Creator () /Producer () /Subject () >>")
    for i, lines in enumerate(chunks):
        content = bytearray()
        for j, line in enumerate(lines):
            line = line.rstrip()
            if not line:
                continue
            y = h - margin - fs - j * lead
            content += f"BT /F1 {fs:.3f} Tf {margin:.2f} {y:.2f} Td (".encode() + _pdf_str(line) + b") Tj ET\n"
        comp = zlib.compress(bytes(content))
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.4f} {h:.4f}] /Contents {6 + 2 * i} 0 R "
                     f"/Resources << /Font << /F1 3 0 R >> /ProcSet [/PDF /Text] >> >>").encode())
        objs.append(f"<< /Filter /FlateDecode /Length {len(comp)} >>\nstream\n".encode() + comp + b"\nendstream")
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    pathlib.Path(path).write_bytes(bytes(buf))


# --------------------------------------------------------------------------- #
# Build and verify
# --------------------------------------------------------------------------- #
def norm(text):
    """Comparable form of a pdftotext dump: single spaces, no blank lines, no page breaks."""
    return [re.sub(r"[ ]+", " ", l).strip() for l in text.replace("\f", "\n").split("\n") if l.strip()]


def build():
    problems = []
    for s in SETS:
        d = OUT / s
        if (d / "inputs").exists():
            shutil.rmtree(d / "inputs")
        (d / "inputs").mkdir(parents=True)
    truth = {s: [] for s in SETS}
    for v in V:
        src = DATASETS / v["set"] / "inputs" / v["base"]
        dst = OUT / v["set"] / "inputs" / v["id"]
        dst.mkdir(parents=True)
        for pdf in sorted(src.glob("*.pdf")):
            if pdf.name in v["drop_docs"]:
                continue
            target = dst / pdf.name
            if pdf.name not in v["edits"]:
                shutil.copyfile(pdf, target)
                if target.read_bytes() != pdf.read_bytes():
                    problems.append(f"{v['id']}/{pdf.name}: copy differs")
                continue
            old = pdftotext(pdf)
            new = apply_ops(old, v["edits"][pdf.name], f"{v['id']}/{pdf.name}")
            write_pdf(target, new, page_size(pdf), pdf.name)
            got = pdftotext(target)
            if norm(got) != norm(new):
                problems.append(f"{v['id']}/{pdf.name}: text does not round-trip")
                a, b = norm(got), norm(new)
                for x, y in zip(a, b):
                    if x != y:
                        problems.append(f"   got : {x}\n   want: {y}")
                        break
            if norm(new) == norm(old):
                problems.append(f"{v['id']}/{pdf.name}: edit changed nothing")
        unknown = set(v["edits"]) - {p.name for p in src.glob("*.pdf")}
        if unknown:
            problems.append(f"{v['id']}: edits for missing documents {sorted(unknown)}")
        truth[v["set"]].append({"antrag": v["id"], "result": v["result"], "begruendung": v["reason"]})
    for s in SETS:
        with open(OUT / s / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for row in sorted(truth[s], key=lambda r: r["antrag"]):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return problems


def table():
    rows = ["| Variant | Base case | Changed fact (old → new) | Expected | Rule and source | How built | Risks |",
            "|---|---|---|---|---|---|---|"]
    for v in V:
        short = {TRIP: "trip", PROC: "proc", EXP: "exp"}[v["set"]]
        rows.append(f"| `{v['id']}` ({short}) | `{v['base']}` | {v['changed']} | {v['result']} | {v['rule']} | {v['how']} | {v['risk']} |")
    return "\n".join(rows)


def main():
    if "--table" in sys.argv:
        print(table())
        return
    problems = build()
    counts = {s: sum(1 for v in V if v["set"] == s) for s in SETS}
    print("built:", counts, "labels:", {r: sum(v["result"] == r for v in V) for r in ("angenommen", "abgelehnt")})
    for p in problems:
        print("PROBLEM:", p)
    if "--check" in sys.argv and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
