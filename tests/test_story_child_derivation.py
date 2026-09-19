#!/usr/bin/env python3
"""B) Spec immutability and patch-only derivation (T032 §2.4, §2.5, §2.6), counterfactuals 5-9."""

from __future__ import annotations

import copy
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
        residual = [self.patch_item("R5")]
        child = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B999",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        stop = self.assert_hard_stop(auth, child, "state_integrity", action_items=residual)
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

    def test_r8_rework_derivation_requires_valid_patch_findings(self) -> None:
        """R8 counterproof: Deriving child with predecessor requires canonical, non-empty, patch-only findings.

        Refuses action_items=None, empty list, human/bad_spec findings, or forged digest.
        Ensures child_derived and child_open are never recorded in any of these failure cases.
        """
        auth = self.authority(self.frozen_authority(authority_id="A010"))
        first = self.base_child(auth)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested", unresolved_action_items=[self.patch_item("R5")])

        events_before = len(auth.journal.read()[0])
        derived_before = len(auth.state.derived)

        # 1. action_items=None must HARD STOP as state_integrity
        child_none = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[self.patch_item("R5")],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as ctx_none:
            story.verify_derivation(auth, child_none, action_items=None)
        self.assertEqual(ctx_none.exception.reason, "state_integrity")
        self.assertIn("mandatory", ctx_none.exception.detail)

        # 2. action_items=[] (empty list) must HARD STOP as state_integrity
        child_empty = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as ctx_empty:
            story.verify_derivation(auth, child_empty, action_items=[])
        self.assertEqual(ctx_empty.exception.reason, "state_integrity")
        self.assertIn("empty", ctx_empty.detail if hasattr(ctx_empty, "detail") else ctx_empty.exception.detail)

        # 3. action item with target_role='human' must HARD STOP as human
        item_human = self.patch_item("R5", target_role="human")
        child_human = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[item_human],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as ctx_human:
            story.verify_derivation(auth, child_human, action_items=[item_human])
        self.assertEqual(ctx_human.exception.reason, "human")

        # 4. action item with category='bad_spec' must HARD STOP as bad_spec
        item_bad_spec = self.patch_item("R5", category="bad_spec")
        child_bad = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[item_bad_spec],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as ctx_bad:
            story.verify_derivation(auth, child_bad, action_items=[item_bad_spec])
        self.assertEqual(ctx_bad.exception.reason, "bad_spec")

        # 5. proposal claiming different findings than closure must HARD STOP
        item_divergent = self.patch_item("R6", location="src/connector.py:42")
        child_divergent = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[item_divergent],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as ctx_div:
            story.verify_derivation(auth, child_divergent, action_items=[item_divergent])
        self.assertEqual(ctx_div.exception.reason, "state_integrity")
        self.assertIn("differ from the ones recorded", ctx_div.exception.detail)

        # 6. Verify that across all attempts, B014 was NEVER derived and child_open was NEVER recorded
        auth.refold()
        self.assertEqual(len(auth.state.derived), derived_before)
        self.assertNotIn("B014", auth.state.children)
        events = [e["kind"] for e in auth.journal.read()[0]]
        self.assertEqual(len([e for e in events if e == "child_derived"]), 1)
        self.assertNotIn("child_open", events)

    def test_r8_residual_digest_binds_checker_blockers_and_declarations(self) -> None:
        """R8 adversarial: blocker/declaration stripping must change identity and cannot derive."""
        blocked = self.patch_item(
            "R5",
            derivation_blockers=["migration"],
            scope_status="inside_parent_envelope",
            spec_status="unchanged",
        )
        stripped_blocker = {k: v for k, v in blocked.items() if k != "derivation_blockers"}
        stripped_scope = {k: v for k, v in blocked.items() if k != "scope_status"}
        stripped_spec = {k: v for k, v in blocked.items() if k != "spec_status"}

        self.assertNotEqual(
            story.unresolved_action_items_digest([blocked]),
            story.unresolved_action_items_digest([stripped_blocker]),
        )
        self.assertNotEqual(
            story.unresolved_action_items_digest([blocked]),
            story.unresolved_action_items_digest([stripped_scope]),
        )
        self.assertNotEqual(
            story.unresolved_action_items_digest([blocked]),
            story.unresolved_action_items_digest([stripped_spec]),
        )

        auth = self.authority(self.frozen_authority(authority_id="A012"))
        first = self.base_child(auth)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested", unresolved_action_items=[blocked])

        forged = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[stripped_blocker],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as stripped:
            story.verify_derivation(auth, forged, action_items=[stripped_blocker], spec_paths=SPEC_PATHS)
        self.assertEqual(stripped.exception.reason, "state_integrity")
        self.assertIn("recorded when the parent closed", stripped.exception.detail)

        honest = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[blocked],
            previous_child_id="B013", model_call_budget=2,
            governance_base_commit=self.governance_base, story_baseline_commit=self.governance_base)
        carried = honest["derived_from_action_items"][0]
        self.assertEqual(carried["derivation_blockers"], ["migration"])
        self.assertEqual(carried["scope_status"], "inside_parent_envelope")
        self.assertEqual(carried["spec_status"], "unchanged")
        self.assertEqual(carried["problem"], blocked["problem"])
        self.assertEqual(carried["evidence"], blocked["evidence"])
        with self.assertRaises(story.HardStop) as honest_stop:
            story.verify_derivation(auth, honest, action_items=[blocked], spec_paths=SPEC_PATHS)
        self.assertEqual(honest_stop.exception.reason, "migration")

        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        self.assertEqual(
            len([e for e in auth.journal.read()[0] if e["kind"] == "child_derived"]),
            1,
        )

    def test_r9_child_cannot_be_rederived_when_active_or_closed(self) -> None:
        """R9 counterproof: Re-deriving a child ID (whether active or closed) is refused.

        Verifies state machine integrity: disk blobs (proposal/proof), children count, and
        lineage remain strictly immutable upon any rederivation attempt.
        """
        auth = self.authority(self.frozen_authority(authority_id="A011"))
        first = self.base_child(auth)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)

        # Capture initial state and blobs on disk
        auth.refold()
        self.assertEqual(len(auth.state.children), 1)
        self.assertIn("B013", auth.state.children)
        initial_prop_bytes = auth.child_proposal_path("B013").read_bytes()
        initial_proof_bytes = auth.child_proof_path("B013").read_bytes()
        initial_events_count = len(auth.journal.read()[0])

        # Attempt 1: Re-derive while child B013 is active via verify_derivation
        with self.assertRaises(story.HardStop) as ctx_active_ver:
            story.verify_derivation(auth, first)
        self.assertEqual(ctx_active_ver.exception.reason, "state_integrity")
        self.assertIn("already been derived", ctx_active_ver.exception.detail)

        # Attempt 2: Re-derive while child B013 is active via record_child_derived
        tampered_first = copy.deepcopy(first)
        tampered_first["model_call_budget"] = 1  # try to modify
        with self.assertRaises(story.HardStop) as ctx_active_rec:
            auth.record_child_derived(tampered_first, proof)
        self.assertEqual(ctx_active_rec.exception.reason, "state_integrity")

        # Verify blobs and journal are untouched
        self.assertEqual(auth.child_proposal_path("B013").read_bytes(), initial_prop_bytes)
        self.assertEqual(auth.child_proof_path("B013").read_bytes(), initial_proof_bytes)
        auth.refold()
        self.assertEqual(len(auth.state.children), 1)

        # Now close B013
        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested", unresolved_action_items=[self.patch_item("R5")])

        auth.refold()
        self.assertEqual(auth.state.children["B013"]["state"], "closed")
        closed_prop_bytes = auth.child_proposal_path("B013").read_bytes()
        closed_proof_bytes = auth.child_proof_path("B013").read_bytes()

        # Attempt 3: Re-derive closed child B013 via verify_derivation
        with self.assertRaises(story.HardStop) as ctx_closed_ver:
            story.verify_derivation(auth, first)
        self.assertEqual(ctx_closed_ver.exception.reason, "state_integrity")
        self.assertIn("already been derived", ctx_closed_ver.exception.detail)

        # Attempt 4: Re-derive closed child B013 via record_child_derived
        with self.assertRaises(story.HardStop) as ctx_closed_rec:
            auth.record_child_derived(first, proof)
        self.assertEqual(ctx_closed_rec.exception.reason, "state_integrity")

        # Verify disk blobs, child count and closure lineage remain 100% immutable
        self.assertEqual(auth.child_proposal_path("B013").read_bytes(), closed_prop_bytes)
        self.assertEqual(auth.child_proof_path("B013").read_bytes(), closed_proof_bytes)
        auth.refold()
        self.assertEqual(len(auth.state.children), 1)
        self.assertEqual(auth.state.children["B013"]["state"], "closed")
        derived_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_derived"]
        self.assertEqual(len(derived_events), 1)


if __name__ == "__main__":
    unittest.main()
