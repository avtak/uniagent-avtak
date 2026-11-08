"""Look-alike layouts of accepted cases from a review.
Each must stay silent on the named note; F-ids. Plus controls (C-ids) that must still fire."""
from snippets import *  # noqa
import snippets

add = snippets.add
T, E, P = "business_trip", "expense_reimbursement", "procurement"
ABROAD = dict(dest="Lyon, FRANKREICH")

# ---- trips: abroad box spellings
for fid, box in [("F01 'Reise ins Ausland: ja' (plain word)", "ja"),
                 ("F02 'X ja'", "X ja"),
                 ("F03 'ja ☒  nein ☐' (box after the word)", "ja ☒  nein ☐"),
                 ("F04 'Ja (Frankreich)'", "Ja (Frankreich)"),
                 ("F05 '■ ja □ nein'", "■ ja □ nein")]:
    add(fid, "M", "FALSE", T, {"antrag-dienstreise.pdf": trip(ausland=box, **ABROAD)}, "Reise ins Ausland", "")
add("C01 control: empty boxes for a foreign destination", "M", "MISS", T,
    {"antrag-dienstreise.pdf": trip(ausland="[ ] ja   [ ] nein", **ABROAD)}, "Reise ins Ausland", "")

# ---- trips: private nights paid privately
PRIV = dict(priv="11.03.2026 bis 19.03.2026 (6 Arbeitstage)")
BUSY = "Beginn Dienstgeschäft: 09.03.2026\nEnde Dienstgeschäft: 11.03.2026\n"
add("F06 private nights listed at 0,00 € (selbst getragen)", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(extra_row="Unterkunft privat, 6 Nächte (selbst getragen)                 6               0,00 €", **PRIV) + BUSY},
    "privater Aufenthalt", "")
add("F07 private nights named in the Kurzbegründung", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(**PRIV) + BUSY + "Kurzbegründung: die 6 Nächte im Anschluss trage ich selbst.\n"},
    "privater Aufenthalt", "")

# ---- trips: online words in a topic
for fid, anlass in [("F08 Anlass 'Online Learning for Robotics'", "Workshop 'Online Learning for Robotics', TU München"),
                    ("F09 Anlass 'Virtual Reality Summit'", "Virtual Reality Summit 2026, Wien"),
                    ("F10 Anlass 'Lehre im virtuellen Raum'", "Tagung 'Lehre im virtuellen Raum', Leipzig")]:
    add(fid, "M", "FALSE", T, {"antrag-dienstreise.pdf": trip(anlass=anlass)}, "Online-Veranstaltung", "")

# ---- trips: return trip booked as part of the outward line
add("F11 Rückreise '—' but the outward line books both ways", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(back="—") + "Hinreise: Bahn, Hin- und Rückfahrt gebucht, Ticket liegt bei\n"},
    "Rückreise", "")

# ---- trips: dinners that are not claimed
add("F12 registration lists a declined gala dinner", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(), "konferenz-registrierung.pdf": " Registration fee   1   180,00 €\n Gala Dinner ticket (declined)   1   70,00 €\n Total   180,00 €"},
    "Abendprogramm", "")
add("F13 hotel 'Dinner, Bed & Breakfast' rate", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(), "hotel-buchung.pdf": "Hotel Lindenhof\n Room, Dinner, Bed & Breakfast rate, 3 nights   225,00 €\n Total   225,00 €"},
    "Abendprogramm", "")

# ---- trips: project grant declared through the Finanzierung line
add("F14 DAAD project grant, Finanzierung names the project", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(fin="Projekt 57612345 (DAAD), Kostenstelle 5588-11"),
     "daad-bewilligung.pdf": "DAAD Bewilligungsbescheid\nDas Projekt 57612345 wird gefördert; Reisekosten werden bewilligt."},
    "Finanzierung durch Dritte", "")

# ---- refunds: copies and receipts of the same invoice
add("F15 invoice plus its signed copy ('sachlich richtig')", "H", "FALSE", E,
    {"rechnung.pdf": INV.format(no="RE 27-0612", total="121,38 €"),
     "rechnung-kopie-sachlich-richtig.pdf": INV.format(no="RE 27-0612", total="121,38 €") + "\nsachlich richtig, 12.03.2027"},
    "doppelte Abrechnung", "")
add("F16 invoice plus a cash receipt for that invoice", "M", "FALSE", E,
    {"rechnung.pdf": INV.format(no="RE 27-0612", total="121,38 €"),
     "quittung.pdf": "Quittung\n121,38 € dankend erhalten für Rechnung Nr. RE 27-0612"},
    "doppelte Abrechnung", "")
add("C02 control: the same invoice claimed twice", "M", "MISS", E,
    {"rechnung-1.pdf": INV.format(no="RE 27-0612", total="121,38 €"), "rechnung-2.pdf": INV.format(no="RE 27-0612", total="121,38 €"),
     "antrag.pdf": "zu erstatten: 242,76 €"},
    "doppelte Abrechnung", "")

# ---- refunds: addressee words
add("F17 'Bill to: Dr. X, Dept. of Physics'", "M", "FALSE", E,
    {"invoice.pdf": "Bill to\nDr. Y. Brammertz\nDept. of Physics, Wernstadt\nInvoice no. FP-27-004\n Book 1 €89.90\nInvoice total €89.90"},
    "nicht an die Universität", "")
add("F18 invoice to 'FB 16, Wilhelmshöher Allee 71-73'", "M", "FALSE", E,
    {"rechnung.pdf": "FB 16, z. Hd. Dr. Brammertz\nWilhelmshöher Allee 71-73\nRechnung Nr. 2027-118\n Kabel 1 49,90 €\n Rechnungsbetrag 49,90 €"},
    "nicht an die Universität", "")
