#!/usr/bin/env python3
"""Concurrent story coordination primitives for tl-orchestrator.

This module coordinates local filesystem state only.  It does not choose a
story, approve a change, or decide whether a merge is allowed by policy.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import posixpath
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

try:
    from tl_job import lock_exclusive, unlock_exclusive
except ImportError:  # Imported as scripts.tl_supervisor from the repository root.
    from scripts.tl_job import lock_exclusive, unlock_exclusive

try:
    from tl_merge_guard import AuthorityReceipt
except ImportError:
    try:
        from scripts.tl_merge_guard import AuthorityReceipt
    except ImportError:
        AuthorityReceipt = None


LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.01
MERGE_FINALIZE_LOCK_GRACE_SECONDS = 30.0
BOARD_ENTRY_PATTERN = re.compile(r"^[ \t]*([^\W_][\w.-]*)[ \t]*:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


class _FileLock:
    """Blocking wrapper around tl_job's portable, non-blocking file lock."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self.path = path
        self.timeout = timeout
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout
        while not lock_exclusive(self.handle):
            if time.monotonic() >= deadline:
                self.handle.close()
                self.handle = None
                raise TimeoutError(f"could not acquire exclusive lock: {self.path}")
            time.sleep(LOCK_RETRY_SECONDS)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.handle is not None:
            unlock_exclusive(self.handle)
            self.handle.close()
            self.handle = None


@contextlib.contextmanager
def _file_lock_with_retry(path: Path, grace_seconds: float):
    """Acquire a file lock repeatedly until the overall grace period expires."""
    deadline = time.monotonic() + grace_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"could not acquire exclusive lock: {path}")
        lock = _FileLock(path, timeout=min(LOCK_TIMEOUT_SECONDS, remaining))
        try:
            lock.__enter__()
            break
        except TimeoutError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(LOCK_RETRY_SECONDS, remaining))
    try:
        yield lock
    finally:
        lock.__exit__(None, None, None)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def _atomic_write_json(path: Path, value: object) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _valid_story_id(story_id: object) -> bool:
    if not isinstance(story_id, str) or not story_id or len(story_id) > 128:
        return False
    if story_id in {".", ".."}:
        return False
    match = BOARD_ENTRY_PATTERN.fullmatch(f"{story_id}: value")
    return match is not None and match.group(1) == story_id


def _run_git(arguments: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )


def _slot_files(pool_dir: Path) -> list[Path]:
    return sorted(pool_dir.glob("*/slot.json"))


def acquire_worktree_slot(pool_dir, story_id, max_slots):
    """Atomically reserve one pool slot and create its Git worktree."""
    pool = Path(pool_dir)
    if (
        not _valid_story_id(story_id)
        or not isinstance(max_slots, int)
        or isinstance(max_slots, bool)
        or max_slots < 1
    ):
        return {"state": "invalid_input"}
    try:
        with _FileLock(pool / ".pool.lock"):
            slots = _slot_files(pool)
            if len(slots) >= max_slots:
                return {"state": "pool_exhausted"}
            worktree = pool / story_id
            slot_file = worktree / "slot.json"
            if worktree.exists() or slot_file.exists():
                return {"state": "slot_conflict"}
            result = _run_git(["worktree", "add", str(worktree)])
            if result.returncode != 0:
                return {
                    "state": "worktree_create_failed",
                    "detail": (result.stderr or result.stdout).strip(),
                }
            now = time.time()
            record = {
                "story_id": story_id,
                "worktree": str(worktree),
                "lease": {
                    "pid": os.getpid(),
                    "start_time": now,
                    "heartbeat_ts": now,
                },
            }
            try:
                _atomic_write_json(slot_file, record)
            except OSError:
                _run_git(["worktree", "remove", "--force", str(worktree)])
                raise
            return {"state": "acquired", **record}
    except (OSError, TimeoutError):
        return {"state": "unavailable"}


