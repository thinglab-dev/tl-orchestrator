#!/usr/bin/env python3
"""Execution Plan Validator and first-class Protected Paths (T033).

An execution plan is the machine-checkable part of a proposal: which gates run, in which
lifecycle phase, and which assertions each gate evaluates. Assertions are not free strings.
They are identifiers in a closed registry that also declares, per assertion, the lifecycle
phases in which evaluating it is meaningful. An assertion nobody registered, or one placed
in a phase where its answer is not yet decidable, is refused; the validator never guesses.

Protected paths are first class here for the same reason: `read_only`, `exact_file_hash`
and `exact_set_snapshot` are verified against the tree, and their policy can only ever be
inherited or tightened, never relaxed.

Everything in this module is the Python standard library. Schema validation is performed by
a strict Draft 2020-12 subset validator that refuses any keyword it does not implement, so
a schema can never rely on semantics this validator silently skips.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- canonical form

# canonical_json_v1: UTF-8, object keys sorted lexicographically, compact deterministic
# separators, no incidental whitespace, array order preserved. No float is admitted: a
# digest that depends on a binary floating point representation is not a digest.


def canonical_json(payload: Any) -> str:
    _reject_floats(payload, "$")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reject_floats(value: Any, path: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"{path}: float values are not admitted in canonical JSON")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: object keys must be strings, got {type(key).__name__}")
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def sha256_hex(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def digest_of(payload: Any) -> str:
    return sha256_hex(canonical_json(payload))


# --------------------------------------------------------------------------- schema subset

# Every keyword this validator implements. A schema carrying anything else is refused rather
# than validated with the unknown keyword ignored, which is how partial validators quietly
# stop enforcing the constraint an author believed they had written.
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "$comment", "title", "description", "default", "examples",
    "deprecated", "readOnly", "writeOnly", "format",
    "type", "enum", "const",
    "required", "properties", "additionalProperties", "patternProperties", "propertyNames",
    "minProperties", "maxProperties", "dependentRequired",
    "items", "prefixItems", "minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains",
    "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
})
# Annotation-only in Draft 2020-12: recorded, never asserted. Listed so the intent is explicit.
ANNOTATION_KEYWORDS = frozenset({
    "$schema", "$id", "$comment", "title", "description", "default", "examples",
    "deprecated", "readOnly", "writeOnly", "format", "$defs",
})


class SchemaError(ValueError):
    """The schema itself is unusable; validating against it would prove nothing."""


def _resolve_ref(node: Any, root: dict, seen: tuple = ()) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise SchemaError(f"unsupported $ref {ref!r}: only local JSON pointers are implemented")
        if ref in seen:
            raise SchemaError(f"cyclic $ref chain through {ref!r}")
        seen = seen + (ref,)
        target: Any = root
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or token not in target:
                raise SchemaError(f"unresolvable $ref {ref!r}")
            target = target[token]
        node = target
    if isinstance(node, bool):
        return {} if node else {"not": {}}
    if not isinstance(node, dict):
        raise SchemaError(f"schema node must be an object or boolean, got {type(node).__name__}")
    return node


def _type_matches(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise SchemaError(f"unknown type name {name!r}")


def _equal(left: Any, right: Any) -> bool:
    """JSON equality: 1 and true are different values even though Python compares them equal."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def validate_json_schema(value: Any, schema: Any, root: dict | None = None, path: str = "$") -> list[str]:
    """Validate `value` against a Draft 2020-12 subset. Returns every error found."""
    root = root if root is not None else (schema if isinstance(schema, dict) else {})
    node = _resolve_ref(schema, root)
    unsupported = sorted(set(node) - SUPPORTED_KEYWORDS)
    if unsupported:
        raise SchemaError(f"{path}: unsupported schema keyword(s) {unsupported}")
    errors: list[str] = []

    if "const" in node and not _equal(value, node["const"]):
        return [f"{path}: expected const {node['const']!r}, got {value!r}"]
    if "enum" in node and not any(_equal(value, option) for option in node["enum"]):
        return [f"{path}: value {value!r} is not one of {node['enum']!r}"]
    if "type" in node:
        names = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_type_matches(value, name) for name in names):
            return [f"{path}: expected type {node['type']!r}, got {type(value).__name__}"]

    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            errors.append(f"{path}: string shorter than minLength {node['minLength']}")
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {node['maxLength']}")
        if "pattern" in node and re.search(node["pattern"], value) is None:
            errors.append(f"{path}: {value!r} does not match pattern {node['pattern']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            errors.append(f"{path}: {value} < minimum {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            errors.append(f"{path}: {value} > maximum {node['maximum']}")
        if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
            errors.append(f"{path}: {value} <= exclusiveMinimum {node['exclusiveMinimum']}")
        if "exclusiveMaximum" in node and value >= node["exclusiveMaximum"]:
            errors.append(f"{path}: {value} >= exclusiveMaximum {node['exclusiveMaximum']}")
        if "multipleOf" in node and node["multipleOf"] and value % node["multipleOf"] != 0:
            errors.append(f"{path}: {value} is not a multiple of {node['multipleOf']}")

    if isinstance(value, list):
        prefix = node.get("prefixItems") or []
        for index, item in enumerate(value):
            if index < len(prefix):
                errors.extend(validate_json_schema(item, prefix[index], root, f"{path}[{index}]"))
            elif "items" in node:
                errors.extend(validate_json_schema(item, node["items"], root, f"{path}[{index}]"))
        if "minItems" in node and len(value) < node["minItems"]:
            errors.append(f"{path}: array shorter than minItems {node['minItems']}")
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(f"{path}: array longer than maxItems {node['maxItems']}")
        if node.get("uniqueItems"):
            for i in range(len(value)):
                if any(_equal(value[i], value[j]) for j in range(i)):
                    errors.append(f"{path}[{i}]: duplicate item violates uniqueItems")
                    break
        if "contains" in node:
            matches = sum(1 for item in value if not validate_json_schema(item, node["contains"], root, path))
            if matches < int(node.get("minContains", 1)):
                errors.append(f"{path}: fewer than minContains {node.get('minContains', 1)} matching items")
            if "maxContains" in node and matches > int(node["maxContains"]):
                errors.append(f"{path}: more than maxContains {node['maxContains']} matching items")

    if isinstance(value, dict):
        properties = node.get("properties") or {}
        patterns = node.get("patternProperties") or {}
        for name in node.get("required") or []:
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        if "minProperties" in node and len(value) < node["minProperties"]:
            errors.append(f"{path}: fewer than minProperties {node['minProperties']}")
        if "maxProperties" in node and len(value) > node["maxProperties"]:
            errors.append(f"{path}: more than maxProperties {node['maxProperties']}")
        for name, required in (node.get("dependentRequired") or {}).items():
            if name in value:
                for dependent in required:
                    if dependent not in value:
                        errors.append(f"{path}: property {name!r} requires {dependent!r}")
        additional = node.get("additionalProperties", True)
        for name, item in value.items():
            matched = False
            if name in properties:
                errors.extend(validate_json_schema(item, properties[name], root, f"{path}.{name}"))
                matched = True
            for expression, subschema in patterns.items():
                if re.search(expression, name):
                    errors.extend(validate_json_schema(item, subschema, root, f"{path}.{name}"))
                    matched = True
            if not matched:
                if additional is False:
                    errors.append(f"{path}: unexpected additional property {name!r}")
                elif additional is not True:
                    errors.extend(validate_json_schema(item, additional, root, f"{path}.{name}"))
            if "propertyNames" in node:
                errors.extend(validate_json_schema(name, node["propertyNames"], root, f"{path}:name({name})"))

    for subschema in node.get("allOf") or []:
        errors.extend(validate_json_schema(value, subschema, root, path))
    if "anyOf" in node and not any(not validate_json_schema(value, s, root, path) for s in node["anyOf"]):
        errors.append(f"{path}: value matches no branch of anyOf")
    if "oneOf" in node:
        matched = sum(1 for s in node["oneOf"] if not validate_json_schema(value, s, root, path))
        if matched != 1:
            errors.append(f"{path}: expected exactly one matching oneOf branch, matched {matched}")
    if "not" in node and not validate_json_schema(value, node["not"], root, path):
        errors.append(f"{path}: value must not match the 'not' subschema")
    if "if" in node:
        branch = "then" if not validate_json_schema(value, node["if"], root, path) else "else"
        if branch in node:
            errors.extend(validate_json_schema(value, node[branch], root, path))
    return errors


def validate_against_schema_file(data: Any, schema_path: str | Path) -> tuple[bool, list[str]]:
    """Fail-closed: an unreadable or unusable schema is a validation failure, never a pass."""
    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, [f"schema unavailable at {schema_path}: {exc}"]
    try:
        errors = validate_json_schema(data, schema, schema)
    except SchemaError as exc:
        return False, [f"schema unusable: {exc}"]
    return not errors, errors


SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


# --------------------------------------------------------------------------- assertion registry

LIFECYCLE_PHASES = (
    "pre_execution",
    "post_maker_pre_review",
    "post_checker_pre_merge",
    "post_merge_pre_close",
    "post_terminal",
)

_SHA40 = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_NAME = {"type": "string", "minLength": 1}

# The closed registry. `phases` is the exhaustive set of lifecycle phases in which the
# assertion is decidable; anywhere else its answer is either not yet determined or already
# stale, and evaluating it there would report a truth about the wrong moment.
ASSERTION_REGISTRY: dict[str, dict[str, Any]] = {
    "checker_approved": {
        "phases": ("post_checker_pre_merge",),
        "parameters": {"unit": _NAME, "reviewed_commit": _SHA40},
        "required": ("unit", "reviewed_commit"),
        "description": "The independent Checker returned `approved` with zero action items for this exact commit.",
    },
    "main_not_merged": {
        "phases": ("post_checker_pre_merge",),
        "parameters": {"branch": _NAME},
        "required": ("branch",),
        "description": "The integration branch has not yet been merged into the protected branch.",
    },
    "merge_commit_exists": {
        "phases": ("post_merge_pre_close", "post_terminal"),
        "parameters": {"commit": _SHA40},
        "required": ("commit",),
        "description": "The merge commit is present and reachable in the repository.",
    },
    "canonical_gate_passed": {
        "phases": ("post_merge_pre_close", "post_terminal"),
        "parameters": {"gate_id": _NAME},
        "required": ("gate_id",),
        "description": "The named canonical gate ran and exited zero after the merge.",
    },
    "origin_synced": {
        "phases": ("post_terminal",),
        "parameters": {"branch": _NAME, "remote": _NAME},
        "required": ("branch", "remote"),
        "description": "The local branch and its remote tracking ref point at the same commit.",
    },
    "spec_digest_unchanged": {
        "phases": LIFECYCLE_PHASES,
        "parameters": {"work_ref": _NAME, "sha256": _SHA256},
        "required": ("work_ref", "sha256"),
        "description": "The authorized specification still hashes to the digest frozen at authorization.",
    },
    "protected_paths_intact": {
        "phases": LIFECYCLE_PHASES,
        "parameters": {"policy_id": _NAME},
        "required": ("policy_id",),
        "description": "Every protected path still satisfies its declared policy.",
    },
    "working_tree_clean": {
        "phases": ("pre_execution", "post_merge_pre_close", "post_terminal"),
        "parameters": {},
        "required": (),
        "description": "No tracked change and no untracked file are present in the working tree.",
    },
    "functional_checkpoint_matches": {
        "phases": ("pre_execution",),
        "parameters": {"commit": _SHA40, "tree": _SHA40},
        "required": ("commit", "tree"),
        "description": "HEAD is exactly the inherited functional checkpoint and carries its recorded tree.",
    },
    "budget_not_exhausted": {
        "phases": ("pre_execution", "post_maker_pre_review", "post_checker_pre_merge"),
        "parameters": {"minimum_remaining": {"type": "integer", "minimum": 0}},
        "required": ("minimum_remaining",),
        "description": "The global authority budget still covers the declared minimum of model calls.",
    },
}

REQUIRED_BUDGET_SCENARIOS = ("straight_line", "retry")


# --------------------------------------------------------------------------- protected paths

PROTECTED_PATH_POLICIES = ("read_only", "exact_file_hash", "exact_set_snapshot")
# Ordered from least to most constraining. A child may move right, never left.
_POLICY_STRICTNESS = {"read_only": 0, "exact_file_hash": 1, "exact_set_snapshot": 2}


PROTECTED_PATH_PATTERN_INVALID = "protected_path_pattern_invalid"
PROTECTED_PATH_UNREADABLE = "protected_path_unreadable"

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class ProtectedPathError(ValueError):
    """A protected path pattern that is not provably relative to, and contained in, the repository."""

    def __init__(self, pattern: Any, detail: str):
        super().__init__(f"{PROTECTED_PATH_PATTERN_INVALID}: {pattern!r}: {detail}")
        self.pattern = pattern
        self.detail = detail


def normalize_protected_pattern(pattern: Any) -> str:
    """The canonical repository-relative POSIX form of `pattern`, or ProtectedPathError.

    Purely lexical: nothing is joined, resolved or touched on disk before the pattern is proven
    to be relative and free of traversal. Anything that would mean something else on another
    platform (a drive, a UNC share, a backslash separator) is ambiguous and therefore refused.
    """
    if not isinstance(pattern, str):
        raise ProtectedPathError(pattern, "pattern must be a string")
    if not pattern:
        raise ProtectedPathError(pattern, "pattern must not be empty")
    if "\0" in pattern:
        raise ProtectedPathError(pattern, "pattern contains a NUL byte")
    if pattern.startswith(("//", "\\\\", "/\\", "\\/")):
        raise ProtectedPathError(pattern, "UNC or network paths are outside the repository")
    if pattern.startswith(("/", "\\")):
        raise ProtectedPathError(pattern, "absolute paths are outside the repository")
    if _WINDOWS_DRIVE_RE.match(pattern):
        raise ProtectedPathError(pattern, "Windows drive paths are outside the repository")
    parts = re.split(r"[\\/]", pattern)
    if ".." in parts:
        raise ProtectedPathError(pattern, "'..' components may escape the repository")
    if "\\" in pattern:
        raise ProtectedPathError(pattern, "backslash separators are ambiguous across platforms")
    normalized = "/".join(part for part in parts if part not in ("", "."))
    return normalized or "."


# ---- descriptor-relative, no-follow traversal (R10) ------------------------------------
#
# A pathname is re-resolved by the kernel on every call, so checking components with lstat
# and then reading by pathname leaves a window in which a validated directory can be swapped
# for a symlink. Every lookup below is therefore relative to a directory descriptor that is
# already held open, and every open refuses to follow a symlink: once a component has been
# opened, renaming or replacing it on disk cannot redirect what is read through it. A platform
# that cannot express this does not get a pathname fallback; it gets an explicit refusal.

PROTECTED_PATH_UNVERIFIABLE = "protected_path_unverifiable"


class SecureTraversalUnavailable(OSError):
    """The platform lacks the descriptor-relative, no-follow primitives protected paths need."""


def _secure_traversal_gaps() -> tuple[str, ...]:
    gaps = [f"os.{flag}" for flag in ("O_NOFOLLOW", "O_DIRECTORY") if not hasattr(os, flag)]
    for function, label in ((os.open, "os.open(dir_fd=)"), (os.stat, "os.stat(dir_fd=)"),
                            (os.readlink, "os.readlink(dir_fd=)")):
        if function not in os.supports_dir_fd:
            gaps.append(label)
    if os.stat not in os.supports_follow_symlinks:
        gaps.append("os.stat(follow_symlinks=False)")
    if os.listdir not in os.supports_fd:
        gaps.append("os.listdir(fd)")
    return tuple(gaps)


# Probed once, before anything could wrap these functions; a test simulates a platform
# without them by patching this tuple.
_SECURE_TRAVERSAL_GAPS = _secure_traversal_gaps()
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | _O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | _O_CLOEXEC


def _located(error: OSError, root: Path, relative: str) -> OSError:
    """The same error, naming the repository path instead of a bare descriptor-relative name."""
    if isinstance(error, SecureTraversalUnavailable):
        return error
    path = str(root / relative) if relative not in ("", ".") else str(root)
    located = type(error)(error.errno, error.strerror or str(error), path)
    located.__cause__ = error
    return located


class _SecureTree:
    """The repository root held open by descriptor. Nothing beneath it is ever looked up by
    pathname: each component is opened relative to its parent's descriptor, without following
    symlinks, and checked to be the very object its lstat described."""

    def __init__(self, root: Path):
        if _SECURE_TRAVERSAL_GAPS:
            raise SecureTraversalUnavailable(
                0, "descriptor-relative no-follow traversal is unavailable on this platform "
                   f"({', '.join(_SECURE_TRAVERSAL_GAPS)}); protected paths cannot be verified safely",
                str(root))
        self.root = root
        try:
            self.fd = os.open(str(root), _DIRECTORY_FLAGS)
        except OSError as error:
            raise _located(error, root, "") from error

    def __enter__(self) -> "_SecureTree":
        return self

    def __exit__(self, *_exc: object) -> None:
        os.close(self.fd)

    def lstat_at(self, dir_fd: int, name: str, relative: str) -> os.stat_result | None:
        """lstat of `name` inside `dir_fd`; None when it does not exist."""
        try:
            return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError as error:
            raise _located(error, self.root, relative) from error

    def open_directory_at(self, dir_fd: int, name: str, relative: str, expected: os.stat_result,
                          pattern: Any) -> int:
        """Open the directory `expected` describes; a swap since that lstat is a refusal."""
        try:
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=dir_fd)
        except OSError as error:
            if error.errno in _SWAPPED_ERRNOS:
                raise ProtectedPathError(
                    pattern, f"component {relative!r} stopped being a directory while it was verified; "
                             "containment in the repository cannot be proven") from error
            raise _located(error, self.root, relative) from error
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino) or not stat.S_ISDIR(opened.st_mode):
            os.close(fd)
            raise ProtectedPathError(
                pattern, f"component {relative!r} was replaced while it was verified; "
                         "containment in the repository cannot be proven")
        return fd

    def read_file_at(self, dir_fd: int, name: str, relative: str, expected: os.stat_result) -> bytes:
        """Every byte of the regular file `expected` describes, read through its own descriptor."""
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
        except OSError as error:
            raise _located(error, self.root, relative) from error
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)):
                raise OSError(errno.ESTALE, "file was replaced while it was verified", str(self.root / relative))
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        except OSError as error:
            raise _located(error, self.root, relative) from error
        finally:
            os.close(fd)

    def readlink_at(self, dir_fd: int, name: str, relative: str) -> bytes:
        try:
            return os.fsencode(os.readlink(name, dir_fd=dir_fd))
        except OSError as error:
            raise _located(error, self.root, relative) from error

    def list_at(self, dir_fd: int, relative: str) -> list[str]:
        try:
            return sorted(os.listdir(dir_fd))
        except OSError as error:
            raise _located(error, self.root, relative) from error

    def open_parent(self, pattern: Any, components: list[str]) -> int | None:
        """A descriptor on the directory holding the last component, or None when an
        intermediate component does not exist. A symlinked intermediate is a refusal: nothing
        behind it is ever opened, stat-ed or read. The caller closes the descriptor."""
        fd = os.dup(self.fd)
        try:
            for index, name in enumerate(components[:-1]):
                relative = "/".join(components[:index + 1])
                info = self.lstat_at(fd, name, relative)
                if info is None:
                    os.close(fd)
                    return None
                if stat.S_ISLNK(info.st_mode):
                    raise ProtectedPathError(
                        pattern, f"intermediate component {relative!r} is a symlink; "
                                 "containment in the repository cannot be proven")
                if not stat.S_ISDIR(info.st_mode):
                    os.close(fd)
                    return None
                child = self.open_directory_at(fd, name, relative, info, pattern)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise


