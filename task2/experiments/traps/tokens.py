import gzip, json, glob, os
R=os.path.expanduser("~/dev/uniagent-avtak/experiments/runs")
rows=[]
for f in glob.glob(R+"/2026-10-11-r13a*/*/run-trace.jsonl.log.gz"):
    model=f.split("/")[-3].rsplit("-",1)[-1]
    for line in gzip.open(f,"rt"):
        e=json.loads(line)
        if e.get("event_type")!="model_call" or e.get("status")!="ok": continue
        msgs=e["input"]["messages"]; chars=sum(len(m["content"]) for m in msgs)
        u=(e.get("output") or {}).get("token_usage") or {}
        pt=u.get("prompt_tokens") or u.get("input_tokens")
        ct=u.get("completion_tokens") or u.get("output_tokens")
        dur=e.get("duration_ms") or e.get("latency_ms")
        rows.append((model, e.get("case_id") or e.get("context",{}).get("case_id"), chars, pt, ct, e["input"].get("max_tokens"), dur))
import statistics
for m in ["20b","120b","qwen7b"]:
    rs=[r for r in rows if r[0]==m and r[3]]
    if not rs: continue
    ratio=[r[2]/r[3] for r in rs]
    print(m, "n",len(rs),"chars/token min %.2f med %.2f"%(min(ratio),statistics.median(ratio)),"max prompt_tokens",max(r[3] for r in rs),"max chars",max(r[2] for r in rs),"max completion",max(r[4] or 0 for r in rs))
print(rows[0])
