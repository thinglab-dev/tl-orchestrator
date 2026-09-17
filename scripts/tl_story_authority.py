#!/usr/bin/env python3
"""Story Authority Envelope and autonomous child batches — `AUTO_STORY` (T032).

One human authorization covers one Story. Under it the runtime may derive and open the
child batches that Story still needs, without asking again per batch, and without ever
inventing a signature: a child batch is authorized only because it is a verifiable strict
subset of the envelope the operator did authorize.

Three things are kept apart on purpose.

*Authority* is immutable and lives in `_tl-orc/project/story-authorities/<authority_id>.json`.
It is never rewritten to record a balance. `root_authority_digest` is
`SHA256(canonical_json(authority_payload))`, and the payload contains only the fields that
were put in front of the operator, so nothing produced after the decision — the digest
itself, the capture timestamp, the literal — can be inside what it digests.

*Consumption* is mutable and lives in `_tl-orc/runtime/story-authorities/<authority_id>/`:
an append-only, fsynced, hash-chained `journal.jsonl` written by a single holder of
`lease.lock`, plus `status.json`, which is only ever a projection of that journal.

*Lineage* is functional, not governance. When a child ends `changes_requested` with the
rework limit exhausted and every residual finding is a patch, the commit the Checker just
reviewed is preserved as-is and becomes the base of the next child. It is not merged into
the protected branch to carry state forward, and the next child does not restart from the
governance base: it starts exactly at that commit, so the final Checker reviews the
cumulative candidate and the delivered commit carries the whole lineage.

Budget is global and single-entry. A physical provider attempt is identified by a
`global_attempt_id`, is charged once against the Story, and the child batch ledger is a
projection of that charge — never a second place where the same call can be paid for.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

try:  # scripts/ on sys.path (how the runtime loads its siblings)
    from validate_execution_plan import (
        assert_protected_paths_monotonic,
        canonical_json,
        digest_of,
        sha256_hex,
        snapshot_set,
        validate_against_schema_file,
        verify_protected_paths,
    )
except ImportError:  # executed from the repository root
    from scripts.validate_execution_plan import (  # type: ignore[no-redef]
        assert_protected_paths_monotonic,
        canonical_json,
        digest_of,
        sha256_hex,
        snapshot_set,
        validate_against_schema_file,
        verify_protected_paths,
    )

try:
    import tl_job
except ImportError:  # pragma: no cover - exercised only outside the scripts/ layout
    try:
        from scripts import tl_job  # type: ignore[no-redef]
    except ImportError:
        tl_job = None  # type: ignore[assignment]


AUTHORITY_MODE = "AUTO_STORY"
LEGACY_AUTHORITY_MODE = "direct_proposal"
AUTHORITY_FORMAT = 1
# v1 runs one child batch at a time. Concurrency here would mean two writers on one budget.
MAX_ACTIVE_CHILD_BATCHES = 1

PROJECT_AUTHORITY_DIR = "_tl-orc/project/story-authorities"
RUNTIME_AUTHORITY_DIR = "_tl-orc/runtime/story-authorities"
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
ENVELOPE_SCHEMA = SCHEMA_DIR / "story-authority-envelope.schema.json"
CHILD_PROPOSAL_SCHEMA = SCHEMA_DIR / "story-child-proposal.schema.json"

# Exactly the fields submitted to the human decision, in the order §2.13 declares them.
AUTHORITY_PAYLOAD_FIELDS = (
    "authority_id",
    "work_ref",
    "authorized_spec_revision",
    "authorized_spec_sha256",
    "authorized_write_scope",
    "allowed_effects",
    "protected_paths",
    "global_model_call_budget",
    "max_child_batches",
    "max_consecutive_failed_batches",
    "wall_clock_deadline",
    "hard_stops",
)
# Produced after the decision. Their presence inside the payload would make the digest
# depend on values that only exist because the digest was already computed.
POST_AUTHORIZATION_FIELDS = (
    "root_authority_digest",
    "operator_authorization",
    "operator_authorization_ref",
    "authorized_at",
    "authorized_literal",
    "authority_source",
)

JOURNAL_EVENTS = (
    "authority_open",
    "model_call_reserved",
    "model_call_consumed",
    "model_call_released",
    "child_derived",
    "child_open",
    "child_closed",
    "child_failed",
    "hard_stop",
    "authority_closed",
)
# What identifies one registered derivation. Two `child_derived` events for the same child agree
# on all of these or they are not the same derivation.
DERIVATION_DIGEST_KEYS = (
    "root_authority_digest", "parent_authority_digest", "parent_batch_digest",
    "child_proposal_digest", "derivation_proof_digest",
)
ATTEMPT_STATES = ("reserved", "consumed", "released", "ambiguous")
# `ambiguous` is charged: a call whose outcome cannot be proven may have reached the provider.
CHARGED_ATTEMPT_STATES = frozenset({"consumed", "ambiguous"})

EFFECT_KEYS = ("local_write", "local_commit", "local_merge", "pull_request", "push", "tag", "release", "merge")

# A residual finding is derivable only if it is all four of these. Anything else returns the
# Story to the operator; the runtime never treats "not approved" as "open another batch".
PATCH_ONLY_TARGET_ROLE = "maker"
PATCH_ONLY_CATEGORY = "patch"
PATCH_ONLY_SCOPE_STATUS = "inside_parent_envelope"
PATCH_ONLY_SPEC_STATUS = "unchanged"
DERIVATION_HARD_STOP_REASONS = (
    "bad_spec", "intent_gap", "human", "security", "scope_expansion",
    "new_boundary", "migration", "capability_expansion",
)

# Applied with `fullmatch` to the literal exactly as captured. `^...$` with `match` would accept
# a trailing newline, and normalizing the input first would accept whatever normalizes into it.
AUTHORIZATION_LITERAL_RE = re.compile(r"AUTORIZO STORY (?P<work_ref>\S+) sha256:(?P<digest>[0-9a-f]{64})")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

COGNITIVE_CLIS = ("agy", "codex", "claude", "gemini")
BARRIER_EXIT_CODE = 97
BARRIER_MESSAGE = (
    "tl-orc cognitive call barrier: direct invocation is blocked under AUTO_STORY. "
    "Every model call must pass through budgeted_model_dispatch under the Story Authority ledger."
)


class Refusal(Exception):
    """Invalid input or state this module refuses to act on."""

    def __init__(self, message: str, code: int = 4):
        super().__init__(message)
        self.code = code


class HardStop(Exception):
    """AUTO_STORY stops and returns control to the operator. Never recovered automatically."""

    def __init__(self, reason: str, detail: str = "", **evidence: Any):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
        self.evidence = evidence


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _require_timestamp(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value):
        raise Refusal(f"{field_name} must be a canonical UTC timestamp (YYYY-MM-DDTHH:MM:SSZ), got {value!r}")
    return value


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if tl_job is not None:
        tl_job.write_atomic(path, payload)
        return
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


# --------------------------------------------------------------------------- authority payload

def _assert_payload_shape(payload: Any) -> None:
    """The payload is exactly the twelve authorized fields. Nothing produced later belongs in it."""
    if not isinstance(payload, dict):
        raise Refusal("authority_payload must be a JSON object")
    present = set(payload)
    contaminated = sorted(present & set(POST_AUTHORIZATION_FIELDS))
    if contaminated:
        raise Refusal(
            "authority_missing_or_ambiguous: authority_payload carries post-authorization field(s) "
            f"{contaminated}; the digest must not depend on anything produced after the human decision", 2)
    missing = [name for name in AUTHORITY_PAYLOAD_FIELDS if name not in present]
    if missing:
        raise Refusal(f"authority_payload is missing required field(s) {missing}")
    extra = sorted(present - set(AUTHORITY_PAYLOAD_FIELDS))
    if extra:
        raise Refusal(f"authority_payload carries unauthorized field(s) {extra}")


def canonical_authority_payload(payload: dict) -> str:
    """canonical_json_v1 over exactly the authorized fields."""
    _assert_payload_shape(payload)
    return canonical_json(payload)


def root_authority_digest(payload: dict) -> str:
    return sha256_hex(canonical_authority_payload(payload))


def authorization_literal(work_ref: str, digest: str) -> str:
    return f"AUTORIZO STORY {work_ref} sha256:{digest}"


def parse_authorization_literal(literal: str) -> tuple[str, str]:
    """Parse the literal byte for byte as captured. Nothing is trimmed, folded or coerced first:
    a leading or trailing space, a tab, a newline or a non-string is a different utterance, and
    the only utterance that grants authority is the canonical one."""
    match = AUTHORIZATION_LITERAL_RE.fullmatch(literal) if isinstance(literal, str) else None
    if not match:
        raise Refusal(
            "authority_missing_or_ambiguous: the operator authorization must be exactly "
            "'AUTORIZO STORY <work_ref> sha256:<root_authority_digest>'", 2)
    return match.group("work_ref"), match.group("digest")


def assert_exact_authorization(literal: Any, work_ref: str, digest: str) -> None:
    """The one concession: the literal equals the canonical phrase for this payload, exactly."""
    parsed_work_ref, parsed_digest = parse_authorization_literal(literal)
    if parsed_work_ref != work_ref:
        raise Refusal(
            f"authority_missing_or_ambiguous: authorization names Story {parsed_work_ref!r} but the payload is for "
            f"{work_ref!r}", 2)
    if parsed_digest != digest:
        raise Refusal(
            f"authority_missing_or_ambiguous: authorization carries digest {parsed_digest} but the payload "
            f"digests to {digest}", 2)
    if literal != authorization_literal(work_ref, digest):
        raise Refusal(
            "authority_missing_or_ambiguous: the operator authorization is not the canonical literal for this "
            "payload", 2)


def build_authority_payload(
    *,
    authority_id: str,
    work_ref: str,
    authorized_spec_revision: str,
    authorized_spec_sha256: str,
    authorized_write_scope: dict,
    allowed_effects: dict,
    protected_paths: list[dict],
    global_model_call_budget: int,
    max_child_batches: int,
    max_consecutive_failed_batches: int,
    wall_clock_deadline: str,
    hard_stops: Iterable[str],
) -> dict:
    """Formulate the payload in read-only mode: no side effect, no authority granted yet."""
    payload = {
        "authority_id": authority_id,
        "work_ref": work_ref,
        "authorized_spec_revision": authorized_spec_revision,
        "authorized_spec_sha256": authorized_spec_sha256,
        "authorized_write_scope": {
            "required_mutation_targets": sorted(set(authorized_write_scope.get("required_mutation_targets") or [])),
            "conditional_mutation_targets": sorted(set(authorized_write_scope.get("conditional_mutation_targets") or [])),
            "forbidden_paths": sorted(set(authorized_write_scope.get("forbidden_paths") or [])),
        },
        "allowed_effects": {key: bool(allowed_effects.get(key, False)) for key in EFFECT_KEYS},
        "protected_paths": list(protected_paths),
        "global_model_call_budget": int(global_model_call_budget),
        "max_child_batches": int(max_child_batches),
        "max_consecutive_failed_batches": int(max_consecutive_failed_batches),
        "wall_clock_deadline": _require_timestamp(wall_clock_deadline, "wall_clock_deadline"),
        "hard_stops": sorted(set(hard_stops)),
    }
    _assert_payload_shape(payload)
    return payload


def present_for_authorization(payload: dict) -> dict:
    """What the operator is shown: the payload, its digest, and the literal they must issue."""
    digest = root_authority_digest(payload)
    return {
        "authority_mode": AUTHORITY_MODE,
        "authority_payload": payload,
        "root_authority_digest": digest,
        "required_operator_literal": authorization_literal(payload["work_ref"], digest),
        "canonical_json": canonical_authority_payload(payload),
    }


def freeze_authority(payload: dict, *, authorized_literal: str, authority_source: str, authorized_at: str | None = None) -> dict:
    """Bind the human decision to the payload. Refuses anything but the exact canonical literal."""
    digest = root_authority_digest(payload)
    assert_exact_authorization(authorized_literal, payload["work_ref"], digest)
    if not str(authority_source).strip():
        raise Refusal("operator_authorization.authority_source must name where the decision was captured")
    envelope = {
        "authority_payload": payload,
        "root_authority_digest": digest,
        "operator_authorization": {
            "authority_source": str(authority_source),
            "authorized_at": _require_timestamp(authorized_at or now_iso(), "authorized_at"),
            "authorized_literal": authorized_literal,  # persisted exactly as issued, never normalized
        },
    }
    valid, errors = validate_against_schema_file(envelope, ENVELOPE_SCHEMA)
    if not valid:
        raise Refusal(f"story authority envelope violates its schema: {errors}")
    return envelope


def verify_authority_envelope(envelope: Any) -> dict:
    """Recompute the digest and require exact equality. Any divergence is a hard stop."""
    valid, errors = validate_against_schema_file(envelope, ENVELOPE_SCHEMA)
    if not valid:
        raise HardStop("authority_missing_or_ambiguous", f"envelope violates its schema: {errors}")
    payload = envelope["authority_payload"]
    try:
        recomputed = root_authority_digest(payload)
    except Refusal as exc:
        raise HardStop("authority_missing_or_ambiguous", str(exc)) from exc
    declared = envelope["root_authority_digest"]
    if recomputed != declared:
        raise HardStop(
            "state_integrity",
            f"authority payload digests to {recomputed} but the envelope declares {declared}; "
            "the authorized payload was mutated after the human decision",
            declared=declared, recomputed=recomputed)
    literal = envelope["operator_authorization"]["authorized_literal"]
    try:
        assert_exact_authorization(literal, payload["work_ref"], declared)
    except Refusal as exc:
        raise HardStop(
            "authority_missing_or_ambiguous",
            f"operator authorization {literal!r} does not bind this payload: {exc}") from exc
    return envelope


def authority_envelope_path(repo: str | Path, authority_id: str) -> Path:
    return Path(repo) / PROJECT_AUTHORITY_DIR / f"{authority_id}.json"


def publish_authority(repo: str | Path, envelope: dict) -> Path:
    """Persist the frozen envelope. An existing envelope is never overwritten in place."""
    verify_authority_envelope(envelope)
    path = authority_envelope_path(repo, envelope["authority_payload"]["authority_id"])
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != envelope:
            raise Refusal(
                f"authority_missing_or_ambiguous: {path.as_posix()} already holds a different frozen envelope", 2)
        return path
    _write_json_atomic(path, envelope)
    return path


def load_authority(path: str | Path) -> dict:
    target = Path(path)
    try:
        envelope = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HardStop("authority_missing_or_ambiguous", f"cannot read {target.as_posix()}: {exc}") from exc
    return verify_authority_envelope(envelope)


# --------------------------------------------------------------------------- journal

class AuthorityJournal:
    """Append-only JSONL, one writer, write-ahead, fsynced, hash-chained."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._seq = 0
        self._prev = ""

    def append(self, kind: str, **payload: Any) -> dict:
        if kind not in JOURNAL_EVENTS:
            raise Refusal(f"unknown authority journal event {kind!r}")
        self._seq += 1
        event = {"format_version": AUTHORITY_FORMAT, "seq": self._seq, "at": now_iso(), "kind": kind,
                 "prev": self._prev, **payload}
        line = canonical_json(event)
        self._prev = sha256_hex(line)[:16]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def read(self) -> tuple[list[dict], int]:
        events: list[dict] = []
        invalid = 0
        prev = ""
        if not self.path.is_file():
            return events, invalid
        with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except ValueError:
                    invalid += 1
                    continue
                if (not isinstance(event, dict) or event.get("format_version") != AUTHORITY_FORMAT
                        or event.get("kind") not in JOURNAL_EVENTS):
                    invalid += 1
                    continue
                # A line edited, removed or inserted after the fact breaks every later link.
                if event.get("prev") != prev:
                    invalid += 1
                prev = sha256_hex(raw)[:16]
                events.append(event)
        self._prev = prev
        return events, invalid

    def fold(self) -> "AuthorityState":
        events, invalid = self.read()
        state = AuthorityState(invalid_lines=invalid)
        seq = 0
        for event in events:
            seq = max(seq, int(event.get("seq", 0)))
            state.events += 1
            kind = event["kind"]
            if kind == "authority_open":
                state.opened = True
                state.opened_at = event.get("at", "")
                state.root_authority_digest = event.get("root_authority_digest", "")
                state.global_model_call_budget = int(event.get("global_model_call_budget", 0))
            elif kind == "model_call_reserved":
                attempt_id = event["global_attempt_id"]
                state.attempts[attempt_id] = {
                    "global_attempt_id": attempt_id,
                    "logical_call_id": event.get("logical_call_id", ""),
                    "child_batch_id": event.get("child_batch_id", ""),
                    "role": event.get("role", ""),
                    "phase": event.get("phase", ""),
                    "payload_digest": event.get("payload_digest", ""),
                    "state": "reserved",
                    "reserved_at": event.get("at", ""),
                }
                state.attempt_order.append(attempt_id)
            elif kind in {"model_call_consumed", "model_call_released"}:
                attempt_id = event["global_attempt_id"]
                record = state.attempts.get(attempt_id)
                if record is None:  # a result without its reservation: charge conservatively
                    record = {"global_attempt_id": attempt_id, "logical_call_id": event.get("logical_call_id", ""),
                              "child_batch_id": event.get("child_batch_id", ""), "role": "", "phase": "",
                              "payload_digest": "", "state": "reserved", "reserved_at": event.get("at", "")}
                    state.attempts[attempt_id] = record
                    state.attempt_order.append(attempt_id)
                outcome = event.get("outcome") or ("consumed" if kind == "model_call_consumed" else "released")
                # An outcome this module never writes is treated as ambiguous, which charges the
                # slot: an unreadable settlement is not evidence that nothing reached the provider.
                record["state"] = outcome if outcome in ATTEMPT_STATES else "ambiguous"
                record["settled_at"] = event.get("at", "")
                if event.get("receipt"):
                    record["receipt"] = event["receipt"]
            elif kind == "child_derived":
                child = state.children.setdefault(event["child_batch_id"], {})
                registered = child.get("derivation")
                if registered is None:
                    state.derived.append(event)
                    child["derivation"] = event
                    child["state"] = "derived"
                elif any(registered.get(key) != event.get(key) for key in DERIVATION_DIGEST_KEYS):
                    # The first derivation is the registered one. A later, different one for the same
                    # child never replaces it: it is evidence that the journal was written around
                    # `record_child_derived`, and the ledger refuses to open on it.
                    state.derivation_conflicts.append(event["child_batch_id"])
            elif kind == "child_open":
                child = state.children.setdefault(event["child_batch_id"], {})
                child["state"] = "open"
                child["open"] = event
            elif kind == "child_closed":
                child = state.children.setdefault(event["child_batch_id"], {})
                child["state"] = "closed"
                child["closure"] = event
                state.last_closed_child = event["child_batch_id"]
                if event.get("made_progress"):
                    state.consecutive_failures = 0
                else:
                    state.consecutive_failures += 1
            elif kind == "child_failed":
                child = state.children.setdefault(event["child_batch_id"], {})
                child["state"] = "failed"
                child["failure"] = event
                state.consecutive_failures += 1
            elif kind == "hard_stop":
                state.hard_stops.append(event)
            elif kind == "authority_closed":
                state.closed = True
                state.close_state = event.get("state", "done")
                state.close_reason = event.get("reason", "")
        self._seq = seq
        return state


