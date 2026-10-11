"""Facts computed by code from the case documents (round R11).

The model is weak at arithmetic and comparisons (Qwen: "2.670 € unter
1.000 €"), so code reads the labelled fields, does the sums and comparisons,
and states the result as plain German lines. A fact that cannot be read for
certain is reported as "unklar", never guessed. Every rule used here is quoted
in the development notes (not included); nothing is specific to one practice case.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from parsing import _DE, _EN, Amount, number_value, parse_amounts, parse_dates

HEADER = (
    "FAKTEN (von Code aus den Belegen berechnet; 'unklar' heißt: nicht sicher "
    "erkannt, dann selbst anhand der Belege prüfen):"
)
THRESHOLD = Decimal("1000")

# Framework-contract product groups, "Rahmenverträge - INTERN - Uni Kassel":
# "Büromaterial, PC's/Notebooks und Monitore, Büropapiere, Bürodrehstühle,
# Seminarstühle, Büromobiliar, Kopiergeräte, Software-Produkte von Microsoft".
FRAMEWORK_WORDS = [
    r"PCs?", r"Desktop-PCs?", r"Notebooks?", r"Laptops?", r"Monitore?", r"Bildschirme?",
    r"Bürodrehst(?:uhl|ühle)", r"Drehst(?:uhl|ühle)", r"Seminarst(?:uhl|ühle)", r"Bürost(?:uhl|ühle)",
    r"Büromöbel", r"Büromobiliar",
    r"Schreibtische?", r"Kopiergeräte?", r"Kopierer", r"Büropapiere?", r"Kopierpapiere?",
    r"Druckerpapiere?", r"Docking-?Stations?", r"Microsoft[- ]Office", r"MS[- ]Office", r"Microsoft 365",
    r"Office chairs?", r"Toner\w*", r"Ordner", r"Druckerpatronen?", r"Tintenpatronen?", r"Kugelschreiber",
    r"Haftnotizen", r"Textmarker", r"Helium\w*", r"Flaschengase?", r"Stickstoff",
]
# Whole word, not part of a compound ("PC-Schnittstelle", "Lab Notebook" are no framework items).
_FRAMEWORK_RE = re.compile(r"(?<![\wÄÖÜäöü-])(" + "|".join(FRAMEWORK_WORDS) + r")(?![\wÄÖÜäöü-])", re.IGNORECASE)
_NOT_FRAMEWORK_BEFORE = re.compile(r"(?:Lab|Labor|inkl\.?|mit|für|Software für|Netzteil|Ladegerät|Tasche|Hülle|Adapter|Kabel|Akku|Halterung|Halter|Ständer|Schutzfolie)\s*$", re.IGNORECASE)
# "Monitor" as a loudspeaker or a patient/baby monitor is no framework item.
_NOT_FRAMEWORK_LINE = re.compile(r"Lautsprecher|Speaker|Studio|Audio|Kopfhörer|Baby|Patienten|Vital", re.IGNORECASE)


def framework_items(text: str) -> list[str]:
    """Framework product words that name the ordered item itself: only in
    item lines (a line with an amount), within the first words of the item
    text, and not after 'Lab', 'inkl.', 'mit', 'für' (rules-review.md, 4)."""
    hits = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not parse_amounts(line):
            # An item wrapped over two lines: the amount is on the next line.
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not (re.match(r"^\s*(?:Pos\.?\s*)?\d+[.)]?\s", line) and parse_amounts(nxt)):
                continue
        if _NOT_FRAMEWORK_LINE.search(line):
            continue
        desc = re.split(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}", line)[0]
        desc = re.sub(r"^\s*(?:Pos\.?\s*)?\d+[.)]?\s*(?:\d+\s*)?(?:[x×]\s*)?", "", desc)
        head = desc.strip()[:80]
        for m in _FRAMEWORK_RE.finditer(head):
            if not _NOT_FRAMEWORK_BEFORE.search(head[:m.start()]):
                hits.append(m.group(1))
    return hits

# A1 certificates: "innerhalb der EU, des EWR, der Schweiz oder in einem der
# Staaten, mit denen ein bilaterales Abkommen besteht" (Dienstreisemanagement).
EU_EWR_CH = [
    "belgien", "bulgarien", "dänemark", "estland", "finnland", "frankreich", "griechenland",
    "irland", "italien", "kroatien", "lettland", "litauen", "luxemburg", "malta", "niederlande",
    "österreich", "polen", "portugal", "rumänien", "schweden", "slowakei", "slowenien", "spanien",
    "tschechien", "ungarn", "zypern", "island", "liechtenstein", "norwegen", "schweiz",
    "belgium", "denmark", "france", "greece", "ireland", "italy", "netherlands", "austria",
    "poland", "spain", "sweden", "switzerland", "norway", "czech",
]
OUTSIDE_EU = [
    "usa", "vereinigte staaten", "united states", "kanada", "canada", "japan", "china", "indien",
    "india", "australien", "australia", "brasilien", "brazil", "mexiko", "mexico", "südkorea",
    "korea", "singapur", "singapore", "südafrika", "südafrika", "neuseeland", "argentinien",
    "chile", "türkei", "turkey", "israel", "vereinigtes königreich", "großbritannien", "uk",
    "united kingdom", "england", "schottland",
]
# Cities that appear without a country often enough to matter.
CITY_COUNTRY = {"rotterdam": "niederlande", "amsterdam": "niederlande", "barcelona": "spanien",
                "madrid": "spanien", "paris": "frankreich", "wien": "österreich", "zürich": "schweiz",
                "boston": "usa", "new york": "usa", "london": "vereinigtes königreich", "tokio": "japan"}

# "Dienstreisen in die Russische Föderation, in die Ukraine, nach Belarus, Moldau
# (die Gebiete im Süden und Osten, die an die Ukraine grenzen), Niger, Iran,
# Israel, in die Palästinensischen Gebiete und Libanon [werden] bis auf Weiteres
# nicht genehmigt" (Dienstreisemanagement). Capitals and large cities included.
NOT_APPROVED = {
    "Russische Föderation": r"Russische Föderation|Russland|Russia|Moskau|Moscow|Sankt Petersburg|St\. Petersburg",
    "Ukraine": r"Ukraine|Kiew|Kyjiw|Kyiv|Kiev|Lwiw|Lviv|Charkiw|Odessa",
    "Belarus": r"Belarus|Weißrussland|Minsk",
    "Moldau (Gebiete an der Grenze zur Ukraine)": r"Moldau|Moldawien|Moldova|Chişinău|Chisinau|Transnistrien",
    "Niger": r"Niger|Niamey",
    "Iran": r"Iran|Teheran|Tehran",
    "Israel": r"Israel|Tel[- ]?Aviv|Jerusalem|Haifa",
    "Palästinensische Gebiete": r"Palästin\w*|Palestin\w*|Gaza|Westjordanland|West Bank|Ramallah",
    "Libanon": r"Libanon|Lebanon|Beirut",
}
_NOT_APPROVED_RE = {k: re.compile(rf"(?<![\wÄÖÜäöü])(?:{v})(?![\wÄÖÜäöü])", re.IGNORECASE) for k, v in NOT_APPROVED.items()}

# Cost rows for evening and accompanying programmes ("Kosten für Begleit- und
# Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht erstattungsfähig").
# A meal already in the conference fee ("inkl.") or a per-diem cut is no such row.
EVENING_RE = re.compile(r"Conference[- ]Dinner|Konferenz[- ]?(?:dinner|abendessen)|Gala[- ]?(?:dinner|abend|diner)|Festessen|Bankett|Banquet|Abendprogramm|Begleitprogramm|Rahmenprogramm|Social (?:event|programme|program)|\bDinner\b|Stadtführung|City tour", re.IGNORECASE)
_NOT_A_COST_ROW = re.compile(r"inkl\.?|inklusive|enthalten|included|Tagegeld|Verpflegung|Kürzung|nicht gebucht", re.IGNORECASE)

# Hospitality for staff only ("Nicht erstattungsfähige Aufwendungen sind:
# Bewirtungen, an denen keine externen Personen teilgenommen haben",
# Bewirtungskostenrichtlinie). Courtesies are allowed only for "Gästen der Universität".
HOSPITALITY_RE = re.compile(r"Kaffee|Coffee|Tee\b|Kuchen|Gebäck|Kekse|Brötchen|Snacks?|Getränke|Catering|Bewirtung|Pizza|Buffet|Imbiss|Frühstück|Mittagessen|Abendessen", re.IGNORECASE)
INTERNAL_RE = re.compile(r"(?:keine|ohne)\s+externe(?:n)?\s+(?:Gäste|Personen|Teilnehmer\w*)|nur\s+(?:Beschäftigte|Mitarbeitende|Mitarbeiter\w*|Universitätsangehörige)|interne[nrs]?\s+(?:Team)?(?:besprechung|sitzung|meeting|runde|klausur)|Teambesprechung|Teamsitzung|Teammeeting|Weihnachtsfeier|Betriebsfeier|Abschiedsfeier|Geburtstagsfeier|Betriebsausflug|Teamevent|(?:Mitarbeiter|Team)frühstück|Arbeitsessen|Teeküche|Kaffeeküche|Büroküche|Sozialraum|Kaffeekasse|Kaffeevorrat|für die Beschäftigten|für das Team|Jour fixe|Dienstbesprechung|Gruppenbesprechung|Institutssitzung|Fachgebietssitzung", re.IGNORECASE)

# Restaurant hospitality needs "Anlass, Teilnehmerliste" (Bewirtungskostenrichtlinie):
# a meal receipt with no document naming the persons entertained.
MEAL_RE = re.compile(r"Bewirtungsbeleg|Gasthaus|Gaststätte|Restaurant|Ristorante|Trattoria|Brauhaus|Wirtshaus|Bistro", re.IGNORECASE)

NET_LABEL = re.compile(r"Summe\s*\(?netto\)?|Subtotal\s*\(net\)|Warenwert netto|Nettobetrag|Gesamtbetrag netto|Summe .*netto|Endbetrag netto|Gesamt netto|Nettosumme|Net total|Total net", re.IGNORECASE)
GROSS_LABEL = re.compile(r"Angebotssumme brutto|Gesamtbetrag brutto|Summe\s*\(?brutto\)?|Rechnungsbetrag|Invoice total|Gesamt brutto|Total due|Total paid|Gutschriftsbetrag|SUMME EUR|Gesamtsumme", re.IGNORECASE)
INVOICE_NO = re.compile(r"(?:Rechnung(?:s)?[- ]?(?:Nr\.?|nummer)|Invoice (?:No\.?|number)|Gutschrift(?:s)?[- ]?(?:Nr\.?|nummer))\s*:?\s*([A-Z0-9][A-Z0-9 \-/]{3,})", re.IGNORECASE)


def euro(value: Decimal) -> str:
    """2667.00 -> '2.667,00 €'."""
    q = f"{value:,.2f}"
    return q.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _field(text: str, label: str) -> Optional[str]:
    """Value after 'Label:' (or 'Label  value' in form tables) on the same line."""
    m = re.search(rf"^\s*(?:{label})\s*:?\s{{1,}}(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


TICKED = r"(?:\[\s*[xX✓✔]\s*\]|\(\s*[xX]\s*\)|[☒☑✓✔■●⊠]|(?<!\w)[xX](?=\s))"
EMPTY = r"(?:\[\s*\]|\(\s*\)|[☐□○])"


def _checkbox(text: str, label: str) -> Optional[str]:
    """The ticked answer of a form field: 'ja', 'nein', 'nicht angekreuzt'
    (only when empty boxes are shown) or 'unklar'. Boxes may stand before or
    after their word ('[X] ja', 'ja ☒  nein ☐'); a plain word counts too."""
    line = _field(text, label)
    if not line:
        return None
    after = re.match(rf"^\s*\w+\s*(?:{TICKED}|{EMPTY})", line) is not None   # 'ja ☒ nein ☐'
    m = re.search(rf"(\w+)\s*{TICKED}", line) if after else re.search(rf"{TICKED}\s*(\w+)", line)
    if m:
        return m.group(1).lower()
    if re.search(EMPTY, line):
        return "nicht angekreuzt"
    word = re.match(r"\s*(ja|nein|yes|no)\b", line, re.IGNORECASE)
    return {"yes": "ja", "no": "nein"}.get(word.group(1).lower(), word.group(1).lower()) if word else "unklar"


def _last_amount_on(lines: Iterable[str], label: re.Pattern[str]) -> Optional[Amount]:
    found = None
    for line in lines:
        if label.search(line):
            amounts = [a for a in parse_amounts(line) if a.currency in (None, "EUR")]
            if amounts:
                found = amounts[-1]
    return found


def _near(lines: Iterable[str], word: str) -> Optional[Decimal]:
    """The amount written right before or right after `word` ("673,00 € netto",
    "Summe netto   3.384,00 €"), never another amount on the same line (the
    sentence "unter 1.000 € liegt" must not be read as the order value)."""
    pat = re.compile(rf"({_DE}|{_EN})\s*(?:€|EUR)?\s*,?\s*{word}\b|{word}\)?\s*:?\s*(?:€|EUR)?\s*({_DE}|{_EN})(?!\d)", re.IGNORECASE)
    found = None
    for line in lines:
        for m in pat.finditer(line):
            found = number_value(m.group(1) or m.group(2))
    return found


def _notes(notes: list[str]) -> list[str]:
    """Problems code found for certain, as plain words at the end (R11b)."""
    if not notes:
        return ["- PRÜFHINWEISE von Code: keine Auffälligkeit erkannt (die übrigen Punkte selbst prüfen)"]
    return ["- PRÜFHINWEISE von Code (mögliche Ablehnungsgründe, bitte anhand der Belege bestätigen):"] + [f"  * {n}" for n in notes]


def _first_date(value: Optional[str]):
    if not value:
        return None
    dates = parse_dates(value)
    return dates[0].value if dates else None


def _yn(flag: Optional[bool]) -> str:
    return "unklar" if flag is None else ("JA" if flag else "NEIN")


# ------------------------------------------------------------------ procurement

# An offer header: the word alone on a line, or followed by its number or date.
# At the start of a line or in a right-hand column (3+ spaces before), ending the line:
# "Angebot", "ANGEBOT Nr. AN-27-0311", "Angebot 2027/0457", "Angebot Nr. Q-1 vom 12.02.2027" (R20).
OFFER_HEAD = re.compile(r"(?:^|(?<=\s{3}))[ \t]*(?:Angebot|Kostenvoranschlag|Quotation|Quote|Offer)"
                        r"(?:[ \t]*(?:Nr\.?|No\.?|Nummer|number|#)?[ \t]*[\w\-/]*\d[\w\-/]*)?(?:[ \t]+vom[ \t]+\S+)?[ \t]*$",
                        re.IGNORECASE | re.MULTILINE)
NOT_AN_OFFER = re.compile(r"vergleich|anfrage|vermerk|request|antrag", re.IGNORECASE)
SINGLE_SOURCE = re.compile(r"Alleinstellung|Einzelanbieter|nur (?:ein(?:en)?|bei(?:m)?) (?:Anbieter|Hersteller|Lieferanten)|nur beim Hersteller|kein(?:e)? weiteren? (?:Anbieter|Angebote)|weitere Angebote (?:sind )?nicht möglich|Ersatzteil|Kompatibilität|kompatibel|sole supplier|single source", re.IGNORECASE)
UNSUITABLE = re.compile(r"scheidet aus|ausgeschlossen|erfüllt\b.{0,60}\bnicht|ungeeignet|nicht geeignet|technisch nicht|does not meet", re.IGNORECASE)


def _offer_heads(text: str) -> list[re.Match]:
    """Offer headers that start a new offer: a new offer number, or a bare title
    ("ANGEBOT") more than 12 lines after the last counted header (one offer has
    its number and its title close together; R20 merged offers)."""
    kept, seen, last_line = [], set(), None
    for m in OFFER_HEAD.finditer(text):
        line = text.count("\n", 0, m.start())
        num = re.search(r"\d[\w\-/]*", m.group(0))
        if num:
            if num.group(0) in seen:
                continue
            seen.add(num.group(0))
            if last_line is not None and line - last_line <= 12 and not re.search(r"\d", kept[-1].group(0)):
                kept[-1] = m          # the number belongs to the title just above
                last_line = line
                continue
        elif last_line is not None and line - last_line <= 12:
            continue
        kept.append(m)
        last_line = line
    return kept


def _proc_kind(name: str, text: str) -> str:
    """request | note | invoice | other, by file name or by the document's own head (R20: files may be named scan_0042.pdf)."""
    head = "\n".join(text.splitlines()[:15])
    if re.search(r"antrag|email|e-mail|bestellung|request", name, re.I) or re.search(r"Beschaffungsantrag|Bestellanforderung|^\s*(?:Von|From|An|To|Cc)\s*:|E-Mail\b", head, re.I | re.M):
        return "request"
    if re.search(r"vermerk|vergleich|anfrage", name, re.I) or re.search(r"Vergabevermerk|Angebotsvergleich|Preisvergleich", head, re.I):
        return "note"
    if re.search(r"rechnung|invoice", name, re.I) or re.search(r"^\s*Rechnung\b|Rechnungsnummer|Rechnung Nr|\bInvoice\b", head, re.I | re.M):
        return "invoice"
    return "other"


