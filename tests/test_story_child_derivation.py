#!/usr/bin/env python3
"""B) Spec immutability and patch-only derivation (T032 §2.4, §2.5, §2.6), counterfactuals 5-9."""

from __future__ import annotations

import copy
import json
import unittest

from story_authority_support import StoryCase, make_payload, story

SPEC_PATHS = ("_tl-orc/project/tasks/connector-2-10.md",)


class ChildDerivationTest(StoryCase):

    def base_child(self, auth, **overrides) -> dict:
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=8, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proposal.update(overrides)
        return proposal

    def assert_hard_stop(self, auth, proposal, reason: str, **kwargs) -> story.HardStop:
        before = len(auth.state.derived)
        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, **kwargs)
        self.assertEqual(raised.exception.reason, reason, raised.exception.detail)
        auth.refold()
        self.assertEqual(len(auth.state.derived), before, "a refused derivation must open no child batch")
        self.assertTrue(auth.state.hard_stops, "the refusal must be journaled")
        self.assertEqual(auth.state.hard_stops[-1]["reason"], reason)
        return raised.exception

    def test_child_rejects_spec_hash_mutation(self) -> None:
        """5. The authorized specification is frozen for the whole authority."""
        auth = self.authority()
        self.assert_hard_stop(auth, self.base_child(auth, authorized_spec_sha256="b" * 64),
                              "unexpected_revision_drift")
        auth_two = self.authority(self.frozen_authority(authority_id="A002"))
        self.assert_hard_stop(auth_two, self.base_child(auth_two, authorized_spec_revision="3"),
                              "unexpected_revision_drift")

    def test_child_budget_cannot_reset_or_exceed_parent_remaining(self) -> None:
        """6. The child budget is a sub-allocation of what is left, never a fresh ceiling."""
        auth = self.authority()
        self.assert_hard_stop(auth, self.base_child(auth, model_call_budget=15), "model_call_budget_exhausted")

        # Spend eleven of fourteen, then try to hand the child the original ceiling again.
        for index in range(11):
            story.budgeted_authority_dispatch(
                auth, child_batch_id="B013", logical_call_id=f"B013-call-{index}", role="maker",
                phase="implementation", dispatch=lambda _a: {"state": "completed"})
        self.assertEqual(auth.remaining_global_budget, 3)
        self.assert_hard_stop(auth, self.base_child(auth, model_call_budget=14), "model_call_budget_exhausted")
        self.assert_hard_stop(auth, self.base_child(auth, model_call_budget=4), "model_call_budget_exhausted")
        proof = story.verify_derivation(auth, self.base_child(auth, model_call_budget=3))
        self.assertEqual(proof["granted_model_calls"], 3)

    def test_child_rejects_effect_expansion(self) -> None:
        """7. A child can only ever narrow the effects the operator authorized."""
        effects = dict(make_payload()["allowed_effects"])
        effects.update({"push": False, "merge": False})
        auth = self.authority(self.frozen_authority(allowed_effects=effects))
        self.assertFalse(auth.payload["allowed_effects"]["push"])

        expanded = dict(effects)
        expanded["push"] = True
        stop = self.assert_hard_stop(auth, self.base_child(auth, allowed_effects=expanded), "effect_expansion")
        self.assertIn("push", stop.detail)

        narrowed = dict(effects)
        narrowed["pull_request"] = False
        proof = story.verify_derivation(auth, self.base_child(auth, allowed_effects=narrowed))
        self.assertEqual({check["check"]: check["result"] for check in proof["checks"]}["effects_subset"], "pass")

    def test_non_patch_checker_finding_cannot_auto_derive_child(self) -> None:
        """8. Anything but a strictly patch-only finding returns the Story to the operator."""
        blocking = {
            "bad_spec": self.patch_item("R7", category="bad_spec"),
            "intent_gap": self.patch_item("R7", category="intent_gap"),
            "human": self.patch_item("R7", target_role="human"),
            "scope_expansion": self.patch_item("R7", location="infra/terraform/main.tf:12"),
            "migration": self.patch_item("R7", derivation_blockers=["migration"]),
            "capability_expansion": self.patch_item("R7", derivation_blockers=["capability_expansion"]),
            "new_boundary": self.patch_item("R7", derivation_blockers=["new_boundary"]),
            "security": self.patch_item("R7", derivation_blockers=["security"]),
        }
        for index, (reason, item) in enumerate(blocking.items()):
            authority_id = f"A1{index:02d}"
            auth = self.authority(self.frozen_authority(authority_id=authority_id))
            eligible, blockers = story.derivation_eligibility([item], auth.payload, SPEC_PATHS)
            self.assertFalse(eligible, reason)
            self.assertIn(reason, {blocker["reason"] for blocker in blockers})
            self.assert_hard_stop(auth, self.base_child(auth), reason, action_items=[item], spec_paths=SPEC_PATHS)

        # A finding the runtime cannot place inside the envelope is refused, never assumed inside.
        auth = self.authority(self.frozen_authority(authority_id="A199"))
        unplaceable = self.patch_item("R8", location="see the review thread")
        eligible, blockers = story.derivation_eligibility([unplaceable], auth.payload, SPEC_PATHS)
        self.assertFalse(eligible)
        self.assertIn("scope_expansion", {blocker["reason"] for blocker in blockers})

        # "Not approved" alone never derives a child: an empty residual set is refused too.
        self.assertEqual(story.derivation_eligibility([], auth.payload, SPEC_PATHS)[0], False)

    def test_child_cannot_name_an_unknown_parent_to_skip_lineage(self) -> None:
        auth = self.authority()
        first = self.base_child(auth)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested", unresolved_action_items=[self.patch_item("R5")])
        child = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[], previous_child_id="B999",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        stop = self.assert_hard_stop(auth, child, "state_integrity")
        self.assertIn("B999", stop.detail)
        self.assertIn("never derived", stop.detail)

    def test_parent_conditional_path_can_become_child_required(self) -> None:
        """9. §2.4: the union is what must be contained, so a conditional path may become required."""
        auth = self.authority()
        scope = auth.payload["authorized_write_scope"]
        self.assertIn("tests/test_connector.py", scope["conditional_mutation_targets"])
        self.assertNotIn("tests/test_connector.py", scope["required_mutation_targets"])

        residual = [
            self.patch_item("R5", location="src/connector.py:118"),
            self.patch_item("R6", location="tests/test_connector.py:64"),
        ]
        child = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=residual, previous_child_id=None,
            model_call_budget=6, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        # The factual finding on a conditional path promoted it to required in the child.
        self.assertEqual(child["required_mutation_targets"], ["src/connector.py", "tests/test_connector.py"])
        promoted = set(child["required_mutation_targets"]) - set(scope["required_mutation_targets"])
        self.assertEqual(promoted, {"tests/test_connector.py"})

        proof = story.verify_derivation(auth, child, action_items=residual, spec_paths=SPEC_PATHS)
        self.assertEqual({check["check"]: check["result"] for check in proof["checks"]}["scope_subset"], "pass")

        # The union rule accepts it; a path in neither parent set is still refused.
        outside = copy.deepcopy(child)
        outside["required_mutation_targets"] = ["src/connector.py", "infra/terraform/main.tf"]
        self.assert_hard_stop(auth, outside, "scope_expansion")

    def test_child_cannot_drop_a_forbidden_path_or_target_one(self) -> None:
        """Forbidden paths are monotonically restrictive and never become write targets."""
        auth = self.authority()
        dropped = self.base_child(auth, forbidden_paths=[".github/workflows"])
        self.assert_hard_stop(auth, dropped, "scope_expansion")

        auth_two = self.authority(self.frozen_authority(authority_id="A003"))
        targeting = self.base_child(auth_two)
        targeting["conditional_mutation_targets"] = sorted(set(targeting["conditional_mutation_targets"]) | {"secrets"})
        self.assert_hard_stop(auth_two, targeting, "scope_expansion")

        auth_three = self.authority(self.frozen_authority(authority_id="A004"))
        tightened = self.base_child(auth_three)
        tightened["forbidden_paths"] = sorted(set(tightened["forbidden_paths"]) | {"vendor"})
        proof = story.verify_derivation(auth_three, tightened)
        self.assertEqual({c["check"]: c["result"] for c in proof["checks"]}["forbidden_monotonic"], "pass")


