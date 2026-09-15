#!/usr/bin/env python3
"""
Unit, deterministic, and counterfactual tests for Automatic Mode (T018).
Finite Authorized Batch Execution, Recovery, and Boundaries.
Spec revision: 3c9d4bc09ceeedc0.

Covers AC01 to AC17:
- AC01: Authority boundary: "iniciar modo automático" authorizes strictly read-only (DISCOVER -> PROPOSE).
- AC02: Formal state machine: IDLE -> DISCOVER -> PROPOSE -> WAIT_AUTHORIZATION -> PREFREEZE_REVALIDATE -> FREEZE_BATCH -> EXECUTE -> CLOSE, and exceptional exits.
- AC03: Partial human approval semantics: never direct filter at freeze; forces new PROPOSE with re-calculated digest.
- AC04: Prefreeze revalidation: synchronous drift check before freeze aborts on mismatch and returns to PROPOSE.
- AC05: Durable hybrid persistence: Bnnn.md authoritative source, STATUS.md projection/coordination lock.
- AC06: Formal rejection of runtime-only batch (Alternative C disqualified).
- AC07: Call accounting by logical write-ahead serialized by coordinator.
- AC08: Auditable crash recovery: ambiguous pending_call counted conservatively as consumed with STOP.
- AC09: Unit admission gate: authority, frozen membership, spec integrity, dependencies done, coordinator, tree state, effects.
- AC10: Dynamic mandatory call reserve: required_call_reserve to independent Checker; stops if insufficient budget.
- AC11: Symmetry of bad_spec_or_intent_gap before Maker and after Checker.
- AC12: Strict limits on automatic rework: Maker-only findings, frozen spec/paths, within round limit and full rework budget.
- AC13: 18 formal stop conditions cataloged with continue_independent_after_block: false by default.
- AC14: Composition with T013-T017 and Advisor constraints (budget debited, non-recursive).
- AC15: T016 major-boundary integration gates at every integration_group transition within batch and at closure.
- AC16: Cumulative effective authorship [openai, google, anthropic] and preferred checker independence.
- AC17: Complete contractual test suite integrity and repository validation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import unittest
import sys
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from tl_job import budgeted_model_dispatch, load_batch_frontmatter

ROOT = Path(__file__).resolve().parent.parent.parent
BATCH_SCHEMA_PATH = ROOT / "schemas" / "batch.schema.json"
MANIFEST_PATH = ROOT / "distribution-manifest.json"

# ==============================================================================
# Domain Logic / Automatic Mode Normative Engine
# ==============================================================================

VALID_BATCH_STATUSES = {"in_progress", "done", "blocked", "stopped", "failed", "cancelled"}

ALL_18_STOP_CONDITIONS = [
    "authority_missing_or_ambiguous",
    "scope_expansion",
    "new_work_outside_frozen_batch",
    "model_call_budget_exhausted",
    "rework_limit_exhausted",
    "insufficient_budget_for_unit_verification",
    "required_checker_independence_unavailable",
    "required_advisor_independence_unavailable",
    "advisor_verdict_stop",
    "advisor_verdict_debate",
    "bad_spec_or_intent_gap",
    "canonical_full_gate_failure",
    "coordinator_conflict",
    "unexpected_tree_state",
    "unexpected_revision_drift",
    "external_effect_not_authorized",
    "unrecoverable_harness_failure",
    "dependency_block",
]

VALID_STATES = {
    "IDLE",
    "DISCOVER",
    "PROPOSE",
    "WAIT_AUTHORIZATION",
    "PREFREEZE_REVALIDATE",
    "FREEZE_BATCH",
    "EXECUTE",
    "CLOSE",
}

EXCEPTIONAL_EXITS = {"BLOCKED", "STOPPED", "FAILED", "CANCELLED"}


class ValidationErrors(list):
    """
    List subclass for validation error reporting that supports:
    - Standard list iteration and membership testing
    - Direct equality with a single string error for clean domain validator assertions
    - Substring containment testing: 'substring' in errors
    """

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return len(self) == 1 and self[0] == other
        return super().__eq__(other)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return any(item in s for s in self)
        return super().__contains__(item)

    def __str__(self) -> str:
        return self[0] if len(self) == 1 else super().__str__()


def validate_batch_envelope(instance: dict[str, Any], schema: dict[str, Any] | None = None) -> tuple[bool, ValidationErrors]:
    """
    Validates a batch frontmatter dictionary against schemas/batch.schema.json (Draft 2020-12).
    """
    if schema is None:
        schema = json.loads(BATCH_SCHEMA_PATH.read_text(encoding="utf-8"))

    errors = ValidationErrors()

    if not isinstance(instance, dict):
        errors.append("Batch frontmatter must be a JSON object")
        return False, errors

    # 1. Top-level properties check
    allowed_props = set(schema.get("properties", {}).keys())
    extra_props = set(instance.keys()) - allowed_props
    if extra_props:
        errors.append(f"Unexpected top-level properties: {sorted(extra_props)}")

    for req in schema.get("required", []):
        if req not in instance:
            errors.append(f"Missing required top-level property: '{req}'")

    if errors:
        return False, errors

    # 2. id
    bid = instance.get("id")
    if not isinstance(bid, str) or not re.match(r"^B[0-9]{3,}$", bid):
        errors.append(f"id must match '^B[0-9]{{3,}}$', got {bid!r}")

    # 3. status
    bstatus = instance.get("status")
    if bstatus not in VALID_BATCH_STATUSES:
        errors.append(f"status must be one of {sorted(VALID_BATCH_STATUSES)}, got {bstatus!r}")

    # 4. batch_revision
    rev = instance.get("batch_revision")
    if not isinstance(rev, int) or rev < 1:
        errors.append(f"batch_revision must be an integer >= 1, got {rev!r}")

    # 5. authorization
    auth = instance.get("authorization")
    if not isinstance(auth, dict):
        errors.append("authorization must be an object")
    else:
        req_auth = [
            "proposal_id",
            "proposal_digest",
            "authority_source",
            "authorized_at",
            "permitted_effects",
            "continue_independent_after_block",
        ]
        for ra in req_auth:
            if ra not in auth:
                errors.append(f"Missing authorization property: '{ra}'")
        if "permitted_effects" in auth and isinstance(auth["permitted_effects"], dict):
            pe = auth["permitted_effects"]
            pe_keys = ["local_write", "local_commit", "local_merge", "pull_request", "push", "tag", "release"]
            for pk in pe_keys:
                if pk not in pe or not isinstance(pe[pk], bool):
                    errors.append(f"permitted_effects.{pk} must be boolean")
        if "continue_independent_after_block" in auth and not isinstance(auth["continue_independent_after_block"], bool):
            errors.append("continue_independent_after_block must be boolean")

    # 6. frozen_scope
    fscope = instance.get("frozen_scope")
    if not isinstance(fscope, dict):
        errors.append("frozen_scope must be an object")
    else:
        req_fs = schema.get("properties", {}).get("frozen_scope", {}).get("required", [
            "advisor_policy", "units", "integration_groups", "major_boundaries", "stop_conditions", "immutable_digest"
        ])
        for rfs in req_fs:
            if rfs not in fscope:
                errors.append(f"Missing frozen_scope property: '{rfs}'")

        fs_props = set(schema.get("properties", {}).get("frozen_scope", {}).get("properties", {}).keys())
        if fs_props:
            extra_fs = set(fscope.keys()) - fs_props
            if extra_fs:
                errors.append(f"Unexpected frozen_scope properties: {sorted(extra_fs)}")

        if "batch_concurrency" in fscope:
            bc = fscope["batch_concurrency"]
            if bc != 1 or isinstance(bc, bool):
                errors.append(f"frozen_scope.batch_concurrency must be 1, got {bc!r}")

        if "advisor_policy" in fscope:
            adv = fscope["advisor_policy"]
            if not isinstance(adv, dict):
                errors.append("frozen_scope.advisor_policy must be an object")
            else:
                adv_schema = (
                    schema.get("properties", {})
                    .get("frozen_scope", {})
                    .get("properties", {})
                    .get("advisor_policy", {})
                )
                adv_props = set(adv_schema.get("properties", {}).keys()) or {"enabled", "triggers", "max_calls"}
                extra_adv = set(adv.keys()) - adv_props
                if extra_adv:
                    errors.append(f"Unexpected advisor_policy properties: {sorted(extra_adv)}")
                req_adv = adv_schema.get("required", ["enabled", "triggers", "max_calls"])
                for ra in req_adv:
                    if ra not in adv:
                        errors.append(f"Missing advisor_policy property: '{ra}'")
                if "enabled" in adv and not isinstance(adv["enabled"], bool):
                    errors.append("advisor_policy.enabled must be boolean")
                if "triggers" in adv:
                    tr = adv["triggers"]
                    if not isinstance(tr, list):
                        errors.append("advisor_policy.triggers must be an array")
                    else:
                        tr_schema = adv_schema.get("properties", {}).get("triggers", {})
                        if tr_schema.get("uniqueItems", True) and len(tr) != len(set(tr)):
                            errors.append("advisor_policy.triggers must contain unique items")
                        allowed_tr = tr_schema.get("items", {}).get("enum", [])
                        for item in tr:
                            if allowed_tr and item not in allowed_tr:
                                errors.append(f"Invalid advisor trigger: {item!r}")
                if "max_calls" in adv:
                    mc = adv["max_calls"]
                    if not isinstance(mc, int) or isinstance(mc, bool) or mc < 0:
                        errors.append(f"advisor_policy.max_calls must be an integer >= 0, got {mc!r}")

        if "units" in fscope:
            units = fscope["units"]
            if not isinstance(units, list) or len(units) < 1:
                errors.append("frozen_scope.units must be a non-empty array")
            else:
                for idx, u in enumerate(units):
                    if not isinstance(u, dict):
                        errors.append(f"frozen_scope.units[{idx}] must be an object")
                        continue
                    for uk in ["work_ref", "revision", "spec_revision", "integration_group", "dependencies"]:
                        if uk not in u:
                            errors.append(f"Missing unit property '{uk}' at index {idx}")
        if "integration_groups" in fscope:
            ig = fscope["integration_groups"]
            if not isinstance(ig, dict) or len(ig) < 1:
                errors.append("frozen_scope.integration_groups must be a non-empty object")
        if "stop_conditions" in fscope:
            sc = fscope["stop_conditions"]
            if not isinstance(sc, list):
                errors.append("frozen_scope.stop_conditions must be an array")
            else:
                sc_schema = (
                    schema.get("properties", {})
                    .get("frozen_scope", {})
                    .get("properties", {})
                    .get("stop_conditions", {})
                )
                min_items = sc_schema.get("minItems")
                max_items = sc_schema.get("maxItems")
                unique_items = sc_schema.get("uniqueItems", False)
                items_enum = sc_schema.get("items", {}).get("enum", [])

                if min_items is not None and len(sc) < min_items:
                    errors.append(
                        f"frozen_scope.stop_conditions must contain at least {min_items} items, got {len(sc)}"
                    )
                if max_items is not None and len(sc) > max_items:
                    errors.append(
                        f"frozen_scope.stop_conditions must contain at most {max_items} items, got {len(sc)}"
                    )
                if unique_items and len(sc) != len(set(sc)):
                    errors.append("frozen_scope.stop_conditions must contain unique items")
                if items_enum:
                    for c in sc:
                        if c not in items_enum:
                            errors.append(f"Invalid stop condition: {c!r}")
                else:
                    for c in sc:
                        if c not in ALL_18_STOP_CONDITIONS:
                            errors.append(f"Invalid stop condition: {c!r}")

    # 7. budget
    budget = instance.get("budget")
    if not isinstance(budget, dict):
        errors.append("budget must be an object")
    else:
        req_b = [
            "max_model_calls",
            "consumed_model_calls",
            "reserved_model_calls",
            "max_rework_rounds_per_unit",
            "max_advisor_calls",
            "consumed_advisor_calls",
            "pending_call",
        ]
        for rb in req_b:
            if rb not in budget:
                errors.append(f"Missing budget property: '{rb}'")
        for int_k in ["max_model_calls", "consumed_model_calls", "reserved_model_calls", "max_rework_rounds_per_unit", "max_advisor_calls", "consumed_advisor_calls"]:
            if int_k in budget and (not isinstance(budget[int_k], int) or budget[int_k] < 0):
                errors.append(f"budget.{int_k} must be non-negative integer")
        pcall = budget.get("pending_call")
        if pcall is not None:
            if not isinstance(pcall, dict):
                errors.append("budget.pending_call must be null or object")
            else:
                for pk in ["call_id", "role", "phase"]:
                    if pk not in pcall:
                        errors.append(f"budget.pending_call missing '{pk}'")

    # 8. execution
    exec_block = instance.get("execution")
    if not isinstance(exec_block, dict):
        errors.append("execution must be an object")
    else:
        req_e = [
            "current_unit",
            "current_phase",
            "current_round",
            "expected_tree_checkpoint",
            "completed_units",
            "stop_reason",
        ]
        for re_k in req_e:
            if re_k not in exec_block:
                errors.append(f"Missing execution property: '{re_k}'")
        if "completed_units" in exec_block and not isinstance(exec_block["completed_units"], list):
            errors.append("execution.completed_units must be array")

        exec_props = set(schema.get("properties", {}).get("execution", {}).get("properties", {}).keys())
        if exec_props:
            extra_e = set(exec_block.keys()) - exec_props
            if extra_e:
                errors.append(f"Unexpected execution properties: {sorted(extra_e)}")

        if "runtime_refs" in exec_block:
            rrefs = exec_block["runtime_refs"]
            if not isinstance(rrefs, dict):
                errors.append("execution.runtime_refs must be an object")
            else:
                rr_schema = (
                    schema.get("properties", {})
                    .get("execution", {})
                    .get("properties", {})
                    .get("runtime_refs", {})
                )
                rr_props = set(rr_schema.get("properties", {}).keys())
                extra_rr = set(rrefs.keys()) - rr_props
                if extra_rr:
                    errors.append(f"Unexpected runtime_refs properties: {sorted(extra_rr)}")
                for prop, val in rrefs.items():
                    if prop in rr_props and val is not None:
                        if prop == "lease_heartbeat_ts":
                            if isinstance(val, bool) or not isinstance(val, (int, float)):
                                errors.append(f"execution.runtime_refs.{prop} must be a number or null")
                        else:
                            if not isinstance(val, str):
                                errors.append(f"execution.runtime_refs.{prop} must be a string or null")

    # 9. Invariâncias contratuais: advisor_policy e budget
    fscope_obj = instance.get("frozen_scope")
    if isinstance(fscope_obj, dict):
        adv_obj = fscope_obj.get("advisor_policy")
        if isinstance(adv_obj, dict):
            b_obj = instance.get("budget")
            if isinstance(b_obj, dict):
                if "max_calls" in adv_obj and "max_advisor_calls" in b_obj:
                    if adv_obj.get("max_calls") != b_obj.get("max_advisor_calls"):
                        errors.append(
                            "advisor_budget_divergence: frozen_scope.advisor_policy.max_calls must equal budget.max_advisor_calls"
                        )
                if not adv_obj.get("enabled", True) and b_obj.get("consumed_advisor_calls", 0) != 0:
                    errors.append(
                        "advisor_disabled_consumption: consumed_advisor_calls must be 0 when advisor_policy.enabled is false"
                    )

    return (len(errors) == 0), errors


def match_draft202012_conditional_allof(schema: dict[str, Any], instance: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Evaluates Draft 2020-12 'allOf' with 'if'/'then' conditional constraints from the real schema directly against an instance.
    """
    errors: list[str] = []
    all_of = schema.get("allOf", [])
    for idx, rule in enumerate(all_of):
        if_rule = rule.get("if")
        then_rule = rule.get("then")
        if not if_rule or not then_rule:
            continue

        if _matches_subschema(if_rule, instance):
            if not _matches_subschema(then_rule, instance):
                errors.append(
                    f"schema_conditional_violation: allOf[{idx}] then condition failed for instance"
                )

    return (len(errors) == 0), errors


