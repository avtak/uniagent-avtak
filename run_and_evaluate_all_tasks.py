#!/usr/bin/env python3
"""Run this baseline end-to-end on all three UNIAGENT'26 task-2 "solving"
spot-check datasets and print the resulting accuracy for each.

For every dataset, this script:

1. Runs `tira-cli code-submission --dry-run` in a subshell, exactly as
   documented in this baseline's README.md ("Submit to TIRA" section). This
   builds the baseline's Docker image, downloads the dataset via TIRA, and
   executes the baseline against it locally.
2. Parses tira-cli's stdout for the local directory holding the run's
   results (`predictions.jsonl`/`run-trace.jsonl.log.gz`), reported in the
   line "... (You can verify them at <directory>)".
3. Runs `tira-cli evaluate` on that directory, exactly as documented in
   [`../../datasets/README.md`](../../datasets/README.md), and parses the
   resulting `accuracy` from its "Result:" JSON output.

Requires OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL in the
environment (forwarded into the baseline's container; OPENAI_REASONING_EFFORT
is forwarded too if set), a working `tira-cli` installation with network
access to TIRA, and Docker. Failures for one dataset are reported but do not
stop the remaining datasets from being tried; the script exits non-zero if
any dataset failed.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Union

BASELINE_DIR = Path(__file__).resolve().parent
TIRA_TASK = "uniagent-2026"

REQUIRED_ENV_VARS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL")
OPTIONAL_ENV_VARS = ("OPENAI_REASONING_EFFORT",)

# Matches the "(You can verify them at <directory>)" message that
# tira.tira_client.TiraClient.submit_code() prints once it has built the
# Docker image and executed it locally on the dataset (see submit_code() in
# the tira python package).
RESULTS_DIRECTORY_PATTERN = re.compile(r"You can verify them at (\S+)\)")

# Matches the "Result:\n\t{...}" JSON object that
# TiraClient.evaluate_sandboxed() prints after running the dataset's
# evaluator (see __run_evaluation() in the tira python package).
EVALUATION_RESULT_PATTERN = re.compile(r"Result:\s*(\{.*\})")


@dataclass
class Task:
    label: str
    tira_dataset_id: str


TASKS = [
    Task(label="business-trip", tira_dataset_id="business-trip-spot-check-20260907-training"),
    Task(
        label="expense-reimbursement",
        tira_dataset_id="task-2-expense-reimbursement-spot-check-20260928-training",
    ),
    Task(label="procurement", tira_dataset_id="task-2-procurement-spot-check-20260928-training"),
]


def require_environment() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            f"Required environment variable(s) not set: {', '.join(missing)}. "
            "Export OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL first."
        )


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(command)}", flush=True)
    result = subprocess.run(command, text=True, **kwargs)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {command!r} returned non-zero exit status {result.returncode}; "
            "see the output above."
        )
    return result


def forwarded_env_vars() -> list[str]:
    return [
        name
        for name in REQUIRED_ENV_VARS + OPTIONAL_ENV_VARS
        if os.environ.get(name, "").strip()
    ]


def run_code_submission(task: Task) -> Path:
    """Run this baseline via `tira-cli code-submission --dry-run` on
    `task`'s dataset and return the local directory holding its results.
    """
    command = [
        "tira-cli",
        "code-submission",
        "--path", ".",
        "--task", TIRA_TASK,
        "--dataset", task.tira_dataset_id,
        "--forward-environment-variable", *forwarded_env_vars(),
        "--command", "/predict.py --input $inputDataset --output $outputDir",
        "--dry-run",
    ]
    result = run(command, cwd=BASELINE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    match = RESULTS_DIRECTORY_PATTERN.search(result.stdout)
    if not match:
        raise RuntimeError(
            f"Could not find the results directory in tira-cli's output for "
            f"dataset {task.tira_dataset_id!r}; see the output above."
        )
    return Path(match.group(1))


def run_evaluate(task: Task, predictions_dir: Path) -> dict:
    """Run `tira-cli evaluate` on `predictions_dir`, as documented in
    ../../datasets/README.md, and parse the resulting measures.
    """
    command = [
        "tira-cli",
        "evaluate",
        "--dataset", f"{TIRA_TASK}/{task.tira_dataset_id}",
        "--predictions", str(predictions_dir),
    ]
    result = run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    match = EVALUATION_RESULT_PATTERN.search(result.stdout)
    if not match:
        raise RuntimeError(
            f"Could not find the evaluation result in tira-cli's output for "
            f"dataset {task.tira_dataset_id!r}; see the output above."
        )
    return json.loads(match.group(1))


def main() -> int:
    require_environment()

    results: dict[str, Union[float, str]] = {}
    for task in TASKS:
        print(f"\n=== {task.label} ({task.tira_dataset_id}) ===", flush=True)
        try:
            predictions_dir = run_code_submission(task)
            evaluation = run_evaluate(task, predictions_dir)
            results[task.label] = evaluation["Accuracy"]
        except Exception as error:
            results[task.label] = f"ERROR: {error}"

    print("\n=== Accuracy summary ===")
    for task in TASKS:
        print(f"{task.label}: {results[task.label]}")

    return 1 if any(isinstance(value, str) for value in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

