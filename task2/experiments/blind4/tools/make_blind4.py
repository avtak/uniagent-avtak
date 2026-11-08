#!/usr/bin/env python3
"""Build the fourth BLIND proposal set for UniAgent Task 2 (15 cases, the author picks 10).

Written blind: without the solver (facts.py, rules.py, predict.py, parsing.py, case_tools.py,
rule_search.py), its tests, the earlier experiment sets or the docs that describe them. Sources:
the policy pages in the University of Kassel policy pages (not included here), the organisers' practice data (READMEs, ground
truth, decision trails) and grep over the retrieval corpora. Every label rests on a rule quoted
verbatim in experiments/blind4-proposals/PROPOSALS.md.

Only the PDF writer, the layout/money/date helpers and the pdftotext call are reused from
experiments/blind3/tools/make_blind3.py (pure Python, base-14 fonts, WinAnsi, one text line per
line).

    python3 experiments/blind4/tools/make_blind4.py           # build + verify
    python3 experiments/blind4/tools/make_blind4.py --table   # print the proposals table

Output (overwritten): experiments/blind4-proposals/<set>/{inputs/<case>/*.pdf,
ground-truth.jsonl} and experiments/blind4-proposals/PROPOSALS.md.
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
OUT = HERE.parent.parent / "blind4-proposals"
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

A4 = (595.28, 841.89)
RECEIPT = (226.77, 700.0)


# --------------------------------------------------------------------------- #
# Minimal PDF writer (reused from experiments/blind3/tools/make_blind3.py)
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
# Helpers: layout, money, dates (reused from make_blind3.py, plus a few)
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


def en(x):  # English number format 1,234.50
    return f"{r2(x):,.2f}"


def tot(*xs):
    return r2(sum(D(x) for x in xs))


def vat_split(gross, rate):
    """net and VAT contained in a gross amount"""
    net = r2(D(gross) / (1 + D(rate) / 100))
    return net, r2(D(gross) - net)


def vat_of(net, rate):
    return r2(D(net) * D(rate) / 100)


def row(cells, widths, aligns=None):
    """one table row; aligns: 'l' or 'r' per column; columns separated by at least 2 spaces"""
    aligns = aligns or "l" * len(cells)
    out = []
    for c, w, a in zip(cells, widths, aligns):
        c = str(c)
        out.append(c.rjust(w) if a == "r" else c.ljust(w))
    return "  ".join(out).rstrip()


WD_S = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WD_L = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


def dt(s):
    return datetime.date.fromisoformat(s)


def de(s):
    return dt(s).strftime("%d.%m.%Y")


def de2(s):  # 25.05.27
    return dt(s).strftime("%d.%m.%y")


def wd(s):  # "Mo 21.06.2027"
    return f"{WD_S[dt(s).weekday()]} {de(s)}"


def wdl(s):  # "Montag, 21.06.2027"
    return f"{WD_L[dt(s).weekday()]}, {de(s)}"


def wde_long(s):  # "Montag, 7. Juni 2027"
    d = dt(s)
    return f"{WD_L[d.weekday()]}, {d.day}. {MON_DE[d.month - 1]} {d.year}"


def wen(s):  # "Tue, 16 Mar 2027"
    d = dt(s)
    return f"{WD_EN[d.weekday()]}, {d.day:02d} {MON_EN[d.month - 1]} {d.year}"


def en_date(s):  # "08 Mar 2027"
    d = dt(s)
    return f"{d.day:02d} {MON_EN[d.month - 1]} {d.year}"


def days_between(a, b):
    return (dt(b) - dt(a)).days


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
SRC_DVK = "Uni-Kassel-Seite „Druckauftrag Visitenkarte“ (doc 6d727cc2-ddb8-4d8a-850b-2ae520e6351e)"
SRC_GF = "Uni-Kassel-Seite „Gerätefondsverfahren“ (doc 835ca50e-172f-4a99-9462-b58f6861a199)"
SRC_GLOS = "Uni-Kassel-Seite „Glossar Drittmittelbewirtschaftung“ (doc ab40fc4f-638f-4898-b501-40fc33916ac4)"
SRC_GT_P07 = "Begründung der Organisatoren, task-2-procurement-spot-check/ground-truth.jsonl, beschaffungsantrag-07"
SRC_DT_P07 = "Entscheidungsmail der Organisatoren, decision-trail/beschaffungsantrag-07/email-rueckfrage-beschaffung.pdf"
SRC_GT_E06 = "Begründung der Organisatoren, task-2-expense-reimbursement-spot-check/ground-truth.jsonl, auslagenerstattung-06"
SRC_GT_E05 = "Begründung der Organisatoren, task-2-expense-reimbursement-spot-check/ground-truth.jsonl, auslagenerstattung-05"
SRC_SAL = ("README der Organisatoren (task-2-expense-reimbursement-spot-check): Sallstedt-Fälle werden „on the "
           "documents alone“ entschieden; Regel steht auf dem Formular HA-07 der TH selbst")

HDR_OWA = "E-Mail – {who}@uni-wernstadt.de" + " " * 30 + "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox"
UW_ADDR = "Mönchebergstraße 19 · 34109 Wernstadt"

FIORI_HEAD = "SAP Fiori · Meine Reisen · Universität Wernstadt"


def fiori_request(nr, created, status, person, persnr, org, rows_general, rows_route, cost_rows, cost_sum,
                  financing, remarks, attachments, signer_date, assist=None):
    """SAP Fiori 'Reiseantrag' print view."""
    lines = [
        lr(FIORI_HEAD, f"Druckansicht {de(created)}"),
        "",
        lr(f"Reiseantrag {nr}", f"Status: {status}"),
        lr(f"Reisende Person: {person}  (Pers.-Nr. {persnr})", f"angelegt am {de(created)}"),
        f"Organisationseinheit: {org}",
    ]
    if assist:
        lines.append(f"Erfasst durch Reiseassistenz: {assist}")
    lines += ["", "ALLGEMEINE DATEN", kv(rows_general, k=34), "", "REISEVERLAUF", kv(rows_route, k=34), "",
              "GESCHÄTZTE KOSTEN",
              "  " + row(["Kostenart", "Erläuterung", "Betrag"], [30, 54, 12], "llr")]
    for a, b, c in cost_rows:
        lines.append("  " + row([a, b, eur(c) + " €"], [30, 54, 12], "llr"))
    lines += ["  " + row(["Summe geschätzte Kosten", "", eur(cost_sum) + " €"], [30, 54, 12], "llr"), "",
              "FINANZIERUNG", kv(financing, k=34), "", "BEMERKUNGEN"]
    lines += ["  " + r for r in remarks] if remarks else ["  —"]
    lines += ["", "ANLAGEN"] + ["  " + a for a in attachments]
    lines += ["", f"Mit dem Absenden versichere ich die Richtigkeit der Angaben. Gesendet am {de(signer_date)}.",
              "", lr("Erstellt mit SAP Fiori · App „Meine Reisen und Reiseabrechnungen“", "Seite 1 von 1")]
    return "\n".join(lines)


def owa_mail(who, subject, sender, when, to, body, cc=None, footer_when=None):
    lines = [HDR_OWA.format(who=who), "", f"  {subject}", f"  {sender}", f"  {when}", f"  An: {to}"]
    if cc:
        lines.append(f"  Cc: {cc}")
    lines.append("")
    lines += ["  " + l if l else "" for l in body]
    lines += ["", lr("Seite 1", footer_when or when.split(" ", 1)[-1])]
    return "\n".join(lines)


# =========================================================================== #
# BUSINESS TRIPS
# =========================================================================== #

# --------------------------------------------------------------------------- #
# d01  abgelehnt: domestic flight (Frankfurt-Berlin) without the required justification
# --------------------------------------------------------------------------- #
def d01():
    created = "2027-02-15"
    out_d, back_d = "2027-03-16", "2027-03-17"
    flight = D("286.40")
    rail = r2(2 * D("49.90"))
    hotel = D("79.00")
    total = tot(flight, rail, hotel)
    assert total == D("465.20")
    nr = "4417203381"
    antrag = fiori_request(
        nr, created, "Antrag eingereicht – in Genehmigung", "Dr. Lennart Asmussen-Weil", "052318",
        "FB 16 Elektrotechnik/Informatik · FG Energiemanagement und Betrieb elektrischer Netze",
        [("Reiseziel", "Berlin, DEUTSCHLAND"),
         ("Reise ins Ausland", "nein"),
         ("Anlass", "Statusseminar Verbundprojekt NetzFlex (Projektträger Energie)"),
         ("Grund der Reise", "Vortrag Arbeitspaket 3 „Lastflexibilität in Verteilnetzen“"),
         ("Reiseart", "Dienstreise"),
         ("Verkehrsmittel", "Flugzeug (Frankfurt FRA – Berlin BER), Bahn bis Flughafen"),
         ("Begründung Flug im Inland", "—"),
         ("(Pflichtangabe, ggf. Anlage)", ""),
         ("Datum der Antragstellung", de(created))],
        [("Beginn der Reise", f"{wd(out_d)}, 05:40 Uhr (Wohnung)"),
         ("Ende der Reise", f"{wd(back_d)}, 21:10 Uhr (Wohnung)"),
         ("Beginn Dienstgeschäft", f"{de(out_d)}, 11:00 Uhr"),
         ("Ende Dienstgeschäft", f"{de(back_d)}, 14:30 Uhr"),
         ("Privater Aufenthalt", "keiner"),
         ("Übernachtungen", "1 (Hotel am Tagungsort)")],
        [("Flug", "FRA–BER–FRA, Economy (Buchung Reiseportal)", flight),
         ("Bahn", "Wernstadt–Frankfurt Flughafen Fernbf., hin/zurück", rail),
         ("Übernachtung", "1 Nacht à 79,00 €", hotel)],
        total,
        [("Kostenstelle / Auftrag", "16 2240 / Auftrag 6-4410217 (Drittmittel NetzFlex)"),
         ("Abschlag beantragt", "nein")],
        [],
        ["Einladung_Statusseminar_NetzFlex.pdf", "Flugbuchung_Reiseportal.pdf"],
        created)
    portal = "\n".join([
        lr("trvlbooker business · Booking confirmation / Buchungsbestätigung", "printed " + en_date(created)),
        "",
        "Booking reference / Buchungscode:   QX7-M4R2LP",
        "Traveller / Reisender:              ASMUSSEN-WEIL / LENNART DR",
        "Company / Firma:                    Universitaet Wernstadt, FG Energiemanagement",
        "Booked on / gebucht am:             " + en_date(created),
        "",
        "FLIGHTS",
        "  " + row(["Flight", "Date", "From", "Dep", "To", "Arr", "Class"], [8, 18, 18, 6, 16, 6, 14]),
        "  " + row(["AL 1074", wen(out_d), "Frankfurt FRA T1", "08:05", "Berlin BER T1", "09:15", "Economy Light"],
                   [8, 18, 18, 6, 16, 6, 14]),
        "  " + row(["AL 1081", wen(back_d), "Berlin BER T1", "17:40", "Frankfurt FRA T1", "18:50", "Economy Light"],
                   [8, 18, 18, 6, 16, 6, 14]),
        "",
        "Baggage: 1 x 8 kg cabin bag. No checked baggage included.",
        "",
        "PRICE / PREIS",
        "  " + row(["Fare / Tarif", en(D("198.00")) + " EUR"], [40, 16], "lr"),
        "  " + row(["Taxes, fees and charges", en(D("80.41")) + " EUR"], [40, 16], "lr"),
        "  " + row(["Service fee trvlbooker", en(D("7.99")) + " EUR"], [40, 16], "lr"),
        "  " + row(["Total charged to card ****4471", en(flight) + " EUR"], [40, 16], "lr"),
        "",
        "Ticket number: 220-4418820193 · e-ticket issued",
        "Changes: not permitted. Refund: taxes only.",
        "",
        "trvlbooker GmbH · Hafenstraße 12 · 20359 Hamburg · www.trvlbooker.example",
    ])
    assert tot("198.00", "80.41", "7.99") == flight
    einladung = owa_mail(
        "lennart.asmussen-weil",
        "Einladung zum Statusseminar NetzFlex am 16./17. März 2027 in Berlin",
        "Projektträger Energie – Statusseminare <statusseminare@pt-energie.example>",
        "Mi 03.02.2027 10:14",
        "Verteiler Verbundprojekt NetzFlex",
        ["Sehr geehrte Damen und Herren,",
         "",
         "wir laden Sie herzlich zum Statusseminar des Verbundprojekts NetzFlex ein.",
         "",
         f"Termin:   {wd(out_d)}, 11:00 Uhr bis {wd(back_d)}, 14:30 Uhr",
         "Ort:      Tagungszentrum am Spreebogen, Alt-Moabit 96, 10559 Berlin",
         "",
         "Jedes Teilvorhaben stellt seinen Arbeitsstand in einem Vortrag von 20 Minuten vor. Für die",
         "Universität Wernstadt ist der Vortrag zu AP 3 am ersten Tag um 14:00 Uhr vorgesehen.",
         "Reisekosten werden aus den Projektmitteln der Teilvorhaben getragen.",
         "",
         "Mit freundlichen Grüßen",
         "Ihr Team Statusseminare"],
        footer_when="03.02.2027 10:14")
    begr = ("Für die Inlandsreise nach Berlin (16.–17.03.2027) ist ein Flug Frankfurt–Berlin über 286,40 € "
            "beantragt. Nach der Uni-Kassel-Seite „Dienstreisemanagement“ kommen Flugkosten im Inland "
            "grundsätzlich nur in Betracht, wenn ein anderes regelmäßig verkehrendes Beförderungsmittel höhere "
            "Kosten verursacht oder besondere dienstliche Gründe vorliegen; diese sind in einer Anlage zur "
            "Genehmigung darzulegen. Das Feld „Begründung Flug im Inland“ ist leer, eine Anlage oder ein "
            "Vergleich mit der Bahnfahrt liegt nicht bei. Der Antrag ist unvollständig und zur Ergänzung "
            "zurückzugeben.")
    case(TRIP, "dienstreiseantrag-d01", "abgelehnt", begr,
         [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica"),
          doc("flugbuchung-reiseportal.pdf", portal, font="Helvetica"),
          doc("email-einladung-statusseminar.pdf", einladung, font="Helvetica")],
         "Domestic trip to Berlin by plane (FRA-BER), justification field for a domestic flight empty, no attachment or rail comparison",
         "„Flugkosten kommen im Inland grundsätzlich nur in Betracht, wenn bei Benutzung eines anderen regelmäßig "
         "verkehrenden Beförderungsmittels höhere Kosten entstehen oder besondere dienstliche Gründe (wesentliche "
         "Einsparung von Arbeitszeit) vorliegen. Diese sind in einer Anlage zur Genehmigung der Dienstreise darzulegen.“",
         SRC_DRM, "SAP Fiori Reiseantrag print + travel-portal booking (EN/DE) + Outlook mail", "no", "high")


# --------------------------------------------------------------------------- #
# d02  angenommen (trap): professor, domestic, 2 days, request filed after the trip
# --------------------------------------------------------------------------- #
def d02():
    out_d, back_d, created = "2027-04-14", "2027-04-15", "2027-04-19"
    assert dt(created) > dt(back_d)
    rail = r2(2 * D("59.90"))
    hotel = D("78.00")
    fee = D("240.00")
    total = tot(rail, hotel, fee)
    assert total == D("437.80")
    antrag = fiori_request(
        "4417206610", created, "Antrag eingereicht", "Prof. Dr. Henrike Dalhoff-Brenner", "031177",
        "FB 14 Bauingenieur- und Umweltingenieurwesen · FG Siedlungswasserwirtschaft",
        [("Reiseziel", "Dresden, DEUTSCHLAND"),
         ("Reise ins Ausland", "nein"),
         ("Anlass", "Fachtagung Regenwasserbewirtschaftung 2027"),
         ("Grund der Reise", "Teilnahme und Leitung der Sitzung „Starkregenvorsorge“"),
         ("Reiseart", "Dienstreise"),
         ("Verkehrsmittel", "Bahn, 2. Klasse"),
         ("Datum der Antragstellung", de(created))],
        [("Beginn der Reise", f"{wd(out_d)}, 06:52 Uhr (Wohnung)"),
         ("Ende der Reise", f"{wd(back_d)}, 20:31 Uhr (Wohnung)"),
         ("Beginn Dienstgeschäft", f"{de(out_d)}, 10:30 Uhr"),
         ("Ende Dienstgeschäft", f"{de(back_d)}, 15:00 Uhr"),
         ("Privater Aufenthalt", "keiner"),
         ("Übernachtungen", "1")],
        [("Bahn", "Wernstadt–Dresden Hbf hin/zurück, 2. Kl. Flexpreis", rail),
         ("Übernachtung", "1 Nacht inkl. Frühstück", hotel),
         ("Teilnahmegebühr", "Fachtagung, Frühbucher", fee)],
        total,
        [("Kostenstelle / Auftrag", "14 3110 (Landesmittel Fachgebiet)"),
         ("Abschlag beantragt", "nein")],
        ["Reise im Sekretariat nachträglich erfasst; Belege der durchgeführten Reise sind angehängt."],
        ["Tagungsprogramm_und_Anmeldung.pdf", "Hotelrechnung_Dresden.pdf", "Bahnticket.pdf"],
        created, assist="Jana Pieczonka (Sekretariat FG Siedlungswasserwirtschaft)")
    net_room, vat_room = vat_split(D("66.00"), 7)
    net_bf, vat_bf = vat_split(D("12.00"), 19)
    assert tot("66.00", "12.00") == hotel
    hotelr = "\n".join([
        lr("HOTEL ELBTERRASSE DRESDEN", "Rechnung Nr. 27-04-1882"),
        "Terrassenufer 9 · 01069 Dresden · USt-IdNr. DE 278 114 905",
        "",
        "Universität Wernstadt",
        "FG Siedlungswasserwirtschaft",
        "Frau Prof. Dr. Henrike Dalhoff-Brenner",
        UW_ADDR,
        "",
        lr("Gast: Prof. Dr. Henrike Dalhoff-Brenner", f"Rechnungsdatum: {de(back_d)}"),
        lr(f"Anreise: {de(out_d)}   Abreise: {de(back_d)}", "Zimmer 314"),
        "",
        row(["Datum", "Leistung", "Menge", "Betrag"], [12, 52, 6, 12], "llrr"),
        row([de(out_d), "Übernachtung Einzelzimmer", "1", eur(66) + " €"], [12, 52, 6, 12], "llrr"),
        row([de(back_d), "Frühstücksbuffet", "1", eur(12) + " €"], [12, 52, 6, 12], "llrr"),
        "",
        row(["", "Gesamtbetrag", "", eur(hotel) + " €"], [12, 52, 6, 12], "llrr"),
        row(["", f"darin USt 7 % auf {eur(net_room)} €", "", eur(vat_room) + " €"], [12, 52, 6, 12], "llrr"),
        row(["", f"darin USt 19 % auf {eur(net_bf)} €", "", eur(vat_bf) + " €"], [12, 52, 6, 12], "llrr"),
        "",
        "Bezahlt mit Kreditkarte (Mastercard ****2207) am " + de(back_d) + ".",
        "Vielen Dank für Ihren Aufenthalt.",
    ])
    programm = "\n".join([
        "Fachtagung Regenwasserbewirtschaftung 2027 · Dresden",
        "Anmeldebestätigung und Programm",
        "",
        "Teilnehmerin:   Prof. Dr. Henrike Dalhoff-Brenner, Universität Wernstadt",
        "Anmeldung vom:  " + de("2027-02-10") + "   ·   Teilnahmegebühr (Frühbucher): " + eur(fee) + " € (bezahlt)",
        "",
        f"{wdl(out_d)}",
        "  10:30  Eröffnung",
        "  11:00  Sitzung 1: Starkregenvorsorge (Sitzungsleitung: Prof. Dr. H. Dalhoff-Brenner)",
        "  14:00  Sitzung 2: Versickerung und Retention im Bestand",
        "  18:30  Abendempfang (optional, nicht in der Gebühr enthalten)",
        f"{wdl(back_d)}",
        "  09:00  Sitzung 3: Blau-grüne Infrastruktur",
        "  13:00  Sitzung 4: Bemessung und Monitoring",
        "  15:00  Ende der Tagung",
        "",
        "Veranstalter: Fachverband Siedlungswasser e. V. · Kongressbüro · 01067 Dresden",
    ])
    ticket = "\n".join([
        "Online-Ticket · Fernverkehr",
        "",
        "Fahrkarte Flexpreis, 2. Klasse, 1 Erwachsener · Hin- und Rückfahrt",
        f"Hinfahrt:  {wd(out_d)}  Wernstadt-Wilhelmshöhe 07:14 -> Dresden Hbf 10:02 (ICE 1557, Umstieg Erfurt)",
        f"Rückfahrt: {wd(back_d)}  Dresden Hbf 15:58 -> Wernstadt-Wilhelmshöhe 19:59 (IC 2156, Umstieg Leipzig)",
        "",
        lr("Gesamtpreis", eur(rail) + " €", 60),
        "Reisende: Henrike Dalhoff-Brenner · Zahlung: Kreditkarte · Auftragsnummer 6YB2QK",
        f"Gebucht am {de('2027-03-29')}",
    ])
    begr = ("Der Reiseantrag wurde erst am 19.04.2027 erfasst, die Reise nach Dresden fand am 14.–15.04.2027 statt. "
            "Antragstellerin ist aber eine Professorin, die Reise ist eine Inlandsdienstreise von zwei Tagen. Nach "
            "der Uni-Kassel-Seite „Dienstreisemanagement“ (Präsidiumsbeschluss 656 vom 21.07.2025) gelten "
            "Dienstreisen im Inland bis sieben Tage für Professorinnen und Professoren qua Amt als genehmigt "
            "(§ 2 Abs. 1 Satz 2 HRKG); eine vorherige Genehmigung war nicht erforderlich. Die Belege sind in "
            "Ordnung: Bahn 2. Klasse, Hotel 78,00 € je Nacht (unter 80 €) auf die Universität ausgestellt, "
            "Tagungsprogramm belegt das dienstliche Interesse, der optionale Abendempfang ist nicht beantragt. "
            "Der Antrag wird angenommen.")
    case(TRIP, "dienstreiseantrag-d02", "angenommen", begr,
         [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica"),
          doc("hotelrechnung-dresden.pdf", hotelr),
          doc("tagungsprogramm-anmeldung.pdf", programm, font="Helvetica"),
          doc("bahnticket.pdf", ticket)],
         "Professor's 2-day domestic conference trip entered in Fiori four days after the trip; documents otherwise compliant",
         "„Mit dem Präsidiumsbeschluss 656 vom 21.07.2025 gelten Dienstreisen und Reisen zum Zwecke der Fortbildung "
         "im Inland mit einer Dauer von bis sieben Tagen für Professorinnen und Professoren mit sofortiger Wirkung "
         "grundsätzlich qua Amt als genehmigt gem. § 2 Abs. 1 Satz 2 Hessisches Reisekostengesetz.“",
         SRC_DRM, "SAP Fiori print (entered by travel assistant) + hotel invoice + programme + rail e-ticket",
         "yes (late request looks like 'no prior approval')", "low")


# --------------------------------------------------------------------------- #
# d03  abgelehnt: excursion – filed 6 days before start, 3 companions for 22 students without reasons
# --------------------------------------------------------------------------- #
def d03():
    start, end = "2027-06-07", "2027-06-09"
    signed, received = "2027-05-31", "2027-06-01"
    assert days_between(received, start) == 6
    n_stud, n_beg = 22, 3
    bus = D("2380.00")
    hostel = r2((n_stud + 1 + n_beg) * 2 * D("31.50"))
    assert hostel == D("1638.00")
    eigen = r2(n_stud * D("45.00"))
    total = tot(bus, hostel)
    students = ["A. Bergmann", "L. Çelik", "J. Dannenberg", "M. Ebeling", "S. Fahrenholz", "T. Grabowski",
                "K. Hinrichs", "N. Ilgner", "P. Jovanovic", "R. Kowalczyk", "E. Lindqvist", "F. Matuschek",
                "C. Nowotny", "D. Okonkwo", "H. Petersen", "I. Quast", "B. Rademacher", "G. Sauerland",
                "V. Tschentscher", "W. Ulbrich", "Y. Vogelsang", "Z. Wittkamp"]
    assert len(students) == n_stud
    p1 = "\n".join([
        "Universität Wernstadt                                         [Eingangsstempel]",
        "Abteilung Personal und Organisation                           EINGEGANGEN",
        "- Exkursionssachbearbeitung -                                 Dekanat FB 14",
        f"                                                              {de(received)}",
        "",
        "ANTRAG AUF GENEHMIGUNG EINER EXKURSION",
        "(vollständig ausgefüllt mind. 14 Tage vor Beginn über das Dekanat einreichen)",
        "",
        "1. Exkursionsleitung",
        "   Name, Titel:        Dr.-Ing. Malte Vorderbrügge",
        "   Fachgebiet:         FB 14 · FG Wasserbau und Wasserwirtschaft",
        "   Lehrveranstaltung:  Wasserbauliches Seminar (M.Sc. Umweltingenieurwesen), SoSe 2027",
        "",
        "2. Art der Exkursion   [ ] Pflichtexkursion   [X] Studienexkursion",
        "",
        "3. Ziel / Programm     Hochwasserschutz und Talsperren im Sauerland",
        "                       (Talsperrenleitzentrale, zwei Stauanlagen, Hochwasserrückhaltebecken)",
        f"   Zeitraum:            {wd(start)} bis {wd(end)}",
        "   Unterkunft:          Jugendherberge am Sorpesee, 2 Nächte",
        "",
        f"4. Teilnehmende        Studierende: {n_stud}     Begleitpersonen (ohne Leitung): {n_beg}",
        "   Begleitpersonen:     M.Sc. Ilka Brandstetter (wiss. Mitarbeiterin)",
        "                        M.Sc. Torben Akyüz-Rehm (wiss. Mitarbeiter)",
        "                        Dipl.-Ing. Wolfram Siebeneicher (techn. Mitarbeiter)",
        "   Gesonderte Begründung, falls mehr als eine Begleitperson je 15 Studierende:",
        "                        ______________________________________________ (nicht ausgefüllt)",
        "",
        "5. Kosten (geschätzt)",
        "   Busunternehmen (Angebot liegt bei)            " + eur(bus).rjust(10) + " €",
        f"   Jugendherberge {n_stud + 1 + n_beg} Pers. x 2 Nächte x 31,50 €     " + eur(hostel).rjust(10) + " €",
        "   Summe                                         " + eur(total).rjust(10) + " €",
        f"   Eigenanteil Studierende ({n_stud} x 45,00 €)          " + eur(eigen).rjust(10) + " €",
        "   Abschlag beantragt:  [ ] ja   [X] nein",
        "",
        "6. Finanzierung        Kostenstelle 14 3420, Studienstrukturmittel Exkursionen",
        "",
        f"Wernstadt, {de(signed)}     gez. M. Vorderbrügge          [Unterschrift unleserlich]",
        "                         Exkursionsleitung             Dekanat FB 14 (Kenntnisnahme)",
        "",
        "Seite 1/2                                          Scan Kopierer 3.OG · " + de(received) + " 11:42",
    ])
    lst = ["TEILNEHMERLISTE  Studienexkursion Sauerland  " + de(start) + " - " + de(end), "",
           "Nr.  Name (gekürzt)         Status", "---  ---------------------  ------------------------"]
    for i, s in enumerate(students, 1):
        lst.append(f"{i:>3}  {s:<21}  Studierende/r M.Sc. UIW")
    lst += [f"{n_stud + 1:>3}  {'M. Vorderbrügge':<21}  Exkursionsleitung",
            f"{n_stud + 2:>3}  {'I. Brandstetter':<21}  Begleitperson",
            f"{n_stud + 3:>3}  {'T. Akyüz-Rehm':<21}  Begleitperson",
            f"{n_stud + 4:>3}  {'W. Siebeneicher':<21}  Begleitperson",
            "", "Seite 2/2"]
    scan = p1 + "\f" + "\n".join(lst)
    fiori = fiori_request(
        "4417209054", signed, "Antrag eingereicht", "Dr.-Ing. Malte Vorderbrügge", "047702",
        "FB 14 Bauingenieur- und Umweltingenieurwesen · FG Wasserbau und Wasserwirtschaft",
        [("Reiseziel", "Sundern (Sauerland), DEUTSCHLAND"),
         ("Reise ins Ausland", "nein"),
         ("Anlass", "Leitung Studienexkursion Hochwasserschutz und Talsperren"),
         ("Reiseart", "Dienstreise (Exkursionsleitung)"),
         ("Verkehrsmittel", "Reisebus der Exkursion"),
         ("Datum der Antragstellung", de(signed))],
        [("Beginn der Reise", f"{wd(start)}, 07:30 Uhr (Dienststätte)"),
         ("Ende der Reise", f"{wd(end)}, 18:00 Uhr (Dienststätte)"),
         ("Privater Aufenthalt", "keiner")],
        [("Übernachtung", "2 Nächte Jugendherberge (über Exkursion)", D("0.00")),
         ("Fahrtkosten", "Reisebus (über Exkursion)", D("0.00"))],
        D("0.00"),
        [("Kostenstelle / Auftrag", "14 3420")],
        ["Kosten laufen über den Exkursionsantrag."],
        ["Exkursionsantrag_mit_Teilnehmerliste.pdf"], signed)
    busang = "\n".join([
        "REISEDIENST HOLLENBACH GmbH & Co. KG",
        "Omnibusbetrieb · Am Lohfeld 4 · 34497 Korbach",
        "",
        "Universität Wernstadt, FG Wasserbau und Wasserwirtschaft, Herrn Dr.-Ing. M. Vorderbrügge",
        "",
        lr("ANGEBOT Nr. 2027-0318", f"Korbach, {de('2027-05-20')}"),
        "",
        f"Fahrt Wernstadt - Sundern/Sauerland und Rundfahrten vor Ort, {de(start)} - {de(end)}",
        "Reisebus 49 Sitzplätze, Fahrer-Übernachtung inklusive",
        "",
        lr("Pauschalpreis inkl. 7 % MwSt.", eur(bus) + " EUR", 70),
        "",
        "Angebot gültig bis 15.06.2027. Zahlung nach Rechnung.",
    ])
    begr = ("Der Antrag auf Genehmigung der Studienexkursion (07.–09.06.2027) ist laut Eingangsstempel erst am "
            "01.06.2027 beim Dekanat eingegangen, also sechs Tage vor Beginn. Nach der Uni-Kassel-Seite "
            "„Dienstreisemanagement“ ist der Antrag vollständig ausgefüllt mindestens 14 Tage vor Beginn der "
            "Exkursion über das Dekanat einzureichen. Zudem nehmen neben der Leitung drei Begleitpersonen an "
            "22 Studierenden teil; angemessen ist in der Regel eine Begleitperson je 15 Studierende, mehr nur mit "
            "gesonderter Begründung, und das Begründungsfeld ist leer. Exkursions- und Reiseantrag der Leitung "
            "sind daher zurückzugeben.")
    case(TRIP, "dienstreiseantrag-d03", "abgelehnt", begr,
         [doc("exkursionsantrag-scan.pdf", scan, jitter=1.6, title="Scan 2027-06-01"),
          doc("reiseantrag-exkursionsleitung-fiori.pdf", fiori, font="Helvetica"),
          doc("angebot-reisebus.pdf", busang, font="Times-Roman")],
         "Excursion leader's trip request: excursion application received 6 days before start; 3 companions for 22 students, justification field empty",
         "„… reicht diesen vollständig ausgefüllt mindestens 14 Tage vor Beginn der Exkursion über das Dekanat bei der "
         "Abteilung Personal und Organisation ein.“ and „Als angemessen anzusehen ist in der Regel eine Begleitperson "
         "für jeweils 15 Studierende. Eine Teilnahme von mehr als einer Begleitperson für je 15 Studierende ist nur "
         "zulässig, wenn dies aufgrund von besonderen Gründen dringend oder zwingend erforderlich ist. Diese Gründe … "
         "sind … in einer gesonderten Begründung darzulegen.“",
         SRC_DRM, "two-page scanned paper form with stamp (jitter) + Fiori print + bus offer", "no", "high")


# --------------------------------------------------------------------------- #
# d04  angenommen (trap): private car at 0,35 EUR/km, good reasons stated before the trip
# --------------------------------------------------------------------------- #
def d04():
    created, out_d, back_d = "2027-04-12", "2027-05-04", "2027-05-05"
    km = 2 * 143
    car = r2(km * D("0.35"))
    assert car == D("100.10")
    inn = D("72.00")
    total = tot(car, inn)
    assert total == D("172.10")
    antrag = fiori_request(
        "4417207145", created, "Antrag eingereicht – in Genehmigung", "Joscha Wendehals-Kröger, M.Sc.", "058840",
        "FB 16 Elektrotechnik/Informatik · FG Windenergietechnik",
        [("Reiseziel", "Messfeld Hohe Röde, 36289 Friedewald-Lautenhausen, DEUTSCHLAND"),
         ("Reise ins Ausland", "nein"),
         ("Anlass", "Messkampagne LiDAR-Windprofil, Kalibrierung am Messmast"),
         ("Reiseart", "Dienstreise"),
         ("Verkehrsmittel", "privater Pkw – triftige Gründe (0,35 €/km)"),
         ("Begründung Pkw-Nutzung", "Transport Kalibrierkoffer LiDAR (46 kg) und zwei Datenlogger;"),
         ("", "Messfeld liegt 9 km von der nächsten Haltestelle, Rufbus nur"),
         ("", "werktags bis 14:00 Uhr; Dienstfahrzeug der Fahrbereitschaft im"),
         ("", "Zeitraum nicht verfügbar (Mail vom 09.04.2027 anbei)"),
         ("Datum der Antragstellung", de(created))],
        [("Beginn der Reise", f"{wd(out_d)}, 07:00 Uhr (Dienststätte)"),
         ("Ende der Reise", f"{wd(back_d)}, 17:30 Uhr (Dienststätte)"),
         ("Beginn Dienstgeschäft", f"{de(out_d)}, 09:00 Uhr"),
         ("Ende Dienstgeschäft", f"{de(back_d)}, 15:30 Uhr"),
         ("Privater Aufenthalt", "keiner"),
         ("Übernachtungen", "1 (Landgasthof Lautenhausen)")],
        [("Wegstreckenentschädigung", f"{km} km x 0,35 € (hin/zurück je 143 km)", car),
         ("Übernachtung", "1 Nacht inkl. Frühstück", inn)],
        total,
        [("Kostenstelle / Auftrag", "16 2610 / Auftrag 6-4420388 (Drittmittel WindProfil)"),
         ("Abschlag beantragt", "nein")],
        ["Parkgebühren fallen am Messfeld nicht an."],
        ["Mail_Fahrbereitschaft_09042027.pdf", "Reservierung_Landgasthof.pdf"],
        created)
    fb = owa_mail(
        "joscha.wendehals-kroeger",
        "AW: Dienstfahrzeug 04./05.05.2027 Messfeld Hohe Röde",
        "Fahrbereitschaft, Universität Wernstadt <fahrbereitschaft@uni-wernstadt.de>",
        "Fr 09.04.2027 13:22",
        "Joscha Wendehals-Kröger <joscha.wendehals-kroeger@uni-wernstadt.de>",
        ["Hallo Herr Wendehals-Kröger,",
         "",
         "für den 04. und 05.05.2027 sind beide Kombis und der Transporter bereits vergeben. Wir können",
         "Ihnen in diesem Zeitraum leider kein Dienstfahrzeug zur Verfügung stellen.",
         "",
         "Mit freundlichen Grüßen",
         "Fahrbereitschaft",
         "",
         "Von: Joscha Wendehals-Kröger",
         "Gesendet: Do 08.04.2027 16:05",
         "Betreff: Dienstfahrzeug 04./05.05.2027 Messfeld Hohe Röde",
         "Ich benötige für die Kalibrierung am Messmast einen Kombi für zwei Tage (Transport 46 kg Messtechnik)."],
        footer_when="09.04.2027 13:22")
    gast = "\n".join([
        "Landgasthof Zur Linde · Lautenhausen",
        "Reservierungsbestätigung",
        "",
        "Rechnungsanschrift: Universität Wernstadt, FG Windenergietechnik, " + UW_ADDR,
        "Gast:               Herr Joscha Wendehals-Kröger",
        f"Anreise:            {wd(out_d)}",
        f"Abreise:            {wd(back_d)}",
        "Zimmer:             Einzelzimmer, 1 Nacht",
        f"Preis:              {eur(inn)} € pro Nacht inkl. Frühstück",
        "",
        "Die Rechnung erhalten Sie bei Abreise. Kostenfreie Stornierung bis 2 Tage vor Anreise.",
        f"Bestätigt am {de('2027-04-12')} · Landgasthof Zur Linde, Dorfstraße 3, 36289 Friedewald",
    ])
    begr = ("Beantragt ist die Nutzung des privaten Pkw mit 0,35 €/km (286 km = 100,10 €). Nach der Uni-Kassel-Seite "
            "„Dienstreisemanagement“ werden 0,35 € je km erstattet, wenn triftige Gründe für die Kfz-Nutzung "
            "vorliegen und die Nutzung vorher genehmigt wird. Der Antrag wurde am 12.04.2027, drei Wochen vor der "
            "Reise, gestellt und nennt die Gründe: 46 kg Messtechnik, Messfeld ohne brauchbare ÖPNV-Anbindung, kein "
            "Dienstfahrzeug verfügbar (Mail der Fahrbereitschaft liegt bei). Die Übernachtung kostet 72,00 € inkl. "
            "Frühstück und liegt unter 80 €, Rechnungsanschrift ist die Universität. Der Antrag ist vollständig und "
            "wird angenommen.")
    case(TRIP, "dienstreiseantrag-d04", "angenommen", begr,
         [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica"),
          doc("email-fahrbereitschaft.pdf", fb, font="Helvetica"),
          doc("reservierung-landgasthof.pdf", gast)],
         "Field-measurement trip by private car at the higher 0,35 EUR/km rate; good reasons (46 kg equipment, no transit, no pool car) stated in the request before the trip",
         "„Beim Vorliegen triftiger Gründe für die Kfz-Nutzung und vorheriger Genehmigung werden 0,35 € für jeden "
         "zurückgelegten Kilometer erstattet.“",
         SRC_DRM, "SAP Fiori print + OWA mail thread (motor pool) + guest-house reservation",
         "yes (private car at the higher rate looks suspicious)", "high")


# --------------------------------------------------------------------------- #
# d05  abgelehnt: one traveller claims hotel and rail for three people
# --------------------------------------------------------------------------- #
def d05():
    created, out_d, back_d = "2027-08-23", "2027-09-14", "2027-09-16"
    rail = r2(3 * 2 * D("44.90"))
    assert rail == D("269.40")
    hotel = r2(3 * 2 * D("76.00"))
    assert hotel == D("456.00")
    total = tot(rail, hotel)
    assert total == D("725.40")
    antrag = fiori_request(
        "4417211902", created, "Antrag eingereicht – in Genehmigung", "Dr. Saskia Oberdiek", "049315",
        "FB 16 Elektrotechnik/Informatik · FG Mikro- und Nanostrukturen",
        [("Reiseziel", "Bremen, DEUTSCHLAND"),
         ("Reise ins Ausland", "nein"),
         ("Anlass", "Projekttreffen Verbund AquaSense, Arbeitsgruppe Sensorik"),
         ("Grund der Reise", "Abstimmung Messprotokolle, Vorstellung Prototyp"),
         ("Reiseart", "Dienstreise"),
         ("Verkehrsmittel", "Bahn, 2. Klasse (Gruppenbuchung)"),
         ("Datum der Antragstellung", de(created))],
        [("Beginn der Reise", f"{wd(out_d)}, 07:45 Uhr (Wohnung)"),
         ("Ende der Reise", f"{wd(back_d)}, 19:20 Uhr (Wohnung)"),
         ("Beginn Dienstgeschäft", f"{de(out_d)}, 13:00 Uhr"),
         ("Ende Dienstgeschäft", f"{de(back_d)}, 13:00 Uhr"),
         ("Privater Aufenthalt", "keiner"),
         ("Übernachtungen", "2")],
        [("Bahn", "Gruppenbuchung 3 Personen, hin/zurück, je 44,90 €", rail),
         ("Übernachtung", "3 Einzelzimmer x 2 Nächte à 76,00 €", hotel)],
        total,
        [("Kostenstelle / Auftrag", "16 2830 / Auftrag 6-4430951 (Drittmittel AquaSense)"),
         ("Abschlag beantragt", "nein")],
        ["Gruppenbuchung für das Projektteam (Frau Femke Hollatz, Herr Pavel Ruzicka-Behrens) über meine",
         "Kreditkarte; bitte die Gesamtkosten an mich erstatten. Die Kollegin und der Kollege stellen",
         "keinen eigenen Antrag."],
        ["Hotelbuchung_Bremen.pdf", "Bahn_Gruppenbuchung.pdf", "Einladung_Projekttreffen.pdf"],
        created)
    hb = "\n".join([
        lr("hotelfinder.example · Ihre Buchungsbestätigung", "Buchungsnr. HF-55-2093318"),
        "",
        "Hotel Weserblick Bremen ***  ·  Schlachte 21  ·  28195 Bremen",
        "",
        "Gebucht von:        Dr. Saskia Oberdiek (saskia.oberdiek@uni-wernstadt.de)",
        "Rechnungsadresse:   Universität Wernstadt, FG Mikro- und Nanostrukturen, " + UW_ADDR,
        f"Anreise:            {wdl(out_d)}",
        f"Abreise:            {wdl(back_d)}  (2 Nächte)",
        "",
        "  " + row(["Zimmer", "Gast", "Nächte", "Preis/Nacht", "Summe"], [22, 26, 6, 12, 10], "llrrr"),
        "  " + row(["1 Einzelzimmer", "Dr. Saskia Oberdiek", "2", "76,00 €", "152,00 €"], [22, 26, 6, 12, 10], "llrrr"),
        "  " + row(["2 Einzelzimmer", "Femke Hollatz", "2", "76,00 €", "152,00 €"], [22, 26, 6, 12, 10], "llrrr"),
        "  " + row(["3 Einzelzimmer", "Pavel Ruzicka-Behrens", "2", "76,00 €", "152,00 €"], [22, 26, 6, 12, 10], "llrrr"),
        "  " + row(["", "Gesamtpreis (ohne Frühstück)", "", "", eur(hotel) + " €"], [22, 26, 6, 12, 10], "llrrr"),
        "",
        "Zahlung: im Hotel mit Kreditkarte der buchenden Person (Visa ****8830).",
        "Kostenlose Stornierung bis 3 Tage vor Anreise.",
    ])
    bahn = "\n".join([
        "Buchungsbestätigung Gruppe · Fernverkehr",
        "Auftragsnummer: 8KQ4TX · Zahlung: Kreditkarte Visa ****8830 (Saskia Oberdiek)",
        "",
        "Reisende: 3 Erwachsene – Saskia Oberdiek, Femke Hollatz, Pavel Ruzicka-Behrens",
        "Sparpreis, 2. Klasse, je Person und Richtung 44,90 €",
        f"Hinfahrt   {wd(out_d)}   Wernstadt-Wilhelmshöhe 08:21 -> Bremen Hbf 11:47 (ICE 573 / IC 2037)",
        f"Rückfahrt  {wd(back_d)}   Bremen Hbf 14:12 -> Wernstadt-Wilhelmshöhe 17:58 (IC 2034 / ICE 576)",
        "",
        lr("Gesamtpreis 3 Personen hin und zurück", eur(rail) + " €", 70),
    ])
    begr = ("Dr. Oberdiek beantragt die Erstattung von Bahn (269,40 €) und Hotel (456,00 €) für sich und zwei "
            "Kolleg:innen, die laut Bemerkung keinen eigenen Antrag stellen. Nach der Uni-Kassel-Seite "
            "„Dienstreisemanagement“ ist es nach einer Prüfung durch den Hessischen Landesrechnungshof untersagt, "
            "Kosten, die für mehrere Personen verauslagt wurden, nur an die verauslagende Person zu erstatten; "
            "die Kolleg:innen müssen ihren Anteil selbst zur Erstattung anfordern. Der Antrag ist auf die eigenen "
            "Kosten (Bahn 89,80 €, Hotel 152,00 €) zu korrigieren und zurückzugeben.")
    case(TRIP, "dienstreiseantrag-d05", "abgelehnt", begr,
         [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica"),
          doc("hotelbuchung-portal.pdf", hb, font="Helvetica"),
          doc("bahn-gruppenbuchung.pdf", bahn)],
         "Project meeting in Bremen: one traveller requests reimbursement of rail and hotel for three people (two colleagues file no request)",
         "„Nach einer Prüfung durch den Hessischen Landesrechnungshof ist es uns untersagt, Kosten, die für mehrere "
         "Personen verauslagt wurden, nur an die verauslagende Person zu erstatten. … Die Kolleginnen müssen ihren "
         "Anteil selber zur Erstattung anfordern …“",
         SRC_DRM, "SAP Fiori print + hotel-portal booking (3 rooms) + rail group booking", "no", "high")


# =========================================================================== #
# PROCUREMENT
# =========================================================================== #
def offer_lines(items):
    """items: list of (pos, text, qty, unit) -> rows, net sum"""
    rows, s = [], D(0)
    for pos, text, qty, unit in items:
        gp = r2(D(qty) * D(unit))
        s += gp
        rows.append((pos, text, qty, D(unit), gp))
    return rows, r2(s)


# --------------------------------------------------------------------------- #
# d06  angenommen (trap): 1.317 EUR net, one supplier, but it is the web-to-print framework shop in WPS
# --------------------------------------------------------------------------- #
def d06():
    created = "2027-03-02"
    items = [("WTP-VK-Q-DE", "Visitenkarten Querformat, CD Universität, 250 Stk./Satz", 18, "24.50"),
             ("WTP-BL-A4-50", "Schreibblock A4, 50 Blatt, CD-Kopfzeile", 120, "2.85"),
             ("WTP-MP-A4-FB", "Präsentationsmappe A4 mit Fachbereichslogo", 300, "1.78")]
    rows, net = offer_lines(items)
    assert net == D("1317.00")
    vat = vat_of(net, 19)
    gross = tot(net, vat)
    w = [16, 52, 6, 12, 12]
    wk = ["WPS Warenbestellsystem · Universität Wernstadt" + " " * 40 + "Druckansicht " + created,
          "",
          " Warenkorb WK-0027-21907",
          kv([("Katalog", "Web-to-Print (UWS) Webshop"),
              ("", "Rahmenvertrag Druckerzeugnisse der Universität: Visitenkarten, Blöcke, Mappen"),
              ("Lieferant (Rahmenvertragspartner)", "Klarsatz Druck GmbH, Göttingen"),
              ("Angelegt", created),
              ("Ersteller:in", "Kerstin Wallbaum-Ilic (Dekanat FB 14), Funktion Ersteller-Besteller"),
              ("Besteller:in (SAP)", "Holger Brinkhoff (Dekanat FB 14)"),
              ("Kontierung", "14 1000 / Dekanat FB 14"),
              ("Freigabe Kostenstelle", "Prof. Dr. Ruprecht Lanzinger-Obst (Dekan), " + created),
              ("Status", "zur Bestellung an Zentrale Beschaffung")], k=36, indent=1),
          "",
          " " + row(["Artikelnr.", "Bezeichnung", "Menge", "Preis netto", "Summe netto"], w, "llrrr")]
    for pos, text, qty, unit, gp in rows:
        wk.append(" " + row([pos, text, str(qty), eur(unit) + " €", eur(gp) + " €"], w, "llrrr"))
    wk += ["",
           " " + row(["Warenwert netto", "", "", "", eur(net) + " €"], w, "llrrr"),
           " " + row(["USt. 19 %", "", "", "", eur(vat) + " €"], w, "llrrr"),
           " " + row(["Gesamt brutto", "", "", "", eur(gross) + " €"], w, "llrrr"),
           "",
           " Druckdaten: Personalisierung der 18 Visitenkarten-Sätze gemäß hochgeladener Liste (VK_FB14_Neue.xlsx).",
           " Lieferadresse: Dekanat FB 14, Raum 1104, " + UW_ADDR]
    mail = owa_mail(
        "beschaffung",
        "WPS-Warenkorb WK-0027-21907 Drucksachen Dekanat FB 14",
        "Kerstin Wallbaum-Ilic <kerstin.wallbaum-ilic@uni-wernstadt.de>",
        "Di 02.03.2027 11:06",
        "beschaffung@uni-wernstadt.de",
        ["Liebes Team der Zentralen Beschaffung,",
         "",
         "anbei der WPS-Warenkorb für die Visitenkarten der neuen Kolleginnen und Kollegen sowie Blöcke und",
         "Mappen für die Absolventenfeier im Juli. Herr Brinkhoff hat den Korb als Besteller übernommen, die",
         "Freigabe der Kostenstelle durch den Dekan ist im WPS hinterlegt.",
         "",
         "Vergleichsangebote haben wir nicht eingeholt, alles kommt aus dem Web-to-Print-Shop.",
         "",
         "Viele Grüße",
         "Kerstin Wallbaum-Ilic",
         "Dekanat Fachbereich 14"],
        cc="Prof. Dr. Ruprecht Lanzinger-Obst <dekan-fb14@uni-wernstadt.de>",
        footer_when="02.03.2027 11:06")
    begr = ("Bestellt werden Visitenkarten, Schreibblöcke und Mappen über 1.317,00 € netto ohne Vergleichsangebote. "
            "Alle drei Artikel stammen laut Warenkorb WK-0027-21907 aus dem Web-to-Print-Webshop im WPS, dem "
            "Rahmenvertrag für Visitenkarten, Blöcke und Mappen. Nach der Uni-Kassel-Seite „Druckauftrag "
            "Visitenkarte“ ist dieser Shop über das WPS-System aufrufbar und die Druckerei Rahmenvertragspartner; "
            "nach der Seite „Rahmenverträge“ werden Bedarfe aus Rahmensortimenten ohne Vergleichsangebote gedeckt, "
            "und nach der Seite „Beschaffung“ entfällt die Pflicht zu drei Angeboten bei Rahmenvertragspartnern. "
            "Die Positionen ergeben die Summe, der Dekan als Kostenstellenbevollmächtigter hat freigegeben. Der "
            "Antrag wird angenommen.")
    case(PROC, "beschaffungsantrag-d06", "angenommen", begr,
         [doc("wps-warenkorb.pdf", "\n".join(wk), font="Helvetica"),
          doc("email-bestellung.pdf", mail, font="Helvetica")],
         "Business cards, notepads and folders for 1.317 EUR net from one supplier without offers, ordered through the web-to-print framework shop in WPS",
         "„Der Web-to-Print Shop für Visitenkarten, Blöcke und Mappen ist über das WPS-System (Hochschul-Einkauf "
         "Lehre & Forschung) aufrufbar … Rahmenvertragspartner Druckerei Klartext“ with „Der Abschluss der "
         "Rahmenverträge ermöglicht den einzelnen Bereichen Ihre Bedarfe aus den jeweiligen Rahmensortimenten ohne "
         "das Einholen von Vergleichsangeboten zu decken.“",
         SRC_DVK + "; " + SRC_RV, "WPS cart print (Ersteller-Besteller) + OWA mail",
         "yes (over 1.000 EUR with a single supplier)", "high")


# --------------------------------------------------------------------------- #
# d07  abgelehnt: chosen offer is not the cheapest – gross price of the cheapest compared with net prices
# --------------------------------------------------------------------------- #
def d07():
    created = "2027-06-21"
    a_rows, a_net = offer_lines([("1", "Schüttelinkubator Tischgerät TS-40, 5-60 °C, 30-300 rpm", 1, "2290.00"),
                                 ("2", "Universal-Klemmenset für Kolben 100-1000 ml", 1, "145.00"),
                                 ("3", "Einweisung vor Ort", 1, "45.00")])
    b_rows, b_net = offer_lines([("10", "Schüttelinkubator NL-Shake 40, 5-60 °C, 25-300 rpm", 1, "2205.00"),
                                 ("20", "Klemmenset für Erlenmeyerkolben 100-1000 ml", 1, "139.00"),
                                 ("30", "Versand und Verpackung, Einweisung vor Ort inklusive", 1, "90.00")])
    c_rows, c_net = offer_lines([("1", "Inkubationsschüttler IS-45 Tisch, 4-65 °C", 1, "2410.00"),
                                 ("2", "Klemmenausstattung 100-1000 ml", 1, "165.00"),
                                 ("3", "Fracht", 1, "35.00"),
                                 ("4", "Einweisung", 1, "25.00")])
    assert (a_net, b_net, c_net) == (D("2480.00"), D("2434.00"), D("2635.00"))
    b_vat = vat_of(b_net, 19)
    b_gross = tot(b_net, b_vat)
    assert b_gross == D("2896.46")
    a_vat = vat_of(a_net, 19)
    a_gross = tot(a_net, a_vat)
    srm = "\n".join([
        lr("SAP SRM · Einkaufswagen anzeigen", "Universität Wernstadt · Mandant 100"),
        "",
        lr("Einkaufswagen 1000473318  „Schüttelinkubator Bioverfahrenstechnik“", "Status: Genehmigung erteilt"),
        kv([("Angelegt von", "Dr. Anouk Schellhorn-Baptiste (FB 15 · FG Bioverfahrenstechnik)"),
            ("Angelegt am", de(created)),
            ("Genehmigt (Kostenstelle)", f"Prof. Dr. Detlev Marquardsen, {de('2027-06-22')}"),
            ("Kontierung", "15 5120 / Auftrag 6-5130447"),
            ("Warengruppe", "Laborgeräte · Anlage"),
            ("Rahmenvertrag", "keiner"),
            ("Vorgeschlagener Lieferant", "Laborgeräte Bründel GmbH, Gießen (Angebot AN-2027-1184)")], k=30),
        "",
        "  " + row(["Pos", "Bezeichnung", "Menge", "Preis", "Wert netto"], [4, 56, 6, 12, 12], "llrrr"),
    ] + ["  " + row([p, t, str(q), eur(u) + " €", eur(g) + " €"], [4, 56, 6, 12, 12], "llrrr") for p, t, q, u, g in a_rows]
      + ["",
         "  " + row(["Gesamtwert netto", "", "", "", eur(a_net) + " €"], [4, 56, 6, 12, 12], "llrrr"),
         "",
         "  Notiz an Einkauf (Preisvergleich, drei Angebote angehängt):",
         "  " + row(["Bieter", "Angebot", "Angebotspreis"], [44, 18, 14], "llr"),
         "  " + row(["Laborgeräte Bründel GmbH, Gießen", "AN-2027-1184", eur(a_net) + " €"], [44, 18, 14], "llr"),
         "  " + row(["Nordlab Vertrieb GmbH & Co. KG, Lübeck", "27-0415", eur(b_gross) + " €"], [44, 18, 14], "llr"),
         "  " + row(["Laborbedarf Zirngibl KG, Regensburg", "Q-27-6610", eur(c_net) + " €"], [44, 18, 14], "llr"),
         "  Auswahl: günstigstes Angebot (Bründel). Gleiche technische Eignung, alle mit Einweisung.",
         "",
         "  Anhänge: Angebot_Bruendel.pdf, Angebot_Nordlab.pdf, Angebot_Zirngibl.pdf"])
    w = [4, 58, 5, 12, 12]
    ang_a = "\n".join([
        "LABORGERÄTE BRÜNDEL GmbH · Frankfurter Straße 140 · 35392 Gießen",
        "",
        "Universität Wernstadt, FG Bioverfahrenstechnik, Dr. A. Schellhorn-Baptiste",
        "",
        lr("ANGEBOT AN-2027-1184", f"Gießen, {de('2027-06-08')}", 94),
        "",
        row(["Pos", "Artikel", "Menge", "EP netto", "GP netto"], w, "llrrr"),
    ] + [row([p, t, str(q), eur(u), eur(g)], w, "llrrr") for p, t, q, u, g in a_rows] + [
        "",
        row(["", "Summe netto", "", "", eur(a_net)], w, "llrrr"),
        row(["", "zzgl. 19 % MwSt.", "", "", eur(a_vat)], w, "llrrr"),
        row(["", "Gesamtbetrag brutto", "", "", eur(a_gross)], w, "llrrr"),
        "",
        "Lieferung frei Verwendungsstelle. Lieferzeit ca. 3 Wochen. Angebot gültig 60 Tage.",
    ])
    ang_b = "\n".join([
        "NORDLAB Vertrieb GmbH & Co. KG",
        "Laborausstattung für Forschung und Industrie · Glashüttenweg 7 · 23568 Lübeck",
        "",
        "An: Universität Wernstadt · FG Bioverfahrenstechnik · z. Hd. Frau Dr. Schellhorn-Baptiste",
        "",
        f"Angebot Nr. 27-0415 vom {de('2027-06-10')}",
        "",
        "  Angebotssumme:        " + eur(b_gross) + " €  (inkl. 19 % MwSt.)",
        "",
        row(["Pos", "Beschreibung", "Menge", "Einzelpreis", "Gesamt"], w, "llrrr"),
    ] + [row([p, t, str(q), eur(u) + " €", eur(g) + " €"], w, "llrrr") for p, t, q, u, g in b_rows] + [
        "",
        row(["", "Zwischensumme (netto)", "", "", eur(b_net) + " €"], w, "llrrr"),
        row(["", "Mehrwertsteuer 19 %", "", "", eur(b_vat) + " €"], w, "llrrr"),
        row(["", "Angebotssumme (brutto)", "", "", eur(b_gross) + " €"], w, "llrrr"),
        "",
        "Technische Daten: Temperaturbereich 5-60 °C, Schüttelfrequenz 25-300 rpm, Orbit 25 mm,",
        "Plattform 46 x 46 cm. Einweisung durch unseren Servicetechniker ist im Preis enthalten.",
        "Gültigkeit: 8 Wochen. Lieferzeit: 2-3 Wochen ab Bestellung.",
    ])
    ang_c = "\n".join([
        "Laborbedarf Zirngibl KG · Donaustaufer Str. 77 · 93059 Regensburg",
        "",
        lr("Angebot Q-27-6610", de("2027-06-14"), 94),
        "Universität Wernstadt, Bioverfahrenstechnik",
        "",
        row(["Pos", "Artikel", "Menge", "Preis", "Summe"], w, "llrrr"),
    ] + [row([p, t, str(q), eur(u), eur(g)], w, "llrrr") for p, t, q, u, g in c_rows] + [
        "",
        row(["", "Nettobetrag", "", "", eur(c_net)], w, "llrrr"),
        row(["", "USt 19 %", "", "", eur(vat_of(c_net, 19))], w, "llrrr"),
        row(["", "Bruttobetrag", "", "", eur(tot(c_net, vat_of(c_net, 19)))], w, "llrrr"),
    ])
    begr = ("Gewählt ist das Angebot der Laborgeräte Bründel GmbH über 2.480,00 € netto als „günstigstes Angebot“. "
            "Im Preisvergleich des Einkaufswagens steht das Angebot der Nordlab Vertrieb GmbH & Co. KG aber mit "
            "seinem Bruttobetrag von 2.896,46 €; netto lautet es auf 2.434,00 € (inkl. Versand und Einweisung) und "
            "ist damit 46,00 € günstiger als Bründel bei gleicher technischer Eignung. Wie im Fall "
            "beschaffungsantrag-07 der Organisatoren beruht die Lieferantenwahl damit auf einem falschen Wert; nach "
            "der Uni-Kassel-Seite „Rahmenverträge“ sind Preisvergleiche aus Gründen der Wirtschaftlichkeit und "
            "Sparsamkeit vorzunehmen. Der Antrag wird abgelehnt.")
    case(PROC, "beschaffungsantrag-d07", "abgelehnt", begr,
         [doc("srm-einkaufswagen.pdf", srm, font="Helvetica"),
          doc("angebot-1-bruendel.pdf", ang_a),
          doc("angebot-2-nordlab.pdf", ang_b, font="Helvetica"),
          doc("angebot-3-zirngibl.pdf", ang_c, font="Times-Roman")],
         "Shaking incubator, three offers; the cart compares the second offer's gross total (2.896,46) with net prices, but its net 2.434,00 is below the chosen 2.480,00",
         "Organisers: „Mit dem richtigen Betrag ist Mergenthal günstiger als die bezuschlagte Thermoskop Ruhland GmbH "
         "…, die Wertung des Vermerks und die Lieferantenwahl … beruhen damit auf einem falschen Wert.“ plus „Wir "
         "empfehlen aus Gründen der Wirtschaftlichkeit und Sparsamkeit grundsätzlich Preisvergleiche …“",
         SRC_GT_P07 + "; " + SRC_RV, "SAP SRM shopping cart + three offers in three layouts (one shows gross first)",
         "yes (looks compliant: three offers, approved, 'cheapest')", "high")


# --------------------------------------------------------------------------- #
# d08  abgelehnt (trap): bottled gases with three offers, cheapest chosen – but gases are a framework product
# --------------------------------------------------------------------------- #
def d08():
    created = "2027-02-22"
    specs = [("Argon 4.6, Flasche 50 l / 200 bar, Füllung", 8),
             ("Mischgas Argon/CO2 82/18, 50 l / 200 bar, Füllung", 6),
             ("Flaschenmiete, je Flasche und Monat (6 Flaschen x 12 Monate)", 72)]
    prices = {"Ruhwedel": ["58.00", "62.50", "6.50"],
              "Pauly": ["61.20", "64.00", "6.90"],
              "Oberbeck": ["63.00", "66.40", "7.20"]}
    nets = {}
    rows_by = {}
    for k, ps in prices.items():
        rows_by[k], nets[k] = offer_lines([(str(i + 1), s[0], s[1], p) for i, (s, p) in enumerate(zip(specs, ps))])
    assert nets == {"Ruhwedel": D("1307.00"), "Pauly": D("1370.40"), "Oberbeck": D("1420.80")}
    net = nets["Ruhwedel"]
    vat = vat_of(net, 19)
    form = "\n".join([
        "Universitat Wernstadt  -  Zentrale Beschaffung                    Antrag Nr. ZB-2027-0219",
        "BESCHAFFUNGSANTRAG / BESTELLANFORDERUNG  (Formular ZB-3, Stand 01/2027)     Datum: " + de(created),
        "",
        "1. Bedarfsstelle",
        "   Organisationseinheit ....... FB 15 Maschinenbau, FG Werkstofftechnik / Fügetechnik-Labor",
        "   Antragsteller:in ........... Dipl.-Ing. Henning Strackerjahn",
        "   Kostenstelle / Auftrag ..... 15 4310 / Auftrag 2150118",
        "   Kostenstellenbevollm. ...... Prof. Dr.-Ing. Ulrike Fennenkötter",
        "",
        "2. Einordnung",
        "   Kategorie .................. [X] Verbrauchsmaterial  [ ] GWG  [ ] Anlage",
        "   Rahmenvertragsprodukt ...... [ ] ja  [X] nein",
        "   Vergabeart ................. Preisvergleich, drei schriftliche Angebote",
        "   Vorgesehener Lieferant ..... Gase-Handel Ruhwedel GmbH, Hann. Münden (Angebot R-27-0088)",
        "",
        "3. Positionen",
        "   " + row(["Pos", "Bezeichnung", "Menge", "EP netto", "GP netto"], [3, 58, 5, 9, 10], "llrrr"),
    ] + ["   " + row([p, t, str(q), eur(u), eur(g)], [3, 58, 5, 9, 10], "llrrr") for p, t, q, u, g in rows_by["Ruhwedel"]]
      + ["",
         "   Summe netto " + "." * 62 + " " + eur(net),
         "   zzgl. 19 % USt " + "." * 58 + " " + eur(vat),
         "   Gesamt brutto " + "." * 59 + " " + eur(tot(net, vat)),
         "",
         "4. Begründung",
         "   Schutzgas für die MIG/MAG- und WIG-Versuchsstände im Praktikum Fügetechnik, Bedarf für 12 Monate.",
         "   Drei Angebote eingeholt (Ruhwedel 1.307,00 / Pauly 1.370,40 / Oberbeck 1.420,80 netto);",
         "   Ruhwedel ist das günstigste Angebot.",
         "",
         f"   Wernstadt, {de(created)}    gez. H. Strackerjahn        Beauftragt: gez. Fennenkötter",
         "                                 Antragsteller:in            Kostenstellenbevollmächtigte:r",
         "",
         "   [Scan · 300 dpi · Seite 1 von 1]"])
    offers = []
    meta = {"Ruhwedel": ("GASE-HANDEL RUHWEDEL GmbH · Kasseler Schlagd 12 · 34346 Hann. Münden", "R-27-0088", "2027-02-09"),
            "Pauly": ("Technische Gase Pauly KG · Industriestraße 31 · 37079 Göttingen", "TGP-2027-117", "2027-02-11"),
            "Oberbeck": ("Schweißfachhandel Oberbeck e.K. · Am Hafen 5 · 34125 Wernstadt", "OB/27/0214", "2027-02-15")}
    for k in ["Ruhwedel", "Pauly", "Oberbeck"]:
        head, nr, d_ = meta[k]
        n = nets[k]
        offers.append("\n".join([
            head, "",
            "Universität Wernstadt, FG Werkstofftechnik, Herrn Dipl.-Ing. H. Strackerjahn", "",
            lr(f"Angebot {nr}", de(d_), 94), "",
            row(["Pos", "Bezeichnung", "Menge", "EP netto", "GP netto"], [3, 62, 5, 9, 10], "llrrr"),
        ] + [row([p, t, str(q), eur(u), eur(g)], [3, 62, 5, 9, 10], "llrrr") for p, t, q, u, g in rows_by[k]] + [
            "",
            row(["", "Summe netto", "", "", eur(n)], [3, 62, 5, 9, 10], "llrrr"),
            row(["", "USt 19 %", "", "", eur(vat_of(n, 19))], [3, 62, 5, 9, 10], "llrrr"),
            row(["", "Gesamt", "", "", eur(tot(n, vat_of(n, 19)))], [3, 62, 5, 9, 10], "llrrr"),
            "",
            "Flaschen bleiben Eigentum des Lieferanten. Lieferung frei Labor, Abholung Leergut inklusive."]))
    begr = ("Bestellt werden Argon und Argon/CO2-Mischgas in 50-l-Flaschen samt Flaschenmiete für 1.307,00 € netto "
            "beim günstigsten von drei regionalen Gashändlern; im Antrag ist „Rahmenvertragsprodukt: nein“ "
            "angekreuzt. Nach der Uni-Kassel-Seite „Rahmenverträge“ besteht aber ein Rahmenvertrag über Flaschengase "
            "(außer Helium); die Rahmenvertragsprodukte sind im WPS-System unter dem Katalog Rahmenvertrag "
            "Flaschengase gelistet und müssen hierüber bestellt werden, und nach der Seite „Beschaffung“ ist ein "
            "solches Produkt ausschließlich beim Rahmenvertragspartner zu bestellen. Drei Angebote ändern daran "
            "nichts. Der Antrag wird abgelehnt.")
    case(PROC, "beschaffungsantrag-d08", "abgelehnt", begr,
         [doc("beschaffungsantrag-scan.pdf", form, jitter=1.2),
          doc("angebot-1.pdf", offers[0], font="Helvetica"),
          doc("angebot-2.pdf", offers[1]),
          doc("angebot-3.pdf", offers[2], font="Times-Roman")],
         "Argon and argon/CO2 cylinders plus rental, 1.307 EUR net, three offers and cheapest chosen, form ticks 'no framework product' – bottled gases are a framework product ordered via WPS",
         "„Rahmenvertrag Flaschengase (außer Helium) … Die Rahmenvertragsprodukte sind im WPS-System unter dem "
         "Katalog Rahmenvertrag Flaschengase gelistet und müssen hierüber bestellt werden.“",
         SRC_RV + "; " + SRC_BESCH, "scanned paper form ZB-3 (OCR-like, jitter) + three offers",
         "yes (looks compliant: three offers, cheapest, signed)", "high")


# --------------------------------------------------------------------------- #
# d09  angenommen (trap): four offers, the cheapest fails a must requirement, cheapest suitable one chosen
# --------------------------------------------------------------------------- #
def d09():
    created = "2027-11-15"
    pos = [("1", "Klimaprüfschrank 120 l, -20 bis +80 °C, Feuchte 20-95 % r.F.", 1, "2985.00"),
           ("2", "Datenlogger-Schnittstelle Ethernet/USB inkl. Software", 1, "165.00"),
           ("3", "Lieferung, Aufstellung, Inbetriebnahme", 1, "90.00")]
    rows, net = offer_lines(pos)
    assert net == D("3240.00")
    vat = vat_of(net, 19)
    gross = tot(net, vat)
    bids = [("Klimatechnik Haverkamp GmbH", "KH-27-4410", "2027-10-25", D("2890.00"), "Muss-Anf. 2 nicht erfüllt (ohne Feuchte)", "ausgeschlossen"),
            ("Prüftechnik Ahlgrimm & Sohn GmbH", "PA-2027-913", "2027-10-27", net, "erfüllt alle Muss-Anforderungen", "1"),
            ("ClimaLab B.V., Eindhoven", "CL-Q-27118", "2027-10-28", D("3315.00"), "erfüllt alle Muss-Anforderungen", "2"),
            ("Umweltsimulation Brückl GmbH", "UB-1027-55", "2027-11-02", D("3468.00"), "erfüllt alle Muss-Anforderungen", "3")]
    suitable = [b for b in bids if b[5] != "ausgeschlossen"]
    assert len(suitable) == 3 and min(b[3] for b in suitable) == net and min(b[3] for b in bids) == D("2890.00")
    antrag = "\n".join([
        lr(" Universität Wernstadt", "Antrag Nr. ZB-2027-1187"),
        lr(" Zentrale Beschaffung", "Datum: " + de(created)),
        "",
        "  Beschaffungsantrag / Bestellanforderung",
        kv([("Organisationseinheit", "FB 14 Bauingenieurwesen, FG Bauphysik"),
            ("Antragsteller:in", "Dr.-Ing. Wiebke Otterbach-Lorenz"),
            ("Kostenstelle / Auftrag", "14 2730 / Auftrag 6-4140662"),
            ("Kostenstellenbevollmächtigte:r", "Prof. Dr.-Ing. Ansgar Hellweg"),
            ("Kategorie", "[ ] Verbrauchsmaterial [ ] GWG [X] Anlage"),
            ("Rahmenvertragsprodukt", "[ ] ja [X] nein"),
            ("Vergabeart", "Preisvergleich, schriftliche Angebote (4 eingeholt)"),
            ("Vorgesehener Lieferant", "Prüftechnik Ahlgrimm & Sohn GmbH, Hagen (PA-2027-913)")], k=34, indent=1),
        "",
        " " + row(["Pos.", "Bezeichnung", "Menge", "EP netto", "GP netto"], [4, 60, 5, 12, 12], "llrrr"),
    ] + [" " + row([p, t, str(q), eur(u) + " €", eur(g) + " €"], [4, 60, 5, 12, 12], "llrrr") for p, t, q, u, g in rows]
      + ["",
         " " + row(["", "Summe netto", "", "", eur(net) + " €"], [4, 60, 5, 12, 12], "llrrr"),
         " " + row(["", "zzgl. 19 % USt.", "", "", eur(vat) + " €"], [4, 60, 5, 12, 12], "llrrr"),
         " " + row(["", "Gesamtbetrag brutto", "", "", eur(gross) + " €"], [4, 60, 5, 12, 12], "llrrr"),
         "",
         "  Begründung: Prüfung des Feuchteverhaltens von Lehmputzproben unter zyklischer Klimabelastung",
         "  (Projekt LehmKlima). Leistungsanforderungen vor der Angebotseinholung festgelegt (Anlage 1).",
         "",
         lr(f" Wernstadt, {de(created)}   gez. W. Otterbach-Lorenz", "Beauftragt: gez. Prof. Dr.-Ing. A. Hellweg"),
         lr(" Antragsteller:in", "Kostenstellenbevollmächtigte:r"),
         "",
         " Formular ZB-3 · Beschaffungsantrag · Stand 01/2027                                        Seite 1"])
    anl = "\n".join([
        "Anlage 1 zu ZB-2027-1187 · Leistungsanforderungen Klimaprüfschrank (Stand " + de("2027-10-18") + ")",
        "",
        "Muss-Anforderungen",
        "  1. Temperaturbereich mindestens -20 °C bis +80 °C",
        "  2. geregelte Luftfeuchte mindestens 20 bis 95 % r.F.",
        "  3. Nutzvolumen mindestens 100 l",
        "  4. Datenschnittstelle zur Aufzeichnung (Ethernet oder USB)",
        "",
        "Diese Anforderungen wurden allen Bietern mit der Aufforderung zur Angebotsabgabe übersandt.",
    ])
    verm = ["Vergabevermerk",
            "Universität Wernstadt · Vorgang V-27-1140 · zum Beschaffungsantrag ZB-2027-1187",
            "",
            kv([("Gegenstand", "Klimaprüfschrank mit Datenschnittstelle, Aufstellung"),
                ("Verfahren", "Preisvergleich durch Einholung schriftlicher Angebote"),
                ("Wertung", "Preis (netto) unter den Angeboten, die alle Muss-Anforderungen erfüllen")], k=14, indent=0),
            "",
            row(["Bieter", "Angebot", "vom", "netto", "Prüfung", "Rang"], [33, 12, 10, 10, 40, 14], "lllrll")]
    for b in bids:
        verm.append(row([b[0], b[1], de(b[2]), eur(b[3]), b[4], b[5]], [33, 12, 10, 10, 40, 14], "lllrll"))
    verm += ["",
             "Das Angebot Haverkamp (Modell KS 120 T) ist ein reiner Temperaturprüfschrank ohne Feuchteregelung und",
             "erfüllt Muss-Anforderung 2 nicht; es ist nicht vergleichbar und wird ausgeschlossen. Unter den drei",
             "vergleichbaren Angeboten ist Prüftechnik Ahlgrimm & Sohn mit " + eur(net) + " € netto das günstigste.",
             "",
             "Zuschlag an: Prüftechnik Ahlgrimm & Sohn GmbH, " + eur(net) + " € netto",
             "",
             f"Wernstadt, {de('2027-11-12')}       Dr.-Ing. W. Otterbach-Lorenz        Prof. Dr.-Ing. A. Hellweg"]
    hk = "\n".join([
        "Klimatechnik Haverkamp GmbH · Gewerbering 18 · 48599 Gronau", "",
        lr("Angebot KH-27-4410", de("2027-10-25"), 94), "Universität Wernstadt, FG Bauphysik", "",
        row(["Pos", "Artikel", "Menge", "Preis netto"], [4, 66, 6, 14], "llrr"),
        row(["1", "Temperaturprüfschrank KS 120 T, 120 l, -40 bis +100 °C", "1", eur(2760)], [4, 66, 6, 14], "llrr"),
        row(["2", "USB-Schnittstelle mit Aufzeichnungssoftware", "1", eur(130)], [4, 66, 6, 14], "llrr"),
        row(["", "Summe netto (frei Haus)", "", eur(2890)], [4, 66, 6, 14], "llrr"),
        "",
        "Hinweis: Eine Feuchteregelung ist für das Modell KS 120 T nicht lieferbar.",
    ])
    assert tot(2760, 130) == D("2890.00")
    pa = "\n".join([
        "PRÜFTECHNIK AHLGRIMM & SOHN GmbH · Eilper Straße 220 · 58091 Hagen", "",
        "Universität Wernstadt · FG Bauphysik · Frau Dr.-Ing. W. Otterbach-Lorenz", "",
        lr("ANGEBOT PA-2027-913", f"Hagen, {de('2027-10-27')}", 94), "",
        row(["Pos", "Bezeichnung", "Menge", "EP netto", "GP netto"], [4, 60, 5, 12, 12], "llrrr"),
    ] + [row([p, t, str(q), eur(u), eur(g)], [4, 60, 5, 12, 12], "llrrr") for p, t, q, u, g in rows] + [
        "", row(["", "Summe netto", "", "", eur(net)], [4, 60, 5, 12, 12], "llrrr"),
        row(["", "19 % USt", "", "", eur(vat)], [4, 60, 5, 12, 12], "llrrr"),
        row(["", "Gesamt brutto", "", "", eur(gross)], [4, 60, 5, 12, 12], "llrrr"),
        "", "Alle Muss-Anforderungen gemäß Ihrer Anlage 1 werden erfüllt. Lieferzeit 4 Wochen."])
    cl_rows, cl_net = offer_lines([("1", "Climatic test chamber CTC-110H, 110 l, -25 to +90 °C, 10-98 % RH", 1, "3090.00"),
                                   ("2", "Ethernet interface and logging software", 1, "150.00"),
                                   ("3", "Delivery and installation (DE)", 1, "75.00")])
    assert cl_net == D("3315.00")
    cl = "\n".join([
        "ClimaLab B.V. · Kanaaldijk 41 · 5611 Eindhoven · The Netherlands · VAT NL 8204.71.553.B01", "",
        lr("QUOTATION CL-Q-27118", "Date: " + en_date("2027-10-28"), 94),
        "To: Universitaet Wernstadt, Building Physics Group, Dr.-Ing. W. Otterbach-Lorenz", "",
        row(["Item", "Description", "Qty", "Unit price", "Amount"], [4, 64, 4, 11, 11], "llrrr"),
    ] + [row([p, t, str(q), "EUR " + en(u), "EUR " + en(g)], [4, 64, 4, 11, 11], "llrrr") for p, t, q, u, g in cl_rows] + [
        "", row(["", "Total net (intra-EU supply, VAT reverse charge)", "", "", "EUR " + en(cl_net)], [4, 64, 4, 11, 11], "llrrr"),
        "", "All mandatory requirements of your Annex 1 are met. Validity: 60 days. Delivery: 5-6 weeks."])
    ub = "\n".join([
        "Umweltsimulation Brückl GmbH · Am Kreuzfeld 9 · 82362 Weilheim", "",
        lr("Angebot UB-1027-55", de("2027-11-02"), 94), "Universität Wernstadt, FG Bauphysik", "",
        row(["Pos", "Artikel", "Menge", "netto"], [4, 66, 6, 14], "llrr"),
        row(["1", "Klimaschrank KS-H 125, -20 bis +85 °C, 15-95 % r.F.", "1", eur(3260)], [4, 66, 6, 14], "llrr"),
        row(["2", "Schnittstelle LAN mit Software", "1", eur(148)], [4, 66, 6, 14], "llrr"),
        row(["3", "Fracht und Aufstellung", "1", eur(60)], [4, 66, 6, 14], "llrr"),
        row(["", "Summe netto", "", eur(3468)], [4, 66, 6, 14], "llrr"),
    ])
    assert tot(3260, 148, 60) == D("3468.00")
    begr = ("Für den Klimaprüfschrank liegen vier Angebote vor. Das niedrigste (Haverkamp, 2.890,00 € netto) bietet "
            "einen Schrank ohne Feuchteregelung und erfüllt damit eine vorab festgelegte Muss-Anforderung nicht; "
            "der Vergabevermerk schließt es nachvollziehbar aus. Nach der Uni-Kassel-Seite „Gerätefondsverfahren“ "
            "sind zunächst die Leistungsanforderungen festzulegen und auf dieser Grundlage mindestens drei "
            "vergleichbare Angebote einzuholen; das ist mit Ahlgrimm (3.240,00 €), ClimaLab (3.315,00 €) und Brückl "
            "(3.468,00 €) erfüllt, und gewählt ist das günstigste vergleichbare Angebot. Positionen und Summe des "
            "Antrags stimmen mit dem Angebot überein, der Kostenstellenbevollmächtigte hat beauftragt. Der Antrag "
            "wird angenommen.")
    case(PROC, "beschaffungsantrag-d09", "angenommen", begr,
         [doc("beschaffungsantrag.pdf", antrag + "\f" + anl, font="Helvetica"),
          doc("vergabevermerk.pdf", "\n".join(verm)),
          doc("angebot-1-haverkamp.pdf", hk, font="Times-Roman"),
          doc("angebot-2-ahlgrimm.pdf", pa),
          doc("angebot-3-climalab-en.pdf", cl, font="Helvetica"),
          doc("angebot-4-brueckl.pdf", ub)],
         "Climate test chamber, four offers; the cheapest lacks the required humidity control and is excluded, the cheapest of the three comparable offers wins",
         "„1. Festlegung der geforderten Leistungsanforderungen / Funktionalitäten 2. Auf dieser Grundlage sind mind. "
         "drei vergleichbare Angebote einzuholen“ with „Grundsätzlich müssen 3 Angebote eingeholt werden“",
         SRC_GF + "; " + SRC_BESCH, "form with annex (2 pages) + award note + four offers incl. one English quotation",
         "yes (chosen offer is not the cheapest)", "high")


# --------------------------------------------------------------------------- #
# d10  abgelehnt: three offers fine, but no order by the cost-centre holder (professor away, "signature follows")
# --------------------------------------------------------------------------- #
def d10():
    created = "2027-06-14"
    pos = [("1", "Kraft-Momenten-Sensor 6-Achsen, Fz 600 N, Mz 25 Nm, EtherCAT", 1, "1420.00"),
           ("2", "Montageflansch ISO 9409-1-50-4-M6", 1, "98.00"),
           ("3", "Anschlusskabel 5 m, geschirmt", 1, "67.00")]
    rows, net = offer_lines(pos)
    assert net == D("1585.00")
    vat = vat_of(net, 19)
    gross = tot(net, vat)
    w = [4, 62, 5, 11, 11]
    form = "\n".join([
        lr(" Universität Wernstadt", "Antrag Nr. ZB-2027-0702"),
        lr(" Zentrale Beschaffung", "Datum: " + de(created)),
        "",
        "  Beschaffungsantrag / Bestellanforderung",
        kv([("Organisationseinheit", "FB 16 Elektrotechnik/Informatik, FG Robotik und autonome Systeme"),
            ("Antragsteller:in", "Ruben Etzold-Nakamura, M.Sc."),
            ("Kostenstelle / Auftrag", "16 2950 / Auftrag 6-4160218"),
            ("Kostenstellenbevollmächtigte:r", "Prof. Dr. Corvin Haubenreißer"),
            ("Kategorie", "[ ] Verbrauchsmaterial [ ] GWG [X] Anlage"),
            ("Rahmenvertragsprodukt", "[ ] ja [X] nein"),
            ("Vergabeart", "Preisvergleich, drei schriftliche Angebote"),
            ("Vorgesehener Lieferant", "Sensorik Brandauer GmbH, Pforzheim (Angebot SB-27-3381)")], k=34, indent=1),
        "",
        " " + row(["Pos.", "Bezeichnung", "Menge", "EP netto", "GP netto"], w, "llrrr"),
    ] + [" " + row([p, t, str(q), eur(u) + " €", eur(g) + " €"], w, "llrrr") for p, t, q, u, g in rows] + [
        "",
        " " + row(["", "Summe netto", "", "", eur(net) + " €"], w, "llrrr"),
        " " + row(["", "zzgl. 19 % USt.", "", "", eur(vat) + " €"], w, "llrrr"),
        " " + row(["", "Gesamtbetrag brutto", "", "", eur(gross) + " €"], w, "llrrr"),
        "",
        "  Begründung: Kraftgeregelte Montageversuche am Leichtbauroboter (Dissertation). Angebote:",
        "  Brandauer 1.585,00 € / Rietzschel Messtechnik 1.642,00 € / Okuma-Sensortechnik 1.719,00 € netto.",
        "",
        lr(f" Wernstadt, {de(created)}   gez. R. Etzold-Nakamura", "Beauftragt: ______________________"),
        lr(" Antragsteller:in", "Kostenstellenbevollmächtigte:r (Unterschrift folgt)"),
        "",
        " Formular ZB-3 · Beschaffungsantrag · Stand 01/2027                                        Seite 1"])
    mail = owa_mail(
        "beschaffung",
        "Beschaffungsantrag ZB-2027-0702 Kraft-Momenten-Sensor FG Robotik",
        "Ruben Etzold-Nakamura <ruben.etzold-nakamura@uni-wernstadt.de>",
        "Mo 14.06.2027 09:37",
        "beschaffung@uni-wernstadt.de",
        ["Guten Morgen,",
         "",
         "anbei Antrag und drei Angebote für einen Kraft-Momenten-Sensor. Prof. Haubenreißer ist bis Ende",
         "Juni im Forschungsfreisemester in Kanada und per Mail kaum erreichbar. Damit die Lieferzeit nicht",
         "verloren geht, reiche ich den Antrag schon ein; seine Unterschrift reiche ich nach, sobald er",
         "zurück ist. Der Sensor wird für Versuche ab Mitte Juli gebraucht.",
         "",
         "Viele Grüße",
         "Ruben Etzold-Nakamura",
         "Wissenschaftlicher Mitarbeiter, FG Robotik und autonome Systeme"],
        footer_when="14.06.2027 09:37")
    offers = []
    for head, nr, d_, factor_rows in [
            ("Sensorik Brandauer GmbH · Kaiser-Friedrich-Str. 66 · 75172 Pforzheim", "SB-27-3381", "2027-06-02", rows),
            ("Rietzschel Messtechnik GmbH · Lange Reihe 14 · 04315 Leipzig", "RM-0627-118", "2027-06-04",
             offer_lines([("1", "6-Achs-Kraft-Momenten-Sensor, EtherCAT", 1, "1465.00"),
                          ("2", "Adapterflansch ISO 50", 1, "104.00"),
                          ("3", "Kabel 5 m", 1, "73.00")])[0]),
            ("Okuma-Sensortechnik Deutschland GmbH · Am Seestern 8 · 40547 Düsseldorf", "OS/DE/27/2290", "2027-06-07",
             offer_lines([("1", "Force/Torque Sensor FT-600, EtherCAT", 1, "1540.00"),
                          ("2", "Mounting flange ISO 9409-50", 1, "112.00"),
                          ("3", "Cable 5 m", 1, "67.00")])[0])]:
        n = tot(*[g for *_, g in factor_rows])
        offers.append((n, "\n".join([
            head, "", "Universität Wernstadt · FG Robotik und autonome Systeme · Herrn R. Etzold-Nakamura", "",
            lr(f"Angebot {nr}", de(d_), 94), "",
            row(["Pos", "Bezeichnung", "Menge", "EP netto", "GP netto"], w, "llrrr")]
            + [row([p, t, str(q), eur(u), eur(g)], w, "llrrr") for p, t, q, u, g in factor_rows]
            + ["", row(["", "Summe netto", "", "", eur(n)], w, "llrrr"),
               row(["", "USt 19 %", "", "", eur(vat_of(n, 19))], w, "llrrr"),
               row(["", "Gesamt brutto", "", "", eur(tot(n, vat_of(n, 19)))], w, "llrrr")])))
    assert [o[0] for o in offers] == [D("1585.00"), D("1642.00"), D("1719.00")]
    begr = ("Der Antrag ZB-2027-0702 über 1.585,00 € netto enthält drei Angebote, und das günstigste ist gewählt. Das "
            "Feld „Beauftragt: Kostenstellenbevollmächtigte:r“ ist aber leer („Unterschrift folgt“), und laut "
            "Begleitmail ist Prof. Haubenreißer nicht beteiligt; er steht auch nicht in Kopie. Nach der "
            "Uni-Kassel-Seite „Beschaffung“ müssen Bestellungen vom Kostenstellenbevollmächtigten (meist "
            "Fachgebietsleitung) beauftragt werden. Ohne diese Beauftragung kann nicht bestellt werden; der Antrag "
            "wird abgelehnt.")
    case(PROC, "beschaffungsantrag-d10", "abgelehnt", begr,
         [doc("beschaffungsantrag.pdf", form, font="Helvetica"),
          doc("email-beschaffungsantrag.pdf", mail, font="Helvetica"),
          doc("angebot-1.pdf", offers[0][1]),
          doc("angebot-2.pdf", offers[1][1], font="Times-Roman"),
          doc("angebot-3.pdf", offers[2][1], font="Helvetica")],
         "Force-torque sensor, 1.585 EUR net, three offers and cheapest chosen, but the cost-centre holder's order field is blank ('signature follows'), professor on sabbatical",
         "„Bestellungen müssen vom Kostenstellenbevollmächtigten (meist Fachgebietsleitung) beauftragt werden.“",
         SRC_BESCH, "form ZB-3 + OWA mail + three offers", "no", "high")


# =========================================================================== #
# EXPENSE REIMBURSEMENT
# =========================================================================== #
def online_form(nr, sent, person, unit, purpose, belege, total, kont, extra=None, signer=None):
    """print of the online form 'Digitale Abrechnung privat verauslagter Kosten'"""
    lines = [lr("Universität Wernstadt · Digitale Abrechnung privat verauslagter Kosten", f"Vorgang {nr}"),
             lr("Online-Formular (Pilotverfahren) · Druckansicht", f"gesendet {sent}"),
             "",
             kv([("Antragsteller:in", person), ("Organisationseinheit", unit), ("Kontierung", kont)], k=26),
             "",
             "Zweck / dienstlicher Anlass"]
    lines += ["  " + p for p in purpose]
    lines += ["", "Belege",
              "  " + row(["Nr.", "Beleg", "Datum", "Betrag"], [4, 60, 10, 12], "lllr")]
    for i, (b, d_, a) in enumerate(belege, 1):
        lines.append("  " + row([str(i), b, d_, eur(a) + " €"], [4, 60, 10, 12], "lllr"))
    lines += ["  " + row(["", "Erstattungsbetrag", "", eur(total) + " €"], [4, 60, 10, 12], "lllr")]
    if extra:
        lines += [""] + ["  " + e for e in extra]
    lines += ["", "Die Originalbelege bewahre ich ein halbes Jahr auf. Ich versichere die Richtigkeit der Angaben.",
              f"Sachlich richtig: {signer}" if signer else "Sachlich richtig: (Workflow Kostenstelle)",
              "", "Formular FIN-PVK-01 · Pilot bis 31.12.2026, verlängert"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# d11  angenommen (trap): hospitality of guests after a colloquium talk; tip on the bill is not claimed
# --------------------------------------------------------------------------- #
def d11():
    day = "2027-06-10"
    food = [("Kalbsrahmgeschnetzeltes mit Spätzle", 3, "24.80"), ("Zanderfilet auf Rahmlinsen", 2, "26.50"),
            ("Gemüse-Risotto", 1, "18.90"), ("Vorspeisensalat", 2, "8.40")]
    drinks = [("Mineralwasser 0,75 l", 3, "6.90"), ("Pils 0,3 l", 5, "3.90"),
              ("Grauburgunder 0,75 l Flasche", 1, "29.00"), ("Kaffee", 4, "2.90")]
    f_sum = tot(*[q * D(p) for _, q, p in food])
    d_sum = tot(*[q * D(p) for _, q, p in drinks])
    assert (f_sum, d_sum) == (D("163.10"), D("80.80"))
    total = tot(f_sum, d_sum)
    assert total == D("243.90")
    f_net, f_vat = vat_split(f_sum, 7)
    d_net, d_vat = vat_split(d_sum, 19)
    tip = D("16.10")
    paid = tot(total, tip)
    assert paid == D("260.00")
    persons = 6
    assert total / persons <= 60
    w = [4, 40, 10, 10]
    bill = ["GASTHAUS ZUR ALTEN SCHMIEDE",
            "Inh. Th. Wöllenstein · Brüder-Grimm-Platz 3 · 34117 Wernstadt",
            "Steuer-Nr. 26 812 40357 · Tel. 0561 77 30 14",
            "",
            "RECHNUNG Nr. 2027-06-0418         Tisch 12",
            f"Datum: {wd(day)}  19:08 - 22:41",
            "Rechnungsempfänger: Universität Wernstadt,",
            "FG Strömungsmechanik, " + UW_ADDR,
            "",
            row(["Anz", "Artikel", "EP", "Betrag"], w, "rlrr")]
    for name, q, p in food + drinks:
        bill.append(row([str(q), name, eur(p), eur(q * D(p))], w, "rlrr"))
    bill += ["-" * 70,
             row(["", "Speisen (7 %)", "", eur(f_sum)], w, "rlrr"),
             row(["", "Getränke (19 %)", "", eur(d_sum)], w, "rlrr"),
             row(["", "SUMME EUR", "", eur(total)], w, "rlrr"),
             row(["", f"Netto 7 %  {eur(f_net)}   MwSt {eur(f_vat)}", "", ""], w, "rlrr"),
             row(["", f"Netto 19 % {eur(d_net)}   MwSt {eur(d_vat)}", "", ""], w, "rlrr"),
             "",
             "TSE-Seriennr. 7f31c0a9e2 · TSE-Transaktion 118402 · Kasse 2",
             "Bezahlt: Kreditkarte",
             "",
             "handschriftlich:  + Trinkgeld 16,10  = 260,00 gezahlt",
             "",
             "Angaben zum Nachweis der Höhe und der betrieblichen Veranlassung von Bewirtungsaufwendungen",
             f"Tag der Bewirtung: {de(day)}    Ort: Gasthaus Zur Alten Schmiede, Wernstadt",
             "Bewirtete Personen: siehe Teilnehmerliste (Anlage)",
             "Anlass: Gastvortrag im Strömungsmechanischen Kolloquium, Anbahnung Folgeprojekt mit Ventimar",
             "Unterschrift des Bewirtenden: [unterschrieben]  Prof. Dr. Ansgar Tiedemann-Holm"]
    form = online_form(
        "PVK-2027-03318", "Fr 11.06.2027 10:02", "Prof. Dr. Ansgar Tiedemann-Holm",
        "FB 15 Maschinenbau · FG Strömungsmechanik", 
        ["Bewirtung nach dem Gastvortrag von Prof. Dr. Ingrid Halvorsen im Strömungsmechanischen Kolloquium",
         f"am {de(day)}; Gespräch über das geplante Folgeprojekt mit der Ventimar Engineering B.V.",
         "",
         "Teilnehmende (G = Gast, U = Universitätsbedienstete):",
         "  G  Prof. Dr. Ingrid Halvorsen, Universitetet i Nordvik (Gastvortragende)",
         "  G  Dr. Pieter van Assche, Ventimar Engineering B.V., Rotterdam",
         "  G  Dipl.-Ing. Carola Mittelstraß, Ventimar Engineering B.V., Bremen",
         "  U  Prof. Dr. Ansgar Tiedemann-Holm (Gastgeber)",
         "  U  Dr. Lina Okafor-Brandt",
         "  U  Tim Reschke, M.Sc.",
         "",
         f"6 Personen · {eur(total)} € · {eur(r2(total / persons))} € je Person"],
        [("Rechnung Gasthaus Zur Alten Schmiede Nr. 2027-06-0418", de2(day), total)],
        total,
        "15 6210 / Auftrag 7-3315026 (Kooperation Ventimar)",
        ["Erstattungsbetrag ohne Trinkgeld (16,10 € nicht beantragt).",
         "Finanzierung: Kooperationsvertrag Ventimar, § 6 Abs. 2 lässt Bewirtungskosten im Projekt zu.",
         "Anlagen: Rechnung mit Bewirtungsnachweis, Einladung Kolloquium, Kreditkartenabrechnung."],
        signer="Prof. Dr. Ansgar Tiedemann-Holm (Kostenstellenbevollmächtigter), 11.06.2027")
    inv = "\n".join([
        "Strömungsmechanisches Kolloquium · Sommersemester 2027",
        "Universität Wernstadt · FB 15 Maschinenbau · FG Strömungsmechanik",
        "",
        "EINLADUNG",
        "",
        f"{wde_long(day)}, 16:15 Uhr, Hörsaal 0110",
        "",
        "Prof. Dr. Ingrid Halvorsen (Universitetet i Nordvik):",
        "„Kavitationserosion an Schiffspropellern – Messung und Modellierung“",
        "",
        "Gäste sind herzlich willkommen. Gastgeber: Prof. Dr. Ansgar Tiedemann-Holm",
    ])
    kk = "\n".join([
        "Kreditkartenabrechnung · Mastercard Gold ****5512 · Ansgar Tiedemann-Holm",
        "Abrechnungszeitraum 01.06.2027 - 30.06.2027",
        "",
        row(["Beleg", "Buchung", "Verwendungszweck", "Betrag EUR"], [10, 10, 52, 12], "lllr"),
        row([de(day), de("2027-06-11"), "GASTHAUS ZUR ALTEN SCHMIEDE WERNSTADT", "-" + eur(paid)], [10, 10, 52, 12], "lllr"),
        row([de("2027-06-14"), de("2027-06-15"), "BUCHHANDLUNG AM STERN", "-38,90"], [10, 10, 52, 12], "lllr"),
    ])
    begr = ("Erstattet werden soll die Bewirtung von drei externen Gästen und drei Universitätsbediensteten nach einem "
            "Gastvortrag im Kolloquium (243,90 €, 40,65 € je Person). Nach der Bewirtungskostenrichtlinie auf der "
            "Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ ist das erstattungsfähig: dienstlicher Anlass mit "
            "Gästen (Kooperation, Drittmitteleinwerbung), Höchstsatz 60 € pro Person und Veranstaltungstag "
            "eingehalten, Finanzierung aus einem Kooperationsauftrag mit dargelegtem Projektbezug, Teilnehmerliste "
            "mit Kennzeichnung der Gäste, maschinelle Rechnung mit TSE-Nummer, Speisen und Getränken, Datum, Ort, "
            "Steuernummer, Empfänger Universität und Unterschrift des Bewirtenden. Das Trinkgeld von 16,10 € ist "
            "nicht erstattungsfähig und wurde richtigerweise nicht beantragt; die Kartenbelastung von 260,00 € "
            "erklärt sich dadurch. Die Erstattung von 243,90 € ist zu gewähren.")
    case(EXP, "auslagenerstattung-d11", "angenommen", begr,
         [doc("bewirtungsrechnung.pdf", "\n".join(bill), size=(340.0, 842.0)),
          doc("erstattungsformular.pdf", form, font="Helvetica"),
          doc("einladung-kolloquium.pdf", inv, font="Helvetica"),
          doc("kreditkartenabrechnung.pdf", kk)],
         "Dinner with 3 external guests and 3 staff after a colloquium talk, 40,65 EUR per head; card charge 260,00 includes a handwritten tip, claim 243,90 excludes it",
         "„Nicht erstattungsfähige Aufwendungen sind … Aufwendungen für Trinkgelder und Pfand“; „Veranstaltungen "
         "(z.B. Tagungen, Konferenzen, Symposien, Kolloquien) Pro Person und Veranstaltungstag € 60,-.“; "
         "„Bewirtungskosten werden nur erstattet, wenn bei der Veranstaltung ein angemessenes Verhältnis von "
         "externen und internen Teilnehmern gegeben ist.“",
         SRC_FIBU + " (Bewirtungskostenrichtlinie)",
         "restaurant bill with TSE line and handwritten tip + online form print + invitation + card statement",
         "yes (amounts differ: 260,00 charged vs 243,90 claimed)", "high")


# --------------------------------------------------------------------------- #
# d12  abgelehnt: till receipt says only "Büromaterial", keyword written is again only "Büromaterial"
# --------------------------------------------------------------------------- #
def d12():
    day = "2027-02-17"
    a, b = D("14.90"), D("8.50")
    total = tot(a, b)
    net, vat = vat_split(total, 19)
    bon = "\n".join([
        "   PAPETERIE GÖRTZ & SOHN",
        "   Obere Königsstr. 28",
        "   34117 Wernstadt",
        "   St.-Nr. 26 803 11942",
        "",
        "WG12 BUEROMATERIAL      " + eur(a).rjust(7),
        "WG12 BUEROMATERIAL      " + eur(b).rjust(7),
        "------------------------------",
        "SUMME EUR               " + eur(total).rjust(7),
        "BAR                       25,00",
        "RUECKGELD                  " + eur(D(25) - total),
        "",
        f"MWST 19% NETTO {eur(net)} MWST {eur(vat)}",
        f"BON 20871  KASSE 1  {de2(day)} 09:12",
        "TSE 0c44e1 TA 55219",
        "  DANKE FUER IHREN EINKAUF",
    ])
    mail = owa_mail(
        "rechnung",
        "Erstattung Bon Büromaterial",
        "Maren Lüdecke-Saran <maren.luedecke-saran@uni-wernstadt.de>",
        "Do 18.02.2027 08:15",
        "Finanzbuchhaltung <rechnung@uni-wernstadt.de>",
        ["Hallo,",
         "",
         "anbei der Bon vom 17.02. über 23,40 €. Es war Büromaterial für die Klausuraufsicht am 18.02., das",
         "kurzfristig fehlte. Ich habe es bar bezahlt und bitte um Erstattung auf mein Konto.",
         "Kostenstelle 16 1200 (Sekretariat Institut für Elektrotechnik).",
         "",
         "Viele Grüße",
         "Maren Lüdecke-Saran",
         "Sekretariat Institut für Elektrotechnik"],
        footer_when="18.02.2027 08:15")
    form = online_form(
        "PVK-2027-00791", "Do 18.02.2027 08:21", "Maren Lüdecke-Saran", "FB 16 · Sekretariat Institut für Elektrotechnik",
        ["Büromaterial für die Klausuraufsicht"],
        [("Kassenbon Papeterie Görtz & Sohn, Bon 20871", de2(day), total)], total, "16 1200")
    begr = ("Eingereicht ist ein Kassenbon über 23,40 €, der nur zweimal die Warengruppe „Büromaterial“ ausweist; "
            "Mail und Formular nennen als Zweck ebenfalls nur „Büromaterial für die Klausuraufsicht“. Nach der "
            "Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ muss bei einer Quittung ohne Artikel ein Stichwort "
            "dazugeschrieben werden, und nach der Seite „Glossar Drittmittelbewirtschaftung“ ist bei Büromaterial "
            "anzugeben, um welche Artikel es sich handelt; die Bezeichnung „Büromaterial“ ist nicht ausreichend. "
            "Welche Artikel gekauft wurden, ist nicht erkennbar. Die Erstattung ist abzulehnen, bis die Artikel "
            "benannt sind.")
    case(EXP, "auslagenerstattung-d12", "abgelehnt", begr,
         [doc("kassenbon.pdf", bon, size=RECEIPT, jitter=1.0),
          doc("email-erstattung.pdf", mail, font="Helvetica"),
          doc("erstattungsformular.pdf", form, font="Helvetica")],
         "Cash receipt for 23,40 EUR showing only the product group 'Büromaterial'; mail and form also say only 'Büromaterial'",
         "„Büromaterial Es ist anzugeben, um welche Artikel es sich handelt. Die Bezeichnung Büromaterial“ ist nicht "
         "ausreichend.“ with „Sollte auf der Quittung kein Artikel ausgewiesen sein, muss ein Stichwort (Schleifpapier "
         "für Labor) dazu geschrieben werden.“",
         SRC_GLOS + "; " + SRC_FIBU, "thermal till receipt (narrow, jitter) + OWA mail + online form", "no", "high")


# --------------------------------------------------------------------------- #
# d13  abgelehnt: till receipt and the invoice issued for the same receipt claimed side by side
# --------------------------------------------------------------------------- #
def d13():
    day = "2027-05-25"
    items = [("Silikon transparent 310 ml", 2, "6.49"), ("Montagekleber 290 g", 1, "8.99"),
             ("Alu-Winkelprofil 20x20 mm, 2 m", 3, "7.45"), ("Schrauben-Sortiment Edelstahl", 1, "19.85")]
    total = tot(*[q * D(p) for _, q, p in items])
    assert total == D("64.17")
    net, vat = vat_split(total, 19)
    bon = ["HAGEDORN BAU & GARTEN", "Leipziger Str. 201 · 34123 Wernstadt", "St.-Nr. 26 241 77105", ""]
    for n, q, p in items:
        bon += [n[:30], f"  {q} x {eur(p)}".ljust(26) + eur(q * D(p)).rjust(8)]
    bon += ["-" * 34, "SUMME EUR".ljust(26) + eur(total).rjust(8), "EC-KARTE".ljust(26) + eur(total).rjust(8),
            f"MWST 19% NETTO {eur(net)} MWST {eur(vat)}", f"BON 7314 KASSE 05 {de2(day)} 15:47", "TSE 9a02bd TA 30117"]
    w = [4, 40, 6, 9, 10]
    rechnung = ["HAGEDORN BAU & GARTEN GmbH · Leipziger Str. 201 · 34123 Wernstadt · St.-Nr. 26 241 77105", "",
                "Universität Wernstadt", "FB 14 · FG Hydromechanik und Hydrologie", UW_ADDR, "",
                lr("RECHNUNG Nr. R-27-031944", f"Datum: {de(day)}", 94),
                f"zu Kassenbon 7314, Kasse 05, vom {de(day)} 15:47 (bezahlt mit EC-Karte)", "",
                row(["Pos", "Artikel", "Menge", "Preis", "Betrag"], w, "llrrr")]
    for i, (n, q, p) in enumerate(items, 1):
        rechnung.append(row([str(i), n, str(q), eur(p), eur(q * D(p))], w, "llrrr"))
    rechnung += ["", row(["", "Gesamtbetrag (bereits bezahlt)", "", "", eur(total)], w, "llrrr"),
                 row(["", f"enthaltene MwSt 19 % auf {eur(net)}", "", "", eur(vat)], w, "llrrr")]
    scan = "\n".join(bon) + "\f" + "\n".join(rechnung)
    form = online_form(
        "PVK-2027-02944", "Mi 26.05.2027 08:40", "Dr. Jannik Feuerhake", "FB 14 · FG Hydromechanik und Hydrologie",
        ["Material für die Versuchsrinne (Abdichtung und Halterung der Messsonden), dringend für die",
         "Messreihe am 26.05.2027; im Baumarkt gekauft und mit EC-Karte bezahlt."],
        [("Kassenbon Hagedorn Bau & Garten, Bon 7314", de2(day), total),
         ("Rechnung Hagedorn Bau & Garten R-27-031944", de2(day), total)],
        tot(total, total), "14 2510 / Auftrag 2140733",
        ["Anlage: Belege (Scan, 2 Seiten), Kontoauszug."])
    ka = "\n".join([
        "Kontoauszug Nr. 5/2027 · Girokonto · Jannik Feuerhake",
        "",
        row(["Buchung", "Valuta", "Vorgang", "Betrag EUR"], [10, 10, 58, 12], "lllr"),
        row([de("2027-05-26"), de(day), "Kartenzahlung girocard HAGEDORN BAU UND GARTEN WERNSTADT", "-" + eur(total)], [10, 10, 58, 12], "lllr"),
        row([de("2027-05-27"), de("2027-05-27"), "Lastschrift Stadtwerke Abschlag", "-84,00"], [10, 10, 58, 12], "lllr"),
    ])
    begr = ("Geltend gemacht werden 128,34 € aus zwei Belegen über je 64,17 €: dem Kassenbon 7314 vom 25.05.2027 und der "
            "Rechnung R-27-031944, die ausdrücklich „zu Kassenbon 7314“ ausgestellt ist, mit denselben Positionen "
            "und dem Vermerk „bereits bezahlt“. Der Kontoauszug zeigt nur eine Kartenzahlung über 64,17 €. Derselbe "
            "Einkauf wird damit zweimal abgerechnet; wie im Fall auslagenerstattung-06 der Organisatoren kann er nur "
            "einmal erstattungsfähig sein. Die Erstattung ist in dieser Form abzulehnen.")
    case(EXP, "auslagenerstattung-d13", "abgelehnt", begr,
         [doc("belege-scan.pdf", scan, jitter=1.4),
          doc("erstattungsformular.pdf", form, font="Helvetica"),
          doc("kontoauszug.pdf", ka)],
         "Hardware-store purchase of 64,17 EUR claimed twice (till receipt and the invoice issued for that receipt, one 2-page scan), 128,34 claimed, one debit",
         "Organisers: „Dieselbe Bestellung wird damit zweimal abgerechnet … erstattungsfähig kann die Bestellung nur "
         "einmal sein.“",
         SRC_GT_E06, "multi-page scan (receipt + invoice) + online form + bank statement", "no", "high")


# --------------------------------------------------------------------------- #
# d14  angenommen (trap): TH Sallstedt, English EU invoice in DKK, reverse charge, card statement in EUR
# --------------------------------------------------------------------------- #
def d14():
    inv_d, pay_d, sub_d = "2027-03-08", "2027-03-09", "2027-04-19"
    lines_ = [("NDIR CO2 sensor module, 0-5,000 ppm, factory calibrated", 2, D("465.00")),
              ("Calibration certificate (ISO 17025)", 1, D("160.00")),
              ("Shipping DE, tracked", 1, D("90.00"))]
    dkk = tot(*[q * p for _, q, p in lines_])
    assert dkk == D("1180.00")
    rate = D("7.4605")
    eur_amt = r2(dkk / rate)
    fee = r2(eur_amt * D("0.0175"))
    claim = tot(eur_amt, fee)
    assert (eur_amt, fee, claim) == (D("158.17"), D("2.77"), D("160.94"))
    assert days_between(inv_d, sub_d) <= 92
    w = [52, 4, 12, 12]
    invoice = "\n".join([
        "Sensorværk ApS · Finlandsgade 25 · 8200 Aarhus N · Denmark",
        "CVR/VAT DK 41 88 20 57 · www.sensorvaerk.example",
        "",
        "INVOICE",
        kv([("Invoice no.", "SV-2027-00418"), ("Invoice date", en_date(inv_d)), ("Order no.", "WEB-77215"),
            ("Payment", "Visa card ****9034, paid " + en_date(pay_d))], k=16, indent=0),
        "",
        "Bill to:",
        "  Technische Hochschule Sallstedt",
        "  Labor für Umweltmesstechnik, attn. Marek Sobczyk-Lindner",
        "  Hochschulring 4, 29525 Sallstedt, Germany",
        "  VAT ID DE 8146 0317 2",
        "",
        row(["Description", "Qty", "Unit DKK", "Amount DKK"], w, "lrrr"),
    ] + [row([d_, str(q), en(p), en(q * p)], w, "lrrr") for d_, q, p in lines_] + [
        "",
        row(["Subtotal", "", "", en(dkk)], w, "lrrr"),
        row(["VAT 0 % - reverse charge, Art. 196 Directive 2006/112/EC", "", "", "0.00"], w, "lrrr"),
        row(["TOTAL DKK", "", "", en(dkk)], w, "lrrr"),
        "",
        "Thank you for your order. Goods shipped " + en_date(pay_d) + ".",
    ])
    kk = "\n".join([
        "Sparkasse Sallstedt-Uelzener Land · Visa Card Umsatzübersicht",
        "Karteninhaber: Marek Sobczyk-Lindner · Karte ****9034 · Abrechnung März 2027",
        "",
        row(["Umsatz", "Buchung", "Händler", "Fremdwährung", "Kurs", "EUR"], [10, 10, 30, 14, 8, 10], "lllrrr"),
        row([de(pay_d), de("2027-03-10"), "SENSORVAERK APS AARHUS", "DKK " + eur(dkk), "7,4605", "-" + eur(eur_amt)],
            [10, 10, 30, 14, 8, 10], "lllrrr"),
        row([de(pay_d), de("2027-03-10"), "Auslandseinsatzentgelt 1,75 %", "", "", "-" + eur(fee)],
            [10, 10, 30, 14, 8, 10], "lllrrr"),
        row([de("2027-03-12"), de("2027-03-15"), "BAECKEREI RIEKEN SALLSTEDT", "", "", "-6,40"],
            [10, 10, 30, 14, 8, 10], "lllrrr"),
    ])
    form = "\n".join([
        "TECHNISCHE HOCHSCHULE SALLSTEDT · Haushaltsabteilung",
        "ANTRAG AUF ERSTATTUNG VERAUSLAGTER BETRÄGE (Formular HA-07, Stand 2026)",
        "",
        "Hinweise:",
        " 1. Beizufügen ist die Originalrechnung, ausgestellt auf die TH Sallstedt; Kassen- oder EC-Belege",
        "    ohne Artikelangabe ersetzen keine Rechnung.",
        " 2. Bei Zahlung in Fremdwährung ist der belastete Euro-Betrag durch Kreditkarten- oder Kontoauszug",
        "    nachzuweisen. Auslandseinsatzentgelte der Karte werden mit erstattet.",
        " 3. Der Antrag ist spätestens drei Monate nach Rechnungsdatum einzureichen.",
        " 4. Die Kostenstellenverantwortliche Person zeichnet sachlich richtig.",
        "",
        kv([("Antragsteller:in", "Dipl.-Ing. Marek Sobczyk-Lindner"),
            ("Einrichtung", "Labor für Umweltmesstechnik, Fakultät Technik"),
            ("Kostenstelle / Projekt", "0731 / UM-27-02"),
            ("Gegenstand", "2 CO2-Sensormodule (NDIR) mit Kalibrierschein"),
            ("Grund der Eigenbeschaffung", "Messkampagne ab 15.03.2027; Lieferzeit über den Einkauf ca. 4 Wochen,"),
            ("", "Hersteller liefert nur über eigenen Webshop")], k=28, indent=1),
        "",
        " " + row(["Beleg", "Datum", "Betrag"], [56, 12, 12], "llr"),
        " " + row(["Rechnung Sensorværk ApS SV-2027-00418 (DKK 1.180,00)", de(inv_d), eur(eur_amt) + " €"], [56, 12, 12], "llr"),
        " " + row(["Auslandseinsatzentgelt laut Visa-Abrechnung", de(pay_d), eur(fee) + " €"], [56, 12, 12], "llr"),
        " " + row(["Erstattungsbetrag", "", eur(claim) + " €"], [56, 12, 12], "llr"),
        "",
        f" Sallstedt, {de(sub_d)}     gez. M. Sobczyk-Lindner",
        " Sachlich richtig: gez. Prof. Dr. Gesine Wartenberg-Ude (Laborleitung, Kostenstelle 0731), " + de(sub_d),
        " Eingang Haushaltsabteilung: " + de("2027-04-20"),
    ])
    begr = ("Fall der TH Sallstedt, entschieden auf den eigenen Unterlagen: Das Formular HA-07 verlangt die "
            "Originalrechnung auf die TH, bei Fremdwährung den Nachweis des belasteten Euro-Betrags (Auslandseinsatz"
            "entgelt wird erstattet), Einreichung binnen drei Monaten nach Rechnungsdatum und die Zeichnung "
            "„sachlich richtig“. Die englische Rechnung SV-2027-00418 vom 08.03.2027 über DKK 1.180,00 ist an das "
            "Labor für Umweltmesstechnik der TH gerichtet und nennt die Artikel; 0 % USt ist bei einer "
            "innergemeinschaftlichen Lieferung an eine Einrichtung mit USt-IdNr. korrekt. Die Visa-Abrechnung "
            "belegt 158,17 € plus 2,77 € Auslandseinsatzentgelt, zusammen genau die beantragten 160,94 €. "
            "Eingereicht am 19.04.2027, sachlich richtig gezeichnet. Die Erstattung ist zu gewähren.")
    case(EXP, "auslagenerstattung-d14", "angenommen", begr,
         [doc("erstattungsantrag-ha07.pdf", form),
          doc("invoice-sensorvaerk.pdf", invoice, font="Helvetica"),
          doc("visa-umsatzuebersicht.pdf", kk)],
         "TH Sallstedt: English Danish invoice in DKK with 0 % VAT (reverse charge) for two sensor modules; card statement converts to EUR plus 1,75 % fee; all conditions printed on the TH's own form met",
         "Form HA-07 of the TH (the case's own rule text): „Bei Zahlung in Fremdwährung ist der belastete Euro-Betrag "
         "durch Kreditkarten- oder Kontoauszug nachzuweisen. Auslandseinsatzentgelte der Karte werden mit erstattet.“ "
         "and „Der Antrag ist spätestens drei Monate nach Rechnungsdatum einzureichen.“",
         SRC_SAL, "TH paper form with printed rules + English EU invoice (DKK, reverse charge) + card statement",
         "yes (foreign currency, 0 % VAT, claim differs from invoice amount)", "high")


# --------------------------------------------------------------------------- #
# d15  angenommen (trap): web-shop invoice minus credit note for a returned defective item
# --------------------------------------------------------------------------- #
def d15():
    inv_d, cn_d, sub_d = "2027-04-13", "2027-04-22", "2027-04-26"
    items = [("Steckernetzteil 12 V / 2 A, Labor", 2, "18.90"), ("USB-Oszilloskop-Tastkopf-Set 1:1/1:10", 1, "54.90"),
             ("Steckbrücken-Kabelsatz 65-teilig", 3, "7.95"), ("Lötrauchabsaugung, Tischgerät mit Aktivkohlefilter", 1, "64.90"),
             ("Versandkosten", 1, "5.90")]
    total = tot(*[q * D(p) for _, q, p in items])
    assert total == D("187.35")
    credit = D("64.90")
    claim = r2(total - credit)
    assert claim == D("122.45")
    net, vat = vat_split(total, 19)
    cnet, cvat = vat_split(credit, 19)
    w = [4, 54, 6, 10, 10]
    inv = ["Elektronik-Versand Kellermann GmbH · Gutenbergring 40 · 22848 Norderstedt", "USt-IdNr. DE 301 552 870", "",
           "Rechnungsanschrift:                          Lieferanschrift:",
           "Universität Wernstadt                        Universität Wernstadt, Labor Mikrosystemtechnik",
           "FB 16 · FG Mikrosystemtechnik                Raum 2.207, z. Hd. Dr. Eske Brammertz",
           UW_ADDR + "        " + UW_ADDR, "",
           lr("RECHNUNG EVK-27-552031", f"Rechnungsdatum {de(inv_d)}", 94),
           "Bestellung 27-0988341 vom " + de("2027-04-12") + " · Zahlart: Kreditkarte (bezahlt)", "",
           row(["Pos", "Artikel", "Menge", "Preis", "Summe"], w, "llrrr")]
    for i, (n, q, p) in enumerate(items, 1):
        inv.append(row([str(i), n, str(q), eur(p) + " €", eur(q * D(p)) + " €"], w, "llrrr"))
    inv += ["", row(["", "Rechnungsbetrag brutto", "", "", eur(total) + " €"], w, "llrrr"),
            row(["", f"enthaltene USt 19 % (netto {eur(net)} €)", "", "", eur(vat) + " €"], w, "llrrr")]
    gs = "\n".join([
        "Elektronik-Versand Kellermann GmbH · Gutenbergring 40 · 22848 Norderstedt", "",
        "Universität Wernstadt · FB 16 · FG Mikrosystemtechnik · " + UW_ADDR, "",
        lr("GUTSCHRIFT EVK-GS-27-01377", f"Datum {de(cn_d)}", 94),
        "zur Rechnung EVK-27-552031 vom " + de(inv_d) + " · Retoure R-27-44120 (Ware defekt: Lüfter ohne Funktion)", "",
        row(["Pos", "Artikel", "Menge", "Preis", "Summe"], w, "llrrr"),
        row(["4", "Lötrauchabsaugung, Tischgerät mit Aktivkohlefilter", "1", eur(credit) + " €", "-" + eur(credit) + " €"], w, "llrrr"),
        "", row(["", "Gutschriftbetrag brutto", "", "", "-" + eur(credit) + " €"], w, "llrrr"),
        row(["", f"enthaltene USt 19 % (netto {eur(cnet)} €)", "", "", eur(cvat) + " €"], w, "llrrr"),
        "", "Der Betrag wird dem bei der Bestellung verwendeten Zahlungsmittel gutgeschrieben.",
    ])
    kk = "\n".join([
        "Kreditkartenabrechnung · Visa ****6021 · Dr. Eske Brammertz · April 2027", "",
        row(["Umsatz", "Buchung", "Verwendungszweck", "Betrag EUR"], [10, 10, 52, 12], "lllr"),
        row([de(inv_d), de("2027-04-14"), "ELEKTRONIK-VERSAND KELLERMANN NORDERSTEDT", "-" + eur(total)], [10, 10, 52, 12], "lllr"),
        row([de(cn_d), de("2027-04-23"), "GUTSCHRIFT ELEKTRONIK-VERSAND KELLERMANN", "+" + eur(credit)], [10, 10, 52, 12], "lllr"),
    ])
    form = online_form(
        "PVK-2027-02210", f"{wd(sub_d)} 14:05", "Dr. Eske Brammertz", "FB 16 · FG Mikrosystemtechnik",
        ["Kleinteile für den Praktikumsversuch „Sensorkennlinien“ am 15.04.2027; über SAP nicht rechtzeitig",
         "lieferbar. Die defekte Lötrauchabsaugung wurde zurückgeschickt und gutgeschrieben."],
        [("Rechnung Elektronik-Versand Kellermann EVK-27-552031", de2(inv_d), total),
         ("Gutschrift EVK-GS-27-01377 (Retoure)", de2(cn_d), -credit)],
        claim, "16 2740 / Auftrag 2160415",
        ["Anlagen: Rechnung, Gutschrift, Kreditkartenabrechnung."])
    begr = ("Die Rechnung EVK-27-552031 über 187,35 € ist an das FG Mikrosystemtechnik der Universität Wernstadt "
            "gerichtet, nennt die Artikel und wurde privat per Kreditkarte bezahlt. Die defekte Lötrauchabsaugung "
            "(64,90 €) ging zurück, die Gutschrift EVK-GS-27-01377 bezieht sich ausdrücklich auf diese Rechnung, und "
            "die Kartenabrechnung zeigt Belastung und Rückbuchung. Beantragt sind genau 122,45 € = 187,35 € − "
            "64,90 €, wie im Fall auslagenerstattung-05 der Organisatoren (Rechnung abzüglich Gutschrift). Es sind "
            "kleine, dringend für einen Praktikumsversuch benötigte Teile, wie es der Abschnitt Kostenerstattung der "
            "Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ für private Auslagen vorsieht. Die Erstattung von "
            "122,45 € ist zu gewähren.")
    case(EXP, "auslagenerstattung-d15", "angenommen", begr,
         [doc("rechnung-kellermann.pdf", "\n".join(inv), font="Helvetica"),
          doc("gutschrift-retoure.pdf", gs, font="Helvetica"),
          doc("kreditkartenabrechnung.pdf", kk),
          doc("erstattungsformular.pdf", form, font="Helvetica")],
         "Web-shop invoice 187,35 EUR billed to the chair, one defective item returned (credit note 64,90), claim is the balance 122,45",
         "„In Ausnahmefällen kann es sein, dass Angestellte der Universität kleinere, zeitlich dringende Anschaffungen "
         "selbst besorgt haben und diese Auslagen zurück erstattet haben möchten.“ with the organisers' reading for "
         "credit notes: „Handschriftlich wird genau der Saldo von 135,68 € geltend gemacht, er ergibt sich aus "
         "121,38 € + 83,32 € abzüglich 69,02 €.“ (accepted)",
         SRC_FIBU + "; " + SRC_GT_E05, "web-shop invoice with separate delivery address + credit note + card statement + online form",
         "yes (claim differs from invoice total)", "high")


# =========================================================================== #
# Build, verify, table
# =========================================================================== #
ALL = [d01, d02, d03, d04, d05, d06, d07, d08, d09, d10, d11, d12, d13, d14, d15]

WEEKDAY_RX = re.compile(
    r"\b(Mo|Di|Mi|Do|Fr|Sa|So|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|"
    r"Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?,? (\d{2})\.(\d{2})\.(\d{4})")
WEEKDAY_EN_RX = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun), (\d{2}) (" + "|".join(MON_EN) + r") (\d{4})")
WEEKDAY_DE_LONG_RX = re.compile(r"\b(" + "|".join(WD_L) + r"), (\d{1,2})\. (" + "|".join(MON_DE) + r") (\d{4})")
WD_ALL = {**{s: i for i, s in enumerate(WD_S)}, **{s: i for i, s in enumerate(WD_L)},
          **{s: i for i, s in enumerate(WD_EN)}}


def weekday_problems(cid, name, text):
    probs = []
    for m in WEEKDAY_RX.finditer(text):
        day = datetime.date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
        if WD_ALL[m.group(1)] != day.weekday():
            probs.append(f"{cid}/{name}: weekday mismatch '{m.group(0)}'")
    for m in WEEKDAY_EN_RX.finditer(text):
        day = datetime.date(int(m.group(4)), MON_EN.index(m.group(3)) + 1, int(m.group(2)))
        if WD_ALL[m.group(1)] != day.weekday():
            probs.append(f"{cid}/{name}: weekday mismatch '{m.group(0)}'")
    for m in WEEKDAY_DE_LONG_RX.finditer(text):
        day = datetime.date(int(m.group(4)), MON_DE.index(m.group(3)) + 1, int(m.group(2)))
        if WD_ALL[m.group(1)] != day.weekday():
            probs.append(f"{cid}/{name}: weekday mismatch '{m.group(0)}'")
    return probs


def words(text):
    return text.split()


def build():
    for fn in ALL:
        fn()
    if OUT.exists():
        shutil.rmtree(OUT)
    problems = []
    n_pdf = 0
    for c in CASES:
        d = OUT / c["set"] / "inputs" / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        for name, text, opts in c["docs"]:
            problems += weekday_problems(c["id"], name, text)
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
        "# Blind set 4: proposals (15 cases, pick 10)",
        "",
        "Built by `experiments/blind4/tools/make_blind4.py`, written blind (no solver code, tests, earlier "
        "experiment sets or their docs were read). Each label follows from the quoted rule. Sources: policy "
        "pages in `the University of Kassel policy pages (not included here)` (corpus doc ids given), the organisers' ground truth and "
        "decision trails, and for the TH Sallstedt case the TH's own form text.",
        "",
        "Blindness note: while locating the PDF helper in `experiments/blind3/tools/make_blind3.py`, a grep "
        "for function names also printed the one-line comment headers of blind3 cases c01-c05 (1st-class rail "
        "and hotel over 80 EUR justified, Israel trip, honorarium, private stay of exactly 5 working days, "
        "pro-rata private BahnCard). No case body was read. These five patterns were avoided here.",
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
        for fn in ALL:
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