# ELOOP: the component became a symlink. ENOTDIR: it became something else, or (on some
# platforms) a symlink refused by O_DIRECTORY|O_NOFOLLOW.
_SWAPPED_ERRNOS = {errno.ELOOP, errno.ENOTDIR}


def _components(normalized: str) -> list[str]:
    return [] if normalized == "." else normalized.split("/")


def _lexically_contained(root: Path, pattern: Any, normalized: str) -> None:
    components = _components(normalized)
    if components and os.path.commonpath([str(root), str(root.joinpath(*components))]) != str(root):
        raise ProtectedPathError(pattern, "pattern does not stay inside the repository root")


def _prove_contained(tree: _SecureTree, pattern: Any, normalized: str) -> None:
    """Every intermediate component of `normalized` exists as a real directory inside the
    repository, or does not exist at all. A symlink on the way is ProtectedPathError."""
    _lexically_contained(tree.root, pattern, normalized)
    components = _components(normalized)
    if not components:
        return
    parent = tree.open_parent(pattern, components)
    if parent is not None:
        os.close(parent)


def _entry(relative: str, kind: str, data: bytes) -> dict[str, Any]:
    return {"path": relative, "type": kind, "size": len(data), "sha256": sha256_hex(data)}


def _walk_entries(tree: _SecureTree, dir_fd: int, prefix: str, pattern: Any, entries: list[dict]) -> None:
    """Snapshot entries beneath an open directory. An unreadable or vanished entry, or one
    that is neither a file, a directory nor a symlink, is an error, never a shorter snapshot."""
    for name in tree.list_at(dir_fd, prefix or "."):
        relative = f"{prefix}/{name}" if prefix else name
        info = tree.lstat_at(dir_fd, name, relative)
        if info is None:
            raise FileNotFoundError(errno.ENOENT, "entry vanished while it was verified", str(tree.root / relative))
        _append_entry(tree, dir_fd, name, relative, info, pattern, entries)


