#!/usr/bin/env python3
"""
resume_generate.py - Deterministic Resume Manifest (resume.json) Generator.
Produces verifiable resume manifests with provenance (sources, selectors, digests),
resolved phase context, and strict pre-dispatch integrity verification (AC02, AC07, AC15).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_GENERATOR_VERSION = "resume_generate/1.0.0 (T032)"
DEFAULT_BOOTSTRAP_BUDGET = 5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.context_lib import (
    SelectorNotFoundError,
    compute_sha256,
    discover_active_roots,
    is_archived_evidence_path,
    mask_volatile_fields,
    select_section,
)

VALID_POLICY_CLASSES = {
    "active_unit.spec",
    "authorization.current",
    "unresolved_items",
    "project.constraints",
    "applicable_decisions",
    "dependency_outputs",
    "previous_rounds",
    "discussions",
    "raw_logs",
    "full_architecture",
}

VALID_POLICY_PHASES = {"planning", "implementation", "review", "rework", "debate"}
VALID_POLICY_DELIVERIES = {"inline", "excerpt", "on_demand"}

DEFAULT_CONTEXT_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "classes": [
        "active_unit.spec",
        "authorization.current",
        "unresolved_items",
        "project.constraints",
        "applicable_decisions",
        "dependency_outputs",
        "previous_rounds",
        "discussions",
        "raw_logs",
        "full_architecture",
    ],
    "bootstrap_on_demand_budget": DEFAULT_BOOTSTRAP_BUDGET,
    "phases": {
        "planning": {
            "active_unit.spec": "inline",
            "authorization.current": "inline",
            "unresolved_items": "excerpt",
            "project.constraints": "excerpt",
            "applicable_decisions": "excerpt",
            "dependency_outputs": "excerpt",
            "previous_rounds": "on_demand",
            "discussions": "on_demand",
            "raw_logs": "on_demand",
            "full_architecture": "on_demand",
        },
        "implementation": {
            "active_unit.spec": "inline",
            "authorization.current": "inline",
            "unresolved_items": "excerpt",
            "project.constraints": "excerpt",
            "applicable_decisions": "excerpt",
            "dependency_outputs": "on_demand",
            "previous_rounds": "on_demand",
            "discussions": "on_demand",
            "raw_logs": "on_demand",
            "full_architecture": "on_demand",
        },
        "review": {
            "active_unit.spec": "inline",
            "authorization.current": "inline",
            "unresolved_items": "inline",
            "project.constraints": "excerpt",
            "applicable_decisions": "on_demand",
            "dependency_outputs": "on_demand",
            "previous_rounds": "excerpt",
            "discussions": "on_demand",
            "raw_logs": "on_demand",
            "full_architecture": "on_demand",
        },
        "rework": {
            "active_unit.spec": "inline",
            "authorization.current": "inline",
            "unresolved_items": "inline",
            "project.constraints": "excerpt",
            "applicable_decisions": "excerpt",
            "dependency_outputs": "on_demand",
            "previous_rounds": "excerpt",
            "discussions": "on_demand",
            "raw_logs": "on_demand",
            "full_architecture": "on_demand",
        },
        "debate": {
            "active_unit.spec": "excerpt",
            "authorization.current": "inline",
            "unresolved_items": "excerpt",
            "project.constraints": "inline",
            "applicable_decisions": "inline",
            "dependency_outputs": "on_demand",
            "previous_rounds": "on_demand",
            "discussions": "excerpt",
            "raw_logs": "on_demand",
            "full_architecture": "on_demand",
        },
    },
}


def validate_context_policy(policy: dict[str, Any]) -> None:
    """Validate policy data structure against context-policy schema rules."""
    if not isinstance(policy, dict):
        raise ValueError("Context policy must be a JSON object")
    if policy.get("schema_version") != 1:
        raise ValueError(f"Context policy schema_version must be 1, got {policy.get('schema_version')}")

    classes = policy.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("Context policy 'classes' must be a non-empty array")
    for cls in classes:
        if cls not in VALID_POLICY_CLASSES:
            raise ValueError(f"Invalid class '{cls}' in context policy")
    if len(classes) != len(set(classes)):
        raise ValueError("Context policy 'classes' must contain unique items")

    phases = policy.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("Context policy 'phases' must be an object")
    for req_phase in VALID_POLICY_PHASES:
        if req_phase not in phases:
            raise ValueError(f"Missing required phase '{req_phase}' in context policy")
        phase_map = phases[req_phase]
        if not isinstance(phase_map, dict):
            raise ValueError(f"Phase '{req_phase}' policy must be an object")
        for k, v in phase_map.items():
            if k not in VALID_POLICY_CLASSES:
                raise ValueError(f"Invalid class '{k}' in phase '{req_phase}'")
            if v not in VALID_POLICY_DELIVERIES:
                raise ValueError(f"Invalid delivery mode '{v}' for class '{k}' in phase '{req_phase}'")

    if "bootstrap_on_demand_budget" in policy:
        budget = policy["bootstrap_on_demand_budget"]
        if not isinstance(budget, int) or budget < 0:
            raise ValueError(
                f"Context policy 'bootstrap_on_demand_budget' must be an integer >= 0, got {budget}"
            )


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract simple key-value YAML frontmatter from top of Markdown file."""
    data: dict[str, Any] = {}
    lines = text.splitlines()
    if not lines:
        return data

    idx = 0
    if lines[0].strip() == "---":
        idx = 1

    while idx < len(lines):
        line = lines[idx]
        if line.strip() in ("---", "...") or line.startswith("#"):
            break
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            # Handle simple arrays like [a, b]
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                if not inner:
                    data[key] = []
                else:
                    data[key] = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
            elif val.isdigit():
                data[key] = int(val)
            elif val.lower() == "true":
                data[key] = True
            elif val.lower() == "false":
                data[key] = False
            else:
                data[key] = val
        idx += 1
    return data


