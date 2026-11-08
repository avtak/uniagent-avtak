#!/usr/bin/env python3
"""Build the LAYOUT-INVARIANCE (metamorphic) test set for UniAgent Task 2.

A layout case is a copy of a practice case in which only the PRESENTATION changes: file names,
checkbox glyphs, label wording, number and date formats, document structure, or an addition that
carries no new fact. No amount, date, name, item, signature or attachment changes, so every layout
case keeps the organisers' label of its source case. A solver that flips its decision on one of
these is reading layout, not facts. They are TESTS ONLY: never used to tune prompts, rule cards or code.

    python3 experiments/layouts/tools/make_layouts.py            # build everything
    python3 experiments/layouts/tools/make_layouts.py --check    # build + verify, exit 1 on problems
    python3 experiments/layouts/tools/make_layouts.py --table    # print the markdown table

Output (mirrors the dataset layout, so tools/eval.py runs it with UNIAGENT_DATASETS):
    experiments/layouts/<set>/{inputs/<base>-L<k>/*.pdf, ground-truth.jsonl}

Six transformations (k), each applied to the 21 practice cases where it is meaningful:
    L1 file names          rename the files (dokument-N / scan_00NN / English / vendor names, always
                           ".pdf" in lower case) and change which file comes first alphabetically
    L2 checkboxes          "[X] ja [ ] nein" -> "☒ ja ☐ nein" | "■ ja □ nein" | "ja ☒ nein ☐" | "ja"
    L3 labels              German form labels -> synonyms or English (values untouched)
    L4 number formats      "1.234,56 €" -> "EUR 1.234,56" | "1.234,56 EUR"; dates "09.03.2026" ->
                           "9. März 2026" | "2026-03-09", one format per document
    L5 document structure  split a multi-page PDF, merge related PDFs, or move a totals block above
                           the positions
    L6 additions           a cover e-mail that only lists the attachments, or a marked copy of an
                           invoice that already carries the same "sachlich richtig" stamp

Needs only python3 (standard library) and pdftotext/pdfinfo (poppler). Reuses the text reader, the
PDF page-size reader, `_realign` and `norm` of experiments/variants/tools/make_variants.py; the PDF
writer is that script's pure-Python Courier writer, extended by a second code range for the glyphs
☒ ☐ ■ □ → ✓ (drawn as vector shapes, text layer via ToUnicode). Unchanged PDFs are byte-copied
from $UNIAGENT_DATASETS (default ~/dev/uniagent-code/cikm26/datasets, read only); changed PDFs are
rebuilt from their `pdftotext -layout` text and verified to round-trip.

--check verifies per case: the label equals the source label and the reason carries the prefix;
every rewritten PDF round-trips through pdftotext -layout; the multiset of all numbers (with dates
and months normalised) equals the source's (L6: the set equals, the multiset is a superset); the
words that disappeared or appeared are only label words of the transformation; L1 keeps the bytes
and moves the alphabetically first file; L2 keeps the ticked answer; L5 keeps every line.
"""
import collections
import hashlib
import json
import pathlib
import re
import shutil
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent                                  # experiments/layouts
sys.path.insert(0, str(HERE.parents[1] / "variants" / "tools"))
import make_variants as mv  # noqa: E402

DATASETS = mv.DATASETS
TRIP, PROC, EXP = mv.TRIP, mv.PROC, mv.EXP
SETS = [TRIP, PROC, EXP]
SHORT = {TRIP: "trip", PROC: "proc", EXP: "exp"}
A4 = (595.276, 841.89)
LAYER_NAME = {1: "file names", 2: "checkboxes", 3: "labels", 4: "number formats",
              5: "document structure", 6: "additions"}


class Skip(Exception):
    pass


# --------------------------------------------------------------------------- #
# PDF writer: the make_variants Courier writer plus a code range for a few glyphs
# --------------------------------------------------------------------------- #
EXTRA = ["☒", "☐", "■", "□", "→", "✓"]
GLYPH_NAME = {"☒": "uni2612", "☐": "uni2610", "■": "uni25A0", "□": "uni25A1", "→": "arrowright", "✓": "uni2713"}


def _pdf_bytes(s):
    out = bytearray()
    for ch in s:
        if ch in EXTRA:
            byte = 1 + EXTRA.index(ch)
        else:
            byte = ch.encode("cp1252")[0]  # raises if a character is not in WinAnsi
        c = chr(byte)
        if c in "\\()":
            out += b"\\" + c.encode()
        elif 32 <= byte < 127:
            out.append(byte)
        else:
            out += b"\\%03o" % byte
    return bytes(out)


def _tounicode():
    pairs = [(1 + i, ch) for i, ch in enumerate(EXTRA)]
    for b in range(32, 256):
        try:
            pairs.append((b, bytes([b]).decode("cp1252")))
        except UnicodeDecodeError:
            pass
    body = ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<00> <FF>\nendcodespacerange\n")
    for k in range(0, len(pairs), 100):
        part = pairs[k:k + 100]
        body += f"{len(part)} beginbfchar\n" + "".join(f"<{c:02X}> <{ord(u):04X}>\n" for c, u in part) + "endbfchar\n"
    body += "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    return body.encode("ascii")


def _shape(ch, x, y, fs):
    """Vector drawing for one special glyph in a monospaced cell at baseline y."""
    cw = 0.6 * fs
    s = 0.58 * fs
    x0 = x + (cw - s) / 2
    lw = max(0.4, fs * 0.07)
    if ch in "☐□":
        return f"q {lw:.2f} w {x0:.2f} {y:.2f} {s:.2f} {s:.2f} re S Q\n"
    if ch == "■":
        return f"q {x0:.2f} {y:.2f} {s:.2f} {s:.2f} re f Q\n"
    if ch == "☒":
        return (f"q {lw:.2f} w {x0:.2f} {y:.2f} {s:.2f} {s:.2f} re S "
                f"{x0:.2f} {y:.2f} m {x0 + s:.2f} {y + s:.2f} l S {x0:.2f} {y + s:.2f} m {x0 + s:.2f} {y:.2f} l S Q\n")
    if ch == "✓":
        return (f"q {lw * 1.4:.2f} w {x0:.2f} {y + s * 0.5:.2f} m {x0 + s * 0.35:.2f} {y:.2f} l "
                f"{x0 + s:.2f} {y + s:.2f} l S Q\n")
    if ch == "→":
        ym = y + s * 0.45
        return (f"q {lw:.2f} w {x0:.2f} {ym:.2f} m {x0 + s:.2f} {ym:.2f} l S "
                f"{x0 + s * 0.65:.2f} {ym + s * 0.28:.2f} m {x0 + s:.2f} {ym:.2f} l {x0 + s * 0.65:.2f} {ym - s * 0.28:.2f} l S Q\n")
    return ""


def write_pdf(path, text, size, title):
    w, h = size
    margin = 28.0
    pages = [p.rstrip("\n").split("\n") for p in text.split("\f") if p.strip()]
    longest = max(len(l.rstrip()) for p in pages for l in p)
    fs = min(9.0, (w - 2 * margin) / (0.6 * max(longest, 1)))
    lead = fs * 1.25
    cap = int((h - 2 * margin) / lead)
    chunks = []
    for p in pages:
        for k in range(0, len(p), cap):
            chunks.append(p[k:k + cap])
    objs = []
    n_pages = len(chunks)
    # ids: 1 catalog, 2 pages, 3 font, 4 info, 5 ToUnicode, then (page, content) pairs
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{6 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>".encode())
    diffs = " ".join(f"/{GLYPH_NAME[c]}" for c in EXTRA)
    objs.append(("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding << /Type /Encoding /BaseEncoding "
                 f"/WinAnsiEncoding /Differences [1 {diffs}] >> /FirstChar 1 /LastChar 255 "
                 f"/Widths [{' '.join(['600'] * 255)}] /ToUnicode 5 0 R >>").encode())
    objs.append(b"<< /Title (" + _pdf_bytes(title) + b") /Author () /Creator () /Producer () /Subject () >>")
    tu = zlib.compress(_tounicode())
    objs.append(f"<< /Filter /FlateDecode /Length {len(tu)} >>\nstream\n".encode() + tu + b"\nendstream")
    for i, lines in enumerate(chunks):
        content = bytearray()
        for j, line in enumerate(lines):
            line = line.rstrip()
            if not line:
                continue
            y = h - margin - fs - j * lead
            # runs of ordinary characters, and each special glyph, are placed at absolute columns
            # (the viewer's advance width of a special glyph is unknown)
            for m in re.finditer(r"[☒☐■□→✓]|[^☒☐■□→✓]+", line):
                x = margin + m.start() * 0.6 * fs
                content += f"BT /F1 {fs:.3f} Tf {x:.2f} {y:.2f} Td (".encode() + _pdf_bytes(m.group(0)) + b") Tj ET\n"
                if m.group(0) in EXTRA:
                    content += _shape(m.group(0), x, y, fs).encode()
        comp = zlib.compress(bytes(content))
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.4f} {h:.4f}] /Contents {7 + 2 * i} 0 R "
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


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def replace_span(line, a, b, new):
    """Replace line[a:b] by `new` and keep the layout: a column that follows stays where it was
    (at least two spaces apart), a right-aligned field keeps its right edge."""
    d = len(new) - (b - a)
    before, after = line[:a], line[b:]
    if d == 0:
        return before + new + after
    if after.strip() == "":  # the field ends the line: keep its right edge
        if d < 0:
            before += " " * (-d)
        else:
            trail = len(before) - len(before.rstrip(" "))
            if trail >= d + 1:
                before = before[:-d]
        return before + new + after
    m = re.match(r"(:?)( *)", after)
    colon, gap = m.group(1), len(m.group(2))
    rest = after[m.end():]
    if gap >= 2:  # a gap follows: keep the next column where it was
        gap = (gap + (-d)) if d < 0 else max(3 if gap >= 3 else 2, gap - d)
        return before + new + colon + " " * gap + rest
    pre = len(before) - len(before.rstrip(" "))  # value hugs the label: keep the right edge of the block
    if d > 0 and pre >= d + 1:
        before = before[:-d]
    elif d < 0 and pre >= 1:
        before += " " * (-d)
    return before + new + after