def _append_entry(tree: _SecureTree, dir_fd: int, name: str, relative: str, info: os.stat_result,
                  pattern: Any, entries: list[dict]) -> None:
    if stat.S_ISLNK(info.st_mode):
        # A symlink is an entry in its own right, hashed by its target text and never followed.
        entries.append(_entry(relative, "symlink", tree.readlink_at(dir_fd, name, relative)))
    elif stat.S_ISREG(info.st_mode):
        entries.append(_entry(relative, "file", tree.read_file_at(dir_fd, name, relative, info)))
    elif stat.S_ISDIR(info.st_mode):
        child = tree.open_directory_at(dir_fd, name, relative, info, pattern)
        try:
            _walk_entries(tree, child, relative, pattern, entries)
        finally:
            os.close(child)
    else:
        raise OSError(errno.EINVAL, "not a regular file, directory or symlink", str(tree.root / relative))


def _snapshot_entries(tree: _SecureTree, pattern: Any, normalized: str) -> list[dict[str, Any]]:
    _lexically_contained(tree.root, pattern, normalized)
    entries: list[dict[str, Any]] = []
    components = _components(normalized)
    if not components:
        _walk_entries(tree, tree.fd, "", pattern, entries)
    else:
        parent = tree.open_parent(pattern, components)
        if parent is None:
            return entries
        try:
            info = tree.lstat_at(parent, components[-1], normalized)
            if info is not None:
                _append_entry(tree, parent, components[-1], normalized, info, pattern, entries)
        finally:
            os.close(parent)
    entries.sort(key=lambda item: item["path"])
    return entries


