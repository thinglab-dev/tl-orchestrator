#!/usr/bin/env python3
"""Small CLI for the serialized merge stage of a supervised story."""

from __future__ import annotations

import argparse
import json
import os
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
    from tl_merge_guard import (
        AuthorityReceipt,
        AuthorityStore,
        DurableExternalAuthorityStore,
        MergeAuthorityGate,
        TrustRoot,
    )
except ImportError:
    try:
        from scripts.tl_merge_guard import (
            AuthorityReceipt,
            AuthorityStore,
            DurableExternalAuthorityStore,
            MergeAuthorityGate,
            TrustRoot,
        )
    except ImportError:
        AuthorityReceipt = None
        AuthorityStore = None
        DurableExternalAuthorityStore = None
        MergeAuthorityGate = None
        TrustRoot = None



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
    live_pr_getter=None,
    repo_root: Path | str | None = None,
    trust_root: TrustRoot | None = None,
    authority_store: AuthorityStore | None = None,
):
    """Ask GitHub CLI to merge only the current pending FIFO head if MergeAuthorityGate confirms authority."""

    def run(item):
        pr_number = int(item.get("pr_number", 0))

        # 1. Resolve AuthorityReceipt
        receipt = None
        live_pr = None
        if authority_validator is not None:
            try:
                import inspect
                sig = inspect.signature(authority_validator)
                if len(sig.parameters) >= 2:
                    if callable(live_pr_getter):
                        live_pr = live_pr_getter(pr_number)
                    else:
                        try:
                            proc_init = subprocess.run(
                                [
                                    gh_executable,
                                    "pr",
                                    "view",
                                    str(pr_number),
                                    "--json",
                                    "state,headRefOid,baseRefOid,baseRefName,comments",
                                ],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if proc_init.returncode == 0 and proc_init.stdout.strip():
                                live_pr = json.loads(proc_init.stdout)
                        except Exception:
                            live_pr = None
                    receipt = authority_validator(item, live_pr)
                else:
                    receipt = authority_validator(item)
            except Exception:
                receipt = authority_validator(item)
        elif authority_receipt is not None:
            receipt = authority_receipt
        elif "receipt" in item and isinstance(item["receipt"], AuthorityReceipt):
            receipt = item["receipt"]
        elif repo_root is not None and MergeAuthorityGate is not None:
            # Canonical authority evaluation on queue path
            try:
                if callable(live_pr_getter):
                    live_pr = live_pr_getter(pr_number)
                else:
                    proc_view = subprocess.run(
                        [
                            gh_executable,
                            "pr",
                            "view",
                            str(pr_number),
                            "--json",
                            "state,headRefOid,baseRefOid,baseRefName,comments",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if proc_view.returncode == 0 and proc_view.stdout.strip():
                        live_pr = json.loads(proc_view.stdout)
                if live_pr is not None:
                    expected_repo = item.get("expected_repo")
                    if not expected_repo:
                        expected_repo = os.environ.get("TL_TARGET_REPOSITORY", "thinglab-dev/tl-orchestrator")
                    comments = live_pr.get("comments", [])
                    head_commit = str(live_pr.get("headRefOid", ""))
                    receipt = MergeAuthorityGate.evaluate(
                        repo_root=Path(repo_root),
                        pr_number=pr_number,
                        live_pr_info=live_pr,
                        checker_commit=item.get("checker_commit", head_commit),
                        candidate_commit=item.get("candidate_commit", head_commit),
                        authority_store=authority_store,
                        expected_repo=expected_repo,
                        comments=comments,
                        enforce_mode="delegated_single_merge",
                        trust_root=trust_root,
                        gh_executable=gh_executable,
                    )
            except Exception:
                receipt = None

        # 2. Check receipt existence and confirmation
        if receipt is None or not isinstance(receipt, AuthorityReceipt) or not receipt.is_confirmed:
            reason = getattr(receipt, "reason", "missing_authority_receipt")
            fallback_receipt = receipt if isinstance(receipt, AuthorityReceipt) else AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
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

        # 3. Fabricated Receipt Defense: verify authentic cryptographic envelope and receipt token
        if not receipt.is_authentic(trust_root):
            reason = "fabricated_authority_receipt_rejected: receipt lacks authentic cryptographic envelope, valid platform signature, or matching verification token"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 4. Strict Scope & Target PR Binding (Prevents Cross-PR Reuse)
        if int(receipt.target_pr) != pr_number:
            reason = f"cross_pr_authority_reuse_rejected: receipt target_pr={receipt.target_pr} does not match queued item pr_number={pr_number}"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 5. External CAS Anti-Replay Reservation on Queue Path
        store = authority_store
        if store is None and DurableExternalAuthorityStore is not None:
            try:
                store = DurableExternalAuthorityStore()
            except Exception:
                store = None

        if store is not None:
            curr_state = store.get_state(receipt.authorization_id)
            if curr_state in {"consumed", "indeterminate"}:
                reason = f"authorization_already_consumed: authority {receipt.authorization_id} has state '{curr_state}'"
                rejected_receipt = AuthorityReceipt(
                    status="REJECTED",
                    authorization_id=receipt.authorization_id,
                    target_pr=pr_number,
                    head_sha=receipt.head_sha,
                    base_sha=receipt.base_sha,
                    checker_commit=receipt.checker_commit,
                    candidate_commit=receipt.candidate_commit,
                    reason=reason,
                )
                return (
                    rejected_receipt,
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
            if not store.reserve(receipt.authorization_id):
                reason = f"authorization_reservation_failed_concurrent_or_consumed: could not reserve {receipt.authorization_id}"
                rejected_receipt = AuthorityReceipt(
                    status="REJECTED",
                    authorization_id=receipt.authorization_id,
                    target_pr=pr_number,
                    head_sha=receipt.head_sha,
                    base_sha=receipt.base_sha,
                    checker_commit=receipt.checker_commit,
                    candidate_commit=receipt.candidate_commit,
                    reason=reason,
                )
                return (
                    rejected_receipt,
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )

        # 6. Mandatory Fresh Pre-Merge TOCTOU Revalidation (Fails closed on any error)
        cmd_view = [
            gh_executable,
            "pr",
            "view",
            str(pr_number),
            "--json",
            "state,headRefOid,baseRefOid,baseRefName,comments",
        ]
        try:
            proc_view = subprocess.run(
                cmd_view,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            reason = f"toctou_live_view_failed: gh pr view execution failed: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if proc_view.returncode != 0:
            reason = f"toctou_live_view_failed: gh pr view exited with code {proc_view.returncode}: {proc_view.stderr.strip()}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        try:
            fresh_live_pr = json.loads(proc_view.stdout)
            if not isinstance(fresh_live_pr, dict):
                raise ValueError("Parsed JSON is not an object")
        except Exception as exc:
            reason = f"toctou_invalid_live_pr_json: failed to parse JSON from gh pr view: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        live_state = str(fresh_live_pr.get("state", "")).upper()
        if live_state != "OPEN":
            reason = f"toctou_pr_not_open: live PR #{pr_number} state is {live_state}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        live_head = str(fresh_live_pr.get("headRefOid") or "").strip()
        live_base = str(fresh_live_pr.get("baseRefOid") or "").strip()

        if not live_head or not live_base:
            reason = f"toctou_missing_live_shas: live PR #{pr_number} missing headRefOid ('{live_head}') or baseRefOid ('{live_base}')"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if receipt.candidate_commit != live_head or receipt.head_sha != live_head:
            reason = f"merge_queue_toctou_head_drift: receipt candidate_commit={receipt.candidate_commit} does not match fresh live PR headRefOid={live_head}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, head_sha=live_head, base_sha=live_base, candidate_commit=live_head, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if receipt.base_sha != live_base:
            reason = f"merge_queue_toctou_base_drift: receipt base_sha={receipt.base_sha} does not match fresh live PR baseRefOid={live_base}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, head_sha=live_head, base_sha=live_base, candidate_commit=live_head, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 7. Atomic CAS Reservation on Platform with --match-head-commit
        cmd_merge = [
            gh_executable,
            "pr",
            "merge",
            str(item["pr_number"]),
            "--auto",
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            receipt.candidate_commit,
        ]
        proc = subprocess.run(
            cmd_merge,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and store is not None:
            store.commit_consumed(receipt.authorization_id)
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