def apply_spans(line, spans):
    """spans = [(a, b, new)], non-overlapping; applied right to left."""
    for a, b, new in sorted(spans, key=lambda s: -s[0]):
        line = replace_span(line, a, b, new)
    return line


def lines_of(text):
    return text.split("\n")


MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
             "November", "Dezember"]
MONTHS_EN = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def canon_numbers(text):
    """Multiset of every integer in the text, dates and month names normalised so that
    09.03.2026, 9. März 2026 and 2026-03-09 all give {9, 3, 2026}."""
    t = text
    t = re.sub(r"\b(" + "|".join(MONTHS_DE) + r")\b", lambda m: f" {MONTHS_DE.index(m.group(1)) + 1} ", t)
    t = re.sub(r"(?<=\d)-(" + "|".join(MONTHS_EN) + r")-(?=\d)", lambda m: f"-{MONTHS_EN.index(m.group(1)) + 1}-", t)
    return collections.Counter(int(x) for x in re.findall(r"\d+", t))


def words(text):
    return collections.Counter(re.findall(r"[A-Za-zÄÖÜäöüß]+", text))


# --------------------------------------------------------------------------- #
# Documents and cases
# --------------------------------------------------------------------------- #
class Doc:
    def __init__(self, name, orig=None, src=None, size=None, text=None):
        self.name, self.orig, self.src, self.size = name, orig, src, size
        self.text = orig if text is None else text

    @property
    def stem(self):
        return self.name[:-4]

    @property
    def rewritten(self):
        return self.src is None or self.text != self.orig

    def clone(self, name=None, text=None):
        return Doc(name or self.name, self.orig, self.src, self.size, self.text if text is None else text)


class Case:
    def __init__(self, idx, set_, base):
        self.idx, self.set, self.base = idx, set_, base
        d = DATASETS / set_ / "inputs" / base
        self.docs = []
        for p in sorted(d.glob("*.pdf")):
            self.docs.append(Doc(p.name, orig=mv.pdftotext(p), src=p, size=mv.page_size(p)))
        gt = {}
        for line in open(DATASETS / set_ / "ground-truth.jsonl", encoding="utf-8"):
            row = json.loads(line)
            gt[row["antrag"]] = row
        self.result, self.reason = gt[base]["result"], gt[base]["begruendung"]

    def doc(self, stem):
        for d in self.docs:
            if d.stem == stem:
                return d
        raise Skip(f"no document {stem}")

    def fresh(self):
        return [d.clone() for d in self.docs]


class Result:
    def __init__(self, docs, what, risk=""):
        self.docs, self.what, self.risk, self.meta = docs, what, risk, {}


# --------------------------------------------------------------------------- #
# L1 file names
# --------------------------------------------------------------------------- #
EN_NAMES = [
    (r"^antrag-dienstreise", "travel-request"),
    (r"^bahn-rechnung", "train-invoice"), (r"^bahn-ticket", "train-ticket"), (r"^bahn-buchung", "train-booking"),
    (r"^hotelrechnung", "hotel-invoice"), (r"^hotel-buchung", "hotel-booking"),
    (r"^kontoauszug", "bank-statement"),
    (r"^email-annahme", "email-paper-acceptance"), (r"^email-einladung", "email-invitation"),
    (r"^email-stipendium|^email-stipendienzusage", "email-scholarship"),
    (r"^email-korrespondenz", "email-thread"), (r"^email-beschaffungsantrag", "purchase-request-email"),
    (r"^konferenz-registrierungsbest|^konferenz-anmeldebest", "registration-confirmation"),
    (r"^konferenz-registrierung$", "registration-invoice"),
    (r"^flug-preisvergleich", "flight-price-comparison"), (r"^flug-angebot", "flight-quote"),
    (r"^angebot-(\d)", r"quote-\1"),
    (r"^beschaffungsantrag$", "purchase-request"), (r"^vergabevermerk", "award-note"), (r"^wps-warenkorb", "wps-cart"),
    (r"^rechnung-adapter-(\d)", r"invoice-\1"), (r"^rechnung-leuchten", "invoice-lights"),
    (r"^rechnung-stative", "invoice-stands"), (r"^rechnung-druckerei", "invoice-print-shop"),
    (r"^rechnung-fachbuch", "invoice-book"), (r"^rechnung-kopfhoerer", "invoice-headphones"),
    (r"^rechnung-laborbedarf", "invoice-lab-supplies"), (r"^rechnung-teekueche", "invoice-tea-kitchen"),
    (r"^rechnung-konferenzgebuehr", "invoice-conference-fee"),
    (r"^gutschrift", "credit-note"), (r"^beleg-1", "receipt"),
]

