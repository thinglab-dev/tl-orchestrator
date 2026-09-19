#!/usr/bin/env python3
"""E) Protected paths and structural integrity (T033 §2.10, T032 §2.15), counterfactuals 20-24."""

from __future__ import annotations

import contextlib
import copy
import io
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
    def filesystem_spy(self, reads: list[bytes] | None = None):
        """Record every path the validator stats, opens, lists, reads or dereferences.

        Lookups relative to a directory descriptor are recorded as the path that descriptor was
        opened on joined with the name, so a descriptor-relative access is judged exactly like
        a pathname one. A descriptor the spy did not see opened is recorded as unresolvable,
        which fails the containment assertion rather than passing it.
        """
        touched: list[str] = []
        fd_paths: dict[int, str] = {}

        def where(target, dir_fd=None) -> str:
            if isinstance(target, int):
                return fd_paths.get(target, f"<unresolved fd {target}>")
            target = os.fsdecode(target)
            if dir_fd is not None:
                return os.path.join(fd_paths.get(dir_fd, f"<unresolved fd {dir_fd}>"), target)
            return os.path.abspath(target)

        def spy(original):
            def wrapper(target, *args, **kwargs):
                touched.append(os.fspath(target))
                return original(target, *args, **kwargs)
            return wrapper

        def spy_at(original):
            def wrapper(target=".", *args, dir_fd=None, **kwargs):
                touched.append(where(target, dir_fd))
                if dir_fd is not None:
                    kwargs["dir_fd"] = dir_fd
                return original(target, *args, **kwargs)
            return wrapper

        def spy_open(original):
            def wrapper(target, flags, mode=0o777, *, dir_fd=None):
                full = where(target, dir_fd)
                touched.append(full)
                fd = original(target, flags, mode, dir_fd=dir_fd)
                fd_paths[fd] = full
                return fd
            return wrapper

        def spy_dup(original):
            def wrapper(fd):
                duplicate = original(fd)
                fd_paths[duplicate] = where(fd)
                return duplicate
            return wrapper

        def spy_read(original):
            def wrapper(fd, size):
                touched.append(where(fd))
                data = original(fd, size)
                if reads is not None:
                    reads.append(data)
                return data
            return wrapper

        with contextlib.ExitStack() as stack:
            for name in ("is_symlink", "is_file", "is_dir", "read_bytes", "lstat", "stat"):
                stack.enter_context(mock.patch.object(Path, name, spy(getattr(Path, name))))
            for name in ("walk", "readlink", "lstat", "stat", "listdir", "scandir"):
                stack.enter_context(mock.patch.object(plan_validator.os, name, spy_at(getattr(os, name))))
            stack.enter_context(mock.patch.object(plan_validator.os, "open", spy_open(os.open)))
            stack.enter_context(mock.patch.object(plan_validator.os, "dup", spy_dup(os.dup)))
            stack.enter_context(mock.patch.object(plan_validator.os, "read", spy_read(os.read)))
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
                    with mock.patch.object(plan_validator.os, "read", side_effect=error):
                        violations = verify(self.root, [item])
                    self.assertEqual([v["violation"] for v in violations], ["protected_path_unreadable"])
                    self.assertEqual(violations[0]["path"], str(self.root / "docs/ARCH.md"))
                    self.assertIn(type(error).__name__, violations[0]["detail"])
                    self.assertIn(error.strerror, violations[0]["detail"])

        # An unreadable directory is not a silently shorter snapshot.
        with mock.patch.object(plan_validator.os, "listdir",
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
        with mock.patch.object(plan_validator.os, "read", side_effect=PermissionError(13, "Permission denied")):
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


    # ---- R10: check-then-use through a swapped intermediate component --------------------

    OUTSIDE_MARK = b"OUTSIDE-SENTINEL"

    def swap_fixture(self) -> tuple[bytes, dict, dict]:
        """`vault/inner/data.txt` inside, and a decoy `inner/data.txt` outside at the same
        relative position, so a pathname lookup through a swapped `vault` lands on the decoy."""
        if not can_symlink(self.root):
            self.skipTest("this platform does not allow creating symlinks")
        inside = b"inside bytes the authority froze\n"
        (self.root / "vault" / "inner").mkdir(parents=True)
        (self.root / "vault" / "inner" / "data.txt").write_bytes(inside)
        (self.outside / "inner").mkdir()
        (self.outside / "inner" / "data.txt").write_bytes(self.OUTSIDE_MARK + b" never read\n")
        single = {"pattern": "vault/inner/data.txt", "policy": "exact_file_hash",
                  "sha256": plan_validator.sha256_hex(inside)}
        whole = {"pattern": "vault", "policy": "exact_set_snapshot", "snapshot": snapshot_set(self.root, "vault")}
        return inside, single, whole

    def swap_vault(self) -> None:
        os.rename(self.root / "vault", self.root / "vault.real")
        os.symlink(self.outside, self.root / "vault")

    def unswap_vault(self) -> None:
        os.unlink(self.root / "vault")
        os.rename(self.root / "vault.real", self.root / "vault")

    def assert_no_outside_byte(self, reads: list[bytes], touched: list[str]) -> None:
        self.assertFalse([chunk for chunk in reads if self.OUTSIDE_MARK in chunk],
                         "a byte behind the swapped component was read")
        self.assert_nothing_outside_touched(touched)

    def test_swap_after_a_component_is_opened_cannot_redirect_the_read(self) -> None:
        """The component is swapped for a symlink right after the policy walk opened it:
        everything after that goes through the held descriptor, so only the original directory
        is read. (verify opens `vault` twice: once proving containment, once for the policy.)"""
        inside, single, whole = self.swap_fixture()
        real_open = os.open
        # The final-component pattern `vault` has no intermediate component to prove, so its only
        # open of `vault` is the policy walk's; the nested pattern's second open is.
        cases = [(single, 2, lambda: verify(self.root, [single])),
                 (whole, 1, lambda: verify(self.root, [whole])),
                 (whole, 1, lambda: snapshot_set(self.root, "vault"))]
        for item, swap_on, run in cases:
            opens: list[str] = []
            swapped: list[bool] = []

            def open_then_swap(target, flags, mode=0o777, *, dir_fd=None):
                fd = real_open(target, flags, mode, dir_fd=dir_fd)
                if target == "vault":
                    opens.append(target)
                    if len(opens) == swap_on:
                        swapped.append(True)
                        self.swap_vault()
                        # Falsifiable: a pathname lookup now reaches the decoy outside the repository.
                        self.assertIn(self.OUTSIDE_MARK, (self.root / "vault/inner/data.txt").read_bytes())
                return fd

            reads: list[bytes] = []
            with self.subTest(policy=item["policy"], swap_on=swap_on):
                try:
                    with mock.patch.object(plan_validator.os, "open", open_then_swap), \
                            self.filesystem_spy(reads) as touched:
                        outcome = run()
                finally:
                    if swapped:
                        self.unswap_vault()
                self.assertTrue(swapped, "the swap never happened; the counterproof is not live")
                if isinstance(outcome, list):
                    self.assertEqual(outcome, [], "the held descriptor verifies the original directory")
                else:
                    self.assertEqual(outcome["digest"], whole["snapshot"]["digest"])
                self.assertIn(inside, b"".join(reads))
                self.assert_no_outside_byte(reads, touched)

    def test_swap_between_lstat_and_open_is_refused(self) -> None:
        """The component is swapped after its lstat said directory and before it is opened:
        the no-follow open refuses it, so nothing behind the new symlink is reached."""
        _inside, single, whole = self.swap_fixture()
        real_stat = os.stat
        for item in (single, whole, {"pattern": "vault/inner/data.txt", "policy": "read_only"}):
            swapped: list[bool] = []

            def stat_then_swap(target, *args, dir_fd=None, follow_symlinks=True):
                result = real_stat(target, *args, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
                if target == "vault" and dir_fd is not None and not swapped:
                    swapped.append(True)
                    self.swap_vault()
                return result

            reads: list[bytes] = []
            with self.subTest(policy=item["policy"]):
                try:
                    with mock.patch.object(plan_validator.os, "stat", stat_then_swap), \
                            self.filesystem_spy(reads) as touched:
                        violations = verify(self.root, [item], dirty_paths=[])
                finally:
                    if swapped:
                        self.unswap_vault()
                self.assertTrue(swapped)
                self.assertEqual([v["violation"] for v in violations], ["protected_path_pattern_invalid"])
                self.assertIn("vault", violations[0]["detail"])
                self.assert_no_outside_byte(reads, touched)

    def test_concurrent_swapping_of_an_intermediate_component_never_reads_outside(self) -> None:
        """A second thread keeps flipping `vault` between the real directory and a symlink to
        the outside while verification runs: no iteration reads a byte from outside, and none
        passes as intact while the link is what it walked."""
        import threading
        inside, single, whole = self.swap_fixture()
        stop = threading.Event()
        flips: list[int] = []

        def flipper() -> None:
            while not stop.is_set():
                self.swap_vault()
                self.unswap_vault()
                flips.append(1)

        reads: list[bytes] = []
        outcomes: set[str] = set()
        thread = threading.Thread(target=flipper, daemon=True)
        with self.filesystem_spy(reads) as touched:
            thread.start()
            try:
                for _ in range(300):
                    for item in (single, whole):
                        found = verify(self.root, [item])
                        outcomes.update(v["violation"] for v in found)
                        if not found:
                            outcomes.add("intact")
            finally:
                stop.set()
                thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertTrue(flips, "the concurrent swap never ran")
        self.assert_no_outside_byte(reads, touched)
        # Whatever interleaving happened, an outcome is intact (the real directory was walked)
        # or a fail-closed violation (for the pattern `vault` itself, a symlink met as the final
        # component is an entry hashed by its target text); never a hash over the decoy's bytes.
        self.assertLessEqual(outcomes, {"intact", "protected_path_pattern_invalid", "protected_path_missing",
                                        "protected_path_unreadable", "protected_set_entry_removed",
                                        "protected_set_entry_added", "protected_set_entry_type_changed"})
        self.assertEqual((self.root / "vault" / "inner" / "data.txt").read_bytes(), inside)

    def test_platform_without_secure_primitives_fails_closed(self) -> None:
        """No descriptor-relative no-follow traversal means no verification, never a pathname
        fallback: every policy, read_only included, is `protected_path_unverifiable`."""
        payload = (self.root / "docs/ARCH.md").read_bytes()
        items = [{"pattern": "docs", "policy": "read_only"},
                 {"pattern": "docs/ARCH.md", "policy": "exact_file_hash", "sha256": plan_validator.sha256_hex(payload)},
                 {"pattern": "docs", "policy": "exact_set_snapshot", "snapshot": snapshot_set(self.root, "docs")}]
        with mock.patch.object(plan_validator, "_SECURE_TRAVERSAL_GAPS", ("os.open(dir_fd=)",)):
            reads: list[bytes] = []
            with self.filesystem_spy(reads) as touched:
                violations = verify(self.root, items, dirty_paths=[])
            self.assertEqual([v["violation"] for v in violations], ["protected_path_unverifiable"] * 3)
            self.assertEqual([v["policy"] for v in violations], [item["policy"] for item in items])
            self.assertIn("os.open(dir_fd=)", violations[0]["detail"])
            self.assertEqual(reads, [])
            self.assert_nothing_outside_touched(touched)
            with self.assertRaises(plan_validator.SecureTraversalUnavailable):
                snapshot_set(self.root, "docs")
            with self.assertRaises(story.HardStop) as raised:
                story.assert_protected_paths_intact(self.root, {"protected_paths": items}, dirty_paths=[])
            self.assertEqual(raised.exception.reason, "protected_path_violation")
            with contextlib.redirect_stderr(io.StringIO()) as refused:
                self.assertNotEqual(story.main(["snapshot", "--repo", str(self.root), "--pattern", "docs"]), 0)
            self.assertIn("protected path snapshot refused", refused.getvalue())
        # Real platform probe: this host is expected to offer the primitives the suite relies on.
        self.assertEqual(plan_validator._secure_traversal_gaps(), plan_validator._SECURE_TRAVERSAL_GAPS)

    # ---- R12: read_only proves real containment before its policy is evaluated -----------

    def test_read_only_refuses_a_symlinked_intermediate_component(self) -> None:
        if not can_symlink(self.root):
            self.skipTest("this platform does not allow creating symlinks")
        os.symlink(self.outside, self.root / "linked")
        item = {"pattern": "linked/sentinel.txt", "policy": "read_only"}
        for dirty in (["linked"], [], ["linked/sentinel.txt"], None):
            with self.subTest(dirty_paths=dirty):
                reads: list[bytes] = []
                with self.filesystem_spy(reads) as touched:
                    violations = verify(self.root, [item], dirty_paths=dirty)
                self.assertEqual([v["violation"] for v in violations], ["protected_path_pattern_invalid"])
                self.assertEqual(violations[0]["policy"], "read_only")
                self.assertIn("linked", violations[0]["detail"])
                self.assertIn("symlink", violations[0]["detail"])
                self.assertEqual(reads, [])
                self.assert_nothing_outside_touched(touched)
        # Through the Story Authority the same pattern is a hard stop, not an intact read_only path.
        with self.assertRaises(story.HardStop) as raised:
            story.assert_protected_paths_intact(self.root, {"protected_paths": [item]}, dirty_paths=["linked"])
        self.assertEqual([v["violation"] for v in raised.exception.evidence["violations"]],
                         ["protected_path_pattern_invalid"])


if __name__ == "__main__":
    unittest.main()
