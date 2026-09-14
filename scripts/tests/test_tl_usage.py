#!/usr/bin/env python3
"""
test_tl_usage.py - Deterministic test suite for scripts/tl_usage.py (Task T025).
Covers CLI parsing, fixture parsing, field-by-field reconciliation, anti-sum invariant,
multi-context preservation, thread topology, timing semantics, privacy, completeness,
rate-limit extraction, zero network/subprocess, strict literal counters, streaming,
and pure stdlib schema validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tl_usage import (
    DERIVATION_ID_UNCACHED,
    compute_sha256,
    enforce_schema_validation,
    format_counter,
    is_recognized_codex_event,
    parse_codex_rollout,
    reconcile_field,
    validate_against_schema,
)


class TestTLUsageCLI(unittest.TestCase):
    """Test CLI argument parsing and error handling."""

    def test_missing_required_args(self) -> None:
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "tl_usage.py")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("the following arguments are required", res.stderr)

    def test_missing_file_error(self) -> None:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--run-id", "test-run",
            "--session-ref", "/nonexistent/path/to/rollout.jsonl",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not found", res.stderr)

    def test_output_file_argument(self) -> None:
        fixture_path = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex" / "01_single_turn_complete.jsonl"
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tl_usage.py"),
                "--run-id", "test-cli-out",
                "--session-ref", str(fixture_path),
                "--output", tmp_path,
                "--verify-schema",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

            with open(tmp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["run_id"], "test-cli-out")
            self.assertEqual(data["completeness"]["status"], "complete")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_text_format(self) -> None:
        fixture_path = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex" / "01_single_turn_complete.jsonl"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--run-id", "test-cli-text",
            "--session-ref", str(fixture_path),
            "--format", "text",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Run ID: test-cli-text", res.stdout)
        self.assertIn("Completeness: complete", res.stdout)


class TestTLUsageFixtures(unittest.TestCase):
    """Test parsing across all synthetic fixtures (positive and negative)."""

    def setUp(self) -> None:
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex"
        self.schema_file = REPO_ROOT / "schemas" / "usage-observation.schema.json"

    def test_fixture_01_single_turn(self) -> None:
        fpath = self.fixtures_dir / "01_single_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-01")

        self.assertEqual(obs["run_id"], "run-01")
        self.assertEqual(obs["harness"], "codex")
        self.assertEqual(obs["harness_version"], "0.153.0")
        self.assertEqual(obs["completeness"]["status"], "complete")
        self.assertEqual(obs["parser_status"]["status"], "supported")

        # Check raw usage
        cum = obs["raw_usage"]["cumulative"]
        self.assertEqual(cum["input_tokens"], 1000)
        self.assertEqual(cum["cached_input_tokens"], 200)
        self.assertEqual(cum["output_tokens"], 150)
        self.assertEqual(cum["reasoning_output_tokens"], 50)
        self.assertEqual(cum["total_tokens"], 1150)

        # Check reconciliation
        recon = obs["raw_usage"]["reconciliation"]
        self.assertEqual(recon["status"], "reconciled")
        self.assertEqual(recon["fields"]["input_tokens"]["status"], "reconciled")
        self.assertEqual(recon["fields"]["input_tokens"]["delta"], 0)

        # Check derived usage (R2: Invariant I5 - strictly not_observable)
        self.assertEqual(obs["derived_usage"]["uncached_input_tokens"], "not_observable")

        # Check rate limits
        self.assertEqual(len(obs["rate_limits"]), 1)
        rl = obs["rate_limits"][0]
        self.assertEqual(rl["scope"], "account")
        self.assertEqual(rl["attribution"], "unknown")
        self.assertEqual(rl["primary"]["used_percent"], 10.0)

        # Validate schema using pure stdlib
        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_02_multi_turn_reconciliation(self) -> None:
        fpath = self.fixtures_dir / "02_multi_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-02")

        self.assertEqual(obs["completeness"]["status"], "complete")
        self.assertEqual(obs["raw_usage"]["response_count"], 3)

        # Cumulative snapshot must equal the 3rd turn total, not the sum of 3 snapshots!
        cum = obs["raw_usage"]["cumulative"]
        self.assertEqual(cum["total_tokens"], 4950)

        per_sum = obs["raw_usage"]["per_response_sum"]
        self.assertEqual(per_sum["total_tokens"], 4950)

        self.assertEqual(obs["raw_usage"]["reconciliation"]["status"], "reconciled")
        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_03_multi_model_effort(self) -> None:
        fpath = self.fixtures_dir / "03_multi_model_effort.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-03")

        self.assertEqual(obs["completeness"]["status"], "complete")
        contexts = obs["observed_contexts"]
        self.assertEqual(len(contexts), 2)

        models = {c["model"] for c in contexts}
        self.assertIn("gpt-5.6-terra", models)
        self.assertIn("gpt-5.6-luna", models)

        efforts = {c["effort"] for c in contexts}
        self.assertIn("high", efforts)
        self.assertIn("medium", efforts)

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_04_subthreads(self) -> None:
        """R1: Thread topology, root persistence, and agent roles preservation."""
        fpath = self.fixtures_dir / "04_subthreads.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-04")

        self.assertEqual(obs["completeness"]["status"], "complete")

        # R1: Root thread id remains intact and is never overwritten by child session_meta
        self.assertEqual(obs["thread_topology"]["root_thread_id"], "thread-root-04")

        threads = obs["thread_topology"]["threads"]
        self.assertEqual(len(threads), 4)

        thread_map = {t["thread_id"]: t for t in threads}
        self.assertIn("thread-root-04", thread_map)
        self.assertEqual(thread_map["thread-root-04"]["role"], "root")
        self.assertIsNone(thread_map["thread-root-04"]["parent_thread_id"])

        self.assertIn("thread-child-01", thread_map)
        self.assertEqual(thread_map["thread-child-01"]["role"], "guardian")
        self.assertEqual(thread_map["thread-child-01"]["parent_thread_id"], "thread-root-04")

        self.assertIn("thread-child-02", thread_map)
        self.assertEqual(thread_map["thread-child-02"]["role"], "auto_review")
        self.assertEqual(thread_map["thread-child-02"]["parent_thread_id"], "thread-root-04")

        self.assertIn("thread-child-03", thread_map)
        self.assertEqual(thread_map["thread-child-03"]["role"], "child")
        self.assertEqual(thread_map["thread-child-03"]["parent_thread_id"], "thread-root-04")

        roles = {t["role"] for t in threads}
        self.assertEqual(roles, {"root", "guardian", "auto_review", "child"})

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_05_truncated_never_complete(self) -> None:
        fpath = self.fixtures_dir / "05_truncated.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-05")

        # Invariant I10: Truncated rollout must never result in complete!
        self.assertEqual(obs["completeness"]["status"], "incomplete")
        self.assertEqual(obs["parser_status"]["status"], "partial")
        self.assertTrue(any("truncated" in r for r in obs["completeness"]["reasons"]))

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_06_malformed_json_handled_gracefully(self) -> None:
        fpath = self.fixtures_dir / "06_malformed_json.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-06")

        # Invariant I10: JSON syntax error must never result in complete!
        self.assertEqual(obs["completeness"]["status"], "incomplete")
        self.assertEqual(obs["parser_status"]["status"], "partial")
        self.assertTrue(any("syntax_error" in r for r in obs["completeness"]["reasons"]))

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_07_missing_fields_not_observable(self) -> None:
        fpath = self.fixtures_dir / "07_missing_fields.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-07")

        # Invariant I3: Missing fields must be "not_observable", NEVER 0!
        cum = obs["raw_usage"]["cumulative"]
        self.assertEqual(cum["cached_input_tokens"], "not_observable")
        self.assertEqual(cum["reasoning_output_tokens"], "not_observable")
        self.assertEqual(cum["input_tokens"], 800)

        # Invariant I4 & I5: Uncached derivation strictly not_observable
        self.assertEqual(obs["derived_usage"]["uncached_input_tokens"], "not_observable")

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")

    def test_fixture_08_unsupported_alien_format(self) -> None:
        """R3: Alien format recognition resulting in unsupported status."""
        fpath = self.fixtures_dir / "08_unsupported_alien_format.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-08")

        self.assertEqual(obs["parser_status"]["status"], "unsupported")
        self.assertIn("unrecognized_event_schema_for_codex", obs["parser_status"]["reasons"])
        self.assertEqual(obs["completeness"]["status"], "not_observable")

        valid, errs = validate_against_schema(obs, str(self.schema_file))
        self.assertTrue(valid, f"Schema validation failed: {errs}")


class TestTLUsageInvariants(unittest.TestCase):
    """Detailed unit tests for protocol invariants and R1-R6 requirements."""

    def setUp(self) -> None:
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex"
        self.schema_file = REPO_ROOT / "schemas" / "usage-observation.schema.json"

    def test_reconcile_homologous_fields(self) -> None:
        # Reconciled
        r1 = reconcile_field(100, 100)
        self.assertEqual(r1["status"], "reconciled")
        self.assertEqual(r1["delta"], 0)

        # Divergent
        r2 = reconcile_field(120, 100)
        self.assertEqual(r2["status"], "divergent")
        self.assertEqual(r2["delta"], 20)

        # Not observable
        r3 = reconcile_field("not_observable", 100)
        self.assertEqual(r3["status"], "not_observable")
        self.assertIsNone(r3["delta"])

    def test_r4_strict_literal_counter_formatting(self) -> None:
        """R4: format_counter strictly accepts int >= 0, rejecting str, float, bool, etc."""
        # Accepted: strictly non-boolean int >= 0
        self.assertEqual(format_counter(0), 0)
        self.assertEqual(format_counter(42), 42)
        self.assertEqual(format_counter(1000000), 1000000)

        # Categorically rejected -> "not_observable"
        self.assertEqual(format_counter("100"), "not_observable")
        self.assertEqual(format_counter("0"), "not_observable")
        self.assertEqual(format_counter(""), "not_observable")
        self.assertEqual(format_counter(100.5), "not_observable")
        self.assertEqual(format_counter(0.0), "not_observable")
        self.assertEqual(format_counter(True), "not_observable")
        self.assertEqual(format_counter(False), "not_observable")
        self.assertEqual(format_counter(-5), "not_observable")
        self.assertEqual(format_counter(None), "not_observable")
        self.assertEqual(format_counter([]), "not_observable")
        self.assertEqual(format_counter({}), "not_observable")
        self.assertEqual(format_counter("not_observable"), "not_observable")

    def test_r4_per_response_sum_non_integer_rejection(self) -> None:
        """R4: Per-response sum ignores non-integers and emits not_observable if none valid."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"type": "session_meta", "payload": {"id": "th-1"}}) + "\n")
            tmp.write(json.dumps({"type": "turn_context", "payload": {"turn_id": "t-1"}}) + "\n")
            # First delta has invalid string and float and bool
            tmp.write(json.dumps({
                "type": "token_usage_record",
                "payload": {"usage": {"input_tokens": "100", "output_tokens": 50.5, "total_tokens": True}}
            }) + "\n")
            # Second delta has valid int for input_tokens, but none for output_tokens
            tmp.write(json.dumps({
                "type": "token_usage_record",
                "payload": {"usage": {"input_tokens": 200, "output_tokens": False}}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r4-sum")
            per_sum = obs["raw_usage"]["per_response_sum"]
            # input_tokens had "100" (ignored) and 200 (valid) -> sum 200
            self.assertEqual(per_sum["input_tokens"], 200)
            # output_tokens had 50.5 and False -> no valid ints -> "not_observable"
            self.assertEqual(per_sum["output_tokens"], "not_observable")
            # total_tokens had True -> "not_observable"
            self.assertEqual(per_sum["total_tokens"], "not_observable")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r2_invariant_i5_counterfactual_probe(self) -> None:
        """R2: Probe counterfactually against ad-hoc subtraction input_tokens - cached_input_tokens."""
        fpath = self.fixtures_dir / "01_single_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-i5-probe")

        # Factual values in fixture: input_tokens=1000, cached_input_tokens=200
        self.assertEqual(obs["raw_usage"]["cumulative"]["input_tokens"], 1000)
        self.assertEqual(obs["raw_usage"]["cumulative"]["cached_input_tokens"], 200)

        # Ad-hoc subtraction would compute 1000 - 200 = 800
        # Invariant I5 requires that uncached_input_tokens is strictly "not_observable"
        uncached = obs["derived_usage"]["uncached_input_tokens"]
        self.assertEqual(uncached, "not_observable")
        self.assertNotEqual(uncached, 800)
        self.assertNotEqual(uncached, 800.0)
        self.assertFalse(isinstance(uncached, dict))

    def test_r1_root_never_overwritten_by_child_session_meta(self) -> None:
        """R1: Root thread id is never overwritten by subsequent child session_meta."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "type": "session_meta",
                "payload": {"id": "root-thread-original", "parent_thread_id": None}
            }) + "\n")
            tmp.write(json.dumps({
                "type": "session_meta",
                "payload": {"id": "child-thread-01", "parent_thread_id": "root-thread-original", "agent_role": "guardian"}
            }) + "\n")
            tmp.write(json.dumps({
                "type": "session_meta",
                "payload": {"id": "child-thread-02", "parent_thread_id": "root-thread-original", "agent_role": "auto_review"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r1")
            self.assertEqual(obs["thread_topology"]["root_thread_id"], "root-thread-original")
            roles_by_id = {t["thread_id"]: t["role"] for t in obs["thread_topology"]["threads"]}
            self.assertEqual(roles_by_id["root-thread-original"], "root")
            self.assertEqual(roles_by_id["child-thread-01"], "guardian")
            self.assertEqual(roles_by_id["child-thread-02"], "auto_review")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r1_out_of_order_child_before_parent(self) -> None:
        """R1: Explicit counterfactual test where child session_meta on line 1 appears before parent session_meta."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T16:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "thread-child-out-of-order",
                    "parent_thread_id": "thread-root-main",
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T16:00:01.000Z",
                "type": "session_meta",
                "payload": {
                    "session_id": "sess-main",
                    "id": "thread-root-main",
                    "parent_thread_id": None,
                    "cli_version": "0.153.0"
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T16:00:02.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "t-1", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T16:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r1-ooo")
            # Root thread must be deterministically resolved to the parent
            self.assertEqual(obs["thread_topology"]["root_thread_id"], "thread-root-main")
            thread_map = {t["thread_id"]: t for t in obs["thread_topology"]["threads"]}
            self.assertIn("thread-child-out-of-order", thread_map)
            self.assertEqual(thread_map["thread-child-out-of-order"]["role"], "child")
            self.assertEqual(thread_map["thread-child-out-of-order"]["parent_thread_id"], "thread-root-main")
            self.assertIn("thread-root-main", thread_map)
            self.assertEqual(thread_map["thread-root-main"]["role"], "root")
            self.assertIsNone(thread_map["thread-root-main"]["parent_thread_id"])

            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r3_hollow_and_alien_events_classification(self) -> None:
        """R3 & R18: Counterfactual tests with synthetic hollow, alien, and non-landmark events."""
        # 1. Hollow response_item without payload (unrecognized event structure -> partial)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"type": "response_item"}) + "\n")
            p1 = tmp.name

        # 2. Alien tool chat_message (unrecognized event type -> partial)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"type": "chat_message", "content": "hello alien tool"}) + "\n")
            p2 = tmp.name

        # 3. Hollow session_meta without payload (unrecognized event structure -> partial)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"type": "session_meta"}) + "\n")
            p3 = tmp.name

        # 4. Alien format without event type envelope -> unsupported
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"log_level": "INFO", "msg": "alien non-event record"}) + "\n")
            p4 = tmp.name

        # 5. Non-landmark recognized event without landmarks -> unsupported
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({"type": "response_item", "payload": {"data": 1}}) + "\n")
            p5 = tmp.name

        try:
            obs1 = parse_codex_rollout(p1, run_id="run-r3-hollow")
            self.assertEqual(obs1["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_structure:response_item" in r for r in obs1["parser_status"]["reasons"]))
            valid1, errs1 = validate_against_schema(obs1, str(self.schema_file))
            self.assertTrue(valid1, f"Schema error: {errs1}")

            obs2 = parse_codex_rollout(p2, run_id="run-r3-alien")
            self.assertEqual(obs2["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_structure:chat_message" in r for r in obs2["parser_status"]["reasons"]))
            valid2, errs2 = validate_against_schema(obs2, str(self.schema_file))
            self.assertTrue(valid2, f"Schema error: {errs2}")

            obs3 = parse_codex_rollout(p3, run_id="run-r3-hollow-meta")
            self.assertEqual(obs3["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_structure:session_meta" in r for r in obs3["parser_status"]["reasons"]))
            valid3, errs3 = validate_against_schema(obs3, str(self.schema_file))
            self.assertTrue(valid3, f"Schema error: {errs3}")

            obs4 = parse_codex_rollout(p4, run_id="run-r3-alien-non-event")
            self.assertEqual(obs4["parser_status"]["status"], "unsupported")
            self.assertIn("unrecognized_event_schema_for_codex", obs4["parser_status"]["reasons"])
            valid4, errs4 = validate_against_schema(obs4, str(self.schema_file))
            self.assertTrue(valid4, f"Schema error: {errs4}")

            obs5 = parse_codex_rollout(p5, run_id="run-r3-recognized-no-landmarks")
            self.assertEqual(obs5["parser_status"]["status"], "unsupported")
            self.assertIn("unrecognized_event_schema_for_codex", obs5["parser_status"]["reasons"])
            valid5, errs5 = validate_against_schema(obs5, str(self.schema_file))
            self.assertTrue(valid5, f"Schema error: {errs5}")
        finally:
            for p in (p1, p2, p3, p4, p5):
                if os.path.exists(p):
                    os.remove(p)

    def test_r5_streaming_large_rollout_bounded_memory(self) -> None:
        """R5: Probe test with 1,000+ synthetic events verifying O(1) bounded memory and observation success."""
        num_events = 1200
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            # Session meta
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T12:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-large-01", "session_id": "sess-large", "cli_version": "0.153.0"}
            }) + "\n")
            # Turn context
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T12:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-large-01", "model": "gpt-5.6-terra", "effort": "high"}
            }) + "\n")
            # 1,200 token_count events
            for i in range(num_events):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T12:00:02.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "turn_id": "turn-large-01",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 10 * (i + 1),
                                "output_tokens": 5 * (i + 1),
                                "total_tokens": 15 * (i + 1),
                            },
                            "last_token_usage": {
                                "input_tokens": 10,
                                "output_tokens": 5,
                                "total_tokens": 15,
                            }
                        }
                    }
                }) + "\n")
            # Terminal event
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T12:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-large-r5")
            self.assertEqual(obs["completeness"]["status"], "complete")
            self.assertEqual(obs["parser_status"]["status"], "supported")
            self.assertEqual(obs["raw_usage"]["response_count"], num_events)

            # Cumulative reflects latest snapshot
            self.assertEqual(obs["raw_usage"]["cumulative"]["total_tokens"], 15 * num_events)
            self.assertEqual(obs["raw_usage"]["cumulative"]["input_tokens"], 10 * num_events)
            self.assertEqual(obs["raw_usage"]["cumulative"]["output_tokens"], 5 * num_events)

            # Per-response sum is sum of all deltas
            self.assertEqual(obs["raw_usage"]["per_response_sum"]["total_tokens"], 15 * num_events)
            self.assertEqual(obs["raw_usage"]["per_response_sum"]["input_tokens"], 10 * num_events)
            self.assertEqual(obs["raw_usage"]["per_response_sum"]["output_tokens"], 5 * num_events)
            self.assertEqual(obs["raw_usage"]["reconciliation"]["status"], "reconciled")

            # Verify no unbounded lists in output structure
            self.assertLessEqual(len(obs["observed_contexts"]), 2)
            self.assertLessEqual(len(obs["thread_topology"]["threads"]), 2)
            self.assertLessEqual(len(obs["rate_limits"]), 2)

            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r7_robust_timing_span_with_invalid_and_interleaved_timestamps(self) -> None:
        """R7: Calculate timing span strictly over valid timestamps, ignoring invalid ones."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            # Line 1: Invalid timestamp at the beginning
            tmp.write(json.dumps({
                "timestamp": "INVALID_DATE_FORMAT",
                "type": "session_meta",
                "payload": {"id": "th-time-1", "session_id": "sess-time"}
            }) + "\n")
            # Line 2: First valid timestamp (T0 = 10:00:00)
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T10:00:00.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-1", "model": "gpt-5.6-terra"}
            }) + "\n")
            # Line 3: Interleaved valid timestamp (T1 = 10:00:15)
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T10:00:15.000Z",
                "type": "event_msg",
                "payload": {"type": "turn_start", "turn_id": "turn-1"}
            }) + "\n")
            # Line 4: Interleaved invalid timestamp (empty string)
            tmp.write(json.dumps({
                "timestamp": "",
                "type": "event_msg",
                "payload": {"type": "item_completed"}
            }) + "\n")
            # Line 5: Last valid timestamp at the end (T2 = 10:00:37.500)
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T10:00:37.500Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r7-timing")
            timing = obs["timing"]
            # Expected span: 10:00:37.500 - 10:00:00.000 = 37.5 seconds
            self.assertEqual(timing["observed_session_span_seconds"], 37.5)
            self.assertEqual(timing["first_timestamp"], "2026-06-25T10:00:00.000Z")
            self.assertEqual(timing["last_timestamp"], "2026-06-25T10:00:37.500Z")
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_timing_semantics(self) -> None:
        fpath = self.fixtures_dir / "01_single_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-time")

        timing = obs["timing"]
        self.assertEqual(timing["observed_session_span_seconds"], 12.0)
        self.assertEqual(timing["source"], "rollout_first_last_timestamp")
        self.assertEqual(timing["job_wall_seconds"], "not_observable")
        self.assertEqual(timing["model_latency_seconds"], "not_observable")

    def test_privacy_no_private_paths_leak(self) -> None:
        fpath = self.fixtures_dir / "01_single_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-priv")
        obs_json = json.dumps(obs)

        self.assertNotIn(str(fpath), obs_json)
        self.assertNotIn("/Users/", obs_json)
        self.assertNotIn("~/.codex", obs_json)

    def test_rate_limits_account_scoped(self) -> None:
        fpath = self.fixtures_dir / "01_single_turn_complete.jsonl"
        obs = parse_codex_rollout(str(fpath), run_id="run-rl")

        for rl in obs["rate_limits"]:
            self.assertEqual(rl["scope"], "account")
            self.assertEqual(rl["attribution"], "unknown")
            self.assertNotIn("usd", json.dumps(rl).lower())


class TestR6PureStdlibSchemaValidation(unittest.TestCase):
    """Test pure Python standard library Draft 2020-12 schema validation."""

    def setUp(self) -> None:
        self.schema_file = str(REPO_ROOT / "schemas" / "usage-observation.schema.json")
        fpath = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex" / "01_single_turn_complete.jsonl"
        self.valid_obs = parse_codex_rollout(str(fpath), run_id="run-valid-schema")

    def test_no_jsonschema_module_imported(self) -> None:
        """R6: Guarantee no dependency on the third-party jsonschema package."""
        import scripts.tl_usage
        self.assertNotIn("jsonschema", sys.modules)

    def test_valid_observation_passes(self) -> None:
        valid, errs = validate_against_schema(self.valid_obs, self.schema_file)
        self.assertTrue(valid, f"Expected valid observation, got errors: {errs}")

    def test_missing_required_property_fails(self) -> None:
        mutated = dict(self.valid_obs)
        del mutated["raw_usage"]
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("missing required property 'raw_usage'" in e for e in errs))

    def test_additional_property_fails(self) -> None:
        mutated = dict(self.valid_obs)
        mutated["unexpected_field_xyz"] = 123
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("unexpected additional property 'unexpected_field_xyz'" in e for e in errs))

    def test_invalid_type_fails(self) -> None:
        mutated = json.loads(json.dumps(self.valid_obs))
        mutated["raw_usage"]["response_count"] = "not_an_integer"
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("expected type integer" in e for e in errs))

    def test_invalid_enum_fails(self) -> None:
        mutated = json.loads(json.dumps(self.valid_obs))
        mutated["harness"] = "alien_harness"
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("not in enum" in e for e in errs))

    def test_invalid_pattern_fails(self) -> None:
        mutated = json.loads(json.dumps(self.valid_obs))
        mutated["session_ref_digest"] = "invalid_sha256_short"
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("does not match pattern" in e for e in errs))

    def test_minimum_constraint_fails(self) -> None:
        mutated = json.loads(json.dumps(self.valid_obs))
        mutated["raw_usage"]["response_count"] = -1
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("< minimum" in e for e in errs))

    def test_oneOf_constraint_fails_on_invalid_value(self) -> None:
        mutated = json.loads(json.dumps(self.valid_obs))
        # counter_value allows int >= 0 or const "not_observable"
        mutated["raw_usage"]["cumulative"]["input_tokens"] = "invalid_string"
        valid, errs = validate_against_schema(mutated, self.schema_file)
        self.assertFalse(valid)
        self.assertTrue(any("oneOf" in e for e in errs))


class TestReviewRound03Requirements(unittest.TestCase):
    """Specific regression tests for Review Round 03 Action Items (R9, R10, R11, R12)."""

    def setUp(self) -> None:
        self.schema_file = REPO_ROOT / "schemas" / "usage-observation.schema.json"
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex"

    def test_r9_atomic_single_pass_hashing(self) -> None:
        """R9: Digest is computed atomically during stream reading on the same descriptor."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r9", "session_id": "sess-r9", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r9", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                expected_sha256 = hashlib.sha256(f.read()).hexdigest()

            obs = parse_codex_rollout(tmp_path, run_id="run-r9-atomic")
            self.assertEqual(obs["session_ref_digest"], expected_sha256)
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r10_unsupported_harness_version_classified_as_partial(self) -> None:
        """R10: Unsupported or unverified harness version classifies parser_status as partial."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r10", "session_id": "sess-r10", "cli_version": "99.9.9-alien"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r10", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r10-version")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertTrue(any("unsupported_or_untested_harness_version:99.9.9-alien" in r for r in obs["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r11_metadata_normalization_and_unconditional_schema_compliance(self) -> None:
        """R11: Non-string versions and malformed rate limits are normalized to satisfy Draft 2020-12."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            # Numeric cli_version and session_id
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r11", "session_id": 123456, "cli_version": 153}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r11", "model": "gpt-5.6-terra"}
            }) + "\n")
            # Malformed rate limits with strings instead of numbers
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "limit_id": "primary-limit",
                        "primary": {
                            "used_percent": "bad_percentage_string",
                            "window_minutes": "sixty",
                            "resets_at": "never"
                        }
                    }
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:03.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r11-normalization")
            self.assertEqual(obs["harness_version"], "153")
            self.assertEqual(obs["thread_topology"]["session_id"], "123456")
            self.assertEqual(len(obs["rate_limits"]), 1)
            rl = obs["rate_limits"][0]
            self.assertIsNone(rl["primary"]["used_percent"])
            self.assertIsNone(rl["primary"]["window_minutes"])
            self.assertIsNone(rl["primary"]["resets_at"])
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r12_bounded_memory_retention_caps(self) -> None:
        """R12: Retention caps prevent unbounded growth in rate limits, threads, contexts and reasons."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-root-r12", "session_id": "sess-r12", "cli_version": "0.153.0"}
            }) + "\n")

            # 120 distinct subthreads
            for i in range(120):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:01.{i % 1000:03d}Z",
                    "type": "session_meta",
                    "payload": {"id": f"th-child-{i}", "parent_thread_id": "th-root-r12"}
                }) + "\n")

            # 70 distinct model/effort contexts
            for i in range(70):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:02.{i % 1000:03d}Z",
                    "type": "turn_context",
                    "payload": {"turn_id": f"turn-ctx-{i}", "model": f"model-{i}", "effort": "high"}
                }) + "\n")

            # 80 distinct rate limits
            for i in range(80):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:03.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "limit_id": f"rate-limit-{i}",
                            "primary": {"used_percent": 10.0, "window_minutes": 60.0, "resets_at": 100.0}
                        }
                    }
                }) + "\n")

            # 70 syntax errors
            for i in range(70):
                tmp.write(f"MALFORMED_JSON_LINE_{i}\n")

            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r12-caps")
            # Check caps
            self.assertLessEqual(len(obs["rate_limits"]), 50)
            self.assertLessEqual(len(obs["thread_topology"]["threads"]), 100)
            self.assertLessEqual(len(obs["observed_contexts"]), 50)
            self.assertLessEqual(len(obs["completeness"]["reasons"]), 50)
            self.assertEqual(len(obs["completeness"]["reasons"]), 50)
            self.assertIn("additional_reasons_truncated", obs["completeness"]["reasons"])

            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r13_supported_classification_policy_and_counterfactuals(self) -> None:
        """R13: supported status requires proven version and format fingerprint covered by fixtures.
        
        Counterfactual probes:
        1. Missing cli_version -> partial ('missing_or_unverified_harness_version')
        2. Unverified CLI prefix/version (0.154.0) -> partial ('unsupported_or_untested_harness_version:0.154.0')
        3. Unknown/untested format fingerprint -> partial ('unsupported_source_format_fingerprint:...')
        4. Valid fixture 09 with 0.153.4 -> supported with fingerprint 487c9d7026a20365.
        """
        # 1. Fixture 09: Proven version 0.153.4 and proven fingerprint 487c9d7026a20365
        f09 = self.fixtures_dir / "09_codex_0_153_4.jsonl"
        obs_09 = parse_codex_rollout(str(f09), run_id="run-r13-f09")
        self.assertEqual(obs_09["harness_version"], "0.153.4")
        self.assertEqual(obs_09["source_format_fingerprint"], "487c9d7026a20365")
        self.assertEqual(obs_09["parser_status"]["status"], "supported")
        self.assertEqual(obs_09["completeness"]["status"], "complete")

        # 2. Counterfactual: Missing cli_version
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-no-ver", "session_id": "sess-no-ver"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-no-ver", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_no_ver = tmp.name

        try:
            obs_no_ver = parse_codex_rollout(tmp_no_ver, run_id="run-r13-no-ver")
            self.assertEqual(obs_no_ver["parser_status"]["status"], "partial")
            self.assertIn("missing_or_unverified_harness_version", obs_no_ver["parser_status"]["reasons"])
            self.assertIsNone(obs_no_ver["harness_version"])
        finally:
            if os.path.exists(tmp_no_ver):
                os.remove(tmp_no_ver)

        # 3. Counterfactual: Unverified version prefix (0.154.0 without fixture)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-untested", "session_id": "sess-untested", "cli_version": "0.154.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-untested", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_untested = tmp.name

        try:
            obs_untested = parse_codex_rollout(tmp_untested, run_id="run-r13-untested")
            self.assertEqual(obs_untested["parser_status"]["status"], "partial")
            self.assertTrue(any("unsupported_or_untested_harness_version:0.154.0" in r for r in obs_untested["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_untested):
                os.remove(tmp_untested)

        # 4. Counterfactual: Unknown / alien format fingerprint
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-fp-alien", "session_id": "sess-fp-alien", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-fp-alien", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "unheard_novel_event_type",
                "payload": {"info": "something novel"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_fp_alien = tmp.name

        try:
            obs_alien = parse_codex_rollout(tmp_fp_alien, run_id="run-r13-fp-alien")
            self.assertEqual(obs_alien["parser_status"]["status"], "partial")
            self.assertTrue(any("unsupported_source_format_fingerprint:" in r for r in obs_alien["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_fp_alien):
                os.remove(tmp_fp_alien)

    def test_r14_unconditional_schema_validation_and_fail_closed(self) -> None:
        """R14: Schema validation is unconditional across all paths and fails closed."""
        # 1. Early return on empty file is validated against schema
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write("\n\n")
            tmp_empty = tmp.name

        try:
            obs_empty = parse_codex_rollout(tmp_empty, run_id="run-r14-empty")
            self.assertEqual(obs_empty["parser_status"]["status"], "unsupported")
            valid, errs = validate_against_schema(obs_empty, str(self.schema_file))
            self.assertTrue(valid, f"Empty observation must satisfy schema: {errs}")
        finally:
            if os.path.exists(tmp_empty):
                os.remove(tmp_empty)

        # 2. Early return on alien format fixture is validated against schema
        f_alien = self.fixtures_dir / "08_unsupported_alien_format.jsonl"
        obs_alien = parse_codex_rollout(str(f_alien), run_id="run-r14-alien")
        self.assertEqual(obs_alien["parser_status"]["status"], "unsupported")
        valid, errs = validate_against_schema(obs_alien, str(self.schema_file))
        self.assertTrue(valid, f"Alien format observation must satisfy schema: {errs}")

        # 3. Fail closed on missing schema
        import unittest.mock as mock
        with mock.patch("pathlib.Path.exists", return_value=False):
            with self.assertRaises(FileNotFoundError):
                enforce_schema_validation(obs_alien)

    def test_r15_strict_retention_caps_adversarial(self) -> None:
        """R15: Strict caps on reasons (<=50), seen_event_types (<=20), and latest_cum fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r15", "session_id": "sess-r15", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r15", "model": "gpt-5.6-terra"}
            }) + "\n")

            # 70 non-dict JSON scalar lines to flood parser_reasons
            for i in range(70):
                tmp.write(json.dumps(f"scalar_string_{i}") + "\n")

            # 40 distinct event types to test seen_event_types cap
            for i in range(40):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:02.{i % 1000:03d}Z",
                    "type": f"adversarial_event_type_{i}",
                    "payload": {}
                }) + "\n")

            # Adversarial token_count with 50 non-contractual keys
            adversarial_tot = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
            for i in range(50):
                adversarial_tot[f"adversarial_key_{i}"] = 999

            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:03.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": adversarial_tot}
                }
            }) + "\n")

            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r15-adversarial")
            # parser_reasons cap is strictly <= 50 (never 51)
            self.assertLessEqual(len(obs["parser_status"]["reasons"]), 50)
            self.assertEqual(len(obs["parser_status"]["reasons"]), 50)
            self.assertIn("additional_reasons_truncated", obs["parser_status"]["reasons"])

            # Cumulative token usage contains ONLY the 6 contractual keys
            counter_fields = {
                "input_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            }
            self.assertEqual(set(obs["raw_usage"]["cumulative"].keys()), counter_fields)
            for k in obs["raw_usage"]["cumulative"].keys():
                self.assertFalse(k.startswith("adversarial_key_"))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r16_rate_limit_deduplication_strictly_by_limit_id(self) -> None:
        """R16: Rate limits are deduplicated strictly by limit_id, retaining the latest snapshot."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r16", "session_id": "sess-r16", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r16", "model": "gpt-5.6-terra"}
            }) + "\n")

            # Rate limit snapshot 1: limit_id: 'codex', plan_type: 'free'
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "limit_id": "codex",
                        "plan_type": "free",
                        "primary": {"used_percent": 20.0, "window_minutes": 300, "resets_at": 1700000000}
                    }
                }
            }) + "\n")

            # Rate limit snapshot 2: same limit_id: 'codex', changed plan_type: 'pro'
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:03.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "limit_id": "codex",
                        "plan_type": "pro",
                        "primary": {"used_percent": 5.0, "window_minutes": 300, "resets_at": 1700000500}
                    }
                }
            }) + "\n")

            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_codex_rollout(tmp_path, run_id="run-r16-rate-limits")
            # Must contain exactly 1 entry for limit_id 'codex'
            self.assertEqual(len(obs["rate_limits"]), 1)
            rl = obs["rate_limits"][0]
            self.assertEqual(rl["limit_id"], "codex")
            # Must reflect the latest snapshot ('pro' with used_percent: 5.0)
            self.assertEqual(rl["plan_type"], "pro")
            self.assertEqual(rl["primary"]["used_percent"], 5.0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r17_unrecognized_event_or_subtype_forces_partial(self) -> None:
        """R17: Any unrecognized event, subtype, or structure forces parser_status to partial with explicit reason."""
        # 1. Counterfactual probe: event_msg with unknown subtype (e.g. future_unrecognized_event)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r17-sub", "session_id": "sess-r17-sub", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r17-sub", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {"type": "future_unrecognized_event", "turn_id": "turn-r17-sub"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_sub = tmp.name

        try:
            obs = parse_codex_rollout(tmp_sub, run_id="run-r17-sub")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_msg_subtype:future_unrecognized_event" in r for r in obs["parser_status"]["reasons"]))
            self.assertEqual(obs["completeness"]["status"], "complete")
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_sub):
                os.remove(tmp_sub)

        # 2. Counterfactual probe: unrecognized top-level event structure with legitimate landmarks
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r17-top", "session_id": "sess-r17-top", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-r17-top", "model": "gpt-5.6-terra"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "future_top_level_event",
                "payload": {"unknown_field": 123}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_top = tmp.name

        try:
            obs_top = parse_codex_rollout(tmp_top, run_id="run-r17-top")
            self.assertEqual(obs_top["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_structure:future_top_level_event" in r for r in obs_top["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs_top, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_top):
                os.remove(tmp_top)

        # 3. Cap resilience: 70 non-dict JSON lines preceding unrecognized event
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r17-cap", "session_id": "sess-r17-cap", "cli_version": "0.153.0"}
            }) + "\n")
            for i in range(70):
                tmp.write(json.dumps(f"scalar_flood_{i}") + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:02.000Z",
                "type": "event_msg",
                "payload": {"type": "future_unrecognized_event"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_cap = tmp.name

        try:
            obs_cap = parse_codex_rollout(tmp_cap, run_id="run-r17-cap")
            self.assertEqual(obs_cap["parser_status"]["status"], "partial")
            self.assertLessEqual(len(obs_cap["parser_status"]["reasons"]), 50)
            self.assertTrue(any("unrecognized" in r for r in obs_cap["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_cap):
                os.remove(tmp_cap)

    def test_r18_unrecognized_without_landmarks_emits_partial_and_preserves_reasons(self) -> None:
        """R18: Unrecognized events/subtypes without landmarks must emit partial (not unsupported) and preserve reasons."""
        # Probe 1: unrecognized event_msg subtype without session_meta or turn_context landmarks
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "event_msg",
                "payload": {"type": "future_unrecognized_probe_subtype", "data": "probe1"}
            }) + "\n")
            tmp_sub = tmp.name

        try:
            obs = parse_codex_rollout(tmp_sub, run_id="run-r18-sub-no-landmarks")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_msg_subtype:future_unrecognized_probe_subtype" in r for r in obs["parser_status"]["reasons"]))
            self.assertEqual(obs["completeness"]["status"], "not_observable")
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_sub):
                os.remove(tmp_sub)

        # Probe 2: unrecognized top-level event structure without landmarks
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "future_top_level_unrecognized_event",
                "payload": {"arbitrary": 999}
            }) + "\n")
            tmp_top = tmp.name

        try:
            obs_top = parse_codex_rollout(tmp_top, run_id="run-r18-top-no-landmarks")
            self.assertEqual(obs_top["parser_status"]["status"], "partial")
            self.assertTrue(any("unrecognized_event_structure:future_top_level_unrecognized_event" in r for r in obs_top["parser_status"]["reasons"]))
            self.assertEqual(obs_top["completeness"]["status"], "not_observable")
            valid, errs = validate_against_schema(obs_top, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_top):
                os.remove(tmp_top)

        # Probe 3: unrecognized subtype without landmarks but with terminal event
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "event_msg",
                "payload": {"type": "future_unrecognized_probe_subtype"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:05.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            tmp_term = tmp.name

        try:
            obs_term = parse_codex_rollout(tmp_term, run_id="run-r18-term-no-landmarks")
            self.assertEqual(obs_term["parser_status"]["status"], "partial")
            self.assertEqual(obs_term["completeness"]["status"], "complete")
            self.assertTrue(any("unrecognized_event_msg_subtype:future_unrecognized_probe_subtype" in r for r in obs_term["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs_term, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(tmp_term):
                os.remove(tmp_term)

        # Probe 4: Alien format without Codex envelope structure remains unsupported
        alien_path = self.fixtures_dir / "08_unsupported_alien_format.jsonl"
        obs_alien = parse_codex_rollout(str(alien_path), run_id="run-r18-alien")
        self.assertEqual(obs_alien["parser_status"]["status"], "unsupported")
        self.assertEqual(obs_alien["parser_status"]["reasons"], ["unrecognized_event_schema_for_codex"])
        valid, errs = validate_against_schema(obs_alien, str(self.schema_file))
        self.assertTrue(valid, f"Schema error: {errs}")

    def test_r19_collection_caps_exceeded_emits_partial_and_records_reasons(self) -> None:
        """R19: Clean probes for 51 contexts, 101 threads, and 51 rate limits verifying cap, reason, and partial status."""
        # 1. Clean probe for 51 distinct contexts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r19-ctx", "session_id": "sess-r19-ctx", "cli_version": "0.153.0"}
            }) + "\n")
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:{i % 60:02d}.000Z",
                    "type": "turn_context",
                    "payload": {"turn_id": f"turn-ctx-{i}", "model": f"model-r19-{i}", "effort": "high"}
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                        "last_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
                    }
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_ctx = tmp.name

        try:
            obs_ctx = parse_codex_rollout(p_ctx, run_id="run-r19-ctx-clean")
            self.assertEqual(len(obs_ctx["observed_contexts"]), 50)
            self.assertEqual(obs_ctx["parser_status"]["status"], "partial")
            self.assertTrue(any("observed_contexts_cap_exceeded:50" in r for r in obs_ctx["parser_status"]["reasons"]))
            self.assertEqual(obs_ctx["completeness"]["status"], "complete")
            valid, errs = validate_against_schema(obs_ctx, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_ctx):
                os.remove(p_ctx)

        # 2. Clean probe for 101 distinct threads
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-root-r19", "session_id": "sess-r19-th", "cli_version": "0.153.0"}
            }) + "\n")
            for i in range(101):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "session_meta",
                    "payload": {"id": f"th-child-{i}", "parent_thread_id": "th-root-r19"}
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:00.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-th-clean", "model": "gpt-5.6-terra", "effort": "high"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:01.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
                        "last_token_usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}
                    }
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_th = tmp.name

        try:
            obs_th = parse_codex_rollout(p_th, run_id="run-r19-th-clean")
            self.assertEqual(len(obs_th["thread_topology"]["threads"]), 100)
            self.assertEqual(obs_th["parser_status"]["status"], "partial")
            self.assertTrue(any("threads_topology_cap_exceeded:100" in r for r in obs_th["parser_status"]["reasons"]))
            self.assertEqual(obs_th["completeness"]["status"], "complete")
            valid, errs = validate_against_schema(obs_th, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_th):
                os.remove(p_th)

        # 3. Clean probe for 51 distinct rate limits
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-rl-r19", "session_id": "sess-r19-rl", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-rl-clean", "model": "gpt-5.6-terra", "effort": "high"}
            }) + "\n")
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 10 * (i + 1), "output_tokens": 5 * (i + 1), "total_tokens": 15 * (i + 1)},
                            "last_token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                        },
                        "rate_limits": {
                            "limit_id": f"quota-limit-{i}",
                            "primary": {"used_percent": float(i), "window_minutes": 60.0, "resets_at": 100.0}
                        }
                    }
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_rl = tmp.name

        try:
            obs_rl = parse_codex_rollout(p_rl, run_id="run-r19-rl-clean")
            self.assertEqual(len(obs_rl["rate_limits"]), 50)
            self.assertEqual(obs_rl["parser_status"]["status"], "partial")
            self.assertTrue(any("rate_limits_cap_exceeded:50" in r for r in obs_rl["parser_status"]["reasons"]))
            self.assertEqual(obs_rl["completeness"]["status"], "complete")
            valid, errs = validate_against_schema(obs_rl, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_rl):
                os.remove(p_rl)

    def test_r20_collection_caps_reasons_preserved_when_reasons_cap_saturated(self) -> None:
        """R20: Counterfactual probes saturating parser_reasons before exceeding each collection cap."""
        # 1. Saturated parser_reasons (60 flood lines) + 51 contexts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r20-ctx", "session_id": "sess-r20-ctx", "cli_version": "0.153.0"}
            }) + "\n")
            # Saturate parser_reasons with 60 non-dict JSON lines
            for i in range(60):
                tmp.write(json.dumps(f"scalar_flood_ctx_{i}") + "\n")
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:01:{i % 60:02d}.000Z",
                    "type": "turn_context",
                    "payload": {"turn_id": f"turn-ctx-r20-{i}", "model": f"model-r20-flood-{i}", "effort": "high"}
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                        "last_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
                    }
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_ctx = tmp.name

        try:
            obs_ctx = parse_codex_rollout(p_ctx, run_id="run-r20-ctx-saturated")
            self.assertEqual(len(obs_ctx["observed_contexts"]), 50)
            self.assertEqual(obs_ctx["parser_status"]["status"], "partial")
            self.assertLessEqual(len(obs_ctx["parser_status"]["reasons"]), 50)
            self.assertTrue(any("observed_contexts_cap_exceeded:50" in r for r in obs_ctx["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs_ctx, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_ctx):
                os.remove(p_ctx)

        # 2. Saturated parser_reasons (60 flood lines) + 101 threads
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-root-r20", "session_id": "sess-r20-th", "cli_version": "0.153.0"}
            }) + "\n")
            for i in range(60):
                tmp.write(json.dumps(f"scalar_flood_th_{i}") + "\n")
            for i in range(101):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:01:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "session_meta",
                    "payload": {"id": f"th-child-r20-{i}", "parent_thread_id": "th-root-r20"}
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:00.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-th-r20", "model": "gpt-5.6-terra", "effort": "high"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:02:01.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
                        "last_token_usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}
                    }
                }
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_th = tmp.name

        try:
            obs_th = parse_codex_rollout(p_th, run_id="run-r20-th-saturated")
            self.assertEqual(len(obs_th["thread_topology"]["threads"]), 100)
            self.assertEqual(obs_th["parser_status"]["status"], "partial")
            self.assertLessEqual(len(obs_th["parser_status"]["reasons"]), 50)
            self.assertTrue(any("threads_topology_cap_exceeded:100" in r for r in obs_th["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs_th, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_th):
                os.remove(p_th)

        # 3. Saturated parser_reasons (60 flood lines) + 51 rate limits
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-rl-r20", "session_id": "sess-r20-rl", "cli_version": "0.153.0"}
            }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:01.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-rl-r20", "model": "gpt-5.6-terra", "effort": "high"}
            }) + "\n")
            for i in range(60):
                tmp.write(json.dumps(f"scalar_flood_rl_{i}") + "\n")
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:01:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 10 * (i + 1), "output_tokens": 5 * (i + 1), "total_tokens": 15 * (i + 1)},
                            "last_token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                        },
                        "rate_limits": {
                            "limit_id": f"quota-limit-r20-{i}",
                            "primary": {"used_percent": float(i), "window_minutes": 60.0, "resets_at": 100.0}
                        }
                    }
                }) + "\n")
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_rl = tmp.name

        try:
            obs_rl = parse_codex_rollout(p_rl, run_id="run-r20-rl-saturated")
            self.assertEqual(len(obs_rl["rate_limits"]), 50)
            self.assertEqual(obs_rl["parser_status"]["status"], "partial")
            self.assertLessEqual(len(obs_rl["parser_status"]["reasons"]), 50)
            self.assertTrue(any("rate_limits_cap_exceeded:50" in r for r in obs_rl["parser_status"]["reasons"]))
            valid, errs = validate_against_schema(obs_rl, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_rl):
                os.remove(p_rl)

    def test_r21_multiple_caps_exceeded_with_unrecognized_flood(self) -> None:
        """R21: Counterfactual probe saturating parser_reasons with unrecognized event subtypes
        and simultaneously exceeding contexts, threads, and rate limits caps."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            # 1. Structural session_meta
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r21-root", "session_id": "sess-r21-flood", "cli_version": "0.153.0"}
            }) + "\n")
            # 2. Flood with 60 unrecognized event_msg subtypes (saturates MAX_REASONS_CAP = 50)
            for i in range(60):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:00:{i % 60:02d}.000Z",
                    "type": "event_msg",
                    "payload": {"type": f"unrecognized_sub_r21_{i}", "extra": "data"}
                }) + "\n")
            # 3. 51 contexts (exceeds MAX_CONTEXTS_CAP = 50)
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:01:{i % 60:02d}.000Z",
                    "type": "turn_context",
                    "payload": {"turn_id": f"turn-r21-{i}", "model": f"model-r21-{i}", "effort": "high"}
                }) + "\n")
            # 4. 102 threads (exceeds MAX_THREADS_CAP = 100)
            for i in range(102):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:02:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "turn_context",
                    "payload": {"thread_id": f"th-r21-branch-{i}", "model": "gpt-5.6-terra"}
                }) + "\n")
            # 5. 51 rate limits (exceeds MAX_RATE_LIMITS_CAP = 50) and valid usage counters
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:03:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 10 * (i + 1), "output_tokens": 5 * (i + 1), "total_tokens": 15 * (i + 1)},
                            "last_token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                        },
                        "rate_limits": {
                            "limit_id": f"quota-r21-{i}",
                            "primary": {"used_percent": float(i), "window_minutes": 60.0, "resets_at": 100.0}
                        }
                    }
                }) + "\n")
            # 6. Clean terminal marker
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_r21 = tmp.name

        try:
            obs = parse_codex_rollout(p_r21, run_id="run-r21-probe")
            # Must be partial due to caps and unrecognized events
            self.assertEqual(obs["parser_status"]["status"], "partial")
            # Must enforce max reasons cap
            reasons = obs["parser_status"]["reasons"]
            self.assertLessEqual(len(reasons), 50)
            # All three collection caps reasons MUST be present simultaneously
            self.assertTrue(any("observed_contexts_cap_exceeded:50" in r for r in reasons), f"Missing contexts cap in {reasons}")
            self.assertTrue(any("threads_topology_cap_exceeded:100" in r for r in reasons), f"Missing threads cap in {reasons}")
            self.assertTrue(any("rate_limits_cap_exceeded:50" in r for r in reasons), f"Missing rate limits cap in {reasons}")
            # Unrecognized reason and truncation marker must also be preserved
            self.assertTrue(any("unrecognized" in r for r in reasons), f"Missing unrecognized reason in {reasons}")
            self.assertIn("additional_reasons_truncated", reasons)
            # Collections capped correctly
            self.assertEqual(len(obs["observed_contexts"]), 50)
            self.assertEqual(len(obs["thread_topology"]["threads"]), 100)
            self.assertEqual(len(obs["rate_limits"]), 50)
            # Must satisfy JSON Schema
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_r21):
                os.remove(p_r21)

    def test_r22_non_unrecognized_flood_then_unrecognized_and_all_caps(self) -> None:
        """R22: Counterfactual probe saturating parser_reasons with non-unrecognized reasons,
        then introducing an unrecognized event subtype and simultaneously exceeding all 3 collection caps."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            # 1. Structural session_meta
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "th-r22-root", "session_id": "sess-r22-flood", "cli_version": "0.153.0"}
            }) + "\n")
            # 2. Flood with 60 non-dict scalar JSON lines (saturates MAX_REASONS_CAP = 50 with line_X_not_a_json_object, completely non-unrecognized)
            for i in range(60):
                tmp.write(json.dumps(f"scalar_flood_r22_{i}") + "\n")
            # 3. Introduce an unrecognized event subtype
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:00:30.000Z",
                "type": "event_msg",
                "payload": {"type": "unrecognized_sub_r22_counterfactual", "details": "unexpected"}
            }) + "\n")
            # 4. 51 contexts (exceeds MAX_CONTEXTS_CAP = 50)
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:01:{i % 60:02d}.000Z",
                    "type": "turn_context",
                    "payload": {"turn_id": f"turn-r22-{i}", "model": f"model-r22-{i}", "effort": "high"}
                }) + "\n")
            # 5. 102 threads (exceeds MAX_THREADS_CAP = 100)
            for i in range(102):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:02:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "turn_context",
                    "payload": {"thread_id": f"th-r22-branch-{i}", "model": "gpt-5.6-terra"}
                }) + "\n")
            # 6. 51 rate limits (exceeds MAX_RATE_LIMITS_CAP = 50) and valid token counts
            for i in range(51):
                tmp.write(json.dumps({
                    "timestamp": f"2026-06-25T14:03:{i % 60:02d}.{i % 1000:03d}Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 10 * (i + 1), "output_tokens": 5 * (i + 1), "total_tokens": 15 * (i + 1)},
                            "last_token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                        },
                        "rate_limits": {
                            "limit_id": f"quota-r22-{i}",
                            "primary": {"used_percent": float(i), "window_minutes": 60.0, "resets_at": 100.0}
                        }
                    }
                }) + "\n")
            # 7. Clean terminal marker
            tmp.write(json.dumps({
                "timestamp": "2026-06-25T14:05:00.000Z",
                "type": "event_msg",
                "payload": {"type": "session_complete"}
            }) + "\n")
            p_r22 = tmp.name

        try:
            obs = parse_codex_rollout(p_r22, run_id="run-r22-probe")
            # Must be partial
            self.assertEqual(obs["parser_status"]["status"], "partial")
            reasons = obs["parser_status"]["reasons"]
            # Must enforce reasons cap <= 50
            self.assertLessEqual(len(reasons), 50)
            # The specific unrecognized reason MUST be present
            self.assertIn("unrecognized_event_msg_subtype:unrecognized_sub_r22_counterfactual", reasons)
            # All three collection caps reasons MUST be present simultaneously
            self.assertIn("observed_contexts_cap_exceeded:50", reasons)
            self.assertIn("threads_topology_cap_exceeded:100", reasons)
            self.assertIn("rate_limits_cap_exceeded:50", reasons)
            # Truncation marker MUST be present
            self.assertIn("additional_reasons_truncated", reasons)
            # Non-unrecognized scalar flood reasons must also occupy the remaining slots
            self.assertTrue(any(r.startswith("line_") and r.endswith("_not_a_json_object") for r in reasons))
            # Collections capped correctly
            self.assertEqual(len(obs["observed_contexts"]), 50)
            self.assertEqual(len(obs["thread_topology"]["threads"]), 100)
            self.assertEqual(len(obs["rate_limits"]), 50)
            # Must satisfy JSON Schema
            valid, errs = validate_against_schema(obs, str(self.schema_file))
            self.assertTrue(valid, f"Schema error: {errs}")
        finally:
            if os.path.exists(p_r22):
                os.remove(p_r22)


class TestSmokeLocalRealRollout(unittest.TestCase):
    """Smoke test against a local real Codex session rollout (if present)."""

    def test_smoke_real_rollout_if_available(self) -> None:
        import glob
        pattern = os.path.expanduser("~/.codex/sessions/*/*/*/*.jsonl")
        files = sorted(glob.glob(pattern), reverse=True)
        if not files:
            self.skipTest("No local ~/.codex session files available for smoke test.")

        real_session_file = files[0]
        obs = parse_codex_rollout(real_session_file, run_id="smoke-local-codex")

        self.assertEqual(obs["run_id"], "smoke-local-codex")
        self.assertEqual(obs["harness"], "codex")
        self.assertIn(obs["completeness"]["status"], ["complete", "incomplete", "not_observable"])
        self.assertIn(obs["parser_status"]["status"], ["supported", "partial"])

        # Check digest is valid SHA-256
        self.assertEqual(len(obs["session_ref_digest"]), 64)

        # Check derived usage is strictly not_observable
        self.assertEqual(obs["derived_usage"]["uncached_input_tokens"], "not_observable")

        # Check schema validity using pure stdlib
        schema_file = REPO_ROOT / "schemas" / "usage-observation.schema.json"
        valid, errs = validate_against_schema(obs, str(schema_file))
        self.assertTrue(valid, f"Real rollout schema validation failed: {errs}")


if __name__ == "__main__":
    unittest.main()
