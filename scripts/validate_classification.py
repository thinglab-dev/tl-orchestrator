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
VALID_SELECTION_BASES = {"minimum_sufficient", "escalation", "pinned", "only_available"}
VALID_ESCALATION_REASONS = {
    "efficient_candidate_insufficient",
    "efficient_candidate_uncertain",
    "checker_family_independence",
    "operator_pinned",
    "pre_dispatch_unavailable",
    "proven_empirical_failure",
    "concrete_technical_necessity",
    "catalog_ineligible",
}
FORBIDDEN_OVERSELECTION_PATTERNS = [
    "frontier model",
    "modelo mais forte",
    "mais forte",
    "maior capacidade de raciocinio",
    "maior capacidade de raciocínio",
    "maior densidade arquitetural",
    "tier heavy exige modelo maximo",
    "tier heavy exige modelo máximo",
    "modelo de fronteira",
]

ROOT_ALLOWED_KEYS = {
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
}

V2_ROLE_ALLOWED_KEYS = {"tier", "reason", "candidates"}
V2_CANDIDATE_ALLOWED_KEYS = {
    "harness",
    "model",
    "effort",
    "evidence_ids",
    "cost_basis",
    "reason",
}

V3_ROLE_ALLOWED_KEYS = {
    "tier",
    "selection_status",
    "reason",
    "tie_break_applied",
    "evaluations",
    "candidates",
    "selection_basis",
    "escalation_reason",
}
V3_EVALUATION_ALLOWED_KEYS = {
    "harness",
    "model",
    "effort",
    "catalog_eligible",
    "technical_adequacy",
    "dispatchable",
    "cost_basis",
    "evidence_ids",
    "uncertainty",
    "reason",
}
V3_CANDIDATE_ALLOWED_KEYS = {
    "harness",
    "model",
    "effort",
    "dispatch_role",
    "degraded_same_family",
    "evidence_ids",
    "cost_basis",
    "reason",
}


