#!/usr/bin/env python3
"""Behavioral tests for the optional supervisor; offline, temporary files only.

These tests exercise failure behavior, not string presence. No network, no model
call and no write outside the temporary directory of each test.
"""

from __future__ import annotations

import builtins
import contextlib
import errno
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CLI = SCRIPTS / "tl_job.py"
sys.path.insert(0, str(SCRIPTS))

import tl_job  # noqa: E402  - path is prepared above


AUTHORIZATION = "story:T012/authorization:2026-09-11"


class JobCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="tl-job-test-", ignore_cleanup_errors=True)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.drain)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.work = self.root / "work"
        self.work.mkdir()
        self.receipt_raw = b""

    def drain(self, limit: float = 90.0) -> None:
        """Every unit here has a bounded timeout; let the supervisors close their logs."""
        jobs = self.state / "jobs"
        if not jobs.is_dir():
            return
        deadline = time.monotonic() + limit
        for job in jobs.iterdir():
            while not (job / "result.json").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
        time.sleep(0.2)

    # --- helpers ---------------------------------------------------------

    def child(self, body: str, name: str = "child.py") -> Path:
        path = self.work / name
        path.write_text("import json, os, sys\n" + body, encoding="utf-8")
        return path

    def run_cli(self, *args: str) -> tuple[int, dict]:
        process = subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True,
            cwd=str(self.root),
        )
        text = process.stdout.decode("utf-8").strip()
        self.assertTrue(text, f"no receipt on stdout; stderr={process.stderr.decode('utf-8', 'replace')}")
        # Kept aside so a ceiling test can weigh the bytes the caller actually read: re-serializing
        # the parsed receipt measures this test's separators, not the ones the command wrote.
        self.receipt_raw = process.stdout.strip()
        return process.returncode, json.loads(text)

    def start(self, script: Path, unit: str = "T012", timeout: str = "60", authorization: str = AUTHORIZATION, extra: list[str] | None = None) -> tuple[int, dict]:
        return self.run_cli(
            *(extra or []),
            "start",
            "--state-dir",
            str(self.state),
            "--unit",
            unit,
            "--authorization",
            authorization,
            "--cwd",
            str(self.work),
            "--timeout",
            timeout,
            "--",
            sys.executable,
            str(script),
        )

    def wait(self, unit: str = "T012", timeout: str = "60", extra: list[str] | None = None) -> tuple[int, dict]:
        return self.run_cli(*(extra or []), "wait", "--state-dir", str(self.state), "--unit", unit, "--timeout", timeout)

    def status(self, unit: str = "T012") -> tuple[int, dict]:
        return self.run_cli("status", "--state-dir", str(self.state), "--unit", unit)

    def job_dir(self, unit: str = "T012") -> Path:
        return self.state / "jobs" / unit

    def write_result(self, payload: str) -> str:
        return f'open(os.environ["TL_JOB_RESULT"], "w", encoding="utf-8").write({payload})\n'

    def claim(self, script: Path, unit: str = "T012", timeout: float = 60.0) -> Path:
        """Write the claim `start` would write, so `supervise` can be driven in this process."""
        job_dir = self.state / "jobs" / unit
        job_dir.mkdir(parents=True)
        manifest = tl_job.build_manifest(
            unit,
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, str(script)],
            timeout,
            job_dir / "unit-result.json",
        )
        # Exactly as `start` does it: the lease file exists before the claim that names it,
        # so every reader has an identity to compare the file it opens against.
        manifest["lease_identity"] = tl_job.create_lease(job_dir / tl_job.LEASE_NAME)
        tl_job.write_atomic(job_dir / "manifest.json", manifest)
        self.anchor(job_dir, unit)
        tl_job.write_status(job_dir, unit, "starting")
        return job_dir

    def anchor(self, job_dir: Path, unit: str | None = None) -> str:
        """Publish, for a hand built claim, the binding `start` publishes for a real one.

        Nothing outside the job directory vouches for a claim written field by field, and a
        claim nothing vouches for is refused everywhere. Re-publishing is allowed here, and
        only here: the tests that rewrite a claim on purpose decide which binding it faces.
        """
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        path = tl_job.anchor_path(job_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        return tl_job.write_anchor(job_dir, unit or job_dir.name, manifest)["binding"]

    def bind_lease(self, job_dir: Path) -> str:
        """Create the lease of a hand-planted claim and record which file it named.

        A claim written field by field commits to no file, and nothing unbound is ever read
        as an ending. This is the one step that makes such a directory comparable to a real
        one, and it is deliberately explicit: the cases about a missing binding need it left out.
        """
        identity = tl_job.create_lease(job_dir / tl_job.LEASE_NAME)
        path = job_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["lease_identity"] = identity
        tl_job.write_atomic(path, manifest)
        self.anchor(job_dir)
        return identity

    def appear(self, path: Path, limit: float = 30.0) -> None:
        deadline = time.monotonic() + limit
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)

    def written(self, path: Path, limit: float = 30.0) -> int:
        """Wait until `path` holds bytes and answer its size; zero means it never did.

        Existence alone still races with the first write, and a caller that only
        waited for the name can stat a file its writer never got to create.
        """
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError):
                size = path.stat().st_size
                if size > 0:
                    return size
            time.sleep(0.05)
        return 0


class ReceiptLimitsTest(JobCase):
    def test_large_stdout_stays_on_disk_and_out_of_the_receipt(self) -> None:
        script = self.child(
            'sys.stdout.write("LEAKED-MARKER " * 60000)\n'
            + self.write_result('json.dumps({"outcome": "delivered", "next_action": "conferir"})')
        )
        code, start = self.start(script)
        self.assertEqual(code, 0)
        self.assertEqual(set(start) & {"stdout", "log", "output"}, set())
        code, result = self.wait()
        self.assertEqual(code, 0)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("LEAKED-MARKER", serialized)
        self.assertLess(len(serialized.encode("utf-8")), tl_job.DEFAULT_MAX_BYTES)
        stdout_log = self.job_dir() / "stdout.log"
        self.assertGreater(stdout_log.stat().st_size, 500000)
        self.assertEqual(result["logs"]["stdout"]["bytes"], stdout_log.stat().st_size)

    def test_initial_receipt_carries_only_identity_and_locators(self) -> None:
        script = self.child('sys.stdout.write("noise")\n' + self.write_result('json.dumps({"outcome": "delivered"})'))
        code, start = self.start(script)
        self.assertEqual(code, 0)
        # The binding is the one addition, and it is not description: it is the token a later
        # reader cannot rebuild from disk, so it has to leave `start` or be lost.
        self.assertEqual(set(start), {"schema", "job_id", "unit", "state", "locators", "binding"})
        self.assertEqual(start["state"], "starting")
        self.assertNotIn(AUTHORIZATION, json.dumps(start))
        # The fingerprints stay in the private manifest, where identity is checked.
        manifest = json.loads((self.job_dir() / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("authorization_fingerprint", manifest)
        self.wait()

    def test_status_receipt_stays_at_identity_state_and_locators(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        code, snapshot = self.status()
        self.assertEqual(code, 0)
        self.assertEqual(set(snapshot), {"schema", "job_id", "unit", "state", "locators"})
        self.wait()

    def test_byte_ceiling_drops_optional_fields_and_keeps_the_core(self) -> None:
        blockers = json.dumps(["bloqueio " + "z" * 400 for _ in range(6)])
        script = self.child(
            self.write_result(
                'json.dumps({"outcome": "blocked", "blockers": %s, "decision": "%s", "next_action": "%s"})'
                % (blockers, "d" * 400, "n" * 400)
            )
        )
        self.start(script)
        code, result = self.wait(extra=["--max-bytes", "600"])
        self.assertEqual(code, tl_job.EXIT_UNIT_FAILED)
        self.assertLessEqual(len(self.receipt_raw), 600)
        self.assertTrue(result["clipped"])
        for key in ("job_id", "unit", "state", "effects"):
            self.assertIn(key, result)

    def test_unicode_survives_normalization_without_control_characters(self) -> None:
        decision = "entrega ção ✅  combinável \U0001f680"
        script = self.child(
            self.write_result('json.dumps({"outcome": "delivered", "decision": %s})' % json.dumps(decision))
        )
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, 0)
        self.assertIn("\U0001f680", result["decision"])
        self.assertNotIn("", result["decision"])
        self.assertEqual(result["decision"], tl_job.clip(result["decision"]))

    def test_clip_cuts_by_bytes_without_breaking_a_codepoint(self) -> None:
        cut = tl_job.clip("á" * 500, 64)
        self.assertLessEqual(len(cut.encode("utf-8")), 64)
        self.assertTrue(cut.endswith("..."))
        json.dumps(cut)  # a broken codepoint would raise here


class IdentityTest(JobCase):
    def effect_script(self, sleep: float = 0.0) -> Path:
        marker = (self.work / "effect.log").as_posix()
        return self.child(
            f"import time\ntime.sleep({sleep})\n"
            f'open({marker!r}, "a", encoding="utf-8").write("ran\\n")\n'
            + self.write_result('json.dumps({"outcome": "delivered"})')
        )

    def effect_lines(self) -> int:
        path = self.work / "effect.log"
        return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    def test_same_identity_repeated_does_not_duplicate_the_unit(self) -> None:
        script = self.effect_script()
        self.assertEqual(self.start(script)[0], 0)
        self.assertEqual(self.wait()[0], 0)
        code, again = self.start(script)
        self.assertEqual(code, 0)
        self.assertTrue(again["reused"])
        self.assertEqual(again["state"], "exited")
        self.assertEqual(self.wait()[0], 0)
        self.assertEqual(self.effect_lines(), 1)

    def test_concurrent_start_runs_the_unit_once(self) -> None:
        script = self.effect_script(sleep=0.4)
        outcomes: list[tuple[int, dict]] = []
        lock = threading.Lock()

        def launch() -> None:
            received = self.start(script)
            with lock:
                outcomes.append(received)

        threads = [threading.Thread(target=launch) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(outcomes), 4)
        for code, payload in outcomes:
            self.assertEqual(code, 0, payload)
        self.assertEqual(self.wait()[0], 0)
        time.sleep(0.3)
        self.assertEqual(self.effect_lines(), 1)

    def test_divergent_manifest_is_refused_and_never_reuses_the_result(self) -> None:
        script = self.effect_script()
        self.start(script)
        self.wait()
        other = self.child('sys.exit(0)\n', name="other.py")
        code, refusal = self.start(other)
        self.assertEqual(code, tl_job.EXIT_CONFLICT)
        self.assertEqual(refusal["state"], "conflict")
        self.assertNotIn("outcome", refusal)
        code, refusal = self.start(script, authorization="story:T012/authorization:other")
        self.assertEqual(code, tl_job.EXIT_CONFLICT)
        self.assertEqual(self.effect_lines(), 1)


class FailureTest(JobCase):
    def test_nonexistent_command_fails_explicitly_with_no_effects(self) -> None:
        missing = str(self.work / "there-is-no-such-binary")
        code, receipt = self.run_cli(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "30",
            "--", missing,
        )
        self.assertEqual(code, 0)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_UNIT_FAILED)
        self.assertEqual(result["state"], "start_failed")
        self.assertEqual(result["effects"], "none")
        self.assertNotIn("outcome", result)

    def test_nonzero_exit_is_reported_as_unit_failure(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "failed"})') + "sys.exit(3)\n")
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_UNIT_FAILED)
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["outcome"], "failed")

    def test_timeout_marks_uncertain_effects(self) -> None:
        script = self.child("import time\ntime.sleep(30)\n")
        self.start(script, timeout="1")
        code, result = self.wait(timeout="45")
        self.assertEqual(code, tl_job.EXIT_TIMEOUT)
        self.assertEqual(result["state"], "timeout")
        self.assertEqual(result["effects"], "uncertain")

    def test_empty_return_never_becomes_success(self) -> None:
        script = self.child('sys.stdout.write("tudo certo, entrega aprovada\\n")\n')
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["result_status"], "missing")
        self.assertEqual(result["effects"], "uncertain")
        self.assertNotIn("outcome", result)

    def test_truncated_or_malformed_result_is_indeterminate(self) -> None:
        script = self.child(self.write_result('\'{"outcome": "deliv\''))
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["result_status"], "malformed")

    def test_outcome_outside_the_allowlist_is_refused(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "aprovado"})'))
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["result_status"], "malformed")

    def test_oversized_result_file_is_refused(self) -> None:
        script = self.child(
            self.write_result('json.dumps({"outcome": "delivered", "decision": "a" * %d})' % (tl_job.MAX_RESULT_BYTES + 10))
        )
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["result_status"], "oversized")

    def test_blocked_and_ready_for_delivery_stay_distinct(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "blocked", "blockers": ["falta prova"]})'))
        self.start(script, unit="T012-a")
        code, blocked = self.wait(unit="T012-a")
        self.assertEqual(code, tl_job.EXIT_UNIT_FAILED)
        self.assertEqual(blocked["outcome"], "blocked")
        self.assertEqual(blocked["blockers"], ["falta prova"])
        ready = self.child(self.write_result('json.dumps({"outcome": "ready_for_delivery"})'), name="ready.py")
        self.start(ready, unit="T012-b")
        code, delivered = self.wait(unit="T012-b")
        self.assertEqual(code, 0)
        self.assertEqual(delivered["outcome"], "ready_for_delivery")

    def test_wait_timeout_is_not_a_unit_result(self) -> None:
        script = self.child("import time\ntime.sleep(20)\n")
        self.start(script, timeout="2")
        code, receipt = self.wait(timeout="0.3")
        self.assertEqual(code, tl_job.EXIT_TIMEOUT)
        self.assertEqual(receipt["state"], "wait_timeout")
        self.assertNotIn("outcome", receipt)

    def test_result_without_terminal_state_is_indeterminate(self) -> None:
        script = self.child("import time\ntime.sleep(20)\n")
        self.start(script, timeout="2")
        code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertIn("error", receipt)


class InheritedResultTest(JobCase):
    """A result file speaks for a unit only when that unit is the one that wrote it."""

    def start_with_result_file(self, script: Path, result_file: str) -> tuple[int, dict]:
        return self.run_cli(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "30",
            "--result-file", result_file, "--", sys.executable, str(script),
        )

    def test_a_success_left_at_the_result_file_is_never_inherited_by_a_new_unit(self) -> None:
        receipts = self.work / "receipts"
        receipts.mkdir()
        (receipts / "T012-1.json").write_text(
            json.dumps({"outcome": "delivered", "next_action": "conferir"}), encoding="utf-8"
        )
        sentinel = self.work / "the-unit-ran"
        # Exits zero without ever touching TL_JOB_RESULT: the only success on disk is the one
        # written before, and the sentinel says whether this unit was spawned at all.
        script = self.child('open(%r, "w", encoding="utf-8").write("ran")\n' % str(sentinel))
        code, _ = self.start_with_result_file(script, "receipts/T012-1.json")
        self.assertEqual(code, 0)
        code, result = self.wait()
        self.assertNotEqual(code, 0, "a result from an earlier unit must never answer as success")
        self.assertEqual(code, tl_job.EXIT_UNIT_FAILED)
        self.assertEqual(result["state"], "start_failed")
        self.assertEqual(result["effects"], "none")
        self.assertNotIn("outcome", result)
        self.assertFalse(sentinel.exists(), "the refusal comes before the spawn")

    def test_a_result_file_that_the_unit_itself_creates_is_still_admitted(self) -> None:
        (self.work / "receipts").mkdir()
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        code, _ = self.start_with_result_file(script, "receipts/T012-2.json")
        self.assertEqual(code, 0)
        code, result = self.wait()
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "delivered")


class UninspectableResultTest(JobCase):
    """Absence of the result file has to be proven, never assumed from a failed inspection.

    The guard above binds the admitted payload to this run by requiring the path to be absent
    before the spawn. `os.path.lexists` answers `False` for a path whose inspection was denied
    exactly as it does for one that is missing, so that spelling would read an uninspectable
    path as a clean slate, spawn the unit and then admit whatever the path already held.
    """

    @contextlib.contextmanager
    def denied(self, target: Path, error: OSError):  # type: ignore[no-untyped-def]
        """Deny the inspection of one path only; every other path is inspected as usual."""
        real = tl_job.os.lstat

        def guarded(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            if Path(os.fsdecode(path)) == target:
                raise error
            return real(path, *args, **kwargs)

        with mock.patch.object(tl_job.os, "lstat", guarded):
            yield

    def test_the_helper_tells_a_denied_inspection_apart_from_a_real_absence(self) -> None:
        target = self.work / "receipt.json"
        manifest = {"result_file": str(target)}
        self.assertIsNone(tl_job.unbound_result(manifest), "a name that is really absent binds nothing")
        for error in (PermissionError(13, "permission denied"), OSError(5, "input/output error")):
            with self.subTest(error=type(error).__name__), self.denied(target, error):
                reason = tl_job.unbound_result(manifest)
                self.assertIsNotNone(reason, "an inspection that failed is not an absence")
                self.assertIn("cannot be inspected", reason or "")
        # The distinction is the exception, not the wording: only absence itself reads as absent.
        with self.denied(target, FileNotFoundError(2, "no such file or directory")):
            self.assertIsNone(tl_job.unbound_result(manifest))
        # And a path that really is there keeps its own reason, unchanged by this round.
        target.write_text("{}", encoding="utf-8")
        self.assertIn("already exists", tl_job.unbound_result(manifest) or "")

    def test_a_result_path_that_cannot_be_inspected_runs_no_command_at_all(self) -> None:
        marker = self.work / "the-unit-ran"
        script = self.child('open(%r, "w", encoding="utf-8").write("ran")\n' % str(marker))
        job_dir = self.claim(script, timeout=30.0)
        with self.denied(job_dir / "unit-result.json", PermissionError(13, "permission denied")):
            code = tl_job.supervise(str(self.state), "T012")
        # The transport worked and wrote its one terminal file; the refusal is inside it.
        self.assertEqual(code, tl_job.EXIT_OK)
        self.assertFalse(marker.exists(), "the unit was spawned although its result path was not inspectable")
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "start_failed")
        self.assertEqual(result["effects"], "none")
        self.assertNotIn("outcome", result)
        self.assertIn("cannot be inspected", result["detail"])
        self.assertFalse(result["containment"]["unit_ran"])
        self.assertFalse(result["containment"]["established"])

    def test_the_same_arrangement_runs_the_command_when_the_path_is_inspectable(self) -> None:
        """The discrimination: the denial is what refuses, not the arrangement around it."""
        marker = self.work / "the-unit-ran"
        script = self.child('open(%r, "w", encoding="utf-8").write("ran")\n' % str(marker))
        job_dir = self.claim(script, timeout=30.0)
        self.assertEqual(tl_job.supervise(str(self.state), "T012"), tl_job.EXIT_OK)
        self.assertTrue(marker.exists(), "the unit never ran; the case above would prove nothing")
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "exited")
        self.assertEqual(result["exit_code"], 0)