VENDOR = {  # file stem -> name built from the issuer named inside the document
    "dienstreiseantrag-01": {"antrag-dienstreisegenehmigung": "universitaet-kassel-antrag-3381029441",
                             "bahn-rechnung-kassel-leipzig": "nordbahn-fernverkehr-1792-0318824411",
                             "hotelrechnung-leipzig": "hotel-alte-messe-leipzig",
                             "kontoauszug-zahlungsnachweis": "bank-kontoauszug"},
    "dienstreiseantrag-02": {"antrag-dienstreisegenehmigung": "universitaet-kassel-antrag-3381029442",
                             "bahn-buchungsbestaetigung": "nordbahn-fernverkehr-buchung",
                             "email-annahmebestaetigung-konferenz": "nordsys-program-chairs",
                             "konferenz-registrierungsbestaetigung": "symposia-events-ns26-inv-0417"},
    "dienstreiseantrag-03": {"antrag-dienstreisegenehmigung": "universitaet-kassel-antrag-3381029443",
                             "bahn-ticket-hinfahrt": "nordbahn-fernverkehr-1792-0311447725",
                             "konferenz-anmeldebestaetigung": "envirotech-summit-ets26-0912"},
    "dienstreiseantrag-04": {"antrag-dienstreisegenehmigung": "universitaet-kassel-antrag-3381029444",
                             "email-einladung-vortrag": "photonicsconnect-steering-committee",
                             "flug-preisvergleich": "reisebuero-campus-kassel-rck-2026-1188",
                             "hotel-buchungsbestaetigung": "hotel-diagonal-congress-hdc-2026-77140"},
    "dienstreiseantrag-05": {"antrag-dienstreisegenehmigung": "universitaet-kassel-antrag-3381029445",
                             "email-stipendienzusage": "dgmk-nachwuchsreisestipendium",
                             "flug-angebot": "reisebuero-campus-kassel-rck-2026-1402",
                             "konferenz-registrierung": "mrs-fall-meeting-fm26-i-20884"},
    "beschaffungsantrag-01": {"angebot-1": "oszillo-kontor-vehrs-an-27-0311", "angebot-2": "abendroth-pilz-2027-0457",
                              "angebot-3": "quistorp-q-104882", "beschaffungsantrag": "universitaet-wernstadt-zb-2027-0147",
                              "vergabevermerk": "zentrale-beschaffung-v-27-0088"},
    "beschaffungsantrag-02": {"angebot-1": "loethaus-dannwolf-dw-a-5518",
                              "email-beschaffungsantrag": "treppner-direktauftrag"},
    "beschaffungsantrag-03": {"email-beschaffungsantrag": "vosskuhl-sammelbestellung"},
    "beschaffungsantrag-04": {"angebot-1": "hollerbach-hb-270512", "angebot-2": "sturmfels-els-a-2027-219",
                              "angebot-3": "rautenberg-r-27-0633", "beschaffungsantrag": "universitaet-wernstadt-zb-2027-0312",
                              "vergabevermerk": "zentrale-beschaffung-v-27-0203"},
    "beschaffungsantrag-05": {"beschaffungsantrag": "universitaet-wernstadt-zb-2027-0388",
                              "wps-warenkorb": "wps-wk-0027-18834"},
    "beschaffungsantrag-06": {"angebot-1": "waagenbau-ifflaender-iw-6620", "angebot-2": "sendelbach-s-27-1187",
                              "beschaffungsantrag": "universitaet-wernstadt-zb-2027-0421",
                              "vergabevermerk": "zentrale-beschaffung-v-27-0249"},
    "beschaffungsantrag-07": {"angebot-1": "thermoskop-ruhland-tr-a-27-0902", "angebot-2": "mergenthal-m-5531",
                              "angebot-3": "zwiebler-kz-27-1044", "beschaffungsantrag": "universitaet-wernstadt-zb-2027-0536",
                              "vergabevermerk": "zentrale-beschaffung-v-27-0318"},
    "beschaffungsantrag-08": {"angebot-1": "hovestadt-hl-27-2209", "angebot-2": "kalinowski-rehm-kr-a-8817",
                              "angebot-3": "wendelstein-w-2027-341", "email-korrespondenz": "th-sallstedt-einkauf-mail",
                              "rechnung-leuchten": "hovestadt-re-27-10418", "rechnung-stative": "hovestadt-re-27-10877"},
    "auslagenerstattung-01": {"rechnung-fachbuch": "folioport-fpm-nl-27-004471908"},
    "auslagenerstattung-02": {"beleg-1": "baufachmarkt-ottensmeier-bon-4471"},
    "auslagenerstattung-03": {"kontoauszug": "ringwall-direktbank-kontoauszug", "rechnung-kopfhoerer": "klangraum-kv-2027-118406"},
    "auslagenerstattung-04": {"rechnung-laborbedarf": "laborhandel-quendt-pf-27-0934"},
    "auslagenerstattung-05": {"gutschrift-druckerei": "pannewitz-gs-27-0031", "rechnung-druckerei": "pannewitz-re-27-0612-0618"},
    "auslagenerstattung-06": {"rechnung-adapter-1": "brackwater-inv-ie-27-0048812", "rechnung-adapter-2": "brackwater-inv-ie-27-0051377"},
    "auslagenerstattung-07": {"rechnung-teekueche": "warenhafen-wh-de-27-7730165"},
    "auslagenerstattung-08": {"kontoauszug": "hainbuchen-bank-kreditkartenabrechnung", "rechnung-konferenzgebuehr": "iwssa-27-r-00318"},
}
L1_STYLES = ["generic", "scan", "english", "vendor"]


def _en_name(stem):
    for rx, name in EN_NAMES:
        if re.search(rx, stem):
            return re.sub(rx, name, stem) if "\\" in name else name
    raise Skip(f"no English name for {stem}")


def _l1_names(c, style):
    n = len(c.docs)
    if style == "generic":
        return [f"dokument-{n - i}.pdf" for i in range(n)]                       # reversed
    if style == "scan":
        return [f"scan_{42 + (i + 1) % n:04d}.pdf" for i in range(n)]              # rotated by one
    if style == "english":
        return [_en_name(d.stem) + ".pdf" for d in c.docs]
    return [VENDOR[c.base][d.stem] + ".pdf" for d in c.docs]


def L1(c):
    n = len(c.docs)
    tried = []
    for k in range(4):
        style = L1_STYLES[(c.idx + k) % 4]
        names = _l1_names(c, style)
        if len(set(names)) != n:
            continue
        order = sorted(range(n), key=lambda i: names[i])
        if n == 1 or order[0] != 0:
            tried.append(style)
            break
    else:
        raise Skip("no naming style moves the first file")
    docs = [d.clone(name=nm) for d, nm in zip(c.docs, names)]
    first = docs[order[0]]
    what = (f"files renamed ({style}): " + ", ".join(f"{d.name}→{x.name}" for d, x in zip(c.docs, docs)) +
            (f"; alphabetically first file is now {first.name} (was {c.docs[0].name})" if n > 1 else "; single file, name only"))
    return Result(docs, what, "Low: PDFs are byte copies; only the names and the alphabetical order differ")


# --------------------------------------------------------------------------- #
# L2 checkboxes
# --------------------------------------------------------------------------- #
BOX = re.compile(r"\[([ X])\]")
L2_STYLES = ["sym1", "sym2", "after", "plain"]
GLYPHS = {"sym1": ("☒", "☐"), "sym2": ("■", "□"), "after": ("☒", "☐")}


def parse_boxes(line):
    """-> prefix, [(ticked, label, tail)], seps ; label = first run of text after a box, tail = text after 2+ spaces."""
    ms = list(BOX.finditer(line))
    if not ms:
        return None
    opts = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(line)
        seg = line[m.end():end].strip()
        label, tail = (re.split(r"\s{2,}", seg, maxsplit=1) + [""])[:2]
        opts.append((m.group(1) == "X", label, tail))
    return line[:ms[0].start()], opts


def convert_box_line(line, style):
    prefix, opts = parse_boxes(line)
    if style == "plain":
        ticked = [lab for t, lab, _ in opts if t]
        if len(ticked) != 1:
            return None
        tail = [tl for t, _, tl in opts if t and tl]
        return prefix + ticked[0] + ("   " + tail[0] if tail else "")
    on, off = GLYPHS[style]
    parts = []
    for t, lab, tail in opts:
        g = on if t else off
        item = f"{g} {lab}" if style != "after" else f"{lab} {g}"
        if tail:
            item += "   " + tail
        parts.append(item)
    sep = "   " if "   " in line[len(prefix):] else " "
    return prefix + sep.join(parts)


def expected_box_regex(style, ticked, label):
    on, off = GLYPHS.get(style, ("", ""))
    g = on if ticked else off
    if style == "after":
        return re.escape(label) + r"\s*" + re.escape(g)
    return re.escape(g) + r"\s*" + re.escape(label)


def L2(c):
    style = L2_STYLES[c.idx % 4]
    docs, n_lines, sources = c.fresh(), 0, []
    ticks = {}
    for d in docs:
        ls = lines_of(d.text)
        for i, l in enumerate(ls):
            if BOX.search(l):
                parsed = parse_boxes(l)
                st = style
                if style == "plain" and sum(t for t, _, _ in parsed[1]) != 1:
                    st = "after"  # nothing ticked (field left empty): keep the empty boxes
                new = convert_box_line(l, st)
                ticks.setdefault(d.name, []).append((i, st, parsed[1]))
                ls[i] = new
                n_lines += 1
        d.text = "\n".join(ls)
    if not n_lines:
        raise Skip("no checkboxes in this case")
    res = Result(docs, f"{n_lines} checkbox line(s) rewritten in style '{style}' "
                       f"({'plain answer' if style == 'plain' else ' / '.join(GLYPHS[style])}); ticked answer unchanged",
                 "Low; plain style drops the unticked options, a field left empty keeps its empty boxes")
    res.meta["ticks"] = ticks
    return res


