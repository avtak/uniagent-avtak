#!/usr/bin/env python3
"""Build the BLIND held-out test set for UniAgent Task 2: HOLDOUT.

Ten cases (h1..h10), each a copy of a practice case with ONE fact changed (or the minimum needed
to reach one rule situation), written WITHOUT reading the solver code (facts/rules/predict) or the
experiment notes, so that the solver cannot have been tuned to them. The wording deliberately
differs from the edge cases (no 'Conference Dinner', 'Tel Aviv/Israel', 'Bürodrehstuhl
ergonomisch', 'interne Teambesprechung'). TESTS ONLY: never used to tune prompts, rule cards or code.

    python3 experiments/holdout/tools/make_holdout.py            # build everything
    python3 experiments/holdout/tools/make_holdout.py --check    # build + verify, exit 1 on problems
    python3 experiments/holdout/tools/make_holdout.py --table    # print the markdown table

Output (mirrors the dataset layout, so tools/eval.py runs it with UNIAGENT_DATASETS):
    experiments/holdout/<set>/{inputs/<base>-h<N>/*.pdf, ground-truth.jsonl}          confidence high
    experiments/holdout-unsure/<set>/{inputs/..., ground-truth.jsonl}                 confidence low (not scored)

Tooling (text editor ops, the pure-Python PDF writer, row_like, field, ...) is imported from
experiments/edge-cases/tools/make_edge_cases.py and experiments/variants/tools/make_variants.py.
Unchanged PDFs are byte-copied from $UNIAGENT_DATASETS (default ~/dev/uniagent-code/cikm26/datasets).
"""
import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "edge-cases" / "tools"))
sys.path.insert(0, str(HERE.parents[1] / "variants" / "tools"))
import make_variants as mv  # noqa: E402
import make_edge_cases as me  # noqa: E402

OUT_HIGH = HERE.parent                                 # experiments/holdout
OUT_LOW = HERE.parents[1] / "holdout-unsure"           # experiments/holdout-unsure
DATASETS = mv.DATASETS
TRIP, PROC, EXP = mv.TRIP, mv.PROC, mv.EXP
SETS = [TRIP, PROC, EXP]
SHORT = {TRIP: "trip", PROC: "proc", EXP: "exp"}
apply_ops, row_like, eur, field, trip_row = me.apply_ops, me.row_like, me.eur, me.field, me.trip_row

CASES = []


def case(set_, base, n, result, confidence, changed, rule, quote, source, tests, risk, reason,
         edits=None, drop_docs=(), new_docs=None):
    CASES.append(dict(set=set_, base=base, n=n, id=f"{base}-h{n}", result=result, confidence=confidence,
                      changed=changed, rule=rule, quote=quote, source=source, tests=tests, risk=risk,
                      reason=reason, edits=edits or {}, drop_docs=list(drop_docs), new_docs=new_docs or {}))


# --------------------------------------------------------------------------- #
# BUSINESS TRIPS (base dienstreiseantrag-02, angenommen: Rotterdam by train)
# --------------------------------------------------------------------------- #
ANTRAG, BAHN, MAILC, REG = me.ANTRAG, me.BAHN, me.MAILC, me.REG
FLUG = "flug-angebot.pdf"


def _two(left, right, w=112):
    return (left + right.rjust(max(1, w - len(left)))) if left else right.rjust(w)


_FROW = " Kassel-Wilhelmshöhe → Rotterdam Centraal,                           1       7 % (D)               84,11 €                  90,00 €"
_FSUM = "                                                                                            Summe (brutto)                  180,00 €"


def flight_doc(dest, iata, price):
    """A flight offer in the layout of the train booking it replaces (no new arrows: WinAnsi)."""
    p = eur(price)
    rows = [
        _two("Dr. Mareike Voss", "Rhein-Main Flugreisen GmbH"),
        _two("", "Flughafenring 7"),
        _two("c/o Universität Kassel", "60549 Frankfurt am Main"),
        "Fachbereich 16",
        "34121 Kassel",
        "", "",
        _two("", "Angebotsnummer: 004518334127"),
        _two("", "Angebotsdatum: 05.09.2026"),
        _two("", "Status: Angebot, buchbar nach Genehmigung"),
        "", "",
        "Flugangebot",
        "Preisauskunft, noch keine Buchung – Buchung erfolgt erst nach Genehmigung der Dienstreise",
        "",
        " Beschreibung                                                  Menge           MwSt                   netto                  brutto",
        "",
        row_like(_FROW, f"Hin- und Rückflug Frankfurt (FRA) – {dest} ({iata}),", "1", "0 % (int.)", p, p, aligns="lrrrr"),
        f" Hinflug 09.11.2026, 11:05 Uhr; Rückflug {iata} – FRA 12.11.2026, 07:40 Uhr; Economy, je 1 Zwischenstopp",
        "",
        row_like(_FSUM, "Summe (brutto)", p),
        "",
        "Preisvergleich: Die Rückreise direkt nach Ende des Dienstgeschäfts (11.11.2026, 18:00 Uhr) wäre erst am",
        f"12.11.2026 möglich (kein Abendflug {iata}–FRA); der Tarif ist derselbe, es entstehen keine Mehrkosten.",
        "Dieses Dokument berechtigt nicht zur Reise.",
        "",
        "",
        "Mit freundlichen Grüßen",
        "Rhein-Main Flugreisen GmbH",
    ]
    return "\n".join(rows) + "\n"


