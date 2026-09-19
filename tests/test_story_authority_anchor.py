#!/usr/bin/env python3
"""R14. The authority journal tail is anchored outside the working tree.

The in-file hash chain protects a line only through its successor: the last line could be
rewritten, keeping its `prev`, with zero invalid lines. The tail is therefore anchored in the
repository's ref store (`refs/tl/story-authorities/<authority_id>/journal-head`), moved by
compare-and-swap before every append. Every counterproof below runs against a real git repository.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from story_authority_support import StoryCase, story


def completed(_attempt: str) -> dict:
    return {"state": "completed"}


class AnchorCase(StoryCase):

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

    def ref(self, auth: story.StoryAuthority) -> str:
        return story.journal_anchor_ref(auth.authority_id)

    def ref_oid(self, auth: story.StoryAuthority) -> str:
        return self.git("rev-parse", "--verify", "-q", self.ref(auth), check=False)

    def receipt(self, auth: story.StoryAuthority) -> dict:
        return json.loads(self.git("cat-file", "blob", self.ref_oid(auth)))

    def lines(self, auth: story.StoryAuthority) -> list[str]:
        return auth.journal.path.read_text(encoding="utf-8").splitlines()

    def rewrite_line(self, auth: story.StoryAuthority, index: int, mutate) -> None:
        """Edit one event and re-serialize it canonically, keeping its `prev` link intact."""
        lines = self.lines(auth)
        event = json.loads(lines[index])
        mutate(event)
        lines[index] = story.canonical_json(event)
        auth.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def snapshot(self, auth: story.StoryAuthority) -> tuple[bytes, str]:
        path = auth.journal.path
        return (path.read_bytes() if path.exists() else b""), self.ref_oid(auth)

    def assert_anchor_refusal(self, action, marker: str = story.ANCHOR_DIVERGENT) -> story.HardStop:
        with self.assertRaises(story.HardStop) as raised:
            action()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn(marker, raised.exception.detail)
        return raised.exception


class AnchoredHeadTest(AnchorCase):

    def test_authority_open_creates_the_anchor_outside_the_working_tree(self) -> None:
        auth = self.authority(self.frozen_authority())
        self.assertEqual(self.git("for-each-ref", "--format=%(refname) %(objecttype)", "refs/tl/"),
                         f"{self.ref(auth)} blob")
        receipt = self.receipt(auth)
        [line] = self.lines(auth)
        self.assertEqual(receipt["seq"], 1)
        self.assertEqual(receipt["line"], line)
        self.assertEqual(json.loads(line)["kind"], "authority_open")
        self.assertEqual(receipt["authority_id"], auth.authority_id)
        self.assertEqual(receipt["root_authority_digest"], auth.root_digest)
        self.assertEqual(receipt["anchor_ref"], self.ref(auth))
        self.assertEqual(receipt["prev_chain_digest"], auth.journal.anchor.seed)
        # The anchor is repository state, never tree content: nothing under the work tree holds it.
        self.assertNotIn("journal-head", self.git("ls-files", "--others", "--cached"))

    def test_every_append_moves_the_anchor_to_the_new_tail(self) -> None:
        auth = self.authority(self.frozen_authority())
        story.budgeted_authority_dispatch(auth, child_batch_id="B013", logical_call_id="c0", role="maker",
                                          phase="implementation", dispatch=completed)
        receipt = self.receipt(auth)
        lines = self.lines(auth)
        self.assertEqual(receipt["seq"], len(lines))
        self.assertEqual(receipt["line"], lines[-1])
        self.assertEqual(json.loads(lines[-1])["kind"], "model_call_consumed")


class TailTamperTest(AnchorCase):
    """(1)-(3): the last line, rewritten with its `prev` intact, is refused by every consumer."""

    SCENARIOS = {
        # scenario: (history builder, last event kind, mutation of the last event)
        "authority_open": (lambda case, auth: None, "authority_open",
                           lambda event: event.__setitem__("global_model_call_budget", 99)),
        "child_open": (lambda case, auth: (case.derive(auth), case.open(auth)), "child_open",
                       lambda event: event.__setitem__("head_commit", "f" * 40)),
        "model_call_consumed": (
            lambda case, auth: story.budgeted_authority_dispatch(
                auth, child_batch_id="B013", logical_call_id="c0", role="maker", phase="implementation",
                dispatch=completed),
            "model_call_consumed", lambda event: event.__setitem__("outcome", "released")),
        "model_call_released": (
            lambda case, auth: story.budgeted_authority_dispatch(
                auth, child_batch_id="B013", logical_call_id="c0", role="maker", phase="implementation",
                dispatch=lambda _a: {"state": "released", "proof": "never started"}),
            "model_call_released", lambda event: event.__setitem__("outcome", "consumed")),
    }

    def test_tail_tamper_is_refused_by_refold_acquire_load_reserve_dispatch_and_append(self) -> None:
        for index, (name, (build, kind, mutate)) in enumerate(self.SCENARIOS.items()):
            with self.subTest(name):
                envelope = self.frozen_authority(authority_id=f"A04{index}")
                writer = self.authority(envelope)
                build(self, writer)
                writer.release()
                self.assertEqual(json.loads(self.lines(writer)[-1])["kind"], kind)
                # A live lease holder, as the runtime is while its worker runs, sees the tail rewritten
                # under it. Holding the lease never makes a rewritten tail usable.
                holder = self.authority(envelope)
                self.rewrite_line(writer, -1, mutate)
                # The in-file chain alone is blind to this: the edited line has no successor.
                self.assertEqual(writer.journal.fold().invalid_lines, 0)
                before = self.snapshot(writer)

                reader = self.authority(envelope, acquire=False)
                self.assert_anchor_refusal(reader.refold)

                self.assert_anchor_refusal(lambda: holder.load_child_derivation("B013"))
                self.assert_anchor_refusal(lambda: holder.reserve_call(
                    logical_call_id="c9", global_attempt_id=f"{holder.authority_id}-attempt-900",
                    child_batch_id="B013"))
                dispatched: list[str] = []
                self.assert_anchor_refusal(lambda: story.budgeted_authority_dispatch(
                    holder, child_batch_id="B013", logical_call_id="c9", role="maker", phase="implementation",
                    dispatch=lambda attempt: dispatched.append(attempt) or {}))
                self.assert_anchor_refusal(lambda: holder.record_child_failed("B013", reason="stopped"))
                self.assert_anchor_refusal(lambda: holder.hard_stop("protected_path_violation", "not on a forged tail"))
                self.assert_anchor_refusal(lambda: holder.journal.append(
                    "hard_stop", authority_id=holder.authority_id, reason="direct", detail="", evidence={}))
                holder.release()

                # R22: a refused acquire keeps no lease, so the next one meets the anchor, not the lock.
                for _attempt in range(2):
                    fresh = self.authority(envelope, acquire=False)
                    self.assert_anchor_refusal(fresh.acquire)
                    self.assertIsNone(fresh._lease)
                self.assertEqual(dispatched, [], "nothing may be dispatched on a tampered tail")
                self.assertEqual(self.snapshot(writer), before, "neither the journal nor the anchor moved")

    def test_intermediate_tamper_still_breaks_the_chain_and_the_anchor(self) -> None:
        """(4)"""
        auth = self.authority(self.frozen_authority())
        self.derive(auth)
        self.open(auth)
        auth.release()
        lines = self.lines(auth)
        derived = next(i for i, line in enumerate(lines) if '"kind":"child_derived"' in line)
        self.assertLess(derived, len(lines) - 1)
        self.rewrite_line(auth, derived, lambda event: event.__setitem__("granted_model_calls", 9))
        stop = self.assert_anchor_refusal(auth.refold)
        self.assertIn("hash chain", stop.detail)
        fresh = self.authority(auth.envelope, acquire=False)
        self.assert_anchor_refusal(fresh.acquire)
        fresh.release()

    def test_dropping_the_tail_restores_it_from_the_anchor_never_from_the_file(self) -> None:
        """A removed last line is the anchored event, so it comes back exactly as anchored."""
        auth = self.authority(self.frozen_authority())
        story.budgeted_authority_dispatch(auth, child_batch_id="B013", logical_call_id="c0", role="maker",
                                          phase="implementation", dispatch=completed)
        auth.release()
        original = self.lines(auth)
        auth.journal.path.write_text("\n".join(original[:-1]) + "\n", encoding="utf-8")
        restored = self.authority(auth.envelope)
        self.assertEqual(self.lines(restored), original)
        self.assertEqual(restored.state.consumed_calls, 1)


class AnchorPresenceTest(AnchorCase):
    """(5): an absent, divergent or unreadable anchor fails closed; nothing re-creates it."""

    def test_missing_anchor_under_a_non_empty_journal_fails_closed_and_is_never_recreated(self) -> None:
        auth = self.authority(self.frozen_authority())
        self.derive(auth)
        auth.release()
        self.git("update-ref", "-d", self.ref(auth))
        before = self.snapshot(auth)
        self.assertEqual(before[1], "")
        self.assert_anchor_refusal(auth.refold)
        fresh = self.authority(auth.envelope, acquire=False)
        self.assert_anchor_refusal(fresh.acquire)
        self.addCleanup(fresh.release)
        self.assert_anchor_refusal(lambda: fresh.journal.append(
            "hard_stop", authority_id=fresh.authority_id, reason="direct", detail="", evidence={}))
        self.assertEqual(self.snapshot(auth), before, "no anchor is bootstrapped from the journal tail")

    def test_divergent_anchor_objects_fail_closed(self) -> None:
        auth = self.authority(self.frozen_authority())
        self.derive(auth)
        auth.release()
        ref, genuine = self.ref(auth), self.ref_oid(auth)
        lines = self.lines(auth)
        tampered_line = json.loads(lines[-1])
        tampered_line["granted_model_calls"] = 9
        forged = auth.journal.anchor.receipt(len(lines), story.canonical_json(tampered_line),
                                             self.receipt(auth)["prev_chain_digest"])

        def blob(content: str) -> str:
            path = self.root / "forged-object"
            path.write_text(content, encoding="utf-8")
            self.addCleanup(lambda: path.unlink(missing_ok=True))
            return self.git("hash-object", "-w", str(path))

        variants = {
            "random_blob": lambda: self.git("update-ref", ref, blob("not a receipt")),
            "commit_object": lambda: self.git("update-ref", ref, self.governance_base),
            "well_formed_receipt_for_another_line": lambda: self.git(
                "update-ref", ref, blob(story.canonical_json(forged))),
            "non_canonical_copy_of_the_genuine_receipt": lambda: self.git(
                "update-ref", ref, blob(json.dumps(self.receipt(auth), indent=1))),
            "symbolic_ref_to_the_genuine_receipt": lambda: (
                self.git("update-ref", "refs/tl/elsewhere", genuine),
                self.git("symbolic-ref", ref, "refs/tl/elsewhere")),
        }
        journal = auth.journal.path.read_bytes()
        for name, install in variants.items():
            with self.subTest(name):
                install()
                self.assert_anchor_refusal(auth.refold)
                fresh = self.authority(auth.envelope, acquire=False)
                self.assert_anchor_refusal(fresh.acquire)
                fresh.release()
                self.assertEqual(auth.journal.path.read_bytes(), journal)
                self.git("update-ref", "--no-deref", ref, genuine)
                auth.refold()  # the genuine anchor verifies again: only the anchor was at fault

    def test_unavailable_anchor_mechanism_fails_closed(self) -> None:
        envelope = self.frozen_authority()
        runtime = lambda root: root / story.RUNTIME_AUTHORITY_DIR / "A001"  # noqa: E731
        outside = tempfile.TemporaryDirectory(prefix="tl-anchor-no-git-")
        self.addCleanup(outside.cleanup)
        plain = Path(outside.name).resolve()
        cases = {
            "no_repository": lambda: story.StoryAuthority(envelope, runtime(self.root)),
            "not_a_git_repository": lambda: story.StoryAuthority(envelope, runtime(plain), repo=plain),
            # A subdirectory would let git discover the enclosing repository and anchor there.
            "not_the_work_tree_root": lambda: story.StoryAuthority(
                envelope, runtime(self.root / "src"), repo=self.root / "src"),
        }
        for name, build in cases.items():
            with self.subTest(name):
                auth = build()
                self.assert_anchor_refusal(auth.acquire, story.ANCHOR_UNAVAILABLE)
                auth.release()
                self.assertFalse(auth.journal.path.exists(), "nothing is journaled without an anchor")
        with self.subTest("git_not_executable"):
            auth = self.authority(envelope, acquire=False)
            with mock.patch.dict(os.environ, {"PATH": ""}):
                self.assert_anchor_refusal(auth.acquire, story.ANCHOR_UNAVAILABLE)
            auth.release()
            self.assertFalse(auth.journal.path.exists())
        self.assertEqual(self.git("for-each-ref", "refs/tl/"), "", "no anchor landed anywhere")


class CrossAuthorityTest(AnchorCase):
    """(6) and (8): another authority's anchor, or this authority's older one, does not serve."""

    def test_anchor_of_another_authority_does_not_verify(self) -> None:
        first = self.authority(self.frozen_authority(authority_id="A001"))
        second = self.authority(self.frozen_authority(authority_id="A002"))
        self.derive(second)
        first.release()
        second.release()
        self.assertNotEqual(self.ref(first), self.ref(second))

        self.git("update-ref", self.ref(first), self.ref_oid(second))
        stop = self.assert_anchor_refusal(first.refold)
        self.assertIn("anchor_ref", stop.detail)

        # Replaying the other authority's journal together with its anchor does not serve either.
        first.journal.path.write_bytes(second.journal.path.read_bytes())
        self.assert_anchor_refusal(first.refold)
        second.refold()  # the other authority is untouched

    def test_rolled_back_anchor_fails_closed_and_is_not_moved_forward(self) -> None:
        auth = self.authority(self.frozen_authority())
        opened = self.ref_oid(auth)
        story.budgeted_authority_dispatch(auth, child_batch_id="B013", logical_call_id="c0", role="maker",
                                          phase="implementation", dispatch=completed)
        auth.release()
        self.git("update-ref", self.ref(auth), opened)
        before = self.snapshot(auth)
        self.assert_anchor_refusal(auth.refold)
        fresh = self.authority(auth.envelope, acquire=False)
        self.assert_anchor_refusal(fresh.acquire)
        self.addCleanup(fresh.release)
        self.assert_anchor_refusal(lambda: fresh.journal.append(
            "hard_stop", authority_id=fresh.authority_id, reason="direct", detail="", evidence={}))
        self.assertEqual(self.snapshot(auth), before, "the journal is never trusted beyond its anchor")


class CompareAndSwapTest(AnchorCase):
    """(8): the anchor moves only from the head the writer verified."""

    def race(self, loser: story.StoryAuthority, winner_append) -> None:
        """Let another writer append between the loser's verification and its compare-and-swap."""
        publish = loser.journal.anchor.publish

        def racing(receipt: dict, expected: str | None) -> str:
            winner_append()
            return publish(receipt, expected)

        loser.journal.anchor.publish = racing  # type: ignore[method-assign]

    def test_a_second_writer_cannot_move_the_anchor_from_a_stale_head(self) -> None:
        envelope = self.frozen_authority()
        holder = self.authority(envelope)
        peer = self.authority(envelope, acquire=False)
        self.race(holder, lambda: peer.journal.append(
            "hard_stop", authority_id=peer.authority_id, reason="peer_writer", detail="", evidence={}))
        stop = self.assert_anchor_refusal(lambda: holder.reserve_call(
            logical_call_id="c0", global_attempt_id="A001-attempt-001", child_batch_id="B013"),
            story.ANCHOR_CONFLICT)
        self.assertIn("compare-and-swap", stop.detail)
        kinds = [json.loads(line)["kind"] for line in self.lines(holder)]
        self.assertEqual(kinds, ["authority_open", "hard_stop"], "the loser appended nothing")
        self.assertEqual(self.receipt(holder)["line"], self.lines(holder)[-1])
        state = holder.refold()
        self.assertEqual(state.attempts, {})
        self.assertEqual(state.remaining(holder.budget), holder.budget)

    def test_two_fresh_writers_cannot_both_create_the_anchor(self) -> None:
        envelope = self.frozen_authority()
        holder = self.authority(envelope, acquire=False)
        peer = self.authority(envelope, acquire=False)
        self.race(holder, lambda: peer.journal.append(
            "authority_open", authority_id=peer.authority_id, work_ref=peer.payload["work_ref"],
            root_authority_digest=peer.root_digest))
        self.assert_anchor_refusal(holder.acquire, story.ANCHOR_CONFLICT)
        self.addCleanup(holder.release)
        self.assertEqual(len(self.lines(holder)), 1)
        self.assertEqual(self.receipt(holder)["line"], self.lines(holder)[0])


