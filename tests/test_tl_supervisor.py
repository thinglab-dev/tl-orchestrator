"""Offline unit tests for concurrent multi-story supervision."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import tl_supervisor
from scripts import tl_run_story
from scripts.tl_merge_guard import AuthorityReceipt


def completed(returncode=0):
    return subprocess.CompletedProcess(["git"], returncode, "", "")


def mock_receipt(confirmed=True, reason="AUTHORITY_CONFIRMED", story_id="T001", pr_number=11):
    return AuthorityReceipt(
        status="CONFIRMED" if confirmed else "REJECTED",
        authorization_id=f"auth-test-{story_id.lower()}",
        target_pr=pr_number,
        head_sha="a" * 40,
        base_sha="b" * 40,
        checker_commit="a" * 40,
        candidate_commit="a" * 40,
        reason=reason,
    )


class SupervisorCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()


class WorktreePoolTest(SupervisorCase):
    @mock.patch.object(tl_supervisor, "_run_git", return_value=completed())
    def test_acquire_exhaustion_and_release(self, run_git):
        pool = self.root / "worktrees"
        first = tl_supervisor.acquire_worktree_slot(pool, "T001", 1)
        second = tl_supervisor.acquire_worktree_slot(pool, "T002", 1)
        self.assertEqual(first["state"], "acquired")
        self.assertEqual(second, {"state": "pool_exhausted"})
        self.assertTrue((pool / "T001" / "slot.json").exists())
        self.assertEqual(tl_supervisor.release_worktree_slot(pool, "T001")["state"], "released")
        self.assertEqual(tl_supervisor.acquire_worktree_slot(pool, "T002", 1)["state"], "acquired")
        self.assertGreaterEqual(run_git.call_count, 3)

    @mock.patch.object(tl_supervisor, "_run_git", return_value=completed())
    def test_concurrent_acquire_grants_exactly_one_slot(self, _run_git):
        pool = self.root / "worktrees"
        barrier = threading.Barrier(3)
        answers = []

        def acquire(story_id):
            barrier.wait()
            answers.append(tl_supervisor.acquire_worktree_slot(pool, story_id, 1)["state"])

        threads = [threading.Thread(target=acquire, args=(story,)) for story in ("T001", "T002")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertCountEqual(answers, ["acquired", "pool_exhausted"])
        self.assertEqual(len(list(pool.glob("*/slot.json"))), 1)

    @mock.patch.object(tl_supervisor, "_atomic_write_json", side_effect=OSError("disk full"))
    @mock.patch.object(tl_supervisor, "_run_git", return_value=completed())
    def test_slot_is_not_granted_when_atomic_publish_fails(self, run_git, _write_json):
        result = tl_supervisor.acquire_worktree_slot(self.root / "worktrees", "T001", 1)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(run_git.call_count, 2, "the created worktree was rolled back")

    def test_dispatch_claims_scope_before_acquiring_and_rolls_back_exhaustion(self):
        calls = []
        with (
            mock.patch.object(
                tl_run_story,
                "claim_scope",
                side_effect=lambda *args: calls.append("claim") or {"state": "claimed"},
            ),
            mock.patch.object(
                tl_run_story,
                "acquire_worktree_slot",
                side_effect=lambda *args: calls.append("acquire") or {"state": "pool_exhausted"},
            ),
            mock.patch.object(
                tl_run_story,
                "release_scope",
                side_effect=lambda *args: calls.append("release") or {"state": "released"},
            ),
        ):
            result = tl_run_story.dispatch_story(
                self.root / "worktrees", "T001", ["docs/file.md"], self.root / "claims.json", 1
            )
        self.assertEqual(result["state"], "pool_exhausted")
        self.assertEqual(calls, ["claim", "acquire", "release"])


class ScopeArbiterTest(SupervisorCase):
    def test_disjoint_scopes_succeed_and_release(self):
        claims = self.root / "claims.json"
        first = tl_supervisor.claim_scope("T001", ["scripts/tl_supervisor.py"], claims)
        second = tl_supervisor.claim_scope("T002", ["docs/EXECUTION_PROTOCOL.md"], claims)
        self.assertEqual(first["state"], "claimed")
        self.assertEqual(second["state"], "claimed")
        self.assertEqual(tl_supervisor.release_scope("T001", claims)["state"], "released")

    def test_equal_ancestor_and_descendant_paths_conflict(self):
        for requested in ("docs", "docs/EXECUTION_PROTOCOL.md"):
            with self.subTest(requested=requested):
                claims = self.root / (requested.replace("/", "_") + ".json")
                self.assertEqual(
                    tl_supervisor.claim_scope("T001", ["docs/EXECUTION_PROTOCOL.md"], claims)["state"],
                    "claimed",
                )
                conflict = tl_supervisor.claim_scope("T002", [requested], claims)
                self.assertEqual(conflict["state"], "scope_conflict")
                self.assertEqual(conflict["conflicting_with"], "T001")

    def test_corrupt_claims_fail_closed(self):
        claims = self.root / "claims.json"
        claims.write_text("not json", encoding="utf-8")
        self.assertEqual(
            tl_supervisor.claim_scope("T001", ["docs/file.md"], claims)["state"],
            "unavailable",
        )

    def test_atomic_claim_publish_failure_fails_closed(self):
        claims = self.root / "claims.json"
        with mock.patch.object(tl_supervisor, "_atomic_write_json", side_effect=OSError("disk full")):
            result = tl_supervisor.claim_scope("T001", ["docs/file.md"], claims)
        self.assertEqual(result["state"], "unavailable")
        self.assertFalse(claims.exists())

    def test_concurrent_claim_race_has_one_winner(self):
        claims = self.root / "claims.json"
        barrier = threading.Barrier(3)
        answers = []

        def claim(story_id):
            barrier.wait()
            answers.append(tl_supervisor.claim_scope(story_id, ["docs/shared.md"], claims)["state"])

        threads = [threading.Thread(target=claim, args=(story,)) for story in ("T001", "T002")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertCountEqual(answers, ["claimed", "scope_conflict"])


class MergeQueueTest(SupervisorCase):
    def test_fifo_and_failed_head_blocks_automatic_advance(self):
        queue = self.root / "merge-queue.json"
        self.assertEqual(tl_supervisor.enqueue_merge("T001", 11, queue)["position"], 0)
        self.assertEqual(tl_supervisor.enqueue_merge("T002", 12, queue)["position"], 1)
        called = []
        first = tl_supervisor.advance_merge_queue(
            queue, lambda item: called.append(item["story_id"]) or mock_receipt(False, "operator_rejected", item["story_id"], item["pr_number"])
        )
        blocked = tl_supervisor.advance_merge_queue(
            queue, lambda item: called.append(item["story_id"]) or mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])
        )
        self.assertEqual(first["state"], "failed")
        self.assertEqual(blocked["state"], "queue_blocked")
        self.assertEqual(called, ["T001"])
        retried = tl_supervisor.advance_merge_queue(
            queue, lambda item: called.append(item["story_id"]) or mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"]), retry_failed=True
        )
        self.assertEqual(retried["state"], "merged")
        self.assertEqual(called, ["T001", "T001"])

    def test_concurrent_enqueue_and_serialized_advance_remain_fifo(self):
        queue = self.root / "merge-queue.json"
        barrier = threading.Barrier(3)
        positions = {}

        def enqueue(story_id, pr_number):
            barrier.wait()
            positions[story_id] = tl_supervisor.enqueue_merge(story_id, pr_number, queue)["position"]

        threads = [
            threading.Thread(target=enqueue, args=("T001", 11)),
            threading.Thread(target=enqueue, args=("T002", 12)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        expected_order = [story_id for story_id, _ in sorted(positions.items(), key=lambda pair: pair[1])]
        order = []
        active = 0
        maximum_active = 0
        guard = threading.Lock()

        def merge(item):
            nonlocal active, maximum_active
            with guard:
                active += 1
                maximum_active = max(maximum_active, active)
            order.append(item["story_id"])
            time.sleep(0.03)
            with guard:
                active -= 1
            return mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])

        advances = [threading.Thread(target=tl_supervisor.advance_merge_queue, args=(queue, merge)) for _ in range(2)]
        for thread in advances:
            thread.start()
        for thread in advances:
            thread.join()
        self.assertEqual(order, expected_order)
        self.assertEqual(maximum_active, 1)
        items = json.loads(queue.read_text(encoding="utf-8"))["items"]
        self.assertEqual([item["state"] for item in items], ["merged", "merged"])

    def test_concurrent_enqueue_succeeds_during_slow_merge_runner(self):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        runner_started = threading.Event()
        allow_runner_to_finish = threading.Event()
        advance_result = {}
        enqueue_result = {}

        def slow_merge(item):
            runner_started.set()
            allow_runner_to_finish.wait(timeout=2)
            return mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])

        def advance():
            advance_result.update(tl_supervisor.advance_merge_queue(queue, slow_merge))

        def enqueue():
            enqueue_result.update(tl_supervisor.enqueue_merge("T002", 12, queue))

        advance_thread = threading.Thread(target=advance)
        enqueue_thread = threading.Thread(target=enqueue)
        advance_thread.start()
        self.assertTrue(runner_started.wait(timeout=1))
        enqueue_thread.start()
        enqueue_thread.join(timeout=1)
        enqueue_finished_while_runner_blocked = not enqueue_thread.is_alive()
        allow_runner_to_finish.set()
        advance_thread.join(timeout=1)
        enqueue_thread.join(timeout=1)

        self.assertTrue(enqueue_finished_while_runner_blocked)
        self.assertEqual(enqueue_result["state"], "enqueued")
        self.assertEqual(advance_result["state"], "merged")

    def test_stale_merging_head_is_recovered_and_does_not_block_queue(self):
        queue = self.root / "merge-queue.json"
        queue.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "story_id": "T001",
                            "pr_number": 11,
                            "state": "merging",
                            "enqueued_at": time.time() - 300,
                            "started_at": time.time() - 180,
                            "in_flight_token": "abandoned-dispatch",
                        },
                        {
                            "story_id": "T002",
                            "pr_number": 12,
                            "state": "pending",
                            "enqueued_at": time.time() - 200,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        called = []

        first = tl_supervisor.advance_merge_queue(
            queue, lambda item: called.append(item["story_id"]) or mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])
        )
        second = tl_supervisor.advance_merge_queue(
            queue, lambda item: called.append(item["story_id"]) or mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])
        )

        self.assertEqual(first["state"], "merged")
        self.assertEqual(second["state"], "merged")
        self.assertEqual(called, ["T001", "T002"])
        items = json.loads(queue.read_text(encoding="utf-8"))["items"]
        self.assertEqual([item["state"] for item in items], ["merged", "merged"])
        self.assertNotIn("started_at", items[0])
        self.assertNotIn("in_flight_token", items[0])

    def test_retry_failed_explicitly_recovers_fresh_merging_head(self):
        queue = self.root / "merge-queue.json"
        queue.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "story_id": "T001",
                            "pr_number": 11,
                            "state": "merging",
                            "enqueued_at": time.time() - 10,
                            "started_at": time.time(),
                            "in_flight_token": "active-dispatch",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        runner = mock.Mock(side_effect=lambda item: mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"]))

        in_progress = tl_supervisor.advance_merge_queue(queue, runner)
        recovered = tl_supervisor.advance_merge_queue(queue, runner, retry_failed=True)

        self.assertEqual(in_progress["state"], "merge_in_progress")
        self.assertEqual(recovered["state"], "merged")
        runner.assert_called_once()

    def test_terminal_state_lock_acquisition_retries_after_timeout(self):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        original_lock = tl_supervisor._FileLock
        queue_lock_attempts = 0

        class OneTransientTimeout:
            def __init__(self, path, timeout=tl_supervisor.LOCK_TIMEOUT_SECONDS):
                self.path = path
                self.timeout = timeout
                self.lock = None

            def __enter__(self):
                nonlocal queue_lock_attempts
                if self.path == queue.with_name(queue.name + ".lock"):
                    queue_lock_attempts += 1
                    if queue_lock_attempts == 2:
                        raise TimeoutError("transient contention")
                self.lock = original_lock(self.path, self.timeout)
                return self.lock.__enter__()

            def __exit__(self, exc_type, exc, traceback):
                if self.lock is not None:
                    return self.lock.__exit__(exc_type, exc, traceback)

        with mock.patch.object(tl_supervisor, "_FileLock", OneTransientTimeout):
            result = tl_supervisor.advance_merge_queue(
                queue, lambda item: mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"])
            )

        self.assertEqual(result["state"], "merged")
        self.assertEqual(queue_lock_attempts, 3)
        item = json.loads(queue.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(item["state"], "merged")

    @mock.patch("scripts.tl_run_story.subprocess.run", return_value=completed())
    def test_story_runner_invokes_gh_for_fifo_head_only(self, run):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        tl_supervisor.enqueue_merge("T002", 12, queue)
        result = tl_run_story.merge_queue_head(
            queue,
            authority_validator=lambda item: mock_receipt(True, story_id=item["story_id"], pr_number=item["pr_number"]),
        )
        self.assertEqual(result["state"], "merged")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0:5], ["gh", "pr", "merge", "11", "--auto"])

    def test_uninspected_callback_without_authority_receipt_is_rejected(self):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        result = tl_supervisor.advance_merge_queue(queue, lambda _item: True)
        self.assertEqual(result["state"], "failed")
        self.assertIn("AuthorityReceipt", result["item"]["detail"])

    def test_unconfirmed_authority_receipt_blocks_merge_and_marks_failed(self):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        result = tl_supervisor.advance_merge_queue(
            queue, lambda item: mock_receipt(False, "missing_merge_authorization", item["story_id"], item["pr_number"])
        )
        self.assertEqual(result["state"], "failed")
        self.assertIn("missing_merge_authorization", result["item"]["detail"])

    @mock.patch("scripts.tl_run_story.subprocess.run", return_value=completed())
    def test_story_runner_rejects_missing_authority_without_invoking_gh(self, run):
        queue = self.root / "merge-queue.json"
        tl_supervisor.enqueue_merge("T001", 11, queue)
        result = tl_run_story.merge_queue_head(queue)
        self.assertEqual(result["state"], "failed")
        run.assert_not_called()
        self.assertIn("missing_authority_receipt", result["item"]["detail"])

    def test_corrupt_queue_never_dispatches_merge(self):
        queue = self.root / "merge-queue.json"
        queue.write_text("{}", encoding="utf-8")
        runner = mock.Mock(return_value=True)
        result = tl_supervisor.advance_merge_queue(queue, runner)
        self.assertEqual(result["state"], "unavailable")
        runner.assert_not_called()



class OrphanSweepTest(SupervisorCase):
    @mock.patch.object(tl_supervisor, "_run_git", return_value=completed())
    def test_only_stale_worktree_is_swept(self, run_git):
        pool = self.root / "worktrees"
        now = time.time()
        for story_id, heartbeat in (("T001", now - 100), ("T002", now - 2)):
            slot = pool / story_id / "slot.json"
            slot.parent.mkdir(parents=True)
            slot.write_text(
                json.dumps({"story_id": story_id, "lease": {"heartbeat_ts": heartbeat}}),
                encoding="utf-8",
            )
        result = tl_supervisor.sweep_orphan_worktrees(pool, 30)
        self.assertEqual(result["removed"], ["T001"])
        self.assertFalse((pool / "T001" / "slot.json").exists())
        self.assertTrue((pool / "T002" / "slot.json").exists())
        self.assertEqual(run_git.call_count, 1)

    def test_malformed_orphan_slot_is_refused_not_removed(self):
        slot = self.root / "worktrees" / "T001" / "slot.json"
        slot.parent.mkdir(parents=True)
        slot.write_text("not json", encoding="utf-8")
        result = tl_supervisor.sweep_orphan_worktrees(self.root / "worktrees", 30)
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["refused"], ["T001"])
        self.assertTrue(slot.exists())


class StatusBoardTest(SupervisorCase):
    def write_status(self, status):
        status.write_text(
            "## Tasks\n"
            "| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T015 | feat | package | in-progress | [T014] | [] | 0 | - |\n",
            encoding="utf-8",
        )

    def test_compare_and_swap_rejects_stale_revision(self):
        status = self.root / "STATUS.md"
        self.write_status(status)
        first = tl_supervisor.update_task_status_atomic(status, "T015", "done", 0)
        second = tl_supervisor.update_task_status_atomic(status, "T015", "parked", 0)
        self.assertEqual(first["state"], "updated")
        self.assertEqual(second["state"], "state_revision_conflict")
        final = status.read_text(encoding="utf-8")
        self.assertIn("| T015 | feat | package | done | [T014] | [] | 1 | - |", final)
        self.assertEqual(final.count("| T015 |"), 1)

    def test_concurrent_compare_and_swap_has_one_winner(self):
        status = self.root / "STATUS.md"
        self.write_status(status)
        barrier = threading.Barrier(3)
        answers = []

        def update(new_status):
            barrier.wait()
            answers.append(
                tl_supervisor.update_task_status_atomic(status, "T015", new_status, 0)["state"]
            )

        threads = [threading.Thread(target=update, args=(value,)) for value in ("done", "parked")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertCountEqual(answers, ["updated", "state_revision_conflict"])

    def test_missing_task_fails_closed_without_rewriting_board(self):
        status = self.root / "STATUS.md"
        self.write_status(status)
        before = status.read_bytes()
        result = tl_supervisor.update_task_status_atomic(status, "T999", "done", 0)
        self.assertEqual(result["state"], "task_not_found")
        self.assertEqual(status.read_bytes(), before)

    def test_unicode_task_id_is_accepted_without_loosening_board_key_rules(self):
        status = self.root / "STATUS.md"
        status.write_text(
            "## Tasks\n"
            "| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| 14-2-navegação | feat | package | in-progress | [] | [] | 0 | - |\n",
            encoding="utf-8",
        )
        result = tl_supervisor.update_task_status_atomic(status, "14-2-navegação", "done", 0)
        self.assertEqual(result["state"], "updated")
        self.assertIn("| 14-2-navegação | feat | package | done |", status.read_text(encoding="utf-8"))
        for invalid in ("_privada", "#comentário", "chave com espaço", '"aspas"', "a:b", ""):
            self.assertFalse(tl_supervisor._valid_story_id(invalid), invalid)


if __name__ == "__main__":
    unittest.main()