def _offers_in(name: str, text: str) -> int:
    """Number of offers a document holds, or 1 for a file named as an offer."""
    if NOT_AN_OFFER.search(name) or _proc_kind(name, text) in ("request", "note", "invoice"):
        return 0
    heads = len(_offer_heads(text))
    if heads:
        return heads
    return 1 if re.search(r"angebot|offer|quot|kostenvoranschlag", name, re.IGNORECASE) else 0


def _is_offer(name: str, text: str) -> bool:
    return _offers_in(name, text) > 0


def _is_request(name: str, text: str = "") -> bool:
    return _proc_kind(name, text) == "request"


def _segments(text: str) -> list[str]:
    """One text per offer: split at offer headers (several offers in one PDF)."""
    starts = [m.start() for m in _offer_heads(text)]
    if len(starts) < 2:
        return [text]
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def procurement_facts(docs: dict[str, str]) -> list[str]:
    out: list[str] = []
    offers = {n: t for n, t in docs.items() if _is_offer(n, t)}
    requests = {n: t for n, t in docs.items() if _is_request(n, t) and n not in offers}
    offer_nets: dict[str, Optional[Decimal]] = {}
    offer_amounts: set[Decimal] = set()
    for n, t in offers.items():
        segs = _segments(t)
        for i, seg in enumerate(segs):
            a = _last_amount_on(seg.splitlines(), NET_LABEL)
            offer_nets[n if len(segs) == 1 else f"{n} (Angebot {i + 1})"] = a.value if a else None
        offer_amounts |= {abs(x.value) for x in parse_amounts(t) if x.currency in (None, "EUR")}
    counted = sum(_offers_in(n, t) for n, t in offers.items())
    form_count = None
    for t in requests.values():
        v = _field(t, r"Eingeholte Angebote|Anzahl (?:der )?Angebote")
        if v and re.match(r"\d+\b", v):
            form_count = int(re.match(r"\d+", v).group())
            break
    sure = form_count is None or form_count == counted
    out.append(f"- Anzahl vorgelegter Angebote: {counted if sure else 'unklar'}" + (f" ({', '.join(sorted(offers))})" if offers else "")
               + (f"; laut Formular: {form_count}" if form_count is not None else ""))
    for n, v in sorted(offer_nets.items()):
        out.append(f"- {n}: Summe netto {euro(v) if v is not None else 'unklar'}")

    req_net = req_gross = None
    for t in requests.values():
        lines = t.splitlines()
        a = _near([l for l in lines if re.search(r"summe|gesamt|zusammen", l, re.I)], "netto")
        if a is None:
            labelled = _last_amount_on(lines, NET_LABEL)
            a = labelled.value if labelled else None
        b = _near([l for l in lines if re.search(r"summe|gesamt|zusammen|betrag", l, re.I)], "brutto")
        req_net = req_net if req_net is not None else a
        req_gross = req_gross if req_gross is not None else b
    known = [v for v in offer_nets.values() if v is not None]
    basis = req_net
    if basis is not None:
        out.append(f"- Auftragswert netto: {euro(basis)}; netto ≥ 1.000 €: {_yn(basis >= THRESHOLD)}")
    elif known and (min(known) >= THRESHOLD or max(known) < THRESHOLD):
        basis = min(known)
        out.append(f"- Auftragswert netto laut Angeboten zwischen {euro(min(known))} und {euro(max(known))}; netto ≥ 1.000 €: {_yn(min(known) >= THRESHOLD)}")
    elif req_gross is not None and req_gross < THRESHOLD:
        out.append(f"- Nur Bruttobetrag genannt ({euro(req_gross)}); damit liegt der Nettobetrag sicher unter 1.000 €: JA")
        basis = req_gross
    else:
        out.append("- Auftragswert netto: unklar")
    # Only material gaps count (README: "nur wesentliche Abweichungen"): within 10 %
    # of an offer total, or equal to a single position of an offer (part order).
    fits = None
    if req_net is not None and known:
        fits = any(abs(req_net - v) <= v * Decimal("0.10") for v in known) or req_net in offer_amounts
        out.append(f"- Antragsbetrag netto passt zu einem Angebot (höchstens 10 % Abweichung oder eine Position): {_yn(fits)}")
        chosen = [v for v in known if v == req_net]
        if chosen and len(known) > 1:
            out.append(f"- Gewähltes Angebot ist das günstigste: {_yn(req_net <= min(known))} (günstigstes Angebot: {euro(min(known))})")

    for t in requests.values():
        box = _checkbox(t, r"Rahmenvertragsprodukt")
        if box:
            out.append(f"- Formularfeld 'Rahmenvertragsprodukt': {box}")
            break
    hits = sorted({h for t in docs.values() for h in framework_items(t)}, key=str.lower)
    # Helium has a framework contract only from 01.05. to 31.07.2026 (Rahmenverträge page; rule-gaps-3, 16).
    dates = [d.value for t in docs.values() for d in parse_dates(t)]
    in_window = any(date(2026, 5, 1) <= d <= date(2026, 7, 31) for d in dates)
    hits = [h for h in hits if not (h.lower().startswith("helium") and not in_window)]
    out.append("- Artikel aus einer Rahmenvertrags-Produktgruppe (PCs/Notebooks/Monitore, Bürostühle, Büromöbel, Kopiergeräte, Büropapier, Büromaterial, Microsoft, Gase): "
               + (f"JA ({', '.join(hits)})" if hits else "NEIN"))
    supplier = next((v for t in requests.values() for v in [_field(t, r"Vorgesehener Lieferant|Lieferant|Supplier")] if v), None)
    if supplier is None:
        supplier = next((v for t in docs.values() for v in [_field(t, r"Vorgesehener Lieferant|Lieferant|Supplier")] if v), None)
    # Lines that name the framework route: the partner, a WPS basket or a catalogue
    # "Rahmenvertrag …"; in a WPS basket its "Lieferant" line names the partner.
    partner_lines = []
    for t in docs.values():
        wps = re.search(r"\bWPS\b|Warenkorb|Katalog\s*:?\s*Rahmenvertrag", t, re.IGNORECASE) is not None
        for l in t.splitlines():
            if re.search(r"Rahmenvertragspartner|Katalog\s*:?\s*Rahmenvertrag", l, re.IGNORECASE) or (wps and re.search(r"^\s*Lieferant\s*:", l, re.IGNORECASE)):
                partner_lines.append(l.strip())
    framework_route = False
    if supplier:
        out.append(f"- Vorgesehener Lieferant: {supplier[:120]}")
    if partner_lines:
        out.append(f"- Genannter Rahmenvertragspartner oder Rahmenvertragskatalog: {' | '.join(partner_lines)[:200]}")
        plain = re.sub(r"\([^)]*\)", " ", supplier or "")
        token = next((w for w in re.split(r"[\s,()]+", plain) if len(w) > 2 and not re.fullmatch(r"GmbH|AG|KG|Co\.?|mbH|und|der|die|das", w, re.I)), None)
        if token:
            framework_route = any(token.lower() in l.lower() for l in partner_lines)
            out.append(f"- Lieferant ist der Rahmenvertragspartner: {_yn(framework_route)}")
    # The route named in other words ("über den Rahmenvertrag Büromaterial (Firma)"): no note, the model checks it.
    route_named = any(re.search(r"\b(?:über|aus|im|nach|gemäß|laut|per|via)\s+(?:dem|den|des|einem|einen)?\s*Rahmenvertrag\b", l, re.I)
                      for t in docs.values() for l in t.splitlines())
    if route_named and not framework_route:
        out.append("- Bestellung über einen Rahmenvertrag genannt: JA (Lieferant selbst prüfen)")
    # R19: who ordered. A holder named in the form, or a professor in To/Cc/signature lines (practice 02, variant 03-v1).
    holder = next((v for t in docs.values() for v in [_field(t, r"Kostenstellenbevollmächtigte?:?r?|Kostenstellenverantwortliche?:?r?")] if v), None)
    holder_line = None
    for t in docs.values():
        for l in t.splitlines():
            if re.match(r"\s*(?:An|To|Cc|Von|From|Unterschrift|Freigabe|Genehmigt|beauftragt)\b", l, re.I):
                name = holder.split()[-1] if holder else None
                if (name and name in l) or (not holder and re.search(r"Prof\.", l)):
                    holder_line = l.strip()[:90]
                    break
        if holder_line:
            break
    if holder_line:
        out.append(f"- Kostenstellenbevollmächtigte:r am Auftrag beteiligt: JA ({holder_line})")
    if counted == 0 and basis is not None and basis < THRESHOLD and any(parse_amounts(t) for t in requests.values()):
        out.append("- Preisnachweis: Preise stehen im Antrag selbst (z. B. Webshop-Preise)")
    reason = any(SINGLE_SOURCE.search(t) for t in requests.values()) or any(SINGLE_SOURCE.search(t) for n, t in docs.items() if re.search(r"vermerk|begründ", n, re.I))
    if reason:
        out.append("- Begründung für weniger Vergleichsangebote (z. B. nur ein Anbieter) genannt: JA")
    # "Beschaffung - INTERN": three offers from 1.000 EUR net, except when
    # ordering from the framework-contract partner.
    notes = []
    if framework_route:
        out.append("- Bestellung beim Rahmenvertragspartner: JA; dann sind keine Vergleichsangebote nötig")
    elif basis is not None and basis < THRESHOLD:
        out.append("- Unter 1.000 € netto: Direktvergabe mit einem Angebot zulässig; Vergleichsangebote sind nicht nötig")
    elif basis is not None and basis >= THRESHOLD:
        out.append(f"- Ab 1.000 € netto sind drei Vergleichsangebote nötig; vorgelegt: {counted if sure else 'unklar'}")
        if sure and counted < 3 and not reason and not partner_lines and not route_named:
            notes.append(f"Auftragswert netto ≥ 1.000 €, aber nur {counted} Angebot(e) vorgelegt, ohne Bestellung beim Rahmenvertragspartner")
    if hits and supplier and partner_lines and not framework_route:
        notes.append("Rahmenvertragsprodukt, aber der Lieferant ist nicht der Rahmenvertragspartner")
    elif hits and not partner_lines and not framework_route and not route_named:
        notes.append(f"Artikel aus einer Rahmenvertrags-Produktgruppe ({', '.join(hits)}); eine Bestellung beim Rahmenvertragspartner ist nicht erkennbar (solche Produkte sind ausschließlich dort zu bestellen)")
    if fits is False:
        notes.append("Antragsbetrag netto weicht wesentlich von jedem Angebot ab")
    unsuitable = any(UNSUITABLE.search(t) for t in docs.values())
    if req_net is not None and known and req_net in known and len(known) > 1 and req_net > min(known) and not unsuitable:
        notes.append("nicht das günstigste Angebot gewählt")
    return out + _notes(notes)