@dataclass
class AuthorityState:
    """Everything the authority needs, rebuilt from the journal alone."""

    events: int = 0
    opened: bool = False
    opened_at: str = ""
    root_authority_digest: str = ""
    global_model_call_budget: int = 0
    attempts: dict[str, dict] = field(default_factory=dict)
    attempt_order: list[str] = field(default_factory=list)
    children: dict[str, dict] = field(default_factory=dict)
    derived: list[dict] = field(default_factory=list)
    derivation_conflicts: list[str] = field(default_factory=list)
    hard_stops: list[dict] = field(default_factory=list)
    consecutive_failures: int = 0
    last_closed_child: str = ""
    closed: bool = False
    close_state: str = ""
    close_reason: str = ""
    invalid_lines: int = 0

    @property
    def consumed_calls(self) -> int:
        return sum(1 for record in self.attempts.values() if record["state"] in CHARGED_ATTEMPT_STATES)

    @property
    def open_reservations(self) -> int:
        return sum(1 for record in self.attempts.values() if record["state"] == "reserved")

    @property
    def released_calls(self) -> int:
        return sum(1 for record in self.attempts.values() if record["state"] == "released")

    def remaining(self, budget: int) -> int:
        # An open reservation is held against the budget: until its outcome is known, the call
        # may already have reached the provider.
        return budget - self.consumed_calls - self.open_reservations

    def attempts_for_child(self, child_batch_id: str) -> list[dict]:
        return [self.attempts[a] for a in self.attempt_order if self.attempts[a].get("child_batch_id") == child_batch_id]

    def active_children(self) -> list[str]:
        return sorted(cid for cid, child in self.children.items() if child.get("state") in {"derived", "open"})

    def closure_of(self, child_batch_id: str) -> dict | None:
        return (self.children.get(child_batch_id) or {}).get("closure")

    def derivation_of(self, child_batch_id: str) -> dict | None:
        """The registered `child_derived` event for exactly this child, or None."""
        return (self.children.get(child_batch_id) or {}).get("derivation")

    def predecessors_of(self, child_batch_id: str) -> list[str]:
        """Children journaled before this one, in journal order. For a child not journaled yet,
        that is every child the authority knows."""
        known = list(self.children)
        return known[:known.index(child_batch_id)] if child_batch_id in known else known

    def latest_closed(self, child_batch_ids: Iterable[str]) -> str:
        """The most recently closed child among the given ones, or '' when none closed."""
        closed = [(int((self.closure_of(cid) or {}).get("seq", 0)), cid)
                  for cid in child_batch_ids if self.closure_of(cid) is not None]
        return max(closed)[1] if closed else ""