def snapshot_set(root: str | Path, pattern: str) -> dict[str, Any]:
    """Reference snapshot of everything under `pattern`, stably ordered and digest-bound."""
    normalized = normalize_protected_pattern(pattern)
    root = Path(root).resolve()
    with _SecureTree(root) as tree:
        entries = _snapshot_entries(tree, pattern, normalized)
    return {"pattern": normalized, "entries": entries, "digest": digest_of(entries)}


def _covers(pattern: str, candidate: str) -> bool:
    normalized = Path(pattern).as_posix().strip("/")
    other = Path(candidate).as_posix().strip("/")
    return normalized in {"", "."} or other == normalized or other.startswith(normalized + "/")


def _git_dirty_paths(root: Path) -> list[str] | None:
    """Changed, staged, renamed or untracked paths; None when git cannot answer."""
    try:
        record = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(root), capture_output=True, text=True, check=False, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if record.returncode != 0:
        return None
    tokens = record.stdout.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        candidates = [path]
        if "R" in status or "C" in status:
            if index < len(tokens):
                candidates.append(tokens[index])
            index += 1
        paths.extend(candidate for candidate in candidates if candidate)
    return sorted(set(paths))


def _invalid_pattern(item: dict, error: ProtectedPathError, **extra: Any) -> dict:
    return {"pattern": str(item.get("pattern", "")), "policy": item.get("policy"),
            "violation": PROTECTED_PATH_PATTERN_INVALID, "detail": error.detail, **extra}