class InputTest(JobCase):
    def test_unit_identifier_cannot_escape_the_state_directory(self) -> None:
        script = self.child("pass\n")
        for unit in ("../escape", "a/b", "", "." * 3, "é-unit", "x" * (tl_job.UNIT_MAX + 1)):
            code, receipt = self.run_cli(
                "start", "--state-dir", str(self.state), "--unit", unit,
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                "--", sys.executable, str(script),
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, unit)
            self.assertEqual(receipt["state"], "invalid_input", unit)
        self.assertFalse((self.state / "jobs").exists())

    def test_result_file_must_stay_inside_the_working_directory(self) -> None:
        script = self.child("pass\n")
        for candidate in ("../outside.json", str(self.root / "absolute.json")):
            code, receipt = self.run_cli(
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                "--result-file", candidate, "--", sys.executable, str(script),
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, candidate)

    def link(self, source: Path, target: Path, directory: bool) -> None:
        """Skip only where the platform refuses the link; on Linux this always runs.

        A Windows session without SeCreateSymbolicLinkPrivilege still creates a directory
        junction, so the directory case is exercised there too.
        """
        try:
            os.symlink(target, source, target_is_directory=directory)
            return
        except (OSError, NotImplementedError, AttributeError) as exc:
            if os.name != "nt":
                raise
            reason = exc
        if directory:
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source), str(target)], capture_output=True
            )
            if junction.returncode == 0:
                return
        self.skipTest(f"this Windows session cannot create the link: {reason}")

    def escape_is_refused(self, candidate: str, outside: Path) -> None:
        script = self.child("pass\n")
        code, receipt = self.run_cli(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
            "--result-file", candidate, "--", sys.executable, str(script),
        )
        self.assertEqual(code, tl_job.EXIT_USAGE, candidate)
        self.assertEqual(receipt["state"], "invalid_input", candidate)
        self.assertEqual(list(outside.iterdir()), [], "nothing was created outside the working directory")
        self.assertFalse((self.state / "jobs" / "T012").exists())

    def test_result_file_through_a_linked_directory_out_of_the_tree_is_refused(self) -> None:
        """A contained spelling is not containment: the link is resolved before accepting."""
        outside = self.root / "outside-dir"
        outside.mkdir()
        self.link(self.work / "escape-dir", outside, directory=True)
        self.escape_is_refused("escape-dir/out.json", outside)

    def test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused(self) -> None:
        outside = self.root / "outside-file"
        outside.mkdir()
        self.link(self.work / "escape-file.json", outside / "leak.json", directory=False)
        self.escape_is_refused("escape-file.json", outside)

    def test_a_link_that_stays_inside_the_tree_is_still_accepted(self) -> None:
        inner = self.work / "reports"
        inner.mkdir()
        self.link(self.work / "inside-dir", inner, directory=True)
        job_dir = tl_job.job_directory(tl_job.check_state_dir(str(self.state)), "T012")
        chosen = tl_job.check_result_file("inside-dir/out.json", tl_job.check_cwd(str(self.work)), job_dir)
        # The lexical spelling is preserved, so identity does not depend on the resolution.
        self.assertEqual(chosen, Path(os.path.normpath(tl_job.check_cwd(str(self.work)) / "inside-dir/out.json")))

    def every_command_refuses(self, outside: Path) -> None:
        """Reading commands are checked too, not only the one that writes."""
        script = self.child("pass\n")
        calls = (
            (
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                "--", sys.executable, str(script),
            ),
            ("status", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "10"),
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
        )
        for call in calls:
            started = time.monotonic()
            code, receipt = self.run_cli(*call)
            self.assertEqual(code, tl_job.EXIT_USAGE, call[0])
            self.assertEqual(receipt["state"], "invalid_input", call[0])
            # A refusal before the loop, not a wait that expired.
            self.assertLess(time.monotonic() - started, 8.0, call[0])
            self.assertEqual(sorted(p.name for p in outside.iterdir()), [], call[0])

    def test_jobs_component_linked_out_of_the_state_directory_is_refused(self) -> None:
        """A valid state directory whose `jobs` is a link elsewhere writes nothing outside."""
        outside = self.root / "outside-jobs"
        outside.mkdir()
        self.state.mkdir()
        self.link(self.state / "jobs", outside, directory=True)
        self.every_command_refuses(outside)

    def test_unit_directory_linked_out_of_the_state_directory_is_refused(self) -> None:
        outside = self.root / "outside-unit"
        outside.mkdir()
        (self.state / "jobs").mkdir(parents=True)
        self.link(self.state / "jobs" / "T012", outside, directory=True)
        self.every_command_refuses(outside)

    def test_anchors_component_linked_out_of_the_state_directory_is_refused(self) -> None:
        """The bindings tree is a component of the state directory, so a link there is an escape.

        `write_anchor` creates this directory when it is missing and writes the binding of the
        unit into it. A link planted before the first start made that write land outside the
        state directory the caller named, under a name the caller never chose.
        """
        outside = self.root / "outside-anchors"
        outside.mkdir()
        self.state.mkdir()
        self.link(self.state / tl_job.ANCHORS_DIR, outside, directory=True)
        marker = self.work / "the-unit-ran"
        script = self.child('open(%r, "w", encoding="utf-8").write("ran")\n' % str(marker))
        code, receipt = self.start(script)
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertEqual(receipt["state"], "invalid_input")
        self.assertIn("anchors directory", receipt["error"])
        self.assertEqual(receipt["effects"], "none")
        self.assertEqual(sorted(p.name for p in outside.iterdir()), [], "a binding was published outside")
        self.assertFalse(marker.exists(), "the command ran under a state tree that was refused")
        self.assertFalse((self.state / "jobs").exists(), "a job was claimed under a state tree that was refused")
        # The refusal comes before any write, so the reading commands answer the same way.
        self.every_command_refuses(outside)

    def test_an_anchors_link_that_stays_inside_the_state_directory_still_runs(self) -> None:
        """The discrimination: resolution refuses the escape without refusing a contained link."""
        real_anchors = self.state / "real-anchors"
        real_anchors.mkdir(parents=True)
        self.link(self.state / tl_job.ANCHORS_DIR, real_anchors, directory=True)
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.assertEqual(self.start(script)[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait()[0], tl_job.EXIT_OK)
        self.assertEqual(sorted(p.name for p in real_anchors.iterdir()), ["T012.json"])

    def test_a_linked_state_tree_that_stays_inside_still_runs_once(self) -> None:
        """The resolution refuses the escape without breaking a contained link or idempotency."""
        real_jobs = self.state / "real-jobs"
        real_jobs.mkdir(parents=True)
        self.link(self.state / "jobs", real_jobs, directory=True)
        script = self.child(self.write_result('json.dumps({"outcome": "delivered", "next_action": "conferir"})'))
        self.assertEqual(self.start(script)[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait()[0], tl_job.EXIT_OK)
        code, again = self.start(script)
        self.assertEqual(code, tl_job.EXIT_OK)
        self.assertTrue(again["reused"])
        self.assertEqual(sorted(p.name for p in real_jobs.iterdir()), ["T012"])

    def test_state_directory_inside_the_package_is_refused(self) -> None:
        script = self.child("pass\n")
        inside = tl_job.PACKAGE_ROOT / "docs" / "state"
        code, receipt = self.run_cli(
            "start", "--state-dir", str(inside), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
            "--", sys.executable, str(script),
        )
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertFalse(inside.exists())

    def test_missing_command_is_refused_instead_of_invented(self) -> None:
        code, receipt = self.run_cli(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
        )
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertIn("invents", receipt["error"])

    # Text that is not a number belongs here too: the refusal must come from the JSON
    # boundary, not from the argument parser exiting with its own usage message.
    BAD_TIMEOUTS = (
        "0", "-1", "nan", "inf", "-inf", str(tl_job.TIMEOUT_MAX + 1),
        "nope", "", " ", "1,5", "10s", "0x10", "None", "1e",
    )

    def test_invalid_timeout_is_refused_by_start_before_any_claim(self) -> None:
        script = self.child("pass\n")
        for value in self.BAD_TIMEOUTS:
            # `--timeout=<value>` keeps a negative number from looking like another option.
            code, receipt = self.run_cli(
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), f"--timeout={value}",
                "--", sys.executable, str(script),
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, value)
            self.assertEqual(receipt["state"], "invalid_input", value)
            self.assertEqual(set(receipt), {"schema", "job_id", "unit", "state", "effects", "error"}, value)
            self.assertEqual(receipt["effects"], "none", value)
        self.assertFalse((self.state / "jobs").exists())

    def test_invalid_timeout_is_refused_by_wait_before_the_loop(self) -> None:
        """An unusable bound must be refused at once, never waited on until it expires."""
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        for value in self.BAD_TIMEOUTS:
            started = time.monotonic()
            code, receipt = self.run_cli(
                "wait", "--state-dir", str(self.state), "--unit", "T012", f"--timeout={value}"
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, value)
            self.assertEqual(receipt["state"], "invalid_input", value)
            self.assertEqual(set(receipt), {"schema", "job_id", "unit", "state", "effects", "error"}, value)
            self.assertLess(time.monotonic() - started, 30.0, value)
        self.wait()

    def test_text_timeout_answers_in_json_without_claiming_or_waiting(self) -> None:
        """A value like `nope` must reach the JSON refusal, not the parser's own exit."""
        script = self.child("pass\n")
        for value in ("nope", "", "1,5"):
            started = time.monotonic()
            code, receipt = self.run_cli(
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), f"--timeout={value}",
                "--", sys.executable, str(script),
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, value)
            self.assertEqual(receipt["state"], "invalid_input", value)
            self.assertIn("seconds", receipt["error"], value)
            self.assertLessEqual(len(json.dumps(receipt).encode("utf-8")), tl_job.DEFAULT_MAX_BYTES, value)

            code, receipt = self.run_cli(
                "wait", "--state-dir", str(self.state), "--unit", "T012", f"--timeout={value}"
            )
            self.assertEqual(code, tl_job.EXIT_USAGE, value)
            self.assertEqual(receipt["state"], "invalid_input", value)
            self.assertLess(time.monotonic() - started, 30.0, value)
        # Nothing was claimed, nothing was written: the refusal came before any state.
        self.assertFalse(self.state.exists())

    def test_missing_working_directory_is_refused(self) -> None:
        script = self.child("pass\n")
        code, _ = self.run_cli(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.root / "absent"), "--timeout", "10",
            "--", sys.executable, str(script),
        )
        self.assertEqual(code, tl_job.EXIT_USAGE)

    def test_identity_does_not_change_when_the_tree_starts_to_exist(self) -> None:
        state = tl_job.check_state_dir(str(self.state))
        job_dir = tl_job.job_directory(state, "T012")
        before = tl_job.manifest_fingerprint(
            tl_job.build_manifest("T012", AUTHORIZATION, self.work, ["x"], 10.0, tl_job.check_result_file(None, self.work, job_dir))
        )
        job_dir.mkdir(parents=True)
        (job_dir / "unit-result.json").write_text("{}", encoding="utf-8")
        state_again = tl_job.check_state_dir(str(self.state))
        job_dir_again = tl_job.job_directory(state_again, "T012")
        after = tl_job.manifest_fingerprint(
            tl_job.build_manifest(
                "T012", AUTHORIZATION, self.work, ["x"], 10.0, tl_job.check_result_file(None, self.work, job_dir_again)
            )
        )
        self.assertEqual(job_dir_again, job_dir)
        self.assertEqual(after, before)

    def test_unknown_unit_is_refused_by_status_and_wait(self) -> None:
        self.assertEqual(self.status("T999")[0], tl_job.EXIT_USAGE)
        self.assertEqual(self.wait("T999", timeout="1")[0], tl_job.EXIT_USAGE)