# --------------------------------------------------------------------------- the authority

class StoryAuthority:
    """The Story Authority ledger: exclusive lease, global budget, derivation and lineage."""

    def __init__(self, envelope: dict, runtime_dir: str | Path, *, repo: str | Path | None = None):
        self.envelope = verify_authority_envelope(envelope)
        self.payload = self.envelope["authority_payload"]
        self.authority_id = self.payload["authority_id"]
        self.root_digest = self.envelope["root_authority_digest"]
        self.runtime_dir = Path(runtime_dir)
        self.repo = Path(repo) if repo is not None else None
        self.journal = AuthorityJournal(self.runtime_dir / "journal.jsonl")
        self._lease = None
        self.state = AuthorityState()

    # ---- construction helpers ----------------------------------------------------------

    @classmethod
    def open_for(cls, repo: str | Path, authority_id: str) -> "StoryAuthority":
        repo = Path(repo)
        envelope = load_authority(authority_envelope_path(repo, authority_id))
        return cls(envelope, repo / RUNTIME_AUTHORITY_DIR / authority_id, repo=repo)

    # ---- lease and journal -------------------------------------------------------------

    def acquire(self) -> "StoryAuthority":
        if self._lease is not None:
            return self
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        handle = open(self.runtime_dir / "lease.lock", "a+", encoding="utf-8")
        if not _lock_exclusive(handle):
            handle.close()
            raise Refusal(
                f"coordinator_conflict: another runtime holds the lease for story authority {self.authority_id}", 5)
        self._lease = handle
        self.refold()
        broken = ""
        if self.state.invalid_lines:
            broken = f"authority journal has {self.state.invalid_lines} invalid line(s); the hash chain is broken"
        elif self.state.opened and self.state.root_authority_digest != self.root_digest:
            broken = (f"the journal was opened for root_authority_digest {self.state.root_authority_digest} but "
                      f"the envelope digests to {self.root_digest}")
        elif self.state.derivation_conflicts:
            broken = (f"child batch(es) {sorted(set(self.state.derivation_conflicts))} were journaled as derived "
                      "more than once with different digests; a registered derivation is never replaced")
        if broken:
            self.release()  # a ledger that refuses to open must not keep the lease it refused under
            raise HardStop("state_integrity", broken, authority_id=self.authority_id)
        if not self.state.opened:
            self.journal.append(
                "authority_open", authority_id=self.authority_id, work_ref=self.payload["work_ref"],
                root_authority_digest=self.root_digest,
                global_model_call_budget=self.payload["global_model_call_budget"],
                max_child_batches=self.payload["max_child_batches"],
                max_consecutive_failed_batches=self.payload["max_consecutive_failed_batches"],
                wall_clock_deadline=self.payload["wall_clock_deadline"],
                authorized_at=self.envelope["operator_authorization"]["authorized_at"])
            self.refold()
        self.write_status()
        return self

    def release(self) -> None:
        if self._lease is not None:
            _unlock_exclusive(self._lease)
            self._lease.close()
            self._lease = None

    def __enter__(self) -> "StoryAuthority":
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()

    def refold(self) -> AuthorityState:
        self.state = self.journal.fold()
        return self.state

    def _require_lease(self) -> None:
        if self._lease is None:
            raise Refusal(
                "coordinator_conflict: the story authority lease must be held before reserving or deriving", 5)

    def _require_open(self) -> None:
        self.refold()
        if self.state.closed:
            raise HardStop(
                "authority_missing_or_ambiguous",
                f"story authority {self.authority_id} is closed ({self.state.close_state}: {self.state.close_reason})")

    # ---- global budget -----------------------------------------------------------------

    @property
    def budget(self) -> int:
        return int(self.payload["global_model_call_budget"])

    @property
    def remaining_global_budget(self) -> int:
        return self.state.remaining(self.budget)

    def assert_budget_covers(self, requested_calls: int) -> None:
        if requested_calls < 0:
            raise Refusal("requested_calls must not be negative")
        if self.remaining_global_budget < requested_calls:
            reason = "insufficient_budget_for_unit_verification" if requested_calls > 1 else "model_call_budget_exhausted"
            raise HardStop(
                reason,
                f"{self.state.consumed_calls} consumed + {self.state.open_reservations} reserved + "
                f"{requested_calls} requested > {self.budget}",
                authority_id=self.authority_id, remaining=self.remaining_global_budget)

    def next_global_attempt_id(self, logical_call_id: str = "") -> str:
        """A fresh id per physical attempt. A retry never reuses the id of an earlier attempt."""
        self.refold()
        used = {int(match.group(1)) for match in
                (re.match(rf"^{re.escape(self.authority_id)}-attempt-(\d+)$", a) for a in self.state.attempts) if match}
        return f"{self.authority_id}-attempt-{max(used) + 1 if used else 1:03d}"

    def reserve_call(
        self,
        *,
        logical_call_id: str,
        global_attempt_id: str,
        child_batch_id: str,
        role: str = "",
        phase: str = "",
        payload_digest: str = "",
        requested_calls: int = 1,
    ) -> dict:
        """Write-ahead reservation under the lease. Idempotent for an identical replayed attempt."""
        self._require_lease()
        self._require_open()
        existing = self.state.attempts.get(global_attempt_id)
        if existing is not None:
            same = (existing.get("logical_call_id") == logical_call_id
                    and existing.get("child_batch_id") == child_batch_id
                    and existing.get("payload_digest") == payload_digest)
            if existing["state"] == "reserved" and same:
                return existing  # crash between reservation and dispatch: the slot is already held
            raise Refusal(
                f"global_attempt_id_reuse: {global_attempt_id} is already {existing['state']}; "
                "a retry must mint a new global_attempt_id", 2)
        self.assert_budget_covers(max(1, int(requested_calls)))
        self.journal.append(
            "model_call_reserved", authority_id=self.authority_id, global_attempt_id=global_attempt_id,
            logical_call_id=logical_call_id, child_batch_id=child_batch_id, role=role, phase=phase,
            payload_digest=payload_digest)
        self.refold()
        self.write_status()
        return self.state.attempts[global_attempt_id]

    def consume_call(self, global_attempt_id: str, *, outcome: str = "consumed", receipt: dict | None = None) -> dict:
        """Charge the attempt exactly once. Replaying a settled attempt never charges twice."""
        self._require_lease()
        if outcome not in {"consumed", "ambiguous"}:
            raise Refusal(f"consume_call outcome must be 'consumed' or 'ambiguous', got {outcome!r}")
        self.refold()
        record = self.state.attempts.get(global_attempt_id)
        if record is None:
            raise Refusal(f"unknown global_attempt_id {global_attempt_id}: reserve before consuming", 2)
        if record["state"] in CHARGED_ATTEMPT_STATES:
            return record
        if record["state"] == "released":
            raise Refusal(
                f"global_attempt_id {global_attempt_id} was released as proven pre-dispatch; it cannot be charged", 2)
        self.journal.append(
            "model_call_consumed", authority_id=self.authority_id, global_attempt_id=global_attempt_id,
            logical_call_id=record.get("logical_call_id", ""), child_batch_id=record.get("child_batch_id", ""),
            outcome=outcome, receipt=receipt or {})
        self.refold()
        self.write_status()
        return self.state.attempts[global_attempt_id]

    def release_call(self, global_attempt_id: str, *, proof: str) -> dict:
        """Release a reservation only when it is proven the call never reached the provider."""
        self._require_lease()
        if not str(proof).strip():
            raise Refusal("release_call requires the proof that the dispatch never started", 2)
        self.refold()
        record = self.state.attempts.get(global_attempt_id)
        if record is None:
            raise Refusal(f"unknown global_attempt_id {global_attempt_id}", 2)
        if record["state"] == "released":
            return record
        if record["state"] in CHARGED_ATTEMPT_STATES:
            raise Refusal(
                f"global_attempt_id {global_attempt_id} is already {record['state']}; a charged call is never released", 2)
        self.journal.append(
            "model_call_released", authority_id=self.authority_id, global_attempt_id=global_attempt_id,
            logical_call_id=record.get("logical_call_id", ""), child_batch_id=record.get("child_batch_id", ""),
            outcome="released", proof=str(proof))
        self.refold()
        self.write_status()
        return self.state.attempts[global_attempt_id]

    def reconcile_orphan_reservations(self, child_batch_id: str, resolver: Callable[[dict], str] | None = None) -> list[dict]:
        """Settle reservations left open by a crash, conservatively unless the transport proves otherwise.

        Default verdict is `ambiguous`, which charges the slot: a reservation whose outcome nobody
        can prove may already have reached the provider, and releasing it would let the same budget
        be spent twice.
        """
        self._require_lease()
        self.refold()
        settled: list[dict] = []
        for attempt in list(self.state.attempts_for_child(child_batch_id)):
            if attempt["state"] != "reserved":
                continue
            verdict = (resolver(attempt) if resolver else "ambiguous") or "ambiguous"
            if verdict == "released":
                settled.append(self.release_call(
                    attempt["global_attempt_id"],
                    proof="reconciliation: the transport proved this dispatch never started"))
            else:
                settled.append(self.consume_call(attempt["global_attempt_id"],
                                                 outcome="consumed" if verdict == "consumed" else "ambiguous",
                                                 receipt={"reconciled": True}))
        return settled

    def child_budget_projection(self, child_batch_id: str) -> dict:
        """The child ledger is this projection of the authority journal, never a second ledger."""
        self.refold()
        attempts = self.state.attempts_for_child(child_batch_id)
        granted = 0
        child = self.state.children.get(child_batch_id) or {}
        derivation = child.get("derivation") or {}
        if derivation:
            granted = int(derivation.get("granted_model_calls", 0))
        return {
            "child_batch_id": child_batch_id,
            "granted_model_calls": granted,
            "consumed_model_calls": sum(1 for a in attempts if a["state"] in CHARGED_ATTEMPT_STATES),
            "reserved_model_calls": sum(1 for a in attempts if a["state"] == "reserved"),
            "released_model_calls": sum(1 for a in attempts if a["state"] == "released"),
            "global_attempt_ids": [a["global_attempt_id"] for a in attempts],
        }

    def reconcile_child_batch(self, batch: dict, child_batch_id: str) -> dict:
        """On resume the authority journal is authoritative; the child ledger is rebuilt from it."""
        projection = self.child_budget_projection(child_batch_id)
        budget = batch.setdefault("budget", {})
        budget["consumed_model_calls"] = projection["consumed_model_calls"]
        budget["reserved_model_calls"] = projection["reserved_model_calls"]
        budget["max_model_calls"] = projection["granted_model_calls"] or budget.get("max_model_calls", 0)
        budget["pending_call"] = None
        for attempt in self.state.attempts_for_child(child_batch_id):
            if attempt["state"] == "reserved":
                budget["pending_call"] = {
                    "call_id": attempt.get("logical_call_id") or attempt["global_attempt_id"],
                    "role": attempt.get("role") or "maker",
                    "phase": attempt.get("phase") or "implementation",
                    "payload_digest": attempt.get("payload_digest", ""),
                    "global_attempt_id": attempt["global_attempt_id"],
                }
                break
        return batch

    # ---- children ----------------------------------------------------------------------

    def record_child_derived(self, proposal: dict, proof: dict) -> dict:
        """Register the derivation: the proposal and its proof, whole, in one journal append.

        This event is the source of truth a runtime later binds an executable batch to, so nothing
        is journaled on trust. The digests are recomputed from the documents handed in, the proof
        must be the one `verify_derivation` yields for this proposal against the ledger as it is
        now, and a child that is already registered is never registered differently.
        """
        self._require_lease()
        self._require_open()
        child_batch_id = str((proposal or {}).get("child_batch_id", ""))
        for name, ok, reason, detail, evidence in registered_derivation_checks(
                self, self.state, child_batch_id, proposal, proof):
            if not ok:
                self.hard_stop(reason, f"{name}: {detail}", check=name, **evidence)
        registered = self.state.derivation_of(child_batch_id)
        if registered is not None:
            if all(registered.get(key) == proof.get(key) for key in DERIVATION_DIGEST_KEYS):
                return registered  # replay after a crash: the derivation is already on the journal
            self.hard_stop(
                "state_integrity",
                f"child batch {child_batch_id} is already derived as {registered['child_proposal_digest'][:16]}; "
                "a registered derivation is never replaced", child_batch_id=child_batch_id)
        event = self.journal.append(
            "child_derived", authority_id=self.authority_id, child_batch_id=child_batch_id,
            parent_child_batch_id=proposal.get("parent_child_batch_id"),
            root_authority_digest=proof["root_authority_digest"],
            parent_authority_digest=proof["parent_authority_digest"],
            parent_batch_digest=proof["parent_batch_digest"],
            child_proposal_digest=proof["child_proposal_digest"],
            derivation_proof_digest=proof["derivation_proof_digest"],
            granted_model_calls=int(proposal["model_call_budget"]),
            functional_parent_checkpoint=proposal.get("functional_parent_checkpoint"),
            unresolved_action_items_digest=proof.get("unresolved_action_items_digest", ""),
            child_proposal=proposal, derivation_proof=proof)
        self.refold()
        self.write_status()
        return event

    def record_child_open(self, child_batch_id: str, *, branch: str, head_commit: str, tree: str) -> dict:
        self._require_lease()
        self._require_open()
        event = self.journal.append(
            "child_open", authority_id=self.authority_id, child_batch_id=child_batch_id, branch=branch,
            head_commit=head_commit, tree=tree)
        self.refold()
        self.write_status()
        return event

    def record_child_closed(
        self,
        *,
        child_batch_id: str,
        governance_base_commit: str,
        checker_reviewed_commit: str,
        checker_reviewed_tree: str,
        functional_checkpoint_commit: str,
        functional_checkpoint_tree: str,
        checker_verdict: str,
        unresolved_action_items: list[dict] | None = None,
        unresolved_digest: str | None = None,
    ) -> dict:
        """Persist the functional lineage of a closing child, merged or not."""
        self._require_lease()
        self._require_open()
        for name, value in (("governance_base_commit", governance_base_commit),
                            ("checker_reviewed_commit", checker_reviewed_commit),
                            ("functional_checkpoint_commit", functional_checkpoint_commit)):
            if not _COMMIT_RE.match(str(value)):
                raise Refusal(f"{name} must be a full 40 character commit sha, got {value!r}")
        digest = unresolved_digest if unresolved_digest is not None else unresolved_action_items_digest(
            unresolved_action_items or [])
        inherited = ((self.state.children.get(child_batch_id) or {}).get("derivation") or {}).get(
            "functional_parent_checkpoint") or {}
        made_progress = checker_reviewed_tree != inherited.get("tree")
        event = self.journal.append(
            "child_closed", authority_id=self.authority_id, child_batch_id=child_batch_id,
            governance_base_commit=governance_base_commit, checker_reviewed_commit=checker_reviewed_commit,
            checker_reviewed_tree=checker_reviewed_tree,
            functional_checkpoint_commit=functional_checkpoint_commit,
            functional_checkpoint_tree=functional_checkpoint_tree, checker_verdict=checker_verdict,
            unresolved_action_items_digest=digest, made_progress=made_progress)
        self.refold()
        self.write_status()
        return event

    def record_child_failed(self, child_batch_id: str, *, reason: str, detail: str = "") -> dict:
        self._require_lease()
        event = self.journal.append(
            "child_failed", authority_id=self.authority_id, child_batch_id=child_batch_id, reason=reason,
            detail=detail[:400])
        self.refold()
        self.write_status()
        return event

    def assert_failure_streak(self) -> None:
        limit = int(self.payload["max_consecutive_failed_batches"])
        if self.state.consecutive_failures >= limit:
            self.hard_stop("consecutive_batch_failures_exhausted",
                           f"{self.state.consecutive_failures} consecutive child batches closed without progress "
                           f"(limit {limit})")

    # ---- terminal states ---------------------------------------------------------------

    def hard_stop(self, reason: str, detail: str = "", **evidence: Any) -> None:
        """Journal the stop and raise. AUTO_STORY never recovers from a hard stop on its own."""
        if self._lease is not None:
            self.journal.append("hard_stop", authority_id=self.authority_id, reason=reason, detail=detail[:400],
                                evidence=evidence)
            self.refold()
            self.write_status()
        raise HardStop(reason, detail, **evidence)

    def close_authority(self, *, state: str = "done", reason: str = "") -> dict:
        self._require_lease()
        self.refold()
        if self.state.closed:
            return self.state.children  # already terminal; closing twice changes nothing
        event = self.journal.append("authority_closed", authority_id=self.authority_id, state=state, reason=reason)
        self.refold()
        self.write_status()
        return event

    # ---- projection ---------------------------------------------------------------------

    def status_projection(self) -> dict:
        state = self.state
        return {
            "schema_version": 1,
            "projection_of": "journal.jsonl",
            "authority_id": self.authority_id,
            "authority_mode": AUTHORITY_MODE,
            "work_ref": self.payload["work_ref"],
            "root_authority_digest": self.root_digest,
            "opened": state.opened,
            "closed": state.closed,
            "close_state": state.close_state,
            "close_reason": state.close_reason,
            "budget": {
                "global_model_call_budget": self.budget,
                "consumed_model_calls": state.consumed_calls,
                "reserved_model_calls": state.open_reservations,
                "released_model_calls": state.released_calls,
                "remaining_global_budget": self.remaining_global_budget,
            },
            "children": {
                cid: {
                    "state": child.get("state", ""),
                    "granted_model_calls": int((child.get("derivation") or {}).get("granted_model_calls", 0)),
                    "checker_verdict": (child.get("closure") or {}).get("checker_verdict", ""),
                    "checker_reviewed_commit": (child.get("closure") or {}).get("checker_reviewed_commit", ""),
                    "functional_checkpoint_commit": (child.get("closure") or {}).get("functional_checkpoint_commit", ""),
                    "budget": self.child_budget_projection(cid),
                }
                for cid, child in sorted(state.children.items())
            },
            "consecutive_failures": state.consecutive_failures,
            "max_child_batches": self.payload["max_child_batches"],
            "hard_stops": [{"reason": e.get("reason"), "detail": e.get("detail")} for e in state.hard_stops],
            "events": state.events,
        }

    def write_status(self) -> Path:
        path = self.runtime_dir / "status.json"
        _write_json_atomic(path, self.status_projection())
        return path


