"""Facts computed by code from the case documents (round R11).

The model is weak at arithmetic and comparisons (Qwen: "2.670 € unter
1.000 €"), so code reads the labelled fields, does the sums and comparisons,
and states the result as plain German lines. A fact that cannot be read for
certain is reported as "unklar", never guessed. Every rule used here is quoted
in the development notes (not included); nothing is specific to one practice case.
"""
from __future__ import annotations

import re
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
]
# Whole word, not part of a compound ("PC-Schnittstelle", "Lab Notebook" are no framework items).
_FRAMEWORK_RE = re.compile(r"(?<![\wÄÖÜäöü-])(" + "|".join(FRAMEWORK_WORDS) + r")(?![\wÄÖÜäöü-])", re.IGNORECASE)
_NOT_FRAMEWORK_BEFORE = re.compile(r"(?:Lab|Labor|inkl\.?|mit|für|Software für)\s*$", re.IGNORECASE)


def framework_items(text: str) -> list[str]:
    """Framework product words that name the ordered item itself: only in
    item lines (a line with an amount), within the first words of the item
    text, and not after 'Lab', 'inkl.', 'mit', 'für' (rules-review.md, 4)."""
    hits = []
    for line in text.splitlines():
        if not parse_amounts(line):
            continue
        desc = re.split(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}", line)[0]
        desc = re.sub(r"^\s*(?:Pos\.?\s*)?\d+\s*(?:[x×]\s*)?", "", desc)
        head = desc.strip()[:45]
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
    "Israel": r"Israel|Tel Aviv|Jerusalem|Haifa",
    "Palästinensische Gebiete": r"Palästin\w*|Palestin\w*|Gaza|Westjordanland|West Bank|Ramallah",
    "Libanon": r"Libanon|Lebanon|Beirut",
}
_NOT_APPROVED_RE = {k: re.compile(rf"(?<![\wÄÖÜäöü])(?:{v})(?![\wÄÖÜäöü])", re.IGNORECASE) for k, v in NOT_APPROVED.items()}

# Cost rows for evening and accompanying programmes ("Kosten für Begleit- und
# Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht erstattungsfähig").
# A meal already in the conference fee ("inkl.") or a per-diem cut is no such row.
EVENING_RE = re.compile(r"Conference[- ]Dinner|Konferenz[- ]?(?:dinner|abendessen)|Gala[- ]?(?:dinner|abend|diner)|Festessen|Bankett|Banquet|Abendprogramm|Begleitprogramm|Rahmenprogramm|Social (?:event|programme|program)|Stadtführung|City tour|Ausflug|Excursion|Exkursion", re.IGNORECASE)
_NOT_A_COST_ROW = re.compile(r"inkl\.?|inklusive|enthalten|included|Tagegeld|Verpflegung|Kürzung|nicht gebucht", re.IGNORECASE)

# Hospitality for staff only ("Nicht erstattungsfähige Aufwendungen sind:
# Bewirtungen, an denen keine externen Personen teilgenommen haben",
# Bewirtungskostenrichtlinie). Courtesies are allowed only for "Gästen der Universität".
HOSPITALITY_RE = re.compile(r"Kaffee|Coffee|Tee\b|Kuchen|Gebäck|Kekse|Brötchen|Snacks?|Getränke|Catering|Bewirtung|Pizza|Buffet|Imbiss|Frühstück|Mittagessen|Abendessen", re.IGNORECASE)
INTERNAL_RE = re.compile(r"(?:keine|ohne)\s+externe(?:n)?\s+(?:Gäste|Personen|Teilnehmer\w*)|nur\s+(?:Beschäftigte|Mitarbeitende|Mitarbeiter\w*|Universitätsangehörige)|interne[nrs]?\s+(?:Team)?(?:besprechung|sitzung|meeting|runde|klausur)|Teambesprechung|Teamsitzung|Teammeeting|Weihnachtsfeier|Betriebsfeier|Abschiedsfeier|Geburtstagsfeier|Betriebsausflug|Teamevent|(?:Mitarbeiter|Team)frühstück|Arbeitsessen|Teeküche|Kaffeeküche|Büroküche|Sozialraum|Kaffeekasse|Kaffeevorrat|für die Beschäftigten|für das Team", re.IGNORECASE)

