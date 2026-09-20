#!/usr/bin/env python3
"""Local, fail-closed distribution helper for TL-Orchestrator development.

The registry deliberately lives in the user's config directory, never in either
the source checkout or a consumer.  This command has no network behaviour.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SHA_RE = re.compile(r"[0-9a-f]{40}")
CONFIG_FORMAT = 1
PACKAGE_DESTINATION = Path("_tl-orc/package")
INTEGRATIONS = (Path(".agents/skills/tl-orchestrator"), Path(".claude/skills/tl-orchestrator"))
CANONICAL_ORIGIN = "https://github.com/thinglab-dev/tl-orchestrator"


class TlOrcError(RuntimeError):
    """A safe, user-actionable refusal."""


@dataclass(frozen=True)
class Source:
    root: Path
    commit: str
    version: str
    files: tuple[str, ...]
    hashes: dict[str, str]


def default_config_dir() -> Path:
    configured = os.environ.get("TL_ORC_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "tl-orc"


def config_path(config_dir: Path) -> Path:
    return config_dir / "registry.json"


def load_config(config_dir: Path) -> dict[str, object]:
    path = config_path(config_dir)
    if not path.exists():
        return {"format_version": CONFIG_FORMAT, "consumers": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TlOrcError(f"invalid local registry {path}: {exc}") from exc
    if value.get("format_version") != CONFIG_FORMAT or not isinstance(value.get("consumers"), dict):
        raise TlOrcError(f"invalid local registry format: {path}")
    return value


def save_config(config_dir: Path, config: dict[str, object]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_path(config_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise TlOrcError(f"source is not an identified Git checkout: {message}")
    return result.stdout.strip()


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{relative}"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip() or "git show failed"
        raise TlOrcError(f"cannot recover installed baseline {commit}:{relative}: {message}")
    return result.stdout


def historical_package_hashes(root: Path, commit: str) -> dict[str, str]:
    """Recover an old package baseline from the local canonical Git object database."""
    if not SHA_RE.fullmatch(commit):
        raise TlOrcError("legacy installation has no valid full installed_commit")
    try:
        manifest = json.loads(git_blob(root, commit, "distribution-manifest.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TlOrcError(f"cannot recover legacy distribution manifest at {commit}: {exc}") from exc
    files = manifest.get("package_files")
    if (
        manifest.get("format_version") != 1
        or not isinstance(files, list)
        or not files
        or manifest.get("package_file_count") != len(files)
        or len(files) != len(set(files))
        or not all(isinstance(item, str) for item in files)
    ):
        raise TlOrcError(f"invalid historical distribution manifest at {commit}")
    hashes: dict[str, str] = {}
    for relative in files:
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.as_posix() != relative or any(part in {"", ".", ".."} for part in candidate.parts):
            raise TlOrcError(f"invalid historical package path at {commit}: {relative}")
        hashes[relative] = hashlib.sha256(git_blob(root, commit, relative)).hexdigest()
    return hashes


def validate_source(source_root: Path, *, require_clean: bool) -> Source:
    root = source_root.expanduser().resolve()
    manifest_path = root / "distribution-manifest.json"
    if not manifest_path.is_file():
        raise TlOrcError(f"source has no distribution-manifest.json: {root}")
    if require_clean and git(root, "status", "--porcelain"):
        raise TlOrcError("refusing dirty source checkout; commit or stash it before sync")
    commit = git(root, "rev-parse", "HEAD")
    if not SHA_RE.fullmatch(commit):
        raise TlOrcError("source HEAD is not a full Git commit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TlOrcError(f"invalid distribution manifest: {exc}") from exc
    files = manifest.get("package_files")
    if (
        manifest.get("format_version") != 1
        or not isinstance(files, list)
        or not files
        or manifest.get("package_file_count") != len(files)
        or len(files) != len(set(files))
        or not all(isinstance(item, str) for item in files)
    ):
        raise TlOrcError("invalid distribution manifest structure")
    hashes: dict[str, str] = {}
    for relative in files:
        candidate = Path(relative)
        if (
            candidate.is_absolute()
            or candidate.as_posix() != relative
            or any(part in {"", ".", ".."} for part in candidate.parts)
            or not (root / candidate).is_file()
            or (root / candidate).is_symlink()
        ):
            raise TlOrcError(f"invalid distribution manifest path: {relative}")
        hashes[relative] = sha256(root / candidate)
    version = manifest.get("package_version")
    if not isinstance(version, str):
        raise TlOrcError("distribution manifest package_version is missing")
    # `git tag --points-at` is the supported way to ask whether a tag resolves
    # to HEAD.  Do not use `--exact-match` here: it belongs to `git describe`.
    tags = git(root, "tag", "--points-at", "HEAD").splitlines()
    return Source(root, commit, tags[0] if tags else "none", tuple(files), hashes)


def current_source_checkout() -> Path | None:
    """Prefer the checkout from which a source-repository closure invokes `tl-orc`."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path.cwd()), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, check=False,
        )
    except OSError:
        return None
    if result.returncode:
        return None
    root = Path(result.stdout.strip()).resolve()
    if (root / "distribution-manifest.json").is_file() and (root / "scripts/tl_orc.py").is_file():
        return root
    return None


