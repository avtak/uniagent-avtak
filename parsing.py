"""Read amounts and dates from the case documents.

Built to the specification in the development notes (not included) (c),
which was measured on all 61 practice PDFs: German, English and whole-number
amounts, signs, currencies before or after the number, and eight date
formats including ranges. Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

# Rule 1: fold the special spaces and dashes that models (and some PDFs) emit.
_FOLD = str.maketrans({" ": " ", " ": " ", " ": " ", "‑": "-", "­": "", "−": "-"})


def normalise(text: str) -> str:
    return text.translate(_FOLD)


_SP = r"[ ]"
_MINUS = r"[-−]"
_CUR = r"(?:€|EUR|Euro|USD|US\$|\$)"
_DE = r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}"
_EN = r"\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2}"
_GRP = r"\d{1,3}(?:[ '’]\d{3})+[.,]\d{2}"
AMOUNT_RE = re.compile(
    rf"(?<![\w.,])(?P<sign>{_MINUS})?(?:(?P<c1>{_CUR}){_SP}?)?"
    rf"(?P<num>{_GRP}|{_DE}|{_EN})(?!\d)(?:{_SP}?(?P<c2>{_CUR})(?![A-Za-z]))?(?!\s?%)"
)
INT_RE = re.compile(
    rf"(?<![\w.,])(?P<num>\d{{1,3}}(?:[.,]\d{{3}})+|\d+){_SP}?(?P<c>EUR|Euro|€|USD)(?![A-Za-z])"
)
_ISO_CURRENCY = {"€": "EUR", "EUR": "EUR", "Euro": "EUR", "USD": "USD", "US$": "USD", "$": "USD"}


@dataclass(frozen=True)
class Amount:
    value: Decimal
    currency: Optional[str]
    raw: str
    line: int

    def label(self) -> str:
        """Short form for the prompt: the text as written, then the plain number."""
        plain = f"{self.value:.2f}" + (f" {self.currency}" if self.currency else "")
        return f"{self.raw.strip()} [{plain}]"


def number_value(text: str) -> Decimal:
    """'2.667,00' -> 2667.00, '2,667.00' -> 2667.00, '94,40' -> 94.40,
    '1.200' -> 1200 (rule 2: the last separator is the decimal one only when
    exactly two digits follow it)."""
    s = normalise(text).strip().replace(" ", "").replace("'", "").replace("’", "")
    s = re.sub(r"^(?:€|EUR|Euro|USD|US\$|\$)", "", s)
    s = re.sub(r"(?:€|EUR|Euro|USD|US\$|\$)$", "", s)
    negative = s.startswith(("-", "−"))
    s = s.lstrip("-−+")
    last = max(s.rfind("."), s.rfind(","))
    if last >= 0 and len(s) - last - 1 == 2:
        whole, decimals = s[:last], s[last + 1:]
        s = re.sub(r"[.,]", "", whole) + "." + decimals
    else:
        s = re.sub(r"[.,]", "", s)
    try:
        value = Decimal(s)
    except InvalidOperation as error:
        raise ValueError(f"Not an amount: {text!r}") from error
    return -value if negative else value


def parse_amounts(text: str) -> list[Amount]:
    """Every monetary amount in `text`, in reading order, not deduplicated."""
    found: list[Amount] = []
    for line_no, raw_line in enumerate(normalise(text).splitlines(), start=1):
        taken: list[tuple[int, int]] = []
        for m in AMOUNT_RE.finditer(raw_line):
            num = m.group("num")
            currency = m.group("c1") or m.group("c2")
            is_period_decimal = re.fullmatch(_EN, num) is not None and "," not in num[-3:]
            if is_period_decimal and not currency:
                continue  # rule 3: "B 0.14", "E 3.12", "10.09" are not amounts
            before = raw_line[max(0, m.start() - 6):m.start()]
            if "Kurs" in before:
                continue  # rule 5: exchange rates
            value = number_value(num)
            if m.group("sign"):
                value = -value
            found.append(Amount(value, _ISO_CURRENCY.get(currency or ""), m.group(0), line_no))
            taken.append(m.span())
        for m in INT_RE.finditer(raw_line):
            if any(a <= m.start() < b for a, b in taken):
                continue
            value = number_value(m.group("num"))
            found.append(Amount(value, _ISO_CURRENCY.get(m.group("c")), m.group(0), line_no))
    return found


# ---------------------------------------------------------------- dates

_MONTHS = {
    "januar": 1, "jan": 1, "january": 1, "februar": 2, "feb": 2, "february": 2,
    "märz": 3, "maerz": 3, "mär": 3, "mrz": 3, "mar": 3, "march": 3, "april": 4, "apr": 4,
    "mai": 5, "may": 5, "juni": 6, "jun": 6, "june": 6, "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10,
    "oct": 10, "october": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12,
    "dec": 12, "december": 12,
}
_MONTH_WORD = r"[A-Za-zÄÖÜäöü]{3,9}"
_DASH = r"\s*[–-]\s*"


@dataclass(frozen=True)
class FoundDate:
    value: date
    raw: str
    line: int


def _month(word: str) -> Optional[int]:
    return _MONTHS.get(word.casefold().rstrip("."))


def _make(y: int, m: Optional[int], d: int) -> Optional[date]:
    if m is None:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


# Order matters: ranges first, then single dates; spans already used are skipped.
_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.(\d{{1,2}})\.{_DASH}(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})(?!\d)"), "r_dmdmY"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.{_DASH}(\d{{1,2}})\.\s*({_MONTH_WORD})\s+(\d{{4}})"), "r_ddMY"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.{_DASH}(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})(?!\d)"), "r_dd_mY"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_WORD}){_DASH}(\d{{1,2}})\s+({_MONTH_WORD})\s+(\d{{4}})"), "r_dMdMY"),
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_DASH}(\d{{1,2}})\s+({_MONTH_WORD})\s+(\d{{4}})"), "r_ddMY_en"),
    (re.compile(r"(?<![\d.\-/])(\d{4})-(\d{2})-(\d{2})(?!\d)"), "iso"),
    (re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"), "dmY"),
    (re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{2})(?![\d.])"), "dmy"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})-({_MONTH_WORD})-(\d{{4}})(?!\d)"), "d-MON-Y"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s+({_MONTH_WORD})\.?\s+(\d{{4}})(?!\d)"), "dMY"),
]


def _dates_from(kind: str, g: tuple[str, ...]) -> list[Optional[date]]:
    if kind == "r_dmdmY":
        y = int(g[4]); return [_make(y, int(g[1]), int(g[0])), _make(y, int(g[3]), int(g[2]))]
    if kind == "r_dd_mY":
        y = int(g[3]); m = int(g[2]); return [_make(y, m, int(g[0])), _make(y, m, int(g[1]))]
    if kind in ("r_ddMY", "r_ddMY_en"):
        m = _month(g[2]); y = int(g[3]); return [_make(y, m, int(g[0])), _make(y, m, int(g[1]))]
    if kind == "r_dMdMY":
        y = int(g[4]); return [_make(y, _month(g[1]), int(g[0])), _make(y, _month(g[3]), int(g[2]))]
    if kind == "iso":
        return [_make(int(g[0]), int(g[1]), int(g[2]))]
    if kind == "dmY":
        return [_make(int(g[2]), int(g[1]), int(g[0]))]
    if kind == "dmy":
        yy = int(g[2]); return [_make(2000 + yy if yy < 70 else 1900 + yy, int(g[1]), int(g[0]))]
    if kind in ("d-MON-Y", "dMY"):
        return [_make(int(g[2]), _month(g[1]), int(g[0]))]
    return []


def parse_dates(text: str) -> list[FoundDate]:
    """Every calendar date in `text`; a range yields its start and its end."""
    out: list[FoundDate] = []
    for line_no, line in enumerate(normalise(text).splitlines(), start=1):
        taken: list[tuple[int, int]] = []
        for pattern, kind in _DATE_PATTERNS:
            for m in pattern.finditer(line):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue
                values = [d for d in _dates_from(kind, m.groups()) if d is not None]
                if not values:
                    continue
                taken.append(m.span())
                out.extend(FoundDate(v, m.group(0), line_no) for v in values)
    return out


def parse_date(value: str) -> date:
    """One date from a short string, in any supported format."""
    found = parse_dates(value)
    if not found:
        raise ValueError(f"Unsupported date {value!r}.")
    return found[0].value
