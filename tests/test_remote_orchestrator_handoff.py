#!/usr/bin/env python3
"""Deterministic contract tests for T034 remote orchestration handoff."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import tl_handoff as handoff


class RemoteHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="tl-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "base")
        self.git("remote", "add", "origin", "https://example.invalid/test/repo.git")
        self.status = self.repo / "STATUS.md"
        self.status.write_text("coordinator:\n  released: true\n", encoding="utf-8")
        self.state_dir = self.repo / "private-state"
        self.context = handoff.validate_context("native/task/T034@task.md", "planning", ["orchestrator", "planner", "maker", "checker"], ["openai"], "ctx-1")

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(self.repo), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.strip()

    def ready_preflight(self):
        return mock.patch.object(handoff, "preflight_codex", return_value={"status": "ready", "reason": "test"})

    def create(self) -> dict:
        return handoff.create_handoff(self.repo, self.state_dir, self.context)

    def claim(self, state: dict) -> dict:
        with self.ready_preflight():
            return handoff.claim_handoff(self.repo, self.state_dir, state["handoff_id"], "chatgpt-rdc:test", "codex")

    def test_preflight_missing_invalid_unknown_and_availability_keep_local(self) -> None:
        with mock.patch.object(handoff, "command_v", return_value=None):
            self.assertEqual(handoff.preflight_codex()["status"], "missing")
        with mock.patch.object(handoff, "command_v", return_value="/fake/codex"), mock.patch.object(
            handoff.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "bad")
        ):
            self.assertEqual(handoff.preflight_codex()["status"], "invalid")
        with mock.patch.object(handoff, "command_v", return_value="/fake/codex"), mock.patch.object(
            handoff.subprocess, "run", side_effect=OSError("noexec")
        ):
            self.assertEqual(handoff.preflight_codex()["status"], "unknown")
        with mock.patch.object(handoff, "preflight_codex", return_value={"status": "invalid", "reason": "bad version"}):
            available = handoff.remote_availability(True)
        self.assertFalse(available["remote_available"])
        self.assertTrue(available["local_available"])

    def test_handoff_compact_private_and_has_no_environment_or_secret(self) -> None:
        state = self.create()
        artifact = handoff.handoff_path(self.state_dir, state["handoff_id"])
        self.assertTrue(artifact.exists())
        self.assertNotIn("secret", artifact.read_text(encoding="utf-8").lower())
        self.assertNotIn("environment", artifact.read_text(encoding="utf-8").lower())
        self.assertEqual(state["state"], "created")
        self.assertEqual(state["context"]["effective_author_families"], ["openai"])

    def test_claim_rejects_branch_head_dirty_and_git_identity_drift(self) -> None:
        for name, drift in {
            "branch": lambda: self.git("checkout", "-qb", "other"),
            "head": lambda: ((self.repo / "next.txt").write_text("next\n", encoding="utf-8"), self.git("add", "next.txt"), self.git("commit", "-qm", "next")),
            "dirty": lambda: (self.repo / "tracked.txt").write_text("dirty\n", encoding="utf-8"),
            "identity": lambda: self.git("remote", "set-url", "origin", "https://example.invalid/other.git"),
        }.items():
            with self.subTest(name=name):
                state = self.create()
                drift()
                with self.ready_preflight(), self.assertRaisesRegex(handoff.HandoffError, "changed"):
                    handoff.claim_handoff(self.repo, self.state_dir, state["handoff_id"], "chatgpt-rdc:test", "codex")
                # Isolate every subtest by rebuilding the Git fixture.
                self.tearDown()
                self.setUp()

    def test_double_claim_replay_and_tamper_fail_closed(self) -> None:
        state = self.create()
        claimed = self.claim(state)
        self.assertEqual(claimed["state"], "claimed")
        with self.ready_preflight(), self.assertRaisesRegex(handoff.HandoffError, "newly created"):
            handoff.claim_handoff(self.repo, self.state_dir, state["handoff_id"], "second", "codex")
        with self.assertRaisesRegex(handoff.HandoffError, "not been released"):
            handoff.activate_handoff(self.repo, self.state_dir, state["handoff_id"])
        artifact = handoff.handoff_path(self.state_dir, state["handoff_id"])
        data = json.loads(artifact.read_text(encoding="utf-8"))
        data["context"]["phase"] = "tampered"
        artifact.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(handoff.HandoffError, "revision"):
            handoff.return_to_local(self.repo, self.state_dir, state["handoff_id"])

    def test_activation_requires_released_coordinator_and_return_resumes_local(self) -> None:
        state = self.create()
        self.claim(state)
        with self.assertRaisesRegex(handoff.HandoffError, "not been released"):
            handoff.activate_handoff(self.repo, self.state_dir, state["handoff_id"])
        self.status.write_text("coordinator:\n  released: false\n", encoding="utf-8")
        with self.assertRaisesRegex(handoff.HandoffError, "not released"):
            handoff.release_local_authority(self.repo, self.state_dir, state["handoff_id"], self.status)
        self.status.write_text("coordinator:\n  released: true\n", encoding="utf-8")
        handoff.release_local_authority(self.repo, self.state_dir, state["handoff_id"], self.status)
        active = handoff.activate_handoff(self.repo, self.state_dir, state["handoff_id"])
        self.assertEqual(active["owner"], "remote")
        returned = handoff.return_to_local(self.repo, self.state_dir, state["handoff_id"])
        self.assertEqual(returned["state"], "returned_to_local")
        self.assertEqual(handoff.resume_local(self.repo, self.state_dir, state["handoff_id"])["next_actions"], ["resume_local", "create_new_remote_handoff"])
        with self.assertRaisesRegex(handoff.HandoffError, "returned repository snapshot changed"):
            (self.repo / "tracked.txt").write_text("after-return\n", encoding="utf-8")
            handoff.resume_local(self.repo, self.state_dir, state["handoff_id"])

    def test_remote_checker_policy_keeps_gemini_independent_when_claude_has_no_quota(self) -> None:
        # The resolver rejects authors' families. OpenAI Maker therefore leaves Claude, then Gemini.
        from scripts.validate_classification import resolve_checker_candidates

        candidates = [
            ("claude", "sonnet", "high"),
            ("agy", "gemini-3.1-pro-high", "high"),
            ("codex", "gpt-5.6-terra", "high"),
        ]
        self.assertEqual(resolve_checker_candidates(candidates, {"openai"}, {"claude"}), ("agy", "gemini-3.1-pro-high", "high"))
        self.assertIsNone(resolve_checker_candidates(candidates, {"openai", "google", "anthropic"}, set()))


if __name__ == "__main__":
    unittest.main()