def _unreadable(item: dict, error: OSError) -> dict:
    pattern = str(item.get("pattern", ""))
    return {"pattern": pattern, "policy": item.get("policy"), "violation": PROTECTED_PATH_UNREADABLE,
            "path": error.filename if isinstance(error.filename, str) else pattern,
            "detail": f"{type(error).__name__}: {error}"}


def _unverifiable(item: dict, error: SecureTraversalUnavailable) -> dict:
    return {"pattern": str(item.get("pattern", "")), "policy": item.get("policy"),
            "violation": PROTECTED_PATH_UNVERIFIABLE, "detail": error.strerror or str(error)}


def protected_pattern_violations(protected_paths: list[dict], **extra: Any) -> list[dict]:
    """One structured violation per protected path whose pattern is not repository-contained."""
    violations: list[dict] = []
    for item in protected_paths:
        try:
            normalize_protected_pattern(item.get("pattern"))
        except ProtectedPathError as error:
            violations.append(_invalid_pattern(item, error, **extra))
    return violations


def verify_protected_paths(root: str | Path, protected_paths: list[dict], *, dirty_paths: list[str] | None = None) -> list[dict]:
    """Verify each protected path against the tree. Returns structured violations (empty = intact).

    A pattern that is not provably inside the repository is refused before anything is joined
    onto the root. Every remaining pattern, whatever its policy, then has its intermediate
    components proven to be real directories inside the repository before any policy is
    evaluated, so a symlinked component is `protected_path_pattern_invalid` even under
    `read_only`. A filesystem error while verifying is a violation carrying its detail, and a
    platform without safe traversal primitives is `protected_path_unverifiable`: none of these
    can escape as an exception nor pass as an intact path.
    """
    violations: list[dict] = []
    valid: list[tuple[dict, str]] = []
    for item in protected_paths:
        try:
            valid.append((item, normalize_protected_pattern(item.get("pattern"))))
        except ProtectedPathError as error:
            violations.append(_invalid_pattern(item, error))
    if not valid:
        return violations
    root = Path(root).resolve()
    try:
        tree = _SecureTree(root)
    except SecureTraversalUnavailable as error:
        return violations + [_unverifiable(item, error) for item, _normalized in valid]
    except OSError as error:
        return violations + [_unreadable(item, error) for item, _normalized in valid]

    with tree:
        contained: list[tuple[dict, str]] = []
        for item, normalized in valid:
            try:
                _prove_contained(tree, item.get("pattern"), normalized)
            except ProtectedPathError as error:
                violations.append(_invalid_pattern(item, error))
                continue
            except OSError as error:
                violations.append(_unreadable(item, error))
                continue
            contained.append((item, normalized))

        read_only = [(item, normalized) for item, normalized in contained if item.get("policy") == "read_only"]
        if read_only:
            dirty = dirty_paths if dirty_paths is not None else _git_dirty_paths(root)
            for item, normalized in read_only:
                pattern = str(item.get("pattern", ""))
                if dirty is None:
                    violations.append({"pattern": pattern, "policy": "read_only",
                                       "violation": "protected_read_only_unverifiable",
                                       "detail": "no baseline was supplied and git could not report the working tree"})
                    continue
                for path in [p for p in dirty if _covers(normalized, p)]:
                    violations.append({"pattern": pattern, "policy": "read_only",
                                       "violation": "protected_read_only_mutated", "path": path})

        for item, normalized in contained:
            policy = item.get("policy")
            if policy not in ("exact_file_hash", "exact_set_snapshot"):
                continue
            pattern = str(item.get("pattern", ""))
            try:
                violations.extend(_verify_exact_policy(tree, item, pattern, normalized, policy))
            except ProtectedPathError as error:
                violations.append(_invalid_pattern(item, error))
            except OSError as error:
                violations.append(_unreadable(item, error))
    return violations


