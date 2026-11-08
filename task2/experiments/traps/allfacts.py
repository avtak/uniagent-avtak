import sys, json, os, glob, subprocess
REPO=os.path.expanduser("~/dev/uniagent-avtak"); sys.path.insert(0, REPO)
from facts import compute_facts
from case_tools import case_type_for
R=REPO+"/experiments"; D=os.path.expanduser("~/dev/uniagent-code/cikm26/datasets")
roots=[D, R+"/variants", R+"/edge-cases", R+"/holdout", R+"/variants-unsure", R+"/edge-cases-unsure", R+"/holdout-unsure"]
show = sys.argv[1:] 
for root in roots:
    for ds in sorted(glob.glob(root+"/*spot-check")):
        if "retrieval" in ds: continue
        gt={}
        if os.path.exists(ds+"/ground-truth.jsonl"):
            for l in open(ds+"/ground-truth.jsonl"):
                j=json.loads(l); gt[j["antrag"]]=j["result"]
        for case in sorted(glob.glob(ds+"/inputs/*")):
            cid=os.path.basename(case)
            try: ct=case_type_for(cid)
            except ValueError: continue
            docs={}
            for pdf in sorted(glob.glob(case+"/*.pdf")):
                docs[os.path.basename(pdf)]=subprocess.run(["pdftotext","-layout",pdf,"-"],capture_output=True,text=True).stdout.strip()
            lines=compute_facts(ct,docs)
            notes=[l for l in lines if l.startswith("  *")]
            label=gt.get(cid,"?")
            flag = "FALSE-NOTE" if notes and label=="angenommen" else ("NO-NOTE-REJ" if not notes and label=="abgelehnt" else "")
            print(f"{os.path.relpath(case,os.path.dirname(os.path.dirname(root)))} [{label}] {flag}")
            if show and any(s in cid for s in show):
                print("\n".join(lines))
            else:
                for n in notes: print("   ",n)