def destination(city, ziel, kurz_land, org, street, plz_city, country, tax, mail_place, code, pauschale, price, iata):
    """Trip 02 moved to another (non-EU) destination: Antrag, acceptance mail, registration invoice
    and a flight offer instead of the train booking. Everything else (dates, fee 450,00 EUR,
    3 nights at 75,00 EUR, funding) is unchanged. Returns (edits, new_docs, drop_docs)."""
    total = 450 + price + 225 + 60
    edits = {
        ANTRAG: [
            ("setline", r"^Reiseziel:", field("Reiseziel:", ziel)),
            ("rep_all", "NordSys", "MeridianSys"),
            ("setline", r"^Verkehrsmittel:", field("Verkehrsmittel:", "Flug, Economy (An- und Abreisetag)")),
            ("setline", r"^A1-Bescheinigung:", field("A1-Bescheinigung:", "nicht erforderlich (Reiseziel außerhalb der EU)")),
            ("setline", r"^ Bahn Kassel–Rotterdam", trip_row(f"Flug Frankfurt–{city}, Hin- und Rückflug, Economy", 1, eur(price))),
            ("rep", "(Pauschale NL)", f"(Pauschale {pauschale})"),
            ("sub", r"Summe \(Schätzung\)[ ]+(?P<x>915,00 €)", eur(total)),
            ("rep", "für die Niederlande", kurz_land),
        ],
        MAILC: [
            ("rep_all", "NordSys", "MeridianSys"),
            ("rep_all", "nordsys2026", "meridiansys2026"),
            ("rep", "held in Rotterdam, the Netherlands,", f"held in {mail_place},"),
            ("rep", "seeing you in Rotterdam", f"seeing you in {city}"),
        ],
        REG: [
            ("rep_all", "NordSys", "MeridianSys"),
            ("rep", "c/o Symposia Events B.V.", org),
            ("rep", "Weena 505", street),
            ("rep", "3013 AL Rotterdam", plz_city),
            ("rep", "Niederlande", country),
            ("rep", "VAT NL812449770B01", tax),
            ("rep", "10–11 November 2026, Rotterdam", f"10–11 November 2026, {city}"),
        ],
    }
    return edits, {FLUG: (flight_doc(city, iata, price), BAHN)}, [BAHN]


_RULE_LIST = ("„Es wird darauf hingewiesen, dass Dienstreisen in die Russische Föderation, in die Ukraine, nach Belarus, "
              "Moldau- die Gebiete im Süden und Osten, die an die Ukraine grenzen, Niger, Iran, Israel, in die "
              "Palästinensischen Gebiete und Libanon bis auf Weiteres nicht genehmigt werden.“")

# ---- h1: Beirut, Libanon --------------------------------------------------- #
e, nd, dd = destination("Beirut", "Beirut, LIBANON", "für den Libanon", "c/o Levant Congress Services s.a.r.l.",
                        "Rue Hamra 214", "1103 2090 Beirut", "Libanon", "Tax ID LB-0038271", "Beirut, Lebanon",
                        "LB", "LB", 640, "BEY")
case(
    TRIP, "dienstreiseantrag-02", 1, "abgelehnt", "high",
    "Destination Rotterdam (NL, train) → Beirut, LIBANON (flight FRA–BEY 640,00 €, estimate 915,00 € → 1.375,00 €); conference renamed MeridianSys 2026; organiser address in Beirut; A1 line 'nicht erforderlich (Reiseziel außerhalb der EU)'",
    "Business trips to Lebanon are not approved",
    _RULE_LIST,
    "`dienstreisemanagement.md` (Wichtige Hinweise zu Ihrer Dienstreisegenehmigung)",
    "the list of destinations that are not approved (country named in the Antrag, the mail and the invoice)",
    "High: the list names 'Libanon' plainly; currency of the list in 2026/27 is UNVERIFIED but the page is the only source. The destination change forces several edits (flight instead of train, organiser address); all are consequences of the one fact",
    "Reiseziel ist Beirut, Libanon. Nach der Seite Dienstreisemanagement der Universitaet Kassel werden Dienstreisen in den Libanon bis auf Weiteres nicht genehmigt; Kosten, Termin und Unterlagen sind sonst in Ordnung. Geaendert gegenueber dienstreiseantrag-02: Reiseziel Beirut statt Rotterdam (Flug statt Bahn).",
    e, new_docs=nd, drop_docs=dd,
)

# ---- h2: Lagos, Nigeria (near miss for 'Niger') ---------------------------- #
e, nd, dd = destination("Lagos", "Lagos, NIGERIA", "für Nigeria", "c/o Atlantic Events Ltd.",
                        "14 Adeola Odeku Street", "Victoria Island, Lagos", "Nigeria", "Tax ID NG-24418830",
                        "Lagos, Nigeria", "NG", "NG", 640, "LOS")