def release_worktree_slot(pool_dir, story_id):
    """Remove one story worktree and release its slot."""
    pool = Path(pool_dir)
    if not _valid_story_id(story_id):
        return {"state": "invalid_input"}
    try:
        with _FileLock(pool / ".pool.lock"):
            worktree = pool / story_id
            slot_file = worktree / "slot.json"
            if not slot_file.exists():
                return {"state": "not_found"}
            record = _read_json(slot_file, None)
            if not isinstance(record, dict) or record.get("story_id") != story_id:
                return {"state": "invalid_slot"}
            result = _run_git(["worktree", "remove", "--force", str(worktree)])
            if result.returncode != 0 and (worktree / ".git").exists():
                return {
                    "state": "remove_failed",
                    "detail": (result.stderr or result.stdout).strip(),
                }
            if slot_file.exists():
                slot_file.unlink()
            with contextlib.suppress(OSError):
                worktree.rmdir()
            return {"state": "released", "story_id": story_id}
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return {"state": "unavailable"}


def _canonical_scope_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("scope paths must be non-empty strings")
    candidate = value.replace("\\", "/")
    if candidate.startswith("/") or (len(candidate) >= 2 and candidate[1] == ":"):
        raise ValueError("scope paths must be repository-relative")
    normalized = posixpath.normpath(candidate)
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        raise ValueError("scope paths must stay inside the repository")
    return normalized.rstrip("/")


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _read_claims(path: Path) -> dict[str, list[str]]:
    value = _read_json(path, {"claims": {}})
    if not isinstance(value, dict) or set(value) != {"claims"}:
        raise ValueError("invalid claims file")
    claims = value["claims"]
    if not isinstance(claims, dict):
        raise ValueError("invalid claims map")
    normalized: dict[str, list[str]] = {}
    for story_id, paths in claims.items():
        if not _valid_story_id(story_id) or not isinstance(paths, list) or not paths:
            raise ValueError("invalid persisted claim")
        normalized[story_id] = [_canonical_scope_path(item) for item in paths]
    return normalized


def claim_scope(story_id, paths, claims_file):
    """Claim non-overlapping repository paths, failing closed on malformed state."""
    target = Path(claims_file)
    if not _valid_story_id(story_id) or isinstance(paths, (str, bytes)):
        return {"state": "invalid_input"}
    try:
        requested = sorted(set(_canonical_scope_path(item) for item in paths))
        if not requested:
            return {"state": "invalid_input"}
        with _FileLock(target.with_name(target.name + ".lock")):
            claims = _read_claims(target)
            existing_for_story = claims.get(story_id)
            if existing_for_story is not None:
                if existing_for_story == requested:
                    return {"state": "claimed", "story_id": story_id, "paths": requested}
                return {"state": "scope_conflict", "conflicting_with": story_id}
            for owner, owned_paths in claims.items():
                if any(_paths_overlap(wanted, owned) for wanted in requested for owned in owned_paths):
                    return {"state": "scope_conflict", "conflicting_with": owner}
            claims[story_id] = requested
            _atomic_write_json(target, {"claims": claims})
            return {"state": "claimed", "story_id": story_id, "paths": requested}
    except (OSError, TypeError, ValueError, json.JSONDecodeError, TimeoutError):
        return {"state": "unavailable"}


def release_scope(story_id, claims_file):
    """Release one story's persisted scope claim."""
    target = Path(claims_file)
    if not _valid_story_id(story_id):
        return {"state": "invalid_input"}
    try:
        with _FileLock(target.with_name(target.name + ".lock")):
            claims = _read_claims(target)
            if story_id not in claims:
                return {"state": "not_found"}
            del claims[story_id]
            _atomic_write_json(target, {"claims": claims})
            return {"state": "released", "story_id": story_id}
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return {"state": "unavailable"}


