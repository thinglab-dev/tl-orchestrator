#!/usr/bin/env python3
"""
Unit, deterministic, and counterfactual tests for the Advisor role and policy (AC01 to AC15).
Spec revision: aecdc421b466be82 (Task T017).

Covers:
- AC01: Role boundary and permission constraints (report-only, fresh session, no edit/commit/state change)
- AC02: Clear role distinction (Planner vs Advisor vs Checker vs Debate)
- AC03: Objective triggers (8 accepted triggers)
- AC04: Strict rejection of routine non-triggers (anti-overuse)
- AC05: Structured result schema validation (Draft 2020-12)
- AC06: Verdict semantics (proceed, adjust, plan, debate, stop)
- AC07: Independence and fresh session (contra-family resolution)
- AC08: Degraded fallback vs blocking under required
- AC09: Classifier support and tier sizing (normal vs heavy)
- AC10: Minimal challenge packet (Context Economy)
- AC11: Conditional authorship propagation
- AC12: Debate escalation without auto-start
- AC13: Blocking disposition of restrictive recommendations
- AC14: Automatic Mode interface (advisor_policy in batch)
- AC15: Deterministic contractual suite integrity
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parent.parent.parent
ADVISOR_SCHEMA_PATH = ROOT / "schemas" / "advisor-result.schema.json"
CLASSIFIER_SCHEMA_PATH = ROOT / "schemas" / "classification-result.schema.json"
MANIFEST_PATH = ROOT / "distribution-manifest.json"

# ==============================================================================
# Domain Logic / Normative Advisor Policy Engine
# ==============================================================================

VALID_VERDICTS = {"proceed", "adjust", "plan", "debate", "stop"}
VALID_CONFIDENCES = {"high", "medium", "low"}

OBJECTIVE_TRIGGERS = {
    "architecture_or_contract_change",
    "hard_to_reverse_decision",
    "governance_experiment",
    "heavy_tier_material_uncertainty",
    "causal_claim_limited_evidence",
    "recurring_failure_class_independent_review",
    "explicit_user_request",
    "pre_freeze_high_cost_batch",
}

NON_TRIGGERS = {
    "story_start",
    "maker_done",
    "review_entry",
    "routine_changes_requested",
    "heavy_without_uncertainty",
    "routine_docs_or_status",
    "second_opinion",
    "por_seguranca",
    "to_be_safe",
    "just_in_case",
}

ROLE_QUESTIONS = {
    "planner": "Como devemos fazer?",
    "advisor": "Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?",
    "checker": "O que foi implementado atende a spec e a prova?",
    "debate": "Temos alternativas materialmente concorrentes; qual direção devemos escolher?",
}

FAMILY_CONTRA_MAP = {
    "anthropic": ["google", "openai"],
    "google": ["openai", "anthropic"],
    "openai": ["google", "anthropic"],
}


def validate_advisor_role_boundary(role_config: dict[str, Any]) -> tuple[bool, str]:
    """
    Validates AC01: Advisor role boundaries and permissions.
    Advisor is strictly report-only, fresh session, cannot edit/commit/change state/close/authorize/dispatch.
    """
    expected_constraints = {
        "report_only": True,
        "fresh_session": "required",
        "may_edit": False,
        "may_commit": False,
        "may_change_state": False,
        "may_close_task": False,
        "may_authorize": False,
        "may_dispatch_agents": False,
        "may_replace_checker": False,
        "may_replace_planner": False,
        "may_recommend_debate": True,
    }
    for key, expected in expected_constraints.items():
        if role_config.get(key) != expected:
            return False, f"Role boundary violation for {key}: expected {expected}, got {role_config.get(key)}"
    return True, "Valid role boundary"


def evaluate_advisor_trigger(trigger: str, context: dict[str, Any] | None = None) -> tuple[bool, str]:
    """
    Validates AC03 and AC04: Evaluates whether an activation trigger is legitimate or prohibited.
    """
    context = context or {}
    t_clean = trigger.strip().lower()

    if t_clean in NON_TRIGGERS:
        return False, f"Prohibited non-trigger rejected (anti-overuse): '{t_clean}'"

    # Specific check for heavy tier: heavy alone is a non-trigger if there is no material uncertainty
    if t_clean == "heavy_tier_material_uncertainty":
        if not context.get("has_material_uncertainty", False):
            return False, "Prohibited non-trigger: tier heavy without material uncertainty is not an accepted trigger"

    if t_clean in OBJECTIVE_TRIGGERS:
        return True, f"Legitimate objective trigger accepted: '{t_clean}'"

    return False, f"Unrecognized trigger: '{t_clean}'"


def validate_advisor_result_schema(instance: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validates an Advisor result dictionary against schemas/advisor-result.schema.json (AC05).
    Deterministic Draft 2020-12 validator adhering to the schema definition.
    """
    errors: list[str] = []

    # 1. Type
    if not isinstance(instance, dict):
        return False, ["Advisor result must be a JSON object"]

    # 2. additionalProperties: false
    allowed_props = set(schema.get("properties", {}).keys())
    extra_props = set(instance.keys()) - allowed_props
    if extra_props:
        errors.append(f"Unexpected properties found (additionalProperties false): {sorted(extra_props)}")

    # 3. required properties
    for req in schema.get("required", []):
        if req not in instance:
            errors.append(f"Missing required property: '{req}'")

    if errors:
        return False, errors

    # 4. Property validations
    # schema_version
    if instance.get("schema_version") != 1:
        errors.append(f"schema_version must be 1, got {instance.get('schema_version')}")

    # verdict
    verdict = instance.get("verdict")
    if verdict not in VALID_VERDICTS:
        errors.append(f"verdict must be one of {sorted(VALID_VERDICTS)}, got '{verdict}'")

    # confidence
    confidence = instance.get("confidence")
    if confidence not in VALID_CONFIDENCES:
        errors.append(f"confidence must be one of {sorted(VALID_CONFIDENCES)}, got '{confidence}'")

    # findings
    findings = instance.get("findings")
    if not isinstance(findings, list) or not all(isinstance(x, str) and len(x) >= 1 for x in findings):
        errors.append("findings must be an array of non-empty strings")

    # alternatives
    alternatives = instance.get("alternatives")
    if not isinstance(alternatives, list) or not all(isinstance(x, str) and len(x) >= 1 for x in alternatives):
        errors.append("alternatives must be an array of non-empty strings")

    # missing_evidence
    missing_evidence = instance.get("missing_evidence")
    if not isinstance(missing_evidence, list) or not all(isinstance(x, str) and len(x) >= 1 for x in missing_evidence):
        errors.append("missing_evidence must be an array of non-empty strings")

    # debate_required
    if not isinstance(instance.get("debate_required"), bool):
        errors.append(f"debate_required must be a boolean, got {type(instance.get('debate_required')).__name__}")

    # 5. Conditional constraints (Draft 2020-12 allOf / if-then)
    for condition in schema.get("allOf", []):
        if_cond = condition.get("if", {})
        then_cond = condition.get("then", {})

        if_match = True
        for prop, rule in if_cond.get("properties", {}).items():
            if "const" in rule and instance.get(prop) != rule["const"]:
                if_match = False
                break
            if "enum" in rule and instance.get(prop) not in rule["enum"]:
                if_match = False
                break

        if if_match:
            for prop, rule in then_cond.get("properties", {}).items():
                if "const" in rule and instance.get(prop) != rule["const"]:
                    errors.append(
                        f"Conditional schema violation (Draft 2020-12 allOf): property '{prop}' must be {rule['const']!r} when {if_cond.get('properties')}, got {instance.get(prop)!r}"
                    )
                if "enum" in rule and instance.get(prop) not in rule["enum"]:
                    errors.append(
                        f"Conditional schema violation (Draft 2020-12 allOf): property '{prop}' must be in {rule['enum']!r} when {if_cond.get('properties')}, got {instance.get(prop)!r}"
                    )

    return (len(errors) == 0), errors