def validate_v2_role(role_name: str, role_data: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(role_data, dict):
        errors.append(f"roles.{role_name} must be an object")
        return
    for k in role_data.keys():
        if k not in V2_ROLE_ALLOWED_KEYS:
            errors.append(f"roles.{role_name}: unexpected additional property '{k}'")
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
        for k in c.keys():
            if k not in V2_CANDIDATE_ALLOWED_KEYS:
                errors.append(f"roles.{role_name}.candidates[{idx}]: unexpected additional property '{k}'")
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
        else:
            for ev_id in ev_ids:
                if not isinstance(ev_id, str) or not ev_id:
                    errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids contains invalid item: {ev_id}")
            if len(ev_ids) != len(set(ev_ids)):
                errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids contains duplicate items")
        cost_basis = c.get("cost_basis")
        if cost_basis not in VALID_COST_BASES:
            errors.append(f"roles.{role_name}.candidates[{idx}].cost_basis invalid: {cost_basis}")
        elif cost_basis != "unknown" and isinstance(ev_ids, list) and len(ev_ids) < 1:
            errors.append(f"roles.{role_name}.candidates[{idx}]: evidence_ids required when cost_basis != unknown")
        c_reason = c.get("reason")
        if not isinstance(c_reason, str) or not c_reason:
            errors.append(f"roles.{role_name}.candidates[{idx}].reason must be non-empty string")


def validate_v3_role(role_name: str, role_data: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(role_data, dict):
        errors.append(f"roles.{role_name} must be an object")
        return
    for k in role_data.keys():
        if k not in V3_ROLE_ALLOWED_KEYS:
            errors.append(f"roles.{role_name}: unexpected additional property '{k}'")
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
    else:
        lower_reason = reason.lower()
        for pat in FORBIDDEN_OVERSELECTION_PATTERNS:
            if pat in lower_reason:
                errors.append(f"roles.{role_name}.reason contains forbidden over-selection phrase: '{pat}'")

    sel_basis = role_data.get("selection_basis")
    esc_reason = role_data.get("escalation_reason")

    if status in ("conclusive", "underdetermined"):
        if not sel_basis:
            errors.append(f"roles.{role_name}: selection_status '{status}' requires selection_basis")
        elif sel_basis not in VALID_SELECTION_BASES:
            errors.append(f"roles.{role_name}.selection_basis invalid: {sel_basis}")
    elif sel_basis is not None and sel_basis not in VALID_SELECTION_BASES:
        errors.append(f"roles.{role_name}.selection_basis invalid: {sel_basis}")

    if sel_basis == "escalation":
        if not esc_reason or not isinstance(esc_reason, str):
            errors.append(f"roles.{role_name}: selection_basis 'escalation' requires non-empty escalation_reason")
        elif esc_reason not in VALID_ESCALATION_REASONS:
            errors.append(f"roles.{role_name}.escalation_reason invalid enum value: '{esc_reason}'")
        else:
            lower_esc = esc_reason.lower()
            for pat in FORBIDDEN_OVERSELECTION_PATTERNS:
                if pat in lower_esc:
                    errors.append(f"roles.{role_name}.escalation_reason contains forbidden over-selection phrase: '{pat}'")
    else:
        if esc_reason is not None and not isinstance(esc_reason, str):
            errors.append(f"roles.{role_name}.escalation_reason must be string or null")
        elif esc_reason is not None and esc_reason != "":
            errors.append(f"roles.{role_name}: escalation_reason must be null when selection_basis is not 'escalation'")

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
            for k in ev.keys():
                if k not in V3_EVALUATION_ALLOWED_KEYS:
                    errors.append(f"roles.{role_name}.evaluations[{idx}]: unexpected additional property '{k}'")
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
            cost_basis = ev.get("cost_basis")
            if cost_basis is not None and cost_basis not in VALID_COST_BASES:
                errors.append(f"roles.{role_name}.evaluations[{idx}].cost_basis invalid: {cost_basis}")
            ev_ids = ev.get("evidence_ids")
            if not isinstance(ev_ids, list):
                errors.append(f"roles.{role_name}.evaluations[{idx}].evidence_ids must be array")
            else:
                for ev_id in ev_ids:
                    if not isinstance(ev_id, str) or not ev_id:
                        errors.append(f"roles.{role_name}.evaluations[{idx}].evidence_ids contains invalid item: {ev_id}")
                if len(ev_ids) != len(set(ev_ids)):
                    errors.append(f"roles.{role_name}.evaluations[{idx}].evidence_ids contains duplicate items")
            uncertainty = ev.get("uncertainty")
            if uncertainty is not None and not isinstance(uncertainty, str):
                errors.append(f"roles.{role_name}.evaluations[{idx}].uncertainty must be string or null")
            ev_reason = ev.get("reason")
            if not isinstance(ev_reason, str) or not ev_reason:
                errors.append(f"roles.{role_name}.evaluations[{idx}].reason must be non-empty string")
            else:
                lower_ev_reason = ev_reason.lower()
                for pat in FORBIDDEN_OVERSELECTION_PATTERNS:
                    if pat in lower_ev_reason:
                        errors.append(f"roles.{role_name}.evaluations[{idx}].reason contains forbidden over-selection phrase: '{pat}'")
            if model and effort:
                pair = (harness, model, effort)
                if pair in eval_by_pair:
                    errors.append(f"roles.{role_name}.evaluations contains duplicate evaluation for pair {pair}")
                eval_by_pair[pair] = ev

    candidates = role_data.get("candidates")
    if not isinstance(candidates, list):
        errors.append(f"roles.{role_name}.candidates must be an array")
        return

    # Invariants R7 & R10: each candidate must have model/effort non-null and match a sufficient evaluation
    for idx, c in enumerate(candidates):
        if not isinstance(c, dict):
            errors.append(f"roles.{role_name}.candidates[{idx}] must be an object")
            continue
        for k in c.keys():
            if k not in V3_CANDIDATE_ALLOWED_KEYS:
                errors.append(f"roles.{role_name}.candidates[{idx}]: unexpected additional property '{k}'")
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
        degraded = c.get("degraded_same_family")
        if degraded is not None and not isinstance(degraded, bool):
            errors.append(f"roles.{role_name}.candidates[{idx}].degraded_same_family must be boolean")
        ev_ids = c.get("evidence_ids")
        if not isinstance(ev_ids, list):
            errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids must be array")
        else:
            for ev_id in ev_ids:
                if not isinstance(ev_id, str) or not ev_id:
                    errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids contains invalid item: {ev_id}")
            if len(ev_ids) != len(set(ev_ids)):
                errors.append(f"roles.{role_name}.candidates[{idx}].evidence_ids contains duplicate items")
        cost_basis = c.get("cost_basis")
        if cost_basis not in VALID_COST_BASES:
            errors.append(f"roles.{role_name}.candidates[{idx}].cost_basis invalid: {cost_basis}")
        elif cost_basis != "unknown" and isinstance(ev_ids, list) and len(ev_ids) < 1:
            errors.append(f"roles.{role_name}.candidates[{idx}]: evidence_ids required when cost_basis != unknown")
        c_reason = c.get("reason")
        if not isinstance(c_reason, str) or not c_reason:
            errors.append(f"roles.{role_name}.candidates[{idx}].reason must be non-empty string")
        else:
            lower_c_reason = c_reason.lower()
            for pat in FORBIDDEN_OVERSELECTION_PATTERNS:
                if pat in lower_c_reason:
                    errors.append(f"roles.{role_name}.candidates[{idx}].reason contains forbidden over-selection phrase: '{pat}'")
        # Check against evaluations
        if model and effort:
            matching_ev = eval_by_pair.get((harness, model, effort))
            if matching_ev is None:
                errors.append(f"roles.{role_name}.candidates[{idx}] ({harness}/{model}/{effort}) has no matching evaluation in evaluations[]")
            else:
                if matching_ev.get("technical_adequacy") != "sufficient" or matching_ev.get("dispatchable") is not True:
                    errors.append(f"roles.{role_name}.candidates[{idx}] ({harness}/{model}/{effort}) evaluated as insufficient/uncertain or not dispatchable")

    # Reasoning effort minimum-sufficient check
    if candidates and len(candidates) > 0 and candidates[0].get("dispatch_role") == "primary":
        pri = candidates[0]
        p_harness = pri.get("harness")
        p_model = pri.get("model")
        p_effort = pri.get("effort")
        if p_effort == "xhigh" and p_harness and p_model:
            high_ev = eval_by_pair.get((p_harness, p_model, "high"))
            if high_ev and high_ev.get("technical_adequacy") == "sufficient" and high_ev.get("dispatchable") is True:
                ev_ids = pri.get("evidence_ids")
                if sel_basis == "pinned":
                    pass
                elif sel_basis == "escalation" and esc_reason == "concrete_technical_necessity" and isinstance(ev_ids, list) and len(ev_ids) > 0:
                    pass
                else:
                    errors.append(
                        f"roles.{role_name}: primary candidate uses effort 'xhigh' when 'high' for the same model is evaluated as sufficient. "
                        f"Requires selection_basis 'escalation' with escalation_reason 'concrete_technical_necessity' and supporting evidence_ids, or 'pinned'."
                    )

        # Minimum Sufficient Capability & Escalation Consistency Check for Maker
        if role_name == "maker" and sel_basis != "pinned":
            pri_cand = (p_harness, p_model, p_effort)
            if pri_cand in DEFAULT_EFFICIENCY_ORDER:
                pri_idx = DEFAULT_EFFICIENCY_ORDER.index(pri_cand)
                higher_cands = DEFAULT_EFFICIENCY_ORDER[:pri_idx]
            else:
                higher_cands = DEFAULT_EFFICIENCY_ORDER

            for hc in higher_cands:
                ev_hc = eval_by_pair.get(hc)
                if not ev_hc:
                    continue
                hc_sufficient = (
                    ev_hc.get("technical_adequacy") == "sufficient"
                    and ev_hc.get("dispatchable") is True
                    and ev_hc.get("catalog_eligible", True) is True
                )
                if hc_sufficient:
                    if sel_basis == "minimum_sufficient":
                        errors.append(
                            f"roles.maker: selection_basis 'minimum_sufficient' selected {pri_cand}, "
                            f"but more efficient candidate {hc} is evaluated as sufficient and dispatchable"
                        )
                    elif sel_basis == "escalation":
                        if esc_reason in ("efficient_candidate_insufficient", "efficient_candidate_uncertain", "catalog_ineligible"):
                            errors.append(
                                f"roles.maker: escalation_reason '{esc_reason}' is contradicted by evaluation for {hc}: "
                                f"candidate is evaluated as sufficient, catalog_eligible, and dispatchable"
                            )

            if sel_basis == "escalation" and esc_reason == "efficient_candidate_insufficient":
                any_insufficient = any(
                    eval_by_pair.get(hc) and eval_by_pair[hc].get("technical_adequacy") == "insufficient"
                    for hc in higher_cands
                )
                if not any_insufficient:
                    errors.append(
                        f"roles.maker: escalation_reason 'efficient_candidate_insufficient' requires at least one more efficient candidate to be evaluated as insufficient"
                    )
            elif sel_basis == "escalation" and esc_reason == "efficient_candidate_uncertain":
                any_uncertain = any(
                    eval_by_pair.get(hc) and eval_by_pair[hc].get("technical_adequacy") == "uncertain"
                    for hc in higher_cands
                )
                if not any_uncertain:
                    errors.append(
                        f"roles.maker: escalation_reason 'efficient_candidate_uncertain' requires at least one more efficient candidate to be evaluated as uncertain"
                    )
            elif sel_basis == "escalation" and esc_reason == "catalog_ineligible":
                any_ineligible = any(
                    eval_by_pair.get(hc) and eval_by_pair[hc].get("catalog_eligible") is False
                    for hc in higher_cands
                )
                if not any_ineligible:
                    errors.append(
                        f"roles.maker: escalation_reason 'catalog_ineligible' requires at least one more efficient candidate to be catalog ineligible"
                    )

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
        if tie_break is not None:
            errors.append(f"roles.{role_name}: awaiting_operator status requires tie_break_applied to be null")
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

    for k in data.keys():
        if k not in ROOT_ALLOWED_KEYS:
            errors.append(f"unexpected additional property '{k}' at root")

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
        else:
            if arr_key in ("facts", "reclassify_when") and len(arr) < 1:
                errors.append(f"{arr_key} must contain at least 1 item")
            for item in arr:
                if not isinstance(item, str) or not item:
                    errors.append(f"{arr_key} contains invalid item: {item}")

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


def match_project_priority(
    candidates: list[tuple[str, str, str]], selectors: list[str]
) -> tuple[tuple[str, str, str] | None, str | None, str]:
    """Match candidates against project_priority selectors deterministically per R13/R20.

    candidates: list of (harness, model, effort) tuples.
    selectors: list of selector patterns, e.g. 'codex/gpt-5.6-terra/high', 'claude/*/*'.

    Rule R20:
    For each selector in order:
    - 0 matches -> ignore and continue;
    - 1 match -> unique winner! Returns (candidate, f"project_priority: {selector}", "underdetermined");
    - >1 matches -> non-unique, does not resolve and continues to next selector;
    - End of list without unique match -> returns (None, None, "awaiting_operator").
    """
    for sel in selectors:
        parts = sel.split("/")
        if len(parts) != 3:
            continue
        h_pat, m_pat, e_pat = parts
        matches = [
            c
            for c in candidates
            if (h_pat == "*" or h_pat == c[0])
            and (m_pat == "*" or m_pat == c[1])
            and (e_pat == "*" or e_pat == c[2])
        ]
        if len(matches) == 1:
            return matches[0], f"project_priority: {sel}", "underdetermined"
    return None, None, "awaiting_operator"


DEFAULT_EFFICIENCY_ORDER: list[tuple[str, str, str]] = [
    ("agy", "gemini-3.8-flash-high", "high"),
    ("codex", "gpt-5.6-terra", "high"),
    ("claude", "sonnet", "high"),
    ("claude", "claude-sonnet-4-6", "high"),
    ("codex", "gpt-5.6-terra", "xhigh"),
]


def resolve_minimum_sufficient(
    evaluations: list[dict[str, Any]],
    efficiency_order: list[tuple[str, str, str]] | None = None,
    pins: dict[str, Any] | None = None,
    forbidden_families: set[str] | None = None,
    pre_dispatch_unavailable: set[tuple[str, str, str]] | None = None,
    require_xhigh: bool = False,
) -> tuple[tuple[str, str, str] | None, str, str | None]:
    """Deterministically resolve the primary model candidate using Minimum Sufficient Capability.

    Args:
        evaluations: List of evaluation dicts for the role.
        efficiency_order: Preferred order of (harness, model, effort) from highest efficiency to lowest.
        pins: Optional pins dict specifying pinned harness/model/effort for the role.
        forbidden_families: Optional set of forbidden families (e.g. {"openai", "google"}).
        pre_dispatch_unavailable: Optional set of candidate tuples unavailable at pre-dispatch.
        require_xhigh: If True, indicates concrete documented necessity for xhigh effort.

    Returns:
        (primary_candidate, selection_basis, escalation_reason)
        where primary_candidate is (harness, model, effort) or None if infeasible.
    """
    if not evaluations:
        return None, "infeasible", None

    family_map = {
        "agy": "google",
        "codex": "openai",
        "claude": "anthropic",
    }
    forbidden_fams = {f.lower() for f in forbidden_families} if forbidden_families else set()
    pre_unavailable = pre_dispatch_unavailable or set()

    eff_order = list(efficiency_order) if efficiency_order is not None else list(DEFAULT_EFFICIENCY_ORDER)

    # Check pin first
    if pins and isinstance(pins, dict):
        p_harness = pins.get("harness")
        p_model = pins.get("model")
        p_effort = pins.get("effort")
        if p_harness or p_model or p_effort:
            pinned_matching = []
            for ev in evaluations:
                h = ev.get("harness")
                m = ev.get("model")
                e = ev.get("effort")
                if p_harness and h != p_harness:
                    continue
                if p_model and m != p_model:
                    continue
                if p_effort and e != p_effort:
                    continue
                if ev.get("technical_adequacy") == "sufficient" and ev.get("catalog_eligible", True) and ev.get("dispatchable", True):
                    cand = (h, m, e)
                    fam = family_map.get(h)
                    if fam and fam in forbidden_fams:
                        continue
                    if cand not in pre_unavailable:
                        pinned_matching.append(cand)
            if pinned_matching:
                def pin_sort_key(c: tuple[str, str, str]) -> tuple[int, str, str, str]:
                    try:
                        idx = eff_order.index(c)
                    except ValueError:
                        idx = 9999
                    return (idx, c[0], c[1], c[2])

                pinned_matching.sort(key=pin_sort_key)
                return pinned_matching[0], "pinned", None

    # Build evaluation lookup and collect extra pairs
    eval_by_pair: dict[tuple[str, str, str], dict[str, Any]] = {}
    extra_pairs: list[tuple[str, str, str]] = []
    for ev in evaluations:
        h = ev.get("harness")
        m = ev.get("model")
        e = ev.get("effort")
        if h and m and e:
            pair = (h, m, e)
            eval_by_pair[pair] = ev
            if pair not in eff_order and pair not in extra_pairs:
                extra_pairs.append(pair)

    # Impose a stable, deterministic total order for pairs outside eff_order
    extra_pairs.sort()
    eff_order.extend(extra_pairs)

    # Identify eligible sufficient candidates
    eligible_sufficient: list[tuple[str, str, str]] = []
    for cand in eff_order:
        ev = eval_by_pair.get(cand)
        if not ev:
            continue
        if ev.get("technical_adequacy") != "sufficient":
            continue
        if not ev.get("catalog_eligible", True):
            continue
        if not ev.get("dispatchable", True):
            continue
        fam = family_map.get(cand[0])
        if fam and fam in forbidden_fams:
            continue
        if cand in pre_unavailable:
            continue
        eligible_sufficient.append(cand)

    if not eligible_sufficient:
        return None, "infeasible", None

    if len(eligible_sufficient) == 1 and len(evaluations) == 1:
        return eligible_sufficient[0], "only_available", None

    # If require_xhigh is True, lower effort variants do not meet the concrete technical necessity
    if require_xhigh:
        xhigh_eligible = [c for c in eligible_sufficient if c[2] in ("xhigh", "max", "ultra")]
        if not xhigh_eligible:
            return None, "infeasible", None
        return xhigh_eligible[0], "escalation", "concrete_technical_necessity"

    # Find the most efficient candidate defined in the profile
    most_efficient_cand = None
    for cand in eff_order:
        if cand in eval_by_pair:
            most_efficient_cand = cand
            break

    # If the most efficient evaluated candidate is eligible and sufficient:
    if most_efficient_cand and most_efficient_cand in eligible_sufficient:
        # Reasoning effort minimum-sufficient check:
        # If candidate has effort xhigh and require_xhigh is False, prefer high variant if available
        h, m, e = most_efficient_cand
        if e == "xhigh" and not require_xhigh:
            if (h, m, "high") in eligible_sufficient:
                return (h, m, "high"), "minimum_sufficient", None
        return most_efficient_cand, "minimum_sufficient", None

    # Escalation needed: explain why the most efficient candidate was skipped
    escalation_reason = "efficient_candidate_insufficient"
    if most_efficient_cand:
        ev_most = eval_by_pair.get(most_efficient_cand)
        fam = family_map.get(most_efficient_cand[0])
        if fam and fam in forbidden_fams:
            escalation_reason = "checker_family_independence"
        elif most_efficient_cand in pre_unavailable:
            escalation_reason = "pre_dispatch_unavailable"
        elif ev_most:
            if ev_most.get("technical_adequacy") == "uncertain":
                escalation_reason = "efficient_candidate_uncertain"
            elif ev_most.get("technical_adequacy") == "insufficient":
                escalation_reason = "efficient_candidate_insufficient"
            elif not ev_most.get("catalog_eligible", True):
                escalation_reason = "catalog_ineligible"

    # Select best candidate from eligible_sufficient according to efficiency_order
    filtered_eligible = []
    for cand in eligible_sufficient:
        h, m, e = cand
        if e == "xhigh" and not require_xhigh and (h, m, "high") in eligible_sufficient:
            continue
        filtered_eligible.append(cand)

    winner = filtered_eligible[0] if filtered_eligible else eligible_sufficient[0]
    return winner, "escalation", escalation_reason


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
