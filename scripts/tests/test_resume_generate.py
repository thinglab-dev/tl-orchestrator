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

    # AC02: Determinism - Two executions on same tree produce byte-identical output
    def test_ac02_determinism(self):
        task_file = "_tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md"
        code1, out1, err1 = self.run_cli("--task", task_file)
        self.assertEqual(code1, 0, f"Run 1 failed: {err1}")

        code2, out2, err2 = self.run_cli("--task", task_file)
        self.assertEqual(code2, 0, f"Run 2 failed: {err2}")

        self.assertEqual(out1, out2, "Two successive runs must be byte-for-byte identical.")

        # Check provenance
        manifest = json.loads(out1)
        self.assertIn("sources", manifest)
        self.assertGreater(len(manifest["sources"]), 0)
        for s in manifest["sources"]:
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
            task_sources = [source for source in manifest["sources"] if source["path"] == "_tl-orc/project/story-bmad.md"]
            self.assertEqual(task_sources, [{
                "path": "_tl-orc/project/story-bmad.md",
                "selector": "### Acceptance criteria",
                "digest": expected.sha256,
            }])
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


if __name__ == "__main__":
    unittest.main()
