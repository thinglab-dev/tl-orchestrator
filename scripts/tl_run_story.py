#!/usr/bin/env python3
"""Small CLI for the serialized merge stage of a supervised story."""

from __future__ import annotations

import argparse
import json
import os
import re
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
    target_repository: str | None = None,
    expected_repo: str | None = None,
):
    """Ask GitHub CLI to merge only the current pending FIFO head if MergeAuthorityGate confirms authority."""

    active_repo_root = Path(repo_root) if repo_root is not None else Path(".")
    expected_repo_param = target_repository or expected_repo
    active_store = authority_store
    if active_store is None and DurableExternalAuthorityStore is not None:
        try:
            active_store = DurableExternalAuthorityStore()
        except Exception:
            active_store = None

    def run(item):
        pr_number = int(item.get("pr_number", 0))
        raw_repo = (
            expected_repo_param
            if expected_repo_param is not None
            else (item.get("target_repository") if "target_repository" in item else item.get("expected_repo"))
        )

        expected_repo = str(raw_repo).strip() if raw_repo is not None else ""
        if not expected_repo or not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", expected_repo):
            reason = f"missing_or_invalid_target_repository: '{raw_repo}'"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # Precondition: validate item authority_mode and commit bindings before any evaluation or reservation
        item_mode = item.get("authority_mode")
        item_checker = item.get("checker_approved_commit")
        item_candidate = item.get("integration_candidate_commit")
        if item_mode == "delegated_single_merge":
            if (
                not isinstance(item_checker, str)
                or not re.match(r"^[0-9a-f]{40}$", item_checker)
                or not isinstance(item_candidate, str)
                or not re.match(r"^[0-9a-f]{40}$", item_candidate)
            ):
                reason = "missing_or_invalid_queue_commit_bindings: delegated_single_merge item missing valid 40-hex checker_approved_commit or integration_candidate_commit"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )

        # 1. Resolve AuthorityReceipt
        receipt = None
        live_pr = None
        gate_reserved = False
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
                                    "--repo",
                                    expected_repo,
                                    "--json",
                                    "state,headRefOid,baseRefOid,baseRefName,comments",
                                ],
                                cwd=active_repo_root,
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
        elif MergeAuthorityGate is not None:
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
                            "--repo",
                            expected_repo,
                            "--json",
                            "state,headRefOid,baseRefOid,baseRefName,comments",
                        ],
                        cwd=active_repo_root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if proc_view.returncode == 0 and proc_view.stdout.strip():
                        live_pr = json.loads(proc_view.stdout)
                if live_pr is not None:
                    comments = live_pr.get("comments", [])
                    receipt = MergeAuthorityGate.evaluate(
                        repo_root=active_repo_root,
                        pr_number=pr_number,
                        live_pr_info=live_pr,
                        checker_commit=item_checker,
                        candidate_commit=item_candidate,
                        authority_store=active_store,
                        expected_repo=expected_repo,
                        comments=comments,
                        enforce_mode="delegated_single_merge",
                        trust_root=trust_root,
                        gh_executable=gh_executable,
                    )
                    if receipt is not None and receipt.is_confirmed:
                        gate_reserved = True
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
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                fallback_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 2. Scope & Target PR Binding (Prevents Cross-PR Reuse)
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
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # Strict Target Repository Binding (Prevents Cross-Repository/Fork Reuse)
        receipt_repo = getattr(receipt, "target_repository", "") or (receipt.envelope.get("target_repository") if isinstance(receipt.envelope, dict) else "")
        if receipt_repo != expected_repo:
            reason = f"cross_repository_authority_reuse_rejected: receipt target_repository='{receipt_repo}' does not match queued item target_repository='{expected_repo}'"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 3. Basic Envelope & Credential Presence (Prevents Fabricated Receipts)
        if (
            not receipt.authorization_id
            or not receipt.candidate_commit
            or not receipt.checker_commit
            or not isinstance(receipt.envelope, dict)
            or not receipt.envelope
        ):
            reason = "fabricated_authority_receipt_rejected: receipt lacks authentic cryptographic envelope, valid platform signature, matching verification token, or target repository binding"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 4. Strict Queued Item Commit Binding (Prevents divergence / fallback)
        item_checker = item.get("checker_approved_commit")
        item_candidate = item.get("integration_candidate_commit")
        if item.get("authority_mode") == "delegated_single_merge":
            if not item_checker or receipt.checker_commit != item_checker:
                reason = f"checker_commit_mismatch: receipt checker_commit='{receipt.checker_commit}' does not match queued item checker_approved_commit='{item_checker}'"
                rejected_receipt = AuthorityReceipt(
                    status="REJECTED",
                    authorization_id=receipt.authorization_id,
                    target_pr=pr_number,
                    head_sha=receipt.head_sha,
                    base_sha=receipt.base_sha,
                    checker_commit=receipt.checker_commit,
                    candidate_commit=receipt.candidate_commit,
                    target_repository=expected_repo,
                    reason=reason,
                )
                return (
                    rejected_receipt,
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
            if not item_candidate or receipt.candidate_commit != item_candidate:
                reason = f"candidate_commit_mismatch: receipt candidate_commit='{receipt.candidate_commit}' does not match queued item integration_candidate_commit='{item_candidate}'"
                rejected_receipt = AuthorityReceipt(
                    status="REJECTED",
                    authorization_id=receipt.authorization_id,
                    target_pr=pr_number,
                    head_sha=receipt.head_sha,
                    base_sha=receipt.base_sha,
                    checker_commit=receipt.checker_commit,
                    candidate_commit=receipt.candidate_commit,
                    target_repository=expected_repo,
                    reason=reason,
                )
                return (
                    rejected_receipt,
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )

        # Strict Authority Mode Binding: automated queue execution REQUIRES delegated_single_merge (AC13)
        # Prevents any automated merge execution when authority_mode is missing, empty, human_merge_only, or not delegated_single_merge
        item_mode = item.get("authority_mode")
        envelope_mode = receipt.envelope.get("authority_mode") if isinstance(receipt.envelope, dict) else None
        receipt_mode = getattr(receipt, "authority_mode", None)
        if (
            item_mode != "delegated_single_merge"
            or envelope_mode != "delegated_single_merge"
            or receipt_mode != "delegated_single_merge"
        ):
            is_human = (item_mode == "human_merge_only" or envelope_mode == "human_merge_only" or receipt_mode == "human_merge_only")
            human_prefix = "human_merge_only_mode_blocks_automated_merge: " if is_human else ""
            reason = f"{human_prefix}strict_authority_mode_required: automated merge requires delegated_single_merge (item_mode={item_mode!r}, envelope_mode={envelope_mode!r}, receipt_mode={receipt_mode!r})"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                target_repository=expected_repo,
                authority_mode="human_merge_only" if is_human else str(envelope_mode or item_mode or receipt_mode or "missing"),
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # Cryptographic Verification: verify authentic cryptographic envelope, token, and expected repository
        if not receipt.is_authentic(trust_root, expected_repo=expected_repo):
            reason = "fabricated_authority_receipt_rejected: receipt lacks authentic cryptographic envelope, valid platform signature, matching verification token, or target repository binding"
            rejected_receipt = AuthorityReceipt(
                status="REJECTED",
                authorization_id=receipt.authorization_id,
                target_pr=pr_number,
                head_sha=receipt.head_sha,
                base_sha=receipt.base_sha,
                checker_commit=receipt.checker_commit,
                candidate_commit=receipt.candidate_commit,
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 4. External CAS Anti-Replay Reservation on Queue Path (MANDATORY PRECONDITION)
        store = active_store
        if store is None:
            if DurableExternalAuthorityStore is None:
                reason = "external_authority_store_unavailable: DurableExternalAuthorityStore primitive missing"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
            try:
                store = DurableExternalAuthorityStore()
            except Exception as exc:
                reason = f"external_authority_store_initialization_failed: {exc}"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )

        try:
            curr_state = store.get_state(receipt.authorization_id)
        except Exception as exc:
            reason = f"external_authority_store_read_failed: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

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
                target_repository=expected_repo,
                reason=reason,
            )
            return (
                rejected_receipt,
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # Single atomic possession: if Gate already acquired the reservation in this execution, verify it
        if gate_reserved:
            if curr_state != "reserved":
                reason = f"authorization_reservation_failed_concurrent_or_consumed: Gate reserved {receipt.authorization_id} but current store state is '{curr_state}'"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
        else:
            # If not reserved by the Gate in this execution, reserve it atomically now
            try:
                reserve_ok = store.reserve(receipt.authorization_id)
            except Exception as exc:
                reason = f"external_authority_store_reserve_failed: {exc}"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
            if not reserve_ok:
                reason = f"authorization_reservation_failed_concurrent_or_consumed: could not reserve {receipt.authorization_id}"
                rejected_receipt = AuthorityReceipt(
                    status="REJECTED",
                    authorization_id=receipt.authorization_id,
                    target_pr=pr_number,
                    head_sha=receipt.head_sha,
                    base_sha=receipt.base_sha,
                    checker_commit=receipt.checker_commit,
                    candidate_commit=receipt.candidate_commit,
                    target_repository=expected_repo,
                    reason=reason,
                )
                return (
                    rejected_receipt,
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )

        # 5. Mandatory Fresh Pre-Merge TOCTOU Revalidation (Fails closed and defensively marks INDETERMINATE on ANY failure)
        cmd_view = [
            gh_executable,
            "pr",
            "view",
            str(pr_number),
            "--repo",
            expected_repo,
            "--json",
            "state,headRefOid,baseRefOid,baseRefName,comments",
        ]
        try:
            proc_view = subprocess.run(
                cmd_view,
                cwd=active_repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"toctou_live_view_failed: gh pr view execution failed: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if proc_view.returncode != 0:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"toctou_live_view_failed: gh pr view exited with code {proc_view.returncode}: {proc_view.stderr.strip()}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        try:
            fresh_live_pr = json.loads(proc_view.stdout)
            if not isinstance(fresh_live_pr, dict):
                raise ValueError("Parsed JSON is not an object")
        except Exception as exc:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"toctou_invalid_live_pr_json: failed to parse JSON from gh pr view: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        live_state = str(fresh_live_pr.get("state", "")).upper()
        if live_state != "OPEN":
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"toctou_pr_not_open: live PR #{pr_number} state is {live_state}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        live_head = str(fresh_live_pr.get("headRefOid") or "").strip()
        live_base = str(fresh_live_pr.get("baseRefOid") or "").strip()

        if not live_head or not live_base:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"toctou_missing_live_shas: live PR #{pr_number} missing headRefOid ('{live_head}') or baseRefOid ('{live_base}')"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if receipt.candidate_commit != live_head or receipt.head_sha != live_head:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"merge_queue_toctou_head_drift: receipt candidate_commit={receipt.candidate_commit} does not match fresh live PR headRefOid={live_head}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, head_sha=live_head, base_sha=live_base, candidate_commit=live_head, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if receipt.base_sha != live_base:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"merge_queue_toctou_base_drift: receipt base_sha={receipt.base_sha} does not match fresh live PR baseRefOid={live_base}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, head_sha=live_head, base_sha=live_base, candidate_commit=live_head, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 6. Atomic Platform Merge Execution with --match-head-commit (NO --auto)
        cmd_merge = [
            gh_executable,
            "pr",
            "merge",
            str(item["pr_number"]),
            "--repo",
            expected_repo,
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            receipt.candidate_commit,
        ]
        proc = subprocess.run(
            cmd_merge,
            cwd=active_repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            return (receipt, proc)

        # 7. Terminal PR Verification (Must be confirmed MERGED before consuming authority)
        cmd_terminal = [
            gh_executable,
            "pr",
            "view",
            str(pr_number),
            "--repo",
            expected_repo,
            "--json",
            "state,headRefOid,baseRefOid",
        ]
        try:
            proc_term = subprocess.run(
                cmd_terminal,
                cwd=active_repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc_term.returncode != 0:
                raise ValueError(f"gh pr view terminal check failed with exit code {proc_term.returncode}: {proc_term.stderr.strip()}")
            term_pr = json.loads(proc_term.stdout)
            if not isinstance(term_pr, dict):
                raise ValueError("terminal gh pr view returned non-dict JSON")
        except Exception as exc:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"terminal_view_failed: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        term_state = str(term_pr.get("state", "")).upper()
        if term_state != "MERGED":
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"terminal_state_not_merged: PR #{pr_number} state is '{term_state}' (delayed merge, auto-merge queue, or still open); authority marked indeterminate"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        term_head = str(term_pr.get("headRefOid") or "").strip()
        term_base = str(term_pr.get("baseRefOid") or "").strip()

        if not term_head or not term_base:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"terminal_missing_commit_bindings: missing terminal headRefOid ({term_head or 'empty'}) or baseRefOid ({term_base or 'empty'}) in PR #{pr_number}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if term_head != receipt.candidate_commit:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"terminal_head_drift: merged head {term_head} != authorized candidate {receipt.candidate_commit}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        if term_base != receipt.base_sha:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"terminal_base_drift: merged base {term_base} != authorized base {receipt.base_sha}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
            )

        # 8. Terminal state confirmed MERGED: commit consumed in CAS store
        try:
            committed = store.commit_consumed(receipt.authorization_id)
            if not committed:
                store.mark_indeterminate(receipt.authorization_id)
                reason = "cas_commit_consumed_failed_after_merge: state was not reserved"
                return (
                    AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                    subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
                )
        except Exception as exc:
            try:
                store.mark_indeterminate(receipt.authorization_id)
            except Exception:
                pass
            reason = f"cas_commit_consumed_exception_after_merge: {exc}"
            return (
                AuthorityReceipt(status="REJECTED", target_pr=pr_number, target_repository=expected_repo, reason=reason),
                subprocess.CompletedProcess([gh_executable], 1, "", f"Authority rejected: {reason}"),
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
    enqueue.add_argument("--target-repository", default=None)
    enqueue.add_argument("--authority-mode", default="delegated_single_merge")
    enqueue.add_argument("--checker-approved-commit", default=None)
    enqueue.add_argument("--integration-candidate-commit", default=None)
    advance = commands.add_parser("advance")
    advance.add_argument("--queue-file", required=True, type=Path)
    advance.add_argument("--gh", default="gh")
    advance.add_argument("--retry-failed", action="store_true")
    advance.add_argument("--repo-root", default=Path("."), type=Path)
    advance.add_argument("--store-dir", default=None, type=Path)
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
        result = enqueue_merge(
            arguments.story_id,
            arguments.pr_number,
            arguments.queue_file,
            target_repository=arguments.target_repository,
            authority_mode=arguments.authority_mode,
            checker_approved_commit=arguments.checker_approved_commit,
            integration_candidate_commit=arguments.integration_candidate_commit,
        )
        success = result.get("state") in {"enqueued", "already_queued"}
    else:
        store = None
        if getattr(arguments, "store_dir", None) and DurableExternalAuthorityStore is not None:
            store = DurableExternalAuthorityStore(arguments.store_dir)
        result = merge_queue_head(
            arguments.queue_file,
            arguments.gh,
            arguments.retry_failed,
            repo_root=arguments.repo_root,
            authority_store=store,
        )
        success = result.get("state") in {"merged", "queue_empty"}
    print(json.dumps(result, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