# --------------------------------------------------------------------------- #
# L3 labels
# --------------------------------------------------------------------------- #
ANY = r"(?=\s)"
# (label, same-language synonym A, other-language B, lookahead override)
LABELS = [
    # business trip request
    ("Zuletzt geändert am", "Letzte Änderung am", "Last changed on"),
    ("Genehmigt von", "Genehmigung durch", "Approved by"),
    ("ANTRAG AUF DIENSTREISEGENEHMIGUNG", "DIENSTREISEANTRAG", "TRAVEL REQUEST"),
    ("Reisenummer", "Reise-Nr.", "Trip number", ANY),
    ("Allgemeine Daten", "Grunddaten", "General data"),
    ("Reiseziel", "Zielort", "Destination"),
    ("Anlass", "Veranstaltung", "Occasion"),
    ("Grund der Reise", "Reisezweck", "Purpose of trip"),
    ("Reise ins Ausland", "Auslandsreise", "Trip abroad"),
    ("Verkehrsmittel", "Transportmittel", "Means of transport"),
    ("Datum der Antragstellung", "Antragsdatum", "Date of application"),
    ("Reiseverlauf", "Reiseablauf", "Itinerary"),
    ("Start", "Reisebeginn", "Start of trip"),
    ("Ende", "Reiseende", "End of trip"),
    ("Beginn Dienstgeschäft", "Dienstgeschäft von", "Business start"),
    ("Ende Dienstgeschäft", "Dienstgeschäft bis", "Business end"),
    ("Hinreise", "Anreise", "Outbound journey"),
    ("Rückreise", "Heimreise", "Return journey"),
    ("priv. Aufenthalt", "Privater Aufenthalt", "Private stay"),
    ("Arbeitstage", "Anzahl Arbeitstage", "Working days"),
    ("A1-Bescheinigung", "A1-Nachweis", "A1 certificate"),
    ("Voraussichtliche Kosten (Schätzung)", "Geschätzte Kosten", "Estimated costs"),
    ("Summe (Schätzung)", "Gesamtsumme (Schätzung)", "Total (estimate)"),
    ("Finanzierung", "Finanzierungsquelle", "Funding"),
    ("Kurzbegründung", "Begründung (kurz)", "Short justification"),
    ("Hinweis der/des Antragsteller:in", "Anmerkung der/des Antragsteller:in", "Note from applicant"),
    ("Unterschrift Antragsteller:in", "Unterschrift der antragstellenden Person", "Applicant signature"),
    ("Personalnummer", "Personal-Nr.", "Staff number"),
    ("Erstellt durch", "Erzeugt durch", "Created by", ANY),
    # e-mail
    ("An", "Empfänger", "To"), ("Cc", "Kopie an", "CC"), ("Von", "Absender", "From"),
    ("Gesendet", "Versendet am", "Sent"), ("Betreff", "Thema", "Subject"),
    # invoices, offers, confirmations
    ("Datum", "Datum", "Date"),
    ("Auftragsnummer", "Auftrags-Nr.", "Order number"), ("Rechnungsnummer", "Rechnungs-Nr.", "Invoice number"),
    ("Rechnungsdatum", "Datum der Rechnung", "Invoice date"), ("Buchungsdatum", "Datum der Buchung", "Booking date"),
    ("Registrierungsnummer", "Registrierungs-Nr.", "Registration number"),
    ("Reservierungsnummer", "Reservierungs-Nr.", "Reservation number"),
    ("Buchungsnummer", "Buchungs-Nr.", "Booking number"), ("Anmeldenummer", "Anmelde-Nr.", "Registration no."),
    ("Bestätigt am", "Bestätigung vom", "Confirmed on"),
    ("Angebotsnummer", "Angebots-Nr.", "Quote number"), ("Angebotsdatum", "Datum des Angebots", "Quote date"),
    ("Gültig bis", "Gültigkeit bis", "Valid until"), ("Bindefrist", "Angebotsbindung bis", "Offer valid until"),
    ("Angebot Nr.", "Angebotsnummer", "Quotation no.", ANY), ("Kundennummer", "Kunden-Nr.", "Customer number"),
    ("Bestellung vom", "Bestelldatum", "Order date"), ("Rechnung Nr.", "Rechnungsnummer", "Invoice no.", ANY),
    ("Gutschrift Nr.", "Gutschriftsnummer", "Credit note no.", ANY),
    ("Rechnungsnr.", "Rechnungsnummer", "Invoice no."), ("Bestellnr.", "Bestellnummer", "Order no."),
    ("Zahlungsinformationen", "Zahlungsdetails", "Payment information"),
    ("Art der Transaktion", "Transaktionsart", "Transaction type"), ("Zahlungsmittel", "Zahlungsart", "Payment method"),
    ("Zahlungsart", "Zahlweise", "Payment type"), ("Zahlungsziel", "Zahlbar bis", "Payment due"),
    ("Betrag", "Zahlbetrag", "Amount"),
    ("Summe (netto)", "Nettosumme", "Net total"), ("Summe netto", "Nettosumme", "Net total"),
    ("Summe (brutto)", "Bruttosumme", "Gross total"), ("Angebotssumme brutto", "Gesamtangebot brutto", "Offer total gross"),
    ("Gesamtbetrag brutto", "Endbetrag brutto", "Total amount gross"), ("Rechnungsbetrag", "Gesamtbetrag", "Invoice total"),
    ("Gutschriftsbetrag", "Gutschriftssumme", "Credit total"), ("Gesamtsumme", "Endsumme", "Grand total"),
    ("Gesamt", "Summe", "Total"), ("Summe", "Gesamt", "Total"),
    ("zzgl.", "zuzüglich", "plus", ANY), ("Lieferzeit", "Lieferfrist", "Delivery time"),
    ("Bankverbindung", "Bank", "Bank details"), ("Anfrage", "Suchanfrage", "Request"),
    ("Rechnung", "Rechnungsbeleg", "Invoice"), ("Angebot", "Preisangebot", "Quotation"), ("Ihr Angebot", "Unser Angebot", "Your quotation"),
    ("Mit freundlichen Grüßen", "Freundliche Grüße", "Kind regards"),
    # bank statement
    ("Zahlungsbeteiligter", "Zahlungspartner", "Counterparty"), ("Buchungstag", "Buchungsdatum", "Booking date"),
    ("Vorgang", "Buchungsart", "Transaction"), ("Verwendungszweck", "Zahlungszweck", "Reference"),
    ("Kontoinhaber", "Inhaber des Kontos", "Account holder"), ("Uhrzeit", "Zeit", "Time"),
    ("Abgefragt von", "Abgerufen von", "Queried by"),
    # procurement request, award note
    ("Antrag Nr.", "Antragsnummer", "Request no.", ANY),
    ("Beschaffungsantrag / Bestellanforderung", "Bestellanforderung / Beschaffungsantrag", "Procurement request / purchase requisition"),
    ("1. Bedarfsstelle", "1. Anforderer", "1. Requesting unit"), ("Organisationseinheit", "Einheit", "Organisational unit"),
    ("Antragsteller:in", "Antragstellende Person", "Applicant"), ("Telefon", "Tel.", "Phone"),
    ("Kostenstelle / Auftrag", "Kostenstelle und Auftrag", "Cost centre / order"),
    ("Kostenstellenbevollmächtigte:r", "Kostenstellen-Bevollmächtigte:r", "Cost centre authorised person"),
    ("2. Einordnung", "2. Klassifizierung", "2. Classification"), ("Kategorie", "Art", "Category"),
    ("Rahmenvertragsprodukt", "Rahmenvertragsartikel", "Framework contract product"),
    ("Vergabeart", "Vergabeverfahren", "Award procedure"), ("Eingeholte Angebote", "Anzahl eingeholter Angebote", "Offers obtained"),
    ("Vorgesehener Lieferant", "Geplanter Lieferant", "Intended supplier"),
    ("3. Positionen", "3. Bestellpositionen", "3. Items"),
    ("4. Begründung des Bedarfs und der Lieferantenauswahl", "4. Begründung von Bedarf und Lieferantenwahl",
     "4. Justification of need and supplier selection"),
    ("Beauftragt", "Beauftragung durch", "Commissioned by"),
    ("Vergabevermerk", "Vergabedokumentation", "Award record"), ("Gegenstand", "Betreff der Beschaffung", "Subject"),
    ("Verfahren", "Vergabeverfahren", "Procedure"), ("Wertung", "Bewertungskriterium", "Evaluation"),
    ("Eingegangene Angebote", "Erhaltene Angebote", "Offers received"), ("Zuschlag an", "Zuschlagserteilung an", "Award to"),
    ("Begründung der Vergabeentscheidung", "Begründung der Zuschlagsentscheidung", "Reasons for the award decision"),
    ("Kostenstelle", "Kostenst.", "Cost centre", r"(?=\s\d)"), ("Auftrag", "Auftragsnr.", "Order", r"(?=\s\d)"),
    ("Warenkorb", "Bestellkorb", "Shopping cart", r"(?=\s)"), ("Lieferant (Rahmenvertragspartner)", "Anbieter (Rahmenvertragspartner)",
                                                              "Supplier (framework partner)"),
    ("Warenwert netto", "Nettowarenwert", "Goods value net"), ("Gesamt brutto", "Bruttogesamtsumme", "Total gross"),
    ("Katalog", "Sortiment", "Catalogue"), ("Besteller:in", "Bestellende Person", "Orderer"),
    ("Kontierung", "Kontenzuordnung", "Account assignment"),
    # receipt
    ("SUMME EUR", "GESAMT EUR", "TOTAL EUR"), ("BAR", "BAR GEGEBEN", "CASH"), ("RÜCKGELD", "ZURÜCK", "CHANGE"),
    ("ART", "ARTIKEL", "ITEM"),
    # English invoices
    ("Bill to", "Invoice to", "Rechnung an"), ("Deliver to", "Ship to", "Lieferung an"),
    ("Invoice no.", "Invoice number", "Rechnungsnr.", ANY), ("Invoice date", "Date of invoice", "Rechnungsdatum"),
    ("Order no.", "Order number", "Bestellnr.", ANY), ("Order date", "Date of order", "Bestelldatum"),
    ("Invoice number", "Invoice no.", "Rechnungsnummer"), ("Order number", "Order no.", "Bestellnummer"),
    ("Sold by", "Seller", "Verkauft von"), ("Subtotal (net)", "Net subtotal", "Zwischensumme (netto)"),
    ("VAT", "Tax", "USt", r"(?=\s\d)"), ("Invoice total", "Total amount", "Rechnungsbetrag"),
    ("Invoice", "Invoice document", "Rechnung"), ("Billing and delivery address", "Billing and shipping address",
                                                  "Rechnungs- und Lieferadresse"),
    ("Receipt no.", "Receipt number", "Beleg-Nr.", ANY), ("Date", "Date of issue", "Datum", r"(?=\s\d)"),
    ("Registration ID", "Registration number", "Registrierungs-ID", ANY), ("Total paid (USD)", "Amount paid (USD)", "Gesamt gezahlt (USD)"),
    ("Total due", "Amount due", "Zu zahlen"),
    ("Gutschrift", "Gutschriftsbeleg", "Credit note"),
]
DEFAULT_LOOK = r"(?=:|,|\s{2,}|\s*$|\s(?=\d))"
HEADER_TOKENS = [
    ("Position", "Posten", "Item"), ("Menge", "Anzahl", "Qty"), ("Betrag", "Preis", "Amount"),
    ("Beschreibung", "Bezeichnung", "Description"), ("Bezeichnung", "Beschreibung", "Description"),
    ("MwSt", "USt", "VAT"), ("netto", "Netto", "net"), ("brutto", "Brutto", "gross"),
    ("Einzelpreis", "Stückpreis", "Unit price"), ("Gesamt netto", "Gesamtpreis netto", "Total net"),
    ("Pos", "Nr.", "No."), ("Pos.", "Nr.", "No."), ("Artikel / Leistung", "Artikel / Dienstleistung", "Item / service"),
    ("EP netto", "Einzelpreis netto", "Unit net"), ("GP netto", "Gesamtpreis netto", "Line net"),
    ("Bieter", "Anbieter", "Bidder"), ("Angebot", "Angebotsnr.", "Quote"), ("vom", "Datum", "Date"),
    ("Rang", "Platz", "Rank"), ("Buchungstag", "Buchungsdatum", "Booking date"),
    ("Vorgang / Verwendungszweck", "Buchung / Verwendungszweck", "Transaction / Reference"),
    ("Description", "Details", "Beschreibung"), ("Qty", "Quantity", "Menge"), ("VAT", "Tax", "MwSt"),
    ("Net", "Net amount", "Netto"), ("Gross", "Gross amount", "Brutto"), ("Item", "Article", "Posten"),
    ("Tax", "VAT rate", "Steuer"), ("Price", "Unit price", "Preis"), ("Amount", "Total", "Betrag"),
]
_LABEL_RX = {}


