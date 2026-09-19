#!/usr/bin/env python3
"""R11. The child lifecycle is a closed state machine: new -> derived -> open -> closed | failed.

A terminal state is final. Every record_child_* call refuses a transition its current state does
not allow, without journaling anything, and a journal whose history contains such a transition is
refused by every consumer — fold consumers, acquire, load and bind — before anything is appended
or dispatched.
"""

from __future__ import annotations

import unittest

from story_authority_support import StoryCase, story


class ChildLifecycleCase(StoryCase):

    def derive(self, auth: story.StoryAuthority, child_id: str = "B013") -> dict:
        proposal = story.derive_child_proposal(
            authority=auth, child_batch_id=child_id, action_items=[], previous_child_id=None,
            model_call_budget=2, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)
        auth.record_child_derived(proposal, story.verify_derivation(auth, proposal))
        return proposal

    def open(self, auth: story.StoryAuthority, child_id: str = "B013") -> dict:
        return auth.record_child_open(child_id, branch="main", head_commit=self.governance_base,
                                      tree=self.git.tree())

    def close(self, auth: story.StoryAuthority, child_id: str = "B013") -> dict:
        return auth.record_child_closed(
            child_batch_id=child_id, governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.governance_base, checker_reviewed_tree=self.git.tree(),
            functional_checkpoint_commit=self.governance_base, functional_checkpoint_tree=self.git.tree(),
            checker_verdict="changes_requested", unresolved_action_items=[self.patch_item("R5")])

    def fail(self, auth: story.StoryAuthority, child_id: str = "B013") -> dict:
        return auth.record_child_failed(child_id, reason="unrecoverable_harness_failure", detail="adapter died")

    def journal_bytes(self, auth: story.StoryAuthority) -> bytes:
        return auth.journal.path.read_bytes()

    def assert_refused(self, auth: story.StoryAuthority, action, *, state: str, expected: str) -> story.HardStop:
        """The transition is refused as state_integrity and the journal is left byte-for-byte untouched."""
        before = self.journal_bytes(auth)
        with self.assertRaises(story.HardStop) as raised:
            action()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("child_lifecycle", raised.exception.detail)
        self.assertEqual(raised.exception.evidence.get("state"), state)
        self.assertEqual(raised.exception.evidence.get("expected"), expected)
        self.assertEqual(self.journal_bytes(auth), before, "a refused transition must not journal anything")
        return raised.exception


class ChildTransitionTest(ChildLifecycleCase):

    def test_the_legal_lifecycle_is_accepted(self) -> None:
        auth = self.authority()
        self.derive(auth)
        self.assertEqual(auth.state.child_state("B013"), "derived")
        self.open(auth)
        self.assertEqual(auth.state.child_state("B013"), "open")
        self.close(auth)
        self.assertEqual(auth.state.child_state("B013"), "closed")
        self.assertEqual(auth.state.lifecycle_violations, [])

        other = self.authority(self.frozen_authority(authority_id="A021"))
        self.derive(other)
        self.open(other)
        self.fail(other)
        self.assertEqual(other.state.child_state("B013"), "failed")

    def test_open_requires_a_derived_child(self) -> None:
        auth = self.authority()
        self.assert_refused(auth, lambda: self.open(auth, "B404"), state="new", expected="derived")
        self.derive(auth)
        self.open(auth)
        stop = self.assert_refused(auth, lambda: self.open(auth), state="open", expected="derived")
        self.assertIn("new -> derived -> open -> closed|failed", stop.detail)

    def test_a_closed_or_failed_child_is_never_reopened(self) -> None:
        closed = self.authority()
        self.derive(closed)
        self.open(closed)
        self.close(closed)
        stop = self.assert_refused(closed, lambda: self.open(closed), state="closed", expected="derived")
        self.assertIn("a terminal state is final", stop.detail)

        failed = self.authority(self.frozen_authority(authority_id="A022"))
        self.derive(failed)
        self.open(failed)
        self.fail(failed)
        stop = self.assert_refused(failed, lambda: self.open(failed), state="failed", expected="derived")
        self.assertIn("a terminal state is final", stop.detail)

    def test_a_second_terminal_state_is_refused(self) -> None:
        closed = self.authority()
        self.derive(closed)
        self.open(closed)
        self.close(closed)
        self.assert_refused(closed, lambda: self.close(closed), state="closed", expected="open")
        self.assert_refused(closed, lambda: self.fail(closed), state="closed", expected="open")
        self.assertEqual(closed.state.consecutive_failures, 0)

        failed = self.authority(self.frozen_authority(authority_id="A023"))
        self.derive(failed)
        self.open(failed)
        self.fail(failed)
        self.assertEqual(failed.state.consecutive_failures, 1)
        self.assert_refused(failed, lambda: self.fail(failed), state="failed", expected="open")
        self.assert_refused(failed, lambda: self.close(failed), state="failed", expected="open")
        # The streak counts the one terminal state, never a refused second one.
        self.assertEqual(failed.state.consecutive_failures, 1)

    def test_closing_or_failing_an_unknown_or_unopened_child_is_refused(self) -> None:
        auth = self.authority()
        self.assert_refused(auth, lambda: self.close(auth, "B404"), state="new", expected="open")
        self.assert_refused(auth, lambda: self.fail(auth, "B404"), state="new", expected="open")
        self.derive(auth)
        self.assert_refused(auth, lambda: self.close(auth), state="derived", expected="open")
        self.assert_refused(auth, lambda: self.fail(auth), state="derived", expected="open")
        self.assertEqual(auth.state.child_state("B013"), "derived")
        self.assertEqual(sorted(auth.state.children), ["B013"])


