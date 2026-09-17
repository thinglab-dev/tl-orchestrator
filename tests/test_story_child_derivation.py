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


if __name__ == "__main__":
    unittest.main()