def _verify_exact_policy(tree: _SecureTree, item: dict, pattern: str, normalized: str, policy: str) -> list[dict]:
    violations: list[dict] = []
    if policy == "exact_file_hash":
        expected = str(item.get("sha256", ""))
        components = _components(normalized)
        observed_bytes: bytes | None = None
        kind = "missing"
        parent = tree.open_parent(pattern, components) if components else None
        if parent is not None:
            try:
                info = tree.lstat_at(parent, components[-1], normalized)
                if info is not None and stat.S_ISLNK(info.st_mode):
                    kind = "symlink"
                elif info is not None and stat.S_ISREG(info.st_mode):
                    kind = "file"
                    observed_bytes = tree.read_file_at(parent, components[-1], normalized, info)
            finally:
                os.close(parent)
        if kind == "symlink":
            violations.append({"pattern": pattern, "policy": policy, "path": pattern,
                               "violation": "protected_file_type_changed",
                               "expected": "file", "observed": "symlink"})
            return violations
        if observed_bytes is None:
            violations.append({"pattern": pattern, "policy": policy, "path": pattern,
                               "violation": "protected_path_missing"})
            return violations
        observed = sha256_hex(observed_bytes)
        if observed != expected:
            violations.append({"pattern": pattern, "policy": policy, "path": pattern,
                               "violation": "protected_file_hash_mismatch",
                               "expected": expected, "observed": observed})
        return violations

    reference = item.get("snapshot") or {}
    declared_entries = [e for e in reference.get("entries", []) if isinstance(e, dict) and "path" in e]
    expected_entries = {entry["path"]: entry for entry in declared_entries}
    observed_entries = {entry["path"]: entry for entry in _snapshot_entries(tree, pattern, normalized)}
    for path in sorted(set(observed_entries) - set(expected_entries)):
        violations.append({"pattern": pattern, "policy": policy, "path": path,
                           "violation": "protected_set_entry_added",
                           "observed": observed_entries[path]})
    for path in sorted(set(expected_entries) - set(observed_entries)):
        violations.append({"pattern": pattern, "policy": policy, "path": path,
                           "violation": "protected_set_entry_removed",
                           "expected": expected_entries[path]})
    for path in sorted(set(expected_entries) & set(observed_entries)):
        expected_entry, observed_entry = expected_entries[path], observed_entries[path]
        if expected_entry.get("type") != observed_entry.get("type"):
            violations.append({"pattern": pattern, "policy": policy, "path": path,
                               "violation": "protected_set_entry_type_changed",
                               "expected": expected_entry.get("type"), "observed": observed_entry.get("type")})
        elif (expected_entry.get("sha256") != observed_entry.get("sha256")
              or expected_entry.get("size") != observed_entry.get("size")):
            violations.append({"pattern": pattern, "policy": policy, "path": path,
                               "violation": "protected_set_entry_modified",
                               "expected": expected_entry, "observed": observed_entry})
    declared_digest = reference.get("digest")
    recomputed = digest_of(declared_entries)
    if declared_digest and declared_digest != recomputed:
        violations.append({"pattern": pattern, "policy": policy,
                           "violation": "protected_snapshot_digest_mismatch",
                           "expected": declared_digest, "observed": recomputed})
    return violations


