#!/usr/bin/env python3
"""Build the second BLIND proposal set for UniAgent Task 2 (15 cases, the author picks 10).

Written without looking at the solver (facts.py, rules.py, predict.py, ...), its tests or
its earlier experiment sets. Sources used: the policy pages in the University of Kassel policy pages (not included here)
and the organisers' practice data (README, ground truth, decision trails). Every label
rests on a rule quoted verbatim in experiments/blind2-proposals/PROPOSALS.md.

The documents imitate systems the practice generator does not use: SAP Fiori (German and
English UI), an SAP SRM shopping cart, a hotel portal, an airline e-ticket, a legacy paper
form, a scanned form with OCR noise, till receipts on a narrow page, English supplier
quotations and invoices, multi-page bundles holding several documents, TH Sallstedt mail.

    python3 experiments/blind2/tools/make_blind2.py           # build + verify
    python3 experiments/blind2/tools/make_blind2.py --table   # print the proposals table

Needs only python3 and poppler's pdftotext. Output (overwritten):
experiments/blind2-proposals/<set>/{inputs/<case>/*.pdf, ground-truth.jsonl}, PROPOSALS.md.
The PDF writer follows experiments/variants/tools/make_variants.py (pure Python, base-14
fonts, WinAnsi, one text line per line), extended with Helvetica column placement, page
breaks, narrow receipt pages and a small x-jitter for scan-like documents.
"""
import json
import pathlib
import random
import re
import shutil
import subprocess
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "blind2-proposals"
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

A4 = (595.28, 841.89)
RECEIPT = (226.77, 700.0)


# --------------------------------------------------------------------------- #
# Minimal PDF writer
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
# Layout helpers
# --------------------------------------------------------------------------- #
def lr(left, right, w=104):
    return left + " " * max(3, w - len(left) - len(right)) + right


def kv(rows, k=28, indent=2):
    return "\n".join((" " * indent + a.ljust(k) + b) if a else (" " * (indent + k) + b) for a, b in rows)


def money(x):
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
CASES = []


def case(set_, cid, result, begruendung, docs, desc, rule, source, imitates, trap, conf):
    CASES.append(dict(set=set_, id=cid, result=result, begruendung=begruendung, docs=docs, desc=desc,
                      rule=rule, source=source, imitates=imitates, trap=trap, conf=conf))


def doc(name, text, **opts):
    return (name, text, opts)


UW = "Universität Wernstadt"

# ---------------------------------------------------------------- b01 ------ #
b01_antrag = "\n".join([
    lr("SAP Fiori · Meine Reisen und Spesen", UW),
    lr("Reiseantrag anzeigen", "Druckansicht 02.02.2027 16:41"),
    "",
    "Reise 0004471203 · Hannover · 13.04.2027 – 15.04.2027",
    lr("Status: Zur Genehmigung gesendet", "Genehmigende Person: Prof. Dr. Konstantin Ebersbach-Lunz"),
    "",
    "Reisende Person",
    kv([("Name", "Dr. Jorinde Haltermann-Weiß"),
        ("Personalnummer", "00718244"),
        ("Organisationseinheit", "Fachbereich 15 Maschinenbau, Fachgebiet Werkstoffprüfung"),
        ("Dienstort", "Wernstadt"),
        ("Beschäftigung", "wissenschaftliche Mitarbeiterin")]),
    "",
    "Reisedaten",
    kv([("Reiseart", "Inlandsdienstreise"),
        ("Zielland / Ort", "Deutschland / Hannover"),
        ("Anlass", "WERKSTOFFTAGE NORD 2027, Fachmesse für Werkstoffprüfung, Fachforum ZfP"),
        ("Dienstlicher Zweck", "Vortrag „Zerstörungsfreie Prüfung von Faserverbund-Bauteilen mit"),
        ("", "aktiver Thermografie“ im Fachforum (14.04.2027, 10:30 Uhr); Gespräche mit den"),
        ("", "Industriepartnern des Projekts THERMOPRÜF"),
        ("Beginn", "13.04.2027, 07:12 Uhr (ab Wohnung)"),
        ("Ende", "15.04.2027, 20:05 Uhr (an Wohnung)"),
        ("Dienstgeschäft", "13.04.2027, 13:00 Uhr bis 15.04.2027, 15:00 Uhr"),
        ("Private Verlängerung", "nein"),
        ("Verkehrsmittel", "Bahn, 2. Klasse; ÖPNV am Messeort")]),
    "",
    "Kostenschätzung",
    "  Kostenart                                              Menge   Einzelbetrag        Betrag",
    "  Bahn Wernstadt Hbf – Hannover Hbf und zurück               2        47,90 €       95,80 €",
    "  Übernachtung Hotel Kronsberg Garten (ohne Frühstück)       2       112,00 €      224,00 €",
    "  ÖPNV Hannover, Tageskarte                                  2         3,60 €        7,20 €",
    "  Messeeintritt (Referentenausweis, kostenfrei)              1         0,00 €        0,00 €",
    "  Summe                                                                          327,00 €",
    "  Tagegeld: wird mit der Reisekostenabrechnung festgesetzt",
    "",
    "Begründung Übernachtungskosten über 80,00 € je Nacht",
    "  Während der WERKSTOFFTAGE NORD sind die Hotels in Hannover stark ausgelastet. Recherche im",
    "  Hotelportal am 01.02.2027 (Ausdruck als Anlage 3): im Umkreis von 10 km um das Messegelände ist",
    "  kein Einzelzimmer unter 112,00 € je Nacht verfügbar; gebucht wurde das günstigste verfügbare",
    "  Angebot. Für Hannover bestehen keine Hotelvereinbarungen der Universität.",
    "",
    "Finanzierung",
    kv([("Kostenstelle / Auftrag", "15 3120 / Drittmittelprojekt THERMOPRÜF (Auftrag 6230118)")]),
    "",
    "Anlagen",
    "  1  Einladung Fachforum ZfP (E-Mail vom 27.01.2027)",
    "  2  Hotelbuchung Hotel Kronsberg Garten, Buchungsnummer 5512093418",
    "  3  Ausdruck Hotelportal-Recherche vom 01.02.2027",
    "",
    "Kommentar der reisenden Person",
    "  Die Bahnfahrt wird nach der Genehmigung über das Firmenkundenportal gebucht.",
    "",
    "Gesendet am 02.02.2027 16:39 von Dr. Jorinde Haltermann-Weiß",
])
b01_hotel = "\n".join([
    lr("roomfinder.example · Ihre Buchungsbestätigung", "Buchungsnummer 5512093418"),
    "",
    "Hotel Kronsberg Garten",
    "Kattenbrookstrift 61 · 30539 Hannover · Tel. 0511 87 33 120",
    "",
    kv([("Gast", "Dr. Jorinde Haltermann-Weiß"),
        ("Rechnungsadresse", UW),
        ("", "Fachbereich 15 · Fachgebiet Werkstoffprüfung"),
        ("", "Ostring 14, 35293 Wernstadt"),
        ("Anreise", "Dienstag, 13. April 2027 (ab 15:00 Uhr)"),
        ("Abreise", "Donnerstag, 15. April 2027 (bis 11:00 Uhr)"),
        ("Zimmer", "1 × Einzelzimmer Standard, Nichtraucher"),
        ("Verpflegung", "ohne Frühstück (vor Ort 16,00 € pro Person, nicht gebucht)")], k=22, indent=0),
    "",
    "Preisdetails",
    "  13.04.2027      Einzelzimmer Standard                 112,00 €",
    "  14.04.2027      Einzelzimmer Standard                 112,00 €",
    "  Gesamtpreis inkl. 7 % MwSt.                           224,00 €",
    "",
    kv([("Zahlung", "im Hotel bei Abreise; Rechnung auf die Rechnungsadresse"),
        ("Stornierung", "kostenfrei bis 06.04.2027, 18:00 Uhr; danach 90 % des Gesamtpreises"),
        ("Gebucht am", "01.02.2027, 23:31 Uhr")], k=22, indent=0),
    "",
    "Der Messezuschlag während der WERKSTOFFTAGE NORD ist im Preis enthalten.",
])
b01_recherche = "\n".join([
    lr("roomfinder.example/suche?ort=hannover-messegelaende", "01.02.2027, 23:14"),
    "",
    "Hannover (Messegelände) · 13.04.2027 – 15.04.2027 · 2 Nächte · 1 Erwachsener · 1 Einzelzimmer",
    "Filter: Entfernung zum Messegelände bis 10 km · Sortierung: Preis (niedrigster zuerst)",
    "19 von 186 Unterkünften haben freie Zimmer",
    "",
    "  Unterkunft                       Entfernung   Bewertung   Preis pro Nacht   Verfügbarkeit",
    "  Pension Am Seelhorster Turm      3,1 km       7,9         –                 ausgebucht",
    "  Gästehaus Bemerode               2,4 km       8,2         –                 ausgebucht",
    "  Hotel Kronsberg Garten           1,8 km       8,4         112 €             2 Zimmer frei",
    "  Hotel Mittelfeld                 2,9 km       7,6         124 €             verfügbar",
    "  City Inn Hannover Süd            6,7 km       8,0         139 €             verfügbar",
    "  Hotel am Expo-Park               0,9 km       8,8         156 €             1 Zimmer frei",
    "  Grand Hotel Leineufer            8,2 km       9,1         189 €             verfügbar",
    "",
    "Alle Preise inkl. MwSt., ohne Frühstück. Während Messen gelten erhöhte Preise.",
    "Seite 1 von 3",
])
b01_mail = "\n".join([
    "Von:       Fachforum ZfP <fachforum@werkstofftage-nord.example>",
    "Gesendet:  Mittwoch, 27. Januar 2027 09:18",
    "An:        Haltermann-Weiß, Jorinde <jorinde.haltermann-weiss@uni-wernstadt.de>",
    "Betreff:   Einladung als Referentin – Fachforum ZfP, WERKSTOFFTAGE NORD 2027",
    "",
    "Sehr geehrte Frau Dr. Haltermann-Weiß,",
    "",
    "im Namen des Programmbeirats laden wir Sie herzlich ein, im Fachforum Zerstörungsfreie Prüfung der",
    "WERKSTOFFTAGE NORD 2027 (13. bis 15. April 2027, Messegelände Hannover) vorzutragen:",
    "",
    "    Mittwoch, 14. April 2027, 10:30 bis 11:00 Uhr, Halle 4, Forum B",
    "    „Zerstörungsfreie Prüfung von Faserverbund-Bauteilen mit aktiver Thermografie“",
    "",
    "Vortragende erhalten einen Referentenausweis für alle drei Messetage. Ein Honorar wird nicht",
    "gezahlt; Reise- und Übernachtungskosten übernimmt der Veranstalter nicht.",
    "",
    "Bitte bestätigen Sie Ihre Teilnahme bis zum 05.02.2027.",
    "",
    "Mit freundlichen Grüßen",
    "Dr. Arne Völkening",
    "Programmbeirat Fachforum ZfP · WERKSTOFFTAGE NORD",
])
case(TRIP, "dienstreiseantrag-b01", "angenommen",
     "Die Übernachtungskosten von 112,00 € je Nacht liegen über der Inlandshöchstgrenze von 80,00 €. Nach der "
     "Uni-Kassel-Seite „Dienstreisemanagement“ werden darüber hinausgehende Übernachtungskosten erstattet, wenn sie "
     "unvermeidbar waren und die Notwendigkeit bei Antragstellung schriftlich begründet ist; die Bemühungen um eine "
     "preiswerte Unterkunft sollen etwa durch den Ausdruck eines Onlineportals dokumentiert werden. Der Antrag enthält "
     "diese Begründung (Messewoche), der Portalausdruck vom 01.02.2027 zeigt, dass kein günstigeres Zimmer verfügbar "
     "war und das günstigste gebucht wurde. Die Buchung lautet auf die Universität, der Antrag ist über zwei Monate "
     "vor Reisebeginn gestellt, die Einladung als Referentin belegt das dienstliche Interesse, ein Honorar wird nicht "
     "gezahlt, die Summe 327,00 € geht auf. Der Antrag wird angenommen.",
     [doc("reiseantrag-fiori.pdf", b01_antrag, font="Helvetica", producer="SAP NetWeaver 7.58",
          creator="SAP Fiori My Travel Requests"),
      doc("hotel-buchungsbestaetigung.pdf", b01_hotel, font="Helvetica", producer="Chromium Skia/PDF"),
      doc("hotelportal-recherche.pdf", b01_recherche, font="Helvetica", producer="Chromium Skia/PDF"),
      doc("email-einladung-fachforum.pdf", b01_mail, producer="Microsoft: Print To PDF")],
     "Domestic fair talk, hotel 112 EUR/night (> 80 cap) but justified in the Fiori request with a hotel-portal printout",
     "„Darüber hinaus gehende Übernachtungskosten werden nur erstattet, wenn sie unvermeidbar waren. D. h. die "
     "Notwendigkeit ist im Einzelfall nachvollziehbar schriftlich bei Antragsstellung zu begründen.“ and „ihre "
     "Bemühungen, eine preiswerte Unterkunft zu bekommen, im Einzelnen dokumentieren (z. B. Ausdruck eines Onlineportals …)“",
     "dienstreisemanagement.md", "SAP Fiori request (German UI), hotel portal booking + search printout, Outlook mail",
     "yes (looks wrong: over the 80 EUR cap)", "high")