class StatePathTest(JobCase):
    def test_status_reports_without_reading_any_log(self) -> None:
        script = self.child(
            'sys.stdout.write("ruido " * 40000)\n' + self.write_result('json.dumps({"outcome": "delivered"})')
        )
        self.start(script)
        self.wait()
        opened: list[str] = []
        real_open = builtins.open
        real_read_text = Path.read_text

        def spy_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        def spy_read_text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            opened.append(str(self))
            return real_read_text(self, *args, **kwargs)

        buffer = io.StringIO()
        with mock.patch.object(builtins, "open", spy_open), mock.patch.object(Path, "read_text", spy_read_text):
            with contextlib.redirect_stdout(buffer):
                code = tl_job.main(["status", "--state-dir", str(self.state), "--unit", "T012"])
        self.assertEqual(code, 0)
        self.assertTrue(opened)
        for path in opened:
            self.assertFalse(path.endswith(("stdout.log", "stderr.log")), path)
        json.loads(buffer.getvalue())

    def test_status_file_keeps_a_snapshot_without_history(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        self.wait()
        status = json.loads((self.job_dir() / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(set(status), {"schema", "job_id", "unit", "state", "pid", "updated_at"})
        for value in status.values():
            self.assertNotIsInstance(value, list)
        self.assertLess((self.job_dir() / "status.json").stat().st_size, 400)

    def test_terminal_result_appears_atomically(self) -> None:
        script = self.child("import time\ntime.sleep(1.0)\n" + self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        result_path = self.job_dir() / "result.json"
        reads = 0
        deadline = time.monotonic() + 60
        while not result_path.exists() and time.monotonic() < deadline:
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = None
            if payload is not None:
                self.assertIn("state", payload)
                reads += 1
            time.sleep(0.01)
        self.assertEqual(self.wait()[0], 0)
        self.assertTrue(json.loads(result_path.read_text(encoding="utf-8"))["state"] == "exited")
        residue = [path.name for path in self.job_dir().iterdir() if ".tmp-" in path.name]
        self.assertEqual(residue, [])
        first = result_path.read_bytes()
        self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(result_path.read_bytes(), first)

    def test_detach_uses_the_branch_of_this_platform(self) -> None:
        kwargs = tl_job.spawn_kwargs(detached=True)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], 0x08000000 | 0x00000008)
            self.assertNotIn("start_new_session", kwargs)
        else:
            self.assertTrue(kwargs["start_new_session"])
            self.assertNotIn("creationflags", kwargs)
        self.assertTrue(kwargs["close_fds"])


GRANDCHILD = """import time
work = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(work, "spawned.txt"), "w", encoding="utf-8").write("1")
beat = os.path.join(work, "beat.txt")
deadline = time.time() + 90
while time.time() < deadline:
    with open(beat, "a", encoding="utf-8") as handle:
        handle.write("x")
        handle.flush()
    time.sleep(0.1)
"""

PARENT = """import subprocess, time
work = os.path.dirname(os.path.abspath(__file__))
subprocess.Popen([sys.executable, os.path.join(work, "grandchild.py")], cwd=work)
time.sleep(120)
"""


class ContainmentTest(JobCase):
    """The unit owns a tree, not one process; ending the unit has to end the tree."""

    def test_descendant_stops_working_when_the_unit_times_out(self) -> None:
        self.child(GRANDCHILD, name="grandchild.py")
        parent = self.child(PARENT, name="parent.py")
        code, _ = self.start(parent, timeout="4")
        self.assertEqual(code, 0)
        code, result = self.wait(timeout="60")
        self.assertEqual(code, tl_job.EXIT_TIMEOUT)
        self.assertEqual(result["state"], "timeout")
        self.assertEqual(result["effects"], "uncertain")
        beat = self.work / "beat.txt"
        self.assertTrue((self.work / "spawned.txt").exists(), "the descendant never ran; this case would prove nothing")
        time.sleep(1.0)
        first = beat.stat().st_size
        self.assertGreater(first, 0, "the descendant never wrote; this case would prove nothing")
        time.sleep(2.0)
        self.assertEqual(beat.stat().st_size, first, "the descendant kept working after the unit was ended")

    def test_receipt_declares_the_containment_actually_used(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        code, result = self.wait()
        self.assertEqual(code, 0)
        containment = result["containment"]
        self.assertTrue(containment["established"])
        self.assertEqual(containment["kind"], "windows_job_object" if os.name == "nt" else "posix_process_group")
        # Exit zero is only reachable through a proven scope: an unproven sweep is indeterminate.
        self.assertIn(containment["swept"], set(tl_job.PROVEN_SCOPES))
        self.assertNotIn("sweep_failed", containment)
        # And so is the accounting of what could have left that scope before the sweep reached it.
        self.assertIn(containment["accounted"], set(tl_job.ACCOUNTED_SCOPES))
        self.assertNotIn("account_failed", containment)


WINDOWS_ONLY = "the extended `\\\\?\\` spelling only exists on Windows"


class PathSpellingTest(unittest.TestCase):
    """Two spellings of one directory are not an escape; a real escape still is.

    Under concurrent starts Windows sometimes resolves the same directory to its
    extended `\\\\?\\` spelling, which used to refuse a legitimate claim.
    """

    @contextlib.contextmanager
    def spelled_extended(self, *paths: Path):  # type: ignore[no-untyped-def]
        plain = os.path.realpath
        answers = {str(path): "\\\\?\\" + str(path) for path in paths}
        with mock.patch.object(os.path, "realpath", lambda path: answers.get(str(path), plain(path))):
            yield

    @unittest.skipUnless(os.name == "nt", WINDOWS_ONLY)
    def test_extended_spelling_of_the_same_directory_is_not_read_as_an_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl-spelling-") as temporary:
            jobs = Path(temporary) / "state" / "jobs"
            jobs.mkdir(parents=True)
            with self.spelled_extended(jobs):
                self.assertEqual(tl_job.real(jobs), Path(str(jobs)))
                # The claim that used to be refused while another start created `jobs`.
                tl_job.contained(jobs / "T012", jobs, "would be a false refusal")

    @unittest.skipUnless(os.name == "nt", WINDOWS_ONLY)
    def test_extended_spelling_does_not_let_a_path_out_of_the_state_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl-spelling-") as temporary:
            root = Path(temporary)
            jobs = root / "state" / "jobs"
            jobs.mkdir(parents=True)
            outside = root / "elsewhere" / "T012"
            with self.spelled_extended(jobs, outside):
                with self.assertRaises(tl_job.JobError) as refusal:
                    tl_job.contained(outside, jobs, "escapes the state directory")
        self.assertEqual(refusal.exception.code, tl_job.EXIT_USAGE)


class FakeJobApi:
    """Controlled stand-in for kernel32: the ending primitive answers as told."""

    def __init__(self, terminates: bool) -> None:
        self.terminates = terminates
        self.calls: list[int] = []

    def TerminateJobObject(self, handle, code):  # noqa: N802 - mirrors the Win32 name
        self.calls.append(code)
        return 1 if self.terminates else 0


class SweepFailureTest(unittest.TestCase):
    """A failed ending primitive must never be reported as a contained tree.

    These cases drive the primitive itself in a controlled copy, on any host, and
    check the discriminating difference: the same code path reports containment
    when the primitive works and refuses to when it does not.
    """

    def job_object(self, api: FakeJobApi) -> tl_job.JobObjectContainment:
        containment = object.__new__(tl_job.JobObjectContainment)
        containment.api = api
        containment.handle = 0x1234
        return containment

    def posix_group(self) -> tl_job.PosixSessionContainment:
        containment = tl_job.PosixSessionContainment()
        containment.pgid = 424242
        containment.reaped = False
        return containment

    @contextlib.contextmanager
    def killpg(self, behavior):  # type: ignore[no-untyped-def]
        """Run the POSIX branch anywhere: the signal numbers are only names here."""
        calls: list[tuple[int, int]] = []

        def fake(pgid: int, number: int) -> None:
            calls.append((pgid, number))
            outcome = behavior(len(calls))
            if outcome is not None:
                raise outcome

        with mock.patch.object(tl_job.os, "killpg", fake, create=True), mock.patch.object(
            tl_job.signal, "SIGKILL", 9, create=True
        ), mock.patch.object(tl_job.signal, "SIGTERM", 15, create=True):
            yield calls

    def verdict(self, containment, sweep, accounted=None):  # type: ignore[no-untyped-def]
        """What a caller would actually read: the record and the resulting classification.

        A proven sweep is only half the answer, so the accounting of escaped descendants is
        supplied here exactly when the case under test is about a sweep that proved something.
        """
        account = tl_job.Account(accounted) if accounted else None
        record = containment.describe(sweep, account)
        admitted = {"result_status": "admitted", "outcome": "delivered", "containment": record}
        return record, tl_job.classify("exited", 0, admitted)

    def test_job_object_that_refuses_to_terminate_is_not_reported_as_contained(self) -> None:
        failing = self.job_object(FakeJobApi(terminates=False))
        with mock.patch.object(tl_job.ctypes, "get_last_error", lambda: 5, create=True):
            sweep = failing.sweep(process=None, graceful=False)
        record, (effects, code) = self.verdict(failing, sweep)
        self.assertEqual(sweep.scope, "unproven")
        self.assertIn("TerminateJobObject", record["sweep_failed"])
        self.assertEqual((effects, code), ("uncertain", tl_job.EXIT_INDETERMINATE))
        self.assertEqual(failing.api.calls, [1])

    def test_job_object_that_terminates_is_the_only_case_reported_as_contained(self) -> None:
        working = self.job_object(FakeJobApi(terminates=True))
        sweep = working.sweep(process=None, graceful=False)
        record, (effects, code) = self.verdict(working, sweep, accounted="job_object")
        self.assertEqual(sweep.scope, "job_object")
        self.assertNotIn("sweep_failed", record)
        self.assertEqual((effects, code), ("known", tl_job.EXIT_OK))

    def test_process_group_that_refuses_the_kill_is_not_reported_as_contained(self) -> None:
        containment = self.posix_group()
        with self.killpg(lambda _: PermissionError(1, "operation not permitted")) as calls:
            sweep = containment.sweep(process=None, graceful=False)
        record, (effects, code) = self.verdict(containment, sweep)
        self.assertEqual(sweep.scope, "unproven")
        self.assertIn("PermissionError", record["sweep_failed"])
        self.assertEqual((effects, code), ("uncertain", tl_job.EXIT_INDETERMINATE))
        # Only the group this supervisor owns was ever signalled.
        self.assertEqual({pgid for pgid, _ in calls}, {424242})

    def test_process_group_that_is_provably_gone_still_counts_as_covered(self) -> None:
        """A group that no longer exists is not a failed primitive: nothing survived it."""
        containment = self.posix_group()
        with self.killpg(lambda _: ProcessLookupError(3, "no such process")) as calls:
            sweep = containment.sweep(process=None, graceful=False)
        record, (effects, code) = self.verdict(containment, sweep, accounted="subreaper_scan")
        self.assertEqual(sweep.scope, "process_group")
        self.assertNotIn("sweep_failed", record)
        self.assertEqual((effects, code), ("known", tl_job.EXIT_OK))
        self.assertEqual(calls, [(424242, 9)])

    def test_graceful_sweep_stops_claiming_when_the_first_signal_fails(self) -> None:
        containment = self.posix_group()
        with self.killpg(lambda _: PermissionError(1, "operation not permitted")) as calls:
            sweep = containment.sweep(process=None, graceful=True)
        self.assertEqual(sweep.scope, "unproven")
        self.assertIn("PermissionError", sweep.failure or "")
        # It refuses at once instead of waiting out the grace and killing a stranger.
        self.assertEqual(calls, [(424242, 15)])

    def test_graceful_sweep_that_works_reports_the_group_after_the_kill(self) -> None:
        containment = self.posix_group()
        with self.killpg(lambda _: None) as calls:
            sweep = containment.sweep(process=None, graceful=True)
        self.assertEqual(sweep.scope, "process_group")
        self.assertIsNone(sweep.failure)
        self.assertEqual(calls, [(424242, 15), (424242, 9)])

    def test_a_reaped_leader_is_never_signalled_again(self) -> None:
        containment = self.posix_group()
        containment.reaped = True
        with self.killpg(lambda _: None) as calls:
            sweep = containment.sweep(process=None, graceful=False)
        self.assertEqual(sweep.scope, "unproven")
        self.assertIsNone(sweep.failure, "abstaining is not a failed primitive")
        self.assertEqual(calls, [])


class SweepFailureReportTest(JobCase):
    def test_a_failed_sweep_recorded_on_disk_is_read_back_as_indeterminate(self) -> None:
        """The refusal survives the file boundary: `result` re-reads and re-classifies it."""
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        self.assertEqual(self.wait()[0], tl_job.EXIT_OK)
        path = self.job_dir() / "result.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["containment"] = dict(payload["containment"], swept="unproven", sweep_failed="forced failure")
        path.write_text(json.dumps(payload), encoding="utf-8")
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["effects"], "uncertain")
        self.assertEqual(result["outcome"], "delivered")


POSIX_ONLY = "the process group branch only exists on POSIX; the Linux CI exercises this case"

SURVIVOR = """import time
work = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(work, "survivor-pid.txt"), "w", encoding="utf-8").write(str(os.getpid()))
beat = os.path.join(work, "survivor-beat.txt")
# Self-bounded: this descendant is meant to outlive the unit, never the test run.
deadline = time.time() + 30
while time.time() < deadline:
    with open(beat, "a", encoding="utf-8") as handle:
        handle.write("x")
        handle.flush()
    time.sleep(0.05)
"""

LEAVING_LEADER = """import subprocess
work = os.path.dirname(os.path.abspath(__file__))
subprocess.Popen([sys.executable, os.path.join(work, "survivor.py")], cwd=work)
"""


class UnprovenSweepTest(JobCase):
    """A sweep that proves nothing must never read as a delivered unit.

    Without `waitid` the wait on the leader also reaps it, so the sweep abstains from
    signalling a pid that may already belong to somebody else: the scope is `unproven`
    and no primitive failed. The copy before this fix answered `effects: known` with
    exit zero while a descendant of the unit was still running and writing.
    """

    def end_survivor(self, pid_file: Path) -> None:
        """This case leaves a descendant alive on purpose; it is ended here by its own pid."""
        with contextlib.suppress(Exception):
            os.kill(int(pid_file.read_text(encoding="utf-8").strip()), signal.SIGKILL)

    @unittest.skipIf(os.name == "nt", POSIX_ONLY)
    def test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered(self) -> None:
        self.child(SURVIVOR, name="survivor.py")
        leader = self.child(
            LEAVING_LEADER + self.write_result('json.dumps({"outcome": "delivered"})'), name="leader.py"
        )
        job_dir = self.claim(leader, timeout=30.0)
        pid_file = self.work / "survivor-pid.txt"
        self.addCleanup(self.end_survivor, pid_file)

        with mock.patch.object(tl_job, "HAS_WAITID", False):
            code = tl_job.supervise(str(self.state), "T012")
        # The transport worked and wrote its one terminal file; the verdict is inside it.
        self.assertEqual(code, tl_job.EXIT_OK)
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "exited")
        self.assertEqual(result["exit_code"], 0)
        # The unit itself said it delivered, and nothing in the sweep failed.
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(result["containment"]["swept"], "unproven")
        self.assertNotIn("sweep_failed", result["containment"])
        self.assertEqual(result["effects"], "uncertain")
        self.assertIn("not proven ended", result["detail"])

        # What the old answer denied: a descendant of the unit is still alive and writing.
        self.appear(pid_file)
        self.assertTrue(pid_file.exists(), "the descendant never started; this case would prove nothing")
        beat = self.work / "survivor-beat.txt"
        self.appear(beat)
        self.assertTrue(beat.exists(), "the descendant never wrote; this case would prove nothing")
        first = beat.stat().st_size
        self.assertGreater(first, 0, "the descendant never wrote; this case would prove nothing")
        time.sleep(1.0)
        self.assertGreater(
            beat.stat().st_size, first, "the descendant already stopped; this case would prove nothing"
        )

        # The refusal survives the file boundary: collection re-reads it as indeterminate.
        code, reported = self.wait(timeout="10")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(reported["effects"], "uncertain")

    def test_an_unproven_scope_without_a_failure_is_indeterminate_on_any_platform(self) -> None:
        """The same classification, driven directly, so Windows covers the rule too."""
        record = {"kind": "posix_process_group", "established": True, "swept": "unproven"}
        admitted = {"result_status": "admitted", "outcome": "delivered", "containment": record}
        self.assertEqual(tl_job.classify("exited", 0, admitted), ("uncertain", tl_job.EXIT_INDETERMINATE))
        # A proven sweep only answers for the scope it swept, so each one is paired with the
        # accounting that covers what left that scope before it.
        for scope, accounted in (("job_object", "job_object"), ("process_group", "subreaper_scan")):
            proven = dict(admitted, containment=dict(record, swept=scope, accounted=accounted))
            self.assertEqual(tl_job.classify("exited", 0, proven), ("known", tl_job.EXIT_OK))
        self.assertEqual(set(tl_job.PROVEN_SCOPES), {"job_object", "process_group"})


LINUX_ONLY = (
    "escaping the swept scope needs `setsid` and the accounting needs the Linux subreaper plus "
    "`/proc`; the Linux CI exercises this case"
)

ESCAPEE = """import time
work = os.path.dirname(os.path.abspath(__file__))
target, source, delay = %(target)r, %(source)r, %(delay)r
# Leave the scope the supervisor can sweep: a session of its own on POSIX. On Windows the
# leader already spawned this process detached, with its own console and its own group.
if hasattr(os, "setsid"):
    os.setsid()
open(os.path.join(work, "left-the-scope.txt"), "w", encoding="utf-8").write(str(os.getpid()))
# Outlive the supervisor: past this sleep the lease is released, so no reader can tell this
# writing apart from the unit's own.
time.sleep(delay)
staged = target + ".staged"
with open(staged, "w", encoding="utf-8") as handle:
    handle.write(open(source, encoding="utf-8").read())
os.replace(staged, target)
open(os.path.join(work, "forged.txt"), "w", encoding="utf-8").write("1")
"""

ESCAPING_LEADER = """import subprocess, time
work = os.path.dirname(os.path.abspath(__file__))
# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP; the POSIX escape is done by the descendant itself.
flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0
subprocess.Popen(
    [sys.executable, os.path.join(work, "escapee.py")],
    cwd=work,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=flags,
)
# Exit only once the descendant is provably outside the scope a sweep can reach; otherwise
# this case would prove nothing about escapees.
marker = os.path.join(work, "left-the-scope.txt")
deadline = time.time() + 30
while not os.path.exists(marker) and time.time() < deadline:
    time.sleep(0.05)
"""


class EscapedDescendantTest(JobCase):
    """A descendant that leaves the swept scope must not be able to forge a delivery.

    The sweep reaches what is still inside the scope it swept. A descendant that left first
    survives it, and once the supervisor exits and drops its lease there is nobody left to
    tell its writing apart from the unit's: it can replace `result.json` with a complete,
    coherent, delivered record, and every field of that record is derivable from the claim.

    So the record alone cannot be the defense. What answers here is the accounting of
    escapees: the tree is ended before the lease is released, and where the platform cannot
    account for what escaped, the terminal answer is indeterminate instead of delivered.
    """

    def forgery(self, job_dir: Path) -> dict:
        """Stage the record an escapee would install: complete, coherent and a success.

        Written to a file of its own so the escapee only has to copy bytes; that is not a
        weakening, since every field here is derivable from `manifest.json` by any process
        that can read the job directory. The containment is forged at its strongest — swept
        and accounted by a proven scope — precisely because a forger can claim that too.
        """
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        forged = {
            "schema": manifest["schema"],
            "job_id": manifest["unit"],
            "unit": manifest["unit"],
            "state": "exited",
            "effects": "known",
            "exit_code": 0,
            "started_at": "2026-09-11T00:00:00Z",
            "finished_at": "2026-09-11T00:00:01Z",
            "authorization_fingerprint": manifest["authorization_fingerprint"],
            "manifest_fingerprint": tl_job.manifest_fingerprint(manifest),
            "logs": {"stdout": {"path": "stdout.log", "bytes": 0}, "stderr": {"path": "stderr.log", "bytes": 0}},
            "containment": {
                "kind": "windows_job_object" if os.name == "nt" else "posix_process_group",
                "established": True,
                "unit_ran": True,
                "swept": "job_object" if os.name == "nt" else "process_group",
                "accounted": "job_object" if os.name == "nt" else "subreaper_scan",
            },
            "result_status": "admitted",
            "outcome": "delivered",
            "next_action": "nada a fazer",
        }
        (self.work / "forgery.json").write_text(json.dumps(forged), encoding="utf-8")
        return forged

    def arrange(self, delay: float) -> Path:
        """Claim a unit whose leader spawns an escapee and then exits, writing no result."""
        job_dir = self.claim(self.child(ESCAPING_LEADER, name="leader.py"), timeout=40.0)
        self.forgery(job_dir)
        self.child(
            ESCAPEE % {"target": str(job_dir / "result.json"), "source": str(self.work / "forgery.json"), "delay": delay},
            name="escapee.py",
        )
        return job_dir

    def end_escapee(self) -> None:
        """Nothing should survive here, but a failing case must not leak a process either."""
        marker = self.work / "left-the-scope.txt"
        with contextlib.suppress(Exception):
            pid = int(marker.read_text(encoding="utf-8").strip())
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)

    def cannot_forge(self, delay: float, accounted: str) -> None:
        """Drive the escape end to end and read the answer the caller would read."""
        job_dir = self.arrange(delay)
        self.addCleanup(self.end_escapee)
        self.assertEqual(tl_job.supervise(str(self.state), "T012"), tl_job.EXIT_OK)

        # The premise: the descendant really did run and really did leave the swept scope.
        self.assertTrue((self.work / "left-the-scope.txt").exists(), "no descendant ever escaped here")
        record = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(record["containment"]["accounted"], accounted)
        self.assertNotIn("account_failed", record["containment"])
        # The unit wrote no result of its own, so nothing about it is delivered.
        self.assertNotEqual(record.get("outcome"), "delivered")

        # Past the delay the escapee would have replaced the terminal file; it is not there
        # to do it, and the answer stays the supervisor's own.
        time.sleep(delay + 2.0)
        self.assertFalse((self.work / "forged.txt").exists(), "an escaped descendant forged the terminal result")
        self.assertEqual(json.loads((job_dir / "result.json").read_text(encoding="utf-8")), record)
        code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertNotEqual(receipt.get("outcome"), "delivered", receipt)
        self.assertNotEqual(receipt["effects"], "known", receipt)
        self.assertNotEqual(code, tl_job.EXIT_OK, receipt)

    @unittest.skipUnless(sys.platform.startswith("linux"), LINUX_ONLY)
    def test_a_setsid_descendant_cannot_forge_a_delivered_result_after_the_lease(self) -> None:
        self.cannot_forge(5.0, "subreaper_scan")

    @unittest.skipUnless(os.name == "nt", "the job object branch only exists on Windows")
    def test_a_detached_descendant_cannot_leave_the_job_object_to_forge_one(self) -> None:
        """The same escape where it can be run here: breakaway is never granted on this job."""
        self.cannot_forge(5.0, "job_object")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_the_forged_record_would_be_delivered_if_it_ever_landed(self) -> None:
        """Why the accounting is the defense: the bytes themselves are indistinguishable.

        Planted by hand over a released lease, the very record the escapee carries is read as
        a proven ending and delivered. Nothing in it can be refused, which is exactly why the
        writer must not survive the supervisor that answers for it.
        """
        job_dir = self.arrange(60.0)
        # The lease of the claim, held by nobody: the file the claim named, with no holder.
        self.assertEqual(tl_job.termination_proof(job_dir), "proven")
        forged = self.forgery(job_dir)
        (job_dir / "result.json").write_text(json.dumps(forged), encoding="utf-8")
        code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        self.assertEqual(receipt["effects"], "known", receipt)
        self.assertEqual(receipt["outcome"], "delivered", receipt)

    def test_a_record_without_accounting_is_read_back_as_indeterminate(self) -> None:
        """The refusal survives the file boundary, on any platform: `result` re-classifies it."""
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.start(script)
        self.assertEqual(self.wait()[0], tl_job.EXIT_OK)
        path = self.job_dir() / "result.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for containment in (
            {key: value for key, value in payload["containment"].items() if key != "accounted"},
            dict(payload["containment"], accounted="unaccounted"),
            dict(payload["containment"], account_failed="2 escaped descendant(s) would not end"),
        ):
            with self.subTest(accounted=containment.get("accounted"), failed="account_failed" in containment):
                path.write_text(json.dumps(dict(payload, containment=containment)), encoding="utf-8")
                code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, result)
                self.assertEqual(result["effects"], "uncertain", result)
                # The unit still said what it said; only the reading of its effects changed.
                self.assertEqual(result["outcome"], "delivered", result)
        self.assertEqual(set(tl_job.ACCOUNTED_SCOPES), {"job_object", "subreaper_scan"})

    def test_the_posix_accounting_refuses_every_case_it_cannot_answer_for(self) -> None:
        """Driven directly in a controlled copy, so this rule is checked on any host."""
        ended = mock.Mock(pid=4242, returncode=0)
        running = mock.Mock(pid=4242, returncode=None)
        for no_subreaper, baseline, process, expected in (
            ("child subreaper is a Linux facility, unavailable on win32", set(), ended, "child subreaper"),
            (None, None, ended, "could not be listed"),
            (None, set(), running, "did not end"),
        ):
            with self.subTest(expected=expected):
                # Built field by field: `__init__` would call the Linux primitives, and the
                # question here is what `account` answers once they are unavailable.
                containment = object.__new__(tl_job.PosixSessionContainment)
                containment.no_subreaper = no_subreaper
                containment.baseline = baseline
                account = containment.account(process)
                self.assertEqual(account.scope, "unaccounted")
                self.assertIn(expected, account.failure or "")
                sweep = tl_job.Sweep("process_group")
                record = containment.describe(sweep, account)
                self.assertEqual(record["accounted"], "unaccounted")
                self.assertIn("account_failed", record)
                admitted = {"result_status": "admitted", "outcome": "delivered", "containment": record}
                self.assertEqual(
                    tl_job.classify("exited", 0, admitted), ("uncertain", tl_job.EXIT_INDETERMINATE)
                )

    def test_the_base_containment_answers_for_nothing_and_the_job_object_for_everything(self) -> None:
        """The two ends of the rule, both readable on any host."""
        bare = tl_job.Containment().account(mock.Mock(pid=1, returncode=0))
        self.assertEqual(bare.scope, "unaccounted")
        self.assertIn("cannot enumerate", bare.failure or "")
        job = object.__new__(tl_job.JobObjectContainment)
        account = job.account(mock.Mock(pid=1, returncode=0))
        self.assertEqual(account.scope, "job_object")
        self.assertIsNone(account.failure)


