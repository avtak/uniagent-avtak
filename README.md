# Team avtak at UniAgent 2026

Code and data of team **avtak** (Hassan Hassanzadeh Aliabadi) for the [UniAgent shared task](https://uniagent.webis.de/cikm26/uniagent26-web/agentic-university-administration.html) at the CIKM 2026 AnalytiCup: administrative tasks at the University of Kassel.

- **Task 1 (Retrieval):** rank pages of the university's website, its intranet and Hessian law for staff queries. A lexical PyTerrier system, optionally with a cross-encoder reranker. No LLM call.
- **Task 2 (Solving):** decide business-trip, procurement and expense-refund cases as *angenommen* or *abgelehnt*. Code reads the PDFs and computes fact lines and check notes; rule cards quote the university's rules; one model call decides.

Paper: *Team avtak at UniAgent 2026: Lexical Retrieval and Code-Computed Facts for Administrative Case Decisions*, UniAgent at CIKM 2026 (CEUR Workshop Proceedings, to appear). Link and DOI will be added here after publication.

## Results (official evaluation)

| Task | System | Result |
|---|---|---|
| 1 | parallel-grouse (lexical) | nDCG@10 0.670 over all queries (web de 0.856, web en 0.766, law 0.656, intranet 0.403) |
| 1 | simple-truss (reranked) | nDCG@10 0.664 (intranet 0.464, web en 0.814) |
| 2 | bordeaux-spore, ambitious-camera (gpt-oss-120b) | accuracy 0.750 on 80 cases |
| 2 | icy-transfer (gpt-oss-120b and -20b) | accuracy 0.713 |

Awards in Task 2: highest accuracy on the regular business-travel cases (0.75), and highest accuracy on the easy cases (0.85, shared). Full tables: [`results/`](results/).

## Submitted versions

Each upload to TIRA has a tag here, with the same name as in the paper (comments in the code shortened). A tag shows the files as they were uploaded, with the Task 2 code at the top level; the current `main` has the tidier layout below.

| Task | Upload name | Tag | Main change |
|---|---|---|---|
| 2 | bold-frogman | `r7-retry` | hand-written checklist; no code facts |
| 2 | unsorted-option | `r13a2` | facts and notes by code; rule cards |
| 2 | feasible-clubhouse | `r20b` | notes only on clear evidence; closing per model |
| 2 | bordeaux-spore | `r22c` | rule search for gpt-oss; more card rules |
| 2 | ambitious-camera | `r22d` | four fact-reader fixes |
| 2 | icy-transfer | `r22f` | OCR; Unicode normalisation; negation |
| 1 | covering-exponential | `t1-upload1` | lexical; exact copies collapsed (`--dedup`) |
| 1 | burgundy-chino | `t1-upload2` | lexical; exact copies kept |
| 1 | simple-truss | `t1-upload3` | parallel-grouse plus reranker and law versions (`task1/Dockerfile.v3`, `--rerank --law-versions`) |
| 1 | parallel-grouse | `t1-upload4` | copies kept; term limit 60; strictly falling scores (`task1/Dockerfile`) |

## Layout

| Path | What |
|---|---|
| `task1/` | Task 1 retrieval (`retrieve.py`, `rerank.py`, `priors.py`), Dockerfiles, local evaluation |
| `task1/synth/` | 260 synthetic Task 1 topics with qrels (four sets) |
| `task1/qrels-twins/` | spot-check qrels extended to exact copies of judged pages |
| `task2/` | Task 2 agent (`predict.py`, `facts.py`, `rules.py`, `rule_search.py`, `parsing.py`, `case_tools.py`, `event_logging.py`), `Dockerfile`, offline tests (`test_*.py`) |
| `task2/experiments/` | synthetic Task 2 development cases (PDFs and ground truth): blind sets, held-out, variants, edge cases, layouts, traps, and 150 approvable cases in unseen layouts (`clean-ood`, `clean-ood-2`) |
| `results/` | official result tables and raw evaluation of our runs |

The University of Kassel policy pages that the rule cards quote are not included; each rule names its source page.

## Running

Task 2 runs as a TIRA code submission; the hosted model is read from `OPENAI_BASE_URL`, `OPENAI_MODEL` and `OPENAI_API_KEY`.

```bash
make setup     # Python venv with the exact versions in task2/requirements-lock.txt
make test      # Task 2 offline tests; they read the organisers' public spot-check data
docker build -t avtak-task2 task2
docker run --rm -e OPENAI_BASE_URL -e OPENAI_MODEL -e OPENAI_API_KEY \
  -v /path/to/cases:/input:ro -v /path/to/out:/output avtak-task2 --input /input --output /output
```

Task 1: see `task1/Dockerfile` (lexical) and `task1/Dockerfile.v3` (with reranker); the entry point is `task1/retrieve.py`.

The tests read the organisers' public spot-check datasets from `~/dev/uniagent-code/cikm26/datasets`, or from the folder in `UNIAGENT_DATASETS`.

## Licence

The code started from the organisers' baselines. A licence will be added once the organisers confirm it.
