#!/usr/bin/env python3
"""
extract_tool_result.py - CLI for deterministic compaction and offloading of tool outputs.
Preserves raw output in an external reference (details_ref) and guarantees losslessness (AC09, AC10)
so that every contractual failure_id is preserved in the compact payload.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def validate_details_ref(details_ref: str) -> None:
    """Validate that details_ref is a non-empty string reference."""
    if not details_ref or not isinstance(details_ref, str) or not details_ref.strip():
        raise ValueError("details_ref must be a valid non-empty string reference")


def extract_go_test(raw: str, details_ref: str) -> dict[str, Any]:
    """
    Extract structured summary from `go test` output.
    Guarantees losslessness: all failed test names (including subtests) are extracted into failure_ids.
    """
    validate_details_ref(details_ref)
    pkg_match = re.search(r"^(?:FAIL|ok)\s+([^\s\t]+)", raw, re.MULTILINE)
    package = pkg_match.group(1) if pkg_match else "unknown"

    # Match --- FAIL: TestName or --- FAIL: TestName/SubTest
    fail_matches = re.findall(r"^--- FAIL:\s*([^\s(]+)", raw, re.MULTILINE)
    pass_matches = re.findall(r"^--- PASS:\s*([^\s(]+)", raw, re.MULTILINE)
    skip_matches = re.findall(r"^--- SKIP:\s*([^\s(]+)", raw, re.MULTILINE)

    failure_ids = []
    for f in fail_matches:
        fid = f"{package}.{f}" if package != "unknown" and not f.startswith(package) else f
        if fid not in failure_ids:
            failure_ids.append(fid)

    is_fail = bool(failure_ids) or bool(re.search(r"^FAIL\b", raw, re.MULTILINE))

    total = len(fail_matches) + len(pass_matches) + len(skip_matches)
    if total == 0 and is_fail:
        total = len(failure_ids) or 1

    return {
        "tool": "go_test",
        "status": "fail" if is_fail else "pass",
        "package": package,
        "total": total,
        "passed": len(pass_matches),
        "failed": len(failure_ids),
        "skipped": len(skip_matches),
        "failure_ids": failure_ids,
        "details_ref": details_ref,
    }


def extract_pytest(raw: str, details_ref: str) -> dict[str, Any]:
    """
    Extract structured summary from `pytest` output.
    Guarantees losslessness: all failed test identifiers are captured in failure_ids.
    """
    validate_details_ref(details_ref)
    # Look for FAILED test_file.py::test_name or ERROR test_file.py::test_name
    fail_matches = re.findall(r"^(?:FAILED|ERROR)\s+([^\s\-]+)", raw, re.MULTILINE)

    failure_ids: list[str] = []
    for f in fail_matches:
        clean = f.strip()
        if clean and clean not in failure_ids:
            failure_ids.append(clean)

    # Summary regex: 1 failed, 2 passed, 1 skipped in 0.12s
    passed = 0
    failed = len(failure_ids)
    skipped = 0
    errors = 0

    p_match = re.search(r"(\d+)\s+passed", raw)
    if p_match:
        passed = int(p_match.group(1))
    f_match = re.search(r"(\d+)\s+failed", raw)
    if f_match:
        failed = max(failed, int(f_match.group(1)))
    s_match = re.search(r"(\d+)\s+skipped", raw)
    if s_match:
        skipped = int(s_match.group(1))
    e_match = re.search(r"(\d+)\s+errors?", raw)
    if e_match:
        errors = int(e_match.group(1))

    is_fail = failed > 0 or errors > 0 or "=== ERRORS ===" in raw or "=== FAILURES ===" in raw

    return {
        "tool": "pytest",
        "status": "fail" if is_fail else "pass",
        "total": passed + failed + skipped + errors,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "failure_ids": failure_ids,
        "details_ref": details_ref,
    }


def extract_git_diff(raw: str, details_ref: str) -> dict[str, Any]:
    """Extract files changed and insertions/deletions from diff or diffstat."""
    validate_details_ref(details_ref)
    affected_files: list[str] = []
    conflict_files: list[str] = []
    current_file = None

    # Check diff --git a/(.*) b/(.*)
    for line in raw.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            current_file = m.group(2)
            if current_file not in affected_files:
                affected_files.append(current_file)
        elif re.match(r"^\s*(\S+)\s+\|\s+\d+", line):
            path = re.match(r"^\s*(\S+)\s+\|\s+\d+", line).group(1)
            if path not in affected_files and not path.endswith("bytes"):
                affected_files.append(path)

        if line.startswith(("<<<<<<<", "+<<<<<<<", "++<<<<<<<")) and current_file:
            if current_file not in conflict_files:
                conflict_files.append(current_file)

    insertions = 0
    deletions = 0
    ins_match = re.search(r"(\d+)\s+insertions?\(\+\)", raw)
    if ins_match:
        insertions = int(ins_match.group(1))
    del_match = re.search(r"(\d+)\s+deletions?\(-\)", raw)
    if del_match:
        deletions = int(del_match.group(1))

    stat_summary = f"{len(affected_files)} files changed, {insertions} insertions(+), {deletions} deletions(-)"
    failure_ids = [f"conflict:{f}" for f in conflict_files]
    is_fail = len(conflict_files) > 0

    return {
        "tool": "git_diff",
        "status": "fail" if is_fail else "pass",
        "files_changed": len(affected_files),
        "insertions": insertions,
        "deletions": deletions,
        "affected_files": affected_files,
        "conflicts": conflict_files,
        "failure_ids": failure_ids,
        "stat_summary": stat_summary,
        "details_ref": details_ref,
    }


def extract_git_status(raw: str, details_ref: str) -> dict[str, Any]:
    """Extract branch and staged, unstaged, untracked file sets."""
    validate_details_ref(details_ref)
    branch = "unknown"
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []

    lines = raw.splitlines()
    is_porcelain = any(line.startswith(("## ", "?? ", " M ", "M  ", "A  ", " D ")) for line in lines[:5])

    if is_porcelain:
        for line in lines:
            if line.startswith("## "):
                branch = line[3:].split("...")[0].strip()
            elif line.startswith("?? "):
                untracked.append(line[3:].strip())
            elif len(line) >= 3:
                x = line[0]
                y = line[1]
                path = line[3:].strip()
                if x in "MADRC":
                    staged.append(path)
                if y in "MD":
                    unstaged.append(path)
    else:
        # Standard human git status
        current_section = None
        for line in lines:
            line_str = line.strip()
            if "On branch " in line_str:
                branch = line_str.replace("On branch ", "").strip()
            elif "Changes to be committed:" in line:
                current_section = "staged"
            elif "Changes not staged for commit:" in line:
                current_section = "unstaged"
            elif "Untracked files:" in line:
                current_section = "untracked"
            elif current_section and line_str and not line_str.startswith("("):
                parts = line_str.split(":", 1)
                file_name = parts[-1].strip()
                if current_section == "staged" and file_name not in staged:
                    staged.append(file_name)
                elif current_section == "unstaged" and file_name not in unstaged:
                    unstaged.append(file_name)
                elif current_section == "untracked" and file_name not in untracked:
                    untracked.append(file_name)

    is_clean = len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0
    failure_ids = (
        [f"staged:{f}" for f in staged]
        + [f"unstaged:{f}" for f in unstaged]
        + [f"untracked:{f}" for f in untracked]
    )

    return {
        "tool": "git_status",
        "branch": branch,
        "is_clean": is_clean,
        "status": "clean" if is_clean else "dirty",
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "failure_ids": failure_ids,
        "details_ref": details_ref,
    }


def extract_grep(raw: str, details_ref: str) -> dict[str, Any]:
    """Extract grep matches and preserve execution failures losslessly.

    Normal match lines are successful search output.  A grep diagnostic (for
    example a missing path or permission error) is a failed gate: its complete
    diagnostic line becomes a failure_id, status is ``fail``, and it is not
    counted as a match.
    """
    validate_details_ref(details_ref)
    matching_files: list[str] = []
    failure_ids: list[str] = []
    match_count = 0

    for line in raw.splitlines():
        if not line.strip():
            continue
        is_diagnostic = bool(re.match(r"^grep(?::|\s+.*(?:error|failed))", line, re.IGNORECASE))
        is_explicit_failure = bool(re.match(r"^(?:ERROR|FAIL(?:ED)?):", line, re.IGNORECASE))
        if is_diagnostic or is_explicit_failure:
            if line not in failure_ids:
                failure_ids.append(line)
            continue
        match_count += 1
        if ":" in line:
            candidate = line.split(":", 1)[0].strip()
            if candidate and candidate not in matching_files:
                matching_files.append(candidate)
        else:
            if line.strip() not in matching_files:
                matching_files.append(line.strip())

    return {
        "tool": "grep",
        "status": "fail" if failure_ids else "pass",
        "match_count": match_count,
        "matching_files": matching_files,
        "failure_ids": failure_ids,
        "details_ref": details_ref,
    }


def extract_build(raw: str, details_ref: str) -> dict[str, Any]:
    """Extract compiler/build errors, warnings, and exit status."""
    validate_details_ref(details_ref)
    error_lines: list[str] = []
    warning_lines: list[str] = []

    for line in raw.splitlines():
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue
        lower = line_str.lower()
        if "warning:" in lower:
            warning_lines.append(line_str)
        elif (
            "error:" in lower
            or "fatal" in lower
            or re.search(r":\d+(?::\d+)?:", line_str)
        ):
            error_lines.append(line_str)

    exit_code = 1 if error_lines else 0
    failure_ids = list(error_lines)

    return {
        "tool": "build",
        "status": "fail" if error_lines else "pass",
        "exit_code": exit_code,
        "error_count": len(error_lines),
        "warning_count": len(warning_lines),
        "errors_summary": error_lines[:10],
        "failure_ids": failure_ids,
        "details_ref": details_ref,
    }


def extract_json_payload(raw: str, details_ref: str, tool_name: str) -> dict[str, Any]:
    """Extract and compact classifier or checker JSON payload with full losslessness."""
    validate_details_ref(details_ref)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "tool": tool_name,
            "status": "invalid_json",
            "error": str(exc),
            "failure_ids": [f"invalid_json:{exc}"],
            "details_ref": details_ref,
        }

    if tool_name == "checker_json":
        verdict = data.get("verdict")
        action_items = list(data.get("action_items", []))
        deferred = list(data.get("deferred", []))
        rejected = list(data.get("rejected", []))
        summary = data.get("summary") or data.get("facts", [])
        if isinstance(summary, list):
            summary = summary[:5]

        failure_ids: list[str] = []
        for idx, ai in enumerate(action_items):
            item_id = ai.get("id") if isinstance(ai, dict) else str(ai)
            failure_ids.append(f"action_item:{item_id or idx}")
        for idx, rej in enumerate(rejected):
            item_id = rej.get("id") if isinstance(rej, dict) else str(rej)
            failure_ids.append(f"rejected:{item_id or idx}")
        for idx, df in enumerate(deferred):
            item_id = df.get("id") if isinstance(df, dict) else str(df)
            failure_ids.append(f"deferred:{item_id or idx}")

        is_fail = verdict in ("changes_requested", "rejected") or len(failure_ids) > 0

        return {
            "tool": "checker_json",
            "status": "fail" if is_fail else "pass",
            "verdict": verdict,
            "schema_version": data.get("schema_version"),
            "summary": summary,
            "action_items": action_items,
            "deferred": deferred,
            "rejected": rejected,
            "failure_ids": failure_ids,
            "details_ref": details_ref,
        }
    elif tool_name == "classifier_json":
        verdict = data.get("verdict") or data.get("confidence")
        status = data.get("status", "valid")
        uncertainties = list(data.get("uncertainties") or data.get("incertezas", []))
        refusals = list(data.get("refusals") or data.get("recusas", []))
        summary = data.get("summary") or data.get("facts", [])
        if isinstance(summary, list):
            summary = summary[:5]

        failure_ids: list[str] = []
        if status not in ("valid", "classified", "success"):
            failure_ids.append(f"invalid_status:{status}")
        for idx, u in enumerate(uncertainties):
            u_str = u if isinstance(u, str) else json.dumps(u)
            failure_ids.append(f"uncertainty:{u_str}")
        for idx, r in enumerate(refusals):
            r_str = r if isinstance(r, str) else json.dumps(r)
            failure_ids.append(f"refusal:{r_str}")

        is_fail = len(failure_ids) > 0 or status in ("refused", "uncertain", "error")

        return {
            "tool": "classifier_json",
            "status": "fail" if is_fail else "pass",
            "verdict": verdict,
            "schema_version": data.get("schema_version"),
            "summary": summary,
            "uncertainties": uncertainties,
            "refusals": refusals,
            "failure_ids": failure_ids,
            "details_ref": details_ref,
        }

    return {
        "tool": tool_name,
        "status": "unknown_tool",
        "failure_ids": [f"unknown_tool:{tool_name}"],
        "details_ref": details_ref,
    }


EXTRACTORS = {
    "go_test": extract_go_test,
    "pytest": extract_pytest,
    "git_diff": extract_git_diff,
    "git_status": extract_git_status,
    "grep": extract_grep,
    "build": extract_build,
    "classifier_json": lambda r, d: extract_json_payload(r, d, "classifier_json"),
    "checker_json": lambda r, d: extract_json_payload(r, d, "checker_json"),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract compact, structured result from raw tool stdout with losslessness preservation."
    )
    parser.add_argument("--tool", "-t", required=True, choices=list(EXTRACTORS.keys()), help="Tool extractor name.")
    parser.add_argument("--input", "-i", required=True, help="Path to raw stdout/log file.")
    parser.add_argument("--output", "-o", help="Path to save compact JSON (default: stdout).")
    parser.add_argument(
        "--details-ref",
        "-d",
        required=True,
        help="Reference (path or URI) to the preserved raw output file.",
    )
    parser.add_argument(
        "--persist-raw",
        action="store_true",
        help="Persist raw input file content into details_ref location if local path.",
    )
    args = parser.parse_args()

    validate_details_ref(args.details_ref)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: input file does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = input_path.read_text(encoding="utf-8")

    if args.persist_raw:
        if not args.details_ref.startswith(("http://", "https://")):
            dest_raw = Path(args.details_ref)
            dest_raw.parent.mkdir(parents=True, exist_ok=True)
            dest_raw.write_text(raw_text, encoding="utf-8")
    elif not args.details_ref.startswith(("http://", "https://")):
        details_path = Path(args.details_ref)
        if not details_path.is_file():
            print(
                "ERROR: details_ref does not exist on disk; use --persist-raw to create it: "
                f"{details_path}",
                file=sys.stderr,
            )
            sys.exit(1)

    extractor = EXTRACTORS[args.tool]
    result = extractor(raw_text, args.details_ref)

    formatted = json.dumps(result, indent=2, sort_keys=True) + "\n"

    if args.output and args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted, encoding="utf-8")
    else:
        sys.stdout.write(formatted)

    sys.exit(0)


if __name__ == "__main__":
    main()