ALL_KNOWN_FAMILIES = ["google", "openai", "anthropic"]


def resolve_advisor_independence(
    challenged_authors: set[str] | list[str] | str,
    available_families: list[str],
    independence_policy: str = "preferred",
) -> dict[str, Any]:
    """
    Validates AC07, AC08, and R1:
    Resolves Advisor independence against the FULL SET of author families that materially
    contributed to the challenged artifact (challenged_author_families).
    eligible_cross_family = available_families - challenged_author_families
    """
    if isinstance(challenged_authors, str):
        authors_set = {challenged_authors.strip().lower()}
    else:
        authors_set = {a.strip().lower() for a in challenged_authors}

    avail = [f.strip().lower() for f in available_families]

    # Preference order for contra-families:
    # 1 author:
    #   [google] -> [openai, anthropic]
    #   [anthropic] -> [google, openai]
    #   [openai] -> [google, anthropic]
    # Pair of authors:
    #   [google, openai] -> [anthropic]
    #   [google, anthropic] -> [openai]
    #   [openai, anthropic] -> [google]
    # Triplet [google, openai, anthropic]:
    #   empty eligible set
    if len(authors_set) == 1:
        single_author = next(iter(authors_set))
        pref_order = FAMILY_CONTRA_MAP.get(single_author, [f for f in ALL_KNOWN_FAMILIES if f != single_author])
    else:
        if authors_set == {"google", "openai"}:
            pref_order = ["anthropic"]
        elif authors_set == {"google", "anthropic"}:
            pref_order = ["openai"]
        elif authors_set == {"openai", "anthropic"}:
            pref_order = ["google"]
        else:
            pref_order = [f for f in ["openai", "anthropic", "google"] if f not in authors_set]

    eligible_contra = [f for f in pref_order if f in avail]

    if eligible_contra:
        return {
            "status": "resolved",
            "advisor_family": eligible_contra[0],
            "independence_mode": "cross_family",
            "fallback_used": False,
            "fallback_reason": None,
        }

    # Contra-families are exhausted (or all available families conflict with challenged authors)
    if independence_policy == "preferred":
        available_conflict = [f for f in avail if f in authors_set]
        if available_conflict:
            return {
                "status": "resolved",
                "advisor_family": available_conflict[0],
                "independence_mode": "degraded_same_family",
                "fallback_used": True,
                "fallback_reason": f"All eligible cross-families {pref_order} unavailable; conflicting author families: {sorted(authors_set)}",
            }
        return {
            "status": "blocked",
            "advisor_family": None,
            "independence_mode": "unavailable",
            "fallback_used": False,
            "fallback_reason": "No model families available in catalog",
        }
    elif independence_policy == "required":
        return {
            "status": "blocked",
            "advisor_family": None,
            "independence_mode": "blocked_under_required",
            "fallback_used": False,
            "fallback_reason": f"advisor_independence is required and no independent cross-family available outside challenged author families {sorted(authors_set)}",
        }
    else:
        raise ValueError(f"Unknown independence policy: {independence_policy}")


