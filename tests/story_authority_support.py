#!/usr/bin/env python3
"""Shared offline scaffolding for the AUTO_STORY suites (T032/T033).

No network, no model call and no write outside the temporary directory of each test. Every
helper here builds real artifacts — a real git repository, a real frozen envelope, a real
append-only journal — because the properties under test are about what is on disk after a
crash, not about what a mock was asked to return.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "auto_story_b013_b014"
for _path in (REPO_ROOT, SCRIPTS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import tl_story_authority as story  # noqa: E402
import validate_execution_plan as plan_validator  # noqa: E402


# R10 counterproofs: every one of these would join onto the repository root and land outside it.
ESCAPING_PATTERNS = {
    "posix_absolute": "/etc",
    "parent_traversal": "../outside",
    "nested_traversal": "a/../../outside",
    "backslash_traversal": "..\\outside",
    "windows_drive_backslash": "C:\\outside",
    "windows_drive_slash": "C:/outside",
    "windows_drive_relative": "C:outside",
    "unc_share": "\\\\server\\share",
    "unc_share_slash": "//server/share",
    "nul_byte": "docs\x00/ARCH.md",
}


def load_fixture(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


def make_payload(**overrides) -> dict:
    """The canonical B013/B014 authority payload, with targeted overrides for a counterfactual."""
    payload = copy.deepcopy(load_fixture("authority-payload.json"))
    for key, value in overrides.items():
        payload[key] = value
    return payload


def freeze(payload: dict, *, source: str = "operator-terminal", at: str = "2026-09-17T09:00:00Z") -> dict:
    digest = story.root_authority_digest(payload)
    literal = story.authorization_literal(payload["work_ref"], digest)
    return story.freeze_authority(payload, authorized_literal=literal, authority_source=source, authorized_at=at)


class Git:
    """Just enough git for the lineage assertions, always against one temporary repository."""

    def __init__(self, root: Path):
        self.root = root

    def __call__(self, *args: str, check: bool = True) -> str:
        record = subprocess.run(["git", *args], cwd=str(self.root), capture_output=True, text=True, check=False)
        if check and record.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {record.stderr.strip()}")
        return record.stdout.strip()

    def commit_all(self, message: str) -> str:
        self("add", "-A")
        self("commit", "-q", "-m", message)
        return self.head()

    def head(self) -> str:
        return self("rev-parse", "HEAD")

    def tree(self, ref: str = "HEAD") -> str:
        return self("rev-parse", f"{ref}^{{tree}}")

    def dirty(self) -> str:
        return self("status", "--porcelain=v1", "--untracked-files=all")


class StoryCase(unittest.TestCase):
    """Base case with a temporary repository carrying the fixture's Story content."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tl-auto-story-")
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.git = Git(self.root)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test Runner")
        self.git("config", "user.email", "test@thinglab.dev")
        self.git("config", "commit.gpgsign", "false")
        # The mutable ledger is runtime state, never tree content: the durable runtime excludes it
        # through .git/info/exclude, and the replay must start from the same ground truth.
        exclude = self.root / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("/_tl-orc/runtime/\n/.tl-runtime/\n", encoding="utf-8")
        self.write("src/connector.py", CONNECTOR_V1)
        self.write("tests/test_connector.py", CONNECTOR_TESTS_V1)
        self.write("docs/ARCH.md", load_fixture("docs-arch.md"))
        self.write("_tl-orc/project/tasks/connector-2-10.md", load_fixture("spec.md"))
        self.governance_base = self.git.commit_all("story baseline")

    def write(self, relative: str, content: str) -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    # ---- authority helpers ----------------------------------------------------------

    def frozen_authority(self, **overrides) -> dict:
        envelope = freeze(make_payload(**overrides))
        story.publish_authority(self.root, envelope)
        return envelope

    def baseline_authority(self, **overrides) -> dict:
        """Freeze the envelope and fold it into the Story baseline: it is governance content, not
        part of the diff the final Checker reviews."""
        envelope = self.frozen_authority(**overrides)
        self.governance_base = self.git.commit_all(
            f"freeze story authority {envelope['authority_payload']['authority_id']}")
        return envelope

    def authority(self, envelope: dict | None = None, *, acquire: bool = True) -> story.StoryAuthority:
        envelope = envelope or self.frozen_authority()
        authority = story.StoryAuthority(
            envelope, self.root / story.RUNTIME_AUTHORITY_DIR / envelope["authority_payload"]["authority_id"],
            repo=self.root)
        if acquire:
            authority.acquire()
            self.addCleanup(authority.release)
        return authority

    def open_child(self, authority: story.StoryAuthority, child_batch_id: str) -> dict:
        """derived -> open, the only way a child reaches a terminal state (R11)."""
        return authority.record_child_open(child_batch_id, branch="main", head_commit=self.git.head(),
                                           tree=self.git.tree())

    def patch_item(self, item_id: str = "R5", location: str = "src/connector.py:118", **overrides) -> dict:
        item = {
            "id": item_id, "severity": "medium", "category": "patch", "target_role": "maker",
            "location": location, "problem": "residual defect", "evidence": "gate output",
            "required_action": "apply the surgical patch",
        }
        item.update(overrides)
        return item


CONNECTOR_V1 = '''"""Connector with bounded retry (B013 implementation)."""

CEILING_SECONDS = 4.0


def backoff(attempt: int) -> float:
    return min(CEILING_SECONDS, 0.4 * (2 ** attempt))


def call(transport, attempts: int, sleep):
    last = None
    for attempt in range(attempts):
        try:
            return transport()
        except TransientError as exc:
            last = exc
            sleep(backoff(attempt))
    raise last


class TransientError(Exception):
    pass
'''

CONNECTOR_V2 = '''"""Connector with bounded retry (B014 patch for R5)."""

CEILING_SECONDS = 4.0


def backoff(attempt: int) -> float:
    return min(CEILING_SECONDS, 0.4 * (2 ** attempt))


def call(transport, attempts: int, sleep):
    last = None
    for attempt in range(attempts):
        try:
            return transport()
        except TransientError as exc:
            last = exc
            if attempt + 1 < attempts:
                sleep(backoff(attempt))
    raise last


class TransientError(Exception):
    pass
'''

CONNECTOR_TESTS_V1 = '''import unittest

from src.connector import TransientError, backoff, call


class ConnectorTest(unittest.TestCase):
    def test_retries_until_success(self):
        calls = []

        def transport():
            calls.append(1)
            if len(calls) < 2:
                raise TransientError("boom")
            return "ok"

        self.assertEqual(call(transport, 3, lambda _s: None), "ok")
'''

CONNECTOR_TESTS_V2 = CONNECTOR_TESTS_V1 + '''

class CeilingTest(unittest.TestCase):
    def test_backoff_is_bounded_by_the_ceiling(self):
        self.assertLessEqual(max(backoff(n) for n in range(12)), 4.0)
'''
