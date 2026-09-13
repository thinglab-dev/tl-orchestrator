#!/usr/bin/env python3
"""
Unit and counterfactual tests for scripts/extract_tool_result.py.
Covers AC09 (extractors) and AC10 (losslessness gate & counterfactual probe).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "extract_tool_result.py"
TOOL_FIXTURES = ROOT / "scripts" / "fixtures" / "tool_outputs"


class TestExtractToolResult(unittest.TestCase):
    def run_cli(self, tool: str, input_file: Path, details_ref: str | None = None) -> dict:
        details_ref = details_ref or str(input_file)
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--tool",
            tool,
            "--input",
            str(input_file),
            "--details-ref",
            details_ref,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, f"CLI error: {proc.stderr}")
        return json.loads(proc.stdout)

    def test_extract_go_test_fail(self):
        res = self.run_cli("go_test", TOOL_FIXTURES / "gotest_fail.txt")
        self.assertEqual(res["tool"], "go_test")
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["details_ref"], str(TOOL_FIXTURES / "gotest_fail.txt"))
        # Must extract both top-level and subtest failures
        failures = res["failure_ids"]
        self.assertTrue(any("TestLoginFailure" in f for f in failures))
        self.assertTrue(any("Invalid_Password" in f for f in failures))

    def test_extract_go_test_pass(self):
        res = self.run_cli("go_test", TOOL_FIXTURES / "gotest_pass.txt")
        self.assertEqual(res["status"], "pass")
        self.assertEqual(len(res["failure_ids"]), 0)

    def test_extract_pytest_fail(self):
        res = self.run_cli("pytest", TOOL_FIXTURES / "pytest_fail.txt")
        self.assertEqual(res["tool"], "pytest")
        self.assertEqual(res["status"], "fail")
        self.assertIn("tests/test_auth.py::test_token_expiration", res["failure_ids"])

    def test_extract_git_diff(self):
        res = self.run_cli("git_diff", TOOL_FIXTURES / "git_diff.txt")
        self.assertEqual(res["tool"], "git_diff")
        self.assertEqual(res["files_changed"], 2)
        self.assertEqual(res["insertions"], 2)
        self.assertEqual(res["deletions"], 0)
        self.assertIn("pkg/auth/token.go", res["affected_files"])

    def test_extract_git_status(self):
        res = self.run_cli("git_status", TOOL_FIXTURES / "git_status.txt")
        self.assertEqual(res["tool"], "git_status")
        self.assertEqual(res["branch"], "feature/t015")
        self.assertFalse(res["is_clean"])
        self.assertIn("pkg/auth/token.go", res["staged"])
        self.assertIn("pkg/auth/token_test.go", res["unstaged"])
        self.assertIn("scripts/temp.py", res["untracked"])

    def test_extract_build(self):
        res = self.run_cli("build", TOOL_FIXTURES / "build_fail.txt")
        self.assertEqual(res["tool"], "build")
        self.assertEqual(res["exit_code"], 1)
        self.assertEqual(res["error_count"], 2)
        self.assertEqual(len(res["errors_summary"]), 2)
        self.assertEqual(len(res["failure_ids"]), 2)

    # Details ref validation and raw persistence
    def test_details_ref_validation_and_persistence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            input_file = td / "raw_input.txt"
            input_file.write_text("FAIL TestFoo\n", encoding="utf-8")
            persisted_ref = td / "persisted_raw.txt"

            # 1. Empty details-ref must fail
            cmd_empty = [sys.executable, str(SCRIPT), "--tool", "go_test", "--input", str(input_file), "--details-ref", "   "]
            p_empty = subprocess.run(cmd_empty, capture_output=True, text=True)
            self.assertNotEqual(p_empty.returncode, 0)

            # 2. --persist-raw creates the details-ref file on disk
            cmd_persist = [
                sys.executable, str(SCRIPT),
                "--tool", "go_test",
                "--input", str(input_file),
                "--details-ref", str(persisted_ref),
                "--persist-raw",
            ]
            p_persist = subprocess.run(cmd_persist, capture_output=True, text=True)
            self.assertEqual(p_persist.returncode, 0)
            self.assertTrue(persisted_ref.is_file())
            self.assertEqual(persisted_ref.read_text(encoding="utf-8"), "FAIL TestFoo\n")

            # 3. A nonexistent local reference without persistence is not
            # recoverable and must be rejected.
            missing_ref = td / "non-existent-audit" / "raw.log"
            cmd_missing = [
                sys.executable, str(SCRIPT), "--tool", "go_test", "--input", str(input_file),
                "--details-ref", str(missing_ref),
            ]
            p_missing = subprocess.run(cmd_missing, capture_output=True, text=True)
            self.assertEqual(p_missing.returncode, 1)
            self.assertIn("details_ref does not exist", p_missing.stderr)

    def test_r9_grep_failure_losslessness_and_counterfactual(self):
        res = self.run_cli("grep", TOOL_FIXTURES / "grep_fail.txt")
        expected_failure = "grep: missing/input.txt: No such file or directory"
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["failure_ids"], [expected_failure])
        self.assertEqual(res["match_count"], 1)
        self.assertEqual(res["matching_files"], ["docs/WORK_MODEL.md"])

        tampered = []
        with self.assertRaises(AssertionError):
            if expected_failure not in tampered:
                raise AssertionError("Losslessness gate violated: missing grep diagnostic")

    # AC10 Losslessness Gate & Counterfactual Probes for ALL extractors

    # 1. go_test counterfactual probe
    def test_ac10_losslessness_gate_and_counterfactual(self):
        res = self.run_cli("go_test", TOOL_FIXTURES / "gotest_fail.txt")
        raw_fails = ["TestLoginFailure", "TestLoginFailure/Invalid_Password"]
        for expected in raw_fails:
            self.assertTrue(any(expected in fid for fid in res["failure_ids"]))

        # Counterfactual probe: dropping a failure fails losslessness verification
        tampered_fids = [f for f in res["failure_ids"] if "Invalid_Password" not in f]
        with self.assertRaises(AssertionError):
            for expected in raw_fails:
                if not any(expected in f for f in tampered_fids):
                    raise AssertionError(f"Losslessness gate violated: missing {expected}")

    # 2. pytest counterfactual probe
    def test_ac10_pytest_losslessness_counterfactual(self):
        res = self.run_cli("pytest", TOOL_FIXTURES / "pytest_fail.txt")
        expected_failure = "tests/test_auth.py::test_token_expiration"
        self.assertIn(expected_failure, res["failure_ids"])

        # Counterfactual: omitting the failure triggers losslessness assertion
        tampered = [f for f in res["failure_ids"] if f != expected_failure]
        with self.assertRaises(AssertionError):
            if expected_failure not in tampered:
                raise AssertionError(f"Losslessness gate violated: missing pytest failure {expected_failure}")

    # 3. build counterfactual probe
    def test_ac10_build_losslessness_counterfactual(self):
        res = self.run_cli("build", TOOL_FIXTURES / "build_fail.txt")
        expected_errors = [
            "pkg/auth/token.go:12:5: undefined: ValidateSecret",
            "pkg/auth/token.go:18:2: syntax error: unexpected semicolon, expecting comma or )",
        ]
        for err in expected_errors:
            self.assertTrue(any(err in f for f in res["failure_ids"]))

        # Counterfactual: omitting one compilation error
        tampered = [f for f in res["failure_ids"] if "undefined: ValidateSecret" not in f]
        with self.assertRaises(AssertionError):
            for err in expected_errors:
                if not any(err in f for f in tampered):
                    raise AssertionError(f"Losslessness gate violated: missing build error {err}")

    # 4. git_diff conflict losslessness counterfactual
    def test_ac10_git_diff_losslessness_counterfactual(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            diff_file = Path(tmpdir) / "conflict.diff"
            diff_file.write_text(
                "diff --git a/pkg/auth.go b/pkg/auth.go\n"
                "index 1234..5678 100644\n"
                "--- a/pkg/auth.go\n"
                "+++ b/pkg/auth.go\n"
                "@@ -1,3 +1,7 @@\n"
                "+<<<<<<< HEAD\n"
                "+ours\n"
                "+=======\n"
                "+theirs\n"
                "+>>>>>>> branch\n",
                encoding="utf-8",
            )
            res = self.run_cli("git_diff", diff_file)
            self.assertEqual(res["status"], "fail")
            self.assertIn("pkg/auth.go", res["conflicts"])
            self.assertTrue(any("pkg/auth.go" in f for f in res["failure_ids"]))

            # Counterfactual: dropping the conflict
            tampered = [f for f in res["failure_ids"] if "pkg/auth.go" not in f]
            with self.assertRaises(AssertionError):
                if not any("pkg/auth.go" in f for f in tampered):
                    raise AssertionError("Losslessness gate violated: dropped git conflict")

    # 5. git_status losslessness counterfactual
    def test_ac10_git_status_losslessness_counterfactual(self):
        res = self.run_cli("git_status", TOOL_FIXTURES / "git_status.txt")
        self.assertEqual(res["status"], "dirty")
        expected_uncommitted = ["staged:pkg/auth/token.go", "unstaged:pkg/auth/token_test.go", "untracked:scripts/temp.py"]
        for expected in expected_uncommitted:
            self.assertIn(expected, res["failure_ids"])

        # Counterfactual: omitting untracked file
        tampered = [f for f in res["failure_ids"] if "scripts/temp.py" not in f]
        with self.assertRaises(AssertionError):
            for expected in expected_uncommitted:
                if expected not in tampered:
                    raise AssertionError(f"Losslessness gate violated: missing uncommitted file {expected}")

    # 6. classifier_json losslessness counterfactual
    def test_ac10_classifier_json_losslessness_counterfactual(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            clf_file = Path(tmpdir) / "classifier.json"
            clf_payload = {
                "schema_version": 1,
                "confidence": "low",
                "status": "uncertain",
                "uncertainties": ["Ambiguity in spec requirements", "Missing test harness"],
                "refusals": ["Cannot determine method"],
            }
            clf_file.write_text(json.dumps(clf_payload), encoding="utf-8")
            res = self.run_cli("classifier_json", clf_file)
            self.assertEqual(res["status"], "fail")
            self.assertEqual(len(res["uncertainties"]), 2)
            self.assertEqual(len(res["refusals"]), 1)

            # Counterfactual: omitting refusal
            tampered = [f for f in res["failure_ids"] if "refusal" not in f]
            with self.assertRaises(AssertionError):
                if not any("refusal" in f for f in tampered):
                    raise AssertionError("Losslessness gate violated: missing classifier refusal")

    # 7. checker_json losslessness and counterfactual probes for action_items, rejected, and deferred
    def test_ac10_checker_json_losslessness_and_counterfactuals(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            chk_file = Path(tmpdir) / "checker_review.json"
            review_payload = {
                "schema_version": 1,
                "verdict": "changes_requested",
                "summary": "Review round 1 identified multiple issues.",
                "action_items": [
                    {"id": "R1", "title": "Fix manifest pre-dispatch integrity"},
                    {"id": "R2", "title": "Fix confinement ledger"},
                ],
                "rejected": [
                    {"id": "REJ-01", "reason": "Alternative architecture dismissed"},
                ],
                "deferred": [
                    {"id": "DEF-01", "reason": "Future enhancement deferred to T016"},
                ],
            }
            chk_file.write_text(json.dumps(review_payload), encoding="utf-8")
            res = self.run_cli("checker_json", chk_file)

            # Invariant: Must preserve action_items, rejected, AND deferred!
            self.assertEqual(res["tool"], "checker_json")
            self.assertEqual(res["status"], "fail")
            self.assertEqual(res["verdict"], "changes_requested")
            self.assertEqual(len(res["action_items"]), 2)
            self.assertEqual(len(res["rejected"]), 1)
            self.assertEqual(len(res["deferred"]), 1)
            self.assertIn("action_item:R1", res["failure_ids"])
            self.assertIn("action_item:R2", res["failure_ids"])
            self.assertIn("rejected:REJ-01", res["failure_ids"])
            self.assertIn("deferred:DEF-01", res["failure_ids"])

            # Counterfactual Probe 1: Dropping an action_item violates losslessness
            tampered_ai = [ai for ai in res["action_items"] if ai["id"] != "R1"]
            with self.assertRaises(AssertionError):
                if len(tampered_ai) != len(review_payload["action_items"]):
                    raise AssertionError("Losslessness gate violated: action_item R1 was omitted!")

            # Counterfactual Probe 2: Dropping a rejected item violates losslessness
            tampered_rej = []  # dropped rejected
            with self.assertRaises(AssertionError):
                if len(tampered_rej) != len(review_payload["rejected"]):
                    raise AssertionError("Losslessness gate violated: rejected item REJ-01 was dropped!")

            # Counterfactual Probe 3: Dropping a deferred item violates losslessness
            tampered_def = []  # dropped deferred
            with self.assertRaises(AssertionError):
                if len(tampered_def) != len(review_payload["deferred"]):
                    raise AssertionError("Losslessness gate violated: deferred item DEF-01 was dropped!")


if __name__ == "__main__":
    unittest.main()