# ---------------------------------------------------------------- b02 ------ #
b02_form = "\n".join([
    lr("UNIVERSITÄT WERNSTADT", "Abteilung Personal und Organisation", 100),
    lr("", "Reisekostenstelle", 100),
    "FORMULAR REISEANTRAG",
    "(nur in begründeten Ausnahmefällen anstelle des ESS-/Fiori-Antrags zu verwenden)",
    "Grund für Papierantrag: Fiori-Zugang nach Wechsel der Kostenstelle noch nicht freigeschaltet",
    "",
    "1. Antragsteller/in",
    "   Name, Vorname:        Querfurth-Adebayo, Malte, Dr.",
    "   Einrichtung:          FB 16 Elektrotechnik/Informatik, FG Technische Akustik",
    "   Dienstort:            Wernstadt",
    "   Telefon / E-Mail:     0561 7390-4418 / malte.querfurth-adebayo@uni-wernstadt.de",
    "",
    "2. Reiseziel und Zweck",
    "   Ort, Staat:           Wien, Österreich",
    "   Veranstaltung:        Vienna Colloquium on Room Acoustics 2027 (VCRA 2027), 21.-22.06.2027",
    "   Zweck:                Eingeladener Hauptvortrag (Keynote) „Data-driven Prediction of",
    "                         Reverberation in Coupled Rooms“; Einladung liegt bei",
    "   Reise ins Ausland:    [X] ja   [ ] nein",
    "   A1-Bescheinigung:     beantragt am 08.03.2027",
    "",
    "3. Zeitraum",
    "   Reisebeginn:          20.06.2027, 09:40 Uhr       Reiseende: 23.06.2027, 19:55 Uhr",
    "   Dienstgeschäft:       21.06.2027, 09:00 Uhr bis 22.06.2027, 17:30 Uhr",
    "   Privater Aufenthalt:  [ ] ja   [X] nein",
    "",
    "4. Beförderungsmittel",
    "   [X] Bahn, 2. Klasse   [ ] Flugzeug   [ ] privater Pkw   [ ] Dienstwagen",
    "",
    "5. Voraussichtliche Kosten",
    "   Bahn Wernstadt Hbf - Wien Hbf und zurück (Sparpreis, 2. Kl.)      239,80 EUR",
    "   Übernachtung Hotel Wiedner Hof, 3 Nächte à 92,00 EUR               276,00 EUR",
    "   Teilnahmegebühr (für Vortragende erlassen)                           0,00 EUR",
    "   Summe                                                              515,80 EUR",
    "",
    "6. Leistungen Dritter (Kostenübernahme, Honorar, Sachleistungen)",
    "   [X] keine   [ ] ja, und zwar: ______________________________________",
    "",
    "7. Finanzierung",
    "   Kostenstelle 16 2210 (Landesmittel, Reisemittel des Fachgebiets)",
    "",
    "8. Abschlag beantragt",
    "   [ ] ja   [X] nein",
    "",
    "Wernstadt, 08.03.2027          gez. Malte Querfurth-Adebayo",
    "                               Unterschrift Antragsteller/in",
    "",
    "Dienstliches Interesse bestätigt, Reise befürwortet:",
    "Wernstadt, 09.03.2027          gez. Prof. Dr. Elke Brandenstein-Mutua",
    "                               Fachgebietsleitung",
    "",
    "Formular RK-1 · Stand 03/2025",
])
b02_mail = "\n".join([
    "Subject:  VCRA 2027 – Invitation to give a keynote lecture",
    "From:     Prof. Dr. Theresa Lindmayr <chair@vcra2027.example>",
    "Date:     15.02.2027, 14:22",
    "To:       Malte Querfurth-Adebayo <malte.querfurth-adebayo@uni-wernstadt.de>",
    "",
    "Dear Dr. Querfurth-Adebayo,",
    "",
    "on behalf of the organising committee of the Vienna Colloquium on Room Acoustics 2027 (VCRA 2027),",
    "21-22 June 2027, I am delighted to invite you to give one of the two keynote lectures, on",
    "21 June 2027, 09:30-10:30.",
    "",
    "As a keynote speaker, your registration fee is waived. In appreciation of your contribution we are",
    "also pleased to offer a speaker honorarium of EUR 750.00, which will be transferred to your personal",
    "bank account after the colloquium. Please return the enclosed payee form with your bank details and",
    "tax identification number by 30 April 2027. Travel and accommodation are arranged by the speakers.",
    "",
    "Rooms at the conference rate (EUR 92.00 per night) can be booked at Hotel Wiedner Hof until",
    "15 May 2027 with the code VCRA27.",
    "",
    "We would be very glad if you could accept this invitation.",
    "",
    "With kind regards,",
    "Theresa Lindmayr",
    "Chair, VCRA 2027 Organising Committee",
    "",
    "Attachment: payee_form_VCRA2027.pdf",
])
b02_bahn = "\n".join([
    lr("Fernverkehr Mitteleuropa · Ihr Reiseplan", "erstellt am 07.03.2027, 18:02"),
    "Angebot – noch nicht gebucht",
    "",
    "Hinfahrt   So 20.06.2027   Wernstadt Hbf ab 09:40   Wien Hbf an 18:58    2 Umstiege",
    "Rückfahrt  Mi 23.06.2027   Wien Hbf ab 10:02        Wernstadt Hbf an 19:55   2 Umstiege",
    "",
    "Tarif: Sparpreis Europa, 2. Klasse, 1 Erwachsener, Zugbindung",
    "",
    "   Hinfahrt                         119,90 EUR",
    "   Rückfahrt                        119,90 EUR",
    "   Gesamtpreis                      239,80 EUR",
    "",
    "Der Preis gilt bei Buchung bis 14.03.2027.",
])
b02_hotel = "\n".join([
    lr("Hotel Wiedner Hof", "Reservierungsbestätigung Nr. WH-27-06614"),
    "Margaretenstraße 38 · 1040 Wien · Österreich",
    "",
    "Rechnungsanschrift:  Universität Wernstadt, FB 16, FG Technische Akustik,",
    "                     z. Hd. Dr. Malte Querfurth-Adebayo, Ostring 14, 35293 Wernstadt, Deutschland",
    "Gast:                Dr. Malte Querfurth-Adebayo",
    "Anreise / Abreise:   20.06.2027 / 23.06.2027 (3 Nächte)",
    "Zimmer:              Einzelzimmer, Konferenzrate VCRA27, ohne Frühstück",
    "",
    "   20.06.2027   Einzelzimmer       92,00 EUR",
    "   21.06.2027   Einzelzimmer       92,00 EUR",
    "   22.06.2027   Einzelzimmer       92,00 EUR",
    "   Summe inkl. 10 % USt.          276,00 EUR",
    "",
    "Kostenfreie Stornierung bis 7 Tage vor Anreise. Ortstaxe wird vor Ort berechnet.",
])
case(TRIP, "dienstreiseantrag-b02", "abgelehnt",
     "Die beigefügte Einladung der VCRA 2027 sagt dem Antragsteller für den Hauptvortrag ein Honorar von 750,00 EUR "
     "zu, das nach dem Kolloquium auf sein privates Konto überwiesen wird. Nach der Uni-Kassel-Seite "
     "„Dienstreisemanagement“ deutet ein Honorar für einen Vortrag auf eine Nebentätigkeit und damit auf eine privat "
     "veranlasste Reise hin; eine Dienstreisegenehmigung und Reisekostenabrechnung aus Landes- oder Drittmitteln ist "
     "dann grundsätzlich nicht möglich. Der Antrag kreuzt bei „Leistungen Dritter“ dennoch „keine“ an und beantragt die "
     "vollen Kosten von 515,80 EUR aus Landesmitteln. Der Antrag wird abgelehnt.",
     [doc("reiseantrag-formular.pdf", b02_form, producer="Adobe Acrobat Pro 2020", creator="Acrobat PDFMaker"),
      doc("email-einladung-keynote.pdf", b02_mail, producer="Mozilla Thunderbird"),
      doc("bahn-reiseplan.pdf", b02_bahn, font="Helvetica", producer="Chromium Skia/PDF"),
      doc("hotel-reservierung.pdf", b02_hotel, font="Helvetica", producer="iText 7.2")],
     "Keynote in Vienna on a legacy paper form; the English invitation offers a EUR 750 speaker honorarium, the form ticks 'Leistungen Dritter: keine'",
     "„Wird Ihnen im Rahmen einer Dienstreise ein Honorar (z.B. für einen Vortrag) gezahlt, deutet dies auf eine "
     "Nebentätigkeit und damit auf eine privat veranlasste Reise hin. Eine Dienstreisegenehmigung und nachfolgende "
     "Reisekostenabrechnung aus Landes- oder Drittmitteln der Universität Kassel ist dann grundsätzlich nicht möglich!“",
     "dienstreisemanagement.md", "legacy fillable paper form RK-1, Thunderbird mail (English), rail portal, Austrian hotel",
     "yes (looks complete and timely, A1 applied; the honorarium sits in the English mail)", "high")

# ---------------------------------------------------------------- b03 ------ #
b03_req = "\n".join([
    lr("SAP Fiori · My Travel and Expenses", UW),
    lr("Travel Request", "Printed 10.05.2027 11:07"),
    "",
    "Trip 0004471388 · Haifa · 06.09.2027 – 10.09.2027",
    lr("Status: Sent for approval", "Approver: Prof. Dr. Gernot Habicht-Mensah"),
    "",
    "Traveller",
    kv([("Name", "Dr. Svenja Ruhnau-Kaplan"),
        ("Personnel number", "00720931"),
        ("Organisational unit", "FB 14 Bauingenieurwesen, Fachgebiet Hydrologie"),
        ("Home office", "Wernstadt")]),
    "",
    "Trip data",
    kv([("Trip type", "Foreign business trip"),
        ("Destination", "Haifa"),
        ("Occasion", "CAM 2027 – International Workshop on Coastal Aquifer Modelling"),
        ("Business purpose", "Oral presentation of the accepted paper „Saltwater intrusion under"),
        ("", "variable recharge: a coupled model“ (session 3, 08.09.2027)"),
        ("Start", "06.09.2027, 05:30 (home)"),
        ("End", "10.09.2027, 22:40 (home)"),
        ("Business activity", "07.09.2027 09:00 – 09.09.2027 16:00"),
        ("Private extension", "no"),
        ("Means of transport", "Flight (economy); rail to and from Frankfurt Airport"),
        ("Abroad", "yes"),
        ("Posting certificate", "to be checked by the travel office")]),
    "",
    "Cost estimate",
    "  Expense type                                      Qty        Amount",
    "  Flight FRA – Haifa area – FRA, economy              1      612,00 €",
    "  Rail Wernstadt Hbf – Frankfurt Airport, return      1      118,00 €",
    "  Hotel Carmel View, 4 nights at 128,00 €             4      512,00 €",
    "  Workshop registration                               1      220,00 €",
    "  Total                                                    1.462,00 €",
    "",
    "Funding",
    kv([("Cost centre / order", "14 5520 / DFG project SALTCOAST (order 6240207)")]),
    "",
    "Attachments",
    "  1  Acceptance notification (e-mail of 28.04.2027)",
    "  2  Flight offer, Reisebüro Fuldatal GmbH (3 options)",
    "",
    "Sent on 10.05.2027 11:05 by Dr. Svenja Ruhnau-Kaplan",
])
b03_mail = "\n".join([
    "From:     CAM 2027 Programme Committee <cam2027@ccri.example.ac.il>",
    "To:       svenja.ruhnau-kaplan@uni-wernstadt.de",
    "Date:     Wed, 28 Apr 2027 17:03:41 +0300",
    "Subject:  CAM 2027 – paper #41 accepted for oral presentation",
    "",
    "Dear Dr. Ruhnau-Kaplan,",
    "",
    "we are happy to inform you that your paper #41 „Saltwater intrusion under variable recharge: a",
    "coupled model“ has been accepted for oral presentation at CAM 2027, the International Workshop on",
    "Coastal Aquifer Modelling, hosted by the Carmel Coast Research Institute, Haifa, Israel,",
    "7-9 September 2027. Your talk is scheduled in session 3 on 8 September 2027.",
    "",
    "Registration (EUR 220) opens on 15 May 2027. A list of partner hotels near the campus is attached.",
    "",
    "Best regards,",
    "Programme Committee CAM 2027",
    "Carmel Coast Research Institute, Haifa, Israel",
])
b03_flug = "\n".join([
    lr("Reisebüro Fuldatal GmbH", "Angebot Nr. RF-27-05519"),
    "Königstor 9 · 35291 Wernstadt · firmenreisen@reisebuero-fuldatal.example",
    "",
    "Universität Wernstadt, FB 14, Fachgebiet Hydrologie",
    "z. Hd. Dr. Svenja Ruhnau-Kaplan                                         Datum: 06.05.2027",
    "",
    "Flugangebot Frankfurt – Tel Aviv – Frankfurt, 06.09.2027 – 10.09.2027, 1 Person, Economy",
    "",
    "  Option   Hinflug                       Rückflug                      Tarif              Preis",
    "  A        06.09. FRA 09:15 – TLV 14:20  10.09. TLV 15:40 – FRA 19:05  Economy Classic   612,00 €",
    "  B        06.09. FRA 06:50 – TLV 15:55  10.09. TLV 06:10 – FRA 13:45  Economy, 1 Stopp  587,00 €",
    "           (Umstieg Wien, 2 h 20 min)    (Umstieg Wien, Reiseende vor Workshop-Ende nicht möglich)",
    "  C        06.09. FRA 12:30 – TLV 17:35  10.09. TLV 17:15 – FRA 20:45  Economy Flex      798,00 €",
    "",
    "Empfehlung: Option A (Direktflug; Option B erzwingt eine zusätzliche Hotelnacht).",
    "Preise inkl. Steuern und Gebühren, Stand 06.05.2027, Buchung nach Genehmigung.",
    "Transfer Flughafen Tel Aviv – Haifa: Bahn, ca. 1 h.",
])
case(TRIP, "dienstreiseantrag-b03", "abgelehnt",
     "Der Antrag ist vollständig und rechtzeitig, das Reiseziel Haifa liegt jedoch in Israel (Annahmemitteilung: "
     "„Carmel Coast Research Institute, Haifa, Israel“; Flug nach Tel Aviv). Nach der Uni-Kassel-Seite "
     "„Dienstreisemanagement“ werden Dienstreisen unter anderem nach Israel bis auf Weiteres nicht genehmigt. "
     "Der Antrag wird abgelehnt.",
     [doc("travel-request-fiori.pdf", b03_req, font="Helvetica", producer="SAP NetWeaver 7.58",
          creator="SAP Fiori My Travel Requests (EN)"),
      doc("email-acceptance.pdf", b03_mail, producer="Apple Mail"),
      doc("flugangebot-reisebuero.pdf", b03_flug, producer="Microsoft Word 2019")],
     "Complete, timely English-UI Fiori request for a workshop in Haifa; the country appears only in the attachments",
     "„Es wird darauf hingewiesen, dass Dienstreisen in die Russische Föderation, in die Ukraine, nach Belarus, "
     "Moldau- …, Niger, Iran, Israel, in die Palästinensischen Gebiete und Libanon bis auf Weiteres nicht genehmigt werden.“",
     "dienstreisemanagement.md", "SAP Fiori request in English UI, Apple Mail (English), travel-agency Word offer",
     "yes (formally perfect; the destination field shows only the city)", "high")

