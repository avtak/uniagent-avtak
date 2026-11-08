#!/usr/bin/env python3
"""Build the third BLIND proposal set for UniAgent Task 2 (15 cases, the author picks 10).

Written blind: without the solver (facts.py, rules.py, predict.py, parsing.py, case_tools.py),
its tests, the earlier experiment sets or the docs that describe them. Sources used: the
policy pages in the University of Kassel policy pages (not included here), the organisers' practice data (READMEs, ground
truth, decision trails) and grep over the retrieval corpora. Every label rests on a rule
quoted verbatim in experiments/blind3-proposals/PROPOSALS.md.

Only the PDF writer and the pdftotext call are reused from experiments/blind2/tools/make_blind2.py
(pure Python, base-14 fonts, WinAnsi, one text line per line).

    python3 experiments/blind3/tools/make_blind3.py           # build + verify
    python3 experiments/blind3/tools/make_blind3.py --table   # print the proposals table

Output (overwritten): experiments/blind3-proposals/<set>/{inputs/<case>/*.pdf,
ground-truth.jsonl} and experiments/blind3-proposals/PROPOSALS.md.
"""
import datetime
import json
import pathlib
import random
import re
import shutil
import subprocess
import sys
import zlib
from decimal import Decimal, ROUND_HALF_UP

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "blind3-proposals"
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

A4 = (595.28, 841.89)
RECEIPT = (226.77, 700.0)


# --------------------------------------------------------------------------- #
# Minimal PDF writer (reused from experiments/blind2/tools/make_blind2.py)
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