class AdmissionEssayTest(JobCase):
    """Synthetic essay on admitted bytes and number of chief queries.

    This counts bytes and calls in one controlled scenario. It is not a token
    measurement and it does not support any percentage claim about cost.
    """

    def test_admitted_bytes_are_a_small_fraction_of_the_raw_log(self) -> None:
        script = self.child(
            'sys.stdout.write("linha de log com detalhe irrelevante\\n" * 60000)\n'
            + self.write_result('json.dumps({"outcome": "delivered", "next_action": "conferir diff"})')
        )
        queries = 0
        code, start = self.start(script)
        queries += 1
        self.assertEqual(code, 0)
        code, result = self.wait()
        queries += 1
        self.assertEqual(code, 0)
        raw = (self.job_dir() / "stdout.log").stat().st_size
        admitted = len(json.dumps(start, ensure_ascii=False).encode("utf-8")) + len(
            json.dumps(result, ensure_ascii=False).encode("utf-8")
        )
        self.assertGreater(raw, 1000000)
        self.assertLess(admitted, raw // 100)
        self.assertEqual(queries, 2)
        self.assertLessEqual(admitted, 2 * tl_job.DEFAULT_MAX_BYTES)


class StateComponentTypeTest(JobCase):
    """A component of the state tree that is a file must answer JSON, not a traceback."""

    def commands(self) -> tuple[tuple[str, ...], ...]:
        script = self.child("pass\n")
        return (
            (
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                "--", sys.executable, str(script),
            ),
            ("status", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "10"),
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
        )

    def every_command_refuses_without_writing(self, occupied: Path) -> None:
        before = occupied.read_bytes()
        for call in self.commands():
            started = time.monotonic()
            code, receipt = self.run_cli(*call)
            self.assertEqual(code, tl_job.EXIT_USAGE, call[0])
            self.assertEqual(receipt["state"], "invalid_input", call[0])
            self.assertEqual(receipt["effects"], "none", call[0])
            self.assertLess(time.monotonic() - started, 8.0, call[0])
            # The file stays exactly as it was: no claim, no truncation, no directory beside it.
            self.assertTrue(occupied.is_file(), call[0])
            self.assertEqual(occupied.read_bytes(), before, call[0])

    def test_state_directory_that_is_a_file_is_refused_by_every_command(self) -> None:
        self.state.write_text("nao sou um diretorio", encoding="utf-8")
        self.every_command_refuses_without_writing(self.state)

    def test_jobs_component_that_is_a_file_is_refused_by_every_command(self) -> None:
        self.state.mkdir()
        (self.state / "jobs").write_text("nao sou um diretorio", encoding="utf-8")
        self.every_command_refuses_without_writing(self.state / "jobs")
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), ["jobs"])

    def test_unit_directory_that_is_a_file_is_refused_by_every_command(self) -> None:
        (self.state / "jobs").mkdir(parents=True)
        (self.state / "jobs" / "T012").write_text("nao sou um diretorio", encoding="utf-8")
        self.every_command_refuses_without_writing(self.state / "jobs" / "T012")
        self.assertEqual(sorted(p.name for p in (self.state / "jobs").iterdir()), ["T012"])

    def run_start_in_process(self, script: Path) -> tuple[int, dict]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = tl_job.main(
                [
                    "start", "--state-dir", str(self.state), "--unit", "T012",
                    "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                    "--", sys.executable, str(script),
                ]
            )
        text = buffer.getvalue().strip()
        self.assertTrue(text)
        return code, json.loads(text)

    def test_creation_denied_by_the_platform_answers_in_json_without_claiming(self) -> None:
        """The type check cannot win a race, so the creation boundary refuses in JSON too."""
        script = self.child("pass\n")
        with mock.patch.object(tl_job.Path, "mkdir", side_effect=PermissionError(13, "denied")):
            code, receipt = self.run_start_in_process(script)
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertEqual(receipt["state"], "invalid_input")
        self.assertEqual(receipt["effects"], "none")
        self.assertFalse(self.state.exists())

    def test_claim_denied_by_the_platform_answers_in_json_without_a_job_directory(self) -> None:
        script = self.child("pass\n")
        real_mkdir = tl_job.Path.mkdir

        def refuse_the_claim(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self.name == "T012":
                raise OSError(22, "name refused by the platform")
            return real_mkdir(self, *args, **kwargs)

        with mock.patch.object(tl_job.Path, "mkdir", refuse_the_claim):
            code, receipt = self.run_start_in_process(script)
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertEqual(receipt["state"], "invalid_input")
        self.assertEqual(receipt["effects"], "none")
        self.assertEqual(sorted(p.name for p in (self.state / "jobs").iterdir()), [])


class ReportAllowlistTest(JobCase):
    """`result` rebuilds its answer from an allowlist; it never forwards `result.json`."""

    NARRATIVA = "NARRATIVA-INJETADA: o agente conversou longamente sobre o problema"

    def terminal_result(self) -> Path:
        script = self.child(
            self.write_result('json.dumps({"outcome": "delivered", "next_action": "conferir diff"})')
        )
        self.assertEqual(self.start(script)[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait()[0], tl_job.EXIT_OK)
        return self.job_dir() / "result.json"

    def tamper(self, path: Path, change) -> None:  # type: ignore[no-untyped-def]
        payload = json.loads(path.read_text(encoding="utf-8"))
        change(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_untouched_terminal_result_is_still_reported_in_full(self) -> None:
        self.terminal_result()
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_OK)
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(result["next_action"], "conferir diff")
        self.assertEqual(result["effects"], "known")
        self.assertTrue(result["transport_only"])
        self.assertIn("logs", result)

    def test_narrative_injected_after_the_terminal_state_is_never_retransmitted(self) -> None:
        path = self.terminal_result()
        self.tamper(path, lambda payload: payload.update(transcript=self.NARRATIVA))
        for command in (
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "10"),
        ):
            code, result = self.run_cli(*command)
            self.assertEqual(code, tl_job.EXIT_INDETERMINATE, command[0])
            self.assertEqual(result["effects"], "uncertain", command[0])
            self.assertNotIn("outcome", result, command[0])
            wire = json.dumps(result, ensure_ascii=False)
            self.assertNotIn(self.NARRATIVA, wire, command[0])
            self.assertNotIn("conversou", wire, command[0])

    def test_extra_field_inside_the_containment_record_is_refused(self) -> None:
        path = self.terminal_result()
        self.tamper(
            path,
            lambda payload: payload.update(containment=dict(payload["containment"], note=self.NARRATIVA)),
        )
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["effects"], "uncertain")
        self.assertNotIn(self.NARRATIVA, json.dumps(result, ensure_ascii=False))

    def test_a_finished_record_without_containment_is_not_read_as_delivered(self) -> None:
        """Absence of the field is absence of proof about the job tree, never proof of none.

        Everything else in this record is the one the supervisor wrote for a unit that really
        ended: identity, fingerprints, exit zero and an admitted `delivered`. Only the record
        of what happened to the tree is gone, and that is the single field saying descendants
        were ended. Read as `known`, it delivers a unit whose tree was never accounted for.
        """
        path = self.terminal_result()
        self.tamper(path, lambda payload: payload.pop("containment"))
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, result)
        self.assertEqual(result["effects"], "uncertain", result)
        self.assertNotIn("outcome", result)

    def test_a_containment_record_missing_its_own_fields_is_not_read_as_delivered(self) -> None:
        """A scope alone is not a containment record: it says nothing about what was contained."""
        path = self.terminal_result()
        whole = json.loads(path.read_text(encoding="utf-8"))
        partial = (
            {"swept": whole["containment"]["swept"]},
            {"established": True, "swept": whole["containment"]["swept"]},
            {"kind": whole["containment"]["kind"], "unit_ran": True},
            dict(whole["containment"], established=False),
        )
        for record in partial:
            with self.subTest(containment=sorted(record)):
                self.tamper(path, lambda payload, record=record: payload.update(containment=record))
                code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, result)
                self.assertEqual(result["effects"], "uncertain", result)
                self.assertNotIn("outcome", result)

    def test_a_finished_record_without_both_log_references_is_not_read_as_delivered(self) -> None:
        """`finalize` opens both files and names both; half a pair answers for another run."""
        path = self.terminal_result()
        whole = json.loads(path.read_text(encoding="utf-8"))
        for logs in ({}, {"stdout": whole["logs"]["stdout"]}, {"stderr": whole["logs"]["stderr"]}):
            with self.subTest(logs=sorted(logs)):
                self.tamper(path, lambda payload, logs=logs: payload.update(logs=logs))
                code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, result)
                self.assertEqual(result["effects"], "uncertain", result)
                self.assertNotIn("outcome", result)

    def test_the_record_this_supervisor_wrote_carries_a_complete_containment(self) -> None:
        """The discrimination: the requirement is met by the real ending, not only by refusals."""
        path = self.terminal_result()
        containment = json.loads(path.read_text(encoding="utf-8"))["containment"]
        for key in tl_job.CONTAINMENT_REQUIRED:
            self.assertIn(key, containment, containment)
        self.assertTrue(containment["unit_ran"], containment)
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_OK, result)
        self.assertEqual(result["outcome"], "delivered", result)
        self.assertEqual(sorted(result["logs"]), ["stderr", "stdout"], result)

    def test_outcome_that_was_never_admitted_is_not_read_as_success(self) -> None:
        path = self.terminal_result()
        self.tamper(path, lambda payload: payload.update(result_status="malformed"))
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["effects"], "uncertain")
        self.assertNotIn("outcome", result)

    def test_result_written_under_another_identity_is_indeterminate(self) -> None:
        path = self.terminal_result()
        self.tamper(path, lambda payload: payload.update(manifest_fingerprint="0" * 16))
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(result["effects"], "uncertain")
        self.assertNotIn("outcome", result)

    def test_a_field_of_the_wrong_type_is_indeterminate(self) -> None:
        path = self.terminal_result()
        self.tamper(path, lambda payload: payload.update(next_action={"texto": self.NARRATIVA}))
        code, result = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertNotIn(self.NARRATIVA, json.dumps(result, ensure_ascii=False))


class SupervisorFailureTest(JobCase):
    """A supervisor that breaks after the spawn still ends the tree and still answers.

    An internal failure used to escape before the sweep and before the terminal file:
    the unit kept running and `wait` could only ever report its own timeout.
    """

    def drain(self, limit: float = 90.0) -> None:
        """Nothing is detached here: every supervisor in this case ends before the assertions."""
        time.sleep(0.2)

    def test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result(self) -> None:
        script = self.child(GRANDCHILD, name="heartbeat.py")
        job_dir = self.claim(script)
        spawned = self.work / "spawned.txt"
        beat = self.work / "beat.txt"
        beating: list[int] = []
        real_write_status = tl_job.write_status

        def refuse_the_running_status(directory, unit, state, pid=None):  # type: ignore[no-untyped-def]
            if state != "running":
                return real_write_status(directory, unit, state, pid)
            # The unit is proven alive and already writing before the disk refuses, so the
            # failure lands after the spawn instead of racing the first beat under load.
            self.appear(spawned)
            beating.append(self.written(beat))
            raise OSError(28, "no space left on device")

        with mock.patch.object(tl_job, "write_status", refuse_the_running_status):
            code = tl_job.supervise(str(self.state), "T012")
        # The arrangement before the behavior: without a live, writing unit this proves nothing.
        self.assertEqual(len(beating), 1, "the supervisor never reached the running status it had to refuse")
        self.assertGreater(beating[0], 0, "the unit never wrote a beat before the injected failure")
        self.assertEqual(code, tl_job.EXIT_OK)
        result_path = job_dir / "result.json"
        self.assertTrue(result_path.exists(), "the supervisor ended without a terminal result")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "crashed")
        self.assertEqual(result["effects"], "uncertain")
        self.assertIn("no space left", result["detail"])
        self.assertIn("failed internally", result["detail"])
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "gone" if tl_job.LEASE_SUPPORTED else "unknown")

        self.assertTrue(spawned.exists(), "the unit never ran; this case would prove nothing")
        first = beat.stat().st_size
        self.assertGreater(first, 0, "the unit never wrote; this case would prove nothing")
        time.sleep(2.0)
        self.assertEqual(beat.stat().st_size, first, "the unit kept working after its supervisor failed")

        code, reported = self.wait(timeout="10")
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(reported["effects"], "uncertain")
        self.assertNotIn("outcome", reported)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_wait_reads_a_supervisor_gone_without_a_result_as_indeterminate(self) -> None:
        script = self.child("pass\n")
        job_dir = self.claim(script)
        # The lease file survives its holder; nobody holds it, so that supervisor is gone.
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "gone")
        buffer = io.StringIO()
        started = time.monotonic()
        with mock.patch.object(tl_job, "LEASE_GRACE_SECONDS", 0.2), contextlib.redirect_stdout(buffer):
            code = tl_job.main(["wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "30"])
        elapsed = time.monotonic() - started
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE)
        self.assertEqual(receipt["state"], "indeterminate")
        self.assertEqual(receipt["effects"], "uncertain")
        self.assertLess(elapsed, 10.0, "wait sat on its deadline instead of seeing the supervisor gone")
        self.assertFalse((job_dir / "result.json").exists(), "no result was invented for a unit nobody finished")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_held_lease_is_never_read_as_a_supervisor_that_ended(self) -> None:
        job_dir = self.claim(self.child("pass\n"))
        identity = tl_job.claimed_lease_identity(job_dir)
        lease = tl_job.claim_lease(job_dir / tl_job.LEASE_NAME, identity)
        self.addCleanup(lease.release)
        self.assertTrue(lease.held)
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "alive")
        # A second supervisor on the same job directory refuses instead of fighting over the result.
        self.assertEqual(tl_job.claim_lease(job_dir / tl_job.LEASE_NAME, identity).status, "busy")
        lease.release()
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "gone")


class SupervisorBoundaryTest(JobCase):
    """`supervise` is reachable from the command line, so it trusts no directory handed to it.

    The earlier shape took a `--job-dir` and executed the `manifest.json` it found there with
    no check at all: any path, including one reached through a link, became argv, logs and a
    result. Here it takes the same two names `start` validates and validates them again.
    """

    def drain(self, limit: float = 90.0) -> None:
        """Nothing is detached here: every refusal answers before the assertions."""
        time.sleep(0.2)

    # --- helpers ---------------------------------------------------------

    def plant(self, directory: Path, unit: str = "T012", **changes: object) -> Path:
        """A claim shaped exactly like a real one, whose argv would leave a mark if obeyed."""
        directory.mkdir(parents=True, exist_ok=True)
        self.marker = self.root / "ran.txt"
        manifest = tl_job.build_manifest(
            unit,
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, "-c", f"open({str(self.marker)!r}, 'w', encoding='utf-8').write('ran')"],
            60.0,
            directory / "unit-result.json",
        )
        manifest.update(changes)
        tl_job.write_atomic(directory / "manifest.json", manifest)
        return directory

    def refusal(self, state_dir: Path, unit: str = "T012") -> dict:
        code, receipt = self.run_cli("supervise", "--state-dir", str(state_dir), "--unit", unit)
        self.assertEqual(code, tl_job.EXIT_USAGE)
        self.assertEqual(receipt["state"], "invalid_input")
        self.assertEqual(receipt["effects"], "none")
        return receipt

    def assert_nothing_ran(self, *directories: Path) -> None:
        self.assertFalse(self.marker.exists(), "the planted argv was executed")
        for directory in directories:
            for name in ("stdout.log", "stderr.log", "result.json", "status.json", "supervisor.json", tl_job.LEASE_NAME):
                self.assertFalse((directory / name).exists(), f"{name} was created in {directory}")

    def link(self, source: Path, target: Path) -> None:
        """A directory link, however this platform spells one: a symlink, or a junction.

        Windows refuses symlinks to an unprivileged account, and `realpath` resolves a
        junction just the same, so the boundary is exercised here as well as on Linux.
        """
        try:
            source.symlink_to(target, target_is_directory=True)
            return
        except (OSError, NotImplementedError) as exc:
            refusal = exc
        if os.name == "nt":
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source), str(target)], capture_output=True
            )
            if junction.returncode == 0:
                return
        self.skipTest(f"this filesystem does not allow the link this case needs: {refusal}")

    # --- cases -----------------------------------------------------------

    def test_a_job_directory_reached_through_a_link_is_refused_before_any_execution(self) -> None:
        outside = self.plant(self.root / "outside" / "T012")
        (self.state / "jobs").mkdir(parents=True)
        self.link(self.state / "jobs" / "T012", outside)
        receipt = self.refusal(self.state)
        self.assertIn("outside the state directory", receipt["error"])
        self.assert_nothing_ran(outside)

    def test_an_arbitrary_directory_as_state_directory_executes_no_claim_found_in_it(self) -> None:
        # The old shape was handed the directory holding the claim. That spelling is not a
        # state directory, so the unit is simply unknown and the planted claim is never read.
        outside = self.plant(self.root / "handed")
        receipt = self.refusal(outside)
        self.assertIn("unknown unit", receipt["error"])
        self.assert_nothing_ran(outside)

    def test_a_claim_that_names_a_result_file_outside_both_trees_is_refused(self) -> None:
        job_dir = self.plant(self.state / "jobs" / "T012", result_file=str(self.root / "elsewhere" / "out.json"))
        receipt = self.refusal(self.state)
        self.assertIn("result_file", receipt["error"])
        self.assert_nothing_ran(job_dir)

    def test_a_claim_with_fields_a_real_claim_never_carries_is_refused(self) -> None:
        job_dir = self.plant(self.state / "jobs" / "T012", extra="planted")
        receipt = self.refusal(self.state)
        self.assertIn("not exactly the ones a claim carries", receipt["error"])
        self.assert_nothing_ran(job_dir)

    def test_a_claim_from_another_schema_is_refused(self) -> None:
        job_dir = self.plant(self.state / "jobs" / "T012", schema=tl_job.SCHEMA_VERSION + 1)
        receipt = self.refusal(self.state)
        self.assertIn(f"schema is not {tl_job.SCHEMA_VERSION}", receipt["error"])
        self.assert_nothing_ran(job_dir)

    def test_a_claim_written_for_another_unit_is_refused(self) -> None:
        job_dir = self.plant(self.state / "jobs" / "T012", unit="T999")
        receipt = self.refusal(self.state)
        self.assertIn("another unit", receipt["error"])
        self.assert_nothing_ran(job_dir)

    def test_the_command_line_no_longer_offers_a_job_directory_to_execute(self) -> None:
        outside = self.plant(self.root / "outside")
        process = subprocess.run(
            [sys.executable, str(CLI), "supervise", "--job-dir", str(outside)],
            capture_output=True,
            cwd=str(self.root),
        )
        self.assertEqual(process.returncode, 2, process.stdout.decode("utf-8", "replace"))
        complaint = process.stderr.decode("utf-8", "replace")
        self.assertIn("required: --state-dir, --unit", complaint)
        self.assertNotIn("--job-dir", complaint.splitlines()[0], "the usage line still offers a job directory")
        self.assert_nothing_ran(outside)

    def test_a_real_claim_in_its_own_job_directory_still_runs(self) -> None:
        """The discrimination: the boundary refuses the cases above and not the legitimate one."""
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        job_dir = self.claim(script)
        # The supervisor writes files and no receipt of its own, so the proof is on disk.
        process = subprocess.run(
            [sys.executable, str(CLI), "supervise", "--state-dir", str(self.state), "--unit", "T012"],
            capture_output=True,
            cwd=str(self.root),
        )
        self.assertEqual(process.returncode, tl_job.EXIT_OK, process.stderr.decode("utf-8", "replace"))
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "exited")
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(result["effects"], "known")


class FinishedUnitTest(JobCase):
    """A unit that already has a terminal result is never reopened.

    The earlier shape validated the claim and then executed it again: a second `supervise`
    on a finished job directory re-ran argv and overwrote the one terminal file, so the
    same authorization produced effects twice.
    """

    def drain(self, limit: float = 90.0) -> None:
        """Nothing is detached here: `supervise` answers before the assertions."""
        time.sleep(0.1)

    def supervise(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), "supervise", "--state-dir", str(self.state), "--unit", "T012"],
            capture_output=True,
            cwd=str(self.root),
        )

    def marks(self) -> str:
        return (self.work / "effect.log").read_text(encoding="utf-8")

    def test_a_second_supervision_of_a_finished_unit_changes_nothing_on_disk(self) -> None:
        marker = (self.work / "effect.log").as_posix()
        script = self.child(
            f'open({marker!r}, "a", encoding="utf-8").write("ran\\n")\n'
            + self.write_result('json.dumps({"outcome": "delivered"})')
        )
        job_dir = self.claim(script)
        first = self.supervise()
        self.assertEqual(first.returncode, tl_job.EXIT_OK, first.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.marks(), "ran\n")
        terminal = (job_dir / "result.json").read_bytes()

        process = self.supervise()
        # The proof is on disk, not in the receipt, so it is asserted first: a guard that
        # stops refusing fails here, on the second effect, instead of on an unparsed receipt.
        self.assertEqual(self.marks(), "ran\n", "the second supervision ran the unit again")
        self.assertEqual((job_dir / "result.json").read_bytes(), terminal)
        receipt = json.loads(process.stdout.decode("utf-8").strip())
        self.assertEqual(process.returncode, tl_job.EXIT_CONFLICT)
        self.assertEqual(receipt["state"], "conflict")
        self.assertEqual(receipt["effects"], "none")
        self.assertIn("never reopened", receipt["error"])

        # The unit result named by the claim is the caller's file, not the terminal one.
        # Removing it must not turn a finished unit back into a runnable one.
        (job_dir / "unit-result.json").unlink()
        replay = self.supervise()
        self.assertEqual(self.marks(), "ran\n", "removing the unit result made argv runnable again")
        self.assertEqual(replay.returncode, tl_job.EXIT_CONFLICT)
        self.assertEqual((job_dir / "result.json").read_bytes(), terminal)
        self.assertFalse((job_dir / "unit-result.json").exists(), "the refused run wrote a unit result")


