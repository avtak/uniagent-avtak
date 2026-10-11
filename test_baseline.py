import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from case_tools import (
    BUSINESS_TRIP_POLICIES,
    EXPENSE_REIMBURSEMENT_POLICIES,
    PROCUREMENT_POLICIES,
    CheckFactsTool,
    ListCaseDocumentsTool,
    LookupPolicyTool,
    ReadPdfTool,
    SearchCaseTool,
    case_type_for,
)
from event_logging import case_context, log_event, log_tool_calls, log_to_file, model_context, reset_state
from predict import (
    MIN_OUTPUT_TOKENS,
    MODEL_CONTEXT_TOKENS,
    NO_TEXT_NOTE,
    build_case_evidence,
    call_model,
    decide_case,
    estimate_prompt_tokens,
    input_cases,
    output_token_budget,
    parse_decision,
)


DATASETS_ROOT = Path(
    os.environ.get("UNIAGENT_DATASETS", Path.home() / "dev/uniagent-code/cikm26/datasets")
).resolve()
DATASET = (DATASETS_ROOT / "business-trip-spot-check" / "inputs").resolve()
EXPENSE_DATASET = (
    DATASETS_ROOT / "task-2-expense-reimbursement-spot-check" / "inputs"
).resolve()
PROCUREMENT_DATASET = (DATASETS_ROOT / "task-2-procurement-spot-check" / "inputs").resolve()