class TamperedLifecycleHistoryTest(ChildLifecycleCase):
    """A journal with an intact hash chain but an impossible history is still refused.

    Each history below is appended through the journal itself, so every line links correctly: the
    only thing wrong with it is the lifecycle it records, which only the state machine can see.
    """

    def forge(self, auth: story.StoryAuthority, name: str) -> None:
        if name != "open_unknown":
            self.derive(auth)
        append = auth.journal.append
        common = {"authority_id": auth.authority_id, "child_batch_id": "B013"}
        opened = {**common, "branch": "main", "head_commit": self.governance_base, "tree": self.git.tree()}
        closure = {**common, "governance_base_commit": self.governance_base,
                   "checker_reviewed_commit": self.governance_base, "checker_reviewed_tree": self.git.tree(),
                   "functional_checkpoint_commit": self.governance_base,
                   "functional_checkpoint_tree": self.git.tree(), "checker_verdict": "approved",
                   "unresolved_action_items": [], "unresolved_action_items_digest": "", "made_progress": True}
        failure = {**common, "reason": "stopped", "detail": ""}
        if name == "open_unknown":
            append("child_open", **opened)
        elif name == "close_without_open":
            append("child_closed", **closure)
        elif name == "reopen_closed":
            append("child_open", **opened)
            append("child_closed", **closure)
            append("child_open", **opened)
        elif name == "reopen_failed":
            append("child_open", **opened)
            append("child_failed", **failure)
            append("child_open", **opened)
        elif name == "double_close":
            append("child_open", **opened)
            append("child_closed", **closure)
            append("child_closed", **closure)
        elif name == "fail_after_close":
            append("child_open", **opened)
            append("child_closed", **closure)
            append("child_failed", **failure)
        elif name == "rederived":
            append("child_derived", **common, granted_model_calls=2)
        else:  # pragma: no cover - a misspelt scenario must not pass silently
            raise AssertionError(name)

    SCENARIOS = ("open_unknown", "close_without_open", "reopen_closed", "reopen_failed", "double_close",
                 "fail_after_close", "rederived")

    def test_every_consumer_fails_closed_without_appending_or_dispatching(self) -> None:
        for index, name in enumerate(self.SCENARIOS):
            with self.subTest(name):
                envelope = self.frozen_authority(authority_id=f"A03{index}")
                writer = self.authority(envelope)
                self.forge(writer, name)

                folded = writer.journal.fold()
                self.assertEqual(folded.invalid_lines, 0, "the hash chain itself is intact")
                self.assertTrue(folded.lifecycle_violations, "fold must detect the impossible history")
                self.assertIn("B013", {v["child_batch_id"] for v in folded.lifecycle_violations})
                before = writer.journal.path.read_bytes()

                reader = self.authority(envelope, acquire=False)
                with self.assertRaises(story.HardStop) as refolded:
                    reader.refold()
                self.assertEqual(refolded.exception.reason, "state_integrity")
                self.assertIn("new -> derived -> open -> closed|failed", refolded.exception.detail)

                with self.assertRaises(story.HardStop) as loaded:
                    reader.load_child_derivation("B013")
                self.assertEqual(loaded.exception.reason, "state_integrity")

                # The lease holder is refused exactly like everyone else: holding the lease never
                # makes an impossible history usable.
                dispatched: list[str] = []
                with self.assertRaises(story.HardStop):
                    story.budgeted_authority_dispatch(
                        writer, child_batch_id="B013", logical_call_id="B013-maker-r01", role="maker",
                        phase="implementation", dispatch=lambda attempt: dispatched.append(attempt) or {})
                with self.assertRaises(story.HardStop):
                    writer.record_child_failed("B013", reason="stopped")
                with self.assertRaises(story.HardStop):
                    writer.hard_stop("protected_path_violation", "must not be appended to a forged history")
                writer.release()

                # R22: a refused acquire keeps no lease, so a second one meets the history, not the lock.
                for _attempt in range(2):
                    with self.assertRaises(story.HardStop) as acquired:
                        reader.acquire()
                    self.assertEqual(acquired.exception.reason, "state_integrity")
                    self.assertIsNone(reader._lease)
                self.assertEqual(dispatched, [], "nothing may be dispatched under an untrustworthy history")
                self.assertEqual(writer.journal.path.read_bytes(), before, "nothing may be appended to it")

    def test_a_broken_hash_chain_is_refused_by_refold_too(self) -> None:
        auth = self.authority()
        self.derive(auth)
        self.open(auth)
        auth.release()
        lines = auth.journal.path.read_text(encoding="utf-8").splitlines()
        derived = next(i for i, line in enumerate(lines) if '"kind":"child_derived"' in line)
        self.assertLess(derived, len(lines) - 1, "the edited line must have a successor that links to it")
        lines[derived] = lines[derived].replace('"granted_model_calls":2', '"granted_model_calls":9')
        auth.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(story.HardStop) as raised:
            auth.refold()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("hash chain", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