class CrashConsistencyTest(AnchorCase):
    """(7): anchor ahead of the journal is completed from the anchored receipt, or fails closed."""

    def crash_after_anchor(self, action, torn: int | None = None) -> None:
        """Run `action` with the journal append dying after the anchor already moved."""
        def dying(journal: story.AuthorityJournal, data: bytes) -> None:
            if torn is not None:
                with open(journal.path, "ab") as handle:
                    handle.write(data[:torn])
            raise OSError("simulated crash before the append was durable")

        with mock.patch.object(story.AuthorityJournal, "_write", dying):
            with self.assertRaises(OSError):
                action()

    def test_crash_between_anchor_and_append_is_recovered_from_the_anchor(self) -> None:
        auth = self.authority(self.frozen_authority())
        self.crash_after_anchor(lambda: auth.reserve_call(
            logical_call_id="c0", global_attempt_id="A001-attempt-001", child_batch_id="B013"))
        auth.release()
        anchored = self.receipt(auth)
        self.assertEqual(json.loads(anchored["line"])["kind"], "model_call_reserved")
        self.assertEqual(len(self.lines(auth)), 1, "the append never landed")

        # A reader already accounts the anchored reservation, without writing anything.
        reader = self.authority(auth.envelope, acquire=False)
        self.assertEqual(reader.refold().open_reservations, 1)
        self.assertEqual(len(self.lines(auth)), 1)

        resumed = self.authority(auth.envelope)
        self.assertEqual(self.lines(resumed)[-1], anchored["line"])
        self.assertEqual(len(self.lines(resumed)), 2)
        self.assertEqual(resumed.journal.fold().invalid_lines, 0)
        self.assertEqual(resumed.remaining_global_budget, resumed.budget - 1, "the slot stays held")
        resumed.consume_call("A001-attempt-001")
        self.assertEqual(resumed.state.consumed_calls, 1)

    def test_torn_append_is_completed_from_the_anchor(self) -> None:
        auth = self.authority(self.frozen_authority())
        self.derive(auth)
        self.crash_after_anchor(lambda: self.open(auth), torn=20)
        auth.release()
        self.assertFalse(auth.journal.path.read_bytes().endswith(b"\n"))
        resumed = self.authority(auth.envelope)
        self.assertEqual(self.lines(resumed)[-1], self.receipt(resumed)["line"])
        self.assertTrue(resumed.journal.path.read_bytes().endswith(b"\n"))
        self.assertEqual(resumed.state.child_state("B013"), "open")
        self.assertEqual(sum('"kind":"child_open"' in line for line in self.lines(resumed)), 1)

    def test_crash_during_authority_open_is_recovered_from_the_anchor(self) -> None:
        envelope = self.frozen_authority()
        first = self.authority(envelope, acquire=False)
        self.crash_after_anchor(first.acquire)
        first.release()
        self.assertFalse(first.journal.path.exists())
        resumed = self.authority(envelope)
        self.assertTrue(resumed.state.opened)
        self.assertEqual([json.loads(line)["kind"] for line in self.lines(resumed)], ["authority_open"])

    def test_anchor_ahead_that_does_not_continue_the_journal_fails_closed(self) -> None:
        def tamper_tail(auth):
            self.rewrite_line(auth, -1, lambda event: event.__setitem__("granted_model_calls", 9))

        def drop_one_more(auth):
            lines = self.lines(auth)
            auth.journal.path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

        def foreign_fragment(auth):
            with open(auth.journal.path, "ab") as handle:
                handle.write(b'{"forged":')

        for index, (name, damage) in enumerate({"tampered_predecessor": tamper_tail,
                                                "journal_two_behind": drop_one_more,
                                                "torn_fragment_not_from_the_anchor": foreign_fragment}.items()):
            with self.subTest(name):
                envelope = self.frozen_authority(authority_id=f"A06{index}")
                auth = self.authority(envelope)
                self.derive(auth)
                self.crash_after_anchor(lambda: self.open(auth))
                auth.release()
                damage(auth)
                before = self.snapshot(auth)
                self.assert_anchor_refusal(auth.refold)
                fresh = self.authority(envelope, acquire=False)
                self.assert_anchor_refusal(fresh.acquire)
                fresh.release()
                self.assertEqual(self.snapshot(auth), before, "nothing was recovered or appended")


if __name__ == "__main__":
    unittest.main()