class BaselineTest(unittest.TestCase):
    def test_lists_all_cases(self):
        self.assertEqual(
            input_cases(DATASET),
            [f"dienstreiseantrag-0{index}" for index in range(1, 6)],
        )

    def test_lists_and_reads_case_documents(self):
        case_id = "dienstreiseantrag-03"
        listed = json.loads(ListCaseDocumentsTool(DATASET, case_id)(case_id))
        self.assertEqual(3, len(listed))
        text = ReadPdfTool(DATASET, case_id)(case_id, "antrag-dienstreisegenehmigung.pdf")
        self.assertIn("Lyon, FRANKREICH", text)

    def test_rejects_cross_case_access(self):
        tool = ListCaseDocumentsTool(DATASET, "dienstreiseantrag-03")
        with self.assertRaises(ValueError):
            tool("dienstreiseantrag-04")

    def test_searches_with_citations(self):
        case_id = "dienstreiseantrag-05"
        matches = json.loads(SearchCaseTool(DATASET, case_id)(case_id, "Doppelfinanzierung", 5))
        self.assertTrue(matches)
        self.assertEqual("email-stipendienzusage.pdf", matches[0]["document"])

    def test_policy_lookup(self):
        result = json.loads(
            LookupPolicyTool(BUSINESS_TRIP_POLICIES)("Doppelfinanzierung Stipendium")
        )
        self.assertIn("double_funding", result["policies"])

    def test_deterministic_fact_checks(self):
        tool = CheckFactsTool()
        dates = json.loads(
            tool(
                {
                    "kind": "compare_dates",
                    "comparisons": [
                        {
                            "name": "application_before_trip",
                            "left": "20.10.2026",
                            "operator": "<",
                            "right": "14.10.2026",
                        }
                    ],
                }
            )
        )
        self.assertFalse(dates["results"][0]["passed"])

        overlap = json.loads(
            tool(
                {
                    "kind": "overlap",
                    "left": ["Flug", "Unterkunft"],
                    "right": ["Konferenz", "Flug"],
                }
            )
        )
        self.assertEqual(["flug"], overlap["overlap"])

    def test_parses_strict_decision(self):
        answer = json.dumps(
            {
                "antrag": "dienstreiseantrag-01",
                "result": "abgelehnt",
                "begruendung": "Der Antrag wurde nach Reisebeginn gestellt.",
            }
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_parses_json_embedded_in_short_explanation(self):
        answer = (
            "Ergebnis:\n"
            '{"antrag":"dienstreiseantrag-01","result":"abgelehnt",'
            '"begruendung":"Der Antrag wurde nach Reisebeginn gestellt."}'
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_does_not_accept_malformed_decision(self):
        with self.assertRaises(ValueError):
            parse_decision("abgelehnt", "dienstreiseantrag-01")

    def test_builds_complete_case_evidence(self):
        evidence = build_case_evidence(DATASET, "dienstreiseantrag-01")
        self.assertIn("antrag-dienstreisegenehmigung.pdf", evidence["documents"])
        self.assertTrue(evidence["document_completeness_check"]["complete"])
        self.assertIn("advance_approval", evidence["policies"]["policies"])


    def test_decides_from_preloaded_evidence_without_agent_protocol(self):
        class FakeModel:
            def __init__(self):
                self.messages = None

            def generate(self, messages, **_kwargs):
                self.messages = messages
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "antrag": "dienstreiseantrag-01",
                            "result": "abgelehnt",
                            "begruendung": "Der Antrag wurde nach der Reise gestellt.",
                        }
                    ),
                    raw=None,
                )

        import contextlib
        import io

        model = FakeModel()
        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case(DATASET, "dienstreiseantrag-01", model)
        self.assertEqual("abgelehnt", decision["result"])
        self.assertIn("bahn-rechnung-kassel-leipzig.pdf", model.messages[1]["content"])

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        event_types = [entry["event_type"] for entry in entries]
        self.assertIn("model_call", event_types)
        self.assertEqual("decision", event_types[-1])
        for entry in entries:
            self.assertEqual("dienstreiseantrag-01", entry["case_id"])
            self.assertEqual("gpt-oss-20b", entry["model"])

    def test_retries_and_recovers_from_one_invalid_json_response(self):
        class FlakyModel:
            def __init__(self):
                self.calls = 0

            def generate(self, messages, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(content="Das ist keine gueltige Antwort.", raw=None)
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "antrag": "dienstreiseantrag-01",
                            "result": "angenommen",
                            "begruendung": "Alle Belege sind vollstaendig und plausibel.",
                        }
                    ),
                    raw=None,
                )

        import contextlib
        import io

        model = FlakyModel()
        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case(DATASET, "dienstreiseantrag-01", model)
        self.assertEqual(2, model.calls)
        self.assertEqual("angenommen", decision["result"])

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        relevant = [
            entry["event_type"]
            for entry in entries
            if entry["event_type"] in {"model_call", "error", "decision"}
        ]
        self.assertEqual(["model_call", "error", "model_call", "decision"], relevant)
        error_entry = next(entry for entry in entries if entry["event_type"] == "error")
        self.assertEqual("error", error_entry["status"])
        self.assertIsNotNone(error_entry["error"])
        self.assertEqual("ok", entries[-1]["status"])

    def test_falls_back_to_a_valid_decision_when_the_model_never_returns_json(self):
        class AlwaysInvalidModel:
            def generate(self, messages, **_kwargs):
                return SimpleNamespace(content="Ich kann keine Entscheidung liefern.", raw=None)

        import contextlib
        import io

        model = AlwaysInvalidModel()
        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case(DATASET, "dienstreiseantrag-01", model)
        self.assertEqual("dienstreiseantrag-01", decision["antrag"])
        self.assertEqual("abgelehnt", decision["result"])
        self.assertTrue(decision["begruendung"])

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        self.assertEqual("decision", entries[-1]["event_type"])
        self.assertEqual("error", entries[-1]["status"])
        self.assertIsNotNone(entries[-1]["error"])
        logged = entries[-1]["output"]
        self.assertEqual(decision, {key: logged[key] for key in decision})
        self.assertIn(
            {"source_id": "antrag-dienstreisegenehmigung.pdf"}, logged["evidence"]
        )
        # Even the fallback prediction must still be well-formed JSON.
        json.dumps(decision, ensure_ascii=False)
        # Chain is unbroken: every event but the first has a parent among
        # the previously logged events.
        self.assertIsNone(entries[0]["parent_event_id"])
        logged_ids = {entry["event_id"] for entry in entries}
        for entry in entries[1:]:
            self.assertIn(entry["parent_event_id"], logged_ids)


