#!/usr/bin/env python3
"""Build the second test set for UniAgent Task 2: EDGE CASES.

An edge case is a copy of a practice case with ONE fact changed (or the minimum needed to
reach one rule situation the 21 practice cases and the 13 variants never test), so that a
rule from the university's own pages decides it. They are TESTS ONLY: never used to tune
prompts, rule cards or code.

    python3 experiments/edge-cases/tools/make_edge_cases.py            # build everything
    python3 experiments/edge-cases/tools/make_edge_cases.py --check    # build + verify, exit 1 on problems
    python3 experiments/edge-cases/tools/make_edge_cases.py --table    # print the markdown table

Output (mirrors the dataset layout, so tools/eval.py runs it with UNIAGENT_DATASETS):
    experiments/edge-cases/<set>/{inputs/<base>-e<N>/*.pdf, ground-truth.jsonl}          confidence high
    experiments/edge-cases-unsure/<set>/{inputs/..., ground-truth.jsonl}                 confidence low (not scored)

Needs only python3 (standard library) and pdftotext/pdfinfo (poppler). Reuses the text editor
and the pure-Python PDF writer of experiments/variants/tools/make_variants.py. Unchanged PDFs
are byte-copied from $UNIAGENT_DATASETS (default ~/dev/uniagent-code/cikm26/datasets, read only);
changed PDFs are rebuilt from their `pdftotext -layout` text and verified to round-trip.

Ops on one document (applied in order to its `pdftotext -layout` text), on top of those of
make_variants (sub, drop, drop_range, merge_pages):
    ("setline", regex, new)         replace the whole line matching regex (exactly one) by `new`
                                    (may hold \\n for several lines)
    ("insert_after", regex, new)    insert `new` (may hold \\n) after the line matching regex
    ("rep", literal, new)           replace a literal in exactly one line (column alignment kept)
A document can also be written from scratch: new_docs={name: (text, size_from)}.
"""
import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "variants" / "tools"))
import make_variants as mv  # noqa: E402

OUT_HIGH = HERE.parent                                 # experiments/edge-cases
OUT_LOW = HERE.parents[1] / "edge-cases-unsure"        # experiments/edge-cases-unsure
DATASETS = mv.DATASETS
TRIP, PROC, EXP = mv.TRIP, mv.PROC, mv.EXP
SETS = [TRIP, PROC, EXP]
SHORT = {TRIP: "trip", PROC: "proc", EXP: "exp"}

CASES = []


def case(set_, base, n, result, confidence, changed, rule, quote, source, tests, risk, reason,
         edits=None, drop_docs=(), new_docs=None):
    CASES.append(dict(set=set_, base=base, n=n, id=f"{base}-e{n}", result=result, confidence=confidence,
                      changed=changed, rule=rule, quote=quote, source=source, tests=tests, risk=risk,
                      reason=reason, edits=edits or {}, drop_docs=list(drop_docs), new_docs=new_docs or {}))


# --------------------------------------------------------------------------- #
# Editing helpers
# --------------------------------------------------------------------------- #
def apply_ops(text, ops, label):
    for op in ops:
        kind = op[0]
        if kind in ("setline", "insert_after", "rep", "rep_all"):
            lines = text.split("\n")
            if kind == "rep_all":
                _, lit, new = op
                idx = [i for i, l in enumerate(lines) if lit in l]
                if not idx:
                    raise SystemExit(f"{label}: rep_all {lit!r} matched no line")
                for i in idx:
                    pos = 0
                    while True:
                        a = lines[i].find(lit, pos)
                        if a < 0:
                            break
                        lines[i] = mv._realign(lines[i], a, a + len(lit), new)
                        pos = a + len(new)
            elif kind == "rep":
                _, lit, new = op
                idx = [i for i, l in enumerate(lines) if lit in l]
                if len(idx) != 1:
                    raise SystemExit(f"{label}: rep {lit!r} matched {len(idx)} lines, need exactly 1")
                i = idx[0]
                l = lines[i]
                while lit in l:  # every occurrence in that line
                    a = l.index(lit)
                    l = mv._realign(l, a, a + len(lit), new)
                    if new and lit in new:
                        break
                lines[i] = l
            else:
                _, pattern, new = op
                rx = re.compile(pattern)
                idx = [i for i, l in enumerate(lines) if rx.search(l)]
                if len(idx) != 1:
                    raise SystemExit(f"{label}: {kind} {pattern!r} matched {len(idx)} lines, need exactly 1")
                i = idx[0]
                if kind == "setline":
                    if new is None:
                        del lines[i]
                    else:
                        lines[i] = new
                else:
                    lines.insert(i + 1, new)
            text = "\n".join(lines)
        else:
            text = mv.apply_ops(text, [op], label)
    return text


def row_like(template, *texts, aligns=None):
    """New table line shaped like `template`. Its columns are runs of text separated by 2+ spaces.
    aligns = string of 'l'/'r' per column (default: a column ending in a digit or euro sign is
    right-aligned to the template's right edge, any other is left-aligned at the template's start)."""
    toks = list(re.finditer(r"\S+(?: \S+)*", template))
    if len(toks) != len(texts):
        raise SystemExit(f"row_like: template has {len(toks)} columns, got {len(texts)}: {template!r}")
    if aligns is None:
        aligns = "".join("r" if re.search(r"[\d€]$", m.group(0)) else "l" for m in toks)
    out = ""
    for m, t, al in zip(toks, texts, aligns):
        if al == "r":
            out = out.ljust(max(len(out), m.end() - len(t)))
            if out and not out.endswith(" "):
                out += " "
            out += t
        else:
            out = out.ljust(m.start())
            if out and not out.endswith(" "):
                out += " "
            out += t
    return out


def eur(x):
    """German money format with euro sign: 1234.5 -> '1.234,50 €'."""
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


# --------------------------------------------------------------------------- #
# BUSINESS TRIPS
# --------------------------------------------------------------------------- #
ANTRAG = "antrag-dienstreisegenehmigung.pdf"
BAHN = "bahn-buchungsbestaetigung.pdf"
MAILC = "email-annahmebestaetigung-konferenz.pdf"
REG = "konferenz-registrierungsbestaetigung.pdf"

_ROW = " Konferenzregistrierung (Early Bird, Mitglied)                                                      1              450,00 €"


def trip_row(label, qty, amount):
    return row_like(_ROW, label, str(qty), amount)


def field(label, value):
    """A label/value line of the Antrag header block ('Reiseziel:   Hamburg')."""
    return label.ljust(43) + value


# ---- e1: conference dinner claimed (abroad trip 02) ------------------------ #
case(
    TRIP, "dienstreiseantrag-02", 1, "abgelehnt", "high",
    "Conference Dinner not booked and not claimed → booked and claimed in the Antrag (new cost row 'Conference Dinner (optional)' 65,00 €, estimate 915,00 € → 980,00 €)",
    "Costs of evening and accompanying programmes (e.g. conference dinner) are not reimbursable",
    "„Kosten für Begleit- und Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht erstattungsfähig.“",
    "decision-trail dienstreiseantrag-02/genehmigt.pdf (the organisers' approval notice for the practice trip); README of business-trip-spot-check lists 'non-reimbursement of evening programs'; page `finanzbuchhaltung-und-steuern.md`: „Rahmenprogramme“ not erstattungsfähig",
    "rules.py business_trip item 8 / policy `evening_programmes`; hidden-test-exposure #7",
    "The quote is from the organisers' approval mail, not from a corpus page; staff might cut the item instead of rejecting the whole request (exposure #7: UNVERIFIED), but the README names the rule as a check pattern",
    "Der Antrag macht das Conference Dinner (65,00 EUR) als Kostenposition geltend (Schaetzung 980,00 EUR statt 915,00 EUR), die Registrierungsbestaetigung sagt, dass es gebucht wurde. Kosten fuer Begleit- und Abendprogramme wie das Conference Dinner sind grundsaetzlich nicht erstattungsfaehig, der Antrag ist so nicht genehmigungsfaehig. Geaendert gegenueber dienstreiseantrag-02: das Dinner ist beantragt (vorher nicht gebucht und nicht beantragt).",
    {ANTRAG: [
        ("insert_after", r"^ Konferenzregistrierung \(Early Bird", "\n" + trip_row("Conference Dinner (optional), 11.11.2026", 1, "65,00 €")),
        ("sub", r"Summe \(Schätzung\)[ ]+(?P<x>915,00 €)", "980,00 €"),
    ], REG: [
        ("setline", r"^Conference Dinner \(65,00 EUR\) wurde nicht gebucht", "Conference Dinner (65,00 EUR) wurde zusätzlich gebucht und wird dem Antrag beigefügt."),
    ]},
)


