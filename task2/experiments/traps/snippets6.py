"""R22e robustness patches (fresh a reviewer review): neutral file
names and Unicode the generators never produce. F-ids must stay silent, C-ids must fire."""
import unicodedata

from snippets import *  # noqa
import snippets

add = snippets.add
E = "expense_reimbursement"
TILL = ("BAUHAUS GmbH\nFiliale Nord\nHauptstr. 12\n34117 Wernstadt\nTel. 0561 123456\nwww.example.de\n\n\n"
        "BON 4711   KASSE 2\n Schrauben 4x40   6,90\n Dübel 8mm   3,49\nSUMME EUR   10,39\nBAR   20,00\n"
        "für Versuchsstand Labor 3")
PRIVATE_INV = ("Max Mustermann\nAm Weinberg 3\n34119 Wernstadt\n\nRechnung Nr. RE-2027-0412\nRechnungsdatum 03.03.2027\n"
               " Fachbuch Regelungstechnik 1   49,90 €\nRechnungsbetrag 49,90 €")

# ---- neutral file names: a till receipt whose 'BON' is below the head
add("F33 till receipt saved as scan_0001.pdf (BON below the first 8 lines)", "H", "FALSE", E,
    {"scan_0001.pdf": TILL, "scan_0002.pdf": "Erstattungsantrag\nzu erstatten: 10,39 €"},
    "nicht an die Universität", "")
add("C08 control: invoice to a private person under a neutral name", "M", "MISS", E,
    {"scan_0001.pdf": PRIVATE_INV, "scan_0002.pdf": "Erstattungsantrag\nzu erstatten: 49,90 €"},
    "nicht an die Universität", "")

# ---- Unicode: decomposed umlauts, non-breaking spaces, ligatures, soft hyphens keep true notes
NFD = unicodedata.normalize("NFD", "Rechnungsbetrag 49,90 €\nzu erstatten: 99,80 €\nGebühr für Prüfung")
add("C09 control: over-claim in NFD text with NBSP and a ligature still fires", "M", "MISS", E,
    {"rechnung.pdf": "Universität Wernstadt, Fachgebiet Regelungstechnik\nRechnung Nr. RE-77\n Proﬁl­schiene 1   49,90 €\n" + NFD},
    "weicht", "")
