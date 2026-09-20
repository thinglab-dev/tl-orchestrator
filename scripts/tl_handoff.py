#!/usr/bin/env python3
"""Private, deterministic handoff state for a ChatGPT + RDC control plane.

This command never invokes a model.  It only checks the local ``codex`` executable and
keeps a small, private state machine below ``_tl-orc/runtime/remote-handoffs``.  The
artifact is deliberately runtime state: it is not evidence, a task record, or a source
of authority for a later session.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX is the supported control-plane host; retain a fail-closed fallback elsewhere.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on unsupported platforms
    fcntl = None  # type: ignore[assignment]


FORMAT_VERSION = 1
STATE_DIR = Path("_tl-orc/runtime/remote-handoffs")
STATES = {"created", "claimed", "active", "completed", "returned_to_local"}
TRANSITIONS = {
    "claim": {"created": "claimed"},
    "activate": {"claimed": "active"},
    "complete": {"active": "completed"},
    "return": {"created": "returned_to_local", "claimed": "returned_to_local", "active": "returned_to_local"},
}
VALID_ROLES = {"orchestrator", "planner", "maker", "checker", "rework", "classifier", "searcher", "advisor"}
VALID_FAMILIES = {"openai", "anthropic", "google"}
HANDOFF_ID_RE = re.compile(r"^rh_[0-9a-f]{32}$")


class HandoffError(RuntimeError):
    """A fail-closed handoff refusal with a stable machine-readable reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def run_git(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
    except OSError as exc:
        raise HandoffError("git_unavailable", str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise HandoffError("git_invalid", detail)
    return completed.stdout


def git_snapshot(repo_root: Path) -> dict[str, Any]:
    """Capture exactly the Git facts that must not drift before a remote claim."""
    root = Path(run_git(repo_root, "rev-parse", "--show-toplevel").strip()).resolve()
    if root != repo_root.resolve():
        raise HandoffError("repo_root_mismatch", f"expected repository root {repo_root.resolve()}, got {root}")
    branch = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    if not branch:
        raise HandoffError("detached_head", "a remote handoff requires a named Git branch")
    head = run_git(root, "rev-parse", "HEAD").strip()
    common_dir = Path(run_git(root, "rev-parse", "--git-common-dir").strip())
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    remote = run_git(root, "remote", "get-url", "origin").strip() if "origin" in run_git(root, "remote").split() else ""
    dirty_bytes = run_git(root, "status", "--porcelain=v1", "-z").encode("utf-8")
    return {
        "repo_root": str(root),
        "git_identity": {"common_dir": str(common_dir), "origin": remote},
        "branch": branch,
        "head": head,
        "dirty": bool(dirty_bytes),
        "dirty_digest": hashlib.sha256(dirty_bytes).hexdigest(),
    }


def command_v(executable: str) -> str | None:
    """Resolve an executable through the shell's `command -v`, without evaluating its name."""
    try:
        completed = subprocess.run(
            ["sh", "-c", 'command -v "$1"', "sh", executable], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as exc:
        raise HandoffError("preflight_unavailable", f"cannot execute command -v: {exc.__class__.__name__}") from exc
    if completed.returncode != 0:
        return None
    resolved = completed.stdout.strip().splitlines()
    return resolved[0] if resolved else None


def preflight_codex(codex_bin: str = "codex", timeout: float = 5.0) -> dict[str, str]:
    """Check the local executable only; no network or model request is made."""
    try:
        executable = command_v(codex_bin)
    except HandoffError as exc:
        return {"status": "unknown", "reason": exc.detail}
    if not executable:
        return {"status": "missing", "reason": "codex executable is absent from PATH"}
    try:
        completed = subprocess.run(
            [executable, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unknown", "reason": f"cannot inspect codex executable: {exc.__class__.__name__}"}
    version = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 or not version:
        return {"status": "invalid", "reason": "codex --version did not return a version"}
    return {"status": "ready", "reason": "codex executable and version are available"}


def remote_availability(remote_enabled: bool, codex_bin: str = "codex") -> dict[str, Any]:
    preflight = preflight_codex(codex_bin)
    remote_ready = remote_enabled and preflight["status"] == "ready"
    return {
        "local_available": True,
        "remote_available": remote_ready,
        "preflight": preflight,
        "reason": "remote handoff is ready" if remote_ready else (
            "remote handoff is disabled by project configuration" if not remote_enabled else preflight["reason"]
        ),
    }


def state_dir(repo_root: Path, override: str | None = None) -> Path:
    path = Path(override).expanduser() if override else repo_root / STATE_DIR
    return path.resolve()


def exclude_private_state(repo_root: Path, directory: Path) -> None:
    """Keep runtime state out of the working-tree snapshot without touching `.gitignore`."""
    try:
        relative = directory.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return
    exclude_value = "/" + relative.as_posix().rstrip("/") + "/"
    raw = run_git(repo_root, "rev-parse", "--git-path", "info/exclude").strip()
    exclude = Path(raw)
    if not exclude.is_absolute():
        exclude = repo_root / exclude
    try:
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if exclude_value not in existing.splitlines():
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(exclude_value + "\n")
    except OSError as exc:
        raise HandoffError("private_state_unavailable", f"cannot exclude private handoff state: {exc.__class__.__name__}") from exc


def handoff_path(directory: Path, handoff_id: str) -> Path:
    if not HANDOFF_ID_RE.fullmatch(handoff_id):
        raise HandoffError("invalid_handoff_id", "handoff ID must be an opaque rh_<32 lowercase hex> value")
    return directory / f"{handoff_id}.json"


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(data) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


@contextlib.contextmanager
def locked_handoff(directory: Path, handoff_id: str) -> Iterator[Path]:
    if fcntl is None:
        raise HandoffError("lock_unavailable", "exclusive local file locks are unavailable")
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / f"{handoff_id}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            raise HandoffError("lock_unavailable", str(exc)) from exc
        try:
            yield handoff_path(directory, handoff_id)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def immutable_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_version": state.get("format_version"),
        "handoff_id": state.get("handoff_id"),
        "created_at": state.get("created_at"),
        "snapshot": state.get("snapshot"),
        "context": state.get("context"),
    }


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise HandoffError("handoff_tampered", "handoff is not a JSON object")
    expected_keys = {
        "format_version", "handoff_id", "created_at", "handoff_revision", "snapshot", "context",
        "state", "owner", "local_authority_released", "claimant", "return_snapshot", "events",
    }
    if set(state) != expected_keys:
        raise HandoffError("handoff_tampered", "handoff has unknown or missing fields")
    if state["format_version"] != FORMAT_VERSION or not isinstance(state["handoff_id"], str) or not HANDOFF_ID_RE.fullmatch(state["handoff_id"]):
        raise HandoffError("handoff_tampered", "handoff format or ID is invalid")
    if not isinstance(state["handoff_revision"], str) or state["handoff_revision"] != digest(immutable_payload(state)):
        raise HandoffError("handoff_tampered", "handoff immutable revision does not match")
    if state["state"] not in STATES or state["owner"] not in {"local", "remote"}:
        raise HandoffError("handoff_tampered", "handoff state or owner is invalid")
    if not isinstance(state["local_authority_released"], bool) or not isinstance(state["events"], list):
        raise HandoffError("handoff_tampered", "handoff mutable fields are invalid")
    if not isinstance(state["snapshot"], dict) or not isinstance(state["context"], dict):
        raise HandoffError("handoff_tampered", "handoff snapshot or context is invalid")
    return state


def read_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HandoffError("handoff_missing", "handoff does not exist") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff_tampered", f"handoff cannot be read: {exc.__class__.__name__}") from exc
    return validate_state(state)


def require_snapshot(repo_root: Path, expected: dict[str, Any], *, label: str) -> dict[str, Any]:
    observed = git_snapshot(repo_root)
    if observed != expected:
        raise HandoffError("snapshot_drift", f"{label} changed; create a new handoff or return explicitly")
    return observed


def coordinator_released(status_file: Path) -> bool:
    try:
        text = status_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffError("coordinator_unverifiable", f"cannot read coordinator status: {exc.__class__.__name__}") from exc
    match = re.search(r"^coordinator:\s*$([\s\S]*?)(?=^[^ \t]|\Z)", text, re.MULTILINE)
    if not match or not re.search(r"^\s+released:\s*true\s*$", match.group(1), re.MULTILINE):
        return False
    return True


def validate_context(active_work_ref: str, phase: str, roles: list[str], families: list[str], context_revision: str) -> dict[str, Any]:
    if not all(isinstance(value, str) and value and len(value) <= 512 for value in (active_work_ref, phase, context_revision)):
        raise HandoffError("invalid_context", "handoff context strings must be non-empty and compact")
    if not isinstance(roles, list) or not roles or any(item not in VALID_ROLES for item in roles) or len(set(roles)) != len(roles):
        raise HandoffError("invalid_context", "roles must be a non-empty unique list of known roles")
    if not isinstance(families, list) or not families or any(item not in VALID_FAMILIES for item in families) or len(set(families)) != len(families):
        raise HandoffError("invalid_context", "families must be a non-empty unique list of known families")
    return {
        "active_work_ref": active_work_ref,
        "phase": phase,
        "roles": roles,
        "effective_author_families": families,
        "context_revision": context_revision,
    }


def create_handoff(repo_root: Path, directory: Path, context: dict[str, Any]) -> dict[str, Any]:
    exclude_private_state(repo_root, directory)
    handoff_id = f"rh_{uuid.uuid4().hex}"
    path = handoff_path(directory, handoff_id)
    state = {
        "format_version": FORMAT_VERSION,
        "handoff_id": handoff_id,
        "created_at": utc_now(),
        "snapshot": git_snapshot(repo_root),
        "context": context,
        "state": "created",
        "owner": "local",
        "local_authority_released": False,
        "claimant": None,
        "return_snapshot": None,
        "events": [{"at": utc_now(), "event": "created", "owner": "local"}],
    }
    state["handoff_revision"] = digest(immutable_payload(state))
    if path.exists():  # UUID collision is implausible, but never overwrite private state.
        raise HandoffError("handoff_collision", "opaque handoff ID already exists")
    atomic_write(path, state)
    return state


def claim_handoff(repo_root: Path, directory: Path, handoff_id: str, claimant: str, codex_bin: str) -> dict[str, Any]:
    if not claimant or len(claimant) > 256:
        raise HandoffError("invalid_claimant", "claimant must be a compact non-empty identifier")
    preflight = preflight_codex(codex_bin)
    if preflight["status"] != "ready":
        raise HandoffError("codex_not_ready", preflight["reason"])
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] != "created":
            raise HandoffError("invalid_transition", "only a newly created handoff can be claimed")
        require_snapshot(repo_root, state["snapshot"], label="repository snapshot")
        state["state"] = "claimed"
        state["claimant"] = claimant
        state["events"].append({"at": utc_now(), "event": "claimed", "owner": "remote", "claimant": claimant})
        atomic_write(path, state)
        return state


def release_local_authority(repo_root: Path, directory: Path, handoff_id: str, status_file: Path) -> dict[str, Any]:
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] not in {"created", "claimed"}:
            raise HandoffError("invalid_transition", "local authority can only be released before activation")
        require_snapshot(repo_root, state["snapshot"], label="repository snapshot")
        if not coordinator_released(status_file):
            raise HandoffError("local_coordinator_active", "STATUS.md shows the local coordinator is not released")
        state["local_authority_released"] = True
        state["events"].append({"at": utc_now(), "event": "local_authority_released", "owner": "none"})
        atomic_write(path, state)
        return state


def activate_handoff(repo_root: Path, directory: Path, handoff_id: str) -> dict[str, Any]:
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] != "claimed":
            raise HandoffError("invalid_transition", "only a claimed handoff can become active")
        require_snapshot(repo_root, state["snapshot"], label="repository snapshot")
        if not state["local_authority_released"]:
            raise HandoffError("local_coordinator_active", "local authority has not been released")
        state["state"] = "active"
        state["owner"] = "remote"
        state["events"].append({"at": utc_now(), "event": "activated", "owner": "remote", "claimant": state["claimant"]})
        atomic_write(path, state)
        return state


def complete_handoff(directory: Path, handoff_id: str) -> dict[str, Any]:
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] != "active":
            raise HandoffError("invalid_transition", "only an active handoff can complete")
        state["state"] = "completed"
        state["owner"] = "remote"
        state["events"].append({"at": utc_now(), "event": "completed", "owner": "remote"})
        atomic_write(path, state)
        return state