# ---- e2..e4: domestic version of trip 02 (Hamburg) ------------------------- #
def domestic_edits(rate, kurz):
    """Trip 02 moved from Rotterdam to Hamburg (domestic): the minimum needed to test the 80 EUR
    hotel cap. kurz = lines that replace the last two lines of the Kurzbegründung."""
    total = 450 + 180 + 3 * rate
    return {
        ANTRAG: [
            ("setline", r"^Reiseziel:", field("Reiseziel:", "Hamburg")),
            ("sub", r"Reise ins Ausland:[ ]+(?P<x>\[X\] ja   \[ \] nein)", "[ ] ja   [X] nein"),
            ("drop", r"^A1-Bescheinigung:"),
            ("setline", r"^ Bahn Kassel–Rotterdam", trip_row("Bahn Kassel–Hamburg, Hin- und Rückfahrt", 1, "180,00 €")),
            ("setline", r"^ Unterkunft, 3 Nächte", trip_row(f"Unterkunft, 3 Nächte à {rate:.2f} €".replace(".", ","), 3, eur(3 * rate))),
            ("drop", r"^ Verpflegungsmehraufwand \(Pauschale NL\)"),
            ("sub", r"Summe \(Schätzung\)[ ]+(?P<x>915,00 €)", eur(total)),
            ("setline", r"^Kooperationspartnern\. Die Übernachtung", kurz[0]),
            ("setline", r"^Höchstgrenze des Auslandsübernachtungsgeldes", kurz[1]),
        ],
        MAILC: [("rep", "Rotterdam, the Netherlands", "Hamburg, Germany"),
                ("rep", "seeing you in Rotterdam", "seeing you in Hamburg")],
        REG: [
            ("rep", "c/o Symposia Events B.V.", "c/o Symposia Events GmbH"),
            ("rep", "Weena 505", "Speicherstraße 18"),
            ("rep", "3013 AL Rotterdam", "20457 Hamburg"),
            ("rep", "Niederlande", "Deutschland"),
            ("rep", "VAT NL812449770B01", "USt-IdNr. DE301552640"),
            ("rep", "10–11 November 2026, Rotterdam", "10–11 November 2026, Hamburg"),
            ("rep", "0%                450,00 € ", "19 %                378,15 € "),
            ("setline", r"^[ ]+\(reverse$", None),
            ("setline", r"^[ ]+charge\)$", None),
            ("sub", r"Summe \(netto\)[ ]+(?P<x>450,00 €)", "378,15 €"),
            ("setline", r"MwSt \(Reverse Charge", "                                                                                                MwSt 19 %                     71,85 €"),
            ("setline", r"^Rechnungsempfänger ist die Universität Kassel\. Leistungsempfänger", "Rechnungsempfänger ist die Universität Kassel."),
            ("setline", r"^USt-IdNr\. wurde geprüft\.$", None),
        ],
    }


# The Bahn doc has two identical '(Duisburg Hbf)' lines; replace both with a pair of explicit edits.
def bahn_domestic_ops():
    return [
        ("rep", "Kassel-Wilhelmshöhe → Rotterdam Centraal,", "Kassel-Wilhelmshöhe → Hamburg Hbf,"),
        ("rep", "Rotterdam Centraal → Kassel-Wilhelmshöhe,", "Hamburg Hbf → Kassel-Wilhelmshöhe,"),
        ("rep_all", "(Duisburg Hbf)", "(Hannover Hbf)"),
        ("drop", r"^Der Preisvergleich gegenüber einer Flugverbindung"),
        ("drop", r"^wirtschaftlicher\.$"),
    ]


def domestic(rate, kurz):
    ed = domestic_edits(rate, kurz)
    ed[BAHN] = bahn_domestic_ops()
    return ed


KURZ_80 = ("Kooperationspartnern. Die Übernachtung erfolgt im Konferenzhotel zum Konferenztarif von 80,00 € je Nacht;",
           "der Satz entspricht der Höchstgrenze für Übernachtungen im Inland.")
KURZ_95 = ("Kooperationspartnern. Die Übernachtung erfolgt im Konferenzhotel zum Konferenztarif von 95,00 € je Nacht.",
           "Die Reise führt nach Hamburg, die Bahnfahrt erfolgt in der 2. Klasse.")
KURZ_95_JUST = ("Kooperationspartnern. Die Übernachtung erfolgt im Konferenzhotel zum Konferenztarif von 95,00 € je Nacht.",
                "Begründung der Überschreitung von 80,00 € je Nacht: Die Überschreitung war unvermeidbar. Zur Tagungswoche ist die Stadt wegen\n"
                "einer Parallelmesse ausgebucht; Anfragen bei drei Hotels in zumutbarer Entfernung zum Tagungsort am 28.08.2026 ergaben\n"
                "Preise von 112,00 € bis 138,00 € je Nacht, das Konferenzhotel war mit 95,00 € das günstigste verfügbare Zimmer.")

case(
    TRIP, "dienstreiseantrag-02", 2, "angenommen", "high",
    "Destination Rotterdam (NL, abroad, 75,00 €/night, A1) → Hamburg (domestic); hotel 3 nights at exactly 80,00 € (the cap); Verpflegung row and A1 line dropped; Bahn, registration (19 % USt) and mail adapted to Hamburg",
    "Domestic hotel at exactly the cap of 80 EUR per night is reimbursable",
    "„Nachgewiesene Übernachtungskosten sind bis zu einer Höhe von 80,00 € je Nacht erstattungsfähig.“",
    "`dienstreisemanagement.md`",
    "rules.py business_trip item 4 / policy `hotel_costs` (boundary: 'bis zu' includes 80,00); hidden-test-exposure #4",
    "Boundary case: a model that reads 'bis 80' as 'unter 80' rejects. The base trip is moved to Germany first (needed for the domestic cap), so this case also shows that the relocated base is clean; the same relocation is in e3 and e4",
    "Inlandsreise nach Hamburg, Uebernachtung im Konferenzhotel zu 80,00 EUR je Nacht (3 Naechte, 240,00 EUR). Nachgewiesene Uebernachtungskosten sind bis zu 80,00 EUR je Nacht erstattungsfaehig, der Satz liegt genau auf der Grenze. Antrag rechtzeitig (02.09. fuer 09.11.), Programm/Annahmebestaetigung und Bahnbuchung liegen bei, Finanzierung aus Drittmittelprojekt der Universitaet. Geaendert gegenueber dienstreiseantrag-02: Reiseziel Hamburg statt Rotterdam, Hotelsatz 80,00 EUR statt 75,00 EUR.",
    domestic(80, KURZ_80),
)
case(
    TRIP, "dienstreiseantrag-02", 3, "abgelehnt", "high",
    "Domestic relocation as in e2; hotel rate 80,00 → 95,00 €/night (3 nights, 285,00 €, estimate 915,00 €), Kurzbegründung gives NO reason for the higher rate",
    "Domestic hotel above 80 EUR per night without a written justification of necessity: only 80 EUR per night are reimbursable",
    "„Erfolgt keine Erklärung der Notwendigkeit, sind höchstens 80,00 € je Nacht erstattungsfähig!“ and „Darüber hinaus gehende Übernachtungskosten werden nur erstattet, wenn sie unvermeidbar waren. D. h. die Notwendigkeit ist im Einzelfall nachvollziehbar schriftlich bei Antragsstellung zu begründen.“",
    "`dienstreisemanagement.md` (Inland section); `hrkg.md` § 8: „Höhere Übernachtungskosten werden erstattet, wenn sie unvermeidbar sind.“",
    "rules.py business_trip item 4 / policy `hotel_costs`; hidden-test-exposure #4 (over-accept: the model may not know the cap)",
    "Staff may cut the hotel to 80 EUR and approve the rest instead of rejecting; the task has only two labels and the request as filed exceeds the cap without a reason, so abgelehnt follows the page",
    "Die Uebernachtung im Inland kostet 95,00 EUR je Nacht (3 Naechte, 285,00 EUR) und liegt ueber der Grenze von 80,00 EUR je Nacht. Eine schriftliche Begruendung der Unvermeidbarkeit fehlt im Antrag; ohne Erklaerung der Notwendigkeit sind hoechstens 80,00 EUR je Nacht erstattungsfaehig. Geaendert gegenueber dienstreiseantrag-02: Inlandsreise Hamburg, Hotelsatz 95,00 EUR ohne Begruendung.",
    domestic(95, KURZ_95),
)
case(
    TRIP, "dienstreiseantrag-02", 4, "angenommen", "high",
    "Domestic relocation as in e2; hotel rate 95,00 €/night (above 80,00 €) WITH a written justification in the Antrag (fully booked city, three hotels asked, 95,00 € the cheapest available)",
    "Domestic hotel above 80 EUR per night is reimbursable when the necessity is justified in writing at the time of application",
    "„Darüber hinaus gehende Übernachtungskosten werden nur erstattet, wenn sie unvermeidbar waren. D. h. die Notwendigkeit ist im Einzelfall nachvollziehbar schriftlich bei Antragsstellung zu begründen.“",
    "`dienstreisemanagement.md` (Inland section); `hrkg.md` § 8",
    "rules.py business_trip item 4 / policy `hotel_costs` ('mehr nur mit schriftlicher Begründung im Antrag'); decision 12 spirit: a stated exception is allowed; hidden-test-exposure #4",
    "Medium: whether staff accept this particular justification as 'unvermeidbar' is a judgement; the page makes a written reason at application the condition, and the reason here is concrete (alternatives asked, prices named). The documents do not attach the hotel enquiries",
    "Die Uebernachtung kostet 95,00 EUR je Nacht und liegt ueber 80,00 EUR. Der Antrag begruendet die Ueberschreitung schriftlich und nachvollziehbar (Stadt wegen Parallelmesse ausgebucht, drei Hotels angefragt, 95,00 EUR das guenstigste verfuegbare Zimmer), damit ist die Unvermeidbarkeit dargelegt und die hoeheren Kosten sind erstattungsfaehig. Geaendert gegenueber dienstreiseantrag-02: Inlandsreise Hamburg, Hotelsatz 95,00 EUR mit schriftlicher Begruendung.",
    domestic(95, KURZ_95_JUST),
)