# ---------------------------------------------------------------- b04 ------ #
b04_p1 = "\n".join([
    lr("Technische Hochschule Sallstedt", "Personalabteilung · Reisestelle", 100),
    "Hochschulring 3 · 29541 Sallstedt",
    "",
    lr("DIENSTREISEANTRAG (Inland)", "Vorgangsnr. DR-2027-0815", 100),
    lr("", "Eingang Reisestelle: 31.08.2027", 100),
    "",
    "Antragsteller:in            Jannik Overbeck-Saalfeld, M.Sc. (wissenschaftlicher Mitarbeiter)",
    "Fakultät / Labor            Fakultät Elektrotechnik, Labor für Leistungselektronik",
    "Reiseziel                   Dresden",
    "Anlass                      Fachtagung Leistungshalbleiter 2027, 19.-20.10.2027",
    "Dienstlicher Zweck          Posterbeitrag „Gate-Treiber für SiC-MOSFETs mit aktiver Miller-Klemmung“,",
    "                            angenommen laut Mitteilung vom 22.08.2027 (Seite 2)",
    "Abreise                     18.10.2027, 16:10 Uhr",
    "Rückkehr                    20.10.2027, 21:35 Uhr",
    "Dienstgeschäft              19.10.2027, 08:30 Uhr bis 20.10.2027, 16:00 Uhr",
    "Anreise am Vortag, weil     Tagungsbeginn 08:30 Uhr; die erste Verbindung ab Sallstedt erreicht",
    "                            Dresden erst um 10:47 Uhr",
    "Verkehrsmittel              Bahn, 2. Klasse",
    "Privataufenthalt            keiner",
    "",
    "Voraussichtliche Kosten",
    "   Bahn Sallstedt – Dresden Hbf und zurück (Seite 4)              129,80 EUR",
    "   Hotel Elbterrasse, 2 Nächte à 96,00 EUR inkl. Frühstück        192,00 EUR",
    "   Tagungsgebühr (Rechnung an die Hochschule)                     180,00 EUR",
    "   Gesamt                                                         501,80 EUR",
    "",
    "Finanzierung                Kostenstelle 4120 Labor Leistungselektronik (Haushaltsmittel)",
    "",
    "Datum, Unterschrift         30.08.2027   gez. J. Overbeck-Saalfeld",
    "Befürwortung Laborleitung   30.08.2027   gez. Prof. Dr. Ansgar Wilmsmeier",
    "",
    "Hinweise der Reisestelle (Reisekostenrichtlinie der TH Sallstedt)",
    " - Dienstreisen sind vor Reiseantritt zu beantragen und zu genehmigen (Ziff. 2.1).",
    " - Bahnfahrten werden in der 2. Klasse erstattet (Ziff. 3.1).",
    " - Übernachtungskosten werden gegen Nachweis bis 110,00 EUR je Nacht erstattet (Ziff. 4.2).",
    "",
    "Seite 1 von 4",
])
b04_p2 = "\n".join([
    "Von:      Tagungsbüro Fachtagung Leistungshalbleiter <tagung@leistungshalbleiter-fachtagung.example>",
    "An:       jannik.overbeck-saalfeld@th-sallstedt.de",
    "Datum:    So 22.08.2027 20:41",
    "Betreff:  Ihr Posterbeitrag P-17 wurde angenommen",
    "",
    "Sehr geehrter Herr Overbeck-Saalfeld,",
    "",
    "Ihr Beitrag „Gate-Treiber für SiC-MOSFETs mit aktiver Miller-Klemmung“ wurde als Poster P-17",
    "angenommen. Die Postersession findet am 19.10.2027 von 14:00 bis 16:00 Uhr statt; Ihre Anwesenheit",
    "am Poster ist erforderlich. Die Tagung beginnt am 19.10.2027 um 08:30 Uhr und endet am 20.10.2027",
    "um 16:00 Uhr. Die Teilnahmegebühr für Posterautoren beträgt 180,00 EUR.",
    "",
    "Mit freundlichen Grüßen",
    "Tagungsbüro Fachtagung Leistungshalbleiter 2027, Dresden",
    "",
    "Seite 2 von 4",
])
b04_p3 = "\n".join([
    lr("hotelfinder24.example – Buchungsbestätigung", "Buchung HF-88120473", 100),
    "",
    "Hotel Elbterrasse · Terrassenufer 12 · 01069 Dresden",
    "",
    "Rechnungsempfänger:   Technische Hochschule Sallstedt, Labor für Leistungselektronik,",
    "                      Hochschulring 3, 29541 Sallstedt",
    "Gast:                 Jannik Overbeck-Saalfeld",
    "Zeitraum:             18.10.2027 – 20.10.2027, 2 Nächte",
    "Zimmer:               Einzelzimmer Komfort inkl. Frühstück",
    "Preis:                2 × 96,00 EUR = 192,00 EUR (inkl. MwSt.)",
    "Zahlung:              Rechnung an die Hochschule",
    "Stornierung:          kostenfrei bis 16.10.2027",
    "",
    "Seite 3 von 4",
])
b04_p4 = "\n".join([
    "Reisebuchung · Auftrag 7741 9920 3381 · gebucht am 01.09.2027",
    "Kunde: Technische Hochschule Sallstedt (Firmenkunde), Reisender: Jannik Overbeck-Saalfeld",
    "",
    "  Mo 18.10.2027  Sallstedt ab 16:10  ->  Dresden Hbf an 20:52   2. Klasse   64,90 EUR",
    "  Mi 20.10.2027  Dresden Hbf ab 16:58  ->  Sallstedt an 21:35   2. Klasse   64,90 EUR",
    "  Summe                                                                   129,80 EUR",
    "",
    "Zahlung: Firmenkundenkonto der Hochschule. Dieses Dokument ist keine Fahrkarte.",
    "",
    "Seite 4 von 4",
])
b04_rech = "\n".join([
    lr("Fachtagung Leistungshalbleiter 2027", "Rechnung Nr. FLH27-0233"),
    lr("c/o Kongressdienst Elbland GmbH · Ostra-Allee 5 · 01067 Dresden", "Datum: 03.09.2027"),
    "",
    "Technische Hochschule Sallstedt",
    "Fakultät Elektrotechnik, Labor für Leistungselektronik",
    "Hochschulring 3, 29541 Sallstedt",
    "",
    "Teilnehmer: Jannik Overbeck-Saalfeld (Posterautor P-17)",
    "",
    "  Teilnahmegebühr Posterautor, 19.-20.10.2027          151,26 EUR",
    "  zzgl. 19 % USt.                                       28,74 EUR",
    "  Rechnungsbetrag                                      180,00 EUR",
    "",
    "Zahlbar bis 01.10.2027 ohne Abzug. Bankverbindung: IBAN DE07 8505 1100 0031 7720 45",
])
case(TRIP, "dienstreiseantrag-b04", "angenommen",
     "Der Fall gehört zur Technischen Hochschule Sallstedt und wird nach den vorgelegten Unterlagen entschieden. "
     "Antrag, Annahmemitteilung, Hotelbuchung, Bahnbuchung und Tagungsrechnung stimmen in Daten und Beträgen überein "
     "(129,80 € + 192,00 € + 180,00 € = 501,80 €); der Antrag wurde sieben Wochen vor Reisebeginn gestellt, die "
     "Anreise am Vortag ist begründet. Der Übernachtungspreis von 96,00 € liegt über dem Kasseler Inlandswert von "
     "80,00 €, aber unter der im Antragsformular genannten Grenze der Reisekostenrichtlinie der TH Sallstedt "
     "(110,00 € je Nacht); die Hessischen Regeln gelten für Sallstedt nicht. Hotel- und Tagungsrechnung lauten auf die "
     "Hochschule. Der Antrag wird angenommen.",
     [doc("dienstreise-unterlagen.pdf", "\f".join([b04_p1, b04_p2, b04_p3, b04_p4]), producer="Canon iR-ADV C5840 PDF",
          creator="Scan to File"),
      doc("tagungsrechnung.pdf", b04_rech, font="Helvetica", producer="LibreOffice 7.6")],
     "TH Sallstedt domestic poster trip, one 4-page bundle (form + mail + hotel + rail); hotel 96 EUR/night, within Sallstedt's own 110 EUR cap",
     "README (procurement/expense sets): „The Sallstedt cases fall under another state's travel law, which is not in "
     "the corpora; they are decided on the documents alone.“ Form: „Übernachtungskosten werden gegen Nachweis bis "
     "110,00 EUR je Nacht erstattet (Ziff. 4.2).“",
     "dataset README.md + the case's own form", "TH Sallstedt form, multi-page scanned bundle, hotel portal, rail firm-customer booking",
     "yes (looks wrong under the Kassel 80 EUR cap)", "high")

