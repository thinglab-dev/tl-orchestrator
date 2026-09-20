#!/usr/bin/env python3
"""Offline tests for scripts/tl_graft.py.

No test here needs network access or the real Graft CLI: the real-CLI proof lives in the
manual smoke run recorded under .tmp/graft-verification.md (never as a substitute for these,
and never substituted by these). Where a behaviour can be exercised for real without network
— filesystem exclusion under `git`, junction/symlink refusal, bounded capture and timeouts of
actual subprocesses, UTF-8 of the real stdout — it is, rather than mocked.
"""

from __future__ import annotations

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

from scripts import tl_graft

GIT = tl_graft._which("git")


def _tmp_root(case: unittest.TestCase, name: str = "proj") -> Path:
    # macOS exposes /tmp through /private/tmp; mirror resolve_target_root() so path-safety
    # tests exercise cache redirects, not the host OS temporary-directory alias.
    tmp = Path(tempfile.mkdtemp()).resolve()
    case.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
    root = tmp / name
    root.mkdir()
    return root


def _git_repo(case: unittest.TestCase, name: str = "proj") -> Path:
    root = _tmp_root(case, name)
    subprocess.run([GIT, "init", "-q", str(root)], capture_output=True, check=True)
    return root


def _install_fake_cli(paths: dict[str, Path]) -> None:
    """Make `is_installed`/graph checks pass without a real install."""
    paths["cli_entry"].parent.mkdir(parents=True, exist_ok=True)
    paths["cli_entry"].write_text("// fake cli\n", encoding="utf-8")
    paths["installed_marker"].write_text(tl_graft.PINNED_VERSION, encoding="utf-8")
    paths["wiring"].parent.mkdir(parents=True, exist_ok=True)
    paths["wiring"].write_text("{}", encoding="utf-8")


def _run_result(code, stdout="", stderr="", status="ok") -> tl_graft.RunResult:
    return tl_graft.RunResult(code, stdout, stderr, status)


CLEAN_CHECK = json.dumps({"context": {"missing": True}, "graph": {"missing": False, "ok": True, "nodes": 7, "added": [], "removed": [], "changed": [], "stale": []}})
STALE_CHECK = json.dumps({"context": {"missing": True}, "graph": {"missing": False, "ok": False, "nodes": 7, "added": ["a"], "removed": [], "changed": ["b"], "stale": []}})
ASK_HIT = json.dumps({"query": "x", "mode": "lexical", "hits": [{"pointer": "a.py:L1-L2", "title": "f"}]})


class _QueryRuns:
    """Side effect for `_run`: one answer for the query, another for the follow-up check."""

    def __init__(self, query: tl_graft.RunResult, check: tl_graft.RunResult):
        self.query = query
        self.check = check
        self.commands: list[list[str]] = []

    def __call__(self, cmd, cwd, timeout, env=None, byte_limit=None):
        self.commands.append(cmd)
        return self.check if "check" in cmd else self.query


def _configured(case: unittest.TestCase):
    """A root with a stamped cache and a fake installed CLI, plus node/npm present."""
    root = _tmp_root(case)
    paths = tl_graft.cache_paths(root)
    tl_graft.ensure_cache_excluded(paths)
    _install_fake_cli(paths)
    patcher = mock.patch.object(tl_graft, "node_available", return_value=("/usr/bin/node", "/usr/bin/npm"))
    patcher.start()
    case.addCleanup(patcher.stop)
    return root, paths


class TestResolveTargetRoot(unittest.TestCase):
    def test_falls_back_to_given_path_without_git(self):
        with mock.patch.object(tl_graft, "_which", return_value=None):
            root = tl_graft.resolve_target_root("/some/plain/dir")
        self.assertEqual(root, Path("/some/plain/dir").resolve())

    def test_uses_git_toplevel_when_available(self):
        fake_toplevel = "/repo/worktrees/graft-isolated"
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_toplevel + "\n", stderr="")
        with mock.patch.object(tl_graft, "_which", return_value="/usr/bin/git"), mock.patch(
            "subprocess.run", return_value=completed
        ) as run_mock:
            root = tl_graft.resolve_target_root("/repo/worktrees/graft-isolated/sub")
        self.assertEqual(root, Path(fake_toplevel).resolve())
        # Git paths are decoded as UTF-8 explicitly, not with the locale codec.
        self.assertEqual(run_mock.call_args.kwargs["encoding"], "utf-8")

    def test_handles_path_with_spaces(self):
        with mock.patch.object(tl_graft, "_which", return_value=None):
            root = tl_graft.resolve_target_root("/some/plain dir/with spaces")
        self.assertEqual(root, Path("/some/plain dir/with spaces").resolve())

    @unittest.skipUnless(GIT, "git not available")
    def test_real_git_repo_root_with_non_ascii_and_spaces(self):
        root = _git_repo(self, "proj ção ünica")
        sub = root / "sub dir"
        sub.mkdir()
        self.assertEqual(tl_graft.resolve_target_root(str(sub)), root.resolve())


