"""Adversarial snippets for facts.compute_facts (robustness audit, 11.10.2026); test_traps.py runs them.

Each case: (id, likelihood H/M/L, kind, case_type, docs, want)
kind  FALSE = a correct (accepted) case; any note matching `want` is a false alarm
      MISS  = a broken case; a note matching `want` should appear
want  substring of the expected/unwanted note ('' = any note)
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from facts import compute_facts  # noqa: E402
from parsing import parse_amounts, parse_dates  # noqa: E402

TRIP_FORM = """ANTRAG AUF DIENSTREISEGENEHMIGUNG
Allgemeine Daten
Reiseziel:                                 {dest}
Anlass:                                    {anlass}
Reise ins Ausland:                         {ausland}
Datum der Antragstellung:                  {applied}
Reiseverlauf
Start:                                     {start}
Ende:                                      {end}
Rückreise:                                 {back}
priv. Aufenthalt:                          {priv}
Voraussichtliche Kosten (Schätzung)
 Bahn Hin- und Rückfahrt                                                1             145,00 €
 Unterkunft, 2 Nächte                                                   2             190,00 €
 {extra_row}
Finanzierung:                              {fin}
"""


def trip(**kw):
    base = dict(dest="Leipzig", anlass="Fachtagung Digitale Verwaltung 2026", ausland="[ ] ja   [X] nein",
                applied="12.02.2026", start="09.03.2026", end="11.03.2026", back="Bahn, 11.03.2026",
                priv="keiner", extra_row="Konferenzgebühr                                       1             180,00 €",
                fin="Fachgebietsbudget, Kostenstelle 5588-11")
    base.update(kw)
    return TRIP_FORM.format(**base)


PROC_FORM = """Beschaffungsantrag / Bestellanforderung
Kostenstellenbevollmächtigte:r                      Prof. Dr. Anselm Quadflieg
Rahmenvertragsprodukt                               {rv}
Eingeholte Angebote                                 {n}
Vorgesehener Lieferant                              {supplier}
 Pos.       Bezeichnung                                              Menge        EP netto        GP netto
 1          {item}                                                       {qty}       {ep}      {gp}
 Summe netto                                                                                   {net}
 zzgl. 19 % USt.                                                                               {vat}
 Gesamtbetrag brutto                                                                           {gross}
 {reason}
"""


def proc(**kw):
    base = dict(rv="[ ] ja [X] nein", n="3", supplier="Oszillo-Kontor Vehrs GmbH, Lüneburg",
                item="Digitales Speicheroszilloskop, 4 Kanäle", qty="1", ep="2.667,00 €", gp="2.667,00 €",
                net="2.667,00 €", vat="506,73 €", gross="3.173,73 €", reason="")
    base.update(kw)
    return PROC_FORM.format(**base)


def offer(net, item="Digitales Speicheroszilloskop, 4 Kanäle", head="Angebot", extra=""):
    return f"""Universität Wernstadt                                   Lieferant GmbH
{head}
 Bezeichnung                                    Menge   Einzelpreis   Gesamt netto
 {item}                                            1     {net}     {net}
{extra}                                                   Summe netto    {net}
                                               Angebotssumme brutto    9.999,99 €