def _lock_exclusive(handle) -> bool:
    if tl_job is not None:
        return bool(tl_job.lock_exclusive(handle))
    try:  # pragma: no cover - only when tl_job is unavailable
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (ImportError, OSError):
        return False


def _unlock_exclusive(handle) -> None:
    if tl_job is not None:
        tl_job.unlock_exclusive(handle)
        return
    with contextlib.suppress(ImportError, OSError, ValueError):  # pragma: no cover
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# --------------------------------------------------------------------------- patch-only derivation

def _normalized_action_item(item: dict) -> dict:
    """The fields of a residual finding that decide whether a child may be derived from it.

    What the Checker declared about derivability is part of the finding: a `derivation_blockers`
    flag or a declared `scope_status`/`spec_status` that was dropped on the way to the proposal
    changes the digest, so it cannot be dropped silently. A child proposal has no field for a
    blocker, which means a blocked finding can never digest to a derivable one.
    """
    entry = {"id": str(item.get("id", "")), "category": str(item.get("category", "")),
             "target_role": str(item.get("target_role", "")), "location": str(item.get("location", "")),
             "required_action": str(item.get("required_action", ""))}
    for name in ("scope_status", "spec_status"):
        if item.get(name) is not None:
            entry[name] = str(item[name])
    blockers = sorted({str(flag) for flag in item.get("derivation_blockers") or []})
    if blockers:
        entry["derivation_blockers"] = blockers
    return entry


def unresolved_action_items_digest(items: Iterable[dict]) -> str:
    """Stable digest of the residual findings a child batch is derived from."""
    return digest_of(sorted((_normalized_action_item(item) for item in items), key=lambda entry: entry["id"]))


def _scope_paths(scope: dict) -> list[str]:
    return list(scope.get("required_mutation_targets") or []) + list(scope.get("conditional_mutation_targets") or [])


def _within(path: str, scopes: Iterable[str]) -> bool:
    normalized = Path(str(path)).as_posix().strip("/")
    for scope in scopes:
        candidate = Path(str(scope)).as_posix().strip("/")
        if candidate in {"", "."} or normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def paths_denied(paths: Iterable[str], denied: Iterable[str]) -> list[str]:
    """The given paths that fall under a forbidden or protected path, in order.

    This is the matcher every derivation proof in this module uses, exported so the runtime
    enforces a prohibition with the same semantics it was proven with.
    """
    denied = list(denied)
    return [str(path) for path in paths if _within(str(path), denied)] if denied else []


def _item_locations(item: dict) -> list[str]:
    """Paths an action item points at. A location that names no path cannot be proven in scope."""
    raw = str(item.get("location", ""))
    parts = [chunk.strip() for chunk in re.split(r"[,;\s]+", raw) if chunk.strip()]
    locations = []
    for part in parts:
        path = part.split(":", 1)[0].strip()
        if path and ("/" in path or "." in path):
            locations.append(Path(path).as_posix())
    return locations


def classify_action_item(item: dict, payload: dict, spec_paths: Iterable[str] = ()) -> dict:
    """Compute scope_status and spec_status mechanically, and refuse a contradicting declaration."""
    scope = payload["authorized_write_scope"]
    authorized = _scope_paths(scope)
    forbidden = list(scope.get("forbidden_paths") or [])
    protected = [str(p.get("pattern", "")) for p in payload.get("protected_paths") or []]
    locations = _item_locations(item)
    if not locations:
        scope_status = "unprovable"
    elif any(_within(path, forbidden) or _within(path, protected) for path in locations):
        scope_status = "outside_parent_envelope"
    elif all(_within(path, authorized) for path in locations):
        scope_status = "inside_parent_envelope"
    else:
        scope_status = "outside_parent_envelope"
    spec_status = "changed" if locations and any(_within(path, spec_paths) for path in locations) else "unchanged"
    if str(item.get("category", "")) == "bad_spec":
        spec_status = "changed"  # the finding is about the specification itself, by construction
    computed = {"scope_status": scope_status, "spec_status": spec_status, "locations": locations}
    for name in ("scope_status", "spec_status"):
        declared = item.get(name)
        if declared is not None and str(declared) != computed[name]:
            computed["conflict"] = (
                f"the Checker declared {name}={declared!r} but the envelope proves {computed[name]!r}")
    return computed


