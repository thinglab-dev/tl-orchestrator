#!/usr/bin/env python3
"""B) Spec immutability and patch-only derivation (T032 §2.4, §2.5, §2.6), counterfactuals 5-9."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
for _p in (_TESTS_DIR, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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

        def spent(authority_id: str) -> story.StoryAuthority:
            # Spend eleven of fourteen, then try to hand the child the original ceiling again. Each
            # attempt gets its own authority: a journaled hard stop is terminal (R18).
            spender = self.authority(self.frozen_authority(authority_id=authority_id))
            for index in range(11):
                story.budgeted_authority_dispatch(
                    spender, child_batch_id="B013", logical_call_id=f"B013-call-{index}", role="maker",
                    phase="implementation", dispatch=lambda _a: {"state": "completed"})
            self.assertEqual(spender.remaining_global_budget, 3)
            return spender

        for authority_id, requested in (("A002", 14), ("A003", 4)):
            spender = spent(authority_id)
            self.assert_hard_stop(spender, self.base_child(spender, model_call_budget=requested),
                                  "model_call_budget_exhausted")
        spender = spent("A004")
        proof = story.verify_derivation(spender, self.base_child(spender, model_call_budget=3))
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
        # The stopped authority stays stopped even for a narrowed child (R18); a fresh one derives it.
        with self.assertRaises(story.HardStop) as terminal:
            story.verify_derivation(auth, self.base_child(auth, allowed_effects=narrowed))
        self.assertIn(story.AUTHORITY_HARD_STOPPED, terminal.exception.detail)
        auth = self.authority(self.frozen_authority(authority_id="A002", allowed_effects=effects))
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

    def test_finding_location_traversal_is_never_inside_parent_envelope(self) -> None:
        auth = self.authority(self.frozen_authority(authority_id="A198"))
        item = self.patch_item("R9", location="src/connector.py/../../secrets/key.txt:1")
        eligible, blockers = story.derivation_eligibility([item], auth.payload, SPEC_PATHS)
        self.assertFalse(eligible)
        self.assertIn("scope_expansion", {blocker["reason"] for blocker in blockers})
        self.assert_hard_stop(
            auth, self.base_child(auth), "scope_expansion",
            action_items=[item], spec_paths=SPEC_PATHS)

    def test_child_cannot_name_an_unknown_parent_to_skip_lineage(self) -> None:
        auth = self.authority()
        first = self.base_child(auth)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        auth.record_child_open("B013", branch="main", head_commit=self.governance_base, tree=self.git.tree())
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

    # ---- Explicit rework counterproofs & R9 rederivation tests (T032 R8/R9) --------

    def _setup_closed_predecessor(self, auth, residual_items=None, child_id="B013") -> None:
        first = self.base_child(auth, child_batch_id=child_id)
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        auth.record_child_open(child_id, branch="main", head_commit=self.governance_base, tree=self.git.tree())
        auth.record_child_closed(
            child_batch_id=child_id, governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested",
            unresolved_action_items=residual_items if residual_items is not None else [self.patch_item("R5")])

    def test_rework_child_rejects_none_action_items_before_child_derived(self) -> None:
        """Rework child with predecessor and action_items=None stops with HardStop before child_derived."""
        auth = self.authority()
        self._setup_closed_predecessor(auth)
        residual = [self.patch_item("R5")]
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, action_items=None, spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("residual_action_items_supplied", raised.exception.detail)

        # Journal / events verification: no child_derived event for B014 was recorded
        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        derived_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_derived" and e.get("child_batch_id") == "B014"]
        self.assertEqual(derived_events, [])

        # Absence of blobs: neither proposal nor proof blob exists for B014
        self.assertFalse(auth.child_proposal_path("B014").exists())
        self.assertFalse(auth.child_proof_path("B014").exists())

    @staticmethod
    def _proof_digest(proof: dict) -> str:
        return story.digest_of({k: v for k, v in proof.items() if k != "derivation_proof_digest"})

    def test_rework_child_rejects_empty_action_items_before_child_derived(self) -> None:
        """Rework child with predecessor and action_items=[] stops with HardStop before child_derived."""
        auth = self.authority()
        self._setup_closed_predecessor(auth)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[], previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, action_items=[], spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "intent_gap")

        # Also verify assert_residual_lineage / record_child_derived rejects empty derived_from_action_items
        dummy_proof = {
            "child_batch_id": "B014",
            "child_proposal_digest": story.digest_of(proposal),
            "unresolved_action_items_digest": story.unresolved_action_items_digest([]),
            "checks": [],
        }
        dummy_proof["derivation_proof_digest"] = self._proof_digest(dummy_proof)
        # On the authority that just hard-stopped, nothing is recorded at all (R18) ...
        with self.assertRaises(story.HardStop) as terminal:
            auth.record_child_derived(proposal, dummy_proof)
        self.assertIn(story.AUTHORITY_HARD_STOPPED, terminal.exception.detail)
        # ... and on one that did not, the empty residual lineage itself is what refuses it.
        other = self.authority(self.frozen_authority(authority_id="A002"))
        self._setup_closed_predecessor(other)
        other_proposal = story.derive_child_proposal(
            authority=other, child_batch_id="B014", action_items=[], previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        other_proof = dict(dummy_proof, child_proposal_digest=story.digest_of(other_proposal))
        other_proof.pop("derivation_proof_digest")
        other_proof["derivation_proof_digest"] = self._proof_digest(other_proof)
        with self.assertRaises(story.HardStop) as raised_rec:
            other.record_child_derived(other_proposal, other_proof)
        self.assertEqual(raised_rec.exception.reason, "state_integrity")
        self.assertNotIn("B014", other.refold().children)

        # Journal / events verification: no child_derived event for B014 was recorded
        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        derived_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_derived" and e.get("child_batch_id") == "B014"]
        self.assertEqual(derived_events, [])

        # Absence of blobs: neither proposal nor proof blob exists for B014
        self.assertFalse(auth.child_proposal_path("B014").exists())
        self.assertFalse(auth.child_proof_path("B014").exists())

    def test_rework_child_rejects_human_target_role_without_child_derived(self) -> None:
        """Rework child with predecessor and target_role=human raises patch-only HardStop without child_derived."""
        auth = self.authority()
        human_item = self.patch_item("R7", target_role="human")
        self._setup_closed_predecessor(auth, residual_items=[human_item])
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[human_item], previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, action_items=[human_item], spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "human")

        # Journal / events verification: no child_derived event for B014 was recorded
        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        derived_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_derived" and e.get("child_batch_id") == "B014"]
        self.assertEqual(derived_events, [])

        # Absence of blobs: neither proposal nor proof blob exists for B014
        self.assertFalse(auth.child_proposal_path("B014").exists())
        self.assertFalse(auth.child_proof_path("B014").exists())

    def test_rework_child_rejects_bad_spec_category_without_child_derived(self) -> None:
        """Rework child with predecessor and category=bad_spec raises patch-only HardStop without child_derived."""
        auth = self.authority()
        bad_spec_item = self.patch_item("R7", category="bad_spec")
        self._setup_closed_predecessor(auth, residual_items=[bad_spec_item])
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=[bad_spec_item], previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, action_items=[bad_spec_item], spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "bad_spec")

        # Journal / events verification: no child_derived event for B014 was recorded
        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        derived_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_derived" and e.get("child_batch_id") == "B014"]
        self.assertEqual(derived_events, [])

        # Absence of blobs: neither proposal nor proof blob exists for B014
        self.assertFalse(auth.child_proposal_path("B014").exists())
        self.assertFalse(auth.child_proof_path("B014").exists())

    def test_rework_child_divergent_proposal_digest_refused_at_persistence(self) -> None:
        """A proposal declaring residual items divergent from predecessor's closure is refused at persistence."""
        auth = self.authority()
        self._setup_closed_predecessor(auth, residual_items=[self.patch_item("R5")])
        forged_residual = [self.patch_item("R6", location="tests/test_connector.py:64")]
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=forged_residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, action_items=forged_residual, spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("differ from the ones recorded", raised.exception.detail)

        auth2 = self.authority(envelope=self.frozen_authority(authority_id="A002"))
        self._setup_closed_predecessor(auth2, residual_items=[self.patch_item("R5")])

        proposal2 = story.derive_child_proposal(
            authority=auth2, child_batch_id="B014", action_items=forged_residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

        dummy_proof = {
            "schema_version": 1,
            "authority_id": "A002",
            "work_ref": proposal2["work_ref"],
            "child_batch_id": "B014",
            "parent_child_batch_id": "B013",
            "root_authority_digest": auth2.envelope["root_authority_digest"],
            "parent_authority_digest": auth2.envelope["root_authority_digest"],
            "parent_batch_digest": "",
            "child_proposal_digest": story.digest_of(proposal2),
            "unresolved_action_items_digest": story.unresolved_action_items_digest(forged_residual),
            "granted_model_calls": 2,
            "functional_parent_checkpoint": proposal2["functional_parent_checkpoint"],
            "checks": [],
        }
        dummy_proof["derivation_proof_digest"] = self._proof_digest(dummy_proof)
        with self.assertRaises(story.HardStop) as raised_rec:
            auth2.record_child_derived(proposal2, dummy_proof)
        self.assertEqual(raised_rec.exception.reason, "state_integrity")
        self.assertIn("residual_lineage", raised_rec.exception.detail)

        auth2.refold()
        self.assertNotIn("B014", auth2.state.children)
        self.assertFalse(auth2.child_proposal_path("B014").exists())
        self.assertFalse(auth2.child_proof_path("B014").exists())
        journal_events = auth2.journal.read()[0]
        self.assertEqual([e for e in journal_events if e.get("child_batch_id") == "B014" and e["kind"] in {"child_derived", "child_open"}], [])

    def test_rework_child_divergent_proof_digest_refused_at_persistence_proposal_digest(self) -> None:
        """A proof declaring forged proposal digest is refused at persistence."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        valid_proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)

        forged_proof_a = copy.deepcopy(valid_proof)
        forged_proof_a["child_proposal_digest"] = "0" * 64
        forged_proof_a["derivation_proof_digest"] = self._proof_digest(forged_proof_a)
        with self.assertRaises(story.HardStop) as raised_a:
            auth.record_child_derived(proposal, forged_proof_a)
        self.assertEqual(raised_a.exception.reason, "state_integrity")
        self.assertIn("was taken over a different child proposal", raised_a.exception.detail)

        auth.refold()
        self.assertNotIn("B014", auth.state.children)
        self.assertFalse(auth.child_proposal_path("B014").exists())
        self.assertFalse(auth.child_proof_path("B014").exists())

    def test_rework_child_divergent_proof_digest_refused_at_persistence_residual_digest(self) -> None:
        """A proof declaring forged residual items digest is refused at persistence."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        valid_proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)

        forged_proof_b = copy.deepcopy(valid_proof)
        forged_proof_b["unresolved_action_items_digest"] = "1" * 64
        forged_proof_b["derivation_proof_digest"] = self._proof_digest(forged_proof_b)
        with self.assertRaises(story.HardStop) as raised_b:
            auth.record_child_derived(proposal, forged_proof_b)
        self.assertEqual(raised_b.exception.reason, "state_integrity")
        self.assertIn("carries unresolved_action_items_digest", raised_b.exception.detail)

        auth.refold()
        self.assertNotIn("B014", auth.state.children)

    def test_rework_child_forged_digest_proposal_refused_before_child_open(self) -> None:
        """Forged proposal digest is refused before child_open."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)
        auth.record_child_derived(proposal, proof)

        # Vector 1: Tamper proposal blob on disk with divergent content (proposal digest divergence)
        tampered_proposal = copy.deepcopy(proposal)
        tampered_proposal["model_call_budget"] = 99
        auth.child_proposal_path("B014").write_text(story.canonical_json(tampered_proposal), encoding="utf-8")

        with self.assertRaises(story.HardStop) as raised_prop:
            auth.load_child_derivation("B014", spec_paths=SPEC_PATHS)
        self.assertEqual(raised_prop.exception.reason, "state_integrity")
        self.assertIn("digests to", raised_prop.exception.detail)

    def test_rework_child_forged_digest_proof_refused_before_child_open(self) -> None:
        """Forged proof digest is refused before child_open."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)
        auth.record_child_derived(proposal, proof)

        # Vector 2: Tamper proof blob on disk (proof digest divergence)
        tampered_proof = copy.deepcopy(proof)
        tampered_proof["unresolved_action_items_digest"] = "e" * 64
        auth.child_proof_path("B014").write_text(story.canonical_json(tampered_proof), encoding="utf-8")

        with self.assertRaises(story.HardStop) as raised_proof:
            auth.load_child_derivation("B014", spec_paths=SPEC_PATHS)
        self.assertEqual(raised_proof.exception.reason, "state_integrity")
        self.assertIn("digests to", raised_proof.exception.detail)

    def test_rework_child_forged_digest_closure_refused_before_child_open(self) -> None:
        """Divergent closure digest is refused before child_open; valid derivation not rewritten."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)
        auth.record_child_derived(proposal, proof)

        auth.refold()
        orig_proposal_bytes = auth.child_proposal_path("B014").read_bytes()
        orig_proof_bytes = auth.child_proof_path("B014").read_bytes()
        valid_derivation_record = copy.deepcopy(auth.state.children["B014"]["derivation"])

        # Vector 3: Closure digest diverges from proof and proposal
        state_closure = auth.state.children["B013"]["closure"]
        orig_closure_digest = state_closure["unresolved_action_items_digest"]
        state_closure["unresolved_action_items_digest"] = "d" * 64
        with self.assertRaises(story.HardStop) as raised_closure:
            story.assert_child_proposal_within_envelope(
                proposal, auth.payload, auth.state, None, proof=proof,
                derivation=valid_derivation_record, spec_paths=SPEC_PATHS)
        self.assertEqual(raised_closure.exception.reason, "state_integrity")
        self.assertIn("residual_lineage:", raised_closure.exception.detail)
        state_closure["unresolved_action_items_digest"] = orig_closure_digest

        # Invariants: no child_open was recorded; valid derivation was not rewritten
        auth.refold()
        self.assertEqual(auth.state.children["B014"]["state"], "derived")
        self.assertEqual(auth.state.children["B014"]["derivation"], valid_derivation_record)
        open_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_open" and e.get("child_batch_id") == "B014"]
        self.assertEqual(open_events, [])

        self.assertEqual(auth.child_proposal_path("B014").read_bytes(), orig_proposal_bytes)
        self.assertEqual(auth.child_proof_path("B014").read_bytes(), orig_proof_bytes)
        recovered_prop, recovered_proof = auth.load_child_derivation("B014", spec_paths=SPEC_PATHS)
        self.assertEqual(story.digest_of(recovered_prop), valid_derivation_record["child_proposal_digest"])

    def test_rework_child_forged_batch_authorization_digest_refused_at_bind(self) -> None:
        """A batch whose authorization declares a forged child_proposal_digest is refused before child_open."""
        import tl_runtime
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proof = story.verify_derivation(auth, proposal, action_items=residual, spec_paths=SPEC_PATHS)
        auth.record_child_derived(proposal, proof)

        orig_prop_bytes = auth.child_proposal_path("B014").read_bytes()
        orig_proof_bytes = auth.child_proof_path("B014").read_bytes()

        class DummyUnit:
            spec_path = self.root / "_tl-orc/project/tasks/connector-2-10.md"
            do_not_touch = []
            allowed_effects = dict(auth.payload["allowed_effects"])

        dummy_batch = {
            "batch_id": "B014",
            "authorization": {
                "child_proposal_digest": "f" * 64,
                "derivation_proof_digest": proof["derivation_proof_digest"],
            },
            "declared_model_calls": 2,
            "units": ["T001"],
            "allowed_effects": dict(auth.payload["allowed_effects"]),
        }

        class MockRuntime:
            def __init__(self, authority, repo, batch):
                self.authority = authority
                self.repo = repo
                self.batch = batch
                self.batch_id = batch["batch_id"]
                self.units = {"T001": DummyUnit()}
                self.git = authority.repo
                self.config = {}

        mock_rt = MockRuntime(auth, self.root, dummy_batch)
        with self.assertRaises(tl_runtime.Refusal) as raised:
            tl_runtime.Runtime._bind_and_verify_auto_story_child(mock_rt)
        self.assertIn("child proposal digest does not match", str(raised.exception))

        auth.refold()
        self.assertEqual(auth.child_proposal_path("B014").read_bytes(), orig_prop_bytes)
        self.assertEqual(auth.child_proof_path("B014").read_bytes(), orig_proof_bytes)
        self.assertEqual(auth.state.children["B014"]["state"], "derived")
        open_events = [e for e in auth.journal.read()[0] if e["kind"] == "child_open" and e.get("child_batch_id") == "B014"]
        self.assertEqual(open_events, [])

    def test_r9_rederiving_active_open_child_refused_with_state_integrity(self) -> None:
        """R9: rederiving a child_batch_id already active/open is refused; original proposal/proof, children count and lineage remain identical."""
        auth = self.authority()
        first = self.base_child(auth, child_batch_id="B013")
        proof = story.verify_derivation(auth, first)
        auth.record_child_derived(first, proof)
        commit = self.governance_base
        tree = self.git.tree()
        auth.record_child_open("B013", branch="main", head_commit=commit, tree=tree)

        auth.refold()
        self.assertEqual(auth.state.children["B013"]["state"], "open")
        orig_proposal_bytes = auth.child_proposal_path("B013").read_bytes()
        orig_proof_bytes = auth.child_proof_path("B013").read_bytes()
        orig_children_count = len(auth.state.children)
        orig_child_entry = copy.deepcopy(auth.state.children["B013"])
        events_before = [e for e in auth.journal.read()[0] if e.get("child_batch_id") == "B013"]

        # Attempt 1: verify_derivation on already open child_batch_id
        with self.assertRaises(story.HardStop) as raised_verify:
            story.verify_derivation(auth, first)
        self.assertEqual(raised_verify.exception.reason, "state_integrity")
        self.assertIn("already derived", raised_verify.exception.detail)

        # Attempt 2: record_child_derived on already open child_batch_id (even with new proposal)
        alt_first = copy.deepcopy(first)
        alt_first["model_call_budget"] = 4
        alt_proof = copy.deepcopy(proof)
        alt_proof["child_proposal_digest"] = story.digest_of(alt_first)
        alt_proof["derivation_proof_digest"] = self._proof_digest(alt_proof)
        with self.assertRaises(story.HardStop) as raised_record:
            auth.record_child_derived(alt_first, alt_proof)
        self.assertEqual(raised_record.exception.reason, "state_integrity")
        self.assertIn("already derived", raised_record.exception.detail)

        # Verify invariants
        auth.refold()
        self.assertEqual(auth.child_proposal_path("B013").read_bytes(), orig_proposal_bytes)
        self.assertEqual(auth.child_proof_path("B013").read_bytes(), orig_proof_bytes)
        self.assertEqual(len(auth.state.children), orig_children_count)
        self.assertEqual(auth.state.children["B013"]["state"], "open")
        self.assertEqual(auth.state.children["B013"]["derivation"], orig_child_entry["derivation"])
        self.assertEqual(auth.state.children["B013"].get("open"), orig_child_entry.get("open"))
        derived_and_open_events = [e for e in auth.journal.read()[0] if e.get("child_batch_id") == "B013" and e["kind"] in {"child_derived", "child_open"}]
        expected_events = [e for e in events_before if e["kind"] in {"child_derived", "child_open"}]
        self.assertEqual(derived_and_open_events, expected_events)

    def test_r9_rederiving_closed_child_refused_with_state_integrity(self) -> None:
        """R9: rederiving a child_batch_id already closed is refused; original proposal/proof, children count and lineage remain identical."""
        auth = self.authority()
        residual = [self.patch_item("R5")]
        self._setup_closed_predecessor(auth, residual_items=residual)

        # Derive, open, and close rework child B014
        second = story.derive_child_proposal(
            authority=auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proof_b014 = story.verify_derivation(auth, second, action_items=residual, spec_paths=SPEC_PATHS)
        auth.record_child_derived(second, proof_b014)
        commit = self.governance_base
        tree = self.git.tree()
        auth.record_child_open("B014", branch="main", head_commit=commit, tree=tree,
                               lineage={"parent_child_batch_id": "B013",
                                        "unresolved_action_items_digest": story.unresolved_action_items_digest(residual)})
        auth.record_child_closed(
            child_batch_id="B014", governance_base_commit=commit, checker_reviewed_commit=commit,
            checker_reviewed_tree=tree, functional_checkpoint_commit=commit, functional_checkpoint_tree=tree,
            checker_verdict="changes_requested", unresolved_action_items=residual)

        auth.refold()
        self.assertEqual(auth.state.children["B014"]["state"], "closed")
        orig_proposal_bytes = auth.child_proposal_path("B014").read_bytes()
        orig_proof_bytes = auth.child_proof_path("B014").read_bytes()
        orig_children_count = len(auth.state.children)
        orig_child_entry = copy.deepcopy(auth.state.children["B014"])
        events_before = [e for e in auth.journal.read()[0] if e.get("child_batch_id") == "B014"]

        # Attempt 1: verify_derivation on closed child
        with self.assertRaises(story.HardStop) as raised_verify:
            story.verify_derivation(auth, second, action_items=residual, spec_paths=SPEC_PATHS)
        self.assertEqual(raised_verify.exception.reason, "state_integrity")
        self.assertIn("already derived", raised_verify.exception.detail)

        # Attempt 2: record_child_derived on closed child
        with self.assertRaises(story.HardStop) as raised_record:
            auth.record_child_derived(second, proof_b014)
        self.assertEqual(raised_record.exception.reason, "state_integrity")
        self.assertIn("already derived", raised_record.exception.detail)

        # Verify invariants: blobs immutable, count identical, lineage identical
        auth.refold()
        self.assertEqual(auth.child_proposal_path("B014").read_bytes(), orig_proposal_bytes)
        self.assertEqual(auth.child_proof_path("B014").read_bytes(), orig_proof_bytes)
        self.assertEqual(len(auth.state.children), orig_children_count)
        self.assertEqual(auth.state.children["B014"]["state"], "closed")
        self.assertEqual(auth.state.children["B014"]["derivation"], orig_child_entry["derivation"])
        self.assertEqual(auth.state.children["B014"].get("open"), orig_child_entry.get("open"))
        self.assertEqual(auth.state.children["B014"]["open"].get("lineage", {}).get("parent_child_batch_id"), "B013")
        derived_open_closed_events = [e for e in auth.journal.read()[0] if e.get("child_batch_id") == "B014" and e["kind"] in {"child_derived", "child_open", "child_closed"}]
        expected_events = [e for e in events_before if e["kind"] in {"child_derived", "child_open", "child_closed"}]
        self.assertEqual(derived_open_closed_events, expected_events)


if __name__ == "__main__":
    unittest.main()