class ClaimValidationTest(JobCase):
    """Every reader of `manifest.json` validates it; none of them builds on a broken claim.

    `load_claim` used to return any readable object, so `start` on reentry, `status`,
    `wait` and `result` reached a missing field inside a fingerprint or a receipt and
    ended in a traceback with no receipt at all.
    """

    def drain(self, limit: float = 90.0) -> None:
        time.sleep(0.1)

    def plant_claim(self, drop: tuple[str, ...] = (), **changes: object) -> Path:
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True, exist_ok=True)
        self.marker = self.root / "ran.txt"
        manifest = tl_job.build_manifest(
            "T012",
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, "-c", f"open({str(self.marker)!r}, 'w', encoding='utf-8').write('ran')"],
            60.0,
            job_dir / "unit-result.json",
        )
        for key in drop:
            manifest.pop(key)
        manifest.update(changes)
        tl_job.write_atomic(job_dir / "manifest.json", manifest)
        return job_dir

    def refused(self, *args: str) -> dict:
        process = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, cwd=str(self.root))
        complaint = process.stderr.decode("utf-8", "replace")
        self.assertNotIn("Traceback", complaint, "the command answered with a traceback instead of a receipt")
        text = process.stdout.decode("utf-8").strip()
        self.assertTrue(text, f"no receipt on stdout; stderr={complaint}")
        self.assertLessEqual(len(text.encode("utf-8")), tl_job.DEFAULT_MAX_BYTES)
        receipt = json.loads(text)
        self.assertEqual(process.returncode, tl_job.EXIT_USAGE, text)
        self.assertEqual(receipt["state"], "invalid_input")
        self.assertEqual(receipt["effects"], "none")
        self.assertFalse(self.marker.exists(), "the planted argv was executed")
        return receipt

    def readers(self) -> tuple[tuple[str, ...], ...]:
        return (
            ("status", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "5"),
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
        )

    def test_every_reader_refuses_a_claim_missing_a_field(self) -> None:
        self.plant_claim(drop=("argv",))
        for command in self.readers():
            with self.subTest(command=command[0]):
                receipt = self.refused(*command)
                self.assertIn("not exactly the ones a claim carries", receipt["error"])

    def test_every_reader_refuses_a_claim_whose_fields_have_the_wrong_type(self) -> None:
        self.plant_claim(timeout="soon")
        for command in self.readers():
            with self.subTest(command=command[0]):
                receipt = self.refused(*command)
                self.assertIn("`timeout` has the wrong type", receipt["error"])

    def test_result_refuses_a_broken_claim_before_reading_the_terminal_file(self) -> None:
        """A terminal file is not enough: the receipt takes its identity from the claim."""
        job_dir = self.plant_claim(argv=["python", 7])
        tl_job.write_atomic(job_dir / "result.json", {"schema": tl_job.SCHEMA_VERSION, "state": "exited"})
        terminal = (job_dir / "result.json").read_bytes()
        receipt = self.refused("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertIn("non-empty strings", receipt["error"])
        self.assertEqual((job_dir / "result.json").read_bytes(), terminal)

    def test_reentering_start_over_a_broken_claim_refuses_instead_of_reusing_it(self) -> None:
        """Reentry compares fingerprints; a claim that cannot be fingerprinted is not a match."""
        self.plant_claim(drop=("cwd",))
        script = self.child("pass\n")
        receipt = self.refused(
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
            "--", sys.executable, str(script),
        )
        self.assertIn("not exactly the ones a claim carries", receipt["error"])
        for name in ("status.json", "result.json", "supervisor.json", tl_job.LEASE_NAME):
            self.assertFalse((self.job_dir() / name).exists(), f"{name} was created over a refused claim")

    def test_a_claim_for_another_unit_is_refused_by_every_reader(self) -> None:
        self.plant_claim(unit="T999")
        for command in self.readers():
            with self.subTest(command=command[0]):
                receipt = self.refused(*command)
                self.assertIn("another unit", receipt["error"])

    def test_concurrent_starts_on_the_same_unit_leave_one_claim_and_one_receipt(self) -> None:
        """The discrimination: a real race still reuses the claim it finds, and runs once."""
        script = self.child(
            'open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "effect.log"), "a").write("ran\\n")\n'
            + self.write_result('json.dumps({"outcome": "delivered"})')
        )
        answers: list[tuple[int, dict]] = []
        barrier = threading.Barrier(3)

        def attempt() -> None:
            barrier.wait()
            answers.append(self.start(script, timeout="30"))

        threads = [threading.Thread(target=attempt) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
        self.assertEqual([code for code, _ in answers], [0, 0, 0], answers)
        self.assertEqual({receipt["unit"] for _, receipt in answers}, {"T012"})
        self.assertEqual(sum(1 for _, receipt in answers if receipt.get("reused")), 2)
        code, result = self.wait(timeout="60")
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual((self.work / "effect.log").read_text(encoding="utf-8"), "ran\n")


class ReceiptCeilingTest(JobCase):
    """The byte ceiling is a promise, including for the fields a receipt always carries.

    The earlier shape copied the result file name and the state read from disk into the
    receipt with no bound, and kept the core keys whole even when they alone overflowed:
    a planted state directory could push arbitrary content past `--max-bytes`.
    """

    def drain(self, limit: float = 90.0) -> None:
        time.sleep(0.1)

    def oversized_claim(self, name: str) -> Path:
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest = tl_job.build_manifest(
            "T012",
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, "-c", "pass"],
            60.0,
            self.work / name,
        )
        tl_job.write_atomic(job_dir / "manifest.json", manifest)
        return job_dir

    def test_a_receipt_stays_within_the_ceiling_when_disk_fields_are_huge(self) -> None:
        # The marker sits at the end of the name, so it can only reach the receipt if the
        # whole unbounded string did.
        leak = "z" * 2000 + "-LEAKED"
        job_dir = self.oversized_claim(leak + ".json")
        tl_job.write_atomic(
            job_dir / "status.json",
            {"schema": tl_job.SCHEMA_VERSION, "job_id": "T012", "unit": "T012", "state": "s" * 3000},
        )
        process = subprocess.run(
            [
                sys.executable, str(CLI), "--max-bytes", str(tl_job.MIN_MAX_BYTES),
                "status", "--state-dir", str(self.state), "--unit", "T012",
            ],
            capture_output=True,
            cwd=str(self.root),
        )
        raw = process.stdout.strip()
        self.assertEqual(process.returncode, tl_job.EXIT_OK, process.stderr.decode("utf-8", "replace"))
        self.assertLessEqual(len(raw), tl_job.MIN_MAX_BYTES)
        receipt = json.loads(raw.decode("utf-8"))  # a cut codepoint would raise here
        self.assertEqual(receipt["unit"], "T012")
        # A state is a label from a closed set; what the planted file carried is not one.
        self.assertEqual(receipt["state"], "unknown")
        text = raw.decode("utf-8")
        self.assertNotIn("LEAKED", text)
        self.assertNotIn("s" * 100, text, "the state planted on disk reached the receipt")
        self.assertLessEqual(len(receipt["locators"]["unit_result"].encode("utf-8")), tl_job.NAME_BYTES)

    def test_the_ceiling_holds_when_the_core_keys_alone_overflow(self) -> None:
        payload = {
            "schema": tl_job.SCHEMA_VERSION,
            "job_id": "j" * 3000,
            "unit": "u" * 3000,
            "state": "exited",
            "effects": "known",
            "detail": "d" * 3000,
        }
        for ceiling in (tl_job.MIN_MAX_BYTES, 200, 64):
            with self.subTest(ceiling=ceiling):
                trimmed = tl_job.enforce_ceiling(payload, ceiling)
                serialized = tl_job.dumps(trimmed).encode("utf-8")
                self.assertLessEqual(len(serialized), ceiling)
                json.loads(serialized.decode("utf-8"))
                self.assertTrue(trimmed["clipped"])
                self.assertEqual(trimmed["schema"], tl_job.SCHEMA_VERSION)

    def test_an_arbitrary_state_written_on_disk_never_becomes_receipt_text(self) -> None:
        for planted in ("delivered by hand", "", "x" * 5000, 7, None, {"state": "exited"}):
            with self.subTest(planted=repr(planted)[:20]):
                self.assertEqual(tl_job.state_on_disk(planted), "unknown")
        for known in tl_job.KNOWN_STATES:
            self.assertEqual(tl_job.state_on_disk(known), known)


class MalformedCeilingTest(JobCase):
    """The ceiling itself is an input, so a bad one has to be refused inside the boundary.

    Declaring `--max-bytes` as `type=int` would let argparse exit with its own usage dump before
    `main` reaches the `JobError` handler: the caller would read an unbounded message on stderr and
    no JSON at all. The value is therefore taken as text and checked as the first statement inside
    the boundary, where the refusal is a receipt like any other and the default ceiling bounds it.
    """

    def drain(self, limit: float = 90.0) -> None:
        time.sleep(0.1)

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        """Raw invocation: unlike `run_cli` this keeps stderr, which is what the finding was about."""
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True,
            cwd=str(self.root),
        )

    def test_a_nonnumeric_ceiling_is_a_bounded_json_refusal_not_a_usage_dump(self) -> None:
        for value in ("nope", "", "4k", "12.5", "0x10", " ", "-", "1,000", "inf"):
            with self.subTest(value=repr(value)):
                process = self.cli(
                    "--max-bytes", value, "status", "--state-dir", str(self.state), "--unit", "T012"
                )
                raw = process.stdout.strip()
                self.assertEqual(process.returncode, tl_job.EXIT_USAGE)
                # The receipt is the whole answer, and it fits the default ceiling.
                self.assertLessEqual(len(raw), tl_job.DEFAULT_MAX_BYTES)
                receipt = json.loads(raw.decode("utf-8"))
                self.assertEqual(receipt["state"], "invalid_input")
                self.assertEqual(receipt["effects"], "none")
                self.assertEqual(receipt["unit"], "T012")
                self.assertIn("whole number", receipt["error"])
                text = process.stderr.decode("utf-8", "replace")
                self.assertNotIn("Traceback", text)
                self.assertNotIn("usage:", text)
                self.assertEqual(text.strip(), "", "the refusal leaked past the receipt")

    def test_a_nonnumeric_ceiling_refuses_before_any_command_can_run(self) -> None:
        marker = self.work / "the-unit-ran"
        script = self.child('open(%r, "w", encoding="utf-8").write("ran")\n' % str(marker))
        process = self.cli(
            "--max-bytes", "nope", "start",
            "--state-dir", str(self.state), "--unit", "T012", "--cwd", str(self.work),
            "--timeout", "30", "--authorization", AUTHORIZATION,
            "--", sys.executable, str(script),
        )
        self.assertEqual(process.returncode, tl_job.EXIT_USAGE)
        receipt = json.loads(process.stdout.strip().decode("utf-8"))
        self.assertEqual(receipt["state"], "invalid_input")
        self.drain()
        self.assertFalse(marker.exists(), "the unit was spawned although the ceiling was malformed")
        self.assertFalse(self.job_dir().exists(), "a job directory was claimed before the ceiling was read")

    def test_the_same_arrangement_accepts_a_whole_number_and_honours_it(self) -> None:
        """The discrimination: the malformed value is what refuses, not the shape of the call."""
        self.claim(self.child("pass\n"))
        process = self.cli(
            "--max-bytes", str(tl_job.MIN_MAX_BYTES), "status",
            "--state-dir", str(self.state), "--unit", "T012",
        )
        raw = process.stdout.strip()
        self.assertEqual(process.returncode, tl_job.EXIT_OK, process.stderr.decode("utf-8", "replace"))
        self.assertLessEqual(len(raw), tl_job.MIN_MAX_BYTES)
        self.assertEqual(json.loads(raw.decode("utf-8"))["state"], "starting")

    def test_the_helper_floors_a_number_that_is_too_small_and_refuses_nothing_else(self) -> None:
        for value in ("0", "-9", "1", str(tl_job.MIN_MAX_BYTES - 1)):
            with self.subTest(value=value):
                self.assertEqual(tl_job.check_max_bytes(value), tl_job.MIN_MAX_BYTES)
        self.assertEqual(tl_job.check_max_bytes(" 8192 "), 8192)
        for value in ("nope", None, 4.5, [], "9e3"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(tl_job.JobError) as caught:
                    tl_job.check_max_bytes(value)
                self.assertEqual(caught.exception.code, tl_job.EXIT_USAGE)
                self.assertEqual(caught.exception.state, "invalid_input")


@unittest.skipUnless(tl_job.LEASE_SUPPORTED, "without an exclusive lock no ending can be proven here")
class ForgedTerminalResultTest(JobCase):
    """A unit can write the terminal file; it cannot make its own ending true.

    The job directory is reachable by the unit and every field of a terminal record can be
    rebuilt from `manifest.json`, fingerprints included. So the record alone says nothing
    about who wrote it or when, and success is read from it only after the supervisor of
    that unit is provably gone.
    """

    FORGER = '''
import hashlib, time
from pathlib import Path

job = Path(os.environ["TL_JOB_DIR"])
manifest = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
identity = {k: manifest[k] for k in ("unit", "authorization_fingerprint", "cwd", "argv", "timeout", "result_file")}
raw = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
forged = {
    "schema": manifest["schema"],
    "job_id": manifest["unit"],
    "unit": manifest["unit"],
    "state": "exited",
    "effects": "known",
    "exit_code": 0,
    "started_at": "2026-09-11T00:00:00Z",
    "finished_at": "2026-09-11T00:00:01Z",
    "authorization_fingerprint": manifest["authorization_fingerprint"],
    "manifest_fingerprint": hashlib.sha256(raw).hexdigest()[:16],
    "logs": {"stdout": {"path": "stdout.log", "bytes": 0}, "stderr": {"path": "stderr.log", "bytes": 0}},
    "result_status": "admitted",
    "outcome": "delivered",
    "next_action": "nada a fazer",
}
(job / "result.json").write_text(json.dumps(forged), encoding="utf-8")
beat = Path("beat.txt")
release = Path("release.txt")
deadline = time.monotonic() + 45
while time.monotonic() < deadline and not release.exists():
    with beat.open("a", encoding="utf-8") as handle:
        handle.write("x\\n")
    time.sleep(0.05)
open(os.environ["TL_JOB_RESULT"], "w", encoding="utf-8").write(
    json.dumps({"outcome": "delivered", "next_action": "conferir diff"})
)
'''

    def setUp(self) -> None:
        super().setUp()
        self.beat = self.work / "beat.txt"
        self.release = self.work / "release.txt"
        self.addCleanup(self.let_the_unit_go)

    def let_the_unit_go(self, limit: float = 60.0) -> None:
        """Release the unit and let its supervisor close, so the temporary tree can be removed."""
        if not self.release.exists():
            self.release.write_text("go", encoding="utf-8")
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline and tl_job.supervisor_liveness(self.job_dir()) == "alive":
            time.sleep(0.05)
        time.sleep(0.3)

    def forging_unit(self) -> None:
        """Start the unit and return once its forged terminal record is on disk."""
        script = self.child(self.FORGER, "forger.py")
        self.assertEqual(self.start(script, timeout="90")[0], tl_job.EXIT_OK)
        forged = self.job_dir() / "result.json"
        self.appear(forged)
        self.assertTrue(forged.exists(), "the unit never managed to plant a terminal result")

    def beats(self) -> int:
        return self.beat.stat().st_size if self.beat.exists() else 0

    def test_neither_wait_nor_result_delivers_while_the_forging_unit_keeps_writing(self) -> None:
        self.forging_unit()
        before = self.beats()
        waited, wait_receipt = self.wait(timeout="3")
        result_code, result_receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        after = self.beats()
        # The premise of the case, taken from disk: the unit was writing throughout both verdicts.
        self.assertGreater(after, before, "the unit stopped writing; this run proves nothing")
        self.assertEqual(tl_job.supervisor_liveness(self.job_dir()), "alive")
        for name, code, receipt in (
            ("wait", waited, wait_receipt),
            ("result", result_code, result_receipt),
        ):
            with self.subTest(command=name):
                self.assertNotEqual(code, tl_job.EXIT_OK, receipt)
                self.assertNotEqual(receipt.get("effects"), "known", receipt)
                self.assertNotEqual(receipt.get("outcome"), "delivered", receipt)
                self.assertEqual(receipt.get("effects"), "uncertain", receipt)
        self.assertEqual(waited, tl_job.EXIT_TIMEOUT, wait_receipt)
        self.assertEqual(result_code, tl_job.EXIT_INDETERMINATE, result_receipt)

    def test_the_same_unit_is_delivered_once_it_has_really_ended(self) -> None:
        """The guard delays the answer to the real ending; it does not withhold it."""
        self.forging_unit()
        self.let_the_unit_go()
        code, receipt = self.wait(timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        self.assertEqual(receipt["outcome"], "delivered")
        self.assertEqual(receipt["effects"], "known")
        self.assertEqual(receipt["next_action"], "conferir diff")
        # The published record is the supervisor's, not the one the unit planted.
        terminal = json.loads((self.job_dir() / "result.json").read_text(encoding="utf-8"))
        self.assertNotEqual(terminal["started_at"], "2026-09-11T00:00:00Z")

    def test_a_record_shorter_than_this_supervisor_writes_is_not_a_delivery(self) -> None:
        """A proven ending is not enough either: the record must be one `finalize` produces.

        These fields are read further down with `get` and carry no verdict of their own, so a
        record assembled without them would otherwise pass through as a success of the unit.
        """
        self.forging_unit()
        self.let_the_unit_go()
        code, receipt = self.wait(timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        terminal = self.job_dir() / "result.json"
        whole = json.loads(terminal.read_text(encoding="utf-8"))
        for missing in ("finished_at", "started_at", "logs", "result_status"):
            with self.subTest(missing=missing):
                terminal.write_text(
                    json.dumps({key: value for key, value in whole.items() if key != missing}),
                    encoding="utf-8",
                )
                code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
                self.assertEqual(receipt["effects"], "uncertain", receipt)
                self.assertNotIn("outcome", receipt)


class LiveUnitCase(JobCase):
    """The harness for what a unit can do to its own job directory while it is still running.

    Every attack here has the same three moves: put another file behind `supervisor.lock`,
    plant a complete terminal record built out of the claim, and keep working while the
    readers give their verdicts. They differ only in `REWRITE`, the step in between, and that
    difference is the whole subject of the binding — a unit that also points the claim at the
    file it planted chooses the identity readers compare against, unless that identity is
    kept somewhere the unit does not write.

    The child script is assembled from the three fragments in order, so a subclass says what
    it does differently and nothing else.
    """

    FORGED_START = "2026-09-11T00:00:00Z"

    SWAP = '''
import hashlib, time
from pathlib import Path

job = Path(os.environ["TL_JOB_DIR"])
manifest = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
identity = {k: manifest[k] for k in ("unit", "authorization_fingerprint", "cwd", "argv", "timeout", "result_file")}
raw = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")

# The attack itself: another file, holding no lock, put behind the name every reader opens.
decoy = Path("decoy.lock")
decoy.write_bytes(b"")
try:
    os.replace(decoy, job / "supervisor.lock")
    Path("swap.txt").write_text("replaced", encoding="utf-8")
except OSError as error:
    Path("swap.txt").write_text("refused:%d" % (error.errno or 0), encoding="utf-8")
'''

    # Nothing by default: the base attack leaves the claim exactly as `start` wrote it.
    REWRITE = ""

    FORGERY = '''
# A complete, coherent, delivered record, every field of it derived from the claim.
forged = {
    "schema": manifest["schema"],
    "job_id": manifest["unit"],
    "unit": manifest["unit"],
    "state": "exited",
    "effects": "known",
    "exit_code": 0,
    "started_at": "2026-09-11T00:00:00Z",
    "finished_at": "2026-09-11T00:00:01Z",
    "authorization_fingerprint": manifest["authorization_fingerprint"],
    "manifest_fingerprint": hashlib.sha256(raw).hexdigest()[:16],
    "logs": {"stdout": {"path": "stdout.log", "bytes": 0}, "stderr": {"path": "stderr.log", "bytes": 0}},
    "containment": {
        "kind": "windows_job_object" if os.name == "nt" else "posix_process_group",
        "established": True,
        "unit_ran": True,
        "swept": "job_object" if os.name == "nt" else "process_group",
        "accounted": "job_object" if os.name == "nt" else "subreaper_scan",
    },
    "result_status": "admitted",
    "outcome": "delivered",
    "next_action": "nada a fazer",
}
(job / "result.json").write_text(json.dumps(forged), encoding="utf-8")

# And it keeps working: the ending it claims has not happened and must not be delivered.
beat = Path("beat.txt")
release = Path("release.txt")
deadline = time.monotonic() + 45
while time.monotonic() < deadline and not release.exists():
    with beat.open("a", encoding="utf-8") as handle:
        handle.write("x\\n")
    time.sleep(0.05)
open(os.environ["TL_JOB_RESULT"], "w", encoding="utf-8").write(
    json.dumps({"outcome": "delivered", "next_action": "conferir diff"})
)
'''

    def setUp(self) -> None:
        super().setUp()
        self.beat = self.work / "beat.txt"
        self.release = self.work / "release.txt"
        self.swap = self.work / "swap.txt"
        self.addCleanup(self.let_the_unit_go)

    def let_the_unit_go(self, limit: float = 60.0) -> None:
        """Release the unit and wait for the supervisor's own record, so the tree can be removed.

        Liveness cannot be waited on here: once the lease is replaced it never answers `gone`
        again, by design. What does change is the terminal file, which the supervisor rewrites
        over the forged one when it finishes.
        """
        if not self.release.exists():
            self.release.write_text("go", encoding="utf-8")
        terminal = self.job_dir() / "result.json"
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            record = tl_job.read_json(terminal)
            if isinstance(record, dict) and record.get("started_at") != self.FORGED_START:
                break
            time.sleep(0.05)
        time.sleep(0.3)

    def replacing_unit(self) -> str:
        """Start the unit and return once it has swapped the lease and planted its record."""
        script = self.child(self.SWAP + self.REWRITE + self.FORGERY, "replacer.py")
        self.assertEqual(self.start(script, timeout="90")[0], tl_job.EXIT_OK)
        forged = self.job_dir() / "result.json"
        self.appear(forged)
        self.assertTrue(forged.exists(), "the unit never managed to plant a terminal result")
        self.assertTrue(self.swap.exists(), "the unit never attempted the swap; this run proves nothing")
        return self.swap.read_text(encoding="utf-8").strip()

    def beats(self) -> int:
        return self.beat.stat().st_size if self.beat.exists() else 0

    def planted(self) -> dict:
        """The terminal record the unit wrote for itself, read back from disk."""
        return json.loads((self.job_dir() / "result.json").read_text(encoding="utf-8"))

    def verdicts(self, wait_timeout: str = "3") -> tuple[tuple, tuple]:
        """Ask both readers while the unit is working, and prove it was working throughout."""
        before = self.beats()
        waited = self.wait(timeout=wait_timeout)
        answered = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        # Read after the verdicts: the unit has to have been working while they were given.
        time.sleep(0.3)
        self.assertGreater(self.beats(), before, "the unit stopped writing; this run proves nothing")
        return waited, answered

    def refuses_everything(self, waited: tuple, answered: tuple) -> None:
        """Neither reader delivered: no exit zero, no known effects, no outcome to act on."""
        for name, (code, receipt) in (("wait", waited), ("result", answered)):
            with self.subTest(command=name):
                self.assertNotEqual(code, tl_job.EXIT_OK, receipt)
                self.assertEqual(receipt["effects"], "uncertain", receipt)
                self.assertNotEqual(receipt.get("effects"), "known", receipt)
                self.assertNotIn("outcome", receipt)


class ReplacedLeaseTest(LiveUnitCase):
    """A live unit that puts another file behind `supervisor.lock` must not be read as ended.

    The lease is the one thing about an ending a unit cannot forge, but it is reached through
    a name inside a directory the unit can write. Replacing the file behind that name used to
    hand the reader an unheld lock: liveness answered `gone`, the ending read as proven, and
    the complete terminal record the unit had already written was delivered as its success.

    What answers now is the identity the job was bound to. A name that leads to another file
    is `replaced`, and `replaced` is never an ending — on a platform where the swap is refused
    outright, the supervisor is simply still alive. Both are asserted here, per platform,
    because only one of the two mechanisms is what actually holds on each.
    """

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_unit_that_replaces_the_lease_still_gets_no_delivery(self) -> None:
        swap = self.replacing_unit()
        (waited, wait_receipt), (result_code, result_receipt) = self.verdicts()
        # The premise, read from disk: the record it planted is the complete, delivered one.
        planted = self.planted()
        self.assertEqual(planted["outcome"], "delivered")
        self.assertEqual(planted["started_at"], self.FORGED_START)

        self.refuses_everything((waited, wait_receipt), (result_code, result_receipt))
        self.assertEqual(result_code, tl_job.EXIT_INDETERMINATE, result_receipt)

        if swap == "replaced":
            # The swap went through, so what refuses the delivery is the identity of the file.
            self.assertEqual(tl_job.supervisor_liveness(self.job_dir()), "replaced")
            self.assertEqual(tl_job.termination_proof(self.job_dir()), "replaced")
            self.assertEqual(waited, tl_job.EXIT_INDETERMINATE, wait_receipt)
            for receipt in (wait_receipt, result_receipt):
                self.assertEqual(receipt["termination"], "replaced", receipt)
        else:
            # The platform refused to move a file being held; the supervisor is simply alive.
            self.assertTrue(swap.startswith("refused:"), swap)
            self.assertEqual(tl_job.supervisor_liveness(self.job_dir()), "alive")
            self.assertEqual(tl_job.termination_proof(self.job_dir()), "running")
            self.assertEqual(waited, tl_job.EXIT_TIMEOUT, wait_receipt)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_replaced_lease_is_not_healed_by_the_unit_really_ending(self) -> None:
        """Fail closed: once the name led elsewhere, no later ending is proven in that directory.

        A replaced lease is not a delay of the answer, it is the loss of the only evidence there
        was. Where the swap is refused this is vacuous, so the case only speaks for the platform
        where it succeeded.
        """
        swap = self.replacing_unit()
        self.let_the_unit_go()
        code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        # The supervisor did finish and did write its own record over the forged one.
        terminal = json.loads((self.job_dir() / "result.json").read_text(encoding="utf-8"))
        self.assertNotEqual(terminal["started_at"], self.FORGED_START)
        if swap == "replaced":
            self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
            self.assertEqual(receipt["termination"], "replaced", receipt)
            self.assertEqual(receipt["effects"], "uncertain", receipt)
            self.assertNotIn("outcome", receipt)
        else:
            self.assertTrue(swap.startswith("refused:"), swap)
            self.assertEqual(code, tl_job.EXIT_OK, receipt)


class RewrittenClaimTest(LiveUnitCase):
    """The same attack, one move stronger: the unit also rewrites the claim readers used.

    Comparing the open lease against `lease_identity` is only worth something if that string
    was not chosen by the unit. It was: the claim lives in the job directory, the unit writes
    there, and `lease_identity` is deliberately outside `manifest_fingerprint` so that two
    starts of one command line still reuse. So a unit could swap the lease, point the claim at
    the file it had just planted, and hand every reader a match — liveness `gone`, ending
    proven, forged record delivered as a success, while it kept running.

    What it cannot rewrite in the same breath is the binding: published once at `start`,
    outside the directory it is free to write. A claim that no longer matches it is `diverged`,
    and that is settled — no wait turns it back into a proof. Unlike the swap, the rewrite
    goes through on every platform, so this case has one answer everywhere.
    """

    REWRITE = '''
# The move the binding exists for: the claim is pointed at the decoy, so a reader that took
# the identity it compares against from `manifest.json` would be told the file it just opened
# is the one the job started with. Nothing else in the claim changes, and nothing else has to.
behind = decoy if decoy.exists() else job / "supervisor.lock"
seen = behind.stat()
manifest["lease_identity"] = "%d:%d" % (seen.st_dev, seen.st_ino)
(job / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
Path("claim.txt").write_text(manifest["lease_identity"], encoding="utf-8")
'''

    def setUp(self) -> None:
        super().setUp()
        self.claimed = self.work / "claim.txt"

    def rewritten(self) -> str:
        """What the unit wrote into its own claim, read from where the unit recorded it."""
        self.appear(self.claimed)
        self.assertTrue(self.claimed.exists(), "the unit never rewrote its claim; this run proves nothing")
        return self.claimed.read_text(encoding="utf-8").strip()

    def divergence(self) -> None:
        """The premise, read from disk: the claim names the decoy and the binding does not."""
        job_dir = self.job_dir()
        claim = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        anchor = tl_job.read_anchor(job_dir)
        self.assertIsNotNone(anchor, "the binding published at start is unreadable")
        self.assertEqual(claim["lease_identity"], self.rewritten())
        self.assertNotEqual(claim["lease_identity"], anchor["lease_identity"])
        # The rewrite left the rest of the claim intact, which is exactly why nothing
        # downstream of the fingerprint would have noticed it.
        self.assertEqual(tl_job.manifest_fingerprint(claim), anchor["manifest_fingerprint"])

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_unit_that_rewrites_its_claim_still_gets_no_delivery(self) -> None:
        self.replacing_unit()
        (waited, wait_receipt), (result_code, result_receipt) = self.verdicts()
        self.divergence()
        # And the record it planted is the complete, delivered one, as in the simpler attack.
        planted = self.planted()
        self.assertEqual(planted["outcome"], "delivered")
        self.assertEqual(planted["started_at"], self.FORGED_START)

        self.refuses_everything((waited, wait_receipt), (result_code, result_receipt))
        self.assertEqual(tl_job.termination_proof(self.job_dir()), "diverged")
        self.assertEqual(waited, tl_job.EXIT_INDETERMINATE, wait_receipt)
        self.assertEqual(result_code, tl_job.EXIT_INDETERMINATE, result_receipt)
        for receipt in (wait_receipt, result_receipt):
            self.assertEqual(receipt["termination"], "diverged", receipt)
        # The wait did not sit out its bound either: a divergence is answered, not waited on.
        self.assertEqual(wait_receipt["state"], "indeterminate", wait_receipt)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_rewritten_claim_is_not_healed_by_the_unit_really_ending(self) -> None:
        """Fail closed: the supervisor really does finish, and still nothing is delivered.

        The record on disk at the end is the supervisor's own, written after the unit exited,
        and by then the ending genuinely happened. It is still not delivered: the directory it
        was written in no longer agrees with what this job was bound to, so there is nothing
        left here that says whose record that is.
        """
        self.replacing_unit()
        self.let_the_unit_go()
        code, receipt = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        terminal = self.planted()
        self.assertNotEqual(terminal["started_at"], self.FORGED_START)
        self.divergence()
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
        self.assertEqual(receipt["termination"], "diverged", receipt)
        self.assertEqual(receipt["effects"], "uncertain", receipt)
        self.assertNotIn("outcome", receipt)


class LeaseBindingTest(JobCase):
    """The claim records which file `supervisor.lock` named, and readers compare against it.

    These cases drive the module directly, so each one is about a single decision: what the
    identity is, what a mismatch does to liveness, to a proof, to a supervisor about to run,
    and what a claim that names no file at all can prove. The end to end attack is next door
    in `ReplacedLeaseTest`; here the answers are read one at a time.
    """

    def drain(self, limit: float = 90.0) -> None:
        # No supervisor is ever spawned here; there is no terminal file to wait for.
        time.sleep(0.05)

    def swap_the_lease(self, job_dir: Path) -> None:
        """Put another file behind the lease name, exactly as a unit with write access would."""
        decoy = self.work / "decoy.lock"
        decoy.write_bytes(b"decoy")
        os.replace(decoy, job_dir / tl_job.LEASE_NAME)

    def test_start_binds_the_claim_to_the_file_it_created(self) -> None:
        script = self.child(self.write_result('json.dumps({"outcome": "delivered"})'))
        self.assertEqual(self.start(script, timeout="30")[0], tl_job.EXIT_OK)
        self.wait(timeout="30")
        job_dir = self.job_dir()
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(tl_job.usable_identity(manifest["lease_identity"]), manifest["lease_identity"])
        self.assertNotEqual(manifest["lease_identity"], tl_job.LEASE_UNBOUND)
        # It names the lease file that is on disk, not merely something well shaped.
        self.assertEqual(
            manifest["lease_identity"],
            tl_job.lease_identity(os.stat(job_dir / tl_job.LEASE_NAME)),
        )

    def test_the_binding_does_not_take_part_in_the_identity_of_a_claim(self) -> None:
        """Two starts of the same authorized command line are still the same claim.

        The lease differs between them by construction, so a fingerprint that included it
        would turn every reuse into a conflict.
        """
        job_dir = self.claim(self.child("pass\n"))
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        other = dict(manifest, lease_identity="7:99999999")
        self.assertNotEqual(manifest["lease_identity"], other["lease_identity"])
        self.assertEqual(tl_job.manifest_fingerprint(manifest), tl_job.manifest_fingerprint(other))

    def test_a_claim_that_names_no_usable_file_is_refused_as_a_claim(self) -> None:
        job_dir = self.claim(self.child("pass\n"))
        path = job_dir / "manifest.json"
        for broken in ("7", "", "seven:eight", "a:1", 7, None, "1:" + "9" * 200):
            with self.subTest(lease_identity=broken):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["lease_identity"] = broken
                path.write_text(json.dumps(manifest), encoding="utf-8")
                self.assertFalse(tl_job.usable_identity(broken))
                code, receipt = self.status()
                self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
                self.assertIn("lease_identity", receipt["error"])

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_an_unheld_lease_behind_the_name_of_another_file_is_not_an_ending(self) -> None:
        job_dir = self.claim(self.child("pass\n"))
        # Unheld and still the file the claim named: that, and only that, is a proven ending.
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "gone")
        self.assertEqual(tl_job.termination_proof(job_dir), "proven")
        self.swap_the_lease(job_dir)
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "replaced")
        self.assertEqual(tl_job.termination_proof(job_dir), "replaced")
        # Nothing is polled away either: waiting does not turn a swap back into a proof.
        self.assertEqual(tl_job.proven_termination(job_dir, settle=0.2), "replaced")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_claim_bound_to_nothing_proves_no_ending_either(self) -> None:
        """An unbound claim is the older shape and the unidentifiable file: never an ending.

        A claim that names no file cannot be compared to one, so liveness is `unbound` and
        nothing there is an ending. The proof says more than that: the binding published at
        `start` still names a file, so a claim that stopped naming it is a claim that was
        rewritten, and the answer is the divergence rather than a plain absence of proof.
        """
        job_dir = self.claim(self.child("pass\n"))
        path = job_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["lease_identity"] = tl_job.LEASE_UNBOUND
        tl_job.write_atomic(path, manifest)
        self.assertEqual(tl_job.supervisor_liveness(job_dir, tl_job.LEASE_UNBOUND), "unbound")
        # Read without an identity handed in, the answer comes from the binding, so it is the
        # same: there is nothing usable left to compare the file behind the name against.
        self.assertEqual(tl_job.supervisor_liveness(job_dir), "unbound")
        self.assertEqual(tl_job.termination_proof(job_dir), "diverged")
        self.assertNotEqual(tl_job.proven_termination(job_dir, settle=0.2), "proven")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_lease_claimed_behind_a_replaced_name_is_not_held(self) -> None:
        job_dir = self.claim(self.child("pass\n"))
        identity = tl_job.claimed_lease_identity(job_dir)
        self.swap_the_lease(job_dir)
        lease = tl_job.claim_lease(job_dir / tl_job.LEASE_NAME, identity)
        self.addCleanup(lease.release)
        self.assertEqual(lease.status, "replaced")
        self.assertFalse(lease.held)
        self.assertIsNone(lease.handle)
        # The decoy is left unlocked: holding it would have locked one file while every
        # reader compared against another.
        with open(job_dir / tl_job.LEASE_NAME, "a+b") as handle:
            self.assertTrue(tl_job.lock_exclusive(handle))
            tl_job.unlock_exclusive(handle)

    def forge(self, job_dir: Path) -> dict:
        """Plant the complete, coherent, delivered record a unit can assemble from its claim."""
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        forged = {
            "schema": manifest["schema"],
            "job_id": manifest["unit"],
            "unit": manifest["unit"],
            "state": "exited",
            "effects": "known",
            "exit_code": 0,
            "started_at": "2026-09-11T00:00:00Z",
            "finished_at": "2026-09-11T00:00:01Z",
            "authorization_fingerprint": manifest["authorization_fingerprint"],
            "manifest_fingerprint": tl_job.manifest_fingerprint(manifest),
            "logs": {"stdout": {"path": "stdout.log", "bytes": 0}, "stderr": {"path": "stderr.log", "bytes": 0}},
            "containment": {
                "kind": "windows_job_object" if os.name == "nt" else "posix_process_group",
                "established": True,
                "unit_ran": True,
                "swept": "job_object" if os.name == "nt" else "process_group",
                "accounted": "job_object" if os.name == "nt" else "subreaper_scan",
            },
            "result_status": "admitted",
            "outcome": "delivered",
            "next_action": "nada a fazer",
        }
        (job_dir / "result.json").write_text(json.dumps(forged), encoding="utf-8")
        return forged

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_no_reader_delivers_a_terminal_record_from_a_replaced_lease(self) -> None:
        """The verdict of both readers over a swapped name, on every platform that locks.

        End to end the swap only goes through where the platform lets a held file be moved,
        so this drives the readers over the state that attack produces, and names the reason
        each of them must report for refusing the record it can see.
        """
        job_dir = self.claim(self.child("pass\n"))
        planted = self.forge(job_dir)
        self.swap_the_lease(job_dir)
        # `result` refuses the claim outright and `wait` stops waiting on it; the reason is
        # carried by the field each of those receipts has for it.
        readers = (
            ("error", "result", "--state-dir", str(self.state), "--unit", "T012"),
            ("detail", "wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "5"),
        )
        for reason, *command in readers:
            with self.subTest(command=command[0]):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    code = tl_job.main(command)
                receipt = json.loads(buffer.getvalue().strip())
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
                self.assertEqual(receipt["state"], "indeterminate", receipt)
                self.assertEqual(receipt["effects"], "uncertain", receipt)
                self.assertNotIn("outcome", receipt)
                self.assertEqual(receipt["termination"], "replaced", receipt)
                self.assertIn("no longer names the file its claim recorded", receipt[reason])
        # The record was readable and deliverable throughout; only the proof was missing.
        self.assertEqual(json.loads((job_dir / "result.json").read_text(encoding="utf-8")), planted)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_supervisor_refuses_a_job_directory_whose_lease_was_replaced(self) -> None:
        marker = self.work / "ran.txt"
        script = self.child(f"open({str(marker)!r}, 'w', encoding='utf-8').write('ran')\n")
        job_dir = self.claim(script)
        self.swap_the_lease(job_dir)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = tl_job.main(["supervise", "--state-dir", str(self.state), "--unit", "T012"])
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_CONFLICT, receipt)
        self.assertEqual(receipt["state"], "conflict", receipt)
        self.assertEqual(receipt["effects"], "none", receipt)
        self.assertIn("tampered", receipt["error"])
        # A tampered directory is refused before anything happens in it.
        self.assertFalse(marker.exists(), "the claimed argv ran over a replaced lease")
        self.assertFalse((job_dir / "result.json").exists(), "a refused claim produced a terminal record")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_binding_rewritten_along_with_the_claim_is_caught_only_by_the_token(self) -> None:
        """The residue, named and then closed by the one check that is not about files.

        Keeping the binding outside the job directory answers a unit that writes where it was
        told to. It is still a file, on the same filesystem, under the same owner, and a unit
        that derives the state directory from `TL_JOB_DIR` reaches it: rewrite the binding to
        match the claim just rewritten and, read from disk alone, everything agrees again. So
        this is what that costs — a delivered forgery — and it is written down rather than
        implied. What no rewrite reaches is the token `start` already handed the caller: the
        binding on disk digests to a different one, and the reader given it delivers nothing.
        """
        job_dir = self.claim(self.child("pass\n"))
        issued = tl_job.read_anchor(job_dir)["binding"]
        planted = self.forge(job_dir)
        self.swap_the_lease(job_dir)
        path = job_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["lease_identity"] = tl_job.lease_identity(os.stat(job_dir / tl_job.LEASE_NAME))
        tl_job.write_atomic(path, manifest)
        rebound = self.anchor(job_dir)
        # Coherent on disk, and a different binding than the one that left `start`.
        self.assertNotEqual(rebound, issued)
        self.assertEqual(tl_job.binding_check(job_dir)[0], "bound")
        self.assertEqual(tl_job.termination_proof(job_dir), "proven")

        code, delivered = self.run_cli("result", "--state-dir", str(self.state), "--unit", "T012")
        self.assertEqual(code, tl_job.EXIT_OK, delivered)
        self.assertEqual(delivered["outcome"], planted["outcome"], delivered)
        code, refused = self.run_cli(
            "result", "--state-dir", str(self.state), "--unit", "T012", "--expect-binding", issued
        )
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, refused)
        self.assertEqual(refused["effects"], "uncertain", refused)
        self.assertEqual(refused["termination"], "diverged", refused)
        self.assertNotIn("outcome", refused)
        self.assertIn("not the one `start` returned", refused["error"])