def derivation_eligibility(action_items: list[dict], payload: dict, spec_paths: Iterable[str] = ()) -> tuple[bool, list[dict]]:
    """A child batch is derivable only when every residual finding is strictly patch-only."""
    blockers: list[dict] = []
    if not action_items:
        blockers.append({"reason": "intent_gap", "detail": "no residual action item to derive a child batch from"})
        return False, blockers
    for item in action_items:
        item_id = str(item.get("id", "?"))
        category = str(item.get("category", ""))
        target_role = str(item.get("target_role", ""))
        if category in DERIVATION_HARD_STOP_REASONS and category != PATCH_ONLY_CATEGORY:
            blockers.append({"reason": category, "item": item_id,
                             "detail": f"category {category!r} requires a human decision"})
            continue
        if category != PATCH_ONLY_CATEGORY:
            blockers.append({"reason": "intent_gap", "item": item_id,
                             "detail": f"category must be {PATCH_ONLY_CATEGORY!r}, got {category!r}"})
            continue
        if target_role != PATCH_ONLY_TARGET_ROLE:
            blockers.append({"reason": "human" if target_role == "human" else "bad_spec", "item": item_id,
                             "detail": f"target_role must be {PATCH_ONLY_TARGET_ROLE!r}, got {target_role!r}"})
            continue
        for flag in item.get("derivation_blockers") or []:
            blockers.append({"reason": str(flag), "item": item_id,
                             "detail": f"the Checker flagged {flag!r} on this item"})
        computed = classify_action_item(item, payload, spec_paths)
        if "conflict" in computed:
            blockers.append({"reason": "state_integrity", "item": item_id, "detail": computed["conflict"]})
        if computed["scope_status"] != PATCH_ONLY_SCOPE_STATUS:
            blockers.append({"reason": "scope_expansion", "item": item_id,
                             "detail": f"scope_status is {computed['scope_status']!r} for {computed['locations']}"})
        if computed["spec_status"] != PATCH_ONLY_SPEC_STATUS:
            blockers.append({"reason": "bad_spec", "item": item_id,
                             "detail": f"spec_status is {computed['spec_status']!r}"})
    return not blockers, blockers


# --------------------------------------------------------------------------- child proposal

def derive_child_proposal(
    *,
    authority: "StoryAuthority",
    child_batch_id: str,
    action_items: list[dict],
    previous_child_id: str | None = None,
    model_call_budget: int | None = None,
    required_mutation_targets: Iterable[str] | None = None,
    conditional_mutation_targets: Iterable[str] | None = None,
    governance_base_commit: str,
    story_baseline_commit: str,
) -> dict:
    """Formulate the next child deterministically from the parent envelope and the residual findings.

    Targets the findings actually name become `required`; everything the parent authorized stays
    available as `conditional`. A path the parent authorized only conditionally may become required
    here, which is exactly what a factual Checker finding does to it.
    """
    payload = authority.payload
    state = authority.refold()
    scope = payload["authorized_write_scope"]
    if required_mutation_targets is None:
        named: list[str] = []
        for item in action_items:
            named.extend(_item_locations(item))
        authorized = _scope_paths(scope)
        required = sorted({path for path in named if _within(path, authorized)})
        required_mutation_targets = required or sorted(scope.get("required_mutation_targets") or [])
    required_list = sorted(set(required_mutation_targets))
    if conditional_mutation_targets is None:
        conditional_mutation_targets = [p for p in _scope_paths(scope) if p not in required_list]
    previous_closure = state.closure_of(previous_child_id) if previous_child_id else None
    checkpoint = None
    if previous_closure:
        checkpoint = {
            "commit": previous_closure["checker_reviewed_commit"],
            "tree": previous_closure["checker_reviewed_tree"],
            "child_batch_id": previous_closure["child_batch_id"],
        }
    granted = int(model_call_budget) if model_call_budget is not None else authority.remaining_global_budget
    proposal = {
        "schema_version": 1,
        "child_batch_id": child_batch_id,
        "authority_id": authority.authority_id,
        "parent_child_batch_id": previous_child_id,
        "work_ref": payload["work_ref"],
        "authorized_spec_revision": payload["authorized_spec_revision"],
        "authorized_spec_sha256": payload["authorized_spec_sha256"],
        "required_mutation_targets": required_list,
        "conditional_mutation_targets": sorted(set(conditional_mutation_targets)),
        "forbidden_paths": sorted(set(scope.get("forbidden_paths") or [])),
        "protected_paths": list(payload.get("protected_paths") or []),
        "allowed_effects": dict(payload["allowed_effects"]),
        "model_call_budget": max(1, granted),
        "functional_parent_checkpoint": checkpoint,
        "derived_from_action_items": [
            {"id": str(item.get("id", "")), "category": str(item.get("category", "")),
             "target_role": str(item.get("target_role", "")), "location": str(item.get("location", "")),
             "required_action": str(item.get("required_action", "")),
             **({"severity": str(item["severity"])} if item.get("severity") else {}),
             # What the Checker declared travels with the finding, so the proof can be recomputed
             # from the registered proposal alone and a contradiction stays a contradiction.
             **{name: str(item[name]) for name in ("scope_status", "spec_status") if item.get(name) is not None}}
            for item in sorted(action_items, key=lambda entry: str(entry.get("id", "")))
        ],
        "lineage": {"governance_base_commit": governance_base_commit, "story_baseline_commit": story_baseline_commit},
    }
    valid, errors = validate_against_schema_file(proposal, CHILD_PROPOSAL_SCHEMA)
    if not valid:
        raise Refusal(f"derived child proposal violates its schema: {errors}")
    return proposal


# One proof, written once. `verify_derivation` (when a child is formulated), `record_child_derived`
# (when it is registered) and `bind_child_batch` (when a runtime is about to execute it) all run the
# generators below, so the library and the runtime cannot drift into proving different things.
# Each yields `(check, ok, hard_stop_reason, detail, evidence)` lazily: the caller stops at the first
# failure, so a later check never reads a field an earlier one has not already proven to exist.

def envelope_checks(payload: dict, proposal: Any) -> Iterable[tuple]:
    """Stateless proof that a child proposal is a subset of the authorized envelope."""
    valid, errors = validate_against_schema_file(proposal, CHILD_PROPOSAL_SCHEMA)
    yield "child_proposal_schema", valid, "state_integrity", str(errors), {}

    yield ("authority_binding",
           proposal["authority_id"] == payload["authority_id"] and proposal["work_ref"] == payload["work_ref"],
           "authority_missing_or_ambiguous", f"child binds {proposal['authority_id']}/{proposal['work_ref']}", {})

    yield ("spec_immutable",
           proposal["authorized_spec_sha256"] == payload["authorized_spec_sha256"]
           and proposal["authorized_spec_revision"] == payload["authorized_spec_revision"],
           "unexpected_revision_drift",
           f"child declares spec {proposal['authorized_spec_sha256'][:16]} but the authority froze "
           f"{payload['authorized_spec_sha256'][:16]}", {})

    scope = payload["authorized_write_scope"]
    authorized_union = _scope_paths(scope)
    child_union = _proposal_targets(proposal)
    outside = sorted({path for path in child_union if not _within(path, authorized_union)})
    # §2.4: the union is what must be contained. A path the parent authorized conditionally may
    # legitimately become required in the child after a factual Checker finding.
    yield ("scope_subset", not outside, "scope_expansion", f"paths outside the parent envelope: {outside}",
           {"outside": outside})

    parent_forbidden = set(scope.get("forbidden_paths") or [])
    child_forbidden = set(proposal["forbidden_paths"])
    yield ("forbidden_monotonic", parent_forbidden <= child_forbidden, "scope_expansion",
           f"the child dropped forbidden path(s) {sorted(parent_forbidden - child_forbidden)}", {})

    # A target inside a forbidden path is refused here. The converse, a forbidden path nested
    # inside a broad target, is legitimate and stays forbidden: `bind_child_batch` hands it to the
    # runtime as executable policy.
    collisions = sorted({path for path in child_union if _within(path, child_forbidden)})
    yield ("no_forbidden_target", not collisions, "scope_expansion",
           f"the child authorizes path(s) it also forbids: {collisions}", {})

    protected_violations = assert_protected_paths_monotonic(
        payload.get("protected_paths") or [], proposal.get("protected_paths") or [])
    yield ("protected_paths_monotonic", not protected_violations, "protected_path_violation",
           canonical_json(protected_violations), {"violations": protected_violations})

    expanded = sorted(key for key in EFFECT_KEYS
                      if proposal["allowed_effects"].get(key) and not payload["allowed_effects"].get(key))
    yield ("effects_subset", not expanded, "effect_expansion",
           f"the child enables effect(s) the parent denied: {expanded}", {"effects": expanded})

    granted = int(proposal["model_call_budget"])
    yield ("budget_within_envelope", granted <= int(payload["global_model_call_budget"]),
           "model_call_budget_exhausted",
           f"the child requests {granted} model calls but the whole Story was authorized "
           f"{payload['global_model_call_budget']}", {"requested": granted})


def lineage_checks(state: "AuthorityState", proposal: dict) -> Iterable[tuple]:
    """Proof of where a child stands in the Story, from the journal alone.

    Everything here is decided by journal order, so it answers the same way when the child is
    formulated, when it is registered and every time a runtime binds to it afterwards.
    """
    child_batch_id = proposal["child_batch_id"]
    previous_id = proposal.get("parent_child_batch_id")
    checkpoint = proposal.get("functional_parent_checkpoint")
    predecessors = state.predecessors_of(child_batch_id)

    if not previous_id:
        # Only the first child of a Story has no parent. A later one that declared none would
        # skip the patch-only proof, the findings recorded at closure and the inherited checkpoint.
        yield ("first_child_is_the_only_root", not predecessors, "state_integrity",
               f"child batch(es) {predecessors} already exist under this authority; a later child must declare "
               "the closed parent it is derived from", {"predecessors": predecessors})
        yield ("first_child_has_no_checkpoint", checkpoint is None, "state_integrity",
               "the first child under an authority inherits no functional checkpoint", {})
        return

    yield ("parent_child_is_registered",
           previous_id in predecessors and state.derivation_of(previous_id) is not None, "state_integrity",
           f"parent_child_batch_id {previous_id!r} was never derived under this authority before "
           f"{child_batch_id!r}", {"parent_child_batch_id": previous_id})

    closure = state.closure_of(previous_id)
    parent_state = (state.children.get(previous_id) or {}).get("state", "")
    yield ("parent_child_is_closed", closure is not None, "state_integrity",
           f"parent child batch {previous_id} is {parent_state or 'unknown'}, not closed; a child is derived "
           "only from what a Checker reviewed", {"parent_state": parent_state})

    latest = state.latest_closed(predecessors)
    yield ("parent_is_the_latest_closed_child", latest == previous_id, "state_integrity",
           f"the functional lineage continues from {latest}, the last child a Checker reviewed, not from "
           f"{previous_id}", {"latest_closed_child": latest})

    yield ("parent_requested_changes", closure.get("checker_verdict") == "changes_requested", "intent_gap",
           f"parent child batch {previous_id} closed {closure.get('checker_verdict')!r}; there is no residual "
           "finding to derive a child from", {})

    expected = {"commit": closure["checker_reviewed_commit"], "tree": closure["checker_reviewed_tree"],
                "child_batch_id": closure["child_batch_id"]}
    yield ("functional_checkpoint_inherited", checkpoint == expected, "state_integrity",
           f"the child must start exactly at the unmerged commit the previous Checker reviewed "
           f"({expected['commit'][:12]}), got {(checkpoint or {}).get('commit', 'none')}",
           {"expected": expected, "observed": checkpoint})

    yield ("unresolved_items_match_closure",
           closure.get("unresolved_action_items_digest")
           == unresolved_action_items_digest(proposal["derived_from_action_items"]),
           "state_integrity", "the residual findings differ from the ones recorded when the parent closed", {})