def _read_queue(path: Path) -> list[dict]:
    value = _read_json(path, {"items": []})
    if not isinstance(value, dict) or set(value) != {"items"} or not isinstance(value["items"], list):
        raise ValueError("invalid merge queue")
    items = value["items"]
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid merge queue item")
        mode = item.get("authority_mode")
        if mode == "delegated_single_merge":
            required = {
                "story_id",
                "pr_number",
                "state",
                "enqueued_at",
                "target_repository",
                "authority_mode",
                "checker_approved_commit",
                "integration_candidate_commit",
            }
        elif mode == "human_merge_only":
            required = {
                "story_id",
                "pr_number",
                "state",
                "enqueued_at",
                "target_repository",
                "authority_mode",
            }
        else:
            raise ValueError("invalid merge queue item: invalid or missing authority_mode")

        allowed_keys = {
            "story_id",
            "pr_number",
            "state",
            "enqueued_at",
            "detail",
            "in_flight_token",
            "started_at",
            "target_repository",
            "authority_mode",
            "checker_approved_commit",
            "integration_candidate_commit",
        }
        checker_sha = item.get("checker_approved_commit")
        candidate_sha = item.get("integration_candidate_commit")
        if (
            not isinstance(item, dict)
            or not required.issubset(item)
            or set(item) - allowed_keys
            or not _valid_story_id(item.get("story_id"))
            or not isinstance(item.get("pr_number"), int)
            or isinstance(item.get("pr_number"), bool)
            or item.get("state") not in {"pending", "merging", "merged", "failed"}
            or not isinstance(item.get("enqueued_at"), (int, float))
            or isinstance(item.get("enqueued_at"), bool)
            or ("detail" in item and not isinstance(item["detail"], str))
            or not isinstance(item.get("target_repository"), str)
            or not item.get("target_repository")
            or not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", item["target_repository"])
            or item.get("authority_mode") not in {"delegated_single_merge", "human_merge_only"}
            or (
                item.get("authority_mode") == "delegated_single_merge"
                and (
                    not isinstance(checker_sha, str)
                    or not re.match(r"^[0-9a-f]{40}$", checker_sha)
                    or not isinstance(candidate_sha, str)
                    or not re.match(r"^[0-9a-f]{40}$", candidate_sha)
                )
            )
            or (
                item.get("authority_mode") == "human_merge_only"
                and (
                    (checker_sha is not None and (not isinstance(checker_sha, str) or not re.match(r"^[0-9a-f]{40}$", checker_sha)))
                    or (candidate_sha is not None and (not isinstance(candidate_sha, str) or not re.match(r"^[0-9a-f]{40}$", candidate_sha)))
                )
            )
            or (
                "started_at" in item
                and (
                    item["state"] != "merging"
                    or not isinstance(item["started_at"], (int, float))
                    or isinstance(item["started_at"], bool)
                    or not math.isfinite(item["started_at"])
                )
            )
            or (
                "in_flight_token" in item
                and (item["state"] != "merging" or not isinstance(item["in_flight_token"], str) or not item["in_flight_token"])
            )
        ):
            raise ValueError("invalid merge queue item")
    return items