# ---- 05 family (Boston) ----------------------------------------------------- #
_ROW05 = " Flug Frankfurt–Boston, Hin- und Rückflug, Economy                                                1               780,00 €"
FLUG = "flug-angebot.pdf"
REG5 = "konferenz-registrierung.pdf"
STIP = "email-stipendienzusage.pdf"

case(
    TRIP, "dienstreiseantrag-05", 1, "abgelehnt", "high",
    "Destination Boston, USA → Tel Aviv, ISRAEL (conference renamed ISMAT 2026, flight FRA–TLV, registration office in Tel Aviv); the scholarship email is left out (as in variant 05-v1) so that the destination is the only defect",
    "Business trips to Israel are not approved",
    "„Dienstreisen in die Russische Föderation, in die Ukraine, nach Belarus, Moldau- die Gebiete im Süden und Osten, die an die Ukraine grenzen, Niger, Iran, Israel, in die Palästinensischen Gebiete und Libanon bis auf Weiteres nicht genehmigt werden.“",
    "`dienstreisemanagement.md`",
    "rules.py business_trip: no rule for destinations that are not approved (only in the page); hidden-test-exposure #15 (over-accept)",
    "Currency of the list in 2026/27 is UNVERIFIED, but the page is the only source we have and it names Israel plainly. Two changes at once (destination, scholarship email dropped); the second only removes the other defect",
    "Reiseziel ist Tel Aviv, Israel. Nach der Seite Dienstreisemanagement der Universitaet Kassel werden Dienstreisen nach Israel bis auf Weiteres nicht genehmigt. Der Antrag kann deshalb nicht genehmigt werden, auch wenn Kosten, Termin und Unterlagen sonst stimmen. Geaendert gegenueber dienstreiseantrag-05: Reiseziel Tel Aviv statt Boston; die Stipendienzusage fehlt, es gibt keine Doppelfinanzierung.",
    {ANTRAG: [
        ("setline", r"^Reiseziel:", field("Reiseziel:", "Tel Aviv, ISRAEL")),
        ("setline", r"^Anlass:", field("Anlass:", "ISMAT 2026 – International Symposium on Advanced Materials")),
        ("setline", r"^ Flug Frankfurt–Boston", row_like(_ROW05, "Flug Frankfurt–Tel Aviv, Hin- und Rückflug, Economy", "1", "780,00 €")),
        ("sub", r"Poster.*?auf dem (?P<x>MRS Fall Meeting),", "ISMAT 2026"),
    ], FLUG: [
        ("sub", r"Frankfurt \(FRA\) – (?P<x>Boston \(BOS\))", "Tel Aviv (TLV)"),
        ("rep", "Hinflug FRA → BOS", "Hinflug FRA → TLV"),
        ("rep", "Rückflug BOS → FRA", "Rückflug TLV → FRA"),
    ], REG5: [
        ("sub", r"^Finn Osterkamp[ ]+(?P<x>MRS Fall Meeting 2026 Registration Office)", "ISMAT 2026 Registration Office"),
        ("setline", r"^MRS Fall Meeting 2026 Registration Office$", "ISMAT 2026 Registration Office"),
        ("rep", "c/o Meeting Services Inc.", "c/o Congress Services Ltd."),
        ("rep", "506 Keystone Drive", "14 Ben Yehuda Street"),
        ("rep", "Warrendale, PA 15086", "Tel Aviv 6380104"),
        ("setline", r"^34121 Kassel, Germany[ ]+USA$", "34121 Kassel, Germany                                                                                                            Israel"),
        ("rep", "MRS Fall Meeting 2026, Boston MA, 29 November", "ISMAT 2026, Tel Aviv, 29 November"),
    ]},
    drop_docs=[STIP],
)

DRITT_MAIL = """E-Mail – finn.osterkamp@uni-kassel.de                                              https://outlook.office.example/mail/id/AAQkAJ




 Drittmittelprojekt NanoGrain – Reisemittel MRS Fall Meeting 2026 bestätigt
 Drittmittelverwaltung, Abteilung Finanzen, Universität Kassel <drittmittel@uni-kassel.example>
 Di 30.06.2026 14:12
 An: Finn Osterkamp <finn.osterkamp@uni-kassel.de>


 Sehr geehrter Herr Osterkamp,

 für Ihre Teilnahme am MRS Fall Meeting 2026 in Boston stehen im Drittmittelprojekt NanoGrain (Kostenstelle 4720-06)
 Reisemittel in Höhe von bis zu 1.910 EUR bereit. Die Mittel gehören zur Projektbewilligung des Drittmittelgebers und
 werden von der Universität Kassel verwaltet.

 Die Mittel sind für Flug, Unterkunft, Konferenzregistrierung und Transfer vorgesehen. Die Abrechnung erfolgt nach der
 Reise ausschließlich über die Reisekostenstelle der Universität Kassel; es erfolgt keine Zahlung an Sie von dritter Seite.

 Wichtiger Hinweis: Eine Doppelfinanzierung derselben Kostenpositionen ist auszuschließen. Bitte rechnen Sie die Reise
 nur einmal über die Reisekostenstelle ab.

 Wir wünschen Ihnen einen erfolgreichen Kongressbeitrag.

 Mit freundlichen Grüßen
 Drittmittelverwaltung, Abteilung Finanzen




1 von 1                                                                                                         16.06.26, 15:42
"""

case(
    TRIP, "dienstreiseantrag-05", 2, "angenommen", "high",
    "Funding of the same trip: external scholarship (DGMK, paid to the traveller) → project money of a Drittmittelprojekt managed by the University of Kassel; the Antrag now names the project in 'Finanzierung'; the confirmation mail has the same shape (and the same 'Doppelfinanzierung' warning) but comes from the university's Drittmittelverwaltung",
    "University-managed Drittmittel are not a benefit from a third party, so nothing is paid twice",
    "„Als Leistungen von dritter Seite gelten nicht Drittmittel, die von der Universität Kassel verwaltet werden.“",
    "`dienstreisemanagement.md`; `hrkg.md`: „Leistungen, die Dienstreisende ihres Amtes wegen von dritter Seite für dieselbe Dienstreise erhalten, sind anzurechnen.“",
    "rules.py business_trip item 7 / policy `third_party` ('Drittmittel ... KEINE Leistungen Dritter'); hidden-test-exposure #1 (R1 error D)",
    "The mail repeats the 'Doppelfinanzierung' warning on purpose (it is the trap); a model that matches that word rejects. The Antrag and the mail are consistent, so nothing else is wrong",
    "Die Reisemittel stammen aus dem Drittmittelprojekt NanoGrain, das von der Universitaet Kassel verwaltet wird; der Antrag nennt es im Feld Finanzierung. Als Leistungen von dritter Seite gelten nicht Drittmittel, die die Universitaet Kassel verwaltet, es wird also nichts doppelt erstattet. Flug, Registrierung, Unterkunft und Transfer sind durch Angebot und Rechnung belegt, der Antrag ist rechtzeitig. Geaendert gegenueber dienstreiseantrag-05: Finanzierung aus uni-verwaltetem Drittmittelprojekt statt Stipendium eines externen Gebers.",
    {ANTRAG: [
        ("setline", r"^Finanzierung:", "Finanzierung:                              Drittmittelprojekt „NanoGrain“ (von der Universität Kassel verwaltet), Kostenstelle 4720-06\n                                           (volle Summe)"),
        ("setline", r"^                                           Summe\)$", None),
        ("sub", r"Reisekosten durch das (?P<x>Fachgebiet)\.", "Drittmittelprojekt"),
    ]},
    drop_docs=[STIP],
    new_docs={"email-drittmittelzusage.pdf": (DRITT_MAIL, STIP)},
)