case(
    TRIP, "dienstreiseantrag-02", 2, "angenommen", "high",
    "Destination Rotterdam (NL, train) → Lagos, NIGERIA (flight FRA–LOS 640,00 €, estimate 1.375,00 €), otherwise the same edits as h1",
    "Nigeria is not on the list of destinations that are not approved (the list names Niger, not Nigeria)",
    _RULE_LIST + " (Nigeria steht nicht darin)",
    "`dienstreisemanagement.md`",
    "string match of the not-approved list against the destination: 'Niger' is a prefix of 'Nigeria'. Pair with h1 (same edits, other country)",
    "High on the page: Niger is listed, Nigeria is not. The real-world security situation of Nigeria is irrelevant to the page; the ARV rate for Nigeria is not on a corpus page, the hotel rate (75,00 €) is far below any ARV rate, so no cap problem arises",
    "Reiseziel ist Lagos, Nigeria. Nigeria steht nicht auf der Liste der Laender, in die Dienstreisen nicht genehmigt werden (genannt ist Niger, nicht Nigeria). Der Antrag ist rechtzeitig, A1 ist ausserhalb der EU nicht erforderlich, der Preisvergleich zum Flug liegt bei, Uebernachtung 75,00 EUR je Nacht, Finanzierung aus Drittmitteln. Geaendert gegenueber dienstreiseantrag-02: Reiseziel Lagos statt Rotterdam (Flug statt Bahn).",
    e, new_docs=nd, drop_docs=dd,
)

# ---- h3: Gala-Abend as a cost row ------------------------------------------ #
case(
    TRIP, "dienstreiseantrag-02", 3, "abgelehnt", "high",
    "Gala-Abend not booked → booked and claimed: new cost row 'Gala-Abend der Tagung (Festbankett), 10.11.2026' 70,00 € in the Antrag (estimate 915,00 € → 985,00 €) and as an extra line of the registration invoice (450,00 € → 520,00 €)",
    "Costs of evening and accompanying programmes are not reimbursable",
    "„Kosten für Begleit- und Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht erstattungsfähig.“ (Hinweis der Genehmigungsmail des Reisemanagements; Bewirtungskostenrichtlinie: „Rahmenprogramme, Finanzierung ggf. über Teilnahmegebühren möglich“)",
    "decision-trail dienstreiseantrag-02/genehmigt.pdf; `finanzbuchhaltung-und-steuern.md` (Nicht erstattungsfähige Aufwendungen)",
    "an evening programme claimed under a name that is not 'Conference Dinner'; the amount is added to the total",
    "The first quote is from the approval notice of the practice trip, not a corpus page (the page has only 'Rahmenprogramme'). Staff might cut the row instead of rejecting the whole request; the task has two labels and the request as filed claims a non-reimbursable cost",
    "Der Antrag macht zusaetzlich den Gala-Abend der Tagung (Festbankett, 70,00 EUR) geltend (Schaetzung 985,00 EUR statt 915,00 EUR); die Registrierungsrechnung weist ihn als gebucht aus. Kosten fuer Begleit- und Abendprogramme sind grundsaetzlich nicht erstattungsfaehig, der Antrag ist so nicht genehmigungsfaehig. Geaendert gegenueber dienstreiseantrag-02: der Gala-Abend ist gebucht und beantragt (vorher nicht).",
    {ANTRAG: [
        ("insert_after", r"^ Konferenzregistrierung \(Early Bird",
         "\n" + trip_row("Gala-Abend der Tagung (Festbankett), 10.11.2026", 1, "70,00 €")),
        ("sub", r"Summe \(Schätzung\)[ ]+(?P<x>915,00 €)", "985,00 €"),
    ], REG: [
        ("insert_after", r"^[ ]+charge\)$",
         "\n" + row_like(" Full registration, early bird, member rate                            1          0%                450,00 €               450,00 €",
                         "Gala evening (Festbankett), 10 Nov 2026", "1", "0%", "70,00 €", "70,00 €", aligns="lrrrr")),
        ("sub", r"Summe \(netto\)[ ]+(?P<x>450,00 €)", "520,00 €"),
        ("sub", r"Summe \(brutto\)[ ]+(?P<x>450,00 €)", "520,00 €"),
        ("sub", r"^Betrag[ ]+(?P<x>450,00 €)", "520,00 €"),
        ("setline", r"^Die Registrierung schließt den Zugang zu allen Sessions sowie die Mittagsverpflegung",
         "Die Registrierung schließt den Zugang zu allen Sessions sowie die Mittagsverpflegung an beiden Konferenztagen ein."),
        ("setline", r"^Conference Dinner \(65,00 EUR\) wurde nicht gebucht",
         "Der Gala-Abend der Tagung (Festbankett, 70,00 EUR) wurde zusätzlich gebucht."),
    ]},
)

