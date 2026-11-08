"""python3 experiments/traps/show.py PREFIX...  -> docs, facts and verdict of matching trap cases."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snippets, snippets2, snippets3, snippets4  # noqa
from facts import compute_facts
for cid, lik, kind, ctype, docs, want, why in snippets.CASES:
    if not any(cid.startswith(p + " ") for p in sys.argv[1:]):
        continue
    lines = compute_facts(ctype, docs)
    notes = snippets.notes_of(lines)
    hit = [n for n in notes if want in n] if want else notes
    ok = (not hit) if kind == "FALSE" else (bool(hit) if kind == "MISS" else None)
    print(f"##### {cid} [{kind}] want={want!r} ok={ok}  -- {why}")
    for n, t in docs.items():
        print(f"--- {n}\n{t}")
    print("--- FACTS"); print("\n".join(lines[1:]))