class TestCacheExclusion(unittest.TestCase):
    """R1: the whole cache — not just the map — must be invisible to Git and to rg."""

    @unittest.skipUnless(GIT, "git not available")
    def test_whole_cache_is_git_ignored_in_a_fresh_consumer(self):
        root = _git_repo(self)
        (root / "app.py").write_text("print('x')\n", encoding="utf-8")
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        _install_fake_cli(paths)
        (paths["home"] / ".graft").mkdir(parents=True, exist_ok=True)
        (paths["home"] / ".graft" / "update-check.json").write_text("{}", encoding="utf-8")

        status = subprocess.run(
            [GIT, "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        tracked = [line for line in status.stdout.splitlines() if tl_graft.CACHE_DIRNAME in line]
        self.assertEqual(tracked, [], f"cache visível em git status: {status.stdout}")
        self.assertIn("app.py", status.stdout)

        for probe in (paths["cli_entry"], paths["installed_marker"], paths["wiring"], paths["stamp"], paths["gitignore"]):
            check = subprocess.run(
                [GIT, "-C", str(root), "check-ignore", "-v", str(probe)], capture_output=True, text=True
            )
            self.assertEqual(check.returncode, 0, f"não ignorado: {probe}")

    def test_exclusion_covers_searches_and_has_no_re_inclusion(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        for name in ("gitignore", "rgignore"):
            body = paths[name].read_text(encoding="utf-8")
            self.assertIn("*", body.splitlines())
            self.assertFalse([line for line in body.splitlines() if line.strip().startswith("!")])

    def test_ensure_ignore_preserves_pre_existing_content(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        paths["gitignore"].write_text("# meu\nold-rule\n", encoding="utf-8")
        tl_graft.ensure_cache_excluded(paths)
        body = paths["gitignore"].read_text(encoding="utf-8")
        self.assertIn("old-rule", body)
        self.assertIn("*", body.splitlines())

    def test_ensure_ignore_is_idempotent(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        first = paths["gitignore"].read_text(encoding="utf-8")
        tl_graft.ensure_cache_excluded(paths)
        self.assertEqual(first, paths["gitignore"].read_text(encoding="utf-8"))

    def test_exclusion_is_written_before_install_and_survives_install_failure(self):
        root, paths = _configured(self)
        # Force a reinstall that fails.
        paths["installed_marker"].unlink()
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(1, "", "network unreachable")):
            result = tl_graft.do_setup(target=str(root), force=True)
        self.assertEqual(result["reason"], "install_failed")
        self.assertTrue(paths["gitignore"].is_file())
        self.assertTrue(paths["rgignore"].is_file())

    def test_upstream_ignore_rewrites_are_disabled_for_the_consumer(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        env = tl_graft._cli_env(paths)
        self.assertEqual(env["GRAFT_NO_GITIGNORE"], "1")
        self.assertEqual(env["GRAFT_NO_IGNORE"], "1")

    def test_setup_does_not_touch_consumer_ignore_files(self):
        root, paths = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, "built")):
            tl_graft.do_setup(target=str(root), force=False)
        self.assertFalse((root / ".gitignore").exists())
        self.assertFalse((root / ".ignore").exists())


class TestSubprocessEnvironment(unittest.TestCase):
    """R3: no inherited key, no consumer .env, no writes to the real home."""

    SENTINELS = {
        "GRAFT_API_KEY": "sentinel-graft",
        "OPENROUTER_API_KEY": "sentinel-openrouter",
        "ORCAROUTER_API_KEY": "sentinel-orca",
        "GRAFT_PROVIDER": "openai",
        "GRAFT_MODEL": "gpt-whatever",
        "GRAFT_BASE_URL": "https://example.invalid",
        "GRAFT_NO_REFRESH": "1",
        "GRAFT_NO_GITIGNORE": "0",
        "DOTENV_CONFIG_PATH": "/tmp/consumer.env",
        "NODE_OPTIONS": "--require /tmp/evil.js",
    }

    NPM_SENTINELS = {
        "NPM_TOKEN": "sentinel-npm-token",
        "GH_TOKEN": "sentinel-gh-token",
        "GITHUB_TOKEN": "sentinel-github-token",
        "AWS_ACCESS_KEY_ID": "sentinel-aws-key-id",
        "AWS_SECRET_ACCESS_KEY": "sentinel-aws-secret",
        "AWS_SESSION_TOKEN": "sentinel-aws-session",
        "NPM_CONFIG_REGISTRY": "https://evil.example.invalid/",
        "npm_config_registry": "https://evil-lower.example.invalid/",
        "NPM_CONFIG_CACHE": "/tmp/attacker-cache",
        "NPM_CONFIG__AUTH": "sentinel-npm-auth",
    }

    def test_cli_env_strips_every_inherited_key_and_config(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        with mock.patch.dict(os.environ, self.SENTINELS, clear=False):
            env = tl_graft._cli_env(paths)
        for name in ("GRAFT_API_KEY", "OPENROUTER_API_KEY", "ORCAROUTER_API_KEY", "GRAFT_PROVIDER", "GRAFT_MODEL", "GRAFT_BASE_URL", "NODE_OPTIONS"):
            self.assertNotIn(name, env, f"{name} vazou para o subprocesso")
        # Only the distinctive values: flags like "1" legitimately reappear as our own switches.
        for value in (v for v in self.SENTINELS.values() if len(v) > 3):
            self.assertNotIn(value, env.values(), f"valor herdado {value!r} sobreviveu")
        # Inherited refresh/ignore switches are replaced by our own explicit values.
        self.assertNotIn("GRAFT_NO_REFRESH", env)
        self.assertEqual(env["GRAFT_NO_GITIGNORE"], "1")
        self.assertEqual(env["DO_NOT_TRACK"], "1")

    def test_dotenv_is_pointed_at_a_path_we_never_create(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        env = tl_graft._cli_env(paths)
        self.assertEqual(env["DOTENV_CONFIG_PATH"], str(paths["no_dotenv"]))
        self.assertFalse(paths["no_dotenv"].exists())
        # A consumer .env beside the root must not be what dotenv reads.
        (root / ".env").write_text("GRAFT_API_KEY=sentinel-dotenv\n", encoding="utf-8")
        self.assertNotEqual(env["DOTENV_CONFIG_PATH"], str(root / ".env"))

    def test_home_is_redirected_into_the_cache(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        env = tl_graft._cli_env(paths)
        self.assertEqual(env["HOME"], str(paths["home"]))
        self.assertEqual(env["USERPROFILE"], str(paths["home"]))

    def test_npm_env_keeps_home_but_drops_keys(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        with mock.patch.dict(os.environ, self.SENTINELS, clear=False):
            env = tl_graft._npm_env(paths)
        self.assertNotIn("GRAFT_API_KEY", env)
        self.assertEqual(env["DO_NOT_TRACK"], "1")
        if "HOME" in os.environ:
            self.assertEqual(env.get("HOME"), os.environ["HOME"])

    def test_npm_env_strips_secrets_and_inherited_npm_config(self):
        # R19: an install script or a leftover NPM_CONFIG_*/secret in the real environment
        # must not reach `npm install`, whatever its case.
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        with mock.patch.dict(os.environ, self.NPM_SENTINELS, clear=False):
            env = tl_graft._npm_env(paths)
        # `npm_config_registry` is legitimately set by us below to the official host; every
        # other inherited key here must not survive at all.
        overridden = {"npm_config_registry"}
        for name in self.NPM_SENTINELS:
            if name.lower() not in overridden:
                self.assertNotIn(name, env, f"{name} vazou para o npm install")
        for value in self.NPM_SENTINELS.values():
            self.assertNotIn(value, env.values(), f"valor herdado {value!r} sobreviveu")

    def test_npm_env_pins_official_registry_and_isolates_config(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        env = tl_graft._npm_env(paths)
        self.assertEqual(env["npm_config_registry"], "https://registry.npmjs.org/")
        self.assertEqual(env["npm_config_cache"], str(paths["npm_cache"]))
        self.assertEqual(env["npm_config_userconfig"], str(paths["npm_no_userrc"]))
        self.assertEqual(env["npm_config_globalconfig"], str(paths["npm_no_globalrc"]))
        self.assertNotEqual(paths["npm_no_userrc"], paths["npm_no_globalrc"])
        self.assertFalse(paths["npm_no_userrc"].exists())
        self.assertFalse(paths["npm_no_globalrc"].exists())
        self.assertNotEqual(paths["npm_cache"], paths["home"])

    def test_seed_update_check_writes_a_fresh_record(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        written = tl_graft.seed_update_check(paths)
        data = json.loads(written.read_text(encoding="utf-8"))
        self.assertIn("checkedAt", data)
        age_ms = __import__("time").time() * 1000 - data["checkedAt"]
        # Upstream only spawns the detached registry check when this record is >24h old.
        self.assertLess(age_ms, 60_000)
        self.assertTrue(str(written).startswith(str(paths["home"])))

    def test_seed_update_check_publishes_atomically_for_concurrent_readers(self):
        """R28: a reader racing the update must see the prior record intact or the new
        record intact, never a truncated/partial file — because the new bytes are staged
        in a sibling temp file and only ever reach `target` via one atomic `os.replace`."""
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        with mock.patch.object(tl_graft.time, "time", return_value=1_000.0):
            tl_graft.seed_update_check(paths)
        target = paths["update_check"]
        previous = json.loads(target.read_text(encoding="utf-8"))

        observed = {}
        real_fdopen = os.fdopen

        def spying_fdopen(fd, mode="r", **kwargs):
            handle = real_fdopen(fd, mode, **kwargs)
            real_write = handle.write

            def spying_write(data):
                # Simulates a concurrent reader opening `target` while the new record is
                # still being written to the not-yet-published temp file.
                observed["mid_write"] = json.loads(target.read_text(encoding="utf-8"))
                observed["mid_write_siblings"] = sorted(
                    p.name for p in target.parent.iterdir()
                )
                return real_write(data)

            handle.write = spying_write
            return handle

        with mock.patch.object(tl_graft.os, "fdopen", side_effect=spying_fdopen), mock.patch.object(
            tl_graft.time, "time", return_value=2_000.0
        ):
            written = tl_graft.seed_update_check(paths)

        self.assertEqual(observed["mid_write"], previous, "leitor viu registro anterior truncado")
        self.assertIn(target.name, observed["mid_write_siblings"])
        self.assertEqual(len(observed["mid_write_siblings"]), 2, "temp deveria coexistir com o alvo íntegro")

        new = json.loads(written.read_text(encoding="utf-8"))
        self.assertNotEqual(new["checkedAt"], previous["checkedAt"])
        self.assertEqual([p.name for p in target.parent.iterdir()], [target.name], "temp não foi limpo após publicar")

    def test_seed_update_check_failure_does_not_erase_previous_record(self):
        """A failed publish (e.g. `os.replace` denied) must leave the previous intact record
        in place and remove its own temp file, per the documented cleanup-on-error fallback."""
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        tl_graft.seed_update_check(paths)
        target = paths["update_check"]
        previous_text = target.read_text(encoding="utf-8")

        with mock.patch.object(tl_graft.os, "replace", side_effect=OSError(13, "Access is denied")):
            with self.assertRaises(OSError):
                tl_graft.seed_update_check(paths)

        self.assertEqual(target.read_text(encoding="utf-8"), previous_text, "registro anterior foi apagado/corrompido")
        self.assertEqual([p.name for p in target.parent.iterdir()], [target.name], "temp órfão após falha de publicação")


class TestGraphStateInterpretation(unittest.TestCase):
    """R2: the real `check --json` body decides, not the exit code."""

    def test_unreadable_report(self):
        self.assertEqual(tl_graft._graph_state(None)[0], "unreadable")

    def test_graph_layer_absent(self):
        self.assertEqual(tl_graft._graph_state({"context": {}, "graph": None})[0], "missing")
        self.assertEqual(tl_graft._graph_state({"graph": {"missing": True}})[0], "missing")

    def test_structural_drift_is_stale(self):
        state, detail = tl_graft._graph_state(json.loads(STALE_CHECK))
        self.assertEqual(state, "stale")
        self.assertEqual(detail["added"], 1)
        self.assertEqual(detail["changed"], 1)

    def test_missing_deep_layer_is_not_drift(self):
        state, _ = tl_graft._graph_state(json.loads(CLEAN_CHECK))
        self.assertEqual(state, "fresh")
        without_context = json.loads(CLEAN_CHECK)
        del without_context["context"]
        self.assertEqual(tl_graft._graph_state(without_context)[0], "fresh")

    INVALID_GRAPHS = (
        {"graph": {}},
        {"graph": {"added": 1}},
        {"graph": {"missing": False, "nodes": 7, "added": [], "removed": []}},
        {"graph": {"nodes": "7", "added": [], "removed": [], "changed": []}},
        {"graph": {"nodes": True, "added": [], "removed": [], "changed": []}},
        {"graph": {"nodes": 7, "added": [], "removed": {}, "changed": []}},
    )

    def test_incomplete_or_mistyped_report_is_unreadable_not_fresh(self):
        """R25: absent or mistyped fields prove nothing — never `fresh`, never a traceback."""
        for payload in self.INVALID_GRAPHS:
            with self.subTest(payload=payload):
                self.assertEqual(tl_graft._graph_state(payload), ("unreadable", {}))

    def test_status_and_query_fall_back_on_incomplete_reports(self):
        root, _ = _configured(self)
        for payload in self.INVALID_GRAPHS[:2]:
            body = json.dumps(payload)
            with self.subTest(payload=payload):
                with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, body)):
                    status = tl_graft.do_status(target=str(root))
                self.assertFalse(status["ok"])
                self.assertEqual(status["reason"], "check_unreadable")
                runs = _QueryRuns(_run_result(0, ASK_HIT), _run_result(0, body))
                with mock.patch.object(tl_graft, "_run", side_effect=runs):
                    query = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100)
                self.assertFalse(query["ok"])
                self.assertEqual(query["reason"], "freshness_unverified")
                self.assertEqual(query["fallback"], "rg")
                self.assertNotIn("verified", query)
                with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, body)), mock.patch(
                    "sys.stdout"
                ) as fake_stdout:
                    exit_code = tl_graft.main(["--target", str(root), "--json", "status"])
                self.assertEqual(exit_code, 1)
                written = "".join(call.args[0] for call in fake_stdout.write.call_args_list if call.args)
                self.assertEqual(json.loads(written.strip())["reason"], "check_unreadable")


class TestSetupFallbacks(unittest.TestCase):
    def test_setup_reports_fallback_when_node_missing(self):
        with mock.patch.object(tl_graft, "node_available", return_value=(None, None)):
            result = tl_graft.do_setup(target=str(_tmp_root(self)), force=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "node_or_npm_missing")

    def test_setup_skips_reinstall_when_pinned_version_present(self):
        root, paths = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, "build ok")) as run_mock:
            result = tl_graft.do_setup(target=str(root), force=False)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["install"]["skipped"])
        self.assertEqual(run_mock.call_count, 1)
        self.assertIn("build", run_mock.call_args.args[0])

    def test_setup_reports_install_timeout(self):
        root, paths = _configured(self)
        paths["installed_marker"].unlink()
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(None, "", "", "timeout")):
            result = tl_graft.do_setup(target=str(root), force=True)
        self.assertEqual(result["reason"], "install_timeout")

    def test_setup_build_error_after_successful_install(self):
        root, paths = _configured(self)

        def fake_run(cmd, cwd, timeout, env=None, byte_limit=None):
            if "install" in cmd:
                return _run_result(0, "installed")
            return _run_result(1, "", "boom")

        with mock.patch.object(tl_graft, "_run", side_effect=fake_run):
            result = tl_graft.do_setup(target=str(root), force=True)
        self.assertEqual(result["reason"], "build_failed")

    def test_setup_reports_missing_graph_even_when_build_exits_zero(self):
        root, paths = _configured(self)
        paths["wiring"].unlink()
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, "done")):
            result = tl_graft.do_setup(target=str(root), force=False)
        self.assertEqual(result["reason"], "graph_missing_after_build")

    def test_setup_refuses_foreign_cache_dir_without_touching_it(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        (paths["base"] / "alheio.txt").write_text("não me toque", encoding="utf-8")
        with mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm")), mock.patch.object(
            tl_graft, "_run"
        ) as run_mock:
            result = tl_graft.do_setup(target=str(root), force=False)
        self.assertEqual(result["reason"], "foreign_cache_dir")
        run_mock.assert_not_called()
        self.assertEqual((paths["base"] / "alheio.txt").read_text(encoding="utf-8"), "não me toque")

    def test_setup_reports_unwritable_cache_without_traceback(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "ensure_cache_excluded", side_effect=PermissionError(13, "Access is denied")):
            result = tl_graft.do_setup(target=str(root), force=False)
        self.assertEqual(result["reason"], "cache_unwritable")
        self.assertIn("Access is denied", result["message"])