# ---- online conference filed as a business trip (unsure) -------------------- #
case(
    TRIP, "dienstreiseantrag-02", 5, "abgelehnt", "low",
    "NordSys 2026 held online instead of on site: Antrag filed as a business trip to 'Online (virtuelle Konferenz)'; only the registration fee (450,00 €) is left in the cost table; the train booking is dropped",
    "Online conferences are not business trips; no Dienstreiseantrag is to be filed, the fee is claimed as a privately advanced cost",
    "„Konferenzen und Tagungen die online durchgeführt werden, sind keine Dienstreisen im Sinne des Reisekostengesetzes. Daher ist in diesem Fall weder ein Dienstreiseantrag noch eine Reisekostenabrechnung im Fiori zu stellen.“",
    "`dienstreisemanagement.md`",
    "rules.py business_trip item 9 / policy `online_conferences`; hidden-test-exposure #18 (over-accept in BT)",
    "LOW: the page says no Dienstreiseantrag is to be filed; what staff do with one that was filed anyway (reject, or redirect to the 'Privat verauslagte Kosten' form) is UNVERIFIED (exposure #18). abgelehnt is our reading",
    "Die Konferenz findet ausschliesslich online statt. Online durchgefuehrte Konferenzen sind keine Dienstreisen; ein Dienstreiseantrag ist nicht zu stellen, die Teilnahmegebuehr wird ueber das Formular fuer privat verauslagte Kosten geltend gemacht. Geaendert gegenueber dienstreiseantrag-02: die Konferenz ist online.",
    {ANTRAG: [
        ("setline", r"^Reiseziel:", field("Reiseziel:", "Online (virtuelle Konferenz)")),
        ("sub", r"Reise ins Ausland:[ ]+(?P<x>\[X\] ja   \[ \] nein)", "[ ] ja   [X] nein"),
        ("setline", r"^Verkehrsmittel:", field("Verkehrsmittel:", "keine (virtuelle Teilnahme)")),
        ("drop", r"^A1-Bescheinigung:"),
        ("setline", r"^Start:", field("Start:", "Dienstag, 10. November 2026, 09:00 Uhr (Beginn der Teilnahme)")),
        ("setline", r"^Ende:", field("Ende:", "Mittwoch, 11. November 2026, 18:00 Uhr (Ende der Teilnahme)")),
        ("setline", r"^Arbeitstage:", field("Arbeitstage:", "2 (Konferenztage)")),
        ("drop", r"^ Bahn Kassel–Rotterdam"),
        ("drop", r"^ Unterkunft, 3 Nächte"),
        ("drop", r"^ Verpflegungsmehraufwand"),
        ("sub", r"Summe \(Schätzung\)[ ]+(?P<x>915,00 €)", "450,00 €"),
        ("setline", r"^Kooperationspartnern\. Die Übernachtung", "Kooperationspartnern."),
        ("drop", r"^Höchstgrenze des Auslandsübernachtungsgeldes"),
    ], MAILC: [
        ("rep", "held in Rotterdam, the Netherlands,", "held online,"),
        ("rep", "seeing you in Rotterdam", "seeing you online"),
    ], REG: [
        ("rep", "NordSys 2026, 10–11 November 2026, Rotterdam", "NordSys 2026, 10–11 November 2026, online"),
        ("rep", "Full registration, early bird, member rate", "Virtual registration, early bird, member rate"),
        ("setline", r"^Die Registrierung schließt den Zugang zu allen Sessions", "Die Registrierung schließt den Zugang zu allen Online-Sessions an beiden Konferenztagen ein. Das optionale"),
        ("setline", r"^Conference Dinner \(65,00 EUR\) wurde nicht gebucht", "Conference Dinner (65,00 EUR) wurde nicht gebucht."),
    ]},
    drop_docs=[BAHN],
)


# --------------------------------------------------------------------------- #
# PROCUREMENT
# --------------------------------------------------------------------------- #
OFFER = "angebot-1.pdf"
MAIL = "email-beschaffungsantrag.pdf"
BA = "beschaffungsantrag.pdf"
VV = "vergabevermerk.pdf"
CART = "wps-warenkorb.pdf"


def offer_ops(a, b, net, vat, gross):
    """beschaffungsantrag-02 (Löthaus Dannwolf): Lötstation unit a (x2), Heißluft b, Entlötpumpen 50,00."""
    f = lambda x: f"{x:.2f}".replace(".", ",") + " €"
    return [
        ("sub", r"mit Ablage[ ]+2[ ]+(?P<x>189,00 €)", f(a)),
        ("sub", r"mit Ablage[ ]+2[ ]+" + re.escape(f(a)) + r"[ ]+(?P<x>378,00 €)", f(2 * a)),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+(?P<x>245,00 €)", f(b)),
        ("sub", r"Heißluft-Rework-Station 700 W[ ]+1[ ]+" + re.escape(f(b)) + r"[ ]+(?P<x>245,00 €)", f(b)),
        ("sub", r"Summe netto[ ]+(?P<x>673,00 €)", eur(net)),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>127,87 €)", eur(vat)),
        ("sub", r"Angebotssumme brutto[ ]+(?P<x>800,87 €)", eur(gross)),
    ]


def mail_ops(a, b, net, gross, sentence=None):
    f = lambda x: f"{x:.2f}".replace(".", ",") + " €"
    ops = [
        ("sub", r"Lötstation digital 80 W mit Ablage, je (?P<x>189,00 €) netto", f(a)),
        ("sub", r"Heißluft-Rework-Station 700 W, je (?P<x>245,00 €) netto", f(b)),
        ("sub", r"Summe (?P<x>673,00 € netto, 800,87 €) brutto\.", f"{eur(net)} netto, {eur(gross)}"),
    ]
    if sentence:
        ops.append(("sub", r"brutto\. (?P<x>Da der Auftragswert unter 1\.000 € liegt, habe ich nur dieses eine Angebot)", sentence))
    return ops


case(
    PROC, "beschaffungsantrag-02", 1, "abgelehnt", "high",
    "Single offer 673,00 € net → exactly 1.000,00 € net (1.190,00 € gross); unit prices 189→250 and 245→450; the mail now says 'Der Auftragswert beträgt genau 1.000 € netto, ich habe nur dieses eine Angebot eingeholt'",
    "The duty to obtain three comparison offers lapses only when the order value is UNDER 1.000 EUR; at exactly 1.000 EUR net a single offer is not enough",
    "„Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ and „Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“",
    "`nachhaltiges-catering.md`; `beschaffung.md`",
    "rules.py procurement item 1/2 ('Unter 1.000 €' / 'Ab 1.000 € netto'), facts.py threshold; hidden-test-exposure #47",
    "Boundary case. The page says 'unter 1.000 Euro', so 1.000,00 is not under it; the Beschaffungsordnung itself is not in the corpus (exposure #47, #51) and may word the limit 'bis 1.000'. Net or gross is also not stated on the page; the net is 1.000,00 and the gross 1.190,00, so both readings give 'not under' and the label does not depend on it",
    "Das einzige Angebot (DW-A-5518) lautet auf genau 1.000,00 EUR netto (1.190,00 EUR brutto). Die Pflicht zu drei Vergleichsangeboten entfaellt nur, wenn der Auftragswert unter 1.000 EUR liegt; 1.000,00 EUR ist nicht darunter, ein Rahmenvertragsprodukt liegt nicht vor (Loetstationen). Es fehlen zwei Vergleichsangebote oder eine Begruendung. Geaendert gegenueber beschaffungsantrag-02: Nettobetrag 1.000,00 EUR (vorher 673,00 EUR).",
    {OFFER: offer_ops(250, 450, 1000, 190, 1190),
     MAIL: mail_ops(250, 450, 1000, 1190,
                    "Der Auftragswert beträgt genau 1.000 € netto, ich habe nur dieses eine Angebot")},
)
case(
    PROC, "beschaffungsantrag-02", 2, "angenommen", "high",
    "Single offer 673,00 € net → 999,00 € net (1.188,81 € gross); unit prices 189→250 and 245→449; the mail keeps 'Da der Auftragswert unter 1.000 € liegt' (true for the net amount)",
    "Order value under 1.000 EUR: direct award with one offer is allowed",
    "„Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“",
    "`nachhaltiges-catering.md`",
    "rules.py procurement item 1; facts.py net-vs-gross threshold; hidden-test-exposure #47",
    "Net 999,00 is under 1.000, the gross 1.188,81 is over; as in variant 02-v2 the page does not say net or gross, but the practice case (net 673,00 / gross 800,87) and the organisers' own reading of such cases use the net. A model comparing the gross rejects",
    "Das einzige Angebot lautet auf 999,00 EUR netto (1.188,81 EUR brutto). Der Auftragswert liegt unter 1.000 EUR, damit entfaellt die Pflicht zu drei Vergleichsangeboten und eine Direktvergabe ist moeglich; Loetstationen sind kein Rahmenvertragsprodukt, die Kostenstellenbevollmaechtigte hat in Kopie beauftragt. Geaendert gegenueber beschaffungsantrag-02: Nettobetrag 999,00 EUR (vorher 673,00 EUR).",
    {OFFER: offer_ops(250, 449, 999, 189.81, 1188.81),
     MAIL: mail_ops(250, 449, 999, 1188.81)},
)