def git_common_dir(root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True, capture_output=True, check=False,
        )
    except OSError:
        return None
    if result.returncode or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def same_git_repository(left: Path, right: Path) -> bool:
    left_common = git_common_dir(left)
    right_common = git_common_dir(right)
    return left_common is not None and left_common == right_common


def source_from_config(config: dict[str, object], override: str | None, *, require_clean: bool) -> Source:
    if override:
        return validate_source(Path(override), require_clean=require_clean)
    configured = config.get("source_root")
    current = current_source_checkout()
    if current is not None:
        if configured is None:
            return validate_source(current, require_clean=require_clean)
        if isinstance(configured, str) and configured and same_git_repository(current, Path(configured).expanduser()):
            return validate_source(current, require_clean=require_clean)
    if not isinstance(configured, str) or not configured:
        raise TlOrcError("no canonical source configured; run install-cli --source <checkout>")
    return validate_source(Path(configured), require_clean=require_clean)


def installation_path(consumer: Path) -> Path:
    return consumer / "_tl-orc/INSTALLATION.md"


def assert_safe_consumer_path(consumer: Path, target: Path, *, allow_leaf_symlink: bool = False) -> None:
    """Refuse redirected ancestors before reading, moving, or deleting consumer content."""
    raw_root = consumer.expanduser().absolute()
    root = consumer.expanduser().resolve()
    target_abs = target.expanduser().absolute()
    try:
        relative = target_abs.relative_to(raw_root)
    except ValueError:
        try:
            relative = target_abs.relative_to(root)
        except ValueError as exc:
            raise TlOrcError(f"consumer path escapes root: {target}") from exc
    canonical_target = root / relative
    current = canonical_target.parent if allow_leaf_symlink else canonical_target
    while current != root:
        if current.is_symlink():
            raise TlOrcError(f"consumer path has redirected ancestor: {current}")
        if root not in current.parents:
            raise TlOrcError(f"consumer path escapes root: {target}")
        current = current.parent


def files_at(destination: Path) -> dict[str, str]:
    if not destination.exists():
        return {}
    if destination.is_symlink() or not destination.is_dir():
        raise TlOrcError(f"destination is not a normal directory: {destination}")
    files: dict[str, str] = {}
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise TlOrcError(f"destination contains unexpected symlink: {path}")
        if path.is_file():
            files[path.relative_to(destination).as_posix()] = sha256(path)
    return files


