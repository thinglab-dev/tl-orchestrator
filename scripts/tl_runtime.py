#!/usr/bin/env python3
"""Optional durable runtime for one frozen batch of the Automatic Mode.

The runtime is the deterministic control plane between AUTHORIZE and CLOSE. It never
chooses work outside the frozen batch, never edits its own policy, and never keeps a model
session alive between steps. Every action is a Step: intent is journaled before the effect,
the result after it. Restarting the runtime folds the journal and continues; a crash is a
pause. Ambiguity after a crash is reconciled against Git, the remote, the harness receipt or
the CI, and when the evidence is insufficient the unit waits for the operator instead of
repeating an external effect.

State of record: `journal.jsonl` (single writer under an exclusive lease), the frozen batch
JSON (authority), Git (tree truth) and the spec files (work truth). Everything else,
including `status.json`, `report.md` and the mutable sections of the batch file, is a
projection regenerated from those sources.
"""

from __future__ import annotations

import argparse
import calendar
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tl_ci_slice
    import tl_job
except ImportError:  # executed from the repository root
    from scripts import tl_ci_slice, tl_job  # type: ignore[no-redef]

try:
    from tl_merge_guard import (
        IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG,
        AuthorityReceipt,
        LocalLedgerAuthorityStore,
        MergeAuthorityGate,
        TrustRoot,
        validate_post_review_delta,
    )
except ImportError:
    try:
        from scripts.tl_merge_guard import (
            IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG,
            AuthorityReceipt,
            LocalLedgerAuthorityStore,
            MergeAuthorityGate,
            TrustRoot,
            validate_post_review_delta,
        )
    except ImportError:
        IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG = "thinglab-merge-authority"
        AuthorityReceipt = None
        LocalLedgerAuthorityStore = None
        MergeAuthorityGate = None
        TrustRoot = None
        def validate_post_review_delta(*_a, **_kw):
            return False, "merge_guard_unavailable"

try:  # T032: AUTO_STORY is opt-in; without this module the runtime runs legacy single batches only.
    import tl_story_authority as story_authority
except ImportError:
    try:
        from scripts import tl_story_authority as story_authority  # type: ignore[no-redef]
    except ImportError:
        story_authority = None  # type: ignore[assignment]


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RUNTIME_VERSION = "0.19.0"
JOURNAL_FORMAT = 1
STATE_DIR_NAME = "_tl-orc/runtime"
RESULT_DIR_NAME = ".tl-runtime"

UNIT_STATES = (
    "ready", "running", "waiting", "retryable", "parked", "blocked", "completed", "failed",
    "awaiting_operator",
)
TERMINAL_UNIT_STATES = {"parked", "blocked", "completed", "failed", "awaiting_operator"}
FAILURE_CLASSES = (
    "transient", "harness", "environment", "semantic", "verification", "authorization",
    "budget", "scope", "state_integrity", "security", "unknown",
)
STOP_CLASSES = {"authorization", "budget", "security", "state_integrity"}
EFFECT_CLASSES = (
    "none", "model_call", "local_write", "local_commit", "local_merge", "push",
    "pull_request", "pull_request_merge", "ci_query", "ci_rerun",
)
NO_DISPATCH_STATES = {"start_failed", "invalid_input", "conflict"}  # transport proved nothing ran: not charged
PHASES = ("prepare", "implement", "contain", "gates", "review", "commit", "push", "pull_request", "ci", "merge", "complete")
ROLE_RESULT_KINDS = {"maker": "unit_result", "checker": "review_result"}
DEFAULT_LIMITS = {
    "transient_retries": 3,
    "harness_retries": 1,
    "loop_threshold": 3,
    "stagnation_rounds": 2,
    "max_parked_units": 3,
    "flaky_reruns": 1,
    "backoff_seconds": 5.0,
    "max_wall_clock_seconds": 14 * 3600,
    "max_cost_usd": None,
    "max_diff_bytes": 200_000,
    "max_pack_bytes": 60_000,
    "gate_output_bytes": 4_000,
}
# Only these names reach a worker unless the config allows more. Everything else the
# operator's shell carries (tokens, keys, cloud credentials) stays out of the worker.
ENV_BASE_ALLOWLIST = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "USERNAME",
    "USER", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SHELL", "PYTHONIOENCODING", "PYTHONUTF8",
    "GOFLAGS", "GOPATH", "GOCACHE", "GOMODCACHE", "NO_COLOR", "CI",
)
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
)
_TRANSIENT = re.compile(r"429|rate.?limit|overloaded|ECONNRESET|ETIMEDOUT|EAI_AGAIN|\b50[234]\b|temporar", re.I)
_ENVIRONMENT = re.compile(r"not recognized as an internal|command not found|No such file or directory|ENOENT|not installed|WinError [23](?!\d)|não pode encontrar o arquivo", re.I)


def resolve_executable(name: str) -> str:
    """Absolute path for argv[0] so Windows shims (claude.cmd, gh.exe) resolve without a shell."""
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return name
    return shutil.which(name) or name


class Refusal(Exception):
    """Invalid input or state the runtime refuses to act on; carries the CLI exit code."""

    def __init__(self, message: str, code: int = 4):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- utilities

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_of(payload: object) -> str:
    return sha256_text(canonical(payload))


def read_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal(f"invalid JSON file {path.as_posix()}: {exc}") from exc
    if not isinstance(data, dict):
        raise Refusal(f"expected a JSON object in {path.as_posix()}")
    return data


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tl_job.write_atomic(path, payload)


def run_argv(argv: list[str], cwd: Path, timeout: float, env: dict | None = None, cap: int = 200_000) -> dict:
    """Run one command and return a bounded, JSON-friendly record. Never raises on exit code."""
    started = time.time()
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env, check=False,
        )
        out, err, code, state = proc.stdout, proc.stderr, proc.returncode, "exited"
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code, state = None, "timeout"
    except (OSError, ValueError) as exc:
        out, err, code, state = "", str(exc), None, "start_failed"
    return {
        "argv": argv, "state": state, "exit_code": code, "seconds": round(time.time() - started, 3),
        "stdout": out[-cap:], "stderr": err[-cap:], "stdout_bytes": len(out), "stderr_bytes": len(err),
    }