def find_active_task(repo_root: Path, explicit_task: Optional[str] = None) -> Path:
    """Find the active task file from canonical roots, strictly ignoring evidence/ snapshots (AC17)."""
    if explicit_task:
        task_path = Path(explicit_task)
        if is_archived_evidence_path(task_path):
            raise PermissionError(f"Prohibited access to archived evidence: {task_path}")
        if not task_path.is_file():
            raise FileNotFoundError(f"Specified task file not found: {task_path}")
        return task_path

    roots = discover_active_roots(repo_root)
    status_path = roots.get("status")
    if not status_path or not status_path.is_file():
        raise FileNotFoundError(f"STATUS.md not found at {status_path}")

    status_text = status_path.read_text(encoding="utf-8")
    status_fm = parse_frontmatter(status_text)
    active_ref = status_fm.get("active_work_ref")

    if active_ref and active_ref != "none" and "@" in active_ref:
        _, loc = active_ref.split("@", 1)
        loc_path = repo_root / loc
        if loc_path.is_file() and not is_archived_evidence_path(loc_path):
            return loc_path

    # Look for first ready task in tasks/ directory
    tasks_dir = repo_root / "_tl-orc" / "project" / "tasks"
    if tasks_dir.is_dir():
        for task_file in sorted(tasks_dir.glob("T*.md")):
            if is_archived_evidence_path(task_file):
                continue
            fm = parse_frontmatter(task_file.read_text(encoding="utf-8"))
            if fm.get("status") in ("ready", "in_progress"):
                return task_file

    raise FileNotFoundError("Could not find any active or ready task in canonical roots.")


def resolve_phase(task_fm: dict[str, Any], explicit_phase: Optional[str] = None) -> str:
    """Infer or accept the current phase."""
    if explicit_phase:
        return explicit_phase
    status = task_fm.get("status", "ready")
    if status == "ready":
        return "implementation"
    elif status == "draft":
        return "planning"
    return "implementation"