class ExpenseReimbursementAndProcurementTest(unittest.TestCase):
    """Covers the expense-reimbursement (auslagenerstattung-XX) and procurement
    (beschaffungsantrag-XX) case types, alongside the business-trip
    (dienstreiseantrag-XX) coverage in BaselineTest above."""

    def test_case_type_is_derived_from_the_directory_name_prefix(self):
        self.assertEqual("business_trip", case_type_for("dienstreiseantrag-01"))
        self.assertEqual("expense_reimbursement", case_type_for("auslagenerstattung-01"))
        self.assertEqual("procurement", case_type_for("beschaffungsantrag-01"))
        with self.assertRaises(ValueError):
            case_type_for("unbekannter-antrag-01")

    def test_lists_all_expense_reimbursement_cases(self):
        self.assertEqual(
            input_cases(EXPENSE_DATASET),
            [f"auslagenerstattung-0{index}" for index in range(1, 9)],
        )

    def test_lists_all_procurement_cases(self):
        self.assertEqual(
            input_cases(PROCUREMENT_DATASET),
            [f"beschaffungsantrag-0{index}" for index in range(1, 9)],
        )

    def test_reads_expense_reimbursement_documents(self):
        case_id = "auslagenerstattung-01"
        listed = json.loads(ListCaseDocumentsTool(EXPENSE_DATASET, case_id)(case_id))
        self.assertEqual(1, len(listed))
        text = ReadPdfTool(EXPENSE_DATASET, case_id)(case_id, "rechnung-fachbuch.pdf")
        self.assertIn("Utrecht", text)

    def test_reads_procurement_documents(self):
        case_id = "beschaffungsantrag-01"
        listed = json.loads(ListCaseDocumentsTool(PROCUREMENT_DATASET, case_id)(case_id))
        self.assertEqual(5, len(listed))
        text = ReadPdfTool(PROCUREMENT_DATASET, case_id)(case_id, "vergabevermerk.pdf")
        self.assertIn("Vergabevermerk", text)

    def test_policy_lookup_is_scoped_to_the_case_type(self):
        expense_policy = json.loads(
            LookupPolicyTool(EXPENSE_REIMBURSEMENT_POLICIES)("Kassenbon Beleg")
        )
        self.assertIn("proof_of_purchase", expense_policy["policies"])
        self.assertNotIn("framework_contracts", expense_policy["policies"])

        procurement_policy = json.loads(
            LookupPolicyTool(PROCUREMENT_POLICIES)("Rahmenvertrag WPS")
        )
        self.assertIn("framework_contracts", procurement_policy["policies"])
        self.assertNotIn("proof_of_purchase", procurement_policy["policies"])

    def test_builds_expense_reimbursement_evidence_with_matching_policies(self):
        evidence = build_case_evidence(EXPENSE_DATASET, "auslagenerstattung-01")
        self.assertIn("rechnung-fachbuch.pdf", evidence["documents"])
        self.assertTrue(evidence["document_completeness_check"]["complete"])
        self.assertIn("proof_of_purchase", evidence["policies"]["policies"])

    def test_builds_procurement_evidence_with_matching_policies(self):
        evidence = build_case_evidence(PROCUREMENT_DATASET, "beschaffungsantrag-01")
        self.assertIn("vergabevermerk.pdf", evidence["documents"])
        self.assertTrue(evidence["document_completeness_check"]["complete"])
        self.assertIn("framework_contracts", evidence["policies"]["policies"])

    def test_decides_an_expense_reimbursement_case_from_preloaded_evidence(self):
        class FakeModel:
            def generate(self, messages, **_kwargs):
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "antrag": "auslagenerstattung-01",
                            "result": "angenommen",
                            "begruendung": "Rechnung ist vollstaendig und an die Universitaet adressiert.",
                        }
                    ),
                    raw=None,
                )

        import contextlib
        import io

        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("auslagenerstattung-01"), model_context("gpt-oss-20b"):
                decision = decide_case(EXPENSE_DATASET, "auslagenerstattung-01", FakeModel())
        self.assertEqual("angenommen", decision["result"])

    def test_decides_a_procurement_case_from_preloaded_evidence(self):
        class FakeModel:
            def generate(self, messages, **_kwargs):
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "antrag": "beschaffungsantrag-01",
                            "result": "angenommen",
                            "begruendung": "Drei Vergleichsangebote liegen vor, das guenstigste wurde beauftragt.",
                        }
                    ),
                    raw=None,
                )

        import contextlib
        import io

        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("beschaffungsantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case(PROCUREMENT_DATASET, "beschaffungsantrag-01", FakeModel())
        self.assertEqual("angenommen", decision["result"])


class EventLoggingTest(unittest.TestCase):
    def test_logs_one_json_object_per_call_with_the_documented_fields(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message * 2

        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            with case_context("dienstreiseantrag-07"), model_context("gpt-oss-20b"):
                result = tool.forward(message="hi")

        self.assertEqual("hihi", result)
        entry = self._single_json_line(output)
        self.assertEqual(
            {
                "case_id",
                "event_id",
                "parent_event_id",
                "timestamp",
                "event_type",
                "model",
                "tool",
                "input",
                "output",
                "status",
                "error",
            },
            set(entry),
        )
        self.assertEqual("dienstreiseantrag-07", entry["case_id"])
        self.assertEqual("tool_call", entry["event_type"])
        self.assertEqual("gpt-oss-20b", entry["model"])
        self.assertEqual("echo", entry["tool"])
        self.assertEqual({"message": "hi"}, entry["input"])
        self.assertEqual("hihi", entry["output"])
        self.assertEqual("ok", entry["status"])
        self.assertIsNone(entry["error"])

    def test_logs_errors_without_swallowing_them(self):
        class FailingTool:
            name = "fails"

            def forward(self) -> str:
                raise ValueError("boom")

        tool = log_tool_calls(FailingTool())
        with self._capture_stdout() as output:
            with self.assertRaises(ValueError):
                tool.forward()

        entry = self._single_json_line(output)
        self.assertEqual("error", entry["status"])
        self.assertEqual("boom", entry["error"])
        self.assertIsNone(entry["output"])

    def test_defaults_to_placeholder_context_and_model_outside_any_context(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            tool.forward(message="hi")

        entry = self._single_json_line(output)
        self.assertEqual("-", entry["case_id"])
        self.assertEqual("-", entry["model"])

    def test_truncates_long_string_inputs_and_outputs(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        long_text = "x" * 500
        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            tool.forward(message=long_text)

        entry = self._single_json_line(output)
        self.assertLessEqual(len(entry["input"]["message"]), 200)
        self.assertTrue(entry["input"]["message"].endswith("…"))
        self.assertLessEqual(len(entry["output"]), 200)

    def test_keeps_small_structured_inputs_as_native_json(self):
        class ChecksTool:
            name = "check_facts"

            def forward(self, facts: dict) -> str:
                return json.dumps(facts)

        tool = log_tool_calls(ChecksTool())
        with self._capture_stdout() as output:
            tool.forward(facts={"kind": "overlap", "left": ["a"], "right": ["a"]})

        entry = self._single_json_line(output)
        self.assertEqual(
            {"kind": "overlap", "left": ["a"], "right": ["a"]}, entry["input"]["facts"]
        )

    def test_log_to_file_writes_gzip_compressed_jsonl_lines_instead_of_stdout(self):
        import gzip
        import tempfile

        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        tool = log_tool_calls(EchoTool())
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run-trace.jsonl.log.gz"
            with self._capture_stdout() as output:
                with log_to_file(log_path):
                    tool.forward(message="hi")
                    tool.forward(message="ho")
                tool.forward(message="outside")

            stdout_lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
            self.assertEqual(["outside"], [line["input"]["message"] for line in stdout_lines])
            with gzip.open(log_path, "rt", encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(["hi", "ho"], [line["input"]["message"] for line in lines])

    @staticmethod
    def _capture_stdout():
        import contextlib
        import io

        return contextlib.redirect_stdout(io.StringIO())

    def _single_json_line(self, output) -> dict:
        lines = [line for line in output.getvalue().splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        return json.loads(lines[0])


class CaseEventLoggingIntegrationTest(unittest.TestCase):
    def test_build_case_evidence_logs_one_jsonl_line_per_tool_call_with_a_causal_chain(self):
        import contextlib
        import io

        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                build_case_evidence(DATASET, "dienstreiseantrag-01")

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        self.assertTrue(entries)
        for entry in entries:
            self.assertEqual("dienstreiseantrag-01", entry["case_id"])
            self.assertEqual("ok", entry["status"])
            self.assertEqual("tool_call", entry["event_type"])
            self.assertEqual("gpt-oss-20b", entry["model"])
        logged_tools = {entry["tool"] for entry in entries}
        self.assertEqual(
            {"list_case_documents", "read_pdf", "search_case", "lookup_policy", "check_facts"},
            logged_tools,
        )
        self.assertIsNone(entries[0]["parent_event_id"])
        logged_ids = {entry["event_id"] for entry in entries}
        for entry in entries[1:]:
            self.assertIn(entry["parent_event_id"], logged_ids)


def _blank_pdf() -> bytes:
    """A valid one-page PDF without a text layer, like an image-only scan."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


class _HTTPError(Exception):
    """Stands in for an openai.APIStatusError: a message and a status_code."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _decision_json(case_id: str, result: str = "abgelehnt", reason: str = "Begruendung.") -> str:
    return json.dumps({"antrag": case_id, "result": result, "begruendung": reason})


def _capture_events(function, *args, **kwargs):
    import contextlib
    import io

    reset_state()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
            result = function(*args, **kwargs)
    entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    return result, entries


class RobustnessTest(unittest.TestCase):
    MESSAGES = [{"role": "user", "content": "Pruefe den Antrag."}]

    # Item 3: max_tokens fits the context; one retry on a context-length error.
    def test_output_token_budget_fits_the_context(self):
        small = [{"role": "user", "content": "x" * 3000}]
        self.assertEqual(16384, output_token_budget(small, 16384))

        large = [{"role": "user", "content": "x" * 60000}]
        budget = output_token_budget(large, 16384)
        self.assertLess(budget, 16384)
        self.assertLessEqual(estimate_prompt_tokens(large) + budget, MODEL_CONTEXT_TOKENS)

        huge = [{"role": "user", "content": "x" * 200000}]
        self.assertEqual(MIN_OUTPUT_TOKENS, output_token_budget(huge, 16384))
        self.assertEqual(1000, output_token_budget(huge, 1000))

    def test_retries_once_with_fewer_tokens_after_a_context_length_error(self):
        class ContextModel:
            def __init__(self):
                self.max_tokens = []

            def generate(self, messages, max_tokens=None, **_kwargs):
                self.max_tokens.append(max_tokens)
                if len(self.max_tokens) == 1:
                    raise _HTTPError(
                        400,
                        "This model's maximum context length is 32768 tokens. However, you "
                        "requested 40000 tokens (23616 in the messages, 16384 in the "
                        "completion).",
                    )
                return SimpleNamespace(content="ok", raw=None)

        model = ContextModel()
        content, entries = _capture_events(
            call_model, model, self.MESSAGES, time.monotonic() + 100, 16384
        )
        self.assertEqual("ok", content)
        self.assertEqual(16384, model.max_tokens[0])
        self.assertEqual(32768 - 23616 - 64, model.max_tokens[1])
        self.assertEqual(["error", "ok"], [entry["status"] for entry in entries])

    def test_a_second_context_length_error_is_raised(self):
        class AlwaysTooLong:
            calls = 0

            def generate(self, messages, **_kwargs):
                AlwaysTooLong.calls += 1
                raise _HTTPError(400, "'max_tokens' or 'max_completion_tokens' is too large")

        with self.assertRaises(_HTTPError):
            _capture_events(call_model, AlwaysTooLong(), self.MESSAGES, time.monotonic() + 100)
        self.assertEqual(2, AlwaysTooLong.calls)

    # Item 2, tested alongside: transient errors are retried within the deadline.
    def test_retries_a_transient_error_instead_of_failing(self):
        class OverloadedOnce:
            calls = 0

            def generate(self, messages, timeout=None, **_kwargs):
                OverloadedOnce.calls += 1
                self.timeout = timeout
                if OverloadedOnce.calls == 1:
                    raise _HTTPError(503, "Service Unavailable")
                return SimpleNamespace(content="ok", raw=None)

        model = OverloadedOnce()
        with mock.patch("predict.time.sleep") as sleep:
            content, _ = _capture_events(call_model, model, self.MESSAGES, time.monotonic() + 100)
        self.assertEqual("ok", content)
        self.assertEqual(2, OverloadedOnce.calls)
        sleep.assert_called_once()
        self.assertLessEqual(model.timeout, 100)

    def test_an_empty_answer_gets_the_second_attempt(self):
        class EmptyThenValid:
            calls = 0

            def generate(self, messages, **_kwargs):
                EmptyThenValid.calls += 1
                if EmptyThenValid.calls == 1:
                    return SimpleNamespace(content="", raw=None)
                return SimpleNamespace(
                    content='{"antrag":"x","result":"angenommen","begruendung":"Alles belegt."}',
                    raw=None,
                )

        decision, _ = _capture_events(decide_case, DATASET, "dienstreiseantrag-01", EmptyThenValid())
        self.assertEqual("angenommen", decision["result"])
        self.assertEqual(2, EmptyThenValid.calls)

    def test_a_long_connection_outage_is_retried_until_the_deadline(self):
        import openai

        class DownForEightCalls:
            calls = 0

            def generate(self, messages, **_kwargs):
                DownForEightCalls.calls += 1
                if DownForEightCalls.calls <= 8:
                    raise openai.APIConnectionError(request=mock.Mock())
                return SimpleNamespace(content="ok", raw=None)

        with mock.patch("predict.time.sleep"):
            content, _ = _capture_events(
                call_model, DownForEightCalls(), self.MESSAGES, time.monotonic() + 250
            )
        self.assertEqual("ok", content)
        self.assertEqual(9, DownForEightCalls.calls)

    def test_does_not_call_the_model_after_the_case_deadline(self):
        class NeverCalled:
            def generate(self, messages, **_kwargs):
                raise AssertionError("must not be called")

        with self.assertRaises(TimeoutError):
            _capture_events(call_model, NeverCalled(), self.MESSAGES, time.monotonic())

    # Item 4: an image-only or damaged PDF does not crash the case.
    def test_case_with_an_image_only_pdf_still_builds_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "dienstreiseantrag-01"
            case.mkdir()
            shutil.copy(DATASET / "dienstreiseantrag-01" / "antrag-dienstreisegenehmigung.pdf", case)
            (case / "scan.pdf").write_bytes(_blank_pdf())
            (case / "kaputt.pdf").write_bytes(b"not a pdf")
            evidence, entries = _capture_events(build_case_evidence, Path(tmp), case.name)
        self.assertEqual(["kaputt.pdf", "scan.pdf"], evidence["documents_without_text"])
        self.assertEqual(NO_TEXT_NOTE, evidence["documents"]["scan.pdf"])
        self.assertIn("nicht gelesen", evidence["documents"]["kaputt.pdf"])
        self.assertIn("Ahlgrim", evidence["documents"]["antrag-dienstreisegenehmigung.pdf"])
        failed = [entry for entry in entries if entry["status"] == "error"]
        self.assertEqual(["read_pdf"], [entry["tool"] for entry in failed])

    def test_normal_case_evidence_has_no_documents_without_text(self):
        evidence, _ = _capture_events(build_case_evidence, DATASET, "dienstreiseantrag-01")
        self.assertNotIn("documents_without_text", evidence)

    # Item 5: every case directory gets exactly one prediction line.
    def test_every_case_directory_gets_exactly_one_prediction_line(self):
        import gzip

        import predict

        class FakeModel:
            def generate(self, messages, **_kwargs):
                if "auslagenerstattung-01" in messages[1]["content"]:
                    raise RuntimeError("model crashed")
                return SimpleNamespace(
                    content=_decision_json("dienstreiseantrag-XX", "angenommen", "Passt."),
                    raw=None,
                    token_usage=SimpleNamespace(input_tokens=1234, output_tokens=56),
                )

        with tempfile.TemporaryDirectory() as tmp:
            inputs = Path(tmp) / "inputs"
            (inputs / "dienstreiseantrag-01").mkdir(parents=True)  # no PDFs
            (inputs / "beschaffungsantrag-02").mkdir()
            (inputs / "beschaffungsantrag-02" / "scan.pdf").write_bytes(_blank_pdf())
            (inputs / "auslagenerstattung-01").mkdir()  # model raises
            (inputs / "sonderantrag-01").mkdir()  # unknown type, holds a PDF
            (inputs / "sonderantrag-01" / "scan.pdf").write_bytes(_blank_pdf())
            (inputs / "retrieval-corpora" / "de").mkdir(parents=True)
            (inputs / "retrieval-corpora" / "de" / "documents.jsonl.gz").write_bytes(b"")
            output = Path(tmp) / "output"
            environment = {
                "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                "OPENAI_API_KEY": "test-not-a-key",
                "OPENAI_MODEL": "fake-model",
            }
            argv = ["predict.py", "--input", str(inputs), "--output", str(output)]
            with mock.patch.dict(os.environ, environment), mock.patch.object(
                sys, "argv", argv
            ), mock.patch.object(predict, "OpenAIModel", lambda **_kwargs: FakeModel()), mock.patch(
                "sys.stderr"
            ):
                predict.main()

            lines = (output / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
            with gzip.open(output / "run-trace.jsonl.log.gz", "rt", encoding="utf-8") as handle:
                events = [json.loads(line) for line in handle if line.strip()]

        predictions = [json.loads(line) for line in lines]
        self.assertEqual(
            [
                "auslagenerstattung-01",
                "beschaffungsantrag-02",
                "dienstreiseantrag-01",
                "sonderantrag-01",
            ],
            [prediction["antrag"] for prediction in predictions],
        )
        results = {prediction["antrag"]: prediction["result"] for prediction in predictions}
        self.assertEqual("angenommen", results["dienstreiseantrag-01"])
        self.assertEqual("angenommen", results["beschaffungsantrag-02"])
        self.assertEqual("abgelehnt", results["auslagenerstattung-01"])
        self.assertEqual("abgelehnt", results["sonderantrag-01"])
        for case_id in results:
            case_events = [event for event in events if event["case_id"] == case_id]
            self.assertEqual("decision", case_events[-1]["event_type"])
            self.assertEqual(
                1, sum(event["event_type"] == "decision" for event in case_events)
            )
            self.assertTrue(all(event["model"] == "fake-model" for event in case_events))

    # Item 6: a wrong or missing antrag is overwritten with the case id.
    def test_wrong_or_missing_antrag_is_replaced_by_the_case_id(self):
        wrong = _decision_json("dienstreiseantrag-XX")
        self.assertEqual("dienstreiseantrag-01", parse_decision(wrong, "dienstreiseantrag-01")["antrag"])
        missing = json.dumps({"result": "angenommen", "begruendung": "Alles belegt."})
        decision = parse_decision(missing, "dienstreiseantrag-01")
        self.assertEqual("dienstreiseantrag-01", decision["antrag"])
        self.assertEqual("angenommen", decision["result"])

    # Item 7: model_call and decision events are logged in full, with token usage.
    def test_logs_full_prompt_response_token_usage_and_reason(self):
        long_reason = "Der Antrag ist vollstaendig belegt. " * 20

        class VerboseModel:
            def generate(self, messages, **_kwargs):
                return SimpleNamespace(
                    content=_decision_json("dienstreiseantrag-01", "angenommen", long_reason),
                    raw=SimpleNamespace(
                        usage=SimpleNamespace(
                            model_dump=lambda **_kwargs: {
                                "prompt_tokens": 6000,
                                "completion_tokens": 700,
                                "total_tokens": 6700,
                            }
                        )
                    ),
                )

        _, entries = _capture_events(decide_case, DATASET, "dienstreiseantrag-01", VerboseModel())
        model_call = next(entry for entry in entries if entry["event_type"] == "model_call")
        messages = model_call["input"]["messages"]
        self.assertEqual(["system", "user"], [message["role"] for message in messages])
        self.assertGreater(len(messages[1]["content"]), 5000)
        self.assertIn("EVIDENCE_JSON", messages[1]["content"])
        self.assertEqual(16384, model_call["input"]["max_tokens"])
        self.assertEqual(
            _decision_json("dienstreiseantrag-01", "angenommen", long_reason),
            model_call["output"]["response"],
        )
        self.assertEqual(6700, model_call["output"]["token_usage"]["total_tokens"])

        decision = entries[-1]
        self.assertEqual("decision", decision["event_type"])
        self.assertEqual(long_reason.strip(), decision["output"]["begruendung"])
        self.assertEqual("angenommen", decision["output"]["result"])
        self.assertIn(
            {"source_id": "bahn-rechnung-kassel-leipzig.pdf"}, decision["output"]["evidence"]
        )
        for entry in entries:
            self.assertEqual(
                {
                    "case_id",
                    "event_id",
                    "parent_event_id",
                    "timestamp",
                    "event_type",
                    "model",
                    "tool",
                    "input",
                    "output",
                    "status",
                    "error",
                },
                set(entry),
            )


class SalvageDecisionTest(unittest.TestCase):
    def test_missing_closing_quote_is_recovered(self):
        broken = '{"antrag":"beschaffungsantrag-01","result":"angenommen","begruendung":"Alle Kriterien sind erfüllt.}'
        decision = parse_decision(broken, "beschaffungsantrag-01")
        self.assertEqual(decision["result"], "angenommen")
        self.assertEqual(decision["begruendung"], "Alle Kriterien sind erfüllt.")

    def test_trailing_fields_after_reason_are_dropped(self):
        broken = '{"result":"abgelehnt","begruendung":"Drei Angebote fehlen.", "extra": 1'
        decision = parse_decision(broken, "beschaffungsantrag-02")
        self.assertEqual(decision["result"], "abgelehnt")
        self.assertEqual(decision["begruendung"], "Drei Angebote fehlen.")

    def test_text_without_a_label_still_fails(self):
        with self.assertRaises(ValueError):
            parse_decision('{"begruendung":"unklar', "beschaffungsantrag-03")


if __name__ == "__main__":
    unittest.main()