"""


CASES = []


def add(cid, lik, kind, ctype, docs, want, why):
    CASES.append((cid, lik, kind, ctype, docs, want, why))


# ---------------------------------------------------------------- business trip
add("T01 form label names 'Stipendium' as an example", "H", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": trip(fin="Fachgebietsbudget\nLeistungen Dritter (z. B. Stipendium, Reisekostenzuschuss):  [ ] ja  [X] nein")},
    "Finanzierung durch Dritte", "a printed form label triggers the third-party note on every trip")
add("T02 conference e-mail advertises travel grants", "M", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": trip(),
     "email-annahme-konferenz.pdf": "Dear author, your paper has been accepted.\nA limited number of student travel grants is available; apply by 1 March."},
    "Finanzierung durch Dritte", "boilerplate in an acceptance mail")
add("T03 same-day application before departure", "L", "FALSE?", "business_trip",
    {"antrag-dienstreise.pdf": trip(applied="09.03.2026", start="09.03.2026, 14:00 Uhr")},
    "Reisebeginn gestellt", ">= flags same day; rule says 'vorher'")
add("T04 separate retroactive application with reasons", "M", "FALSE?", "business_trip",
    {"antrag-nachtraegliche-genehmigung.pdf": trip(applied="20.03.2026") +
     "\nAntrag auf nachträgliche Genehmigung. Begründung: kurzfristige Einladung durch das Ministerium.\nStellungnahme der Fachgebietsleitung: befürwortet."},
    "Reisebeginn gestellt", "the 'gesonderter Antrag' route of the rule card")
add("T05 student field trip (Exkursion) as the purpose", "M", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": trip(anlass="Geländeexkursion mit Studierenden",
                                    extra_row="Exkursion Busmiete Harz                               1             450,00 €")},
    "Abendprogramm", "'Exkursion' is in EVENING_RE")
add("T06 conference about Ukraine held in Rome", "L", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": trip(dest="Rom, ITALIEN", anlass="Ukraine Recovery Conference 2026", ausland="[X] ja   [ ] nein")},
    "nicht genehmigt", "Anlass field scanned for country names")
add("T07 'Tel-Aviv' with a hyphen", "M", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(dest="Tel-Aviv", ausland="[X] ja   [ ] nein")},
    "nicht genehmigt", "pattern needs 'Tel Aviv' with a space")
add("T08 destination label 'Zielort' instead of 'Reiseziel'", "M", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip().replace("Reiseziel:  ", "Zielort:    ").replace("Leipzig", "Haifa, Israel")},
    "nicht genehmigt", "only Reiseziel/Anlass/Zweck/Ort are read")
add("T09 form file without 'antrag' in its name, late application", "H", "MISS", "business_trip",
    {"dienstreisegenehmigung.pdf": trip(applied="20.03.2026")},
    "Reisebeginn gestellt", "form found only by filename")
add("T10 English travel request, late", "M", "MISS", "business_trip",
    {"travel-request.pdf": "TRAVEL REQUEST\nDestination:        Leipzig\nDate of application: 2026-03-20\nDeparture:          2026-03-09\n"},
    "Reisebeginn gestellt", "English labels not read")
add("T11 two files with 'antrag': an attachment sorts first", "M", "MISS", "business_trip",
    {"anlage-zum-antrag-programm.pdf": "Programm der Tagung, 10.-11. März 2026",
     "antrag-dienstreise.pdf": trip(applied="20.03.2026")},
    "Reisebeginn gestellt", "next() takes the first file whose name has 'antrag'")
add("T12 private stay of 6 working days", "H", "FALSE?", "business_trip",
    {"antrag-dienstreise.pdf": trip(priv="11.09.2026 bis 18.09.2026 (6 Arbeitstage, Urlaub im Anschluss)")},
    "", "no check for > 5 working days (variant 04-v1 is missed by Qwen)")
add("T13 return trip missing, Ausland box empty for France", "H", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(dest="Lyon, FRANKREICH", ausland="[ ] ja   [ ] nein   (Feld nicht ausgefüllt)", back="—")},
    "", "facts print 'nicht angekreuzt' but give no note (practice trip 03 is missed by Qwen)")
add("T14 dinner booked in the registration, fee in the form", "M", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(extra_row="Konferenzgebühr inkl. gebuchter Zusatzleistungen       1             265,00 €"),
     "konferenz-registrierung.pdf": " Registration fee            1     180,00 €\n Conference Dinner           1      85,00 €\n Total                             265,00 €"},
    "Abendprogramm", "only form rows are scanned")
add("T15 English cost row 'Social dinner'", "M", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(extra_row="Social dinner (optional)                              1              60,00 €")},
    "Abendprogramm", "'Social dinner' not in EVENING_RE")
add("T16 US date in application field, late", "L", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(applied="03/20/2026", start="03/09/2026")},
    "Reisebeginn gestellt", "slash dates not parsed")
add("T17 'Start' line with weekday and month name, normal", "H", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": trip(applied="12. Februar 2026", start="Montag, 9. März 2026, 07:00 Uhr")},
    "Reisebeginn gestellt", "control: should be quiet")
add("T18 Antragsdatum later than the 'Zuletzt geändert' header", "M", "FALSE", "business_trip",
    {"antrag-dienstreise.pdf": "Zuletzt geändert am: 15. März 2026\n" + trip()},
    "Reisebeginn gestellt", "control: header date is not the application date")
add("T19 Hotel 95 EUR/night in Germany without reason", "M", "FALSE?", "business_trip",
    {"antrag-dienstreise.pdf": trip().replace("Unterkunft, 2 Nächte                                                   2             190,00 €",
                                             "Unterkunft, 2 Nächte à 95,00 €                                         2             190,00 €")},
    "", "no 80 EUR check")
add("T20 Online conference filed as a trip", "M", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(anlass="Online-Konferenz ICIS 2026 (virtuell, Teilnahme per Zoom)")},
    "", "no online check")

# ---------------------------------------------------------------- procurement
add("P01 three offers in one combined PDF", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(),
     "angebote.pdf": offer("2.667,00 €") + "\f" + offer("2.783,00 €") + "\f" + offer("2.745,00 €")},
    "Angebot(e) vorgelegt", "offers counted per file")
add("P02 offer files named after the vendor, header 'ANGEBOT Nr. ...'", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(),
     "vehrs-gmbh.pdf": offer("2.667,00 €", head="ANGEBOT Nr. AN-27-0311"),
     "pilz-kg.pdf": offer("2.783,00 €", head="ANGEBOT Nr. 2027/0457"),
     "quistorp.pdf": offer("2.745,00 €", head="Angebot Nr. Q-104882 vom 12.02.2027")},
    "Angebot(e) vorgelegt", "offer header must be a line with only 'Angebot'")
add("P03 English quotations named after vendors", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(),
     "acme.pdf": "QUOTATION No. Q-2231\n Oscilloscope 4ch      1   EUR 2,667.00\n Net total    EUR 2,667.00",
     "keysight.pdf": "QUOTATION No. 88123\n Oscilloscope 4ch      1   EUR 2,783.00\n Net total    EUR 2,783.00",
     "rs.pdf": "Quotation 5512\n Oscilloscope 4ch      1   EUR 2,745.00\n Net total    EUR 2,745.00"},
    "Angebot(e) vorgelegt", "'Quotation No.' line and 'Net total' not recognised")
add("P04 one offer with a single-source justification", "M", "FALSE?", "procurement",
    {"beschaffungsantrag.pdf": proc(n="1", reason="Begründung: Ersatzteil nur beim Hersteller erhältlich (Alleinstellungsmerkmal), weitere Angebote nicht möglich."),
     "angebot-1.pdf": offer("2.667,00 €")},
    "Angebot(e) vorgelegt", "GT 02-e1 says 'Vergleichsangebote oder eine Begruendung'")
add("P05 partner named in a sentence: 'beim Rahmenvertragspartner der Universität (Bechtle GmbH)'", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(rv="[X] ja [ ] nein", n="0", supplier="Bechtle GmbH, Kassel", item="Monitor 27 Zoll WQHD",
                                    qty="10", ep="218,60 €", gp="2.186,00 €", net="2.186,00 €", vat="415,34 €", gross="2.601,34 €",
                                    reason="Bestellung beim Rahmenvertragspartner der Universität (Bechtle GmbH) über WPS.")},
    "", "first word after 'Rahmenvertragspartner' is 'der'")
add("P06 WPS basket labelled 'Katalog: Rahmenvertrag ...' (no word 'Rahmenvertragspartner')", "H", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(rv="[X] ja [ ] nein", n="0", supplier="Officeplus GmbH, Kassel", item="Bürodrehstuhl ergonomisch",
                                    qty="8", ep="289,00 €", gp="2.312,00 €", net="2.312,00 €", vat="439,28 €", gross="2.751,28 €"),
     "wps-warenkorb.pdf": "WPS Warenbestellsystem\nWarenkorb WK-0027-20011\nKatalog:      Rahmenvertrag Büroausstattung, Los 1\nLieferant:    Officeplus GmbH, Kassel\n RV-ST-0815  Bürodrehstuhl ergonomisch   8   289,00 €   2.312,00 €\n Warenwert netto   2.312,00 €"},
    "", "the procurement-05 trap reworded; two false notes")
add("P07 vendor footer 'Rahmenvertragspartner des Landes Hessen'", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(rv="[X] ja [ ] nein", n="0", supplier="Tessmer & Kolb Systemhaus GmbH", item="Notebook 14 Zoll Vertragskonfiguration A",
                                    qty="2", ep="1.127,40 €", gp="2.254,80 €", net="2.254,80 €", vat="428,41 €", gross="2.683,21 €"),
     "wps-warenkorb.pdf": "Warenkorb WK-0027-18834\nLieferant (Rahmenvertragspartner)   Tessmer & Kolb Systemhaus GmbH\n RV-NB-14 Notebook 14 Zoll  2  1.127,40 €  2.254,80 €\n Warenwert netto  2.254,80 €",
     "angebot-hinweis.pdf": "Tessmer & Kolb Systemhaus GmbH ist Rahmenvertragspartner des Landes Hessen."},
    "", "first partner line wins; here the WPS line comes later by filename")
add("P08 TH Sallstedt orders a monitor from a web shop (Kassel framework not binding)", "M", "FALSE?", "procurement",
    {"email-beschaffungsantrag.pdf": "Technische Hochschule Sallstedt, Medienlabor\nBitte bestellen:\n 1. 1 × Monitor 27 Zoll, je 169,00 € brutto = 169,00 €\nGesamtsumme: 169,00 € brutto."},
    "Rahmenvertrags-Produktgruppe", "README: Sallstedt cases are decided on the documents alone")
add("P09 offer with discount, 'Nettobetrag' before 'Endbetrag netto'", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(n="3", net="2.660,00 €", ep="2.660,00 €", gp="2.660,00 €"),
     "angebot-1.pdf": "Angebot\n Speicheroszilloskop  1  2.800,00 €\n Nettobetrag     2.800,00 €\n abzgl. 5 % Rabatt  -140,00 €\n Endbetrag netto  2.660,00 €",
     "angebot-2.pdf": offer("2.783,00 €"), "angebot-3.pdf": offer("2.745,00 €")},
    "", "offer net read as 2.800, request 2.660 -> 'passt zu keinem Angebot' and wrong ranking")
add("P10 request orders a subset of the offer (optional item dropped)", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(n="1", net="680,00 €", ep="680,00 €", gp="680,00 €", vat="129,20 €", gross="809,20 €"),
     "angebot-1.pdf": "Angebot\n Lötstation 1  680,00 €\n Optional: Heißluftmodul 1  140,00 €\n Summe netto  820,00 €"},
    "passt zu keinem Angebot", "material?: README says only material deviations count")
add("P11 cheapest offer technically unsuitable, reason in award note", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(),
     "angebot-1.pdf": offer("2.667,00 €"), "angebot-2.pdf": offer("2.490,00 €"), "angebot-3.pdf": offer("2.745,00 €"),
     "vergabevermerk.pdf": "Vergabevermerk\nAngebot 2 (2.490,00 € netto) erfüllt die Mindestanforderung 350 MHz nicht und scheidet aus.\nZuschlag an Vehrs, 2.667,00 € netto (günstigstes geeignetes Angebot)."},
    "günstigste", "rule: cheapest 'bei gleicher technischer Eignung'")
add("P12 studio monitor speakers in a media-lab order", "L", "FALSE", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen (Medienlabor):\n 1. 2 × Monitor 5 Zoll aktiv (Lautsprecher), je 149,00 € brutto = 298,00 €\nGesamtsumme: 298,00 € brutto."},
    "Rahmenvertrags-Produktgruppe", "'Monitor' as loudspeaker")
add("P13 notebook power supply", "L", "FALSE", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen:\n 1. 3 × Netzteil Notebook 65 W USB-C, je 29,90 € brutto = 89,70 €\nGesamtsumme: 89,70 € brutto."},
    "Rahmenvertrags-Produktgruppe", "accessory after a noun")
add("P14 toner and folders from a web shop (Büromaterial)", "M", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen bei buero-discount24.de:\n 1. 4 × Tonerkartusche schwarz, je 59,00 € brutto = 236,00 €\n 2. 20 × Ordner A4, je 2,49 € brutto = 49,80 €\nGesamtsumme: 285,80 € brutto."},
    "Rahmenvertrags-Produktgruppe", "Büromaterial words not in the list")
add("P15 helium cylinder from a non-partner", "L", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Bestelldatum: 12.06.2026\nBitte bestellen bei Gase-Express:\n 1. 1 × Helium 5.0, Flasche 50 l, 480,00 € netto\nGesamtsumme: 480,00 € netto."},
    "Rahmenvertrags-Produktgruppe", "gases are framework items on the card, not in facts")
add("P16 'Display' and 'office chair' in English", "M", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Please order:\n 1. 2 × 27\" Display WQHD, EUR 169.00 each = EUR 338.00\n 2. 2 × Office chair ergonomic, EUR 210.00 each = EUR 420.00\nTotal: EUR 758.00 gross"},
    "Rahmenvertrags-Produktgruppe", "English item words")
add("P17 framework word later than 45 characters in the description", "M", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen bei sitzwerk-shop.de:\n 1. 2 × Ergonomischer, höhenverstellbarer, schwarzer Bürodrehstuhl mit Armlehnen, je 249,00 € = 498,00 €\nGesamtsumme: 498,00 € brutto."},
    "Rahmenvertrags-Produktgruppe", "head = desc[:45]")
add("P18 item wrapped: amount on the next line", "M", "MISS", "procurement",
    {"email-beschaffungsantrag.pdf": "Bitte bestellen bei bildschirmlager.de:\n 1. 2 × Monitor 27 Zoll WQHD höhenverstellbar\n    je 169,00 € brutto = 338,00 €\nGesamtsumme: 338,00 € brutto."},
    "Rahmenvertrags-Produktgruppe", "only lines with an amount are scanned")
add("P19 request net 'Gesamt netto' after shipping; offer 'Summe netto' before shipping", "M", "FALSE", "procurement",
    {"beschaffungsantrag.pdf": proc(net="2.682,00 €").replace(" Summe netto", " Versand netto     15,00 €\n Gesamtsumme netto"),
     "angebot-1.pdf": offer("2.667,00 €", extra=" Versandkosten pauschal 15,00 € netto\n"), "angebot-2.pdf": offer("2.783,00 €"), "angebot-3.pdf": offer("2.745,00 €")},
    "passt zu keinem Angebot", "shipping outside the offer's 'Summe netto'")

# ---------------------------------------------------------------- expense reimbursement
INV = """Universität Wernstadt                                          Druckwerkstatt Pannewitz
Lehrstuhl für Hochfrequenztechnik
                                                               Rechnung Nr. {no}