# ------------------------------------------------------------------ business trip

def _country_status(dest: Optional[str]) -> Optional[bool]:
    """True = EU/EWR/CH (A1 needed), False = outside, None = unclear."""
    if not dest:
        return None
    d = dest.lower()
    for city, country in CITY_COUNTRY.items():
        if city in d:
            d += " " + country
    if any(re.search(rf"(?<!\w){re.escape(c)}(?!\w)", d) for c in EU_EWR_CH):
        return True
    if any(re.search(rf"(?<!\w){re.escape(c)}(?!\w)", d) for c in OUTSIDE_EU):
        return False
    return None


FORM_LABELS = re.compile(r"^\s*(?:Reiseziel|Zielort|Reiseort|Destination|Datum der Antragstellung|Antragsdatum|Date of application|"
                         r"Beginn Dienstgeschäft|Dienstgeschäft von|Reiseverlauf|Reiseablauf|Reise ins Ausland|Auslandsreise|priv\. Aufenthalt|"
                         r"Privater Aufenthalt|Departure|Anlass|Veranstaltung)\b", re.IGNORECASE | re.MULTILINE)
ABROAD_LABEL = r"Reise ins Ausland|Auslandsreise|Travel abroad|Abroad"
RETURN_LABEL = r"Rückreise|Heimreise|Rückfahrt|Return trip|Return"
BUSINESS_START = r"Beginn Dienstgeschäft|Dienstgeschäft von|Beginn des Dienstgeschäfts|Business start"
BUSINESS_END = r"Ende Dienstgeschäft|Dienstgeschäft bis|Ende des Dienstgeschäfts|Business end"
FUNDING = re.compile(r"(?:Reise)?stipendi(?:um|en)\w*|scholarship|travel grant|Reisekostenzuschuss|Reisezuschuss|Erasmus|DAAD|Grant Agreement|Mobility Agreement|"
                     r"Veranstalter übernimmt|vom Veranstalter (?:übernommen|bezahlt|getragen)|covered by the organi[sz]ers?|host (?:will )?covers?", re.IGNORECASE)
