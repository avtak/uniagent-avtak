#!/usr/bin/env python3
"""avtak Task 1 (retrieval): the organisers' PyTerrier baseline plus four lexical
changes from the development notes (not included), no model in the path.

1. weighting model (default DPH instead of BM25);
2. the title (first text block) repeated in the indexed text;
3. query = short query + description when the topic has one;
4. optional exact-duplicate collapse (--dedup): of documents with the same body, only the
   highest-ranked one stays; off by default (decision 26). Scores fall strictly by rank (ties).
Plus: Terrier's term-length limit raised to 60 (German compounds), optional --rerank (rerank.py).

    retrieve.py --dataset DIR --output DIR [--wmodel DPH] [--title-weight 3]
                [--no-description] [--dedup]
"""
from pathlib import Path
import hashlib
import re
import tempfile

import click
import pandas as pd
import pyterrier as pt

# Terrier drops every token longer than 20 characters by default, so German compounds such as
# "Wegstreckenentschädigung" or "Reisekostenerstattung" never reached index or query (T4).
# Must be set before Java starts.
pt.terrier.set_property("max.term.length", "60")
from tira.third_party_integrations import ir_datasets
from tirex_tracker import tracking

RETRIEVAL_CONFIGURATION = {
    "de": {
        "stemmer": pt.TerrierStemmer.german,
        "stopwords": Path(__file__).with_name("german-stopwords.txt").read_text(encoding="utf-8").splitlines(),
        "tokeniser": pt.TerrierTokeniser.utf,
    },
    "en": {
        "stemmer": pt.TerrierStemmer.porter,
        "stopwords": pt.TerrierStopwords.terrier,
        "tokeniser": pt.TerrierTokeniser.english,
    },
}
DEPTH = 1000


def title_of(text: str) -> str:
    """The first block of a document's text is its title ("Startseite - UNI",
    "§ 2 HRKG | Landesnorm Hessen | ...")."""
    return text.strip().split("\n\n", 1)[0][:300]


def body_key(text: str) -> str:
    """Hash of the body without the title, whitespace-normalised: pages that differ
    only in their title or spacing count as copies."""
    body = text.strip().split("\n\n", 1)[-1]
    return hashlib.sha1(re.sub(r"\s+", " ", body).strip().lower().encode()).hexdigest()


def query_language(query) -> str:
    original = query.original_query if isinstance(query.original_query, dict) else {}
    language = (original.get("language") or "de").strip().lower()[:2]
    return language if language in RETRIEVAL_CONFIGURATION else "de"


def query_text(query, use_description: bool) -> str:
    text = query.default_text()
    original = query.original_query if isinstance(query.original_query, dict) else {}
    description = (original.get("description") or getattr(query, "description", "") or "").strip()
    if use_description and description and description != text:
        text = f"{text} {description}"
    return text


def create_index(docs: list, language: str, title_weight: int, output: Path, slugs: dict | None = None,
                 slug_weight: int = 0):
    index_directory = Path(tempfile.mkdtemp(prefix="avtak-retrieval_"))
    indexer = pt.IterDictIndexer(str(index_directory), overwrite=True, meta={"docno": 100},
                                 verbose=False, **RETRIEVAL_CONFIGURATION[language])
    slugs = slugs or {}
    stream = ({"docno": str(d.doc_id), "text": (title_of(d.default_text()) + " ") * title_weight
               + (slugs.get(str(d.doc_id), "") + " ") * slug_weight + d.default_text()}
              for d in docs)
    with tracking(export_file_path=output / f"index-ir-metadata-{language}.yml"):
        return pt.IndexFactory.of(indexer.index(stream))


def rrf(parts: list, k: int = 60) -> pd.DataFrame:
    """Reciprocal rank fusion of several runs over the same topics."""
    scores = {}
    for part in parts:
        for qid, docno, rank in part[["qid", "docno", "rank"]].itertuples(index=False):
            scores[(qid, docno)] = scores.get((qid, docno), 0.0) + 1.0 / (k + rank + 1)
    fused = pd.DataFrame([(q, d, s) for (q, d), s in scores.items()], columns=["qid", "docno", "score"])
    fused = fused.sort_values(["qid", "score"], ascending=[True, False]).groupby("qid").head(DEPTH)
    fused["rank"] = fused.groupby("qid").cumcount()
    return fused


def collapse_duplicates(run: pd.DataFrame, keys: dict) -> pd.DataFrame:
    """Keep the best-ranked document per body hash and query, then re-rank."""
    run = run.sort_values(["qid", "rank"])
    run = run[~run.assign(key=run["docno"].map(keys)).duplicated(["qid", "key"])].copy()
    run["rank"] = run.groupby("qid").cumcount()
    return run


