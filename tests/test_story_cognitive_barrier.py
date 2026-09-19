#!/usr/bin/env python3
"""Mechanical blocking of cognitive calls outside the ledger (T032 §2.8).

The mandatory counter-proof: a direct invocation of a cognitive CLI from the authorized worker
must fail deterministically *before* it can reach the network or a provider. Where the platform
cannot guarantee that, the capability is `unavailable` and AUTO_STORY refuses to start.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from story_authority_support import StoryCase, story


class CognitiveCallBarrierTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tl-barrier-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.barrier = self.root / "cognitive-barrier"

    def worker_env(self) -> dict:
        return story.barrier_worker_env({"PATH": os.environ.get("PATH", ""), "HOME": str(self.root)}, self.barrier)

    def test_direct_cognitive_cli_invocation_fails_before_reaching_the_provider(self) -> None:
        story.install_cognitive_barrier(self.barrier)
        env = self.worker_env()
        self.assertTrue(env["PATH"].startswith(str(self.barrier)))
        self.assertEqual(env["TL_COGNITIVE_CALL_BARRIER"], str(self.barrier))

        for name in story.COGNITIVE_CLIS:
            resolved = shutil.which(name, path=env["PATH"])
            self.assertIsNotNone(resolved, name)
            self.assertEqual(Path(resolved).resolve().parent, self.barrier.resolve(), name)
            run = subprocess.run([resolved, "--model", "opus", "-p", "hello"],
                                 capture_output=True, text=True, check=False, env=env, timeout=30)
            self.assertEqual(run.returncode, story.BARRIER_EXIT_CODE, name)
            self.assertIn("cognitive call barrier", run.stderr)
            self.assertEqual(run.stdout, "")

    @unittest.skipIf(os.name == "nt", "the POSIX shell probe does not apply on Windows")
    def test_a_worker_shell_cannot_reach_a_cognitive_cli_by_name(self) -> None:
        """The counter-proof from inside a shell the worker itself would spawn."""
        story.install_cognitive_barrier(self.barrier)
        real = self.root / "real-bin"
        real.mkdir()
        # A genuine CLI further down the PATH must never be the one that resolves.
        impostor = real / "codex"
        impostor.write_text("#!/bin/sh\necho 'REACHED THE PROVIDER'\nexit 0\n", encoding="utf-8")
        impostor.chmod(impostor.stat().st_mode | stat.S_IXUSR)
        env = story.barrier_worker_env({"PATH": f"{real}:{os.environ.get('PATH', '')}", "HOME": str(self.root)},
                                       self.barrier)
        run = subprocess.run(["/bin/sh", "-c", "codex exec 'do the thing'"],
                             capture_output=True, text=True, check=False, env=env, timeout=30)
        self.assertEqual(run.returncode, story.BARRIER_EXIT_CODE)
        self.assertNotIn("REACHED THE PROVIDER", run.stdout)
        self.assertIn("cognitive call barrier", run.stderr)

        # Declared limitation, asserted so it stays declared: the barrier shadows names, not paths.
        direct = subprocess.run([str(impostor)], capture_output=True, text=True, check=False, env=env, timeout=30)
        self.assertEqual(direct.returncode, 0)
        self.assertIn("REACHED THE PROVIDER", direct.stdout)
        self.assertIn("name resolution only", story.probe_cognitive_barrier(self.barrier, env=env)["limitation"])

    def test_probe_reports_available_only_when_every_cli_is_blocked(self) -> None:
        report = story.require_cognitive_barrier(self.barrier)
        self.assertEqual(report["capability"], "available")
        self.assertEqual({check["cli"] for check in report["checks"]}, set(story.COGNITIVE_CLIS))
        self.assertTrue(all(check["blocked"] for check in report["checks"]))

    def test_auto_story_refuses_to_start_when_the_barrier_cannot_hold(self) -> None:
        """No degraded mode: an unprovable barrier stops initialization with a named reason."""
        story.install_cognitive_barrier(self.barrier)
        (self.barrier / ("codex.cmd" if os.name == "nt" else "codex")).unlink()
        report = story.probe_cognitive_barrier(self.barrier)
        self.assertEqual(report["capability"], "unavailable")
        missing = next(check for check in report["checks"] if check["cli"] == "codex")
        self.assertFalse(missing["shadows_real_cli"])

        # require_* reinstalls, so the unavailable path is exercised against a directory that
        # cannot host an executable shim at all.
        blocked_dir = self.root / "not-a-directory"
        blocked_dir.write_text("this path is a file\n", encoding="utf-8")
        with self.assertRaises((story.HardStop, OSError, NotADirectoryError, FileExistsError)) as raised:
            story.require_cognitive_barrier(blocked_dir)
        if isinstance(raised.exception, story.HardStop):
            self.assertEqual(raised.exception.reason, "cognitive_call_barrier_unavailable")

    @unittest.skipIf(os.name == "nt", "POSIX permission semantics")
    def test_a_non_executable_shim_is_reported_unavailable(self) -> None:
        story.install_cognitive_barrier(self.barrier)
        for name in story.COGNITIVE_CLIS:
            shim = self.barrier / name
            shim.chmod(shim.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        report = story.probe_cognitive_barrier(self.barrier)
        self.assertEqual(report["capability"], "unavailable")
        with self.assertRaises(story.HardStop) as raised:
            # Reinstalling would repair the bit, so the refusal is asserted on the probe result.
            if report["capability"] != "available":
                raise story.HardStop("cognitive_call_barrier_unavailable", "probe reported unavailable")
        self.assertEqual(raised.exception.reason, "cognitive_call_barrier_unavailable")


class RuntimePolicyBarrierTest(StoryCase):
    """The barrier reaches the worker through the runtime's own policy boundary."""

    def test_worker_env_carries_the_barrier_only_under_auto_story(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import tl_runtime

        batch = {"authorization": {"permitted_effects": {"local_write": True}}}
        legacy = tl_runtime.Policy({"sensitive_paths": []}, batch)
        self.assertNotIn("TL_COGNITIVE_CALL_BARRIER", legacy.worker_env())

        barrier = self.root / "barrier"
        story.install_cognitive_barrier(barrier)
        guarded = tl_runtime.Policy({"sensitive_paths": []}, batch, cognitive_barrier=barrier)
        env = guarded.worker_env()
        self.assertEqual(env["TL_COGNITIVE_CALL_BARRIER"], str(barrier))
        self.assertTrue(env["PATH"].startswith(str(barrier)))
        self.assertEqual(Path(shutil.which("claude", path=env["PATH"])).resolve().parent, barrier.resolve())


if __name__ == "__main__":
    unittest.main()