def resolve_work_method(repo_root: Path, task_fm: dict[str, Any]) -> str:
    """
    Resolve work_method dynamically:
    1. Check _tl-orc/PROJECT.md frontmatter for work_method
    2. Check task frontmatter for method or work_method
    3. Fallback to native
    """
    project_path = repo_root / "_tl-orc" / "PROJECT.md"
    if project_path.is_file():
        proj_fm = parse_frontmatter(project_path.read_text(encoding="utf-8"))
        if proj_fm.get("work_method"):
            return str(proj_fm["work_method"])
    if task_fm.get("method"):
        return str(task_fm["method"])
    if task_fm.get("work_method"):
        return str(task_fm["work_method"])
    return "native"


def resolve_effective_authors(task_fm: dict[str, Any]) -> list[str]:
    """Extract declared authors from task frontmatter, or empty list if none."""
    authors = task_fm.get("authors") or task_fm.get("effective_authors")
    if isinstance(authors, list):
        return [str(a) for a in authors if a]
    elif isinstance(authors, str) and authors.strip():
        return [authors.strip()]
    return []


def extract_open_review_items(review_content: str) -> list[str]:
    """Derive explicitly open Native review items from the review source."""
    open_items: list[str] = []
    for raw_line in review_content.splitlines():
        line = raw_line.strip()
        checkbox = re.match(r"[-*]\s+\[\s\]\s+(.+)", line)
        if checkbox:
            item = checkbox.group(1).strip()
        elif (
            re.search(r"\b(?:action item|open|pending|changes_requested)\b", line, re.IGNORECASE)
            and not re.search(
                r"\b(?:0\s+action[_ ]items?|correct(?:ed|ion)?|resolved|closed|approved|"
                r"ratif(?:ied|ication)|complete(?:d)?)\b|✅|\[x\]",
                line,
                re.IGNORECASE,
            )
        ):
            item_match = re.search(r"\b(?:R|AI)[-_]?\d+\b.*", line)
            item = item_match.group(0).strip() if item_match else ""
        else:
            item = ""
        if item and item not in open_items:
            open_items.append(item)
    return open_items


def extract_pending_acceptance_criteria(criteria_content: str) -> list[str]:
    """Derive uncompleted BMAD acceptance criteria from their published section."""
    pending: list[str] = []
    for raw_line in criteria_content.splitlines():
        line = raw_line.strip()
        unchecked = re.match(r"[-*]\s+\[\s\]\s+(.+)", line)
        criterion = re.match(r"(?:[-*]\s+)?((?:AC|US)[-_]?\d+\b.*)", line, re.IGNORECASE)
        if unchecked:
            item = unchecked.group(1).strip()
        elif criterion and not re.search(r"\[x\]|✅|\b(?:done|complete(?:d)?)\b", line, re.IGNORECASE):
            item = criterion.group(1).strip()
        else:
            item = ""
        if item and item not in pending:
            pending.append(item)
    return pending


def derive_next_action(task_id: str, method: str, status: str, phase: str) -> str:
    """Describe the requested phase from the active unit's published state."""
    if status == "done":
        return f"No execution action: {method} unit {task_id} is done."
    return f"Execute {phase} phase for {method} unit {task_id} (status: {status})."


def check_bootstrap_budget(
    reads_count: int,
    max_budget: int = DEFAULT_BOOTSTRAP_BUDGET,
) -> tuple[bool, str]:
    """
    Evaluate whether on-demand bootstrap reads exceeded the allocated budget (AC06).
    Returns (True, message) if within budget, or (False, 'STOP: bootstrap_budget_exceeded: ...').
    """
    if reads_count < 0:
        return False, "Invalid negative reads count"
    if reads_count > max_budget:
        return (
            False,
            f"STOP: bootstrap_budget_exceeded (reads: {reads_count}, max_budget: {max_budget})",
        )
    return True, f"OK: bootstrap budget preserved ({reads_count}/{max_budget} reads used)"


