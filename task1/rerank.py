"""Cross-encoder rerank of each topic's lexical top K, blended with the lexical rank by RRF (Task 1 v3).

bge-reranker-v2-m3 on the top 20: +0.036 mean nDCG@10 over 7 sets in T3 (the development notes);
about 2.5 pairs/s on 4 CPU threads, so 50 topics take about 7 minutes.
"""
import os
from pathlib import Path

import pandas as pd

MODEL_DIR = Path("/app/models/bge-reranker-v2-m3")
DEVICE = os.environ.get("RERANK_DEVICE", "cpu")  # TIRA has no GPU; "cuda" only for development runs
TOP_K = 20
WORDS = 350


def rerank(run: pd.DataFrame, query_texts: dict, doc_texts: dict, threads: int = 4) -> pd.DataFrame:
    import torch
    from sentence_transformers import CrossEncoder

    torch.set_num_threads(threads)
    model = CrossEncoder(str(MODEL_DIR), max_length=512, device=DEVICE)
    out = []
    for qid, group in run.sort_values(["qid", "rank"]).groupby("qid", sort=False):
        docs = list(group["docno"])
        top, rest = docs[:TOP_K], docs[TOP_K:]
        scores = model.predict([(query_texts[qid], " ".join(doc_texts[d].split()[:WORDS])) for d in top],
                               batch_size=16, show_progress_bar=False)
        by_score = [d for _, d in sorted(zip(scores, top), key=lambda x: -x[0])]
        fused = sorted(top, key=lambda d: -(1 / (61 + top.index(d)) + 1 / (61 + by_score.index(d))))
        out += [(qid, d, i) for i, d in enumerate(fused + rest)]
    return pd.DataFrame(out, columns=["qid", "docno", "rank"])