AWARDED = re.compile(r"Zusage|zugesagt|zuerkannt|bewilligt|gewährt|awarded|granted|erhalten|übernimmt|übernommen|bezahlt|getragen|cover|in Höhe von|amount of|Grant Agreement|Mobility Agreement", re.IGNORECASE)
ONLINE = re.compile(r"Online-(?:Konferenz|Tagung|Veranstaltung|Teilnahme|Meeting|Event)|(?:online|virtuell|virtual)e?[nr]?\s+(?:Teilnahme|Konferenz|Tagung|Veranstaltung|conference|meeting|participation)"
                    r"|Teilnahme (?:online|virtuell)|per Zoom|via Zoom|Webex|MS Teams|(?:rein|ausschließlich|nur) (?:online|virtuell)", re.IGNORECASE)
NOT_ONLINE = re.compile(r"hybrid|Präsenz|vor Ort|in person|on site", re.IGNORECASE)


def _us_dates(text: str) -> str:
    """Rewrite slash dates to dd.mm.yyyy when the document shows its order
    (a part above 12); ambiguous documents stay as they are."""
    pairs = [(int(a), int(b)) for a, b in re.findall(r"\b(\d{1,2})/(\d{1,2})/\d{4}\b", text)]
    if any(b > 12 for a, b in pairs):      # month/day/year
        return re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", lambda m: f"{int(m[2]):02d}.{int(m[1]):02d}.{m[3]}", text)
    if any(a > 12 for a, b in pairs):      # day/month/year
        return re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", lambda m: f"{int(m[1]):02d}.{int(m[2]):02d}.{m[3]}", text)
    return text