Rechnung
 Posterdruck DIN A0                     3     19 %     87,00 €     103,53 €
                                                    Rechnungsbetrag     {total}
"""
add("E01 invoice + till receipt whose total line is 'SUMME' without EUR", "H", "FALSE", "expense_reimbursement",
    {"rechnung-druckerei.pdf": INV.format(no="RE 27-0612", total="50,00 €"),
     "kassenbon-baumarkt.pdf": "BAUFACHMARKT\nART 700184\n2 ST x 4,19   8,38\nSUMME                    19,86\nKabelbinder für Labor E 3.12\nzu erstatten gesamt: 69,86 €"},
    "weicht", "a receipt with no recognised total is silently left out of the sum")
add("E02 invoice + receipt 'Gesamt 19,86 €' + claim", "H", "FALSE", "expense_reimbursement",
    {"rechnung-druckerei.pdf": INV.format(no="RE 27-0612", total="50,00 €"),
     "quittung.pdf": "Taxi Kassel Nord\nQuittung\nFahrt Bahnhof - Campus\nGesamt 19,86 €\nzu erstatten: 69,86 €"},
    "weicht", "'Gesamt' alone not a total label")
add("E03 claim line carries the sum and its parts", "M", "FALSE", "expense_reimbursement",
    {"rechnung-druckerei.pdf": INV.format(no="RE 27-0612", total="121,38 €") + INV.format(no="RE 27-0618", total="83,32 €"),
     "gutschrift-druckerei.pdf": "Gutschrift Nr. GS 27-0031\n Gutschriftsbetrag   69,02 €\nErstattungsbetrag: 135,68 € (Rechnungen 204,70 € abzgl. Gutschrift 69,02 €)"},
    "weicht", "last amount on the claim line is taken")
add("E04 invoice addressed to 'TH Sallstedt' (abbreviation)", "H", "FALSE", "expense_reimbursement",
    {"rechnung-fachbuch.pdf": "TH Sallstedt\nMedienlabor\nBrühlstraße 7\n99643 Sallstedt\n          Rechnung Nr. 2027-118\nRechnung\n Fachbuch Lichttechnik  1  49,90 €\n Rechnungsbetrag   49,90 €"},
    "nicht an die Universität adressiert", "UNI_WORDS lacks 'TH', 'Uni', 'Department'")
add("E05 invoice addressed to 'Uni Wernstadt, FB 71'", "M", "FALSE", "expense_reimbursement",
    {"rechnung-fachbuch.pdf": "Uni Wernstadt, FB 71\nz. Hd. Dr. Brammertz\nAm Lindenhang 40\n          Rechnung Nr. 2027-118\nRechnung\n Fachbuch  1  49,90 €\n Rechnungsbetrag   49,90 €"},
    "nicht an die Universität adressiert", "abbreviation")
add("E06 English invoice 'Bill to: ... Department of Physics'", "M", "FALSE", "expense_reimbursement",
    {"invoice-book.pdf": "Bill to\nDr. Y. Brammertz\nDepartment of Physics, Wernstadt\nInvoice no. FPM-NL-27-004\nDescription  Qty  Net  Gross\n Book  1  €84.02  €89.90\nInvoice total  €89.90"},
    "nicht an die Universität adressiert", "")
add("E07 web-shop invoice: billing address after line 18", "H", "FALSE", "expense_reimbursement",
    {"rechnung-shop.pdf": "\n".join(["Kranich Bauteile GmbH", "Industriestr. 4", "12345 Musterstadt", "Tel. 0123 4567", "Fax 0123 4568",
                                      "www.kranich-bauteile.de", "Geschäftsführer: A. Kranich", "Amtsgericht Musterstadt HRB 1234",
                                      "USt-IdNr. DE123456789", "Bankverbindung: Sparkasse", "IBAN DE00 0000 0000 0000 0000 00", "BIC SPKADE00",
                                      "Kundennummer: 778812", "Bestellnummer: 3018-55", "Bestelldatum: 01.03.2027", "Lieferdatum: 03.03.2027",
                                      "Zahlungsart: Kreditkarte", "Seite 1 von 1", "Rechnungsadresse:", "Universität Wernstadt, FG Eingebettete Systeme",
                                      "Rechnung Nr. KB-2027-5512", " Steckplatinen-Set  6  8,90 €  53,40 €", "Rechnungsbetrag  53,40 €"])},
    "nicht an die Universität adressiert", "head = first 18 lines")
add("E08 taxi receipt (Quittung), purpose handwritten", "M", "FALSE", "expense_reimbursement",
    {"quittung-taxi.pdf": "Taxi Kassel Nord\nQuittung\nFahrt Hbf - Campus Holländischer Platz\nBetrag 23,50 €\nhandschriftlich: Abholung Gastprofessor Dr. Lind, Kolloquium"},
    "nicht an die Universität adressiert", "receipts need a keyword, not an addressee")
add("E09 private invoice + bank statement (column 'Verwendungszweck')", "H", "MISS", "expense_reimbursement",
    {"rechnung-kopfhoerer.pdf": "Herrn Malte Kroll\nAm Weinberg 3\n34117 Kassel\n          Rechnung Nr. 55-1182\nRechnung\n Kopfhörer  1  229,00 €\n Rechnungsbetrag  229,00 €",
     "kontoauszug.pdf": "Kontoauszug\n Buchungstag   Vorgang / Verwendungszweck     Betrag\n 03.03.2027    Hifi-Shop Kassel               -229,00 EUR"},
    "nicht an die Universität adressiert", "practice refund 03: the statement header suppresses the note")
add("E10 invoice mentions 'Gutschrift' in its terms (not a credit note)", "M", "FALSE", "expense_reimbursement",
    {"rechnung-shop.pdf": "Universität Wernstadt\n          Rechnung Nr. KB-2027-5512\nRechnung\nBei Rücksendung erhalten Sie eine Gutschrift.\n Steckplatinen-Set  6  8,90 €  53,40 €\n Rechnungsbetrag  53,40 €\nzu erstatten: 53,40 €"},
    "weicht", "invoice treated as credit note; claim 53,40 vs expected -53,40")
add("E11 hotel/booking invoice with 'Storno' conditions", "L", "FALSE", "expense_reimbursement",
    {"rechnung-seminarraum.pdf": "Universität Wernstadt\n          Rechnung Nr. 7781\nRechnung\nStornobedingungen: kostenfrei bis 14 Tage vorher\n Raummiete Workshop  1  300,00 €\n Rechnungsbetrag  300,00 €\nzu erstatten: 300,00 €"},
    "weicht", "'storno' in first 25 lines")
add("E12 team meeting WITH external partners", "M", "FALSE", "expense_reimbursement",
    {"beleg-catering.pdf": "Bäckerei Café Rosengarten\nKaffee, Kuchen, Brötchen  6 Pers.  48,60 €\nSUMME EUR 48,60\nVermerk: Projekttreffen (Teammeeting) mit externen Partnern der Firma Hydrotec: 4 extern, 2 Beschäftigte"},
    "Bewirtung ohne externe Personen", "INTERNAL_RE fires without checking for external guests")
add("E13 'Arbeitsessen' with mostly external guests", "M", "FALSE?", "expense_reimbursement",
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\nArbeitsessen mit Gutachtern der DFG\nTeilnehmende: Prof. A (extern), Dr. B (extern), Dr. C (extern), Prof. D (Uni)\nRechnungsbetrag 142,00 €"},
    "Bewirtung ohne externe Personen", "policy: 'Arbeitsessen mit überwiegend Universitätsangehörigen'")
add("E14 restaurant receipt with 'Gästeliste:'", "M", "FALSE", "expense_reimbursement",
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\nRechnungsbetrag 142,00 €\nAnlass: Besuch Delegation Universität Turku\nGästeliste: Prof. Virtanen, Dr. Laine (Gäste); Prof. D (Uni Wernstadt)"},
    "ohne Anlass und Liste", "GUEST_LIST_RE has 'Gäste:' but not 'Gästeliste'")
add("E15 restaurant receipt with 'Guests:' (English)", "L", "FALSE", "expense_reimbursement",
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\nRechnungsbetrag 142,00 €\nOccasion: visit of the Turku delegation\nGuests: Prof. Virtanen, Dr. Laine (external)"},
    "ohne Anlass und Liste", "")
add("E16 standard Bewirtungsbeleg with EMPTY 'Bewirtete Person(en):' field", "M", "MISS", "expense_reimbursement",
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\nRechnungsbetrag 142,00 €\nAngaben zum Nachweis von Bewirtungsaufwendungen\nTag der Bewirtung: 03.03.2027\nBewirtete Person(en):\nAnlass der Bewirtung:"},
    "ohne Anlass und Liste", "the printed label counts as a guest list")
add("E17 invoice in CHF, claim in EUR", "L", "FALSE", "expense_reimbursement",
    {"rechnung-tagung.pdf": "Universität Wernstadt\n          Rechnung Nr. ETH-77\nRechnung\n Tagungsband  1  CHF 120,00\n Rechnungsbetrag  CHF 120,00",
     "kreditkarte.pdf": "Kreditkartenabrechnung\n ETH Store Zürich  CHF 120,00  -125,30 EUR\nzu erstatten: 125,30 €"},
    "weicht", "CHF read as EUR")
add("E18 two partial-delivery invoices of one order", "H", "FALSE", "expense_reimbursement",
    {"rechnung-teil-1.pdf": "Universität Wernstadt\nRechnung Nr. KB-1\nBestellnummer: 028-5561-7730914\nTeillieferung 1 von 2\n Kabel 1 20,00 €\n Rechnungsbetrag 20,00 €",
     "rechnung-teil-2.pdf": "Universität Wernstadt\nRechnung Nr. KB-2\nBestellnummer: 028-5561-7730914\nTeillieferung 2 von 2\n Stecker 1 15,00 €\n Rechnungsbetrag 15,00 €"},
    "doppelte Abrechnung", "same order number, different items; marketplaces split orders like this")
add("E19 invoice + order confirmation file 'bestellbestaetigung.pdf' (ae spelling)", "H", "FALSE", "expense_reimbursement",
    {"rechnung.pdf": "Universität Wernstadt\nRechnung Nr. KB-1\nBestellnummer: 028-5561-7730914\n Kabel 1 20,00 €\n Rechnungsbetrag 20,00 €",
     "bestellbestaetigung.pdf": "Ihre Bestellung\nBestellnummer: 028-5561-7730914\n Kabel 1 20,00 €"},
    "doppelte Abrechnung", "exclusion only matches 'bestätigung' with ä")
add("E20 invoice + delivery note (Lieferschein)", "M", "FALSE", "expense_reimbursement",
    {"rechnung.pdf": "Universität Wernstadt\nRechnung Nr. KB-1\nBestellnummer: 028-5561-7730914\n Kabel 1 20,00 €\n Rechnungsbetrag 20,00 €",
     "lieferschein.pdf": "Lieferschein\nBestellnummer: 028-5561-7730914\n Kabel 1 Stück"},
    "doppelte Abrechnung", "")
add("E21 final invoice that names the earlier pro-forma", "M", "FALSE", "expense_reimbursement",
    {"rechnung-laborbedarf.pdf": "Universität Wernstadt\nRechnung Nr. LB-2027-88 (ersetzt Pro-forma-Rechnung PF-2027-12)\nRechnung\n Pipetten  1  80,00 €\n Rechnungsbetrag  80,00 €\nBezahlt am 05.03.2027"},
    "Pro-forma", "any 'pro forma' anywhere sets the flag")
add("E22 USD fee paid by PayPal, PayPal receipt attached", "M", "FALSE", "expense_reimbursement",
    {"receipt-workshop.pdf": "Dr. O. W., c/o Universität Wernstadt\nReceipt\nOnline participation  USD 175.00\nTotal paid  USD 175.00",
     "paypal-zahlungsbeleg.pdf": "PayPal\nSie haben eine Zahlung gesendet\nUSD 175.00 = 160,37 EUR\nTransaktionscode 8KX"},
    "Fremdwährung ohne Zahlungsnachweis", "only 'kontoauszug|kreditkarte|statement' count as proof")
add("E23 same invoice submitted twice (copy), no order number", "M", "FALSE?", "expense_reimbursement",
    {"rechnung-1.pdf": INV.format(no="RE 27-0612", total="121,38 €"), "rechnung-1-kopie.pdf": INV.format(no="RE 27-0612", total="121,38 €")},
    "doppelte Abrechnung", "duplicates found by order number only, not invoice number")
add("E24 OCR without umlaut: 'Universitat Wernstadt'", "M", "FALSE", "expense_reimbursement",
    {"rechnung.pdf": "Universitat Wernstadt\nFachgebiet X\n          Rechnung Nr. 2027-118\nRechnung\n Kabel  1  49,90 €\n Rechnungsbetrag   49,90 €"},
    "nicht an die Universität adressiert", "")
add("E25 private address but 'Kassel' in the vendor header", "M", "MISS", "expense_reimbursement",
    {"rechnung-kopfhoerer.pdf": "Hifi-Studio Kassel GmbH\nHerrn Malte Kroll\nAm Weinberg 3\n34117 Kassel\n          Rechnung Nr. 55-1182\nRechnung\n Kopfhörer  1  229,00 €\n Rechnungsbetrag  229,00 €"},
    "nicht an die Universität adressiert", "'kasse' in 'Kassel' turns NEIN into unklar")
add("E26 internal coffee for staff meeting, worded 'Jour fixe'", "M", "MISS", "expense_reimbursement",
    {"beleg-1.pdf": "Bäckerei Rosengarten\nKaffee, Kuchen  8 Pers.\nSUMME EUR 32,40\nVermerk: Jour fixe des Fachgebiets"},
    "Bewirtung ohne externe Personen", "staff-only wording not in the list")


def notes_of(lines):
    return [l.strip()[2:] for l in lines if l.startswith("  *")]


def main():
    bad = []
    for cid, lik, kind, ctype, docs, want, why in CASES:
        lines = compute_facts(ctype, docs)
        notes = notes_of(lines)
        hit = [n for n in notes if want in n] if want else notes
        if kind.startswith("FALSE"):
            ok = not hit
        else:
            ok = bool(hit)
        status = "ok " if ok else "BAD"
        print(f"{status} [{lik}] {kind:6} {cid}")
        if not ok:
            bad.append(cid)
            for n in notes or ["(no notes)"]:
                print(f"        note: {n}")
            err = [l for l in lines if "konnten nicht" in l or "nicht gefunden" in l]
            for e in err:
                print(f"        fact: {e.strip()}")
    print(f"\n{len(bad)} of {len(CASES)} misbehave")
    # parsing probes
    print("\nparse_amounts probes:")
    for s in ["Übernachtung 2 120,00 €", "Total CHF 1'234.50", "Betrag 69,02- €", "Summe EUR 1.234", "EUR 2,667.00 net", "£120.00", "12l,38 €"]:
        print(f"  {s!r:32} -> {[(str(a.value), a.currency) for a in parse_amounts(s)]}")
    print("parse_dates probes:")
    for s in ["03/20/2026", "March 9, 2026", "9. März 2026", "2026-03-09", "09.03.26", "9.3.2026", "Mo, 09.03."]:
        print(f"  {s!r:20} -> {[d.value.isoformat() for d in parse_dates(s)]}")


if __name__ == "__main__":
    main()
