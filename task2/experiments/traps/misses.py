import json, glob, os
R = os.path.expanduser("~/dev/uniagent-avtak/experiments")
D = os.path.expanduser("~/dev/uniagent-code/cikm26/datasets")
setroot = {"": D, "var-": R+"/variants", "edge-": R+"/edge-cases", "holdout-": R+"/holdout"}
runs = {"r13a-":"", "r13a-var-":"var-", "r13a-edge-":"edge-", "r13a-holdout-":"holdout-",
        "r13a2-exp-":"", "r13a2-edge-exp-":"edge-", "r13a2-holdout-exp-":"holdout-"}
for run, s in runs.items():
    for model in ["20b","120b","qwen7b"]:
        d = f"{R}/runs/2026-10-11-{run}{model}"
        if not os.path.isdir(d): continue
        for ds in sorted(os.listdir(d)):
            if "r13a-" == run[:5] and "expense" in ds and run in ("r13a-","r13a-edge-","r13a-holdout-"):
                tag="(superseded by r13a2)"
            else: tag=""
            gt = {}
            p = f"{setroot[s]}/{ds}/ground-truth.jsonl"
            if not os.path.exists(p): print("no gt", p); continue
            for l in open(p):
                j=json.loads(l); gt[j["antrag"]]=j
            pf=f"{d}/{ds}/predictions.jsonl"
            if not os.path.exists(pf): continue
            for l in open(pf):
                j=json.loads(l)
                g=gt.get(j["antrag"])
                if g and g["result"]!=j["result"]:
                    print(f"== {run}{model} {ds} {j['antrag']} truth={g['result']} pred={j['result']} {tag}\n   MODEL: {j['begruendung'][:500]}\n   GT: {g['begruendung'][:400]}")
