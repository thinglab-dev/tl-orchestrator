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
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import uuid

# Canonicalize sys.modules so 'scripts.tl_merge_guard' and 'tl_merge_guard' share single module state
_self_mod = sys.modules.get(__name__)
if _self_mod is not None:
    if __name__ == "scripts.tl_merge_guard":
        sys.modules.setdefault("tl_merge_guard", _self_mod)
    elif __name__ == "tl_merge_guard":
        sys.modules.setdefault("scripts.tl_merge_guard", _self_mod)

try:
    from scripts.tl_usage import validate_against_schema
except ImportError:
    try:
        from tl_usage import validate_against_schema  # type: ignore[no-redef]
    except ImportError:
        def validate_against_schema(data: Any, schema_path: str) -> tuple[bool, list[str]]:
            return False, ["FAIL_CLOSED: schema validator unavailable: tl_usage.validate_against_schema could not be imported"]


def _resolve_schema_path(schema_path: str | Path | None = None) -> Path:
    """Resolve merge authorization schema path, falling back to canonical package schema."""
    if schema_path is not None:
        p = Path(schema_path)
        if p.is_file():
            return p
        return p
    return Path(__file__).resolve().parent.parent / "schemas" / "merge-authorization.schema.json"


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


ISO_UTC_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


def validate_canonical_utc_timestamp(ts: Any, field_name: str = "timestamp") -> datetime:
    """
    Strictly validate that a timestamp is in canonical UTC ISO 8601 format.
    Must match ISO_UTC_REGEX and be a valid datetime ending in Z or +00:00 with zero UTC offset.
    """
    if not isinstance(ts, str):
        raise ValueError(f"{field_name} must be a string, got {type(ts).__name__}")
    if not ISO_UTC_REGEX.match(ts):
        raise ValueError(
            f"{field_name} must be a canonical UTC ISO 8601 timestamp ending in 'Z' or '+00:00' (e.g. 'YYYY-MM-DDTHH:MM:SSZ'), got {ts!r}"
        )
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"Invalid {field_name} datetime value {ts!r}: {exc}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(f"{field_name} must have a strict UTC offset of +00:00 or Z, got {dt.utcoffset()}")
    return dt