class BindingAnchorTest(JobCase):
    """The binding as a record: where it is kept, when it is readable, who refuses without it.

    `ReplacedLeaseTest` and `RewrittenClaimTest` drive the attack end to end; these cases read
    the record that stops it one answer at a time — the path it is published at, the shapes
    that are not a binding at all, and what a missing or contradicted binding does to a proof,
    to a supervisor about to run, to a reuse and to a reader handed the token from `start`.
    """

    def drain(self, limit: float = 90.0) -> None:
        # Most cases here never spawn a supervisor; the ones that do wait on their own.
        time.sleep(0.05)

    def delivering_unit(self) -> Path:
        return self.child(self.write_result('json.dumps({"outcome": "delivered", "next_action": "nada a fazer"})'))

    def test_the_binding_is_published_outside_the_directory_the_unit_writes(self) -> None:
        """A record kept inside the job directory would be one more file the unit can rewrite."""
        job_dir = self.claim(self.child("pass\n"))
        path = tl_job.anchor_path(job_dir)
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.parent, self.state / tl_job.ANCHORS_DIR)
        self.assertNotIn(job_dir, path.parents)
        self.assertNotIn(job_dir.parent, path.parents)

    def test_a_record_is_a_binding_only_when_it_names_its_own_fields(self) -> None:
        """Shape, unit, identity and token are all checked; a file that is merely there is not one."""
        job_dir = self.claim(self.child("pass\n"))
        path = tl_job.anchor_path(job_dir)
        published = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNotNone(tl_job.read_anchor(job_dir))
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        rejected = {
            # A field rewritten in place: the token still names what was published, not this.
            "rewritten identity": dict(published, lease_identity="7:99999999"),
            "rewritten authorization": dict(published, authorization_fingerprint="0" * 64),
            "rewritten token": dict(published, binding="0" * tl_job.BINDING_TOKEN_BYTES),
            # Rebuilt coherently, and still not this job: the token names another unit.
            "another unit": tl_job.build_anchor("T999", manifest),
            # Bound to nothing, which no reader ever reads as an ending.
            "bound to nothing": tl_job.build_anchor("T012", dict(manifest, lease_identity=tl_job.LEASE_UNBOUND)),
            "wrong schema": dict(published, schema=published["schema"] + 1),
            "missing field": {k: v for k, v in published.items() if k != "manifest_fingerprint"},
            "extra field": dict(published, extra="x"),
            "wrong type": dict(published, lease_identity=7),
        }
        for name, broken in rejected.items():
            with self.subTest(binding=name):
                path.write_text(json.dumps(broken), encoding="utf-8")
                self.assertIsNone(tl_job.read_anchor(job_dir), name)
                self.assertEqual(tl_job.binding_check(job_dir), ("unanchored", tl_job.LEASE_UNBOUND))
        for name, unreadable in (("not json", "{"), ("not an object", "[]"), ("empty", "")):
            with self.subTest(binding=name):
                path.write_text(unreadable, encoding="utf-8")
                self.assertIsNone(tl_job.read_anchor(job_dir), name)
        path.unlink()
        self.assertIsNone(tl_job.read_anchor(job_dir))
        # And the one that was published is read back whole, so the rejections above are about
        # what was done to it and not about the check refusing everything.
        path.write_text(json.dumps(published), encoding="utf-8")
        self.assertEqual(tl_job.read_anchor(job_dir), published)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_job_with_no_binding_or_a_contradicted_one_proves_no_ending(self) -> None:
        """Both answers are settled: waiting is not what is missing, so nothing polls them."""
        job_dir = self.claim(self.child("pass\n"))
        path = tl_job.anchor_path(job_dir)
        published = path.read_bytes()
        self.assertEqual(tl_job.termination_proof(job_dir), "proven")

        path.unlink()
        self.assertEqual(tl_job.binding_check(job_dir), ("unanchored", tl_job.LEASE_UNBOUND))
        self.assertEqual(tl_job.termination_proof(job_dir), "unanchored")
        self.assertEqual(tl_job.proven_termination(job_dir, settle=0.2), "unanchored")

        path.write_bytes(published)
        claim = job_dir / "manifest.json"
        manifest = json.loads(claim.read_text(encoding="utf-8"))
        tl_job.write_atomic(claim, dict(manifest, lease_identity="7:99999999"))
        self.assertEqual(tl_job.binding_check(job_dir), ("diverged", tl_job.LEASE_UNBOUND))
        self.assertEqual(tl_job.termination_proof(job_dir), "diverged")
        self.assertEqual(tl_job.proven_termination(job_dir, settle=0.2), "diverged")
        # The claim itself is still well shaped and still fingerprints the same; only the
        # comparison against what was published outside the directory says otherwise.
        self.assertEqual(
            tl_job.manifest_fingerprint(json.loads(claim.read_text(encoding="utf-8"))),
            tl_job.read_anchor(job_dir)["manifest_fingerprint"],
        )
        self.assertEqual(tl_job.termination_proof(job_dir), "diverged")
        for state in ("unanchored", "diverged"):
            self.assertIn(state, tl_job.SETTLED_UNPROVABLE)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_no_reader_delivers_a_real_ending_it_can_no_longer_check(self) -> None:
        """Fail closed over a genuine run: the ending happened and is still not delivered.

        The record here is the supervisor's own, written after a unit that really exited, so
        nothing about it is forged. What is gone is the ability to say so: with no binding, or
        with a claim the binding does not answer for, the directory no longer identifies whose
        record that is, and neither reader forwards it.
        """
        self.assertEqual(self.start(self.delivering_unit(), timeout="30")[0], tl_job.EXIT_OK)
        code, delivered = self.wait(timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, delivered)
        job_dir = self.job_dir()
        path = tl_job.anchor_path(job_dir)
        published = path.read_bytes()
        claim = job_dir / "manifest.json"
        manifest = json.loads(claim.read_text(encoding="utf-8"))

        tampering = {
            "unanchored": lambda: path.unlink(),
            "diverged": lambda: tl_job.write_atomic(claim, dict(manifest, lease_identity="7:99999999")),
        }
        for termination, tamper in tampering.items():
            path.write_bytes(published)
            tl_job.write_atomic(claim, manifest)
            tamper()
            readers = (
                ("result", ("result", "--state-dir", str(self.state), "--unit", "T012")),
                ("wait", ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "5")),
            )
            for name, command in readers:
                with self.subTest(termination=termination, command=name):
                    code, receipt = self.run_cli(*command)
                    self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
                    self.assertEqual(receipt["state"], "indeterminate", receipt)
                    self.assertEqual(receipt["effects"], "uncertain", receipt)
                    self.assertEqual(receipt["termination"], termination, receipt)
                    self.assertNotIn("outcome", receipt)
        # The terminal record never moved: what changed is only what can be proven about it.
        self.assertTrue((job_dir / "result.json").exists())

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_a_supervisor_refuses_a_claim_its_binding_does_not_answer_for(self) -> None:
        """Nothing runs in a directory whose claim nothing outside it vouches for."""
        marker = self.work / "ran.txt"
        script = self.child(f"open({str(marker)!r}, 'w', encoding='utf-8').write('ran')\n")
        job_dir = self.claim(script)
        path = tl_job.anchor_path(job_dir)
        published = path.read_bytes()
        claim = job_dir / "manifest.json"
        manifest = json.loads(claim.read_text(encoding="utf-8"))

        tampering = {
            "unanchored": lambda: path.unlink(),
            "diverged": lambda: tl_job.write_atomic(claim, dict(manifest, lease_identity="7:99999999")),
        }
        for state, tamper in tampering.items():
            path.write_bytes(published)
            tl_job.write_atomic(claim, manifest)
            tamper()
            with self.subTest(binding=state):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    code = tl_job.main(["supervise", "--state-dir", str(self.state), "--unit", "T012"])
                receipt = json.loads(buffer.getvalue().strip())
                self.assertEqual(code, tl_job.EXIT_CONFLICT, receipt)
                self.assertEqual(receipt["state"], "conflict", receipt)
                self.assertEqual(receipt["effects"], "none", receipt)
                self.assertEqual(receipt["error"], tl_job.BINDING_REFUSED[state], receipt)
                self.assertFalse(marker.exists(), "the claimed argv ran without a binding to check it against")
                self.assertFalse((job_dir / "result.json").exists(), "a refused claim produced a terminal record")

    def test_a_binding_that_outlived_its_job_directory_is_never_overwritten(self) -> None:
        """`start` publishes once and exclusively; a name already there stops the start.

        Deleting the job directory and starting the same unit again is the honest way to reach
        that state in a test, and it is also what it would look like from the outside: a fresh
        directory, and a binding for this unit that somebody else put there. Adopting it would
        mean writing the record whose whole purpose is to be written by one run only.
        """
        script = self.delivering_unit()
        self.assertEqual(self.start(script, timeout="30")[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait(timeout="30")[0], tl_job.EXIT_OK)
        job_dir = self.job_dir()
        path = tl_job.anchor_path(job_dir)
        published = path.read_bytes()
        shutil.rmtree(job_dir)

        code, refused = self.start(script, timeout="30")
        self.assertEqual(code, tl_job.EXIT_CONFLICT, refused)
        self.assertEqual(refused["effects"], "none", refused)
        self.assertIn("never overwritten", refused["error"])
        self.assertEqual(path.read_bytes(), published, "the binding of an earlier run was rewritten")
        # The refusal happens before the claim is written, so nothing supervises that directory.
        self.assertFalse((job_dir / "manifest.json").exists())
        self.assertFalse((job_dir / "result.json").exists())

    def test_a_reuse_is_refused_when_no_binding_answers_for_the_claim(self) -> None:
        """Reuse hands back an earlier run; an unprovable one is refused instead of adopted."""
        script = self.delivering_unit()
        self.assertEqual(self.start(script, timeout="30")[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait(timeout="30")[0], tl_job.EXIT_OK)
        job_dir = self.job_dir()
        path = tl_job.anchor_path(job_dir)
        published = path.read_bytes()
        claim = job_dir / "manifest.json"
        manifest = json.loads(claim.read_text(encoding="utf-8"))

        code, reused = self.start(script, timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, reused)
        self.assertTrue(reused["reused"], reused)
        self.assertEqual(reused["binding"], json.loads(published.decode("utf-8"))["binding"], reused)

        tampering = {
            "unanchored": lambda: path.unlink(),
            "diverged": lambda: tl_job.write_atomic(claim, dict(manifest, lease_identity="7:99999999")),
        }
        for state, tamper in tampering.items():
            path.write_bytes(published)
            tl_job.write_atomic(claim, manifest)
            tamper()
            with self.subTest(binding=state):
                code, refused = self.start(script, timeout="30")
                self.assertEqual(code, tl_job.EXIT_CONFLICT, refused)
                self.assertEqual(refused["effects"], "none", refused)
                self.assertEqual(refused["error"], tl_job.REUSE_REFUSED[state], refused)
                self.assertNotIn("reused", refused)

    def test_an_expected_binding_is_checked_for_shape_before_anything_is_read(self) -> None:
        """A token that cannot be one is a usage error, not a comparison that happens to fail."""
        self.assertEqual(self.start(self.delivering_unit(), timeout="30")[0], tl_job.EXIT_OK)
        self.assertEqual(self.wait(timeout="30")[0], tl_job.EXIT_OK)
        token = tl_job.read_anchor(self.job_dir())["binding"]
        malformed = ("", "   ", "z" * tl_job.BINDING_TOKEN_BYTES, "A" * tl_job.BINDING_TOKEN_BYTES, token[:-1], token + "0")
        readers = (("result", ()), ("wait", ("--timeout", "5")))
        for bad in malformed:
            for reader, extra in readers:
                with self.subTest(token=bad, command=reader):
                    code, receipt = self.run_cli(
                        reader, "--state-dir", str(self.state), "--unit", "T012", *extra, "--expect-binding", bad
                    )
                    self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
                    self.assertEqual(receipt["state"], "invalid_input", receipt)
                    self.assertIn("expected binding", receipt["error"])
        # Checked before the unit is even looked for: a malformed token is never a lookup.
        code, receipt = self.run_cli(
            "result", "--state-dir", str(self.state), "--unit", "T999", "--expect-binding", "nope"
        )
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertIn("expected binding", receipt["error"])

    def test_the_token_start_returned_delivers_the_run_it_was_returned_for(self) -> None:
        """The out of band check is not in the way of the ordinary case: same result, same code."""
        code, started = self.start(self.delivering_unit(), timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, started)
        token = started["binding"]
        self.assertEqual(token, tl_job.read_anchor(self.job_dir())["binding"])
        code, delivered = self.run_cli(
            "wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "30", "--expect-binding", token
        )
        self.assertEqual(code, tl_job.EXIT_OK, delivered)
        self.assertEqual(delivered["outcome"], "delivered", delivered)
        code, again = self.run_cli(
            "result", "--state-dir", str(self.state), "--unit", "T012", "--expect-binding", token
        )
        self.assertEqual(code, tl_job.EXIT_OK, again)
        self.assertEqual(again["outcome"], delivered["outcome"], again)
        # And a token that is well shaped but names another binding stops the same run.
        other = "0" * tl_job.BINDING_TOKEN_BYTES
        self.assertNotEqual(other, token)
        code, refused = self.run_cli(
            "result", "--state-dir", str(self.state), "--unit", "T012", "--expect-binding", other
        )
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, refused)
        self.assertEqual(refused["termination"], "diverged", refused)
        self.assertEqual(refused["effects"], "uncertain", refused)
        self.assertNotIn("outcome", refused)


class UnprovableTerminationTest(JobCase):
    """Where no exclusive file lock exists, no ending can be proven, so none is delivered.

    The lease is the only signal about an ending that a unit cannot forge. On a platform
    that offers no exclusive lock there is no lease, and what is left on disk is exactly
    what the unit itself could have written: a complete, coherent terminal record. The
    answer there is the indeterminate one with its reason named, never an exit zero.
    """

    def drain(self, limit: float = 90.0) -> None:
        # No supervisor ever runs in this class; there is nothing to wait for.
        time.sleep(0.05)

    def plant_claim(self) -> Path:
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True)
        self.marker = self.work / "ran.txt"
        manifest = tl_job.build_manifest(
            "T012",
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, "-c", f"open({str(self.marker)!r}, 'w', encoding='utf-8').write('ran')"],
            60.0,
            job_dir / "unit-result.json",
        )
        tl_job.write_atomic(job_dir / "manifest.json", manifest)
        return job_dir

    def forge(self, job_dir: Path) -> dict:
        """Plant the record a unit can assemble on its own: complete, coherent, a success.

        Every field here is derivable from `manifest.json`, fingerprints included, which is
        why the record alone says nothing about who wrote it or whether anything ended. The
        containment record is forged at its strongest — a tree established and swept by a
        proven scope — precisely because a unit writing its own result can claim that too.
        """
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        forged = {
            "schema": manifest["schema"],
            "job_id": manifest["unit"],
            "unit": manifest["unit"],
            "state": "exited",
            "effects": "known",
            "exit_code": 0,
            "started_at": "2026-09-11T00:00:00Z",
            "finished_at": "2026-09-11T00:00:01Z",
            "authorization_fingerprint": manifest["authorization_fingerprint"],
            "manifest_fingerprint": tl_job.manifest_fingerprint(manifest),
            "logs": {"stdout": {"path": "stdout.log", "bytes": 0}, "stderr": {"path": "stderr.log", "bytes": 0}},
            "containment": {
                "kind": "windows_job_object" if os.name == "nt" else "posix_process_group",
                "established": True,
                "unit_ran": True,
                "swept": "job_object" if os.name == "nt" else "process_group",
                "accounted": "job_object" if os.name == "nt" else "subreaper_scan",
            },
            "result_status": "admitted",
            "outcome": "delivered",
            "next_action": "nada a fazer",
        }
        (job_dir / "result.json").write_text(json.dumps(forged), encoding="utf-8")
        return forged

    def answer(self, *args: str, supported: bool = False) -> tuple[int, dict]:
        buffer = io.StringIO()
        with mock.patch.object(tl_job, "LEASE_SUPPORTED", supported), contextlib.redirect_stdout(buffer):
            code = tl_job.main(list(args))
        text = buffer.getvalue().strip()
        self.assertTrue(text, "the command stopped without a receipt")
        self.assertLessEqual(len(text.encode("utf-8")), tl_job.DEFAULT_MAX_BYTES)
        return code, json.loads(text)

    def readers(self) -> tuple[tuple[str, ...], ...]:
        return (
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "5"),
        )

    def test_an_unsupported_proof_delivers_no_terminal_result_to_any_reader(self) -> None:
        job_dir = self.plant_claim()
        planted = self.forge(job_dir)
        with mock.patch.object(tl_job, "LEASE_SUPPORTED", False):
            # The premise of the case, read from the module: this platform proves nothing.
            self.assertEqual(tl_job.termination_proof(job_dir), "unsupported")
        for command in self.readers():
            with self.subTest(command=command[0]):
                code, receipt = self.answer(*command)
                self.assertNotEqual(code, tl_job.EXIT_OK, receipt)
                self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
                self.assertEqual(receipt["state"], "indeterminate", receipt)
                self.assertNotEqual(receipt.get("effects"), "known", receipt)
                self.assertEqual(receipt["effects"], "uncertain", receipt)
                self.assertNotIn("outcome", receipt)
                # The refusal says which ending could not be proven, not merely that one could not.
                self.assertEqual(receipt["termination"], "unsupported", receipt)
                self.assertIn("no exclusive file lock", receipt["error"])
        self.assertFalse(self.marker.exists(), "the claimed argv was executed by a reader")
        self.assertEqual(json.loads((job_dir / "result.json").read_text(encoding="utf-8")), planted)

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_the_same_record_is_delivered_where_the_ending_can_be_proven(self) -> None:
        """The discrimination: nothing in the record itself is what withholds the delivery.

        With a lease nobody holds, the same planted record is read as a proven ending and
        delivered. So the refusal above comes from the missing proof and from nothing else.
        """
        job_dir = self.plant_claim()
        # The lease file outlives its holder; unheld, and still the file the claim named,
        # it is the proof that the holder ended.
        self.bind_lease(job_dir)
        self.forge(job_dir)
        self.assertEqual(tl_job.termination_proof(job_dir), "proven")
        code, receipt = self.answer(
            "result", "--state-dir", str(self.state), "--unit", "T012", supported=True
        )
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        self.assertEqual(receipt["effects"], "known", receipt)
        self.assertEqual(receipt["outcome"], "delivered", receipt)

    def test_an_unproven_ending_is_refused_with_its_own_reason(self) -> None:
        """The other unprovable answer keeps its own words; the two are not merged."""
        job_dir = self.plant_claim()
        # A binding that stands, so the refusal is about the lease and not about the claim,
        # and then the lease file removed: on a platform that has locks, an absent lease
        # proves nothing either way.
        self.bind_lease(job_dir)
        (job_dir / tl_job.LEASE_NAME).unlink()
        self.forge(job_dir)
        code, receipt = self.answer(
            "result", "--state-dir", str(self.state), "--unit", "T012", supported=True
        )
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
        self.assertEqual(receipt["effects"], "uncertain", receipt)
        self.assertEqual(receipt["termination"], "unproven", receipt)
        self.assertNotIn("outcome", receipt)

    def test_the_ceiling_still_holds_for_the_refusal_that_names_the_reason(self) -> None:
        """The new field is not an exception to the byte ceiling of a receipt."""
        job_dir = self.plant_claim()
        self.forge(job_dir)
        floor = tl_job.MIN_MAX_BYTES
        code, receipt = self.answer(
            "--max-bytes", str(floor), "result", "--state-dir", str(self.state), "--unit", "T012"
        )
        self.assertEqual(code, tl_job.EXIT_INDETERMINATE, receipt)
        self.assertLessEqual(len(tl_job.dumps(receipt).encode("utf-8")), floor)
        self.assertNotIn("outcome", receipt)
        # Below the floor the promise still holds: the refusal collapses like any other receipt.
        for ceiling in (256, 128, 64):
            with self.subTest(ceiling=ceiling):
                collapsed = tl_job.enforce_ceiling(receipt, ceiling)
                self.assertLessEqual(len(tl_job.dumps(collapsed).encode("utf-8")), ceiling)
                self.assertNotEqual(collapsed.get("effects"), "known", collapsed)