def _pattern_is_valid(item: dict) -> bool:
    try:
        normalize_protected_pattern(item.get("pattern"))
    except ProtectedPathError:
        return False
    return True


def assert_protected_paths_monotonic(parent: list[dict], child: list[dict]) -> list[dict]:
    """Semantic monotonicity (T032 §2.15): every inherited pattern keeps an identical policy.

    Textual presence of the pattern is not enough. For an inherited entry the child must carry
    the same policy and the same policy parameters, so an expected hash or a reference snapshot
    can never be swapped for one that happens to match whatever the child produced. A pattern
    on either side that is not provably inside the repository is itself a violation.
    """
    violations: list[dict] = (protected_pattern_violations(parent, side="parent")
                              + protected_pattern_violations(child, side="child"))
    invalid = {id(item) for item in [*parent, *child] if not _pattern_is_valid(item)}
    child_by_pattern = {str(item.get("pattern", "")): item for item in child if id(item) not in invalid}
    for item in parent:
        if id(item) in invalid:
            continue
        pattern = str(item.get("pattern", ""))
        policy = item.get("policy")
        inherited = child_by_pattern.get(pattern)
        if inherited is None:
            narrower = sorted(p for p in child_by_pattern if p != pattern and _covers(pattern, p))
            violations.append({
                "pattern": pattern, "policy": policy,
                "violation": "protected_path_coverage_reduced" if narrower else "protected_path_removed",
                "detail": f"pattern narrowed to {narrower}" if narrower else "pattern absent from the child",
            })
            continue
        child_policy = inherited.get("policy")
        if child_policy != policy:
            weaker = _POLICY_STRICTNESS.get(str(child_policy), -1) < _POLICY_STRICTNESS.get(str(policy), -1)
            violations.append({
                "pattern": pattern, "policy": policy,
                "violation": "protected_path_policy_weakened" if weaker else "protected_path_policy_changed",
                "expected": policy, "observed": child_policy,
            })
            continue
        if policy == "exact_file_hash" and inherited.get("sha256") != item.get("sha256"):
            violations.append({"pattern": pattern, "policy": policy,
                               "violation": "protected_path_hash_replaced",
                               "expected": item.get("sha256"), "observed": inherited.get("sha256")})
        if policy == "exact_set_snapshot":
            expected = (item.get("snapshot") or {}).get("digest")
            observed = (inherited.get("snapshot") or {}).get("digest")
            if expected != observed:
                violations.append({"pattern": pattern, "policy": policy,
                                   "violation": "protected_path_snapshot_replaced",
                                   "expected": expected, "observed": observed})
    return violations


# --------------------------------------------------------------------------- plan validation

def gate_call_constraints_are_satisfiable_under_budget(plan: dict) -> list[dict]:
    """Arithmetic proof that every declared scenario fits under the plan's model call budget.

    A plan that only adds up on the happy path is a plan that stops mid-review the first time
    the Maker needs a second round, so both the straight-line and the retry scenario must be
    declared and both must be shown to fit.
    """
    findings: list[dict] = []
    budget = plan.get("budget") or {}
    ceiling = int(budget.get("max_model_calls", 0))
    bootstrap = int(budget.get("bootstrap_calls", 0))
    per_round = budget.get("role_calls_per_round") or {}
    round_cost = sum(int(value) for value in per_round.values())
    gate_cost = sum(int(gate.get("model_calls", 0)) for gate in plan.get("gates") or [])
    scenarios = plan.get("scenarios") or []
    declared = {str(scenario.get("name")) for scenario in scenarios}
    if len(declared) != len(scenarios):
        findings.append({"violation": "duplicate_budget_scenario",
                         "detail": "scenario names within scenarios array must be unique"})
    for name in REQUIRED_BUDGET_SCENARIOS:
        if name not in declared:
            findings.append({"violation": "missing_budget_scenario", "scenario": name,
                             "detail": "satisfiability must be proven for the straight-line and the retry scenario"})
    for scenario in scenarios:
        name = str(scenario.get("name"))
        rounds = int(scenario.get("rework_rounds", 0))
        if name == "straight_line" and rounds != 0:
            findings.append({"violation": "invalid_budget_scenario_rounds", "scenario": "straight_line",
                             "rework_rounds": rounds, "detail": "straight_line scenario must specify rework_rounds == 0"})
        elif name == "retry" and rounds < 1:
            findings.append({"violation": "invalid_budget_scenario_rounds", "scenario": "retry",
                             "rework_rounds": rounds, "detail": "retry scenario must specify at least 1 rework round (rework_rounds >= 1)"})
        required = bootstrap + (1 + rounds) * round_cost + gate_cost
        if required > ceiling:
            findings.append({"violation": "gate_call_constraints_unsatisfiable", "scenario": scenario.get("name"),
                             "required_calls": required, "max_model_calls": ceiling,
                             "detail": f"{bootstrap} bootstrap + {1 + rounds} round(s) x {round_cost} + {gate_cost} gate call(s)"})
    return findings


