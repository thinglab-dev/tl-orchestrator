#!/usr/bin/env python3
"""Optional local helper around the upstream Graft CLI (structural code map, no key).

This never runs `graft init`: it does not touch AGENTS.md, CLAUDE.md, GEMINI.md, `.claude/`,
or any global config. It installs a pinned `@nanonets/graft` build into an isolated,
worktree-local cache and calls `graft build`/`ask`/`grep`/`skeleton`/`callers`/`map`/`check`
against that cache.

Guarantees this module is responsible for (each one is enforced here, not assumed):

* **The whole cache is invisible to Git and to fallback searches.** We write `*` into
  `<cache>/.gitignore` and `<cache>/.ignore` before installing anything, and we set
  `GRAFT_NO_GITIGNORE=1`/`GRAFT_NO_IGNORE=1` so upstream never edits the consumer's own
  ignore files (it would otherwise ignore only `graph/` and re-admit it to ripgrep).
* **No inherited credentials or config.** Every `GRAFT_*`/`DOTENV_CONFIG_*` variable and the
  known provider keys are stripped from the subprocess environment, and `dotenv/config` is
  pointed at a file we guarantee does not exist, so a consumer `.env` cannot reintroduce a
  key. The deep/LLM tier is therefore unreachable from here.
* **No network after `npm install`.** The CLI's `preAction` spawns a detached registry check
  once a day and writes `~/.graft/update-check.json`. We redirect `HOME`/`USERPROFILE` into
  the cache and seed a fresh check record there, so that spawn never happens and the user's
  real home is never written to.
* **Answers are verified before they are trusted.** A query is only reported as `ok` when the
  CLI exited 0, printed parseable JSON with actual results, reported no degraded refresh on
  stderr, and a follow-up `graft check --json` confirms the graph still matches the code.

Absence of Node/npm, a CLI error, a timeout, an unverified/stale graph or an empty answer is a
tool-availability fact, never evidence that matching code does not exist: callers must fall
back to `rg`/direct reads. This script never approves work and never gates a task on Graft
being present.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

# Pin an explicit, verified upstream release. Bump only after checking
# `npm view @nanonets/graft versions --json` and re-running the smoke check in
# docs/GRAFT.md.
PINNED_PACKAGE = "@nanonets/graft"
PINNED_VERSION = "0.18.0"
PINNED_SPEC = f"{PINNED_PACKAGE}@{PINNED_VERSION}"

CACHE_DIRNAME = ".tl-orc-graft-cache"
CACHE_STAMP_NAME = "tl-orc-cache.json"
CACHE_STAMP_TOOL = "tl-orchestrator/tl_graft"
CACHE_FORMAT_VERSION = 1

INSTALL_TIMEOUT_SECONDS = 300
BUILD_TIMEOUT_SECONDS = 180
QUERY_TIMEOUT_SECONDS = 60
CHECK_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 10
# How long the stream pumps may keep draining after the child itself ended. Reaching it means
# a descendant inherited our pipe and is still holding it open, which is answered by ending
# the whole group instead of returning with the threads still running.
DRAIN_JOIN_SECONDS = 15

OUTPUT_CHAR_LIMIT = 4000
# Hard ceiling for --limit-chars: keeps the promised "short JSON reply" true even when a
# caller passes an oversized or non-positive value, instead of trusting `_truncate`'s
# `limit <= 0` shortcut (which means "no limit") to never receive one.
MAX_LIMIT_CHARS = 20_000
# Hard ceiling on what we ever hold in memory from a subprocess, per stream. Reaching it
# terminates the child: an unbounded `capture_output=True` would buffer a runaway CLI in full
# before any later truncation could help.
CAPTURE_BYTE_LIMIT = 2_000_000
INSTALL_CAPTURE_BYTE_LIMIT = 4_000_000

QUERY_MODES = ("ask", "grep", "skeleton", "callers", "map")

# Directory names never considered as workspace children (mirrors upstream's own skipping
# of tooling dirs closely enough for a refusal check).
_SKIP_CHILD_DIRS = frozenset({"node_modules", "__pycache__", "venv", ".venv", "dist", "build"})

# Environment that must never reach the CLI: provider credentials and any inherited Graft or
# dotenv configuration (which could switch on deep mode, move the context dir, disable the
# refresh we rely on, or re-enable the ignore rewrites we deliberately suppress).
ENV_STRIP_EXACT = (
    "OPENROUTER_API_KEY",
    "ORCAROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "DOTENV_KEY",
    "NODE_OPTIONS",
)
ENV_STRIP_PREFIXES = ("GRAFT_", "DOTENV_CONFIG_")

# Upstream prints these on stderr when it answered from a graph it could not bring up to
# date (`graph/refresh.ts`). Any of them means the answer is not backed by current code.
DEGRADED_REFRESH_MARKERS = (
    "graph refresh skipped",
    "rebuild is already in flight",
    "still copying the graph",
    "no graft/ here",
)


class GraftUnavailable(Exception):
    """Raised when the CLI cannot run at all (missing tool, no cache, bad install)."""


class CacheUnsafe(Exception):
    """Raised when the cache path is redirected, foreign, or otherwise not ours to use."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def _truncate(text: object, limit: int = OUTPUT_CHAR_LIMIT) -> str:
    """Bound a captured stream for the response. Bytes are normalized first: a timeout can
    hand back raw bytes, and concatenating those with a str used to raise TypeError inside
    the very path that exists to produce a graceful fallback."""
    if text is None:
        return ""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8", "replace")
    elif not isinstance(text, str):
        text = str(text)
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncado, {len(text) - limit} caracteres omitidos]"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _same_path(a: Path, b: Path) -> bool:
    """Case-insensitive, symlink-resolved path identity (Windows-safe)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _is_reparse_point(path: Path) -> bool:
    """True for symlinks and for Windows junctions/reparse points.

    `Path.is_symlink()` alone answers False for a junction, which is exactly the redirect an
    attacker (or a careless `mklink /J`) would use to make us install or delete elsewhere.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _assert_not_redirected(path: Path) -> None:
    """Refuse one path whose own entry — or any ancestor — is a symlink/junction.

    `os.path.realpath` resolves the entire chain and works on a path that does not exist yet,
    so this also answers for a file we are about to create: a junction planted on the parent
    directory is caught before the first `mkdir`/`write_text` follows it.
    """
    if _is_reparse_point(path):
        raise CacheUnsafe(
            "cache_path_redirected",
            f"{path} é link/junction; recusando instalar, consultar ou remover através dele.",
        )
    real = os.path.realpath(path)
    if os.path.normcase(real) != os.path.normcase(os.path.abspath(path)):
        raise CacheUnsafe(
            "cache_path_redirected",
            f"{path} aponta para {real}; recusando seguir o redirecionamento.",
        )