# ---------------------------------------------------------------- b05 ------ #
b05_scan = "\n".join([
    "Scan 04.10.2027 08:52 · MFP-3.OG-Flur · Seite 1/1",
    "",
    lr("Universität Wernstadt", "Antrag auf Genehmigung einer Dienstreise", 100),
    lr("Abt. Personal und Organisation / Reisekostenste1le", "(Papierantrag)", 100),
    "",
    lr("Name: Wißmann-Tchoua, Lena", "Personal-Nr.: 0072 4410", 100),
    lr("Fachgebiet: Umweltökonomie (FB 07)", "Status: wiss. Mitarbeiterin", 100),
    lr("Reiseziel: Berlin", "Reise ins Ausland: [ ] ja  [x] nein", 100),
    "Zweck: Fachgespräch beim Projektträger zum Zwischenbericht des Projekts KREISLAUF-REGIO,",
    "       Einladung anbei",
    lr("Beginn der Reise: 09.11.2027, 04:50 Uhr", "Ende der Reise: 09.11.2027, 22:30 Uhr", 100),
    "Dienstgeschäft: 09.11.2027, 10:00 - 16:00 Uhr",
    "Verkehrsmitte1: [ ] Bahn  [x] Flugzeug  [ ] Pkw  [ ] Sonstiges",
    "",
    "Bei Flugreisen im Inland: Begründung (höhere Kosten anderer Verkehrsmittel oder wesentliche",
    "Einsparung von Arbeitszeit) als Anlage beifügen.        Anlage beigefügt:  [ ] ja   [ ] nein",
    "",
    "Kosten:",
    "  Flug Frankfurt (FRA) - Berlin (BER) und zurück, Economy                286,40 EUR",
    "  Bahn Wernstadt Hbf - Frankfurt Flughafen und zurück                     79,80 EUR",
    "  Summe                                                                  366,20 EUR",
    "",
    "Finanzierung: Projekt KREISLAUF-REGIO, Auftrag 6210533",
    "Anlagen: Einladung (E-Mai1 vom 01.10.2027), Flugbuchung",
    "",
    "Datum: 04.10.2027     Unterschrift: L. Wißmann-Tchoua",
    "Vorgesetzte/r (dienstl. Interesse bestätigt): Prof. Dr. Ortwin Kämpfer-Diop",
])
b05_ticket = "\n".join([
    "NORDWIND AIR · ITINERARY RECEIPT / E-TICKET",
    "",
    "Booking reference  K7QZ4M          Issued 05OCT27          Ticket number 512-2400918832",
    "Passenger          WISSMANN-TCHOUA/LENA MS",
    "Customer           UNIVERSITAET WERNSTADT FB07 UMWELTOEKONOMIE",
    "",
    "  Flight    Date      From                To                  Dep    Arr    Class        Status",
    "  NW 1102   09NOV27   FRANKFURT FRA T1    BERLIN BER T1       07:05  08:15  Y ECONOMY    OK",
    "  NW 1119   09NOV27   BERLIN BER T1       FRANKFURT FRA T1    18:40  19:50  Y ECONOMY    OK",
    "",
    "Fare               EUR 214.00",
    "Taxes/fees         EUR  72.40",
    "Total              EUR 286.40",
    "Form of payment    CC VI XXXXXXXXXXXX6612",
    "Baggage            1 piece cabin baggage 8 kg",
    "",
    "Fare conditions: non-refundable, change fee EUR 70.00 plus fare difference.",
])
b05_mail = "\n".join([
    "Von:      Projektträger Nachhaltige Regionen <fachgespraech@pt-nachhaltige-regionen.example>",
    "An:       lena.wissmann-tchoua@uni-wernstadt.de",
    "Datum:    Fr 01.10.2027 11:26",
    "Betreff:  Einladung Fachgespräch Zwischenbericht KREISLAUF-REGIO, 09.11.2027",
    "",
    "Sehr geehrte Frau Wißmann-Tchoua,",
    "",
    "zum Zwischenbericht des Verbundprojekts KREISLAUF-REGIO laden wir Sie zum Fachgespräch am",
    "Dienstag, 09.11.2027, 10:00 bis 16:00 Uhr, in unsere Räume in Berlin-Mitte ein. Bitte stellen Sie",
    "die Ergebnisse des Arbeitspakets 2 in etwa 30 Minuten vor.",
    "",
    "Reisekosten werden vom Projektträger nicht übernommen; sie sind aus den Projektmitteln zu tragen.",
    "",
    "Mit freundlichen Grüßen",
    "Projektträger Nachhaltige Regionen, Referat 3",
])
case(TRIP, "dienstreiseantrag-b05", "abgelehnt",
     "Beantragt ist ein Inlandsflug Frankfurt–Berlin für ein eintägiges Fachgespräch. Nach der Uni-Kassel-Seite "
     "„Dienstreisemanagement“ kommen Flugkosten im Inland grundsätzlich nur in Betracht, wenn bei Benutzung eines "
     "anderen regelmäßig verkehrenden Beförderungsmittels höhere Kosten entstehen oder besondere dienstliche Gründe "
     "(wesentliche Einsparung von Arbeitszeit) vorliegen; diese sind in einer Anlage zur Genehmigung darzulegen. Das "
     "Formular verlangt diese Anlage selbst, sie fehlt aber (kein Kästchen angekreuzt, keine Begründung, kein "
     "Vergleich mit der Bahn). Der Antrag ist zur Ergänzung zurückzugeben und wird abgelehnt.",
     [doc("dienstreiseantrag-scan.pdf", b05_scan, jitter=1.6, producer="Kyocera TASKalfa 3554ci",
          creator="Scan to PDF"),
      doc("eticket-itinerary.pdf", b05_ticket, producer="Amadeus e-Ticket Service"),
      doc("email-einladung.pdf", b05_mail, producer="Microsoft: Print To PDF")],
     "Scanned paper form (OCR noise) for a one-day domestic flight FRA-BER; the required reasons attachment for a domestic flight is missing",
     "„Flugkosten kommen im Inland grundsätzlich nur in Betracht, wenn bei Benutzung eines anderen regelmäßig "
     "verkehrenden Beförderungsmittels höhere Kosten entstehen oder besondere dienstliche Gründe (wesentliche "
     "Einsparung von Arbeitszeit) vorliegen. Diese sind in einer Anlage zur Genehmigung der Dienstreise darzulegen.“",
     "dienstreisemanagement.md", "scanned paper form with OCR noise, English airline e-ticket, mail",
     "yes (complete and timely; only an unticked box shows the gap)", "high")

# ---------------------------------------------------------------- b06 ------ #
b06_srm = "\n".join([
    lr("SAP SRM · Einkaufswagen", "Universität Wernstadt · Mandant 100"),
    lr("Einkaufswagen 1000348812  „Bürostühle Sekretariat Stadtplanung“", "Druck 11.05.2027 10:15"),
    lr("Status: Genehmigt (Kostenstelle) – wartet auf Bearbeitung Einkauf", "Erstellt: 10.05.2027"),
    "",
    "Allgemeine Daten",
    kv([("Angefordert für", "Annegret Pohlmann-Diallo, Sekretariat FG Stadtplanung (FB 06)"),
        ("Lieferadresse", "Gebäude Nordflügel, Raum 2108, Ostring 14, 35293 Wernstadt"),
        ("Kontierung", "Kostenstelle 06 1840, Sachkonto 0815210 (Geringwertige Wirtschaftsgüter)"),
        ("Genehmiger", "Prof. Dr. Henrike Sommerfeld-Ajayi (Kostenstellenverantwortliche), 10.05.2027")]),
    "",
    "Positionen",
    "  Pos  Typ             Beschreibung                                   Menge   Preis/ME      Wert netto",
    "  10   Freitext        Bürodrehstuhl ErgoLine 300, Synchronmechanik,      6   248,00 EUR  1.488,00 EUR",
    "                       Lordosenstütze, Armlehnen 4D, Bezug anthrazit",
    "                       Warengruppe 3912 Büromöbel/Sitzmöbel",
    "                       Bevorzugter Lieferant: Sitzkontor Brennecke GmbH, Bielefeld",
    "                       Angebot SB-27-1904 vom 06.05.2027",
    "",
    "  Gesamtwert netto                                                                        1.488,00 EUR",
    "  Steuer 19 %                                                                               282,72 EUR",
    "  Gesamtwert brutto                                                                       1.770,72 EUR",
    "",
    "Notiz an den Einkauf",
    "  Drei Vergleichsangebote eingeholt (Sitzkontor Brennecke 1.488,00 EUR, Büroeinrichtung Lahnau",
    "  1.590,00 EUR, Officeplus Versand 1.632,00 EUR, jeweils netto); günstigster Bieter gewählt.",
    "  Kein Katalogartikel gefunden, daher Freitextposition.",
    "",
    "Genehmigungsverlauf",
    "  10.05.2027 14:02  Einkaufswagen bestellt          A. Pohlmann-Diallo",
    "  10.05.2027 16:47  Genehmigt (Stufe Kostenstelle)  H. Sommerfeld-Ajayi",
])
b06_o1 = "\n".join([
    lr("Sitzkontor Brennecke GmbH", "Angebot SB-27-1904"),
    lr("Artur-Ladebeck-Weg 18 · 33647 Bielefeld · vertrieb@sitzkontor-brennecke.example", "06.05.2027"),
    "",
    "Universität Wernstadt, FG Stadtplanung, Frau Pohlmann-Diallo, Ostring 14, 35293 Wernstadt",
    "",
    "  Pos  Artikel                                                  Menge   EP netto     GP netto",
    "  1    Bürodrehstuhl ErgoLine 300, Synchronmechanik,               6   248,00 EUR  1.488,00 EUR",
    "       Lordosenstütze, 4D-Armlehnen, Stoff anthrazit",
    "                                                            Summe netto           1.488,00 EUR",
    "                                                            19 % USt.               282,72 EUR",
    "                                                            Summe brutto          1.770,72 EUR",
    "",
    "Lieferung frei Verwendungsstelle, Lieferzeit 3 Wochen. Angebot gültig bis 06.06.2027.",
])
b06_o2 = "\n".join([
    "BÜROEINRICHTUNG LAHNAU OHG · Am Kreuzstein 3 · 35633 Lahnau",
    "",
    lr("Universität Wernstadt – FG Stadtplanung", "Angebotsnummer 27/0512"),
    lr("Ostring 14, 35293 Wernstadt", "Datum 07.05.2027"),
    "",
    "Wir bieten an:",
    "  6 Stück Drehstuhl Modell Comfort Pro, Synchronmechanik, Lordosenstütze, Armlehnen",
    "  höhen- und breitenverstellbar, Bezugsstoff anthrazit, je 265,00 EUR netto = 1.590,00 EUR netto",
    "  zzgl. 19 % MwSt. 302,10 EUR, Gesamt 1.892,10 EUR",
    "",
    "Lieferung und Montage inklusive. Bindefrist 30 Tage.",
])
b06_o3 = "\n".join([
    lr("officeplus-versand.example › Warenkorb › Angebot drucken", "08.05.2027 09:41"),
    "",
    "Angebot aus Warenkorb Nr. W-5530217 (gültig 14 Tage)",
    "Kunde: Universität Wernstadt, Annegret Pohlmann-Diallo",
    "",
    "  Artikel                                         Menge   Stückpreis   Gesamt",
    "  Drehstuhl Ergo Basic Plus, Synchronmechanik,      6     272,00 €     1.632,00 €",
    "  Lordosenstütze, Armlehnen 3D, anthrazit",
    "",
    "  Zwischensumme (netto)                                                1.632,00 €",
    "  MwSt. 19 %                                                             310,08 €",
    "  Gesamtsumme (brutto)                                                 1.942,08 €",
    "  Versand                                                              kostenlos",
])
case(PROC, "beschaffungsantrag-b06", "abgelehnt",
     "Der SRM-Einkaufswagen über sechs Bürodrehstühle (1.488,00 € netto) stützt sich auf drei Vergleichsangebote und "
     "wählt das günstigste. Nach der Uni-Kassel-Seite „Rahmenverträge“ besteht jedoch ein Rahmenvertrag über die "
     "Lieferung von Bürodrehstühlen, die Bestellungen sind über das WPS-System zu buchen; laut Beschaffungsseite muss ein "
     "Produkt, zu dem ein Rahmenvertrag besteht, ausschließlich beim Rahmenvertragspartner bestellt werden. Drei "
     "Angebote freier Händler ersetzen das nicht. Der Antrag wird abgelehnt.",
     [doc("srm-einkaufswagen.pdf", b06_srm, font="Helvetica", producer="SAP SRM 7.0 Smart Forms"),
      doc("angebot-sitzkontor.pdf", b06_o1, font="Helvetica", producer="Microsoft Word 2016"),
      doc("angebot-lahnau.pdf", b06_o2, producer="PDF-XChange 9"),
      doc("angebot-officeplus-warenkorb.pdf", b06_o3, font="Helvetica", producer="Chromium Skia/PDF")],
     "SAP SRM shopping cart for 6 office swivel chairs with 3 offers, cheapest chosen; but swivel chairs are a framework-contract (WPS) product",
     "„Derzeit existieren Rahmenverträge u.a. für … Bürodrehstühle …“ (rahmenvertraege.md) and „Sollte man ein Produkt "
     "bestellen wollen, zu dem ein Rahmenvertrag besteht, muss man dieses Produkt ausschließlich beim "
     "Rahmenvertragspartner bestellen“ (beschaffung.md)",
     "rahmenvertraege.md + beschaffung.md", "SAP SRM cart printout, Word offer, plain offer letter, web-shop basket",
     "yes (looks exemplary: 3 offers, cheapest wins)", "high")