def _label_rx(entry):
    label, look = entry[0], (entry[3] if len(entry) > 3 else DEFAULT_LOOK)
    key = (label, look)
    if key not in _LABEL_RX:
        _LABEL_RX[key] = re.compile(r"(?:^\s*|(?<=  )|(?<=· ))(?P<x>" + re.escape(label) + r")" + look)
    return _LABEL_RX[key]


def label_words(style):
    src, dst = set(), set()
    for e in LABELS:
        src |= set(words(e[0]))
        dst |= set(words(e[1] if style == "A" else e[2]))
    for t in HEADER_TOKENS:
        src |= set(words(t[0]))
        dst |= set(words(t[1] if style == "A" else t[2]))
    return src, dst


def convert_labels(text, style):
    hdr = {h[0]: h for h in HEADER_TOKENS}
    ls = lines_of(text)
    count = 0
    for i, line in enumerate(ls):
        toks = [m for m in re.finditer(r"\S+(?: \S+)*", line)]
        known = [m for m in toks if m.group(0) in hdr]
        spans = []
        if len(known) >= 3 and len(known) >= 0.6 * len(toks):
            nxt = ls[i + 1].strip() if i + 1 < len(ls) else ""
            for m in known:
                h = hdr[m.group(0)]
                if m.group(0) == "Einzelpreis" and nxt == "netto":
                    continue
                new = h[1] if style == "A" else h[2]
                if new != h[0]:
                    spans.append((m.start(), m.end(), new))
        else:
            cands = []
            for e in LABELS:
                new = e[1] if style == "A" else e[2]
                if new == e[0]:
                    continue
                for m in _label_rx(e).finditer(line):
                    cands.append((m.start("x"), m.end("x"), new))
            cands.sort(key=lambda s: (s[0], -(s[1] - s[0])))
            last = -1
            for a, b, new in cands:
                if a >= last:
                    spans.append((a, b, new))
                    last = b
        if spans:
            ls[i] = apply_spans(line, spans)
            count += len(spans)
    return "\n".join(ls), count


def L3(c):
    style = "A" if c.idx % 2 == 0 else "B"
    docs, total = c.fresh(), 0
    for d in docs:
        d.text, n = convert_labels(d.text, style)
        total += n
    if total < 3:
        raise Skip(f"only {total} label(s) found")
    kind = "German synonyms (or English synonyms in English documents)" if style == "A" else "English (German in English documents)"
    return Result(docs, f"{total} form label(s) replaced by {kind}; values untouched",
                  "Medium: a synonym can be read differently by a rule that keys on the original word; values are identical")


# --------------------------------------------------------------------------- #
# L4 number formats
# --------------------------------------------------------------------------- #
MONEY_DE = re.compile(r"(?<![\d.,])(?P<n>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?) €")
MONEY_EN = re.compile(r"€(?P<n>\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})(?!\d)")
MONEY_SUF = re.compile(r"(?<![\d.,])(?P<neg>-)?(?P<n>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}) EUR\b")
DATE_RX = re.compile(r"""
 (?P<rm>(?<![\d.])(?P<f1>\d{1,2})\.(?P<f2>\d{2})\.\s*(?P<fsep>bis|–|-)\s*(?P<f3>\d{1,2})\.(?P<f4>\d{2})\.(?P<f5>\d{4})(?!\d))
|(?P<rng>(?<![\d.])(?P<d1>\d{1,2})\.\s*(?P<sep>bis|–|-)\s*(?P<d2>\d{1,2})\.(?P<m>\d{2})\.(?P<y>\d{4})(?!\d))
|(?P<rny>(?<![\d.])(?P<e1>\d{1,2})\.–(?P<e2>\d{1,2})\.(?P<em>\d{2})\.(?!\d))
|(?P<num>(?<![\d.])(?P<nd>\d{1,2})\.(?P<nm>\d{2})\.(?P<ny>\d{4})(?!\d))
|(?P<yl>(?<![\d.])(?P<y1>\d{1,2})\.(?P<y2>\d{2})\.(?!\d))
|(?P<abbr>(?<!\d)(?P<ad>\d{2})-(?P<am>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(?P<ay>\d{4})(?!\d))
|(?P<iso>(?<![\d-])(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})(?![\d-]))
|(?P<lrng>(?<![\d.])(?P<l1>\d{1,2})\.\s*(?P<lsep>–|bis|-)\s*(?P<l2>\d{1,2})\.[ ](?P<lm>MONTHS)[ ](?P<lyr>\d{4}))
|(?P<lng>(?<![\d.])(?P<n1>\d{1,2})\.[ ](?P<nmn>MONTHS)[ ](?P<nyy>\d{4}))
|(?P<lry>(?<![\d.])(?P<q1>\d{1,2})\.\s*(?P<qsep>–|bis|-)\s*(?P<q2>\d{1,2})\.[ ](?P<qm>MONTHS)\b(?![ ]\d{4}))
|(?P<lyl>(?<![\d.])(?P<r1>\d{1,2})\.[ ](?P<rmo>MONTHS)\b(?![ ]\d{4}))
""".replace("MONTHS", "|".join(MONTHS_DE)), re.X)
YEARLESS = ("rny", "yl", "lry", "lyl")


def _long(d, m, y):
    return f"{int(d)}. {MONTHS_DE[int(m) - 1]} {y}"


def _iso(d, m, y):
    return f"{y}-{int(m):02d}-{int(d):02d}"


