from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check-mypy-baseline.py"
SPEC = importlib.util.spec_from_file_location("check_mypy_baseline", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
check_mypy_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_mypy_baseline)


class MypyBaselineGateTests(unittest.TestCase):
    def _baseline_file(self, errors: Counter[tuple[str, str, str]]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "baseline.json"
        path.write_text(
            json.dumps(check_mypy_baseline.baseline_payload(errors)),
            encoding="utf-8",
        )
        return path

    def _run_main(
        self,
        *,
        baseline: Counter[tuple[str, str, str]],
        result: subprocess.CompletedProcess[str],
    ) -> int:
        actual, unparsed = check_mypy_baseline.parse_mypy_diagnostics(result)
        baseline_path = self._baseline_file(baseline)
        with (
            patch.object(
                check_mypy_baseline,
                "run_mypy",
                return_value=(result, actual, unparsed),
            ),
            patch.object(sys, "argv", [str(SCRIPT_PATH), "--baseline", str(baseline_path)]),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            return check_mypy_baseline.main()

    def test_parser_counts_exact_fingerprints_and_allows_notes(self) -> None:
        result = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=(
                "app/example.py:10: error: Incompatible types  [assignment]\n"
                "app/example.py:11: note: The assignment is declared here\n"
                "app/example.py:12: error: Incompatible types  [assignment]\n"
            ),
            stderr="",
        )

        actual, unparsed = check_mypy_baseline.parse_mypy_diagnostics(result)

        self.assertEqual(
            actual,
            Counter({("app/example.py", "assignment", "Incompatible types"): 2}),
        )
        self.assertEqual(unparsed, [])

    def test_exit_one_with_unparseable_output_fails_closed(self) -> None:
        result = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout="mypy changed its diagnostic format\n",
            stderr="",
        )

        self.assertEqual(self._run_main(baseline=Counter(), result=result), 2)

    def test_retired_baseline_allowance_must_be_removed(self) -> None:
        fingerprint = ("app/example.py", "assignment", "Incompatible types")
        result = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout="app/example.py:10: error: Incompatible types  [assignment]\n",
            stderr="",
        )

        self.assertEqual(self._run_main(baseline=Counter({fingerprint: 2}), result=result), 1)

    def test_exact_fingerprint_counts_pass(self) -> None:
        fingerprint = ("app/example.py", "assignment", "Incompatible types")
        result = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=(
                "app/example.py:10: error: Incompatible types  [assignment]\n"
                "app/example.py:12: error: Incompatible types  [assignment]\n"
            ),
            stderr="",
        )

        self.assertEqual(self._run_main(baseline=Counter({fingerprint: 2}), result=result), 0)

    def test_increased_fingerprint_count_fails(self) -> None:
        fingerprint = ("app/example.py", "assignment", "Incompatible types")
        result = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=(
                "app/example.py:10: error: Incompatible types  [assignment]\n"
                "app/example.py:12: error: Incompatible types  [assignment]\n"
            ),
            stderr="",
        )

        self.assertEqual(self._run_main(baseline=Counter({fingerprint: 1}), result=result), 1)


if __name__ == "__main__":
    unittest.main()
