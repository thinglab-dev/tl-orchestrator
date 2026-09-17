#!/usr/bin/env python3
"""E) Protected paths and structural integrity (T033 §2.10, T032 §2.15), counterfactuals 20-24."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path

from story_authority_support import StoryCase, plan_validator, story

monotonic = plan_validator.assert_protected_paths_monotonic
snapshot_set = plan_validator.snapshot_set
verify = plan_validator.verify_protected_paths


def can_symlink(root) -> bool:
    probe = root / ".symlink-probe"
    try:
        os.symlink("target", probe)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


class ProtectedPathVerificationTest(StoryCase):

    def protected_docs(self) -> dict:
        return {"pattern": "docs", "policy": "exact_set_snapshot", "snapshot": snapshot_set(self.root, "docs")}

    def test_protected_paths_symlink_tampering(self) -> None:
        """20. Replacing a regular file with a symlink is a violation, not an equivalent tree."""
        if not can_symlink(self.root):
            self.skipTest("this platform does not allow creating symlinks")
        self.write("docs/NOTES.md", "operational notes\n")
        reference = self.protected_docs()
        self.assertEqual(verify(self.root, [reference]), [])

        target = self.root / "docs" / "ARCH.md"
        payload = target.read_bytes()
        decoy = self.root / "docs" / ".arch-real.md"
        decoy.write_bytes(payload)
        target.unlink()
        os.symlink(".arch-real.md", target)
        self.assertEqual(target.read_bytes(), payload, "the symlink resolves to identical bytes")

        violations = verify(self.root, [reference])
        kinds = {item["violation"] for item in violations}
        self.assertIn("protected_set_entry_type_changed", kinds)
        changed = next(v for v in violations if v["violation"] == "protected_set_entry_type_changed")
        self.assertEqual(changed["path"], "docs/ARCH.md")
        self.assertEqual((changed["expected"], changed["observed"]), ("file", "symlink"))
        self.assertIn("protected_set_entry_added", kinds)
        self.assertIn("docs/.arch-real.md", {v.get("path") for v in violations})

        # The same substitution under exact_file_hash is refused before any hash is compared.
        single = [{"pattern": "docs/ARCH.md", "policy": "exact_file_hash",
                   "sha256": plan_validator.sha256_hex(payload)}]
        self.assertEqual([v["violation"] for v in verify(self.root, single)], ["protected_file_type_changed"])

    def test_exact_set_snapshot_detects_addition_deletion_and_byte_change(self) -> None:
        reference = self.protected_docs()
        self.write("docs/UNTRACKED.md", "slipped in\n")
        self.assertEqual([v["violation"] for v in verify(self.root, [reference])], ["protected_set_entry_added"])
        (self.root / "docs" / "UNTRACKED.md").unlink()
        self.assertEqual(verify(self.root, [reference]), [])

        self.write("docs/ARCH.md", (self.root / "docs" / "ARCH.md").read_text(encoding="utf-8") + "\n")
        self.assertEqual([v["violation"] for v in verify(self.root, [reference])], ["protected_set_entry_modified"])

        self.write("docs/ARCH.md", reference["snapshot"]["entries"][0]["path"] and
                   (self.root / "docs" / "ARCH.md").read_text(encoding="utf-8").rstrip("\n") + "\n")
        self.assertEqual(verify(self.root, [reference]), [])
        (self.root / "docs" / "ARCH.md").unlink()
        self.assertEqual([v["violation"] for v in verify(self.root, [reference])], ["protected_set_entry_removed"])

    def test_read_only_policy_is_verified_against_the_working_tree(self) -> None:
        read_only = [{"pattern": "docs", "policy": "read_only"}]
        self.assertEqual(verify(self.root, read_only), [])
        self.write("docs/ARCH.md", "rewritten\n")
        violations = verify(self.root, read_only)
        self.assertEqual([v["violation"] for v in violations], ["protected_read_only_mutated"])
        self.assertEqual(violations[0]["path"], "docs/ARCH.md")
        # With neither git nor a baseline the answer is a refusal, never a silent pass.
        outside = tempfile.TemporaryDirectory(prefix="tl-no-git-")
        self.addCleanup(outside.cleanup)
        unverifiable = verify(Path(outside.name), read_only)
        self.assertEqual([v["violation"] for v in unverifiable], ["protected_read_only_unverifiable"])

    def test_snapshot_digest_is_bound_to_its_entries(self) -> None:
        reference = self.protected_docs()
        forged = copy.deepcopy(reference)
        forged["snapshot"]["digest"] = "0" * 64
        self.assertIn("protected_snapshot_digest_mismatch", {v["violation"] for v in verify(self.root, [forged])})

    def test_authority_protected_paths_are_enforced_against_the_tree(self) -> None:
        payload = self.frozen_authority()["authority_payload"]
        self.assertEqual(story.assert_protected_paths_intact(self.root, payload), [])
        self.write("docs/ARCH.md", "an unauthorized edit\n")
        with self.assertRaises(story.HardStop) as raised:
            story.assert_protected_paths_intact(self.root, payload)
        self.assertEqual(raised.exception.reason, "protected_path_violation")


class ProtectedPathMonotonicityTest(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.snapshot = snapshot_set(self.root, "docs")
        self.parent = [
            {"pattern": "docs/ARCH.md", "policy": "exact_file_hash",
             "sha256": plan_validator.sha256_hex((self.root / "docs/ARCH.md").read_bytes())},
            {"pattern": "_tl-orc/project/story-authorities", "policy": "exact_set_snapshot",
             "snapshot": snapshot_set(self.root, "_tl-orc/project")},
            {"pattern": "secrets", "policy": "read_only"},
        ]

    def test_child_cannot_weaken_protected_path_policy(self) -> None:
        """21. An inherited pattern keeps its exact policy; a more permissive one is refused."""
        weakened = copy.deepcopy(self.parent)
        weakened[0] = {"pattern": "docs/ARCH.md", "policy": "read_only"}
        violations = monotonic(self.parent, weakened)
        self.assertEqual([v["violation"] for v in violations], ["protected_path_policy_weakened"])
        self.assertEqual(violations[0]["expected"], "exact_file_hash")
        self.assertEqual(violations[0]["observed"], "read_only")

        # Dropping the pattern entirely, and narrowing it to a subpath, are both refused.
        dropped = [item for item in self.parent if item["pattern"] != "secrets"]
        self.assertEqual([v["violation"] for v in monotonic(self.parent, dropped)], ["protected_path_removed"])

        narrowed = [item for item in self.parent if item["pattern"] != "secrets"]
        narrowed.append({"pattern": "secrets/prod", "policy": "read_only"})
        violations = monotonic(self.parent, narrowed)
        self.assertEqual([v["violation"] for v in violations], ["protected_path_coverage_reduced"])
        self.assertIn("secrets/prod", violations[0]["detail"])

        self.assertEqual(monotonic(self.parent, copy.deepcopy(self.parent)), [])

    def test_child_cannot_replace_expected_file_hash(self) -> None:
        """22. The inherited expected hash cannot be swapped for whatever the child produced."""
        replaced = copy.deepcopy(self.parent)
        replaced[0]["sha256"] = "a" * 64
        violations = monotonic(self.parent, replaced)
        self.assertEqual([v["violation"] for v in violations], ["protected_path_hash_replaced"])
        self.assertEqual(violations[0]["expected"], self.parent[0]["sha256"])
        self.assertEqual(violations[0]["observed"], "a" * 64)

    def test_child_cannot_replace_exact_set_snapshot(self) -> None:
        """23. The inherited reference snapshot cannot be re-baselined by the child."""
        self.write("_tl-orc/project/drafts/new-note.md", "a file the child added\n")
        rebaselined = copy.deepcopy(self.parent)
        rebaselined[1]["snapshot"] = snapshot_set(self.root, "_tl-orc/project")
        self.assertNotEqual(rebaselined[1]["snapshot"]["digest"], self.parent[1]["snapshot"]["digest"])
        violations = monotonic(self.parent, rebaselined)
        self.assertEqual([v["violation"] for v in violations], ["protected_path_snapshot_replaced"])
        self.assertEqual(violations[0]["expected"], self.parent[1]["snapshot"]["digest"])

    def test_child_may_add_additional_protected_path(self) -> None:
        """24. Adding protection is always allowed; only removing or relaxing it is not."""
        extended = copy.deepcopy(self.parent) + [
            {"pattern": "src/connector.py", "policy": "exact_file_hash",
             "sha256": plan_validator.sha256_hex((self.root / "src/connector.py").read_bytes())},
            {"pattern": ".github", "policy": "read_only"},
        ]
        self.assertEqual(monotonic(self.parent, extended), [])

        # And the authority accepts such a child while still refusing a relaxed one.
        auth = self.authority(self.frozen_authority(protected_paths=self.parent))
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=4, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proposal["protected_paths"] = extended
        proof = story.verify_derivation(auth, proposal)
        self.assertEqual({c["check"]: c["result"] for c in proof["checks"]}["protected_paths_monotonic"], "pass")

        relaxed = copy.deepcopy(self.parent)
        relaxed[0] = {"pattern": "docs/ARCH.md", "policy": "read_only"}
        proposal["protected_paths"] = relaxed
        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal)
        self.assertEqual(raised.exception.reason, "protected_path_violation")


if __name__ == "__main__":
    unittest.main()
