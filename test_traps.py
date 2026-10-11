"""Trap documents from the robustness audit (the development notes (not included)).

FALSE: a case that should pass; the named note must not fire.
MISS:  a broken case; the named note must fire.
FALSE?: the right label is unclear; not asserted.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "experiments" / "traps"))
import snippets  # noqa: E402
import snippets2  # noqa: E402,F401
import snippets3  # noqa: E402,F401
import snippets4  # noqa: E402,F401
from facts import compute_facts  # noqa: E402


class TrapTest(unittest.TestCase):
    def test_traps(self):
        for cid, _lik, kind, ctype, docs, want, why in snippets.CASES:
            if kind not in ("FALSE", "MISS"):
                continue
            with self.subTest(case=cid):
                notes = snippets.notes_of(compute_facts(ctype, docs))
                hit = [n for n in notes if want in n] if want else notes
                if kind == "FALSE":
                    self.assertFalse(hit, f"false note: {hit} ({why})")
                else:
                    self.assertTrue(hit, f"missed defect, notes: {notes} ({why})")


if __name__ == "__main__":
    unittest.main()
