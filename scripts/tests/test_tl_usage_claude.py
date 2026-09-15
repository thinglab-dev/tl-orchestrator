#!/usr/bin/env python3
"""
test_tl_usage_claude.py - Deterministic test suite for Claude Harness Usage Observation (Task T029).
Covers CLI parsing, Classes A through J, Golden 2.1.257, Invariants I1 to I14,
Draft 2020-12 schema validation, privacy, bounded memory, and fail-closed policies.
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tl_usage import (
    CLAUDE_CANONICAL_FINGERPRINT,
    CLAUDE_COUNTER_FIELDS,
    CLAUDE_SOURCE_FORMAT,
    RULE_ID_CLAUDE_CODE_V1,
    SCHEMA_VERSION,
    enforce_schema_validation,
    format_counter,
    has_nested_path,
    parse_claude_session,
    validate_against_schema,
)


class TestTLUsageClaudeCLI(unittest.TestCase):
    """Test CLI argument parsing and error handling for Claude harness."""

    def setUp(self) -> None:
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "claude"
        self.schema_path = REPO_ROOT / "schemas" / "usage-observation.schema.json"

    def test_cli_default_harness_is_codex(self) -> None:
        fixture_path = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "codex" / "01_single_turn_complete.jsonl"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--run-id", "test-default-cli",
            "--session-ref", str(fixture_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["harness"], "codex")

    def test_cli_explicit_harness_claude(self) -> None:
        fixture_path = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--harness", "claude",
            "--run-id", "test-claude-cli",
            "--session-ref", str(fixture_path),
            "--verify-schema",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["harness"], "claude")
        self.assertEqual(data["source_format"], CLAUDE_SOURCE_FORMAT)
        self.assertEqual(data["source_format_fingerprint"], CLAUDE_CANONICAL_FINGERPRINT)

    def test_cli_claude_output_file(self) -> None:
        fixture_path = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tl_usage.py"),
                "--harness", "claude",
                "--run-id", "test-claude-out",
                "--session-ref", str(fixture_path),
                "--output", tmp_path,
                "--verify-schema",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)

            with open(tmp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["run_id"], "test-claude-out")
            self.assertEqual(data["harness"], "claude")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_cli_claude_text_format(self) -> None:
        fixture_path = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--harness", "claude",
            "--run-id", "test-claude-text",
            "--session-ref", str(fixture_path),
            "--format", "text",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Harness: claude", res.stdout)
        self.assertIn("Normalized Status: normalized", res.stdout)


class TestTLUsageClaudeClasses(unittest.TestCase):
    """Test parsing across mandatory test classes A through J and Golden 2.1.257."""

    def setUp(self) -> None:
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "claude"
        self.schema_path = REPO_ROOT / "schemas" / "usage-observation.schema.json"

    def test_classe_a_mono_block_standard(self) -> None:
        """Classe A: Single assistant block per response; 1:1 physical to unique preservation."""
        f = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-a")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        self.assertEqual(obs["parser_status"]["status"], "supported")
        self.assertEqual(obs["completeness"]["status"], "not_observable")  # Invariant I8
        self.assertEqual(obs["raw_usage"]["reconciliation"]["status"], "not_observable")  # Invariant I7

        raw_ch = obs["raw_usage_channels"]
        self.assertEqual(raw_ch["claude_assistant_messages"]["event_count"], 1)
        self.assertEqual(raw_ch["claude_assistant_messages"]["native_counters_sum"]["input_tokens"], 100)
        self.assertEqual(raw_ch["claude_assistant_messages"]["native_counters_sum"]["output_tokens"], 20)

        self.assertEqual(raw_ch["claude_unique_responses"]["event_count"], 1)
        self.assertEqual(raw_ch["claude_unique_responses"]["native_counters_sum"]["input_tokens"], 100)

        nu = obs["normalized_usage"]
        self.assertEqual(nu["status"], "normalized")
        self.assertEqual(nu["rule_id"], RULE_ID_CLAUDE_CODE_V1)
        self.assertEqual(nu["semantic_response_count"], 1)
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 100)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 20)
        self.assertEqual(nu["semantic_request_sum"]["cache_creation_input_tokens"], 50)
        self.assertEqual(nu["semantic_request_sum"]["cache_read_input_tokens"], 30)

    def test_classe_b_multi_block_deduplication(self) -> None:
        """Classe B: Multiple consecutive assistant lines sharing message.id and requestId deduplicate to 1."""
        f = self.fixtures_dir / "02_classe_b_multi_block_dedup.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-b")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        raw_ch = obs["raw_usage_channels"]
        # 3 physical lines observed
        self.assertEqual(raw_ch["claude_assistant_messages"]["event_count"], 3)
        self.assertEqual(raw_ch["claude_assistant_messages"]["native_counters_sum"]["input_tokens"], 600)
        self.assertEqual(raw_ch["claude_assistant_messages"]["native_counters_sum"]["output_tokens"], 240)

        # Deduplicated to 1 unique response
        self.assertEqual(raw_ch["claude_unique_responses"]["event_count"], 1)
        self.assertEqual(raw_ch["claude_unique_responses"]["native_counters_sum"]["input_tokens"], 200)
        self.assertEqual(raw_ch["claude_unique_responses"]["native_counters_sum"]["output_tokens"], 80)

        nu = obs["normalized_usage"]
        self.assertEqual(nu["status"], "normalized")
        self.assertEqual(nu["semantic_response_count"], 1)
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 200)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 80)

    def test_classe_c_extended_thinking(self) -> None:
        """Classe C: Extended thinking extracted literally without assuming equality to reasoning_output_tokens."""
        f = self.fixtures_dir / "03_classe_c_thinking.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-c")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        nu = obs["normalized_usage"]
        self.assertEqual(nu["semantic_request_sum"]["thinking_tokens"], 120)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 300)

        # Invariant I6: canonical block must not map thinking_tokens -> reasoning_output_tokens
        self.assertEqual(nu["semantic_per_response_sum"]["reasoning_output_tokens"], "not_observable")
        self.assertEqual(obs["raw_usage"]["per_response_sum"]["reasoning_output_tokens"], "not_observable")

    def test_classe_d_context_compaction_isolation(self) -> None:
        """Classe D: Compaction metrics recorded in context_compaction_observations; zero usage contamination."""
        f = self.fixtures_dir / "04_classe_d_compaction.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-d")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        comp = obs.get("context_compaction_observations", [])
        self.assertEqual(len(comp), 1)
        c0 = comp[0]
        self.assertEqual(c0["trigger"], "auto")
        self.assertEqual(c0["pre_tokens"], 50000)
        self.assertEqual(c0["post_tokens"], 5000)
        self.assertEqual(c0["cumulative_dropped_tokens"], 45000)
        self.assertEqual(c0["duration_ms"], 1200)
        self.assertEqual(c0["preserved_messages_count"], 2)

        # Invariant I9: usage numbers must ONLY be actual response usage (100 + 50 = 150)
        nu = obs["normalized_usage"]
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 150)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 35)

    def test_classe_e_multi_model_session(self) -> None:
        """Classe E: Multi-model session with distinct models preserved under observed_contexts."""
        f = self.fixtures_dir / "05_classe_e_multi_model.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-e")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        contexts = obs["observed_contexts"]
        self.assertEqual(len(contexts), 2)
        models = {c["model"] for c in contexts}
        self.assertIn("claude-3-7-sonnet-20250219", models)
        self.assertIn("claude-3-5-haiku-20241022", models)

        nu = obs["normalized_usage"]
        self.assertEqual(nu["semantic_response_count"], 2)
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 150)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 35)

    def test_classe_f_subagents_explicit_linking_and_strict_boundary(self) -> None:
        """Classe F: Subagent linked via toolUseId -> tool_use.id; tokens NOT added to parent session."""
        f = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        sub_meta = self.fixtures_dir / "06_subagent.meta.json"
        obs = parse_claude_session(str(f), run_id="run-claude-f", subagent_paths=[str(sub_meta)])
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        # Subagent is linked in thread_topology
        threads = obs["thread_topology"]["threads"]
        self.assertEqual(len(threads), 2)
        child = [t for t in threads if t["role"] == "child"][0]
        self.assertEqual(child["tool_use_id"], "toolu_sub_classe_f_01")
        self.assertEqual(child["parent_thread_id"], obs["thread_topology"]["root_thread_id"])

        # Invariant I10: Child tokens (500, 100) are NOT summed into parent!
        nu = obs["normalized_usage"]
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 100)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 20)

    def test_classe_g_interrupted_negative_marker(self) -> None:
        """Classe G: Session with isAbortedMidStream classified fail-closed as incomplete and partial."""
        f = self.fixtures_dir / "07_classe_g_interrupted.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-g")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        self.assertEqual(obs["completeness"]["status"], "incomplete")
        self.assertTrue(any("isAbortedMidStream" in r for r in obs["completeness"]["reasons"]))
        self.assertEqual(obs["parser_status"]["status"], "partial")

    def test_classe_h_conflicting_identity_degrades_strictly(self) -> None:
        """Classe H: Reused message.id with conflicting requestId or usage degrades to ambiguous and not_observable."""
        f = self.fixtures_dir / "08_classe_h_conflicting_identity.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-h")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        self.assertEqual(obs["parser_status"]["status"], "partial")
        nu = obs["normalized_usage"]
        self.assertEqual(nu["status"], "not_observable")
        self.assertFalse(nu["eligible_for_normalization"])
        self.assertTrue(any("conflicting_structural_identity" in r for r in nu["ineligibility_reasons"]))

    def test_classe_i_ledger_overflow_bounded_memory(self) -> None:
        """Classe I: Over 100 unique responses triggers bounded memory cap degradation without crash."""
        f = self.fixtures_dir / "09_classe_i_ledger_overflow.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-i")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        self.assertEqual(obs["parser_status"]["status"], "partial")
        nu = obs["normalized_usage"]
        self.assertEqual(nu["status"], "not_observable")
        self.assertTrue(any("identity_ledger_cap_exceeded:100" in r for r in nu["ineligibility_reasons"]))

        # Action Item R2 / Invariant I12: Under overflow, unique responses channel must be unambiguously truncated/not_observable
        uniq_ch = obs["raw_usage_channels"]["claude_unique_responses"]
        self.assertEqual(uniq_ch["status"], "truncated")
        self.assertEqual(uniq_ch["event_count"], "not_observable")
        self.assertNotEqual(uniq_ch["event_count"], 100)
        for cf in CLAUDE_COUNTER_FIELDS:
            self.assertEqual(uniq_ch["native_counters_sum"][cf], "not_observable")

        # Action Item R1 (r07) / Invariant I12: Under overflow, observed_contexts must NOT publish partial subtotals
        self.assertEqual(len(obs["observed_contexts"]), 1)
        ctx = obs["observed_contexts"][0]
        self.assertEqual(ctx["turn_count"], "not_observable")
        self.assertNotEqual(ctx["turn_count"], 100)
        for cf in CLAUDE_COUNTER_FIELDS:
            self.assertEqual(ctx["raw_usage"][cf], "not_observable")
            self.assertNotEqual(ctx["raw_usage"][cf], 1000)

        # Action Item R1 (r08) / Invariant I12: Under overflow, thread_topology root turn_count must be not_observable
        self.assertGreater(len(obs["thread_topology"]["threads"]), 0)
        root_th = obs["thread_topology"]["threads"][0]
        self.assertEqual(root_th["role"], "root")
        self.assertEqual(root_th["turn_count"], "not_observable")
        self.assertNotEqual(root_th["turn_count"], 100)

    def test_r1_counterfactual_ledger_overflow_observed_contexts_probe(self) -> None:
        """Action Item R1 (r07): Counterfactual probe verifying that ledger overflow degrades observed_contexts fail-closed instead of publishing partial subtotals."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            for i in range(105):
                tmp.write(json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_overflow_probe",
                    "uuid": f"uuid_{i}",
                    "version": "2.1.257",
                    "requestId": f"req_{i}",
                    "message": {
                        "id": f"msg_{i}",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-cf-overflow")
            self.assertEqual(obs["parser_status"]["status"], "partial")

            # Must fail if observed_contexts emits partial numeric turn_count or sums
            self.assertGreater(len(obs["observed_contexts"]), 0)
            for ctx in obs["observed_contexts"]:
                self.assertEqual(ctx["turn_count"], "not_observable")
                self.assertNotEqual(ctx["turn_count"], 100)
                self.assertNotEqual(ctx["turn_count"], 105)
                for cf in CLAUDE_COUNTER_FIELDS:
                    self.assertEqual(ctx["raw_usage"][cf], "not_observable")
                    self.assertNotEqual(ctx["raw_usage"][cf], 1000)
                    self.assertNotEqual(ctx["raw_usage"][cf], 500)

            # Action Item R1 (r08): Under overflow, thread_topology root turn_count must be not_observable
            root_th = obs["thread_topology"]["threads"][0]
            self.assertEqual(root_th["turn_count"], "not_observable")
            self.assertNotEqual(root_th["turn_count"], 100)
            self.assertNotEqual(root_th["turn_count"], 105)

            valid, errs = validate_against_schema(obs, str(self.schema_path))
            self.assertTrue(valid, errs)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r1_counterfactual_ledger_overflow_thread_topology_probe(self) -> None:
        """Action Item R1 (r08): Counterfactual probe verifying that ledger overflow degrades root thread turn_count to not_observable and fails if 100 or partial subtotal is emitted."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            for i in range(106):
                tmp.write(json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_th_overflow_probe",
                    "uuid": f"uuid_th_{i}",
                    "version": "2.1.257",
                    "requestId": f"req_th_{i}",
                    "message": {
                        "id": f"msg_th_{i}",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-th-cf-overflow")
            self.assertEqual(obs["parser_status"]["status"], "partial")

            # Must fail if root thread emits partial numeric turn_count
            threads = obs["thread_topology"]["threads"]
            self.assertGreater(len(threads), 0)
            root_th = threads[0]
            self.assertEqual(root_th["role"], "root")
            self.assertEqual(root_th["turn_count"], "not_observable")
            self.assertNotEqual(root_th["turn_count"], 100)
            self.assertNotEqual(root_th["turn_count"], 106)

            valid, errs = validate_against_schema(obs, str(self.schema_path))
            self.assertTrue(valid, errs)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_classe_j_synthetic_model_excluded_from_semantic_sum(self) -> None:
        """Classe J: Records with message.model: '<synthetic>' are in raw channels but excluded from semantic_request_sum."""
        f = self.fixtures_dir / "10_classe_j_synthetic.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-j")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        raw_ch = obs["raw_usage_channels"]
        self.assertEqual(raw_ch["claude_assistant_messages"]["event_count"], 2)
        self.assertEqual(raw_ch["claude_unique_responses"]["event_count"], 2)

        nu = obs["normalized_usage"]
        self.assertEqual(nu["status"], "normalized")
        self.assertEqual(nu["semantic_response_count"], 1)  # only real model response
        self.assertEqual(nu["semantic_request_sum"]["input_tokens"], 100)
        self.assertEqual(nu["semantic_request_sum"]["output_tokens"], 20)

    def test_golden_2_1_257_supported(self) -> None:
        """Golden session: Supported version 2.1.257 with canonical profile b3140fe31bd7968a."""
        f = self.fixtures_dir / "11_golden_2_1_257_supported.jsonl"
        obs = parse_claude_session(str(f), run_id="run-claude-golden")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

        self.assertEqual(obs["harness_version"], "2.1.257")
        self.assertEqual(obs["source_format_fingerprint"], CLAUDE_CANONICAL_FINGERPRINT)
        self.assertEqual(obs["parser_status"]["status"], "supported")
        self.assertEqual(obs["completeness"]["status"], "not_observable")
        self.assertEqual(obs["normalized_usage"]["status"], "normalized")
        self.assertEqual(obs["normalized_usage"]["semantic_response_count"], 2)
        self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["input_tokens"], 550)
        self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["output_tokens"], 105)


class TestTLUsageClaudeInvariants(unittest.TestCase):
    """Rigorous verification of Invariants I1 to I14 for Claude usage observation."""

    def setUp(self) -> None:
        self.fixtures_dir = REPO_ROOT / "scripts" / "fixtures" / "tl_usage" / "claude"
        self.schema_path = REPO_ROOT / "schemas" / "usage-observation.schema.json"

    def test_i7_and_i8_cumulative_and_completeness_never_fabricated(self) -> None:
        """Invariant I7 & I8: reconciliation.status and cumulative are not_observable; completeness never complete."""
        f = self.fixtures_dir / "11_golden_2_1_257_supported.jsonl"
        obs = parse_claude_session(str(f), run_id="run-inv-i7-i8")

        self.assertEqual(obs["raw_usage"]["reconciliation"]["status"], "not_observable")
        for k, v in obs["raw_usage"]["cumulative"].items():
            self.assertEqual(v, "not_observable", f"Cumulative field {k} must be not_observable")

        self.assertEqual(obs["normalized_usage"]["reconciliation"]["status"], "not_observable")
        for k, v in obs["normalized_usage"]["cumulative"].items():
            self.assertEqual(v, "not_observable", f"Normalized cumulative field {k} must be not_observable")

        self.assertNotEqual(obs["completeness"]["status"], "complete", "Claude v1 must NEVER emit complete")

    def test_i6_unproven_fields_not_observable(self) -> None:
        """Invariant I6: Fields without proven equivalence (total_tokens, uncached_input_tokens) must be not_observable."""
        f = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        obs = parse_claude_session(str(f), run_id="run-inv-i6")

        self.assertEqual(obs["raw_usage"]["per_response_sum"]["total_tokens"], "not_observable")
        self.assertEqual(obs["raw_usage"]["per_response_sum"]["cached_input_tokens"], "not_observable")
        self.assertEqual(obs["raw_usage"]["per_response_sum"]["reasoning_output_tokens"], "not_observable")
        self.assertEqual(obs["derived_usage"]["uncached_input_tokens"], "not_observable")

    def test_i13_privacy_compliance(self) -> None:
        """Invariant I13: No text from content blocks or file paths persisted or emitted."""
        f = self.fixtures_dir / "04_classe_d_compaction.jsonl"
        obs = parse_claude_session(str(f), run_id="run-inv-i13")
        obs_json_str = json.dumps(obs)

        self.assertNotIn("Summary content that should be discarded", obs_json_str)
        self.assertNotIn(str(f), obs_json_str)
        self.assertRegex(obs["session_ref_digest"], r"^[a-f0-9]{64}$")

    def test_unsupported_version_degrades_gracefully(self) -> None:
        """Sessão com versão diferente de 2.1.257 deve degradar para parser_status: partial e normalized: not_observable."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_alien",
                "uuid": "a1",
                "version": "1.9.999",  # alien version
                "requestId": "req_alien",
                "message": {
                    "id": "msg_alien",
                    "role": "assistant",
                    "model": "claude-3-5-haiku-20241022",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-alien-ver")
            valid, errs = validate_against_schema(obs, str(self.schema_path))
            self.assertTrue(valid, errs)

            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertTrue(any("unsupported_claude_version:1.9.999" in r for r in obs["parser_status"]["reasons"]))
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r1_source_kind_presence(self) -> None:
        """Action Item R1: Claude observation must emit source_kind: harness_native_log."""
        f = self.fixtures_dir / "01_classe_a_mono_block.jsonl"
        obs = parse_claude_session(str(f), run_id="run-r1-source-kind")
        self.assertIn("source_kind", obs)
        self.assertEqual(obs["source_kind"], "harness_native_log")
        valid, errs = validate_against_schema(obs, str(self.schema_path))
        self.assertTrue(valid, errs)

    def test_r2_invalid_counter_type_degrades_fail_closed(self) -> None:
        """Action Item R2 (r06) / I13: Invalid counter types must degrade fail-closed without raw value leakage and must not publish 0 as fact."""
        sentinel_secret = "SENTINEL_LEAK_SECRET_TOKEN_XYZ123"
        bad_values = [sentinel_secret, -5, True]
        for bad_val in bad_values:
            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_bad_counter",
                    "uuid": "a1",
                    "version": "2.1.257",
                    "requestId": "req_bad_counter",
                    "message": {
                        "id": "msg_bad_counter",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "usage": {"input_tokens": bad_val, "output_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }) + "\n")
                tmp_path = tmp.name

            try:
                obs = parse_claude_session(tmp_path, run_id="run-bad-counter")
                self.assertEqual(obs["parser_status"]["status"], "partial")
                self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
                if isinstance(bad_val, int) and bad_val < 0:
                    self.assertTrue(any("negative_counter_value_input_tokens" in r for r in obs["parser_status"]["reasons"]))
                else:
                    self.assertTrue(any("invalid_counter_type_input_tokens" in r for r in obs["parser_status"]["reasons"]))

                # Action Item R1 (r04) / Invariant I13: Sentinel textual secret must NEVER appear anywhere in serialized JSON
                raw_json = json.dumps(obs)
                self.assertNotIn(sentinel_secret, raw_json)

                # Action Item R1 (r06): Propagate per-field invalidity to raw/unique/contextual aggregates; never publish 0 as fact
                asst_ch = obs["raw_usage_channels"]["claude_assistant_messages"]
                self.assertEqual(asst_ch["status"], "not_observable")
                self.assertNotEqual(asst_ch["status"], "exact")
                self.assertEqual(asst_ch["native_counters_sum"]["input_tokens"], "not_observable")
                self.assertNotEqual(asst_ch["native_counters_sum"]["input_tokens"], 0)
                self.assertEqual(asst_ch["native_counters_sum"]["output_tokens"], 10)

                uniq_ch = obs["raw_usage_channels"]["claude_unique_responses"]
                self.assertEqual(uniq_ch["status"], "not_observable")
                self.assertNotEqual(uniq_ch["status"], "exact")
                self.assertEqual(uniq_ch["native_counters_sum"]["input_tokens"], "not_observable")
                self.assertNotEqual(uniq_ch["native_counters_sum"]["input_tokens"], 0)
                self.assertEqual(uniq_ch["native_counters_sum"]["output_tokens"], 10)

                self.assertEqual(obs["raw_usage"]["per_response_sum"]["input_tokens"], "not_observable")
                self.assertNotEqual(obs["raw_usage"]["per_response_sum"]["input_tokens"], 0)
                self.assertEqual(obs["raw_usage"]["per_response_sum"]["output_tokens"], 10)

                self.assertEqual(obs["observed_contexts"][0]["raw_usage"]["input_tokens"], "not_observable")
                self.assertNotEqual(obs["observed_contexts"][0]["raw_usage"]["input_tokens"], 0)
                self.assertEqual(obs["observed_contexts"][0]["raw_usage"]["output_tokens"], 10)

                valid, errs = validate_against_schema(obs, str(self.schema_path))
                self.assertTrue(valid, errs)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def test_r1_invalid_thinking_tokens_sentinel_no_leak(self) -> None:
        """Action Item R1 (r04/r06) / Invariant I13: Thinking tokens invalid type degrades fail-closed without raw value leakage or 0 substitution."""
        sentinel_secret = "SENTINEL_THINKING_TOKEN_SECRET_999"
        for bad_val in [sentinel_secret, True, -10]:
            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_bad_thinking",
                    "uuid": "a1",
                    "version": "2.1.257",
                    "requestId": "req_bad_thinking",
                    "message": {
                        "id": "msg_bad_thinking",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 10,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens_details": {"thinking_tokens": bad_val}
                        }
                    }
                }) + "\n")
                tmp_path = tmp.name

            try:
                obs = parse_claude_session(tmp_path, run_id="run-bad-thinking")
                self.assertEqual(obs["parser_status"]["status"], "partial")
                self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
                if isinstance(bad_val, int) and bad_val < 0:
                    self.assertTrue(any("negative_thinking_tokens_value" in r for r in obs["parser_status"]["reasons"]))
                else:
                    self.assertTrue(any("invalid_thinking_tokens_type" in r for r in obs["parser_status"]["reasons"]))
                raw_json = json.dumps(obs)
                self.assertNotIn(sentinel_secret, raw_json)

                # Action Item R1 (r06): Propagate thinking_tokens invalidity per field
                self.assertEqual(obs["raw_usage_channels"]["claude_assistant_messages"]["status"], "not_observable")
                self.assertEqual(obs["raw_usage_channels"]["claude_assistant_messages"]["native_counters_sum"]["thinking_tokens"], "not_observable")
                self.assertNotEqual(obs["raw_usage_channels"]["claude_assistant_messages"]["native_counters_sum"]["thinking_tokens"], 0)
                self.assertEqual(obs["raw_usage_channels"]["claude_unique_responses"]["status"], "not_observable")
                self.assertEqual(obs["raw_usage_channels"]["claude_unique_responses"]["native_counters_sum"]["thinking_tokens"], "not_observable")
                self.assertNotEqual(obs["raw_usage_channels"]["claude_unique_responses"]["native_counters_sum"]["thinking_tokens"], 0)
                self.assertEqual(obs["observed_contexts"][0]["raw_usage"]["thinking_tokens"], "not_observable")
                self.assertNotEqual(obs["observed_contexts"][0]["raw_usage"]["thinking_tokens"], 0)

                valid, errs = validate_against_schema(obs, str(self.schema_path))
                self.assertTrue(valid, errs)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def test_r1_counterfactual_invalid_counters_probe(self) -> None:
        """Action Item R1 (r06): Counterfactual probe verifying that textual, boolean, and negative values never publish 0 as fact across all aggregates."""
        counter_fields = ["input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]
        bad_values = ["corrupted_string", True, False, -1, -999]

        for target_field in counter_fields:
            for bad_val in bad_values:
                standard_usage = {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 5,
                }
                standard_usage[target_field] = bad_val

                with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
                    tmp.write(json.dumps({
                        "type": "assistant",
                        "sessionId": "sess_cf_probe",
                        "uuid": "u_cf_1",
                        "version": "2.1.257",
                        "requestId": "req_cf_1",
                        "message": {
                            "id": "msg_cf_1",
                            "role": "assistant",
                            "model": "claude-3-7-sonnet-20250219",
                            "usage": standard_usage,
                        }
                    }) + "\n")
                    tmp_path = tmp.name

                try:
                    obs = parse_claude_session(tmp_path, run_id=f"run-cf-{target_field}")
                    self.assertEqual(obs["parser_status"]["status"], "partial")

                    # Channel status must degrade to not_observable, not exact
                    asst_ch = obs["raw_usage_channels"]["claude_assistant_messages"]
                    self.assertEqual(asst_ch["status"], "not_observable")
                    self.assertNotEqual(asst_ch["status"], "exact")

                    # The invalid field must be not_observable and NEVER fabricated as 0
                    self.assertEqual(asst_ch["native_counters_sum"][target_field], "not_observable")
                    self.assertNotEqual(asst_ch["native_counters_sum"][target_field], 0)

                    # Other valid fields must be preserved factually
                    for other_field in counter_fields:
                        if other_field != target_field:
                            self.assertEqual(asst_ch["native_counters_sum"][other_field], standard_usage[other_field])

                    # Unique responses channel
                    uniq_ch = obs["raw_usage_channels"]["claude_unique_responses"]
                    self.assertEqual(uniq_ch["status"], "not_observable")
                    self.assertNotEqual(uniq_ch["status"], "exact")
                    self.assertEqual(uniq_ch["native_counters_sum"][target_field], "not_observable")
                    self.assertNotEqual(uniq_ch["native_counters_sum"][target_field], 0)

                    # Contextual stats
                    ctx_usage = obs["observed_contexts"][0]["raw_usage"]
                    self.assertEqual(ctx_usage[target_field], "not_observable")
                    self.assertNotEqual(ctx_usage[target_field], 0)

                    # per_response_sum
                    if target_field in ("input_tokens", "output_tokens"):
                        self.assertEqual(obs["raw_usage"]["per_response_sum"][target_field], "not_observable")
                        self.assertNotEqual(obs["raw_usage"]["per_response_sum"][target_field], 0)

                    valid, errs = validate_against_schema(obs, str(self.schema_path))
                    self.assertTrue(valid, f"Schema validation failed for {target_field}={bad_val}: {errs}")
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

    def test_r2_mixed_versions_degrades_fail_closed(self) -> None:
        """Action Item R2: Mixed versions in a single session must degrade fail-closed."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_mixed_ver",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_mv_1",
                "message": {
                    "id": "msg_mv_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_mixed_ver",
                "uuid": "a2",
                "version": "9.9.9",
                "requestId": "req_mv_2",
                "message": {
                    "id": "msg_mv_2",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-mixed-ver")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("multiple_versions_observed" in r for r in obs["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r3_subagents_strictly_explicit_no_implicit_discovery(self) -> None:
        """Action Item R3: Subagent references are strictly explicit; no implicit discovery of sibling files."""
        parent_fixture = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        sub_meta_fixture = self.fixtures_dir / "06_subagent.meta.json"
        sub_jsonl_fixture = self.fixtures_dir / "06_subagent.jsonl"

        # 1. Providing only .meta.json: reads only meta, turn_count remains 0 (does not implicitly open sibling .jsonl)
        obs_meta_only = parse_claude_session(
            str(parent_fixture),
            run_id="run-sa-meta-only",
            subagent_paths=[str(sub_meta_fixture)]
        )
        child_threads = [t for t in obs_meta_only["thread_topology"]["threads"] if t["role"] == "child"]
        self.assertEqual(len(child_threads), 1)
        self.assertEqual(child_threads[0]["turn_count"], 0)

        # 2. Providing only .jsonl: does NOT open sibling .meta.json; no toolUseId link is made
        obs_jsonl_only = parse_claude_session(
            str(parent_fixture),
            run_id="run-sa-jsonl-only",
            subagent_paths=[str(sub_jsonl_fixture)]
        )
        child_threads_2 = [t for t in obs_jsonl_only["thread_topology"]["threads"] if t["role"] == "child"]
        self.assertEqual(len(child_threads_2), 0)

        # 3. Providing malformed .meta.json does not crash and records error reason
        with tempfile.NamedTemporaryFile(suffix=".meta.json", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write("{malformed json\n")
            tmp_meta_path = tmp.name

        try:
            obs_malformed = parse_claude_session(
                str(parent_fixture),
                run_id="run-sa-malformed",
                subagent_paths=[tmp_meta_path]
            )
            self.assertTrue(any("subagent_meta_read_error" in r for r in obs_malformed["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_meta_path):
                os.remove(tmp_meta_path)

    def test_r4_bounded_memory_collections_caps(self) -> None:
        """Action Item R4: Collections have strict caps and degrade fail-closed upon overflow."""
        # 1. Compactions cap overflow (> 50)
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_comp_overflow",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_1",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            for idx in range(55):
                tmp.write(json.dumps({
                    "type": "system",
                    "sessionId": "sess_comp_overflow",
                    "uuid": f"c_{idx}",
                    "version": "2.1.257",
                    "compactMetadata": {
                        "trigger": "auto",
                        "preTokens": 1000,
                        "postTokens": 500,
                        "cumulativeDroppedTokens": 500,
                        "durationMs": 100,
                        "preservedMessages": {"uuids": ["a1"]}
                    }
                }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-comp-overflow")
            self.assertEqual(len(obs["context_compaction_observations"]), 50)
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("context_compaction_observations_cap_exceeded" in r for r in obs["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 2. Tool use IDs cap overflow (> 100)
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            content_blocks = [{"type": "tool_use", "id": f"toolu_{i:04d}", "name": "bash", "input": {}} for i in range(110)]
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_tu_overflow",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_1",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "content": content_blocks,
                    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp_path_tu = tmp.name

        try:
            obs_tu = parse_claude_session(tmp_path_tu, run_id="run-tu-overflow")
            self.assertEqual(obs_tu["parser_status"]["status"], "partial")
            self.assertEqual(obs_tu["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("observed_tool_use_ids_cap_exceeded" in r for r in obs_tu["parser_status"]["reasons"]))
        finally:
            if os.path.exists(tmp_path_tu):
                os.remove(tmp_path_tu)

    def test_r5_cli_stderr_sanitization_no_absolute_path(self) -> None:
        """Action Item R5: CLI stderr must not leak absolute input paths."""
        fake_secret_path = "/tmp/confidential_classified_dir_xyz/secret_session.jsonl"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "tl_usage.py"),
            "--harness", "claude",
            "--run-id", "test-stderr-sanitization",
            "--session-ref", fake_secret_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn("confidential_classified_dir_xyz", res.stderr)
        self.assertIn("secret_session.jsonl", res.stderr)

    def test_r6_anti_dedup_numerica_distinct_ids_same_counters(self) -> None:
        """Action Item R6 / Invariant I2: Distinct message.ids with identical counters must NOT be deduplicated."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_anti_num",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_1",
                "message": {
                    "id": "msg_first_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_anti_num",
                "uuid": "a2",
                "version": "2.1.257",
                "requestId": "req_2",
                "message": {
                    "id": "msg_second_2",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-anti-num")
            self.assertEqual(obs["raw_usage_channels"]["claude_assistant_messages"]["event_count"], 2)
            self.assertEqual(obs["raw_usage_channels"]["claude_unique_responses"]["event_count"], 2)
            self.assertEqual(obs["normalized_usage"]["semantic_response_count"], 2)
            self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["input_tokens"], 200)
            self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["output_tokens"], 40)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r6_anti_adjacencia_non_adjacent_repetition(self) -> None:
        """Action Item R6 / Invariant I3: Repetitions of same message.id separated by other events are deduplicated."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_anti_adj",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_shared_1",
                "message": {
                    "id": "msg_repeated",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp.write(json.dumps({
                "type": "user",
                "sessionId": "sess_anti_adj",
                "uuid": "u2",
                "version": "2.1.257",
                "message": {"role": "user", "content": [{"type": "text", "text": "intervening user turn"}]}
            }) + "\n")
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_anti_adj",
                "uuid": "a2",
                "version": "2.1.257",
                "requestId": "req_other_2",
                "message": {
                    "id": "msg_other",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 50, "output_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            # Non-adjacent repetition of msg_repeated with same requestId and counters
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_anti_adj",
                "uuid": "a3",
                "version": "2.1.257",
                "requestId": "req_shared_1",
                "message": {
                    "id": "msg_repeated",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-anti-adj")
            self.assertEqual(obs["raw_usage_channels"]["claude_assistant_messages"]["event_count"], 3)
            self.assertEqual(obs["raw_usage_channels"]["claude_unique_responses"]["event_count"], 2)
            self.assertEqual(obs["normalized_usage"]["semantic_response_count"], 2)
            self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["input_tokens"], 150)
            self.assertEqual(obs["normalized_usage"]["semantic_request_sum"]["output_tokens"], 30)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r1_context_stats_cap_overflow_fail_closed(self) -> None:
        """Action Item R1: Over 50 distinct models exceeds context_stats cap and degrades fail-closed."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            for i in range(55):
                tmp.write(json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_ctx_overflow",
                    "uuid": f"a_{i}",
                    "version": "2.1.257",
                    "requestId": f"req_{i}",
                    "message": {
                        "id": f"msg_{i}",
                        "role": "assistant",
                        "model": f"claude-model-variant-{i}",
                        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-ctx-overflow")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertEqual(len(obs["observed_contexts"]), 50)
            self.assertTrue(any("context_stats_cap_exceeded:50" in r for r in obs["parser_status"]["reasons"]))
            self.assertTrue(any("context_stats_cap_exceeded:50" in r for r in obs["normalized_usage"]["ineligibility_reasons"]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r1_subagent_refs_cap_overflow_fail_closed(self) -> None:
        """Action Item R1: Over 50 subagent references exceeds cap and degrades fail-closed."""
        parent_fixture = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        fake_refs = [f"/tmp/fake_sub_{i}.meta.json" for i in range(55)]
        obs = parse_claude_session(str(parent_fixture), run_id="run-sa-cap", subagent_paths=fake_refs)
        self.assertEqual(obs["parser_status"]["status"], "partial")
        self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
        self.assertTrue(any("subagent_refs_cap_exceeded:50" in r for r in obs["parser_status"]["reasons"]))

    def test_r2_assistant_message_missing_or_non_dict_fail_closed(self) -> None:
        """Action Item R2: Assistant event with missing or non-dict message degrades fail-closed."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            # First valid line
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_malformed_msg",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_1",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            # Second line with non-dict message
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_malformed_msg",
                "uuid": "a2",
                "version": "2.1.257",
                "requestId": "req_2",
                "message": "not_a_valid_dict"
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-malformed-msg")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("message_not_dict" in r for r in obs["parser_status"]["reasons"]))
            self.assertNotEqual(obs["source_format_fingerprint"], CLAUDE_CANONICAL_FINGERPRINT)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r2_assistant_usage_missing_or_non_dict_fail_closed(self) -> None:
        """Action Item R2: Assistant event with missing or non-dict usage degrades fail-closed."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            # First valid line
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_malformed_usg",
                "uuid": "a1",
                "version": "2.1.257",
                "requestId": "req_1",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
            }) + "\n")
            # Second line with non-dict usage
            tmp.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess_malformed_usg",
                "uuid": "a2",
                "version": "2.1.257",
                "requestId": "req_2",
                "message": {
                    "id": "msg_2",
                    "role": "assistant",
                    "model": "claude-3-7-sonnet-20250219",
                    "usage": [100, 20]
                }
            }) + "\n")
            tmp_path = tmp.name

        try:
            obs = parse_claude_session(tmp_path, run_id="run-malformed-usg")
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("usage_not_dict" in r for r in obs["parser_status"]["reasons"]))
            self.assertNotEqual(obs["source_format_fingerprint"], CLAUDE_CANONICAL_FINGERPRINT)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_r3_subagent_read_failure_fail_closed_and_no_basename_leak(self) -> None:
        """Action Item R3: Subagent read failure degrades to partial/not_observable and never leaks path basename in JSON."""
        parent_fixture = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        sensitive_name = "secret_agent_007_confidential.meta.json"
        missing_ref = f"/private/vault/{sensitive_name}"

        obs = parse_claude_session(str(parent_fixture), run_id="run-sa-leak-check", subagent_paths=[missing_ref])
        self.assertEqual(obs["parser_status"]["status"], "partial")
        self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
        self.assertTrue(any("subagent_ref_file_not_found" in r for r in obs["parser_status"]["reasons"]))

        # Privacy verification: serialized JSON must not contain sensitive basename or directory
        raw_json = json.dumps(obs)
        self.assertNotIn(sensitive_name, raw_json)
        self.assertNotIn("secret_agent", raw_json)
        self.assertNotIn("private/vault", raw_json)

    def test_r3_subagent_opaque_thread_id_no_basename_derivation(self) -> None:
        """Action Item R3: Subagent thread_id is structurally opaque and derived from toolUseId, not file basename."""
        parent_fixture = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        sub_meta_fixture = self.fixtures_dir / "06_subagent.meta.json"

        obs = parse_claude_session(
            str(parent_fixture),
            run_id="run-sa-opaque",
            subagent_paths=[str(sub_meta_fixture)]
        )
        child_threads = [t for t in obs["thread_topology"]["threads"] if t["role"] == "child"]
        self.assertEqual(len(child_threads), 1)
        self.assertEqual(child_threads[0]["thread_id"], "subagent_toolu_sub_classe_f_01")
        self.assertEqual(child_threads[0]["tool_use_id"], "toolu_sub_classe_f_01")

        # Serialized JSON should not leak "06_subagent"
        raw_json = json.dumps(obs)
        self.assertNotIn("06_subagent", raw_json)

    def test_r1_subagent_malformed_jsonl_fail_closed(self) -> None:
        """Action Item R1 (r03): Malformed JSON line in subagent .jsonl degrades fail-closed with generic reason."""
        parent_fixture = self.fixtures_dir / "06_classe_f_subagents.jsonl"
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write('{"type": "user", "sessionId": "sub_sess_1"}\n')
            tmp.write('{malformed json line in child stream\n')
            tmp_jsonl = tmp.name

        try:
            obs = parse_claude_session(str(parent_fixture), run_id="run-sa-malformed-jsonl", subagent_paths=[tmp_jsonl])
            self.assertEqual(obs["parser_status"]["status"], "partial")
            self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("subagent_jsonl_decode_error" in r for r in obs["parser_status"]["reasons"]))
            # Privacy: no temp filename leaked in serialized JSON
            raw_json = json.dumps(obs)
            self.assertNotIn(os.path.basename(tmp_jsonl), raw_json)
        finally:
            if os.path.exists(tmp_jsonl):
                os.remove(tmp_jsonl)


    def test_r1_multi_subagent_association_and_inverted_order_probe(self) -> None:
        """Action Item R1 (r09): Multi-subagent topology preserves verifiable structural association
        per explicit pair, is order-invariant, and degrades to not_observable when unprovable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Parent session with 2 tool_use events
            parent_file = tmp_path / "parent_session.jsonl"
            parent_lines = [
                json.dumps({
                    "type": "user",
                    "sessionId": "sess_multi_parent",
                    "uuid": "u1",
                    "parentUuid": None,
                    "timestamp": "2025-05-10T12:00:00.000Z",
                    "version": "2.1.257",
                    "message": {"role": "user", "content": [{"type": "text", "text": "Dispatch two subagents"}]}
                }),
                json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_multi_parent",
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "requestId": "req_parent_01",
                    "timestamp": "2025-05-10T12:00:02.000Z",
                    "version": "2.1.257",
                    "message": {
                        "id": "msg_parent_01",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "content": [
                            {"type": "tool_use", "id": "toolu_sub_alpha", "name": "dispatch_subagent", "input": {}}
                        ],
                        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }),
                json.dumps({
                    "type": "user",
                    "sessionId": "sess_multi_parent",
                    "uuid": "u2",
                    "parentUuid": "a1",
                    "timestamp": "2025-05-10T12:00:03.000Z",
                    "version": "2.1.257",
                    "message": {"role": "user", "content": [{"type": "text", "text": "Next dispatch"}]}
                }),
                json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_multi_parent",
                    "uuid": "a2",
                    "parentUuid": "u2",
                    "requestId": "req_parent_02",
                    "timestamp": "2025-05-10T12:00:05.000Z",
                    "version": "2.1.257",
                    "message": {
                        "id": "msg_parent_02",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "content": [
                            {"type": "tool_use", "id": "toolu_sub_beta", "name": "dispatch_subagent", "input": {}}
                        ],
                        "usage": {"input_tokens": 120, "output_tokens": 30, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }),
            ]
            parent_file.write_text("\n".join(parent_lines) + "\n", encoding="utf-8")

            # Subagent Alpha: 2 assistant turns
            meta_alpha = tmp_path / "subagent_alpha.meta.json"
            meta_alpha.write_text(json.dumps({
                "agentType": "general-purpose",
                "toolUseId": "toolu_sub_alpha",
                "sessionId": "sess_sub_alpha"
            }), encoding="utf-8")

            jsonl_alpha = tmp_path / "subagent_alpha.jsonl"
            alpha_lines = [
                json.dumps({"type": "user", "sessionId": "sess_sub_alpha", "uuid": "au1", "version": "2.1.257", "message": {"role": "user", "content": [{"type": "text", "text": "start"}]}}),
                json.dumps({"type": "assistant", "sessionId": "sess_sub_alpha", "uuid": "aa1", "version": "2.1.257", "message": {"id": "m_a1", "role": "assistant", "usage": {"input_tokens": 10, "output_tokens": 5}}}),
                json.dumps({"type": "assistant", "sessionId": "sess_sub_alpha", "uuid": "aa2", "version": "2.1.257", "message": {"id": "m_a2", "role": "assistant", "usage": {"input_tokens": 10, "output_tokens": 5}}}),
            ]
            jsonl_alpha.write_text("\n".join(alpha_lines) + "\n", encoding="utf-8")

            # Subagent Beta: 5 assistant turns
            meta_beta = tmp_path / "subagent_beta.meta.json"
            meta_beta.write_text(json.dumps({
                "agentType": "general-purpose",
                "toolUseId": "toolu_sub_beta",
                "sessionId": "sess_sub_beta"
            }), encoding="utf-8")

            jsonl_beta = tmp_path / "subagent_beta.jsonl"
            beta_lines = [
                json.dumps({"type": "user", "sessionId": "sess_sub_beta", "uuid": "bu1", "version": "2.1.257", "message": {"role": "user", "content": [{"type": "text", "text": "start"}]}}),
            ] + [
                json.dumps({"type": "assistant", "sessionId": "sess_sub_beta", "uuid": f"ba{i}", "version": "2.1.257", "message": {"id": f"m_b{i}", "role": "assistant", "usage": {"input_tokens": 10, "output_tokens": 5}}})
                for i in range(1, 6)
            ]
            jsonl_beta.write_text("\n".join(beta_lines) + "\n", encoding="utf-8")

            # Probe 1: Normal argument order [meta_alpha, jsonl_alpha, meta_beta, jsonl_beta]
            obs_normal = parse_claude_session(
                str(parent_file),
                run_id="run-normal-order",
                subagent_paths=[str(meta_alpha), str(jsonl_alpha), str(meta_beta), str(jsonl_beta)]
            )
            child_threads = {t["thread_id"]: t for t in obs_normal["thread_topology"]["threads"] if t["role"] == "child"}
            self.assertEqual(len(child_threads), 2)
            self.assertEqual(child_threads["subagent_toolu_sub_alpha"]["turn_count"], 2)
            self.assertNotEqual(child_threads["subagent_toolu_sub_alpha"]["turn_count"], 5)
            self.assertEqual(child_threads["subagent_toolu_sub_beta"]["turn_count"], 5)
            self.assertNotEqual(child_threads["subagent_toolu_sub_beta"]["turn_count"], 2)
            self.assertEqual(obs_normal["parser_status"]["status"], "supported")

            # Probe 2: Inverted argument order [jsonl_beta, meta_alpha, jsonl_alpha, meta_beta]
            obs_inverted = parse_claude_session(
                str(parent_file),
                run_id="run-inverted-order",
                subagent_paths=[str(jsonl_beta), str(meta_alpha), str(jsonl_alpha), str(meta_beta)]
            )
            child_threads_inv = {t["thread_id"]: t for t in obs_inverted["thread_topology"]["threads"] if t["role"] == "child"}
            self.assertEqual(len(child_threads_inv), 2)
            self.assertEqual(child_threads_inv["subagent_toolu_sub_alpha"]["turn_count"], 2)
            self.assertNotEqual(child_threads_inv["subagent_toolu_sub_alpha"]["turn_count"], 5)
            self.assertEqual(child_threads_inv["subagent_toolu_sub_beta"]["turn_count"], 5)
            self.assertNotEqual(child_threads_inv["subagent_toolu_sub_beta"]["turn_count"], 2)
            self.assertEqual(obs_inverted["parser_status"]["status"], "supported")

            # Probe 3: Ambiguous / unprovable association (Mismatched stems and sessions)
            mismatched_1 = tmp_path / "other_child_1.jsonl"
            mismatched_1.write_text(json.dumps({"type": "assistant", "sessionId": "other_1", "version": "2.1.257"}) + "\n", encoding="utf-8")
            mismatched_2 = tmp_path / "other_child_2.jsonl"
            mismatched_2.write_text(json.dumps({"type": "assistant", "sessionId": "other_2", "version": "2.1.257"}) + "\n", encoding="utf-8")

            obs_ambiguous = parse_claude_session(
                str(parent_file),
                run_id="run-ambiguous",
                subagent_paths=[str(meta_alpha), str(meta_beta), str(mismatched_1), str(mismatched_2)]
            )
            child_threads_amb = {t["thread_id"]: t for t in obs_ambiguous["thread_topology"]["threads"] if t["role"] == "child"}
            self.assertEqual(len(child_threads_amb), 2)
            self.assertEqual(child_threads_amb["subagent_toolu_sub_alpha"]["turn_count"], "not_observable")
            self.assertNotEqual(child_threads_amb["subagent_toolu_sub_alpha"]["turn_count"], 2)
            self.assertEqual(child_threads_amb["subagent_toolu_sub_beta"]["turn_count"], "not_observable")
            self.assertNotEqual(child_threads_amb["subagent_toolu_sub_beta"]["turn_count"], 5)
            self.assertEqual(obs_ambiguous["parser_status"]["status"], "partial")
            self.assertEqual(obs_ambiguous["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("subagent_jsonl_association_unverifiable:toolu_sub_alpha" in r for r in obs_ambiguous["parser_status"]["reasons"]))
            self.assertTrue(any("subagent_jsonl_association_unverifiable:toolu_sub_beta" in r for r in obs_ambiguous["parser_status"]["reasons"]))

            # Probe 4: Partial child transcripts (One matched, one unassociated)
            obs_partial_sub = parse_claude_session(
                str(parent_file),
                run_id="run-partial-sub",
                subagent_paths=[str(meta_alpha), str(jsonl_alpha), str(meta_beta)]
            )
            child_threads_part = {t["thread_id"]: t for t in obs_partial_sub["thread_topology"]["threads"] if t["role"] == "child"}
            self.assertEqual(len(child_threads_part), 2)
            self.assertEqual(child_threads_part["subagent_toolu_sub_alpha"]["turn_count"], 2)
            self.assertEqual(child_threads_part["subagent_toolu_sub_beta"]["turn_count"], "not_observable")
            self.assertNotEqual(child_threads_part["subagent_toolu_sub_beta"]["turn_count"], 0)
            self.assertNotEqual(child_threads_part["subagent_toolu_sub_beta"]["turn_count"], 2)
            self.assertEqual(obs_partial_sub["parser_status"]["status"], "partial")
            self.assertEqual(obs_partial_sub["normalized_usage"]["status"], "not_observable")
            self.assertTrue(any("subagent_jsonl_association_unverifiable:toolu_sub_beta" in r for r in obs_partial_sub["parser_status"]["reasons"]))


    def test_r1_duplicate_tool_use_id_metadata_collision_probe(self) -> None:
        """Action Item R1 (r10): Multiple explicit metadata files with the same toolUseId collide,
        are preserved without silent overwriting, and degrade fail-closed across all CLI argument permutations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Parent session referencing toolu_sub_alpha
            parent_file = tmp_path / "parent_session.jsonl"
            parent_lines = [
                json.dumps({
                    "type": "user",
                    "sessionId": "sess_collision_parent",
                    "uuid": "u1",
                    "timestamp": "2025-05-10T12:00:00.000Z",
                    "version": "2.1.257",
                    "message": {"role": "user", "content": [{"type": "text", "text": "Dispatch subagent"}]}
                }),
                json.dumps({
                    "type": "assistant",
                    "sessionId": "sess_collision_parent",
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "requestId": "req_col_01",
                    "timestamp": "2025-05-10T12:00:02.000Z",
                    "version": "2.1.257",
                    "message": {
                        "id": "msg_col_01",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-3-7-sonnet-20250219",
                        "content": [
                            {"type": "tool_use", "id": "toolu_sub_alpha", "name": "dispatch_subagent", "input": {}}
                        ],
                        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                    }
                }),
            ]
            parent_file.write_text("\n".join(parent_lines) + "\n", encoding="utf-8")

            # Duplicate metadata file 1 for toolu_sub_alpha: 2 assistant turns in its paired JSONL
            meta_1 = tmp_path / "sub_candidate_1.meta.json"
            meta_1.write_text(json.dumps({
                "agentType": "general-purpose",
                "toolUseId": "toolu_sub_alpha",
                "sessionId": "sess_cand_1"
            }), encoding="utf-8")

            jsonl_1 = tmp_path / "sub_candidate_1.jsonl"
            lines_1 = [
                json.dumps({"type": "user", "sessionId": "sess_cand_1", "version": "2.1.257"}),
                json.dumps({"type": "assistant", "sessionId": "sess_cand_1", "version": "2.1.257"}),
                json.dumps({"type": "assistant", "sessionId": "sess_cand_1", "version": "2.1.257"}),
            ]
            jsonl_1.write_text("\n".join(lines_1) + "\n", encoding="utf-8")

            # Duplicate metadata file 2 for the SAME toolu_sub_alpha: 7 assistant turns in its paired JSONL
            meta_2 = tmp_path / "sub_candidate_2.meta.json"
            meta_2.write_text(json.dumps({
                "agentType": "general-purpose",
                "toolUseId": "toolu_sub_alpha",
                "sessionId": "sess_cand_2"
            }), encoding="utf-8")

            jsonl_2 = tmp_path / "sub_candidate_2.jsonl"
            lines_2 = [
                json.dumps({"type": "user", "sessionId": "sess_cand_2", "version": "2.1.257"}),
            ] + [
                json.dumps({"type": "assistant", "sessionId": "sess_cand_2", "version": "2.1.257"})
                for _ in range(7)
            ]
            jsonl_2.write_text("\n".join(lines_2) + "\n", encoding="utf-8")

            permutations = [
                # Order 1: candidate 1 before candidate 2
                [str(meta_1), str(jsonl_1), str(meta_2), str(jsonl_2)],
                # Order 2: candidate 2 before candidate 1
                [str(meta_2), str(jsonl_2), str(meta_1), str(jsonl_1)],
                # Order 3: JSONLs before metas
                [str(jsonl_1), str(jsonl_2), str(meta_1), str(meta_2)],
                # Order 4: Interleaved reverse
                [str(meta_2), str(jsonl_1), str(meta_1), str(jsonl_2)],
            ]

            for i, p_args in enumerate(permutations):
                obs = parse_claude_session(
                    str(parent_file),
                    run_id=f"run-dup-meta-p{i}",
                    subagent_paths=p_args
                )
                child_threads = {t["thread_id"]: t for t in obs["thread_topology"]["threads"] if t["role"] == "child"}
                self.assertEqual(len(child_threads), 1)
                th = child_threads["subagent_toolu_sub_alpha"]
                # Must degrade to not_observable and never emit 2 or 7 as fact
                self.assertEqual(th["turn_count"], "not_observable")
                self.assertNotEqual(th["turn_count"], 2)
                self.assertNotEqual(th["turn_count"], 7)
                self.assertEqual(obs["parser_status"]["status"], "partial")
                self.assertEqual(obs["normalized_usage"]["status"], "not_observable")
                self.assertTrue(
                    any("subagent_jsonl_association_unverifiable:toolu_sub_alpha" in r for r in obs["parser_status"]["reasons"]),
                    f"Permutation {i} missing reason"
                )


if __name__ == "__main__":
    unittest.main()