def derivation_chain(state: "AuthorityState", root_digest: str, proposal: dict) -> dict:
    """The digests a child's proof must carry, recomputed from the journal. Call after
    `lineage_checks` passed: a declared parent is then known to be registered."""
    previous_id = proposal.get("parent_child_batch_id")
    if not previous_id:
        return {"parent_authority_digest": root_digest, "parent_batch_digest": ""}
    parent = state.derivation_of(previous_id) or {}
    return {"parent_authority_digest": parent.get("derivation_proof_digest", ""),
            "parent_batch_digest": parent.get("child_proposal_digest", "")}


def patch_only_check(items: list[dict], payload: dict, spec_paths: Iterable[str]) -> tuple:
    eligible, blockers = derivation_eligibility(items, payload, spec_paths)
    reason = "state_integrity"
    if not eligible:
        reason = next((b["reason"] for b in blockers if b["reason"] in DERIVATION_HARD_STOP_REASONS),
                      blockers[0]["reason"])
    return "patch_only_findings", eligible, reason, canonical_json(blockers), {"blockers": blockers}


def _proposal_targets(proposal: dict) -> list[str]:
    return list(proposal["required_mutation_targets"]) + list(proposal["conditional_mutation_targets"])


def _proof_digest(proof: dict) -> str:
    return digest_of({key: value for key, value in proof.items() if key != "derivation_proof_digest"})


def verify_derivation(
    authority: "StoryAuthority",
    child_proposal: dict,
    *,
    action_items: list[dict] | None = None,
    spec_paths: Iterable[str] = (),
    now: str | None = None,
) -> dict:
    """Prove the child batch is a strict, verifiable subset of the authorized envelope.

    This is the only thing that gives a derived batch authority. It never produces a signature;
    it produces a chain of digests anchored in the one authorization the operator did issue.
    """
    payload = authority.payload
    state = authority.refold()
    checks: list[dict] = []

    def check(name: str, ok: bool, reason: str, detail: str = "", **evidence: Any) -> None:
        checks.append({"check": name, "result": "pass" if ok else "fail"})
        if not ok:
            authority.hard_stop(reason, f"{name}: {detail}", check=name, **evidence)

    for name, ok, reason, detail, evidence in envelope_checks(payload, child_proposal):
        check(name, ok, reason, detail, **evidence)

    check("authority_open", not state.closed, "authority_missing_or_ambiguous",
          f"authority already closed as {state.close_state}")

    remaining = authority.remaining_global_budget
    granted = int(child_proposal["model_call_budget"])
    check("budget_projection", granted <= remaining, "model_call_budget_exhausted",
          f"the child requests {granted} model calls but the authority has {remaining} left",
          requested=granted, remaining=remaining)

    child_count = len(state.children) + (0 if child_proposal["child_batch_id"] in state.children else 1)
    check("max_child_batches", child_count <= int(payload["max_child_batches"]), "max_child_batches_exhausted",
          f"{child_count} child batches exceeds max_child_batches {payload['max_child_batches']}")

    active = [cid for cid in state.active_children() if cid != child_proposal["child_batch_id"]]
    check("max_active_child_batches", len(active) < MAX_ACTIVE_CHILD_BATCHES, "state_integrity",
          f"child batch(es) {active} are still active; AUTO_STORY v1 runs one at a time")

    check("wall_clock_deadline", (now or now_iso()) <= payload["wall_clock_deadline"],
          "wall_clock_deadline_exceeded",
          f"now {now or now_iso()} is past the authorized deadline {payload['wall_clock_deadline']}")

    check("consecutive_failures", state.consecutive_failures < int(payload["max_consecutive_failed_batches"]),
          "consecutive_batch_failures_exhausted",
          f"{state.consecutive_failures} consecutive child batches without progress")

    previous_id = child_proposal.get("parent_child_batch_id")
    # A child with a parent exists only because of the parent's residual findings, so it cannot
    # be verified without them. Only the first child of a Story may be verified with none.
    check("residual_findings_supplied", action_items is not None or not previous_id, "intent_gap",
          f"child of {previous_id} was submitted without the residual findings it is derived from")
    unresolved_digest = ""
    if action_items is not None:
        name, ok, reason, detail, evidence = patch_only_check(action_items, payload, spec_paths)
        check(name, ok, reason, detail, **evidence)
        unresolved_digest = unresolved_action_items_digest(action_items)
        declared_digest = unresolved_action_items_digest(child_proposal["derived_from_action_items"])
        check("derived_from_findings", declared_digest == unresolved_digest, "state_integrity",
              "the child is not derived from the residual findings it claims")

    for name, ok, reason, detail, evidence in lineage_checks(state, child_proposal):
        check(name, ok, reason, detail, **evidence)

    proof = {
        "schema_version": 1,
        "authority_id": authority.authority_id,
        "work_ref": payload["work_ref"],
        "child_batch_id": child_proposal["child_batch_id"],
        "parent_child_batch_id": previous_id,
        "root_authority_digest": authority.root_digest,
        **derivation_chain(state, authority.root_digest, child_proposal),
        "child_proposal_digest": digest_of(child_proposal),
        "functional_parent_checkpoint": child_proposal.get("functional_parent_checkpoint"),
        "unresolved_action_items_digest": unresolved_digest,
        "granted_model_calls": granted,
        "checks": checks,
    }
    proof["derivation_proof_digest"] = _proof_digest(proof)
    return proof


def registered_derivation_checks(
    authority: "StoryAuthority",
    state: "AuthorityState",
    child_batch_id: str,
    proposal: Any,
    proof: Any,
    *,
    spec_paths: Iterable[str] = (),
) -> Iterable[tuple]:
    """Re-prove a derivation from its two documents, trusting neither.

    Used when the derivation is registered and again every time a runtime binds a batch to it.
    Every digest is recomputed from the document it claims to digest, the chain is recomputed
    from the journal, and the envelope and lineage proofs are the same generators
    `verify_derivation` ran. Only the checks that depend on the moment (remaining budget, active
    children, deadline, failure streak) are left to `verify_derivation`: they were true when the
    child was derived and the ledger enforces them again on every reservation.
    """
    yield ("derivation_documents_present", isinstance(proposal, dict) and isinstance(proof, dict),
           "state_integrity", f"child batch {child_batch_id!r} has no registered child proposal and derivation "
           "proof to recompute", {})

    for item in envelope_checks(authority.payload, proposal):
        yield item

    yield ("proposal_names_this_child", proposal["child_batch_id"] == child_batch_id, "state_integrity",
           f"the registered proposal is for {proposal['child_batch_id']!r}, not {child_batch_id!r}", {})

    recomputed = digest_of(proposal)
    yield ("child_proposal_digest_recomputed", proof.get("child_proposal_digest") == recomputed, "state_integrity",
           f"the child proposal digests to {recomputed} but its proof binds {proof.get('child_proposal_digest')}",
           {"recomputed": recomputed})

    recomputed_proof = _proof_digest(proof)
    yield ("derivation_proof_digest_recomputed", proof.get("derivation_proof_digest") == recomputed_proof,
           "state_integrity",
           f"the derivation proof digests to {recomputed_proof} but declares {proof.get('derivation_proof_digest')}",
           {"recomputed": recomputed_proof})

    bound = {"authority_id": authority.authority_id, "work_ref": authority.payload["work_ref"],
             "child_batch_id": child_batch_id, "parent_child_batch_id": proposal.get("parent_child_batch_id"),
             "root_authority_digest": authority.root_digest,
             "functional_parent_checkpoint": proposal.get("functional_parent_checkpoint"),
             "granted_model_calls": int(proposal["model_call_budget"])}
    unbound = sorted(key for key, value in bound.items() if proof.get(key) != value)
    yield ("proof_binds_this_derivation", not unbound, "state_integrity",
           f"the derivation proof disagrees with the authority or the proposal on {unbound}", {"fields": unbound})

    results = proof.get("checks")
    failed = (["checks"] if not isinstance(results, list) or not results else
              [str(entry.get("check")) for entry in results
               if not isinstance(entry, dict) or entry.get("result") != "pass"])
    yield ("proof_records_only_passes", not failed, "state_integrity",
           f"the derivation proof does not record a complete passing verification: {failed}", {})

    for item in lineage_checks(state, proposal):
        yield item

    chain = derivation_chain(state, authority.root_digest, proposal)
    broken = sorted(key for key, value in chain.items() if proof.get(key) != value)
    yield ("derivation_chain_recomputed", not broken, "state_integrity",
           f"the proof's {broken} do not match the chain the journal records", {"expected": chain})

    items = proposal["derived_from_action_items"]
    acceptable = {unresolved_action_items_digest(items)}
    if proposal.get("parent_child_batch_id"):
        yield patch_only_check(items, authority.payload, spec_paths)
    else:
        acceptable.add("")  # the first child of a Story may be verified with no residual finding at all
    yield ("proof_binds_the_findings", proof.get("unresolved_action_items_digest") in acceptable,
           "state_integrity", "the proof was computed over different residual findings than the proposal carries",
           {})


# --------------------------------------------------------------------------- executable binding

# A batch states its effects in the runtime's vocabulary; the envelope authorized them in its own.
# An effect with no counterpart here was never put in front of the operator, so it is not granted.
BATCH_EFFECT_TO_ENVELOPE = {
    "local_write": "local_write", "local_commit": "local_commit", "local_merge": "local_merge",
    "pull_request": "pull_request", "push": "push", "tag": "tag", "release": "release",
    "pull_request_merge": "merge",
}


