#!/usr/bin/env python3
"""Build the CLEAN out-of-distribution test set for UniAgent Task 2 (75 correct cases, all `angenommen`).

Purpose: measure how often a document-reading program raises false alarms on correct documents it has never
seen. Every case is meant to be clearly compliant with the University of Kassel rules (pseudonymised here as
"Universität Wernstadt"); only the FORM varies (imitated systems, layouts, file names, page order, number and
date formats, tricky-but-fine details), never the rules.

Written blind: without the solver (facts.py, rules.py, predict.py, rule_search.py, parsing.py, case_tools.py),
its tests, experiments/traps, experiments/layouts or any review / robustness / rule-gap document. Sources: the
policy pages in the University of Kassel policy pages (not included here), the organisers' practice cases and ground truth in
~/dev/uniagent-code/cikm26/datasets/*/, experiments/blind4-proposals/PROPOSALS.md and the helper functions of
experiments/blind4/tools/make_blind4.py (loaded, not copied: lr, kv, row, money and date helpers, the Fiori and
OWA print layouts).

    python3 experiments/clean-ood/tools/make_clean.py            # build + verify + README
    python3 experiments/clean-ood/tools/make_clean.py --table    # print the README table only

Output (overwritten): experiments/clean-ood/<set>/{inputs/<case>/*.pdf, ground-truth.jsonl}, README.md.
"""
import sys

sys.dont_write_bytecode = True  # do not leave __pycache__ in other experiment folders

import datetime
import importlib.util
import json
import pathlib
import random
import re
import shutil
import subprocess
import zlib
from decimal import Decimal, ROUND_HALF_UP

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
REPO = OUT.parent.parent
TRIP = "business-trip-spot-check"
PROC = "task-2-procurement-spot-check"
EXP = "task-2-expense-reimbursement-spot-check"
SETS = [TRIP, PROC, EXP]

# --------------------------------------------------------------------------- #
# helpers from blind4 (layout, money and date helpers, Fiori / OWA prints)
# --------------------------------------------------------------------------- #
_spec = importlib.util.spec_from_file_location("make_blind4", REPO / "experiments/blind4/tools/make_blind4.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
lr, kv, row, D, r2, eur, en, tot, vat_split, vat_of = B.lr, B.kv, B.row, B.D, B.r2, B.eur, B.en, B.tot, B.vat_split, B.vat_of
dt, de, de2, wd, wdl, wde_long, wen, en_date = B.dt, B.de, B.de2, B.wd, B.wdl, B.wde_long, B.wen, B.en_date
WD_S, WD_L, WD_EN, MON_EN, MON_DE = B.WD_S, B.WD_L, B.WD_EN, B.MON_EN, B.MON_DE
fiori_request, owa_mail, pdftotext = B.fiori_request, B.owa_mail, B.pdftotext
A4 = B.A4
RECEIPT = (226.77, 700.0)
LETTERW = (595.28, 841.89)

UW = "Universität Wernstadt"
UW_STREET = "Am Lindenhang 40"
UW_CITY = "35291 Wernstadt"
UW_ADDR = f"{UW_STREET} · {UW_CITY}"


def addday(s, n):
    return (dt(s) + datetime.timedelta(days=n)).isoformat()


def workdays(a, b):
    """number of Mon-Fri days from a to b inclusive"""
    d, n = dt(a), 0
    while d <= dt(b):
        n += d.weekday() < 5
        d += datetime.timedelta(days=1)
    return n


# --------------------------------------------------------------------------- #
# number and date formats (the same amount appears in many shapes)
# --------------------------------------------------------------------------- #
def money(x, style="de"):
    x = r2(x)
    neg = x < 0
    a = abs(x)
    de_s = f"{a:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    en_s = f"{a:,.2f}"
    plain = f"{a:.2f}"
    s = {"de": de_s + " €", "eur": "EUR " + de_s, "eur-sp": "EUR " + en_s.replace(",", " ").replace(".", ","),
         "en": "€" + en_s, "en-eur": "EUR " + en_s, "plain": plain + " EUR", "bare": de_s, "bare-en": en_s,
         "eurplain": "EUR " + plain, "nosym": de_s}[style]
    return ("-" + s) if neg else s


def datef(s, style="de"):
    d = dt(s)
    return {"de": d.strftime("%d.%m.%Y"), "de2": d.strftime("%d.%m.%y"), "iso": d.isoformat(),
            "en": f"{d.day} {d.strftime('%B')} {d.year}", "us": f"{d.strftime('%B')} {d.day}, {d.year}",
            "slash": d.strftime("%d/%m/%Y"), "short": f"{d.day}.{d.month}.{d.year}",
            "long": f"{d.day}. {MON_DE[d.month - 1]} {d.year}", "dmy-en": f"{d.day:02d}-{d.strftime('%b').upper()}-{d.year}",
            "en-short": f"{d.day:02d} {MON_EN[d.month - 1]} {d.year}"}[style]


# --------------------------------------------------------------------------- #
# PDF writer: several fonts per file, per-part page size / jitter, Zapf ticks
# --------------------------------------------------------------------------- #
ZAPF = {"✔": "4", "✓": "3", "✘": "8", "✗": "7", "■": "n", "❏": "o", "●": "l",
        "○": "m", "❖": "V", "★": "H"}


def _enc(s):
    out = bytearray()
    for byte in s.encode("cp1252"):
        ch = chr(byte)
        if ch in "\\()":
            out += b"\\" + ch.encode()
        elif 32 <= byte < 127:
            out.append(byte)
        else:
            out += b"\\%03o" % byte
    return bytes(out)


def write_pdf2(path, content, size=A4, title="", font="Courier", margin=28.0, jitter=0.0, fs_max=9.0,
               producer="", creator="", lead=1.3):
    """content: str (pages split by form feed) or a list of (text, options) parts; options override the defaults
    per part (font, size, margin, jitter, fs_max, lead). Returns the number of pages."""
    parts = content if isinstance(content, list) else [(content, {})]
    pages = []
    for text, po in parts:
        o = dict(size=size, font=font, margin=margin, jitter=jitter, fs_max=fs_max, lead=lead)
        o.update(po)
        text = norm(text)
        for p in [x for x in text.split("\f") if x.strip()]:
            lines = p.strip("\n").split("\n")
            longest = max(len(l.rstrip()) for l in lines)
            w, h = o["size"]
            fs = min(o["fs_max"], (w - 2 * o["margin"]) / (0.6 * max(longest, 1)))
            cap = int((h - 2 * o["margin"]) / (fs * o["lead"]))
            for k in range(0, len(lines), cap):
                pages.append((lines[k:k + cap], o, fs))
    rnd = random.Random(str(path))
    objs = [None, None]  # catalog, pages
    objs.append(b"<< /Title (" + _enc(title) + b") /Producer (" + _enc(producer) + b") /Creator (" + _enc(creator) + b") >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /ZapfDingbats >>")
    fontnum = {}
    for fname in sorted({pg[1]["font"] for pg in pages}):
        objs.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{fname} /Encoding /WinAnsiEncoding >>".encode())
        fontnum[fname] = len(objs)
    kids = []
    for lines, o, fs in pages:
        w, h = o["size"]
        cw, ld = 0.6 * fs, fs * o["lead"]
        content_b = bytearray()
        for j, line in enumerate(lines):
            line = line.rstrip()
            if not line:
                continue
            y = h - o["margin"] - fs - j * ld
            dx = rnd.uniform(-o["jitter"], o["jitter"]) if o["jitter"] else 0.0
            dy = rnd.uniform(-o["jitter"] / 3, o["jitter"] / 3) if o["jitter"] else 0.0
            if o["font"] == "Courier":
                segs = [(0, line)]
            else:
                segs = [(m.start(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", line)]
            for col, seg in segs:
                runs, cur, kind = [], "", None
                for idx, ch in enumerate(seg):
                    k = ch in ZAPF
                    if kind is None or k != kind:
                        if cur:
                            runs.append((kind, start, cur))
                        cur, kind, start = "", k, idx
                    cur += ch
                if cur:
                    runs.append((kind, start, cur))
                for k, st, txt in runs:
                    x = o["margin"] + dx + (col + st) * cw
                    if k:
                        for q, ch in enumerate(txt):
                            content_b += (f"BT /FZ {fs:.3f} Tf {x + q * cw:.2f} {y + dy:.2f} Td ({ZAPF[ch]}) Tj ET\n").encode()
                    else:
                        content_b += (f"BT /F1 {fs:.3f} Tf {x:.2f} {y + dy:.2f} Td (".encode() + _enc(txt) + b") Tj ET\n")
        comp = zlib.compress(bytes(content_b))
        objs.append(f"<< /Filter /FlateDecode /Length {len(comp)} >>\nstream\n".encode() + comp + b"\nendstream")
        cnum = len(objs)
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.4f} {h:.4f}] /Contents {cnum} 0 R "
                     f"/Resources << /Font << /F1 {fontnum[o['font']]} 0 R /FZ 4 0 R >> /ProcSet [/PDF /Text] >> >>").encode())
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(f'{k} 0 R' for k in kids)}] >>".encode()
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 3 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    pathlib.Path(path).write_bytes(bytes(buf))
    return len(kids)


def norm(s):
    return s.replace("→", "->").replace("\u2212", "-").replace("\u2009", " ").replace("\u2082", "2")


def all_text(content):
    if isinstance(content, list):
        content = "\n".join(t for t, _ in content)
    return norm(content)


# --------------------------------------------------------------------------- #
# case registry
# --------------------------------------------------------------------------- #
CASES = []


def case(set_, cid, docs, begr, sys_, trick, rule, src, conf="high"):
    """docs: list of (filename, content, options); conf: high | medium | low"""
    CASES.append(dict(set=set_, id=cid, docs=docs, begr=begr, sys=sys_, trick=trick, rule=rule, src=src, conf=conf))


def doc(name, content, **opts):
    return (name, content, opts)


def shuffle_docs(docs, cid):
    """documents in random order (the file system order is what a reader sees)"""
    docs = list(docs)
    random.Random("order-" + cid).shuffle(docs)
    return docs


def iban(rnd):
    while True:
        digits = "".join(str(rnd.randint(0, 9)) for _ in range(20))
        s = "DE" + digits
        rearr = (s[4:] + s[:4]).replace("D", "13").replace("E", "14")
        if int(rearr) % 97 != 1:  # deliberately invalid check digits
            return f"DE{digits[:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:]}"


# --------------------------------------------------------------------------- #
# fictional pools
# --------------------------------------------------------------------------- #
FIRST = ["Anselm", "Birgit", "Cornelius", "Dagmar", "Eike", "Farina", "Gunnar", "Hedwig", "Ilias", "Jorina", "Karsten",
         "Leandra", "Malte", "Nadine", "Ole", "Pia", "Quirin", "Rosalind", "Sven", "Tamsin", "Ulrike", "Valentin",
         "Wiebke", "Xaver", "Yvonne", "Zeno", "Amelie", "Bastian", "Carolin", "Dorian", "Elif", "Fynn", "Greta",
         "Hannes", "Imke", "Jasper", "Katinka", "Lorenz", "Mirela", "Niklas", "Odile", "Piet", "Rieke", "Soren",
         "Thea", "Urs", "Vesna", "Wolfram", "Yara", "Zdenka", "Aurel", "Brit", "Caspar", "Dunja", "Emre", "Frauke",
         "Gideon", "Helene", "Ingmar", "Joris", "Kaja", "Lasse", "Mette", "Nils", "Oksana", "Paulus", "Reza", "Silja",
         "Tobit", "Uta", "Vanja", "Wanja", "Ylva"]
LAST = ["Vorwerk-Lindner", "Haselhorst", "Tiedemann-Rau", "Kellermeyer", "Ostermann-Voss", "Grotjahn", "Pfeiffer-Ahlers",
        "Seidelmann", "Brockhaus-Neu", "Rademacher", "Lüdemann", "Wolkenstein-Reis", "Hinnerksen", "Marquardt-Elbe",
        "Ehrenfeld", "Strothotte", "Zielinski-Berg", "Altenhofen", "Pirwitz", "Knauth", "Dethloff", "Eilers-Mohn",
        "Sandkühler", "Pohlmann-Yilmaz", "Tschirch", "Overbeck", "Nowack-Lenz", "Kranzbühler", "Hesselbarth",
        "Gerstenkorn", "Lamprecht", "Reichenbach-Dahl", "Ihle", "Vogelgesang", "Wendland", "Zimmermann-Okafor",
        "Hoogeveen", "Schwanitz", "Bauermeister", "Cordes-Jahn", "Dörrfuss", "Engelhardt-Sato", "Fahrenkrog",
        "Gawlik", "Heitkamp", "Imhoff-Sarr", "Jungclaus", "Kaltenbach", "Lehnhoff", "Mühlbauer-Cho", "Nagelschmidt",
        "Oelkers", "Prinzhorn", "Quasthoff", "Reimers-Tan", "Steinfurth", "Thielemann", "Ulbricht-Moreau", "Vahldiek",
        "Wiegand-Aziz", "Yilmaz-Brandt", "Zacharias", "Aschenbrenner", "Bruns-Kowalczyk", "Czerny", "Droste-Vella",
        "Eggebrecht", "Fiedler-Osei", "Gottwald", "Hartkopf"]
FBS = [("71", "Elektrotechnik und Informatik"), ("72", "Maschinenbau"), ("73", "Physik und Materialwissenschaften"),
       ("74", "Bauingenieur- und Umweltingenieurwesen"), ("75", "Wirtschaftswissenschaften"), ("76", "Chemie und Biologie"),
       ("77", "Agrarwissenschaften"), ("78", "Gesellschaftswissenschaften"), ("79", "Architektur und Stadtplanung")]
FGS = {"71": ["Hochfrequenztechnik", "Verteilte Systeme", "Eingebettete Systeme", "Leistungselektronik", "Datenbanken und Wissensmanagement"],
       "72": ["Strömungsmechanik", "Fertigungstechnik", "Regelungstechnik", "Thermodynamik und Energietechnik"],
       "73": ["Experimentelle Festkörperphysik", "Photonik", "Theoretische Physik", "Werkstoffanalytik"],
       "74": ["Siedlungswasserwirtschaft", "Geotechnik", "Konstruktiver Ingenieurbau", "Verkehrsplanung"],
       "75": ["Unternehmensrechnung", "Marketing", "Volkswirtschaftslehre", "Wirtschaftsinformatik"],
       "76": ["Analytische Chemie", "Mikrobiologie", "Biochemie", "Umweltchemie"],
       "77": ["Pflanzenbau", "Bodenkunde", "Agrarökonomie", "Tierernährung"],
       "78": ["Soziologie der Arbeit", "Politische Theorie", "Bildungsforschung", "Sozialpsychologie"],
       "79": ["Entwerfen und Konstruieren", "Stadtgeschichte", "Landschaftsarchitektur", "Bauphysik"]}


def staff(i, title=None, fb=None):
    """deterministic fictional staff member i"""
    rnd = random.Random(1000 + i)
    first, last = FIRST[(i * 7) % len(FIRST)], LAST[(i * 11 + 3) % len(LAST)]
    fbc, fbn = FBS[(i if fb is None else int(fb) - 71) % len(FBS)]
    fg = FGS[fbc][(i * 3) % len(FGS[fbc])]
    t = title if title is not None else rnd.choice(["Dr.", "Dr.", "", "Prof. Dr."])
    name = f"{t} {first} {last}".strip()
    return dict(name=name, plain=f"{first} {last}", first=first, last=last, title=t, persnr=f"{rnd.randint(30000, 59999):06d}",
                fb=fbc, fbname=fbn, fg=fg, email=f"{first}.{last}".lower().replace("ü", "ue").replace("ö", "oe")
                .replace("ä", "ae").replace("ß", "ss").replace("-", "").replace(" ", "") + "@uni-wernstadt.de",
                org=f"FB {fbc} {fbn} · FG {fg}", org_long=f"Fachbereich {fbc} {fbn}, Fachgebiet {fg}",
                ks=f"{fbc} {rnd.randint(4100, 4990)}", auftrag=f"21{rnd.randint(40000, 69999):05d}",
                dr_auftrag=f"6-{rnd.randint(4400000, 4499999)}", tel=f"0561 7390-{rnd.randint(4100, 4990)}")


def kostenstellenleiter(i, fb):
    return staff(i + 500, title="Prof. Dr.", fb=fb)


SURN = ["Sperling", "Tiegelmann", "Rübsam", "Hornung", "Ziegenhain", "Wöhlk", "Brandstetter", "Kuckuck", "Lindgens",
        "Meixner", "Nordmann-Esch", "Opitz", "Pfannkuch", "Raschke", "Sieveking", "Tretschok", "Uhlenbruck", "Vollmar",
        "Wehmeyer", "Zerbe", "Ahlborn", "Bellmann", "Cramme", "Dallmeier", "Eckermann", "Fuhrmann-Lau", "Gerdes",
        "Hackmann", "Ibing", "Jaensch", "Kleinschmidt", "Lauterbach", "Mohrmann", "Neuhaus", "Oberdorf", "Pagel",
        "Quast", "Ruppert", "Sauerbier", "Thormählen", "Ullmann", "Volkerts", "Wasmuth", "Zeidler"]
WORDS = {"lab": ["Laborbedarf", "Analytik-Handel", "Probenwelt", "Labortechnik", "Chemikalien-Kontor"],
         "elec": ["Bauteile-Kontor", "Elektronik-Vertrieb", "Sensorik", "Platinenwerk", "Messtechnik"],
         "mess": ["Messgeräte", "Prüftechnik", "Instrumenten-Vertrieb", "Mess- und Regeltechnik", "Optik-Vertrieb"],
         "werk": ["Werkstattbedarf", "Maschinenhandel", "Technischer Großhandel", "Werkzeug-Center", "Industriebedarf"],
         "print": ["Druckwerkstatt", "Copyshop", "Digitaldruck", "Plakat- und Posterdruck", "Druckerei"],
         "gen": ["Handels", "Vertriebs", "Service", "Fachhandels", "Systemhaus"],
         "buero": ["Bürowelt", "Büro-Partner", "Bürobedarf", "Papier-Kontor"],
         "move": ["Wohn- und Objekteinrichtung", "Raumkonzepte", "Objektmöbel"],
         "gas": ["Gase-Kontor", "Industriegase", "Gasetechnik"],
         "serv": ["Kalibrierdienst", "Prüflabor", "Servicetechnik", "Messdienst"]}
CITIES = [("Göttingen", "37073"), ("Ulm", "89073"), ("Bremen", "28195"), ("Jena", "07743"), ("Nürnberg", "90402"),
          ("Aachen", "52062"), ("Erfurt", "99084"), ("Lüneburg", "21335"), ("Freising", "85354"), ("Hamm", "59065"),
          ("Kaiserslautern", "67655"), ("Offenbach", "63065"), ("Osnabrück", "49074"), ("Chemnitz", "09111"),
          ("Marburg", "35037"), ("Paderborn", "33098"), ("Rostock", "18055"), ("Heilbronn", "74072"), ("Kiel", "24103"),
          ("Regensburg", "93047"), ("Münster", "48143"), ("Karlsruhe", "76133"), ("Würzburg", "97070"),
          ("Magdeburg", "39104"), ("Bielefeld", "33602"), ("Dortmund", "44137")]
STREETS = ["Industriestraße", "Gewerbering", "Am Spülfeld", "Hafenweg", "Bahnhofstraße", "Lessingstraße", "Siemensallee",
           "Kellerwaldstraße", "Am Güterbahnhof", "Werkstraße", "Gutenbergring", "Mühlenkamp", "Schmiedegasse",
           "Ostenallee", "An der Alten Ziegelei", "Technologiepark"]
LEGAL = ["GmbH", "GmbH", "KG", "e.K.", "GmbH & Co. KG", "OHG", "GmbH"]


def vendor(i, kind="lab"):
    rnd = random.Random(2000 + i * 13 + sum(map(ord, kind)) % 7)
    word = rnd.choice(WORDS[kind])
    sur = rnd.choice(SURN)
    legal = rnd.choice(LEGAL)
    city, plz = rnd.choice(CITIES)
    street = f"{rnd.choice(STREETS)} {rnd.randint(2, 98)}"
    name = f"{word} {sur} {legal}" if rnd.random() < .6 else f"{sur} {word} {legal}"
    dom = re.sub(r"[^a-z]", "", (sur + word).lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae"))[:18]
    return dict(name=name, street=street, plz=plz, city=city, tel=f"0{rnd.randint(200, 899)} {rnd.randint(1000, 99999)}-{rnd.randint(0, 99)}",
                mail=f"{rnd.choice(['info', 'vertrieb', 'angebote', 'service'])}@{dom}.example", web=f"www.{dom}.example",
                vat=f"DE {rnd.randint(100, 999)} {rnd.randint(100, 999)} {rnd.randint(100, 999)}",
                stnr=f"{rnd.randint(10, 99)}/{rnd.randint(100, 999)}/{rnd.randint(10000, 99999)}",
                iban=iban(rnd), line=f"{street} · {plz} {city}")


# =========================================================================== #
# text helpers
# =========================================================================== #
import textwrap


def wrap(text, width):
    return textwrap.wrap(text, width) or [""]


def kvw(rows, k=28, width=70, indent=2):
    """key/value rows, long values wrapped under the value column"""
    out = []
    for a, b in rows:
        ls = wrap(str(b), width)
        out.append(" " * indent + a.ljust(k) + ls[0])
        out += [" " * (indent + k) + x for x in ls[1:]]
    return "\n".join(out)


def para(text, width=100, indent=0):
    return [" " * indent + l for l in wrap(text, width - indent)]


def yn(val, style="x"):
    on = {"x": "[X]", "xs": "[x]", "times": "[×]", "tick": "[✔]", "cross": "[✘]", "box": "[■]", "paren": "(x)",
          "dot": "(•)", "star": "[*]", "slash": "[/]", "mark": "[✓]"}[style]
    off = "( )" if style in ("paren", "dot") else "[ ]"
    return f"{on} ja   {off} nein" if val else f"{off} ja   {on} nein"


def yn_en(val, style="x"):
    return yn(val, style).replace(" ja ", " yes").replace("nein", "no").replace(" yes  ", " yes ")


def table(headers, rows, widths, aligns, indent=1):
    out = [" " * indent + row(headers, widths, aligns)]
    for r in rows:
        out.append(" " * indent + row(r, widths, aligns))
    return out


# =========================================================================== #
# TRIP: the request itself, in six imitated systems
# =========================================================================== #
def trip_total(costs):
    return tot(*[c[2] for c in costs])


LBL = {
    "ess": dict(dest="Reiseziel:", abroad="Reise ins Ausland:", anlass="Anlass:", grund="Grund der Reise:", mode="Verkehrsmittel:",
                created="Datum der Antragstellung:", start="Start:", end="Ende:", biz_from="Beginn Dienstgeschäft:",
                biz_to="Ende Dienstgeschäft:", priv="priv. Aufenthalt:", nights="Übernachtungen:", a1="A1-Bescheinigung:"),
    "web": dict(dest="Zielort, Land", abroad="Auslandsreise", anlass="Anlass der Reise", grund="Dienstliches Interesse", mode="Beförderungsmittel",
                created="Antragsdatum", start="Abreise", end="Rückkehr", biz_from="Dienstgeschäft von", biz_to="Dienstgeschäft bis",
                priv="Privater Aufenthalt", nights="Zahl der Übernachtungen", a1="Entsendebescheinigung A1"),
    "paper": dict(dest="REISEZIEL", abroad="Auslandsreise?", anlass="ANLASS", grund="BEGRÜNDUNG", mode="VERKEHRSMITTEL",
                  created="DATUM", start="REISEBEGINN", end="REISEENDE", biz_from="DIENSTGESCHÄFT AB", biz_to="DIENSTGESCHÄFT BIS",
                  priv="PRIVATER AUFENTHALT", nights="ÜBERNACHTUNGEN", a1="A1"),
    "en": dict(dest="Destination:", abroad="Trip abroad:", anlass="Occasion:", grund="Purpose of the trip:", mode="Means of transport:",
               created="Date of application:", start="Departure:", end="Return:", biz_from="Business starts:",
               biz_to="Business ends:", priv="Private stay:", nights="Nights:", a1="A1 certificate:"),
}


def _t(T, k, style, datefmt):
    """a (date, time) tuple rendered"""
    d, tm = T[k]
    if style == "en":
        return f"{wen(d)}, {tm}"
    return f"{wdl(d) if datefmt == 'wdl' else datef(d, datefmt)}, {tm} Uhr"


def trip_antrag(style, T, glyph="x", datefmt="de"):
    p = T["person"]
    L = LBL.get(style, LBL["ess"])
    abroad = T["abroad"]
    country = T["country"]
    tot_ = trip_total(T["costs"])
    if style == "fiori":
        gen = [("Reiseziel", f"{T['dest']}, {country}"), ("Reise ins Ausland", "ja" if abroad else "nein"),
               ("Anlass", T["anlass"]), ("Grund der Reise", T["grund"]), ("Reiseart", "Dienstreise"),
               ("Verkehrsmittel", T["mode"])] + T.get("extra_general", []) + [("Datum der Antragstellung", datef(T["created"], datefmt))]
        route = [("Beginn der Reise", _t(T, "start", "de", datefmt) + " (Wohnung)"), ("Ende der Reise", _t(T, "end", "de", datefmt) + " (Wohnung)"),
                 ("Beginn Dienstgeschäft", _t(T, "biz_from", "de", datefmt)), ("Ende Dienstgeschäft", _t(T, "biz_to", "de", datefmt)),
                 ("Privater Aufenthalt", T["priv"]), ("Übernachtungen", str(T["nights"]))]
        if T.get("a1"):
            route.append(("A1-Bescheinigung", T["a1"]))
        return fiori_request(T["nr"], T["created"], T.get("status", "Antrag eingereicht – in Genehmigung"), p["name"], p["persnr"],
                             p["org_long"], gen, route, T["costs"], tot_, T["finance"], T["remarks"], T["attach"], T["created"],
                             assist=T.get("assist"))
    if style in ("ess", "en"):
        en_ = style == "en"
        left = [p["name"], "", f"Fachgebiet {p['fg']}", "", f"Personalnummer {p['persnr']}"]
        right = [UW, f"Fachbereich {p['fb']}", p["fbname"], UW_STREET, UW_CITY]
        head = [lr(a, b, 100) for a, b in zip(left, right)]
        lines = head + ["", lr("Seite 1 von 1", f"Last modified: {datef(T['created'], 'en')}" if en_ else f"Zuletzt geändert am: {datef(T['created'], 'long')}", 100),
                        lr("", "Status: " + ("Application submitted" if en_ else "Antrag eingereicht"), 100),
                        lr("", ("Approved by: ---" if en_ else "Genehmigt von: ---"), 100), "",
                        "APPLICATION FOR BUSINESS TRIP APPROVAL" if en_ else "ANTRAG AUF DIENSTREISEGENEHMIGUNG",
                        (f"to be submitted before departure · trip number {T['nr']}" if en_ else f"vor Antritt der Reise einzureichen · Reisenummer {T['nr']}"), "",
                        "General data" if en_ else "Allgemeine Daten"]
        yes = yn_en(abroad, glyph) if en_ else yn(abroad, glyph)
        rows = [(L["dest"], f"{T['dest']}, {country}"), (L["anlass"], T["anlass"]), (L["grund"], T["grund"]), (L["abroad"], yes),
                (L["mode"], T["mode"])] + [(a + ":" if not a.endswith(":") else a, b) for a, b in T.get("extra_general", [])] + [(L["created"], datef(T["created"], "en" if en_ else datefmt))]
        lines.append(kvw(rows, k=42, width=66, indent=0))
        lines += ["", "Itinerary" if en_ else "Reiseverlauf"]
        rows = [(L["start"], _t(T, "start", style, datefmt)), (L["end"], _t(T, "end", style, datefmt)),
                (L["biz_from"], _t(T, "biz_from", style, datefmt)), (L["biz_to"], _t(T, "biz_to", style, datefmt)), (L["priv"], T["priv"]),
                (L["nights"], str(T["nights"]))]
        if T.get("a1"):
            rows.append((L["a1"], T["a1"]))
        lines.append(kvw(rows, k=42, width=66, indent=0))
        lines += ["", "Estimated costs" if en_ else "Voraussichtliche Kosten (Schätzung)",
                  " " + row(["Position" if not en_ else "Item", "Menge" if not en_ else "Qty", "Betrag" if not en_ else "Amount"], [74, 8, 16], "lrr")]
        for lab, det, amt in T["costs"]:
            lines.append(" " + row([lab + (" – " + det if det else ""), "1", money(amt, "en" if en_ else "de")], [74, 8, 16], "lrr"))
        lines.append(" " + row(["Total (estimate)" if en_ else "Summe (Schätzung)", "", money(tot_, "en" if en_ else "de")], [74, 8, 16], "lrr"))
        lines += ["", kvw([("Funding:" if en_ else "Finanzierung:", "; ".join(b if a in ("Finanzierung", "Funding", "") else f"{a}: {b}" for a, b in T["finance"]))], k=42, width=66, indent=0),
                  "", "Short justification" if en_ else "Kurzbegründung"]
        for r in T["remarks"]:
            lines += para(r, 100)
        if T.get("attach"):
            lines += ["", ("Attachments: " if en_ else "Anlagen: ") + ", ".join(T["attach"])]
        lines += ["", lr(f"Datum: {datef(T['created'], 'en' if en_ else datefmt)}", f"{'Signature applicant' if en_ else 'Unterschrift Antragsteller:in'}: {p['name']}", 100), "",
                  ("Created by ESS Travel Management · " if en_ else "Erstellt durch ESS-Reisemanagement · ") + UW]
        return "\n".join(lines)
    if style == "web":
        lines = [lr("https://dienstreise.uni-wernstadt.de/antrag/neu/zusammenfassung", f"{wd(T['created'])} {T.get('time', '09:12')}", 104),
                 "", f"Dienstreiseantrag online · Zusammenfassung vor dem Absenden · Schritt 4 von 4 · Vorgang {T['nr']}", "",
                 "1  Antragstellende Person", kvw([("Name", p["name"]), ("Personalnummer", p["persnr"]), ("Organisationseinheit", p["org"]),
                                                     ("E-Mail", p["email"])], k=30, width=66)]
        lines += ["", "2  Reise", kvw([(L["dest"], f"{T['dest']} ({country.title()})"), (L["abroad"], yn(abroad, glyph)), (L["anlass"], T["anlass"]),
                                       (L["grund"], T["grund"]), (L["mode"], T["mode"])] + T.get("extra_general", []), k=30, width=66)]
        rows = [(L["start"], _t(T, "start", style, datefmt)), (L["end"], _t(T, "end", style, datefmt)),
                (L["biz_from"], _t(T, "biz_from", style, datefmt)), (L["biz_to"], _t(T, "biz_to", style, datefmt)), (L["priv"], T["priv"]),
                (L["nights"], str(T["nights"]))]
        if T.get("a1"):
            rows.append((L["a1"], T["a1"]))
        lines += ["", "3  Zeiten", kvw(rows, k=30, width=66), "", "4  Kosten (Schätzung) und Finanzierung",
                  " " + row(["Kostenart", "Betrag"], [84, 14], "lr")]
        for lab, det, amt in T["costs"]:
            lines.append(" " + row([lab + (" · " + det if det else ""), money(amt, T.get("mfmt", "de"))], [84, 14], "lr"))
        lines.append(" " + row(["Summe", money(tot_, T.get("mfmt", "de"))], [84, 14], "lr"))
        lines += ["", kvw(T["finance"], k=30, width=66), "", "5  Begründung / Hinweise"]
        for r in T["remarks"]:
            lines += para(r, 100, 2)
        lines += ["", "6  Anlagen (PDF)"] + ["  • " + a for a in T["attach"]]
        lines += ["", "[✔] Ich versichere die Richtigkeit meiner Angaben.   [Antrag absenden]", "", lr("Seite 1 / 1", f"Ausdruck {datef(T['created'], 'de')}", 104)]
        return "\n".join(lines)
    if style == "paper":
        lines = ["DIENSTREISEANTRAG   (Vordruck PO-12, Stand 03/2021)  –  bitte in Druckschrift ausfüllen", "",
                 f"Eingegangen: {datef(addday(T['created'], 1), 'de')}   Dekanat FB {p['fb']}   [Stempel]", "",
                 f"NAME: {p['name'].upper()}        PERS.-NR.: {p['persnr']}        TEL.: {p['tel']}",
                 f"EINRICHTUNG: {UW.upper()}, FB {p['fb']}, FG {p['fg'].upper()}", ""]
        rows = [(L["dest"], f"{T['dest'].upper()}, {country}"), (L["abroad"], yn(abroad, glyph)), (L["anlass"], T["anlass"].upper()),
                (L["grund"], T["grund"].upper()), (L["mode"], T["mode"].upper())] + [(a.upper(), b.upper()) for a, b in T.get("extra_general", [])]
        lines.append(kvw(rows, k=26, width=74, indent=0))
        rows = [(L["start"], _t(T, "start", style, datefmt)), (L["end"], _t(T, "end", style, datefmt)),
                (L["biz_from"], _t(T, "biz_from", style, datefmt)), (L["biz_to"], _t(T, "biz_to", style, datefmt)),
                (L["priv"], T["priv"].upper()), (L["nights"], str(T["nights"]))]
        if T.get("a1"):
            rows.append((L["a1"], T["a1"].upper()))
        lines += ["", kvw(rows, k=26, width=74, indent=0), "", "VORAUSSICHTLICHE KOSTEN"]
        for lab, det, amt in T["costs"]:
            lines.append(row([lab.upper() + (" (" + det + ")" if det else ""), money(amt, "de")], [84, 14], "lr"))
        lines.append(row(["SUMME", money(tot_, "de")], [84, 14], "lr"))
        lines += ["", kvw([(a.upper(), b) for a, b in T["finance"]], k=26, width=74, indent=0), "", "BEGRÜNDUNG / BEMERKUNGEN"]
        for r in T["remarks"]:
            lines += para(r.upper() if T.get("caps") else r, 100)
        lines += ["", "ANLAGEN: " + ", ".join(T["attach"]), "", f"{T['dest'].upper()[:0]}Wernstadt, den {datef(T['created'], 'de')}      __________________ (Unterschrift {p['plain']})",
                  "Genehmigt / Dekanat: ______________   Datum: ________     Sachlich richtig (Kostenstelle): ______________"]
        return "\n".join(lines)
    raise ValueError(style)


# =========================================================================== #
# TRIP: supporting documents
# =========================================================================== #
def invite_mail(lang, to_name, subject, sender, when, body, who):
    """OWA print of an invitation / acceptance mail"""
    return owa_mail(who, subject, sender, when, to_name, body)


def hotel_names():
    return ["Hotel Lindenhof", "Stadthotel Am Markt", "Parkhotel Elbblick", "Gästehaus Sonnenberg", "Hotel Drei Linden",
            "City Inn Bahnhof", "Hotel Rosengarten", "Boardinghouse Kastanienallee", "Hotel Zum Anker", "Hotel Residenz Nord"]


def hotel_doc(style, h, guest, unit, nights, rate, cin, cout, bookno, issued, breakfast=True, foot=None, lang="de",
              mfmt="de", datefmt="de", rooms="Einzelzimmer Komfort", bill_to=None):
    """hotel booking confirmation; the invoice recipient is always the university (rule: Rechnungen nur mit Universität als Adressat)"""
    total = r2(D(rate) * nights)
    bill = bill_to or f"{UW}, {unit}, {UW_ADDR}"
    foot = foot or []
    if style == "letter":
        L = [lr(h["name"], f"{h['street']}, {h['plz']} {h['city']}", 100), lr("", f"Tel. {h['tel']} · {h['mail']}", 100), "",
             UW, unit, f"z. Hd. {guest}", UW_ADDR, "", lr(f"Buchungsbestätigung Nr. {bookno}", f"{h['city']}, {datef(issued, datefmt)}", 100), "",
             f"Sehr geehrte Gäste der Universität Wernstadt, wir bestätigen Ihre Reservierung wie folgt:", "",
             kvw([("Anreise", wdl(cin)), ("Abreise", wdl(cout)), ("Zimmer", rooms + (", inkl. Frühstück" if breakfast else ", ohne Frühstück")),
                  ("Nächte", str(nights)), ("Preis je Nacht", money(rate, mfmt) + " (inkl. gesetzl. MwSt.)"), ("Gesamtpreis", money(total, mfmt)),
                  ("Rechnungsanschrift", bill), ("Zahlung", "bei Abreise, Rechnung auf die Universität Wernstadt")], k=24, width=74)]
        if foot:
            L += [""] + foot
        L += ["", "Mit freundlichen Grüßen", "Ihre Rezeption"]
        return "\n".join(L)
    if style == "portal":
        L = [lr("STAYBOOK · Booking confirmation", f"Confirmation no. {bookno}", 100), "", h["name"] + ", " + h["city"],
             f"{h['street']}, {h['plz']} {h['city']}", "",
             kvw([("Guest", guest), ("Check-in", f"{wen(cin)} from 15:00"), ("Check-out", f"{wen(cout)} until 11:00"), ("Nights", str(nights)),
                  ("Room", rooms + (" - breakfast included" if breakfast else " - room only")), ("Price per night", money(rate, "en-eur")),
                  ("Total price", money(total, "en-eur")), ("Payment", "pay at the property · invoice to the company below"),
                  ("Invoice recipient", bill), ("Booked on", en_date(issued))], k=24, width=74)]
        if foot:
            L += [""] + foot
        L += ["", "This is not an invoice. The hotel issues the invoice on departure."]
        return "\n".join(L)
    if style == "mail":
        body = [f"Sehr geehrte Frau/Herr {guest.split()[-1]},", "", f"vielen Dank für Ihre Buchung. Wir haben für Sie reserviert:", "",
                f"{nights} Nacht/Nächte, {wdl(cin)} bis {wdl(cout)}", f"{rooms}, {'mit' if breakfast else 'ohne'} Frühstück", f"Preis je Nacht: {money(rate, mfmt)}, gesamt {money(total, mfmt)}",
                f"Rechnungsempfänger: {bill}", ""] + foot + ["", "Herzliche Grüße", h["name"]]
        return owa_mail(guest.lower().replace(" ", ".").replace("dr..", ""), f"Ihre Reservierung {bookno}", f"{h['name']} <reservierung@{h['mail'].split('@')[1]}>", wd(issued) + " 11:05", guest, body)
    if style == "fr":
        L = [lr(h["name"], f"{h['street']}, {h['plz']} {h['city']}", 100), "", UW, unit, f"À l'attention de {guest}", UW_ADDR, "",
             f"Confirmation de réservation n° {bookno}", "",
             kvw([("Arrivée", datef(cin, "slash")), ("Départ", datef(cout, "slash")), ("Chambre", "Chambre simple" + (", petit-déjeuner inclus" if breakfast else ", sans petit-déjeuner")),
                  ("Nuits", str(nights)), ("Tarif par nuit", money(rate, "eur") + " TTC"), ("Total", money(total, "eur") + " TTC"),
                  ("Facturation", bill), ("Paiement", "à la réception, facture au nom de l'université")], k=24, width=74)]
        if foot:
            L += [""] + foot
        return "\n".join(L)
    if style == "table":
        net, vat = vat_split(total, 7)
        w = [58, 6, 7, 11, 11]
        L = [lr(guest, h["name"], 100), lr(UW, f"{h['street']}", 100), lr(unit, f"{h['plz']} {h['city']}", 100), UW_ADDR, "",
             lr("", f"Buchungsnummer: {bookno}", 100), lr("", f"Buchungsdatum: {datef(issued, datefmt)}", 100), lr("", "Status: bestätigt, Zahlung bei Abreise", 100), "",
             "Buchungsbestätigung", "", row(["Beschreibung", "Menge", "MwSt", "netto", "brutto"], w, "lrrrr"),
             row([f"{nights} Nächte à {money(rate, mfmt)}, {wdl(cin)} bis {wdl(cout)}, {rooms}", str(nights), "7 %", money(net, mfmt), money(total, mfmt)], w, "lrrrr"), "",
             lr("", f"Rechnung an: {bill}", 100), lr("", f"Gesamt: {money(total, mfmt)}", 100)] + [""] + foot
        return "\n".join(L)
    raise ValueError(style)


def rail_doc(style, who, legs, prices, order, issued, foot=None, payer="persönliche Kreditkarte", lang="de", mfmt="de"):
    """rail booking. legs: [(date, dep, from, arr, to, train, class)]; prices: [(label, amount)], total = sum"""
    total = tot(*[a for _, a in prices])
    foot = foot or []
    if style == "bahn":
        L = [lr("Firmenkundenportal · Online-Ticket · Buchungsbestätigung", f"gedruckt am {datef(issued, 'de')}", 100), "",
             kvw([("Auftragsnummer", order), ("Kunde", f"{UW} (Firmenkundenrabatt 5 % berücksichtigt)"), ("Reisende:r", who), ("Zahlung", payer)], k=22, width=76), ""]
        for d, a, f, b, t, tr, cl in legs:
            L.append(f"{wd(d)}   {f} ab {a}  →  {t} an {b}   {tr}, {cl}")
        L += [""] + [row([lab, money(am, mfmt)], [70, 16], "lr") for lab, am in prices] + [row(["Gesamtpreis", money(total, mfmt)], [70, 16], "lr"), ""] + foot
        return "\n".join(L)
    if style == "practice":
        L = [lr(who, "Nordbahn Fernverkehr AG", 100), lr("", "Gleisfeld 4", 100), lr(UW, "60329 Frankfurt am Main", 100), "", lr("", f"Auftragsnummer: {order}", 100),
             lr("", f"Buchungsdatum: {datef(issued, 'de')}", 100), lr("", "Status: reserviert, zahlbar bei Abreise", 100), "", "Buchungsbestätigung",
             "Reservierung, noch keine Rechnung – Zahlung erfolgt erst nach Genehmigung der Dienstreise", "",
             row(["Beschreibung", "Menge", "MwSt", "netto", "brutto"], [58, 6, 8, 11, 11], "lrrrr")]
        for (d, a, f, b, t, tr, cl), (lab, am) in zip(legs, prices):
            net, vat = vat_split(am, 7)
            L.append(row([f"{f} → {t}, {datef(d, 'de')}, {a} Uhr, {cl}", "1", "7 % (D)", money(net, mfmt), money(am, mfmt)], [58, 6, 8, 11, 11], "lrrrr"))
        net, vat = vat_split(total, 7)
        L += ["", lr("", f"Summe brutto  {money(total, mfmt)}", 100), "Dieses Dokument berechtigt nicht zur Fahrt."] + foot
        return "\n".join(L)
    if style == "mail":
        body = ["Ihre Buchung ist bestätigt.", "", f"Auftrag {order}", ""]
        for d, a, f, b, t, tr, cl in legs:
            body.append(f"{wd(d)}  {a}  {f}  →  {b}  {t}   ({tr}, {cl})")
        body += [""] + [f"{lab}: {money(am, mfmt)}" for lab, am in prices] + [f"Gesamt: {money(total, mfmt)}", ""] + foot + ["", "Gute Reise!"]
        return owa_mail(who.lower().replace(" ", "."), f"Ihre Buchung {order} – Bestätigung", "Bahn.Business Service <noreply@bahn-business.example>", wd(issued) + " 08:40", who, body)
    if style == "en":
        L = [lr("RAILPLANNER BUSINESS · Booking confirmation", f"Booking {order}", 100), "", f"Passenger: {who}", f"Issued: {en_date(issued)}", ""]
        for d, a, f, b, t, tr, cl in legs:
            L.append(f"{wen(d)}   {a} {f}  ->  {b} {t}   {tr}, {cl}")
        L += [""] + [row([lab, money(am, 'en-eur')], [60, 16], "lr") for lab, am in prices] + [row(["Total", money(total, "en-eur")], [60, 16], "lr"), ""] + foot
        return "\n".join(L)
    raise ValueError(style)


# =========================================================================== #
# quoted rules (verbatim from the University of Kassel policy pages (not included here)) and sources
# =========================================================================== #
SRC_DRM, SRC_FIBU, SRC_BESCH, SRC_RV, SRC_DVK, SRC_GF, SRC_GLOS = B.SRC_DRM, B.SRC_FIBU, B.SRC_BESCH, B.SRC_RV, B.SRC_DVK, B.SRC_GF, B.SRC_GLOS
SRC_NC = "Uni-Kassel-Seite „Nachhaltiges Catering“ (doc 08143d1c-7e2f-4f9c-b6e0-42969f36852f)"
SRC_DM = "Uni-Kassel-Seite „Drittmittel – Projektdurchführung“ (doc 92d90600-da23-4865-a3d0-cc45bd823856)"
SRC_WEB = "Uni-Kassel-Seite „Web-to-Print Shop“ (doc 720c0ba3-3daf-4ee3-b600-e83cbee88ce9)"
SRC_WEB2 = "Uni-Kassel-Seite „Druckauftrag Visitenkarte“ (doc 6d727cc2-ddb8-4d8a-850b-2ae520e6351e)"
SRC_EB = "Uni-Kassel-Seite „WPS Ersteller-Besteller“ (doc 229ad709-b934-4bc4-8529-06ab4ec7801a)"
SRC_ITS = "Uni-Kassel-Seite „Endgeräte-Beschaffung – ITS“ (doc b47abafe-da27-4c97-b584-38b8683c959e)"
SRC_FB = "Uni-Kassel-Seite „Fahrbereitschaft / Dienstfahrzeuge“ (doc 39db75ef-0e83-46dc-8114-35b1f1a4fef5)"
SRC_ANL = "Uni-Kassel-Seite „Anlagen“ (doc 5143c85c-aa7a-4462-b6f4-155e47042775)"

R_BEFORE = ("„Reisekosten können nur für Dienstreisen und Reisen zur Fortbildung im dienstlichen Interesse erstattet werden, wenn diese "
            "vorher angeordnet oder genehmigt sind.“")
R_ATTACH = ("„Dem Reiseantrag sind grundsätzlich alle Unterlagen (Programme, Einladungen) als Anlage beizufügen, aus denen das "
            "dienstliche Interesse sowie Ort und Dauer der Abwesenheit hervorgeht.“")
R_HOTEL = ("„Nachgewiesene Übernachtungskosten sind bis zu einer Höhe von 80,00 € je Nacht erstattungsfähig.“ und „Rechnungen für "
           "Übernachtungskosten werden nur erstattet, sofern die Universität Kassel als Adressat angegeben ist.“")
R_HOTEL_ABROAD = ("„Nachgewiesene Übernachtungskosten werden bis zu einer Höhe des in der ARV ausgewiesenen Betrages für das jeweilige Land "
                  "erstattet.“ und „Rechnungen für Übernachtungskosten werden nur erstattet, sofern die Universität Kassel als Adressat angegeben ist.“")
R_A1 = ("„… wird empfohlen, spätestens acht Wochen vor Beginn einer Auslandsdienstreise die Genehmigung der Reise über das bekannte "
        "ESS-System … zu beantragen“")
R_PRIV5 = ("„Dauert der Privataufenthalt weniger als oder genau 5 Arbeitstage, so wird die Reisekostenvergütung so festgesetzt, als habe "
           "nur die Dienstreise stattgefunden.“")
R_PRIVMORE = ("„Dauert der Privataufenthalt mehr als 5 Arbeitstage, wird der Reise ein überwiegend privater Hintergrund zuerkannt.“ mit „In diesem "
              "Fall dürfen nur die zusätzlichen Fahrtauslagen erstattet werden, die zur Ausübung des Dienstgeschäftes notwendig sind. Tage- und "
              "Übernachtungsgeld sowie sonstige Kosten (Nebenkosten) werden nur für die Dauer des Dienstgeschäftes und die Reisetage gewährt.“")
R_CAR = ("„Für die Benutzung eines privaten Kraftfahrzeugs wird als Wegstreckenentschädigung ein Betrag von 0,21 € je zurückgelegtem Kilometer "
         "erstattet.“")
R_THIRD = ("„Die erhaltenen Leistungen von dritter Seite werden nach § 4 Abs. 3 HRKG bzw. § 3 Abs. 2 BRKG auf die zustehende Reisekostenerstattung "
           "angerechnet. Aus diesem Grund ist bei einer Reisekostenabrechnung anzugeben, welche Leistungen Sie erhalten haben.“")
R_HONORAR = ("„Wird Ihnen im Rahmen einer Dienstreise ein Honorar (z.B. für einen Vortrag) gezahlt, deutet dies auf eine Nebentätigkeit und damit "
             "auf eine privat veranlasste Reise hin.“ (hier: kein Honorar)")
R_PROF = ("„… gelten Dienstreisen und Reisen zum Zwecke der Fortbildung im Inland mit einer Dauer von bis sieben Tagen für Professorinnen und "
          "Professoren mit sofortiger Wirkung grundsätzlich qua Amt als genehmigt gem. § 2 Abs. 1 Satz 2 Hessisches Reisekostengesetz.“")
R_ABSCHLAG = ("„… kann auf Antrag ein Abschlag bis zur Höhe von 80% der zu erwartenden Reisekosten gezahlt werden. Dieser Abschlag wird allerdings "
              "nur dann angewiesen, wenn ein Betrag von 150 € überschritten wird.“")
R_FLUGIN = ("„Flugkosten kommen im Inland grundsätzlich nur in Betracht, wenn bei Benutzung eines anderen regelmäßig verkehrenden "
            "Beförderungsmittels höhere Kosten entstehen oder besondere dienstliche Gründe (wesentliche Einsparung von Arbeitszeit) vorliegen. Diese "
            "sind in einer Anlage zur Genehmigung der Dienstreise darzulegen.“ und „Erstattungsfähig ist ausschließlich die Economy Class.“")
R_FLUGPREIS = "„Bei Flugreisen ist dem Dienstreiseantrag ein Preisvergleich beizufügen.“"
R_TAXI = ("„Anfallende Nebenkosten (z. B. Taxi- und Telefonkosten etc.) können nur erstattet werden, sofern sie dienstlich notwendig und in der "
          "Reisekostenabrechnung entsprechend begründet werden.“")
R_TAGUNG = ("„Die auf den Rechnungen ausgewiesenen Verpflegungskosten für Mittag- uns Abendverpflegung werden im Rahmen von Reisekosten nur dann "
            "erstattet, wenn es sich nachweislich um eine notwendige Pauschale handelt (Tagungspauschale etc.).“")
R_RAHMENPROG = "„Rahmenprogramme, Finanzierung ggf. über Teilnahmegebühren möglich“ (Bewirtungskostenrichtlinie)"
R_HILFSKR = ("„Anträge auf Genehmigung einer Dienstreise sowie für die Erstattung von Reisekosten stellen Hilfskräfte bitte weiterhin in Papierform "
             "und fügen auch Belege in Papierform bei.“")
R_ASSIST = ("„Im Falle einer vorgesehenen Reiseassistenz … muss diese ebenfalls über den Fiori Benutzerantrag beantragt werden. Die "
            "Einverständnsierklärung für die Reiseassistenz ist ebenfalls mit einzureichen.“")
R_BAHNCARD = "„Sofern Sie im Besitz einer privaten BahnCard sind ist diese zwingend für Dienstreisen einzusetzen.“"
R_DRITT = "„Als Leistungen von dritter Seite gelten nicht Drittmittel, die von der Universität Kassel verwaltet werden.“"
R_EXK = ("„Die Exkursionsleitung bereitet den Antrag auf Genehmigung einer Exkursion … vor und reicht diesen vollständig ausgefüllt mindestens 14 Tage "
         "vor Beginn der Exkursion über das Dekanat bei der Abteilung Personal und Organisation ein.“ und „Als angemessen anzusehen ist in der "
         "Regel eine Begleitperson für jeweils 15 Studierende.“")
R_FAHRZEUG = "„Für Bedienstete der Universität Kassel besteht die Möglichkeit sich ein Fahrzeug aus dem Fuhrpark der Universität Kassel zu leihen.“"
R_CO2 = "„Die Kosten für CO2-Kompensationen sind nicht erstattungsfähig.“ (hier: nicht beantragt)"
R_ONLINE = ("„Konferenzen und Tagungen die online durchgeführt werden, sind keine Dienstreisen im Sinne des Reisekostengesetzes. … Die Teilnahmegebühren "
            "für Online Konferenzen / Tagungen sind über das Formular "
            "\"Privat Verauslagte Kosten\" bei der Finanzabteilung geltend zu machen.“")

# --------------------------------------------------------------------------- #
# trip helpers
# --------------------------------------------------------------------------- #
def nextwd(iso, weekday):
    d = dt(iso)
    while d.weekday() != weekday:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def weeks_before(iso, n, extra=0):
    return addday(iso, -(7 * n + extra))


def conf_pages(title, org, venue, addr, days, notes, url="https://tagung.example/programm", lang="de", fmt="de"):
    """web print of a programme page. days: [(iso date, [(time, text)])]"""
    L = [lr(url, "Ausdruck" if lang == "de" else "Printout", 100), "", title, org, f"{'Ort' if lang == 'de' else 'Venue'}: {venue}, {addr}", ""]
    for d, items in days:
        L.append((wdl(d) if lang == "de" else wen(d)))
        for tm, tx in items:
            L.append(f"   {tm}   {tx}")
        L.append("")
    L += notes
    return "\n".join(L)


def reg_invoice(lang, issuer, to_lines, title, nr, issued, items, vatnote, notes, dfmt="de", mfmt="de", payline=None):
    """conference registration invoice; items: [(text, qty, net, gross)]"""
    LB = {"de": ("Rechnungsnummer", "Rechnungsdatum", "Beschreibung", "Menge", "netto", "brutto", "Summe"),
          "en": ("Invoice no.", "Invoice date", "Description", "Qty", "net", "gross", "Total"),
          "fr": ("Facture n°", "Date de facture", "Designation", "Qte", "HT", "TTC", "Total")}[lang]
    L = [lr(issuer[0], "", 100)] + [lr("", x, 100) for x in issuer[1:]] + [""] + to_lines + [""]
    L += [lr("", f"{LB[0]}: {nr}", 100), lr("", f"{LB[1]}: {datef(issued, dfmt)}", 100), ""]
    L += [title, ""]
    w = [58, 5, 14, 14]
    L.append(row([LB[2], LB[3], LB[4], LB[5]], w, "lrrr"))
    for tx, q, n, g in items:
        for k, l_ in enumerate(wrap(tx, 58)):
            L.append(row([l_, str(q) if k == 0 else "", money(n, mfmt) if k == 0 else "", money(g, mfmt) if k == 0 else ""], w, "lrrr"))
    L += ["", lr("", f"{LB[6]}: {money(tot(*[g for _, _, _, g in items]), mfmt)}", 100), "", vatnote, ""] + notes
    if payline:
        L += ["", payline]
    return "\n".join(L)


def ticket_kv(rows, k=24, width=74):
    return kvw(rows, k, width, 0)


# =========================================================================== #
# TRIPS  (dienstreiseantrag-k01 .. k25)
# =========================================================================== #
def k01():
    p = staff(1, "Dr.", fb="71")
    cid = "dienstreiseantrag-k01"
    out, back = "2027-03-09", "2027-03-10"
    created = addday(out, -29)
    costs = [("Bahn", "Wernstadt Hbf – Leipzig Hbf und zurück, 2. Klasse", D("109.80")), ("Übernachtung", "1 Nacht à 79,00 € inkl. Frühstück", D("79.00"))]
    T = dict(person=p, nr="4417311502", created=created, dest="Leipzig", country="DEUTSCHLAND", abroad=False,
             anlass="Workshop „Eingebettete Systeme in der Praxis“ des Regionalverbunds Embedded Mitteldeutschland",
             grund="Vortrag „Zeitgeberdrift in verteilten Messnetzen“ (Beitrag angenommen, Einladung liegt bei)", mode="Bahn, 2. Klasse (Sparpreis)",
             start=(out, "06:05"), end=(back, "20:50"), biz_from=(out, "10:00"), biz_to=(back, "13:30"), priv="keiner", nights=1,
             costs=costs, finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}"), ("Abschlag beantragt", "nein")],
             remarks=[], attach=["Einladung_Workshop_EmbeddedMD.pdf", "Bahnbuchung.pdf", "Hotelbestaetigung.pdf"])
    antrag = trip_antrag("fiori", T)
    rail = rail_doc("bahn", p["plain"], [(out, "06:42", "Wernstadt Hbf", "10:15", "Leipzig Hbf", "ICE 1527", "2. Klasse Sparpreis"),
                                         (back, "15:38", "Leipzig Hbf", "19:21", "Wernstadt Hbf", "ICE 1594", "2. Klasse Sparpreis")],
                    [("Hinfahrt Sparpreis", D("49.90")), ("Rückfahrt Sparpreis", D("59.90"))], "C7K-44519", addday(created, 2),
                    foot=["* Flexpreis wäre 98,80 € je Strecke gewesen. Aufpreis 1. Klasse 29,00 € (nicht gebucht).", "* Stornierung des Sparpreises vor Reiseantritt: 17,50 € je Ticket."])
    hot = hotel_doc("letter", dict(name="Hotel Lindenhof Leipzig", street="Gerberstraße 14", plz="04105", city="Leipzig", tel="0341 5520-0", mail="rezeption@lindenhof-leipzig.example"),
                    p["name"], p["org_long"], 1, D("79.00"), out, back, "LH-27-30118", addday(created, 3),
                    foot=["Stornierung bis 18:00 Uhr am Anreisetag kostenfrei, danach 79,00 €. Parkplatz 12,00 € je Nacht (nicht gebucht)."])
    inv = owa_mail(p["email"].split("@")[0], "Einladung zum Workshop „Eingebettete Systeme in der Praxis“, 9./10. März 2027, Leipzig",
                   "Regionalverbund Embedded Mitteldeutschland <workshop@embedded-md.example>", f"{wd(addday(out, -52))} 14:21", p["name"],
                   ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", "wir freuen uns, Ihren Beitrag in das Programm des Workshops aufzunehmen.", "",
                    f"Termin: {wd(out)}, 10:00 Uhr bis {wd(back)}, 13:30 Uhr", "Ort:    Handwerkskammer Leipzig, Dresdner Straße 11, 04103 Leipzig", "",
                    "Ihr Vortrag (20 Minuten) ist für den ersten Tag um 14:40 Uhr vorgesehen. Die Teilnahme ist gebührenfrei.",
                    "Ein Honorar wird nicht gezahlt, Reisekosten werden nicht übernommen.", "", "Freundliche Grüße", "Das Organisationsteam"])
    begr = (f"Der Antrag wurde am {de(created)} gestellt, 29 Tage vor Reisebeginn am {de(out)}. Die Einladung belegt das dienstliche Interesse (Vortrag), Ort und Dauer; "
            "Bahn (Sparpreis, 2. Klasse) und eine Übernachtung zu 79,00 € inkl. Frühstück liegen unter der Höchstgrenze von 80,00 €, das Hotel adressiert die Universität. "
            "Summe 188,80 € aus Landesmitteln der Kostenstelle; Aufpreise und Stornogebühren in den Fußnoten gehören nicht zum Antrag.")
    case(TRIP, cid, [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica", producer="SAP Fiori Print", creator="Chromium"),
                     doc("bahn-buchung-firmenkundenportal.pdf", rail, font="Helvetica"), doc("hotel-bestaetigung.pdf", hot, font="Times-Roman"),
                     doc("email-einladung-workshop.pdf", inv, font="Helvetica")], begr,
         "SAP Fiori Reiseantrag + DB-Firmenkundenportal-Ticket + Hotelbrief + Outlook-Einladung",
         "Fußnoten mit Beträgen, die nicht beantragt sind (Flexpreis 98,80, 1. Klasse +29,00, Storno 17,50, Parkplatz); „Honorar wird nicht gezahlt“",
         R_BEFORE + " " + R_HOTEL, SRC_DRM)


def k02():
    p = staff(2, "Dr.", fb="73")
    cid = "dienstreiseantrag-k02"
    out, back = "2027-05-17", "2027-05-21"
    created = weeks_before(out, 10)
    reg = D("395.00")
    costs = [("Konferenzregistrierung", "Early Bird, Mitglied", reg), ("Bahn Wernstadt – Eindhoven und zurück", "2. Klasse, Sparpreis", D("142.80")),
             ("Unterkunft", "4 Nächte à 74,00 €, ohne Frühstück", D("296.00"))]
    T = dict(person=p, nr="3381029871", created=created, dest="Eindhoven", country="NIEDERLANDE", abroad=True,
             anlass="OptoSys 2027 – International Workshop on Integrated Optics and Sensing",
             grund="Vortrag des nach Begutachtung angenommenen Beitrags „Coupling Loss in Thin-Film Waveguides“",
             mode="Bahn, 2. Klasse (An- und Abreisetag)", start=(out, "06:10"), end=(back, "21:30"), biz_from=(addday(out, 1), "09:00"),
             biz_to=(addday(back, -1), "17:30"), priv="keiner", nights=4, a1=f"beantragt am {de(created)} (Vorlauf > 8 Wochen)",
             costs=costs, finance=[("Finanzierung", f"Fachgebietsbudget Photonik, Kostenstelle {p['ks']}")],
             remarks=["Der Beitrag wurde nach Begutachtung angenommen (Annahmebestätigung liegt bei). Die Übernachtung erfolgt in Konferenznähe; der Satz von 74,00 € "
                      "liegt innerhalb der Höchstgrenze des Auslandsübernachtungsgeldes für die Niederlande."],
             attach=["Annahme-Mail.pdf", "Registrierung.pdf", "Bahnbuchung.pdf", "Hotel.pdf"])
    antrag = trip_antrag("ess", T, glyph="times")
    h = dict(name="Hotel De Brug", street="Stationsplein 14", plz="5611 AB", city="Eindhoven", tel="+31 40 555 0142", mail="reservations@hoteldebrug.example")
    hot = hotel_doc("portal", h, p["plain"], p["org_long"], 4, D("74.00"), out, back, "SB-8829-4471", addday(created, 5), breakfast=False,
                    foot=["Breakfast buffet is available for EUR 12.50 per person and day (not booked). Tourist tax EUR 3.90 per night is collected at check-out. Free cancellation until 5 days before arrival."],
                    datefmt="en")
    rail = rail_doc("en", p["plain"], [(out, "06:25", "Wernstadt Hbf", "13:52", "Eindhoven Centraal", "ICE 14 / IC 8", "2nd class"),
                                       (back, "13:10", "Eindhoven Centraal", "20:41", "Wernstadt Hbf", "IC 8 / ICE 23", "2nd class")],
                    [("Outbound saver fare", D("68.40")), ("Return saver fare", D("74.40"))], "RP-77120-NL", addday(created, 6),
                    foot=["Flexible fare for the same journey: EUR 186.00. Seat reservation (optional, EUR 4.50 per seat) not booked."])
    regd = reg_invoice("en", ["OptoSys 2027 Conference Office", "c/o Eventlab B.V.", "Dommelstraat 21, 5611 CK Eindhoven, The Netherlands", "VAT NL812449770B01"],
                       [UW, p["org_long"], f"z. Hd. {p['name']}", UW_ADDR], "Registration confirmation / Invoice", "OS27-INV-0388", addday(created, 7),
                       [("Full registration, early bird, member rate (includes 3 days of sessions, coffee breaks, two lunches and the welcome reception on Monday evening)", 1, reg, reg)],
                       "VAT 0 % (reverse charge, Art. 44 VAT Directive). The recipient is the University.",
                       ["The optional conference dinner (EUR 65.00) is not part of this registration and was not booked.", "Payment: bank transfer within 30 days, status: open - payment after approval of the trip."],
                       dfmt="en-short", mfmt="en-eur")
    acc = owa_mail(p["email"].split("@")[0], "OptoSys 2027 – Paper acceptance (#64)", "OptoSys 2027 Program Chairs <chairs@optosys2027.example>", f"{wd(addday(created, -20))} 21:03", p["plain"],
                   ["Dear Dr. " + p["last"] + ",", "", "we are pleased to inform you that your contribution", "", "#64 - \"Coupling Loss in Thin-Film Waveguides\"", "",
                    "has been accepted as an oral presentation at OptoSys 2027, Eindhoven, 18-20 May 2027. At least one author must register and present on site.",
                    "No honorarium and no travel support can be offered.", "", "Best regards,", "The OptoSys 2027 Program Committee"])
    begr = (f"Antrag vom {de(created)}, mehr als zehn Wochen vor Reisebeginn; das Feld „Reise ins Ausland“ ist angekreuzt (Zeichen [×]), die A1-Bescheinigung ist rechtzeitig beantragt. "
            "Die Annahmebestätigung belegt Vortrag und Anlass; Bahn 2. Klasse, Hotel zu 74,00 € je Nacht (ohne Frühstück, auf die Universität ausgestellt) und die Registrierungsgebühr "
            "(inkl. Empfang, Reverse Charge) ergeben 833,80 €. Das optionale Konferenzdinner ist nicht gebucht.")
    case(TRIP, cid, [doc("antrag-dienstreisegenehmigung.pdf", antrag, producer="ESS Reisemanagement"), doc("anlage-2.pdf", rail, font="Helvetica"),
                     doc("Dokument.pdf", hot, font="Helvetica"), doc("registration-invoice.pdf", regd, font="Helvetica"), doc("accepted.pdf", acc, font="Helvetica")], begr,
         "ESS-Antrag (Stil der Organisatoren) mit „[×]“ + englische Bahn-, Hotel- und Konferenzdokumente, neutrale Dateinamen",
         "Auslandsfeld mit Zeichen „[×]“; Anmeldegebühr enthält Empfang und Mittagessen; Fußnoten mit Frühstück 12,50, Dinner 65,00, Kurtaxe 3,90 (nicht beantragt)",
         R_A1 + " " + R_HOTEL_ABROAD + " " + R_RAHMENPROG, SRC_DRM + "; " + SRC_FIBU)


def k03():
    p = staff(3, "", fb="75")
    cid = "dienstreiseantrag-k03"
    out, back = "2027-04-13", "2027-04-14"
    created = weeks_before(out, 4)
    costs = [("Bahn", "Wernstadt – Hannover Hbf und zurück, 2. Klasse Sparpreis", D("94.80")), ("Übernachtung", "1 Nacht à 77,00 € (Frühstück inkl.)", D("77.00"))]
    T = dict(person=p, nr="WEB-27-018842", created=created, dest="Hannover", country="Deutschland", abroad=False,
             anlass="Jahrestagung des Arbeitskreises Rechnungswesen in Forschungsbetrieben (AKRF)",
             grund="Teilnahme am Praxisforum „Kostenrechnung für Drittmittelprojekte“; Fortbildung im Aufgabengebiet Haushalt/Drittmittel", mode="Bahn (2. Klasse), Sparpreis",
             start=(out, "06:50"), end=(back, "19:40"), biz_from=(out, "10:30"), biz_to=(back, "15:00"), priv="keiner", nights=1, costs=costs, mfmt="plain",
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)"), ("Auftrag", p["auftrag"])],
             remarks=["Tagungsgebühr entfällt (Mitgliedschaft der Universität im AKRF).", "Hotel: Tagungshotel, Rechnung auf die Universität."],
             attach=["Programm_AKRF_2027.pdf", "Bahnbuchung.pdf", "Hotelreservierung.pdf"], time="08:41")
    antrag = trip_antrag("web", T, glyph="tick", datefmt="iso")
    prog = conf_pages("AKRF-Jahrestagung 2027", "Arbeitskreis Rechnungswesen in Forschungsbetrieben", "Tagungshotel Messe-Nord", "Hannover",
                      [(out, [("10:30", "Begrüßung und Eröffnung"), ("11:00", "Praxisforum „Kostenrechnung für Drittmittelprojekte“"), ("12:30", "Mittagspause (Imbiss kostenfrei)"), ("14:00", "Arbeitsgruppen")]),
                       (back, [("09:00", "Plenum: Neues aus den Förderrichtlinien"), ("11:00", "Podium"), ("13:00", "Mittagsimbiss"), ("15:00", "Ende der Tagung")])],
                      ["Teilnahmegebühr für Mitgliedseinrichtungen: entfällt. Mittagsimbiss und Kaffeepausen sind für Teilnehmende kostenfrei.", "Anmeldung bis 31. März 2027."],
                      url="https://www.akrf-tagung.example/2027/programm")
    rail = rail_doc("mail", p["plain"], [(out, "06:55", "Wernstadt Hbf", "10:02", "Hannover Hbf", "ICE 612", "2. Klasse"), (back, "16:20", "Hannover Hbf", "19:31", "Wernstadt Hbf", "ICE 613", "2. Klasse")],
                    [("Hinfahrt Sparpreis", D("44.90")), ("Rückfahrt Sparpreis", D("49.90"))], "7714-2288-ZK", addday(created, 3), mfmt="plain")
    hot = hotel_doc("mail", dict(name="Tagungshotel Messe-Nord", street="Messeallee 3", plz="30521", city="Hannover", tel="0511 8800-0", mail="reservierung@messenord-hotel.example"),
                    p["plain"], p["org_long"], 1, D("77.00"), out, back, "TMN-5521", addday(created, 4), mfmt="plain",
                    foot=["Zusatzleistung Parkplatz 14,00 € (nicht gebucht).", "Kostenfreie Stornierung bis 3 Tage vor Anreise."])
    begr = (f"Antrag vom {datef(created, 'iso')} (online), vier Wochen vor der Reise. Das Programm der Tagung und die Bahn- und Hotelunterlagen zeigen Ort und Dauer; die Fortbildung "
            "im Aufgabengebiet begründet das dienstliche Interesse. Bahn 94,80 € und eine Nacht zu 77,00 € (unter 80,00 €, Rechnung auf die Universität). Summe 171,80 € aus Landesmitteln.")
    case(TRIP, cid, [doc("online-antrag-WEB-27-018842.pdf", antrag, font="Helvetica", producer="Mozilla Firefox 125", creator="Dienstreise-Portal"), doc("programm.pdf", prog, font="Helvetica"),
                     doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica")], begr,
         "Online-Formular-Ausdruck (Web) mit Ankreuzzeichen „[✔]“, ISO-Datum, Beträge „94.80 EUR“-Stil; Programm als Webseite, Bahn/Hotel als Mail-Ausdruck",
         "Beträge im Format 94.80 EUR und ISO-Daten; Mittagsimbiss im Programm kostenfrei; Parkplatz 14,00 € nicht gebucht",
         R_ATTACH + " " + R_HOTEL, SRC_DRM)


def k04():
    p = staff(4, "", fb="76")
    cid = "dienstreiseantrag-k04"
    day = "2027-06-08"
    created = weeks_before(day, 3)
    costs = [("Bahn", "Wernstadt – Göttingen und zurück, 2. Klasse Sparpreis", D("77.80"))]
    T = dict(person=p, nr="", created=created, dest="Göttingen", country="DEUTSCHLAND", abroad=False,
             anlass="Praxistag Laborautomation, Universität Göttingen (Gastgeber Institut für Mikrobiologie)",
             grund="Hilfskraft begleitet Dr. Wiebke Achterhold-Runge zur Einweisung in das Pipettiersystem (Projektmitarbeit)", mode="Bahn 2. Klasse",
             start=(day, "07:10"), end=(day, "19:55"), biz_from=(day, "10:00"), biz_to=(day, "16:30"), priv="keiner", nights=0, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Hilfskraftmittel, FG {p['fg']})")], remarks=["Studentische Hilfskraft; Antrag und Belege in Papierform (Hilfskräfte haben keinen Fiori-Zugang)."],
             attach=["Einladung Praxistag", "Fahrkarte (Kopie)"], caps=True)
    antrag = trip_antrag("paper", T, glyph="cross")
    antrag += "\n\nGenehmigt (Fachgebietsleitung): Prof. Dr. Quirin Seidelmann-Voss      Datum: " + de(addday(created, 2))
    einl = "\n".join(["Universität Göttingen · Institut für Mikrobiologie · Praxistag Laborautomation", "", "An die Universität Wernstadt, FG " + p["fg"], "z. Hd. Frau Dr. Achterhold-Runge und Mitarbeitende", "",
                      f"Göttingen, den {de(addday(day, -30))}", "", "Sehr geehrte Frau Dr. Achterhold-Runge,", "",
                      f"gern bestätigen wir Ihre Anmeldung zum Praxistag Laborautomation am {wdl(day)}, 10:00 bis 16:30 Uhr, Institut für Mikrobiologie, Grisebachstraße 8.",
                      "Angemeldet sind Sie und eine Mitarbeitende/ein Mitarbeiter (Einweisung in das Pipettiersystem). Die Teilnahme ist kostenfrei; es wird kein Honorar gezahlt.", "",
                      "Mit freundlichen Grüßen", "Institut für Mikrobiologie, Sekretariat"])
    fk = "\n".join(["DEUTSCHE BAHN  FAHRKARTE  Sparpreis  2. Klasse", "", f"Hinfahrt: {datef(day, 'de')}  Wernstadt Hbf 07:10  -> Göttingen 09:24  ICE 1241", f"Rückfahrt: {datef(day, 'de')}  Göttingen 16:48  -> Wernstadt Hbf 19:01  ICE 1244",
                    "", "Preis Hinfahrt 36,90 EUR    Preis Rückfahrt 40,90 EUR", "Gesamt 77,80 EUR      Kunde: Universität Wernstadt (Firmenkunde)", f"Reisende: {p['plain']}"])
    parts = [(einl, dict(font="Times-Roman", jitter=1.2)), (antrag, dict(font="Courier", jitter=1.0)), (fk, dict(font="Courier", jitter=0.8, size=(420, 595)))]
    random.Random(cid).shuffle(parts)
    begr = ("Papierantrag einer studentischen Hilfskraft (Hilfskräfte stellen Anträge weiterhin in Papierform), drei Wochen vor dem Tagesausflug nach Göttingen und von der Fachgebietsleitung genehmigt. "
            "Die Einladung belegt Anlass, Ort und Dauer (kein Honorar), die Bahnkarte 77,80 € ist die einzige Kostenposition. Alle Unterlagen liegen in einer gescannten Datei in beliebiger Reihenfolge vor.")
    case(TRIP, cid, [doc("Dokument.pdf", parts, producer="Canon iR-ADV Scan", creator="Scan")], begr,
         "Papierantrag einer Hilfskraft (Scan mit Zeilenversatz), Einladung und Fahrkarte; alles in EINER Datei, Seiten in zufälliger Reihenfolge, verschiedene Seitenformate/Schriften",
         "Hilfskraft ohne Fiori-Zugang; Antrag in Großbuchstaben; Genehmigungsvermerk am Ende; Reihenfolge Einladung/Antrag/Fahrkarte beliebig",
         R_HILFSKR, SRC_DRM)


def k05():
    p = staff(5, "Prof. Dr.", fb="72")
    cid = "dienstreiseantrag-k05"
    out, back = "2027-06-14", "2027-06-18"
    created = weeks_before(out, 11)
    flight = D("238.40")
    reg = D("420.00")
    costs = [("Flug", "FRA–LIS–FRA, Economy", flight), ("Bahn zum/vom Flughafen Frankfurt", "2. Klasse, hin/zurück", D("64.00")), ("Unterkunft", "4 Nächte à 73,00 €, ohne Frühstück", D("292.00")),
             ("Konferenzgebühr", "Registrierung inkl. Empfang", reg)]
    T = dict(person=p, nr="4417318840", created=created, dest="Lissabon", country="PORTUGAL", abroad=True,
             anlass="FlowTech Europe 2027 – European Conference on Applied Fluid Mechanics", grund="Eingeladener Plenarvortrag (Keynote) und Leitung der Sitzung „Turbulence Modelling“",
             mode="Flug (Economy), Bahn zum Flughafen", extra_general=[("Begründung Flug", "Bahnfahrt Wernstadt–Lissabon dauert > 24 h; Preisvergleich liegt bei")],
             start=(out, "05:30"), end=(back, "22:10"), biz_from=(addday(out, 1), "09:00"), biz_to=(addday(back, -1), "18:00"), priv="keiner", nights=4, a1=f"beantragt am {de(created)} (Vorlauf > 10 Wochen)",
             costs=costs, finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}")], remarks=[],
             attach=["Einladung_FlowTech.pdf", "Flugbuchung.pdf", "Preisvergleich_Bahn_Flug.pdf", "Hotel.pdf", "Registrierung.pdf"], mfmt="eur")
    antrag = trip_antrag("fiori", T, datefmt="de")
    fl = "\n".join([lr("SKYBOOKER BUSINESS · Booking confirmation", f"printed {en_date(addday(created, 4))}", 100), "", "Booking reference: MPQ-77K3L", f"Passenger: {p['last'].upper()}/{p['first'].upper()} PROF DR",
                    f"Company: Universitaet Wernstadt, {p['fg']}", "", "FLIGHTS", "  " + row(["Flight", "Date", "From", "Dep", "To", "Arr", "Class"], [8, 18, 20, 6, 20, 6, 14], "lllllll"),
                    "  " + row(["MR 405", wen(out), "Frankfurt FRA T1", "07:45", "Lisbon LIS T1", "09:55", "Economy Light"], [8, 18, 20, 6, 20, 6, 14], "lllllll"),
                    "  " + row(["MR 408", wen(back), "Lisbon LIS T1", "17:20", "Frankfurt FRA T1", "21:25", "Economy Light"], [8, 18, 20, 6, 20, 6, 14], "lllllll"), "",
                    "PRICE", "  " + row(["Fare", money(D('201.00'), 'en-eur')], [40, 14], "lr"), "  " + row(["Taxes, fees and charges", money(D('31.40'), 'en-eur')], [40, 14], "lr"),
                    "  " + row(["Service fee", money(D('6.00'), 'en-eur')], [40, 14], "lr"), "  " + row(["Total", money(flight, 'en-eur')], [40, 14], "lr"), "",
                    "Optional (not selected): CO2 compensation EUR 9.40 · checked baggage EUR 48.00 · seat selection EUR 12.00",
                    "Ticket number: 220-4418820755 · e-ticket issued. Changes not permitted."])
    assert tot("201.00", "31.40", "6.00") == flight
    pv = "\n".join(["Reisebüro Campus Wernstadt GmbH · Rahmenvertragspartner der Universität Wernstadt", "", f"Preisvergleich Flug / Bahn · Angebotsnr. RCW-27-0912 · {de(addday(created, 3))}", "",
                    "Strecke: Wernstadt – Lissabon und zurück, 1 Person", "",
                    row(["Variante", "Dauer einfach", "Preis hin/zurück"], [58, 14, 18], "lrr"),
                    row(["A  Flug Frankfurt–Lissabon (Economy), Bahn zum Flughafen", "ca. 8 h", money(tot(flight, '64.00'), 'de')], [58, 14, 18], "lrr"),
                    row(["B  Bahn (über Paris/Irun, Nachtzug)", "ca. 27 h", money(D('684.00'), 'de')], [58, 14, 18], "lrr"), "",
                    f"Variante A ist günstiger und spart rund 19 Stunden Reisezeit je Richtung. Rückreise direkt nach Ende des Dienstgeschäfts ({wd(back)} Abflug)."])
    h = dict(name="Hotel Praça Nova", street="Rua da Palma 112", plz="1100-391", city="Lisboa", tel="+351 21 555 0188", mail="geral@pracanova-hotel.example")
    hot = hotel_doc("portal", h, p["plain"], p["org_long"], 4, D("73.00"), out, back, "HPN-27-0455", addday(created, 5), breakfast=False, foot=["Tourist tax EUR 2.00 per person and night (not included, paid on site by the guest)."])
    regd = reg_invoice("en", ["FlowTech Europe 2027 Secretariat", "Av. da Liberdade 110, 1269-046 Lisboa, Portugal", "VAT PT 5xx xxx xxx"], [UW, p["org_long"], f"Attn. {p['name']}", UW_ADDR],
                       "Registration confirmation / Invoice", "FT27-0731", addday(created, 6),
                       [("Invited speaker registration incl. welcome reception on Monday evening, coffee breaks and lunches (Tue-Thu)", 1, reg, reg)],
                       "No VAT charged (reverse charge). Recipient: Universität Wernstadt.", ["Gala dinner (EUR 85.00) is not included in this fee and has not been booked."], dfmt="dmy-en", mfmt="eur-sp")
    einl = owa_mail(p["email"].split("@")[0], "Invitation: Plenary Lecture at FlowTech Europe 2027", "FlowTech Europe 2027 Steering Committee <chairs@flowtech-europe.example>", f"{wd(addday(created, -60))} 09:30", p["plain"],
                    ["Dear Professor " + p["last"] + ",", "", "on behalf of the Steering Committee I am delighted to invite you to give a plenary lecture at FlowTech Europe 2027 (Lisbon, 15-17 June 2027).", "",
                     "The lecture is scheduled for Tuesday, 15 June, 09:30. You are also invited to chair the session 'Turbulence Modelling' on Wednesday.", "The speaker registration fee is EUR 420.00. We are not able to offer an honorarium or to cover travel costs.", "",
                     "Kind regards,", "Prof. Dr. M. Tavares, Chair"])
    begr = (f"Antrag vom {de(created)}, elf Wochen vor Reisebeginn, Auslandsfeld mit (x) markiert, A1 beantragt. Der Flug ist mit Preisvergleich Bahn/Flug (Bahn 27 h und teurer) begründet, Economy, Rückflug direkt nach dem Dienstgeschäft. "
            "Hotel 73,00 € je Nacht ohne Frühstück auf die Universität, Konferenzgebühr inkl. Empfang laut Rechnung; Summe 1.014,40 €.")
    case(TRIP, cid, [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica", producer="SAP Fiori Print"), doc("flugbuchung.pdf", fl, font="Helvetica"), doc("preisvergleich-reisebuero.pdf", pv, font="Times-Roman"),
                     doc("hotel-lisboa.pdf", hot, font="Helvetica"), doc("rechnung-konferenz.pdf", regd, font="Helvetica"), doc("email-einladung.pdf", einl, font="Helvetica")], begr,
         "SAP Fiori + Airline-Portal (EN) + Reisebüro-Preisvergleich + Hotelportal (EN) + Konferenzrechnung (EN, „EUR 1 234,56“-Format)",
         "Flug mit Preisvergleich Bahn/Flug; Betragsformat „EUR 1 014,40“; Gebühr enthält Empfang; Fußnoten mit CO2-Ausgleich 9,40, Gepäck 48,00, Galadinner 85,00, Kurtaxe (nicht beantragt)",
         R_FLUGPREIS + " und „Erstattungsfähig ist ausschließlich die Economy Class.“", SRC_DRM + "; " + SRC_FIBU)


def letter(frm_lines, to_lines, date_line, subject, body, sign):
    L = [lr(frm_lines[0], "", 100)] + [lr("", x, 100) for x in frm_lines[1:]] + [""] + to_lines + ["", date_line, "", subject, ""] + body + ["", "Mit freundlichen Grüßen"] + sign
    return "\n".join(L)


def k06():
    p = staff(6, "Dr.", fb="74")
    cid = "dienstreiseantrag-k06"
    day = "2027-04-27"
    created = weeks_before(day, 5)
    km, rate = 214, D("0.21")
    pkw = r2(km * 2 * rate)
    assert pkw == D("89.88")
    costs = [("Wegstrecke Privat-Pkw", f"{km * 2} km × 0,21 € Wegstreckenentschädigung", pkw)]
    T = dict(person=p, nr="4417324107", created=created, dest="Würzburg", country="DEUTSCHLAND", abroad=False,
             anlass="Probenahme und Abstimmungstermin im Prüffeld Bodenmechanik, Institut für Bodenmechanik Würzburg",
             grund="Gemeinsame Entnahme von 12 Bodenproben (Verbundprojekt „SandFlex“), Gerät- und Probentransport", mode="Privat-Pkw (0,21 € je km); Parkgebühren werden nicht beantragt",
             start=(day, "06:30"), end=(day, "19:30"), biz_from=(day, "09:30"), biz_to=(day, "16:00"), priv="keiner", nights=0, costs=costs,
             finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['dr_auftrag']} (Drittmittel SandFlex)"), ("Abschlag beantragt", "nein")],
             remarks=[f"Wirtschaftlicher als die Bahn: Bahn hin/zurück für eine Person 136,60 €, Pkw {eur(pkw)} €; zusätzlich werden 40 kg Probenmaterial transportiert."],
             attach=["Einladung_Probenahme.pdf", "Routenplaner_Ausdruck.pdf"])
    antrag = trip_antrag("fiori", T, datefmt="de2")
    route = "\n".join([lr("Routenplaner · Strecke berechnen", f"Ausdruck {datef(created, 'de')}", 100), "", f"Start:  Universität Wernstadt, {UW_STREET}, {UW_CITY}",
                       "Ziel:   Institut für Bodenmechanik, Hubland-Nord 5, 97074 Würzburg", "", "Empfohlene Route (schnellste): über A7", row(["Strecke", "Entfernung", "Fahrzeit"], [34, 12, 12], "lrr"),
                       row(["Hinfahrt", f"{km} km", "2 Std. 31 Min."], [34, 12, 12], "lrr"), row(["Rückfahrt", f"{km} km", "2 Std. 28 Min."], [34, 12, 12], "lrr"),
                       row(["Gesamt", f"{km * 2} km", ""], [34, 12, 12], "lrr"), "", f"Hinweis: Mautfreie Strecke. Alternative über B27: 231 km (nicht gewählt).", "Kein Anspruch auf Richtigkeit der Angaben."])
    br = letter(["Institut für Bodenmechanik", "Hubland-Nord 5 · 97074 Würzburg"], [UW, f"FG {p['fg']}", f"z. Hd. {p['name']}"], f"Würzburg, {datef(addday(day, -45), 'long')}",
                "Probenahme im Prüffeld am " + datef(day, "long"), ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"wie besprochen findet die gemeinsame Entnahme der Bodenproben am {wdl(day)} ab 09:30 Uhr im Prüffeld Süd statt.",
                                                                    "Bitte bringen Sie Ihre Probenbehälter und das Messgerät mit. Parkplätze stehen auf dem Institutsgelände kostenfrei zur Verfügung.", "Eine Vergütung ist nicht vorgesehen."], ["Dr. K. Wiegand-Aziz"])
    begr = ("Antrag fünf Wochen vor der Fahrt. Privat-Pkw mit dem Grundsatz von 0,21 € je km (2 × 214 km = 428 km, 89,88 €); die Kosten liegen unter der Bahnalternative (136,60 €), der Probentransport begründet die Wahl. "
            "Parkgebühren sind nicht beantragt, die Einladung des Instituts belegt Ort, Dauer und Anlass.")
    case(TRIP, cid, [doc("fiori-reiseantrag.pdf", antrag, font="Helvetica"), doc("route.pdf", route, font="Helvetica"), doc("brief-probenahme.pdf", br, font="Times-Roman")], begr,
         "Fiori mit Datum „27.04.27“ + Routenplaner-Ausdruck + Einladungsbrief (Times)", "Privat-Pkw mit 0,21 €/km; Pkw-Rechnung 428 km × 0,21; Alternativroute 231 km und Bahnpreis nur im Vergleich genannt; „keine Vergütung“",
         R_CAR + " " + R_ATTACH, SRC_DRM)


def k07():
    p = staff(7, "", fb="79")
    cid = "dienstreiseantrag-k07"
    out, bz, back = "2027-09-16", "2027-09-17", "2027-09-20"
    created = weeks_before(out, 6)
    assert workdays("2027-09-18", back) == 1
    costs = [("Bahn Hinfahrt", "Do, 2. Klasse Sparpreis", D("69.90")), ("Bahn Rückfahrt", "Vergleichspreis Freitag (dienstlicher Rückreisetag)", D("59.90")),
             ("Übernachtung", "1 Nacht (Do–Fr) à 78,00 €, inkl. Frühstück", D("78.00")), ("Tagungsgebühr", "inkl. Empfang am Donnerstagabend", D("120.00"))]
    T = dict(person=p, nr="4417325562", created=created, dest="Hamburg", country="DEUTSCHLAND", abroad=False,
             anlass="Symposium „Urbane Dichte und Freiraum“ der Gesellschaft für Stadtforschung", grund="Vortrag im Panel „Nachverdichtung im Bestand“ (Programm anbei)", mode="Bahn, 2. Klasse",
             start=(out, "06:20"), end=(back, "21:30"), biz_from=(out, "13:00"), biz_to=(bz, "12:30"),
             priv=f"{de('2027-09-18')} bis {de(back)}: 1 Arbeitstag (Montag {de(back)}, Urlaub beantragt); Kosten des Aufenthalts trage ich selbst", nights=1, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Der private Anschlussaufenthalt umfasst höchstens 5 Arbeitstage. Beantragt sind nur die Kosten der Dienstreise: Rückfahrt zum Preis des dienstlichen Rückreisetags; den Mehrpreis (5,00 €) und die privaten Nächte trage ich selbst."],
             attach=["Programm.pdf", "Bahnbuchung.pdf", "Preisauskunft.pdf", "Hotel.pdf"])
    antrag = trip_antrag("fiori", T)
    rail = rail_doc("bahn", p["plain"], [(out, "07:02", "Wernstadt Hbf", "11:49", "Hamburg Hbf", "ICE 701", "2. Klasse Sparpreis"), (back, "17:11", "Hamburg Hbf", "21:58", "Wernstadt Hbf", "ICE 706", "2. Klasse Sparpreis")],
                    [("Hinfahrt Do", D("69.90")), ("Rückfahrt Mo (gebucht)", D("64.90"))], "H88-20771", addday(created, 4),
                    foot=[f"Preisauskunft für die Rückfahrt am {wd(bz)}: Sparpreis 59,90 € (siehe Anlage); Mehrpreis Montag: 5,00 €, privat."])
    pa = "\n".join(["Preisauskunft Firmenkundenportal", f"Strecke Hamburg Hbf -> Wernstadt Hbf, {wd(bz)}, ab 13:11, ICE 704, 2. Klasse Sparpreis: 59,90 EUR", f"Strecke Hamburg Hbf -> Wernstadt Hbf, {wd(back)}, ab 17:11, ICE 706, 2. Klasse Sparpreis: 64,90 EUR",
                    "Differenz: 5,00 EUR"])
    hot = "\n".join([lr("Hotel Elbfähre", "Fischmarktstraße 9 · 20359 Hamburg", 100), "", "Buchungsbestätigung  HE-27-2201", "",
                     row(["Buchung", "Zeitraum", "Nächte", "Preis/Nacht", "Rechnung an"], [10, 34, 7, 12, 30], "llrrl"),
                     row(["1 (dienstlich)", f"{wd(out)} – {wd(bz)}", "1", "78,00 €", UW + ", FG " + p["fg"]], [10, 34, 7, 12, 30], "llrrl"),
                     row(["2 (privat)", f"{wd(bz)} – {wd(back)}", "3", "78,00 €", "Gast persönlich (privat)"], [10, 34, 7, 12, 30], "llrrl"), "",
                     "Zimmer jeweils Einzelzimmer inkl. Frühstück. Rechnung zu Buchung 1 an die Universität Wernstadt, zu Buchung 2 an den Gast persönlich.", "Parkplatz Tiefgarage 22,00 € je Nacht nicht gebucht."])
    prog = conf_pages("Symposium „Urbane Dichte und Freiraum“", "Gesellschaft für Stadtforschung e. V.", "Kulturhaus Altona", "Hamburg", [(out, [("13:00", "Eröffnung"), ("14:30", f"Panel „Nachverdichtung im Bestand“ – Vortrag {p['plain']}"), ("19:00", "Empfang (in der Tagungsgebühr enthalten)")]), (bz, [("09:00", "Plenum"), ("12:30", "Ende der Tagung")])],
                      ["Tagungsgebühr 120,00 € (inkl. Empfang und Pausengetränke)."], url="https://stadtforschung.example/symposium-2027", fmt="de")
    begr = ("Antrag sechs Wochen vor der Reise. Der private Anschluss (Sa–Mo) umfasst nur einen Arbeitstag, damit werden die Kosten wie bei einer reinen Dienstreise festgesetzt; beantragt sind die Rückfahrt zum Preis des dienstlichen Rückreisetags (59,90 €), "
            "eine dienstliche Nacht (78,00 €, getrennte Hotelrechnungen) und die Tagungsgebühr. Mehrpreis und private Nächte trägt die Reisende selbst.")
    case(TRIP, cid, [doc("fiori-antrag.pdf", antrag, font="Helvetica"), doc("db-buchung.pdf", rail, font="Helvetica"), doc("preisauskunft.pdf", pa), doc("hotel-doppelbuchung.pdf", hot, font="Helvetica"), doc("programm.pdf", prog, font="Helvetica")],
         begr, "Fiori + DB-Ticket (Rückfahrt Montag) + Preisauskunft + Hotel mit zwei Buchungen + Programm",
         "Privataufenthalt mit nur 1 Arbeitstag, abweichender Rückfahrtpreis (64,90 gebucht / 59,90 beantragt), private Nächte nur im Hotelbrief erwähnt; Parkplatz-Fußnote",
         R_PRIV5, SRC_DRM)


def k08():
    p = staff(8, "Dr.", fb="72")
    cid = "dienstreiseantrag-k08"
    out, back_b, back_a = "2027-10-04", "2027-10-07", "2027-10-16"
    created = weeks_before(out, 12)
    assert workdays("2027-10-08", "2027-10-15") == 6
    costs = [("Bahn zum Flughafen", "Wernstadt – Frankfurt Flughafen und zurück, 2. Klasse", D("64.00")), ("Hinflug", "FRA–OPO, Economy", D("189.00")),
             ("Rückflug (Vergleichstarif)", f"OPO–FRA am {de(back_b)} (dienstlicher Rückreisetag), Economy", D("171.00")),
             ("Unterkunft", "3 Nächte (04.–07.10.) à 72,00 €, ohne Frühstück", D("216.00")), ("Konferenzgebühr", "Registrierung inkl. Empfang", D("360.00"))]
    assert trip_total(costs) == D("1000.00")
    T = dict(person=p, nr="4417330093", created=created, dest="Porto", country="PORTUGAL", abroad=True,
             anlass="ThermoPort 2027 – International Conference on Heat Transfer in Energy Systems", grund="Vortrag „Latent Heat Storage under Cyclic Load“ (angenommen)",
             mode="Flug (Economy)", extra_general=[("Begründung Flug", "Bahn Wernstadt–Porto > 24 h; Preisvergleich liegt bei")],
             start=(out, "05:50"), end=(back_a, "22:30"), biz_from=(addday(out, 1), "09:00"), biz_to=(back_b, "15:00"),
             priv=f"{de('2027-10-08')} bis {de(back_a)}: 6 Arbeitstage, Urlaub beantragt, Kosten trage ich selbst", nights=3, a1=f"beantragt am {de(created)}",
             costs=costs, finance=[("Kostenstelle", f"{p['ks']} / Auftrag {p['auftrag']}")],
             remarks=["Der private Aufenthalt dauert mehr als fünf Arbeitstage. Beantragt werden daher nur die dienstlich veranlassten Kosten: Hinflug, Rückflug zum Vergleichstarif des dienstlichen Rückreisetags, drei Nächte, Konferenzgebühr und die Bahn zum Flughafen. "
                      "Den Mehrpreis des späteren Rückflugs (34,00 €) und die privaten Nächte trage ich selbst."],
             attach=["Annahme.pdf", "Preisvergleich.pdf", "Hotel.pdf", "Registrierung.pdf"], mfmt="de")
    antrag = trip_antrag("fiori", T)
    cmp_ = "\n".join(["Reisebüro am Markt GmbH · Rahmenvertragspartner der Universität Wernstadt", "", f"Preisvergleich Rückflug · {de(addday(created, 4))}", "Anfrage: Porto (OPO) -> Frankfurt (FRA), Economy, 1 Person", "",
                      row(["Variante", "Flug", "Datum / Abflug", "Preis"], [34, 10, 24, 12], "llrr"),
                      row(["A  dienstlicher Rückreisetag", "LH 1129", f"{de(back_b)}, 17:35", money(D('171.00'))], [34, 10, 24, 12], "llrr"),
                      row(["B  nach privatem Aufenthalt (gebucht)", "LH 1131", f"{de(back_a)}, 18:20", money(D('205.00'))], [34, 10, 24, 12], "llrr"),
                      row(["Differenz B – A (privater Mehrpreis)", "", "", money(D('34.00'))], [34, 10, 24, 12], "llrr"), "",
                      "Erstattungsfähig: Variante A (171,00 €). Privat zu tragen: 34,00 €. Hinflug (beide Varianten identisch): FRA -> OPO am " + de(out) + ", 08:40 Uhr, 189,00 €. Bahn Bahn zum Flughafen separat."])
    h = dict(name="Hotel Ribeira Nova", street="Rua das Flores 88", plz="4050-262", city="Porto", tel="+351 22 555 0120", mail="info@ribeiranova.example")
    w = [30, 14, 14, 6, 11]
    hot = "\n".join([lr(h["name"], f"{h['street']}, {h['plz']} {h['city']}", 100), "", f"Booking confirmation HRN-27-1180 · guest {p['plain']}", "",
                     row(["Booking", "Check-in", "Check-out", "Nights", "Rate"], w, "lllrr"),
                     row(["1 business - invoice to Universität Wernstadt", datef(out, 'iso'), datef(back_b, 'iso'), "3", "EUR 72.00"], w, "lllrr"),
                     row(["2 private - invoice to the guest personally", datef(back_b, 'iso'), datef(back_a, 'iso'), "9", "EUR 72.00"], w, "lllrr"), "",
                     f"Invoice address booking 1: {UW}, {p['org_long']}, {UW_ADDR}.", "Room only; breakfast optional EUR 9.00 per person (not booked). Tourist tax not included."])
    regd = reg_invoice("en", ["ThermoPort 2027 Registration", "Rua do Almada 12, 4050-032 Porto, Portugal", "VAT PT 5xx xxx xxx"], [UW, p["org_long"], f"Attn. {p['name']}", UW_ADDR], "Registration invoice", "TP27-0210", addday(created, 7),
                       [("Regular registration incl. welcome reception (Tue evening), coffee breaks and lunches", 1, D("360.00"), D("360.00"))], "No VAT (reverse charge).", ["Excursion on Thursday (EUR 55.00) and gala dinner (EUR 90.00) not booked."], dfmt="us", mfmt="en-eur")
    acc = owa_mail(p["email"].split("@")[0], "ThermoPort 2027 - your abstract has been accepted", "ThermoPort 2027 <submissions@thermoport2027.example>", f"{wd(addday(created, -25))} 10:12", p["plain"],
                   ["Dear Dr. " + p["last"] + ",", "", "your abstract \"Latent Heat Storage under Cyclic Load\" has been accepted for an oral presentation on Wednesday, 6 October 2027, 11:40.", "The conference takes place from 5 to 7 October 2027 in Porto. We cannot offer an honorarium.", "", "Best regards,", "The Programme Committee"])
    begr = (f"Antrag zwölf Wochen vor Abflug mit A1. Der private Anschluss dauert 6 Arbeitstage (mehr als fünf), deshalb sind ausschließlich die dienstlichen Kosten beantragt: Hinflug, Rückflug zum Vergleichstarif (171,00 €), drei Nächte zu 72,00 €, "
            "Gebühr und Bahn zum Flughafen (zusammen 1.000,00 €); Mehrpreis 34,00 € und private Nächte trägt der Reisende, die Hotelrechnungen sind getrennt, die dienstliche lautet auf die Universität.")
    case(TRIP, cid, [doc("fiori-reiseantrag.pdf", antrag, font="Helvetica"), doc("preisvergleich-rueckflug.pdf", cmp_, font="Helvetica"), doc("hotel-booking.pdf", hot, font="Helvetica"),
                     doc("registration.pdf", regd, font="Helvetica"), doc("acceptance.pdf", acc, font="Helvetica")], begr,
         "Fiori + Reisebüro-Preisvergleich + zweigeteilte Hotelbuchung (EN) + Konferenzrechnung (US-Datum) + Annahme-Mail",
         "Privataufenthalt von 6 Arbeitstagen, nur dienstliche Kosten beantragt, Mehrpreis 34 € ausgewiesen; Flug mit Begründung",
         R_PRIVMORE, SRC_DRM, "high")


def k09():
    p = staff(9, "Dr.", fb="74")
    cid = "dienstreiseantrag-k09"
    out, back = "2027-05-11", "2027-05-13"
    created = weeks_before(out, 4)
    costs = [("Dienstfahrzeug (Fuhrpark)", "Kraftstoff über Tankkarte, Schätzung", D("58.00")), ("Übernachtung", "2 Nächte à 68,00 €, Gästehaus mit Frühstück", D("136.00"))]
    T = dict(person=p, nr="", created=created, dest="Clausthal-Zellerfeld (Harz)", country="DEUTSCHLAND", abroad=False,
             anlass="Messkampagne Hangstabilität, Gemeinde Altenau", grund="Geotechnische Messungen mit Inklinometer an drei Standorten, Termin mit dem Bauamt", mode="Dienstfahrzeug der Universität (Fahrbereitschaft), 2 Personen",
             start=(out, "06:00"), end=(back, "18:30"), biz_from=(out, "10:00"), biz_to=(back, "15:00"), priv="keiner", nights=2, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Das Dienstfahrzeug wird von der Fahrbereitschaft gestellt (Reservierung anbei). Mitreisende Person: wissenschaftlicher Mitarbeiter, eigener Antrag."],
             attach=["Terminbestätigung Bauamt", "Fahrzeugreservierung", "Gästehaus"], caps=False)
    antrag = trip_antrag("paper", T, glyph="slash")
    res = owa_mail("fahrbereitschaft", f"Reservierung Dienstfahrzeug {wd(out)} bis {wd(back)}", "Fahrbereitschaft <fahrbereitschaft@uni-wernstadt.de>", f"{wd(addday(created, 2))} 09:48", p["name"],
                   ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"für den Zeitraum {de(out)} bis {de(back)} ist ein Kombi (Kennzeichen WE-UW 41) für Sie reserviert.", "Abholung ab 05:30 Uhr am Fuhrpark, Rückgabe bis 19:00 Uhr.",
                    "Die Tankkarte liegt im Fahrzeug; Kraftstoffkosten werden dem Fachgebiet belastet. Mautpflichtige Strecken: keine.", "Eine Selbstbeteiligung bei Schäden trägt die Kostenstelle des ausleihenden Bereichs.", "", "Freundliche Grüße", "Fahrbereitschaft"])
    bau = owa_mail(p["email"].split("@")[0], "AW: Messtermine Hangstabilität", "Bauamt Altenau <bauamt@altenau-gemeinde.example>", f"{wd(addday(created, -9))} 16:02", p["name"],
                   ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"wir bestätigen Ihren Messtermin vom {de(out)} (10:00 Uhr) bis {de(back)} (15:00 Uhr). Ansprechpartner vor Ort: Herr Marquardt.",
                    "Das Gelände ist freigegeben. Eine Aufwandsentschädigung wird nicht gezahlt.", "", "Mit freundlichen Grüßen", "Bauamt"])
    hot = hotel_doc("letter", dict(name="Gästehaus Sonnenberg", street="Bergstraße 6", plz="38707", city="Altenau", tel="05328 5530", mail="info@sonnenberg-altenau.example"), p["name"], p["org_long"], 2, D("68.00"), out, back, "GS-1141", addday(created, 3),
                    foot=["Kostenfreie Stornierung bis 7 Tage vor Anreise. Wanderkarte 4,50 € (nicht bestellt)."], datefmt="de")
    begr = ("Antrag vier Wochen vor der Messkampagne (Papierformular, eingescannt). Das Dienstfahrzeug der Fahrbereitschaft ist reserviert, die Kosten sind der Kraftstoff (58,00 €) und zwei Nächte zu 68,00 € mit Frühstück im Gästehaus (Rechnung auf die Universität). "
            "Die Terminbestätigung des Bauamts belegt Anlass und Dauer; eine Entschädigung wird nicht gezahlt.")
    case(TRIP, cid, [doc("IMG_2231.pdf", antrag, jitter=1.1, producer="Canon iR-ADV Scan"), doc("scan_0002.pdf", res, font="Helvetica"), doc("bestaetigung-bauamt.pdf", bau, font="Helvetica"), doc("gaestehaus.pdf", hot, font="Times-Roman")],
         begr, "Gescanntes Papierformular (Zeilenversatz, Kreuz „[/]“) + Reservierung der Fahrbereitschaft + Mailbestätigung + Gästehausbrief; Dateinamen IMG_2231 / scan_0002",
         "Dienstfahrzeug statt Privat-Pkw, ohne Wegstreckenentschädigung; „Aufwandsentschädigung wird nicht gezahlt“; Wanderkarte-Fußnote", R_FAHRZEUG + " " + R_HOTEL, SRC_DRM)


def k10():
    p = staff(10, "Dr.", fb="76")
    cid = "dienstreiseantrag-k10"
    out, back = "2027-09-22", "2027-09-25"
    created = weeks_before(out, 10)
    costs = [("Bahn Wernstadt – Prag und zurück", "2. Klasse, Sparpreis", D("122.00")), ("Unterkunft", "3 Nächte à 70,00 €, ohne Frühstück", D("210.00")), ("Konferenzgebühr", "Registrierung", D("410.00")),
             ("abzüglich Reisezuschuss Dritter", "Stiftung Nordlicht (Zusage anbei), voll abgezogen", D("-300.00"))]
    T = dict(person=p, nr="4417334471", created=created, dest="Prag", country="TSCHECHISCHE REPUBLIK", abroad=True,
             anlass="BioAnalytics Central Europe 2027", grund="Posterpräsentation „Trace Metal Speciation in Soil Extracts“ (Poster angenommen)", mode="Bahn, 2. Klasse",
             start=(out, "05:45"), end=(back, "21:50"), biz_from=(addday(out, 1), "09:00"), biz_to=(addday(back, -1), "16:30"), priv="keiner", nights=3, a1=f"beantragt am {de(created)} (Vorlauf > 8 Wochen)",
             costs=costs, finance=[("Leistungen von dritter Seite", "Reisezuschuss der Stiftung Nordlicht, pauschal 300,00 € (Zusage anbei), auf die Kosten angerechnet"), ("Kostenstelle", f"{p['ks']} (Landesmittel, nur Restbetrag 442,00 €)")],
             remarks=["Beantragt wird nur der Betrag, der nicht durch den Zuschuss der Stiftung gedeckt ist (742,00 € Gesamtkosten abzüglich 300,00 €). Eine Doppelfinanzierung findet nicht statt."],
             attach=["Zusage_Stiftung.pdf", "Posterannahme.pdf", "Bahn.pdf", "Hotel.pdf", "Registrierung.pdf"])
    assert trip_total(costs) == D("442.00")
    antrag = trip_antrag("fiori", T)
    rail = rail_doc("practice", p["plain"], [(out, "06:02", "Wernstadt Hbf", "15:20", "Praha hl.n.", "EC 175", "2. Klasse"), (back, "09:40", "Praha hl.n.", "18:57", "Wernstadt Hbf", "EC 174", "2. Klasse")],
                    [("Hinfahrt", D("58.00")), ("Rückfahrt", D("64.00"))], "T27-5518", addday(created, 5), foot=["Reservierung 5,00 € je Strecke (nicht gebucht).", "Zuschlag 1. Klasse 31,00 € je Strecke (nicht gebucht)."])
    hot = hotel_doc("portal", dict(name="Hotel U Mostu", street="Narodni 18", plz="110 00", city="Praha 1", tel="+420 2 5555 0140", mail="booking@umostu-praha.example"), p["plain"], p["org_long"], 3, D("70.00"), out, back, "SB-5514-0021", addday(created, 6), breakfast=False,
                    foot=["City tax CZK 50 per person and night is paid on site."], datefmt="de")
    regd = reg_invoice("en", ["BioAnalytics Central Europe 2027", "Technická 14, 160 00 Praha 6, Czech Republic", "VAT CZ xxxxxxxx"], [UW, p["org_long"], f"Attn. {p['name']}", UW_ADDR], "Invoice", "BACE27-118", addday(created, 8),
                       [("Registration fee, poster presenter (includes coffee breaks, lunch on both conference days and the welcome reception)", 1, D("410.00"), D("410.00"))], "VAT 0 % - reverse charge. Recipient is the University.", ["Payment by bank transfer."], dfmt="slash", mfmt="eurplain")
    gr = letter(["Stiftung Nordlicht", "Reiseförderung für Nachwuchsforschende"], [p["name"], f"c/o {UW}", UW_ADDR], f"Hamburg, {datef(addday(created, -12), 'long')}", "Zusage Reisezuschuss BAC-2027",
                ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", "wir bewilligen Ihnen für die Reise nach Prag (22.–25.09.2027) einen pauschalen Reisezuschuss von 300,00 €. Der Zuschuss ist auf Reisekosten anzurechnen; eine Doppelerstattung durch die Hochschule ist nicht zulässig.",
                 "Der Höchstbetrag für Langstreckenreisen beträgt 500,00 € (gilt für diese Reise nicht)."], ["Stiftung Nordlicht"])
    pos = owa_mail(p["email"].split("@")[0], "BACE 2027 - poster accepted (ID 52)", "BACE 2027 Committee <poster@bace2027.example>", f"{wd(addday(created, -30))} 11:20", p["plain"],
                   ["Dear Dr. " + p["last"] + ",", "", "your poster \"Trace Metal Speciation in Soil Extracts\" has been accepted for the poster session on Thursday, 23 September 2027 (14:00-16:00).", "Presenting authors must register by 15 August 2027.", "", "Best wishes,", "BACE 2027"])
    begr = ("Antrag zehn Wochen vor der Reise, A1 beantragt. Der Zuschuss der Stiftung (300,00 €) ist in der Finanzierung als Leistung von dritter Seite angegeben und von den Gesamtkosten (742,00 €) abgezogen; beantragt sind 442,00 €. "
            "Hotel 70,00 € je Nacht ohne Frühstück auf die Universität; die Registrierungsgebühr enthält den Empfang. Keine Doppelfinanzierung.")
    case(TRIP, cid, [doc("reiseantrag.pdf", antrag, font="Helvetica"), doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("invoice-bace.pdf", regd, font="Helvetica"),
                     doc("zusage-stiftung.pdf", gr, font="Times-Roman"), doc("poster-accepted.pdf", pos, font="Helvetica")], begr,
         "Fiori mit Abzugszeile + Bahn (Stil der Organisatoren) + Hotelportal + Rechnung + Stiftungsbrief + Mail", "Dritte Seite (Stiftungszuschuss 300 €) ordnungsgemäß angegeben und abgezogen; Höchstbetrag 500 € im Zusagebrief nicht relevant; Empfang in Gebühr",
         R_THIRD, SRC_DRM, "medium")


def k11():
    p = staff(11, "", fb="78")
    cid = "dienstreiseantrag-k11"
    out, back = "2027-11-09", "2027-11-10"
    created = weeks_before(out, 5)
    costs = [("Bahn", "Wernstadt – Marburg und zurück, 2. Klasse", D("88.60")), ("Übernachtung", "1 Nacht à 72,00 €, Frühstück inkl.", D("72.00"))]
    T = dict(person=p, nr="WEB-27-031277", created=created, dest="Marburg", country="Deutschland", abroad=False, anlass="Soziologisches Kolloquium Marburg, Sitzung „Arbeit im Wandel“",
             grund="Eingeladener Vortrag „Plattformarbeit und Mitbestimmung“; Austausch mit dem Fachbereich zum gemeinsamen Drittmittelantrag", mode="Bahn, 2. Klasse",
             start=(out, "07:20"), end=(back, "20:15"), biz_from=(out, "16:00"), biz_to=(back, "12:00"), priv="keiner", nights=1, costs=costs, mfmt="eur",
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Für den Vortrag wird kein Honorar gezahlt (siehe Einladung). Die Reisekosten werden von der einladenden Stelle nicht übernommen."],
             attach=["Einladung.pdf", "Bahn.pdf", "Hotel.pdf"], time="14:03")
    antrag = trip_antrag("web", T, glyph="paren", datefmt="short")
    inv = owa_mail(p["email"].split("@")[0], "Einladung zum Kolloquium am 9. November", "Soziologisches Kolloquium <kolloquium@soz-marburg.example>", f"{wd(addday(created, -40))} 09:05", p["name"],
                   ["Liebe Frau/Lieber Herr " + p["last"] + ",", "", "wir würden uns freuen, wenn Sie am Dienstag, 9. November 2027, um 16:00 Uhr in unserem Kolloquium über Plattformarbeit und Mitbestimmung vortragen.", "",
                    "Leider können wir kein Honorar zahlen und auch keine Reise- oder Übernachtungskosten übernehmen. Die Kosten wird Ihre Hochschule tragen müssen.", "Im Anschluss ist ein gemeinsames Abendessen im Kreis des Fachbereichs geplant (Selbstzahler).", "", "Herzliche Grüße", "Das Kolloquiumsteam"])
    rail = rail_doc("mail", p["plain"], [(out, "07:25", "Wernstadt Hbf", "10:58", "Marburg(Lahn)", "IC 2377", "2. Klasse"), (back, "14:47", "Marburg(Lahn)", "18:15", "Wernstadt Hbf", "IC 2370", "2. Klasse")],
                    [("Hinfahrt Sparpreis", D("41.80")), ("Rückfahrt Sparpreis", D("46.80"))], "K-4410-77", addday(created, 3), mfmt="eur")
    hot = hotel_doc("mail", dict(name="Hotel Zum Anker", street="Ketzerbach 22", plz="35037", city="Marburg", tel="06421 5550", mail="reservierung@anker-marburg.example"), p["plain"], p["org_long"], 1, D("72.00"), out, back, "ZA-9917", addday(created, 4), mfmt="eur",
                    foot=["Gästekarte für den Nahverkehr kostenfrei inbegriffen."])
    begr = ("Online-Antrag fünf Wochen vor der Reise. Die Einladung zum Kolloquium belegt Vortrag, Ort und Dauer; sie stellt ausdrücklich klar, dass kein Honorar gezahlt wird (keine Nebentätigkeit) und die Kosten bei der Hochschule liegen. "
            "Bahn 88,60 € und eine Nacht zu 72,00 € unter der Höchstgrenze, Rechnung auf die Universität.")
    case(TRIP, cid, [doc("antrag-online.pdf", antrag, font="Helvetica", producer="Mozilla Firefox"), doc("einladung-kolloquium.pdf", inv, font="Helvetica"), doc("anlage-3.pdf", rail, font="Helvetica"), doc("anlage-4.pdf", hot, font="Helvetica")],
         begr, "Online-Formular mit „(x)“ und Daten „9.11.2027“ + Einladungsmail + Bahn-/Hotelmails (EUR-Format)", "Negationen: „kein Honorar“, „keine Reise- oder Übernachtungskosten übernehmen“; privates Abendessen als Selbstzahler erwähnt, nicht beantragt",
         R_HONORAR + " " + R_ATTACH, SRC_DRM)


def k12():
    cid = "dienstreiseantrag-k12"
    p = staff(12, "Prof. Dr.", fb="71")
    q = staff(112, "", fb="71")
    day = "2027-07-07"
    created = addday(day, -37)
    bus = D("780.00")
    nb, vb = vat_split(bus, 7)
    studs = [(FIRST[(i * 5 + 2) % len(FIRST)], LAST[(i * 7 + 9) % len(LAST)]) for i in range(28)]
    TL = ["Teilnehmerliste Exkursion Umspannwerk und Windpark Nordheide", f"Datum: {wdl(day)} · Leitung: {p['name']} · Begleitperson: {q['plain']}", "", row(["Nr.", "Name", "Matr.-Nr.", "Studiengang"], [4, 34, 10, 26], "lllll")]
    for i, (f_, l_) in enumerate(studs, 1):
        TL.append(row([str(i), f"{l_}, {f_}", str(5200000 + i * 371 % 90000), "B.Sc. Elektrotechnik"], [4, 34, 10, 26], "lllll"))
    TL += ["", f"Summe: {len(studs)} Studierende, 1 Exkursionsleitung, 1 Begleitperson (Verhältnis 1 : 14)"]
    ant = "\n".join([lr("Universität Wernstadt · Abteilung Personal und Organisation", "Antrag auf Genehmigung einer Exkursion", 100), "",
                     f"Eingang Dekanat FB 71: {de(addday(created, 1))}     Weiterleitung an Personal und Organisation: {de(addday(created, 3))}", "",
                     kvw([("Art der Exkursion", "[X] Studienexkursion   [ ] Pflichtexkursion"), ("Ziel", "Umspannwerk Nordheide und Windpark Nordheide (Tagesexkursion)"), ("Datum", wdl(day)),
                          ("Lehrveranstaltung", "Vorlesung „Elektrische Energiesysteme“, WiSe/SoSe 2027"), ("Exkursionsleitung", p["name"] + " (Professor, Mitglied der Universität)"),
                          ("Begleitperson", q["plain"] + " (wissenschaftlicher Mitarbeiter, führt das begleitende Seminar durch)"), ("Teilnehmende Studierende", "28 (Liste anbei), alle an der Universität Wernstadt immatrikuliert"),
                          ("Verhältnis", "Leitung plus eine Begleitperson für 28 Studierende (Regel: eine Begleitperson je 15 Studierende)"), ("Kosten", f"Busanmietung {money(bus)} (Angebot anbei), direkt von der Universität zu zahlen; keine weiteren Kosten"),
                          ("Abschlag", "nicht beantragt"), ("Kostenstelle", f"{p['ks']}")], k=28, width=66, indent=0), "",
                     "Anlagen: Teilnehmerliste, Angebot Busunternehmen, Einladung Betreiber, Reiseanträge (Fiori) der beiden Beschäftigten", "",
                     f"Wernstadt, {de(created)}      Unterschrift Exkursionsleitung: {p['name']}      Dekanat: ____________"])
    angebot = "\n".join([lr("Reisebus-Service Hackmann KG", "Mühlenkamp 12 · 21335 Lüneburg", 100), "", UW, f"FB 71 · FG {p['fg']}", f"z. Hd. {p['name']}", "", lr(f"Angebot Nr. RB-27-0412", f"Datum: {de(addday(created, -10))}", 100), "",
                         f"Tagesfahrt {de(day)}: Wernstadt – Umspannwerk Nordheide – Windpark – Wernstadt, ca. 310 km, Reisebus 49 Sitze, inkl. Fahrer und Wartezeit bis 8 Stunden",
                         row(["Position", "Nettobetrag", "USt 7 %", "Brutto"], [50, 12, 10, 12], "lrrr"), row(["Gesamtleistung Personenbeförderung", money(nb, 'bare'), money(vb, 'bare'), money(bus, 'bare')], [50, 12, 10, 12], "lrrr"), "",
                         "Angebotssumme brutto: " + money(bus, "eur"), "Das Angebot ist bis zum " + de(addday(day, -14)) + " gültig. Nicht enthalten: Parkgebühren am Zielort (falls anfallend)."])
    betr = letter(["Netzbetrieb Nordheide GmbH", "Besucherdienst"], [UW, f"FG {p['fg']}", f"z. Hd. {p['name']}"], f"Nordheide, {datef(addday(created, -20), 'long')}", "Betriebsbesichtigung am " + datef(day, "long"),
                  ["Sehr geehrte Damen und Herren,", "", f"gern empfangen wir 30 Personen Ihrer Gruppe am {wdl(day)} von 10:00 bis 15:00 Uhr im Umspannwerk und im Windpark. Die Führung ist kostenfrei.", "Festes Schuhwerk und Warnwesten werden gestellt."], ["Besucherdienst"])
    docs = [doc("exkursionsantrag.pdf", ant, font="Helvetica"), doc("teilnehmerliste.pdf", "\n".join(TL)), doc("angebot-bus.pdf", angebot, font="Helvetica"), doc("einladung-betreiber.pdf", betr, font="Times-Roman")]
    for tag, who in (("leitung", p), ("begleitung", q)):
        costs = [("Busanmietung (Direktzahlung der Universität)", "siehe Exkursionsantrag, keine Auslagen der Person", D("0.00"))]
        T = dict(person=who, nr="44173" + ("41002" if tag == "leitung" else "41003"), created=addday(created, 1), dest="Nordheide", country="DEUTSCHLAND", abroad=False, anlass="Studienexkursion Umspannwerk und Windpark Nordheide",
                 grund="Exkursionsleitung" if tag == "leitung" else "Begleitperson der Exkursion", mode="Reisebus (Charter der Universität)", start=(day, "07:30"), end=(day, "17:30"), biz_from=(day, "10:00"), biz_to=(day, "15:00"),
                 priv="keiner", nights=0, costs=costs, finance=[("Kostenstelle", p["ks"])], remarks=["Reiseantrag zur genehmigten Exkursion (Antrag vom " + de(created) + ")."], attach=["Exkursionsantrag", "Teilnehmerliste"])
        docs.append(doc(f"fiori-reiseantrag-{tag}.pdf", trip_antrag("fiori", T), font="Helvetica"))
    begr = (f"Der Exkursionsantrag ging {(dt(day) - dt(created)).days} Tage vor Beginn über das Dekanat ein (mindestens 14 Tage verlangt). 28 Studierende werden von Leitung und einer Begleitperson betreut (mindestens eine Begleitperson je 15). "
            "Der Bus kostet 780,00 € brutto (unter 1.000 €), die Betreiber-Einladung belegt Ort und Dauer; beide Beschäftigten haben ein Fiori-Reiseantrag gestellt.")
    case(TRIP, cid, docs, begr, "Exkursionsantrag (Formular) + Teilnehmerliste + Busangebot + Betreiberbrief + zwei Fiori-Reiseanträge", "Exkursion: 37 Tage vorab, 28 Studierende, Leitung + 1 Begleitperson; Fiori-Anträge mit 0,00 € Auslagen; Teilnehmerliste mit Matrikelnummern",
         R_EXK, SRC_DRM, "medium")


def k13():
    p = staff(13, "Dr.", fb="75")
    cid = "dienstreiseantrag-k13"
    out, back = "2027-03-23", "2027-03-25"
    created = weeks_before(out, 5)
    costs = [("Bahn", "Wernstadt – München und zurück, 2. Klasse Sparpreis", D("148.60")), ("Übernachtung", "2 Nächte à 79,00 €, inkl. Frühstück", D("158.00")), ("Teilnahmegebühr", "inkl. Tagungspauschale (Verpflegung)", D("350.00"))]
    total = trip_total(costs)
    abs_ = r2(total * D("0.8"))
    assert total == D("656.60") and abs_ == D("525.28")
    assist = "Birgit Zielinski-Berg (Sekretariat, Reiseassistenz; Einverständnis liegt vor)"
    T = dict(person=p, nr="4417339920", created=created, dest="München", country="DEUTSCHLAND", abroad=False, anlass="Fachtagung „Wirtschaftsinformatik in der Lehre 2027“", grund="Vortrag im Workshop „Curriculumsentwicklung“ (Annahmemail anbei)", mode="Bahn, 2. Klasse",
             start=(out, "06:15"), end=(back, "21:40"), biz_from=(out, "13:00"), biz_to=(back, "14:00"), priv="keiner", nights=2, costs=costs, assist=assist,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)"), ("Abschlag beantragt", f"ja: {eur(abs_)} € (80 % von {eur(total)} €)")], remarks=["Der Abschlag liegt über 150 € und wird mit der Reisekostenabrechnung innerhalb von vier Wochen nach der Reise abgerechnet."],
             attach=["Annahme.pdf", "Rechnung_Tagung.pdf", "Bahn.pdf", "Hotel.pdf", "Einverstaendnis_Reiseassistenz.pdf"])
    antrag = trip_antrag("fiori", T, datefmt="long")
    ein = "\n".join(["Einverständniserklärung Reiseassistenz (Fiori)", "", f"Ich, {p['name']} (Pers.-Nr. {p['persnr']}), bin damit einverstanden, dass {assist.split(' (')[0]} meine Dienstreiseanträge und -abrechnungen im Fiori-System in meinem Namen erfasst.",
                     "Der Fiori-Benutzerantrag für die Reiseassistenz wurde am " + de(addday(created, -40)) + " gestellt und bewilligt.", "", f"Wernstadt, {de(created)}        {p['name']}"])
    rng = reg_invoice("de", ["Gesellschaft für Wirtschaftsinformatik e. V.", "Tagungsbüro, Lenbachplatz 2, 80333 München", "USt-IdNr. DE 2xx xxx xxx"], [UW, p["org_long"], f"z. Hd. {p['name']}", UW_ADDR], "Rechnung Tagungsteilnahme", "WIL27-0415", addday(created, 6),
                      [("Teilnahmegebühr, 2 Tage (Wissenschaft), inkl. Tagungspauschale: Mittagessen, Kaffeepausen, Abendempfang", 1, vat_split(D("350.00"), 19)[0], D("350.00"))], f"Im Rechnungsbetrag sind 19 % USt ({money(vat_split(D('350.00'), 19)[1])}) enthalten.", ["Zahlbar innerhalb von 14 Tagen auf IBAN " + iban(random.Random(13)) + "."], dfmt="de", mfmt="de")
    rail = rail_doc("practice", p["plain"], [(out, "06:30", "Wernstadt Hbf", "11:41", "München Hbf", "ICE 595", "2. Klasse Sparpreis"), (back, "15:20", "München Hbf", "20:31", "Wernstadt Hbf", "ICE 592", "2. Klasse Sparpreis")],
                    [("Hinfahrt", D("69.80")), ("Rückfahrt", D("78.80"))], "M-27-80455", addday(created, 5))
    hot = hotel_doc("table", dict(name="Hotel Isarblick", street="Rosenheimer Straße 44", plz="81669", city="München", tel="089 5550 410", mail="reservierung@isarblick.example"), p["name"], p["org_long"], 2, D("79.00"), out, back, "HI-27-1920", addday(created, 6))
    acc = owa_mail(p["email"].split("@")[0], "WIL 2027 – Ihr Workshopbeitrag ist angenommen", "WIL 2027 <programm@wil2027.example>", f"{wd(addday(created, -22))} 15:30", p["name"],
                   ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"Ihr Beitrag zum Workshop „Curriculumsentwicklung“ wurde angenommen. Der Workshop findet am {wde_long(addday(out, 1))} statt; die Tagung dauert vom {de(out)} bis {de(back)}.", "Ein Honorar kann nicht gezahlt werden.", "", "Mit freundlichen Grüßen", "Das Programmkomitee"])
    begr = (f"Antrag fünf Wochen vor der Reise, von der Reiseassistenz erfasst (Einverständniserklärung liegt bei). Der beantragte Abschlag von {eur(abs_)} € ist genau 80 % der erwarteten Kosten ({eur(total)} €) und liegt über 150 €. "
            "Tagung (mit Tagungspauschale), Bahn und zwei Nächte zu 79,00 € sind belegt, das Hotel adressiert die Universität.")
    case(TRIP, cid, [doc("fiori-reiseantrag-assistenz.pdf", antrag, font="Helvetica"), doc("einverstaendnis-reiseassistenz.pdf", ein, font="Times-Roman"), doc("rechnung-tagung.pdf", rng, font="Helvetica"),
                     doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("annahme.pdf", acc, font="Helvetica")], begr, "Fiori mit Reiseassistenz + Einverständniserklärung + Tagungsrechnung (19 % USt) + Hotel/Bahn (Stil der Organisatoren)",
         "Abschlag 80 % korrekt berechnet (525,28 von 656,60); „Honorar kann nicht gezahlt werden“; Tagungspauschale", R_ABSCHLAG + " " + R_ASSIST + " " + R_TAGUNG, SRC_DRM, "high")


def k14():
    p = staff(14, "Dr.", fb="71")
    cid = "dienstreiseantrag-k14"
    out, back = "2027-06-22", "2027-06-25"
    created = weeks_before(out, 10)
    costs = [("Bahn Wernstadt – Breslau und zurück", "2. Klasse, Sparpreis", D("165.00")), ("Unterkunft", "3 Nächte à 70,00 € (PLN 315,00 je Nacht, Planungskurs 4,50)", D("210.00")), ("Konferenzgebühr", "Registrierung, ohne Galadinner", D("250.00"))]
    T = dict(person=p, nr="WEB-27-040115", created=created, dest="Breslau (Wroclaw)", country="Polen", abroad=True, anlass="WroSec 2027 – Workshop on Embedded Security", grund="Vortrag „Side-Channel Leakage of Low-Power Radios“ (Beitrag angenommen)",
             mode="Bahn, 2. Klasse", start=(out, "05:55"), end=(back, "22:15"), biz_from=(addday(out, 1), "09:00"), biz_to=(addday(back, -1), "17:00"), priv="keiner", nights=3, a1=f"beantragt am {de(created)} (Vorlauf mehr als 8 Wochen)", costs=costs, mfmt="de",
             finance=[("Kostenstelle", f"{p['ks']} / Auftrag {p['auftrag']}")], remarks=["Die Hotelrechnung lautet auf PLN; der Planungskurs 4,50 ergibt 70,00 € je Nacht, unter der Höchstgrenze des Auslandsübernachtungsgeldes."],
             attach=["Annahme.pdf", "Bahn.pdf", "Hotel.pdf", "Anmeldung.pdf"], time="10:27")
    antrag = trip_antrag("web", T, glyph="box", datefmt="de")
    rail = rail_doc("en", p["plain"], [(out, "06:12", "Wernstadt Hbf", "17:35", "Wroclaw Glowny", "ICE 1555 / EC 341", "2nd class"), (back, "08:20", "Wroclaw Glowny", "19:40", "Wernstadt Hbf", "EC 340 / ICE 1558", "2nd class")],
                    [("Outbound saver fare", D("79.00")), ("Return saver fare", D("86.00"))], "RC-5188-PL", addday(created, 4), foot=["Seat reservation PLN 13.00 per leg is included. Flexible fare: EUR 260.00 (not booked)."])
    hot = "\n".join([lr("Hotel Odra Centrum", "ul. Piaskowa 21 · 50-001 Wroclaw", 100), "", f"Potwierdzenie rezerwacji / Booking confirmation OC-27-7719 · {datef(addday(created, 5), 'us')}", "",
                     kvw([("Guest", p["plain"]), ("Arrival / Departure", f"{datef(out, 'us')} / {datef(back, 'us')}"), ("Nights", "3"), ("Room", "Single room, breakfast not included"), ("Rate per night", "PLN 315.00"),
                          ("Total", "PLN 945.00 (approx. EUR 210.00 at 4.50)"), ("Invoice to", f"{UW}, FG {p['fg']}, {UW_ADDR}"), ("Payment", "on departure by the guest, invoice in the name of the university")], k=22, width=70, indent=0), "",
                     "Breakfast PLN 45.00 per person (optional, not booked). City tax PLN 3.00 per night is not included."])
    regd = reg_invoice("en", ["WroSec 2027 Organising Committee", "Politechnika Wroclawska (host), ul. Smoluchowskiego 11, 50-370 Wroclaw", "VAT PL xxxxxxxxxx"], [UW, p["org_long"], f"Attn. {p['name']}", UW_ADDR], "Invoice / Registration", "WS27-0066", addday(created, 6),
                       [("Registration, one author: three conference days with lunches, coffee breaks and the welcome reception", 1, D("250.00"), D("250.00"))], "VAT 0 % (reverse charge).", ["Gala dinner on Thursday (EUR 90.00) is optional and has not been booked."], dfmt="us", mfmt="en-eur")
    acc = owa_mail(p["email"].split("@")[0], "WroSec 2027: decision on submission 31", "WroSec 2027 PC <pc@wrosec2027.example>", f"{wd(addday(created, -30))} 18:44", p["plain"],
                   ["Dear Dr. " + p["last"] + ",", "", "we are happy to accept your paper \"Side-Channel Leakage of Low-Power Radios\" as a full talk (25 minutes) at WroSec 2027, Wroclaw, 23-24 June 2027.", "No honorarium or travel support is provided.", "", "Kind regards,", "WroSec PC chairs"])
    begr = ("Antrag zehn Wochen vor Reisebeginn, Auslandsfeld angekreuzt, A1 beantragt. Hotel PLN 315,00 je Nacht = 70,00 € beim Planungskurs, auf die Universität ausgestellt; Gebühr ohne das optionale Galadinner; Bahn 2. Klasse. Die Annahme belegt den Vortrag. Summe 625,00 €.")
    case(TRIP, cid, [doc("online-antrag.pdf", antrag, font="Helvetica", producer="Chromium"), doc("rail.pdf", rail, font="Helvetica"), doc("hotel-wroclaw.pdf", hot, font="Helvetica"), doc("invoice.pdf", regd, font="Helvetica"), doc("accept.pdf", acc, font="Helvetica")],
         begr, "Web-Formular mit „[■]“ im Auslandsfeld + englische Dokumente mit PLN-Preisen und US-Datum", "Hotelpreis in PLN mit Euro-Umrechnung (4,50); optionales Galadinner und Frühstück nicht gebucht; Auslandsfeld mit „[■]“-Glyphe",
         R_A1 + " " + R_HOTEL_ABROAD, SRC_DRM, "high")


def k15():
    p = staff(15, "Dr.", fb="72")
    cid = "dienstreiseantrag-k15"
    out, back = "2027-05-25", "2027-05-26"
    created = weeks_before(out, 4)
    costs = [("Bahn", "Wernstadt – Stuttgart und zurück, 2. Klasse Sparpreis", D("134.80")), ("Übernachtung", "1 Nacht à 78,50 €, inkl. Frühstück", D("78.50")), ("Taxi", "Hauptbahnhof Wernstadt – Wohnung am 26.05., Ankunft 23:48 Uhr", D("28.00"))]
    T = dict(person=p, nr="4417342208", created=created, dest="Stuttgart", country="DEUTSCHLAND", abroad=False, anlass="Sitzung des Beirats Transferzentrum Fertigung", grund="Mitglied des Beirats; Vorstellung der Projektergebnisse (Einladung anbei)", mode="Bahn, 2. Klasse",
             start=(out, "06:10"), end=(addday(back, 1), "00:05"), biz_from=(out, "13:00"), biz_to=(back, "17:30"), priv="keiner", nights=1, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Das Taxi ist dienstlich notwendig und wird begründet: Die Sitzung endet erst um 17:30 Uhr, der letzte Zug erreicht Wernstadt um 23:48 Uhr; danach verkehrt kein Bus (Nachtverkehr erst ab 05:00 Uhr), Fußweg 6 km."],
             attach=["Einladung_Beirat.pdf", "Bahn.pdf", "Hotel.pdf"])
    antrag = trip_antrag("fiori", T)
    rail = rail_doc("bahn", p["plain"], [(out, "06:44", "Wernstadt Hbf", "11:32", "Stuttgart Hbf", "ICE 811", "2. Klasse Sparpreis"), (back, "18:12", "Stuttgart Hbf", "23:48", "Wernstadt Hbf", "ICE 814 / RE 4", "2. Klasse Sparpreis")],
                    [("Hinfahrt", D("64.90")), ("Rückfahrt", D("69.90"))], "S27-0912", addday(created, 3), foot=["Hinweis: Für diese Verbindung ist keine Fahrtunterbrechung möglich. Letzte Verbindung des Tages von Stuttgart nach Wernstadt."])
    hot = hotel_doc("letter", dict(name="Hotel Rosengarten", street="Königstraße 31", plz="70173", city="Stuttgart", tel="0711 5550 12", mail="rezeption@rosengarten-s.example"), p["name"], p["org_long"], 1, D("78.50"), out, back, "RG-27-4412", addday(created, 3), datefmt="long")
    ein = letter(["Transferzentrum Fertigung Stuttgart", "Geschäftsstelle des Beirats"], [p["name"], UW, f"FG {p['fg']}"], f"Stuttgart, {datef(addday(out, -50), 'long')}", f"Einladung zur Beiratssitzung am {datef(out, 'long')}",
                 ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"die nächste Sitzung des Beirats findet am {wdl(out)}, 13:00 Uhr, bis {wdl(back)}, 17:30 Uhr, im Transferzentrum Stuttgart statt.", "Die Mitarbeit im Beirat ist ehrenamtlich; es werden weder Sitzungsgelder noch Honorare gezahlt, Reisekosten trägt die entsendende Einrichtung."], ["Geschäftsstelle"])
    begr = (f"Antrag vier Wochen vor der Sitzung. Das Taxi (28,00 €) ist ausdrücklich begründet (letzte Ankunft 23:48 Uhr, kein Nahverkehr mehr), Bahn und eine Nacht zu 78,50 € liegen im Rahmen, die Einladung belegt Anlass und Dauer; Beiratsarbeit ohne Sitzungsgeld.")
    case(TRIP, cid, [doc("reiseantrag.pdf", antrag, font="Helvetica"), doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Times-Roman"), doc("einladung.pdf", ein, font="Times-Roman")], begr,
         "Fiori + DB-Ticket + Hotelbrief (Langdatum) + Einladungsbrief", "Taxikosten im Antrag begründet (Ankunft 23:48, Rückkehr nach Mitternacht: Reiseende 00:05 am Folgetag); „weder Sitzungsgelder noch Honorare“", R_TAXI, SRC_DRM)


def k16():
    p = staff(16, "Dr.", fb="79")
    cid = "dienstreiseantrag-k16"
    out, back = "2027-02-17", "2027-02-18"
    created = weeks_before(out, 4)
    costs = [("Bahn", "Wernstadt – Berlin Hbf und zurück, 2. Klasse, mit privater BahnCard 50 (Fahrpreise bereits ermäßigt)", D("96.80")), ("Übernachtung", "1 Nacht à 74,00 €, Zimmer inkl. Frühstück", D("74.00"))]
    T = dict(person=p, nr="WEB-27-009930", created=created, dest="Berlin", country="Deutschland", abroad=False, anlass="Werkstattgespräch Baukultur, Akademie der Künste (Gesprächsrunde der Landschaftsarchitektur)",
             grund="Teilnahme als Fachgutachter:in; die Ergebnisse fließen in das laufende Entwurfsseminar ein", mode="Bahn 2. Klasse; private BahnCard 50 wird eingesetzt", start=(out, "07:05"), end=(back, "19:50"), biz_from=(out, "11:00"), biz_to=(back, "14:30"), priv="keiner", nights=1, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Die Fahrpreise enthalten bereits die Ermäßigung der privaten BahnCard 50; ein Firmenkundenrabatt kann damit nicht kombiniert werden."], attach=["Einladung.pdf", "Fahrkarte.pdf", "Hotel.pdf"], time="19:02")
    antrag = trip_antrag("web", T, glyph="cross", datefmt="slash")
    rail = rail_doc("bahn", p["plain"], [(out, "07:12", "Wernstadt Hbf", "10:41", "Berlin Hbf", "ICE 1507", "2. Klasse Sparpreis, BahnCard 50"), (back, "15:49", "Berlin Hbf", "19:17", "Wernstadt Hbf", "ICE 1502", "2. Klasse Sparpreis, BahnCard 50")],
                    [("Hinfahrt (BahnCard 50: –25 % auf Sparpreis 62,00 €)", D("46.90")), ("Rückfahrt (BahnCard 50: –25 % auf Sparpreis 66,60 €)", D("49.90"))], "B-27-3390", addday(created, 3), mfmt="de",
                    foot=["BahnCard 50 Nr. hinterlegt; Firmenkundenrabatt nicht kombinierbar mit BahnCard 25/50. Zahlung: persönliche Kreditkarte. Reservierung 4,50 € je Strecke: nicht gebucht."])
    hot = hotel_doc("letter", dict(name="Hotel Spreebogen", street="Invalidenstraße 71", plz="10557", city="Berlin", tel="030 5550 87", mail="info@spreebogen-hotel.example"), p["name"], p["org_long"], 1, D("74.00"), out, back, "HS-9921", addday(created, 2), datefmt="en",
                    foot=["Early check-in ab 10:00 Uhr gegen 15,00 € (nicht gebucht)."])
    prog = conf_pages("Werkstattgespräch Baukultur", "Akademie der Künste, Fachgruppe Baukunst", "Pariser Platz 4", "10117 Berlin", [(out, [("11:00", "Begrüßung"), ("11:30", "Gesprächsrunde Landschaftsarchitektur (geladene Gutachterinnen und Gutachter)"), ("13:00", "Mittagsimbiss"), ("14:30", "Runde 2: Zwischenräume")]), (back, [("09:30", "Thesen und Ergebnisse"), ("13:00", "Schlussrunde"), ("14:30", "Ende")])],
                      ["Die Teilnahme für geladene Gutachterinnen und Gutachter ist kostenfrei. Es wird kein Honorar gezahlt."], url="https://akademie.example/werkstattgespraech")
    begr = ("Online-Antrag vier Wochen vor der Reise; die Fahrpreise zeigen den Einsatz der privaten BahnCard 50 (Pflicht bei Besitz) ohne Firmenkundenrabatt. Eine Nacht zu 74,00 € inkl. Frühstück, Rechnung auf die Universität, Programm belegt die Gutachterrolle, kein Honorar.")
    case(TRIP, cid, [doc("online-antrag.pdf", antrag, font="Helvetica"), doc("db.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("programm.pdf", prog, font="Helvetica")], begr,
         "Web-Formular mit „[✘]“ + DB-Ticket mit BahnCard-Rabatt (Zeilenumbrüche) + Hotelbrief mit englischem Datum + Programm", "Private BahnCard 50 eingesetzt; Fahrpreise bereits ermäßigt (ursprüngliche Sparpreise 62,00 / 66,60 stehen in der Zeile); Early-Check-in-Fußnote 15,00 €",
         R_BAHNCARD + " " + R_HOTEL, SRC_DRM)


def k17():
    p = staff(17, "Dr.", fb="73")
    p["first"], p["last"], p["plain"], p["name"] = "Sunita", "Raghunathan", "Sunita Raghunathan", "Dr. Sunita Raghunathan"
    p["email"] = "sunita.raghunathan@uni-wernstadt.de"
    cid = "dienstreiseantrag-k17"
    out, back = "2027-09-06", "2027-09-10"
    created = weeks_before(out, 11)
    costs = [("Rail fare Wernstadt - Ljubljana and back", "2nd class, saver fares via Munich and Salzburg", D("189.00")), ("Accommodation", "4 nights at EUR 68.00, room only", D("272.00")), ("Conference registration", "incl. welcome reception and lunches", D("280.00"))]
    T = dict(person=p, nr="3381030312", created=created, dest="Ljubljana", country="SLOVENIA", abroad=True, anlass="PhotoMat Europe 2027 - Conference on Photonic Materials", grund="Oral presentation of the accepted abstract 'Defect Tolerance in Perovskite Films' (acceptance attached)",
             mode="Train, 2nd class", start=(out, "05:50"), end=(back, "22:40"), biz_from=(addday(out, 1), "09:00"), biz_to=(addday(back, -1), "18:00"), priv="none", nights=4, a1=f"applied for on {datef(created, 'en')} (more than 8 weeks ahead)", costs=costs,
             finance=[("Funding", f"Chair budget {p['ks']} / order {p['auftrag']}")], remarks=["Rail was chosen instead of flying because the total travel time differs by less than three hours and the fare is lower than the flight (EUR 241.00 from Frankfurt incl. airport transfers)."],
             attach=["acceptance.pdf", "rail-booking.pdf", "hotel.pdf", "registration.pdf"])
    antrag = trip_antrag("en", T, glyph="xs", datefmt="en")
    rail = rail_doc("en", p["plain"], [(out, "06:05", "Wernstadt Hbf", "17:48", "Ljubljana", "ICE 91 / RJX 63 / EC 213", "2nd class"), (back, "07:12", "Ljubljana", "19:33", "Wernstadt Hbf", "EC 212 / RJX 62 / ICE 90", "2nd class")],
                    [("Outbound saver fare", D("91.00")), ("Return saver fare", D("98.00"))], "OB-27-77120", addday(created, 3), foot=["Optional Nightjet couchette (EUR 59.00) not booked."])
    hot = hotel_doc("portal", dict(name="Central Park Hotel", street="Trg Republike 3", plz="1000", city="Ljubljana", tel="+386 1 555 0190", mail="reception@centralpark-lj.example"), p["plain"], p["org_long"], 4, D("68.00"), out, back, "STB-31-8800", addday(created, 5), breakfast=False, foot=["City tax EUR 3.13 per person and night is not included."])
    regd = reg_invoice("en", ["PhotoMat Europe 2027", "Cankarjeva 5, 1000 Ljubljana, Slovenia", "VAT SI xxxxxxxx"], [UW, p["org_long"], f"Attn. {p['name']}", UW_ADDR], "Registration invoice", "PME27-0234", addday(created, 6),
                       [("Early registration, academic rate, includes welcome reception, lunches (Tue-Fri) and coffee breaks", 1, D("280.00"), D("280.00"))], "Reverse charge - VAT 0 %.", ["Conference dinner EUR 75.00: not part of the fee, not booked."], dfmt="dmy-en", mfmt="eurplain")
    acc = owa_mail(p["email"].split("@")[0], "PhotoMat Europe 2027 - abstract accepted", "PhotoMat Europe 2027 <abstracts@photomat-europe.example>", f"{wd(addday(created, -35))} 12:30", p["plain"],
                   ["Dear Dr Raghunathan,", "", "we are pleased to confirm that your abstract 'Defect Tolerance in Perovskite Films' is accepted as an oral presentation (Wednesday 8 September 2027, 14:20).", "The registration fee for academic participants is EUR 280.00. We do not pay an honorarium.", "", "Kind regards,", "PhotoMat Europe 2027"])
    begr = ("English-language application eleven weeks ahead with the abroad field ticked [x] and the A1 certificate requested. Rail 2nd class (cheaper than flying), four nights at EUR 68.00 room only (invoice to the university), registration including reception; total EUR 741.00. Acceptance e-mail shows the talk and that no honorarium is paid.")
    assert trip_total(costs) == D("741.00")
    case(TRIP, cid, [doc("application.pdf", antrag, producer="ESS Travel Management"), doc("rail-booking.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("registration.pdf", regd, font="Helvetica"), doc("acceptance.pdf", acc, font="Helvetica")], begr,
         "Englischsprachiger Antrag (ESS in English) + englische Bahn-/Hotel-/Konferenzdokumente, Daten „6 September 2027“, Beträge „EUR 280.00“", "Alles auf Englisch, kein deutscher Text außer Stammdaten; Nightjet und Konferenzdinner nicht gebucht; Stadttaxe nicht enthalten",
         R_A1 + " " + R_HOTEL_ABROAD, SRC_DRM, "high")


def k18():
    p = staff(18, "Prof. Dr.", fb="77")
    cid = "dienstreiseantrag-k18"
    out, back = "2027-05-18", "2027-05-20"
    created = addday(out, -12)
    costs = [("Bahn", "Wernstadt – Freiburg und zurück, 2. Klasse", D("212.40")), ("Unterkunft", "2 Nächte à 79,00 €, inkl. Frühstück", D("158.00")), ("Tagungsgebühr", "Mitglied, inkl. Abendempfang", D("280.00"))]
    T = dict(person=p, nr="4417349915", created=created, status="Genehmigt (qua Amt, Präsidiumsbeschluss 656)", dest="Freiburg im Breisgau", country="DEUTSCHLAND", abroad=False, anlass="Jahrestagung der Gesellschaft für Pflanzenbauwissenschaften", grund="Plenarvortrag und Sitzungsleitung „Zwischenfrüchte und Bodenwasser“",
             mode="Bahn, 2. Klasse", start=(out, "05:40"), end=(back, "22:20"), biz_from=(addday(out, 1), "09:00"), biz_to=(back, "16:00"), priv="keiner", nights=2, costs=costs, finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}")],
             remarks=["Inlandsdienstreise einer Professorin/eines Professors mit einer Dauer von drei Tagen (bis sieben Tage): gilt qua Amt als genehmigt gem. § 2 Abs. 1 Satz 2 HRKG (Präsidiumsbeschluss 656 vom 21.07.2025). Der Eintrag dient der Mittelbindung."], attach=["Programm.pdf", "Bahn.pdf", "Hotel.pdf"])
    antrag = trip_antrag("fiori", T)
    prog = conf_pages("Jahrestagung der Gesellschaft für Pflanzenbauwissenschaften 2027", "GfP", "Konzerthaus Freiburg", "Konrad-Adenauer-Platz 1, 79098 Freiburg", [(addday(out, 1), [("09:00", "Eröffnung"), ("10:00", f"Plenarvortrag: {p['plain']}"), ("19:00", "Abendempfang (in der Tagungsgebühr enthalten)")]), (back, [("09:00", f"Sitzung „Zwischenfrüchte und Bodenwasser“ – Leitung {p['plain']}"), ("16:00", "Ende")])],
                      ["Tagungsgebühr für Mitglieder 280,00 € (inkl. Abendempfang, Kaffeepausen). Für eingeladene Plenarsprecher wird kein Honorar gezahlt."], url="https://gfp-tagung.example/2027")
    rail = rail_doc("mail", p["plain"], [(out, "06:00", "Wernstadt Hbf", "11:45", "Freiburg(Breisgau) Hbf", "ICE 273", "2. Klasse"), (back, "16:50", "Freiburg(Breisgau) Hbf", "22:08", "Wernstadt Hbf", "ICE 276", "2. Klasse")], [("Hinfahrt", D("101.20")), ("Rückfahrt", D("111.20"))], "F-27-1040", addday(created, 1))
    hot = hotel_doc("letter", dict(name="Hotel Münsterblick", street="Herrenstraße 8", plz="79098", city="Freiburg", tel="0761 5550 20", mail="reservierung@muensterblick.example"), p["name"], p["org_long"], 2, D("79.00"), addday(out, 1), back, "MB-27-5521", addday(created, 1), datefmt="de")
    begr = ("Inlandsdienstreise einer Professorin/eines Professors über drei Tage (bis sieben Tage): gilt nach dem Präsidiumsbeschluss 656 qua Amt als genehmigt, der Fiori-Eintrag dient der Mittelbindung und nennt dies ausdrücklich. "
            "Programm, Bahn (212,40 €) und zwei Nächte zu 79,00 € inkl. Frühstück (Hotelrechnung an die Universität) sind belegt.")
    case(TRIP, cid, [doc("reiseantrag.pdf", antrag, font="Helvetica"), doc("programm.pdf", prog, font="Helvetica"), doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica")], begr,
         "Fiori-Eintrag einer Professur mit Status „Genehmigt (qua Amt)“ + Tagungsprogramm + Mail + Hotelbrief", "Antrag nur 12 Tage vor Reisebeginn; Professur, Inland, 3 Tage: Genehmigung qua Amt; kein Honorar für Plenarsprecher",
         R_PROF, SRC_DRM, "high")


def k19():
    p = staff(19, "Dr.", fb="72")
    cid = "dienstreiseantrag-k19"
    out, back = "2027-04-19", "2027-04-20"
    created = weeks_before(out, 5)
    costs = [("Flug", "Frankfurt FRA – München MUC und zurück, Economy", D("168.00")), ("Bahn zum Flughafen Frankfurt", "2. Klasse, hin/zurück", D("56.00")), ("Übernachtung", "1 Nacht à 79,00 €, inkl. Frühstück", D("79.00"))]
    T = dict(person=p, nr="4417352281", created=created, dest="München", country="DEUTSCHLAND", abroad=False, anlass="Abnahmetermin Prüfstand beim Projektpartner und Abstimmung zur Fertigungslinie", grund="Teilnahme an der Werksabnahme des gemeinsam entwickelten Prüfstands (Termin 20.04., 08:00 Uhr)",
             mode="Flugzeug (Economy) mit Anreise zum Flughafen per Bahn", extra_general=[("Begründung Flug im Inland", "siehe Anlage 1 (Kosten- und Zeitvergleich)")], start=(out, "10:45"), end=(back, "21:30"), biz_from=(out, "15:00"), biz_to=(back, "13:00"), priv="keiner", nights=1, costs=costs,
             finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}")], remarks=[], attach=["Anlage_1_Begruendung_Flug.pdf", "Flugbuchung.pdf", "Hotel.pdf", "Terminbestaetigung.pdf"])
    antrag = trip_antrag("fiori", T)
    anl = "\n".join(["Anlage 1 zum Dienstreiseantrag " + T["nr"] + ": Begründung der Flugreise im Inland", "", f"Reise {p['plain']}, Wernstadt – München, {de(out)} bis {de(back)}", "",
                     row(["", "Bahn (Wernstadt–München)", "Flug (inkl. Bahn zum Flughafen)"], [26, 26, 30], "lrr"), row(["Fahrpreis hin/zurück", money(D("238.80")), money(D("224.00"))], [26, 26, 30], "lrr"),
                     row(["Reisezeit einfach", "ca. 5 h 45 min", "ca. 3 h 40 min"], [26, 26, 30], "lrr"), row(["Reisezeit gesamt (hin/zurück)", "ca. 11 h 30 min", "ca. 7 h 20 min"], [26, 26, 30], "lrr"), "",
                     "Begründung: Der Flug ist 14,80 € günstiger als die Bahn (Flexpreis, da Abnahmetermin um 08:00 Uhr nicht verschiebbar) und spart insgesamt rund 4 Stunden Arbeitszeit. Gebucht ist die Economy Class.", f"Wernstadt, {de(created)}  {p['name']}"])
    assert D("168.00") + D("56.00") == D("224.00")
    fl = "\n".join([lr("FLUGBUCHUNG Business · Bestätigung", f"Ausdruck {datef(addday(created, 2), 'de')}", 100), "", f"Buchungscode: KX4-9TT2  · Reisende:r: {p['last'].upper()}/{p['first'].upper()} DR", "",
                    row(["Flug", "Datum", "Von", "Ab", "Nach", "An", "Klasse"], [8, 16, 16, 6, 16, 6, 14], "lllllll"), row(["AX 2210", wd(out), "Frankfurt FRA", "13:05", "München MUC", "14:10", "Economy Light"], [8, 16, 16, 6, 16, 6, 14], "lllllll"),
                    row(["AX 2217", wd(back), "München MUC", "17:50", "Frankfurt FRA", "18:55", "Economy Light"], [8, 16, 16, 6, 16, 6, 14], "lllllll"), "", row(["Tarif", money(D("131.00"))], [40, 12], "lr"), row(["Steuern und Gebühren", money(D("37.00"))], [40, 12], "lr"), row(["Gesamt", money(D("168.00"))], [40, 12], "lr"),
                    "", "Nicht gebucht: Aufgabegepäck 35,00 € · Sitzplatz 9,00 €."])
    hot = hotel_doc("mail", dict(name="Hotel Maximilian", street="Lindwurmstraße 90", plz="80337", city="München", tel="089 5550 77", mail="buchung@maximilian-hotel.example"), p["plain"], p["org_long"], 1, D("79.00"), out, back, "HM-8821", addday(created, 3))
    tb = owa_mail(p["email"].split("@")[0], "Termin Werksabnahme Prüfstand " + de(back), "Projektpartner Fertigungstechnik <abnahme@partner-fertigung.example>", f"{wd(addday(created, -20))} 08:15", p["name"],
                  ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"die Werksabnahme des Prüfstands ist für {wdl(back)}, 08:00 Uhr, im Werk 2 angesetzt. Der Termin ist wegen der Prüfstandsfreigabe nicht verschiebbar.", "Eine Vergütung für Ihre Teilnahme erfolgt nicht.", "", "Freundliche Grüße", "Projektpartner"])
    begr = ("Antrag fünf Wochen vor der Reise. Der Inlandsflug ist in einer Anlage begründet: Er ist günstiger als die Bahn (224,00 € gegenüber 238,80 €) und spart rund vier Stunden Arbeitszeit; gebucht ist Economy. Eine Nacht zu 79,00 €, Hotel auf die Universität; Terminbestätigung des Partners liegt bei.")
    case(TRIP, cid, [doc("antrag-fiori.pdf", antrag, font="Helvetica"), doc("anlage-1-flugbegruendung.pdf", anl, font="Helvetica"), doc("flugbuchung.pdf", fl, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("terminbestaetigung.pdf", tb, font="Helvetica")], begr,
         "Fiori + Anlage „Begründung Flug im Inland“ + Flugbuchung (DE) + Hotelmail + Terminbestätigung", "Inlandsflug mit begründender Anlage (günstiger und Zeitersparnis), Economy; Gepäck-/Sitzplatzgebühren nicht gebucht", R_FLUGIN, SRC_DRM, "high")


def k20():
    p = staff(20, "", fb="75")
    cid = "dienstreiseantrag-k20"
    out, back = "2027-03-30", "2027-03-31"
    created = weeks_before(out, 4)
    costs = [("Bahn", "Wernstadt – Frankfurt (Main) und zurück, 2. Klasse", D("98.60")), ("Übernachtung", "1 Nacht à 76,00 €", D("76.00")), ("Seminargebühr", "Fortbildung „Fördermittelrecht kompakt“", D("320.00"))]
    total = trip_total(costs)
    assert total == D("494.60")
    T = dict(person=p, nr="3381030544", created=created, dest="Frankfurt am Main", country="DEUTSCHLAND", abroad=False, anlass="Seminar „Fördermittelrecht kompakt“ des Deutschen Instituts für Forschungsmanagement", grund="Fortbildung im Aufgabengebiet Projektverwaltung (Reise zum Zweck der Fortbildung)",
             mode="Bahn, 2. Klasse", start=(out, "06:35"), end=(back, "20:40"), biz_from=(out, "10:00"), biz_to=(back, "16:00"), priv="keiner", nights=1, costs=costs, finance=[("Finanzierung", f"Kostenstelle {p['ks']}")], remarks=["Fortbildungsreise; Anmeldung und Programm liegen bei."], attach=["Seminarprogramm", "Bahn", "Hotel"])
    antrag = trip_antrag("ess", T, glyph="x", datefmt="slash")
    mail = owa_mail(p["email"].split("@")[0], "Dienstreiseantrag " + p["plain"] + ", Seminar Frankfurt " + de(out), f"{p['plain']} <{p['email']}>", f"{wd(addday(created, 1))} 08:20", "reisekosten@uni-wernstadt.de",
                    ["Sehr geehrte Damen und Herren,", "", f"anbei der Dienstreiseantrag (Reisenummer {T['nr']}) für das Seminar in Frankfurt am {de(out)} und {de(back)} samt Anlagen. Zur schnelleren Bearbeitung die Kosten in Kürze:", "",
                     "   Bahn hin und zurück           98,60 EUR", "   Übernachtung 1 x 76,00        76,00 EUR", "   Seminargebühr                 320,00 EUR", "   --------------------------------------", "   Summe                         494,60 EUR", "",
                     "Die Reise dient der Fortbildung; Honorar oder Kostenübernahme durch Dritte gibt es nicht. Mietwagen: nein. Abschlag: nein.", "", "Mit freundlichen Grüßen", p["name"]])
    prog = conf_pages("Seminar „Fördermittelrecht kompakt“", "Deutsches Institut für Forschungsmanagement", "Tagungszentrum Mainufer", "Mainkai 7, 60311 Frankfurt am Main",
                      [(out, [("10:00", "Grundlagen Zuwendungsrecht"), ("12:30", "Mittagspause"), ("13:30", "Verwendungsnachweis und Prüfung")]), (back, [("09:00", "Vergaberecht im Projekt"), ("13:00", "Mittagspause"), ("16:00", "Ende")])],
                      ["Seminargebühr 320,00 € (steuerfrei, Bildungsleistung). Anmeldung verbindlich bis 16.03.2027."], url="https://dif-fm.example/seminare/foerdermittelrecht")
    rail = rail_doc("practice", p["plain"], [(out, "06:50", "Wernstadt Hbf", "09:13", "Frankfurt(Main) Hbf", "ICE 1042", "2. Klasse Sparpreis"), (back, "17:02", "Frankfurt(Main) Hbf", "19:31", "Wernstadt Hbf", "ICE 1049", "2. Klasse Sparpreis")],
                    [("Hinfahrt", D("46.60")), ("Rückfahrt", D("52.00"))], "FF-27-701", addday(created, 2))
    hot = hotel_doc("table", dict(name="City Inn Bahnhof", street="Poststraße 6", plz="60329", city="Frankfurt", tel="069 5550 130", mail="info@cityinn-ffm.example"), p["plain"], p["org_long"], 1, D("76.00"), out, back, "CI-27-2210", addday(created, 2), datefmt="slash")
    begr = ("Der Antrag ist vier Wochen vor dem Seminar gestellt; die Begleit-E-Mail nennt dieselben Beträge wie der Antrag (494,60 €). Seminarprogramm belegt Ort und Dauer, Reise zur Fortbildung im Aufgabengebiet. Bahn, eine Nacht zu 76,00 € und die Gebühr 320,00 €; Mietwagen und Abschlag nicht beantragt.")
    case(TRIP, cid, [doc("anlage-1.pdf", mail, font="Helvetica"), doc("antrag-dienstreise.pdf", antrag), doc("seminarprogramm.pdf", prog, font="Helvetica"), doc("anlage-3.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica")], begr,
         "Begleitmail (Outlook) mit Beträgen im Text + ESS-Antrag + Programm + DB-/Hotelbestätigungen (Organisatoren-Stil), neutrale Namen anlage-1/anlage-3", "Kostenübersicht als Textblock in der Mail (stimmt mit Antrag überein), „Mietwagen: nein. Abschlag: nein.“, Datumsformat 30/03/2027",
         R_ATTACH, SRC_DRM)


def k21():
    p = staff(21, "Dr.", fb="76")
    cid = "dienstreiseantrag-k21"
    out, back = "2027-06-01", "2027-06-02"
    created = weeks_before(out, 5)
    fee = D("266.00")
    costs = [("Bahn", "Wernstadt – Dortmund und zurück, 2. Klasse Sparpreis", D("117.80")), ("Übernachtung", "1 Nacht à 79,00 € (inkl. Frühstück)", D("79.00")), ("Tagungsgebühr einschl. Tagungspauschale", "Gebühr 190,00 € + Pauschale 76,00 €", fee)]
    T = dict(person=p, nr="4417356631", created=created, dest="Dortmund", country="DEUTSCHLAND", abroad=False, anlass="Mikrobiologie-Tage 2027", grund="Vortrag „Biofilmbildung auf Edelstahloberflächen“", mode="Bahn 2. Klasse", start=(out, "06:30"), end=(back, "19:50"), biz_from=(out, "10:30"), biz_to=(back, "15:00"), priv="keiner", nights=1, costs=costs,
             finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}")], remarks=["Die Tagungspauschale umfasst Mittagessen und Kaffeepausen an beiden Tagen und ist in der Rechnung gesondert ausgewiesen."], attach=["Rechnung_Tagung.pdf", "Bahn.pdf", "Hotel.pdf", "Programm.pdf"])
    antrag = trip_antrag("fiori", T, datefmt="long")
    net, vat = vat_split(fee, 19)
    inv = reg_invoice("de", ["Verband für Mikrobiologie und Hygiene e. V.", "Tagungsbüro, Westfalendamm 220, 44141 Dortmund", "USt-IdNr. DE 3xx xxx xxx"], [UW, p["org_long"], f"z. Hd. {p['name']}", UW_ADDR], "Rechnung über die Teilnahme an den Mikrobiologie-Tagen 2027", "MT27-1127", addday(created, 7),
                      [("Tagungsgebühr (Vortragende), beide Tage", 1, vat_split(D("190.00"), 19)[0], D("190.00")), ("Tagungspauschale: Mittagessen und Kaffeepausen an beiden Tagen", 2, vat_split(D("76.00"), 19)[0], D("76.00"))],
                      f"Rechnungsbetrag {money(fee)}, darin 19 % USt {money(vat)}.", ["Zahlbar bis 14 Tage vor Tagungsbeginn."], dfmt="de", mfmt="de")
    rail = rail_doc("bahn", p["plain"], [(out, "06:44", "Wernstadt Hbf", "09:40", "Dortmund Hbf", "ICE 925", "2. Klasse Sparpreis"), (back, "16:13", "Dortmund Hbf", "19:09", "Wernstadt Hbf", "ICE 928", "2. Klasse Sparpreis")], [("Hinfahrt", D("55.90")), ("Rückfahrt", D("61.90"))], "DO-0021-X", addday(created, 3))
    hot = hotel_doc("letter", dict(name="Parkhotel Westfalen", street="Hohe Straße 14", plz="44139", city="Dortmund", tel="0231 5550 4", mail="rezeption@parkhotel-westfalen.example"), p["name"], p["org_long"], 1, D("79.00"), out, back, "PW-27-318", addday(created, 3))
    prog = conf_pages("Mikrobiologie-Tage 2027", "Verband für Mikrobiologie und Hygiene e. V.", "Kongresszentrum Westfalenhalle", "Dortmund", [(out, [("10:30", "Eröffnung"), ("11:30", f"Vortrag {p['plain']}: Biofilmbildung auf Edelstahloberflächen"), ("12:30", "Mittagessen (Tagungspauschale)")]), (back, [("09:00", "Plenum"), ("15:00", "Ende")])], ["Die Tagungspauschale ist für alle Teilnehmenden verbindlich."], url="https://mikrobiologie-tage.example")
    begr = ("Antrag fünf Wochen vorab. Die Rechnung weist die Tagungspauschale (Mittagessen, Kaffeepausen) gesondert als notwendige Pauschale aus (76,00 €); dazu Gebühr 190,00 €, Bahn 117,80 € und eine Nacht zu 79,00 €. Summe 462,80 €, alle Belege auf die Universität.")
    case(TRIP, cid, [doc("fiori.pdf", antrag, font="Helvetica"), doc("rechnung-tagung.pdf", inv, font="Helvetica"), doc("db.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica"), doc("programm.pdf", prog, font="Helvetica")], begr,
         "Fiori mit Langdatum + Tagungsrechnung (19 % USt, zwei Positionen) + DB + Hotelbrief + Programm", "Verpflegung nur als ausgewiesene Tagungspauschale (Gebühr 190 + Pauschale 76 = 266); Mehrwertsteuer im Rechnungsbetrag enthalten", R_TAGUNG, SRC_DRM)
    assert trip_total(costs) == D("462.80")


def k22():
    p = staff(22, "Dr.", fb="73")
    cid = "dienstreiseantrag-k22"
    out, back = "2027-10-12", "2027-10-15"
    created = weeks_before(out, 9)
    costs = [("Bahn Wernstadt – Lyon und zurück", "2. Klasse, über Paris/Strasbourg", D("218.00")), ("Unterkunft", "3 Nächte à 69,00 €, ohne Frühstück", D("207.00")), ("Konferenzgebühr", "inkl. Cocktail de bienvenue", D("300.00"))]
    T = dict(person=p, nr="WEB-27-051180", created=created, dest="Lyon", country="FRANKREICH", abroad=True, anlass="Journées Optique Appliquée 2027", grund="Vortrag (Sprache: Englisch) „Adaptive Aberration Correction in Compact Cameras“", mode="Bahn, 2. Klasse", start=(out, "05:40"), end=(back, "23:05"),
             biz_from=(addday(out, 1), "09:00"), biz_to=(addday(back, -1), "17:30"), priv="keiner", nights=3, a1=f"beantragt am {de(created)} (Vorlauf > 8 Wochen)", costs=costs, finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Das Hotel liegt unter der Höchstgrenze des Auslandsübernachtungsgeldes für Frankreich."], attach=["Annahme", "Billet", "Hotel", "Inscription"], caps=True)
    antrag = trip_antrag("paper", T, glyph="mark")
    rail = "\n".join([lr("RAILEUROPE EXPRESS · Confirmation de commande", f"imprimé le {datef(addday(created, 3), 'slash')}", 100), "", f"Voyageur : {p['plain']}  ·  Facturation : {UW}", "", f"Aller   {datef(out, 'slash')}   Wernstadt Hbf 06:02 -> Lyon Part-Dieu 15:27   (ICE/TGV, 2de classe, 2 correspondances)",
                      f"Retour  {datef(back, 'slash')}   Lyon Part-Dieu 09:40 -> Wernstadt Hbf 19:21   (TGV/ICE, 2de classe)", "", row(["Aller", money(D('104.00'), 'eur')], [30, 14], "lr"), row(["Retour", money(D('114.00'), 'eur')], [30, 14], "lr"), row(["Total TTC", money(D('218.00'), 'eur')], [30, 14], "lr"),
                      "", "Assurance annulation facultative 12,00 EUR (non souscrite)."])
    hot = hotel_doc("fr", dict(name="Hôtel des Terreaux".replace("ô", "o"), street="12 rue Puits Gaillot", plz="69001", city="Lyon", tel="+33 4 55 55 01 20", mail="contact@terreaux-hotel.example"), p["name"], p["org_long"], 3, D("69.00"), out, back, "HT-27-1109", addday(created, 5), breakfast=False,
                    foot=["Taxe de séjour (1,80 EUR par personne et par nuit) non incluse. Petit-déjeuner 11,00 EUR (non réservé)."])
    reg = reg_invoice("fr", ["Journees Optique Appliquee 2027", "Societe Francaise d'Optique, 8 rue de la Republique, 69002 Lyon", "TVA FR xx xxx xxx xxx"], [UW, p["org_long"], f"A l'attention de {p['name']}", UW_ADDR], "Facture / Confirmation d'inscription", "JOA27-0551", addday(created, 6),
                      [("Inscription auteur, comprenant dejeuners, pauses cafe et cocktail de bienvenue (mardi soir)", 1, D("300.00"), D("300.00"))], "TVA 0 % (autoliquidation). Destinataire : Universität Wernstadt.", ["Le diner de gala (80 EUR) n'est pas inclus et n'a pas ete reserve."], dfmt="slash", mfmt="eur")
    acc = owa_mail(p["email"].split("@")[0], "JOA 2027: acceptation de votre communication", "JOA 2027 <comite@joa2027.example>", f"{wd(addday(created, -28))} 09:12", p["plain"],
                   ["Dear Dr. " + p["last"] + ",", "", "your talk 'Adaptive Aberration Correction in Compact Cameras' is accepted for JOA 2027, Lyon, 13-14 October 2027 (talk on 13 October, 15:10).", "Kind regards, the JOA 2027 committee (no honorarium, no travel support)"])
    begr = ("Gescanntes Papierformular neun Wochen vor der Reise, Auslandsfeld mit [✓] markiert, A1 beantragt. Hotel 69,00 € je Nacht ohne Frühstück (französische Bestätigung auf die Universität), Bahn 2. Klasse, Gebühr inklusive Begrüßungscocktail (Rahmenprogramm über die Teilnahmegebühr), Gala-Dinner nicht gebucht. Summe 725,00 €.")
    case(TRIP, cid, [doc("Scan_20270309_001.pdf", antrag, jitter=1.0, producer="Epson Scan"), doc("Scan_20270309_002.pdf", rail, font="Helvetica", jitter=0.7), doc("Scan_20270309_003.pdf", hot, font="Helvetica", jitter=0.7), doc("Scan_20270309_004.pdf", reg, font="Helvetica", jitter=0.7), doc("Scan_20270309_005.pdf", acc, font="Helvetica")], begr,
         "Papierformular als Scan (Zeilenversatz, „[✓]“) + französische Bahn-, Hotel- und Rechnungsdokumente, Dateien Scan_…_001-005", "Französische Dokumente (TVA, TTC); Auslandsfeld mit „[✓]“; Cocktail in Gebühr enthalten, Gala-Dinner, Stornoversicherung und Frühstück nicht gebucht",
         R_A1 + " " + R_HOTEL_ABROAD + " " + R_RAHMENPROG, SRC_DRM + "; " + SRC_FIBU, "medium")
    assert trip_total(costs) == D("725.00")


def k23():
    p = staff(23, "Dr.", fb="75")
    cid = "dienstreiseantrag-k23"
    day = "2027-11-16"
    created = weeks_before(day, 9)
    costs = [("Bahn Wernstadt – Brüssel und zurück", "2. Klasse, Sparpreis, Tagesreise", D("168.60"))]
    T = dict(person=p, nr="4417361150", created=created, dest="Brüssel", country="BELGIEN", abroad=True, anlass="Konsortialtreffen EU-Projekt „DigiRegio“", grund="Teilnahme am halbtägigen Konsortialtreffen (Work Package 4), Partner aus 7 Ländern", mode="Bahn, 2. Klasse; Tagesreise ohne Übernachtung",
             start=(day, "04:55"), end=(day, "23:10"), biz_from=(day, "11:00"), biz_to=(day, "16:30"), priv="keiner", nights=0, a1=f"beantragt am {de(created)} (Vorlauf > 8 Wochen)", costs=costs, finance=[("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['dr_auftrag']} (Drittmittel DigiRegio)")],
             remarks=["Mittagessen wird vom Gastgeber gestellt; das Tagegeld wird bei der Abrechnung entsprechend gekürzt. Reise- und Übernachtungskosten werden vom Koordinator nicht erstattet."], attach=["Einladung_Konsortialtreffen.pdf", "Bahnbuchung.pdf"])
    antrag = trip_antrag("fiori", T, datefmt="de")
    rail = rail_doc("en", p["plain"], [(day, "05:12", "Wernstadt Hbf", "10:02", "Bruxelles-Midi", "ICE 16 / THA 9", "2nd class"), (day, "17:56", "Bruxelles-Midi", "22:44", "Wernstadt Hbf", "THA 12 / ICE 29", "2nd class")], [("Outbound saver fare", D("79.60")), ("Return saver fare", D("89.00"))], "BX-27-8812", addday(created, 5), foot=["Flexible fare: EUR 249.00 (not booked)."])
    ein = owa_mail(p["email"].split("@")[0], "DigiRegio WP4 consortium meeting, Brussels, 16 November 2027", "DigiRegio Coordination <coordination@digiregio.example>", f"{wd(addday(created, -20))} 13:10", "All WP4 partners",
                   ["Dear partners,", "", f"the WP4 consortium meeting takes place on {wen(day)}, 11:00-16:30, at the Regional Office, Rue de la Loi 155, 1040 Brussels. A sandwich lunch is provided by the host.", "As agreed in the consortium agreement, the coordinator does not reimburse travel or accommodation costs; partners cover them from their own project budgets.", "",
                    "Best regards,", "DigiRegio coordination team"])
    begr = ("Antrag neun Wochen vor der Reise; Tagesreise ins EU-Ausland mit gesetztem Auslandsfeld und rechtzeitig beantragter A1. Die Einladung belegt Anlass, Ort und Dauer; der Koordinator erstattet nichts (keine Doppelfinanzierung), das vom Gastgeber gestellte Mittagessen ist im Antrag genannt. Kosten: Bahn 168,60 €, finanziert aus dem Drittmittelprojekt.")
    case(TRIP, cid, [doc("reiseantrag-fiori.pdf", antrag, font="Helvetica"), doc("rail.pdf", rail, font="Helvetica"), doc("invitation-wp4.pdf", ein, font="Helvetica")], begr, "Fiori + englische Bahnbestätigung + englische Einladung zum Konsortialtreffen", "Eintägige Auslandsreise (A1 trotzdem beantragt); Mittagessen vom Gastgeber gestellt, im Antrag erwähnt; Koordinator erstattet nichts",
         R_A1 + " " + R_DRITT, SRC_DRM, "medium")


def k24():
    p = staff(24, "Dr.", fb="78")
    cid = "dienstreiseantrag-k24"
    out, back = "2027-06-08", "2027-06-10"
    created = weeks_before(out, 4)
    costs = [("Bahn", "Wernstadt – Berlin und zurück, 2. Klasse Sparpreis", D("158.20")), ("Übernachtung", "2 Nächte à 79,00 €, inkl. Frühstück", D("158.00"))]
    T = dict(person=p, nr="4417363307", created=created, dest="Berlin", country="DEUTSCHLAND", abroad=False, anlass="Jahrestagung der Sektion Arbeits- und Industriesoziologie", grund="Vortrag in der Sitzung „Digitale Kontrolle“ am Mittwochabend (Programm anbei)",
             mode="Bahn, 2. Klasse", start=(out, "06:50"), end=(back, "17:30"), biz_from=(out, "13:00"), biz_to=(back, "13:00"), priv="keiner", nights=2, costs=costs, finance=[("Kostenstelle", p["ks"])],
             remarks=["Zwei Übernachtungen sind notwendig: Der Abendvortrag am " + wd(addday(out, 1)) + " endet um 21:15 Uhr, danach fährt kein Zug mehr nach Wernstadt."], attach=["Programm.pdf", "Bahn.pdf", "Hotel.pdf"])
    antrag = trip_antrag("ess", T, glyph="paren", datefmt="dmy-en")
    prog = conf_pages("Jahrestagung der Sektion Arbeits- und Industriesoziologie", "Deutsche Gesellschaft für Soziologie (Sektion)", "Humboldt-Haus", "Berlin-Mitte", [(out, [("13:00", "Eröffnung"), ("14:00", "Plenum")]), (addday(out, 1), [("10:00", "Sektionssitzungen"), ("19:00", "Sitzung „Digitale Kontrolle“"), ("21:15", f"Ende; Vortrag {p['plain']} um 19:45")]), (back, [("09:00", "Abschlussrunde"), ("13:00", "Ende")])], ["Teilnahmegebühr: 40,00 € (Studierende frei). Kein Honorar."], url="https://soziologie-sektion.example/jahrestagung")
    rail = rail_doc("practice", p["plain"], [(out, "07:02", "Wernstadt Hbf", "10:31", "Berlin Hbf", "ICE 1507", "2. Klasse Sparpreis"), (back, "14:10", "Berlin Hbf", "17:39", "Wernstadt Hbf", "ICE 1502", "2. Klasse Sparpreis")], [("Hinfahrt", D("77.60")), ("Rückfahrt", D("80.60"))], "BE-27-4419", addday(created, 2))
    hot = hotel_doc("portal", dict(name="Hotel Humboldtpark", street="Torstraße 112", plz="10119", city="Berlin", tel="030 5550 321", mail="booking@humboldtpark-hotel.example"), p["plain"], p["org_long"], 2, D("79.00"), out, back, "STB-4410-9981", addday(created, 2), foot=["Free cancellation until 24 hours before arrival. Late arrival after 22:00 possible on request."], datefmt="de")
    begr = ("Antrag vier Wochen vorab; die zweite Übernachtung ist schriftlich begründet (Abendvortrag bis 21:15 Uhr, kein Anschlusszug). Zwei Nächte zu 79,00 € inkl. Frühstück, Bahn 158,20 €; Programm zeigt Vortrag und Dauer, Rechnungsempfänger ist die Universität.")
    case(TRIP, cid, [doc("antrag.pdf", antrag), doc("programm.pdf", prog, font="Helvetica"), doc("bahn.pdf", rail, font="Helvetica"), doc("hotel.pdf", hot, font="Helvetica")], begr,
         "ESS-Antrag mit Datum „08-JUN-2027“-Stil und „(x)“ + Programm + Bahn + Hotelportal", "Zweite Nacht ausdrücklich begründet (Abendvortrag); Teilnahmegebühr 40 € nur im Programm erwähnt, nicht beantragt (Studierende frei)", R_HOTEL, SRC_DRM, "high")


def k25():
    p = staff(25, "", fb="74")
    cid = "dienstreiseantrag-k25"
    out, back = "2027-04-06", "2027-04-07"
    created = weeks_before(out, 5)
    costs = [("Bahn", "Wernstadt – Frankfurt (Main) und zurück, 2. Klasse", D("94.80")), ("Übernachtung", "1 Nacht à 78,00 €, ohne Frühstück", D("78.00"))]
    T = dict(person=p, nr="", created=created, dest="Frankfurt am Main", country="DEUTSCHLAND", abroad=False, anlass="Statikertag Hessen 2027", grund="Fortbildung zu den neuen Bemessungsnormen; Vortrag im Forum „Bestandsbewertung“", mode="Bahn 2. Klasse", start=(out, "06:50"), end=(back, "19:35"), biz_from=(out, "10:00"), biz_to=(back, "15:30"), priv="keiner", nights=1, costs=costs,
             finance=[("Kostenstelle", f"{p['ks']} (Landesmittel)")], remarks=["Mietwagen: nein. Taxi: nein. Private Verlängerung: nein."], attach=["Einladung", "Bahnticket", "Hotelbestätigung"])
    antrag = trip_antrag("paper", T, glyph="xs", datefmt="short")
    einl = owa_mail(p["email"].split("@")[0], "Statikertag Hessen 2027: Programm und Einladung zum Vortrag", "Statikertag Hessen <info@statikertag.example>", f"{wd(addday(created, -40))} 10:05", p["name"],
                    ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"der Statikertag Hessen findet am {de2(out)} und {de2(back)} im Congress Center Frankfurt statt. Ihr Vortrag im Forum „Bestandsbewertung“ ist für den ersten Tag, 11:30 Uhr, vorgesehen.", "Die Teilnahme für Referierende ist gebührenfrei. Honorare werden nicht gezahlt.", "", "Mit freundlichen Grüßen", "Das Veranstaltungsteam"])
    rail = rail_doc("mail", p["plain"], [(out, "07:05", "Wernstadt Hbf", "09:28", "Frankfurt(Main) Hbf", "ICE 1042", "2. Klasse"), (back, "16:13", "Frankfurt(Main) Hbf", "18:41", "Wernstadt Hbf", "ICE 1049", "2. Klasse")], [("Hinfahrt", D("45.90")), ("Rückfahrt", D("48.90"))], "FFM-882", addday(created, 3))
    hot = hotel_doc("letter", dict(name="Hotel Zum Anker", street="Kaiserstraße 40", plz="60329", city="Frankfurt", tel="069 5550 880", mail="rezeption@anker-ffm.example"), p["name"], p["org_long"], 1, D("78.00"), out, back, "ZA-27-701", addday(created, 3), breakfast=False, datefmt="slash")
    parts = [(antrag, dict(font="Courier", jitter=1.0)), (einl, dict(font="Helvetica", jitter=0.8)), (rail, dict(font="Helvetica", jitter=0.8)), (hot, dict(font="Times-Roman", jitter=1.0))]
    random.Random(cid).shuffle(parts)
    begr = ("Gescannter Papierantrag fünf Wochen vor der Reise, zusammen mit Einladung (Vortrag, keine Gebühr, kein Honorar), Bahn und Hotelbestätigung in einer Sammeldatei in beliebiger Reihenfolge. Bahn 94,80 € und eine Nacht zu 78,00 €, Hotelbrief auf die Universität; Mietwagen, Taxi und private Verlängerung sind verneint.")
    case(TRIP, cid, [doc("Dokument.pdf", parts, producer="Brother ADS Scan"), doc("anlage-3.pdf", "Hinweis zur Anreise: Treffpunkt Foyer Congress Center, Eingang Ost, 09:30 Uhr (Referierende).\nAkkreditierung: Namensschild liegt bereit, Ausweis mitbringen.\n", font="Helvetica")], begr,
         "Sammel-Scan (Antrag, Mail, Bahn, Hotel in zufälliger Seitenfolge, verschiedene Schriften) + Zusatzblatt „anlage-3.pdf“", "Mehrere Dokumente in EINER Datei, Reihenfolge zufällig; Datum „6.4.2027“; Verneinungen „Mietwagen: nein. Taxi: nein. Private Verlängerung: nein.“; Zusatzblatt ohne Betrag",
         R_ATTACH, SRC_DRM)


# =========================================================================== #
# PROCUREMENT renderers
# =========================================================================== #
def items(*rows):
    """rows: (description, qty, unit_net)"""
    return [dict(desc=d, qty=q, unit=D(u)) for d, q, u in rows]


def calc(its, vat=19, disc=0):
    net = tot(*[i["qty"] * i["unit"] for i in its])
    if disc:
        net = r2(net * (1 - D(disc) / 100))
    v = vat_of(net, vat)
    return net, v, r2(net + v)


def item_lines(its, widths, aligns, mfmt="de", start=1, pos=True, indent=1):
    out = []
    for n, i in enumerate(its, start):
        ds = wrap(i["desc"], widths[1] if pos else widths[0])
        vals = ([str(n)] if pos else []) + [ds[0], str(i["qty"]), money(i["unit"], mfmt), money(i["qty"] * i["unit"], mfmt)]
        out.append(" " * indent + row(vals, widths, aligns))
        for extra in ds[1:]:
            out.append(" " * indent + row(([""] if pos else []) + [extra, "", "", ""], widths, aligns))
    return out


def sums_block(net, v, gross, vat=19, mfmt="de", right=100, labels=("Summe netto", "zzgl. {vat} % USt.", "Angebotssumme brutto"), disc=0, gross_net=None):
    L = []
    if disc:
        L.append(lr("", f"abzüglich {disc} % Rabatt (Nettosumme nach Rabatt)", right))
    L += [lr("", f"{labels[0]}  {money(net, mfmt)}", right), lr("", f"{labels[1].format(vat=vat)}  {money(v, mfmt)}", right), lr("", f"{labels[2]}  {money(gross, mfmt)}", right)]
    return L


def offer_doc(style, v, buyer, nr, date, valid, its, vat=19, mfmt="de", datefmt="de", foot=None, disc=0, subject=None, ref=None, ordermail=None):
    """a vendor offer in one of several imitated layouts; buyer = lines (university + unit + contact)"""
    net, vv, gross = calc(its, vat, disc)
    foot = foot or []
    vline = f"{v['street']} · {v['plz']} {v['city']}"
    if style == "letter":
        L = [lr(buyer[0], v["name"], 100)] + [lr(b, x, 100) for b, x in zip(buyer[1:] + [""] * 5, [v["street"], f"{v['plz']} {v['city']}", f"Tel. {v['tel']}", v["mail"]])] + [""]
        L += [lr("", f"Angebot Nr. {nr}", 100), lr("", f"Datum: {datef(date, datefmt)}", 100), lr("", f"Bindefrist: {datef(valid, datefmt)}", 100), ""]
        if ref:
            L += [lr("", f"Ihre Anfrage: {ref}", 100), ""]
        L += ["Angebot", "Wir danken für Ihre Anfrage und bieten Ihnen freibleibend an:", "", " " + row(["Bezeichnung", "Menge", "Einzelpreis netto", "Gesamt netto"], [56, 7, 17, 15], "lrrr")]
        L += item_lines(its, [56, 7, 17, 15], "lrrr", mfmt, pos=False)
        L += [""] + sums_block(net, vv, gross, vat, mfmt, disc=disc) + [""] + foot + [f"Bankverbindung: IBAN {v['iban']}", "", "Mit freundlichen Grüßen", v["name"]]
        return "\n".join(L)
    if style == "table":
        L = [f"{v['name']} · {vline} · {v['tel']} · {v['mail']}", "", ""] + [" " + b for b in buyer] + ["", lr("", f"Angebot {nr}", 100), lr("", f"vom {datef(date, datefmt)}", 100), lr("", f"gültig bis {datef(valid, datefmt)}", 100), "",
                                                                                                          "Ihr Angebot", "gerne bieten wir Ihnen wie folgt an:", "", "  " + row(["Pos", "Artikel / Leistung", "Menge", "EP netto", "GP netto"], [4, 56, 6, 14, 14], "llrrr")]
        L += item_lines(its, [4, 56, 6, 14, 14], "llrrr", mfmt, indent=2)
        L += [""] + sums_block(net, vv, gross, vat, mfmt, disc=disc) + [""] + foot + ["Preise zzgl. gesetzlicher USt., Versand frei.", f"Bankverbindung: IBAN {v['iban']}"]
        return "\n".join(L)
    if style == "en":
        L = [v["name"].upper(), vline, f"Tel. {v['tel']} · {v['mail']} · VAT ID {v['vat']}", "", "QUOTATION", lr(f"Quotation no. {nr}", f"Date: {datef(date, datefmt)}", 100), lr(f"Your reference: {ref or 'enquiry'}", f"Valid until: {datef(valid, datefmt)}", 100), "",
             "Customer:"] + [" " + b for b in buyer] + ["", " " + row(["Item / description", "Qty", "Unit price", "Amount"], [56, 6, 15, 15], "lrrr")]
        L += item_lines(its, [56, 6, 15, 15], "lrrr", mfmt, pos=False)
        if vat == 0:
            L += ["", lr("", f"Subtotal  {money(net, mfmt)}", 100), lr("", "VAT 0 % (intra-community supply, reverse charge)  " + money(D('0'), mfmt), 100), lr("", f"Total  {money(gross, mfmt)}", 100)]
        else:
            L += [""] + sums_block(net, vv, gross, vat, mfmt, labels=("Subtotal", "VAT {vat} %", "Total"), disc=disc)
        L += [""] + foot + ["Terms: delivery DAP Wernstadt, payment 30 days net. Prices valid for the period stated above.", f"Bank: IBAN {v['iban']}", "", "Kind regards", v["name"]]
        return "\n".join(L)
    if style == "mail":
        body = ["Sehr geehrte Damen und Herren,", "", f"vielen Dank für Ihre Anfrage{(' (' + ref + ')') if ref else ''}. Gerne unterbreiten wir Ihnen folgendes Angebot {nr} (gültig bis {datef(valid, datefmt)}):", ""]
        for n, i in enumerate(its, 1):
            for k, l_ in enumerate(wrap(f"Pos. {n}: {i['qty']} x {i['desc']}", 92)):
                body.append(("   " if k else "") + l_)
            body.append(f"        Einzelpreis netto {money(i['unit'], mfmt)}, Gesamt {money(i['qty'] * i['unit'], mfmt)}")
        body += ["", f"Summe netto: {money(net, mfmt)}", f"zzgl. {vat} % USt.: {money(vv, mfmt)}", f"Angebotssumme brutto: {money(gross, mfmt)}", ""] + foot + ["Lieferzeit ca. 10 Werktage ab Auftragseingang.", "", "Mit freundlichen Grüßen", v["name"], v["tel"]]
        return owa_mail("beschaffung", f"Angebot {nr}: {subject or 'Ihre Anfrage'}", f"{v['name']} <{v['mail']}>", wd(date) + " 10:41", buyer[2].replace("z. Hd. ", ""), body)
    if style == "web":
        L = [lr(f"https://{v['web']}/angebot/{nr}", f"Druckansicht {datef(date, datefmt)}", 100), "", f"{v['name']} · Online-Angebot", "",
             kvw([("Angebots-ID", nr), ("Erstellt am", datef(date, datefmt)), ("Gültig bis", datef(valid, datefmt)), ("Kunde", " / ".join(buyer))], k=18, width=78, indent=0), "",
             row(["Pos", "Produkt", "Anz.", "Stückpreis", "Zeilensumme"], [4, 54, 5, 14, 14], "llrrr")]
        L += item_lines(its, [4, 54, 5, 14, 14], "llrrr", mfmt, indent=0)
        L += [""] + sums_block(net, vv, gross, vat, mfmt, labels=("Warenwert netto", "MwSt. {vat} %", "Gesamt brutto"), disc=disc) + [""] + foot + ["[In den Warenkorb]   [Angebot als PDF]   [Bestellung auslösen]"]
        return "\n".join(L)
    raise ValueError(style)


def zb3(nr, date, p, ksb, kat, rv, vergabeart, n_off, lieferant, its, begruendung, vat=19, mfmt="de", cat_row=True, vat_note=None, extra_rows=None, title="Beschaffungsantrag / Bestellanforderung", sign_note=None):
    net, vv, gross = calc(its, vat)
    cats = " ".join(f"[{'X' if k == kat else ' '}] {k}" for k in ["Verbrauchsmaterial", "GWG", "Anlage", "Dienstleistung"])
    rows = [("Organisationseinheit", p["org_long"]), ("Antragsteller:in", p["name"]), ("Telefon", p["tel"]), ("Kostenstelle / Auftrag", f"{p['ks']} / Auftrag {p['auftrag']}"), ("Kostenstellenbevollmächtigte:r", ksb)]
    cls = ([("Kategorie", cats)] if cat_row else []) + [("Rahmenvertragsprodukt", "[X] ja [ ] nein" if rv else "[ ] ja [X] nein"), ("Vergabeart", vergabeart), ("Eingeholte Angebote", str(n_off)), ("Vorgesehener Lieferant", lieferant)] + (extra_rows or [])
    L = [lr(f" {UW}", f"Antrag Nr. {nr}", 100), lr("", f"Datum: {datef(date, 'de')}", 100), " Zentrale Beschaffung", " Eingang über: beschaffung@uni-wernstadt.de", "", f"  {title}", "  1. Bedarfsstelle", kvw(rows, k=34, width=76, indent=1),
         "", "  2. Einordnung", kvw(cls, k=34, width=76, indent=1), "", "  3. Positionen", "   " + row(["Pos.", "Bezeichnung", "Menge", "EP netto", "GP netto"], [5, 58, 6, 13, 13], "llrrr")]
    L += item_lines(its, [5, 58, 6, 13, 13], "llrrr", mfmt, indent=3)
    L += ["", lr("", f"Summe netto  {money(net, mfmt)}", 104), lr("", (vat_note or f"zzgl. {vat} % USt.") + f"  {money(vv, mfmt)}", 104), lr("", f"Gesamtbetrag brutto  {money(gross, mfmt)}", 104), "", "  4. Begründung des Bedarfs und der Lieferantenauswahl"]
    for b in begruendung:
        L += para(b, 104, 2)
    L += ["", "", lr(f"Wernstadt, {datef(date, 'de')}", f"Beauftragt: Kostenstellenbevollmächtigte:r  {ksb}", 104), "Antragsteller:in" + (("  " + sign_note) if sign_note else ""), "", lr("Formular ZB-3 · Beschaffungsantrag · Stand 01/2027", "Seite 1", 104)]
    return "\n".join(L)


def vermerk(nr, apnr, date, gegenstand, verfahren, wertung, offers, zuschlag, begr, mfmt="de", signer="Zentrale Beschaffung"):
    """award note; offers: [(Bieter, Angebotsnr, date, net, gross)]"""
    ranks = sorted(range(len(offers)), key=lambda i: offers[i][3])
    L = ["Vergabevermerk", f"{UW} · Vorgang {nr} · zum Beschaffungsantrag {apnr}", "", kvw([("Gegenstand", gegenstand), ("Verfahren", verfahren), ("Wertung", wertung)], k=22, width=76, indent=0), "", "Eingegangene Angebote",
         row(["Bieter", "Angebot", "vom", "netto", "brutto", "Rang"], [30, 12, 11, 14, 14, 5], "lllrrr")]
    for i, (b, a, d, n, g) in enumerate(offers):
        L.append(row([b, a, datef(d, "de"), money(n, mfmt), money(g, mfmt), str(ranks.index(i) + 1)], [30, 12, 11, 14, 14, 5], "lllrrr"))
    L += ["", kvw([("Zuschlag an", zuschlag)], k=22, width=76, indent=0), "", "Begründung der Vergabeentscheidung"] + para(begr, 100) + ["", f"Wernstadt, {datef(date, 'de')}", "", signer]
    return "\n".join(L)


def wps_cart(kind, nr, date, catalog, partner, who, kont, its, vat=19, status="zur Freigabe an Zentrale Beschaffung", notes=None, mfmt="de", art_prefix="RV", extra=None):
    net, vv, gross = calc(its, vat)
    L = [lr(f"WPS Warenbestellsystem · {UW}", f"Druckansicht {datef(date, 'iso')}", 110), "", f"Warenkorb {nr}",
         kvw([("Katalog", catalog), ("Lieferant (Rahmenvertragspartner)", partner), ("Angelegt", datef(date, "iso"))] + (extra or []) + [("Besteller:in", who), ("Kontierung", kont), ("Status", status)], k=36, width=70, indent=0), "",
         row(["Artikelnr.", "Bezeichnung", "Menge", "Preis netto", "Summe netto"], [16, 56, 7, 13, 13], "llrrr")]
    for n, i in enumerate(its, 1):
        ds = wrap(i["desc"], 56)
        L.append(row([f"{art_prefix}-{1000 + n * 37:04d}", ds[0], str(i["qty"]), money(i["unit"], mfmt), money(i["qty"] * i["unit"], mfmt)], [16, 56, 7, 13, 13], "llrrr"))
        L += [row(["", e, "", "", ""], [16, 56, 7, 13, 13], "llrrr") for e in ds[1:]]
    L += ["", lr("", f"Warenwert netto  {money(net, mfmt)}", 110), lr("", f"USt. {vat} %  {money(vv, mfmt)}", 110), lr("", f"Gesamt brutto  {money(gross, mfmt)}", 110), ""] + (notes or [])
    return "\n".join(L)


def srm_cart(nr, date, p, ksb, its, vendor_name, lang_text, vat=19, mfmt="de", notes=None, wgr="Messgeräte / Laborgeräte"):
    net, vv, gross = calc(its, vat)
    L = [lr("SAP SRM · Einkaufswagen (Bestellanforderung)", f"Druck {datef(date, 'de')} 14:22", 110), "", lr(f"Einkaufswagen {nr}", "Status: Zur Genehmigung / Bestellfreigabe", 110),
         kvw([("Ersteller", p["name"]), ("Kostenstelle / Auftrag", f"{p['ks']} / {p['auftrag']}"), ("Genehmiger", ksb), ("Warengruppe", wgr), ("Lieferant (vorgeschlagen)", vendor_name), ("Lieferadresse", f"{UW}, {p['org_long']}, {UW_ADDR}")], k=30, width=74, indent=0), "",
         row(["Pos", "Kurztext", "Menge", "Preis/Einh. (netto)", "Wert netto"], [4, 54, 6, 18, 14], "llrrr")]
    L += item_lines(its, [4, 54, 6, 18, 14], "llrrr", mfmt, indent=0)
    L += ["", lr("", f"Gesamtwert netto  {money(net, mfmt)}", 106), lr("", f"Steuer {vat} %  {money(vv, mfmt)}", 106), lr("", f"Gesamtwert brutto  {money(gross, mfmt)}", 106), "", "Langtext / Begründung des Bestellwunsches:"]
    for t in lang_text:
        L += para(t, 106, 2)
    L += [""] + (notes or [])
    return "\n".join(L)


def order_mail(frm_p, subject, to, cc, when, body, sig=None):
    b = ["Sehr geehrte Damen und Herren,", ""] + body + ["", "Mit freundlichen Grüßen"] + (sig or [frm_p["plain"], frm_p["fg"] + ", Tel. " + frm_p["tel"]])
    return owa_mail(frm_p["email"].split("@")[0], subject, f"{frm_p['plain']} <{frm_p['email']}>", when, to, b, cc=cc)


def three_offers(its_specs, prices, discs=(0, 0, 0)):
    """its_specs: [(desc_variants(3), qty)]; prices: [[p_a,p_b,p_c], ...] per position -> three item lists"""
    offs = []
    for k in range(3):
        offs.append(items(*[(dv[k], q, prices[n][k]) for n, ((dv, q)) in enumerate(its_specs)]))
    return offs


BUYER = lambda p: [UW, p["org_long"].replace(", Fachgebiet", " · FG"), f"z. Hd. {p['name']}", UW_ADDR]


def kstb(i, fb):
    return kostenstellenleiter(i, fb)["name"]


# =========================================================================== #
# PROCUREMENT  (beschaffungsantrag-k26 .. k50)
# =========================================================================== #
P3 = "„Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern.“"
P_KSB = "„Bestellungen müssen vom Kostenstellenbevollmächtigten (meist Fachgebietsleitung) beauftragt werden.“"
P_DIR = ("„Diese Pflicht [drei Vergleichsangebote] entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da hier eine Direktvergabe möglich ist.“")
P_RV = ("„Der Abschluss der Rahmenverträge ermöglicht den einzelnen Bereichen Ihre Bedarfe aus den jeweiligen Rahmensortimenten ohne das Einholen von "
        "Vergleichsangeboten zu decken.“ und „Die Bestellungen sind über das WPS-System zu buchen.“")
P_RVMUST = "„Sollte man ein Produkt bestellen wollen, zu dem ein Rahmenvertrag besteht, muss man dieses Produkt ausschließlich beim Rahmenvertragspartner bestellen“"


def offers_pack(p, vids, kind, d0, specs, prices, styles, mfmts=("de", "de", "de"), dfmts=("de", "de", "de"), names=None, foots=None, vat=19, vopts=None, ref="Anfrage", subj=None, nrs=None, kinds=None):
    names = names or ["angebot-1.pdf", "angebot-2.pdf", "angebot-3.pdf"]
    foots = foots or [[], [], []]
    vopts = vopts or [{}, {}, {}]
    its3 = three_offers(specs, prices)
    docs, summ, vs = [], [], []
    for k in range(3):
        v = vendor(vids[k], (kinds or [kind] * 3)[k])
        vs.append(v)
        date = addday(d0, 2 * k)
        valid = addday(date, 30)
        nr = (nrs or [f"AN-27-{300 + vids[k] * 7 + k:04d}", f"{2027}/{400 + vids[k]}", f"Q-{104000 + vids[k] * 11}"])[k]
        txt = offer_doc(styles[k], v, BUYER(p), nr, date, valid, its3[k], vat, mfmts[k], dfmts[k], foots[k], ref=ref, subject=subj)
        net, vv, gross = calc(its3[k], vat)
        summ.append((v["name"], nr, date, net, gross))
        o = dict(vopts[k])
        if styles[k] in ("letter", "table", "web", "en") and "font" not in o:
            o["font"] = "Helvetica" if styles[k] in ("table", "web", "en") else "Courier"
        elif styles[k] == "mail" and "font" not in o:
            o["font"] = "Helvetica"
        docs.append(doc(names[k], txt, **o))
    return docs, summ, its3, vs


def cheapest(summ):
    return min(range(3), key=lambda i: summ[i][3])


def side_by_side(title, sub, summ, its3, mfmt="de", valid_days=30):
    w = 30
    L = [title, sub, "", row(["Position"] + [s[0][:w - 2] for s in summ], [34, w, w, w], "llll")]
    L.append(row(["Angebot Nr. / vom"] + [f"{s[1]} / {datef(s[2], 'de')}" for s in summ], [34, w, w, w], "llll"))
    L.append(row(["gültig bis"] + [datef(addday(s[2], valid_days), "de") for s in summ], [34, w, w, w], "llll"))
    for n in range(len(its3[0])):
        L.append(row([f"Pos. {n + 1}: " + its3[0][n]["desc"][:24]] + [f"{its3[k][n]['qty']} x {money(its3[k][n]['unit'], mfmt)}" for k in range(3)], [34, w, w, w], "llll"))
    L.append(row(["Summe netto"] + [money(s[3], mfmt) for s in summ], [34, w, w, w], "llll"))
    L.append(row(["Summe brutto"] + [money(s[4], mfmt) for s in summ], [34, w, w, w], "llll"))
    return L


def k26():
    p = staff(26, "Dr.", fb="73")
    cid = "beschaffungsantrag-k26"
    ks = kstb(26, "73")
    specs = [(["Wärmebildkamera 384 × 288 Pixel, Objektiv 25°, Messbereich −20 bis 650 °C", "Infrarotkamera 384x288, 25°-Objektiv, −20…650 °C, Fokus manuell", "Thermografiekamera 384 × 288 px, Objektiv 25°, Bereich −20 °C bis 650 °C"], 1),
             (["Transportkoffer und Ersatzakku", "Hartschalenkoffer inkl. Zweitakku", "Koffer mit zweitem Akku"], 1), (["Kalibrierzertifikat (Werkskalibrierung)", "Werkskalibrierschein", "Kalibrierung mit Protokoll"], 1)]
    prices = [["2980.00", "3190.00", "3055.00"], ["260.00", "245.00", "290.00"], ["120.00", "135.00", "110.00"]]
    d0 = "2027-02-08"
    docs3, summ, its3, vs = offers_pack(p, [3, 9, 15], "mess", d0, specs, prices, ["letter", "table", "mail"], mfmts=("de", "eur", "en-eur"), dfmts=("de", "slash", "iso"),
                                         foots=[["* Garantieverlängerung auf 36 Monate: 190,00 € netto (nicht Bestandteil dieses Angebots)."], [], []], ref="Thermografie Prüffeld")
    c = cheapest(summ)
    its = its3[c]
    net, vv, gross = calc(its)
    reqd = "2027-02-17"
    antrag = zb3("ZB-2027-0211", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its,
                 ["Die Wärmebildkamera ersetzt das defekte Altgerät im Prüffeld Werkstoffanalytik. Es wurden drei Angebote eingeholt; das Angebot " + summ[c][1] + " ist bei gleicher Ausstattung das günstigste."], mfmt="de")
    ver = vermerk("V-27-0121", "ZB-2027-0211", addday(reqd, 1), "Wärmebildkamera mit Koffer und Kalibrierung", "Preisvergleich durch Einholung schriftlicher Angebote", "Preis (netto), bei gleicher technischer Eignung", summ, f"{summ[c][0]}, {money(summ[c][3])} netto",
                  "Alle drei Angebote erfüllen die Anforderungen. Den Zuschlag erhält das preislich günstigste Angebot.")
    begr = (f"Drei schriftliche Angebote ({', '.join(money(s[3]) for s in summ)} netto) bei einem Auftragswert über 1.000 €; der Antrag übernimmt die Positionen des günstigsten Angebots ({summ[c][1]}, {money(summ[c][3])} netto), Vergabevermerk und Antrag nennen dieselben Beträge. "
            "Wärmebildkameras sind kein Rahmenvertragsprodukt; die Kostenstellenbevollmächtigte hat beauftragt. Die Garantieverlängerung in der Fußnote ist nicht bestellt.")
    case(PROC, cid, [doc("beschaffungsantrag.pdf", antrag, producer="Formular ZB-3")] + docs3 + [doc("vergabevermerk.pdf", ver, font="Helvetica")], begr, "ZB-3-Formular + drei Angebote (Brief / Tabelle mit „EUR 3.570,00“ / Mail mit „EUR 3,455.00“) + Vergabevermerk",
         "Angebote in drei Zahlenformaten und Datumsformaten (30.01.2027 / 2027-02-10 / 12/02/2027-Stil); Fußnote mit Garantieverlängerung 190 € nicht bestellt; Zeilenumbrüche in Positionen", P3 + " " + P_KSB, SRC_BESCH, "high")


def k27():
    p = staff(27, "Prof. Dr.", fb="76")
    cid = "beschaffungsantrag-k27"
    ks = p["name"]
    specs = [(["Tischzentrifuge gekühlt, 24 × 1,5/2,0 ml, max. 21.000 × g", "Kühlzentrifuge Tischgerät, Rotor 24-fach, 21.000 x g", "Refrigerated benchtop centrifuge, 24-place rotor, 21,000 x g"], 1),
             (["Zusatzrotor 4 × 50 ml Röhrchen", "Rotor für 4 Röhrchen à 50 ml", "Additional rotor, 4 x 50 ml tubes"], 1), (["Einweisung vor Ort (halber Tag)", "Geräteeinweisung vor Ort", "On-site instruction (half day)"], 1)]
    prices = [["2150.00", "2290.00", "2075.00"], ["385.00", "360.00", "410.00"], ["120.00", "150.00", "95.00"]]
    d0 = "2027-03-01"
    its3 = three_offers(specs, prices)
    vs = [vendor(21, "lab"), vendor(33, "lab"), vendor(45, "lab")]
    summ, parts = [], []
    for k, (sty, fnt, mf) in enumerate([("letter", "Courier", "de"), ("table", "Helvetica", "bare-en"), ("en", "Times-Roman", "en-eur")]):
        date, nr = addday(d0, 3 * k), ["A-2027-0771", "KT/27/0418", "QUO-27-5531"][k]
        parts.append((offer_doc(sty, vs[k], BUYER(p), nr, date, addday(date, 30), its3[k], 19 if k < 2 else 19, mf, "de" if k < 2 else "en", ["Lieferzeit ca. 3 Wochen."] if k == 0 else []), dict(font=fnt)))
        net, vv, gross = calc(its3[k])
        summ.append((vs[k]["name"], nr, date, net, gross))
    c = cheapest(summ)
    reqd = "2027-03-12"
    its = its3[c]
    net, vv, gross = calc(its)
    cart = srm_cart("1000417733", reqd, p, ks, its, f"{summ[c][0]} (Angebot {summ[c][1]})", ["Ersatz für die ausgefallene Kühlzentrifuge im Labor 2.14.", "Es wurden drei schriftliche Angebote eingeholt: " + "; ".join(f"{s[0]} {money(s[3])}" for s in summ) + " (jeweils netto).",
                                                                                              "Zuschlag an das günstigste Angebot, alle Angebote technisch gleichwertig. Rahmenvertrag: nein (kein Rahmenvertragsprodukt)."], notes=["Beauftragt durch Kostenstellenbevollmächtigte: " + ks + ", " + datef(reqd, "de")])
    begr = (f"Der SRM-Einkaufswagen nennt im Langtext drei eingeholte Angebote ({', '.join(money(s[3]) for s in summ)} netto) und bestellt das günstigste ({summ[c][1]}, {money(summ[c][3])} netto); die Positionen entsprechen dem Angebot. "
            "Die drei Angebote liegen in einer Sammeldatei, eines davon auf Englisch. Kein Rahmenvertragsprodukt, beauftragt von der Kostenstellenbevollmächtigten.")
    case(PROC, cid, [doc("SRM-Einkaufswagen-1000417733.pdf", cart, font="Helvetica", producer="SAP GUI Print"), doc("angebote.pdf", parts, producer="Microsoft Print to PDF")], begr,
         "SAP-SRM-Einkaufswagen mit Begründung im Langtext + EINE Sammeldatei mit drei Angeboten, ein Angebot pro Seite (Brief, Tabelle, englische Quotation)", "Drei Angebote auf drei Seiten in verschiedenen Layouts und Sprachen, Preise „1.234,56“ / „1,234.56“; kein separater Vergabevermerk (Begründung im Einkaufswagen)",
         P3 + " " + P_KSB, SRC_BESCH, "high")


def k28():
    p = staff(28, "Dr.", fb="76")
    cid = "beschaffungsantrag-k28"
    ks = kstb(28, "76")
    specs = [(["Zentrifugenröhrchen 50 ml, steril, VE 500", "Röhrchen 50 ml steril PP, 500 Stk.", "Zentrifugenröhrchen PP 50 ml, steril, 500er-Pack"], 6), (["Reaktionsgefäße 1,5 ml, VE 1000", "Reaktionsgefäß 1,5 ml, 1.000 Stück", "Safe-Lock-Gefäße 1,5 ml, VE 1000"], 10),
             (["Nitril-Handschuhe Gr. M, puderfrei, VE 200", "Einmalhandschuhe Nitril M, 200 Stk.", "Nitrilhandschuhe M puderfrei, Box à 200"], 40)]
    prices = [["138.00", "142.50", "129.90"], ["34.50", "36.80", "33.90"], ["8.90", "9.20", "8.40"]]
    d0 = "2027-04-06"
    docs3, summ, its3, vs = offers_pack(p, [4, 10, 16], "lab", d0, specs, prices, ["mail", "mail", "mail"], mfmts=("de", "eur", "plain"), dfmts=("de", "de", "de"), names=["email-angebot-a.pdf", "email-angebot-b.pdf", "email-angebot-c.pdf"],
                                         ref="Anfrage Verbrauchsmaterial", subj="Verbrauchsmaterial Labor")
    c = cheapest(summ)
    side = "\n".join(side_by_side("Preisvergleich Verbrauchsmaterial Labor (Preisspiegel)", f"Erstellt von {p['plain']}, {de(addday(d0, 8))}; alle Preise netto, Staffelpreise nicht berücksichtigt", summ, its3))
    mail = order_mail(p, "Bestellung Laborverbrauchsmaterial, drei Angebote", "beschaffung@uni-wernstadt.de", f"{ks}", f"{wd(addday(d0, 9))} 09:15",
                      [f"für das Praktikumslabor bitte ich um Bestellung von Verbrauchsmaterial beim günstigsten Anbieter, {summ[c][0]} (Angebot {summ[c][1]}, {money(summ[c][3])} netto, {money(summ[c][4])} brutto).",
                       f"Die drei eingeholten Angebote ({'; '.join(s[1] for s in summ)}) und der Preisspiegel sind angehängt. Kein Rahmenvertragsprodukt.", f"Kostenstelle {p['ks']}, Auftrag {p['auftrag']}. {ks} (Kostenstellenbevollmächtigte) ist in Kopie und hat die Bestellung beauftragt."])
    begr = (f"Bestellung per E-Mail über {money(summ[c][3])} netto (über 1.000 €) mit drei Angeboten in Mailform ({', '.join(money(s[3]) for s in summ)} netto) und Preisspiegel; bestellt wird beim günstigsten Anbieter, die Positionen stimmen mit dem Angebot überein. Verbrauchsmaterial ohne Rahmenvertrag, Kostenstellenbevollmächtigte in Kopie.")
    case(PROC, cid, [doc("bestellung.pdf", mail, font="Helvetica")] + docs3 + [doc("preisspiegel.pdf", side)], begr, "Bestellmail mit Kopie an Kostenstellenbevollmächtigte + drei Angebote als Outlook-Mails + Preisspiegel nebeneinander (drei Spalten)",
         "Angebote als Mailtexte mit Beträgen in drei Formaten; Vergleich in Spaltenform (side by side); Verbrauchsmaterial über 1.000 € mit drei Angeboten", P3 + " " + P_KSB, SRC_BESCH, "high")


def k29():
    p = staff(29, "Dr.", fb="72")
    cid = "beschaffungsantrag-k29"
    ks = kstb(29, "72")
    specs = [(["Umwälzthermostat -25 bis 200 °C, 13 l Bad, Pumpe 20 l/min", "Kältethermostat -25…200 °C, Badvolumen 13 l, Umwälzpumpe", "Thermostat mit Kühlung, Arbeitsbereich -25 bis +200 °C, 13-l-Bad"], 1),
             (["Wärmeträgerflüssigkeit, Kanister 20 l", "Thermoflüssigkeit 20 l", "Wärmeträgeröl 20-l-Gebinde"], 2), (["Schlauchset isoliert, 2 m", "Isolierte Schlauchleitung 2 m (Paar)", "Schlauchpaar isoliert 2 m"], 2)]
    prices = [["1480.00", "1395.00", "1520.00"], ["96.00", "104.00", "99.00"], ["42.00", "39.50", "45.00"]]
    d0 = "2027-05-03"
    docs3, summ, its3, vs = offers_pack(p, [5, 11, 17], "mess", d0, specs, prices, ["web", "letter", "table"], mfmts=("de", "de", "eur"), dfmts=("de", "long", "de"), names=["angebot-web.pdf", "angebot-brief.pdf", "angebot-tabelle.pdf"], ref="Thermostat Wärmeübertragung")
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-05-13"
    antrag = zb3("ZB-2027-0376", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its, ["Neues Thermostat für den Versuchsstand Wärmeübertragung (Praktikum). Das gewählte Angebot ist bei gleicher Ausstattung das günstigste; ein Rahmenvertrag besteht nicht."], mfmt="de", cat_row=True)
    side = "\n".join(side_by_side("Angebotsvergleich Umwälzthermostat", f"Zusammenstellung {de(addday(reqd, -1))}; alle Beträge netto bzw. brutto in EUR", summ, its3))
    begr = (f"Drei schriftliche Angebote ({', '.join(money(s[3]) for s in summ)} netto); der Antrag übernimmt die Positionen des günstigsten ({summ[c][1]}), der Angebotsvergleich zeigt die drei Angebote nebeneinander mit denselben Summen. Kein Rahmenvertragsprodukt; beauftragt von der Kostenstellenbevollmächtigten.")
    case(PROC, cid, [doc("zb3.pdf", antrag)] + docs3 + [doc("vergleich-nebeneinander.pdf", side)], begr, "ZB-3 + Angebote (Web-Ausdruck, Brief mit Langdatum, Tabelle „EUR“) + Angebotsvergleich in drei Spalten",
         "Drei Angebote nebeneinander in einer Tabelle (Spalten); Web-Ausdruck eines Online-Angebots; Zahlen- und Datumsformate gemischt", P3 + " " + P_KSB, SRC_BESCH, "high")


def k30():
    p = staff(30, "Dr.", fb="71")
    cid = "beschaffungsantrag-k30"
    ks = kstb(30, "71")
    its = items(("Tragbarer Rechner 14 Zoll, 16 GB RAM, 512 GB SSD, Vertragskonfiguration B", 3, "1090.00"), ("Dockingstation USB-C, 100 W", 3, "129.90"), ("Monitor 27 Zoll, WQHD, USB-C, höhenverstellbar", 3, "214.00"))
    net, vv, gross = calc(its)
    assert net == D("4301.70")
    d = "2027-06-14"
    cart = wps_cart("rv", "WK-0027-31922", d, "Rahmenvertrag IT-Arbeitsplatzgeräte der hessischen Hochschulen, Los 1 und 2", "Systemhaus Hellweg GmbH, Offenbach", p["name"], f"{p['ks']} / Auftrag {p['auftrag']}", its, art_prefix="RV-IT",
                    notes=["Katalogpreise gemäß Rahmenvertrag. Zustimmung des ITS gilt bei Beschaffungen aus dem Rahmenvertrag für IT-Systeme als erteilt."])
    mail = order_mail(p, "Freigabe WPS-Warenkorb WK-0027-31922 (IT-Arbeitsplätze)", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 11:48",
                      ["für drei neue Arbeitsplätze meiner Mitarbeitenden habe ich im WPS den Warenkorb WK-0027-31922 aus dem IT-Rahmenvertrag angelegt (drei Notebooks, drei Docks, drei Monitore, zusammen " + money(net) + " netto).",
                       "Alle Artikel stammen aus dem Rahmenvertragskatalog; Vergleichsangebote entfallen. Kostenstelle " + p["ks"] + ". Die Kostenstellenbevollmächtigte " + ks + " ist in Kopie und hat die Bestellung beauftragt."])
    begr = (f"Alle drei Positionen (Notebooks, Docks, Monitore, {money(net)} netto) stammen laut WPS-Warenkorb aus dem Rahmenvertrag IT-Arbeitsplatzgeräte und werden über WPS gebucht; Vergleichsangebote entfallen bei Rahmenvertragspartnern. Mengen und Preise von Mail und Warenkorb stimmen überein, die Kostenstellenbevollmächtigte hat beauftragt.")
    case(PROC, cid, [doc("wps-warenkorb.pdf", cart, font="Helvetica"), doc("mail-freigabe.pdf", mail, font="Helvetica")], begr, "WPS-Warenkorb (Rahmenvertrag IT) + Freigabemail an die Beschaffung mit Kopie an die Kostenstellenbevollmächtigte",
         "4.301,70 € netto ohne Vergleichsangebote, weil Rahmenvertragsprodukte (Notebook/Dock/Monitor) über WPS; keine Angebote und kein Vergabevermerk", P_RV + " " + P_RVMUST, SRC_RV + "; " + SRC_ITS, "high")


def k31():
    p = staff(31, "", fb="75")
    cid = "beschaffungsantrag-k31"
    ks = kstb(31, "75")
    its = items(("Schnellhefter A4, Pappe, 100 Stück", 2, "11.80"), ("Ordner A4 breit, 80 mm, 20 Stück", 3, "36.40"), ("Notizblock A5 kariert, 50 Blatt, 10 Stück", 6, "9.20"), ("Kugelschreiber blau, Dokumentenecht, 50 Stück", 2, "18.90"), ("Haftnotizen 76 × 76 mm, 12er Pack", 4, "7.60"),
                ("Textmarker-Set 6 Farben", 8, "5.40"), ("Tacker-Klammern 24/6, 1000 Stück, 10 Schachteln", 3, "8.20"), ("Klarsichthüllen A4, genarbt, 100 Stück", 2, "6.90"))
    net, vv, gross = calc(its)
    d = "2027-02-23"
    cart = wps_cart("rv", "WK-0027-10311", d, "Rahmenvertrag Büro- und Geschäftsbedarf (Kernsortiment)", "Büro-Kontor Walther GmbH, Darmstadt", "Sekretariat " + p["fg"] + " (Ersteller)", f"{p['ks']} / {p['auftrag']}", its, art_prefix="BK",
                    notes=[f"Mindestbestellwert 15,00 € netto erfüllt (Warenwert {money(net)}); kein Mindermengenzuschlag."], extra=[("Ersteller:in", "Sekretariat " + p["fg"]), ("Bestellende Person (SAP)", p["name"])])
    mail = order_mail(p, "Bürobedarf aus dem Rahmenvertrag, WK-0027-10311", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 14:20", [f"anbei die Bestellung von Büro- und Geschäftsbedarf aus dem Rahmenvertrag über WPS (Warenkorb WK-0027-10311, {money(net)} netto). Es handelt sich ausschließlich um Artikel des Rahmensortiments; Angebote wurden daher nicht eingeholt.",
                                                                                                                                                  f"Kostenstelle {p['ks']}. Beauftragt durch {ks}."])
    begr = (f"Bürobedarf über {money(net)} netto stammt komplett aus dem Rahmenvertrag und wird im WPS-System gebucht (Warenkorb WK-0027-10311); Rahmensortimente brauchen keine Vergleichsangebote, der Mindestbestellwert von 15 € netto ist erreicht. Die Artikel sind einzeln benannt, die Kostenstellenbevollmächtigte hat beauftragt.")
    case(PROC, cid, [doc("warenkorb-buerobedarf.pdf", cart, font="Helvetica"), doc("email-beschaffung.pdf", mail, font="Helvetica")], begr, "WPS-Warenkorb Büro- und Geschäftsbedarf (Ersteller: Sekretariat, Besteller mit SAP-Zugang) + Bestellmail", "Rahmenvertrag Büromaterial über WPS, 8 Artikel einzeln bezeichnet (Büromaterial wird nicht pauschal genannt); Mindestbestellwert erwähnt",
         P_RV, SRC_RV, "high")


def k32():
    p = staff(32, "", fb="78")
    cid = "beschaffungsantrag-k32"
    ks = kstb(32, "78")
    its = items(("Notizblock A5, 50 Blatt, Uni-Design mit Fachbereichslogo, 500 Stück", 1, "560.00"), ("Präsentationsmappe DIN A4, 2 Klappen, Uni-Design, 300 Stück", 1, "585.00"), ("Visitenkarten Querformat, deutsch/englisch, je 250 Stück", 4, "38.50"))
    net, vv, gross = calc(its)
    d = "2027-03-17"
    cart = wps_cart("rv", "WK-0027-11874", d, "Web-to-Print-Shop Hochschul-Druckerzeugnisse (Rahmenvertrag Druckerei)", "Kartenwerk Druck GmbH, Göttingen", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="W2P", notes=["Druckdaten aus der Shop-Vorlage (Corporate Design). Lieferung ca. 8 Werktage."])
    antrag = zb3("ZB-2027-0188", d, p, ks, "Verbrauchsmaterial", True, "Abruf aus Rahmenvertrag (Web-to-Print-Shop) über WPS", 0, "Kartenwerk Druck GmbH, Göttingen", its,
                 ["Notizblöcke, Mappen und Visitenkarten für den Fachbereich im Corporate Design. Die Artikel stammen aus dem Web-to-Print-Shop des Rahmenvertrags; Vergleichsangebote entfallen. Bestellung über WPS."], mfmt="de")
    begr = (f"Druckprodukte über {money(net)} netto aus dem Web-to-Print-Shop des Rahmenvertrags, bestellt über WPS (Warenkorb WK-0027-11874); Rahmenvertragsprodukte werden ohne Vergleichsangebote beschafft. Antrag und Warenkorb nennen dieselben Positionen, die Kostenstellenbevollmächtigte hat beauftragt.")
    case(PROC, cid, [doc("scan_0001.pdf", antrag, jitter=0.9, producer="Canon iR-ADV Scan"), doc("scan_0002.pdf", cart, font="Helvetica", jitter=0.6)], begr, "ZB-3 als Scan (Zeilenversatz) + WPS-Warenkorb Web-to-Print-Shop; neutrale Namen scan_0001/scan_0002",
         "Web-to-Print-Rahmenvertrag über 1.299 € netto ohne Angebote; „Eingeholte Angebote: 0“ auf dem Formular", P_RV, SRC_WEB + "; " + SRC_WEB2 + "; " + SRC_RV, "high")


def k33():
    p = staff(33, "Prof. Dr.", fb="79")
    cid = "beschaffungsantrag-k33"
    its = items(("Bürodrehstuhl Synchronmechanik, Netzrücken, Armlehnen 3D, schwarz", 6, "389.00"), ("Rollen Hartboden, Satz à 5 Stück", 6, "14.90"))
    net, vv, gross = calc(its)
    d = "2027-08-02"
    cart = wps_cart("rv", "WK-0027-23560", d, "Rahmenvertrag Bürodrehstühle der hessischen Hochschulen", "Sitzwerk Stein GmbH, Steyerbach", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="SW", notes=["Mindestbestellwert erfüllt. Lieferung frei Verwendungsstelle."])
    mail = order_mail(p, "Bestellung Bürodrehstühle über WPS (WK-0027-23560)", "beschaffung@uni-wernstadt.de", None, f"{wd(d)} 16:05", [f"als Kostenstellenbevollmächtigte beauftrage ich hiermit die Bestellung von sechs Bürodrehstühlen aus dem Rahmenvertrag (WPS-Warenkorb WK-0027-23560, {money(net)} netto).",
                                                                                                                                      "Die Stühle ersetzen die Arbeitsplatzstühle im Raum 3.12 (Doktorandenbüro). Aufgrund des Rahmenvertrags wurden keine weiteren Angebote eingeholt."],
                      sig=[p["name"], "Kostenstellenbevollmächtigte " + p["ks"]])
    begr = (f"Sechs Bürodrehstühle über {money(net)} netto aus dem Rahmenvertrag für Bürodrehstühle, gebucht über WPS; dort sind keine Vergleichsangebote nötig. Die Professur ist selbst Kostenstellenbevollmächtigte und beauftragt in der Mail.")
    case(PROC, cid, [doc("wps.pdf", cart, font="Helvetica"), doc("bestellung.pdf", mail, font="Helvetica")], begr, "WPS-Warenkorb (Stuhlrahmenvertrag) + Mail der Kostenstellenbevollmächtigten selbst (kein Cc)", "Besteller:in = Kostenstellenbevollmächtigte (keine zweite Person); 2.334 € + 89,40 € netto ohne Angebote", P_RV + " " + P_KSB, SRC_RV + "; " + SRC_BESCH, "high")


def k34():
    p = staff(34, "Dr.", fb="72")
    cid = "beschaffungsantrag-k34"
    ks = kstb(34, "72")
    its = items(("Argon 4.6, 50-l-Flasche (Füllung 10 m³)", 8, "71.40"), ("Schweißgas Argon/CO₂ 82/18".replace("₂", "2") + ", 50-l-Flasche", 6, "64.80"), ("Flaschenmiete 12 Monate (je Flasche)", 14, "18.50"))
    net, vv, gross = calc(its)
    assert net == D("1219.00")
    d = "2027-09-07"
    cart = wps_cart("rv", "WK-0027-27011", d, "Rahmenvertrag Flaschengase (außer Helium)", "Gase-Kontor Lindner GmbH, Pullheim", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="FG",
                    notes=["Helium ist nicht Bestandteil dieses Warenkorbs (separater Rahmenvertrag, nicht bestellt)."])
    antrag = zb3("ZB-2027-0602", d, p, ks, "Verbrauchsmaterial", True, "Abruf aus Rahmenvertrag Flaschengase über WPS (Warenkorb WK-0027-27011)", 0, "Gase-Kontor Lindner GmbH", its, ["Schutzgas für die Schweiß- und Versuchsanlagen. Alle Gase sind Rahmenvertragsprodukte (Katalog Flaschengase) und werden über WPS bestellt; Vergleichsangebote entfallen."], mfmt="de", cat_row=True)
    begr = (f"Argon und Argon/CO2 samt Flaschenmiete ({money(net)} netto, über 1.000 €) sind Produkte des Rahmenvertrags Flaschengase und wurden im WPS-Katalog bestellt; Rahmenvertragsprodukte sind dort zu bestellen, ohne Vergleichsangebote. Antrag, Warenkorb und Summe stimmen überein; Helium ist nicht enthalten.")
    case(PROC, cid, [doc("beschaffungsantrag.pdf", antrag, font="Courier"), doc("wps-warenkorb.pdf", cart, font="Helvetica")], begr, "ZB-3 (Rahmenvertrag ja, 0 Angebote) + WPS-Warenkorb Katalog Flaschengase", "Flaschengase 1.219 € netto ohne drei Angebote, weil im WPS-Katalog Rahmenvertrag Flaschengase; Negation „Helium nicht enthalten“",
         "„Die Rahmenvertragsprodukte sind im WPS-System unter dem Katalog Rahmenvertrag Flaschengase gelistet und müssen hierüber bestellt werden.“", SRC_RV, "high")


def k35():
    p = staff(35, "Prof. Dr.", fb="79")
    cid = "beschaffungsantrag-k35"
    its = items(("Schreibtisch höhenverstellbar elektrisch, 160 × 80 cm, Dekor Ahorn", 4, "689.00"), ("Rollcontainer 3 Schübe, abschließbar, Dekor Ahorn", 4, "218.00"))
    net, vv, gross = calc(its)
    d1 = "2027-07-05"
    bv = vendor(50, "move")
    angebot = "\n".join([lr("Raumkonzept Bader GmbH · Beratung für den Rahmenvertragspartner Kranz + Ruppert Büromöbel", "", 100), lr("", f"{bv['street']} · {bv['plz']} {bv['city']}", 100), "", UW, p["org_long"], f"z. Hd. {p['name']}", "", lr("Angebot AN-27-3302", f"Datum {de(d1)}", 100),
                         "Lieferant: Kranz + Ruppert Büromöbel (Rahmenvertragspartner Büromöbel), Beratung und Angebotserstellung: Raumkonzept Bader", ""] + item_lines(its, [54, 6, 15, 15], "lrrr", "de", pos=False) +
                        ["", lr("", f"Summe netto  {money(net)}", 100), lr("", f"zzgl. 19 % USt.  {money(vv)}", 100), lr("", f"Angebotssumme brutto  {money(gross)}", 100), "", "Nach Ihrer Rückmeldung wird das Angebot in den WPS-Artikellisten des Rahmenvertragspartners eingestellt."])
    ruck = owa_mail(p["email"].split("@")[0], "AW: Angebot AN-27-3302 Büromöbel", f"{p['plain']} <{p['email']}>", f"{wd(addday(d1, 2))} 08:50", "Raumkonzept Bader GmbH <beratung@raumkonzept-bader.example>", ["Sehr geehrter Herr Bader,", "", "das Angebot AN-27-3302 vom " + de(d1) + " ist so in Ordnung. Bitte stellen Sie es für die Bestellung im WPS ein.", "", "Mit freundlichen Grüßen", p["plain"]])
    cart = wps_cart("rv", "WK-0027-24905", addday(d1, 6), "Rahmenvertrag Büromöbel · Artikelliste Kranz + Ruppert (Angebot AN-27-3302)", "Kranz + Ruppert Büromöbel, Karbach", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="KR-AL", status="Angebot in Artikelliste eingestellt, zur Bestellung")
    mail = order_mail(p, "Bestellung Büromöbel über WPS (Artikelliste), WK-0027-24905", "beschaffung@uni-wernstadt.de", None, f"{wd(addday(d1, 6))} 10:12", [f"das Angebot AN-27-3302 (Rahmenvertragspartner Büromöbel, {money(net)} netto) wurde nach meiner Rückmeldung in der WPS-Artikelliste eingestellt; die Bestellung buche ich über Warenkorb WK-0027-24905.",
                                                                                                                                                   "Gemäß Rahmenvertrag entfallen weitere Vergleichsangebote. Ich beauftrage die Bestellung als Kostenstellenbevollmächtigte."], sig=[p["name"]])
    begr = (f"Büromöbel ({money(net)} netto) gehören zum Rahmenvertrag Büromöbel; der vorgeschriebene Ablauf ist eingehalten: Angebot der beratenden Firma für den Rahmenvertragspartner, Rückmeldung ‚in Ordnung‘, Einstellen in die WPS-Artikelliste, Bestellung über WPS. Vergleichsangebote entfallen, die Professur beauftragt selbst.")
    case(PROC, cid, [doc("angebot-bueromoebel.pdf", angebot), doc("rueckmeldung.pdf", ruck, font="Helvetica"), doc("wps-artikelliste.pdf", cart, font="Helvetica"), doc("bestellmail.pdf", mail, font="Helvetica")], begr, "Möbel-Rahmenvertrag: Beratungsangebot + Rückmeldungsmail + WPS-Artikelliste + Bestellmail",
         "Ein einziges Angebot (kein Preisvergleich), weil Rahmenvertragsprozess Büromöbel: Angebot -> Rückmeldung -> Einstellen in WPS-Artikelliste", "„Nachdem Sie von der Firma Büro & Wohn Design ein schriftliches Angebot erhalten haben, müssen Sie an die Firma Büro & Wohn Design eine Rückmeldung geben, dass das Angebot so in Ordnung ist. Daraufhin wird Ihnen das Angebot für die Bestellung im WPS-System unter dem Rahmenvertragspartner König + Neurath \"Artikellisten\" eingestellt und Sie können die Bestellung über das WPS-System buchen.“", SRC_RV, "medium")


def k36():
    p = staff(36, "", fb="76")
    cid = "beschaffungsantrag-k36"
    ks = kstb(36, "76")
    its = items(("Petrischalen 94 × 16 mm, steril, VE 500", 2, "89.00"), ("Impfösen Einmal 10 µl, VE 1000", 3, "34.00"), ("Kulturmedium LB-Agar, 500 g", 2, "58.50"), ("Parafilm M, Rolle 38 m", 4, "21.50"), ("Desinfektionsmittel Flächen, 5 l", 3, "27.50"))
    net, vv, gross = calc(its)
    d = "2027-05-27"
    v = vendor(23, "lab")
    ang = offer_doc("letter", v, BUYER(p), "DW-A-7751", addday(d, -6), addday(d, 24), its, mfmt="de", foot=["Lieferung frei Haus ab 250,00 € Warenwert."], ref="Verbrauchsmaterial Mikrobiologie")
    mail = order_mail(p, "Direktauftrag Laborverbrauchsmaterial Mikrobiologie", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 09:40", [f"für das Praktikum bitte ich um Bestellung bei {v['name']} gemäß beiliegendem Angebot DW-A-7751:", ""] +
                      [f"   {i['qty']} × {i['desc']}, je {money(i['unit'])} netto" for i in its] + ["", f"Summe {money(net)} netto, {money(gross)} brutto. Da der Auftragswert unter 1.000 € liegt, habe ich nur dieses eine Angebot eingeholt (Direktvergabe).", f"Kostenstelle {p['ks']}, Auftrag {p['auftrag']}. {ks} ist in Kopie und hat die Bestellung beauftragt."])
    assert gross < D("1000")
    begr = (f"Direktvergabe: Der Auftragswert liegt mit {money(net)} netto ({money(gross)} brutto) unter 1.000 €, daher genügt das eine Angebot; die Mail und das Angebot nennen dieselben Positionen und Summen. Verbrauchsmaterial ohne Rahmenvertrag, die Kostenstellenbevollmächtigte hat in Kopie beauftragt.")
    case(PROC, cid, [doc("email-direktauftrag.pdf", mail, font="Helvetica"), doc("angebot.pdf", ang)], begr, "Bestellmail (Direktvergabe) + ein Angebot im Briefformat", "Nur ein Angebot, weil unter 1.000 €; Fünf Positionen mit Staffel-/Packungsgrößen im Text („VE 500“)", P_DIR + " " + P_KSB, SRC_NC + "; " + SRC_BESCH, "high")


def k37():
    p = staff(37, "Dr.", fb="71")
    cid = "beschaffungsantrag-k37"
    ks = kstb(37, "71")
    lines = [("Temperatursensor PT1000, Dünnschicht, 5 Stück", 2, "14.20"), ("Operationsverstärker-Muster sortiert, 120 Teile", 1, "39.90"), ("Steckbrett 830 Kontakte", 4, "5.45"), ("Jumper-Kabel-Set 120 Stück", 3, "6.60"), ("Lötzinn bleifrei 1,0 mm, 250 g", 2, "21.90"),
             ("Widerstandssortiment E12, 1160 Stück", 2, "17.80"), ("Mikrocontroller-Entwicklungsboard (ARM, 32-bit)", 6, "11.90")]
    net_total = tot(*[q * D(u) for _, q, u in lines])
    gross = r2(net_total * D("1.19"))
    gross_lines = [(d_, q, r2(D(u) * D("1.19"))) for d_, q, u in lines]
    sumg = tot(*[q * g for _, q, g in gross_lines])
    d = "2027-02-16"
    v = vendor(27, "elec")
    shop = "\n".join([lr(f"{v['name']} · Online-Shop · Warenkorb", f"{datef(d, 'de')} 15:31", 100), "", "Ihr Warenkorb (7 Positionen)", row(["Artikel", "Anz.", "Einzelpreis inkl. USt.", "Summe"], [60, 5, 21, 12], "lrrr")] +
                     [row([d_, str(q), money(g, "bare"), money(q * g, "bare")], [60, 5, 21, 12], "lrrr") for d_, q, g in gross_lines] +
                     ["", lr("", f"Warenwert (inkl. 19 % USt.)  {money(sumg, 'de')}", 100), lr("", "Versand: kostenlos ab 59,00 €  0,00 €", 100), lr("", f"Gesamtsumme  {money(sumg, 'de')}", 100), "", "[Zur Kasse]   Sie sparen 7,40 € gegenüber dem Listenpreis · 118 Treuepunkte"])
    mail = order_mail(p, "Bitte bestellen: Elektronikbauteile Praktikum", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 15:50", [f"für das Elektronikpraktikum bitte ich um Bestellung des beiliegenden Warenkorbs bei {v['name']} (Katalogpreise, Gesamtsumme {money(sumg)} brutto, das entspricht ca. {money(net_total)} netto).",
                                                                                                                              f"Der Auftragswert liegt unter 1.000 €; ich habe daher kein weiteres Angebot eingeholt (Direktvergabe). Kostenstelle {p['ks']}, Auftrag {p['auftrag']}. {ks} hat die Bestellung beauftragt (in Kopie)."])
    assert sumg < D("1000")
    begr = (f"Direktvergabe unter 1.000 € ({money(sumg)} brutto, rund {money(net_total)} netto): Der Webshop-Warenkorb ist das Angebot, die Mail nennt Gesamtsumme und Lieferanten; Bauteile sind kein Rahmenvertragsprodukt. Beauftragt durch die Kostenstellenbevollmächtigte (Kopie). Fußnoten (Ersparnis, Treuepunkte) betreffen nicht die Bestellung.")
    case(PROC, cid, [doc("bestellmail.pdf", mail, font="Helvetica"), doc("warenkorb-shop.pdf", shop, font="Helvetica")], begr, "Bestellmail + Webshop-Warenkorb-Ausdruck (Preise inkl. USt.) eines Elektronikhändlers", "Kein formelles Angebot; Preise brutto; Fußzeile „Sie sparen 7,40 €“ und „118 Treuepunkte“ sind keine Beträge der Bestellung", P_DIR, SRC_NC + "; " + SRC_BESCH, "high")


def k38():
    p = staff(38, "Dr.", fb="73")
    cid = "beschaffungsantrag-k38"
    ks = kstb(38, "73")
    its = items(("Werkskalibrierung Analysenwaage 0,1 mg, mit Prüfprotokoll", 4, "142.00"), ("Anfahrt und Prüfgewichtsatz pauschal", 1, "85.00"))
    net, vv, gross = calc(its)
    d = "2027-10-11"
    v = vendor(31, "serv")
    ang = offer_doc("table", v, BUYER(p), "KD-27-0882", addday(d, -9), addday(d, 21), its, mfmt="de", foot=["Kalibrierung vor Ort, Dauer ca. 1 Tag. Keine Rücknahme der Geräte nötig."], ref="Kalibrierung Waagen")
    mail = order_mail(p, "Auftrag Kalibrierung Analysenwaagen (Direktvergabe)", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 13:05", [f"bitte beauftragen Sie die Kalibrierung unserer vier Analysenwaagen bei {v['name']} laut Angebot KD-27-0882 ({money(net)} netto, {money(gross)} brutto).",
                                                                                                                                       "Es besteht kein Rahmenvertrag für diese Leistung. Da der Auftragswert unter 1.000 € liegt, ist eine Direktvergabe möglich; ein weiteres Angebot wurde nicht eingeholt.", f"Kostenstelle {p['ks']}, Auftrag {p['auftrag']}. Beauftragt von {ks} (Kopie)."])
    assert gross < D("1000")
    begr = (f"Dienstleistungsauftrag über {money(net)} netto ({money(gross)} brutto) unter 1.000 €: Direktvergabe mit einem Angebot ist möglich. Kein Rahmenvertrag, Angebot und Mail stimmen in Positionen und Summe überein, die Kostenstellenbevollmächtigte hat in Kopie beauftragt.")
    case(PROC, cid, [doc("auftrag-kalibrierung.pdf", mail, font="Helvetica"), doc("angebot-kalibrierdienst.pdf", ang, font="Helvetica")], begr, "Auftragsmail (Dienstleistung) + Angebot im Tabellenformat", "Dienstleistung statt Ware, Direktvergabe unter 1.000 €; „kein Rahmenvertrag“ ausdrücklich verneint", P_DIR, SRC_NC + "; " + SRC_BESCH, "high")


def shop_cart(v, d, tm, lines_net, extra_foot=None, free_ship=59, gross_prices=True):
    """web-shop cart with prices incl. VAT; returns (text, gross_sum)"""
    gl = [(d_, q, r2(D(u) * D("1.19"))) for d_, q, u in lines_net]
    sumg = tot(*[q * g for _, q, g in gl])
    L = [lr(f"{v['name']} · Online-Shop · Warenkorb", f"{datef(d, 'de')} {tm}", 104), "", f"Ihr Warenkorb ({len(gl)} Positionen)", row(["Artikel", "Anz.", "Einzelpreis inkl. USt.", "Summe"], [62, 5, 21, 12], "lrrr")]
    L += [row([d_, str(q), money(g, "bare"), money(q * g, "bare")], [62, 5, 21, 12], "lrrr") for d_, q, g in gl]
    L += ["", lr("", f"Warenwert inkl. 19 % USt.  {money(sumg)}", 104), lr("", f"Versand (frei ab {free_ship},00 €)  {money(D('0'))}", 104), lr("", f"Gesamtsumme  {money(sumg)}", 104), ""] + (extra_foot or []) + ["[Zur Kasse]"]
    return "\n".join(L), sumg


def k39():
    p = staff(39, "Dr.", fb="72")
    cid = "beschaffungsantrag-k39"
    ks = kstb(39, "72")
    specs = [(["DAkkS-Kalibrierung Druckaufnehmer 0–16 bar (mit Kalibrierschein)", "Kalibrierung Druckmessumformer 0 bis 16 bar, akkreditiert, inkl. Schein", "Akkreditierte Kalibrierung Drucksensor 0-16 bar mit Zertifikat"], 12), (["Hin- und Rückversand, versichert", "Transport hin und zurück inkl. Versicherung", "Versicherter Versand (beide Richtungen)"], 1)]
    prices = [["245.00", "238.00", "259.00"], ["85.00", "95.00", "70.00"]]
    d0 = "2027-04-12"
    docs3, summ, its3, vs = offers_pack(p, [6, 12, 18], "serv", d0, specs, prices, ["table", "letter", "mail"], mfmts=("de", "de", "eur"), dfmts=("de", "de", "de"), names=["angebot-a.pdf", "angebot-b.pdf", "angebot-c.pdf"], ref="Kalibrierung Druckaufnehmer", subj="Kalibrierung Druckaufnehmer")
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-04-23"
    antrag = zb3("ZB-2027-0302", reqd, p, ks, "Dienstleistung", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its, ["Jährliche Kalibrierung der zwölf Druckaufnehmer des Strömungskanals. Drei akkreditierte Dienstleister wurden angefragt; das gewählte Angebot ist bei gleichem Leistungsumfang das günstigste."])
    vm = owa_mail(ks.split()[-1].lower(), f"AW: Kalibrierung Druckaufnehmer, Zuschlag", f"{ks} <{ks.split()[-1].lower()}@uni-wernstadt.de>", f"{wd(addday(reqd, 1))} 08:30", p["name"],
                  ["Sehr geehrte Frau/Herr " + p["last"] + ",", "", f"ich habe die drei Angebote geprüft ({'; '.join(s[1] + ' ' + money(s[3]) + ' netto' for s in summ)}). Alle erfüllen die Anforderungen (akkreditierte Kalibrierung, Schein). Den Zuschlag erhält das preislich günstigste Angebot {summ[c][1]} ({summ[c][0]}).", "Bitte bestellen Sie dort. Ich beauftrage die Bestellung hiermit.", "", ks])
    begr = (f"Dienstleistung über {money(summ[c][3])} netto mit drei Angeboten ({', '.join(money(s[3]) for s in summ)} netto); beantragt ist das günstigste, der Zuschlag steht in der Mail der Kostenstellenbevollmächtigten, die damit auch beauftragt. Kein Rahmenvertrag für Kalibrierungen.")
    case(PROC, cid, [doc("antrag.pdf", antrag)] + docs3 + [doc("zuschlag-email.pdf", vm, font="Helvetica")], begr, "ZB-3 (Kategorie Dienstleistung) + drei Angebote (Tabelle, Brief, Mail) + Zuschlag per Mail der Kostenstellenbevollmächtigten",
         "Dienstleistung; Zuschlag und Beauftragung nur per Mail statt Vergabevermerk; Angebote mit unterschiedlichen Positionsbezeichnungen", P3 + " " + P_KSB, SRC_BESCH, "high")


def k40():
    p = staff(40, "Prof. Dr.", fb="73")
    cid = "beschaffungsantrag-k40"
    ks = p["name"]
    specs = [(["Praktikumsmikroskop Durchlicht, Trinokular, Planachromate 4×/10×/40×/100×, LED", "Durchlichtmikroskop trinokular, 4 Planachromate, LED-Kollektor", "Labormikroskop Durchlicht, Trinokulartubus, Plan-Achromate 4x–100x, LED"], 6),
             (["Kameraaufsatz C-Mount 5 MP, USB 3", "C-Mount-Kamera 5 Megapixel, USB 3.0", "USB-3-Kamera 5 MP mit C-Mount-Adapter"], 6)]
    prices = [["3120.00", "3250.00", "3100.00"], ["310.00", "295.00", "340.00"]]
    d0 = "2027-03-08"
    docs3, summ, its3, vs = offers_pack(p, [7, 13, 19], "mess", d0, specs, prices, ["letter", "table", "web"], mfmts=("de", "de", "de"), dfmts=("de", "de", "long"), names=["angebot-1.pdf", "angebot-2.pdf", "angebot-3.pdf"], ref="Aufforderung zur Angebotsabgabe vom 01.03.2027")
    c = cheapest(summ)
    its = its3[c]
    net, vv, gross = calc(its)
    assert net < D("50000")
    reqd = "2027-03-22"
    auff = "\n".join([f"{UW} · Zentrale Materialwirtschaft", "Vordruck: Aufforderung zur Angebotsabgabe", "", f"Datum: {de('2027-03-01')}    Bedarfsstelle: {p['org_long']}    Ansprechpartner:in: {p['name']}, {p['tel']}", "",
                      "Wir fordern Sie auf, bis zum " + de("2027-03-12") + " ein schriftliches Angebot abzugeben für:", "   Praktikumsmikroskope mit Kameraaufsatz, 6 Arbeitsplätze (Lehre, Praktikum Optik)", "",
                      "Anlage: Leistungsanforderungen / Funktionalitäten", "  1. Durchlichtmikroskop, Trinokulartubus, LED-Beleuchtung, Köhler-Beleuchtung einstellbar", "  2. Objektive Planachromat 4×, 10×, 40× (Federung), 100× (Öl)", "  3. Kamera-Aufsatz mit C-Mount, mindestens 5 Megapixel, USB 3",
                      "  4. Lieferung frei Verwendungsstelle einschließlich Einweisung; Garantie mindestens 24 Monate", "  5. Keine zusätzlichen Versorgungsanschlüsse und kein Umbau erforderlich", "", "Der Zuschlag erfolgt auf das wirtschaftlichste Angebot, das alle Anforderungen erfüllt.", "", f"Unterschrift Bedarfsstelle: {p['name']}"])
    antrag = zb3("ZB-2027-0245", reqd, p, ks, "Anlage", False, "Gerätefondsverfahren: Aufforderung zur Angebotsabgabe, drei Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its,
                 ["Ausstattung des Praktikums Optik (6 Arbeitsplätze) aus Gerätefondsmitteln (QSL, Praktika); 3er-Auftrag 3004417 wurde über das SG IV D eingerichtet. Leistungsanforderungen festgelegt, drei vergleichbare Angebote auf dem Vordruck „Aufforderung zur Angebotsabgabe“ eingeholt.",
                  "Abstimmung mit Abt. V (Bau und Liegenschaften): nicht erforderlich, da keine besonderen Anschlüsse, Umbauten oder zusätzlicher Platzbedarf entstehen. Das Angebot " + summ[c][1] + " ist das günstigste."],
                 extra_rows=[("Finanzierung", "Gerätefondsverfahren / QSL-Mittel, 3er-Auftrag 3004417")])
    ver = vermerk("V-27-0166", "ZB-2027-0245", addday(reqd, 1), "Praktikumsmikroskope (6 Stück) mit Kameraaufsatz", "Gerätefondsverfahren: Angebotseinholung durch die Bedarfsstelle (Auftragswert bis 50.000 € netto)", "Preis (netto), bei Erfüllung aller Leistungsanforderungen", summ, f"{summ[c][0]}, {money(summ[c][3])} netto",
                  "Alle drei Angebote erfüllen die Anforderungen der Aufforderung. Den Zuschlag erhält das wirtschaftlichste Angebot.")
    begr = (f"Gerätefondsverfahren bis 50.000 € netto: Leistungsanforderungen festgelegt, drei vergleichbare Angebote auf dem Vordruck „Aufforderung zur Angebotsabgabe“ ({', '.join(money(s[3]) for s in summ)} netto), das günstigste ({summ[c][1]}) hat den Zuschlag. 3er-Auftrag für QSL-Mittel eingerichtet, Abt. V nicht zu beteiligen. Kein IT-System. Die Professorin beauftragt selbst.")
    case(PROC, cid, [doc("antrag-zb3.pdf", antrag), doc("aufforderung-zur-angebotsabgabe.pdf", auff, font="Helvetica")] + docs3 + [doc("vergabevermerk.pdf", ver, font="Helvetica")], begr,
         "Gerätefonds: ZB-3 + Vordruck „Aufforderung zur Angebotsabgabe“ mit Leistungsanforderungen + drei Angebote (Brief, Tabelle, Web) + Vergabevermerk", "20.580 € netto (Gerätefondsverfahren bis 50.000 €); 3er-Auftrag für QSL-Mittel, Abstimmung mit Abt. V verneint (keine Sonderanschlüsse)",
         "„Auf dieser Grundlage sind mind. drei vergleichbare Angebote einzuholen“; „für die Angebotseinholung wird der Vordruck „Aufforderung zur Angebotsabgabe“ verwendet“", SRC_GF + "; " + SRC_BESCH, "medium")


def k41():
    p = staff(41, "Dr.", fb="77")
    cid = "beschaffungsantrag-k41"
    ks = kstb(41, "77")
    specs = [(["Klimaschrank 250 l, Temperatur 0–60 °C (ohne Feuchteregelung)", "Klimaschrank 250 l, Temperatur 0 bis 60 °C, Feuchte 10–90 % r. F. geregelt", "Klima-Prüfschrank 250 l, 0–60 °C, 10–90 % r. F., Befeuchtung und Entfeuchtung"], 1), (["Lieferung und Inbetriebnahme", "Lieferung, Aufstellung, Inbetriebnahme", "Lieferung und Inbetriebnahme mit Einweisung"], 1)]
    prices = [["3980.00", "4210.00", "4440.00"], ["140.00", "170.00", "150.00"]]
    d0 = "2027-06-07"
    docs3, summ, its3, vs = offers_pack(p, [8, 14, 20], "mess", d0, specs, prices, ["table", "letter", "web"], mfmts=("de", "de", "de"), dfmts=("de", "de", "de"), ref="Klimaschrank Pflanzenversuche")
    c = 1
    its = its3[c]
    reqd = "2027-06-18"
    antrag = zb3("ZB-2027-0444", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote; günstigstes Angebot erfüllt Anforderung nicht", 3, f"{summ[c][0]} ({summ[c][1]})", its,
                 ["Der Klimaschrank dient Keimungsversuchen bei geregelter Luftfeuchte. Pflichtanforderung: Feuchteregelung 10–90 % r. F. Das preislich günstigste Angebot (" + summ[0][1] + ") enthält nur eine Temperaturregelung und scheidet daher aus. Den Zuschlag erhält das günstigste Angebot, das alle Anforderungen erfüllt (" + summ[c][1] + ")."])
    ver = vermerk("V-27-0210", "ZB-2027-0444", addday(reqd, 1), "Klimaschrank 250 l mit Feuchteregelung", "Preisvergleich durch Einholung schriftlicher Angebote nach festgelegten Leistungsanforderungen", "Preis (netto) unter den Angeboten, die alle Pflichtanforderungen erfüllen", summ, f"{summ[c][0]}, {money(summ[c][3])} netto",
                  f"Das Angebot {summ[0][1]} ({money(summ[0][3])} netto) ist nicht vergleichbar: Das Gerät hat keine Feuchteregelung, die laut Aufforderung zwingend gefordert war, und wird von der Wertung ausgeschlossen. Von den beiden vergleichbaren Angeboten ist {summ[c][1]} das günstigere.")
    begr = (f"Drei Angebote wurden eingeholt; das billigste ({money(summ[0][3])} netto) erfüllt die vorab festgelegte Pflichtanforderung Feuchteregelung nicht und ist im Vergabevermerk begründet ausgeschlossen. Zuschlag an das günstigste vergleichbare Angebot ({summ[c][1]}, {money(summ[c][3])} netto). Antrag und Vermerk nennen dieselben Beträge.")
    case(PROC, cid, [doc("antrag.pdf", antrag)] + docs3 + [doc("vergabevermerk.pdf", ver, font="Helvetica")], begr, "ZB-3 + drei Angebote (Tabelle, Brief, Web) + Vergabevermerk mit begründetem Ausschluss des billigsten Angebots", "Gewählt wird NICHT das niedrigste Angebot: Pflichtanforderung (Feuchteregelung) fehlt dort; Begründung im Antrag und im Vermerk",
         "„1. Festlegung der geforderten Leistungsanforderungen / Funktionalitäten 2. Auf dieser Grundlage sind mind. drei vergleichbare Angebote einzuholen“", SRC_GF + "; " + SRC_BESCH, "medium")


def k42():
    p = staff(42, "Dr.", fb="73")
    cid = "beschaffungsantrag-k42"
    ks = kstb(42, "73")
    vA = dict(name="Optilab Instruments B.V.", street="Schiekade 120", plz="3033 AA", city="Rotterdam, The Netherlands", tel="+31 10 555 0142", mail="sales@optilab-instruments.example", web="www.optilab-instruments.example", vat="NL8120.44.977.B01", iban="NL28 XXXX 0123 4567 89", line="")
    vB = vendor(41, "mess")
    vC = dict(name="Spektrum Nordic ApS", street="Hvidovrevej 18", plz="2610", city="Rødovre, Denmark".replace("ø", "o"), tel="+45 35 55 01 20", mail="quote@spektrum-nordic.example", web="www.spektrum-nordic.example", vat="DK 3182 4477", iban="DK50 XXXX 0001 2345 67", line="")
    specs = [(["Compact spectrometer 200-1100 nm, 0.5 nm resolution, USB", "Kompaktspektrometer 200–1100 nm, 0,5 nm Auflösung, USB", "Compact UV-VIS spectrometer 200-1100 nm, 0.6 nm, USB"], 2), (["Fibre-optic probe set, 400 µm, 2 m", "Faseroptische Sonde 400 µm, 2 m, Set", "Fibre probe 400 um, 2 m"], 2), (["Calibration light source (deuterium-halogen)", "Kalibrierlichtquelle Deuterium-Halogen", "Deuterium-halogen calibration source"], 1)]
    prices = [["1980.00", "2150.00", "2050.00"], ["285.00", "270.00", "255.00"], ["560.00", "640.00", "590.00"]]
    d0 = "2027-07-12"
    its3 = three_offers(specs, prices)
    vats = (0, 19, 0)
    summ, docs3 = [], []
    for k, (v, sty, mf, df) in enumerate([(vA, "en", "en-eur", "us"), (vB, "letter", "de", "de"), (vC, "en", "eurplain", "dmy-en")]):
        date, nr = addday(d0, 2 * k), ["OLQ-2027-1180", "AN-27-5112", "SN-Q-27-0381"][k]
        txt = offer_doc(sty, v, BUYER(p), nr, date, addday(date, 45), its3[k], vats[k], mf, df, ["Delivery time 4-5 weeks after order."] if k != 1 else ["Lieferzeit ca. 5 Wochen."], ref="enquiry spectrometer")
        net, vv, gross = calc(its3[k], vats[k])
        summ.append((v["name"], nr, date, net, gross))
        docs3.append(doc(["quotation-optilab.pdf", "angebot-deutsch.pdf", "quote-spektrum.pdf"][k], txt, font="Helvetica" if sty == "en" else "Courier"))
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-07-23"
    antrag = zb3("ZB-2027-0488", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote (zwei aus dem EU-Ausland)", 3, f"{summ[c][0]} ({summ[c][1]})", its,
                 ["Zwei Spektrometer für das Praktikum Optische Messtechnik. Drei Angebote eingeholt (Niederlande, Deutschland, Dänemark); alle Angebote sind technisch gleichwertig, das gewählte Angebot ist netto das günstigste. Das Angebot ist eine innergemeinschaftliche Lieferung ohne ausgewiesene Umsatzsteuer; die Erwerbsbesteuerung übernimmt die Universität."],
                 vat=0, vat_note="zzgl. 0 % USt. (innergemeinschaftliche Lieferung)")
    ver = vermerk("V-27-0231", "ZB-2027-0488", addday(reqd, 1), "Zwei Kompaktspektrometer mit Zubehör", "Preisvergleich durch Einholung schriftlicher Angebote (Wertung netto)", "Preis (netto), bei gleicher technischer Eignung", summ, f"{summ[c][0]}, {money(summ[c][3])} netto",
                  "Alle Angebote erfüllen die Anforderungen. Verglichen werden die Nettopreise; zwei Angebote sind innergemeinschaftliche Lieferungen ohne Umsatzsteuer.")
    begr = (f"Drei Angebote ({', '.join(money(s[3]) for s in summ)} netto), zwei davon von EU-Anbietern auf Englisch ohne ausgewiesene USt (innergemeinschaftliche Lieferung); gewertet wird netto, das günstigste ({summ[c][1]}) hat den Zuschlag. Antrag, Vermerk und Angebot nennen {money(summ[c][3])} netto, brutto = netto, weil keine deutsche USt anfällt.")
    case(PROC, cid, [doc("antrag.pdf", antrag)] + docs3 + [doc("vermerk.pdf", ver, font="Helvetica")], begr, "ZB-3 + zwei englische Angebote aus dem EU-Ausland (Niederlande, Dänemark; 0 % USt) + ein deutsches Angebot + Vergabevermerk",
         "Englische Angebote, Formate „EUR 5,090.00“ und „EUR 5340.00“, 0 % USt innergemeinschaftlich (brutto = netto), Wertung netto", P3, SRC_BESCH, "medium")


def k43():
    p = staff(43, "Dr.", fb="76")
    cid = "beschaffungsantrag-k43"
    ks = kstb(43, "76")
    specs = [(["Laborautoklav 60 l, Frontlader, Programmsteuerung", "Autoklav 60 Liter Frontlader mit Programmen", "Dampfsterilisator 60 l, Frontbeladung, programmierbar"], 1), (["Zubehörkorb Edelstahl, 2 Stück", "Edelstahlkörbe (2 Stück)", "Einsatzkörbe Edelstahl, Satz 2"], 1)]
    prices = [["2890.00", "3010.00", "2955.00"], ["180.00", "165.00", "175.00"]]
    d0 = "2027-08-09"
    its3 = three_offers(specs, prices)
    vs = [vendor(24, "lab"), vendor(30, "lab"), vendor(36, "lab")]
    summ, docs = [], []
    for k in range(3):
        date, nr = addday(d0, k), ["2027-0912", "A/27/611", "Q-8851"][k]
        txt = offer_doc("letter" if k != 1 else "table", vs[k], BUYER(p), nr, date, addday(date, 30), its3[k], 19, "de", "de", ref="Autoklav")
        txt = f"EINGANG {datef(addday(date, 2), 'de')}   Zentrale Beschaffung   [Eingangsstempel]\n\n" + txt
        net, vv, gross = calc(its3[k])
        summ.append((vs[k]["name"], nr, date, net, gross))
        docs.append(doc(f"scan_000{k + 1}.pdf", txt, font="Courier" if k != 1 else "Helvetica", jitter=1.1, producer="Canon iR-ADV Scan"))
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-08-20"
    antrag = zb3("ZB-2027-0531", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its, ["Ersatz für den Autoklaven (Baujahr 2009, nicht mehr reparabel). Drei Angebote eingeholt, das gewählte ist das günstigste bei gleicher Ausstattung."])
    memo = "\n".join(["HANDSCHRIFTLICHER VERMERK (Scan)", "", f"Angebote verglichen am {de(addday(reqd, 1))}:", *[f"  {s[1]:<12} {s[0][:34]:<36} {money(s[3])} netto" for s in summ], "",
                     f"Zuschlag: {summ[c][0]}, Angebot {summ[c][1]}, {money(summ[c][3])} netto (günstigstes Angebot, alle gleichwertig).", "", f"{ks}  (Kostenstellenbevollmächtigte)  {de(addday(reqd, 1))}"])
    begr = (f"Gescannte Unterlagen: drei Angebote ({', '.join(money(s[3]) for s in summ)} netto), der Beschaffungsantrag für das günstigste ({summ[c][1]}) und ein handschriftlicher Vermerk mit demselben Zuschlag. Auftragswert über 1.000 €, kein Rahmenvertragsprodukt, Kostenstellenbevollmächtigte hat beauftragt.")
    case(PROC, cid, docs + [doc("scan_0004.pdf", antrag, jitter=1.0, producer="Canon iR-ADV Scan"), doc("scan_0005.pdf", memo, jitter=1.3, producer="Canon iR-ADV Scan")], begr, "Alles als Scan: drei Angebote mit Eingangsstempel, ZB-3 und handschriftlicher Vergabevermerk; Dateien scan_0001–scan_0005 ohne Hinweis auf Inhalt",
         "Neutrale Dateinamen, Zeilenversatz (Scan-Look), Eingangsstempel-Zeilen, Vermerk als handschriftlicher Text", P3 + " " + P_KSB, SRC_BESCH, "high")


def k44():
    p = staff(44, "Dr.", fb="71")
    cid = "beschaffungsantrag-k44"
    ks = kstb(44, "71")
    specs = [(["Datenerfassungssystem 16 Kanäle, 24 Bit, Ethernet, Messsoftware inklusive", "Mess-Datenlogger 16 Kanäle, 24-Bit-ADC, LAN, mit Software", "Multikanal-Erfassungssystem 16 Ch., 24 Bit, Ethernet, inkl. Software"], 1), (["Thermoelement-Eingangsmodul, 8 Kanäle", "Modul 8 Thermoelement-Eingänge", "8-Kanal-Thermoelementmodul"], 2)]
    prices = [["2890.00", "2760.00", "2975.00"], ["410.00", "445.00", "395.00"]]
    d0 = "2027-09-13"
    docs3, summ, its3, vs = offers_pack(p, [9, 15, 22], "elec", d0, specs, prices, ["letter", "web", "table"], mfmts=("de", "de", "de"), dfmts=("de", "iso", "de"), ref="Datenerfassung Projekt SensorNetz")
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-09-24"
    antrag = zb3("ZB-2027-0610", reqd, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote (Drittmittelprojekt)", 3, f"{summ[c][0]} ({summ[c][1]})", its,
                 ["Messtechnik für das Verbundprojekt SensorNetz (Arbeitspaket 2). Finanzierung aus Drittmitteln; der Bewilligungsbescheid enthält keine von der Beschaffungsordnung abweichenden Vergabevorgaben (Auszug anbei). Es gelten daher die üblichen Regeln: drei Angebote, günstigstes gewählt."],
                 extra_rows=[("Mittelherkunft", "Drittmittel Auftrag " + p["dr_auftrag"] + " (Projekt SensorNetz)")])
    bb = "\n".join(["Auszug aus dem Bewilligungsbescheid (Projekt SensorNetz, Zuwendungsgeber: Bundesministerium, Förderkennzeichen 03SN1234)", "", "Nr. 3  Bewilligte Ausgaben: Sachmittel für Messtechnik bis zur Höhe von 6.000,00 € (Gesamtansatz).", "Nr. 5  Vergabe: Bei der Vergabe von Aufträgen sind die haushaltsrechtlichen Bestimmungen der Hochschule zu beachten; weitergehende oder abweichende Wertgrenzen werden durch diesen Bescheid nicht festgelegt.",
                    "Nr. 7  Die Zweckbindung der beschafften Gegenstände beträgt drei Jahre."])
    begr = (f"Drittmittelbeschaffung nach denselben Regeln wie Landesmittel: drei Angebote ({', '.join(money(s[3]) for s in summ)} netto), günstigstes gewählt, Bewilligungsbescheid (Auszug) enthält keine strengeren Vergabevorgaben. Der Gesamtansatz 6.000 € im Bescheid deckt die {money(summ[c][3])} netto. Beauftragt durch die Kostenstellenbevollmächtigte.")
    case(PROC, cid, [doc("beschaffungsantrag.pdf", antrag)] + docs3 + [doc("bescheid-auszug.pdf", bb, font="Helvetica")], begr, "ZB-3 mit Drittmittel-Auftrag (6-…) + drei Angebote (Brief, Web mit ISO-Datum, Tabelle) + Auszug aus dem Bewilligungsbescheid", "Drittmittelprojekt: Bescheid-Auszug mit Betragsgrenze 6.000 € (gedeckt) und ohne abweichende Vergabewerte; Zweckbindung drei Jahre erwähnt",
         "„Die Beschaffung von Geräten und Verbrauchsmaterialien aus Drittmitteln unterliegt grundsätzlich den gleichen Regeln wie die Beschaffung aus dem vom Land bereitgestellten Budget. Sofern ein Drittmittelgeber eigene Vorgaben zu diesem Themenkreis macht, gelten immer die strengeren Regelungen.“", SRC_DM + "; " + SRC_BESCH, "medium")
    assert summ[c][3] < D("6000")


def k45():
    p = staff(45, "", fb="74")
    cid = "beschaffungsantrag-k45"
    ks = kstb(45, "74")
    d = "2027-05-04"
    vA, vB = vendor(25, "werk"), vendor(35, "lab")
    la = [("Schutzbrille klar, EN 166, Überbrille", 8, "4.90"), ("Gehörschutz-Kapseln SNR 28", 4, "9.50"), ("Schnittschutzhandschuhe Gr. 9, Paar", 6, "7.20"), ("Messschieber digital 150 mm", 2, "18.90")]
    lb = [("Probenbehälter PP 250 ml, VE 100", 3, "31.50"), ("Etikettenband beschreibbar, 3 Rollen", 4, "6.80"), ("Cutter-Messer Ersatzklingen, 10er", 5, "3.40")]
    ta, ga = shop_cart(vA, d, "10:02", la, ["Ihre Ersparnis: 6,20 €. Mit Ihrer Bestellung sammeln Sie 74 Bonuspunkte."])
    tb, gb = shop_cart(vB, d, "10:11", lb, ["Pfand/Verpackung: keine Kosten."])
    total = ga + gb
    assert total < D("1000")
    mail = order_mail(p, "Sammelbestellung Werkstatt und Labor (zwei Händler)", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 10:30", [f"bitte bestellen Sie die folgenden Positionen für Werkstatt und Praktikumslabor bei zwei Händlern (Warenkörbe anbei, Preise brutto):", "",
                                                                                                                                       f"  {vA['name']}: Schutzbrillen (8), Gehörschutz (4), Schnittschutzhandschuhe (6), Messschieber (2): {money(ga)}", f"  {vB['name']}: Probenbehälter (3 x 100), Etikettenband (4), Ersatzklingen (5): {money(gb)}", "",
                                                                                                                                       f"Gesamt {money(total)} brutto; je Händler liegt der Auftragswert unter 1.000 €, daher Direktvergabe ohne weitere Angebote. Kein Rahmenvertragsprodukt (weder Büromaterial noch IT).", f"Kostenstelle {p['ks']}, Auftrag {p['auftrag']}; {ks} ist in Kopie und hat beauftragt."])
    begr = (f"Sammelbestellung bei zwei Händlern mit {money(ga)} und {money(gb)} brutto, zusammen {money(total)} brutto und damit insgesamt unter 1.000 €: Direktvergabe ohne weitere Angebote. Die Warenkörbe belegen die Positionen und Preise, nichts davon ist Rahmenvertragsware, die Kostenstellenbevollmächtigte hat in Kopie beauftragt. Bonuspunkte und Ersparnis sind Werbung.")
    case(PROC, cid, [doc("sammelbestellung-email.pdf", mail, font="Helvetica"), doc("warenkorb-1.pdf", ta, font="Helvetica"), doc("warenkorb-2.pdf", tb, font="Helvetica")], begr, "Sammelbestellung per Mail mit zwei Webshop-Warenkörben (Preise brutto)", "Sieben Positionen bei zwei Händlern, jeder und die Summe unter 1.000 €; Werbezeilen („Ersparnis 6,20 €“, „74 Bonuspunkte“); „keine Kosten“ bei Verpackung", P_DIR, SRC_NC + "; " + SRC_BESCH, "high")


def k46():
    p = staff(46, "Dr.", fb="72")
    h = staff(146, "", fb="72")
    cid = "beschaffungsantrag-k46"
    ks = kstb(46, "72")
    its = items(("Tragbarer Rechner 14 Zoll, 16 GB RAM, 512 GB SSD, Vertragskonfiguration B", 2, "1090.00"), ("Dockingstation USB-C, 100 W", 2, "129.90"), ("Monitor 24 Zoll, FHD, höhenverstellbar", 2, "154.00"))
    net, vv, gross = calc(its)
    d = "2027-10-19"
    cart = wps_cart("rv", "WK-0027-33118", d, "Rahmenvertrag IT-Arbeitsplatzgeräte der hessischen Hochschulen, Los 1 und 2", "Systemhaus Hellweg GmbH, Offenbach", p["name"], f"{p['ks']} / Auftrag {p['auftrag']}", its, art_prefix="RV-IT", status="bestellt (Funktion Ersteller – Besteller)",
                    extra=[("Ersteller:in (Warenkorb zusammengestellt)", h["plain"] + " (Mitarbeiter:in, WPS-Ersteller)")], notes=["Der Warenkorb wurde von der Ersteller:in zusammengestellt und von der bestellberechtigten Person mit SAP-Zugang freigegeben und bestellt."])
    mail = order_mail(p, "Bestellung WPS WK-0027-33118 (Ersteller – Besteller)", "beschaffung@uni-wernstadt.de", f"{h['plain']}; {ks}", f"{wd(d)} 15:22", [f"{h['plain']} hat im WPS (Funktion Ersteller – Besteller) den Warenkorb WK-0027-33118 mit zwei Notebooks, zwei Docks und zwei Monitoren aus dem IT-Rahmenvertrag zusammengestellt ({money(net)} netto). Ich habe als bestellberechtigte Person mit SAP-Zugang bestellt.",
                                                                                                                                  "Es handelt sich um Rahmenvertragsprodukte; Vergleichsangebote entfallen. Kostenstellenbevollmächtigte: " + ks + " (Kopie, beauftragt)."])
    begr = (f"Rahmenvertragsartikel ({money(net)} netto) wurden von einer Ersteller:in im WPS zusammengestellt und von einer bestellberechtigten Person mit SAP-Zugang bestellt (Funktion Ersteller – Besteller); keine Vergleichsangebote nötig. Mail und Warenkorb stimmen überein, die Kostenstellenbevollmächtigte hat beauftragt.")
    case(PROC, cid, [doc("wps-erstellerbesteller.pdf", cart, font="Helvetica"), doc("mail.pdf", mail, font="Helvetica")], begr, "WPS-Warenkorb mit Rolle Ersteller/Besteller + Mail", "Zwei Personen im Prozess (Ersteller und Besteller) – kein Widerspruch; Rahmenvertrag IT ohne Angebote", P_RV, SRC_RV + "; " + SRC_EB, "high")


def k47():
    p = staff(47, "", fb="79")
    cid = "beschaffungsantrag-k47"
    ks = kstb(47, "79")
    d = "2027-01-26"
    its = items(("Kopier- und Druckpapier A4, 80 g/m², weiß, 5 × 500 Blatt (Karton)", 12, "24.90"), ("Kopier- und Druckpapier A3, 80 g/m², weiß, 5 × 500 Blatt (Karton)", 2, "48.60"))
    net, vv, gross = calc(its)
    cart = wps_cart("rv", "WK-0027-02207", d, "Rahmenvertrag Büro- und Kopierpapier (Rahmenvertrag der Zentralen Beschaffungsstelle)", "Papier-Kontor Hofmann GmbH, Hofheim", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="PK", notes=[f"Mindestbestellwert 50,00 € netto erfüllt (Warenwert {money(net)})."])
    vB = vendor(28, "buero")
    env = [("Briefhüllen DIN lang, ohne Fenster, 1000 Stück", 2, "17.40"), ("Versandtaschen C4, haftklebend, 250 Stück", 2, "14.50")]
    shop, sg = shop_cart(vB, d, "09:48", env, ["Hinweis der Besteller:in: für Briefhüllen und Versandtaschen besteht derzeit kein Rahmenvertrag; Preise wurden im Vergleich geprüft."], free_ship=75)
    mail = order_mail(p, "Papier (Rahmenvertrag, WPS) und Umschläge (Direktkauf)", "beschaffung@uni-wernstadt.de", ks, f"{wd(d)} 10:05", [f"1) Kopierpapier A4/A3: Bestellung über WPS aus dem Rahmenvertrag (Warenkorb WK-0027-02207, {money(net)} netto), keine Vergleichsangebote nötig.",
                                                                                                                                         f"2) Briefhüllen und Versandtaschen: dazu gibt es derzeit keinen Rahmenvertrag; ich bitte um Direktbestellung bei {vB['name']} laut Warenkorb ({money(sg)} brutto, unter 1.000 €).", f"Kostenstelle {p['ks']}; {ks} ist in Kopie und beauftragt."])
    assert sg < D("1000")
    begr = (f"Das Papier ({money(net)} netto) kommt aus dem Rahmenvertrag und wird über WPS bestellt (Mindestbestellwert 50 € erreicht); für Briefhüllen und Versandtaschen besteht kein Rahmenvertrag, sie werden mit {money(sg)} brutto (unter 1.000 €) direkt vergeben. Beide Teile sind in der Mail sauber getrennt und belegt.")
    case(PROC, cid, [doc("wps-papier.pdf", cart, font="Helvetica"), doc("shop-umschlaege.pdf", shop, font="Helvetica"), doc("mail.pdf", mail, font="Helvetica")], begr, "Gemischte Bestellung: Papier über WPS-Rahmenvertrag + Umschläge per Direktkauf unter 1.000 €; Mail trennt beides", "Rahmenvertragsteil und Nicht-Rahmenvertragsteil in einer Mail; Mindestbestellwert-Hinweis; „besteht derzeit kein Rahmenvertrag“ (Negation)", P_RV + " " + P_DIR, SRC_RV + "; " + SRC_NC, "high")


def k48():
    p = staff(48, "Prof. Dr.", fb="78")
    cid = "beschaffungsantrag-k48"
    its = items(("Holzschalenstuhl stapelbar, Buche, Sitzhöhe 46 cm (Seminarstuhl)", 30, "94.50"), ("Stuhlwagen für 12 Stühle", 2, "168.00"))
    net, vv, gross = calc(its)
    d = "2027-07-20"
    cart = wps_cart("rv", "WK-0027-25102", d, "Rahmenvertrag Seminarstühle / Holzschalenstühle der hessischen Hochschulen", "Sitzmöbel Maurer GmbH, Malsch", p["name"], f"{p['ks']} / {p['auftrag']}", its, art_prefix="SM", notes=["Bestellung gemäß Infoblatt des Rahmenvertragspartners für WPS-Bestellungen."])
    antrag = zb3("ZB-2027-0498", d, p, p["name"], "Verbrauchsmaterial", True, "Abruf aus Rahmenvertrag Seminarstühle über WPS (Warenkorb WK-0027-25102)", 0, "Sitzmöbel Maurer GmbH, Malsch", its, ["Ausstattung des Seminarraums 3.04 mit 30 Stühlen und zwei Stuhlwagen. Die Stühle sind Rahmenvertragsprodukte; Vergleichsangebote entfallen. Bestellung im WPS."], mfmt="de", cat_row=False)
    begr = (f"Seminarstühle und Stuhlwagen ({money(net)} netto) aus dem Rahmenvertrag Seminarstühle, gebucht im WPS; deshalb null Vergleichsangebote, wie es der Rahmenvertrag vorsieht. Antrag und Warenkorb sind deckungsgleich, die Professur ist Kostenstellenbevollmächtigte und beauftragt.")
    case(PROC, cid, [doc("antrag-zb3.pdf", antrag), doc("wps-cart.pdf", cart, font="Helvetica")], begr, "ZB-3 ohne Kategoriezeile (Rahmenvertrag ja, 0 Angebote) + WPS-Warenkorb Seminarstühle", "2.835 € + 336 € netto ohne Angebote; Kategoriezeile fehlt (Möbel, kein Gerät)", P_RV, SRC_RV, "high")


def k49():
    p = staff(49, "Dr.", fb="76")
    cid = "beschaffungsantrag-k49"
    ks = kstb(49, "76")
    specs = [(["Pipettenspitzen 200 µl, gestopft, steril, VE 960", "Filterspitzen 200 µl steril, Rack à 96 (10 Racks je VE)", "Pipettenspitzen 200 µl, Filter, steril, 960er-Pack"], 10), (["Nitril-Handschuhe Gr. S, puderfrei, VE 200", "Einmalhandschuhe Nitril S, Box 200 Stk.", "Nitrilhandschuhe S puderfrei, 200er-Box"], 30),
             (["Kryoröhrchen 2 ml, steril, VE 500", "Kryoröhrchen 2 ml, Außengewinde, steril, 500er-VE", "Kryogefäße 2 ml steril, VE 500"], 6)]
    prices = [["76.00", "71.50", "79.40"], ["8.60", "8.95", "8.40"], ["92.00", "88.40", "94.00"]]
    d0 = "2027-11-02"
    docs3, summ, its3, vs = offers_pack(p, [10, 16, 26], "lab", d0, specs, prices, ["en", "web", "letter"], mfmts=("en-eur", "de", "de"), dfmts=("en-short", "de", "de"), names=["quote-1.pdf", "angebot-online.pdf", "angebot-3.pdf"],
                                         foots=[[], [], ["Mengenstaffel: ab 20 Packungen 4 % Rabatt auf Positionen 1 und 3 (nicht berücksichtigt, Bestellmenge darunter)."]], ref="Verbrauchsmaterial Zellkultur")
    c = cheapest(summ)
    its = its3[c]
    reqd = "2027-11-12"
    antrag = zb3("ZB-2027-0701", reqd, p, ks, "Verbrauchsmaterial", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", its, ["Jahresbedarf an Verbrauchsmaterial für die Zellkultur. Drei Angebote eingeholt (eines auf Englisch), das gewählte ist das günstigste."])
    mail = owa_mail(ks.split()[-1].lower(), "Zuschlag Verbrauchsmaterial Zellkultur", f"{ks} <{ks.split()[-1].lower()}@uni-wernstadt.de>", f"{wd(addday(reqd, 1))} 12:00", "beschaffung@uni-wernstadt.de",
                    ["Sehr geehrte Damen und Herren,", "", f"zum Antrag ZB-2027-0701: Die drei Angebote ({'; '.join(s[1] + ' ' + money(s[3]) + ' netto' for s in summ)}) wurden verglichen. Den Zuschlag erhält {summ[c][0]} mit {money(summ[c][3])} netto als günstigstes Angebot. Ich beauftrage die Bestellung.", "", ks])
    begr = (f"Verbrauchsmaterial über {money(summ[c][3])} netto: drei Angebote ({', '.join(money(s[3]) for s in summ)} netto), das günstigste ({summ[c][1]}) ist beantragt und per Mail der Kostenstellenbevollmächtigten bestätigt. Die Mengenstaffel im Angebot 3 ist nicht erreicht und beeinflusst nichts.")
    case(PROC, cid, [doc("antrag.pdf", antrag)] + docs3 + [doc("zuschlag-mail.pdf", mail, font="Helvetica")], begr, "ZB-3 + drei Angebote (englisches Angebot, Web-Ausdruck, Brief mit Mengenstaffel) + Zuschlagsmail", "Fußnote mit Mengenrabatt 4 % (nicht erreicht); englisches Angebot mit Format „EUR 1,404.00“; Verbrauchsmaterial über 1.000 €", P3, SRC_BESCH, "high")


def k50():
    p = staff(50, "Prof. Dr.", fb="72")
    cid = "beschaffungsantrag-k50"
    ks = p["name"]
    itsA = items(("Tragbarer Rechner 14 Zoll, 16 GB RAM, 512 GB SSD, Vertragskonfiguration B", 1, "1090.00"), ("Dockingstation USB-C, 100 W", 1, "129.90"))
    dA = "2027-03-29"
    cartA = wps_cart("rv", "WK-0027-06741", dA, "Rahmenvertrag IT-Arbeitsplatzgeräte der hessischen Hochschulen, Los 1 und 2", "Systemhaus Hellweg GmbH, Offenbach", p["name"], f"{p['ks']} / {p['auftrag']}", itsA, art_prefix="RV-IT")
    antA = zb3("ZB-2027-0229", dA, p, ks, "Anlage", True, "Abruf aus Rahmenvertrag über WPS (Warenkorb WK-0027-06741)", 0, "Systemhaus Hellweg GmbH, Offenbach", itsA, ["Teil A der Anschaffung: ein Notebook mit Dockingstation für die neue wissenschaftliche Mitarbeiterin; Rahmenvertragsprodukte, bestellt im WPS."], mfmt="de")
    specs = [(["3D-Drucker FDM, Bauraum 300 × 300 × 400 mm, Doppelextruder, geschlossenes Gehäuse", "FDM-3D-Drucker 300x300x400 mm, 2 Extruder, Kammer geschlossen", "Filamentdrucker mit Einhausung, Bauvolumen 300 × 300 × 400 mm, Dual-Extruder"], 1), (["Starterpaket Filament (PETG und PLA, je 4 Rollen)", "Filament-Starterset PETG/PLA, 8 Rollen", "Materialpaket PETG + PLA, 8 Spulen"], 1)]
    prices = [["1790.00", "1640.00", "1710.00"], ["160.00", "185.00", "150.00"]]
    d0 = "2027-04-05"
    docs3, summ, its3, vs = offers_pack(p, [29, 34, 40], "werk", d0, specs, prices, ["table", "letter", "mail"], mfmts=("de", "de", "de"), dfmts=("de", "de", "de"), names=["angebot-3d-a.pdf", "angebot-3d-b.pdf", "angebot-3d-c.pdf"], ref="3D-Drucker Werkstatt", subj="3D-Drucker")
    c = cheapest(summ)
    itsB = its3[c]
    dB = "2027-04-14"
    antB = zb3("ZB-2027-0233", dB, p, ks, "Anlage", False, "Preisvergleich, drei schriftliche Angebote", 3, f"{summ[c][0]} ({summ[c][1]})", itsB, ["Teil B der Anschaffung: 3D-Drucker für die Prototypenwerkstatt; kein Rahmenvertragsprodukt. Drei Angebote eingeholt, das gewählte ist das günstigste. (Teil A: Notebook mit Dock, separater Antrag ZB-2027-0229 über WPS.)"])
    ver = vermerk("V-27-0140", "ZB-2027-0233", addday(dB, 1), "3D-Drucker FDM mit Materialpaket", "Preisvergleich durch Einholung schriftlicher Angebote", "Preis (netto), bei gleicher technischer Eignung", summ, f"{summ[c][0]}, {money(summ[c][3])} netto", "Alle Angebote erfüllen die Anforderungen; Zuschlag an das günstigste Angebot.")
    begr = (f"Zwei getrennte Anträge: Teil A (Notebook mit Dock, {money(calc(itsA)[0])} netto) ist Rahmenvertragsware über WPS ohne Angebote; Teil B (3D-Drucker, {money(summ[c][3])} netto) ist kein Rahmenvertragsprodukt und hat drei Angebote ({', '.join(money(s[3]) for s in summ)} netto) mit Vergabevermerk. Beides ist korrekt getrennt, die Professur beauftragt als Kostenstellenbevollmächtigte.")
    case(PROC, cid, [doc("antrag-a-rahmenvertrag.pdf", antA), doc("wps-warenkorb-a.pdf", cartA, font="Helvetica"), doc("antrag-b-3d-drucker.pdf", antB)] + docs3 + [doc("vergabevermerk-b.pdf", ver, font="Helvetica")], begr,
         "Zwei Anträge in einem Vorgang: Rahmenvertragsteil (WPS) und Wettbewerbsteil (3 Angebote: Tabelle, Brief, Mail)", "Beschaffung mischt Rahmenvertragsware (ohne Angebote) mit Nicht-Rahmenvertragsware (mit drei Angeboten) – jeweils korrekt getrennt", P_RV + " " + P3, SRC_RV + "; " + SRC_BESCH, "high")


# =========================================================================== #
# EXPENSE REIMBURSEMENT renderers
# =========================================================================== #
E_ERST = ("„In Ausnahmefällen kann es sein, dass Angestellte der Universität kleinere, zeitlich dringende Anschaffungen selbst besorgt haben und diese "
          "Auslagen zurück erstattet haben möchten.“")
E_QUITT = ("„Er/Sie muss ein Erstattungsformular ausfüllen und die Originalquittung aufkleben. Sollte auf der Quittung kein Artikel ausgewiesen sein, muss ein "
           "Stichwort (Schleifpapier für Labor) dazu geschrieben werden.“")
E_UPLOAD = "„Bitte laden Sie Ihre Belege direkt im Formular hoch; die Originalbelege sind anschließend von Ihnen für ein halbes Jahr aufzubewahren.“"
E_GESTE = ("„Keine Bewirtungskosten, sondern laufende Betriebsaufwendungen und damit auch aus Landesmitteln finanzierbar sind die üblichen Gesten der Höflichkeit "
           "(Mineralwasser, Kaffee, Tee, Obst und Gebäck), die Gästen der Universität angeboten werden.“")


def till(store, addr, tel, lines, pay, ts, bon, footer=None, vat=19, cash=None, width=34, hand=None, tax_id=None):
    """narrow till receipt. lines: (desc, qty, unit_gross)"""
    L = [store.center(width).rstrip(), addr.center(width).rstrip(), tel.center(width).rstrip(), ""]
    total = D("0")
    for d_, q, u in lines:
        amt = r2(q * D(u))
        total += amt
        if q == 1 and len(d_) <= width - 11:
            L.append(d_.ljust(width - 10) + f"{eur(amt):>10}")
        else:
            L += wrap(d_, width)
            if q == 1:
                L.append(" " * (width - 10) + f"{eur(amt):>10}")
            else:
                L.append(f"{q} ST x {eur(u)}".ljust(width - 10) + f"{eur(amt):>10}")
    L += ["", "SUMME EUR".ljust(width - 10) + f"{eur(total):>10}"]
    if cash:
        L += [f"BAR {eur(cash)}".ljust(width - 10), f"RÜCKGELD {eur(cash - total)}"]
    else:
        L += [pay]
    if vat:
        net, v = vat_split(total, vat)
        L += [f"MWST {vat}% NETTO {eur(net)} MWST {eur(v)}"[:width + 6]]
    L += [f"BON {bon} {ts}"] + ([f"St.-Nr. {tax_id}"] if tax_id else []) + (footer or []) + ([""] + hand if hand else [])
    return "\n".join(L), r2(total)


def card_statement(kind, holder, rows, period, bank="Hainbuchen Bank AG", mark=None):
    """rows: (booking date iso, text, amount signed Decimal, extra line or None). Returns text"""
    mark = mark or set()
    if kind == "kredit":
        L = [lr(f"{bank}, Kreditkartenabrechnung", f"Abrechnung {period}", 100), f"Karteninhaber: {holder} · Visa ****{random.Random(holder).randint(1000, 9999)}", "",
             row(["Buchungstag", "Vorgang / Verwendungszweck", "Betrag"], [12, 66, 14], "llr")]
        for d_, t_, a, x in rows:
            L.append(row([datef(d_, "de"), ("» " if d_ + t_ in mark else "") + t_, money(a, "eur")], [12, 66, 14], "llr"))
            if x:
                L.append(row(["", "   " + x, ""], [12, 66, 14], "llr"))
        L += ["", f"Summe Umsätze {money(sum((a for _, _, a, _ in rows), D('0')), 'eur')}. Der Betrag wird zum Monatsende vom Referenzkonto eingezogen."]
        return "\n".join(L)
    if kind == "giro":
        L = [lr(f"{bank}", f"Kontoauszug {period}", 100), f"Kontoinhaber: {holder}", "", row(["Buchung", "Wert", "Buchungstext / Verwendungszweck", "Betrag EUR"], [10, 10, 60, 12], "lllr")]
        for d_, t_, a, x in rows:
            L.append(row([datef(d_, "de2"), datef(addday(d_, 0), "de2"), t_, money(a, "bare")], [10, 10, 60, 12], "lllr"))
            if x:
                L.append(row(["", "", "   " + x, ""], [10, 10, 60, 12], "lllr"))
        return "\n".join(L)
    raise ValueError(kind)


def pvk_online(nr, sent, p, purpose, belege, total, kont, extra=None, mfmt="de", style=1):
    """print of the online form 'Digitale Abrechnung privat verauslagter Kosten' in two layouts"""
    if style == 1:
        L = [lr("Universität Wernstadt · Digitale Abrechnung privat verauslagter Kosten", f"Vorgang {nr}", 104), lr("Online-Formular (Pilotverfahren) · Druckansicht", f"gesendet {sent}", 104), "",
             kvw([("Antragsteller:in", p["name"]), ("Organisationseinheit", p["org"]), ("Kontierung", kont)], k=26, width=70, indent=0), "", "Zweck / dienstlicher Anlass"]
        L += para(purpose, 100, 2)
        L += ["", "Belege", "  " + row(["Nr.", "Beleg", "Datum", "Betrag"], [4, 58, 10, 12], "lllr")]
        for i, (b, d_, a) in enumerate(belege, 1):
            L.append("  " + row([str(i), b, d_, money(a, mfmt)], [4, 58, 10, 12], "lllr"))
        L += ["  " + row(["", "Erstattungsbetrag", "", money(total, mfmt)], [4, 58, 10, 12], "lllr")]
        if extra:
            L += [""] + ["  " + e for e in extra]
        L += ["", "Die Originalbelege bewahre ich ein halbes Jahr auf. Ich versichere die Richtigkeit der Angaben.", "Sachlich richtig: (Workflow Kostenstelle)", "", "Formular FIN-PVK-01 · Pilot bis 31.12.2026, verlängert"]
        return "\n".join(L)
    L = [f"Erstattung privat verauslagter Kosten – Antrag {nr}", f"Eingereicht am {sent} über das Selfservice-Portal der Finanzabteilung", "", "[Schritt 1/3] Person", f"  {p['name']} · {p['org']} · {p['email']}", "", "[Schritt 2/3] Was wurde gekauft und wozu?"]
    L += para(purpose, 100, 2)
    L += ["", "[Schritt 3/3] Hochgeladene Belege", "  " + row(["Datei / Beleg", "Datum", "Betrag"], [66, 10, 14], "llr")]
    for b, d_, a in belege:
        L.append("  " + row([b, d_, money(a, mfmt)], [66, 10, 14], "llr"))
    L += ["  " + row(["Summe der beantragten Erstattung", "", money(total, mfmt)], [66, 10, 14], "llr"), f"  Kostenstelle/Auftrag: {kont}"]
    if extra:
        L += [""] + ["  " + e for e in extra]
    L += ["", "[✔] Originalbelege werden sechs Monate aufbewahrt   [Antrag absenden]"]
    return "\n".join(L)


def invoice_shop(v, buyer, deliver, nr, date, order, its_gross, vat=19, pay="Kreditkarte (bezahlt)", dfmt="de", mfmt="de", foot=None, title="RECHNUNG", ship=None, lang="de"):
    """web-shop invoice; its_gross: (desc, qty, unit_gross); returns (text, total_gross)"""
    rows_ = list(its_gross) + ([("Versandkosten" if lang == "de" else "Shipping", 1, ship)] if ship else [])
    total = tot(*[q * D(u) for _, q, u in rows_])
    net, vv = vat_split(total, vat)
    en_ = lang == "en"
    w = [4, 56, 6, 12, 12]
    L = [f"{v['name']} · {v['street']} · {v['plz']} {v['city']}", f"USt-IdNr. {v['vat']}", "", "Rechnungsanschrift:" if not en_ else "Bill to:"] + ["  " + a for a in buyer] + ["Lieferanschrift:" if not en_ else "Ship to:"] + ["  " + b for b in deliver]
    L += ["", lr(f"{title} {nr}", f"{'Invoice date' if en_ else 'Rechnungsdatum'} {datef(date, dfmt)}", 100), f"{'Order' if en_ else 'Bestellung'} {order} · {'Payment' if en_ else 'Zahlart'}: {pay}", "",
          row(["Pos", "Artikel" if not en_ else "Item", "Menge" if not en_ else "Qty", "Preis" if not en_ else "Price", "Summe" if not en_ else "Amount"], w, "llrrr")]
    for n, (d_, q, u) in enumerate(rows_, 1):
        ds = wrap(d_, 56)
        L.append(row([str(n), ds[0], str(q), money(u, mfmt), money(q * D(u), mfmt)], w, "llrrr"))
        L += [row(["", e, "", "", ""], w, "llrrr") for e in ds[1:]]
    L += ["", row(["", "Rechnungsbetrag brutto" if not en_ else "Invoice total", "", "", money(total, mfmt)], w, "llrrr"), row(["", (f"included VAT {vat} % (net {money(net, mfmt)})" if en_ else f"enthaltene USt {vat} % (netto {money(net, mfmt)})"), "", "", money(vv, mfmt)], w, "llrrr")] + [""] + (foot or [])
    return "\n".join(L), total


def e_case(cid, docs, begr, sys_, trick, rule=E_ERST, conf="high", src=None):
    case(EXP, cid, docs, begr, sys_, trick, rule, src or SRC_FIBU, conf)


# =========================================================================== #
# EXPENSE REIMBURSEMENT  (auslagenerstattung-k51 .. k75)
# =========================================================================== #
def UBUY(p):
    return [UW, p["org_long"].replace("Fachbereich ", "FB ").replace(", Fachgebiet", " · FG"), UW_ADDR]


def DEL(p, room="Raum 2.14"):
    return [UW, f"FG {p['fg']}, {room}", f"z. Hd. {p['plain']}", UW_ADDR]


def k51():
    p = staff(51, "", fb="71")
    cid = "auslagenerstattung-k51"
    d = "2027-03-18"
    lines = [("Kabelbinder 200 St. 2,5x100", 1, "3.49"), ("Schrumpfschlauch-Set 127-tlg", 1, "11.99"), ("Klemmleiste 12-pol 2,5qmm", 2, "2.79"), ("Isolierband schwarz 15mm", 3, "1.59"), ("Loetzinn bleifrei 1mm 100g", 1, "7.95")]
    txt, total = till("BAUMARKT HANSEN & SOHN", "Dorfstrasse 11 · 31134 Hildesheim", "Tel. 05121 90 44 713", lines, "GIROCARD ***4471 GENEHMIGT", f"{datef(d, 'de2')} 16:42", "2217 KASSE 02", ["VIELEN DANK FUER IHREN EINKAUF"], tax_id="66/218/40913",
                      hand=["Material fuer Versuchsstand", "Labor E 3.12 (FG " + p["fg"] + ")", "dringend, Messung Montag", p["plain"]])
    assert total == D("33.78")
    begr = ("Kassenbon eines Baumarkts über 33,78 € mit allen Artikeln einzeln bezeichnet (Kabelbinder, Schrumpfschlauch, Klemmleiste, Isolierband, Lötzinn); handschriftlich ist der dienstliche Zweck (Versuchsstand im Labor, dringend) ergänzt. "
            "Eine kleine, zeitlich dringende Anschaffung, privat per Girocard gezahlt; es liegt der Originalbeleg vor.")
    e_case(cid, [doc("beleg.pdf", txt, size=RECEIPT, jitter=0.7, producer="Scan")], begr, "Schmaler Kassenbon (Textversatz) eines Baumarkts, nur dieser eine Beleg", "Alle Artikel gedruckt, handschriftlicher Zusatz zum Zweck; MwSt-Zeile und Steuernummer auf dem Bon", E_QUITT)


def k52():
    p = staff(52, "Dr.", fb="76")
    cid = "auslagenerstattung-k52"
    d = "2027-04-08"
    lines = [("Ethanol 96% 1 l", 2, "7.49"), ("Einmalpipetten 3ml 100 St", 1, "6.95"), ("Alufolie 30m", 1, "3.99"), ("--Kaffee to go--", 1, "3.40"), ("--Kaugummi--", 1, "1.29")]
    txt, total = till("DROGERIE UND LABORBEDARF KRÜGER", "Marktplatz 3 · 34117 Marburg", "Tel. 06421 55 10 02", lines, "GIROCARD ***4471 GENEHMIGT", f"{datef(d, 'de')} 11:08", "0883 KASSE 01", ["Bitte Beleg aufbewahren"], tax_id="03/118/77421",
                      hand=["Durchgestrichen = PRIVAT:", "Kaffee 3,40 + Kaugummi 1,29", "Rest dienstlich: Ethanol, Pipetten,", "Alufolie fuer Praktikum", p["plain"]])
    priv = D("3.40") + D("1.29")
    claim = r2(total - priv)
    pvk = pvk_online("PVK-2027-03318", f"{wd(addday(d, 2))} 09:50", p, "Dringend benötigte Laborartikel für das Praktikum (Ethanol, Einmalpipetten, Alufolie). Auf dem Kassenbon sind zwei private Positionen durchgestrichen und nicht beantragt.",
                     [(f"Kassenbon Drogerie Krüger (Bon 0883): Gesamt {eur(total)} €, davon privat {eur(priv)} €", datef(d, "de2"), claim)], claim, f"{p['ks']} / Auftrag {p['auftrag']}", mfmt="eur", style=2)
    begr = (f"Der Kassenbon weist {eur(total)} € aus; zwei private Positionen (Kaffee 3,40 €, Kaugummi 1,29 €) sind durchgestrichen und nicht beantragt. Erstattet werden nur die dienstlichen Laborartikel: {eur(claim)} €, im Formular genau so beantragt. Alle verbleibenden Artikel sind bezeichnet, dringender Praktikumsbedarf.")
    e_case(cid, [doc("kassenbon.pdf", txt, size=RECEIPT, jitter=0.6), doc("antrag-online.pdf", pvk, font="Helvetica")], begr, "Kassenbon mit handschriftlich durchgestrichenen privaten Positionen + Ausdruck des Online-Formulars (Variante 2)", "Beantragter Betrag NIEDRIGER als der Bon: private Zeilen (3,40 + 1,29) durchgestrichen, beantragt ist nur der Rest", E_ERST + " " + E_UPLOAD, "medium")


def k53():
    p = staff(53, "Dr.", fb="72")
    cid = "auslagenerstattung-k53"
    inv_d, cn_d = "2027-05-10", "2027-05-19"
    v = dict(name="Bluecart Marketplace Services Ltd. (for seller Delta Tools Europe B.V.)", street="Keizersgracht 45", plz="1015 CJ", city="Amsterdam, NL", vat="NL 8112 5540 7B01")
    its = [("Digital caliper 150 mm, stainless steel, 0.01 mm", 1, "24.90"), ("ESD wrist strap with coiled cord, pack of 10", 2, "11.50")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p), "BC-NL-27-0094417", inv_d, "114-8820931-6624", its, 19, "Credit card ****6021, paid", "dmy-en", "en-eur", ["German VAT charged under the EU one-stop-shop scheme."], "Invoice", ship=D("3.95"), lang="en")
    assert total == D("51.85")
    credit = D("11.50")
    cn = "\n".join([v["name"], "", f"Credit note BC-NL-27-CN-0013307 · {datef(cn_d, 'dmy-en')}", f"Re: invoice BC-NL-27-0094417 of {datef(inv_d, 'dmy-en')} · return authorisation R-4410298", "",
                    row(["Item", "Qty", "Amount"], [60, 6, 14], "lrr"), row(["ESD wrist strap with coiled cord, pack of 10 (returned: wrong connector)", "1", money(-credit, "en-eur")], [60, 6, 14], "lrr"), "", f"Credit note total {money(-credit, 'en-eur')} (incl. 19 % VAT)", "Refunded to the original payment method (credit card ****6021)."])
    kk = card_statement("kredit", p["plain"], [(addday(inv_d, 1), "BLUECART MKT AMSTERDAM 114-8820931", -total, None), (addday(inv_d, 3), "LEBENSMITTEL NORDMARKT", -D("34.18"), None), (addday(cn_d, 2), "BLUECART MKT AMSTERDAM GUTSCHRIFT", credit, None)], "Mai 2027")
    claim = r2(total - credit)
    pvk = pvk_online("PVK-2027-04871", f"{wd(addday(cn_d, 4))} 13:22", p, "Messschieber und ESD-Armbänder für den Messplatz im Praktikum, kurzfristig benötigt; ein Armband-Pack wurde zurückgeschickt und gutgeschrieben.",
                     [("Rechnung BC-NL-27-0094417", datef(inv_d, "de2"), total), ("Gutschrift BC-NL-27-CN-0013307 (Retoure)", datef(cn_d, "de2"), -credit)], claim, f"{p['ks']} / Auftrag {p['auftrag']}", mfmt="de", style=2)
    begr = (f"Die Rechnung über {eur(total)} € ist an die Universität gerichtet, nennt die Artikel (Messschieber, ESD-Armbänder) und wurde privat mit der Kreditkarte bezahlt. Die Gutschrift über 11,50 € bezieht sich auf diese Rechnung, die Kartenabrechnung zeigt Belastung und Rückbuchung. Beantragt ist der Saldo {eur(claim)} € = {eur(total)} € − 11,50 €.")
    e_case(cid, [doc("invoice.pdf", txt, font="Helvetica"), doc("credit-note.pdf", cn, font="Helvetica"), doc("kreditkarte.pdf", kk), doc("antrag.pdf", pvk, font="Helvetica")], begr, "Englische Marktplatzrechnung + Gutschrift + Kartenabrechnung + Online-Formular (Variante 2)", "Gutschrift korrekt abgezogen (51,85 − 11,50 = 40,35); Lieferanschrift getrennt von Rechnungsanschrift; Kartenabrechnung enthält fremde Zeile", E_ERST + " (Saldo wie im Fall auslagenerstattung-05 der Organisatoren)")


def k54():
    p = staff(54, "Dr.", fb="75")
    cid = "auslagenerstattung-k54"
    d = "2027-03-05"
    gross = D("189.00")
    net, vat = vat_split(gross, 19)
    inv = "\n".join(["Eventlab GmbH · Hafenweg 4 · 20457 Hamburg", "USt-IdNr. DE 311 552 870", "", f"{p['name']}", f"c/o {UW}, FG {p['fg']}", UW_ADDR, "", lr("RECHNUNG EL-27-004118", f"Rechnungsdatum {datef(d, 'de')}", 100),
                     "Zahlungsart: Kreditkarte, bezahlt", "", row(["Leistung", "Menge", "netto", "brutto"], [60, 6, 12, 12], "lrrr"), row(["Ticket „DataViz Summit Online 2027“, Online-Teilnahme (Livestream), 2 Tage, inkl. Aufzeichnungen", "1", money(net, "bare"), money(gross, "bare")], [60, 6, 12, 12], "lrrr"),
                     "", f"Rechnungsbetrag {money(gross)}, darin 19 % USt {money(vat)}", "", "Die Veranstaltung findet ausschließlich online statt. Zugangslink 24 Stunden vorher per E-Mail."])
    kk = card_statement("kredit", p["plain"], [(addday(d, 0), "EVENTLAB GMBH HAMBURG", -gross, None), (addday(d, 2), "APOTHEKE AM MARKT", -D("16.80"), None), (addday(d, 5), "TANKSTELLE NORDRING", -D("62.15"), None)], "März 2027")
    begr = ("Teilnahmegebühr für eine ausschließlich online stattfindende Tagung (Livestream, kein Reiseanlass): Nach den Regeln zu Dienstreisen sind Gebühren für Online-Konferenzen privat zu verauslagen und bei der Finanzabteilung geltend zu machen; es gibt keinen Dienstreiseantrag. Rechnung "
            "benennt die Leistung, Kreditkartenabrechnung weist 189,00 € aus (andere Zeilen sind nicht Teil der Auslage).")
    e_case(cid, [doc("rechnung.pdf", inv, font="Helvetica"), doc("kreditkarte.pdf", kk)], begr, "Rechnung eines Veranstalters (DE, 19 % USt) + Kartenabrechnung mit fremden Zeilen; kein Formular", "Online-Tagung statt Dienstreise; Kartenabrechnung mit Apotheke und Tankstelle als nicht betroffene Zeilen", R_ONLINE, "medium" if False else "high", SRC_DRM)


def k55():
    p = staff(55, "Dr.", fb="73")
    cid = "auslagenerstattung-k55"
    d = "2027-06-03"
    rate = D("1.1660")
    gbp = D("150.00")
    eur_ = r2(gbp * rate)
    fee = r2(eur_ * D("0.0175"))
    assert eur_ == D("174.90")
    rec = "\n".join([lr("SURFACE SCIENCE NETWORK UK", "", 100), "Registered in England · 14 Granton Row, Bristol BS1 5AA", "", f"{p['name']}", f"{UW}, FG {p['fg']}", UW_ADDR, p["email"], "",
                     lr("Receipt no. SSN-V27-00418", f"Date: {datef(d, 'us')}", 100), "Registration ID: V-2207", "", "Virtual Workshop on Surface Science, 16-17 June 2027 (online only)", row(["Item", "Qty", "Amount"], [64, 6, 14], "lrr"),
                     row(["Online participation, academic rate (live sessions and recordings)", "1", "GBP 150.00"], [64, 6, 14], "lrr"), "", "Total paid GBP 150.00", "Paid by credit card on " + datef(d, "iso") + ". No VAT charged (outside the scope of EU VAT)."])
    kk = card_statement("kredit", p["plain"], [(addday(d, 1), "SSN UK BRISTOL GB", -eur_, f"GBP {gbp:,.2f} Kurs {str(rate).replace('.', ',')}"), (addday(d, 1), "Auslandseinsatzentgelt", -fee, "1,75 % von " + eur(eur_) + " EUR (nicht Teil der Erstattung)"), (addday(d, 4), "BUCHHANDLUNG AM UHRTURM", -D("18.40"), None)], "Juni 2027", bank="Hainbuchen Bank AG")
    begr = (f"Online-Workshop (nur virtuell, daher keine Dienstreise) in Großbritannien: Die Teilnahmegebühr GBP 150,00 wurde privat per Kreditkarte gezahlt; die Abrechnung zeigt die Umrechnung auf {eur(eur_)} € (Kurs 1,1660). Erstattet wird der belastete Betrag {eur(eur_)} €; das Auslandseinsatzentgelt ist ausdrücklich nicht beantragt.")
    e_case(cid, [doc("receipt-ssn.pdf", rec, font="Helvetica"), doc("kreditkarte-juni.pdf", kk)], begr, "Englische Quittung in GBP (ohne USt) + Kreditkartenabrechnung mit Umrechnungskurs und Auslandseinsatzentgelt", "Fremdwährung (GBP) mit Kurs; Entgelt-Zeile 3,06 € nicht Teil der Auslage; US-Datum „June 3, 2027“", R_ONLINE, "high", SRC_DRM)


def k56():
    p = staff(56, "Prof. Dr.", fb="72")
    cid = "auslagenerstattung-k56"
    d = "2027-02-12"
    v = dict(name="Buchhandlung am Uhrturm GmbH", street="Marktgasse 9", plz="35037", city="Marburg", vat="DE 224 118 905")
    its = [("Regelungstechnik 1 – Grundlagen, 12. Auflage (ISBN 978-3-000-00000-1)", 1, "62.00"), ("Digitale Regelung in der Praxis, 3. Auflage (ISBN 978-3-000-00000-2)", 1, "48.50")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p, "Sekretariat"), "RE-27-3318", d, "K-4490", its, 7, "Girocard (bezahlt)", "long", "de", ["Bücher unterliegen dem ermäßigten Steuersatz von 7 %."])
    assert total == D("110.50")
    ec = "\n".join(["GIROCARD-BELEG", "Buchhandlung am Uhrturm GmbH", f"{datef(d, 'de')}  13:21", "Terminal 4410-02", "Karte ***4471", "", f"Betrag EUR {eur(total)}", "Zahlung erfolgt", "Beleg 3318"])
    begr = ("Rechnung der Buchhandlung über zwei benannte Fachbücher (110,50 €, 7 % USt) an das Fachgebiet der Universität; Zahlung privat per Girocard, Girocard-Beleg liegt bei. Lehrbücher für das Fachgebiet sind eine kleine, kurzfristig benötigte Anschaffung für die Lehre; Original-Rechnung vorhanden.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Times-Roman"), doc("ec-beleg.pdf", ec, size=RECEIPT)], begr, "Buchhandlungsrechnung mit Langdatum und 7 % USt + Girocard-Beleg (schmal)", "Reduzierter Steuersatz 7 %; ISBN in Positionen; Rechnung auf die Universität, Zahlung privat", E_ERST, "medium")


def k57():
    p = staff(57, "", fb="74")
    cid = "auslagenerstattung-k57"
    d = "2027-05-26"
    v = dict(name="Plakat- und Posterdruck Brandt e.K.", street="Gewerbering 12", plz="34117", city="Kassel-Süd".replace("Kassel-Süd", "Wernstadt-Süd"), vat="DE 118 004 557")
    its = [("Posterdruck DIN A0, 180 g/m², matt, nach PDF-Vorlage", 2, "37.49"), ("Posterleiste Alu, 84 cm", 2, "4.76")]
    t1, total = invoice_shop(v, UBUY(p), DEL(p), "RE 27-1409", d, "A-8812", its, 19, "Girocard am Tag der Abholung", "de2", "de")
    t2 = "*** KOPIE ***  (Zweitschrift, kein Originalbeleg)\n\n" + t1.replace("RE 27-1409", "RE 27-1409").replace("RECHNUNG", "RECHNUNG (Kopie)")
    ec = "\n".join(["GIROCARD-BELEG", v["name"], f"{datef(d, 'de')}  14:07", "Karte ***4471", f"Betrag EUR {eur(total)}", "Zahlung erfolgt"])
    begr = (f"Die Rechnung RE 27-1409 über {eur(total)} € (zwei Poster mit Leisten für die Tagungspräsentation) liegt im Original und als ausdrücklich mit „KOPIE“ gekennzeichnete Zweitschrift derselben Rechnung (gleiche Nummer, gleicher Betrag) vor; geltend gemacht wird sie nur einmal. Privat per Girocard gezahlt, Beleg liegt bei, Rechnung an das Fachgebiet.")
    e_case(cid, [doc("rechnung-original-und-kopie.pdf", [(t1, dict(font="Helvetica")), (t2, dict(font="Helvetica", jitter=0.6))]), doc("ec-zahlbeleg.pdf", ec, size=RECEIPT)], begr, "Eine PDF-Datei mit Original (Seite 1) und Zweitschrift „KOPIE“ derselben Rechnung (Seite 2) + Girocard-Beleg", "Gleiche Rechnungsnummer zweimal im Antrag, die zweite Seite ist erkennbar „KOPIE“ – ein einziger Betrag", E_ERST, "medium")
    # NB: the amount appears twice in the file but is claimed once


def k58():
    p = staff(58, "", fb="77")
    cid = "auslagenerstattung-k58"
    d1, d2 = "2027-09-14", "2027-09-15"
    t1, a1 = till("BAUMARKT BRINKMANN", "Industrieweg 5 · 48155 Münster", "Tel. 0251 77 10 33", [("Schleifpapier K120 5er", 2, "4.95"), ("Schleifpapier K240 5er", 2, "4.95"), ("Pinsel flach 25mm", 1, "3.60")], "EC-KARTE ***4471", f"{datef(d1, 'de2')} 09:55", "4471 KASSE 3", tax_id="337/5511/20")
    t2, a2 = till("ELEKTRO HELLWEG", "Ringstrasse 21 · 48143 Münster", "Tel. 0251 22 08 41", [("Batterien AA 8er", 1, "9.95"), ("Sicherung 5x20 T1A 10er", 1, "3.40"), ("Lüsterklemmen 12er", 1, "4.50")], "EC-KARTE ***4471", f"{datef(d2, 'de2')} 08:31", "0912 KASSE 1", tax_id="337/5512/44")
    assert (a1, a2) == (D("23.40"), D("17.85"))
    mail = owa_mail(p["email"].split("@")[0], "Erstattung Auslagen Bodenkundepraktikum", f"{p['plain']} <{p['email']}>", f"{wd(addday(d2, 1))} 10:12", "finanzbuchhaltung@uni-wernstadt.de",
                    ["Sehr geehrte Damen und Herren,", "", "für das Bodenkundepraktikum musste ich kurzfristig zwei Einkäufe selbst besorgen, da der Bestellweg zu lange gedauert hätte. Die Belege sind angehängt:", "",
                     f"   Beleg 1  {datef(d1, 'de')}  Baumarkt Brinkmann (Schleifpapier K120/K240, Pinsel für Probenvorbereitung)      23,40 EUR", f"   Beleg 2  {datef(d2, 'de')}  Elektro Hellweg (Batterien, Sicherungen, Lüsterklemmen für Messgeräte)            17,85 EUR", "   ------------------------------------------------------------------------------------------", "   Summe                                                                                         41,25 EUR", "",
                     f"Bitte erstatten Sie die 41,25 EUR. Kostenstelle {p['ks']}.", "", "Freundliche Grüße", p["plain"]])
    begr = ("Zwei Kassenbons (23,40 € und 17,85 €) mit allen Artikeln einzeln bezeichnet; die Begleitmail nennt dieselben Einzelbeträge und die Summe 41,25 € und erklärt den dienstlichen Zweck (Bodenkundepraktikum, Probenvorbereitung und Messgeräte). Kleine, dringende Anschaffungen, privat per EC-Karte bezahlt.")
    e_case(cid, [doc("mail-erstattung.pdf", mail, font="Helvetica"), doc("beleg-1.pdf", t1, size=RECEIPT, jitter=0.5), doc("beleg-2.pdf", t2, size=RECEIPT, jitter=0.5)], begr, "Begleitmail mit Beträgen im Text + zwei schmale Kassenbons", "Beträge stehen auch im Mailtext (Einzelwerte + Summe 41,25), kein Formular", E_ERST + " " + E_QUITT)


def k59():
    p = staff(59, "Dr.", fb="76")
    cid = "auslagenerstattung-k59"
    d = "2027-07-21"
    txt, total = till("ADLER-APOTHEKE E.K.", "Bahnhofstrasse 2 · 99084 Erfurt", "Tel. 0361 55 22 10", [("Isopropanol 70% 1 l", 3, "6.95"), ("Wattestaebchen 200 St", 1, "1.95"), ("Nitril-Handschuhe 100 St M", 1, "7.45")], "EC-KARTE ***4471 GENEHMIGT", f"{datef(d, 'de')} 17:26", "1180 KASSE 1",
                      ["Preise inkl. gesetzl. MwSt.", "TSE-Seriennr. 4F7A-11C0-90B2", "TSE-Start 17:25:48 Stop 17:26:10"], hand=["Reinigung Versuchsplatz nach", "Leckage – dringend, kein Bestand", p["plain"] + ", FG " + p["fg"]])
    assert total == D("30.25")
    begr = ("Apothekenbon über 30,25 € mit allen Artikeln (Isopropanol, Wattestäbchen, Nitril-Handschuhe) und handschriftlich ergänztem dienstlichem Anlass (Reinigung des Versuchsplatzes nach einer Leckage, kein Bestand). Eine kleine, zeitlich dringende Anschaffung, privat gezahlt; Originalbeleg liegt vor.")
    e_case(cid, [doc("IMG_4417.pdf", txt, size=RECEIPT, jitter=0.6, producer="iPhone Scan")], begr, "Apothekenbon (schmal, Zeilenversatz) mit TSE-Zeilen; Dateiname IMG_4417", "TSE-Seriennummer und Zeitstempel als zusätzliche Ziffernzeilen; handschriftlicher Anlass", E_QUITT)


def k60():
    p = staff(60, "Dr.", fb="76")
    cid = "auslagenerstattung-k60"
    d = "2027-10-07"
    v = vendor(60, "lab")
    its = [("Pipettenspitzen 10–200 µl, gelb, VE 1000", 2, "18.45"), ("Einmalhandschuhe Nitril Gr. S, VE 200", 3, "9.90"), ("Probengefäße 15 ml, steril, VE 100", 1, "14.20")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p, "Labor 4.02"), "RE-27-118843", d, "WEB-4408821", its, 19, "Kreditkarte, bezahlt am " + datef(d, "de"), "de", "eur", ["Expresslieferung (Lieferung am Folgetag) ausgewählt.", "Zahlungseingang bestätigt. Dies ist die Rechnung; es folgt keine weitere Rechnung."], ship=D("8.90"))
    pvk = pvk_online("PVK-2027-06602", f"{wd(addday(d, 3))} 16:40", p, "Verbrauchsmaterial für die Praktikumsversuche ging aus; die reguläre Bestellung über SAP wäre erst nach Versuchsbeginn geliefert worden (Express).", [(f"Rechnung RE-27-118843, {v['name']}", datef(d, "de2"), total)], total, f"{p['ks']} / Auftrag {p['auftrag']}", mfmt="eur", style=1)
    begr = (f"Echte Rechnung (kein Pro-forma-Beleg) über {eur(total)} € an die Universität mit benannten Laborartikeln, Expressversand und Vermerk, dass keine weitere Rechnung folgt; privat per Kreditkarte bezahlt. Der Bedarf war kurzfristig, im Formular begründet.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Helvetica"), doc("antrag.pdf", pvk, font="Helvetica")], begr, "B2B-Laborshop-Rechnung („EUR 77,80“-Format) mit Zahlungsvermerk + Online-Formular (Variante 1)", "Rechnung ist ausdrücklich keine Pro-forma; Versand und Express als eigene Zeile; Beträge im Format „EUR 88,93“", E_ERST + " " + E_UPLOAD)


def k61():
    p = staff(61, "Dr.", fb="71")
    cid = "auslagenerstattung-k61"
    d = "2027-08-24"
    its = [("ESD tweezers set, 6 pcs, stainless", 2, D("19.80")), ("ESD work mat 60 x 45 cm, with grounding cord", 1, D("34.90")), ("Shipping (NL > DE), tracked", 1, D("6.90"))]
    net = tot(*[q * u for _, q, u in its])
    assert net == D("81.40")
    inv = "\n".join(["Tweezerhouse B.V. · Havenstraat 44 · 3011 TB Rotterdam · The Netherlands", "VAT ID NL 8574.12.063.B01", "", "Bill to:                                      Ship to:", f"{UW}                         {UW}, FG {p['fg']}", f"Zentraler Rechnungseingang                    z. Hd. {p['plain']}",
                     UW_ADDR + "           " + UW_ADDR, f"Customer VAT ID: DE 811 000 000", "", lr("INVOICE TH-27-77120", f"Invoice date {datef(d, 'dmy-en')}", 100), "Order 77120 · Payment: credit card, paid", "",
                     row(["Item", "Qty", "Unit price", "Amount"], [58, 5, 13, 13], "lrrr")] + [row([a, str(q), money(u, 'en-eur'), money(q * u, 'en-eur')], [58, 5, 13, 13], "lrrr") for a, q, u in its] +
                    ["", row(["Net total", "", "", money(net, "en-eur")], [58, 5, 13, 13], "lrrr"), row(["VAT 0 % (intra-community supply, reverse charge applies)", "", "", money(D("0"), "en-eur")], [58, 5, 13, 13], "lrrr"), row(["Total", "", "", money(net, "en-eur")], [58, 5, 13, 13], "lrrr")])
    kk = card_statement("kredit", p["plain"], [(addday(d, 1), "TWEEZERHOUSE ROTTERDAM NL", -net, None), (addday(d, 2), "BAECKEREI MOELLER", -D("6.40"), None)], "August 2027")
    begr = ("Englische Rechnung eines niederländischen Händlers über 81,40 € netto, an die Universität gerichtet (Lieferanschrift am Fachgebiet) mit USt-IdNr. der Universität; Steuer 0 % (innergemeinschaftliche Lieferung, Reverse Charge), daher brutto = netto. Artikel (ESD-Pinzetten, ESD-Matte) benannt, privat per Kreditkarte bezahlt, Kartenabrechnung zeigt dieselbe Belastung.")
    e_case(cid, [doc("invoice-TH-27-77120.pdf", inv, font="Helvetica"), doc("kreditkarte-aug.pdf", kk)], begr, "Englische Rechnung eines niederländischen Händlers mit 0 % USt (Reverse Charge) + Kartenabrechnung", "Brutto gleich netto wegen Reverse Charge; Lieferanschrift ≠ Rechnungsanschrift; Betragsformat „EUR 81.40“", E_ERST + " " + E_QUITT, "medium")


def k62():
    p = staff(62, "", fb="71")
    cid = "auslagenerstattung-k62"
    d = "2027-05-03"
    v = vendor(62, "elec")
    its = [("Steckernetzteil 12 V / 2 A, Labor", 2, "14.90"), ("Bananenstecker-Satz, 20-teilig", 2, "8.50")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p), "BK-27-22140", d, "27-0988341", its, 19, "Kreditkarte (bezahlt)", "short", "plain", ["Lieferung ab 49 € versandkostenfrei."])
    rows_ = [("2027-04-29", "TANKSTELLE NORDRING WERNSTADT", -D("58.20"), None), ("2027-04-30", "NORDMARKT SUPERMARKT", -D("43.07"), None), (d, "BAUTEILE-KONTOR WEBSHOP NUERNBERG", -total, None), ("2027-05-04", "KINO CAPITOL WERNSTADT", -D("19.00"), None),
             ("2027-05-06", "DEUTSCHE BAHN FERNVERKEHR", -D("69.90"), None), ("2027-05-07", "BAECKEREI MOELLER", -D("5.30"), None), ("2027-05-10", "ZAHLUNGSEINGANG DANKE", D("196.47"), None)]
    kk = card_statement("kredit", p["plain"], rows_, "Mai 2027")
    note = "\n".join([f"Auslage Elektronikversand {datef(d, 'de')}: {eur(total)} €", "(Zeile 03.05. der Kartenabrechnung; alle anderen Zeilen privat)", "Zweck: Netzteile und Steckersätze für den Messaufbau im Praktikum.", "✔ nur Rechnung BK-27-22140 beantragt", p["plain"]])
    begr = (f"Beantragt wird nur die Rechnung BK-27-22140 über {eur(total)} € (Netzteile und Steckersätze für den Messaufbau, benannt, an die Universität gerichtet); die Kartenabrechnung enthält zahlreiche private Zeilen, die nicht beantragt sind, und zeigt dieselbe Belastung am 03.05. Der Zettel nennt die relevante Zeile ausdrücklich.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Helvetica"), doc("kartenabrechnung-mai.pdf", kk), doc("notiz.pdf", note, font="Helvetica", jitter=0.6)], begr, "Shop-Rechnung + Kreditkartenabrechnung mit sieben Zeilen, davon nur eine betroffen; handschriftlicher Zettel mit „✔“", "Viele fremde Beträge (58,20; 43,07; 19,00; 69,90 …) auf der Abrechnung, nur 03.05. gehört zur Auslage", E_ERST + " " + E_QUITT)


def k63():
    p = staff(63, "Dr.", fb="77")
    cid = "auslagenerstattung-k63"
    d1, d2, d3 = "2027-06-15", "2027-06-16", "2027-06-16"
    r1, a1 = till("BAUMARKT SCHMIDT", "Am Anger 9 · 37073 Göttingen", "0551 33 10 77", [("Kabelrohr 20mm 2m", 2, "3.45"), ("Dübel 6mm 50 St", 1, "2.80"), ("Silikon transparent", 1, "2.79")], "EC ***4471", f"{datef(d1, 'de2')} 12:44", "3345", tax_id="20/118/3350")
    r2_, a2 = till("DROGERIE MÜLLER-WEST", "Weender Str. 40 · 37073 Göttingen", "0551 21 77 08", [("Desinfektionstuecher 100", 1, "5.95"), ("Zellstoff 6 Rollen", 1, "3.00")], "EC ***4471", f"{datef(d2, 'de2')} 08:03", "7781", tax_id="20/118/9901")
    r3, a3 = till("ELEKTRONIK-DISCOUNT", "Groner Str. 12 · 37073 Göttingen", "0551 84 10 90", [("USB-Kabel A-C 1m", 2, "4.95"), ("Batterie 9V Block", 2, "3.00")], "EC ***4471", f"{datef(d3, 'de2')} 14:19", "1520", tax_id="20/118/7745")
    total = a1 + a2 + a3
    cover = "\n".join(["ERSTATTUNGSFORMULAR privat verauslagte Kosten (Deckblatt)", "", f"Name: {p['name']}   Einrichtung: {p['org']}", f"Kostenstelle/Auftrag: {p['ks']} / {p['auftrag']}", "", "Beleg   Datum        Geschäft               Stichwort (Artikel)                                    Betrag",
                       f"  1     {datef(d1, 'de')}   Baumarkt Schmidt       Kabelrohr, Dübel, Silikon (Geländemessstation)          {eur(a1)} €", f"  2     {datef(d2, 'de')}   Drogerie Müller-West   Desinfektionstücher, Zellstoff (Gerätereinigung)        {eur(a2)} €",
                       f"  3     {datef(d3, 'de')}   Elektronik-Discount    Kabel, 9-V-Batterien (Feldmessung)                      {eur(a3)} €", "", f"Summe: {eur(total)} €", "Originalbelege auf Rückseite aufgeklebt.", f"Göttingen, {de(addday(d3, 2))}   {p['plain']}"])
    parts = [(cover, dict(font="Courier", jitter=1.0)), (r1, dict(size=RECEIPT, jitter=0.8)), (r2_, dict(size=RECEIPT, jitter=0.8)), (r3, dict(size=RECEIPT, jitter=0.8))]
    random.Random(cid).shuffle(parts)
    begr = (f"Eine Sammel-Scandatei mit Deckblatt und drei Kassenbons in beliebiger Reihenfolge: Das Deckblatt listet die Belege mit Stichwort und Betrag ({eur(a1)} €, {eur(a2)} €, {eur(a3)} €, Summe {eur(total)} €), die Summen stimmen mit den Bons überein. Kleine dringende Anschaffungen für Feldmessungen, privat bezahlt.")
    e_case(cid, [doc("IMG_2231.pdf", parts, producer="Samsung Scanner")], begr, "Ein Sammelscan: Deckblatt (Erstattungsformular) und drei Kassenbons verschiedener Händler, Seitenreihenfolge zufällig, verschiedene Seitenformate", "Mehrere Belege in EINER Datei, Reihenfolge zufällig, Summe nur auf dem Deckblatt", E_QUITT)
    assert total == a1 + a2 + a3


def k64():
    p = staff(64, "Dr.", fb="72")
    cid = "auslagenerstattung-k64"
    d1, d2 = "2027-04-14", "2027-04-16"
    v1, v2 = vendor(64, "werk"), vendor(65, "werk")
    t1, g1 = invoice_shop(v1, UBUY(p), DEL(p, "Werkstatt"), "R-27-4411", d1, "W-90771", [("3D-Druck-Filament PETG 1,75 mm, 1 kg, grau", 2, "22.45")], 19, "Kreditkarte (bezahlt)", "de", "de", ship=D("4.90"))
    t2, g2 = invoice_shop(v2, UBUY(p), DEL(p, "Werkstatt"), "2027-018833", d2, "55320", [("Filament PLA 1,75 mm, 1 kg, weiß", 1, "19.90"), ("Düsen-Set 0,4 mm, 5 St.", 1, "7.60")], 19, "Kreditkarte (bezahlt)", "iso", "plain")
    total = g1 + g2
    mail = owa_mail(p["email"].split("@")[0], "Auslagenerstattung Filament für Prototypenwerkstatt", f"{p['plain']} <{p['email']}>", f"{wd(addday(d2, 2))} 09:05", "finanzbuchhaltung@uni-wernstadt.de",
                    ["Sehr geehrte Damen und Herren,", "", "wegen einer kurzfristigen Messreihe musste ich Filament und Düsen sofort selbst bestellen. Die beiden Rechnungen hängen an:", "", f"   Rechnung R-27-4411 ({v1['name']}):  {eur(g1)} EUR", f"   Rechnung 2027-018833 ({v2['name']}):  {eur(g2)} EUR", f"   zusammen:  {eur(total)} EUR", "",
                     "Beide Rechnungen sind an die Universität gerichtet und mit meiner Kreditkarte bezahlt. Dies sind zwei verschiedene Bestellungen bei zwei Händlern.", "", "Mit freundlichen Grüßen", p["plain"]])
    begr = (f"Zwei Rechnungen verschiedener Händler (R-27-4411: {eur(g1)} €, 2027-018833: {eur(g2)} €), an die Universität gerichtet, Artikel benannt; die Begleitmail nennt dieselben Beträge und die Summe {eur(total)} € und stellt klar, dass es zwei verschiedene Bestellungen sind (keine Doppelabrechnung). Kleine, dringende Anschaffung für eine Messreihe.")
    e_case(cid, [doc("mail.pdf", mail, font="Helvetica"), doc("rechnung-1.pdf", t1, font="Helvetica"), doc("rechnung-2.pdf", t2, font="Courier")], begr, "Begleitmail mit Beträgen + zwei Web-Shop-Rechnungen verschiedener Händler (zwei Datumsformate)", "Zwei Rechnungen mit unterschiedlichen Nummern und Händlern, in der Mail ausdrücklich als zwei Bestellungen genannt; Beträge in Mailtext", E_ERST)


def k65():
    p = staff(65, "", fb="73")
    cid = "auslagenerstattung-k65"
    d = "2027-09-02"
    v = vendor(66, "elec")
    txt, total = invoice_shop(v, UBUY(p), DEL(p, "Labor 1.08"), "RE-27-90332", d, "SH-880214", [("Messleitungen silikon 1 m, rot/schwarz, Paar", 3, "9.90"), ("Krokodilklemmen isoliert, 10 St", 2, "6.45")], 19, "PayPal (bezahlt)", "de", "bare")
    pp = "\n".join(["PayPal", "Zahlungsbestätigung", "", f"Sie haben eine Zahlung von {eur(total)} € an {v['name']} gesendet.", f"Transaktionsdatum: {datef(d, 'de')}, 18:11 Uhr MESZ", "Transaktionscode: 7XK41120MR5517782", f"Rechnungsnummer: RE-27-90332", "", "Zahlungsquelle: Kreditkarte ****4471",
                   f"Bruttobetrag: -{eur(total)} EUR", "Gebühr: 0,00 EUR", "", "Käuferschutz: aktiv (Warenkauf)", "Hinweis: Dies ist eine automatische Bestätigung, keine Rechnung."])
    begr = (f"Rechnung RE-27-90332 über {eur(total)} € an die Universität (Messleitungen, Krokodilklemmen), bezahlt per PayPal; die PayPal-Zahlungsbestätigung weist den Händler, den Betrag und die Rechnungsnummer aus. Die Bestätigung ist ausdrücklich keine zweite Rechnung, es wird nur einmal abgerechnet.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Helvetica"), doc("paypal-beleg.pdf", pp, font="Helvetica")], begr, "Shop-Rechnung + PayPal-Zahlungsbestätigung (Bildschirmausdruck)", "Zwei Dokumente mit gleichem Betrag und gleicher Rechnungsnummer (Rechnung + Zahlungsbestätigung), Hinweis „keine Rechnung“", E_ERST + " " + E_QUITT)


def k66():
    p = staff(66, "Dr.", fb="71")
    cid = "auslagenerstattung-k66"
    d, rd = "2027-11-03", "2027-11-12"
    v = vendor(67, "elec")
    its = [("Lüfter 80 mm, 12 V, kugelgelagert", 2, "9.95"), ("Temperaturfühler NTC, 1 m Kabel", 3, "6.45"), ("Kühlkörper 40 × 40 mm", 4, "2.15")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p), "RE-27-31870", d, "WS-2217730", its, 19, "Kreditkarte (bezahlt)", "de", "de")
    refund = D("19.90")
    mail = owa_mail(p["email"].split("@")[0], "Ihre Retoure R-27-4410: Erstattung veranlasst", f"{v['name']} Kundenservice <service@{v['mail'].split('@')[1]}>", f"{wd(rd)} 10:44", p["name"],
                    ["Guten Tag,", "", f"wir haben Ihre Rücksendung (2 × Lüfter 80 mm, 12 V) zur Rechnung RE-27-31870 erhalten (Retoure R-27-4410, Grund: Spannungsbereich ungeeignet).", f"Die Erstattung von {eur(refund)} € wurde auf Ihre Kreditkarte veranlasst und erscheint in den nächsten Tagen.", "Eine Gutschrift als Dokument erstellen wir nicht; diese Mail ist Ihr Nachweis.", "", "Freundliche Grüße", "Kundenservice"])
    claim = r2(total - refund)
    pvk = pvk_online("PVK-2027-07720", f"{wd(addday(rd, 3))} 11:30", p, "Kühlung und Sensorik für den Prüfaufbau, kurzfristig und dringend; die zwei Lüfter ungeeigneter Spannung wurden zurückgegeben und erstattet.",
                     [("Rechnung RE-27-31870", datef(d, "de2"), total), ("Erstattung Retoure R-27-4410 (2 Lüfter), laut Mail", datef(rd, "de2"), -refund)], claim, f"{p['ks']} / Auftrag {p['auftrag']}", mfmt="de", style=1)
    begr = (f"Rechnung {eur(total)} € (Lüfter, Fühler, Kühlkörper) an die Universität; zwei Lüfter (19,90 €) wurden zurückgeschickt, die Erstattung ist per Mail des Shops bestätigt. Beantragt ist der Saldo {eur(claim)} € = {eur(total)} € − 19,90 €, das Formular führt beide Posten auf.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Helvetica"), doc("email-retoure.pdf", mail, font="Helvetica"), doc("antrag-online.pdf", pvk, font="Helvetica")], begr, "Rechnung + Retouren-Mail des Shops (statt Gutschrift) + Online-Formular (Variante 1)", "Erstattung nur als Mail bestätigt (keine Gutschrift); beantragt ist der Saldo, nicht die Rechnungssumme", E_ERST + " (Saldo wie im Fall auslagenerstattung-05 der Organisatoren)")


def k67():
    p = staff(67, "Prof. Dr.", fb="75")
    cid = "auslagenerstattung-k67"
    d = "2027-05-20"
    txt, total = till("BÄCKEREI & CAFÉ LINDENHOF", "Lindenhang 12 · 35291 Wernstadt", "Tel. 0561 55 10 41", [("Kaffee Kanne 1,0 l", 3, "7.50"), ("Gebaeck Auswahl", 8, "2.40"), ("Mineralwasser 1,0 l", 3, "2.20"), ("Obstschale gross", 1, "9.90")], "EC-KARTE ***4471", f"{datef(d, 'de')} 08:47", "0550 KASSE 1", vat=7, hand=["Gaeste: Delegation Partneruniversitaet", "(6 Gaeste, Besprechung 09:30 Uhr,", "Raum 3.05) – Kaffee, Gebaeck, Wasser,", "Obst; Prof. " + p["last"]])
    guests = owa_mail(p["email"].split("@")[0], "Besuch der Delegation der Partneruniversität am 20. Mai", f"{p['plain']} <{p['email']}>", f"{wd(addday(d, -7))} 14:15", "Sekretariat FG " + p["fg"],
                      ["Liebe Frau Kollegin,", "", f"am {wdl(d)} um 09:30 Uhr besucht uns die sechsköpfige Delegation der Partneruniversität (Rektoratsreferent, drei Fachbereichsleitungen, zwei Doktoranden) zur Besprechung des Kooperationsabkommens, Raum 3.05.", "Bitte kümmern Sie sich um Kaffee, Gebäck, Mineralwasser und Obst für die Gäste.", "", "Danke und Gruß", p["plain"]])
    begr = (f"Kaffee, Gebäck, Mineralwasser und Obst ({eur(total)} €) für eine sechsköpfige externe Delegation: das sind die üblichen Gesten der Höflichkeit gegenüber Gästen der Universität, keine Bewirtung im Sinne der Richtlinie, und aus Landesmitteln erstattungsfähig. Zweck und Gästezahl sind auf dem Bon vermerkt und durch die Vorab-Mail belegt; Artikel einzeln bezeichnet.")
    e_case(cid, [doc("bon.pdf", txt, size=RECEIPT, jitter=0.6), doc("vorab-email.pdf", guests, font="Helvetica")], begr, "Bäckerei-Kassenbon (7 % MwSt) mit handschriftlichem Zweck + Vorab-Mail an das Sekretariat", "Bewirtung ohne Teilnehmerliste/Bewirtungsbeleg, weil nur Kaffee/Gebäck/Wasser/Obst für Gäste (Geste der Höflichkeit)", E_GESTE, "medium")


def k68():
    p = staff(68, "Prof. Dr.", fb="72")
    h2 = staff(168, "Dr.", fb="72")
    cid = "auslagenerstattung-k68"
    d = "2027-06-24"
    guests = ["Prof. Dr. Alina Wöhrle-Tran (Universität Aachen)", "Dr. Henrik Vasquez (Institut für Prozesstechnik)", "Dipl.-Ing. Marta Szymanski (Firma Rotor & Co.)", "Dr. Yusuf Adeyemi (Forschungszentrum Nord)", "Prof. Dr. Jean-Luc Fabre (INSA Lyon)"]
    items_ = [("Vorspeise: Spargelcremesuppe", 7, "7.80"), ("Hauptgang: Zanderfilet/Rinderfilet/Pasta", 7, "21.90"), ("Dessert", 7, "6.80"), ("Mineralwasser 0,75 l", 5, "6.20"), ("Weißwein Schorle 0,3 l", 6, "4.60"), ("Kaffee", 7, "3.20")]
    sumg = tot(*[q * D(u) for _, q, u in items_])
    per = r2(sumg / 7)
    assert per <= D("60.00")
    net, v = vat_split(sumg, 19)
    bill = ["RISTORANTE ZUM ALTEN BAHNHOF", "Bahnhofsplatz 2 · 35291 Wernstadt", "Steuernummer 66/118/20944 · Tel. 0561 55 77 20", "", lr(f"Rechnung Nr. 20270624-0087", f"Registriernummer (TSE): R-4417-8802-31", 96), lr(f"Datum {datef(d, 'de')} · Tisch 12", "Ort des Verzehrs: Ristorante Zum Alten Bahnhof, Wernstadt", 96), "",
            f"Rechnungsempfänger: {UW}, FG {p['fg']}, {UW_ADDR}", "Anlass: Abendessen nach dem Kolloquium „Prozessintensivierung“ (Gäste: siehe Teilnehmerliste)", "", row(["Menge", "Bezeichnung", "Einzel", "Gesamt"], [5, 54, 9, 10], "rlrr")]
    bill += [row([str(q), t_, eur(D(u)), eur(q * D(u))], [5, 54, 9, 10], "rlrr") for t_, q, u in items_]
    bill += ["", row(["", "Rechnungsbetrag brutto", "", eur(sumg)], [5, 54, 9, 10], "rlrr"), row(["", f"darin 19 % MwSt (netto {eur(net)})", "", eur(v)], [5, 54, 9, 10], "rlrr"), "Trinkgeld: nicht enthalten, nicht erstattet.", "", f"Zahlung: Kreditkarte {p['plain']}, ****6021", "Gesehen und bestätigt (Bewirtender), handschriftlich unterschrieben: M. " + p["last"] + "  –  " + p["name"],
             "TSE-Signatur: 7c41e2 9a0b13 44d5ff  Start 21:42:11  Stop 22:07:30"]
    tl = ["Teilnehmerliste zur Bewirtung am " + datef(d, "de") + " (Ristorante Zum Alten Bahnhof)", "", "GÄSTE (extern):"] + [f"  {i}. {g}" for i, g in enumerate(guests, 1)] + ["", "UNIVERSITÄTSBEDIENSTETE:", f"  6. {p['name']} (Gastgeber)", f"  7. {h2['name']} (Projektleitung)", "",
          "Verhältnis extern/intern: 5 : 2. Kosten je Person " + eur(per) + " € (Höchstsatz Veranstaltungstag: 60,00 €)."]
    einl = owa_mail(p["email"].split("@")[0], "Einladung: Kolloquium Prozessintensivierung am 24. Juni 2027, 16:00 Uhr", f"{p['plain']} <{p['email']}>", f"{wd(addday(d, -21))} 09:00", "Verteiler Gäste Kolloquium",
                    ["Sehr geehrte Kolleginnen und Kollegen,", "", f"herzlich lade ich Sie zum Kolloquium „Prozessintensivierung“ am {wdl(d)}, 16:00 Uhr (Hörsaal 3), im Rahmen des Verbundprojekts ProIntens ein. Im Anschluss laden wir zum gemeinsamen Abendessen ein, um die Zusammenarbeit im Projekt zu vertiefen.", "", "Mit freundlichen Grüßen", p["plain"]])
    kk = card_statement("kredit", p["plain"], [(d, "RISTORANTE ZUM ALTEN BAHNHOF WERNSTADT", -sumg, None), (addday(d, 2), "BUCHHANDLUNG AM UHRTURM", -D("27.80"), None)], "Juni 2027")
    pvk = pvk_online("PVK-2027-08105", f"{wd(addday(d, 4))} 10:10", p, "Bewirtung der externen Gäste des Projekt-Kolloquiums „Prozessintensivierung“ (Verbundprojekt ProIntens). Finanzierung aus Drittmitteln; die Vertragsbedingungen des Drittmittelgebers lassen Bewirtung zu (Projekttreffen dient dem Fortgang des Projekts).",
                     [(f"Bewirtungsbeleg Nr. 20270624-0087, Ristorante Zum Alten Bahnhof (7 Personen, 5 Gäste)", datef(d, "de2"), sumg)], sumg, f"{p['dr_auftrag']} (Drittmittel ProIntens)", extra=["Anlagen: Bewirtungsbeleg, Teilnehmerliste, Einladung, Kartenabrechnung."], mfmt="de", style=1)
    begr = (f"Bewirtungsbeleg erfüllt die Anforderungen: maschinell erstellt mit Registriernummer, Speisen und Getränke einzeln, Datum und Ort, Rechnungsempfänger Universität, Betrag mit MwSt, Anschrift und Steuernummer der Gaststätte, Unterschrift des Bewirtenden, Teilnehmerliste mit Gästen (5) und Bediensteten (2) getrennt. Kosten je Person {eur(per)} € unter 60 €, kein Trinkgeld. "
            "Anlass durch Einladung belegt, Finanzierung aus Drittmitteln mit zulässigen Bedingungen.")
    e_case(cid, [doc("bewirtungsbeleg.pdf", "\n".join(bill), font="Helvetica"), doc("teilnehmerliste.pdf", "\n".join(tl), font="Helvetica"), doc("einladung-kolloquium.pdf", einl, font="Helvetica"), doc("kartenabrechnung.pdf", kk), doc("antrag-online.pdf", pvk, font="Helvetica")], begr,
            "Restaurant-Bewirtungsbeleg mit TSE-Angaben + Teilnehmerliste (Gäste/Bedienstete getrennt) + Einladung + Kartenabrechnung + Online-Formular (Variante 1)", "Bewirtung nach Richtlinie: 5 externe Gäste, 2 Bedienstete, ~44 €/Person, kein Trinkgeld; Trinkgeld-Zeile „nicht enthalten“ (Negation)",
            "„Der Bewirtungsbeleg (Rechnung) muss maschinell erstellt und mit einer Registriernummer versehen sein, … auf den Rechnungsempfänger (Universität Kassel) ausgestellt sein … vom Bewirtenden unterschrieben sein … und die Namen der bewirteten Personen ausweisen (ggf. separate Teilnehmerliste).“ und „Pro Person und Veranstaltungstag € 60,-.“", "low")


def k69():
    p = staff(69, "", fb="71")
    cid = "auslagenerstattung-k69"
    d = "2027-12-02"
    txt, total = till("ELEKTRO-FACHMARKT WEBER", "Bahnhofstrasse 7 · 33098 Paderborn", "05251 70 22 15", [("Batterie Lithium CR2032 4er", 2, "5.99"), ("Steckernetzteil 5V 2A", 1, "12.95"), ("Akku-Ladegeraet AA/AAA", 1, "9.99")], "EC-KARTE ***4471", f"{datef(d, 'de2')} 10:22", "6620 KASSE 2", ["Garantie: 24 Monate (Beleg aufbewahren)", "Sie sparten heute 3,20 EUR"],
                      hand=["Feldmessgeraet Ausfall – Ersatz", "fuer Messkampagne (Batterien, Netzteil,", "Ladegeraet) – FG " + p["fg"]])
    begr = (f"Elektrofachmarkt-Bon über {eur(total)} € mit Artikeln (Batterien, Netzteil, Ladegerät); handschriftlich ist der dienstliche Anlass genannt (Ausfall von Feldmessgerät, Ersatz für die Messkampagne). Kleine, dringende Anschaffung, privat per EC-Karte gezahlt; Hinweise zu Garantie und Ersparnis (3,20 €) sind nur Werbezeilen.")
    e_case(cid, [doc("beleg.pdf", txt, size=RECEIPT, jitter=0.5)], begr, "Schmaler Elektromarkt-Bon mit Garantiehinweis und Ersparniszeile", "Werbezeile „Sie sparten 3,20 EUR“ ist nicht der Erstattungsbetrag; Stichwort handschriftlich", E_QUITT)


def k70():
    p = staff(70, "Dr.", fb="74")
    cid = "auslagenerstattung-k70"
    d = "2027-03-31"
    tk = "\n".join(["WERNSTADTER VERKEHRSBETRIEBE", "Tageskarte Zone 1 (Einzelperson)", f"gültig {datef(d, 'de')} bis 03:00 Uhr Folgetag", "Preis 5,80 EUR inkl. 7 % MwSt", f"Automat 044 · {datef(d, 'de')} 09:12", "Ticket-Nr. 4410-7721-88", "",
                    "Handschriftlich:", f"Grund: Abstimmungstermin Probenahme Flussgebiet", "Ziel: Amt für Wasserwirtschaft, Hauptstr. 4, Wernstadt", f"Dienstgang am {datef(d, 'de')}, 10:00–12:30 Uhr", f"{p['plain']}, FG {p['fg']}"])
    begr = ("Tageskarte des Nahverkehrs für einen Dienstgang am Dienstort (Abstimmungstermin beim Amt für Wasserwirtschaft); Grund und Ziel des Dienstganges sind handschriftlich angegeben, wie es für Fahrscheine verlangt ist. Reisen am Dienstort brauchen in der Regel keine Genehmigung; kleiner Betrag 5,80 €.")
    e_case(cid, [doc("fahrschein.pdf", tk, size=RECEIPT, jitter=0.6)], begr, "Automaten-Tageskarte (schmal) mit handschriftlichem Grund und Ziel des Dienstganges", "Fahrschein ohne Rechnung, nur mit Grund und Ziel; Dienstgang am Dienstort", "„Fahrscheine: Der Grund und das Ziel des Dienstganges sind anzugeben.“ und „Reisen am Dienstort müssen in der Regel nicht genehmigt werden.“", "low", SRC_GLOS + "; " + SRC_DRM)


def k71():
    p = staff(71, "Dr.", fb="76")
    cid = "auslagenerstattung-k71"
    d = "2027-02-25"
    v = vendor(71, "werk")
    its = [("Schutzbrille klar, EN 166, Überbrille", 4, "6.90"), ("Laborkittel Baumwolle, Gr. L", 1, "24.50"), ("Einmal-Überschuhe, 100 St", 1, "11.90")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p, "Labor 2.06"), "BAR-27-0412", d, "Kasse", its, 19, "Barzahlung", "iso", "eur", ["BETRAG DANKEND BAR ERHALTEN  " + datef(d, "de") + "   (Stempel / Unterschrift Kasse)"], title="RECHNUNG / Quittung")
    begr = (f"Rechnung/Quittung über {eur(total)} € (Schutzbrillen, Laborkittel, Überschuhe) an die Universität, mit Stempelvermerk „Betrag dankend bar erhalten“; Barzahlung durch die Mitarbeiterin, Artikel benannt. Schutzausrüstung für ein Praktikum, kurzfristig benötigt; Original-Quittung liegt vor.")
    e_case(cid, [doc("rechnung-quittung.pdf", txt, font="Helvetica", jitter=0.5)], begr, "Rechnung mit Barzahlungsstempel („dankend bar erhalten“) ohne weitere Zahlungsnachweise", "Barzahlung statt Karte: Quittungsstempel statt Kontoauszug", E_ERST)


def k72():
    p = staff(72, "Dr.", fb="78")
    cid = "auslagenerstattung-k72"
    d = "2027-09-27"
    rate = D("0.9660")
    chf = D("120.00")
    e_ = r2(chf * rate)
    fee = r2(e_ * D("0.0175"))
    assert e_ == D("115.92")
    rec = "\n".join(["Institut für angewandte Bildungsforschung, Zürich", "Seestrasse 118, 8002 Zürich, Schweiz", "", p["name"], f"{UW}, FG {p['fg']}", UW_ADDR, "", lr("Quittung / Receipt Q-27-5530", f"Datum {datef(d, 'long')}", 100), "",
                     "Online-Seminar „Qualitative Interviews auswerten“ (3 Abende per Videokonferenz, 5.–7. Oktober 2027)", "Teilnahmegebühr CHF 120.00", "Bezahlt per Kreditkarte. Keine Mehrwertsteuer (Leistungsort außerhalb der EU).", "", "Die Veranstaltung findet ausschließlich online statt."])
    kk = card_statement("kredit", p["plain"], [(addday(d, 1), "IABF ZUERICH CH", -e_, f"CHF {chf:,.2f} Kurs {str(rate).replace('.', ',')}"), (addday(d, 1), "Auslandseinsatzentgelt", -fee, "nicht Bestandteil des Antrags"), (addday(d, 6), "NORDMARKT SUPERMARKT", -D("38.12"), None)], "Oktober 2027")
    begr = (f"Online-Seminar (nur per Videokonferenz) – keine Dienstreise, die Teilnahmegebühr CHF 120,00 ist privat zu verauslagen und bei der Finanzabteilung geltend zu machen. Die Quittung benennt Veranstaltung und Betrag, die Kartenabrechnung zeigt den belasteten Betrag {eur(e_)} € (Kurs 0,9660); beantragt ist dieser Betrag ohne das Auslandseinsatzentgelt.")
    e_case(cid, [doc("quittung-zuerich.pdf", rec, font="Times-Roman"), doc("kartenabrechnung.pdf", kk)], begr, "Quittung eines Schweizer Anbieters in CHF (Langdatum) + Kreditkartenabrechnung mit Kurs", "Fremdwährung CHF mit Kurs 0,9660; keine MwSt wegen Drittland; Entgelt-Zeile ausdrücklich nicht beantragt", R_ONLINE, "medium", SRC_DRM)


def k73():
    p = staff(73, "", fb="71")
    cid = "auslagenerstattung-k73"
    d = "2027-07-08"
    v = vendor(73, "elec")
    its = [("MCP9808T-E/MS Digital Temp Sensor", 5, "1.83"), ("TMP117AIDRVR", 3, "3.12"), ("SN74LVC1G125DBVR", 10, "0.31"), ("Pin header 2.54 1x40", 4, "0.46")]
    txt, total = invoice_shop(v, UBUY(p), DEL(p, "Elektroniklabor"), "DS-27-558110", d, "AB-77412", its, 19, "Kreditkarte (bezahlt)", "us" if False else "slash", "en-eur", ["Versand: Brief, versandkostenfrei."], title="Rechnung / Invoice")
    kk = card_statement("kredit", p["plain"], [(addday(d, 1), "DISTRIBUTOR KONTAKTE ERFURT", -total, None), (addday(d, 3), "BAECKEREI MOELLER", -D("4.90"), None)], "Juli 2027")
    note = "\n".join(["Stichwort zur Rechnung DS-27-558110:", "Temperatursensoren und Zubehör (Bauteile) fuer", "den Praktikumsversuch „Temperaturmessung” am 12.07. –", "Lieferung ueber SAP nicht rechtzeitig moeglich.", p["plain"] + ", FG " + p["fg"]])
    begr = (f"Rechnung über {eur(total)} € an die Universität; die Positionen sind Herstellerbezeichnungen (MCP9808, TMP117 usw.), im handschriftlichen Stichwort als Temperatursensoren und Zubehör für einen Praktikumsversuch erklärt; privat per Kreditkarte bezahlt, Abrechnung zeigt dieselbe Belastung.")
    e_case(cid, [doc("rechnung.pdf", txt, font="Helvetica"), doc("kartenabrechnung.pdf", kk), doc("stichwort.pdf", note, font="Helvetica", jitter=0.7)], begr, "Rechnung mit Typenbezeichnungen (Bauteile) + Kartenabrechnung + handschriftliches Stichwort", "Positionsbezeichnungen sind nur Typennummern; Erklärung steht nur im Stichwort; Beträge „EUR 1.83“ als en-eur", E_QUITT)


def k74():
    p = staff(74, "Dr.", fb="72")
    cid = "auslagenerstattung-k74"
    d = "2027-04-22"
    txt, total = till("HAGEBAU CENTER KRAUSE", "Gewerbepark Nord 4 · 24103 Kiel", "Tel. 0431 88 10 20 · www.krause-center.example", [("Gewindestange M8 1m verzinkt", 4, "2.95"), ("Sechskantmutter M8 100 St", 1, "6.49"), ("Unterlegscheibe M8 100 St", 1, "4.29"), ("Winkelverbinder 90x90", 6, "1.19")], "EC-KARTE ***4471", f"{datef(d, 'de')} 15:58", "0023-7731", vat=19,
                      footer=["", "Ihre Bonuspunkte heute: 38 (Stand 1.240)", "Sie sparten 12,10 EUR mit Ihren Coupons", "Gewinnspiel: Hauptgewinn 5.000 EUR!", "Rückgabe innerhalb von 14 Tagen mit Bon", "Gutschein 10 EUR ab 100 EUR Einkauf"], hand=["Halterung Messaufbau (Gewindestangen,", "Muttern, Scheiben, Winkel) FG " + p["fg"], "dringend – Versuch am Freitag"])
    begr = (f"Baumarktbon über {eur(total)} € mit allen Artikeln (Gewindestangen, Muttern, Scheiben, Winkel) und handschriftlichem Zweck (Halterung für den Messaufbau). Die vielen Werbebeträge im Fuß (Ersparnis 12,10 €, Hauptgewinn 5.000 €, Gutschein 10 €, Bonuspunkte) gehören nicht zur Zahlung; maßgeblich ist die Summe {eur(total)} €. Kleine dringende Anschaffung.")
    e_case(cid, [doc("kassenbon.pdf", txt, size=RECEIPT, jitter=0.5)], begr, "Baumarkt-Kassenbon mit Werbe- und Bonuszeilen im Fuß", "Fremde Beträge im Fuß (Ersparnis 12,10 €, Hauptgewinn 5.000 €, Gutschein 10 €, Bonuspunkte 38/1.240) – nur die Summe zählt", E_QUITT)


def k75():
    p = staff(75, "Dr.", fb="72")
    cid = "auslagenerstattung-k75"
    d0 = "2027-10-26"
    v = vendor(75, "werk")
    its = [("Bohrer-Set HSS 1–10 mm, 19-tlg", 1, "21.90"), ("Gewindebohrer-Set M3–M10", 1, "31.50"), ("Messschieber analog 150 mm", 1, "9.99")]
    total = tot(*[q * D(u) for _, q, u in its])
    sub = tot(*[q * D(u) for _, q, u in its]) + D("3.99")
    bb = "\n".join([v["name"], v["street"] + " · " + v["plz"] + " " + v["city"], "", f"Auftragsbestätigung AB-27-7712 zu Ihrer Bestellung 27-77120 vom {datef(d0, 'de')}", f"Kunde: {UW}, FG {p['fg']}, z. Hd. {p['plain']}", ""] +
                   [f"  {q} x {d_}  {eur(D(u))} €" for d_, q, u in its] + [f"  Versandkosten  3,99 €", f"  Voraussichtlicher Gesamtbetrag  {eur(sub)} € (inkl. 19 % USt)", "", "Dies ist keine Rechnung. Lieferung in 2–3 Werktagen."])
    ls = "\n".join([v["name"], f"LIEFERSCHEIN LS-27-4521 vom {datef(addday(d0, 2), 'de')}", f"Zu Bestellung 27-77120, Auftrag AB-27-7712", "", f"Empfänger: {UW}, FG {p['fg']}, {UW_ADDR}", ""] + [f"  {q} x {d_}" for d_, q, u in its] + ["  Versand", "", "Paket 1 von 1, 1,2 kg. Kein Preisausweis auf diesem Lieferschein. Rechnung folgt separat per E-Mail."])
    rg, g = invoice_shop(v, UBUY(p), DEL(p), "RE-27-18820", addday(d0, 2), "27-77120", its, 19, "Kreditkarte (bezahlt)", "de", "de", ["Diese Rechnung bezieht sich auf die Auftragsbestätigung AB-27-7712 und den Lieferschein LS-27-4521 (derselbe Auftrag)."], ship=D("3.99"))
    assert g == sub
    zb = "\n".join(["Kreditkartenabrechnung · Visa ****4471 · " + p["plain"], "", f"{datef(addday(d0, 3), 'de')}  {v['name'].upper()[:36]}  {v['city'].upper()}   -{eur(g)} EUR", "", "Zahlungsnachweis zur Bestellung 27-77120 / Rechnung RE-27-18820"])
    begr = (f"Alle vier Dokumente gehören zu derselben Bestellung 27-77120: Auftragsbestätigung (ausdrücklich keine Rechnung), Lieferschein (ohne Preise), Rechnung RE-27-18820 über {eur(g)} € und Zahlungsnachweis über denselben Betrag. Die Rechnung ist die einzige Abrechnungsgrundlage, es wird nur einmal {eur(g)} € beantragt; Werkzeuge (Bohrer, Gewindebohrer, Messschieber) für die Werkstatt, an die Universität adressiert.")
    e_case(cid, [doc("auftragsbestaetigung.pdf", bb, font="Helvetica"), doc("lieferschein.pdf", ls, font="Helvetica"), doc("rechnung.pdf", rg, font="Helvetica"), doc("zahlung.pdf", zb)], begr, "Vier Dokumente zu EINER Bestellung (Auftragsbestätigung, Lieferschein, Rechnung, Zahlungsnachweis), Beträge in drei davon gleich", "Derselbe Betrag 67,38 € in mehreren Dokumenten (Bestätigung, Rechnung, Zahlung) – kein Doppelantrag; ausdrücklich „keine Rechnung“ / „Rechnung folgt separat“", E_ERST)
    assert total + D("3.99") == g


# =========================================================================== #
# build, verify, README
# =========================================================================== #
UNSURE = {
    "dienstreiseantrag-k10": "Stiftungszuschuss als Leistung von dritter Seite: die Seite verlangt nur die Angabe; ob ein pauschaler Zuschuss einfach abgezogen werden darf, ist nicht ausdrücklich geregelt.",
    "dienstreiseantrag-k12": "Exkursionsantrag, Teilnehmerliste und zwei Reiseanträge gehören zu einem eigenen Verfahren (Exkursionssachbearbeitung); ob die Unterlagen als „Dienstreiseantrag“ vollständig sind, ist nicht an einem Praxisfall belegt.",
    "dienstreiseantrag-k22": "Französische Dokumente und Cocktail in der Gebühr; Hotelsatz 69 € gegen den ARV-Satz Frankreich nicht nachgeschlagen (ARV nicht im Korpus).",
    "dienstreiseantrag-k23": "Eintägige Auslandsreise: A1 und Tagegeld-Kürzung für gestellte Verpflegung sind nur sinngemäß aus den Seiten abgeleitet.",
    "auslagenerstattung-k52": "Teilerstattung eines gemischten Bons (private Positionen durchgestrichen): die Seite regelt das nicht ausdrücklich.",
    "auslagenerstattung-k56": "Bücher sollen laut Drittmittelglossar grundsätzlich über die Bibliothek beschafft werden; ein Praxisfall (auslagenerstattung-01) wurde angenommen.",
    "auslagenerstattung-k57": "Kopie derselben Rechnung im Antrag: Seite fordert die Originalquittung; das Original liegt bei, die Kopie ist als solche markiert.",
    "auslagenerstattung-k61": "Reverse-Charge-Rechnung mit 0 % USt bei privater Kartenzahlung; steuerlich nicht näher geregelt.",
    "auslagenerstattung-k67": "Gesten der Höflichkeit sind keine Bewirtungskosten, aber die Grenze zwischen Geste und Bewirtung (Gebäck für 6 Gäste) ist unscharf.",
    "auslagenerstattung-k68": "Vollständige Bewirtung mit Restaurantbeleg: alle Pflichtangaben der Richtlinie sind erfüllt, aber es gibt viele Einzelanforderungen (Verhältnis extern/intern, Drittmittelbedingungen) und keinen Praxisfall.",
    "auslagenerstattung-k70": "Fahrschein-Dienstgang: nur der Satz „Der Grund und das Ziel des Dienstganges sind anzugeben“ im Drittmittelglossar; ob ein Fahrschein ohne Rechnung als Erstattungsbeleg genügt, ist nicht belegt.",
    "auslagenerstattung-k72": "Online-Seminar statt Konferenz/Tagung: die Seite nennt „Konferenzen und Tagungen“; Fortbildungsseminar online wurde sinngemäß gleich behandelt.",
    "beschaffungsantrag-k35": "Ablauf des Rahmenvertrags Büromöbel nur aus einem Absatz der Seite abgeleitet; Rahmenvertragspartner sind pseudonymisiert.",
    "beschaffungsantrag-k40": "Gerätefondsverfahren: Vordruck und Anforderungen aus der Seite nachgebaut, kein Praxisfall; Betrag 20.580 € netto.",
    "beschaffungsantrag-k41": "Zuschlag an das zweitgünstigste Angebot mit Ausschlussbegründung: die Seiten sagen nichts zu Ausschlüssen, nur „vergleichbare Angebote“.",
    "beschaffungsantrag-k42": "Innergemeinschaftliche Lieferung ohne USt: Wertung netto ist nur von der Praxis (Vergabevermerk „Preis netto“) gedeckt.",
    "beschaffungsantrag-k44": "Drittmittelbeschaffung: die Seite verweist auf den Bewilligungsbescheid („zum Teil andere Wertgrenzen“); der Bescheid-Auszug ist erfunden.",
}


def build():
    for s in SETS:
        shutil.rmtree(OUT / s, ignore_errors=True)
    problems, n_pdf = [], 0
    for c in CASES:
        d = OUT / c["set"] / "inputs" / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        for name, content, opts in c["docs"]:
            p = d / name
            write_pdf2(p, content, **opts)
            n_pdf += 1
            text = all_text(content)
            problems += B.weekday_problems(c["id"], name, text)
            out = pdftotext(p)
            got, want = out.split(), text.replace("\f", "\n").split()
            if got != want:
                g, w = "".join(got), "".join(want)
                if g != w:
                    k = next((i for i, (a, b_) in enumerate(zip(g, w)) if a != b_), min(len(g), len(w)))
                    problems.append(f"{c['id']}/{name}: round-trip differs at char {k}: got {g[k:k + 30]!r} want {w[k:k + 30]!r}")
            if len(out.strip()) < 40:
                problems.append(f"{c['id']}/{name}: almost no extractable text")
    return n_pdf, problems


def table():
    n = {s: sum(c["set"] == s for c in CASES) for s in SETS}
    out = ["| id | system / layout | tricky detail | why compliant (rule quote + source page) | confidence |", "|---|---|---|---|---|"]
    for c in CASES:
        cells = [c["id"], c["sys"], c["trick"], f"{c['rule']} — {c['src']}", c["conf"]]
        out.append("| " + " | ".join(x.replace("|", "/") for x in cells) + " |")
    return "\n".join(out)


NEUTRAL = re.compile(r"^(scan_|Scan_|IMG_|Dokument|anlage-|accepted|bahn\.pdf|hotel\.pdf|mail\.pdf|rail\.pdf|beleg\.pdf|antrag\.pdf|wps\.pdf|zahlung|angebot-\d|quote-\d)", re.I)


def stats():
    docs = [(c, d) for c in CASES for d in c["docs"]]
    neutral_cases = sum(1 for c in CASES if any(re.match(r"^(scan_|Scan_|IMG_|Dokument|anlage-)", d[0]) for d in c["docs"]))
    merged = sum(1 for c in CASES for d in c["docs"] if isinstance(d[1], list) or "\f" in d[1])
    n_pdf = len(docs)
    by_conf = {k: sum(c["conf"] == k for c in CASES) for k in ("high", "medium", "low")}
    return n_pdf, neutral_cases, merged, by_conf


def readme():
    n_pdf, neutral_cases, merged, by_conf = stats()
    low = [c for c in CASES if c["conf"] != "high"]
    L = [
        "# clean-ood: 75 correct cases for false-alarm measurement",
        "",
        "Test set of 75 approvable (`angenommen`) German university admin cases as PDFs, built to measure how often a document-reading program raises "
        "false alarms on correct documents it has never seen: 25 business-trip requests (`dienstreiseantrag-k01..k25`), 25 procurement requests "
        "(`beschaffungsantrag-k26..k50`), 25 expense refunds (`auslagenerstattung-k51..k75`). All labels are `angenommen`, so any rejection is a false alarm. "
        "The university is pseudonymised as „Universität Wernstadt“; people, firms, numbers and IBANs are invented (IBAN check digits are wrong on purpose).",
        "",
        "## How it was built",
        "",
        "`python3 experiments/clean-ood/tools/make_clean.py` writes everything (idempotent, overwrites the three set folders and this README). "
        "Layout is the same as the organisers' practice data: `<set>/inputs/<case-id>/*.pdf` plus `<set>/ground-truth.jsonl` "
        "(`{\"antrag\", \"result\": \"angenommen\", \"begruendung\"}`). No decision trail is needed because nothing is rejected.",
        "",
        "- The rules are held constant, the FORM varies. Every case passes the University of Kassel rules in `the University of Kassel policy pages (not included here)` "
        "(dienstreisemanagement, finanzbuchhaltung-und-steuern, beschaffung, rahmenvertraege, nachhaltiges-catering, geraetefondsverfahren, "
        "drittmittel-projektdurchfuehrung and related pages). Sums, VAT splits, weekdays, advance payments (80 %) and per-km amounts are computed and "
        "asserted in the script.",
        "- Imitated systems: SAP Fiori travel prints, ESS-style request forms (organisers' layout), online-form prints, scanned paper forms with text jitter, "
        "SAP SRM carts, WPS shop carts (framework contracts, Ersteller/Besteller), web-shop carts and invoices, Outlook/OWA mail prints, rail/hotel/airline "
        "portals, till receipts (narrow pages), card and bank statements, PayPal confirmations, English, French and Polish-Euro vendor documents.",
        f"- {n_pdf} PDFs in total. {neutral_cases} cases carry neutral file names (scan_0001, Dokument, IMG_2231, anlage-3 and so on, more than a third); "
        f"{merged} files are merged multi-page PDFs (several documents in one file, pages in random order, mixed fonts and page sizes). "
        "Document order inside a case is not the order of the process.",
        "- Formats vary on purpose: amounts `1.234,56 €` / `1234.56 EUR` / `EUR 1 234,56` / `EUR 1,234.56` / `€1,234.56`, dates `14.03.2027` / `14.03.27` / `2027-03-14` / "
        "`14 March 2027` / `March 14, 2027` / `14/03/2027` / `14-MAR-2027` / `14. März 2027`, ticks in `[X] [x] [×] (x) (•) [/] [*]` and in odd glyphs "
        "(`[✔] [✘] [✓] [■]`, drawn with the ZapfDingbats font).",
        "- Tricky-but-fine details are listed per case in the table: wrapped lines, negations (`kein Honorar`, `wird nicht gezahlt`, `Mietwagen: nein`), "
        "footnotes with amounts that are not the claim, claims lower than receipts (private items struck out), credit notes deducted correctly, a copy of an invoice "
        "marked `KOPIE`, cover e-mails with amounts in the body, framework-contract orders without offers, three offers in unusual layouts (letters, tables, "
        "mails, one page each in a merged file, side by side), abroad trips to allowed countries, a conference fee that includes a reception, third-party funding declared.",
        "- Verification inside the script: every PDF is run through `pdftotext -layout` and its words (or, for glyph pages, its characters) must equal the text that was written; "
        "weekday names next to dates are checked against the calendar.",
        "",
        f"Confidence: {by_conf['high']} high, {by_conf['medium']} medium, {by_conf['low']} low (details below). Treat `low` as 'exclude when measuring the false-alarm rate "
        "if in doubt'; `medium` cases are clearly defensible but rest on a looser reading of a rule page.",
        "",
        "## Blindness statement",
        "",
        "Written blind. I did NOT open `facts.py`, `rules.py`, `predict.py`, `rule_search.py`, `parsing.py`, `case_tools.py`, any `test_*.py`, `experiments/traps/`, "
        "`experiments/layouts/`, or any `review notes`, robustness or rule-gap file. A directory listing of the repository root, `experiments/` and `the development notes (not included)` "
        "showed those file and folder NAMES (for example `facts.py`, `traps`, `layouts`, `robustness-audit.md`, `rule-gaps-2.md`), but none of them was read. "
        "What I read: `experiments/blind4/tools/make_blind4.py` (its layout, money, date, Fiori and OWA helpers are loaded by the script, not copied), "
        "`experiments/blind4-proposals/PROPOSALS.md`, the organisers' practice cases with READMEs and ground truth in `~/dev/uniagent-code/cikm26/datasets/*/` (to learn what "
        "correct cases contain), and the policy pages in `the University of Kassel policy pages (not included here)`. No model was run. Nothing was committed.",
        "",
        "## Cases to treat with care",
        "",
    ]
    for c in low:
        L.append(f"- `{c['id']}` ({c['conf']}): {UNSURE.get(c['id'], '')}")
    L += ["", "## Table", "", table(), ""]
    return "\n".join(L)


def check_set():
    probs = []
    ids = [c["id"] for c in CASES]
    if len(set(ids)) != len(ids):
        probs.append("duplicate case ids")
    for s, prefix, lo, hi in ((TRIP, "dienstreiseantrag-k", 1, 25), (PROC, "beschaffungsantrag-k", 26, 50), (EXP, "auslagenerstattung-k", 51, 75)):
        want = [f"{prefix}{i:02d}" for i in range(lo, hi + 1)]
        have = [c["id"] for c in CASES if c["set"] == s]
        if sorted(have) != want:
            probs.append(f"{s}: ids {sorted(set(want) ^ set(have))}")
    for c in CASES:
        if c["conf"] not in ("high", "medium", "low"):
            probs.append(f"{c['id']}: bad confidence")
        if c["conf"] != "high" and c["id"] not in UNSURE:
            probs.append(f"{c['id']}: confidence {c['conf']} without a note in UNSURE")
    return probs


NEUTRALIZE = {"dienstreiseantrag-k03": "scan", "dienstreiseantrag-k06": "anlage", "dienstreiseantrag-k07": "dok", "dienstreiseantrag-k13": "img", "dienstreiseantrag-k16": "anlage",
              "dienstreiseantrag-k18": "scan", "dienstreiseantrag-k21": "dok", "beschaffungsantrag-k29": "anlage", "beschaffungsantrag-k31": "img", "beschaffungsantrag-k34": "scan",
              "beschaffungsantrag-k38": "dok", "beschaffungsantrag-k46": "anlage", "beschaffungsantrag-k48": "img", "auslagenerstattung-k53": "scan", "auslagenerstattung-k55": "dok",
              "auslagenerstattung-k58": "img", "auslagenerstattung-k64": "anlage", "auslagenerstattung-k66": "scan", "auslagenerstattung-k71": "img", "auslagenerstattung-k75": "dok"}


def neutralize():
    """rename the files of selected cases to neutral names and put them in random order"""
    for c in CASES:
        style = NEUTRALIZE.get(c["id"])
        if not style:
            continue
        order = list(range(len(c["docs"])))
        random.Random("nm-" + c["id"]).shuffle(order)
        new = []
        for pos, idx in enumerate(order, 1):
            _, content, opts = c["docs"][idx]
            nm = {"scan": f"scan_{pos:04d}.pdf", "img": f"IMG_{2200 + pos * 7 + len(c['id'])}.pdf", "anlage": f"anlage-{pos}.pdf", "dok": "Dokument.pdf" if pos == 1 else f"Dokument ({pos}).pdf"}[style]
            new.append((nm, content, opts))
        c["docs"] = new
        c["sys"] += " [neutrale Dateinamen, zufällige Reihenfolge]"


def main():
    fns = [f for n, f in sorted(globals().items()) if re.fullmatch(r"k\d\d", n)]
    for fn in fns:
        fn()
    neutralize()
    CASES.sort(key=lambda c: (SETS.index(c["set"]), c["id"]))
    if "--table" in sys.argv:
        print(table())
        return
    n_pdf, problems = build()
    problems += check_set()
    for s in SETS:
        with open(OUT / s / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for c in CASES:
                if c["set"] == s:
                    f.write(json.dumps({"antrag": c["id"], "result": "angenommen", "begruendung": c["begr"]}, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text(readme(), encoding="utf-8")
    print(f"built {len(CASES)} cases, {n_pdf} PDFs in {OUT}")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
