from snippets import *  # noqa
import snippets
add = snippets.add
add("E27 card statement lists an unrelated restaurant payment", "M", "FALSE", "expense_reimbursement",
    {"rechnung-fachbuch.pdf": "Universität Wernstadt\nRechnung Nr. 2027-118\nRechnung\n Fachbuch  1  49,90 €\n Rechnungsbetrag   49,90 €",
     "kreditkartenabrechnung.pdf": "Kreditkartenabrechnung\n 02.03.2027  Restaurant Da Mario   -38,50 EUR\n 03.03.2027  Buchhandlung Uhrturm  -49,90 EUR"},
    "ohne Anlass und Liste", "MEAL_RE scans the first 600 chars of every document")
add("E28 seminar-room invoice from 'Hotel & Restaurant Zur Post'", "M", "FALSE", "expense_reimbursement",
    {"rechnung-raummiete.pdf": "Hotel & Restaurant Zur Post\nUniversität Wernstadt, FG Hochfrequenztechnik\nRechnung Nr. 7781\nRechnung\n Raummiete Seminarraum Workshop  1  300,00 €\n Rechnungsbetrag  300,00 €"},
    "ohne Anlass und Liste", "")
add("T22 Sallstedt trip with a conference dinner row (other state's law)", "L", "FALSE?", "business_trip",
    {"antrag-dienstreise.pdf": "Technische Hochschule Sallstedt\n" + trip(extra_row="Conference Dinner                                   1              65,00 €")},
    "Abendprogramm", "Kassel rule applied to a Sallstedt case")
add("P22 Kopierpapier from a web shop, below 1000 (true defect, control)", "M", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen bei papier-direkt.de:\n 1. 10 × Kopierpapier A4, 500 Blatt, je 4,99 € brutto = 49,90 €\nGesamtsumme: 49,90 € brutto."},
    "Rahmenvertrags-Produktgruppe", "control")