case(
    PROC, "beschaffungsantrag-03", 1, "abgelehnt", "high",
    "Position 9: '2 × Monitor 27 Zoll, WQHD, höhenverstellbar' from bildschirmlager-vogtland.de → '2 × Bürodrehstuhl ergonomisch, Netzrücken' from sitzwerk-onlineshop.de, same price 169,00 € gross each, total 926,93 € unchanged",
    "Office swivel chairs are a framework-contract product group and must be ordered exclusively from the framework partner (via WPS), not from a web shop, whatever the amount",
    "„Derzeit existieren Rahmenverträge u.a. für Büromaterial, PC's/Notebooks und Monitore, Büropapiere, Bürodrehstühle, Seminarstühle, Büromobiliar, Kopiergeräte, Software-Produkte von Microsoft.“ and „Sollte man ein Produkt bestellen wollen, zu dem ein Rahmenvertrag besteht, muss man dieses Produkt ausschließlich beim Rahmenvertragspartner bestellen“",
    "`rahmenvertraege.md` (Bürodrehstühle: Nowy Styl Deutschland GmbH, orders via WPS); `beschaffung.md`",
    "rules.py procurement item 3 (list names Bürodrehstühle); hidden-test-exposure #40 (R1 error C)",
    "Same label as the base (03 is already abgelehnt), so a model that learnt 'monitors from a web shop' only passes by luck here; the test is whether chairs are on its list. Same remaining risk as 03: the professor is only in copy",
    "Position 9 sind zwei Buerodrehstuehle aus einem Webshop (sitzwerk-onlineshop.de). Fuer Buerodrehstuehle besteht ein Rahmenvertrag (Nowy Styl Deutschland GmbH), solche Produkte sind ausschliesslich beim Rahmenvertragspartner ueber WPS zu bestellen; die geringe Summe (926,93 EUR brutto) hebt diese Bindung nicht auf. Geaendert gegenueber beschaffungsantrag-03: Position 9 (vorher zwei Monitore, ebenfalls Rahmenvertragsprodukt).",
    {MAIL: [
        ("sub", r"9\. 2 × (?P<x>Monitor 27 Zoll, WQHD, höhenverstellbar), je 169,00", "Bürodrehstuhl ergonomisch, Netzrücken"),
        ("setline", r"bildschirmlager-vogtland\.de/produkt/27-wqhd-hv-2207", "  https://www.sitzwerk-onlineshop.de/produkt/bds-netz-2207"),
        ("sub", r"^[ ]*Die (?P<x>Monitore) sind für die zwei neuen Messplätze", "Stühle"),
    ]},
)

_ROW5 = "   1          Tragbarer Rechner 14 Zoll, 32 GB RAM, 1 TB SSD,                                  2           1.127,40 €          2.254,80 €"
_CART_ROW = "  RV-NB-14-3210            Tragbarer Rechner 14 Zoll, 32 GB RAM, 1 TB SSD,                     2            1.127,40 €           2.254,80 €"
_CHAIR_NET = 6 * 287.50 + 2 * 264.00          # 2.253,00
_CHAIR_VAT = round(_CHAIR_NET * 0.19, 2)      # 428,07
_CHAIR_GROSS = round(_CHAIR_NET + _CHAIR_VAT, 2)

case(
    PROC, "beschaffungsantrag-05", 1, "angenommen", "high",
    "Cart and Antrag: IT equipment (notebooks, monitors, docking stations; Rahmenvertrag IT-Arbeitsplatzgeräte, Tessmer & Kolb) → office swivel chairs (6 + 2) from the WPS catalogue 'Rahmenvertrag Bürodrehstühle', framework partner Nowy Styl Deutschland GmbH; 2.253,00 € net, no comparison offers; category GWG (net unit price under 800 €)",
    "A framework product ordered from the framework partner through WPS needs no comparison offers, whatever the amount",
    "„Der Abschluss der Rahmenverträge ermöglicht den einzelnen Bereichen Ihre Bedarfe aus den jeweiligen Rahmensortimenten ohne das Einholen von Vergleichsangeboten zu decken.“ and „Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“",
    "`rahmenvertraege.md` (Bürodrehstühle: Nowy Styl Deutschland GmbH, „Die Bestellungen sind über das WPS-System zu buchen“); `beschaffung.md`",
    "rules.py procurement items 2/3 (framework exception, chairs on the list); hidden-test-exposure #40, #41",
    "The pair of 03-e1 (web shop, reject) and this case (WPS, accept) tests both directions on the same product group. Prices and the model names are invented; the partner name is the one on the page",
    "Beide Positionen sind Buerodrehstuehle, ein Rahmenvertragsprodukt; sie werden ueber den WPS-Katalog Rahmenvertrag Buerodrehstuehle beim Rahmenvertragspartner Nowy Styl Deutschland GmbH bestellt (Warenkorb WK-0027-18834, Antrag und Warenkorb stimmen ueberein, 2.253,00 EUR netto). Bei Rahmenvertragspartnern entfaellt das Einholen von drei Angeboten, die Kostenstellenbevollmaechtigte hat beauftragt. Geaendert gegenueber beschaffungsantrag-05: Rahmenvertragsprodukt Buerodrehstuehle statt IT-Geraete.",
    {BA: [
        ("setline", r"^ Kategorie ", " Kategorie                                           [ ] Verbrauchsmaterial [X] GWG [ ] Anlage"),
        ("setline", r"^ Vorgesehener Lieferant", " Vorgesehener Lieferant                              Nowy Styl Deutschland GmbH, Steyerberg"),
        ("setline", r"^   1          Tragbarer Rechner",
         row_like(_ROW5, "1", "Bürodrehstuhl, Netzrücken, 3D-Armlehnen,", "6", eur(287.50), eur(6 * 287.50))),
        ("setline", r"^              Vertragskkonfiguration A|^              Vertragskonfiguration A", "              Vertragsmodell A"),
        ("setline", r"^   2          Monitor 27 Zoll",
         row_like(_ROW5, "2", "Bürodrehstuhl, Vollpolster, Vertragsmodell B", "2", eur(264.00), eur(2 * 264.00))),
        ("drop", r"^   3          Dockingstation"),
        ("sub", r"Summe netto[ ]+(?P<x>2\.971,80 €)", eur(_CHAIR_NET)),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>564,64 €)", eur(_CHAIR_VAT)),
        ("sub", r"Gesamtbetrag brutto[ ]+(?P<x>3\.536,44 €)", eur(_CHAIR_GROSS)),
        ("setline", r"^  Ausstattung von zwei neuen Arbeitsplätzen", "  Ersatz verschlissener Bürodrehstühle in zwei Büros des Fachgebiets. Alle Artikel stammen aus dem"),
    ], CART: [
        ("setline", r"^ Katalog ", " Katalog                                       Rahmenvertrag Bürodrehstühle der hessischen Hochschulen"),
        ("drop", r"^[ ]+Notebooks und Monitore$"),
        ("sub", r"Lieferant \(Rahmenvertragspartner\)[ ]+(?P<x>Tessmer & Kolb Systemhaus GmbH, Offenbach)", "Nowy Styl Deutschland GmbH, Steyerberg"),
        ("setline", r"^  RV-NB-14-3210",
         row_like(_CART_ROW, "RV-BD-14-0110", "Bürodrehstuhl, Netzrücken, 3D-Armlehnen,", "6", eur(287.50), eur(6 * 287.50), aligns="llrrr")),
        ("setline", r"^                           Vertragskonfiguration A", "                           Vertragsmodell A"),
        ("setline", r"^  RV-MO-27-0415",
         row_like(_CART_ROW, "RV-BD-14-0125", "Bürodrehstuhl, Vollpolster, Vertragsmodell B", "2", eur(264.00), eur(2 * 264.00), aligns="llrrr")),
        ("drop", r"^  RV-DS-C-0088"),
        ("sub", r"Warenwert netto[ ]+(?P<x>2\.971,80 €)", eur(_CHAIR_NET)),
        ("sub", r"USt\. 19 %[ ]+(?P<x>564,64 €)", eur(_CHAIR_VAT)),
        ("sub", r"Gesamt brutto[ ]+(?P<x>3\.536,44 €)", eur(_CHAIR_GROSS)),
    ]},
)

