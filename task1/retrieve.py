#!/usr/bin/env python3
"""avtak Task 1 (retrieval): the organisers' PyTerrier baseline plus four lexical
changes from the development notes (not included), no model in the path.

1. weighting model (default DPH instead of BM25);
2. the title (first text block) repeated in the indexed text;
3. query = short query + description when the topic has one;
4. exact-duplicate collapse: of documents with the same body, only the
   highest-ranked one stays in the run.

    retrieve.py --dataset DIR --output DIR [--wmodel DPH] [--title-weight 3]
                [--no-description] [--no-dedup]
"""
from pathlib import Path
import hashlib
import re
import tempfile

import click
import pandas as pd
import pyterrier as pt
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


def create_index(docs: list, language: str, title_weight: int, output: Path):
    index_directory = Path(tempfile.mkdtemp(prefix="avtak-retrieval_"))
    indexer = pt.IterDictIndexer(str(index_directory), overwrite=True, meta={"docno": 100},
                                 verbose=False, **RETRIEVAL_CONFIGURATION[language])
    stream = ({"docno": str(d.doc_id), "text": (title_of(d.default_text()) + " ") * title_weight + d.default_text()}
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
@click.option("--no-dedup", is_flag=True, help="Keep duplicate documents in the run.")
def main(dataset: str, output: Path, wmodel: str, title_weight: int, no_description: bool, no_dedup: bool) -> None:
    ir_dataset = ir_datasets.load(dataset)
    output.mkdir(parents=True, exist_ok=True)
    docs = list(ir_dataset.docs_iter())
    keys = {str(d.doc_id): body_key(d.default_text()) for d in docs}
    queries = list(ir_dataset.queries_iter())
    if not queries:
        raise click.ClickException("The dataset has no queries.")
    # One index per query language present (the baseline refused mixed-language topic sets).
    runs = []
    for language in sorted({query_language(q) for q in queries}):
        index = create_index(docs, language, title_weight, output)
        tokeniser = pt.TerrierTokeniser.java_tokeniser(RETRIEVAL_CONFIGURATION[language]["tokeniser"])
        topics = pd.DataFrame([{"qid": str(q.query_id),
                                "query": " ".join(tokeniser.getTokens(query_text(q, not no_description)))}
                               for q in queries if query_language(q) == language], columns=["qid", "query"])
        with tracking(export_file_path=output / f"retrieval-ir-metadata-{language}.yml"):
            parts = [pt.terrier.Retriever(index, wmodel=m, num_results=DEPTH).transform(topics) for m in wmodel.split("+")]
        runs.append(parts[0] if len(parts) == 1 else rrf(parts))
    run = pd.concat(runs, ignore_index=True)
    if not no_dedup:
        run = collapse_duplicates(run, keys)
    pt.io.write_results(run, output / "run.txt.gz")
    click.echo(f"{len(queries)} queries, {len(docs)} documents, {wmodel}, title x{title_weight}, "
               f"description {'off' if no_description else 'on'}, dedup {'off' if no_dedup else 'on'}")


if __name__ == "__main__":
    main()
