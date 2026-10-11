"""Run-time rule search over the case folder's corpora (R13, decision 13 and 20).

Each dataset folder holds `retrieval-corpora/<name>/documents.jsonl.gz` (the
university's public pages, Hessian law, maybe an intranet crawl on the hidden
test). The rule cards cover the rules we know; this search reaches rules we have
not seen. BM25 over paragraphs of the administration's pages only (URL paths
/intern/, /hochschulverwaltung/, SAP service pages, or any page of a corpus whose
name says intranet). The query is the case's own words that also occur in the
index, ranked by rarity. Plain Python, no extra package; built once per run.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Optional

ADMIN_PATH = re.compile(r"uni-kassel\.de/(?:intern/|hochschulverwaltung/|its/it-dienste-software/sap-)", re.IGNORECASE)
WORD = re.compile(r"[a-zäöüß]{4,}", re.IGNORECASE)
STOP = set("""
aber alle allem allen aller alles also auch auf aus bei beim bitte damit dann dass dein deine dem den denen der des
dessen die dies diese diesem diesen dieser dieses doch dort durch eine einem einen einer eines euch fuer für gegen
haben hatte hier ihre ihrem ihren ihrer ihres immer jede jedem jeden jeder jedes kann keine können mehr mein mich mit
nach nicht noch nur oder ohne sehr sein seine sich sind soll sowie über unter uns unser vom von vor wann warum was
weil wenn werden wie wird wir wurde zum zur zwischen sowie sofern bzw werden worden kann können müssen muss sollen
universität kassel intern uni www html seite seiten
""".split())
K1, B = 1.2, 0.75
MAX_PARAGRAPH = 900


def _tokens(text: str) -> list[str]:
    return [w for w in (m.group(0).lower() for m in WORD.finditer(text)) if w not in STOP]


def _paragraphs(title: str, text: str) -> list[str]:
    """Blocks of about 300 to 900 characters, each prefixed with the page title."""
    out, cur = [], ""
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        if len(cur) + len(block) < MAX_PARAGRAPH:
            cur = f"{cur} {block}".strip()
            continue
        if len(cur) >= 120:
            out.append(cur)
        cur = block[:MAX_PARAGRAPH]
    if len(cur) >= 120:
        out.append(cur)
    return out


class RuleIndex:
    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.tf = [Counter(_tokens(p["text"])) for p in passages]
        self.length = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.length) / len(self.length)) if self.length else 1.0
        df = Counter(w for c in self.tf for w in c)
        n = len(passages)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def search(self, case_text: str, k: int = 3, query_terms: int = 40) -> list[dict]:
        words = {w for w in _tokens(case_text) if w in self.idf}
        query = sorted(words, key=lambda w: -self.idf[w])[:query_terms]
        scored = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w in query:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (K1 + 1) / (f + K1 * (1 - B + B * self.length[i] / self.avg))
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        seen, hits = set(), []
        for s, i in scored:
            p = self.passages[i]
            key = p["text"][:200]
            if p["url"] in seen or key in seen:   # one passage per page; the same page under two URLs once
                continue
            seen.update((p["url"], key))
            hits.append(p)
            if len(hits) == k:
                break
        return hits


def build_index(input_root: Path) -> Optional[RuleIndex]:
    """Index the administration pages of every corpus under input_root/retrieval-corpora; None if there are none."""
    passages = []
    for corpus in sorted((input_root / "retrieval-corpora").glob("*/documents.jsonl.gz")):
        name = corpus.parent.name.lower()
        if name.endswith("-en") or "law" in name:
            continue
        intranet = "intra" in name or "intern" in name
        with gzip.open(corpus, "rt", encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = d.get("url", "")
                if not (intranet or ADMIN_PATH.search(url)):
                    continue
                title = (d.get("title") or "").strip()
                for para in _paragraphs(title, d.get("content") or d.get("text") or ""):
                    passages.append({"title": title, "url": url, "text": para})
    return RuleIndex(passages) if passages else None


def rules_block(index: Optional[RuleIndex], case_text: str, k: int = 3) -> str:
    """The prompt block with the top passages, or "" when there is no index or no hit."""
    if index is None:
        return ""
    hits = index.search(case_text, k)
    if not hits:
        return ""
    lines = ["WEITERE REGELSTELLEN aus den Seiten der Universität (automatisch gesucht; nur anwenden, "
             "wenn eine Stelle eindeutig auf diesen Fall zutrifft):"]
    for h in hits:
        lines.append(f"- {h['title']} ({h['url']}): {h['text'][:MAX_PARAGRAPH]}")
    return "\n".join(lines) + "\n\n"