def return_to_local(repo_root: Path, directory: Path, handoff_id: str) -> dict[str, Any]:
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] not in {"created", "claimed", "active"}:
            raise HandoffError("invalid_transition", "only a non-terminal handoff can return to local")
        state["return_snapshot"] = git_snapshot(repo_root)
        state["state"] = "returned_to_local"
        state["owner"] = "local"
        state["events"].append({"at": utc_now(), "event": "returned_to_local", "owner": "local"})
        atomic_write(path, state)
        return state


def resume_local(repo_root: Path, directory: Path, handoff_id: str) -> dict[str, Any]:
    with locked_handoff(directory, handoff_id) as path:
        state = read_state(path)
        if state["state"] != "returned_to_local" or state["owner"] != "local" or not isinstance(state["return_snapshot"], dict):
            raise HandoffError("invalid_transition", "only a returned handoff can resume locally")
        require_snapshot(repo_root, state["return_snapshot"], label="returned repository snapshot")
        return {
            "handoff_id": state["handoff_id"],
            "state": state["state"],
            "owner": "local",
            "next_actions": ["resume_local", "create_new_remote_handoff"],
            "context": state["context"],
        }


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "handoff_id": state["handoff_id"], "handoff_revision": state["handoff_revision"],
        "state": state["state"], "owner": state["owner"],
        "local_authority_released": state["local_authority_released"],
    }


