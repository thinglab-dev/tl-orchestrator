#!/usr/bin/env python3
"""Optional stdlib supervisor for one authorized unit; transport only, not approval.

The caller owns authority, scope, models and gates. This script never chooses a
model, never invents a command and never approves a story: it starts one already
authorized command line, keeps its raw output on disk and returns a compact
receipt. A zero exit code means the transport worked, not that the unit is good.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

# Liveness of a supervisor is proven by an exclusive file lock, never by a pid: a pid can be
# recycled and a file left on disk survives a crash. Only one of these modules exists per
# platform, and a platform that offers neither reports liveness as unknown instead of guessing.
fcntl = None
msvcrt = None
with contextlib.suppress(ImportError):
    import fcntl  # type: ignore[no-redef]
with contextlib.suppress(ImportError):
    import msvcrt  # type: ignore[no-redef]

SCHEMA_VERSION = 1
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

UNIT_PATTERN = "ASCII letter or digit, then letters, digits, dot, dash or underscore"
UNIT_MAX = 64
AUTHORIZATION_MAX = 256
ARGV_MAX = 64
TIMEOUT_MAX = 86400.0

RESULT_FIELDS = ("outcome", "decision", "blockers", "next_action", "observable_usage", "proof_refs")
OUTCOMES = ("delivered", "ready_for_delivery", "blocked", "failed")
SUCCESS_OUTCOMES = ("delivered", "ready_for_delivery")

# What a terminal result may carry on the wire. `report` rebuilds its answer from these
# names only, so a field that appeared in `result.json` by corruption or by a unit writing
# into the state directory is never retransmitted.
TRANSPORT_KEYS = (
    "schema", "job_id", "unit", "state", "effects", "exit_code", "started_at", "finished_at",
    "authorization_fingerprint", "manifest_fingerprint", "logs", "containment", "detail",
)
ADMITTED_KEYS = (
    "result_status", "result_bytes", "reason", "outcome", "decision", "next_action",
    "observable_usage", "blockers", "proof_refs", "blockers_omitted", "proof_refs_omitted",
    "dropped_fields", "dropped_fields_omitted",
)
KNOWN_RESULT_KEYS = frozenset(TRANSPORT_KEYS + ADMITTED_KEYS)
# What `finalize` always writes. A terminal record missing any of these was not produced by
# the supervisor of this unit, however well the rest of it is shaped: it is refused, never
# read as a success. `containment` belongs here because it is the only field that says what
# happened to the job tree: without it `swept_proven` has nothing to refuse and a record
# assembled without it would read as a delivered unit. `detail` stays out: most endings
# carry nothing to explain.
REQUIRED_RESULT_KEYS = (
    "schema", "job_id", "unit", "state", "effects", "exit_code", "started_at", "finished_at",
    "authorization_fingerprint", "manifest_fingerprint", "logs", "containment", "result_status",
)
CONTAINMENT_KEYS = {
    "kind": str,
    "established": bool,
    "unit_ran": bool,
    "swept": str,
    "sweep_failed": str,
    "accounted": str,
    "account_failed": str,
}
# Every containment record this supervisor writes carries these three, whatever the ending.
# A shorter one is incomplete, and an incomplete record is not evidence about the job tree.
CONTAINMENT_REQUIRED = ("kind", "established", "unit_ran")
# Log references this supervisor always opens and always names. A map missing either one is
# not the pair `finalize` writes, so the record carrying it answers for a different run.
LOG_NAMES = frozenset({"stdout", "stderr"})
# Scopes whose sweep proves the whole tree ended. Any other scope (`unproven`) leaves
# descendants unaccounted for, so the outcome read from disk cannot be called final.
PROVEN_SCOPES = ("job_object", "process_group")
# Scopes whose accounting covers a descendant that left the group with `setsid`, which a
# sweep of the group by definition cannot reach. Any other scope (`unaccounted`) leaves an
# escapee free to rewrite the result file after this supervisor exits, so a record carrying
# it is read as indeterminate no matter how complete and terminal that record looks.
ACCOUNTED_SCOPES = ("job_object", "subreaper_scan")
TERMINAL_STATES = ("exited", "timeout", "crashed", "start_failed")
# What a claim carries on disk. The supervisor validates against this before obeying it,
# so a manifest that was planted, edited or written by another version is refused.
MANIFEST_KEYS = {
    "schema": int,
    "unit": str,
    "authorization_fingerprint": str,
    "cwd": str,
    "argv": list,
    "timeout": (int, float),
    "result_file": str,
    "lease_identity": str,
}
RESULT_STATUSES = ("absent", "missing", "unreadable", "oversized", "malformed", "admitted")
# What the binding of a job carries, beside the `jobs` tree rather than inside it. It is the
# record readers compare a claim against, so it is validated on the same terms as a claim.
ANCHOR_KEYS = {
    "schema": int,
    "unit": str,
    "lease_identity": str,
    "manifest_fingerprint": str,
    "authorization_fingerprint": str,
    "binding": str,
}
# The fields the short token names. `binding` itself is excluded: it is their digest.
BINDING_KEYS = ("schema", "unit", "lease_identity", "manifest_fingerprint", "authorization_fingerprint")
# Every state this schema ever writes to `status.json` or `result.json`. A state is a label
# from a closed set, so anything else found on disk is read as `unknown` instead of forwarded.
KNOWN_STATES = frozenset(TERMINAL_STATES + ("starting", "running"))
NAME_BYTES = 64

DEFAULT_MAX_BYTES = 4096
MIN_MAX_BYTES = 512
MAX_FIELD_BYTES = 512
MAX_LIST_ITEMS = 8
MAX_NAMES = 8
MAX_RESULT_BYTES = 262144
PATH_MAX_BYTES = 4096
CLAIM_WAIT_SECONDS = 5.0
# A claim is published by rename, and for a moment right after the name lands an open of it can
# still be refused: on Windows the name a rename just created can be held by the publication
# itself, and a reader that gets there inside that window is answered with a sharing denial
# instead of the claim that is already on disk. Reading that as an unusable claim turned a real
# concurrent `start` — the one case reuse exists for — into `invalid_input`. The denial is
# retried inside this budget and only inside it: past the budget the same answer is a claim this
# process cannot read, refused like every other unusable one. The budget is one-shot per call,
# so the worst a reader pays before that refusal is bounded by it.
CLAIM_PUBLISH_SECONDS = 1.0
# Marks the one refusal that is worth retrying, so the reason a reader hands back still carries
# the detail of the denial for the refusal that follows when the window closes.
CLAIM_PUBLISHING = "publishing: "
# Access denied, sharing violation, lock violation: what Windows answers while a name is held.
PUBLISH_WINERRORS = frozenset({5, 32, 33})
POLL_SECONDS = 0.05
TERM_GRACE_SECONDS = 1.0
REAP_WAIT_SECONDS = 5.0
# A descendant that left the group is signalled and then has to disappear from the child list
# of this supervisor. The bound keeps the accounting from hanging: past it the ending is
# reported as unaccounted instead of waited on forever.
ESCAPEE_GRACE_SECONDS = 3.0

LEASE_NAME = "supervisor.lock"
# The lease is a name in a directory the unit can write, so the name alone identifies nothing:
# a unit that replaces the file behind it leaves a lock nobody holds, which a reader would
# have read as an ending. The claim records which file the lease named when the job started —
# device and inode — and every reader compares the open handle against it. An identity that
# cannot be formed or compared is `unbound`, and nothing unbound is ever read as an ending.
LEASE_UNBOUND = "unbound"
LEASE_IDENTITY_MAX = 80
# Which file the lease named is recorded here as well as in the claim, and it is this copy
# that readers compare against. The claim lives inside the job directory, which is a directory
# the unit itself writes: a unit that replaces the lease and then rewrites `lease_identity`
# would otherwise choose the very string readers check it against. The binding is published
# once, exclusively, outside that directory, and a claim that no longer matches it proves
# nothing. What a same-user unit can still reach is named in `termination_proof`.
ANCHORS_DIR = "anchors"
# Binding answers that no amount of waiting can change, so a wait stops at once on them.
SETTLED_UNPROVABLE = ("replaced", "diverged", "unanchored")
BINDING_TOKEN_BYTES = 16
SUPERVISOR_NAME = "supervisor.json"
# A supervisor that was just spawned has not taken its lease yet, so an absent holder is only
# conclusive after this window. It bounds the wrong answer in both directions: no infinite wait
# on a dead supervisor, and no dead verdict on one that is still starting.
LEASE_GRACE_SECONDS = 5.0
LEASE_SUPPORTED = fcntl is not None or msvcrt is not None
# `finalize` writes the terminal file while the supervisor still holds its lease and releases
# it milliseconds later. A one-shot reader absorbs that window instead of calling a genuine
# record unfinished; it never waits on a supervisor that is really still running.
TERMINATION_SETTLE_SECONDS = 2.0

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_SUSPENDED = 0x00000004

HAS_WAITID = all(hasattr(os, name) for name in ("waitid", "P_PID", "WEXITED", "WNOWAIT", "WNOHANG"))

CORE_KEYS = ("schema", "job_id", "unit", "state", "effects")
OPTIONAL_ORDER = (
    "proof_refs",
    "observable_usage",
    "blockers",
    "decision",
    "next_action",
    "dropped_fields",
    "locators",
    "logs",
    "containment",
    "authorization_fingerprint",
    "manifest_fingerprint",
    "started_at",
    "finished_at",
    # Last to go: it is the one field of a `start` receipt that a later reader cannot rebuild
    # from disk, so dropping it early would cost the caller the only out of band check it has.
    "binding",
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFLICT = 3
EXIT_TIMEOUT = 4
EXIT_INDETERMINATE = 5
EXIT_UNIT_FAILED = 6


class JobError(Exception):
    """Explicit refusal carrying the exit code and the state to report."""

    def __init__(
        self,
        code: int,
        state: str,
        message: str,
        effects: str = "none",
        termination: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.state = state
        self.message = message
        self.effects = effects
        # Declared only where an ending was asked for and could not be proven.
        self.termination = termination


# --- text and payload limits -------------------------------------------------


def clip(value: object, limit: int = MAX_FIELD_BYTES) -> str:
    """Normalize, drop control characters and cut by encoded bytes, never codepoints."""
    text = unicodedata.normalize("NFC", value if isinstance(value, str) else str(value))
    text = "".join(
        " " if char in "\t\r\n" else char
        for char in text
        if char in "\t\r\n" or unicodedata.category(char)[0] != "C"
    )
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[: max(0, limit - 3)].decode("utf-8", "ignore") + "..."


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fits(payload: dict, max_bytes: int) -> bool:
    return len(dumps(payload).encode("utf-8")) <= max_bytes


def enforce_ceiling(payload: dict, max_bytes: int) -> dict:
    """Drop optional keys in a fixed order until the receipt fits the byte ceiling.

    The ceiling is a promise, not a preference: when even the core keys overflow, their
    strings are clipped and, as a last resort, the receipt collapses to a fixed minimum
    that reports the overflow instead of emitting content past the limit.
    """
    trimmed = dict(payload)
    for key in OPTIONAL_ORDER:
        if fits(trimmed, max_bytes):
            return trimmed
        if key in trimmed:
            trimmed.pop(key)
            trimmed["clipped"] = True
    if fits(trimmed, max_bytes):
        return trimmed
    core = {key: trimmed[key] for key in CORE_KEYS if key in trimmed}
    core["clipped"] = True
    for limit in (NAME_BYTES, 16):
        if fits(core, max_bytes):
            return core
        core = {
            key: clip(value, limit) if isinstance(value, str) else value
            for key, value in core.items()
        }
    if fits(core, max_bytes):
        return core
    return {"schema": SCHEMA_VERSION, "state": "receipt_overflow", "clipped": True}


def emit(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Always UTF-8 on the wire, so a console codepage cannot break a receipt."""
    data = (dumps(enforce_ceiling(payload, max_bytes)) + "\n").encode("utf-8")
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(data.decode("utf-8"))
        sys.stdout.flush()
        return
    stream.write(data)
    stream.flush()


