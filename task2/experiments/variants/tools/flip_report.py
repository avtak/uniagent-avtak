#!/usr/bin/env python3
"""Compare a variant run with a run on the practice cases (same model, same code).

    python3 experiments/variants/tools/flip_report.py experiments/runs/<variants-run> experiments/runs/<practice-run>

For every variant: the base case's prediction and gold label, the variant's prediction and gold
label, and whether the model changed its answer when the gold label changed. Read-only; calls no model.
"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
VARIANTS = HERE.parent
PRACTICE = pathlib.Path(os.environ.get("UNIAGENT_PRACTICE",
                                       pathlib.Path.home() / "dev/uniagent-code/cikm26/datasets"))
SETS = ["business-trip-spot-check", "task-2-procurement-spot-check", "task-2-expense-reimbursement-spot-check"]


def rows(path):
    p = pathlib.Path(path)
    return {j["antrag"]: j["result"] for j in map(json.loads, open(p))} if p.exists() else {}


def main():
    v_run, b_run = map(pathlib.Path, sys.argv[1:3])
    print(f"{'variant':28} {'base gold':11} {'base pred':11} {'var gold':11} {'var pred':11} verdict")
    ok = 0
    n = 0
    for s in SETS:
        v_gold = rows(VARIANTS / s / "ground-truth.jsonl")
        b_gold = rows(PRACTICE / s / "ground-truth.jsonl")
        v_pred, b_pred = rows(v_run / s / "predictions.jsonl"), rows(b_run / s / "predictions.jsonl")
        for vid, g in sorted(v_gold.items()):
            base = vid.rsplit("-v", 1)[0]
            vp, bp = v_pred.get(vid, "NONE"), b_pred.get(base, "NONE")
            verdict = "correct" if vp == g else "WRONG"
            if g != b_gold[base]:
                verdict += ", flip expected, " + ("flipped" if vp != bp else "DID NOT FLIP")
            else:
                verdict += ", label kept"
            n += 1
            ok += vp == g
            print(f"{vid:28} {b_gold[base]:11} {bp:11} {g:11} {vp:11} {verdict}")
    print(f"{ok}/{n} variants correct")


if __name__ == "__main__":
    main()