case(
    PROC, "beschaffungsantrag-01", 1, "abgelehnt", "high",
    "Award: cheapest offer (Oszillo-Kontor Vehrs, 2.667,00 € net, rank 1) → the middle offer (Messgeräte Quistorp, 2.745,00 € net, rank 2) in Antrag and Vergabevermerk; the Antrag/Vergabevermerk give no reason for passing over the cheapest; 'Wertung: Preis (netto), bei gleicher technischer Eignung' and 'Alle drei Angebote erfüllen die Anforderungen' stay",
    "With three technically equal offers the award goes to the cheapest (most economical) one; passing it over needs a documented reason",
    "„Wertung: Preis (netto), bei gleicher technischer Eignung“ and „Alle drei Angebote erfüllen die Anforderungen.“ (the Vergabevermerk form itself); practice case beschaffungsantrag-07: „Den Zuschlag erhält das günstigste Angebot“; the page `beschaffung.md` only requires three offers (and `rahmenvertraege.md`: „Wir empfehlen aus Gründen der Wirtschaftlichkeit und Sparsamkeit grundsätzlich Preisvergleiche“)",
    "Vergabevermerk form of the practice cases 01/04/06/07; Beschaffungsordnung not in the corpus (rule-inventory PR-07: UNVERIFIED in the corpus)",
    "rules.py procurement item 4 / policy `cheapest_offer`; rule-inventory PR-07",
    "The rule is not on a corpus page: it comes from the Vergabevermerk form that every practice case carries (the form's own criterion is price at equal fitness and it states all offers are fit). No page sentence says 'cheapest must win', so a strict reader could call the label unsupported; kept in the scored set because the case documents contradict themselves",
    "Die drei Angebote sind technisch gleichwertig (Vergabevermerk: alle erfuellen die Anforderungen, Wertung nach dem Nettopreis). Den Zuschlag erhaelt aber die Messgeraete Quistorp GmbH mit 2.745,00 EUR netto, obwohl das Angebot der Oszillo-Kontor Vehrs GmbH mit 2.667,00 EUR netto guenstiger ist; eine Begruendung dafuer fehlt. Das wirtschaftlichste Angebot ist nicht gewaehlt. Geaendert gegenueber beschaffungsantrag-01: Zuschlag an das zweitguenstigste statt an das guenstigste Angebot.",
    {BA: [
        ("setline", r"^ Vorgesehener Lieferant", " Vorgesehener Lieferant                              Messgeräte Quistorp GmbH, Kaiserslautern (Angebot Q-104882)"),
        ("setline", r"^   1          Digitales Speicheroszilloskop",
         row_like("   1          Digitales Speicheroszilloskop, 4 Kanäle, 350 MHz, 5 GS/s                          1           2.390,00 €          2.390,00 €",
                  "1", "Oszilloskop digital, 4 Kanäle, 350 MHz Bandbreite", "1", "2.455,00 €", "2.455,00 €")),
        ("setline", r"^   2          Passiver Tastkopf",
         row_like("   2          Passiver Tastkopf 10:1, 500 MHz                                                   4              48,00 €            192,00 €",
                  "2", "Tastkopfsatz 500 MHz, je Stück", "4", "45,00 €", "180,00 €")),
        ("setline", r"^   3          Werkskalibrierschein",
         row_like("   3          Werkskalibrierschein                                                              1              85,00 €              85,00 €",
                  "3", "DAkkS-Kalibrierung", "1", "110,00 €", "110,00 €")),
        ("sub", r"Summe netto[ ]+(?P<x>2\.667,00 €)", "2.745,00 €"),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>506,73 €)", "521,55 €"),
        ("sub", r"Gesamtbetrag brutto[ ]+(?P<x>3\.173,73 €)", "3.266,55 €"),
        ("setline", r"^  nicht aus\. Es wurden drei Angebote eingeholt",
         "  nicht aus. Es wurden drei Angebote eingeholt; ausgewählt wurde das Angebot der Messgeräte Quistorp GmbH."),
        ("drop", r"^  das günstigste\.$"),
    ], VV: [
        ("setline", r"^Zuschlag an", "Zuschlag an                                 Messgeräte Quistorp GmbH, 2.745,00 € netto"),
        ("setline", r"^Alle drei Angebote erfüllen die Anforderungen", "Alle drei Angebote erfüllen die Anforderungen. Den Zuschlag erhält die Messgeräte Quistorp GmbH."),
    ]},
)
case(
    PROC, "beschaffungsantrag-01", 2, "angenommen", "high",
    "Antrag: VAT 506,73 € → 506,74 € and gross 3.173,73 € → 3.173,74 € (a rounding difference of one cent against offer and Vergabevermerk); net 2.667,00 € unchanged",
    "Only material inconsistencies between form, offer and award note count; a one-cent rounding difference is not material",
    "„Inconsistencies only count when they are material, so an agent is not rewarded for nitpicking“ (procurement README)",
    "`task-2-procurement-spot-check/README.md` (Cases section); practice case 04 gold: „Die Abweichung ... liegt weit über der Wesentlichkeitsgrenze“",
    "rules.py procurement item 5 ('nur wesentliche Abweichungen zählen'); hidden-test-exposure #46",
    "No threshold is written anywhere (exposure #46: UNVERIFIED); one cent on 3.173,73 € is far below any reasonable threshold and the practice differences are 38-41 %. The source is the task README, not a university page",
    "Alle drei Angebote liegen vor (2.667,00 / 2.745,00 / 2.783,00 EUR netto), das guenstigste erhaelt den Zuschlag, die Positionen und die Nettosumme stimmen in Antrag, Angebot und Vergabevermerk ueberein. Der Antrag weist USt und Brutto um einen Cent hoeher aus (3.173,74 statt 3.173,73 EUR): eine Rundungsdifferenz, nicht wesentlich. Geaendert gegenueber beschaffungsantrag-01: USt/Brutto im Antrag +0,01 EUR.",
    {BA: [
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>506,73 €)", "506,74 €"),
        ("sub", r"Gesamtbetrag brutto[ ]+(?P<x>3\.173,73 €)", "3.173,74 €"),
    ]},
)

case(
    PROC, "beschaffungsantrag-02", 3, "abgelehnt", "low",
    "E-Mail: the Cc line to Prof. Eichelkraut and the sentence 'Frau Prof. Eichelkraut ist in Kopie und hat die Bestellung beauftragt.' removed; the order comes from the employee alone and no cost-centre holder is named or shown to have ordered",
    "Orders must be placed by the cost-centre holder (mostly the head of the Fachgebiet)",
    "„Bestellungen müssen vom Kostenstellenbevollmächtigten (meist Fachgebietsleitung) beauftragt werden.“",
    "`beschaffung.md`",
    "rules.py procurement item 6 / policy `cost_centre`; hidden-test-exposure #39 (over-accept)",
    "LOW: UNVERIFIED whether staff reject for this alone (exposure #39); the mail may simply be completed on request, and the Beschaffungsantrag form of the other cases carries a signature field that an e-mail order lacks. abgelehnt is our reading of the page",
    "Die Bestellung per E-Mail stammt von einem Mitarbeiter allein; ein Kostenstellenbevollmaechtigter (Fachgebietsleitung) ist weder in Kopie noch genannt und hat nicht beauftragt. Bestellungen muessen vom Kostenstellenbevollmaechtigten beauftragt werden. Geaendert gegenueber beschaffungsantrag-02: der Hinweis auf die Beauftragung durch die Professorin und der Cc-Empfaenger fehlen.",
    {MAIL: [
        ("drop", r"^[ ]*Cc: "),
        ("sub", r"Auftrag 2140112\.(?P<x> Frau Prof\. Eichelkraut ist in Kopie und hat die Bestellung beauftragt\.)", ""),
    ]},
)


# --------------------------------------------------------------------------- #
# EXPENSE REIMBURSEMENT
# --------------------------------------------------------------------------- #
def bakery_receipt(note_lines):
    return "\n".join([
        " BÄCKEREI-CAFÉ HELLWIG",
        " Marktgasse 14",
        " 37073 Göttingen",
        " Tel. 0551 48 21 307",
        "",
        "KAFFEE KANNE 1,0 L",
        "3 ST x 6,90                     20,70",
        "",
        "KUCHEN STUECK",
        "6 ST x 2,40                     14,40",
        "",
        "SUMME EUR                       35,10",
        "",
        " BAR 40,00",
        " RÜCKGELD 4,90",
        "",
        " MWST 7% NETTO 32,80 MWST 2,30",
        " BON 2217 KASSE 01 19.05.27 08:35",
        " St.-Nr. 20/218/52871",
        " VIELEN DANK FÜR IHREN BESUCH",
        "",
        "",
    ] + note_lines) + "\n"


case(
    EXP, "auslagenerstattung-02", 1, "abgelehnt", "high",
    "Till receipt: hardware store with article numbers → bakery-café with named items (3 coffee pots, 6 pieces of cake, 35,10 €); handwritten note 'Kabelbinder + Schrumpfschlauch für Versuchsstand' → 'Kaffee + Kuchen für interne Teambesprechung Lehrstuhl (6 Beschäftigte, keine externen Gäste)'",
    "Hospitality at which no external persons took part is not reimbursable",
    "„Nicht erstattungsfähige Aufwendungen sind: Bewirtungen, an denen keine externen Personen teilgenommen haben,“ and „Arbeitsessen, d. h. aus dienstlichem Interesse mit überwiegend Universitätsangehörigen,“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie, 'Nicht erstattungsfähige Aufwendungen sind')",
    "rules.py expense item 5 / policy `hospitality`; hidden-test-exposure #30 (both directions)",
    "Pair with e2: the receipt text is identical, only the handwritten note differs. 'Kaffee/Kuchen' is on the page's list of normal courtesies, but only 'die Gästen der Universität angeboten werden'; an internal team meeting has no guests. Practice case 07 (tea kitchen, abgelehnt) is the neighbour",
    "Der Bon eines Baeckerei-Cafes ueber 35,10 EUR (Kaffee und Kuchen) ist mit dem handschriftlichen Vermerk versehen, dass er fuer eine interne Teambesprechung des Lehrstuhls mit 6 Beschaeftigten und ohne externe Gaeste angefallen ist. Bewirtungen, an denen keine externen Personen teilgenommen haben, sind nach der Bewirtungskostenrichtlinie nicht erstattungsfaehig. Geaendert gegenueber auslagenerstattung-02: Beleg ist ein Bewirtungsbon, Zweck interne Besprechung.",
    new_docs={"beleg-1.pdf": (bakery_receipt([
        " Kaffee + Kuchen für interne Teambesprechung",
        " Lehrstuhl (6 Beschäftigte, keine externen Gäste)",
        " (F. Kallweit-Omondi)"]), "beleg-1.pdf")},
)
case(
    EXP, "auslagenerstattung-02", 2, "angenommen", "high",
    "As e1, same bakery receipt; the handwritten note now says 'Kaffee + Kuchen für Gäste des Kolloquiums (4 externe Gäste, 2 Beschäftigte)'",
    "Mineral water, coffee, tea, fruit and pastries offered to guests of the university are courtesies and running operating costs, not hospitality costs; they are reimbursable",
    "„Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen und damit auch aus Landesmitteln finanzierbar sind die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden.“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie); „kleinere, zeitlich dringende Anschaffungen“ and „Stichwort“ from the section Kostenerstattung",
    "rules.py expense item 5 / policy `hospitality`; hidden-test-exposure #30",
    "A strict reader may ask for a participant list (that applies to real Bewirtungskosten, not to courtesies) or find a bakery run not 'zeitlich dringend'; the page gives coffee and pastries for guests as the explicit allowed example. Pair with e1",
    "Der Bon eines Baeckerei-Cafes ueber 35,10 EUR (Kaffee und Kuchen) ist mit dem Vermerk versehen, dass er fuer Gaeste des Kolloquiums (4 externe Gaeste, 2 Beschaeftigte) angefallen ist. Kaffee und Gebaeck, die Gaesten der Universitaet angeboten werden, sind laufende Betriebsaufwendungen und erstattungsfaehig; der Betrag ist klein, Beleg und Zweck sind vollstaendig. Geaendert gegenueber auslagenerstattung-02: Beleg ist ein Bon fuer Kaffee und Kuchen, Zweck Gaeste des Kolloquiums.",
    new_docs={"beleg-1.pdf": (bakery_receipt([
        " Kaffee + Kuchen für Gäste des Kolloquiums",
        " (4 externe Gäste, 2 Beschäftigte)",
        " (F. Kallweit-Omondi)"]), "beleg-1.pdf")},
)