# ---------------------------------------------------------------- b07 ------ #
b07_mail = "\n".join([
    lr("Outlook Web App – tamino.grevenbroich-osei@uni-wernstadt.de", "Drucken"),
    "",
    "AW: Bestellung Drehtisch mit Steuerung, Labor Robotik",
    "Prof. Dr. Ute Kalkbrenner <ute.kalkbrenner@uni-wernstadt.de>",
    "Do 18.11.2027 08:12",
    "An: Tamino Grevenbroich-Osei; beschaffung@uni-wernstadt.de",
    "",
    "    Einverstanden, bitte bei Kestrel bestellen. Kostenstelle wie angegeben.",
    "    Ute Kalkbrenner (Kostenstellenbevollmächtigte FG Robotik)",
    "",
    "Von: Tamino Grevenbroich-Osei",
    "Gesendet: Mi 17.11.2027 16:55",
    "An: beschaffung@uni-wernstadt.de",
    "Cc: Prof. Dr. Ute Kalkbrenner",
    "Betreff: Bestellung Drehtisch mit Steuerung, Labor Robotik",
    "",
    "    Liebes Team der Zentralen Beschaffung,",
    "",
    "    für den Kalibrierstand im Labor Robotik benötigen wir einen motorisierten Präzisionsdrehtisch mit",
    "    Schrittmotorsteuerung. Ich habe drei Angebote eingeholt (alle Beträge netto, Lieferung frei Haus):",
    "",
    "      1. Kestrel Motion Ltd., Cork (IE), Quotation Q-27-0815 vom 09.11.2027      4.180,00 EUR",
    "      2. Feinmechanik Haberkorn GmbH, Jena, Angebot 27-1142 vom 10.11.2027      4.395,00 EUR",
    "      3. Präzisionsantriebe Lohmeyer, Stuttgart, Warenkorb-Angebot vom 12.11.2027  4.612,00 EUR",
    "",
    "    Alle drei erfüllen die Anforderungen (Auflösung 0,001°, Last 20 kg, Hohlwelle 35 mm). Bitte",
    "    bestellen Sie beim günstigsten Anbieter Kestrel Motion. Die Lieferung aus Irland ist eine",
    "    innergemeinschaftliche Lieferung (Reverse Charge). Ein Rahmenvertrag für Positioniertechnik",
    "    besteht nicht.",
    "",
    "    Kostenstelle 16 7730, Auftrag 2160418 (Landesmittel Labor Robotik)",
    "",
    "    Viele Grüße",
    "    Tamino Grevenbroich-Osei",
])
b07_q1 = "\n".join([
    lr("KESTREL MOTION LTD", "QUOTATION"),
    lr("Unit 7, Ringaskiddy Business Park, Cork P43 X392, Ireland", "Quotation no.  Q-27-0815"),
    lr("VAT IE 3384712LH · sales@kestrel-motion.example", "Date           09 Nov 2027"),
    lr("", "Valid until    08 Jan 2028"),
    "",
    "Customer:  Universität Wernstadt, Fachgebiet Robotik, attn. Tamino Grevenbroich-Osei",
    "           Ostring 14, 35293 Wernstadt, Germany · VAT ID DE 113 058 990",
    "",
    "  Item  Description                                           Qty   Unit price      Amount",
    "  1     RS-120 motorised rotation stage, 0.001° resolution,      1   EUR 3,560.00   EUR 3,560.00",
    "        20 kg load, 35 mm clear aperture",
    "  2     SC-2 two-axis stepper motor controller, USB/Ethernet     1   EUR   620.00   EUR   620.00",
    "  3     Delivery DAP Wernstadt                                   1   EUR     0.00   EUR     0.00",
    "",
    "                                                        Subtotal (net)        EUR 4,180.00",
    "                                                        VAT 0 %               EUR     0.00",
    "                                                        Total                 EUR 4,180.00",
    "",
    "Intra-Community supply, VAT reverse charge (Art. 196 Directive 2006/112/EC).",
    "Payment terms: 30 days net. Delivery: 4-5 weeks after order.",
])
b07_q2 = "\n".join([
    "Feinmechanik Haberkorn GmbH · Carl-Zeiss-Platz 9 · 07743 Jena",
    "",
    lr("Universität Wernstadt", "Angebot 27-1142"),
    lr("Fachgebiet Robotik, Herrn Grevenbroich-Osei", "Jena, 10.11.2027"),
    "Ostring 14, 35293 Wernstadt",
    "",
    "  Pos.  Bezeichnung                                              Menge   Preis netto",
    "  1     Präzisionsdrehtisch DT-100M, Schrittmotor, Auflösung       1     3.745,00 EUR",
    "        0,001°, Traglast 25 kg, Hohlwelle 40 mm",
    "  2     Steuerung ST-2, 2 Achsen, USB                              1       650,00 EUR",
    "                                                     Summe netto      4.395,00 EUR",
    "                                                     19 % MwSt.         835,05 EUR",
    "                                                     Summe brutto     5.230,05 EUR",
    "",
    "Lieferung frei Haus, Lieferzeit ca. 6 Wochen. Zahlungsziel 30 Tage.",
])
b07_q3 = "\n".join([
    lr("lohmeyer-antriebe.example – Angebot aus Warenkorb", "12.11.2027, 10:03"),
    "Präzisionsantriebe Lohmeyer e.K. · Heilbronner Straße 140 · 70191 Stuttgart",
    "Kunde: Universität Wernstadt, FG Robotik (Kundennr. 40177)",
    "",
    "  Art.-Nr.     Artikel                                        Menge   Preis netto",
    "  RT-90-ST     Drehtisch RT-90, Schrittmotor, 0,001°, 20 kg      1     3.890,00 €",
    "  CTRL-2X      Controller 2-Achs, Ethernet                       1       722,00 €",
    "",
    "  Summe netto                                                        4.612,00 €",
    "  MwSt. 19 %                                                           876,28 €",
    "  Gesamt brutto                                                      5.488,28 €",
    "  Versand                                                            frei",
])
case(PROC, "beschaffungsantrag-b07", "angenommen",
     "Für den motorisierten Drehtisch mit Steuerung liegen drei schriftliche Angebote vor (4.180,00 €, 4.395,00 € und "
     "4.612,00 € netto), wie es die Beschaffungsseite der Universität Kassel ab 1.000 Euro verlangt. Gewählt ist das "
     "günstigste Angebot der Kestrel Motion Ltd. (Irland, innergemeinschaftliche Lieferung mit Reverse Charge, Lieferung "
     "frei Haus); die Beträge in der E-Mail stimmen mit den Angeboten überein. Für Positioniertechnik besteht kein "
     "Rahmenvertrag, und die Kostenstellenbevollmächtigte hat die Bestellung im Verlauf schriftlich beauftragt. Der "
     "Antrag wird angenommen.",
     [doc("email-bestellung.pdf", b07_mail, producer="Microsoft Outlook Web App"),
      doc("quotation-kestrel-motion.pdf", b07_q1, font="Helvetica", producer="Xero Invoicing"),
      doc("angebot-haberkorn.pdf", b07_q2, producer="Microsoft Word 2019"),
      doc("angebot-lohmeyer-warenkorb.pdf", b07_q3, font="Helvetica", producer="Chromium Skia/PDF")],
     "E-mail order with 3 offers incl. an English Irish quotation (net, reverse charge); cheapest chosen, cost-centre holder approves in the thread",
     "„Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“ and „Bestellungen müssen "
     "vom Kostenstellenbevollmächtigten (meist Fachgebietsleitung) beauftragt werden.“",
     "beschaffung.md", "OWA mail thread, English supplier quotation (accounting-tool layout), Word offer, web-shop basket",
     "no (format test: English quote, net vs gross across offers)", "high")

# ---------------------------------------------------------------- b08 ------ #
b08_mail = "\n".join([
    "Von:      Dr. Carolin Westerhoff-Bamba <carolin.westerhoff-bamba@uni-wernstadt.de>",
    "An:       beschaffung@uni-wernstadt.de",
    "Cc:       Prof. Dr. Raimund Esch-Okonkwo <raimund.esch-okonkwo@uni-wernstadt.de>",
    "Datum:    Mo 14.06.2027 09:37",
    "Betreff:  Laborglas Praktikum Analytische Chemie – zwei Bestellanforderungen",
    "Anlage:   vorgang-laborglas.pdf (3 Seiten)",
    "",
    "Liebes Beschaffungsteam,",
    "",
    "anbei zwei Bestellanforderungen für Becherglas-Sets für das Praktikum Analytische Chemie, je 20 Sets",
    "für die beiden Praktikumsgruppen. Beide liegen unter 1.000 EUR netto, daher als Direktauftrag beim",
    "Anbieter des Angebots A-27-3310. Prof. Esch-Okonkwo hat beide Anforderungen unterschrieben.",
    "",
    "Viele Grüße",
    "Carolin Westerhoff-Bamba",
    "Fachgebiet Analytische Chemie, FB 18",
])
b08_offer = "\n".join([
    lr("Laborglas Tessendorf KG", "ANGEBOT A-27-3310"),
    lr("Glashüttenweg 4 · 98693 Ilmenau · Tel. 03677 46 20 11", "Datum: 08.06.2027"),
    lr("", "gültig bis: 08.08.2027"),
    "",
    "Universität Wernstadt, FB 18, Fachgebiet Analytische Chemie",
    "z. Hd. Dr. Carolin Westerhoff-Bamba, Ostring 14, 35293 Wernstadt",
    "",
    "  Pos  Bezeichnung                                             Menge   EP netto    GP netto",
    "  1    Becherglas-Set Borosilikat 3.3, niedrige Form,            40    47,00 EUR  1.880,00 EUR",
    "       5-teilig (50/100/250/400/600 ml)",
    "",
    "                                                       Summe netto          1.880,00 EUR",
    "                                                       zzgl. 19 % USt.        357,20 EUR",
    "                                                       Angebotssumme brutto 2.237,20 EUR",
    "",
    "Teillieferungen möglich. Versandkostenfrei ab 250 EUR netto.",
    "",
    "Seite 1 von 3",
])


def banf(n, nr):
    return "\n".join([
        lr("Universität Wernstadt · Bestellanforderung (BANF)", f"BANF-Nr. 18-2027-{nr}"),
        lr("Zentrale Beschaffung", "Datum: 14.06.2027"),
        "",
        "Anfordernde Stelle       FB 18, Fachgebiet Analytische Chemie (Praktikum)",
        "Ansprechpartnerin        Dr. Carolin Westerhoff-Bamba, Tel. 0561 7390-6131",
        "Kostenstelle             18 4410 (Lehrmittel Praktikum)",
        f"Zweck                    Laborglas Praktikum Analytische Chemie, Gruppe {n}",
        "",
        "Lieferant                Laborglas Tessendorf KG, Ilmenau",
        "Grundlage                Angebot A-27-3310 vom 08.06.2027" + (", Pos. 1, Teilmenge" if n == "A" else ", Pos. 1, Restmenge"),
        "Vergabeart               Direktauftrag (Auftragswert unter 1.000 EUR netto)",
        "Vergleichsangebote       entfällt",
        "Rahmenvertragsprodukt    nein",
        "",
        "  Pos  Bezeichnung                                     Menge   EP netto    GP netto",
        "  1    Becherglas-Set Borosilikat 3.3, 5-teilig          20    47,00 EUR   940,00 EUR",
        "",
        "  Summe netto 940,00 EUR · USt. 19 % 178,60 EUR · Summe brutto 1.118,60 EUR",
        "",
        "Kategorie                [X] Verbrauchsmaterial  [ ] GWG  [ ] Anlage",
        "",
        "Beauftragt (Kostenstellenbevollmächtigter):  14.06.2027  gez. Prof. Dr. Raimund Esch-Okonkwo",
        "",
        f"Seite {2 if n == 'A' else 3} von 3",
    ])


case(PROC, "beschaffungsantrag-b08", "abgelehnt",
     "Die zwei Bestellanforderungen vom 14.06.2027 über je 940,00 € netto beziehen sich auf dasselbe Angebot "
     "A-27-3310 der Laborglas Tessendorf KG über 40 Becherglas-Sets zu zusammen 1.880,00 € netto: gleicher Tag, "
     "gleiche Kostenstelle, gleicher Lieferant, Teil- und Restmenge derselben Position. Der Auftragswert beträgt damit "
     "1.880,00 € netto. Die Pflicht zu drei Vergleichsangeboten entfällt nur, wenn der Auftragswert unter 1.000 Euro "
     "liegt (Uni-Kassel-Seite „Nachhaltiges Catering“ mit Verweis auf die Beschaffungsordnung); grundsätzlich sind drei "
     "Angebote einzuholen (Beschaffungsseite). Die Aufteilung in zwei Anforderungen umgeht diese Grenze, "
     "Vergleichsangebote fehlen. Der Antrag wird abgelehnt.",
     [doc("email-anschreiben.pdf", b08_mail, producer="Microsoft: Print To PDF"),
      doc("vorgang-laborglas.pdf", "\f".join([b08_offer, banf("A", "0611"), banf("B", "0612")]),
          producer="Canon iR-ADV C5840 PDF", creator="Scan to File")],
     "One 3-page PDF (offer + 2 BANF forms): an offer of 1,880 EUR net split into two 940 EUR direct awards on the same day",
     "„Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ "
     "(nachhaltiges-catering.md) with „Grundsätzlich müssen 3 Angebote eingeholt werden“ (beschaffung.md)",
     "nachhaltiges-catering.md + beschaffung.md", "multi-page scanned bundle with BANF form in another field order, Outlook mail",
     "yes (each request alone is under 1,000 EUR)", "high")