def trip_facts(docs: dict[str, str]) -> list[str]:
    out: list[str] = []
    # The form is the document with the most form labels, not the first file named "antrag".
    scored = sorted(((len(FORM_LABELS.findall(t)), bool(re.search(r"antrag", n, re.I)), n) for n, t in docs.items()), reverse=True)
    name = scored[0][2] if scored and scored[0][0] >= 2 else next((n for n in sorted(docs) if re.search(r"antrag", n, re.I)), None)
    if name is None:
        return ["- Antragsformular: nicht gefunden"]
    form = _us_dates(docs[name])
    applied = _first_date(_field(form, r"Datum der Antragstellung|Antragsdatum|Date of application|Application date"))
    start = _first_date(_field(form, r"Start|Beginn der Reise|Reisebeginn|Abreise|Departure|Start date"))
    business = _first_date(_field(form, BUSINESS_START))
    business_end = _first_date(_field(form, BUSINESS_END))
    begin = start or business
    out.append(f"- Antrag gestellt am: {applied.strftime('%d.%m.%Y') if applied else 'unklar'}; Reisebeginn: {begin.strftime('%d.%m.%Y') if begin else 'unklar'}")
    if applied and begin:
        out.append(f"- Antrag vor Reisebeginn gestellt: {_yn(applied < begin)}")
    dest = _field(form, r"Reiseziel|Zielort|Reiseort|Destination")
    abroad = _checkbox(form, ABROAD_LABEL)
    foreign = _country_status(dest) is not None
    out.append(f"- Reiseziel: {dest or 'unklar'}; Formularfeld 'Reise ins Ausland': {abroad or 'unklar'}")
    # No A1 fact line (R12d): the sentence "kein Ablehnungsgrund" made Qwen accept
    # whole trips (R12c, trips 03 and 05, reproduced). The rule card states A1.
    a1 = _field(form, r"A1-Bescheinigung")
    if a1:
        out.append(f"- Formularfeld 'A1-Bescheinigung': {a1[:100]}")
    private = _field(form, r"priv\. Aufenthalt|privater Aufenthalt|Private stay")
    if private:
        out.append(f"- Privater Aufenthalt laut Antrag: {private[:120]}")
    # Third-party money counts only where a document reports an award, not a form
    # label answered "nein" or an advert for grants.
    funding = sorted(n for n, t in docs.items()
                     if any(FUNDING.search(l) and AWARDED.search(l) and not re.search(r"\[\s*[xX]\s*\]\s*nein", l, re.I)
                            for l in t.splitlines()) or (FUNDING.search(t) and re.search(r"zusage|bewilligung|award", n, re.I)))
    out.append("- Hinweis auf Finanzierung durch Dritte (Stipendium, Zuschuss, Erasmus, Kostenübernahme): " + (f"JA ({', '.join(funding)})" if funding else "NEIN"))
    # Declared in the form (named in Finanzierung / Leistungen Dritter, or credited): the rule is met.
    declared = any(FUNDING.search(l) and (re.search(r"angerechnet|abzüglich|abzgl|abgezogen|in Abzug|verrechnet|\[\s*[xX]\s*\]\s*ja", l, re.I) or re.match(r"\s*(?:Finanzierung|Leistungen Dritter)", l, re.I))
                   for l in form.splitlines())
    if funding:
        out.append(f"- Finanzierung durch Dritte im Antrag angegeben oder angerechnet: {_yn(declared)}")
    # R21: a fee for the talk signals a Nebentätigkeit and a private trip (Dienstreisemanagement; rule-gaps-3, 3).
    fee_docs = sorted(n for n, t in docs.items() if any(
        re.search(r"\bHonorar(?!professor)\w*|Vortragshonorar|Referentenhonorar|honorari(?:um|a)\b|speaker(?:'s)? fee", l, re.I)
        and (parse_amounts(l) or re.search(r"zahlen|gezahlt|erhalten|in Höhe von|will be paid|we offer|wir bieten", l, re.I))
        and not re.search(r"ohne Honorar|kein\w* Honorar|no (?:honorarium|fee)|unentgeltlich|honorarfrei|waive", l, re.I)
        for l in t.splitlines()))
    if fee_docs:
        out.append(f"- Honorar für die Reise oder den Vortrag in den Belegen: JA ({', '.join(fee_docs)})")
    where = " ".join(filter(None, [dest, _field(form, r"Veranstaltungsort|Ort der Veranstaltung")]))
    banned = [k for k, r in _NOT_APPROVED_RE.items() if r.search(where)]
    if banned:
        out.append(f"- Reiseziel in einem Land, für das Dienstreisen bis auf Weiteres nicht genehmigt werden (Dienstreisemanagement): JA ({', '.join(banned)})")
    evening = [re.sub(r"\s{2,}", " ", l.strip())[:70] for l in form.splitlines()
               if parse_amounts(l) and EVENING_RE.search(l) and not _NOT_A_COST_ROW.search(l)]
    # A dinner booked in the registration counts when the registration total is claimed in the form.
    form_amounts = {a.value for a in parse_amounts(form)}
    for n, t in docs.items():
        if n == name:
            continue
        if not re.search(r"regist|anmeld|tagung|konferenz|conference", n + "\n".join(t.splitlines()[:5]), re.I):
            continue
        rows = [l for l in t.splitlines() if parse_amounts(l) and EVENING_RE.search(l) and not _NOT_A_COST_ROW.search(l)
                and not re.search(r"optional|nicht gebucht|not booked|declined|abgewählt|nicht gewählt|storniert|cancell?ed", l, re.I)]
        totals = {a.value for l in t.splitlines() if re.search(r"Total|Summe|Gesamt", l, re.I) for a in parse_amounts(l)}
        if rows and totals & form_amounts:
            evening += [re.sub(r"\s{2,}", " ", l.strip())[:70] + f" ({n})" for l in rows]
    if evening:
        out.append(f"- Kostenposition für Begleit- oder Abendprogramm beantragt: JA ({'; '.join(evening)})")
    # R19: positive facts for what gpt-oss looked for in vain (05-e2, 05-v1, h4).
    if re.search(r"\bFlug|\bflight", form, re.I):
        fares = sorted(n for n, t in docs.items() if n != name and re.search(r"flug|flight|preisvergleich|reisebüro|fare", n + "\n".join(t.splitlines()[:5]), re.I) and parse_amounts(t))
        if fares:
            out.append(f"- Flugangebot oder Preisvergleich beigefügt: JA ({', '.join(fares)})")
    fee = next((re.sub(r"\s{2,}", " ", l.strip())[:80] for l in form.splitlines() if parse_amounts(l)
                and re.search(r"(?:Teilnahme|Konferenz|Tagungs|Registrierungs)\w*gebühr.*(?:inkl\.?|inklusive|einschließlich).*(?:Abend|Dinner|Empfang|Rahmenprogramm|Verpflegung)", l, re.I)), None)
    if fee:
        out.append(f"- Teilnahmegebühr als Ganzes beantragt; Abendprogramm oder Empfang darin enthalten ({fee})")
    back = _field(form, RETURN_LABEL)
    both_ways = re.search(r"Hin- und Rück|Hin-/Rück|round trip|return ticket", form, re.I) is not None
    missing_return = (back is not None and not both_ways and re.fullmatch(r"[—–\-]+|offen|fehlt|n/a", back.strip(), re.I) is not None) \
        or re.search(r"^\s*(?:Summe|Gesamt|Total).*(?:unvollständig|incomplete)", form, re.I | re.M) is not None
    if missing_return:
        out.append("- Rückreise oder Kostensumme im Antrag offen: JA")
    end_before = business_end is not None and ((business and business_end < business) or (begin and business_end < begin))
    if end_before:
        out.append(f"- Ende Dienstgeschäft ({business_end.strftime('%d.%m.%Y')}) liegt vor dem Beginn: JA")
    days = re.search(r"(\d+)\s*Arbeitstage", private or "")
    # Nights claimed: cost rows with a non-zero amount, not the private ones paid by the traveller.
    nights = [int(m.group(1)) for l in form.splitlines() if any(a.value > 0 for a in parse_amounts(l)) and not re.search(r"privat|selbst", l, re.I)
              for m in re.finditer(r"(\d+)\s*(?:Nächte|Übernachtungen)", l)]
    long_private = days is not None and int(days.group(1)) > 5
    private_nights = long_private and business and business_end and nights and max(nights) > (business_end - business).days + 1
    online = ONLINE.search(" ".join(filter(None, [_field(form, r"Anlass"), _field(form, r"Grund der Reise")]))) and not NOT_ONLINE.search(form)
    notes = []
    if banned:
        notes.append(f"Reiseziel {', '.join(banned)}: Dienstreisen dorthin werden bis auf Weiteres nicht genehmigt")
    if fee_docs:
        notes.append("Honorar für den Vortrag: deutet auf eine Nebentätigkeit und eine privat veranlasste Reise; Dienstreisegenehmigung grundsätzlich nicht möglich")
    if evening:
        notes.append("Begleit- oder Abendprogramm (z. B. Conference Dinner) als Kosten beantragt: grundsätzlich nicht erstattungsfähig; der Antrag ist so nicht genehmigungsfähig")
    if applied and begin and applied >= begin:
        notes.append("Antrag erst am oder nach dem Reisebeginn gestellt")
    if funding and not declared:
        notes.append("Finanzierung durch Dritte in den Belegen, aber nicht im Antrag angegeben oder angerechnet")
    if foreign and abroad in ("nicht angekreuzt", "nein"):
        notes.append(f"Reiseziel im Ausland, aber Pflichtfeld 'Reise ins Ausland' {'nicht ausgefüllt' if abroad == 'nicht angekreuzt' else 'mit nein beantwortet'}")
    if missing_return:
        notes.append("Antrag unvollständig: Rückreise oder Kostensumme offen")
    if end_before:
        notes.append("Antrag widersprüchlich: Ende des Dienstgeschäfts liegt vor dem Beginn")
    if private_nights:
        notes.append(f"privater Aufenthalt über 5 Arbeitstage, aber {max(nights)} Übernachtungen beantragt (nur dienstlich veranlasste Kosten erstattungsfähig)")
    if online:
        notes.append("Online-Veranstaltung: Online-Konferenzen sind keine Dienstreisen")
    return out + _notes(notes)


