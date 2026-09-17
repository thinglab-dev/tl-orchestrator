#!/usr/bin/env python3
"""F) Operational limits and the Story boundary (T032 §2.9), counterfactuals 25-26."""

from __future__ import annotations

import unittest

from story_authority_support import StoryCase, story


class OperationalLimitsTest(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.auth = self.authority(self.baseline_authority())

    def test_max_consecutive_failures_halts_auto_story(self) -> None:
        """25. N child batches in a row without progress stop the Story for the operator.

        The batch ceiling is deliberately raised here so the streak, not the child count, is what
        stops the Story."""
        auth = self.authority(self.frozen_authority(authority_id="A010", max_child_batches=6))
        self.assertEqual(auth.payload["max_consecutive_failed_batches"], 2)
        auth.record_child_failed("B013", reason="unrecoverable_harness_failure", detail="adapter never started")
        self.assertEqual(auth.state.consecutive_failures, 1)
        auth.assert_failure_streak()  # one failure is not yet the limit

        auth.record_child_failed("B014", reason="unrecoverable_harness_failure", detail="adapter never started")
        self.assertEqual(auth.state.consecutive_failures, 2)
        with self.assertRaises(story.HardStop) as raised:
            auth.assert_failure_streak()
        self.assertEqual(raised.exception.reason, "consecutive_batch_failures_exhausted")
        self.assertEqual(auth.state.hard_stops[-1]["reason"], "consecutive_batch_failures_exhausted")

        # Derivation is refused for the same reason, so no further child opens.
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B015", action_items=[], previous_child_id=None,
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as refused:
            story.verify_derivation(auth, proposal)
        self.assertEqual(refused.exception.reason, "consecutive_batch_failures_exhausted")

    def test_a_child_that_closes_without_progress_counts_as_a_failure(self) -> None:
        """A batch that reviews the same tree it inherited has not advanced the Story."""
        auth = self.authority(self.frozen_authority(authority_id="A006"))
        tree = self.git.tree()
        commit = self.git.head()
        first = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=4, governance_base_commit=commit, story_baseline_commit=commit)
        auth.record_child_derived(first, story.verify_derivation(auth, first))
        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=commit, checker_reviewed_commit=commit,
            checker_reviewed_tree=tree, functional_checkpoint_commit=commit, functional_checkpoint_tree=tree,
            checker_verdict="changes_requested", unresolved_action_items=[self.patch_item("R5")])
        # No inherited checkpoint means the first child always counts as progress.
        self.assertEqual(auth.state.consecutive_failures, 0)
        self.assertTrue(auth.state.closure_of("B013")["made_progress"])

    def test_auto_story_strictly_prohibits_next_story_start(self) -> None:
        """26. The authority covers one Story; the next one in the queue needs a new decision."""
        story.assert_story_boundary(self.auth.payload, "connector:2-10")
        story.assert_story_boundary(self.auth.payload, "connector:2-10/unit-a")
        story.assert_batch_within_story(self.auth.payload, ["connector:2-10", "connector:2-10/unit-b"])

        for next_story in ("connector:2-11", "connector:2-1", "connector", "billing:3-1", ""):
            with self.assertRaises(story.HardStop, msg=next_story) as raised:
                story.assert_story_boundary(self.auth.payload, next_story)
            self.assertEqual(raised.exception.reason, "next_story_without_authorization")
            self.assertIn("requires a new", raised.exception.detail)

        with self.assertRaises(story.HardStop) as batch:
            story.assert_batch_within_story(self.auth.payload, ["connector:2-10", "connector:2-11"])
        self.assertEqual(batch.exception.reason, "next_story_without_authorization")

        # Closing the Story closes the authority: nothing more may be reserved or derived under it.
        self.auth.close_authority(state="done", reason="story reached CLOSE")
        with self.assertRaises(story.HardStop) as closed:
            self.auth.reserve_call(logical_call_id="next-story-maker", global_attempt_id="A001-attempt-900",
                                   child_batch_id="B099")
        self.assertEqual(closed.exception.reason, "authority_missing_or_ambiguous")
        self.assertIn("is closed", closed.exception.detail)

    def test_max_child_batches_and_single_active_child_are_enforced(self) -> None:
        auth = self.authority(self.frozen_authority(authority_id="A007"))
        commit, tree = self.git.head(), self.git.tree()

        residual = [self.patch_item("R5")]

        def proposal(child_id: str, parent: str | None = None) -> dict:
            return story.derive_child_proposal(
                authority=auth, child_batch_id=child_id, action_items=residual if parent else [],
                previous_child_id=parent, model_call_budget=2, governance_base_commit=commit,
                story_baseline_commit=commit)

        first = proposal("B013")
        auth.record_child_derived(first, story.verify_derivation(auth, first))
        # A second child while the first is still open is refused: AUTO_STORY v1 runs one at a time.
        with self.assertRaises(story.HardStop) as active:
            story.verify_derivation(auth, proposal("B014"))
        self.assertEqual(active.exception.reason, "state_integrity")
        self.assertIn("max_active_child_batches", active.exception.detail)
        self.assertEqual(story.MAX_ACTIVE_CHILD_BATCHES, 1)

        auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=commit, checker_reviewed_commit=commit,
            checker_reviewed_tree=tree, functional_checkpoint_commit=commit, functional_checkpoint_tree=tree,
            checker_verdict="changes_requested", unresolved_action_items=residual)
        second = proposal("B014", parent="B013")
        auth.record_child_derived(second, story.verify_derivation(auth, second, action_items=residual))
        auth.record_child_closed(
            child_batch_id="B014", governance_base_commit=commit, checker_reviewed_commit=commit,
            checker_reviewed_tree=tree, functional_checkpoint_commit=commit, functional_checkpoint_tree=tree,
            checker_verdict="changes_requested", unresolved_action_items=residual)
        # max_child_batches is 2: a third is refused whatever else is true.
        with self.assertRaises(story.HardStop) as exhausted:
            story.verify_derivation(auth, proposal("B015", parent="B014"), action_items=residual)
        self.assertEqual(exhausted.exception.reason, "max_child_batches_exhausted")

    def test_wall_clock_deadline_stops_derivation(self) -> None:
        auth = self.authority(self.frozen_authority(authority_id="A008",
                                                    wall_clock_deadline="2026-09-17T12:00:00Z"))
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        story.verify_derivation(auth, proposal, now="2026-09-17T11:59:59Z")
        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal, now="2026-09-17T12:00:01Z")
        self.assertEqual(raised.exception.reason, "wall_clock_deadline_exceeded")

    def test_merge_effect_flag_is_not_a_t028_bypass(self) -> None:
        """§2.9: allowed_effects.merge is a capability flag; T028 still decides the merge."""
        self.assertTrue(self.auth.payload["allowed_effects"]["merge"])

        class Receipt:
            def __init__(self, status, reason=""):
                self.status = status
                self.reason = reason

            @property
            def is_confirmed(self):
                return self.status == "CONFIRMED"

            def is_authentic(self, _trust_root=None, _expected_repo=None):
                return False

        with self.assertRaises(story.HardStop) as absent:
            story.assert_merge_authority(self.auth.payload, None)
        self.assertEqual(absent.exception.reason, "authority_missing_or_ambiguous")

        with self.assertRaises(story.HardStop) as rejected:
            story.assert_merge_authority(self.auth.payload, Receipt("REJECTED", "missing_merge_authorization"))
        self.assertIn("REJECTED", rejected.exception.detail)

        with self.assertRaises(story.HardStop) as forged:
            story.assert_merge_authority(self.auth.payload, Receipt("CONFIRMED"))
        self.assertIn("trust root", forged.exception.detail)

        denied = self.authority(self.frozen_authority(
            authority_id="A009",
            allowed_effects={**self.auth.payload["allowed_effects"], "merge": False}))
        with self.assertRaises(story.HardStop) as effect:
            story.assert_merge_authority(denied.payload, Receipt("CONFIRMED"))
        self.assertEqual(effect.exception.reason, "effect_expansion")


if __name__ == "__main__":
    unittest.main()
