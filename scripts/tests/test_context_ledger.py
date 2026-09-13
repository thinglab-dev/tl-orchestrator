#!/usr/bin/env python3
"""
Unit and counterfactual tests for scripts/context_ledger.py.
Covers AC11 (ledger generation & pricing), AC12 (rotation observability), and AC16 (confinement gate).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "context_ledger.py"
TRANSCRIPTS_DIR = ROOT / "scripts" / "fixtures" / "transcripts"


class TestContextLedger(unittest.TestCase):
    def run_cli(self, transcript_file: Path, *extra_args: str) -> dict:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(transcript_file),
            "--unit",
            "T015",
            "--phase",
            "implementation",
        ] + list(extra_args)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, f"CLI failed: {proc.stderr}")
        return json.loads(proc.stdout)

    # AC11: Ledger metrics, tokens, pricing block
    def test_ac11_ledger_generation(self):
        res = self.run_cli(TRANSCRIPTS_DIR / "transcript_normal.jsonl")
        self.assertEqual(res["unit"], "T015")
        self.assertEqual(res["phase"], "implementation")
        self.assertEqual(res["turn_count"], 3)
        self.assertEqual(res["tool_calls"], 1)

        # Tokens
        tokens = res["tokens"]
        self.assertGreater(tokens["input_tokens"], 0)
        self.assertGreater(tokens["output_tokens"], 0)

        # Tool metrics
        tool_metrics = res["tool_metrics"]
        self.assertGreater(tool_metrics["raw_result_bytes"], 0)
        self.assertIsNotNone(tool_metrics["tool_delivery_ratio"])

        # Pricing block
        pricing = res["pricing"]
        self.assertIn(pricing["basis"], ["official_task_proxy", "token_price_only", "unknown"])
        self.assertEqual(pricing["subscription_quota_impact"], "unknown")
        self.assertIsInstance(pricing["assumptions"], list)

    # AC12: Rotation observability
    def test_ac12_rotation_recommendation(self):
        res = self.run_cli(TRANSCRIPTS_DIR / "transcript_normal.jsonl")
        rotation = res["rotation"]
        self.assertFalse(rotation["rotation_recommended"])
        self.assertEqual(rotation["reason"], "not_calibrated")
        self.assertEqual(rotation["applied_thresholds"], {})

        # Simulate heavy transcript triggering rotation recommendation
        from scripts.context_ledger import build_ledger_from_transcript
        import tempfile
        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            for i in range(35):
                tf.write(f'{{"step_index": {i}, "type": "USER_INPUT"}}\n')
            tf.flush()
            heavy_res = build_ledger_from_transcript(
                Path(tf.name), "T015", "implementation", max_turns=30
            )
            self.assertTrue(heavy_res["rotation"]["rotation_recommended"])
            self.assertIn("Turn count", heavy_res["rotation"]["reason"])

    # AC16 Confinement Gate & Counterfactual Probe
    def test_ac16_confinement_gate(self):
        # 1. Normal transcript has no reads outside allowed set
        res_normal = self.run_cli(
            TRANSCRIPTS_DIR / "transcript_normal.jsonl",
            "--allowed-inputs",
            "docs/",
        )
        self.assertEqual(res_normal["reads_outside_allowed_set"], [])

        # 2. Leaked transcript accesses ~/thinglab/platform/secrets.env
        res_leak = self.run_cli(
            TRANSCRIPTS_DIR / "transcript_leak.jsonl",
            "--allowed-inputs",
            "docs/",
        )
        self.assertGreater(len(res_leak["reads_outside_allowed_set"]), 0)
        self.assertTrue(
            any("thinglab/platform" in path for path in res_leak["reads_outside_allowed_set"]),
            f"External access not flagged: {res_leak['reads_outside_allowed_set']}",
        )

    # R2: Auditoria de leituras via comandos Bash
    def test_r2_bash_read_commands_auditing(self):
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript

        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            # 1. read_section.py with flags and json output
            tf.write(json.dumps({
                "step_index": 1,
                "tool_calls": [{
                    "tool": "Bash",
                    "parameters": {"command": "python3 scripts/read_section.py --file docs/WORK_MODEL.md --heading '## Layout'"},
                    "output": json.dumps({"path": "docs/WORK_MODEL.md", "heading": "## Layout", "bytes": 100, "digest": "digest_layout", "content": "## Layout\ncontent"}),
                }]
            }) + "\n")

            # 2. cat command
            tf.write(json.dumps({
                "step_index": 2,
                "tool_calls": [{
                    "tool": "run_command",
                    "parameters": {"CommandLine": "cat docs/WORK_MODEL.md"},
                    "output": "sample content for cat",
                }]
            }) + "\n")

            # 3. head command
            tf.write(json.dumps({
                "step_index": 3,
                "tool_calls": [{
                    "tool": "commandline",
                    "parameters": {"cmd": "head -n 20 docs/WORK_MODEL.md"},
                    "output": "sample content for head",
                }]
            }) + "\n")

            # 4. sed command
            tf.write(json.dumps({
                "step_index": 4,
                "tool_calls": [{
                    "tool": "terminal",
                    "parameters": {"CommandLine": "sed -n '1,10p' docs/WORK_MODEL.md"},
                    "output": "sample content for sed",
                }]
            }) + "\n")
            tf.flush()

            ledger = build_ledger_from_transcript(Path(tf.name), "T015", "implementation")
            self.assertEqual(len(ledger["observed_reads"]), 4)
            self.assertEqual(ledger["tool_calls"], 4)

            # Check read_section parsing
            first_read = ledger["observed_reads"][0]
            self.assertEqual(first_read["path"], "docs/WORK_MODEL.md")
            self.assertEqual(first_read["selector"], "## Layout")
            self.assertEqual(first_read["digest"], "digest_layout")
            self.assertEqual(first_read["bytes"], 100)

            # Check cat/head/sed parsing
            for read_entry in ledger["observed_reads"][1:]:
                self.assertEqual(read_entry["path"], "docs/WORK_MODEL.md")
                self.assertEqual(read_entry["selector"], "full_file")
                self.assertGreater(read_entry["bytes"], 0)

    # R2: Strict confinement and counterfactual probe (no substring evasion)
    def test_r2_strict_confinement_counterfactual_probe(self):
        from scripts.context_ledger import is_path_in_allowed_set

        # Substring evasion probe: "docs_fake/secret.txt" contains "docs" as substring
        # Under strict confinement, it MUST NOT match "docs"
        self.assertFalse(
            is_path_in_allowed_set("docs_fake/secret.txt", allowed_inputs=["docs"], allowed_support=[]),
            "Substring evasion allowed: docs_fake was permitted by 'docs'",
        )

        # Directory traversal probe
        self.assertFalse(
            is_path_in_allowed_set("../outside/secret.txt", allowed_inputs=["docs"], allowed_support=[]),
            "Directory traversal was permitted",
        )

        # External path probe
        self.assertFalse(
            is_path_in_allowed_set("/etc/passwd", allowed_inputs=[], allowed_support=[]),
            "System file /etc/passwd was permitted",
        )

        # Legitimate nested file
        self.assertTrue(
            is_path_in_allowed_set("docs/WORK_MODEL.md", allowed_inputs=["docs"], allowed_support=[]),
        )

        # R7 exploit proof: repository support paths no longer carry an
        # implicit allowlist.
        self.assertFalse(
            is_path_in_allowed_set("docs/unlisted-secret.md", allowed_inputs=[], allowed_support=[]),
        )

    # R2: Failed read attempts separation
    def test_r2_failed_read_attempts(self):
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript

        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            # 1. Failed bash read (FileNotFound)
            tf.write(json.dumps({
                "step_index": 1,
                "tool_calls": [{
                    "tool": "Bash",
                    "parameters": {"command": "cat nonexistent_file.txt"},
                    "output": "cat: nonexistent_file.txt: No such file or directory",
                    "exit_code": 1,
                }]
            }) + "\n")

            # 2. Failed direct tool read
            tf.write(json.dumps({
                "step_index": 2,
                "tool_calls": [{
                    "tool": "read_section",
                    "parameters": {"file": "docs/WORK_MODEL.md", "heading": "## Missing"},
                    "output": "SelectorNotFoundError: heading '## Missing' not found",
                    "is_error": True,
                }]
            }) + "\n")
            tf.flush()

            ledger = build_ledger_from_transcript(Path(tf.name), "T015", "implementation")
            self.assertEqual(len(ledger["observed_reads"]), 0)
            self.assertEqual(len(ledger["failed_read_attempts"]), 2)

            fail1 = ledger["failed_read_attempts"][0]
            self.assertEqual(fail1["path"], "nonexistent_file.txt")
            self.assertEqual(fail1["bytes_delivered"], 0)
            self.assertEqual(fail1["outcome"], "No such file or directory")

            fail2 = ledger["failed_read_attempts"][1]
            self.assertEqual(fail2["path"], "docs/WORK_MODEL.md")
            self.assertEqual(fail2["bytes_delivered"], 0)
            self.assertEqual(fail2["outcome"], "SelectorNotFoundError")

    # R2: Allowed-set frozen file reference and loading
    def test_r2_allowed_set_reference_and_loading(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w+", suffix=".json") as as_tf:
            allowed_data = {
                "inputs": ["_tl-orc/project/tasks/T015-test.md"],
                "allowed_support": ["fixtures/custom/"],
            }
            as_tf.write(json.dumps(allowed_data))
            as_tf.flush()

            res = self.run_cli(
                TRANSCRIPTS_DIR / "transcript_normal.jsonl",
                "--allowed-set",
                as_tf.name,
            )

            al_block = res["allowed_set"]
            self.assertEqual(al_block["reference"], as_tf.name)
            self.assertIn("_tl-orc/project/tasks/T015-test.md", al_block["inputs"])
            self.assertIn("fixtures/custom/", al_block["allowed_support"])

    # R2: Wrapper telemetry divergence
    def test_r2_wrapper_telemetry_divergence(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w+", suffix=".json") as wt_tf:
            # Aligned telemetry (contains docs/WORK_MODEL.md as read in transcript_normal.jsonl)
            wt_tf.write(json.dumps({"reads": ["docs/WORK_MODEL.md"]}))
            wt_tf.flush()

            res_aligned = self.run_cli(
                TRANSCRIPTS_DIR / "transcript_normal.jsonl",
                "--wrapper-telemetry",
                wt_tf.name,
            )
            td_aligned = res_aligned["telemetry_divergence"]
            self.assertIsNotNone(td_aligned)
            self.assertEqual(td_aligned["status"], "aligned")
            self.assertEqual(td_aligned["divergence_count"], 0)

        with tempfile.NamedTemporaryFile("w+", suffix=".json") as wt_tf2:
            # Divergent telemetry
            wt_tf2.write(json.dumps({"reads": ["docs/OTHER.md"]}))
            wt_tf2.flush()

            res_divergent = self.run_cli(
                TRANSCRIPTS_DIR / "transcript_normal.jsonl",
                "--wrapper-telemetry",
                wt_tf2.name,
            )
            td_div = res_divergent["telemetry_divergence"]
            self.assertIsNotNone(td_div)
            self.assertEqual(td_div["status"], "divergent")
            self.assertEqual(td_div["divergence_count"], 2)
            self.assertIn("docs/WORK_MODEL.md", td_div["in_transcript_not_in_telemetry"])
            self.assertIn("docs/OTHER.md", td_div["in_telemetry_not_in_transcript"])

    # R2: Retrieval Amplification (RA) metric
    def test_r2_retrieval_amplification(self):
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript

        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            # Two reads of same content (redundant retrieval)
            line1 = {
                "step_index": 1,
                "tool_calls": [{
                    "tool": "read_section",
                    "parameters": {"file": "docs/WORK_MODEL.md", "heading": "## Layout"},
                    "output": "content block with 50 bytes text...................",
                }]
            }
            line2 = {
                "step_index": 2,
                "tool_calls": [{
                    "tool": "read_section",
                    "parameters": {"file": "docs/WORK_MODEL.md", "heading": "## Layout"},
                    "output": "content block with 50 bytes text...................",
                }]
            }
            tf.write(json.dumps(line1) + "\n" + json.dumps(line2) + "\n")
            tf.flush()

            # Default RA: 100 bytes total / 50 bytes unique = 2.0
            ledger = build_ledger_from_transcript(Path(tf.name), "T015", "implementation")
            self.assertIsNotNone(ledger["retrieval_amplification"])
            self.assertEqual(ledger["retrieval_amplification"], 2.0)

            # With sources manifest:
            with tempfile.NamedTemporaryFile("w+", suffix=".json") as sm_tf:
                digest = ledger["observed_reads"][0]["digest"]
                sm_tf.write(json.dumps({"sources": [{"digest": digest}]}))
                sm_tf.flush()

                ledger_sources = build_ledger_from_transcript(
                    Path(tf.name),
                    "T015",
                    "implementation",
                    sources_manifest_path=Path(sm_tf.name),
                )
                self.assertEqual(ledger_sources["retrieval_amplification"], 1.0)

    # R2: Configurable rotation thresholds
    def test_r2_configurable_rotation_thresholds(self):
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript

        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            for i in range(12):
                tf.write(f'{{"step_index": {i}, "type": "USER_INPUT"}}\n')
            tf.flush()

            # Default max_turns is 30 -> 12 turns does not trigger
            res_default = build_ledger_from_transcript(Path(tf.name), "T015", "implementation")
            self.assertFalse(res_default["rotation"]["rotation_recommended"])
            self.assertEqual(res_default["rotation"]["reason"], "not_calibrated")
            self.assertEqual(res_default["rotation"]["applied_thresholds"], {})

            # Custom max_turns is 10 -> 12 turns triggers recommendation
            res_custom = build_ledger_from_transcript(
                Path(tf.name),
                "T015",
                "implementation",
                max_turns=10,
                max_tool_bytes=2000,
                max_cache_tokens=5000,
            )
            self.assertTrue(res_custom["rotation"]["rotation_recommended"])
            self.assertIn("10", res_custom["rotation"]["reason"])
            thresholds = res_custom["rotation"]["applied_thresholds"]
            self.assertEqual(thresholds["max_turns"], 10)
            self.assertEqual(thresholds["max_tool_bytes"], 2000)
            self.assertEqual(thresholds["max_cache_tokens"], 5000)

    def test_r7_read_section_payload_and_multiline_pipeline_parser(self):
        import hashlib
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript, parse_bash_read_commands

        section = "## Layout\ncanonical section\n"
        payload = {
            "path": "docs/WORK_MODEL.md",
            "heading_path": "## Layout",
            "sha256": hashlib.sha256(section.encode("utf-8")).hexdigest(),
            "bytes": len(section.encode("utf-8")),
            "content": section,
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            tf.write(json.dumps({
                "tool_calls": [{
                    "tool": "Bash",
                    "parameters": {"command": "python3 scripts/read_section.py --file docs/WORK_MODEL.md --heading '## Layout'"},
                    "output": json.dumps(payload),
                }],
            }) + "\n")
            tf.flush()
            ledger = build_ledger_from_transcript(Path(tf.name), "T015", "implementation")

        observed = ledger["observed_reads"][0]
        self.assertEqual(observed["digest"], payload["sha256"])
        self.assertNotEqual(observed["digest"], hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest())
        self.assertEqual(observed["bytes"], payload["bytes"])
        self.assertEqual(observed["selector"], "## Layout")

        reads = parse_bash_read_commands(
            "echo 'docs/not-a-read.md' | sed -n 's/x/y/p'\n"
            "cat <<'EOF'\n"
            "docs/not-a-read-either.md\n"
            "EOF\n"
            "python3 scripts/read_section.py --file docs/WORK_MODEL.md --heading '## Layout' | sed -n 's/x/y/p'\n"
            "sed -i '' 's/x/y/' transient-output.tmp"
        )
        self.assertEqual(reads, [("docs/WORK_MODEL.md", "## Layout")])

    def test_r7_direct_read_grep_and_glob_use_explicit_roots_and_cwd(self):
        import tempfile
        from scripts.context_ledger import build_ledger_from_transcript

        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tf:
            for tool, path in [
                ("Read", "WORK_MODEL.md"),
                ("Grep", "WORK_MODEL.md"),
                ("Glob", "*.md"),
                ("Grep", "../outside/secret.md"),
            ]:
                tf.write(json.dumps({
                    "tool_calls": [{
                        "tool": tool,
                        "parameters": {"path": path, "cwd": "docs"},
                        "output": "result",
                    }],
                }) + "\n")
            tf.flush()
            ledger = build_ledger_from_transcript(
                Path(tf.name), "T015", "implementation", allowed_inputs=["docs"]
            )

        self.assertEqual(len(ledger["observed_reads"]), 4)
        self.assertEqual(ledger["reads_outside_allowed_set"], ["../outside/secret.md"])

    # R2: Schema validation guarantee
    def test_r2_schema_validation_guarantee(self):
        from scripts.context_ledger import validate_context_ledger

        res = self.run_cli(TRANSCRIPTS_DIR / "transcript_normal.jsonl")
        is_valid, errors = validate_context_ledger(res)
        self.assertTrue(is_valid, f"Ledger failed validation: {errors}")

        # Counterfactual probe: tampering with required field fails validation
        tampered = dict(res)
        del tampered["retrieval_amplification"]
        is_valid, errors = validate_context_ledger(tampered)
        self.assertFalse(is_valid)
        self.assertIn("Missing required field: retrieval_amplification", errors[0])


if __name__ == "__main__":
    unittest.main()