def emit(data: dict[str, Any], code: int = 0) -> int:
    print(canonical_json(data))
    return code


def parse_list(value: str) -> list[str]:
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("must be a JSON string array") from exc
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise argparse.ArgumentTypeError("must be a JSON string array")
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--codex-bin", default="codex")
    availability = sub.add_parser("availability")
    availability.add_argument("--remote-enabled", action="store_true")
    availability.add_argument("--codex-bin", default="codex")
    create = sub.add_parser("create")
    create.add_argument("--repo", default=".")
    create.add_argument("--state-dir")
    create.add_argument("--active-work-ref", required=True)
    create.add_argument("--phase", required=True)
    create.add_argument("--roles", required=True, type=parse_list)
    create.add_argument("--families", required=True, type=parse_list)
    create.add_argument("--context-revision", required=True)
    for name in ("claim", "release-local", "activate", "complete", "return-local", "resume-local"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=".")
        command.add_argument("--state-dir")
        command.add_argument("--handoff-id", required=True)
    claim.add_argument("--claimant", required=True)
    claim.add_argument("--codex-bin", default="codex")
    release = sub.choices["release-local"]
    release.add_argument("--status-file")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            return emit(preflight_codex(args.codex_bin))
        if args.command == "availability":
            return emit(remote_availability(args.remote_enabled, args.codex_bin))
        repo = Path(args.repo).resolve()
        directory = state_dir(repo, args.state_dir)
        if args.command == "create":
            context = validate_context(args.active_work_ref, args.phase, args.roles, args.families, args.context_revision)
            return emit(public_state(create_handoff(repo, directory, context)))
        if args.command == "claim":
            return emit(public_state(claim_handoff(repo, directory, args.handoff_id, args.claimant, args.codex_bin)))
        if args.command == "release-local":
            status = Path(args.status_file).resolve() if args.status_file else repo / "_tl-orc/project/STATUS.md"
            return emit(public_state(release_local_authority(repo, directory, args.handoff_id, status)))
        if args.command == "activate":
            return emit(public_state(activate_handoff(repo, directory, args.handoff_id)))
        if args.command == "complete":
            return emit(public_state(complete_handoff(directory, args.handoff_id)))
        if args.command == "return-local":
            return emit(public_state(return_to_local(repo, directory, args.handoff_id)))
        if args.command == "resume-local":
            return emit(resume_local(repo, directory, args.handoff_id))
        raise AssertionError(f"unexpected command {args.command}")
    except HandoffError as exc:
        return emit({"error": exc.reason, "detail": exc.detail}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