# ---- h4: fee includes the evening reception (near miss) -------------------- #
case(
    TRIP, "dienstreiseantrag-02", 4, "angenommen", "high",
    "No separate dinner cost: the cost row reads 'Teilnahmegebühr inkl. Abendempfang (Early Bird, Mitglied)' 450,00 € (unchanged), the invoice line 'Full registration incl. welcome reception' and the note that the fee includes the reception on 10.11.; the sentence that the optional dinner was not booked is removed",
    "A fee that includes an evening reception is a conference fee (Pauschale/Teilnahmegebühr), not a separately claimed evening programme",
    "„Die auf den Rechnungen ausgewiesenen Verpflegungskosten für Mittag- uns Abendverpflegung werden im Rahmen von Reisekosten nur dann erstattet, wenn es sich nachweislich um eine notwendige Pauschale handelt (Tagungspauschale etc.).“ and „Rahmenprogramme, Finanzierung ggf. über Teilnahmegebühren möglich“",
    "`dienstreisemanagement.md` (Informationen rund um die Kosten); `finanzbuchhaltung-und-steuern.md`",
    "a keyword check on 'Abend' in the cost table or invoice would reject; the amount (450,00 €) and every other fact equal the accepted base",
    "Medium-high: 'Abendempfang' could be read as an evening programme, but it is part of the mandatory fee and no separate cost is claimed; the page allows exactly this route (fee includes the programme). Pair with h3",
    "Die Teilnahmegebuehr (450,00 EUR) schliesst den Abendempfang ein; es gibt keine gesonderte Kostenposition fuer ein Abend- oder Rahmenprogramm. Die Gebuehr ist eine Tagungspauschale und erstattungsfaehig. Alle uebrigen Angaben entsprechen dem genehmigten dienstreiseantrag-02. Geaendert gegenueber dienstreiseantrag-02: die Teilnahmegebuehr schliesst einen Abendempfang ein (vorher: Conference Dinner nicht gebucht).",
    {ANTRAG: [
        ("setline", r"^ Konferenzregistrierung \(Early Bird",
         trip_row("Teilnahmegebühr inkl. Abendempfang (Early Bird, Mitglied)", 1, "450,00 €")),
    ], REG: [
        ("rep", "Full registration, early bird, member rate", "Full registration incl. welcome reception, early bird, member rate"),
        ("setline", r"^Die Registrierung schließt den Zugang zu allen Sessions sowie die Mittagsverpflegung",
         "Die Registrierung schließt den Zugang zu allen Sessions, die Mittagsverpflegung an beiden Konferenztagen sowie den"),
        ("setline", r"^Conference Dinner \(65,00 EUR\) wurde nicht gebucht", "Abendempfang am 10.11.2026 ein."),
    ]},
)

# ---- h10: Minsk, 'Weißrussland' (synonym of Belarus) ----------------------- #
e, nd, dd = destination("Minsk", "Minsk, WEISSRUSSLAND", "für Weißrussland", "c/o Neman Kongress UP",
                        "Nezavisimosti Ave. 68", "220050 Minsk", "Weißrussland", "UNP 190455312",
                        "Minsk", "BY", "BY", 640, "MSQ")
case(
    TRIP, "dienstreiseantrag-02", 10, "abgelehnt", "high",
    "Destination Rotterdam (NL, train) → Minsk, WEISSRUSSLAND (flight FRA–MSQ 640,00 €, estimate 1.375,00 €); same edits as h1; the country is named only as 'Weißrussland' (never 'Belarus') in the Antrag and the invoice, the acceptance mail says only 'Minsk'",
    "Business trips to Belarus are not approved; Weißrussland is the German synonym of Belarus",
    _RULE_LIST,
    "`dienstreisemanagement.md`",
    "string match of the not-approved list: the list says 'Belarus', the documents say 'Weißrussland' / 'Minsk' (a check on the list's spelling or on the Antrag only misses it)",
    "High: Weißrussland is Belarus. A reader who knows Minsk is in Belarus rejects; one who matches strings accepts. The documents never contain the word Belarus",
    "Reiseziel ist Minsk, Weissrussland, also Belarus. Dienstreisen nach Belarus werden nach der Seite Dienstreisemanagement der Universitaet Kassel bis auf Weiteres nicht genehmigt. Kosten, Termin und Unterlagen sind sonst in Ordnung. Geaendert gegenueber dienstreiseantrag-02: Reiseziel Minsk statt Rotterdam (Flug statt Bahn).",
    e, new_docs=nd, drop_docs=dd,
)

# --------------------------------------------------------------------------- #
# PROCUREMENT (base beschaffungsantrag-02, angenommen: single offer 673,00 € net, direct award)
# --------------------------------------------------------------------------- #
OFFER, MAIL = me.OFFER, me.MAIL
_O1 = " Lötstation digital 80 W mit Ablage                                    2            189,00 €              378,00 €"