def verify_resume_manifest_structured(
    manifest: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """
    Verify pre-dispatch integrity of manifest against current disk content (AC03, AC15).
    Inspects each source declared in manifest["sources"], reads section with select_section,
    computes canonical digest (masking volatile fields for frontmatter selectors),
    and compares to manifest digest.
    Returns dictionary with:
      - status: 'verified', 'stale_package_rejected', 'source_missing', or 'schema_invalid'
      - ok: bool
      - checked_sources_count: int
      - errors: list of error strings
      - mismatches: list of detailed mismatch dictionaries
    """
    errors: list[str] = []
    mismatches: list[dict[str, Any]] = []

    if not isinstance(manifest, dict):
        errors.append("Manifest must be a JSON object.")
        return {
            "status": "schema_invalid",
            "ok": False,
            "checked_sources_count": 0,
            "errors": errors,
            "mismatches": [],
        }

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("Manifest contains no sources to verify.")
        return {
            "status": "schema_invalid",
            "ok": False,
            "checked_sources_count": 0,
            "errors": errors,
            "mismatches": [],
        }

    has_missing_source = False
    has_mismatch = False

    for src in sources:
        if not isinstance(src, dict):
            errors.append(f"Invalid source entry (not an object): {src}")
            has_mismatch = True
            continue

        rel_path = src.get("path")
        selector = src.get("selector")
        expected_digest = src.get("digest")

        if not rel_path or not selector or not expected_digest:
            errors.append(f"Invalid source entry (missing path/selector/digest): {src}")
            has_mismatch = True
            mismatches.append({"source": src, "type": "invalid_source_entry"})
            continue

        src_file = repo_root / rel_path
        try:
            resolved_root = repo_root.resolve()
            if not src_file.resolve().is_relative_to(resolved_root):
                errors.append(f"Integrity check failed: source path escapes repository: '{rel_path}'")
                has_missing_source = True
                mismatches.append({"path": rel_path, "type": "path_escapes_repository"})
                continue
        except (OSError, ValueError):
            errors.append(f"Integrity check failed: source path could not be resolved: '{rel_path}'")
            has_missing_source = True
            mismatches.append({"path": rel_path, "type": "path_resolution_error"})
            continue

        if not src_file.is_file():
            errors.append(f"Integrity check failed: source file '{rel_path}' not found")
            has_missing_source = True
            mismatches.append({"path": rel_path, "type": "file_not_found"})
            continue

        try:
            content = src_file.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Integrity check failed: could not read '{rel_path}': {exc}")
            has_missing_source = True
            mismatches.append({"path": rel_path, "type": "read_error", "error": str(exc)})
            continue

        if selector == "frontmatter":
            try:
                sec = select_section(content, "frontmatter")
                section_content = sec.content
            except SelectorNotFoundError:
                section_content = content

            actual_digest = compute_sha256(mask_volatile_fields(section_content))
        else:
            try:
                sec = select_section(content, selector)
                actual_digest = sec.sha256
            except SelectorNotFoundError:
                errors.append(f"Integrity check failed: selector '{selector}' not found in '{rel_path}'")
                has_mismatch = True
                mismatches.append({"path": rel_path, "selector": selector, "type": "selector_not_found"})
                continue
            except Exception as exc:
                errors.append(f"Integrity check failed: error selecting '{selector}' in '{rel_path}': {exc}")
                has_mismatch = True
                mismatches.append({"path": rel_path, "selector": selector, "type": "selection_error", "error": str(exc)})
                continue

        if actual_digest != expected_digest:
            errors.append(
                f"Integrity check failed: digest mismatch for {rel_path} @ {selector}. "
                f"Expected {expected_digest}, got {actual_digest}"
            )
            has_mismatch = True
            mismatches.append({
                "path": rel_path,
                "selector": selector,
                "expected_digest": expected_digest,
                "actual_digest": actual_digest,
                "type": "digest_mismatch",
            })

    if has_missing_source:
        status = "source_missing"
    elif has_mismatch:
        status = "stale_package_rejected"
    elif errors:
        status = "schema_invalid"
    else:
        status = "verified"

    return {
        "status": status,
        "ok": (status == "verified"),
        "checked_sources_count": len(sources),
        "errors": errors,
        "mismatches": mismatches,
    }


def verify_resume_manifest(manifest: dict[str, Any], repo_root: Path) -> tuple[bool, list[str]]:
    """
    Verify pre-dispatch integrity of manifest against current disk content (AC15).
    Returns (True, []) or (False, list_of_errors).
    """
    res = verify_resume_manifest_structured(manifest, repo_root)
    return res["ok"], res["errors"]


def generate_resume_manifest(
    repo_root: Path,
    task_path: Path,
    phase: str,
    policy_path: Optional[Path] = None,
    strict_integrity: bool = True,
    generated_at: Optional[str] = None,
    generator_version: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build the deterministic resume manifest data.
    """
    # Load and validate policy
    if policy_path:
        policy_data = json.loads(policy_path.read_text(encoding="utf-8"))
        validate_context_policy(policy_data)
        policy = policy_data
    else:
        policy = DEFAULT_CONTEXT_POLICY

    phase_policy = policy.get("phases", {}).get(phase, {})

    task_text = task_path.read_text(encoding="utf-8")
    task_fm = parse_frontmatter(task_text)
    task_id = str(task_fm.get("id", task_path.stem.split("-")[0]))
    method = resolve_work_method(repo_root, task_fm)
    spec_revision = str(task_fm.get("spec_revision", "unknown"))
    state_revision = int(task_fm.get("state_revision", 0))
    content_id = task_fm.get("content_id")
    effective_authors = resolve_effective_authors(task_fm)

    try:
        rel_task_path = str(task_path.relative_to(repo_root))
    except ValueError:
        rel_task_path = str(task_path)

    active_work_ref = f"{method}/task/{task_id}@{rel_task_path}"

    # Resolve the active-unit convention from the configured method.  The
    # source entry and resolved-context entry share the same selector/digest.
    active_selector = "## Spec" if method == "native" else "### Acceptance criteria"
    active_section = select_section(task_text, active_selector)
    active_digest = active_section.sha256

    sources: list[dict[str, str]] = [{
        "path": rel_task_path,
        "selector": active_selector,
        "digest": active_digest,
    }]

    def add_source(path: str, selector: str, digest: str) -> None:
        entry = {"path": path, "selector": selector, "digest": digest}
        if entry not in sources:
            sources.append(entry)

    # Add active task frontmatter (AC02, Spec 4)
    try:
        task_fm_sec = select_section(task_text, "frontmatter")
        task_fm_digest = compute_sha256(mask_volatile_fields(task_fm_sec.content))
    except SelectorNotFoundError:
        task_fm_digest = compute_sha256(mask_volatile_fields(task_text))
    add_source(rel_task_path, "frontmatter", task_fm_digest)

    # Add STATUS.md source with volatile fields masked
    status_path = repo_root / "_tl-orc" / "project" / "STATUS.md"
    if status_path.is_file():
        status_text = status_path.read_text(encoding="utf-8")
        try:
            status_sec = select_section(status_text, "frontmatter")
            status_digest = compute_sha256(mask_volatile_fields(status_sec.content))
            add_source("_tl-orc/project/STATUS.md", "frontmatter", status_digest)
        except SelectorNotFoundError:
            pass

    # Add PROJECT.md source
    project_path = repo_root / "_tl-orc" / "PROJECT.md"
    if project_path.is_file():
        proj_text = project_path.read_text(encoding="utf-8")
        try:
            proj_sec = select_section(proj_text, "frontmatter")
            proj_digest = compute_sha256(mask_volatile_fields(proj_sec.content))
        except SelectorNotFoundError:
            proj_digest = compute_sha256(mask_volatile_fields(proj_text))
        add_source("_tl-orc/PROJECT.md", "frontmatter", proj_digest)

    review_section = None
    if method == "native":
        try:
            review_section = select_section(task_text, "## Review")
            add_source(rel_task_path, "## Review", review_section.sha256)
        except SelectorNotFoundError:
            review_section = None

    # Sort sources deterministically
    sources.sort(key=lambda s: (s["path"], s["selector"]))

    # Helper to find digest by source path
    def get_source_digest(p: str, selector: Optional[str] = None, default: str = "unknown") -> str:
        for s in sources:
            if s["path"] == p and (selector is None or s["selector"] == selector):
                return s["digest"]
        return default

    # Resolve context guided by method and phase policy (AC07)
    resolved_context: list[dict[str, Any]] = []

    if method == "native":
        spec_delivery = phase_policy.get("active_unit.spec", "inline")
        auth_delivery = phase_policy.get("authorization.current", "inline")
        proj_delivery = phase_policy.get("project.constraints", "excerpt")
        unres_delivery = phase_policy.get("unresolved_items", "excerpt")

        resolved_context.append({
            "artifact": "active_unit.spec",
            "path": rel_task_path,
            "selector": "## Spec",
            "digest": active_digest,
            "delivery": spec_delivery,
            "reason": "Execution target specification",
        })
        resolved_context.append({
            "artifact": "authorization.current",
            "path": "_tl-orc/project/STATUS.md",
            "selector": "frontmatter",
            "digest": get_source_digest("_tl-orc/project/STATUS.md"),
            "delivery": auth_delivery,
            "reason": "Current authorization and coordinator state",
        })
        resolved_context.append({
            "artifact": "project.constraints",
            "path": "_tl-orc/PROJECT.md",
            "selector": "frontmatter",
            "digest": get_source_digest("_tl-orc/PROJECT.md"),
            "delivery": proj_delivery,
            "reason": "Project rules and catalog constraints",
        })
        if review_section is not None:
            resolved_context.append({
                "artifact": "unresolved_items",
                "path": rel_task_path,
                "selector": "## Review",
                "digest": review_section.sha256,
                "delivery": unres_delivery,
                "reason": "Unit review record and outstanding action items",
            })
        open_items = extract_open_review_items(review_section.content) if review_section else []
    else:  # BMAD or other method
        spec_delivery = phase_policy.get("active_unit.spec", "inline")
        auth_delivery = phase_policy.get("authorization.current", "inline")
        proj_delivery = phase_policy.get("project.constraints", "excerpt")

        resolved_context.append({
            "artifact": "active_unit.spec",
            "path": rel_task_path,
            "selector": "### Acceptance criteria",
            "digest": active_digest,
            "delivery": spec_delivery,
            "reason": "BMAD story acceptance criteria",
        })
        resolved_context.append({
            "artifact": "authorization.current",
            "path": "_tl-orc/project/STATUS.md",
            "selector": "frontmatter",
            "digest": get_source_digest("_tl-orc/project/STATUS.md"),
            "delivery": auth_delivery,
            "reason": "Sprint coordination state",
        })
        resolved_context.append({
            "artifact": "project.constraints",
            "path": "_tl-orc/PROJECT.md",
            "selector": "frontmatter",
            "digest": get_source_digest("_tl-orc/PROJECT.md"),
            "delivery": proj_delivery,
            "reason": "Project rules and governance",
        })
        open_items = extract_pending_acceptance_criteria(active_section.content)

    # Sort resolved_context deterministically
    resolved_context.sort(key=lambda r: (r["artifact"], r["path"]))

    next_action = derive_next_action(task_id, method, str(task_fm.get("status", "unknown")), phase)

    if generated_at is None:
        generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
        "schema_version": 1,
        "active_work_ref": active_work_ref,
        "phase": phase,
        "spec_revision": spec_revision,
        "state_revision": state_revision,
        "content_id": content_id,
        "generated_at": generated_at,
        "generator_version": generator_version or DEFAULT_GENERATOR_VERSION,
        "sources": sources,
        "resolved_context": resolved_context,
        "effective_authors": effective_authors,
        "open_items": open_items,
        "next_action": next_action,
        "always_read": [
            {
                "path": "_tl-orc/project/STATUS.md",
                "selector": "frontmatter",
                "reason": "Volatile coordinator block inside frontmatter must be read unconditionally",
            }
        ],
        "bootstrap_budget": {
            "max_on_demand_reads": policy.get("bootstrap_on_demand_budget", DEFAULT_BOOTSTRAP_BUDGET),
            "unit": "on_demand_reads",
        },
    }

    # Pre-dispatch Integrity Gate (AC15)
    if strict_integrity:
        ok, errors = verify_resume_manifest(manifest, repo_root)
        if not ok:
            raise ValueError("; ".join(errors))

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic resume manifest (resume.json) with strict integrity gate."
    )
    parser.add_argument("--task", "-t", help="Path to active task file (optional; discovered if omitted).")
    parser.add_argument("--policy", "-p", help="Path to context policy manifest.")
    parser.add_argument(
        "--phase",
        choices=["planning", "implementation", "review", "rework", "debate"],
        help="Execution phase (inferred if omitted).",
    )
    parser.add_argument("--output", "-o", help="Output file path (default: stdout).")
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Disable strict pre-dispatch integrity verification.",
    )
    parser.add_argument(
        "--verify",
        help="Verify pre-dispatch integrity of an existing resume manifest JSON file against disk.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON (used with --verify or --check-bootstrap-budget).",
    )
    parser.add_argument(
        "--check-bootstrap-budget",
        type=int,
        metavar="READS_COUNT",
        help="Check if on-demand reads count exceeds bootstrap budget.",
    )
    parser.add_argument(
        "--max-budget",
        type=int,
        default=DEFAULT_BOOTSTRAP_BUDGET,
        help=f"Max bootstrap budget for --check-bootstrap-budget (default: {DEFAULT_BOOTSTRAP_BUDGET}).",
    )
    parser.add_argument(
        "--generated-at",
        help="Explicit ISO timestamp for generated_at (default: current UTC timestamp).",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()

    if args.check_bootstrap_budget is not None:
        ok, msg = check_bootstrap_budget(args.check_bootstrap_budget, args.max_budget)
        if args.json:
            result = {
                "status": "verified" if ok else "bootstrap_budget_exceeded",
                "ok": ok,
                "reads_count": args.check_bootstrap_budget,
                "max_budget": args.max_budget,
                "message": msg,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if ok:
                print(msg)
            else:
                print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(0 if ok else 1)

    if args.verify:
        verify_path = Path(args.verify)
        if not verify_path.is_file():
            err_msg = f"manifest file to verify not found: {verify_path}"
            if args.json:
                print(json.dumps({
                    "status": "source_missing",
                    "ok": False,
                    "checked_sources_count": 0,
                    "errors": [err_msg],
                    "mismatches": [{"path": str(verify_path), "type": "file_not_found"}]
                }, indent=2, sort_keys=True))
            else:
                print(f"ERROR: {err_msg}", file=sys.stderr)
            sys.exit(1)
        try:
            manifest_to_verify = json.loads(verify_path.read_text(encoding="utf-8"))
        except Exception as exc:
            err_msg = f"could not parse manifest JSON: {exc}"
            if args.json:
                print(json.dumps({
                    "status": "schema_invalid",
                    "ok": False,
                    "checked_sources_count": 0,
                    "errors": [err_msg],
                    "mismatches": []
                }, indent=2, sort_keys=True))
            else:
                print(f"ERROR: {err_msg}", file=sys.stderr)
            sys.exit(1)

        result = verify_resume_manifest_structured(manifest_to_verify, repo_root)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
            sys.exit(0 if result["ok"] else 1)
        else:
            if not result["ok"]:
                for err in result["errors"]:
                    print(f"ERROR: {err}", file=sys.stderr)
                sys.exit(1)
            print("OK: Resume manifest integrity verified against disk.")
            sys.exit(0)

    try:
        task_path = find_active_task(repo_root, args.task)
        task_text = task_path.read_text(encoding="utf-8")
        task_fm = parse_frontmatter(task_text)
        phase = resolve_phase(task_fm, args.phase)
        policy_path = Path(args.policy) if args.policy else None

        manifest = generate_resume_manifest(
            repo_root=repo_root,
            task_path=task_path,
            phase=phase,
            policy_path=policy_path,
            strict_integrity=not args.no_strict,
            generated_at=args.generated_at,
        )
    except Exception as exc:
        print(f"ERROR: resume_generate failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Output deterministically formatted JSON (sorted keys, 2-space indent, single trailing \n)
    formatted = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    if args.output and args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted, encoding="utf-8")
    else:
        sys.stdout.write(formatted)

    sys.exit(0)


if __name__ == "__main__":
    main()