# ---------------------------------------------------------------- b09 ------ #
b09_bm = "\n".join([
    "UNIVERSITÄT WERNSTADT – BEDARFSMELDUNG                                  Nr. BM-71-2027-044",
    "",
    "Lieferant ........................ Labortechnik Wallenhorst GmbH, Hafenweg 22, 48155 Münster",
    "Grundlage ........................ Webshop-Angebot WA-2027-77812 vom 02.08.2027",
    "Artikel .......................... Tisch-Messgerät pH/Leitfähigkeit LM-540 mit Kombielektrode,",
    "                                   Leitfähigkeitszelle und Kalibrierset",
    "Menge ............................ 1",
    "Betrag netto ..................... 935,00 EUR",
    "Betrag brutto (19 % USt.) ........ 1.112,65 EUR",
    "Vergabeart ....................... Direktauftrag, Auftragswert unter 1.000 EUR netto",
    "Vergleichsangebote ............... entfällt (Direktauftrag)",
    "Rahmenvertragsprodukt ............ nein",
    "Kategorie ........................ Anlage (selbstständig nutzbares Gerät, Nettoeinzelpreis über 800 EUR)",
    "Verwendungszweck ................. Ersatz des defekten pH-Meters im Wasserlabor (Lehre und Forschung)",
    "Kostenstelle / Auftrag ........... 71 3305 / Auftrag 2130077",
    "Bedarfsstelle .................... FB 71, Fachgebiet Umweltverfahrenstechnik, Wasserlabor",
    "Angefordert von .................. Sören Lüdtke-Asante (Laboringenieur), 03.08.2027",
    "",
    "Beauftragt durch Kostenstellenbevollmächtigte:n",
    "Wernstadt, 03.08.2027   gez. Prof. Dr. Margarete Höfling-Nwachukwu",
    "",
    "Eingang Zentrale Beschaffung: 04.08.2027",
])
b09_shop = "\n".join([
    lr("labortechnik-wallenhorst.example", "Angebot WA-2027-77812"),
    lr("Ihr Warenkorb als verbindliches Angebot", "02.08.2027 15:20"),
    "",
    "Kunde: Universität Wernstadt, FB 71, Wasserlabor · Kundennummer 300811",
    "",
    "  Tisch-Messgerät pH/Leitfähigkeit LM-540",
    "  inkl. Kombielektrode pH, Leitfähigkeitszelle K=1, Kalibrierset, Stativ",
    "  Art.-Nr. LM540-SET                                   Menge: 1",
    "",
    "  Preis                                                  1.112,65 €",
    "                                                  inkl. 19 % MwSt.",
    "                                         (935,00 € zzgl. 177,65 € MwSt.)",
    "  Versand                                                 kostenlos",
    "  ------------------------------------------------------------------",
    "  Gesamtsumme                                            1.112,65 €",
    "",
    "Angebot gültig 30 Tage. Lieferung innerhalb von 5 Werktagen. Zahlung auf Rechnung für Hochschulen.",
    "Labortechnik Wallenhorst GmbH · Hafenweg 22 · 48155 Münster · USt-IdNr. DE 291 774 503",
])
case(PROC, "beschaffungsantrag-b09", "angenommen",
     "Das Tisch-Messgerät kostet laut Webshop-Angebot 935,00 € netto (1.112,65 € brutto) und wird ohne "
     "Vergleichsangebote als Direktauftrag angefordert. Nach der Uni-Kassel-Seite „Nachhaltiges Catering“ (Verweis auf "
     "die Beschaffungsordnung) entfällt die Pflicht zu drei Vergleichsangeboten, wenn der Auftragswert unter 1.000 Euro "
     "liegt; maßgeblich ist wie bei den Freigabegrenzen der Finanzabteilung („30.000 Euro/netto“) der Nettowert. "
     "Messgeräte sind kein Rahmenvertragsprodukt, das Gerät ist richtig als Anlage eingeordnet (Nettoeinzelpreis über "
     "800,00 €), und die Kostenstellenbevollmächtigte hat beauftragt. Der Antrag wird angenommen.",
     [doc("bedarfsmeldung.pdf", b09_bm, producer="LibreOffice 7.4", creator="Writer"),
      doc("webshop-angebot.pdf", b09_shop, font="Helvetica", producer="Chromium Skia/PDF")],
     "Single-offer direct award for a lab meter: 935 EUR net but 1,112.65 EUR gross (the shop shows gross first)",
     "„Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ "
     "(nachhaltiges-catering.md); net basis: „Freigabe von Bestellungen bis 30.000 Euro/netto“ (finanzen-geschaeftsverteilung.md)",
     "nachhaltiges-catering.md (+ finanzen-geschaeftsverteilung.md)", "dotted-leader 'Bedarfsmeldung' form, gross-first web-shop offer",
     "yes (looks wrong: gross above 1,000 EUR)", "low (the corpus never says net explicitly for the 1,000 EUR rule)")

# ---------------------------------------------------------------- b10 ------ #
b10_mail = "\n".join([
    lr("Roundcube Webmail – einkauf@th-sallstedt.de", "https://webmail.th-sallstedt.de/?_task=mail"),
    "",
    "Bestellung Absauganlagen Lötarbeitsplätze, Labor Fertigungstechnik",
    "Dr. Wiebke Asamoah-Kröger <wiebke.asamoah-kroeger@th-sallstedt.de>",
    "Di 07.09.2027 13:18",
    "An: einkauf@th-sallstedt.de",
    "Cc: Prof. Dr. Hartmut Feddersen-Lowe <hartmut.feddersen-lowe@th-sallstedt.de>",
    "",
    "  Sehr geehrte Damen und Herren,",
    "",
    "  für die neuen Lötarbeitsplätze im Labor Fertigungstechnik benötigen wir zwei mobile",
    "  Absauganlagen. Anbei drei Angebote und der Preisspiegel. Wir bitten um Bestellung bei der",
    "  Absaugwerk Krautheim KG (Angebot AK-5521, 3.348,00 EUR netto). Kostenstelle 5230.",
    "  Prof. Feddersen-Lowe (Laborleitung, Budgetverantwortung) ist in Kopie und einverstanden.",
    "",
    "  Mit freundlichen Grüßen",
    "  Wiebke Asamoah-Kröger",
    "  Labor Fertigungstechnik, Fakultät Maschinenbau, Technische Hochschule Sallstedt",
])


def b10_offer(firm, addr, nr, date, model, unit):
    tot = 2 * unit
    return "\n".join([
        lr(firm, f"Angebot {nr}"),
        lr(addr, f"Datum: {date}"),
        "",
        "Technische Hochschule Sallstedt, Labor Fertigungstechnik",
        "z. Hd. Dr. Wiebke Asamoah-Kröger, Hochschulring 3, 29541 Sallstedt",
        "",
        "  Pos  Bezeichnung                                              Menge   EP netto       GP netto",
        f"  1    {model:<55}     2   {money(unit):>9} EUR  {money(tot):>9} EUR",
        "       Filterstufen F7 + H13 + Aktivkohle, 2 Absaugarme",
        "",
        f"                                                   Summe netto        {money(tot):>9} EUR",
        f"                                                   zzgl. 19 % USt.    {money(round(tot * 0.19, 2)):>9} EUR",
        f"                                                   Summe brutto       {money(round(tot * 1.19, 2)):>9} EUR",
        "",
        "Lieferung frei Haus, Lieferzeit 3-4 Wochen. Angebot freibleibend, gültig 60 Tage.",
    ])


b10_ps = "\n".join([
    "Preisspiegel_Absaugung_Labor_FT.xlsx – Tabelle1 (Druck 07.09.2027)",
    "",
    "Vorhaben;Mobile Absauganlage Lötrauch, 2 Stück",
    "Zuschlagskriterium;niedrigster Preis (netto) bei technischer Gleichwertigkeit",
    "",
    "Bieter;Angebot;Datum;netto EUR;brutto EUR;Leistungsverzeichnis erfüllt;Rang Preis",
    "Filtertechnik Rambach GmbH;FR-27-0419;30.08.2027;3.120,00;3.712,80;ja;1",
    "Absaugwerk Krautheim KG;AK-5521;01.09.2027;3.348,00;3.984,12;ja;2",
    "Luftrein Systeme Oberhilbersheim;LS-2027-188;02.09.2027;3.505,00;4.170,95;ja;3",
    "",
    "Zuschlag;Absaugwerk Krautheim KG",
    "Begründung;bewährter Lieferant, gute Erfahrungen bei früheren Lieferungen",
    "Erstellt;W. Asamoah-Kröger",
])
case(PROC, "beschaffungsantrag-b10", "abgelehnt",
     "Der Fall gehört zur TH Sallstedt und wird nach den Unterlagen entschieden. Der Preisspiegel nennt als "
     "Zuschlagskriterium den niedrigsten Nettopreis bei technischer Gleichwertigkeit und bestätigt für alle drei "
     "Angebote, dass das Leistungsverzeichnis erfüllt ist. Günstigstes Angebot ist das der Filtertechnik Rambach GmbH "
     "mit 3.120,00 € netto; der Zuschlag geht dennoch an die Absaugwerk Krautheim KG mit 3.348,00 € netto, begründet nur "
     "mit „bewährter Lieferant“. Die Lieferantenwahl widerspricht dem eigenen Wertungskriterium (228,00 € netto "
     "Mehrpreis); wie im Übungsfall 07 beruht die Lieferantenwahl nicht auf der dokumentierten Wertung. Der Antrag wird "
     "abgelehnt.",
     [doc("email-einkauf.pdf", b10_mail, producer="Roundcube Webmail 1.6 / Firefox"),
      doc("angebot-rambach.pdf", b10_offer("Filtertechnik Rambach GmbH", "Gewerbering 12 · 36179 Bebra",
                                           "FR-27-0419", "30.08.2027",
                                           "Mobile Absauganlage LA-200, 230 V, 200 m³/h,", 1560.00),
          font="Helvetica", producer="Microsoft Word 2016"),
      doc("angebot-krautheim.pdf", b10_offer("Absaugwerk Krautheim KG", "Industriestraße 40 · 74238 Krautheim",
                                             "AK-5521", "01.09.2027",
                                             "Lötrauchabsaugung KRA-Mobil 2, 230 V, 210 m³/h,", 1674.00),
          producer="sevDesk"),
      doc("angebot-luftrein.pdf", b10_offer("Luftrein Systeme Oberhilbersheim", "Mühlweg 3 · 55437 Oberhilbersheim",
                                            "LS-2027-188", "02.09.2027",
                                            "Absauggerät AirSol 220, 230 V, 220 m³/h,", 1752.50),
          font="Helvetica", producer="lexoffice"),
      doc("preisspiegel.pdf", b10_ps, producer="Microsoft Excel 2019")],
     "TH Sallstedt webmail order; the spreadsheet price comparison names 'lowest net price' as criterion but awards the 2nd-cheapest ('proven supplier')",
     "Organisers' GT beschaffungsantrag-07: „die Wertung des Vermerks und die Lieferantenwahl … beruhen damit auf einem "
     "falschen Wert“; GT 08: „Das gewählte Angebot ist das günstigste.“; the case's own sheet: „Zuschlagskriterium;niedrigster Preis (netto)“",
     "procurement ground-truth.jsonl (07, 08) + the case's own price sheet", "Roundcube webmail, CSV-like Excel printout, offers from 3 invoicing tools",
     "no (but needs reading the sheet against the award)", "high")

# ---------------------------------------------------------------- b11 ------ #
b11_bon = "\n".join([
    "  FRISCHMARKT HULSKAMP",
    "  Breite Strasse 41",
    "  35287 Wernstadt",
    "  Tel. 0561 4419 220",
    "",
    "KAFFEE GEMAHL. 5OOG        6,99 B",
    "TEE AUSWAHLBOX 3OST        3,49 B",
    "BUTTERKEKSE 2OOG",
    "  2 x 1,29                 2,58 B",
    "AEPFEL ELSTAR 1KG          2,79 B",
    "H-MILCH 1,5% 1L            1,19 B",
    "WUERFELZUCKER 5OOG         1,39 B",
    "--------------------------------",
    "SUMME EUR                 18,43",
    "================================",
    "EC-KARTE                  18,43",
    "",
    "MWST   NETTO   MWST   BRUTTO",
    "B 7%   17,22   1,21   18,43",
    "",
    "22.09.27 17:48  BON 0812 K02",
    "St.-Nr. 026 7I4 30981",
    "TSE-SIG: a8F3..91c",
    "  VIELEN DANK  BIS BALD",
    "",
    "[handschriftlich:]",
    "Kaffee/Tee/Kekse/Obst fur",
    "Gaste Projektbeirat AQUA-NET",
    "am 23.09.27 - R. Lindqvist-Brede",
])
b11_form = "\n".join([
    "Scan 27.09.2027 10:31 · Seite 1/1",
    "",
    "Universität Wernstadt – Abteilung Finanzen – Finanzbuchhaltung",
    "ERSTATTUNG PRIVAT VERAUSLAGTER KOSTEN (Papierweg)",
    "",
    "Antragsteller/in:     Dr. Ronja Lindqvist-Brede",
    "Einrichtung:          FB 14, Fachgebiet Siedlungswasserwirtschaft",
    "Kostenstelle/Auftrag: 14 6610 / Projekt AQUA-NET, Auftrag 6240311",
    "",
    "Nr.  Datum      Beleg / Lieferant              Zweck                                 Betrag",
    "1    22.09.2027 Kassenbon Frischmarkt Hulskamp Kaffee, Tee, Gebäck, Obst für die     18,43 EUR",
    "                                               Gäste der Projektbeiratssitzung",
    "                                               am 23.09.2027 (Einladung anbei)",
    "                                                                      Summe         18,43 EUR",
    "",
    "Originalbeleg aufgeklebt: [x]          Zahlung privat (EC-Karte): [x]",
    "",
    "Wernstadt, 27.09.2027    gez. R. Lindqvist-Brede",
    "Sachlich richtig:        gez. Prof. Dr. Jens Tamm-Achterberg (Kostenstellenverantwortlicher)",
])
b11_inv = "\n".join([
    "Von:      Dr. Ronja Lindqvist-Brede <ronja.lindqvist-brede@uni-wernstadt.de>",
    "An:       Projektbeirat AQUA-NET (Verteiler)",
    "Datum:    Mo 06.09.2027 14:05",
    "Betreff:  Einladung 3. Sitzung Projektbeirat AQUA-NET, 23.09.2027",
    "",
    "Sehr geehrte Mitglieder des Projektbeirats,",
    "",
    "zur 3. Sitzung des Projektbeirats lade ich Sie herzlich ein:",
    "Donnerstag, 23.09.2027, 10:00 bis 13:00 Uhr, Ostring 14, Raum 1203.",
    "",
    "Tagesordnung: 1. Stand der Messkampagne  2. Ergebnisse Pilotanlage  3. Planung 2028",
    "",
    "Teilnehmende:",
    "  extern:  Dipl.-Ing. Holger Brackmann (Stadtentwässerung Wernstadt)",
    "           Dr. Paula Szymanski-Ott (Wasserverband Mittlere Fulde)",
    "           Thilo Ramadani (Ingenieurgesellschaft Ramadani & Wichert)",
    "           Dr. Ines Kortüm (Landesamt für Umwelt, Referat Abwasser)",
    "  intern:  Prof. Dr. Jens Tamm-Achterberg, Dr. Ronja Lindqvist-Brede, Malik Oduya (FG SWW)",
    "",
    "Für Kaffee und Tee ist gesorgt.",
    "",
    "Mit freundlichen Grüßen",
    "Ronja Lindqvist-Brede",
])
case(EXP, "auslagenerstattung-b11", "angenommen",
     "Der Kassenbon vom 22.09.2027 über 18,43 € umfasst Kaffee, Tee, Kekse, Äpfel, Milch und Zucker. Laut "
     "handschriftlichem Vermerk, Erstattungsformular und Einladung wurden sie den Gästen der Projektbeiratssitzung am "
     "23.09.2027 angeboten; vier der sieben Teilnehmenden sind extern. Nach der Bewirtungskostenrichtlinie auf der "
     "Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ sind die üblichen Gesten der Höflichkeit (Mineralwasser, "
     "Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden, keine Bewirtungskosten, sondern "
     "laufende Betriebsaufwendungen. Es handelt sich um eine kleine, kurzfristige Anschaffung, der Originalbeleg mit "
     "Stichwort ist aufgeklebt und sachlich richtig gezeichnet. Die Erstattung ist zu gewähren.",
     [doc("kassenbon-scan.pdf", b11_bon, size=RECEIPT, margin=12.0, jitter=1.2,
          producer="Epson DS-410 Scan", creator="Document Capture Pro"),
      doc("erstattungsformular-scan.pdf", b11_form, jitter=1.4, producer="Kyocera TASKalfa 3554ci",
          creator="Scan to PDF"),
      doc("email-einladung-projektbeirat.pdf", b11_inv, producer="Microsoft: Print To PDF")],
     "OCR-noisy till receipt (coffee, tea, biscuits, fruit) for an advisory-board meeting with 4 of 7 external guests",
     "„Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen und damit auch aus Landesmitteln finanzierbar sind "
     "die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität "
     "angeboten werden.“",
     "finanzbuchhaltung-und-steuern.md (cf. GT auslagenerstattung-07)", "thermal till receipt with OCR errors (narrow page), scanned paper refund form, mail",
     "yes (looks like the rejected tea-kitchen practice case 07)", "low (the corpus does not say outright that a private advance is the right route)")

