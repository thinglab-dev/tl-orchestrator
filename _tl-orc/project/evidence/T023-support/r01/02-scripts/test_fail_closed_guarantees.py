#!/usr/bin/env python3
"""
test_fail_closed_guarantees.py
Unit and counterfactual tests proving fail-closed behaviors by directly importing and exercising
the actual runner functions from run_arms.py and run_evaluator.py (R5 and R7):
1. run_arm raises RuntimeError immediately if subprocess returncode != 0 and leaves target outputs directory non-existent (never creates it).
2. run_arm raises RuntimeError immediately if Arm B exceeds sub-budget (11 requests) and leaves target outputs directory non-existent.
3. run_arm does NOT modify or delete pre-existing files in target outputs directory on failure.
4. ArmTurnController blocks 11th request launch attempt for Arm B, proving launch prevention.
5. execute_decomposed_arm_turns dispatches exactly 10 requests and blocks the 11th before dispatch with integrated executor.
6. BudgetTracker pre-phase check blocks phase launch when projected requests or tokens exceed global caps (including downstream reservations).
7. run_evaluation raises RuntimeError immediately on exit code != 0, unblinds NO keys, and leaves target eval directory non-existent.
8. validate_and_extract_verdict raises RuntimeError if ```json code block is missing before unblinding.
9. validate_and_extract_verdict raises RuntimeError if JSON block is malformed before unblinding.
10. validate_and_extract_verdict raises RuntimeError if required keys (alpha, beta, comparative_verdict) are missing.
11. calculate_and_verify_global_budget accounts for all 7 request phases (=18) and all token phases, raising RuntimeError on request or token breaches.
12. Positive control: valid execution creates destination directories and writes all expected artifacts, proving falsifiability of negative tests.
13. Counterfactual transactional publication: run_arm publication failure rolls back and removes newly created target directory (R7).
14. Counterfactual transactional publication: run_arm publication failure preserves pre-existing target directory and files byte-by-byte (R7).
15. Counterfactual transactional publication: run_evaluator publication failure rolls back and removes newly created target directory (R7).
16. Counterfactual transactional publication: run_evaluator publication failure preserves pre-existing target directory and files byte-by-byte (R7).
17. Counterfactual rollback failure: run_arm publication failure with rmtree error reports incomplete rollback (R7).
18. Counterfactual rollback failure: run_arm publication failure with copy2 restoration error reports incomplete rollback (R7).
19. Counterfactual rollback failure: run_arm publication failure with unlink error reports incomplete rollback (R7).
20. Counterfactual rollback failure: run_evaluator publication failure with rmtree error reports incomplete rollback (R7).
21. Counterfactual rollback failure: run_evaluator publication failure with copy2 restoration error reports incomplete rollback (R7).
22. Counterfactual rollback failure: run_evaluator publication failure with unlink error reports incomplete rollback (R7).
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add script directory to sys.path to import runners directly
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_arms
import run_evaluator


class TestFailClosedGuarantees(unittest.TestCase):

    def test_run_arm_nonzero_exit_code_aborts_without_creating_target_dir(self):
        """Proof that run_arm raises RuntimeError and NEVER creates target directory on subprocess failure (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_arm_outputs"
            self.assertFalse(test_out_dir.exists())

            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = "Failure stdout"
            mock_proc.stderr = "Harness crash simulation"

            def mock_sub_run(*args, **kwargs):
                cmd = args[0]
                if "-o" in cmd:
                    out_file = Path(cmd[cmd.index("-o") + 1])
                    out_file.write_text("partial staged output before crash", encoding="utf-8")
                return mock_proc

            with patch("subprocess.run", side_effect=mock_sub_run):
                with self.assertRaises(RuntimeError) as ctx:
                    run_arms.run_arm(
                        "Arm_Test",
                        SCRIPT_DIR,
                        "dummy prompt",
                        outputs_dir=test_out_dir
                    )

                self.assertIn("FAIL-CLOSED: Arm_Test execution failed with exit code 1", str(ctx.exception))
                # Critical R7 check: verify that target destination directory was NEVER created
                self.assertFalse(test_out_dir.exists(), "Target directory was created despite subprocess failure!")

    def test_run_arm_b_sub_budget_breach_aborts_without_creating_target_dir(self):
        """Proof that run_arm aborts and NEVER creates target directory when Arm B exceeds sub-budget (R5/R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_arm_b"
            self.assertFalse(test_out_dir.exists())

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "session id: 11111111-2222-3333-4444-555555555555\nCompleted."
            mock_proc.stderr = ""

            dummy_session = Path(tmpdir) / "dummy-session.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            # Mock usage data returning 11 requests (counterfactual breach)
            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 11,
                    "semantic_per_response_sum": {
                        "input_tokens": 450000,
                        "cached_input_tokens": 300000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 7000,
                        "total_tokens": 457000
                    }
                }
            }

            def side_effect(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    return mock_proc
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    u_mock = MagicMock()
                    u_mock.returncode = 0
                    return u_mock

            with patch("subprocess.run", side_effect=side_effect):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with self.assertRaises(RuntimeError) as ctx:
                        run_arms.run_arm(
                            "Arm_B",
                            SCRIPT_DIR,
                            "dummy prompt",
                            outputs_dir=test_out_dir,
                            max_budget=10
                        )

                    self.assertIn("FAIL-CLOSED INCONCLUSIVE: Arm B exceeded sub-budget (11 requests > limit 10)", str(ctx.exception))
                    # Critical R7 check: target directory was NEVER created
                    self.assertFalse(test_out_dir.exists(), "Target directory was created despite sub-budget breach!")

    def test_run_arm_does_not_modify_or_delete_preexisting_files_in_target_dir_on_failure(self):
        """Proof that run_arm failure does not modify or delete pre-existing files in target directory (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "preexisting_outputs"
            test_out_dir.mkdir()
            canary_file = test_out_dir / "canary.txt"
            canary_file.write_text("precious canary data", encoding="utf-8")

            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = "Failure stdout"
            mock_proc.stderr = "Crash simulation"

            with patch("subprocess.run", return_value=mock_proc):
                with self.assertRaises(RuntimeError):
                    run_arms.run_arm(
                        "Arm_Test",
                        SCRIPT_DIR,
                        "dummy prompt",
                        outputs_dir=test_out_dir
                    )

                # Verify canary is intact and NO extra files were created
                self.assertTrue(canary_file.exists())
                self.assertEqual(canary_file.read_text(encoding="utf-8"), "precious canary data")
                self.assertEqual(len(list(test_out_dir.iterdir())), 1)

    def test_arm_turn_controller_blocks_11th_request_launch_attempt(self):
        """Proof that ArmTurnController intercepts and BLOCKS the 11th request launch attempt (R5)."""
        controller = run_arms.ArmTurnController("Arm_B", max_budget=10)

        # First 10 requests acquire permission successfully
        for i in range(1, 11):
            attempt = controller.acquire_launch_permission()
            self.assertEqual(attempt, i)

        self.assertEqual(controller.launched_attempts, 10)

        # 11th request attempt is BLOCKED fail-closed before launching
        with self.assertRaises(RuntimeError) as ctx:
            controller.acquire_launch_permission()

        self.assertIn("Blocked attempt to launch request 11 for Arm_B (exceeds sub-budget limit of 10)", str(ctx.exception))
        self.assertEqual(controller.launched_attempts, 10, "Attempt count was incremented despite block!")

    def test_decomposed_arm_blocks_11th_turn_dispatch_with_integrated_executor(self):
        """Proof that run_arm in decomposed mode executes exactly 10 turns and blocks the 11th dispatch (R5)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_decomposed_outputs"
            self.assertFalse(test_out_dir.exists())

            dispatched_calls = []

            def mock_dispatcher(arm_label, idx, prompt, staging_dir):
                dispatched_calls.append(idx)
                return {"turn": idx, "output": f"Turn {idx} output"}

            prompts = [f"Prompt {i}" for i in range(1, 12)]  # 11 prompts
            self.assertEqual(len(prompts), 11)

            with self.assertRaises(RuntimeError) as ctx:
                run_arms.run_arm(
                    "Arm_B",
                    SCRIPT_DIR,
                    prompts,
                    outputs_dir=test_out_dir,
                    max_budget=10,
                    turn_dispatcher=mock_dispatcher,
                    decomposed=True
                )

            self.assertIn("Blocked attempt to launch request 11 for Arm_B (exceeds sub-budget limit of 10)", str(ctx.exception))
            # Critical R5 check: exactly 10 calls were dispatched; 11th call was intercepted BEFORE dispatch!
            self.assertEqual(len(dispatched_calls), 10)
            self.assertEqual(dispatched_calls, list(range(1, 11)))
            # Critical R7 check: target directory was never created due to fail-closed abort
            self.assertFalse(test_out_dir.exists())

    def test_budget_tracker_pre_phase_token_and_request_reservations(self):
        """Proof that BudgetTracker validates both request and token caps atomically with reservations (R5)."""
        tracker = run_arms.BudgetTracker(request_cap=18, token_cap=3505000)

        # 1. Arm A request cap breach check:
        # Arm A requesting 2 requests -> 4 current + 2 requested + 13 reserved = 19 > 18
        with self.assertRaises(RuntimeError) as ctx:
            tracker.check_pre_phase_budget("Arm_A", requested_reqs=2, requested_tokens=2025000)
        self.assertIn("Projected requests (19) exceed global cap (18)", str(ctx.exception))

        # 2. Arm A token cap breach check:
        # Arm A requesting 2400000 tokens -> 15972 current + 2400000 + 1180000 reserved = 3595972 > 3505000
        with self.assertRaises(RuntimeError) as ctx:
            tracker.check_pre_phase_budget("Arm_A", requested_reqs=1, requested_tokens=2400000)
        self.assertIn("Projected tokens (3595972) exceed global cap (3505000)", str(ctx.exception))

        # 3. Arm A valid check: fits within 18 requests and 3505000 tokens
        try:
            tracker.check_pre_phase_budget("Arm_A", requested_reqs=1, requested_tokens=2025000)
        except RuntimeError:
            self.fail("check_pre_phase_budget raised RuntimeError unexpectedly for valid Arm A budget!")

        # Record Arm A outcome: 1 request, 67770 tokens
        tracker.record_phase("Arm_A", {"requests_count": 1, "total_tokens": 67770})

        # 4. Arm B request cap breach check:
        # Arm B requesting 11 requests -> (4+1) current + 11 requested + 3 reserved = 19 > 18
        with self.assertRaises(RuntimeError) as ctx:
            tracker.check_pre_phase_budget("Arm_B", requested_reqs=11, requested_tokens=530000)
        self.assertIn("Projected requests (19) exceed global cap (18)", str(ctx.exception))

        # 5. Arm B token cap breach check:
        # Arm B requesting 2800000 tokens -> (15972+67770) + 2800000 + 650000 reserved = 3533742 > 3505000
        with self.assertRaises(RuntimeError) as ctx:
            tracker.check_pre_phase_budget("Arm_B", requested_reqs=10, requested_tokens=2800000)
        self.assertIn("Projected tokens (3533742) exceed global cap (3505000)", str(ctx.exception))

        # 6. Arm B valid check: fits within 18 requests and 3505000 tokens
        try:
            tracker.check_pre_phase_budget("Arm_B", requested_reqs=10, requested_tokens=530000)
        except RuntimeError:
            self.fail("check_pre_phase_budget raised RuntimeError unexpectedly for valid Arm B budget!")

    def test_run_evaluator_nonzero_exit_code_aborts_without_creating_target_dir_or_key_read(self):
        """Proof that run_evaluation aborts on exit code != 0 without creating eval dir or reading blinding keys (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "uncreated_eval_dir"
            self.assertFalse(test_eval_dir.exists())

            mock_proc = MagicMock()
            mock_proc.returncode = 127
            mock_proc.stdout = "Agy execution failed"
            mock_proc.stderr = "Command not found: agy"

            with patch("subprocess.run", return_value=mock_proc):
                with patch("run_evaluator.unblind_verdict") as mock_unblind:
                    with self.assertRaises(RuntimeError) as ctx:
                        run_evaluator.run_evaluation(eval_dir=test_eval_dir)

                    self.assertIn("FAIL-CLOSED: Blind evaluator execution failed with exit code 127", str(ctx.exception))
                    # Critical R7 checks:
                    # 1. unblind_verdict was never called
                    mock_unblind.assert_not_called()
                    # 2. Target eval directory was NEVER created
                    self.assertFalse(test_eval_dir.exists(), "Target eval dir was created despite failure!")

    def test_evaluator_missing_json_block_aborts_without_unblinding(self):
        """Proof that validate_and_extract_verdict aborts if ```json code block is missing (R7)."""
        stdout_missing_json = "This is a detailed analysis but without any structured code block."
        with self.assertRaises(RuntimeError) as ctx:
            run_evaluator.validate_and_extract_verdict(stdout_missing_json)
        self.assertIn("missing required ```json code block before unblinding", str(ctx.exception))

    def test_evaluator_malformed_json_aborts_without_unblinding(self):
        """Proof that validate_and_extract_verdict aborts if JSON block is malformed (R7)."""
        stdout_malformed_json = "Analysis:\n```json\n{ invalid json content here: \n```"
        with self.assertRaises(RuntimeError) as ctx:
            run_evaluator.validate_and_extract_verdict(stdout_malformed_json)
        self.assertIn("JSON block failed to parse", str(ctx.exception))

    def test_evaluator_missing_required_keys_aborts_without_unblinding(self):
        """Proof that validate_and_extract_verdict aborts if required keys are missing (R7)."""
        incomplete_json = json.dumps({"alpha": {"verdict": "pass"}})
        stdout_incomplete = f"```json\n{incomplete_json}\n```"
        with self.assertRaises(RuntimeError) as ctx:
            run_evaluator.validate_and_extract_verdict(stdout_incomplete)
        self.assertIn("missing required keys (alpha, beta, comparative_verdict)", str(ctx.exception))

    def test_global_budget_exact_accounting_and_breach_detection(self):
        """Proof that calculate_and_verify_global_budget accounts for all 7 phases and tokens, enforcing caps (R5)."""
        metrics_a = {"requests_count": 1, "total_tokens": 67770}
        metrics_b = {"requests_count": 10, "total_tokens": 442519}

        # Baseline execution: all 7 phases accounted (3 class + 1 adv + 1 A + 10 B + 1 eval + 1 check + 1 cont = 18)
        # Actual tokens: 10972 (class) + 5000 (adv) + 67770 (A) + 442519 (B) + 17889 (eval) = 544150
        total_reqs, actual_toks = run_arms.calculate_and_verify_global_budget(metrics_a, metrics_b)
        self.assertEqual(total_reqs, 18, f"Expected exactly 18 planned requests in ledger, got {total_reqs}")
        self.assertEqual(actual_toks, 544150, f"Expected 544150 actual tokens recorded, got {actual_toks}")

        # Counterfactual breach 1: Arm B used 11 requests -> total 19 -> must abort fail-closed
        breach_b = {"requests_count": 11, "total_tokens": 450000}
        with self.assertRaises(RuntimeError) as ctx:
            run_arms.calculate_and_verify_global_budget(metrics_a, breach_b)
        self.assertIn("Global request budget exceeded: 19 > 18", str(ctx.exception))

        # Counterfactual breach 2: Actual tokens exceed global token cap (3505000)
        massive_token_b = {"requests_count": 10, "total_tokens": 3500000}
        with self.assertRaises(RuntimeError) as ctx:
            run_arms.calculate_and_verify_global_budget(metrics_a, massive_token_b)
        self.assertIn("Global actual token budget exceeded", str(ctx.exception))

        # Counterfactual breach 3: Planned tokens (including reservations) exceed cap
        with self.assertRaises(RuntimeError) as ctx:
            run_arms.calculate_and_verify_global_budget(
                metrics_a,
                metrics_b,
                checker_reserved_tokens=3000000
            )
        self.assertIn("Global planned token budget exceeded", str(ctx.exception))

    def test_positive_control_all_runners_create_directories_and_files_on_success(self):
        """Proof that valid executions create destination directories and write all outputs (proving falsifiability)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Test run_arm positive control
            arm_out_dir = Path(tmpdir) / "successful_arm_out"
            self.assertFalse(arm_out_dir.exists())

            dummy_session = Path(tmpdir) / "dummy-session-pos.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_side_effect(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 22222222-3333-4444-5555-666666666666"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            with patch("subprocess.run", side_effect=arm_side_effect):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    metrics = run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=arm_out_dir)
                    self.assertEqual(metrics["requests_count"], 1)

                    # Verify that directory was created and all 6 artifacts were published
                    self.assertTrue(arm_out_dir.exists())
                    self.assertTrue((arm_out_dir / "raw-decision-A.md").exists())
                    self.assertTrue((arm_out_dir / "Arm_A-stdout.txt").exists())
                    self.assertTrue((arm_out_dir / "Arm_A-stderr.txt").exists())
                    self.assertTrue((arm_out_dir / "arm_a-session.jsonl").exists())
                    self.assertTrue((arm_out_dir / "arm_a-usage.json").exists())
                    self.assertTrue((arm_out_dir / "Arm_A-summary.json").exists())

            # 2. Test run_evaluator positive control
            eval_out_dir = Path(tmpdir) / "successful_eval_out"
            self.assertFalse(eval_out_dir.exists())

            dummy_key = Path(tmpdir) / "dummy-key.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "fail", "must": {"M1": True, "M2": True, "M3": False, "M4": True}, "must_not_violations": ["X2"]},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Beta", "rationale": "Beta verified all sources directly."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation text...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            with patch("subprocess.run", return_value=mock_eval_proc):
                v_data = run_evaluator.run_evaluation(eval_dir=eval_out_dir, key_file=dummy_key)
                self.assertEqual(v_data["beta"]["verdict"], "pass")

                # Verify that directory was created and all 4 artifacts were published
                self.assertTrue(eval_out_dir.exists())
                self.assertTrue((eval_out_dir / "evaluator-briefing.md").exists())
                self.assertTrue((eval_out_dir / "evaluator-stdout.txt").exists())
                self.assertTrue((eval_out_dir / "evaluator-stderr.txt").exists())
                self.assertTrue((eval_out_dir / "evaluator-verdict.json").exists())

            # 3. Test execute_decomposed_arm_turns positive control
            decomposed_out_dir = Path(tmpdir) / "successful_decomposed_out"
            self.assertFalse(decomposed_out_dir.exists())

            def mock_pos_dispatcher(arm_label, idx, prompt, staging_dir):
                return {"turn": idx, "output": f"Success turn {idx}"}

            summary = run_arms.run_arm(
                "Arm_B",
                SCRIPT_DIR,
                ["turn1", "turn2"],
                outputs_dir=decomposed_out_dir,
                max_budget=10,
                turn_dispatcher=mock_pos_dispatcher,
                decomposed=True
            )
            self.assertEqual(summary["requests_count"], 2)
            self.assertTrue(decomposed_out_dir.exists())
            self.assertTrue((decomposed_out_dir / "Arm_B-summary.json").exists())

    def test_run_arm_publication_failure_rolls_back_uncreated_target_dir(self):
        """Proof that run_arm publication failure rolls back and removes newly created target directory (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_pub_fail_arm_out"
            self.assertFalse(test_out_dir.exists())

            dummy_session = Path(tmpdir) / "dummy-session-fail.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 33333333-4444-5555-6666-777777777777"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_out_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                        self.assertIn("FAIL-CLOSED: Transactional publication failed and was rolled back cleanly", str(ctx.exception))
                        self.assertTrue(has_failed, "Failure was never injected into copy2!")
                        # Critical R7 check: target directory was completely removed by rollback!
                        self.assertFalse(test_out_dir.exists(), "Target directory was left behind after publication failure!")

    def test_run_arm_publication_failure_preserves_preexisting_target_dir_byte_by_byte(self):
        """Proof that run_arm publication failure preserves pre-existing target directory and files byte-by-byte (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "preexisting_arm_out"
            test_out_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_out_dir / "canary.txt"
            canary_content = "canary token data: do not alter or delete\n"
            canary_file.write_text(canary_content, encoding="utf-8")
            canary_hash = hashlib.sha256(canary_file.read_bytes()).hexdigest()

            decision_file = test_out_dir / "raw-decision-A.md"
            orig_decision_content = "# Pre-existing Decision A\nOriginal content prior to failed run.\n"
            decision_file.write_text(orig_decision_content, encoding="utf-8")
            decision_hash = hashlib.sha256(decision_file.read_bytes()).hexdigest()

            dummy_session = Path(tmpdir) / "dummy-session-fail2.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("new decision content that should be rolled back", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 44444444-5555-6666-7777-888888888888"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_out_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                        self.assertIn("FAIL-CLOSED: Transactional publication failed and was rolled back cleanly", str(ctx.exception))
                        self.assertTrue(has_failed, "Failure was never injected into copy2!")

                        # Critical R7 checks:
                        # 1. Target directory still exists
                        self.assertTrue(test_out_dir.exists())
                        # 2. Canary is byte-for-byte identical
                        self.assertEqual(hashlib.sha256(canary_file.read_bytes()).hexdigest(), canary_hash)
                        self.assertEqual(canary_file.read_text(encoding="utf-8"), canary_content)
                        # 3. Overwritten decision file was restored byte-for-byte from backup
                        self.assertEqual(hashlib.sha256(decision_file.read_bytes()).hexdigest(), decision_hash)
                        self.assertEqual(decision_file.read_text(encoding="utf-8"), orig_decision_content)
                        # 4. No new partial files left behind
                        remaining_files = sorted(p.name for p in test_out_dir.iterdir())
                        self.assertEqual(remaining_files, ["canary.txt", "raw-decision-A.md"])

    def test_run_evaluator_publication_failure_rolls_back_uncreated_target_dir(self):
        """Proof that run_evaluator publication failure rolls back and removes newly created target directory (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "uncreated_pub_fail_eval_out"
            self.assertFalse(test_eval_dir.exists())

            dummy_key = Path(tmpdir) / "dummy-key-fail.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_eval_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected evaluator disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with self.assertRaises(RuntimeError) as ctx:
                        run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                    self.assertIn("FAIL-CLOSED: Transactional publication failed and was rolled back cleanly", str(ctx.exception))
                    self.assertTrue(has_failed, "Failure was never injected into copy2!")
                    # Critical R7 check: target eval directory was completely removed by rollback!
                    self.assertFalse(test_eval_dir.exists(), "Target eval dir was left behind after publication failure!")

    def test_run_evaluator_publication_failure_preserves_preexisting_target_dir_byte_by_byte(self):
        """Proof that run_evaluator publication failure preserves pre-existing target directory and files byte-by-byte (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "preexisting_eval_out"
            test_eval_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_eval_dir / "canary.txt"
            canary_content = "evaluator canary token: must remain untouched\n"
            canary_file.write_text(canary_content, encoding="utf-8")
            canary_hash = hashlib.sha256(canary_file.read_bytes()).hexdigest()

            briefing_file = test_eval_dir / "evaluator-briefing.md"
            orig_briefing_content = "# Pre-existing Briefing\nPrior briefing content.\n"
            briefing_file.write_text(orig_briefing_content, encoding="utf-8")
            briefing_hash = hashlib.sha256(briefing_file.read_bytes()).hexdigest()

            dummy_key = Path(tmpdir) / "dummy-key-fail2.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_eval_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected evaluator disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with self.assertRaises(RuntimeError) as ctx:
                        run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                    self.assertIn("FAIL-CLOSED: Transactional publication failed and was rolled back cleanly", str(ctx.exception))
                    self.assertTrue(has_failed, "Failure was never injected into copy2!")

                    # Critical R7 checks:
                    # 1. Target eval directory still exists
                    self.assertTrue(test_eval_dir.exists())
                    # 2. Canary is byte-for-byte identical
                    self.assertEqual(hashlib.sha256(canary_file.read_bytes()).hexdigest(), canary_hash)
                    self.assertEqual(canary_file.read_text(encoding="utf-8"), canary_content)
                    # 3. Overwritten briefing file was restored byte-for-byte from backup
                    self.assertEqual(hashlib.sha256(briefing_file.read_bytes()).hexdigest(), briefing_hash)
                    self.assertEqual(briefing_file.read_text(encoding="utf-8"), orig_briefing_content)
                    # 4. No new partial files left behind
                    remaining_files = sorted(p.name for p in test_eval_dir.iterdir())
                    self.assertEqual(remaining_files, ["canary.txt", "evaluator-briefing.md"])

    def test_run_arm_publication_failure_with_rmtree_error_reports_incomplete_rollback(self):
        """Proof that if rmtree fails during rollback of uncreated target dir, run_arm reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_rmtree_fail_out"
            self.assertFalse(test_out_dir.exists())

            dummy_session = Path(tmpdir) / "dummy-session-fail-rmtree.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 55555555-6666-7777-8888-999999999999"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_out_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_rmtree = shutil.rmtree

            def failing_rmtree(path, *args, **kwargs):
                if str(test_out_dir) in str(path):
                    raise OSError("Injected hardware fault during rmtree")
                return orig_rmtree(path, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with patch("shutil.rmtree", side_effect=failing_rmtree):
                            with self.assertRaises(RuntimeError) as ctx:
                                run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                            exc_msg = str(ctx.exception)
                            self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                            self.assertIn("Failed to remove target_dir", exc_msg)
                            self.assertTrue(has_failed)

    def test_run_arm_publication_failure_with_restoration_error_reports_incomplete_rollback(self):
        """Proof that if copy2 fails during restoration of pre-existing files, run_arm reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "preexisting_restore_fail_out"
            test_out_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_out_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            decision_file = test_out_dir / "raw-decision-A.md"
            decision_file.write_text("prior decision content", encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-fail-rst.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("new staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 66666666-7777-8888-9999-000000000000"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            restore_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed, restore_failed
                dst_path = Path(dst)
                src_path = Path(src)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            raise OSError("Injected disk failure on second publication copy")
                else:
                    # During rollback restoration: fail when copying backup back to dst
                    if str(test_out_dir) in str(dst_path) and "backup_" in src_path.name:
                        restore_failed = True
                        raise OSError("Injected failure during backup restoration")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to restore", exc_msg)
                        self.assertTrue(has_failed)
                        self.assertTrue(restore_failed)

    def test_run_arm_publication_failure_with_unlink_error_reports_incomplete_rollback(self):
        """Proof that if unlink fails during rollback of newly created file, run_arm reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "preexisting_unlink_fail_out"
            test_out_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_out_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-fail-unl.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("new staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 77777777-8888-9999-0000-111111111111"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_out_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected publication failure on second copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_unlink = Path.unlink
            unlink_failed = False

            def failing_unlink(path_self, *args, **kwargs):
                nonlocal unlink_failed
                if has_failed and str(test_out_dir) in str(path_self):
                    unlink_failed = True
                    raise OSError("Injected unlink permission denied")
                return orig_unlink(path_self, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with patch.object(Path, "unlink", failing_unlink):
                            with self.assertRaises(RuntimeError) as ctx:
                                run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                            exc_msg = str(ctx.exception)
                            self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                            self.assertIn("Failed to unlink newly created file", exc_msg)
                            self.assertTrue(has_failed)
                            self.assertTrue(unlink_failed)

    def test_run_evaluator_publication_failure_with_rmtree_error_reports_incomplete_rollback(self):
        """Proof that if rmtree fails during rollback of uncreated eval dir, run_evaluator reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "uncreated_eval_rmtree_fail_out"
            self.assertFalse(test_eval_dir.exists())

            dummy_key = Path(tmpdir) / "dummy-key-rmtree-fail.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_eval_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected evaluator disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_rmtree = shutil.rmtree

            def failing_rmtree(path, *args, **kwargs):
                if str(test_eval_dir) in str(path):
                    raise OSError("Injected hardware fault during eval rmtree")
                return orig_rmtree(path, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with patch("shutil.rmtree", side_effect=failing_rmtree):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to remove target_dir", exc_msg)
                        self.assertTrue(has_failed)

    def test_run_evaluator_publication_failure_with_restoration_error_reports_incomplete_rollback(self):
        """Proof that if copy2 fails during restoration of pre-existing eval files, run_evaluator reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "preexisting_eval_rst_fail_out"
            test_eval_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_eval_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            briefing_file = test_eval_dir / "evaluator-briefing.md"
            briefing_file.write_text("prior briefing", encoding="utf-8")

            dummy_key = Path(tmpdir) / "dummy-key-rst-fail.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            restore_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed, restore_failed
                dst_path = Path(dst)
                src_path = Path(src)
                if not has_failed:
                    if str(test_eval_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            raise OSError("Injected evaluator disk failure on second publication copy")
                else:
                    if str(test_eval_dir) in str(dst_path) and "backup_" in src_path.name:
                        restore_failed = True
                        raise OSError("Injected failure during eval backup restoration")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with self.assertRaises(RuntimeError) as ctx:
                        run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                    exc_msg = str(ctx.exception)
                    self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                    self.assertIn("Failed to restore", exc_msg)
                    self.assertTrue(has_failed)
                    self.assertTrue(restore_failed)

    def test_run_evaluator_publication_failure_with_unlink_error_reports_incomplete_rollback(self):
        """Proof that if unlink fails during rollback of newly created eval file, run_evaluator reports incomplete rollback (R7)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "preexisting_eval_unl_fail_out"
            test_eval_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_eval_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            dummy_key = Path(tmpdir) / "dummy-key-unl-fail.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and str(test_eval_dir) in str(dst_path):
                    copy_count += 1
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected evaluator disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_unlink = Path.unlink
            unlink_failed = False

            def failing_unlink(path_self, *args, **kwargs):
                nonlocal unlink_failed
                if has_failed and str(test_eval_dir) in str(path_self):
                    unlink_failed = True
                    raise OSError("Injected eval unlink permission denied")
                return orig_unlink(path_self, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with patch.object(Path, "unlink", failing_unlink):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to unlink newly created file", exc_msg)
                        self.assertTrue(has_failed)
                        self.assertTrue(unlink_failed)

    def test_run_arm_publication_failure_preserves_external_preexisting_raw_decision_file_byte_by_byte(self):
        """Proof that pre-existing external raw_decision_file is preserved byte-by-byte when target_dir is uncreated (R9)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_decision_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_decision_file = ext_dir / "external-raw-decision.md"
            ext_content = "Pre-existing external decision content from prior workflow"
            ext_decision_file.write_text(ext_content, encoding="utf-8")
            orig_hash = hashlib.sha256(ext_decision_file.read_bytes()).hexdigest()

            dummy_session = Path(tmpdir) / "dummy-session-ext-dec.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("new staged decision overwriting external", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 88888888-9999-0000-1111-222222222222"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and (str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path)):
                    copy_count += 1
                    # Copy 1 is to ext_decision_file (let it succeed and overwrite)
                    # Copy 2 is to test_out_dir (inject failure)
                    if copy_count >= 2:
                        has_failed = True
                        raise OSError("Injected disk failure on second publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", raw_decision_file=ext_decision_file, outputs_dir=test_out_dir)

                        self.assertIn("rolled back cleanly", str(ctx.exception))
                        self.assertTrue(has_failed)
                        # target_out_dir was uncreated and cleanly removed
                        self.assertFalse(test_out_dir.exists())
                        # Pre-existing external file was preserved byte-by-byte
                        self.assertTrue(ext_decision_file.exists())
                        self.assertEqual(hashlib.sha256(ext_decision_file.read_bytes()).hexdigest(), orig_hash)
                        self.assertEqual(ext_decision_file.read_text(encoding="utf-8"), ext_content)

    def test_run_arm_publication_failure_preserves_external_preexisting_usage_json_file_byte_by_byte(self):
        """Proof that pre-existing external usage_json_file is preserved byte-by-byte when target_dir is uncreated (R9)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_usage_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_usage_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_usage_file = ext_dir / "external-arm-usage.json"
            ext_content = json.dumps({"preexisting": "usage", "tokens": 12345})
            ext_usage_file.write_text(ext_content, encoding="utf-8")
            orig_hash = hashlib.sha256(ext_usage_file.read_bytes()).hexdigest()

            dummy_session = Path(tmpdir) / "dummy-session-ext-usg.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 99999999-0000-1111-2222-333333333333"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed and (str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path)):
                    copy_count += 1
                    # Copy 5 is to ext_usage_file (let it succeed and overwrite)
                    # Copy 6 is to target_out_dir summary (inject failure)
                    if copy_count >= 6:
                        has_failed = True
                        raise OSError("Injected disk failure on sixth publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", usage_json_file=ext_usage_file, outputs_dir=test_out_dir)

                        self.assertIn("rolled back cleanly", str(ctx.exception))
                        self.assertTrue(has_failed)
                        # target_out_dir was cleanly removed
                        self.assertFalse(test_out_dir.exists())
                        # Pre-existing external usage file was preserved byte-by-byte
                        self.assertTrue(ext_usage_file.exists())
                        self.assertEqual(hashlib.sha256(ext_usage_file.read_bytes()).hexdigest(), orig_hash)
                        self.assertEqual(ext_usage_file.read_text(encoding="utf-8"), ext_content)

    def test_run_arm_publication_failure_external_preexisting_restoration_error_reports_incomplete_rollback(self):
        """Proof that if copy2 fails during restoration of external pre-existing file, run_arm reports incomplete rollback (R9)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_rst_ext_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_rst_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_decision_file = ext_dir / "external-raw-decision.md"
            ext_decision_file.write_text("prior external decision", encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-ext-rst.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 00000000-1111-2222-3333-444444444444"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            restore_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed, restore_failed
                dst_path = Path(dst)
                src_path = Path(src)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            raise OSError("Injected disk failure on second publication copy")
                else:
                    # During rollback restoration: fail when copying backup back to external dst
                    if str(ext_dir) in str(dst_path) and "backup_" in src_path.name:
                        restore_failed = True
                        raise OSError("Injected failure during external decision backup restoration")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", raw_decision_file=ext_decision_file, outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to restore", exc_msg)
                        self.assertTrue(has_failed)
                        self.assertTrue(restore_failed)

    def test_run_arm_publication_failure_external_usage_restoration_error_reports_incomplete_rollback(self):
        """Proof that if copy2 fails during restoration of external pre-existing usage file, run_arm reports incomplete rollback (R9)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_usage_rst_ext_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_usage_rst_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_usage_file = ext_dir / "external-arm-usage.json"
            ext_usage_file.write_text(json.dumps({"prior": "usage"}), encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-ext-usg-rst.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 11111111-2222-3333-4444-555555555555"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            restore_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed, restore_failed
                dst_path = Path(dst)
                src_path = Path(src)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 6:
                            has_failed = True
                            raise OSError("Injected disk failure on sixth publication copy")
                else:
                    # During rollback restoration: fail when copying backup back to external usage dst
                    if str(ext_dir) in str(dst_path) and "backup_" in src_path.name:
                        restore_failed = True
                        raise OSError("Injected failure during external usage backup restoration")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", usage_json_file=ext_usage_file, outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to restore", exc_msg)
                        self.assertTrue(has_failed)
                        self.assertTrue(restore_failed)

    def test_run_arm_publication_failure_missing_external_backup_reports_incomplete_rollback(self):
        """Proof that if external pre-existing backup file is missing or inaccessible, run_arm reports incomplete rollback (R10)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_missing_bkp_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_missing_bkp_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_decision_file = ext_dir / "external-raw-decision.md"
            ext_decision_file.write_text("prior external decision", encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-ext-bkp-fail.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 12341234-5678-5678-9999-000000000000"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            backup_paths = []

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if "backup_" in dst_path.name:
                    backup_paths.append(dst_path)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            # Simulate backup file becoming missing/inaccessible prior to rollback
                            for bp in backup_paths:
                                if bp.exists():
                                    bp.unlink()
                            raise OSError("Injected disk failure on second publication copy with backup missing")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", raw_decision_file=ext_decision_file, outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("missing or inaccessible", exc_msg)
                        self.assertTrue(has_failed)

    def test_run_arm_publication_failure_missing_internal_backup_reports_incomplete_rollback(self):
        """Proof that if internal pre-existing backup file is missing or inaccessible, run_arm reports incomplete rollback (R10)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "preexisting_missing_bkp_out_dir"
            test_out_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_out_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            decision_file = test_out_dir / "raw-decision-A.md"
            decision_file.write_text("prior decision content", encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-int-bkp-fail.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 56785678-1234-1234-9999-000000000000"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            backup_paths = []

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if "backup_" in dst_path.name:
                    backup_paths.append(dst_path)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            for bp in backup_paths:
                                if bp.exists():
                                    bp.unlink()
                            raise OSError("Injected disk failure on second publication copy with internal backup missing")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("missing or inaccessible", exc_msg)
                        self.assertTrue(has_failed)

    def test_run_evaluator_publication_failure_missing_backup_reports_incomplete_rollback(self):
        """Proof that if evaluator pre-existing backup file is missing or inaccessible, run_evaluator reports incomplete rollback (R10)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "preexisting_eval_missing_bkp_out"
            test_eval_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_eval_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            briefing_file = test_eval_dir / "evaluator-briefing.md"
            briefing_file.write_text("prior briefing", encoding="utf-8")

            dummy_key = Path(tmpdir) / "dummy-key-missing-bkp.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            backup_paths = []

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if "backup_" in dst_path.name:
                    backup_paths.append(dst_path)
                if not has_failed:
                    if str(test_eval_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 2:
                            has_failed = True
                            for bp in backup_paths:
                                if bp.exists():
                                    bp.unlink()
                            raise OSError("Injected evaluator disk failure with backup missing")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with self.assertRaises(RuntimeError) as ctx:
                        run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                    exc_msg = str(ctx.exception)
                    self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                    self.assertIn("missing or inaccessible", exc_msg)
                    self.assertTrue(has_failed)

    def test_run_arm_publication_failure_missing_external_usage_backup_reports_incomplete_rollback(self):
        """Proof that if external pre-existing usage backup file is missing, run_arm reports incomplete rollback (R10)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_usage_missing_bkp_out"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_usage_missing_bkp_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)
            ext_usage_file = ext_dir / "external-arm-usage.json"
            ext_usage_file.write_text(json.dumps({"prior": "usage"}), encoding="utf-8")

            dummy_session = Path(tmpdir) / "dummy-session-ext-usg-bkp-fail.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("decision content in staging", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: 98769876-4321-4321-0000-111111111111"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False
            backup_paths = []

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if "backup_" in dst_path.name:
                    backup_paths.append(dst_path)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path):
                        copy_count += 1
                        if copy_count >= 6:
                            has_failed = True
                            for bp in backup_paths:
                                if bp.exists():
                                    bp.unlink()
                            raise OSError("Injected disk failure on sixth publication copy with backup missing")
                return orig_copy2(src, dst, *args, **kwargs)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", usage_json_file=ext_usage_file, outputs_dir=test_out_dir)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("missing or inaccessible", exc_msg)
                        self.assertTrue(has_failed)

    def test_run_arm_publication_failure_backup_exists_permission_error_reports_incomplete_rollback_and_continues_cleanup(self):
        """Proof that if backup_file.exists() raises PermissionError, run_arm catches it, continues cleanup of subsequent destinations, and reports incomplete rollback (R11/R12)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_out_dir = Path(tmpdir) / "uncreated_stat_fail_out_dir"
            self.assertFalse(test_out_dir.exists())

            ext_dir = Path(tmpdir) / "external_stat_fail_dir"
            ext_dir.mkdir(parents=True, exist_ok=True)

            # Pre-existing destination 1: decision file (its backup stat will fail with PermissionError during rollback)
            ext_decision_file = ext_dir / "external-raw-decision.md"
            ext_decision_file.write_text("prior external decision content", encoding="utf-8")

            # Pre-existing destination 5: SUBSEQUENT OBSERVABLE EXTERNAL DESTINATION (R12)
            ext_usage_file = ext_dir / "external-usage.json"
            ext_usage_file.write_text("prior external usage content", encoding="utf-8")
            orig_usage_hash = hashlib.sha256(b"prior external usage content").hexdigest()

            dummy_session = Path(tmpdir) / "dummy-session-stat-fail.jsonl"
            dummy_session.write_text('{"event":"test"}\n', encoding="utf-8")

            mock_usage = {
                "normalized_usage": {
                    "semantic_response_count": 1,
                    "semantic_per_response_sum": {
                        "input_tokens": 50000,
                        "cached_input_tokens": 10000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2000,
                        "total_tokens": 52000
                    }
                }
            }

            def arm_sub_run(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == "codex":
                    if "-o" in cmd:
                        out_file = Path(cmd[cmd.index("-o") + 1])
                        out_file.write_text("staged decision", encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    m.stdout = "session id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                    m.stderr = ""
                    return m
                else:
                    out_idx = cmd.index("--output") + 1
                    Path(cmd[out_idx]).write_text(json.dumps(mock_usage), encoding="utf-8")
                    m = MagicMock()
                    m.returncode = 0
                    return m

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                if not has_failed:
                    if str(test_out_dir) in str(dst_path) or str(ext_dir) in str(dst_path):
                        copy_count += 1
                        # Copies 1-5 succeed:
                        # 1. ext_decision_file
                        # 2. Arm_A-stdout.txt
                        # 3. Arm_A-stderr.txt
                        # 4. arm_a-session.jsonl
                        # 5. ext_usage_file
                        # Copy 6: Arm_A-summary.json -> INJECT FAILURE HERE!
                        if copy_count >= 6:
                            has_failed = True
                            raise OSError("Injected disk failure on sixth publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_exists = Path.exists
            stat_error_injected = False

            def failing_exists(path_self):
                nonlocal stat_error_injected
                # During rollback, only fail stat for the decision backup file
                if has_failed and "backup_" in str(path_self) and "external-raw-decision.md" in str(path_self):
                    stat_error_injected = True
                    raise PermissionError("Simulated permission denied on decision backup stat")
                return orig_exists(path_self)

            with patch("subprocess.run", side_effect=arm_sub_run):
                with patch("run_arms.find_session_file", return_value=dummy_session):
                    with patch("shutil.copy2", side_effect=failing_copy2):
                        with patch.object(Path, "exists", failing_exists):
                            with self.assertRaises(RuntimeError) as ctx:
                                run_arms.run_arm("Arm_A", SCRIPT_DIR, "prompt", raw_decision_file=ext_decision_file, usage_json_file=ext_usage_file, outputs_dir=test_out_dir)

                            exc_msg = str(ctx.exception)
                            self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                            self.assertIn("Failed to check existence/stat of backup file", exc_msg)
                            self.assertTrue(has_failed, "Publication failure was never injected!")
                            self.assertTrue(stat_error_injected, "Stat error was never injected into decision backup!")

                            # Critical R11 / R12 checks:
                            # 1. Subsequent pre-existing external usage file was restored byte-by-byte from backup!
                            self.assertEqual(ext_usage_file.read_text(encoding="utf-8"), "prior external usage content")
                            self.assertEqual(hashlib.sha256(ext_usage_file.read_bytes()).hexdigest(), orig_usage_hash)

                            # 2. Created target output directory was completely removed by post-loop cleanup!
                            self.assertFalse(test_out_dir.exists())

    def test_run_evaluator_publication_failure_backup_exists_oserror_reports_incomplete_rollback_and_continues_cleanup(self):
        """Proof that if evaluator backup exists() raises OSError, run_evaluator catches it, continues cleanup of subsequent destinations, and reports incomplete rollback (R11/R12)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_eval_dir = Path(tmpdir) / "preexisting_eval_stat_fail_out"
            test_eval_dir.mkdir(parents=True, exist_ok=True)

            canary_file = test_eval_dir / "canary.txt"
            canary_file.write_text("canary data", encoding="utf-8")

            # Pre-existing destination 1 (briefing) - its backup stat will fail with OSError during rollback
            briefing_file = test_eval_dir / "evaluator-briefing.md"
            briefing_file.write_text("prior briefing content", encoding="utf-8")

            # Pre-existing destination 2 (stdout) - SUBSEQUENT OBSERVABLE PRE-EXISTING DESTINATION (R12)
            stdout_file = test_eval_dir / "evaluator-stdout.txt"
            stdout_file.write_text("prior stdout content", encoding="utf-8")
            orig_stdout_hash = hashlib.sha256(b"prior stdout content").hexdigest()

            # Destination 3 (stderr) is initially non-existent, but will be created during publication before failure
            stderr_file = test_eval_dir / "evaluator-stderr.txt"
            self.assertFalse(stderr_file.exists())

            dummy_key = Path(tmpdir) / "dummy-key-stat-fail.json"
            dummy_key.write_text(json.dumps({
                "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
                "alpha": "Arm_A",
                "beta": "Arm_B"
            }), encoding="utf-8")

            valid_json = json.dumps({
                "alpha": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "beta": {"verdict": "pass", "must": {"M1": True, "M2": True, "M3": True, "M4": True}, "must_not_violations": []},
                "comparative_verdict": {"superior_decision": "Tie", "rationale": "Both passed."}
            })
            mock_eval_proc = MagicMock()
            mock_eval_proc.returncode = 0
            mock_eval_proc.stdout = f"Evaluation output...\n```json\n{valid_json}\n```\nDone."
            mock_eval_proc.stderr = ""

            orig_copy2 = shutil.copy2
            copy_count = 0
            has_failed = False

            def failing_copy2(src, dst, *args, **kwargs):
                nonlocal copy_count, has_failed
                dst_path = Path(dst)
                # During publication phase (before has_failed), count copies into test_eval_dir
                if not has_failed and str(test_eval_dir) in str(dst_path):
                    copy_count += 1
                    # Copy 1: evaluator-briefing.md (succeeds)
                    # Copy 2: evaluator-stdout.txt (succeeds)
                    # Copy 3: evaluator-stderr.txt (succeeds)
                    # Copy 4: evaluator-verdict.json -> INJECT FAILURE HERE!
                    if copy_count >= 4:
                        has_failed = True
                        raise OSError("Injected evaluator disk failure on fourth publication copy")
                return orig_copy2(src, dst, *args, **kwargs)

            orig_exists = Path.exists
            stat_error_injected = False

            def failing_exists(path_self):
                nonlocal stat_error_injected
                # During rollback, only fail stat for the briefing backup file
                if has_failed and "backup_" in str(path_self) and "evaluator-briefing.md" in str(path_self):
                    stat_error_injected = True
                    raise OSError("Injected OS error querying briefing backup stat")
                return orig_exists(path_self)

            with patch("subprocess.run", return_value=mock_eval_proc):
                with patch("shutil.copy2", side_effect=failing_copy2):
                    with patch.object(Path, "exists", failing_exists):
                        with self.assertRaises(RuntimeError) as ctx:
                            run_evaluator.run_evaluation(eval_dir=test_eval_dir, key_file=dummy_key)

                        exc_msg = str(ctx.exception)
                        self.assertIn("ROLLBACK FAILED / INCOMPLETE", exc_msg)
                        self.assertIn("Failed to check existence/stat of backup file", exc_msg)
                        self.assertTrue(has_failed, "Publication failure on copy 4 was never injected!")
                        self.assertTrue(stat_error_injected, "Stat error on briefing backup was never injected!")

                        # Critical R11/R12 checks:
                        # 1. Canary remains untouched
                        self.assertEqual(canary_file.read_text(encoding="utf-8"), "canary data")

                        # 2. Subsequent pre-existing destination (evaluator-stdout.txt) was restored byte-by-byte from backup!
                        self.assertEqual(stdout_file.read_text(encoding="utf-8"), "prior stdout content")
                        self.assertEqual(hashlib.sha256(stdout_file.read_bytes()).hexdigest(), orig_stdout_hash)

                        # 3. Subsequent newly created destination (evaluator-stderr.txt) was unlinked and removed!
                        self.assertFalse(stderr_file.exists(), "Subsequent newly created file was not unlinked!")

                        # 4. Failed fourth destination was not left behind
                        self.assertFalse((test_eval_dir / "evaluator-verdict.json").exists())


if __name__ == "__main__":
    unittest.main()