def resolve_target_root(target: str | None) -> Path:
    """Resolve the isolated worktree/project root a cache belongs to.

    Prefers the Git worktree root (so distinct worktrees never share a cache), falls back
    to the given/current directory when Git is unavailable or the path is not a repo.
    """
    start = Path(target).resolve() if target else Path.cwd().resolve()
    git = _which("git")
    if git:
        try:
            proc = subprocess.run(
                [git, "-C", str(start), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            proc = None
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    return start


def cache_paths(root: Path) -> dict[str, Path]:
    base = root / CACHE_DIRNAME
    graph = base / "graph"
    home = base / "home"
    return {
        "base": base,
        "cli": base / "cli",
        "graph": graph,
        "home": home,
        # Upstream keeps its update-check record under `<home>/.graft/`. Neither the directory
        # nor the file is created by the install, so both are named here: that is what makes
        # them part of the validated set instead of a pair of paths we write through blindly.
        "update_dir": home / ".graft",
        "update_check": home / ".graft" / "update-check.json",
        "stamp": base / CACHE_STAMP_NAME,
        "gitignore": base / ".gitignore",
        "rgignore": base / ".ignore",
        "no_dotenv": base / "no-dotenv.env",
        "cli_entry": base / "cli" / "node_modules" / "@nanonets" / "graft" / "dist" / "cli.js",
        "installed_marker": base / "cli" / ".installed-version",
        # Upstream's own wiring graph path for a context dir: `<dir>/.graph/wiring.json`.
        "wiring": graph / ".graph" / "wiring.json",
    }


# ---------------------------------------------------------------------------- environment


def _scrubbed_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ENV_STRIP_EXACT and not key.startswith(ENV_STRIP_PREFIXES)
    }
    # Upstream's documented opt-out (TELEMETRY.md): silences the npm postinstall event and
    # every later CLI event.
    env["DO_NOT_TRACK"] = "1"
    return env


def _npm_env() -> dict[str, str]:
    """Install-time environment: scrubbed, but the real HOME is kept so npm still finds its
    own config/cache."""
    return _scrubbed_env()


def _cli_env(paths: dict[str, Path]) -> dict[str, str]:
    """Environment for every `node dist/cli.js` call we make."""
    env = _scrubbed_env()
    # We own the exclusion (`<cache>/.gitignore` + `<cache>/.ignore`), so upstream must not
    # rewrite the consumer's root ignore files — it would cover only `graph/` and re-admit
    # it to ripgrep, leaving `cli/` (the whole npm install) visible to `git status`.
    env["GRAFT_NO_GITIGNORE"] = "1"
    env["GRAFT_NO_IGNORE"] = "1"
    # `dist/cli.js` does `import "dotenv/config"`, which would read the consumer's `.env`
    # from the cwd and could reintroduce GRAFT_API_KEY/OPENROUTER_API_KEY. Point dotenv at a
    # path we never create.
    env["DOTENV_CONFIG_PATH"] = str(paths["no_dotenv"])
    env["DOTENV_CONFIG_QUIET"] = "true"
    # `os.homedir()` decides where `~/.graft` lives (update check, telemetry state). Keep it
    # inside the cache so the user's real home is never written to.
    home = str(paths["home"])
    env["HOME"] = home
    env["USERPROFILE"] = home
    return env


def seed_update_check(paths: dict[str, Path]) -> Path:
    """Write a fresh `<cache-home>/.graft/update-check.json`.

    `maybeRefreshInBackground` (upstream `upkeep.ts`) runs on every non-exempt command and,
    when that record is missing or older than 24h, spawns a detached `graft _update-check`
    that hits the npm registry. DO_NOT_TRACK does not cover it. Seeding a current record is
    what makes "no network after install" true rather than aspirational.

    This record is written before the CLI ever starts, through `home/.graft/` — a directory no
    install creates. So the whole destination chain is validated here too: `mkdir` succeeds
    happily on an existing junction and `write_text` would then overwrite a file outside the
    cache. Checked before creating the directory and again after, and raised as `CacheUnsafe`
    so the caller falls back without having run anything.
    """
    target = paths["update_check"]
    for path in (paths["home"], paths["update_dir"], target):
        _assert_not_redirected(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    for path in (paths["update_dir"], target):
        _assert_not_redirected(path)
    payload = {"latest": None, "checkedAt": int(time.time() * 1000)}
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------- subprocess


class RunResult:
    """Outcome of one subprocess: exit code, bounded streams, and how it ended."""

    __slots__ = ("code", "stdout", "stderr", "status")

    def __init__(self, code: int | None, stdout: str, stderr: str, status: str) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.status = status  # ok | timeout | limit | spawn_error

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.code == 0


_POSIX_PROCESS_GROUPS = os.name != "nt" and hasattr(os, "killpg") and hasattr(os, "setsid")


def _spawn_kwargs() -> dict:
    """Put the child in a session of its own on POSIX (same idiom as `tl_job.spawn_kwargs`).

    Without it there is no handle on the tree: `proc.kill()` reaches the leader only, and npm,
    node and a native compiler all leave descendants behind that would keep writing into the
    cache and keep our pipes open after a timeout.
    """
    return {"start_new_session": True} if _POSIX_PROCESS_GROUPS else {}


def _kill_process_tree(proc: subprocess.Popen, pgid: int | None = None) -> None:
    """Terminate the child and whatever it started (npm spawns node; node spawns more).

    With a process group the signal goes to the group and is sent *even when the leader has
    already exited* — exactly the case where a surviving descendant keeps the inherited pipe
    open. On Windows `taskkill /F /T` walks the tree down from a live parent; a descendant
    orphaned by an already-dead leader is outside its reach, and outside what this helper
    claims to end.
    """
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:  # already gone, or not ours to signal
            pass
    elif os.name == "nt" and proc.poll() is None:
        taskkill = shutil.which("taskkill")
        if taskkill:
            try:
                subprocess.run(
                    [taskkill, "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=15,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _run(
    cmd: list[str],
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
    byte_limit: int = CAPTURE_BYTE_LIMIT,
) -> RunResult:
    """Run a command as an argv list (never a shell string) so spaces in paths are safe.

    Both streams are drained concurrently (a full pipe would otherwise deadlock the child)
    into buffers capped at `byte_limit`; exceeding the cap or the deadline kills the process
    tree and reports it, instead of buffering an unbounded amount and truncating afterwards.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **_spawn_kwargs(),
        )
    except (OSError, ValueError) as exc:
        return RunResult(None, "", str(exc), "spawn_error")

    pgid: int | None = None
    if _POSIX_PROCESS_GROUPS:
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = None
        if pgid is not None and (pgid != proc.pid or pgid == os.getpgrp()):
            # The child did not become the leader of its own group; signalling that group
            # could reach this very process, so fall back to the single pid.
            pgid = None

    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    buffer_lock = threading.Lock()
    over_limit = threading.Event()

    def pump(stream, key: str) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                with buffer_lock:
                    buf = buffers[key]
                    room = byte_limit - len(buf)
                    if room > 0:
                        buf.extend(chunk[:room])
                    reached = len(buf) >= byte_limit
                if reached and not over_limit.is_set():
                    over_limit.set()
                    _kill_process_tree(proc, pgid)
                    # keep reading so the child is never blocked on a full pipe
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    threads = [
        threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc, pgid)
    for thread in threads:
        thread.join(timeout=DRAIN_JOIN_SECONDS)
    if any(thread.is_alive() for thread in threads):
        # The child ended but its pipes did not close: a descendant inherited them. Ending the
        # group closes them, which is what lets the pumps finish before we read their buffers.
        _kill_process_tree(proc, pgid)
        for thread in threads:
            thread.join(timeout=DRAIN_JOIN_SECONDS)

    with buffer_lock:
        out = bytes(buffers["stdout"]).decode("utf-8", "replace")
        err = bytes(buffers["stderr"]).decode("utf-8", "replace")
    if timed_out:
        return RunResult(None, out, err, "timeout")
    if over_limit.is_set():
        return RunResult(proc.returncode, out, err, "limit")
    return RunResult(proc.returncode, out, err, "ok")


def node_available() -> tuple[str | None, str | None]:
    return _which("node"), _which("npm")


# ---------------------------------------------------------------------------- cache guards


def multi_repo_children(root: Path) -> list[str]:
    """Immediate Git-repo children of a root that is not itself a repo.

    Graft treats that layout as a *workspace* and builds into `<child>/graft` in every child,
    dropping our `--dir` isolation entirely. That is out of scope for this integration, so it
    is refused rather than attempted.
    """
    try:
        if (root / ".git").exists():
            return []
        entries = sorted(os.scandir(root), key=lambda entry: entry.name)
    except OSError:
        return []
    children: list[str] = []
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        name = entry.name
        if name.startswith(".") or name in _SKIP_CHILD_DIRS:
            continue
        try:
            if (Path(entry.path) / ".git").exists():
                children.append(name)
        except OSError:
            continue
    return children if len(children) >= 2 else []


# Every path this module ever opens for read/write/delete, split by expected type. A cache
# that was sealed honestly on a prior run can later have any one of these individually replaced
# with a symlink/junction (not just the top-level cli/graph/home dirs), so all of them — the
# ignore files, the version marker, the wiring report — are checked, not only the directories.
_CACHE_DIR_KEYS = ("base", "cli", "graph", "home", "update_dir")
_CACHE_FILE_KEYS = (
    "cli_entry",
    "stamp",
    "gitignore",
    "rgignore",
    "no_dotenv",
    "installed_marker",
    "wiring",
    "update_check",
)


def assert_safe_cache(root: Path, paths: dict[str, Path]) -> None:
    """Refuse to read, write, or delete anything through a redirected cache path.

    Checked for every path in `_CACHE_DIR_KEYS`/`_CACHE_FILE_KEYS`, not just the cache root: a
    cache sealed on a prior run can have an individual member (`.gitignore`, the version marker,
    `cli/node_modules`, the wiring report) replaced with a symlink or Windows junction later.
    `os.path.realpath` resolves the whole ancestor chain, so redirecting any ancestor directory
    is caught here even when the leaf itself is not a reparse point.
    """
    base = paths["base"]
    if not _same_path(base.parent, root) or base.name != CACHE_DIRNAME:
        raise CacheUnsafe(
            "cache_path_unexpected",
            f"caminho de cache inesperado, recusando usar: {base}",
        )
    for key in _CACHE_DIR_KEYS + _CACHE_FILE_KEYS:
        path = paths[key]
        _assert_not_redirected(path)
        if not path.exists():
            continue
        if key in _CACHE_DIR_KEYS and not path.is_dir():
            raise CacheUnsafe(
                "cache_path_unexpected",
                f"{path} existe e não é diretório; recusando usar o cache.",
            )
        if key in _CACHE_FILE_KEYS and path.is_dir():
            raise CacheUnsafe(
                "cache_path_unexpected",
                f"{path} existe e é diretório; recusando usar o cache.",
            )


def assert_no_dotenv_file(paths: dict[str, Path]) -> None:
    """Refuse to start the CLI while `<cache>/no-dotenv.env` exists.

    `dist/cli.js` does `import "dotenv/config"`, and `DOTENV_CONFIG_PATH` points at this path
    precisely because nothing ever creates it: dotenv finds no file, so the scrubbed
    environment stays scrubbed. If the file is there — left by a user, by another tool, or on
    purpose — every key and every `GRAFT_*` setting in it would be loaded back into the process
    we just cleaned, deep mode included. It is neither read nor deleted here: we name it,
    refuse, and let the caller fall back.
    """
    path = paths["no_dotenv"]
    if path.exists() or _is_reparse_point(path):
        raise CacheUnsafe(
            "dotenv_file_present",
            f"{path} existe e o Graft carregaria variáveis dele; recusando iniciar o CLI. Nada "
            "foi lido nem alterado — apague ou renomeie esse arquivo para usar o acelerador.",
        )


def _scan_for_internal_reparse_points(base: Path, limit: int = 5) -> list[Path]:
    """Find the links under `base` that removing the cache could follow outside it.

    `os.walk(followlinks=False)` is not enough on Windows: it recognizes real symlinks but not
    junctions, which `os.path.islink` reports as plain directories. `_is_reparse_point` checks
    the reparse-point attribute directly, so a junction planted inside an already-sealed cache
    (e.g. a redirected `cli/node_modules`) is found here even though it is neither the cache
    root nor one of the named paths in `cache_paths`.

    Not every link inside the cache is a redirect, though. A normal npm install on POSIX links
    `cli/node_modules/.bin/<tool>` into the package it just unpacked, so refusing every link
    would refuse every honest Linux/macOS install. A plain symlink whose target stays inside
    the cache is therefore left for the removal to unlink — `shutil.rmtree` deletes such an
    entry instead of descending through it, so its destination is never traversed. Everything
    else is reported: a link that leaves the cache, and any non-symlink reparse point (a
    Windows junction, which `rmtree` *does* walk into).
    """
    found: list[Path] = []
    base_real = os.path.normcase(os.path.realpath(base))

    def _stays_inside(path: Path) -> bool:
        try:
            real = os.path.normcase(os.path.realpath(path))
        except OSError:
            return False
        return real == base_real or real.startswith(base_real + os.sep)

    def _walk(path: Path) -> None:
        if len(found) >= limit:
            return
        try:
            entries = list(os.scandir(path))
        except OSError:
            return
        for entry in entries:
            if len(found) >= limit:
                return
            child = Path(entry.path)
            if _is_reparse_point(child):
                # `Path.is_symlink()` answers False for a junction — exactly the distinction
                # that matters here, since only a plain symlink is deleted without being read.
                if not (child.is_symlink() and _stays_inside(child)):
                    found.append(child)
                continue
            if entry.is_dir(follow_symlinks=False):
                _walk(child)

    _walk(base)
    return found


def cache_ownership(paths: dict[str, Path]) -> str:
    """`ours` (our stamp is present), `empty` (nothing there), or `foreign`."""
    base = paths["base"]
    stamp = paths["stamp"]
    try:
        if not base.exists():
            return "empty"
        if stamp.is_file():
            data = json.loads(stamp.read_text(encoding="utf-8"))
            return "ours" if data.get("tool") == CACHE_STAMP_TOOL else "foreign"
        return "empty" if not any(base.iterdir()) else "foreign"
    except (OSError, ValueError, UnicodeDecodeError):
        return "foreign"


_IGNORE_EVERYTHING_HEADER = (
    "# Cache local do acelerador de contexto Graft (tl-orchestrator).\n"
    "# Regenerável e nunca versionado: ignora a instalação do CLI, o mapa e este arquivo.\n"
)


def _ensure_ignore_file(path: Path) -> bool:
    """Idempotently make sure `path` excludes everything under its directory.

    Returns True when the file was written. Any pre-existing content is preserved: we append
    our rule instead of replacing a file someone else may own.
    """
    current = ""
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
        if any(line.strip() == "*" for line in current.splitlines()):
            return False
    gap = "" if current == "" or current.endswith("\n") else "\n"
    path.write_text(current + gap + _IGNORE_EVERYTHING_HEADER + "*\n", encoding="utf-8")
    return True


def ensure_cache_excluded(paths: dict[str, Path]) -> dict:
    """Create the cache dir and make it invisible to Git and to ripgrep *before* installing.

    Both files matter: `.gitignore` keeps `git status`/`git add -A` clean in the consumer, and
    `.ignore` (read by ripgrep at higher precedence) keeps the vendored `node_modules` and the
    generated map out of the very `rg` searches that are our fallback.
    """
    base = paths["base"]
    base.mkdir(parents=True, exist_ok=True)
    wrote_git = _ensure_ignore_file(paths["gitignore"])
    wrote_rg = _ensure_ignore_file(paths["rgignore"])
    paths["home"].mkdir(parents=True, exist_ok=True)
    stamp = paths["stamp"]
    if not stamp.is_file():
        stamp.write_text(
            json.dumps(
                {
                    "tool": CACHE_STAMP_TOOL,
                    "cache_format": CACHE_FORMAT_VERSION,
                    "pinned": PINNED_SPEC,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return {"gitignore_written": wrote_git, "ignore_written": wrote_rg}


def is_installed(paths: dict[str, Path]) -> bool:
    try:
        if not paths["cli_entry"].is_file():
            return False
        marker = paths["installed_marker"]
        if not marker.is_file():
            return False
        return marker.read_text(encoding="utf-8", errors="replace").strip() == PINNED_VERSION
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------- results


def _fallback(reason: str, message: str, root: Path, **extra) -> dict:
    result = {
        "ok": False,
        "reason": reason,
        "message": message,
        "fallback": "rg",
        "target": str(root),
    }
    result.update(extra)
    return result


def _guard(target: str | None, for_cli: bool = True) -> tuple[Path, dict[str, Path], dict | None]:
    """Resolve the root and refuse layouts/paths we must not run against.

    `for_cli=False` is for `disable`, which never starts the CLI: the checks that exist to keep
    that subprocess clean must not stand between the user and removing the cache.
    """
    root = resolve_target_root(target)
    paths = cache_paths(root)
    children = multi_repo_children(root)
    if children:
        return root, paths, _fallback(
            "workspace_layout_unsupported",
            "Esta pasta não é um repositório Git e contém vários repositórios "
            f"({', '.join(children[:5])}). O Graft trataria isso como workspace e escreveria "
            "dentro de cada repositório; esta integração recusa esse modo. Nada foi alterado — "
            "ative o acelerador dentro de um repositório específico, ou siga com rg/leitura direta.",
            root,
            children=children,
        )
    try:
        assert_safe_cache(root, paths)
        if for_cli:
            assert_no_dotenv_file(paths)
    except CacheUnsafe as exc:
        return root, paths, _fallback(exc.reason, exc.message, root)
    return root, paths, None


# ---------------------------------------------------------------------------- commands


def do_setup(target: str | None, force: bool) -> dict:
    root, paths, refusal = _guard(target)
    if refusal is not None:
        return refusal

    node, npm = node_available()
    if not node or not npm:
        return _fallback(
            "node_or_npm_missing",
            "Node.js/npm não encontrados; economia de contexto por Graft indisponível. "
            "Use leitura direta/rg normalmente — nada foi bloqueado.",
            root,
        )

    ownership = cache_ownership(paths)
    if ownership == "foreign":
        return _fallback(
            "foreign_cache_dir",
            f"Já existe um diretório {CACHE_DIRNAME}/ que não foi criado por este helper; "
            "nada foi alterado nem removido. Renomeie ou apague esse diretório manualmente "
            "se quiser ativar o acelerador aqui.",
            root,
        )

    # Exclusion first, and kept even if everything below fails: a half-finished install must
    # never show up in `git status` or in an `rg` fallback.
    try:
        exclusion = ensure_cache_excluded(paths)
        seed_update_check(paths)
    except CacheUnsafe as exc:
        return _fallback(exc.reason, exc.message, root)
    except OSError as exc:
        return _fallback(
            "cache_unwritable",
            f"Não foi possível preparar o cache local ({exc.strerror or exc}); "
            "siga sem o acelerador.",
            root,
        )

    installed_before = is_installed(paths)
    if installed_before and not force:
        install_result = {"skipped": True, "reason": "already_installed_pinned_version"}
    else:
        try:
            paths["cli"].mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _fallback(
                "cache_unwritable",
                f"Não foi possível criar o cache do CLI ({exc.strerror or exc}); "
                "siga sem o acelerador.",
                root,
            )
        run = _run(
            [
                npm,
                "install",
                "--prefix",
                str(paths["cli"]),
                "--no-save",
                "--no-audit",
                "--no-fund",
                PINNED_SPEC,
            ],
            cwd=paths["cli"],
            timeout=INSTALL_TIMEOUT_SECONDS,
            env=_npm_env(),
            byte_limit=INSTALL_CAPTURE_BYTE_LIMIT,
        )
        if run.status == "timeout":
            return _fallback(
                "install_timeout",
                "Instalação do Graft excedeu o tempo limite; siga sem o acelerador.",
                root,
                exclusion=exclusion,
            )
        if run.status != "ok" or run.code != 0 or not paths["cli_entry"].is_file():
            return _fallback(
                "install_failed",
                "Não foi possível instalar o Graft (versão pinada); siga sem o acelerador.",
                root,
                exclusion=exclusion,
                diagnostics={
                    "exit_code": run.code,
                    "status": run.status,
                    "stderr": _truncate(run.stderr),
                    "stdout": _truncate(run.stdout),
                },
            )
        try:
            paths["installed_marker"].write_text(PINNED_VERSION, encoding="utf-8")
        except OSError as exc:
            return _fallback(
                "cache_unwritable",
                f"Instalação concluída, mas não foi possível registrar a versão ({exc.strerror or exc}); "
                "siga sem o acelerador.",
                root,
            )
        install_result = {"skipped": False, "exit_code": run.code}

    build = _run(
        [node, str(paths["cli_entry"]), "--dir", str(paths["graph"]), "build", str(root)],
        cwd=root,
        timeout=BUILD_TIMEOUT_SECONDS,
        env=_cli_env(paths),
    )
    if build.status == "timeout":
        return _fallback(
            "build_timeout",
            "Instalação concluída, mas gerar o mapa excedeu o tempo limite; tente novamente depois.",
            root,
            install=install_result,
        )
    if build.status != "ok" or build.code != 0:
        return _fallback(
            "build_failed",
            "Graft instalado, mas a geração do mapa falhou; siga sem o acelerador.",
            root,
            install=install_result,
            diagnostics={
                "exit_code": build.code,
                "status": build.status,
                "stderr": _truncate(build.stderr),
                "stdout": _truncate(build.stdout),
            },
        )
    if not paths["wiring"].is_file():
        return _fallback(
            "graph_missing_after_build",
            "O Graft terminou sem erro, mas nenhum mapa foi encontrado; siga sem o acelerador.",
            root,
            install=install_result,
        )
    return {
        "ok": True,
        "message": "Economia de contexto ativada: mapa estrutural do código gerado localmente "
        "(sem IA, sem chave). O cache fica ignorado por Git e por buscas.",
        "target": str(root),
        "cache": str(paths["base"]),
        "version": PINNED_VERSION,
        "install": install_result,
        "exclusion": exclusion,
        "build": {"exit_code": build.code, "stdout": _truncate(build.stdout, 800)},
    }


def _run_check(paths: dict[str, Path], root: Path) -> tuple[RunResult, dict | None]:
    """`graft check --json` (never refreshes — it is the drift report) plus its parsed body."""
    run = _run(
        [
            _which("node") or "node",
            str(paths["cli_entry"]),
            "--dir",
            str(paths["graph"]),
            "check",
            str(root),
            "--json",
        ],
        cwd=root,
        timeout=CHECK_TIMEOUT_SECONDS,
        env=_cli_env(paths),
    )
    payload = None
    if run.status == "ok" and run.stdout.strip():
        try:
            parsed = json.loads(run.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except ValueError:
            payload = None
    return run, payload


def _graph_state(payload: dict | None) -> tuple[str, dict]:
    """Classify `check --json`.

    `graph` is the structural (tree-sitter) layer we build; `context` is the `--deep` markdown
    layer we never build, so its absence is expected and is not drift.
    """
    if payload is None:
        return "unreadable", {}
    graph = payload.get("graph")
    if graph is None:
        return "missing", {}
    if not isinstance(graph, dict):
        return "unreadable", {}
    if graph.get("missing"):
        return "missing", {}
    detail = {
        "nodes": graph.get("nodes"),
        "added": len(graph.get("added") or []),
        "removed": len(graph.get("removed") or []),
        "changed": len(graph.get("changed") or []),
    }
    structural_drift = detail["added"] or detail["removed"] or detail["changed"]
    if structural_drift:
        return "stale", detail
    return "fresh", detail


def do_status(target: str | None) -> dict:
    root, paths, refusal = _guard(target)
    if refusal is not None:
        refusal["configured"] = False
        return refusal

    node, npm = node_available()
    if not node or not npm:
        result = _fallback(
            "node_or_npm_missing",
            "Economia de contexto por Graft não disponível (falta Node.js/npm). Nada bloqueado.",
            root,
        )
        result["configured"] = False
        return result
    if not is_installed(paths):
        result = _fallback(
            "not_configured",
            "Graft ainda não foi ativado neste diretório. Rode o setup para ativar.",
            root,
        )
        result["configured"] = False
        return result
    if not paths["wiring"].is_file():
        result = _fallback(
            "graph_missing",
            "Graft instalado, mas o mapa ainda não foi gerado. Rode o setup novamente.",
            root,
        )
        result["configured"] = True
        return result

    try:
        seed_update_check(paths)
    except CacheUnsafe as exc:
        result = _fallback(exc.reason, exc.message, root)
        result["configured"] = True
        return result
    except OSError as exc:
        result = _fallback(
            "update_check_seed_failed",
            f"Não foi possível preparar o registro local de atualização ({exc.strerror or exc}); "
            "recusando rodar o Graft para não arriscar uma checagem de rede não intencional.",
            root,
        )
        result["configured"] = True
        return result
    run, payload = _run_check(paths, root)
    if run.status == "timeout":
        result = _fallback(
            "check_timeout",
            "Verificação de atualidade do mapa excedeu o tempo limite; trate como possivelmente desatualizado.",
            root,
        )
        result["configured"] = True
        return result
    if run.status != "ok" or run.code is None or run.code not in (0, 1):
        result = _fallback(
            "check_failed",
            "Não foi possível verificar o mapa; trate como possivelmente desatualizado.",
            root,
            diagnostics={"exit_code": run.code, "status": run.status, "stderr": _truncate(run.stderr, 600)},
        )
        result["configured"] = True
        return result

    state, detail = _graph_state(payload)
    if state == "unreadable":
        result = _fallback(
            "check_unreadable",
            "A verificação do mapa não retornou um relatório legível; trate como possivelmente desatualizado.",
            root,
        )
        result["configured"] = True
        return result
    if state == "missing":
        result = _fallback(
            "graph_missing",
            "Graft instalado, mas o mapa ainda não foi gerado. Rode o setup novamente.",
            root,
        )
        result["configured"] = True
        return result

    stale = state == "stale"
    return {
        "ok": True,
        "configured": True,
        "stale": stale,
        "message": "Mapa desatualizado em relação ao código: a próxima consulta o atualiza "
        "automaticamente antes de responder, e só entrega resposta se a atualização der certo. "
        "Para atualizar agora, rode o setup de novo."
        if stale
        else "Mapa em dia com o código.",
        "target": str(root),
        "cache": str(paths["base"]),
        "version": PINNED_VERSION,
        "graph": detail,
    }


def _degraded_refresh(stderr: str) -> str | None:
    lowered = stderr.lower()
    for marker in DEGRADED_REFRESH_MARKERS:
        if marker in lowered:
            return marker
    return None


def _payload_is_empty(mode: str, payload: object) -> bool:
    """True when the CLI answered successfully but found nothing (never "code absent")."""
    if not isinstance(payload, dict):
        return True
    if mode == "ask":
        return not payload.get("hits")
    if mode == "grep":
        return not payload.get("groups") or not payload.get("totalHits")
    if mode == "skeleton":
        return not payload.get("entries")
    if mode == "callers":
        matches = payload.get("matches") or []
        return not any(match.get("hits") for match in matches if isinstance(match, dict))
    if mode == "map":
        totals = payload.get("totals") or {}
        if isinstance(totals, dict) and (totals.get("files") or totals.get("symbols")):
            return False
        return not payload.get("dirs") and not payload.get("hotspots")
    return False


def do_query(target: str | None, mode: str, arg: str, limit_chars: int) -> dict:
    if mode not in QUERY_MODES:
        raise ValueError(f"modo de consulta desconhecido: {mode}")

    root, paths, refusal = _guard(target)
    if refusal is not None:
        return refusal

    node, npm = node_available()
    if not node or not npm:
        return _fallback(
            "node_or_npm_missing",
            "Graft indisponível; use rg/leitura direta para esta consulta.",
            root,
        )
    if not is_installed(paths) or not paths["wiring"].is_file():
        return _fallback(
            "not_configured",
            "Graft não ativado aqui; use rg/leitura direta ou rode o setup primeiro.",
            root,
        )
    if mode != "map" and not arg:
        result = _fallback(
            "missing_argument",
            f"--arg é obrigatório para --mode {mode}.",
            root,
        )
        result.pop("fallback", None)
        return result
    if not (1 <= limit_chars <= MAX_LIMIT_CHARS):
        result = _fallback(
            "invalid_limit_chars",
            f"--limit-chars deve ser um inteiro entre 1 e {MAX_LIMIT_CHARS}.",
            root,
        )
        result.pop("fallback", None)
        return result

    try:
        seed_update_check(paths)
    except CacheUnsafe as exc:
        return _fallback(exc.reason, exc.message, root, mode=mode, query=arg)
    except OSError as exc:
        return _fallback(
            "update_check_seed_failed",
            f"Não foi possível preparar o registro local de atualização ({exc.strerror or exc}); "
            "recusando rodar o Graft para não arriscar uma checagem de rede não intencional.",
            root,
            mode=mode,
            query=arg,
        )

    base_cmd = [node, str(paths["cli_entry"]), "--dir", str(paths["graph"])]
    if mode == "map":
        # `graft map [dir]` takes no query argument; --arg is ignored for this mode.
        cmd = base_cmd + ["map", str(root), "--json"]
    else:
        cmd = base_cmd + [mode, arg, str(root), "--json"]

    run = _run(cmd, cwd=root, timeout=QUERY_TIMEOUT_SECONDS, env=_cli_env(paths))
    if run.status == "timeout":
        return _fallback(
            "query_timeout",
            "Consulta ao Graft excedeu o tempo limite; não significa ausência de código — "
            "use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )
    if run.status == "limit":
        return _fallback(
            "output_limit",
            "A consulta produziu saída grande demais e foi interrompida; não significa ausência "
            "de código — use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )
    if run.status != "ok" or run.code != 0:
        return _fallback(
            "query_error",
            "Consulta ao Graft falhou; não significa ausência de código — use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
            diagnostics={
                "exit_code": run.code,
                "status": run.status,
                "stderr": _truncate(run.stderr, 600),
            },
        )

    degraded = _degraded_refresh(run.stderr)
    if degraded:
        return _fallback(
            "refresh_degraded",
            "O Graft respondeu a partir de um mapa que não conseguiu atualizar; a resposta não é "
            "confiável — use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
            diagnostics={"note": _truncate(run.stderr, 400)},
        )

    if not run.stdout.strip():
        return _fallback(
            "empty_output",
            "O Graft não retornou resposta; não significa ausência de código — use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )
    try:
        payload = json.loads(run.stdout)
    except ValueError:
        return _fallback(
            "invalid_output",
            "A resposta do Graft não é JSON válido; não significa ausência de código — "
            "use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )
    if _payload_is_empty(mode, payload):
        return _fallback(
            "no_results",
            "O Graft não encontrou nada para esta consulta; isso não significa ausência de código — "
            "confirme com rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )

    # The query auto-refreshes before answering, so verify *afterwards* that the graph it
    # answered from matches the code on disk. Anything short of a clean, readable report is
    # reported as unverified rather than as a result.
    check_run, check_payload = _run_check(paths, root)
    if check_run.status != "ok" or check_run.code not in (0, 1):
        return _fallback(
            "freshness_unverified",
            "Não foi possível confirmar que o mapa está em dia com o código; trate a resposta como "
            "não verificada e use rg/leitura direta.",
            root,
            mode=mode,
            query=arg,
        )
    state, detail = _graph_state(check_payload)
    if state != "fresh":
        return _fallback(
            "stale_graph" if state == "stale" else "freshness_unverified",
            "O mapa não está em dia com o código; a resposta não é confiável — use rg/leitura direta "
            "e rode o setup para regerar.",
            root,
            mode=mode,
            query=arg,
            graph=detail,
        )

    return {
        "ok": True,
        "mode": mode,
        "query": arg,
        "target": str(root),
        "verified": {"graph": "fresh", **detail},
        "result": _truncate(run.stdout, limit_chars),
    }


# Our two ignore files and the ownership stamp are written before the install and deleted
# last. While any cache content survives a partial removal they keep the leftovers invisible
# to Git and to `rg`, and keep the directory provably ours — so a second `disable` finishes
# the job instead of refusing a now-unstamped directory as somebody else's.
_DISABLE_KEEP_LAST = ("gitignore", "rgignore", "stamp")


def _rmtree_collecting(path: Path, failures: list[str]) -> None:
    """`shutil.rmtree` that records what it could not delete instead of raising."""
    try:
        shutil.rmtree(path, onexc=lambda func, target, exc: failures.append(str(target)))
    except TypeError:  # pragma: no cover - Python < 3.12 uses onerror
        shutil.rmtree(path, onerror=lambda func, target, exc: failures.append(str(target)))
    except OSError as exc:
        failures.append(str(exc))


def _remove_cache_contents(base: Path, keep: set[str], failures: list[str]) -> list[str]:
    """Delete everything directly under `base` except `keep`; answer with what is still there."""
    try:
        entries = list(os.scandir(base))
    except OSError as exc:
        failures.append(str(exc))
        return [base.name]
    for entry in entries:
        if entry.name in keep:
            continue
        child = Path(entry.path)
        if entry.is_dir(follow_symlinks=False) and not _is_reparse_point(child):
            _rmtree_collecting(child, failures)
            continue
        try:
            child.unlink()
        except OSError as exc:
            try:  # a link to a directory is removed as a link, never descended into
                child.rmdir()
            except OSError:
                failures.append(str(exc))
    try:
        return sorted(entry.name for entry in os.scandir(base) if entry.name not in keep)
    except OSError as exc:
        failures.append(str(exc))
        return []


def _disable_incomplete(root: Path, base: Path, failures: list[str], kept: list[str]) -> dict:
    return {
        "ok": False,
        "reason": "disable_incomplete",
        "message": "Parte do cache não pôde ser removida (algum arquivo está em uso ou sem "
        "permissão). O que sobrou continua ignorado por Git e por buscas, e continua marcado "
        "como deste helper: feche o programa que esteja usando o cache e rode a desativação de "
        "novo para concluir.",
        "target": str(root),
        "remaining": str(base),
        "failures": failures[:10],
        "preserved": kept,
    }


def do_disable(target: str | None) -> dict:
    root, paths, refusal = _guard(target, for_cli=False)
    if refusal is not None:
        return refusal

    base = paths["base"]
    if not base.exists():
        return {
            "ok": True,
            "message": "Graft já estava desativado (nada a remover).",
            "target": str(root),
        }
    ownership = cache_ownership(paths)
    # `empty` is accepted as well: an earlier removal that got as far as deleting the stamp and
    # then failed to remove the directory itself must not leave a cache nobody may finish.
    if ownership not in ("ours", "empty"):
        raise GraftUnavailable(
            f"{base} não tem a marca deste helper; recusando remover um diretório que não criamos."
        )

    internal_links = _scan_for_internal_reparse_points(base)
    if internal_links:
        raise GraftUnavailable(
            f"{base} contém um link/junction interno ({internal_links[0]}); recusando remover para "
            "não seguir um redirecionamento e apagar algo fora do cache. Nada foi apagado."
        )

    kept = sorted(paths[key].name for key in _DISABLE_KEEP_LAST)
    failures: list[str] = []
    remaining = _remove_cache_contents(base, set(kept), failures)
    if failures or remaining:
        # Something is still there (a locked binary, typically). The ignore files and the stamp
        # stay exactly as they are: they are what keeps the leftovers out of `git status` and
        # out of `rg`, and what lets the next attempt recognize the directory as ours.
        return _disable_incomplete(root, base, failures, kept)

    # Only our own files are left. Remove them in order, stamp last, so an interruption still
    # leaves a directory the next run can finish removing.
    for key in _DISABLE_KEEP_LAST:
        path = paths[key]
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError as exc:
            failures.append(str(exc))
            break
    if not failures:
        try:
            base.rmdir()
        except OSError as exc:
            failures.append(str(exc))
    if failures or base.exists():
        return _disable_incomplete(root, base, failures, kept)
    return {
        "ok": True,
        "message": "Graft desativado: cache e mapa locais removidos. Código e configurações do "
        "projeto preservados.",
        "target": str(root),
    }


# ---------------------------------------------------------------------------- CLI


def _print_result(result: dict, as_json: bool) -> None:
    """Print the response as UTF-8 regardless of the console/redirect encoding.

    On Windows a redirected stdout defaults to the legacy code page, which would mangle (or
    raise on) accented messages and non-ASCII paths.
    """
    stream = sys.stdout
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, OSError, ValueError):  # pragma: no cover - exotic stdout
        pass
    if as_json:
        text = json.dumps(result, ensure_ascii=False)
    else:
        text = result.get("message", json.dumps(result, ensure_ascii=False))
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover - stdout we could not reconfigure
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            raise
        buffer.write(text.encode("utf-8", "replace") + b"\n")
        buffer.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tl_graft.py",
        description="Ativa/consulta o acelerador de contexto Graft (opcional, local, sem bloquear a tarefa).",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Raiz do projeto/worktree (padrão: cwd resolvido via git). Passe sempre a raiz do "
        "consumidor quando rodar este script de dentro do pacote instalado.",
    )
    parser.add_argument("--json", action="store_true", help="Saída JSON compacta para automação")
    sub = parser.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup", help="Instala versão pinada e gera o mapa estrutural (sem IA)")
    setup_p.add_argument("--force", action="store_true", help="Reinstala mesmo se a versão pinada já estiver presente")

    sub.add_parser("status", help="Mostra se o Graft está ativo e se o mapa está atualizado")

    query_p = sub.add_parser("query", help="Consulta o mapa (ask/grep/skeleton/callers/map)")
    query_p.add_argument("--mode", choices=QUERY_MODES, required=True)
    query_p.add_argument(
        "--arg",
        default="",
        help="Texto da pergunta, regex, arquivo ou símbolo, conforme o modo (ignorado para --mode map)",
    )
    query_p.add_argument(
        "--limit-chars",
        type=int,
        default=OUTPUT_CHAR_LIMIT,
        help=f"Tamanho máximo da resposta, entre 1 e {MAX_LIMIT_CHARS} caracteres",
    )

    sub.add_parser("disable", help="Remove cache e mapa locais; não apaga código nem config alheia")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            result = do_setup(args.target, args.force)
        elif args.command == "status":
            result = do_status(args.target)
        elif args.command == "query":
            result = do_query(args.target, args.mode, args.arg, args.limit_chars)
        elif args.command == "disable":
            result = do_disable(args.target)
        else:  # pragma: no cover - argparse enforces choices
            raise ValueError(f"comando desconhecido: {args.command}")
    except GraftUnavailable as exc:
        _print_result({"ok": False, "reason": "refused", "message": str(exc)}, args.json)
        return 1
    except OSError as exc:
        _print_result(
            {
                "ok": False,
                "reason": "filesystem_error",
                "message": f"Falha de sistema de arquivos ao falar com o Graft ({exc.strerror or exc}); "
                "siga sem o acelerador.",
                "fallback": "rg",
            },
            args.json,
        )
        return 1
    _print_result(result, args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
