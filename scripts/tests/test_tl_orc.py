"""Offline contract tests for the local development distribution CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import tl_orc


ROOT = Path(__file__).resolve().parents[2]


class TlOrcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        (self.source / "scripts").mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts/tl_orc.py", self.source / "scripts/tl_orc.py")
        (self.source / "README.md").write_text("local source\n", encoding="utf-8")
        (self.source / "distribution-manifest.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "package_version": "9.9.9",
                    "package_file_count": 2,
                    "package_files": ["README.md", "scripts/tl_orc.py"],
                }
            ),
            encoding="utf-8",
        )
        self.git("init")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "TL test")
        self.git("add", ".")
        self.git("commit", "-m", "source")
        self.config_dir = self.base / "config"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> None:
        result = subprocess.run(["git", "-C", str(self.source), *args], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def source_info(self) -> tl_orc.Source:
        return tl_orc.validate_source(self.source, require_clean=True)

    def test_registry_install_launcher_and_status_are_local(self) -> None:
        home = self.base / "home"
        with mock.patch.object(tl_orc.Path, "home", return_value=home):
            self.assertEqual(
                tl_orc.main(["--config-dir", str(self.config_dir), "install-cli", "--source", str(self.source)]),
                0,
            )
        consumer = self.base / "consumer"
        consumer.mkdir()
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "register", "one", str(consumer)]), 0)
        config = json.loads((self.config_dir / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(config["source_root"], str(self.source.resolve()))
        self.assertEqual(config["consumers"], {"one": str(consumer.resolve())})
        self.assertTrue((home / ".local/bin/tl-orc").is_file())
        self.assertFalse((self.source / ".tl-orc").exists())
        self.assertFalse((consumer / ".tl-orc").exists())

    def test_sync_multiple_consumers_integrations_verify_smoke_and_project_preserved(self) -> None:
        first = self.base / "first"
        second = self.base / "second"
        for consumer in (first, second):
            (consumer / "_tl-orc/project/evidence").mkdir(parents=True)
            (consumer / "_tl-orc/project/evidence/keep.txt").write_text("keep", encoding="utf-8")
        (first / ".agents/skills/tl-orchestrator").mkdir(parents=True)
        config = {"format_version": 1, "source_root": str(self.source), "consumers": {"first": str(first), "second": str(second)}}
        tl_orc.save_config(self.config_dir, config)
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 0)
        source = self.source_info()
        for consumer in (first, second):
            self.assertEqual(tl_orc.files_at(consumer / "_tl-orc/package"), source.hashes)
            self.assertEqual((consumer / "_tl-orc/project/evidence/keep.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual(tl_orc.files_at(first / ".agents/skills/tl-orchestrator"), source.hashes)
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "verify", "--all"]), 0)
        before_smoke = {path.relative_to(first).as_posix() for path in first.rglob("*")}
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "smoke", "--all"]), 0)
        after_smoke = {path.relative_to(first).as_posix() for path in first.rglob("*")}
        self.assertEqual(after_smoke, before_smoke)
        self.assertFalse(any("__pycache__" in item for item in after_smoke))

    def test_current_legacy_installation_migrates_only_when_copies_match_hashes(self) -> None:
        consumer = self.base / "consumer"
        package = consumer / "_tl-orc/package"
        integration = consumer / ".agents/skills/tl-orchestrator"
        source = self.source_info()
        tl_orc.copy_package(source, package)
        tl_orc.copy_package(source, integration)
        hashes = "\n".join(f"| `{item}` | `{source.hashes[item]}` |" for item in source.files)
        tl_orc.installation_path(consumer).write_text(
            "\n".join(
                (
                    "format_version: 1",
                    "origin: https://github.com/thinglab-dev/tl-orchestrator",
                    "installed_version: none",
                    f"installed_commit: {source.commit}",
                    "update_check: enabled",
                    "",
                    "## Harness integrations",
                    "| Harness | Destination | Mode |",
                    "| --- | --- | --- |",
                    "| canonical project package | `_tl-orc/package/` | canonical copy |",
                    "| Codex | `.agents/skills/tl-orchestrator/` | copy |",
                    "",
                    "## Package hashes",
                    "| Path | SHA-256 |",
                    "| --- | --- |",
                    hashes,
                    "",
                )
            ),
            encoding="utf-8",
        )
        _, legacy_hashes, legacy_destinations = tl_orc.parse_installation(tl_orc.installation_path(consumer))
        self.assertEqual(legacy_hashes, source.hashes)
        self.assertIn(".agents/skills/tl-orchestrator", legacy_destinations)
        tl_orc.save_config(
            self.config_dir,
            {"format_version": 1, "source_root": str(self.source), "consumers": {"one": str(consumer)}},
        )
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 0)
        normalized = tl_orc.installation_path(consumer).read_text(encoding="utf-8")
        self.assertIn("origin: https://github.com/thinglab-dev/tl-orchestrator", normalized)
        self.assertIn("source_mode: local-dev", normalized)
        self.assertIn("source_validation: local-validated-commit", normalized)
        self.assertNotIn(str(self.source), normalized)
        (integration / "README.md").write_text("local delta", encoding="utf-8")
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 1)
        self.assertEqual((integration / "README.md").read_text(encoding="utf-8"), "local delta")

    def test_header_only_legacy_install_recovers_baseline_and_adopts_exact_standard_copies(self) -> None:
        consumer = self.base / "header-only"
        package = consumer / "_tl-orc/package"
        integration = consumer / ".agents/skills/tl-orchestrator"
        source = self.source_info()
        tl_orc.copy_package(source, package)
        tl_orc.copy_package(source, integration)
        tl_orc.installation_path(consumer).write_text(
            "\n".join((
                "source_repository: thinglab-dev/tl-orchestrator",
                f"installed_commit: {source.commit}",
                f"package_file_count: {len(source.files)}",
                "update_policy: notify",
                "",
                "# legacy local-dev note without hash/integration tables",
                "",
            )),
            encoding="utf-8",
        )
        tl_orc.save_config(
            self.config_dir,
            {"format_version": 1, "source_root": str(self.source), "consumers": {"legacy": str(consumer)}},
        )
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 0)
        self.assertEqual(tl_orc.files_at(integration), source.hashes)
        normalized = tl_orc.installation_path(consumer).read_text(encoding="utf-8")
        self.assertIn("source_mode: local-dev", normalized)
        self.assertIn(".agents/skills/tl-orchestrator: copy, verified", normalized)

    def test_relative_integration_links_are_preserved_and_verified(self) -> None:
        consumer = self.base / "linked"
        package = consumer / "_tl-orc/package"
        source = self.source_info()
        tl_orc.copy_package(source, package)
        for relative in tl_orc.INTEGRATIONS:
            target = consumer / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink("../../_tl-orc/package", target)
        tl_orc.installation_path(consumer).write_text(
            tl_orc.installation_text(source, [package], consumer), encoding="utf-8"
        )
        tl_orc.save_config(
            self.config_dir,
            {"format_version": 1, "source_root": str(self.source), "consumers": {"linked": str(consumer)}},
        )
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 0)
        for relative in tl_orc.INTEGRATIONS:
            target = consumer / relative
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), package.resolve())
        installation = tl_orc.installation_path(consumer).read_text(encoding="utf-8")
        self.assertIn("link -> _tl-orc/package, verified", installation)
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "verify", "--all"]), 0)

    def test_sync_from_source_checkout_prefers_current_worktree_of_same_repository(self) -> None:
        consumer = self.base / "cwd-consumer"
        consumer.mkdir()
        configured = self.base / "configured-worktree"
        result = subprocess.run(
            ["git", "-C", str(self.source), "worktree", "add", "--detach", str(configured), "HEAD"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            # Make the configured worktree dirty. The clean current worktree should win because
            # both share the same Git common-dir.
            (configured / "README.md").write_text("dirty configured worktree\n", encoding="utf-8")
            tl_orc.save_config(
                self.config_dir,
                {"format_version": 1, "source_root": str(configured), "consumers": {"one": str(consumer)}},
            )
            previous = Path.cwd()
            try:
                os.chdir(self.source)
                self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 0)
            finally:
                os.chdir(previous)
            self.assertEqual(tl_orc.files_at(consumer / "_tl-orc/package"), self.source_info().hashes)
        finally:
            subprocess.run(
                ["git", "-C", str(self.source), "worktree", "remove", "--force", str(configured)],
                text=True, capture_output=True, check=False,
            )

    def test_dirty_source_invalid_manifest_and_delta_fail_closed(self) -> None:
        consumer = self.base / "consumer"
        consumer.mkdir()
        config = {"format_version": 1, "source_root": str(self.source), "consumers": {"one": str(consumer)}}
        tl_orc.save_config(self.config_dir, config)
        (self.source / "README.md").write_text("dirty\n", encoding="utf-8")
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 2)
        self.git("add", "README.md")
        self.git("commit", "-m", "dirty committed")
        (self.source / "distribution-manifest.json").write_text("{}", encoding="utf-8")
        self.git("add", "distribution-manifest.json")
        self.git("commit", "-m", "invalid manifest")
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 2)
        # Restore a valid commit, then prove an unrecorded consumer copy is not overwritten.
        self.git("reset", "--hard", "HEAD~1")
        package = consumer / "_tl-orc/package"
        package.mkdir(parents=True)
        (package / "local.txt").write_text("do not erase", encoding="utf-8")
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "sync", "--all"]), 1)
        self.assertTrue((package / "local.txt").exists())

    def test_redirected_consumer_ancestor_is_refused_before_any_write(self) -> None:
        consumer = self.base / "redirected"
        consumer.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        os.symlink(outside, consumer / "_tl-orc")
        source = self.source_info()
        with self.assertRaisesRegex(tl_orc.TlOrcError, "redirected ancestor"):
            tl_orc.replace_consumer(source, consumer)
        self.assertEqual(list(outside.iterdir()), [])

    def test_verify_and_smoke_refuse_dirty_source_checkout(self) -> None:
        consumer = self.base / "dirty-read-source"
        consumer.mkdir()
        source = self.source_info()
        tl_orc.replace_consumer(source, consumer)
        tl_orc.save_config(
            self.config_dir,
            {"format_version": 1, "source_root": str(self.source), "consumers": {"one": str(consumer)}},
        )
        (self.source / "README.md").write_text("dirty after install\n", encoding="utf-8")
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "verify", "--all"]), 2)
        self.assertEqual(tl_orc.main(["--config-dir", str(self.config_dir), "smoke", "--all"]), 2)

    def test_new_install_rollback_removes_new_installation_record(self) -> None:
        consumer = self.base / "new-rollback"
        consumer.mkdir()
        source = self.source_info()
        real_verify = tl_orc.verify_consumer
        def fail_final_verify(source_arg, consumer_arg):
            if tl_orc.installation_path(consumer_arg).exists():
                raise tl_orc.TlOrcError("simulated post-swap verification failure")
            return real_verify(source_arg, consumer_arg)
        with mock.patch.object(tl_orc, "verify_consumer", side_effect=fail_final_verify):
            with self.assertRaises(tl_orc.TlOrcError):
                tl_orc.replace_consumer(source, consumer)
        self.assertFalse((consumer / "_tl-orc/package").exists())
        self.assertFalse(tl_orc.installation_path(consumer).exists())

    def test_rollback_restores_destination_when_staged_replacement_fails_after_backup(self) -> None:
        consumer = self.base / "consumer"
        package = consumer / "_tl-orc/package"
        package.mkdir(parents=True)
        source = self.source_info()
        tl_orc.copy_package(source, package)
        tl_orc.installation_path(consumer).write_text(
            tl_orc.installation_text(source, [package], consumer), encoding="utf-8"
        )
        before = tl_orc.files_at(package)
        before_installation = tl_orc.installation_path(consumer).read_text(encoding="utf-8")
        real_replace = os.replace
        calls = 0

        def fail_second_stage(old: os.PathLike[str], new: os.PathLike[str]) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:  # old package is already in backup; staged replacement now fails.
                raise OSError("simulated replace failure")
            real_replace(old, new)

        with mock.patch.object(tl_orc.os, "replace", side_effect=fail_second_stage):
            with self.assertRaises(OSError):
                tl_orc.replace_consumer(source, consumer)
        self.assertEqual(tl_orc.files_at(package), before)
        self.assertEqual(tl_orc.installation_path(consumer).read_text(encoding="utf-8"), before_installation)

    def test_exact_head_tag_is_reported_and_non_tagged_head_is_none(self) -> None:
        self.assertEqual(self.source_info().version, "none")
        self.git("tag", "v9.9.9")
        self.assertEqual(self.source_info().version, "v9.9.9")


if __name__ == "__main__":
    unittest.main()
