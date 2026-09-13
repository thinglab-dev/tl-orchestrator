#!/usr/bin/env python3
"""Validate classification results for tl-orchestrator (Dual v2 / v3 support)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VALID_PHASES = {"debate", "planning", "implementation", "review", "rework"}
VALID_CONFIDENCES = {"high", "medium", "low"}
VALID_ROLES = {"planner", "maker", "checker", "searcher", "advisor"}
VALID_TIERS = {"simple", "normal", "heavy"}
VALID_HARNESSES = {"codex", "claude", "agy"}
VALID_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
VALID_COST_BASES = {"local_observed", "official_task_proxy", "token_price_only", "unknown"}
VALID_SELECTION_STATUSES = {"conclusive", "underdetermined", "awaiting_operator", "infeasible"}
VALID_TECHNICAL_ADEQUACIES = {"sufficient", "insufficient", "uncertain"}
VALID_DISPATCH_ROLES = {"primary", "fallback", "unassigned"}


def validate_v2_role(role_name: str, role_data: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(role_data, dict):
        errors.append(f"roles.{role_name} must be an object")
        return
    for req in ("tier", "reason", "candidates"):
        if req not in role_data:
            errors.append(f"roles.{role_name} missing required key: {req}")
    tier = role_data.get("tier")
    if tier not in VALID_TIERS:
        errors.append(f"roles.{role_name}.tier invalid: {tier}")
    reason = role_data.get("reason")
    if not isinstance(reason, str) or not reason:
        errors.append(f"roles.{role_name}.reason must be non-empty string")
    candidates = role_data.get("candidates")
    if not isinstance(candidates, list) or not (1 <= len(candidates) <= 3):
        errors.append(f"roles.{role_name}.candidates must be array of 1 to 3 items")
        return
    for idx, c in enumerate(candidates):
        if not isinstance(c, dict):
            errors.append(f"roles.{role_name}.candidates[{idx}] must be an object")
            continue
        for req in ("harness", "model", "effort", "evidence_ids", "cost_basis", "reason"):
            if req not in c:
                errors.append(f"roles.{role_name}.candidates[{idx}] missing key: {req}")
        harness = c.get("harness")
        if harness not in VALID_HARNESSES:
            errors.append(f"roles.{role_name}.candidates[{idx}].harness invalid: {harness}")
        model = c.get("model")
        effort = c.get("effort")
        if model is None:
            if effort is not None:
                errors.append(f"roles.{role_name}.candidates[{idx}]: model is null but effort is not null")
        else:
            if not isinstance(model, str) or not model:
                errors.append(f"roles.{role_name}.candidates[{idx}].model must be non-empty string or null")
            if effort not in VALID_EFFORTS:
                errors.append(f"roles.{role_name}.candidates[{idx}].effort invalid: {effort}")
        ev_ids = c.get("evidence_ids")
        if not isinstance(ev_ids, list):
            errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids must be array")
        cost_basis = c.get("cost_basis")
        if cost_basis not in VALID_COST_BASES:
            errors.append(f"roles.{role_name}.candidates[{idx}].cost_basis invalid: {cost_basis}")
        elif cost_basis != "unknown" and isinstance(ev_ids, list) and len(ev_ids) < 1:
            errors.append(f"roles.{role_name}.candidates[{idx}]: evidence_ids required when cost_basis != unknown")


def validate_v3_role(role_name: str, role_data: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(role_data, dict):
        errors.append(f"roles.{role_name} must be an object")
        return
    for req in ("tier", "selection_status", "reason", "tie_break_applied", "evaluations", "candidates"):
        if req not in role_data:
            errors.append(f"roles.{role_name} missing required key: {req}")
    tier = role_data.get("tier")
    if tier not in VALID_TIERS:
        errors.append(f"roles.{role_name}.tier invalid: {tier}")
    status = role_data.get("selection_status")
    if status not in VALID_SELECTION_STATUSES:
        errors.append(f"roles.{role_name}.selection_status invalid: {status}")
    reason = role_data.get("reason")
    if not isinstance(reason, str) or not reason:
        errors.append(f"roles.{role_name}.reason must be non-empty string")
    tie_break = role_data.get("tie_break_applied")
    if tie_break is not None and not isinstance(tie_break, str):
        errors.append(f"roles.{role_name}.tie_break_applied must be string or null")

    evaluations = role_data.get("evaluations")
    eval_by_pair: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not isinstance(evaluations, list) or len(evaluations) < 1:
        errors.append(f"roles.{role_name}.evaluations must be non-empty array")
    else:
        for idx, ev in enumerate(evaluations):
            if not isinstance(ev, dict):
                errors.append(f"roles.{role_name}.evaluations[{idx}] must be an object")
                continue
            for req in ("harness", "model", "effort", "catalog_eligible", "technical_adequacy", "dispatchable", "evidence_ids", "uncertainty", "reason"):
                if req not in ev:
                    errors.append(f"roles.{role_name}.evaluations[{idx}] missing key: {req}")
            harness = ev.get("harness")
            if harness not in VALID_HARNESSES:
                errors.append(f"roles.{role_name}.evaluations[{idx}].harness invalid: {harness}")
            model = ev.get("model")
            effort = ev.get("effort")
            if model is None:
                if effort is not None:
                    errors.append(f"roles.{role_name}.evaluations[{idx}]: model is null but effort is not null")
            else:
                if not isinstance(model, str) or not model:
                    errors.append(f"roles.{role_name}.evaluations[{idx}].model must be non-empty string or null")
                if effort not in VALID_EFFORTS:
                    errors.append(f"roles.{role_name}.evaluations[{idx}].effort invalid: {effort}")
            cat_elig = ev.get("catalog_eligible")
            if not isinstance(cat_elig, bool):
                errors.append(f"roles.{role_name}.evaluations[{idx}].catalog_eligible must be boolean")
            tech_adeq = ev.get("technical_adequacy")
            if tech_adeq not in VALID_TECHNICAL_ADEQUACIES:
                errors.append(f"roles.{role_name}.evaluations[{idx}].technical_adequacy invalid: {tech_adeq}")
            dispatchable = ev.get("dispatchable")
            if not isinstance(dispatchable, bool):
                errors.append(f"roles.{role_name}.evaluations[{idx}].dispatchable must be boolean")
            else:
                if dispatchable and not (tech_adeq == "sufficient" and cat_elig is True):
                    errors.append(f"roles.{role_name}.evaluations[{idx}]: dispatchable cannot be true unless technical_adequacy==sufficient and catalog_eligible==true")
                if tech_adeq in ("insufficient", "uncertain") and dispatchable:
                    errors.append(f"roles.{role_name}.evaluations[{idx}]: insufficient/uncertain cannot be dispatchable")
            if model and effort:
                eval_by_pair[(harness, model, effort)] = ev

    candidates = role_data.get("candidates")
    if not isinstance(candidates, list):
        errors.append(f"roles.{role_name}.candidates must be an array")
        return

    # Invariants R7 & R10: each candidate must have model/effort non-null and match a sufficient evaluation
    for idx, c in enumerate(candidates):
        if not isinstance(c, dict):
            errors.append(f"roles.{role_name}.candidates[{idx}] must be an object")
            continue
        for req in ("harness", "model", "effort", "dispatch_role", "evidence_ids", "cost_basis", "reason"):
            if req not in c:
                errors.append(f"roles.{role_name}.candidates[{idx}] missing key: {req}")
        harness = c.get("harness")
        model = c.get("model")
        effort = c.get("effort")
        if harness not in VALID_HARNESSES:
            errors.append(f"roles.{role_name}.candidates[{idx}].harness invalid: {harness}")
        if not isinstance(model, str) or not model:
            errors.append(f"roles.{role_name}.candidates[{idx}].model cannot be null or empty in v3 candidates[]")
        if effort not in VALID_EFFORTS:
            errors.append(f"roles.{role_name}.candidates[{idx}].effort invalid: {effort}")
        dispatch_role = c.get("dispatch_role")
        if dispatch_role not in VALID_DISPATCH_ROLES:
            errors.append(f"roles.{role_name}.candidates[{idx}].dispatch_role invalid: {dispatch_role}")
        ev_ids = c.get("evidence_ids")
        cost_basis = c.get("cost_basis")
        if cost_basis not in VALID_COST_BASES:
            errors.append(f"roles.{role_name}.candidates[{idx}].cost_basis invalid: {cost_basis}")
        elif cost_basis != "unknown" and isinstance(ev_ids, list) and len(ev_ids) < 1:
            errors.append(f"roles.{role_name}.candidates[{idx}]: evidence_ids required when cost_basis != unknown")
        # Check against evaluations
        if model and effort:
            matching_ev = eval_by_pair.get((harness, model, effort))
            if matching_ev is None:
                errors.append(f"roles.{role_name}.candidates[{idx}] ({harness}/{model}/{effort}) has no matching evaluation in evaluations[]")
            else:
                if matching_ev.get("technical_adequacy") != "sufficient" or matching_ev.get("dispatchable") is not True:
                    errors.append(f"roles.{role_name}.candidates[{idx}] ({harness}/{model}/{effort}) evaluated as insufficient/uncertain or not dispatchable")

    # Invariant R18: State matrix
    if status == "conclusive":
        if tie_break is not None:
            errors.append(f"roles.{role_name}: conclusive status requires tie_break_applied to be null")
        if len(candidates) < 1:
            errors.append(f"roles.{role_name}: conclusive status requires at least 1 candidate")
        else:
            if candidates[0].get("dispatch_role") != "primary":
                errors.append(f"roles.{role_name}: conclusive status requires candidates[0].dispatch_role == \"primary\"")
            for idx in range(1, len(candidates)):
                if candidates[idx].get("dispatch_role") != "fallback":
                    errors.append(f"roles.{role_name}: candidate[{idx}] must have dispatch_role == \"fallback\" in conclusive status")
    elif status == "underdetermined":
        if not isinstance(tie_break, str) or not tie_break:
            errors.append(f"roles.{role_name}: underdetermined status requires non-empty tie_break_applied")
        if len(candidates) < 1:
            errors.append(f"roles.{role_name}: underdetermined status requires at least 1 candidate")
        else:
            if candidates[0].get("dispatch_role") != "primary":
                errors.append(f"roles.{role_name}: underdetermined status requires candidates[0].dispatch_role == \"primary\"")
            for idx in range(1, len(candidates)):
                if candidates[idx].get("dispatch_role") != "fallback":
                    errors.append(f"roles.{role_name}: candidate[{idx}] must have dispatch_role == \"fallback\" in underdetermined status")
    elif status == "awaiting_operator":
        if len(candidates) < 2:
            errors.append(f"roles.{role_name}: awaiting_operator status requires at least 2 candidates")
        for idx, c in enumerate(candidates):
            if c.get("dispatch_role") != "unassigned":
                errors.append(f"roles.{role_name}: candidate[{idx}] must have dispatch_role == \"unassigned\" in awaiting_operator status")
    elif status == "infeasible":
        if tie_break is not None:
            errors.append(f"roles.{role_name}: infeasible status requires tie_break_applied to be null")
        if len(candidates) != 0:
            errors.append(f"roles.{role_name}: infeasible status requires candidates[] to be empty")


def validate_classification_data(
    data: Any,
    expected_story: str | None = None,
    expected_phase: str | None = None,
    expected_version: int | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["classification result must be a JSON object"]

    # Basic root keys
    for req in (
        "schema_version",
        "story_id",
        "phase",
        "context_revision",
        "catalog_revision",
        "confidence",
        "facts",
        "uncertainties",
        "reclassify_when",
        "roles",
    ):
        if req not in data:
            errors.append(f"missing root required key: {req}")

    version = data.get("schema_version")
    if version not in (2, 3):
        errors.append(f"unsupported schema_version: {version} (must be 2 or 3)")
        return False, errors

    if expected_version is not None and version != expected_version:
        errors.append(f"expected schema_version {expected_version}, got {version}")

    story_id = data.get("story_id")
    if story_id is not None and (not isinstance(story_id, str) or not story_id):
        errors.append("story_id must be non-empty string or null")
    if expected_story is not None and story_id != expected_story:
        errors.append(f"expected story_id {expected_story}, got {story_id}")

    phase = data.get("phase")
    if phase not in VALID_PHASES:
        errors.append(f"invalid phase: {phase}")
    if expected_phase is not None and phase != expected_phase:
        errors.append(f"expected phase {expected_phase}, got {phase}")

    for rev_key in ("context_revision", "catalog_revision"):
        val = data.get(rev_key)
        if not isinstance(val, str) or not val:
            errors.append(f"{rev_key} must be non-empty string")

    confidence = data.get("confidence")
    if confidence not in VALID_CONFIDENCES:
        errors.append(f"invalid confidence: {confidence}")

    for arr_key in ("facts", "uncertainties", "reclassify_when"):
        arr = data.get(arr_key)
        if not isinstance(arr, list):
            errors.append(f"{arr_key} must be an array")
        elif arr_key in ("facts", "reclassify_when") and len(arr) < 1:
            errors.append(f"{arr_key} must contain at least 1 item")

    roles = data.get("roles")
    if not isinstance(roles, dict) or len(roles) < 1:
        errors.append("roles must be non-empty object")
    else:
        for role_name, role_data in roles.items():
            if role_name not in VALID_ROLES:
                errors.append(f"unsupported role name: {role_name}")
                continue
            if version == 2:
                validate_v2_role(role_name, role_data, errors)
            elif version == 3:
                validate_v3_role(role_name, role_data, errors)

    return len(errors) == 0, errors


def validate_classification_file(
    file_path: Path | str,
    expected_story: str | None = None,
    expected_phase: str | None = None,
    expected_version: int | None = None,
) -> tuple[bool, list[str]]:
    path = Path(file_path)
    if not path.is_file():
        return False, [f"file not found: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"failed to parse JSON in {path}: {exc}"]
    return validate_classification_data(
        data,
        expected_story=expected_story,
        expected_phase=expected_phase,
        expected_version=expected_version,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tl-orchestrator classification result (v2 or v3).")
    parser.add_argument("--file", "-f", required=True, help="Path to classification result JSON file")
    parser.add_argument("--story", help="Expected story_id")
    parser.add_argument("--phase", choices=list(VALID_PHASES), help="Expected phase")
    parser.add_argument("--schema-version", type=int, choices=[2, 3], help="Expected schema_version")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()
    valid, errors = validate_classification_file(
        args.file,
        expected_story=args.story,
        expected_phase=args.phase,
        expected_version=args.schema_version,
    )

    if args.format == "json":
        print(json.dumps({"valid": valid, "errors": errors}, indent=2))
    else:
        if valid:
            print(f"OK: classification result {args.file} is valid!")
        else:
            print(f"FAILED: classification result {args.file} is INVALID:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)

    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