def registered_destination(value: str, installation: Path) -> str:
    """Accept only destinations owned by this tool, never arbitrary table cells."""
    normalized = value.strip().strip("`").rstrip("/")
    allowed = {PACKAGE_DESTINATION.as_posix(), *(item.as_posix() for item in INTEGRATIONS)}
    if normalized not in allowed:
        raise TlOrcError(f"existing installation has invalid integration destination {normalized!r}: {installation}")
    return normalized


def section(text: str, headings: tuple[str, ...]) -> str | None:
    for heading in headings:
        marker = heading + "\n"
        if marker in text:
            return text.split(marker, 1)[1].split("\n## ", 1)[0]
    return None


def legacy_hash_row(line: str) -> tuple[str, str] | None:
    """Parse either current bullet hashes or legacy Markdown SHA-256 tables."""
    bullet = re.fullmatch(r"- ([0-9a-f]{64})  (.+)", line)
    if bullet:
        return bullet.group(2).strip("`"), bullet.group(1)
    if "|" not in line:
        return None
    cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
    digest = next((cell for cell in cells if re.fullmatch(r"[0-9a-f]{64}", cell)), None)
    if digest is None:
        return None
    paths = [
        cell for cell in cells
        if cell != digest and cell.lower() not in {"file", "path", "package", "filename"}
        and not cell.lower().startswith(("sha", "hash"))
    ]
    if len(paths) != 1:
        raise TlOrcError(f"ambiguous package hash row: {line}")
    return paths[0], digest


def parse_installation(path: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Return header, manifest hashes and registered copy destinations."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TlOrcError(f"cannot read existing installation {path}: {exc}") from exc
    header: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if ": " in line:
            key, value = line.split(": ", 1)
            header[key] = value
    content = section(text, ("## Arquivos", "## Package hashes"))
    hashes: dict[str, str] = {}
    if content is not None:
        for line in content.splitlines():
            item = legacy_hash_row(line)
            if item:
                relative, digest = item
                if relative in hashes:
                    raise TlOrcError(f"existing installation repeats package hash {relative}: {path}")
                hashes[relative] = digest
        if not hashes:
            raise TlOrcError(f"existing installation has an empty/invalid package hash section: {path}")
    destinations = {PACKAGE_DESTINATION.as_posix()}
    integration_content = section(text, ("## Integrações", "## Harness integrations"))
    if integration_content is not None:
        for line in integration_content.splitlines():
            match = re.fullmatch(r"- (.+): copy, verified", line)
            if match:
                destinations.add(registered_destination(match.group(1), path))
                continue
            link_match = re.fullmatch(r"- (.+): link -> _tl-orc/package, verified", line)
            if link_match:
                destinations.add(registered_destination(link_match.group(1), path))
                continue
            if "|" in line:
                cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
                allowed_integrations = {item.as_posix() for item in INTEGRATIONS}
                for cell in cells:
                    normalized = cell.rstrip("/")
                    if normalized in allowed_integrations:
                        destinations.add(registered_destination(cell, path))
    return header, hashes, destinations


def assert_no_unauthorized_delta(
    consumer: Path, destinations: Iterable[Path], *, source_root: Path | None = None
) -> None:
    install = installation_path(consumer)
    existing = [destination for destination in destinations if destination.exists() or destination.is_symlink()]
    if not existing:
        return
    if not install.is_file():
        nonempty = [destination for destination in existing if not destination.is_symlink() and files_at(destination)]
        if nonempty or any(destination.is_symlink() for destination in existing):
            raise TlOrcError(f"local delta blocked: destinations exist without {install}")
        return
    header, expected, registered = parse_installation(install)
    if not expected:
        if source_root is None:
            raise TlOrcError(f"legacy installation has no hashes and no canonical local source: {install}")
        installed_commit = header.get("installed_commit", "")
        expected = historical_package_hashes(source_root, installed_commit)
        declared_count = header.get("package_file_count")
        if declared_count is None or not declared_count.isdigit() or int(declared_count) != len(expected):
            raise TlOrcError(f"legacy installation package_file_count does not match {installed_commit}: {install}")
    known_integrations = {item.as_posix() for item in INTEGRATIONS}
    for destination in existing:
        relative = destination.relative_to(consumer).as_posix()
        if destination.is_symlink():
            if relative not in registered and relative not in known_integrations:
                raise TlOrcError(f"local delta blocked: unregistered destination {relative}")
            verify_integration_link(consumer, destination)
            continue
        actual = files_at(destination)
        if relative not in registered:
            # Some pre-registry local-dev installs copied the standard harness destinations
            # without recording them. Adopt only an exact historical package copy; any byte
            # difference remains an unauthorized local delta.
            if relative not in known_integrations or actual != expected:
                raise TlOrcError(f"local delta blocked: unregistered destination {relative}")
        elif actual != expected:
            raise TlOrcError(f"local delta blocked in {relative}; preserve or reconcile it first")


def verify_integration_link(consumer: Path, target: Path) -> None:
    assert_safe_consumer_path(consumer, target, allow_leaf_symlink=True)
    if not target.is_symlink():
        raise TlOrcError(f"expected integration link is not a symlink: {target}")
    package = (consumer / PACKAGE_DESTINATION).resolve()
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise TlOrcError(f"broken integration link: {target}: {exc}") from exc
    if resolved != package:
        raise TlOrcError(f"integration link escapes canonical package: {target} -> {resolved}")


def selected_destinations(consumer: Path) -> list[Path]:
    """Return physical copies to replace; verified links remain in place."""
    consumer = consumer.expanduser().resolve()
    package = consumer / PACKAGE_DESTINATION
    assert_safe_consumer_path(consumer, package)
    destinations = [package]
    registered: set[str] = set()
    install = installation_path(consumer)
    if install.is_file():
        _, _, registered = parse_installation(install)
    for relative in INTEGRATIONS:
        target = consumer / relative
        if target.is_symlink():
            verify_integration_link(consumer, target)
            continue
        assert_safe_consumer_path(consumer, target)
        if target.exists() or relative.as_posix() in registered:
            destinations.append(target)
    return destinations


def copy_package(source: Source, destination: Path) -> None:
    for relative in source.files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.root / relative, target)
    if files_at(destination) != source.hashes:
        raise TlOrcError(f"staging verification failed for {destination}")