class ReworkLineageTest(StoryCase):
    """R8 and R9: a rework child continues exactly its predecessor's residual findings, and a
    child_batch_id is derived once. Every refusal must leave the journal lineage, the child count
    and the persisted proposal/proof blobs exactly as they were."""

    def setUp(self) -> None:
        super().setUp()
        self.auth = self.authority(self.baseline_authority())
        self.commit, self.tree = self.git.head(), self.git.tree()
        self.first = self.derive("B013", None, [])
        self.first_proof = story.verify_derivation(self.auth, self.first)
        self.auth.record_child_derived(self.first, self.first_proof)

    # ---- helpers ------------------------------------------------------------------------

    def derive(self, child_id: str, parent: str | None, items: list[dict], budget: int = 2) -> dict:
        return story.derive_child_proposal(
            authority=self.auth, child_batch_id=child_id, action_items=items, previous_child_id=parent,
            model_call_budget=budget, governance_base_commit=self.commit, story_baseline_commit=self.commit)

    def close(self, child_id: str, residual: list[dict], verdict: str = "changes_requested") -> None:
        self.auth.record_child_closed(
            child_batch_id=child_id, governance_base_commit=self.commit, checker_reviewed_commit=self.commit,
            checker_reviewed_tree=self.tree, functional_checkpoint_commit=self.commit,
            functional_checkpoint_tree=self.tree, checker_verdict=verdict, unresolved_action_items=residual)

    def forged_proof(self, proposal: dict, *, unresolved_digest: str) -> dict:
        """Everything verify_derivation would write, self-digested, but never produced by it."""
        parent = proposal.get("parent_child_batch_id")
        derivation = (self.auth.state.children.get(parent) or {}).get("derivation") or {}
        proof = {
            "schema_version": 1, "authority_id": self.auth.authority_id,
            "work_ref": self.auth.payload["work_ref"], "child_batch_id": proposal["child_batch_id"],
            "parent_child_batch_id": parent, "root_authority_digest": self.auth.root_digest,
            "parent_authority_digest": derivation.get("derivation_proof_digest") or self.auth.root_digest,
            "parent_batch_digest": derivation.get("child_proposal_digest", ""),
            "child_proposal_digest": story.digest_of(proposal),
            "functional_parent_checkpoint": proposal.get("functional_parent_checkpoint"),
            "unresolved_action_items_digest": unresolved_digest, "spec_paths": list(SPEC_PATHS),
            "granted_model_calls": proposal.get("model_call_budget"), "checks": [],
        }
        proof["derivation_proof_digest"] = story.digest_of(proof)
        return proof

    def snapshot(self) -> dict:
        self.auth.refold()
        events, _invalid = self.auth.journal.read()
        proposals = self.auth.runtime_dir / "proposals"
        return {
            "lineage": [(e["kind"], e["child_batch_id"], e.get("child_proposal_digest"))
                        for e in events if e["kind"].startswith("child_")],
            "children": {cid: child.get("state") for cid, child in self.auth.state.children.items()},
            "derived": len(self.auth.state.derived),
            "blobs": {path.name: path.read_bytes() for path in sorted(proposals.glob("*.json"))},
        }

    def assert_refused(self, call, reason: str, fragment: str = "") -> story.HardStop:
        before = self.snapshot()
        with self.assertRaises(story.HardStop) as raised:
            call()
        self.assertEqual(raised.exception.reason, reason, raised.exception.detail)
        if fragment:
            self.assertIn(fragment, raised.exception.detail)
        self.assertEqual(self.snapshot(), before, "a refused derivation must change no lineage, count or blob")
        self.assertEqual(self.auth.state.hard_stops[-1]["reason"], reason, "the refusal must be journaled")
        return raised.exception

    # ---- R8: residual findings lineage ---------------------------------------------------

    def test_rework_child_refuses_missing_residual_findings(self) -> None:
        residual = [self.patch_item("R5")]
        self.close("B013", residual)
        child = self.derive("B014", "B013", residual)
        closure_digest = story.unresolved_action_items_digest(residual)

        # None: verifying a rework child without the residual findings proves nothing.
        self.assert_refused(lambda: story.verify_derivation(self.auth, child), "state_integrity",
                            "residual_findings_supplied")
        # None in the proposal itself is refused before any child_derived, however it is digested.
        nulled = dict(child, derived_from_action_items=None)
        self.assert_refused(
            lambda: self.auth.record_child_derived(nulled, self.forged_proof(nulled, unresolved_digest=closure_digest)),
            "state_integrity", "schema")
        # An empty declaration against a closure that did leave findings is refused as well.
        emptied = self.derive("B014", "B013", [])
        self.assert_refused(
            lambda: self.auth.record_child_derived(emptied, self.forged_proof(emptied, unresolved_digest=closure_digest)),
            "state_integrity", "declares no residual finding")
        self.assertNotIn("B014", self.auth.state.children)

    def test_rework_child_refuses_a_parent_that_closed_with_no_residual(self) -> None:
        self.close("B013", [])
        child = self.derive("B014", "B013", [])
        # "Not approved" with nothing left is not a reason to open another batch.
        self.assert_refused(lambda: story.verify_derivation(self.auth, child, action_items=[], spec_paths=SPEC_PATHS),
                            "intent_gap")
        # Bypassing verify_derivation with a self-digested proof does not help.
        self.assert_refused(
            lambda: self.auth.record_child_derived(
                child, self.forged_proof(child, unresolved_digest=story.unresolved_action_items_digest([]))),
            "state_integrity", "residual_findings_present")
        self.assertNotIn("B014", self.auth.state.children)

    def test_rework_child_recomputes_patch_only_eligibility_from_the_closure(self) -> None:
        cases = {
            "human": self.patch_item("R5", target_role="human"),
            "bad_spec": self.patch_item("R5", category="bad_spec"),
            # The proposal carries no derivation_blockers; only the closure still knows about them.
            "security": self.patch_item("R5", derivation_blockers=["security"]),
        }
        for index, (reason, item) in enumerate(cases.items()):
            with self.subTest(reason=reason):
                self.auth = self.authority(self.frozen_authority(authority_id=f"A2{index:02d}"))
                first = self.derive("B013", None, [])
                self.auth.record_child_derived(first, story.verify_derivation(self.auth, first))
                self.close("B013", [item])
                closure = self.auth.state.closure_of("B013")
                self.assertEqual(closure["unresolved_action_items"], story.canonical_residual_action_items([item]))

                child = self.derive("B014", "B013", [item])
                self.assert_refused(
                    lambda: story.verify_derivation(self.auth, child, action_items=[item], spec_paths=SPEC_PATHS),
                    reason)
                forged = self.forged_proof(child, unresolved_digest=closure["unresolved_action_items_digest"])
                self.assert_refused(lambda: self.auth.record_child_derived(child, forged), reason,
                                    "patch_only_findings")
                self.assertNotIn("B014", self.auth.state.children)
                self.assertFalse(self.auth.child_proposal_path("B014").exists())

    def test_rework_child_refuses_divergent_residual_digest(self) -> None:
        residual = [self.patch_item("R5"), self.patch_item("R6", location="tests/test_connector.py:64")]
        self.close("B013", residual)
        child = self.derive("B014", "B013", residual)
        other = story.unresolved_action_items_digest([self.patch_item("R9", location="src/connector.py:5")])

        for declared in (other, ""):
            with self.subTest(declared=declared):
                self.assert_refused(
                    lambda: self.auth.record_child_derived(child, self.forged_proof(child, unresolved_digest=declared)),
                    "state_integrity", "proof unresolved_action_items_digest")
        # The proposal may not swap the findings either, even when the proof names the right digest.
        swapped = self.derive("B014", "B013", [self.patch_item("R9", location="src/connector.py:5")])
        self.assert_refused(
            lambda: self.auth.record_child_derived(
                swapped, self.forged_proof(swapped, unresolved_digest=story.unresolved_action_items_digest(residual))),
            "state_integrity", "differ from the ones recorded")
        self.assertNotIn("B014", self.auth.state.children)

        # Control: the honest derivation of the same child is accepted and binds the closure digest.
        proof = story.verify_derivation(self.auth, child, action_items=residual, spec_paths=SPEC_PATHS)
        self.assertEqual({c["check"]: c["result"] for c in proof["checks"]}["residual_lineage"], "pass")
        self.auth.record_child_derived(child, proof)
        self.assertEqual(self.auth.state.children["B014"]["derivation"]["unresolved_action_items_digest"],
                         self.auth.state.closure_of("B013")["unresolved_action_items_digest"])
        loaded, _proof = self.auth.load_child_derivation("B014")
        self.assertEqual(loaded, child)

    # ---- R9: a child_batch_id is derived once -------------------------------------------

    def test_active_child_cannot_be_rederived_or_reopened(self) -> None:
        self.auth.record_child_open("B013", branch="auto-story/A001/B013", head_commit=self.commit, tree=self.tree)
        before = self.snapshot()
        self.assertEqual(before["children"], {"B013": "open"})

        self.assert_refused(lambda: story.verify_derivation(self.auth, self.first), "state_integrity",
                            "child_batch_id_unused")
        self.assert_refused(lambda: self.auth.record_child_derived(self.first, self.first_proof), "state_integrity",
                            "already derived")
        wider = dict(self.first, model_call_budget=6)
        self.assert_refused(
            lambda: self.auth.record_child_derived(wider, self.forged_proof(wider, unresolved_digest="")),
            "state_integrity", "already derived")
        self.assert_refused(
            lambda: self.auth.record_child_open("B013", branch="elsewhere", head_commit=self.commit, tree=self.tree),
            "state_integrity", "cannot open")

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.auth.state.children["B013"]["derivation"]["child_proposal_digest"],
                         self.first_proof["child_proposal_digest"])
        self.assertEqual(self.auth.child_budget_projection("B013")["granted_model_calls"], 2)

    def test_closed_child_cannot_be_rederived_rebound_or_reopened(self) -> None:
        residual = [self.patch_item("R5")]
        self.close("B013", residual)
        second = self.derive("B014", "B013", residual)
        second_proof = story.verify_derivation(self.auth, second, action_items=residual, spec_paths=SPEC_PATHS)
        self.auth.record_child_derived(second, second_proof)
        self.close("B014", residual)
        before = self.snapshot()
        self.assertEqual(before["children"], {"B013": "closed", "B014": "closed"})
        self.assertEqual(before["derived"], 2)

        # Re-deriving either terminal id, with its own proof or through verification, is refused.
        self.assert_refused(lambda: self.auth.record_child_derived(self.first, self.first_proof), "state_integrity",
                            "state closed")
        self.assert_refused(lambda: self.auth.record_child_derived(second, second_proof), "state_integrity",
                            "state closed")
        self.assert_refused(lambda: story.verify_derivation(self.auth, second, action_items=residual,
                                                            spec_paths=SPEC_PATHS),
                            "state_integrity", "child_batch_id_unused")
        # A terminal child is never reopened.
        for child_id in ("B013", "B014"):
            self.assert_refused(
                lambda: self.auth.record_child_open(child_id, branch="again", head_commit=self.commit, tree=self.tree),
                "state_integrity", "cannot open from state closed")
        self.assertEqual(self.snapshot(), before)

        # Reusing an id is not a way around max_child_batches (2): a new id is still exhausted.
        third = self.derive("B015", "B014", residual)
        self.assert_refused(lambda: story.verify_derivation(self.auth, third, action_items=residual,
                                                            spec_paths=SPEC_PATHS),
                            "max_child_batches_exhausted")

    def test_journal_that_replays_a_derivation_or_reopens_a_terminal_child_is_refused(self) -> None:
        self.close("B013", [self.patch_item("R5")])
        closure = self.auth.state.closure_of("B013")
        # Written straight into the journal, past every guard, the replay still cannot take effect.
        self.auth.journal.append("child_derived", authority_id="A001", child_batch_id="B013",
                                 parent_child_batch_id=None, child_proposal_digest="f" * 64,
                                 derivation_proof_digest="f" * 64, granted_model_calls=14)
        self.auth.journal.append("child_open", authority_id="A001", child_batch_id="B013", branch="again",
                                 head_commit=self.commit, tree=self.tree)
        state = self.auth.refold()
        self.assertEqual(state.children["B013"]["state"], "closed")
        self.assertEqual(state.closure_of("B013"), closure)
        self.assertEqual(state.children["B013"]["derivation"]["child_proposal_digest"],
                         self.first_proof["child_proposal_digest"])
        self.assertEqual(len(state.derived), 1)
        self.assertEqual(len(state.integrity_violations), 2)

        self.auth.release()
        reopened = self.authority(self.auth.envelope, acquire=False)
        self.addCleanup(reopened.release)
        with self.assertRaises(story.HardStop) as raised:
            reopened.acquire()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("rewrites child lineage", raised.exception.detail)

    def test_persisted_derivation_artifacts_are_never_overwritten(self) -> None:
        residual = [self.patch_item("R5")]
        self.close("B013", residual)
        child = self.derive("B014", "B013", residual)
        proof = story.verify_derivation(self.auth, child, action_items=residual, spec_paths=SPEC_PATHS)

        # A different proposal already on disk for an id the journal never derived is not replaced.
        foreign = json.dumps(dict(child, model_call_budget=6)).encode()
        self.auth.child_proposal_path("B014").parent.mkdir(parents=True, exist_ok=True)
        self.auth.child_proposal_path("B014").write_bytes(foreign)
        self.assert_refused(lambda: self.auth.record_child_derived(child, proof), "state_integrity",
                            "never overwritten")
        self.assertEqual(self.auth.child_proposal_path("B014").read_bytes(), foreign)

        # The identical objects left by a crash before the journal append let the retry finish.
        self.auth.child_proposal_path("B014").write_text(json.dumps(child), encoding="utf-8")
        self.auth.record_child_derived(child, proof)
        self.assertEqual(self.auth.state.children["B014"]["state"], "derived")


if __name__ == "__main__":
    unittest.main()