class TestStatus(unittest.TestCase):
    def test_status_not_configured(self):
        root = _tmp_root(self)
        with mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm")):
            result = tl_graft.do_status(target=str(root))
        self.assertFalse(result["configured"])
        self.assertEqual(result["reason"], "not_configured")

    def test_status_reports_fresh_graph(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, CLEAN_CHECK)):
            result = tl_graft.do_status(target=str(root))
        self.assertTrue(result["ok"])
        self.assertFalse(result["stale"])

    def test_status_stale_graph_is_reported_not_hidden(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(1, STALE_CHECK)):
            result = tl_graft.do_status(target=str(root))
        self.assertTrue(result["ok"])
        self.assertTrue(result["stale"])

    def test_status_execution_failure_is_not_success(self):
        root, _ = _configured(self)
        for run in (
            _run_result(None, "", "", "timeout"),
            _run_result(None, "", "ENOENT", "spawn_error"),
            _run_result(2, "", "crash"),
        ):
            with self.subTest(status=run.status, code=run.code):
                with mock.patch.object(tl_graft, "_run", return_value=run):
                    result = tl_graft.do_status(target=str(root))
                self.assertFalse(result["ok"])
                self.assertNotIn("stale", result)

    def test_status_non_json_output_is_not_success(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, "graph check: OK")):
            result = tl_graft.do_status(target=str(root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "check_unreadable")

    def test_status_refuses_to_run_when_update_check_cannot_be_seeded(self):
        """R13: a failed seed must not silently proceed — that is the only thing that makes
        "no network after install" fail-closed rather than best-effort."""
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "seed_update_check", side_effect=OSError(13, "Access is denied")), mock.patch.object(
            tl_graft, "_run"
        ) as run_mock:
            result = tl_graft.do_status(target=str(root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "update_check_seed_failed")
        run_mock.assert_not_called()


class TestQuery(unittest.TestCase):
    def test_query_falls_back_when_not_configured(self):
        root = _tmp_root(self)
        with mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm")):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="where is X", limit_chars=100)
        self.assertFalse(result["ok"])
        self.assertEqual(result["fallback"], "rg")

    def test_query_refuses_to_run_when_update_check_cannot_be_seeded(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "seed_update_check", side_effect=OSError(13, "Access is denied")), mock.patch.object(
            tl_graft, "_run"
        ) as run_mock:
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "update_check_seed_failed")
        run_mock.assert_not_called()

    def test_query_rejects_non_positive_and_oversized_limit_chars(self):
        """R14: --limit-chars must not be able to defeat the short-JSON-reply promise."""
        root, _ = _configured(self)
        for bad in (-1, 0, tl_graft.MAX_LIMIT_CHARS + 1):
            with self.subTest(limit_chars=bad):
                with mock.patch.object(tl_graft, "_run") as run_mock:
                    result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=bad)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], "invalid_limit_chars")
                run_mock.assert_not_called()

    def test_query_accepts_limit_chars_at_the_boundaries(self):
        root, _ = _configured(self)
        for good in (1, tl_graft.MAX_LIMIT_CHARS):
            with self.subTest(limit_chars=good):
                runs = _QueryRuns(_run_result(0, ASK_HIT), _run_result(0, CLEAN_CHECK))
                with mock.patch.object(tl_graft, "_run", side_effect=runs):
                    result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=good)
                self.assertTrue(result["ok"], result)

    def test_main_reports_invalid_limit_chars_as_json_without_running_the_cli(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run") as run_mock, mock.patch.object(sys, "stdout", new=io.StringIO()) as out:
            code = tl_graft.main(
                ["--target", str(root), "--json", "query", "--mode", "ask", "--arg", "x", "--limit-chars", "-1"]
            )
        run_mock.assert_not_called()
        self.assertEqual(code, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["reason"], "invalid_limit_chars")

    def test_query_ok_only_when_verified_fresh(self):
        root, _ = _configured(self)
        runs = _QueryRuns(_run_result(0, ASK_HIT), _run_result(0, CLEAN_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verified"]["graph"], "fresh")
        self.assertEqual(len(runs.commands), 2)

    def test_query_result_from_stale_graph_is_a_fallback(self):
        root, _ = _configured(self)
        runs = _QueryRuns(_run_result(0, ASK_HIT), _run_result(1, STALE_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "stale_graph")
        self.assertEqual(result["fallback"], "rg")

    def test_query_unverifiable_freshness_is_a_fallback(self):
        root, _ = _configured(self)
        runs = _QueryRuns(_run_result(0, ASK_HIT), _run_result(None, "", "", "timeout"))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
        self.assertEqual(result["reason"], "freshness_unverified")

    def test_query_lock_contention_note_is_a_fallback(self):
        root, _ = _configured(self)
        note = "[graft] a graph rebuild is already in flight — answering from the current graph\n"
        runs = _QueryRuns(_run_result(0, ASK_HIT, note), _run_result(0, CLEAN_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
        self.assertEqual(result["reason"], "refresh_degraded")

    def test_query_failed_refresh_note_is_a_fallback(self):
        root, _ = _configured(self)
        note = "[graft] graph refresh skipped: EPERM\n"
        runs = _QueryRuns(_run_result(0, ASK_HIT, note), _run_result(0, CLEAN_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
        self.assertEqual(result["reason"], "refresh_degraded")

    def test_query_empty_and_invalid_answers_are_fallbacks(self):
        root, _ = _configured(self)
        cases = {
            "empty_output": _run_result(0, "   "),
            "invalid_output": _run_result(0, "not json at all"),
            "no_results": _run_result(0, json.dumps({"query": "x", "mode": "empty", "hits": []})),
        }
        for reason, query_run in cases.items():
            with self.subTest(reason=reason):
                runs = _QueryRuns(query_run, _run_result(0, CLEAN_CHECK))
                with mock.patch.object(tl_graft, "_run", side_effect=runs):
                    result = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=4000)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["fallback"], "rg")

    def test_emptiness_rules_per_mode(self):
        empty = {
            "ask": {"hits": []},
            "grep": {"totalHits": 0, "groups": []},
            "skeleton": {"file": "a.py", "entries": [], "note": "no definitions indexed for this file"},
            "callers": {"query": "f", "matches": [{"symbol": {}, "hits": [], "note": "loose"}]},
            "map": {"totals": {"files": 0, "symbols": 0}, "dirs": [], "hotspots": []},
        }
        filled = {
            "ask": {"hits": [{"pointer": "a:L1-L2"}]},
            "grep": {"totalHits": 2, "groups": [{"path": "a"}]},
            "skeleton": {"entries": [{"name": "f"}]},
            "callers": {"matches": [{"symbol": {}, "hits": [{"pointer": "a"}]}]},
            "map": {"totals": {"files": 3, "symbols": 9}, "dirs": [{"path": "src"}], "hotspots": []},
        }
        for mode in tl_graft.QUERY_MODES:
            with self.subTest(mode=mode):
                self.assertTrue(tl_graft._payload_is_empty(mode, empty[mode]))
                self.assertFalse(tl_graft._payload_is_empty(mode, filled[mode]))
                self.assertTrue(tl_graft._payload_is_empty(mode, "not a dict"))

    def test_query_timeout_is_not_absence_of_code(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(None, "", "", "timeout")):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="thing", limit_chars=100)
        self.assertEqual(result["reason"], "query_timeout")
        self.assertEqual(result["fallback"], "rg")

    def test_query_output_limit_is_not_absence_of_code(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(0, "x" * 10, "", "limit")):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="thing", limit_chars=100)
        self.assertEqual(result["reason"], "output_limit")

    def test_query_error_is_not_absence_of_code(self):
        root, _ = _configured(self)
        with mock.patch.object(tl_graft, "_run", return_value=_run_result(2, "", "parse error")):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="thing", limit_chars=100)
        self.assertEqual(result["reason"], "query_error")

    def test_query_map_mode_ignores_missing_arg(self):
        root, _ = _configured(self)
        map_json = json.dumps({"totals": {"files": 2, "symbols": 5}, "dirs": [{"path": "src"}], "hotspots": []})
        runs = _QueryRuns(_run_result(0, map_json), _run_result(0, CLEAN_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="map", arg="", limit_chars=4000)
        self.assertTrue(result["ok"], result)
        self.assertIn("map", runs.commands[0])

    def test_query_non_map_mode_requires_arg(self):
        root, _ = _configured(self)
        result = tl_graft.do_query(target=str(root), mode="grep", arg="", limit_chars=100)
        self.assertEqual(result["reason"], "missing_argument")

    def test_query_output_is_truncated(self):
        root, _ = _configured(self)
        huge = json.dumps({"hits": [{"pointer": "a", "blob": "x" * 10_000}]})
        runs = _QueryRuns(_run_result(0, huge), _run_result(0, CLEAN_CHECK))
        with mock.patch.object(tl_graft, "_run", side_effect=runs):
            result = tl_graft.do_query(target=str(root), mode="ask", arg="thing", limit_chars=50)
        self.assertLessEqual(len(result["result"]), 200)
        self.assertIn("truncado", result["result"])


class TestPathProtection(unittest.TestCase):
    """R4: never install, query or delete through a symlink/junction or a foreign dir."""

    def _make_link(self, link: Path, target: Path) -> bool:
        if os.name == "nt":
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            return proc.returncode == 0
        try:
            os.symlink(target, link, target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            return False

    def test_redirected_cache_base_is_refused_by_every_command(self):
        root = _tmp_root(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        paths = tl_graft.cache_paths(root)
        if not self._make_link(paths["base"], outside):
            self.skipTest("sem permissão para criar junction/symlink")

        with mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm")), mock.patch.object(
            tl_graft, "_run"
        ) as run_mock:
            setup = tl_graft.do_setup(target=str(root), force=False)
            status = tl_graft.do_status(target=str(root))
            query = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100)
            disable = tl_graft.do_disable(target=str(root))
        for result in (setup, status, query, disable):
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "cache_path_redirected")
        run_mock.assert_not_called()
        self.assertTrue(sentinel.is_file(), "arquivo fora do cache foi afetado")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_redirected_subdir_is_refused(self):
        root = _tmp_root(self)
        outside = _tmp_root(self, "outside")
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        if not self._make_link(paths["cli"], outside):
            self.skipTest("sem permissão para criar junction/symlink")
        with mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm")), mock.patch.object(
            tl_graft, "_run"
        ) as run_mock:
            result = tl_graft.do_setup(target=str(root), force=False)
        self.assertEqual(result["reason"], "cache_path_redirected")
        run_mock.assert_not_called()
        self.assertTrue((outside / "keep.txt").is_file())

    def test_redirected_named_file_paths_are_refused_too(self):
        """R12: assert_safe_cache used to check only base/cli/graph/home/cli_entry. A cache
        sealed on a prior run can have any other named path (the ignore files, the version
        marker, the wiring report, the stamp) individually replaced later; each must be
        refused on its own, not just the top-level directories."""
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        for key in ("gitignore", "rgignore", "stamp", "no_dotenv", "installed_marker", "wiring"):
            with self.subTest(key=key):
                root = _tmp_root(self, f"proj-{key}")
                paths = tl_graft.cache_paths(root)
                tl_graft.ensure_cache_excluded(paths)
                _install_fake_cli(paths)
                target_path = paths[key]
                if target_path.exists():
                    if target_path.is_dir():
                        import shutil as _shutil

                        _shutil.rmtree(target_path)
                    else:
                        target_path.unlink()
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                if not self._make_link(target_path, outside):
                    self.skipTest("sem permissão para criar junction/symlink")
                with self.assertRaises(tl_graft.CacheUnsafe) as ctx:
                    tl_graft.assert_safe_cache(root, paths)
                self.assertEqual(ctx.exception.reason, "cache_path_redirected")
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_disable_refuses_a_redirected_install_dir_that_hides_a_named_path(self):
        """R12: redirecting `cli/node_modules` puts a named path (the CLI entry point) behind
        the junction, and that path then no longer exists. `realpath` resolves the whole chain
        anyway, so the refusal is structured and arrives before anything is removed."""
        root, paths = _configured(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        node_modules = paths["cli"] / "node_modules"
        shutil.rmtree(node_modules)
        if not self._make_link(node_modules, outside):
            self.skipTest("sem permissão para criar junction/symlink")

        result = tl_graft.do_disable(target=str(root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "cache_path_redirected")
        self.assertTrue(sentinel.is_file(), "arquivo fora do cache foi afetado")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")
        self.assertTrue(paths["base"].exists(), "cache não deveria ter sido parcialmente apagado")

    def test_disable_scan_refuses_an_internal_link_under_no_named_path(self):
        """R12: a reparse point planted where `cache_paths` names nothing below it (npm's
        `.bin`, a subdirectory of the graph) is invisible to `assert_safe_cache`; the scan must
        find it and stop the removal, because `rmtree` walks into a junction on Windows."""
        root, paths = _configured(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        planted = paths["cli"] / "node_modules" / ".bin"
        if not self._make_link(planted, outside):
            self.skipTest("sem permissão para criar junction/symlink")

        self.assertEqual(tl_graft._scan_for_internal_reparse_points(paths["base"]), [planted])
        with self.assertRaises(tl_graft.GraftUnavailable):
            tl_graft.do_disable(target=str(root))
        self.assertTrue(sentinel.is_file(), "arquivo fora do cache foi afetado")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")
        self.assertTrue(paths["base"].exists(), "cache não deveria ter sido parcialmente apagado")

    def test_disable_removes_only_our_stamped_cache(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        _install_fake_cli(paths)
        src = root / "src"
        src.mkdir()
        (src / "app.py").write_text("print('keep me')", encoding="utf-8")

        result = tl_graft.do_disable(target=str(root))
        self.assertTrue(result["ok"])
        self.assertFalse(paths["base"].exists())
        self.assertTrue((src / "app.py").is_file())

    def test_disable_refuses_unstamped_directory(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        (paths["base"] / "alheio.txt").write_text("dados de outro dono", encoding="utf-8")
        with self.assertRaises(tl_graft.GraftUnavailable):
            tl_graft.do_disable(target=str(root))
        self.assertTrue((paths["base"] / "alheio.txt").is_file())

    def test_disable_is_idempotent_when_already_absent(self):
        root = _tmp_root(self)
        self.assertTrue(tl_graft.do_disable(target=str(root))["ok"])

    def test_disable_refuses_cache_outside_the_root(self):
        root = _tmp_root(self)
        elsewhere = _tmp_root(self, "elsewhere")
        paths = {**tl_graft.cache_paths(root), "base": elsewhere}
        with mock.patch.object(tl_graft, "cache_paths", return_value=paths):
            result = tl_graft.do_disable(target=str(root))
        self.assertEqual(result["reason"], "cache_path_unexpected")
        self.assertTrue(elsewhere.is_dir())

    def test_disable_reports_incomplete_removal_without_traceback(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)

        def fake_rmtree(path, **kwargs):
            handler = kwargs.get("onexc") or kwargs.get("onerror")
            if handler:
                handler(os.unlink, str(Path(path) / "cli" / "locked.dll"), PermissionError(13, "in use"))

        with mock.patch.object(tl_graft.shutil, "rmtree", side_effect=fake_rmtree):
            result = tl_graft.do_disable(target=str(root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "disable_incomplete")
        self.assertTrue(paths["base"].is_dir())


class TestWorkspaceRefusal(unittest.TestCase):
    """R5: a non-repo parent holding several repos must never reach the CLI."""

    def _parent_with_two_repos(self) -> tuple[Path, list[Path]]:
        parent = _tmp_root(self, "parent")
        children = []
        for name in ("repoA", "repoB"):
            child = parent / name
            (child / ".git").mkdir(parents=True)
            (child / "main.go").write_text("package main\n", encoding="utf-8")
            children.append(child)
        return parent, children

    def test_every_command_refuses_and_children_are_untouched(self):
        parent, children = self._parent_with_two_repos()
        before = {path: sorted(p.name for p in path.rglob("*")) for path in children}
        with mock.patch.object(tl_graft, "resolve_target_root", return_value=parent), mock.patch.object(
            tl_graft, "node_available", return_value=("/n", "/npm")
        ), mock.patch.object(tl_graft, "_run") as run_mock:
            results = [
                tl_graft.do_setup(target=str(parent), force=False),
                tl_graft.do_status(target=str(parent)),
                tl_graft.do_query(target=str(parent), mode="ask", arg="x", limit_chars=100),
                tl_graft.do_disable(target=str(parent)),
            ]
        for result in results:
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "workspace_layout_unsupported")
        run_mock.assert_not_called()
        for path in children:
            self.assertEqual(before[path], sorted(p.name for p in path.rglob("*")))
            self.assertFalse((path / "graft").exists())
        self.assertFalse((parent / tl_graft.CACHE_DIRNAME).exists())

    def test_single_repo_parent_is_not_treated_as_workspace(self):
        parent = _tmp_root(self, "solo")
        (parent / ".git").mkdir()
        (parent / "child").mkdir()
        ((parent / "child") / ".git").mkdir()
        self.assertEqual(tl_graft.multi_repo_children(parent), [])


class TestRealSubprocessCapture(unittest.TestCase):
    """R6: bounded, non-blocking capture of real (offline) subprocesses."""

    def _py(self, code: str) -> list[str]:
        return [sys.executable, "-c", code]

    def test_output_over_the_limit_kills_the_process(self):
        root = _tmp_root(self)
        code = "import sys\nwhile True:\n    sys.stdout.write('x' * 4096)\n    sys.stdout.flush()\n"
        run = tl_graft._run(self._py(code), cwd=root, timeout=60, env=os.environ.copy(), byte_limit=200_000)
        self.assertEqual(run.status, "limit")
        self.assertLessEqual(len(run.stdout.encode("utf-8")), 220_000)

    def test_timeout_with_both_streams_filled_returns_text_not_bytes(self):
        root = _tmp_root(self)
        code = (
            "import sys, time\n"
            "sys.stdout.write('o' * 50000); sys.stdout.flush()\n"
            "sys.stderr.write('e' * 50000); sys.stderr.flush()\n"
            "time.sleep(30)\n"
        )
        run = tl_graft._run(self._py(code), cwd=root, timeout=3, env=os.environ.copy())
        self.assertEqual(run.status, "timeout")
        self.assertIsInstance(run.stdout, str)
        self.assertIsInstance(run.stderr, str)
        # The formatting path that used to raise TypeError on bytes must stay clean.
        self.assertIn("truncado", tl_graft._truncate(run.stdout, 100))

    def test_partial_utf8_is_replaced_not_raised(self):
        root = _tmp_root(self)
        code = "import sys\nsys.stdout.buffer.write('café'.encode('utf-8')[:-1])\n"
        run = tl_graft._run(self._py(code), cwd=root, timeout=30, env=os.environ.copy())
        self.assertEqual(run.status, "ok")
        self.assertTrue(run.stdout.startswith("caf"))

    def test_large_stderr_does_not_deadlock(self):
        root = _tmp_root(self)
        code = "import sys\nsys.stderr.write('e' * 500000)\nsys.stdout.write('done')\n"
        run = tl_graft._run(self._py(code), cwd=root, timeout=60, env=os.environ.copy())
        self.assertIn(run.status, ("ok", "limit"))
        self.assertEqual(run.code if run.status == "ok" else 0, 0)

    def test_missing_binary_is_a_spawn_error(self):
        root = _tmp_root(self)
        run = tl_graft._run(["binario-que-nao-existe-xyz"], cwd=root, timeout=10, env=os.environ.copy())
        self.assertEqual(run.status, "spawn_error")
        self.assertIsNone(run.code)

    def test_windows_containment_failure_is_a_spawn_error_before_popen(self):
        """R23: without the job object nothing could end the descendants; never run unprotected."""
        root = _tmp_root(self)
        with mock.patch.object(tl_graft, "_WINDOWS", True), mock.patch.object(
            tl_graft.tl_job, "JobObjectContainment", side_effect=tl_graft.tl_job.ContainmentError("sem job")
        ), mock.patch.object(tl_graft.subprocess, "Popen") as popen_mock:
            run = tl_graft._run(self._py("pass"), cwd=root, timeout=10, env=os.environ.copy())
        popen_mock.assert_not_called()
        self.assertEqual(run.status, "spawn_error")
        self.assertIsNone(run.code)
        self.assertFalse(run.ok)
        self.assertIn("sem job", run.stderr)

    def test_capture_not_proven_drained_is_not_ok(self):
        """R23: a pump still alive after the final join is an unfinished capture, not success."""

        class _NeverDrained(threading.Thread):
            def is_alive(self):
                return True

        root = _tmp_root(self)
        with mock.patch.object(tl_graft, "DRAIN_JOIN_SECONDS", 0.5), mock.patch.object(
            tl_graft.threading, "Thread", _NeverDrained
        ):
            run = tl_graft._run(self._py("print('x')"), cwd=root, timeout=30, env=os.environ.copy())
        self.assertEqual(run.status, "unconfirmed")
        self.assertIsNone(run.code)
        self.assertFalse(run.ok)

    def test_truncate_accepts_bytes(self):
        self.assertEqual(tl_graft._truncate(b"caf\xc3\xa9"), "café")


class TestFilesystemFailures(unittest.TestCase):
    """R10: expected filesystem trouble becomes a structured result, never a traceback."""

    def test_invalid_marker_is_not_installed(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        _install_fake_cli(paths)
        paths["installed_marker"].write_bytes(b"\xff\xfe\x00" + "binário".encode("utf-16-le"))
        self.assertFalse(tl_graft.is_installed(paths))

    def test_unreadable_marker_is_not_installed(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        _install_fake_cli(paths)
        with mock.patch.object(Path, "read_text", side_effect=PermissionError(13, "denied")):
            self.assertFalse(tl_graft.is_installed(paths))

    def test_invalid_stamp_is_foreign(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        paths["stamp"].write_text("{isto não é json", encoding="utf-8")
        self.assertEqual(tl_graft.cache_ownership(paths), "foreign")

    def test_main_converts_filesystem_error_into_json(self):
        with mock.patch.object(tl_graft, "do_status", side_effect=PermissionError(13, "Access is denied")), mock.patch(
            "sys.stdout"
        ) as fake_stdout:
            exit_code = tl_graft.main(["--target", str(_tmp_root(self)), "--json", "status"])
        self.assertEqual(exit_code, 1)
        written = "".join(call.args[0] for call in fake_stdout.write.call_args_list if call.args)
        payload = json.loads(written.strip())
        self.assertEqual(payload["reason"], "filesystem_error")


class TestCLIEntrypoint(unittest.TestCase):
    def test_main_json_output_on_fallback(self):
        with mock.patch.object(tl_graft, "node_available", return_value=(None, None)), mock.patch(
            "sys.stdout"
        ) as fake_stdout:
            exit_code = tl_graft.main(["--target", str(_tmp_root(self)), "--json", "setup"])
        self.assertEqual(exit_code, 1)
        written = "".join(call.args[0] for call in fake_stdout.write.call_args_list if call.args)
        payload = json.loads(written.strip())
        self.assertEqual(payload["reason"], "node_or_npm_missing")

    def test_json_stdout_is_utf8_bytes_in_a_real_subprocess(self):
        """R7: redirected stdout on Windows must still be UTF-8, with a non-ASCII path."""
        parent = _tmp_root(self, "alvo ção ünico")
        for name in ("repoA", "repoB"):  # refusal path: fast, no CLI, no network
            (parent / name / ".git").mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        env["PYTHONUTF8"] = "0"
        env["PYTHONPATH"] = str(Path(tl_graft.__file__).resolve().parents[1])
        proc = subprocess.run(
            [sys.executable, str(Path(tl_graft.__file__).resolve()), "--target", str(parent), "--json", "status"],
            capture_output=True,
            env=env,
        )
        payload = json.loads(proc.stdout.decode("utf-8").strip())
        self.assertEqual(payload["reason"], "workspace_layout_unsupported")
        self.assertIn("ção ünico", payload["target"])


class TestUpdateCheckSeedProtection(unittest.TestCase):
    """R12: the seeded update-check record is written through `home/.graft/`, which no install
    creates. A junction on that directory or a symlink on the file would be followed by
    `write_text`, so both are refused before the write and before any subprocess."""

    def _junction(self, link: Path, target: Path) -> bool:
        if os.name == "nt":
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            return proc.returncode == 0
        try:
            os.symlink(target, link, target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            return False

    def _assert_every_command_refuses(self, root: Path) -> None:
        with mock.patch.object(tl_graft, "_run") as run_mock:
            results = [
                tl_graft.do_setup(target=str(root), force=False),
                tl_graft.do_status(target=str(root)),
                tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100),
            ]
        for result in results:
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "cache_path_redirected")
        run_mock.assert_not_called()

    def test_junction_on_the_update_dir_is_refused_before_seeding(self):
        root, paths = _configured(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        if not self._junction(paths["update_dir"], outside):
            self.skipTest("sem permissão para criar junction/symlink")

        with self.assertRaises(tl_graft.CacheUnsafe) as ctx:
            tl_graft.seed_update_check(paths)
        self.assertEqual(ctx.exception.reason, "cache_path_redirected")
        self._assert_every_command_refuses(root)
        self.assertFalse((outside / "update-check.json").exists(), "escreveu fora do cache")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_symlink_on_the_record_file_is_refused_before_seeding(self):
        root, paths = _configured(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "alheio.json"
        sentinel.write_text('{"nao":"mexa"}', encoding="utf-8")
        paths["update_dir"].mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(sentinel, paths["update_check"])
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão para criar symlink de arquivo")

        with self.assertRaises(tl_graft.CacheUnsafe) as ctx:
            tl_graft.seed_update_check(paths)
        self.assertEqual(ctx.exception.reason, "cache_path_redirected")
        self._assert_every_command_refuses(root)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), '{"nao":"mexa"}')

    def test_the_honest_path_still_seeds_a_fresh_record(self):
        _, paths = _configured(self)
        target = tl_graft.seed_update_check(paths)
        self.assertEqual(target, paths["update_check"])
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertLess(abs(payload["checkedAt"] / 1000 - time.time()), 120)


class TestDotenvFileRefusal(unittest.TestCase):
    """R18: `DOTENV_CONFIG_PATH` only neutralizes `dotenv/config` while the file it names does
    not exist. If it does exist, its keys would be loaded into the process we just scrubbed."""

    SECRET = "GRAFT_API_KEY=sentinela\nGRAFT_DEEP=1\nOPENAI_API_KEY=sentinela\n"

    def test_existing_file_refuses_every_cli_command_without_reading_it(self):
        root, paths = _configured(self)
        paths["no_dotenv"].write_text(self.SECRET, encoding="utf-8")

        with mock.patch.object(tl_graft, "_run") as run_mock:
            results = [
                tl_graft.do_setup(target=str(root), force=False),
                tl_graft.do_status(target=str(root)),
                tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100),
            ]
        for result in results:
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "dotenv_file_present")
            self.assertEqual(result["fallback"], "rg")
        run_mock.assert_not_called()
        self.assertEqual(paths["no_dotenv"].read_text(encoding="utf-8"), self.SECRET)

    def test_disable_still_removes_a_cache_that_has_the_file(self):
        root, paths = _configured(self)
        paths["no_dotenv"].write_text(self.SECRET, encoding="utf-8")
        result = tl_graft.do_disable(target=str(root))
        self.assertTrue(result["ok"], result)
        self.assertFalse(paths["base"].exists())


class TestNpmConfigFileRefusal(unittest.TestCase):
    """R24: `npm_config_userconfig`/`globalconfig` isolate the install only while the two files
    they name do not exist; either one present would be loaded by npm as configuration."""

    SECRET = "registry=https://sentinela.invalid/\n//sentinela.invalid/:_authToken=sentinela\n"

    def test_each_existing_file_refuses_setup_without_reading_or_running_npm(self):
        for key in ("npm_no_userrc", "npm_no_globalrc"):
            with self.subTest(key=key):
                root, paths = _configured(self)
                paths["installed_marker"].unlink()
                paths[key].write_text(self.SECRET, encoding="utf-8")
                with mock.patch.object(tl_graft, "_run") as run_mock:
                    for force in (False, True):
                        result = tl_graft.do_setup(target=str(root), force=force)
                        self.assertFalse(result["ok"])
                        self.assertEqual(result["reason"], "npm_config_file_present")
                        self.assertEqual(result["fallback"], "rg")
                run_mock.assert_not_called()
                self.assertEqual(paths[key].read_text(encoding="utf-8"), self.SECRET)


class TestCacheOwnershipForStatusAndQuery(unittest.TestCase):
    """R26: status/query seed `home/.graft` and start the CLI inside the cache, so an apparent
    install they do not own must be refused before either happens, and left intact."""

    def _apparent_install(self, stamp: str | None):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()
        _install_fake_cli(paths)
        if stamp is not None:
            paths["stamp"].write_text(stamp, encoding="utf-8")
        patcher = mock.patch.object(tl_graft, "node_available", return_value=("/n", "/npm"))
        patcher.start()
        self.addCleanup(patcher.stop)
        return root, paths

    def _snapshot(self, base: Path) -> dict[str, bytes]:
        return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}

    STAMPS = {
        "ausente": None,
        "alheio": json.dumps({"tool": "outra-ferramenta"}),
        "lista": "[]",
        "malformado": "{isto não é json",
    }

    def test_status_and_query_refuse_without_writing_or_running(self):
        for label, stamp in self.STAMPS.items():
            with self.subTest(stamp=label):
                root, paths = self._apparent_install(stamp)
                before = self._snapshot(paths["base"])
                with mock.patch.object(tl_graft, "_run") as run_mock, mock.patch.object(
                    tl_graft, "seed_update_check"
                ) as seed_mock:
                    status = tl_graft.do_status(target=str(root))
                    query = tl_graft.do_query(target=str(root), mode="ask", arg="x", limit_chars=100)
                for result in (status, query):
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["reason"], "foreign_cache_dir")
                    self.assertEqual(result["fallback"], "rg")
                self.assertFalse(status["configured"])
                run_mock.assert_not_called()
                seed_mock.assert_not_called()
                self.assertFalse(paths["update_check"].exists())
                self.assertEqual(self._snapshot(paths["base"]), before)

    def test_list_stamp_is_foreign_for_setup_and_disable_without_traceback(self):
        root, paths = self._apparent_install("[]")
        self.assertEqual(tl_graft.cache_ownership(paths), "foreign")
        before = self._snapshot(paths["base"])
        with mock.patch.object(tl_graft, "_run") as run_mock:
            setup = tl_graft.do_setup(target=str(root), force=False)
            # The same structured refusal an unstamped directory gets (not an AttributeError).
            with self.assertRaises(tl_graft.GraftUnavailable):
                tl_graft.do_disable(target=str(root))
        self.assertEqual(setup["reason"], "foreign_cache_dir")
        run_mock.assert_not_called()
        self.assertEqual(self._snapshot(paths["base"]), before)


class TestNpmBinSymlinks(unittest.TestCase):
    """R15: a real npm install on POSIX links `node_modules/.bin/<tool>` into the package it
    just unpacked. Refusing every internal link would refuse every honest Linux/macOS install;
    a link that leaves the cache must still be refused, with its target untouched."""

    def _bin_dir(self, paths: dict[str, Path]) -> Path:
        bin_dir = paths["cli"] / "node_modules" / ".bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        return bin_dir

    def _symlink(self, link: Path, target: Path | str) -> None:
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão para criar symlink de arquivo")

    def test_internal_bin_link_is_accepted_by_setup_guards_and_removed_by_disable(self):
        root, paths = _configured(self)
        link = self._bin_dir(paths) / "graft"
        self._symlink(link, Path("..") / "@nanonets" / "graft" / "dist" / "cli.js")
        self.assertTrue(link.is_symlink())
        self.assertTrue(link.resolve().is_file(), "layout npm de teste não aponta para o pacote")

        tl_graft.assert_safe_cache(root, paths)  # o guard de instalação não recusa o layout
        self.assertEqual(tl_graft._scan_for_internal_reparse_points(paths["base"]), [])
        result = tl_graft.do_disable(target=str(root))
        self.assertTrue(result["ok"], result)
        self.assertFalse(paths["base"].exists())

    def test_bin_link_leaving_the_cache_is_refused_and_its_target_preserved(self):
        root, paths = _configured(self)
        outside = _tmp_root(self, "outside")
        sentinel = outside / "sentinel.js"
        sentinel.write_text("// preserve me", encoding="utf-8")
        self._symlink(self._bin_dir(paths) / "graft", sentinel)

        with self.assertRaises(tl_graft.GraftUnavailable):
            tl_graft.do_disable(target=str(root))
        self.assertTrue(paths["base"].is_dir(), "nada deveria ter sido removido")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "// preserve me")


class TestPartialDisable(unittest.TestCase):
    """R17: when one file cannot be deleted, the ignore files and the stamp must survive — they
    are what keeps the leftovers invisible to Git/rg and what lets a second run finish."""

    def test_leftovers_stay_ignored_and_a_second_run_finishes(self):
        if not GIT:
            self.skipTest("git indisponível")
        root = _git_repo(self)
        paths = tl_graft.cache_paths(root)
        tl_graft.ensure_cache_excluded(paths)
        _install_fake_cli(paths)
        locked = paths["cli"] / "node_modules" / "locked.dll"
        locked.write_bytes(b"binario em uso")
        before = {key: paths[key].read_bytes() for key in ("gitignore", "rgignore", "stamp")}
        real_rmtree = shutil.rmtree

        def partial_rmtree(path, **kwargs):
            """Really delete the subtree, except the locked file: the Windows 'in use' case."""
            path = Path(path)
            if not locked.is_relative_to(path):
                real_rmtree(path)
                return
            for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if child == locked or child in locked.parents:
                    continue
                child.rmdir() if child.is_dir() else child.unlink()
            handler = kwargs.get("onexc") or kwargs.get("onerror")
            if handler:
                handler(os.unlink, str(locked), PermissionError(13, "in use"))

        with mock.patch.object(tl_graft.shutil, "rmtree", side_effect=partial_rmtree):
            first = tl_graft.do_disable(target=str(root))

        self.assertFalse(first["ok"])
        self.assertEqual(first["reason"], "disable_incomplete")
        self.assertTrue(locked.is_file(), "o arquivo bloqueado deveria continuar lá")
        for key, content in before.items():
            self.assertEqual(paths[key].read_bytes(), content, f"{key} foi alterado ou removido")
        self.assertEqual(tl_graft.cache_ownership(paths), "ours")
        ignored = subprocess.run(
            [GIT, "-C", str(root), "check-ignore", str(locked)], capture_output=True
        )
        self.assertEqual(ignored.returncode, 0, "o que sobrou deixou de ser ignorado por Git")

        locked.unlink()  # o programa que segurava o arquivo foi fechado
        second = tl_graft.do_disable(target=str(root))
        self.assertTrue(second["ok"], second)
        self.assertFalse(paths["base"].exists())

    def test_a_cache_left_empty_by_a_failed_close_can_still_be_removed(self):
        root = _tmp_root(self)
        paths = tl_graft.cache_paths(root)
        paths["base"].mkdir()  # selo e ignores já removidos por uma tentativa anterior
        result = tl_graft.do_disable(target=str(root))
        self.assertTrue(result["ok"], result)
        self.assertFalse(paths["base"].exists())


@unittest.skipIf(
    os.name == "nt",
    "contenção por grupo de processos é POSIX; no Windows o encerramento usa taskkill /T",
)
class TestPosixDescendantContainment(unittest.TestCase):
    """R16: npm, node and a native compiler leave descendants behind. A timeout or an oversized
    capture must end the whole group — including when the leader already exited — and the pumps
    must finish draining before `_run` returns."""

    PARENT = (
        "import subprocess, sys, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', sys.argv[2]])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "if sys.argv[3] == 'wait':\n"
        "    child.wait()\n"
    )
    SLEEPER = "import time\ntime.sleep(120)\n"
    FLOOD = "import sys\nwhile True:\n    sys.stdout.write('x' * 4096)\n    sys.stdout.flush()\n"

    def _descendant_pid(self, marker: Path) -> int:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                text = marker.read_text(encoding="utf-8").strip()
            except OSError:
                text = ""
            if text:
                return int(text)
            time.sleep(0.05)
        self.fail("o processo filho não registrou o pid do neto")

    def _assert_ended(self, pid: int) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.05)
        with __import__("contextlib").suppress(OSError):  # nunca deixar processo vivo no teste
            os.kill(pid, signal.SIGKILL)
        self.fail(f"o descendente {pid} sobreviveu ao encerramento")

    def _cmd(self, marker: Path, child_code: str, mode: str) -> list[str]:
        return [sys.executable, "-c", self.PARENT, str(marker), child_code, mode]

    def test_timeout_ends_the_descendant_too(self):
        root = _tmp_root(self)
        marker = root / "pid.txt"
        run = tl_graft._run(
            self._cmd(marker, self.SLEEPER, "wait"), cwd=root, timeout=3, env=os.environ.copy()
        )
        self.assertEqual(run.status, "timeout")
        self._assert_ended(self._descendant_pid(marker))

    def test_a_descendant_that_outlives_the_leader_is_ended_and_drains_the_pipe(self):
        root = _tmp_root(self)
        marker = root / "pid.txt"
        with mock.patch.object(tl_graft, "DRAIN_JOIN_SECONDS", 1.0):
            started = time.monotonic()
            run = tl_graft._run(
                self._cmd(marker, self.SLEEPER, "exit"), cwd=root, timeout=90, env=os.environ.copy()
            )
            elapsed = time.monotonic() - started
        self.assertEqual(run.status, "ok")
        self.assertLess(elapsed, 60, "_run ficou preso no pipe herdado pelo descendente")
        self._assert_ended(self._descendant_pid(marker))

    def test_capture_limit_ends_the_descendant_that_produced_the_output(self):
        root = _tmp_root(self)
        marker = root / "pid.txt"
        run = tl_graft._run(
            self._cmd(marker, self.FLOOD, "wait"),
            cwd=root,
            timeout=90,
            env=os.environ.copy(),
            byte_limit=200_000,
        )
        self.assertEqual(run.status, "limit")
        self._assert_ended(self._descendant_pid(marker))


@unittest.skipUnless(os.name == "nt", "contenção por job object é exclusiva do Windows")
class TestWindowsDescendantContainment(unittest.TestCase):
    """R20: the job object must end a descendant that outlives the leader, whether the leader
    was killed on timeout/limit or exited on its own leaving the pipe inherited — the same
    scope `TestPosixDescendantContainment` proves on POSIX via the process group."""

    PARENT = TestPosixDescendantContainment.PARENT
    SLEEPER = TestPosixDescendantContainment.SLEEPER
    FLOOD = TestPosixDescendantContainment.FLOOD

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_INVALID_PARAMETER = 87  # OpenProcess on a pid that names no process

    def _descendant_pid(self, marker: Path) -> int:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                text = marker.read_text(encoding="utf-8").strip()
            except OSError:
                text = ""
            if text:
                return int(text)
            time.sleep(0.05)
        self.fail("o processo filho não registrou o pid do neto")

    def _kernel32(self):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        return kernel32

    def _last_error(self) -> int:
        import ctypes

        return ctypes.get_last_error()

    def _pid_alive(self, pid: int) -> bool:
        """True while running, False only when the process is proven gone or exited; any other
        failure to inspect it fails the test instead of passing as a death."""
        import ctypes
        from ctypes import wintypes

        kernel32 = self._kernel32()
        handle = kernel32.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            error = self._last_error()
            if error == self.ERROR_INVALID_PARAMETER:
                return False
            self.fail(f"OpenProcess({pid}) falhou com erro {error}; encerramento não comprovado")
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                self.fail(f"GetExitCodeProcess({pid}) falhou com erro {self._last_error()}")
            return code.value == self.STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    def _assert_ended(self, pid: int) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not self._pid_alive(pid):
                return
            time.sleep(0.05)
        with __import__("contextlib").suppress(OSError):  # nunca deixar processo vivo no teste
            os.kill(pid, signal.SIGTERM)
        self.fail(f"o descendente {pid} sobreviveu ao encerramento")

    def _cmd(self, marker: Path, child_code: str, mode: str) -> list[str]:
        return [sys.executable, "-c", self.PARENT, str(marker), child_code, mode]

    def test_probe_sees_a_known_live_process_and_then_its_death(self):
        """R27: the probe itself must tell alive from ended, or the tests below prove nothing."""
        proc = subprocess.Popen([sys.executable, "-c", self.SLEEPER])
        self.addCleanup(lambda: (proc.poll() is None and proc.kill(), proc.wait()))
        self.assertTrue(self._pid_alive(proc.pid))
        proc.kill()
        proc.wait(timeout=30)
        self._assert_ended(proc.pid)

    def test_probe_query_failures_fail_instead_of_passing_as_death(self):
        class _DeniedOpen:
            def OpenProcess(self, access, inherit, pid):
                return None

        class _FailedExitCode:
            closed: list = []

            def OpenProcess(self, access, inherit, pid):
                return 1234

            def GetExitCodeProcess(self, handle, code):
                return 0

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return 1

        access_denied = 5
        with mock.patch.object(self, "_kernel32", return_value=_DeniedOpen()), mock.patch.object(
            self, "_last_error", return_value=access_denied
        ):
            with self.assertRaises(AssertionError):
                self._pid_alive(4242)
            with self.assertRaises(AssertionError):
                self._assert_ended(4242)
        failed = _FailedExitCode()
        with mock.patch.object(self, "_kernel32", return_value=failed), mock.patch.object(
            self, "_last_error", return_value=access_denied
        ):
            with self.assertRaises(AssertionError):
                self._pid_alive(4242)
        self.assertEqual(failed.closed, [1234])

    def test_timeout_ends_the_descendant_too(self):
        root = _tmp_root(self)
        marker = root / "pid.txt"
        run = tl_graft._run(
            self._cmd(marker, self.SLEEPER, "wait"), cwd=root, timeout=3, env=os.environ.copy()
        )
        self.assertEqual(run.status, "timeout")
        self._assert_ended(self._descendant_pid(marker))

    def test_a_descendant_that_outlives_the_leader_is_ended_and_drains_the_pipe(self):
        # "exit" mode: the leader (PARENT) returns immediately after spawning the sleeper and
        # never waits on it, so the sleeper is the one still holding whatever pipe it inherited
        # once the leader is gone — the scenario R20 flagged as unreachable by `taskkill /T`.
        root = _tmp_root(self)
        marker = root / "pid.txt"
        with mock.patch.object(tl_graft, "DRAIN_JOIN_SECONDS", 1.0):
            started = time.monotonic()
            run = tl_graft._run(
                self._cmd(marker, self.SLEEPER, "exit"), cwd=root, timeout=90, env=os.environ.copy()
            )
            elapsed = time.monotonic() - started
        self.assertEqual(run.status, "ok")
        self.assertLess(elapsed, 60, "_run ficou preso no descendente após o líder sair")
        self._assert_ended(self._descendant_pid(marker))

    def test_capture_limit_ends_the_descendant_that_produced_the_output(self):
        root = _tmp_root(self)
        marker = root / "pid.txt"
        run = tl_graft._run(
            self._cmd(marker, self.FLOOD, "wait"),
            cwd=root,
            timeout=90,
            env=os.environ.copy(),
            byte_limit=200_000,
        )
        self.assertEqual(run.status, "limit")
        self._assert_ended(self._descendant_pid(marker))


if __name__ == "__main__":
    unittest.main()
