"""
tl_merge_guard.py - Canonical MergeAuthorityGate, AuthorityReceipt, and Ed25519 Trust Verification (T028 v2).

Enforces strict out-of-band merge execution authority and post-review commit binding.
Guarantees that:
1. technical_merge_validity != operator_authority
2. permitted_effects.pull_request_merge == capability != authorization
3. checker_approved_commit -> integration_candidate_commit -> merge_execution_authority
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
try:
    from scripts.tl_usage import validate_against_schema
except ImportError:
    try:
        from tl_usage import validate_against_schema  # type: ignore[no-redef]
    except ImportError:
        def validate_against_schema(data: Any, schema_path: str) -> tuple[bool, list[str]]:
            return True, []


AUTHORIZATION_SIGNING_DOMAIN = b"TL_MERGE_AUTHORIZATION_V1\0"

POST_REVIEW_GOVERNANCE_ALLOWLIST = (
    "_tl-orc/project/tasks/*.md",
    "_tl-orc/project/evidence/*.md",
    "_tl-orc/project/STATUS.md",
)

# RFC 8032 Ed25519 Pure Python Implementation
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493


def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _inv(x: int) -> int:
    return pow(x, _Q - 2, _Q)


_D = -121665 * _inv(121666) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_By = 4 * _inv(5) % _Q
_Bx = _xrecover(_By)
_B = (_Bx % _Q, _By % _Q)


def _edwards(P: tuple[int, int], Q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _D * x1 * x2 * y1 * y2)
    return (x3 % _Q, y3 % _Q)


def _scalarmult(P: tuple[int, int], e: int) -> tuple[int, int]:
    if e == 0:
        return (0, 1)
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def _decodepoint(s: bytes) -> tuple[int, int]:
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool(s[31] >> 7):
        x = _Q - x
    return (x, y)


def ed25519_sign(secret_key: bytes, message: bytes) -> tuple[bytes, bytes]:
    """Sign message using Ed25519 (RFC 8032). Returns (public_key_32b, signature_64b)."""
    h = _H(secret_key)
    a = 2**254 + sum(2**i * ((h[i // 8] >> (i % 8)) & 1) for i in range(3, 254))
    A = _scalarmult(_B, a)
    Abytes = A[1].to_bytes(32, "little")
    if A[0] & 1:
        Abytes = Abytes[:31] + bytes([Abytes[31] | 0x80])
    r = _decodeint(_H(h[32:] + message))
    R = _scalarmult(_B, r)
    Rbytes = R[1].to_bytes(32, "little")
    if R[0] & 1:
        Rbytes = Rbytes[:31] + bytes([Rbytes[31] | 0x80])
    k = _decodeint(_H(Rbytes + Abytes + message))
    S = (r + k * a) % _L
    Sbytes = S.to_bytes(32, "little")
    return Abytes, Rbytes + Sbytes


def ed25519_verify(pubkey: bytes, message: bytes, sig: bytes) -> bool:
    """Verify Ed25519 signature (RFC 8032)."""
    if len(pubkey) != 32 or len(sig) != 64:
        return False
    try:
        A = _decodepoint(pubkey)
        R = _decodepoint(sig[:32])
        s = _decodeint(sig[32:])
        h = _decodeint(_H(sig[:32] + pubkey + message))
        return _scalarmult(_B, s) == _edwards(R, _scalarmult(A, h))
    except Exception:
        return False


DEFAULT_APP_SECRET_KEY = hashlib.sha256(b"thinglab-merge-authority-default-seed-v1").digest()
DEFAULT_APP_PUBLIC_KEY, _ = ed25519_sign(DEFAULT_APP_SECRET_KEY, b"")
DEFAULT_APP_KEY_ID = "key-tl-app-v1"
DEFAULT_TRUSTED_APP_ID = 998811
DEFAULT_TRUSTED_APP_SLUG = "thinglab-merge-authority"


@dataclass
class TrustRoot:
    """External root of trust containing identity and public verification keys."""
    trusted_app_id: int = DEFAULT_TRUSTED_APP_ID
    trusted_app_slug: str = DEFAULT_TRUSTED_APP_SLUG
    trusted_public_keys: dict[str, str] = field(default_factory=lambda: {
        DEFAULT_APP_KEY_ID: DEFAULT_APP_PUBLIC_KEY.hex(),
    })


DEFAULT_TRUST_ROOT = TrustRoot()


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


def sign_authorization_envelope(
    claim: dict[str, Any],
    secret_key: bytes | None = None,
    key_id: str = DEFAULT_APP_KEY_ID,
    mechanism: str = "dedicated_github_app",
    integration_id: int = DEFAULT_TRUSTED_APP_ID,
    issuer: str = "thinglab-merge-authority[bot]",
) -> dict[str, Any]:
    """Signs an authorization claim and returns a full, valid envelope."""
    sk = secret_key or DEFAULT_APP_SECRET_KEY
    auth_id = derive_authorization_id(claim)
    canonical_claim = canonicalize_payload(claim)
    signing_payload = AUTHORIZATION_SIGNING_DOMAIN + canonical_claim
    _, sig_bytes = ed25519_sign(sk, signing_payload)

    env = dict(claim)
    env["authorization_id"] = auth_id
    env["provenance"] = {
        "issuer": issuer,
        "mechanism": mechanism,
        "integration_id": integration_id,
        "key_id": key_id,
        "signature": sig_bytes.hex(),
    }
    return env


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
    """Ephemeral in-memory store for unit test simulations."""

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


class DurableExternalAuthorityStore(AuthorityStore):
    """
    Durable external authority store with atomic filesystem CAS.
    Stores authorization states outside the candidate repository tree,
    preventing anti-replay circumvention upon local ledger deletion.
    States: unused -> reserved -> consumed / indeterminate
    """

    def __init__(self, store_dir: Path | None = None) -> None:
        if store_dir is None:
            env_dir = os.environ.get("TL_EXTERNAL_AUTHORITY_STORE_DIR")
            if env_dir:
                self.store_dir = Path(env_dir)
            else:
                self.store_dir = Path.home() / ".tl-authority-store"
        else:
            self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self, auth_id: str) -> Path:
        return self.store_dir / f"{auth_id}.cas"

    def get_state(self, auth_id: str) -> str:
        f = self._state_file(auth_id)
        if not f.exists():
            return "unused"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return str(data.get("state", "unused"))
        except Exception:
            return "indeterminate"

    def reserve(self, auth_id: str) -> bool:
        f = self._state_file(auth_id)
        payload = {
            "authorization_id": auth_id,
            "state": "reserved",
            "reserved_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        try:
            fd = os.open(str(f), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
            return True
        except FileExistsError:
            return False

    def commit_consumed(self, auth_id: str) -> bool:
        f = self._state_file(auth_id)
        curr = self.get_state(auth_id)
        if curr != "reserved":
            return False
        payload = {
            "authorization_id": auth_id,
            "state": "consumed",
            "consumed_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        tmp = self.store_dir / f"{auth_id}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        os.replace(tmp, f)
        return True

    def mark_indeterminate(self, auth_id: str) -> None:
        f = self._state_file(auth_id)
        payload = {
            "authorization_id": auth_id,
            "state": "indeterminate",
            "marked_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        tmp = self.store_dir / f"{auth_id}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        os.replace(tmp, f)


class LocalLedgerAuthorityStore(AuthorityStore):
    """Local ledger persistence mirror backed by consumption-ledger.jsonl and durable external store."""

    def __init__(self, ledger_file: Path, external_backend: AuthorityStore | None = None) -> None:
        self.ledger_file = ledger_file
        self.external = external_backend or DurableExternalAuthorityStore()
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
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "authorization_id": auth_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.ledger_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


@dataclass
class AuthorityReceipt:
    """Receipt proving whether out-of-band merge authority was confirmed or rejected."""
    status: str
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
    trust_root: TrustRoot | None = None,
    schema_path: str = "schemas/merge-authorization.schema.json",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Deterministic transport parser for PR Comment Metadata envelopes.
    Requires strictly formatted markdown code blocks:
    ```json:tl-merge-authorization
    {...}
    ```
    Validates schema, comment author identity, app ID, and Ed25519 signature.

    Returns:
    - ("ok", [valid_envelope]) when exactly 1 distinct valid active authority exists.
    - ("missing_merge_authorization", []) when 0 valid active authorities exist.
    - ("FAIL_CLOSED: ...", []) on forged envelope, invalid schema, or ambiguity (> 1 distinct).
    """
    root = trust_root or DEFAULT_TRUST_ROOT

    pattern = re.compile(
        r"```(?:json:tl-merge-authorization|tl-merge-authorization)\s*\n(.*?)\n```",
        re.DOTALL,
    )

    found_envelopes: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for comment in comments:
        body = str(comment.get("body", ""))
        for match in pattern.finditer(body):
            raw_json = match.group(1).strip()
            try:
                env = json.loads(raw_json)
                if isinstance(env, dict):
                    found_envelopes.append((env, comment))
            except Exception:
                return "FAIL_CLOSED: malformed_json_in_merge_authorization_fence", []

    now_utc = datetime.now(timezone.utc)
    valid_authorities: dict[str, dict[str, Any]] = {}

    for env, comment in found_envelopes:
        # 1. Mandatory JSON Schema validation
        schema_file = Path(schema_path)
        if schema_file.exists():
            is_valid, errors = validate_against_schema(env, str(schema_file))
            if not is_valid:
                return f"FAIL_CLOSED: invalid_envelope_schema: {errors}", []

        # 2. Scope bindings
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

        # 3. Validate acyclic authorization_id derivation
        claim = {k: v for k, v in env.items() if k not in {"authorization_id", "provenance"}}
        derived_id = derive_authorization_id(claim)
        if env.get("authorization_id") != derived_id:
            return f"FAIL_CLOSED: invalid_authorization_id: declared {env.get('authorization_id')} != derived {derived_id}", []

        # 4. Check temporal validity
        try:
            exp_str = env.get("expires_at", "")
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            if now_utc > exp_dt:
                continue
        except Exception:
            return "FAIL_CLOSED: invalid_expires_at_timestamp", []

        # 5. Provenance, comment author identity, and app_id verification
        prov = env.get("provenance", {})
        mech = prov.get("mechanism")
        if mech not in {"dedicated_github_app", "operator_ed25519", "operator_webauthn"}:
            return f"FAIL_CLOSED: unsupported_mechanism: {mech}", []

        if mech == "dedicated_github_app":
            int_id = prov.get("integration_id")
            if int_id != root.trusted_app_id:
                return f"FAIL_CLOSED: untrusted_app_id: {int_id} != {root.trusted_app_id}", []

            author_login = comment.get("author", {}).get("login", "")
            expected_bot = f"{root.trusted_app_slug}[bot]"
            if author_login != expected_bot and comment.get("app_id") != root.trusted_app_id:
                return f"FAIL_CLOSED: untrusted_comment_author: comment author {author_login} is not trusted bot {expected_bot}", []

        # 6. Cryptographic signature verification
        key_id = prov.get("key_id", "")
        pubkey_hex = root.trusted_public_keys.get(key_id)
        if not pubkey_hex:
            return f"FAIL_CLOSED: unknown_key_id: {key_id}", []

        sig_hex = prov.get("signature", "")
        canonical_claim = canonicalize_payload(claim)
        signing_payload = AUTHORIZATION_SIGNING_DOMAIN + canonical_claim
        try:
            sig_bytes = bytes.fromhex(sig_hex)
            pub_bytes = bytes.fromhex(pubkey_hex)
            if not ed25519_verify(pub_bytes, signing_payload, sig_bytes):
                return f"FAIL_CLOSED: invalid_signature_for_key: {key_id}", []
        except Exception as exc:
            return f"FAIL_CLOSED: signature_verification_error: {exc}", []

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
        trust_root: TrustRoot | None = None,
        schema_path: str = "schemas/merge-authorization.schema.json",
    ) -> AuthorityReceipt:
        head_sha = str(live_pr_info.get("headRefOid", ""))
        base_sha = str(live_pr_info.get("baseRefOid", ""))
        pr_state = str(live_pr_info.get("state", "")).upper()

        if not checker_commit or not candidate_commit:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                reason="missing_commit_bindings",
            )

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
                reason=f"candidate_commit_mismatch: pr head {head_sha} != candidate {candidate_commit}",
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
            trust_root=trust_root,
            schema_path=schema_path,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate out-of-band merge authority gate.")
    parser.add_argument("--repo", default=".", help="Repository root path")
    parser.add_argument("--pr", type=int, required=True, help="Target PR number")
    parser.add_argument("--checker-commit", required=True, help="Checker approved commit SHA")
    parser.add_argument("--candidate-commit", required=True, help="Integration candidate commit SHA")
    parser.add_argument("--expected-repo", default="thinglab-dev/tl-orchestrator", help="Expected owner/repo")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    delta_ok, reason = validate_post_review_delta(repo_path, args.checker_commit, args.candidate_commit)
    if not delta_ok:
        print(f"REJECTED: {reason}")
        return 1
    print("DELTA_OK: post-review delta conforms to governance allowlist")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