RESTAURANT = """Gasthaus Zum Alten Brunnen                                            Bewirtungsbeleg Nr. 004417
Inh. Familie Kettwig                                                 Registriernummer R-27-0044170
Brunnenstraße 9, 37154 Northeim                                      Datum und Ort des Verzehrs:
Steuernummer 20/218/30451                                            27.05.2027, Northeim, Tisch 6, 4 Personen


Rechnungsempfänger:
Universität Wernstadt
Lehrstuhl für Hochfrequenztechnik
Am Lindenhang 40
35291 Wernstadt


 Beschreibung                                                   Menge        MwSt              netto            brutto

 Schweinemedaillons mit Pilzrahmsauce und Spätzle                   2         7 %            30,84 €           33,00 €

 Gemüselasagne mit Salat                                            2         7 %            30,84 €           33,00 €

 Mineralwasser 0,75 l                                               2        19 %             8,74 €           10,40 €

 Kaffee                                                             4        19 %            12,10 €           14,40 €

                                                                              Summe netto                      82,52 €
                                                                              zzgl. USt 7 %                     4,32 €
                                                                              zzgl. USt 19 %                    3,96 €
                                                                              Rechnungsbetrag                  90,80 €

Bezahlt mit EC-Karte durch den Bewirtenden am 27.05.2027.

Unterschrift des Bewirtenden: Dr. Wiebke Achterhold
"""

NACHWEIS = """Bewirtungsnachweis zum Bewirtungsbeleg Nr. 004417 (Gasthaus Zum Alten Brunnen, Northeim, 27.05.2027)


Anlass, Zweck und dienstliches Interesse
Arbeitstreffen mit zwei Kooperationspartnern zur Vorbereitung eines gemeinsamen Drittmittelantrags im Programm
"Sensorik für die Fertigung" (Einwerbung von Drittmitteln und Kooperationen). Einladung der Universität Wernstadt
vom 12.05.2027, Beginn 12:00 Uhr, Dauer etwa zwei Stunden.

Teilnehmerkreis (Gäste und Universitätsbedienstete gesondert gekennzeichnet)

 Nr.   Name                          Einrichtung                                       Kennzeichnung
 1     Dr. Wiebke Achterhold         Universität Wernstadt, Lehrstuhl Hochfrequenztechnik   Universitätsbedienstete (bewirtend)
 2     M. Sc. Pelle Wimmerstedt      Universität Wernstadt, Lehrstuhl Hochfrequenztechnik   Universitätsbedienstete
 3     Dr. Sabine Kowarsch           Sensorik Nordhessen GmbH                          Gast (extern)
 4     Prof. Dr. Lutz Hettenbach     Hochschule Weserbergland                          Gast (extern)

Kosten
Rechnungsbetrag 90,80 € für 4 Personen, das sind 22,70 € je Person (Höchstsatz 60,00 € je Person und Veranstaltungstag).
Finanzierung aus Drittmitteln: Drittmittelprojekt "HF-Kooperation", Kostenstelle 71 4410.


Wernstadt, 28.05.2027                                              Unterschrift: Dr. Wiebke Achterhold
"""

case(
    EXP, "auslagenerstattung-07", 1, "angenommen", "high",
    "Invoice for kettle, mugs, coffee, tea and two name lines for the chair's tea kitchen (abgelehnt) → a restaurant hospitality receipt (Bewirtungsbeleg to the university, named dishes, 90,80 € for 4 persons = 22,70 € each) with a separate Bewirtungsnachweis (purpose, participant list marking 2 guests and 2 employees, Drittmittel financing)",
    "Hospitality of guests is reimbursable with written purpose, a participant list with guests marked, a hospitality receipt made out to the university with exact items, within 60 EUR per person and day, financed from Drittmittel",
    "„Der Anlass, der Zweck und das dienstliche Interesse der Bewirtung sind hinreichend schriftlich darzulegen.“, „Der Teilnehmerkreis ist mit einer Liste der Namen der bewirteten Personen schriftlich anzugeben.“, „Pro Person und Veranstaltungstag € 60,-.“, „Die Finanzierung muss aus Drittmitteln erfolgen.“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie: Erstattungsfähige Bewirtungskosten, Zu erbringende Nachweise, Erstattungssätze)",
    "rules.py expense item 5 / policy `hospitality` (guest hospitality needs Anlass, Teilnehmerliste, Rechnung an die Universität); hidden-test-exposure #29",
    "Both documents are written from scratch (no practice document has this shape), so this is more than one changed fact; the base id names the practice case whose theme (hospitality) it tests. The receipt has Registriernummer, items, date and place, recipient, VAT, signature, address and tax number, but not the names of the guests (they are on the Nachweis, which the page allows: 'ggf. separate Teilnehmerliste'). Pair with e2",
    "Der Bewirtungsbeleg des Gasthauses ist auf die Universitaet Wernstadt ausgestellt, nennt die verzehrten Speisen und Getraenke genau, Datum, Ort, Steuernummer, USt und Unterschrift. Das Bewirtungsnachweis-Blatt legt Anlass (Kooperationstreffen zur Drittmitteleinwerbung), Teilnehmerkreis mit zwei externen Gaesten und zwei Beschaeftigten sowie die Finanzierung aus einem Drittmittelprojekt dar; 22,70 EUR je Person liegen unter 60,00 EUR. Die Bewirtungskostenrichtlinie ist erfuellt. Geaendert gegenueber auslagenerstattung-07: Bewirtung von Gaesten mit vollstaendigem Nachweis statt Teekuechen-Einkauf.",
    drop_docs=["rechnung-teekueche.pdf"],
    new_docs={"bewirtungsbeleg.pdf": (RESTAURANT, "rechnung-teekueche.pdf"),
              "bewirtungsnachweis.pdf": (NACHWEIS, "rechnung-teekueche.pdf")},
)
case(
    EXP, "auslagenerstattung-07", 2, "abgelehnt", "high",
    "As e1, same restaurant receipt, but the Bewirtungsnachweis (purpose, participant list with guests marked, financing) is missing; the receipt shows no names of the persons entertained",
    "Hospitality needs a written participant list with the names of the persons entertained (guests marked) and a written purpose",
    "„Der Teilnehmerkreis ist mit einer Liste der Namen der bewirteten Personen schriftlich anzugeben. Dabei sollen Gäste und Universitätsbedienstete gesondert gekennzeichnet sein.“ and „Der Anlass, der Zweck und das dienstliche Interesse der Bewirtung sind hinreichend schriftlich darzulegen.“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie, Zu erbringende Nachweise)",
    "rules.py expense item 5 / policy `hospitality`; hidden-test-exposure #29 (restaurant bill without participant list accepted)",
    "The receipt is otherwise complete; the single missing piece is the list and the purpose. Staff might ask for the list instead of rejecting (the task has two labels). Pair with e1",
    "Eingereicht ist nur der Bewirtungsbeleg eines Restaurants ueber 90,80 EUR fuer 4 Personen. Es fehlen die schriftliche Darlegung von Anlass, Zweck und dienstlichem Interesse und die Liste der Namen der bewirteten Personen mit Kennzeichnung der Gaeste; auf dem Beleg stehen keine Namen. Ohne diese Nachweise ist die Bewirtung nach der Bewirtungskostenrichtlinie nicht erstattungsfaehig. Geaendert gegenueber auslagenerstattung-07: Gaeste-Bewirtung ohne Anlass und Teilnehmerliste.",
    drop_docs=["rechnung-teekueche.pdf"],
    new_docs={"bewirtungsbeleg.pdf": (RESTAURANT, "rechnung-teekueche.pdf")},
)

