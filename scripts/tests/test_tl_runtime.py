"""Behavioural and fault-injection tests for the optional durable runtime."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import tl_ci_slice  # noqa: E402
import tl_runtime  # noqa: E402

FAKE_HARNESS = SCRIPTS / "fixtures" / "runtime" / "fake_harness.py"
FAKE_GH = SCRIPTS / "fixtures" / "runtime" / "fake_gh.py"
SPEC_A = """---
id: T001
title: Add greeting module
type: code
scope_paths: [pkg/]
do_not_touch: [secrets/]
flags: []
acceptance:
  - pkg/greet.py exposes greet()
verification:
  - python -c "import pkg.greet"
---
# T001

Implement greet().
"""
SPEC_B = SPEC_A.replace("T001", "T002").replace("greeting", "farewell").replace("greet", "bye")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()


class Fixture:
    """One consumer repository with a bare remote, two specs, a batch and a runtime config."""

    def __init__(self, root: Path, *, effects: dict | None = None, gates: list | None = None, limits: dict | None = None,
                 max_calls: int = 20, max_rework: int = 2, continue_after_block: bool = False, ci: bool = False, units: int = 2):
        self.root = root
        self.repo = root / "repo"
        self.remote = root / "remote.git"
        self.scenario = root / "scenario"
        self.scenario.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "commit.gpgsign", "false")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "pkg").mkdir()
        (self.repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (self.repo / "secrets").mkdir()
        (self.repo / "secrets" / "keep.txt").write_text("x", encoding="utf-8")
        tasks = self.repo / "_tl-orc" / "project" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "T001-greet.md").write_text(SPEC_A, encoding="utf-8")
        (tasks / "T002-bye.md").write_text(SPEC_B, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "push", "-q", "origin", "main")
        specs = {"T001": SPEC_A, "T002": SPEC_B}
        batch_units = [{"work_ref": "T001", "revision": 0, "spec_revision": hashlib.sha256(SPEC_A.encode()).hexdigest()[:16], "integration_group": "g1", "dependencies": []}]
        if units > 1:
            batch_units.append({"work_ref": "T002", "revision": 0, "spec_revision": hashlib.sha256(SPEC_B.encode()).hexdigest()[:16], "integration_group": "g1", "dependencies": ["T001"]})
        scope = {"batch_concurrency": 1, "advisor_policy": {"enabled": False, "triggers": [], "max_calls": 0}, "units": batch_units,
                 "integration_groups": ["g1"], "major_boundaries": [], "stop_conditions": ["scope_expansion", "model_call_budget_exhausted"]}
        scope["immutable_digest"] = tl_runtime.frozen_scope_digest(scope)
        permitted = {"local_write": True, "local_commit": True, "local_merge": True, "pull_request": False, "push": False, "tag": False, "release": False}
        permitted.update(effects or {})
        self.batch = {
            "id": "B001", "status": "in_progress", "batch_revision": 1,
            "authorization": {"proposal_id": "P1", "proposal_digest": "d" * 16, "authority_source": "test", "authorized_at": "2026-01-01T00:00:00Z",
                              "permitted_effects": permitted, "continue_independent_after_block": continue_after_block},
            "frozen_scope": scope,
            "budget": {"max_model_calls": max_calls, "consumed_model_calls": 0, "reserved_model_calls": 0, "max_rework_rounds_per_unit": max_rework,
                       "max_advisor_calls": 0, "consumed_advisor_calls": 0, "pending_call": None},
            "execution": {"current_unit": None, "current_phase": None, "current_round": None, "expected_tree_checkpoint": None, "completed_units": [], "stop_reason": None, "runtime_refs": {}},
        }
        self.batch_path = root / "B001.json"
        self.batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        self.gh_state = root / "gh.json"
        base_limits = {"backoff_seconds": 0, "transient_retries": 2, "harness_retries": 1, "loop_threshold": 3, "max_parked_units": 5}
        base_limits.update(limits or {})
        adapter = lambda role: {"argv": [sys.executable, str(FAKE_HARNESS), "--scenario", str(self.scenario), "--role", role, "--pack", "{pack_path}", "--result", "{result_path}"],
                                "family": role + "-family", "capabilities": {"tools_allowlist": False, "network_sandbox": False, "usage_telemetry": False}, "usage_parser": "none"}
        self.config = {
            "schema_version": 1,
            "adapters": {"fake-maker": adapter("maker"), "fake-checker": adapter("checker")},
            "roles": {"maker": {"adapter": "fake-maker", "model": "m1", "effort": "low", "timeout_seconds": 120},
                      "checker": {"adapter": "fake-checker", "model": "c1", "effort": "low", "timeout_seconds": 120}},
            "gates": {"always": gates if gates is not None else [{"id": "compile", "argv": [sys.executable, "-c", "import pkg"]}], "by_flag": {}, "canonical": []},
            "limits": base_limits, "base_branch": "main", "gh_executable": [sys.executable, str(FAKE_GH)],
            "ci": {"enabled": ci, "poll_seconds": 0, "timeout_seconds": 5, "flaky_reruns": 1},
            "sensitive_paths": ["secrets/"], "env_allowlist": ["TL_FAKE_GH_STATE"], "accept_unisolated_worker": True,
        }
        self.config_path = root / "runtime.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.state_dir = root / "state"

    def script(self, role: str, actions: list[dict]) -> None:
        (self.scenario / f"{role}.json").write_text(json.dumps(actions), encoding="utf-8")

    def runtime(self) -> tl_runtime.Runtime:
        return tl_runtime.Runtime(self.batch_path, self.config_path, self.repo, self.state_dir, sleep=lambda s: None)

    def run_cli(self, *args: str, fault: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ, TL_FAKE_GH_STATE=str(self.gh_state), PYTHONIOENCODING="utf-8")
        if fault:
            env["TL_RUNTIME_FAULT"] = fault
        return subprocess.run([sys.executable, str(SCRIPTS / "tl_runtime.py"), *args, "--batch", str(self.batch_path), "--config", str(self.config_path),
                               "--repo", str(self.repo), "--state-dir", str(self.state_dir)], capture_output=True, text=True, env=env, encoding="utf-8")

    def journal(self) -> list[dict]:
        path = self.state_dir / "journal.jsonl"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def fold(self) -> tl_runtime.Fold:
        return tl_runtime.Journal(self.state_dir / "journal.jsonl").fold()


MAKER_OK = [{"files": {"pkg/greet.py": "def greet():\n    return 'hi'\n"}}, {"files": {"pkg/bye.py": "def bye():\n    return 'bye'\n"}}]
CHECKER_OK = [{"verdict": "approved"}]


class RuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["TL_FAKE_GH_STATE"] = str(self.root / "gh.json")

    def tearDown(self) -> None:
        os.environ.pop("TL_FAKE_GH_STATE", None)
        self.tmp.cleanup()

    # ---- happy path -------------------------------------------------------------------

    def test_batch_runs_two_dependent_units_and_closes(self) -> None:
        fx = Fixture(self.root)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        state = fx.runtime().run()
        self.assertEqual(state, "done")
        fold = fx.fold()
        self.assertEqual({u: r.state for u, r in fold.units.items()}, {"T001": "completed", "T002": "completed"})
        self.assertEqual(fold.model_calls_done, 4)
        self.assertTrue(fold.units["T001"].merged and fold.units["T002"].merged)
        log = git(fx.repo, "log", "--oneline", "main")
        self.assertIn("T001", log)
        self.assertIn("T002", log)
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")
        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        self.assertEqual(batch["status"], "done")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 4)
        self.assertEqual(batch["frozen_scope"], fx.batch["frozen_scope"])
        report = (fx.state_dir / "report.md").read_text(encoding="utf-8")
        for heading in ("## Completed", "## Changed", "## Commits / PRs", "## Verification", "## Automatically Resolved", "## FYI",
                        "## REVIEW", "## DECISION REQUIRED", "## BLOCKED", "## Cost / Usage", "## Models", "## Recovery Events", "## What Happens Next"):
            self.assertIn(heading, report)
        self.assertIn("- T001: Add greeting module (merged)", report)
        self.assertIn("## Changed" + chr(10) + chr(10) + "- T001: pkg/greet.py", report)
        self.assertIn("tokens: unknown", report)
        status = json.loads((fx.state_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["progress"], {"completed": 2, "total": 2})
        # Second run is a no-op on a closed batch.
        self.assertEqual(fx.runtime().run(), "done")
        # Packs carry the contract, policy, spec and task, in that order, and never the journal.
        pack = (fx.scenario / "maker-0.pack.md").read_text(encoding="utf-8")
        self.assertLess(pack.index("## contract"), pack.index("## policy"))
        self.assertLess(pack.index("## policy"), pack.index("## spec"))
        self.assertIn("scope_paths (only these may change): pkg/", pack)
        self.assertNotIn("journal", pack.lower().split("## task")[1])

    def test_worker_env_is_scrubbed(self) -> None:
        fx = Fixture(self.root)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        os.environ["SUPER_SECRET_TOKEN"] = "ghp_" + "a" * 36
        try:
            fx.runtime().run(max_units=1)
        finally:
            os.environ.pop("SUPER_SECRET_TOKEN")
        seen = json.loads((fx.scenario / "maker-0.env.json").read_text(encoding="utf-8"))
        self.assertNotIn("SUPER_SECRET_TOKEN", seen)
        self.assertIn("PATH", seen)
        self.assertIn("TL_FAKE_GH_STATE", seen)

    # ---- rework, loops, parking ---------------------------------------------------------

    def test_changes_requested_triggers_one_rework_round(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "def greet():\n    return 'hi'\n"}}, {"files": {"pkg/greet.py": "def greet():\n    return 'hello'\n"}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": "R1", "target": "maker", "category": "patch", "summary": "say hello", "paths": ["pkg/greet.py"]}]}, {"verdict": "approved"}])
        self.assertEqual(fx.runtime().run(), "done")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].round, 2)
        self.assertEqual([a["move"] for a in fold.units["T001"].attempts], ["rework"])
        pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("## open_findings", pack)
        self.assertIn("say hello", pack)
        self.assertIn("hello", (fx.repo / "pkg" / "greet.py").read_text(encoding="utf-8"))
        self.assertIn("review r1: verification → rework", (fx.state_dir / "report.md").read_text(encoding="utf-8"))

    def test_rework_exhaustion_parks_unit_and_blocks_dependent(self) -> None:
        fx = Fixture(self.root, max_rework=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n"}}, {"files": {"pkg/greet.py": "x = 2\n"}}, {"files": {"pkg/greet.py": "x = 3\n"}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": f"R{i}", "target": "maker", "category": "patch", "summary": f"wrong: {w}"}]} for i, w in enumerate(["a", "b", "c"])])
        self.assertEqual(fx.runtime().run(), "blocked")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "parked")
        self.assertIn("rework_limit_exhausted", fold.units["T001"].reason)
        self.assertEqual(fold.units["T002"].state, "blocked")
        self.assertIn("dependency_block", fold.units["T002"].reason)
        self.assertEqual(fold.batch_state, "blocked")
        self.assertIn("## BLOCKED\n\n- T001: parked", (fx.state_dir / "report.md").read_text(encoding="utf-8"))

    def test_same_findings_twice_is_stagnation(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=5)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1" + chr(10)}}, {"files": {"pkg/greet.py": "x = 2" + chr(10)}}, {"files": {"pkg/greet.py": "x = 3" + chr(10)}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": "R1", "target": "maker", "category": "patch", "summary": "still wrong"}]}])
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertIn("stagnation", record.reason)
        self.assertEqual(record.round, 2)
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "", "parked work is checkpointed and the tree cleaned")
        self.assertTrue(record.checkpoints)
        self.assertIn("x = 2", git(fx.repo, "show", f"{record.checkpoints[-1]}:pkg/greet.py"))

    def test_continue_independent_after_block_runs_unrelated_unit(self) -> None:
        fx = Fixture(self.root, max_rework=0, continue_after_block=True)
        fx.batch["frozen_scope"]["units"][1]["dependencies"] = []
        fx.batch["frozen_scope"]["immutable_digest"] = tl_runtime.frozen_scope_digest(fx.batch["frozen_scope"])
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n"}}, {"files": {"pkg/bye.py": "y = 1\n"}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": "R1", "target": "maker", "category": "patch", "summary": "wrong"}]}, {"verdict": "approved"}])
        self.assertEqual(fx.runtime().run(), "blocked")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "parked")
        self.assertEqual(fold.units["T002"].state, "completed")

    def test_loop_detector_parks_on_repeated_gate_signature(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=6, gates=[{"id": "always-red", "argv": [sys.executable, "-c", "import sys; print('boom 42'); sys.exit(1)"]}])
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n"}}, {"files": {"pkg/greet.py": "x = 2\n"}}, {"files": {"pkg/greet.py": "x = 3\n"}}, {"files": {"pkg/greet.py": "x = 4\n"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("loop_detected", record.reason)
        self.assertEqual(len(record.attempts), 3)
        self.assertEqual(len({a["signature"] for a in record.attempts}), 1)
        self.assertEqual(fx.fold().model_calls_done, 3, "no checker call is spent while gates are red")

    def test_diff_oscillation_parks(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=6)
        fx.script("maker", [{"files": {"pkg/greet.py": "A\n"}}, {"files": {"pkg/greet.py": "B\n"}}, {"files": {"pkg/greet.py": "A\n"}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": f"R{i}", "target": "maker", "category": "patch", "summary": f"finding {w}"}]} for i, w in enumerate(["alpha", "beta", "gamma", "delta", "epsilon"])])
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertIn("diff_oscillation", record.reason)

    def test_intent_gap_for_human_awaits_operator_and_decide_resumes(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n"}}, {"files": {"pkg/greet.py": "x = 2\n"}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [{"id": "R1", "target": "human", "category": "intent_gap", "summary": "which greeting language?"}]}, {"verdict": "approved"}])
        self.assertEqual(fx.runtime().run(), "blocked")
        self.assertEqual(fx.fold().units["T001"].state, "awaiting_operator")
        report = (fx.state_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("## DECISION REQUIRED\n\n- T001: intent_gap: which greeting language?", report)
        decided = fx.run_cli("decide", "--unit", "T001", "--option", "retry")
        self.assertEqual(decided.returncode, 0, decided.stderr)
        self.assertEqual(fx.fold().units["T001"].state, "retryable")
        self.assertEqual(fx.fold().batch_state, "in_progress", "a batch blocked only on a decision reopens")
        self.assertEqual(fx.run_cli("run").returncode, 0)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertEqual(fold.batch_state, "done")

    def test_pending_verification_matching_a_green_gate_is_resolved_by_runtime(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [
            {"id": "R1", "target": "human", "category": "intent_gap", "summary": "verificacao_pendente: run " + sys.executable + " -c import pkg; proves the package imports.", "paths": ["pkg/"]}]}])
        self.assertEqual(fx.runtime().run(), "done")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertTrue(any("resolved by runtime evidence" in n.get("text", "") for n in fold.notes))
        pack = (fx.scenario / "checker-0.pack.md").read_text(encoding="utf-8")
        self.assertIn("## runtime_verification", pack)
        self.assertIn("compile: pass", pack)

    def test_gate_artifacts_never_reach_the_commit(self) -> None:
        fx = Fixture(self.root, units=1, gates=[{"id": "dirty-gate", "argv": [sys.executable, "-c", "open('pkg/artifact.tmp', 'w').write('x')"]}])
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        self.assertNotIn("artifact.tmp", git(fx.repo, "ls-tree", "-r", "--name-only", "main"))
        self.assertTrue(any("changed the tree" in n.get("text", "") for n in fx.fold().notes))

    def test_unisolated_adapter_needs_explicit_acceptance(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.config.pop("accept_unisolated_worker")
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("accept_unisolated_worker", str(ctx.exception))

    def test_worker_that_moves_head_stops_the_batch(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1" + chr(10)}, "argv": ["git", "commit", "-q", "--allow-empty", "-m", "worker commits by itself"]}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "unexpected_tree_state")

    def test_journal_hash_chain_detects_tampering(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        fx.run_cli("run", fault="after_intent:maker")
        lines = (fx.state_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        edited = json.loads(lines[1])
        edited["state"] = "completed"
        lines[1] = json.dumps(edited, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        (fx.state_dir / "journal.jsonl").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        result = fx.run_cli("run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid line", result.stderr)

    def test_discarded_tree_is_kept_under_a_ref(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=4)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1" + chr(10), "other.txt": "outside"}}, {"files": {"pkg/greet.py": "x = 2" + chr(10)}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        refs = git(fx.repo, "for-each-ref", "--format=%(refname)", "refs/tl/discarded/")
        self.assertTrue(refs, "the scope-violating tree was snapshotted before being discarded")
        self.assertEqual(git(fx.repo, "show", refs.splitlines()[0] + ":other.txt"), "outside")

    def test_linked_worktree_is_supported(self) -> None:
        fx = Fixture(self.root, units=1)
        linked = self.root / "linked"
        git(fx.repo, "worktree", "add", "-q", str(linked), "-b", "linked-main", "main")
        fx.config["base_branch"] = "linked-main"
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        runtime = tl_runtime.Runtime(fx.batch_path, fx.config_path, linked, fx.state_dir, sleep=lambda s: None)
        self.assertEqual(runtime.run(), "done")
        self.assertIn("T001", git(linked, "log", "--oneline", "linked-main"))

    def test_resume_after_commit_with_changed_pack_does_not_redispatch(self) -> None:
        fx = Fixture(self.root, units=1)
        # The Maker adds a test file, so the round-1 pack (related_tests) differs on resume.
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1" + chr(10), "pkg/test_greet.py": "import unittest" + chr(10)}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:commit").returncode, 70)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertEqual(fold.model_calls_done, 2, "no Maker or Checker call is repeated after the commit was reconciled")

    def test_gate_placeholders_and_script_name_matching(self) -> None:
        audit = self.root / "audit.py"
        audit.write_text("import subprocess, sys; base = sys.argv[1]; out = subprocess.run(['git', 'diff', '--name-only', base], capture_output=True, text=True).stdout; sys.exit(0 if out.strip() else 3)", encoding="utf-8")
        fx = Fixture(self.root, units=1, gates=[{"id": "audit", "argv": [sys.executable, str(audit), "{base_commit}"]}])
        fx.script("maker", [{"files": {"pkg/__init__.py": "VERSION = 1" + chr(10)}}])
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [
            {"id": "R1", "target": "human", "category": "intent_gap", "summary": "verificacao_pendente: executar audit.py sobre pkg/__init__.py para confirmar higiene do diff.", "paths": ["pkg/"]}]}])
        self.assertEqual(fx.runtime().run(), "done")
        fold = fx.fold()
        gate = next(v for k, v in fold.steps.items() if k.startswith("gate:audit:"))
        self.assertEqual(gate["result"]["argv"][2], fold.units["T001"].base_commit)
        self.assertTrue(gate["result"]["passed"])
        self.assertTrue(any("resolved by runtime evidence" in n.get("text", "") for n in fold.notes))

    def test_local_write_false_is_refused_before_any_dispatch(self) -> None:
        fx = Fixture(self.root, units=1, effects={"local_write": False})
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("local_write", str(ctx.exception))

    def test_missing_immutable_digest_is_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        del fx.batch["frozen_scope"]["immutable_digest"]
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("immutable_digest", str(ctx.exception))

    def test_secret_beyond_the_pack_diff_cap_is_still_caught(self) -> None:
        fx = Fixture(self.root, units=1, limits={"max_diff_bytes": 1000})
        filler = "# filler" + chr(10)
        fx.script("maker", [{"files": {"pkg/greet.py": filler * 400 + "TOKEN = 'AKIA" + "Q" * 16 + "'" + chr(10)}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "secret_detected")

    def test_local_merge_refuses_a_branch_that_moved_after_review(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:commit").returncode, 70)
        git(fx.repo, "commit", "-q", "--allow-empty", "-m", "someone else pushed to the unit branch")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("moved", record.reason)
        self.assertNotIn("T001", git(fx.repo, "log", "--oneline", "main"))

    def test_pr_merge_is_pinned_to_the_reviewed_commit(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"]}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:pull_request").returncode, 70)
        git(fx.repo, "commit", "-q", "--allow-empty", "-m", "foreign commit on the unit branch")
        git(fx.repo, "push", "-q", "origin", "tl/B001/T001")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "merge"]), 0)

    def test_non_boolean_optional_effects_are_refused(self) -> None:
        fx = Fixture(self.root, units=1, effects={"pull_request_merge": "false"})
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("pull_request_merge", str(ctx.exception))

    def test_rename_out_of_scope_into_scope_is_contained(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=0)
        fx.script("maker", [{"argv": ["git", "mv", "secrets/keep.txt", "pkg/keep.txt"]}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "external_effect_not_authorized")
        self.assertEqual(git(fx.repo, "log", "--oneline", "tl/B001/T001").count(chr(10)), 0, "nothing was committed")
        self.assertIn("keep.txt", git(fx.repo, "status", "--porcelain"), "tree left for inspection, not committed")

    def test_secret_with_scope_violation_still_stops(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"other.txt": "outside", "pkg/greet.py": "TOKEN = 'AKIA" + "Q" * 16 + "'" + chr(10)}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "secret_detected")

    def test_decide_needs_the_lease(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        holder = fx.runtime()
        holder.acquire()
        try:
            out = fx.run_cli("decide", "--unit", "T001", "--option", "skip")
        finally:
            holder.release()
        self.assertEqual(out.returncode, 5, out.stderr)
        self.assertIn("coordinator_conflict", out.stderr)

    def test_merged_pr_at_another_head_is_not_adopted(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"]}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_intent:pull_request_merge").returncode, 70)
        state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        pr = next(iter(state["prs"].values()))
        pr["state"], pr["mergedAt"], pr["head_oid"] = "MERGED", "2026-01-01T00:00:00Z", "f" * 40
        fx.gh_state.write_text(json.dumps(state), encoding="utf-8")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertFalse(record.merged)

    def test_resume_after_commit_does_not_reserve_new_calls(self) -> None:
        fx = Fixture(self.root, units=1, max_calls=2)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:commit").returncode, 70)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.batch_state, "done")
        self.assertEqual(fold.model_calls_done, 2)

    def test_pre_existing_dirt_on_the_unit_branch_is_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        git(fx.repo, "checkout", "-q", "-b", "tl/B001/T001")
        (fx.repo / "pkg" / "user_edit.py").write_text("mine = 1" + chr(10), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "unexpected_tree_state")
        self.assertEqual((fx.repo / "pkg" / "user_edit.py").read_text(encoding="utf-8"), "mine = 1" + chr(10))

    def test_changed_gate_command_is_not_served_from_cache(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=0)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:gate").returncode, 70)
        fx.config["gates"]["always"] = [{"id": "compile", "argv": [sys.executable, "-c", "import sys; sys.exit(1)"]}]
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.run_cli("run", "--accept-stale-version")
        gates = [v for k, v in fx.fold().steps.items() if k.startswith("gate:compile:") and v["status"] == "ok"]
        self.assertTrue(gates)
        self.assertTrue(all(not v["result"]["passed"] and "sys.exit(1)" in " ".join(v["result"]["argv"]) for v in gates), "no green result served from the stale command")

    def test_zero_cost_cap_is_enforced_on_observed_cost(self) -> None:
        fx = Fixture(self.root, units=2)
        fx.config["adapters"]["fake-maker"]["usage_parser"] = "claude_json"
        fx.config["limits"]["max_cost_usd"] = 0
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1" + chr(10)}, "stdout": json.dumps({"usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0.5, "num_turns": 1})}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "cost_budget_exhausted")

    def test_merge_in_progress_after_crash_waits_for_operator(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_intent:local_merge").returncode, 70)
        merge_head = Path(git(fx.repo, "rev-parse", "--git-path", "MERGE_HEAD"))
        merge_head = merge_head if merge_head.is_absolute() else fx.repo / merge_head
        merge_head.write_text(git(fx.repo, "rev-parse", "tl/B001/T001") + chr(10), encoding="utf-8")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        self.assertEqual(fx.fold().units["T001"].state, "awaiting_operator")
        self.assertTrue(merge_head.exists(), "runtime must not abort a merge it did not start")

    def test_report_models_come_from_the_journal(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        fx.config["roles"]["maker"]["model"] = "m9"
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.config["adapters"]["fake-maker"]["capabilities"]["network_sandbox"] = True
        fx.config["adapters"]["fake-checker"]["capabilities"]["network_sandbox"] = True
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        report = fx.run_cli("report").stdout
        self.assertIn("fake-maker / m1 / low", report)
        self.assertNotIn("m9", report)
        self.assertIn("limitation: no network sandbox", report)

    def test_secret_inside_a_binary_file_is_caught(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"argv": [sys.executable, "-c", "open('pkg/blob.bin', 'wb').write(bytes([0, 1, 2, 255]) + b'AKIA" + "Q" * 16 + "')"]}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "secret_detected")

    def test_gate_output_secret_is_redacted_from_packs(self) -> None:
        leak = "AKIA" + "Q" * 16
        fx = Fixture(self.root, units=1, max_rework=1, gates=[{"id": "leaky", "argv": [sys.executable, "-c", "import sys; print('token " + leak + "'); sys.exit(1)"]}])
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        fx.runtime().run()
        pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("## gate_failures", pack)
        self.assertNotIn(leak, pack)
        self.assertIn("[REDACTED:", pack)

    def test_operator_edit_after_review_is_never_committed(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_intent:commit").returncode, 70)
        (fx.repo / "pkg" / "operator.py").write_text("mine = 1" + chr(10), encoding="utf-8")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("reviewed tree", record.reason)
        self.assertEqual(git(fx.repo, "log", "--oneline", "tl/B001/T001").count(chr(10)), 0, "nothing was committed")
        refs = git(fx.repo, "for-each-ref", "refs/tl", "--format=%(refname)").split()
        kept = [ref for ref in refs if "pkg/operator.py" in git(fx.repo, "ls-tree", "-r", "--name-only", ref)]
        self.assertTrue(kept, "the operator edit is preserved in a checkpoint ref, never committed nor lost")

    def test_foreign_pr_on_the_branch_is_not_adopted(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True})
        fx.gh_state.write_text(json.dumps({"prs": {"tl/B001/T001": {"number": 41, "url": "https://example.invalid/pr/41", "state": "MERGED", "mergedAt": "2025-01-01T00:00:00Z", "base": "main", "head_oid": "e" * 40}}}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("pull_request_failed", record.reason)
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertFalse(any(c[:2] == ["pr", "create"] for c in calls))

    def test_gate_leftovers_after_crash_are_not_committed(self) -> None:
        fx = Fixture(self.root, units=1, gates=[{"id": "writer", "argv": [sys.executable, "-c", "open('pkg/artifact.txt', 'w').write('built')"]}])
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:gate").returncode, 70)
        self.assertTrue((fx.repo / "pkg" / "artifact.txt").exists(), "the crash left the gate artifact behind")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("artifact.txt", git(fx.repo, "ls-tree", "-r", "--name-only", "main"))
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")

    def test_zero_model_call_budget_is_refused(self) -> None:
        fx = Fixture(self.root, units=1, max_calls=0)
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("max_model_calls", str(ctx.exception))

    def test_secret_in_a_file_git_would_quote_is_caught(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"argv": [sys.executable, "-c", "open('pkg/s\u00e9gredo espa\u00e7o.bin', 'wb').write(bytes([0, 1, 2, 255]) + b'AKIA" + "Q" * 16 + "')"]}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "secret_detected")

    def test_retargeted_pr_is_not_merged(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"]}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:ci_poll").returncode, 70)
        state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        next(iter(state["prs"].values()))["base"] = "release"
        fx.gh_state.write_text(json.dumps(state), encoding="utf-8")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("release", record.reason)
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertFalse(any(c[:2] == ["pr", "merge"] for c in calls))

    def test_pr_merged_into_another_base_after_crash_is_not_adopted(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"]}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:pull_request_merge").returncode, 70)
        state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        next(iter(state["prs"].values()))["base"] = "release"
        fx.gh_state.write_text(json.dumps(state), encoding="utf-8")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertFalse(record.merged)

    def test_remote_reset_after_a_pushed_crash_is_not_pushed_over(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:push").returncode, 70)
        # Somebody reset the remote branch back to main while the runtime was down.
        git(fx.repo, "push", "-q", "-f", "origin", "main:tl/B001/T001")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.recoveries[0]["verdict"], "ambiguous")
        self.assertEqual(fold.units["T001"].state, "awaiting_operator")
        self.assertEqual(git(fx.repo, "ls-remote", "--heads", "origin", "tl/B001/T001").split()[0], git(fx.repo, "rev-parse", "main"))

    def test_crash_before_push_effect_is_released_and_pushed_once(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_intent:push").returncode, 70)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.recoveries[0]["verdict"], "released")
        self.assertEqual(git(fx.repo, "ls-remote", "--heads", "origin", "tl/B001/T001").split()[0], fold.units["T001"].commit)

    def test_push_that_errors_after_landing_is_not_repeated(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True})
        flag = self.root / "push_failed_once"
        script = self.root / "flaky_git.py"
        script.write_text(
            "import os, subprocess, sys" + chr(10)
            + "args = sys.argv[1:]" + chr(10)
            + "r = subprocess.run(['git', *args])" + chr(10)
            + "if args and args[0] == 'push' and not os.path.exists(" + repr(str(flag)) + "):" + chr(10)
            + "    open(" + repr(str(flag)) + ", 'w').close()" + chr(10)
            + "    sys.stderr.write('error: RPC failed; HTTP 502 curl 22 The requested URL returned error: 502')" + chr(10)
            + "    sys.exit(1)" + chr(10)
            + "sys.exit(r.returncode)" + chr(10), encoding="utf-8")
        if os.name == "nt":
            self.skipTest("a .cmd shim cannot forward multi-line commit messages; this scenario runs on the POSIX CI")
        shim = self.root / "flaky_git"
        shim.write_text("#!/bin/sh" + chr(10) + "exec " + sys.executable + " " + str(script) + ' "$@"' + chr(10), encoding="utf-8")
        shim.chmod(0o755)
        fx.config["git_executable"] = str(shim)
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        fold = fx.fold()
        step = fold.steps["T001:push:" + fold.units["T001"].commit]
        self.assertEqual(step["status"], "ok")
        self.assertIn("push reported an error but the remote is at the commit", step["result"]["detail"])
        self.assertTrue(flag.exists())
        self.assertEqual([a["class"] for a in fold.units["T001"].attempts], [], "no retry was journaled")

    def test_pr_retargeted_between_check_and_merge_is_reported(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"], "retarget_on_merge": "release"}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertTrue(record.merged)
        self.assertIn("merged_into_unexpected_base", record.reason)

    def test_merge_queue_success_reply_is_not_a_merge(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"], "merge_queues": True}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run").returncode, 3)
        fold = fx.fold()
        record = fold.units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("merge_queued", record.reason)
        self.assertFalse(record.merged)
        self.assertEqual(fold.steps["T001:merge:" + record.commit]["status"], "ambiguous")
        # The queue merges it later; the operator retries and the runtime adopts the terminal state without a second merge call.
        state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        pr = next(iter(state["prs"].values()))
        pr["state"], pr["mergedAt"] = "MERGED", "2026-01-01T00:00:00Z"
        fx.gh_state.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(fx.run_cli("decide", "--unit", "T001", "--option", "retry").returncode, 0)
        self.assertEqual(fx.run_cli("run").returncode, 0)
        fold = fx.fold()
        self.assertTrue(fold.units["T001"].merged)
        self.assertEqual(fold.batch_state, "done")
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "merge"]), 1)

    def test_crash_between_merge_call_and_verification_waits_for_operator(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["success"], "merge_queues": True}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_call:pull_request_merge").returncode, 70)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "awaiting_operator")
        self.assertEqual(fold.recoveries[-1]["verdict"], "ambiguous")
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "merge"]), 1, "the merge call is never repeated blindly")

    def test_worktree_tree_sees_a_same_size_rewrite_within_one_second(self) -> None:
        fx = Fixture(self.root, units=1)
        repo_git = tl_runtime.Git(fx.repo, "git")
        target = fx.repo / "pkg" / "racy.py"
        target.write_text("A" + chr(10), encoding="utf-8")
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "racy fixture")
        target.write_text("B" + chr(10), encoding="utf-8")  # same size, same second as the index entry
        time.sleep(1.2)  # the index copy now has a newer second than the entry: stat alone would trust the stale hash
        head_tree = git(fx.repo, "rev-parse", "HEAD^{tree}")
        self.assertNotEqual(repo_git.worktree_tree(), head_tree)
        self.assertEqual(git(fx.repo, "rev-parse", "HEAD^{tree}"), head_tree, "the real index and HEAD are untouched")

    def test_stale_unit_branch_with_foreign_commits_waits_for_operator(self) -> None:
        fx = Fixture(self.root, units=1)
        git(fx.repo, "checkout", "-q", "-b", "tl/B001/T001")
        (fx.repo / "pkg" / "foreign.py").write_text("smuggled = 1" + chr(10), encoding="utf-8")
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "foreign commit on a stale unit branch")
        git(fx.repo, "checkout", "-q", "main")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("stale_branch", record.reason)
        self.assertNotIn("foreign", git(fx.repo, "log", "--oneline", "main"))
        self.assertEqual(fx.fold().model_calls_done, 0, "no Maker was dispatched on a stale branch")

    def test_base_moved_during_interrupted_local_merge_waits_for_operator(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_intent:local_merge").returncode, 70)
        git(fx.repo, "checkout", "-q", "main")
        git(fx.repo, "commit", "-q", "--allow-empty", "-m", "someone moved main while the runtime was down")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "awaiting_operator")
        self.assertEqual(fold.recoveries[-1]["verdict"], "ambiguous")
        self.assertNotIn("T001", git(fx.repo, "log", "--oneline", "main"), "no merge ran on a moved base")

    def test_base_reset_after_a_completed_local_merge_is_not_merged_again(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.run_cli("run", fault="after_effect:local_merge").returncode, 70)
        merged_tip = git(fx.repo, "rev-parse", "main")
        git(fx.repo, "checkout", "-q", "main")
        git(fx.repo, "reset", "-q", "--hard", "HEAD~1")
        git(fx.repo, "commit", "-q", "--allow-empty", "-m", "base rewritten while the runtime was down")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "awaiting_operator")
        self.assertEqual(git(fx.repo, "rev-list", "--count", "main"), "2", "base untouched by the runtime")
        self.assertNotEqual(git(fx.repo, "rev-parse", "main"), merged_tip)

    # ---- policy -----------------------------------------------------------------------------

    def test_scope_expansion_restores_tree_then_parks_on_repeat(self) -> None:
        fx = Fixture(self.root, units=1, max_rework=4)
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n", "other.txt": "outside"}}, {"files": {"pkg/greet.py": "x = 1\n", "other2.txt": "outside again"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("scope_expansion", record.reason)
        self.assertFalse((fx.repo / "other.txt").exists())
        self.assertFalse((fx.repo / "other2.txt").exists())
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")
        pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("tree restored; stay inside scope_paths", pack)

    def test_secret_in_diff_stops_batch(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "TOKEN = 'AKIA" + "Q" * 16 + "'\n"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        fold = fx.fold()
        self.assertEqual(fold.stop_reason, "secret_detected")
        self.assertEqual(git(fx.repo, "log", "--oneline", "main").count("\n"), 0, "nothing was committed")

    def test_sensitive_path_stops_batch(self) -> None:
        fx = Fixture(self.root, units=1)
        widened = SPEC_A.replace("scope_paths: [pkg/]", "scope_paths: [pkg/, secrets/]").replace("do_not_touch: [secrets/]", "do_not_touch: []")
        (fx.repo / "_tl-orc" / "project" / "tasks" / "T001-greet.md").write_text(widened, encoding="utf-8")
        git(fx.repo, "commit", "-q", "-am", "widen")
        digest = hashlib.sha256(widened.encode()).hexdigest()[:16]
        fx.batch["frozen_scope"]["units"][0]["spec_revision"] = digest
        fx.batch["frozen_scope"]["immutable_digest"] = tl_runtime.frozen_scope_digest(fx.batch["frozen_scope"])
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        fx.script("maker", [{"files": {"secrets/keep.txt": "changed"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "external_effect_not_authorized")

    def test_unauthorized_push_is_never_attempted(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": False, "pull_request": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        self.assertEqual(git(fx.repo, "ls-remote", "--heads", "origin"), git(fx.repo, "ls-remote", "--heads", "origin", "main"))
        self.assertFalse(fx.gh_state.exists(), "gh was never called without a push")

    def test_spec_drift_and_scope_drift_are_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        (fx.repo / "_tl-orc" / "project" / "tasks" / "T001-greet.md").write_text(SPEC_A + "\nedited after freeze\n", encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("unexpected_revision_drift", str(ctx.exception))
        (fx.repo / "_tl-orc" / "project" / "tasks" / "T001-greet.md").write_text(SPEC_A, encoding="utf-8")
        fx.batch["frozen_scope"]["units"][0]["integration_group"] = "tampered"
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("frozen_scope digest", str(ctx.exception))

    def test_same_family_review_is_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.config["adapters"]["fake-checker"]["family"] = "maker-family"
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as ctx:
            fx.runtime()
        self.assertIn("required_checker_independence_unavailable", str(ctx.exception))

    # ---- budgets ----------------------------------------------------------------------------

    def test_budget_reserve_stops_before_an_unverifiable_unit(self) -> None:
        fx = Fixture(self.root, max_calls=3)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertEqual(fold.stop_reason, "insufficient_budget_for_unit_verification")
        self.assertEqual(fold.model_calls_done, 2)

    def test_dirty_tree_before_unit_stops(self) -> None:
        fx = Fixture(self.root, units=1)
        (fx.repo / "pkg" / "stray.py").write_text("", encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "unexpected_tree_state")

    def test_lease_is_exclusive(self) -> None:
        fx = Fixture(self.root, units=1)
        first = fx.runtime()
        first.acquire()
        try:
            with self.assertRaises(tl_runtime.Refusal) as ctx:
                fx.runtime().acquire()
            self.assertEqual(ctx.exception.code, 5)
        finally:
            first.release()

    # ---- harness failures --------------------------------------------------------------------

    def test_harness_crash_retries_once_then_parks(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"crash": True, "exit": 3, "stderr": "segfault"}, {"crash": True, "exit": 3, "stderr": "segfault"}, {"files": {"pkg/greet.py": "x\n"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("harness_failure", record.reason)
        self.assertEqual([a["class"] for a in record.attempts], ["harness", "harness"])
        self.assertEqual(fx.fold().model_calls_done, 2)

    def test_missing_harness_executable_is_environment_and_not_charged(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.config["adapters"]["fake-maker"]["argv"][0] = "no-such-harness-binary"
        fx.config_path.write_text(json.dumps(fx.config), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertEqual([a["class"] for a in record.attempts], ["environment"])
        self.assertEqual(fx.fold().model_calls_done, 0, "a dispatch that provably never started is not charged")
        self.assertIn("model calls: 0 / 20", (fx.state_dir / "report.md").read_text(encoding="utf-8"))

    def test_transient_failure_retries_with_backoff_then_succeeds(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"no_result": True, "exit": 1, "stderr": "429 rate limit exceeded"}, {"files": {"pkg/greet.py": "x = 1\n"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        record = fx.fold().units["T001"]
        self.assertEqual([a["class"] for a in record.attempts], ["transient"])
        self.assertEqual(record.round, 1)

    def test_maker_blocked_on_authorization_stops_batch(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"outcome": "blocked", "blockers": ["needs authorization to push to production"]}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "stopped")
        self.assertEqual(fx.fold().stop_reason, "external_effect_not_authorized")

    # ---- crash / replay / reconciliation ---------------------------------------------------------

    def test_crash_before_maker_effect_releases_the_call(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_intent:maker")
        self.assertEqual(first.returncode, 70, first.stderr)
        fold = fx.fold()
        self.assertEqual(len(fold.open_intents), 1)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertEqual([r["verdict"] for r in fold.recoveries], ["released"])
        self.assertEqual(fold.model_calls_done, 2, "the released call was not charged")
        self.assertIn("## Recovery Events\n\n- T001:r1:maker: released", (fx.state_dir / "report.md").read_text(encoding="utf-8"))

    def test_crash_after_maker_effect_consumes_call_and_continues_from_checkpoint(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", [{"files": {"pkg/greet.py": "partial = True\n"}}, {"files": {"pkg/greet.py": "partial = True\ndone = True\n"}}])
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_effect:maker")
        self.assertEqual(first.returncode, 70, first.stderr)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "completed")
        self.assertEqual([r["verdict"] for r in fold.recoveries], ["ambiguous"])
        self.assertEqual(fold.model_calls_done, 3, "the ambiguous call is charged; a second maker call resumes from the checkpoint")
        self.assertTrue(fold.units["T001"].checkpoints)
        pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("## checkpoint", pack)
        self.assertIn("done = True", git(fx.repo, "show", "main:pkg/greet.py"))

    def test_crash_after_commit_is_reconciled_without_a_second_commit(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_effect:commit")
        self.assertEqual(first.returncode, 70, first.stderr)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual([r["verdict"] for r in fold.recoveries], ["ok"])
        self.assertIn("commit found on HEAD", fold.recoveries[0]["detail"])
        self.assertEqual(git(fx.repo, "rev-list", "--count", "main"), "3", "base + unit commit + merge commit")

    def test_crash_after_push_is_reconciled_against_the_remote(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_effect:push")
        self.assertEqual(first.returncode, 70, first.stderr)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.recoveries[0]["verdict"], "ok")
        self.assertIn("remote already at expected commit", fold.recoveries[0]["detail"])
        remote = git(fx.repo, "ls-remote", "--heads", "origin", "tl/B001/T001").split()[0]
        self.assertEqual(remote, fold.units["T001"].commit)

    def test_diverged_remote_after_crash_awaits_operator(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_effect:push")
        self.assertEqual(first.returncode, 70, first.stderr)
        # Somebody else moved the remote branch while the runtime was down.
        other = self.root / "other"
        git(self.root, "clone", "-q", str(fx.remote), str(other))
        git(other, "config", "user.email", "o@example.invalid")
        git(other, "config", "user.name", "o")
        git(other, "checkout", "-q", "tl/B001/T001")
        (other / "pkg" / "foreign.py").write_text("", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "foreign")
        git(other, "push", "-q", "origin", "tl/B001/T001")
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 3, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.recoveries[0]["verdict"], "ambiguous")
        self.assertEqual(fold.units["T001"].state, "awaiting_operator")

    def test_invalid_journal_line_is_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        fx.run_cli("run", fault="after_intent:maker")
        with open(fx.state_dir / "journal.jsonl", "a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        result = fx.run_cli("run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid line", result.stderr)

    def test_stale_runtime_version_stops_until_accepted(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        fx.run_cli("run", fault="after_intent:maker")
        lines = (fx.state_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].replace(tl_runtime.RUNTIME_VERSION + ":", "0.0.1:")
        (fx.state_dir / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        refused = fx.run_cli("run")
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("stale_workflow_version", refused.stderr)
        self.assertEqual(fx.fold().batch_state, "stopped")
        # After inspection the operator accepts the version; the stop is superseded by a new run.
        (fx.state_dir / "journal.jsonl").write_text("\n".join(l for l in lines if '"batch_state"' not in l) + "\n", encoding="utf-8")
        accepted = fx.run_cli("run", "--accept-stale-version")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(fx.fold().units["T001"].state, "completed")

    # ---- CI loop -----------------------------------------------------------------------------------

    def test_ci_code_failure_is_sliced_reworked_and_merged(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["pending", "failure", "success"],
                                           "failed_log": "test\tRun go test\t2026-01-01T00:00:00Z --- FAIL: TestGreet (0.00s)\ntest\tRun go test\t    greet_test.go:12: expected hello\ntest\tRun go test\t##[error]Process completed with exit code 1."}), encoding="utf-8")
        fx.script("maker", [{"files": {"pkg/greet.py": "x = 1\n"}}, {"files": {"pkg/greet.py": "x = 2\n"}}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done")
        fold = fx.fold()
        record = fold.units["T001"]
        self.assertTrue(record.merged)
        self.assertEqual(record.round, 2)
        self.assertEqual([a["class"] for a in record.attempts], ["verification"])
        pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("## ci_failure", pack)
        self.assertIn("TestGreet", pack)
        self.assertNotIn("##[error]", pack.split("## ci_failure")[1].split("excerpt")[0])
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "merge"]), 1)
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "create"]), 1)
        self.assertTrue(any(c[:3] == ["run", "view", "7"] for c in calls), "log taken from the run of the reviewed commit")
        self.assertFalse(any(c[:3] == ["run", "view", "6"] for c in calls))
        self.assertEqual(git(fx.repo, "rev-list", "--count", "main"), "1", "remote merge, no local merge")

    def test_ci_infrastructure_failure_reruns_once_then_parks(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True, "ci_rerun": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["failure", "failure", "failure"],
                                           "failed_log": "job\tstep\t##[error]The hosted runner encountered an error while running your job. lost communication with the server"}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("ci_external_infrastructure", record.reason)
        self.assertEqual(json.loads(fx.gh_state.read_text(encoding="utf-8"))["reruns"], 1)
        self.assertTrue(any(c[:3] == ["run", "rerun", "7"] for c in json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]))
        self.assertFalse(record.merged)
        self.assertIn("T001:ci_rerun:" + record.commit + ":1", fx.fold().steps)

    def test_ci_rerun_without_permission_parks_without_touching_ci(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True}, ci=True)
        fx.gh_state.write_text(json.dumps({"checks_sequence": ["failure"], "failed_log": "job\tstep\t##[error]lost communication with the server"}), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertIn("rerun not permitted", record.reason)
        self.assertNotIn("reruns", json.loads(fx.gh_state.read_text(encoding="utf-8")))

    def test_crash_after_pr_creation_is_reconciled(self) -> None:
        fx = Fixture(self.root, units=1, effects={"push": True, "pull_request": True})
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        first = fx.run_cli("run", fault="after_effect:pull_request")
        self.assertEqual(first.returncode, 70, first.stderr)
        second = fx.run_cli("run")
        self.assertEqual(second.returncode, 0, second.stderr)
        fold = fx.fold()
        self.assertEqual(fold.recoveries[0]["verdict"], "ok")
        calls = json.loads(fx.gh_state.read_text(encoding="utf-8"))["calls"]
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "create"]), 1)
        self.assertIn("REVIEW\n\n- T001: PR https://example.invalid/pr/100 open, not merged", (fx.state_dir / "report.md").read_text(encoding="utf-8"))


class CiSliceTest(unittest.TestCase):
    def test_go_failure_is_code_failure_with_stable_signature(self) -> None:
        log = "2026-01-01T00:00:00.000Z --- FAIL: TestReplay_Timeout (1.23s)\n2026-01-01T00:00:01.000Z     replay_test.go:88: deadline 0x7f3a exceeded\n2026-01-01T00:00:02.000Z ##[error]Process completed with exit code 1."
        first = tl_ci_slice.slice_log(log)
        second = tl_ci_slice.slice_log(log.replace("1.23s", "9.87s").replace("0x7f3a", "0x1b2c").replace("00:00:0", "00:01:0"))
        self.assertEqual(first["classification"], "code_failure")
        self.assertEqual(first["failed_tests"], ["TestReplay_Timeout"])
        self.assertEqual(first["signature"], second["signature"])
        self.assertIn("--- FAIL: TestReplay_Timeout", first["excerpt"])

    def test_pytest_and_unittest_names(self) -> None:
        out = tl_ci_slice.slice_log("FAILED tests/test_a.py::test_x - AssertionError\nFAIL: test_y (tests.test_b.TB.test_y)")
        self.assertEqual(out["failed_tests"], ["tests/test_a.py::test_x", "test_y (tests.test_b.TB.test_y)"])

    def test_infrastructure_and_configuration(self) -> None:
        infra = tl_ci_slice.slice_log("curl: (35) Connection reset by peer\n##[error]Process completed with exit code 35.")
        self.assertEqual(infra["classification"], "external_infrastructure")
        config = tl_ci_slice.slice_log("Invalid workflow file: .github/workflows/x.yml#L3")
        self.assertEqual(config["classification"], "configuration")
        nothing = tl_ci_slice.slice_log("all fine\nnothing here")
        self.assertEqual(nothing["classification"], "unknown")
        self.assertNotIn("flaky", tl_ci_slice.CLASSES)

    def test_excerpt_is_bounded(self) -> None:
        log = "\n".join(f"line {i}" for i in range(500)) + "\n--- FAIL: TestX\n" + "\n".join(f"tail {i}" for i in range(500))
        out = tl_ci_slice.slice_log(log, excerpt_lines=20)
        self.assertEqual(out["excerpt_lines"], 20)
        self.assertEqual(out["total_lines"], 1001)

    def test_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ci.log"
            path.write_text("--- FAIL: TestCli\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPTS / "tl_ci_slice.py"), "--log", str(path)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["failed_tests"], ["TestCli"])


class ParserTest(unittest.TestCase):
    def test_frontmatter_lists_and_scalars(self) -> None:
        data = tl_runtime.parse_frontmatter("---\nid: T1\nflags: [ui, migration]\nscope_paths:\n  - a/\n  - b.py\nok: true\nn: 3\n---\nbody")
        self.assertEqual(data, {"id": "T1", "flags": ["ui", "migration"], "scope_paths": ["a/", "b.py"], "ok": True, "n": 3})

    def test_path_within_and_secret_scan(self) -> None:
        self.assertTrue(tl_runtime.path_within("pkg/x/y.py", ["pkg/"]))
        self.assertFalse(tl_runtime.path_within("pkgx/y.py", ["pkg/"]))
        self.assertTrue(tl_runtime.path_within("a.py", ["a.py"]))
        self.assertTrue(tl_runtime.scan_secrets("key = 'ghp_" + "a" * 36 + "'"))
        self.assertFalse(tl_runtime.scan_secrets("nothing secret here"))

    def test_usage_parsers_never_invent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stdout.log"
            path.write_text('{"type":"result","usage":{"input_tokens":10,"cache_read_input_tokens":5,"output_tokens":2},"total_cost_usd":0.01,"num_turns":3}\n', encoding="utf-8")
            usage = tl_runtime.parse_usage("claude_json", path)
            self.assertEqual((usage["input_tokens"], usage["cache_read_tokens"], usage["cost_usd"], usage["api_calls"]), (10, 5, 0.01, 3))
            path.write_text("plain text\n", encoding="utf-8")
            self.assertIsNone(tl_runtime.parse_usage("claude_json", path)["input_tokens"])
            self.assertIsNone(tl_runtime.parse_usage("none", path)["cost_usd"])


if __name__ == "__main__":
    unittest.main()