class MalformedClaimTest(JobCase):
    """A claim that is present and unreadable is invalid input, never a concurrent claim.

    `manifest.json` arrives by rename, so the only window a reader may wait out is the one
    where the name is simply absent. A file that is there and is not a claim will never
    become one: waiting on it spent the claim window and then answered `conflict`, which
    reads as another process holding the unit, for what is an unusable file on disk.
    """

    def drain(self, limit: float = 90.0) -> None:
        time.sleep(0.05)

    def corrupt(self, content: bytes) -> Path:
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "manifest.json").write_bytes(content)
        return job_dir

    def readers(self) -> tuple[tuple[str, ...], ...]:
        return (
            ("status", "--state-dir", str(self.state), "--unit", "T012"),
            ("wait", "--state-dir", str(self.state), "--unit", "T012", "--timeout", "5"),
            ("result", "--state-dir", str(self.state), "--unit", "T012"),
            (
                "start", "--state-dir", str(self.state), "--unit", "T012",
                "--authorization", AUTHORIZATION, "--cwd", str(self.work), "--timeout", "10",
                "--", sys.executable, "-c", "pass",
            ),
        )

    def refused(self, *args: str) -> dict:
        process = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, cwd=str(self.root))
        complaint = process.stderr.decode("utf-8", "replace")
        self.assertNotIn("Traceback", complaint, "the command answered with a traceback instead of a receipt")
        text = process.stdout.decode("utf-8").strip()
        self.assertTrue(text, f"no receipt on stdout; stderr={complaint}")
        self.assertLessEqual(len(text.encode("utf-8")), tl_job.DEFAULT_MAX_BYTES)
        receipt = json.loads(text)
        self.assertEqual(process.returncode, tl_job.EXIT_USAGE, text)
        self.assertEqual(receipt["state"], "invalid_input", text)
        self.assertEqual(receipt["effects"], "none", text)
        self.assertNotEqual(receipt["state"], "conflict", text)
        for name in ("status.json", "result.json", "supervisor.json", tl_job.LEASE_NAME):
            self.assertFalse((self.job_dir() / name).exists(), f"{name} was created over an unusable claim")
        return receipt

    def every_reader_refuses(self, content: bytes, expected: str) -> None:
        self.corrupt(content)
        for command in self.readers():
            with self.subTest(command=command[0]):
                receipt = self.refused(*command)
                self.assertIn("not a usable manifest", receipt["error"])
                self.assertIn(expected, receipt["error"])
                # The bytes are refused, never repaired in place for the next reader.
                self.assertEqual((self.job_dir() / "manifest.json").read_bytes(), content)

    def test_every_reader_refuses_a_claim_that_is_not_json(self) -> None:
        self.every_reader_refuses(b'{"schema": 1, "unit": "T012"', "not valid JSON")

    def test_every_reader_refuses_a_claim_that_is_not_utf8(self) -> None:
        self.every_reader_refuses(b'{"unit": "T\xff12"}', "not valid UTF-8")

    def test_every_reader_refuses_a_claim_that_is_not_an_object(self) -> None:
        self.every_reader_refuses(b'["T012"]', "not an object")

    def test_every_reader_refuses_a_claim_larger_than_the_ceiling(self) -> None:
        oversized = b'{"unit": "T012", "pad": "' + b"x" * (tl_job.MAX_RESULT_BYTES + 1) + b'"}'
        self.every_reader_refuses(oversized, "byte ceiling for a claim")

    def test_an_unusable_claim_is_refused_without_waiting_out_the_claim_window(self) -> None:
        """The wait is for a name that is not there yet; this name is there and will not change."""
        self.corrupt(b"nao sou um manifesto\n")
        buffer = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stdout(buffer):
            code = tl_job.main(["status", "--state-dir", str(self.state), "--unit", "T012"])
        elapsed = time.monotonic() - started
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertLess(
            elapsed,
            tl_job.CLAIM_WAIT_SECONDS,
            "the reader waited out the claim window on a file that was never going to become a claim",
        )

    def denied_stat(self):  # type: ignore[no-untyped-def]
        """Patch `stat` so only `manifest.json` answers with a denial, as a locked-down tree does."""
        original = Path.stat

        def stat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self.name == "manifest.json":
                raise PermissionError(13, "Permission denied")
            return original(self, *args, **kwargs)

        return mock.patch.object(Path, "stat", stat)

    def test_a_claim_that_cannot_be_inspected_is_not_reported_as_absent(self) -> None:
        """The helper answers about the name it was given: denied is not the same as not there.

        Only absence is waitable, because only a rename in flight resolves by itself. A stat
        that is refused resolves by nothing, and calling it absence sent the caller into the
        claim window and then made it answer `conflict` — another process holding the unit —
        for a state directory this supervisor simply cannot read.
        """
        job_dir = self.corrupt(b'{"unit": "T012"}')
        with self.denied_stat():
            reason, claim = tl_job.read_claim_file(job_dir / "manifest.json")
        self.assertNotEqual(reason, "absent", reason)
        self.assertIsNone(claim)
        self.assertIn("cannot be inspected", reason)

    def test_a_name_that_is_not_there_is_still_answered_as_absent(self) -> None:
        """The discrimination: the one error that really is a rename in flight keeps its meaning."""
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True)
        reason, claim = tl_job.read_claim_file(job_dir / "manifest.json")
        self.assertEqual(reason, "absent")
        self.assertIsNone(claim)

    def test_a_claim_that_cannot_be_inspected_is_invalid_input_without_waiting(self) -> None:
        """What the caller sees: the usage error of an unreadable claim, not a claimed unit."""
        self.corrupt(b'{"unit": "T012"}')
        buffer = io.StringIO()
        started = time.monotonic()
        with self.denied_stat(), contextlib.redirect_stdout(buffer):
            code = tl_job.main(["status", "--state-dir", str(self.state), "--unit", "T012"])
        elapsed = time.monotonic() - started
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertEqual(receipt["effects"], "none", receipt)
        self.assertIn("not a usable manifest", receipt["error"])
        self.assertLess(
            elapsed,
            tl_job.CLAIM_WAIT_SECONDS,
            "the reader waited out the claim window on a claim it could not even inspect",
        )

    def test_a_claim_that_is_only_absent_is_still_waited_out_as_a_concurrent_one(self) -> None:
        """The discrimination: the transient window a claim really has is still tolerated."""
        self.job_dir().mkdir(parents=True)
        buffer = io.StringIO()
        with mock.patch.object(tl_job, "CLAIM_WAIT_SECONDS", 0.3), contextlib.redirect_stdout(buffer):
            code = tl_job.main(["status", "--state-dir", str(self.state), "--unit", "T012"])
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_CONFLICT, receipt)
        self.assertEqual(receipt["state"], "conflict", receipt)
        self.assertEqual(receipt["effects"], "uncertain", receipt)

    def test_a_claim_still_being_written_is_read_once_it_lands(self) -> None:
        """A rename in flight is absence, and absence is what the wait is for."""
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True)
        manifest = tl_job.build_manifest(
            "T012",
            AUTHORIZATION,
            tl_job.check_cwd(str(self.work)),
            [sys.executable, "-c", "pass"],
            60.0,
            job_dir / "unit-result.json",
        )
        landed = threading.Thread(
            target=lambda: (time.sleep(0.4), tl_job.write_atomic(job_dir / "manifest.json", manifest)),
        )
        landed.start()
        self.addCleanup(landed.join, 30)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = tl_job.main(["status", "--state-dir", str(self.state), "--unit", "T012"])
        receipt = json.loads(buffer.getvalue().strip())
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        self.assertEqual(receipt["unit"], "T012", receipt)