case(
    EXP, "auslagenerstattung-08", 1, "angenommen", "high",
    "Online-workshop fee billed in USD (USD 175,00) with a card statement showing 160,37 € + 2,81 € → receipt in EUR (EUR 160,00), card statement left out (a EUR receipt marked 'Paid by credit card' needs no conversion proof)",
    "A privately advanced online-conference fee is reimbursed with the original receipt; in euros the receipt alone shows the amount",
    "„Die Teilnahmegebühren für Online Konferenzen / Tagungen sind über das Formular \"Privat Verauslagte Kosten\" bei der Finanzabteilung geltend zu machen.“ and „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“",
    "`dienstreisemanagement.md`; `finanzbuchhaltung-und-steuern.md` (Kostenerstattung)",
    "rules.py expense policy `foreign_currency` ('bei Fremdwährung ... Zahlungsnachweis') must not fire for EUR; hidden-test-exposure #33 (over-reject), #18",
    "The payment proof is not demanded by any page; the receipt says 'Paid by credit card (Visa ****6031)'. A model with a rule 'always need a card statement' rejects. The odd e-mail address on the receipt (pseudonymization trace) stays and never decides",
    "Die Quittung ueber die Teilnahme an einem ausschliesslich online stattfindenden Workshop lautet auf EUR 160,00 und ist laut Vermerk per Kreditkarte bezahlt; Online-Konferenzen sind keine Dienstreisen, die Teilnahmegebuehr wird als privat verauslagte Kosten erstattet. Bei einem Betrag in Euro belegt die Quittung den Betrag, ein Kontoauszug zur Umrechnung ist nicht noetig. Geaendert gegenueber auslagenerstattung-08: Betrag in EUR statt USD, Kartenabrechnung entfaellt.",
    {"rechnung-konferenzgebuehr.pdf": [
        ("rep_all", "USD 175.00", "EUR 160.00"),
        ("rep", "Total paid (USD)", "Total paid (EUR)"),
    ]},
    drop_docs=["kontoauszug.pdf"],
)
case(
    EXP, "auslagenerstattung-08", 2, "abgelehnt", "low",
    "Card statement left out; the receipt stays in USD (USD 175,00), so the euro amount of the claim cannot be checked",
    "Costs in a foreign currency: receipt and payment proof together show the euro amount",
    "no page sentence on payment proof in a foreign currency; nearest: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“",
    "`finanzbuchhaltung-und-steuern.md` (Kostenerstattung); rule EX6 of the system prompt has no page source",
    "rules.py expense policy `foreign_currency` (EX6, no page source); hidden-test-exposure #33, #34",
    "hidden-test-exposure #33 marks the rule UNVERIFIED. The receipt is an original receipt marked paid, which the page asks for; a reader could accept it and leave the conversion to the finance office. Not scored",
    "Die Quittung lautet auf USD 175,00; der Euro-Betrag der Erstattung ist ohne Kreditkartenabrechnung nicht belegt. Geaendert gegenueber auslagenerstattung-08: Kontoauszug fehlt.",
    drop_docs=["kontoauszug.pdf"],
)
case(
    EXP, "auslagenerstattung-05", 1, "angenommen", "low",
    "Invoice RE 27-0618: the item line 'Handout DIN A3, 4-farbig, 160 g/m²' → a person's name ('Corinna Hasselbrink'), qty, tax and amounts unchanged",
    "Pseudonymization traces such as a name instead of an article never decide a case; the other items, the recipient and the credit note are in order",
    "„These traces never decide a case.“ (README of the expense set) against „Es ist anzugeben, um welche Artikel es sich handelt.“ (`glossar-drittmittelbewirtschaftung.md`)",
    "`task-2-expense-reimbursement-spot-check/README.md`; `glossar-drittmittelbewirtschaftung.md`",
    "rules.py GENERAL ('Geschwärzte oder ersetzte Namen entscheiden nie'); hidden-test-exposure #31 (over-reject)",
    "Practice case 07 has the same trace and is abgelehnt for other reasons; here the only oddity is the name on a 14,30 € line of a correct print invoice. The README says traces never decide, the glossary says the article must be named: ambiguous. Not scored",
    "Rechnungen und Gutschrift sind an den Lehrstuhl gerichtet, der Saldo von 135,68 EUR ist richtig. Eine Position zeigt statt einer Artikelbezeichnung einen Personennamen; das ist eine Spur der Pseudonymisierung und entscheidet nicht. Geaendert gegenueber auslagenerstattung-05: Artikelbezeichnung der Handout-Position durch einen Namen ersetzt.",
    {"rechnung-druckerei.pdf": [
        ("sub", r"(?P<x>Handout DIN A3, 4-farbig, 160 g/m²)", "Corinna Hasselbrink"),
    ]},
)


# --------------------------------------------------------------------------- #
# Build and verify
# --------------------------------------------------------------------------- #
def build():
    problems = []
    for base in (OUT_HIGH, OUT_LOW):
        for s in SETS:
            d = base / s
            if (d / "inputs").exists():
                shutil.rmtree(d / "inputs")
            (d / "inputs").mkdir(parents=True)
    truth = {(c, s): [] for c in ("high", "low") for s in SETS}
    for v in CASES:
        out = OUT_HIGH if v["confidence"] == "high" else OUT_LOW
        src = DATASETS / v["set"] / "inputs" / v["base"]
        dst = out / v["set"] / "inputs" / v["id"]
        dst.mkdir(parents=True)
        names = {p.name for p in src.glob("*.pdf")}
        unknown = (set(v["edits"]) | set(v["drop_docs"])) - names
        if unknown:
            problems.append(f"{v['id']}: edits/drops for missing documents {sorted(unknown)}")
        for pdf in sorted(src.glob("*.pdf")):
            if pdf.name in v["drop_docs"]:
                continue
            target = dst / pdf.name
            if pdf.name in v["new_docs"]:
                continue  # written below
            if pdf.name not in v["edits"]:
                shutil.copyfile(pdf, target)
                if target.read_bytes() != pdf.read_bytes():
                    problems.append(f"{v['id']}/{pdf.name}: copy differs")
                continue
            old = mv.pdftotext(pdf)
            new = apply_ops(old, v["edits"][pdf.name], f"{v['id']}/{pdf.name}")
            new = new.replace("→", "->")  # WinAnsi/Courier has no arrow glyph
            mv.write_pdf(target, new, mv.page_size(pdf), pdf.name)
            check(problems, v, target, new, old)
        for name, (text, size_from) in v["new_docs"].items():
            target = dst / name
            sz = mv.page_size(src / size_from)
            mv.write_pdf(target, text, sz, name)
            check(problems, v, target, text, None)
        truth[(v["confidence"], v["set"])].append({"antrag": v["id"], "result": v["result"], "begruendung": v["reason"]})
    for (conf, s), rows in truth.items():
        d = (OUT_HIGH if conf == "high" else OUT_LOW) / s
        with open(d / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for row in sorted(rows, key=lambda r: r["antrag"]):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return problems


def check(problems, v, target, new, old):
    got = mv.pdftotext(target)
    if mv.norm(got) != mv.norm(new):
        problems.append(f"{v['id']}/{target.name}: text does not round-trip")
        for x, y in zip(mv.norm(got), mv.norm(new)):
            if x != y:
                problems.append(f"   got : {x}\n   want: {y}")
                break
    if old is not None and mv.norm(new) == mv.norm(old):
        problems.append(f"{v['id']}/{target.name}: edit changed nothing")
    if re.search(r"[�]", got):
        problems.append(f"{v['id']}/{target.name}: replacement character in text")


def table(confidence="high"):
    rows = ["| Case | Base | Changed fact (old → new) | Expected | Rule, quote, source | Confidence | Tests (our rule or fact) | Risk |",
            "|---|---|---|---|---|---|---|---|"]
    for v in CASES:
        if v["confidence"] != confidence:
            continue
        rows.append(f"| `{v['id']}` ({SHORT[v['set']]}) | `{v['base']}` | {v['changed']} | {v['result']} | "
                    f"{v['rule']}: {v['quote']} ({v['source']}) | {v['confidence']} | {v['tests']} | {v['risk']} |")
    return "\n".join(rows)


def main():
    if "--table" in sys.argv:
        print(table("high"))
        print()
        print(table("low"))
        return
    problems = build()
    for conf in ("high", "low"):
        cs = [v for v in CASES if v["confidence"] == conf]
        print(conf, "built:", {SHORT[s]: sum(1 for v in cs if v["set"] == s) for s in SETS},
              "labels:", {r: sum(v["result"] == r for v in cs) for r in ("angenommen", "abgelehnt")})
    for p in problems:
        print("PROBLEM:", p)
    if "--check" in sys.argv and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
