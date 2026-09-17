#!/usr/bin/env python3
"""AUTO_STORY inside the durable runtime: budget, barrier, lineage and retrocompatibility.

These exercise the real control plane rather than the library in isolation, because §2.8 and
§2.12 are claims about what the runtime does with a worker and a budget, not about what a
helper returns when called directly.
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

from story_authority_support import story

import tl_runtime  # noqa: E402
from scripts.tests.test_tl_runtime import CHECKER_OK, MAKER_OK, Fixture, SPEC_A, git  # noqa: E402
from tl_merge_guard import temporary_platform_anchor_for_testing  # noqa: E402
from scripts.fixtures.runtime.fake_gh import TEST_FIXTURE_KEY_ID, TEST_FIXTURE_PUBLIC_KEY  # noqa: E402

PATCH_ITEM = {
    "id": "R5", "severity": "medium", "category": "patch", "target_role": "maker",
    "location": "pkg/greet.py:1", "problem": "greet() returns an unbounded value",
    "evidence": "the compile gate passes but the acceptance criterion is unmet",
    "required_action": "return the bounded greeting",
}


class AutoStoryRuntimeTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tl-auto-story-runtime-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.environ["TL_FAKE_GH_STATE"] = str(self.root / "gh.json")
        self.addCleanup(lambda: os.environ.pop("TL_FAKE_GH_STATE", None))
        anchor = temporary_platform_anchor_for_testing({TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()})
        anchor.__enter__()
        self.addCleanup(anchor.__exit__, None, None, None)

    # ---- scaffolding --------------------------------------------------------------------

    def auto_story_fixture(self, *, budget: int = 8, max_rework: int = 2, max_calls: int = 8,
                           limits: dict | None = None) -> Fixture:
        fx = Fixture(self.root, units=1, max_calls=max_calls, max_rework=max_rework, limits=limits)
        spec_sha = hashlib.sha256(SPEC_A.encode()).hexdigest()
        payload = story.build_authority_payload(
            authority_id="A001", work_ref="T001", authorized_spec_revision=spec_sha[:16],
            authorized_spec_sha256=spec_sha,
            authorized_write_scope={"required_mutation_targets": ["pkg"],
                                    "conditional_mutation_targets": [],
                                    "forbidden_paths": ["secrets"]},
            allowed_effects={"local_write": True, "local_commit": True, "local_merge": True,
                             "pull_request": False, "push": False, "tag": False, "release": False,
                             "merge": False},
            protected_paths=[], global_model_call_budget=budget, max_child_batches=2,
            max_consecutive_failed_batches=2, wall_clock_deadline="2027-01-01T00:00:00Z",
            hard_stops=["scope_expansion", "model_call_budget_exhausted", "state_integrity"])
        envelope = story.freeze_authority(
            payload,
            authorized_literal=story.authorization_literal("T001", story.root_authority_digest(payload)),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        story.publish_authority(fx.repo, envelope)
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "freeze story authority A001")

        with story.StoryAuthority.open_for(fx.repo, "A001") as authority:
            proposal = story.derive_child_proposal(
                authority=authority, child_batch_id="B001", action_items=[], previous_child_id=None,
                model_call_budget=budget, governance_base_commit=git(fx.repo, "rev-parse", "HEAD"),
                story_baseline_commit=git(fx.repo, "rev-parse", "HEAD"))
            proof = story.verify_derivation(authority, proposal)
            authority.record_child_derived(proposal, proof)

        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        self.envelope = envelope
        return fx

    def authority(self, fx: Fixture) -> story.StoryAuthority:
        return story.StoryAuthority(self.envelope, fx.repo / story.RUNTIME_AUTHORITY_DIR / "A001", repo=fx.repo)

    # ---- §2.12 one charge, two ledgers ---------------------------------------------------

    def test_auto_story_batch_charges_the_story_budget_exactly_once_per_call(self) -> None:
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        state = fx.runtime().run()
        self.assertEqual(state, "done", fx.state_dir)

        fold = fx.fold()
        self.assertEqual(fold.model_calls_done, 2)
        authority = self.authority(fx)
        authority.journal.fold()
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.consumed_calls, 2)
        self.assertEqual(authority.remaining_global_budget, 6)
        projection = authority.child_budget_projection("B001")
        self.assertEqual(projection["consumed_model_calls"], 2)
        # Every attempt the batch journal charged is an attempt the authority journal owns.
        self.assertEqual(len(projection["global_attempt_ids"]), 2)
        self.assertEqual(authority.state.closure_of("B001")["checker_verdict"], "approved")

    def test_global_budget_stops_the_batch_before_the_child_ledger_would(self) -> None:
        """The child allocation is generous; the Story ceiling is what actually binds."""
        fx = self.auto_story_fixture(budget=8, max_calls=8)
        # Another child under the same authority has already spent seven of the eight calls.
        with self.authority(fx) as spender:
            for index in range(7):
                story.budgeted_authority_dispatch(
                    spender, child_batch_id="B000", logical_call_id=f"B000-call-{index}", role="maker",
                    phase="implementation", dispatch=lambda _a: {"state": "completed"})
            self.assertEqual(spender.remaining_global_budget, 1)

        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        state = fx.runtime().run()
        self.assertEqual(state, "stopped")
        fold = fx.fold()
        # The child ledger still shows an allocation of eight; one global call cannot cover Maker
        # plus an independent Checker, so the Story ceiling is what stops the batch.
        self.assertEqual(fold.stop_reason, "insufficient_budget_for_unit_verification")
        self.assertIn("story authority A001", json.dumps(fx.journal()))
        self.assertEqual(fold.model_calls_done, 0)
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.consumed_calls, 7)
        self.assertEqual(authority.child_budget_projection("B001")["consumed_model_calls"], 0)

    # ---- §2.8 mechanical barrier ---------------------------------------------------------

    def test_worker_cannot_invoke_a_cognitive_cli_directly(self) -> None:
        probe = self.root / "probe.json"
        script = (
            "import json,subprocess,sys,pathlib;"
            "r=subprocess.run(['codex','exec','write the patch'],capture_output=True,text=True);"
            f"pathlib.Path({str(probe)!r}).write_text(json.dumps("
            "{'code':r.returncode,'err':r.stderr[-300:],'out':r.stdout[-300:]}))"
        )
        fx = self.auto_story_fixture()
        fx.script("maker", [{"files": MAKER_OK[0]["files"], "argv": [sys.executable, "-c", script]}])
        fx.script("checker", CHECKER_OK)
        state = fx.runtime().run()
        self.assertEqual(state, "done")

        self.assertTrue(probe.is_file(), "the worker probe never ran")
        observed = json.loads(probe.read_text(encoding="utf-8"))
        self.assertEqual(observed["code"], story.BARRIER_EXIT_CODE)
        self.assertIn("cognitive call barrier", observed["err"])
        self.assertEqual(observed["out"], "")

        barrier = fx.state_dir / "cognitive-barrier"
        self.assertTrue(barrier.is_dir())
        installed = sorted(p.stem for p in barrier.iterdir())
        self.assertEqual(installed, sorted(story.COGNITIVE_CLIS))

    def test_auto_story_refuses_to_start_without_the_story_authority_module(self) -> None:
        fx = self.auto_story_fixture()
        original = tl_runtime.story_authority
        tl_runtime.story_authority = None
        try:
            with self.assertRaises(tl_runtime.Refusal) as raised:
                fx.runtime()
            self.assertIn("tl_story_authority.py", str(raised.exception))
        finally:
            tl_runtime.story_authority = original

    def test_auto_story_batch_missing_its_derivation_chain_is_refused(self) -> None:
        fx = self.auto_story_fixture()
        for field in ("story_authority_id", "root_authority_digest", "child_proposal_digest",
                      "derivation_proof_digest"):
            batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
            batch["authorization"].pop(field)
            fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
            with self.assertRaises(tl_runtime.Refusal) as raised:
                fx.runtime()
            self.assertIn(field, str(raised.exception))
            fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")

        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["authorization"]["root_authority_digest"] = "f" * 64
        fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime()
        self.assertIn("authority_missing_or_ambiguous", str(raised.exception))

    # ---- §2.11 functional lineage from a real rework-exhausted child ----------------------

    def test_rework_limit_exhausted_preserves_the_reviewed_commit_unmerged(self) -> None:
        # The stagnation detector is relaxed here so the unit reaches the rework ceiling literally,
        # which is the termination §2.11 names; the checkpoint is preserved for the other park
        # reasons in this cycle too, and test_stagnation_also_preserves_the_checkpoint proves it.
        fx = self.auto_story_fixture(budget=6, max_rework=1, max_calls=6, limits={"stagnation_rounds": 6})
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [PATCH_ITEM]}])
        state = fx.runtime().run()
        self.assertEqual(state, "blocked")
        fold = fx.fold()
        self.assertEqual(fold.units["T001"].state, "parked")
        self.assertIn("rework_limit_exhausted", fold.units["T001"].reason)

        ref = "refs/tl/functional-checkpoints/B001/T001"
        checkpoint = git(fx.repo, "rev-parse", ref)
        self.assertRegex(checkpoint, "^[0-9a-f]{40}$")

        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        closure = authority.state.closure_of("B001")
        self.assertIsNotNone(closure)
        self.assertEqual(closure["checker_verdict"], "changes_requested")
        self.assertEqual(closure["checker_reviewed_commit"], checkpoint)
        self.assertEqual(closure["checker_reviewed_tree"], git(fx.repo, "rev-parse", f"{checkpoint}^{{tree}}"))
        self.assertEqual(closure["unresolved_action_items_digest"],
                         story.unresolved_action_items_digest([PATCH_ITEM]))

        # The reviewed work exists as a commit, carries the Maker's file, and main never saw it.
        self.assertIn("pkg/greet.py", git(fx.repo, "ls-tree", "--name-only", "-r", checkpoint))
        self.assertNotIn("pkg/greet.py", git(fx.repo, "ls-tree", "--name-only", "-r", "main"))
        self.assertEqual(git(fx.repo, "branch", "--contains", checkpoint, "--list", "main"), "")

        # A derived child can now be verified against exactly that checkpoint.
        with story.StoryAuthority.open_for(fx.repo, "A001") as reopened:
            child = story.derive_child_proposal(
                authority=reopened, child_batch_id="B002", action_items=[PATCH_ITEM],
                previous_child_id="B001", model_call_budget=2,
                governance_base_commit=closure["governance_base_commit"],
                story_baseline_commit=closure["governance_base_commit"])
            self.assertEqual(child["functional_parent_checkpoint"],
                             {"commit": checkpoint, "tree": closure["checker_reviewed_tree"],
                              "child_batch_id": "B001"})
            proof = story.verify_derivation(reopened, child, action_items=[PATCH_ITEM],
                                            spec_paths=["_tl-orc/project/tasks/T001-greet.md"])
            self.assertEqual(proof["root_authority_digest"], self.envelope["root_authority_digest"])

    def test_stagnation_also_preserves_the_checkpoint(self) -> None:
        """A child stopped by the loop detector still leaves its reviewed commit as evidence."""
        fx = self.auto_story_fixture(budget=6, max_rework=3, max_calls=6)
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [PATCH_ITEM]}])
        self.assertEqual(fx.runtime().run(), "blocked")
        self.assertIn("stagnation", fx.fold().units["T001"].reason)
        checkpoint = git(fx.repo, "rev-parse", "refs/tl/functional-checkpoints/B001/T001")
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.closure_of("B001")["checker_reviewed_commit"], checkpoint)

    def test_closing_the_same_child_twice_journals_one_terminal_state(self) -> None:
        """Re-running a blocked batch must not re-count the child against the failure streak."""
        fx = self.auto_story_fixture(budget=6, max_rework=1, max_calls=6, limits={"stagnation_rounds": 6})
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [PATCH_ITEM]}])
        self.assertEqual(fx.runtime().run(), "blocked")
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        streak = authority.state.consecutive_failures
        terminal = [e for e in authority.journal.read()[0] if e["kind"] in {"child_closed", "child_failed"}]
        self.assertEqual(len(terminal), 1)

        fx.runtime().run()
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.consecutive_failures, streak)
        terminal = [e for e in authority.journal.read()[0] if e["kind"] in {"child_closed", "child_failed"}]
        self.assertEqual(len(terminal), 1)

    # ---- §5 retrocompatibility ------------------------------------------------------------

    def test_legacy_batch_without_story_authority_mode_is_untouched(self) -> None:
        fx = Fixture(self.root, units=1)
        self.assertNotIn("story_authority_mode", fx.batch["authorization"])
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        runtime = fx.runtime()
        self.assertIsNone(runtime.authority)
        self.assertEqual(runtime.authority_mode, "direct_proposal")
        self.assertIsNone(runtime.policy.cognitive_barrier)
        self.assertNotIn("TL_COGNITIVE_CALL_BARRIER", runtime.policy.worker_env())
        self.assertEqual(runtime.run(), "done")
        self.assertFalse((fx.repo / story.RUNTIME_AUTHORITY_DIR).exists())
        self.assertFalse((fx.state_dir / "cognitive-barrier").exists())

    def test_unknown_story_authority_mode_is_refused(self) -> None:
        fx = Fixture(self.root, units=1)
        fx.batch["authorization"]["story_authority_mode"] = "AUTO_EVERYTHING"
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime()
        self.assertIn("story_authority_mode", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