def enqueue_merge(
    story_id: str,
    pr_number: int,
    target: Path,
    target_repository: str | None = None,
    authority_mode: str = "delegated_single_merge",
    checker_approved_commit: str | None = None,
    integration_candidate_commit: str | None = None,
) -> dict:
    """Safely append a merge request to the queue under the lock."""
    target = Path(target)
    if (
        not _valid_story_id(story_id)
        or not isinstance(pr_number, int)
        or isinstance(pr_number, bool)
        or pr_number < 1
    ):
        return {"state": "invalid_input"}
    if (
        not isinstance(target_repository, str)
        or not target_repository
        or not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", target_repository)
    ):
        return {"state": "invalid_input"}
    if authority_mode not in {"delegated_single_merge", "human_merge_only"}:
        return {"state": "invalid_input"}
    if authority_mode == "delegated_single_merge":
        if (
            not isinstance(checker_approved_commit, str)
            or not re.match(r"^[0-9a-f]{40}$", checker_approved_commit)
            or not isinstance(integration_candidate_commit, str)
            or not re.match(r"^[0-9a-f]{40}$", integration_candidate_commit)
        ):
            return {"state": "invalid_input"}
    elif authority_mode == "human_merge_only":
        if checker_approved_commit is not None and (
            not isinstance(checker_approved_commit, str)
            or not re.match(r"^[0-9a-f]{40}$", checker_approved_commit)
        ):
            return {"state": "invalid_input"}
        if integration_candidate_commit is not None and (
            not isinstance(integration_candidate_commit, str)
            or not re.match(r"^[0-9a-f]{40}$", integration_candidate_commit)
        ):
            return {"state": "invalid_input"}

    resolved_repo = target_repository
    try:
        with _FileLock(target.with_name(target.name + ".lock")):
            items = _read_queue(target)
            if any(item["story_id"] == story_id or item["pr_number"] == pr_number for item in items):
                return {"state": "already_queued"}
            item = {
                "story_id": story_id,
                "pr_number": pr_number,
                "target_repository": resolved_repo,
                "authority_mode": authority_mode,
                "state": "pending",
                "enqueued_at": time.time(),
            }
            if checker_approved_commit is not None:
                item["checker_approved_commit"] = checker_approved_commit
            if integration_candidate_commit is not None:
                item["integration_candidate_commit"] = integration_candidate_commit
            items.append(item)
            _atomic_write_json(target, {"items": items})
            return {"state": "enqueued", "position": len(items) - 1, "item": item}
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return {"state": "unavailable"}


def _merge_succeeded(result: object, dispatch_item: dict | None = None) -> tuple[bool, str]:
    """Inspect merge runner outcome and enforce valid AuthorityReceipt presentation (Rule B)."""
    receipt = None
    outcome = None
    if AuthorityReceipt is not None and isinstance(result, AuthorityReceipt):
        receipt = result
        outcome = True
    elif isinstance(result, tuple) and len(result) == 2:
        receipt, outcome = (
            (result[0], result[1])
            if AuthorityReceipt is not None and isinstance(result[0], AuthorityReceipt)
            else (result[1], result[0])
            if AuthorityReceipt is not None and isinstance(result[1], AuthorityReceipt)
            else (None, None)
        )
    elif isinstance(result, dict) and "receipt" in result:
        receipt = result["receipt"] if (AuthorityReceipt is not None and isinstance(result["receipt"], AuthorityReceipt)) else None
        outcome = result.get("merged", True)

    if receipt is None or not isinstance(receipt, AuthorityReceipt):
        raise ValueError("merge runner must present a valid AuthorityReceipt; uninspected merge callbacks are rejected (Rule B)")

    if not receipt.is_confirmed:
        return False, f"authority_not_confirmed: {receipt.reason}"

    # Scope binding validation against dispatch_item
    if dispatch_item is not None:
        expected_repo = dispatch_item.get("target_repository")
        if expected_repo and getattr(receipt, "target_repository", None) != expected_repo:
            return False, f"cross_repository_receipt_mismatch: receipt target_repository={getattr(receipt, 'target_repository', None)} != item target_repository={expected_repo}"
        expected_pr = int(dispatch_item.get("pr_number", 0))
        if expected_pr and int(receipt.target_pr) != expected_pr:
            return False, f"cross_pr_receipt_mismatch: receipt target_pr={receipt.target_pr} != item pr_number={expected_pr}"
        expected_checker = dispatch_item.get("checker_approved_commit")
        if expected_checker and receipt.checker_commit != expected_checker:
            return False, f"checker_commit_mismatch: receipt checker_commit={receipt.checker_commit} != item checker_approved_commit={expected_checker}"
        expected_candidate = dispatch_item.get("integration_candidate_commit")
        if expected_candidate and receipt.candidate_commit != expected_candidate:
            return False, f"candidate_commit_mismatch: receipt candidate_commit={receipt.candidate_commit} != item integration_candidate_commit={expected_candidate}"
        if "base_sha" in dispatch_item and dispatch_item["base_sha"] != receipt.base_sha:
            return False, f"base_sha_mismatch: receipt base_sha={receipt.base_sha} != item base_sha={dispatch_item['base_sha']}"

    expected_repo = dispatch_item.get("target_repository") if dispatch_item else None
    if not receipt.is_authentic(expected_repo=expected_repo):
        return False, f"unverified_or_fabricated_receipt: {receipt.reason}"

    if isinstance(outcome, bool):
        return outcome, receipt.reason if outcome else f"merge_failed: {receipt.reason}"
    if isinstance(outcome, int):
        return outcome == 0, f"exit code {outcome}"
    returncode = getattr(outcome, "returncode", None)
    if isinstance(returncode, int):
        detail = getattr(outcome, "stderr", "") or getattr(outcome, "stdout", "") or ""
        return returncode == 0, str(detail).strip()
    if isinstance(outcome, str) and outcome in {"merged", "failed"}:
        return outcome == "merged", ""
    raise ValueError(f"unsupported outcome type in merge result tuple: {type(outcome)}")