def goods_ops(supplier, web, street, plz, tel, mailaddr, row1, row2_drop, row3, net, vat, gross, extra_line):
    """Offer + e-mail edits for a single-supplier order; row1 = (text, qty, unit) of the first item."""
    txt, qty, unit = row1
    o = [
        ("rep_all", "Löthaus Dannwolf e.K.", supplier),
        ("rep", "Ostenallee 58", street),
        ("rep", "59065 Hamm", plz),
        ("rep", "02381 97 21 60", tel),
        ("rep", "shop@dannwolf-loethaus.de", mailaddr),
        ("setline", r"^ Lötstation digital 80 W mit Ablage",
         row_like(_O1, txt, str(qty), eur(unit), eur(qty * unit))),
    ]
    if row2_drop:
        o.append(("drop", r"^ Heißluft-Rework-Station 700 W"))
    if row3:
        o.append(("rep", "Entlötpumpe Metall, antistatisch", row3))
    o += [
        ("sub", r"Summe netto[ ]+(?P<x>673,00 €)", eur(net)),
        ("sub", r"zzgl\. 19 % USt\.[ ]+(?P<x>127,87 €)", eur(vat)),
        ("sub", r"Angebotssumme brutto[ ]+(?P<x>800,87 €)", eur(gross)),
    ]
    if extra_line:
        o.append(("insert_after", r"^Versand innerhalb von 3 Werktagen", extra_line))
    return o


# ---- h5: Seminarstuhl from an ordinary web shop ---------------------------- #
_N5, _V5 = 8 * 59 + 4 * 12.5, round((8 * 59 + 4 * 12.5) * 0.19, 2)
case(
    PROC, "beschaffungsantrag-02", 5, "abgelehnt", "high",
    "Goods: soldering stations, hot-air station, desoldering pumps (Löthaus Dannwolf, 673,00 € net) → 8 × 'Seminarstuhl, Holzschale, stapelbar' (59,00 € net) and 4 felt glide sets from the online shop 'Sitzgut Direkt e.K.' (522,00 € net, 621,18 € gross); the mail still says the order value is under 1.000 € and a single offer was obtained",
    "Seminar chairs (Holzschalenstühle) are a framework-contract product group and must be ordered exclusively from the framework partner, whatever the amount",
    "„Die Universität Kassel hat zusammen mit den Hessischen Hochschulen einen Rahmenvertrag über die Lieferung von Seminarstühlen bzw. Holzschalenstühlen mit der Firma Malscher SitzMöbel Stöcklein GmbH abgeschlossen.“ and „Sollte man ein Produkt bestellen wollen, zu dem ein Rahmenvertrag besteht, muss man dieses Produkt ausschließlich beim Rahmenvertragspartner bestellen“",
    "`rahmenvertraege.md` (Seminarstühle: Malscher SitzMöbel Stöcklein GmbH); `beschaffung.md`",
    "framework-contract product group recognised by a word not in the base (Seminarstuhl / Holzschale) while the direct-award sentence ('unter 1.000 €') is true and may tempt an accept",
    "High: the page names Seminarstühle and Holzschalenstühle; the order is by e-mail from an online shop, not via WPS from the framework partner. The felt glide set is accessories (not necessarily a framework item) but the chairs alone decide",
    "Der Auftrag umfasst acht Seminarstuehle (Holzschale, stapelbar) aus einem Onlineshop (Sitzgut Direkt e.K.). Fuer Seminarstuehle besteht ein Rahmenvertrag (Malscher SitzMoebel Stoecklein GmbH); solche Produkte sind ausschliesslich beim Rahmenvertragspartner ueber WPS zu bestellen. Dass der Auftragswert mit 522,00 EUR netto unter 1.000 EUR liegt, hebt diese Bindung nicht auf. Geaendert gegenueber beschaffungsantrag-02: Seminarstuehle vom Onlineshop statt Loetstationen.",
    {OFFER: goods_ops("Sitzgut Direkt e.K.", "www.sitzgut-direkt.de", "Hafenstraße 31", "26122 Oldenburg", "0441 38 20 91",
                      "service@sitzgut-direkt.de", ("Seminarstuhl, Holzschale, stapelbar", 8, 59.0), True,
                      "Stuhlgleiter Filz, 4er-Set", _N5, _V5, round(_N5 + _V5, 2),
                      "Bestellung über unseren Onlineshop www.sitzgut-direkt.de."),
     MAIL: [
         ("setline", r"^[ ]+Direktauftrag Lötstationen Werkstatt", "  Direktauftrag Seminarstühle FG Elektrische Messtechnik"),
         ("setline", r"^[ ]+für die Elektronikwerkstatt des Fachgebiets bitte ich",
          "  für den Seminarraum des Fachgebiets bitte ich um Bestellung der folgenden Artikel im Onlineshop Sitzgut Direkt"),
         ("setline", r"^[ ]+e\.K\. gemäß beiliegendem Angebot",
          "  e.K. (www.sitzgut-direkt.de) gemäß beiliegendem Angebot DW-A-5518 vom 03.03.2027:"),
         ("setline", r"^[ ]+2 × Lötstation digital", "  8 × Seminarstuhl, Holzschale, stapelbar, je 59,00 € netto"),
         ("drop", r"^[ ]+1 × Heißluft-Rework-Station"),
         ("setline", r"^[ ]+4 × Entlötpumpe", "  4 × Stuhlgleiter Filz, 4er-Set, je 12,50 € netto"),
         ("sub", r"Summe (?P<x>673,00 € netto, 800,87 €) brutto\.", f"{eur(_N5)} netto, {eur(round(_N5 + _V5, 2))}"),
         ("sub", r"^[ ]+(?P<x>Elektronikwerkstatt), Fachgebiet", "Sekretariat"),
     ]},
)

