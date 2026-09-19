#!/usr/bin/env python3
"""R11. The child lifecycle is derived -> open -> closed | failed, enforced by the authority itself.

Every refused transition leaves the journal byte for byte as it was: no lifecycle event, no
hard_stop, no reservation. A journal that already carries an illegal transition (written by
hand, by an older writer, or by anything that bypassed these methods) is refused on refold,
wherever the refold happens, not only when the lease is first taken.
"""

from __future__ import annotations

import unittest

from story_authority_support import StoryCase, story


class ChildLifecycleTest(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.auth = self.authority(self.baseline_authority())
        self.commit, self.tree = self.git.head(), self.git.tree()

    # ---- helpers ------------------------------------------------------------------------

    def derive(self, child_id: str = "B013") -> None:
        proposal = story.derive_child_proposal(
            authority=self.auth, child_batch_id=child_id, action_items=[], previous_child_id=None,
            model_call_budget=2, governance_base_commit=self.commit, story_baseline_commit=self.commit)
        self.auth.record_child_derived(proposal, story.verify_derivation(self.auth, proposal))

    def open(self, child_id: str = "B013") -> dict:
        return self.auth.record_child_open(child_id, branch="main", head_commit=self.commit, tree=self.tree)

    def close(self, child_id: str = "B013") -> dict:
        return self.auth.record_child_closed(
            child_batch_id=child_id, governance_base_commit=self.commit, checker_reviewed_commit=self.commit,
            checker_reviewed_tree=self.tree, functional_checkpoint_commit=self.commit,
            functional_checkpoint_tree=self.tree, checker_verdict="changes_requested",
            unresolved_action_items=[self.patch_item("R5")])

    def fail(self, child_id: str = "B013") -> dict:
        return self.auth.record_child_failed(child_id, reason="unrecoverable_harness_failure", detail="x")

    def journal_bytes(self) -> bytes:
        return self.auth.journal.path.read_bytes()

    def assert_refused_without_effect(self, action, fragment: str) -> story.HardStop:
        before = self.journal_bytes()
        consumed = self.auth.state.consumed_calls
        with self.assertRaises(story.HardStop) as raised:
            action()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn(fragment, raised.exception.detail)
        self.assertEqual(self.journal_bytes(), before, "a refused transition must not journal anything")
        self.auth.refold()
        self.assertEqual(self.auth.state.consumed_calls, consumed)
        self.assertEqual(self.auth.state.open_reservations, 0)
        return raised.exception

    def forge(self, kind: str, **payload) -> None:
        """Append a correctly hash-chained event that bypasses the lifecycle methods."""
        journal = story.AuthorityJournal(self.auth.journal.path)
        journal.fold()
        journal.append(kind, authority_id=self.auth.authority_id, **payload)

    # ---- the one legal path ---------------------------------------------------------------

    def test_derived_open_closed_and_derived_open_failed_are_the_legal_paths(self) -> None:
        self.derive()
        self.assertEqual(self.auth.state.children["B013"]["state"], "derived")
        self.open()
        self.assertEqual(self.auth.state.children["B013"]["state"], "open")
        self.close()
        self.assertEqual(self.auth.state.children["B013"]["state"], "closed")

        other = self.authority(self.frozen_authority(authority_id="A002"))
        self.auth = other
        self.derive("B013")
        self.open("B013")
        self.fail("B013")
        self.assertEqual(self.auth.state.children["B013"]["state"], "failed")

    # ---- unknown child ---------------------------------------------------------------------

    def test_unknown_child_cannot_open_close_or_fail(self) -> None:
        for action in (lambda: self.open("B999"), lambda: self.close("B999"), lambda: self.fail("B999")):
            self.assert_refused_without_effect(action, "never derived")
        for bogus in ("", None, 7):
            self.assert_refused_without_effect(
                lambda bogus=bogus: self.auth.record_child_failed(bogus, reason="x"), "names no child batch")

    # ---- out of order ----------------------------------------------------------------------

    def test_derived_child_cannot_terminate_without_opening(self) -> None:
        self.derive()
        self.assert_refused_without_effect(self.close, "requires state open")
        self.assert_refused_without_effect(self.fail, "requires state open")
        self.assertEqual(self.auth.state.children["B013"]["state"], "derived")

    def test_open_child_cannot_open_again(self) -> None:
        self.derive()
        self.open()
        self.assert_refused_without_effect(self.open, "in state open")

    # ---- terminal is terminal --------------------------------------------------------------

    def test_closed_child_cannot_reopen_close_again_or_fail(self) -> None:
        self.derive()
        self.open()
        self.close()
        for action in (self.open, self.close, self.fail):
            self.assert_refused_without_effect(action, "in state closed")
        closure = self.auth.state.closure_of("B013")
        self.assertEqual(closure["checker_verdict"], "changes_requested")
        self.assertEqual(self.auth.state.consecutive_failures, 0)

    def test_failed_child_cannot_reopen_fail_again_or_close(self) -> None:
        self.derive()
        self.open()
        self.fail()
        for action in (self.open, self.fail, self.close):
            self.assert_refused_without_effect(action, "in state failed")
        # The streak counted the failure once; a refused duplicate never re-counts it.
        self.assertEqual(self.auth.state.consecutive_failures, 1)

    def test_derived_child_cannot_be_derived_again(self) -> None:
        self.derive()
        with self.assertRaises(story.HardStop) as raised:
            self.derive()
        self.assertEqual(raised.exception.reason, "state_integrity")

    # ---- a journal that carries an illegal transition is refused on refold -----------------

    def test_forged_illegal_transitions_are_refused_on_refold_and_bind(self) -> None:
        forgeries = {
            "reopen_closed": ("closed", "child_open", {"branch": "main", "head_commit": "0" * 40, "tree": "0" * 40}),
            "reopen_failed": ("failed", "child_open", {"branch": "main", "head_commit": "0" * 40, "tree": "0" * 40}),
            "double_close": ("closed", "child_closed", {"made_progress": True}),
            "double_fail": ("failed", "child_failed", {"reason": "x"}),
            "fail_after_close": ("closed", "child_failed", {"reason": "x"}),
            "close_unopened": ("derived", "child_closed", {"made_progress": True}),
            "unknown_child": (None, "child_failed", {"reason": "x"}),
        }
        for index, (name, (reach, kind, payload)) in enumerate(forgeries.items()):
            with self.subTest(name):
                self.auth = self.authority(self.frozen_authority(authority_id=f"A{100 + index}"))
                child = "B013"
                if reach is not None:
                    self.derive(child)
                if reach in {"closed", "failed"}:
                    self.open(child)
                    (self.close if reach == "closed" else self.fail)(child)
                target = child if reach is not None else "B777"
                self.forge(kind, child_batch_id=target, **payload)
                before = self.journal_bytes()

                # The live holder refuses on its next refold, before any write.
                with self.assertRaises(story.HardStop) as raised:
                    self.auth.refold()
                self.assertEqual(raised.exception.reason, "state_integrity")
                self.assertIn("illegal child lifecycle", raised.exception.detail)
                with self.assertRaises(story.HardStop):
                    self.auth.reserve_call(logical_call_id="after-forgery", global_attempt_id="G-after",
                                           child_batch_id=child)
                with self.assertRaises(story.HardStop):
                    self.auth.load_child_derivation(child)
                self.assertEqual(self.journal_bytes(), before, "nothing is written onto an untrusted journal")

                # A fresh holder refuses to take the lease over it.
                self.auth.release()
                fresh = self.authority(acquire=False, envelope=self.auth.envelope)
                with self.assertRaises(story.HardStop) as reopened:
                    fresh.acquire()
                fresh.release()
                self.assertEqual(reopened.exception.reason, "state_integrity")
                self.assertEqual(self.journal_bytes(), before)

    def test_broken_hash_chain_is_refused_on_refold_mid_session(self) -> None:
        self.derive()
        self.open()
        # Inflate the derived grant; the edited line is linked from the child_open after it.
        lines = self.journal_bytes().decode("utf-8").splitlines()
        self.assertIn('"granted_model_calls":2', lines[-2])
        lines[-2] = lines[-2].replace('"granted_model_calls":2', '"granted_model_calls":9')
        self.auth.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        before = self.journal_bytes()
        for action in (self.close, self.fail, self.auth.refold):
            with self.assertRaises(story.HardStop) as raised:
                action()
            self.assertEqual(raised.exception.reason, "state_integrity")
            self.assertIn("hash chain", raised.exception.detail)
        self.assertEqual(self.journal_bytes(), before)


if __name__ == "__main__":
    unittest.main()
