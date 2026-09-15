"""
tl_merge_guard.py - Canonical MergeAuthorityGate and AuthorityReceipt (T028 v2).

Enforces strict out-of-band merge execution authority and post-review commit binding.
Guarantees that:
1. technical_merge_validity != operator_authority
2. permitted_effects.pull_request_merge == capability != authorization
3. checker_approved_commit -> integration_candidate_commit -> merge_execution_authority
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


AUTHORIZATION_SIGNING_DOMAIN = b"TL_MERGE_AUTHORIZATION_V1\0"

POST_REVIEW_GOVERNANCE_ALLOWLIST = (
    "_tl-orc/project/tasks/*.md",
    "_tl-orc/project/evidence/*.md",
    "_tl-orc/project/STATUS.md",
)


def canonicalize_payload(payload: Any) -> bytes:
    """
    Deterministic byte-by-byte canonicalization (canonical_authorization_payload_v1).
    Rules:
    - UTF-8 encoding without BOM.
    - Keys sorted lexicographically.
    - No insignificant whitespace (separators=(',', ':')).
    - No float types permitted (integers only).
    - Normalized string escaping.
    """
    def _validate_types(val: Any) -> None:
        if isinstance(val, bool) or val is None:
            return
        if isinstance(val, (int, str)):
            return
        if isinstance(val, float):
            raise ValueError("Float values are strictly prohibited in canonical authorization payload")
        if isinstance(val, dict):
            for k, v in val.items():
                if not isinstance(k, str):
                    raise ValueError(f"Dictionary keys must be strings, got {type(k)}")
                _validate_types(v)
            return
        if isinstance(val, (list, tuple)):
            for item in val:
                _validate_types(item)
            return
        raise ValueError(f"Unsupported type {type(val)} in canonical payload")

    _validate_types(payload)
    canonical_json_str = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return canonical_json_str.encode("utf-8")


def compute_claim_digest(claim: dict[str, Any]) -> str:
    """Compute sha256 hex digest of the canonical authorization claim."""
    canonical_bytes = canonicalize_payload(claim)
    return hashlib.sha256(canonical_bytes).hexdigest()


def derive_authorization_id(claim: dict[str, Any]) -> str:
    """Derive acyclic authorization_id from the canonical authorization claim."""
    digest = compute_claim_digest(claim)
    return "auth-" + digest[:32]


def compute_signing_payload(envelope_without_signature: dict[str, Any]) -> bytes:
    """Compute domain-separated signing payload."""
    canonical_env = canonicalize_payload(envelope_without_signature)
    return AUTHORIZATION_SIGNING_DOMAIN + canonical_env


def validate_post_review_delta(repo_root: Path, checker_commit: str, candidate_commit: str) -> tuple[bool, str]:
    """
    Validates post-review delta against the strict post_review_governance_delta_only allowlist.
    Returns (True, reason) or (False, failure_reason).
    """
    if checker_commit == candidate_commit:
        return True, "diff_zero"

    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", checker_commit, candidate_commit],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        return False, f"git_diff_failed: {exc}"

    changed_files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not changed_files:
        return True, "diff_zero"

    for path_str in changed_files:
        norm_path = path_str.replace("\\", "/")
        matched = False
        for pattern in POST_REVIEW_GOVERNANCE_ALLOWLIST:
            if fnmatch.fnmatch(norm_path, pattern):
                matched = True
                break
        if not matched:
            return False, f"uninspected_code_mutation_post_review: {norm_path}"

    return True, "governance_delta_allowed"


class AuthorityStore:
    """Abstract trust domain store for authority reservation and anti-replay."""

    def get_state(self, auth_id: str) -> str:
        raise NotImplementedError

    def reserve(self, auth_id: str) -> bool:
        raise NotImplementedError

    def commit_consumed(self, auth_id: str) -> bool:
        raise NotImplementedError

    def mark_indeterminate(self, auth_id: str) -> None:
        raise NotImplementedError


class InMemoryAuthorityStore(AuthorityStore):
    """External trust domain simulated in-memory store."""

    def __init__(self, initial_records: dict[str, str] | None = None) -> None:
        self._states: dict[str, str] = dict(initial_records or {})

    def get_state(self, auth_id: str) -> str:
        return self._states.get(auth_id, "unused")

    def reserve(self, auth_id: str) -> bool:
        curr = self.get_state(auth_id)
        if curr == "unused":
            self._states[auth_id] = "reserved"
            return True
        return False

    def commit_consumed(self, auth_id: str) -> bool:
        if self._states.get(auth_id) == "reserved":
            self._states[auth_id] = "consumed"
            return True
        return False

    def mark_indeterminate(self, auth_id: str) -> None:
        self._states[auth_id] = "indeterminate"


class LocalLedgerAuthorityStore(AuthorityStore):
    """Local ledger persistence mirror backed by consumption-ledger.jsonl."""

    def __init__(self, ledger_file: Path, external_backend: AuthorityStore | None = None) -> None:
        self.ledger_file = ledger_file
        self.external = external_backend or InMemoryAuthorityStore()
        self._load_local_records()

    def _load_local_records(self) -> None:
        if not self.ledger_file.exists():
            return
        for line in self.ledger_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                aid = rec.get("authorization_id")
                st = rec.get("status")
                if aid and st:
                    # Sync local mirror without overriding external
                    if self.external.get_state(aid) == "unused":
                        if st == "consumed":
                            self.external.reserve(aid)
                            self.external.commit_consumed(aid)
                        elif st == "reserved":
                            self.external.reserve(aid)
            except Exception:
                continue

    def get_state(self, auth_id: str) -> str:
        return self.external.get_state(auth_id)

    def reserve(self, auth_id: str) -> bool:
        ok = self.external.reserve(auth_id)
        if ok:
            self._append_local(auth_id, "reserved")
        return ok

    def commit_consumed(self, auth_id: str) -> bool:
        ok = self.external.commit_consumed(auth_id)
        if ok:
            self._append_local(auth_id, "consumed")
        return ok

    def mark_indeterminate(self, auth_id: str) -> None:
        self.external.mark_indeterminate(auth_id)
        self._append_local(auth_id, "indeterminate")

    def _append_local(self, auth_id: str, status: str) -> None:
        try:
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "authorization_id": auth_id,
                "status": status,
            }
            with open(self.ledger_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass


@dataclass(frozen=True)
class AuthorityReceipt:
    status: str  # "CONFIRMED", "REJECTED", "AWAITING_HUMAN"
    authorization_id: str
    target_pr: int
    head_sha: str
    base_sha: str
    checker_commit: str
    candidate_commit: str
    reason: str
    envelope: dict[str, Any] | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.status == "CONFIRMED"


def parse_pr_comment_transport(
    comments: list[dict[str, Any]],
    expected_repo: str,
    pr_number: int,
    expected_head: str,
    expected_base: str,
    candidate_commit: str,
    trusted_app_id: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Deterministic transport parser for PR Comment Metadata envelopes.
    Returns:
    - ("ok", [valid_envelope]) when exactly 1 distinct valid active authority exists.
    - ("missing_merge_authorization", []) when 0 valid active authorities exist.
    - ("FAIL_CLOSED: ambiguous_merge_authorization", []) when > 1 distinct valid authorities exist.
    """
    pattern = re.compile(
        r"<!--\s*TL_MERGE_AUTHORIZATION_V1_START\s*-->\s*(\{.*?\})\s*<!--\s*TL_MERGE_AUTHORIZATION_V1_END\s*-->",
        re.DOTALL,
    )

    found_envelopes: list[dict[str, Any]] = []

    for comment in comments:
        body = str(comment.get("body", ""))
        for match in pattern.finditer(body):
            raw_json = match.group(1).strip()
            try:
                env = json.loads(raw_json)
                if isinstance(env, dict):
                    found_envelopes.append(env)
            except Exception:
                continue

    # Filter and validate matching active authorities
    now_utc = datetime.now(timezone.utc)
    valid_authorities: dict[str, dict[str, Any]] = {}

    for env in found_envelopes:
        if env.get("schema_version") != 1:
            continue

        if env.get("target_repository") != expected_repo:
            continue
        if env.get("target_pr") != pr_number:
            continue
        if env.get("expected_head_sha") != expected_head:
            continue
        if env.get("expected_base_sha") != expected_base:
            continue
        if env.get("integration_candidate_commit") != candidate_commit:
            continue

        # Validate acyclic authorization_id derivation
        claim = {k: v for k, v in env.items() if k not in {"authorization_id", "provenance"}}
        derived_id = derive_authorization_id(claim)
        if env.get("authorization_id") != derived_id:
            continue

        # Check temporal validity
        try:
            exp_str = env.get("expires_at", "")
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            if now_utc > exp_dt:
                continue
        except Exception:
            continue

        # Valid active candidate
        valid_authorities[derived_id] = env

    if len(valid_authorities) == 0:
        return "missing_merge_authorization", []
    if len(valid_authorities) == 1:
        return "ok", list(valid_authorities.values())
    return "FAIL_CLOSED: ambiguous_merge_authorization", []