def advance_merge_queue(
    queue_file,
    merge_runner: Callable[[dict], object],
    retry_failed: bool = False,
    stale_merge_seconds: float = 120.0,
):
    """Run at most the FIFO head and persist its terminal state while serialized."""
    target = Path(queue_file)
    queue_lock = target.with_name(target.name + ".lock")
    dispatch_lock = target.with_name(target.name + ".dispatch.lock")
    if (
        not callable(merge_runner)
        or not isinstance(retry_failed, bool)
        or not isinstance(stale_merge_seconds, (int, float))
        or isinstance(stale_merge_seconds, bool)
        or not math.isfinite(stale_merge_seconds)
        or stale_merge_seconds <= 0
    ):
        return {"state": "invalid_input"}
    try:
        # Serialize merge dispatches independently from short queue mutations so
        # enqueue_merge never waits for a network-bound merge runner.
        with _FileLock(dispatch_lock):
            with _FileLock(queue_lock):
                items = _read_queue(target)
                head_index = next(
                    (index for index, item in enumerate(items) if item["state"] != "merged"),
                    None,
                )
                if head_index is None:
                    return {"state": "queue_empty"}
                head = items[head_index]
                if head["state"] == "failed":
                    if not retry_failed:
                        return {"state": "queue_blocked", "item": dict(head)}
                    head["state"] = "pending"
                    head.pop("detail", None)
                if head["state"] == "merging":
                    started_at = head.get("started_at", 0)
                    if not retry_failed and time.time() - started_at <= stale_merge_seconds:
                        return {"state": "merge_in_progress", "item": dict(head)}
                    head["state"] = "pending"
                    head.pop("in_flight_token", None)
                    head.pop("started_at", None)
                    head.pop("detail", None)
                if head["state"] != "pending":
                    return {"state": "merge_in_progress", "item": dict(head)}
                dispatch_item = dict(head)
                in_flight_token = uuid.uuid4().hex
                head["state"] = "merging"
                head["in_flight_token"] = in_flight_token
                head["started_at"] = time.time()
                _atomic_write_json(target, {"items": items})

            try:
                succeeded, detail = _merge_succeeded(merge_runner(dispatch_item), dispatch_item)
            except Exception as exc:
                succeeded, detail = False, f"{type(exc).__name__}: {exc}"

            with _file_lock_with_retry(queue_lock, MERGE_FINALIZE_LOCK_GRACE_SECONDS):
                items = _read_queue(target)
                if head_index >= len(items):
                    return {"state": "unavailable"}
                head = items[head_index]
                if (
                    head["story_id"] != dispatch_item["story_id"]
                    or head["pr_number"] != dispatch_item["pr_number"]
                    or head["state"] != "merging"
                    or head.get("in_flight_token") != in_flight_token
                ):
                    return {"state": "unavailable"}
                head["state"] = "merged" if succeeded else "failed"
                head.pop("in_flight_token", None)
                head.pop("started_at", None)
                if detail:
                    head["detail"] = detail
                else:
                    head.pop("detail", None)
                _atomic_write_json(target, {"items": items})
                return {"state": head["state"], "item": dict(head)}
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return {"state": "unavailable"}


