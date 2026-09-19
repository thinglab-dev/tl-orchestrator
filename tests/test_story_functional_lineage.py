#!/usr/bin/env python3
"""C) Functional lineage across unmerged children (T032 §2.11), counterfactual 10."""

from __future__ import annotations

import unittest

from story_authority_support import CONNECTOR_TESTS_V2, CONNECTOR_V2, StoryCase, story

SPEC_PATHS = ("_tl-orc/project/tasks/connector-2-10.md",)


class FunctionalLineageTest(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.auth = self.authority(self.baseline_authority())
        self.residual = [
            self.patch_item("R5", location="src/connector.py:118"),
            self.patch_item("R6", location="tests/test_connector.py:64"),
        ]
        # B013 runs, is reviewed, is NOT approved, and is NOT merged.
        b013 = story.derive_child_proposal(
            authority=self.auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=8, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        self.auth.record_child_derived(b013, story.verify_derivation(self.auth, b013))
        self.git("checkout", "-q", "-b", "auto-story/A001/B013", self.governance_base)
        self.auth.record_child_open("B013", branch="auto-story/A001/B013", head_commit=self.git.head(),
                                    tree=self.git.tree())
        self.write("src/connector.py", CONNECTOR_V2.replace("if attempt + 1 < attempts:\n                ", ""))
        self.reviewed_commit = self.git.commit_all("B013: bounded retry with backoff")
        self.reviewed_tree = self.git.tree()
        self.auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.reviewed_commit, checker_reviewed_tree=self.reviewed_tree,
            functional_checkpoint_commit=self.reviewed_commit, functional_checkpoint_tree=self.reviewed_tree,
            checker_verdict="changes_requested", unresolved_action_items=self.residual)

    def child(self, checkpoint) -> dict:
        proposal = story.derive_child_proposal(
            authority=self.auth, child_batch_id="B014", action_items=self.residual, previous_child_id="B013",
            model_call_budget=6, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proposal["functional_parent_checkpoint"] = checkpoint
        return proposal

    def test_derived_child_inherits_exact_unmerged_checker_reviewed_checkpoint(self) -> None:
        """10. Starting from main or from a tampered commit fails; the correct child inherits the
        whole cumulative diff of a predecessor that was never integrated."""
        governance_tree = self.git.tree(self.governance_base)
        self.assertNotEqual(self.reviewed_tree, governance_tree)

        # A child that wants to restart from the governance base is refused. Checked without the
        # lease, so each refusal is raised but not journaled: a journaled hard stop is terminal
        # (R18) and the correct child below must still be derivable under this authority.
        self.auth.release()
        for wrong in (
            None,
            {"commit": self.governance_base, "tree": governance_tree, "child_batch_id": "B013"},
            {"commit": self.reviewed_commit, "tree": governance_tree, "child_batch_id": "B013"},
            {"commit": self.governance_base, "tree": self.reviewed_tree, "child_batch_id": "B013"},
            {"commit": self.reviewed_commit, "tree": self.reviewed_tree, "child_batch_id": "B999"},
        ):
            with self.assertRaises(story.HardStop) as raised:
                story.verify_derivation(self.auth, self.child(wrong), action_items=self.residual,
                                        spec_paths=SPEC_PATHS)
            self.assertEqual(raised.exception.reason, "state_integrity", raised.exception.detail)

        self.assertEqual(self.auth.refold().hard_stops, [], "refusals without the lease journal nothing")
        self.auth.acquire()
        correct = {"commit": self.reviewed_commit, "tree": self.reviewed_tree, "child_batch_id": "B013"}
        proof = story.verify_derivation(self.auth, self.child(correct), action_items=self.residual,
                                        spec_paths=SPEC_PATHS)
        self.assertEqual(proof["functional_parent_checkpoint"], correct)

        # The worktree itself is proven before the Maker is allowed to touch anything.
        self.git("checkout", "-q", "main")
        with self.assertRaises(story.HardStop) as from_main:
            story.verify_functional_checkpoint(self.root, correct)
        self.assertEqual(from_main.exception.reason, "unexpected_tree_state")
        self.assertIn("must start at", from_main.exception.detail)

        with self.assertRaises(story.HardStop) as absent:
            story.verify_functional_checkpoint(self.root, {"commit": "a" * 40, "tree": self.reviewed_tree})
        self.assertEqual(absent.exception.reason, "state_integrity")
        self.assertIn("not present", absent.exception.detail)

        self.git("checkout", "-q", "-b", "auto-story/A001/B014", self.reviewed_commit)
        with self.assertRaises(story.HardStop) as tampered:
            story.verify_functional_checkpoint(self.root, {"commit": self.reviewed_commit, "tree": governance_tree})
        self.assertEqual(tampered.exception.reason, "unexpected_tree_state")
        self.assertIn("not the recorded", tampered.exception.detail)

        self.write("src/connector.py", "# uncommitted drift\n")
        with self.assertRaises(story.HardStop) as dirty:
            story.verify_functional_checkpoint(self.root, correct)
        self.assertEqual(dirty.exception.reason, "unexpected_tree_state")
        self.assertIn("not clean", dirty.exception.detail)
        self.git("checkout", "--", "src/connector.py")

        verified = story.verify_functional_checkpoint(self.root, correct)
        self.assertEqual(verified, {"commit": self.reviewed_commit, "tree": self.reviewed_tree, "verified": True})

        # The derived child carries B013's work forward without B013 ever touching main.
        self.write("src/connector.py", CONNECTOR_V2)
        self.write("tests/test_connector.py", CONNECTOR_TESTS_V2)
        integration_candidate = self.git.commit_all("B014: resolve R5 and R6")
        cumulative = self.git("diff", "--name-only", self.governance_base, integration_candidate).split()
        self.assertEqual(sorted(cumulative), ["src/connector.py", "tests/test_connector.py"])
        self.assertIn("if attempt + 1 < attempts", (self.root / "src/connector.py").read_text(encoding="utf-8"))
        self.assertEqual(self.git("rev-parse", "main"), self.governance_base)
        self.assertEqual(self.git("branch", "--contains", self.reviewed_commit, "--list", "main"), "")
        # B013 stays immutable as historical evidence.
        self.assertEqual(self.git("rev-parse", f"{self.reviewed_commit}^{{tree}}"), self.reviewed_tree)
        self.assertEqual(self.git("rev-parse", f"{integration_candidate}^"), self.reviewed_commit)

    def test_cumulative_review_range_spans_the_story_not_the_patch(self) -> None:
        """The next Checker reviews story_baseline..integration_candidate, not the child's patch."""
        self.git("checkout", "-q", "-b", "auto-story/A001/B014", self.reviewed_commit)
        self.write("src/connector.py", CONNECTOR_V2)
        candidate = self.git.commit_all("B014: resolve R5")
        self.assertEqual(story.cumulative_review_range(self.governance_base, candidate),
                         f"{self.governance_base}..{candidate}")
        spanned = self.git("rev-list", f"{self.governance_base}..{candidate}").split()
        self.assertEqual(spanned, [candidate, self.reviewed_commit])

    def test_child_closure_records_the_full_lineage(self) -> None:
        """Every field §2.11 requires is journaled when a child closes, merged or not."""
        closure = self.auth.state.closure_of("B013")
        for field in ("child_batch_id", "governance_base_commit", "checker_reviewed_commit",
                      "checker_reviewed_tree", "functional_checkpoint_commit", "functional_checkpoint_tree",
                      "checker_verdict", "unresolved_action_items_digest"):
            self.assertIn(field, closure, field)
        self.assertEqual(closure["checker_verdict"], "changes_requested")
        self.assertEqual(closure["unresolved_action_items_digest"],
                         story.unresolved_action_items_digest(self.residual))

    def test_next_child_must_be_derived_from_the_findings_recorded_at_closure(self) -> None:
        """A child claiming different residual findings than the closure recorded is refused."""
        forged = story.derive_child_proposal(
            authority=self.auth, child_batch_id="B014",
            action_items=[self.patch_item("R9", location="src/connector.py:5")],
            previous_child_id="B013", model_call_budget=6, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(self.auth, forged,
                                    action_items=[self.patch_item("R9", location="src/connector.py:5")],
                                    spec_paths=SPEC_PATHS)
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("differ from the ones recorded", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