class BusyLeaseSuperviseTest(JobCase):
    """`supervise` is reachable from the command line, so its busy path answers in JSON too.

    A second supervisor on a job directory that already has a live one must refuse, and the
    refusal has to arrive the way every other one does: a bounded receipt on stdout. A bare
    exit code is a silent stop for whoever invoked the subcommand by hand.
    """

    def drain(self, limit: float = 5.0) -> None:
        # `supervise` answers in this process's lifetime, and a refused one leaves nothing
        # behind: there is no detached supervisor here whose logs need waiting out.
        super().drain(limit)

    def supervise_cli(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), "supervise", "--state-dir", str(self.state), "--unit", "T012"],
            capture_output=True,
            cwd=str(self.root),
        )

    def unit_script(self) -> Path:
        return self.child(
            'open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "effect.log"), "a").write("ran\\n")\n'
            + self.write_result('json.dumps({"outcome": "delivered"})')
        )

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_supervise_over_a_held_lease_answers_a_conflict_receipt(self) -> None:
        job_dir = self.claim(self.unit_script())
        lease = tl_job.claim_lease(job_dir / tl_job.LEASE_NAME, tl_job.claimed_lease_identity(job_dir))
        self.addCleanup(lease.release)
        self.assertTrue(lease.held, "the lease of this job directory was not taken; the case would prove nothing")
        process = self.supervise_cli()
        complaint = process.stderr.decode("utf-8", "replace")
        self.assertNotIn("Traceback", complaint)
        text = process.stdout.decode("utf-8").strip()
        self.assertTrue(text, f"the busy path stopped with a bare exit code and no receipt; stderr={complaint}")
        self.assertLessEqual(len(text.encode("utf-8")), tl_job.DEFAULT_MAX_BYTES)
        receipt = json.loads(text)
        self.assertEqual(process.returncode, tl_job.EXIT_CONFLICT, text)
        self.assertEqual(receipt["state"], "conflict", text)
        self.assertEqual(receipt["effects"], "none", text)
        self.assertEqual(receipt["unit"], "T012", text)
        self.assertIn("already holds the lease", receipt["error"])
        self.assertFalse((self.work / "effect.log").exists(), "the refused supervisor ran the unit anyway")
        self.assertFalse((job_dir / "result.json").exists(), "the refused supervisor wrote a terminal result")

    @unittest.skipUnless(tl_job.LEASE_SUPPORTED, "no exclusive file lock exists on this platform")
    def test_the_same_invocation_runs_the_unit_once_the_lease_is_free(self) -> None:
        """The discrimination: the refusal is about the lease, not about the claim on disk."""
        job_dir = self.claim(self.unit_script())
        lease = tl_job.claim_lease(job_dir / tl_job.LEASE_NAME, tl_job.claimed_lease_identity(job_dir))
        self.assertEqual(self.supervise_cli().returncode, tl_job.EXIT_CONFLICT)
        lease.release()
        process = self.supervise_cli()
        self.assertEqual(process.returncode, tl_job.EXIT_OK, process.stdout.decode("utf-8", "replace"))
        self.assertEqual((self.work / "effect.log").read_text(encoding="utf-8"), "ran\n")
        self.assertTrue((job_dir / "result.json").exists())


class ClaimPublicationWindowTest(JobCase):
    """A claim that is landing is not a claim that is broken, and the two are told apart by time.

    `manifest.json` is published by rename, and on Windows an open of the name that rename
    just created can come back denied for an instant. `read_claim_file` classified every
    refused read as a claim on disk that will never be readable, so a real concurrent
    `start` — the one case reuse exists for — could exit `2` with `invalid_input` while the
    unit it should have reused was running. The denial is now retried inside a bounded
    budget and only inside it; everything that will not resolve by waiting still refuses at
    once, and the refusal past the budget is the same one as before.

    The window is forced here instead of raced for, so the rule is driven the same way on
    every host, including the Linux CI that has no such window of its own.
    """

    def drain(self, limit: float = 90.0) -> None:
        """Only a started unit leaves a supervisor to wait for; a planted claim never had one.

        `status.json` is written by `start` and by nothing here, so it tells the two apart
        instead of spending the whole drain budget on a job that will never end.
        """
        if (self.job_dir() / "status.json").exists():
            super().drain(limit)
        else:
            time.sleep(0.05)

    def unit_script(self) -> Path:
        return self.child(
            'open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "effect.log"), "a").write("ran\\n")\n'
            + self.write_result('json.dumps({"outcome": "delivered"})')
        )

    def start_argv(self, script: Path, timeout: str = "30") -> list[str]:
        return [
            "start", "--state-dir", str(self.state), "--unit", "T012",
            "--authorization", AUTHORIZATION, "--cwd", str(self.work),
            "--timeout", timeout, "--", sys.executable, str(script),
        ]

    def denied_read(self, failures: int | None, error: type[OSError] = PermissionError, code: int = errno.EACCES):
        """Deny the read of `manifest.json`, `failures` times or forever when that is `None`.

        The name still inspects fine — this is the open coming back denied, which is what a
        publication holding the name it just created answers. `error`/`code` are open so the
        same shape can drive a failure that is *not* of that class.
        """
        original = Path.read_text
        seen = {"denied": 0}

        def read_text(this, *args, **kwargs):  # type: ignore[no-untyped-def]
            if this.name == "manifest.json" and (failures is None or seen["denied"] < failures):
                seen["denied"] += 1
                raise error(code, "Permission denied" if code == errno.EACCES else "I/O error")
            return original(this, *args, **kwargs)

        return mock.patch.object(Path, "read_text", read_text), seen

    def run_main(self, argv: list[str], patch) -> tuple[int, dict, float]:
        buffer = io.StringIO()
        started = time.monotonic()
        with patch, contextlib.redirect_stdout(buffer):
            code = tl_job.main(argv)
        elapsed = time.monotonic() - started
        return code, json.loads(buffer.getvalue().strip()), elapsed

    def test_a_start_inside_the_publication_window_reuses_the_claim_instead_of_refusing(self) -> None:
        """The probe the finding asked for: the loser of the race reuses, it does not refuse.

        The first `start` publishes the claim and the unit runs. The second meets the exact
        refusal a publication in flight gives, three times, and has to come out of it with
        the receipt of the claim that was on disk the whole time. Before the fix this exited
        `2` with `invalid_input` on the first denial.
        """
        script = self.unit_script()
        code, first = self.start(script, timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, first)
        self.assertFalse(first.get("reused"), first)
        claim = (self.job_dir() / "manifest.json").read_bytes()

        patch, seen = self.denied_read(3)
        code, receipt, elapsed = self.run_main(self.start_argv(script), patch)

        self.assertNotEqual(receipt["state"], "invalid_input", receipt)
        self.assertEqual(code, tl_job.EXIT_OK, receipt)
        self.assertTrue(receipt.get("reused"), receipt)
        self.assertEqual(receipt["unit"], "T012", receipt)
        self.assertEqual(seen["denied"], 3, "the window was not met three times; the case proves less than it says")
        self.assertLess(elapsed, tl_job.CLAIM_WAIT_SECONDS, "the reuse waited out the claim window")
        # The retry only re-reads: the claim is not rewritten, repaired or re-published.
        self.assertEqual((self.job_dir() / "manifest.json").read_bytes(), claim)

        code, result = self.wait(timeout="60")
        self.assertEqual(code, tl_job.EXIT_OK, result)
        self.assertEqual(result["outcome"], "delivered", result)
        self.assertEqual(
            (self.work / "effect.log").read_text(encoding="utf-8"),
            "ran\n",
            "the unit ran more than once for one identity",
        )

    def test_three_starts_of_one_identity_through_the_window_run_the_unit_once(self) -> None:
        """The same discrimination with the whole race: one claim, one run, two reuses.

        Every reader after the first meets the denial, so this is the concurrent shape the
        finding described, with its timing made deterministic instead of hoped for.
        """
        script = self.unit_script()
        code, first = self.start(script, timeout="30")
        self.assertEqual(code, tl_job.EXIT_OK, first)
        answers = []
        for _ in range(2):
            patch, seen = self.denied_read(2)
            code, receipt, _ = self.run_main(self.start_argv(script), patch)
            answers.append((code, receipt))
            self.assertEqual(seen["denied"], 2, receipt)
        self.assertEqual([code for code, _ in answers], [tl_job.EXIT_OK, tl_job.EXIT_OK], answers)
        self.assertTrue(all(receipt.get("reused") for _, receipt in answers), answers)
        self.assertEqual({receipt["unit"] for _, receipt in answers}, {"T012"})
        code, result = self.wait(timeout="60")
        self.assertEqual(code, tl_job.EXIT_OK, result)
        self.assertEqual((self.work / "effect.log").read_text(encoding="utf-8"), "ran\n")
        self.assertEqual(len(list((self.state / "jobs").iterdir())), 1)

    def plant_claim(self) -> Path:
        """A claim on disk whose argv leaves a mark, so a refusal can be proven to be one."""
        job_dir = self.job_dir()
        job_dir.mkdir(parents=True)
        self.marker = self.root / "ran.txt"
        tl_job.write_atomic(
            job_dir / "manifest.json",
            tl_job.build_manifest(
                "T012",
                AUTHORIZATION,
                tl_job.check_cwd(str(self.work)),
                [sys.executable, "-c", f"open({str(self.marker)!r}, 'w', encoding='utf-8').write('ran')"],
                60.0,
                job_dir / "unit-result.json",
            ),
        )
        return job_dir

    def test_a_denial_that_never_clears_is_refused_as_an_unusable_claim(self) -> None:
        """The other half: the budget is a budget. A denial that stays is still invalid input.

        It is refused with its own detail, well inside the claim window, and never as
        `conflict` — which would name another process holding a unit nobody holds.
        """
        job_dir = self.plant_claim()
        patch, seen = self.denied_read(None)
        with mock.patch.object(tl_job, "CLAIM_PUBLISH_SECONDS", 0.3):
            code, receipt, elapsed = self.run_main(
                ["status", "--state-dir", str(self.state), "--unit", "T012"], patch
            )
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertEqual(receipt["effects"], "none", receipt)
        self.assertIn("not a usable manifest", receipt["error"])
        self.assertIn("could not be read", receipt["error"])
        self.assertNotIn("publishing", receipt["error"], "the internal mark leaked into the receipt")
        self.assertGreater(seen["denied"], 1, "the denial was refused without the budget it is owed")
        self.assertGreaterEqual(elapsed, 0.3, "the budget was not honored before the refusal")
        self.assertLess(elapsed, tl_job.CLAIM_WAIT_SECONDS, "the refusal waited out the claim window")
        self.assertFalse(self.marker.exists(), "the planted argv was executed")
        for name in ("status.json", "result.json", "supervisor.json", tl_job.LEASE_NAME):
            self.assertFalse((job_dir / name).exists(), f"{name} was created over a claim that could not be read")

    def test_the_budget_is_opened_once_and_not_restarted_by_every_denial(self) -> None:
        """A denial that keeps coming back must not buy a fresh window each time.

        The reads here alternate denied and absent forever. With a budget reopened per
        denial the loop would never expire and would answer `conflict` at the end of the
        claim window; with one budget per call it refuses as invalid input right after it.
        """
        self.plant_claim()
        original = Path.read_text
        seen = {"reads": 0}

        def read_text(this, *args, **kwargs):  # type: ignore[no-untyped-def]
            if this.name != "manifest.json":
                return original(this, *args, **kwargs)
            seen["reads"] += 1
            if seen["reads"] % 2:
                raise PermissionError(errno.EACCES, "Permission denied")
            raise FileNotFoundError(errno.ENOENT, "No such file or directory")

        patch = mock.patch.object(Path, "read_text", read_text)
        with mock.patch.object(tl_job, "CLAIM_PUBLISH_SECONDS", 0.3):
            code, receipt, elapsed = self.run_main(
                ["status", "--state-dir", str(self.state), "--unit", "T012"], patch
            )
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertNotEqual(receipt["state"], "conflict", receipt)
        self.assertLess(elapsed, tl_job.CLAIM_WAIT_SECONDS, "the budget was restarted by each new denial")
        self.assertFalse(self.marker.exists(), "the planted argv was executed")

    def test_an_inspection_that_is_denied_still_fails_immediately(self) -> None:
        """The denial test kept apart: a name this process cannot even inspect gets no window.

        `stat` answering denied is a locked-down tree, not a rename in flight: nothing about
        it resolves by waiting, so it is refused before any budget is opened.
        """
        self.plant_claim()
        original = Path.stat

        def stat(this, *args, **kwargs):  # type: ignore[no-untyped-def]
            if this.name == "manifest.json":
                raise PermissionError(errno.EACCES, "Permission denied")
            return original(this, *args, **kwargs)

        code, receipt, elapsed = self.run_main(
            ["status", "--state-dir", str(self.state), "--unit", "T012"],
            mock.patch.object(Path, "stat", stat),
        )
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertEqual(receipt["effects"], "none", receipt)
        self.assertIn("cannot be inspected", receipt["error"])
        self.assertLess(
            elapsed,
            tl_job.CLAIM_PUBLISH_SECONDS,
            "an inspection that will never succeed was retried as a publication in flight",
        )

    def test_a_read_failure_that_is_not_a_denial_still_fails_immediately(self) -> None:
        """The class is narrow: an I/O error on the read is not what a publication answers."""
        self.plant_claim()
        patch, seen = self.denied_read(None, error=OSError, code=errno.EIO)
        code, receipt, elapsed = self.run_main(
            ["status", "--state-dir", str(self.state), "--unit", "T012"], patch
        )
        self.assertEqual(code, tl_job.EXIT_USAGE, receipt)
        self.assertEqual(receipt["state"], "invalid_input", receipt)
        self.assertEqual(seen["denied"], 1, "a failure outside the class was retried anyway")
        self.assertLess(elapsed, tl_job.CLAIM_PUBLISH_SECONDS)

    def test_only_denials_are_read_as_a_publication_in_flight(self) -> None:
        """The predicate, field by field, including the Windows codes this exists for."""
        for winerror in (5, 32, 33):
            with self.subTest(winerror=winerror):
                error = PermissionError(errno.EACCES, "Access is denied")
                error.winerror = winerror
                self.assertTrue(tl_job.publication_denial(error))
        for winerror in (2, 3, 1224):
            with self.subTest(winerror=winerror):
                error = OSError(errno.EACCES, "not a sharing refusal")
                error.winerror = winerror
                self.assertFalse(
                    tl_job.publication_denial(error),
                    "a Windows error outside the sharing codes was read as a publication",
                )
        self.assertTrue(tl_job.publication_denial(PermissionError(errno.EACCES, "Permission denied")))
        self.assertTrue(tl_job.publication_denial(PermissionError(errno.EPERM, "Operation not permitted")))
        for code in (errno.EIO, errno.EISDIR, errno.ENOENT, errno.ENAMETOOLONG):
            with self.subTest(errno=code):
                self.assertFalse(tl_job.publication_denial(OSError(code, "not a denial")))

    def test_the_mark_never_reaches_a_reader_of_the_helper(self) -> None:
        """`read_claim_file` still answers the two settled kinds exactly as it did."""
        job_dir = self.plant_claim()
        reason, claim = tl_job.read_claim_file(job_dir / "manifest.json")
        self.assertEqual(reason, "claim")
        self.assertIsInstance(claim, dict)
        (job_dir / "manifest.json").write_bytes(b"nao sou um manifesto\n")
        reason, claim = tl_job.read_claim_file(job_dir / "manifest.json")
        self.assertIsNone(claim)
        self.assertFalse(reason.startswith(tl_job.CLAIM_PUBLISHING), reason)
        self.assertIn("not valid JSON", reason)


if __name__ == "__main__":
    unittest.main()
