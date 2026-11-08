import sys, os, json
REPO=os.path.expanduser("~/dev/uniagent-avtak"); sys.path.insert(0, REPO)
from pathlib import Path
import predict
D=Path(os.path.expanduser("~/dev/uniagent-code/cikm26/datasets"))
for ds, case in [("business-trip-spot-check","dienstreiseantrag-01"),("task-2-procurement-spot-check","beschaffungsantrag-08"),("task-2-expense-reimbursement-spot-check","auslagenerstattung-05")]:
    ev=predict.build_case_evidence(D/ds/"inputs", case)
    parts={k: len(json.dumps(v, ensure_ascii=False)) for k,v in ev.items()}
    p=predict.decision_prompt(ev); s=predict.system_prompt_for(predict.case_type_for(case))
    raw=sum(len(t) for t in ev["documents"].values())
    import re
    squeezed=sum(len(re.sub(r"[ ]{2,}","  ",t)) for t in ev["documents"].values())
    print(case, "prompt chars", len(p)+len(s), parts, "raw doc chars", raw, "docs with spaces squeezed", squeezed)
