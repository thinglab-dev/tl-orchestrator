#!/usr/bin/env python3
"""Small CLI for the serialized merge stage of a supervised story."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

try:
    from tl_supervisor import (
        acquire_worktree_slot,
        advance_merge_queue,
        claim_scope,
        enqueue_merge,
        release_scope,
        release_worktree_slot,
    )
except ImportError:
    from scripts.tl_supervisor import (
        acquire_worktree_slot,
        advance_merge_queue,
        claim_scope,
        enqueue_merge,
        release_scope,
        release_worktree_slot,
    )

try:
    from tl_merge_guard import AuthorityReceipt
except ImportError:
    try:
        from scripts.tl_merge_guard import AuthorityReceipt
    except ImportError:
        AuthorityReceipt = None



def dispatch_story(pool_dir, story_id, paths, claims_file, max_slots):
    """Claim scope before opening a worktree; roll back if no slot is granted."""
    claim = claim_scope(story_id, paths, claims_file)
    if claim.get("state") != "claimed":
        return claim
    slot = acquire_worktree_slot(pool_dir, story_id, max_slots)
    if slot.get("state") != "acquired":
        release = release_scope(story_id, claims_file)
        if release.get("state") != "released":
            return {"state": "rollback_failed", "slot": slot, "scope_release": release}
    return slot


def release_story(pool_dir, story_id, claims_file):
    """Close the worktree before making its paths eligible for another writer."""
    slot = release_worktree_slot(pool_dir, story_id)
    if slot.get("state") not in {"released", "not_found"}:
        return slot
    scope = release_scope(story_id, claims_file)
    if scope.get("state") not in {"released", "not_found"}:
        return scope
    return {"state": "released", "story_id": story_id}


def merge_queue_head(
    queue_file,
    gh_executable="gh",
    retry_failed: bool = False,
    authority_receipt: AuthorityReceipt | None = None,
    authority_validator=None,
):
    """Ask GitHub CLI to merge only the current pending FIFO head if MergeAuthorityGate confirms authority."""

    def run(item):
        receipt = None
        if authority_validator is not None:
            receipt = authority_validator(item)
        elif authority_receipt is not None:
            receipt = authority_receipt
        elif "receipt" in item and isinstance(item["receipt"], AuthorityReceipt):
            receipt = item["receipt"]

        if receipt is None or not isinstance(receipt, AuthorityReceipt) or not receipt.is_confirmed:
            reason = getattr(receipt, "reason", "missing_authority_receipt")
            fallback_receipt = receipt if isinstance(receipt, AuthorityReceipt) else AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=int(item.get("pr_number", 0)),
                head_sha="",
                base_sha="",
                checker_commit="",
                candidate_commit="",
                reason=reason,
            )
            return (
                fallback_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        proc = subprocess.run(
            [
                gh_executable,
                "pr",
                "merge",
                str(item["pr_number"]),
                "--auto",
                "--squash",
                "--delete-branch",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return (receipt, proc)

    return advance_merge_queue(queue_file, run, retry_failed=retry_failed)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--story-id", required=True)
    dispatch.add_argument("--path", action="append", dest="paths", required=True)
    dispatch.add_argument("--pool-dir", required=True, type=Path)
    dispatch.add_argument("--claims-file", required=True, type=Path)
    dispatch.add_argument("--max-slots", required=True, type=int)
    release = commands.add_parser("release")
    release.add_argument("--story-id", required=True)
    release.add_argument("--pool-dir", required=True, type=Path)
    release.add_argument("--claims-file", required=True, type=Path)
    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--story-id", required=True)
    enqueue.add_argument("--pr-number", required=True, type=int)
    enqueue.add_argument("--queue-file", required=True, type=Path)
    advance = commands.add_parser("advance")
    advance.add_argument("--queue-file", required=True, type=Path)
    advance.add_argument("--gh", default="gh")
    advance.add_argument("--retry-failed", action="store_true")
    return value


def main(argv=None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "dispatch":
        result = dispatch_story(
            arguments.pool_dir,
            arguments.story_id,
            arguments.paths,
            arguments.claims_file,
            arguments.max_slots,
        )
        success = result.get("state") == "acquired"
    elif arguments.command == "release":
        result = release_story(arguments.pool_dir, arguments.story_id, arguments.claims_file)
        success = result.get("state") == "released"
    elif arguments.command == "enqueue":
        result = enqueue_merge(arguments.story_id, arguments.pr_number, arguments.queue_file)
        success = result.get("state") in {"enqueued", "already_queued"}
    else:
        result = merge_queue_head(arguments.queue_file, arguments.gh, arguments.retry_failed)
        success = result.get("state") in {"merged", "queue_empty"}
    print(json.dumps(result, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