# ---- h6: Laborhocker ESD from a lab supplier (near miss, unsure) ----------- #
_N6 = 4 * 98 + 245 + 50
_V6 = round(_N6 * 0.19, 2)
case(
    PROC, "beschaffungsantrag-02", 6, "angenommen", "low",
    "First item: 2 × Lötstation (189,00 €) → 4 × 'Laborhocker ESD, höhenverstellbar, Gleiter' (98,00 € net); supplier renamed 'Labortechnik Dannwolf e.K.'; hot-air station and desoldering pumps unchanged; 687,00 € net, 817,53 € gross",
    "A laboratory stool is not an office swivel chair, seminar chair or office furniture; no framework contract exists for it, so a direct award under 1.000 € net with one offer is allowed",
    "„Der Abschluss der Rahmenverträge ermöglicht den einzelnen Bereichen Ihre Bedarfe aus den jeweiligen Rahmensortimenten ohne das Einholen von Vergleichsangeboten zu decken.“ / „Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ (the list: Büromaterial, PC's/Notebooks und Monitore, Büropapiere, Bürodrehstühle, Seminarstühle, Büromobiliar, Kopiergeräte, Software von Microsoft)",
    "`rahmenvertraege.md` (list of framework contracts; Büromöbel 'ausgenommen Bürodreh-, Besucher- und Seminarstühle'); `nachhaltiges-catering.md` / `beschaffung.md` (1.000 Euro)",
    "over-matching: 'Stuhl/Hocker' as framework furniture (a word-list check on 'Hocker' or 'Stuhl') against a lab article that is on no list",
    "LOW: a stool is furniture, and 'Büromobiliar' is a framework group; whether a lab stool with ESD protection counts as office furniture is a judgement the page does not settle. I read 'Büromobiliar' as office furniture and a lab stool as laboratory equipment. Not scored",
    "Vier Laborhocker (ESD, hoehenverstellbar) kommen zusammen mit einer Heissluft-Rework-Station und Entloetpumpen von einem Laborausstatter; der Gesamtwert liegt bei 687,00 EUR netto, unter 1.000 EUR, ein Angebot genuegt (Direktvergabe), die Kostenstellenbevollmaechtigte hat in Kopie beauftragt. Laborhocker sind kein Bueromobiliar oder Stuhl mit Rahmenvertrag. Geaendert gegenueber beschaffungsantrag-02: eine Position (Laborhocker statt Loetstationen).",
    {OFFER: goods_ops("Labortechnik Dannwolf e.K.", "", "Ostenallee 58", "59065 Hamm", "02381 97 21 60",
                      "shop@dannwolf-labortechnik.de", ("Laborhocker ESD, höhenverstellbar, Gleiter", 4, 98.0), False,
                      None, _N6, _V6, round(_N6 + _V6, 2), None),
     MAIL: [
         ("setline", r"^[ ]+Direktauftrag Lötstationen Werkstatt", "  Direktauftrag Laborausstattung Werkstatt FG Elektrische Messtechnik"),
         ("rep", "beim Löthaus Dannwolf", "bei Labortechnik Dannwolf"),
         ("rep", "der folgenden Geräte", "der folgenden Artikel"),
         ("setline", r"^[ ]+2 × Lötstation digital", "  4 × Laborhocker ESD, höhenverstellbar, Gleiter, je 98,00 € netto"),
         ("sub", r"Summe (?P<x>673,00 € netto, 800,87 €) brutto\.", f"{eur(_N6)} netto, {eur(round(_N6 + _V6, 2))}"),
     ]},
)

# --------------------------------------------------------------------------- #
# EXPENSE REIMBURSEMENT (base auslagenerstattung-02, angenommen: hardware-store till receipt)
# The receipt is written from scratch in the layout of the practice receipt (beleg-1.pdf).
# --------------------------------------------------------------------------- #
def till(shop, street, plz, tel, items, bon, steuernr, vat_lines, total, paid, note):
    lines = [f" {shop}", f" {street}", f" {plz}", f" Tel. {tel}", ""]
    for name, qty, unit, amount in items:
        lines.append(name)
        lines.append(f"{qty} ST x {unit}".ljust(32) + amount)
        lines.append("")
    lines += [f"SUMME EUR".ljust(32) + total, "", f" BAR {paid[0]}", f" RÜCKGELD {paid[1]}", ""]
    lines += [f" {v}" for v in vat_lines]
    lines += [f" {bon}", f" St.-Nr. {steuernr}", " VIELEN DANK FÜR IHREN EINKAUF", "", ""]
    return "\n".join(lines + note) + "\n"


BELEG = "beleg-1.pdf"

