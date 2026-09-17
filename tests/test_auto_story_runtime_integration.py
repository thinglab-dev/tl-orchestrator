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
                           limits: dict | None = None, forbidden: tuple[str, ...] = ("secrets",),
                           scope: tuple[str, ...] = ("pkg",), seed_files: dict | None = None,
                           effects: dict | None = None, register: bool = True,
                           spec_sha: str | None = None, spec_text: str = SPEC_A) -> Fixture:
        fx = Fixture(self.root, units=1, max_calls=max_calls, max_rework=max_rework, limits=limits,
                     effects=effects)
        for relative, content in (seed_files or {}).items():
            target = fx.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        if spec_text != SPEC_A:
            (fx.repo / "_tl-orc" / "project" / "tasks" / "T001-greet.md").write_text(spec_text, encoding="utf-8")
            fx.batch["frozen_scope"]["units"][0]["spec_revision"] = hashlib.sha256(spec_text.encode()).hexdigest()[:16]
            fx.batch["frozen_scope"]["immutable_digest"] = tl_runtime.frozen_scope_digest(fx.batch["frozen_scope"])
        spec_sha = spec_sha or hashlib.sha256(spec_text.encode()).hexdigest()
        payload = story.build_authority_payload(
            authority_id="A001", work_ref="T001", authorized_spec_revision=spec_sha[:16],
            authorized_spec_sha256=spec_sha,
            authorized_write_scope={"required_mutation_targets": list(scope),
                                    "conditional_mutation_targets": [],
                                    "forbidden_paths": list(forbidden)},
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
            if register:
                authority.record_child_derived(proposal, proof)

        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        self.envelope = envelope
        self.proposal, self.proof = proposal, proof
        return fx

    def assert_refused_before_any_worker(self, fx: Fixture, *fragments: str) -> str:
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime().run()
        message = str(raised.exception)
        for fragment in fragments:
            self.assertIn(fragment, message)
        self.assertFalse((fx.scenario / "maker.count").exists(), "a Maker was dispatched")
        self.assertFalse((fx.scenario / "checker.count").exists(), "a Checker was dispatched")
        self.assertFalse((fx.state_dir / "journal.jsonl").exists(), "the batch journal was opened")
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.attempts, {}, "a model call was reserved")
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")
        # Refusing must leave both leases free for the operator's next move.
        with self.authority(fx):
            pass
        return message

    def rewrite_batch(self, fx: Fixture, mutate) -> None:
        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        mutate(batch)
        fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")

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

    # ---- §2.4 the executable batch is bound to the registered derivation -------------------

    def test_batch_that_was_never_derived_is_refused_before_any_worker(self) -> None:
        """Digests that were computed but never registered under the authority grant nothing."""
        fx = self.auto_story_fixture(register=False)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assert_refused_before_any_worker(fx, "authority_missing_or_ambiguous", "child_is_registered", "B001")
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.hard_stops[-1]["reason"], "authority_missing_or_ambiguous")
        self.assertEqual(authority.state.derived, [])

    def test_batch_id_that_is_not_the_registered_child_is_refused(self) -> None:
        """The derivation is looked up for exactly batch.id: a sibling's digests do not transfer."""
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.rewrite_batch(fx, lambda batch: batch.__setitem__("id", "B002"))
        self.assert_refused_before_any_worker(fx, "child_is_registered", "B002")

    def test_tampered_derivation_digests_are_refused_before_any_worker(self) -> None:
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        for field in ("child_proposal_digest", "derivation_proof_digest"):
            self.rewrite_batch(fx, lambda batch, field=field: batch["authorization"].__setitem__(field, "f" * 64))
            self.assert_refused_before_any_worker(fx, "state_integrity", "batch_declares_registered_digests", field)
            fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        # Untouched, the very same fixture runs: the refusals above were about the digests alone.
        self.assertEqual(fx.runtime().run(), "done")

    def test_registered_proposal_edited_in_the_journal_is_refused_before_any_worker(self) -> None:
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        journal = fx.repo / story.RUNTIME_AUTHORITY_DIR / "A001" / "journal.jsonl"
        original = journal.read_text(encoding="utf-8")
        self.assertIn('"forbidden_paths":["secrets"]', original)
        # The edit stays inside the envelope on purpose: nothing but recomputing the digest of the
        # registered document can tell that it is no longer the document that was registered.
        journal.write_text(original.replace('"forbidden_paths":["secrets"]', '"forbidden_paths":["secrets","tmp"]'),
                           encoding="utf-8")
        self.assertNotEqual(journal.read_text(encoding="utf-8"), original)
        self.assert_refused_before_any_worker(fx, "state_integrity", "child_proposal_digest_recomputed")

        # An edit that leaves the envelope is refused for that, by the same proof that derived it.
        journal.write_text(original.replace('"model_call_budget":8', '"model_call_budget":80'), encoding="utf-8")
        self.assert_refused_before_any_worker(fx, "model_call_budget_exhausted", "budget_within_envelope")

    def test_batch_asking_for_more_than_its_derived_child_is_refused(self) -> None:
        fx = self.auto_story_fixture(budget=8, max_calls=8)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.rewrite_batch(fx, lambda batch: batch["budget"].__setitem__("max_model_calls", 9))
        self.assert_refused_before_any_worker(fx, "model_call_budget_exhausted", "batch_budget_within_grant")

        self.rewrite_batch(fx, lambda batch: (batch["budget"].__setitem__("max_model_calls", 8),
                                              batch["authorization"]["permitted_effects"].__setitem__("push", True)))
        self.assert_refused_before_any_worker(fx, "effect_expansion", "batch_effects_within_child", "push")

    def test_batch_whose_unit_is_not_the_authorized_spec_is_refused(self) -> None:
        fx = self.auto_story_fixture(spec_sha="c" * 64)
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assert_refused_before_any_worker(fx, "unexpected_revision_drift", "batch_spec_is_the_authorized_spec")

    def test_batch_scope_wider_than_its_derived_child_is_refused(self) -> None:
        """The unit declares pkg/, but the Story only ever authorized pkg/sub."""
        fx = self.auto_story_fixture(scope=("pkg/sub",))
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        self.assert_refused_before_any_worker(fx, "scope_expansion", "batch_scope_within_child", "T001:pkg/")

    def test_second_child_forged_as_first_child_is_refused_by_the_runtime(self) -> None:
        """B001 closed with findings; a B002 written straight into the journal as a parentless
        first child would restart from the governance base and skip the patch-only proof."""
        fx = self.auto_story_fixture(budget=8, max_rework=1, max_calls=4, limits={"stagnation_rounds": 6})
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [PATCH_ITEM]}])
        self.assertEqual(fx.runtime().run(), "blocked")

        forged = dict(self.proposal, child_batch_id="B002", model_call_budget=2)
        proof = {
            "schema_version": 1, "authority_id": "A001", "work_ref": "T001", "child_batch_id": "B002",
            "parent_child_batch_id": None, "root_authority_digest": self.envelope["root_authority_digest"],
            "parent_authority_digest": self.envelope["root_authority_digest"], "parent_batch_digest": "",
            "child_proposal_digest": story.digest_of(forged), "functional_parent_checkpoint": None,
            "unresolved_action_items_digest": "", "granted_model_calls": 2,
            "checks": [{"check": "everything", "result": "pass"}],
        }
        proof["derivation_proof_digest"] = story._proof_digest(proof)
        with self.authority(fx) as authority:
            with self.assertRaises(story.HardStop) as gateway:
                authority.record_child_derived(forged, proof)
            self.assertIn("first_child_is_the_only_root", gateway.exception.detail)
            authority.journal.append(
                "child_derived", authority_id="A001", child_batch_id="B002", parent_child_batch_id=None,
                root_authority_digest=proof["root_authority_digest"],
                parent_authority_digest=proof["parent_authority_digest"], parent_batch_digest="",
                child_proposal_digest=proof["child_proposal_digest"],
                derivation_proof_digest=proof["derivation_proof_digest"], granted_model_calls=2,
                functional_parent_checkpoint=None, unresolved_action_items_digest="",
                child_proposal=forged, derivation_proof=proof)

        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["id"] = "B002"
        batch["budget"]["max_model_calls"] = 2
        batch["authorization"].update({"child_proposal_digest": proof["child_proposal_digest"],
                                       "derivation_proof_digest": proof["derivation_proof_digest"]})
        second = self.root / "B002.json"
        second.write_text(json.dumps(batch), encoding="utf-8")
        for counter in fx.scenario.glob("*.count"):
            counter.unlink()
        runtime = tl_runtime.Runtime(second, fx.config_path, fx.repo, self.root / "state-b002", sleep=lambda s: None)
        with self.assertRaises(tl_runtime.Refusal) as raised:
            runtime.run()
        self.assertIn("first_child_is_the_only_root", str(raised.exception))
        self.assertFalse((fx.scenario / "maker.count").exists(), "a Maker was dispatched for the forged child")

    def test_derived_child_runs_from_the_bound_checkpoint_and_closes_the_story(self) -> None:
        """B001 exhausts its rework, B002 is derived, bound and executed by the real runtime."""
        fx = self.auto_story_fixture(budget=8, max_rework=1, max_calls=4, limits={"stagnation_rounds": 6})
        fx.script("maker", MAKER_OK)
        fx.script("checker", [{"verdict": "changes_requested", "action_items": [PATCH_ITEM]}])
        self.assertEqual(fx.runtime().run(), "blocked")
        checkpoint = git(fx.repo, "rev-parse", "refs/tl/functional-checkpoints/B001/T001")
        main_before = git(fx.repo, "rev-parse", "main")

        with self.authority(fx) as authority:
            spent = authority.state.consumed_calls
            closure = authority.state.closure_of("B001")
            child = story.derive_child_proposal(
                authority=authority, child_batch_id="B002", action_items=[PATCH_ITEM], previous_child_id="B001",
                model_call_budget=2, governance_base_commit=closure["governance_base_commit"],
                story_baseline_commit=closure["governance_base_commit"])
            proof = story.verify_derivation(authority, child, action_items=[PATCH_ITEM],
                                            spec_paths=["_tl-orc/project/tasks/T001-greet.md"])
            authority.record_child_derived(child, proof)

        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["id"] = "B002"
        batch["budget"]["max_model_calls"] = 2
        batch["authorization"].update({"child_proposal_digest": proof["child_proposal_digest"],
                                       "derivation_proof_digest": proof["derivation_proof_digest"]})
        second = self.root / "B002.json"
        second.write_text(json.dumps(batch), encoding="utf-8")
        for counter in fx.scenario.glob("*.count"):
            counter.unlink()
        fx.script("maker", [{"files": {"pkg/greet.py": "def greet():\n    return 'hi'[:2]\n"}}])
        fx.script("checker", CHECKER_OK)
        state_dir = self.root / "state-b002"
        runtime = tl_runtime.Runtime(second, fx.config_path, fx.repo, state_dir, sleep=lambda s: None)
        self.assertEqual(runtime.run(), "done", state_dir)
        self.assertEqual(runtime.child_binding["functional_parent_checkpoint"]["commit"], checkpoint)

        fold = tl_runtime.Journal(state_dir / "journal.jsonl").fold()
        self.assertEqual(fold.units["T001"].base_commit, checkpoint, "B002 must start at B001's reviewed commit")
        # B001 reached main only through B002's approved candidate, never on its own.
        self.assertNotEqual(git(fx.repo, "rev-parse", "main"), main_before)
        self.assertIn(checkpoint, git(fx.repo, "rev-list", "main").split())
        self.assertIn("[:2]", git(fx.repo, "show", "main:pkg/greet.py"))

        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.closure_of("B002")["checker_verdict"], "approved")
        self.assertEqual(authority.state.consumed_calls, spent + 2)
        self.assertEqual(authority.child_budget_projection("B002")["consumed_model_calls"], 2)

    def test_crash_and_resume_rebinds_and_charges_each_physical_attempt_once(self) -> None:
        """A second process re-proves the same registered derivation and never pays a call twice."""
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        crashed = fx.run_cli("run", fault="after_effect:maker")
        self.assertEqual(crashed.returncode, 70, crashed.stderr)
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.consumed_calls, 1, "the Maker call was settled before the crash")

        resumed = fx.run_cli("run")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(fx.fold().batch_state, "done")

        authority.state = authority.journal.fold()
        physical = sum(int((fx.scenario / f"{role}.count").read_text(encoding="utf-8")) for role in ("maker", "checker"))
        attempts = authority.state.attempts
        self.assertEqual(authority.state.consumed_calls, physical, "one charge per physical provider attempt")
        self.assertEqual(authority.state.open_reservations, 0)
        self.assertEqual(len(attempts), len({a["global_attempt_id"] for a in attempts.values()}))
        self.assertEqual(authority.remaining_global_budget, 8 - physical)
        # Both processes bound to the one registered derivation: nothing was re-derived, no refusal
        # was journaled, and the child reached exactly one terminal state.
        events, invalid = authority.journal.read()
        self.assertEqual(invalid, 0)
        kinds = [event["kind"] for event in events]
        self.assertEqual(kinds.count("child_derived"), 1)
        self.assertEqual(kinds.count("hard_stop"), 0)
        self.assertEqual(kinds.count("child_closed") + kinds.count("child_failed"), 1)
        self.assertEqual(authority.state.closure_of("B001")["checker_verdict"], "approved")

    # ---- forbidden paths nested inside a broad scope path ----------------------------------

    FORBIDDEN_SEED = {"pkg/blocked.txt": "keep\n", "pkg/vault/key.txt": "keep\n"}
    FORBIDDEN = ("secrets", "pkg/blocked.txt", "pkg/vault/")

    def test_forbidden_descendant_of_a_broad_scope_is_policy_before_and_after_the_maker(self) -> None:
        """scope_paths is pkg/, the child forbids pkg/blocked.txt and pkg/vault/: both stay forbidden."""
        touching = {"pkg/greet.py": "def greet():\n    return 'hi'\n", "pkg/blocked.txt": "overwritten\n",
                    "pkg/vault/new.txt": "planted\n"}

        # Control: the very same Maker under a legacy batch. The paths are inside scope_paths, so
        # nothing but the Story Authority's forbidden_paths stands between them and a commit.
        legacy_root = self.root / "legacy"
        legacy_root.mkdir()
        legacy = Fixture(legacy_root, units=1)
        for relative, content in self.FORBIDDEN_SEED.items():
            (legacy.repo / relative).parent.mkdir(parents=True, exist_ok=True)
            (legacy.repo / relative).write_text(content, encoding="utf-8")
        git(legacy.repo, "add", "-A")
        git(legacy.repo, "commit", "-q", "-m", "seed")
        legacy.script("maker", [{"files": touching}])
        legacy.script("checker", CHECKER_OK)
        self.assertEqual(legacy.runtime().run(), "done")
        self.assertEqual(git(legacy.repo, "show", "main:pkg/blocked.txt"), "overwritten")
        self.assertIn("pkg/vault/new.txt", git(legacy.repo, "ls-tree", "-r", "--name-only", "main"))

        fx = self.auto_story_fixture(forbidden=self.FORBIDDEN, seed_files=self.FORBIDDEN_SEED)
        self.assertEqual(self.proposal["forbidden_paths"], ["pkg/blocked.txt", "pkg/vault/", "secrets"])
        fx.script("maker", [{"files": touching}, {"files": {"pkg/greet.py": touching["pkg/greet.py"]}}])
        fx.script("checker", CHECKER_OK)
        runtime = fx.runtime()
        self.assertEqual(runtime.run(), "done", fx.state_dir)

        # Before the Maker: the prohibition is in the unit policy and in the pack it was handed.
        self.assertEqual(runtime.units["T001"].do_not_touch, ["pkg/blocked.txt", "pkg/vault", "secrets", "secrets/"])
        first_pack = (fx.scenario / "maker-0.pack.md").read_text(encoding="utf-8")
        policy_line = next(line for line in first_pack.splitlines() if line.startswith("do_not_touch:"))
        for path in ("pkg/blocked.txt", "pkg/vault", "secrets"):
            self.assertIn(path, policy_line)

        # After the Maker: containment refused the round, restored the tree and said why.
        attempts = [event for event in fx.journal() if event.get("kind") == "attempt"]
        self.assertEqual([(a["class"], a["phase"]) for a in attempts], [("scope", "contain")])
        self.assertIn("pkg/blocked.txt", attempts[0]["detail"])
        self.assertIn("pkg/vault/new.txt", attempts[0]["detail"])
        self.assertNotIn("pkg/greet.py", attempts[0]["detail"])
        second_pack = (fx.scenario / "maker-1.pack.md").read_text(encoding="utf-8")
        self.assertIn("tree restored; stay inside scope_paths", second_pack)
        self.assertIn("pkg/blocked.txt", second_pack)

        # Nothing forbidden reached the working tree, the unit branch or main.
        self.assertEqual((fx.repo / "pkg/blocked.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((fx.repo / "pkg/vault/new.txt").exists())
        for ref in ("main", "tl/B001/T001"):
            self.assertEqual(git(fx.repo, "show", f"{ref}:pkg/blocked.txt"), "keep")
            self.assertNotIn("pkg/vault/new.txt", git(fx.repo, "ls-tree", "-r", "--name-only", ref))
            self.assertIn("pkg/greet.py", git(fx.repo, "ls-tree", "-r", "--name-only", ref))
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")

    def test_dot_prefixed_forbidden_path_under_a_repository_wide_scope_is_contained(self) -> None:
        """scope_paths is the whole repository and the Story forbids .github/workflows and .env.

        The prohibition is judged by the matcher that proved the derivation. The legacy
        `path_within` drops the leading dot of a top-level path, so on its own the unit's
        `do_not_touch` list would let exactly these two through."""
        self.assertFalse(tl_runtime.path_within(".github/workflows/ci.yml", [".github/workflows"]))
        self.assertEqual(story.paths_denied([".github/workflows/ci.yml", ".env", "pkg/a.py", ".envrc"],
                                            [".github/workflows", ".env"]),
                         [".github/workflows/ci.yml", ".env"])

        wide = SPEC_A.replace("scope_paths: [pkg/]", "scope_paths: [.]")
        self.assertNotEqual(wide, SPEC_A)
        fx = self.auto_story_fixture(scope=(".",), forbidden=("secrets", ".github/workflows", ".env"),
                                     spec_text=wide)
        greet = {"pkg/greet.py": "def greet():\n    return 'hi'\n"}
        fx.script("maker", [{"files": dict(greet, **{".github/workflows/ci.yml": "on: push\n", ".env": "MODE=x\n"})},
                            {"files": greet}])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "done", fx.state_dir)

        attempts = [event for event in fx.journal() if event.get("kind") == "attempt"]
        self.assertEqual([a["class"] for a in attempts], ["scope"])
        self.assertIn(".github/workflows/ci.yml", attempts[0]["detail"])
        self.assertIn(".env", attempts[0]["detail"])
        policy_line = next(line for line in (fx.scenario / "maker-0.pack.md").read_text(encoding="utf-8").splitlines()
                           if line.startswith("do_not_touch:"))
        self.assertIn(".github/workflows", policy_line)
        self.assertIn(".env", policy_line)
        tracked = git(fx.repo, "ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertIn("pkg/greet.py", tracked)
        self.assertNotIn(".github/workflows/ci.yml", tracked)
        self.assertNotIn(".env", tracked)
        self.assertFalse((fx.repo / ".github").exists())
        self.assertFalse((fx.repo / ".env").exists())

    def test_renaming_or_deleting_a_forbidden_descendant_is_contained_and_never_checkpointed(self) -> None:
        fx = self.auto_story_fixture(forbidden=self.FORBIDDEN, seed_files=self.FORBIDDEN_SEED, max_rework=3)
        fx.script("maker", [
            {"files": {"pkg/greet.py": "x = 1\n"}, "argv": ["git", "mv", "pkg/blocked.txt", "pkg/allowed.txt"]},
            {"files": {"pkg/greet.py": "x = 2\n"}, "delete": ["pkg/vault/key.txt"]},
        ])
        fx.script("checker", CHECKER_OK)
        self.assertEqual(fx.runtime().run(), "blocked")
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "parked")
        self.assertIn("scope_expansion", record.reason)
        details = [event["detail"] for event in fx.journal() if event.get("kind") == "attempt"]
        self.assertIn("pkg/blocked.txt", details[0])  # the source side of the rename counts
        self.assertIn("pkg/vault/key.txt", details[1])

        self.assertEqual((fx.repo / "pkg/blocked.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertEqual((fx.repo / "pkg/vault/key.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((fx.repo / "pkg/allowed.txt").exists())
        self.assertEqual(git(fx.repo, "status", "--porcelain"), "")
        # No Checker ever saw these rounds, so no functional checkpoint carries them forward.
        self.assertFalse((fx.scenario / "checker.count").exists())
        refs = git(fx.repo, "for-each-ref", "--format=%(refname)", "refs/tl/functional-checkpoints")
        self.assertEqual(refs, "")
        authority = self.authority(fx)
        authority.state = authority.journal.fold()
        self.assertIsNone(authority.state.closure_of("B001"))
        self.assertIsNotNone(authority.state.children["B001"].get("failure"))

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