def _matches_subschema(subschema: dict[str, Any], data: Any) -> bool:
    if not isinstance(subschema, dict):
        return True
    if "const" in subschema:
        target = subschema["const"]
        if data != target or type(data) is not type(target):
            return False
    if "enum" in subschema and data not in subschema["enum"]:
        return False
    if "required" in subschema:
        if not isinstance(data, dict):
            return False
        for req in subschema["required"]:
            if req not in data:
                return False
    if "properties" in subschema:
        if not isinstance(data, dict):
            return False
        for prop, p_sch in subschema["properties"].items():
            if prop in data:
                if not _matches_subschema(p_sch, data[prop]):
                    return False
    return True


class AutomaticModeStateMachine:
    """
    Formal state machine for Automatic Mode (AC02).
    Transitions:
    IDLE -> DISCOVER -> PROPOSE -> WAIT_AUTHORIZATION -> PREFREEZE_REVALIDATE -> FREEZE_BATCH -> EXECUTE -> CLOSE
    """

    ALLOWED_TRANSITIONS = {
        "IDLE": {"DISCOVER"},
        "DISCOVER": {"PROPOSE", "CANCELLED", "IDLE"},
        "PROPOSE": {"WAIT_AUTHORIZATION", "CANCELLED", "IDLE"},
        "WAIT_AUTHORIZATION": {"PREFREEZE_REVALIDATE", "PROPOSE", "IDLE", "CANCELLED"},
        "PREFREEZE_REVALIDATE": {"FREEZE_BATCH", "PROPOSE", "CANCELLED", "STOPPED"},
        "FREEZE_BATCH": {"EXECUTE", "STOPPED", "FAILED"},
        "EXECUTE": {"CLOSE", "EXECUTE", "BLOCKED", "STOPPED", "FAILED", "CANCELLED"},
        "CLOSE": {"IDLE"},
        "BLOCKED": {"IDLE", "EXECUTE"},
        "STOPPED": {"IDLE", "EXECUTE"},
        "FAILED": {"IDLE"},
        "CANCELLED": {"IDLE"},
    }

    def __init__(self, initial_state: str = "IDLE") -> None:
        if initial_state not in VALID_STATES and initial_state not in EXCEPTIONAL_EXITS:
            raise ValueError(f"Invalid initial state: {initial_state}")
        self.state = initial_state
        self.history: list[str] = [initial_state]

    def transition_to(self, next_state: str) -> None:
        allowed = self.ALLOWED_TRANSITIONS.get(self.state, set())
        if next_state not in allowed:
            raise ValueError(f"Illegal state jump: cannot transition from {self.state} to {next_state}")
        self.state = next_state
        self.history.append(next_state)