# ---- h7: Weihnachtsfeier of the department --------------------------------- #
case(
    EXP, "auslagenerstattung-02", 7, "abgelehnt", "high",
    "Till receipt: hardware store with article numbers (19,86 €) → bakery till receipt with named items (40 Brötchen, 2 Kannen Kaffee, 4 Orangensaft; 49,80 €); handwritten note 'Kabelbinder + Schrumpfschlauch für Versuchsstand' → 'Brötchen + Getränke für die Weihnachtsfeier des Fachgebiets (14 Beschäftigte des Fachgebiets)'",
    "Catering for a Christmas party of an individual department is not reimbursable (social events; internal celebrations of single Fachgebiete)",
    "„Nicht erstattungsfähige Aufwendungen sind: […] Bewirtungskosten für sonstige Veranstaltungen geselliger Art (z. B. Betriebsausflüge, Verabschiedungen, Weihnachts- oder Geburtstagsfeiern, Dienstjubiläen, Verabschiedungen)“ and „Bewirtungen, an denen keine externen Personen teilgenommen haben,“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie, Nicht erstattungsfähige Aufwendungen)",
    "hospitality rule via the occasion (Weihnachtsfeier) with the participants only implied (employees of the Fachgebiet); wording differs from 'interne Teambesprechung'",
    "High: Weihnachtsfeier is named on the page and the group is staff only. The sentence 'keine externen Personen' is not written on the receipt, only '14 Beschäftigte des Fachgebiets'",
    "Der Bon einer Baeckerei ueber 49,80 EUR (Broetchen, Kaffee, Saft) traegt den Vermerk, dass er fuer die Weihnachtsfeier des Fachgebiets mit 14 Beschaeftigten angefallen ist. Bewirtungskosten fuer gesellige Veranstaltungen wie Weihnachtsfeiern und Bewirtungen ohne externe Personen sind nach der Bewirtungskostenrichtlinie nicht erstattungsfaehig. Geaendert gegenueber auslagenerstattung-02: Bewirtungsbon fuer die Weihnachtsfeier statt Baumarktbon.",
    new_docs={BELEG: (till(
        "LANDBÄCKEREI TIEDEMANN", "Bahnhofstraße 22", "37269 Eschwege", "05651 30 18 442",
        [("BROETCHEN GEMISCHT", 40, "0,65", "26,00"), ("ORANGENSAFT 1,0 L", 4, "2,20", "8,80"),
         ("KAFFEE KANNE 1,0 L", 2, "7,50", "15,00")],
        "BON 3186 KASSE 01 17.12.27 07:52", "20/218/66310",
        ["MWST 7% NETTO 24,30 MWST 1,70", "MWST 19% NETTO 20,00 MWST 3,80"], "49,80", ("50,00", "0,20"),
        [" Brötchen + Getränke für die", " Weihnachtsfeier des Fachgebiets", " (14 Beschäftigte des Fachgebiets)", " (T. Brockmann)"]), BELEG)},
)

# ---- h8: external visitors (DFG reviewers) --------------------------------- #
case(
    EXP, "auslagenerstattung-02", 8, "angenommen", "high",
    "As h7 in layout; items changed to rolls (12), coffee (2 pots), mineral water (4), fruit bowl (39,70 €); the note: 'Bewirtung Gutachterbesuch DFG am 12.10.27, 3 externe Gutachter (names, institutions) + 1 Beschäftigte' with the guests marked",
    "Coffee, water, fruit and pastries offered to guests of the university are running operating costs, not hospitality costs",
    "„Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen und damit auch aus Landesmitteln finanzierbar sind die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden.“; for real hospitality: „Der Teilnehmerkreis ist mit einer Liste der Namen der bewirteten Personen schriftlich anzugeben. Dabei sollen Gäste und Universitätsbedienstete gesondert gekennzeichnet sein.“",
    "`finanzbuchhaltung-und-steuern.md` (Bewirtungskostenrichtlinie)",
    "pair with h7: same kind of receipt, but the guests are external (and named, marked as Gast (extern)); a check that rejects any catering receipt fails here",
    "Medium-high: the items are courtesies (Gebäck, Kaffee, Wasser, Obst); a strict reader may treat the visit as Bewirtung and demand an Bewirtungsbeleg made out to the university (a till receipt cannot give it). The purpose (DFG Gutachterbesuch = Einwerbung von Drittmitteln) and a participant list with the guests marked are on the receipt note",
    "Der Bon einer Baeckerei ueber 39,70 EUR (Broetchen, Kaffee, Wasser, Obst) ist mit dem Vermerk versehen, dass er fuer den Besuch von drei externen DFG-Gutachtern am 12.10.2027 angefallen ist; die Teilnehmer sind namentlich genannt, die Gaeste als extern gekennzeichnet, eine Beschaeftigte nahm teil. Kaffee, Wasser, Obst und Gebaeck fuer Gaeste der Universitaet sind laufende Betriebsaufwendungen und erstattungsfaehig; Anlass und Teilnehmerkreis sind dargelegt. Geaendert gegenueber auslagenerstattung-02: Bon fuer die Bewirtung externer Gutachter statt Baumarktbon.",
    new_docs={BELEG: (till(
        "CAFÉ & BÄCKEREI HOFMANN", "Obermarkt 9", "37213 Witzenhausen", "05542 61 07 255",
        [("BROETCHEN GEMISCHT", 12, "0,70", "8,40"), ("KAFFEE KANNE 1,0 L", 2, "7,50", "15,00"),
         ("MINERALWASSER 0,75 L", 4, "1,60", "6,40"), ("OBSTSCHALE", 1, "9,90", "9,90")],
        "BON 2054 KASSE 02 12.10.27 09:15", "20/218/70512",
        ["MWST 7% NETTO 17,10 MWST 1,20", "MWST 19% NETTO 17,98 MWST 3,42"], "39,70", ("40,00", "0,30"),
        [" Bewirtung Gutachterbesuch DFG", " am 12.10.27, Besprechung Antrag", " Teilnehmer:",
         " Prof. M. Lindqvist, Uni Bremen (extern)", " Dr. A. Rademacher, TU Chemnitz (extern)",
         " Prof. S. Okonjo, HS Fulda (extern)", " Dr. K. Weidemann, Beschäftigte", " (K. Weidemann)"]), BELEG)},
)

