#!/usr/bin/env python3
"""Slice a raw CI log into the smallest failure record a model needs to act on.

The slicer is deterministic and offline. It never decides that a red run is flaky: it
only names the failing job, step, tests and a normalized signature, keeps a bounded excerpt
and points at the raw file. Classification is a first pass by pattern; `unknown` is a
valid answer and is never upgraded to `flaky` here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
CLASSES = ("code_failure", "external_infrastructure", "configuration", "unknown")
DEFAULT_EXCERPT_LINES = 40
MAX_TESTS = 20

# GitHub Actions and common runners prefix lines with a timestamp and group markers.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s?")
_JOB_PREFIX = re.compile(r"^(?P<job>[^\t]+)\t(?P<step>[^\t]+)\t(?P<rest>.*)$")
_GROUP = re.compile(r"##\[group\](?P<name>.+)")
_ERROR_MARK = re.compile(r"##\[error\](?P<msg>.*)")

_TEST_PATTERNS = (
    re.compile(r"^--- FAIL: (?P<name>\S+)"),                       # go test
    re.compile(r"^FAILED (?P<name>\S+::\S+)"),                      # pytest summary
    re.compile(r"^FAIL: (?P<name>\S+ \([\w.]+\))"),                 # unittest
    re.compile(r"^ERROR: (?P<name>\S+ \([\w.]+\))"),                # unittest
    re.compile(r"^\s*[✕×] (?P<name>.+?)(?: \(\d+ ?ms\))?$"),       # jest / vitest
    re.compile(r"^\s*(?:●|✗|✘) (?P<name>.+)$"),                     # jest verbose / mocha
    re.compile(r"^(?:error|failures?):\s+(?P<name>[\w:]+::\S+)"),   # cargo test
)
_INFRA_PATTERNS = (
    re.compile(r"connection reset|econnreset|etimedout|socket hang up", re.I),
    re.compile(r"\b(502|503|504)\b.*(gateway|unavailable|timeout)", re.I),
    re.compile(r"rate limit|too many requests|429", re.I),
    re.compile(r"could not resolve host|temporary failure in name resolution", re.I),
    re.compile(r"the hosted runner .* lost communication|runner has received a shutdown", re.I),
    re.compile(r"no space left on device", re.I),
    re.compile(r"toomanyrequests|failed to download action", re.I),
)
_CONFIG_PATTERNS = (
    re.compile(r"invalid workflow file|unable to resolve action|unrecognized named-value", re.I),
    re.compile(r"secret .* (not found|is not set)|missing required (input|secret)", re.I),
    re.compile(r"yaml\.parser|yaml: line \d+", re.I),
)
_PROCESS_EXIT = re.compile(r"process completed with exit code (?P<code>\d+)", re.I)

_HEX = re.compile(r"\b[0-9a-f]{7,}\b")
_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_PATH = re.compile(r"(?:[A-Za-z]:)?[\\/][\w.\\/-]+")
_TIME = re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|m|h)\b")


def normalize(text: str) -> str:
    text = text.lower()
    text = _TIMESTAMP.sub("", text)
    text = _TIME.sub("<t>", text)
    text = _HEX.sub("<hex>", text)
    text = _PATH.sub("<path>", text)
    text = _NUM.sub("<n>", text)
    return re.sub(r"\s+", " ", text).strip()


def signature(*parts: str) -> str:
    joined = "\n".join(normalize(p) for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _strip(line: str) -> tuple[str | None, str | None, str]:
    """Return (job, step, text) for a line, tolerating both `gh run view --log` and raw logs."""
    match = _JOB_PREFIX.match(line)
    if match:
        return match.group("job"), match.group("step"), _TIMESTAMP.sub("", match.group("rest"))
    return None, None, _TIMESTAMP.sub("", line)


def slice_log(text: str, *, excerpt_lines: int = DEFAULT_EXCERPT_LINES, raw_ref: str | None = None) -> dict:
    lines = text.splitlines()
    failed_tests: list[str] = []
    errors: list[str] = []
    infra_hits: list[str] = []
    config_hits: list[str] = []
    exit_codes: list[int] = []
    job = step = None
    current_group = None
    first_failure_index: int | None = None
    for index, raw in enumerate(lines):
        line_job, line_step, line = _strip(raw)
        group = _GROUP.search(line)
        if group:
            current_group = group.group("name").strip()
        hit = False
        for pattern in _TEST_PATTERNS:
            match = pattern.match(line)
            if match:
                name = match.group("name").strip()
                if name not in failed_tests and len(failed_tests) < MAX_TESTS:
                    failed_tests.append(name)
                hit = True
                break
        error = _ERROR_MARK.search(line)
        if error:
            errors.append(error.group("msg").strip())
            hit = True
        exit_match = _PROCESS_EXIT.search(line)
        if exit_match:
            exit_codes.append(int(exit_match.group("code")))
            hit = True
        if any(p.search(line) for p in _INFRA_PATTERNS):
            infra_hits.append(line.strip())
            hit = True
        if any(p.search(line) for p in _CONFIG_PATTERNS):
            config_hits.append(line.strip())
            hit = True
        if hit and first_failure_index is None:
            first_failure_index = index
            job = line_job
            step = line_step or current_group
    if first_failure_index is None:
        excerpt = lines[-excerpt_lines:]
    else:
        start = max(0, first_failure_index - 5)
        excerpt = lines[start:start + excerpt_lines]
    excerpt_text = "\n".join(_strip(l)[2] for l in excerpt)

    if failed_tests or (exit_codes and not infra_hits and not config_hits):
        klass = "code_failure"
    elif config_hits and not failed_tests:
        klass = "configuration"
    elif infra_hits and not failed_tests:
        klass = "external_infrastructure"
    else:
        klass = "unknown"
    sig_source = failed_tests[:5] or errors[:3] or infra_hits[:2] or config_hits[:2] or [excerpt_text[-400:]]
    return {
        "schema_version": SCHEMA_VERSION,
        "job": job,
        "step": step,
        "failed_tests": failed_tests,
        "errors": errors[:10],
        "exit_codes": exit_codes[:5],
        "classification": klass,
        "signature": signature(*sig_source),
        "excerpt": excerpt_text,
        "excerpt_lines": len(excerpt),
        "total_lines": len(lines),
        "raw_ref": raw_ref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", required=True, help="raw log file; `-` reads stdin")
    parser.add_argument("--excerpt-lines", type=int, default=DEFAULT_EXCERPT_LINES)
    parser.add_argument("--out", default=None, help="write the JSON slice here instead of stdout")
    args = parser.parse_args(argv)
    if args.log == "-":
        text = sys.stdin.read()
        raw_ref = None
    else:
        path = Path(args.log)
        text = path.read_text(encoding="utf-8", errors="replace")
        raw_ref = path.as_posix()
    result = slice_log(text, excerpt_lines=max(5, args.excerpt_lines), raw_ref=raw_ref)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
