#!/usr/bin/env python3
"""
Unit and counterfactual tests for scripts/resume_generate.py.
Covers AC02 (determinism), AC07 (resolver), and AC15 (pre-dispatch integrity gate).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "resume_generate.py"
SCHEMA_PATH = ROOT / "schemas" / "resume-manifest.schema.json"


class TestResumeGenerate(unittest.TestCase):
    def run_cli(self, *args: str, cwd: Path = ROOT) -> tuple[int, str, str]:
        cmd = [sys.executable, str(SCRIPT)] + list(args)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
        return proc.returncode, proc.stdout, proc.stderr

    # AC02 & AC07: Determinism & Non-identitary metadata
    def test_ac02_determinism(self):
        task_file = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
        fixed_time = "2026-09-17T12:00:00Z"
        code1, out1, err1 = self.run_cli("--task", task_file, "--generated-at", fixed_time)
        self.assertEqual(code1, 0, f"Run 1 failed: {err1}")

        code2, out2, err2 = self.run_cli("--task", task_file, "--generated-at", fixed_time)
        self.assertEqual(code2, 0, f"Run 2 failed: {err2}")

        self.assertEqual(out1, out2, "Two successive runs with fixed timestamp must be byte-for-byte identical.")

        # Canonical identity matches even when generated_at differs (AC07)
        code3, out3, err3 = self.run_cli("--task", task_file, "--generated-at", "2026-09-17T13:00:00Z")
        self.assertEqual(code3, 0)
        m1 = json.loads(out1)
        m3 = json.loads(out3)
        for canonical_key in [
            "sources",
            "resolved_context",
            "spec_revision",
            "state_revision",
            "content_id",
            "generator_version",
            "active_work_ref",
            "bootstrap_budget",
        ]:
            self.assertEqual(m1[canonical_key], m3[canonical_key], f"Canonical identity key {canonical_key} must match.")
        self.assertNotEqual(m1["generated_at"], m3["generated_at"])

        # Check provenance
        self.assertIn("sources", m1)
        self.assertGreater(len(m1["sources"]), 0)
        for s in m1["sources"]:
            self.assertIn("path", s)
            self.assertIn("selector", s)
            self.assertIn("digest", s)

    # AC07: Resolved context manifest contains delivery and reason
    def test_ac07_resolved_context_structure(self):
        task_file = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
        code, stdout, stderr = self.run_cli("--task", task_file)
        self.assertEqual(code, 0)
        manifest = json.loads(stdout)
        resolved = manifest["resolved_context"]
        artifacts = {r["artifact"]: r for r in resolved}
        self.assertIn("active_unit.spec", artifacts)
        self.assertEqual(artifacts["active_unit.spec"]["delivery"], "inline")
        self.assertIn("project.constraints", artifacts)
        self.assertEqual(artifacts["project.constraints"]["delivery"], "excerpt")

    # AC15 & Counterfactual probe: Mutating a source file byte causes integrity check to abort
    def test_ac15_integrity_gate_counterfactual_probe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            # Copy minimal tree
            shutil.copytree(ROOT / "_tl-orc", temp_root / "_tl-orc")
            shutil.copytree(ROOT / "scripts", temp_root / "scripts")

            task_rel = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
            task_file = temp_root / task_rel

            from scripts.resume_generate import generate_resume_manifest, verify_resume_manifest

            # 1. Baseline generation and verification succeeds
            manifest = generate_resume_manifest(temp_root, task_file, "implementation", strict_integrity=True)
            ok, errors = verify_resume_manifest(manifest, temp_root)
            self.assertTrue(ok, f"Baseline verification failed: {errors}")
            self.assertEqual(len(errors), 0)

            # Write manifest to disk and verify via CLI
            manifest_path = temp_root / "resume.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            code_v, out_v, err_v = self.run_cli("--verify", str(manifest_path), cwd=temp_root)
            self.assertEqual(code_v, 0, f"CLI --verify failed: {err_v}")
            self.assertIn("Resume manifest integrity verified", out_v)

            # 2. Counterfactual Probe A: Mutate PROJECT.md frontmatter on disk without updating manifest
            proj_file = temp_root / "_tl-orc" / "PROJECT.md"
            proj_orig = proj_file.read_text(encoding="utf-8")
            proj_file.write_text(proj_orig.replace("work_method: native", "work_method: bmad"), encoding="utf-8")

            # Function must return False and identify the mismatch
            ok_tampered, errors_tampered = verify_resume_manifest(manifest, temp_root)
            self.assertFalse(ok_tampered, "Verification must fail against tampered disk source")
            self.assertTrue(any("digest mismatch" in e and "_tl-orc/PROJECT.md" in e for e in errors_tampered))

            # CLI --verify must exit with code 1
            code_tampered, out_tampered, err_tampered = self.run_cli("--verify", str(manifest_path), cwd=temp_root)
            self.assertEqual(code_tampered, 1, "CLI --verify must fail with exit code 1 when source is tampered")
            self.assertIn("digest mismatch", err_tampered)

            # Re-running generator with strict integrity on tampered state must fail
            # Revert PROJECT.md and mutate task spec instead
            proj_file.write_text(proj_orig, encoding="utf-8")
            task_orig = task_file.read_text(encoding="utf-8")
            task_file.write_text(task_orig.replace("## Spec", "## Spec\nMutated Line in Spec\n"), encoding="utf-8")

            # Against the previous frozen manifest, verification fails
            ok_task_tampered, errors_task = verify_resume_manifest(manifest, temp_root)
            self.assertFalse(ok_task_task := ok_task_tampered)
            self.assertTrue(any("digest mismatch" in e for e in errors_task))

    # R1: Policy argument consumption and validation
    def test_r1_policy_support_and_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            task_file = ROOT / "_tl-orc" / "project" / "tasks" / "T022-context-economy-selective-retrieval-e-handoff-verificavel.md"

            # 1. Custom valid policy altering delivery modes
            custom_policy = {
                "schema_version": 1,
                "classes": [
                    "active_unit.spec",
                    "authorization.current",
                    "unresolved_items",
                    "project.constraints",
                    "applicable_decisions",
                    "dependency_outputs",
                    "previous_rounds",
                    "discussions",
                    "raw_logs",
                    "full_architecture",
                ],
                "phases": {
                    "planning": {"active_unit.spec": "inline"},
                    "implementation": {
                        "active_unit.spec": "excerpt",
                        "project.constraints": "inline",
                    },
                    "review": {"active_unit.spec": "inline"},
                    "rework": {"active_unit.spec": "inline"},
                    "debate": {"active_unit.spec": "on_demand"},
                },
            }
            policy_file = temp_root / "custom_policy.json"
            policy_file.write_text(json.dumps(custom_policy), encoding="utf-8")

            code, out, err = self.run_cli(
                "--task", str(task_file),
                "--policy", str(policy_file),
                "--phase", "implementation",
            )
            self.assertEqual(code, 0, f"Failed with custom policy: {err}")
            manifest = json.loads(out)
            res_ctx = {r["artifact"]: r for r in manifest["resolved_context"]}
            self.assertEqual(res_ctx["active_unit.spec"]["delivery"], "excerpt")
            self.assertEqual(res_ctx["project.constraints"]["delivery"], "inline")

            # 2. Invalid policy rejected
            invalid_policy = {"schema_version": 2}
            invalid_file = temp_root / "invalid_policy.json"
            invalid_file.write_text(json.dumps(invalid_policy), encoding="utf-8")

            code_inv, out_inv, err_inv = self.run_cli(
                "--task", str(task_file),
                "--policy", str(invalid_file),
            )
            self.assertNotEqual(code_inv, 0, "Invalid policy must be rejected")
            self.assertIn("schema_version must be 1", err_inv)

    # R1: Dynamic work_method, effective_authors, and always_read frontmatter
    def test_r1_dynamic_resolution_and_always_read(self):
        task_file = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
        code, out, err = self.run_cli("--task", task_file)
        self.assertEqual(code, 0)
        manifest = json.loads(out)

        # 1. effective_authors is not hardcoded ["google"]
        self.assertEqual(manifest["effective_authors"], [])

        # 2. always_read targets frontmatter of STATUS.md
        always_read = manifest["always_read"]
        self.assertEqual(len(always_read), 1)
        self.assertEqual(always_read[0]["path"], "_tl-orc/project/STATUS.md")
        self.assertEqual(always_read[0]["selector"], "frontmatter")

        # 3. Volatile coordinator fields change does not break verification
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            shutil.copytree(ROOT / "_tl-orc", temp_root / "_tl-orc")
            shutil.copytree(ROOT / "scripts", temp_root / "scripts")

            task_rel = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
            from scripts.resume_generate import generate_resume_manifest, verify_resume_manifest

            m = generate_resume_manifest(temp_root, temp_root / task_rel, "implementation")

            # Mutate only coordinator session and last_write_at in STATUS.md
            status_file = temp_root / "_tl-orc" / "project" / "STATUS.md"
            orig_status = status_file.read_text(encoding="utf-8")
            mutated_status = orig_status.replace("session: claude-code-b5b7f943", "session: sess-new-renewed")
            mutated_status = mutated_status.replace("last_write_at: 20260911T161300Z", "last_write_at: 20260911T180000Z")
            status_file.write_text(mutated_status, encoding="utf-8")

            # Verification MUST succeed because volatile fields are masked
            ok_volatile, errs_volatile = verify_resume_manifest(m, temp_root)
            self.assertTrue(ok_volatile, f"Volatile coordinator renewal should not break integrity: {errs_volatile}")

    def test_r8_bmad_selector_digest_and_integrity_counterfactual(self):
        from scripts.context_lib import select_section
        from scripts.resume_generate import generate_resume_manifest, verify_resume_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            project_dir = temp_root / "_tl-orc" / "project"
            project_dir.mkdir(parents=True)
            (temp_root / "_tl-orc" / "PROJECT.md").write_text(
                "format_version: 1\nwork_method: bmad\n",
                encoding="utf-8",
            )
            (project_dir / "STATUS.md").write_text(
                "format_version: 1\nwork_method: bmad\nactive_work_ref: none\n",
                encoding="utf-8",
            )
            task_file = project_dir / "story-bmad.md"
            task_text = (
                "id: BMAD-7\nstatus: ready\nspec_revision: synthetic\n\n"
                "## Story\n\n"
                "### Acceptance criteria\n"
                "- [ ] AC01 Preserve the selective digest.\n"
                "- [x] AC02 Completed criterion.\n"
            )
            task_file.write_text(task_text, encoding="utf-8")

            manifest = generate_resume_manifest(temp_root, task_file, "implementation")
            expected = select_section(task_text, "### Acceptance criteria")
            expected_fm = select_section(task_text, "frontmatter")
            task_sources = [source for source in manifest["sources"] if source["path"] == "_tl-orc/project/story-bmad.md"]
            self.assertEqual(len(task_sources), 2)
            self.assertIn({
                "path": "_tl-orc/project/story-bmad.md",
                "selector": "### Acceptance criteria",
                "digest": expected.sha256,
            }, task_sources)
            self.assertIn({
                "path": "_tl-orc/project/story-bmad.md",
                "selector": "frontmatter",
                "digest": expected_fm.sha256,
            }, task_sources)
            active = next(item for item in manifest["resolved_context"] if item["artifact"] == "active_unit.spec")
            self.assertEqual(active["selector"], "### Acceptance criteria")
            self.assertEqual(active["digest"], expected.sha256)
            self.assertEqual(manifest["open_items"], ["AC01 Preserve the selective digest."])
            self.assertIn("Execute implementation phase for bmad unit BMAD-7", manifest["next_action"])

            manifest_path = temp_root / "resume.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verify_resume_manifest(manifest, temp_root)[0])

            task_file.write_text(task_text.replace("selective digest", "selective digesT"), encoding="utf-8")
            ok, errors = verify_resume_manifest(manifest, temp_root)
            self.assertFalse(ok)
            self.assertTrue(any("digest mismatch" in error and "Acceptance criteria" in error for error in errors))
            code, _out, err = self.run_cli("--verify", str(manifest_path), cwd=temp_root)
            self.assertEqual(code, 1)
            self.assertIn("digest mismatch", err)

    def test_r8_native_review_digest_and_open_items(self):
        from scripts.context_lib import select_section
        from scripts.resume_generate import generate_resume_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            project_dir = temp_root / "_tl-orc" / "project"
            project_dir.mkdir(parents=True)
            (temp_root / "_tl-orc" / "PROJECT.md").write_text("work_method: native\n", encoding="utf-8")
            (project_dir / "STATUS.md").write_text("work_method: native\n", encoding="utf-8")
            task_file = project_dir / "native-task.md"
            task_text = (
                "id: N-1\nstatus: ready\nspec_revision: synthetic\n\n"
                "## Spec\nimplementation\n\n"
                "## Review\n- [ ] R8 derive review item\n"
            )
            task_file.write_text(task_text, encoding="utf-8")
            manifest = generate_resume_manifest(temp_root, task_file, "rework")
            review = select_section(task_text, "## Review")
            unresolved = next(item for item in manifest["resolved_context"] if item["artifact"] == "unresolved_items")
            self.assertEqual(unresolved["digest"], review.sha256)
            self.assertEqual(manifest["open_items"], ["R8 derive review item"])

    # AC01: Schema Extendido validates state_revision, generated_at, generator_version, bootstrap_budget
    def test_ac01_schema_extended_validation(self):
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        task_file = "_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md"
        code, out, err = self.run_cli("--task", task_file)
        self.assertEqual(code, 0, f"CLI generate failed: {err}")
        manifest = json.loads(out)
        # Must validate cleanly against schema
        jsonschema.validate(instance=manifest, schema=schema)
        self.assertIsInstance(manifest["state_revision"], int)
        self.assertGreaterEqual(manifest["state_revision"], 0)
        self.assertIsInstance(manifest["generated_at"], str)
        self.assertIsInstance(manifest["generator_version"], str)
        self.assertIn("bootstrap_budget", manifest)
        self.assertEqual(manifest["bootstrap_budget"]["unit"], "on_demand_reads")
        self.assertEqual(manifest["bootstrap_budget"]["max_on_demand_reads"], 5)

    # AC03: CLI --verify --json structured output with verified, stale_package_rejected, source_missing
    def test_ac03_verify_structured_and_status_codes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            shutil.copytree(ROOT / "_tl-orc", temp_root / "_tl-orc")
            shutil.copytree(ROOT / "scripts", temp_root / "scripts")

            task_rel = "_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md"
            task_file = temp_root / task_rel
            manifest_path = temp_root / "resume.json"

            # 1. Baseline generate & verify --json -> status: verified, code 0
            code_g, out_g, err_g = self.run_cli("--task", str(task_file), "--output", str(manifest_path), cwd=temp_root)
            self.assertEqual(code_g, 0, f"Generate failed: {err_g}")

            code_v, out_v, err_v = self.run_cli("--verify", str(manifest_path), "--json", cwd=temp_root)
            self.assertEqual(code_v, 0, f"Verify failed: {err_v}")
            data_v = json.loads(out_v)
            self.assertEqual(data_v["status"], "verified")
            self.assertTrue(data_v["ok"])
            self.assertGreater(data_v["checked_sources_count"], 0)
            self.assertEqual(data_v["errors"], [])
            self.assertEqual(data_v["mismatches"], [])

            # 2. Tamper source on disk -> status: stale_package_rejected, code 1
            proj_file = temp_root / "_tl-orc" / "PROJECT.md"
            proj_orig = proj_file.read_text(encoding="utf-8")
            proj_file.write_text(proj_orig.replace("work_method: native", "work_method: bmad"), encoding="utf-8")

            code_tampered, out_tampered, err_tampered = self.run_cli(
                "--verify", str(manifest_path), "--json", cwd=temp_root
            )
            self.assertEqual(code_tampered, 1)
            data_tampered = json.loads(out_tampered)
            self.assertEqual(data_tampered["status"], "stale_package_rejected")
            self.assertFalse(data_tampered["ok"])
            self.assertGreater(len(data_tampered["mismatches"]), 0)
            self.assertTrue(any(m.get("type") == "digest_mismatch" for m in data_tampered["mismatches"]))

            # 3. Missing source file -> status: source_missing, code 1
            proj_file.unlink()
            code_missing, out_missing, err_missing = self.run_cli(
                "--verify", str(manifest_path), "--json", cwd=temp_root
            )
            self.assertEqual(code_missing, 1)
            data_missing = json.loads(out_missing)
            self.assertEqual(data_missing["status"], "source_missing")
            self.assertFalse(data_missing["ok"])
            self.assertTrue(any(m.get("type") == "file_not_found" for m in data_missing["mismatches"]))

    # AC06 & AC09: Bootstrap budget counterfactual and fail-closed check
    def test_ac06_bootstrap_budget_and_fail_closed(self):
        from scripts.resume_generate import check_bootstrap_budget

        # In-process unit verification
        ok_under, msg_under = check_bootstrap_budget(3, 5)
        self.assertTrue(ok_under)
        self.assertIn("3/5 reads used", msg_under)

        ok_at_limit, msg_at_limit = check_bootstrap_budget(5, 5)
        self.assertTrue(ok_at_limit)
        self.assertIn("5/5 reads used", msg_at_limit)

        ok_over, msg_over = check_bootstrap_budget(6, 5)
        self.assertFalse(ok_over)
        self.assertIn("STOP: bootstrap_budget_exceeded", msg_over)

        # CLI invocation
        code_cli_ok, out_cli_ok, _ = self.run_cli("--check-bootstrap-budget", "4", "--max-budget", "5")
        self.assertEqual(code_cli_ok, 0)
        self.assertIn("4/5 reads used", out_cli_ok)

        code_cli_stop, out_cli_stop, _ = self.run_cli(
            "--check-bootstrap-budget", "7", "--max-budget", "5", "--json"
        )
        self.assertEqual(code_cli_stop, 1)
        data_stop = json.loads(out_cli_stop)
        self.assertFalse(data_stop["ok"])
        self.assertEqual(data_stop["status"], "bootstrap_budget_exceeded")
        self.assertIn("STOP: bootstrap_budget_exceeded", data_stop["message"])

    # AC07: generated_at as non-identitary metadata (does not cause false rejection)
    def test_ac07_generated_at_non_identitary_determinism(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            shutil.copytree(ROOT / "_tl-orc", temp_root / "_tl-orc")
            shutil.copytree(ROOT / "scripts", temp_root / "scripts")

            from scripts.resume_generate import generate_resume_manifest, verify_resume_manifest_structured

            task_file = temp_root / "_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md"
            m1 = generate_resume_manifest(temp_root, task_file, "implementation", generated_at="2026-09-17T00:00:00Z")
            m2 = generate_resume_manifest(temp_root, task_file, "implementation", generated_at="2026-09-17T23:59:59Z")

            # Source digests are strictly identical
            self.assertEqual(m1["sources"], m2["sources"])
            self.assertNotEqual(m1["generated_at"], m2["generated_at"])

            # Both verify successfully against current tree
            res1 = verify_resume_manifest_structured(m1, temp_root)
            res2 = verify_resume_manifest_structured(m2, temp_root)
            self.assertEqual(res1["status"], "verified")
            self.assertEqual(res2["status"], "verified")

    # AC09: Counterfactual probe on task frontmatter drift (state_revision)
    def test_ac09_state_revision_drift_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            shutil.copytree(ROOT / "_tl-orc", temp_root / "_tl-orc")
            shutil.copytree(ROOT / "scripts", temp_root / "scripts")

            from scripts.resume_generate import generate_resume_manifest, verify_resume_manifest_structured

            task_file = temp_root / "_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md"
            manifest = generate_resume_manifest(temp_root, task_file, "implementation")
            current_rev = manifest["state_revision"]
            self.assertGreaterEqual(current_rev, 1)

            res_baseline = verify_resume_manifest_structured(manifest, temp_root)
            self.assertEqual(res_baseline["status"], "verified")

            # Mutate state_revision in task frontmatter on disk
            orig_text = task_file.read_text(encoding="utf-8")
            mutated_text = orig_text.replace(f"state_revision: {current_rev}", f"state_revision: {current_rev + 1}")
            task_file.write_text(mutated_text, encoding="utf-8")

            # Verification against disk must detect drift on task frontmatter
            res_drift = verify_resume_manifest_structured(manifest, temp_root)
            self.assertEqual(res_drift["status"], "stale_package_rejected")
            self.assertFalse(res_drift["ok"])
            self.assertTrue(any("frontmatter" in m.get("selector", "") for m in res_drift["mismatches"]))


if __name__ == "__main__":
    unittest.main()
