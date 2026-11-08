import sys, os, json
REPO=os.path.expanduser("~/dev/uniagent-avtak"); sys.path.insert(0, REPO)
from pathlib import Path
import predict
from case_tools import case_type_for
probes = {
 "umlaut key": '{"antrag":"x","result":"angenommen","begründung":"ok"}',
 "capitalised label": '{"antrag":"x","result":"Angenommen","begruendung":"ok"}',
 "english label": '{"antrag":"x","result":"accepted","begruendung":"ok"}',
 "no reason": '{"antrag":"x","result":"angenommen"}',
 "reason key 'reason'": '{"result":"abgelehnt","reason":"fehlt"}',
 "template echo last": 'Antwort: {"antrag":"x","result":"abgelehnt","begruendung":"Rückreise fehlt"} Format war {"antrag":"x","result":"angenommen|abgelehnt","begruendung":"..."}',
 "markdown json fence w/ text": 'Hier:\n```json\n{"antrag":"x","result":"angenommen","begruendung":"ok"}\n```',
 "single quotes": "{'antrag':'x','result':'abgelehnt','begruendung':'fehlt'}",
 "trailing period label": '{"result":"abgelehnt.","begruendung":"x"}',
 "unescaped quote in reason": '{"antrag":"x","result":"abgelehnt","begruendung":"Feld "Reise ins Ausland" leer"}',
}
for k, v in probes.items():
    try:
        r = predict.parse_decision(v, "case-1"); print(f"OK   {k:28} -> {r['result']} / {r['begruendung'][:40]!r}")
    except Exception as e:
        print(f"FAIL {k:28} -> {type(e).__name__}: {str(e)[:90]}")
print()
inp = Path("fake_in").resolve()
cases = predict.input_cases(inp)
print("cases:", cases)
for c in cases:
    try:
        print(c, "->", case_type_for(c))
    except Exception as e:
        print(c, "-> ERROR", e)
ev = predict.build_case_evidence(inp, "dienstreiseantrag-94")
print("dienstreiseantrag-94 documents:", list(ev["documents"]), ev["facts_by_code"][1:2])
ev = predict.build_case_evidence(inp, "dienstreiseantrag-90")
print("dienstreiseantrag-90:", {k: v[:80] for k, v in ev["documents"].items()}, ev.get("documents_without_text"))
# context: prompt alone too large
class E(Exception):
    status_code = 400
e = E("This model's maximum context length is 32768 tokens. However, you requested 34000 tokens (33000 in the messages, 1000 in the completion).")
print("context error recognised:", predict.is_context_length_error(e), "reduced:", predict.reduced_output_tokens(e, 1000))
msgs=[{"role":"user","content":"x"*120000}]
print("budget for 120k-char prompt:", predict.output_token_budget(msgs, 16384), "est prompt tokens", predict.estimate_prompt_tokens(msgs))
msgs=[{"role":"user","content":"x"*75000}]
print("budget for 75k-char prompt (gpt-oss would want ~10k):", predict.output_token_budget(msgs, 16384))