def canonicalize_payload(payload: Any) -> bytes:
    """
    Deterministic byte-by-byte canonicalization (canonical_authorization_payload_v1).
    Rules:
    - UTF-8 encoding without BOM.
    - Keys sorted lexicographically.
    - No insignificant whitespace (separators=(',', ':')).
    - No float types permitted (integers only).
    - Normalized string escaping.
    - Strict canonical UTC ISO 8601 validation for issued_at and expires_at.
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
    if isinstance(payload, dict):
        issued_dt = None
        expires_dt = None
        if "issued_at" in payload:
            issued_dt = validate_canonical_utc_timestamp(payload["issued_at"], "issued_at")
        if "expires_at" in payload:
            expires_dt = validate_canonical_utc_timestamp(payload["expires_at"], "expires_at")
        if issued_dt is not None and expires_dt is not None:
            if issued_dt > expires_dt:
                raise ValueError(
                    f"issued_at ({payload['issued_at']}) cannot be later than expires_at ({payload['expires_at']})"
                )

    canonical_json_str = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return canonical_json_str.encode("utf-8")


IMMUTABLE_PLATFORM_AUTHORITY_APP_ID: int = 998811
IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG: str = "thinglab-merge-authority"
# Production immutable platform authority anchors (private key is NEVER stored in repository)
IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS: dict[str, str] = {
    "key-tl-app-v1": "9d901616c6ba67e9fcf156fece357ceea9e3f6ad85731338a0815beedee723a1",
}

_active_platform_root_keys: dict[str, str] = dict(IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS)


def get_platform_root_public_keys() -> dict[str, str]:
    """Return active platform root public keys (strictly IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS in production)."""
    if _active_platform_root_keys != IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS:
        return dict(_active_platform_root_keys)
    return dict(IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS)



@contextlib.contextmanager
def temporary_platform_anchor_for_testing(test_public_keys: dict[str, str]):
    """
    Test-only context manager to register temporary in-memory fixture keys.
    Mechanically isolated to authorized test harnesses. Strictly forbidden from
    production runtime entry points or modules.
    """
    import inspect
    stack = inspect.stack()
    for frame_info in stack:
        filename = os.path.abspath(frame_info.filename)
        base = os.path.basename(filename)
        if base in ("tl_runtime.py", "tl_run_story.py", "tl_supervisor.py"):
            raise PermissionError(
                f"temporary_platform_anchor_for_testing is strictly forbidden from runtime execution: found {base} in call stack"
            )
    is_test_harness = any(
        ("test" in os.path.basename(f.filename) or "unittest" in f.filename or "_test" in f.filename)
        for f in stack
    )
    if not is_test_harness:
        raise PermissionError(
            "temporary_platform_anchor_for_testing is strictly forbidden outside an authorized test harness"
        )
    global _active_platform_root_keys
    old = _active_platform_root_keys
    _active_platform_root_keys = dict(test_public_keys)
    try:
        yield
    finally:
        _active_platform_root_keys = old


def compute_receipt_token(
    authorization_id: str,
    target_pr: int,
    candidate_commit: str,
    checker_commit: str,
    head_sha: str,
    base_sha: str,
    envelope_signature: str,
    target_repository: str = "",
    authority_mode: str = "delegated_single_merge",
) -> str:
    """Compute deterministic cryptographic receipt token binding authorization, repo, commits, and authority mode."""
    msg = f"{authorization_id}:{target_repository}:{target_pr}:{candidate_commit}:{checker_commit}:{head_sha}:{base_sha}:{envelope_signature}:{authority_mode}".encode("utf-8")
    return "rcpt-" + hashlib.sha256(b"TL_AUTHORITY_RECEIPT_V1\0" + msg).hexdigest()


@dataclass
class PlatformCapability:
    """
    Unforgeable cryptographic capability token proving a TrustRoot was established
    by an authenticated out-of-process authority.
    Signed strictly by the immutable platform authority root key over deterministic canonical metadata.
    """
    capability_id: str
    app_id: int
    app_slug: str
    keys_fingerprint: str
    issued_at: str
    expires_at: str
    signature: str

    def is_valid(self, app_id: int, app_slug: str, public_keys: dict[str, str]) -> bool:
        # 1. Enforce immutable platform authority identity
        if int(self.app_id) != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID or int(app_id) != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
            return False
        if str(self.app_slug) != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG or str(app_slug) != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
            return False
        if not public_keys:
            return False

        # 2. Reject any public keys not anchored in the platform root keys
        platform_roots = get_platform_root_public_keys()
        for kid, khex in public_keys.items():
            expected_hex = platform_roots.get(kid)
            if not expected_hex or expected_hex != khex:
                return False

        # 3. Keys fingerprint check
        fp = hashlib.sha256(json.dumps(sorted(public_keys.items()), separators=(",", ":")).encode("utf-8")).hexdigest()
        if self.keys_fingerprint != fp:
            return False

        # 4. UTC timestamps check
        try:
            exp = validate_canonical_utc_timestamp(self.expires_at, "expires_at")
            if datetime.now(timezone.utc) > exp:
                return False
            validate_canonical_utc_timestamp(self.issued_at, "issued_at")
        except Exception:
            return False

        payload = canonicalize_payload({
            "capability_id": self.capability_id,
            "app_id": self.app_id,
            "app_slug": self.app_slug,
            "keys_fingerprint": self.keys_fingerprint,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        })
        domain_msg = b"TL_PLATFORM_CAPABILITY_V1\0" + payload
        try:
            sig_bytes = bytes.fromhex(self.signature)
        except Exception:
            return False

        # 5. Strictly verify signature against anchored platform root public keys ONLY
        for anchor_hex in platform_roots.values():
            try:
                pub_bytes = bytes.fromhex(anchor_hex)
                if ed25519_verify(pub_bytes, domain_msg, sig_bytes):
                    return True
            except Exception:
                continue
        return False


def issue_platform_capability(
    app_id: int,
    app_slug: str,
    public_keys: dict[str, str],
    signing_secret_key: bytes,
    ttl_seconds: int = 86400,
) -> PlatformCapability:
    """Issue a canonical PlatformCapability signed by the out-of-process platform authority."""
    fp = hashlib.sha256(json.dumps(sorted(public_keys.items()), separators=(",", ":")).encode("utf-8")).hexdigest()
    now_utc = datetime.now(timezone.utc)
    issued_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    from datetime import timedelta
    expires_at = (now_utc + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cap_id = "cap-" + hashlib.sha256(f"{app_id}:{app_slug}:{fp}:{issued_at}".encode("utf-8")).hexdigest()[:24]
    payload = canonicalize_payload({
        "capability_id": cap_id,
        "app_id": app_id,
        "app_slug": app_slug,
        "keys_fingerprint": fp,
        "issued_at": issued_at,
        "expires_at": expires_at,
    })
    _, sig = ed25519_sign(signing_secret_key, b"TL_PLATFORM_CAPABILITY_V1\0" + payload)
    return PlatformCapability(
        capability_id=cap_id,
        app_id=app_id,
        app_slug=app_slug,
        keys_fingerprint=fp,
        issued_at=issued_at,
        expires_at=expires_at,
        signature=sig.hex(),
    )


@dataclass
class TrustRoot:
    """External root of trust containing identity and public verification keys (zero embedded private keys)."""
    trusted_app_id: int = 0
    trusted_app_slug: str = ""
    trusted_public_keys: dict[str, str] = field(default_factory=dict)
    trust_source: str = "advisory_env"
    _platform_capability: PlatformCapability | None = field(default=None, repr=False)
    _verified_via_platform: bool = field(default=False, repr=False)

    @property
    def is_out_of_process(self) -> bool:
        """
        Mechanically verifiable out-of-process isolation property.
        Returns True ONLY when mechanically authenticated via an out-of-process
        platform query (e.g. gh api) or holding a valid unforgeable platform capability.
        Cannot be asserted by local caller-supplied boolean flags.
        """
        if self._platform_capability is not None:
            return self._platform_capability.is_valid(
                app_id=self.trusted_app_id,
                app_slug=self.trusted_app_slug,
                public_keys=self.trusted_public_keys,
            )
        return self._verified_via_platform

    @classmethod
    def from_env(cls) -> TrustRoot:
        """
        Resolve TrustRoot from environment variables TL_MERGE_AUTHORITY_*.
        Local process environment variables are strictly advisory and NEVER mechanically isolated
        from agent/runtime processes (AC11). Therefore, is_out_of_process is always False.
        """
        app_id_str = os.environ.get("TL_MERGE_AUTHORITY_APP_ID", "")
        app_id = int(app_id_str) if app_id_str.isdigit() else 0
        app_slug = os.environ.get("TL_MERGE_AUTHORITY_APP_SLUG", "")
        pubkeys: dict[str, str] = {}
        env_keys = os.environ.get("TL_MERGE_AUTHORITY_PUBLIC_KEYS", "")
        if env_keys:
            for part in env_keys.split(","):
                if "=" in part:
                    kid, khex = part.split("=", 1)
                    pubkeys[kid.strip()] = khex.strip()
        single_key = os.environ.get("TL_MERGE_AUTHORITY_PUBLIC_KEY", "")
        single_key_id = os.environ.get("TL_MERGE_AUTHORITY_KEY_ID", "key-default")
        if single_key:
            pubkeys[single_key_id] = single_key.strip()
        return cls(
            trusted_app_id=app_id,
            trusted_app_slug=app_slug,
            trusted_public_keys=pubkeys,
            trust_source="advisory_env",
        )

    def authenticate_against_platform(self, gh_executable: str | list[str] = "gh") -> tuple[bool, str]:
        """
        Query the external platform CLI (gh api) out-of-process to verify this trust root.
        Rejects forged responses, forged executables, or unauthorized public keys by verifying
        strictly against the immutable platform trust anchor.
        """
        if not self.trusted_app_slug or self.trusted_app_slug != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
            self._verified_via_platform = False
            return False, f"untrusted_or_missing_app_slug: expected {IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG}, got {self.trusted_app_slug}"
        if self.trusted_app_id and int(self.trusted_app_id) != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
            self._verified_via_platform = False
            return False, f"untrusted_app_id: expected {IMMUTABLE_PLATFORM_AUTHORITY_APP_ID}, got {self.trusted_app_id}"

        gh_cmd = gh_executable if gh_executable is not None else "gh"
        cmd = [gh_cmd] if isinstance(gh_cmd, str) else list(gh_cmd)
        try:
            proc = subprocess.run(
                [*cmd, "api", f"apps/{self.trusted_app_slug}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            self._verified_via_platform = False
            return False, f"gh_api_execution_failed: {exc}"
        if proc.returncode != 0:
            self._verified_via_platform = False
            return False, f"platform_rejected: exit code {proc.returncode}"
        try:
            data = json.loads(proc.stdout)
            if not isinstance(data, dict):
                raise ValueError("platform response must be a JSON object")
        except Exception:
            self._verified_via_platform = False
            return False, "invalid_platform_json_response"

        platform_id = int(data.get("id", 0))
        if platform_id != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
            self._verified_via_platform = False
            return False, f"forged_or_unanchored_platform_response: app ID {platform_id} != {IMMUTABLE_PLATFORM_AUTHORITY_APP_ID}"

        platform_slug = str(data.get("slug", ""))
        if platform_slug and platform_slug != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
            self._verified_via_platform = False
            return False, f"forged_or_unanchored_platform_response: app slug {platform_slug} != {IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG}"

        platform_keys = data.get("public_keys")
        if not isinstance(platform_keys, dict) or not platform_keys:
            self._verified_via_platform = False
            return False, "forged_or_unanchored_platform_response: missing or empty public_keys"

        # Verify every returned key against the platform trust anchor
        platform_roots = get_platform_root_public_keys()
        for kid, khex in platform_keys.items():
            expected = platform_roots.get(kid)
            if not expected or expected != khex:
                self._verified_via_platform = False
                return False, f"forged_or_unanchored_platform_response: key {kid} not recognized by immutable platform trust anchor"

        if self.trusted_public_keys:
            for kid, khex in self.trusted_public_keys.items():
                if platform_keys.get(kid) != khex:
                    self._verified_via_platform = False
                    return False, f"platform_key_mismatch: key {kid} not recognized by platform"
        else:
            self.trusted_public_keys = dict(platform_keys)

        self.trusted_app_id = IMMUTABLE_PLATFORM_AUTHORITY_APP_ID
        self._verified_via_platform = True
        return True, "authenticated"

    def verify_out_of_process_authenticity(self, gh_executable: str | list[str] = "gh") -> tuple[bool, str]:
        """Verify that this trust root is mechanically authenticated out-of-process."""
        if self.is_out_of_process:
            return True, "verified"
        return self.authenticate_against_platform(gh_executable=gh_executable)

    @classmethod
    def from_platform(
        cls,
        app_slug: str = IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG,
        gh_executable: str | list[str] = "gh",
        trust_source: str = "dedicated_github_app",
    ) -> TrustRoot:
        """
        Construct TrustRoot by querying external platform CLI out-of-process and validating
        against the immutable platform trust anchor.
        """
        if app_slug != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
            raise ValueError(f"Untrusted app slug: {app_slug} != {IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG}")

        gh_cmd = gh_executable if gh_executable is not None else "gh"
        cmd = [gh_cmd] if isinstance(gh_cmd, str) else list(gh_cmd)
        try:
            proc = subprocess.run(
                [*cmd, "api", f"apps/{app_slug}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to query external platform via {gh_executable}: {exc}") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"External platform query failed for app '{app_slug}' with exit code {proc.returncode}: {proc.stderr}")
        try:
            data = json.loads(proc.stdout)
            if not isinstance(data, dict):
                raise ValueError("platform response must be a JSON object")
        except Exception as exc:
            raise ValueError(f"Invalid JSON returned from external platform: {exc}") from exc

        app_id = int(data.get("id", 0))
        if app_id != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
            raise ValueError(f"Forged or untrusted platform response: app ID {app_id} != {IMMUTABLE_PLATFORM_AUTHORITY_APP_ID}")

        pubkeys = dict(data.get("public_keys", {}))
        if not pubkeys:
            raise ValueError("Forged or untrusted platform response: empty public_keys")

        platform_roots = get_platform_root_public_keys()
        for kid, khex in pubkeys.items():
            expected = platform_roots.get(kid)
            if not expected or expected != khex:
                raise ValueError(f"Forged or untrusted platform response: public key {kid} does not match immutable platform trust anchor")

        root = cls(
            trusted_app_id=app_id,
            trusted_app_slug=app_slug,
            trusted_public_keys=pubkeys,
            trust_source=trust_source,
        )
        root._verified_via_platform = True
        return root

    @classmethod
    def from_platform_capability(
        cls,
        capability: PlatformCapability,
        trusted_app_id: int = IMMUTABLE_PLATFORM_AUTHORITY_APP_ID,
        trusted_app_slug: str = IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG,
        trusted_public_keys: dict[str, str] | None = None,
        trust_source: str = "dedicated_github_app",
    ) -> TrustRoot:
        """
        Construct TrustRoot bound to an unforgeable out-of-process PlatformCapability token.
        """
        keys_to_verify = dict(trusted_public_keys) if trusted_public_keys is not None else dict(IMMUTABLE_PLATFORM_ROOT_PUBLIC_KEYS)
        if not capability.is_valid(trusted_app_id, trusted_app_slug, keys_to_verify):
            raise ValueError("Invalid, expired, forged, or unanchored platform capability token")
        root = cls(
            trusted_app_id=trusted_app_id,
            trusted_app_slug=trusted_app_slug,
            trusted_public_keys=keys_to_verify,
            trust_source=trust_source,
        )
        root._platform_capability = capability
        return root

    @classmethod
    def from_external_platform(
        cls,
        trusted_app_id: int,
        trusted_app_slug: str,
        trusted_public_keys: dict[str, str],
        trust_source: str = "dedicated_github_app",
        capability: PlatformCapability | None = None,
    ) -> TrustRoot:
        """
        Construct TrustRoot for an external platform.
        Note: is_out_of_process is ONLY True if capability is valid or authenticate_against_platform() succeeds.
        """
        if not trusted_app_id or not trusted_app_slug or not trusted_public_keys:
            raise ValueError("External platform trust root requires non-empty app_id, app_slug, and trusted_public_keys")
        if int(trusted_app_id) != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID or str(trusted_app_slug) != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
            raise ValueError(f"Untrusted platform identity: expected {IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG} ({IMMUTABLE_PLATFORM_AUTHORITY_APP_ID})")
        root = cls(
            trusted_app_id=trusted_app_id,
            trusted_app_slug=trusted_app_slug,
            trusted_public_keys=dict(trusted_public_keys),
            trust_source=trust_source,
        )
        if capability is not None and capability.is_valid(trusted_app_id, trusted_app_slug, trusted_public_keys):
            root._platform_capability = capability
        return root


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
    secret_key: bytes,
    key_id: str,
    mechanism: str = "dedicated_github_app",
    integration_id: int | None = None,
    issuer: str = "thinglab-merge-authority[bot]",
) -> dict[str, Any]:
    """Signs an authorization claim using an externally provided private key."""
    if not secret_key or not isinstance(secret_key, (bytes, bytearray)):
        raise ValueError("secret_key is required and must be bytes to sign authorization envelope")
    if not key_id or not isinstance(key_id, str):
        raise ValueError("key_id is required and must be a string")
    if "issued_at" not in claim or "expires_at" not in claim:
        raise ValueError("claim must contain both 'issued_at' and 'expires_at'")
    issued_dt = validate_canonical_utc_timestamp(claim["issued_at"], "issued_at")
    expires_dt = validate_canonical_utc_timestamp(claim["expires_at"], "expires_at")
    if issued_dt > expires_dt:
        raise ValueError(f"issued_at ({claim['issued_at']}) cannot be later than expires_at ({claim['expires_at']})")
    auth_id = derive_authorization_id(claim)
    canonical_claim = canonicalize_payload(claim)
    signing_payload = AUTHORIZATION_SIGNING_DOMAIN + canonical_claim
    _, sig_bytes = ed25519_sign(bytes(secret_key), signing_payload)

    env = dict(claim)
    env["authorization_id"] = auth_id
    provenance = {
        "issuer": issuer,
        "mechanism": mechanism,
        "key_id": key_id,
        "signature": sig_bytes.hex(),
    }
    if integration_id is not None:
        provenance["integration_id"] = integration_id
    env["provenance"] = provenance
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
        if self._states.get(auth_id) == "indeterminate":
            return False
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

    @contextlib.contextmanager
    def _lock_auth(self, auth_id: str):
        lock_path = self.store_dir / f"{auth_id}.lock"
        with open(lock_path, "a") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

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
        with self._lock_auth(auth_id):
            curr = self.get_state(auth_id)
            if curr != "unused":
                return False
            payload = {
                "authorization_id": auth_id,
                "state": "reserved",
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            }
            tmp = self.store_dir / f"{auth_id}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
            try:
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp)
                os.replace(tmp, self._state_file(auth_id))
                return True
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def commit_consumed(self, auth_id: str) -> bool:
        with self._lock_auth(auth_id):
            curr = self.get_state(auth_id)
            # Priority fail-closed: once marked indeterminate, transition to consumed is strictly forbidden
            if curr == "indeterminate":
                return False
            if curr != "reserved":
                return False
            payload = {
                "authorization_id": auth_id,
                "state": "consumed",
                "consumed_at": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            }
            tmp = self.store_dir / f"{auth_id}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
            try:
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp)
                os.replace(tmp, self._state_file(auth_id))
                return True
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def mark_indeterminate(self, auth_id: str) -> None:
        with self._lock_auth(auth_id):
            payload = {
                "authorization_id": auth_id,
                "state": "indeterminate",
                "marked_at": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            }
            tmp = self.store_dir / f"{auth_id}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
            try:
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp)
                os.replace(tmp, self._state_file(auth_id))
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass


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
                        elif st == "indeterminate":
                            self.external.mark_indeterminate(aid)
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
    authorization_id: str = ""
    target_pr: int = 0
    head_sha: str = ""
    base_sha: str = ""
    checker_commit: str = ""
    candidate_commit: str = ""
    target_repository: str = ""
    authority_mode: str = ""
    reason: str = ""
    envelope: dict[str, Any] | None = None
    degraded_mode: str | None = None
    receipt_token: str = ""

    @property
    def is_confirmed(self) -> bool:
        return self.status == "CONFIRMED"

    def is_authentic(self, trust_root: TrustRoot | None = None, expected_repo: str | None = None) -> bool:
        """
        Verify that this receipt is authentic, was issued by MergeAuthorityGate,
        contains a valid cryptographic envelope signed by an authorized platform trust root,
        and carries a matching receipt_token.
        Validates envelope schema, claims, timestamps, and verifies the signature strictly
        against the anchored platform root public keys.
        Never trusts caller-controlled keys or unverified TrustRoot.
        """
        if not self.is_confirmed:
            return False
        if (
            not self.authorization_id
            or not self.candidate_commit
            or not self.checker_commit
            or not self.head_sha
            or not self.base_sha
            or not self.target_pr
        ):
            return False
        if not isinstance(self.envelope, dict) or not self.envelope:
            return False

        # 1. Mandatory JSON Schema validation (fails closed)
        schema_path = _resolve_schema_path()
        is_schema_valid, schema_err = validate_against_schema(self.envelope, str(schema_path))
        if not is_schema_valid:
            return False

        # 2. Scope bindings & mode check (AC13: automated merge authority REQUIRES delegated_single_merge)
        envelope_mode = self.envelope.get("authority_mode")
        if envelope_mode != "delegated_single_merge":
            return False
        receipt_mode = getattr(self, "authority_mode", "")
        if receipt_mode != "delegated_single_merge":
            return False
        if self.envelope.get("authorization_id") != self.authorization_id:
            return False
        if int(self.envelope.get("target_pr", 0)) != int(self.target_pr):
            return False
        envelope_repo = self.envelope.get("target_repository")
        if not isinstance(envelope_repo, str) or not envelope_repo:
            return False
        if self.target_repository and self.target_repository != envelope_repo:
            return False
        if expected_repo and (envelope_repo != expected_repo or (self.target_repository and self.target_repository != expected_repo)):
            return False
        if self.envelope.get("integration_candidate_commit") != self.candidate_commit:
            return False
        if self.envelope.get("checker_approved_commit") != self.checker_commit:
            return False
        if self.envelope.get("expected_head_sha") != self.head_sha:
            return False
        if self.envelope.get("expected_base_sha") != self.base_sha:
            return False

        # 3. Acyclic authorization_id derivation verification
        claim = {k: v for k, v in self.envelope.items() if k not in ("authorization_id", "provenance")}
        derived_auth_id = derive_authorization_id(claim)
        if self.authorization_id != derived_auth_id:
            return False

        # 4. Provenance & Identity verification
        provenance = self.envelope.get("provenance", {})
        if not isinstance(provenance, dict) or not provenance.get("signature"):
            return False
        if provenance.get("mechanism") != "dedicated_github_app":
            return False
        if provenance.get("integration_id") != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
            return False
        if provenance.get("issuer") != f"{IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG}[bot]":
            return False

        # 5. Timestamps check & expiration check
        try:
            issued_str = str(self.envelope.get("issued_at", ""))
            expires_str = str(self.envelope.get("expires_at", ""))
            issued_dt = validate_canonical_utc_timestamp(issued_str, "issued_at")
            expires_dt = validate_canonical_utc_timestamp(expires_str, "expires_at")
            if issued_dt > expires_dt:
                return False
            if datetime.now(timezone.utc) > expires_dt:
                return False
        except Exception:
            return False

        # 6. Receipt token verification
        env_sig = str(provenance.get("signature", ""))
        target_repo = str(self.target_repository or envelope_repo or "")
        expected_token = compute_receipt_token(
            authorization_id=self.authorization_id,
            target_pr=int(self.target_pr),
            candidate_commit=self.candidate_commit,
            checker_commit=self.checker_commit,
            head_sha=self.head_sha,
            base_sha=self.base_sha,
            envelope_signature=env_sig,
            target_repository=target_repo,
            authority_mode=str(envelope_mode),
        )
        if self.receipt_token != expected_token:
            return False

        # 7. Trust root validation (NEVER trust caller-controlled keys)
        platform_keys = get_platform_root_public_keys()
        if trust_root is not None:
            if not isinstance(trust_root, TrustRoot):
                return False
            if not getattr(trust_root, "is_out_of_process", False):
                return False
            if trust_root.trusted_app_id != IMMUTABLE_PLATFORM_AUTHORITY_APP_ID:
                return False
            if trust_root.trusted_app_slug != IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG:
                return False
            # Reject any trust_root with keys not matching platform anchor
            for kid, khex in trust_root.trusted_public_keys.items():
                if platform_keys.get(kid) != khex:
                    return False

        # 8. Signature verification against anchored platform root public key
        key_id = str(provenance.get("key_id", ""))
        pub_hex = platform_keys.get(key_id)
        if not pub_hex:
            return False
        try:
            pub_bytes = bytes.fromhex(pub_hex)
            sig_bytes = bytes.fromhex(env_sig)
            canonical_claim = canonicalize_payload(claim)
            signing_payload = AUTHORIZATION_SIGNING_DOMAIN + canonical_claim
            if not ed25519_verify(pub_bytes, signing_payload, sig_bytes):
                return False
        except Exception:
            return False

        return True


def parse_pr_comment_transport(
    comments: list[dict[str, Any]],
    expected_repo: str,
    pr_number: int,
    expected_head: str,
    expected_base: str,
    candidate_commit: str,
    checker_commit: str | None = None,
    authority_mode: str | None = None,
    trust_root: TrustRoot | None = None,
    schema_path: str | Path | None = None,
    gh_executable: str = "gh",
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
    resolved_schema = _resolve_schema_path(schema_path)
    if not resolved_schema.is_file():
        return f"FAIL_CLOSED: merge authorization schema file not found: {resolved_schema}", []

    root = trust_root if trust_root is not None else TrustRoot.from_env()
    if authority_mode == "delegated_single_merge":
        if trust_root is not None and getattr(root, "trust_source", "") != "advisory_env":
            is_auth, auth_err = root.verify_out_of_process_authenticity(gh_executable=gh_executable)
            if not is_auth:
                return f"FAIL_CLOSED: unauthenticated_trust_root: {auth_err}", []
        else:
            if not getattr(root, "is_out_of_process", False):
                return "FAIL_CLOSED: advisory_trust_root_cannot_authorize_delegated_single_merge", []

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
        # 1. Mandatory JSON Schema validation (fails closed)
        is_valid, errors = validate_against_schema(env, str(resolved_schema))
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
        if checker_commit is not None and env.get("checker_approved_commit") != checker_commit:
            continue
        if authority_mode is not None and env.get("authority_mode") != authority_mode:
            continue

        # 3. Validate acyclic authorization_id derivation
        claim = {k: v for k, v in env.items() if k not in {"authorization_id", "provenance"}}
        derived_id = derive_authorization_id(claim)
        if env.get("authorization_id") != derived_id:
            return f"FAIL_CLOSED: invalid_authorization_id: declared {env.get('authorization_id')} != derived {derived_id}", []

        # 4. Check temporal validity & strict UTC ISO 8601 format
        try:
            issued_str = env.get("issued_at")
            expires_str = env.get("expires_at")
            if not issued_str or not expires_str:
                return "FAIL_CLOSED: missing_timestamp: both issued_at and expires_at are required", []
            issued_dt = validate_canonical_utc_timestamp(issued_str, "issued_at")
            expires_dt = validate_canonical_utc_timestamp(expires_str, "expires_at")
            if issued_dt > expires_dt:
                return f"FAIL_CLOSED: temporal_inversion: issued_at ({issued_str}) > expires_at ({expires_str})", []
            if now_utc > expires_dt:
                continue
        except ValueError as exc:
            return f"FAIL_CLOSED: invalid_timestamp: {exc}", []

        # 5. Provenance, comment author identity, and app_id verification
        prov = env.get("provenance", {})
        mech = prov.get("mechanism")
        if mech not in {"dedicated_github_app", "operator_ed25519", "operator_webauthn"}:
            return f"FAIL_CLOSED: unsupported_mechanism: {mech}", []

        is_delegated = (authority_mode == "delegated_single_merge" or env.get("authority_mode") == "delegated_single_merge")
        if is_delegated and mech != "dedicated_github_app":
            return f"FAIL_CLOSED: mechanism_not_permitted_for_delegated_single_merge: {mech} (delegated single merge strictly requires dedicated_github_app)", []

        if mech == "dedicated_github_app":
            int_id = prov.get("integration_id")
            if int_id != root.trusted_app_id:
                return f"FAIL_CLOSED: untrusted_app_id: {int_id} != {root.trusted_app_id}", []

            author_dict = comment.get("author") or comment.get("user") or {}
            author_login = author_dict.get("login", "")
            expected_bot = f"{root.trusted_app_slug}[bot]"
            if author_login != expected_bot:
                return f"FAIL_CLOSED: untrusted_comment_author: comment author {author_login!r} is not trusted bot {expected_bot!r}", []
            if "app_id" in comment and comment["app_id"] != root.trusted_app_id:
                return f"FAIL_CLOSED: untrusted_comment_app_id: comment app_id {comment['app_id']} != {root.trusted_app_id}", []

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
        gh_executable: str = "gh",
    ) -> AuthorityReceipt:
        head_sha = str(live_pr_info.get("headRefOid", ""))
        base_sha = str(live_pr_info.get("baseRefOid", ""))
        pr_state = str(live_pr_info.get("state", "")).upper()

        if not expected_repo or not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", str(expected_repo).strip()):
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                target_repository=str(expected_repo) if expected_repo is not None else "",
                reason=f"missing_or_invalid_target_repository: '{expected_repo}'",
            )

        if not checker_commit or not candidate_commit:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id="",
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                target_repository=expected_repo,
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
                target_repository=expected_repo,
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
                target_repository=expected_repo,
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
                target_repository=expected_repo,
                reason=delta_reason,
            )

        # Out-of-process root of trust check for delegated_single_merge
        if trust_root is not None:
            resolved_root = trust_root
        else:
            try:
                resolved_root = TrustRoot.from_platform(gh_executable=gh_executable)
            except Exception:
                resolved_root = TrustRoot.from_env()

        if enforce_mode == "delegated_single_merge":
            if getattr(resolved_root, "trust_source", "") != "advisory_env":
                is_auth, auth_err = resolved_root.verify_out_of_process_authenticity(gh_executable=gh_executable)
                if not is_auth:
                    return AuthorityReceipt(
                        status="REJECTED",
                        authorization_id="",
                        target_pr=pr_number,
                        head_sha=head_sha,
                        base_sha=base_sha,
                        checker_commit=checker_commit,
                        candidate_commit=candidate_commit,
                        target_repository=expected_repo,
                        reason=f"FAIL_CLOSED: unauthenticated_trust_root: {auth_err}",
                    )
            else:
                if not getattr(resolved_root, "is_out_of_process", False):
                    return AuthorityReceipt(
                        status="AWAITING_HUMAN",
                        authorization_id="",
                        target_pr=pr_number,
                        head_sha=head_sha,
                        base_sha=base_sha,
                        checker_commit=checker_commit,
                        candidate_commit=candidate_commit,
                        target_repository=expected_repo,
                        reason="advisory_trust_root_degraded_to_human_merge_only: local process environment trust root is not mechanically isolated; delegated_single_merge requires out-of-process authority root",
                        degraded_mode="human_merge_only.enforced",
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
            checker_commit=checker_commit,
            authority_mode=enforce_mode,
            trust_root=resolved_root,
            schema_path=schema_path,
            gh_executable=gh_executable,
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
                target_repository=expected_repo,
                reason=parse_status,
            )

        envelope = envelopes[0]
        auth_id = envelope["authorization_id"]

        # Scope validation on matched envelope (defense-in-depth)
        if envelope.get("target_repository") != expected_repo:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                target_repository=expected_repo,
                reason=f"cross_repository_authority_reuse_rejected: envelope target_repository='{envelope.get('target_repository')}' does not match expected_repo='{expected_repo}'",
                envelope=envelope,
            )
        if envelope.get("checker_approved_commit") != checker_commit:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                target_repository=expected_repo,
                reason=f"envelope_checker_commit_mismatch: {envelope.get('checker_approved_commit')} != {checker_commit}",
                envelope=envelope,
            )
        if envelope.get("authority_mode") != enforce_mode:
            return AuthorityReceipt(
                status="REJECTED",
                authorization_id=auth_id,
                target_pr=pr_number,
                head_sha=head_sha,
                base_sha=base_sha,
                checker_commit=checker_commit,
                candidate_commit=candidate_commit,
                target_repository=expected_repo,
                reason=f"envelope_authority_mode_mismatch: {envelope.get('authority_mode')} != {enforce_mode}",
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
                target_repository=expected_repo,
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
                target_repository=expected_repo,
                authority_mode="human_merge_only",
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
                target_repository=expected_repo,
                authority_mode=enforce_mode,
                reason="authorization_reservation_failed_concurrent_or_consumed",
                envelope=envelope,
            )

        env_sig = ""
        if isinstance(envelope, dict):
            env_sig = str(envelope.get("provenance", {}).get("signature", ""))
        target_repo = str(expected_repo or (envelope.get("target_repository") if isinstance(envelope, dict) else "") or "")
        receipt_tok = compute_receipt_token(
            authorization_id=auth_id,
            target_pr=pr_number,
            candidate_commit=candidate_commit,
            checker_commit=checker_commit,
            head_sha=head_sha,
            base_sha=base_sha,
            envelope_signature=env_sig,
            target_repository=target_repo,
            authority_mode="delegated_single_merge",
        )

        return AuthorityReceipt(
            status="CONFIRMED",
            authorization_id=auth_id,
            target_pr=pr_number,
            head_sha=head_sha,
            base_sha=base_sha,
            checker_commit=checker_commit,
            candidate_commit=candidate_commit,
            target_repository=target_repo,
            authority_mode="delegated_single_merge",
            reason="AUTHORITY_CONFIRMED",
            envelope=envelope,
            receipt_token=receipt_tok,
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
