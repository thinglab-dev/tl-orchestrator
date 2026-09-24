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
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
for _p in (_TESTS_DIR, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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
                           limits: dict | None = None, seed: dict | None = None, protected_paths=None,
                           root: Path | None = None) -> Fixture:
        """`seed` files are committed with the frozen authority; `protected_paths` is a list, or a
        callable given the repository that returns one (so hashes and snapshots see the seed)."""
        fx = Fixture(root or self.root, units=1, max_calls=max_calls, max_rework=max_rework, limits=limits)
        for relative, content in (seed or {}).items():
            (fx.repo / relative).parent.mkdir(parents=True, exist_ok=True)
            (fx.repo / relative).write_text(content, encoding="utf-8")
        protected = protected_paths(fx.repo) if callable(protected_paths) else list(protected_paths or [])
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
            protected_paths=protected, global_model_call_budget=budget, max_child_batches=2,
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

    def test_auto_story_refuses_tampered_child_and_proof_digests(self) -> None:
        fx = self.auto_story_fixture()
        original = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        for field in ("child_proposal_digest", "derivation_proof_digest"):
            with self.subTest(field=field):
                batch = json.loads(json.dumps(original))
                batch["authorization"][field] = "f" * 64
                fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
                with self.assertRaises(tl_runtime.Refusal) as raised:
                    fx.runtime().acquire()
                self.assertIn("authority_missing_or_ambiguous", str(raised.exception))
        fx.batch_path.write_text(json.dumps(original), encoding="utf-8")

    def test_auto_story_refuses_unregistered_child_batch(self) -> None:
        fx = self.auto_story_fixture()
        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["id"] = "B999"
        fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime().acquire()
        self.assertIn("never derived child batch B999", str(raised.exception))

    def test_auto_story_refuses_effect_expansion_against_child_proposal(self) -> None:
        fx = self.auto_story_fixture()
        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["authorization"]["permitted_effects"]["push"] = True
        fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime().acquire()
        self.assertIn("effect_expansion", str(raised.exception))

    def test_auto_story_enforces_nested_forbidden_path_in_runtime_containment(self) -> None:
        # The task owns the broad pkg scope. Make a narrower descendant forbidden only in
        # Story Authority; this is the case pre-bind scope checks alone cannot protect.
        forbidden = "pkg/blocked.txt"
        fx = Fixture(self.root, units=1, max_calls=8, max_rework=2)
        spec_sha = hashlib.sha256(SPEC_A.encode()).hexdigest()
        payload = story.build_authority_payload(
            authority_id="A001", work_ref="T001", authorized_spec_revision=spec_sha[:16],
            authorized_spec_sha256=spec_sha,
            authorized_write_scope={"required_mutation_targets": ["pkg"],
                                    "conditional_mutation_targets": [],
                                    "forbidden_paths": [forbidden]},
            allowed_effects={"local_write": True, "local_commit": True, "local_merge": True,
                             "pull_request": False, "push": False, "tag": False, "release": False,
                             "merge": False},
            protected_paths=[], global_model_call_budget=8, max_child_batches=2,
            max_consecutive_failed_batches=2, wall_clock_deadline="2027-01-01T00:00:00Z",
            hard_stops=["scope_expansion", "model_call_budget_exhausted", "state_integrity"])
        envelope = story.freeze_authority(
            payload, authorized_literal=story.authorization_literal("T001", story.root_authority_digest(payload)),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        story.publish_authority(fx.repo, envelope)
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "freeze nested forbidden authority")
        with story.StoryAuthority.open_for(fx.repo, "A001") as auth:
            proposal = story.derive_child_proposal(
                authority=auth, child_batch_id="B001", action_items=[], previous_child_id=None,
                model_call_budget=8, governance_base_commit=git(fx.repo, "rev-parse", "HEAD"),
                story_baseline_commit=git(fx.repo, "rev-parse", "HEAD"))
            proof = story.verify_derivation(auth, proposal)
            auth.record_child_derived(proposal, proof)
        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        runtime = fx.runtime()
        runtime.acquire()
        try:
            unit = runtime.units["T001"]
            self.assertIn(forbidden, unit.do_not_touch)
            klass, detail = runtime.policy.check_containment(unit, [forbidden], "")
            self.assertEqual(klass, "scope")
            self.assertIn("scope_expansion", detail)
            self.assertIn(forbidden, detail)
        finally:
            runtime.release()

    def test_auto_story_refuses_batch_budget_above_child_allocation(self) -> None:
        fx = self.auto_story_fixture(budget=4, max_calls=4)
        batch = json.loads(fx.batch_path.read_text(encoding="utf-8"))
        batch["budget"]["max_model_calls"] = 5
        fx.batch_path.write_text(json.dumps(batch), encoding="utf-8")
        with self.assertRaises(tl_runtime.Refusal) as raised:
            fx.runtime().acquire()
        self.assertIn("model_call_budget_exhausted", str(raised.exception))

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
                story_baseline_commit=reopened.load_child_derivation("B001")[0]["lineage"]["story_baseline_commit"])
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

        # R9: the terminal child is never rebound, so the re-run is refused before any work.
        with self.assertRaises(tl_runtime.Refusal) as refused:
            fx.runtime().run()
        self.assertIn("state_integrity", str(refused.exception))
        self.assertIn("never reopened or rebound", str(refused.exception))
        authority.state = authority.journal.fold()
        self.assertEqual(authority.state.consecutive_failures, streak)
        terminal = [e for e in authority.journal.read()[0] if e["kind"] in {"child_closed", "child_failed"}]
        self.assertEqual(len(terminal), 1)

    # ---- R13: protected paths inside the AUTO_STORY lifecycle -----------------------------

    FROZEN = {"pkg/frozen/a.txt": "frozen content\n"}
    GREET = {"pkg/greet.py": "def greet():\n    return 'hi'\n"}
    # policy -> (the change that violates it, the violation it must produce)
    TAMPERING = {
        "read_only": ({"pkg/frozen/a.txt": "rewritten\n"}, "protected_read_only_mutated"),
        "exact_file_hash": ({"pkg/frozen/a.txt": "rewritten\n"}, "protected_file_hash_mismatch"),
        "exact_set_snapshot": ({"pkg/frozen/b.txt": "slipped in\n"}, "protected_set_entry_added"),
    }

    @staticmethod
    def protected(policy: str):
        if policy == "read_only":
            return lambda repo: [{"pattern": "pkg/frozen", "policy": "read_only"}]
        if policy == "exact_file_hash":
            return lambda repo: [{"pattern": "pkg/frozen/a.txt", "policy": "exact_file_hash",
                                  "sha256": story.sha256_hex((repo / "pkg/frozen/a.txt").read_bytes())}]
        return lambda repo: [{"pattern": "pkg/frozen", "policy": "exact_set_snapshot",
                              "snapshot": story.snapshot_set(repo, "pkg/frozen")}]

    def protected_fixture(self, policy: str) -> Fixture:
        root = self.root / policy
        root.mkdir()
        return self.auto_story_fixture(seed=self.FROZEN, protected_paths=self.protected(policy), root=root)

    def batch_steps(self, fx: Fixture) -> list[tuple[str, str]]:
        path = fx.state_dir / "journal.jsonl"
        if not path.is_file():
            return []
        return [(e.get("effect_class", ""), (e.get("intent") or {}).get("type", ""))
                for e in fx.journal() if e.get("kind") == "step_intent"]

    def test_maker_violating_each_protected_policy_stops_before_gates_review_and_commit(self) -> None:
        for policy, (tamper, violation) in self.TAMPERING.items():
            with self.subTest(policy):
                fx = self.protected_fixture(policy)
                fx.script("maker", [{"files": {**self.GREET, **tamper}}])
                fx.script("checker", CHECKER_OK)
                commits_before = git(fx.repo, "rev-list", "--all", "--count")

                self.assertEqual(fx.runtime().run(), "stopped")
                fold = fx.fold()
                self.assertEqual(fold.stop_reason, "protected_path_violation")
                self.assertEqual(fold.model_calls_done, 1, "only the Maker ran; no Checker was dispatched")
                steps = self.batch_steps(fx)
                self.assertIn(("model_call", "maker"), steps)
                for forbidden in ("gate", "checker", "commit"):
                    self.assertNotIn(forbidden, {kind for _effect, kind in steps}, f"{policy}: {forbidden} ran")
                self.assertEqual(git(fx.repo, "rev-list", "--all", "--count"), commits_before, "nothing was committed")

                authority = self.authority(fx)
                authority.refold()
                self.assertEqual(authority.state.child_state("B001"), "failed")
                self.assertEqual(authority.state.children["B001"]["failure"]["reason"], "protected_path_violation")
                stop = authority.state.hard_stops[-1]
                self.assertEqual(stop["reason"], "protected_path_violation")
                self.assertIn("after the Maker of T001 round 1", stop["detail"])
                self.assertIn(violation, [v["violation"] for v in stop["evidence"]["violations"]])
                self.assertEqual(authority.state.consumed_calls, 1)

                # The failed child is terminal: running it again binds nothing and dispatches nothing.
                with self.assertRaises(tl_runtime.Refusal):
                    fx.runtime().run()
                self.assertEqual(fx.fold().model_calls_done, 1)

    def test_protected_paths_are_verified_before_the_child_opens(self) -> None:
        """A change committed after the Story baseline leaves HEAD clean, and is still a violation."""
        for policy, (tamper, violation) in self.TAMPERING.items():
            with self.subTest(policy):
                fx = self.protected_fixture(policy)
                fx.script("maker", MAKER_OK)
                fx.script("checker", CHECKER_OK)
                for relative, content in tamper.items():
                    (fx.repo / relative).write_text(content, encoding="utf-8")
                git(fx.repo, "add", "-A")
                git(fx.repo, "commit", "-q", "-m", "change a protected path after the Story baseline")
                self.assertEqual(git(fx.repo, "status", "--porcelain"), "")

                with self.assertRaises(tl_runtime.Refusal) as refused:
                    fx.runtime().run()
                self.assertIn("protected_path_violation", str(refused.exception))
                self.assertIn("before child_open", str(refused.exception))
                self.assertIn(violation, str(refused.exception))

                authority = self.authority(fx)
                authority.refold()
                self.assertEqual(authority.state.child_state("B001"), "derived", "the child never opened")
                kinds = [e["kind"] for e in authority.journal.read()[0]]
                self.assertNotIn("child_open", kinds)
                self.assertNotIn("model_call_reserved", kinds)
                self.assertEqual(authority.state.hard_stops[-1]["reason"], "protected_path_violation")
                self.assertEqual(self.batch_steps(fx), [])

    def test_intact_protected_paths_let_the_child_complete(self) -> None:
        for policy in self.TAMPERING:
            with self.subTest(policy):
                fx = self.protected_fixture(policy)
                fx.script("maker", [{"files": self.GREET}])
                fx.script("checker", CHECKER_OK)
                self.assertEqual(fx.runtime().run(), "done")
                authority = self.authority(fx)
                authority.refold()
                self.assertEqual(authority.state.child_state("B001"), "closed")
                self.assertEqual(authority.state.hard_stops, [])

    # ---- R11: a forged child lifecycle is refused at bind ---------------------------------

    def test_forged_child_lifecycle_refuses_bind_without_any_event_or_dispatch(self) -> None:
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        forger = self.authority(fx)
        forger.journal.fold()  # position the writer at the tail so the hash chain stays intact
        forger.journal.append(
            "child_closed", authority_id="A001", child_batch_id="B001", checker_verdict="approved",
            unresolved_action_items=[], unresolved_action_items_digest="", made_progress=True)
        self.assertEqual(forger.journal.fold().invalid_lines, 0)
        before = forger.journal.path.read_bytes()

        with self.assertRaises(tl_runtime.Refusal) as refused:
            fx.runtime().run()
        self.assertIn("state_integrity", str(refused.exception))
        self.assertIn("new -> derived -> open -> closed|failed", str(refused.exception))
        self.assertEqual(forger.journal.path.read_bytes(), before, "nothing was appended")
        self.assertEqual(self.batch_steps(fx), [], "nothing was dispatched")

    # ---- R14: a rewritten journal tail is refused at bind -----------------------------------

    def test_tampered_authority_tail_refuses_bind_without_any_event_or_dispatch(self) -> None:
        fx = self.auto_story_fixture()
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)
        authority = self.authority(fx)
        lines = authority.journal.path.read_text(encoding="utf-8").splitlines()
        tail = json.loads(lines[-1])
        self.assertEqual(tail["kind"], "child_derived")
        tail["granted_model_calls"] = 80  # its `prev` is kept, so the in-file chain cannot see it
        lines[-1] = story.canonical_json(tail)
        authority.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(authority.journal.fold().invalid_lines, 0)
        ref = story.journal_anchor_ref("A001")
        anchored = git(fx.repo, "rev-parse", ref)
        before = authority.journal.path.read_bytes()

        with self.assertRaises(tl_runtime.Refusal) as refused:
            fx.runtime().run()
        self.assertIn("state_integrity", str(refused.exception))
        self.assertIn(story.ANCHOR_DIVERGENT, str(refused.exception))
        self.assertEqual(authority.journal.path.read_bytes(), before, "nothing was appended")
        self.assertEqual(git(fx.repo, "rev-parse", ref), anchored, "the anchor did not move")
        self.assertEqual(self.batch_steps(fx), [], "nothing was dispatched")

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

    # ---- §6 counterproofs against persisted self-digested expansion ----------------------

    def test_auto_story_refuses_persisted_self_digested_proposal_with_expanded_effect(self) -> None:
        """A persisted proposal with expanded effects (even self-digested) must HARD STOP before child_open."""
        fx = Fixture(self.root, units=1)
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
            protected_paths=[], global_model_call_budget=8, max_child_batches=2,
            max_consecutive_failed_batches=2, wall_clock_deadline="2027-01-01T00:00:00Z",
            hard_stops=["scope_expansion", "model_call_budget_exhausted", "state_integrity"])
        envelope = story.freeze_authority(
            payload,
            authorized_literal=story.authorization_literal("T001", story.root_authority_digest(payload)),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        story.publish_authority(fx.repo, envelope)
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "freeze story authority A001")

        auth = story.StoryAuthority(envelope, fx.repo / story.RUNTIME_AUTHORITY_DIR / "A001", repo=fx.repo)
        head = git(fx.repo, "rev-parse", "HEAD")
        # Craft a proposal with expanded effects ("push": True, denied by root envelope)
        proposal = {
            "schema_version": 1,
            "authority_id": "A001",
            "child_batch_id": "B001",
            "parent_child_batch_id": None,
            "work_ref": "T001",
            "authorized_spec_revision": spec_sha[:16],
            "authorized_spec_sha256": spec_sha,
            "required_mutation_targets": ["pkg"],
            "conditional_mutation_targets": [],
            "forbidden_paths": ["secrets"],
            "protected_paths": [],
            "allowed_effects": {
                "local_write": True, "local_commit": True, "local_merge": True,
                "pull_request": False, "push": True, "tag": False, "release": False,
                "merge": False,
            },
            "model_call_budget": 4,
            "functional_parent_checkpoint": None,
            "derived_from_action_items": [],
            "lineage": {"governance_base_commit": head, "story_baseline_commit": head},
        }
        proposal_digest = story.digest_of(proposal)
        proof = {
            "schema_version": 1,
            "authority_id": "A001",
            "work_ref": "T001",
            "child_batch_id": "B001",
            "parent_child_batch_id": None,
            "root_authority_digest": envelope["root_authority_digest"],
            "parent_authority_digest": envelope["root_authority_digest"],
            "parent_batch_digest": "",
            "child_proposal_digest": proposal_digest,
            "functional_parent_checkpoint": None,
            "unresolved_action_items_digest": "",
            "granted_model_calls": 4,
            "checks": [{"check": "effects_subset", "result": "pass"}],
        }
        proof["derivation_proof_digest"] = story.digest_of(proof)

        # Directly persist the self-digested proposal/proof on disk and in journal
        (auth.runtime_dir / "proposals").mkdir(parents=True, exist_ok=True)
        auth.child_proposal_path("B001").write_text(json.dumps(proposal), encoding="utf-8")
        auth.child_proof_path("B001").write_text(json.dumps(proof), encoding="utf-8")
        auth.journal.append(
            "child_derived", authority_id="A001", child_batch_id="B001",
            parent_child_batch_id=None,
            root_authority_digest=proof["root_authority_digest"],
            parent_authority_digest=proof["parent_authority_digest"],
            parent_batch_digest="",
            child_proposal_digest=proposal_digest,
            derivation_proof_digest=proof["derivation_proof_digest"],
            granted_model_calls=4,
            functional_parent_checkpoint=None,
            unresolved_action_items_digest="")

        fx.batch["batch_id"] = "B001"
        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY",
            "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proposal_digest,
            "derivation_proof_digest": proof["derivation_proof_digest"],
            "permitted_effects": {
                "local_write": True, "local_commit": True, "local_merge": True,
                "pull_request": False, "push": True, "tag": False, "release": False,
            },
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")

        # Verify that record_child_derived under lease also refuses this proposal
        with auth:
            with self.assertRaises(story.HardStop) as rec_ctx:
                auth.record_child_derived(proposal, proof)
            self.assertEqual(rec_ctx.exception.reason, "effect_expansion")

        # Runtime must HARD STOP (surfaced as Refusal caused by HardStop) before child_open or worker execution
        runtime = fx.runtime()
        with self.assertRaises(tl_runtime.Refusal) as raised:
            runtime.acquire()
        self.assertIn("effect_expansion", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, story.HardStop)
        self.assertEqual(raised.exception.__cause__.reason, "effect_expansion")

        # Verify child_open was NEVER recorded
        auth.refold()
        child_state = (auth.state.children.get("B001") or {}).get("state")
        self.assertNotEqual(child_state, "open")
        events = [e["kind"] for e in auth.journal.read()[0]]
        self.assertNotIn("child_open", events)

    def test_auto_story_refuses_persisted_self_digested_proposal_with_expanded_scope(self) -> None:
        """A persisted proposal with expanded scope (even self-digested) must HARD STOP before child_open."""
        fx = Fixture(self.root, units=1)
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
            protected_paths=[], global_model_call_budget=8, max_child_batches=2,
            max_consecutive_failed_batches=2, wall_clock_deadline="2027-01-01T00:00:00Z",
            hard_stops=["scope_expansion", "model_call_budget_exhausted", "state_integrity"])
        envelope = story.freeze_authority(
            payload,
            authorized_literal=story.authorization_literal("T001", story.root_authority_digest(payload)),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        story.publish_authority(fx.repo, envelope)
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "freeze story authority A001")

        auth = story.StoryAuthority(envelope, fx.repo / story.RUNTIME_AUTHORITY_DIR / "A001", repo=fx.repo)
        head = git(fx.repo, "rev-parse", "HEAD")
        # Craft a proposal with expanded scope (targeting outside root scope)
        proposal = {
            "schema_version": 1,
            "authority_id": "A001",
            "child_batch_id": "B001",
            "parent_child_batch_id": None,
            "work_ref": "T001",
            "authorized_spec_revision": spec_sha[:16],
            "authorized_spec_sha256": spec_sha,
            "required_mutation_targets": ["pkg", "unauthorized_dir/malicious.py"],
            "conditional_mutation_targets": [],
            "forbidden_paths": ["secrets"],
            "protected_paths": [],
            "allowed_effects": {
                "local_write": True, "local_commit": True, "local_merge": True,
                "pull_request": False, "push": False, "tag": False, "release": False,
                "merge": False,
            },
            "model_call_budget": 4,
            "functional_parent_checkpoint": None,
            "derived_from_action_items": [],
            "lineage": {"governance_base_commit": head, "story_baseline_commit": head},
        }
        proposal_digest = story.digest_of(proposal)
        proof = {
            "schema_version": 1,
            "authority_id": "A001",
            "work_ref": "T001",
            "child_batch_id": "B001",
            "parent_child_batch_id": None,
            "root_authority_digest": envelope["root_authority_digest"],
            "parent_authority_digest": envelope["root_authority_digest"],
            "parent_batch_digest": "",
            "child_proposal_digest": proposal_digest,
            "functional_parent_checkpoint": None,
            "unresolved_action_items_digest": "",
            "granted_model_calls": 4,
            "checks": [{"check": "scope_subset", "result": "pass"}],
        }
        proof["derivation_proof_digest"] = story.digest_of(proof)

        # Directly persist the self-digested proposal/proof on disk and in journal
        (auth.runtime_dir / "proposals").mkdir(parents=True, exist_ok=True)
        auth.child_proposal_path("B001").write_text(json.dumps(proposal), encoding="utf-8")
        auth.child_proof_path("B001").write_text(json.dumps(proof), encoding="utf-8")
        auth.journal.append(
            "child_derived", authority_id="A001", child_batch_id="B001",
            parent_child_batch_id=None,
            root_authority_digest=proof["root_authority_digest"],
            parent_authority_digest=proof["parent_authority_digest"],
            parent_batch_digest="",
            child_proposal_digest=proposal_digest,
            derivation_proof_digest=proof["derivation_proof_digest"],
            granted_model_calls=4,
            functional_parent_checkpoint=None,
            unresolved_action_items_digest="")

        fx.batch["batch_id"] = "B001"
        fx.batch["units"] = [{"id": "T001", "scope_paths": ["pkg", "unauthorized_dir/malicious.py"]}]
        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY",
            "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proposal_digest,
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")

        # Verify that record_child_derived under lease also refuses this proposal
        with auth:
            with self.assertRaises(story.HardStop) as rec_ctx:
                auth.record_child_derived(proposal, proof)
            self.assertEqual(rec_ctx.exception.reason, "scope_expansion")

        # Runtime must HARD STOP (surfaced as Refusal caused by HardStop) before child_open or worker execution
        runtime = fx.runtime()
        with self.assertRaises(tl_runtime.Refusal) as raised:
            runtime.acquire()
        self.assertIn("scope_expansion", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, story.HardStop)
        self.assertEqual(raised.exception.__cause__.reason, "scope_expansion")

        # Verify child_open was NEVER recorded
        auth.refold()
        child_state = (auth.state.children.get("B001") or {}).get("state")
        self.assertNotEqual(child_state, "open")
        events = [e["kind"] for e in auth.journal.read()[0]]
        self.assertNotIn("child_open", events)





    def test_auto_story_two_child_cumulative_review(self) -> None:
        # A) Two-child + cumulative review
        fx = self.auto_story_fixture(budget=8, max_rework=0, max_calls=8, limits={"stagnation_rounds": 6})

        # Maker scripts: B001 cria pkg/A.txt; B002 cria pkg/B.txt
        fx.script("maker", [
            {"files": {"pkg/A.txt": "Hello A"}},
            {"files": {"pkg/B.txt": "Hello B"}}
        ])

        # Checker: primeiro changes_requested com patch_item válido em pkg/B.txt:1; segundo approved.
        patch_item_b = {
            "id": "R1", "severity": "medium", "category": "patch", "target_role": "maker",
            "location": "pkg/B.txt:1", "problem": "need B", "evidence": "no B", "required_action": "make B"
        }
        fx.script("checker", [
            {"verdict": "changes_requested", "action_items": [patch_item_b]},
            {"verdict": "approved", "action_items": []}
        ])

        rt = fx.runtime()
        result = rt.run_story()
        self.assertEqual(result, "done")
        self.assertEqual(rt.story_runtime.batch_id, "B002")

        auth = self.authority(fx)
        auth.refold()
        self.assertEqual(auth.state.child_state("B001"), "closed")
        self.assertEqual(auth.state.closure_of("B001")["checker_verdict"], "changes_requested")
        self.assertEqual(auth.state.child_state("B002"), "closed")
        self.assertEqual(auth.state.closure_of("B002")["checker_verdict"], "approved")
        self.assertEqual(auth.state.close_state, "done")

        # O pack REAL do Checker de B002 está em rt.story_runtime.state_dir / packs.
        # O pack final contém pkg/A.txt E pkg/B.txt e diff --git para ambos.

        # Find the checker pack for B002
        packs_dir = rt.story_runtime.state_dir / "packs"
        checker_packs = list(packs_dir.glob("*checker*.md"))
        self.assertTrue(len(checker_packs) >= 1)
        # Use the last checker pack
        checker_packs.sort()
        pack_content = checker_packs[-1].read_text(encoding="utf-8")

        self.assertIn("pkg/A.txt", pack_content)
        self.assertIn("pkg/B.txt", pack_content)
        self.assertIn("diff --git a/pkg/A.txt b/pkg/A.txt", pack_content)
        self.assertIn("diff --git a/pkg/B.txt b/pkg/B.txt", pack_content)

    def test_auto_story_resume_after_governance_branch(self) -> None:
        # B) Resume após governance branch
        fx = self.auto_story_fixture(budget=8, max_rework=0, max_calls=8, limits={"stagnation_rounds": 6})

        fx.script("maker", [
            {"files": {"pkg/A.txt": "Hello A"}},
            {"files": {"pkg/B.txt": "Hello B"}}
        ])

        patch_item_b = {
            "id": "R1", "severity": "medium", "category": "patch", "target_role": "maker",
            "location": "pkg/B.txt:1", "problem": "need B", "evidence": "no B", "required_action": "make B"
        }
        fx.script("checker", [
            {"verdict": "changes_requested", "action_items": [patch_item_b]},
            {"verdict": "approved", "action_items": []}
        ])

        # Primeira instância runtime.run()
        rt1 = fx.runtime()
        result1 = rt1.run()
        self.assertEqual(result1, "blocked")

        # Deve deixar branch main
        current_branch = git(fx.repo, "branch", "--show-current")
        self.assertEqual(current_branch, "main")

        # e B001 closed changes_requested
        auth = self.authority(fx)
        auth.refold()
        self.assertEqual(auth.state.child_state("B001"), "closed")
        self.assertEqual(auth.state.closure_of("B001")["checker_verdict"], "changes_requested")

        # Nova instância fx.runtime().run_story() retorna done e deriva/executa B002 automaticamente
        rt2 = fx.runtime()
        result2 = rt2.run_story()
        self.assertEqual(result2, "done")

        # Valide B002 closed/approved e authority done
        auth.refold()
        self.assertEqual(auth.state.child_state("B002"), "closed")
        self.assertEqual(auth.state.closure_of("B002")["checker_verdict"], "approved")
        self.assertEqual(auth.state.close_state, "done")

    def test_auto_story_resume_retroceded_governance_refused(self) -> None:
        fx = self.auto_story_fixture(budget=8, max_rework=0, max_calls=8, limits={"stagnation_rounds": 6})

        # Advance governance (G)
        Path(fx.repo, "pkg", "G.txt").write_text("G", encoding="utf-8")
        git(fx.repo, "add", "pkg/G.txt")
        git(fx.repo, "commit", "-m", "advance governance to G")
        g_commit = git(fx.repo, "rev-parse", "HEAD")

        # Propose and bind child based on G
        auth = self.authority(fx)
        auth.refold()
        proposal = story.derive_child_proposal(
            auth, "B001", [], None, 8, g_commit, g_commit)
        proof = story.verify_derivation(auth, proposal)
        with StoryAuthority.open_for(fx.repo, "A001") as w_auth:
            w_auth.record_child_derived(proposal, proof)
            w_auth.record_child_opened("B001", proof, g_commit, {})

        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": auth.payload["root_authority_digest"],
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")

        rt = fx.runtime()
        rt.acquire()
        rt.journal.append("unit_state", unit="U1", state="running", reason="", data={"phase": "implement", "base_commit": g_commit, "commit": g_commit})
        rt.release()

        # Now reset base_branch to an ancestor of G
        git(fx.repo, "reset", "--hard", "HEAD~1")

        rt2 = fx.runtime()
        with self.assertRaises(tl_runtime.StopBatch) as ctx:
            rt2.acquire()
        self.assertIn("resuming would continue a history this child never journaled", str(ctx.exception))

    def test_auto_story_crash_between_batch_state_terminal_and_child_closed(self) -> None:
        # C) Crash entre batch_state terminal e child_closed
        fx = self.auto_story_fixture(budget=8, max_rework=0, max_calls=8, limits={"stagnation_rounds": 6})

        fx.script("maker", [{"files": {"pkg/A.txt": "Hello A"}}, {"files": {"pkg/B.txt": "Hello B"}}])
        patch_item_b = {
            "id": "R1", "severity": "medium", "category": "patch", "target_role": "maker",
            "location": "pkg/B.txt:1", "problem": "need", "evidence": "no", "required_action": "do"
        }
        fx.script("checker", [
            {"verdict": "changes_requested", "action_items": [patch_item_b]},
            {"verdict": "approved", "action_items": []}
        ])

        root = fx.runtime()
        s1 = root.run()
        self.assertEqual(s1, "blocked")

        successor, outcome = root.advance_story(s1)
        self.assertEqual(successor.batch_id, "B002")

        original_close_child = successor._close_child_batch
        crashed = False
        def monkeypatched_close_child(state: str) -> None:
            nonlocal crashed
            if not crashed:
                crashed = True
                raise RuntimeError('simulated crash')
            original_close_child(state)

        successor._close_child_batch = monkeypatched_close_child

        with self.assertRaises(RuntimeError) as raised:
            successor.run()
        self.assertEqual(str(raised.exception), "simulated crash")
        self.assertTrue(crashed)

        # Confirme que batch journal está terminal/closed
        successor.refold()
        self.assertTrue(successor.fold.closed)
        self.assertEqual(successor.fold.batch_state, "done")

        # mas authority child ainda não tem closure terminal correspondente
        auth = self.authority(fx)
        auth.acquire()
        auth.refold()
        self.assertEqual(auth.state.child_state("B002"), "open")
        self.assertIsNone(auth.state.closure_of("B002"))
        auth.release()

        # crie NOVA instância fx.runtime() sem patch e chame run_story()
        rt2 = fx.runtime()
        result = rt2.run_story()
        self.assertEqual(result, "done")

        # advance_story deriva B002 e a Story termina done
        auth.refold()
        self.assertEqual(auth.state.child_state("B001"), "closed")
        self.assertEqual(auth.state.child_state("B002"), "closed")
        self.assertEqual(auth.state.closure_of("B002")["checker_verdict"], "approved")
        self.assertEqual(auth.state.close_state, "done")

if __name__ == "__main__":
    unittest.main()
