"""TIRA safety (R15): input layouts and answers that must not lose a case."""
import tempfile
import unittest
from pathlib import Path

from case_tools import case_pdfs, case_type_for
from predict import case_root, fit_evidence, input_cases, parse_decision, decision_prompt, MODEL_CONTEXT_TOKENS


class AnswerTest(unittest.TestCase):
    def test_labels_and_keys_in_other_spellings(self):
        for answer, label in [('{"result": "Angenommen", "begruendung": "ok"}', "angenommen"),
                              ('{"result": "abgelehnt.", "begründung": "fehlt"}', "abgelehnt"),
                              ('{"result": "accepted", "reason": "fine"}', "angenommen"),
                              ('{"result": "abgelehnt"}', "abgelehnt"),
                              ('Text {"result": "angenommen", "begruendung": "x"} {"result": "angenommen|abgelehnt"}', "angenommen")]:
            with self.subTest(answer=answer):
                self.assertEqual(parse_decision(answer, "c-1")["result"], label)

    def test_unknown_label_still_fails(self):
        with self.assertRaises(ValueError):
            parse_decision('{"result": "vielleicht", "begruendung": "x"}', "c-1")


class InputTest(unittest.TestCase):
    def test_nested_cases_and_uppercase_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "inputs" / "dienstreiseantrag-91"
            case.mkdir(parents=True)
            (case / "ANTRAG.PDF").write_bytes(b"%PDF-1.4")
            root = case_root(Path(tmp))
            self.assertEqual(root.name, "inputs")
            self.assertEqual(input_cases(root), ["dienstreiseantrag-91"])
            self.assertEqual([p.name for p in case_pdfs(case)], ["ANTRAG.PDF"])

    def test_case_type_spellings(self):
        self.assertEqual(case_type_for("Beschaffungsantrag-91"), "procurement")
        self.assertEqual(case_type_for("reisekostenantrag_7"), "business_trip")


class ModelTest(unittest.TestCase):
    def test_unknown_model_name_gets_the_strict_closing(self):
        import os
        import predict
        old = os.environ.get("OPENAI_MODEL")
        try:
            for name, gpt in [("openai/gpt-oss-120b", True), ("Qwen/Qwen2.5-7B-Instruct", False), ("model-c", False)]:
                os.environ["OPENAI_MODEL"] = name
                self.assertEqual(predict.is_gpt_oss(), gpt, name)
                self.assertEqual("lehne ab, statt" in predict.system_prompt_for("procurement"), not gpt, name)
        finally:
            if old is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = old

    def test_timeout_retry_is_short(self):
        import time
        import predict

        class Slow:
            calls = []

            def generate(self, messages, max_tokens, timeout):
                self.calls.append((messages[-1]["content"][-20:], max_tokens, timeout))
                if len(self.calls) == 1:
                    raise TimeoutError("Request timed out.")
                class R:
                    content = '{"result": "angenommen", "begruendung": "ok"}'
                    raw = None
                return R()

        model = Slow()
        out = predict.call_model(model, [{"role": "user", "content": "Prüfe."}], time.monotonic() + 270, 16384)
        self.assertIn("angenommen", out)
        self.assertEqual(model.calls[0][2], predict.FIRST_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(model.calls[1][1], predict.SHORT_RETRY_MAX_TOKENS)
        self.assertIn("JSON-Objekt.", model.calls[1][0])


class FitTest(unittest.TestCase):
    def test_long_case_is_cut_to_fit(self):
        evidence = {"case_id": "dienstreiseantrag-91", "documents": {"a.pdf": "x " * 60000, "b.pdf": "kurz"},
                    "amounts_by_document": {}, "search_results": ["y" * 5000], "policies": {}}
        fitted = fit_evidence(evidence, 6000)
        self.assertLess(len(decision_prompt(fitted)) / 2.5 + 6000 / 2.5, MODEL_CONTEXT_TOKENS - 8000)
        self.assertIn("gekürzt", fitted["documents"]["a.pdf"])
        self.assertEqual(fitted["documents"]["b.pdf"], "kurz")

    def test_normal_case_unchanged(self):
        evidence = {"case_id": "dienstreiseantrag-91", "documents": {"a.pdf": "kurz"}, "amounts_by_document": {},
                    "search_results": [], "policies": {}}
        self.assertIs(fit_evidence(evidence, 6000), evidence)


if __name__ == "__main__":
    unittest.main()


class EvidenceSmokeTest(unittest.TestCase):
    """build_case_evidence must run end to end on a real case (R22e: a missing
    import made every case fall back, and no unit test called this path)."""

    def test_practice_case_builds_evidence_with_facts(self):
        from predict import build_case_evidence
        root = Path.home() / "dev/uniagent-code/cikm26/datasets/task-2-expense-reimbursement-spot-check/inputs"
        evidence = build_case_evidence(root, "auslagenerstattung-01")
        self.assertTrue(evidence["documents"])
        self.assertTrue(evidence["facts_by_code"])
        self.assertNotIn("documents_without_text", evidence)
