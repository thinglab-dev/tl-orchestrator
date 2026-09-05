#!/usr/bin/env python3
"""Validate repository structure; this does not prove method behavior."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "distribution-manifest.json"
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load_manifest() -> list[str]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid distribution manifest: {exc}")
    if data.get("format_version") != 1:
        fail("distribution manifest format_version must be 1")
    files = data.get("package_files")
    if not isinstance(files, list) or not files or not all(isinstance(x, str) for x in files):
        fail("package_files must be a non-empty string array")
    if len(files) != len(set(files)) or data.get("package_file_count") != len(files):
        fail("package manifest count or uniqueness mismatch")
    normalized: set[str] = set()
    for item in files:
        path = Path(item)
        canonical = path.as_posix()
        if (
            not item
            or item != canonical
            or item.startswith("./")
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or canonical in normalized
        ):
            fail(f"non-canonical package path: {item}")
        normalized.add(canonical)
        source = ROOT / path
        if source.is_symlink() or not source.is_file():
            fail(f"invalid or missing package path: {item}")
        try:
            source.resolve(strict=True).relative_to(ROOT.resolve())
        except ValueError:
            fail(f"package path resolves outside repository: {item}")
        current = ROOT
        for part in path.parts[:-1]:
            current /= part
            if current.is_symlink():
                fail(f"package path traverses a symlink: {item}")
    return files


def validate_json() -> None:
    for path in sorted(ROOT.rglob("*.json")):
        if ".git" in path.parts or "_tl-orc" in path.parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def validate_frontmatter() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        fail("SKILL.md frontmatter is missing or malformed")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            fail(f"unsupported SKILL.md frontmatter line: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"} or fields["name"] != "tl-orchestrator":
        fail("SKILL.md frontmatter must contain only canonical name and description")
    if not fields["description"]:
        fail("SKILL.md description must not be empty")


def github_slug(heading: str) -> str:
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[`*~]", "", heading).strip().lower()
    heading = "".join(char for char in heading if unicodedata.category(char)[0] not in {"P", "S"} or char in "-_ ")
    return re.sub(r"\s", "-", heading).strip("-")


def heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", path.read_text(encoding="utf-8"), re.MULTILINE):
        base = github_slug(heading)
        number = occurrences.get(base, 0)
        occurrences[base] = number + 1
        anchors.add(base if number == 0 else f"{base}-{number}")
    return anchors


def resolve_link(source: Path, target: str, package: set[Path]) -> None:
    target = unquote(target.strip().split()[0])
    if not target or target.startswith(("https://", "http://", "mailto:")):
        return
    clean, separator, anchor = target.partition("#")
    resolved = source.resolve() if not clean else (source.parent / clean).resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        fail(f"link escapes repository in {source.relative_to(ROOT)}: {target}")
    if not resolved.is_file():
        fail(f"broken local link in {source.relative_to(ROOT)}: {target}")
    source_relative = source.relative_to(ROOT)
    if source_relative in package and relative not in package:
        fail(f"distributed file links to repo-only path in {source_relative}: {target}")
    if separator and anchor and anchor not in heading_anchors(resolved):
        fail(f"broken anchor in {source_relative}: {target}")


def validate_links(files: list[str]) -> None:
    package = {Path(item) for item in files}
    markdown = {path for path in package if path.suffix == ".md"}
    markdown.update({Path("CHANGELOG.md"), Path("CONTRIBUTING.md")})
    for relative in sorted(markdown):
        source = ROOT / relative
        for target in LINK_RE.findall(source.read_text(encoding="utf-8")):
            resolve_link(source, target, package)


def validate_export(files: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="tl-orchestrator-validate-") as tmp:
        export = Path(tmp)
        for item in files:
            source = ROOT / item
            destination = export / item
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        exported = sorted(str(path.relative_to(export)) for path in export.rglob("*") if path.is_file())
        if exported != sorted(files):
            fail("exported path set differs from manifest")
        for item in files:
            source_hash = hashlib.sha256((ROOT / item).read_bytes()).digest()
            export_hash = hashlib.sha256((export / item).read_bytes()).digest()
            if source_hash != export_hash:
                fail(f"export hash mismatch: {item}")


def shell_block(readme: str, first_line: str) -> str:
    marker = f"```sh\n{first_line}"
    if marker not in readme:
        fail(f"README shell block is missing: {first_line}")
    return first_line + readme.split(marker, 1)[1].split("```", 1)[0]


def validate_readme_manifest(files: list[str]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    marker = "<!-- distribution-manifest:start -->"
    end_marker = "<!-- distribution-manifest:end -->"
    if marker not in readme or end_marker not in readme:
        fail("README distribution manifest markers are missing")
    block = readme.split(marker, 1)[1].split(end_marker, 1)[0]
    listed = re.findall(r"^- `([^`]+)`$", block, re.MULTILINE)
    if listed != files:
        fail("README package list differs from distribution-manifest.json")
    if f"exatamente {len(files)} arquivos" not in readme:
        fail("README package count does not match manifest")
    expected = set(files)
    export_tokens = set(shlex.split(shell_block(readme, "set -eu")))
    hash_tokens = set(shlex.split(shell_block(readme, "checksum_file=$(mktemp")))
    if expected.intersection(export_tokens) != expected:
        missing = sorted(expected.difference(export_tokens))
        fail(f"README export commands omit manifest paths: {', '.join(missing)}")
    if expected.intersection(hash_tokens) != expected:
        missing = sorted(expected.difference(hash_tokens))
        fail(f"README hash commands omit manifest paths: {', '.join(missing)}")


def main() -> None:
    files = load_manifest()
    validate_json()
    validate_frontmatter()
    validate_links(files)
    validate_export(files)
    validate_readme_manifest(files)
    print(f"OK: {len(files)} package files; JSON, frontmatter, links, export and hashes validated")
    print("NOTE: structural checks do not prove method behavior")


if __name__ == "__main__":
    main()