# ---------------------------------------------------------------- b12 ------ #
b12_bon = "\n".join([
    "  GASTHAUS ZUR ALTEN FAEHRE",
    "  Fuldaufer 7",
    "  35291 Wernstadt",
    "  St.-Nr. 026 812 44190",
    "",
    "RECHNUNG Nr. 2027-18842",
    "Tisch 12   Gaeste 6   Bed. 04",
    "16.09.2027  13:41",
    "--------------------------------",
    "2 Rinderroulade      37,80  A",
    "2 Zanderfilet        43,00  A",
    "2 Gemuesestrudel     31,80  A",
    "4 Apfelschorle 0,4   15,60  B",
    "2 Pils 0,3            7,20  B",
    "3 Espresso            7,20  B",
    "--------------------------------",
    "SUMME EUR           142,60",
    "Kreditkarte         142,60",
    "",
    "A 7%  Netto 105,23  MwSt 7,37",
    "B 19% Netto  25,21  MwSt 4,79",
    "",
    "Rechnungsempfaenger:",
    "Universitaet Wernstadt",
    "FG Siedlungswasserwirtschaft",
    "Ostring 14, 35293 Wernstadt",
    "",
    "Kasse 1  Reg.-Nr. 77-0193-2045",
    "TSE-Transaktion 554210",
    "  Vielen Dank fuer Ihren Besuch",
])
b12_back = "\n".join([
    "Angaben zum Nachweis der Höhe und der betrieblichen Veranlassung von Bewirtungsaufwendungen",
    "",
    "Tag der Bewirtung:     16.09.2027",
    "Ort der Bewirtung:     Gasthaus Zur Alten Fähre, Fuldaufer 7, 35291 Wernstadt",
    "Anlass:                Arbeitstreffen Arbeitspaket 3 des Projekts AQUA-NET:",
    "                       Abstimmung der Messkampagne Herbst 2027 mit dem Ingenieurbüro",
    "Bewirtete Personen:    siehe Teilnehmerliste (6 Personen)",
    "Höhe der Aufwendungen: 142,60 EUR (ohne Trinkgeld)",
    "Finanzierung:          Drittmittel, Projekt AQUA-NET, Auftrag 6240311",
    "                       (Bewirtung laut Zuwendungsbescheid zulässig)",
    "Bewirtende Person:     Dr. Henning Abara-Solms",
    "",
    "Wernstadt, 17.09.2027      gez. H. Abara-Solms",
])
b12_list = "\n".join([
    "Teilnehmerliste Bewirtung 16.09.2027 – Arbeitstreffen AP 3 AQUA-NET",
    "",
    "  Nr.  Name                          Einrichtung                                   G = Gast / U = Uni",
    "  1    Dr. Henning Abara-Solms       Universität Wernstadt, FG SWW                 U",
    "  2    Prof. Dr. Jens Tamm-Achterberg Universität Wernstadt, FG SWW                U",
    "  3    Malik Oduya                   Universität Wernstadt, FG SWW                 U",
    "  4    Leonie Faßbender              Universität Wernstadt, FG SWW                 U",
    "  5    Dr. Arvid Petersen-Klee       Universität Wernstadt, FG Hydrologie          U",
    "  6    Thilo Ramadani                Ingenieurgesellschaft Ramadani & Wichert      G",
    "",
    "  Gäste: 1     Universitätsbedienstete: 5     Summe: 6     je Person: 23,77 EUR",
    "",
    "Zahlung privat per Kreditkarte durch Dr. Henning Abara-Solms; um Erstattung wird gebeten.",
])
case(EXP, "auslagenerstattung-b12", "abgelehnt",
     "Der Bewirtungsbeleg des Gasthauses Zur Alten Fähre vom 16.09.2027 über 142,60 € ist formal vollständig "
     "(maschinell erstellt, Registriernummer, Steuernummer, Universität als Rechnungsempfänger, unterschriebene "
     "Bewirtungsangaben, Teilnehmerliste, 23,77 € je Person). Bewirtet wurden aber sechs Personen, davon fünf "
     "Bedienstete der Universität und ein Gast; Anlass ist ein Arbeitstreffen des Projekts. Nach der "
     "Bewirtungskostenrichtlinie auf der Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ sind Arbeitsessen, d. h. aus "
     "dienstlichem Interesse mit überwiegend Universitätsangehörigen, nicht erstattungsfähig, und Bewirtungskosten "
     "werden nur bei einem angemessenen Verhältnis von externen und internen Teilnehmern erstattet. Die Erstattung ist "
     "abzulehnen.",
     [doc("bewirtungsbeleg.pdf", b12_bon + "\f" + b12_back, size=RECEIPT, margin=12.0,
          producer="Epson DS-410 Scan", creator="Document Capture Pro"),
      doc("teilnehmerliste.pdf", b12_list, producer="Microsoft Word 2019")],
     "Restaurant receipt (POS, 2 pages with hospitality form) for a project working lunch: 5 university staff, 1 guest",
     "Not reimbursable: „Arbeitsessen, d. h. aus dienstlichem Interesse mit überwiegend Universitätsangehörigen“ and "
     "„Bewirtungskosten werden nur erstattet, wenn bei der Veranstaltung ein angemessenes Verhältnis von externen und "
     "internen Teilnehmern gegeben ist.“",
     "finanzbuchhaltung-und-steuern.md", "restaurant POS receipt on a narrow page + reverse-side hospitality form, Word list",
     "yes (meets every formal receipt requirement)", "high")

# ---------------------------------------------------------------- b13 ------ #
b13_arzt = "\n".join([
    "Praxis für Reise- und Tropenmedizin",
    "Dr. med. Gerlinde Ostendorp · Fachärztin für Allgemeinmedizin, Tropenmedizin",
    "Friedrichsplatz 6 · 35291 Wernstadt · Gelbfieberimpfstelle Nr. HE-0418",
    "",
    lr("Herrn", "Rechnung Nr. 2027/3317"),
    lr("Dr. Kofi Lammersdorf-Agyeman", "Rechnungsdatum: 18.10.2027"),
    "Ellenbacher Weg 12",
    "35289 Wernstadt",
    "",
    "Privatliquidation nach der Gebührenordnung für Ärzte (GOÄ)",
    "Behandlungszeitraum: 14.10.2027 · Diagnose: Z24.3 Impfung gegen Gelbfieber; reisemedizinische Beratung",
    "",
    "  Datum       GOÄ-Nr.  Leistung                                     Faktor     Betrag",
    "  14.10.2027  1        Beratung, auch telefonisch                     2,3    10,72 EUR",
    "  14.10.2027  375      Schutzimpfung (i.m., s.c.)                     2,3    10,72 EUR",
    "  14.10.2027  Auslagen Gelbfieberimpfstoff, 1 Dosis (§ 10 GOÄ)               62,40 EUR",
    "",
    "                                                         Rechnungsbetrag    83,84 EUR",
    "",
    "Bezahlt am 14.10.2027 mit EC-Karte. Diese Rechnung ist umsatzsteuerfrei (§ 4 Nr. 14 UStG).",
])
b13_apo = "\n".join([
    "  LÖWEN-APOTHEKE WERNSTADT",
    "  Obere Königsstraße 30",
    "  35291 Wernstadt",
    "",
    "PRIVATREZEPT",
    "ATOVAQUON/PROGUANIL",
    "250/100MG 12 FTBL      58,97",
    "--------------------------------",
    "SUMME EUR              58,97",
    "GIROCARD               58,97",
    "",
    "enth. MwSt 19%          9,42",
    "14.10.2027 16:22  Kasse 2",
    "Beleg-Nr. 40-118327",
    "  Gute Besserung!",
])
b13_form = "\n".join([
    lr("Universität Wernstadt · Digitale Abrechnung privat verauslagter Kosten", "Vorgang PVK-2027-03894"),
    lr("Zusammenfassung (Ausdruck)", "eingereicht 19.10.2027 08:14"),
    "",
    kv([("Antragsteller", "Dr. Kofi Lammersdorf-Agyeman, FB 11 Ökologische Agrarwissenschaften"),
        ("Kostenstelle / Auftrag", "11 2740 / Projekt SOILGHANA, Auftrag 6250102"),
        ("Bezug", "genehmigte Dienstreise nach Accra (Ghana), 08.11.–19.11.2027, Reise 0004471906")], k=24, indent=0),
    "",
    "  Pos  Beleg                         Datum        Zweck                                       Betrag",
    "  1    Arztrechnung Nr. 2027/3317    18.10.2027   Gelbfieberimpfung (Einreisepflicht Ghana)    83,84 €",
    "  2    Apotheke, Beleg 40-118327     14.10.2027   Malariaprophylaxe für die Dienstreise        58,97 €",
    "                                                                          Summe              142,81 €",
    "",
    kv([("Begründung", "Die Impfung ist für die Einreise nach Ghana vorgeschrieben; der Termin beim"),
        ("", "betriebsärztlichen Dienst war erst nach dem Abflug frei, daher privat beim Hausarzt."),
        ("Bestätigung", "sachlich richtig, Prof. Dr. Ilona Brückner-Ofori, 19.10.2027")], k=24, indent=0),
    "",
    "Hinweis: Originalbelege sind ein halbes Jahr aufzubewahren.",
])
case(EXP, "auslagenerstattung-b13", "abgelehnt",
     "Geltend gemacht werden 142,81 € für eine Gelbfieberimpfung (Arztrechnung nach GOÄ, 83,84 €) und "
     "Malariaprophylaxe (Apothekenbeleg, 58,97 €) vor einer genehmigten Dienstreise nach Ghana. Nach der "
     "Uni-Kassel-Seite „Dienstreisemanagement“ werden notwendige Schutzimpfungen und prophylaktische Maßnahmen durch den "
     "betriebsärztlichen Dienst vorgenommen; eine Kostenerstattung für selbstverauslagte Impf- bzw. Arztkosten ist nicht "
     "möglich. Die Erstattung ist abzulehnen.",
     [doc("erstattung-zusammenfassung.pdf", b13_form, font="Helvetica", producer="Universität Wernstadt PVK-Portal"),
      doc("arztrechnung-goae.pdf", b13_arzt, producer="medatixx Praxissoftware"),
      doc("apotheke-quittung.pdf", b13_apo, size=RECEIPT, margin=12.0, jitter=0.8, producer="Epson DS-410 Scan")],
     "Online-form refund of a yellow-fever vaccination (GOÄ doctor's bill) and malaria pills for an approved trip to Ghana",
     "„Eine Kostenerstattung für selbstverauslagte Impf- bzw. Arztkosten ist nicht möglich.“",
     "dienstreisemanagement.md", "online refund-portal printout, GOÄ private doctor's invoice, pharmacy till receipt",
     "yes (well documented, approved trip, plausible reason)", "high")

