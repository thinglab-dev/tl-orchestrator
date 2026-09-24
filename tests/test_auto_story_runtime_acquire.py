import sys
import hashlib
from pathlib import Path
_TESTS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
for _p in (_TESTS_DIR, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import json
import tempfile
import unittest
import os
import shutil
import tl_runtime
from scripts.tests.test_tl_runtime import Fixture, SPEC_A, git
from tl_runtime import Runtime, Refusal
from tl_story_authority import StoryAuthority
from tl_merge_guard import temporary_platform_anchor_for_testing
from scripts.fixtures.runtime.fake_gh import TEST_FIXTURE_KEY_ID, TEST_FIXTURE_PUBLIC_KEY
from story_authority_support import story

class RuntimeAcquireTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        anchor = temporary_platform_anchor_for_testing({TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()})
        anchor.__enter__()
        self.addCleanup(anchor.__exit__, None, None, None)

    def fixture(self) -> Fixture:
        fx = Fixture(self.root, units=1)
        spec_sha = hashlib.sha256(SPEC_A.encode()).hexdigest()
        payload = story.build_authority_payload(
            authority_id="A001", work_ref="T001", authorized_spec_revision=spec_sha[:16],
            authorized_spec_sha256=spec_sha,
            authorized_write_scope={"required_mutation_targets": ["pkg"], "conditional_mutation_targets": [], "forbidden_paths": []},
            allowed_effects={"local_write": True, "local_commit": True, "local_merge": True, "pull_request": False, "push": False, "tag": False, "release": False, "merge": False},
            protected_paths=[], global_model_call_budget=20, max_child_batches=2,
            max_consecutive_failed_batches=2, wall_clock_deadline="2027-01-01T00:00:00Z",
            hard_stops=["scope_expansion", "model_call_budget_exhausted", "state_integrity"])
        envelope = story.freeze_authority(
            payload, authorized_literal=story.authorization_literal("T001", story.root_authority_digest(payload)),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        story.publish_authority(fx.repo, envelope)
        git(fx.repo, "add", "-A")
        git(fx.repo, "commit", "-q", "-m", "freeze")

        with StoryAuthority.open_for(fx.repo, "A001") as auth:
            proposal = story.derive_child_proposal(
                authority=auth, child_batch_id="B001", action_items=[], previous_child_id=None,
                model_call_budget=20, governance_base_commit=git(fx.repo, "rev-parse", "HEAD"),
                story_baseline_commit=git(fx.repo, "rev-parse", "HEAD"))
            proof = story.verify_derivation(auth, proposal)
            auth.record_child_derived(proposal, proof)

        fx.batch["authorization"].update({
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": envelope["root_authority_digest"],
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
        })
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        return fx

    def test_acquire_releases_all_locks_on_fold_failure(self):
        fx = self.fixture()
        # write invalid journal line to trigger failure after bind
        (fx.state_dir).mkdir(parents=True, exist_ok=True)
        (fx.state_dir / "journal.jsonl").write_text("invalid json\n", encoding="utf-8")

        rt1 = fx.runtime()
        with self.assertRaises(Refusal) as ctx:
            rt1.acquire()
        self.assertIn("unrecoverable_harness_failure_or_ambiguous_dispatch", str(ctx.exception))

        # rt2 should be able to acquire because rt1 released locks
        (fx.state_dir / "journal.jsonl").write_text("", encoding="utf-8")
        rt2 = fx.runtime()
        rt2.acquire()
        rt2.release()

    def test_acquire_releases_all_locks_on_bind_exception(self):
        fx = self.fixture()
        rt1 = fx.runtime()

        from unittest import mock
        with mock.patch.object(Runtime, '_bind_and_verify_auto_story_child', side_effect=RuntimeError("mock bind error")):
            with self.assertRaisesRegex(RuntimeError, "mock bind error"):
                rt1.acquire()

        # rt2 should be able to acquire because rt1 released locks
        rt2 = fx.runtime()
        rt2.acquire()
        rt2.release()

    def test_acquire_releases_all_locks_on_keyboard_interrupt(self):
        fx = self.fixture()
        rt1 = fx.runtime()

        from unittest import mock
        with mock.patch.object(rt1.journal, 'fold', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                rt1.acquire()

        self.assertIsNone(rt1._lease)
        self.assertIsNone(rt1.authority._lease)

        # rt2 should be able to acquire because rt1 released locks
        rt2 = fx.runtime()
        rt2.acquire()
        rt2.release()