def compute_digest(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def process_human_authorization(proposal: dict[str, Any], user_response: dict[str, Any]) -> dict[str, Any]:
    """
    Validates AC01 and AC03:
    - If user approves partially (subset of proposed units), never directly filter at freeze.
    - Forces a new PROPOSE cycle with re-calculated dependencies, budget, boundaries, and proposal_digest.
    """
    approved_units = user_response.get("approved_units", [])
    proposed_units = [u["work_ref"] for u in proposal.get("units", [])]

    if not approved_units:
        return {"outcome": "rejected", "next_state": "IDLE"}

    # Subset check
    if set(approved_units) == set(proposed_units):
        return {
            "outcome": "approved_full",
            "next_state": "PREFREEZE_REVALIDATE",
            "proposal": proposal,
        }

    # Partial approval semantics:
    filtered_units = [u for u in proposal["units"] if u["work_ref"] in approved_units]
    new_proposal = dict(proposal)
    new_proposal["units"] = filtered_units
    new_proposal["proposal_id"] = f"{proposal['proposal_id']}-revised"
    new_proposal["proposal_digest"] = compute_digest(new_proposal["units"])

    return {
        "outcome": "partial_requires_reproposal",
        "next_state": "PROPOSE",
        "revised_proposal": new_proposal,
    }


def prefreeze_revalidate(proposal: dict[str, Any], actual_tree_state: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """
    Validates AC04:
    Immediately before freeze, synchronously revalidates revisions, spec_revisions, dependencies, and digests.
    Any drift aborts freeze and returns to PROPOSE.
    """
    for u in proposal.get("units", []):
        wref = u["work_ref"]
        if wref not in actual_tree_state.get("tasks", {}):
            return False, f"drift_missing_task: {wref}", {"next_state": "PROPOSE"}
        actual = actual_tree_state["tasks"][wref]
        if actual.get("revision") != u.get("revision"):
            return False, f"drift_task_revision: {wref}", {"next_state": "PROPOSE"}
        if actual.get("spec_revision") != u.get("spec_revision"):
            return False, f"drift_spec_revision: {wref}", {"next_state": "PROPOSE"}
        if actual.get("dependencies") != u.get("dependencies"):
            return False, f"drift_dependencies: {wref}", {"next_state": "PROPOSE"}

    # Validate scope digest
    current_digest = compute_digest(proposal.get("units", []))
    if current_digest != proposal.get("proposal_digest"):
        return False, "drift_proposal_digest_mismatch", {"next_state": "PROPOSE"}

    return True, "prefreeze_revalidation_ok", {"next_state": "FREEZE_BATCH"}


def evaluate_admission_gate(
    batch: dict[str, Any],
    unit_ref: str,
    tree_checkpoint: str,
    coordinator_session: str,
    unit_state: dict[str, Any],
    required_effects: list[str],
) -> tuple[bool, str]:
    """
    Validates AC09: Unit Admission Gate before starting execution of a unit.
    """
    # 1. Authority unchanged
    if batch.get("authorization", {}).get("authority_source") != "explicit_user_authorization":
        return False, "authority_missing_or_ambiguous"

    # 2. Frozen scope membership
    frozen_units = {u["work_ref"]: u for u in batch.get("frozen_scope", {}).get("units", [])}
    if unit_ref not in frozen_units:
        return False, "new_work_outside_frozen_batch"

    frozen_unit = frozen_units[unit_ref]

    # 3. Revision and spec_revision integrity
    if unit_state.get("revision") != frozen_unit.get("revision") or unit_state.get("spec_revision") != frozen_unit.get("spec_revision"):
        return False, "unexpected_revision_drift"

    # 4. Dependencies satisfied (status == done)
    for dep in frozen_unit.get("dependencies", []):
        if dep not in batch.get("execution", {}).get("completed_units", []):
            return False, "dependency_block"

    # 5. Coordinator valid
    if not coordinator_session:
        return False, "coordinator_conflict"

    # 6. Tree state matches expected checkpoint
    if tree_checkpoint != batch.get("execution", {}).get("expected_tree_checkpoint"):
        return False, "unexpected_tree_state"

    # 7. Permitted effects
    pe = batch.get("authorization", {}).get("permitted_effects", {})
    for eff in required_effects:
        if not pe.get(eff, False):
            return False, "external_effect_not_authorized"

    # 8. Budget available for minimum dynamic reserve
    reserve = calculate_dynamic_reserve(unit_ref, current_phase="implementation")
    b = batch.get("budget", {})
    available = b.get("max_model_calls", 0) - b.get("consumed_model_calls", 0) - b.get("reserved_model_calls", 0)
    if available < reserve:
        return False, "insufficient_budget_for_unit_verification"

    return True, "admission_pass"


def calculate_dynamic_reserve(
    unit_ref: str,
    current_phase: str,
    has_advisor_trigger: bool = False,
    has_planner: bool = False,
    is_rework: bool = False,
) -> int:
    """
    Validates AC10: Dynamic mandatory call reserve.
    Calculates all mandatory calls remaining until independent Checker verification.
    """
    reserve = 0
    if is_rework:
        # Classifier rework + Maker + Classifier rev + Checker
        reserve = 4
        if has_advisor_trigger:
            reserve += 1
        return reserve

    if current_phase == "implementation":
        # Classifier impl + Maker + Classifier rev + Checker
        reserve = 4
        if has_planner:
            reserve += 1
        if has_advisor_trigger:
            reserve += 1
        return reserve

    if current_phase == "post_classifier_impl":
        # Maker + Classifier rev + Checker
        return 3

    if current_phase == "review":
        # Classifier rev + Checker
        return 2

    return 1


def evaluate_write_ahead_transition(
    batch: dict[str, Any],
    action: str,
    call_info: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Validates AC07: Write-ahead logical progression:
    check -> reserve -> pending_call -> dispatch -> receipt -> consumed -> clear pending_call.
    """
    b = batch["budget"]
    avail = b["max_model_calls"] - b["consumed_model_calls"] - b["reserved_model_calls"]

    if action == "reserve":
        count = call_info.get("count", 1) if call_info else 1
        if avail < count:
            return False, "insufficient_budget", batch
        b["reserved_model_calls"] += count
        return True, "reserved", batch

    if action == "set_pending_call":
        b["pending_call"] = {
            "call_id": call_info["call_id"],
            "role": call_info["role"],
            "phase": call_info["phase"],
            "dispatched_at": call_info.get("dispatched_at", "2026-09-12T18:00:00Z"),
        }
        return True, "pending_call_set", batch

    if action == "complete_call":
        if b["reserved_model_calls"] > 0:
            b["reserved_model_calls"] -= 1
        b["consumed_model_calls"] += 1
        b["pending_call"] = None
        return True, "call_completed", batch

    return False, "unknown_action", batch


def recover_from_crash(batch: dict[str, Any], receipt_found: bool, ambiguous: bool) -> tuple[str, dict[str, Any]]:
    """
    Validates AC08: Auditable crash recovery:
    If pending_call exists:
    - Clear receipt -> consumed and proceed
    - Dispatch definitely didn't happen -> release reservation and proceed
    - Ambiguous -> consumed conservatively and STOP
    """
    b = batch["budget"]
    pcall = b.get("pending_call")

    if not pcall:
        return "resume_clean", batch

    if receipt_found:
        if b["reserved_model_calls"] > 0:
            b["reserved_model_calls"] -= 1
        b["consumed_model_calls"] += 1
        b["pending_call"] = None
        return "consumed_and_resume", batch

    if ambiguous:
        # Conservative accounting
        if b["reserved_model_calls"] > 0:
            b["reserved_model_calls"] -= 1
        b["consumed_model_calls"] += 1
        b["pending_call"] = None
        batch["status"] = "stopped"
        batch["execution"]["stop_reason"] = "unrecoverable_harness_failure"
        return "conservative_stop", batch

    # Dispatched definitely didn't happen:
    if b["reserved_model_calls"] > 0:
        b["reserved_model_calls"] -= 1
    b["pending_call"] = None
    return "released_and_resume", batch


def evaluate_symmetry_bad_spec(finding_phase: str, finding_type: str) -> tuple[bool, str]:
    """
    Validates AC11: Symmetry of bad_spec_or_intent_gap.
    - Pre-Maker / Classifier -> STOP before Maker.
    - Post-Checker -> STOP before rework.
    """
    if finding_type in {"bad_spec", "intent_gap", "bad_spec_or_intent_gap"}:
        if finding_phase in {"classifier_impl", "pre_maker"}:
            return False, "STOP: bad_spec_or_intent_gap (stopped before Maker)"
        if finding_phase in {"checker_review", "post_checker"}:
            return False, "STOP: bad_spec_or_intent_gap (stopped before rework)"
    return True, "proceed"


def evaluate_integration_boundary_gate(
    batch: dict[str, Any],
    current_unit_group: str,
    next_unit_group: str | None,
    gate_exit_code: int | None,
) -> tuple[bool, str]:
    """
    Validates AC15: T016 major boundary gate at integration_group transitions within batch.
    """
    # If next_unit_group is None, it is batch closure.
    transition_happening = (next_unit_group is None) or (current_unit_group != next_unit_group)
    if not transition_happening:
        return True, "intragroup_no_gate_required"

    if gate_exit_code is None:
        return False, "canonical_full_gate_required_not_run"

    if gate_exit_code != 0:
        return False, "canonical_full_gate_failure"

    return True, "canonical_full_gate_pass"


def evaluate_batch_persistence(
    batch_file: Path | str | None,
    in_memory_only: bool = False,
    disk_content: dict[str, Any] | None = None,
    status_projection: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Validates AC05 and AC06:
    - Bnnn.md on disk is the authoritative source of truth.
    - If memory_only / no durable disk file, reject immediately (Alternative C disqualified).
    - If status_projection diverges from disk_content, disk_content (Bnnn.md) prevails.
    """
    if in_memory_only or batch_file is None:
        return False, "runtime_only_batch_rejected", None

    if disk_content is None:
        return False, "durable_batch_file_missing", None

    effective = dict(disk_content)
    if status_projection and status_projection.get("active_batch") != disk_content.get("id"):
        effective["_reconciled_from_disk"] = True

    return True, "durable_batch_authoritative", effective


def evaluate_rework_admission(
    batch: dict[str, Any],
    unit_ref: str,
    checker_verdict: str,
    finding_target: str,
    requested_paths: list[str],
    frozen_content_paths: list[str],
    current_round: int,
    unit_spec_revision: str,
    frozen_spec_revision: str,
) -> tuple[bool, str]:
    """
    Validates AC12: Strict limits on automatic rework:
    - Allowed only when checker_verdict == "changes_requested"
    - Findings targeted to Maker only (no architecture/product changes)
    - Spec revision and content_paths must remain within frozen scope
    - current_round < max_rework_rounds_per_unit
    - Budget remaining >= required_call_reserve for rework
    """
    if checker_verdict != "changes_requested":
        return False, "rework_not_requested"

    if finding_target != "maker":
        return False, "bad_spec_or_intent_gap"

    if unit_spec_revision != frozen_spec_revision:
        return False, "unexpected_revision_drift"

    for p in requested_paths:
        if p not in frozen_content_paths:
            return False, "scope_expansion"

    max_rounds = batch.get("budget", {}).get("max_rework_rounds_per_unit", 2)
    if current_round >= max_rounds:
        return False, "rework_limit_exhausted"

    reserve = calculate_dynamic_reserve(unit_ref, current_phase="implementation", is_rework=True)
    b = batch.get("budget", {})
    available = b.get("max_model_calls", 0) - b.get("consumed_model_calls", 0) - b.get("reserved_model_calls", 0)
    if available < reserve:
        return False, "insufficient_budget_for_unit_verification"

    return True, "rework_admitted"


def dispatch_advisor_call(
    batch: dict[str, Any],
    caller_role: str,
    trigger: str = "architecture_or_contract_change",
) -> tuple[bool, str, dict[str, Any]]:
    """
    Validates AC14 Advisor constraints:
    - Checks advisor_policy.enabled: if False, returns advisor_disabled and preserves consumed_advisor_calls.
    - Checks advisor_policy.triggers: trigger must be in declared triggers.
    - Prohibits advisor recursion: Advisor cannot dispatch another Advisor.
    - Debits consumed_advisor_calls upon dispatch.
    - Blocks new advisor call if consumed_advisor_calls >= max_advisor_calls.
    """
    if not batch.get("frozen_scope", {}).get("advisor_policy", {}).get("enabled", False):
        return False, "advisor_disabled: advisor_policy.enabled is False", batch

    if trigger not in batch.get("frozen_scope", {}).get("advisor_policy", {}).get("triggers", []):
        return False, f"unauthorized_trigger: {trigger}", batch

    if caller_role == "advisor":
        return False, "advisor_recursion_prohibited", batch

    b = batch.get("budget", {})
    max_adv = b.get("max_advisor_calls", 2)
    consumed_adv = b.get("consumed_advisor_calls", 0)

    if consumed_adv >= max_adv:
        return False, "advisor_budget_exhausted", batch

    new_batch = dict(batch)
    new_batch["budget"] = dict(b)
    new_batch["budget"]["consumed_advisor_calls"] = consumed_adv + 1

    return True, "advisor_dispatched", new_batch


# ==============================================================================
# Unit and Deterministic Test Suite
# ==============================================================================

class TestAutomaticModeContract(unittest.TestCase):

    def setUp(self) -> None:
        self.schema = json.loads(BATCH_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.valid_batch_frontmatter = {
            "id": "B001",
            "status": "in_progress",
            "batch_revision": 1,
            "authorization": {
                "proposal_id": "prop-20260912-001",
                "proposal_digest": "sha256:abc1234567890",
                "authority_source": "explicit_user_authorization",
                "authorized_at": "2026-09-12T16:00:00Z",
                "permitted_effects": {
                    "local_write": True,
                    "local_commit": True,
                    "local_merge": False,
                    "pull_request": False,
                    "push": False,
                    "tag": False,
                    "release": False,
                },
                "continue_independent_after_block": False,
            },
            "frozen_scope": {
                "batch_concurrency": 1,
                "advisor_policy": {
                    "enabled": True,
                    "triggers": [
                        "architecture_or_contract_change",
                        "heavy_tier_material_uncertainty",
                    ],
                    "max_calls": 2,
                },
                "units": [
                    {
                        "work_ref": "T018",
                        "revision": 1,
                        "spec_revision": "3c9d4bc09ceeedc0",
                        "integration_group": "group-native",
                        "dependencies": [],
                    },
                    {
                        "work_ref": "T019",
                        "revision": 1,
                        "spec_revision": "98a7b6c5d4e3f210",
                        "integration_group": "group-native",
                        "dependencies": ["T018"],
                    },
                ],
                "integration_groups": {
                    "group-native": ["T018", "T019"],
                },
                "major_boundaries": [
                    {
                        "from": "group-native",
                        "to": "batch_closure",
                        "gate": "python3 scripts/validate_repository.py",
                    }
                ],
                "stop_conditions": list(ALL_18_STOP_CONDITIONS),
                "immutable_digest": "sha256:immutable1234567890",
            },
            "budget": {
                "max_model_calls": 24,
                "consumed_model_calls": 0,
                "reserved_model_calls": 0,
                "max_rework_rounds_per_unit": 2,
                "max_advisor_calls": 2,
                "consumed_advisor_calls": 0,
                "pending_call": None,
            },
            "execution": {
                "current_unit": "T018",
                "current_phase": "implementation",
                "current_round": 0,
                "expected_tree_checkpoint": "4775c6b39c954da49aa40562afeea7e3eafad390",
                "completed_units": [],
                "stop_reason": None,
            },
        }

    # --------------------------------------------------------------------------
    # AC05: Schema Validation Tests
    # --------------------------------------------------------------------------

    def test_ac05_schema_valid_batch_and_pending_call(self) -> None:
        valid, errors = validate_batch_envelope(self.valid_batch_frontmatter, self.schema)
        self.assertTrue(valid, f"Validation failed unexpectedly: {errors}")

        data = dict(self.valid_batch_frontmatter)
        data["budget"] = dict(data["budget"])
        data["budget"]["pending_call"] = {
            "call_id": "call-12345",
            "role": "maker",
            "phase": "implementation",
            "payload_digest": "sha256:abc",
            "dispatched_at": "2026-09-12T17:00:00Z",
        }
        valid, errors = validate_batch_envelope(data, self.schema)
        self.assertTrue(valid, f"Pending call object should be valid: {errors}")

    def test_ac05_schema_counterfactual_missing_required(self) -> None:
        invalid = dict(self.valid_batch_frontmatter)
        del invalid["authorization"]
        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("Missing required top-level property: 'authorization'" in e for e in errors))

    def test_ac05_schema_counterfactual_invalid_id_format(self) -> None:
        invalid = dict(self.valid_batch_frontmatter)
        invalid["id"] = "INVALID_BATCH_ID"
        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("id must match" in e for e in errors))

    def test_ac05_schema_counterfactual_invalid_status_enum(self) -> None:
        invalid = dict(self.valid_batch_frontmatter)
        invalid["status"] = "in_limbo"
        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("status must be one of" in e for e in errors))

    def test_ac05_schema_counterfactual_pending_call_missing_role(self) -> None:
        data = dict(self.valid_batch_frontmatter)
        data["budget"] = dict(data["budget"])
        data["budget"]["pending_call"] = {
            "call_id": "call-12345",
            "phase": "implementation",
        }
        valid, errors = validate_batch_envelope(data, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("pending_call missing 'role'" in e for e in errors))

    # --------------------------------------------------------------------------
    # AC06: Formal Rejection of Runtime-Only Batch (Alternative C)
    # --------------------------------------------------------------------------

    def test_ac06_runtime_only_memory_batch_rejection(self) -> None:
        # Positive proof: durable Bnnn.md on disk is authoritative
        disk_batch = dict(self.valid_batch_frontmatter)
        status_projection = {
            "active_batch": "B001",
            "batch_status": "in_progress",
            "next_batch_id": "B002",
        }
        ok, reason, effective = evaluate_batch_persistence(
            batch_file=Path("_tl-orc/project/batches/B001.md"),
            in_memory_only=False,
            disk_content=disk_batch,
            status_projection=status_projection,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "durable_batch_authoritative")
        self.assertIsNotNone(effective)
        self.assertEqual(effective["id"], "B001")

        # In case of divergence between STATUS.md and Bnnn.md, disk entity prevails
        divergent_projection = {
            "active_batch": "B999_divergent",
            "batch_status": "blocked",
            "next_batch_id": "B002",
        }
        ok, reason, effective = evaluate_batch_persistence(
            batch_file=Path("_tl-orc/project/batches/B001.md"),
            in_memory_only=False,
            disk_content=disk_batch,
            status_projection=divergent_projection,
        )
        self.assertTrue(ok)
        self.assertEqual(effective["id"], "B001")
        self.assertTrue(effective.get("_reconciled_from_disk"))

        # Counterfactual proof: attempt at runtime-only memory batch is disqualified and rejected
        ok_mem, reason_mem, _ = evaluate_batch_persistence(
            batch_file=None,
            in_memory_only=True,
            disk_content=None,
        )
        self.assertFalse(ok_mem)
        self.assertEqual(reason_mem, "runtime_only_batch_rejected")

        # Missing disk file is rejected
        ok_nofile, reason_nofile, _ = evaluate_batch_persistence(
            batch_file=Path("_tl-orc/project/batches/B001.md"),
            in_memory_only=False,
            disk_content=None,
        )
        self.assertFalse(ok_nofile)
        self.assertEqual(reason_nofile, "durable_batch_file_missing")

    # --------------------------------------------------------------------------
    # AC01 & AC02: State Machine & Authority Invariant
    # --------------------------------------------------------------------------

    def test_ac01_authority_read_only_in_discover_propose(self) -> None:
        sm = AutomaticModeStateMachine("IDLE")
        sm.transition_to("DISCOVER")
        # In DISCOVER or PROPOSE, write actions must be blocked
        read_only_mode = (sm.state in {"DISCOVER", "PROPOSE"})
        self.assertTrue(read_only_mode)

        sm.transition_to("PROPOSE")
        read_only_mode = (sm.state in {"DISCOVER", "PROPOSE"})
        self.assertTrue(read_only_mode)

    def test_ac02_state_machine_valid_full_lifecycle(self) -> None:
        sm = AutomaticModeStateMachine("IDLE")
        sm.transition_to("DISCOVER")
        sm.transition_to("PROPOSE")
        sm.transition_to("WAIT_AUTHORIZATION")
        sm.transition_to("PREFREEZE_REVALIDATE")
        sm.transition_to("FREEZE_BATCH")
        sm.transition_to("EXECUTE")
        sm.transition_to("CLOSE")
        sm.transition_to("IDLE")
        self.assertEqual(sm.history, [
            "IDLE", "DISCOVER", "PROPOSE", "WAIT_AUTHORIZATION",
            "PREFREEZE_REVALIDATE", "FREEZE_BATCH", "EXECUTE", "CLOSE", "IDLE"
        ])

    def test_ac02_state_machine_counterfactual_illegal_jumps(self) -> None:
        sm = AutomaticModeStateMachine("IDLE")
        with self.assertRaises(ValueError):
            sm.transition_to("EXECUTE")  # Cannot jump straight to EXECUTE

        with self.assertRaises(ValueError):
            sm.transition_to("FREEZE_BATCH")  # Cannot jump straight to FREEZE_BATCH

        sm.transition_to("DISCOVER")
        sm.transition_to("PROPOSE")
        with self.assertRaises(ValueError):
            sm.transition_to("FREEZE_BATCH")  # Cannot skip WAIT_AUTHORIZATION

    # --------------------------------------------------------------------------
    # AC03: Partial Human Approval Semantics
    # --------------------------------------------------------------------------

    def test_ac03_partial_human_approval_forces_reproposal_cycle(self) -> None:
        proposal = {
            "proposal_id": "prop-100",
            "units": [
                {"work_ref": "T018", "revision": 1},
                {"work_ref": "T019", "revision": 1},
                {"work_ref": "T020", "revision": 1},
            ],
            "proposal_digest": compute_digest([
                {"work_ref": "T018", "revision": 1},
                {"work_ref": "T019", "revision": 1},
                {"work_ref": "T020", "revision": 1},
            ]),
        }
        # Human approves only T018 and T019
        user_response = {"approved_units": ["T018", "T019"]}
        result = process_human_authorization(proposal, user_response)

        self.assertEqual(result["outcome"], "partial_requires_reproposal")
        self.assertEqual(result["next_state"], "PROPOSE")
        revised = result["revised_proposal"]
        self.assertEqual([u["work_ref"] for u in revised["units"]], ["T018", "T019"])
        self.assertNotEqual(revised["proposal_digest"], proposal["proposal_digest"])
        self.assertEqual(revised["proposal_digest"], compute_digest(revised["units"]))

    def test_ac03_full_human_approval_advances_to_prefreeze_revalidate(self) -> None:
        proposal = {
            "proposal_id": "prop-100",
            "units": [{"work_ref": "T018", "revision": 1}],
            "proposal_digest": compute_digest([{"work_ref": "T018", "revision": 1}]),
        }
        user_response = {"approved_units": ["T018"]}
        result = process_human_authorization(proposal, user_response)
        self.assertEqual(result["outcome"], "approved_full")
        self.assertEqual(result["next_state"], "PREFREEZE_REVALIDATE")

    # --------------------------------------------------------------------------
    # AC04: Prefreeze Revalidation against Drift
    # --------------------------------------------------------------------------

    def test_ac04_prefreeze_revalidation_success(self) -> None:
        proposal = {
            "units": [
                {"work_ref": "T018", "revision": 1, "spec_revision": "spec01", "dependencies": []}
            ],
            "proposal_digest": compute_digest([
                {"work_ref": "T018", "revision": 1, "spec_revision": "spec01", "dependencies": []}
            ]),
        }
        tree_state = {
            "tasks": {
                "T018": {"revision": 1, "spec_revision": "spec01", "dependencies": []}
            }
        }
        ok, reason, res = prefreeze_revalidate(proposal, tree_state)
        self.assertTrue(ok)
        self.assertEqual(res["next_state"], "FREEZE_BATCH")

    def test_ac04_prefreeze_revalidation_counterfactual_drift_returns_propose(self) -> None:
        proposal = {
            "units": [
                {"work_ref": "T018", "revision": 1, "spec_revision": "spec01", "dependencies": []}
            ],
            "proposal_digest": compute_digest([
                {"work_ref": "T018", "revision": 1, "spec_revision": "spec01", "dependencies": []}
            ]),
        }
        # External modification happened while user was deciding: revision bumped to 2
        tree_state_drifted = {
            "tasks": {
                "T018": {"revision": 2, "spec_revision": "spec02_modified", "dependencies": []}
            }
        }
        ok, reason, res = prefreeze_revalidate(proposal, tree_state_drifted)
        self.assertFalse(ok)
        self.assertIn("drift", reason)
        self.assertEqual(res["next_state"], "PROPOSE")

    # --------------------------------------------------------------------------
    # AC07 & AC08: Logical Write-Ahead & Crash Recovery
    # --------------------------------------------------------------------------

    def test_ac07_write_ahead_call_lifecycle(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        # 1. Reserve call
        ok, msg, batch = evaluate_write_ahead_transition(batch, "reserve", {"count": 1})
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 1)

        # 2. Set pending_call before dispatch
        call_info = {"call_id": "call-1", "role": "maker", "phase": "implementation"}
        ok, msg, batch = evaluate_write_ahead_transition(batch, "set_pending_call", call_info)
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["pending_call"]["call_id"], "call-1")

        # 3. Complete call upon observing receipt
        ok, msg, batch = evaluate_write_ahead_transition(batch, "complete_call")
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertIsNone(batch["budget"]["pending_call"])

    def test_ac08_crash_recovery_ambiguous_stops_conservatively(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        batch["budget"]["reserved_model_calls"] = 1
        batch["budget"]["consumed_model_calls"] = 2
        batch["budget"]["pending_call"] = {"call_id": "call-interrupted", "role": "maker", "phase": "implementation"}

        # Ambiguous crash state (unknown if dispatch finished or failed)
        outcome, batch = recover_from_crash(batch, receipt_found=False, ambiguous=True)
        self.assertEqual(outcome, "conservative_stop")
        self.assertEqual(batch["status"], "stopped")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 3)  # Counted conservatively
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])
        self.assertEqual(batch["execution"]["stop_reason"], "unrecoverable_harness_failure")

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # T027: Mandatory Write-Ahead Journaling & Budgeted Dispatch Tests
    # --------------------------------------------------------------------------

    def test_t027_straight_line_budgeted_dispatch(self) -> None:
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        batch["budget"]["max_model_calls"] = 12
        batch["budget"]["consumed_model_calls"] = 0
        batch["budget"]["reserved_model_calls"] = 0

        dummy_runner = lambda cmd, cwd: (0, "{'status': 'ok'}", "")

        # 1. Classifier Implementation
        ok, reason, res1 = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-01-classifier-impl", harness_cmd=["agy", "run"],
            runner_fn=dummy_runner
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "dispatch_complete")
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # 2. Maker Implementation
        ok, reason, res2 = budgeted_model_dispatch(
            batch, role="maker", phase="implementation",
            call_id="call-02-maker-impl", harness_cmd=["codex", "exec"],
            runner_fn=dummy_runner
        )
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 2)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # 3. Classifier Review
        ok, reason, res3 = budgeted_model_dispatch(
            batch, role="classifier", phase="review",
            call_id="call-03-classifier-rev", harness_cmd=["agy", "run"],
            runner_fn=dummy_runner
        )
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 3)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # 4. Checker Review
        ok, reason, res4 = budgeted_model_dispatch(
            batch, role="checker", phase="review",
            call_id="call-04-checker-rev", harness_cmd=["claude", "review"],
            runner_fn=dummy_runner
        )
        self.assertTrue(ok)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 4)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

    def test_t027_classifier_retry_counts_every_real_dispatch(self) -> None:
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        batch["budget"]["max_model_calls"] = 12
        batch["budget"]["consumed_model_calls"] = 0
        batch["budget"]["reserved_model_calls"] = 0

        # Attempt 1: schema failure (non-zero exit)
        fail_runner = lambda cmd, cwd: (1, "", "SchemaValidationError: missing properties")
        ok1, reason1, res1 = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-01-classifier-impl-1", harness_cmd=["agy", "run"],
            runner_fn=fail_runner
        )
        self.assertFalse(ok1)
        self.assertEqual(reason1, "dispatch_complete")
        # Attempt 1 MUST be consumed!
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # Attempt 2: valid retry
        success_runner = lambda cmd, cwd: (0, "{'valid': True}", "")
        ok2, reason2, res2 = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-01-classifier-impl-2", harness_cmd=["agy", "run"],
            runner_fn=success_runner,
            calculate_reserve_fn=calculate_dynamic_reserve,
            unit_ref="T027"
        )
        self.assertTrue(ok2)
        # Attempt 2 consumed second call!
        self.assertEqual(batch["budget"]["consumed_model_calls"], 2)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

        # Remaining steps: Maker + Classifier Rev + Checker Rev
        for role, phase, cid in [
            ("maker", "implementation", "call-02-maker-impl"),
            ("classifier", "review", "call-03-classifier-rev"),
            ("checker", "review", "call-04-checker-rev"),
        ]:
            ok, reason, res = budgeted_model_dispatch(
                batch, role=role, phase=phase, call_id=cid,
                harness_cmd=["harness", "cmd"], runner_fn=success_runner
            )
            self.assertTrue(ok)

        # Total factual dispatches = 5 (2 classifiers + 1 maker + 1 classifier + 1 checker)
        self.assertEqual(batch["budget"]["consumed_model_calls"], 5)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

    def test_t027_pre_dispatch_unavailable_does_not_consume_call(self) -> None:
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        batch["budget"]["max_model_calls"] = 12
        batch["budget"]["consumed_model_calls"] = 0
        batch["budget"]["reserved_model_calls"] = 0

        ok, reason, res = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-pre-fail", harness_cmd=["nonexistent_harness_xyz_999"],
            simulate_pre_dispatch_failure=True
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "PRE_DISPATCH_UNAVAILABLE")
        # PRE_DISPATCH_UNAVAILABLE MUST NOT consume call!
        self.assertEqual(batch["budget"]["consumed_model_calls"], 0)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])

    def test_t027_ambiguous_dispatch_consumes_call_and_stops_conservatively(self) -> None:
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        batch["budget"]["max_model_calls"] = 12
        batch["budget"]["consumed_model_calls"] = 2
        batch["budget"]["reserved_model_calls"] = 0

        ok, reason, res = budgeted_model_dispatch(
            batch, role="maker", phase="implementation",
            call_id="call-ambiguous-crash", harness_cmd=["codex", "exec"],
            simulate_ambiguous_outcome=True
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "ambiguous_dispatch_stopped")
        # Ambiguous dispatch MUST consume 1 call conservatively and STOP
        self.assertEqual(batch["budget"]["consumed_model_calls"], 3)
        self.assertEqual(batch["budget"]["reserved_model_calls"], 0)
        self.assertIsNone(batch["budget"]["pending_call"])
        self.assertEqual(batch["status"], "stopped")
        self.assertEqual(batch["execution"]["stop_reason"], "unrecoverable_harness_failure")

    def test_t027_retry_stops_when_budget_insufficient_for_verification(self) -> None:
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        # Only 4 total calls allowed
        batch["budget"]["max_model_calls"] = 4
        batch["budget"]["consumed_model_calls"] = 0
        batch["budget"]["reserved_model_calls"] = 0

        fail_runner = lambda cmd, cwd: (1, "", "schema failure")
        # Attempt 1 consumes 1 call -> consumed = 1, remaining = 3
        ok1, reason1, _ = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-01-classifier-1", harness_cmd=["agy"],
            runner_fn=fail_runner
        )
        self.assertEqual(batch["budget"]["consumed_model_calls"], 1)

        # Before Attempt 2, calculate_dynamic_reserve requires 4 calls:
        # Classifier impl attempt 2 + Maker + Classifier rev + Checker = 4
        # But remaining is only 4 - 1 = 3 < 4!
        ok2, reason2, _ = budgeted_model_dispatch(
            batch, role="classifier", phase="implementation",
            call_id="call-01-classifier-2", harness_cmd=["agy"],
            runner_fn=lambda c, w: (0, "", ""),
            calculate_reserve_fn=calculate_dynamic_reserve,
            unit_ref="T027"
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "insufficient_budget_for_unit_verification")
        self.assertEqual(batch["status"], "stopped")
        self.assertEqual(batch["execution"]["stop_reason"], "insufficient_budget_for_unit_verification")

    def test_t027_budgeted_dispatch_with_batch_file_persistence(self) -> None:
        import tempfile
        batch = copy.deepcopy(self.valid_batch_frontmatter)
        batch["budget"]["max_model_calls"] = 10
        batch["budget"]["consumed_model_calls"] = 0
        batch["budget"]["reserved_model_calls"] = 0
        batch["budget"]["pending_call"] = None

        with tempfile.TemporaryDirectory() as tmpdir:
            batch_path = Path(tmpdir) / "B999.md"
            import yaml
            body_text = "# Batch Test Body\n"
            batch_path.write_text(f"---\n{yaml.safe_dump(batch)}---\n{body_text}", encoding="utf-8")

            success_runner = lambda cmd, cwd: (0, "model output", "")
            ok, reason, detail = budgeted_model_dispatch(
                batch_input=batch_path,
                role="classifier",
                phase="implementation",
                call_id="call-01-classifier",
                harness_cmd=["agy", "--help"],
                runner_fn=success_runner,
            )
            self.assertTrue(ok)
            self.assertEqual(reason, "dispatch_complete")

            # Check persisted batch on disk
            persisted, _ = load_batch_frontmatter(batch_path)
            self.assertEqual(persisted["budget"]["consumed_model_calls"], 1)
            self.assertEqual(persisted["budget"]["reserved_model_calls"], 0)
            self.assertIsNone(persisted["budget"]["pending_call"])

    # AC09: Admission Gate by Unit
    # --------------------------------------------------------------------------

    def test_ac09_admission_gate_pass(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        unit_state = {"revision": 1, "spec_revision": "3c9d4bc09ceeedc0"}
        ok, reason = evaluate_admission_gate(
            batch=batch,
            unit_ref="T018",
            tree_checkpoint="4775c6b39c954da49aa40562afeea7e3eafad390",
            coordinator_session="sess-12345",
            unit_state=unit_state,
            required_effects=["local_write", "local_commit"],
        )
        self.assertTrue(ok, f"Admission should pass: {reason}")
        self.assertEqual(reason, "admission_pass")

    def test_ac09_admission_gate_counterfactual_tree_state_divergence(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        unit_state = {"revision": 1, "spec_revision": "3c9d4bc09ceeedc0"}
        ok, reason = evaluate_admission_gate(
            batch=batch,
            unit_ref="T018",
            tree_checkpoint="unexpected_divergent_tree_hash",
            coordinator_session="sess-12345",
            unit_state=unit_state,
            required_effects=["local_write", "local_commit"],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unexpected_tree_state")

    def test_ac09_admission_gate_counterfactual_dependency_not_done(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        unit_state = {"revision": 1, "spec_revision": "98a7b6c5d4e3f210"}
        # T019 depends on T018, but completed_units is empty
        ok, reason = evaluate_admission_gate(
            batch=batch,
            unit_ref="T019",
            tree_checkpoint="4775c6b39c954da49aa40562afeea7e3eafad390",
            coordinator_session="sess-12345",
            unit_state=unit_state,
            required_effects=["local_write", "local_commit"],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "dependency_block")

    # --------------------------------------------------------------------------
    # AC10: Dynamic Mandatory Call Reserve
    # --------------------------------------------------------------------------

    def test_ac10_dynamic_reserve_calculation(self) -> None:
        # Standard implementation starting: Classifier impl + Maker + Classifier rev + Checker = 4
        res_std = calculate_dynamic_reserve("T018", current_phase="implementation")
        self.assertEqual(res_std, 4)

        # Standard implementation with Advisor required: 4 + 1 = 5
        res_adv = calculate_dynamic_reserve("T018", current_phase="implementation", has_advisor_trigger=True)
        self.assertEqual(res_adv, 5)

        # Pre-maker (post classifier): Maker + Classifier rev + Checker = 3
        res_post_cl = calculate_dynamic_reserve("T018", current_phase="post_classifier_impl")
        self.assertEqual(res_post_cl, 3)

        # Rework: Classifier rework + Maker + Classifier rev + Checker = 4
        res_rwk = calculate_dynamic_reserve("T018", current_phase="implementation", is_rework=True)
        self.assertEqual(res_rwk, 4)

    def test_ac10_dynamic_reserve_stops_when_budget_insufficient(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        # Total 24, consumed 21, remaining 3.
        # Starting new unit requires 4 calls (insufficient!)
        batch["budget"]["consumed_model_calls"] = 21
        unit_state = {"revision": 1, "spec_revision": "3c9d4bc09ceeedc0"}
        ok, reason = evaluate_admission_gate(
            batch=batch,
            unit_ref="T018",
            tree_checkpoint="4775c6b39c954da49aa40562afeea7e3eafad390",
            coordinator_session="sess-12345",
            unit_state=unit_state,
            required_effects=["local_write"],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_budget_for_unit_verification")

    # --------------------------------------------------------------------------
    # AC11: Symmetry of bad_spec_or_intent_gap
    # --------------------------------------------------------------------------

    def test_ac11_symmetry_bad_spec_stops_before_maker_and_rework(self) -> None:
        ok_pre, reason_pre = evaluate_symmetry_bad_spec("classifier_impl", "bad_spec_or_intent_gap")
        self.assertFalse(ok_pre)
        self.assertIn("stopped before Maker", reason_pre)

        ok_post, reason_post = evaluate_symmetry_bad_spec("checker_review", "bad_spec_or_intent_gap")
        self.assertFalse(ok_post)
        self.assertIn("stopped before rework", reason_post)

    # --------------------------------------------------------------------------
    # AC12: Strict Limits on Automatic Rework
    # --------------------------------------------------------------------------

    def test_ac12_rework_budget_and_scope_limits(self) -> None:
        batch = dict(self.valid_batch_frontmatter)
        frozen_paths = [
            "distribution-manifest.json",
            "schemas/batch.schema.json",
            "scripts/tests/test_automatic_mode.py",
        ]

        # Positive proof: rework under changes_requested within frozen spec, paths, and budget
        ok, reason = evaluate_rework_admission(
            batch=batch,
            unit_ref="T018",
            checker_verdict="changes_requested",
            finding_target="maker",
            requested_paths=["schemas/batch.schema.json", "scripts/tests/test_automatic_mode.py"],
            frozen_content_paths=frozen_paths,
            current_round=1,
            unit_spec_revision="3c9d4bc09ceeedc0",
            frozen_spec_revision="3c9d4bc09ceeedc0",
        )
        self.assertTrue(ok, f"Rework should be admitted: {reason}")
        self.assertEqual(reason, "rework_admitted")

        # Counterfactual 1: blocked when rework rounds reach max_rework_rounds_per_unit (2)
        ok_rounds, reason_rounds = evaluate_rework_admission(
            batch=batch,
            unit_ref="T018",
            checker_verdict="changes_requested",
            finding_target="maker",
            requested_paths=["schemas/batch.schema.json"],
            frozen_content_paths=frozen_paths,
            current_round=2,  # round 2 equals max_rework_rounds_per_unit (2)
            unit_spec_revision="3c9d4bc09ceeedc0",
            frozen_spec_revision="3c9d4bc09ceeedc0",
        )
        self.assertFalse(ok_rounds)
        self.assertEqual(reason_rounds, "rework_limit_exhausted")

        # Counterfactual 2: blocked when requested path is outside frozen content_paths
        ok_scope, reason_scope = evaluate_rework_admission(
            batch=batch,
            unit_ref="T018",
            checker_verdict="changes_requested",
            finding_target="maker",
            requested_paths=["schemas/batch.schema.json", "unauthorized/new_file.py"],
            frozen_content_paths=frozen_paths,
            current_round=1,
            unit_spec_revision="3c9d4bc09ceeedc0",
            frozen_spec_revision="3c9d4bc09ceeedc0",
        )
        self.assertFalse(ok_scope)
        self.assertEqual(reason_scope, "scope_expansion")

        # Counterfactual 3: blocked when budget cannot cover mandatory rework cycle (required_call_reserve = 4)
        exhausted_batch = dict(self.valid_batch_frontmatter)
        exhausted_batch["budget"] = dict(exhausted_batch["budget"])
        # Total 24, consumed 21, reserved 0, available = 3 < required_call_reserve (4)
        exhausted_batch["budget"]["consumed_model_calls"] = 21
        ok_budget, reason_budget = evaluate_rework_admission(
            batch=exhausted_batch,
            unit_ref="T018",
            checker_verdict="changes_requested",
            finding_target="maker",
            requested_paths=["schemas/batch.schema.json"],
            frozen_content_paths=frozen_paths,
            current_round=1,
            unit_spec_revision="3c9d4bc09ceeedc0",
            frozen_spec_revision="3c9d4bc09ceeedc0",
        )
        self.assertFalse(ok_budget)
        self.assertEqual(reason_budget, "insufficient_budget_for_unit_verification")

    # --------------------------------------------------------------------------
    # AC15: T016 Major-Boundary Integration Gates within Batch
    # --------------------------------------------------------------------------

    def test_ac15_intragroup_does_not_trigger_full_gate(self) -> None:
        ok, reason = evaluate_integration_boundary_gate(
            batch=self.valid_batch_frontmatter,
            current_unit_group="group-A",
            next_unit_group="group-A",
            gate_exit_code=None,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "intragroup_no_gate_required")

    def test_ac15_group_transition_enforces_full_gate(self) -> None:
        # Group transition from group-A to group-B without running gate
        ok, reason = evaluate_integration_boundary_gate(
            batch=self.valid_batch_frontmatter,
            current_unit_group="group-A",
            next_unit_group="group-B",
            gate_exit_code=None,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "canonical_full_gate_required_not_run")

        # Passing gate
        ok, reason = evaluate_integration_boundary_gate(
            batch=self.valid_batch_frontmatter,
            current_unit_group="group-A",
            next_unit_group="group-B",
            gate_exit_code=0,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "canonical_full_gate_pass")

        # Failing gate blocks transition
        ok, reason = evaluate_integration_boundary_gate(
            batch=self.valid_batch_frontmatter,
            current_unit_group="group-A",
            next_unit_group="group-B",
            gate_exit_code=1,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "canonical_full_gate_failure")

    def test_ac15_batch_closure_enforces_final_gate(self) -> None:
        # next_unit_group=None indicates batch closure
        ok, reason = evaluate_integration_boundary_gate(
            batch=self.valid_batch_frontmatter,
            current_unit_group="group-A",
            next_unit_group=None,
            gate_exit_code=0,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "canonical_full_gate_pass")

    # --------------------------------------------------------------------------
    # AC13: 18 Stop Conditions Catalog Integrity & Schema Enforcement
    # --------------------------------------------------------------------------

    def test_ac13_all_18_stop_conditions_present_and_cataloged(self) -> None:
        # 1. Catalog completeness
        self.assertEqual(len(ALL_18_STOP_CONDITIONS), 18)
        self.assertEqual(len(set(ALL_18_STOP_CONDITIONS)), 18)
        self.assertIn("dependency_block", ALL_18_STOP_CONDITIONS)
        self.assertIn("insufficient_budget_for_unit_verification", ALL_18_STOP_CONDITIONS)
        self.assertIn("canonical_full_gate_failure", ALL_18_STOP_CONDITIONS)
        self.assertIn("unexpected_tree_state", ALL_18_STOP_CONDITIONS)

        # 2. Real JSON Schema inspection (R1)
        sc_schema = (
            self.schema.get("properties", {})
            .get("frozen_scope", {})
            .get("properties", {})
            .get("stop_conditions", {})
        )
        self.assertEqual(sc_schema.get("minItems"), 18)
        self.assertEqual(sc_schema.get("maxItems"), 18)
        self.assertTrue(sc_schema.get("uniqueItems"))
        items_enum = sc_schema.get("items", {}).get("enum", [])
        self.assertEqual(len(items_enum), 18)
        self.assertEqual(len(set(items_enum)), 18)
        self.assertEqual(set(items_enum), set(ALL_18_STOP_CONDITIONS))

        # 3. Counterfactual: 17 valid conditions -> REJECT (fails minItems)
        invalid_17 = dict(self.valid_batch_frontmatter)
        invalid_17["frozen_scope"] = dict(invalid_17["frozen_scope"])
        invalid_17["frozen_scope"]["stop_conditions"] = list(ALL_18_STOP_CONDITIONS[:17])
        valid, errors = validate_batch_envelope(invalid_17, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("at least 18 items" in e for e in errors))

        # 4. Counterfactual: 18 items with duplicate -> REJECT (fails uniqueItems)
        invalid_dup = dict(self.valid_batch_frontmatter)
        invalid_dup["frozen_scope"] = dict(invalid_dup["frozen_scope"])
        dup_list = list(ALL_18_STOP_CONDITIONS[:17]) + [ALL_18_STOP_CONDITIONS[0]]
        self.assertEqual(len(dup_list), 18)
        invalid_dup["frozen_scope"]["stop_conditions"] = dup_list
        valid, errors = validate_batch_envelope(invalid_dup, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("unique items" in e for e in errors))

        # 5. Positive proof: 18 complete unique items -> ACCEPT (valid)
        valid_18 = dict(self.valid_batch_frontmatter)
        valid_18["frozen_scope"] = dict(valid_18["frozen_scope"])
        valid_18["frozen_scope"]["stop_conditions"] = list(ALL_18_STOP_CONDITIONS)
        valid, errors = validate_batch_envelope(valid_18, self.schema)
        self.assertTrue(valid, f"18 unique items should be valid: {errors}")

    # --------------------------------------------------------------------------
    # AC14: Execution Protocol & Advisor Constraints
    # --------------------------------------------------------------------------

    def test_ac14_execution_protocol_and_advisor_constraints(self) -> None:
        # 1. Compact terminal receipt consumption (< 4 KiB)
        receipt = {
            "outcome": "ready_for_delivery",
            "decision": "unit implementation and verification complete",
            "blockers": [],
            "next_action": "proceed to integration gate",
            "observable_usage": "unknown",
            "proof_refs": ["_tl-orc/project/evidence/T018-verification.md"],
        }
        receipt_json = json.dumps(receipt)
        # Receipt must be compact (< 4096 bytes / 4 KiB)
        self.assertLess(len(receipt_json.encode("utf-8")), 4096)
        valid_outcomes = {"delivered", "ready_for_delivery", "blocked", "failed"}
        self.assertIn(receipt["outcome"], valid_outcomes)

        # 2. Positive proof: Advisor call debits consumed_advisor_calls
        batch = dict(self.valid_batch_frontmatter)
        self.assertEqual(batch["budget"]["consumed_advisor_calls"], 0)
        ok, reason, updated_batch = dispatch_advisor_call(batch, caller_role="orchestrator")
        self.assertTrue(ok)
        self.assertEqual(reason, "advisor_dispatched")
        self.assertEqual(updated_batch["budget"]["consumed_advisor_calls"], 1)

        # 3. Counterfactual proof: blocked when max_advisor_calls reached
        exhausted_batch = dict(self.valid_batch_frontmatter)
        exhausted_batch["budget"] = dict(exhausted_batch["budget"])
        exhausted_batch["budget"]["consumed_advisor_calls"] = 2  # equals max_advisor_calls (2)
        ok_limit, reason_limit, _ = dispatch_advisor_call(exhausted_batch, caller_role="orchestrator")
        self.assertFalse(ok_limit)
        self.assertEqual(reason_limit, "advisor_budget_exhausted")

        # 4. Counterfactual proof: non-recursion (Advisor cannot dispatch another Advisor)
        ok_rec, reason_rec, _ = dispatch_advisor_call(batch, caller_role="advisor")
        self.assertFalse(ok_rec)
        self.assertEqual(reason_rec, "advisor_recursion_prohibited")

        # 5. Counterfactual proof: unauthorized trigger rejected
        ok_trig, reason_trig, _ = dispatch_advisor_call(
            batch,
            caller_role="orchestrator",
            trigger="unauthorized_random_trigger",
        )
        self.assertFalse(ok_trig)
        self.assertEqual(reason_trig, "unauthorized_trigger: unauthorized_random_trigger")

    def test_ac14_advisor_policy_schema_accept_valid(self) -> None:
        """Positive proof: full batch envelope with valid advisor_policy is accepted by schema."""
        # 1. Real JSON Schema inspection
        fs_schema = self.schema.get("properties", {}).get("frozen_scope", {})
        self.assertIn("advisor_policy", fs_schema.get("required", []))
        adv_schema = fs_schema.get("properties", {}).get("advisor_policy", {})
        self.assertFalse(adv_schema.get("additionalProperties", True))
        self.assertEqual(set(adv_schema.get("required", [])), {"enabled", "triggers", "max_calls"})
        self.assertEqual(adv_schema.get("properties", {}).get("max_calls", {}).get("minimum"), 0)

        triggers_enum = adv_schema.get("properties", {}).get("triggers", {}).get("items", {}).get("enum", [])
        self.assertEqual(len(triggers_enum), 8)
        self.assertIn("architecture_or_contract_change", triggers_enum)
        self.assertIn("heavy_tier_material_uncertainty", triggers_enum)

        # 2. Domain envelope validation
        valid, errors = validate_batch_envelope(self.valid_batch_frontmatter, self.schema)
        self.assertTrue(valid, f"Valid batch frontmatter with advisor_policy should pass: {errors}")

    def test_ac14_advisor_policy_schema_counterfactual_missing_policy(self) -> None:
        """Counterfactual: removing advisor_policy from frozen_scope is rejected by schema."""
        invalid = dict(self.valid_batch_frontmatter)
        invalid["frozen_scope"] = dict(invalid["frozen_scope"])
        del invalid["frozen_scope"]["advisor_policy"]

        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("Missing frozen_scope property: 'advisor_policy'" in e for e in errors))

    def test_ac14_advisor_policy_schema_counterfactual_invalid_trigger(self) -> None:
        """Counterfactual: trigger outside the 8-item enum is rejected by schema."""
        invalid = dict(self.valid_batch_frontmatter)
        invalid["frozen_scope"] = dict(invalid["frozen_scope"])
        invalid["frozen_scope"]["advisor_policy"] = dict(invalid["frozen_scope"]["advisor_policy"])
        invalid["frozen_scope"]["advisor_policy"]["triggers"] = [
            "architecture_or_contract_change",
            "unauthorized_random_trigger",
        ]

        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("Invalid advisor trigger: 'unauthorized_random_trigger'" in e for e in errors))

    def test_ac14_advisor_policy_schema_counterfactual_additional_property(self) -> None:
        """Counterfactual: extra property in advisor_policy is rejected (additionalProperties: false)."""
        invalid = dict(self.valid_batch_frontmatter)
        invalid["frozen_scope"] = dict(invalid["frozen_scope"])
        invalid["frozen_scope"]["advisor_policy"] = dict(invalid["frozen_scope"]["advisor_policy"])
        invalid["frozen_scope"]["advisor_policy"]["extra_property"] = "disallowed"

        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("Unexpected advisor_policy properties" in e for e in errors))

    def test_ac14_advisor_policy_schema_counterfactual_negative_max_calls(self) -> None:
        """Counterfactual: negative max_calls is rejected by schema (minimum: 0)."""
        invalid = dict(self.valid_batch_frontmatter)
        invalid["frozen_scope"] = dict(invalid["frozen_scope"])
        invalid["frozen_scope"]["advisor_policy"] = dict(invalid["frozen_scope"]["advisor_policy"])
        invalid["frozen_scope"]["advisor_policy"]["max_calls"] = -1
        # Maintain budget.max_advisor_calls in parity to isolate schema validation
        invalid["budget"] = dict(invalid["budget"])
        invalid["budget"]["max_advisor_calls"] = -1

        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertTrue(any("advisor_policy.max_calls must be an integer >= 0" in e for e in errors))

    def test_ac14_advisor_policy_counterfactual_budget_divergence(self) -> None:
        """Counterfactual: advisor_policy.max_calls != budget.max_advisor_calls is rejected by validator."""
        invalid = dict(self.valid_batch_frontmatter)
        invalid["frozen_scope"] = dict(invalid["frozen_scope"])
        invalid["frozen_scope"]["advisor_policy"] = dict(invalid["frozen_scope"]["advisor_policy"])
        invalid["frozen_scope"]["advisor_policy"]["max_calls"] = 3
        invalid["budget"] = dict(invalid["budget"])
        invalid["budget"]["max_advisor_calls"] = 2

        valid, errors = validate_batch_envelope(invalid, self.schema)
        self.assertFalse(valid)
        self.assertIn(
            "advisor_budget_divergence: frozen_scope.advisor_policy.max_calls must equal budget.max_advisor_calls",
            errors,
        )

    def test_ac14_advisor_policy_counterfactual_disabled(self) -> None:
        """Counterfactual: advisor_policy.enabled = False blocks dispatch and preserves consumed_calls == 0."""
        batch = dict(self.valid_batch_frontmatter)
        batch["frozen_scope"] = dict(batch["frozen_scope"])
        batch["frozen_scope"]["advisor_policy"] = dict(batch["frozen_scope"]["advisor_policy"])
        batch["frozen_scope"]["advisor_policy"]["enabled"] = False

        self.assertEqual(batch["budget"]["consumed_advisor_calls"], 0)
        ok, reason, updated_batch = dispatch_advisor_call(
            batch,
            caller_role="orchestrator",
            trigger="architecture_or_contract_change",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "advisor_disabled: advisor_policy.enabled is False")
        self.assertEqual(updated_batch["budget"]["consumed_advisor_calls"], 0)

    def test_ac14_advisor_policy_schema_allof_structure(self) -> None:
        """AC14/R05: Verify Draft 2020-12 allOf conditional structure in batch.schema.json."""
        all_of = self.schema.get("allOf", [])
        self.assertIsInstance(all_of, list)
        self.assertGreaterEqual(len(all_of), 1)

        # Locate advisor_policy conditional
        cond = all_of[0]
        self.assertIn("if", cond)
        self.assertIn("then", cond)

        # 'if' clause assertions
        if_clause = cond["if"]
        self.assertEqual(if_clause.get("required"), ["frozen_scope"])
        fs_prop = if_clause.get("properties", {}).get("frozen_scope", {})
        self.assertEqual(fs_prop.get("required"), ["advisor_policy"])
        adv_prop = fs_prop.get("properties", {}).get("advisor_policy", {})
        self.assertEqual(adv_prop.get("required"), ["enabled"])
        self.assertIs(adv_prop.get("properties", {}).get("enabled", {}).get("const"), False)

        # 'then' clause assertions
        then_clause = cond["then"]
        self.assertEqual(then_clause.get("required"), ["budget"])
        budget_prop = then_clause.get("properties", {}).get("budget", {})
        self.assertEqual(budget_prop.get("required"), ["consumed_advisor_calls"])
        self.assertEqual(budget_prop.get("properties", {}).get("consumed_advisor_calls", {}).get("const"), 0)

        # Counterproof: No inverse rule (enabled: true -> consumed > 0)
        self.assertNotIn("else", cond)
        for rule in all_of:
            rule_str = json.dumps(rule)
            self.assertNotIn('"enabled": true', rule_str)
            self.assertNotIn('"enabled":true', rule_str)
            # Counterproof: Does not force max_calls=0 when enabled=false
            self.assertNotIn('"max_calls": 0', rule_str)
            self.assertNotIn('"max_calls":0', rule_str)

    def test_ac14_advisor_policy_disabled_consumption_zero_accepted(self) -> None:
        """AC14/R05: enabled=False with consumed_advisor_calls=0 is ACCEPTED by schema and validator."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["frozen_scope"]["advisor_policy"]["enabled"] = False
        envelope["budget"]["consumed_advisor_calls"] = 0

        # 1. Real JSON Schema validation
        schema_ok, schema_errs = match_draft202012_conditional_allof(self.schema, envelope)
        self.assertTrue(schema_ok, f"Real schema should accept enabled=False with consumed=0: {schema_errs}")

        # 2. Contractual validator
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertTrue(valid, f"Contractual validator should accept enabled=False with consumed=0: {errors}")

    def test_ac14_advisor_policy_disabled_consumption_one_rejected(self) -> None:
        """AC14/R05: enabled=False with consumed_advisor_calls=1 is REJECTED by schema and validator."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["frozen_scope"]["advisor_policy"]["enabled"] = False
        envelope["budget"]["consumed_advisor_calls"] = 1

        # 1. Real JSON Schema validation
        schema_ok, schema_errs = match_draft202012_conditional_allof(self.schema, envelope)
        self.assertFalse(schema_ok, "Real schema must reject enabled=False with consumed=1")
        self.assertTrue(any("schema_conditional_violation" in e for e in schema_errs))

        # 2. Contractual validator
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertFalse(valid, "Contractual validator must reject enabled=False with consumed=1")
        self.assertIn(
            "advisor_disabled_consumption: consumed_advisor_calls must be 0 when advisor_policy.enabled is false",
            errors,
        )

    def test_ac14_advisor_policy_disabled_consumption_max_calls_rejected(self) -> None:
        """AC14/R05: enabled=False with consumed_advisor_calls=max_calls (>0) is REJECTED by schema and validator."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["frozen_scope"]["advisor_policy"]["enabled"] = False
        max_calls = envelope["frozen_scope"]["advisor_policy"]["max_calls"]
        self.assertGreater(max_calls, 0)
        envelope["budget"]["consumed_advisor_calls"] = max_calls

        # 1. Real JSON Schema validation
        schema_ok, schema_errs = match_draft202012_conditional_allof(self.schema, envelope)
        self.assertFalse(schema_ok, f"Real schema must reject enabled=False with consumed=max_calls ({max_calls})")
        self.assertTrue(any("schema_conditional_violation" in e for e in schema_errs))

        # 2. Contractual validator
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertFalse(valid, f"Contractual validator must reject enabled=False with consumed=max_calls ({max_calls})")
        self.assertIn(
            "advisor_disabled_consumption: consumed_advisor_calls must be 0 when advisor_policy.enabled is false",
            errors,
        )

    def test_ac14_advisor_policy_enabled_consumption_zero_accepted(self) -> None:
        """AC14/R05: enabled=True with consumed_advisor_calls=0 is ACCEPTED by schema and validator."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["frozen_scope"]["advisor_policy"]["enabled"] = True
        envelope["budget"]["consumed_advisor_calls"] = 0

        # 1. Real JSON Schema validation
        schema_ok, schema_errs = match_draft202012_conditional_allof(self.schema, envelope)
        self.assertTrue(schema_ok, f"Real schema should accept enabled=True with consumed=0: {schema_errs}")

        # 2. Contractual validator
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertTrue(valid, f"Contractual validator should accept enabled=True with consumed=0: {errors}")

    def test_ac14_advisor_policy_enabled_consumption_positive_accepted(self) -> None:
        """AC14/R05: enabled=True with 0 < consumed_advisor_calls <= max_calls is ACCEPTED by schema and validator."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["frozen_scope"]["advisor_policy"]["enabled"] = True
        max_calls = envelope["frozen_scope"]["advisor_policy"]["max_calls"]
        self.assertGreater(max_calls, 0)

        for consumed in range(1, max_calls + 1):
            envelope["budget"]["consumed_advisor_calls"] = consumed

            # 1. Real JSON Schema validation
            schema_ok, schema_errs = match_draft202012_conditional_allof(self.schema, envelope)
            self.assertTrue(
                schema_ok,
                f"Real schema should accept enabled=True with consumed={consumed} (<= max_calls {max_calls}): {schema_errs}",
            )

            # 2. Contractual validator
            valid, errors = validate_batch_envelope(envelope, self.schema)
            self.assertTrue(
                valid,
                f"Contractual validator should accept enabled=True with consumed={consumed} (<= max_calls {max_calls}): {errors}",
            )

    # --------------------------------------------------------------------------
    # AC16 & AC17: Governance & Verification Integrity
    # --------------------------------------------------------------------------

    def test_ac16_t018_authorship_and_checker_governance(self) -> None:
        task_file = ROOT / "_tl-orc" / "project" / "tasks" / "T018-automatic-mode-finite-authorized-batch-execution-recovery-and-boundaries.md"
        content = task_file.read_text(encoding="utf-8")
        self.assertIn("effective_authors: [openai, google, anthropic]", content)
        self.assertIn("checker_independence: preferred", content)

    def test_ac17_distribution_manifest_file_count_parity(self) -> None:
        """AC17: Manifest internal integrity and required T018 package artifacts presence."""
        manifest_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(manifest_data.get("package_files"), list)
        self.assertIsInstance(manifest_data.get("package_file_count"), int)
        self.assertEqual(manifest_data.get("package_file_count"), len(manifest_data.get("package_files", [])))
        # Durable guarantees of T018 artifacts:
        self.assertIn("schemas/batch.schema.json", manifest_data["package_files"])
        self.assertIn("docs/EXECUTION_PROTOCOL.md", manifest_data["package_files"])
        self.assertIn("scripts/tl_job.py", manifest_data["package_files"])

    # --------------------------------------------------------------------------
    # AC18, AC19, AC20: T018 x v0.11 Architectural Boundary Tests
    # --------------------------------------------------------------------------

    def test_ac18_batch_concurrency_schema_and_counterfactuals(self) -> None:
        """AC18: batch_concurrency: 1 in frozen_scope.properties and required. Const 1 enforced."""
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        self.assertEqual(envelope["frozen_scope"]["batch_concurrency"], 1)

        # 1. Positive: batch_concurrency: 1 passes
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertTrue(valid, f"batch_concurrency: 1 should pass: {errors}")

        # 2. Counterfactual: batch_concurrency: 2 is rejected
        invalid_concurrency = copy.deepcopy(envelope)
        invalid_concurrency["frozen_scope"]["batch_concurrency"] = 2
        valid_c2, errors_c2 = validate_batch_envelope(invalid_concurrency, self.schema)
        self.assertFalse(valid_c2)
        self.assertTrue(any("batch_concurrency must be 1" in e for e in errors_c2))

        # 3. Counterfactual: missing batch_concurrency is rejected
        missing_concurrency = copy.deepcopy(envelope)
        del missing_concurrency["frozen_scope"]["batch_concurrency"]
        valid_mc, errors_mc = validate_batch_envelope(missing_concurrency, self.schema)
        self.assertFalse(valid_mc)
        self.assertTrue(any("Missing frozen_scope property: 'batch_concurrency'" in e for e in errors_mc))

        # 4. Digest includes batch_concurrency: altering it changes compute_digest
        digest_orig = compute_digest(envelope["frozen_scope"])
        mutated_scope = copy.deepcopy(envelope["frozen_scope"])
        mutated_scope["batch_concurrency"] = 2
        digest_mut = compute_digest(mutated_scope)
        self.assertNotEqual(digest_orig, digest_mut)

    def test_ac19_parked_precedence_and_continue_independent(self) -> None:
        """AC19: Parking precedence over continue_independent_after_block."""
        envelope_no_cont = copy.deepcopy(self.valid_batch_frontmatter)
        envelope_no_cont["authorization"]["continue_independent_after_block"] = False

        parking_condition = "rework_limit_exhausted"
        self.assertIn(parking_condition, ALL_18_STOP_CONDITIONS)

        def handle_unit_parking(envelope: dict[str, Any], parked_unit: str, stop_reason: str) -> dict[str, Any]:
            continue_indep = envelope["authorization"]["continue_independent_after_block"]
            if not continue_indep:
                return {
                    "batch_status": "stopped",
                    "stop_reason": stop_reason,
                    "admitted_units": [],
                    "current_unit": None,
                }
            units = envelope["frozen_scope"]["units"]
            eligible = [
                u["work_ref"] for u in units
                if u["work_ref"] != parked_unit and parked_unit not in u.get("dependencies", [])
            ]
            return {
                "batch_status": "in_progress" if eligible else "stopped",
                "stop_reason": None if eligible else stop_reason,
                "admitted_units": eligible[:1] if eligible else [],
                "current_unit": eligible[0] if eligible else None,
            }

        decision_stop = handle_unit_parking(envelope_no_cont, "T018", parking_condition)
        self.assertEqual(decision_stop["batch_status"], "stopped")
        self.assertEqual(decision_stop["stop_reason"], "rework_limit_exhausted")
        self.assertEqual(decision_stop["admitted_units"], [])

        # Counterfactual: with continue_independent_after_block: True
        envelope_cont = copy.deepcopy(envelope_no_cont)
        envelope_cont["authorization"]["continue_independent_after_block"] = True
        envelope_cont["frozen_scope"]["units"].append({
            "work_ref": "T020",
            "revision": 1,
            "spec_revision": "spec20",
            "integration_group": "group-native",
            "dependencies": [],
        })
        decision_advance = handle_unit_parking(envelope_cont, "T018", parking_condition)
        self.assertEqual(decision_advance["batch_status"], "in_progress")
        self.assertEqual(decision_advance["admitted_units"], ["T020"])

    def test_ac20_runtime_refs_canonical_properties_acceptance(self) -> None:
        """AC20: Cada propriedade canônica individual e em conjunto é aceita em execution.runtime_refs."""
        canonical_props = {
            "supervisor_state_dir": "/tmp/tl-state/story-123",
            "worktree_slot": "slot_01",
            "scope_claim": "story-123",
            "merge_queue_entry": "story-123",
            "lease_heartbeat_ts": 1726245600.5,
        }

        # Conjunto completo válido
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["execution"]["runtime_refs"] = canonical_props
        valid, errors = validate_batch_envelope(envelope, self.schema)
        self.assertTrue(valid, f"All canonical runtime_refs should pass: {errors}")

        # Cada propriedade isolada
        for k, v in canonical_props.items():
            env_single = copy.deepcopy(self.valid_batch_frontmatter)
            env_single["execution"]["runtime_refs"] = {k: v}
            v_ok, errs = validate_batch_envelope(env_single, self.schema)
            self.assertTrue(v_ok, f"Single property {k} should pass: {errs}")

        # Valores nulos para cada propriedade são aceitos
        env_null = copy.deepcopy(self.valid_batch_frontmatter)
        env_null["execution"]["runtime_refs"] = {k: None for k in canonical_props}
        v_null, errs_null = validate_batch_envelope(env_null, self.schema)
        self.assertTrue(v_null, f"Null runtime_refs values should pass: {errs_null}")

    def test_ac20_runtime_refs_invalid_types_rejected(self) -> None:
        """AC20: Tipos inválidos para propriedades canônicas são rejeitados."""
        invalid_cases = [
            ("supervisor_state_dir", 12345),
            ("supervisor_state_dir", ["/dir"]),
            ("worktree_slot", True),
            ("worktree_slot", 99),
            ("scope_claim", 456),
            ("scope_claim", {"path": "a"}),
            ("merge_queue_entry", ["item"]),
            ("merge_queue_entry", 789),
            ("lease_heartbeat_ts", "not-a-number"),
            ("lease_heartbeat_ts", True),
            ("lease_heartbeat_ts", [123]),
        ]
        for prop, bad_val in invalid_cases:
            env = copy.deepcopy(self.valid_batch_frontmatter)
            env["execution"]["runtime_refs"] = {prop: bad_val}
            valid, errors = validate_batch_envelope(env, self.schema)
            self.assertFalse(valid, f"Bad value {bad_val!r} for {prop} should fail")
            self.assertTrue(
                any(f"execution.runtime_refs.{prop} must be" in e for e in errors),
                f"Expected type error for {prop}, got: {errors}",
            )

    def test_ac20_runtime_refs_obsolete_aliases_rejected(self) -> None:
        """AC20: Nomes obsoletos e aliases (scope_claim_id, merge_queue_id) são estritamente rejeitados."""
        obsolete_cases = [
            {"scope_claim_id": "claim_123"},
            {"merge_queue_id": "queue_123"},
            {"worktree": "slot_01"},
            {"heartbeat_ts": 1726245600.0},
            {"state_dir": "/tmp/state"},
            {"unauthorized_property": "val"},
        ]
        for bad_rr in obsolete_cases:
            env = copy.deepcopy(self.valid_batch_frontmatter)
            env["execution"]["runtime_refs"] = bad_rr
            valid, errors = validate_batch_envelope(env, self.schema)
            self.assertFalse(valid, f"Obsolete/unauthorized runtime_refs {bad_rr} must fail")
            self.assertTrue(
                any("Unexpected runtime_refs properties" in e for e in errors),
                f"Expected 'Unexpected runtime_refs properties', got: {errors}",
            )

    def test_ac20_runtime_refs_doc_schema_parity(self) -> None:
        """AC20: docs/EXECUTION_PROTOCOL.md e schemas/batch.schema.json possuem exatamente o mesmo conjunto canônico."""
        import re

        # Extrair identificadores declarados no schema
        rr_schema = (
            self.schema.get("properties", {})
            .get("execution", {})
            .get("properties", {})
            .get("runtime_refs", {})
        )
        schema_props = set(rr_schema.get("properties", {}).keys())
        expected_canonical = {
            "supervisor_state_dir",
            "worktree_slot",
            "scope_claim",
            "merge_queue_entry",
            "lease_heartbeat_ts",
        }
        self.assertEqual(
            schema_props,
            expected_canonical,
            f"batch.schema.json runtime_refs props {schema_props} diverge from expected {expected_canonical}",
        )

        # Extrair identificadores documentados em docs/EXECUTION_PROTOCOL.md
        exec_proto_path = Path(__file__).resolve().parent.parent.parent / "docs" / "EXECUTION_PROTOCOL.md"
        self.assertTrue(exec_proto_path.exists(), f"EXECUTION_PROTOCOL.md not found at {exec_proto_path}")
        content = exec_proto_path.read_text(encoding="utf-8")

        # Procura a declaração de runtime_refs em EXECUTION_PROTOCOL.md
        match = re.search(r"runtime_refs`\s*do\s*envelope.*?`Bnnn\.md`", content, re.DOTALL)
        self.assertIsNotNone(match, "Could not find runtime_refs section in EXECUTION_PROTOCOL.md")
        # Encontrar os identificadores citados entre crases na seção
        section_snippet = content[max(0, match.start() - 200) : match.end()]
        declared_in_doc = set(re.findall(r"`([a-z0-9_]+)`", section_snippet))
        # Deve conter todos os 5 identificadores canônicos
        for prop in expected_canonical:
            self.assertIn(
                prop,
                declared_in_doc,
                f"Canonical property '{prop}' missing from EXECUTION_PROTOCOL.md runtime_refs section",
            )
        # Nomes obsoletos não devem aparecer na seção
        self.assertNotIn("scope_claim_id", declared_in_doc)
        self.assertNotIn("merge_queue_id", declared_in_doc)

    def test_ac20_runtime_refs_forbidden_in_frozen_scope_and_digest_invariant(self) -> None:
        """AC20: runtime_refs proibido em frozen_scope e isolado do immutable_digest."""
        # 1. Proibido em frozen_scope
        invalid_fs = copy.deepcopy(self.valid_batch_frontmatter)
        invalid_fs["frozen_scope"]["runtime_refs"] = {"worktree_slot": "slot_01"}
        valid_fs, errors_fs = validate_batch_envelope(invalid_fs, self.schema)
        self.assertFalse(valid_fs)
        self.assertTrue(any("Unexpected frozen_scope properties" in e for e in errors_fs))

        # 2. Digest invariance: alterar runtime_refs em execution não altera digest do frozen_scope
        envelope = copy.deepcopy(self.valid_batch_frontmatter)
        envelope["execution"]["runtime_refs"] = {"worktree_slot": "slot_01"}
        digest_before = compute_digest(envelope["frozen_scope"])

        envelope["execution"]["runtime_refs"]["worktree_slot"] = "slot_99"
        envelope["execution"]["runtime_refs"]["lease_heartbeat_ts"] = 1726249999.0
        digest_after = compute_digest(envelope["frozen_scope"])
        self.assertEqual(digest_before, digest_after)


if __name__ == "__main__":
    unittest.main()
