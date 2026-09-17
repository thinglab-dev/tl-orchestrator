#!/usr/bin/env python3
"""D) Global accounting and physical attempts (T032 §2.3, §2.12, §2.14), counterfactuals 11-19."""

from __future__ import annotations

import json
import unittest

from story_authority_support import StoryCase, story

import tl_job  # noqa: E402


def completed(_attempt_id: str) -> dict:
    return {"state": "completed", "exit_code": 0}


def child_batch(max_model_calls: int = 8) -> dict:
    """A minimal in-memory child batch ledger, exactly as budgeted_model_dispatch mutates it."""
    return {
        "id": "B013", "status": "in_progress",
        "budget": {"max_model_calls": max_model_calls, "consumed_model_calls": 0,
                   "reserved_model_calls": 0, "max_rework_rounds_per_unit": 2, "max_advisor_calls": 0,
                   "consumed_advisor_calls": 0, "pending_call": None},
        "execution": {"stop_reason": None},
    }


class GlobalAccountingTest(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.envelope = self.frozen_authority()
        self.auth = self.authority(self.envelope)

    def second_runtime(self) -> story.StoryAuthority:
        return story.StoryAuthority(self.envelope, self.auth.runtime_dir, repo=self.root)

    # ---- 11. mutual exclusion -----------------------------------------------------------

    def test_two_runtimes_cannot_double_spend_parent_budget(self) -> None:
        other = self.second_runtime()
        with self.assertRaises(story.Refusal) as raised:
            other.acquire()
        self.assertIn("coordinator_conflict", str(raised.exception))
        self.assertEqual(raised.exception.code, 5)

        # Without the lease no reservation is even attempted, so the balance cannot be read stale.
        with self.assertRaises(story.Refusal):
            other.reserve_call(logical_call_id="B013-maker-r01", global_attempt_id="A001-attempt-001",
                               child_batch_id="B013")

        self.auth.reserve_call(logical_call_id="B013-maker-r01", global_attempt_id="A001-attempt-001",
                               child_batch_id="B013")
        self.auth.consume_call("A001-attempt-001")
        self.assertEqual(self.auth.remaining_global_budget, 13)

        # Only after the holder releases can the other instance take over, and it reads one spend.
        self.auth.release()
        other.acquire()
        self.addCleanup(other.release)
        self.assertEqual(other.state.consumed_calls, 1)
        self.assertEqual(other.remaining_global_budget, 13)

    def test_budget_exhaustion_refuses_the_reservation_before_any_effect(self) -> None:
        small = self.authority(self.frozen_authority(authority_id="A005", global_model_call_budget=2))
        for index in range(2):
            story.budgeted_authority_dispatch(small, child_batch_id="B013",
                                              logical_call_id=f"call-{index}", role="maker",
                                              phase="implementation", dispatch=completed)
        self.assertEqual(small.remaining_global_budget, 0)
        with self.assertRaises(story.HardStop) as raised:
            story.budgeted_authority_dispatch(small, child_batch_id="B013", logical_call_id="call-2",
                                              role="maker", phase="implementation", dispatch=completed)
        self.assertEqual(raised.exception.reason, "model_call_budget_exhausted")
        self.assertEqual(small.state.consumed_calls, 2)

    # ---- 12-15. one charge across two ledgers -------------------------------------------

    def test_cross_ledger_call_is_counted_exactly_once(self) -> None:
        batch = child_batch()
        context = story.AuthorityDispatchContext(self.auth, "B013", "B013-maker-r01")
        ok, reason, detail = tl_job.budgeted_model_dispatch(
            batch_input=batch, role="maker", phase="implementation", call_id="B013-maker-r01",
            harness_cmd=["echo", "maker"], runner_fn=lambda _cmd, _cwd: (0, "", ""),
            authority_context=context)
        self.assertTrue(ok, reason)
        self.assertEqual(self.auth.refold().consumed_calls, 1)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])
        # One physical attempt, one id, one charge — in both ledgers.
        projection = self.auth.child_budget_projection("B013")
        self.assertEqual(projection["consumed_model_calls"], 1)
        self.assertEqual(projection["global_attempt_ids"], [context.global_attempt_id])
        self.assertEqual(self.auth.remaining_global_budget, 13)

    def test_crash_between_parent_and_child_reservation_does_not_double_debit(self) -> None:
        batch = child_batch()
        context = story.AuthorityDispatchContext(self.auth, "B013", "B013-maker-r01")
        context.reserve(role="maker", phase="implementation", payload_digest="sha256:deadbeef")
        # Crash here: the authority holds the reservation, the child ledger never learned about it.
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertEqual(self.auth.refold().open_reservations, 1)
        self.assertEqual(self.auth.remaining_global_budget, 13)

        settled = self.auth.reconcile_orphan_reservations("B013")
        self.assertEqual([record["state"] for record in settled], ["ambiguous"])
        self.assertEqual(self.auth.state.consumed_calls, 1)
        self.assertEqual(self.auth.remaining_global_budget, 13)

        self.auth.reconcile_child_batch(batch, "B013")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # Reconciling twice does not move the balance again.
        self.auth.reconcile_orphan_reservations("B013")
        self.auth.reconcile_child_batch(batch, "B013")
        self.assertEqual(self.auth.state.consumed_calls, 1)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)

    def test_ambiguous_global_call_is_consumed_once(self) -> None:
        self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id="A001-attempt-001",
                               child_batch_id="B013")
        self.auth.consume_call("A001-attempt-001", outcome="ambiguous")
        for _ in range(3):
            self.auth.consume_call("A001-attempt-001", outcome="ambiguous")
        self.assertEqual(self.auth.state.consumed_calls, 1)
        self.assertEqual(self.auth.state.attempts["A001-attempt-001"]["state"], "ambiguous")
        # A charged attempt is never released back into the budget.
        with self.assertRaises(story.Refusal):
            self.auth.release_call("A001-attempt-001", proof="claims it never started")
        self.assertEqual(self.auth.remaining_global_budget, 13)

    def test_child_budget_is_projection_of_parent_allocation(self) -> None:
        batch = child_batch()
        for index in range(3):
            story.budgeted_authority_dispatch(self.auth, child_batch_id="B013",
                                              logical_call_id=f"B013-call-{index}", role="maker",
                                              phase="implementation", dispatch=completed)
        # Whatever the child ledger claims, the authority journal decides.
        batch["budget"]["consumed_model_calls"] = 99
        batch["budget"]["reserved_model_calls"] = 7
        batch["budget"]["pending_call"] = {"call_id": "ghost", "role": "maker", "phase": "implementation"}
        self.auth.reconcile_child_batch(batch, "B013")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 3)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])
        self.assertEqual(self.auth.child_budget_projection("B013")["consumed_model_calls"], 3)
        # A second child's calls are attributed to that child, never to this one.
        story.budgeted_authority_dispatch(self.auth, child_batch_id="B014", logical_call_id="B014-call-0",
                                          role="maker", phase="rework", dispatch=completed)
        self.assertEqual(self.auth.child_budget_projection("B013")["consumed_model_calls"], 3)
        self.assertEqual(self.auth.child_budget_projection("B014")["consumed_model_calls"], 1)
        self.assertEqual(self.auth.state.consumed_calls, 4)

    def test_pre_dispatch_failure_releases_the_slot_in_both_ledgers(self) -> None:
        batch = child_batch()
        context = story.AuthorityDispatchContext(self.auth, "B013", "B013-maker-r01")
        ok, reason, _detail = tl_job.budgeted_model_dispatch(
            batch_input=batch, role="maker", phase="implementation", call_id="B013-maker-r01",
            harness_cmd=["echo", "maker"], runner_fn=lambda _c, _w: (0, "", ""),
            simulate_pre_dispatch_failure=True, authority_context=context)
        self.assertFalse(ok)
        self.assertEqual(reason, "PRE_DISPATCH_UNAVAILABLE")
        self.assertEqual(self.auth.refold().consumed_calls, 0)
        self.assertEqual(self.auth.state.attempts[context.global_attempt_id]["state"], "released")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 0)
        self.assertEqual(self.auth.remaining_global_budget, 14)

    def test_ambiguous_dispatch_charges_both_ledgers_once_and_stops(self) -> None:
        batch = child_batch()
        context = story.AuthorityDispatchContext(self.auth, "B013", "B013-checker-r01")
        ok, reason, _detail = tl_job.budgeted_model_dispatch(
            batch_input=batch, role="checker", phase="review", call_id="B013-checker-r01",
            harness_cmd=["echo", "checker"], runner_fn=lambda _c, _w: (0, "", ""),
            simulate_ambiguous_outcome=True, authority_context=context)
        self.assertFalse(ok)
        self.assertEqual(reason, "ambiguous_dispatch_stopped")
        self.assertEqual(batch["status"], "stopped")
        self.assertEqual(batch["execution"]["stop_reason"], "unrecoverable_harness_failure")
        self.assertEqual(self.auth.refold().consumed_calls, 1)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertEqual(self.auth.child_budget_projection("B013")["consumed_model_calls"], 1)

    # ---- 16-19. logical call versus physical attempt ------------------------------------

    def test_retry_uses_new_global_attempt_id(self) -> None:
        first = self.auth.next_global_attempt_id("B013-checker-r01")
        self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id=first,
                               child_batch_id="B013")
        self.auth.consume_call(first, outcome="ambiguous")

        with self.assertRaises(story.Refusal) as raised:
            self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id=first,
                                   child_batch_id="B013")
        self.assertIn("global_attempt_id_reuse", str(raised.exception))

        second = self.auth.next_global_attempt_id("B013-checker-r01")
        self.assertNotEqual(second, first)
        self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id=second,
                               child_batch_id="B013")
        self.auth.consume_call(second)
        # One logical call, two physical attempts, two distinct ids.
        attempts = self.auth.state.attempts
        self.assertEqual({a["logical_call_id"] for a in attempts.values()}, {"B013-checker-r01"})
        self.assertEqual(sorted(attempts), sorted([first, second]))

    def test_two_provider_attempts_consume_two_global_slots(self) -> None:
        for index in range(2):
            story.budgeted_authority_dispatch(self.auth, child_batch_id="B013",
                                              logical_call_id="B013-maker-r01", role="maker",
                                              phase="implementation", dispatch=completed)
        self.assertEqual(self.auth.state.consumed_calls, 2)
        self.assertEqual(self.auth.remaining_global_budget, 12)
        self.assertEqual(len(self.auth.state.attempts), 2)

    def test_replay_same_global_attempt_id_is_idempotent(self) -> None:
        dispatched: list[str] = []

        def record_dispatch(attempt_id: str) -> dict:
            dispatched.append(attempt_id)
            return {"state": "completed"}

        first = story.budgeted_authority_dispatch(
            self.auth, child_batch_id="B013", logical_call_id="B013-maker-r01", role="maker",
            phase="implementation", dispatch=record_dispatch)
        attempt_id = first["global_attempt_id"]
        self.assertEqual(dispatched, [attempt_id])

        for _ in range(3):
            replay = story.budgeted_authority_dispatch(
                self.auth, child_batch_id="B013", logical_call_id="B013-maker-r01", role="maker",
                phase="implementation", dispatch=record_dispatch, global_attempt_id=attempt_id)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["attempt_state"], "consumed")
        self.assertEqual(dispatched, [attempt_id], "the physical call must not run again on replay")
        self.assertEqual(self.auth.state.consumed_calls, 1)
        self.assertEqual(self.auth.remaining_global_budget, 13)

        # A reservation replayed before it settled holds the same slot rather than taking a second.
        held = self.auth.next_global_attempt_id("B013-checker-r01")
        self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id=held,
                               child_batch_id="B013", payload_digest="sha256:abc")
        self.auth.reserve_call(logical_call_id="B013-checker-r01", global_attempt_id=held,
                               child_batch_id="B013", payload_digest="sha256:abc")
        self.assertEqual(self.auth.state.open_reservations, 1)
        self.assertEqual(self.auth.remaining_global_budget, 12)

    def test_ambiguous_attempt_then_retry_consumes_two_slots(self) -> None:
        first = story.budgeted_authority_dispatch(
            self.auth, child_batch_id="B013", logical_call_id="B013-checker-r01", role="checker",
            phase="review", dispatch=lambda _a: {"state": "ambiguous", "detail": "receipt never observed"})
        second = story.budgeted_authority_dispatch(
            self.auth, child_batch_id="B013", logical_call_id="B013-checker-r01", role="checker",
            phase="review", dispatch=completed)
        self.assertNotEqual(first["global_attempt_id"], second["global_attempt_id"])
        self.assertEqual(self.auth.state.attempts[first["global_attempt_id"]]["state"], "ambiguous")
        self.assertEqual(self.auth.state.attempts[second["global_attempt_id"]]["state"], "consumed")
        self.assertEqual(self.auth.state.consumed_calls, 2)
        self.assertEqual(self.auth.remaining_global_budget, 12)

    # ---- journal discipline --------------------------------------------------------------

    def test_status_json_is_a_pure_projection_of_the_journal(self) -> None:
        story.budgeted_authority_dispatch(self.auth, child_batch_id="B013", logical_call_id="c0",
                                          role="maker", phase="implementation", dispatch=completed)
        status_path = self.auth.runtime_dir / "status.json"
        projection = json.loads(status_path.read_text(encoding="utf-8"))
        status_path.write_text(json.dumps({"budget": {"consumed_model_calls": 999}}), encoding="utf-8")
        rebuilt = self.second_runtime()
        rebuilt.journal.fold()
        rebuilt.state = rebuilt.journal.fold()
        self.assertEqual(rebuilt.state.consumed_calls, 1)
        self.auth.write_status()
        self.assertEqual(json.loads(status_path.read_text(encoding="utf-8")), projection)

    def test_tampered_journal_line_breaks_the_hash_chain(self) -> None:
        story.budgeted_authority_dispatch(self.auth, child_batch_id="B013", logical_call_id="c0",
                                          role="maker", phase="implementation", dispatch=completed)
        self.auth.release()
        journal = self.auth.runtime_dir / "journal.jsonl"
        lines = journal.read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1].replace('"role":"maker"', '"role":"checker"')
        journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
        reopened = self.second_runtime()
        with self.assertRaises(story.HardStop) as raised:
            reopened.acquire()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("hash chain", raised.exception.detail)
        reopened.release()

    def test_journal_is_append_only_and_never_holds_the_balance(self) -> None:
        story.budgeted_authority_dispatch(self.auth, child_batch_id="B013", logical_call_id="c0",
                                          role="maker", phase="implementation", dispatch=completed)
        kinds = [json.loads(line)["kind"] for line in
                 (self.auth.runtime_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kinds, ["authority_open", "model_call_reserved", "model_call_consumed"])
        envelope_text = story.authority_envelope_path(self.root, "A001").read_text(encoding="utf-8")
        for forbidden in ("consumed_model_calls", "remaining_global_budget", "global_attempt_id"):
            self.assertNotIn(forbidden, envelope_text)


if __name__ == "__main__":
    unittest.main()