def parse_frontmatter(text: str) -> dict:
    """Minimal YAML-subset frontmatter: scalars, inline lists and dash lists. No nesting."""
    if not text.startswith("---"):
        return {}
    body = text.split("\n---", 1)[0].split("\n", 1)[1] if "\n" in text else ""
    data: dict = {}
    key = None
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and key is not None and raw.strip().startswith("- "):
            data.setdefault(key, [])
            if isinstance(data[key], list):
                data[key].append(_scalar(raw.strip()[2:]))
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_scalar(v.strip()) for v in inner.split(",")] if inner else []
        else:
            data[key] = _scalar(value)
    return data


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    low = value.lower()
    if low in {"true", "yes"}:
        return True
    if low in {"false", "no"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def normalize_signature(*parts: str) -> str:
    return tl_ci_slice.signature(*parts)


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace every secret-pattern match with a marker. Returns (text, replacements)."""
    total = 0
    for pattern in SECRET_PATTERNS:
        text, n = pattern.subn("[REDACTED:" + pattern.pattern[:24] + "]", text)
        total += n
    return text, total


def scan_secrets(text: str) -> list[str]:
    hits = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern[:24])
    return hits


def path_within(path: str, scopes: list[str]) -> bool:
    normalized = Path(path).as_posix().lstrip("./")
    for scope in scopes:
        scope_n = Path(scope).as_posix().strip("/")
        if scope_n in {"", "."}:
            return True
        if normalized == scope_n or normalized.startswith(scope_n + "/"):
            return True
    return False


# --------------------------------------------------------------------------- journal

@dataclass
class UnitRecord:
    id: str
    state: str = "ready"
    reason: str = ""
    phase: str = "prepare"
    round: int = 0
    branch: str = ""
    base: str = ""
    tree: str = ""
    commit: str = ""
    base_commit: str = ""
    pr: dict = field(default_factory=dict)
    merged: bool = False
    attempts: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    ci: dict = field(default_factory=dict)
    checkpoints: list = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    decision: dict = field(default_factory=dict)
    checker_commit: str = ""
    candidate_commit: str = ""



@dataclass
class Fold:
    """Everything the loop needs, rebuilt from the journal alone."""
    events: int = 0
    started_at: str = ""
    batch_state: str = "in_progress"
    stop_reason: str = ""
    runtime_stamp: str = ""
    base_branch: str = ""
    units: dict = field(default_factory=dict)
    steps: dict = field(default_factory=dict)         # step_id -> last result event (status ok or not)
    open_intents: list = field(default_factory=list)  # intents without a result, in order
    model_calls_done: int = 0
    model_calls_open: int = 0
    usage: list = field(default_factory=list)          # observed usage records from model calls
    recoveries: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    closed: bool = False
    invalid_lines: int = 0
    meta: dict = field(default_factory=dict)           # units/budget/roles as journaled at batch_open


class Journal:
    """Append-only JSONL with one writer. Each line is fsynced before the caller continues."""

    def __init__(self, path: Path):
        self.path = path
        self._seq = 0
        self._prev = ""

    def append(self, kind: str, **payload) -> dict:
        self._seq += 1
        event = {"format_version": JOURNAL_FORMAT, "seq": self._seq, "at": now_iso(), "kind": kind, "prev": self._prev, **payload}
        line = canonical(event)
        self._prev = sha256_text(line)[:16]
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
                if not isinstance(event, dict) or event.get("format_version") != JOURNAL_FORMAT or "kind" not in event:
                    invalid += 1
                    continue
                # Hash chain: a line edited, removed or inserted after the fact breaks every later link.
                if event.get("prev") != prev:
                    invalid += 1
                prev = sha256_text(raw)[:16]
                events.append(event)
        self._prev = prev
        return events, invalid

    def fold(self) -> Fold:
        events, invalid = self.read()
        fold = Fold(invalid_lines=invalid)
        pending: dict[str, dict] = {}
        seq = 0
        for event in events:
            seq = max(seq, int(event.get("seq", 0)))
            fold.events += 1
            kind = event["kind"]
            if not fold.started_at:
                fold.started_at = event.get("at", "")
            if kind == "batch_open":
                fold.runtime_stamp = event.get("runtime_stamp", "")
                fold.base_branch = event.get("base_branch", "")
                fold.meta = {"units": event.get("units_meta") or {}, "budget": event.get("budget") or {}, "roles": event.get("roles") or {},
                             "capabilities": event.get("capabilities")}
                for unit_id in event.get("units", []):
                    fold.units.setdefault(unit_id, UnitRecord(id=unit_id))
            elif kind == "step_intent":
                pending[event["step_id"]] = event
            elif kind == "step_result":
                intent = pending.pop(event["step_id"], None)
                fold.steps[event["step_id"]] = event
                if (intent or {}).get("effect_class") == "model_call" or event.get("effect_class") == "model_call":
                    if event.get("status") != "released":
                        fold.model_calls_done += 1
                    usage = (event.get("result") or {}).get("usage")
                    if isinstance(usage, dict):
                        fold.usage.append({"step_id": event["step_id"], **usage})
            elif kind == "unit_state":
                record = fold.units.setdefault(event["unit"], UnitRecord(id=event["unit"]))
                for key, value in (event.get("data") or {}).items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                record.state = event["state"]
                record.reason = event.get("reason", "")
            elif kind == "attempt":
                record = fold.units.setdefault(event["unit"], UnitRecord(id=event["unit"]))
                record.attempts.append({k: v for k, v in event.items() if k not in {"kind", "format_version", "seq", "unit"}})
            elif kind == "recovery":
                fold.recoveries.append(event)
            elif kind == "decision":
                fold.decisions.append(event)
            elif kind == "note":
                fold.notes.append(event)
            elif kind == "batch_state":
                fold.batch_state = event["state"]
                fold.stop_reason = event.get("reason", "")
                fold.closed = event["state"] != "in_progress"
        fold.open_intents = list(pending.values())
        fold.model_calls_open = sum(1 for e in pending.values() if e.get("effect_class") == "model_call")
        self._seq = seq
        return fold


# --------------------------------------------------------------------------- git

class Git:
    def __init__(self, repo: Path, executable: str = "git"):
        self.repo = repo
        self.exe = executable
        self._git_dir: Path | None = None

    def git_path(self, name: str) -> Path:
        """Path inside the repository's git dir, correct for linked worktrees where .git is a file."""
        record = run_argv([self.exe, "rev-parse", "--git-path", name], self.repo, 60)
        if record["exit_code"] != 0:
            raise Refusal(f"not a git repository: {self.repo.as_posix()}")
        path = Path(record["stdout"].strip())
        return path if path.is_absolute() else self.repo / path

    def run(self, *args: str, check: bool = True, timeout: float = 600) -> str:
        record = run_argv([self.exe, *args], self.repo, timeout)
        if check and record["exit_code"] != 0:
            raise Refusal(f"git {' '.join(args[:2])} failed: {record['stderr'].strip()[:400] or record['state']}", 4)
        return record["stdout"].strip()

    def head(self) -> str:
        return self.run("rev-parse", "HEAD")

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD")

    def tree(self, ref: str = "HEAD") -> str:
        return self.run("rev-parse", f"{ref}^{{tree}}")

    def rev(self, ref: str) -> str | None:
        record = run_argv([self.exe, "rev-parse", "--verify", "--quiet", ref + "^{commit}"], self.repo, 60)
        return record["stdout"].strip() or None

    def dirty_paths(self) -> list[str]:
        """Every changed, staged, renamed or untracked path, exactly as named on disk (NUL-separated, never quoted)."""
        record = run_argv([self.exe, "status", "--porcelain=v1", "-z", "--untracked-files=all"], self.repo, 120)
        if record["exit_code"] != 0:
            raise Refusal(f"git status failed: {record['stderr'][:300]}")
        tokens = record["stdout"].split(chr(0))
        paths = []
        i = 0
        while i < len(tokens):
            entry = tokens[i]
            i += 1
            if len(entry) < 4:
                continue
            status, path = entry[:2], entry[3:]
            candidates = [path]
            if "R" in status or "C" in status:
                candidates.append(tokens[i])  # the rename/copy source follows as its own token
                i += 1
            for candidate in candidates:
                if candidate and not (candidate.startswith(RESULT_DIR_NAME + "/") or candidate.startswith(STATE_DIR_NAME + "/")):
                    paths.append(candidate)
        return sorted(set(paths))

    def worktree_tree(self) -> str:
        """Tree of the working directory (tracked + untracked, respecting ignores) without touching the index."""
        index = self.git_path("index")
        temp_index = index.with_name(f"tl-runtime-index-{os.getpid()}")
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(temp_index)
        try:
            if index.is_file():
                shutil.copyfile(index, temp_index)
                # git trusts an index entry whose size and second-granularity mtime match the file, unless
                # the entry is "racy" (mtime >= index mtime). A file rewritten with the same size within
                # the same second would then keep its stale hash. An index mtime of 1 s (0 disables the
                # check in git) makes every entry racy, so git compares content instead of stat.
                os.utime(temp_index, (1, 1))
            record = run_argv([self.exe, "add", "-A", "--", "."], self.repo, 300, env)
            if record["exit_code"] != 0:
                raise Refusal(f"git add for tree checkpoint failed: {record['stderr'][:300]}")
            record = run_argv([self.exe, "write-tree"], self.repo, 120, env)
            if record["exit_code"] != 0:
                raise Refusal(f"git write-tree failed: {record['stderr'][:300]}")
            return record["stdout"].strip()
        finally:
            with contextlib.suppress(OSError):
                temp_index.unlink()

    def checkpoint(self, tree: str, message: str, ref: str) -> str:
        parent = self.head()
        commit = self.run("commit-tree", tree, "-p", parent, "-m", message)
        self.run("update-ref", ref, commit)
        return commit

    def restore_tree(self, tree: str, keep_ref: str = "") -> str:
        """Make the working directory equal to `tree`. Whatever is discarded is first kept under `keep_ref`."""
        kept = ""
        current = self.worktree_tree()
        if current != tree and keep_ref:
            kept = self.run("commit-tree", current, "-p", self.head(), "-m", f"tl-runtime discarded tree before restoring {tree[:12]}")
            self.run("update-ref", keep_ref, kept)
        # Clean under the ignore rules in force now, then restore: a file ignored by a rule that
        # only exists in the current tree stays on disk instead of being deleted after the rule is gone.
        self.run("clean", "-fd", "--", ".")
        self.run("read-tree", "--reset", "-u", tree)
        return kept

    def diff_text(self, base: str, limit: int, tree: str | None = None) -> tuple[str, bool]:
        """Diff from `base` to the working tree, untracked files included (via the tree object)."""
        target = tree or self.worktree_tree()
        record = run_argv([self.exe, "diff", base, target], self.repo, 300, cap=limit + 1)
        text = record["stdout"]
        return text[:limit], record["stdout_bytes"] > limit

    def changed_files(self, base: str, tree: str | None = None) -> str:
        return self.run("diff", "--name-only", base, tree or self.worktree_tree())

    def ensure_exclude(self) -> None:
        exclude = self.git_path("info/exclude")
        exclude.parent.mkdir(parents=True, exist_ok=True)
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        lines = [f"/{RESULT_DIR_NAME}/", f"/{STATE_DIR_NAME}/"]
        missing = [l for l in lines if l not in current.splitlines()]
        if missing:
            exclude.write_text(current.rstrip("\n") + ("\n" if current else "") + "\n".join(missing) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- configuration

def load_runtime_config(path: Path) -> dict:
    config = read_json_file(path)
    if config.get("schema_version") != 1:
        raise Refusal("runtime config schema_version must be 1")
    adapters = config.get("adapters")
    roles = config.get("roles")
    if not isinstance(adapters, dict) or not adapters:
        raise Refusal("runtime config needs at least one adapter")
    if not isinstance(roles, dict) or "maker" not in roles or "checker" not in roles:
        raise Refusal("runtime config needs roles.maker and roles.checker")
    for name, adapter in adapters.items():
        argv = adapter.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise Refusal(f"adapter {name}: argv must be a non-empty list of strings")
        if "{pack_path}" not in " ".join(argv) and "{pack_text}" not in " ".join(argv):
            raise Refusal(f"adapter {name}: argv must reference {{pack_path}} or {{pack_text}}")
        caps = adapter.setdefault("capabilities", {})
        for key in ("tools_allowlist", "network_sandbox", "usage_telemetry", "native_resume"):
            caps.setdefault(key, False)
        adapter.setdefault("usage_parser", "none")
        adapter.setdefault("family", name)
    for name, role in roles.items():
        if role.get("adapter") not in adapters:
            raise Refusal(f"role {name}: unknown adapter {role.get('adapter')!r}")
        role.setdefault("timeout_seconds", 1800)
        role.setdefault("model", "unknown")
        role.setdefault("effort", "unknown")
        role["family"] = adapters[role["adapter"]]["family"]
    if roles["maker"]["family"] == roles["checker"]["family"] and not config.get("allow_same_family_review", False):
        raise Refusal("required_checker_independence_unavailable: maker and checker share a family", 2)
    unisolated = [name for name, adapter in adapters.items()
                  if not adapter["capabilities"].get("tools_allowlist") and not adapter["capabilities"].get("network_sandbox")]
    if unisolated and not config.get("accept_unisolated_worker", False):
        raise Refusal("adapter(s) " + ", ".join(unisolated) + " declare neither tools_allowlist nor network_sandbox; "
                      "set accept_unisolated_worker: true to run them knowingly", 2)
    limits = dict(DEFAULT_LIMITS)
    limits.update(config.get("limits") or {})
    config["limits"] = limits
    gates = config.setdefault("gates", {})
    gates.setdefault("always", [])
    gates.setdefault("by_flag", {})
    gates.setdefault("canonical", [])
    for group in [gates["always"], gates["canonical"], *gates["by_flag"].values()]:
        for gate in group:
            if not isinstance(gate.get("id"), str) or not isinstance(gate.get("argv"), list):
                raise Refusal("every gate needs id and argv")
            gate.setdefault("timeout_seconds", 900)
    config.setdefault("ci", {"enabled": False})
    config["ci"].setdefault("poll_seconds", 60)
    config["ci"].setdefault("timeout_seconds", 1800)
    config.setdefault("git_executable", "git")
    gh = config.setdefault("gh_executable", "gh")
    config["gh_argv"] = list(gh) if isinstance(gh, list) else [str(gh)]
    config["gh_argv"][0] = resolve_executable(config["gh_argv"][0])
    config["git_executable"] = resolve_executable(config.setdefault("git_executable", "git"))
    config.setdefault("base_branch", "")
    config.setdefault("branch_prefix", "tl/")
    config.setdefault("tasks_dir", "_tl-orc/project/tasks")
    config.setdefault("sensitive_paths", [])
    config.setdefault("env_allowlist", [])
    config.setdefault("env_set", {})
    config.setdefault("prompts_dir", "")
    config.setdefault("notify_argv", [])
    config.setdefault("price_table", {})
    config["_digest"] = digest_of({k: v for k, v in config.items() if not k.startswith("_")})
    return config


def load_batch(path: Path) -> dict:
    batch = read_json_file(path)
    for key in ("id", "status", "authorization", "frozen_scope", "budget", "execution"):
        if key not in batch:
            raise Refusal(f"batch missing {key}")
    auth = batch["authorization"]
    if not auth.get("proposal_digest") or not auth.get("authorized_at") or not auth.get("authority_source"):
        raise Refusal("authority_missing_or_ambiguous: batch authorization incomplete", 2)
    effects = auth.get("permitted_effects") or {}
    for key in ("local_write", "local_commit", "local_merge", "pull_request", "push", "tag", "release"):
        if not isinstance(effects.get(key), bool):
            raise Refusal(f"permitted_effects.{key} must be boolean")
    effects.setdefault("pull_request_merge", False)
    effects.setdefault("ci_rerun", False)
    for key in ("pull_request_merge", "ci_rerun"):
        if not isinstance(effects[key], bool):
            raise Refusal(f"permitted_effects.{key} must be boolean")
    if not effects.get("local_write"):
        raise Refusal("external_effect_not_authorized: permitted_effects.local_write is false; the runtime cannot run a Maker without it", 2)
    scope = batch["frozen_scope"]
    units = scope.get("units")
    if not isinstance(units, list) or not units:
        raise Refusal("frozen_scope.units must be non-empty")
    budget = batch["budget"]
    if not isinstance(budget.get("max_model_calls"), int) or isinstance(budget.get("max_model_calls"), bool) or budget["max_model_calls"] < 1:
        raise Refusal("budget.max_model_calls must be an integer >= 1")
    if not isinstance(budget.get("max_rework_rounds_per_unit", 0), int) or budget.get("max_rework_rounds_per_unit", 0) < 0:
        raise Refusal("budget.max_rework_rounds_per_unit must be an integer >= 0")
    if int(scope.get("batch_concurrency", 1)) != 1:
        raise Refusal("this runtime executes batch_concurrency = 1 only", 2)
    expected = frozen_scope_digest(scope)
    declared = scope.get("immutable_digest")
    if not declared:
        raise Refusal(f"authority_missing_or_ambiguous: frozen_scope.immutable_digest is required (expected {expected})", 2)
    if declared != expected:
        raise Refusal(f"unexpected_revision_drift: frozen_scope digest {declared} != {expected}", 2)
    ids = [u["work_ref"] for u in units]
    if len(ids) != len(set(ids)):
        raise Refusal("duplicate work_ref in frozen_scope.units")
    for unit in units:
        for dep in unit.get("dependencies", []):
            if dep not in ids:
                raise Refusal(f"new_work_outside_frozen_batch: {unit['work_ref']} depends on {dep} outside the batch", 2)
    # T032: strictly opt-in. A batch with no story_authority_mode keeps the legacy single-batch
    # semantics (direct_proposal) unchanged, which is what every pre-T032 fixture declares.
    mode = auth.get("story_authority_mode", "direct_proposal")
    if mode not in {"direct_proposal", "AUTO_STORY"}:
        raise Refusal(f"authorization.story_authority_mode must be direct_proposal or AUTO_STORY, got {mode!r}", 2)
    if mode == "AUTO_STORY":
        if story_authority is None:
            raise Refusal("AUTO_STORY requires scripts/tl_story_authority.py, which could not be imported", 2)
        for key in ("story_authority_id", "root_authority_digest", "child_proposal_digest", "derivation_proof_digest"):
            if not auth.get(key):
                raise Refusal(f"authority_missing_or_ambiguous: AUTO_STORY batch is missing authorization.{key}", 2)
    return batch


def frozen_scope_digest(scope: dict) -> str:
    payload = {k: v for k, v in scope.items() if k != "immutable_digest"}
    return digest_of(payload)


@dataclass
class Unit:
    id: str
    spec_path: Path
    spec_revision: str
    dependencies: list
    integration_group: str
    scope_paths: list
    do_not_touch: list
    flags: list
    kind: str
    acceptance: list
    verification: list
    title: str
    spec_digest: str
    checker_approved_commit: str = ""
    integration_candidate_commit: str = ""
    authority_mode: str = ""
    authorization_id: str = ""
    target_repository: str = ""


def load_unit(batch_unit: dict, repo: Path, tasks_dir: str) -> Unit:
    ref = batch_unit["work_ref"]
    candidates = [repo / ref]
    if tasks_dir and (repo / tasks_dir).is_dir():
        candidates += [repo / tasks_dir / f"{ref}.md", *sorted((repo / tasks_dir).glob(f"{ref}-*.md"))]
    spec_path = next((c for c in candidates if c.is_file()), None)
    if spec_path is None:
        raise Refusal(f"bad_spec_or_intent_gap: spec for {ref} not found", 2)
    text = spec_path.read_text(encoding="utf-8")
    digest = sha256_text(text)
    declared = str(batch_unit.get("spec_revision", ""))
    if declared not in {digest, digest[:16], digest[:12]}:
        raise Refusal(f"unexpected_revision_drift: spec {ref} revision {digest[:16]} != frozen {declared}", 2)
    front = parse_frontmatter(text)
    scope_paths = front.get("scope_paths") or front.get("content_paths") or []
    if isinstance(scope_paths, str):
        scope_paths = [scope_paths]
    if not scope_paths:
        raise Refusal(f"bad_spec_or_intent_gap: {ref} declares no scope_paths", 2)
    unit_id = str(front.get("id") or ref)
    return Unit(
        id=ref, spec_path=spec_path, spec_revision=declared, dependencies=list(batch_unit.get("dependencies", [])),
        integration_group=str(batch_unit.get("integration_group", "default")), scope_paths=[str(p) for p in scope_paths],
        do_not_touch=[str(p) for p in (front.get("do_not_touch") or [])], flags=[str(f) for f in (front.get("flags") or [])],
        kind=str(front.get("type") or front.get("kind") or "code"), acceptance=[str(a) for a in (front.get("acceptance") or [])],
        verification=[str(v) for v in (front.get("verification") or [])], title=str(front.get("title") or unit_id),
        spec_digest=digest,
        checker_approved_commit=str(batch_unit.get("checker_approved_commit") or ""),
        integration_candidate_commit=str(batch_unit.get("integration_candidate_commit") or ""),
        authority_mode=str(batch_unit.get("authority_mode") or ""),
        authorization_id=str(batch_unit.get("authorization_id") or ""),
        target_repository=str(batch_unit.get("target_repository") or ""),
    )


# --------------------------------------------------------------------------- policy

class Policy:
    """Deterministic boundary. Workers never see the journal, the batch or the operator's env."""

    def __init__(self, config: dict, batch: dict, cognitive_barrier: Path | None = None):
        self.config = config
        self.effects = batch["authorization"]["permitted_effects"]
        self.sensitive = [str(p) for p in config.get("sensitive_paths", [])]
        # T032 §2.8: under AUTO_STORY the worker environment mechanically shadows every cognitive
        # CLI, so a direct `agy`/`codex`/`claude`/`gemini` invocation fails before it reaches a
        # provider instead of spending budget nobody journaled.
        self.cognitive_barrier = cognitive_barrier

    def effect_allowed(self, effect: str) -> bool:
        return bool(self.effects.get(effect, False))

    def worker_env(self) -> dict:
        allowed = set(ENV_BASE_ALLOWLIST) | {str(k).upper() for k in self.config.get("env_allowlist", [])}
        env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
        env.update({str(k): str(v) for k, v in (self.config.get("env_set") or {}).items()})
        env["DO_NOT_TRACK"] = "1"
        if self.cognitive_barrier is not None and story_authority is not None:
            env = story_authority.barrier_worker_env(env, self.cognitive_barrier)
        return env

    def check_containment(self, unit: Unit, dirty: list[str], diff_text: str) -> tuple[str, str]:
        """Return (failure_class, detail); ('', '') when contained."""
        sensitive = [p for p in dirty if self.sensitive and path_within(p, self.sensitive)]
        if sensitive:
            return "security", "sensitive_path_touched: " + ", ".join(sensitive[:12])
        secrets = scan_secrets(diff_text)
        if secrets:
            return "security", "secret_pattern_in_diff: " + ", ".join(secrets)
        outside = [p for p in dirty if not path_within(p, unit.scope_paths)]
        forbidden = [p for p in dirty if unit.do_not_touch and path_within(p, unit.do_not_touch)]
        if outside or forbidden:
            return "scope", "scope_expansion: " + ", ".join(sorted(set(outside + forbidden))[:12])
        return "", ""

    def capabilities_report(self) -> list[dict]:
        return [{"adapter": name, **adapter.get("capabilities", {})} for name, adapter in self.config["adapters"].items()]


# --------------------------------------------------------------------------- context compiler

class ContextCompiler:
    """Builds one bounded, stably ordered pack per dispatch and records its manifest."""

    def __init__(self, config: dict, repo: Path, git: Git):
        self.config = config
        self.repo = repo
        self.git = git
        self.max_bytes = int(config["limits"]["max_pack_bytes"])

    def _prompt(self, role: str) -> tuple[str, str]:
        names = {"maker": "maker.md", "checker": "checker-report-only.md"}
        candidates = []
        if self.config.get("prompts_dir"):
            candidates.append(Path(self.config["prompts_dir"]) / names.get(role, f"{role}.md"))
        candidates.append(tl_job.PACKAGE_ROOT / "prompts" / names.get(role, f"{role}.md"))
        for path in candidates:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                return text, sha256_text(text)[:16]
        return "", ""

    def _related_tests(self, unit: Unit) -> list[str]:
        found: list[str] = []
        for scope in unit.scope_paths:
            base = self.repo / scope
            root = base if base.is_dir() else base.parent
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                name = path.name.lower()
                if path.is_file() and ("test" in name or "spec" in name) and len(found) < 30:
                    found.append(path.relative_to(self.repo).as_posix())
        return sorted(set(found))

    def build(self, role: str, unit: Unit, phase: str, *, result_path: str, findings: list | None = None,
              ci_slice: dict | None = None, diff_base: str | None = None, checkpoint_note: str = "",
              gate_failures: list | None = None, gate_results: list | None = None) -> tuple[str, dict]:
        contract, contract_digest = self._prompt(role)
        spec_text = unit.spec_path.read_text(encoding="utf-8")
        sections: list[tuple[str, str]] = []
        manifest: list[dict] = []

        def add(name: str, text: str, ref: str = "", cap: int | None = None):
            if not text:
                return
            if cap and len(text) > cap:
                text = text[:cap] + f"\n[... truncated, {len(text)} chars total; full content on demand at {ref or 'artifact'}]"
            sections.append((name, text))
            manifest.append({"section": name, "ref": ref, "bytes": len(text.encode("utf-8")), "digest": sha256_text(text)[:16]})

        add("contract", contract, f"prompts:{role}:{contract_digest}", cap=12_000)
        policy_lines = [
            f"unit: {unit.id}", f"phase: {phase}", f"role: {role}",
            "scope_paths (only these may change): " + ", ".join(unit.scope_paths),
            "do_not_touch: " + (", ".join(unit.do_not_touch) or "(none beyond scope)"),
            "git: never run git, gh, commit, push, merge or branch commands; the runtime owns them",
            f"result_file: {result_path} (required, single JSON object, closed field list)",
        ]
        add("policy", "\n".join(policy_lines))
        add("spec", spec_text, unit.spec_path.relative_to(self.repo).as_posix(), cap=24_000)
        if unit.acceptance:
            add("acceptance", "\n".join(f"- {a}" for a in unit.acceptance))
        if unit.verification:
            add("verification_commands", "\n".join(f"- {v}" for v in unit.verification))
        tests = self._related_tests(unit)
        if tests:
            add("related_tests", "\n".join(tests))
        if findings:
            add("open_findings", json.dumps(findings, ensure_ascii=False, indent=1), cap=8_000)
        if gate_failures:
            add("gate_failures", json.dumps(gate_failures, ensure_ascii=False, indent=1), cap=8_000)
        if ci_slice:
            head = {k: v for k, v in ci_slice.items() if k != "excerpt"}
            add("ci_failure", json.dumps(head, ensure_ascii=False, indent=1) + "\n" + ci_slice.get("excerpt", ""), ci_slice.get("raw_ref") or "", cap=6_000)
        if checkpoint_note:
            add("checkpoint", checkpoint_note)
        if gate_results:
            rows = [f"- {g['id']}: {'pass' if g.get('passed') else 'FAIL'} (exit {g.get('exit_code')}) `{' '.join(g.get('argv', []))}`" for g in gate_results]
            add("runtime_verification", "The runtime already executed these gates on the tree under review; do not report them as pending verification:" + chr(10) + chr(10).join(rows))
        if diff_base:
            limit = int(self.config["limits"]["max_diff_bytes"])
            diff, truncated = self.git.diff_text(diff_base, limit)
            files = self.git.changed_files(diff_base)
            add("changed_files", files)
            add("diff", diff + ("\n[diff truncated; review by file with git diff on demand]" if truncated else ""), f"git:diff:{diff_base}")
        if role == "maker":
            task = (
                "Implement the unit within scope_paths, run the verification commands you can, and write result_file "
                "with {\"outcome\": one of delivered|ready_for_delivery|blocked|failed, \"decision\", \"blockers\", "
                "\"next_action\", \"observable_usage\", \"proof_refs\"}. Use ready_for_delivery when the tree is ready for "
                "the runtime's gates and review. Do not widen scope; report an intent gap as blocked."
            )
        else:
            task = (
                "Review the diff against the spec and acceptance. Write result_file with the review-result schema: "
                "{\"schema_version\": 1, \"verdict\": approved|changes_requested, \"action_items\": [{\"id\", \"target\": maker|human, "
                "\"category\": patch|intent_gap|deferred, \"summary\", \"paths\"}], \"deferred\": [], \"rejected\": []}. "
                "Report only; do not edit files."
            )
        add("task", task)
        text = "\n\n".join(f"## {name}\n{body}" for name, body in sections)
        if len(text.encode("utf-8")) > self.max_bytes:
            text = text.encode("utf-8")[: self.max_bytes].decode("utf-8", "ignore") + "\n[pack truncated at max_pack_bytes]"
        text, redactions = redact_secrets(text)
        pack_manifest = {"role": role, "unit": unit.id, "phase": phase, "sections": manifest, "bytes": len(text.encode("utf-8")), "digest": sha256_text(text), "redactions": redactions}
        return text, pack_manifest


# --------------------------------------------------------------------------- harness adapter

def parse_usage(parser: str, stdout_path: Path) -> dict:
    """Observed usage from the harness's own output. Anything not observed stays unknown."""
    unknown = {"input_tokens": None, "cache_read_tokens": None, "output_tokens": None, "cost_usd": None, "api_calls": None, "source": parser}
    if parser == "none" or not stdout_path.is_file():
        return unknown
    try:
        text = stdout_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return unknown
    if parser == "claude_json":
        for chunk in reversed(text.strip().splitlines()):
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            if isinstance(data, dict) and "usage" in data:
                usage = data.get("usage") or {}
                return {
                    "input_tokens": usage.get("input_tokens"),
                    "cache_read_tokens": usage.get("cache_read_input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "cost_usd": data.get("total_cost_usd"),
                    "api_calls": data.get("num_turns"),
                    "source": parser,
                }
        return unknown
    if parser == "codex_jsonl":
        totals = {"input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0}
        seen = False
        for chunk in text.splitlines():
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            usage = None
            if isinstance(data, dict):
                if data.get("type") == "token_count":
                    usage = (data.get("info") or {}).get("total_token_usage") or data.get("usage")
                elif "usage" in data and isinstance(data["usage"], dict):
                    usage = data["usage"]
            if isinstance(usage, dict):
                seen = True
                totals["input_tokens"] = usage.get("input_tokens", totals["input_tokens"])
                totals["cache_read_tokens"] = usage.get("cached_input_tokens", totals["cache_read_tokens"])
                totals["output_tokens"] = usage.get("output_tokens", totals["output_tokens"])
        if not seen:
            return unknown
        return {**totals, "cost_usd": None, "api_calls": None, "source": parser}
    return unknown


class Harness:
    """Universal core over tl_job: dispatch, containment, timeout, receipt, observed usage."""

    def __init__(self, config: dict, repo: Path, jobs_dir: Path, policy: Policy):
        self.config = config
        self.repo = repo
        self.jobs_dir = jobs_dir
        self.policy = policy
        self.tl_job = Path(tl_job.__file__).resolve()

    def render(self, role: str, pack_path: Path, pack_text: str, result_path: str) -> list[str]:
        role_cfg = self.config["roles"][role]
        adapter = self.config["adapters"][role_cfg["adapter"]]
        values = {
            "pack_path": pack_path.as_posix(), "pack_text": pack_text, "result_path": result_path,
            "model": str(role_cfg.get("model", "")), "effort": str(role_cfg.get("effort", "")),
            "tools": ",".join(role_cfg.get("tools", [])), "role": role,
        }
        argv = []
        for item in adapter["argv"]:
            for key, value in values.items():
                item = item.replace("{" + key + "}", value)
            argv.append(item)
        argv[0] = resolve_executable(argv[0])
        return argv

    @staticmethod
    def job_name(step_id: str, input_digest: str) -> str:
        return (re.sub(r"[^A-Za-z0-9._-]", "-", step_id)[:52] + "-" + input_digest[:8])[:64]

    def dispatch(self, role: str, step_id: str, pack_path: Path, pack_text: str, result_rel: str, authorization: str, input_digest: str = "") -> dict:
        role_cfg = self.config["roles"][role]
        adapter = self.config["adapters"][role_cfg["adapter"]]
        argv = self.render(role, pack_path, pack_text, result_rel)
        unit_name = self.job_name(step_id, input_digest)
        state_dir = self.jobs_dir / unit_name
        timeout = str(int(role_cfg.get("timeout_seconds", 1800)))
        start = run_argv(
            [sys.executable, str(self.tl_job), "start", "--state-dir", str(state_dir), "--unit", unit_name,
             "--authorization", authorization[:200], "--cwd", str(self.repo), "--timeout", timeout,
             "--result-file", result_rel, "--", *argv],
            self.repo, 120, env=self.policy.worker_env() | {"PYTHONIOENCODING": "utf-8"},
        )
        receipt = _receipt_json(start)
        if receipt.get("state") not in {"starting", "running"} and start["exit_code"] != 0:
            return {"state": receipt.get("state") or start["state"], "receipt": receipt, "stderr": start["stderr"][-1000:], "usage": parse_usage("none", state_dir)}
        binding = receipt.get("binding") or ""
        wait = run_argv(
            [sys.executable, str(self.tl_job), "wait", "--state-dir", str(state_dir), "--unit", unit_name,
             "--timeout", str(int(role_cfg.get("timeout_seconds", 1800)) + 60), *(["--expect-binding", binding] if binding else [])],
            self.repo, int(role_cfg.get("timeout_seconds", 1800)) + 120,
        )
        final = _receipt_json(wait)
        logs = final.get("logs") or {}
        stdout_ref = logs.get("stdout") if isinstance(logs, dict) else None
        stdout_name = stdout_ref.get("path") if isinstance(stdout_ref, dict) else (stdout_ref or "stdout.log")
        stdout_path = state_dir / "jobs" / unit_name / str(stdout_name)
        usage = parse_usage(adapter.get("usage_parser", "none"), stdout_path)
        stderr_tail = ""
        with contextlib.suppress(OSError):
            stderr_tail = (state_dir / "jobs" / unit_name / "stderr.log").read_text(encoding="utf-8", errors="replace")[-2000:]
        return {"state": final.get("state", wait["state"]), "receipt": final, "usage": usage, "stderr": stderr_tail, "job_dir": state_dir.as_posix(), "model": role_cfg.get("model"), "effort": role_cfg.get("effort"), "family": role_cfg.get("family")}

    def inspect(self, step_id: str, input_digest: str = "") -> dict:
        """Used by recovery: what does the transport say about a call whose result was never journaled?"""
        unit_name = self.job_name(step_id, input_digest)
        state_dir = self.jobs_dir / unit_name
        if not state_dir.is_dir():
            return {"state": "not_started"}
        status = run_argv([sys.executable, str(self.tl_job), "status", "--state-dir", str(state_dir), "--unit", unit_name], self.repo, 60)
        return _receipt_json(status) or {"state": "unknown"}


def _receipt_json(record: dict) -> dict:
    for chunk in (record.get("stdout") or "").strip().splitlines()[::-1]:
        try:
            data = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return {}


# --------------------------------------------------------------------------- failure classification

def classify_dispatch(dispatch: dict, result: dict | None, expected_kind: str) -> tuple[str, str, str]:
    """(class, signature, detail) for one model call. Deterministic; never asks a model."""
    state = dispatch.get("state")
    receipt = dispatch.get("receipt") or {}
    stderr = dispatch.get("stderr") or str(receipt.get("detail") or "")
    if state in {"start_failed", "invalid_input", "conflict"}:
        klass = "environment" if _ENVIRONMENT.search(stderr) else "harness"
        return klass, normalize_signature("dispatch", state, stderr[:300]), f"{state}: {stderr[:200]}"
    if state in {"timeout", "wait_timeout"}:
        return "harness", normalize_signature("dispatch", "timeout"), "harness call timed out"
    if state in {"crashed", "indeterminate", "unknown", "receipt_overflow"}:
        return "harness", normalize_signature("dispatch", state), f"transport {state}"
    exit_code = receipt.get("exit_code")
    if result is None:
        detail = str(receipt.get("reason") or receipt.get("result_status") or "no result file")
        if _TRANSIENT.search(detail) or _TRANSIENT.search(stderr):
            return "transient", normalize_signature("dispatch", "transient", detail[:200]), detail[:200]
        if exit_code not in {0, None}:
            return "harness", normalize_signature("dispatch", "exit", str(exit_code), detail[:200]), f"exit {exit_code}: {detail[:200]}"
        return "harness", normalize_signature("dispatch", "no_result"), detail[:200]
    if expected_kind == "unit_result":
        outcome = result.get("outcome")
        if outcome in {"delivered", "ready_for_delivery"}:
            return "", "", ""
        blockers = " ".join(str(b) for b in (result.get("blockers") or []))
        if outcome == "blocked":
            if re.search(r"authori[sz]|permission|approval", blockers, re.I) and re.search(r"push|merge|external|network|deploy|prod", blockers, re.I):
                return "authorization", normalize_signature("blocked", "authorization", blockers[:200]), blockers[:300]
            if re.search(r"requires approval|permission denied|tool .* not allowed", blockers, re.I):
                return "harness", normalize_signature("blocked", "harness_permission", blockers[:200]), blockers[:300]
            return "semantic", normalize_signature("blocked", blockers[:300]), blockers[:300] or "blocked without blockers"
        return "semantic", normalize_signature("failed", str(result.get("decision", ""))[:200]), str(result.get("decision", ""))[:300] or "maker reported failed"
    if expected_kind == "review_result":
        if result.get("verdict") == "approved":
            return "", "", ""
        items = result.get("action_items") or []
        summary = " | ".join(str(i.get("summary", ""))[:80] for i in items[:6])
        if any(i.get("category") == "intent_gap" and i.get("target") == "human" for i in items):
            return "semantic", normalize_signature("review", "intent_gap", summary), "intent_gap for human: " + summary
        return "verification", normalize_signature("review", summary), summary or "changes_requested"
    return "unknown", normalize_signature("unknown"), "unclassified result"


def load_result(path: Path, kind: str) -> dict | None:
    data = tl_job.read_json(path)
    if data is None:
        return None
    if kind == "unit_result":
        if data.get("outcome") not in tl_job.OUTCOMES:
            return None
        return {k: data.get(k) for k in tl_job.RESULT_FIELDS}
    if kind == "review_result":
        if data.get("verdict") not in {"approved", "changes_requested"} or not isinstance(data.get("action_items"), list):
            return None
        return {"schema_version": data.get("schema_version", 1), "verdict": data["verdict"], "action_items": data["action_items"], "deferred": data.get("deferred") or [], "rejected": data.get("rejected") or []}
    return data


# --------------------------------------------------------------------------- gates and CI

def gates_for(config: dict, unit: Unit) -> list[dict]:
    gates = list(config["gates"]["always"])
    for flag in unit.flags:
        gates.extend(config["gates"]["by_flag"].get(flag, []))
    seen = set()
    ordered = []
    for gate in gates:
        if gate["id"] not in seen:
            seen.add(gate["id"])
            ordered.append(gate)
    return ordered


def run_gate(gate: dict, repo: Path, env: dict, output_cap: int, values: dict | None = None) -> dict:
    """Run one gate. argv placeholders: {repo}, {unit}, {branch}, {base_commit}, {tree}."""
    argv = []
    for item in gate["argv"]:
        item = str(item)
        for key, value in (values or {}).items():
            item = item.replace("{" + key + "}", str(value))
        argv.append(item)
    argv[0] = resolve_executable(argv[0])
    record = run_argv(argv, repo, float(gate.get("timeout_seconds", 900)), env=env, cap=output_cap)
    passed = record["state"] == "exited" and record["exit_code"] == 0
    tail = (record["stderr"] or record["stdout"])[-output_cap:]
    return {"id": gate["id"], "argv": argv, "passed": passed, "state": record["state"], "exit_code": record["exit_code"], "seconds": record["seconds"], "tail": tail, "signature": "" if passed else normalize_signature("gate", gate["id"], tail[-600:])}


class CI:
    def __init__(self, config: dict, repo: Path, artifacts: Path, target_repository: str | None = None):
        self.config = config.get("ci", {}) if isinstance(config.get("ci"), dict) else {}
        self.gh = config.get("gh_argv", ["gh"])
        self.repo = repo
        self.artifacts = artifacts
        raw_repo = target_repository if target_repository is not None else config.get("target_repository")
        self.target_repository = str(raw_repo).strip() if raw_repo is not None else ""

    def _resolve_target_repo(self) -> str:
        if not self.target_repository or not isinstance(self.target_repository, str) or not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", self.target_repository):
            raise Refusal("missing_or_invalid_target_repository", 2)
        return self.target_repository

    def checks(self, pr_number: int) -> dict:
        target_repo = self._resolve_target_repo()
        record = run_argv([*self.gh, "pr", "checks", str(pr_number), "--repo", target_repo, "--json", "name,state,link,workflow"], self.repo, 120)
        if record["exit_code"] != 0:
            # gh exits 8 when checks are pending and 1 when some failed; both still print JSON.
            pass
        try:
            rows = json.loads(record["stdout"] or "[]")
        except ValueError:
            return {"state": "unknown", "detail": record["stderr"][-300:], "rows": []}
        if not isinstance(rows, list):
            return {"state": "unknown", "detail": "unexpected gh output", "rows": []}
        states = {str(r.get("state", "")).upper() for r in rows}
        if not rows:
            state = "none"
        elif states & {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}:
            state = "failure"
        elif states - {"SUCCESS", "SKIPPED", "NEUTRAL"}:
            state = "pending"
        else:
            state = "success"
        return {"state": state, "rows": rows}

    def _runs(self, branch: str, commit: str) -> list:
        target_repo = self._resolve_target_repo()
        argv = [*self.gh, "run", "list", "--repo", target_repo, "--branch", branch, "--json", "databaseId,conclusion,status,headSha", "--limit", "10"]
        if commit:
            argv += ["--commit", commit]
        runs = run_argv(argv, self.repo, 120)
        try:
            rows = json.loads(runs["stdout"] or "[]")
        except ValueError:
            return []
        return [r for r in rows if isinstance(r, dict) and (not commit or not r.get("headSha") or r.get("headSha") == commit)]

    def failed_log(self, pr_number: int, branch: str, commit: str = "") -> tuple[str, str]:
        target_repo = self._resolve_target_repo()
        run_id = None
        try:
            for row in self._runs(branch, commit):
                if str(row.get("conclusion", "")).lower() in {"failure", "cancelled", "timed_out"}:
                    run_id = row.get("databaseId")
                    break
        except ValueError:
            pass
        if run_id is None:
            return "", ""
        log = run_argv([*self.gh, "run", "view", str(run_id), "--repo", target_repo, "--log-failed"], self.repo, 300, cap=5_000_000)
        raw = self.artifacts / f"ci-{run_id}.log"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(log["stdout"], encoding="utf-8")
        return log["stdout"], raw.as_posix()

    def rerun_failed(self, branch: str, commit: str = "") -> bool:
        target_repo = self._resolve_target_repo()
        try:
            for row in self._runs(branch, commit):
                if str(row.get("conclusion", "")).lower() == "failure":
                    return run_argv([*self.gh, "run", "rerun", str(row["databaseId"]), "--repo", target_repo, "--failed"], self.repo, 120)["exit_code"] == 0
        except (ValueError, KeyError):
            return False
        return False


# --------------------------------------------------------------------------- scheduler

def topological(units: dict[str, Unit]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    marks: set[str] = set()

    def visit(uid: str, stack: tuple = ()):
        if uid in seen:
            return
        if uid in marks:
            raise Refusal(f"dependency cycle: {' -> '.join(stack + (uid,))}", 2)
        marks.add(uid)
        for dep in sorted(units[uid].dependencies):
            visit(dep, stack + (uid,))
        marks.discard(uid)
        seen.add(uid)
        order.append(uid)

    for uid in sorted(units):
        visit(uid)
    return order


def next_ready(fold: Fold, units: dict[str, Unit], batch: dict) -> tuple[str | None, dict[str, str]]:
    """Deterministic pick: first topological unit that is ready. Also returns derived blocks."""
    order = topological(units)
    blocks: dict[str, str] = {}
    continue_after_block = bool(batch["authorization"].get("continue_independent_after_block", False))
    any_parked = any(fold.units[u].state in {"parked", "failed", "awaiting_operator"} for u in order if u in fold.units)
    for uid in order:
        record = fold.units.get(uid) or UnitRecord(id=uid)
        if record.state in TERMINAL_UNIT_STATES or record.state == "running":
            continue
        dep_states = {d: (fold.units.get(d).state if d in fold.units else "ready") for d in units[uid].dependencies}
        if any(s in {"parked", "failed", "blocked", "awaiting_operator"} for s in dep_states.values()):
            blocks[uid] = "dependency_block: " + ", ".join(f"{d}={s}" for d, s in sorted(dep_states.items()) if s != "completed")
            continue
        if any(s != "completed" for s in dep_states.values()):
            continue  # waiting for a dependency still in flight or ahead in order
        if any_parked and not continue_after_block:
            blocks[uid] = "continue_independent_after_block=false"
            continue
        return uid, blocks
    return None, blocks


# --------------------------------------------------------------------------- runtime

class StopBatch(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class Runtime:
    def __init__(self, batch_path: Path, config_path: Path, repo: Path, state_dir: Path | None = None, *, sleep=time.sleep):
        self.batch_path = batch_path
        self.config_path = config_path
        self.repo = repo.resolve()
        self.config = load_runtime_config(config_path)
        self.batch = load_batch(batch_path)
        self.batch_id = str(self.batch["id"])
        self.state_dir = (state_dir or (self.repo / STATE_DIR_NAME / self.batch_id)).resolve()
        self.journal = Journal(self.state_dir / "journal.jsonl")
        # Repository hooks (post-checkout, pre-push, ...) are consumer code that could push or rewrite
        # outside permitted_effects. Runtime-owned git commands run with an empty hooks path; workers
        # and gates do not inherit it (worker_env filters the environment). Requires git >= 2.31.
        hooks_count = int(os.environ.get("GIT_CONFIG_COUNT", "0") or 0)
        slot = next((i for i in range(hooks_count) if os.environ.get(f"GIT_CONFIG_KEY_{i}") == "core.hooksPath"), hooks_count)
        os.environ[f"GIT_CONFIG_KEY_{slot}"] = "core.hooksPath"
        os.environ[f"GIT_CONFIG_VALUE_{slot}"] = str(self.state_dir / "no-hooks")
        os.environ["GIT_CONFIG_COUNT"] = str(max(hooks_count, slot + 1))
        self.git = Git(self.repo, self.config["git_executable"])
        self.authority = None
        self.barrier_report = None
        self.authority_mode = str(self.batch["authorization"].get("story_authority_mode", "direct_proposal"))
        barrier_dir = self.state_dir / "cognitive-barrier" if self.authority_mode == "AUTO_STORY" else None
        self.policy = Policy(self.config, self.batch, cognitive_barrier=barrier_dir)
        if self.authority_mode == "AUTO_STORY":
            try:
                # Proven in the environment the worker will actually get, and refused rather than
                # degraded: a barrier that might not hold is not a barrier.
                self.barrier_report = story_authority.require_cognitive_barrier(
                    barrier_dir, env=self.policy.worker_env())
                self.authority = story_authority.StoryAuthority.open_for(
                    self.repo, self.batch["authorization"]["story_authority_id"])
            except story_authority.HardStop as stop:
                raise Refusal(f"{stop.reason}: {stop.detail}", 2) from stop
            declared = self.batch["authorization"]["root_authority_digest"]
            if self.authority.root_digest != declared:
                raise Refusal(
                    f"authority_missing_or_ambiguous: batch declares root_authority_digest {declared} but the "
                    f"envelope digests to {self.authority.root_digest}", 2)
        self.harness = Harness(self.config, self.repo, self.state_dir / "jobs", self.policy)
        self.compiler = ContextCompiler(self.config, self.repo, self.git)
        target_repo = self.config.get("target_repository") or self.batch.get("authorization", {}).get("target_repository")
        self.ci = CI(self.config, self.repo, self.state_dir / "artifacts", target_repository=target_repo)
        self.units: dict[str, Unit] = {}
        for batch_unit in self.batch["frozen_scope"]["units"]:
            self.units[batch_unit["work_ref"]] = load_unit(batch_unit, self.repo, self.config.get("tasks_dir", ""))
        topological(self.units)
        self.stamp = f"{RUNTIME_VERSION}:{self.config['_digest'][:16]}"
        self.limits = self.config["limits"]
        self.sleep = sleep
        self.fault = os.environ.get("TL_RUNTIME_FAULT", "")
        self._lease = None
        self.fold: Fold = Fold()

    # ---- lease and journal --------------------------------------------------------------

    def _bind_and_verify_auto_story_child(self) -> None:
        """Bind the executable batch to one persisted, verified child derivation (T032)."""
        # The authority journal is the source of truth. A batch-supplied digest or an arbitrary
        # proposal file beside the batch is not authority. Recover the objects that were actually
        # derived, re-hash them, and then bind the executable batch to that exact proposal.
        proposal, proof = self.authority.load_child_derivation(self.batch_id)
        auth = self.batch["authorization"]

        if auth["child_proposal_digest"] != story_authority.digest_of(proposal):
            raise Refusal("authority_missing_or_ambiguous: child proposal digest does not match the authority journal", 2)
        if auth["derivation_proof_digest"] != proof["derivation_proof_digest"]:
            raise Refusal("authority_missing_or_ambiguous: derivation proof digest does not match the authority journal", 2)

        # Independent revalidation of containment, effects, budget, predecessor/closure,
        # and checkpoint against the root authority envelope before binding.
        story_authority.assert_child_proposal_within_envelope(
            proposal=proposal, payload=self.authority.payload,
            state=self.authority.state, authority=self.authority)

        story_authority.assert_batch_matches_child_proposal(
            batch=self.batch, units=self.units.values(), proposal=proposal, payload=self.authority.payload)

        # The child proposal's forbidden paths are part of the executable containment policy,
        # not just derivation metadata. Merge them into each Unit so the Maker sees them in its
        # context pack and the post-Maker dirty-tree check rejects forbidden descendants even
        # when the unit owns a broader parent directory (for example scope `pkg/` with
        # forbidden `pkg/secrets/`).
        forbidden = {str(path) for path in proposal.get("forbidden_paths") or []}
        for unit in self.units.values():
            unit.do_not_touch = sorted(set(unit.do_not_touch) | forbidden)

        checkpoint = proposal.get("functional_parent_checkpoint")
        if checkpoint:
            story_authority.verify_functional_checkpoint(self.repo, checkpoint)

        child_state = (self.authority.state.children.get(self.batch_id) or {}).get("state")
        if child_state not in {"open", "closed", "failed"}:
            branch = self.git.current_branch() or self.config.get("base_branch", "")
            self.authority.record_child_open(
                self.batch_id, branch=branch, head_commit=self.git.head(), tree=self.git.tree())

    def acquire(self) -> None:
        if self._lease is not None:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "artifacts").mkdir(exist_ok=True)
        (self.state_dir / "packs").mkdir(exist_ok=True)
        handle = open(self.state_dir / "lease.lock", "a+", encoding="utf-8")
        if not tl_job.lock_exclusive(handle):
            handle.close()
            raise Refusal("coordinator_conflict: another runtime holds the lease for this batch", 5)
        self._lease = handle
        self.git.ensure_exclude()
        if self.authority is not None:
            # One holder of the authority lease at a time: the global budget has a single writer.
            try:
                self.authority.acquire()
                self._bind_and_verify_auto_story_child()
            except (story_authority.HardStop, Refusal) as err:
                self.release()
                if isinstance(err, Refusal):
                    raise
                raise Refusal(f"{err.reason}: {err.detail}", 2) from err
        self.fold = self.journal.fold()
        if self.fold.invalid_lines:
            raise Refusal(f"unrecoverable_harness_failure_or_ambiguous_dispatch: journal has {self.fold.invalid_lines} invalid line(s); inspect journal.jsonl", 2)
        if self.fold.events == 0:
            self.journal.append("batch_open", batch=self.batch_id, runtime_stamp=self.stamp, runtime_version=RUNTIME_VERSION,
                                proposal_digest=self.batch["authorization"]["proposal_digest"], units=sorted(self.units),
                                repo_head=self.git.head(), base_branch=self.config["base_branch"] or self.git.current_branch(),
                                capabilities=self.policy.capabilities_report(),
                                units_meta={uid: {"title": u.title} for uid, u in self.units.items()},
                                budget={k: self.batch["budget"].get(k) for k in ("max_model_calls", "max_rework_rounds_per_unit")},
                                roles={role: {k: cfg.get(k) for k in ("adapter", "model", "effort", "family")} for role, cfg in self.config["roles"].items()})
            self.fold = self.journal.fold()

    def release(self) -> None:
        if self.authority is not None:
            self.authority.release()
        if self._lease is not None:
            tl_job.unlock_exclusive(self._lease)
            self._lease.close()
            self._lease = None

    @property
    def base_branch(self) -> str:
        return self.fold.base_branch or self.config["base_branch"] or self.git.current_branch()

    def refold(self) -> Fold:
        self.fold = self.journal.fold()
        return self.fold

    def _fault_point(self, name: str) -> None:
        """Fault injection for tests: TL_RUNTIME_FAULT=<point> kills the process at that point once."""
        if self.fault and self.fault == name:
            marker = self.state_dir / f"fault-{re.sub(r'[^A-Za-z0-9]', '_', name)}.fired"
            if not marker.exists():
                marker.write_text(now_iso(), encoding="utf-8")
                os._exit(70)

    def unit_state(self, uid: str, state: str, reason: str = "", **data) -> None:
        if state not in UNIT_STATES:
            raise Refusal(f"unknown unit state {state}")
        self.journal.append("unit_state", unit=uid, state=state, reason=reason, data=data)
        record = self.fold.units.setdefault(uid, UnitRecord(id=uid))
        for key, value in data.items():
            if hasattr(record, key):
                setattr(record, key, value)
        record.state, record.reason = state, reason

    def note(self, text: str, **data) -> None:
        self.fold.notes.append(self.journal.append("note", text=text, **data))

    def artifact(self, name: str, content: str) -> str:
        digest = sha256_text(content)
        path = self.state_dir / "artifacts" / f"{digest[:16]}-{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:60]}"
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        return path.as_posix()

    # ---- step primitive -----------------------------------------------------------------

    def step(self, step_id: str, effect_class: str, unit: str, phase: str, intent: dict, fn, *, cacheable: bool = True, context: dict | None = None) -> dict:
        """Journal intent, run `fn(intent)`, journal result. A valid prior result is reused.

        `context` is journaled with the intent for reconciliation (pre-effect observations) but is
        not part of the input digest, so it never invalidates a cached result."""
        if effect_class not in EFFECT_CLASSES:
            raise Refusal(f"unknown effect class {effect_class}")
        input_digest = digest_of(intent)
        prior = self.fold.steps.get(step_id)
        if cacheable and prior and prior.get("status") == "ok" and prior.get("input_digest") == input_digest:
            return prior["result"]
        if cacheable and prior and prior.get("status") == "ok" and effect_class == "model_call":
            # A model call is identified by its step id (unit, round, attempt). The pack can differ on
            # resume (related tests, diff), but the call already happened and was paid for.
            self.note(f"{step_id}: reused the journaled model result; the recompiled pack digest differs", step_id=step_id)
            return prior["result"]
        tree_before = self.git.worktree_tree() if effect_class in {"model_call", "local_write", "local_commit", "local_merge"} else ""
        head_before = (self.git.head(), self.git.current_branch()) if effect_class == "model_call" else None
        self.journal.append("step_intent", step_id=step_id, batch=self.batch_id, unit=unit, phase=phase, type=intent.get("type", phase),
                            effect_class=effect_class, input_digest=input_digest, runtime_stamp=self.stamp, intent=intent, tree_before=tree_before,
                            intent_context=context or {})
        self._fault_point(f"after_intent:{intent.get('type', phase)}")
        result = fn(intent)
        self._fault_point(f"after_effect:{intent.get('type', phase)}")
        status = result.pop("_status", "ok")
        evidence = result.pop("_evidence", [])
        tree_after = self.git.worktree_tree() if tree_before else ""
        if head_before is not None and (self.git.head(), self.git.current_branch()) != head_before:
            result["class"], result["detail"] = "state_integrity", f"worker moved HEAD or branch during {step_id} ({head_before[1]}@{head_before[0][:12]} -> {self.git.current_branch()}@{self.git.head()[:12]})"
        self.journal.append("step_result", step_id=step_id, unit=unit, phase=phase, effect_class=effect_class, status=status,
                            input_digest=input_digest, result=result, tree_after=tree_after, evidence=evidence)
        self.fold.steps[step_id] = {"step_id": step_id, "status": status, "input_digest": input_digest, "result": result, "effect_class": effect_class}
        self._fault_point(f"after_result:{intent.get('type', phase)}")
        if effect_class == "model_call" and status != "released":
            self.fold.model_calls_done += 1
            if isinstance(result.get("usage"), dict):
                self.fold.usage.append({"step_id": step_id, **result["usage"]})
        return result

    # ---- budgets --------------------------------------------------------------------------

    def model_calls_consumed(self) -> int:
        return self.fold.model_calls_done + len([i for i in self.fold.open_intents if i.get("effect_class") == "model_call"])

    def _calls_needed(self, uid: str, round_no: int) -> int:
        """Model calls a round still has to make: a journaled ok Maker or Checker result is not charged again."""
        return sum(1 for role in ("maker", "checker")
                   if not any(k.startswith(f"{uid}:r{round_no}:{role}") and v.get("status") == "ok" for k, v in self.fold.steps.items()))

    def budgeted_dispatch(self, role: str, step_id: str, phase: str, payload_digest: str, dispatch) -> dict:
        """Every control-plane model call goes through here. Under AUTO_STORY it is also the only
        place the global Story budget is reserved and settled, so a physical provider attempt is
        charged exactly once even though it also appears in this child batch's ledger."""
        if self.authority is None:
            return dispatch()
        context = story_authority.AuthorityDispatchContext(self.authority, self.batch_id, step_id)
        try:
            context.reserve(role=role, phase=phase, payload_digest=payload_digest)
        except story_authority.HardStop as stop:
            raise StopBatch(stop.reason, stop.detail) from stop
        try:
            record = dispatch()
        except BaseException:
            # The call may already have reached the provider: never released on doubt.
            context.consume(outcome="ambiguous", receipt={"detail": "dispatch raised before a receipt was observed"})
            raise
        state = str((record or {}).get("state", ""))
        if state in NO_DISPATCH_STATES:
            context.release(proof=f"transport state {state!r}: the dispatch never started")
        elif state in {"indeterminate", "unknown", "running", ""}:
            context.consume(outcome="ambiguous", receipt={"state": state})
        else:
            context.consume(outcome="consumed", receipt={"state": state})
        record["global_attempt_id"] = context.global_attempt_id
        return record

    def check_budget(self, needed_calls: int = 0) -> None:
        budget = self.batch["budget"]
        max_calls = int(budget.get("max_model_calls", 0))
        if max_calls and self.model_calls_consumed() + needed_calls > max_calls:
            reason = "insufficient_budget_for_unit_verification" if needed_calls > 1 else "model_call_budget_exhausted"
            raise StopBatch(reason, f"{self.model_calls_consumed()} consumed + {needed_calls} needed > {max_calls}")
        if self.authority is not None:
            # The child allocation is a projection: the Story ceiling binds before the local one.
            remaining = self.authority.remaining_global_budget
            if remaining < needed_calls or remaining <= 0:
                reason = "insufficient_budget_for_unit_verification" if needed_calls > 1 else "model_call_budget_exhausted"
                raise StopBatch(reason, f"story authority {self.authority.authority_id} has {remaining} model "
                                        f"call(s) left and {needed_calls} are needed")
        max_wall = self.limits.get("max_wall_clock_seconds")
        if max_wall and self.fold.started_at:
            started = calendar.timegm(time.strptime(self.fold.started_at, "%Y-%m-%dT%H:%M:%SZ"))
            if time.time() - started > float(max_wall):
                raise StopBatch("wall_clock_exhausted", f"batch older than {max_wall}s")
        cap = self.limits.get("max_cost_usd")
        if cap is not None:
            known = [u.get("cost_usd") for u in self.fold.usage if isinstance(u.get("cost_usd"), (int, float))]
            if known and sum(known) >= float(cap):
                raise StopBatch("cost_budget_exhausted", f"observed {sum(known):.2f} USD >= cap {cap}")

    # ---- main loop ------------------------------------------------------------------------

    def run(self, max_units: int | None = None) -> str:
        """Run until the batch closes, stops or nothing is ready. Returns the batch state."""
        self.acquire()
        try:
            if self.fold.closed:
                return self.fold.batch_state
            self.reconcile()
            done = 0
            while True:
                self.refold()
                try:
                    self.check_budget()
                    uid, blocks = next_ready(self.fold, self.units, self.batch)
                    for blocked, why in blocks.items():
                        record = self.fold.units.get(blocked)
                        if record is None or record.state != "blocked" or record.reason != why:
                            self.unit_state(blocked, "blocked", why)
                    if uid is None:
                        return self.close()
                    if max_units is not None and done >= max_units:
                        self.project()
                        return "in_progress"
                    self.execute_unit(uid)
                    done += 1
                except StopBatch as stop:
                    return self.stop(stop.reason, stop.detail)
                finally:
                    self.project()
        finally:
            self.release()

    def stop(self, reason: str, detail: str = "") -> str:
        current = self.fold.units
        for uid, record in current.items():
            if record.state == "running":
                self.unit_state(uid, "retryable", f"batch stopped: {reason}", phase=record.phase)
        self.journal.append("batch_state", state="stopped", reason=reason, detail=detail[:500])
        self.refold()
        self._close_child_batch("stopped")
        self.project()
        self.notify({"event": "batch_stopped", "batch": self.batch_id, "reason": reason})
        return "stopped"

    def close(self) -> str:
        self.refold()
        states = {uid: self.fold.units.get(uid, UnitRecord(id=uid)).state for uid in self.units}
        if all(s == "completed" for s in states.values()):
            failures = []
            head_tree = self.git.run("rev-parse", "HEAD^{tree}")
            if self.git.worktree_tree() != head_tree:
                self.restore(head_tree, "canonical gates: leftovers discarded", "")
            for gate in self.config["gates"]["canonical"]:
                tree = self.git.worktree_tree()
                if tree != head_tree:
                    self.restore(head_tree, "canonical gate leftovers discarded", "")
                    tree = head_tree
                outcome = self.step(f"gate:canonical:{gate['id']}:{tree}", "none", "", "close", {"type": "gate", "gate": gate["id"], "tree": tree, "argv": [str(a) for a in gate["argv"]]},
                                    lambda intent, g=gate: run_gate(g, self.repo, self.policy.worker_env(), int(self.limits["gate_output_bytes"]), {"repo": self.repo.as_posix(), "tree": tree}))
                if not outcome.get("passed"):
                    failures.append(outcome["id"])
            if failures:
                self.journal.append("batch_state", state="blocked", reason="canonical_full_gate_failure", detail=", ".join(failures))
                state = "blocked"
            else:
                self.journal.append("batch_state", state="done", reason="")
                state = "done"
        elif any(s in {"ready", "running", "waiting", "retryable"} for s in states.values()):
            # Nothing eligible now but work remains (dependency waiting on an operator decision).
            self.refold()
            self.project()
            return "in_progress"
        else:
            reason = "dependency_block" if any(s == "blocked" for s in states.values()) else "units_parked"
            self.journal.append("batch_state", state="blocked", reason=reason, detail=canonical(states))
            state = "blocked"
        self.refold()
        self._close_child_batch(state)
        self.project()
        self.notify({"event": "batch_closed", "batch": self.batch_id, "state": state})
        return state

    # ---- unit lifecycle -------------------------------------------------------------------

    def execute_unit(self, uid: str) -> None:
        unit = self.units[uid]
        record = self.fold.units.setdefault(uid, UnitRecord(id=uid))
        self.check_budget(needed_calls=self._calls_needed(uid, record.round if record.round and record.phase in {"implement", "contain", "gates", "review"} else record.round + 1)
                          if record.phase not in {"commit", "push", "pull_request", "ci", "merge", "complete"} else 0)
        if record.state != "running":
            self.unit_state(uid, "running", "", phase=record.phase or "prepare", started_at=record.started_at or now_iso())
        self.notify({"event": "unit_started", "batch": self.batch_id, "unit": uid})
        try:
            self.prepare(unit)
            self.rounds(unit)
            self.deliver(unit)
            self.unit_state(uid, "completed", "", phase="complete", finished_at=now_iso())
            self.notify({"event": "unit_completed", "batch": self.batch_id, "unit": uid, "pr": self.fold.units[uid].pr})
        except UnitPark as park:
            if self.authority is not None and self.fold.units[uid].findings:
                # §2.11: this child ends `changes_requested` (rework_limit_exhausted, and equally
                # stagnation or a detected loop), so `deliver` never ran and no commit exists for
                # the tree the Checker just reviewed. Materialize it before the tree is restored:
                # the next child inherits exactly this commit, unmerged.
                self._preserve_functional_checkpoint(uid, park.reason)
            self._park_cleanup(uid)
            self.unit_state(uid, park.state, park.reason, phase=self.fold.units[uid].phase, finished_at=now_iso(), decision=park.decision)
            self.notify({"event": "unit_" + park.state, "batch": self.batch_id, "unit": uid, "reason": park.reason})
            parked = sum(1 for r in self.fold.units.values() if r.state in {"parked", "awaiting_operator"})
            if parked >= int(self.limits["max_parked_units"]):
                raise StopBatch("max_parked_units", f"{parked} units parked")
        finally:
            self._leave_branch()

    def _reviewed_tree(self, uid: str) -> str:
        """The exact tree the last journaled Checker reviewed, not whatever is on disk now."""
        reviewed = ""
        for step_id, event in self.fold.steps.items():
            if step_id.startswith(f"{uid}:r") and ":checker" in step_id and event.get("status") == "ok":
                candidate = (event.get("result") or {}).get("tree")
                if candidate:
                    reviewed = candidate
        return reviewed or self.fold.units[uid].tree or self.git.worktree_tree()

    def _preserve_functional_checkpoint(self, uid: str, reason: str) -> dict | None:
        """Commit the reviewed tree and journal the child's lineage on the Story Authority.

        The commit is kept under `refs/tl/functional-checkpoints/...`, never merged into the
        protected branch: merging a `changes_requested` child only to carry state forward is
        exactly what §2.11 forbids.
        """
        record = self.fold.units.get(uid)
        if record is None or not record.branch or self.git.current_branch() != record.branch:
            return None
        self.authority.refold()
        if self.authority.state.closure_of(self.batch_id) is not None:
            return None  # this child already recorded its lineage; a closure is written once
        tree = self._reviewed_tree(uid)
        ref = f"refs/tl/functional-checkpoints/{self.batch_id}/{uid}"
        commit = self.git.checkpoint(tree, f"functional checkpoint {self.batch_id}/{uid}: tree reviewed by the Checker ({reason[:80]})", ref)
        base = self.git.rev(self.base_branch) or record.base_commit or commit
        closure = self.authority.record_child_closed(
            child_batch_id=self.batch_id, governance_base_commit=base, checker_reviewed_commit=commit,
            checker_reviewed_tree=tree, functional_checkpoint_commit=commit, functional_checkpoint_tree=tree,
            checker_verdict="changes_requested", unresolved_action_items=list(record.findings or []))
        self.note(f"{uid}: functional checkpoint {commit[:12]} preserved at {ref}; a derived child batch starts there",
                  unit=uid, ref=ref, commit=commit, tree=tree)
        return closure

    def _close_child_batch(self, state: str) -> None:
        """Journal the child's lineage when it closes approved, if the park path did not already."""
        if self.authority is None:
            return
        self.authority.refold()
        child = self.authority.state.children.get(self.batch_id) or {}
        if child.get("closure") is not None or child.get("failure") is not None:
            return  # a terminal state is journaled once; re-running `close` never re-counts it
        completed = [uid for uid, record in self.fold.units.items() if record.state == "completed"]
        if state != "done" or not completed:
            self.authority.record_child_failed(self.batch_id, reason=self.fold.stop_reason or state,
                                               detail=canonical({u: r.state for u, r in self.fold.units.items()}))
            return
        record = self.fold.units[completed[-1]]
        commit = record.candidate_commit or record.checker_commit or record.commit
        if not _COMMIT_RE.match(str(commit)):
            return
        tree = self.git.run("rev-parse", f"{commit}^{{tree}}")
        self.authority.record_child_closed(
            child_batch_id=self.batch_id, governance_base_commit=self.git.rev(self.base_branch) or record.base_commit,
            checker_reviewed_commit=commit, checker_reviewed_tree=tree, functional_checkpoint_commit=commit,
            functional_checkpoint_tree=tree, checker_verdict="approved", unresolved_action_items=[])

    def restore(self, tree: str, why: str, uid: str = "") -> None:
        """Restore the working tree; anything that would be lost is kept at refs/tl/discarded/... and noted."""
        n = sum(1 for e in self.fold.notes if str(e.get("text", "")).startswith("discarded tree kept")) + 1
        ref = f"refs/tl/discarded/{self.batch_id}/{n}"
        kept = self.git.restore_tree(tree, keep_ref=ref)
        if kept:
            self.note(f"discarded tree kept at {ref} ({kept[:12]}): {why}", unit=uid, ref=ref, commit=kept)

    def _park_cleanup(self, uid: str) -> None:
        """Keep a parked unit's uncommitted work as a checkpoint ref, then clean the tree for the next unit."""
        if not self.git.dirty_paths():
            return
        self._checkpoint_dirty(uid, {"step_id": "park"})
        self.restore(self.git.run("rev-parse", "HEAD^{tree}"), f"{uid} parked; work is in its checkpoint", uid)

    def _leave_branch(self) -> None:
        """Return to the base branch with a clean tree so the next unit starts from a known state."""
        base = self.base_branch
        if base and self.git.current_branch() != base and not self.git.dirty_paths():
            with contextlib.suppress(Refusal):
                self.git.run("checkout", "--quiet", base)

    @property
    def functional_checkpoint(self) -> dict | None:
        """T032 §2.11: the unmerged commit the previous Checker reviewed, as the authority recorded it."""
        if self.authority is None:
            return None
        derivation = (self.authority.state.children.get(self.batch_id) or {}).get("derivation") or {}
        return derivation.get("functional_parent_checkpoint") or None

    def base_ref(self, unit: Unit) -> str:
        base = self.base_branch
        unmerged = [d for d in unit.dependencies if not self.fold.units[d].merged]
        if not unmerged:
            # A derived child continues the functional lineage: it starts exactly at the commit the
            # previous Checker reviewed, never back at the governance base, and that commit is never
            # merged into the protected branch just to carry state forward.
            checkpoint = self.functional_checkpoint
            return str(checkpoint["commit"]) if checkpoint else base
        return self.fold.units[unmerged[-1]].branch or base

    def prepare(self, unit: Unit) -> None:
        uid = unit.id
        record = self.fold.units[uid]
        branch = record.branch or f"{self.config['branch_prefix']}{self.batch_id}/{uid}"
        base = record.base or self.base_ref(unit)
        if record.phase == "prepare":
            self.unit_state(uid, "running", "", phase="prepare", branch=branch, base=base)
        dirty = self.git.dirty_paths()
        if dirty and (record.phase == "prepare" or self.git.current_branch() != branch):
            raise StopBatch("unexpected_tree_state", f"dirty tree before {uid}: {', '.join(dirty[:8])}")

        def do(intent: dict) -> dict:
            existing = self.git.rev(branch)
            if existing:
                expected = self.git.rev(base)
                if existing != expected:
                    # A stale branch with foreign commits would enter the delivery outside the reviewed diff.
                    return {"_status": "failed", "detail": f"stale_branch: {branch} already exists at {existing[:12]}, not at base {str(expected)[:12]}; delete or rename it", "branch": branch}
                self.git.run("checkout", "--quiet", branch)
            else:
                self.git.run("checkout", "--quiet", "-b", branch, base)
            extra = [d for d in unit.dependencies if not self.fold.units[d].merged and self.fold.units[d].branch and self.fold.units[d].branch != base]
            for dep_branch in extra:
                merge = run_argv([self.git.exe, "merge", "--no-edit", "--no-ff", dep_branch], self.repo, 300)
                if merge["exit_code"] != 0:
                    run_argv([self.git.exe, "merge", "--abort"], self.repo, 60)
                    return {"_status": "failed", "detail": f"dependency_block: merge of {dep_branch} conflicts", "branch": branch}
            return {"branch": branch, "base_commit": self.git.head()}

        result = self.step(f"{uid}:prepare", "none", uid, "prepare", {"type": "prepare", "branch": branch, "base": base, "deps": unit.dependencies}, do)
        if str(result.get("detail", "")).startswith("dependency_block"):
            raise UnitPark("parked", result["detail"])
        if str(result.get("detail", "")).startswith("stale_branch"):
            raise UnitPark("awaiting_operator", result["detail"][:200], decision={"options": ["retry", "skip"]})
        if self.git.current_branch() != branch:
            self.git.run("checkout", "--quiet", branch)
        checkpoint = self.functional_checkpoint
        if checkpoint and record.phase == "prepare":
            # Proven before the Maker touches anything: the commit exists, HEAD is exactly it, it
            # carries the recorded tree, and the working tree is clean. Anything else is a hard stop
            # and the previous child stays immutable as historical evidence.
            try:
                story_authority.verify_functional_checkpoint(self.repo, checkpoint)
            except story_authority.HardStop as stop:
                raise StopBatch(stop.reason if stop.reason in {"unexpected_tree_state"} else "unexpected_tree_state",
                                f"{stop.reason}: {stop.detail}") from stop
        if record.phase == "prepare":
            self.unit_state(uid, "running", "", phase="implement", branch=branch, base=base, commit=result.get("base_commit", ""), base_commit=result.get("base_commit", ""))

    def rounds(self, unit: Unit) -> None:
        uid = unit.id
        record = self.fold.units[uid]
        if record.phase in {"commit", "push", "pull_request", "ci", "merge", "complete"}:
            return
        max_rounds = int(self.batch["budget"].get("max_rework_rounds_per_unit", 2))
        feedback = dict(record.decision.get("feedback") or {}) if isinstance(record.decision, dict) else {}
        if record.phase == "implement" and record.findings and not feedback:
            feedback = {"findings": record.findings}
        resume_round = (record.round > 0 and not feedback and record.phase in {"implement", "contain", "gates", "review"}
                        and any(s.startswith(f"{uid}:r{record.round}:maker") for s in self.fold.steps))
        while True:
            round_no = record.round if resume_round else record.round + 1
            resume_round = False
            self.check_budget(needed_calls=self._calls_needed(uid, round_no))
            if round_no > max_rounds + 1:
                raise UnitPark("parked", "rework_limit_exhausted")
            record.round = round_no
            self.unit_state(uid, "running", "", phase="implement", round=round_no)
            outcome = self.implement(unit, round_no, feedback)
            if outcome == "retry":
                record.round -= 1
                continue
            if isinstance(outcome, dict):
                feedback = outcome
                continue
            contained = self.contain(unit, round_no)
            if isinstance(contained, dict):
                feedback = contained
                continue
            gate_failures = self.gates(unit, round_no)
            if gate_failures:
                move = self.failure(unit, "verification", normalize_signature("gates", *[g["signature"] for g in gate_failures]), "gate failure: " + ", ".join(g["id"] for g in gate_failures), phase="gates")
                if move == "retry":
                    record.round -= 1
                    continue
                feedback = {"gate_failures": gate_failures}
                continue
            review = self.review(unit, round_no)
            if review is None:
                return
            feedback = review

    def implement(self, unit: Unit, round_no: int, feedback: dict):
        uid = unit.id
        record = self.fold.units[uid]
        step_id = f"{uid}:r{round_no}:maker"
        prior = self.fold.steps.get(step_id)
        attempt = sum(1 for a in record.attempts if str(a.get("step_id", "")).startswith(step_id) and a.get("move") == "retry")
        attempt += sum(1 for s, e in self.fold.steps.items() if s.startswith(step_id) and e.get("status") == "ambiguous")
        if attempt:
            step_id = f"{uid}:r{round_no}:maker:a{attempt}"
        checkpoint_note = ""
        ambiguous = any(s.startswith(f"{uid}:r{round_no}:maker") and e.get("status") == "ambiguous" for s, e in self.fold.steps.items())
        if ambiguous and record.checkpoints:
            checkpoint_note = f"A previous call for this round ended without a result. The tree already contains partial work (checkpoint {record.checkpoints[-1]}). Continue from it; do not start over."
        result_rel = f"{RESULT_DIR_NAME}/{uid}/r{round_no}-maker.json"
        pack_text, manifest = self.compiler.build("maker", unit, "implement", result_path=result_rel, findings=feedback.get("findings"),
                                                  ci_slice=feedback.get("ci_slice"), gate_failures=feedback.get("gate_failures"), checkpoint_note=checkpoint_note)
        pack_path = self.state_dir / "packs" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', step_id)}.md"
        pack_path.write_text(pack_text, encoding="utf-8")
        (self.repo / RESULT_DIR_NAME / uid).mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            (self.repo / result_rel).unlink()

        def do(intent: dict) -> dict:
            self.check_budget(needed_calls=1)
            dispatch = self.budgeted_dispatch(
                "maker", step_id, "implementation", digest_of(intent),
                lambda: self.harness.dispatch("maker", step_id, pack_path, pack_text, result_rel,
                                              self.batch["authorization"]["proposal_digest"], digest_of(intent)))
            result = load_result(self.repo / result_rel, "unit_result")
            klass, signature, detail = classify_dispatch(dispatch, result, "unit_result")
            return {"_status": "released" if dispatch.get("state") in NO_DISPATCH_STATES else "ok","dispatch": {k: v for k, v in dispatch.items() if k != "receipt"} | {"receipt_state": (dispatch.get("receipt") or {}).get("state")},
                    "result": result, "usage": dispatch.get("usage"), "class": klass, "signature": signature, "detail": detail, "tree": self.git.worktree_tree(),
                    "_evidence": [self.artifact(f"{step_id}.pack.manifest.json", canonical(manifest))]}

        outcome = self.step(step_id, "model_call", uid, "implement", {"type": "maker", "round": round_no, "pack_digest": manifest["digest"], "step": step_id}, do)
        if outcome.get("class") == "state_integrity":
            raise StopBatch("unexpected_tree_state", outcome["detail"])
        if not outcome.get("class"):
            return None
        move = self.failure(unit, outcome["class"], outcome["signature"], outcome["detail"], phase="implement", step_id=step_id)
        if move == "retry":
            return "retry"
        return {"findings": [{"id": "maker", "target": "maker", "category": "patch", "summary": outcome["detail"]}]}

    def contain(self, unit: Unit, round_no: int):
        uid = unit.id
        record = self.fold.units[uid]
        dirty = self.git.dirty_paths()
        base_commit = record.base_commit or self.git.head()
        # The secret scan must see every byte that could be committed, so this diff is uncapped;
        # only the Checker's pack is bounded by max_diff_bytes.
        diff, truncated = self.git.diff_text(base_commit, 1 << 31)
        if truncated:
            raise StopBatch("unexpected_tree_state", "diff too large to scan for secrets")
        raw = []
        for path in dirty:
            file_path = self.repo / path
            if file_path.is_file():
                try:
                    raw.append(file_path.read_bytes().decode("latin-1"))
                except OSError as exc:
                    raise StopBatch("unexpected_tree_state", f"cannot read {path} for the secret scan: {exc}")
        klass, detail = self.policy.check_containment(unit, dirty, diff + "\n" + "\n".join(raw))
        intent_tree = ""
        for event in self.journal.read()[0]:
            if event.get("kind") == "step_intent" and str(event.get("step_id", "")).startswith(f"{uid}:r{round_no}:maker"):
                intent_tree = event.get("tree_before", "")
        if not klass:
            if intent_tree and self.git.worktree_tree() == intent_tree:
                move = self.failure(unit, "semantic", normalize_signature("no_change"), "maker produced no change", phase="contain")
                if move == "retry":
                    return {}
                return {"findings": [{"id": "no_change", "target": "maker", "category": "patch", "summary": "no files changed inside scope_paths"}]}
            return None
        if klass == "security":
            raise StopBatch("external_effect_not_authorized" if "sensitive" in detail else "secret_detected", detail)
        # scope: restore the tree to the round start so the widening never reaches a commit.
        if intent_tree:
            self.restore(intent_tree, f"{uid} scope violation: {detail[:80]}", uid)
        move = self.failure(unit, "scope", normalize_signature("scope", detail), detail, phase="contain")
        if move == "retry":
            return {}
        return {"findings": [{"id": "scope", "target": "maker", "category": "patch", "summary": detail + " (tree restored; stay inside scope_paths)"}]}

    def gates(self, unit: Unit, round_no: int) -> list[dict]:
        uid = unit.id
        failures = []
        expected = ""
        for step_id, step in self.fold.steps.items():
            if step_id.startswith(f"{uid}:r{round_no}:maker") and step.get("status") == "ok":
                expected = (step.get("result") or {}).get("tree") or ""
        tree = self.git.worktree_tree()
        if expected and tree != expected:
            # A crash between a gate's effect and its result leaves the gate's files behind; the
            # tree under verification is the Maker's, so it is restored before any gate runs.
            self.restore(expected, f"{uid}: tree drifted after the Maker (gate leftovers)", uid)
            self.note(f"{uid}: tree restored to the Maker's tree before gates")
            tree = self.git.worktree_tree()
        record = self.fold.units[uid]
        values = {"repo": self.repo.as_posix(), "unit": uid, "branch": record.branch, "base_commit": record.base_commit, "tree": tree}
        for gate in gates_for(self.config, unit):
            outcome = self.step(f"gate:{gate['id']}:{tree}", "none", uid, "gates", {"type": "gate", "gate": gate["id"], "tree": tree, "base_commit": record.base_commit, "argv": [str(a) for a in gate["argv"]]},
                                lambda intent, g=gate: run_gate(g, self.repo, self.policy.worker_env(), int(self.limits["gate_output_bytes"]), values))
            after = self.git.worktree_tree()
            if after != tree:
                # A verification gate that leaves files behind (caches, build output, auto-fixes) must not
                # smuggle them into the delivery: the tree under review is the Maker's, not the gate's.
                self.restore(tree, f"gate {gate['id']} artifacts", uid)
                self.note(f"{uid}: gate {gate['id']} changed the tree; discarded its artifacts (add them to .gitignore or make the gate read-only)")
            if not outcome.get("passed"):
                failures.append({"id": outcome["id"], "exit_code": outcome.get("exit_code"), "state": outcome.get("state"), "tail": outcome.get("tail", "")[-1500:], "signature": outcome.get("signature", "")})
        return failures

    def review(self, unit: Unit, round_no: int):
        uid = unit.id
        record = self.fold.units[uid]
        step_id = f"{uid}:r{round_no}:checker"
        attempt = sum(1 for a in record.attempts if str(a.get("step_id", "")).startswith(step_id) and a.get("move") == "retry")
        attempt += sum(1 for s, e in self.fold.steps.items() if s.startswith(step_id) and e.get("status") == "ambiguous")
        if attempt:
            step_id = f"{uid}:r{round_no}:checker:a{attempt}"
        result_rel = f"{RESULT_DIR_NAME}/{uid}/r{round_no}-checker.json"
        base_commit = record.base_commit or self.git.head()
        tree = self.git.worktree_tree()
        gate_results = []
        for gate in gates_for(self.config, unit):
            prior = self.fold.steps.get(f"gate:{gate['id']}:{tree}")
            if prior and prior.get("status") == "ok":
                gate_results.append({**(prior.get("result") or {}), "argv": (prior.get("result") or {}).get("argv") or [str(a) for a in gate["argv"]]})
        pack_text, manifest = self.compiler.build("checker", unit, "review", result_path=result_rel, diff_base=base_commit, gate_results=gate_results)
        pack_path = self.state_dir / "packs" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', step_id)}.md"
        pack_path.write_text(pack_text, encoding="utf-8")
        with contextlib.suppress(OSError):
            (self.repo / result_rel).unlink()

        def do(intent: dict) -> dict:
            self.check_budget(needed_calls=1)
            dispatch = self.budgeted_dispatch(
                "checker", step_id, "review", digest_of(intent),
                lambda: self.harness.dispatch("checker", step_id, pack_path, pack_text, result_rel,
                                              self.batch["authorization"]["proposal_digest"], digest_of(intent)))
            result = load_result(self.repo / result_rel, "review_result")
            klass, signature, detail = classify_dispatch(dispatch, result, "review_result")
            after = self.git.worktree_tree()
            if after != tree:
                self.restore(tree, f"{uid} checker modified the tree", uid)
                klass, detail = "state_integrity", "checker modified the tree; restored"
            return {"_status": "released" if dispatch.get("state") in NO_DISPATCH_STATES else "ok",
                    "dispatch": {k: v for k, v in dispatch.items() if k != "receipt"} | {"receipt_state": (dispatch.get("receipt") or {}).get("state")},
                    "result": result, "usage": dispatch.get("usage"), "class": klass, "signature": signature, "detail": detail, "tree": tree,
                    "_evidence": [self.artifact(f"{step_id}.pack.manifest.json", canonical(manifest))]}

        outcome = self.step(step_id, "model_call", uid, "review", {"type": "checker", "round": round_no, "tree": tree, "pack_digest": manifest["digest"]}, do)
        if not outcome.get("class"):
            self.unit_state(uid, "running", "", phase="commit", findings=[], tree=tree)
            return None
        if outcome["class"] == "state_integrity":
            raise StopBatch("unexpected_tree_state", outcome["detail"])
        items = (outcome.get("result") or {}).get("action_items") or []
        resolved, items = self._resolve_pending_verification(items, gate_results)
        for item in resolved:
            self.note(f"{uid}: Checker item {item.get('id')} resolved by runtime evidence (gate already passed): {str(item.get('summary', ''))[:120]}")
        if resolved and not items:
            self.unit_state(uid, "running", "", phase="commit", findings=[], tree=tree)
            return None
        human = [i for i in items if i.get("target") == "human" and i.get("category") != "deferred"]
        if human:
            raise UnitPark("awaiting_operator", "intent_gap: " + "; ".join(str(i.get("summary", ""))[:120] for i in human[:3]),
                           decision={"options": ["retry", "skip"], "items": human[:5]})
        findings_digest = sha256_text(chr(10).join(sorted(str(i.get("summary", "")) for i in items)))[:16]
        move = self.failure(unit, outcome["class"], outcome["signature"], outcome["detail"], phase="review", findings_digest=findings_digest, step_id=step_id)
        if move == "retry":
            record.round -= 1
            return {}
        self.unit_state(uid, "running", "", phase="implement", findings=items)
        return {"findings": [i for i in items if i.get("target") == "maker" or i.get("category") == "patch"] or items}

    @staticmethod
    def _resolve_pending_verification(items: list, gate_results: list) -> tuple[list, list]:
        """A `verificacao_pendente` the Checker could not run is satisfied when the runtime ran that gate green."""
        resolved, remaining = [], []
        for item in items:
            summary = str(item.get("summary", ""))
            matched = False
            if item.get("target") == "human" and "verificacao_pendente" in summary.lower().replace("ç", "c").replace("ã", "a"):
                for gate in gate_results:
                    if not gate.get("passed"):
                        continue
                    argv = [str(a) for a in gate.get("argv", [])]
                    tokens = {" ".join(argv), str(gate.get("id", ""))}
                    tokens |= {Path(a).name for a in argv if Path(a).suffix in {".py", ".sh", ".ps1", ".js", ".ts"}}
                    if any(token and token in summary for token in tokens):
                        matched = True
                        break
            (resolved if matched else remaining).append(item)
        return resolved, remaining

    # ---- failure handling -----------------------------------------------------------------

    def failure(self, unit: Unit, klass: str, signature: str, detail: str, *, phase: str, findings_digest: str = "", step_id: str = "") -> str:
        """Record the attempt, apply the loop detector, and return the move: retry | rework | (raises)."""
        uid = unit.id
        record = self.fold.units[uid]
        tree = self.git.worktree_tree()
        history = record.attempts
        same_signature = sum(1 for a in history if a.get("signature") == signature and signature)
        trees = [a.get("tree") for a in history[-2:]] + [tree]
        oscillation = len(trees) == 3 and trees[0] == trees[2] and trees[0] != trees[1]
        stagnation = bool(findings_digest) and sum(1 for a in history[-(int(self.limits["stagnation_rounds"]) - 1):] if a.get("findings_digest") == findings_digest) >= int(self.limits["stagnation_rounds"]) - 1
        move = ""
        if klass in STOP_CLASSES:
            move = "stop"
        elif same_signature + 1 >= int(self.limits["loop_threshold"]):
            move = "park:loop_detected"
        elif oscillation:
            move = "park:diff_oscillation"
        elif stagnation:
            move = "park:stagnation"
        elif klass == "transient":
            retries = sum(1 for a in history if a.get("class") == "transient" and a.get("phase") == phase)
            move = "retry" if retries < int(self.limits["transient_retries"]) else "park:transient_retries_exhausted"
        elif klass == "harness":
            retries = sum(1 for a in history if a.get("class") == "harness" and a.get("phase") == phase)
            move = "retry" if retries < int(self.limits["harness_retries"]) else "park:harness_failure"
        elif klass == "environment":
            move = "park:environment"
        elif klass == "scope":
            prior = sum(1 for a in history if a.get("class") == "scope")
            move = "rework" if prior < 1 else "park:scope_expansion"
        elif klass in {"semantic", "verification"}:
            max_rounds = int(self.batch["budget"].get("max_rework_rounds_per_unit", 2))
            move = "rework" if record.round <= max_rounds else "park:rework_limit_exhausted"
        else:
            move = "park:unknown_failure"
        self.journal.append("attempt", unit=uid, phase=phase, round=record.round, **{"class": klass}, signature=signature, detail=detail[:400],
                            tree=tree, findings_digest=findings_digest, move=move, step_id=step_id,
                            model=self.config["roles"].get("maker" if phase != "review" else "checker", {}).get("model"))
        record.attempts.append({"phase": phase, "round": record.round, "class": klass, "signature": signature, "tree": tree, "findings_digest": findings_digest, "move": move, "step_id": step_id})
        if move == "stop":
            raise StopBatch({"authorization": "external_effect_not_authorized", "budget": "model_call_budget_exhausted", "security": "secret_detected", "state_integrity": "unexpected_tree_state"}[klass], detail)
        if move.startswith("park:"):
            raise UnitPark("parked", move.split(":", 1)[1] + ": " + detail[:200])
        if move == "retry":
            backoff = float(self.limits["backoff_seconds"]) * (2 ** max(0, same_signature))
            if backoff:
                self.sleep(min(backoff, 300))
        return move

    # ---- delivery -------------------------------------------------------------------------

    def deliver(self, unit: Unit) -> None:
        uid = unit.id
        record = self.fold.units[uid]
        effects = self.policy
        if record.phase == "complete":
            return
        if not effects.effect_allowed("local_commit"):
            # Approved work that the runtime may not commit is handed to the operator, never "completed":
            # the park keeps it in a checkpoint ref and the report lists the decision.
            raise UnitPark("awaiting_operator", f"approved work left uncommitted on branch {record.branch}: local_commit is not permitted; commit it yourself or authorize local_commit",
                           decision={"options": ["skip"]})
        # commit
        if record.phase in {"commit", "implement", "review", "gates", "contain"}:
            tree = self.git.worktree_tree()
            if record.tree and tree != record.tree:
                raise UnitPark("awaiting_operator", f"working tree {tree[:12]} differs from the reviewed tree {record.tree[:12]}; nothing committed",
                               decision={"options": ["retry", "skip"]})
            message = f"{uid}: {unit.title}\n\nbatch: {self.batch_id}\nspec_revision: {unit.spec_revision}\ntree: {tree}"

            def commit(intent: dict) -> dict:
                self.git.run("add", "-A", "--", ".")
                files = self.git.run("diff", "--cached", "--name-only")
                if not files:
                    # HEAD already holds the reviewed tree but no journaled step produced it: never adopt it.
                    return {"_status": "ambiguous", "empty": True, "files": [], "detail": f"nothing to commit: HEAD {self.git.head()[:12]} already holds the reviewed tree but is not a journaled commit of {uid}"}
                self.git.run("commit", "--quiet", "-m", message)
                return {"commit": self.git.head(), "empty": False, "files": files.splitlines()}

            prior = self.fold.steps.get(f"{uid}:commit:{tree}")
            if prior and prior.get("status") == "ok" and (prior.get("result") or {}).get("commit"):
                # The commit was journaled but the phase change was not (crash in between): adopt the
                # journaled commit, never whatever the branch points at now.
                result = prior["result"]
                tip = self.git.rev(record.branch)
                if tip != result["commit"]:
                    raise UnitPark("awaiting_operator", f"branch {record.branch} points at {str(tip)[:12]} but the journaled commit is {result['commit'][:12]}",
                                   decision={"options": ["retry", "skip"]})
            else:
                result = self.step(f"{uid}:commit:{tree}", "local_commit", uid, "commit", {"type": "commit", "tree": tree, "message": message, "parent": self.git.head()}, commit)
            if not result.get("commit"):
                raise UnitPark("awaiting_operator", "commit_ambiguous: " + str(result.get("detail", ""))[:200], decision={"options": ["retry", "skip"]})
            self.unit_state(uid, "running", "", phase="push", commit=result["commit"], tree=tree)
            record = self.fold.units[uid]
        # push
        if record.phase == "push":
            if effects.effect_allowed("push"):
                remote_before = run_argv([self.git.exe, "ls-remote", "--heads", "origin", record.branch], self.repo, 120)
                if remote_before["exit_code"] != 0:
                    raise UnitPark("parked", "remote unreachable before push: " + remote_before["stderr"][-200:])
                before = remote_before["stdout"].split()[0] if remote_before["stdout"].strip() else ""

                def push(intent: dict) -> dict:
                    tip = self.git.rev(record.branch)
                    if tip != record.commit:
                        return {"_status": "failed", "ambiguous": True, "detail": f"branch {record.branch} points at {str(tip)[:12]}, not the reviewed {record.commit[:12]}; nothing pushed"}
                    # The refspec pins the effect to the reviewed commit; the branch name is only the destination.
                    out = run_argv([self.git.exe, "push", "--quiet", "origin", f"{record.commit}:refs/heads/{record.branch}"], self.repo, 600)
                    if out["exit_code"] == 0:
                        return {"pushed": record.commit}
                    # An error reply does not prove the push failed: look at the remote before deciding.
                    after = run_argv([self.git.exe, "ls-remote", "--heads", "origin", record.branch], self.repo, 120)
                    remote_now = after["stdout"].split()[0] if after["exit_code"] == 0 and after["stdout"].strip() else ("" if after["exit_code"] == 0 else None)
                    if remote_now == record.commit:
                        return {"pushed": record.commit, "detail": "push reported an error but the remote is at the commit: " + out["stderr"][-200:]}
                    if remote_now == before:
                        return {"_status": "failed", "detail": out["stderr"][-400:]}
                    return {"_status": "failed", "ambiguous": True, "detail": f"push errored and the remote is at {str(remote_now)[:12] or 'absent/unknown'}, neither the commit nor the pre-push state: " + out["stderr"][-200:]}
                result = self.step(f"{uid}:push:{record.commit}", "push", uid, "push", {"type": "push", "commit": record.commit, "branch": record.branch}, push,
                                   context={"remote_before": before})
                if not result.get("pushed"):
                    detail = str(result.get("detail", ""))
                    if result.get("ambiguous"):
                        raise UnitPark("awaiting_operator", "push_ambiguous: " + detail[:200], decision={"options": ["retry", "skip"]})
                    move = self.failure(unit, "transient" if _TRANSIENT.search(detail) else "environment", normalize_signature("push", detail), detail, phase="push")
                    if move == "retry":
                        return self.deliver(unit)
                self.unit_state(uid, "running", "", phase="pull_request")
            else:
                self.unit_state(uid, "running", "", phase="merge")
            record = self.fold.units[uid]
        # pull request
        if record.phase == "pull_request":
            if effects.effect_allowed("pull_request"):
                base = self.base_branch
                title = f"{uid}: {unit.title}"[:120]

                def pr(intent: dict) -> dict:
                    rows = self._find_pr(record.branch, uid)
                    if rows is None:
                        return {"_status": "failed", "detail": "gh pr list failed before create"}
                    if rows:
                        row = rows[0]
                        if row.get("baseRefName") != base or row.get("headRefOid") != record.commit:
                            return {"_status": "failed", "detail": f"pull request {row.get('number')} exists for this branch with base {row.get('baseRefName')} at head {str(row.get('headRefOid'))[:12]}, not {base} at {record.commit[:12]}"}
                        state = str(row.get("state", "")).upper()
                        if state == "MERGED":
                            return {"url": row.get("url"), "number": row.get("number"), "existing": True, "merged": True}
                        if state != "OPEN":
                            return {"_status": "failed", "detail": f"pull request {row.get('number')} for this branch is {state}"}
                        return {"url": row.get("url"), "number": row.get("number"), "existing": True}
                    expected_repo = self._resolve_target_repository(uid)
                    body = f"Batch {self.batch_id}, unit {uid}. Spec {unit.spec_path.relative_to(self.repo).as_posix()} @ {unit.spec_revision}.\n\nGenerated by tl_runtime {RUNTIME_VERSION}."
                    out = run_argv([*self.config["gh_argv"], "pr", "create", "--repo", expected_repo, "--head", record.branch, "--base", base, "--title", title, "--body", body], self.repo, 300)
                    if out["exit_code"] != 0:
                        return {"_status": "failed", "detail": out["stderr"][-400:]}
                    url = out["stdout"].strip().splitlines()[-1] if out["stdout"].strip() else ""
                    number = int(url.rstrip("/").rsplit("/", 1)[-1]) if url.rstrip("/").rsplit("/", 1)[-1].isdigit() else None
                    return {"url": url, "number": number}
                result = self.step(f"{uid}:pr", "pull_request", uid, "pull_request", {"type": "pull_request", "branch": record.branch, "base": base, "title": title, "commit": record.commit}, pr)
                if result.get("number") is None and not result.get("url"):
                    raise UnitPark("parked", "pull_request_failed: " + str(result.get("detail", ""))[:200])
                if result.get("merged"):
                    self.note(f"{uid}: pull request {result.get('number')} was already merged with the reviewed base and head")
                    self.unit_state(uid, "running", "", phase="complete", merged=True, pr={"url": result.get("url"), "number": result.get("number")})
                else:
                    self.unit_state(uid, "running", "", phase="ci", pr={"url": result.get("url"), "number": result.get("number")})
            else:
                self.unit_state(uid, "running", "", phase="merge")
            record = self.fold.units[uid]
        # ci
        if record.phase == "ci":
            if self.config["ci"].get("enabled") and record.pr.get("number"):
                outcome = self.ci_loop(unit)
                if outcome == "rework":
                    self.unit_state(uid, "running", "", phase="implement")
                    self.rounds(unit)
                    self.unit_state(uid, "running", "", phase="commit")
                    return self.deliver(unit)
            self.unit_state(uid, "running", "", phase="merge")
            record = self.fold.units[uid]
        # merge
        if record.phase == "merge":
            if record.pr.get("number") and effects.effect_allowed("pull_request_merge"):
                if self.config["ci"].get("enabled") and record.ci.get("state") != "success":
                    self.note(f"{uid}: merge skipped, CI state {record.ci.get('state') or 'unknown'}")
                else:
                    view = self._pr_view(record.pr["number"], uid)
                    if view is None:
                        raise UnitPark("awaiting_operator", f"gh pr view failed before merge evaluation for PR {record.pr['number']}", decision={"options": ["retry", "skip"]})
                    if str(view.get("state", "")).upper() == "MERGED" and view.get("baseRefName") == self.base_branch and view.get("headRefOid") == record.commit:
                        self.unit_state(uid, "running", "", phase="complete", merged=True)
                        return

                    authority_mode = getattr(unit, "authority_mode", "") or self.batch.get("authorization", {}).get("authority_mode", "")
                    if not authority_mode:
                        raise UnitPark("awaiting_operator", f"missing_authority_mode: unit {uid} must declare authority_mode to execute merge", decision={"options": ["retry", "skip"]})

                    if authority_mode == "delegated_single_merge":
                        checker_commit = getattr(unit, "checker_approved_commit", "")
                        candidate_commit = getattr(unit, "integration_candidate_commit", "")
                        if not checker_commit or not candidate_commit:
                            raise UnitPark("awaiting_operator", f"missing_commit_bindings: unit {uid} in delegated_single_merge must declare checker_approved_commit and integration_candidate_commit", decision={"options": ["retry", "skip"]})
                        if not _COMMIT_RE.match(checker_commit) or not _COMMIT_RE.match(candidate_commit):
                            raise UnitPark("awaiting_operator", f"invalid_commit_bindings: unit {uid} in delegated_single_merge requires 40-hex lowercase commits", decision={"options": ["skip"]})
                        if candidate_commit != record.commit:
                            raise UnitPark("awaiting_operator", f"candidate_commit_mismatch: unit {uid} candidate {candidate_commit} != record.commit {record.commit}", decision={"options": ["retry", "skip"]})
                        delta_ok, delta_reason = validate_post_review_delta(self.repo, checker_commit, candidate_commit)
                        if not delta_ok:
                            raise UnitPark("awaiting_operator", f"unapproved_post_review_delta: {delta_reason}", decision={"options": ["skip"]})
                    elif authority_mode in ("human_merge_only.enforced", "human_merge_only.policy_only", "human_merge_only"):
                        raise UnitPark("awaiting_operator", f"human_merge_only: unit {uid} configured for {authority_mode}", decision={"options": ["retry", "skip"]})
                    else:
                        raise UnitPark("awaiting_operator", f"unsupported_authority_mode: {authority_mode}", decision={"options": ["skip"]})
                    expected_repo = self._resolve_target_repository(uid)
                    comments = view.get("comments") or []

                    store = getattr(self, "authority_store", None)
                    if store is None:
                        store = LocalLedgerAuthorityStore(self.repo / "_tl-orc" / "project" / "consumption-ledger.jsonl")
                        self.authority_store = store

                    trust_root = getattr(self, "trust_root", None)
                    gh_cmd = list(self.config.get("gh_argv", ["gh"]))
                    if trust_root is None and TrustRoot is not None:
                        try:
                            trust_root = TrustRoot.from_platform(
                                app_slug=IMMUTABLE_PLATFORM_AUTHORITY_APP_SLUG,
                                gh_executable=gh_cmd,
                            )
                        except Exception:
                            trust_root = TrustRoot.from_env()
                        self.trust_root = trust_root

                    if MergeAuthorityGate is not None:
                        receipt = MergeAuthorityGate.evaluate(
                            repo_root=self.repo,
                            pr_number=record.pr["number"],
                            live_pr_info=view,
                            checker_commit=checker_commit,
                            candidate_commit=candidate_commit,
                            authority_store=store,
                            expected_repo=expected_repo,
                            comments=comments,
                            enforce_mode=authority_mode,
                            trust_root=trust_root,
                            gh_executable=gh_cmd,
                        )
                        if not receipt.is_confirmed:
                            if receipt.degraded_mode:
                                raise UnitPark("awaiting_operator", f"human_merge_only: {receipt.reason}", decision={"options": ["retry", "skip"]})
                            raise UnitPark("awaiting_operator", f"merge_authority_not_confirmed: {receipt.reason}", decision={"options": ["retry", "skip"]})

                        receipt_mode = getattr(receipt, "authority_mode", "")
                        env_mode = receipt.envelope.get("authority_mode") if isinstance(receipt.envelope, dict) else None
                        if receipt_mode != "delegated_single_merge" or env_mode != "delegated_single_merge":
                            raise UnitPark(
                                "awaiting_operator",
                                f"strict_authority_mode_required: automated merge requires delegated_single_merge (receipt_mode={receipt_mode!r}, env_mode={env_mode!r})",
                                decision={"options": ["retry", "skip"]},
                            )
                        if not receipt.is_authentic(trust_root, expected_repo=expected_repo):
                            raise UnitPark(
                                "awaiting_operator",
                                "fabricated_authority_receipt_rejected: receipt failed authenticity check against trust root",
                                decision={"options": ["retry", "skip"]},
                            )
                        if self.authority is not None:
                            # T032 §2.9: allowed_effects.merge is a capability flag, never a bypass.
                            # The Story Authority is subordinate to the T028 gate, not above it.
                            try:
                                story_authority.assert_merge_authority(
                                    self.authority.payload, receipt, trust_root=trust_root, expected_repo=expected_repo)
                            except story_authority.HardStop as stop:
                                raise UnitPark("awaiting_operator", f"{stop.reason}: {stop.detail}"[:200],
                                               decision={"options": ["retry", "skip"]}) from stop
                    else:
                        raise UnitPark("awaiting_operator", "merge_authority_unavailable: MergeAuthorityGate could not be loaded", decision={"options": ["skip"]})

                    def merge(intent: dict) -> dict:
                        curr_view = self._pr_view(record.pr["number"], uid)
                        if curr_view is None:
                            return {"_status": "failed", "detail": "gh pr view failed before merge"}
                        if str(curr_view.get("state", "")).upper() == "MERGED" and curr_view.get("baseRefName") == intent["base"] and curr_view.get("headRefOid") == record.commit:
                            if receipt and receipt.base_sha and curr_view.get("baseRefOid") != receipt.base_sha:
                                return {"_status": "failed", "base_sha_mismatch": curr_view.get("baseRefOid"), "detail": f"already merged into unexpected base SHA {curr_view.get('baseRefOid')} != {receipt.base_sha}"}
                            return {"merged": True, "detail": "already merged with the reviewed base and head (merge queue or operator)"}

                        # Strict TOCTOU revalidation immediately before invoking gh pr merge
                        if receipt is not None and receipt.is_confirmed:
                            curr_base = curr_view.get("baseRefOid")
                            curr_head = curr_view.get("headRefOid")
                            if not curr_base or curr_base != receipt.base_sha:
                                return {"_status": "failed", "detail": f"toctou_base_drift: base moved from {receipt.base_sha} to {curr_base}"}
                            if not curr_head or curr_head != receipt.head_sha:
                                return {"_status": "failed", "detail": f"toctou_head_drift: head moved from {receipt.head_sha} to {curr_head}"}

                        if curr_view.get("baseRefName") != intent["base"] or curr_view.get("headRefOid") != record.commit or str(curr_view.get("state", "")).upper() != "OPEN":
                            return {"_status": "failed", "detail": f"pull request {record.pr['number']} is {curr_view.get('state')} against {curr_view.get('baseRefName')} at {str(curr_view.get('headRefOid'))[:12]}; reviewed: {intent['base']} at {record.commit[:12]}"}

                        # Defense-in-depth: strict authority revalidation immediately prior to execution
                        if (
                            receipt is None
                            or not receipt.is_confirmed
                            or getattr(receipt, "authority_mode", "") != "delegated_single_merge"
                            or not isinstance(receipt.envelope, dict)
                            or receipt.envelope.get("authority_mode") != "delegated_single_merge"
                            or not receipt.is_authentic(trust_root, expected_repo=expected_repo)
                        ):
                            return {
                                "_status": "failed",
                                "detail": "strict_authority_verification_failed: merge aborted without authentic delegated_single_merge receipt",
                            }

                        out = run_argv([*self.config["gh_argv"], "pr", "merge", str(record.pr["number"]), "--repo", expected_repo, "--merge", "--delete-branch=false", "--match-head-commit", record.commit], self.repo, 300)
                        self._fault_point("after_call:pull_request_merge")
                        if out["exit_code"] != 0:
                            return {"_status": "failed", "detail": out["stderr"][-400:]}
                        after = self._pr_view(record.pr["number"], uid)
                        if after is None:
                            return {"_status": "ambiguous", "merged": False, "queued": True, "detail": "gh pr merge returned success but gh pr view failed afterwards; verify and retry"}
                        if str(after.get("state", "")).upper() != "MERGED":
                            return {"_status": "ambiguous", "merged": False, "queued": True, "detail": f"gh pr merge returned success but the pull request is still {after.get('state')} (merge queue or delayed merge); verify and retry"}
                        
                        term_head = after.get("headRefOid")
                        term_base = after.get("baseRefOid")
                        if not term_head or not term_base:
                            return {
                                "_status": "failed",
                                "terminal_missing_commit_bindings": True,
                                "detail": f"terminal_missing_commit_bindings: headRefOid={term_head}, baseRefOid={term_base}",
                            }

                        if after.get("baseRefName") != intent["base"]:
                            return {"merged": True, "base_mismatch": after.get("baseRefName")}
                        expected_head = receipt.candidate_commit if (receipt and receipt.candidate_commit) else record.commit
                        if term_head != expected_head:
                            return {"merged": True, "head_mismatch": term_head}
                        if receipt and receipt.base_sha and term_base != receipt.base_sha:
                            return {"merged": True, "base_sha_mismatch": term_base}
                        return {"merged": True}

                    result = self.step(f"{uid}:merge:{record.commit}", "pull_request_merge", uid, "merge", {"type": "pull_request_merge", "pr": record.pr["number"], "commit": record.commit, "base": self.base_branch}, merge)
                    if result.get("queued"):
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        raise UnitPark("awaiting_operator", "merge_queued: " + str(result.get("detail", ""))[:200], decision={"options": ["retry", "skip"]})
                    if result.get("terminal_missing_commit_bindings"):
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        raise UnitPark("awaiting_operator", f"terminal_missing_commit_bindings: pull request {record.pr['number']} terminal view missing headRefOid or baseRefOid",
                                       decision={"options": ["retry", "skip"]})
                    if result.get("merged") and result.get("head_mismatch"):
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        self.unit_state(uid, "running", "", phase="complete", merged=True)
                        raise UnitPark("awaiting_operator", f"merged_unexpected_head: pull request {record.pr['number']} merged at {str(result['head_mismatch'])[:12]}, not the reviewed {record.commit[:12]}",
                                       decision={"options": ["skip"]})
                    if result.get("merged") and result.get("base_mismatch"):
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        self.unit_state(uid, "running", "", phase="complete", merged=True)
                        raise UnitPark("awaiting_operator", f"merged_into_unexpected_base: pull request {record.pr['number']} was retargeted to {result['base_mismatch']} between the check and the merge",
                                       decision={"options": ["skip"]})
                    if result.get("merged") and result.get("base_sha_mismatch"):
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        self.unit_state(uid, "running", "", phase="complete", merged=True)
                        raise UnitPark("awaiting_operator", f"merged_into_unexpected_base_sha: pull request {record.pr['number']} merged into base SHA {str(result['base_sha_mismatch'])[:12]}, not the authorized {str(receipt.base_sha)[:12]}",
                                       decision={"options": ["skip"]})
                    if result.get("merged"):
                        if receipt and receipt.authorization_id:
                            consumed_ok = False
                            try:
                                consumed_ok = store.commit_consumed(receipt.authorization_id)
                            except Exception:
                                consumed_ok = False
                            if not consumed_ok:
                                try:
                                    store.mark_indeterminate(receipt.authorization_id)
                                except Exception:
                                    pass
                                raise UnitPark("awaiting_operator", f"authority_commit_consumed_failed: pull request {record.pr['number']} authority token could not be consumed (CAS state conflict or indeterminate)",
                                               decision={"options": ["skip"]})
                        self.unit_state(uid, "running", "", phase="complete", merged=True)
                    else:
                        if receipt and receipt.authorization_id:
                            store.mark_indeterminate(receipt.authorization_id)
                        raise UnitPark("awaiting_operator", "merge_failed: " + result.get("detail", "")[:200], decision={"options": ["retry", "skip"]})
            elif not record.pr.get("number") and effects.effect_allowed("local_merge") and self.base_branch:
                base = self.base_branch
                protected_bases = set(self.config.get("protected_bases", self.config.get("protected_branches", [])))
                if base in protected_bases:
                    raise UnitPark("awaiting_operator", f"merge_authority_not_confirmed: local_merge_to_protected_base_{base}_not_authorized", decision={"options": ["retry", "skip"]})

                def local_merge(intent: dict) -> dict:
                    tip = self.git.rev(record.branch)
                    if tip != record.commit:
                        return {"_status": "failed", "detail": f"branch {record.branch} moved to {str(tip)[:12]} after review of {record.commit[:12]}"}
                    self.git.run("checkout", "--quiet", base)
                    out = run_argv([self.git.exe, "merge", "--no-ff", "--no-edit", record.commit], self.repo, 300)
                    if out["exit_code"] != 0:
                        run_argv([self.git.exe, "merge", "--abort"], self.repo, 60)
                        return {"_status": "failed", "detail": out["stderr"][-400:] or out["stdout"][-400:]}
                    return {"merged": True, "base_commit": self.git.head()}
                result = self.step(f"{uid}:local_merge:{record.commit}", "local_merge", uid, "merge", {"type": "local_merge", "branch": record.branch, "base": base, "commit": record.commit}, local_merge,
                                   context={"base_before": self.git.rev(base) or ""})
                if not result.get("merged"):
                    raise UnitPark("awaiting_operator", "local_merge_conflict: " + result.get("detail", "")[:200], decision={"options": ["retry", "skip"]})
                self.unit_state(uid, "running", "", phase="complete", merged=True)
            self.unit_state(uid, "running", "", phase="complete")

    def ci_loop(self, unit: Unit) -> str:
        uid = unit.id
        self.ci.target_repository = self._resolve_target_repository(uid)
        record = self.fold.units[uid]
        number = record.pr["number"]
        deadline = time.time() + float(self.config["ci"]["timeout_seconds"])
        reruns = sum(1 for a in record.attempts if a.get("class") == "ci_rerun")
        while True:
            checks = self.step(f"{uid}:ci:{record.commit}:{int(time.time())}", "ci_query", uid, "ci", {"type": "ci_poll", "pr": number, "commit": record.commit},
                               lambda intent: self.ci.checks(number), cacheable=False)
            state = checks.get("state")
            self.unit_state(uid, "running", "", phase="ci", ci={"state": state, "commit": record.commit})
            if state == "success":
                return "ok"
            if state in {"pending", "none", "unknown"}:
                if time.time() > deadline:
                    raise UnitPark("awaiting_operator", f"ci_timeout: state {state} after {self.config['ci']['timeout_seconds']}s", decision={"options": ["retry", "skip"]})
                self.sleep(float(self.config["ci"]["poll_seconds"]))
                continue
            log, raw_ref = self.ci.failed_log(number, record.branch, record.commit)
            slice_ = tl_ci_slice.slice_log(log, raw_ref=raw_ref) if log else {"classification": "unknown", "signature": normalize_signature("ci", "nolog"), "excerpt": "", "failed_tests": []}
            self.journal.append("note", text=f"{uid}: CI failure {slice_['classification']}", ci_slice={k: v for k, v in slice_.items() if k != "excerpt"})
            if slice_["classification"] in {"external_infrastructure", "unknown"} and not slice_.get("failed_tests") and reruns < int(self.limits["flaky_reruns"]):
                if not self.policy.effect_allowed("ci_rerun"):
                    raise UnitPark("parked", f"ci_{slice_['classification']}: rerun not permitted (permitted_effects.ci_rerun)")
                reruns += 1
                self.journal.append("attempt", unit=uid, phase="ci", round=record.round, **{"class": "ci_rerun"}, signature=slice_["signature"], detail=slice_["classification"], tree=record.tree, findings_digest="", move="rerun", step_id="")
                record.attempts.append({"class": "ci_rerun", "phase": "ci", "signature": slice_["signature"]})
                rerun = self.step(f"{uid}:ci_rerun:{record.commit}:{reruns}", "ci_rerun", uid, "ci", {"type": "ci_rerun", "commit": record.commit, "n": reruns},
                                  lambda intent: {"rerun": self.ci.rerun_failed(record.branch, record.commit)})
                if not rerun.get("rerun"):
                    raise UnitPark("parked", "ci_rerun_failed: " + slice_["classification"])
                self.sleep(float(self.config["ci"]["poll_seconds"]))
                continue
            if slice_["classification"] == "code_failure":
                move = self.failure(unit, "verification", slice_["signature"], "ci: " + ", ".join(slice_.get("failed_tests") or [])[:300], phase="ci")
                if move == "rework":
                    record.decision = {"feedback": {"ci_slice": slice_}}
                    self.unit_state(uid, "running", "", phase="implement", decision=record.decision)
                    return "rework"
                return "ok"
            raise UnitPark("parked", f"ci_{slice_['classification']}: {slice_['signature']}")

    # ---- recovery -------------------------------------------------------------------------

    def reconcile(self) -> None:
        """Resolve every intent that has no result, with evidence, before scheduling anything."""
        if self.authority is not None:
            # The authority journal is authoritative on resume: reservations it still holds are
            # settled here, and the child ledger is then rebuilt from that state, never the reverse.
            open_steps = {intent["step_id"] for intent in self.fold.open_intents}

            def verdict(attempt: dict) -> str:
                step_id = attempt.get("logical_call_id", "")
                prior = self.fold.steps.get(step_id)
                if prior and prior.get("status") == "released":
                    return "released"
                if prior and prior.get("status") == "ok":
                    return "consumed"
                if step_id in open_steps:
                    return "ambiguous"
                return "ambiguous"

            self.authority.reconcile_orphan_reservations(self.batch_id, verdict)
            self.authority.reconcile_child_batch(self.batch, self.batch_id)
        for intent in list(self.fold.open_intents):
            step_id = intent["step_id"]
            effect = intent.get("effect_class")
            uid = intent.get("unit", "")
            if intent.get("runtime_stamp") != self.stamp and not self._version_accepted():
                self.journal.append("batch_state", state="stopped", reason="stale_workflow_version", detail=f"open step {step_id} was journaled by {intent.get('runtime_stamp')}, running {self.stamp}")
                self.refold()
                raise Refusal("stale_workflow_version: rerun with --accept-stale-version after inspecting the open step", 2)
            verdict, result = self._reconcile_one(intent)
            self.journal.append("recovery", step_id=step_id, effect_class=effect, unit=uid, verdict=verdict, detail=str(result.get("detail", ""))[:300])
            self.journal.append("step_result", step_id=step_id, unit=uid, phase=intent.get("phase"), effect_class=effect, status=verdict,
                                input_digest=intent.get("input_digest"), result=result, tree_after=self.git.worktree_tree() if intent.get("tree_before") else "", evidence=[], reconciled=True)
            if verdict == "ambiguous" and uid and uid in self.fold.units:
                self._checkpoint_dirty(uid, intent)
            if verdict == "ambiguous" and effect in {"local_commit", "local_merge", "push", "pull_request", "pull_request_merge"}:
                self.unit_state(uid, "awaiting_operator", f"ambiguous effect after crash: {step_id}: {str(result.get('detail', ''))[:160]}", decision={"options": ["retry", "skip"]})
        self.refold()
        for uid, record in self.fold.units.items():
            if record.state == "running":
                dirty = self.git.dirty_paths()
                if dirty and self.git.current_branch() == record.branch:
                    self._checkpoint_dirty(uid, {"step_id": "resume"})
                self.unit_state(uid, "retryable", "resumed after restart", phase=record.phase)
        self.refold()

    def _pr_view(self, number, unit_id: str | None = None) -> dict | None:
        expected_repo = self._resolve_target_repository(unit_id)
        out = run_argv([*self.config["gh_argv"], "pr", "view", str(number), "--repo", expected_repo, "--json", "state,mergedAt,headRefOid,baseRefName,baseRefOid,comments"], self.repo, 120)
        try:
            view = json.loads(out["stdout"] or "{}") if out["exit_code"] == 0 else None
        except ValueError:
            view = None
        return view if isinstance(view, dict) else None

    def _resolve_target_repository(self, unit_id: str | None = None) -> str:
        repo = ""
        if unit_id and unit_id in self.units and getattr(self.units[unit_id], "target_repository", ""):
            repo = self.units[unit_id].target_repository
        if not repo:
            repo = self.config.get("target_repository") or self.batch.get("authorization", {}).get("target_repository")
        if not repo or not isinstance(repo, str):
            raise Refusal("missing_or_invalid_target_repository", 2)
        repo_str = repo.strip()
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo_str):
            raise Refusal(f"missing_or_invalid_target_repository: '{repo}'", 2)
        return repo_str

    def _find_pr(self, branch: str, unit_id: str | None = None) -> list | None:
        """Open or merged pull requests whose head is `branch`; None when gh failed."""
        expected_repo = self._resolve_target_repository(unit_id)
        out = run_argv([*self.config["gh_argv"], "pr", "list", "--repo", expected_repo, "--head", branch, "--state", "all", "--json", "number,url,baseRefName,headRefOid,state", "--limit", "1"], self.repo, 120)
        try:
            rows = json.loads(out["stdout"] or "[]") if out["exit_code"] == 0 else None
        except ValueError:
            rows = None
        return rows if isinstance(rows, list) or rows is None else None

    def _version_accepted(self) -> bool:
        return any(d.get("option") == "accept_stale_version" and d.get("stamp") == self.stamp for d in self.fold.decisions)

    def _checkpoint_dirty(self, uid: str, intent: dict) -> None:
        record = self.fold.units.get(uid)
        if record is None or not record.branch or self.git.current_branch() != record.branch:
            return
        if not self.git.dirty_paths():
            return
        tree = self.git.worktree_tree()
        ref = f"refs/tl/checkpoints/{self.batch_id}/{uid}/{len(record.checkpoints) + 1}"
        commit = self.git.checkpoint(tree, f"checkpoint {uid} after {intent.get('step_id')}", ref)
        self.unit_state(uid, record.state, record.reason, checkpoints=record.checkpoints + [commit])

    def _reconcile_one(self, intent: dict) -> tuple[str, dict]:
        effect = intent.get("effect_class")
        payload = intent.get("intent") or {}
        step_id = intent["step_id"]
        if effect == "model_call":
            status = self.harness.inspect(step_id, str(intent.get("input_digest", "")))
            state = status.get("state")
            if state == "not_started":
                return "released", {"detail": "harness never started; call not consumed"}
            if state in {"starting", "running"}:
                # Attach to the still-running supervisor instead of dispatching a second call.
                role = "maker" if "maker" in step_id else "checker"
                unit_name = self.harness.job_name(step_id, str(intent.get("input_digest", "")))
                wait = run_argv([sys.executable, str(self.harness.tl_job), "wait", "--state-dir", str(self.harness.jobs_dir / unit_name), "--unit", unit_name,
                                 "--timeout", str(int(self.config["roles"][role]["timeout_seconds"]) + 60)], self.repo, int(self.config["roles"][role]["timeout_seconds"]) + 120)
                status = _receipt_json(wait)
                state = status.get("state")
            if state in tl_job.TERMINAL_STATES:
                return "ambiguous", {"detail": f"harness ended ({state}) before the result was journaled; call consumed, unit continues from checkpoint"}
            return "ambiguous", {"detail": f"harness state {state}; call consumed conservatively"}
        if effect == "local_commit":
            head = self.git.head()
            head_tree = self.git.run("rev-parse", "HEAD^{tree}")
            parent = payload.get("parent")
            head_parent = self.git.rev("HEAD^") or ""
            if head_tree == payload.get("tree") and (not parent or head_parent == parent):
                files = self.git.run("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
                return "ok", {"commit": head, "empty": False, "files": files.splitlines(), "detail": "commit found on HEAD"}
            if parent and head != parent and run_argv([self.git.exe, "merge-base", "--is-ancestor", parent, "HEAD"], self.repo, 60)["exit_code"] == 0:
                # Something committed after the journaled parent, but HEAD is not exactly our commit: never adopt it.
                return "ambiguous", {"detail": f"HEAD moved to {head[:12]} past the journaled parent {parent[:12]}; commit not adopted"}
            return "released", {"detail": "commit not present; will redo"}
        if effect == "push":
            branch, commit = payload.get("branch", ""), payload.get("commit", "")
            remote = run_argv([self.git.exe, "ls-remote", "--heads", "origin", branch], self.repo, 120)
            if remote["exit_code"] != 0:
                return "ambiguous", {"detail": "remote unreachable: " + remote["stderr"][-200:]}
            remote_sha = remote["stdout"].split()[0] if remote["stdout"].strip() else ""
            if remote_sha == commit:
                return "ok", {"pushed": commit, "detail": "remote already at expected commit"}
            before = (intent.get("intent_context") or {}).get("remote_before")
            if before is not None and remote_sha == before:
                return "released", {"detail": "remote exactly as observed before the push intent; push will run"}
            if before is None and not remote_sha:
                return "released", {"detail": "remote branch absent; push will run"}
            return "ambiguous", {"detail": f"remote at {remote_sha[:12] or 'absent'}: neither the pushed commit {commit[:12]} nor the pre-push state {str(before)[:12] or 'absent'}"}
        uid = intent.get("unit", "")
        if effect == "pull_request":
            rows = self._find_pr(payload.get("branch", ""), uid)
            if rows is None:
                return "ambiguous", {"detail": "gh pr list failed"}
            if rows:
                row = rows[0]
                expected_head = payload.get("commit") or self.git.rev(payload.get("branch", "")) or ""
                if row.get("baseRefName") != payload.get("base") or not row.get("headRefOid") or row.get("headRefOid") != expected_head:
                    return "ambiguous", {"detail": f"pull request {row.get('number')} exists but base/head differ from the journaled intent"}
                state = str(row.get("state", "")).upper()
                if state == "MERGED":
                    return "ok", {"url": row.get("url"), "number": row.get("number"), "merged": True, "detail": "pull request already merged with the reviewed base and head"}
                if state != "OPEN":
                    return "ambiguous", {"detail": f"pull request {row.get('number')} is {state}"}
                return "ok", {"url": row.get("url"), "number": row.get("number"), "detail": "pull request already exists"}
            return "released", {"detail": "no pull request for branch; create will run"}
        if effect == "pull_request_merge":
            view = self._pr_view(payload.get("pr", ""), uid)
            if view is None:
                return "ambiguous", {"detail": "gh pr view failed"}
            if str(view.get("state", "")).upper() == "MERGED" or view.get("mergedAt"):
                if payload.get("base") and view.get("baseRefName") != payload.get("base"):
                    return "ambiguous", {"detail": f"pull request merged into {view.get('baseRefName')}, not the reviewed base {payload.get('base')}"}
                if payload.get("commit") and view.get("headRefOid") != payload.get("commit"):
                    return "ambiguous", {"detail": f"pull request merged at head {str(view.get('headRefOid'))[:12]}, not the reviewed commit {str(payload.get('commit'))[:12]}"}
                return "ok", {"merged": True, "detail": "pull request already merged"}
            # An enqueued merge leaves the PR OPEN, exactly like a merge that never ran: the state cannot
            # prove the call did not happen, so the operator decides (retry adopts a queue merge without a new call).
            return "ambiguous", {"detail": "pull request still open after an interrupted merge intent; a merge queue may hold it"}
        if effect == "ci_rerun":
            return "ambiguous", {"rerun": True, "detail": "rerun may have been requested; counted, not repeated"}
        if effect == "local_merge":
            base = payload.get("base", "")
            commit = payload.get("commit") or payload.get("branch", "")
            check = run_argv([self.git.exe, "merge-base", "--is-ancestor", commit, base], self.repo, 60)
            if check["exit_code"] == 0:
                return "ok", {"merged": True, "base_commit": self.git.rev(base), "detail": "reviewed commit already reachable from base"}
            if run_argv([self.git.exe, "rev-parse", "-q", "--verify", "MERGE_HEAD"], self.repo, 60)["exit_code"] == 0:
                return "ambiguous", {"detail": "a merge is in progress in the working tree; not aborted, operator decides"}
            base_before = (intent.get("intent_context") or {}).get("base_before")
            base_now = self.git.rev(base) or ""
            if base_before is None or base_now == base_before:
                return "released", {"detail": "base exactly as observed before the merge intent; merge will run"}
            return "ambiguous", {"detail": f"base {base} moved from {str(base_before)[:12]} to {base_now[:12]} while the merge intent was open; operator decides"}
        return "released", {"detail": "no external effect; step will rerun"}


class UnitPark(Exception):
    def __init__(self, state: str, reason: str, decision: dict | None = None):
        super().__init__(reason)
        self.state = state
        self.reason = reason
        self.decision = decision or {}


# --------------------------------------------------------------------------- projections

def _usage_totals(fold: Fold) -> dict:
    totals = {"calls": fold.model_calls_done, "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
              "calls_with_tokens": 0, "calls_with_cost": 0}
    for usage in fold.usage:
        if isinstance(usage.get("input_tokens"), (int, float)):
            totals["calls_with_tokens"] += 1
            totals["input_tokens"] += usage.get("input_tokens") or 0
            totals["cache_read_tokens"] += usage.get("cache_read_tokens") or 0
            totals["output_tokens"] += usage.get("output_tokens") or 0
        if isinstance(usage.get("cost_usd"), (int, float)):
            totals["calls_with_cost"] += 1
            totals["cost_usd"] += float(usage["cost_usd"])
    totals["tokens_known"] = totals["calls_with_tokens"] == fold.model_calls_done and fold.model_calls_done > 0
    totals["cost_known"] = totals["calls_with_cost"] == fold.model_calls_done and fold.model_calls_done > 0
    return totals


def status_projection(runtime: "Runtime") -> dict:
    fold = runtime.fold
    units = []
    for uid in topological(runtime.units):
        record = fold.units.get(uid, UnitRecord(id=uid))
        units.append({"unit": uid, "state": record.state, "phase": record.phase, "round": record.round, "reason": record.reason,
                      "branch": record.branch, "pr": record.pr, "merged": record.merged, "attempts": len(record.attempts)})
    totals = _usage_totals(fold)
    next_unit, _ = next_ready(fold, runtime.units, runtime.batch) if not fold.closed else (None, {})
    return {
        "batch": runtime.batch_id, "state": fold.batch_state, "stop_reason": fold.stop_reason, "runtime": RUNTIME_VERSION,
        "progress": {"completed": sum(1 for u in units if u["state"] == "completed"), "total": len(units)},
        "budget": {"model_calls": totals["calls"], "max_model_calls": runtime.batch["budget"].get("max_model_calls"),
                   "cost_usd": round(totals["cost_usd"], 4) if totals["cost_known"] else "unknown"},
        "blocked": [u["unit"] for u in units if u["state"] == "blocked"],
        "waiting": [u["unit"] for u in units if u["state"] in {"awaiting_operator", "parked"}],
        "next": next_unit, "units": units, "updated_at": now_iso(),
    }


def project_batch(runtime: "Runtime") -> None:
    """Mirror the mutable sections of the batch file; the frozen sections are never touched."""
    batch = read_json_file(runtime.batch_path)
    fold = runtime.fold
    budget = batch.setdefault("budget", {})
    budget["consumed_model_calls"] = fold.model_calls_done
    budget["reserved_model_calls"] = fold.model_calls_open
    budget["pending_call"] = None
    for intent in fold.open_intents:
        if intent.get("effect_class") == "model_call":
            phase = {"implement": "implementation", "review": "review"}.get(str(intent.get("phase")), "implementation")
            budget["pending_call"] = {"call_id": intent["step_id"], "role": intent.get("intent", {}).get("type"), "phase": phase,
                                      "payload_digest": intent.get("input_digest"), "dispatched_at": intent.get("at")}
    execution = batch.setdefault("execution", {})
    running = [uid for uid, r in fold.units.items() if r.state == "running"]
    execution["current_unit"] = running[0] if running else None
    execution["current_phase"] = fold.units[running[0]].phase if running else None
    execution["current_round"] = fold.units[running[0]].round if running else 0
    execution["completed_units"] = sorted(uid for uid, r in fold.units.items() if r.state == "completed")
    execution["stop_reason"] = fold.stop_reason or None
    execution.setdefault("runtime_refs", {})
    execution["runtime_refs"]["supervisor_state_dir"] = runtime.state_dir.as_posix()
    if fold.batch_state != "in_progress":
        batch["status"] = fold.batch_state
    write_json_atomic(runtime.batch_path, batch)


def render_report(runtime: "Runtime") -> str:
    fold = runtime.fold
    order = topological(runtime.units)
    records = {uid: fold.units.get(uid, UnitRecord(id=uid)) for uid in order}
    totals = _usage_totals(fold)
    lines: list[str] = [f"# Overnight Run {runtime.batch_id}", ""]
    lines.append(f"State: **{fold.batch_state}**" + (f" ({fold.stop_reason})" if fold.stop_reason else "") + f" · runtime {RUNTIME_VERSION} · started {fold.started_at} · generated {now_iso()}")
    lines.append("")

    def section(title: str, rows: list[str], empty: str = "none"):
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(rows or [f"- {empty}"])
        lines.append("")

    meta = fold.meta or {}
    titles = {uid: (meta.get("units") or {}).get(uid, {}).get("title") or runtime.units[uid].title for uid in records}
    section("Completed", [f"- {uid}: {titles[uid]}" + (" (merged)" if r.merged else "") for uid, r in records.items() if r.state == "completed"])
    changed = []
    for uid in order:
        files: list[str] = []
        for step_id, step in fold.steps.items():
            if step_id.startswith(f"{uid}:commit:") and step.get("status") == "ok":
                files.extend((step.get("result") or {}).get("files") or [])
        if files:
            changed.append(f"- {uid}: " + ", ".join(files[:12]) + (" …" if len(files) > 12 else ""))
    section("Changed", changed)
    section("Commits / PRs", [f"- {uid}: branch `{r.branch}` commit `{r.commit[:12]}`" + (f" PR {r.pr.get('url') or r.pr.get('number')}" if r.pr else "") for uid, r in records.items() if r.commit])
    verification = []
    for step_id, step in sorted(fold.steps.items()):
        if step_id.startswith("gate:"):
            res = step.get("result") or {}
            verification.append(f"- {step_id.split(':')[1]} @ {step_id.split(':')[-1][:12]}: {'pass' if res.get('passed') else 'FAIL'}")
    for uid, r in records.items():
        if r.ci.get("state"):
            verification.append(f"- {uid}: CI {r.ci['state']} @ {r.ci.get('commit', '')[:12]}")
    section("Verification", verification)
    resolved = []
    for uid, r in records.items():
        for attempt in r.attempts:
            if attempt.get("move") in {"retry", "rework", "rerun"}:
                resolved.append(f"- {uid} {attempt.get('phase')} r{attempt.get('round', '')}: {attempt.get('class')} → {attempt.get('move')} ({str(attempt.get('detail', ''))[:100]})")
    section("Automatically Resolved", resolved)
    section("FYI", [f"- {n.get('text')}" for n in fold.notes])
    review = [f"- {uid}: PR {r.pr.get('url') or r.pr.get('number')} open, not merged" for uid, r in records.items() if r.state == "completed" and r.pr and not r.merged]
    section("REVIEW", review)
    decisions = [f"- {uid}: {r.reason} → options: {', '.join((r.decision or {}).get('options', ['retry', 'skip']))} (`tl_runtime.py decide --unit {uid} --option <choice>`)" for uid, r in records.items() if r.state == "awaiting_operator"]
    section("DECISION REQUIRED", decisions)
    section("BLOCKED", [f"- {uid}: {r.state} — {r.reason}" for uid, r in records.items() if r.state in {"parked", "blocked", "failed"}])
    cost = [f"- model calls: {totals['calls']} / {(meta.get('budget') or {}).get('max_model_calls') or runtime.batch['budget'].get('max_model_calls', '∞')}"]
    if totals["tokens_known"]:
        cost.append(f"- tokens: input {totals['input_tokens']}, cache read {totals['cache_read_tokens']}, output {totals['output_tokens']}")
    else:
        cost.append(f"- tokens: unknown ({totals['calls_with_tokens']} of {totals['calls']} calls reported usage)")
    cost.append(f"- cost: {'US$ %.2f' % totals['cost_usd'] if totals['cost_known'] else 'unknown (%d of %d calls reported cost)' % (totals['calls_with_cost'], totals['calls'])}")
    if runtime.limits.get("max_cost_usd") is not None and not totals["cost_known"]:
        cost.append("- cost cap declared but not enforceable: some calls did not report cost")
    section("Cost / Usage", cost)
    section("Models", [f"- {role}: {cfg.get('adapter')} / {cfg.get('model')} / {cfg.get('effort')} (family {cfg.get('family')})" for role, cfg in (meta.get("roles") or runtime.config["roles"]).items()])
    section("Recovery Events", [f"- {e.get('step_id')}: {e.get('verdict')} — {e.get('detail')}" for e in fold.recoveries])
    nxt = []
    if fold.batch_state == "in_progress":
        next_unit, _ = next_ready(fold, runtime.units, runtime.batch)
        nxt.append(f"- next unit: {next_unit}" if next_unit else "- nothing eligible; resolve DECISION REQUIRED / BLOCKED then rerun `tl_runtime.py run`")
    elif fold.batch_state == "done":
        nxt.append("- batch closed; the runtime never opens another batch")
    elif fold.batch_state == "blocked":
        nxt.append(f"- batch blocked: {fold.stop_reason}; `tl_runtime.py decide` on the units above reopens it for the next `run`")
    else:
        nxt.append(f"- batch {fold.batch_state}: {fold.stop_reason}; a new authorization is needed to continue")
    journaled = (fold.meta or {}).get("capabilities")
    caps = [c for c in (journaled if journaled is not None else runtime.policy.capabilities_report()) if not c.get("network_sandbox")]
    if caps:
        nxt.append("- limitation: no network sandbox for adapter(s) " + ", ".join(c["adapter"] for c in caps))
    section("What Happens Next", nxt)
    return "\n".join(lines)


def _project(self: "Runtime") -> None:
    write_json_atomic(self.state_dir / "status.json", status_projection(self))
    with contextlib.suppress(Refusal, OSError):
        project_batch(self)
    (self.state_dir / "report.md").write_text(render_report(self), encoding="utf-8")


def _notify(self: "Runtime", payload: dict) -> None:
    argv = self.config.get("notify_argv") or []
    if not argv:
        return
    run_argv([*argv, canonical(payload)], self.repo, 60, env=self.policy.worker_env())


Runtime.project = _project
Runtime.notify = _notify


# --------------------------------------------------------------------------- cli

def _runtime_from_args(args: argparse.Namespace) -> Runtime:
    repo = Path(args.repo).resolve()
    state_dir = Path(args.state_dir).resolve() if args.state_dir else None
    return Runtime(Path(args.batch).resolve(), Path(args.config).resolve(), repo, state_dir)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--batch", required=True, help="frozen batch JSON (batch.schema.json)")
    parser.add_argument("--config", required=True, help="runtime config JSON (runtime-config.schema.json)")
    parser.add_argument("--repo", default=".", help="consumer repository root")
    parser.add_argument("--state-dir", default=None, help=f"defaults to <repo>/{STATE_DIR_NAME}/<batch id>")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute the frozen batch until close, stop or idle; resumable")
    _add_common(run)
    run.add_argument("--max-units", type=int, default=None, help="stop after this many units (testing / staged runs)")
    run.add_argument("--accept-stale-version", action="store_true", help="accept an open step journaled by another runtime version")
    for name, help_text in (("status", "operator view"), ("report", "morning report from the journal"), ("validate", "read-only preflight"),
                            ("journal", "diagnostic fold of the journal")):
        p = sub.add_parser(name, help=help_text)
        _add_common(p)
        if name == "report":
            p.add_argument("--out", default=None)
        if name == "journal":
            p.add_argument("--unit", default=None)
    decide = sub.add_parser("decide", help="record the operator's decision for a unit that awaits one")
    _add_common(decide)
    decide.add_argument("--unit", required=True)
    decide.add_argument("--option", required=True, choices=["retry", "skip"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = _runtime_from_args(args)
        if args.command == "validate":
            print(canonical({"ok": True, "batch": runtime.batch_id, "units": topological(runtime.units), "stamp": runtime.stamp,
                             "frozen_scope_digest": frozen_scope_digest(runtime.batch["frozen_scope"]),
                             "capabilities": runtime.policy.capabilities_report(), "repo_clean": not runtime.git.dirty_paths()}))
            return 0
        if args.command == "run":
            if args.accept_stale_version:
                runtime.acquire()
                runtime.journal.append("decision", option="accept_stale_version", stamp=runtime.stamp)
                runtime.refold()
            state = runtime.run(max_units=args.max_units)
            print(canonical(status_projection(runtime)))
            return {"done": 0, "in_progress": 0, "stopped": 2, "blocked": 3}.get(state, 2)
        runtime.fold = runtime.journal.fold()
        if args.command == "status":
            print(canonical(status_projection(runtime)))
            return 0
        if args.command == "report":
            text = render_report(runtime)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text + "\n")
            return 0
        if args.command == "journal":
            fold = runtime.fold
            payload = {"events": fold.events, "batch_state": fold.batch_state, "open_intents": [i["step_id"] for i in fold.open_intents],
                       "steps": sorted(fold.steps), "recoveries": fold.recoveries, "usage": fold.usage,
                       "units": {uid: {"state": r.state, "phase": r.phase, "round": r.round, "reason": r.reason, "attempts": r.attempts, "checkpoints": r.checkpoints}
                                 for uid, r in fold.units.items() if not args.unit or uid == args.unit}}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.command == "decide":
            runtime.acquire()
            record = runtime.fold.units.get(args.unit)
            if record is None or record.state not in {"awaiting_operator", "parked", "blocked", "failed"}:
                raise Refusal(f"unit {args.unit} is not waiting for a decision")
            runtime.journal.append("decision", unit=args.unit, option=args.option, previous_state=record.state, reason=record.reason)
            if args.option == "retry":
                runtime.unit_state(args.unit, "retryable", "operator: retry", phase=record.phase if record.phase in PHASES else "implement")
            else:
                runtime.unit_state(args.unit, "failed", "operator: skipped")
            if runtime.fold.batch_state == "blocked":
                # A batch blocked only on decisions reopens for the next `run`; a stopped batch never does.
                runtime.journal.append("batch_state", state="in_progress", reason="operator decision")
            runtime.fold = runtime.journal.fold()
            runtime.project()
            runtime.release()
            print(canonical({"unit": args.unit, "state": runtime.fold.units[args.unit].state}))
            return 0
        raise Refusal("unknown command")
    except Refusal as exc:
        print(canonical({"error": str(exc), "code": exc.code}), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
