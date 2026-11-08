"""R22d precision fixes (a review): look-alikes of the three
false notes on blind cases (F-ids, must stay silent) and controls (C-ids, must still fire)."""
from snippets import *  # noqa
import snippets

add = snippets.add
T, E = "business_trip", "expense_reimbursement"
BON = "PAPETERIE MUSTER\n Ordner 14,90\n Stifte 8,50\nSUMME EUR 34,75\nVermerk: für das Labor Elektrotechnik"
DINNER = "Restaurant Lindenhof\n Menü 6 Personen 243,90\nSUMME EUR 243,90\nAnlass: Projekttreffen\nGäste: Dr. Lind (Kranich GmbH), Prof. Q"

# ---- A1: the first claim row counts, a footnote "nicht beantragt" does not (blind4 d11)
add("F29 claim row, then a footnote naming the unclaimed tip", "M", "FALSE", E,
    {"bewirtungsrechnung.pdf": DINNER,
     "erstattungsformular.pdf": "Erstattungsformular\n Erstattungsbetrag   243,90 €\n Erstattungsbetrag ohne Trinkgeld (16,10 € nicht beantragt)."},
    "weicht", "")
add("C05 control: claim row above the bill total", "M", "MISS", E,
    {"bewirtungsrechnung.pdf": DINNER,
     "erstattungsformular.pdf": "Erstattungsformular\n Erstattungsbetrag   260,00 €\n (inkl. Trinkgeld 16,10 €)"},
    "weicht", "")

# ---- A2: an under-claim is no mismatch (blind3 c14)
add("F30 private items struck out, less claimed than the receipt", "M", "FALSE", E,
    {"kassenbon.pdf": BON, "erstattungsformular.pdf": "davon privat: 10,78 EUR\nErstattungsbetrag: 23,97 EUR"},
    "weicht", "")
add("C06 control: more claimed than the receipt", "M", "MISS", E,
    {"kassenbon.pdf": BON, "erstattungsformular.pdf": "Erstattungsbetrag: 44,75 EUR"},
    "weicht", "")

# ---- A3: the fee negation wraps to the next line (blind2 b01)
add("F31 'Ein Honorar wird nicht' / 'gezahlt' on two lines", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(),
     "email-einladung.pdf": "Vortragende erhalten einen Ausweis für alle Messetage. Ein Honorar wird nicht\ngezahlt; Reisekosten übernimmt der Veranstalter nicht."},
    "Honorar", "")
add("F32 'Ein Honorar ist nicht vorgesehen, Speaker erhalten freien Eintritt'", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(),
     "email-einladung.pdf": "Speaker erhalten freien Eintritt. Ein Honorar ist nicht vorgesehen."},
    "Honorar", "")
add("C07 control: fee paid, a later clause says travel is not paid", "M", "MISS", T,
    {"antrag-dienstreise.pdf": trip(),
     "email-einladung.pdf": "Vortragende erhalten ein Honorar von 400 €.\nReisekosten werden nicht gezahlt."},
    "Honorar", "")
