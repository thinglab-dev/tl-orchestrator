#!/usr/bin/env python3
"""E) Protected paths and structural integrity (T033 §2.10, T032 §2.15), counterfactuals 20-24."""

from __future__ import annotations

import contextlib
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from story_authority_support import ESCAPING_PATTERNS, StoryCase, freeze, make_payload, plan_validator, story

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


class ProtectedPathContainmentTest(StoryCase):
    """R10. A protected path pattern is repository-relative and contained, or it is refused
    before anything is joined onto the root; filesystem errors are violations, never exceptions."""

    def setUp(self) -> None:
        super().setUp()
        outside = tempfile.TemporaryDirectory(prefix="tl-outside-")
        self.addCleanup(outside.cleanup)
        self.outside = Path(outside.name).resolve()
        self.sentinel = self.outside / "sentinel.txt"
        self.sentinel.write_text("must never be read through a protected path\n", encoding="utf-8")
        # Falsifiable: without the refusal, joining this pattern onto the root reaches the sentinel.
        self.escape = os.path.relpath(self.sentinel, self.root)
        self.assertTrue(self.escape.startswith(".."))
        self.assertEqual((self.root / self.escape).read_bytes(), self.sentinel.read_bytes())

    @contextlib.contextmanager
    def filesystem_spy(self):
        """Record every path the validator stats, reads, walks or dereferences."""
        touched: list[str] = []

        def spy(original):
            def wrapper(target, *args, **kwargs):
                touched.append(os.fspath(target))
                return original(target, *args, **kwargs)
            return wrapper

        with contextlib.ExitStack() as stack:
            for name in ("is_symlink", "is_file", "is_dir", "read_bytes", "lstat", "stat"):
                stack.enter_context(mock.patch.object(Path, name, spy(getattr(Path, name))))
            for name in ("walk", "readlink", "lstat", "stat"):
                stack.enter_context(mock.patch.object(plan_validator.os, name, spy(getattr(os, name))))
            yield touched

    def assert_nothing_outside_touched(self, touched: list[str]) -> None:
        root = str(self.root)
        for path in map(os.path.abspath, touched):
            # Resolving the repository root itself walks its ancestors; nothing else may be touched.
            inside_or_ancestor = os.path.commonpath([root, path]) in {root, path}
            self.assertTrue(inside_or_ancestor, f"{path!r} is outside the repository and was accessed")
            self.assertNotEqual(os.path.commonpath([str(self.outside), path]), str(self.outside))

    def all_escapes(self) -> dict[str, str]:
        return {**ESCAPING_PATTERNS, "real_sentinel_escape": self.escape}

    def test_central_normalization_refuses_every_escape_and_keeps_relative_patterns(self) -> None:
        for name, pattern in self.all_escapes().items():
            with self.subTest(name):
                with self.assertRaises(plan_validator.ProtectedPathError) as raised:
                    plan_validator.normalize_protected_pattern(pattern)
                self.assertEqual(raised.exception.pattern, pattern)
                self.assertTrue(raised.exception.detail)
        for pattern in ("", None, 7):
            with self.assertRaises(plan_validator.ProtectedPathError):
                plan_validator.normalize_protected_pattern(pattern)
        for pattern, normalized in (("docs", "docs"), ("docs/", "docs"), ("./docs/ARCH.md", "docs/ARCH.md"),
                                    ("_tl-orc/project", "_tl-orc/project"), ("a..b/c", "a..b/c"), (".", ".")):
            self.assertEqual(plan_validator.normalize_protected_pattern(pattern), normalized)

    def test_snapshot_set_refuses_before_any_external_access(self) -> None:
        for name, pattern in self.all_escapes().items():
            with self.subTest(name), self.filesystem_spy() as touched:
                with self.assertRaises(plan_validator.ProtectedPathError):
                    snapshot_set(self.root, pattern)
                self.assertEqual(touched, [], "the refusal must precede every filesystem access")
        # The spy is live: a legitimate snapshot does stat and read the tree.
        with self.filesystem_spy() as touched:
            snapshot = snapshot_set(self.root, "./docs/")
        self.assertTrue(touched)
        self.assert_nothing_outside_touched(touched)
        self.assertEqual(snapshot["pattern"], "docs")
        self.assertEqual([entry["path"] for entry in snapshot["entries"]], ["docs/ARCH.md"])

    def test_symlinked_intermediate_directory_cannot_redirect_outside(self) -> None:
        if not can_symlink(self.root):
            self.skipTest("this platform does not allow creating symlinks")
        os.symlink(self.outside, self.root / "linked")
        self.assertTrue((self.root / "linked" / "sentinel.txt").is_file())
        expected = plan_validator.sha256_hex(self.sentinel.read_bytes())
        with self.filesystem_spy() as touched:
            with self.assertRaises(plan_validator.ProtectedPathError):
                snapshot_set(self.root, "linked/sentinel.txt")
            violations = verify(self.root, [{"pattern": "linked/sentinel.txt", "policy": "exact_file_hash",
                                             "sha256": expected}])
        self.assert_nothing_outside_touched(touched)
        self.assertEqual([v["violation"] for v in violations], ["protected_path_pattern_invalid"])
        self.assertIn("symlink", violations[0]["detail"])
        # The symlink itself, as the final component, is still an entry and never followed.
        self.assertEqual([e["type"] for e in snapshot_set(self.root, "linked")["entries"]], ["symlink"])

    def test_verify_protected_paths_refuses_escapes_under_every_policy(self) -> None:
        payload = self.sentinel.read_bytes()
        entry = {"path": "sentinel.txt", "type": "file", "size": len(payload),
                 "sha256": plan_validator.sha256_hex(payload)}
        for name, pattern in self.all_escapes().items():
            items = [
                {"pattern": pattern, "policy": "read_only"},
                {"pattern": pattern, "policy": "exact_file_hash", "sha256": plan_validator.sha256_hex(payload)},
                {"pattern": pattern, "policy": "exact_set_snapshot",
                 "snapshot": {"entries": [entry], "digest": plan_validator.digest_of([entry])}},
            ]
            for item in items:
                with self.subTest(name, policy=item["policy"]), self.filesystem_spy() as touched:
                    violations = verify(self.root, [item], dirty_paths=[])
                    self.assert_nothing_outside_touched(touched)
                    self.assertEqual([v["violation"] for v in violations], ["protected_path_pattern_invalid"])
                    self.assertEqual(violations[0]["pattern"], pattern)
                    self.assertEqual(violations[0]["policy"], item["policy"])
                    self.assertTrue(violations[0]["detail"])

        # One invalid pattern never hides, nor is hidden by, the verification of a valid one.
        mixed = [{"pattern": "../outside", "policy": "exact_file_hash", "sha256": "0" * 64},
                 {"pattern": "./docs/ARCH.md", "policy": "exact_file_hash",
                  "sha256": plan_validator.sha256_hex((self.root / "docs/ARCH.md").read_bytes())},
                 {"pattern": "docs/", "policy": "read_only"}]
        self.assertEqual([v["violation"] for v in verify(self.root, mixed, dirty_paths=["docs/ARCH.md"])],
                         ["protected_path_pattern_invalid", "protected_read_only_mutated"])

    def test_filesystem_errors_become_structured_violations(self) -> None:
        reference = {"pattern": "docs", "policy": "exact_set_snapshot", "snapshot": snapshot_set(self.root, "docs")}
        single = {"pattern": "docs/ARCH.md", "policy": "exact_file_hash",
                  "sha256": plan_validator.sha256_hex((self.root / "docs/ARCH.md").read_bytes())}
        for error in (PermissionError(13, "Permission denied", str(self.root / "docs/ARCH.md")),
                      OSError(5, "Input/output error", str(self.root / "docs/ARCH.md"))):
            for item in (reference, single):
                with self.subTest(type(error).__name__, policy=item["policy"]):
                    with mock.patch.object(Path, "read_bytes", side_effect=error):
                        violations = verify(self.root, [item])
                    self.assertEqual([v["violation"] for v in violations], ["protected_path_unreadable"])
                    self.assertEqual(violations[0]["path"], str(self.root / "docs/ARCH.md"))
                    self.assertIn(type(error).__name__, violations[0]["detail"])
                    self.assertIn(error.strerror, violations[0]["detail"])

        # An unreadable directory is not a silently shorter snapshot.
        with mock.patch.object(plan_validator.os, "walk",
                               side_effect=PermissionError(13, "Permission denied", str(self.root / "docs"))):
            violations = verify(self.root, [reference])
        self.assertEqual([v["violation"] for v in violations], ["protected_path_unreadable"])
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            private = self.root / "docs" / "private"
            private.mkdir()
            os.chmod(private, 0)
            self.addCleanup(os.chmod, private, 0o700)
            with self.assertRaises(PermissionError):
                snapshot_set(self.root, "docs")
            self.assertEqual([v["violation"] for v in verify(self.root, [reference])], ["protected_path_unreadable"])

        # Through the Story Authority the violation is a hard stop that carries the detail.
        payload = {"protected_paths": [single]}
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaises(story.HardStop) as raised:
                story.assert_protected_paths_intact(self.root, payload)
        self.assertEqual(raised.exception.reason, "protected_path_violation")
        self.assertEqual([v["violation"] for v in raised.exception.evidence["violations"]],
                         ["protected_path_unreadable"])

    def test_story_authority_refuses_escaping_protected_paths(self) -> None:
        for name, pattern in self.all_escapes().items():
            with self.subTest(name):
                escaping = [{"pattern": pattern, "policy": "read_only"}]
                with self.assertRaises(story.Refusal) as raised:
                    freeze(make_payload(protected_paths=escaping))
                self.assertIn("protected_path_pattern_invalid", str(raised.exception))
                with self.assertRaises(story.HardStop) as stopped:
                    story.assert_protected_paths_intact(self.root, {"protected_paths": escaping}, dirty_paths=[])
                self.assertEqual(stopped.exception.reason, "protected_path_violation")
                self.assertEqual([v["violation"] for v in stopped.exception.evidence["violations"]],
                                 ["protected_path_pattern_invalid"])

        # A frozen envelope whose payload is later edited to escape is a hard stop, never trusted.
        envelope = copy.deepcopy(self.frozen_authority())
        envelope["authority_payload"]["protected_paths"].append({"pattern": "../outside", "policy": "read_only"})
        with self.assertRaises(story.HardStop) as stopped:
            story.verify_authority_envelope(envelope)
        self.assertIn("protected_path_pattern_invalid", stopped.exception.detail)

    def test_monotonicity_refuses_escaping_patterns_on_either_side(self) -> None:
        parent = [{"pattern": "docs/ARCH.md", "policy": "exact_file_hash",
                   "sha256": plan_validator.sha256_hex((self.root / "docs/ARCH.md").read_bytes())}]
        for name, pattern in self.all_escapes().items():
            with self.subTest(name):
                child = copy.deepcopy(parent) + [{"pattern": pattern, "policy": "read_only"}]
                violations = monotonic(parent, child)
                self.assertEqual([(v["violation"], v["side"]) for v in violations],
                                 [("protected_path_pattern_invalid", "child")])
                self.assertEqual(violations[0]["pattern"], pattern)
                violations = monotonic(parent + [{"pattern": pattern, "policy": "read_only"}], copy.deepcopy(parent))
                self.assertEqual([(v["violation"], v["side"]) for v in violations],
                                 [("protected_path_pattern_invalid", "parent")])

        auth = self.authority(self.frozen_authority(protected_paths=parent))
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=4, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        proposal["protected_paths"] = copy.deepcopy(parent) + [{"pattern": "/etc", "policy": "read_only"}]
        with self.assertRaises(story.HardStop) as raised:
            story.verify_derivation(auth, proposal)
        self.assertEqual(raised.exception.reason, "protected_path_violation")
        self.assertIn("protected_path_pattern_invalid", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