# Restaurant hospitality needs "Anlass, Teilnehmerliste" (Bewirtungskostenrichtlinie):
# a meal receipt with no document naming the persons entertained.
MEAL_RE = re.compile(r"Bewirtungsbeleg|Gasthaus|Gaststätte|Restaurant|Ristorante|Trattoria|Brauhaus|Wirtshaus|Bistro", re.IGNORECASE)
GUEST_LIST_RE = re.compile(r"Teilnehm\w*|bewirtete[nr]? Person|Gast \(|\(extern\)|Gäste\s*:", re.IGNORECASE)

NET_LABEL = re.compile(r"Summe\s*\(?netto\)?|Subtotal\s*\(net\)|Warenwert netto|Nettobetrag|Gesamtbetrag netto|Summe .*netto", re.IGNORECASE)
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


def _checkbox(text: str, label: str) -> Optional[str]:
    line = _field(text, label)
    if not line:
        return None
    m = re.search(r"\[\s*[xX]\s*\]\s*(\w+)", line)
    return m.group(1).lower() if m else "nicht angekreuzt"


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

def _is_offer(name: str, text: str) -> bool:
    if re.search(r"angebot|offer|quote|kostenvoranschlag", name, re.IGNORECASE):
        return True
    head = "\n".join(text.splitlines()[:40])
    return re.search(r"^\s*(Angebot|Kostenvoranschlag|Quotation)\s*$", head, re.IGNORECASE | re.MULTILINE) is not None


def _is_request(name: str) -> bool:
    return re.search(r"antrag|email|e-mail|bestellung|request", name, re.IGNORECASE) is not None


def procurement_facts(docs: dict[str, str]) -> list[str]:
    out: list[str] = []
    offers = {n: t for n, t in docs.items() if _is_offer(n, t)}
    requests = {n: t for n, t in docs.items() if _is_request(n) and n not in offers}
    offer_nets = {}
    for n, t in offers.items():
        a = _last_amount_on(t.splitlines(), NET_LABEL)
        offer_nets[n] = a.value if a else None
    out.append(f"- Anzahl vorgelegter Angebote: {len(offers)}" + (f" ({', '.join(sorted(offers))})" if offers else ""))
    for n, v in sorted(offer_nets.items()):
        out.append(f"- {n}: Summe netto {euro(v) if v is not None else 'unklar'}")

    req_net = req_gross = None
    for t in requests.values():
        lines = t.splitlines()
        a = _near([l for l in lines if re.search(r"summe|gesamt|zusammen", l, re.I)], "netto")
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
    if req_net is not None and known:
        out.append(f"- Antragsbetrag netto stimmt mit einem Angebot überein: {_yn(any(v == req_net for v in known))}")
        if any(v == req_net for v in known) and len(known) > 1:
            out.append(f"- Gewähltes Angebot ist das günstigste: {_yn(req_net <= min(known))} (günstigstes Angebot: {euro(min(known))})")

    for t in requests.values():
        box = _checkbox(t, r"Rahmenvertragsprodukt")
        if box:
            out.append(f"- Formularfeld 'Rahmenvertragsprodukt': {box}")
            break
    hits = sorted({h for t in docs.values() for h in framework_items(t)}, key=str.lower)
    out.append("- Artikel aus einer Rahmenvertrags-Produktgruppe (PCs/Notebooks/Monitore, Bürostühle, Büromöbel, Kopiergeräte, Büropapier, Büromaterial, Microsoft): "
               + (f"JA ({', '.join(hits)})" if hits else "NEIN"))
    framework_route = False
    supplier = next((v for t in docs.values() for v in [_field(t, r"Vorgesehener Lieferant|Lieferant|Supplier")] if v), None)
    partner_line = next((l.strip() for t in docs.values() for l in t.splitlines() if re.search(r"Rahmenvertragspartner|Katalog Rahmenvertrag", l)), None)
    if supplier:
        out.append(f"- Vorgesehener Lieferant: {supplier[:120]}")
    if partner_line:
        out.append(f"- Genannter Rahmenvertragspartner: {partner_line[:160]}")
        name = re.sub(r".*Rahmenvertragspartner\)?\s*:?\s*", "", partner_line).strip()
        first = re.split(r"[\s,]+", name)[0].lower() if name else ""
        if supplier and first and len(first) > 2:
            same = first in supplier.lower()
            out.append(f"- Lieferant ist der Rahmenvertragspartner: {_yn(same)}")
            framework_route = same
    # "Beschaffung - INTERN": three offers from 1.000 EUR net, except when
    # ordering from the framework-contract partner.
    notes = []
    if framework_route:
        out.append("- Bestellung beim Rahmenvertragspartner: JA; dann sind keine Vergleichsangebote nötig")
    elif basis is not None and basis < THRESHOLD:
        out.append("- Unter 1.000 € netto: Direktvergabe mit einem Angebot zulässig; Vergleichsangebote sind nicht nötig")
    elif basis is not None and basis >= THRESHOLD:
        out.append(f"- Ab 1.000 € netto sind drei Vergleichsangebote nötig; vorgelegt: {len(offers)}")
        if len(offers) < 3:
            notes.append(f"Auftragswert netto ≥ 1.000 €, aber nur {len(offers)} Angebot(e) vorgelegt und keine Bestellung beim Rahmenvertragspartner")
    if hits and supplier and partner_line and not framework_route:
        notes.append("Rahmenvertragsprodukt, aber der Lieferant ist nicht der Rahmenvertragspartner")
    elif hits and not partner_line and not framework_route:
        notes.append(f"Artikel aus einer Rahmenvertrags-Produktgruppe ({', '.join(hits)}); eine Bestellung beim Rahmenvertragspartner ist nicht erkennbar (solche Produkte sind ausschließlich dort zu bestellen)")
    if req_net is not None and known and not any(v == req_net for v in known):
        notes.append("Antragsbetrag netto passt zu keinem Angebot")
    if req_net is not None and known and any(v == req_net for v in known) and len(known) > 1 and req_net > min(known):
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