def _heartbeat(record: dict) -> float:
    lease = record.get("lease")
    value = lease.get("heartbeat_ts") if isinstance(lease, dict) else record.get("heartbeat_ts")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("invalid heartbeat")
    return float(value)


def sweep_orphan_worktrees(pool_dir, stale_after_seconds):
    """Remove metadata/worktrees whose heartbeat is strictly older than the threshold."""
    pool = Path(pool_dir)
    if (
        not isinstance(stale_after_seconds, (int, float))
        or isinstance(stale_after_seconds, bool)
        or stale_after_seconds <= 0
    ):
        return {"state": "invalid_input"}
    removed: list[str] = []
    refused: list[str] = []
    try:
        with _FileLock(pool / ".pool.lock"):
            now = time.time()
            for slot_file in _slot_files(pool):
                try:
                    record = _read_json(slot_file, None)
                    if not isinstance(record, dict) or not _valid_story_id(record.get("story_id")):
                        raise ValueError("invalid slot")
                    if now - _heartbeat(record) <= float(stale_after_seconds):
                        continue
                    story_id = record["story_id"]
                    worktree = slot_file.parent
                    result = _run_git(["worktree", "remove", "--force", str(worktree)])
                    if result.returncode != 0 and (worktree / ".git").exists():
                        refused.append(story_id)
                        continue
                    if slot_file.exists():
                        slot_file.unlink()
                    with contextlib.suppress(OSError):
                        worktree.rmdir()
                    removed.append(story_id)
                except (OSError, ValueError, json.JSONDecodeError):
                    refused.append(slot_file.parent.name)
            return {"state": "swept", "removed": removed, "refused": refused}
    except (OSError, TimeoutError):
        return {"state": "unavailable", "removed": removed, "refused": refused}


def update_task_status_atomic(status_file, task_id, new_status, expected_revision):
    """CAS-update one STATUS.md task row and increment its state_revision."""
    target = Path(status_file)
    if (
        not _valid_story_id(task_id)
        or not isinstance(new_status, str)
        or not new_status.strip()
        or new_status.strip() != new_status
        or any(character.isspace() for character in new_status)
        or "|" in new_status
        or not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        return {"state": "invalid_input"}
    try:
        with _FileLock(target.with_name(target.name + ".lock")):
            original = target.read_text(encoding="utf-8")
            lines = original.splitlines(keepends=True)
            matches: list[tuple[int, list[str], str]] = []
            for index, line in enumerate(lines):
                ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                body = line[:-len(ending)] if ending else line
                if not body.lstrip().startswith("|"):
                    continue
                cells = [cell.strip() for cell in body.strip().strip("|").split("|")]
                if cells and cells[0] == task_id:
                    matches.append((index, cells, ending))
            if len(matches) != 1:
                return {"state": "task_not_found" if not matches else "invalid_board"}
            index, cells, ending = matches[0]
            if len(cells) != 8:
                return {"state": "invalid_board"}
            try:
                current_revision = int(cells[6])
            except ValueError:
                return {"state": "invalid_board"}
            if current_revision != expected_revision:
                return {
                    "state": "state_revision_conflict",
                    "current_revision": current_revision,
                }
            cells[3] = new_status.strip()
            cells[6] = str(current_revision + 1)
            lines[index] = "| " + " | ".join(cells) + " |" + ending
            if target.read_text(encoding="utf-8") != original:
                return {"state": "state_revision_conflict"}
            _atomic_write_text(target, "".join(lines))
            return {
                "state": "updated",
                "task_id": task_id,
                "status": cells[3],
                "state_revision": current_revision + 1,
            }
    except (OSError, UnicodeError, TimeoutError):
        return {"state": "unavailable"}
