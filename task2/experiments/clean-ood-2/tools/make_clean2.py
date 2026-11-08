#!/usr/bin/env python3
"""Build the second independent CLEAN test set (75 correct cases) for UniAgent Task 2.

Purpose: measure how often a document-reading program raises false alarms on correct
(approvable) German university admin cases it has never seen. All 75 cases carry the
label `angenommen`.

Written blind: the solver (facts.py, rules.py, predict.py, rule_search.py, case_tools.py), its
tests and all earlier experiment sets and their write-ups were NOT read. Sources used: the
policy pages in the University of Kassel policy pages (not included here) (the university's intranet/public pages, pseudonymised here as
"Universität Wernstadt"), the organisers' practice cases and ground truth, and
experiments/blind3-proposals/PROPOSALS.md. Only the PDF writer and the pdftotext call are
imported from experiments/blind3/tools/make_blind3.py (pure Python, base-14 fonts, WinAnsi).

    python3 experiments/clean-ood-2/tools/make_clean2.py

Output (overwritten): experiments/clean-ood-2/<set>/{inputs/<case>/*.pdf, ground-truth.jsonl}
and experiments/clean-ood-2/README.md.
"""
import datetime
import json
import pathlib
import re
import shutil
import sys
import textwrap
from decimal import Decimal

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "blind3" / "tools"))
import make_blind3 as mb  # noqa: E402  (PDF writer + pdftotext only)

write_pdf = mb.write_pdf
pdftotext = mb.pdftotext
D, r2, tot, vat_split, lr, kv = mb.D, mb.r2, mb.tot, mb.vat_split, mb.lr, mb.kv
A4, RECEIPT = mb.A4, mb.RECEIPT

OUT = HERE.parent
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

# --------------------------------------------------------------------------- #
# Number and date formats
# --------------------------------------------------------------------------- #
def _fmt(x, dec, thou, dp):
    s = f"{r2(x):,.2f}"
    return s.replace(",", "\0").replace(".", dp).replace("\0", thou)


def eur(x):       # 1.234,56
    return _fmt(x, 2, ".", ",")


def eng(x):       # 1,234.56
    return _fmt(x, 2, ",", ".")


def fr(x):        # 1 234,56
    return _fmt(x, 2, " ", ",")


def chf(x):       # 1'234.56
    return _fmt(x, 2, "'", ".")


def kz(x):        # 1234,56 (no thousands separator)
    return _fmt(x, 2, "", ",")


def rate_eur(x):  # exchange rate, 4 decimals
    return f"{D(x):.4f}".replace(".", ",")


MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
             "Oktober", "November", "Dezember"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
             "octobre", "novembre", "décembre"]
MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]
MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september",
             "oktober", "november", "december"]
WD_S = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WD_L = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WD_ENL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def dt(s):
    return datetime.date.fromisoformat(s)


def add(s, days):
    return (dt(s) + datetime.timedelta(days=days)).isoformat()


def de(s):        # 09.11.2026
    return dt(s).strftime("%d.%m.%Y")


def de2(s):       # 09.11.26
    return dt(s).strftime("%d.%m.%y")


def deshort(s):   # 9.11.
    d = dt(s)
    return f"{d.day}.{d.month}."


def iso(s):       # 2026-11-09
    return dt(s).isoformat()


def uk(s):        # 09/11/2026
    return dt(s).strftime("%d/%m/%Y")


def mon3(s):      # 09-NOV-2026
    return dt(s).strftime("%d-%b-%Y").upper()


def wds(s):       # Mo 09.11.2026
    return f"{WD_S[dt(s).weekday()]} {de(s)}"


def wdl(s):       # Montag, 09.11.2026
    return f"{WD_L[dt(s).weekday()]}, {de(s)}"


def wen(s):       # Mon 09.11.2026
    return f"{WD_EN[dt(s).weekday()]} {de(s)}"


def dlong(s):     # 9. November 2026
    d = dt(s)
    return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"


def wdlong(s):    # Montag, 9. November 2026
    return f"{WD_L[dt(s).weekday()]}, {dlong(s)}"


def den(s):       # 9 November 2026
    d = dt(s)
    return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def wden(s):      # Monday, 9 November 2026
    return f"{WD_ENL[dt(s).weekday()]}, {den(s)}"


def dfr(s):       # 9 novembre 2026
    d = dt(s)
    return f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def dit(s):       # 9 novembre 2026
    d = dt(s)
    return f"{d.day} {MONTHS_IT[d.month - 1]} {d.year}"


def dnl(s):       # 9 november 2026
    d = dt(s)
    return f"{d.day} {MONTHS_NL[d.month - 1]} {d.year}"


def nxt(s, n):
    """first date on or after s that falls on weekday n (0 = Monday)"""
    d = dt(s)
    while d.weekday() != n:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def conv(x, rate):
    """amount * exchange rate, rounded"""
    return r2(D(x) * D(rate))


def ndays(a, b):  # inclusive number of calendar days
    return (dt(b) - dt(a)).days + 1


def workdays(a, b):
    n, d = 0, dt(a)
    while d <= dt(b):
        n += d.weekday() < 5
        d += datetime.timedelta(days=1)
    return n


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #
def W(text, width=70, indent="", sub=None):
    """wrap a paragraph; the wrap may fall inside a phrase on purpose"""
    sub = indent if sub is None else sub
    return textwrap.fill(" ".join(text.split()), width=width, initial_indent=indent,
                         subsequent_indent=sub, break_long_words=False, break_on_hyphens=False)


def box(lines, w=None, ch="+-|"):
    """ASCII box around lines"""
    w = w or max(len(l) for l in lines)
    c, h, v = ch
    out = [c + h * (w + 2) + c]
    out += [v + " " + l.ljust(w) + " " + v for l in lines]
    out.append(c + h * (w + 2) + c)
    return "\n".join(out)


def rule(w=100, ch="-"):
    return ch * w


def grid(rows, widths, aligns=None, sep="  ", indent=0):
    """fixed-width table; each row a list of strings; widths per column; aligns 'l'/'r'.
    Left-aligned cells longer than the column are wrapped onto continuation lines."""
    aligns = aligns or ["l"] * len(widths)
    out = []
    for r in rows:
        cells = []
        for i, (c, w) in enumerate(zip(r, widths)):
            c = str(c)
            if aligns[i] == "l" and len(c) > w:
                cells.append(textwrap.wrap(c, w, break_long_words=False))
            else:
                cells.append([c.rjust(w) if aligns[i] == "r" else c.ljust(w)])
        n = max(len(x) for x in cells)
        for k in range(n):
            parts = []
            for i, (x, w) in enumerate(zip(cells, widths)):
                t = x[k] if k < len(x) else ""
                parts.append(t.rjust(w) if aligns[i] == "r" else t.ljust(w))
            out.append((" " * indent + sep.join(parts)).rstrip())
    return "\n".join(out)


def two(left, right, w=100):
    """two blocks side by side (left-aligned left block, right block flush right)"""
    L, R = left.split("\n"), right.split("\n")
    n = max(len(L), len(R))
    L += [""] * (n - len(L))
    R += [""] * (n - len(R))
    return "\n".join(lr(a, b, w) for a, b in zip(L, R))


def pages(*ps):
    return "\f".join(p.strip("\n") for p in ps)


def lines(*xs):
    return "\n".join(xs)


def net_gross(net, rate):
    net = r2(net)
    v = r2(net * D(rate) / 100)
    return net, v, r2(net + v)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
CASES = []
UW = "Universität Wernstadt"


def doc(name, text, **opts):
    return (name, text, opts)


def case(set_, cid, begruendung, docs, system, tricky, why, conf="high"):
    CASES.append(dict(set=set_, id=cid, begruendung=begruendung, docs=docs, system=system,
                      tricky=tricky, why=why, conf=conf))


# short source labels used in the README table
S_DRM = "policy-pages/dienstreisemanagement.md"
S_BESCH = "policy-pages/beschaffung.md"
S_RV = "policy-pages/rahmenvertraege.md"
S_FIBU = "policy-pages/finanzbuchhaltung-und-steuern.md"
S_GF = "policy-pages/geraetefondsverfahren.md"
S_CAT = "policy-pages/nachhaltiges-catering.md"
S_GLOS = "policy-pages/glossar-drittmittelbewirtschaftung.md"
S_HRKG = "policy-pages/hrkg.md"
S_ANL = "policy-pages/anlagen.md"
S_ITS = "policy-pages/endgeraete-beschaffung-its.md"
S_FAHR = "policy-pages/fahrbereitschaft-dienstfahrzeuge.md"
S_ZOLL = "policy-pages/zollverfahren.md"
S_W2P = "policy-pages/web-to-print-shop.md"
S_WPS = "policy-pages/wps-ersteller-besteller.md"

# frequently quoted rules
Q_NOAPPR = "„Reisekosten können nur für Dienstreisen … erstattet werden, wenn diese vorher angeordnet oder genehmigt sind.“"
Q_HOTEL80 = "„Nachgewiesene Übernachtungskosten sind bis zu einer Höhe von 80,00 € je Nacht erstattungsfähig.“"
Q_HOTELADDR = "„Rechnungen für Übernachtungskosten werden nur erstattet, sofern die [Universität] als Adressat angegeben ist.“"
Q_3OFFERS = "„Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“"
Q_DIRECT = "„Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“"
Q_RVBIND = "„Die Rahmenverträge sind verbindlich für alle Bereiche der [Universität].“"
Q_RVNOCOMP = "„… ohne das Einholen von Vergleichsangeboten zu decken.“"
Q_KOSTENERST = "„Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“"
Q_STICHWORT = "„Sollte auf der Quittung kein Artikel ausgewiesen sein, muss ein Stichwort … dazu geschrieben werden.“"


# =========================================================================== #
# BUSINESS TRIPS  (dienstreiseantrag-m01 .. m25)
# =========================================================================== #
def wk(s, n):
    """assert that date s falls on weekday n (0 = Monday) and return s"""
    assert dt(s).weekday() == n, (s, dt(s).weekday(), n)
    return s


# --------------------------------------------------------------------------- #
# m01  HISinOne print, private BahnCard 50 used, hotel 79 EUR with breakfast
# --------------------------------------------------------------------------- #
def m01():
    a, b, ant = wk("2027-03-25", 3), wk("2027-03-26", 4), "2027-02-22"
    fare = D("41.90")
    hotel = D("79.00")
    est = tot(fare * 2, hotel)
    form = f"""
HISinOne  |  Dienstreisen  |  Reiseantrag                                   angemeldet als: j.taubenheim
{rule(104, "=")}
Reiseantrag 2027-DR-00418                                  Status: eingereicht (Dienstweg: Dekanat FB 12)
{rule(104)}
 Reisende/r         Prof. Dr. Jorin Taubenheim, FB 12 Maschinenbau, Fachgebiet Strömungsmechanik
 Antragsdatum       {de(ant)}  (Reisebeginn in 31 Tagen)
 Reiseziel          Hamburg (Inland)            Auslandsreise: [ ] ja  [x] nein      A1: entfällt
 Anlass             Nutzertreffen "Windkanal-Verbund Nord", Programmpunkt: Vortrag der eigenen Ergebnisse
 Reisezeit          {wds(a)} 07:12 Uhr  bis  {wds(b)} 19:40 Uhr
 Dienstgeschäft     {wds(a)} 11:30 Uhr bis {wds(b)} 15:00 Uhr
 Privataufenthalt   keiner

 Kostenplan                                                   Anzahl        Betrag in EUR
 {rule(94)}
 Bahnfahrt Wernstadt Hbf - Hamburg Hbf und zurück, 2. Kl.        2 x {eur(fare)}       {eur(fare * 2)}
   (Sparpreis, vorhandene private BahnCard 50 wird eingesetzt; die Anschaffungskosten der
    BahnCard werden NICHT geltend gemacht)
 Übernachtung {de(a)} auf {de(b)}, Hotel Elbblick, inkl. Frühstück   1 x {eur(hotel)}      {eur(hotel)}
   (Frühstück im Zimmerpreis enthalten; Kürzung des Tagegeldes um 20 % ist mir bekannt)
 Teilnahmegebühr                                               entfällt                  0,00
 {rule(94)}
 Summe voraussichtlich                                                              {eur(est)}
 Tagegeld nach § 7 HRKG wird mit der Reisekostenabrechnung ermittelt.

 Finanzierung       Kostenstelle 12-4410 (Landesmittel, Fachgebiet)
 Anlagen            (1) Einladung vom 08.02.2027   (2) Bahn-Auftragsbestätigung   (3) Hotelreservierung
{rule(104)}
 Abgesendet von: Prof. Dr. Jorin Taubenheim am {de(ant)}, 09:14 Uhr
"""
    inv = f"""
Windkanal-Verbund Nord e. V.
Geschäftsstelle · Hafenstraße 9 · 21079 Hamburg


Prof. Dr. Jorin Taubenheim
Universität Wernstadt, FB 12


Hamburg, 8. Februar 2027

Einladung zum Nutzertreffen am {de(a)} und {de(b)}

Sehr geehrter Herr Kollege Taubenheim,

wir freuen uns, Sie zum Nutzertreffen unseres Verbundes einladen zu dürfen. Auf
dem Programm steht am Donnerstag um 11:30 Uhr Ihr Vortrag "Grenzschichtmessungen
im Kleinwindkanal" (25 Minuten). Die Veranstaltung endet am Freitag gegen 15:00 Uhr.

Das Treffen ist für Mitglieder des Verbundes kostenfrei.

Mit freundlichen Grüßen
Dr. Hanne Ostermeyer, Geschäftsführung
"""
    bahn = f"""
Auftragsbestätigung Bahn
Nr. 7 40 19 662 810
-------------------------------------
Reisende: J. TAUBENHEIM
Rabatt:   BahnCard 50 (2. Klasse)
-------------------------------------
Hinfahrt  {de(a)}
Wernstadt Hbf   ab 07:12
Hamburg Hbf     an 11:02
Sparpreis, 2. Klasse     {eur(fare)} EUR
-------------------------------------
Rückfahrt {de(b)}
Hamburg Hbf     ab 16:28
Wernstadt Hbf   an 19:40
Sparpreis, 2. Klasse     {eur(fare)} EUR
-------------------------------------
Gesamt                   {eur(fare * 2)} EUR
inkl. 7 % USt (Fernverkehr 2. Kl.)
Zahlung: Kreditkarte, Buchung
vorbehaltlich Genehmigung
"""
    hot = f"""
Von: reservierung@hotel-elbblick.example
An: j.taubenheim@uni-wernstadt.example
Betreff: Reservierungsbestätigung 88-41027
Datum: Fr, 12 Feb 2027 15:03 +0100

Guten Tag Herr Prof. Taubenheim,

hiermit bestätigen wir Ihre Reservierung:

   Zimmer:           Einzelzimmer Standard
   Anreise/Abreise:  {de(a)} / {de(b)}  (1 Nacht)
   Preis:            {eur(hotel)} EUR pro Nacht inkl. Frühstück und MwSt.
   Rechnung an:      Universität Wernstadt, FB 12 Maschinenbau,
                     Hochschulring 21, 35291 Wernstadt
   Stornierung:      kostenfrei bis 24.03.2027, 18:00 Uhr

Wir freuen uns auf Ihren Besuch.
Hotel Elbblick, Rezeption
"""
    docs = [doc("HISinOne_Reiseantrag_2027-DR-00418.pdf", form, margin=24),
            doc("einladung-nutzertreffen.pdf", inv, font="Times-Roman", producer="Microsoft Word"),
            doc("scan_0211.pdf", bahn, size=RECEIPT, margin=10),
            doc("hotel-reservierung.pdf", hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m01",
         "Rechtzeitig vor der Reise eingereichter Inlandsantrag mit Einladung und Vortrag. Bahn 2. Klasse mit privater BahnCard, "
         "deren Anschaffungskosten ausdrücklich nicht beantragt werden. Hotel 79,00 EUR liegt unter 80,00 EUR, die Rechnung geht an die Universität, "
         "die Kürzung des Tagegeldes wegen Frühstück ist erklärt. Summe stimmt.", docs,
         "HISinOne screen print (Courier), Word invitation letter, narrow rail receipt, hotel mail",
         "'BahnCard' appears but its purchase price is explicitly not claimed; 79 EUR hotel just below 80 EUR; breakfast included, Tagegeld cut acknowledged",
         "Rule: " + Q_HOTEL80 + " + „Die Erstattung der Anschaffungskosten für eine private BahnCard ist ausschließlich dann möglich, wenn sich die Kosten … vollständig amortisiert haben.“ (not claimed) + „Wenn die Übernachtungskosten die Kosten des Frühstücks einschließen, … 20% des Tagegeldes … einbehalten.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m02  MACH-style key/value form, Vienna, flight with comparison, gala dinner not booked
# --------------------------------------------------------------------------- #
def m02():
    ant = "2027-04-12"
    a, b = wk("2027-06-14", 0), wk("2027-06-16", 2)
    flight, hotel, reg = D("142.00"), D("78.00"), D("395.00")
    est = tot(flight, hotel * 2, reg)
    mach = f"""
MACH c/s  -  Modul DIENSTREISE  -  Maske RA01 (Reiseantrag Ausland)               Seite 1/1
------------------------------------------------------------------------------------------
Lfd.Nr. ...............: RA-27-0933
Antragsteller/in ......: Dr. Selma Kaczmarek-Ihle
Organisationseinheit ..: Institut für Umweltsystemforschung (USF)
Kostenstelle/Auftrag ..: 4100-77 / 6-2931  (Drittmittel, Projekt CLIMAPATH, AP 4)
Erfassungsdatum .......: {de(ant)}                    Eingang Reisestelle: {de(ant)}
------------------------------------------------------------------------------------------
Reiseziel .............: Wien, ÖSTERREICH
Reise ins Ausland .....: J                              A1-Antrag gestellt am: {de(ant)}
Anlass ................: Konferenz "EnvSys Vienna 2027" (14.-16.06.), Posterbeitrag
Beginn Reise ..........: {de(a)} 09:40 (Abflug FRA)      Ende Reise: {de(b)} 20:15 (Landung FRA)
Beginn Dienstgeschäft .: {de(a)} 13:00                  Ende Dienstgeschäft: {de(b)} 17:30
Privataufenthalt ......: N
Verkehrsmittel ........: Flug Economy FRA-VIE-FRA
Begründung Flug .......: Flug 142,00 EUR günstiger als Bahn (169,00 EUR, 9 h 05 min pro Richtung);
                         Preisvergleich liegt bei. Rückflug am Tag des Dienstschlusses.
------------------------------------------------------------------------------------------
Pos  Kostenart                              Menge   Einzelbetrag   Summe EUR
 1   Flug FRA-VIE-FRA, Economy                  1       {eur(flight):>8}    {eur(flight):>8}
 2   Übernachtung Wien (Hotel nahe Tagungsort)  2       {eur(hotel):>8}    {eur(hotel * 2):>8}
 3   Tagungsgebühr (Standard, Poster)           1       {eur(reg):>8}    {eur(reg):>8}
 4   Gala-Dinner (15.06.)                       --         nicht beantragt     0,00
                                                       Gesamt (Schätzung)   {eur(est):>8}
------------------------------------------------------------------------------------------
Hinweis Antragsteller/in: Das Gala-Dinner wurde nicht gebucht und wird weder jetzt noch bei der
Abrechnung geltend gemacht.
Unterschrift Antragsteller/in: S. Kaczmarek-Ihle        Datum: {de(ant)}
Genehmigung Institutsleitung: --- (liegt zur Unterschrift vor)
"""
    reg_doc = f"""
 ConfTool Pro - EnvSys Vienna 2027                              Registration Confirmation
 ----------------------------------------------------------------------------------------
 Registration #: 2027-0318                       Date: {den(ant)}
 Participant:    Dr. Selma Kaczmarek-Ihle, {UW}
 Invoice to:     {UW}, Institut für Umweltsystemforschung, Hochschulring 21, 35291 Wernstadt
 VAT ID:         (reverse charge, Art. 196 VAT Directive)

 Item                                              Amount
 Regular registration (poster presenter)           EUR {eng(reg)}
 Gala dinner, Tue 15 June (optional)               not booked
 Lunches on 15 and 16 June                         included
 ----------------------------------------------------------------------------------------
 Total                                             EUR {eng(reg)}
 Payment due: {den(add(ant, 30))} by bank transfer. Payer reference: EVV-0318
"""
    vgl = f"""
Reisebüro Römerberg GmbH                                                  Preisvergleich
Zeil 14 · 60313 Frankfurt am Main                                  Nr. PV-27-1180 vom {de(ant)}

Kundin: Dr. S. Kaczmarek-Ihle, Universität Wernstadt, Institut für Umweltsystemforschung

Strecke Frankfurt (FRA) - Wien (VIE), Economy, 1 Person, Hin {de(a)} / Rück {de(b)}

  Variante                                                Preis
  A  Flug, Rückflug am {de(b)} (Ende Dienstgeschäft)    {eur(flight)} EUR
  B  Flug, späterer Rückflug                                 --  (nicht gebucht)
  C  Bahn Wernstadt - Wien - Wernstadt, 2. Klasse, Sparpreis 169,00 EUR, 9 h 05 min je Richtung

Empfehlung: Variante A (günstigste Verbindung). Preise inkl. USt, Stand {de(ant)}.
"""
    docs = [doc("Reiseantrag_RA-27-0933.pdf", mach, margin=22),
            doc("registration-confirmation.pdf", reg_doc, font="Helvetica"),
            doc("Preisvergleich_Flug_Bahn.pdf", vgl, font="Times-Roman")]
    case(TRIP, "dienstreiseantrag-m02",
         "Vollständiger Auslandsantrag zehn Wochen vor Reisebeginn, A1 am selben Tag beantragt, Poster angenommen. Flug Economy mit Preisvergleich gegen Bahn und "
         "gegen späteren Rückflug, Hotel 78,00 EUR, Tagungsgebühr stimmt mit der Registrierung überein. Das Gala-Dinner wird weder gebucht noch beantragt.", docs,
         "MACH c/s style key/value mask (dotted labels), ConfTool registration (English), agency price comparison",
         "optional gala dinner named in three documents but 'not booked / not claimed'; lunches included in fee (no meal claim)",
         "Rule: „Bei Flugreisen ist dem Dienstreiseantrag ein Preisvergleich beizufügen.“ + „Die auf den Rechnungen ausgewiesenen Verpflegungskosten für Mittag- uns Abendverpflegung werden … nur dann erstattet, wenn es sich nachweislich um eine notwendige Pauschale handelt“ (dinner not claimed) + A1 „spätestens acht Wochen vor Beginn“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m03  DFN-style mail print as the application itself; unpaid invited talk, host lunch
# --------------------------------------------------------------------------- #
def m03():
    ant = "2027-04-19"
    a = wk("2027-05-12", 2)
    b = "2027-05-13"
    fare, hotel = D("58.40"), D("74.00")
    mail = f"""
Thunderbird  -  Gesendet  -  Mail-Header drucken
=================================================================================
Von:      Prof. Dr. Gundula Reinsch <g.reinsch@uni-wernstadt.example>
An:       dienstreisen@uni-wernstadt.example
Kopie:    Dekanat FB 15 <dekanat-fb15@uni-wernstadt.example>
Datum:    {WD_S[dt(ant).weekday()]}, {dt(ant).day:02d}.{dt(ant).month:02d}.{dt(ant).year}, 08:51
Betreff:  Genehmigung Dienstreise Freiburg {de(a)} - {de(b)} (Kolloquium)
Priorität: normal
=================================================================================

Sehr geehrte Damen und Herren,

hiermit beantrage ich die Genehmigung einer Dienstreise nach Freiburg (Inland).

 Anlass:       Eingeladener Vortrag im Physikalischen Kolloquium der Universität
               Freiburg, {wdl(a)}, 16:15 Uhr
 Reisezeit:    Mi {de(a)}, Abfahrt 10:20 Uhr, bis Do {de(b)}, Ankunft ca. 14:30 Uhr
 Kosten:       Bahn 2. Klasse hin/zurück   {eur(fare)} EUR (Sparpreis)
               Hotel, 1 Nacht              {eur(hotel)} EUR (ohne Frühstück)
               Summe                       {eur(tot(fare, hotel))} EUR
 Kostenstelle: 15-2002 (Landesmittel)

Die Einladung (Mail von Prof. Wiegand vom 02.04.) füge ich als PDF an. Das Kolloquium
sieht für Gäste ausdrücklich keine Vergütung vor; ich erhalte also weder Honorar noch
Aufwandsentschädigung für den Vortrag. Der Gastgeber lädt zum gemeinsamen Mittagessen
am Donnerstag ein - für diesen Tag wird das Tagegeld daher um 40 % gekürzt, das habe ich
bei der Abrechnung zu berücksichtigen. Sonstige Leistungen Dritter gibt es nicht.

Eine Verlängerung um private Tage ist nicht geplant.

Mit freundlichen Grüßen
Gundula Reinsch

--
Prof. Dr. Gundula Reinsch · FB 15 Physik · Fachgebiet Festkörperoptik
Hochschulring 21 · 35291 Wernstadt · Tel. 0611-55 20 17
"""
    einl = f"""
Von: Wiegand, Anselm <anselm.wiegand@physik.uni-freiburg.example>
Gesendet: Freitag, 2. April 2027 17:44
An: Reinsch, Gundula
Betreff: Einladung Physikalisches Kolloquium SoSe 2027

Liebe Frau Reinsch,

vielen Dank für Ihre Zusage! Wir freuen uns sehr, dass Sie am {dlong(a)} um 16:15 Uhr
im Hörsaal 2 über "Nichtlineare Optik in dünnen Schichten" sprechen. Wie bei allen
Gästen des Kolloquiums können wir leider kein Vortragshonorar zahlen; wir übernehmen
aber gern das gemeinsame Mittagessen am Donnerstag mit dem Arbeitskreis. Reise und
Übernachtung bitte über Ihre Einrichtung abrechnen.

Herzliche Grüße
Anselm Wiegand
"""
    docs = [doc("Antrag_Freiburg.pdf", mail, margin=24),
            doc("Einladung Kolloquium.pdf", einl, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m03",
         "Formloser Antrag per E-Mail mit Einladung. Der Vortrag ist unvergütet (kein Honorar), die Reisekosten trägt die Universität; das vom Gastgeber gestellte "
         "Mittagessen wird mit 40 % Tagegeldkürzung berücksichtigt. Kosten (58,40 + 74,00 = 132,40 EUR) stimmen.", docs,
         "Thunderbird mail print as the application, quoted invitation mail from the host",
         "'Honorar' only in negated form ('weder Honorar noch Aufwandsentschädigung', 'kein Vortragshonorar'); host pays lunch, Tagegeld cut stated",
         "Rule: „Wird Ihnen im Rahmen einer Dienstreise ein Honorar … gezahlt, deutet dies auf eine Nebentätigkeit … hin.“ (here: no fee paid) + „Erhalten Dienstreisende … von dritter Seite unentgeltlich Verpflegung bereitgestellt …, … für das Mittag- … um 40 Prozent … zu kürzen“ [" + S_DRM + ", " + S_HRKG + " § 10]")


# --------------------------------------------------------------------------- #
# m04  Fiori-like (Helvetica); DAAD grant covers the flight only, claim limited to rest
# --------------------------------------------------------------------------- #
def m04():
    ant = "2027-05-03"
    a, b = wk("2027-07-12", 0), wk("2027-07-15", 3)
    hotel, reg, flight = D("74.00"), D("360.00"), D("318.00")
    claim = tot(hotel * 3, reg)
    app = f"""
 SAP                         Meine Reiseanträge  >  Reiseantrag 1000067213                         Abbrechen   Sichern
 -----------------------------------------------------------------------------------------------------------------
 Reiseantrag 1000067213          Status: In Genehmigung          Reisende: Dr. Ravi Menon-Hartwig (P-0048213)
 -----------------------------------------------------------------------------------------------------------------
 Allgemein                                   Zeitraum
   Reiseziel        Lissabon, Portugal         Beginn         {de(a)}  06:15 (Abreise Wohnort)
   Auslandsreise    Ja                         Ende           {de(b)}  23:10 (Ankunft Wohnort)
   Anlass           International Conference on Soft Matter Rheology (ICSMR 2027), Vortrag
   Antragsdatum     {de(ant)}                  A1-Bescheinigung   beantragt, {de(ant)}
 -----------------------------------------------------------------------------------------------------------------
 Kosten (Schätzung, in EUR)                                                     Beantragt     Dritter
   Flug Frankfurt - Lissabon - Frankfurt (Economy)                                   0,00      {eur(flight)}
   Hotel 3 Nächte, je {eur(hotel)}                                                 {eur(hotel * 3)}         0,00
   Konferenzgebühr (Early Bird)                                                    {eur(reg)}         0,00
   Summe beantragt aus Landesmitteln FB 07                                        {eur(claim)}
 -----------------------------------------------------------------------------------------------------------------
 Leistungen von dritter Seite
   Geber: DAAD (Reisekostenzuschuss für Promovierte und Postdocs), Bewilligung Nr. 57741906 vom 14.04.2027
   Umfang: ausschließlich Flugkosten bis {eur(D("380.00"))} EUR. Unterkunft und Tagungsgebühr sind nicht gefördert.
   Der Flug ({eur(flight)} EUR) wird daher NICHT aus Mitteln der Universität beantragt; es besteht keine
   Doppelfinanzierung. Zuschussbescheid hängt an.
 -----------------------------------------------------------------------------------------------------------------
 Anlagen  Annahmebestätigung Vortrag · DAAD-Bescheid · Flugbuchung · Hotelbuchung · Gebührenrechnung
"""
    daad = f"""
Deutscher Akademischer Austauschdienst
Referat 322 · Kennedyallee 50 · 53175 Bonn


Herrn Dr. Ravi Menon-Hartwig
Universität Wernstadt, FB 07


Bonn, 14. April 2027                                           Bewilligung Nr. 57741906

Reisekostenzuschuss zur Teilnahme an wissenschaftlichen Fachtagungen im Ausland

Sehr geehrter Herr Dr. Menon-Hartwig,

wir freuen uns, Ihnen für die Teilnahme an der ICSMR 2027 in Lissabon (12. bis 15. Juli 2027)
einen Zuschuss zu den Flugkosten in Höhe von höchstens 380,00 EUR bewilligen zu können.
Die Förderung ist auf die Flugkosten beschränkt. Kosten für Unterkunft, Verpflegung
und Tagungsgebühr werden nicht übernommen. Bitte beachten Sie, dass Leistungen, die
Ihre Heimateinrichtung für dieselben Kostenpositionen erbringt, anzugeben sind.

Mit freundlichen Grüßen
Im Auftrag
Beate Lindner
"""
    flug = f"""
BOOKING CONFIRMATION                                     Reference: 6F3KQ9
Passenger: MENON-HARTWIG/RAVI MR                         Issued: {den(add(ant, -2))}

Flight        Date              From              To                Time        Class
TX 4451       {den(a)}   Frankfurt (FRA)   Lisbon (LIS)      07:55-10:40  Economy (V)
TX 4458       {den(b)}   Lisbon (LIS)      Frankfurt (FRA)   18:05-22:00  Economy (V)

Fare EUR {eng(D("268.07"))}   Taxes and charges EUR {eng(D("49.93"))}   TOTAL EUR {eng(flight)}
Form of payment: DAAD travel grant account (direct billing to DAAD, grant 57741906)
"""
    hot = f"""
Hotel Palmeira Central · Rua das Flores 88 · 1200-195 Lisboa · Portugal
CONFIRMATION / CONFIRMAÇÃO DE RESERVA                       Booking no. PC-221907

Guest:     Dr. Ravi Menon-Hartwig
Invoice to: {UW}, FB 07 Naturwissenschaften, Hochschulring 21, 35291 Wernstadt, Germany
Check-in:  {den(a)}   Check-out: {den(b)}   3 nights, single room
Rate:      EUR {eng(hotel)} per night incl. 6 % city taxes, no breakfast        Total EUR {eng(hotel * 3)}
"""
    docs = [doc("reiseantrag_1000067213.pdf", app, font="Helvetica", margin=22),
            doc("DAAD_Bewilligung.pdf", daad, font="Times-Roman", producer="Microsoft Word"),
            doc("Anlage 3.pdf", flug + "\f" + hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m04",
         "Auslandsantrag neun Wochen vor Reisebeginn. Der DAAD-Zuschuss deckt ausschließlich den Flug, der Antrag verlangt aus Universitätsmitteln nur Hotel und Gebühr "
         "(222,00 + 360,00 = 582,00 EUR). Keine Doppelfinanzierung, die Leistung Dritter ist angegeben.", docs,
         "SAP Fiori-style object page (Helvetica) with a 'Dritter' column, DAAD letter, merged flight+hotel PDF with neutral name",
         "third-party grant mentioned prominently, but it covers other cost items; flight shows 0,00 in the claimed column",
         "Rule: „Die erhaltenen Leistungen von dritter Seite werden nach § 4 Abs. 3 HRKG … auf die zustehende Reisekostenerstattung angerechnet. Aus diesem Grund ist bei einer Reisekostenabrechnung anzugeben, welche Leistungen Sie erhalten haben.“ (done, no overlap) [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m05  Bologna, private extension of 2 working days; prices show no extra cost
# --------------------------------------------------------------------------- #
def m05():
    ant = "2027-03-08"
    a, b = wk("2027-05-17", 0), wk("2027-05-19", 2)
    priv_to = wk("2027-05-23", 6)
    fl = D("119.00")
    hotel = D("79.00")
    reg = D("290.00")
    est = tot(fl, hotel * 2, reg)
    letter = f"""
Dr. Ewa Lindenau                                                   Wernstadt, {dlong(ant)}
Fachgebiet Bioinformatik, FB 10
Universität Wernstadt

An die Reisekostenstelle

ANTRAG AUF GENEHMIGUNG EINER DIENSTREISE (Ausland) mit anschließendem Privataufenthalt

Reiseziel:         Bologna, Italien
Anlass:            Jahrestagung der Fachgesellschaft "Computational Genomics Italia" (CGI 2027),
                   {dlong(a)} bis {dlong(b)}; ich halte einen Vortrag (Einladung als Anlage)
Dienstgeschäft:    {wds(a)} ab 14:00 Uhr bis {wds(b)} 17:00 Uhr
Hinflug:           {de(a)} (Frankfurt - Bologna, Economy)
Rückflug:          {de(priv_to)} (gebucht nach dem privaten Aufenthalt)
Privataufenthalt:  {wds(add(b, 1))} bis {wds(priv_to)} - das sind 2 Arbeitstage ({de(add(b,1))}, {de(add(b,2))})
                   und das Wochenende; Urlaubstage sind beantragt (SAP-Abwesenheit vom {de(ant)}).

Der private Anschlussaufenthalt dauert damit nicht mehr als 5 Arbeitstage. Der Preisvergleich
des Reisebüros liegt bei: Der Rückflug am {de(b)} kostet {eur(fl)} EUR, der gebuchte Rückflug am
{de(priv_to)} ebenfalls {eur(fl)} EUR; durch die Verlängerung entstehen der Universität keine Mehrkosten.
Die zwei Hotelnächte nach dem {de(b)} und alle weiteren privaten Kosten trage ich selbst (separate
Buchung auf meinen Namen).

Kostenschätzung (dienstlich):
   Flug Economy, hin/zurück                         {eur(fl):>8} EUR
   Hotel Bologna, 2 Nächte x {eur(hotel)} EUR (Tagungshotel)  {eur(hotel * 2):>8} EUR
   Tagungsgebühr                                    {eur(reg):>8} EUR
   Summe                                            {eur(est):>8} EUR
Finanzierung: Kostenstelle 10-3180. Eine A1-Bescheinigung wurde heute beantragt.

Mit freundlichen Grüßen
Ewa Lindenau
"""
    prezzo = f"""
Reisebüro Nordlicht · Tel. 069 55 91 04 · info@reisebuero-nordlicht.example

PREISVERGLEICH FLUG                                 Datum: {de(ant)}
Reisende: Dr. Ewa Lindenau · Frankfurt (FRA) - Bologna (BLQ) - Frankfurt (FRA) · Economy

  Nr.  Hinflug         Rückflug         Preis (inkl. Steuern/Gebühren)
  A    {de(a)}   {de(b)}    {eur(fl)} EUR   <- Rückreise direkt nach Ende des Dienstgeschäfts
  B    {de(a)}   {de(priv_to)}    {eur(fl)} EUR   <- gebucht

Differenz B - A: 0,00 EUR. Tarif "Light" in beiden Fällen, gleiche Gesellschaft (Lagonero Air).
"""
    hotel_it = f"""
HOTEL PALAZZO DELLE ARTI ** Bologna · Via Zamboni 77 · 40126 Bologna
CONFERMA DI PRENOTAZIONE n. 2027/05/0412

Ospite:            Dott.ssa Ewa Lindenau
Fatturare a:       {UW}, Fachgebiet Bioinformatik, Hochschulring 21, 35291 Wernstadt (DE)
Prenotazione 1:    {dit(a)} - {dit(b)}, 2 notti, camera singola, {fr(hotel)} euro a notte, IVA inclusa
                   (tariffa congresso CGI 2027)                          totale {fr(hotel * 2)} euro
Prenotazione 2:    {dit(b)} - {dit(priv_to)}, 4 notti - prenotazione PRIVATA a nome dell'ospite,
                   pagamento e fattura personali. Non fatturare all'universita.
Tassa di soggiorno non inclusa (pagamento in hotel).
"""
    docs = [doc("Antrag_Bologna.pdf", letter, font="Times-Roman", producer="Microsoft Word", margin=36),
            doc("preisvergleich.pdf", prezzo, font="Helvetica"),
            doc("Bestätigung_Hotel_it.pdf", hotel_it, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m05",
         "Konferenzreise nach Bologna mit privatem Anschluss von nur 2 Arbeitstagen (plus Wochenende), also höchstens 5 Arbeitstage. Preisvergleich zeigt "
         "keinen Mehrpreis, private Hotelnächte sind getrennt gebucht und nicht beantragt. Antrag acht Wochen vor Reisebeginn, A1 beantragt.", docs,
         "Word letter (Times), travel-agency comparison, Italian hotel confirmation with two bookings",
         "private extension clearly shown (4 private nights, return flight after the weekend) but within 5 working days; zero price difference",
         "Rule: „Dauert der Privataufenthalt weniger als oder genau 5 Arbeitstage, so wird die Reisekostenvergütung so festgesetzt, als habe nur die Dienstreise stattgefunden.“ + „Bei Flugreisen ist dem Dienstreiseantrag ein Preisvergleich beizufügen.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m06  English form (international staff); long private stay (> 5 working days), only
#      the official part claimed
# --------------------------------------------------------------------------- #
def m06():
    ant = "2027-03-29"
    a, b = wk("2027-06-07", 0), wk("2027-06-09", 2)
    p_from, p_to = wk("2027-06-10", 3), wk("2027-06-22", 1)
    rail_o, rail_r = D("62.90"), D("62.90")
    hotel = D("77.00")
    est = tot(rail_o, rail_r, hotel * 2)
    form = f"""
{UW}  -  Personnel and Organisation - Travel Section
TRAVEL AUTHORISATION REQUEST (domestic)                                  Form DR-EN / v. 2027-01
{rule(100, "=")}
Applicant            : Dr. Lioba Nussbaumer (staff no. 20-4417), Dept. of Sociology, FB 03
Date of request      : {den(ant)}
Destination          : Munich, Germany (domestic)          Abroad: [ ] yes   [x] no
Purpose              : Annual meeting of the European Network for Time-Use Research (ENTUR),
                       {den(a)} - {den(b)}; presentation of a project paper (acceptance e-mail attached)
Official part        : {wden(a)}, 14:00  to  {wden(b)}, 16:30
Private stay         : {den(p_from)} to {den(p_to)} (annual leave, {workdays(p_from, p_to)} working days) - private
                       Return journey on {den(add(p_to, 0))}.
{rule(100)}
Because the private stay is longer than five working days, the trip is treated as predominantly
private. I therefore request ONLY the costs necessary for the official business:

   - Rail Wernstadt - Munich, outward {den(a)}, 2nd class        EUR {eng(rail_o)}
   - Rail Munich - Wernstadt, return fare as on {den(add(b, 0))} (price comparison enclosed;
     the ticket actually used is flexible and dated {den(p_to)})        EUR {eng(rail_r)}
   - Hotel, 2 nights during the meeting ({den(a)} to {den(b)}), conference rate  2 x EUR {eng(hotel)} = EUR {eng(hotel * 2)}
   - Daily allowance only for the official days and the travel days (calculated at settlement).

   NOT claimed: the {workdays(p_from, p_to)} private nights, meals and local transport during the leave, and any fare supplement.
{rule(100)}
Total estimated (official part)                                          EUR {eng(est)}
Funding : cost centre 03-5520
Signature: L. Nussbaumer, {den(ant)}
Line manager (Prof. Dr. T. Eschenbach): approved in advance by e-mail of {den(add(ant, 1))} (attached)
"""
    vgl = f"""
RAIL PRICE COMPARISON (screenshot of booking portal, printed {de(add(ant, 0))})

Route:  Munich Hbf -> Wernstadt Hbf, 2nd class, 1 adult
  Date of travel                      Fare type         Price
  {de(b)} (end of official part)    Sparpreis          EUR {eng(rail_r)}
  {de(p_to)} (actual, after leave)    Flexpreis          EUR {eng(D("108.00"))}   <- not claimed in full

Only the Sparpreis of {de(b)} (EUR {eng(rail_r)}) is claimed; the difference stays with the traveller.
"""
    hot = f"""
Booking confirmation          Hotel Isarblick Munich              Conf. no. IB-77-0603
Guest: LIOBA NUSSBAUMER
Bill to: {UW}, FB 03 Gesellschaftswissenschaften, Hochschulring 21, 35291 Wernstadt
Stay 1 (invoice to the University): {de(a)} - {de(b)}, 2 nights, single room, EUR {eng(hotel)} per night
Stay 2 (private, invoice to guest, not for reimbursement): {de(p_from)} - {de(p_to)} was booked at a different hotel.
"""
    docs = [doc("travel_request.pdf", form, font="Helvetica", margin=22),
            doc("rail-comparison.pdf", vgl, font="Courier"),
            doc("hotel.pdf", hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m06",
         "Der private Anschluss ist länger als 5 Arbeitstage, deshalb beantragt die Antragstellerin ausschließlich den dienstlichen Anteil (Bahn zum Vergleichspreis des "
         "dienstlichen Rückreisetags, 2 Hotelnächte, Tagegeld nur für Dienst- und Reisetage). Private Nächte und Mehrpreis werden selbst getragen.", docs,
         "English travel form (Helvetica), rail price comparison with Flexpreis, hotel confirmation (English)",
         "12-day private stay is stated openly (> 5 working days) but costs are split correctly; return fare capped at the comparison fare",
         "Rule: „Dauert der Privataufenthalt mehr als 5 Arbeitstage, … dürfen nur die zusätzlichen Fahrtauslagen erstattet werden, die zur Ausübung des Dienstgeschäftes notwendig sind. Tage- und Übernachtungsgeld sowie sonstige Kosten werden nur für die Dauer des Dienstgeschäftes und die Reisetage gewährt.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m07  Switzerland by rail; web-form print; CHF; fee waived; private lodging, no allowance claimed
# --------------------------------------------------------------------------- #
def m07():
    ant = "2027-03-15"
    a, b = wk("2027-06-03", 3), wk("2027-06-04", 4)
    fare = D("79.90")
    rate = D("1.04")
    tram = D("18.00")
    tram_eur = conv(tram, rate)
    est = tot(fare * 2, tram_eur)
    web = f"""
https://reisen.intranet.uni-wernstadt.example/antrag/neu?id=DR27-5531                           {de(ant)}, 10:48
Dienstreise beantragen  ·  Schritt 4 von 4: Zusammenfassung
--------------------------------------------------------------------------------------------------------
Antragstellerin     Dr. Henrike Albrecht-Vollmer · FB 16 Elektrotechnik/Informatik · Fachgebiet Eingebettete Systeme
Zielort             Basel, SCHWEIZ                    Auslandsreise  (x) Ja   ( ) Nein
Veranstaltung       Workshop on Embedded Learning Systems (WELS 2027), Rheinknie Institute of Technology
Dienstgeschäft      {wds(a)} 13:00  bis  {wds(b)} 12:30  -  eingeladener Kurzvortrag (Einladung hängt an)
Abreise / Rückkehr  {wds(a)} 06:05 Uhr  /  {wds(b)} 19:10 Uhr
Entsendebescheinigung (A1/CH)  Antrag gestellt am {de(ant)}, 11 Wochen vor Reisebeginn

Voraussichtliche Kosten
  Bahn Wernstadt Hbf - Basel SBB und zurück, 2. Kl., Sparpreis Europa   2 x {eur(fare)}  = {eur(fare * 2)} EUR
  Teilnahmegebühr      CHF 0.00 (Referent:innen: Gebühr erlassen, siehe Bestätigung)   =  0,00 EUR
  ÖV-Tageskarten Basel 2 x CHF 9.00 (Kurs {rate_eur(rate)}) = CHF {chf(tram)} = {eur(tram_eur)} EUR
      Begründung Nebenkosten: Veranstaltungsort liegt außerhalb des Bahnhofsumfelds, einziger
      sinnvoller Weg ist der Tramverkehr.
  Übernachtung          keine Kosten beantragt: Ich übernachte privat bei Bekannten und
                        beantrage auch das pauschale Übernachtungsgeld nicht.
  Summe                                                                 {eur(est)} EUR
Kostenträger        Kostenstelle 16-0771 (Landesmittel)
--------------------------------------------------------------------------------------------------------
[ x ] Ich habe alle Angaben vollständig gemacht      [ x ] Anlagen hochgeladen: 2
[ Antrag absenden ]                                        Seite 1 von 1 · gedruckt aus Chromium
"""
    conf = f"""
Rheinknie Institute of Technology · Departement Informatik · Spiegelgasse 12 · CH-4051 Basel

Anmeldebestätigung WELS 2027                              Basel, {dlong(add(ant, -20))}
Teilnehmerin: Dr. Henrike Albrecht-Vollmer, Universität Wernstadt (D)
Rechnungsadresse: Universität Wernstadt, FB 16, Hochschulring 21, D-35291 Wernstadt

  Position                                      Betrag
  Tagungsgebühr Standard                        CHF 180.00
  Ermässigung Eingeladene Referierende (100 %)  CHF -180.00
  Total                                         CHF   0.00

Das Programm ist beigelegt: Ihr Kurzvortrag "Tiny Models on Tiny Devices" ist für
{WD_L[dt(a).weekday()]}, {dlong(a)}, 14:20 Uhr vorgesehen. Pausenverpflegung ist inbegriffen. Die
Workshop-Abendveranstaltung findet auf eigene Rechnung statt und ist von Ihnen nicht gebucht worden.
"""
    tick = f"""
Reiseplan  -  Fahrplanauskunft
-------------------------------------
Hinfahrt   {de(a)}
Wernstadt Hbf     ab 06:05
Basel SBB         an 11:09
2. Klasse Sparpreis Europa
Preis             {eur(fare)} EUR
-------------------------------------
Rückfahrt  {de(b)}
Basel SBB         ab 13:50
Wernstadt Hbf     an 19:10
2. Klasse Sparpreis Europa
Preis             {eur(fare)} EUR
-------------------------------------
Summe             {eur(fare * 2)} EUR
(Angebot, Zugbindung)
"""
    docs = [doc("Antrag_DR27-5531_Zusammenfassung.pdf", web, font="Helvetica", margin=22,
                producer="Skia/PDF m118", creator="Chromium"),
            doc("Anmeldung_WELS_Bestaetigung.pdf", conf, font="Times-Roman"),
            doc("fahrplan.pdf", tick, size=RECEIPT, margin=10)]
    case(TRIP, "dienstreiseantrag-m07",
         "Auslandsantrag elf Wochen im Voraus mit Einladung und A1-Antrag. Tagungsgebühr für Vortragende erlassen (CHF 0.00), Bahn 2. Klasse, private Unterkunft "
         "ohne Übernachtungsgeld; die kleine Nebenkostenposition (Tram) ist begründet. Summe 177,52 EUR stimmt.", docs,
         "Chromium web-form print (Helvetica), Swiss confirmation with CHF and apostrophes, narrow fare-planner receipt",
         "fee shown as 180.00 then -180.00 = 0.00 (waived); no hotel and no lump-sum claimed; CHF amount converted at stated rate",
         "Rule: „Anfallende Nebenkosten (z. B. Taxi- und Telefonkosten etc.) können nur erstattet werden, sofern sie dienstlich notwendig und in der Reisekostenabrechnung entsprechend begründet werden.“ (justified) + „Ohne Nachweis wird auf Antrag … Übernachtungsgeld … erstattet“ (no request) + A1 acht Wochen vorher [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m08  Ticket-system print (Zammad style); UK, GBP, UK date formats, dinner declined
# --------------------------------------------------------------------------- #
def m08():
    ant = "2027-07-05"
    a, b = wk("2027-09-20", 0), wk("2027-09-22", 2)
    flight = D("186.40")
    hotel_gbp, reg_gbp = D("66.00"), D("210.00")
    rate = D("1.16")
    hotel_eur = conv(hotel_gbp * 2, rate)
    reg_eur = conv(reg_gbp, rate)
    est = tot(flight, hotel_eur, reg_eur)
    z = f"""
Zammad  ·  Ticket#2027070500264  ·  Dienstreise Edinburgh {deshort(a)}-{deshort(b)}2027 (FG Geoinformatik)
=========================================================================================================
Status: offen      Gruppe: Reisekosten / FB 13       Priorität: 2 normal       Kunde: Dr. Fridtjof Holm
Erstellt: {de(ant)} 09:31          Zuletzt aktualisiert: {de(ant)} 09:31          Artikel: 2
---------------------------------------------------------------------------------------------------------
[1] E-Mail von Dr. Fridtjof Holm an dienstreisen@uni-wernstadt.example - {de(ant)} 09:31
    Betreff: Dienstreiseantrag Edinburgh, Geospatial Methods Meeting (GSM 2027)

    Liebe Reisestelle,

    ich bitte um Genehmigung der folgenden Auslandsdienstreise (Vorlauf 11 Wochen, damit die
    Entsendebescheinigung für das Vereinigte Königreich rechtzeitig beantragt werden kann):

      Ziel:            Edinburgh, Vereinigtes Königreich
      Anlass:          Geospatial Methods Meeting, {den(a)} - {den(b)}; Vortrag (accepted talk,
                       confirmation attached)
      Flug:            Frankfurt - Edinburgh - Frankfurt, Economy, {eur(flight)} EUR
      Hotel:           2 Nächte, GBP {eng(hotel_gbp)} je Nacht = GBP {eng(hotel_gbp * 2)}  (~ {eur(hotel_eur)} EUR bei 1 GBP = {rate_eur(rate)} EUR)
      Tagungsgebühr:   GBP {eng(reg_gbp)}  (~ {eur(reg_eur)} EUR)
      Gesamt:          ca. {eur(est)} EUR aus Kostenstelle 13-6160

    Das Conference Dinner (GBP 65.00) habe ich bei der Anmeldung abgewählt; es entsteht kein
    Antrag auf Erstattung dafür. Der Preisvergleich zwischen Rückflug am Tagungsende und
    Alternativen liegt dem Flugangebot bei (kein Privataufenthalt).

    Viele Grüße
    Fridtjof Holm
---------------------------------------------------------------------------------------------------------
[2] Notiz (intern) von Reisestelle FB 13 - {de(ant)} 11:02
    Eingang vollständig: Antrag, Annahmebestätigung, Flugangebot, Hotelbuchung, Rechnung. An Fachbereich
    zur Unterschrift weitergeleitet.
"""
    hot = f"""
Booking confirmation - Old Town Lodge, 14 Candlemaker Row, Edinburgh EH1 2QE
Booking ref: OTL/9947120                    Booked: 02/07/2027 (dd/mm/yyyy)

Guest name:  Dr Fridtjof Holm
Invoice address: {UW}, FB 13 Geoinformatik, Hochschulring 21, 35291 Wernstadt, Germany
Arrival:     {uk(a)}        Departure: {uk(b)}        2 nights, single room
Rate:        GBP {eng(hotel_gbp)} per night, VAT included            Total GBP {eng(hotel_gbp * 2)}
Breakfast is not included. Free cancellation until {uk(add(a, -3))}.
"""
    inv = f"""
GSM 2027 Local Organising Committee            INVOICE No. GSM-27-0642        Date: {uk(add(ant, -9))}
Edinburgh Centre for Geoinformation, 22 Buccleuch Place, Edinburgh EH8 9LN        VAT Reg. GB 212 4421 90

Bill to: {UW}, FB 13 Geoinformatik, Hochschulring 21, 35291 Wernstadt, Germany
Delegate: Dr Fridtjof Holm (speaker, abstract ID 214)

  Description                                               Net        VAT 20%      Gross
  Registration, full delegate rate (3 days)            GBP {eng(net_gross(reg_gbp / D("1.2"), 20)[0])}   GBP {eng(net_gross(reg_gbp / D("1.2"), 20)[1])}   GBP {eng(reg_gbp)}
  Conference dinner, {uk(add(a, 1))}  -  declined                    --          --          --
  Total due                                                                          GBP {eng(reg_gbp)}
Refreshments and lunches on all three days are included in the registration fee.
"""
    docs = [doc("Ticket-2027070500264.pdf", z, margin=22, producer="Zammad", creator="wkhtmltopdf"),
            doc("hotel_booking.pdf", hot, font="Helvetica"),
            doc("INV_GSM-27-0642.pdf", inv, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m08",
         "Auslandsantrag elf Wochen vor Reisebeginn per Ticketsystem, Flug Economy, Hotel GBP 66 je Nacht mit Rechnung auf die Universität, Gebühr passt zur Rechnung. "
         "Das Conference Dinner ist abgewählt und wird nicht beantragt; kein Privataufenthalt.", docs,
         "Zammad ticket print with internal note, UK booking with dd/mm/yyyy dates, English invoice with 20 % VAT",
         "declined dinner appears in three documents; GBP amounts with stated rate; ticket shows 'Status: offen' and an internal note about forwarding",
         "Rule: „Die auf den Rechnungen ausgewiesenen Verpflegungskosten für Mittag- uns Abendverpflegung werden … nur dann erstattet, wenn es sich nachweislich um eine notwendige Pauschale handelt“ (dinner declined, lunches in fee) + „Rechnungen für Übernachtungskosten werden nur erstattet, sofern die [Universität] als Adressat angegeben ist.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m09  Spreadsheet-style form; Poland by rail (PLN, ASCII); meals inside the fee, Tagegeld cut
# --------------------------------------------------------------------------- #
def m09():
    ant = "2027-07-26"
    a, b = wk("2027-10-06", 2), wk("2027-10-08", 4)
    rate = D("4.30")          # PLN per EUR
    rail_pln, hotel_pln, reg_pln = D("259.00"), D("290.00"), D("1080.00")
    rail_eur = r2(rail_pln / rate)
    hotel_eur = r2(hotel_pln / rate)
    reg_eur = r2(reg_pln / rate)
    est = tot(rail_eur * 2, hotel_eur * 2, reg_eur)
    sheet = f"""
Dienstreise_Antrag_FB12_Vorlage-2027.xlsx   -   Tabelle1                                     Blatt 1 von 1
      |        A         |                   B                    |       C       |        D        |
------+------------------+----------------------------------------+---------------+-----------------+
   1  | ANTRAG           | Genehmigung Auslandsdienstreise        |               | {de(ant)}      |
   2  | Name             | Dr. Katarzyna Brandt-Nowak, FB 12      |               |                 |
   3  | Ziel             | Wroclaw (Breslau), POLEN               | A1 beantragt  | ja, {de(ant)}  |
   4  | Anlass           | Int. Conference on Applied Mechanics   |               |                 |
      |                  | (ICAM 2027), Vortrag Nr. 88            |               |                 |
   5  | Reisezeit        | {wds(a)} 05:48  -  {wds(b)} 21:30     |               |                 |
   6  | Dienstgeschäft   | {wds(a)} 14:00  -  {wds(b)} 13:00     |               |                 |
------+------------------+----------------------------------------+---------------+-----------------+
   7  | KOSTEN           | Position                               | PLN           | EUR (Kurs {rate_eur(rate)}) |
   8  |                  | Bahn Wernstadt - Wroclaw, einfach      | {kz(rail_pln):>9}     | {eur(rail_eur):>9}       |
   9  |                  | Bahn Wroclaw - Wernstadt, einfach      | {kz(rail_pln):>9}     | {eur(rail_eur):>9}       |
  10  |                  | Hotel 2 Nächte à PLN {kz(hotel_pln)}           | {kz(hotel_pln * 2):>9}     | {eur(hotel_eur * 2):>9}       |
  11  |                  | Tagungsgebühr (Pauschale)              | {kz(reg_pln):>9}     | {eur(reg_eur):>9}       |
  12  |                  | SUMME                                  |               | {eur(est):>9}       |
------+------------------+----------------------------------------+---------------+-----------------+
  13  | Hinweis          | Die Tagungsgebühr ist eine Tagungspauschale; sie enthält Mittagessen am 07.10. und 08.10.  |
  14  |                  | sowie das Abendessen am 06.10. und 07.10. Das Tagegeld wird nach § 10 HRKG für diese   |
  15  |                  | gestellten Mahlzeiten gekürzt; weitere Verpflegungskosten werden nicht beantragt.       |
  16  | Finanzierung     | Kostenstelle 12-3004 (Landesmittel)                                                   |
"""
    pl_reg = f"""
KONGRES ICAM 2027 - Politechnika Wroclawska-Sud - Biuro Kongresu
ul. Wybrzeze Stanislawa 15, 50-370 Wroclaw          NIP PL 899 000 12 45

FAKTURA VAT / REGISTRATION INVOICE No. 2027/10/0213           Data / Date: {iso(add(ant, -3))}
Nabywca / Bill to: {UW}, FB 12 Maschinenbau, Hochschulring 21, 35291 Wernstadt, DE
Uczestnik / Participant: Dr. Katarzyna Brandt-Nowak (speaker, paper 88)

  Opis / Description                                           Cena / Price
  Oplata konferencyjna / Conference package: sessions, 2 lunches
  (07.10., 08.10.), 2 dinners (06.10., 07.10.), coffee breaks   PLN {fr(reg_pln)}
  Podatek / VAT: 0 % (usluga wykonana poza PL - reverse charge)
  RAZEM / TOTAL                                                 PLN {fr(reg_pln)}
  Termin platnosci / Payment due: {iso(add(a, -21))}
"""
    hot = f"""
Hotel Piast *** Wroclaw   ul. Kielbasnicza 7   50-110 Wroclaw
POTWIERDZENIE REZERWACJI / BOOKING CONFIRMATION nr R-27-88104

Gosc / Guest: Katarzyna Brandt-Nowak
Faktura na / Invoice to: {UW}, FB 12 Maschinenbau, Hochschulring 21, 35291 Wernstadt
Przyjazd {iso(a)}   Wyjazd {iso(b)}   2 noce / nights, pokoj 1-os.
Cena za noc / rate per night: PLN {fr(hotel_pln)}  (w tym VAT 8 %)       Razem: PLN {fr(hotel_pln * 2)}
Sniadanie nie wliczone / breakfast not included.
"""
    docs = [doc("Reiseantrag_Breslau.pdf", sheet, margin=18),
            doc("faktura_icam.pdf", pl_reg, font="Helvetica"),
            doc("dokument2.pdf", hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m09",
         "Auslandsantrag drei Monate im Voraus (A1 beantragt), Bahnreise, Hotel PLN 290 (ca. 67 EUR). Die Tagungsgebühr ist eine nachgewiesene Pauschale mit Mahlzeiten, "
         "das Tagegeld wird dafür gekürzt, weitere Verpflegung nicht beantragt. Umrechnung zum angegebenen Kurs.", docs,
         "spreadsheet printout with cell borders and column letters, bilingual Polish/English invoice (ASCII), hotel confirmation with ISO dates",
         "meals inside the conference fee (explicit lump sum) with stated Tagegeld cut; PLN amounts with space thousands separator and a stated exchange rate",
         "Rule: „… Verpflegungskosten … werden … nur dann erstattet, wenn es sich nachweislich um eine notwendige Pauschale handelt (Tagungspauschale etc.).“ + § 10 Abs. 1 HRKG: „… so ist das Tagegeld … für das Mittag- und Abendessen um je 40 Prozent … zu kürzen.“ [" + S_DRM + ", " + S_HRKG + "]")


# --------------------------------------------------------------------------- #
# m10  paper form for a student assistant (Hilfskraft), scan look, checkbox glyphs
# --------------------------------------------------------------------------- #
def m10():
    ant = "2027-03-09"
    a = wk("2027-03-17", 2)
    fare = D("34.90")
    form = f"""
               U N I V E R S I T Ä T   W E R N S T A D T          Vordruck DR-H (Papier, nur für Hilfskräfte)
               Antrag auf Genehmigung einer Dienstreise  -  Inland
================================================================================================
1. Person
   Name, Vorname:  Sorge, Yannick                Status:  (X) wiss. Hilfskraft   ( ) stud. Hilfskraft
   Fachgebiet:     FG Experimentelle Physik, FB 15        Vertrag: 40 Std./Monat, bis 30.09.2027
2. Reise
   Reiseziel:      Leipzig                       Ausland?     ( ) ja   (X) nein
   Anlass:         Probenübergabe und Messtermin am Partnerinstitut (Projekt SPINNET, TP 2)
   Abreise:        {wds(a)}  06:40 Uhr          Rückkehr:   {wds(a)}  19:55 Uhr
   Mehrtägig:      ( ) ja   (X) nein            Übernachtung:  (X) keine
3. Verkehrsmittel
   (X) Bahn 2. Klasse   ( ) Privat-Pkw   ( ) Dienstwagen   ( ) Flug    Fahrkarte beigefügt: (X) ja  ( ) nein
4. Voraussichtliche Kosten
   Fahrtkosten Bahn hin und zurück ............  2 x {eur(fare)} = {eur(fare * 2)} EUR
   Tagegeld (Abwesenheit mehr als 8 Std.) ......  nach HRKG, bei Abrechnung
   Sonstiges ...................................  keine
5. Finanzierung      Kostenstelle:  15-8812 (Drittmittel, 6-4105)
6. Bestätigung
   Antragsteller:   {de(ant)}  Y. Sorge  (gez.)
   Dienstvorgesetzte/r (vor Antritt der Reise): ein Dienstgeschäft im dienstlichen Interesse wird bestätigt.
                    {de(add(ant, 1))}  gez. Prof. Dr. Gundula Reinsch
   Eingang Reisekostenstelle: {de(add(ant, 2))}       [ ] genehmigt     [ ] abgelehnt     (wird dort ausgefüllt)
"""
    mail = f"""
Von:      Dr. Imke Schlüter <imke.schlueter@partner-institut.example>
Gesendet: Montag, 1. März 2027 14:22
An:       Sorge, Yannick
Betreff:  Messtermin {de(a)}, 10:00 Uhr - Proben bitte persönlich mitbringen

Hallo Herr Sorge,

der Messtermin am Strahlrohr ist für Mittwoch, den {de(a)} um 10:00 Uhr bestätigt. Bitte bringen Sie die
gekühlten Proben (Transportbox, ca. 6 kg) persönlich mit; ein Versand ist wegen der Kühlkette nicht möglich.
Wir rechnen mit etwa fünf Stunden Messzeit. Ein Pförtner holt Sie am Haupteingang ab.

Beste Grüße
Imke Schlüter
"""
    tick = f"""
Online-Ticket  Auftrag 4417 8820 1135
Fahrgast: Yannick Sorge
---------------------------------------
Hinfahrt {de(a)}  Wernstadt Hbf 06:40
   -> Leipzig Hbf 10:09 (Sparpreis, 2. Kl.)
   Preis {eur(fare)} EUR
Rückfahrt {de(a)}  Leipzig Hbf 16:20
   -> Wernstadt Hbf 19:55 (Sparpreis, 2. Kl.)
   Preis {eur(fare)} EUR
---------------------------------------
Gesamt {eur(fare * 2)} EUR (MwSt 7 %)
"""
    docs = [doc("Scan_20270309_0840.pdf", form, jitter=0.9, margin=22, producer="Canon iR-ADV scanner OCR"),
            doc("Anlage_Mail_Messtermin.pdf", mail, font="Helvetica"),
            doc("Fahrkarte.pdf", tick, size=RECEIPT, margin=10)]
    case(TRIP, "dienstreiseantrag-m10",
         "Papierantrag einer Hilfskraft (dafür vorgesehene Papierform), Eintagesreise in Inland mit bestätigter Messzeit, Unterschrift der Vorgesetzten vor Reiseantritt, "
         "Bahn 2. Klasse. Felder für Genehmigung bleiben bewusst leer, weil sie von der Reisekostenstelle ausgefüllt werden.", docs,
         "scanned paper form with ( ) / (X) glyphs and OCR-clean text, Outlook-style mail, narrow online ticket",
         "unchecked approve/reject boxes ([ ] genehmigt [ ] abgelehnt) belong to the receiving office; many unchecked options elsewhere",
         "Rule: „Da die meisten Hilfskräfte keine Dienstreisen unternehmen, … stellen Hilfskräfte bitte weiterhin in Papierform [Anträge] und fügen auch Belege in Papierform bei.“ + „Dem Reiseantrag sind … alle Unterlagen … als Anlage beizufügen, aus denen das dienstliche Interesse ersichtlich ist“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m11  Professor, domestic trip <= 7 days "qua Amt" approved, created by travel assistant
# --------------------------------------------------------------------------- #
def m11():
    ant = "2027-10-04"
    a = nxt("2027-11-15", 0)
    b = add(a, 3)
    fare, hotel = D("87.40"), D("76.00")
    est = tot(fare * 2, hotel * 3)
    obj = f"""
 SAP     Reiseanträge  >  Reiseantrag 1000071044  >  Details                                  [ Bearbeiten ]
 ================================================================================================================
 Reiseantrag 1000071044            Erstellt durch: Reiseassistenz (G. Meyer-Wenzel) im Auftrag von
                                   Prof. Dr. Marit Oltmanns, Fachgebiet Wirtschaftsinformatik, FB 07
 Einverständniserklärung zur Reiseassistenz: liegt vor (Anlage 1)
 ----------------------------------------------------------------------------------------------------------------
 Status               : Gesendet am {de(ant)}, 16:02
 Genehmigung          : gilt qua Amt als genehmigt (Präsidiumsbeschluss 656 vom 21.07.2025: Inlandsdienstreise
                        einer Professorin, Dauer bis zu sieben Tage); Anzeige zur Kenntnis an die Reisestelle
 Reiseziel            : Dresden (Inland)       Dauer: {wds(a)} - {wds(b)} = 4 Tage (unter 7 Tagen)
 Anlass               : Programmbeirat und Tagung "Digitale Verwaltung 2027" (Einladung Anlage 2)
 Abwesenheit          : Abfahrt {de(a)} 06:35 Uhr · Rückkehr {de(b)} 20:05 Uhr
 ----------------------------------------------------------------------------------------------------------------
 Kosten (Planung)                                                                         EUR
   Bahn 2. Klasse hin und zurück (Sparpreis)             2 x {eur(fare)}                  {eur(fare * 2)}
   Hotel Dresden Altmarkt, 3 Nächte, Einzelzimmer        3 x {eur(hotel)}                  {eur(hotel * 3)}
   Tagungsgebühr: Mitglieder des Beirats frei                                               0,00
   Summe                                                                                    {eur(est)}
 Kostenstelle         : 07-1190   ·   Anlagen (3): Einverständniserklärung · Einladung · Hotelreservierung
"""
    ein = f"""
Einverständniserklärung zur Reiseassistenz

Hiermit erkläre ich, Prof. Dr. Marit Oltmanns, mein Einverständnis, dass Frau Gerda Meyer-Wenzel
(Sekretariat Fachgebiet Wirtschaftsinformatik) Reiseanträge und Reiseabrechnungen in meinem Namen im
SAP-Reisemanagement vorbereitet und einreicht. Die inhaltliche Verantwortung bleibt bei mir.

Wernstadt, {de(add(ant, -14))}                         Unterschrift: M. Oltmanns
"""
    inv = f"""
Fachgesellschaft Digitale Verwaltung e. V. - Geschäftsstelle Dresden
Einladung zur Sitzung des Programmbeirats                                     Dresden, 20.09.2027

Sehr geehrte Frau Prof. Oltmanns,

zur Sitzung des Programmbeirats am {WD_L[dt(add(a, 1)).weekday()]}, {de(add(a, 1))}, sowie zur Tagung "Digitale Verwaltung 2027"
am {de(add(a, 2))} und {de(b)} laden wir Sie herzlich nach Dresden ein. Die Teilnahme ist für Beiratsmitglieder
kostenfrei. Wir bitten um Anreise am {de(a)} (Beginn der Vorabendveranstaltung).

Mit freundlichen Grüßen
Dr. Lutz Hellwig
"""
    hot = f"""
Hotel Dresden Altmarkt · Reservierungsbestätigung · Vorgang 55/2027-3190
Gast: Prof. Dr. Marit Oltmanns · Rechnung an: {UW}, FB 07, Hochschulring 21, 35291 Wernstadt
{de(a)} - {de(b)} · 3 Nächte · EZ Business · {eur(hotel)} EUR pro Nacht (inkl. MwSt., ohne Frühstück)
"""
    docs = [doc("Reiseantrag_1000071044_Details.pdf", obj, font="Helvetica", margin=20),
            doc("Anlage1_Einverstaendnis.pdf", ein, font="Times-Roman"),
            doc("Anlage 2 und 3.pdf", pages(inv, hot), font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m11",
         "Inlandsreise einer Professorin über 4 Tage; die Genehmigung ergibt sich qua Amt aus dem Präsidiumsbeschluss (bis sieben Tage), die Reisestelle erhält eine Anzeige. "
         "Von der Reiseassistenz mit vorliegender Einverständniserklärung erstellt. Einladung, Hotel (76,00 EUR, Rechnung an die Universität) und Kosten vollständig.", docs,
         "SAP object page created by a travel assistant, consent form (Times), merged invitation + hotel PDF",
         "no 'Genehmigt von' name: approval is 'qua Amt'; created by assistant on behalf of the professor; fee waived for advisory-board members",
         "Rule: „Mit dem Präsidiumsbeschluss 656 vom 21.07.2025 gelten Dienstreisen … im Inland mit einer Dauer von bis sieben Tagen für Professorinnen und Professoren … grundsätzlich qua Amt als genehmigt“ + Reiseassistenz: „Die Einverständnsierklärung für die Reiseassistenz ist ebenfalls mit einzureichen.“ [" + S_DRM + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m12  general trip permit (Generelle Dienstreisegenehmigung) for repeated same-place trips
# --------------------------------------------------------------------------- #
def m12():
    ant = "2027-08-30"
    a = nxt("2027-09-14", 1)
    b = add(a, 2)
    fare, hotel = D("64.90"), D("77.00")
    est = tot(fare * 2, hotel * 2)
    antrag = f"""
Reiseantrag 1000072309 (Kurzform, Inland)                         Antragsdatum {de(ant)}     Status: gesendet
-----------------------------------------------------------------------------------------------
Reisende:        Annika Reuther, M.Sc., wiss. Mitarbeiterin, FB 11 Ökologische Agrarwissenschaften
Reiseziel:       Bremen (Inland, Partnerinstitut des Verbundprojekts GRÜNLAND-2030)
Zeitraum:        {wds(a)} 07:45 Uhr  bis  {wds(b)} 18:20 Uhr  (3 Tage)
Anlass:          Probennahme und Projekttreffen, wiederkehrendes Dienstgeschäft (Reise 4 von 9 in diesem Jahr)
Genehmigung:     Generelle Dienstreisegenehmigung Nr. GDG-27-014 (Dekan FB 11), gültig {de("2027-02-01")} bis {de("2028-01-31")},
                 für gleichartige Dienstgeschäfte in Bremen bis zu je 7 Tagen - Kopie als Anlage 1
Kosten:          Bahn 2. Kl. Sparpreis 2 x {eur(fare)} = {eur(fare * 2)}   ·   Hotel 2 Nächte x {eur(hotel)} = {eur(hotel * 2)}
                 Summe {eur(est)} EUR (Kostenstelle 11-5207, Drittmittel 6-3392)
Anlagen:         (1) generelle Genehmigung  (2) Terminbestätigung Projektpartner  (3) Bahnbuchung  (4) Hotel
"""
    gdg = f"""
Universität Wernstadt · Fachbereich 11 · Der Dekan

Generelle Dienstreisegenehmigung Nr. GDG-27-014

Frau Annika Reuther, M.Sc., wird auf Antrag vom 27.01.2027 gemäß § 2 Abs. 1 Satz 2 Hessisches Reisekostengesetz
die generelle Genehmigung erteilt, Dienstreisen zu gleichartigen Dienstgeschäften (Projekttreffen und Probennahme
im Verbundprojekt GRÜNLAND-2030) an den Ort Bremen mit einer Dauer von jeweils bis zu sieben Tagen anzutreten.
Die Genehmigung gilt vom 01.02.2027 bis zum 31.01.2028 (höchstens ein Jahr).

Wernstadt, 28. Januar 2027

gez. Prof. Dr. Ansgar Kellermann, Dekan
"""
    bahn = f"""
Ihre Buchung (PDF-Ticket)                      Auftragsnr. 77 5521 9043
Reisende: Annika Reuther
Hinfahrt:   {wds(a)}  Wernstadt Hbf 07:45  ->  Bremen Hbf 11:18   Sparpreis, 2. Kl.   {eur(fare)} EUR
Rückfahrt:  {wds(b)}  Bremen Hbf 14:44  ->  Wernstadt Hbf 18:20   Sparpreis, 2. Kl.   {eur(fare)} EUR
Gesamtpreis {eur(fare * 2)} EUR (inkl. 7 % USt.)
"""
    hot = f"""
From: booking@hotel-weserblick.example     To: a.reuther@uni-wernstadt.example
Subject: Ihre Buchung WB-77019 - Hotel Weserblick Bremen
Zimmer: Einzelzimmer, {de(a)} bis {de(add(a, 2))}, 2 Nächte à {eur(hotel)} EUR inkl. MwSt.
Rechnungsempfänger: Universität Wernstadt, FB 11, Hochschulring 21, 35291 Wernstadt
"""
    docs = [doc("Reiseantrag_1000072309.pdf", antrag, font="Helvetica", margin=22),
            doc("GDG-27-014.pdf", gdg, font="Times-Roman", producer="Microsoft Word"),
            doc("Buchung_Bahn_Hotel.pdf", pages(bahn, hot), font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m12",
         "Wiederkehrende Inlandsreisen nach Bremen sind durch eine generelle Dienstreisegenehmigung des Dekans abgedeckt (gleichartig, bis 7 Tage, höchstens ein Jahr, Kopie liegt bei). "
         "Der Einzelantrag nennt die Genehmigung, Kosten stimmen (129,80 + 154,00 EUR).", docs,
         "SAP short form (Helvetica), dean's Word letter, merged rail + hotel PDF",
         "approval is a blanket permit instead of a per-trip approval; 'Reise 4 von 9' suggests repetition",
         "Rule: „Bei Inlandsdienstreisen mit gleichartigen Dienstgeschäften an denselben Ort … mit einer Dauer von bis zu jeweils sieben Tagen kann durch die Dekaninnen/Dekane … eine generelle Dienstreisegenehmigung ausgesprochen worden. Diese Genehmigung darf längstens für die Dauer von einem Jahr ausgesprochen werden.“ [" + S_DRM + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m13  Word letter; private car at 0.21 EUR/km, colleague taken along (0.02), parking not claimed
# --------------------------------------------------------------------------- #
def m13():
    ant = "2027-04-12"
    a = nxt("2027-04-27", 1)
    one_way = 170
    km = one_way * 2
    wse = r2(D(km) * D("0.21"))
    mit = r2(D(km) * D("0.02"))
    est = tot(wse, mit)
    letter = f"""
Dr. Jonas Brandl                                                       Wernstadt, {dlong(ant)}
Fachgebiet Photovoltaik und Systemintegration (FB 13)

An die Reisekostenstelle
nachrichtlich: Dekanat FB 13

Antrag auf Genehmigung einer Dienstreise mit privatem Kraftfahrzeug

Sehr geehrte Damen und Herren,

am {wdlong(a)} muss ich zur Abnahme der Messaufbauten das Institut für Solarmodule in Stuttgart
besuchen (Termin gemäß beigefügter E-Mail, 10:00 bis 15:30 Uhr). Ich bitte um Genehmigung der Reise
mit meinem privaten Pkw.

   Strecke:           Wernstadt - Stuttgart und zurück, laut Routenplaner 2 x {one_way} km = {km} km
   Wegstreckenentschädigung:  {km} km x 0,21 EUR/km = {eur(wse)} EUR
   Mitnahme:          Mein Kollege Dipl.-Ing. Karsten Pohl fährt dienstlich mit (eigener Reiseantrag
                      1000069922). Mitnahmeentschädigung {km} km x 0,02 EUR/km = {eur(mit)} EUR
   Parkgebühren:      Das Parken beim Institut ist kostenfrei; Parkgebühren werden nicht geltend gemacht.
   Triftige Gründe:   werden nicht geltend gemacht, es wird der Grundsatz von 0,21 EUR/km beantragt.
   Wirtschaftlichkeit: Die Bahnfahrt hätte bei Flexpreis für zwei Personen 224,00 EUR gekostet (Auszug
                      anbei) und 6 Stunden Fahrzeit bedeutet; die Pkw-Fahrt ist deutlich günstiger.

   Gesamtkosten (Wegstreckenentschädigung und Mitnahme): {eur(est)} EUR, Kostenstelle 13-2288.
   Tagegeld wird mit der Abrechnung ermittelt (Abwesenheit über 8 Stunden).

Mit freundlichen Grüßen

Jonas Brandl
"""
    route = f"""
Routenplaner - Streckenübersicht                                           Ausdruck {de(ant)}
Start:  Wernstadt, Hochschulring 21          Ziel: Stuttgart, Pfaffenwaldring 47
Strecke: {one_way} km (Autobahn 87 %), Fahrzeit ca. 1 h 58 min
Rückweg: {one_way} km
Gesamt:  {km} km
Vergleich ÖPNV/Bahn (Flexpreis, 2. Kl., hin/zurück): 112,00 EUR je Person, Fahrzeit 3 h 05 min je Richtung
"""
    mail = f"""
Von: Dr. Corinna Hartleb <hartleb@isolar-stuttgart.example>
An: Brandl, Jonas
Datum: Mi, 7. April 2027 09:12
Betreff: Abnahme Messaufbau am {de(a)}

Lieber Herr Brandl, die Abnahme der beiden Messaufbauten ist am {wdlong(a)} ab 10:00 Uhr eingeplant.
Bitte kommen Sie mit Herrn Pohl direkt zum Labor 2.14; Parkplätze vor dem Haus sind für Gäste frei.
Viele Grüße, Corinna Hartleb
"""
    docs = [doc("Antrag_Pkw_Stuttgart.pdf", letter, font="Times-Roman", producer="Microsoft Word", margin=34),
            doc("routenplaner_ausdruck.pdf", route, font="Helvetica"),
            doc("Terminmail.pdf", mail, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m13",
         "Antrag auf Fahrt mit dem privaten Pkw vorab gestellt, Entfernung belegt (2 x 170 km), Satz 0,21 EUR/km ohne Berufung auf triftige Gründe, "
         "Mitnahme eines dienstreisenden Kollegen mit 0,02 EUR/km, Parkgebühren ausdrücklich nicht beantragt. 71,40 + 6,80 = 78,20 EUR.", docs,
         "Word letter (Times), route-planner print, Outlook-style appointment mail",
         "private car and parking mentioned but parking explicitly not claimed; 'triftige Gründe' explicitly not invoked; carry-along allowance",
         "Rule: „Für die Benutzung eines privaten Kraftfahrzeugs wird als Wegstreckenentschädigung ein Betrag von 0,21 € je zurückgelegtem Kilometer erstattet.“ + „Für die Mitnahme von Dienstreisenden wird eine Mitnahmeentschädigung in Höhe von 0,02 € je Kilometer gewährt.“ + „Parkgebühren werden nur erstattet, wenn die Benutzung … aus triftigen Gründen vor Antritt der Dienstreise genehmigt wurde.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m14  private car at 0.35 EUR/km with prior written approval and parking fee
# --------------------------------------------------------------------------- #
def m14():
    ant = "2027-05-10"
    a = nxt("2027-06-08", 1)
    one_way = 212
    km = 2 * one_way
    wse = r2(D(km) * D("0.35"))
    park = D("14.00")
    est = tot(wse, park)
    form = f"""
Reiseantrag Inland - PDF-Formular (ausfüllbar)  ·  Version 3.2                  Blatt 1/1
-----------------------------------------------------------------------------------------
Name ........................ Dr. Ines Wachtel          Personalnr. ... 20-5871
Einrichtung ................. FG Messtechnik und Sensorik (FB 12)
Datum des Antrags ........... {de(ant)}
Ziel ........................ Jena            Zweck: Aufbau und Inbetriebnahme von zwei Messgeräten
Beginn / Ende ............... {de(a)} 06:30 Uhr / {de(a)} 20:10 Uhr  (eintägig)
Verkehrsmittel .............. [v] privater Pkw   [ ] Bahn   [ ] Dienstfahrzeug   [ ] Flug
Triftiger Grund für Pkw ..... [v] ja (siehe unten)   [ ] nein
Vorherige Genehmigung Pkw ... [v] liegt vor: E-Mail der Reisekostenstelle vom {de(add(ant, 3))}
Kilometer ................... {km} km (2 x {one_way} km)     Satz: 0,35 EUR/km  = {eur(wse)} EUR
Parkgebühr .................. {eur(park)} EUR (Parkhaus am Institut, Beleg folgt); wegen der genehmigten Pkw-Nutzung beantragt
Begründung .................. Die beiden Messgeräte (zusammen 46 kg, empfindliche Optik) müssen
                              erschütterungsarm transportiert und am selben Tag aufgebaut werden. Bahn
                              mit Umstieg und Taxi ist nicht vertretbar.
Summe ....................... {eur(est)} EUR           Kostenstelle: 12-6102
Unterschrift ................ I. Wachtel
"""
    mail = f"""
Von:       Reisekostenstelle FB 12/14 <reisekosten-fb12@uni-wernstadt.example>
Gesendet:  Donnerstag, {dlong(add(ant, 3))}  11:48
An:        Wachtel, Ines
Betreff:   AW: Anfrage Pkw-Nutzung Dienstreise Jena am {de(a)}

Sehr geehrte Frau Dr. Wachtel,

die Nutzung Ihres privaten Kraftfahrzeugs wird aus triftigen Gründen (Transport von zwei empfindlichen
Messgeräten mit zusammen 46 kg) vor Antritt der Reise genehmigt. Es gilt somit die erhöhte
Wegstreckenentschädigung von 0,35 EUR je Kilometer; Parkgebühren werden gegen Beleg erstattet.

Bitte fügen Sie diese Mail Ihrem Reiseantrag bei.

Freundliche Grüße
i. A. Silke Rautenberg, Reisekostenstelle

----- Ursprüngliche Nachricht -----
Von: Wachtel, Ines
Gesendet: Montag, {dlong(ant)} 08:15
Betreff: Anfrage Pkw-Nutzung Dienstreise Jena am {de(a)}
Ich bitte um Genehmigung, mit dem privaten Pkw nach Jena zu fahren (Messgeräte 46 kg, siehe Antrag).
"""
    docs = [doc("Reiseantrag_Wachtel.pdf", form, margin=24),
            doc("Genehmigung_Pkw.pdf", mail, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m14",
         "Die erhöhte Wegstreckenentschädigung von 0,35 EUR/km und die Parkgebühr sind durch die ausdrücklich vor der Reise erteilte Genehmigung der Reisekostenstelle gedeckt "
         "(triftiger Grund: Transport empfindlicher 46-kg-Messgeräte). 148,40 + 14,00 = 162,40 EUR.", docs,
         "fillable-PDF style form with [v] glyphs and dotted leaders, Outlook thread with quoted request and approval",
         "0.35 EUR/km and parking fee look like an overclaim but the approval mail precedes the trip; Reisekostenstelle reply quoted above the original",
         "Rule: „Beim Vorliegen triftiger Gründe für die Kfz-Nutzung und vorheriger Genehmigung werden 0,35 € für jeden zurückgelegten Kilometer erstattet.“ + „Parkgebühren werden nur erstattet, wenn die Benutzung des privaten Kraftfahrzeugs aus triftigen Gründen vor Antritt der Dienstreise genehmigt wurde.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m15  fleet vehicle (Fuhrpark), no mileage allowance
# --------------------------------------------------------------------------- #
def m15():
    ant = "2027-05-24"
    a = nxt("2027-06-21", 0)
    b = add(a, 2)
    hotel = D("75.00")
    est = hotel * 2
    antrag = f"""
UNIVERSITÄT WERNSTADT · Abteilung Personal und Organisation · Reisekostenstelle III B
Antrag auf Genehmigung einer Dienstreise (Inland) · Ersteller: j.eisenhauer · {de(ant)} 13:20
===========================================================================================
Reisender .......... Dr.-Ing. Joachim Eisenhauer, FG Strömungsmaschinen (FB 12)
Ziel / Dauer ....... Ulm · {wds(a)} 07:00 Uhr bis {wds(b)} 18:30 Uhr (3 Tage, 2 Nächte)
Anlass ............. Aufbau der mobilen Messstrecke beim Industriepartner (Projekt TURBOMESS, AP 3)
Mitreisende ........ Dipl.-Ing. Rosalie Fink und M.Sc. David Tran (eigene Reiseanträge: 1000070188,
                     1000070190); Fahrer: Antragsteller
Verkehrsmittel ..... Dienstfahrzeug aus dem Fuhrpark der Universität (Transporter, 8 Sitze);
                     Reservierung FB-27-0386 der Fahrbereitschaft liegt bei. Die Fahrgenehmigung für das
                     Selbststeuern (Antrag mit Führerscheinkopie) ist bei der Fahrbereitschaft hinterlegt.
Wegstreckenentschädigung ... keine (Dienstfahrzeug, kein Privatfahrzeug)
Kraftstoff ......... über die Tankkarte des Fahrzeugs, keine Einzelabrechnung durch die Reisenden
Übernachtung ....... 2 Nächte x {eur(hotel)} EUR = {eur(est)} EUR (Hotel Schwabenblick, Rechnung an die Universität)
Sonstige Kosten .... keine
Gesamt (Reisekosten, ohne Tagegeld) ...... {eur(est)} EUR           Kostenstelle 12-3470 / Auftrag 6-3401
===========================================================================================
Unterschrift Reisender: J. Eisenhauer                  Unterschrift Vorgesetzte(r): ---
"""
    res = f"""
Von: fahrbereitschaft@uni-wernstadt.example
An: j.eisenhauer@uni-wernstadt.example
Betreff: Reservierungsbestätigung FB-27-0386 - Transporter 8-Sitzer
Datum: Mo, 24.05.2027 15:41

Guten Tag Herr Dr. Eisenhauer,

wir bestätigen die Reservierung des Fahrzeugs (8-Sitzer, Kennzeichen intern: WE-U 214)
vom {de(a)} (Abholung ab 06:30 Uhr) bis {de(b)} (Rückgabe bis 19:30 Uhr).
Kostenstelle für die interne Verrechnung: 12-3470. Die Fahrgenehmigung für das Selbststeuern
liegt uns vor. Die Haftung richtet sich nach den Hinweisen der Fahrbereitschaft (Schäden trägt
das Fachgebiet).

Fahrbereitschaft · Tel. intern 2120
"""
    hot = f"""
Hotel Schwabenblick · Ulm · Buchungsbestätigung 2027-0611-17
Gast: Dr.-Ing. Joachim Eisenhauer · Rechnungsempfänger: {UW}, FB 12, Hochschulring 21, 35291 Wernstadt
Zeitraum {de(a)} bis {de(b)}, 2 Nächte, Einzelzimmer, {eur(hotel)} EUR je Nacht inkl. MwSt.
"""
    docs = [doc("Antrag_Ulm_Dienstfahrzeug.pdf", antrag, margin=24),
            doc("Reservierung_Fahrbereitschaft.pdf", res, font="Helvetica"),
            doc("img0042.pdf", hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m15",
         "Gemeinsame Fahrt mit einem Dienstfahrzeug aus dem Fuhrpark: Reservierung und Fahrgenehmigung für das Selbststeuern liegen vor, es wird keine Wegstreckenentschädigung beantragt, "
         "nur zwei Hotelnächte à 75,00 EUR. Die Mitreisenden haben eigene Anträge.", docs,
         "form with dotted leaders and 'Ersteller' header (internal masks), fleet reservation mail, hotel confirmation with neutral name",
         "three travellers but one application (others have own IDs); 'Unterschrift Vorgesetzte(r): ---' empty because the application is still to be signed",
         "Rule: Fahrbereitschaft: „Um eine Fahrgenehmigung zu erhalten, ist ein „Antrag zur Genehmigung für das Selbststeuern eines universitätseigenen Kraftfahrzeuges …“ zu stellen“ (done) + „Für Bedienstete … besteht die Möglichkeit sich ein Fahrzeug aus dem Fuhrpark … zu leihen.“ [" + S_FAHR + ", " + S_DRM + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m16  hotel above 80 EUR with written justification and portal printout
# --------------------------------------------------------------------------- #
def m16():
    ant = "2027-06-14"
    a = nxt("2027-09-06", 1)
    b = add(a, 2)
    fare, hotel, ticket = D("57.90"), D("114.00"), D("29.00")
    est = tot(fare * 2, hotel * 2, ticket)
    form = f"""
Dienstreisemanagement · Neuer Antrag · Zusammenfassung (Druckansicht)              {de(ant)}
Kennung DR-2027/06/00851                                          Antragsteller: Dr. Merle Tannenhauer
================================================================================================
Einrichtung   FG Prozessanalytik, FB 14 Chemie
Zielort       Hannover (Inland)               Auslandsreise: nein
Anlass        Besuch der Fachmesse "LaborTech Nord 2027" ({wds(a)} bis {wds(b)}) und Gespräche mit Geräteherstellern
              zur Ersatzbeschaffung des GC-MS (Vorbereitung eines Beschaffungsverfahrens)
Reisezeit     {wds(a)} 07:20 Uhr - {wds(b)} 17:45 Uhr

Kosten                                                                               EUR
  Bahn 2. Klasse hin/zurück (Sparpreis)                      2 x {eur(fare)}          {eur(fare * 2)}
  Hotel, 2 Nächte                                            2 x {eur(hotel)}         {eur(hotel * 2)}
  Messeticket (Tagesticket, einmalig)                                                  {eur(ticket)}
  Summe                                                                              {eur(est)}

Begründung der Übernachtungskosten über 80,00 EUR je Nacht (Pflichtfeld):
  Während der Messe sind die Hotels im Umkreis von 10 km stark nachgefragt. Die Recherche vom
  {de(add(ant, 0))} (Ausdruck liegt bei) ergab für beide Nächte kein Zimmer unter 112,00 EUR; das gebuchte
  Hotel ist mit 114,00 EUR das günstigste mit Stornierungsmöglichkeit. Die höheren Kosten sind daher
  unvermeidbar. Ein Zimmer unter 80,00 EUR war nicht verfügbar.
================================================================================================
Datum: {de(ant)}                                         Antragsteller: M. Tannenhauer
"""
    portal = f"""
Hotelportal (Ausdruck vom {de(ant)}, 11:07)  ·  Hannover · {de(a)} - {de(b)} · 2 Nächte · 1 Gast · Umkreis Messegelände 10 km
Sortierung: Preis aufsteigend

   1.  Hotel am Messeturm ***      3,2 km     ab 112,00 EUR / Nacht    nur noch 1 Zimmer   Nicht stornierbar
   2.  City-Lodge Hannover ***     4,8 km     ab 113,00 EUR / Nacht    nur noch 2 Zimmer   Nicht stornierbar
   3.  Parkhotel Eilenriede ****   2,1 km     ab 114,00 EUR / Nacht    kostenlos stornierbar bis {de(add(a, -4))}   <- gebucht
   4.  Leine-Hotel ***             6,7 km     ab 121,00 EUR / Nacht
   5.  Congress Hotel ****         1,0 km     ab 149,00 EUR / Nacht
   6.  Alle weiteren Unterkünfte im Umkreis: ausgebucht

Preise inkl. MwSt., ohne Frühstück.
"""
    conf = f"""
Parkhotel Eilenriede · Hannover · Buchungsbestätigung 14-77120
Gast: Dr. Merle Tannenhauer     Rechnungsadresse: {UW}, FB 14 Chemie, Hochschulring 21, 35291 Wernstadt
Anreise {de(a)}, Abreise {de(b)}, 2 Nächte, Einzelzimmer Komfort, {eur(hotel)} EUR je Nacht (Messepreis, inkl. MwSt.)
Kostenfreie Stornierung bis {de(add(a, -4))}.
"""
    docs = [doc("Antrag_DR-2027-06-00851.pdf", form, margin=24),
            doc("Hotelportal-Recherche.pdf", portal, font="Helvetica"),
            doc("Buchung.pdf", conf, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m16",
         "Hotel 114,00 EUR je Nacht ist höher als 80,00 EUR, aber schriftlich als unvermeidbar begründet (Messezeitraum, Portalrecherche vom Antragstag mit allen Alternativen ab 112 EUR). "
         "Rechnung geht an die Universität. Summe 372,80 EUR stimmt.", docs,
         "intranet print view with mandatory-justification field, hotel-portal search printout, hotel confirmation",
         "price above 80 EUR/night looks like a violation but is justified in writing at application time with documented search",
         "Rule: „Darüber hinaus gehende Übernachtungskosten werden nur erstattet, wenn sie unvermeidbar waren. D. h. die Notwendigkeit ist im Einzelfall nachvollziehbar schriftlich bei Antragsstellung zu begründen.“ + „… ihre Bemühungen, eine preiswerte Unterkunft zu bekommen, im Einzelnen dokumentieren (z. B. Ausdruck eines Onlineportals …)“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m17  1st class rail on a long leg, justified (low confidence)
# --------------------------------------------------------------------------- #
def m17():
    ant = "2027-08-02"
    a = nxt("2027-09-21", 1)
    c1, c2 = D("119.00"), D("92.00")
    est = c1 * 2
    mail = f"""
Von:      Prof. Dr. Alexander Brühl-Sattler <a.bruehl-sattler@uni-wernstadt.example>
Gesendet: Montag, {dlong(ant)} 07:58
An:       Reisestelle FB 03/05 <reisestelle-fb03@uni-wernstadt.example>
Betreff:  Dienstreiseantrag Berlin {de(a)} (Gutachtersitzung) - 1. Klasse begründet

Sehr geehrte Damen und Herren,

anbei mein Antrag für eine eintägige Dienstreise nach Berlin am {wdlong(a)}: Sitzung des
Fachkollegiums (Begutachtung von Förderanträgen) von 12:00 bis 17:30 Uhr in der Geschäftsstelle der Stiftung,
Einladung anbei.

  Bahn Wernstadt Hbf - Berlin Hbf und zurück, Sparpreis 1. Klasse     2 x {eur(c1)} = {eur(est)} EUR
  (zum Vergleich 2. Klasse: 2 x {eur(c2)} EUR; Mehrpreis 1. Klasse {eur((c1 - c2) * 2)} EUR)

Begründung 1. Klasse: Die Fahrtdauer der einfachen Strecke beträgt 4 Stunden 21 Minuten und damit mehr als
zwei Stunden (§ 5 Abs. 1 HRKG). Auf der Hinfahrt muss ich 140 Seiten Antragsunterlagen
für die Sitzung vertraulich durcharbeiten, was im Großraum der 2. Klasse nicht möglich ist; die Rückfahrt dient
dem Protokoll. Darüber hinaus keine Mehrkosten: kein Hotel, keine Gebühren, Tagegeld nach HRKG.

Kostenstelle 03-1040 (Landesmittel). Mit freundlichen Grüßen
A. Brühl-Sattler
"""
    inv = f"""
Fachkollegium Sozialwissenschaften · Geschäftsstelle · Berlin
Einladung zur Sitzung am {wdlong(a)}, 12:00 Uhr (Ende ca. 17:30 Uhr)

Sehr geehrter Herr Professor Brühl-Sattler,
wir laden Sie zur Sitzung des Fachkollegiums ein. Die Tagesordnung und die Antragsunterlagen
(Verschlusssache bis zur Sitzung) senden wir Ihnen separat zu. Eine Aufwandsentschädigung ist
nicht vorgesehen; Reisekosten werden von Ihrer Einrichtung getragen.
"""
    tkt = f"""
Reiseauskunft / Preisübersicht {de(ant)}
Hinfahrt  {de(a)}  Wernstadt Hbf 06:40 - Berlin Hbf 11:01   (4 h 21 min)
Rückfahrt {de(a)}  Berlin Hbf 17:58 - Wernstadt Hbf 22:19   (4 h 21 min)
                          Sparpreis 2. Kl.   {eur(c2)} EUR je Richtung
                          Sparpreis 1. Kl.   {eur(c1)} EUR je Richtung   <- beantragt
"""
    docs = [doc("Mail_Antrag_Berlin.pdf", mail, margin=24),
            doc("Einladung_Fachkollegium.pdf", inv, font="Times-Roman"),
            doc("Preisuebersicht.pdf", tkt, font="Courier", margin=30)]
    case(TRIP, "dienstreiseantrag-m17",
         "Eintägige Reise zu einer Gutachtersitzung. Die 1. Klasse ist wegen der Fahrtdauer von über zwei Stunden pro Richtung und der Notwendigkeit, vertrauliche Unterlagen "
         "ungestört durchzuarbeiten, im Antrag begründet; der Mehrpreis ist beziffert. Ohne Honorar, kein Hotel.", docs,
         "Outlook mail print as application, foundation invitation, fare overview",
         "first-class rail claimed with written reason; 'Aufwandsentschädigung ist nicht vorgesehen' (negated)",
         "Rule: „Die Kosten für Bahnfahrten können bis zur nächst höheren Klasse erstattet werden, wenn die Fahrtdauer der einfachen Strecke mehr als zwei Stunden beträgt oder sonstige triftige Gründe vorliegen.“ [" + S_HRKG + " § 5 Abs. 1]. Doubt: the travel-management page stresses economy for flights and the HRKG phrase is a 'kann' rule.",
         conf="low")


# --------------------------------------------------------------------------- #
# m18  Fortbildung (training trip) with HR development form
# --------------------------------------------------------------------------- #
def m18():
    ant = "2027-08-16"
    a = nxt("2027-10-12", 1)
    b = add(a, 1)
    fee, hotel, fare = D("390.00"), D("72.00"), D("38.90")
    est = tot(fee, hotel, fare * 2)
    form = f"""
Universität Wernstadt                                                         Personalentwicklung (Abt. II)

ANTRAG AUF GENEHMIGUNG EINER REISE ZU FORTBILDUNGSZWECKEN
(gem. HRKG; Reisen zur Fortbildung sind Dienstreisen im dienstlichen Interesse)

1. Beschäftigte:   Mareike Oertel, Sekretariat Fachgebiet Betriebswirtschaftslehre (FB 07), E 6
2. Maßnahme:       "Haushalts- und Vergaberecht für Sekretariate, Teil 2" (2 Tage, 9:00-16:30 Uhr)
                   Veranstalter: Verwaltungsakademie Leinetal, Göttingen
                   Termin: {wds(a)} und {wds(b)}               Bildungsplan 2027, Maßnahme Nr. 14
3. Reise:          Abfahrt {wds(a)} 06:50 Uhr, Rückkehr {wds(b)} 19:40 Uhr; Bahn 2. Klasse; Ort: Göttingen
4. Dienstliches Interesse (Vorgesetzte): Die Maßnahme ist für die Beschaffungsabwicklung im Fachgebiet
                   erforderlich. Befürwortet. Prof. Dr. L. Brandes, {de(add(ant, 2))}
5. Kosten:
        Seminargebühr (umsatzsteuerfrei, Rechnung an die Universität)         {eur(fee)} EUR
        Übernachtung 1 Nacht ({de(a)} - {de(b)}), Hotel Leinebogen             {eur(hotel)} EUR
        Bahn 2. Klasse Wernstadt - Göttingen und zurück, 2 x {eur(fare)}       {eur(fare * 2)} EUR
        Summe                                                                  {eur(est)} EUR
6. Kostenstelle:    07-9000 (Fortbildungsmittel Fachbereich)
7. Unterschrift Beschäftigte: {de(ant)}  M. Oertel                 Personalentwicklung: Eingang {de(add(ant, 3))}
"""
    prog = f"""
Verwaltungsakademie Leinetal · Programm 2027/II · Seminar HV-215

Haushalts- und Vergaberecht für Sekretariate, Teil 2
Termin:    {wdl(a)} und {wdl(b)}, jeweils 9:00 bis 16:30 Uhr
Ort:       Göttingen, Akademiegebäude, Raum 3
Gebühr:    390,00 EUR je Teilnehmende/r (nach § 4 Nr. 22 UStG umsatzsteuerfrei), Unterlagen und Mittagsimbiss inklusive
Anmeldeschluss: 17.09.2027       Teilnahmebescheinigung wird ausgestellt.
"""
    docs = [doc("Fortbildungsantrag_Oertel.pdf", form, font="Times-Roman", margin=30, producer="Microsoft Word"),
            doc("Seminarprogramm_HV-215.pdf", prog, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m18",
         "Reise zur Fortbildung (Seminar im Bildungsplan) mit befürwortendem Vermerk der Vorgesetzten vor der Reise, Programm mit Termin, Ort und Gebühr, "
         "Bahn 2. Klasse, eine Hotelnacht à 72,00 EUR. Die Mittagsverpflegung ist in der Seminargebühr enthalten.", docs,
         "Word form from HR development with numbered sections, academy programme sheet",
         "no 'Dienstreise' wording: it is a 'Reise zu Fortbildungszwecken'; seminar fee without VAT (§ 4 Nr. 22 UStG); lunch included in fee",
         "Rule: „Reisen zur Fortbildung sind Reisen, die Bedienstete nach Abschluss ihrer Ausbildung zur beruflichen Weiterbildung … unternehmen.“ + „Reisekosten können nur für Dienstreisen und Reisen zur Fortbildung im dienstlichen Interesse erstattet werden, wenn diese vorher angeordnet oder genehmigt sind.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m19  advance payment (Abschlag) of exactly 80 % of the expected costs
# --------------------------------------------------------------------------- #
def m19():
    ant = "2027-09-27"
    a = nxt("2027-11-15", 0)
    b = add(a, 3)
    fare, hotel, fee = D("118.60"), D("78.00"), D("190.00")
    tg = D("14.00") * 2 + D("28.00") * 2
    total = tot(fare, hotel * 3, fee, tg)
    abschlag = r2(total * D("0.8"))
    assert abschlag > 150
    web = f"""
https://dienstreise.uni-wernstadt.example/antraege/DR-27-1344                  Gedruckt am {de(ant)} 14:22

 Reiseantrag DR-27-1344  mit Antrag auf Abschlagszahlung                      Status: eingereicht
 --------------------------------------------------------------------------------------------------
 Antragsteller      Dr. Rafael Stoltenberg-Ivanov, Institut für Kunstgeschichte (FB 05)
 Reiseziel          Berlin (Inland)       Auslandsreise: nein
 Anlass             Fachkongress "Kunstgeschichte digital", {den(a)} - {den(b)}, Vortrag in Sektion 4
 Zeitraum           {wds(a)} 08:15 bis {wds(b)} 19:30

 Voraussichtliche Reisekosten
   Bahn 2. Klasse, Sparpreis, hin/zurück                           {eur(fare):>9} EUR
   Hotel Berlin Mitte, 3 Nächte à {eur(hotel)} EUR                  {eur(hotel * 3):>9} EUR
   Kongressgebühr (Standard)                                       {eur(fee):>9} EUR
   Tagegeld § 7 HRKG: 2 Reisetage à 14,00 + 2 volle Tage à 28,00   {eur(tg):>9} EUR
   ------------------------------------------------------------------
   Zu erwartende Reisekosten gesamt                                {eur(total):>9} EUR

 Abschlag: beantragt wird ein Abschlag von 80 % der zu erwartenden
 Reisekosten = {eur(abschlag)} EUR. Der Betrag von 150,00 EUR wird überschritten. Der Abschlag wird
 innerhalb von vier Wochen nach Reiseende mit der Reisekostenabrechnung abgerechnet (Kenntnis genommen).
 Bankverbindung: wie in der Personalakte hinterlegt.
 --------------------------------------------------------------------------------------------------
 [x] Programm des Kongresses hochgeladen      [x] Hotelbuchung hochgeladen      Seite 1/1
"""
    prog = f"""
KUNSTGESCHICHTE DIGITAL 2027 · Berlin · {dlong(a)} bis {dlong(b)}
Sektion 4 (Dienstag): Digitale Editionen  ·  14:30  Stoltenberg-Ivanov (Wernstadt): "Bildkorpora und ihre
Metadaten - Erfahrungen aus drei Jahren"  ·  Teilnahmegebühr Standard: {eur(fee)} EUR (inkl. Pausenverpflegung, ohne Abendessen)
"""
    hot = f"""
Berlin Mitte Boutique-Hotel · Buchungsnummer MB-2027-90412
Gast: Rafael Stoltenberg-Ivanov · Rechnungsempfänger: {UW}, FB 05, Hochschulring 21, 35291 Wernstadt
{de(a)} - {de(b)} · 3 Nächte · {eur(hotel)} EUR je Nacht inkl. MwSt. · Frühstück nicht enthalten
"""
    docs = [doc("Antrag_DR-27-1344.pdf", web, font="Helvetica", margin=20),
            doc("Programm_Hotel.pdf", pages(prog, hot), font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m19",
         "Inlandsreise mit Antrag auf Abschlag in Höhe von genau 80 % der zu erwartenden Kosten (Summe über 150 EUR), mit dem Hinweis auf die Abrechnung innerhalb von vier Wochen "
         "nach Reiseende. Programm und Hotelbuchung (Rechnung an die Universität) liegen bei; Rechnung der Summe stimmt.", docs,
         "Chromium print of a web application with an advance-payment block, merged programme + hotel PDF",
         "advance payment ('Abschlag') on top of the trip: 80 % computed from a stated total; Tagegeld estimated with explicit rates",
         "Rule: „… kann auf Antrag ein Abschlag bis zur Höhe von 80% der zu erwartenden Reisekosten gezahlt werden. Dieser Abschlag wird allerdings nur dann angewiesen, wenn ein Betrag von 150 € überschritten wird.“ + „Abschlagszahlungen sind innerhalb von vier Wochen nach dem Ende der Dienstreise durch Vorlage der Reisekostenabrechnung abzurechnen.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m20  free guest-house accommodation accepted with prior written consent; no lodging claimed
# --------------------------------------------------------------------------- #
def m20():
    ant = "2027-05-17"
    a = nxt("2027-07-26", 0)
    b = add(a, 4)
    fare = D("79.90")
    est = fare * 2
    mail = f"""
Von:      Dr. Tobias Wendelin <t.wendelin@uni-wernstadt.example>
Gesendet: Montag, {dlong(ant)} 10:36
An:       Reisestelle FB 09/10 <reisestelle-fb09@uni-wernstadt.example>
Betreff:  Antrag Auslandsdienstreise Gent {de(a)} - {de(b)} (A1 bitte mitbeantragen)
Anlagen:  Einladung_UGent.pdf; Zustimmung_Annahme_Leistung.pdf

Sehr geehrte Damen und Herren,

ich beantrage die Genehmigung einer Dienstreise nach Gent, Belgien, zu einer Forschungswoche im Rahmen des
Kooperationsprojekts (Datenerhebung am Partnerlabor, {den(a)} bis {den(b)}). Die A1-Bescheinigung bitte ich
mitzubeantragen (Vorlauf 10 Wochen).

Hinweis zu Leistungen Dritter: Das Partnerlabor stellt mir für die vier Nächte ein Zimmer im Universitätsgästehaus
unentgeltlich zur Verfügung. Dies habe ich vor Antritt der Reise meiner Dienstvorgesetzten (Dekanin FB 09)
vollständig mitgeteilt; ihre schriftliche Zustimmung zur Annahme liegt an (Anlage 2). Ich beantrage deshalb
weder Übernachtungskosten noch das pauschale Übernachtungsgeld.

Beantragt sind ausschließlich:
   Bahn Wernstadt Hbf - Gent-Sint-Pieters und zurück, 2. Klasse, 2 x {eur(fare)} = {eur(est)} EUR
   Tagegeld nach Auslandsreisekostenverordnung (bei Abrechnung)
Kostenstelle 09-7721 (Landesmittel).

Mit freundlichen Grüßen
Tobias Wendelin
"""
    inv = f"""
Ghent University · Department of Applied Mathematics, Computer Science and Statistics
Krijgslaan 281 (S9), B-9000 Gent                                      Ghent, {den(add(ant, -22))}

Dear Dr Wendelin,

we are looking forward to your research week with us from {den(a)} to {den(b)}. As agreed, you will
work in the data lab on the 3rd floor with our team. We can offer you one of the guest rooms of the university
guest house free of charge for the four nights (this is our standard hospitality for visiting researchers;
it is not linked to any fee or service). We do not pay a fee or any other compensation, and we cannot cover
travel costs.

Kind regards,
Prof. Dr. An Verhaegen
"""
    zust = f"""
Universität Wernstadt · Fachbereich 09 · Die Dekanin

Zustimmung zur Annahme einer Leistung von dritter Seite                   Az. ZA-27-031
(Verwaltungsvorschriften zur Korruptionsbekämpfung in der Landesverwaltung)

Herr Dr. Tobias Wendelin hat mir am {de(add(ant, -4))} vor Antritt der Reise mitgeteilt, dass ihm die Ghent University
für die Dauer seines Forschungsaufenthalts ({de(a)} bis {de(b)}) eine Gästehausunterkunft ohne Entgelt überlässt.
Der Gastgeber ist Kooperationspartner im Projekt; ein Zusammenhang mit einer Vergabe, Bewertung oder
Entscheidung besteht nicht. Ich stimme der Annahme dieser Leistung im Einzelfall zu. Sie ist bei der
Reisekostenabrechnung anzugeben und wird angerechnet (es werden keine Übernachtungskosten gezahlt).

Wernstadt, {dlong(add(ant, -3))}                                   gez. Prof. Dr. Dorothea Frank-Imhof
"""
    docs = [doc("Antrag_Gent.pdf", mail, margin=24),
            doc("Einladung_UGent.pdf", inv, font="Times-Roman"),
            doc("Zustimmung_Annahme_Leistung.pdf", zust, font="Times-Roman", producer="Microsoft Word")]
    case(TRIP, "dienstreiseantrag-m20",
         "Das Partnerlabor stellt eine Gästehausunterkunft unentgeltlich; die Dienstvorgesetzte hat der Annahme vor Antritt der Reise schriftlich zugestimmt und der Antragsteller "
         "beantragt weder Übernachtungskosten noch Übernachtungsgeld. Keine Vergütung. Beantragt wird nur die Bahn (159,80 EUR) plus Tagegeld; A1 mit zehn Wochen Vorlauf.", docs,
         "Outlook mail as application with attachments list, English invitation, Word consent memo with file number",
         "free accommodation from a third party is declared and consented to in advance; 'we do not pay a fee or any other compensation' (negation)",
         "Rule: „Im Einzelfall kann die Zustimmung zur Annahme … erteilt werden. … Sie sind verpflichtet, die für die Entscheidung maßgeblichen Umstände vollständig vor Antritt der Reise mitzuteilen.“ + „Die erhaltenen Leistungen von dritter Seite werden … angerechnet.“ [" + S_DRM + "]. Doubt: a clerk may hesitate over the unusual accommodation constellation.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m21  France, French-language booking documents, EU-funded project meeting
# --------------------------------------------------------------------------- #
def m21():
    ant = "2027-02-08"
    a = nxt("2027-04-20", 1)
    b = add(a, 2)
    fare, hotel = D("54.00"), D("79.00")
    est = tot(fare * 2, hotel * 2)
    form = f"""
UNIVERSITÄT WERNSTADT · Formular DR-AUS · Antrag auf Genehmigung einer Auslandsdienstreise
------------------------------------------------------------------------------------------------
Name:            Dr. Nadine Vogelsang-Rey         Org.-Einheit:   Institut für Europäische Integration (IEI)
Antrag vom:      {de(ant)}                       Reisebeginn in:  10 Wochen
Zielland / Ort:  FRANKREICH · Straßburg           Auslandsreise:   [ja]  [  ]    A1: beantragt am {de(ant)}
Veranstaltung:   Konsortialtreffen "EUREKA-Civics" (Horizon Europe, GA 101-77-4-0052), Work Package 3
Zeit:            {wdl(a)} 06:50 - {wdl(b)} 20:30; Treffen {de(a)} 14:00 bis {de(b)} 12:30
Kosten:          Bahn 2. Kl. Wernstadt - Straßburg und zurück  2 x {eur(fare)} EUR
                 Hotel 2 Nächte x {eur(hotel)} EUR (Hotel de la Cathédrale, ohne Frühstück)
                 Summe {eur(est)} EUR
Finanzierung:    EU-Projekt, Auftrag 6-4419 (Reisekostenbudget WP 3). Der Geldgeber lässt keine abweichenden
                 Erstattungsregeln zu; es gelten die Regelungen der Universität.
Anlagen:         Einladung des Koordinators · Fahrkarte · Hotelbestätigung
Unterschrift:    N. Vogelsang-Rey
"""
    bil = f"""
VOTRE BILLET ELECTRONIQUE · Dossier 3Q8XK2 · Emis le {dfr(add(ant, -1))}
Voyageur : VOGELSANG-REY / NADINE            Classe : 2e classe              Tarif : Prem's
Aller    : {dfr(a)}   Wernstadt Hbf 06:50 -> Strasbourg 10:41     {fr(fare)} EUR
Retour   : {dfr(b)}   Strasbourg 17:19 -> Wernstadt Hbf 20:30     {fr(fare)} EUR
Montant total TTC : {fr(fare * 2)} EUR  (TVA 10 % incluse)       Billet non echangeable
"""
    hot = f"""
HOTEL DE LA CATHEDRALE - 8 rue des Orfevres - 67000 Strasbourg
CONFIRMATION DE RESERVATION n° 27-0419-0083

Client : Dr Nadine Vogelsang-Rey
Facture a etablir au nom de : {UW}, Institut fuer Europaeische Integration, Hochschulring 21, 35291 Wernstadt (Allemagne)
Arrivee : {dfr(a)}      Depart : {dfr(b)}      2 nuits, chambre simple
Tarif : {fr(hotel)} EUR la nuit, TVA 10 % incluse - petit-dejeuner non inclus      Total : {fr(hotel * 2)} EUR
Annulation gratuite jusqu'au {dfr(add(a, -2))}.
"""
    inv = f"""
EUREKA-Civics · Consortium meeting · WP3 Strasbourg
Coordinator: Prof. Hélène Marchetti (Université de Strasbourg-Nord)

Dear partners, the third consortium meeting takes place on {wden(a)} (14:00-18:00) and
{wden(b)} (09:00-12:30), at the Maison de l'Europe, Strasbourg. Please book your own travel and
accommodation according to your institution's rules; travel costs are covered from the WP3 travel budget
of each partner. Lunch on {WD_ENL[dt(b).weekday()]} is provided by the host.
"""
    docs = [doc("DR-AUS_Antrag_Strassburg.pdf", form, margin=22),
            doc("billet.pdf", bil, font="Helvetica"),
            doc("reservation-hotel-fr.pdf", hot, font="Helvetica"),
            doc("invitation_consortium.pdf", inv, font="Times-Roman")]
    case(TRIP, "dienstreiseantrag-m21",
         "Auslandsantrag zehn Wochen im Voraus für ein EU-Konsortialtreffen, A1 gleichzeitig beantragt. Fahrkarte und Hotelbestätigung (79,00 EUR je Nacht, Rechnung auf die Universität) "
         "französisch; Finanzierung aus Drittmitteln ohne abweichende Geberregeln, der vom Gastgeber gestellte Lunch wird vom Tagegeld abgezogen.", docs,
         "German form with [ja]/[  ] boxes, French e-ticket and hotel confirmation (ASCII), English consortium note",
         "French-language bookings (billet, TVA, nuits); EU-grant funded; host-provided lunch mentioned only in the invitation",
         "Rule: „Reisen aus Drittmitteln unterliegen grundsätzlich den gleichen Regelungen wie Reisen aus Landesmitteln.“ [" + S_GLOS + "] + „Rechnungen für Übernachtungskosten werden nur erstattet, sofern die [Universität] als Adressat angegeben ist.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m22  day trip, rail booked via the corporate customer portal with 5 % discount lines
# --------------------------------------------------------------------------- #
def m22():
    ant = "2027-06-07"
    a = nxt("2027-06-30", 2)
    p1, p2 = D("40.00"), D("40.00")
    d1, d2 = r2(p1 * D("0.05")), r2(p2 * D("0.05"))
    est = tot(p1 - d1, p2 - d2)
    web = f"""
Intranet · Dienstreisen · Kurzantrag Tagesreise                                            {de(ant)}  15:33
--------------------------------------------------------------------------------------------------------
Name             Tamara Eilers · Referentin Studium und Lehre (Abt. IV)
Ziel             Frankfurt am Main (Inland)             Auslandsreise:  nein
Anlass           Arbeitstreffen der hessischen Hochschulen zur Studiengangsentwicklung ({wdl(a)}, 10:30-15:30 Uhr)
Abfahrt/Ankunft  {de(a)} 07:55 / {de(a)} 18:40
Mehrtägig        nein            Privataufenthalt  keiner
Ticket           über das Firmenkundenportal der DB gebucht (Kundennummer der Universität hinterlegt;
                 keine private BahnCard vorhanden). Preise inkl. 5 % Firmenkundenrabatt.
Kosten           2 x Sparpreis 2. Klasse                                                   {eur(est)} EUR
Kostenstelle     IV-0110
Hinweis          Tagegeld wird bei der Abrechnung ermittelt (Abwesenheit mehr als 8 Stunden).
--------------------------------------------------------------------------------------------------------
Anlagen: Einladung vom 19.05.2027 (PDF) · Buchungsbestätigung Firmenkundenportal (PDF)         [Antrag speichern]
"""
    buch = f"""
Deutsche Bahn · Firmenkundenportal                                    Buchungsbestätigung
Kundennummer (Universität): 77 31 904 188             Buchungsdatum: {uk(add(ant, 0))}
Reisende: Tamara Eilers
  Pos  Reise                                          Preis        Rabatt 5 %       Zu zahlen
   1   {de(a)} Wernstadt Hbf 07:55 - Frankfurt Hbf 09:21     {eur(p1)}         -{eur(d1)}          {eur(p1 - d1)}
       Sparpreis, 2. Klasse
   2   {de(a)} Frankfurt Hbf 16:34 - Wernstadt Hbf 18:40     {eur(p2)}         -{eur(d2)}          {eur(p2 - d2)}
       Sparpreis, 2. Klasse
  Gesamt vor Rabatt {eur(p1 + p2)} EUR · Rabatt gesamt -{eur(d1 + d2)} EUR · Zu zahlen {eur(est)} EUR
  Zahlung mit persönlicher Kreditkarte; enthaltene USt. 7 %.
"""
    inv = f"""
Hessisches Ministerium - Hochschulabteilung (Referat Studium und Lehre)
Betreff: Arbeitstreffen Studiengangsentwicklung am {de(a)}

Sehr geehrte Damen und Herren,
wir laden Sie zum Arbeitstreffen am {wdl(a)}, 10:30 bis 15:30 Uhr, in unser Haus (Frankfurt) ein.
Eine Anmeldung ist nicht erforderlich. Mittagsimbiss ist nicht vorgesehen.
"""
    docs = [doc("Kurzantrag_Eilers.pdf", web, font="Helvetica", margin=22, creator="Chromium"),
            doc("Buchung_Firmenkundenportal.pdf", buch, font="Courier", margin=22),
            doc("Einladung Arbeitstreffen.pdf", inv, font="Times-Roman")]
    case(TRIP, "dienstreiseantrag-m22",
         "Eintägige Inlandsreise, Bahn über das Firmenkundenportal mit 5 % Firmenkundenrabatt (negative Rabattzeilen), Kosten nach Rabatt 76,00 EUR. "
         "Keine private BahnCard, keine Übernachtung, kein Mittagsimbiss.", docs,
         "intranet short form (Helvetica), booking confirmation with discount columns (negative amounts), ministry invitation letter",
         "booking table lists gross prices, '-2,00' discount lines and net payable; claim equals the discounted total",
         "Rule: „Der Firmenkundenrabatt in Höhe von 5 % wird bei Buchungen über das Firmenkundenportal automatisch berücksichtigt.“ + „Sofern Sie im Besitz einer privaten BahnCard sind ist diese zwingend für Dienstreisen einzusetzen.“ (none owned) [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m23  English UI; journey the day before is justified by the earliest arrival time
# --------------------------------------------------------------------------- #
def m23():
    ant = "2027-09-13"
    conf_start = nxt("2027-10-18", 0)
    dep = add(conf_start, -1)
    end = add(conf_start, 1)
    fare, hotel = D("88.40"), D("76.00")
    est = tot(fare * 2, hotel * 2)
    form = f"""
SAP S/4HANA  ·  Employee Self-Service  ·  My Trips  >  New Trip Request                  English (EN)  |  Deutsch
==========================================================================================================
Trip No. 1000073120                       Created {den(ant)}                        Status: Submitted
Employee                                  Dr. Oliver Fröhlich, Department of Applied Geoscience, FB 14
Trip type                                 Domestic trip (Germany)
Destination                               Konstanz
Business purpose                          Workshop "Remote Sensing of Lakes" (WRSL 2027), {den(conf_start)}, 08:30 to {den(end)}, 17:00;
                                          talk on {den(conf_start)}, 11:20 (programme attached)
Departure / return                        {wden(dep)}, 15:48    /    {wden(end)}, 17:40 (departure from Konstanz) -> home 22:50
Justification for travelling on the day before the event:
   The workshop starts at 08:30. With a departure on the morning of {den(conf_start)} the earliest possible
   arrival in Konstanz is 12:40, i.e. after the start of the first session and after my own talk.
   Arrival on {WD_ENL[dt(dep).weekday()]} evening (21:20) is therefore necessary. (Sunday travel: working-time rules for
   travel days applied.)
----------------------------------------------------------------------------------------------------------
Cost estimate                                              Qty      Unit price        Total (EUR)
   Rail Wernstadt Hbf <-> Konstanz, 2nd class, Sparpreis     2         {eng(fare):>7}         {eng(fare * 2):>7}
   Hotel Konstanz, nights {iso(dep)} and {iso(conf_start)}         2         {eng(hotel):>7}         {eng(hotel * 2):>7}
   Workshop fee                                              --       free of charge       0.00
   Total                                                                                   {eng(est):>7}
Cost centre 14-3302            Attachments: programme (PDF), rail booking (PDF), hotel booking (PDF)
"""
    prog = f"""
WRSL 2027 · Workshop "Remote Sensing of Lakes" · Konstanz
Monday, {den(conf_start)}   08:30 Welcome   09:00 Keynote   11:20 O. Fröhlich (Wernstadt): "Chlorophyll from space: ..."
Tuesday, {den(end)}   09:00 Session 4   14:00 Poster   17:00 Close
Participation is free of charge for all registered participants (limited seats). Lunch is not provided.
"""
    bahn = f"""
Buchung 5 0033 718 441 · Sparpreis · 2. Klasse · Reisender O. FRÖHLICH
{wds(dep)}  Wernstadt Hbf 15:48  ->  Konstanz 21:20      {eur(fare)} EUR
{wds(end)}  Konstanz 17:40  ->  Wernstadt Hbf 22:50      {eur(fare)} EUR
Gesamt {eur(fare * 2)} EUR (inkl. 7 % USt.)
Hinweis: Eine Fahrt am Montagmorgen (frühester Zug ab 06:45) erreicht Konstanz erst um 12:40 Uhr.
"""
    hot = f"""
Hotel Seeblick Konstanz · Reservierung 2027/118
Gast: Dr. Oliver Fröhlich · Rechnung an: {UW}, FB 14 Geowissenschaften, Hochschulring 21, 35291 Wernstadt
{de(dep)} bis {de(end)} · 2 Nächte · Einzelzimmer · {eur(hotel)} EUR je Nacht inkl. MwSt., Frühstück separat (nicht gebucht)
"""
    docs = [doc("Trip_1000073120_EN.pdf", form, font="Helvetica", margin=20),
            doc("programme.pdf", prog, font="Helvetica"),
            doc("Buchungen.pdf", pages(bahn, hot), font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m23",
         "Anreise am Vortag (Sonntag) ist im Antrag begründet: bei Abfahrt am Konferenztag wäre die Ankunft erst um 12:40 Uhr, nach Beginn und nach dem eigenen Vortrag. "
         "Zwei Hotelnächte à 76,00 EUR, Rechnung an die Universität, Bahn 2. Klasse, Workshop kostenlos.", docs,
         "SAP S/4HANA ESS page in English UI (justification field), programme sheet, merged rail + hotel PDF",
         "Sunday departure, two hotel nights for a two-day workshop: explained by the first-train arrival time; mixed German/English",
         "Rule: „Erstattungsfähig sind nur dienstlich veranlasste und zur Durchführung des Dienstgeschäfts notwendige Kosten.“ + „Nachgewiesene Übernachtungskosten sind bis zu einer Höhe von 80,00 € je Nacht erstattungsfähig.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m24  Latvia: flight with comparison, EasyChair-like acceptance, hotel invoice in two languages
# --------------------------------------------------------------------------- #
def m24():
    ant = "2027-06-21"
    a = nxt("2027-09-13", 0)
    b = add(a, 3)
    flight, hotel, reg = D("156.00"), D("62.00"), D("250.00")
    est = tot(flight, hotel * 3, reg)
    form = f"""
Dienstreise - Auslandsantrag (Word-Vorlage FB 16, Stand 2027-01)

Reise ins Ausland?     [ ja ]   [    ]                   Datum des Antrags:  {de(ant)}  (11 Wochen vor Reisebeginn)
Name:                  Dr. Sunita Rao-Nagel, Fachgebiet Verteilte Sensorsysteme
Reiseziel:             Riga, Lettland
Veranstaltung:         Baltic Sensor Networks Workshop (BSNW 2027), {dlong(a)} bis {dlong(b)} - Posterpräsentation
Verkehrsmittel:        Flug (Economy) Frankfurt - Riga - Frankfurt
Flugkosten-Vergleich:  Rückflug direkt nach Ende des Dienstgeschäfts ({de(b)}, 17:35): {eur(flight)} EUR.
                       Dieser Flug wird gebucht, es gibt keinen Privataufenthalt. Bahn/Bus zum Ziel unter 30 Stunden nicht möglich.
A1-Bescheinigung:      beantragt am {de(ant)}

Kostenplan:            Flug Economy                                    {eur(flight):>8} EUR
                       Hotel 3 Nächte x {eur(hotel)} EUR              {eur(hotel * 3):>8} EUR
                       Workshopgebühr (Early Bird)                     {eur(reg):>8} EUR
                       Summe                                           {eur(est):>8} EUR
Finanzierung:          Kostenstelle 16-0415 / Auftrag 6-3688 (Drittmittel)

Unterschrift Antragstellerin: S. Rao-Nagel                Unterschrift Fachgebietsleitung: ---
"""
    acc = f"""
BSNW 2027 - Submission system (EasyChair-style)  ·  Notification for submission 57
Dear Sunita Rao-Nagel,

we are happy to inform you that your poster "Duty Cycling under Energy Harvesting Uncertainty" has been accepted
for presentation at BSNW 2027 (Riga, {den(a)}-{den(b)}). At least one author must register by {den(add(ant, 40))}.
The early-bird fee is EUR {eng(reg)} (VAT reverse charge applies for institutions with a VAT ID).
Presenters are not paid a fee; there is no travel support this year. The social dinner on {den(add(a, 1))} is
optional and charged separately (EUR 55); please state at registration whether you will attend.

Best wishes, the BSNW 2027 programme chairs
"""
    flug = f"""
E-TICKET RECEIPT / ITINERARY                                  Booking ref. R7P2LM
Passenger: RAONAGEL/SUNITA MS                                 Date of issue: {den(add(ant, 1))}

BJ 311   {den(a)}    FRA 07:10 -> RIX 10:45     Economy L
BJ 312   {den(b)}    RIX 17:35 -> FRA 19:20     Economy L        (return directly after the workshop)

Air fare EUR {eng(D("109.00"))}   Taxes/fees EUR {eng(D("47.00"))}   TOTAL EUR {eng(flight)}
Comparison fare for return on the following day ({den(add(b, 1))}): EUR 156.00 (same fare, no saving) - not booked.
"""
    hot = f"""
HOTEL ZELTA ROZE · Riga · Brivibas iela 41 · LV-1050
REKINS / INVOICE-CONFIRMATION nr. ZR-2027-3312

Viesis / Guest: Sunita Rao-Nagel
Maksatajs / Bill to: {UW}, FB 16 Elektrotechnik/Informatik, Hochschulring 21, 35291 Wernstadt, Germany
Naktis / nights: 3 ({iso(a)} - {iso(b)})   Cena par nakti / rate: EUR {eng(hotel)} (PVN/VAT 12 % included)   Kopa / total: EUR {eng(hotel * 3)}
Brokastis / breakfast: not included.
"""
    docs = [doc("Auslandsantrag_Riga.pdf", form, font="Times-Roman", margin=34, producer="Microsoft Word"),
            doc("notification_submission57.pdf", acc, font="Helvetica"),
            doc("ticket_BJ311.pdf", flug, font="Helvetica"),
            doc("hotel_rekins.pdf", hot, font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m24",
         "Flug nach Riga mit schriftlichem Preisvergleich (Rückflug direkt nach Dienstgeschäftsende zum gleichen Preis), Posterannahme, kein Honorar und keine Förderung, "
         "optionales Social Dinner nicht gebucht. A1 mit elf Wochen Vorlauf. Hotelrechnung auf die Universität. Summe 592,00 EUR.", docs,
         "Word template with [ ja ]/[   ] boxes, EasyChair-style notification, itinerary receipt, bilingual Latvian/English invoice (ASCII)",
         "optional social dinner (EUR 55) only mentioned as optional and absent from the cost plan; 'not paid a fee' (negated); flight comparison states 'same fare, no saving'",
         "Rule: „Bei Flugreisen ist dem Dienstreiseantrag ein Preisvergleich beizufügen. Daraus sollte hervorgehen, wie hoch die Kosten für einen Flug gewesen wären, wenn die Rückreise direkt nach Beendigung des Dienstgeschäftes angetreten würde.“ + „Erstattungsfähig ist ausschließlich die Economy Class.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m25  waiver of Tagegeld and lodging allowance; only the rail fare claimed
# --------------------------------------------------------------------------- #
def m25():
    ant = "2027-10-11"
    a = nxt("2027-11-23", 1)
    b = add(a, 1)
    fare = D("73.40")
    est = fare * 2
    letter = f"""
Dr. Wiebke Hartung-Sengel, Akademische Rätin                                Wernstadt, {dlong(ant)}
Institut für Bildungsforschung (FB 02)

An die Reisekostenstelle FB 01/02

Antrag auf Genehmigung einer Dienstreise nach Berlin ({de(a)} bis {de(b)})

Sehr geehrte Damen und Herren,

ich bitte um Genehmigung einer Dienstreise nach Berlin zur Jahrestagung der Gesellschaft für Empirische
Bildungsforschung (Programm und Zusage zu meinem Beitrag liegen an). Die Tagung findet am {wdl(a)}
und {wdl(b)} statt; ich fahre am {de(a)} um 06:15 Uhr ab und kehre am {de(b)} gegen 21:30 Uhr zurück.

Kosten: Bahnfahrt 2. Klasse, Sparpreis, hin und zurück, 2 x {eur(fare)} = {eur(est)} EUR (Kostenstelle 02-4416).
Ich übernachte bei Verwandten in Berlin. Auf Tagegeld und Übernachtungsgeld verzichte ich für diese
Reise (siehe beiliegende Verzichtserklärung), beantragt wird daher ausschließlich die Erstattung
der Fahrtkosten. Honorar oder sonstige Leistungen Dritter erhalte ich nicht.

Mit freundlichen Grüßen
Wiebke Hartung-Sengel
"""
    verz = f"""
Verzichtserklärung (Reisekosten)

Ich, Dr. Wiebke Hartung-Sengel, verzichte für die Dienstreise nach Berlin vom {de(a)} bis {de(b)} (Tagung der
Gesellschaft für Empirische Bildungsforschung) rechtswirksam und endgültig auf die Erstattung von

   [x] Tagegeld          [x] Übernachtungsgeld (pauschal)          [ ] Fahrtkosten

Eine Reisekostenabrechnung ist insoweit ausgeschlossen. Die Fahrtkosten werden ausdrücklich nicht
verzichtet, sondern abgerechnet.

Wernstadt, {de(ant)}                         Unterschrift: W. Hartung-Sengel
"""
    prog = f"""
GEB-Jahrestagung 2027 · Berlin · Programmübersicht (Auszug)
{WD_L[dt(a).weekday()]}, {de(a)}   13:30-15:00  Symposium 7: Lernverläufe im Grundschulalter
                       14:15  W. Hartung-Sengel (Wernstadt): "Förderdiagnostik im Längsschnitt"
{WD_L[dt(b).weekday()]}, {de(b)}  09:00-12:00  Postersession · 12:00 Abschluss
Tagungsbeitrag: 0,00 EUR (Mitgliedsinstitutionen).
"""
    bahn = f"""
Ticket-Bestätigung                              Auftrag 6 61 10 4478
Fahrgast: W. HARTUNG-SENGEL
Hinfahrt  {de(a)}  Wernstadt Hbf 06:15 -> Berlin Hbf 10:48    Sparpreis 2. Kl.  {eur(fare)} EUR
Rückfahrt {de(b)}  Berlin Hbf 17:12 -> Wernstadt Hbf 21:30    Sparpreis 2. Kl.  {eur(fare)} EUR
Summe {eur(est)} EUR
"""
    docs = [doc("Antrag_Berlin.pdf", letter, font="Times-Roman", producer="Microsoft Word", margin=34),
            doc("Verzicht.pdf", verz, font="Times-Roman", margin=34),
            doc("Programm_Fahrkarte.pdf", pages(prog, bahn), font="Helvetica")]
    case(TRIP, "dienstreiseantrag-m25",
         "Inlandsreise, bei der die Antragstellerin ausdrücklich auf Tagegeld und Übernachtungsgeld verzichtet (unterschriebene Verzichtserklärung); beantragt werden nur die Bahnkosten "
         "(146,80 EUR). Keine Hotelkosten, kein Honorar, Tagungsbeitrag entfällt.", docs,
         "Word letter, one-page waiver with [x]/[ ] boxes, merged programme + rail ticket PDF",
         "waiver of allowances: no hotel, no per diem, only fare; checkbox 'Fahrtkosten' stays unchecked in the waiver (they are NOT waived)",
         "Rule: „Auf die Erstattung von Reisekosten kann ganz oder teilweise rechtswirksam verzichtet werden. Eine Reisekostenabrechnung ist damit ausgeschlossen.“ [" + S_DRM + "]",
         conf="medium")


# =========================================================================== #
# PROCUREMENT  (beschaffungsantrag-m26 .. m50)
# =========================================================================== #
def calc(items, vat=19, discount_pct=0, shipping=0):
    """items: list of (desc, qty, unit_net) -> dict with line totals, discount, net, vat, gross"""
    lines = [(d, q, D(u), r2(D(q) * D(u))) for d, q, u in items]
    sub = r2(sum(l[3] for l in lines))
    disc = r2(sub * D(discount_pct) / 100) if discount_pct else D("0.00")
    ship = r2(D(shipping))
    net = r2(sub - disc + ship)
    v = r2(net * D(vat) / 100)
    return dict(lines=lines, sub=sub, disc=disc, ship=ship, net=net, vat=v, gross=r2(net + v), rate=vat,
                disc_pct=discount_pct)


def _vendor_head(v):
    return [v["name"], v["street"], v["city"]] + ([v["contact"]] if v.get("contact") else [])


def quote_classic(v, no, date_, valid, to_lines, c, title="Angebot", note=""):
    """German classic: vendor block right, recipient left, table below"""
    head = two("\n".join(to_lines), "\n".join(_vendor_head(v)), 100)
    rows = [["Bezeichnung", "Menge", "Einzelpreis netto", "Gesamt netto"]]
    for d, q, u, t in c["lines"]:
        rows.append([d, q, f"{eur(u)} €", f"{eur(t)} €"])
    tab = grid(rows, [56, 6, 18, 16], ["l", "r", "r", "r"], indent=1)
    sums = [f"Summe netto{' ' * 4}{eur(c['sub'])} €"]
    if c["disc"]:
        sums.append(f"abzgl. {c['disc_pct']} % Rabatt   -{eur(c['disc'])} €")
    if c["ship"]:
        sums.append(f"Fracht / Versand netto   {eur(c['ship'])} €")
    sums.append(f"Angebotssumme netto   {eur(c['net'])} €")
    sums.append(f"zzgl. {c['rate']} % USt.   {eur(c['vat'])} €")
    sums.append(f"Angebotssumme brutto   {eur(c['gross'])} €")
    sm = "\n".join(" " * 60 + s for s in sums)
    return f"""
{head}


{"Angebot".replace("Angebot", title)} Nr. {no}                                            Datum: {de(date_)}
Bindefrist: {de(valid)}

Wir danken für Ihre Anfrage und bieten Ihnen freibleibend an:

{tab}

{sm}
{note}
Mit freundlichen Grüßen
{v["name"]}
"""


def quote_en(v, no, date_, valid, to_lines, c, note="", cur="EUR"):
    rows = [["Pos", "Description", "Qty", "Unit price", "Amount"]]
    for i, (d, q, u, t) in enumerate(c["lines"], 1):
        rows.append([i, d, q, f"{eng(u)}", f"{eng(t)}"])
    tab = grid(rows, [3, 52, 4, 11, 12], ["r", "l", "r", "r", "r"])
    s = [f"Subtotal {cur} {eng(c['sub'])}"]
    if c["disc"]:
        s.append(f"Discount {c['disc_pct']} % -{eng(c['disc'])}")
    if c["ship"]:
        s.append(f"Carriage {eng(c['ship'])}")
    s.append(f"Total net {cur} {eng(c['net'])}")
    s.append(f"VAT {c['rate']} % {eng(c['vat'])}")
    s.append(f"TOTAL {cur} {eng(c['gross'])}")
    return f"""
{v["name"].upper()}
{" · ".join(_vendor_head(v)[1:])}

QUOTATION {no}                                                  Date: {den(date_)}
Valid until: {den(valid)}
To: {" / ".join(to_lines)}

{tab}

{chr(10).join(" " * 44 + x for x in s)}
{note}
Terms: net 30 days. Delivery as per quotation, prices ex works unless stated.
"""


def quote_mail(v, no, date_, to_name, c, subj, note=""):
    lines_ = [f"   {i}. {d}: {q} x {eur(u)} EUR = {eur(t)} EUR" for i, (d, q, u, t) in enumerate(c["lines"], 1)]
    extra = []
    if c["disc"]:
        extra.append(f"   Rabatt {c['disc_pct']} %: -{eur(c['disc'])} EUR")
    if c["ship"]:
        extra.append(f"   Versand: {eur(c['ship'])} EUR")
    return f"""
Von:      {v.get('contact_name', 'Vertrieb')} <{v['mail']}>
Gesendet: {WD_L[dt(date_).weekday()]}, {dlong(date_)} 09:47
An:       {to_name}
Betreff:  {subj}

Guten Tag,

vielen Dank für Ihre Anfrage. Gern bieten wir Ihnen wie folgt an (Angebot {no}):

{chr(10).join(lines_)}
{chr(10).join(extra)}
   Summe netto {eur(c['net'])} EUR, zzgl. {c['rate']} % USt. {eur(c['vat'])} EUR, brutto {eur(c['gross'])} EUR
{note}
Das Angebot ist freibleibend und gilt 30 Tage. Lieferzeit nach Absprache.

Freundliche Grüße
{v.get('contact_name', 'Vertrieb')}
{v['name']}
"""


def quote_letter(v, no, date_, to_lines, c, subject, intro="", note=""):
    pos = []
    for i, (d, q, u, t) in enumerate(c["lines"], 1):
        pos.append(f"  Position {i}: {d}")
        pos.append(f"      {q} Stück zum Einzelpreis von {eur(u)} EUR netto, zusammen {eur(t)} EUR netto")
    extra = ""
    if c["disc"]:
        extra += f"\n  Nachlass von {c['disc_pct']} % (= {eur(c['disc'])} EUR) ist bereits berücksichtigt."
    if c["ship"]:
        extra += f"\n  Frachtkosten: {eur(c['ship'])} EUR netto."
    return f"""
{v["name"]} · {v["street"]} · {v["city"]}


{chr(10).join(to_lines)}


{v["city"].split()[-1]}, {dlong(date_)}

Ihre Anfrage vom {de(add(date_, -6))} - unser Angebot Nr. {no}

{subject}

{W(intro or "Sehr geehrte Damen und Herren, wir bedanken uns für Ihr Interesse und unterbreiten Ihnen folgendes Angebot:", 90)}

{chr(10).join(pos)}{extra}

  Angebotspreis netto {eur(c['net'])} EUR, Umsatzsteuer {c['rate']} % {eur(c['vat'])} EUR, insgesamt {eur(c['gross'])} EUR.
{note}
Wir würden uns über Ihren Auftrag freuen und stehen für Rückfragen gern zur Verfügung.

Mit freundlichen Grüßen
i. A. {v.get('contact_name', 'Vertrieb')}
"""


def quote_fr(v, no, date_, valid, to_lines, c, note=""):
    rows = [["Désignation", "Qté", "Prix unitaire HT", "Total HT"]]
    for d, q, u, t in c["lines"]:
        rows.append([d, q, f"{fr(u)} EUR", f"{fr(t)} EUR"])
    tab = grid(rows, [52, 5, 18, 16], ["l", "r", "r", "r"])
    return f"""
{v["name"]} - {v["street"]} - {v["city"]}

DEVIS n° {no}                                               Date : {dfr(date_)}
Valable jusqu'au : {dfr(valid)}
Client : {" / ".join(to_lines)}

{tab}

{" " * 40}Total HT          {fr(c['net'])} EUR
{" " * 40}TVA {c['rate']} %        {fr(c['vat'])} EUR
{" " * 40}Total TTC         {fr(c['gross'])} EUR
{note}
Conditions : paiement à 30 jours net. Livraison franco de port à partir de 500 EUR HT.
"""


def quote_it(v, no, date_, valid, to_lines, c, note="", iva_note=""):
    rows = [["Descrizione", "Q.ta", "Prezzo unitario", "Importo"]]
    for d, q, u, t in c["lines"]:
        rows.append([d, q, f"{eur(u)} EUR", f"{eur(t)} EUR"])
    tab = grid(rows, [52, 5, 18, 16], ["l", "r", "r", "r"])
    s = [f"Imponibile lordo   {eur(c['sub'])} EUR"]
    if c["disc"]:
        s.append(f"Sconto {c['disc_pct']} %         -{eur(c['disc'])} EUR")
    s.append(f"Totale netto       {eur(c['net'])} EUR")
    s.append(f"IVA {c['rate']} %          {eur(c['vat'])} EUR")
    s.append(f"Totale             {eur(c['gross'])} EUR")
    return f"""
{v["name"]}
{v["street"]} - {v["city"]}

PREVENTIVO n. {no}                                          del {dit(date_)}
Validita: fino al {dit(valid)}
Spett.le {" / ".join(to_lines)}

{tab}

{chr(10).join(" " * 40 + x for x in s)}
{iva_note}
{note}
Condizioni: pagamento a 30 giorni data fattura. Resa DAP.
"""


def quote_nl(v, no, date_, valid, to_lines, c, note=""):
    rows = [["Omschrijving", "Aantal", "Prijs per stuk", "Totaal"]]
    for d, q, u, t in c["lines"]:
        rows.append([d, q, f"€ {eur(u)}", f"€ {eur(t)}"])
    tab = grid(rows, [50, 7, 16, 16], ["l", "r", "r", "r"])
    return f"""
{v["name"]}  |  {v["street"]}  |  {v["city"]}

OFFERTE {no}                                              Datum: {dnl(date_)}
Geldig tot: {dnl(valid)}
Aan: {" / ".join(to_lines)}

{tab}

{" " * 36}Subtotaal excl. btw     € {eur(c['net'])}
{" " * 36}Btw {c['rate']} %                € {eur(c['vat'])}
{" " * 36}Totaal incl. btw        € {eur(c['gross'])}
{note}
Levertijd: 2-3 weken. Betaling binnen 30 dagen.
"""


def to_uw(unit, contact, street="Hochschulring 21"):
    return [UW, unit, f"z. Hd. {contact}", street, "35291 Wernstadt"]


def V(name, street, city, mail=None, contact=None, contact_name=None):
    return dict(name=name, street=street, city=city, contact=contact, mail=mail or "vertrieb@example.example",
                contact_name=contact_name)


# --------------------------------------------------------------------------- #
# m26  four offers, cheapest one fails a written requirement and is excluded; SAP GUI requisition
# --------------------------------------------------------------------------- #
def m26():
    rfq_date = "2027-03-01"
    unit = to_uw("Fachgebiet Photonik, FB 15", "Dr. Linus Pfannkuch")
    A = V("Optomess Handels GmbH", "Gewerbering 14", "47051 Duisburg", "angebote@optomess.example", "0203 41 77 20", "Ruth Kamphaus")
    B = V("Lichtwerk Systeme KG", "Am Seehafen 3", "28217 Bremen", None, None, "Dr. Peer Hollmann")
    C = V("Photonis Instruments Ltd", "Unit 4, Harbour Park", "Southampton SO14 3QT, UK")
    Dv = V("Strumenti Ottici Brianza S.r.l.", "Via dei Tessitori 18", "20851 Lissone (MB), Italia")
    cA = calc([("Thermischer Laserleistungsmesser, Messkopf 10 W / Ø 25 mm + Anzeigegerät (kal.)", 1, "3990.00"),
               ("Kalibrierzertifikat rückführbar (DAkkS)", 1, "190.00")])
    cB = calc([("Leistungsmesssystem LP-10, thermisch, 0,01-10 W, USB, mit Kalibrierung", 1, "4390.00")])
    cC = calc([("Thermal power meter TP-10, 10 mW - 10 W, with software and traceable calibration", 1, "4540.00")], vat=0)
    cD = calc([("Misuratore di potenza termico MPT-5, 0,5 - 5 W, USB, con taratura", 1, "3640.00")], vat=0)
    assert cA["net"] == D("4180.00")
    pa = quote_classic(A, "OH-27-1182", "2027-03-08", "2027-04-07", unit, cA)
    pb = quote_letter(B, "LS-2027/0233", "2027-03-09", unit, cB, "Leistungsmesssystem LP-10",
                      note="  Lieferzeit 3 Wochen ab Auftragseingang, frei Haus.")
    pc = quote_en(C, "Q-41907", "2027-03-10", "2027-04-09", ["Universität Wernstadt", "Fachgebiet Photonik"], cC, cur="EUR",
                  note="  Delivered duty paid (DDP) Wernstadt, prices in EUR, customs clearance handled by the supplier; no UK VAT charged on export.")
    pd = quote_it(Dv, "P-2027-0441", "2027-03-12", "2027-04-12", ["Universita Wernstadt", "Fachgebiet Photonik"], cD,
                  iva_note="Operazione intracomunitaria non imponibile (art. 41 DL 331/93) - IVA a carico del committente.")
    rfq = f"""
Universität Wernstadt · Fachbereich 15 · Fachgebiet Photonik

AUFFORDERUNG ZUR ANGEBOTSABGABE                                          Wernstadt, {de(rfq_date)}
(Vordruck Gerätefondsverfahren, Beschaffung aus der Bedarfsstelle, Auftragswert bis 50.000 EUR netto)

Gegenstand: 1 thermischer Laserleistungsmesser mit Messkopf
Abgabefrist: {de("2027-03-12")}, 12:00 Uhr · an vier Anbieter versandt (Optomess, Lichtwerk Systeme, Photonis, Strumenti Ottici Brianza)

Geforderte Leistungsanforderungen / Funktionalitäten (Anlage zum Vordruck):
  1. Thermischer Messkopf, Apertur mindestens 20 mm
  2. Messbereich mindestens 10 mW bis 10 W (kontinuierlich)
  3. Wellenlängenbereich 400 nm bis 1100 nm
  4. USB-Anbindung und Auswertesoftware für Windows
  5. Rückführbares Kalibrierzertifikat im Lieferumfang
Die Angebote müssen die Anforderungen 1 bis 5 erfüllen, um in die Wertung zu gelangen.
Zuschlagskriterium: niedrigster Preis (netto) unter den vergleichbaren Angeboten.

Dr. Linus Pfannkuch (Antragsteller)
"""
    vergl = f"""
Vergleichstabelle zur Aufforderung vom {de(rfq_date)}  (Excel-Auszug, Blatt "Wertung")

 Anbieter                        Angebot            Anf.1  Anf.2  Anf.3  Anf.4  Anf.5   Preis netto EUR   Wertung
 -------------------------------------------------------------------------------------------------------------------
 A  Optomess Handels GmbH        OH-27-1182         ja     ja     ja     ja     ja       {eur(cA['net']):>10}      1 (Zuschlag)
 B  Lichtwerk Systeme KG         LS-2027/0233       ja     ja     ja     ja     ja       {eur(cB['net']):>10}      2
 C  Photonis Instruments Ltd     Q-41907            ja     ja     ja     ja     ja       {eur(cC['net']):>10}      3
 D  Strumenti Ottici Brianza     P-2027-0441        ja     nein   ja     ja     ja       {eur(cD['net']):>10}      ausgeschieden
 -------------------------------------------------------------------------------------------------------------------
 Angebot D ist das preisgünstigste, erfüllt aber Anforderung 2 nicht (Messbereich nur 0,5 bis 5 W gegenüber
 geforderten 10 W) und ist mit den anderen Angeboten nicht vergleichbar. Es scheidet aus der Wertung aus.
 Unter den drei vergleichbaren Angeboten A, B und C ist A das niedrigste. Zuschlag an A (Optomess Handels GmbH).

 Wernstadt, {de("2027-03-22")}   gez. L. Pfannkuch      Kenntnis genommen: Prof. Dr. Henriette Mauch-Brandl
"""
    sap = f"""
Bestellanforderung anlegen                                                      ME51N     Benutzer: PFANNKUCH
-----------------------------------------------------------------------------------------------------------
Bestellanforderung 10 0047 3361      Belegart  NB Standard-BANF       Einkäufergruppe  304 FB 15
 [Kopf] [Positionsübersicht] [Texte] [Zuordnung]

 Pos  Warengruppe  Kurztext                                              Menge  ME  Preis netto   Lieferant
 10   ANLAGE       Laserleistungsmesser thermisch 10 W, Kopf+Anzeige      1     ST  {eur(cA['sub'] - D('190.00')):>9} EUR  Optomess Handels GmbH
 20   AUFWAND      Kalibrierzertifikat (Zubehör)                           1     ST  {eur(D('190.00')):>9} EUR  Optomess Handels GmbH
                                                                          Summe netto  {eur(cA['net']):>9} EUR
 Zuordnung: Kostenstelle 15-2204     Auftrag 2140612     Standort Gebäude F, Raum 1.012 (für Anlageninventar)

 Kopftext: Beschaffung nach Aufforderung zur Angebotsabgabe vom {de(rfq_date)} an vier Anbieter. Vergleichstabelle
           vom {de("2027-03-22")} anbei: A ist das günstigste vergleichbare Angebot. Angebot D wegen
           Messbereich nicht vergleichbar. Kein Rahmenvertragsprodukt.
 Freigabe: Prof. Dr. Henriette Mauch-Brandl (Kostenstellenbevollmächtigte), {de("2027-03-23")} - beauftragt
"""
    docs = [doc("BANF_10-0047-3361_ME51N.pdf", sap, margin=20),
            doc("Aufforderung_Angebotsabgabe.pdf", rfq, font="Times-Roman", producer="Microsoft Word", margin=32),
            doc("Angebot_A.pdf", pa, font="Courier"),
            doc("Angebote_B_und_C.pdf", pages(pb, pc), font="Helvetica"),
            doc("scan_3.pdf", pd, font="Helvetica", jitter=0.6),
            doc("Vergleich_Wertung.pdf", vergl, margin=20)]
    case(PROC, "beschaffungsantrag-m26",
         "Messgerät 4.180,00 EUR netto: vier Angebote nach Aufforderung mit schriftlichen Leistungsanforderungen. Das billigste Angebot (3.640,00 EUR) erfüllt eine Anforderung nicht und wird "
         "begründet ausgeschieden; unter den drei vergleichbaren ist das gewählte Angebot das niedrigste. Freigabe durch die Kostenstellenbevollmächtigte liegt vor.", docs,
         "SAP GUI ME51N requisition print (Courier), RFQ, offers in German / letter / English (UK, GBP-free EUR) / Italian, Excel scoring table",
         "cheapest offer (D) is NOT chosen: excluded for a missed requirement; three comparable offers remain; foreign offers without VAT",
         "Rule: „… Auf dieser Grundlage sind mind. drei vergleichbare Angebote einzuholen“ (Auftragswert bis 50.000 € netto, Angebotseinholung durch die Bedarfsstelle) + „Festlegung der geforderten Leistungsanforderungen / Funktionalitäten“ [" + S_GF + "] + „Grundsätzlich müssen 3 Angebote eingeholt werden“ [" + S_BESCH + "]")


# --------------------------------------------------------------------------- #
# m27  direct award just below 1,000 EUR net (one offer), mail with approval in a reply
# --------------------------------------------------------------------------- #
def m27():
    mail_date = "2027-05-10"
    vendor = V("Labormarkt Wiedenhöft e. K.", "Industriestr. 7", "37081 Göttingen", "vertrieb@labormarkt-wiedenhoeft.example",
               contact_name="Sandra Wiedenhöft")
    c = calc([("Nitril-Handschuhe puderfrei, Gr. M, Box à 100", 10, "8.40"),
              ("Pipettenspitzen 200 µL, Rack à 96, steril", 12, "17.80"),
              ("Zentrifugenröhrchen 50 mL, Beutel à 500", 4, "46.50"),
              ("Parafilm M, Rolle 38 m x 10 cm", 6, "21.50"),
              ("Kryoboxen 81 Plätze, PP", 20, "12.55"),
              ("Einmal-Skalpelle steril, Nr. 11, Box à 10", 5, "24.18")])
    assert c["net"] == D("984.50") and c["gross"] > 1000
    offer = quote_mail(vendor, "AN-2027-05-0317", "2027-05-06", "Dr. Fenja Rothkirch <f.rothkirch@uni-wernstadt.example>", c,
                       "Ihre Anfrage Laborverbrauchsmaterial - Angebot AN-2027-05-0317",
                       note="Versandkostenfrei ab 150,00 EUR netto.")
    req = f"""
Von:      Fenja Rothkirch <f.rothkirch@uni-wernstadt.example>
Gesendet: {WD_L[dt(mail_date).weekday()]}, {dlong(mail_date)} 08:14
An:       beschaffung@uni-wernstadt.example
Kopie:    Prof. Dr. Isolde Sadowski <i.sadowski@uni-wernstadt.example>
Betreff:  Bestellung Laborverbrauchsmaterial AG Zellbiologie - Direktvergabe

Sehr geehrte Damen und Herren,

wir bitten um Bestellung des Verbrauchsmaterials gemäß beiliegendem Angebot AN-2027-05-0317 (Labormarkt
Wiedenhöft, 06.05.2027): Auftragswert {eur(c['net'])} EUR netto ({eur(c['gross'])} EUR brutto). Der Auftragswert
liegt netto unter 1.000 EUR; wir haben daher nur dieses eine Angebot eingeholt (Direktvergabe). Es handelt sich
um Laborverbrauchsmaterial, für das kein Rahmenvertrag besteht. Kostenstelle 10-5530, Auftrag 2140901.

Beste Grüße, Fenja Rothkirch

------------------------------------------------------------------------------------
Von:      Prof. Dr. Isolde Sadowski
Gesendet: {WD_L[dt(mail_date).weekday()]}, {dlong(mail_date)} 09:02
Betreff:  AW: Bestellung Laborverbrauchsmaterial AG Zellbiologie - Direktvergabe

Einverstanden, bitte so bestellen. Als Kostenstellenbevollmächtigte beauftrage ich hiermit die Bestellung.
I. Sadowski
"""
    docs = [doc("Mail_Bestellung_Verbrauchsmaterial.pdf", req, margin=24, creator="Thunderbird"),
            doc("angebot.pdf", offer, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m27",
         "Laborverbrauchsmaterial über 984,50 EUR netto mit nur einem Angebot: der Auftragswert liegt netto unter 1.000 EUR, die Direktvergabe ist zulässig, kein Rahmenvertragsprodukt, "
         "die Kostenstellenbevollmächtigte hat per Antwortmail beauftragt. Summen stimmen.", docs,
         "Thunderbird mail thread (request + approval reply), vendor offer as a mail print",
         "gross amount (1.171,56 EUR) exceeds 1.000 EUR, net (984,50 EUR) does not; one offer only; approval is a reply further down",
         "Rule: „Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ [" + S_CAT + "] + „Bestellungen müssen vom Kostenstellenbevollmächtigten … beauftragt werden.“ [" + S_BESCH + "]. Doubt: whether 'Auftragswert' means net or gross is not spelled out on the page (the practice case 02 uses net).",
         conf="medium")


# --------------------------------------------------------------------------- #
# m28  framework contract: office supplies through the WPS basket
# --------------------------------------------------------------------------- #
def m28():
    d = "2027-02-17"
    c = calc([("Ordner A4 breit, 80 mm, Wolkenmarmor", 50, "1.89"),
              ("Hängemappen für Registratur, 100 St.", 6, "17.40"),
              ("Kugelschreiber blau, Karton à 50", 8, "24.60"),
              ("Whiteboard-Marker sortiert, Set à 4", 20, "9.80"),
              ("Flipchart-Block kariert, 20 Blatt", 30, "14.20"),
              ("Haftnotizen 75x75 mm, Würfel", 40, "6.15"),
              ("Locher 2-fach, Metall", 12, "11.90"),
              ("Archivboxen, A4, 10er Pack", 15, "28.40"),
              ("Papierkorb 18 l, Metall", 10, "16.75")])
    items = "\n".join(f"  {i:>2}   {x[0]:<48} {x[1]:>4}   {eur(x[2]):>8}   {eur(x[3]):>9}" for i, x in enumerate(c["lines"], 1))
    wk_ = f"""
WPS · Warenbestellsystem · Universität Wernstadt                                          Druckansicht {iso(d)}
=====================================================================================================
 Warenkorb   WK-0027-04512             Status: zur Freigabe          Erstellt von: M. Hübenthal (Sekretariat FB 07)
 Katalog:   Rahmenvertrag Büro- und Geschäftsbedarf (Kernsortiment) · Lieferant: Kontorhaus Brenner GmbH, Darmstadt
 Kontierung: Kostenstelle 07-1002 · Lieferadresse: Hochschulring 21, Gebäude B, Raum 0.14
-----------------------------------------------------------------------------------------------------
  Pos   Artikel                                              Menge   Preis netto   Summe netto
{items}
-----------------------------------------------------------------------------------------------------
  Warenwert netto                                                                   {eur(c['net']):>9} EUR
  USt. 19 %                                                                         {eur(c['vat']):>9} EUR
  Gesamt brutto                                                                     {eur(c['gross']):>9} EUR
  Mindestbestellwert des Rahmenvertragspartners (15,00 EUR netto) erreicht - kein Mindermengenzuschlag.
-----------------------------------------------------------------------------------------------------
 Hinweis: Katalogpreise gemäß Rahmenvertrag; Vergleichsangebote entfallen.
"""
    mail = f"""
Subject: Bestellfreigabe WPS WK-0027-04512 (Büromaterial 2. Quartal)
From: Prof. Dr. Cornelius Eisfeld <c.eisfeld@uni-wernstadt.example>
To: Hübenthal, Maren
Date: {WD_EN[dt(add(d, 1)).weekday()]}, {dt(add(d, 1)).day} Feb 2027 10:31

Liebe Frau Hübenthal,

die Bestellung aus dem Rahmenvertrag Büromaterial ist in Ordnung. Ich gebe sie als Kostenstellenbevollmächtigter
hiermit frei - bitte im WPS abschicken und den Wareneingang buchen, sobald die Lieferung da ist.

Beste Grüße
Cornelius Eisfeld
"""
    docs = [doc("WPS_Warenkorb_WK-0027-04512.pdf", wk_, font="Helvetica", margin=20),
            doc("Freigabe.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m28",
         "Büro- und Geschäftsbedarf über den Rahmenvertrag im WPS: Katalogartikel des Rahmenvertragspartners, Mindestbestellwert erreicht, daher keine Vergleichsangebote nötig. "
         "Kostenstellenbevollmächtigter hat die Bestellung per Mail freigegeben.", docs,
         "WPS basket print (Helvetica, boxed), approval mail in English-header style",
         "order value well above 1.000 EUR with no offers at all: allowed because every item is from the framework catalogue",
         "Rule: „Der Abschluss der Rahmenverträge ermöglicht den einzelnen Bereichen Ihre Bedarfe aus den jeweiligen Rahmensortimenten ohne das Einholen von Vergleichsangeboten zu decken.“ + „Bestellungen sind über das WPS-System zu buchen.“ + Mindestbestellauftragswert 15 EUR netto [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m29  framework contract for office chairs, spreadsheet requisition + catalogue extract
# --------------------------------------------------------------------------- #
def m29():
    d = "2027-04-06"
    c = calc([("Bürodrehstuhl 'Merian 2', Netzrücken, 3D-Armlehnen", 8, "389.00")])
    sheet = f"""
Bestellanforderung_Moebel_FG-Mikrosysteme.xlsx          Tabelle: BANF                       gedruckt {de(d)}
+-----+------------------------------------------+-------+-------------+--------------+-----------------------+
|  Nr | Artikel (Rahmenvertrag Bürodrehstühle)   | Menge | EP netto    | GP netto     | Katalog / Artikelnr.   |
+-----+------------------------------------------+-------+-------------+--------------+-----------------------+
|   1 | Bürodrehstuhl "Merian 2", Netzrücken      |     8 | {eur(D("389.00")):>9} € | {eur(c['net']):>10} € | WPS-Katalog RV-DS / 20-1177 |
+-----+------------------------------------------+-------+-------------+--------------+-----------------------+
|     | USt. 19 %                                |       |             | {eur(c['vat']):>10} € |                       |
|     | Gesamt brutto                            |       |             | {eur(c['gross']):>10} € |                       |
+-----+------------------------------------------+-------+-------------+--------------+-----------------------+
 Kostenstelle: 11-3040          Lieferort: Gebäude C, Räume 2.08 bis 2.11 (Neueinrichtung Doktorandenbüros)
 Vergabeart: Abruf aus dem Rahmenvertrag der hessischen Hochschulen (Bürodrehstühle), Lieferant Sessel & Form
             Deutschland GmbH. Es wurden keine Vergleichsangebote eingeholt, weil für Bürodrehstühle ein
             verbindlicher Rahmenvertrag besteht. Bestellung ausschließlich über WPS.
 Beauftragt: Prof. Dr. Margit Stolzenburg (Kostenstellenbevollmächtigte) 06.04.2027  ----  Ersteller: B. Rademacher
"""
    cat = f"""
WPS · Katalogauszug · Rahmenvertrag Bürodrehstühle · Lieferant: Sessel & Form Deutschland GmbH
Stand der Preisliste: 01.01.2027                                              Preise in EUR, netto, frei Haus

 Art.-Nr.   Modell                                    Ausführung                         Preis
 20-1177    Merian 2                                  Netzrücken, 3D-Armlehnen            {eur(D("389.00"))}
 20-1178    Merian 2 Plus                             mit Kopfstütze                      {eur(D("429.00"))}
 20-1190    Neckar Basic                              Polsterrücken, feste Armlehnen      {eur(D("279.00"))}

Hinweis: Bestellungen für Bürodrehstühle sind ausschließlich über das WPS-System bei dem Rahmenvertragspartner zu buchen.
"""
    docs = [doc("BANF_Stuehle.pdf", sheet, margin=18),
            doc("katalogauszug_RV.pdf", cat, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m29",
         "Acht Bürodrehstühle zu 389,00 EUR netto (3.112,00 EUR) aus dem Rahmenvertrag Bürodrehstühle über WPS, Preis stimmt mit dem Katalogauszug überein, "
         "keine Vergleichsangebote, beauftragt durch die Kostenstellenbevollmächtigte.", docs,
         "spreadsheet requisition with box-drawn grid, catalogue extract (Helvetica)",
         "over 3.000 EUR with zero offers; catalogue price check; 'keine Vergleichsangebote' stated in plain words",
         "Rule: „Derzeit existieren Rahmenverträge u.a. für … Bürodrehstühle“ + „Die Rahmenverträge sind verbindlich für alle Bereiche der [Universität].“ + „Die Bestellungen sind über das WPS-System zu buchen.“ [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m30  office furniture via framework partner + advisor offer that the buyer confirms
# --------------------------------------------------------------------------- #
def m30():
    d = "2027-06-14"
    cc = calc([("Schreibtisch höhenverstellbar elektrisch 160x80, Lindner+Rath 'Flex 4'", 4, "640.00"),
               ("Rollcontainer 3 Schübe, abschließbar", 2, "215.00")])
    offer = f"""
Raumform Beratung GmbH · Fliegerstr. 31-35 · 34277 Fuldabrück-Süd (Beratung und Angebotserstellung für den Rahmenvertragspartner Lindner + Rath Büromöbel GmbH)

ANGEBOT 2027-A-0388                                                       {de(add(d, -9))}
für: Universität Wernstadt, FB 03, Fachgebiet Soziologie, z. Hd. Frau Jelena Bartkowiak

 Pos  Bezeichnung                                                        Menge   EP netto    GP netto
 1    Schreibtisch höhenverstellbar elektrisch 160x80 'Flex 4'              4     {eur(D("640.00")):>8}   {eur(cc['lines'][0][3]):>9}
 2    Rollcontainer 3 Schübe, abschließbar                                  2     {eur(D("215.00")):>8}   {eur(cc['lines'][1][3]):>9}
                                                                            Summe netto  {eur(cc['net']):>9} EUR
                                                                            zzgl. 19 % USt {eur(cc['vat']):>9} EUR

Preise gemäß Rahmenvertrag der hessischen Hochschulen (Büromöbel, ausgenommen Dreh-, Besucher- und Seminarstühle).
Nach Ihrer Rückmeldung, dass das Angebot so in Ordnung ist, stellen wir es in Ihre WPS-Artikelliste ein.
"""
    thread = f"""
Von:      Jelena Bartkowiak <j.bartkowiak@uni-wernstadt.example>
Gesendet: Montag, {dlong(d)} 13:05
An:       Raumform Beratung GmbH <angebote@raumform.example>
Kopie:    Prof. Dr. Ottilie Haverkamp; Zentrale Materialwirtschaft
Betreff:  AW: Angebot 2027-A-0388 - Rückmeldung

Sehr geehrter Herr Möller,

das Angebot 2027-A-0388 ist so in Ordnung. Bitte stellen Sie es wie besprochen in unsere WPS-Artikelliste
unter dem Rahmenvertragspartner Lindner + Rath ein. Die Bestellung buche ich anschließend im WPS.

Mit freundlichen Grüßen
Jelena Bartkowiak

-----------------------------------------
Von: Raumform Beratung GmbH
Gesendet: {WD_L[dt(add(d, -9)).weekday()]}, {dlong(add(d, -9))} 16:20
Betreff: Angebot 2027-A-0388
(Angebot im Anhang, siehe Angebots-PDF)

Von:      Prof. Dr. Ottilie Haverkamp
Gesendet: Montag, {dlong(d)} 14:11
An:       Bartkowiak, Jelena
Betreff:  Freigabe

Die Bestellung der Möbel ist von mir als Kostenstellenbevollmächtigter beauftragt, bitte buchen.
"""
    wps = f"""
WPS · Artikelliste "Lindner + Rath Büromöbel GmbH - Angebote"                 Druckansicht {iso(add(d, 2))}
Status: Angebot 2027-A-0388 eingestellt am {iso(add(d, 1))} (nach Rückmeldung des Bestellers)
  Pos  Art.-Nr.   Bezeichnung                                              Menge   Netto/Stück    Netto gesamt
  1    LR-FLX4    Schreibtisch höhenverstellbar 160x80 'Flex 4'              4     {eur(D("640.00")):>9}    {eur(cc['lines'][0][3]):>9}
  2    LR-RC3     Rollcontainer 3 Schübe, abschließbar                        2     {eur(D("215.00")):>9}    {eur(cc['lines'][1][3]):>9}
  Summe netto {eur(cc['net'])} EUR · Kostenstelle 03-2210 · Lieferung KW 30
"""
    docs = [doc("Angebot_2027-A-0388.pdf", offer, font="Helvetica"),
            doc("Mailverlauf_Moebel.pdf", thread, margin=22),
            doc("WPS_Artikelliste_Druck.pdf", wps, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m30",
         "Büromöbel (2.990,00 EUR netto) über den Möbel-Rahmenvertrag: wie von der Rahmenvertragsseite verlangt, erstellt der Berater des Vertragspartners das Angebot, der Besteller gibt die "
         "Rückmeldung, dass es so in Ordnung ist, und danach wird die Bestellung im WPS gebucht. Beauftragung durch die Kostenstellenbevollmächtigte liegt vor.", docs,
         "advisor quotation (Helvetica), Outlook thread with quoted offer mail, WPS list print",
         "the offer comes from an advisor company (not the framework partner itself) and no comparison offers exist; confirmation mail precedes the WPS booking",
         "Rule: „Nachdem Sie von der Firma Büro & Wohn Design ein schriftliches Angebot erhalten haben, müssen Sie … eine Rückmeldung geben, dass das Angebot so in Ordnung ist. Daraufhin wird Ihnen das Angebot für die Bestellung im WPS-System … eingestellt“ [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m31  IT framework contract with the creator/orderer function of WPS
# --------------------------------------------------------------------------- #
def m31():
    d = "2027-07-05"
    c = calc([("Notebook 14 Zoll, 32 GB RAM, 1 TB SSD, Vertragskonfiguration B", 4, "1284.00"),
              ("Dockingstation USB-C, 100 W, Vertragsartikel", 4, "139.90"),
              ("Monitor 27 Zoll WQHD, USB-C, Vertragsartikel", 4, "218.60")])
    wps = f"""
WPS  >  Ersteller-Besteller  >  Warenkorb WK-0027-09877                             Druckansicht {iso(add(d, 1))}
------------------------------------------------------------------------------------------------------------
Katalog           Rahmenvertrag IT-Arbeitsplatzgeräte, Los 2 Notebooks und Monitore (Hochschulverbund)
Lieferant         Rhein-Main IT Systemhaus GmbH (Rahmenvertragspartner)
Ersteller:in      Sven Nowack (WPS-Zugang als Ersteller, keine SAP-Bestellberechtigung)
Besteller:in      Monika Lührs (SAP-bekannte Nutzerin, Bestellberechtigung FB 16)
Status            vom Ersteller bereitgestellt {iso(d)} · zur Bestellung durch Besteller:in · ITS-Zustimmung: gilt bei
                  Bestellungen aus dem IT-Rahmenvertrag als erteilt
Kontierung        Kostenstelle 16-9040 / Auftrag 2141207          Lieferort Gebäude E, Raum 0.31

 Art.-Nr.         Bezeichnung                                                 Menge  Preis netto   Summe netto
 RV-NB-14-3210B   Notebook 14", 32 GB / 1 TB, Vertragskonfiguration B             4   {eur(D("1284.00")):>9}    {eur(c['lines'][0][3]):>9}
 RV-DS-C-0088     Dockingstation USB-C, 100 W                                     4   {eur(D("139.90")):>9}    {eur(c['lines'][1][3]):>9}
 RV-MO-27-0415    Monitor 27", WQHD, USB-C                                        4   {eur(D("218.60")):>9}    {eur(c['lines'][2][3]):>9}
                                                                    Warenwert netto  {eur(c['net']):>9}
                                                                    USt. 19 %        {eur(c['vat']):>9}
                                                                    Gesamt brutto    {eur(c['gross']):>9}
Bestellung nur über das WPS-System; Katalogpreise gemäß Rahmenvertrag. Vergleichsangebote sind nicht erforderlich.
"""
    mail = f"""
Von:      Sven Nowack <s.nowack@uni-wernstadt.example>
An:       Monika Lührs <m.luehrs@uni-wernstadt.example>
Kopie:    Prof. Dr. Gero Wittekind
Datum:    {WD_L[dt(add(d, 1)).weekday()]}, {dlong(add(d, 1))}, 08:20
Betreff:  Warenkorb WK-0027-09877 zur Bestellung - Ausstattung neue Doktorandenarbeitsplätze

Hallo Monika,

ich habe im WPS (Ersteller-Funktion) den Warenkorb WK-0027-09877 für vier Arbeitsplätze zusammengestellt. Bitte
bestelle ihn als Besteller. Es sind ausschließlich Artikel aus dem IT-Rahmenvertrag, daher gibt es keine
Vergleichsangebote. Herr Prof. Wittekind hat als Kostenstellenbevollmächtigter in der letzten Gruppenbesprechung
zugestimmt und bestätigt dies in Kopie.

Danke und Gruß, Sven

--
AW von Gero Wittekind, {dlong(add(d, 1))} 09:03: Bestätigt, bitte bestellen.
"""
    docs = [doc("Warenkorb_Ersteller-Besteller.pdf", wps, font="Helvetica", margin=20),
            doc("Mail_Besteller.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m31",
         "Vier Arbeitsplatzausstattungen aus dem IT-Rahmenvertrag über WPS (Ersteller-Besteller-Funktion): Der Ersteller stellt den Korb zusammen, die berechtigte Besteller:in bestellt. "
         "Vergleichsangebote entfallen, ITS-Zustimmung gilt beim IT-Rahmenvertrag als erteilt, Kostenstellenbevollmächtigter bestätigt.", docs,
         "WPS Ersteller-Besteller basket print, internal mail with approval reply at the bottom",
         "two different people (creator without SAP rights, orderer with rights); 5.000+ EUR without offers; approval typed as 'AW von ...' line",
         "Rule: „Bei Beschaffungen aus dem Rahmenvertrag für IT-Systeme gilt die Zustimmung des ITS als erteilt.“ [" + S_GF + "] + „Diese Funktion ermöglicht Mitarbeiterzugänge, um Warenkörbe zusammenzustellen und durch einen ausgewählten SAP-bekannten User diesen bestellen zu lassen.“ [" + S_WPS + "] + „… alle Bestellungen ausschließlich über unser WPS-System“ [" + S_ITS + "]")


# --------------------------------------------------------------------------- #
# m32  sustainable catering framework, lot 1 (up to 50 persons), lead time kept
# --------------------------------------------------------------------------- #
def m32():
    order = "2027-09-27"
    ev = nxt("2027-10-26", 1)
    n = 44
    c = calc([("Mittagsbuffet vegetarisch/vegan, bio-regional-saisonal", n, "28.50"),
              ("Getränkepauschale (Wasser, Saft, Kaffee, Tee, fair gehandelt)", n, "4.20"),
              ("Anlieferung, Aufbau und Rücknahme (Mehrweggeschirr)", 1, "65.00")], vat=19)
    form = f"""
GREEN OFFICE · Veranstaltungsformular Nachhaltiges Catering                               Formular-Nr. NC-1
=======================================================================================================
Veranstaltung        Auftaktworkshop Graduiertenkolleg "Resiliente Landnutzung"
Datum / Uhrzeit      {wdl(ev)}, Mittagsbuffet 12:30 Uhr
Ort                  Gebäude A, Raum A 1.02 (Campus Nord)
Personenanzahl       {n} Personen        -> Los 1 (1 - 50 Personen), Rahmenvertragspartner Campuskantine Lindenhof
Bestelldatum         {de(order)} (Vorlaufzeit {(dt(ev) - dt(order)).days // 7} Wochen; mindestens drei Wochen bei bis zu 50 Personen)
Kontakt              Judith Weidlich, Tel. 7390-4207
Kostenstelle         05-3318 (DFG-Graduiertenkolleg, Auftrag 6-3720)
Wünsche              vegetarisch/vegan, 3 x glutenfrei; keine Einwegverpackung
=======================================================================================================
"""
    bestell = f"""
Campuskantine Lindenhof · Rahmenvertragspartner Catering (Los 1)                      Bestellung Nr. LH-27-0912
Lindenhofweg 3 · 35291 Wernstadt

Bestellformular                                                                    Datum {de(order)}
Besteller: Universität Wernstadt, FB 05, Dr. Judith Weidlich

  Leistung                                                     Personen   Preis/Pers.   Netto
  Mittagsbuffet vegetarisch/vegan (bio · regional · saisonal)     {n}        {eur(D("28.50"))}     {eur(c['lines'][0][3])}
  Getränkepauschale (fair gehandelt)                              {n}         {eur(D("4.20"))}     {eur(c['lines'][1][3])}
  Anlieferung, Aufbau, Mehrweggeschirr                            pauschal                 {eur(c['lines'][2][3])}
                                                                       Summe netto {eur(c['net'])} EUR
                                                                       USt. 19 % {eur(c['vat'])} EUR · Gesamt {eur(c['gross'])} EUR

Liefertermin {de(ev)}, 11:45 Uhr. Abrechnung direkt zwischen Besteller und Caterer gemäß Rahmenvertrag.
"""
    mail = f"""
Von: Judith Weidlich <j.weidlich@uni-wernstadt.example>
An: Campuskantine Lindenhof <bestellung@lindenhof-kantine.example>
Cc: Prof. Dr. Esther Klingebiel; Green Office <green-office@uni-wernstadt.example>
Datum: {WD_EN[dt(order).weekday()]}, {dt(order).day} Sep 2027 09:12
Betreff: Cateringbestellung {de(ev)} - Los 1 - {n} Personen

Guten Tag,

anbei das Veranstaltungsformular und das Bestellformular für unseren Workshop am {de(ev)} (4 Wochen Vorlauf).
Prof. Klingebiel hat als Kostenstellenbevollmächtigte die Bestellung unterschrieben freigegeben. Bitte um
kurze Bestätigung.

Freundliche Grüße, Judith Weidlich
"""
    docs = [doc("Veranstaltungsformular_NC-1.pdf", form, margin=22),
            doc("Bestellformular_Lindenhof.pdf", bestell, font="Helvetica"),
            doc("Mail_an_Caterer.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m32",
         "Cateringbestellung für 44 Personen beim Rahmenvertragspartner des Loses 1 (bis 50 Personen) mit mehr als drei Wochen Vorlauf; Veranstaltungs- und Bestellformular liegen vor, "
         "Freigabe durch die Kostenstellenbevollmächtigte. Vergleichsangebote entfallen wegen des Rahmenvertrags.", docs,
         "Green-Office event form (Courier), caterer order form (Helvetica), mail to the caterer",
         "1.600+ EUR order without offers (framework lot 1); lead time stated as a number of weeks; funded from a DFG project",
         "Rule: „Für kleinere und mittlere Veranstaltungen mit einer Personenanzahl von bis zu 200 ist die Dépa Forschungskantine Rahmenvertragspartner.“ (Los 1: 1-50) + „Die Vorlaufzeit für die Bestellung von Caterings bis 50 Personen beträgt drei Wochen.“ [" + S_CAT + "] + „Die Koordination der Bestellung und Abrechnung läuft direkt zwischen dem bestellenden Bereich … und dem Caterer.“")


# --------------------------------------------------------------------------- #
# m33  conventional catering below 1,000 EUR: direct award, one offer
# --------------------------------------------------------------------------- #
def m33():
    d = "2027-05-31"
    v = V("Partyservice Hartung", "Brunnenstr. 22", "35390 Gießen", None, None, "Elke Hartung")
    c = calc([("Belegte Brötchen, gemischt (Käse, Schinken, vegetarisch)", 76, "2.60"),
              ("Obstplatte groß (für 20 Personen)", 2, "34.00"),
              ("Kaffee/Tee-Service mit Geschirr, pauschal für 38 Personen", 1, "78.00"),
              ("Mineralwasser 0,75 l (Mehrweg), Kiste à 12", 4, "13.50")], vat=19)
    assert c["net"] < 1000
    offer = quote_letter(v, "2027-0412", "2027-05-24", ["Universität Wernstadt", "Fachgebiet Didaktik der Chemie", "z. Hd. Frau Birte Lorenzen"],
                         c, "Catering für Ihre Veranstaltung am 17.06.2027 (38 Personen)",
                         note="  Lieferung und Abbau durch uns, Abholung des Geschirrs am Folgetag.")
    web = f"""
Intranet-Formular "Beschaffungsantrag (formlos)" · Eingang beschaffung@uni-wernstadt.example · {iso(d)} 10:44
---------------------------------------------------------------------------------------------------------
Bedarfsstelle       FB 14 Chemie · FG Didaktik der Chemie · Birte Lorenzen
Beschaffungsgegenstand   Catering Kolloquium mit Lehrkräften (38 Personen), Lieferung 17.06.2027 11:30 Uhr
Art                 ( ) Rahmenvertrag   (x) kein Rahmenvertrag vorhanden (konventionelles Catering)
Wert                {eur(c['net'])} EUR netto ({eur(c['gross'])} EUR brutto)
Angebote            1 (Partyservice Hartung, Angebot 2027-0412). Auftragswert unter 1.000 EUR netto,
                    daher Direktvergabe ohne Vergleichsangebote.
Kostenstelle        14-7701 (Landesmittel). Keine Drittmittel, kein Bewilligungsbescheid betroffen.
Nachhaltigkeit      Mehrweggeschirr und Mineralwasser in Mehrwegflaschen; nachhaltiges Catering (Rahmenvertrag)
                    wurde geprüft, ist an diesem Termin nicht verfügbar.
Freigabe            Prof. Dr. Ludger Pahlke, Kostenstellenbevollmächtigter: "freigegeben" ({iso(d)})
---------------------------------------------------------------------------------------------------------
[ Absenden ]  Anlagen: Angebot (PDF)
"""
    docs = [doc("Beschaffungsantrag_formlos_20270531.pdf", web, font="Helvetica", margin=22),
            doc("Angebot_Hartung.pdf", offer, font="Times-Roman", producer="Microsoft Word", margin=36)]
    case(PROC, "beschaffungsantrag-m33",
         "Konventionelles Catering (kein Rahmenvertrag) mit einem Angebot über " + eur(c["net"]) + " EUR netto: unter 1.000 EUR, Direktvergabe ohne Vergleichsangebote zulässig, "
         "Landesmittel, Freigabe durch den Kostenstellenbevollmächtigten.", docs,
         "intranet web form with ( ) / (x) options, Word-style offer letter",
         "catering with no framework partner and one offer; the form mentions 'Rahmenvertrag' (unchecked) and 'nachhaltiges Catering' (not available)",
         "Rule: „Für konventionelles Catering existiert derzeit kein Rahmenvertrag. Hier besteht weiterhin, abhängig vom Auftragswert, die Notwendigkeit der Einholung von mindestens drei Vergleichsangeboten. Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ [" + S_CAT + "]")


# --------------------------------------------------------------------------- #
# m34  cylinder gases via the framework catalogue (helium explicitly not part)
# --------------------------------------------------------------------------- #
def m34():
    d = "2027-03-23"
    c = calc([("Argon 5.0, Stahlflasche 50 l / 200 bar, Füllung", 8, "118.40"),
              ("Stickstoff 5.0, Stahlflasche 50 l / 200 bar, Füllung", 6, "96.80"),
              ("Formiergas 95/5 (N2/H2), 50 l / 200 bar, Füllung", 4, "142.00"),
              ("Flaschenmiete je Flasche und Quartal", 18, "9.50")])
    wps = f"""
WPS Warenbestellsystem · Katalog "Rahmenvertrag Flaschengase" · Lieferant: Rheingas Industriegase GmbH          {iso(d)}
-------------------------------------------------------------------------------------------------------------------
Warenkorb WK-0027-02210        Besteller: Dr. Walther Brenneisen (FG Dünne Schichten)         Status: bestellt am {iso(add(d, 1))}

 Pos   Artikel                                                   Menge     Preis netto    Summe netto
{chr(10).join(f"  {i}    {x[0]:<56} {x[1]:>3}    {eur(x[2]):>9}    {eur(x[3]):>9}" for i, x in enumerate(c["lines"], 1))}
                                                                       Warenwert netto  {eur(c['net']):>10} EUR
                                                                       USt. 19 %        {eur(c['vat']):>10} EUR
                                                                       Gesamt brutto    {eur(c['gross']):>10} EUR

Alle Positionen sind Rahmenvertragsprodukte (Katalog Flaschengase, außer Helium). Heliumprodukte sind nicht Bestandteil
dieser Bestellung und werden gesondert über den Heliumkatalog bezogen.
"""
    mail = f"""
Von:      Walther Brenneisen
An:       Zentrale Materialwirtschaft <zentrale-materialwirtschaft@uni-wernstadt.example>
Datum:    {WD_L[dt(d).weekday()]}, {de(d)}
Betreff:  Gasbestellung 1. Halbjahr - Rahmenvertrag - kein Vergleichsangebot

Guten Tag,

wie jedes Quartal bestelle ich die Prozessgase für die Sputteranlagen über den WPS-Katalog Flaschengase.
Weil es sich um den Rahmenvertrag handelt, habe ich keine Vergleichsangebote eingeholt. Kostenstelle 15-6612,
Prof. Dr. Sieglinde Raab hat als Kostenstellenbevollmächtigte die Bestellung beauftragt (Telefonat, per Mail
bestätigt, siehe unten).

[Bestätigung S. Raab, {de(d)} 15:50: "Bestellung der Gase wie beschrieben ist beauftragt."]
"""
    docs = [doc("WPS_Gase_WK-0027-02210.pdf", wps, font="Helvetica", margin=20),
            doc("Mail_Gase.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m34",
         "Prozessgase ausschließlich aus dem WPS-Katalog des Rahmenvertrags Flaschengase, keine Heliumprodukte, daher keine Vergleichsangebote nötig. "
         "Summen stimmen, die Kostenstellenbevollmächtigte hat beauftragt (per Mail bestätigt).", docs,
         "WPS catalogue print, short internal mail with a bracketed confirmation line",
         "helium mentioned only as 'not part of this order'; quarterly cylinder rent as separate line; no offers",
         "Rule: „Die Rahmenvertragsprodukte sind im WPS-System unter dem Katalog Rahmenvertrag Flaschengase gelistet und müssen hierüber bestellt werden.“ [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m35  business cards through the web-to-print framework shop
# --------------------------------------------------------------------------- #
def m35():
    d = "2027-04-19"
    c = calc([("Visitenkarten Querformat, deutsch, mit Fachbereichslogo, 250 Stück", 4, "38.00")])
    shop = f"""
DRUCKWERK SÜD WEBSHOP (hochschulweiter Web-to-Print-Shop, Rahmenvertrag)           Order confirmation / Bestellbestätigung
Shop-ID: UW-SHOP-4417                                                              {iso(d)} 11:08

Bestellung Nr. DW-2027-088412                    Zugang: über WPS (Punch-out), Benutzerin Ilse Karamanlis (SAP-Zugang)
Kostenstelle 13-0050                             Lieferadresse: Dekanat FB 13, Hochschulring 21, 35291 Wernstadt

 Pos  Produkt                                                   Menge    Preis netto     Summe netto
 1    Visitenkarten Querformat DE, mit FB-Logo, 250 Stück          4       {eur(D("38.00"))} EUR      {eur(c['net'])} EUR
      (4 Namen: C. Haupt, A. Lindqvist-Maurer, T. Okonkwo, R. Zielinski - Korrekturabzüge freigegeben)
 Versand innerhalb Deutschlands: im Preis enthalten
                                                                Summe netto {eur(c['net'])} EUR
                                                                USt. 19 %    {eur(c['vat'])} EUR
                                                                Gesamt       {eur(c['gross'])} EUR

Dies ist der für die Universität vereinbarte Rahmenvertragspreis. Zahlung gegen Rechnung an die Zentrale Rechnungsprüfung.
"""
    mail = f"""
Betreff: Visitenkarten für vier Kolleg:innen - Bestellung im Web-to-Print-Shop

Liebe Frau Karamanlis,

könnten Sie bitte für Herrn Haupt, Frau Lindqvist-Maurer, Herrn Okonkwo und Herrn Zielinski jeweils 250
Visitenkarten im Querformat (deutsch, mit Fachbereichslogo) über den Web-to-Print-Shop bestellen? Sie haben als
Einzige im Dekanat einen SAP-Zugang. Die Daten stehen in der Tabelle unten. Kostenstelle: 13-0050.

Einverstanden - Dekan Prof. Dr. Anselm Rübsamen (Kostenstellenbevollmächtigter), {de(d)}.
"""
    docs = [doc("Bestellbestaetigung_DW-2027-088412.pdf", shop, font="Helvetica", margin=20),
            doc("bestellwunsch.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m35",
         "Visitenkarten über den hochschulweiten Web-to-Print-Shop (Rahmenvertragspartner), bestellt von der bestellberechtigten Kollegin mit SAP-Zugang für vier Kolleg:innen. "
         "Rahmenvertragspreis, Kleinbetrag (152,00 EUR netto), Freigabe des Dekans.", docs,
         "web-shop order confirmation with bilingual heading (Helvetica), short request mail",
         "ordered by a colleague on behalf of others (as the shop rules require); framework price; no offers",
         "Rule: „Bitte wenden Sie sich mit Ihrem Bestellwunsch an die bestellberechtigten Kolleg*innen in Ihrer Organisationseinheit (Kolleginnen und Kollegen mit einem SAP Zugang)“ + Rahmenvertragspartner Druckerei [" + S_W2P + "]")


# --------------------------------------------------------------------------- #
# m36  equipment-fund procedure below 50,000 EUR: three comparable offers, building coordination
# --------------------------------------------------------------------------- #
def m36():
    rfq_d = "2027-04-12"
    unit = to_uw("Fachgebiet Werkstoffprüfung, FB 12", "Prof. Dr. Xaver Lichtenegger")
    A = V("Thermotest Prüftechnik GmbH", "Dieselstr. 40", "73728 Esslingen", None, "0711 38 20 50", "Albrecht Kimmich")
    B = V("Climatic Solutions Europe B.V.", "Kanaalweg 112", "5611 EL Eindhoven, Nederland")
    C = V("Enceintes Climatiques Rhône SA", "27 rue des Fonderies", "69007 Lyon, France")
    cA = calc([("Klimaprüfschrank 400 l, -40 bis +180 °C, Regelung, Datenlogger", 1, "37200.00"),
               ("Aufstellung, Inbetriebnahme, Einweisung", 1, "1700.00")])
    cB = calc([("Climatic test chamber 400 l, -40 to +180 °C, controller and data logger", 1, "38350.00"),
               ("Delivery, installation, training", 1, "1430.00")], vat=0)
    cC = calc([("Enceinte climatique 400 L, -40/+180 °C, régulation et enregistreur", 1, "39100.00"),
               ("Livraison, mise en service, formation", 1, "2150.00")], vat=0)
    assert cA["net"] == D("38900.00") and cA["net"] < cB["net"] < cC["net"]
    rfq = f"""
Universität Wernstadt · Fachbereich 12 · Fachgebiet Werkstoffprüfung                 Wernstadt, {de(rfq_d)}

AUFFORDERUNG ZUR ANGEBOTSABGABE (Gerätefondsverfahren)    Gegenstand: Klimaprüfschrank 400 l

Leistungsanforderungen (Anlage 1):
   - Nutzvolumen mindestens 400 l, Temperaturbereich mindestens -40 bis +180 °C
   - Temperaturänderungsrate mindestens 5 K/min, Schnittstelle Ethernet, Datenlogger
   - Elektroanschluss 400 V CEE 32 A (vorhanden im Raum G 0.17), kein Abluftanschluss erforderlich
   - Lieferung, Aufstellung, Inbetriebnahme und Einweisung im Angebot enthalten
Angebote bis {de("2027-05-03")}. Angeschrieben: Thermotest Prüftechnik, Climatic Solutions Europe, Enceintes Climatiques Rhône.
Wertung nach dem niedrigsten Gesamtpreis (netto) der vergleichbaren Angebote.
"""
    abtv = f"""
Von:      Bau und Liegenschaften, Abt. V <abt-v@uni-wernstadt.example>
Gesendet: Donnerstag, {dlong("2027-04-08")} 10:15
An:       Lichtenegger, Xaver
Betreff:  AW: Aufstellung Klimaprüfschrank Raum G 0.17 - Abstimmung

Sehr geehrter Herr Prof. Lichtenegger,

wir haben die Unterlagen geprüft: Der Raum G 0.17 verfügt über einen CEE-32-A-Anschluss (400 V) mit ausreichender
Absicherung. Zusätzlicher Platzbedarf entsteht nicht (Stellfläche 1,1 x 0,9 m, Traglast des Bodens ausreichend);
Um- oder Anschlussmaßnahmen sind nicht erforderlich. Aus Sicht von Abt. V bestehen keine Einwände. Das Ergebnis
kann dem Beschaffungsvorgang beigefügt werden.

Freundliche Grüße, i. A. Hannelore Tiedemann
"""
    pa = quote_classic(A, "TT-27-3094", "2027-04-26", "2027-06-04", unit, cA)
    pb = quote_en(B, "CSE-2027-1180", "2027-04-28", "2027-06-04", ["Universität Wernstadt", "Materials Testing Group, FB 12"], cB,
                  note="  Delivered duty paid, EUR prices, intra-Community supply (VAT ID provided); reverse charge applies.")
    pc = quote_fr(C, "D-27-0912", "2027-04-29", "2027-06-04", ["Université de Wernstadt", "Groupe Essais des Matériaux, FB 12"], cC,
                  note="Livraison intracommunautaire, autoliquidation de la TVA.")
    vm = f"""
Vergabevermerk · Gerätefondsverfahren · Klimaprüfschrank                                  {de("2027-05-06")}

Vergleich der Angebote (netto, inklusive Aufstellung/Inbetriebnahme):
   Thermotest Prüftechnik GmbH               TT-27-3094       {eur(cA['net']):>10} EUR   <- niedrigster Gesamtpreis
   Climatic Solutions Europe B.V.            CSE-2027-1180    {eur(cB['net']):>10} EUR
   Enceintes Climatiques Rhône SA            D-27-0912        {eur(cC['net']):>10} EUR
Alle drei Angebote erfüllen die Anforderungen 1 bis 4 und sind vergleichbar. Auftragswert unter 50.000 EUR netto,
daher Angebotseinholung durch die Bedarfsstelle zulässig. Abstimmung mit Abt. V (Mail vom 08.04.2027) liegt bei;
ITS-Beteiligung nicht erforderlich (kein DV-System). Zuschlag an Thermotest.

X. Lichtenegger (Antragsteller)    Freigabe als Kostenstellenbevollmächtigter: gez. X. Lichtenegger, {de("2027-05-06")}
"""
    docs = [doc("Aufforderung_Angebotsabgabe.pdf", rfq, font="Times-Roman", producer="Microsoft Word", margin=32),
            doc("Abstimmung_Abt_V.pdf", abtv, font="Helvetica"),
            doc("angebot_1.pdf", pa),
            doc("angebot_2.pdf", pb, font="Helvetica"),
            doc("angebot_3_fr.pdf", pc, font="Helvetica"),
            doc("Vergabevermerk.pdf", vm, font="Courier", margin=26)]
    case(PROC, "beschaffungsantrag-m36",
         "Klimaprüfschrank 38.900,00 EUR netto im Gerätefondsverfahren: Leistungsanforderungen festgelegt, Aufforderung zur Angebotsabgabe an drei Anbieter (deutsch, englisch, französisch), "
         "günstigstes vergleichbares Angebot gewählt, Abstimmung mit Bau und Liegenschaften liegt bei. Vergabevermerk nennt die Beträge richtig.", docs,
         "Word RFQ, mail from building department, three offers in DE / EN (NL) / FR, short Courier award note",
         "high value without a formal tender (below 50.000 EUR net) is allowed; foreign offers with reverse charge; coordination mail attached on purpose",
         "Rule: Auftragswert bis € 50.000 netto → „Angebotseinholung durch die Bedarfsstelle … mind. drei vergleichbare Angebote einzuholen“; „für die Angebotseinholung wird der Vordruck „Aufforderung zur Angebotsabgabe“ verwendet“; „Die Beschaffung von Geräten, die … zusätzliche oder besondere Ver- oder Entsorgungsanschlüsse benötigen …, sind vorab mit der Abt. V … abzustimmen. Das Ergebnis ist dem Beschaffungsvorgang beizufügen.“ [" + S_GF + "]")


# --------------------------------------------------------------------------- #
# m37  value above 50,000 EUR net: specification (Leistungsverzeichnis) and formal procedure
# --------------------------------------------------------------------------- #
def m37():
    d = "2027-02-09"
    bids = [("Kristallos Analytik GmbH", D("74300.00"), "2027-03-30"),
            ("Roentgenwerk Hegner AG", D("77950.00"), "2027-03-31"),
            ("Diffrax Scientific Instruments S.A.", D("81400.00"), "2027-03-31")]
    antrag = f"""
Universität Wernstadt · Fachbereich 15 · Fachgebiet Kristallographie                  Wernstadt, {dlong(d)}

An die Zentrale Materialwirtschaft (Sachgebiet IV B)

Beschaffungsantrag: Röntgen-Pulverdiffraktometer (Tischgerät) mit Probenwechsler

Sehr geehrte Damen und Herren,

der geschätzte Auftragswert liegt mit rund 75.000 EUR netto über der Grenze von 50.000 EUR netto, bis zu der die
Bedarfsstelle selbst Angebote einholen kann. Ich beantrage deshalb ein förmliches Vergabeverfahren auf der Grundlage des
beigefügten Leistungsverzeichnisses (zu vereinbarende Funktionalitäten). Der Wert bleibt unter 200.000 EUR
einschließlich MwSt.; ein Großgeräteverfahren ist nicht erforderlich. Finanzierung aus dem Gerätefonds
(Kostenstelle 15-1170). Die Durchführung des Verfahrens liegt bei der Zentralen Materialwirtschaft.

Mit freundlichen Grüßen
Prof. Dr. Ferdinand Alsdorf (Kostenstellenbevollmächtigter)
"""
    lv = f"""
LEISTUNGSVERZEICHNIS · Röntgen-Pulverdiffraktometer (Tischgerät)          Anlage zum Beschaffungsantrag vom {de(d)}
Grundlage des förmlichen Vergabeverfahrens und Bestandteil des Auftrags

 Nr   Funktionalität (Muss)                                                      Nachweis
 1.   Cu-Röhre, 600 W, Bragg-Brentano-Geometrie, theta/theta                      Datenblatt
 2.   Positionsempfindlicher Detektor, Winkelauflösung besser als 0,01° 2-Theta        Datenblatt
 3.   Automatischer Probenwechsler für mindestens 16 Proben                       Datenblatt
 4.   Strahlenschutzgehäuse nach RöV mit Verriegelung, Abnahme durch den Anbieter Erklärung
 5.   Auswertesoftware mit Phasenanalyse und Datenbankzugriff, 3 Lizenzen         Angebot
 6.   Lieferung, Aufstellung, Inbetriebnahme, Einweisung, 24 Monate Gewährleistung Angebot
Zuschlagskriterium: niedrigster Preis unter den Angeboten, die alle Muss-Funktionalitäten erfüllen.
"""
    prot = f"""
Öffnungsprotokoll · Beschränkte Ausschreibung "Röntgen-Pulverdiffraktometer" · Zentrale Materialwirtschaft

Ablauf: Aufforderung an fünf Unternehmen am 22.02.2027; Angebotsfrist 31.03.2027, 12:00 Uhr; drei Angebote eingegangen.
Öffnung am {de("2027-03-31")}, 12:30 Uhr, im Beisein von zwei Mitarbeitenden (Vier-Augen-Prinzip).

 Bieter                                   Eingang        Angebotssumme netto    Muss-Funktionalitäten 1-6
 {bids[0][0]:<40} {de(bids[0][2])}   {eur(bids[0][1]):>14} EUR       erfüllt
 {bids[1][0]:<40} {de(bids[1][2])}   {eur(bids[1][1]):>14} EUR       erfüllt
 {bids[2][0]:<40} {de(bids[2][2])}   {eur(bids[2][1]):>14} EUR       erfüllt
 (zwei weitere angefragte Unternehmen haben mit Schreiben vom 10.03. und 15.03.2027 abgesagt)
"""
    vm = f"""
Vergabevermerk · Zentrale Materialwirtschaft · {de("2027-04-07")}

Das Angebot der Kristallos Analytik GmbH über {eur(bids[0][1])} EUR netto ({eur(r2(bids[0][1] * D("1.19")))} EUR brutto) ist
das günstigste der drei Angebote; es erfüllt alle Muss-Funktionalitäten des Leistungsverzeichnisses. Preisabstand zum zweiten
Angebot: {eur(bids[1][1] - bids[0][1])} EUR. Zuschlag an Kristallos Analytik GmbH. Bestellung als Anlage in SAP-MM durch die Zentrale
Materialwirtschaft; Wareneingang erst nach Abnahme des Strahlenschutzes.
gez. Zentrale Materialwirtschaft          Kenntnis: Prof. Dr. F. Alsdorf, Kostenstellenbevollmächtigter
"""
    docs = [doc("Antrag_Diffraktometer.pdf", antrag, font="Times-Roman", producer="Microsoft Word", margin=34),
            doc("LV_Diffraktometer.pdf", lv, margin=22),
            doc("Oeffnungsprotokoll.pdf", prot, font="Helvetica"),
            doc("Vergabevermerk_ZMW.pdf", vm, font="Times-Roman", margin=32)]
    case(PROC, "beschaffungsantrag-m37",
         "Röntgen-Pulverdiffraktometer ca. 74.300,00 EUR netto: über 50.000 EUR netto wird nicht mit informellen Angeboten gearbeitet, sondern ein Leistungsverzeichnis erstellt und ein förmliches Verfahren "
         "durch die Zentrale Materialwirtschaft geführt (Öffnungsprotokoll, drei Angebote, Vergabevermerk). Wert unter der Großgeräte-Grenze von 200.000 EUR.", docs,
         "Word application, specification list, opening protocol and award note of the central purchasing office",
         "two further invited firms declined (only three bids); the cheapest bid wins; value between 50.000 and 200.000 EUR",
         "Rule: Auftragswert über € 50.000 netto → „Erstellung eines Leistungsverzeichnisses (Inhalt: zu vereinbarende Funktionalitäten), das als Grundlage für ein förmliches Vergabeverfahren dient und damit Grundlage des Auftrages wird“; Großgeräteverfahren erst ab „€ 200.000 (incl. MwSt.)“ [" + S_GF + "]. Doubt: the page does not describe the formal procedure in detail.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m38  non-framework IT system with IT-service consent and three offers
# --------------------------------------------------------------------------- #
def m38():
    d = "2027-08-23"
    unit = to_uw("Fachgebiet Maschinelles Lernen, FB 16", "Dr. Pauline Wegener-Ahlers")
    A = V("Tensorhaus Computer GmbH", "Frankenstr. 9", "90461 Nürnberg", "angebote@tensorhaus.example", None, "Dirk Brandner")
    B = V("Servercontor Kiel eG", "Hafenstr. 6", "24103 Kiel", None, None, "Marion Petersen")
    C = V("GPU-Systems Deutschland GmbH", "Industrieweg 71", "40231 Düsseldorf", None, "0211 77 66 12", "Tim Quandt")
    cA = calc([("GPU-Server 4 HE, 4x GPU 24 GB, 2x 24-Core CPU, 512 GB RAM, 8 TB NVMe", 1, "9150.00"),
               ("Rack-Schienen, Kabelsatz, Einbau und Burn-in-Test", 1, "490.00")])
    cB = calc([("Compute-Server 4U, 4 x GPU 24 GB, 2 x 24 Core, 512 GB, 8 TB NVMe", 1, "9890.00")])
    cC = calc([("GPU-Server 4U Rackmount, 4 GPU (24 GB), 2 CPU 24 Core, 512 GB RAM, 8 TB SSD, Schienen, Burn-in", 1, "10240.00")])
    assert cA["net"] == D("9640.00")
    z = f"""
Zammad · Ticket#2027082300077 · ITS-Beschaffung · GPU-Server FG Maschinelles Lernen
==========================================================================================
Status: geschlossen (Zustimmung erteilt)        Gruppe: IT-Servicezentrum / Beschaffung        Erstellt: {de(d)}
------------------------------------------------------------------------------------------
[1] Pauline Wegener-Ahlers, {de(d)} 10:02:
    Bitte um Zustimmung des ITS zur Beschaffung eines GPU-Servers (kein Rahmenvertragsprodukt) für das Rechenzentrum
    des Fachbereichs. Drei Angebote liegen vor (Tensorhaus, Servercontor Kiel, GPU-Systems). Das Vorhaben ist im
    DV-Konzept des FB 16 (Maßnahme 3.4, vom Präsidium zustimmend zur Kenntnis genommen am 12.01.2026) enthalten.
[2] ITS, Torsten Möbius, {de(add(d, 2))} 14:40:
    Das ITS stimmt der Beschaffung zu (Az. ITS-27-0152). Kompatibel mit der Rack-Infrastruktur und dem
    Netzkonzept; Betrieb durch den FB. Bitte diese Zustimmung der Bestellanforderung beifügen.
"""
    form = f"""
BESTELLANTRAG (Word-Vordruck BZ-2)                                                    Datum {de(add(d, 7))}
Antragstellerin: Dr. Pauline Wegener-Ahlers, FB 16, FG Maschinelles Lernen                  Kostenstelle 16-4902
Gegenstand:      GPU-Server (Anlage; selbstständig nutzbares Gerät, Nettoeinzelpreis über 800,01 EUR)
Lieferant:       Tensorhaus Computer GmbH, Nürnberg (Angebot TH-27-0877 vom {de(add(d, -6))}, {eur(cA['net'])} EUR netto)
Angebote:        3 (Tensorhaus {eur(cA['net'])} · Servercontor Kiel {eur(cB['net'])} · GPU-Systems {eur(cC['net'])} EUR netto);
                 gewählt wurde das günstigste Angebot, alle drei sind technisch gleichwertig (siehe Anlage 4)
ITS-Zustimmung: liegt vor (Ticket 2027082300077, Az. ITS-27-0152, Anlage 1)
Rahmenvertrag:  kein Rahmenvertragsprodukt (Server fallen nicht unter den IT-Rahmenvertrag für Arbeitsplatzgeräte)
Standort:       Rechenzentrum FB 16, Gebäude E, Raum E 0.01
Freigabe:       Prof. Dr. Ansgar Wittgenstein, Kostenstellenbevollmächtigter · {de(add(d, 7))}
"""
    docs = [doc("ITS_Ticket_2027082300077.pdf", z, margin=22, producer="Zammad"),
            doc("Bestellantrag_BZ-2.pdf", form, font="Times-Roman", producer="Microsoft Word", margin=30),
            doc("Angebot_Tensorhaus.pdf", quote_classic(A, "TH-27-0877", add(d, -6), add(d, 24), unit, cA)),
            doc("Angebot_Servercontor.pdf", quote_mail(B, "SK-2027-612", add(d, -5), "Dr. Pauline Wegener-Ahlers", cB,
                                                       "Angebot Compute-Server SK-2027-612"), font="Helvetica"),
            doc("Angebot_GPU-Systems.pdf", quote_letter(C, "GS-27-4410", add(d, -4), unit, cC, "GPU-Server 4U",
                                                        note="  Lieferzeit ca. 5 Wochen."), font="Times-Roman")]
    case(PROC, "beschaffungsantrag-m38",
         "Ein GPU-Server (9.640,00 EUR netto) außerhalb des Rahmenvertrags: drei technisch gleichwertige Angebote, günstigstes gewählt, Zustimmung des ITS liegt schriftlich vor, "
         "die Maßnahme ist im DV-Konzept des Fachbereichs enthalten. Freigabe durch den Kostenstellenbevollmächtigten.", docs,
         "ticket-system print with consent from IT service, Word order form, offers as classic / mail / letter",
         "IT hardware outside the framework contract: ITS consent is in a closed ticket (not an email); offers dated before the consent",
         "Rule: „Die Beschaffung von DV-Systemen ist vorab mit dem ITS abzustimmen. Die Zustimmung ist dem Sachgebiet IVB mit der Bestallanforderung einzureichen.“ + „Als Voraussetzung … müssen die beantragten Beschaffungsmaßnahmen im DV-Konzept des Fachbereichs … enthalten sein“ + drei vergleichbare Angebote [" + S_GF + "]")




# --------------------------------------------------------------------------- #
# m39  third-party-funded purchase; the grant is stricter than the university (3 offers from 500 EUR)
# --------------------------------------------------------------------------- #
def m39():
    d = "2027-03-29"
    unit = to_uw("Fachgebiet Agrarökologie, FB 11", "Dr. Henrike Thaler-Weiß")
    A = V("Agrarlab Bedarf GmbH", "Lerchenweg 9", "37574 Einbeck", None, "05563 71 90 4", "Silke Tönnies")
    B = V("Bodenanalytik-Shop e. K.", "Marktstr. 31", "99084 Erfurt", "bestellung@bodenanalytik-shop.example", None, "Ronny Kastner")
    C = V("Probenwelt Handels GmbH", "Seestr. 145", "13353 Berlin", None, None, "Anja Preisler")
    items = [("Bodenprobenbeutel PE, 1 l, Karton à 500", 5, "46.50"),
             ("Kunststoff-Spaten-Set (Edelstahl) für Probennahme", 3, "58.90"),
             ("Etiketten wasserfest, Rolle à 1000", 8, "12.20"),
             ("Probenkühlbox 25 l mit Akkus", 3, "74.30")]
    mult = {"A": D("1"), "B": D("1.035"), "C": D("1.07")}
    cs = {k: calc([(n, q, r2(D(u) * m)) for n, q, u in items]) for k, m in mult.items()}
    assert cs["A"]["net"] < cs["B"]["net"] < cs["C"]["net"] and cs["A"]["net"] > 500
    excerpt = f"""
Stiftung Landwirtschaft und Klima · Zuwendungsbescheid Az. SLK-2026-0441 (Projekt AgriSense-W) · Auszug

Nebenbestimmungen zur Mittelverwendung
  3.1  Die Zuwendung ist wirtschaftlich und sparsam zu verwenden; Bewirtungskosten sind nicht zuwendungsfähig.
  3.2  Für Beschaffungen ab einem Auftragswert von 500,00 EUR netto sind mindestens drei vergleichbare Angebote
       einzuholen und im Verwendungsnachweis zu dokumentieren. Direktvergaben bis 500,00 EUR netto sind zulässig.
  3.3  Für Geräte und Verbrauchsmaterial gelten daneben die Beschaffungsregeln der Empfängerin.
"""
    antrag = f"""
Von:      Henrike Thaler-Weiß <h.thaler-weiss@uni-wernstadt.example>
Gesendet: {WD_L[dt(d).weekday()]}, {dlong(d)} 11:26
An:       beschaffung@uni-wernstadt.example
Kopie:    Prof. Dr. Ewald Kornfeld (Kostenstellenbevollmächtigter)
Betreff:  Bestellung Probennahmematerial, Drittmittelprojekt AgriSense-W (Auftrag 6-4020)

Guten Tag,

wir bitten um Bestellung von Probennahmematerial für die Feldkampagne aus dem Drittmittelprojekt AgriSense-W (Auftrag 6-4020).
Der Zuwendungsbescheid (Nr. 3.2, Auszug anbei) verlangt schon ab 500 EUR netto drei Vergleichsangebote - strenger als die
Regel der Universität, die erst ab 1.000 EUR netto drei Angebote verlangt. Wir haben deshalb drei Angebote eingeholt:

   Agrarlab Bedarf GmbH             Angebot AB-27-331    {eur(cs['A']['net'])} EUR netto   <- günstigstes
   Bodenanalytik-Shop e. K.         Angebot BS-8812      {eur(cs['B']['net'])} EUR netto
   Probenwelt Handels GmbH          Angebot PW-27-0094   {eur(cs['C']['net'])} EUR netto

Die Positionen sind in allen drei Angeboten identisch. Bitte bestellen bei Agrarlab Bedarf. Die Angebote werden dem
Verwendungsnachweis beigefügt.

Viele Grüße, Henrike Thaler-Weiß
[Antwort E. Kornfeld, {de(d)} 12:40: "Bestellung ist von mir beauftragt."]
"""
    pa = quote_classic(A, "AB-27-331", add(d, -8), add(d, 22), unit, cs["A"])
    pb = quote_mail(B, "BS-8812", add(d, -7), "Dr. Henrike Thaler-Weiß", cs["B"], "Angebot BS-8812 Probennahmematerial")
    pc = quote_letter(C, "PW-27-0094", add(d, -6), unit, cs["C"], "Probennahmematerial für Feldkampagnen")
    docs = [doc("Mail_Bestellung_AgriSense.pdf", antrag, margin=22),
            doc("Zuwendungsbescheid_Auszug.pdf", excerpt, font="Times-Roman", margin=32),
            doc("Angebote.pdf", pages(pa, pb, pc), font="Helvetica")]
    case(PROC, "beschaffungsantrag-m39",
         "Drittmittelkauf über " + eur(cs["A"]["net"]) + " EUR netto: Die Universität verlangt erst ab 1.000 EUR drei Angebote, der Zuwendungsbescheid aber schon ab 500 EUR netto. "
         "Es gilt das Strengere, und es liegen drei vergleichbare Angebote vor; das günstigste wurde gewählt, der Kostenstellenbevollmächtigte hat beauftragt.", docs,
         "mail print with bracketed approval line, funder's grant conditions (Times), merged three-page offers PDF",
         "order below the university's 1.000 EUR line still carries three offers because the grant is stricter; excerpt mentions 'Direktvergaben bis 500 EUR'",
         "Rule: „Sofern ein Drittmittelgeber eigene Vorgaben zu diesem Themenkreis macht, gelten immer die strengeren Regelungen.“ [" + S_GLOS + "] + „Maßnahmen, die aufgrund eines Drittmittelprojekts vergeben werden, unterliegen zum Teil anderen Wertgrenzen. Hier ist der Bewilligungsbescheid entsprechend zu prüfen.“ [" + S_CAT + "]")


# --------------------------------------------------------------------------- #
# m40  Swiss supplier (CHF, customs); three offers compared in EUR including side costs
# --------------------------------------------------------------------------- #
def m40():
    d = "2027-05-17"
    rate = D("1.04")
    chf_item, chf_cust = D("3980.00"), D("85.00")
    a_chf = chf_item + chf_cust
    a_eur = conv(a_chf, rate)
    cB = calc([("Präzisions-Mikropositionierer 3-Achsen, 10 nm Auflösung, Controller", 1, "4420.00")])
    cC = calc([("Precisie micropositioneerder 3-assig, 10 nm, controller incl. software", 1, "4515.00")], vat=21)
    offer_ch = f"""
Mikrotechnik Aarefeld AG · Industriestrasse 28 · CH-5000 Aarau                    Offerte Nr. 27-1049
Ihre Anfrage vom {de(add(d, -12))}                                                    Datum: {de(add(d, -6))}  ·  gültig bis {de(add(d, 24))}

Universität Wernstadt, Fachgebiet Mikrosystemtechnik, z. Hd. Dr. Matthias Eberhart-Lück, D-35291 Wernstadt

  Pos.  Bezeichnung                                                   Menge       Preis CHF
  1     Präzisions-Mikropositionierer 3-Achsen, 10 nm, Controller        1        {chf(chf_item):>10}
  2     Zollabfertigung und Ausfuhranmeldung (Spedition)                 1           {chf(chf_cust):>7}
        Total netto, Lieferung DAP Wernstadt                                       {chf(a_chf):>10}
        Mehrwertsteuer Schweiz: 0 % (Ausfuhrlieferung)

Zahlungsbedingungen: 30 Tage netto, in CHF. Umrechnung für Ihren Vergleich zum Kurs {rate_eur(rate)} EUR/CHF
(Stand {de(add(d, -6))}): {eur(a_eur)} EUR. Einfuhrumsatzsteuer und Zollanmeldung in Deutschland durch den Käufer.
"""
    zoll = f"""
Universität Wernstadt · Zentrale Materialwirtschaft · Zollverfahren (Drittland)

ANTRAG AUF ZOLLBEFREIUNG FÜR WAREN ZU FORSCHUNGS- UND LEHRZWECKEN                    zur Bestellbuchung
Bestellung:        Präzisions-Mikropositionierer, Lieferant Mikrotechnik Aarefeld AG (CH), Angebot 27-1049
Verwendung:        Forschung (Fachgebiet Mikrosystemtechnik, Labor F 0.07); die Ware wird nicht weiterverkauft.
Warenwert:         CHF {chf(chf_item)}  (ca. {eur(conv(chf_item, rate))} EUR)
Zollanmeldung:     durch die im Angebot genannte Spedition (Kosten CHF {chf(chf_cust)} sind im Angebot enthalten)
Der Antrag wurde mit der Bestellbuchung ausgefüllt.            Datum {de(add(d, 2))}   Unterschrift: M. Eberhart-Lück
"""
    antrag = f"""
UNIVERSITÄT WERNSTADT · Formular ZB-5 · Beschaffungsantrag mit Angebotsvergleich                            {de(add(d, 2))}
==============================================================================================================
Bedarfsstelle       Fachgebiet Mikrosystemtechnik (FB 16) · Dr. Matthias Eberhart-Lück · Kostenstelle 16-3335
Gegenstand          Präzisions-Mikropositionierer 3-Achsen, 10 nm (Anlage)
Rahmenvertrag       [ ] ja   [x] nein
Zollverfahren       [x] Lieferant im Drittland (Schweiz): Zollbefreiung (Forschung) beantragt, Formular liegt bei
Angebotsvergleich (netto, in EUR, alle Nebenkosten bis Wernstadt eingerechnet):
     1  Mikrotechnik Aarefeld AG (CH)      CHF {chf(a_chf)} = {eur(a_eur)} EUR (Kurs {rate_eur(rate)})     <- gewählt
     2  Nanoposition GmbH (D)                                   {eur(cB['net'])} EUR
     3  Micropositie Delft B.V. (NL)                            {eur(cC['net'])} EUR
Das gewählte Angebot ist das günstigste, auch nach Einrechnung der Zollabfertigung (CHF 85,00).
Freigabe: Prof. Dr. Jolanda Wiegmann, Kostenstellenbevollmächtigte, {de(add(d, 2))} - beauftragt
==============================================================================================================
"""
    docs = [doc("ZB-5_Antrag_Positionierer.pdf", antrag, margin=22),
            doc("Zollbefreiung_Antrag.pdf", zoll, font="Helvetica"),
            doc("Offerte_Aarefeld.pdf", offer_ch, font="Helvetica"),
            doc("Angebot_Nanoposition.pdf",
                quote_classic(V("Nanoposition GmbH", "Technologiepark 3", "07745 Jena", None, "03641 22 80 1"), "NP-27-205", add(d, -9), add(d, 21),
                              to_uw("Fachgebiet Mikrosystemtechnik, FB 16", "Dr. Matthias Eberhart-Lück"), cB), font="Courier"),
            doc("offerte_delft.pdf",
                quote_nl(V("Micropositie Delft B.V.", "Rotterdamseweg 402", "2629 HH Delft"), "O-2027-0318", add(d, -8), add(d, 22),
                         ["Universität Wernstadt", "Fachgebiet Mikrosystemtechnik"], cC,
                         note="Intracommunautaire levering, btw verlegd (reverse charge)."), font="Helvetica")]
    case(PROC, "beschaffungsantrag-m40",
         "Mikropositionierer aus der Schweiz (Drittland): drei Angebote in drei Währungen/Sprachen, im Vergleich inklusive Zollabfertigungskosten in EUR umgerechnet ist das gewählte Schweizer Angebot das günstigste. "
         "Zollbefreiung für Forschungszwecke wurde mit der Bestellbuchung beantragt, das Formular liegt bei.", docs,
         "form with [ ] / [x] boxes, Swiss offer (CHF with apostrophes), German offer, Dutch offer, customs exemption form",
         "foreign supplier outside the EU plus customs fee line; conversion at a stated rate; one offer with reverse charge",
         "Rule: „Dann müssen Sie in diesem Zusammenhang beachten, dass zusätzlich zum Kaufpreis Einfuhrabgaben anfallen.“ + Zollbefreiung „grundsätzlich immer dann möglich, wenn Sie die bestellte Ware für den Bereich Forschung und Lehre einsetzen. Es muss jedoch bereits mit Bestellbuchung ein entsprechender Antrag ausgefüllt werden.“ [" + S_ZOLL + "] + drei Angebote [" + S_BESCH + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m41  discount and reverse-charge in an Italian offer; chosen after discount
# --------------------------------------------------------------------------- #
def m41():
    d = "2027-06-07"
    unit = to_uw("Fachgebiet Biophysik, FB 10", "Dr. Valentin Osterkamp")
    cI = calc([("Lettore di micropiastre multimodale, absorbance/fluorescenza, con software", 1, "3260.00")], vat=0, discount_pct=8)
    cD = calc([("Multimode-Mikroplatten-Reader, Absorption/Fluoreszenz, inkl. Software", 1, "3150.00")], shipping="95.00")
    cN = calc([("Multimode microplate reader, absorbance/fluorescence, incl. software", 1, "3380.00")], vat=0)
    assert cI["net"] == D("2999.20") and cI["net"] < cD["net"] < cN["net"]
    pi = quote_it(V("Biostrumenti Lombardia S.p.A.", "Via Galvani 52", "20125 Milano, Italia"), "P-27/0612", add(d, -12), add(d, 18),
                  ["Universita Wernstadt", "Fachgebiet Biophysik", "p.c. Dr. Osterkamp"], cI,
                  iva_note="Operazione non soggetta a IVA ai sensi dell'art. 7-ter DPR 633/72 (inversione contabile, cessione intracomunitaria)." +
                           "\nL'importo di sconto e' gia' dedotto dal totale netto.")
    pd = quote_classic(V("Labortechnik Neumeyer GmbH", "Rosenstr. 12", "89073 Ulm", None, "0731 84 20 5"), "LN-27-904", add(d, -10), add(d, 20), unit, cD)
    pn = quote_en(V("Brightline Bioinstruments B.V.", "Prof. Bavincklaan 9", "1183 AT Amstelveen, Netherlands"), "Q-77310", add(d, -9), add(d, 21),
                  ["Universität Wernstadt", "Biophysics Group"], cN, note="  Intra-Community supply: reverse charge, VAT ID of the buyer required.")
    brief = f"""
Dr. Valentin Osterkamp · Fachgebiet Biophysik (FB 10)                                          Wernstadt, {dlong(d)}

An die Zentrale Beschaffung

Bestellung Mikroplatten-Reader - Angebotsvergleich

Sehr geehrte Damen und Herren,

für unser Fachgebiet beantrage ich die Beschaffung eines Multimode-Mikroplatten-Readers. Ich habe drei Angebote
eingeholt und vergleiche die Nettobeträge nach Abzug von Rabatt und mit allen Nebenkosten:

     Biostrumenti Lombardia S.p.A.   3.260,00 EUR abzüglich 8 % Sconto  = {eur(cI['net'])} EUR     (Reverse Charge, keine USt.)
     Labortechnik Neumeyer GmbH      3.150,00 EUR zuzüglich 95,00 EUR Fracht = {eur(cD['net'])} EUR
     Brightline Bioinstruments B.V.  {eur(cN['net'])} EUR

Das italienische Angebot ist nach Rabatt am günstigsten und erfüllt alle in der Anfrage genannten Anforderungen. Ich bitte um
Bestellung bei Biostrumenti Lombardia S.p.A. Die Umsatzsteuer wird nach dem Reverse-Charge-Verfahren in Deutschland abgeführt.

Kostenstelle 10-6040; beauftragt: Prof. Dr. Ines Vollbrecht (Kostenstellenbevollmächtigte), {de(d)}.

Mit freundlichen Grüßen
Valentin Osterkamp
"""
    docs = [doc("Antrag_Reader.pdf", brief, font="Times-Roman", producer="Microsoft Word", margin=32),
            doc("preventivo_P-27-0612.pdf", pi, font="Helvetica"),
            doc("Angebot_LN-27-904.pdf", pd),
            doc("Q-77310.pdf", pn, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m41",
         "Drei Angebote für einen Mikroplatten-Reader über je rund 3.000 EUR netto; verglichen wird nach Rabatt (8 % Sconto im italienischen Angebot) und mit Fracht, "
         "so ist das italienische Angebot mit 2.999,20 EUR netto das günstigste. Reverse Charge ist erklärt, Freigabe liegt vor.", docs,
         "Word application letter with comparison, Italian preventivo (ASCII) with a discount line, German offer, English offer",
         "the list price of the chosen vendor (3.260 EUR) is higher than the other two; the discount makes it cheapest",
         "Rule: „Grundsätzlich müssen 3 Angebote eingeholt werden“ [" + S_BESCH + "] + Gerätefondsverfahren „mind. drei vergleichbare Angebote“ [" + S_GF + "]; cheapest = net price after discount and carriage („Skonto und Rabatte sind abzurechnen“, „Bezugsnebenkosten (z. B. Fracht …) sind dem Kaufpreis … zuzurechnen“ [" + S_ANL + "]).")


# --------------------------------------------------------------------------- #
# m42  lowest unit price is NOT the cheapest total: carriage included, Dutch offer chosen
# --------------------------------------------------------------------------- #
def m42():
    d = "2027-09-06"
    unit = to_uw("Fachgebiet Hydrologie, FB 14", "Dr. Tilmann Rehberger")
    cA = calc([("Datenlogger-Station Pegel, 4 Kanäle, GSM-Modem", 3, "1180.00")])
    cB = calc([("Datalogger waterpeil, 4 kanalen, GSM-modem", 3, "1090.00")], vat=0, shipping="115.00")
    cC = calc([("Level data logger station, 4 channels, GSM modem", 3, "1040.00")], vat=0, shipping="390.00")
    assert cB["net"] < cA["net"] and cB["net"] < cC["net"]
    pa = quote_letter(V("Pegelwerk Messsysteme GmbH", "Wehrstr. 4", "79098 Freiburg", None, None, "Karin Seibold"), "PM-27-0771", add(d, -8), unit, cA,
                      "Datenlogger-Stationen Pegel")
    pb = quote_nl(V("Hydrodata Nederland B.V.", "Zuiderhaven 71", "8911 AX Leeuwarden"), "OFF-27-0455", add(d, -7), add(d, 23),
                  ["Universität Wernstadt", "Fachgebiet Hydrologie"], cB,
                  note="Verzendkosten: € 115,00 (inbegrepen in totaal). Intracommunautaire levering, btw verlegd.")
    pc = quote_en(V("Nordic Hydromet Ltd", "Unit 12 Quayside Estate", "Aberdeen AB11 5RG, UK"), "HM/27/118", add(d, -7), add(d, 23),
                  ["University of Wernstadt", "Hydrology"], cC, note="  Carriage and customs clearance (DDP): EUR 390.00 as shown.")
    vgl = f"""
Preisvergleich Datenlogger-Stationen (3 Stück)                                              {de(add(d, -1))}
Verglichen werden die Gesamtkosten netto bis Wernstadt (Anschaffungskosten = Kaufpreis + Bezugsnebenkosten):

   Anbieter                      Preis je Station    Summe Geräte     Fracht/Zoll      Gesamt netto
   Pegelwerk Messsysteme GmbH     {eur(D("1180.00")):>9} EUR    {eur(cA['sub']):>9}        {eur(cA['ship']):>7}      {eur(cA['net']):>9} EUR
   Hydrodata Nederland B.V.       {eur(D("1090.00")):>9} EUR    {eur(cB['sub']):>9}        {eur(cB['ship']):>7}      {eur(cB['net']):>9} EUR   <- gewählt
   Nordic Hydromet Ltd (UK)       {eur(D("1040.00")):>9} EUR    {eur(cC['sub']):>9}        {eur(cC['ship']):>7}      {eur(cC['net']):>9} EUR

Hinweis: Nordic Hydromet hat zwar den niedrigsten Stückpreis, ist durch Fracht und Zollabfertigung aber insgesamt am teuersten.
Bestellung bei Hydrodata Nederland B.V. (günstigste Gesamtkosten). Kostenstelle 14-3180, beauftragt: Prof. Dr. Cäcilie Ruppert, {de(add(d, -1))}.
"""
    docs = [doc("Vergleich_Datenlogger.pdf", vgl, margin=22),
            doc("PM-27-0771.pdf", pa, font="Times-Roman"),
            doc("OFF-27-0455_nl.pdf", pb, font="Helvetica"),
            doc("HM_27_118.pdf", pc, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m42",
         "Drei Angebote für drei Datenlogger-Stationen (je um 3.500 EUR netto); der Vergleich rechnet Fracht und Zollabfertigung mit ein, deshalb ist nicht der Anbieter mit dem niedrigsten Stückpreis, "
         "sondern der niederländische mit den niedrigsten Gesamtkosten (3.385,00 EUR netto) gewählt. Freigabe liegt vor.", docs,
         "price-comparison table (Courier), German letter offer, Dutch offer (€ prefix), English offer from the UK",
         "chosen vendor does not have the lowest unit price; the comparison includes carriage/customs; mixed languages and currency symbols",
         "Rule: Anschaffungskosten = Kaufpreis + Nebenkosten: „Bezugsnebenkosten (z. B. Fracht, Inbetriebnahme) sind dem Kaufpreis des Wirtschaftsgutes zuzurechnen“ [" + S_ANL + "] + „Grundsätzlich müssen 3 Angebote eingeholt werden“ [" + S_BESCH + "]")


# --------------------------------------------------------------------------- #
# m43  software licences from the university's framework (Microsoft)
# --------------------------------------------------------------------------- #
def m43():
    d = "2027-02-22"
    c = calc([("Microsoft Office LTSC Professional Plus 2024, Volumenlizenz Education, Einzelplatz", 15, "118.50")])
    wps = f"""
WPS · Katalog "Software / Campuslizenzen" · Rahmenvertrag Microsoft-Software-Produkte (Hochschul-Landeslizenz)
Warenkorb WK-0027-01733 · Besteller: Hannes Dörr (IT-Beauftragter FB 07) · Datum {iso(d)} · Status: bestellt

 Art.-Nr.     Bezeichnung                                                            Menge   Preis netto   Summe netto
 MS-OLT-24E   Office LTSC Professional Plus 2024, Education, Volumenlizenz              15    {eur(D("118.50")):>9}     {eur(c['net']):>9}
                                                                          Warenwert netto {eur(c['net']):>9} EUR
                                                                          USt. 19 %       {eur(c['vat']):>9} EUR
                                                                          Gesamt brutto   {eur(c['gross']):>9} EUR
 Lieferung: Lizenzschlüssel per E-Mail an die IT-Beauftragten, keine Datenträger. Kontierung: Kostenstelle 07-9120.
 Hinweis: Lizenzen werden ausschließlich über das WPS im Rahmen der Hochschul-Sammellizenz bezogen. Für Citavi und Sophos
 bestehen Campuslizenzen mit zentraler Kostenübernahme - diese sind nicht Teil dieser Bestellung.
"""
    mail = f"""
Subject: WPS WK-0027-01733 - Office-Lizenzen für das Pool-Labor
From: Hannes Dörr <h.doerr@uni-wernstadt.example>
To: Prof. Dr. Dagmar Brüning
Date: {WD_EN[dt(d).weekday()]}, {dt(d).day:02d} Feb 2027 08:41 +0100

Sehr geehrte Frau Brüning,

die 15 Office-Lizenzen für den Pool-Raum bestelle ich aus dem Microsoft-Rahmenvertrag im WPS ({eur(c['net'])} EUR netto).
Vergleichsangebote sind nicht nötig, weil es sich um ein Rahmenvertragsprodukt handelt. Bitte um Ihre Freigabe als
Kostenstellenbevollmächtigte.

Viele Grüße, H. Dörr

--- Antwort ---
Freigabe erteilt. D. Brüning, {de(d)}, 09:30
"""
    docs = [doc("WPS_Software_WK-0027-01733.pdf", wps, font="Helvetica", margin=20),
            doc("Freigabe_Lizenzen.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m43",
         "Fünfzehn Office-Lizenzen aus dem Microsoft-Rahmenvertrag der Hochschul-Sammellizenz über WPS (1.777,50 EUR netto), keine Vergleichsangebote nötig. "
         "Zentrale Campuslizenzen (Citavi, Sophos) sind ausdrücklich nicht Teil der Bestellung. Freigabe der Kostenstellenbevollmächtigten.", docs,
         "WPS software-catalogue print, mail with 'Antwort' block",
         "software licences, 1.700+ EUR without offers; campus licences named but not part of the order",
         "Rule: „Derzeit existieren Rahmenverträge u.a. für … Software-Produkte von Microsoft.“ + „Für Sophos … und Citavi … sind Campus-Lizenzen vereinbart – Die Kosten für diese werden zentral getragen.“ [" + S_RV + "] + „Die Beschaffung der Lizenzen erfolgt über das WPS-System.“ [policy-pages/software-campuslizenzen.md]")


# --------------------------------------------------------------------------- #
# m44  copy paper from the paper framework contract; minimum order value met
# --------------------------------------------------------------------------- #
def m44():
    d = "2027-08-09"
    c = calc([("Kopierpapier A4, 80 g/m², weiß, Karton à 5 x 500 Blatt", 60, "21.90")])
    wps = f"""
WPS - Bestellbestätigung                                          Bestelldatum {de(d)}   Bestellnummer 4500 27 7731
=======================================================================================================
Rahmenvertrag Büro- und Kopierpapier (Beschaffungsstelle des Landes) · Vertragspartner: Papierhandel Hohenlohe GmbH
Besteller: Zentrale Materialwirtschaft im Auftrag von Frau Mareike Sander (Dekanat FB 03, Kostenstelle 03-0001)

 Pos  Artikel                                                      Menge ME     Preis netto    Summe netto
 10   Kopierpapier A4 80 g weiß, 5 x 500 Blatt                       60 KT        {eur(D("21.90")):>8}     {eur(c['net']):>9}

 Liefertermin: {de(add(d, 7))} · Lieferstellen: Gebäude A (20 KT), Gebäude B (20 KT), Gebäude C (20 KT)
 Mindestbestellwert des Rahmenvertrags (50,00 EUR) erreicht: Warenwert {eur(c['net'])} EUR netto.
 Briefhüllen und Versandtaschen sind nicht Teil dieser Bestellung (derzeit kein Rahmenvertrag).
 USt. 19 % {eur(c['vat'])} EUR · Gesamt {eur(c['gross'])} EUR
=======================================================================================================
"""
    mail = f"""
Von: Mareike Sander
An: Zentrale Materialwirtschaft
Kopie: Dekan Prof. Dr. Ulrich Bohnsack
Betreff: Papierbestellung Dekanat und Fachgebiete (Rahmenvertrag)

Bitte 60 Kartons Kopierpapier aus dem Rahmenvertrag wie in der Aufstellung bestellen (je 20 Kartons an die drei Gebäude).
Es werden keine Vergleichsangebote eingeholt, da das Papier unter den Rahmenvertrag fällt.
Der Dekan hat als Kostenstellenbevollmächtigter zugestimmt (siehe Cc, "ok, B.").
"""
    docs = [doc("Bestellbestaetigung_4500277731.pdf", wps, margin=20),
            doc("Mail_Papier.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m44",
         "Sechzig Kartons Kopierpapier beim Rahmenvertragspartner für Büro- und Kopierpapier, Mindestbestellwert von 50 EUR erreicht, keine Vergleichsangebote. "
         "Briefhüllen ausdrücklich nicht enthalten. Dekan hat zugestimmt.", docs,
         "SAP/WPS order confirmation with unit codes (KT) and delivery split, short mail",
         "1.314 EUR without any offer; minimum order value stated; envelopes (no framework) explicitly excluded; approval is a quoted 'ok, B.'",
         "Rule: „Das HCC-Zentrale Beschaffungsstelle des Landes Hessen hat einen Rahmenvertrag für die Beschaffung von Büro- und Kopierpapier abgeschlossen. Die Bestellungen sind über das WPS-System zu buchen.“ + „Der Mindestbestellwert der Fa. Berberich beträgt 50,00 €.“ [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m45  additional multifunction device on rental from the copier framework contract
# --------------------------------------------------------------------------- #
def m45():
    d = "2027-01-18"
    rent = D("39.90")
    months = 38
    antrag = f"""
UNIVERSITÄT WERNSTADT · Zentrale Materialwirtschaft                                    Bestellformular M-KOP
Miete von Kopier- und Multifunktionssystemen - Abruf aus dem Rahmenvertrag (Laufzeit 01.04.2025 bis 31.03.2030)
===========================================================================================================
Bedarfsstelle     Institut für Sozialforschung (FB 03), Sekretariat · Ansprechpartnerin Lena Bruckmann
Gerät             Multifunktionssystem Leistungsklasse LK 3 (Farbe, A4/A3), Follow-me-Printing über Campuscard
Anzahl            2 Geräte (Standorte: Flur 1. OG und Doktorandenraum)       Lieferung bis {de(add(d, 28))}
Miete             je Gerät {eur(rent)} EUR netto monatlich laut Mietkostenliste LK 3 des Rahmenvertrags
                  = {eur(rent * 2)} EUR netto monatlich; Mietdauer bis Vertragsende 31.03.2030 ({months} Monate ab {de(add(d, 28))}, gerundet)
Kostenumlage      je Kopier-/Druckvorgang über die Rahmenvertragsumlage (enthält Wartung, Papier, Toner)
Angebote          keine - Rahmenvertragsprodukt; Vergleichsangebote entfallen
Ersatz            die zwei vorhandenen Arbeitsplatzdrucker werden ausgesondert (Verzicht auf Arbeitsplatzgeräte)
Kostenstelle      03-0900 (interne Kostenverrechnung)
Beauftragt        Prof. Dr. Waltraud Imhoff-Stenzel, Kostenstellenbevollmächtigte · {de(d)}
===========================================================================================================
"""
    mail = f"""
Von:      Lena Bruckmann
An:       Zentrale Materialwirtschaft; ITS-Servicedesk
Betreff:  Zusatzgeräte Kopiersystem LK 3 - Bestellformular M-KOP anbei
Datum:    {WD_L[dt(d).weekday()]}, {de(d)}

Guten Tag,

anbei das ausgefüllte Formular für zwei weitere Multifunktionsgeräte aus dem Kopierer-Rahmenvertrag. Die Geräte sollen
als Drucksysteme (Follow-me-Printing mit Campuscard) laufen, die Arbeitsplatzdrucker im Sekretariat entfallen damit.
Bitte um Rückmeldung zum Liefertermin. Vergleichsangebote sind nicht vorgesehen, weil der Rahmenvertrag verbindlich ist.

Freundliche Grüße, L. Bruckmann
"""
    docs = [doc("Bestellformular_M-KOP.pdf", antrag, margin=22),
            doc("Anschreiben.pdf", mail, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m45",
         "Zwei zusätzliche Multifunktionsgeräte werden aus dem Miet-Rahmenvertrag für Kopiersysteme abgerufen (Mietkostenliste LK 3, Laufzeit bis 31.03.2030), "
         "keine Vergleichsangebote, Arbeitsplatzdrucker entfallen. Beauftragt durch die Kostenstellenbevollmächtigte.", docs,
         "central purchasing order form for rental (Courier), cover mail",
         "rental over several years with no offers; running per-page charge instead of a fixed price; devices replace printers",
         "Rule: „Für die Universität … wurde ein Rahmenvertrag über die Miete von Kopier- und Multifunktionssystemen sowie Druckern … abgeschlossen. Dieser hat eine Laufzeit vom 01.04.2025 bis zum 31.03.2030.“ + „Die Rahmenverträge sind verbindlich für alle Bereiche der [Universität].“ [" + S_RV + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m46  below 1,000 EUR with one offer; price check printout; SAP display screen
# --------------------------------------------------------------------------- #
def m46():
    d = "2027-11-03"
    c = calc([("Lötzinn bleifrei 0,5 mm, 500 g Spule", 6, "38.90"),
              ("Entlötlitze 2,0 mm, 3 m", 20, "4.85"),
              ("Lötspitzen-Satz für Lötstation, 5 Stück", 4, "29.50"),
              ("ESD-Arbeitsmatte 60 x 50 cm", 3, "41.70"),
              ("Flussmittel-Stift", 10, "8.95")])
    assert c["net"] < 1000
    vendor = V("Elektronikbedarf Nolte e. K.", "Gartenstr. 18", "48143 Münster", "angebot@nolte-elektronik.example", contact_name="Gerd Nolte")
    off = quote_mail(vendor, "NA-27-6620", add(d, -5), "Selma Ehrenberg <s.ehrenberg@uni-wernstadt.example>", c, "Angebot NA-27-6620 Lötbedarf")
    sap = f"""
Bestellanforderung anzeigen                                                    ME53N   Benutzer: EHRENBERG
------------------------------------------------------------------------------------------------------------
BANF 10 0049 1127     Belegart NB     Status: freigegeben (Freigabecode K3)         Erstellt am {de(d)}
 Pos  Warengruppe    Kurztext                                       Menge  ME  Preis netto   Gesamt netto
 10   VERBRAUCH      Lötzinn bleifrei 0,5 mm 500 g                    6    ST     38,90        233,40
 20   VERBRAUCH      Entlötlitze 2,0 mm 3 m                          20    ST      4,85         97,00
 30   VERBRAUCH      Lötspitzen-Satz 5 St.                            4    ST     29,50        118,00
 40   VERBRAUCH      ESD-Arbeitsmatte 60x50                           3    ST     41,70        125,10
 50   VERBRAUCH      Flussmittel-Stift                               10    ST      8,95         89,50
                                                              Gesamtwert netto  {eur(c['net']):>9} EUR
 Kopftext:  Direktvergabe: Auftragswert {eur(c['net'])} EUR netto (unter 1.000 EUR), ein Angebot (NA-27-6620 vom {de(add(d, -5))}).
            Preisangemessenheit geprüft: Preisvergleich in HELF am {de(add(d, -2))} (Ausdruck anbei): Angebot liegt 4 % unter dem
            günstigsten Listenpreis ({eur(r2(c['net'] * D("1.04")))} EUR netto). Kein Rahmenvertragsprodukt.
 Zuordnung: Kostenstelle 16-2290 · Freigabe: Prof. Dr. Ludwig Hasenclever (Kostenstellenbevollmächtigter) {de(add(d, 1))}
"""
    helf = f"""
HELF · Preisvergleich Hochschul-Einkauf                           Abfrage {de(add(d, -2))}, 16:48
Warenkorb: Lötbedarf (5 Positionen, gleiche Mengen wie Angebot NA-27-6620)

  Anbieter                          Summe netto     Versand
  Elektronikbedarf Nolte e. K.      {eur(c['net']):>9}      frei    (Angebot, NA-27-6620)
  Löttechnik-Direkt GmbH            {eur(r2(c['net'] * D("1.04"))):>9}     5,90     (Listenpreis)
  Werkstattwelt Online              {eur(r2(c['net'] * D("1.08"))):>9}      frei     (Listenpreis)
Ergebnis: günstigstes Angebot ist das vorliegende.
"""
    docs = [doc("BANF_10-0049-1127_ME53N.pdf", sap, margin=18),
            doc("HELF_Preisvergleich.pdf", helf, font="Helvetica"),
            doc("NA-27-6620.pdf", off, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m46",
         "Lötbedarf über " + eur(c["net"]) + " EUR netto mit nur einem Angebot: unter 1.000 EUR ist eine Direktvergabe möglich; die Angemessenheit des Preises wurde zusätzlich im Preisvergleichsportal geprüft. "
         "Kein Rahmenvertragsprodukt, freigegeben durch den Kostenstellenbevollmächtigten.", docs,
         "SAP display screen ME53N with 'freigegeben' status, HELF price-check print, mail-style vendor offer",
         "one offer only (explicit 'Direktvergabe'); the price check shows two cheaper-looking vendors with higher totals",
         "Rule: „Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ [" + S_CAT + "] + „Wir empfehlen aus Gründen der Wirtschaftlichkeit und Sparsamkeit grundsätzlich Preisvergleiche in HELF vorzunehmen.“ [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m47  fixed asset purchase (3D printer) with asset data; warranty and cables booked as expense
# --------------------------------------------------------------------------- #
def m47():
    d = "2027-10-04"
    unit = to_uw("Fachgebiet Konstruktionstechnik, FB 12", "Dr. Alina Hoffmeister")
    cA = calc([("3D-Drucker FDM 'ProBuild X2', Bauraum 300x300x400 mm, Dualextruder", 1, "4350.00"),
               ("Garantieverlängerung auf 36 Monate", 1, "189.00"),
               ("Kabel- und Zubehörsatz", 1, "24.00")])
    cB = calc([("Industrial 3D printer 'FormLine 400', build volume 300x300x400 mm, dual extruder", 1, "4580.00"),
               ("Extended warranty (36 months)", 1, "210.00")])
    cC = calc([("3D-Drucksystem 'Layerwerk L4', 300x300x400 mm, 2 Extruder", 1, "4720.00"),
               ("Garantieverlängerung 36 Monate", 1, "195.00"),
               ("Anschlusskabel und Zubehörsatz", 1, "30.00")])
    assert cA["net"] < cB["net"] < cC["net"]
    erfassung = f"""
Anlagenerfassung (Anlage zur Bestellanforderung)                                           {de(add(d, 9))}
-----------------------------------------------------------------------------------------------------------------
Bestellanforderung 10 0050 2217       Lieferant: Prototyp-Technik Bergmann GmbH, Angebot PB-27-0933 vom {de(add(d, -10))}

 Pos  Bezeichnung                                              Netto EUR     Behandlung
 10   3D-Drucker ProBuild X2 (Fabrikat Bergmann), Dualextruder   {eur(D("4350.00")):>9}   ANLAGE (selbstständig nutzbar, Nettoeinzelpreis über 800,01 EUR)
 20   Garantieverlängerung 36 Monate                              {eur(D("189.00")):>9}   AUFWAND (Garantieerweiterung)
 30   Kabel- und Zubehörsatz                                      {eur(D("24.00")):>9}   AUFWAND (Kabel)
      Summe netto                                                {eur(cA['net']):>9}

 Bezeichnung der Anlage (sprechend): 3D-Drucker ProBuild X2 FDM, Fachgebiet Konstruktionstechnik
 Standort (endgültig): Gebäude D, Raum D 1.15 · Kostenstelle 12-5040 · Auftrag 2142003
 Gleichartige Anlagen: nein (Einzelgerät) · Inzahlungnahme eines Altgeräts: nein
 Angebote: 3 (Bergmann {eur(cA['net'])} · FormLine {eur(cB['net'])} · Layerwerk {eur(cC['net'])} EUR netto); günstigstes gewählt.
 Freigabe: Prof. Dr. Reinhild Katzenberger, Kostenstellenbevollmächtigte, {de(add(d, 9))}
"""
    docs = [doc("Anlagenerfassung_3D-Drucker.pdf", erfassung, margin=20),
            doc("Angebot_PB-27-0933.pdf", quote_classic(V("Prototyp-Technik Bergmann GmbH", "Zeppelinstr. 8", "88045 Friedrichshafen", None, "07541 55 01 2"),
                                                       "PB-27-0933", add(d, -10), add(d, 20), unit, cA)),
            doc("Quotation_FL400.pdf", quote_en(V("FormLine Additive Ltd.", "Unit 7 Mill Lane", "Leeds LS11 5AB, UK"), "Q-2027-1442", add(d, -9), add(d, 21),
                                              ["Universität Wernstadt", "Konstruktionstechnik"], cB, note="  Delivered duty paid, EUR prices."), font="Helvetica"),
            doc("Angebot_Layerwerk.pdf", quote_letter(V("Layerwerk Systeme GmbH", "Gewerbepark 3", "01109 Dresden", None, None, "Uta Schlegel"),
                                                      "LW-27-0518", add(d, -8), unit, cC, "3D-Drucksystem L4"), font="Times-Roman")]
    case(PROC, "beschaffungsantrag-m47",
         "3D-Drucker (4.350,00 EUR netto) als Anlage mit sprechender Bezeichnung, Standort und Hinweis auf Einzelgerät; Garantieerweiterung und Kabel sind als Aufwand getrennt erfasst. "
         "Drei Angebote, das günstigste (4.563,00 EUR netto insgesamt) gewählt, Freigabe liegt vor.", docs,
         "asset-capture sheet (Courier) split into asset vs expense lines, offers: classic / English from the UK / letter",
         "same order has an 'ANLAGE' line and 'AUFWAND' lines; the cheapest total is chosen though bid lines differ (cable set missing in one offer)",
         "Rule: „Anlagen: > 410,00 € netto/Gerät“ / „Anschaffungen ab 800,01 € … selbstständig nutzbares Gerät“; „Die Bezeichnung der Anlage muss sprechend sein“; „Die Raum- und Gebäudenummern sind für den endgültigen Standort der Anlage anzugeben“; „Garantieerweiterungen, Wartung, Kabel etc. sind als Aufwand zu erfassen“ [" + S_ANL + "] + „Grundsätzlich müssen 3 Angebote eingeholt werden“ [" + S_BESCH + "]")


# --------------------------------------------------------------------------- #
# m48  spare part available from one source only, reason documented (LOW)
# --------------------------------------------------------------------------- #
def m48():
    d = "2027-04-26"
    c = calc([("Original-Detektormodul DM-4 für Massenspektrometer MS-300 (Seriennr. 20-8841)", 1, "2380.00"),
              ("Einbau und Justage durch Hersteller-Service", 1, "70.00")])
    antrag = f"""
Von:      Dr. Rolf Zimmerling-Aust <r.zimmerling-aust@uni-wernstadt.example>
Gesendet: Montag, {dlong(d)} 09:18
An:       beschaffung@uni-wernstadt.example
Kopie:    Prof. Dr. Lioba Hartenstein-Voigt
Betreff:  Ersatzteilbeschaffung Massenspektrometer - nur ein Angebot (Begründung)

Sehr geehrte Damen und Herren,

am Massenspektrometer MS-300 ist das Detektormodul ausgefallen. Wir bitten um Bestellung des Original-Moduls beim
Hersteller-Vertrieb (Angebot 27-S-0418, {eur(c['net'])} EUR netto). Es liegt nur dieses eine Angebot vor. Begründung:
Das Modul ist herstellerspezifisch (Steckverbindung, Firmware und Kalibrierung), kompatible Nachbauten anderer Anbieter
existieren nicht, und der Hersteller hat schriftlich bestätigt, dass er das Modul in Deutschland ausschließlich selbst
liefert (Bestätigung anbei). Eine Einholung von drei Vergleichsangeboten ist daher nicht möglich. Rahmenvertragsprodukt:
nein. Kostenstelle 14-4410.

Frau Prof. Hartenstein-Voigt als Kostenstellenbevollmächtigte hat in Kopie zugestimmt und beauftragt.

Mit freundlichen Grüßen
Rolf Zimmerling-Aust
"""
    herst = f"""
Spektra Analytik GmbH · Servicezentrale · Bahnhofstr. 41 · 65185 Wiesbaden

Bestätigung zum Ersatzteil DM-4                                                  {de(add(d, -6))}

Hiermit bestätigen wir, dass das Detektormodul DM-4 für das Massenspektrometer MS-300 ausschließlich von der Spektra
Analytik GmbH hergestellt und in Deutschland nur direkt über unseren Service vertrieben wird. Kompatible
Austauschmodule Dritter sind nicht freigegeben; ihr Einsatz würde die Gerätegarantie und die Kalibrierung beenden.

Angebot 27-S-0418: Modul {eur(c['lines'][0][3])} EUR netto, Einbau und Justage {eur(c['lines'][1][3])} EUR netto, zusammen {eur(c['net'])} EUR netto.
"""
    docs = [doc("Mail_Ersatzteil.pdf", antrag, margin=22),
            doc("Herstellerbestaetigung_DM-4.pdf", herst, font="Times-Roman")]
    case(PROC, "beschaffungsantrag-m48",
         "Ersatzteil für ein vorhandenes Messgerät (2.450,00 EUR netto), das nach Herstellerbestätigung nur direkt vom Hersteller geliefert wird; es liegt nur ein Angebot vor, "
         "der Grund für das Fehlen weiterer Angebote ist ausführlich und belegt begründet. Kein Rahmenvertrag, Beauftragung durch die Kostenstellenbevollmächtigte.", docs,
         "mail print with written reason for the single offer, manufacturer's exclusivity letter (Times)",
         "2.450 EUR with ONE offer, allowed only because a documented single-source reason exists (not a threshold exemption)",
         "Rule: „Grundsätzlich müssen 3 Angebote eingeholt werden“ [" + S_BESCH + "]; the policy pages do not name a single-source exception, so this case rests on the documented impossibility of comparable offers.",
         conf="low")


# --------------------------------------------------------------------------- #
# m49  collective order of small lab items from a web shop, below 1,000 EUR
# --------------------------------------------------------------------------- #
def m49():
    d = "2027-12-07"
    c = calc([("Widerstands-Sortiment E12, 1/4 W, 1200 St.", 2, "24.90"),
              ("Kondensator-Sortiment Keramik, 600 St.", 2, "31.40"),
              ("Schrumpfschlauch-Set 328 St., sortiert", 4, "14.95"),
              ("Steckbrücken 2,54 mm, 100 St.", 5, "6.20"),
              ("Flachbandkabel 20-polig, 50 m", 2, "38.50"),
              ("Feinsicherungen-Sortiment 5x20 mm, 100 St.", 6, "12.35"),
              ("Kabelbinder 200 mm, 1000 St.", 3, "17.90"),
              ("Epoxid-Platinenzuschnitt 100x160 mm, einseitig", 20, "5.95"),
              ("Mindermengenzuschlag", 1, "7.50")], shipping="6.90")
    assert c["net"] < 1000
    rows = "\n".join(f"  {i:>2}  {x[0]:<54} {x[1]:>3}  {eur(x[2]):>8}  {eur(x[3]):>9}" for i, x in enumerate(c["lines"], 1))
    shop = f"""
https://shop.elektro-baumarkt-lenz.example/warenkorb                                         {iso(d)} 10:12
Warenkorb (9 Positionen) · Kundenkonto: Universität Wernstadt, FG Leistungselektronik
----------------------------------------------------------------------------------------------
  Nr  Artikel                                                 Menge   Einzel netto   Gesamt netto
{rows}
  Versand (DHL Paket)                                                                {eur(c['ship']):>9}
----------------------------------------------------------------------------------------------
  Zwischensumme netto                                                                {eur(c['net']):>9}
  USt. 19 %                                                                          {eur(c['vat']):>9}
  Gesamt brutto                                                                      {eur(c['gross']):>9}
  Zahlungsart: Rechnung (Zahlungsziel 14 Tage) - Rechnungsadresse: Universität Wernstadt, Zentraler Rechnungseingang
"""
    mail = f"""
Von:      Hendrik Alswede <h.alswede@uni-wernstadt.example>
Gesendet: {WD_L[dt(d).weekday()]}, {dlong(d)} 10:31
An:       beschaffung@uni-wernstadt.example
Cc:       Prof. Dr. Kunigunde Waldmüller
Betreff:  Sammelbestellung Elektronikbauteile Praktikum - Direktvergabe

Hallo zusammen,

für das Elektronikpraktikum im Wintersemester brauchen wir die Bauteile aus dem Warenkorb (Anhang): acht Positionen plus
Mindermengenzuschlag und Versand, insgesamt {eur(c['net'])} EUR netto. Das ist unter 1.000 EUR, deshalb Direktvergabe ohne
weitere Angebote; es handelt sich nicht um Büromaterial oder IT-Geräte aus den Rahmenverträgen. Kostenstelle 13-7710.
Prof. Waldmüller (Cc) ist einverstanden und gibt die Bestellung als Kostenstellenbevollmächtigte hiermit frei.

Danke und Gruß, Hendrik
"""
    docs = [doc("Warenkorb_Lenz_20271207.pdf", shop, font="Helvetica", margin=20, creator="Chromium"),
            doc("Sammelbestellung_Mail.pdf", mail, margin=22)]
    case(PROC, "beschaffungsantrag-m49",
         "Sammelbestellung von Elektronikbauteilen für ein Praktikum über " + eur(c["net"]) + " EUR netto (acht Positionen, Mindermengenzuschlag, Versand): unter 1.000 EUR, Direktvergabe ohne Vergleichsangebote, "
         "keine Rahmenvertragsprodukte (Bauteile). Freigabe durch die Kostenstellenbevollmächtigte in Kopie.", docs,
         "web-shop basket print with surcharge and shipping lines, mail with approval in Cc",
         "nine positions in one order (looks like a bundle) but the net total is under 1.000 EUR; surcharge line is an item row",
         "Rule: „Diese Pflicht entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“ [" + S_CAT + "]; Elektronikbauteile gehören nicht zu den Rahmenverträgen („u.a. für Büromaterial, PC's/Notebooks und Monitore, …“) [" + S_RV + "]")


# --------------------------------------------------------------------------- #
# m50  one mail, two procurement processes: monitors via framework, instrument with 3 offers
# --------------------------------------------------------------------------- #
def m50():
    d = "2027-05-25"
    unit = to_uw("Fachgebiet Messtechnik, FB 16", "Frau Dr. Elfriede Brockmann")
    mon = calc([("Monitor 27 Zoll WQHD, USB-C, höhenverstellbar, Vertragsartikel", 2, "218.60")])
    dev = [calc([("Digitalmultimeter 6½-stellig, Tisch, USB/LAN, Kalibrierschein", 1, "2380.00")]),
           calc([("Tischmultimeter 6,5 Digit mit LAN/USB und Kalibrierzertifikat", 1, "2455.00")]),
           calc([("6½-digit bench multimeter, USB/LAN, with calibration certificate", 1, "2590.00")], vat=0)]
    mail = f"""
Von:      Elfriede Brockmann <e.brockmann@uni-wernstadt.example>
Gesendet: Dienstag, {dlong(d)} 14:07
An:       beschaffung@uni-wernstadt.example
Cc:       Prof. Dr. Joost Kleinschmidt
Betreff:  Zwei Bestellvorgänge FG Messtechnik: (1) Monitore Rahmenvertrag, (2) Tischmultimeter

Sehr geehrte Damen und Herren,

wir haben zwei getrennte Beschaffungen, die ich bewusst in einer Mail zusammenfasse:

(1) Zwei Monitore. Sie stammen aus dem IT-Rahmenvertrag und stehen im WPS-Warenkorb WK-0027-06120
    ({eur(mon['net'])} EUR netto). Es werden keine Angebote eingeholt, die Bestellung läuft ausschließlich über WPS.

(2) Ein Tischmultimeter (6½-stellig), kein Rahmenvertragsprodukt. Auftragswert {eur(dev[0]['net'])} EUR netto, daher drei Angebote:
       Metrologie Kaiser GmbH     {eur(dev[0]['net'])} EUR   <- günstigstes
       Prüfgeräte Dahlmann KG     {eur(dev[1]['net'])} EUR
       Precision Instruments NV   {eur(dev[2]['net'])} EUR
    Bitte bei Metrologie Kaiser GmbH bestellen (Angebot MK-27-2290).

Beide Vorgänge sind unabhängige Anschaffungen (andere Lieferanten, anderer Verwendungszweck); die Summen werden nicht
zusammengerechnet. Kostenstelle 16-7003. Herr Prof. Kleinschmidt hat beide Bestellungen als Kostenstellenbevollmächtigter freigegeben.

Mit freundlichen Grüßen
Elfriede Brockmann
"""
    wps = f"""
WPS · Warenkorb WK-0027-06120                      Katalog: Rahmenvertrag IT-Arbeitsplatzgeräte (Monitore)
Lieferant: Rhein-Main IT Systemhaus GmbH           Besteller: E. Brockmann                    Datum {iso(d)}
  RV-MO-27-0415   Monitor 27", WQHD, USB-C, höhenverstellbar     2 ST     218,60 EUR      437,20 EUR
  Warenwert netto {eur(mon['net'])} EUR · USt. 19 % {eur(mon['vat'])} EUR · brutto {eur(mon['gross'])} EUR
  Kontierung 16-7003 · Status: zur Bestellung freigegeben
"""
    offs = pages(
        quote_classic(V("Metrologie Kaiser GmbH", "Messeplatz 2", "90471 Nürnberg", None, "0911 30 11 7"), "MK-27-2290", add(d, -9), add(d, 21), unit, dev[0]),
        quote_letter(V("Prüfgeräte Dahlmann KG", "Am Kanal 17", "30167 Hannover", None, None, "Rita Dahlmann"), "PD-27/611", add(d, -8), unit, dev[1], "Tischmultimeter 6,5 Digit"),
        quote_en(V("Precision Instruments NV", "Kortrijksesteenweg 88", "9000 Gent, Belgium"), "PI-27-3071", add(d, -7), add(d, 23),
                 ["Universität Wernstadt", "Fachgebiet Messtechnik"], dev[2], note="  Intra-Community supply, reverse charge."))
    docs = [doc("Mail_zwei_Vorgaenge.pdf", mail, margin=22),
            doc("WPS_WK-0027-06120.pdf", wps, font="Helvetica"),
            doc("Angebote_Multimeter.pdf", offs, font="Helvetica")]
    case(PROC, "beschaffungsantrag-m50",
         "Eine Mail enthält zwei unabhängige Beschaffungen: Monitore (437,20 EUR netto) aus dem IT-Rahmenvertrag über WPS ohne Angebote, und ein Tischmultimeter (2.380,00 EUR netto) mit drei Angeboten, "
         "günstigstes gewählt. Beide sind korrekt abgewickelt und vom Kostenstellenbevollmächtigten freigegeben.", docs,
         "mail print explaining two separate processes, WPS basket, merged three-page offers PDF",
         "one mail with two procurement routes: the framework part has no offers, the other part has three; the text states the totals are not to be added",
         "Rule: „Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“ [" + S_BESCH + "] + „Bei Beschaffungen aus dem Rahmenvertrag für IT-Systeme gilt die Zustimmung des ITS als erteilt.“ [" + S_GF + "]",
         conf="high")


# =========================================================================== #
# EXPENSE REFUNDS  (auslagenerstattung-m51 .. m75)
# =========================================================================== #
def till(head, items, vat_lines, foot, pay="BAR", given=None, w=38):
    """narrow till receipt; items: (name, qty, unit_price) ; returns (text, total)"""
    out = list(head) + ["-" * w]
    total = D("0.00")
    for name, q, u in items:
        t = r2(D(q) * D(u))
        total += t
        for k, part in enumerate(textwrap.wrap(name, w - 2) or [""]):
            out.append(part)
        out.append(f"{q} x {eur(u)}".ljust(w - 10) + eur(t).rjust(10) if q != 1 else " " * (w - 10) + eur(t).rjust(10))
    total = r2(total)
    out += ["-" * w, "SUMME EUR".ljust(w - 10) + eur(total).rjust(10)]
    if given is not None:
        out += [f"{pay} {eur(given)}".ljust(w), f"RÜCKGELD {eur(r2(D(given) - total))}"]
    else:
        out += [pay]
    out += list(vat_lines) + [""] + list(foot)
    return "\n".join(out), total


def invoice(v, no, date_, to_lines, c, lang="de", head_extra=(), foot=(), cur="EUR", ref=""):
    """generic net invoice in de / en / fr / it / nl"""
    T = {"de": ("RECHNUNG", "Nr.", "Datum", "Bezeichnung", "Menge", "Einzelpreis", "Gesamt", "Summe netto", "USt.", "Rechnungsbetrag", eur),
         "en": ("INVOICE", "No.", "Date", "Description", "Qty", "Unit price", "Amount", "Subtotal", "VAT", "Total due", eng),
         "fr": ("FACTURE", "n°", "Date", "Désignation", "Qté", "Prix unitaire", "Montant", "Total HT", "TVA", "Net à payer", fr),
         "it": ("FATTURA", "n.", "Data", "Descrizione", "Q.ta", "Prezzo unit.", "Importo", "Imponibile", "IVA", "Totale fattura", eur),
         "nl": ("FACTUUR", "nr.", "Datum", "Omschrijving", "Aantal", "Prijs", "Totaal", "Subtotaal", "BTW", "Totaal te betalen", eur)}[lang]
    title, nr, dat, desc, qty, unitp, amt, sub, vat, totl, f = T
    datef = {"de": de, "en": den, "fr": dfr, "it": dit, "nl": dnl}[lang](date_)
    rows = [[desc, qty, unitp, amt]]
    for d_, q, u, t in c["lines"]:
        rows.append([d_, q, f(u), f(t)])
    tab = grid(rows, [50, 5, 12, 12], ["l", "r", "r", "r"], indent=1)
    sums = [f"{sub}  {f(c['net']):>12}"]
    if c["rate"]:
        sums.append(f"{vat} {c['rate']} %  {f(c['vat']):>12}")
    sums.append(f"{totl} {cur}  {f(c['gross']):>12}")
    return f"""
{v["name"]}
{v["street"]} · {v["city"]}
{chr(10).join(head_extra)}

{chr(10).join(to_lines)}


{title} {nr} {no}                                    {dat}: {datef}   {ref}

{tab}

{chr(10).join(" " * 44 + s for s in sums)}

{chr(10).join(foot)}
"""


def stmt(holder, bank, rows, closing=""):
    """card / account statement; rows = (date, text, amount_str)"""
    body = "\n".join(f"  {a:<12}{b:<62}{c:>14}" for a, b, c in rows)
    return f"""
{bank}                                                          Umsatzübersicht
Karteninhaber/in: {holder}

  Buchung     Verwendungszweck / Umsatz                                                  Betrag EUR
  ----------------------------------------------------------------------------------------------
{body}
  ----------------------------------------------------------------------------------------------
{closing}
"""


# --------------------------------------------------------------------------- #
# m51  till receipt with abbreviated article names and a keyword added by hand
# --------------------------------------------------------------------------- #
def m51():
    d = "2027-03-18"
    txt, total = till(["BAUZENTRUM HELLWIG", "Zum Gewerbepark 4", "58095 Hagen", "Tel. 02331 4471"],
                      [("SCHLEIFP.K120 BOGEN 10ST", 2, "5.49"), ("GEWEBEBAND 50MM SW", 1, "6.95"), ("EINMALHANDSCH.NITRIL 100", 1, "9.49")],
                      ["MWST 19% NETTO 23,04 MWST 4,38"], [f"BON 8841 KASSE 02 {de2(d)} 10:42", "St.-Nr. 321/5870/4417", "VIELEN DANK FÜR IHREN EINKAUF"],
                      pay="BAR", given="30.00")
    note = f"""

 [handschriftlich:]
 Schleifpapier, Gewebeband,
 Handschuhe für Probenhalter-
 Bau im Labor E 3.12
 (dringend, Werkstatt zu)
 M. Eisenhut, FG Mikrofluidik
 Kst. 15-3320
"""
    docs = [doc("Kassenbon_Hellwig.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m51",
         "Kassenbon eines Baumarkts über " + eur(total) + " EUR mit abgekürzten Artikelbezeichnungen (Schleifpapier, Gewebeband, Nitril-Handschuhe), handschriftlich ergänzt um Verwendungszweck, Raum und Kostenstelle. "
         "Kleine, zeitlich dringende Anschaffung für das Labor, Beleg im Original, Beträge gehen auf.", docs,
         "narrow till receipt with abbreviations (SCHLEIFP., EINMALHANDSCH.) and a typed 'handschriftlich' block",
         "article lines abbreviated, but a purpose note is written on the receipt; payment in cash with change",
         "Rule: " + Q_KOSTENERST + " + " + Q_STICHWORT + " [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m52  web-shop invoice (gross prices) with a voucher line and PayPal receipt
# --------------------------------------------------------------------------- #
def m52():
    d = "2027-05-04"
    p1, p2, ship, vou = D("39.90"), D("27.50"), D("4.90"), D("5.00")
    total = p1 + p2 + ship - vou
    inv = f"""
Werkzeug-Direkt24 GmbH · Industriepark Süd 5 · 74076 Heilbronn · USt-IdNr. DE 8 112 440 17

Universität Wernstadt
Fachgebiet Fertigungstechnik, FB 12
Hochschulring 21, 35291 Wernstadt

Rechnung RE-2027-0449127          Rechnungsdatum {iso(d)}          Bestellung 77-1182-90  (Online-Shop, {iso(d)})

 Pos  Artikel                                                  Menge     Preis brutto    Gesamt
  1   Maschinengewindebohrer-Satz M3-M12, HSS                     1        {eur(p1):>7} €     {eur(p1):>7} €
  2   Spiralbohrer-Set 1-10 mm, 19-teilig, Kassette               1        {eur(p2):>7} €     {eur(p2):>7} €
      Versandkosten (Paket)                                                {eur(ship):>7} €     {eur(ship):>7} €
      Gutschein NEUKUNDE5 (Aktionsrabatt)                                  -{eur(vou):>6} €    -{eur(vou):>6} €
 -----------------------------------------------------------------------------------------
 Rechnungsbetrag (brutto, bezahlt)                                                    {eur(total):>7} €
 enthaltene USt. 19 %: {eur(vat_split(total, 19)[1])} €   Netto: {eur(vat_split(total, 19)[0])} €

Der Betrag wurde per PayPal beglichen. Lieferung am {iso(add(d, 2))}.
"""
    pp = f"""
PayPal · Zahlungsbestätigung                                                  {de(d)}, 16:21 Uhr
Sie haben eine Zahlung über {eur(total)} EUR an Werkzeug-Direkt24 GmbH gesendet.

   Transaktionscode:  5KM71482GU305812X
   Zahlungsquelle:    Girokonto (privat)
   Verwendungszweck:  Bestellung 77-1182-90 / Rechnung RE-2027-0449127
   Gesamtbetrag:      -{eur(total)} EUR
"""
    docs = [doc("Rechnung_RE-2027-0449127.pdf", inv, font="Helvetica", margin=20),
            doc("paypal.pdf", pp, font="Helvetica")]
    case(EXP, "auslagenerstattung-m52",
         "Onlinerechnung an das Fachgebiet für Gewindebohrer- und Bohrersatz (Rechnungsbetrag " + eur(total) + " EUR nach Gutschein und Versand), per PayPal vom Privatkonto bezahlt; "
         "der PayPal-Betrag entspricht dem Rechnungsbetrag. Erstattet wird der tatsächlich gezahlte Betrag.", docs,
         "web-shop invoice with gross prices, a negative voucher line and a shipping line; PayPal confirmation",
         "voucher (-5,00) and shipping lines change the total; claim equals the amount actually paid, not the sum of item prices",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ (invoice addressed to the Fachgebiet, items named, amount proven by payment receipt) [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m53  GBP invoice, card statement with exchange rate and foreign-use fee
# --------------------------------------------------------------------------- #
def m53():
    d = "2027-06-15"
    c = calc([("Biopsy punches 4 mm, pack of 10", 2, "19.50"), ("Dissection kit, stainless steel, 12 pieces", 1, "32.00")], vat=20)
    rate = D("1.1632")
    eur_amt = conv(c["gross"], rate)
    fee = r2(eur_amt * D("0.0175"))
    inv = invoice(V("Peterborough Lab Supplies Ltd", "14 Fen Road", "Peterborough PE2 6QT, United Kingdom"), "PLS-2027-30417", d,
                  ["Bill to / ship to:", UW, "Biomechanics Group (FB 10)", "Hochschulring 21", "35291 Wernstadt, Germany"], c, "en",
                  head_extra=["VAT Reg. No. GB 331 4471 06"], cur="GBP",
                  foot=[f"Paid by credit card on {den(d)}. Thank you for your order.", "Items shipped by courier, tracking PLS/774120."])
    st = stmt("Dr. Greta Hollenbach", "Hainbuchen Bank AG · Kreditkartenabrechnung",
              [(de(add(d, 1)), f"PETERBOROUGH LAB SUP GBP {eng(c['gross'])} (Kurs {rate_eur(rate)})", f"-{eur(eur_amt)}"),
               (de(add(d, 1)), f"Auslandseinsatzentgelt 1,75 % von {eur(eur_amt)} EUR", f"-{eur(fee)}"),
               (de(add(d, 6)), "Buchhandlung am Markt, Marburg", "-23,90")],
              closing=f"  Abrechnung Visa ****4416 · für die Universität relevant: Zeilen 1 und 2 ({eur(eur_amt + fee)} EUR)")
    docs = [doc("invoice_PLS-2027-30417.pdf", inv, font="Helvetica", margin=22),
            doc("Kreditkartenabrechnung_Juni.pdf", st, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m53",
         "Englische Rechnung eines britischen Händlers in GBP an die Arbeitsgruppe, per privater Kreditkarte bezahlt; die Abrechnung zeigt den EUR-Betrag " + eur(eur_amt) + " EUR (Kurs 1,1632) und das "
         "Auslandseinsatzentgelt " + eur(fee) + " EUR. Geltend gemacht werden zusammen " + eur(eur_amt + fee) + " EUR, die privat andere Buchung bleibt außen vor.", docs,
         "English invoice (GBP, UK VAT), bank statement with exchange rate, foreign fee and an unrelated private line",
         "foreign currency; private bookshop line on the same statement is not claimed; the card fee is claimed as part of the actual cost",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]; foreign fee accepted in the organisers' practice case 08 (accepted case with USD fee). Doubt: fee reimbursement is not stated in the policy pages.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m54  Polish invoice (ASCII) in PLN for a book, card statement with conversion
# --------------------------------------------------------------------------- #
def m54():
    d = "2027-04-08"
    pln = D("189.00")
    rate = D("4.3000")
    eur_amt = r2(pln / rate)
    fee = r2(eur_amt * D("0.0175"))
    inv = f"""
Ksiegarnia Naukowa KOPERNIK Sp. z o.o.
ul. Slawkowska 17, 31-014 Krakow, Polska        NIP PL 675 000 14 21

FAKTURA VAT nr 2027/FV/04412                               Data wystawienia / Invoice date: {iso(d)}
Data sprzedazy / Date of sale: {iso(d)}                    Sposob zaplaty / Payment: karta platnicza (zaplacono)

Nabywca / Buyer:  {UW}
                  Institut fuer Slawistik, Hochschulring 21, 35291 Wernstadt, Niemcy
Odbiorca / Delivered to: Institut fuer Slawistik, Bibliothek des Instituts (Raum 1.18)

 Lp  Nazwa towaru / Description                                    Ilosc    Cena brutto     VAT
  1  Gramatyka historyczna jezyka polskiego, wyd. 3 (ISBN 978-83-01-20114-5)   1    {kz(pln)} PLN    5%

 Razem do zaplaty / Total:  {kz(pln)} PLN     w tym VAT 5 % / incl. VAT: {kz(vat_split(pln, 5)[1])} PLN
 Wysylka: odbior osobisty w ksiegarni / Shipping: collected in the shop
"""
    st = stmt("Prof. Dr. Henryk Wawrzyniak", "Hainbuchen Bank AG · Girokonto, Kartenumsätze",
              [(de(add(d, 2)), f"KSIEGARNIA KOPERNIK KRAKOW PLN {kz(pln)} Kurs {rate_eur(rate)}", f"-{eur(eur_amt)}"),
               (de(add(d, 2)), "Entgelt Fremdwährung 1,75 %", f"-{eur(fee)}")],
              closing=f"  Zusammen für die Universität: {eur(eur_amt + fee)} EUR")
    docs = [doc("faktura_kopernik.pdf", inv, font="Helvetica", margin=20),
            doc("Kartenumsatz.pdf", st, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m54",
         "Fachbuch einer polnischen Buchhandlung (Faktura mit 5 % USt.), Rechnungsempfänger ist das Institut für Slawistik, in der Bibliothek des Instituts abgegeben; per Karte privat bezahlt, "
         "die Kartenabrechnung zeigt " + eur(eur_amt) + " EUR zuzüglich " + eur(fee) + " EUR Entgelt. Beleg ist ein Original mit genannter Ware.", docs,
         "bilingual Polish/English invoice in ASCII, PLN with space-less amounts, bank statement with conversion",
         "all Polish labels; PLN amount converted at 4,3000; invoice addressed to a university institute",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]; practice case 01 (invoice from abroad for a book, billed to the university, accepted).",
         conf="medium")


# --------------------------------------------------------------------------- #
# m55  online conference fee (the prescribed route "privat verauslagte Kosten")
# --------------------------------------------------------------------------- #
def m55():
    d = "2027-02-25"
    c = calc([("Virtual attendance ticket, 3 days (live sessions + recordings)", 1, "100.84")], vat=19)
    ev = "2027-03-15"
    rec = f"""
Verband für Angewandte Linguistik e. V. · Konferenzbüro · Postfach 114 · 20095 Hamburg
ConfTool Pro · Zahlungsbeleg                                                 Beleg-Nr. LingTag-27-0312

Teilnehmer/in:    Dr. Ariane Zeidler (E-Mail: a.zeidler@uni-wernstadt.example)
Rechnungsadresse: {UW}, Institut für Germanistik, Hochschulring 21, 35291 Wernstadt
Veranstaltung:    LingTag 2027 - Jahrestagung, {dlong(ev)} bis {dlong(add(ev, 2))}, ausschließlich ONLINE (Zoom)
Datum:            {de(d)}

   Leistung                                                          Netto        USt. 19 %     Brutto
   Virtuelle Teilnahme (3 Tage), Standardgebühr                  {eur(c['net']):>8} €     {eur(c['vat']):>6} €   {eur(c['gross']):>8} €
   Virtuelles Rahmenprogramm "Spieleabend" (optional)                 nicht gebucht

   Bezahlt per Kreditkarte (Visa ****2211) am {de(d)}          Betrag: {eur(c['gross'])} EUR
"""
    form = f"""
Digitale Abrechnung privat verauslagter Kosten · Eingangsbestätigung                {de(add(d, 1))}  09:14
Angemeldet mit Uni-Account: a.zeidler · Vorgang PVK-27-018833

   Art der Kosten:     Teilnahmegebühr Online-Konferenz (keine Dienstreise, kein Reiseantrag erforderlich)
   Veranstaltung:      LingTag 2027, online, {de(ev)} - {de(add(ev, 2))}
   Betrag:             {eur(c['gross'])} EUR            Beleg hochgeladen: ja (PDF, 1 Seite)
   Kostenstelle:       02-1203
   Hinweis:            Originalbeleg wird für ein halbes Jahr aufbewahrt.
"""
    kto = stmt("Dr. Ariane Zeidler", "Kreditkartenabrechnung Visa ****2211",
               [(de(add(d, 0)), "VERBAND ANGEW LINGUISTIK LINGTAG27 HAMBURG", f"-{eur(c['gross'])}")])
    docs = [doc("LingTag27_Zahlungsbeleg.pdf", rec, font="Helvetica", margin=22),
            doc("PVK_Eingangsbestaetigung.pdf", form, font="Helvetica", margin=22),
            doc("Abrechnung.pdf", kto, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m55",
         "Teilnahmegebühr für eine rein online stattfindende Tagung (" + eur(c["gross"]) + " EUR, Kreditkarte): Online-Konferenzen sind keine Dienstreisen, die Gebühr wird als privat verauslagte Kosten "
         "abgerechnet, der Eingangsbeleg des digitalen Formulars liegt bei. Das optionale Rahmenprogramm wurde nicht gebucht.", docs,
         "ConfTool-style payment receipt, confirmation of the digital 'privat verauslagte Kosten' form, card statement",
         "'Konferenz' without a travel request is correct because the event is online-only; optional programme 'nicht gebucht'",
         "Rule: „Konferenzen und Tagungen die online durchgeführt werden, sind keine Dienstreisen … Die Teilnahmegebühren für Online Konferenzen / Tagungen sind über das Formular „Privat Verauslagte Kosten“ bei der Finanzabteilung geltend zu machen.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m56  invoice for three participants, the claimant claims only her own share
# --------------------------------------------------------------------------- #
def m56():
    d = "2027-07-19"
    each = D("90.00")
    inv = f"""
Open Methods Workshop Series · Registration invoice                                  Invoice OMW-27-0241 · {den(d)}
Open Methods Association, 18 Grove Court, Bristol BS1 5TT, UK (VAT-exempt educational services, no VAT charged)

Invoiced to:  {UW} (affiliation) c/o Dr. Lea Hirschfeld, Hochschulring 21, 35291 Wernstadt, Germany
Event:        "Reproducible Text Analysis", online workshop, {den(add(d, 21))} (live, online only)

  Participant                                   Fee (EUR)
  1  Dr. Lea Hirschfeld                            {eng(each)}
  2  Ben Aschenbrenner, M.Sc.                      {eng(each)}
  3  Chiara Vogt, M.A.                             {eng(each)}
  Total paid by card                               {eng(each * 3)}
"""
    quit_ = f"""
QUITTUNG                                                              Wernstadt, {de(add(d, 2))}

Frau Dr. Lea Hirschfeld bestätigt, von den Kolleg:innen für die Teilnahmegebühr am Online-Workshop "Reproducible Text
Analysis" (Rechnung OMW-27-0241) je {eur(each)} EUR als Auslagen bezahlt zu haben, die sie vorab für alle drei
Teilnehmenden mit ihrer Kreditkarte verauslagt hat:

   Ben Aschenbrenner, M.Sc.     {eur(each)} EUR    (Quittung für den eigenen Erstattungsantrag)
   Chiara Vogt, M.A.            {eur(each)} EUR    (Quittung für den eigenen Erstattungsantrag)

Unterschrift: L. Hirschfeld
"""
    claim = f"""
Von: Lea Hirschfeld
An: Finanzabteilung (privat verauslagte Kosten)
Datum: {de(add(d, 3))}
Betreff: Erstattung Workshopgebühr Online-Workshop - nur mein Anteil

Ich beantrage die Erstattung meiner eigenen Teilnahmegebühr in Höhe von {eur(each)} EUR (Position 1 der Rechnung OMW-27-0241).
Die Anteile von Herrn Aschenbrenner und Frau Vogt ({eur(each * 2)} EUR) beantrage ich NICHT; beide haben von mir
eine Quittung erhalten und stellen ihre Anträge selbst. Der Workshop findet ausschließlich online statt.
Kreditkartenabbuchung insgesamt {eur(each * 3)} EUR vom {de(d)} liegt als Kontoauszug an.
"""
    kto = stmt("Dr. Lea Hirschfeld", "Kreditkartenabrechnung",
               [(de(add(d, 1)), "OPEN METHODS ASSOC BRISTOL GB EUR 270,00", f"-{eur(each * 3)}")])
    docs = [doc("OMW-27-0241_invoice.pdf", inv, font="Helvetica"),
            doc("Quittung_Kolleg-innen.pdf", quit_, font="Times-Roman", margin=34),
            doc("Antrag_Hirschfeld.pdf", claim, font="Helvetica"),
            doc("Kontoauszug.pdf", kto, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m56",
         "Die Rechnung nennt drei Teilnehmende (270 EUR), die Antragstellerin verlangt aber nur ihre eigenen 90,00 EUR; für die beiden Kolleg:innen hat sie Quittungen ausgestellt, die diese für ihre eigenen Anträge nutzen. "
         "Online-Workshop, daher über das Formular für privat verauslagte Kosten. Das Verbot der Sammelerstattung ist eingehalten.", docs,
         "English invoice listing three participants, German receipt (Quittung) for colleagues, claim mail, card statement for the total",
         "invoice and card statement show 270,00 EUR but only 90,00 EUR is claimed; the other two shares are explicitly not requested",
         "Rule: „… ist es uns untersagt, Kosten, die für mehrere Personen verauslagt wurden, nur an die verauslagende Person zu erstatten. … Die Kolleginnen müssen ihren Anteil selber zur Erstattung anfordern, unter Vorlage einer von Ihnen ausgestellten Quittung oder Kontoauszug bei bargeldloser Zahlung.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m57  print shop: partial refund on the card after a reprint complaint, net claim
# --------------------------------------------------------------------------- #
def m57():
    d = "2027-06-02"
    c = calc([("Posterdruck A0, 120 g Fotopapier, matt (Datei 'P1-P4')", 4, "36.50"), ("Expresszuschlag Fertigung bis 12 Uhr", 1, "12.00")])
    refund_net = D("36.50")
    refund = r2(refund_net * D("1.19"))
    claim = r2(c["gross"] - refund)
    inv = invoice(V("Druckerei Pixelpress GmbH", "Fabrikstr. 66", "63065 Offenbach"), "R-27-051120", d,
                  [UW, "Lehrstuhl für Medienpädagogik (FB 02)", "Hochschulring 21", "35291 Wernstadt"], c, "de",
                  foot=["Zahlung per Kreditkarte bei Bestellung (Online-Auftrag 51120). Reklamationen innerhalb von 7 Tagen."])
    st = stmt("Prof. Dr. Antonia Merkelbach", "Hainbuchen Bank AG · Kreditkartenumsätze",
              [(de(add(d, 0)), "PIXELPRESS OFFENBACH AUFTRAG 51120", f"-{eur(c['gross'])}"),
               (de(add(d, 5)), "PIXELPRESS OFFENBACH ERSTATTUNG RECL. 51120 (Poster 3)", f"+{eur(refund)}")],
              closing=f"  Saldo Auftrag 51120: -{eur(claim)} EUR")
    note = f"""
Notiz zur Erstattung
Die Druckerei hat Poster 3 wegen eines Farbfehlers auf Reklamation gutgeschrieben und {eur(refund)} EUR (36,50 EUR netto
plus 19 % USt.) auf die Karte zurückgebucht. Ich beantrage daher nur den tatsächlich verbliebenen Betrag von {eur(claim)} EUR
(Rechnungsbetrag {eur(c['gross'])} EUR abzüglich Rückbuchung {eur(refund)} EUR). Die Poster dienen der Fachtagung am 10.06.2027.
{de(add(d, 7))}   A. Merkelbach
"""
    docs = [doc("Rechnung_R-27-051120.pdf", inv),
            doc("Kartenabrechnung_Juni.pdf", st, font="Helvetica", margin=20),
            doc("Notiz_Erstattung.pdf", note, font="Times-Roman", margin=34)]
    case(EXP, "auslagenerstattung-m57",
         "Posterdruck für eine Fachtagung (Rechnung " + eur(c["gross"]) + " EUR); ein fehlerhaftes Poster wurde reklamiert und " + eur(refund) + " EUR auf die Karte zurückgebucht. Beantragt wird nur der Saldo von "
         + eur(claim) + " EUR, die Rechnung ist an den Lehrstuhl gerichtet.", docs,
         "German print-shop invoice, card statement with a positive refund line, short typed note",
         "a refund (positive booking) appears on the statement; the claim is invoice minus refund",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]; only the real net cost is reimbursed (practice case 05 accepts a netted claim with credit note).")


# --------------------------------------------------------------------------- #
# m58  post office receipt for sending samples to a partner institute
# --------------------------------------------------------------------------- #
def m58():
    d = "2027-02-11"
    txt, total = till(["POSTFILIALE 4417", "(Partner: Schreibwaren Köhler)", "Bahnhofstr. 9", "35291 Wernstadt"],
                      [("Paket national bis 5 kg", 1, "8.99"), ("Versandkarton M, 30x20x15", 1, "1.60")],
                      ["Im Paketpreis enthalten:", "Sendungsverfolgung, Haftung bis 50 EUR", "MwSt 19% auf Karton: 0,26"],
                      [f"{de2(d)} 15:12  Bed. 04  Beleg 0017/2231", "Sendungsnr. 00340 4342 7711 5532 08", "Danke für Ihren Besuch"],
                      pay="girocard (kontaktlos)")
    note = f"""

 [handschriftlich:]
 Probenversand dienstlich
 an Partnerinstitut Leipzig
 (Dr. I. Schlüter), Kühlbox
 Projekt SPINNET TP 2
 - Spedition erst Montag,
   Proben müssen heute raus -
 {de(d)}  Y. Sorge, FG Exp. Physik
 Kst. 15-8812
"""
    docs = [doc("scan_postfiliale.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m58",
         "Quittung einer Postfiliale über " + eur(total) + " EUR für ein dringendes Probenpaket an ein Partnerinstitut (Kühlbox), handschriftlich mit Zweck, Projekt und Kostenstelle versehen. "
         "Kleine, zeitlich dringende Auslage für die Universität, Originalbeleg.", docs,
         "narrow post-office receipt with parcel number and a 'handschriftlich' note, neutral file name",
         "no itemised goods in the usual sense (postage + box); purpose written on the receipt",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen selbst besorgt … Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m59  pharmacy receipt, refill of the first-aid cabinet
# --------------------------------------------------------------------------- #
def m59():
    d = "2027-09-20"
    txt, total = till(["LINDEN-APOTHEKE", "Inh. Dr. Brigitte Faust", "Marktplatz 3 · 35039 Wernstadt-Mitte", "Tel. 06421 55 20"],
                      [("Wundschnellverband 10x6 cm 50ST", 2, "6.45"), ("Verbandpäckchen mittel DIN 13151", 4, "2.10"),
                       ("Augenspülflasche 250 ml", 2, "7.95"), ("Desinfektionsspray 250 ml", 1, "9.80")],
                      ["MwSt 19%: 47,00 -> 7,50", "(Preise inkl. MwSt)"],
                      [f"{de(d)}  11:36  Kasse 1  Bon 40871", "Kundenkarte: nein", "Gute Besserung!"], pay="EC-Karte")
    note = f"""

 [Vermerk]
 Nachfüllung Erste-Hilfe-
 Schrank Labor E 2.04
 (Kontrolle ergab Fehlbestand,
 Praktikum beginnt morgen)
 {de(d)}  Dr. A. Vollmer, Sicherheitsbeauftr.
 Kst. 15-0040
"""
    docs = [doc("Apotheke_Bon.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m59",
         "Apothekenbon über " + eur(total) + " EUR mit vollständiger Artikelliste (Wundverband, Verbandpäckchen, Augenspülflaschen, Desinfektionsspray) für die Nachfüllung des Erste-Hilfe-Schranks im Labor, "
         "Zweck und Kostenstelle vermerkt, kleine dringende Auslage vor Praktikumsbeginn.", docs,
         "pharmacy till receipt with itemised articles, typed 'Vermerk' block",
         "pharmacy purchase (health-related) is for the laboratory first-aid cabinet, not for a person; card payment",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen … Beispiel: Im Labor wurde kurzfristig Schleifpapier benötigt. … Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m60  coffee and pastry for guests of the university (courtesy), no tip
# --------------------------------------------------------------------------- #
def m60():
    d = "2027-11-16"
    txt, total = till(["CAFÉ BACKSTUBE MERKEL", "Obere Gasse 12 · 35037 Wernstadt", "Steuer-Nr. 019/233/50127"],
                      [("Kaffee Crema", 7, "2.80"), ("Tee Kännchen", 2, "3.60"), ("Käsekuchen Stück", 4, "3.40"),
                       ("Apfelstreusel Stück", 3, "3.20")],
                      ["Speisen 7 %: 23,20 enthaltene MwSt 1,52", "Getränke 19 %: 26,80 enthaltene MwSt 4,28"],
                      [f"{de(d)} 14:48  Tisch 6  Bon 3302", "TSE-Trans. 4 117 902 · Sig. 66120", "Trinkgeld nicht enthalten"],
                      pay="EC")
    note = f"""

 [Anlass, handschriftlich]
 Besuch der Delegation der
 Partnerhochschule (Gäste: 5,
 Beschäftigte: 2) im Rahmen
 der Auslandskooperation.
 Kaffee, Tee und Gebäck als
 übliche Geste der Höflichkeit
 gegenüber Gästen der Univ.
 Kein Essen, kein Alkohol.
 {de(d)}  J. Neuhäuser, Intern. Office
 Kst. 01-0220
"""
    docs = [doc("Beleg_Cafe_Merkel_20271116.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m60",
         "Café-Beleg über " + eur(total) + " EUR für Kaffee, Tee und Gebäck beim Besuch von fünf Gästen einer Partnerhochschule (zwei Beschäftigte): übliche Geste der Höflichkeit gegenüber Gästen, "
         "also laufender Betriebsaufwand und keine Bewirtung im Sinne der Richtlinie. Kein Trinkgeld, kein Alkohol, Anlass vermerkt.", docs,
         "café till receipt with TSE data and tax split, typed occasion block",
         "hospitality purchase that is NOT a 'Bewirtung': coffee, tea and pastry for guests are customary courtesies; mix of 7 % and 19 % VAT",
         "Rule: „Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen … sind die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden.“ [" + S_FIBU + "]",
         conf="medium")


# --------------------------------------------------------------------------- #
# m61  business lunch with external project partners from third-party funds, tip not claimed
# --------------------------------------------------------------------------- #
def m61():
    d = "2027-05-20"
    food = D("72.50")
    drinks = D("24.40")
    total = food + drinks
    v7 = vat_split(food, 7)[1]
    v19 = vat_split(drinks, 19)[1]
    bill = f"""
GASTHAUS AM BRUNNEN · Inh. Roswitha Behrend
Am Brunnen 2 · 36037 Fulda · Steuernummer 018/226/40731

RECHNUNG / BEWIRTUNGSBELEG Nr. 2027-004471                      Datum und Ort des Verzehrs: {de(d)}, Fulda
Tisch 7 · Bedienung 03                                           Uhrzeit: 12:21 bis 13:48

Rechnungsempfänger: {UW}, Fachgebiet Verteilte Energiesysteme (FB 13), Hochschulring 21, 35291 Wernstadt

 Menge  Bezeichnung (genaue Bezeichnung der Speisen und Getränke)                 EP        Gesamt
   2    Tagesgericht 1: Rinderrouladen, Rotkohl, Klöße                             14,50     29,00
   2    Tagesgericht 2: Gemüselasagne mit Salat                                    14,50     29,00
   1    Tagesgericht 3: Forelle Müllerin, Salzkartoffeln                           14,50     14,50
   5    Mineralwasser still 0,5 l                                                   3,20     16,00
   3    Kaffee                                                                      2,80      8,40
 --------------------------------------------------------------------------------------------------
 Speisen 7 %: {eur(food)}  (enthaltene MwSt {eur(v7)})     Getränke 19 %: {eur(drinks)}  (enthaltene MwSt {eur(v19)})
 RECHNUNGSBETRAG BRUTTO                                                              {eur(total)} EUR
 Zahlung: EC-Karte (Bewirtender)
 TSE: Registriernummer / Transaktion 2 118 047 · Seriennr. 8d2f-71a0 · Signaturzähler 441 902 · Start 12:21 · Ende 13:48

 Bewirtender: gez. Isabel Roth-Lemke                          Unterschrift des Bewirtenden
"""
    liste = f"""
Bewirtung am {de(d)} in Fulda: Anlass, Zweck, Teilnehmerkreis (Anlage zum Bewirtungsbeleg Nr. 2027-004471)

Anlass und dienstliches Interesse: Arbeitsessen im Anschluss an das Projekttreffen "KoopDigital" (Arbeitspaket 2, Abstimmung
der Messkampagne) mit den externen Kooperationspartnern. Dem Fortgang des Projekts dienend (Einwerbung/Pflege von Kooperationen).
Finanzierung: Drittmittel, Auftrag 6-2850 (Projekt KoopDigital). Der Zuwendungsbescheid (Nebenbestimmung 5.3) lässt Bewirtungskosten
im Rahmen der Landesrichtlinien zu. Die Kosten je Person liegen bei {eur(r2(total / 5))} EUR und damit unter 60,00 EUR.

 Teilnehmende                                                      Zuordnung
 1  Dr. Pia Wichert, Netzbetreiber Mittelhessen GmbH               Gast (extern)
 2  Dipl.-Ing. Karl-Heinz Berndt, Stadtwerke Fulda AG              Gast (extern)
 3  Zoran Petrovic, M.Sc., Sensorfabrik Rhön GmbH                  Gast (extern)
 4  Prof. Dr. Isabel Roth-Lemke, Universität Wernstadt             Bedienstete (bewirtend)
 5  Dr. Fynn Kaufhold, Universität Wernstadt                       Bedienstete

Auszug Zuwendungsbescheid, Nebenbestimmung 5.3: "Bewirtungskosten sind zuwendungsfähig, soweit sie dem Fortgang des Vorhabens dienen
und die Landesrichtlinien eingehalten werden."

Trinkgeld: 3,00 EUR wurden bar bezahlt; sie sind nicht Teil der Rechnung und werden nicht zur Erstattung beantragt.
Erstattung beantragt: {eur(total)} EUR laut Beleg.          {de(add(d, 2))}   I. Roth-Lemke
"""
    docs = [doc("Bewirtungsbeleg_2027-004471.pdf", bill, margin=22),
            doc("Teilnehmerliste_Anlass.pdf", liste, font="Helvetica", margin=22)]
    case(EXP, "auslagenerstattung-m61",
         "Arbeitsessen mit drei externen Projektpartnern und zwei Beschäftigten aus Drittmitteln (Projekt, Zuwendungsbescheid lässt es zu): maschinelle Rechnung mit TSE-Daten, genauer Bezeichnung, Datum, Ort, "
         "Empfänger Universität, Steuernummer, Unterschrift; Teilnehmerliste mit Kennzeichnung Gäste/Bedienstete, 19,38 EUR je Person. Das bar gezahlte Trinkgeld wird ausdrücklich nicht beantragt.", docs,
         "restaurant hospitality bill (Courier) with TSE data and tax split, participant list with purpose and funding",
         "tip is mentioned only as 'nicht Teil der Rechnung ... nicht beantragt'; two employees at the table; funding sentence about a grant clause",
         "Rule: „Der Bewirtungsbeleg … muss maschinell erstellt …, die genaue Bezeichnung der verzehrten Speisen …, Datum und Ort …, auf den Rechnungsempfänger … ausgestellt, … vom Bewirtenden unterschrieben …, die Anschrift und die Steuernummer der Gaststätte … und die Namen der bewirteten Personen“ + „Aufwendungen für Trinkgelder und Pfand“ nicht erstattungsfähig + „Die Finanzierung muss aus Drittmitteln erfolgen.“ [" + S_FIBU + "] + „Bewirtungskosten sind nur dann aus Drittmitteln erstattungsfähig, wenn … das … Treffen dem Fortgang des Projekts dient“ [" + S_GLOS + "]")


# --------------------------------------------------------------------------- #
# m62  workshop lunch for 14 (9 external) in an English-language restaurant invoice
# --------------------------------------------------------------------------- #
def m62():
    d = "2027-09-08"
    n, ext = 14, 9
    each = D("27.50")
    gross = each * n
    inv = f"""
THE GATEHOUSE KITCHEN & BAR · Schloßgasse 4 · 35037 Marburg-Weidenhausen (restaurant, event rooms)
VAT / Tax no. 31/0412/22087

INVOICE No. 27-009182                                           Date of event: {den(d)}  ·  Table: Event room 2

Billed to: {UW}, Department of Economic Geography (FB 07), Hochschulring 21, 35291 Wernstadt, Germany
Booking reference: group lunch "ClimateEcon workshop", {n} guests

  Qty  Description                                                      Unit price    Amount
  {n:>3}  Set lunch, 2 courses, incl. mineral water, juice and coffee           27.50      {eng(gross)}
  -----------------------------------------------------------------------------------------
  Total (gross, incl. 7 % VAT on food and 19 % VAT on drinks)                          EUR {eng(gross)}
  No alcoholic beverages were served. Service charge not included; no tip is shown on this invoice.
  TSE: transaction 5 441 207, registration no. 71-B-044, signature counter 90 114, 12:05-14:10.
  Paid by: credit card of Prof. Dr. Heiko Zwingmann
"""
    lst = f"""
Teilnehmerliste ClimateEcon Workshop, {de(d)}, Marburg (Anlage zum Bewirtungsbeleg 27-009182)
Anlass: Projektworkshop im Drittmittelprojekt ClimateEcon (Auftrag 6-3115) mit den Verbundpartnern. Zweck: Abstimmung der Szenarien
und der Publikationsplanung. Dem Fortgang des Projekts dienend (Workshop). Der Zuwendungsbescheid (Nr. 4.2: "Kosten von Projektworkshops mit den Verbundpartnern einschließlich Verpflegung sind zuwendungsfähig") lässt dies zu.
Die Bewirtungskosten je Teilnehmer und Tag betragen {eur(each)} EUR
(unter dem Tagegeldsatz von 28,00 EUR und unter 60,00 EUR).

 Externe Gäste (9): Prof. Dr. M. Aalto (Helsinki), Dr. K. Ribeiro (Lissabon), Dr. S. Hartmann (Potsdam), Dr. L. Ferrand (Lyon),
   T. Nowicki, M.Sc. (Poznan), Dr. E. Wolde (Addis Abeba), Prof. Dr. J. Lund (Aarhus), Dr. P. Vesely (Prag), A. Konstantinou, M.A. (Athen)
 Bedienstete der Universität (5): Prof. Dr. Heiko Zwingmann, Dr. Ines Falkenrath, Joachim Teuber, M.Sc., Lena Brockhaus, M.Sc., Dr. Samuel Kühne
"""
    docs = [doc("invoice_27-009182.pdf", inv, font="Helvetica", margin=20),
            doc("Anlage_Teilnehmerliste.pdf", lst, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m62",
         "Gruppenlunch eines Projektworkshops für 14 Personen (9 externe Gäste, 5 Beschäftigte), englische Restaurantrechnung an die Universität über 385,00 EUR (27,50 EUR je Person, unter Tagegeldsatz und 60-EUR-Grenze), "
         "ohne Alkohol, ohne Trinkgeld, mit Teilnehmerliste und Projektbezug aus Drittmitteln.", docs,
         "English-language restaurant invoice with TSE line, German participant list with named guests from many countries",
         "385 EUR for 14 people looks large but is 27,50 per head with a majority of external guests; 'Service charge not included' negation",
         "Rule: „Bewirtungskosten sind nur dann aus Drittmitteln erstattungsfähig, wenn die Bewilligungs- oder Vertragsbedingungen dies zulassen und das … Treffen dem Fortgang des Projekts dient (z.B. Arbeitsessen mit dem Drittmittelgeber, Workshop).“ + „Die Bewirtungskosten sollten pro Teilnehmer und Tag nicht höher sein als der im Hess. Reisekostengesetz festgelegte Tagegeldsatz.“ [" + S_GLOS + "] + „Pro Person und Veranstaltungstag € 60,-.“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m63  catering for a faculty appointment procedure within the 280 EUR budget (LOW)
# --------------------------------------------------------------------------- #
def m63():
    d = "2027-07-13"
    c = calc([("Kaltes Buffet (Brötchen, Käse, Wurst, Salate) für 10 Personen", 1, "128.00"),
              ("Kaffee, Tee und Wasser, ganztägig, pauschal", 1, "62.00"),
              ("Obst und Gebäck, 2 Platten", 2, "17.50")], vat=19)
    total = c["gross"]
    assert total < 280
    inv = invoice(V("Kantine & Catering Rosenhof", "Rosenhof 1", "35037 Marburg"), "2027-RH-0391", d,
                  [UW, "FB 06 Sozialwesen, Dekanat", "z. Hd. Frau Maren Vollmer", "Hochschulring 21", "35291 Wernstadt"], c, "de",
                  head_extra=["Steuernummer 031/118/40207"],
                  foot=[f"Leistungsdatum {de(d)} (Anhörungstag 2 und Sitzung der Berufungskommission), Ort: Sitzungsraum 3.12",
                        "Vollständig ohne Alkohol. Kein Trinkgeld enthalten. Rechnung maschinell erstellt, Registrier-Nr. RH-27-0391-7."])
    lst = f"""
Berufungsverfahren Professur "Soziale Arbeit und Digitalisierung" (FB 06) · Bewirtung am Anhörungstag {de(d)}

Anlass: Anhörungstage der Berufungskommission mit anschließender Sitzung. Gesamtbudget der Bewirtung laut Bewirtungskostenrichtlinie: 280,00 EUR
für die Anhörungstage und die anschließende Sitzung der Berufungskommission. Dieser Beleg: {eur(total)} EUR; weitere Belege fallen nicht an.

Teilnehmende (10): Berufungskommission 7 Mitglieder (davon 2 externe Mitglieder: Prof. Dr. N. Albers, Hochschule Rhein-Main-Nord; Prof. Dr. U. Kessler, Universität
Göttingen), 2 Gleichstellungs-/Studierendenvertretende, 1 Vorsitzende. Kandidatinnen und Kandidaten wurden nicht bewirtet.
Finanzierung: Dekanatsmittel (Präsidiumsbeschluss zur Bewirtung in Berufungsverfahren), Kostenstelle 06-0010.      {de(add(d, 3))}  M. Vollmer
"""
    docs = [doc("Rechnung_Rosenhof_2027-RH-0391.pdf", inv),
            doc("Berufungsverfahren_Bewirtung.pdf", lst, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m63",
         "Bewirtung der Berufungskommission an den Anhörungstagen: Rechnung " + eur(total) + " EUR bleibt unter dem Gesamtbudget von 280,00 EUR für Anhörungstage und Sitzung, ohne Alkohol und Trinkgeld, "
         "mit Teilnehmerliste (zwei externe Kommissionsmitglieder) und Anlass.", docs,
         "German caterer invoice (7 % VAT), list for an appointment procedure with budget statement",
         "mostly internal participants (a 'Arbeitsessen' pattern) but appointment procedures have their own explicit budget of 280 EUR",
         "Rule: Erstattungssätze: „Berufungsverfahren 280,- Gesamtbudget für die Bewirtung an den Anhörungstagen und die anschl. Sitzung der Berufungskommission“ [" + S_FIBU + "]. Doubt: the same page excludes „Arbeitsessen … mit überwiegend Universitätsangehörigen“.",
         conf="low")


# --------------------------------------------------------------------------- #
# m64  reception after an inaugural lecture within the 200 EUR limit (MEDIUM)
# --------------------------------------------------------------------------- #
def m64():
    d = "2027-11-24"
    food = D("117.00")
    drink = D("34.00")
    gross = r2(food * D("1.07") + drink * D("1.19"))
    assert gross < 200
    inv = f"""
Catering Lindenhain · Inh. Torsten Gerlach · Lindenhain 12 · 35037 Marburg · St.-Nr. 031/204/55118

Rechnung Nr. 2027-1124                         Leistungsdatum {de(d)}                      Rechnungsdatum {de(add(d, 1))}
An: {UW}, FB 09 Rechtswissenschaft, z. Hd. Frau Dr. Kerstin Vahlenkamp, Hochschulring 21, 35291 Wernstadt

  Pos  Leistung                                                   Menge    Netto      MwSt      Brutto
   1   Fingerfood-Auswahl (Platten à 10 Pers.), 7 %                   6    {eur(food):>8}   {eur(vat_split(food * D("1.07"), 7)[1]):>6}   {eur(r2(food * D("1.07"))):>8}
   2   Säfte, Mineralwasser, Kaffee, pauschal, 19 %                   1    {eur(drink):>8}   {eur(vat_split(drink * D("1.19"), 19)[1]):>6}   {eur(r2(drink * D("1.19"))):>8}
  Rechnungsbetrag brutto                                                                           {eur(gross):>8} EUR
  Ohne alkoholische Getränke. Trinkgeld nicht enthalten. Rechnung maschinell erstellt, Reg.-Nr. CL-27-1124-02.
"""
    lst = f"""
Empfang nach der Antrittsvorlesung von Prof. Dr. Jörn Silbernagel, {dlong(d)}, 18:00 Uhr (Foyer Gebäude H)
Anlass: akademisches Gemeinschaftsleben / Anlass der Hochschule (Antrittsvorlesung). Rahmen: bis 200,00 EUR je Veranstaltung. Beleg: {eur(gross)} EUR.
Teilnehmerkreis (Anlage 1, Liste der Eingeladenen): 41 Gäste (Mitglieder anderer Fachbereiche, externe Kolleginnen und Kollegen, Alumni, Presse),
12 Beschäftigte des Fachbereichs; Gäste und Beschäftigte sind in der Liste getrennt gekennzeichnet.
Finanzierung: nicht zweckgebundene Mittel Auftrag 6-0990 (Spende ohne Zuwendungsbescheinigung); keine Landesmittel.
Unterschrift Veranstalterin: K. Vahlenkamp, {de(add(d, 2))}
"""
    docs = [doc("Rechnung_2027-1124.pdf", inv, margin=20),
            doc("Anlass_Antrittsvorlesung.pdf", lst, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m64",
         "Empfang nach einer Antrittsvorlesung für 41 Gäste und 12 Beschäftigte: Rechnung " + eur(gross) + " EUR bleibt unter dem Satz von 200 EUR je Antrittsvorlesung, ohne Alkohol und Trinkgeld, Gäste und Beschäftigte getrennt gelistet, "
         "Finanzierung aus nicht zweckgebundenen Drittmitteln (Spende ohne Zuwendungsbescheinigung).", docs,
         "caterer invoice with net/VAT/gross columns per rate, event note with funding statement",
         "reception costs for a large group look like 'Bewirtung' but the guideline lists an explicit amount for inaugural lectures; mixed 7 % / 19 % VAT",
         "Rule: Erstattungssätze: „Antrittsvorlesung 200,- pro Veranstaltung“ + Anlässe „… Antrittsvorlesungen“ + Spenden: „Eine Finanzierung von Bewirtungsaufwendungen aus Spendenmitteln ist nur möglich, wenn keine Zuwendungsbescheinigung für die Mittel ausgestellt wurde und keine Zweckbindung vorliegt.“ [" + S_FIBU + "]. Doubt: funding route (Spende) is unusual.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m65  mineral water for conference guests; deposit (Pfand) deducted from the claim
# --------------------------------------------------------------------------- #
def m65():
    d = "2027-10-14"
    txt, total = till(["GETRÄNKEMARKT SCHÖNBORN", "Gewerbestr. 22 · 35390 Wernstadt-Nord", "Tel. 0641 31 77 0"],
                      [("MINERALW. MEDIUM 12x0,75 KASTEN", 4, "6.99"), ("PFAND KASTEN + FLASCHEN", 4, "3.30")],
                      ["MwSt 19%: Ware 27,96 -> 4,46", "Pfand: nicht steuerbar"],
                      [f"{de2(d)} 09:15  Kasse 2  Bon 117720", "Pfandrückgabe nur gegen Bon", "Danke für Ihren Einkauf"], pay="EC")
    ware = r2(D("4") * D("6.99"))
    pfand = r2(D("4") * D("3.30"))
    note = f"""

 [Vermerk Antragsteller]
 Mineralwasser für die Gäste
 der Fachtagung am {deshort(add(d, 1))}
 (ca. 80 externe Teilnehmende),
 Hausverwaltung konnte nicht
 liefern.
 Bon-Summe {eur(total)}
 abzgl. Pfand {eur(pfand)}
 = Erstattung {eur(ware)} EUR
 (Pfand wird nicht beansprucht)
 {de(d)} S. Bergfeld, Tagungsbüro
 Kst. 03-0300
"""
    docs = [doc("Getraenkemarkt_Bon.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m65",
         "Bon eines Getränkemarkts über " + eur(total) + " EUR für Mineralwasser für die Gäste einer Fachtagung, der Antragsteller macht nur den Warenwert von " + eur(ware) + " EUR geltend und zieht das Pfand von "
         + eur(pfand) + " EUR ausdrücklich ab. Mineralwasser für Gäste ist laufender Betriebsaufwand.", docs,
         "narrow beverage-market receipt with deposit lines and a calculation block",
         "'Pfand' appears on the receipt and is deducted from the claim (total minus deposit); the Bon sum is higher than the claim",
         "Rule: Nicht erstattungsfähig: „Aufwendungen für Trinkgelder und Pfand“ (deducted) + „… die üblichen Gesten der Höflichkeit (Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden“ als Betriebsaufwand [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m66  specialist book, invoice with a university discount, card slip
# --------------------------------------------------------------------------- #
def m66():
    d = "2027-01-27"
    price = D("89.00")
    disc = r2(price * D("0.10"))
    total = price - disc
    inv = f"""
Wissenschaftsbuchhandlung Fehling · Universitätsstr. 41 · 35037 Marburg · Tel. 06421 17 44 2 · USt-IdNr. DE 8 220 114 90

Universität Wernstadt
Lehrstuhl für Statistik und Ökonometrie
Hochschulring 21 · 35291 Wernstadt

RECHNUNG 2027-B-018832                                              Datum {de(d)}      Kunde: Lehrstuhl (Barkunde)

 Pos  Titel                                                                           Menge   Preis brutto
  1   Hastie/Tibshirani/Wainwright: Statistical Learning with Sparsity, 2nd ed.         1         {eur(price):>7} €
      ISBN 978-1-03-221455-0 · Hardcover
      abzüglich Hochschulrabatt 10 %                                                           -{eur(disc):>6} €
 -----------------------------------------------------------------------------------------------
 Rechnungsbetrag (im Preis enthalten 7 % MwSt: {eur(vat_split(total, 7)[1])} €)                          {eur(total):>7} €
 Lieferung: Mitnahme in der Buchhandlung. Bezahlt mit Girocard am {de(d)}.
"""
    slip = f"""
girocard-Zahlung · Händlerbeleg · Wissenschaftsbuchhandlung Fehling
{de(d)}  14:03   Terminal 33810417   Trace 004122
Betrag: {eur(total)} EUR            Karte: ****7712 (Kontoinhaber: Prof. Dr. Ilse Dörflinger)
Zahlung erfolgt                    Beleg-Nr. 2027-B-018832
"""
    docs = [doc("Rechnung_B-018832.pdf", inv, font="Helvetica", margin=20),
            doc("Kartenbeleg.pdf", slip, font="Courier", margin=30)]
    case(EXP, "auslagenerstattung-m66",
         "Fachbuch einer Wissenschaftsbuchhandlung, Rechnung an den Lehrstuhl über " + eur(total) + " EUR nach 10 % Hochschulrabatt (Buchtitel und ISBN genannt, 7 % MwSt.), "
         "Mitnahme in der Buchhandlung, mit Girocard privat bezahlt; der Kartenbeleg zeigt denselben Betrag.", docs,
         "bookshop invoice with an ISBN line and a negative discount line, separate card slip",
         "discount line: gross price 89,00 but claimed 80,10; 'Barkunde' (cash customer) label with the chair as addressee",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "] (invoice addressed to the chair; practice case 01 accepts a book bought privately)")


# --------------------------------------------------------------------------- #
# m67  Italian invoice (ASCII) for lab consumables, PayPal receipt in English
# --------------------------------------------------------------------------- #
def m67():
    d = "2027-03-30"
    c = calc([("Carta da filtro qualitativa, 90 mm, conf. 100 fogli", 4, "9.80"),
              ("Provette coniche 15 ml, sterili, conf. 500", 2, "21.40")], vat=22)
    inv = invoice(V("Laboratori Vignola S.r.l.", "Via dell'Industria 14", "41058 Vignola (MO), Italia"), "FT-2027/01188", d,
                  ["Spett.le", f"{UW}", "Institut fuer Bodenkunde (FB 11)", "Hochschulring 21, 35291 Wernstadt, Germania"], c, "it",
                  head_extra=["P.IVA IT 02847561201 - Codice SDI 0000000"],
                  foot=["Pagamento: PayPal (gia' incassato). Consegna: corriere espresso, spedizione gratuita.",
                        "IVA 22 % esposta in fattura (vendita a distanza, consumatore finale)."])
    pp = f"""
PayPal · You sent a payment                                                        {den(add(d, -1))}
Payment of EUR {eng(c['gross'])} to Laboratori Vignola S.r.l. (webshop order W-998112)

   Transaction ID:     2WN30118PE731420K
   Funding source:     Bank account (private)
   Subject:            Order W-998112 / invoice FT-2027/01188
   Total:              -{eng(c['gross'])} EUR
"""
    note = f"""
Hinweis zur Bestellung (Institut für Bodenkunde): Das Filterpapier und die Probenröhrchen wurden für die Feldprobenaufbereitung
kurzfristig benötigt, weil die reguläre Lieferung des Rahmenlieferanten ausfiel. Lieferadresse: Gebäude C, Labor C 0.11.   {de(add(d, 3))}  N. Brandt
"""
    docs = [doc("fattura_FT-2027-01188.pdf", inv, font="Helvetica", margin=20),
            doc("PayPal_receipt.pdf", pp, font="Helvetica"),
            doc("Notiz.pdf", note, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m67",
         "Italienische Rechnung an das Institut für Bodenkunde für Filterpapier und Probenröhrchen (" + eur(c["gross"]) + " EUR einschließlich 22 % IVA), per PayPal vom Privatkonto bezahlt, Beträge gehen auf; "
         "die Notiz erklärt den dringenden Bedarf im Labor.", docs,
         "Italian fattura (ASCII) with SDI code, English PayPal receipt, short German note",
         "Italian VAT 22 % shown as consumer sale; amounts in German number format on an Italian document",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen selbst besorgt … Originalquittung“ [" + S_FIBU + "]; practice case 01 (foreign invoice billed to the university) is accepted.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m68  copy shop invoice with a customer-card discount line
# --------------------------------------------------------------------------- #
def m68():
    d = "2027-12-13"
    copies = D("2280") * D("0.04")
    bind = D("60") * D("0.90")
    sub = copies + bind
    disc = r2(sub * D("0.05"))
    net = sub - disc
    vat = r2(net * D("0.19"))
    gross = r2(net + vat)
    inv = f"""
COPY-CENTER STUDIO 7 · Wilhelm-Roser-Str. 8 · 35037 Marburg · USt-IdNr. DE 8 009 417 66

Universität Wernstadt, Fachgebiet Baustatik, FB 12, z. Hd. Herrn Bastian Ohlendorf

Rechnung 2027/11923                                                                 {de(d)}, 16:52

 Menge  Leistung                                                            Einzelpreis      Gesamt
  2.280  Kopien s/w A4, beidseitig (Skript "Baustatik I", 60 Exemplare)           0,04 €    {eur(copies):>8} €
     60  Klebebindung mit Deckblatt                                             0,90 €    {eur(bind):>8} €
         Zwischensumme netto                                                              {eur(sub):>8} €
         Kundenkarten-Rabatt 5 %                                                          -{eur(disc):>7} €
         Summe netto                                                                      {eur(net):>8} €
         MwSt 19 %                                                                         {eur(vat):>7} €
         Rechnungsbetrag (bar bezahlt)                                                    {eur(gross):>8} €
"""
    mail = f"""
Von:      Hausdruckerei <hausdruckerei@uni-wernstadt.example>
Gesendet: Montag, {dlong(d)} 13:40
An:       Ohlendorf, Bastian
Betreff:  AW: Druckauftrag Skript Baustatik I bis morgen

Sehr geehrter Herr Ohlendorf,

leider ist unsere Digitaldruckmaschine seit Freitag ausgefallen (Techniker kommt erst Mittwoch). Wir können Ihr Skript
(60 Exemplare, beidseitig, gebunden) nicht bis morgen früh liefern. Bitte weichen Sie auf einen externen Copyshop aus.

Freundliche Grüße, Hausdruckerei
"""
    note = f"""
Vermerk: Die Skripte werden am {dlong(add(d, 1))} in der ersten Vorlesung "Baustatik I" ausgegeben. Weil die Hausdruckerei ausgefallen ist
(Mail anbei), habe ich den Druck im Copy-Center bar bezahlt. {de(d)}  B. Ohlendorf   Kst. 12-0070
"""
    docs = [doc("Rechnung_2027-11923.pdf", inv, font="Helvetica", margin=20),
            doc("Mail_Hausdruckerei.pdf", mail, font="Helvetica"),
            doc("Vermerk.pdf", note, font="Times-Roman", margin=34)]
    case(EXP, "auslagenerstattung-m68",
         "Dringender Druck von 60 Lehrskripten im Copyshop (Rechnung " + eur(gross) + " EUR einschließlich 5 % Kundenkartenrabatt), weil die Hausdruckerei ausgefallen war (Mail liegt bei). "
         "Rechnung an das Fachgebiet, Positionen benannt, Beträge gehen auf, bar bezahlt.", docs,
         "copy-shop invoice with a quantity table and a negative discount, mail from the in-house print shop, short note",
         "a customer-card discount reduces the amount; the in-house print shop outage explains why an external vendor was used",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen selbst besorgt … Erstattungsformular … Originalquittung“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m69  two receipts from the same store on the same day, different articles
# --------------------------------------------------------------------------- #
def m69():
    d = "2027-08-24"
    t1, tot1 = till(["BAUMARKT STEINMETZ", "Westring 3 · 35390 Wernstadt", "St.-Nr. 31/118/00245"],
                    [("HOLZSCHR. SPAX 4X40 200ST", 1, "8.95"), ("WINKEL VERZINKT 90X90 10ST", 2, "3.49"), ("STECKDOSENLEISTE 6FACH 1,5M", 1, "12.90")],
                    ["MWST 19% NETTO 24,23 MWST 4,60"], [f"BON 5521 KASSE 04 {de2(d)} 10:42", "VIELEN DANK"], pay="EC")
    t2, tot2 = till(["BAUMARKT STEINMETZ", "Westring 3 · 35390 Wernstadt", "St.-Nr. 31/118/00245"],
                    [("DUEBEL NYLON 8MM 50ST", 1, "4.99"), ("BOHRER HSS 8MM", 1, "3.95")],
                    ["MWST 19% NETTO 7,51 MWST 1,43"], [f"BON 5533 KASSE 02 {de2(d)} 11:05", "VIELEN DANK"], pay="EC")
    n1 = f"""

 [Vermerk]
 Regalaufbau Messplatz
 Labor G 1.04, Kst. 12-0071
 Bon 1 von 2
"""
    n2 = f"""

 [Vermerk]
 Bon 2 von 2: Dübel und Bohrer
 beim ersten Einkauf vergessen,
 daher zweiter Einkauf um 11:05.
 Zwei getrennte Bons, andere
 Artikel, kein Doppelbeleg.
 Beide zusammen: {eur(tot1 + tot2)} EUR
 {de(d)}  T. Okonkwo
"""
    docs = [doc("Bon1_5521.pdf", t1 + n1, size=RECEIPT, margin=10),
            doc("Bon2_5533.pdf", t2 + n2, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m69",
         "Zwei Kassenbons desselben Baumarkts am selben Tag (10:42 und 11:05) über " + eur(tot1) + " und " + eur(tot2) + " EUR mit unterschiedlichen Bon-Nummern und Artikeln (Regalaufbau im Labor); "
         "der Vermerk erklärt den zweiten Einkauf. Es ist keine doppelt eingereichte Rechnung, beide Beträge werden einmal geltend gemacht (zusammen " + eur(tot1 + tot2) + " EUR).", docs,
         "two narrow till receipts, same store, same date, consecutive bon numbers, each with a typed 'Vermerk'",
         "looks like a duplicate submission (same shop, same day, similar layout) but numbers, times, articles and totals differ",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "] (each receipt is a separate original; practice case 06 rejects the SAME order billed twice, which is not the case here)")


# --------------------------------------------------------------------------- #
# m70  drugstore receipt with private items marked out; only the lab share claimed
# --------------------------------------------------------------------------- #
def m70():
    d = "2027-05-12"
    items = [("KUECHENROLLE 4ER", 1, "3.95"), ("WATTESTAEBCHEN 200ST", 1, "1.45"), ("MIKROFASERTUECHER 5ST", 1, "2.49"),
             ("SCHOKOLADE VOLLMILCH", 1, "1.29"), ("SHAMPOO 250ML", 1, "2.95")]
    txt, total = till(["DROGERIE WEISSBACH", "Lindenstr. 31 · 35037 Wernstadt-Mitte"], items,
                      ["MWST 7%: 1,29 -> 0,08", "MWST 19%: 10,84 -> 1,73"],
                      [f"BON 2203 KASSE 1 {de2(d)} 12:11", "Sie wurden bedient von: Frau Otte"], pay="BAR", given="15.00")
    share = D("3.95") + D("1.45") + D("2.49")
    note = f"""

 [handschriftlich]
 Pos. 4 + 5 PRIVAT
 (Schokolade, Shampoo) -
 durchgestrichen, nicht
 beansprucht.
 Pos. 1-3 für die Reinigung
 der Messoptik / Labor
 H 2.07 (Putzmittel
 aufgebraucht, dringend)
 Beansprucht: {eur(share)} EUR
 {de(d)}  A. Falkenstein
 Kst. 15-0050
"""
    docs = [doc("Drogerie_Bon_20270512.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m70",
         "Drogeriebon über " + eur(total) + " EUR, auf dem zwei private Artikel (Schokolade, Shampoo) handschriftlich als privat markiert und nicht beansprucht werden; geltend gemacht wird nur der dienstliche Anteil von "
         + eur(share) + " EUR (Küchenrolle, Wattestäbchen, Mikrofasertücher) für das Labor.", docs,
         "narrow drugstore receipt with change, handwritten block that marks items 4 and 5 as private",
         "private articles are on the receipt, but only the lab share is claimed; claim (7,89) is lower than the Bon sum (12,13)",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen … Erstattungsformular … Originalquittung“ [" + S_FIBU + "]: only university expenses (the lab share) are claimed; private items are excluded. Doubt: mixed receipts are not discussed on the page.",
         conf="medium")


# --------------------------------------------------------------------------- #
# m71  stationery shop: coupon and loyalty-point lines reduce the total
# --------------------------------------------------------------------------- #
def m71():
    d = "2027-11-02"
    items = [("FLIPCHARTBLOCK KARIERT 20BL", 3, "14.90"), ("MODERATIONSKARTEN OVAL 100ST", 2, "6.50"),
             ("MODERATIONSMARKER 2ER", 2, "8.90"), ("COUPON 10% AUF ALLES", 1, "-7.55"), ("TREUEPUNKTE EINGELOEST", 1, "-2.00")]
    txt, total = till(["SCHREIBWAREN BRANDT", "Fußgängerzone 14 · 35390 Wernstadt", "St.-Nr. 31/220/18803"], items,
                      ["MWST 19%: 65,95 -> 10,53", "Punktestand nach Einlösung: 112"],
                      [f"BON 90412 KASSE 1 {de2(d)} 08:41", "DANKE UND BIS BALD"], pay="EC")
    note = f"""

 [Vermerk]
 Material für den Workshop
 "Moderationsmethoden" am
 {deshort(add(d, 0))} im Tagungs-
 haus (Lieferung des Büro-
 materials nicht rechtzeitig).
 Gezahlter Betrag laut Bon:
 {eur(total)} EUR (nach
 Coupon und Punkteinlösung)
 {de(d)} E. Marquardt, Kst. 07-9000
"""
    docs = [doc("Brandt_Bon_90412.pdf", txt + note, size=RECEIPT, margin=10)]
    case(EXP, "auslagenerstattung-m71",
         "Schreibwarenbon über " + eur(total) + " EUR für Moderationsmaterial eines Workshops, auf dem ein 10-%-Coupon und eingelöste Treuepunkte als negative Zeilen stehen; erstattet wird der tatsächlich gezahlte Betrag. "
         "Artikel benannt, Verwendungszweck und Kostenstelle vermerkt.", docs,
         "narrow stationery receipt with two negative lines (coupon, loyalty points) and a typed note",
         "negative lines in the item list; the claim is the net paid amount, not the sum of positive lines (75,50)",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen selbst besorgt … Erstattungsformular … Originalquittung“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m72  online summer school fee in GBP via PayPal (online only)
# --------------------------------------------------------------------------- #
def m72():
    d = "2027-06-24"
    gbp = D("140.00")
    rate = D("1.1650")
    eur_amt = conv(gbp, rate)
    rec = f"""
LinguaData Ltd · 40 Station Road · Cambridge CB1 2JH · United Kingdom
RECEIPT No. LD-SS27-0577                                                        {den(d)}

Received from:  Dr. Hana Bergström, {UW}, Institut für Computerlinguistik (c/o address on file)
For:            LinguaData Virtual Summer School 2027 - online participation (live sessions on Zoom, 12-16 July 2027)
Delivery mode:  ONLINE ONLY - no on-site programme

   Participation fee (virtual)                                           GBP {eng(gbp)}
   Social programme (virtual quiz night)                                 not booked
   Total received (no VAT charged, education services outside scope)     GBP {eng(gbp)}
   Paid by PayPal on {den(d)}
"""
    pp = f"""
PayPal · Zahlung gesendet                                                        {de(d)}, 20:02 Uhr
Sie haben 140,00 GBP an LinguaData Ltd gesendet.

   Transaktionscode:   9XC47710TM418809B
   Wechselkurs:        1 GBP = {rate_eur(rate)} EUR (PayPal-Kurs inkl. Aufschlag)
   Abgebuchter Betrag: {eur(eur_amt)} EUR
   Zahlungsquelle:     Girokonto (privat)
"""
    form = f"""
Digitale Abrechnung privat verauslagter Kosten · Eingangsbestätigung                     {de(add(d, 1))}
Vorgang PVK-27-031290 · Hana Bergström

   Art der Kosten:    Teilnahmegebühr Online-Veranstaltung (kein Dienstreiseantrag, da ausschließlich online)
   Betrag:            {eur(eur_amt)} EUR (140,00 GBP umgerechnet laut PayPal-Beleg)
   Belege:            Quittung der Veranstalterin (PDF) · PayPal-Zahlungsbestätigung (PDF)
   Kostenstelle:      02-3300
"""
    docs = [doc("receipt_LD-SS27-0577.pdf", rec, font="Helvetica", margin=22),
            doc("paypal-bestaetigung.pdf", pp, font="Helvetica", margin=22),
            doc("PVK_Bestaetigung.pdf", form, font="Helvetica", margin=22)]
    case(EXP, "auslagenerstattung-m72",
         "Gebühr einer ausschließlich online stattfindenden Sommerschule in GBP (140,00 GBP = " + eur(eur_amt) + " EUR laut PayPal), englische Quittung, PayPal-Beleg und digitale Eingangsbestätigung für privat verauslagte Kosten. "
         "Kein Reiseantrag erforderlich, das virtuelle Rahmenprogramm wurde nicht gebucht.", docs,
         "English receipt, PayPal confirmation (German), digital form confirmation",
         "'Summer School' without a travel request is correct because it is online only; GBP converted at the PayPal rate",
         "Rule: „Konferenzen und Tagungen die online durchgeführt werden, sind keine Dienstreisen … Die Teilnahmegebühren für Online Konferenzen / Tagungen sind über das Formular „Privat Verauslagte Kosten“ bei der Finanzabteilung geltend zu machen.“ [" + S_DRM + "]")


# --------------------------------------------------------------------------- #
# m73  Dutch invoice (factuur) with German VAT under the one-stop shop
# --------------------------------------------------------------------------- #
def m73():
    d = "2027-02-04"
    c = calc([("USB-C naar USB-A kabel 2 m, afgeschermd", 6, "7.60"), ("Voedingsadapter 12 V / 5 A, stekker EU", 2, "15.90"),
              ("Kabelgoot zelfklevend 20x10 mm, 2 m", 5, "3.20")], vat=19)
    inv = invoice(V("Elektronica Groothandel Tilburg B.V.", "Spoorlaan 119", "5038 CB Tilburg, Nederland"), "F-2027-60418", d,
                  ["Factuuradres en afleveradres:", UW, "Fachgebiet Messtechnik, FB 16", "Hochschulring 21", "35291 Wernstadt, Duitsland"], c, "nl",
                  head_extra=["KvK 18274460 · BTW NL 8101 4527 B01"],
                  foot=["Duitse btw 19 % berekend volgens de OSS-regeling (bestemming Duitsland).", "Betaald met creditcard (online) op " + dnl(d) + ". Levering: DHL, 2 werkdagen."])
    st = stmt("Dipl.-Ing. Torben Vollmann", "Kreditkartenabrechnung",
              [(de(add(d, 1)), "ELEKTRONICA GROOTHANDEL TILBURG NL EUR " + eur(c["gross"]), f"-{eur(c['gross'])}")])
    docs = [doc("factuur_F-2027-60418.pdf", inv, font="Helvetica", margin=20),
            doc("Kreditkarte_Februar.pdf", st, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m73",
         "Niederländische Rechnung (Factuur) für Kabel, Netzteile und Kabelkanäle an das Fachgebiet Messtechnik, deutsche USt. 19 % nach dem One-Stop-Shop-Verfahren ausgewiesen (" + eur(c["gross"]) + " EUR); "
         "per Kreditkarte privat bezahlt, die Abbuchung entspricht dem Rechnungsbetrag.", docs,
         "Dutch invoice (headings in Dutch, German VAT via OSS) and a card statement",
         "Dutch labels and a Dutch seller, but the invoice shows German VAT and a German addressee",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen … Erstattungsformular … Originalquittung“ [" + S_FIBU + "]; practice case 01 (marketplace invoice with German VAT via the one-stop shop, seller in the Netherlands) is accepted.")


# --------------------------------------------------------------------------- #
# m74  French invoice (facture) with German VAT under the one-stop shop
# --------------------------------------------------------------------------- #
def m74():
    d = "2027-10-19"
    c = calc([("Filtres a seringue PES 0,22 µm, boite de 50", 2, "34.20"), ("Papier filtre qualitatif 125 mm, boite de 100", 3, "6.80"),
              ("Flacons verre ambre 20 ml, carton de 100", 1, "26.50")], vat=19)
    inv = invoice(V("Fournitures de Laboratoire Rhone-Alpes SAS", "12 avenue des Frères Lumière", "69008 Lyon, France"), "FA-2027-117320", d,
                  [UW, "Institut fuer Pharmazeutische Chemie", "Hochschulring 21", "35291 Wernstadt, Allemagne"], c, "fr",
                  head_extra=["SIRET 442 118 907 00036 · TVA FR 52 442118907"],
                  foot=["TVA allemande 19 % appliquee selon le guichet unique (OSS), destination Allemagne.",
                        "Paiement par carte bancaire a la commande. Frais de port offerts."])
    st = stmt("Dr. Ulrike Heimbach", "Hainbuchen Bank AG · Kartenumsätze",
              [(de(add(d, 1)), "FOURNITURES LAB RHONE-ALPES LYON FR", f"-{eur(c['gross'])}")],
              closing="  Hinweis: keine weitere Buchung zu dieser Bestellung")
    docs = [doc("facture_FA-2027-117320.pdf", inv, font="Helvetica", margin=20),
            doc("Karte.pdf", st, font="Helvetica", margin=20)]
    case(EXP, "auslagenerstattung-m74",
         "Französische Rechnung (Facture) über Spritzenfilter, Filterpapier und Braunglasflaschen (" + eur(c["gross"]) + " EUR einschließlich 19 % deutscher USt. nach OSS) an das Institut für Pharmazeutische Chemie, "
         "Versandkosten frei, per Karte privat bezahlt; Kartenabrechnung entspricht dem Betrag.", docs,
         "French invoice (headings, SIRET, TVA) with German VAT, one-line card statement",
         "French document with an accented micro sign and German addressee; 'Frais de port offerts'",
         "Rule: „… kleinere, zeitlich dringende Anschaffungen … Erstattungsformular … Originalquittung“ [" + S_FIBU + "]")


# --------------------------------------------------------------------------- #
# m75  one order evidenced by confirmation, invoice and payment proof: claimed once
# --------------------------------------------------------------------------- #
def m75():
    d = "2027-07-28"
    items = [("USB-3.0-Hub, 10 Ports, aktiv, mit Netzteil", 2, D("49.90")), ("Netzteil 12 V / 5 A, Hohlstecker 5,5 x 2,1", 1, D("18.90"))]
    ship = D("4.90")
    sub = sum(q * p for _, q, p in items)
    total = sub + ship
    rows = "\n".join(f"   {i}. {n:<52} {q} St. zu {eur(p):>6} = {eur(q * p):>7}" for i, (n, q, p) in enumerate(items, 1))
    conf = f"""
Von:      service@elektro-direktversand.example
An:       s.kranz@uni-wernstadt.example
Datum:    {WD_L[dt(d).weekday()]}, {de(d)}, 18:07
Betreff:  Ihre Bestellung 4451-88-210 bei Elektro-Direktversand - Auftragsbestätigung

Vielen Dank für Ihre Bestellung! Dies ist KEINE Rechnung. Die Rechnung erhalten Sie mit der Lieferung.

Bestellnummer: 4451-88-210       Lieferadresse: {UW}, Institut für Mikrosystemtechnik, Hochschulring 21, 35291 Wernstadt
{rows}
   Versand                                                                {eur(ship):>7}
   Gesamtsumme (brutto, inkl. 19 % MwSt.)                                  {eur(total)} EUR
Zahlungsart: PayPal. Voraussichtliche Lieferung: {de(add(d, 2))}.
"""
    inv = f"""
Elektro-Direktversand GmbH · Ringstr. 5 · 09111 Chemnitz · USt-IdNr. DE 8 118 442 05

Rechnung RE-2027-3387102                                         Rechnungsdatum {de(add(d, 2))}          Bestellung 4451-88-210
Rechnungsanschrift = Lieferanschrift: {UW}, Institut für Mikrosystemtechnik, Hochschulring 21, 35291 Wernstadt

 Pos  Artikel                                                      Menge     Einzel brutto    Gesamt brutto
{chr(10).join(f"  {i}   {n:<56} {q}       {eur(p):>7}      {eur(q * p):>8}" for i, (n, q, p) in enumerate(items, 1))}
      Versand                                                                                      {eur(ship):>8}
 Rechnungsbetrag brutto {eur(total)} EUR (enthaltene MwSt. 19 %: {eur(vat_split(total, 19)[1])} EUR) - bereits per PayPal bezahlt
"""
    pp = f"""
PayPal · Zahlungsbestätigung · {de(d)}, 18:05
Zahlung an Elektro-Direktversand GmbH: {eur(total)} EUR · Transaktionscode 3FG58801HJ271193Y
Verwendungszweck: Bestellung 4451-88-210 · Zahlungsquelle: Girokonto (privat)
"""
    claim = f"""
Hinweis zur Einreichung: Die drei Unterlagen (Auftragsbestätigung, Rechnung RE-2027-3387102, PayPal-Zahlungsbestätigung) gehören zu EINER
Bestellung (4451-88-210). Geltend gemacht wird der Betrag von {eur(total)} EUR nur einmal; die Auftragsbestätigung und die
Zahlungsbestätigung sind keine Rechnungen. Verwendung: Ersatz für defekte USB-Hubs am Messplatz (Ausfall am Vortag).   {de(add(d, 4))}  S. Kranz
"""
    docs = [doc("1_Auftragsbestaetigung.pdf", conf, font="Helvetica", margin=22),
            doc("2_Rechnung_RE-2027-3387102.pdf", inv, font="Helvetica", margin=20),
            doc("3_PayPal.pdf", pp, font="Helvetica", margin=22),
            doc("Hinweis.pdf", claim, font="Helvetica", margin=22)]
    case(EXP, "auslagenerstattung-m75",
         "Eine Bestellung (4451-88-210) ist durch Auftragsbestätigung, Rechnung und PayPal-Zahlungsbestätigung belegt; geltend gemacht wird der Betrag von " + eur(total) + " EUR nur einmal. "
         "Die Rechnung ist an das Institut gerichtet, die Positionen sind benannt, der Betrag stimmt in allen Unterlagen überein.", docs,
         "order confirmation mail (marked 'KEINE Rechnung'), invoice, PayPal proof, one short note",
         "same order number and the same amount in three documents (looks like a double claim) – only one invoice exists",
         "Rule: „Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben.“ [" + S_FIBU + "]; practice case 06 rejects two INVOICES for one order, here there is one invoice plus non-invoice documents.")


# =========================================================================== #
# Build, verify, README
# =========================================================================== #
WD_ALL = {**{s: i for i, s in enumerate(WD_S)}, **{s: i for i, s in enumerate(WD_L)},
          **{s: i for i, s in enumerate(WD_EN)}, **{s: i for i, s in enumerate(WD_ENL)}}
RX_NUM = re.compile(r"\b(Mo|Di|Mi|Do|Fr|Sa|So|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|"
                    r"Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?,?\s+(\d{1,2})[./](\d{1,2})[./](\d{4})")
RX_LONG_DE = re.compile(r"\b(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s+(\d{1,2})\.\s+"
                        r"(" + "|".join(MONTHS_DE) + r")\s+(\d{4})")
RX_LONG_EN = re.compile(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})\s+"
                        r"(" + "|".join(MONTHS_EN) + r")\s+(\d{4})")


def weekday_problems(text):
    out = []
    for m in RX_NUM.finditer(text):
        wdn, d, mo, y = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if m.group(0).count("/") and not m.group(1) in WD_EN:
            continue
        try:
            day = datetime.date(y, mo, d)
        except ValueError:
            # dd/mm vs mm/dd: try the other order
            try:
                day = datetime.date(y, d, mo)
            except ValueError:
                out.append(m.group(0))
                continue
        if WD_ALL[wdn] != day.weekday():
            out.append(m.group(0))
    for rx, months in ((RX_LONG_DE, MONTHS_DE), (RX_LONG_EN, MONTHS_EN)):
        for m in rx.finditer(text):
            day = datetime.date(int(m.group(4)), months.index(m.group(3)) + 1, int(m.group(2)))
            if WD_ALL[m.group(1)] != day.weekday():
                out.append(m.group(0))
    return out


def words(text):
    return text.split()


def all_case_fns():
    return [g for n, g in sorted(globals().items()) if re.fullmatch(r"m\d\d", n) and callable(g)]


NEUTRAL = re.compile(r"^(scan|img|image|dok|dokument|document|anlage|doc|unbenannt|file|pdf|beleg|bild|scan_|"
                     r"\d)", re.I)


NEUTRAL_PATTERNS = ["scan_{n:04d}.pdf", "Dokument{n}.pdf", "Anlage_{n}.pdf", "IMG_20270{m:02d}{d:02d}_{n:04d}.pdf",
                    "file{n}.pdf", "20270{m:02d}{d:02d}_{n:03d}.pdf", "Unbenannt{n}.pdf", "doc{n:03d}.pdf"]


def neutralise(c):
    """about a third of the cases (ids divisible by 3) get neutral file names"""
    k = int(c["id"][-2:])
    if k % 3:
        return False
    pat = NEUTRAL_PATTERNS[(k // 3) % len(NEUTRAL_PATTERNS)]
    n0 = (k * 7) % 9 + 1
    c["docs"] = [(pat.format(n=n0 + i, m=1 + k % 9, d=1 + (k * 5) % 27), text, opts)
                 for i, (name, text, opts) in enumerate(c["docs"])]
    return True


def build():
    CASES.clear()
    for fn in all_case_fns():
        fn()
    n_neutral_cases = sum(neutralise(c) for c in CASES)
    for s in SETS:
        p = OUT / s
        if p.exists():
            shutil.rmtree(p)
    problems = []
    n_pdf = n_neutral = n_multi = 0
    ids = set()
    for c in CASES:
        assert c["id"] not in ids, c["id"]
        ids.add(c["id"])
        d = OUT / c["set"] / "inputs" / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        names = set()
        for name, text, opts in c["docs"]:
            assert name not in names, (c["id"], name)
            names.add(name)
            if re.search(r"kas" r"sel", text, re.I):
                problems.append(f"{c['id']}/{name}: contains the real university name")
            for w in weekday_problems(text):
                problems.append(f"{c['id']}/{name}: weekday mismatch '{w}'")
            p = d / name
            write_pdf(p, text, **opts)
            n_pdf += 1
            n_neutral += bool(NEUTRAL.match(name))
            n_multi += "\f" in text
            got = words(pdftotext(p))
            want = words(text.replace("\f", "\n"))
            if got != want:
                k = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
                problems.append(f"{c['id']}/{name}: round-trip differs at word {k}: "
                                f"got {got[k:k + 6]} want {want[k:k + 6]}")
            if len(got) < 20:
                problems.append(f"{c['id']}/{name}: too little text ({len(got)} words)")
        c["files"] = sorted(names)
    for s in SETS:
        rows = [c for c in CASES if c["set"] == s]
        (OUT / s).mkdir(parents=True, exist_ok=True)
        with open(OUT / s / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for c in rows:
                f.write(json.dumps({"antrag": c["id"], "result": "angenommen", "begruendung": c["begruendung"]},
                                   ensure_ascii=False) + "\n")
    stats = dict(n_pdf=n_pdf, n_neutral=n_neutral, n_multi=n_multi, n_nc=n_neutral_cases)
    (OUT / "README.md").write_text(readme(stats), encoding="utf-8")
    return stats, problems


def readme(stats):
    n = {s: sum(c["set"] == s for c in CASES) for s in SETS}
    low = [c["id"] for c in CASES if c["conf"] == "low"]
    med = [c["id"] for c in CASES if c["conf"] == "medium"]
    rows = []
    for c in CASES:
        cells = [f"`{c['id']}`", c["system"], c["tricky"], c["why"], c["conf"]]
        rows.append("| " + " | ".join(x.replace("|", "/").replace("\n", " ") for x in cells) + " |")
    return README_TMPL.format(total=len(CASES), n_trip=n[TRIP], n_proc=n[PROC], n_exp=n[EXP], stats=stats,
                              low=", ".join(low) or "none", med=", ".join(med) or "none",
                              n_low=len(low), n_med=len(med), table="\n".join(rows))


README_TMPL = """# clean-ood-2: 75 correct cases that were written blind

All {total} cases carry the label `angenommen`. The set measures **false alarms**: how often a
document-reading program rejects (or flags) a case that a careful clerk of "Universität Wernstadt"
(pseudonymised name of the university whose rules the policy pages describe) would approve. It is independent of the
other writer's clean set (`experiments/clean-ood/`, not opened).

| set | cases | ids |
|---|---|---|
| `business-trip-spot-check` | {n_trip} | `dienstreiseantrag-m01` .. `m25` |
| `task-2-procurement-spot-check` | {n_proc} | `beschaffungsantrag-m26` .. `m50` |
| `task-2-expense-reimbursement-spot-check` | {n_exp} | `auslagenerstattung-m51` .. `m75` |

Layout is the organisers' practice layout: `<set>/inputs/<case-id>/*.pdf` and one
`ground-truth.jsonl` per set (`{{"antrag", "result": "angenommen", "begruendung"}}`). {stats[n_pdf]} PDFs in total.

## How it was built

`python3 experiments/clean-ood-2/tools/make_clean2.py` regenerates everything (PDFs, ground
truth, this README) deterministically. No model is run and nothing is committed by the script.

* **Rules**: only the policy pages in `the University of Kassel policy pages (not included here)` (the university's intranet and public pages and the Hessian travel law) and the organisers' practice READMEs and ground
  truth. Each case was designed around one or two rules it must satisfy and one *unusual wording or
  layout* that a keyword matcher might misread (see the table).
* **Different administration**: instead of imitating the practice documents, each case invents its own
  system and form design: HISinOne and MACH masks, SAP Fiori and S/4 pages, WPS baskets, DFN/Thunderbird and
  Outlook mail prints, Word letters, paper forms with checkbox glyphs (`[x]`, `(X)`, `[v]`, `[ja]`),
  ticket-system prints, spreadsheet exports, conference portals (ConfTool, EasyChair style), web-shop and
  marketplace invoices, narrow till receipts, and vendors in English, French, Italian, Dutch and Polish
  (ASCII, because the PDF writer is WinAnsi only) with CHF, GBP and PLN amounts. Number formats
  (`1.234,56`, `1,234.56`, `1 234,56`, `1'234.50`) and date formats (`09.11.2026`, `2026-11-09`,
  `09-NOV-2026`, `9 November 2026`, `09/11/2026`) are mixed.
* **Phrasing varies, rules do not**: negations ("kein Honorar", "weder ... noch", "not claimed"),
  exclusions, unclaimed extras, private shares, discounts, refunds, partial claims, waived fees, declined dinners,
  unpaid talks, third-party funding, framework-contract orders, offer comparisons and approvals are said in many
  natural ways, in German and English, sometimes wrapped across lines.
* **Files**: {stats[n_nc]} of the {total} cases (every third id) use neutral file names (`scan_0004.pdf`, `Dokument3.pdf`, `IMG_20270314_0002.pdf`, ...), and some other PDFs have neutral names too ({stats[n_neutral]} PDFs in all). {stats[n_multi]} PDFs
  merge several documents on several pages.
* **Checks inside the script**: every PDF round-trips through `pdftotext -layout` with exactly the words that
  were written; every typed weekday matches its date; document sums are computed from the line items; the real
  name of the university appears in no PDF or file name.
* **Known limits**: all PDFs are plain text-layer files in base-14 fonts (no logos, stamps or scans as images), laid out on a
  character grid; the 'scan' look is only simulated by small jitter and neutral names.

## Blindness statement

This set was written without opening: `facts.py`, `rules.py`, `predict.py`, `rule_search.py`,
`case_tools.py`, any `test_*.py`, `experiments/traps/`, `experiments/layouts/`, `experiments/clean-ood/` (another
writer's set), `experiments/scanned/`, any `review notes`, robustness or rule-gaps file, and
`the development notes`. Allowed and used: `experiments/blind3/tools/make_blind3.py` (imported for the PDF
writer and the `pdftotext` call only), `experiments/blind3-proposals/PROPOSALS.md`, the organisers' practice cases
and ground truth in `~/dev/uniagent-code/cikm26/datasets/*/`, and the policy pages. The solver's behaviour is
unknown to the writer; the labels rest on the quoted rules alone.

## Confidence

{n_low} case(s) marked `low` ({low}) and {n_med} marked `medium` ({med}). `low` means a reasonable clerk could
hesitate; for a clean false-alarm rate, report results with and without `low` and `medium`.
`high` means the rule text on the policy page clearly allows the case.

## Cases

Rule quotes are verbatim from the policy pages; the pseudonymised university is written `[Universität]` in
quotes. Sources are file names under `the University of Kassel policy pages (not included here)`.

| id | system / layout | tricky detail | why compliant (rule quote + source page) | confidence |
|---|---|---|---|---|
{table}
"""


def main():
    stats, problems = build()
    print(f"built {len(CASES)} cases, {stats['n_pdf']} PDFs ({stats['n_nc']} cases with neutral names, "
          f"{stats['n_multi']} multi-page docs) in {OUT}")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
