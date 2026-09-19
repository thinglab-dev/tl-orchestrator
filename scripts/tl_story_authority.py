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
`lease.lock`, plus `status.json`, which is only ever a projection of that journal. A chain only
protects a line that has a successor, so the tail is anchored outside the working tree, in the
repository's ref store (`refs/tl/story-authorities/<authority_id>/journal-head`), moved by
compare-and-swap before each append; see `JournalAnchor`.

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
        PROTECTED_PATH_PATTERN_INVALID,
        ProtectedPathError,
        assert_protected_paths_monotonic,
        canonical_json,
        digest_of,
        git_changed_paths,
        protected_pattern_violations,
        sha256_hex,
        snapshot_set,
        validate_against_schema_file,
        verify_protected_paths,
    )
except ImportError:  # executed from the repository root
    from scripts.validate_execution_plan import (  # type: ignore[no-redef]
        PROTECTED_PATH_PATTERN_INVALID,
        ProtectedPathError,
        assert_protected_paths_monotonic,
        canonical_json,
        digest_of,
        git_changed_paths,
        protected_pattern_violations,
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
# The child lifecycle is a closed state machine: new -> derived -> open -> closed | failed, and a
# terminal state is final. Each child event names the one state it may leave; anything else in the
# journal is a history this module never writes, so folding it fails closed.
CHILD_TRANSITIONS = {
    "child_derived": ("new", "derived"),
    "child_open": ("derived", "open"),
    "child_closed": ("open", "closed"),
    "child_failed": ("open", "failed"),
}
CHILD_TERMINAL_STATES = frozenset({"closed", "failed"})
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

AUTHORIZATION_LITERAL_RE = re.compile(r"^AUTORIZO STORY (?P<work_ref>\S+) sha256:(?P<digest>[0-9a-f]{64})\Z")
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
    protected = payload["protected_paths"]
    invalid = protected_pattern_violations(
        [item for item in protected if isinstance(item, dict)]) if isinstance(protected, list) else []
    if invalid:
        raise Refusal(f"{PROTECTED_PATH_PATTERN_INVALID}: authority_payload protected_paths {canonical_json(invalid)}")


def canonical_authority_payload(payload: dict) -> str:
    """canonical_json_v1 over exactly the authorized fields."""
    _assert_payload_shape(payload)
    return canonical_json(payload)


def root_authority_digest(payload: dict) -> str:
    return sha256_hex(canonical_authority_payload(payload))


def authorization_literal(work_ref: str, digest: str) -> str:
    return f"AUTORIZO STORY {work_ref} sha256:{digest}"


def parse_authorization_literal(literal: str) -> tuple[str, str]:
    if not isinstance(literal, str):
        raise Refusal(
            "authority_missing_or_ambiguous: the operator authorization must be exactly "
            "'AUTORIZO STORY <work_ref> sha256:<root_authority_digest>'", 2)
    match = AUTHORIZATION_LITERAL_RE.match(literal)
    if not match:
        raise Refusal(
            "authority_missing_or_ambiguous: the operator authorization must be exactly "
            "'AUTORIZO STORY <work_ref> sha256:<root_authority_digest>'", 2)
    return match.group("work_ref"), match.group("digest")


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
    work_ref, authorized_digest = parse_authorization_literal(authorized_literal)
    if work_ref != payload["work_ref"]:
        raise Refusal(
            f"authority_missing_or_ambiguous: authorization names Story {work_ref!r} but the payload is for "
            f"{payload['work_ref']!r}", 2)
    if authorized_digest != digest:
        raise Refusal(
            f"authority_missing_or_ambiguous: authorization carries digest {authorized_digest} but the payload "
            f"digests to {digest}", 2)
    if not str(authority_source).strip():
        raise Refusal("operator_authorization.authority_source must name where the decision was captured")
    envelope = {
        "authority_payload": payload,
        "root_authority_digest": digest,
        "operator_authorization": {
            "authority_source": str(authority_source),
            "authorized_at": _require_timestamp(authorized_at or now_iso(), "authorized_at"),
            "authorized_literal": str(authorized_literal).strip(),
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
    work_ref, authorized_digest = parse_authorization_literal(literal)
    if authorized_digest != declared or work_ref != payload["work_ref"]:
        raise HardStop(
            "authority_missing_or_ambiguous",
            f"operator authorization {literal!r} does not bind this payload")
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

def _child_transition_violation(state: "AuthorityState", event: dict) -> dict | None:
    """The reason `event` is not a legal step of its child's lifecycle, or None when it is."""
    kind = event["kind"]
    expected, _target = CHILD_TRANSITIONS[kind]
    child_id = event.get("child_batch_id")
    if not isinstance(child_id, str) or not child_id:
        return {"seq": event.get("seq"), "kind": kind, "child_batch_id": child_id,
                "detail": "child event names no child_batch_id"}
    current = state.child_state(child_id)
    if current == expected:
        return None
    return {"seq": event.get("seq"), "kind": kind, "child_batch_id": child_id, "from": current,
            "expected": expected}


ANCHOR_REF_PREFIX = "refs/tl/story-authorities"
ANCHOR_FORMAT = 1
ANCHOR_KIND = "tl_story_authority_journal_head"
ANCHOR_UNAVAILABLE = "story_authority_anchor_unavailable"
ANCHOR_DIVERGENT = "story_authority_anchor_divergent"
ANCHOR_CONFLICT = "story_authority_anchor_conflict"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_OID_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
# The anchor must land in exactly the repository the authority belongs to, whatever the caller's
# environment says: any of these would redirect the ref store or the object database elsewhere.
_ANCHOR_GIT_ENV_DROP = frozenset({
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
})


def journal_anchor_ref(authority_id: str) -> str:
    return f"{ANCHOR_REF_PREFIX}/{authority_id}/journal-head"


def journal_chain_seed(authority_id: str, root_digest: str) -> str:
    """Chain digest before the first line. Binds every chain digest to one authority and envelope."""
    return digest_of({"anchor_ref": journal_anchor_ref(authority_id), "authority_id": authority_id,
                      "root_authority_digest": root_digest})


def journal_chain_step(previous: str, line: bytes) -> str:
    """Full-length running digest over every journal line: any edited, dropped or inserted line changes it."""
    return sha256_hex(previous.encode("ascii") + b"\n" + line)


class JournalAnchor:
    """The journal tail, anchored where a write to the working tree cannot reach it.

    The hash chain inside `journal.jsonl` protects a line only through its successor, so the last
    line could be rewritten, keeping its `prev`, without breaking anything the file itself carries.
    A self-hash, a checksum in `status.json` or any other file next to the journal does not help:
    whoever can rewrite the journal can rewrite those in the same stroke.

    The tail is therefore anchored in the repository's ref store, outside the working tree:
    `refs/tl/story-authorities/<authority_id>/journal-head` points at a blob, the receipt, that
    carries the canonical last line itself, its seq, the running full-length chain digest before
    and after it, and the authority id and root digest it belongs to. The ref is namespaced by
    authority and lives in the repository's own ref store; the receipt names its ref, authority
    and envelope, so an anchor copied from another authority, or pointed at through a symbolic
    ref, does not verify. It is moved only by `git update-ref --stdin` with the old value
    (`create` for the first event, `update <new> <old>` afterwards), so a second writer, or a
    writer holding a stale view, cannot move it, and it is never moved backwards by this module.

    Ordering (write-ahead to the anchor): receipt blob, then CAS on the ref, then the fsynced
    append. A crash between the CAS and the append leaves the anchor exactly one event ahead; that
    event is recovered from the anchored receipt, and only when the receipt proves it is the
    unique continuation of the chain on disk (seq = lines + 1, prev and prev chain digest equal to
    the on-disk tail, any torn fragment a prefix of the anchored line). The opposite never
    happens: a journal line the anchor does not cover is never used to create or move an anchor,
    so there is no window in which a rewritten tail can be blessed. A missing anchor under a
    non-empty journal, or a mechanism that cannot answer, fails closed.
    """

    def __init__(self, repo: str | Path, authority_id: str, root_digest: str):
        self.repo = Path(repo)
        self.authority_id = authority_id
        self.root_digest = root_digest
        self.ref = journal_anchor_ref(authority_id)
        self.seed = journal_chain_seed(authority_id, root_digest)
        self._repository_checked = False

    def _unavailable(self, detail: str) -> HardStop:
        return HardStop("state_integrity", f"{ANCHOR_UNAVAILABLE}: {detail}; AUTO_STORY does not run on an "
                        "unanchored journal", authority_id=self.authority_id, anchor_ref=self.ref)

    def _git(self, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if key not in _ANCHOR_GIT_ENV_DROP}
        command = ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsync=loose-object,reference", *args]
        try:
            return subprocess.run(command, cwd=str(self.repo), input=stdin, capture_output=True, check=False,
                                  timeout=60, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            raise self._unavailable(f"git could not be executed: {exc}") from exc

    def _require_repository(self) -> None:
        """The anchor goes into this repository's ref store or nowhere: never into an enclosing one."""
        if self._repository_checked:
            return
        record = self._git("rev-parse", "--show-toplevel")
        top = record.stdout.decode("utf-8", "replace").strip()
        if record.returncode != 0 or not top:
            raise self._unavailable(f"{self.repo.as_posix()} is not a git work tree: "
                                    f"{record.stderr.decode('utf-8', 'replace').strip()[:200]}")
        if os.path.realpath(top) != os.path.realpath(str(self.repo)):
            raise self._unavailable("the authority repository is not the root of its git work tree, so the "
                                    "anchor would land in another repository")
        self._repository_checked = True

    def load(self) -> tuple[str, dict] | None:
        """(oid, receipt) of the current anchor, None when the ref does not exist. Raises when unusable."""
        self._require_repository()
        listed = self._git("for-each-ref", "--format=%(refname) %(objectname) %(objecttype) %(symref)", self.ref)
        if listed.returncode != 0:
            raise self._unavailable(f"cannot read {self.ref}: {listed.stderr.decode('utf-8', 'replace').strip()[:200]}")
        rows = [row.split(" ") for row in listed.stdout.decode("utf-8", "replace").splitlines() if row.strip()]
        rows = [row for row in rows if row and row[0] == self.ref]
        if not rows:
            return None
        refname, oid, kind, symref = (rows[0] + ["", "", "", ""])[:4]
        if len(rows) != 1 or symref or kind != "blob" or not _OID_RE.match(oid):
            raise HardStop("state_integrity",
                           f"{ANCHOR_DIVERGENT}: {self.ref} is not a direct ref to a receipt blob "
                           f"(type {kind or 'unknown'}, symref {symref or 'none'})",
                           authority_id=self.authority_id, anchor_ref=self.ref)
        blob = self._git("cat-file", "blob", oid)
        if blob.returncode != 0:
            raise self._unavailable(f"cannot read anchor object {oid}: "
                                    f"{blob.stderr.decode('utf-8', 'replace').strip()[:200]}")
        try:
            text = blob.stdout.decode("utf-8")
            receipt = json.loads(text)
            canonical = isinstance(receipt, dict) and canonical_json(receipt) == text
        except ValueError:
            receipt, canonical = None, False
        if not canonical:
            raise HardStop("state_integrity", f"{ANCHOR_DIVERGENT}: the object {oid} under {self.ref} is not a "
                           "canonical journal head receipt", authority_id=self.authority_id, anchor_ref=self.ref)
        return oid, receipt

    def receipt(self, seq: int, line: str, prev_chain_digest: str) -> dict:
        return {
            "anchor_format": ANCHOR_FORMAT,
            "anchor_kind": ANCHOR_KIND,
            "anchor_ref": self.ref,
            "authority_id": self.authority_id,
            "root_authority_digest": self.root_digest,
            "seq": seq,
            "line": line,
            "line_sha256": sha256_hex(line),
            "prev_chain_digest": prev_chain_digest,
            "chain_digest": journal_chain_step(prev_chain_digest, line.encode("utf-8")),
        }

    def receipt_problem(self, receipt: dict) -> str:
        """Why this receipt is not a head this authority could have anchored, or "" when it is."""
        for name, expected in (("anchor_format", ANCHOR_FORMAT), ("anchor_kind", ANCHOR_KIND),
                               ("anchor_ref", self.ref), ("authority_id", self.authority_id),
                               ("root_authority_digest", self.root_digest)):
            if receipt.get(name) != expected:
                return f"the receipt carries {name}={receipt.get(name)!r}, not {expected!r}"
        seq, line, prev_chain = receipt.get("seq"), receipt.get("line"), receipt.get("prev_chain_digest")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1 or not isinstance(line, str):
            return "the receipt carries no usable seq or line"
        if not isinstance(prev_chain, str) or not _HEX64_RE.match(prev_chain):
            return "the receipt carries no usable prev_chain_digest"
        if receipt.get("line_sha256") != sha256_hex(line):
            return "the receipt line does not reproduce its line_sha256"
        if receipt.get("chain_digest") != journal_chain_step(prev_chain, line.encode("utf-8")):
            return "the receipt line does not reproduce its chain_digest"
        if seq == 1 and prev_chain != self.seed:
            return "the first anchored event does not start this authority's chain"
        try:
            event = json.loads(line)
            canonical = isinstance(event, dict) and canonical_json(event) == line
        except ValueError:
            event, canonical = None, False
        if not canonical:
            return "the anchored line is not a canonical journal event"
        if (event.get("format_version") != AUTHORITY_FORMAT or event.get("kind") not in JOURNAL_EVENTS
                or event.get("seq") != seq or event.get("authority_id") != self.authority_id):
            return "the anchored line is not an event of this authority at this seq"
        return ""

    def publish(self, receipt: dict, expected_oid: str | None) -> str:
        """Store the receipt and move the ref from exactly `expected_oid`. Never moves it on conflict."""
        self._require_repository()
        stored = self._git("hash-object", "-t", "blob", "-w", "--stdin", stdin=canonical_json(receipt).encode("utf-8"))
        oid = stored.stdout.decode("utf-8", "replace").strip()
        if stored.returncode != 0 or not _OID_RE.match(oid):
            raise self._unavailable(f"cannot store the journal head receipt: "
                                    f"{stored.stderr.decode('utf-8', 'replace').strip()[:200]}")
        instruction = (f"create {self.ref} {oid}\n" if expected_oid is None
                       else f"update {self.ref} {oid} {expected_oid}\n")
        moved = self._git("update-ref", "--no-deref", "--stdin", stdin=instruction.encode("ascii"))
        if moved.returncode != 0:
            raise HardStop(
                "state_integrity",
                f"{ANCHOR_CONFLICT}: {self.ref} is no longer at {expected_oid or 'absent'} (compare-and-swap refused: "
                f"{moved.stderr.decode('utf-8', 'replace').strip()[:200]}); another writer moved the anchor, so "
                "nothing was appended",
                authority_id=self.authority_id, anchor_ref=self.ref, expected=expected_oid or "")
        return oid


class AuthorityJournal:
    """Append-only JSONL, one writer, write-ahead, fsynced, hash-chained, tail anchored in git.

    Every read verifies the whole file against the anchored head (see `JournalAnchor`); a failure
    is recorded in `anchor_failure`, becomes a hard stop in every refold, and `append` refuses to
    write anything after it.
    """

    def __init__(self, path: Path, anchor: JournalAnchor | None = None):
        self.path = Path(path)
        self.anchor = anchor
        self._seq = 0
        self._prev = ""
        self._chain = anchor.seed if anchor is not None else ""
        self._anchor_oid: str | None = None
        self._pending = b""
        self._pending_chain = ""
        self.anchor_failure = ""

    def append(self, kind: str, **payload: Any) -> dict:
        if kind not in JOURNAL_EVENTS:
            raise Refusal(f"unknown authority journal event {kind!r}")
        _events, invalid = self.read()
        refused = self.integrity_failure(invalid)
        if refused:
            raise HardStop("state_integrity", f"{refused}; nothing is appended to it", journal=self.path.name)
        self.recover()
        seq = self._seq + 1
        event = {"format_version": AUTHORITY_FORMAT, "seq": seq, "at": now_iso(), "kind": kind,
                 "prev": self._prev, **payload}
        line = canonical_json(event)
        receipt = self.anchor.receipt(seq, line, self._chain)
        # Write-ahead to the anchor: if the append below never lands, the anchored receipt still
        # holds the exact line, and `recover` completes it. The reverse order would leave a line
        # no anchor covers, and nothing may ever anchor a line it read from the journal.
        self._anchor_oid = self.anchor.publish(receipt, self._anchor_oid)
        self._write(line.encode("utf-8") + b"\n")
        self._seq, self._prev, self._chain = seq, sha256_hex(line)[:16], receipt["chain_digest"]
        return event

    def _write(self, data: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        with open(self.path, "ab") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if created:
            with contextlib.suppress(OSError, AttributeError):
                directory = os.open(str(self.path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)

    def recover(self) -> bool:
        """Complete, from the anchored receipt, the one event a crash left anchored but not appended."""
        if not self._pending:
            return False
        self._write(self._pending)
        _events, invalid = self.read()
        refused = self.integrity_failure(invalid)
        if refused or self._pending:
            raise HardStop("state_integrity", f"{ANCHOR_DIVERGENT}: recovery of the anchored tail did not "
                           f"converge: {refused or 'the anchor is still ahead'}", journal=self.path.name)
        return True

    def integrity_failure(self, invalid: int) -> str:
        problems: list[str] = []
        if invalid:
            problems.append(f"authority journal has {invalid} invalid line(s); the hash chain is broken")
        if self.anchor_failure:
            problems.append(self.anchor_failure)
        return "; ".join(problems)

    def read(self) -> tuple[list[dict], int]:
        events: list[dict] = []
        invalid = 0
        prev = ""
        chain = self._chain = self.anchor.seed if self.anchor is not None else ""
        self._pending, self.anchor_failure = b"", ""
        data = self.path.read_bytes() if self.path.is_file() else b""
        segments = data.split(b"\n")
        # Whatever follows the last newline was never completed by an append: it is not a line.
        torn = segments.pop()
        lines = [segment.strip() for segment in segments if segment.strip()]
        for raw_bytes in lines:
            chain = journal_chain_step(chain, raw_bytes)
            raw = raw_bytes.decode("utf-8", errors="replace")
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
        self._prev, self._chain, self._seq = prev, chain, len(lines)
        pending = self._verify_anchor(lines, torn.strip() and torn, chain, prev)
        if pending is not None:
            event, line = pending
            events.append(event)
            self._prev, self._chain, self._seq = sha256_hex(line)[:16], self._pending_chain, len(lines) + 1
        return events, invalid

    def _verify_anchor(self, lines: list[bytes], torn: bytes, chain: str, prev: str) -> tuple[dict, str] | None:
        """Hold the file to the anchored head. Returns the anchored event still to append, if any."""
        if self.anchor is None:
            self.anchor_failure = (f"{ANCHOR_UNAVAILABLE}: no repository to anchor the journal tail in; AUTO_STORY "
                                   "does not run on an unanchored journal")
            return None
        try:
            head = self.anchor.load()
        except HardStop as stop:
            self.anchor_failure = stop.detail
            return None
        self._anchor_oid = head[0] if head is not None else None
        if head is None:
            if lines or torn:
                # Never bootstrap: an anchor created from what the journal says would bless the
                # very tail it exists to protect. Only an explicit, authenticated migration could.
                self.anchor_failure = (
                    f"{ANCHOR_DIVERGENT}: the journal holds {len(lines)} line(s) but {self.anchor.ref} does not "
                    "exist; an unanchored tail is never trusted and no anchor is created from it")
            return None
        oid, receipt = head
        problem = self.anchor.receipt_problem(receipt)
        if problem:
            self.anchor_failure = f"{ANCHOR_DIVERGENT}: {self.anchor.ref} -> {oid}: {problem}"
            return None
        seq, line = receipt["seq"], receipt["line"]
        if seq == len(lines) and not torn:
            if receipt["chain_digest"] != chain:
                self.anchor_failure = (
                    f"{ANCHOR_DIVERGENT}: the journal tail at seq {seq} does not reproduce the head anchored in "
                    f"{self.anchor.ref}; a journal line was rewritten after it was anchored")
            return None
        line_bytes = line.encode("utf-8") + b"\n"
        continues = (seq == len(lines) + 1 and receipt["prev_chain_digest"] == chain
                     and json.loads(line).get("prev") == prev
                     and len(torn) < len(line_bytes) and line_bytes.startswith(torn))
        if not continues:
            self.anchor_failure = (
                f"{ANCHOR_DIVERGENT}: {self.anchor.ref} anchors seq {seq} but the journal holds {len(lines)} complete "
                f"line(s){' and a torn fragment' if torn else ''} that the anchored head does not continue; "
                "the journal is never trusted beyond or instead of its anchor")
            return None
        # Crash between the anchor CAS and the append: the anchored receipt is the only source.
        self._pending = line_bytes[len(torn):]
        self._pending_chain = receipt["chain_digest"]
        return json.loads(line), line

    def fold(self) -> "AuthorityState":
        events, invalid = self.read()
        state = AuthorityState(invalid_lines=invalid, anchor_failure=self.anchor_failure)
        for event in events:
            state.events += 1
            kind = event["kind"]
            if kind in CHILD_TRANSITIONS:
                violation = _child_transition_violation(state, event)
                if violation is not None:
                    # Never applied: a refused transition does not become state, and the violation
                    # itself makes every consumer of this fold fail closed.
                    state.lifecycle_violations.append(violation)
                    continue
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
                state.derived.append(event)
                state.children.setdefault(event["child_batch_id"], {})["derivation"] = event
                state.children[event["child_batch_id"]]["state"] = "derived"
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
    hard_stops: list[dict] = field(default_factory=list)
    consecutive_failures: int = 0
    last_closed_child: str = ""
    closed: bool = False
    close_state: str = ""
    close_reason: str = ""
    invalid_lines: int = 0
    anchor_failure: str = ""
    lifecycle_violations: list[dict] = field(default_factory=list)

    def child_state(self, child_batch_id: str) -> str:
        return (self.children.get(child_batch_id) or {}).get("state") or "new"

    def integrity_failure(self) -> str:
        """Why this history cannot be trusted, or "" when it can."""
        problems: list[str] = []
        if self.invalid_lines:
            problems.append(f"authority journal has {self.invalid_lines} invalid line(s); the hash chain is broken")
        if self.anchor_failure:
            problems.append(self.anchor_failure)
        if self.lifecycle_violations:
            problems.append("authority journal records child transition(s) outside new -> derived -> open -> "
                            f"closed|failed: {canonical_json(self.lifecycle_violations)}")
        return "; ".join(problems)

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
        # Without a repository there is nowhere to anchor the tail: the journal then fails closed.
        anchor = JournalAnchor(self.repo, self.authority_id, self.root_digest) if self.repo is not None else None
        self.journal = AuthorityJournal(self.runtime_dir / "journal.jsonl", anchor)
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
        # A crash between the anchor CAS and the append left one anchored event unwritten; only the
        # lease holder completes it, and only from the anchored receipt.
        if self.journal.recover():
            self.refold()
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
        """Rebuild the state from the journal, refusing a history this module could not have written.

        A broken hash chain, a journal that its anchored head does not cover (or an anchor that
        cannot be read), or a child transition outside the lifecycle is a hard stop for every
        caller — acquire, load, bind, reserve, derive, record — and nothing is appended to it.
        """
        state = self.journal.fold()
        failure = state.integrity_failure()
        if failure:
            raise HardStop("state_integrity", failure, authority_id=self.authority_id,
                           invalid_lines=state.invalid_lines, lifecycle_violations=state.lifecycle_violations)
        self.state = state
        return self.state

    def _require_child_transition(self, kind: str, child_batch_id: Any) -> None:
        """Refuse, without journaling anything, a child event its current state does not allow."""
        expected, target = CHILD_TRANSITIONS[kind]
        if not isinstance(child_batch_id, str) or not child_batch_id:
            raise HardStop("state_integrity", f"child_lifecycle: {kind} names no child_batch_id",
                           event=kind, child_batch_id=child_batch_id)
        current = self.state.child_state(child_batch_id)
        if current != expected:
            terminal = " and a terminal state is final" if current in CHILD_TERMINAL_STATES else ""
            raise HardStop(
                "state_integrity",
                f"child_lifecycle: {kind} moves child batch {child_batch_id} from {expected} to {target}, but under "
                f"story authority {self.authority_id} it is {current}; a child moves new -> derived -> open -> "
                f"closed|failed{terminal}",
                event=kind, child_batch_id=child_batch_id, state=current, expected=expected)

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

    def child_proposal_path(self, child_batch_id: str) -> Path:
        return self.runtime_dir / "proposals" / f"{child_batch_id}.proposal.json"

    def child_proof_path(self, child_batch_id: str) -> Path:
        return self.runtime_dir / "proposals" / f"{child_batch_id}.proof.json"

    def get_child_proposal(self, child_batch_id: str) -> dict | None:
        path = self.child_proposal_path(child_batch_id)
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def get_child_proof(self, child_batch_id: str) -> dict | None:
        path = self.child_proof_path(child_batch_id)
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    @staticmethod
    def _read_canonical(path: Path, what: str, child_batch_id: str) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HardStop("state_integrity",
                           f"the {what} of child batch {child_batch_id} is unreadable at "
                           f"{path.as_posix()}: {exc}") from exc
        if not isinstance(payload, dict):
            raise HardStop("state_integrity", f"the {what} of child batch {child_batch_id} is not an object")
        return payload

    def load_child_derivation(self, child_batch_id: str, *, spec_paths: Iterable[str] = ()) -> tuple[dict, dict]:
        """Recover the canonical child proposal and its derivation proof, re-digesting both.

        A digest a batch declares is worth nothing unless the object it digests can be produced
        and hashed again, so this reads the persisted objects and recomputes. A missing
        derivation event, an unreadable file, or a digest that does not reproduce is a hard stop;
        nothing here falls back to "close enough".
        """
        self.refold()
        derivation = (self.state.children.get(child_batch_id) or {}).get("derivation")
        if not derivation:
            raise HardStop(
                "authority_missing_or_ambiguous",
                f"story authority {self.authority_id} never derived child batch {child_batch_id}; "
                "a batch cannot claim an authority that did not authorize it",
                child_batch_id=child_batch_id, derived=sorted(self.state.children))
        proposal = self._read_canonical(self.child_proposal_path(child_batch_id), "child proposal", child_batch_id)
        proof = self._read_canonical(self.child_proof_path(child_batch_id), "derivation proof", child_batch_id)

        proposal_digest = digest_of(proposal)
        if proposal_digest != derivation.get("child_proposal_digest"):
            raise HardStop("state_integrity",
                           f"the persisted child proposal of {child_batch_id} digests to {proposal_digest} but the "
                           f"journal recorded {derivation.get('child_proposal_digest')}",
                           recomputed=proposal_digest, journaled=derivation.get("child_proposal_digest"))
        # The proof digests itself by construction, so it is recomputed over the proof without
        # the field that only exists because the digest was already taken.
        recomputed = digest_of({k: v for k, v in proof.items() if k != "derivation_proof_digest"})
        if recomputed != proof.get("derivation_proof_digest") or recomputed != derivation.get("derivation_proof_digest"):
            raise HardStop("state_integrity",
                           f"the derivation proof of {child_batch_id} digests to {recomputed} but the proof declares "
                           f"{proof.get('derivation_proof_digest')} and the journal recorded "
                           f"{derivation.get('derivation_proof_digest')}")
        if proof.get("child_proposal_digest") != proposal_digest:
            raise HardStop("state_integrity",
                           f"the derivation proof of {child_batch_id} was taken over a different child proposal")
        if proof.get("root_authority_digest") != self.root_digest:
            raise HardStop("authority_missing_or_ambiguous",
                           f"the derivation proof of {child_batch_id} is anchored in authority "
                           f"{proof.get('root_authority_digest')}, not {self.root_digest}")

        # Revalidate the persisted proposal independently against the root authority envelope.
        # A persisted proposal must be a strict, valid subset of the root envelope regardless
        # of whether hashes matched, and a rework child must still reproduce the residual
        # findings its predecessor closed with.
        assert_child_proposal_within_envelope(
            proposal, self.payload, self.state, self, proof=proof, derivation=derivation,
            spec_paths=[*(proof.get("spec_paths") or []), *spec_paths])

        return proposal, proof

    def record_child_derived(self, proposal: dict, proof: dict) -> dict:
        self._require_lease()
        self._require_open()
        child_id = proposal["child_batch_id"]

        # Validate proposal and proof before persisting or journaling.
        assert_child_proposal_within_envelope(proposal, self.payload, self.state, self, proof=proof,
                                              spec_paths=proof.get("spec_paths") or ())

        proposal_digest = digest_of(proposal)
        if proof.get("child_proposal_digest") != proposal_digest:
            self.hard_stop("state_integrity",
                           f"the derivation proof of {child_id} was taken over a different child proposal")
        if proof.get("root_authority_digest") != self.root_digest:
            self.hard_stop("authority_missing_or_ambiguous",
                           f"the derivation proof of {child_id} is anchored in authority "
                           f"{proof.get('root_authority_digest')}, not {self.root_digest}")
        recomputed = digest_of({k: v for k, v in proof.items() if k != "derivation_proof_digest"})
        if recomputed != proof.get("derivation_proof_digest"):
            self.hard_stop("state_integrity",
                           f"the derivation proof of {child_id} has invalid digest {proof.get('derivation_proof_digest')}, expected {recomputed}")
        # Last gate before anything is written: an id is derived once, and what was persisted for
        # it is never overwritten.
        self.assert_child_batch_id_unused(child_id)

        # The digests below are only verifiable if the objects survive: persist them in canonical
        # form so a later run can re-read and re-hash them instead of trusting a hex string.
        (self.runtime_dir / "proposals").mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self.child_proposal_path(child_id), proposal)
        _write_json_atomic(self.child_proof_path(child_id), proof)
        event = self.journal.append(
            "child_derived", authority_id=self.authority_id, child_batch_id=child_id,
            parent_child_batch_id=proposal.get("parent_child_batch_id"),
            root_authority_digest=proof["root_authority_digest"],
            parent_authority_digest=proof["parent_authority_digest"],
            parent_batch_digest=proof["parent_batch_digest"],
            child_proposal_digest=proof["child_proposal_digest"],
            derivation_proof_digest=proof["derivation_proof_digest"],
            granted_model_calls=int(proposal["model_call_budget"]),
            functional_parent_checkpoint=proposal.get("functional_parent_checkpoint"),
            unresolved_action_items_digest=proof.get("unresolved_action_items_digest", ""))
        self.refold()
        self.write_status()
        return event

    def assert_child_batch_id_unused(self, child_batch_id: str) -> None:
        """A child_batch_id is derived exactly once, whatever state it reached afterwards.

        Re-deriving an id would overwrite the proposal and proof its digests were taken over,
        and would let a reused id slip past max_child_batches and the lineage it already has.
        """
        self.refold()
        known = self.state.children.get(child_batch_id)
        if known is not None:
            self.hard_stop(
                "state_integrity",
                f"child batch {child_batch_id} was already derived under story authority {self.authority_id} "
                f"(state {known.get('state') or 'unknown'}); a child_batch_id is derived once and its proposal "
                "and proof are never rewritten",
                child_batch_id=child_batch_id, state=known.get("state", ""))
        persisted = [path.name for path in (self.child_proposal_path(child_batch_id),
                                            self.child_proof_path(child_batch_id)) if path.exists()]
        if persisted:
            self.hard_stop(
                "state_integrity",
                f"child batch {child_batch_id} already has persisted derivation artifacts {persisted}; "
                "they are never overwritten",
                child_batch_id=child_batch_id, persisted=persisted)

    def record_child_open(self, child_batch_id: str, *, branch: str, head_commit: str, tree: str,
                          lineage: dict | None = None) -> dict:
        self._require_lease()
        self._require_open()
        self._require_child_transition("child_open", child_batch_id)
        event = self.journal.append(
            "child_open", authority_id=self.authority_id, child_batch_id=child_batch_id, branch=branch,
            head_commit=head_commit, tree=tree, **({"lineage": lineage} if lineage else {}))
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
        self._require_child_transition("child_closed", child_batch_id)
        for name, value in (("governance_base_commit", governance_base_commit),
                            ("checker_reviewed_commit", checker_reviewed_commit),
                            ("functional_checkpoint_commit", functional_checkpoint_commit)):
            if not _COMMIT_RE.match(str(value)):
                raise Refusal(f"{name} must be a full 40 character commit sha, got {value!r}")
        # The canonical residual findings are persisted with their digest, so the next child can be
        # rechecked against the findings themselves rather than against a hex string.
        residual = canonical_residual_items(unresolved_action_items or [])
        digest = unresolved_digest if unresolved_digest is not None else unresolved_action_items_digest(residual)
        inherited = ((self.state.children.get(child_batch_id) or {}).get("derivation") or {}).get(
            "functional_parent_checkpoint") or {}
        made_progress = checker_reviewed_tree != inherited.get("tree")
        event = self.journal.append(
            "child_closed", authority_id=self.authority_id, child_batch_id=child_batch_id,
            governance_base_commit=governance_base_commit, checker_reviewed_commit=checker_reviewed_commit,
            checker_reviewed_tree=checker_reviewed_tree,
            functional_checkpoint_commit=functional_checkpoint_commit,
            functional_checkpoint_tree=functional_checkpoint_tree, checker_verdict=checker_verdict,
            unresolved_action_items=residual, unresolved_action_items_digest=digest, made_progress=made_progress)
        self.refold()
        self.write_status()
        return event

    def record_child_failed(self, child_batch_id: str, *, reason: str, detail: str = "") -> dict:
        self._require_lease()
        self.refold()
        self._require_child_transition("child_failed", child_batch_id)
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
            self.refold()  # an untrustworthy history is refused, never appended to
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

def unresolved_action_items_digest(items: Iterable[dict]) -> str:
    """Stable digest of the residual findings a child batch is derived from."""
    normalized = sorted(
        ({"id": str(item.get("id", "")), "category": str(item.get("category", "")),
          "target_role": str(item.get("target_role", "")), "location": str(item.get("location", "")),
          "required_action": str(item.get("required_action", ""))} for item in items),
        key=lambda entry: entry["id"])
    return digest_of(normalized)


def canonical_residual_items(items: Iterable[dict]) -> list[dict]:
    """The residual findings a closing child hands to its successor, in the form the journal keeps.

    Carries every field derivation_eligibility reads, so the patch-only decision can be recomputed
    from the journal alone; digests to the same value as the raw items.
    """
    canonical: list[dict] = []
    for item in items:
        entry = {"id": str(item.get("id", "")), "category": str(item.get("category", "")),
                 "target_role": str(item.get("target_role", "")), "location": str(item.get("location", "")),
                 "required_action": str(item.get("required_action", ""))}
        for optional in ("severity", "scope_status", "spec_status"):
            if item.get(optional) is not None:
                entry[optional] = str(item[optional])
        if item.get("derivation_blockers"):
            entry["derivation_blockers"] = sorted(str(flag) for flag in item["derivation_blockers"])
        canonical.append(entry)
    return sorted(canonical, key=lambda entry: entry["id"])


def _eligibility_stop_reason(blockers: list[dict]) -> str:
    return next((b["reason"] for b in blockers if b["reason"] in DERIVATION_HARD_STOP_REASONS), blockers[0]["reason"])


def assert_residual_lineage(
    proposal: dict,
    state: Any,
    payload: dict,
    *,
    spec_paths: Iterable[str] = (),
    proof: dict | None = None,
    derivation: dict | None = None,
) -> dict:
    """Prove a rework child is derived from exactly the residual findings its predecessor closed with.

    Applies to every child that names a parent_child_batch_id. The canonical findings persisted in
    the parent's closure are mandatory and non-empty, must reproduce the closure digest, must be
    strictly patch-only when recomputed here, and the child's derived_from_action_items, its proof
    and its child_derived event must all carry that same digest. Raises HardStop otherwise.
    Returns the lineage evidence that was confirmed.
    """
    child_id = str(proposal.get("child_batch_id", ""))
    parent = proposal.get("parent_child_batch_id")
    if not parent:
        return {}
    closure = state.closure_of(parent) if state is not None else None
    if closure is None:
        raise HardStop("state_integrity",
                       f"residual_lineage: child batch {parent!r} has not closed; there are no residual findings "
                       f"to derive {child_id} from")
    closure_digest = str(closure.get("unresolved_action_items_digest") or "")
    closure_items = closure.get("unresolved_action_items")
    if not isinstance(closure_items, list) or not closure_items:
        raise HardStop("state_integrity",
                       f"residual_lineage: the closure of {parent} recorded no canonical residual action items; "
                       f"rework child {child_id} has nothing it can be derived from",
                       parent_child_batch_id=parent)
    if unresolved_action_items_digest(closure_items) != closure_digest:
        raise HardStop("state_integrity",
                       f"residual_lineage: the residual action items journaled at the closure of {parent} do not "
                       f"reproduce its unresolved_action_items_digest {closure_digest}",
                       parent_child_batch_id=parent)
    declared = proposal.get("derived_from_action_items")
    if not isinstance(declared, list) or not declared:
        raise HardStop("state_integrity",
                       f"residual_lineage: child {child_id} continues {parent} but declares no "
                       "derived_from_action_items",
                       parent_child_batch_id=parent)
    for source, items in (("closure", closure_items), ("proposal", declared)):
        eligible, blockers = derivation_eligibility(items, payload, spec_paths)
        if not eligible:
            raise HardStop(_eligibility_stop_reason(blockers),
                           f"residual_lineage: patch_only_findings ({source}): {canonical_json(blockers)}",
                           blockers=blockers)
    declared_digest = unresolved_action_items_digest(declared)
    if declared_digest != closure_digest:
        raise HardStop("state_integrity",
                       f"residual_lineage: the residual findings differ from the ones recorded when the parent "
                       f"closed ({declared_digest} != {closure_digest})",
                       declared=declared_digest, recorded=closure_digest)
    for source, record in (("derivation proof", proof), ("child_derived event", derivation)):
        if record is not None and record.get("unresolved_action_items_digest") != closure_digest:
            raise HardStop("state_integrity",
                           f"residual_lineage: the {source} of {child_id} carries unresolved_action_items_digest "
                           f"{record.get('unresolved_action_items_digest')!r} but the closure of {parent} recorded "
                           f"{closure_digest}",
                           declared=record.get("unresolved_action_items_digest"), recorded=closure_digest)
    return {"parent_child_batch_id": parent, "unresolved_action_items_digest": closure_digest,
            "residual_action_item_ids": [str(item.get("id", "")) for item in closure_items]}


def _scope_paths(scope: dict) -> list[str]:
    return list(scope.get("required_mutation_targets") or []) + list(scope.get("conditional_mutation_targets") or [])


def _within(path: str, scopes: Iterable[str]) -> bool:
    normalized = Path(str(path)).as_posix().strip("/")
    for scope in scopes:
        candidate = Path(str(scope)).as_posix().strip("/")
        if candidate in {"", "."} or normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


within_scope = _within


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
             **({"severity": str(item["severity"])} if item.get("severity") else {})}
            for item in sorted(action_items, key=lambda entry: str(entry.get("id", "")))
        ],
        "lineage": {"governance_base_commit": governance_base_commit, "story_baseline_commit": story_baseline_commit},
    }
    valid, errors = validate_against_schema_file(proposal, CHILD_PROPOSAL_SCHEMA)
    if not valid:
        raise Refusal(f"derived child proposal violates its schema: {errors}")
    return proposal


def assert_child_proposal_within_envelope(
    proposal: dict,
    payload: dict,
    state: Any = None,
    authority: Any = None,
    *,
    now: str | None = None,
    proof: dict | None = None,
    derivation: dict | None = None,
    spec_paths: Iterable[str] = (),
) -> dict:
    """Prove a child proposal is a strict, verifiable subset of the authorized root envelope.

    Revalidates schema, authority binding, spec immutability, scope containment, forbidden path
    monotonicity, protected paths monotonicity, allowed effects subset, budget ceiling, deadline,
    and (when state is provided) authority lifecycle, child limits, streak, predecessor closure,
    functional checkpoint inheritance and residual lineage (see assert_residual_lineage).

    Raises HardStop on any violation. Returns the residual lineage evidence it confirmed.
    """
    def _fail(reason: str, detail: str, **evidence: Any) -> None:
        if authority is not None and hasattr(authority, "hard_stop"):
            authority.hard_stop(reason, detail, **evidence)
        raise HardStop(reason, detail, **evidence)

    valid, errors = validate_against_schema_file(proposal, CHILD_PROPOSAL_SCHEMA)
    if not valid:
        _fail("state_integrity", f"child proposal schema validation failed: {errors}")

    if (proposal.get("authority_id") != payload.get("authority_id") or
            proposal.get("work_ref") != payload.get("work_ref")):
        _fail("authority_missing_or_ambiguous",
              f"child binds {proposal.get('authority_id')}/{proposal.get('work_ref')}, "
              f"expected {payload.get('authority_id')}/{payload.get('work_ref')}")

    if (proposal.get("authorized_spec_sha256") != payload.get("authorized_spec_sha256") or
            proposal.get("authorized_spec_revision") != payload.get("authorized_spec_revision")):
        _fail("unexpected_revision_drift",
              f"child declares spec {str(proposal.get('authorized_spec_sha256'))[:16]} "
              f"rev {proposal.get('authorized_spec_revision')}, but authority froze "
              f"{str(payload.get('authorized_spec_sha256'))[:16]} rev {payload.get('authorized_spec_revision')}")

    scope = payload.get("authorized_write_scope") or {}
    authorized_union = _scope_paths(scope)
    child_union = list(proposal.get("required_mutation_targets") or []) + list(proposal.get("conditional_mutation_targets") or [])
    outside = sorted({path for path in child_union if not _within(path, authorized_union)})
    if outside:
        _fail("scope_expansion", f"paths outside the parent envelope: {outside}", outside=outside)

    parent_forbidden = set(scope.get("forbidden_paths") or [])
    child_forbidden = set(proposal.get("forbidden_paths") or [])
    if not parent_forbidden <= child_forbidden:
        dropped = sorted(parent_forbidden - child_forbidden)
        _fail("scope_expansion", f"the child dropped forbidden path(s) {dropped}", dropped=dropped)

    collisions = sorted({path for path in child_union if _within(path, child_forbidden)})
    if collisions:
        _fail("scope_expansion", f"the child authorizes path(s) it also forbids: {collisions}", collisions=collisions)

    protected_violations = assert_protected_paths_monotonic(
        payload.get("protected_paths") or [], proposal.get("protected_paths") or [])
    if protected_violations:
        _fail("protected_path_violation", canonical_json(protected_violations), violations=protected_violations)

    proposal_effects = proposal.get("allowed_effects") or {}
    payload_effects = payload.get("allowed_effects") or {}
    expanded = sorted(key for key in EFFECT_KEYS
                      if proposal_effects.get(key) and not payload_effects.get(key))
    if expanded:
        _fail("effect_expansion", f"the child enables effect(s) the parent denied: {expanded}", effects=expanded)

    granted = int(proposal.get("model_call_budget", 0))
    global_budget = int(payload.get("global_model_call_budget", 0))
    if global_budget and granted > global_budget:
        _fail("model_call_budget_exhausted",
              f"the child requests {granted} model calls which exceeds global budget {global_budget}",
              requested=granted, global_budget=global_budget)
    if authority is not None and hasattr(authority, "remaining_global_budget"):
        # At derivation time (before child is recorded in journal), the granted budget must fit in remaining budget.
        child_id = str(proposal.get("child_batch_id", ""))
        child_already_derived = state is not None and child_id in getattr(state, "children", {})
        if not child_already_derived:
            remaining = authority.remaining_global_budget
            if granted > remaining:
                _fail("model_call_budget_exhausted",
                      f"the child requests {granted} model calls but the authority has {remaining} left",
                      requested=granted, remaining=remaining)

    current_time = now or now_iso()
    deadline = payload.get("wall_clock_deadline", "")
    if deadline and current_time > deadline:
        _fail("wall_clock_deadline_exceeded",
              f"now {current_time} is past the authorized deadline {deadline}")

    if state is not None:
        if getattr(state, "closed", False):
            _fail("authority_missing_or_ambiguous",
                  f"authority already closed as {getattr(state, 'close_state', 'unknown')}")

        child_id = str(proposal.get("child_batch_id", ""))
        child_count = len(state.children) + (0 if child_id in state.children else 1)
        max_children = int(payload.get("max_child_batches", 0))
        if max_children and child_count > max_children:
            _fail("max_child_batches_exhausted",
                  f"{child_count} child batches exceeds max_child_batches {max_children}")

        active = [cid for cid in state.active_children() if cid != child_id]
        if len(active) >= MAX_ACTIVE_CHILD_BATCHES:
            _fail("state_integrity",
                  f"child batch(es) {active} are still active; AUTO_STORY v1 runs one at a time")

        max_failures = int(payload.get("max_consecutive_failed_batches", 0))
        if max_failures and state.consecutive_failures >= max_failures:
            _fail("consecutive_batch_failures_exhausted",
                  f"{state.consecutive_failures} consecutive child batches without progress")

        previous_id = proposal.get("parent_child_batch_id")
        if previous_id:
            if previous_id not in state.children:
                _fail("state_integrity",
                      f"parent_child_batch_id {previous_id!r} was never derived under this authority",
                      known=sorted(state.children))
            previous_closure = state.closure_of(previous_id)
            if previous_closure is None:
                _fail("state_integrity",
                      f"child batch {previous_id!r} has not closed; its reviewed commit does not exist yet")
            expected_checkpoint = {
                "commit": previous_closure["checker_reviewed_commit"],
                "tree": previous_closure["checker_reviewed_tree"],
                "child_batch_id": previous_closure["child_batch_id"],
            }
            if proposal.get("functional_parent_checkpoint") != expected_checkpoint:
                _fail("state_integrity",
                      f"the child must start exactly at the unmerged commit the previous Checker reviewed "
                      f"({expected_checkpoint['commit'][:12]}), got {(proposal.get('functional_parent_checkpoint') or {}).get('commit', 'none')}",
                      expected=expected_checkpoint, observed=proposal.get("functional_parent_checkpoint"))
            try:
                return assert_residual_lineage(proposal, state, payload, spec_paths=spec_paths, proof=proof,
                                               derivation=derivation)
            except HardStop as stop:
                _fail(stop.reason, stop.detail, **stop.evidence)
        else:
            if child_id in state.children:
                all_ids = list(state.children.keys())
                if all_ids and all_ids[0] != child_id:
                    _fail("state_integrity",
                          f"child {child_id} has no parent_child_batch_id but is not the first child ({all_ids})")
            else:
                existing_children = [cid for cid in state.children if cid != child_id]
                if len(existing_children) > 0:
                    _fail("state_integrity",
                          f"story authority {payload.get('authority_id')} already has children {existing_children}; subsequent child must declare parent_child_batch_id")
            if proposal.get("functional_parent_checkpoint") is not None:
                _fail("state_integrity",
                      "the first child under an authority inherits no functional checkpoint")
    return {}


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

    valid, errors = validate_against_schema_file(child_proposal, CHILD_PROPOSAL_SCHEMA)
    check("child_proposal_schema", valid, "state_integrity", str(errors))

    check("authority_binding",
          child_proposal["authority_id"] == payload["authority_id"] and child_proposal["work_ref"] == payload["work_ref"],
          "authority_missing_or_ambiguous",
          f"child binds {child_proposal['authority_id']}/{child_proposal['work_ref']}")

    check("authority_open", not state.closed, "authority_missing_or_ambiguous",
          f"authority already closed as {state.close_state}")

    child_id = child_proposal["child_batch_id"]
    persisted = [path.name for path in (authority.child_proposal_path(child_id), authority.child_proof_path(child_id))
                 if path.exists()]
    check("child_batch_id_unused", child_id not in state.children and not persisted, "state_integrity",
          f"child batch {child_id} was already derived under story authority {authority.authority_id} "
          f"(state {(state.children.get(child_id) or {}).get('state') or 'none'}, persisted {persisted}); "
          "a child_batch_id is derived once and never re-derived",
          child_batch_id=child_id)

    check("spec_immutable",
          child_proposal["authorized_spec_sha256"] == payload["authorized_spec_sha256"]
          and child_proposal["authorized_spec_revision"] == payload["authorized_spec_revision"],
          "unexpected_revision_drift",
          f"child declares spec {child_proposal['authorized_spec_sha256'][:16]} but the authority froze "
          f"{payload['authorized_spec_sha256'][:16]}")

    scope = payload["authorized_write_scope"]
    authorized_union = _scope_paths(scope)
    child_union = list(child_proposal["required_mutation_targets"]) + list(child_proposal["conditional_mutation_targets"])
    outside = sorted({path for path in child_union if not _within(path, authorized_union)})
    # §2.4: the union is what must be contained. A path the parent authorized conditionally may
    # legitimately become required in the child after a factual Checker finding.
    check("scope_subset", not outside, "scope_expansion", f"paths outside the parent envelope: {outside}",
          outside=outside)

    parent_forbidden = set(scope.get("forbidden_paths") or [])
    child_forbidden = set(child_proposal["forbidden_paths"])
    check("forbidden_monotonic", parent_forbidden <= child_forbidden, "scope_expansion",
          f"the child dropped forbidden path(s) {sorted(parent_forbidden - child_forbidden)}")

    collisions = sorted({path for path in child_union if _within(path, child_forbidden)})
    check("no_forbidden_target", not collisions, "scope_expansion",
          f"the child authorizes path(s) it also forbids: {collisions}")

    protected_violations = assert_protected_paths_monotonic(
        payload.get("protected_paths") or [], child_proposal.get("protected_paths") or [])
    check("protected_paths_monotonic", not protected_violations, "protected_path_violation",
          canonical_json(protected_violations), violations=protected_violations)

    expanded = sorted(key for key in EFFECT_KEYS
                      if child_proposal["allowed_effects"].get(key) and not payload["allowed_effects"].get(key))
    check("effects_subset", not expanded, "effect_expansion", f"the child enables effect(s) the parent denied: {expanded}",
          effects=expanded)

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
    if previous_id:
        # A parent this authority never derived is not a parent. Treating an unknown id as
        # "no predecessor" would let a child skip the functional checkpoint entirely by naming
        # a batch that does not exist.
        check("parent_child_batch_known", previous_id in state.children, "state_integrity",
              f"parent_child_batch_id {previous_id!r} was never derived under this authority",
              known=sorted(state.children))
        check("parent_child_batch_closed", state.closure_of(previous_id) is not None, "state_integrity",
              f"child batch {previous_id!r} has not closed; its reviewed commit does not exist yet")
        # A rework child exists only because of residual findings; it cannot omit them.
        check("residual_action_items_supplied", action_items is not None, "state_integrity",
              f"child {child_proposal['child_batch_id']} continues {previous_id!r} but no residual action items "
              "were supplied to derive it from")
    else:
        existing_children = [cid for cid in state.children if cid != child_proposal["child_batch_id"]]
        check("first_child_has_no_predecessor", len(existing_children) == 0, "state_integrity",
              f"story authority {authority.authority_id} already has children {existing_children}; subsequent child must declare parent_child_batch_id")
    previous_closure = state.closure_of(previous_id) if previous_id else None
    unresolved_digest = ""
    if action_items is not None:
        eligible, blockers = derivation_eligibility(action_items, payload, spec_paths)
        if not eligible:
            reason = _eligibility_stop_reason(blockers)
            checks.append({"check": "patch_only_findings", "result": "fail"})
            authority.hard_stop(reason, f"patch_only_findings: {canonical_json(blockers)}", blockers=blockers)
        checks.append({"check": "patch_only_findings", "result": "pass"})
        unresolved_digest = unresolved_action_items_digest(action_items)
        declared_digest = unresolved_action_items_digest(child_proposal["derived_from_action_items"])
        check("derived_from_findings", declared_digest == unresolved_digest, "state_integrity",
              "the child is not derived from the residual findings it claims")

    if previous_closure is not None:
        expected = {"commit": previous_closure["checker_reviewed_commit"],
                    "tree": previous_closure["checker_reviewed_tree"],
                    "child_batch_id": previous_closure["child_batch_id"]}
        check("functional_checkpoint_inherited", child_proposal.get("functional_parent_checkpoint") == expected,
              "state_integrity",
              f"the child must start exactly at the unmerged commit the previous Checker reviewed "
              f"({expected['commit'][:12]}), got {(child_proposal.get('functional_parent_checkpoint') or {}).get('commit', 'none')}",
              expected=expected, observed=child_proposal.get("functional_parent_checkpoint"))
        if unresolved_digest:
            check("unresolved_items_match_closure",
                  previous_closure.get("unresolved_action_items_digest") == unresolved_digest,
                  "state_integrity", "the residual findings differ from the ones recorded when the parent closed")
        try:
            assert_residual_lineage(child_proposal, state, payload, spec_paths=spec_paths)
            checks.append({"check": "residual_lineage", "result": "pass"})
        except HardStop as stop:
            checks.append({"check": "residual_lineage", "result": "fail"})
            authority.hard_stop(stop.reason, stop.detail, check="residual_lineage", **stop.evidence)
    else:
        check("first_child_has_no_checkpoint", child_proposal.get("functional_parent_checkpoint") is None,
              "state_integrity", "the first child under an authority inherits no functional checkpoint")

    parent_authority_digest = authority.root_digest
    parent_batch_digest = ""
    if previous_id:
        derivation = (state.children.get(previous_id) or {}).get("derivation") or {}
        parent_authority_digest = derivation.get("derivation_proof_digest") or authority.root_digest
        parent_batch_digest = derivation.get("child_proposal_digest", "")
    proof = {
        "schema_version": 1,
        "authority_id": authority.authority_id,
        "work_ref": payload["work_ref"],
        "child_batch_id": child_proposal["child_batch_id"],
        "parent_child_batch_id": previous_id,
        "root_authority_digest": authority.root_digest,
        "parent_authority_digest": parent_authority_digest,
        "parent_batch_digest": parent_batch_digest,
        "child_proposal_digest": digest_of(child_proposal),
        "functional_parent_checkpoint": child_proposal.get("functional_parent_checkpoint"),
        "unresolved_action_items_digest": unresolved_digest,
        # Recorded so persistence and bind recompute spec_status against the same specification.
        "spec_paths": sorted({Path(str(path)).as_posix() for path in spec_paths}),
        "granted_model_calls": granted,
        "checks": checks,
    }
    proof["derivation_proof_digest"] = digest_of(proof)
    return proof


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


def assert_protected_paths_intact(
    repo: str | Path,
    payload: dict,
    *,
    dirty_paths: list[str] | None = None,
    child_protected_paths: Iterable[dict] = (),
    baseline_commit: str | None = None,
) -> list[dict]:
    """Verify the authority's protected paths against the tree. Any violation is a hard stop.

    `child_protected_paths` adds what a derived child declared on top of the root (monotonicity
    means it can only add or repeat). With `baseline_commit`, read_only is judged against that
    commit rather than HEAD, so a change committed in an earlier round or by an earlier child of
    the lineage is still a change; if git cannot answer for that baseline the path is
    unverifiable, never assumed untouched. exact_file_hash and exact_set_snapshot always judge
    the tree as it is now.
    """
    protected = list(payload.get("protected_paths") or [])
    seen = {canonical_json(item) for item in protected if isinstance(item, dict)}
    for item in child_protected_paths or ():
        if isinstance(item, dict) and canonical_json(item) not in seen:
            seen.add(canonical_json(item))
            protected.append(item)
    unverifiable: list[dict] = []
    read_only = [item for item in protected if isinstance(item, dict) and item.get("policy") == "read_only"]
    if dirty_paths is None and baseline_commit is not None and read_only:
        dirty_paths = git_changed_paths(repo, baseline_commit)
        if dirty_paths is None:
            unverifiable = [{"pattern": str(item.get("pattern", "")), "policy": "read_only",
                             "violation": "protected_read_only_unverifiable",
                             "detail": f"git could not report the changes since baseline {baseline_commit!r}"}
                            for item in read_only]
            # Containment and the exact policies are still verified; only the change set is unknown.
            dirty_paths = []
    violations = unverifiable + verify_protected_paths(repo, protected, dirty_paths=dirty_paths)
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


# Batch `permitted_effects` key -> child proposal `allowed_effects` key. `ci_rerun` has no
# counterpart: re-running a CI job mutates nothing in the repository, so the envelope does not
# govern it. Everything else must map, and an unmapped key is refused rather than ignored.
_EFFECT_MAP = {
    "local_write": "local_write", "local_commit": "local_commit", "local_merge": "local_merge",
    "pull_request": "pull_request", "push": "push", "tag": "tag", "release": "release",
    "pull_request_merge": "merge",
}
_UNGOVERNED_EFFECTS = ("ci_rerun",)


def assert_batch_matches_child_proposal(*, batch: dict, units: Iterable[Any], proposal: dict, payload: dict) -> None:
    """Prove that the batch about to run is no wider than its derived child proposal and root authority envelope."""
    assert_child_proposal_within_envelope(proposal=proposal, payload=payload)

    auth = batch.get("authorization") or {}
    if auth.get("story_authority_id") != proposal["authority_id"]:
        raise HardStop("authority_missing_or_ambiguous",
                       f"batch names authority {auth.get('story_authority_id')!r} but the proposal is for "
                       f"{proposal['authority_id']!r}")
    if auth.get("child_proposal_digest") != digest_of(proposal):
        raise HardStop("state_integrity", "batch child_proposal_digest does not reproduce the derived proposal")

    story_ref = payload["work_ref"]
    authorized_union = list(proposal["required_mutation_targets"]) + list(proposal["conditional_mutation_targets"])
    forbidden = list(proposal["forbidden_paths"])
    root_authorized_union = _scope_paths(payload["authorized_write_scope"])
    root_forbidden = set(payload["authorized_write_scope"].get("forbidden_paths") or [])

    observed = list(units)
    if len(observed) != 1:
        raise HardStop("new_work_outside_frozen_batch",
                       f"AUTO_STORY v1 derives one authorized Story per child batch, got {len(observed)} units")
    unit = observed[0]
    work_ref = str(getattr(unit, "id", ""))
    if work_ref != story_ref:
        raise HardStop("bad_spec", f"child batch unit {work_ref!r} is not the authorized Story {story_ref!r}")
    if str(getattr(unit, "spec_digest", "")) != payload["authorized_spec_sha256"]:
        raise HardStop("unexpected_revision_drift",
                       f"unit {work_ref} specification differs from the hash frozen in Story Authority")

    scope_paths = list(getattr(unit, "scope_paths", []) or [])
    outside = sorted({path for path in scope_paths if not _within(path, authorized_union)})
    if outside:
        raise HardStop("scope_expansion",
                       f"unit {work_ref} may write {outside}, outside the derived proposal", outside=outside)
    outside_root = sorted({path for path in scope_paths if not _within(path, root_authorized_union)})
    if outside_root:
        raise HardStop("scope_expansion",
                       f"unit {work_ref} may write {outside_root}, outside the root authority envelope", outside=outside_root)

    collides = sorted({path for path in scope_paths if _within(path, forbidden)})
    if collides:
        raise HardStop("scope_expansion",
                       f"unit {work_ref} may write {collides}, which the proposal forbids", collides=collides)
    collides_root = sorted({path for path in scope_paths if _within(path, root_forbidden)})
    if collides_root:
        raise HardStop("scope_expansion",
                       f"unit {work_ref} may write {collides_root}, which the root authority envelope forbids", collides=collides_root)

    effects = auth.get("permitted_effects") or {}
    unmapped = sorted(set(effects) - set(_EFFECT_MAP) - set(_UNGOVERNED_EFFECTS))
    if unmapped:
        raise HardStop("effect_expansion", f"batch declares ungoverned effect(s): {unmapped}")
    expanded = sorted(key for key, mapped in _EFFECT_MAP.items()
                      if effects.get(key) and not proposal["allowed_effects"].get(mapped))
    if expanded:
        raise HardStop("effect_expansion",
                       f"batch enables effect(s) the derived proposal denies: {expanded}", effects=expanded)
    expanded_root = sorted(key for key, mapped in _EFFECT_MAP.items()
                           if effects.get(key) and not payload["allowed_effects"].get(mapped))
    if expanded_root:
        raise HardStop("effect_expansion",
                       f"batch enables effect(s) the root authority envelope denies: {expanded_root}", effects=expanded_root)

    granted = int(proposal["model_call_budget"])
    declared = int((batch.get("budget") or {}).get("max_model_calls", 0))
    if declared > granted:
        raise HardStop("model_call_budget_exhausted",
                       f"batch declares {declared} model calls but the child proposal grants {granted}")
    global_budget = int(payload.get("global_model_call_budget", 0))
    if declared > global_budget:
        raise HardStop("model_call_budget_exhausted",
                       f"batch declares {declared} model calls but the root authority envelope grants {global_budget}")


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
    try:
        snapshot = snapshot_set(args.repo, args.pattern)
    except (ProtectedPathError, OSError) as exc:
        raise Refusal(f"protected path snapshot refused: {exc}") from exc
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
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