def executable_batch_checks(payload: dict, proposal: dict, batch: dict, units: list[dict]) -> Iterable[tuple]:
    """Proof that the batch about to run is the child that was derived, and not more than it."""
    outside_story = sorted({str(unit["work_ref"]) for unit in units
                            if not work_ref_within_story(payload, str(unit["work_ref"]))})
    yield ("batch_within_story", not outside_story, "next_story_without_authorization",
           f"this authority covers Story {payload['work_ref']!r}; unit(s) {outside_story} require a new explicit "
           "human authorization", {"authorized_work_ref": payload["work_ref"], "requested": outside_story})

    drifted = sorted(str(unit["work_ref"]) for unit in units
                     if unit.get("spec_sha256") != proposal["authorized_spec_sha256"])
    yield ("batch_spec_is_the_authorized_spec", not drifted, "unexpected_revision_drift",
           f"unit(s) {drifted} are specified by a document that does not digest to the authorized "
           f"{proposal['authorized_spec_sha256'][:16]}", {"units": drifted})

    targets = _proposal_targets(proposal)
    denied = list(proposal["forbidden_paths"]) + [str(p.get("pattern", "")) for p in proposal["protected_paths"]]
    outside = sorted({f"{unit['work_ref']}:{path}" for unit in units for path in unit.get("scope_paths") or []
                      if not _within(path, targets)})
    yield ("batch_scope_within_child", not outside, "scope_expansion",
           f"scope_paths outside the derived child's mutation targets: {outside}", {"outside": outside})
    inside_denied = sorted({f"{unit['work_ref']}:{path}" for unit in units for path in unit.get("scope_paths") or []
                            if _within(path, denied)})
    yield ("batch_scope_avoids_forbidden", not inside_denied, "scope_expansion",
           f"scope_paths inside a forbidden or protected path: {inside_denied}", {"inside": inside_denied})

    effects = (batch.get("authorization") or {}).get("permitted_effects") or {}
    expanded = sorted(key for key, enabled in effects.items() if enabled and not proposal["allowed_effects"].get(
        BATCH_EFFECT_TO_ENVELOPE.get(key, ""), False))
    yield ("batch_effects_within_child", not expanded, "effect_expansion",
           f"the batch enables effect(s) the derived child was not granted: {expanded}", {"effects": expanded})

    ceiling = (batch.get("budget") or {}).get("max_model_calls")
    granted = int(proposal["model_call_budget"])
    yield ("batch_budget_within_grant",
           isinstance(ceiling, int) and not isinstance(ceiling, bool) and 1 <= ceiling <= granted,
           "model_call_budget_exhausted",
           f"the batch budgets {ceiling!r} model calls but the derived child was granted {granted}",
           {"requested": ceiling, "granted": granted})


def bind_child_batch(authority: "StoryAuthority", batch: dict, units: list[dict]) -> dict:
    """Bind an executable AUTO_STORY batch to the derivation registered for exactly `batch['id']`.

    Runs under the authority lease, before any worker. The digests a batch file declares are
    claims; what is proven here is that the Story Authority journal registered a child proposal
    and a derivation proof for this batch id, that both still digest to what was registered and
    to what the batch declares, that the derivation still holds against the immutable envelope
    and the journal, and that the batch asks for nothing the derived child was not given.

    `units` is one `{"work_ref", "scope_paths", "spec_sha256", "spec_path"}` per frozen unit.
    Returns the verified proposal and proof, plus `do_not_touch`: the forbidden and protected
    paths the runtime must enforce as policy even when they sit inside a broad scope path.
    """
    authority._require_lease()
    state = authority.refold()
    child_batch_id = str(batch.get("id", ""))
    declared = batch.get("authorization") or {}
    checks: list[dict] = []

    def check(name: str, ok: bool, reason: str, detail: str = "", **evidence: Any) -> None:
        checks.append({"check": name, "result": "pass" if ok else "fail"})
        if not ok:
            authority.hard_stop(reason, f"{name}: {detail}", check=name, child_batch_id=child_batch_id, **evidence)

    check("batch_names_this_authority", declared.get("story_authority_id") == authority.authority_id
          and declared.get("root_authority_digest") == authority.root_digest, "authority_missing_or_ambiguous",
          f"batch {child_batch_id} declares authority {declared.get('story_authority_id')!r} / "
          f"{str(declared.get('root_authority_digest'))[:16]}, not {authority.authority_id} / "
          f"{authority.root_digest[:16]}")

    registered = state.derivation_of(child_batch_id)
    check("child_is_registered", registered is not None, "authority_missing_or_ambiguous",
          f"no child_derived event exists for batch {child_batch_id!r} under story authority "
          f"{authority.authority_id}; a batch that was not derived has no authority")
    proposal, proof = registered.get("child_proposal"), registered.get("derivation_proof")

    spec_paths = sorted({str(unit["spec_path"]) for unit in units if unit.get("spec_path")})
    for name, ok, reason, detail, evidence in registered_derivation_checks(
            authority, state, child_batch_id, proposal, proof, spec_paths=spec_paths):
        check(name, ok, reason, detail, **evidence)

    tampered = sorted(key for key in DERIVATION_DIGEST_KEYS if registered.get(key) != proof.get(key))
    check("journal_digests_match_documents", not tampered, "state_integrity",
          f"the child_derived event and the documents it carries disagree on {tampered}", fields=tampered)

    forged = sorted(key for key in ("child_proposal_digest", "derivation_proof_digest")
                    if declared.get(key) != registered.get(key))
    check("batch_declares_registered_digests", not forged, "state_integrity",
          f"batch {child_batch_id} declares {forged} that are not the ones registered for it", fields=forged)

    for name, ok, reason, detail, evidence in executable_batch_checks(authority.payload, proposal, batch, units):
        check(name, ok, reason, detail, **evidence)

    return {
        "child_batch_id": child_batch_id,
        "child_proposal": proposal,
        "derivation_proof": proof,
        "functional_parent_checkpoint": proposal.get("functional_parent_checkpoint"),
        "do_not_touch": sorted({Path(str(path)).as_posix() for path in (
            list(proposal["forbidden_paths"]) + [str(p.get("pattern", "")) for p in proposal["protected_paths"]])
            if str(path).strip()}),
        "checks": checks,
    }


# --------------------------------------------------------------------------- functional lineage

def _git(repo: str | Path, *args: str, timeout: float = 120) -> tuple[int, str, str]:
    record = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, check=False, timeout=timeout)
    return record.returncode, record.stdout.strip(), record.stderr.strip()


def verify_functional_checkpoint(repo: str | Path, checkpoint: dict) -> dict:
    """Prove, before the Maker touches anything, that this worktree is exactly the inherited commit."""
    commit = str((checkpoint or {}).get("commit", ""))
    tree = str((checkpoint or {}).get("tree", ""))
    if not _COMMIT_RE.match(commit) or not _COMMIT_RE.match(tree):
        raise HardStop("state_integrity",
                       f"the functional checkpoint is missing or ambiguous: {checkpoint!r}")
    code, _out, err = _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if code != 0:
        raise HardStop("state_integrity",
                       f"functional checkpoint {commit[:12]} is not present in this repository: {err[:200]}",
                       commit=commit)
    code, head, _err = _git(repo, "rev-parse", "HEAD")
    if code != 0 or head != commit:
        raise HardStop("unexpected_tree_state",
                       f"HEAD is {head[:12] or 'unknown'} but the derived child must start at {commit[:12]}",
                       head=head, expected=commit)
    code, head_tree, _err = _git(repo, "rev-parse", f"{commit}^{{tree}}")
    if code != 0 or head_tree != tree:
        raise HardStop("unexpected_tree_state",
                       f"commit {commit[:12]} carries tree {head_tree[:12] or 'unknown'}, not the recorded "
                       f"functional checkpoint tree {tree[:12]}",
                       observed_tree=head_tree, expected_tree=tree)
    code, dirty, _err = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if code != 0 or dirty:
        raise HardStop("unexpected_tree_state",
                       f"the working tree is not clean at the functional checkpoint: {dirty[:300]}",
                       dirty=dirty[:300])
    return {"commit": commit, "tree": tree, "verified": True}


def cumulative_review_range(story_baseline_commit: str, integration_candidate_commit: str) -> str:
    """The next Checker reviews the whole Story so far, not only the current child's patch."""
    return f"{story_baseline_commit}..{integration_candidate_commit}"


def assert_protected_paths_intact(repo: str | Path, payload: dict, *, dirty_paths: list[str] | None = None) -> list[dict]:
    """Verify the authority's protected paths against the tree. Any violation is a hard stop."""
    violations = verify_protected_paths(repo, payload.get("protected_paths") or [], dirty_paths=dirty_paths)
    if violations:
        raise HardStop("protected_path_violation", canonical_json(violations), violations=violations)
    return violations


# --------------------------------------------------------------------------- story boundary (T028, §2.9)

def work_ref_within_story(payload: dict, work_ref: str) -> bool:
    """A unit belongs to the Story when it is the Story itself or a reference nested under it."""
    authorized = str(payload["work_ref"])
    candidate = str(work_ref)
    return candidate == authorized or candidate.startswith(authorized + "/")


def assert_story_boundary(payload: dict, requested_work_ref: str) -> None:
    """AUTO_STORY covers one Story. The next one in the backlog needs its own authorization."""
    if not work_ref_within_story(payload, requested_work_ref):
        raise HardStop(
            "next_story_without_authorization",
            f"this authority covers Story {payload['work_ref']!r}; starting {requested_work_ref!r} requires a new "
            "explicit human authorization",
            authorized_work_ref=payload["work_ref"], requested_work_ref=requested_work_ref)


def assert_batch_within_story(payload: dict, work_refs: Iterable[str]) -> None:
    """Every unit of a child batch must belong to the one authorized Story."""
    for work_ref in sorted(set(work_refs)):
        assert_story_boundary(payload, work_ref)


def assert_merge_authority(payload: dict, receipt: Any, *, trust_root: Any = None, expected_repo: str | None = None) -> Any:
    """`allowed_effects.merge` is a capability flag, never a bypass of the T028 authority gate."""
    if not payload["allowed_effects"].get("merge"):
        raise HardStop("effect_expansion", "the authority does not allow the merge effect")
    if receipt is None:
        raise HardStop("authority_missing_or_ambiguous",
                       "a merge on a protected branch requires an out-of-band T028 authority receipt")
    if not getattr(receipt, "is_confirmed", False):
        raise HardStop("authority_missing_or_ambiguous",
                       f"T028 merge authority receipt is {getattr(receipt, 'status', 'absent')}: "
                       f"{getattr(receipt, 'reason', '')}")
    authentic = getattr(receipt, "is_authentic", None)
    if callable(authentic) and not authentic(trust_root, expected_repo):
        raise HardStop("authority_missing_or_ambiguous",
                       "the T028 merge authority receipt did not verify against the platform trust root")
    return receipt


# --------------------------------------------------------------------------- cognitive call barrier (§2.8)

_POSIX_SHIM = """#!/bin/sh
printf '%s\\n' "{message} (blocked: {name})" 1>&2
exit {code}
"""
_WINDOWS_SHIM = """@echo off
1>&2 echo {message} (blocked: {name})
exit /b {code}
"""