# ------------------------------------------------------------------ expense reimbursement

# Words that show a document is addressed to the university or one of its units
# (abbreviations and OCR spellings included, rules-review and robustness audit).
UNI_WORDS = re.compile(r"Universität|Universitat|Universitaet|\bUni\b|Hochschule|\bTH\b|\bTU\b|University|Department|Faculty|"
                       r"Lehrstuhl|Fachgebiet|Fachbereich|Institut|Professur|Rechnungseingang|Dept\.?|Univ\.|\bFB\s?\d+|School of|College|Research Group|Chair of", re.IGNORECASE)
STATEMENT = re.compile(r"kontoauszug|kreditkarte|statement|umsatz|paypal|zahlungsbeleg|transaktion|visa|mastercard|amex|\bcard\b", re.IGNORECASE)
CONFIRMATION = re.compile(r"best(?:ä|ae)tigung|confirmation|lieferschein|delivery note", re.IGNORECASE)
CREDIT = re.compile(r"gutschrift|credit note|storno", re.IGNORECASE)
FORM = re.compile(r"antrag|request|formular|\bform\b", re.IGNORECASE)
RECEIPT = re.compile(r"kassenbon|\bbon\b|quittung|receipt|beleg|ticket|fahrschein|taxi", re.IGNORECASE)
CLAIM = re.compile(r"zu erstatten|Erstattungsbetrag|Erstattung beantragt|erstattet werden", re.IGNORECASE)
WEAK_TOTAL = re.compile(r"^\s*SUMME\b|\bGesamt\b(?!\s*netto)|Zu zahlen|\bTotal\b|Amount due|Grand total|Endbetrag|^\s*Betrag\b", re.IGNORECASE)
FOREIGN = re.compile(r"\bCHF\b|\bUSD\b|\bGBP\b|£|\$|\bFr\.", re.IGNORECASE)
PROFORMA = re.compile(r"^\s*Pro[- ]?forma\b|Pro[- ]?forma[- ]?Nr", re.IGNORECASE | re.MULTILINE)
EXTERNAL = re.compile(r"extern|Gäste|\bGast\b|Delegation|Gutachter|Besucher|\bguests?\b|visitors?|Kooperationspartner|Partner der Firma|Beirat\w*|Firma|Gastvortrag|Gastdozent\w*|Industriepartner|Projektpartner", re.IGNORECASE)
NEGATED_EXTERNAL = re.compile(r"(?:keine|ohne)\s+extern\w*\s+\w+", re.IGNORECASE)
MEAL_ITEMS = re.compile(r"Bewirtung|Speisen|Getränke|Essen|Menü|Kaffee|Wasser|Wein|Bier|Pizza|Salat|Suppe|Dessert|Tisch\s*\d|\d\s*Personen", re.IGNORECASE)
GUEST_LIST = re.compile(r"(?:Bewirtete\s+Person\w*(?:\(en\))?|Teilnehmer\w*(?::innen)?|Teilnehmende|Gästeliste|Gäste|Guests?|Attendees?|Anwesende|Participants?|Namen?)\s*:[ \t]*\S"
                        r"|Gast\s*\(extern|\(extern(?:al)?\)|\(Gäste?\)", re.IGNORECASE)