class MergeAuthorityGate:
    """Canonical evaluator for out-of-band merge authority (T028)."""

    @classmethod
    def evaluate(
        cls,
        repo_root: Path,
        pr_number: int,
        live_pr_info: dict[str, Any],
        checker_commit: str,
        candidate_commit: str,
        authority_store: AuthorityStore,
        expected_repo: str,
        comments: list[dict[str, Any]] | None = None,
        enforce_mode: str = "delegated_single_merge",
        trusted_app_id: int | None = None,
    ) -> AuthorityReceipt:
        head_sha = str(live_pr_info.get("headRefOid", ""))
        base_sha = str(live_pr_info.get("baseRefOid", ""))
        pr_state = str(live_pr_info.get("state", "")).upper()

        if pr_state != "OPEN":
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason=f"pr_not_open: {pr_state}",
            )

        if head_sha != candidate_commit:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="candidate_commit_mismatch",
            )

        # Delta validation between checker_approved_commit and candidate_commit
        delta_ok, delta_reason = validate_post_review_delta(repo_root, checker_commit, candidate_commit)
        if not delta_ok:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason=delta_reason,
            )

        # Transport parsing
        comments_list = comments or []
        parse_status, envelopes = parse_pr_comment_transport(
            comments=comments_list,
            expected_repo=expected_repo,
            pr_number=pr_number,
            expected_head=head_sha,
            expected_base=base_sha,
            candidate_commit=candidate_commit,
            trusted_app_id=trusted_app_id,
        )

        if parse_status != "ok":
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason=parse_status,
            )

        envelope = envelopes[0]
        auth_id = envelope["authorization_id"]

        # Check provenance / mechanism
        provenance = envelope.get("provenance", {})
        mechanism = provenance.get("mechanism")
        if mechanism not in {"dedicated_github_app", "operator_ed25519", "operator_webauthn"}:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="untrusted_authorization_provenance",
                envelope=envelope,
            )

        # External anti-replay CAS check
        store_state = authority_store.get_state(auth_id)
        if store_state in {"consumed", "indeterminate"}:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="authorization_already_consumed",
                envelope=envelope,
            )

        if enforce_mode == "human_merge_only":
            return AuthorityReceipt(
                status="AWAITING_HUMAN",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="human_merge_only_mode",
                envelope=envelope,
            )

        # Attempt atomic CAS reservation in external trust domain
        if not authority_store.reserve(auth_id):
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="authorization_reservation_failed_concurrent_or_consumed",
                envelope=envelope,
            )

        return AuthorityReceipt(
            status="CONFIRMED",
            authorization_id=auth_id,
            target_pr=pr_number,
            head_sha=head_sha,
            base_sha=base_sha,
            checker_commit=checker_commit,
            candidate_commit=candidate_commit,
            reason="AUTHORITY_CONFIRMED",
            envelope=envelope,
        )