def install_cognitive_barrier(directory: str | Path, *, names: Iterable[str] = COGNITIVE_CLIS) -> dict:
    """Write deterministic refusal shims that shadow every cognitive CLI on the worker PATH."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for name in names:
        if os.name == "nt":
            shim = target / f"{name}.cmd"
            shim.write_text(_WINDOWS_SHIM.format(message=BARRIER_MESSAGE, name=name, code=BARRIER_EXIT_CODE),
                            encoding="utf-8", newline="\r\n")
        else:
            shim = target / name
            shim.write_text(_POSIX_SHIM.format(message=BARRIER_MESSAGE, name=name, code=BARRIER_EXIT_CODE),
                            encoding="utf-8", newline="\n")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(shim.name)
    return {"directory": target.as_posix(), "installed": sorted(installed), "exit_code": BARRIER_EXIT_CODE}


def barrier_path(directory: str | Path, base_path: str | None = None) -> str:
    """The barrier goes first, so a real CLI further down the PATH is never the one that resolves."""
    base = base_path if base_path is not None else os.environ.get("PATH", "")
    return os.pathsep.join([str(Path(directory)), base]) if base else str(Path(directory))


def barrier_worker_env(env: dict, directory: str | Path) -> dict:
    worker = dict(env)
    worker["PATH"] = barrier_path(directory, worker.get("PATH", ""))
    worker["TL_COGNITIVE_CALL_BARRIER"] = str(Path(directory))
    return worker


def probe_cognitive_barrier(directory: str | Path, *, names: Iterable[str] = COGNITIVE_CLIS,
                            env: dict | None = None) -> dict:
    """Prove mechanically that a direct invocation fails before it can reach any provider.

    The probe runs in the environment the worker will actually get, resolves each name through that
    PATH, and executes what it finds. If the platform cannot make the barrier win PATH resolution,
    or the shim does not fail deterministically, the capability is `unavailable` and AUTO_STORY
    refuses to start. There is no degraded mode: a barrier that might not hold is not a barrier.

    Known limitation, declared rather than papered over: the barrier shadows *name* resolution.
    A worker that already knows the absolute path of a real cognitive CLI can still execute it,
    which is why `budgeted_model_dispatch` remains the control-plane obligation and the barrier is
    a second line of defence, not the only one.
    """
    target = Path(directory)
    worker_env = dict(env) if env is not None else dict(os.environ)
    worker_env["PATH"] = barrier_path(target, worker_env.get("PATH", os.environ.get("PATH", "")))
    checks: list[dict] = []
    available = True
    for name in names:
        resolved = shutil.which(name, path=worker_env["PATH"])
        shadowed = bool(resolved) and Path(resolved).resolve().parent == target.resolve()
        record: dict[str, Any] = {"cli": name, "resolved": resolved or "", "shadows_real_cli": shadowed}
        if not shadowed:
            record["reason"] = "the barrier directory does not win PATH resolution for this name"
            available = False
            checks.append(record)
            continue
        try:
            run = subprocess.run([resolved], capture_output=True, text=True, check=False, timeout=30,
                                 env=worker_env)
            record["exit_code"] = run.returncode
            record["blocked"] = run.returncode == BARRIER_EXIT_CODE
            record["stderr"] = run.stderr.strip()[:200]
        except (OSError, subprocess.SubprocessError) as exc:
            # A shim that cannot be executed at all still refuses the call, but it refuses for a
            # reason the platform chose rather than one this barrier proved. That is not enough.
            record["blocked"] = False
            record["reason"] = f"the shim could not be executed: {exc}"
        if not record.get("blocked"):
            available = False
        checks.append(record)
    return {"capability": "available" if available else "unavailable", "barrier_directory": target.as_posix(),
            "expected_exit_code": BARRIER_EXIT_CODE, "checks": checks,
            "limitation": "name resolution only: an absolute path to a real cognitive CLI is not shadowed"}


def require_cognitive_barrier(directory: str | Path, *, names: Iterable[str] = COGNITIVE_CLIS,
                              env: dict | None = None) -> dict:
    """Install and prove the barrier, or refuse to initialize AUTO_STORY. Never degrade silently."""
    install_cognitive_barrier(directory, names=names)
    report = probe_cognitive_barrier(directory, names=names, env=env)
    if report["capability"] != "available":
        raise HardStop(
            "cognitive_call_barrier_unavailable",
            "this environment cannot mechanically block direct cognitive CLI invocation, so AUTO_STORY "
            "will not start: " + canonical_json(report["checks"]),
            report=report)
    return report


# --------------------------------------------------------------------------- budgeted dispatch bridge

class AuthorityDispatchContext:
    """Duck-typed bridge handed to `tl_job.budgeted_model_dispatch`.

    The authority journal is written first and settled last, so the child batch ledger can only
    ever be a projection of a charge that already exists globally. A crash between the two leaves
    a reservation that the authority still owns, never a call charged twice or charged nowhere.
    """

    def __init__(self, authority: StoryAuthority, child_batch_id: str, logical_call_id: str,
                 global_attempt_id: str | None = None):
        self.authority = authority
        self.child_batch_id = child_batch_id
        self.logical_call_id = logical_call_id
        self.global_attempt_id = global_attempt_id or authority.next_global_attempt_id(logical_call_id)

    def reserve(self, *, role: str = "", phase: str = "", payload_digest: str = "", requested_calls: int = 1) -> str:
        self.authority.reserve_call(
            logical_call_id=self.logical_call_id, global_attempt_id=self.global_attempt_id,
            child_batch_id=self.child_batch_id, role=role, phase=phase, payload_digest=payload_digest,
            requested_calls=requested_calls)
        return self.global_attempt_id

    def consume(self, *, outcome: str = "consumed", receipt: dict | None = None) -> str:
        self.authority.consume_call(self.global_attempt_id, outcome=outcome, receipt=receipt)
        return self.global_attempt_id

    def release(self, *, proof: str) -> str:
        self.authority.release_call(self.global_attempt_id, proof=proof)
        return self.global_attempt_id

    def remaining(self) -> int:
        return self.authority.remaining_global_budget


def budgeted_authority_dispatch(
    authority: StoryAuthority,
    *,
    child_batch_id: str,
    logical_call_id: str,
    role: str,
    phase: str,
    dispatch: Callable[[str], dict],
    payload_digest: str = "",
    requested_calls: int = 1,
    global_attempt_id: str | None = None,
) -> dict:
    """Reserve globally, dispatch once, settle globally. The only path a model call may take.

    `dispatch(global_attempt_id)` must return a record with `state`:
      - `released`  the transport proved nothing started; the slot is returned unspent
      - `ambiguous` the outcome cannot be proven; the slot is charged conservatively
      - anything else: the call happened and is charged.
    """
    context = AuthorityDispatchContext(authority, child_batch_id, logical_call_id, global_attempt_id)
    prior = authority.refold().attempts.get(context.global_attempt_id)
    if prior is not None and prior["state"] != "reserved":
        # Replaying a settled attempt after a crash re-reads the ledger; it never calls the provider
        # again and never moves the budget again.
        return {"global_attempt_id": context.global_attempt_id, "logical_call_id": logical_call_id,
                "child_batch_id": child_batch_id, "record": None, "replayed": True,
                "attempt_state": prior["state"], "remaining_global_budget": authority.remaining_global_budget}
    context.reserve(role=role, phase=phase, payload_digest=payload_digest, requested_calls=requested_calls)
    try:
        record = dispatch(context.global_attempt_id)
    except Exception as exc:  # the call may have reached the provider: never released on doubt
        context.consume(outcome="ambiguous", receipt={"error": str(exc)[:300]})
        raise
    state = str((record or {}).get("state", ""))
    if state == "released":
        context.release(proof=str((record or {}).get("proof") or "transport proved the dispatch never started"))
    elif state == "ambiguous":
        context.consume(outcome="ambiguous", receipt={"detail": str((record or {}).get("detail", ""))[:300]})
    else:
        context.consume(outcome="consumed", receipt={"state": state})
    return {"global_attempt_id": context.global_attempt_id, "logical_call_id": logical_call_id,
            "child_batch_id": child_batch_id, "record": record,
            "remaining_global_budget": authority.remaining_global_budget}


# --------------------------------------------------------------------------- CLI

def _cmd_present(args) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    print(json.dumps(present_for_authorization(payload), indent=2, ensure_ascii=False))
    return 0


def _cmd_freeze(args) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    envelope = freeze_authority(payload, authorized_literal=args.authorization, authority_source=args.source,
                                authorized_at=args.authorized_at)
    path = publish_authority(args.repo, envelope)
    print(json.dumps({"published": path.as_posix(), "root_authority_digest": envelope["root_authority_digest"]},
                     indent=2, ensure_ascii=False))
    return 0


def _cmd_status(args) -> int:
    with StoryAuthority.open_for(args.repo, args.authority_id) as authority:
        print(json.dumps(authority.status_projection(), indent=2, ensure_ascii=False))
    return 0


def _cmd_probe_barrier(args) -> int:
    install_cognitive_barrier(args.directory)
    report = probe_cognitive_barrier(args.directory)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["capability"] == "available" else 1


def _cmd_snapshot(args) -> int:
    print(json.dumps(snapshot_set(args.repo, args.pattern), indent=2, ensure_ascii=False))
    return 0


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Story Authority Envelope and AUTO_STORY ledger (T032).")
    sub = parser.add_subparsers(dest="command", required=True)

    present = sub.add_parser("present", help="print the payload, its digest and the literal the operator must issue")
    present.add_argument("--payload", required=True)
    present.set_defaults(func=_cmd_present)

    freeze = sub.add_parser("freeze", help="bind an operator authorization to a payload and publish the envelope")
    freeze.add_argument("--payload", required=True)
    freeze.add_argument("--authorization", required=True, help="the exact 'AUTORIZO STORY <work_ref> sha256:<digest>' literal")
    freeze.add_argument("--source", required=True)
    freeze.add_argument("--authorized-at", dest="authorized_at")
    freeze.add_argument("--repo", default=".")
    freeze.set_defaults(func=_cmd_freeze)

    status = sub.add_parser("status", help="print the read-only projection of the authority journal")
    status.add_argument("--authority-id", required=True)
    status.add_argument("--repo", default=".")
    status.set_defaults(func=_cmd_status)

    barrier = sub.add_parser("probe-barrier", help="install and prove the cognitive call barrier")
    barrier.add_argument("--directory", required=True)
    barrier.set_defaults(func=_cmd_probe_barrier)

    snapshot = sub.add_parser("snapshot", help="compute an exact_set_snapshot reference for a protected path")
    snapshot.add_argument("--repo", default=".")
    snapshot.add_argument("--pattern", required=True)
    snapshot.set_defaults(func=_cmd_snapshot)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except HardStop as stop:
        print(json.dumps({"hard_stop": stop.reason, "detail": stop.detail, "evidence": stop.evidence},
                         indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    except Refusal as refusal:
        print(json.dumps({"refusal": str(refusal)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return refusal.code


if __name__ == "__main__":
    sys.exit(main())