def trip_facts(docs: dict[str, str]) -> list[str]:
    out: list[str] = []
    form = next((t for n, t in docs.items() if re.search(r"antrag", n, re.I)), None)
    if form is None:
        return ["- Antragsformular: nicht gefunden"]
    applied = _first_date(_field(form, r"Datum der Antragstellung|Antragsdatum"))
    start = _first_date(_field(form, r"Start|Beginn der Reise|Reisebeginn|Abreise"))
    business = _first_date(_field(form, r"Beginn Dienstgeschäft"))
    begin = start or business
    out.append(f"- Antrag gestellt am: {applied.strftime('%d.%m.%Y') if applied else 'unklar'}; Reisebeginn: {begin.strftime('%d.%m.%Y') if begin else 'unklar'}")
    if applied and begin:
        out.append(f"- Antrag vor Reisebeginn gestellt: {_yn(applied < begin)}")
    dest = _field(form, r"Reiseziel")
    abroad = _checkbox(form, r"Reise ins Ausland")
    out.append(f"- Reiseziel: {dest or 'unklar'}; Formularfeld 'Reise ins Ausland': {abroad or 'unklar'}")
    # No A1 fact line (R12d): the sentence "kein Ablehnungsgrund" made Qwen accept
    # whole trips (R12c, trips 03 and 05, reproduced). The rule card states A1.
    a1 = _field(form, r"A1-Bescheinigung")
    if a1:
        out.append(f"- Formularfeld 'A1-Bescheinigung': {a1[:100]}")
    private = _field(form, r"priv\. Aufenthalt|privater Aufenthalt")
    if private:
        out.append(f"- Privater Aufenthalt laut Antrag: {private[:120]}")
    funding = sorted(n for n, t in docs.items() if re.search(r"\b(?:Reise)?stipendium\b|Stipendienzusage|\bscholarship\b|travel grant|Reisekostenzuschuss|Reisezuschuss", t, re.I))
    out.append("- Hinweis auf Finanzierung durch Dritte (Stipendium, Zuschuss): " + (f"JA ({', '.join(funding)})" if funding else "NEIN"))
    where = " ".join(filter(None, [dest, _field(form, r"Anlass|Zweck"), _field(form, r"Ort|Veranstaltungsort")]))
    banned = [k for k, r in _NOT_APPROVED_RE.items() if r.search(where)]
    if banned:
        out.append(f"- Reiseziel in einem Land, für das Dienstreisen bis auf Weiteres nicht genehmigt werden (Dienstreisemanagement): JA ({', '.join(banned)})")
    evening = [re.sub(r"\s{2,}", " ", l.strip())[:70] for l in form.splitlines()
               if parse_amounts(l) and EVENING_RE.search(l) and not _NOT_A_COST_ROW.search(l)]
    if evening:
        out.append(f"- Kostenposition für Begleit- oder Abendprogramm im Antrag: JA ({'; '.join(evening)})")
    notes = []
    if banned:
        notes.append(f"Reiseziel {', '.join(banned)}: Dienstreisen dorthin werden bis auf Weiteres nicht genehmigt")
    if evening:
        notes.append("Begleit- oder Abendprogramm (z. B. Conference Dinner) als Kosten beantragt: grundsätzlich nicht erstattungsfähig")
    if applied and begin and applied >= begin:
        notes.append("Antrag erst am oder nach dem Reisebeginn gestellt")
    if funding:
        notes.append("Finanzierung durch Dritte erwähnt: prüfen, ob sie im Antrag angegeben und angerechnet ist")
    return out + _notes(notes)