def write_pdf(path, text, size=A4, title="", font="Courier", margin=28.0, jitter=0.0,
              producer="", creator=""):
    w, h = size
    pages = [p.strip("\n").split("\n") for p in text.split("\f") if p.strip()]
    longest = max(len(l.rstrip()) for p in pages for l in p)
    fs = min(9.0, (w - 2 * margin) / (0.6 * max(longest, 1)))
    cw = 0.6 * fs
    lead = fs * 1.3
    cap = int((h - 2 * margin) / lead)
    chunks = []
    for p in pages:
        for k in range(0, len(p), cap):
            chunks.append(p[k:k + cap])
    rnd = random.Random(str(path))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(len(chunks)))
    objs.append(f"<< /Type /Pages /Count {len(chunks)} /Kids [{kids}] >>".encode())
    objs.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{font} /Encoding /WinAnsiEncoding >>".encode())
    objs.append(b"<< /Title (" + _pdf_str(title) + b") /Producer (" + _pdf_str(producer)
                + b") /Creator (" + _pdf_str(creator) + b") >>")
    for i, lines in enumerate(chunks):
        content = bytearray()
        for j, line in enumerate(lines):
            line = line.rstrip()
            if not line:
                continue
            y = h - margin - fs - j * lead
            dx = rnd.uniform(-jitter, jitter) if jitter else 0.0
            if font == "Courier":
                segs = [(0, line)]
            else:  # proportional font: place each column segment at its monospace position
                segs = [(m.start(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", line)]
            for col, seg in segs:
                x = margin + dx + col * cw
                content += (f"BT /F1 {fs:.3f} Tf {x:.2f} {y:.2f} Td (".encode() + _pdf_str(seg)
                            + b") Tj ET\n")
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
    return len(chunks)


def pdftotext(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True,
                          text=True).stdout


# --------------------------------------------------------------------------- #
# Helpers: layout, money, dates
# --------------------------------------------------------------------------- #
def lr(left, right, w=104):
    return left + " " * max(3, w - len(left) - len(right)) + right


def kv(rows, k=28, indent=2):
    return "\n".join((" " * indent + a.ljust(k) + b) if a else (" " * (indent + k) + b) for a, b in rows)


def D(x):
    return Decimal(str(x))


def r2(x):
    return D(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def eur(x):
    s = f"{r2(x):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tot(*xs):
    return r2(sum(D(x) for x in xs))


def vat_split(gross, rate):
    """net and VAT contained in a gross amount"""
    net = r2(D(gross) / (1 + D(rate) / 100))
    return net, r2(D(gross) - net)


WD_S = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WD_L = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def dt(s):
    return datetime.date.fromisoformat(s)


def de(s):
    return dt(s).strftime("%d.%m.%Y")


def wd(s):  # "Mo 21.06.2027"
    return f"{WD_S[dt(s).weekday()]} {de(s)}"


def wdl(s):  # "Montag, 21.06.2027"
    return f"{WD_L[dt(s).weekday()]}, {de(s)}"


def wen(s):  # "Mon 21.06.2027"
    return f"{WD_EN[dt(s).weekday()]} {de(s)}"


# --------------------------------------------------------------------------- #
# Case registry
# --------------------------------------------------------------------------- #
CASES = []


def case(set_, cid, result, begruendung, docs, desc, rule, source, imitates, trap, conf):
    CASES.append(dict(set=set_, id=cid, result=result, begruendung=begruendung, docs=docs, desc=desc,
                      rule=rule, source=source, imitates=imitates, trap=trap, conf=conf))


def doc(name, text, **opts):
    return (name, text, opts)


UW = "Universität Wernstadt"
SAL = "Technische Hochschule Sallstedt"
SRC_DRM = "Uni-Kassel-Seite „Dienstreisemanagement“ (doc 32bc169e-4d0b-4931-9b72-bf425ec7311b)"
SRC_FIBU = "Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ (doc 74ae8556-feb0-4b84-a70e-9566acb8360b)"
SRC_BESCH = "Uni-Kassel-Seite „Beschaffung“ (doc 4bea4f9c-217e-42a8-afd3-beccd578adef)"
SRC_RV = "Uni-Kassel-Seite „Rahmenverträge“ (doc ed4468f8-7450-4152-a624-33503f78f919)"
SRC_CAT = "Uni-Kassel-Seite „Nachhaltiges Catering“ (doc 08143d1c-7e2f-4f9c-b6e0-42969f36852f)"
SRC_GF = "Uni-Kassel-Seite „Gerätefondsverfahren“ (doc 835ca50e-172f-4a99-9462-b58f6861a199)"
SRC_GLOS = "Uni-Kassel-Seite „Glossar Drittmittelbewirtschaftung“ (doc ab40fc4f-638f-4898-b501-40fc33916ac4)"
SRC_HRKG5 = "§ 5 HRKG (hessian-law doc jlr-NNLHE0000518BNN00000000011)"
SRC_HRKG14 = "§ 14 HRKG (hessian-law doc jlr-NNLHE0000518BNN00000000023)"
SRC_SAL = "README der Organisatoren (task-2-procurement-spot-check): Sallstedt-Fälle werden allein auf den Unterlagen entschieden"

HDR_OWA = "E-Mail – {who}@uni-wernstadt.de" + " " * 40 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox"


# =========================================================================== #
# BUSINESS TRIPS
# =========================================================================== #

# --------------------------------------------------------------------------- #
# c01  angenommen (trap): 1st class rail (> 2 h one way) + hotel over 80 EUR, justified
# --------------------------------------------------------------------------- #
def c01():
    rail = D("89.90")
    rail_sum = tot(rail, rail)
    hotel = D("94.00")
    hotel_sum = tot(hotel, hotel)
    fee = D("240.00")
    total = tot(rail_sum, hotel_sum, fee)
    assert total == D("607.80")
    rail_net, rail_vat = vat_split(rail_sum, 7)

    fiori = "\n".join([
        lr("SAP    Meine Reiseanträge", "Dr. Malte Quernheim   (MQ)", 112),
        lr("<  Zurück      Reiseantrag 4100027713", "Status: Zur Genehmigung gesendet", 112),
        "",
        "Kiel – 18. Kolloquium Maritime Strömungstechnik (KMS 2027)",
        "Reisender: Dr. Malte Quernheim   ·   Personalnr. 00418822   ·   Fachgebiet Strömungsmechanik, FB 15 Maschinenbau",
        f"Angelegt am {de('2027-05-10')} 09:41   ·   Gesendet am {de('2027-05-10')} 09:58   ·   Genehmiger: Prof. Dr. Annegret Vollbrecht",
        "",
        "Allgemeine Daten   |   Reiseverlauf   |   Kostenschätzung   |   Anlagen (4)   |   Genehmigungsverlauf",
        "",
        "ALLGEMEINE DATEN",
        kv([
            ("Reiseart", "Inlandsdienstreise"),
            ("Zweck / Anlass", "Vortrag „Wirbelablösung an schräg angeströmten Rundzylindern“"),
            ("", f"(Programm Session B2, {de('2027-06-22')}, 14:20 Uhr)"),
            ("Reiseziel", "Kiel, Deutschland"),
            ("Dienstgeschäft", f"{de('2027-06-22')} 08:30 Uhr   bis   {de('2027-06-23')} 16:00 Uhr"),
            ("Reisebeginn", f"{wd('2027-06-21')} 14:10 Uhr, Wohnung"),
            ("Reiseende", f"{wd('2027-06-23')} ca. 21:45 Uhr, Wohnung"),
            ("Privater Reiseanteil", "nein"),
            ("Kostenzuordnung", "Kostenstelle 15210400 (Landesmittel FG Strömungsmechanik)"),
        ], k=26),
        "",
        "REISEVERLAUF",
        "  Datum          Von                        Nach                       Verkehrsmittel",
        f"  {de('2027-06-21')}     Wernstadt Hbf   14:28      Kiel Hbf   18:40           Bahn, 1. Klasse, Umstieg Hamburg Hbf",
        f"  {de('2027-06-23')}     Kiel Hbf   17:19           Wernstadt Hbf   21:31      Bahn, 1. Klasse, Umstieg Hamburg Hbf",
        "",
        kv([
            ("Fahrtdauer einfache Strecke", "4 Std. 12 Min. (Hinfahrt)   /   4 Std. 12 Min. (Rückfahrt)"),
            ("Begründung höhere Klasse", "Fahrtdauer der einfachen Strecke über zwei Stunden"),
            ("BahnCard / Zeitkarte", "keine"),
        ], k=30),
        "",
        "KOSTENSCHÄTZUNG",
        "  Kostenart                                    Menge     Einzelbetrag        Betrag",
        f"  Fahrtkosten Bahn, 1. Klasse, Sparpreis          2          {eur(rail)} €      {eur(rail_sum)} €",
        f"  Übernachtung Kiel inkl. Frühstück               2          {eur(hotel)} €      {eur(hotel_sum)} €",
        f"  Tagungsgebühr KMS 2027                          1         {eur(fee)} €      {eur(fee)} €",
        f"  Summe                                                                 {eur(total)} €",
        "  Verpflegungsmehraufwand: Ermittlung bei der Reisekostenabrechnung",
        "",
        "  Begründung Übernachtungskosten über 80,00 € je Nacht:",
        f"  Zeitgleich mit dem Kolloquium findet in Kiel die Fachmesse MariTec 2027 statt ({de('2027-06-21')} bis {de('2027-06-24')}).",
        f"  Das Zimmerkontingent des Tagungshotels war bei der Buchung am {de('2027-05-03')} ausgeschöpft. Laut Hotelportal",
        f"  (Ausdruck vom {de('2027-05-03')}, Anlage) war das Hotel Förde-Blick mit 94,00 € die günstigste verfügbare",
        "  Unterkunft in Kiel. Die Notwendigkeit wird hiermit bei Antragstellung schriftlich begründet.",
        "",
        "ANLAGEN",
        "  KMS2027_Programm.pdf   ·   Bahn_Reservierung.pdf   ·   Hotelportal_Suche_03-05-2027.pdf   ·   Hotel_Reservierung.pdf",
        "",
        "GENEHMIGUNGSVERLAUF",
        f"  {de('2027-05-10')} 09:58   Gesendet durch Dr. Malte Quernheim",
        f"  {de('2027-05-10')} 09:58   Wartet auf Genehmigung: Prof. Dr. Annegret Vollbrecht (Fachgebietsleitung)",
    ])

    programm = "\n".join([
        "KMS 2027",
        "18. Kolloquium Maritime Strömungstechnik",
        f"{de('2027-06-22')} – {de('2027-06-23')}   ·   Kiel, Hörsaalgebäude am Westring",
        "",
        "PROGRAMM (Stand: 26. April 2027)",
        "",
        wdl('2027-06-22'),
        "  08:30   Registrierung",
        "  09:00   Eröffnung",
        "  09:15   Session A1: Schiffshydrodynamik",
        "  11:00   Session A2: Offshore-Strukturen",
        "  12:30   Mittagspause (in der Tagungsgebühr enthalten)",
        "  13:40   Session B1: Umströmte Körper",
        "  14:20   Session B2: Wirbelinduzierte Schwingungen",
        "          M. Quernheim (Universität Wernstadt): Wirbelablösung an schräg angeströmten Rundzylindern",
        "          K. Ahrends (Hochschule Flensbek): Galloping bei vereisten Seilen",
        "  16:30   Posterbegehung",
        "  19:00   Kolloquiumsabend (optional, 45,00 €, nicht in der Tagungsgebühr enthalten)",
        "",
        wdl('2027-06-23'),
        "  09:00   Session C1: Messtechnik in Schlepptanks",
        "  11:00   Session C2: Numerische Verfahren",
        "  12:30   Mittagspause",
        "  13:30   Session C3: Hafen- und Küstenwasserbau",
        "  15:30   Abschlussdiskussion",
        "  16:00   Ende des Kolloquiums",
        "",
        "Tagungsgebühr: 240,00 € (Frühbucher bis 31.05.2027), 290,00 € regulär.",
        "Zimmerkontingent im Tagungshotel Am Hafen: abrufbar bis 30.04.2027, inzwischen ausgebucht.",
        f"Hinweis: Vom {de('2027-06-21')} bis {de('2027-06-24')} findet in Kiel die Fachmesse MariTec statt.",
        "Bitte buchen Sie Ihre Unterkunft frühzeitig.",
    ])

    bahn = "\n".join([
        lr("Universität Wernstadt", "Fernverkehr Mitte-Nord AG"),
        lr("Fachgebiet Strömungsmechanik", "Kundenservice Geschäftsreisen"),
        lr("z. Hd. Dr. Malte Quernheim", "Postfach 11 04 20"),
        lr("Kurfürstenring 40", "30159 Hannover"),
        "34127 Wernstadt",
        "",
        lr("", f"Auftragsnummer: 7731 0429 5518"),
        lr("", f"Buchungsdatum: {de('2027-05-03')}"),
        lr("", "Status: Option, Zahlung nach Genehmigung bis 24.05.2027"),
        "",
        "Reservierungsbestätigung – keine Fahrkarte, keine Rechnung",
        "",
        "  Fahrt     Datum         Verbindung                                        Klasse   Tarif       Preis",
        f"  Hin       {de('2027-06-21')}    Wernstadt Hbf 14:28 – Hamburg Hbf 16:39 (FV 581)      1.       Sparpreis   {eur(rail)} €",
        "                          Hamburg Hbf 17:05 – Kiel Hbf 18:40 (RE 21088)",
        "                          Reisedauer 4:12 h, 1 Umstieg",
        f"  Rück      {de('2027-06-23')}    Kiel Hbf 17:19 – Hamburg Hbf 18:52 (RE 21095)         1.       Sparpreis   {eur(rail)} €",
        "                          Hamburg Hbf 19:20 – Wernstadt Hbf 21:31 (FV 586)",
        "                          Reisedauer 4:12 h, 1 Umstieg",
        "",
        lr("", f"Summe brutto   {eur(rail_sum)} €"),
        lr("", f"enthaltene MwSt. 7 %   {eur(rail_vat)} €"),
        lr("", f"Summe netto   {eur(rail_net)} €"),
        "",
        "Ermäßigung: keine (keine BahnCard angegeben). Zugbindung gemäß Sparpreis-Bedingungen.",
        "Vergleich 2. Klasse Sparpreis: 2 × 59,90 € = 119,80 €.",
        "",
        "Fernverkehr Mitte-Nord AG · Sitz Hannover · USt-IdNr. DE 811 902 337",
    ])

    portal = "\n".join([
        lr("hotelfinder.example", "abgerufen am 03.05.2027, 10:14 Uhr"),
        "Suchergebnis: Kiel (Umkreis 10 km)   ·   21.06.2027 – 23.06.2027 (2 Nächte)   ·   1 Erwachsener   ·   Einzelzimmer",
        "Sortierung: Preis aufsteigend   ·   Hinweis: Messe MariTec 21.–24.06. – hohe Nachfrage in Kiel",
        "",
        "  Nr.   Unterkunft                         Lage                     Verpflegung        Preis/Nacht    Gesamt",
        "  1     Hotel Förde-Blick                  1,8 km vom Zentrum       inkl. Frühstück        94,00 €    188,00 €",
        "  2     Hotel Am Hafen (Tagungshotel)      0,4 km vom Zentrum       –                    ausgebucht          –",
        "  3     Pension Holtenau                   4,9 km vom Zentrum       –                    ausgebucht          –",
        "  4     Gästehaus Düsternbrook             2,6 km vom Zentrum       –                    ausgebucht          –",
        "  5     City-Hotel Kiel Hbf                0,6 km vom Zentrum       inkl. Frühstück       112,00 €    224,00 €",
        "  6     Hotel Seebrise                     3,1 km vom Zentrum       inkl. Frühstück       128,00 €    256,00 €",
        "  7     Kiel Business Suites               1,2 km vom Zentrum       ohne Frühstück        139,00 €    278,00 €",
        "",
        "4 von 11 Unterkünften im Umkreis von 10 km für Ihre Daten verfügbar.",
        "Alle Preise inkl. MwSt. und Gebühren.",
    ])

    hotel_doc = "\n".join([
        lr("Hotel Förde-Blick GmbH", "Reservierungsbestätigung"),
        lr("Kiellinie 212 · 24106 Kiel", "Reservierungs-Nr. FB-27-06-3381"),
        lr("Tel. 0431 77 40 90 · Steuer-Nr. 20 291 44017", f"Datum: {de('2027-05-03')}"),
        "",
        "Rechnungsanschrift:",
        "Universität Wernstadt",
        "Fachgebiet Strömungsmechanik",
        "Kurfürstenring 40, 34127 Wernstadt",
        "",
        "Gast: Dr. Malte Quernheim",
        "",
        kv([
            ("Anreise", wd('2027-06-21')),
            ("Abreise", wd('2027-06-23')),
            ("Zimmer", "1 Einzelzimmer Komfort"),
            ("Rate", "94,00 € pro Nacht inkl. Frühstück (2 Nächte)"),
            ("Gesamtbetrag", f"{eur(hotel_sum)} € inkl. MwSt."),
            ("Zahlung", "auf Rechnung an die Universität Wernstadt"),
            ("Storno", "kostenfrei bis 7 Tage vor Anreise"),
        ], k=16),
        "",
        "Wir freuen uns auf Ihren Besuch.",
    ])

    case(TRIP, "dienstreiseantrag-c01", "angenommen",
         "Inlandsdienstreise nach Kiel zum KMS 2027 mit eigenem Vortrag (Programm Session B2 am 22.06.2027), "
         "am 10.05.2027 und damit sechs Wochen vor Reisebeginn beantragt. Die Bahnfahrt in der 1. Klasse ist "
         "zulässig: nach § 5 Abs. 1 Satz 2 HRKG können die Kosten für Bahnfahrten bis zur nächst höheren Klasse "
         "erstattet werden, wenn die Fahrtdauer der einfachen Strecke mehr als zwei Stunden beträgt; laut "
         "Reservierung dauern Hin- und Rückfahrt je 4:12 Stunden. Die Übernachtung zu 94,00 € liegt über der "
         "Grenze von 80,00 €, ist aber, wie die Uni-Kassel-Seite „Dienstreisemanagement“ verlangt, bei "
         "Antragstellung schriftlich begründet (Messe MariTec, Tagungshotel ausgebucht) und durch den "
         "Portalausdruck belegt, das gebuchte Hotel ist die günstigste verfügbare Unterkunft. Die Hotelrechnung "
         "geht an die Universität, die Summe von 607,80 € (179,80 + 188,00 + 240,00) stimmt. Der Antrag ist zu "
         "genehmigen.",
         [doc("fiori-reiseantrag.pdf", fiori, font="Helvetica", title="Reiseantrag 4100027713",
              producer="SAP Fiori Launchpad (Druckansicht)"),
          doc("kms2027-programm.pdf", programm, title="KMS 2027 Programm"),
          doc("bahn-reservierung.pdf", bahn, font="Helvetica", title="Reservierungsbestaetigung"),
          doc("hotelportal-suche-03-05-2027.pdf", portal, font="Helvetica", title="hotelfinder.example"),
          doc("hotel-reservierung.pdf", hotel_doc, title="Reservierung FB-27-06-3381")],
         "Domestic trip with 1st-class rail (4:12 h one way) and a 94 EUR hotel justified in writing with a portal printout",
         "§ 5 Abs. 1 HRKG: „Die Kosten für Bahnfahrten können bis zur nächst höheren Klasse erstattet werden, wenn die "
         "Fahrtdauer der einfachen Strecke mehr als zwei Stunden beträgt oder sonstige triftige Gründe vorliegen.“ + "
         "Dienstreisemanagement: „Darüber hinaus gehende Übernachtungskosten werden nur erstattet, wenn sie unvermeidbar "
         "waren. D. h. die Notwendigkeit ist im Einzelfall nachvollziehbar schriftlich bei Antragsstellung zu begründen.“",
         f"{SRC_HRKG5}; {SRC_DRM}",
         "SAP Fiori 'Meine Reiseanträge' object page (Helvetica), rail reservation, hotel-portal search printout, hotel confirmation",
         "yes (looks wrong: 1st class and > 80 EUR hotel; both allowed)", "high")


# --------------------------------------------------------------------------- #
# c02  abgelehnt (trap): trip to Haifa, Israel – not approved until further notice
# --------------------------------------------------------------------------- #
def c02():
    flight, rail, hotel_n, fee = D("412.00"), D("98.00"), D("96.00"), D("180.00")
    hotel = r2(hotel_n * 4)
    total = tot(flight, rail, hotel, fee)
    assert total == D("1074.00")
    form = "\n".join([
        "UNIVERSITÄT WERNSTADT                                     Abteilung Personal und Organisation",
        "                                                          - Reisekostenstelle -",
        "ANTRAG AUF GENEHMIGUNG ElNER DIENSTREISE                   Eingang:  03. AUG. 2027",
        "(Papierformular für Hilfskräfte ohne Fiori-Zugang)",
        ". , '",
        "1. Antragsteller/in",
        "   Name, Vorname:       Brakensiek, Lenja",
        "   Beschäftigung:       [X] wiss. Hilfskraft   [ ] stud. Hilfskraft   [ ] Beschäftigte/r",
        "   Fachgebiet / FB:     Bodenphysik / FB 11",
        "   Telefon (intern):    -4471",
        "",
        "2. Angaben zur Reise",
        "   Reiseziel (Ort):     Haifa, Technion-Campus",
        "   Auslandsreise:       [X] ja   [ ] nein          Land:  Israel",
        "   Anlass:              Posterbeitrag „Infiltration into crusted loess soils under",
        "                        simulated rainfall“ beim 9th International Workshop on",
        "                        Arid Soil Hydrology (IWASH 2027)",
        f"   Dienstgeschäft:      {de('2027-10-12')} bis {de('2027-10-14')}",
        f"   Reisebeginn:         {wd('2027-10-11')}, 03:40 Uhr, Wohnung",
        f"   Reiseende:           {wd('2027-10-15')}, ca. 20:30 Uhr, Wohnung",
        "   Verkehrsmittel:      [X] Flugzeug (Economy)   [X] Bahn 2. Kl. (Zubringer Flughafen)",
        "                        [ ] privates Kfz   [ ] Mietwagen",
        "   Privater Anteil:     [ ] ja   [X] nein",
        "   A1-Bescheinigung:    [ ] nicht erforderlich   [X] Beantragung über Reisekostenstelle",
        "",
        "3. Voraussichtliche Kosten",
        f"   Flug Frankfurt - Tel Aviv - Frankfurt, Economy (Angebot anbei)      {eur(flight):>10} EUR",
        f"   Bahn Wernstadt - Frankfurt Flughafen, hin und zurück                {eur(rail):>10} EUR",
        f"   Unterkunft Haifa, 4 Nächte à {eur(hotel_n)} EUR (Gästehaus Technion)       {eur(hotel):>10} EUR",
        f"   Teilnahmegebühr (Studierendentarif)                                 {eur(fee):>10} EUR",
        f"   Summe                                                               {eur(total):>10} EUR",
        "",
        "4. Finanzierung:       DFG-Projekt BR 2291/3-1, Auftrag 6114-0388 (Reisemittel)",
        "5. Begründung:         Vorstellung der Feldmessungen aus dem DFG-Projekt; Poster",
        "                       angenommen (E-Mail der Organisatoren anbei).",
        "",
        f"   Datum: {de('2027-08-02')}      Unterschrift Antragstel1er/in:  [Unterschrift]",
        "",
        f"   Zustimmung Fachgebiets1eitung: Prof. Dr. Gerwin Taubenheim-Ruppel   [Unterschrift]   {de('2027-08-02')}",
        "",
        "   Vom Antragsteller nicht auszufüllen:   genehmigt [ ]   Rückfrage [ ]   Datum / Zeichen: ______",
        "",
        "Formular RK-1H, Stand 01/2026                                                      Seite 1 von 1",
    ])
    mail = "\n".join([
        "E-Mail – lenja.brakensiek@uni-wernstadt.de" + " " * 30 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  IWASH 2027 – Poster acceptance (submission P-044)",
        "  IWASH 2027 Organizing Committee <iwash2027@workshops.example.org>",
        f"  {wen('2027-07-19')} 16:22",
        "  An: Lenja Brakensiek <lenja.brakensiek@uni-wernstadt.de>",
        "",
        "  Dear Ms Brakensiek,",
        "",
        "  we are happy to inform you that your contribution",
        "",
        "      P-044  „Infiltration into crusted loess soils under simulated rainfall“",
        "",
        "  has been accepted for poster presentation at the 9th International Workshop on Arid Soil",
        "  Hydrology (IWASH 2027), which will take place at the Technion campus in Haifa, Israel,",
        "  from 12 to 14 October 2027.",
        "",
        "  Poster session: Wednesday, 13 October 2027, 15:30-17:30. Poster size A0 portrait.",
        "  Registration fee: EUR 180 (student rate), EUR 420 (regular). Accommodation is available in",
        "  the Technion guest house at EUR 96 per night (single room).",
        "",
        "  Best regards,",
        "  The IWASH 2027 Organizing Committee",
        "",
        "1 von 1" + " " * 90 + f"{de('2027-07-19')}",
    ])
    assert dt('2027-10-13').strftime("%A") == "Wednesday"
    offer = "\n".join([
        lr("Reisebüro Kolbeck & Söhne – Firmendienst", "Angebot Nr. KS-27-08-1142"),
        lr("Lindenplatz 3 · 34117 Wernstadt", f"Datum: {de('2027-07-30')}"),
        "",
        "Für: Universität Wernstadt, FG Bodenphysik, Reisende: Lenja Brakensiek",
        "",
        "Flugangebot Economy, Preise inkl. Steuern und Gebühren",
        "",
        "  Variante 1 (empfohlen)",
        f"    Hinflug    {wd('2027-10-11')}   Frankfurt FRA 06:55  ->  Tel Aviv TLV 11:50   direkt",
        f"    Rückflug   {wd('2027-10-15')}   Tel Aviv TLV 13:05  ->  Frankfurt FRA 16:40   direkt",
        "    Tarif Economy Classic, 1 Gepäckstück 23 kg                                   412,00 EUR",
        "",
        "  Variante 2 (Vergleich)",
        "    gleiche Tage, 1 Umstieg in Wien, Tarif Economy Flex                          489,00 EUR",
        "",
        "Zug zum Flug Wernstadt - Frankfurt Flughafen (2. Kl.), hin und zurück:           98,00 EUR",
        "Option gültig bis 20.08.2027. Ticketausstellung nach Genehmigung der Dienstreise.",
    ])
    case(TRIP, "dienstreiseantrag-c02", "abgelehnt",
         "Die beantragte Reise führt zum IWASH 2027 nach Haifa; der Antrag nennt als Land Israel, die "
         "Annahme-Mail bestätigt den Technion-Campus in Haifa, Israel. Nach der Uni-Kassel-Seite "
         "„Dienstreisemanagement“ werden Dienstreisen unter anderem nach Israel bis auf Weiteres nicht "
         "genehmigt. Dass der Papierantrag der wissenschaftlichen Hilfskraft sonst vollständig, rechtzeitig und "
         "rechnerisch richtig ist (Summe 1.074,00 €), ändert daran nichts. Der Antrag ist abzulehnen.",
         [doc("reiseantrag-scan.pdf", form, jitter=1.6, title="Scan_20270803_0912",
              producer="Canon iR-ADV C5560 (Scan to PDF)"),
          doc("email-poster-acceptance.pdf", mail, title="IWASH 2027 – Poster acceptance"),
          doc("flugangebot-reisebuero.pdf", offer, font="Helvetica", title="Angebot KS-27-08-1142")],
         "Scanned paper form of a research assistant for a poster at a workshop in Haifa; complete and on time, but the destination is Israel",
         "Dienstreisemanagement: „Es wird darauf hingewiesen, dass Dienstreisen in die Russische Föderation, in die "
         "Ukraine, nach Belarus, Moldau- die Gebiete im Süden und Osten, die an die Ukraine grenzen, Niger, Iran, "
         "Israel, in die Palästinensischen Gebiete und Libanon bis auf Weiteres nicht genehmigt werden.“",
         SRC_DRM,
         "Scanned legacy paper form with checkboxes and OCR noise (Hilfskraft route), English acceptance mail, travel-agency offer",
         "yes (looks complete and fine; destination rule)", "high")


# --------------------------------------------------------------------------- #
# c03  abgelehnt: keynote with honorarium -> Nebentätigkeit
# --------------------------------------------------------------------------- #
def c03():
    rail, hotel_n = D("119.90"), D("118.00")
    rail_sum, hotel_sum = tot(rail, rail), r2(hotel_n * 2)
    total = tot(rail_sum, hotel_sum)
    assert total == D("475.80")
    form = "\n".join([
        lr("Reiseportal Universität Wernstadt", "Druckansicht", 108),
        lr("Dienstreiseantrag DR-2027-04418", f"erstellt {de('2027-03-01')} 11:02", 108),
        "",
        "1   Antragstellerin",
        kv([("Name", "Prof. Dr. Henrike Olbertz-Nauen"),
            ("Organisationseinheit", "FB 07, Fachgebiet Wirtschaftsinformatik und Unternehmenssysteme"),
            ("Status", "Professorin (W3)")], k=30, indent=4),
        "",
        "2   Reise",
        kv([("Art", "Auslandsdienstreise (EU)"),
            ("Ziel", "Aarhus, Dänemark"),
            ("Anlass", "Keynote „Process Mining in Mid-sized Manufacturing“, NAIS Industry Day 2027"),
            ("Dienstgeschäft", f"{wd('2027-05-19')}, 09:00 – 17:00 Uhr"),
            ("Abreise", f"{wd('2027-05-18')}, 08:12 Uhr, Wernstadt Hbf"),
            ("Rückkehr", f"{wd('2027-05-20')}, 18:47 Uhr, Wernstadt Hbf"),
            ("Verkehrsmittel", "Bahn, 2. Klasse"),
            ("Privater Reiseanteil", "nein"),
            ("A1-Bescheinigung", f"über Reisekostenstelle beantragt am {de('2027-03-01')}")], k=30, indent=4),
        "",
        "3   Kostenschätzung",
        f"    Bahn Wernstadt – Aarhus H, hin und zurück (2 × {eur(rail)} €)                       {eur(rail_sum)} €",
        f"    Hotel Aarhus, 2 Nächte à {eur(hotel_n)} € (ohne Frühstück)                            {eur(hotel_sum)} €",
        "    Teilnahmegebühr (entfällt, eingeladene Rednerin)                                    0,00 €",
        f"    Summe                                                                            {eur(total)} €",
        "",
        "4   Finanzierung",
        kv([("Kostenstelle", "07311000 (Landesmittel)"),
            ("Leistungen Dritter", "keine"),
            ("(Kostenübernahme, Sachleistungen, Honorare)", "")], k=30, indent=4),
        "",
        "5   Begründung",
        "    Einladung als Keynote-Sprecherin durch die Nordic Association for Information Systems (NAIS).",
        "    Transfer der Forschungsergebnisse in die Praxis; Kontakte für Kooperationsprojekte.",
        "    Anlagen: E-Mail-Verlauf mit der Einladung, Programm des Industry Day.",
        "",
        "6   Genehmigung",
        "    Status: eingereicht, wartet auf Prüfung durch die Reisekostenstelle",
    ])
    thread = "\n".join([
        "E-Mail – h.olbertz-nauen@uni-wernstadt.de" + " " * 30 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  RE: Invitation – Keynote at NAIS Industry Day 2027",
        "  Henrike Olbertz-Nauen <h.olbertz-nauen@uni-wernstadt.de>",
        f"  {wen('2027-02-24')} 09:12",
        "  An: Mikkel Thorsager <m.thorsager@nais-association.example>",
        "",
        "  Dear Mikkel,",
        "  thank you very much, I am happy to confirm. I will arrange my travel through my university",
        "  and send you the title and abstract by the end of March.",
        "  Best regards, Henrike",
        "",
        "  Von: Mikkel Thorsager <m.thorsager@nais-association.example>",
        f"  Gesendet: {wen('2027-02-22')} 15:47",
        "  An: Henrike Olbertz-Nauen <h.olbertz-nauen@uni-wernstadt.de>",
        "  Betreff: RE: Invitation – Keynote at NAIS Industry Day 2027",
        "",
        "  Dear Professor Olbertz-Nauen,",
        "  many thanks for your positive reply. To confirm the details: the keynote (45 minutes plus",
        "  questions) is scheduled for the morning of 19 May 2027 in Aarhus. As is customary for our",
        "  Industry Day keynotes, NAIS offers an honorarium of EUR 800, paid after the event against an",
        "  invoice. Unfortunately we are not able to reimburse travel or accommodation costs.",
        "  Kind regards, Mikkel",
        "",
        "  Von: Mikkel Thorsager <m.thorsager@nais-association.example>",
        f"  Gesendet: {wen('2027-02-15')} 10:03",
        "  An: Henrike Olbertz-Nauen <h.olbertz-nauen@uni-wernstadt.de>",
        "  Betreff: Invitation – Keynote at NAIS Industry Day 2027",
        "",
        "  Dear Professor Olbertz-Nauen,",
        "  on behalf of the Nordic Association for Information Systems I would like to invite you to give",
        "  the opening keynote at our NAIS Industry Day 2027 in Aarhus, Denmark, on 19 May 2027. About 180",
        "  participants from industry and academia are expected.",
        "  Kind regards,",
        "  Mikkel Thorsager, Chair, NAIS Industry Day 2027",
        "",
        "1 von 1" + " " * 90 + de('2027-03-01'),
    ])
    assert dt('2027-05-19').strftime("%A") == "Wednesday"
    prog = "\n".join([
        "NAIS INDUSTRY DAY 2027",
        "Wednesday, 19 May 2027  ·  Aarhus, Denmark  ·  Navitas Conference Centre",
        "",
        "09:00   Welcome (Mikkel Thorsager, NAIS)",
        "09:15   Keynote: Process Mining in Mid-sized Manufacturing",
        "        Prof. Dr. Henrike Olbertz-Nauen, Universität Wernstadt",
        "10:15   Coffee",
        "10:45   Industry track I: ERP modernisation",
        "12:30   Lunch",
        "13:30   Industry track II: Data platforms",
        "15:30   Panel: Research meets practice",
        "17:00   Closing",
        "",
        "Participation is free for invited speakers.",
    ])
    case(TRIP, "dienstreiseantrag-c03", "abgelehnt",
         "Nach der beigefügten E-Mail von NAIS vom 22.02.2027 erhält Prof. Olbertz-Nauen für die Keynote am "
         "19.05.2027 ein Honorar von 800 EUR; Reise- und Hotelkosten übernimmt NAIS nicht. Im Antrag ist das Feld "
         "„Leistungen Dritter (Kostenübernahme, Sachleistungen, Honorare)“ dagegen mit „keine“ ausgefüllt. Nach "
         "der Uni-Kassel-Seite „Dienstreisemanagement“ deutet ein für einen Vortrag gezahltes Honorar auf eine "
         "Nebentätigkeit und damit auf eine privat veranlasste Reise hin; eine Dienstreisegenehmigung und "
         "Reisekostenabrechnung aus Landes- oder Drittmitteln ist dann grundsätzlich nicht möglich. Die "
         "beantragten 475,80 € aus Landesmitteln können so nicht genehmigt werden, der Antrag ist abzulehnen.",
         [doc("reiseportal-antrag-dr-2027-04418.pdf", form, font="Helvetica", title="DR-2027-04418",
              producer="Reiseportal Wernstadt"),
          doc("email-verlauf-einladung.pdf", thread, title="RE: Invitation – Keynote at NAIS Industry Day 2027"),
          doc("programm-industry-day.pdf", prog, font="Helvetica", title="NAIS Industry Day 2027")],
         "Professor's keynote trip to Aarhus; the English mail thread offers an 800 EUR honorarium, the form says 'no third-party benefits'",
         "Dienstreisemanagement: „Wird Ihnen im Rahmen einer Dienstreise ein Honorar (z.B. für einen Vortrag) "
         "gezahlt, deutet dies auf eine Nebentätigkeit und damit auf eine privat veranlasste Reise hin. Eine "
         "Dienstreisegenehmigung und nachfolgende Reisekostenabrechnung aus Landes- oder Drittmitteln der "
         "Universität Kassel ist dann grundsätzlich nicht möglich!“",
         SRC_DRM,
         "Web travel-portal print view (Helvetica), English Outlook thread with quoted replies, event flyer",
         "no", "high")


# --------------------------------------------------------------------------- #
# c04  angenommen (trap): private stay of exactly 5 working days
# --------------------------------------------------------------------------- #
def c04():
    out_f, back_f, back_alt = D("168.00"), D("176.00"), D("214.00")
    hotel_n, fee, train = D("85.00"), D("390.00"), D("49.90")
    hotel = r2(hotel_n * 4)
    train_sum = tot(train, train)
    total = tot(out_f, back_f, hotel, fee, train_sum)
    assert total == D("1173.80") and back_alt - back_f == D("38.00")
    leave = ['2027-09-16', '2027-09-17', '2027-09-20', '2027-09-21', '2027-09-22']
    assert all(dt(x).weekday() < 5 for x in leave)
    span = [dt('2027-09-16') + datetime.timedelta(days=i) for i in range(7)]
    assert sum(1 for x in span if x.weekday() < 5) == 5
    fiori = "\n".join([
        lr("SAP    My Travel Requests", "Dr. Teodora Fenske   (TF)", 112),
        lr("<  Travel Request 4100027958", "Status: Sent for Approval", 112),
        "",
        "Porto – EuroSysCon 2027",
        "Traveler: Dr. Teodora Fenske   ·   Personnel No. 00427106   ·   Control and System Theory, Faculty 16",
        f"Created {de('2027-06-28')} 14:20   ·   Approver: Prof. Dr. Lorenz Achterberg",
        "",
        "General Data   |   Itinerary   |   Estimated Costs   |   Attachments (3)   |   Approval Log",
        "",
        "GENERAL DATA",
        kv([("Trip Type", "Foreign business trip (EU)"),
            ("Purpose", "Presentation of accepted paper #217 „Moving-horizon estimation for"),
            ("", "networked drives with delayed measurements“"),
            ("Destination", "Porto, Portugal"),
            ("Business Activity", f"{de('2027-09-13')} 09:00   to   {de('2027-09-15')} 17:30"),
            ("Trip Start", f"{wen('2027-09-12')} 10:15, residence"),
            ("Trip End", f"{wen('2027-09-22')} approx. 21:15, residence"),
            ("Private Stay", f"yes, {de('2027-09-16')} to {de('2027-09-22')}: annual leave of 5 working days,"),
            ("", "approved (see attachment); nights 16.09.–22.09. booked and paid privately"),
            ("A1 Certificate", f"requested via travel office on {de('2027-06-28')}"),
            ("Cost Assignment", "Internal order 6116-0712 (DFG project FE 1180/2-1, travel budget)")], k=22),
        "",
        "ITINERARY",
        "  Date          From                           To                             Means of Transport",
        f"  {de('2027-09-12')}    Wernstadt Hbf   10:41          Frankfurt Airport   13:05      Train, 2nd class",
        f"  {de('2027-09-12')}    Frankfurt (FRA)   15:20        Porto (OPO)   17:10            Flight, Economy",
        f"  {de('2027-09-22')}    Porto (OPO)   14:05            Frankfurt (FRA)   17:55        Flight, Economy",
        f"  {de('2027-09-22')}    Frankfurt Airport   18:31      Wernstadt Hbf   20:58          Train, 2nd class",
        "",
        "ESTIMATED COSTS",
        "  Expense Type                                             Qty    Unit Amount        Amount",
        f"  Flight FRA–OPO, {de('2027-09-12')}                                1       {eur(out_f)} €      {eur(out_f)} €",
        f"  Flight OPO–FRA, {de('2027-09-22')} (see price comparison)         1       {eur(back_f)} €      {eur(back_f)} €",
        f"  Hotel Porto, 12.09.–16.09.2027, conference rate                4        {eur(hotel_n)} €      {eur(hotel)} €",
        f"  Conference fee (member rate)                                   1       {eur(fee)} €      {eur(fee)} €",
        f"  Train Wernstadt Hbf – Frankfurt Airport and back               2        {eur(train)} €       {eur(train_sum)} €",
        f"  Total                                                                              {eur(total)} €",
        "  Per diem: calculated at settlement for 12.09.–16.09.2027, as if only the business trip had taken place.",
        "",
        "ATTACHMENTS",
        "  EuroSysCon2027_acceptance.pdf   ·   Preisvergleich_Rueckflug_Reisebuero.pdf   ·   Urlaubsantrag_genehmigt.pdf",
        "",
        "APPROVAL LOG",
        f"  {de('2027-06-28')} 14:20   Sent by Dr. Teodora Fenske",
        f"  {de('2027-06-28')} 14:20   Awaiting approval: Prof. Dr. Lorenz Achterberg (head of department)",
    ])
    vergleich = "\n".join([
        lr("Hanseatica Firmenreisen GmbH", "Preisvergleich Flug"),
        lr("Ständeplatz 9 · 34117 Wernstadt", f"erstellt am {de('2027-06-25')}"),
        "",
        "Kunde: Universität Wernstadt, FG Regelungs- und Systemtheorie",
        "Reisende: Dr. Teodora Fenske   ·   Anlass: EuroSysCon 2027, Porto (Dienstgeschäft 13.09.–15.09.2027)",
        "",
        "Hinflug (beide Varianten gleich)",
        f"   {wd('2027-09-12')}   Frankfurt FRA 15:20 – Porto OPO 17:10   Economy Light+   {eur(out_f)} EUR",
        "",
        "Variante A – Rückreise direkt nach Ende des Dienstgeschäfts",
        f"   {wd('2027-09-16')}   Porto OPO 06:40 – Frankfurt FRA 10:30   Economy Light+   {eur(back_alt)} EUR",
        "   (am Abend des 15.09. keine Verbindung mehr nach Frankfurt nach Ende des Programms um 17:30 Uhr)",
        "",
        "Variante B – gebucht, Rückreise nach dem privaten Aufenthalt",
        f"   {wd('2027-09-22')}   Porto OPO 14:05 – Frankfurt FRA 17:55   Economy Light+   {eur(back_f)} EUR",
        "",
        f"Ergebnis: Variante B ist {eur(back_alt - back_f)} EUR günstiger als Variante A.",
        "Durch die Verlängerung entstehen keine Mehrkosten für den Rückflug.",
        "Hotel: in beiden Varianten 4 dienstliche Nächte (12.09.–16.09.2027) zum Konferenztarif von 85,00 EUR.",
        "",
        "Preise inkl. Steuern und Gebühren, Stand des Abrufs. Hanseatica Firmenreisen GmbH",
    ])
    urlaub = "\n".join([
        lr("SAP ESS · Abwesenheitsantrag", f"Ausdruck vom {de('2027-06-29')}"),
        "",
        kv([("Mitarbeiterin", "Dr. Teodora Fenske (00427106)"),
            ("Abwesenheitsart", "Erholungsurlaub"),
            ("Zeitraum", f"{wd('2027-09-16')} bis {wd('2027-09-22')}"),
            ("Dauer", "5,0 Arbeitstage (Sa 18.09. und So 19.09. arbeitsfrei)"),
            ("Bemerkung", "Anschluss an Dienstreise EuroSysCon 2027 (Porto)"),
            ("Status", f"genehmigt – Prof. Dr. Lorenz Achterberg, {de('2027-06-29')}"),
            ("Resturlaub 2027 danach", "9,0 Tage")], k=26),
    ])
    assert dt('2027-09-18').weekday() == 5 and dt('2027-09-19').weekday() == 6
    accept = "\n".join([
        "E-Mail – teodora.fenske@uni-wernstadt.de" + " " * 30 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  EuroSysCon 2027: decision on paper #217",
        "  EuroSysCon 2027 Program Committee <pc@eurosyscon2027.example>",
        f"  {wen('2027-06-04')} 18:05",
        "  An: Teodora Fenske <teodora.fenske@uni-wernstadt.de>",
        "",
        "  Dear Dr. Fenske,",
        "",
        "  congratulations: paper #217 „Moving-horizon estimation for networked drives with delayed",
        "  measurements“ has been accepted for oral presentation at EuroSysCon 2027, the 14th European",
        "  Symposium on Control and Estimation, Porto, Portugal, 13–15 September 2027.",
        "",
        "  At least one author must register (member rate EUR 390) and present the paper in person.",
        "  The conference hotel offers a rate of EUR 85 per night (12–16 September) until 31 July.",
        "",
        "  Best regards,",
        "  EuroSysCon 2027 Program Committee",
    ])
    case(TRIP, "dienstreiseantrag-c04", "angenommen",
         "Auslandsdienstreise zur EuroSysCon 2027 in Porto (Vortrag des angenommenen Beitrags #217), rund elf "
         "Wochen vorher beantragt, A1-Bescheinigung beantragt. Der anschließende private Aufenthalt vom 16. bis "
         "22.09.2027 umfasst laut genehmigtem Urlaubsantrag genau 5 Arbeitstage (Do, Fr, Mo, Di, Mi). Nach der "
         "Uni-Kassel-Seite „Dienstreisemanagement“ wird bei einem Privataufenthalt von weniger als oder genau 5 "
         "Arbeitstagen die Reisekostenvergütung so festgesetzt, als habe nur die Dienstreise stattgefunden; nach "
         "§ 14 Abs. 1 Satz 2 HRKG darf sie die Kosten des tatsächlichen Reiseverlaufs nicht übersteigen. Der "
         "beigefügte Preisvergleich zeigt, dass der gebuchte Rückflug am 22.09. mit 176,00 € um 38,00 € günstiger "
         "ist als die dienstliche Rückreise am 16.09.; beantragt sind nur die vier dienstlichen Hotelnächte, die "
         "privaten Nächte trägt die Antragstellerin selbst. Die Summe von 1.173,80 € stimmt. Zu genehmigen.",
         [doc("fiori-travel-request-4100027958.pdf", fiori, font="Helvetica", title="Travel Request 4100027958",
              producer="SAP Fiori Launchpad (Print Preview)"),
          doc("preisvergleich-rueckflug.pdf", vergleich, font="Helvetica", title="Preisvergleich Flug"),
          doc("urlaubsantrag-ess.pdf", urlaub, title="Abwesenheitsantrag"),
          doc("eurosyscon2027-acceptance.pdf", accept, title="EuroSysCon 2027: decision on paper #217")],
         "Conference in Porto followed by a private stay of exactly 5 working days; price comparison shows no extra cost",
         "Dienstreisemanagement: „Dauert der Privataufenthalt weniger als oder genau 5 Arbeitstage, so wird die "
         "Reisekostenvergütung so festgesetzt, als habe nur die Dienstreise stattgefunden.“ + § 14 Abs. 1 Satz 2 "
         "HRKG: „Die Reisekostenerstattung nach Satz 1 darf die sich nach dem tatsächlichen Reiseverlauf ergebende "
         "nicht übersteigen.“",
         f"{SRC_DRM}; {SRC_HRKG14}",
         "SAP Fiori travel request in English UI, travel-agency price comparison, SAP ESS leave request, acceptance mail",
         "yes (looks like a long private extension; boundary case of exactly 5 working days)", "high")


# --------------------------------------------------------------------------- #
# c05  abgelehnt (trap): pro-rata refund of a private BahnCard 50 requested
# --------------------------------------------------------------------------- #
def c05():
    leg = D("44.20")
    rail = tot(leg, leg)
    hotel, fee, bc = D("78.00"), D("95.00"), D("244.00")
    share = r2(bc / 4)
    total = tot(rail, hotel, fee, share)
    assert share == D("61.00") and total == D("322.40")
    form = "\n".join([
        "Universität Wernstadt                                         REISEANTRAG",
        "Abteilung Personal und Organisation                           (Formular für begründete Ausnahmefälle)",
        "",
        "Grund für die Nutzung des Formulars: Fiori-Störung 15.–19.10.2027 (ITS-Meldung 2027-1182)",
        "",
        "+-------------------------------------------------------------------------------------------+",
        "| Name, Vorname        | Aschoff-Yilmaz, Benedikt                    | Pers.-Nr. 00431977     |",
        "| Dienststelle         | FB 14, FG Siedlungswasserwirtschaft         | Tel. -3318             |",
        "+-------------------------------------------------------------------------------------------+",
        "| Reiseziel            | Essen                                                              |",
        "| Zweck                | Teilnahme Erfahrungsaustausch Kanalsanierung 2027 (Einladung anbei)|",
        f"| Dienstgeschäft       | {de('2027-11-18')} 10:00 Uhr bis {de('2027-11-19')} 13:00 Uhr                        |",
        f"| Reisebeginn / -ende  | {wd('2027-11-18')} 06:52 Uhr   /   {wd('2027-11-19')} ca. 17:30 Uhr             |",
        "| Verkehrsmittel       | [X] Bahn 2. Klasse  [ ] 1. Klasse  [ ] Flug  [ ] privates Kfz  [ ] Mietwagen |",
        "| Private BahnCard     | [X] ja: BahnCard 50, 2. Klasse, gültig 01.04.2027 bis 31.03.2028  [ ] nein  |",
        "| Privater Reiseanteil | [ ] ja   [X] nein                                                  |",
        "+-------------------------------------------------------------------------------------------+",
        "| Voraussichtliche Kosten                                                         EUR        |",
        f"| Bahn Wernstadt Hbf – Essen Hbf und zurück, Flexpreis mit BahnCard 50            {eur(rail):>8}   |",
        f"| Übernachtung Essen, 1 Nacht (Hotel am Grugapark)                                {eur(hotel):>8}   |",
        f"| Teilnahmegebühr                                                                 {eur(fee):>8}   |",
        f"| Anteilige Erstattung BahnCard 50 (Anschaffung {eur(bc)} EUR, 4 geplante       {eur(share):>8}   |",
        "|   Dienstreisen 2027/28, Anteil 1/4; Rechnung anbei)                                        |",
        f"| Summe                                                                           {eur(total):>8}   |",
        "+-------------------------------------------------------------------------------------------+",
        "| Kostenstelle / Auftrag   14420100 (Landesmittel)                                           |",
        "+-------------------------------------------------------------------------------------------+",
        "",
        f"Wernstadt, {de('2027-10-18')}        Unterschrift Antragsteller: [Unterschrift]",
        f"Befürwortet (Fachgebietsleitung): Prof. Dr. Swantje Möllenkamp   [Unterschrift]   {de('2027-10-18')}",
    ])
    einladung = "\n".join([
        lr("Fachverband Abwassertechnik West e.V.", "Geschäftsstelle · Rüttenscheider Str. 48 · 45130 Essen"),
        "",
        "Einladung",
        "Erfahrungsaustausch Kanalsanierung 2027",
        f"{wdl('2027-11-18')}, 10:00 Uhr bis {wdl('2027-11-19')}, 13:00 Uhr",
        "Tagungszentrum am Grugapark, Essen",
        "",
        "Programm",
        f"  {de('2027-11-18')}   10:00   Begrüßung",
        "                10:30   Schlauchliner im Bestand – Erfahrungen aus fünf Kommunen",
        "                14:00   Arbeitsgruppen (Inspektion, Hydraulik, Vergabe)",
        "                17:30   Ende des ersten Tages",
        f"  {de('2027-11-19')}   09:00   Ergebnisse der Arbeitsgruppen",
        "                11:00   Forschung trifft Praxis: Kurzvorträge der Hochschulen",
        "                13:00   Ende",
        "",
        "Teilnahmegebühr 95,00 EUR (inkl. Tagungsgetränke), Anmeldung bis 05.11.2027.",
        "Wir würden uns freuen, Herrn Aschoff-Yilmaz als Vertreter der Universität Wernstadt begrüßen zu dürfen.",
    ])
    bahn = "\n".join([
        lr("Fernverkehr Mitte-Nord AG", "Buchungsbestätigung"),
        lr("Kundenservice · Postfach 11 04 20 · 30159 Hannover", f"Buchungsdatum {de('2027-10-18')}"),
        "",
        "Reisender: Benedikt Aschoff-Yilmaz        Auftrag 7731 1106 2047",
        "Ermäßigung: BahnCard 50 (2. Klasse), Nr. wird bei der Fahrkartenkontrolle vorgezeigt",
        "",
        "  Hinfahrt   " + wd('2027-11-18') + "   Wernstadt Hbf 06:58 – Essen Hbf 09:41   2. Kl.   Flexpreis   " + eur(leg) + " €",
        "  Rückfahrt  " + wd('2027-11-19') + "   Essen Hbf 14:16 – Wernstadt Hbf 17:02   2. Kl.   Flexpreis   " + eur(leg) + " €",
        "",
        f"  Gesamtpreis (mit BahnCard 50, statt 2 × 88,40 €)                         {eur(rail)} €",
        "",
        "Zahlung: Option bis 25.10.2027, Zahlung nach Genehmigung der Dienstreise.",
    ])
    bc_inv = "\n".join([
        lr("Fernverkehr Mitte-Nord AG", "Rechnung Nr. BC-2027-0409-77182"),
        lr("BahnCard-Service · 30159 Hannover", f"Rechnungsdatum {de('2027-04-01')}"),
        "",
        "Herrn",
        "Benedikt Aschoff-Yilmaz",
        "Weinbergstraße 17",
        "34121 Wernstadt",
        "",
        "  BahnCard 50, 2. Klasse, Gültigkeit 01.04.2027 bis 31.03.2028          244,00 €",
        "  enthaltene MwSt. 7 %                                                    15,96 €",
        "",
        "Bezahlt per Lastschrift am 01.04.2027. Persönliche BahnCard, nicht übertragbar.",
    ])
    assert vat_split(bc, 7)[1] == D("15.96")
    case(TRIP, "dienstreiseantrag-c05", "abgelehnt",
         "Der Antrag zur Fahrt nach Essen setzt richtig die vorhandene private BahnCard 50 ein (Fahrkarten "
         "88,40 €), beantragt aber zusätzlich eine anteilige Erstattung der BahnCard 50 über 61,00 € (ein Viertel "
         "der Anschaffungskosten von 244,00 €, Rechnung vom 01.04.2027). Nach der Uni-Kassel-Seite "
         "„Dienstreisemanagement“ ist die Erstattung der Anschaffungskosten einer privaten BahnCard ausschließlich "
         "dann möglich, wenn sich die Kosten aufgrund von durchgeführten Dienstreisen vollständig amortisiert "
         "haben; eine Voraberstattung oder die anteilige Erstattung ist nicht möglich. Die Kostenschätzung von "
         "322,40 € ist um diese Position zu korrigieren; in dieser Form ist der Antrag abzulehnen.",
         [doc("reiseantrag-formular.pdf", form, title="Reiseantrag (Ausnahmeformular)",
              producer="Adobe Acrobat (ausfüllbares Formular)"),
          doc("einladung-erfahrungsaustausch.pdf", einladung, font="Helvetica", title="Einladung"),
          doc("bahn-buchung.pdf", bahn, font="Helvetica", title="Buchungsbestaetigung"),
          doc("rechnung-bahncard50.pdf", bc_inv, title="Rechnung BahnCard 50")],
         "Domestic trip using a private BahnCard 50; the cost estimate adds a 1/4 pro-rata refund of the BahnCard itself",
         "Dienstreisemanagement: „Die Erstattung der Anschaffungskosten für eine private BahnCard ist ausschließlich "
         "dann möglich, wenn sich die Kosten aufgrund von durchgeführten Dienstreisen vollständig amortisiert haben. "
         "Eine Voraberstattung oder die anteilige Erstattung der Anschaffungskosten ist nicht möglich.“",
         SRC_DRM,
         "Legacy fillable PDF form with ASCII table borders (exception route), invitation letter, rail booking, BahnCard invoice",
         "yes (looks economical; subtle BahnCard rule)", "high")


# =========================================================================== #
# PROCUREMENT
# =========================================================================== #

# --------------------------------------------------------------------------- #
# c06  abgelehnt (trap): office swivel chairs from a web shop with three offers
# --------------------------------------------------------------------------- #
def c06():
    n = 6
    p1, p2, p3 = D("289.00"), D("312.50"), D("334.00")
    s1, s2, s3 = r2(p1 * n), r2(p2 * n), r2(p3 * n)
    vat = r2(s1 * D("0.19"))
    gross = tot(s1, vat)
    assert (s1, s2, s3, gross) == (D("1734.00"), D("1875.00"), D("2004.00"), D("2063.46"))
    antrag = "\n".join([
        lr("Universität Wernstadt · Intranet · Beschaffungsantrag (Formular BA-1, Version 3/2026)", "BA-27-0915", 112),
        "",
        "1. Bedarfsstelle",
        kv([("Fachgebiet", "Technische Thermodynamik (FB 15)"),
            ("Ansprechpartner", "Dipl.-Ing. Carsten Weyrauch, Tel. -2290"),
            ("Kostenstelle", "15240100"),
            ("Lieferanschrift", "Kurfürstenring 40, Geb. M3, Räume 1.104 und 1.106")], k=24, indent=3),
        "",
        "2. Gegenstand",
        "   Pos.   Menge   Bezeichnung                                                  Einzelpreis netto     Gesamt netto",
        f"   1        {n}     Bürodrehstuhl ErgoSit Pro 3D, Synchronmechanik, Armlehnen          {eur(p1)} €       {eur(s1)} €",
        "                  4D, Sitztiefenverstellung, Bezug Stoff anthrazit",
        f"                                                                         Summe netto        {eur(s1)} €",
        f"                                                                         MwSt. 19 %           {eur(vat)} €",
        f"                                                                         Summe brutto       {eur(gross)} €",
        "",
        "3. Lieferant",
        kv([("Firma", "Möbelwerk24 Versand GmbH (Onlineshop moebelwerk24.example)"),
            ("Anschrift", "Herforder Straße 301, 33609 Bielefeld")], k=24, indent=3),
        "",
        "4. Vergabe",
        kv([("Vergabeart", "Preisanfrage, drei Vergleichsangebote, wirtschaftlichstes Angebot"),
            ("Angebote", "Möbelwerk24 1.734,00 € · Hellweg Büroausstattung 1.875,00 € · Sitzkultur Rabe 2.004,00 € (netto)"),
            ("Rahmenvertragsprodukt", "[ ] ja    [X] nein"),
            ("Zuordnung", "GWG (Einzelpreis netto 250,00 – 800,00 €)"),
            ("Begründung Bedarf", "Erstausstattung von zwei Büros für neue Mitarbeitende ab 01.10.2027")], k=24, indent=3),
        "",
        "5. Beauftragung durch Kostenstellenbevollmächtigte",
        f"   Prof. Dr. Ottilie Brandhorst          {de('2027-09-08')}          [Unterschrift]",
        "",
        "Anlagen: Angebot Möbelwerk24 (Warenkorb), Angebot Hellweg, Angebot Sitzkultur Rabe (E-Mail), Vergabevermerk",
    ])
    shop = "\n".join([
        lr("moebelwerk24.example", f"Angebot zum Warenkorb W-77120458 · erstellt {de('2027-09-01')}"),
        "Geschäftskunden-Angebot · gültig 14 Tage · Preise netto zzgl. MwSt.",
        "",
        "  Artikel                                        Art.-Nr.       Menge    Einzelpreis       Summe",
        f"  Bürodrehstuhl ErgoSit Pro 3D, Stoff anthrazit  ES-P3D-ANT        {n}       {eur(p1)} €    {eur(s1)} €",
        "  Versand (Spedition, frei Verwendungsstelle)                                0,00 €      0,00 €",
        "",
        f"  Zwischensumme netto                                                             {eur(s1)} €",
        f"  MwSt. 19 %                                                                        {eur(vat)} €",
        f"  Gesamtbetrag                                                                    {eur(gross)} €",
        "",
        "Kunde: Universität Wernstadt, FG Technische Thermodynamik, z. Hd. Herrn Weyrauch",
        "Lieferzeit 8–10 Werktage. Zahlung auf Rechnung (öffentliche Auftraggeber).",
        "Möbelwerk24 Versand GmbH · Herforder Straße 301 · 33609 Bielefeld · HRB 44102",
    ])
    hellweg = "\n".join([
        "Hellweg Büroausstattung GmbH",
        "Objekteinrichtung · Sitzmöbel · Bürotechnik",
        "Bahnhofstraße 14 · 59065 Hamm",
        "",
        "Universität Wernstadt",
        "Fachgebiet Technische Thermodynamik",
        "Herrn Dipl.-Ing. Carsten Weyrauch",
        "Kurfürstenring 40",
        "34127 Wernstadt",
        "",
        lr("Angebot Nr. 27-1310", f"Hamm, {de('2027-09-02')}"),
        "",
        "Sehr geehrter Herr Weyrauch,",
        "vielen Dank für Ihre Anfrage. Wir bieten Ihnen an:",
        "",
        f"  {n} Stück Bürodrehstuhl „Comfort Synchro 400“, Armlehnen 4D, Stoff anthrazit",
        f"  Einzelpreis netto {eur(p2)} €                                  Gesamt netto {eur(s2)} €",
        "",
        "Lieferung frei Haus, Lieferzeit ca. 3 Wochen. Angebot gültig bis 30.09.2027.",
        "",
        "Mit freundlichen Grüßen",
        "Hellweg Büroausstattung GmbH",
    ])
    rabe = "\n".join([
        "E-Mail – carsten.weyrauch@uni-wernstadt.de" + " " * 30 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  AW: Preisanfrage 6 Bürodrehstühle",
        "  Sitzkultur Rabe e.K. <info@sitzkultur-rabe.example>",
        f"  {wd('2027-09-06')} 11:37",
        "  An: Carsten Weyrauch <carsten.weyrauch@uni-wernstadt.de>",
        "",
        "  Guten Tag Herr Weyrauch,",
        f"  für 6 Bürodrehstühle „Rabe Office Line S“ (Synchronmechanik, Armlehnen höhenverstellbar) können wir",
        f"  Ihnen {eur(p3)} € netto je Stück anbieten, zusammen {eur(s3)} € netto, Lieferung inklusive.",
        "  Das Angebot gilt bis Monatsende.",
        "",
        "  Freundliche Grüße",
        "  Jens Rabe, Sitzkultur Rabe e.K., Am Markt 6, 34277 Fuldabrück",
    ])
    vermerk = "\n".join([
        "Vergabevermerk zum Beschaffungsantrag BA-27-0915",
        "",
        "Gegenstand: 6 Bürodrehstühle für Büros M3 1.104 / 1.106",
        "Verfahren: Preisanfrage bei drei Anbietern (Onlineshop und Fachhandel)",
        "",
        "  Bieter                           Angebot vom      Summe netto",
        f"  Möbelwerk24 Versand GmbH         {de('2027-09-01')}       {eur(s1)} €",
        f"  Hellweg Büroausstattung GmbH     {de('2027-09-02')}       {eur(s2)} €",
        f"  Sitzkultur Rabe e.K.             {de('2027-09-06')}       {eur(s3)} €",
        "",
        "Zuschlag: Möbelwerk24 Versand GmbH als wirtschaftlichstes Angebot.",
        f"Wernstadt, {de('2027-09-08')}    C. Weyrauch",
    ])
    case(PROC, "beschaffungsantrag-c06", "abgelehnt",
         "Beantragt werden sechs Bürodrehstühle aus einem Onlineshop für 1.734,00 € netto (2.063,46 € brutto). "
         "Drei Angebote liegen vor, das günstigste ist gewählt, und im Antrag ist „Rahmenvertragsprodukt: nein“ "
         "angekreuzt. Nach der Seite „Rahmenverträge“ der Universität Kassel bestehen aber Rahmenverträge unter "
         "anderem für Bürodrehstühle, und sie sind verbindlich für alle Bereiche; nach der Beschaffungsseite muss "
         "ein Produkt, zu dem ein Rahmenvertrag besteht, ausschließlich beim Rahmenvertragspartner bestellt "
         "werden (Bestellung über das WPS-System). Vergleichsangebote ersetzen den Rahmenvertrag nicht. Der Antrag "
         "ist abzulehnen.",
         [doc("beschaffungsantrag-ba-27-0915.pdf", antrag, font="Helvetica", title="Beschaffungsantrag BA-27-0915",
              producer="Intranet-Formularserver Wernstadt"),
          doc("angebot-moebelwerk24-warenkorb.pdf", shop, font="Helvetica", title="Angebot Warenkorb W-77120458"),
          doc("angebot-hellweg.pdf", hellweg, title="Angebot 27-1310"),
          doc("angebot-sitzkultur-rabe-email.pdf", rabe, title="AW: Preisanfrage 6 Buerodrehstuehle"),
          doc("vergabevermerk.pdf", vermerk, title="Vergabevermerk BA-27-0915")],
         "Six office swivel chairs from a web shop, three offers, cheapest chosen, 'no framework product' ticked",
         "Rahmenverträge: „Derzeit existieren Rahmenverträge u.a. für Büromaterial, PC's/Notebooks und Monitore, "
         "Büropapiere, Bürodrehstühle, Seminarstühle, Büromobiliar, …“ and „Die Rahmenverträge sind verbindlich für "
         "alle Bereiche der Universität Kassel.“ + Beschaffung: „Sollte man ein Produkt bestellen wollen, zu dem ein "
         "Rahmenvertrag besteht, muss man dieses Produkt ausschließlich beim Rahmenvertragspartner bestellen“",
         f"{SRC_RV}; {SRC_BESCH}",
         "Intranet web-form printout (Helvetica), web-shop basket quote, letter quote, e-mail quote, award note",
         "yes (looks exemplary: three offers, cheapest chosen)", "high")


# --------------------------------------------------------------------------- #
# c07  abgelehnt (trap): one need split into two direct awards below 1,000 EUR
# --------------------------------------------------------------------------- #
def c07():
    unit = D("158.00")
    half = r2(unit * 6)
    whole = r2(unit * 12)
    vat = r2(whole * D("0.19"))
    gross = tot(whole, vat)
    assert half == D("948.00") and whole == D("1896.00") and gross == D("2256.24")

    def banf(nr, pos_time):
        return "\n".join([
            f"Bestellanforderung {nr}" + " " * 40 + f"Druckdatum {de('2027-03-08')}   Seite 1",
            "-" * 100,
            f"Belegart NB  Normal-BANF        Ersteller KROHNEALB   Angelegt {de('2027-03-08')} {pos_time}",
            "Einkäufergruppe 210 Zentrale Beschaffung      Werk 1000 Universität Wernstadt",
            "-" * 100,
            "Pos  Kurztext                              Menge ME     Preis/ME   Wert netto   Lieferant",
            f"10   Magnetrührer m. Heizplatte MR-H5          6 ST       {eur(unit)}      {eur(half)}   71204 Labortechnik Fremersdorf GmbH",
            "     Lieferdatum 26.03.2027  Lagerort LB-02 Praktikumslabor Bioverfahrenstechnik",
            "-" * 100,
            f"Gesamtwert netto                                                {eur(half)} EUR",
            "Kontierung        K  Kostenstelle 16420300",
            "Vergabeart        DV Direktauftrag (Auftragswert unter 1.000 EUR netto), 1 Angebot",
            "Angebot           AN-27-0412 vom 03.03.2027",
            "Freigabe KSt.     LEIMBACH  08.03.2027",
        ])
    mail = "\n".join([
        "E-Mail – svenja.krohne-albers@uni-wernstadt.de" + " " * 24 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  Magnetrührer Praktikumslabor – BANF 10048817 und 10048818",
        "  Svenja Krohne-Albers <svenja.krohne-albers@uni-wernstadt.de>",
        f"  {wd('2027-03-08')} 14:12",
        "  An: beschaffung@uni-wernstadt.de",
        "  Cc: Prof. Dr. Hartwig Leimbach <hartwig.leimbach@uni-wernstadt.de>",
        "",
        "  Liebes Team der Zentralen Beschaffung,",
        "",
        "  für die zwölf Arbeitsplätze im Praktikumslabor brauchen wir neue Magnetrührer. Ich habe zwei BANFen",
        "  angelegt (10048817 und 10048818, je 6 Stück), beide als Direktauftrag unter 1.000 € netto bei",
        "  Labortechnik Fremersdorf. Das Angebot liegt bei. Die Geräte sollten vor Semesterbeginn da sein.",
        "",
        "  Viele Grüße",
        "  Svenja Krohne-Albers",
        "  Fachgebiet Bioverfahrenstechnik",
    ])
    offer = "\n".join([
        "LABORTECHNIK FREMERSDORF GMBH",
        "Gewerbepark Nord 7 · 66798 Wallerfangen-Fremersdorf · Tel. 06831 90 22 0",
        "",
        "Universität Wernstadt",
        "FG Bioverfahrenstechnik, Frau Dr. Krohne-Albers",
        "Kurfürstenring 52, 34127 Wernstadt",
        "",
        lr("ANGEBOT AN-27-0412", f"Datum {de('2027-03-03')}", 96),
        "Ihre Anfrage vom 01.03.2027: Magnetrührer für Praktikumslabor (12 Arbeitsplätze)",
        "",
        "Pos  Menge  Artikel                                            Einzelpreis      Gesamt",
        f"1    12     Magnetrührer mit Heizplatte MR-H5, 15 l, 340 °C       {eur(unit)} €   {eur(whole)} €",
        "",
        f"                                                    Summe netto       {eur(whole)} €",
        f"                                                    MwSt. 19 %          {eur(vat)} €",
        f"                                                    Summe brutto      {eur(gross)} €",
        "",
        "Lieferung frei Haus in einer Sendung, ca. 2 Wochen nach Bestelleingang.",
        "Angebot gültig bis 31.03.2027. Es gelten unsere AGB.",
    ])
    case(PROC, "beschaffungsantrag-c07", "abgelehnt",
         "Die Bestellanforderungen 10048817 und 10048818 vom 08.03.2027 betreffen denselben Bedarf (zwölf "
         "Magnetrührer MR-H5 für die zwölf Arbeitsplätze des Praktikumslabors), denselben Lieferanten und "
         "dasselbe Angebot AN-27-0412 über 12 Stück zu 1.896,00 € netto, Lieferung in einer Sendung. Der "
         "Auftragswert beträgt damit 1.896,00 € netto, nicht zweimal 948,00 €. Die Direktvergabe ohne "
         "Vergleichsangebote ist nach der Seite „Nachhaltiges Catering“ der Universität Kassel (Verweis auf die "
         "Beschaffungsordnung) nur unter einem Auftragswert von 1.000 Euro möglich; darüber sind nach der "
         "Beschaffungsseite grundsätzlich drei Angebote einzuholen. Die Aufteilung in zwei Bestellungen umgeht "
         "diese Grenze, Vergleichsangebote fehlen. Der Antrag ist abzulehnen.",
         [doc("banf-10048817.pdf", banf("10048817", "13:51"), title="BANF 10048817", producer="SAP GUI Druck (ME53N)"),
          doc("banf-10048818.pdf", banf("10048818", "13:58"), title="BANF 10048818", producer="SAP GUI Druck (ME53N)"),
          doc("email-an-beschaffung.pdf", mail, title="Magnetruehrer Praktikumslabor"),
          doc("angebot-an-27-0412.pdf", offer, title="Angebot AN-27-0412")],
         "Twelve stirrers from one offer (1,896 EUR net) split into two SAP requisitions of 948 EUR each as 'direct award < 1,000 EUR'",
         "Nachhaltiges Catering: „Hier besteht weiterhin, abhängig vom Auftragswert, die Notwendigkeit der Einholung "
         "von mindestens drei Vergleichsangeboten. Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro "
         "liegt, da hier eine Direktvergabe möglich ist.“ + Beschaffung: „Grundsätzlich müssen 3 Angebote eingeholt "
         "werden“ (no explicit anti-splitting text in the corpora; the order value is the one offer's 1.896 EUR)",
         f"{SRC_CAT}; {SRC_BESCH}",
         "Two SAP GUI requisition printouts (Courier), Outlook mail, supplier offer for the full quantity",
         "yes (each requisition looks compliant on its own)", "low")


# --------------------------------------------------------------------------- #
# c08  abgelehnt (trap): equipment-fund purchase above 50,000 EUR net without formal procedure
# --------------------------------------------------------------------------- #
def c08():
    a, b, c = D("52900.00"), D("55480.00"), D("57150.00")
    vat = r2(a * D("0.19"))
    gross = tot(a, vat)
    assert gross == D("62951.00")
    banf = "\n".join([
        lr("Universität Wernstadt – Abteilung Finanzen, SG IV B Zentrale Materialwirtschaft", "Eingang IV B: 09.04.2027", 110),
        "BESTELLANFORDERUNG – BESCHAFFUNG AUS DEM GERÄTEFONDS",
        "",
        kv([("Bedarfsstelle", "FB 15, Fachgebiet Werkstoffmechanik, Prof. Dr. Ruben Elsässer-Kunz"),
            ("Bewilligung Gerätefonds", "GF-27-08 vom 15.02.2027, bis 65.000,00 € brutto"),
            ("Kontierung", "Auftrag 3115-0027 (Gerätefonds 2027)"),
            ("Standort", "Geb. M5, Raum 0.012 (Crashlabor)"),
            ("Anlagenzuordnung", "Anlage, Inventarisierung erforderlich")], k=26),
        "",
        "Gegenstand",
        "  Pos  Menge  Bezeichnung                                                           Gesamt netto",
        f"  1    1      Hochgeschwindigkeitskamera-System HSC-X12 (1 MP, 21.000 fps), inkl.     {eur(a)} €",
        "               Objektivsatz, Steuer- und Auswertesoftware, Installation und Einweisung",
        f"                                                          Summe netto           {eur(a)} €",
        f"                                                          Erwerbsteuer 19 %      {eur(vat)} €",
        f"                                                          Summe brutto          {eur(gross)} €",
        "",
        kv([("Lieferant", "Kinetix Imaging Europe B.V., Eindhoven (NL), USt-IdNr. NL 8571.24.903.B01"),
            ("Vergabeart", "Angebotseinholung durch die Bedarfsstelle, Vordruck „Aufforderung zur"),
            ("", "Angebotsabgabe“, drei vergleichbare Angebote (Vergabevermerk anbei)"),
            ("ITS-Beteiligung", "nicht erforderlich (kein DV-System)")], k=26),
        "",
        f"Wernstadt, {de('2027-04-08')}   Prof. Dr. Ruben Elsässer-Kunz (Kostenstellenbevollmächtigter)   [Unterschrift]",
    ])
    rfq = "\n".join([
        "Universität Wernstadt · Fachgebiet Werkstoffmechanik",
        "AUFFORDERUNG ZUR ANGEBOTSABGABE",
        f"Datum: {de('2027-03-15')}      Angebotsfrist: {de('2027-04-02')}, 12:00 Uhr",
        "",
        "Versandt per E-Mail an: Kinetix Imaging Europe B.V.; Schnellbild Messtechnik GmbH; OptoDyn Systems GmbH",
        "",
        "Leistungsanforderungen (Mindestanforderungen)",
        "  1. Hochgeschwindigkeitskamera, Auflösung mind. 1 Megapixel",
        "  2. Bildrate mind. 20.000 Bilder/s bei voller Auflösung",
        "  3. Objektivsatz 24 mm, 50 mm, 85 mm; Steuer- und Auswertesoftware",
        "  4. Installation und Einweisung vor Ort, Gewährleistung mind. 24 Monate",
        "",
        "Zuschlagskriterium: niedrigster Preis bei Erfüllung aller Mindestanforderungen.",
        "Finanzierung: Gerätefonds 2027 (Bewilligung GF-27-08).",
    ])
    offers = "\n\f\n".join([
        "\n".join([
            "KINETIX IMAGING EUROPE B.V.",
            "Flight Forum 880 · 5657 DV Eindhoven · The Netherlands · VAT NL 8571.24.903.B01",
            "",
            lr("QUOTATION Q-27-0388", f"Date: {de('2027-03-30')}", 96),
            "To: Universität Wernstadt, Fachgebiet Werkstoffmechanik, Prof. Dr. R. Elsässer-Kunz",
            "",
            "Item  Description                                                        Amount (EUR)",
            "1     HSC-X12 high-speed camera, 1 MP at 21,000 fps, 64 GB memory              46,950.00",
            "2     Lens kit 24 / 50 / 85 mm                                                  3,480.00",
            "3     Control and analysis software, perpetual licence                          1,320.00",
            "4     Installation and on-site training (1 day)                                 1,150.00",
            "",
            "      Total net (intra-Community supply, reverse charge)                       52,900.00",
            "",
            "Warranty 24 months. Delivery 6 weeks after order. Valid until 30 June 2027.",
        ]),
        "\n".join([
            "Schnellbild Messtechnik GmbH · Industriestraße 22 · 73730 Esslingen",
            "",
            lr("Angebot SB-27-1176", f"Esslingen, {de('2027-03-31')}", 96),
            "An: Universität Wernstadt, FG Werkstoffmechanik",
            "",
            "  1   Hochgeschwindigkeitskamera FlashCam 1000 (1 MP, 22.500 fps)        49.890,00 €",
            "  2   Objektivsatz 24/50/85 mm                                              3.240,00 €",
            "  3   Software FlashView Pro                                                1.200,00 €",
            "  4   Installation und Einweisung                                           1.150,00 €",
            f"      Summe netto                                                         {eur(b)} €",
            "",
            "Gewährleistung 24 Monate, Lieferzeit 5 Wochen.",
        ]),
        "\n".join([
            "OptoDyn Systems GmbH · Am Technologiepark 5 · 07745 Jena",
            "",
            lr("Angebot OD-2027-0412", f"Jena, {de('2027-04-01')}", 96),
            "Universität Wernstadt, Fachgebiet Werkstoffmechanik",
            "",
            "  Hochgeschwindigkeitskamera OD-HS 21 (1,1 MP, 20.400 fps) mit Objektivsatz,",
            "  Software, Installation und Einweisung, Gewährleistung 36 Monate",
            f"  Gesamtpreis netto                                                    {eur(c)} €",
            "",
            "Lieferzeit 8 Wochen.",
        ]),
    ])
    assert tot("46950", "3480", "1320", "1150") == a
    assert tot("49890", "3240", "1200", "1150") == b
    vermerk = "\n".join([
        "VERGABEVERMERK",
        "Beschaffung Hochgeschwindigkeitskamera-System – Gerätefonds 2027 (GF-27-08)",
        "",
        f"Aufforderung zur Angebotsabgabe vom {de('2027-03-15')} an drei Anbieter; alle drei haben fristgerecht angeboten.",
        "",
        "  Bieter                           Angebot          Mindestanforderungen   Preis netto",
        f"  Kinetix Imaging Europe B.V.      Q-27-0388        erfüllt                {eur(a)} €",
        f"  Schnellbild Messtechnik GmbH     SB-27-1176       erfüllt                {eur(b)} €",
        f"  OptoDyn Systems GmbH             OD-2027-0412     erfüllt                {eur(c)} €",
        "",
        "Zuschlag: Kinetix Imaging Europe B.V. (niedrigster Preis).",
        f"Wernstadt, {de('2027-04-07')}    Prof. Dr. R. Elsässer-Kunz",
    ])
    case(PROC, "beschaffungsantrag-c08", "abgelehnt",
         "Das Hochgeschwindigkeitskamera-System wird aus dem Gerätefonds beschafft (Bewilligung GF-27-08), der "
         "Auftragswert beträgt 52.900,00 € netto (62.951,00 € brutto). Die Bedarfsstelle hat selbst drei Angebote "
         "eingeholt und das günstigste bezuschlagt. Nach der Seite „Gerätefondsverfahren“ der Universität Kassel "
         "ist die Angebotseinholung durch die Bedarfsstelle aber nur bis zu einem Auftragswert von 50.000 € netto "
         "vorgesehen; über 50.000 € netto ist ein Leistungsverzeichnis zu erstellen, das als Grundlage für ein "
         "förmliches Vergabeverfahren dient. Ein solches Verfahren hat nicht stattgefunden. Dass drei Angebote "
         "vorliegen und das günstigste gewählt wurde, ändert daran nichts. Der Antrag ist abzulehnen.",
         [doc("banf-geraetefonds.pdf", banf, font="Helvetica", title="Bestellanforderung Geraetefonds"),
          doc("aufforderung-angebotsabgabe.pdf", rfq, title="Aufforderung zur Angebotsabgabe"),
          doc("angebote-hsc.pdf", offers, title="Angebote (3 Dokumente)", producer="PDF24 Merge"),
          doc("vergabevermerk.pdf", vermerk, title="Vergabevermerk")],
         "Equipment-fund high-speed camera at 52,900 EUR net; three informal offers, cheapest chosen, no formal procedure",
         "Gerätefondsverfahren (table): „Auftragswert bis € 50.000 netto“ → „Angebotseinholung durch die Bedarfsstelle "
         "unter folgenden Voraussetzungen möglich: … mind. drei vergleichbare Angebote einzuholen“; „Auftragswert über "
         "€ 50.000 netto“ → „Erstellung eines Leistungsverzeichnisses (Inhalt: zu vereinbarende Funktionalitäten), das "
         "als Grundlage für ein förmliches Vergabeverfahren dient und damit Grundlage des Auftrages wird“",
         SRC_GF,
         "Equipment-fund requisition form (Helvetica), RFQ form, merged multi-document PDF of three offers (one English), award note",
         "yes (three offers and cheapest chosen look exemplary; value threshold)", "high")


# --------------------------------------------------------------------------- #
# c09  angenommen (trap): cheapest offer excluded for failing a mandatory requirement
# --------------------------------------------------------------------------- #
def c09():
    o1, o2, o3, o4 = D("18400.00"), D("21950.00"), D("23100.00"), D("24780.00")
    vat = r2(o2 * D("0.19"))
    gross = tot(o2, vat)
    assert gross == D("26120.50")
    fiori = "\n".join([
        lr("SAP    Bestellanforderungen verwalten", "Johanna Pietsch-Okafor", 112),
        lr("<  Bestellanforderung 10051174", "Status: Genehmigt (Kostenstelle) · zur Bearbeitung in IV B", 112),
        "",
        "Kopfdaten",
        kv([("Beschreibung", "Spektrumanalysator 9 kHz – 26,5 GHz, Projekt RAD-SENSE"),
            ("Angelegt von", f"Dr.-Ing. Johanna Pietsch-Okafor, {de('2027-05-03')}"),
            ("Kontierung", "Auftrag 6118-0451 (BMBF-Verbundprojekt RAD-SENSE, Sachmittel Geräte)"),
            ("Genehmigung", f"Prof. Dr. Erwin Dannenberg-Lutz (Projektleiter, kostenstellenbevollmächtigt), {de('2027-05-03')}")], k=20),
        "",
        "Positionen",
        "  Pos   Material / Kurztext                          Menge   ME   Preis netto     Wert netto     Lieferant",
        f"  10    Spektrumanalysator SA-265, 9 kHz–26,5 GHz       1     ST   {eur(o2)} €   {eur(o2)} €   HF-Systemhaus Brandauer KG",
        "        inkl. Vorverstärker, 3 Jahre Garantie",
        "",
        f"  Gesamtwert netto {eur(o2)} €   ·   Steuer 19 % {eur(vat)} €   ·   Gesamtwert brutto {eur(gross)} €",
        "",
        "Anlagen (6): Anfrage_12-04-2027.pdf · Angebot_Ostermann.pdf · Angebot_Brandauer.pdf · Angebot_Signalwerk.pdf ·",
        "             Quotation_Spektra.pdf · Vergabevermerk.pdf",
        "Notiz an Einkauf: Anlage (Inventarisierung), Standort Geb. E2, Raum 2.207 (HF-Labor).",
    ])
    anfrage = "\n".join([
        "Universität Wernstadt · FG Mikrowellensysteme · Verbundprojekt RAD-SENSE",
        "Anfrage / Aufforderung zur Angebotsabgabe",
        f"Datum: {de('2027-04-12')}    Frist: {de('2027-04-28')}",
        "",
        "Gegenstand: 1 Spektrumanalysator für Radarsensor-Messungen",
        "",
        "Mindestanforderungen (Nichterfüllung führt zum Ausschluss):",
        "  M1  Frequenzbereich mindestens 9 kHz bis 26,5 GHz",
        "  M2  Anzeigerauschen (DANL) mit Vorverstärker <= -150 dBm/Hz bei 10 GHz",
        "  M3  Garantie mindestens 3 Jahre",
        "",
        "Zuschlag: niedrigster Gesamtpreis netto unter den Angeboten, die alle Mindestanforderungen erfüllen.",
        "Angefragt: Messgeräte Ostermann GmbH, HF-Systemhaus Brandauer KG, Signalwerk Vertrieb GmbH,",
        "           Spektra Instruments Europe B.V.",
    ])
    ost = "\n".join([
        "MESSGERÄTE OSTERMANN GMBH · Hansaring 61 · 48155 Münster",
        "",
        lr("Angebot MO-27-3302", f"{de('2027-04-22')}", 90),
        "Universität Wernstadt, FG Mikrowellensysteme",
        "",
        "  Spektrumanalysator SpecLine 136 (9 kHz – 13,6 GHz), DANL -152 dBm/Hz,",
        "  mit Vorverstärker, Garantie 3 Jahre",
        f"  Preis netto                                                    {eur(o1)} €",
        "",
        "  Hinweis: Eine Ausführung bis 26,5 GHz führen wir nicht.",
        "Lieferzeit 2 Wochen.",
    ])
    bra = "\n".join([
        "HF-Systemhaus Brandauer KG",
        "Mess- und Prüftechnik für Hochfrequenz · Gutenbergstraße 9 · 82205 Gilching",
        "",
        "Universität Wernstadt",
        "FG Mikrowellensysteme, Frau Dr.-Ing. Pietsch-Okafor",
        "",
        lr("Angebot 27-A-0871", f"Gilching, {de('2027-04-26')}"),
        "",
        "  Pos. 1   Spektrumanalysator SA-265, 9 kHz – 26,5 GHz                    20.480,00 €",
        "  Pos. 2   Vorverstärker-Option (DANL -154 dBm/Hz bei 10 GHz)              1.470,00 €",
        "           Garantie 3 Jahre inklusive",
        f"           Summe netto                                                    {eur(o2)} €",
        "",
        "Lieferzeit 4 Wochen. Angebot gültig 60 Tage.",
    ])
    assert tot("20480", "1470") == o2
    sig = "\n".join([
        "Signalwerk Vertrieb GmbH · Rheinallee 120 · 55120 Mainz",
        "",
        lr("ANGEBOT SW-2027-554", f"Mainz, {de('2027-04-27')}", 90),
        "Kunde: Universität Wernstadt, Fachgebiet Mikrowellensysteme",
        "",
        "  1 x Spektrumanalysator SW-FSA 26 (9 kHz bis 26,5 GHz), Vorverstärker, DANL -151 dBm/Hz,",
        "      Garantie 3 Jahre",
        f"  Gesamtpreis netto                                              {eur(o3)} €",
    ])
    spk = "\n".join([
        "SPEKTRA INSTRUMENTS EUROPE B.V.",
        "Science Park 400 · 1098 XH Amsterdam · The Netherlands",
        "",
        lr("QUOTATION SIE-Q-27-1029", f"Date: {de('2027-04-28')}", 90),
        "Customer: Universität Wernstadt, Microwave Systems Group",
        "",
        "  1   Spectrum analyser SIE 2650, 9 kHz to 26.5 GHz, preamplifier,",
        "      DANL -155 dBm/Hz at 10 GHz, 3-year warranty                          EUR 24,780.00",
        "",
        "  Total net, intra-Community supply (reverse charge)                      EUR 24,780.00",
        "Delivery: 5 weeks.",
    ])
    vermerk = "\n".join([
        "VERGABEVERMERK – Spektrumanalysator, Verbundprojekt RAD-SENSE (Auftrag 6118-0451)",
        "",
        f"Anfrage vom {de('2027-04-12')} an vier Anbieter mit festgelegten Mindestanforderungen M1–M3.",
        "",
        "  Bieter                             Preis netto    M1 (26,5 GHz)   M2     M3     Wertung",
        f"  Messgeräte Ostermann GmbH          {eur(o1)} €    nein (13,6)     ja     ja     ausgeschlossen (M1)",
        f"  HF-Systemhaus Brandauer KG         {eur(o2)} €    ja              ja     ja     Rang 1",
        f"  Signalwerk Vertrieb GmbH           {eur(o3)} €    ja              ja     ja     Rang 2",
        f"  Spektra Instruments Europe B.V.    {eur(o4)} €    ja              ja     ja     Rang 3",
        "",
        "Drei vergleichbare Angebote erfüllen alle Mindestanforderungen. Zuschlag: HF-Systemhaus Brandauer KG",
        "als niedrigstes Angebot unter den zulässigen Angeboten.",
        f"Wernstadt, {de('2027-04-30')}   J. Pietsch-Okafor      gesehen: E. Dannenberg-Lutz",
    ])
    case(PROC, "beschaffungsantrag-c09", "angenommen",
         "Für den Spektrumanalysator wurden vier Angebote auf eine Anfrage mit festgelegten Mindestanforderungen "
         "eingeholt. Das billigste Angebot (Ostermann, 18.400,00 € netto) reicht nur bis 13,6 GHz statt der "
         "geforderten 26,5 GHz und wurde im Vergabevermerk deshalb ausgeschlossen. Es bleiben drei vergleichbare "
         "Angebote (21.950,00 €, 23.100,00 €, 24.780,00 € netto), wie es die Beschaffungsseite der Universität "
         "Kassel (grundsätzlich drei Angebote) und die Seite „Gerätefondsverfahren“ (auf Grundlage der geforderten "
         "Leistungsanforderungen mindestens drei vergleichbare Angebote) verlangen; nach dem Glossar "
         "Drittmittelbewirtschaftung gelten für Drittmittel dieselben Regeln. Bezuschlagt ist das günstigste "
         "zulässige Angebot; Bestellanforderung (21.950,00 € netto, 26.120,50 € brutto), Angebot und Vermerk "
         "stimmen überein, der kostenstellenbevollmächtigte Projektleiter hat genehmigt. Anzunehmen.",
         [doc("fiori-banf-10051174.pdf", fiori, font="Helvetica", title="Bestellanforderung 10051174",
              producer="SAP Fiori Launchpad (Druckansicht)"),
          doc("anfrage-12-04-2027.pdf", anfrage, title="Anfrage Spektrumanalysator"),
          doc("angebot-ostermann.pdf", ost, title="Angebot MO-27-3302"),
          doc("angebot-brandauer.pdf", bra, font="Helvetica", title="Angebot 27-A-0871"),
          doc("angebot-signalwerk.pdf", sig, title="Angebot SW-2027-554"),
          doc("quotation-spektra.pdf", spk, font="Helvetica", title="Quotation SIE-Q-27-1029"),
          doc("vergabevermerk.pdf", vermerk, title="Vergabevermerk Spektrumanalysator")],
         "Four offers for a spectrum analyser; the cheapest misses the 26.5 GHz minimum and is excluded, the cheapest compliant one wins",
         "Beschaffung: „Grundsätzlich müssen 3 Angebote eingeholt werden“ + Gerätefondsverfahren: „1. Festlegung der "
         "geforderten Leistungsanforderungen / Funktionalitäten 2. Auf dieser Grundlage sind mind. drei vergleichbare "
         "Angebote einzuholen“ + Glossar: „Die Beschaffung von Geräten und Verbrauchsmaterialien aus Drittmitteln "
         "unterliegt grundsätzlich den gleichen Regeln wie die Beschaffung aus dem vom Land bereitgestellten Budget.“",
         f"{SRC_BESCH}; {SRC_GF}; {SRC_GLOS}",
         "SAP Fiori 'Bestellanforderungen verwalten' print, RFQ, four offers in four layouts (one English), award matrix",
         "yes (looks wrong: cheapest offer not chosen)", "high")


# --------------------------------------------------------------------------- #
# c10  angenommen (trap): TH Sallstedt direct award under its own 3,000 EUR rule
# --------------------------------------------------------------------------- #
def c10():
    net, listp = D("2418.00"), D("2690.00")
    vat = r2(net * D("0.19"))
    gross = tot(net, vat)
    disc = r2((listp - net) / listp * 100)
    assert gross == D("2877.42") and disc == D("10.11")
    banf = "\n".join([
        "TECHNISCHE HOCHSCHULE SALLSTEDT                       Dezernat 3 – Haushalt und Beschaffung",
        "BESTELLANFORDERUNG (BANF)                             Nr. (wird vom Dezernat vergeben): ________",
        "",
        "Bedarfsstelle:   Fakultät Verfahrenstechnik, Labor Thermische Verfahren",
        "Besteller/in:    M.Eng. Fabian Wöllner, Tel. 0 77 31 / 58 - 4412",
        "Kostenstelle:    4410 · Haushaltsjahr 2027",
        "",
        "Gegenstand:",
        "  Menge   Bezeichnung                                                   Preis netto",
        f"  1       Umwälzkühler Polartherm UK-800, 800 W bei 20 °C, -20 bis       {eur(net)} EUR",
        "          +40 °C, inkl. Schlauchsatz",
        f"  Summe netto {eur(net)} EUR   ·   USt. 19 % {eur(vat)} EUR   ·   Summe brutto {eur(gross)} EUR",
        "",
        "Lieferant:  Kältetechnik Brümmer GmbH, Hafenstraße 18, 78224 Singen",
        "",
        "Vergabeart (bitte ankreuzen):",
        "[X] Direktauftrag – geschätzter Auftragswert bis 3.000 EUR netto (§ 5 Abs. 2 Beschaffungsrichtlinie",
        "    der TH Sallstedt): Vergleichsangebote nicht erforderlich; die Angemessenheit des Preises ist",
        "    zu dokumentieren.",
        "[ ] Preisanfrage – über 3.000 EUR bis 25.000 EUR netto: mindestens drei schriftliche Angebote",
        "[ ] Ausschreibung über Dezernat 3 – über 25.000 EUR netto",
        "",
        f"Dokumentation Preisangemessenheit: Herstellerpreisliste 2027 (Listenpreis {eur(listp)} EUR netto,",
        f"Auszug anbei); das Angebot liegt {eur(disc)} % unter dem Listenpreis.",
        "",
        "Begründung des Bedarfs: Ersatz des defekten Kühlers am Rektifikationsversuch (Praktikum VT-4).",
        "",
        f"Sallstedt, {de('2027-06-09')}   Besteller/in: [Unterschrift]",
        f"Anordnung Kostenstellenverantwortliche: Prof. Dr. Ines Haberland-Meis   [Unterschrift]   {de('2027-06-09')}",
        "",
        "Ohne Unterschrift der/des Kostenstellenverantwortlichen wird die Bestellung nicht ausgelöst.",
    ])
    offer = "\n".join([
        "Kältetechnik Brümmer GmbH",
        "Hafenstraße 18 · 78224 Singen · Tel. 07731 66 21 0",
        "",
        "Technische Hochschule Sallstedt",
        "Fakultät Verfahrenstechnik, Herrn Wöllner",
        "",
        lr("Angebot KB-27-0619", f"Singen, {de('2027-06-07')}"),
        "",
        "  1 Stück Umwälzkühler Polartherm UK-800, inkl. Schlauchsatz 2 m",
        f"  Preis netto                                                    {eur(net)} EUR",
        f"  zzgl. 19 % USt.                                                  {eur(vat)} EUR",
        f"  Gesamt                                                         {eur(gross)} EUR",
        "",
        "Lieferung frei Haus innerhalb von 10 Arbeitstagen. Zahlungsziel 30 Tage netto.",
    ])
    liste = "\n".join([
        "POLARTHERM GMBH · Preisliste 2027 (gültig ab 01.01.2027) · Auszug Seite 14",
        "",
        "  Art.-Nr.     Modell     Kühlleistung (20 °C)   Temperaturbereich     Listenpreis netto",
        "  PT-UK-0400   UK-400     400 W                  -10 bis +40 °C            1.780,00 EUR",
        f"  PT-UK-0800   UK-800     800 W                  -20 bis +40 °C            {eur(listp)} EUR",
        "  PT-UK-1500   UK-1500    1.500 W                -25 bis +40 °C            3.940,00 EUR",
        "",
        "Preise ab Werk, zzgl. gesetzlicher USt. Händlerrabatte nach Vereinbarung.",
    ])
    case(PROC, "beschaffungsantrag-c10", "angenommen",
         "Fall der TH Sallstedt; deren Recht steht nicht in den Korpora, entschieden wird auf den eigenen "
         "Unterlagen. Der BANF-Vordruck der TH Sallstedt sieht bis zu einem Auftragswert von 3.000 EUR netto "
         "einen Direktauftrag ohne Vergleichsangebote vor (§ 5 Abs. 2 ihrer Beschaffungsrichtlinie) und verlangt "
         "nur eine Dokumentation der Preisangemessenheit. Der Auftrag über 2.418,00 EUR netto liegt darunter, der "
         "Vergleich mit der Herstellerpreisliste (2.690,00 EUR, Angebot 10,11 % darunter) ist beigefügt, BANF und "
         "Angebot stimmen überein (2.877,42 EUR brutto), und die Kostenstellenverantwortliche hat angeordnet. Die "
         "1.000-Euro-Grenze der Universität Kassel gilt für Sallstedt nicht. Anzunehmen.",
         [doc("banf-sallstedt.pdf", banf, jitter=0.8, title="BANF_Scan_0609", producer="Kyocera TASKalfa (Scan)"),
          doc("angebot-kb-27-0619.pdf", offer, font="Helvetica", title="Angebot KB-27-0619"),
          doc("preisliste-polartherm-auszug.pdf", liste, title="Preisliste 2027 Auszug")],
         "TH Sallstedt: one offer of 2,418 EUR net, allowed as direct award by Sallstedt's own form (limit 3,000 EUR) with documented price check",
         "Sallstedt's own BANF form: „Direktauftrag – geschätzter Auftragswert bis 3.000 EUR netto (§ 5 Abs. 2 "
         "Beschaffungsrichtlinie der TH Sallstedt): Vergleichsangebote nicht erforderlich; die Angemessenheit des "
         "Preises ist zu dokumentieren.“ + organisers' README: „The Sallstedt cases fall under another state's travel "
         "law, which is not in the corpora; they are decided on the documents alone.“",
         SRC_SAL,
         "Scanned TH Sallstedt paper requisition with checkboxes, supplier offer, manufacturer price list excerpt",
         "yes (looks wrong under Kassel's 1,000 EUR rule)", "low")


# =========================================================================== #
# EXPENSE REIMBURSEMENT
# =========================================================================== #

# --------------------------------------------------------------------------- #
# c11  angenommen (trap): hospitality with external partners, tip excluded
# --------------------------------------------------------------------------- #
def c11():
    food = [("Tagessuppe (Kürbis)", 3, D("5.80")), ("Gemüse-Risotto", 2, D("13.90")),
            ("Hähnchenbrust mit Ofengemüse", 3, D("15.50"))]
    drinks = [("Mineralwasser 0,5 l", 5, D("3.20")), ("Apfelschorle 0,4 l", 2, D("3.60")),
              ("Kaffee", 4, D("2.90"))]
    food_sum = tot(*[q * p for _, q, p in food])
    drink_sum = tot(*[q * p for _, q, p in drinks])
    total = tot(food_sum, drink_sum)
    tip = D("8.50")
    paid = tot(total, tip)
    f_net, f_vat = vat_split(food_sum, 7)
    d_net, d_vat = vat_split(drink_sum, 19)
    per_person = r2(total / 5)
    assert total == D("126.50") and paid == D("135.00") and per_person == D("25.30")
    meet = '2027-07-15'
    antrag = "\n".join([
        lr("Universität Wernstadt · Abteilung Finanzen", "Antrag auf Erstattung von Bewirtungskosten", 100),
        "(nach der Bewirtungskostenrichtlinie; mit Beleg, Teilnehmerliste und Nachweis des Anlasses)",
        "",
        kv([("Bewirtende Person", "Prof. Dr. Konrad Wiesenthal-Bär, FG Verkehrsplanung und Verkehrssysteme"),
            ("Anlass", "Projekttreffen Verbundprojekt MOVE-WS (Mobilitätsstationen im ländlichen Raum)"),
            ("Zweck / dienstl. Interesse", "Abstimmung der Feldphase mit den Verbundpartnern (Tagesordnung anbei)"),
            ("Datum / Ort", f"{wd(meet)}, Gasthaus Zur Alten Fähre, Wernstadt"),
            ("Teilnehmende", "5 Personen: 3 externe Gäste, 2 Universitätsangehörige (Liste anbei)"),
            ("Finanzierung", "Drittmittel, Auftrag 6117-0905 (Bewirtung lt. Zuwendungsbescheid Nr. 4.2)")], k=28),
        "",
        "Betrag",
        f"  Rechnungsbetrag lt. Beleg 2027-004812                        {eur(total)} €",
        f"  Trinkgeld (handschriftlich, nicht erstattungsfähig)           {eur(tip)} €   nicht beantragt",
        f"  Bezahlt mit Kreditkarte                                       {eur(paid)} €",
        f"  Beantragter Erstattungsbetrag                                {eur(total)} €   ({eur(per_person)} € je Person)",
        "",
        f"Wernstadt, {de('2027-07-19')}    Unterschrift Bewirtende/r: [Unterschrift]",
        "Sachlich richtig: Dipl.-Kffr. Anke Dombrowski (Projektverwaltung)   [Unterschrift]",
    ])
    lines = []
    for name, q, p in food + drinks:
        lines.append(f"  {q} x {name:<34}{eur(p):>7}   {eur(q * p):>8}")
    rechnung = "\n".join([
        "GASTHAUS ZUR ALTEN FÄHRE",
        "Inh. Margit Sollmann · Fährweg 2 · 34128 Wernstadt",
        "Tel. 0561 87 21 40 · Steuernummer 026 812 44071",
        "",
        "RECHNUNG Nr. 2027-004812",
        f"Datum: {de(meet)} 13:48     Tisch 12     Kasse 2     Bed. 04",
        "",
        "Rechnungsempfänger: Universität Wernstadt, FG Verkehrsplanung und",
        "Verkehrssysteme, Mönchebergring 7, 34127 Wernstadt",
        "",
        *lines,
        "  " + "-" * 56,
        f"  Summe                                                {eur(total):>8}",
        f"  darin Speisen 7 %:  netto {eur(f_net)}  USt {eur(f_vat)}",
        f"  darin Getränke 19 %: netto {eur(d_net)}  USt {eur(d_vat)}",
        "",
        "  TSE-Signatur: 4F2A-99C1-07B3 · Transaktion 188204 · Seriennr. KA2-0571",
        "",
        "  [handschriftlich:] Trinkgeld 8,50   Gesamt 135,00   bez. VISA ****2208",
        "",
        "Angaben zum Nachweis der Höhe und der betrieblichen Veranlassung",
        "Bewirtete Personen: siehe Teilnehmerliste",
        "Anlass: Projekttreffen MOVE-WS",
        f"Ort / Datum: Wernstadt, {de(meet)}",
        "Unterschrift des Bewirtenden: [Unterschrift] K. Wiesenthal-Bär",
    ])
    liste = "\n".join([
        "Verbundprojekt MOVE-WS · Projekttreffen",
        f"{wdl(meet)}, 10:00 – 15:30 Uhr, Universität Wernstadt, Raum K33-0.104",
        "",
        "Tagesordnung",
        "  10:00   Stand der Arbeitspakete 2 und 3",
        "  11:15   Auswahl der Pilotgemeinden für die Feldphase",
        "  12:30   Mittagessen (Gasthaus Zur Alten Fähre)",
        "  13:45   Zeitplan Befragungen, Datenschutzkonzept",
        "  15:30   Ende",
        "",
        "Teilnehmerliste (G = Gast, U = Universitätsangehörige)",
        "  Nr.  Name                          Institution                                      G/U",
        "  1    Prof. Dr. Konrad Wiesenthal-Bär  Universität Wernstadt (Gastgeber)             U",
        "  2    Dipl.-Ing. Saskia Morgenroth  Universität Wernstadt                            U",
        "  3    Dr. Arvid Lindqvist           Stadtwerke Fuldatal-Nord GmbH (Verbundpartner)   G",
        "  4    Mareen Tepe                   Verkehrsverbund Nordhessen-West (Verbundpartner) G",
        "  5    Holger Ruschmeier             Ingenieurbüro Ruschmeier & Partner (Verbundpartner) G",
    ])
    bescheid = "\n".join([
        "Projektträger Mobilität und Raum (PtMR)",
        "Zuwendungsbescheid zum Verbundprojekt MOVE-WS, Teilvorhaben Universität Wernstadt",
        "Förderkennzeichen 19M27014B · Auszug Seite 4 von 9",
        "",
        "4. Zuwendungsfähige Ausgaben",
        "4.1 Personal- und Sachausgaben gemäß Finanzierungsplan.",
        "4.2 Ausgaben für die Bewirtung von Verbundpartnern bei Projekttreffen sind bis zu 30 Euro je",
        "    Person und Treffen zuwendungsfähig. Trinkgelder sind nicht zuwendungsfähig.",
        "4.3 Reisekosten nach dem Reisekostenrecht des Zuwendungsempfängers.",
    ])
    bundle = "\n\f\n".join([antrag, rechnung, liste, bescheid])
    case(EXP, "auslagenerstattung-c11", "angenommen",
         "Bewirtung von drei externen Verbundpartnern und zwei Universitätsangehörigen beim Projekttreffen MOVE-WS "
         "am 15.07.2027. Die Bewirtungskostenrichtlinie (Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“) lässt "
         "Bewirtungen von Gästen zur Pflege von Kooperationen zu, finanziert aus Drittmitteln; nach dem Glossar "
         "Drittmittelbewirtschaftung müssen die Bewilligungsbedingungen das zulassen, hier erlaubt der "
         "Zuwendungsbescheid (Nr. 4.2) bis 30 € je Person. Es ist kein Arbeitsessen mit überwiegend "
         "Universitätsangehörigen. Die Rechnung erfüllt die Belegpflichten der Richtlinie: maschinell mit "
         "Registriernummer, Speisen und Getränke einzeln, Datum und Ort, Rechnungsempfänger Universität, Betrag "
         "und USt., Anschrift und Steuernummer der Gaststätte, Unterschrift des Bewirtenden, Teilnehmerliste mit "
         "Kennzeichnung der Gäste. Das handschriftliche Trinkgeld von 8,50 € ist nach der Richtlinie nicht "
         "erstattungsfähig und wurde nicht beantragt; beantragt sind 126,50 € (25,30 € je Person). Anzunehmen.",
         [doc("bewirtung-antrag-beleg-teilnehmer.pdf", bundle, title="Bewirtung Projekttreffen MOVE-WS (Scan, 4 Seiten)",
              producer="Canon iR-ADV C5560 (Scan to PDF)")],
         "Business lunch with three external project partners from third-party funds; receipt shows a tip that is correctly not claimed",
         "Bewirtungskostenrichtlinie: „Nicht erstattungsfähige Aufwendungen sind … Aufwendungen für Trinkgelder und "
         "Pfand“; „Einwerbung von Drittmitteln und Kooperationen“; „Die Finanzierung muss aus "
         "Drittmitteln erfolgen.“ + Glossar: „Bewirtungskosten sind nur dann aus Drittmitteln erstattungsfähig, wenn "
         "die Bewilligungs- oder Vertragsbedingungen dies zulassen und das dem zu Grunde liegende Treffen dem "
         "Fortgang des Projekts dient“",
         f"{SRC_FIBU}; {SRC_GLOS}",
         "One scanned 4-page bundle: hospitality claim form, restaurant invoice with TSE line and handwritten tip, agenda and participant list, grant excerpt",
         "yes (looks wrong: restaurant bill with tip)", "high")


# --------------------------------------------------------------------------- #
# c12  abgelehnt (trap): one person claims online-workshop fees paid for three people
# --------------------------------------------------------------------------- #
def c12():
    fee = D("120.00")
    total = r2(fee * 3)
    assert total == D("360.00")
    form = "\n".join([
        lr("Universität Wernstadt", "Abteilung Finanzen – Finanzbuchhaltung", 100),
        "ANTRAG AUF ERSTATTUNG PRIVAT VERAUSLAGTER KOSTEN",
        "",
        kv([("Antragstellerin", "Dr. Paulina Ostrowski-Reim, FB 14, FG Ingenieurhydrologie"),
            ("Erstattung an", "Antragstellerin (Konto lt. Bezügestelle)"),
            ("Kostenstelle / Auftrag", "14460200 (Landesmittel)")], k=26),
        "",
        "  Nr.   Beleg                          Datum         Zweck                                         Betrag",
        f"  1     Invoice EHIN-WS27-0193         {de('2027-02-03')}    Teilnahmegebühren Online-Workshop              {eur(total)} €",
        "                                                       HydroRepro 2027 (23.–24.02.2027, Zoom) für das",
        "                                                       Team: P. Ostrowski-Reim, T. Ekwueme, B. Hollensen",
        f"  Summe                                                                                           {eur(total)} €",
        "",
        "Hinweis der Antragstellerin: Online-Veranstaltung, daher kein Dienstreiseantrag; Abrechnung als privat",
        "verauslagte Kosten. Die Gebühren für alle drei Teilnehmenden wurden mit meiner Kreditkarte bezahlt.",
        "",
        f"Wernstadt, {de('2027-03-01')}    Unterschrift: [Unterschrift]",
        "Sachlich richtig (Fachgebietsleitung): Prof. Dr. Ulrike Hadenfeldt   [Unterschrift]",
    ])
    assert dt('2027-02-23').weekday() == 1
    inv = "\n".join([
        "EUROPEAN HYDRO-INFORMATICS NETWORK (EHIN) e.V.",
        "Hohenzollernring 72 · 50672 Köln · Germany · VAT ID DE 309 551 207",
        "",
        lr("INVOICE EHIN-WS27-0193", f"Date: {de('2027-02-03')}", 96),
        "",
        "Bill to: Universität Wernstadt, FG Ingenieurhydrologie",
        "         attn. Dr. Paulina Ostrowski-Reim",
        "",
        "Event: HydroRepro 2027 – Online Workshop on Reproducible Hydrological Modelling",
        "       23–24 February 2027, online (Zoom)",
        "",
        "  #   Participant                         Ticket                   Amount",
        f"  1   Dr. Paulina Ostrowski-Reim          Academic, online         EUR {eur(fee)}",
        f"  2   Tamo Ekwueme, M.Sc.                 Academic, online         EUR {eur(fee)}",
        f"  3   Birte Hollensen, M.Sc.              Academic, online         EUR {eur(fee)}",
        "",
        f"      Total (exempt from VAT, § 4 Nr. 22a UStG)                    EUR {eur(total)}",
        "",
        "Paid by credit card (VISA ****4471, card holder P. Ostrowski-Reim) on 03.02.2027. Thank you.",
    ])
    stmt = "\n".join([
        "Kreditkartenabrechnung · VISA Classic ****4471 · Paulina Ostrowski-Reim",
        "Abrechnungszeitraum 01.02.2027 – 28.02.2027 (Auszug)",
        "",
        "  Belegdatum   Buchung      Umsatz                                          Betrag EUR",
        "  01.02.2027   02.02.2027   REWE MARKT WERNSTADT                                 -23,18",
        f"  03.02.2027   04.02.2027   EHIN E.V. WORKSHOP KOELN                            -{eur(total)}",
        "  11.02.2027   12.02.2027   STADTWERKE WERNSTADT PARKHAUS                         -6,00",
    ])
    case(EXP, "auslagenerstattung-c12", "abgelehnt",
         "Dr. Ostrowski-Reim beantragt die Erstattung von 360,00 € Teilnahmegebühren für einen Online-Workshop, "
         "die sie laut Rechnung EHIN-WS27-0193 und Kreditkartenabrechnung für sich und zwei Kollegen (je 120,00 €) "
         "bezahlt hat. Der Weg über die privat verauslagten Kosten ist für Online-Veranstaltungen richtig. Nach der "
         "Uni-Kassel-Seite „Dienstreisemanagement“ ist es nach einer Prüfung durch den Hessischen "
         "Landesrechnungshof aber untersagt, Kosten, die für mehrere Personen verauslagt wurden, nur an die "
         "verauslagende Person zu erstatten; die Kolleginnen und Kollegen müssen ihren Anteil selbst zur Erstattung "
         "anfordern, mit einer Quittung der Verauslagenden oder dem Kontoauszug. Erstattungsfähig an die "
         "Antragstellerin wären nur ihre eigenen 120,00 €. In dieser Form abzulehnen.",
         [doc("antrag-privat-verauslagte-kosten.pdf", form, font="Helvetica", title="Erstattung privat verauslagter Kosten"),
          doc("invoice-ehin-ws27-0193.pdf", inv, title="Invoice EHIN-WS27-0193"),
          doc("kreditkartenabrechnung-auszug.pdf", stmt, title="Kreditkartenabrechnung Februar 2027")],
         "Online-workshop fees for three team members paid by one researcher, all claimed by her (English invoice, card statement)",
         "Dienstreisemanagement: „Nach einer Prüfung durch den Hessischen Landesrechnungshof ist es uns untersagt, "
         "Kosten, die für mehrere Personen verauslagt wurden, nur an die verauslagende Person zu erstatten. … Die "
         "Kolleginnen müssen ihren Anteil selber zur Erstattung anfordern, unter Vorlage einer von Ihnen "
         "ausgestellten Quittung oder Kontoauszug bei bargeldloser Zahlung.“",
         SRC_DRM,
         "Claim form (Helvetica), English association invoice listing three participants, credit-card statement excerpt",
         "yes (looks like the accepted online-fee route)", "high")


# --------------------------------------------------------------------------- #
# c13  abgelehnt (trap): self-paid vaccination for an approved trip
# --------------------------------------------------------------------------- #
def c13():
    items = [("Reisemedizinische Beratung (GOÄ Nr. 1, 2,3-fach)", D("10.72")),
             ("Impfung Gelbfieber (GOÄ Nr. 375, 2,3-fach)", D("10.72")),
             ("Impfstoff Gelbfieber, 1 Dosis (Auslage)", D("61.48")),
             ("Eintrag Internationale Impfbescheinigung", D("6.00"))]
    total = tot(*[x for _, x in items])
    assert total == D("88.92")
    online = "\n".join([
        lr("Digitale Abrechnung privat verauslagter Kosten", "Universität Wernstadt · Abteilung Finanzen", 104),
        lr("Eingangsbestätigung", f"Vorgang PVK-2027-03318 · eingereicht {de('2027-09-08')} 16:41", 104),
        "",
        "Antragstellerin      Dr. Merle Ansorge-Diallo (FB 11, FG Agrartechnik in den Tropen und Subtropen)",
        "Kostenzuordnung      Auftrag 6111-0247 (Drittmittel, DAAD-Partnerschaftsprojekt)",
        "",
        "Position 1",
        f"  Belegdatum          {de('2027-09-06')}",
        "  Lieferant           Reisemedizinisches Zentrum Wernstadt, Dr. med. Ulf Hagemeister",
        f"  Betrag              {eur(total)} EUR",
        "  Zweck               Pflichtimpfung Gelbfieber für die genehmigte Dienstreise nach Tamale, Ghana",
        "                      (08.11.–26.11.2027, Reisenummer 4100028331); Gelbfieberimpfung ist",
        "                      Einreisevoraussetzung",
        "  Upload              Rechnung_Reisemedizin_2027-09-06.pdf, Genehmigung_Dienstreise.pdf",
        "",
        f"Gesamtbetrag         {eur(total)} EUR",
        "Status               eingereicht, wartet auf Prüfung",
        "Die Originalbelege sind ein halbes Jahr aufzubewahren.",
    ])
    rows = [f"  {d:<52}{eur(x):>8} €" for d, x in items]
    rechnung = "\n".join([
        "Reisemedizinisches Zentrum Wernstadt",
        "Dr. med. Ulf Hagemeister · Facharzt für Allgemeinmedizin · Gelbfieberimpfstelle",
        "Friedrichsplatz 11 · 34117 Wernstadt",
        "",
        "Frau",
        "Dr. Merle Ansorge-Diallo",
        "Wolfsangerstraße 88",
        "34125 Wernstadt",
        "",
        lr("PRIVATLIQUIDATION Nr. 27-09-1184", f"Rechnungsdatum {de('2027-09-06')}", 90),
        f"Behandlungsdatum: {de('2027-09-06')}    Diagnose: Z24.3 Impfung gegen Gelbfieber",
        "",
        *rows,
        "  " + "-" * 62,
        f"  Rechnungsbetrag                                     {eur(total):>8} €",
        "",
        "Betrag dankend erhalten (EC-Karte), 06.09.2027.",
        "Ärztliche Leistungen sind nach § 4 Nr. 14 UStG umsatzsteuerfrei.",
    ])
    genehm = "\n".join([
        "E-Mail – merle.ansorge-diallo@uni-wernstadt.de" + " " * 24 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox",
        "",
        "  [Extern] Ihr Dienstreiseantrag 4100028331 wurde genehmigt",
        "  Fiori-Reisemanagement, Universität Wernstadt <noreply-reise@uni-wernstadt.de>",
        f"  {wd('2027-08-30')} 07:55",
        "  An: Merle Ansorge-Diallo <merle.ansorge-diallo@uni-wernstadt.de>",
        "",
        "  Guten Tag,",
        "",
        "  Ihr Antrag auf Genehmigung einer Dienstreise (Reisenummer 4100028331, Tamale/Ghana,",
        "  08.11.2027 – 26.11.2027) wurde genehmigt.",
        "",
        "  Bitte kontrollieren Sie Ihren Antrag im Fiori-Reisemanagement auf etwaige Anmerkungen der",
        "  genehmigenden Instanzen.",
        "",
        "  Mit freundlichen Grüßen",
        "  Fiori-Reisemanagement",
    ])
    assert dt('2027-11-08').weekday() == 0
    case(EXP, "auslagenerstattung-c13", "abgelehnt",
         "Beantragt wird die Erstattung von 88,92 € für eine Gelbfieberimpfung mit reisemedizinischer Beratung in "
         "einer privaten Praxis (Privatliquidation vom 06.09.2027) vor der genehmigten Dienstreise nach Ghana. Nach "
         "der Uni-Kassel-Seite „Dienstreisemanagement“ werden notwendige Schutzimpfungen für Dienstreisen durch den "
         "betriebsärztlichen Dienst (MAS) vorgenommen; eine Kostenerstattung für selbstverauslagte Impf- bzw. "
         "Arztkosten ist nicht möglich. Dass die Reise genehmigt ist und die Impfung Einreisevoraussetzung ist, "
         "ändert daran nichts. Der Antrag ist abzulehnen.",
         [doc("pvk-2027-03318-eingangsbestaetigung.pdf", online, font="Helvetica", title="Vorgang PVK-2027-03318",
              producer="Formularserver Finanzen (Pilot)"),
          doc("rechnung-reisemedizin.pdf", rechnung, title="Privatliquidation 27-09-1184"),
          doc("genehmigung-dienstreise.pdf", genehm, title="Ihr Dienstreiseantrag 4100028331 wurde genehmigt")],
         "Yellow-fever vaccination at a private travel clinic before an approved trip to Ghana, claimed as an advanced cost",
         "Dienstreisemanagement: „Notwendige Schutzimpfungen und andere prophylaktische Maßnahmen (z. B. gegen "
         "Malaria) sowie Gesundheitsatteste für Reisen in Infektions- und Epidemiegebiete, die für die Dienstreise "
         "zwingend erforderlich sind, werden ebenfalls durch das MAS vorgenommen.“ and „Eine Kostenerstattung für "
         "selbstverauslagte Impf- bzw. Arztkosten ist nicht möglich.“",
         SRC_DRM,
         "Online-form receipt of the digital advanced-cost process, doctor's private invoice, Fiori approval mail",
         "yes (looks legitimate: approved trip, proper invoice)", "high")


# --------------------------------------------------------------------------- #
# c14  angenommen (trap): mixed till receipt, private items crossed out, only lab share claimed
# --------------------------------------------------------------------------- #
def c14():
    lab = [("4021173", "SCHLEIFPAPIER SET K120-240", D("7.49")),
           ("4518820", "2K EPOXIDKLEBER 25ML", D("12.99")),
           ("3007419", "ISOLIERBAND 3ER PACK", D("3.49"))]
    priv = [("8810452", "BLUMENERDE 40L", D("6.99")),
            ("7740318", "GRILLANZUENDER 32ST", D("3.79"))]
    lab_sum = tot(*[p for *_, p in lab])
    priv_sum = tot(*[p for *_, p in priv])
    total = tot(lab_sum, priv_sum)
    net, vat = vat_split(total, 19)
    assert (lab_sum, priv_sum, total) == (D("23.97"), D("10.78"), D("34.75"))
    buy = '2027-05-07'
    form = "\n".join([
        "Universität Wernstadt – Erstattungsformular für kleinere, dringende Anschaffungen",
        "",
        "Name:            Jannik Hollenbach (techn. Angestellter)",
        "Bereich:         FB 15, FG Werkstofftechnik, Labor Werkstoffprüfung",
        "Kostenstelle:    15230300",
        "",
        "Was wurde gekauft und warum dringend?",
        "  Schleifpapier, 2K-Epoxidkleber und Isolierband zum Nachbessern der Probenhalter;",
        f"  Zugversuche für das Praktikum am {de('2027-05-10')} (Montag), Vorrat im Labor aufgebraucht.",
        "",
        f"Beleg:            Kassenbon Baumarkt Holzmann & Co., Filiale Wernstadt-Nord, {wd(buy)}",
        f"Betrag lt. Bon:   {eur(total)} EUR",
        f"davon privat:     {eur(priv_sum)} EUR (Pos. 4 Blumenerde, Pos. 5 Grillanzünder – auf dem Bon",
        "                  gestrichen und als privat gekennzeichnet, nicht beantragt)",
        f"Erstattungsbetrag: {eur(lab_sum)} EUR",
        "",
        "Originalquittung: aufgeklebt (Rückseite)",
        "",
        f"Wernstadt, {de('2027-05-10')}    Unterschrift: [Unterschrift]",
        "Sachlich richtig (Fachgebietsleitung): Prof. Dr. Gesine Wolters-Amadi   [Unterschrift]",
    ])
    assert dt('2027-05-10').weekday() == 0
    rows = []
    for i, (nr, name, p) in enumerate(lab, 1):
        rows.append(f"{nr} {name:<27}{eur(p):>6} A")
    rows_p = []
    for nr, name, p in priv:
        rows_p.append(f"{nr} {name:<27}{eur(p):>6} A  <- privat")
    bon = "\n".join([
        "   BAUMARKT HOLZMANN & CO.",
        "    Filiale Wernstadt-Nord",
        "   Industriestr. 40, 34123 Wernstadt",
        "    St.-Nr. 026 233 50918",
        "",
        f"{de(buy)}  17:26   Kasse 03  Bon 4471",
        "-" * 42,
        *rows,
        *[r.replace(" A  <- privat", " A") + "  ---" for r in rows_p],
        "-" * 42,
        f"SUMME EUR                         {eur(total):>6}",
        f"EC-KARTE                          {eur(total):>6}",
        "",
        f"A = 19% MwSt  Netto {eur(net)}  MwSt {eur(vat)}",
        "",
        "TSE-Sig. 77AC-1F03-4B9E  Trans. 99812",
        "  Vielen Dank fuer Ihren Einkauf!",
        "",
        "[handschriftlich: Pos. 4 + 5 privat,",
        " nicht beantragt. Pos. 1-3 Labor",
        " Werkstoffpruefung (Probenhalter) J.H.]",
    ])
    case(EXP, "auslagenerstattung-c14", "angenommen",
         "Der Kassenbon des Baumarkts vom 07.05.2027 über 34,75 € enthält drei Laborartikel (Schleifpapier, "
         "Epoxidkleber, Isolierband: 7,49 + 12,99 + 3,49 = 23,97 €) und zwei private Artikel (Blumenerde, "
         "Grillanzünder: 10,78 €), die auf dem Bon gestrichen und als privat gekennzeichnet sind. Beantragt sind "
         "genau die 23,97 € für das Labor. Nach dem Abschnitt Kostenerstattung der Uni-Kassel-Seite "
         "„Finanzbuchhaltung und Steuern“ dürfen kleinere, zeitlich dringende Anschaffungen privat verauslagt und "
         "mit Erstattungsformular und aufgeklebter Originalquittung erstattet werden; der Zweck ist angegeben "
         "(Probenhalter für Zugversuche am folgenden Montag). Die privaten Positionen sind nicht Teil des Antrags, "
         "der Betrag geht auf. Anzunehmen.",
         [doc("erstattungsformular.pdf", form, jitter=0.6, title="Erstattungsformular Scan",
              producer="HP LaserJet MFP (Scan)"),
          doc("kassenbon-baumarkt.pdf", bon, size=RECEIPT, margin=12.0, jitter=0.4, title="Kassenbon 4471")],
         "Hardware-store receipt with three lab items and two private items crossed out; only the lab share (23.97 EUR) is claimed",
         "Finanzbuchhaltung und Steuern, Kostenerstattung: „In Ausnahmefällen kann es sein, dass Angestellte der "
         "Universität kleinere, zeitlich dringende Anschaffungen selbst besorgt haben und diese Auslagen zurück "
         "erstattet haben möchten. … Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung "
         "aufkleben.“ (only the university share is an Auslage for the university)",
         SRC_FIBU,
         "Scanned paper reimbursement form, narrow till receipt with handwritten 'private' marks",
         "yes (looks wrong: receipt contains private items)", "high")


# --------------------------------------------------------------------------- #
# c15  abgelehnt: TH Sallstedt claim lists three receipts, only two attached
# --------------------------------------------------------------------------- #
def c15():
    p1, p2, p3 = D("49.90"), D("46.80"), D("38.60")
    total = tot(p1, p2, p3)
    assert total == D("135.30")
    b_net, b_vat = vat_split(p1, 7)
    c_net, c_vat = vat_split(p3, 19)
    antrag = "\n".join([
        "TECHNISCHE HOCHSCHULE SALLSTEDT · Dezernat 3 – Haushalt, Kasse",
        "ANTRAG AUF ERSTATTUNG VON AUSLAGEN",
        "",
        "Antragsteller:  Dr. Rasmus Vietinghoff, Fakultät Angewandte Chemie, Labor Analytik",
        "Kostenstelle:   5120 (Projekt SEP-27)",
        "",
        "  Nr.  Datum        Gegenstand / Zweck                                               Betrag EUR",
        f"  1    {de('2027-05-12')}   Fachbuch „Praktische Chromatographie“, Buchhandlung Lesezeichen   {eur(p1):>8}",
        f"  2    {de('2027-05-14')}   Kurierversand Probenkiste an Partnerlabor (Expresskurier)         {eur(p2):>8}",
        f"  3    {de('2027-05-18')}   Laborbedarf (Septen, Vials), Chemiehandel Raabe                   {eur(p3):>8}",
        f"       Summe                                                                         {eur(total):>8}",
        "",
        "  Anzahl beigefügter Originalbelege: 3",
        "",
        f"Sallstedt, {de('2027-05-25')}    Unterschrift: [Unterschrift]",
        "Sachlich richtig (Kostenstellenverantwortliche/r): Prof. Dr. Almut Grevenkamp   [Unterschrift]",
        "",
        "Hinweis: Jede Position ist durch einen Originalbeleg nachzuweisen. Unvollständige Anträge werden zur",
        "Ergänzung zurückgegeben.",
    ])
    buch = "\n".join([
        "BUCHHANDLUNG LESEZEICHEN",
        "Marktgasse 5 · 78462 Sallstedt",
        "St.-Nr. 09 104 77821",
        "",
        f"Quittung Nr. 2027-1884     {de('2027-05-12')}",
        "",
        f"1 x Praktische Chromatographie, 4. Aufl.    {eur(p1)}",
        f"Summe EUR                                   {eur(p1)}",
        f"darin 7 % MwSt. {eur(b_vat)}  (netto {eur(b_net)})",
        "bar bezahlt",
        "",
        "Rechnungsempfänger: TH Sallstedt, Labor Analytik",
    ])
    chem = "\n".join([
        "CHEMIEHANDEL RAABE OHG",
        "Laborbedarf · Reagenzien · Glaswaren",
        "Industriering 12 · 78467 Sallstedt",
        "",
        f"Barverkaufsrechnung BV-27-0533     {de('2027-05-18')}",
        "Kunde: Technische Hochschule Sallstedt, Labor Analytik (Dr. Vietinghoff)",
        "",
        "  1 Pck  Septen PTFE/Silikon, 9 mm, 100 St.               17,90",
        "  1 Pck  Schraubvials 1,5 ml, braun, 100 St.              20,70",
        f"  Summe brutto                                           {eur(p3)}",
        f"  darin 19 % MwSt. {eur(c_vat)}  (netto {eur(c_net)})",
        "",
        "  Betrag bar erhalten.",
    ])
    assert tot("17.90", "20.70") == p3
    bundle = "\n\f\n".join([antrag, buch, chem])
    case(EXP, "auslagenerstattung-c15", "abgelehnt",
         "Fall der TH Sallstedt, entschieden auf den eigenen Unterlagen. Der Erstattungsantrag nennt drei "
         "Positionen über zusammen 135,30 € und gibt drei beigefügte Originalbelege an. Beigefügt sind aber nur die "
         "Quittung der Buchhandlung (49,90 €) und die Barverkaufsrechnung des Chemiehandels (38,60 €); für "
         "Position 2, Kurierversand über 46,80 €, fehlt jeder Beleg. Der Vordruck der TH Sallstedt verlangt für "
         "jede Position einen Originalbeleg und gibt unvollständige Anträge zur Ergänzung zurück. Der Antrag ist "
         "abzulehnen.",
         [doc("auslagenerstattung-scan.pdf", bundle, jitter=1.0, title="Scan_0525_Vietinghoff",
              producer="Kyocera TASKalfa (Scan)")],
         "TH Sallstedt: claim with three positions and 'three receipts attached', but the courier receipt (46.80 EUR) is missing",
         "Sallstedt's own claim form: „Jede Position ist durch einen Originalbeleg nachzuweisen. Unvollständige "
         "Anträge werden zur Ergänzung zurückgegeben.“ + organisers' README (Sallstedt decided on the documents alone)",
         SRC_SAL,
         "One scanned multi-page PDF: TH Sallstedt claim form, bookshop receipt, cash-sale invoice",
         "no", "high")


# =========================================================================== #
# Build and verify
# =========================================================================== #
WEEKDAY_RX = re.compile(
    r"\b(Mo|Di|Mi|Do|Fr|Sa|So|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|"
    r"Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?,? (\d{2})\.(\d{2})\.(\d{4})")
WD_ALL = {**{s: i for i, s in enumerate(WD_S)}, **{s: i for i, s in enumerate(WD_L)},
          **{s: i for i, s in enumerate(WD_EN)}}


def words(text):
    return text.split()


def build():
    for fn in [c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13, c14, c15]:
        fn()
    if OUT.exists():
        shutil.rmtree(OUT)
    problems = []
    n_pdf = 0
    for c in CASES:
        d = OUT / c["set"] / "inputs" / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        for name, text, opts in c["docs"]:
            for m in WEEKDAY_RX.finditer(text):
                day = datetime.date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
                if WD_ALL[m.group(1)] != day.weekday():
                    problems.append(f"{c['id']}/{name}: weekday mismatch '{m.group(0)}'")
            p = d / name
            write_pdf(p, text, **opts)
            n_pdf += 1
            got = words(pdftotext(p))
            want = words(text.replace("\f", "\n"))
            if got != want:
                k = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
                problems.append(f"{c['id']}/{name}: round-trip differs at word {k}: "
                                f"got {got[k:k + 6]} want {want[k:k + 6]}")
    for s in SETS:
        rows = [c for c in CASES if c["set"] == s]
        with open(OUT / s / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for c in rows:
                f.write(json.dumps({"antrag": c["id"], "result": c["result"], "begruendung": c["begruendung"],
                                    "belege": []}, ensure_ascii=False) + "\n")
    (OUT / "PROPOSALS.md").write_text(table(), encoding="utf-8")
    return n_pdf, problems


def table():
    n_a = sum(c["result"] == "angenommen" for c in CASES)
    n_t = sum(c["trap"].startswith("yes") for c in CASES)
    out = [
        "# Blind set 3: proposals (15 cases, pick 10)",
        "",
        "Built by `experiments/blind3/tools/make_blind3.py`, written blind (no solver code, tests, earlier "
        "experiment sets or their docs were read). Each label follows from the quoted rule. Sources: policy "
        "pages in `the University of Kassel policy pages (not included here)` (corpus doc ids given), HRKG from the hessian-law corpus, and "
        "the organisers' README for the TH Sallstedt cases.",
        "",
        f"Labels: {n_a} angenommen, {len(CASES) - n_a} abgelehnt. Traps: {n_t}. Every PDF round-trips through "
        "`pdftotext -layout`; sums and weekdays are computed and asserted in the script.",
        "",
        "| id | description | label | deciding rule (verbatim) + source | imitated system / layout | trap | confidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in CASES:
        cells = [c["id"], c["desc"], c["result"], f"{c['rule']} — {c['source']}", c["imitates"], c["trap"],
                 c["conf"]]
        out.append("| " + " | ".join(x.replace("|", "/") for x in cells) + " |")
    out.append("")
    return "\n".join(out)


def main():
    if "--table" in sys.argv:
        for fn in [c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13, c14, c15]:
            fn()
        print(table())
        return
    n_pdf, problems = build()
    print(f"built {len(CASES)} cases, {n_pdf} PDFs in {OUT}")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