# --- identity and state directory -------------------------------------------


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_unit(unit: str) -> str:
    if not unit or len(unit) > UNIT_MAX:
        raise JobError(EXIT_USAGE, "invalid_input", f"unit identifier must be 1..{UNIT_MAX} characters")
    head, tail = unit[0], unit[1:]
    allowed = set("._-")
    if not head.isascii() or not head.isalnum():
        raise JobError(EXIT_USAGE, "invalid_input", f"unit identifier must start with {UNIT_PATTERN}")
    for char in tail:
        if not char.isascii() or not (char.isalnum() or char in allowed):
            raise JobError(EXIT_USAGE, "invalid_input", f"unit identifier must use {UNIT_PATTERN}")
    return unit


def absolute(raw: str | Path) -> Path:
    """Normalize by text only; identity must not change when a path starts to exist."""
    return Path(os.path.abspath(os.path.expanduser(str(raw))))


def check_state_dir(raw: str) -> Path:
    state_dir = absolute(raw)
    for candidate in (state_dir, Path(os.path.realpath(state_dir))):
        try:
            candidate.relative_to(PACKAGE_ROOT)
        except ValueError:
            continue
        raise JobError(EXIT_USAGE, "invalid_input", "state directory must stay outside the published package")
    return state_dir


EXTENDED_PREFIX = "\\\\?\\"
EXTENDED_UNC_PREFIX = "\\\\?\\UNC\\"


def real(path: Path) -> Path:
    """Resolve links; the existing prefix of a path that does not exist yet is resolved too.

    Windows sometimes hands back the `\\\\?\\` extended spelling of the very same directory:
    when a concurrent creation makes the check of the plain spelling fail with a different
    error, `realpath` keeps the prefix. Two spellings of one directory would read as an
    escape here, so the prefix is normalized away. The link resolution itself is untouched.
    """
    resolved = os.path.realpath(path)
    if os.name == "nt":
        if resolved.startswith(EXTENDED_UNC_PREFIX):
            resolved = "\\\\" + resolved[len(EXTENDED_UNC_PREFIX):]
        elif resolved.startswith(EXTENDED_PREFIX):
            resolved = resolved[len(EXTENDED_PREFIX):]
    return Path(resolved)


def contained(child: Path, root: Path, message: str) -> None:
    """Refuse a spelling that looks contained but resolves elsewhere through a link."""
    try:
        real(child).relative_to(real(root))
    except ValueError:
        raise JobError(EXIT_USAGE, "invalid_input", message) from None


def check_component(path: Path, label: str) -> None:
    """An existing component of the state tree must be a directory, never a file.

    The containment checks below accept a file: its spelling stays inside and `realpath`
    resolves it fine. `mkdir` would then raise `FileExistsError` or `NotADirectoryError`
    outside any handler, so the caller would get a traceback instead of a receipt. The
    type is checked before any creation, claim, read or write happens.
    """
    try:
        if os.path.lexists(path) and not path.is_dir():
            raise JobError(EXIT_USAGE, "invalid_input", f"{label} exists and is not a directory")
    except OSError as exc:
        raise JobError(EXIT_USAGE, "invalid_input", f"{label} cannot be inspected: {exc.strerror or exc}") from None


def job_directory(state_dir: Path, unit: str) -> Path:
    jobs = state_dir / "jobs"
    job_dir = Path(os.path.normpath(jobs / unit))
    if job_dir.parent != jobs:
        raise JobError(EXIT_USAGE, "invalid_input", "job directory escapes the state directory")
    # Every command goes through this function, so one shape check here covers the writer
    # and the readers: a file where a directory belongs is refused in JSON, with no effects.
    check_component(state_dir, "state directory")
    check_component(jobs, "jobs directory")
    check_component(job_dir, "job directory")
    # The bindings live beside `jobs`, so `anchors` is a component of this tree too and is
    # checked here with the others. It was not, and a link left in place before the first
    # start was adopted: `write_anchor` created the directory when it was missing and wrote
    # straight through it when it was a link, publishing the binding of a unit outside the
    # state directory the caller named.
    anchors = state_dir / ANCHORS_DIR
    check_component(anchors, "anchors directory")
    # normpath is lexical only. `jobs`, or the unit directory itself, may already exist as a
    # link that keeps a contained spelling while pointing outside the state directory. Both are
    # resolved here, and every command goes through this function, so the refusal happens
    # before any mkdir, claim, read or write and no manifest, status or log lands outside.
    # It does not defeat an adversary who swaps a component after this check; that filesystem
    # race is not claimed.
    contained(jobs, state_dir, "jobs directory resolves outside the state directory through a link")
    contained(job_dir, jobs, "job directory resolves outside the state directory through a link")
    contained(anchors, state_dir, "anchors directory resolves outside the state directory through a link")
    # Identity is built on the lexical path, so the returned spelling must not change.
    return job_dir


def check_path_bytes(path: Path, label: str) -> Path:
    """One bound for paths, applied when a path is accepted and again when it is read back."""
    if len(str(path).encode("utf-8")) > PATH_MAX_BYTES:
        raise JobError(EXIT_USAGE, "invalid_input", f"{label} is longer than {PATH_MAX_BYTES} bytes")
    return path


def check_cwd(raw: str) -> Path:
    path = Path(os.path.realpath(absolute(raw)))
    check_path_bytes(path, "working directory")
    if not path.is_dir():
        raise JobError(EXIT_USAGE, "invalid_input", "working directory does not exist")
    return path


def check_timeout(value: object, label: str) -> float:
    """Finite, positive and bounded; NaN, infinity and zero are refused, never clamped."""
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise JobError(EXIT_USAGE, "invalid_input", f"{label} must be a number of seconds") from None
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        raise JobError(EXIT_USAGE, "invalid_input", f"{label} must be a finite number of seconds")
    if not 0 < seconds <= TIMEOUT_MAX:
        raise JobError(EXIT_USAGE, "invalid_input", f"{label} must be above zero and at most {TIMEOUT_MAX} seconds")
    return seconds


def check_max_bytes(value: object) -> int:
    """Accept a whole number of bytes and raise the usual refusal for anything else.

    Checked here, inside the caller's `JobError` boundary, instead of by `argparse`: a ceiling
    that the parser rejects would leave through its own usage message, which is neither JSON
    nor bounded, so the one contract the receipt offers would not hold for the one flag that
    sets its size. A value below the floor is clamped, as every other caller of `emit` clamps.
    """
    try:
        ceiling = int(str(value).strip(), 10)
    except (TypeError, ValueError):
        raise JobError(EXIT_USAGE, "invalid_input", "receipt ceiling must be a whole number of bytes") from None
    return max(MIN_MAX_BYTES, ceiling)


def check_result_file(raw: str | None, cwd: Path, job_dir: Path) -> Path:
    if raw is None:
        return check_path_bytes(job_dir / "unit-result.json", "result file")
    candidate = Path(raw)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise JobError(EXIT_USAGE, "invalid_input", "result file must be relative to the working directory")
    resolved = Path(os.path.normpath(cwd / candidate))
    try:
        resolved.relative_to(cwd)
    except ValueError:
        raise JobError(EXIT_USAGE, "invalid_input", "result file escapes the working directory") from None
    # The lexical check above cannot see a link: a component that already exists as a
    # symlink to the outside keeps a contained spelling while writing elsewhere. Resolving
    # the links refuses that preexisting escape. It does not defeat an adversary who swaps
    # a component after this check; that race is not claimed here.
    contained(resolved, cwd, "result file resolves outside the working directory through a link")
    check_path_bytes(resolved, "result file")
    # The lexical path is what identity is built on, so it must not change here.
    return resolved


def build_manifest(
    unit: str,
    authorization: str,
    cwd: Path,
    argv: list[str],
    timeout: float,
    result_file: Path,
    lease: str = LEASE_UNBOUND,
) -> dict:
    # `lease` is which file the lease of this job names, and it is filled in once the job
    # directory exists. It is deliberately outside the fingerprint below: identity of a unit
    # is its authorized command line, so reusing a job never turns on which inode was created.
    return {
        "schema": SCHEMA_VERSION,
        "unit": unit,
        "authorization_fingerprint": digest(authorization)[:16],
        "cwd": str(cwd),
        "argv": list(argv),
        "timeout": timeout,
        "result_file": str(result_file),
        "lease_identity": lease,
    }


def manifest_fingerprint(manifest: dict) -> str:
    identity = {key: manifest[key] for key in ("unit", "authorization_fingerprint", "cwd", "argv", "timeout", "result_file")}
    return digest(json.dumps(identity, ensure_ascii=False, sort_keys=True))[:16]


# --- atomic files ------------------------------------------------------------