# ---- h9: coffee and tea for the office (staff consumption) ----------------- #
case(
    EXP, "auslagenerstattung-02", 9, "abgelehnt", "high",
    "Till receipt: hardware store (19,86 €) → supermarket till receipt with named items (coffee, tea, milk, sugar; 43,66 €); handwritten note 'Kaffee, Tee, Milch für die Kaffeekasse der Arbeitsgruppe (Büro E 2.14)'",
    "Coffee and tea are operating costs only when offered to guests of the university; for the staff themselves they are not reimbursable, and purchases belong in the SAP procurement",
    "„Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen […] sind die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden.“ and „Beschaffungen müssen immer über das SAP-Beschaffungsprogramm bestellt werden. In Ausnahmefällen kann es sein, dass Angestellte der Universität kleinere, zeitlich dringende Anschaffungen selbst besorgt haben“",
    "`finanzbuchhaltung-und-steuern.md` (Kostenerstattung; Bewirtungskostenrichtlinie); practice case auslagenerstattung-07 (tea kitchen supplies, abgelehnt)",
    "staff consumption without any 'Bewirtung' or 'Feier' word: no occasion, no event, just supplies 'für die Kaffeekasse'; not urgent, not a guest courtesy",
    "High, by analogy with the practice case 07 whose gold reason rejects coffee and tea for the staff. The page has no sentence that says in so many words that coffee for staff is not reimbursable; it follows from the guests-only wording and from the exceptional character of private purchases",
    "Der Supermarktbon ueber 43,66 EUR (Kaffee, Tee, Milch, Zucker) ist mit dem Vermerk versehen, dass die Waren fuer die Kaffeekasse der Arbeitsgruppe im Buero gekauft wurden. Kaffee und Tee sind nach der Bewirtungskostenrichtlinie nur als Geste gegenueber Gaesten der Universitaet Betriebsaufwand; fuer die Beschaeftigten selbst sind sie nicht erstattungsfaehig, und es handelt sich auch nicht um eine kleine, dringende Anschaffung. Geaendert gegenueber auslagenerstattung-02: Verpflegung fuer das Buero statt Baumarktbon.",
    new_docs={BELEG: (till(
        "SUPERMARKT HEIDENREICH", "Lange Straße 5", "34117 Kassel", "0561 70 31 906",
        [("KAFFEE GEMAHLEN 500 G", 4, "6,49", "25,96"), ("TEE SORTIMENT 40 BTL", 3, "3,29", "9,87"),
         ("H-MILCH 1,5% 1 L", 6, "1,09", "6,54"), ("ZUCKER 1 KG", 1, "1,29", "1,29")],
        "BON 3318 KASSE 02 14.06.27 16:20", "26/218/90417",
        ["MWST 7% NETTO 40,80 MWST 2,86"], "43,66", ("50,00", "6,34"),
        [" Kaffee, Tee, Milch für die", " Kaffeekasse der Arbeitsgruppe", " (Büro E 2.14)", " (J. Bremer)"]), BELEG)},
)


# --------------------------------------------------------------------------- #
# Build and verify (same as the edge-case script)
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
            if pdf.name in v["drop_docs"] or pdf.name in v["new_docs"]:
                continue
            target = dst / pdf.name
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
    # no arrow glyphs and no forbidden reuse of the edge-case wording
    for bad in ("Tel Aviv", "Israel", "Bürodrehstuhl ergonomisch", "interne Teambesprechung"):
        if bad in got:
            problems.append(f"{v['id']}/{target.name}: contains edge-case wording {bad!r}")


def table(confidence="high"):
    rows = ["| Case | Base | Changed fact (old → new) | Expected | Rule, quote, source | Confidence | Tests | Risk |",
            "|---|---|---|---|---|---|---|---|"]
    for v in sorted(CASES, key=lambda c: c["n"]):
        if v["confidence"] != confidence:
            continue
        rows.append(f"| `{v['id']}` ({SHORT[v['set']]}) | `{v['base']}` | {v['changed']} | {v['result']} | "
                    f"{v['quote']} ({v['source']}) | {v['confidence']} | {v['tests']} | {v['risk']} |")
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