def _kind(name: str, text: str) -> str:
    """statement | confirmation | credit | receipt | invoice (by file name and head)."""
    head = name + "\n" + "\n".join(text.splitlines()[:8])
    if CREDIT.search("\n".join(text.splitlines()[:25])) and not STATEMENT.search(head):
        return "credit"
    for kind, pat in (("statement", STATEMENT), ("confirmation", CONFIRMATION), ("credit", CREDIT), ("form", FORM), ("receipt", RECEIPT)):
        if pat.search(head):
            return kind
    return "invoice"


def _addressed(kind: str, text: str) -> Optional[bool]:
    """JA if a university word appears anywhere in the document; NEIN for an
    invoice with none; receipts and tickets carry no addressee (unclear)."""
    if UNI_WORDS.search(text):
        return True
    return False if kind == "invoice" else None


def _totals(lines: list[str]) -> tuple[list[Decimal], bool]:
    """Gross totals of one document (strong labels first, weak ones as a fallback) and whether one is foreign."""
    for label in (GROSS_LABEL, WEAK_TOTAL):
        found, foreign = [], False
        for line in lines:
            if label.search(line) and not CLAIM.search(line):
                a = parse_amounts(line)
                if a:
                    foreign |= bool(FOREIGN.search(line)) or any(x.currency not in (None, "EUR") for x in a)
                    found.append(abs(a[-1].value))
        if found:
            return found, foreign
    return [], False


def _split_merged(docs: dict[str, str]) -> dict[str, str]:
    """One PDF may hold several documents (an invoice and its bank statement, two
    invoices). Pages of different kinds, or with different invoice numbers, become
    separate documents; their kind then comes from the page itself (R20)."""
    out = {}
    for n, t in docs.items():
        pages = [pg for pg in t.split("\f") if pg.strip()]
        kinds = [_kind("", pg) for pg in pages]
        numbers = [{m.group(1).strip() for m in INVOICE_NO.finditer(pg)} for pg in pages]
        distinct = all(numbers) and len(set().union(*numbers)) == len(pages) if pages else False
        if len(pages) > 1 and (len(set(kinds)) > 1 or distinct):
            for i, pg in enumerate(pages, 1):
                out[f"{n} (Seite {i})"] = pg
        else:
            out[n] = t
    return out


def expense_facts(docs: dict[str, str]) -> list[str]:
    docs = _split_merged(docs)
    out: list[str] = []
    credits: list[Decimal] = []
    invoices: list[Decimal] = []
    claimed: Optional[Decimal] = None
    clean = True  # every countable document gave one clean euro total per invoice number
    kinds = {n: _kind("" if "(Seite " in n else n, t) for n, t in docs.items()}
    for n, t in sorted(docs.items()):
        lines = t.splitlines()
        kind = kinds[n]
        if kind in ("invoice", "receipt", "credit") and not parse_amounts(t):
            kind = kinds[n] = "other"   # a cover letter or e-mail without amounts is no bill (R20b)
        if kind in ("invoice", "receipt", "credit"):
            proforma = PROFORMA.search(n + "\n" + t) is not None and "ersetzt" not in t.lower()
            # A written work note ("für Versuchsstand …"), not the printed "VIELEN DANK FÜR IHREN EINKAUF".
            note = next((m for l in lines[-8:] if not re.search(r"dank", l, re.I)
                         for m in [re.search(r"^\s*(?:Vermerk:?\s*|Zweck:?\s*|handschriftlich:?\s*)?(.*\bfür\b.{3,60}?)\s*$", l)] if m), None)
            if kind == "receipt" and not UNI_WORDS.search(t) and note:
                # R19: a till receipt has no addressee; its work note is what counts (refund 02, Qwen).
                out.append(f"- {n}: Kassenbon ohne Adressat; dienstlicher Vermerk auf dem Beleg: JA ('{note.group(1).strip()[:70]}')")
            else:
                out.append(f"- {n}: an Universität/Einrichtung adressiert: {_yn(_addressed(kind, t))}" + ("; Pro-forma-Rechnung: JA" if proforma else ""))
            totals, foreign = _totals(lines)
            numbers = {m.group(1).strip() for m in INVOICE_NO.finditer(t)}
            if totals and not foreign and len(totals) == max(1, len(numbers)):
                (credits if kind == "credit" else invoices).extend(totals)
            else:
                clean = False
        for line in lines:
            m = CLAIM.search(line)
            if m:
                # "zu erstatten: 121,38 € + 83,32 € ./. 69,02 € = 135,68 €": the result after "=";
                # "Erstattungsbetrag: 135,68 € (Rechnungen …)": the first amount after the label.
                rest = line[m.end():].rsplit("=", 1)[-1]
                a = [x for x in parse_amounts(rest) if x.currency in (None, "EUR")]
                if a and not FOREIGN.search(rest):
                    claimed = a[0].value
    if invoices:
        out.append(f"- Rechnungsbeträge: {', '.join(euro(v) for v in invoices)}" + (f"; Gutschriften: {', '.join(euro(v) for v in credits)}" if credits else ""))
    if claimed is not None and invoices and clean:
        expected = sum(invoices, Decimal("0")) - sum(credits, Decimal("0"))
        out.append(f"- Geforderter Betrag: {euro(claimed)}; Rechnungen minus Gutschriften = {euro(expected)}; stimmt überein: {_yn(abs(claimed - expected) <= Decimal('0.01'))}")
    elif claimed is not None:
        out.append(f"- Geforderter Betrag: {euro(claimed)}; Abgleich mit Rechnungen und Gutschriften: unklar")
    # Double claims: the same invoice number in two invoices, or the same order
    # number in two invoices with the same total (partial deliveries differ).
    inv_docs = {n: t for n, t in docs.items() if kinds[n] in ("invoice", "receipt")}
    by_invoice: dict[str, set[str]] = {}
    by_order: dict[str, set[str]] = {}
    for n, t in inv_docs.items():
        for m in INVOICE_NO.finditer(t):
            by_invoice.setdefault(re.sub(r"\s+", "", m.group(1)).upper(), set()).add(n)
        for m in re.finditer(r"(?:Bestell(?:nummer|-Nr\.?|ung Nr\.?)|Order(?: No\.?| number| #|-Nr\.?))\s*:?\s*([A-Z0-9][A-Z0-9\-/]{4,})", t, re.I):
            by_order.setdefault(m.group(1).upper(), set()).add(n)
    copies = sorted(k for k, v in by_invoice.items() if len(v) > 1)
    copy_docs = {n for k in copies for n in by_invoice[k]}
    dupes = []
    for k, v in by_order.items():
        # Different invoices for one order with the same total: billed twice (practice refund 06).
        totals = [tuple(_totals(inv_docs[n].splitlines())[0]) for n in v]
        if len(v) > 1 and len(set(totals)) < len(totals) and not v <= copy_docs:
            dupes.append(k)
    # A copy or a payment receipt of the same invoice is normal; a double claim needs the
    # claimed amount to count it twice (signed copies, "sachlich richtig").
    claimed_twice = claimed is not None and invoices and abs(claimed - (sum(invoices, Decimal("0")) - sum(credits, Decimal("0")))) <= Decimal("0.01")
    if copies and claimed_twice:
        dupes += copies
    elif copies:
        out.append(f"- Dieselbe Rechnung liegt mehrfach vor (Kopie oder Zahlungsbeleg?): {', '.join(copies)}; doppelt beantragt: unklar")
    out.append("- Dieselbe Rechnung oder Bestellung (gleicher Betrag) in mehreren Belegen: " + (f"JA ({', '.join(sorted(set(dupes)))})" if dupes else "NEIN"))
    notes = []
    purpose_note = any(re.search(r"Verwendungszweck|Zweck\s*:|Vermerk|handschriftlich|\bfür (?:das|den|die) (?:Labor|Projekt|Fachgebiet|Lehrstuhl|Institut|Versuch|Seminar|Workshop)", t, re.I)
                       for n, t in docs.items() if kinds[n] != "statement")
    if any("adressiert: NEIN" in l for l in out) and not purpose_note:
        notes.append("Rechnung an eine Privatperson, nicht an die Universität adressiert (ohne dienstlichen Vermerk ein Ablehnungsgrund)")
    if any("stimmt überein: NEIN" in l for l in out):
        notes.append("geforderter Betrag weicht von Rechnungen minus Gutschriften ab")
    if dupes:
        notes.append("dieselbe Rechnung oder Bestellung in mehreren Belegen: doppelte Abrechnung")
    if any("Pro-forma-Rechnung: JA" in l for l in out):
        notes.append("Pro-forma-Rechnung ist kein Zahlungsbeleg")
    usd = any(a.currency == "USD" for t in docs.values() for a in parse_amounts(t))
    if usd:
        has_proof = any(kinds[n] == "statement" for n in docs)
        out.append(f"- Beträge in Fremdwährung (USD): JA; Zahlungsnachweis (Kontoauszug, Kreditkarte, PayPal) vorhanden: {_yn(has_proof)}")
        if not has_proof:
            notes.append("Fremdwährung ohne Zahlungsnachweis")
    receipts = {n: t for n, t in docs.items() if kinds[n] != "statement"}
    internal = sorted(n for n, t in receipts.items()
                      if HOSPITALITY_RE.search(t) and INTERNAL_RE.search(t) and not EXTERNAL.search(NEGATED_EXTERNAL.sub("", t)))
    if internal:
        out.append(f"- Bewirtung oder Verpflegung nur für Beschäftigte (ohne externe Gäste) laut Beleg: JA ({', '.join(internal)})")
        notes.append("Bewirtung ohne externe Personen (interne Besprechung, Feier, Teeküche): nach der Bewirtungskostenrichtlinie nicht erstattungsfähig")
    meals = sorted(n for n, t in receipts.items() if MEAL_RE.search(n + " " + t[:600]) and MEAL_ITEMS.search(t))
    # R21: an Arbeitsessen is hospitality "mit überwiegend Universitätsangehörigen" (Bewirtungskostenrichtlinie).
    # Count the marked participant rows; note only on a strict staff majority with at least one guest.
    guests = staff = 0
    for t in docs.values():
        if not re.search(r"Teilnehm|Bewirtete|Gäste|Attendees|Anwesende", t, re.I):
            continue
        for l in t.splitlines():
            if not re.match(r"\s*\d{1,2}[.)]?\s+\S", l):
                continue
            g = re.search(r"\bGast\b|\bGäste\b|\(extern|\bextern\b|\bguest\b|\bexternal\b", l, re.I)
            u = re.search(r"Universitätsbedienstete|Universitätsangehörige|Bedienstete|Beschäftigte|Mitarbeiter\w*|\(intern|\bstaff\b", l, re.I)
            if g and not u:
                guests += 1
            elif u and not g:
                staff += 1
    if meals and (guests or staff):
        out.append(f"- Teilnehmende laut Liste: {staff} Universitätsangehörige, {guests} Gäste")
    if meals and not internal and staff > guests >= 1:
        notes.append(f"Bewirtung mit überwiegend Universitätsangehörigen ({staff} gegenüber {guests} Gästen): Arbeitsessen, nach der Bewirtungskostenrichtlinie nicht erstattungsfähig")
    if meals and not internal:
        listed = any(GUEST_LIST.search(t) for t in docs.values())
        out.append(f"- Bewirtung im Restaurant ({', '.join(meals)}); Teilnehmerliste mit Kennzeichnung der Gäste vorhanden: {_yn(listed)}")
        if not listed:
            notes.append("Bewirtungsbeleg ohne Anlass und Liste der bewirteten Personen (von der Bewirtungskostenrichtlinie verlangt)")
    return out + _notes(notes)