def canon_dates(text):
    """(Counter of canonical dates, Counter of the remaining integers) - independent of the written form."""
    dates = collections.Counter()

    def ymd(y, m, d):
        return f"{y or '-'}-{int(m):02d}-{int(d):02d}"

    def repl(m):
        g = m.groupdict()
        mo = lambda name: MONTHS_DE.index(name) + 1
        if g["rm"]:
            dates.update([ymd(g["f5"], g["f2"], g["f1"]), ymd(g["f5"], g["f4"], g["f3"])])
        elif g["rng"]:
            dates.update([ymd(g["y"], g["m"], g["d1"]), ymd(g["y"], g["m"], g["d2"])])
        elif g["rny"]:
            dates.update([ymd("", g["em"], g["e1"]), ymd("", g["em"], g["e2"])])
        elif g["num"]:
            dates.update([ymd(g["ny"], g["nm"], g["nd"])])
        elif g["yl"]:
            dates.update([ymd("", g["y2"], g["y1"])])
        elif g["abbr"]:
            dates.update([ymd(g["ay"], MONTHS_EN.index(g["am"]) + 1, g["ad"])])
        elif g["iso"]:
            dates.update([ymd(g["iy"], g["im"], g["id"])])
        elif g["lrng"]:
            dates.update([ymd(g["lyr"], mo(g["lm"]), g["l1"]), ymd(g["lyr"], mo(g["lm"]), g["l2"])])
        elif g["lng"]:
            dates.update([ymd(g["nyy"], mo(g["nmn"]), g["n1"])])
        elif g["lry"]:
            dates.update([ymd("", mo(g["qm"]), g["q1"]), ymd("", mo(g["qm"]), g["q2"])])
        else:
            dates.update([ymd("", mo(g["rmo"]), g["r1"])])
        return " "

    rest = DATE_RX.sub(repl, text)
    return dates, collections.Counter(int(x) for x in re.findall(r"\d+", rest))


def date_spans(line, mode):
    spans = []
    for m in DATE_RX.finditer(line):
        g = m.groupdict()
        fmt = _long if mode == "long" else _iso
        if g["rm"]:
            sep = g["fsep"]
            if mode == "long":
                new = (f"{int(g['f1'])}. {MONTHS_DE[int(g['f2']) - 1]}{' bis ' if sep == 'bis' else ' – '}"
                       f"{int(g['f3'])}. {MONTHS_DE[int(g['f4']) - 1]} {g['f5']}")
            else:
                new = (f"{_iso(g['f1'], g['f2'], g['f5'])}{' bis ' if sep == 'bis' else ' – '}"
                       f"{_iso(g['f3'], g['f4'], g['f5'])}")
        elif g["rng"]:
            sep = g["sep"]
            if mode == "long":
                new = (f"{int(g['d1'])}. bis " if sep == "bis" else f"{int(g['d1'])}.–") + f"{int(g['d2'])}. {MONTHS_DE[int(g['m']) - 1]} {g['y']}"
            else:
                new = f"{_iso(g['d1'], g['m'], g['y'])}{' bis ' if sep == 'bis' else ' – '}{_iso(g['d2'], g['m'], g['y'])}"
        elif g["rny"]:
            new = f"{int(g['e1'])}.–{int(g['e2'])}. {MONTHS_DE[int(g['em']) - 1]}"
        elif g["yl"]:
            new = f"{int(g['y1'])}. {MONTHS_DE[int(g['y2']) - 1]}"
        elif g["num"]:
            new = fmt(g["nd"], g["nm"], g["ny"])
        elif g["abbr"]:
            new = fmt(g["ad"], MONTHS_EN.index(g["am"]) + 1, g["ay"])
        elif g["iso"]:
            if mode == "iso":
                continue
            new = _long(g["id"], g["im"], g["iy"])
        elif g["lry"] or g["lyl"]:
            continue  # a date in words without a year: left as written (the document then stays in long form)
        elif g["lrng"]:  # a date already written in words: only rewritten when the document goes to ISO
            if mode == "long":
                continue
            m2 = MONTHS_DE.index(g["lm"]) + 1
            new = f"{_iso(g['l1'], m2, g['lyr'])}{' bis ' if g['lsep'] == 'bis' else ' – '}{_iso(g['l2'], m2, g['lyr'])}"
        else:
            if mode == "long":
                continue
            new = _iso(g["n1"], MONTHS_DE.index(g["nmn"]) + 1, g["nyy"])
        spans.append((m.start(), m.end(), new))
    return spans


def convert_formats(text, money, date):
    """money in {'pre', 'suf'}; date in {'long', 'iso'} (iso falls back to long when a date has no year)."""
    if date == "iso" and any(m.group(k) for m in DATE_RX.finditer(text) for k in YEARLESS):
        date = "long"
    ls = lines_of(text)
    n_money = n_date = 0
    for i, line in enumerate(ls):
        spans = []
        for m in MONEY_DE.finditer(line):
            spans.append((m.start(), m.end(), f"EUR {m.group('n')}" if money == "pre" else f"{m.group('n')} EUR"))
            n_money += 1
        for m in MONEY_EN.finditer(line):
            spans.append((m.start(), m.end(), f"EUR {m.group('n')}" if money == "pre" else f"{m.group('n')} EUR"))
            n_money += 1
        if money == "pre":  # amounts already written 'x,xx EUR' follow the document's new form
            for m in MONEY_SUF.finditer(line):
                spans.append((m.start(), m.end(), f"EUR {m.group('neg') or ''}{m.group('n')}"))
                n_money += 1
        ds = date_spans(line, date)
        n_date += len(ds)
        spans += ds
        if spans:
            ls[i] = apply_spans(line, spans)
    return "\n".join(ls), n_money, n_date, date


