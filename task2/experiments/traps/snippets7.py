"""R22f: negations and tick glyphs from the first clean out-of-distribution set
(experiments/clean-ood). F-ids must stay silent, C-ids must fire."""
from snippets import *  # noqa
import snippets

add = snippets.add
T = "business_trip"
INV = lambda body: {"antrag-dienstreise.pdf": trip(), "email-einladung.pdf": body}

for fid, body in [("F34 'We are not able to offer an honorarium'", "The registration fee is EUR 420.00. We are not able to offer an honorarium or to cover travel costs."),
                  ("F35 'Ein Honorar kann nicht gezahlt werden'", "Ihr Beitrag wurde angenommen.\nEin Honorar kann nicht gezahlt werden."),
                  ("F36 'weder Sitzungsgelder noch Honorare gezahlt'", "Die Mitarbeit ist ehrenamtlich; es werden weder Sitzungsgelder noch Honorare gezahlt, Reisekosten trägt die Einrichtung."),
                  ("F37 'We do not pay an honorarium' after a fee amount", "The registration fee for academic participants is EUR 280.00. We do not pay an honorarium."),
                  ("F38 negation on the line before: 'Es werden keine ⏎ Honorare gezahlt'", "Es werden keine\nHonorare gezahlt.")]:
    add(fid, "M", "FALSE", T, INV(body), "Honorar", "")
add("C10 control: fee with an amount, travel costs not paid in the same sentence", "M", "MISS", T,
    INV("Neben dem Honorar von 300 € werden keine Reisekosten erstattet."), "Honorar", "")
add("C11 control: fee paid, a later clause excludes travel", "M", "MISS", T,
    INV("Das Honorar beträgt 500 € und wird nach dem Vortrag gezahlt, Reisekosten werden nicht übernommen."), "Honorar", "")

# ---- evening programme excluded in the cost row
add("F39 cost row 'Registrierung, ohne Galadinner'", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(extra_row="Konferenzgebühr · Registrierung, ohne Galadinner          1          250,00 €")},
    "Abendprogramm", "")
add("C12 control: 'Galadinner (ohne Getränke)' claimed", "M", "MISS", T,
    {"antrag-dienstreise.pdf": trip(extra_row="Galadinner (ohne Getränke)                                1           85,00 €")},
    "Abendprogramm", "")

# ---- tick glyphs
add("F40 abroad box '[×] ja'", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(ausland="[×] ja   [ ] nein", dest="Eindhoven, NIEDERLANDE")}, "Reise ins Ausland", "")
add("F41 abroad box '[✘] ja'", "M", "FALSE", T,
    {"antrag-dienstreise.pdf": trip(ausland="[✘] ja   [ ] nein", dest="Eindhoven, NIEDERLANDE")}, "Reise ins Ausland", "")