# Cases of another university are decided on the documents alone (dataset
# README: "another state's travel law, which is not in the corpora"). Notes that
# rest on Kassel's own pages are dropped there; document checks stay (R17).
OTHER_UNIVERSITY = re.compile(r"Sallstedt", re.IGNORECASE)
# The applicant side names the home university; a supplier in Kassel does not (R21).
HOME_UNIVERSITY = re.compile(r"Universit(?:ä|ae|a)t (?:Kassel|Wernstadt)|@uni-(?:kassel|wernstadt)\.de|Uni (?:Kassel|Wernstadt)", re.IGNORECASE)
KASSEL_ONLY_NOTES = ("Rahmenvertrag", "Artikel aus einer Rahmenvertrags", "Reiseziel ", "Begleit- oder Abendprogramm",
                     "Bewirtung", "Online-Veranstaltung", "privater Aufenthalt über 5", "Auftragswert netto ≥ 1.000 €",
                     "Arbeitsessen")
KASSEL_ONLY_FACTS = ("- Unter 1.000 € netto", "- Ab 1.000 € netto", "- Auftragswert netto", "- Nur Bruttobetrag genannt")
OWN_LIMIT = re.compile(r"[^.\n]{0,80}(?:ab|bis|über|unter|bis zu|höchstens|maximal)\s+\d[\d.]*(?:,\d{2})?\s*(?:€|EUR|Euro)[^.\n]{0,80}", re.IGNORECASE)
LIMIT_TOPIC = re.compile(r"Angebot|Vergleichsangebot|Direktauftrag|Wertgrenze|je Nacht|Übernachtung|pro Person|je Person|Kilometer", re.IGNORECASE)


def _drop_kassel_notes(lines: list[str], text: str = "") -> list[str]:
    """Another university's case: drop the notes and threshold lines that rest on Kassel's
    pages, keep the document checks, and show the limits its own documents state."""
    kept = [l for l in lines if not (l.startswith("  * ") and l[4:].startswith(KASSEL_ONLY_NOTES)) and not l.startswith(KASSEL_ONLY_FACTS)]
    if not any(l.startswith("  * ") for l in kept):
        kept = [l for l in kept if not l.startswith("- PRÜFHINWEISE")] + _notes([])
    own = sorted({re.sub(r"\s+", " ", m.group(0)).strip()[:160] for m in OWN_LIMIT.finditer(text) if LIMIT_TOPIC.search(m.group(0))})
    at = next(i for i, l in enumerate(kept) if l.startswith("- PRÜFHINWEISE"))
    extra = [f"- Grenze laut Unterlagen der Hochschule: '{limit}'" for limit in own[:3]]
    extra.append("- Hochschule laut Belegen: TH Sallstedt; entschieden wird nur anhand der Belege und ihrer eigenen Grenzen")
    return kept[:at] + extra + kept[at:]


def compute_facts(case_type: str, docs: dict[str, str]) -> list[str]:
    """Plain-German fact lines for the prompt, headed by HEADER."""
    fn = {"procurement": procurement_facts, "business_trip": trip_facts, "expense_reimbursement": expense_facts}.get(case_type)
    if fn is None:
        return []
    try:
        lines = fn(docs)
        text = "\n".join(docs.values())
        if OTHER_UNIVERSITY.search(text) and not HOME_UNIVERSITY.search(text):
            lines = _drop_kassel_notes(lines, text)
    except Exception as error:  # a fact helper must never cost the case
        lines = [f"- Fakten konnten nicht berechnet werden ({type(error).__name__})"]
    return [HEADER] + lines