def write_atomic(path: Path, payload: dict) -> None:
    """One rename per file; a failure here is reported, never retried in place."""
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(dumps(payload) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        # A write that failed leaves no half-written name behind for a reader to find.
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def read_json(path: Path, limit: int = MAX_RESULT_BYTES) -> dict | None:
    try:
        if path.stat().st_size > limit:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def publication_denial(exc: OSError) -> bool:
    """True when a refused open is the kind a publication in flight produces.

    The name was inspected a moment earlier in `read_claim_file`, so it is present and sized;
    an open of it that comes back denied is what a rename still holding that name answers.
    It is deliberately narrow — a denial, not any `OSError` — and it is not the proof of a
    publication, only the one answer that can be one. Time decides the rest: the caller
    retries it inside a bounded budget and refuses it past the budget.

    On POSIX no publication refuses a reader like this, so the class is empty in practice
    there and a denial that appears anyway costs the same bounded delay before the same
    refusal. That is preferred to a platform branch this test suite could not drive on both.
    """
    if getattr(exc, "winerror", None) is not None:
        return exc.winerror in PUBLISH_WINERRORS
    return exc.errno in (errno.EACCES, errno.EPERM)


def read_claim_file(path: Path, limit: int = MAX_RESULT_BYTES) -> tuple[str, dict | None]:
    """Read a claim and say which of the failures happened, because they differ.

    A claim arrives by rename, so before it lands the name is simply absent, and that is one
    window a reader may wait out. A file that is there and cannot be read as a claim —
    malformed, not UTF-8, larger than the ceiling, or not an object — is never going to
    become one, and waiting on it would answer a conflict for what is invalid input.

    A name that cannot even be inspected is a third kind: a denied permission or a broken
    component is not a rename in flight and will not resolve by waiting. Reading it as
    absence spent the claim window and then answered `conflict`, which names another process
    holding the unit, for what is an unusable state directory.

    The last kind is the narrow one: the name inspected fine and then the open was denied.
    That is what a publication holding the name it just created answers, so the reason is
    marked `publishing` and the caller retries it inside a bounded budget. The mark is on a
    refusal that is still a refusal: it carries its own detail, and nothing here waits.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return "absent", None
    except OSError as exc:
        return f"it cannot be inspected: {exc.strerror or exc}", None
    if size > limit:
        return f"it is larger than the {limit} byte ceiling for a claim", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "absent", None
    except UnicodeDecodeError:
        return "it is not valid UTF-8 text", None
    except ValueError:
        return "it is not valid JSON", None
    except OSError as exc:
        detail = f"it could not be read: {exc.strerror or exc}"
        return (CLAIM_PUBLISHING + detail if publication_denial(exc) else detail), None
    if not isinstance(data, dict):
        return "it is not an object", None
    return "claim", data


def write_status(job_dir: Path, unit: str, state: str, pid: int | None = None) -> None:
    """Snapshot only: the status path never accumulates history."""
    write_atomic(
        job_dir / "status.json",
        {
            "schema": SCHEMA_VERSION,
            "job_id": unit,
            "unit": unit,
            "state": state,
            "pid": pid,
            "updated_at": now(),
        },
    )


def log_reference(path: Path) -> dict:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"path": path.name, "bytes": size}


# --- receipts ----------------------------------------------------------------


def locators(job_dir: Path, manifest: dict) -> dict:
    """Every locator is bounded here: these strings come from disk and feed the receipt."""
    unit_result = manifest.get("result_file", "")
    if not isinstance(unit_result, str):
        unit_result = ""
    return {
        "job_dir": clip(str(job_dir), MAX_FIELD_BYTES),
        "stdout": "stdout.log",
        "stderr": "stderr.log",
        "status": "status.json",
        "result": "result.json",
        "unit_result": clip(os.path.basename(unit_result), NAME_BYTES),
    }


def receipt(job_dir: Path, manifest: dict, state: str, extra: dict | None = None) -> dict:
    """Successful receipt: identity, state and where to look. Nothing the caller cannot use.

    Fingerprints stay in the private manifest and in the identity check; a receipt that
    repeated them only paid bytes. States that carry an observable reason, such as a wait
    that timed out, pass it explicitly through `extra`.
    """
    unit = clip(manifest.get("unit", ""), UNIT_MAX)
    payload = {
        "schema": SCHEMA_VERSION,
        "job_id": unit,
        "unit": unit,
        "state": clip(state, NAME_BYTES),
        "locators": locators(job_dir, manifest),
    }
    if extra:
        payload.update(extra)
    return payload


def error_payload(unit: str, error: JobError) -> dict:
    payload = {
        "schema": SCHEMA_VERSION,
        "job_id": clip(unit, UNIT_MAX),
        "unit": clip(unit, UNIT_MAX),
        "state": clip(error.state, NAME_BYTES),
        "effects": error.effects,
        "error": clip(error.message),
    }
    if error.termination is not None:
        payload["termination"] = clip(error.termination, NAME_BYTES)
    return payload


# --- unit result admission ---------------------------------------------------


def admit_result(path: Path) -> dict:
    """Read the conductor's own final JSON under an allowlist; never copy narrative.

    What binds this file to the unit is `unbound_result`, checked before the spawn: the path
    was absent then, so anything read here appeared while this unit ran.
    """
    if not path.is_file():
        return {"result_status": "missing"}
    try:
        size = path.stat().st_size
    except OSError:
        return {"result_status": "unreadable"}
    if size > MAX_RESULT_BYTES:
        return {"result_status": "oversized", "result_bytes": size}
    data = read_json(path)
    if data is None:
        return {"result_status": "malformed"}
    admitted: dict = {"result_status": "admitted"}
    outcome = data.get("outcome")
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        return {"result_status": "malformed", "reason": "outcome missing or outside the allowlist"}
    admitted["outcome"] = outcome
    for field in ("decision", "next_action", "observable_usage"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            admitted[field] = clip(value)
    for field in ("blockers", "proof_refs"):
        value = data.get(field)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            items = [clip(item) for item in value[:MAX_LIST_ITEMS] if isinstance(item, (str, int, float))]
            if items:
                admitted[field] = items
            if len(value) > MAX_LIST_ITEMS:
                admitted[field + "_omitted"] = len(value) - MAX_LIST_ITEMS
    dropped = sorted(key for key in data if key not in RESULT_FIELDS)
    if dropped:
        admitted["dropped_fields"] = [clip(name, NAME_BYTES) for name in dropped[:MAX_NAMES]]
        if len(dropped) > MAX_NAMES:
            admitted["dropped_fields_omitted"] = len(dropped) - MAX_NAMES
    return admitted


def swept_proven(containment: object) -> bool:
    """Answer whether the sweep proved the whole job tree ended.

    A scope outside `PROVEN_SCOPES` (`unproven`) and a failed primitive are the same
    thing for this reader: descendants may still be running and writing. So is a record
    that is not there at all — nothing was proven about the tree, and reading absence as
    proof is how a record stripped of its containment would answer `known` with exit zero.
    """
    if not isinstance(containment, dict):
        return False
    if containment.get("sweep_failed"):
        return False
    return containment.get("swept") in PROVEN_SCOPES


def tree_accounted(containment: object) -> bool:
    """Answer whether escaped descendants were accounted for, not just the swept scope.

    A sweep of a process group cannot reach a descendant that left it with `setsid()`, and
    such a descendant outlives this supervisor: once the lease is gone it can replace the
    result file with a complete, terminal, forged record that no reader can tell from the
    unit's own. Only a record whose accounting names a scope that covers escapees, with no
    failure, may be read as final; missing accounting is refused like any other absence.
    """
    if not isinstance(containment, dict):
        return False
    if containment.get("account_failed"):
        return False
    return containment.get("accounted") in ACCOUNTED_SCOPES


def classify(state: str, exit_code: int | None, admitted: dict) -> tuple[str, int]:
    """Map transport state and admitted outcome to effects and exit code."""
    containment = admitted.get("containment")
    if state == "start_failed":
        if isinstance(containment, dict) and containment.get("unit_ran"):
            # It was already running when containment failed: the effects are unknown.
            return "uncertain", EXIT_INDETERMINATE
        return "none", EXIT_UNIT_FAILED
    if not swept_proven(containment):
        # Either the ending primitive failed or it proved nothing about the tree: part
        # of it may still be running and writing, so no outcome read from disk can be
        # called final here.
        return "uncertain", EXIT_INDETERMINATE
    if not tree_accounted(containment):
        # The group ended, but a descendant that had already left it is free to rewrite the
        # result after this supervisor exits. Nothing terminal can be claimed from that.
        return "uncertain", EXIT_INDETERMINATE
    if state == "timeout":
        return "uncertain", EXIT_TIMEOUT
    if state == "crashed":
        return "uncertain", EXIT_INDETERMINATE
    if admitted.get("result_status") != "admitted":
        return "uncertain", EXIT_INDETERMINATE
    if exit_code != 0 or admitted.get("outcome") not in SUCCESS_OUTCOMES:
        return "known", EXIT_UNIT_FAILED
    return "known", EXIT_OK


# --- job tree containment ----------------------------------------------------


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount",
        "WriteOperationCount",
        "OtherOperationCount",
        "ReadTransferCount",
        "WriteTransferCount",
        "OtherTransferCount",
    )]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("cntUsage", ctypes.c_uint32),
        ("th32ThreadID", ctypes.c_uint32),
        ("th32OwnerProcessID", ctypes.c_uint32),
        ("tpBasePri", ctypes.c_long),
        ("tpDeltaPri", ctypes.c_long),
        ("dwFlags", ctypes.c_uint32),
    ]


class ContainmentError(Exception):
    """The job tree could not be owned; a unit never runs outside containment."""

    def __init__(self, message: str, unit_ran: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.unit_ran = unit_ran


class Sweep:
    """What the ending primitive proved: a failed primitive never reads as contained.

    `scope` is the coverage actually proven; `failure` describes the primitive that
    did not work. A process or group that is provably gone is not a failure: there
    was nothing left to end, which is exactly the scope being claimed.
    """

    def __init__(self, scope: str, failure: str | None = None) -> None:
        self.scope = scope
        self.failure = failure


class Account:
    """Whether the tree was accounted for past the sweep, including escapees.

    A sweep reaches what is still inside the scope it swept. A descendant that
    left the scope first — `setsid()` on POSIX — survives that sweep, and once
    this supervisor exits and drops its lease there is nobody left to tell its
    writing apart from the unit's. `scope` names the mechanism that accounted
    for those escapees; `failure` says why accounting was not possible.
    """

    def __init__(self, scope: str, failure: str | None = None) -> None:
        self.scope = scope
        self.failure = failure


PR_SET_CHILD_SUBREAPER = 36


def become_subreaper() -> str | None:
    """Inherit escaped descendants so they can still be ended; the reason when impossible.

    A descendant that calls `setsid()` leaves the process group, so a sweep of the group
    cannot reach it. With this flag set, it is reparented here when its parent dies instead
    of to init, which is what makes the scan below able to see and end it.
    """
    if not sys.platform.startswith("linux"):
        return f"child subreaper is a Linux facility, unavailable on {sys.platform}"
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        ctypes.set_errno(0)
        if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
            return f"prctl(PR_SET_CHILD_SUBREAPER) failed with errno {ctypes.get_errno()}"
    except (OSError, AttributeError, ValueError, TypeError) as exc:
        return f"prctl could not be called: {type(exc).__name__}"
    return None


def own_children() -> set[int] | None:
    """Pids this process is the parent of right now; None when they cannot be read."""
    tasks = Path("/proc/self/task")
    pids: set[int] = set()
    try:
        for task in tasks.iterdir():
            try:
                listed = (task / "children").read_text(encoding="ascii")
            except OSError:
                # A thread that ended between listing and reading is not a missing answer.
                continue
            pids.update(int(item) for item in listed.split())
    except (OSError, ValueError):
        return None
    return pids


class Containment:
    """Own every process the unit creates, so ending the unit ends its tree.

    Signalling the direct child alone leaves descendants working after a
    timeout. Each platform branch below claims only the scope it can prove:
    `job_object` covers the whole tree, including a descendant that starts its
    own session; `process_group` covers the tree while it stays in the group.
    """

    kind = "none"

    def spawn_kwargs(self) -> dict:
        return {"close_fds": True}

    def adopt(self, process: subprocess.Popen) -> None:
        """Take ownership of the child before it can create any descendant."""

    def release(self, process: subprocess.Popen) -> None:
        """Let the owned child run."""

    def watch(self, process: subprocess.Popen, timeout: float) -> None:
        """Block until the unit leader is gone; raise TimeoutExpired past the deadline."""
        raise NotImplementedError

    def sweep(self, process: subprocess.Popen, graceful: bool) -> Sweep:
        """End whatever survives in the tree and report the scope actually proven."""
        raise NotImplementedError

    def account(self, process: subprocess.Popen) -> Account:
        """End descendants that left the swept scope and report how they were accounted for."""
        return Account("unaccounted", "this containment cannot enumerate escaped descendants")

    def reap(self, process: subprocess.Popen) -> int | None:
        """Collect the leader's exit code; None when it could not be collected."""
        if process.returncode is not None:
            return process.returncode
        try:
            return process.wait(timeout=REAP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            return None

    def close(self) -> None:
        """Release platform handles."""

    def describe(self, sweep: Sweep, account: Account | None = None) -> dict:
        # A sweep only happens over a unit that was spawned, so `unit_ran` is true here; it is
        # written out anyway, because the reader asks every record the same three questions.
        record = {"kind": self.kind, "established": True, "unit_ran": True, "swept": sweep.scope}
        if sweep.failure:
            record["sweep_failed"] = clip(sweep.failure, 160)
        if account is not None:
            record["accounted"] = account.scope
            if account.failure:
                record["account_failed"] = clip(account.failure, 160)
        return record


class PosixSessionContainment(Containment):
    """New session for the unit; signals go to the process group, never to a bare pid."""

    kind = "posix_process_group"

    def __init__(self) -> None:
        self.pgid: int | None = None
        self.reaped = False
        # Both happen before the unit exists: the flag so an escapee comes back here instead
        # of going to init, the snapshot so anything already ours is never mistaken for one.
        self.no_subreaper = become_subreaper()
        self.baseline = own_children()

    def spawn_kwargs(self) -> dict:
        return {"close_fds": True, "start_new_session": True}

    def adopt(self, process: subprocess.Popen) -> None:
        try:
            pgid = os.getpgid(process.pid)
        except OSError as exc:
            raise ContainmentError(f"process group of the unit is unknown: {exc}", unit_ran=True) from None
        if pgid != process.pid:
            raise ContainmentError("the unit did not become the leader of its own session", unit_ran=True)
        self.pgid = pgid

    def watch(self, process: subprocess.Popen, timeout: float) -> None:
        if self.pgid is None or not HAS_WAITID:
            # Without waitid the wait also reaps, so the sweep below stays unproven.
            process.wait(timeout=timeout)
            self.reaped = True
            return
        deadline = time.monotonic() + timeout
        while True:
            try:
                # WNOWAIT reads the exit without reaping: the pgid stays ours, so a
                # recycled pid can never receive our signals.
                info = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            except ChildProcessError:
                self.reaped = True
                return
            except OSError:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
                self.reaped = True
                return
            if info is not None:
                return
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(process.args, timeout)
            time.sleep(POLL_SECONDS)

    def sweep(self, process: subprocess.Popen, graceful: bool) -> Sweep:
        if self.pgid is None or self.reaped:
            # The leader was already reaped: its pid may belong to somebody else now.
            return Sweep("unproven")
        if graceful:
            outcome = self.signal_group(signal.SIGTERM)
            if outcome == "absent":
                # Nothing is left in the group; the scope is covered with nothing to end.
                return Sweep("process_group")
            if outcome != "sent":
                return Sweep("unproven", outcome)
            deadline = time.monotonic() + TERM_GRACE_SECONDS
            while time.monotonic() < deadline:
                time.sleep(POLL_SECONDS)
        outcome = self.signal_group(signal.SIGKILL)
        if outcome not in {"sent", "absent"}:
            # SIGKILL did not land: survivors may remain, so nothing is claimed.
            return Sweep("unproven", outcome)
        return Sweep("process_group")

    def account(self, process: subprocess.Popen) -> Account:
        """End what left the group, or say why this platform cannot answer for it."""
        if self.no_subreaper is not None:
            return Account("unaccounted", self.no_subreaper)
        if self.baseline is None:
            return Account("unaccounted", "the children of this supervisor could not be listed")
        if process.returncode is None:
            # An escapee is reparented here while its parent dies. Without the leader's ending
            # collected there is no moment at which the list below is known to be complete.
            return Account("unaccounted", "the unit leader did not end, so escapees may be hidden")
        deadline = time.monotonic() + ESCAPEE_GRACE_SECONDS
        while True:
            present = own_children()
            if present is None:
                return Account("unaccounted", "the children of this supervisor could not be listed")
            # This supervisor spawns exactly one child; anything else adopted after the sweep
            # left the unit's group behind, which is precisely what the sweep could not reach.
            escapees = present - self.baseline - {process.pid}
            if not escapees:
                return Account("subreaper_scan")
            for pid in sorted(escapees):
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
                with contextlib.suppress(OSError):
                    os.waitpid(pid, os.WNOHANG)
            if time.monotonic() >= deadline:
                return Account("unaccounted", f"{len(escapees)} escaped descendant(s) would not end")
            time.sleep(POLL_SECONDS)

    def signal_group(self, number: int) -> str:
        """`sent`, `absent` when the group is provably gone, or why the signal failed."""
        try:
            os.killpg(self.pgid, number)
        except ProcessLookupError:
            return "absent"
        except OSError as exc:
            return f"killpg({number}) failed: {type(exc).__name__} {exc.errno}"
        return "sent"

    def reap(self, process: subprocess.Popen) -> int | None:
        if self.reaped:
            return process.returncode
        return super().reap(process)


class JobObjectContainment(Containment):
    """Windows job object with kill-on-close, assigned before the child runs."""

    kind = "windows_job_object"

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    TH32CS_SNAPTHREAD = 0x00000004
    THREAD_SUSPEND_RESUME = 0x00000002
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    def __init__(self) -> None:
        loader = getattr(ctypes, "WinDLL", None)
        if loader is None:  # pragma: no cover - only reachable off Windows
            raise ContainmentError("job objects exist only on Windows")
        self.api = loader("kernel32", use_last_error=True)
        self.declare()
        handle = self.api.CreateJobObjectW(None, None)
        if not handle:
            raise ContainmentError(f"CreateJobObject failed with error {ctypes.get_last_error()}")
        self.handle = handle
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = self.api.SetInformationJobObject(
            ctypes.c_void_p(handle),
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not ok:
            error = ctypes.get_last_error()
            self.close()
            raise ContainmentError(f"kill-on-close could not be set on the job object: error {error}")

    def declare(self) -> None:
        """Explicit signatures: a handle truncated to 32 bits would target the wrong object."""
        handle, dword, boolean = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
        self.api.CreateJobObjectW.restype = handle
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.api.SetInformationJobObject.restype = boolean
        self.api.SetInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, dword]
        self.api.AssignProcessToJobObject.restype = boolean
        self.api.AssignProcessToJobObject.argtypes = [handle, handle]
        self.api.TerminateJobObject.restype = boolean
        self.api.TerminateJobObject.argtypes = [handle, ctypes.c_uint32]
        self.api.CloseHandle.restype = boolean
        self.api.CloseHandle.argtypes = [handle]
        self.api.CreateToolhelp32Snapshot.restype = handle
        self.api.CreateToolhelp32Snapshot.argtypes = [dword, dword]
        self.api.Thread32First.restype = boolean
        self.api.Thread32First.argtypes = [handle, ctypes.c_void_p]
        self.api.Thread32Next.restype = boolean
        self.api.Thread32Next.argtypes = [handle, ctypes.c_void_p]
        self.api.OpenThread.restype = handle
        self.api.OpenThread.argtypes = [dword, boolean, dword]
        self.api.ResumeThread.restype = dword
        self.api.ResumeThread.argtypes = [handle]

    def spawn_kwargs(self) -> dict:
        # Suspended: the child exists but cannot spawn anything before it is owned.
        return {"close_fds": True, "creationflags": CREATE_NO_WINDOW | CREATE_SUSPENDED}

    def adopt(self, process: subprocess.Popen) -> None:
        ok = self.api.AssignProcessToJobObject(
            ctypes.c_void_p(self.handle), ctypes.c_void_p(int(process._handle))
        )
        if not ok:
            raise ContainmentError(
                f"the unit could not be assigned to its job object: error {ctypes.get_last_error()}"
            )

    def release(self, process: subprocess.Popen) -> None:
        resumed = 0
        snapshot = self.api.CreateToolhelp32Snapshot(self.TH32CS_SNAPTHREAD, 0)
        if not snapshot or snapshot == self.INVALID_HANDLE:
            raise ContainmentError(f"thread snapshot failed with error {ctypes.get_last_error()}")
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(THREADENTRY32)
            more = self.api.Thread32First(ctypes.c_void_p(snapshot), ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID == process.pid:
                    thread = self.api.OpenThread(self.THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID)
                    if thread:
                        if self.api.ResumeThread(ctypes.c_void_p(thread)) != 0xFFFFFFFF:
                            resumed += 1
                        self.api.CloseHandle(ctypes.c_void_p(thread))
                more = self.api.Thread32Next(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        finally:
            self.api.CloseHandle(ctypes.c_void_p(snapshot))
        if not resumed:
            raise ContainmentError("the suspended unit could not be resumed, so it never ran")

    def watch(self, process: subprocess.Popen, timeout: float) -> None:
        # The pid is irrelevant here: the sweep below uses the job handle.
        process.wait(timeout=timeout)

    def sweep(self, process: subprocess.Popen, graceful: bool) -> Sweep:
        # The job object lives while this handle is open, so there is no "already gone"
        # case here: a zero return is a real failure and the tree stays unproven.
        if not self.api.TerminateJobObject(ctypes.c_void_p(self.handle), 1):
            return Sweep("unproven", f"TerminateJobObject failed with error {ctypes.get_last_error()}")
        return Sweep("job_object")

    def account(self, process: subprocess.Popen) -> Account:
        # Breakaway is never granted on this job, so a descendant cannot leave it: the
        # termination above already covered the whole tree, escapees included.
        return Account("job_object")

    def close(self) -> None:
        handle, self.handle = getattr(self, "handle", None), None
        if handle:
            # Kill-on-close is the last guarantee if this supervisor dies early.
            self.api.CloseHandle(ctypes.c_void_p(handle))


def open_containment() -> Containment:
    """Refuse to spawn where the tree cannot be owned, instead of pretending it is."""
    if os.name == "nt":
        return JobObjectContainment()
    if hasattr(os, "killpg") and hasattr(os, "setsid"):
        return PosixSessionContainment()
    raise ContainmentError("this platform offers no way to contain the job tree")


# --- supervise (local child, no AI calls) ------------------------------------


def spawn_kwargs(detached: bool) -> dict:
    """Flags for the supervisor itself; the unit is spawned through a containment."""
    kwargs: dict = {"close_fds": True}
    if os.name == "nt":
        flags = CREATE_NO_WINDOW
        if detached:
            flags |= DETACHED_PROCESS
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return kwargs


def is_crash(code: int | None) -> bool:
    """POSIX reports a signal as a negative code; Windows reports an NTSTATUS above 0xC0000000."""
    if code is None:
        return False
    if code < 0:
        return True
    return os.name == "nt" and code >= 0xC0000000


def discard(process: subprocess.Popen) -> None:
    """Kill a child that could not be contained; it must never be left running."""
    with contextlib.suppress(OSError):
        process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=REAP_WAIT_SECONDS)


def lock_exclusive(handle) -> bool:
    """Take the lock the platform offers; a refusal means somebody else already holds it."""
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            return False
    except OSError:
        return False
    return True


def unlock_exclusive(handle) -> None:
    with contextlib.suppress(OSError, ValueError):
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class Lease:
    """An open handle whose lock the operating system releases when this process ends."""

    def __init__(self, handle, status: str, detail: str) -> None:
        self.handle = handle
        self.status = status
        self.detail = detail

    @property
    def held(self) -> bool:
        return self.status == "held"

    def release(self) -> None:
        if self.handle is None:
            return
        unlock_exclusive(self.handle)
        with contextlib.suppress(OSError, ValueError):
            self.handle.close()
        self.handle = None


def lease_identity(status: os.stat_result) -> str:
    """Which file the platform says this is: device and inode, as one comparable string.

    A platform that does not number inodes answers zero for every file, and an identity that
    cannot tell two files apart is no identity at all: it is `unbound` and proves nothing.
    """
    if not status.st_ino:
        return LEASE_UNBOUND
    return f"{status.st_dev}:{status.st_ino}"


def usable_identity(value: object) -> bool:
    """Shape of a lease identity read from disk, checked before anything compares against it."""
    if not isinstance(value, str) or not 0 < len(value) <= LEASE_IDENTITY_MAX:
        return False
    if value == LEASE_UNBOUND:
        return True
    device, separator, inode = value.partition(":")
    if not separator or not inode.isdigit():
        return False
    return device.lstrip("-").isdigit()


def create_lease(path: Path) -> str:
    """Create the lease file of a job and answer the identity its supervisor must hold.

    `start` does this before it writes the claim, so the file the lease names is committed
    to disk together with the command line it belongs to. Every later reader compares what
    it opens against this string instead of trusting the name.
    """
    with open(path, "a+b") as handle:
        return lease_identity(os.fstat(handle.fileno()))


def claimed_lease_identity(job_dir: Path) -> str:
    """The identity the claim of this job recorded, or `unbound` when none can be read."""
    claim = read_json(job_dir / "manifest.json")
    value = claim.get("lease_identity") if isinstance(claim, dict) else None
    return value if usable_identity(value) else LEASE_UNBOUND


# --- the binding -------------------------------------------------------------


def anchor_path(job_dir: Path) -> Path:
    """Where the binding of this job lives: beside the `jobs` tree, never inside the job."""
    return job_dir.parent.parent / ANCHORS_DIR / (job_dir.name + ".json")


def binding_token(anchor: dict) -> str:
    """The short name of one binding: the fields it binds, digested. `start` returns it."""
    bound = {key: anchor[key] for key in BINDING_KEYS}
    return digest(json.dumps(bound, ensure_ascii=False, sort_keys=True))[:BINDING_TOKEN_BYTES]


def build_anchor(unit: str, manifest: dict) -> dict:
    """What a job is bound to: which file its lease named, and which claim that lease belongs to."""
    anchor = {
        "schema": SCHEMA_VERSION,
        "unit": unit,
        "lease_identity": manifest["lease_identity"],
        "manifest_fingerprint": manifest_fingerprint(manifest),
        "authorization_fingerprint": manifest["authorization_fingerprint"],
    }
    return dict(anchor, binding=binding_token(anchor))


def write_anchor(job_dir: Path, unit: str, manifest: dict) -> dict:
    """Publish the binding of this job exactly once, and answer what was published.

    `O_EXCL` is the whole point: this file is created with the job and never rewritten, so a
    second write of the same unit is an error rather than a new binding. A name that is
    already there when a fresh job directory was just created is left alone, and the caller
    refuses the start instead of adopting a record it did not write.
    """
    anchor = build_anchor(unit, manifest)
    path = anchor_path(job_dir)
    check_component(path.parent, "anchors directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(dumps(anchor) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return anchor


def read_anchor(job_dir: Path) -> dict | None:
    """The binding of this job as it was published, or `None` when none can be trusted.

    Shape is checked the way a claim is checked, for the same reason: this record decides
    what every reader compares a lease against, so a file that is merely present is not a
    binding. `binding` is recomputed rather than believed — a record whose token does not
    name its own fields is not one this schema wrote, whoever wrote it.
    """
    anchor = read_json(anchor_path(job_dir))
    if not isinstance(anchor, dict) or set(anchor) != set(ANCHOR_KEYS):
        return None
    for key, kind in ANCHOR_KEYS.items():
        if not isinstance(anchor[key], kind) or isinstance(anchor[key], bool):
            return None
    if anchor["schema"] != SCHEMA_VERSION or anchor["unit"] != job_dir.name:
        return None
    if not usable_identity(anchor["lease_identity"]) or anchor["lease_identity"] == LEASE_UNBOUND:
        return None
    if anchor["binding"] != binding_token(anchor):
        return None
    return anchor


def binding_check(job_dir: Path) -> tuple[str, str]:
    """Whether the claim still agrees with the binding, and which lease identity to expect.

    Answers `bound`, `unanchored` when no binding can be read, or `diverged` when the claim
    on disk is not the one the binding was published for. Only `bound` carries an identity;
    the other two answer `unbound`, which no reader ever reads as an ending.
    """
    anchor = read_anchor(job_dir)
    if anchor is None:
        return "unanchored", LEASE_UNBOUND
    claim = read_json(job_dir / "manifest.json")
    if not isinstance(claim, dict):
        return "diverged", LEASE_UNBOUND
    try:
        fingerprint = manifest_fingerprint(claim)
    except (KeyError, TypeError, ValueError):
        return "diverged", LEASE_UNBOUND
    if fingerprint != anchor["manifest_fingerprint"]:
        return "diverged", LEASE_UNBOUND
    for key in ("lease_identity", "authorization_fingerprint"):
        if claim.get(key) != anchor[key]:
            return "diverged", LEASE_UNBOUND
    return "bound", anchor["lease_identity"]


def lease_verdict(handle, expected: str) -> str:
    """Compare an open lease handle with the recorded identity: `same`, `other` or `unbound`.

    The comparison is made on the handle, never on the path: between a `stat` of the name and
    the lock taken on a descriptor the name can be made to point somewhere else, and only the
    descriptor says which file the lock was actually taken on.
    """
    if expected == LEASE_UNBOUND:
        return "unbound"
    try:
        actual = lease_identity(os.fstat(handle.fileno()))
    except (OSError, ValueError):
        return "unbound"
    if actual == LEASE_UNBOUND:
        return "unbound"
    return "same" if actual == expected else "other"


def claim_lease(path: Path, expected: str) -> Lease:
    """Hold the lease for as long as this supervisor lives; a crash releases it for us."""
    try:
        handle = open(path, "a+b")
    except OSError as exc:
        # Without a lease the supervisor still runs: collection then reads liveness as unknown.
        return Lease(None, "unavailable", clip(str(exc)))
    if not LEASE_SUPPORTED:
        with contextlib.suppress(OSError):
            handle.close()
        return Lease(None, "unsupported", "this platform offers no exclusive file lock")
    if not lock_exclusive(handle):
        with contextlib.suppress(OSError):
            handle.close()
        return Lease(None, "busy", "another supervisor already holds the lease of this job")
    if lease_verdict(handle, expected) == "other":
        # Somebody put another file behind the name before this supervisor got there. Holding
        # it would lock a decoy while every reader compares against the file the claim named.
        unlock_exclusive(handle)
        with contextlib.suppress(OSError):
            handle.close()
        return Lease(None, "replaced", "the lease path no longer names the file this claim recorded")
    return Lease(handle, "held", "")


def supervisor_liveness(job_dir: Path, expected: str | None = None) -> str:
    """Answer alive, gone, replaced, unbound or unknown; only a verified lease reads as gone.

    `alive` and `gone` are statements about the file the binding committed to. When the name
    leads somewhere else the answer is `replaced`, and when this platform or this binding
    cannot identify the file at all the answer is `unbound`. Neither is ever an ending.

    `expected` is the identity to compare against; left out, it is read from the binding of
    this job. It is never read from the claim: the claim sits in a directory the unit writes,
    so a unit that rewrote it would be choosing the string it is checked against.
    """
    if not LEASE_SUPPORTED:
        return "unknown"
    if expected is None:
        expected = binding_check(job_dir)[1]
    path = job_dir / LEASE_NAME
    if not path.exists():
        # The supervisor may not have reached its lease yet: absence proves nothing.
        return "unknown"
    try:
        handle = open(path, "a+b")
    except OSError:
        return "unknown"
    try:
        verdict = lease_verdict(handle, expected)
        if verdict != "same":
            return "replaced" if verdict == "other" else "unbound"
        if not lock_exclusive(handle):
            return "alive"
        unlock_exclusive(handle)
        return "gone"
    finally:
        with contextlib.suppress(OSError):
            handle.close()


# Why an ending could not be proven, in the words the receipt carries. Every answer other
# than `proven` refuses the terminal result; these say which of them happened.
UNPROVABLE_END = {
    "unproven": "no supervisor of this unit can be shown to have ended, so its terminal result is not final",
    "unsupported": "this platform offers no exclusive file lock, so the ending of this unit cannot be "
    "proven and its terminal result is not final",
    "replaced": "the lease path of this unit no longer names the file its claim recorded, so no ending "
    "can be proven here and its terminal result is not final",
    "unanchored": "no binding was published for this unit when it started, so there is nothing here to "
    "check its claim against, no ending can be proven and its terminal result is not final",
    "diverged": "the claim of this unit no longer matches the binding published when it started, so no "
    "ending can be proven here and its terminal result is not final",
}

# Why a supervisor refuses to run a job directory whose claim it cannot trust.
BINDING_REFUSED = {
    "unanchored": "no binding was published for this unit; a claim nothing vouches for is not supervised",
    "diverged": "the claim of this unit no longer matches the binding published when it started; "
    "this job directory was tampered with and is not run again",
}

# Why a second `start` on the same manifest refuses to hand back what is already there.
REUSE_REFUSED = {
    "unanchored": "this unit exists with no binding to check its claim against; it is never reused",
    "diverged": "the claim of this unit was tampered with after it started; it is never reused",
}


def termination_proof(job_dir: Path) -> str:
    """Say whether the supervisor of this unit provably finished: `proven`, `running`,
    `replaced`, `diverged`, `unanchored`, `unproven` or `unsupported`.

    The terminal file lives in a directory the unit itself can reach, and a unit that reads
    `manifest.json` can rebuild every field of a terminal record, fingerprints included. So
    its content proves nothing about who wrote it or when. The lease is different: it is held
    by the supervisor process and released by the operating system when that process ends, so
    no file a unit writes can make it look ended.

    What a unit can still do to a file is replace it. The lock is taken on a descriptor, but
    the descriptor is reached through a name, and an unlocked file put behind that name would
    read as a supervisor that ended while the real one is still running. That is why the file
    itself is identified — `start` records the device and inode it created, and every reader
    compares the handle it opened against that. A name that leads to another file is
    `replaced`, an identity that cannot be compared is not an ending either, and success is
    read from the record only once this answers `proven`.

    Where that identity is kept is the other half. Inside `manifest.json` it was worth
    nothing: the claim sits in the job directory, the unit writes there, and a unit that
    replaced the lease could rewrite the string readers compared against in the same breath —
    `lease_identity` is outside `manifest_fingerprint` by design, so nothing downstream even
    changed. It is published instead as the binding of the job, once and exclusively, outside
    that directory, and a claim that no longer matches its binding is `diverged` while a job
    with no readable binding is `unanchored`. Neither is an ending.

    The residue is named rather than hidden: the binding is a file, and a same-user unit that
    derives the state directory from `TL_JOB_DIR` can reach it too. Nothing kept on the same
    filesystem under the same owner closes that. What does close it is the token `start`
    returns out of band: `wait --expect-binding` and `result --expect-binding` compare the
    binding on disk against the one the caller was handed, and a rewritten binding is a
    different token. A caller that passes it is not relying on the unit leaving files alone.
    """
    if not LEASE_SUPPORTED:
        # No exclusive lock on this platform: nothing here can prove an ending either way.
        return "unsupported"
    state, expected = binding_check(job_dir)
    if state != "bound":
        return state
    liveness = supervisor_liveness(job_dir, expected)
    if liveness == "alive":
        return "running"
    if liveness == "gone":
        return "proven"
    if liveness == "replaced":
        return "replaced"
    return "unproven"


def proven_termination(job_dir: Path, settle: float = TERMINATION_SETTLE_SECONDS) -> str:
    """The same answer, after waiting out the window between the terminal write and the exit.

    Only `running` is polled: it is the one answer that legitimately changes on its own, and
    the wait is bounded by `settle`. `unproven` and `unsupported` are not waited on, because
    no amount of waiting turns a missing lease into a proof.
    """
    deadline = time.monotonic() + max(0.0, settle)
    while True:
        proof = termination_proof(job_dir)
        if proof != "running" or time.monotonic() >= deadline:
            return proof
        time.sleep(POLL_SECONDS)


def record_supervisor(job_dir: Path, unit: str, lease: Lease, started: str) -> None:
    """Identity for a human reader; the lease, not this file, is what proves liveness."""
    with contextlib.suppress(OSError):
        write_atomic(
            job_dir / SUPERVISOR_NAME,
            {
                "schema": SCHEMA_VERSION,
                "job_id": unit,
                "unit": unit,
                "pid": os.getpid(),
                "started_at": started,
                "lease": lease.status,
            },
        )


class UnitRun:
    """What is known so far about one unit, so any exit path can still finalize it."""

    def __init__(self) -> None:
        self.state = "running"
        self.exit_code: int | None = None
        self.detail = ""
        self.containment: dict | None = None
        self.unit_ran = False
        self.ended = False

    def note(self, detail: str) -> None:
        self.detail = "; ".join(filter(None, (self.detail, detail)))


def run_under_containment(job_dir: Path, manifest: dict, run: UnitRun, out, err, environment: dict) -> None:
    """Spawn the unit inside its containment and end that tree before returning."""
    process = None
    containment = None
    try:
        try:
            containment = open_containment()
            process = subprocess.Popen(  # noqa: S603 - argv comes closed from the caller
                manifest["argv"],
                cwd=manifest["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=environment,
                **containment.spawn_kwargs(),
            )
            run.unit_ran = True
            containment.adopt(process)
            containment.release(process)
        except ContainmentError as exc:
            run.state = "start_failed"
            run.note(f"job tree containment refused: {exc.message}")
            run.containment = {
                "kind": containment.kind if containment is not None else "none",
                "established": False,
                "unit_ran": exc.unit_ran,
            }
            run.unit_ran = exc.unit_ran
            if process is not None:
                discard(process)
            process = None
            run.ended = True
        except (OSError, ValueError) as exc:
            run.state = "start_failed"
            run.note(str(exc))
            # The spawn itself refused, so no unit exists and no tree was ever established;
            # the record says exactly that instead of leaving the ending unaccounted for.
            run.containment = {
                "kind": containment.kind if containment is not None else "none",
                "established": False,
                "unit_ran": False,
            }
            process = None
            run.ended = True
        if process is not None and containment is not None:
            write_status(job_dir, manifest["unit"], "running", process.pid)
            try:
                containment.watch(process, manifest["timeout"])
                run.state = "exited"
            except subprocess.TimeoutExpired:
                run.state = "timeout"
                run.note(f"unit exceeded {manifest['timeout']} seconds")
            # The sweep runs before the leader is reaped, so the identity signalled is
            # still the one this supervisor owns, never a recycled pid.
            sweep = containment.sweep(process, graceful=run.state == "timeout")
            run.exit_code = containment.reap(process)
            # Accounting only makes sense over a swept scope: where the sweep proved nothing,
            # the tree is already read as indeterminate and killing adopted pids would end
            # processes this supervisor never proved were the unit's.
            account = containment.account(process) if sweep.scope in PROVEN_SCOPES else None
            run.containment = containment.describe(sweep, account)
            run.ended = True
            if account is not None and account.failure:
                # The group ended but an escapee may still be out there, free to write after
                # this supervisor is gone: the record says so instead of claiming a final tree.
                run.note(f"escaped descendants not accounted for: {account.failure}")
            if sweep.failure:
                # An unended tree may still be writing: say so instead of reporting scope.
                run.note(f"job tree not proven ended: {sweep.failure}")
            elif sweep.scope not in PROVEN_SCOPES:
                # Nothing failed, but nothing was proven either: the leader was already
                # reaped, so descendants could not be signalled as a group.
                run.note(f"job tree not proven ended: sweep scope {sweep.scope}")
            if run.state == "exited" and run.exit_code is None:
                run.state = "crashed"
                run.note("the unit leader left without a collectable exit code")
            if run.state == "exited" and is_crash(run.exit_code):
                run.state = "crashed"
                run.note(f"abnormal termination code {run.exit_code}")
    finally:
        # Whatever failed above, the tree is ended here by the same containment that owns it:
        # a unit must never outlive the supervisor that answers for it.
        if not run.ended and process is not None and containment is not None:
            with contextlib.suppress(Exception):
                sweep = containment.sweep(process, graceful=False)
                run.containment = containment.describe(sweep)
            with contextlib.suppress(Exception):
                run.exit_code = containment.reap(process)
            if run.containment is not None and swept_proven(run.containment):
                # This path is the abnormal one, so the accounting is attempted but never
                # assumed: a record without it is refused, which is the safe direction.
                with contextlib.suppress(Exception):
                    account = containment.account(process)
                    run.containment = containment.describe(sweep, account)
            run.ended = True
        if containment is not None:
            with contextlib.suppress(Exception):
                containment.close()


def unbound_result(manifest: dict) -> str | None:
    """Say why the result file could not belong to this run, or `None` when it can.

    Admission reads whatever JSON sits at `result_file`, and nothing in that payload names
    the execution that produced it. A file already on disk when the unit starts could carry
    a success written by an earlier unit, so a command that exits zero without ever touching
    `TL_JOB_RESULT` would inherit it. Requiring absence before the spawn is what binds the
    admitted payload to this run: anything read afterwards appeared while this unit ran.

    A path whose existence cannot even be inspected is refused the same way; guessing that
    it is absent is exactly the inherited success this guard exists to refuse. Only
    `FileNotFoundError` proves absence, so the inspection is done with `os.lstat` rather than
    `os.path.lexists`: the helper answers `False` for a denied directory just as it does for a
    missing file, which would read an uninspectable path as a clean slate and spawn anyway.
    """
    path = Path(manifest["result_file"])
    try:
        os.lstat(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        detail = getattr(exc, "strerror", None) or exc
        return f"the result file cannot be inspected, so nothing binds it to this run: {detail}"
    return "the result file already exists, so its content cannot be bound to this run"


def execute_unit(job_dir: Path, manifest: dict, run: UnitRun) -> None:
    """Open the raw logs and run the unit; a failure to open them leaves no child behind."""
    unbound = unbound_result(manifest)
    if unbound is not None:
        # Refused before the spawn: the unit never runs, so there are no effects to report
        # and `finalize` keeps the admission absent instead of reading the stale file.
        run.state = "start_failed"
        run.note(unbound)
        run.containment = {"kind": "none", "established": False, "unit_ran": False}
        run.ended = True
        return
    environment = dict(os.environ)
    environment.update(
        {
            "TL_JOB_ID": manifest["unit"],
            "TL_JOB_DIR": str(job_dir),
            "TL_JOB_RESULT": str(Path(manifest["result_file"])),
        }
    )
    with open(job_dir / "stdout.log", "wb") as out, open(job_dir / "stderr.log", "wb") as err:
        run_under_containment(job_dir, manifest, run, out, err, environment)


def internal_failure(run: UnitRun, exc: BaseException) -> None:
    """A supervisor that broke mid-flight reports what the unit may have done, never none."""
    run.note(f"the supervisor failed internally: {type(exc).__name__}: {exc}")
    if run.unit_ran:
        # The unit existed, so its effects are unknown: crashed keeps them uncertain.
        run.state = "crashed"
        if run.containment is None:
            run.containment = {"kind": "none", "established": False, "unit_ran": True}
    elif run.state not in TERMINAL_STATES:
        run.state = "start_failed"
        if run.containment is None:
            run.containment = {"kind": "none", "established": False, "unit_ran": False}


def finalize(job_dir: Path, manifest: dict, run: UnitRun, started: str) -> int:
    """Write the single terminal file for this unit, or report that none could be written."""
    unit = manifest["unit"]
    if run.state not in TERMINAL_STATES:
        run.state = "crashed"
        run.note("the supervisor ended without a terminal state for this unit")
    if run.state in {"exited", "crashed"}:
        try:
            admitted = admit_result(Path(manifest["result_file"]))
        except OSError as exc:
            admitted = {"result_status": "unreadable", "reason": clip(str(exc))}
    else:
        admitted = {"result_status": "absent"}
    # Every terminal record carries one, including the paths that never reached a sweep: the
    # reader refuses a record without it, so a gap here would be published as indeterminate
    # instead of as the ending this supervisor actually observed.
    if run.containment is None:
        run.containment = {"kind": "none", "established": False, "unit_ran": run.unit_ran}
    admitted = dict(admitted, containment=run.containment)
    effects, _ = classify(run.state, run.exit_code, admitted)
    payload = {
        "schema": SCHEMA_VERSION,
        "job_id": unit,
        "unit": unit,
        "state": run.state,
        "effects": effects,
        "exit_code": run.exit_code,
        "started_at": started,
        "finished_at": now(),
        "authorization_fingerprint": manifest["authorization_fingerprint"],
        "manifest_fingerprint": manifest_fingerprint(manifest),
        "logs": {
            "stdout": log_reference(job_dir / "stdout.log"),
            "stderr": log_reference(job_dir / "stderr.log"),
        },
    }
    payload.update(admitted)
    if run.detail:
        payload["detail"] = clip(run.detail)
    try:
        write_atomic(job_dir / "result.json", payload)
    except OSError:
        # The disk refused the terminal file and there is nothing truthful to retry: the lease
        # released on exit lets collection see a supervisor gone without a result.
        return EXIT_INDETERMINATE
    with contextlib.suppress(OSError):
        write_status(job_dir, unit, run.state)
    return EXIT_OK


def run_supervised(job_dir: Path, manifest: dict, lease: Lease) -> int:
    """Everything between taking the lease and writing the result, failures included."""
    started = now()
    run = UnitRun()
    record_supervisor(job_dir, manifest["unit"], lease, started)
    try:
        execute_unit(job_dir, manifest, run)
    except Exception as exc:  # noqa: BLE001 - an internal failure must still finalize the unit
        internal_failure(run, exc)
    return finalize(job_dir, manifest, run, started)


def under(child: Path, root: Path) -> bool:
    """Lexical and link-resolved containment as an answer, with no refusal of its own."""
    try:
        Path(os.path.normpath(child)).relative_to(Path(os.path.normpath(root)))
        real(child).relative_to(real(root))
    except ValueError:
        return False
    return True


def refuse_manifest(reason: str) -> None:
    raise JobError(EXIT_USAGE, "invalid_input", f"the claim for this unit is not a usable manifest: {reason}")


def validate_claim(manifest: object, unit: str) -> dict:
    """The one gate every reader of `manifest.json` passes through.

    The manifest is a file, and a caller names the directory it lives in, so nothing in
    it is trusted. This half asks only what can be answered without touching the
    filesystem, so `start`, `status`, `wait` and `result` can reuse it: a claim that is
    missing a field or carries the wrong type becomes an explicit refusal receipt here
    instead of a traceback deeper in, where a fingerprint or a receipt is being built.
    """
    if not isinstance(manifest, dict):
        refuse_manifest("it is not an object")
    if set(manifest) != set(MANIFEST_KEYS):
        refuse_manifest("its fields are not exactly the ones a claim carries")
    for key, kind in MANIFEST_KEYS.items():
        if not isinstance(manifest[key], kind) or isinstance(manifest[key], bool):
            refuse_manifest(f"`{key}` has the wrong type")
    if manifest["schema"] != SCHEMA_VERSION:
        refuse_manifest(f"schema is not {SCHEMA_VERSION}")
    if manifest["unit"] != unit:
        refuse_manifest("it was written for another unit")
    fingerprint = manifest["authorization_fingerprint"]
    if len(fingerprint) != 16 or any(char not in "0123456789abcdef" for char in fingerprint):
        refuse_manifest("the authorization fingerprint is not a 16 character digest")
    argv = manifest["argv"]
    if not 0 < len(argv) <= ARGV_MAX or not all(isinstance(item, str) and item for item in argv):
        refuse_manifest(f"`argv` must be 1..{ARGV_MAX} non-empty strings")
    timeout = check_timeout(manifest["timeout"], "the claimed timeout")
    cwd = Path(manifest["cwd"])
    if not cwd.is_absolute():
        refuse_manifest("`cwd` is not an absolute path")
    check_path_bytes(cwd, "the claimed working directory")
    result_file = Path(manifest["result_file"])
    if not result_file.is_absolute():
        refuse_manifest("`result_file` is not an absolute path")
    check_path_bytes(result_file, "the claimed result file")
    if not usable_identity(manifest["lease_identity"]):
        refuse_manifest("`lease_identity` does not name a file the way this schema records it")
    # Timeout is normalized to a float so a claim read back fingerprints as it was written.
    return dict(manifest, timeout=timeout)


def check_manifest(manifest: dict, unit: str, job_dir: Path) -> dict:
    """The full boundary before a claim is obeyed: shape, then the paths it names.

    Every refusal happens before the spawn, before any log and before the result file is
    read.
    """
    claim = validate_claim(manifest, unit)
    cwd = check_cwd(claim["cwd"])
    result_file = Path(claim["result_file"])
    # `start` only ever writes a result file under the working directory or under the job
    # directory. Anything else would let a planted manifest name a file outside both trees.
    if not (under(result_file, cwd) or under(result_file, job_dir)):
        refuse_manifest("`result_file` is outside the working directory and the job directory")
    return claim


def supervise(state_dir_raw: str, unit_raw: str) -> int:
    """Run the authorized command line, keep raw output on disk and write one final result.

    This subcommand is reachable from the command line, so it repeats the whole boundary
    `start` applied instead of trusting a directory handed to it: state directory outside
    the package, unit identifier, job directory contained and shaped, and a manifest fully
    validated. A refusal here raises `JobError`, so the caller gets a receipt and no argv.
    """
    unit = check_unit(unit_raw)
    state_dir = check_state_dir(state_dir_raw)
    job_dir = job_directory(state_dir, unit)
    if not job_dir.is_dir():
        raise JobError(EXIT_USAGE, "invalid_input", "unknown unit in this state directory")
    raw = read_json(job_dir / "manifest.json")
    if raw is None:
        raise JobError(EXIT_USAGE, "invalid_input", "this unit has no readable claim to supervise")
    manifest = check_manifest(raw, unit, job_dir)
    # The claim is shaped, but shape says nothing about who wrote it. The binding published at
    # `start` does, and it is what the lease below is claimed against: a supervisor that ran on
    # the identity named by a rewritten claim would hold a lock no reader ever looks at.
    bound, expected = binding_check(job_dir)
    if bound != "bound":
        raise JobError(
            EXIT_CONFLICT,
            "conflict",
            BINDING_REFUSED[bound],
            effects="none",
        )
    # A finished unit is never reopened. The check is the existence of the terminal file,
    # not its content, so a corrupt or truncated result still refuses a second run: only
    # one execution may ever answer for one unit, and nothing on disk is touched here.
    if os.path.lexists(job_dir / "result.json"):
        raise JobError(
            EXIT_CONFLICT,
            "conflict",
            "this unit already has a terminal result; a finished unit is never reopened",
            effects="none",
        )
    lease = claim_lease(job_dir / LEASE_NAME, expected)
    if lease.status == "replaced":
        # The lease of this job directory was taken over by another file before this supervisor
        # reached it. Running anyway would produce a record no reader could ever prove final.
        raise JobError(
            EXIT_CONFLICT,
            "conflict",
            "the lease path of this unit no longer names the file its claim recorded; "
            "this job directory was tampered with and is not run again",
            effects="none",
        )
    if lease.status == "busy":
        # A live supervisor already answers for this job directory; two would fight over one
        # result. The refusal is explicit and on stdout like every other one: this path is
        # reachable from the command line, and a bare exit code would be a silent stop.
        raise JobError(
            EXIT_CONFLICT,
            "conflict",
            "another supervisor already holds the lease of this unit; only one may answer for it",
            effects="none",
        )
    try:
        return run_supervised(job_dir, manifest, lease)
    finally:
        # Released only after the terminal file exists, so no reader sees gone-without-result early.
        lease.release()


# --- commands ----------------------------------------------------------------


def load_claim(job_dir: Path, unit: str) -> dict:
    """Read the claim and validate it before any caller uses a field of it.

    A claim being written by another process is briefly absent, and that is what the wait is
    for. A claim that is on disk but unreadable is a different answer: it is refused as
    invalid input right away, never waited on, repaired, reused or executed.

    Between the two there is one narrow case with a window of its own: the name is there and
    the open of it was denied, which is what a publication still holding that name answers.
    That one is retried, for `CLAIM_PUBLISH_SECONDS` counted from the first time it appeared
    and never longer — a budget this call opens once, so a denial that keeps coming back is
    refused with its own detail instead of being retried for as long as it lasts. Nothing is
    repaired or written here either: the retry only re-reads.
    """
    deadline = time.monotonic() + CLAIM_WAIT_SECONDS
    publication_deadline: float | None = None
    while True:
        reason, manifest = read_claim_file(job_dir / "manifest.json")
        if manifest is not None:
            return validate_claim(manifest, unit)
        if reason.startswith(CLAIM_PUBLISHING):
            if publication_deadline is None:
                publication_deadline = time.monotonic() + CLAIM_PUBLISH_SECONDS
            if time.monotonic() >= publication_deadline:
                refuse_manifest(reason[len(CLAIM_PUBLISHING) :])
            time.sleep(POLL_SECONDS)
            continue
        if reason != "absent":
            refuse_manifest(reason)
        if time.monotonic() >= deadline:
            raise JobError(
                EXIT_CONFLICT,
                "conflict",
                "an incomplete claim already holds this unit; inspect the state directory by hand",
                effects="uncertain",
            )
        time.sleep(POLL_SECONDS)


def state_on_disk(value: object) -> str:
    """A state is a label from a closed set; anything else on disk reads as `unknown`.

    This keeps an arbitrary file from choosing the text of a receipt field, and keeps the
    field bounded without clipping something the caller would have to guess at.
    """
    return value if isinstance(value, str) and value in KNOWN_STATES else "unknown"


def current_state(job_dir: Path) -> str:
    """The state on disk, reading the terminal file only when nothing is still running.

    A unit that plants a `result.json` would otherwise choose the state of a snapshot too:
    while its supervisor is provably alive the answer comes from `status.json`, which only
    this schema writes and which says `running` for exactly that situation. A lease that was
    replaced is read the same way: the terminal file there is a file whoever swapped the lease
    could equally have written, so a snapshot never forwards it as the state of this unit.
    """
    live = termination_proof(job_dir) in ("running",) + SETTLED_UNPROVABLE
    names = ("status.json",) if live else ("result.json", "status.json")
    for name in names:
        payload = read_json(job_dir / name)
        if isinstance(payload, dict):
            return state_on_disk(payload.get("state"))
    return "unknown"


def command_start(args: argparse.Namespace, argv: list[str], max_bytes: int) -> int:
    unit = check_unit(args.unit)
    if not argv:
        raise JobError(EXIT_USAGE, "invalid_input", "no command after `--`; this tool never invents one")
    if len(argv) > ARGV_MAX:
        raise JobError(EXIT_USAGE, "invalid_input", f"command line exceeds {ARGV_MAX} arguments")
    if not args.authorization or len(args.authorization) > AUTHORIZATION_MAX:
        raise JobError(EXIT_USAGE, "invalid_input", f"authorization reference must be 1..{AUTHORIZATION_MAX} characters")
    timeout = check_timeout(args.timeout, "timeout")
    state_dir = check_state_dir(args.state_dir)
    cwd = check_cwd(args.cwd)
    job_dir = job_directory(state_dir, unit)
    result_file = check_result_file(args.result_file, cwd, job_dir)
    manifest = build_manifest(unit, args.authorization, cwd, argv, timeout, result_file)
    fingerprint = manifest_fingerprint(manifest)

    # Creating and claiming touch the filesystem, so the whole family of `OSError` belongs
    # here: a component that is a file, a permission, a name the platform refuses. Nothing
    # has been written at this point, which is why these refusals can say `effects: none`.
    try:
        job_dir.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise JobError(
            EXIT_USAGE, "invalid_input", f"the state directory could not be created: {exc.strerror or exc}"
        ) from None
    try:
        job_dir.mkdir()
    except FileExistsError:
        if not job_dir.is_dir():
            raise JobError(EXIT_USAGE, "invalid_input", "job directory exists and is not a directory") from None
        existing = load_claim(job_dir, unit)
        if manifest_fingerprint(existing) != fingerprint:
            raise JobError(
                EXIT_CONFLICT,
                "conflict",
                "this unit already ran under a different manifest; a changed manifest never reuses the result",
            ) from None
        # Reuse hands the caller someone else's earlier run. A claim that no longer agrees with
        # its binding, or a job with no binding at all, is refused rather than adopted: there is
        # nothing left here that a later `wait` or `result` could prove an ending against.
        bound, _ = binding_check(job_dir)
        if bound != "bound":
            raise JobError(EXIT_CONFLICT, "conflict", REUSE_REFUSED[bound]) from None
        anchor = read_anchor(job_dir)
        extra = {"reused": True, "binding": anchor["binding"]} if anchor else {"reused": True}
        emit(receipt(job_dir, existing, current_state(job_dir), extra), max_bytes)
        return EXIT_OK
    except OSError as exc:
        raise JobError(
            EXIT_USAGE, "invalid_input", f"the job directory could not be claimed: {exc.strerror or exc}"
        ) from None

    try:
        # The lease file is created here, before the claim that records which file it is. A
        # supervisor that finds another file behind the name refuses the job, and so does
        # every reader that would otherwise have read an unheld decoy as an ending.
        manifest["lease_identity"] = create_lease(job_dir / LEASE_NAME)
        # And the binding is published before the claim, outside the directory this unit will
        # be free to write. The claim is a convenience for readers; the binding is what they
        # check it against, so a claim written after it can only ever agree or be caught.
        anchor = write_anchor(job_dir, unit, manifest)
        write_atomic(job_dir / "manifest.json", manifest)
        write_status(job_dir, unit, "starting")
    except FileExistsError:
        # A binding already stands for this unit while its job directory did not exist a moment
        # ago. Something outside this run put it there; overwriting it would be exactly the move
        # this whole record exists to prevent, so the job stops here instead.
        raise JobError(
            EXIT_CONFLICT,
            "conflict",
            "a binding for this unit already exists in this state directory; it is never overwritten",
        ) from None
    except OSError as exc:
        # The claim directory exists from here on, so the refusal names that residue instead
        # of pretending the state directory was left untouched. No unit was started.
        raise JobError(
            EXIT_INDETERMINATE,
            "start_failed",
            f"the claim could not be completed and is incomplete on disk: {exc.strerror or exc}",
        ) from None
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, this interpreter only
            # The supervisor receives the same two names this command validated and validates
            # them again on its side; it is never handed a job directory to trust.
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "supervise",
                "--state-dir",
                str(state_dir),
                "--unit",
                unit,
            ],
            cwd=str(job_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **spawn_kwargs(detached=True),
        )
    except (OSError, ValueError) as exc:
        write_status(job_dir, unit, "start_failed")
        raise JobError(EXIT_INDETERMINATE, "start_failed", f"local supervisor did not start: {exc}") from None
    # The binding token travels with the receipt because that is the one moment it is known to
    # come from `start` itself. A caller that keeps it can later demand it back on `wait` and
    # `result`, which is the only check no unit can satisfy by rewriting what is on disk.
    emit(receipt(job_dir, manifest, "starting", {"binding": anchor["binding"]}), max_bytes)
    return EXIT_OK


def command_status(args: argparse.Namespace, max_bytes: int) -> int:
    unit = check_unit(args.unit)
    job_dir = job_directory(check_state_dir(args.state_dir), unit)
    if not job_dir.is_dir():
        raise JobError(EXIT_USAGE, "invalid_input", "unknown unit in this state directory")
    manifest = load_claim(job_dir, unit)
    emit(receipt(job_dir, manifest, current_state(job_dir)), max_bytes)
    return EXIT_OK


def command_wait(args: argparse.Namespace, max_bytes: int) -> int:
    """Local wait on files; no model call happens here."""
    unit = check_unit(args.unit)
    # Validated before the loop, as start does: an unusable bound must be refused, not waited on.
    timeout = check_timeout(args.timeout, "wait timeout")
    expect = check_binding_token(args.expect_binding)
    job_dir = job_directory(check_state_dir(args.state_dir), unit)
    if not job_dir.is_dir():
        raise JobError(EXIT_USAGE, "invalid_input", "unknown unit in this state directory")
    manifest = load_claim(job_dir, unit)
    # Checked here so a wrong binding is refused now rather than after the whole timeout, and
    # checked again in `report` below, which is the boundary delivery actually crosses.
    check_expected_binding(job_dir, expect)
    deadline = time.monotonic() + timeout
    result_path = job_dir / "result.json"
    gone_since: float | None = None
    while True:
        proof = termination_proof(job_dir)
        if proof in SETTLED_UNPROVABLE:
            # A swapped lease, a claim that left its binding and a job with no binding at all
            # never become provable again, so these are answered at once instead of waited
            # out: whatever is on disk here was reachable by whoever produced that state.
            emit(
                receipt(
                    job_dir,
                    manifest,
                    "indeterminate",
                    {"effects": "uncertain", "detail": UNPROVABLE_END[proof], "termination": proof},
                ),
                max_bytes,
            )
            return EXIT_INDETERMINATE
        # The terminal file is necessary but never sufficient: a unit can write one and keep
        # running. What ends this wait is that file plus a supervisor that is no longer alive.
        if result_path.exists() and proof != "running":
            break
        if time.monotonic() >= deadline:
            extra = {"effects": "uncertain"}
            if result_path.exists():
                extra["detail"] = "a terminal result is present but the supervisor of this unit has not ended"
            emit(receipt(job_dir, manifest, "wait_timeout", extra), max_bytes)
            return EXIT_TIMEOUT
        # A supervisor whose lease nobody holds is gone. Waiting out the whole timeout for a
        # result it can no longer write reports a bound that was never the real answer.
        if proof == "proven":
            if gone_since is None:
                gone_since = time.monotonic()
            elif time.monotonic() - gone_since >= LEASE_GRACE_SECONDS and not result_path.exists():
                emit(
                    receipt(
                        job_dir,
                        manifest,
                        "indeterminate",
                        {
                            "effects": "uncertain",
                            "detail": "the supervisor of this unit ended without writing a terminal result",
                        },
                    ),
                    max_bytes,
                )
                return EXIT_INDETERMINATE
        else:
            gone_since = None
        time.sleep(POLL_SECONDS)
    return report(job_dir, unit, max_bytes, expect)


def command_result(args: argparse.Namespace, max_bytes: int) -> int:
    unit = check_unit(args.unit)
    expect = check_binding_token(args.expect_binding)
    job_dir = job_directory(check_state_dir(args.state_dir), unit)
    if not job_dir.is_dir():
        raise JobError(EXIT_USAGE, "invalid_input", "unknown unit in this state directory")
    return report(job_dir, unit, max_bytes, expect)


def incoherent(message: str) -> JobError:
    """A terminal file this schema cannot vouch for is indeterminate, never forwarded as it is."""
    return JobError(EXIT_INDETERMINATE, "indeterminate", message, effects="uncertain")


def admitted_text(value: object, field: str, limit: int = MAX_FIELD_BYTES) -> str:
    if not isinstance(value, str):
        raise incoherent(f"field `{field}` of the terminal result is not text")
    return clip(value, limit)


def admitted_count(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise incoherent(f"field `{field}` of the terminal result is not a count")
    return value


def admitted_list(value: object, field: str, limit: int = MAX_FIELD_BYTES) -> list:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise incoherent(f"field `{field}` of the terminal result is not a bounded list")
    return [admitted_text(item, field, limit) for item in value]


def admitted_logs(value: object) -> dict:
    # Exactly the pair, not a subset of it: `finalize` opens both files and references both,
    # so an empty or half map was assembled by somebody else and names no log of this run.
    if not isinstance(value, dict) or set(value) != LOG_NAMES:
        raise incoherent("the log references of the terminal result are not the expected pair")
    rebuilt = {}
    for name, reference in value.items():
        if not isinstance(reference, dict) or set(reference) != {"path", "bytes"}:
            raise incoherent("a log reference of the terminal result is outside this schema")
        rebuilt[name] = {
            "path": admitted_text(reference["path"], "logs.path", NAME_BYTES),
            "bytes": admitted_count(reference["bytes"], "logs.bytes"),
        }
    return rebuilt


def admitted_containment(value: object) -> dict:
    """Rebuild a containment record only when it is complete and typed for its own shape.

    This is the field the delivery verdict is read from, so a partial one is refused rather
    than completed by default: a record carrying only `swept` would otherwise satisfy
    `swept_proven` without ever saying whether containment was established or the unit ran.
    An established containment always reports the scope its sweep reached, and one that was
    never established reports none, because there was no tree of its own to sweep.
    """
    if not isinstance(value, dict) or set(value) - set(CONTAINMENT_KEYS):
        raise incoherent("the containment record of the terminal result is outside this schema")
    missing = [key for key in CONTAINMENT_REQUIRED if key not in value]
    if missing:
        names = ", ".join(missing)
        raise incoherent(f"the containment record of the terminal result is incomplete: {names}")
    rebuilt = {}
    for key, kind in CONTAINMENT_KEYS.items():
        if key not in value:
            continue
        if kind is bool:
            if not isinstance(value[key], bool):
                raise incoherent(f"field `containment.{key}` of the terminal result is not a flag")
            rebuilt[key] = value[key]
        else:
            rebuilt[key] = admitted_text(value[key], f"containment.{key}", MAX_FIELD_BYTES)
    if rebuilt["established"] and "swept" not in rebuilt:
        raise incoherent("the containment record of the terminal result reports no sweep of its tree")
    if not rebuilt["established"] and "swept" in rebuilt:
        raise incoherent("the containment record of the terminal result sweeps a tree it never established")
    return rebuilt


def rebuild_result(result: dict, manifest: dict) -> dict:
    """Answer with an allowlist of transport and admitted fields, rebuilt key by key.

    `result.json` is written by this supervisor, but a unit that can reach the state
    directory, a partial write or a corruption can leave extra keys in it. Copying the file
    through would carry narrative into the receipt, and a small extra field survives the
    byte ceiling untouched. Anything unexpected or incoherent makes the unit indeterminate
    here: it is refused, not retransmitted and never read as a success.
    """
    unexpected = sorted(set(result) - KNOWN_RESULT_KEYS)
    if unexpected:
        names = ", ".join(clip(name, NAME_BYTES) for name in unexpected[:MAX_NAMES])
        raise incoherent(f"the terminal result carries fields outside this schema: {names}")
    # A record this supervisor wrote carries every one of these. A shorter one was assembled
    # by somebody else, and the fields it does carry are not evidence that the unit ended.
    missing = sorted(key for key in REQUIRED_RESULT_KEYS if key not in result)
    if missing:
        names = ", ".join(clip(name, NAME_BYTES) for name in missing[:MAX_NAMES])
        raise incoherent(f"the terminal result is missing fields this supervisor always writes: {names}")
    unit = manifest["unit"]
    if result.get("schema") != SCHEMA_VERSION:
        raise incoherent("the terminal result was written under another schema")
    if result.get("job_id") != unit or result.get("unit") != unit:
        raise incoherent("the terminal result does not belong to this unit")
    if result.get("authorization_fingerprint") != manifest["authorization_fingerprint"]:
        raise incoherent("the terminal result does not carry the authorization of this claim")
    if result.get("manifest_fingerprint") != manifest_fingerprint(manifest):
        raise incoherent("the terminal result does not match the manifest that claimed this unit")
    state = result.get("state")
    if state not in TERMINAL_STATES:
        raise incoherent("the terminal result does not carry a terminal state")
    status = result.get("result_status")
    if status not in RESULT_STATUSES:
        raise incoherent("the terminal result does not carry a known admission status")
    exit_code = result.get("exit_code")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        raise incoherent("the terminal result does not carry a usable exit code")

    payload = {
        "schema": SCHEMA_VERSION,
        "job_id": unit,
        "unit": unit,
        "state": state,
        "exit_code": exit_code,
        "result_status": status,
        "authorization_fingerprint": manifest["authorization_fingerprint"],
        "manifest_fingerprint": manifest_fingerprint(manifest),
    }
    outcome = result.get("outcome")
    if outcome is not None:
        if status != "admitted" or outcome not in OUTCOMES:
            raise incoherent("the terminal result carries an outcome that was never admitted")
        payload["outcome"] = outcome
    for field in ("decision", "next_action", "observable_usage", "reason", "detail", "started_at", "finished_at"):
        if field in result:
            payload[field] = admitted_text(result[field], field)
    for field in ("blockers", "proof_refs"):
        if field in result:
            payload[field] = admitted_list(result[field], field)
    if "dropped_fields" in result:
        payload["dropped_fields"] = admitted_list(result["dropped_fields"], "dropped_fields", NAME_BYTES)
    for field in ("result_bytes", "blockers_omitted", "proof_refs_omitted", "dropped_fields_omitted"):
        if field in result:
            payload[field] = admitted_count(result[field], field)
    # Both are required above, so they are rebuilt outright: a record that reached this point
    # without a usable pair of logs or a complete containment record is not one of ours.
    payload["logs"] = admitted_logs(result["logs"])
    payload["containment"] = admitted_containment(result["containment"])
    return payload


def check_binding_token(raw: object) -> str | None:
    """Shape of an expected binding, checked before anything is compared against it."""
    if raw is None:
        return None
    token = str(raw).strip()
    if len(token) != BINDING_TOKEN_BYTES or any(char not in "0123456789abcdef" for char in token):
        raise JobError(
            EXIT_USAGE,
            "invalid_input",
            f"expected binding must be the {BINDING_TOKEN_BYTES} character token `start` returned",
        )
    return token


def check_expected_binding(job_dir: Path, expect: str | None) -> None:
    """Refuse before delivery when the binding on disk is not the one the caller was handed.

    This is the only check here that does not depend on a unit leaving files alone: the token
    came back from `start` out of band, so a binding rewritten on disk — by anyone, including
    a unit that reached the state directory — is simply a different token.
    """
    if expect is None:
        return
    anchor = read_anchor(job_dir)
    if anchor is None or anchor["binding"] != expect:
        raise JobError(
            EXIT_INDETERMINATE,
            "indeterminate",
            "the binding of this unit is not the one `start` returned, so nothing here is delivered",
            effects="uncertain",
            termination="diverged",
        )


def report(job_dir: Path, unit: str, max_bytes: int, expect: str | None = None) -> int:
    # The claim is validated before the terminal file is read: identity and locators of the
    # receipt come from it, so an unusable claim is a refusal, not a half-built receipt.
    manifest = load_claim(job_dir, unit)
    check_expected_binding(job_dir, expect)
    result = read_json(job_dir / "result.json")
    if result is None:
        raise JobError(
            EXIT_INDETERMINATE,
            current_state(job_dir),
            "no readable terminal result for this unit",
            effects="uncertain",
        )
    # Only now, with a terminal file on disk, is the ending worth proving: a record is a
    # success of this unit only if the supervisor that answers for it has provably finished.
    proof = proven_termination(job_dir)
    if proof == "running":
        raise JobError(
            EXIT_INDETERMINATE,
            "running",
            "a terminal result is on disk while the supervisor of this unit is still running; "
            "nothing written so far is final",
            effects="uncertain",
            termination=proof,
        )
    if proof != "proven":
        # No proof, no delivery. A missing lease and a platform with no exclusive lock differ
        # in cause and in nothing else that matters here: neither can show this supervisor
        # ended, and every field of the record on disk is reachable by the unit itself. The
        # answer is indeterminate with the reason named, never an exit zero taken on trust.
        raise JobError(
            EXIT_INDETERMINATE,
            "indeterminate",
            UNPROVABLE_END.get(proof, "the ending of this unit cannot be proven, so its result is not final"),
            effects="uncertain",
            termination=proof,
        )
    payload = rebuild_result(result, manifest)
    payload["locators"] = locators(job_dir, manifest)
    effects, code = classify(payload["state"], payload.get("exit_code"), payload)
    payload["effects"] = effects
    payload["transport_only"] = True
    emit(payload, max_bytes)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tl_job.py",
        description="Start one authorized unit, wait locally and return a compact receipt.",
        epilog="Exit zero means the transport worked; it never approves a story nor replaces gates and Checker.",
    )
    # Taken as text for the same reason as `start --timeout`: `type=int` makes argparse exit
    # with its own usage message before `main` reaches the receipt boundary, so a value like
    # `nope` would answer with a traceback-shaped usage dump instead of a bounded refusal.
    parser.add_argument(
        "--max-bytes",
        default=str(DEFAULT_MAX_BYTES),
        help=f"byte ceiling of the printed receipt; whole number, at least {MIN_MAX_BYTES}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="claim the unit and start the detached local supervisor")
    start.add_argument("--state-dir", required=True)
    start.add_argument("--unit", required=True)
    start.add_argument("--authorization", required=True, help="reference or fingerprint of the existing authorization")
    start.add_argument("--cwd", required=True)
    # Taken as text on purpose: argparse would exit with its own usage message before the
    # JSON boundary, so a value like `nope` would answer outside the receipt contract.
    start.add_argument(
        "--timeout",
        required=True,
        help=f"unit timeout in seconds; finite, above zero and at most {TIMEOUT_MAX}",
    )
    start.add_argument("--result-file", default=None, help="conductor's final JSON, relative to --cwd")

    for name, help_text in (
        ("status", "print the current snapshot without reading logs"),
        ("result", "print the terminal result under the allowlist"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--state-dir", required=True)
        sub.add_argument("--unit", required=True)

    wait = subparsers.add_parser("wait", help="wait locally for the terminal result")
    wait.add_argument("--state-dir", required=True)
    wait.add_argument("--unit", required=True)
    wait.add_argument(
        "--timeout",
        required=True,
        help=f"wait timeout in seconds; finite, above zero and at most {TIMEOUT_MAX}, checked before waiting",
    )

    # Only the two subcommands that deliver take it, and only they need it: `status` describes
    # what is on disk and promises nothing final about it. Optional because a caller that did
    # not keep the token from `start` still gets every check that does not depend on holding it.
    for delivering in (subparsers.choices["result"], wait):
        delivering.add_argument(
            "--expect-binding",
            default=None,
            help="the binding token `start` returned; nothing is delivered unless the job on disk still carries it",
        )

    supervise_parser = subparsers.add_parser("supervise", help="internal: run and watch one claimed unit")
    supervise_parser.add_argument("--state-dir", required=True)
    supervise_parser.add_argument("--unit", required=True)
    return parser


def split_command(raw: list[str]) -> tuple[list[str], list[str]]:
    if "--" in raw:
        index = raw.index("--")
        return raw[:index], raw[index + 1 :]
    return raw, []


def main(raw: list[str] | None = None) -> int:
    own, argv = split_command(list(sys.argv[1:] if raw is None else raw))
    args = build_parser().parse_args(own)
    unit = getattr(args, "unit", "unknown")
    # The ceiling is itself validated inside the boundary, so the refusal for a malformed
    # value is a bounded receipt. Until it is known, the default ceiling bounds that receipt.
    max_bytes = DEFAULT_MAX_BYTES
    try:
        max_bytes = check_max_bytes(args.max_bytes)
        if args.command == "supervise":
            return supervise(args.state_dir, args.unit)
        if args.command == "start":
            return command_start(args, argv, max_bytes)
        if args.command == "status":
            return command_status(args, max_bytes)
        if args.command == "wait":
            return command_wait(args, max_bytes)
        return command_result(args, max_bytes)
    except JobError as error:
        emit(error_payload(unit, error), max_bytes)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