def installation_text(source: Source, destinations: Iterable[Path], consumer: Path) -> str:
    lines = [
        "format_version: 1",
        f"origin: {CANONICAL_ORIGIN}",
        "source_mode: local-dev",
        "source_validation: local-validated-commit",
        f"installed_version: {source.version}",
        f"installed_commit: {source.commit}",
        "update_check: disabled",
        "update_ref: refs/heads/main",
        "update_policy: notify",
        "contribution_mode: ask",
        "",
        "## Arquivos",
    ]
    lines.extend(f"- {source.hashes[item]}  {item}" for item in source.files)
    lines.extend(("", "## Integrações"))
    physical = {destination.relative_to(consumer).as_posix() for destination in destinations}
    lines.append(f"- {PACKAGE_DESTINATION.as_posix()}: copy, verified")
    for relative in INTEGRATIONS:
        target = consumer / relative
        if target.is_symlink():
            verify_integration_link(consumer, target)
            lines.append(f"- {relative.as_posix()}: link -> _tl-orc/package, verified")
        elif relative.as_posix() in physical:
            lines.append(f"- {relative.as_posix()}: copy, verified")
    lines.extend(("", "## Instalações concorrentes", "- nenhuma registrada", ""))
    return "\n".join(lines)


def replace_consumer(source: Source, consumer: Path) -> None:
    consumer = consumer.expanduser().resolve()
    if not consumer.is_dir():
        raise TlOrcError(f"consumer root is not an existing directory: {consumer}")
    destinations = selected_destinations(consumer)
    assert_no_unauthorized_delta(consumer, destinations, source_root=source.root)
    stage_root = Path(tempfile.mkdtemp(prefix=".tl-orc-stage-", dir=consumer))
    backup_root = Path(tempfile.mkdtemp(prefix=".tl-orc-backup-", dir=consumer))
    swapped: list[tuple[Path, Path | None]] = []
    installation = installation_path(consumer)
    installation_existed = installation.exists()
    try:
        staged: list[tuple[Path, Path]] = []
        for index, destination in enumerate(destinations):
            stage = stage_root / str(index)
            copy_package(source, stage)
            staged.append((destination, stage))
        for destination, stage in staged:
            backup = backup_root / str(len(swapped)) if destination.exists() else None
            if backup is not None:
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, backup)
            # Record the old destination before the second rename.  A failure at
            # that point must restore this destination too, not just earlier ones.
            swapped.append((destination, backup))
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, destination)
        install_stage = stage_root / "INSTALLATION.md"
        install_stage.parent.mkdir(parents=True, exist_ok=True)
        install_stage.write_text(installation_text(source, destinations, consumer), encoding="utf-8")
        previous_install = backup_root / "INSTALLATION.md" if installation_existed else None
        if previous_install is not None:
            os.replace(installation, previous_install)
        installation.parent.mkdir(parents=True, exist_ok=True)
        os.replace(install_stage, installation)
        # Verify the final on-disk consumer while backups still exist so any
        # unexpected post-swap mismatch rolls back this consumer atomically.
        verify_consumer(source, consumer)
    except Exception:
        for destination, backup in reversed(swapped):
            if destination.exists():
                shutil.rmtree(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
        previous_install = backup_root / "INSTALLATION.md"
        installation = installation_path(consumer)
        if previous_install.exists():
            if installation.exists():
                installation.unlink()
            os.replace(previous_install, installation)
        elif not installation_existed and installation.exists():
            installation.unlink()
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
        shutil.rmtree(backup_root, ignore_errors=True)


def verify_consumer(source: Source, consumer: Path) -> None:
    consumer = consumer.expanduser().resolve()
    if not consumer.is_dir():
        raise TlOrcError(f"consumer root is not an existing directory: {consumer}")
    install = installation_path(consumer)
    assert_safe_consumer_path(consumer, install)
    if not install.is_file():
        raise TlOrcError(f"missing {install}")
    header, hashes, registered = parse_installation(install)
    if header.get("source_mode") != "local-dev" or header.get("installed_commit") != source.commit:
        raise TlOrcError(f"installation commit/mode differs: {consumer}")
    if header.get("installed_version") != source.version or hashes != source.hashes:
        raise TlOrcError(f"installation manifest differs: {consumer}")
    if PACKAGE_DESTINATION.as_posix() not in registered:
        raise TlOrcError(f"package destination is not registered: {consumer}")
    for relative in sorted(registered):
        target = consumer / relative
        if target.is_symlink():
            verify_integration_link(consumer, target)
            continue
        if files_at(target) != source.hashes:
            raise TlOrcError(f"destination differs from source: {target}")


def smoke_consumer(source: Source, consumer: Path) -> None:
    consumer = consumer.expanduser().resolve()
    verify_consumer(source, consumer)
    package = consumer / PACKAGE_DESTINATION
    before = {path.relative_to(consumer).as_posix() for path in consumer.rglob("*")}
    critical = ("scripts/tl_orc.py", "scripts/tl_runtime.py", "scripts/validate_classification.py")
    for relative in critical:
        target = package / relative
        if target.exists():
            try:
                ast.parse(target.read_text(encoding="utf-8"), filename=str(target), mode="exec")
            except (OSError, SyntaxError) as exc:
                raise TlOrcError(f"safe Python parse failed for {target}: {exc}") from exc
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(package / "scripts/tl_orc.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode:
        raise TlOrcError(f"safe CLI help failed for {consumer}: {result.stderr.strip()}")
    # Re-hash all managed destinations after the probe. This catches content
    # mutation even when no path was added/removed, while the path snapshot
    # catches bytecode/cache files created outside the registered destinations.
    verify_consumer(source, consumer)
    after = {path.relative_to(consumer).as_posix() for path in consumer.rglob("*")}
    if after != before:
        raise TlOrcError(f"smoke must be read-only; consumer files changed: {consumer}")


def consumer_entries(config: dict[str, object], names: list[str], all_consumers: bool) -> list[tuple[str, Path]]:
    consumers = config["consumers"]
    assert isinstance(consumers, dict)
    chosen = sorted(consumers) if all_consumers else names
    if not chosen:
        raise TlOrcError("select a consumer name or pass --all")
    entries: list[tuple[str, Path]] = []
    for name in chosen:
        raw = consumers.get(name)
        if not isinstance(raw, str):
            raise TlOrcError(f"consumer is not registered: {name}")
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            raise TlOrcError(f"consumer root is not an existing directory: {root}")
        entries.append((name, root))
    return entries


def command_install_cli(args: argparse.Namespace, config: dict[str, object]) -> int:
    source = validate_source(Path(args.source), require_clean=True)
    config["source_root"] = str(source.root)
    save_config(args.config_dir, config)
    bin_dir = Path(args.bin_dir).expanduser() if args.bin_dir else Path.home() / ".local/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "tl-orc"
    launcher.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(source.root / 'scripts/tl_orc.py'))} \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    print(f"configured source: {source.root}")
    print(f"launcher installed: {launcher}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=default_config_dir(), help="local registry directory (default: user config)")
    parser.add_argument("--source", help="canonical source checkout override")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show local configuration")
    subparsers.add_parser("consumers", help="list registered consumers")
    register = subparsers.add_parser("register", help="register a consumer root")
    register.add_argument("name")
    register.add_argument("root", type=Path)
    unregister = subparsers.add_parser("unregister", help="remove a consumer from the local registry")
    unregister.add_argument("name")
    for command in ("sync", "verify", "smoke"):
        current = subparsers.add_parser(command, help=f"{command} registered consumers")
        current.add_argument("names", nargs="*")
        current.add_argument("--all", action="store_true")
    install = subparsers.add_parser("install-cli", help="configure source and install a thin local launcher")
    install.add_argument("--source", required=True, dest="install_source")
    install.add_argument("--bin-dir")
    args = parser.parse_args(argv)
    args.config_dir = args.config_dir.expanduser()
    try:
        config = load_config(args.config_dir)
        if args.command == "install-cli":
            args.source = args.install_source
            return command_install_cli(args, config)
        if args.command == "register":
            root = args.root.expanduser().resolve()
            if not root.is_dir():
                raise TlOrcError(f"consumer root is not a directory: {root}")
            consumers = config["consumers"]
            assert isinstance(consumers, dict)
            consumers[args.name] = str(root)
            save_config(args.config_dir, config)
            print(f"registered {args.name}: {root}")
            return 0
        if args.command == "unregister":
            consumers = config["consumers"]
            assert isinstance(consumers, dict)
            if args.name not in consumers:
                raise TlOrcError(f"consumer is not registered: {args.name}")
            del consumers[args.name]
            save_config(args.config_dir, config)
            print(f"unregistered {args.name}")
            return 0
        if args.command in {"status", "consumers"}:
            print(json.dumps(config, indent=2, sort_keys=True))
            return 0
        source = source_from_config(config, args.source, require_clean=True)
        entries = consumer_entries(config, args.names, args.all)
        failures = 0
        for name, consumer in entries:
            try:
                if args.command == "sync":
                    replace_consumer(source, consumer)
                elif args.command == "verify":
                    verify_consumer(source, consumer)
                else:
                    smoke_consumer(source, consumer)
                print(f"OK {args.command} {name}: {consumer}")
            except (TlOrcError, OSError) as exc:
                failures += 1
                print(f"ERROR {args.command} {name}: {exc}", file=sys.stderr)
        return 1 if failures else 0
    except TlOrcError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
