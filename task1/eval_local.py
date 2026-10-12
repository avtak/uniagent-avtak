#!/usr/bin/env python3
"""Score Task 1 configurations on the three spot-check sets (nDCG@10, R@100).
Runs inside the baseline image:

    eval_local.py --data /data --out /out "label:--wmodel BM25 --title-weight 0 --no-description --no-dedup" ...
"""
import subprocess
import sys
from pathlib import Path

import ir_measures
from ir_measures import nDCG, R

SETS = ["retrieval-de-spot-check", "retrieval-en-spot-check", "retrieval-hessian-law-de-spot-check"]


def main(argv):
    data, out = Path(argv[argv.index("--data") + 1]), Path(argv[argv.index("--out") + 1])
    configs = [a for a in argv if ":" in a and not a.startswith("/")]
    print(f"{'config':28} " + " ".join(f"{s.split('-')[1][:5]:>13}" for s in SETS) + "   mean nDCG")
    for spec in configs:
        label, args = spec.split(":", 1)
        cells, means = [], []
        for s in SETS:
            target = out / label / s
            subprocess.run([sys.executable, str(Path(__file__).with_name("retrieve.py")), "--dataset", str(data / s),
                            "--output", str(target), *args.split()], check=True, capture_output=True)
            qrels = list(ir_measures.read_trec_qrels(str(data / s / "qrels.txt")))
            run = list(ir_measures.read_trec_run(str(target / "run.txt.gz")))
            agg = ir_measures.calc_aggregate([nDCG @ 10, R @ 100], qrels, run)
            cells.append(f"{agg[nDCG @ 10]:.3f}/{agg[R @ 100]:.2f}")
            means.append(agg[nDCG @ 10])
        print(f"{label:28} " + " ".join(f"{c:>13}" for c in cells) + f"   {sum(means) / len(means):.3f}", flush=True)


if __name__ == "__main__":
    main(sys.argv)