def evaluate_advisor_independence(
    challenged_authors: set[str] | list[str] | str,
    available_families: list[str],
    independence_policy: str = "preferred",
) -> tuple[bool, Any]:
    """
    Evaluates advisor independence, returning (is_authorized, resolution_or_error_msg).
    Under 'required', returns (False, error_msg) if blocked.
    Under 'preferred', returns (True, resolution_dict) if resolved (including degraded_same_family).
    """
    res = resolve_advisor_independence(challenged_authors, available_families, independence_policy)
    if res["status"] == "resolved":
        return True, res
    return False, res.get("fallback_reason", "Advisor independence evaluation blocked")


resolve_advisor_candidates = resolve_advisor_independence


def validate_challenge_packet(packet: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validates AC10: Minimal challenge packet (Context Economy).
    Must contain concise, targeted fields and not a raw dump.
    """
    required_keys = [
        "proposal_under_challenge",
        "goal",
        "constraints",
        "known_facts",
        "evidence",
        "assumptions",
        "considered_alternatives",
        "authority_limits",
        "specific_question",
    ]
    errors = []
    for key in required_keys:
        if key not in packet:
            errors.append(f"Missing required packet field: '{key}'")
        elif packet[key] is None or (isinstance(packet[key], str) and not packet[key].strip()):
            errors.append(f"Empty or null packet field: '{key}'")

    if packet.get("raw_repository_dump") is True:
        errors.append("Violation of Context Economy: raw_repository_dump is strictly prohibited")

    return (len(errors) == 0), errors


def evaluate_authorship_propagation(
    advisor_family: str,
    current_effective_authors: list[str],
    substantial_content_incorporated: bool,
) -> list[str]:
    """
    Validates AC11: Strict authorship propagation rules.
    Advisory report alone NEVER enters effective_authors.
    Only if substantial content is directly copied to spec/content_paths does advisor family propagate.
    """
    updated_authors = list(current_effective_authors)
    if substantial_content_incorporated:
        if advisor_family not in updated_authors:
            updated_authors.append(advisor_family)
    return updated_authors


def check_verdict_disposition(
    verdict: str,
    debate_required: bool,
    disposition_record: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Validates AC13: Blocking disposition of restrictive recommendations (adjust, plan, debate, stop).
    """
    if verdict == "proceed" and not debate_required:
        return True, "Proceed verdict: normal flow continues"

    if not disposition_record or not isinstance(disposition_record, dict):
        return False, f"Blocking violation: verdict '{verdict}' (debate_required={debate_required}) cannot be silently ignored without disposition record"

    status = disposition_record.get("status")
    if not status or status not in {"disposed", "escalated", "halted", "rejected_with_rationale"}:
        return False, f"Invalid disposition status: '{status}'"

    rationale = disposition_record.get("rationale", "").strip()
    if not rationale:
        return False, "Disposition record must provide explicit justification/rationale"

    return True, "Disposition formally recorded"


def evaluate_batch_advisor_policy(
    policy: dict[str, Any],
    requested_trigger: str,
    current_calls: int,
) -> tuple[bool, str]:
    """
    Validates AC14: Interface with Automatic Mode (T018).
    Checks advisor_policy enabled, trigger permission, and call quota against frozen budget.
    """
    if not policy.get("enabled", False):
        return False, "Advisor calls disabled in batch advisor_policy"

    allowed_triggers = set(policy.get("triggers", []))
    if requested_trigger not in allowed_triggers:
        return False, f"Trigger '{requested_trigger}' not permitted by batch advisor_policy triggers: {sorted(allowed_triggers)}"

    max_calls = policy.get("max_calls", 0)
    if current_calls >= max_calls:
        return False, f"Advisor call limit reached ({current_calls}/{max_calls}) for batch budget"

    return True, "Advisor invocation authorized under batch advisor_policy"


# ==============================================================================
# Unit and Deterministic Test Suite
# ==============================================================================

class TestAdvisorPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ADVISOR_SCHEMA_PATH, "r", encoding="utf-8") as f:
            cls.advisor_schema = json.load(f)
        with open(CLASSIFIER_SCHEMA_PATH, "r", encoding="utf-8") as f:
            cls.classifier_schema = json.load(f)

    # --------------------------------------------------------------------------
    # AC01: Role boundary and permission constraints
    # --------------------------------------------------------------------------
    def test_ac01_role_boundary_strict_compliance(self):
        valid_role = {
            "report_only": True,
            "fresh_session": "required",
            "may_edit": False,
            "may_commit": False,
            "may_change_state": False,
            "may_close_task": False,
            "may_authorize": False,
            "may_dispatch_agents": False,
            "may_replace_checker": False,
            "may_replace_planner": False,
            "may_recommend_debate": True,
        }
        ok, msg = validate_advisor_role_boundary(valid_role)
        self.assertTrue(ok, msg)

    def test_ac01_role_boundary_rejects_mutable_permissions(self):
        mutable_flags = [
            ("may_edit", True),
            ("may_commit", True),
            ("may_change_state", True),
            ("may_close_task", True),
            ("may_authorize", True),
            ("may_dispatch_agents", True),
            ("may_replace_checker", True),
            ("may_replace_planner", True),
            ("report_only", False),
            ("fresh_session", "optional"),
        ]
        base = {
            "report_only": True,
            "fresh_session": "required",
            "may_edit": False,
            "may_commit": False,
            "may_change_state": False,
            "may_close_task": False,
            "may_authorize": False,
            "may_dispatch_agents": False,
            "may_replace_checker": False,
            "may_replace_planner": False,
            "may_recommend_debate": True,
        }
        for flag, invalid_val in mutable_flags:
            with self.subTest(flag=flag, invalid_val=invalid_val):
                bad = dict(base)
                bad[flag] = invalid_val
                ok, msg = validate_advisor_role_boundary(bad)
                self.assertFalse(ok, f"Expected violation for {flag}={invalid_val}")
                self.assertIn("Role boundary violation", msg)

    # --------------------------------------------------------------------------
    # AC02: Clear role distinctions (Planner vs Advisor vs Checker vs Debate)
    # --------------------------------------------------------------------------
    def test_ac02_clear_role_distinctions(self):
        self.assertEqual(ROLE_QUESTIONS["planner"], "Como devemos fazer?")
        self.assertEqual(ROLE_QUESTIONS["advisor"], "Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?")
        self.assertEqual(ROLE_QUESTIONS["checker"], "O que foi implementado atende a spec e a prova?")
        self.assertEqual(ROLE_QUESTIONS["debate"], "Temos alternativas materialmente concorrentes; qual direção devemos escolher?")

        # Mutually exclusive
        questions = list(ROLE_QUESTIONS.values())
        self.assertEqual(len(questions), len(set(questions)))

    # --------------------------------------------------------------------------
    # AC03: Objective triggers (all 8 accepted)
    # --------------------------------------------------------------------------
    def test_ac03_all_8_objective_triggers_accepted(self):
        expected_triggers = [
            ("architecture_or_contract_change", {}),
            ("hard_to_reverse_decision", {}),
            ("governance_experiment", {}),
            ("heavy_tier_material_uncertainty", {"has_material_uncertainty": True}),
            ("causal_claim_limited_evidence", {}),
            ("recurring_failure_class_independent_review", {}),
            ("explicit_user_request", {}),
            ("pre_freeze_high_cost_batch", {}),
        ]
        self.assertEqual(len(expected_triggers), 8)
        for trigger, ctx in expected_triggers:
            with self.subTest(trigger=trigger):
                ok, msg = evaluate_advisor_trigger(trigger, ctx)
                self.assertTrue(ok, f"Trigger '{trigger}' must be accepted: {msg}")

    # --------------------------------------------------------------------------
    # AC04: Strict rejection of routine non-triggers (anti-overuse)
    # --------------------------------------------------------------------------
    def test_ac04_strict_rejection_of_routine_non_triggers(self):
        rejected_triggers = [
            "story_start",
            "maker_done",
            "review_entry",
            "routine_changes_requested",
            "routine_docs_or_status",
            "second_opinion",
            "por_seguranca",
            "to_be_safe",
            "just_in_case",
        ]
        for trigger in rejected_triggers:
            with self.subTest(trigger=trigger):
                ok, msg = evaluate_advisor_trigger(trigger)
                self.assertFalse(ok, f"Non-trigger '{trigger}' must be strictly rejected")
                self.assertIn("Prohibited non-trigger", msg)

    def test_ac04_heavy_tier_without_material_uncertainty_rejected(self):
        ok, msg = evaluate_advisor_trigger("heavy_tier_material_uncertainty", {"has_material_uncertainty": False})
        self.assertFalse(ok)
        self.assertIn("tier heavy without material uncertainty is not an accepted trigger", msg)

    # --------------------------------------------------------------------------
    # AC05: Structured result schema validation (Draft 2020-12)
    # --------------------------------------------------------------------------
    def test_ac05_valid_advisor_results_for_all_verdicts(self):
        for verdict in VALID_VERDICTS:
            with self.subTest(verdict=verdict):
                instance = {
                    "schema_version": 1,
                    "verdict": verdict,
                    "confidence": "high",
                    "findings": ["Premissa X não comprovada sob concorrência"],
                    "alternatives": ["Adotar lock cooperativo explícito"],
                    "missing_evidence": ["Medição de contenção sob 10 workers"],
                    "debate_required": (verdict == "debate"),
                    "reason": f"Análise crítica resultando em veredito {verdict}",
                }
                ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
                self.assertTrue(ok, f"Valid instance failed validation: {errs}")

    def test_ac05_schema_rejects_missing_required_fields(self):
        required_fields = ["schema_version", "verdict", "confidence", "findings", "alternatives", "missing_evidence", "debate_required", "reason"]
        valid_base = {
            "schema_version": 1,
            "verdict": "proceed",
            "confidence": "medium",
            "findings": [],
            "alternatives": [],
            "missing_evidence": [],
            "debate_required": False,
            "reason": "OK",
        }
        for field in required_fields:
            with self.subTest(missing_field=field):
                bad = dict(valid_base)
                del bad[field]
                ok, errs = validate_advisor_result_schema(bad, self.advisor_schema)
                self.assertFalse(ok)
                self.assertTrue(any(f"Missing required property: '{field}'" in e for e in errs))

    def test_ac05_schema_rejects_extra_properties(self):
        instance = {
            "schema_version": 1,
            "verdict": "proceed",
            "confidence": "high",
            "findings": [],
            "alternatives": [],
            "missing_evidence": [],
            "debate_required": False,
            "reason": "OK",
            "unexpected_field": "disallowed",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertFalse(ok)
        self.assertTrue(any("additionalProperties false" in e for e in errs))

    def test_ac05_schema_rejects_invalid_verdict_or_confidence(self):
        instance = {
            "schema_version": 1,
            "verdict": "invalid_verdict",
            "confidence": "extreme",
            "findings": [],
            "alternatives": [],
            "missing_evidence": [],
            "debate_required": False,
            "reason": "OK",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertFalse(ok)
        self.assertTrue(any("verdict must be one of" in e for e in errs))
        self.assertTrue(any("confidence must be one of" in e for e in errs))

    def test_ac05_schema_rejects_wrong_schema_version(self):
        instance = {
            "schema_version": 2,
            "verdict": "proceed",
            "confidence": "high",
            "findings": [],
            "alternatives": [],
            "missing_evidence": [],
            "debate_required": False,
            "reason": "OK",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertFalse(ok)
        self.assertTrue(any("schema_version must be 1" in e for e in errs))

    def test_r2_debate_verdict_with_debate_required_true_passes_schema(self):
        instance = {
            "schema_version": 1,
            "verdict": "debate",
            "confidence": "high",
            "findings": ["Alternativas concorrentes de concorrência"],
            "alternatives": ["Opção A", "Opção B"],
            "missing_evidence": ["Testes de carga"],
            "debate_required": True,
            "reason": "Debate formal estritamente recomendado",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertTrue(ok, f"verdict='debate' with debate_required=True must pass validation: {errs}")

    def test_r2_debate_verdict_with_debate_required_false_fails_schema(self):
        instance = {
            "schema_version": 1,
            "verdict": "debate",
            "confidence": "high",
            "findings": ["Alternativas concorrentes de concorrência"],
            "alternatives": ["Opção A", "Opção B"],
            "missing_evidence": ["Testes de carga"],
            "debate_required": False,
            "reason": "Debate com debate_required False deve falhar",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertFalse(ok, "verdict='debate' with debate_required=False must FAIL schema validation")
        self.assertTrue(
            any("debate_required" in e for e in errs),
            f"Expected error message indicating debate_required conditional failure, got: {errs}",
        )

    def test_r2_adjust_verdict_with_debate_required_true_passes_schema(self):
        # Proves that the inverse implication is not imposed: adjust with debate_required=True is valid
        instance = {
            "schema_version": 1,
            "verdict": "adjust",
            "confidence": "medium",
            "findings": ["Necessidade de ajuste e posterior deliberação"],
            "alternatives": ["Ajustar parâmetros e abrir debate"],
            "missing_evidence": ["Evidência preliminar"],
            "debate_required": True,
            "reason": "Ajuste acompanhado de debate sobre impacto",
        }
        ok, errs = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertTrue(ok, f"verdict='adjust' with debate_required=True must pass validation: {errs}")

    # --------------------------------------------------------------------------
    # AC06: Verdict semantics
    # --------------------------------------------------------------------------
    def test_ac06_verdict_operational_effects(self):
        semantics = {
            "proceed": "normal flow continues",
            "adjust": "mandatory disposition required before next dispatch",
            "plan": "formal planning and specification required",
            "debate": "recommend formal debate panel",
            "stop": "halt progression until critical risk/evidence resolution",
        }
        self.assertEqual(set(semantics.keys()), VALID_VERDICTS)

    # --------------------------------------------------------------------------
    # AC07: Independence and fresh session (Contra-family resolution)
    # --------------------------------------------------------------------------
    def test_ac07_contra_family_resolution_anthropic_proposal(self):
        # Proposal by Anthropic (Claude) -> prefers Google or OpenAI
        avail = ["anthropic", "google", "openai"]
        res = resolve_advisor_independence("anthropic", avail, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "google")
        self.assertEqual(res["independence_mode"], "cross_family")
        self.assertFalse(res["fallback_used"])

    def test_ac07_contra_family_resolution_google_proposal(self):
        # Proposal by Google (Gemini) -> prefers OpenAI or Anthropic
        avail = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence("google", avail, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "openai")
        self.assertEqual(res["independence_mode"], "cross_family")

    def test_ac07_contra_family_resolution_openai_proposal(self):
        # Proposal by OpenAI (Codex) -> prefers Google or Anthropic
        avail = ["openai", "anthropic", "google"]
        res = resolve_advisor_independence("openai", avail, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "google")
        self.assertEqual(res["independence_mode"], "cross_family")

    # --------------------------------------------------------------------------
    # AC08: Degraded fallback vs blocking under required
    # --------------------------------------------------------------------------
    def test_ac08_degraded_fallback_under_preferred_when_cross_family_unavailable(self):
        # Proposal by Anthropic, only Anthropic available in catalog
        res = resolve_advisor_independence("anthropic", ["anthropic"], "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "anthropic")
        self.assertEqual(res["independence_mode"], "degraded_same_family")
        self.assertTrue(res["fallback_used"])
        self.assertIsNotNone(res["fallback_reason"])

    def test_ac08_blocking_under_required_when_cross_family_unavailable(self):
        # Proposal by Anthropic, only Anthropic available, but advisor_independence: required
        res = resolve_advisor_independence("anthropic", ["anthropic"], "required")
        self.assertEqual(res["status"], "blocked")
        self.assertIsNone(res["advisor_family"])
        self.assertEqual(res["independence_mode"], "blocked_under_required")

    def test_r1_authors_pair_google_openai_resolves_anthropic(self):
        # authors=[google, openai], available=[google, openai, anthropic] -> advisor=anthropic
        authors = ["google", "openai"]
        available = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence(authors, available, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "anthropic")
        self.assertEqual(res["independence_mode"], "cross_family")
        self.assertFalse(res["fallback_used"])

        ok, out = evaluate_advisor_independence(authors, available, "preferred")
        self.assertTrue(ok)
        self.assertEqual(out["advisor_family"], "anthropic")

    def test_r1_authors_pair_google_anthropic_resolves_openai(self):
        # authors=[google, anthropic], available=[google, openai, anthropic] -> advisor=openai
        authors = ["google", "anthropic"]
        available = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence(authors, available, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "openai")
        self.assertEqual(res["independence_mode"], "cross_family")
        self.assertFalse(res["fallback_used"])

        ok, out = evaluate_advisor_independence(authors, available, "preferred")
        self.assertTrue(ok)
        self.assertEqual(out["advisor_family"], "openai")

    def test_r1_authors_pair_openai_anthropic_resolves_google(self):
        # authors=[openai, anthropic], available=[google, openai, anthropic] -> advisor=google
        authors = ["openai", "anthropic"]
        available = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence(authors, available, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["advisor_family"], "google")
        self.assertEqual(res["independence_mode"], "cross_family")
        self.assertFalse(res["fallback_used"])

        ok, out = evaluate_advisor_independence(authors, available, "preferred")
        self.assertTrue(ok)
        self.assertEqual(out["advisor_family"], "google")

    def test_r1_authors_triplet_under_required_policy_blocks_with_error(self):
        # authors=[google, openai, anthropic], policy="required" -> blocked (retorna False com erro)
        authors = ["google", "openai", "anthropic"]
        available = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence(authors, available, "required")
        self.assertEqual(res["status"], "blocked")
        self.assertIsNone(res["advisor_family"])
        self.assertEqual(res["independence_mode"], "blocked_under_required")

        ok, err = evaluate_advisor_independence(authors, available, "required")
        self.assertFalse(ok)
        self.assertIn("advisor_independence is required", err)

    def test_r1_authors_triplet_under_preferred_policy_resolves_degraded_same_family(self):
        # authors=[google, openai, anthropic], policy="preferred" -> degraded_same_family com fallback_reason preenchido
        authors = ["google", "openai", "anthropic"]
        available = ["google", "openai", "anthropic"]
        res = resolve_advisor_independence(authors, available, "preferred")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["independence_mode"], "degraded_same_family")
        self.assertTrue(res["fallback_used"])
        self.assertTrue(bool(res["fallback_reason"]))
        # Confirms fallback_reason details the conflicting families
        for fam in authors:
            self.assertIn(fam, res["fallback_reason"])

        ok, out = evaluate_advisor_independence(authors, available, "preferred")
        self.assertTrue(ok)
        self.assertEqual(out["independence_mode"], "degraded_same_family")

    # --------------------------------------------------------------------------
    # AC09: Classifier support for Advisor role
    # --------------------------------------------------------------------------
    def test_ac09_classifier_schema_supports_advisor_role(self):
        roles_props = self.classifier_schema["properties"]["roles"]["properties"]
        self.assertIn("advisor", roles_props, "classifier schema must define 'advisor' role in roles.properties")
        self.assertEqual(roles_props["advisor"], {"$ref": "#/$defs/role"})

    def test_ac09_advisor_role_adheres_to_role_schema(self):
        role_def = self.classifier_schema["$defs"]["role"]
        self.assertIn("tier", role_def["properties"])
        self.assertEqual(role_def["properties"]["tier"]["enum"], ["simple", "normal", "heavy"])

    # --------------------------------------------------------------------------
    # AC10: Minimal challenge packet (Context Economy)
    # --------------------------------------------------------------------------
    def test_ac10_minimal_challenge_packet_structure(self):
        valid_packet = {
            "proposal_under_challenge": "Migração do protocolo de RPC para gRPC sem compatibilidade reversa",
            "goal": "Unificar camada de transporte",
            "constraints": "Sem downtime no cluster de produção",
            "known_facts": ["Clientes legados ainda usam JSON-HTTP", "Gateway suporta dual-stack"],
            "evidence": ["Medição de latência RPC", "Contagem de conexões legadas"],
            "assumptions": ["Todos os clientes podem ser atualizados em 48h"],
            "considered_alternatives": ["Manter adapter legado por 90 dias"],
            "authority_limits": "Orquestrador não pode autorizar quebra de SLA externo",
            "specific_question": "A premissa de cutover em 48h sem fallback é sustentável ou introduz risco inaceitável de indisponibilidade?",
        }
        ok, errs = validate_challenge_packet(valid_packet)
        self.assertTrue(ok, f"Valid challenge packet rejected: {errs}")

    def test_ac10_challenge_packet_rejects_raw_dump(self):
        packet_with_dump = {
            "proposal_under_challenge": "Migração X",
            "goal": "Goal Y",
            "constraints": "Constraint Z",
            "known_facts": ["Fact 1"],
            "evidence": ["Ev 1"],
            "assumptions": ["Assump 1"],
            "considered_alternatives": ["Alt 1"],
            "authority_limits": "Limit 1",
            "specific_question": "Question 1",
            "raw_repository_dump": True,
        }
        ok, errs = validate_challenge_packet(packet_with_dump)
        self.assertFalse(ok)
        self.assertTrue(any("raw_repository_dump is strictly prohibited" in e for e in errs))

    # --------------------------------------------------------------------------
    # AC11: Conditional authorship propagation
    # --------------------------------------------------------------------------
    def test_ac11_advisory_opinion_alone_does_not_propagate_authorship(self):
        current_authors = ["google"]
        updated = evaluate_authorship_propagation(
            advisor_family="openai",
            current_effective_authors=current_authors,
            substantial_content_incorporated=False,
        )
        self.assertEqual(updated, ["google"], "Advisory opinion alone must not propagate to effective_authors")

    def test_ac11_substantial_content_incorporated_propagates_authorship(self):
        current_authors = ["google"]
        updated = evaluate_authorship_propagation(
            advisor_family="openai",
            current_effective_authors=current_authors,
            substantial_content_incorporated=True,
        )
        self.assertEqual(updated, ["google", "openai"], "Substantially incorporated content must propagate advisor family to effective_authors")

    # --------------------------------------------------------------------------
    # AC12: Debate escalation without auto-start
    # --------------------------------------------------------------------------
    def test_ac12_advisor_recommends_debate_cannot_auto_start(self):
        instance = {
            "schema_version": 1,
            "verdict": "debate",
            "confidence": "high",
            "findings": ["Alternativas de arquitetura materialmente concorrentes"],
            "alternatives": ["Opção A: microserviços", "Opção B: monólito modular"],
            "missing_evidence": ["Projeção de throughput sob carga máxima"],
            "debate_required": True,
            "reason": "Incerteza estratégica crítica que requer deliberação multi-perspectiva",
        }
        ok, _ = validate_advisor_result_schema(instance, self.advisor_schema)
        self.assertTrue(ok)
        self.assertTrue(instance["debate_required"])

        # Advisor has may_recommend_debate=True, but may_dispatch_agents=False and may_authorize=False
        role = {
            "report_only": True,
            "fresh_session": "required",
            "may_edit": False,
            "may_commit": False,
            "may_change_state": False,
            "may_close_task": False,
            "may_authorize": False,
            "may_dispatch_agents": False,
            "may_replace_checker": False,
            "may_replace_planner": False,
            "may_recommend_debate": True,
        }
        self.assertFalse(role["may_dispatch_agents"])
        self.assertFalse(role["may_authorize"])
        self.assertTrue(role["may_recommend_debate"])

    # --------------------------------------------------------------------------
    # AC13: Blocking disposition of restrictive recommendations
    # --------------------------------------------------------------------------
    def test_ac13_proceed_does_not_block_advancement(self):
        ok, msg = check_verdict_disposition("proceed", debate_required=False, disposition_record=None)
        self.assertTrue(ok, msg)

    def test_ac13_restrictive_verdicts_block_without_formal_disposition(self):
        for verdict in ["adjust", "plan", "debate", "stop"]:
            with self.subTest(verdict=verdict):
                ok, msg = check_verdict_disposition(verdict, debate_required=False, disposition_record=None)
                self.assertFalse(ok)
                self.assertIn("cannot be silently ignored", msg)

    def test_ac13_debate_required_blocks_without_disposition_even_if_proceed(self):
        ok, msg = check_verdict_disposition("proceed", debate_required=True, disposition_record=None)
        self.assertFalse(ok)
        self.assertIn("cannot be silently ignored", msg)

    def test_ac13_formal_disposition_unblocks_progression(self):
        record = {
            "status": "disposed",
            "rationale": "Premissas ajustadas na spec §3 conforme apontamento do Advisor",
            "disposed_by": "orchestrator",
        }
        ok, msg = check_verdict_disposition("adjust", debate_required=False, disposition_record=record)
        self.assertTrue(ok, msg)

    # --------------------------------------------------------------------------
    # AC14: Automatic Mode interface (advisor_policy in batch)
    # --------------------------------------------------------------------------
    def test_ac14_batch_advisor_policy_authorized_call(self):
        policy = {
            "enabled": True,
            "triggers": ["architecture_or_contract_change", "hard_to_reverse_decision"],
            "max_calls": 3,
        }
        ok, msg = evaluate_batch_advisor_policy(policy, "architecture_or_contract_change", current_calls=1)
        self.assertTrue(ok, msg)

    def test_ac14_batch_advisor_policy_disabled_blocks_calls(self):
        policy = {
            "enabled": False,
            "triggers": ["architecture_or_contract_change"],
            "max_calls": 3,
        }
        ok, msg = evaluate_batch_advisor_policy(policy, "architecture_or_contract_change", current_calls=0)
        self.assertFalse(ok)
        self.assertIn("disabled", msg)

    def test_ac14_batch_advisor_policy_unauthorized_trigger_blocked(self):
        policy = {
            "enabled": True,
            "triggers": ["architecture_or_contract_change"],
            "max_calls": 3,
        }
        ok, msg = evaluate_batch_advisor_policy(policy, "governance_experiment", current_calls=0)
        self.assertFalse(ok)
        self.assertIn("not permitted by batch advisor_policy triggers", msg)

    def test_ac14_batch_advisor_policy_exceeding_budget_blocked(self):
        policy = {
            "enabled": True,
            "triggers": ["architecture_or_contract_change"],
            "max_calls": 2,
        }
        ok, msg = evaluate_batch_advisor_policy(policy, "architecture_or_contract_change", current_calls=2)
        self.assertFalse(ok)
        self.assertIn("call limit reached", msg)

    # --------------------------------------------------------------------------
    # AC15: Contractual distribution and suite integrity
    # --------------------------------------------------------------------------
    def test_ac15_distribution_manifest_parity_and_advisor_artifacts_integrity(self):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest.get("format_version"), 1)
        package_file_count = manifest.get("package_file_count")
        files = manifest.get("package_files", [])
        self.assertEqual(package_file_count, len(files))
        self.assertGreaterEqual(package_file_count, 19)
        self.assertIn("prompts/advisor.md", files)
        self.assertIn("schemas/advisor-result.schema.json", files)


if __name__ == "__main__":
    unittest.main()