def L4(c):
    money = "pre" if c.idx % 2 == 0 else "suf"
    date = "long" if (c.idx // 2) % 2 == 0 else "iso"
    docs, tm, td, used, modes = c.fresh(), 0, 0, set(), {}
    for d in docs:
        d.text, nm, nd, dm = convert_formats(d.text, money, date)
        tm, td = tm + nm, td + nd
        if nd:
            used.add(dm)
            modes[d.name] = dm
    if tm + td == 0:
        raise Skip("no amount with € and no dd.mm.yyyy date in this case (e.g. till receipt with 2-digit year)")
    res = Result(docs, f"{tm} amount(s) → '{'EUR 1.234,56' if money == 'pre' else '1.234,56 EUR'}', {td} date(s) → "
                       f"'{'9. März 2026' if date == 'long' else '2026-03-09'}'" +
                 (" (long form where a date has no year)" if used - {date} else ""),
                 "Low; dates with a missing year (07.–10.09.) are written as '7.–10. September' in long form only")
    res.meta["modes"] = modes
    return res


# --------------------------------------------------------------------------- #
# L5 document structure
# --------------------------------------------------------------------------- #
def move_block(text, start_rx, end_rx, before_rx, label):
    ls = lines_of(text)

    def find(rx):
        idx = [i for i, l in enumerate(ls) if re.search(rx, l)]
        if len(idx) < 1:
            raise Skip(f"{label}: pattern {rx!r} not found")
        return idx[0]

    a, b, t = find(start_rx), find(end_rx), find(before_rx)
    if not (t < a <= b):
        raise Skip(f"{label}: block not below the target")
    block = ls[a:b + 1]
    del ls[a:b + 1]
    ls[t:t] = block + [""]
    return "\n".join(ls)


def pages_of(doc):
    return [p for p in doc.text.split("\f") if p.strip()]


def merge_docs(docs, name):
    text = "".join(d.text if d.text.endswith("\f") else d.text.rstrip("\n") + "\n\f" for d in docs)
    return Doc(name, orig=None, src=None, size=docs[0].size, text=text)


L5_PLAN = {  # base -> (kind, argument)
    "dienstreiseantrag-01": ("merge", (["bahn-rechnung-kassel-leipzig", "hotelrechnung-leipzig"], "reisebelege.pdf")),
    "dienstreiseantrag-02": ("merge", (["email-annahmebestaetigung-konferenz", "konferenz-registrierungsbestaetigung"], "konferenzunterlagen.pdf")),
    "dienstreiseantrag-03": ("merge", (["bahn-ticket-hinfahrt", "konferenz-anmeldebestaetigung"], "ticket-und-anmeldung.pdf")),
    "dienstreiseantrag-04": ("split", ("antrag-dienstreisegenehmigung", "antrag-dienstreisegenehmigung-teil-{n}.pdf")),
    "dienstreiseantrag-05": ("merge", (["flug-angebot", "konferenz-registrierung"], "flug-und-registrierung.pdf")),
    "beschaffungsantrag-01": ("merge", (["angebot-1", "angebot-2", "angebot-3"], "angebote.pdf")),
    "beschaffungsantrag-02": ("reorder", ("angebot-1", r"^\s*Summe netto", r"^\s*Angebotssumme brutto", r"^ Bezeichnung\s+Menge")),
    "beschaffungsantrag-03": ("reorder", ("email-beschaffungsantrag", r"^\s*Gesamtsumme:", r"^\s*Gesamtsumme:", r"^\s*1\. 6 ×")),
    "beschaffungsantrag-04": ("merge", (["angebot-1", "angebot-2", "angebot-3"], "angebote.pdf")),
    "beschaffungsantrag-05": ("merge", (["beschaffungsantrag", "wps-warenkorb"], "antrag-mit-warenkorb.pdf")),
    "beschaffungsantrag-06": ("merge", (["angebot-1", "angebot-2"], "angebote.pdf")),
    "beschaffungsantrag-07": ("reorder", ("beschaffungsantrag", r"^ Summe netto", r"^ Gesamtbetrag brutto", r"^\s+Pos\.\s+Bezeichnung")),
    "beschaffungsantrag-08": ("merge", (["angebot-1", "angebot-2", "angebot-3"], "angebote.pdf")),
    "auslagenerstattung-01": ("reorder", ("rechnung-fachbuch", r"Subtotal \(net\)", r"Invoice total", r"^ Description\s+Qty")),
    "auslagenerstattung-02": ("reorder", ("beleg-1", r"^SUMME EUR", r"^SUMME EUR", r"^ART 700184")),
    "auslagenerstattung-03": ("merge", (["rechnung-kopfhoerer", "kontoauszug"], "rechnung-mit-kontoauszug.pdf")),
    "auslagenerstattung-04": ("reorder", ("rechnung-laborbedarf", r"Summe netto", r"Rechnungsbetrag", r"^ Beschreibung\s+Menge")),
    "auslagenerstattung-05": ("split", ("rechnung-druckerei", "rechnung-druckerei-teil-{n}.pdf")),
    "auslagenerstattung-06": ("merge", (["rechnung-adapter-1", "rechnung-adapter-2"], "rechnungen.pdf")),
    "auslagenerstattung-07": ("reorder", ("rechnung-teekueche", r"Summe netto", r"Rechnungsbetrag", r"^ Beschreibung\s+Menge")),
    "auslagenerstattung-08": ("merge", (["rechnung-konferenzgebuehr", "kontoauszug"], "gebuehr-und-kontoauszug.pdf")),
}


def L5(c):
    kind, arg = L5_PLAN[c.base]
    docs = c.fresh()
    if kind == "merge":
        stems, name = arg
        parts = [d for d in docs if d.stem in stems]
        if len(parts) != len(stems):
            raise Skip("documents to merge not found")
        merged = merge_docs(parts, name)
        out = [d for d in docs if d.stem not in stems] + [merged]
        what = f"{' + '.join(p.name for p in parts)} merged into one PDF {name} ({len(parts)} pages, same order)"
        risk = "Low; the merged file is a new PDF, text identical page by page"
    elif kind == "split":
        stem, pattern = arg
        d = c.doc(stem)
        pg = pages_of(d)
        if len(pg) < 2:
            raise Skip("single page")
        out = [x for x in docs if x.stem != stem]
        for n, p in enumerate(pg, 1):
            out.append(Doc(pattern.format(n=n), orig=None, src=None, size=d.size, text=p))
        what = f"{d.name} ({len(pg)} pages) split into {len(pg)} PDFs: " + ", ".join(pattern.format(n=n) for n in range(1, len(pg) + 1))
        last = pg[-1].strip().split("\n")
        risk = ("Medium: the last page holds only the signature block; a solver must read the two files as one request"
                if len(last) < 12 else "Low: each part is a complete page of the original")
    else:
        stem, a, b, before = arg
        out = []
        for d in docs:
            if d.stem == stem:
                d.text = move_block(d.text, a, b, before, f"{c.base}/{d.name}")
            out.append(d)
        what = f"totals block moved above the positions in {stem}.pdf (lines unchanged)"
        risk = "Low: same lines, different order inside one block"
    return Result(out, what, risk)


# --------------------------------------------------------------------------- #
# L6 additions
# --------------------------------------------------------------------------- #
TITLES = {
    "antrag-dienstreisegenehmigung": "Antrag auf Dienstreisegenehmigung", "bahn-rechnung-kassel-leipzig": "Bahnrechnung",
    "bahn-buchungsbestaetigung": "Bahn-Buchungsbestätigung", "bahn-ticket-hinfahrt": "Bahnticket Hinfahrt",
    "hotelrechnung-leipzig": "Hotelrechnung", "hotel-buchungsbestaetigung": "Hotel-Buchungsbestätigung",
    "kontoauszug-zahlungsnachweis": "Kontoauszug", "kontoauszug": "Kontoauszug",
    "email-annahmebestaetigung-konferenz": "E-Mail Annahmebestätigung der Konferenz",
    "konferenz-registrierungsbestaetigung": "Konferenz-Registrierungsbestätigung",
    "konferenz-anmeldebestaetigung": "Konferenz-Anmeldebestätigung", "email-einladung-vortrag": "E-Mail Einladung zum Vortrag",
    "flug-preisvergleich": "Flug-Preisvergleich", "email-stipendienzusage": "E-Mail Stipendienzusage",
    "flug-angebot": "Flugangebot", "konferenz-registrierung": "Konferenz-Registrierung",
    "beschaffungsantrag": "Beschaffungsantrag", "vergabevermerk": "Vergabevermerk", "wps-warenkorb": "WPS-Warenkorb",
    "email-beschaffungsantrag": "E-Mail Beschaffungsantrag", "email-korrespondenz": "E-Mail-Korrespondenz",
    "angebot-1": "Erstes Angebot", "angebot-2": "Zweites Angebot", "angebot-3": "Drittes Angebot",
    "rechnung-leuchten": "Rechnung Leuchten", "rechnung-stative": "Rechnung Stative",
    "rechnung-fachbuch": "Rechnung", "beleg-1": "Kassenbeleg", "rechnung-kopfhoerer": "Rechnung",
    "rechnung-laborbedarf": "Rechnung", "gutschrift-druckerei": "Gutschrift", "rechnung-druckerei": "Rechnungen der Druckerei",
    "rechnung-adapter-1": "Erste Rechnung", "rechnung-adapter-2": "Zweite Rechnung", "rechnung-teekueche": "Rechnung",
    "rechnung-konferenzgebuehr": "Rechnung Konferenzgebühr",
}
A4_SIZE = A4


def cover_mail(titles):
    items = "\n".join(f" - {t}" for t in titles)
    return f"""E-Mail – Anlagen zum Antrag




 Unterlagen zum Antrag
 Von: Antragsteller:in
 An: zuständige Stelle


 Sehr geehrte Damen und Herren,

 anbei finden Sie die folgenden Anlagen zum Antrag:

{items}

 Mit freundlichen Grüßen
 Antragsteller:in
"""


def L6(c):
    if c.base == "beschaffungsantrag-08":
        d = c.doc("rechnung-leuchten")
        m = re.search(r"^\s*(\d\d\.\d\d\.\d{4})\s+(I\. Sonnabend-Rüger)\s*$", d.text, re.M)
        if not m:
            raise Skip("stamp not found")
        date, who = m.group(1), m.group(2)
        copy = Doc("rechnung-leuchten-kopie.pdf", orig=None, src=None, size=d.size,
                   text=f"Kopie – sachlich richtig, {who}, {date}\n\n" + d.text)
        return Result(c.fresh() + [copy], f"added rechnung-leuchten-kopie.pdf: the invoice RE-27-10418 again, marked "
                      f"'Kopie – sachlich richtig, {who}, {date}' (name and date of the stamp already on the invoice)",
                      "Medium: a second copy of an invoice may be summed twice by a solver; the marking says Kopie and "
                      "the invoice number, amounts and stamp are identical")
    if len(c.docs) == 1 and c.docs[0].stem.startswith("email-"):
        raise Skip("the only document is the request e-mail itself; a cover e-mail would list nothing")
    titles = [TITLES.get(d.stem) or d.stem.replace("-", " ").capitalize() for d in c.docs]
    mail = Doc("anschreiben.pdf", orig=None, src=None, size=A4_SIZE, text=cover_mail(titles))
    return Result(c.fresh() + [mail], f"added anschreiben.pdf: cover e-mail that only lists the {len(titles)} attachment(s) "
                  "by title (no sender name, no date, no amount)",
                  "Low; the mail names no person, date, amount or completeness claim")


LAYERS = {1: L1, 2: L2, 3: L3, 4: L4, 5: L5, 6: L6}


# --------------------------------------------------------------------------- #
# Build and verify
# --------------------------------------------------------------------------- #
def all_cases():
    cases = []
    for s in SETS:
        names = sorted(p.name for p in (DATASETS / s / "inputs").iterdir() if p.is_dir() and not p.name.startswith("retrieval"))
        for b in names:
            cases.append(Case(len(cases), s, b))
    return cases


def check_case(c, k, res, outdir, problems):
    ident = f"{c.base}-L{k}"
    names = sorted(p.name for p in outdir.glob("*"))
    got = {n: mv.pdftotext(outdir / n) for n in names}
    for n in names:
        if not n.endswith(".pdf") or n != n.lower() or "/" in n:
            problems.append(f"{ident}/{n}: file name must be lower-case .pdf")
    # every rewritten document round-trips; every untouched one is a byte copy
    for d in res.docs:
        target = outdir / d.name
        if not target.exists():
            problems.append(f"{ident}: {d.name} missing")
            continue
        if d.rewritten:
            if mv.norm(got[d.name]) != mv.norm(d.text):
                problems.append(f"{ident}/{d.name}: text does not round-trip")
                for x, y in zip(mv.norm(got[d.name]), mv.norm(d.text)):
                    if x != y:
                        problems.append(f"   got : {x}\n   want: {y}")
                        break
            if re.search("�", got[d.name]):
                problems.append(f"{ident}/{d.name}: replacement character in text")
        elif target.read_bytes() != d.src.read_bytes():
            problems.append(f"{ident}/{d.name}: copy differs")
    src_text = "\n".join(d.orig for d in c.docs)
    dst_text = "\n".join(got[n] for n in names)
    ns, nd = canon_numbers(src_text), canon_numbers(dst_text)
    if k == 4:
        ds, rs = canon_dates(src_text)
        dd, rd = canon_dates(dst_text)
        if ds != dd:
            problems.append(f"{ident}: dates differ: missing {dict(ds - dd)} new {dict(dd - ds)}")
        if rs != rd:
            problems.append(f"{ident}: numbers differ: missing {dict(rs - rd)} new {dict(rd - rs)}")
        ns = nd = collections.Counter()  # compared above
    if k == 6:
        if set(ns) != set(nd) or any(nd[x] < v for x, v in ns.items()):
            problems.append(f"{ident}: numbers differ: missing {dict(ns - nd)} new {sorted(set(nd) - set(ns))}")
    elif ns != nd:
        problems.append(f"{ident}: numbers differ: missing {dict(ns - nd)} new {dict(nd - ns)}")
    ws, wd = words(src_text), words(dst_text)
    gone, new = ws - wd, wd - ws
    if k == 1:
        h = lambda ps: sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in ps)
        if h(sorted((DATASETS / c.set / "inputs" / c.base).glob("*.pdf"))) != h(sorted(outdir.glob("*.pdf"))):
            problems.append(f"{ident}: file bytes differ from the source")
        if len(names) > 1:
            first_src = hashlib.sha256(c.docs[0].src.read_bytes()).hexdigest()
            first_dst = hashlib.sha256((outdir / names[0]).read_bytes()).hexdigest()
            if first_src == first_dst:
                problems.append(f"{ident}: the alphabetically first file is still the same document")
    elif k == 2:
        allowed = set()
        for d in c.docs:
            for l in lines_of(d.orig):
                if BOX.search(l):
                    allowed |= set(words(l))
        if set(new) or set(gone) - allowed:
            problems.append(f"{ident}: unexpected words changed: gone {sorted(set(gone) - allowed)} new {sorted(new)}")
        for dname, items in res.meta["ticks"].items():
            dl = lines_of(got[dname])
            d = next(x for x in res.docs if x.name == dname)
            ol = lines_of(d.orig)
            # the source line index equals the output line index only when no blank lines are dropped: compare by search
            for i, st, opts in items:
                found = False
                for line in dl:
                    if st == "plain":
                        tick = [lab for t, lab, _ in opts if t]
                        if tick and line.strip().endswith(tick[0]) and not re.search(r"[☒☐■□]", line):
                            found = True
                    elif all(re.search(expected_box_regex(st, t, lab), line) for t, lab, _ in opts):
                        found = True
                    if found:
                        break
                if not found:
                    problems.append(f"{ident}/{dname}: ticked answer of line {i} not preserved ({opts})")
    elif k == 3:
        style = "A" if c.idx % 2 == 0 else "B"
        src_w, dst_w = label_words(style)
        bad_gone, bad_new = set(gone) - src_w, set(new) - dst_w
        if bad_gone or bad_new:
            problems.append(f"{ident}: non-label words changed: gone {sorted(bad_gone)} new {sorted(bad_new)}")
    elif k == 4:
        for n in names:
            t = got[n]
            iso_n = len(re.findall(r"(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])", t))
            num_n = (len(re.findall(r"(?<![\d.])\d{1,2}\.\d{2}\.(?:\d{4})?(?!\d)", t)) +
                     len(re.findall(r"\d{2}-(?:" + "|".join(MONTHS_EN) + r")-\d{4}", t)))
            long_n = len(re.findall(r"(?<![\d.])\d{1,2}\. (?:" + "|".join(MONTHS_DE) + r")\b", t))
            mode = res.meta["modes"].get(n)
            if mode == "iso" and (num_n or long_n):
                problems.append(f"{ident}/{n}: dates not all ISO (numeric {num_n}, in words {long_n})")
            if mode == "long" and (num_n or iso_n):
                problems.append(f"{ident}/{n}: dates not all in words (numeric {num_n}, ISO {iso_n})")
        allowed_new = set(MONTHS_DE) | {"EUR", "bis"}
        allowed_gone = set(MONTHS_EN) | set(MONTHS_DE) | {"bis"}
        if set(new) - allowed_new or set(gone) - allowed_gone:
            problems.append(f"{ident}: words changed: gone {sorted(set(gone) - allowed_gone)} new {sorted(set(new) - allowed_new)}")
    elif k == 5:
        if collections.Counter(mv.norm(src_text)) != collections.Counter(mv.norm(dst_text)):
            problems.append(f"{ident}: line multiset differs")
    elif k == 6:
        if gone:
            problems.append(f"{ident}: words of the source disappeared: {sorted(gone)}")
        for n in names:
            if not any(n == d.name for d in c.docs):
                added = got[n]
                if re.search(r"\d", added) and c.base != "beschaffungsantrag-08":
                    problems.append(f"{ident}/{n}: the added document contains digits")


