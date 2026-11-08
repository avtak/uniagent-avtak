"""Rule-based signals from document metadata (Task 1 T6; ideas from a blind review). Hand-set, not learned: our synthetic topics were sampled with
a preference for admin URLs, so anything fitted on them would be circular.

- URL slug words as an extra indexed field (the CMS slug is a clean, hyphen-split heading).
- URL prior: news, people, event and mailing-list pages are demoted (never relevant in the spot check).
- Law versions: a norm's current version first, its outdated versions ("gültig bis") right behind it,
  so both one-copy and pooled judging find it (818 of 2,829 spot-check law documents are outdated, none relevant).
"""
import gzip
import json
import re
from pathlib import Path

import pandas as pd

LOW_VALUE_URL = re.compile(r"news|/aktuelles|meldung|pressemitteilung|/personen?/|/team/|/people/|veranstaltung|"
                           r"/events?/|lists\.its|sympa|/termine/", re.IGNORECASE)
URL_FACTOR = 0.7
NORM_KEY = re.compile(r"^\s*(.+?)\s*\|\s*Landesnorm", re.IGNORECASE)
OUTDATED = re.compile(r"gültig\s+bis", re.IGNORECASE)


def load_meta(dataset: str) -> dict:
    """doc_id -> (url, title) from the dataset folder's documents.jsonl.gz; empty if not available."""
    path = Path(dataset) / "documents.jsonl.gz"
    if not path.exists():
        return {}
    meta = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            meta[str(d["doc_id"])] = (d.get("url") or "", d.get("title") or "")
    return meta


def slug_words(url: str) -> str:
    """Words of the last two URL path segments: .../beschaffung/software-campuslizenzen.html ->
    'beschaffung software campuslizenzen'. Query strings, fragments, file endings and ids are dropped."""
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0].split("#")[0]
    parts = [re.sub(r"\.(html?|php|aspx?)$", "", p) for p in path.split("/") if p]
    words = re.split(r"[-_.]+", " ".join(parts[-2:]))
    return " ".join(w for w in words if w and not w.isdigit() and len(w) > 1)


def _rerank(run: pd.DataFrame) -> pd.DataFrame:
    run = run.copy()
    run["rank"] = run.groupby("qid").cumcount()
    return run


def url_prior(run: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Multiply the retrieval score of low-value page types by URL_FACTOR and re-sort."""
    run = run.copy()
    factor = run["docno"].map(lambda d: URL_FACTOR if LOW_VALUE_URL.search(meta.get(d, ("", ""))[0]) else 1.0)
    run["score"] = run["score"] * factor
    return _rerank(run.sort_values(["qid", "score"], ascending=[True, False]))


def group_law_versions(run: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Keep each norm's versions together at the position of its best-ranked version, current first."""
    out = []
    for qid, group in run.sort_values(["qid", "rank"]).groupby("qid", sort=False):
        docs = list(group["docno"])
        key = {d: (NORM_KEY.match(meta.get(d, ("", ""))[1]) or [None, None])[1] for d in docs}
        members = {}
        for d in docs:
            if key[d]:
                members.setdefault(key[d], []).append(d)
        emitted, order = set(), []
        for d in docs:
            if d in emitted:
                continue
            if key[d]:
                versions = members[key[d]]
                current = [v for v in versions if not OUTDATED.search(meta[v][1])]
                for v in current + [v for v in versions if v not in current]:
                    order.append(v)
                    emitted.add(v)
            else:
                order.append(d)
                emitted.add(d)
        out += [(qid, d, i) for i, d in enumerate(order)]
    return pd.DataFrame(out, columns=["qid", "docno", "rank"]).assign(score=lambda f: float(len(f)) - f["rank"])