add("F19 English refund form without a university word", "M", "FALSE", E,
    {"reimbursement-request.pdf": "Reimbursement request\nApplicant: Dr. Y. Brammertz\nPurpose: textbook for the lab course\nzu erstatten: 49,90 €",
     "rechnung.pdf": INV.format(no="RE 27-0612", total="49,90 €")},
    "nicht an die Universität", "")

# ---- refunds: guest lists and payment proof
add("F20 restaurant bill plus 'Attendees:' list", "M", "FALSE", E,
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\n Menü 4 Personen 142,00 €\nRechnungsbetrag 142,00 €\nAnlass: Projekttreffen\nAttendees: Dr. Lind (Kranich GmbH), Prof. Q (Uni)"},
    "ohne Anlass und Liste", "")
add("F21 restaurant bill plus 'Teilnehmende:' list", "M", "FALSE", E,
    {"bewirtungsbeleg.pdf": "Restaurant Lindenhof\n Menü 4 Personen 142,00 €\nRechnungsbetrag 142,00 €\nAnlass: Projekttreffen\nTeilnehmende: Dr. Lind (Kranich GmbH), Prof. Q"},
    "ohne Anlass und Liste", "")
add("F22 USD fee plus 'mastercard-umsatz.pdf'", "M", "FALSE", E,
    {"receipt-workshop.pdf": "Dr. O. W., c/o Universität Wernstadt\nReceipt\nOnline participation  USD 175.00\nTotal paid  USD 175.00",
     "mastercard-umsatz.pdf": "Umsatz 02.03.2027  Workshop Inc.  USD 175.00  -160,37 EUR"},
    "Fremdwährung ohne Zahlungsnachweis", "")
add("F23 catering for an institute meeting with advisory-board members of a firm", "M", "FALSE", E,
    {"beleg-catering.pdf": "Bäckerei Rosengarten\nKaffee, Kuchen 8 Pers. 32,40 €\nSUMME EUR 32,40\nVermerk: Institutssitzung mit Beiratsmitgliedern der Firma Kranich"},
    "Bewirtung ohne externe Personen", "")

# ---- procurement: framework route named without the word 'Rahmenvertragspartner'
add("F24 'Bestellung über den Rahmenvertrag Büromaterial (Büro Schmidt GmbH)'", "M", "FALSE", P,
    {"email-beschaffungsantrag.pdf": "Bitte bestellen:\n 1. 4 × Tonerkartusche schwarz, je 59,00 € brutto = 236,00 €\nGesamtsumme: 236,00 € brutto.\nBestellung über den Rahmenvertrag Büromaterial (Büro Schmidt GmbH)."},
    "Rahmenvertrag", "")
add("F25 'Bestellung aus dem Rahmenvertrag des Landes Hessen (Bechtle GmbH)'", "M", "FALSE", P,
    {"email-beschaffungsantrag.pdf": "Bitte bestellen:\n 1. 2 × Notebook 14 Zoll, je 799,00 € brutto = 1.598,00 €\nGesamtsumme: 1.598,00 € brutto.\nBestellung aus dem Rahmenvertrag des Landes Hessen (Bechtle GmbH)."},
    "Rahmenvertrag", "")

# ---- R21: helium has a framework contract only from 01.05. to 31.07.2026
add("F26 helium ordered in October 2026 (outside the contract window)", "M", "FALSE", P,
    {"email-beschaffungsantrag.pdf": "Bestelldatum: 14.10.2026\nBitte bestellen bei Gase-Express:\n 1. 1 × Helium 5.0, Flasche 50 l, 480,00 € netto\nGesamtsumme: 480,00 € netto."},
    "Rahmenvertrag", "")

# ---- R21: working lunch and speaker fee
LUNCH = "Restaurant Lindenhof\n Menü 6 Personen 186,00 €\nRechnungsbetrag 186,00 €\nAnlass: Projekttreffen\nTeilnehmerliste:\n"
add("C03 control: restaurant, 4 staff and 1 guest (Arbeitsessen)", "M", "MISS", E,
    {"bewirtungsbeleg.pdf": LUNCH + " 1 Dr. A (Universitätsbedienstete)\n 2 B (Universitätsbedienstete)\n 3 C (Universitätsbedienstete)\n 4 D (Universitätsbedienstete)\n 5 Prof. E, Firma X (Gast, extern)\n"},
    "Arbeitsessen", "")
add("F27 restaurant, 2 staff and 2 guests (balanced)", "M", "FALSE", E,
    {"bewirtungsbeleg.pdf": LUNCH + " 1 Dr. A (Universitätsbedienstete)\n 2 B (Universitätsbedienstete)\n 3 Prof. E, Firma X (Gast, extern)\n 4 Dr. F, Firma Y (Gast, extern)\n"},
    "Arbeitsessen", "")
add("C04 control: invitation pays a speaker honorarium of 750 €", "M", "MISS", T,
    {"antrag-dienstreise.pdf": trip(), "email-einladung.pdf": "Dear colleague, we are pleased to invite you as keynote speaker.\nAn honorarium of EUR 750 will be paid after the talk."},
    "Honorar", "")
add("F28 Honorarprofessor travelling, no fee", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip() + "Antragsteller: Prof. Dr. X (Honorarprofessor)\n", "email-einladung.pdf": "Der Vortrag erfolgt ohne Honorar; Reisekosten trägt die Universität."},
    "Honorar", "")