# ------------------------------------------------------------------ expense reimbursement

UNI_WORDS = re.compile(r"Universität|Hochschule|University|Lehrstuhl|Fachgebiet|Fachbereich|Institut|Rechnungseingang", re.IGNORECASE)


def expense_facts(docs: dict[str, str]) -> list[str]:
    out: list[str] = []
    credits: list[Decimal] = []
    invoices: list[Decimal] = []
    claimed: Optional[Decimal] = None
    unclear_totals = False
    for n, t in sorted(docs.items()):
        lines = t.splitlines()
        is_credit = re.search(r"gutschrift|credit note|storno", n + " " + "\n".join(lines[:25]), re.I) is not None
        is_statement = re.search(r"kontoauszug|kreditkarte|statement|umsatzanzeige", n + " " + "\n".join(lines[:15]), re.I) is not None
        proforma = re.search(r"pro[- ]?forma", t, re.I) is not None
        head = "\n".join(lines[:18])
        if not is_statement:
            addressed = True if UNI_WORDS.search(head) else (None if re.search(r"kasse|bon|beleg", n + head, re.I) else False)
            out.append(f"- {n}: an Universität/Einrichtung adressiert: {_yn(addressed)}" + ("; Pro-forma-Rechnung: JA" if proforma else ""))
            totals = []
            for line in lines:
                if GROSS_LABEL.search(line):
                    a = [x for x in parse_amounts(line) if x.currency in (None, "EUR")]
                    if a:
                        totals.append(abs(a[-1].value))
            numbers = {m.group(1).strip() for m in INVOICE_NO.finditer(t)}
            if totals and len(totals) == max(1, len(numbers)):
                (credits if is_credit else invoices).extend(totals)
            elif totals:
                unclear_totals = True
        for line in lines:
            if re.search(r"zu erstatten|Erstattungsbetrag|Erstattung beantragt|erstattet werden", line, re.I):
                a = [x for x in parse_amounts(line) if x.currency in (None, "EUR")]
                if a:
                    claimed = a[-1].value
    if invoices:
        expected = sum(invoices, Decimal("0")) - sum(credits, Decimal("0"))
        out.append(f"- Rechnungsbeträge: {', '.join(euro(v) for v in invoices)}" + (f"; Gutschriften: {', '.join(euro(v) for v in credits)}" if credits else ""))
        if claimed is not None and unclear_totals:
            out.append(f"- Geforderter Betrag: {euro(claimed)}; Abgleich mit Rechnungen und Gutschriften: unklar")
        elif claimed is not None:
            out.append(f"- Geforderter Betrag: {euro(claimed)}; Rechnungen minus Gutschriften = {euro(expected)}; stimmt überein: {_yn(abs(claimed - expected) <= Decimal('0.01'))}")
    orders: dict[str, set[str]] = {}
    for n, t in docs.items():
        if re.search(r"kontoauszug|kreditkarte|statement|umsatzanzeige|bestätigung|confirmation", n, re.I):
            continue
        for m in re.finditer(r"(?:Bestell(?:nummer|-Nr\.?|ung Nr\.?)|Order(?: No\.?| number| #|-Nr\.?))\s*:?\s*([A-Z0-9][A-Z0-9\-/]{4,})", t, re.I):
            orders.setdefault(m.group(1).upper(), set()).add(n)
    dupes = sorted(k for k, v in orders.items() if len(v) > 1)
    out.append("- Dieselbe Bestellnummer in mehreren Belegen: " + (f"JA ({', '.join(dupes)})" if dupes else "NEIN"))
    notes = []
    purpose_note = any(re.search(r"Verwendungszweck|Zweck\s*:|\bfür (?:das|den|die) (?:Labor|Projekt|Fachgebiet|Lehrstuhl|Institut|Versuch|Seminar|Workshop)", t, re.I) for t in docs.values())
    if any(l.endswith("adressiert: NEIN") or "adressiert: NEIN;" in l for l in out) and not purpose_note:
        notes.append("Rechnung nicht an die Universität adressiert (ohne dienstlichen Vermerk ein Ablehnungsgrund)")
    if any("stimmt überein: NEIN" in l for l in out):
        notes.append("geforderter Betrag weicht von Rechnungen minus Gutschriften ab")
    if dupes:
        notes.append("dieselbe Bestellung in mehreren Belegen: doppelte Abrechnung")
    internal = sorted(n for n, t in docs.items() if HOSPITALITY_RE.search(t) and INTERNAL_RE.search(t))
    if internal:
        out.append(f"- Bewirtung oder Verpflegung nur für Beschäftigte (ohne externe Gäste) laut Beleg: JA ({', '.join(internal)})")
        notes.append("Bewirtung ohne externe Personen (interne Besprechung, Feier, Teeküche): nach der Bewirtungskostenrichtlinie nicht erstattungsfähig")
    meals = sorted(n for n, t in docs.items() if MEAL_RE.search(n + " " + t[:600]))
    if meals and not internal:
        listed = any(GUEST_LIST_RE.search(t) for t in docs.values())
        out.append(f"- Bewirtung im Restaurant ({', '.join(meals)}); Teilnehmerliste mit Kennzeichnung der Gäste vorhanden: {_yn(listed)}")
        if not listed:
            notes.append("Bewirtungsbeleg ohne Anlass und Liste der bewirteten Personen (von der Bewirtungskostenrichtlinie verlangt)")
    if any("Pro-forma-Rechnung: JA" in l for l in out):
        notes.append("Pro-forma-Rechnung ist kein Zahlungsbeleg")
    usd = any(a.currency == "USD" for t in docs.values() for a in parse_amounts(t))
    if usd:
        has_proof = any(re.search(r"kontoauszug|kreditkarte|statement", n + t[:400], re.I) for n, t in docs.items())
        out.append(f"- Beträge in Fremdwährung (USD): JA; Zahlungsnachweis (Kontoauszug/Kreditkarte) vorhanden: {_yn(has_proof)}")
        if not has_proof:
            notes.append("Fremdwährung ohne Zahlungsnachweis")
    return out + _notes(notes)


def compute_facts(case_type: str, docs: dict[str, str]) -> list[str]:
    """Plain-German fact lines for the prompt, headed by HEADER."""
    fn = {"procurement": procurement_facts, "business_trip": trip_facts, "expense_reimbursement": expense_facts}.get(case_type)
    if fn is None:
        return []
    try:
        lines = fn(docs)
    except Exception as error:  # a fact helper must never cost the case
        lines = [f"- Fakten konnten nicht berechnet werden ({type(error).__name__})"]
    return [HEADER] + lines