def validate_execution_plan(
    plan: Any,
    *,
    repo_root: str | Path | None = None,
    parent_protected_paths: list[dict] | None = None,
    verify_paths: bool = False,
    schema_path: str | Path | None = None,
) -> dict:
    """Validate one execution plan. Fail-closed: any doubt is a refusal, never a warning."""
    errors: list[dict] = []
    schema_file = Path(schema_path) if schema_path else SCHEMA_DIR / "execution-plan.schema.json"
    valid, schema_errors = validate_against_schema_file(plan, schema_file)
    if not valid:
        return {"approved": False,
                "errors": [{"violation": "schema_invalid", "detail": message} for message in schema_errors]}

    seen_gates: set[str] = set()
    for gate in plan["gates"]:
        gate_id = str(gate["gate_id"])
        if gate_id in seen_gates:
            errors.append({"violation": "duplicate_gate_id", "gate_id": gate_id})
        seen_gates.add(gate_id)
        phase = str(gate["lifecycle_phase"])
        if phase not in LIFECYCLE_PHASES:
            errors.append({"violation": "unknown_lifecycle_phase", "gate_id": gate_id, "lifecycle_phase": phase})
            continue
        for assertion in gate["assertions"]:
            assertion_id = str(assertion["assertion_id"])
            spec = ASSERTION_REGISTRY.get(assertion_id)
            if spec is None:
                errors.append({"violation": "unknown_assertion", "gate_id": gate_id, "assertion_id": assertion_id,
                               "detail": "assertion is not in the closed registry"})
                continue
            if phase not in spec["phases"]:
                errors.append({"violation": "assertion_phase_mismatch", "gate_id": gate_id,
                               "assertion_id": assertion_id, "lifecycle_phase": phase,
                               "allowed_phases": list(spec["phases"])})
            parameters = assertion.get("parameters") or {}
            for name in spec["required"]:
                if name not in parameters:
                    errors.append({"violation": "assertion_parameter_missing", "gate_id": gate_id,
                                   "assertion_id": assertion_id, "parameter": name})
            for name, value in parameters.items():
                declared = spec["parameters"].get(name)
                if declared is None:
                    errors.append({"violation": "assertion_parameter_unknown", "gate_id": gate_id,
                                   "assertion_id": assertion_id, "parameter": name})
                    continue
                for message in validate_json_schema(value, declared, declared, f"{gate_id}.{assertion_id}.{name}"):
                    errors.append({"violation": "assertion_parameter_invalid", "gate_id": gate_id,
                                   "assertion_id": assertion_id, "parameter": name, "detail": message})

    errors.extend(gate_call_constraints_are_satisfiable_under_budget(plan))

    declared = plan.get("protected_paths") or []
    errors.extend(protected_pattern_violations(declared))
    protected = [item for item in declared if _pattern_is_valid(item)]
    for item in protected:
        if item.get("policy") == "exact_file_hash" and not item.get("sha256"):
            errors.append({"violation": "protected_path_missing_hash", "pattern": item.get("pattern")})
        if item.get("policy") == "exact_set_snapshot" and not isinstance((item.get("snapshot") or {}).get("entries"), list):
            errors.append({"violation": "protected_path_missing_snapshot", "pattern": item.get("pattern")})
    if parent_protected_paths is not None:
        errors.extend(assert_protected_paths_monotonic(parent_protected_paths, protected))
    if verify_paths:
        if repo_root is None:
            errors.append({"violation": "protected_paths_unverifiable",
                           "detail": "a repository root is required to verify protected paths"})
        else:
            errors.extend(verify_protected_paths(repo_root, protected))

    return {"approved": not errors, "errors": errors, "plan_id": plan.get("plan_id"),
            "plan_digest": digest_of(plan), "assertions_registered": sorted(ASSERTION_REGISTRY)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an execution plan and its protected paths (T033).")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--repo", type=Path, help="repository root used to verify protected paths")
    parser.add_argument("--parent-plan", type=Path, help="parent plan whose protected paths must be inherited or tightened")
    parser.add_argument("--verify-protected-paths", action="store_true")
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-registry", action="store_true", help="print the closed assertion registry and exit")
    args = parser.parse_args(argv)

    if args.print_registry:
        print(json.dumps({"lifecycle_phases": list(LIFECYCLE_PHASES),
                          "assertions": {name: {"phases": list(spec["phases"]), "required": list(spec["required"]),
                                                "description": spec["description"]}
                                         for name, spec in sorted(ASSERTION_REGISTRY.items())}},
                         indent=2, ensure_ascii=False))
        return 0
    if args.plan is None:
        parser.error("--plan is required unless --print-registry is used")

    result: dict
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result = {"approved": False, "errors": [{"violation": "plan_unreadable", "detail": str(exc)}]}
    else:
        parent_paths = None
        blocked = False
        if args.parent_plan:
            try:
                parent = json.loads(args.parent_plan.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                result = {"approved": False, "errors": [{"violation": "parent_plan_unreadable", "detail": str(exc)}]}
                blocked = True
            else:
                parent_paths = (parent or {}).get("protected_paths") or []
        if not blocked:
            result = validate_execution_plan(plan, repo_root=args.repo, parent_protected_paths=parent_paths,
                                             verify_paths=args.verify_protected_paths, schema_path=args.schema)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.get("approved") else 1


if __name__ == "__main__":
    sys.exit(main())