def build(check=False):
    problems, built, skipped = [], [], []
    for s in SETS:
        d = OUT / s
        if (d / "inputs").exists():
            shutil.rmtree(d / "inputs")
        (d / "inputs").mkdir(parents=True)
    truth = {s: [] for s in SETS}
    for c in all_cases():
        for k, fn in LAYERS.items():
            ident = f"{c.base}-L{k}"
            try:
                res = fn(c)
            except Skip as e:
                skipped.append((c, k, str(e)))
                continue
            outdir = OUT / c.set / "inputs" / ident
            outdir.mkdir(parents=True)
            for d in res.docs:
                target = outdir / d.name
                if target.exists():
                    problems.append(f"{ident}: duplicate file name {d.name}")
                if d.rewritten:
                    write_pdf(target, d.text, d.size, d.name)
                else:
                    shutil.copyfile(d.src, target)
            check_case(c, k, res, outdir, problems)
            built.append((c, k, res))
            truth[c.set].append({"antrag": ident, "result": c.result,
                                 "begruendung": f"Layout-Variante L{k} von {c.base}: {c.reason}"})
    for s in SETS:
        with open(OUT / s / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            for row in sorted(truth[s], key=lambda r: r["antrag"]):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return problems, built, skipped


def table(built, skipped):
    rows = ["| Case | Base | Layer | What changed (presentation only) | Expected | Risk that a fact changed |",
            "|---|---|---|---|---|---|"]
    for c, k, res in built:
        rows.append(f"| `{c.base}-L{k}` ({SHORT[c.set]}) | `{c.base}` | L{k} {LAYER_NAME[k]} | {res.what} | {c.result} | {res.risk} |")
    rows += ["", "Skipped:", ""]
    for c, k, why in skipped:
        rows.append(f"- `{c.base}-L{k}` ({SHORT[c.set]}, L{k} {LAYER_NAME[k]}): {why}")
    return "\n".join(rows)


def summary(built, skipped):
    cnt = collections.Counter((SHORT[c.set], k) for c, k, _ in built)
    lines = ["built per layer and case type (trip/proc/exp):"]
    for k in LAYERS:
        lines.append(f"  L{k} {LAYER_NAME[k]:<18} " + "  ".join(f"{t}={cnt[(t, k)]}" for t in ("trip", "proc", "exp")) +
                     f"  total={sum(cnt[(t, k)] for t in ('trip', 'proc', 'exp'))}")
    lines.append(f"  total cases: {len(built)}, labels: " +
                 str({r: sum(c.result == r for c, _, _ in built) for r in ("angenommen", "abgelehnt")}))
    lines.append(f"skipped: {len(skipped)}")
    for c, k, why in skipped:
        lines.append(f"  {c.base}-L{k}: {why}")
    return "\n".join(lines)


def main():
    problems, built, skipped = build()
    if "--table" in sys.argv:
        print(table(built, skipped))
        return
    print(summary(built, skipped))
    for p in problems:
        print("PROBLEM:", p)
    if "--check" in sys.argv:
        print("check:", "FAILED" if problems else "ok", f"({len(built)} cases verified)")
        if problems:
            sys.exit(1)


if __name__ == "__main__":
    main()