# ---------------------------------------------------------------- b14 ------ #
b14_p1 = "\n".join([
    lr("Universität Wernstadt · Digitale Abrechnung privat verauslagter Kosten", "Vorgang PVK-2027-03951"),
    lr("Zusammenfassung mit Belegen (3 Seiten)", "eingereicht 08.10.2027 09:02"),
    "",
    kv([("Antragstellerin", "Merle Haugwitz-Onyango, technische Angestellte"),
        ("Einrichtung", "FB 10 Physik, Fachgebiet Optische Messtechnik"),
        ("Kostenstelle / Auftrag", "10 4420 / Landesmittel Fachgebiet"),
        ("Betrag", "46,80 €"),
        ("Zweck", "Ersatz-Netzteil 24 V für das Laborspektrometer BS-400; das Originalnetzteil"),
        ("", "fiel am 04.10.2027 während einer laufenden Messreihe aus. Über SAP war beim"),
        ("", "Hersteller keine Lieferung vor drei Wochen möglich, daher Expressbestellung"),
        ("", "beim irischen Händler mit privater Kreditkarte."),
        ("Belege", "Seite 2: Rechnung INV-BC-270188; Seite 3: Kreditkartenabrechnung"),
        ("Sachlich richtig", "Prof. Dr. Bastian Rehwinkel, 07.10.2027")], k=24, indent=0),
    "",
    "Seite 1 von 3",
])
b14_p2 = "\n".join([
    lr("BRIGHTWELL COMPONENTS LTD", "INVOICE"),
    lr("Unit 3, Mervue Business Park, Galway H91 TK33, Ireland", "Invoice no.   INV-BC-270188"),
    lr("VAT IE 9822417KH · orders@brightwell-components.example", "Invoice date  05 Oct 2027"),
    lr("", "Order no.     BC-W-440921"),
    "",
    "Bill to:   Universität Wernstadt, Fachgebiet Optische Messtechnik",
    "           Ostring 14, 35293 Wernstadt, Germany",
    "Ship to:   Universität Wernstadt, Labor Optische Messtechnik, Raum 0.118",
    "           Ostring 14, 35293 Wernstadt, Germany",
    "",
    "  Description                                              Qty   Unit price     Amount",
    "  24 V DC power supply unit, 60 W, 5.5/2.1 mm barrel,        1   EUR 34.29      EUR 34.29",
    "  compatible with BS-400 bench spectrometer (PSU-24-60)",
    "  Express shipping to Germany (2 working days)               1   EUR  5.04      EUR  5.04",
    "",
    "                                                  Net total             EUR 39.33",
    "                                                  VAT 19 % (DE, OSS)    EUR  7.47",
    "                                                  Total                 EUR 46.80",
    "",
    "Paid in full by Visa ending 4417 on 05 Oct 2027. Thank you for your order.",
    "",
    "Page 2 of 3",
])
b14_p3 = "\n".join([
    "Kreditkartenabrechnung (Auszug) · Visa ****4417 · Inhaberin Merle Haugwitz-Onyango",
    "",
    "  Buchung     Beleg       Händler / Verwendungszweck                    Betrag",
    "  01.10.2027  30.09.2027  Stadtwerke Wernstadt Parkhaus                 -4,50 EUR",
    "  06.10.2027  05.10.2027  BRIGHTWELL COMPONENTS GALWAY IE              -46,80 EUR",
    "  07.10.2027  06.10.2027  Buchhandlung am Markt                        -12,99 EUR",
    "",
    "Abrechnung vom 15.10.2027, Lastschrift vom Referenzkonto am 20.10.2027.",
    "",
    "Seite 3 von 3",
])
case(EXP, "auslagenerstattung-b14", "angenommen",
     "Die englischsprachige Rechnung der Brightwell Components Ltd. (Galway) vom 05.10.2027 über 46,80 € für ein "
     "Ersatz-Netzteil des Laborspektrometers ist an die Universität Wernstadt, Fachgebiet Optische Messtechnik, gerichtet "
     "und an das Labor geliefert; die Beträge gehen auf (39,33 € netto + 19 % USt = 46,80 €), die Kreditkartenabrechnung "
     "zeigt dieselbe Zahlung. Nach dem Abschnitt Kostenerstattung der Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ "
     "dürfen kleinere, zeitlich dringende Anschaffungen privat verauslagt und erstattet werden; die Dringlichkeit "
     "(Ausfall während einer laufenden Messreihe, keine schnelle Lieferung über SAP) ist begründet und sachlich richtig "
     "gezeichnet. Die Erstattung ist zu gewähren.",
     [doc("erstattung-netzteil.pdf", "\f".join([b14_p1, b14_p2, b14_p3]), font="Helvetica",
          producer="Universität Wernstadt PVK-Portal")],
     "One 3-page PDF (online refund summary + English Irish invoice + card statement) for an urgent lab power supply, billed to the university",
     "„In Ausnahmefällen kann es sein, dass Angestellte der Universität kleinere, zeitlich dringende Anschaffungen selbst "
     "besorgt haben und diese Auslagen zurück erstattet haben möchten.“",
     "finanzbuchhaltung-und-steuern.md (cf. GT auslagenerstattung-01)", "online refund portal bundle, English supplier invoice, card statement",
     "no (format test: multi-document PDF, English invoice)", "high")

# ---------------------------------------------------------------- b15 ------ #
b15_rec = "\n".join([
    lr("LAKESHORE CONFERENCES LLC", "RECEIPT"),
    lr("2200 University Ave, Suite 410, Madison, WI 53726, USA", "Receipt no.  LSC-ODS27-04471"),
    lr("billing@lakeshore-conferences.example", "Date         2027-10-12"),
    "",
    "Event:     Open Data Science Summit 2027 (online only), 3-5 November 2027",
    "Billed to: Dr. Friederike Nwosu-Lambrecht, Universität Wernstadt, FB 07, Fachgebiet Statistik",
    "",
    "  Group registration                                          Qty    Price        Amount",
    "  Online pass (academic) – Dr. Friederike Nwosu-Lambrecht       1    USD 140.00   USD 140.00",
    "  Online pass (academic) – Pavel Tenbrink-Okafor                1    USD 140.00   USD 140.00",
    "  Online pass (academic) – Mirja Sundqvist                      1    USD 140.00   USD 140.00",
    "",
    "                                                   Total paid             USD 420.00",
    "",
    "Paid by credit card (Mastercard ending 2093) on 2027-10-12. No sales tax: electronically supplied",
    "services to a customer outside the USA. Access links are e-mailed to each attendee.",
])
b15_cc = "\n".join([
    lr("Hainbuchen Bank AG · Kreditkartenabrechnung", "Abrechnung vom 31.10.2027"),
    "Mastercard ****2093 · Karteninhaberin Dr. Friederike Nwosu-Lambrecht",
    "",
    "  Buchung     Händler / Verwendungszweck                                   Betrag",
    "  13.10.2027  LAKESHORE CONFERENCES MADISON US                          -385,14 EUR",
    "              USD 420,00 Kurs 1,0905",
    "  13.10.2027  Auslandseinsatzentgelt 1,75 % von 385,14 EUR                 -6,74 EUR",
    "  21.10.2027  Tankstelle Ostring, Wernstadt                               -58,30 EUR",
    "",
    "Der Saldo wird am 05.11.2027 vom Referenzkonto eingezogen.",
])
b15_form = "\n".join([
    lr("Universität Wernstadt · Digitale Abrechnung privat verauslagter Kosten", "Vorgang PVK-2027-04120"),
    lr("Zusammenfassung (Ausdruck)", "eingereicht 02.11.2027 15:47"),
    "",
    kv([("Antragstellerin", "Dr. Friederike Nwosu-Lambrecht, FB 07, Fachgebiet Statistik"),
        ("Kostenstelle / Auftrag", "07 3150 / Landesmittel Fachgebiet"),
        ("Art der Kosten", "Teilnahmegebühr Online-Konferenz (keine Dienstreise)"),
        ("Zweck", "Teilnahme an der Online-Konferenz Open Data Science Summit 2027 für mich und"),
        ("", "die Doktorandin und den Doktoranden des Fachgebiets (Gruppenanmeldung)"),
        ("Erstattungsbetrag", "391,88 € (385,14 € Teilnahmegebühren + 6,74 € Auslandseinsatzentgelt)"),
        ("Auszahlung an", "Dr. Friederike Nwosu-Lambrecht (Konto laut Personalstammdaten)"),
        ("Belege", "Receipt LSC-ODS27-04471, Kreditkartenabrechnung vom 31.10.2027"),
        ("Sachlich richtig", "Prof. Dr. Detlef Amankwah-Rohr, 02.11.2027")], k=24, indent=0),
])
case(EXP, "auslagenerstattung-b15", "abgelehnt",
     "Die Quittung der Lakeshore Conferences LLC belegt eine Gruppenanmeldung zur Online-Konferenz für drei Personen "
     "des Fachgebiets (je USD 140,00), bezahlt mit der Kreditkarte der Antragstellerin, die den gesamten Betrag von "
     "391,88 € an sich auszahlen lassen will. Online-Konferenzgebühren sind zwar als privat verauslagte Kosten "
     "abzurechnen, nach der Uni-Kassel-Seite „Dienstreisemanagement“ ist es aber untersagt, Kosten, die für mehrere "
     "Personen verauslagt wurden, nur an die verauslagende Person zu erstatten; die Kolleginnen und Kollegen müssen "
     "ihren Anteil selbst anfordern. Die Erstattung in dieser Form ist abzulehnen.",
     [doc("registration-receipt.pdf", b15_rec, font="Helvetica", producer="Stripe Receipts"),
      doc("kreditkartenabrechnung.pdf", b15_cc, producer="Hainbuchen Bank Online-Banking"),
      doc("erstattung-zusammenfassung.pdf", b15_form, font="Helvetica", producer="Universität Wernstadt PVK-Portal")],
     "Online-conference group registration (3 people, USD 420) paid by one person who claims all of it",
     "„Nach einer Prüfung durch den Hessischen Landesrechnungshof ist es uns untersagt, Kosten, die für mehrere Personen "
     "verauslagt wurden, nur an die verauslagende Person zu erstatten.“ (with „Die Teilnahmegebühren für Online "
     "Konferenzen / Tagungen sind über das Formular \"Privat Verauslagte Kosten\" … geltend zu machen.“)",
     "dienstreisemanagement.md", "Stripe-style English receipt, bank card statement, online refund portal printout",
     "yes (looks like the accepted practice case 08)", "low (the rule sits in the travel-cost section)")


# --------------------------------------------------------------------------- #
# Build and verify
# --------------------------------------------------------------------------- #
def words(text):
    return text.split()


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    problems = []
    for c in CASES:
        d = OUT / c["set"] / "inputs" / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        for name, text, opts in c["docs"]:
            path = d / name
            n_pages = write_pdf(path, text, title=name[:-4], **opts)
            got = pdftotext(path)
            if words(got) != words(text.replace("\f", "\n")):
                problems.append(f"{c['id']}/{name}: text layer differs from source")
            if got.count("\f") != n_pages:
                problems.append(f"{c['id']}/{name}: expected {n_pages} pages, pdftotext saw {got.count(chr(12))}")
    for s in SETS:
        lines = [json.dumps({"antrag": c["id"], "result": c["result"], "begruendung": c["begruendung"]},
                            ensure_ascii=False) for c in CASES if c["set"] == s]
        (OUT / s / "ground-truth.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "PROPOSALS.md").write_text(table(), encoding="utf-8")
    return problems


def table():
    n_a = sum(c["result"] == "angenommen" for c in CASES)
    n_t = sum(c["trap"].startswith("yes") for c in CASES)
    out = ["# Blind set 2: proposals",
           "",
           f"{len(CASES)} proposed cases, {n_a} angenommen and {len(CASES) - n_a} abgelehnt, {n_t} traps. "
           "the author picks 10 to score. Built by `experiments/blind2/tools/make_blind2.py` without reading the solver, its "
           "tests or earlier experiment sets. Every label rests on the quoted rule; policy files are in "
           "`the University of Kassel policy pages (not included here)`, ground truth in each set's `ground-truth.jsonl`.",
           "",
           "Trap = looks wrong but is fine, or looks fine but breaks a rule. Confidence = how sure the label is, "
           "not how hard the case is.",
           "",
           "| id | description | label | deciding rule (quote) | source | imitates | trap | confidence |",
           "|---|---|---|---|---|---|---|---|"]
    for c in CASES:
        cells = [c["id"], c["desc"], c["result"], c["rule"], c["source"], c["imitates"], c["trap"], c["conf"]]
        out.append("| " + " | ".join(x.replace("|", "/") for x in cells) + " |")
    out += ["", "Files per case: `<set>/inputs/<id>/*.pdf`. All PDFs have a text layer and round-trip through "
            "`pdftotext -layout` word for word (checked by the build).", ""]
    return "\n".join(out)


def main():
    if "--table" in sys.argv:
        print(table())
        return 0
    problems = build()
    for p in problems:
        print("PROBLEM", p)
    n_docs = sum(len(c["docs"]) for c in CASES)
    print(f"built {len(CASES)} cases, {n_docs} PDFs into {OUT}; problems: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