@click.command()
@click.option("--dataset", required=True, help="The TIRA dataset ID or local dataset directory.")
@click.option("--output", required=True, type=click.Path(path_type=Path, file_okay=False))
@click.option("--wmodel", default="DPH", show_default=True, help="One model, or several joined by '+' for RRF fusion.")
@click.option("--title-weight", default=3, show_default=True, type=int)
@click.option("--no-description", is_flag=True, help="Search with the short query only.")
@click.option("--dedup", is_flag=True, help="Collapse exact copies (only pays if the qrels judge one copy; decision 26).")
@click.option("--no-dedup", is_flag=True, hidden=True, help="Kept for old commands; copies are kept by default now.")
@click.option("--rerank", is_flag=True, help="Cross-encoder rerank of the top 20 (rerank.py; needs the v3 image).")
@click.option("--slug-weight", default=0, show_default=True, type=int, help="Repeat URL slug words in the index (priors.py).")
@click.option("--url-prior", is_flag=True, help="Demote news, people, event and mailing-list pages (priors.py).")
@click.option("--law-versions", is_flag=True, help="Current norm version first, outdated versions right behind (priors.py).")
def main(dataset: str, output: Path, wmodel: str, title_weight: int, no_description: bool, dedup: bool, no_dedup: bool,
         rerank: bool, slug_weight: int, url_prior: bool, law_versions: bool) -> None:
    ir_dataset = ir_datasets.load(dataset)
    output.mkdir(parents=True, exist_ok=True)
    docs = list(ir_dataset.docs_iter())
    keys = {str(d.doc_id): body_key(d.default_text()) for d in docs}
    meta = {}
    if slug_weight or url_prior or law_versions:
        from priors import load_meta, slug_words
        meta = load_meta(dataset)  # url and title from documents.jsonl.gz; empty if the folder has none
    slugs = {d: slug_words(u) for d, (u, _) in meta.items()} if slug_weight else {}
    queries = list(ir_dataset.queries_iter())
    if not queries:
        raise click.ClickException("The dataset has no queries.")
    # One index per query language present (the baseline refused mixed-language topic sets).
    runs = []
    for language in sorted({query_language(q) for q in queries}):
        index = create_index(docs, language, title_weight, output, slugs, slug_weight)
        tokeniser = pt.TerrierTokeniser.java_tokeniser(RETRIEVAL_CONFIGURATION[language]["tokeniser"])
        topics = pd.DataFrame([{"qid": str(q.query_id),
                                "query": " ".join(tokeniser.getTokens(query_text(q, not no_description)))}
                               for q in queries if query_language(q) == language], columns=["qid", "query"])
        with tracking(export_file_path=output / f"retrieval-ir-metadata-{language}.yml"):
            parts = [pt.terrier.Retriever(index, wmodel=m, num_results=DEPTH).transform(topics) for m in wmodel.split("+")]
        runs.append(parts[0] if len(parts) == 1 else rrf(parts))
    run = pd.concat(runs, ignore_index=True)
    if meta and url_prior:
        from priors import url_prior as apply_url_prior
        run = apply_url_prior(run, meta)
    if meta and law_versions:
        from priors import group_law_versions
        run = group_law_versions(run, meta)
    if rerank:
        from rerank import rerank as cross_rerank
        texts = {str(d.doc_id): d.default_text() for d in docs}
        with tracking(export_file_path=output / "rerank-ir-metadata.yml"):
            run = cross_rerank(run, {str(q.query_id): query_text(q, not no_description) for q in queries}, texts)
    if meta and law_versions and rerank:
        run = group_law_versions(run, meta)  # the reranker may split a norm's versions again
    if dedup and not no_dedup:
        run = collapse_duplicates(run, keys)
    # Strictly falling scores: exact copies share a DPH score, and evaluators break ties by
    # docno, which would replace our ranking with an arbitrary one (198 of 250 de top-10 slots).
    run = run.sort_values(["qid", "rank"]).copy()
    run["score"] = float(DEPTH) - run["rank"]
    pt.io.write_results(run, output / "run.txt.gz")
    click.echo(f"{len(queries)} queries, {len(docs)} documents, {wmodel}, title x{title_weight}, "
               f"description {'off' if no_description else 'on'}, dedup {'on' if dedup and not no_dedup else 'off'}, "
               f"rerank {'on' if rerank else 'off'}, slug x{slug_weight}, url prior {'on' if url_prior else 'off'}, "
               f"law versions {'on' if law_versions else 'off'} (metadata for {len(meta)} documents)")


if __name__ == "__main__":
    main()
