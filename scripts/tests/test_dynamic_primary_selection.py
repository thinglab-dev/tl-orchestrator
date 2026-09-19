#!/usr/bin/env python3
"""Contractual and behavior tests for T019: Dynamic Primary Harness Selection.

Covers invariants R1 to R22 and acceptance criteria AC01 to AC10.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import Any

from scripts.validate_classification import (
    DEFAULT_EFFICIENCY_ORDER,
    match_project_priority,
    resolve_minimum_sufficient,
    validate_classification_data,
    validate_classification_file,
)

ROOT = Path(__file__).resolve().parents[2]


class DynamicPrimarySelectionContractTest(unittest.TestCase):
    """Test v3 schema, state matrix, and semantic invariants R1-R22."""

    def setUp(self) -> None:
        self.base_v3 = {
            "schema_version": 3,
            "story_id": "T019",
            "phase": "implementation",
            "context_revision": "ctx-rev-test",
            "catalog_revision": "cat-rev-test",
            "confidence": "high",
            "facts": ["T019 test scenario"],
            "uncertainties": [],
            "reclassify_when": ["Scope changes"],
            "roles": {},
        }

    def _make_eval(
        self,
        harness: str,
        model: str | None,
        effort: str | None,
        catalog_eligible: bool = True,
        technical_adequacy: str = "sufficient",
        dispatchable: bool = True,
        cost_basis: str | None = "token_price_only",
        evidence_ids: list[str] | None = None,
        uncertainty: str | None = None,
        reason: str = "Evaluation reason",
    ) -> dict[str, Any]:
        return {
            "harness": harness,
            "model": model,
            "effort": effort,
            "catalog_eligible": catalog_eligible,
            "technical_adequacy": technical_adequacy,
            "dispatchable": dispatchable,
            "cost_basis": cost_basis,
            "evidence_ids": evidence_ids or (["ev-1"] if cost_basis != "unknown" else []),
            "uncertainty": uncertainty,
            "reason": reason,
        }

    def _make_cand(
        self,
        harness: str,
        model: str,
        effort: str,
        dispatch_role: str,
        cost_basis: str = "token_price_only",
        evidence_ids: list[str] | None = None,
        reason: str = "Candidate reason",
    ) -> dict[str, Any]:
        return {
            "harness": harness,
            "model": model,
            "effort": effort,
            "dispatch_role": dispatch_role,
            "evidence_ids": evidence_ids or (["ev-1"] if cost_basis != "unknown" else []),
            "cost_basis": cost_basis,
            "reason": reason,
        }

    def test_r01_and_ac01_codex_is_global_primary_when_sufficient(self) -> None:
        """AC01: Codex High is the global Maker primary when it is sufficient and dispatchable."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Codex Terra elected as the global Maker preference with sufficient technical adequacy",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                    self._make_eval("agy", "gemini-3.8-flash-high", "high", True, "insufficient", False),
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                    self._make_cand("claude", "sonnet", "high", "fallback"),
                ],
            }
        }
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Validation failed: {errors}")
        self.assertEqual(data["roles"]["maker"]["candidates"][0]["harness"], "codex")
        self.assertEqual(data["roles"]["maker"]["candidates"][0]["dispatch_role"], "primary")

    def test_r01_and_ac01_agy_as_primary_and_claude_as_primary(self) -> None:
        """AC01: Agy and Claude can each be elected as recommended_primary."""
        # Agy as primary
        data_agy = dict(self.base_v3)
        data_agy["roles"] = {
            "planner": {
                "tier": "normal",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Agy elected as primary Planner",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("agy", "gemini-3.8-flash-medium", "medium", True, "sufficient", True),
                    self._make_eval("claude", "sonnet", "medium", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("agy", "gemini-3.8-flash-medium", "medium", "primary"),
                    self._make_cand("claude", "sonnet", "medium", "fallback"),
                ],
            }
        }
        valid_agy, errors_agy = validate_classification_data(data_agy)
        self.assertTrue(valid_agy, f"Validation failed: {errors_agy}")
        self.assertEqual(data_agy["roles"]["planner"]["candidates"][0]["harness"], "agy")

        # Claude as primary
        data_claude = dict(self.base_v3)
        data_claude["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "escalation",
                "escalation_reason": "efficient_candidate_insufficient",
                "reason": "Claude Sonnet High elected as primary Maker after more efficient options insufficient",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("agy", "gemini-3.8-flash-high", "high", True, "insufficient", False),
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "insufficient", False),
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("claude", "sonnet", "high", "primary"),
                ],
            }
        }
        valid_claude, errors_claude = validate_classification_data(data_claude)
        self.assertTrue(valid_claude, f"Validation failed: {errors_claude}")
        self.assertEqual(data_claude["roles"]["maker"]["candidates"][0]["harness"], "claude")

    def test_r01_unknown_handling_does_not_lose_economically(self) -> None:
        """R1: cost_basis: unknown never loses economic comparison."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "normal",
                "selection_status": "underdetermined",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Unknown cost cannot be declared more expensive than known cost; resolved by project_priority",
                "tie_break_applied": "project_priority: codex/gpt-5.6-terra/*",
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "medium", True, "sufficient", True, cost_basis="unknown"),
                    self._make_eval("claude", "sonnet", "medium", True, "sufficient", True, cost_basis="token_price_only"),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "medium", "primary", cost_basis="unknown"),
                    self._make_cand("claude", "sonnet", "medium", "fallback", cost_basis="token_price_only"),
                ],
            }
        }
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Validation failed: {errors}")

    def test_r07_and_r10_insufficient_or_uncertain_excluded_from_candidates(self) -> None:
        """AC03, R7, R10: Pairs with technical_adequacy insufficient/uncertain are excluded from candidates[]."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Flash medium excluded for technical inadequacy; Terra High elected",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("agy", "gemini-3.8-flash-medium", "medium", True, "insufficient", False),
                    self._make_eval("claude", "haiku", "low", True, "uncertain", False),
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                ],
            }
        }
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Validation failed: {errors}")

        # Counterfactual test: promoting an insufficient pair to candidates[] must be rejected
        data_bad = dict(self.base_v3)
        data_bad["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Attempting invalid promotion",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("agy", "gemini-3.8-flash-medium", "medium", True, "insufficient", False),
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("agy", "gemini-3.8-flash-medium", "medium", "primary"),
                    self._make_cand("codex", "gpt-5.6-terra", "high", "fallback"),
                ],
            }
        }
        valid_bad, errors_bad = validate_classification_data(data_bad)
        self.assertFalse(valid_bad)
        self.assertTrue(any("insufficient/uncertain" in err for err in errors_bad))

    def test_r08_and_r11_awaiting_operator_under_ask_policy(self) -> None:
        """AC04, R8, R11: Under ask policy or unresolved tie, selection_status: awaiting_operator."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "awaiting_operator",
                "reason": "Tie under ask policy requires operator authorization",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "unassigned"),
                    self._make_cand("claude", "sonnet", "high", "unassigned"),
                ],
            }
        }
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Validation failed: {errors}")

        # Counterfactual test: awaiting_operator cannot designate a primary
        data_bad = dict(self.base_v3)
        data_bad["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "awaiting_operator",
                "reason": "Invalid primary under awaiting_operator",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                    self._make_cand("claude", "sonnet", "high", "unassigned"),
                ],
            }
        }
        valid_bad, errors_bad = validate_classification_data(data_bad)
        self.assertFalse(valid_bad)
        self.assertTrue(any("unassigned" in err for err in errors_bad))

    def test_r13_and_r20_project_priority_matcher_mechanics(self) -> None:
        """AC05, R13, R20: project_priority matching: 0 matches skip, 1 match resolves, >1 continue."""

        candidates = [
            ("codex", "gpt-5.6-terra", "high"),
            ("claude", "sonnet", "high"),
            ("agy", "gemini-3.8-flash-high", "high"),
        ]

        # Case 1: 0 matches skips, 1 match resolves
        selectors_1 = ["codex/nonexistent/*", "claude/sonnet/high"]
        winner_1, tie_break_1, status_1 = match_project_priority(candidates, selectors_1)
        self.assertEqual(status_1, "underdetermined")
        self.assertEqual(winner_1, ("claude", "sonnet", "high"))
        self.assertEqual(tie_break_1, "project_priority: claude/sonnet/high")

        # Case 2: >1 matches continues to next selector
        selectors_2 = ["*/*/*", "agy/*/*"]
        winner_2, tie_break_2, status_2 = match_project_priority(candidates, selectors_2)
        self.assertEqual(status_2, "underdetermined")
        self.assertEqual(winner_2, ("agy", "gemini-3.8-flash-high", "high"))

        # Case 3: Exhaustion without unique resolution -> awaiting_operator
        selectors_3 = ["nonexistent/*/*"]
        winner_3, tie_break_3, status_3 = match_project_priority(candidates, selectors_3)
        self.assertEqual(status_3, "awaiting_operator")
        self.assertIsNone(winner_3)

    def test_r18_infeasible_state_matrix(self) -> None:
        """R18: When no candidate reaches sufficient technical adequacy, status is infeasible."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "infeasible",
                "reason": "All available models cataloged fail technical adequacy for safety-critical task",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("agy", "gemini-3.8-flash-medium", "medium", True, "insufficient", False),
                    self._make_eval("claude", "haiku", "low", True, "insufficient", False),
                ],
                "candidates": [],
            }
        }
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Validation failed: {errors}")

        # Counterfactual: infeasible with candidates must fail
        data_bad = dict(data)
        data_bad["roles"]["maker"]["candidates"] = [
            self._make_cand("agy", "gemini-3.8-flash-medium", "medium", "primary")
        ]
        valid_bad, errors_bad = validate_classification_data(data_bad)
        self.assertFalse(valid_bad)
        self.assertTrue(any("infeasible" in err for err in errors_bad))

    def test_r09_dual_pipeline_and_opt_in_compatibility(self) -> None:
        """AC10 & R9: Dual validation for v2 and v3 in scripts/validate_classification.py."""
        # Valid v2 fixture
        v2_data = {
            "schema_version": 2,
            "story_id": "T018",
            "phase": "implementation",
            "context_revision": "ctx-v2",
            "catalog_revision": "cat-v2",
            "confidence": "high",
            "facts": ["Fact 1"],
            "uncertainties": [],
            "reclassify_when": ["Scope changes"],
            "roles": {
                "maker": {
                    "tier": "normal",
                    "reason": "Legacy v2 implementation",
                    "candidates": [
                        {
                            "harness": "agy",
                            "model": "gemini-3.8-flash-high",
                            "effort": "high",
                            "evidence_ids": ["price-flash-high"],
                            "cost_basis": "token_price_only",
                            "reason": "Legacy ordinal primary",
                        }
                    ],
                }
            },
        }
        valid_v2, errors_v2 = validate_classification_data(v2_data, expected_version=2)
        self.assertTrue(valid_v2, f"v2 validation failed: {errors_v2}")

        # v2 with expected_version=3 fails
        valid_mismatch, errors_mismatch = validate_classification_data(v2_data, expected_version=3)
        self.assertFalse(valid_mismatch)
        self.assertTrue(any("expected schema_version 3" in err for err in errors_mismatch))

    def test_r03_quota_pressure_does_not_alter_recommended_primary(self) -> None:
        """R3: Quota pressure acts in runtime at dispatch time, not in durable recommended_primary."""
        # 1. Contractual verification: prompts/classifier.md
        classifier_prompt = (ROOT / "prompts" / "classifier.md").read_text(encoding="utf-8")
        self.assertIn("Pressão de quota (`quota_pressure`) e disponibilidade factual observada NÃO influenciam o ranking semântico", classifier_prompt)
        self.assertIn("Ambos pertencem exclusivamente ao Runtime na determinação do `effective_primary`", classifier_prompt)

        # 2. Contractual verification: prompts/orchestrator.md
        orchestrator_prompt = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("(`quota_pressure`) é restrição operacional no momento do despacho e **não altera** o ranking semântico", orchestrator_prompt)

        # 3. Structural enforcement: quota_pressure is rejected by schema/validator if passed in classification
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "reason": "Valid conclusive selection",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                ],
            }
        }
        # Reject quota_pressure inside candidate
        data["roles"]["maker"]["candidates"][0]["quota_pressure"] = True
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid)
        self.assertTrue(any("unexpected additional property 'quota_pressure'" in e for e in errors))

        # Reject quota_pressure inside evaluation
        del data["roles"]["maker"]["candidates"][0]["quota_pressure"]
        data["roles"]["maker"]["evaluations"][0]["quota_pressure"] = True
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid)
        self.assertTrue(any("unexpected additional property 'quota_pressure'" in e for e in errors))

    def test_r05_and_ac06_ambiguous_dispatch_blocks_fallback_and_emits_stop(self) -> None:
        """AC06 & R5: DISPATCH_OUTCOME_AMBIGUOUS strictly blocks automatic fallback and emits STOP."""
        # 1. Contractual verification: docs/WORK_MODEL.md
        work_model = (ROOT / "docs" / "WORK_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("`DISPATCH_OUTCOME_AMBIGUOUS`", work_model)
        self.assertIn("**O fallback automático é terminantemente PROIBIDO.**", work_model)
        self.assertIn("STOP imediato (`dispatch_outcome_ambiguous`)", work_model)
        self.assertIn("unrecoverable_harness_failure_or_ambiguous_dispatch", work_model)

        # 2. Contractual verification: prompts/orchestrator.md
        orch_prompt = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("`DISPATCH_OUTCOME_AMBIGUOUS`: timeout, crash ou falha deixando árvore de trabalho dirty", orch_prompt)
        self.assertIn("**O fallback automático é terminantemente PROIBIDO.**", orch_prompt)
        self.assertIn("O Orquestrador emite\n     STOP imediato, preserva o workspace para reconciliação humana", orch_prompt)

        # 3. Contractual verification: CHANGELOG.md
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("bloqueio absoluto de fallback diante de `DISPATCH_OUTCOME_AMBIGUOUS`", changelog)

    def test_r14_and_ac07_proven_no_effect_is_rigorous(self) -> None:
        """AC07 & R14: DISPATCH_FAILED_PROVEN_NO_EFFECT requires clean tree, terminal tree and effects: none."""
        # 1. Contractual verification: docs/WORK_MODEL.md
        work_model = (ROOT / "docs" / "WORK_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("`DISPATCH_FAILED_PROVEN_NO_EFFECT`", work_model)
        self.assertIn("process-tree terminal", work_model)
        self.assertIn("git status --porcelain", work_model)
        self.assertIn("content_paths", work_model)
        self.assertIn("Ausência comprovada de efeitos externos", work_model)

        # 2. Contractual verification: prompts/orchestrator.md
        orch_prompt = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("`DISPATCH_FAILED_PROVEN_NO_EFFECT`: falha operacional sem efeitos colaterais", orch_prompt)
        self.assertIn("processo terminado", orch_prompt)
        self.assertIn("git status", orch_prompt)
        self.assertIn("content_paths", orch_prompt)
        self.assertIn("zero efeitos de rede", orch_prompt)

    def test_r21_local_vs_remote_preflight_budget_accounting(self) -> None:
        """R21: Local preflight failure releases reservation; remote preflight consumes slot."""
        # 1. Contractual verification: docs/WORK_MODEL.md
        work_model = (ROOT / "docs" / "WORK_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("Preflight local", work_model)
        self.assertIn("`PRE_DISPATCH_UNAVAILABLE`", work_model)
        self.assertIn("reservation released", work_model)
        self.assertIn("tentativa formal", work_model)

        # 2. Contractual verification: prompts/orchestrator.md
        orch_prompt = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("Preflight local vs remoto (R21):", orch_prompt)
        self.assertIn("`PRE_DISPATCH_UNAVAILABLE`", orch_prompt)
        self.assertIn("liberação de reserva", orch_prompt)
        self.assertIn("tentativa formal", orch_prompt)

    def test_r22_and_ac08_fallback_preserves_required_call_reserve(self) -> None:
        """AC08 & R22: Fallback permitted if and only if remaining_budget >= fallback_cost + required_call_reserve."""
        # 1. Contractual verification: docs/WORK_MODEL.md
        work_model = (ROOT / "docs" / "WORK_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("required_call_reserve", work_model)
        self.assertIn("insufficient_budget_for_unit_verification", work_model)
        self.assertIn("Preservação da reserva mandatória de orçamento", work_model)

        # 2. Contractual verification: prompts/orchestrator.md
        orch_prompt = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("preservação integral da reserva orçamentária", orch_prompt)
        self.assertIn("required_call_reserve(current_checkpoint)", orch_prompt)
        self.assertIn("R22", orch_prompt)

        # 3. Contractual verification: CHANGELOG.md
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("exigência de reserva dinâmica `required_call_reserve` antes de acionar fallback", changelog)

    def test_r06_patch_counterproof_candidates_cannot_have_uncertainty_or_extra_properties(self) -> None:
        """Finding R6: candidates[] cannot declare uncertainty or extra properties."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                ],
            }
        }
        # Baseline is valid
        valid, errors = validate_classification_data(data)
        self.assertTrue(valid, f"Expected valid baseline, got: {errors}")

        # Inject uncertainty into candidates[0]
        data["roles"]["maker"]["candidates"][0]["uncertainty"] = "low"
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid, "Expected candidates[0] with uncertainty to be rejected")
        self.assertTrue(any("unexpected additional property 'uncertainty'" in e for e in errors))

        # Inject arbitrary extra property
        del data["roles"]["maker"]["candidates"][0]["uncertainty"]
        data["roles"]["maker"]["candidates"][0]["arbitrary_field"] = "bad"
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid, "Expected candidates[0] with arbitrary field to be rejected")
        self.assertTrue(any("unexpected additional property 'arbitrary_field'" in e for e in errors))

    def test_r06_patch_counterproof_evaluations_cannot_have_extra_properties(self) -> None:
        """Finding R6: evaluations[] cannot declare unauthorized properties."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                ],
            }
        }
        data["roles"]["maker"]["evaluations"][0]["unknown_eval_key"] = "forbidden"
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid, "Expected evaluations[0] with unknown key to be rejected")
        self.assertTrue(any("unexpected additional property 'unknown_eval_key'" in e for e in errors))

    def test_r06_patch_counterproof_root_and_role_cannot_have_extra_properties(self) -> None:
        """Finding R6: root and roles cannot declare unauthorized properties."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": None,
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                ],
            }
        }
        # Inject extra at role level
        data["roles"]["maker"]["extra_role_prop"] = True
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid, "Expected role with extra property to be rejected")
        self.assertTrue(any("unexpected additional property 'extra_role_prop'" in e for e in errors))

        # Inject extra at root level
        del data["roles"]["maker"]["extra_role_prop"]
        data["extra_root_prop"] = 123
        valid, errors = validate_classification_data(data)
        self.assertFalse(valid, "Expected root with extra property to be rejected")
        self.assertTrue(any("unexpected additional property 'extra_root_prop'" in e for e in errors))

    def test_r06_patch_classifier_prompt_format_fixture_valid(self) -> None:
        """Finding R6: Fixture formatted strictly per prompts/classifier.md must be fully valid."""
        fixture = {
            "schema_version": 3,
            "story_id": "T019",
            "phase": "implementation",
            "context_revision": "tl-orchestrator@f6206f2+T019-spec-124cdbab8122d6bc",
            "catalog_revision": "PROJECT.md-perfil-de-despacho-2026-09-07",
            "confidence": "high",
            "facts": [
                "Implementation phase for story T019",
                "13 content paths within scope",
            ],
            "uncertainties": [],
            "reclassify_when": [
                "Scope changes beyond R1-R22",
            ],
            "roles": {
                "maker": {
                    "tier": "heavy",
                    "selection_status": "conclusive",
                    "selection_basis": "minimum_sufficient",
                    "escalation_reason": None,
                    "reason": "Codex elected as the global Maker primary with high effort",
                    "tie_break_applied": None,
                    "evaluations": [
                        {
                            "harness": "codex",
                            "model": "gpt-5.6-terra",
                            "effort": "high",
                            "catalog_eligible": True,
                            "technical_adequacy": "sufficient",
                            "dispatchable": True,
                            "cost_basis": "token_price_only",
                            "evidence_ids": ["price-terra", "gpt56-coding"],
                            "uncertainty": None,
                            "reason": "Adequate for heavy tier and preferred for Maker",
                        },
                        {
                            "harness": "agy",
                            "model": "gemini-3.8-flash-high",
                            "effort": "high",
                            "catalog_eligible": True,
                            "technical_adequacy": "sufficient",
                            "dispatchable": True,
                            "cost_basis": "token_price_only",
                            "evidence_ids": ["price-flash", "transport-flash"],
                            "uncertainty": None,
                            "reason": "Adequate Maker fallback",
                        },
                    ],
                    "candidates": [
                        {
                            "harness": "codex",
                            "model": "gpt-5.6-terra",
                            "effort": "high",
                            "dispatch_role": "primary",
                            "evidence_ids": ["price-terra", "gpt56-coding"],
                            "cost_basis": "token_price_only",
                            "reason": "Primary candidate",
                        },
                        {
                            "harness": "agy",
                            "model": "gemini-3.8-flash-high",
                            "effort": "high",
                            "dispatch_role": "fallback",
                            "evidence_ids": ["price-flash", "transport-flash"],
                            "cost_basis": "token_price_only",
                            "reason": "Fallback candidate",
                        },
                    ],
                }
            },
        }
        valid, errors = validate_classification_data(fixture, expected_story="T019", expected_phase="implementation", expected_version=3)
        self.assertTrue(valid, f"Expected classifier prompt fixture to be valid, got errors: {errors}")

    def test_r07_and_r12_schema_and_validator_state_matrix_fully_closed(self) -> None:
        """Findings R7 & R12: State matrix fully closed and falsifiable in Draft 2020-12 schema & validator."""
        # 1. Structural inspection of Draft 2020-12 schema
        schema_path = ROOT / "schemas" / "classification-result-v3.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        role_selection = schema["$defs"]["role_v3"]
        all_of = role_selection.get("allOf", [])
        self.assertGreaterEqual(len(all_of), 4, "Expected 4 conditional branches in schema allOf")

        # Branch 0: conclusive
        conclusive_branch = all_of[0]
        self.assertEqual(conclusive_branch["if"]["properties"]["selection_status"]["const"], "conclusive")
        self.assertEqual(conclusive_branch["then"]["properties"]["tie_break_applied"]["type"], "null")
        self.assertEqual(conclusive_branch["then"]["properties"]["candidates"]["minItems"], 1)
        self.assertEqual(
            conclusive_branch["then"]["properties"]["candidates"]["prefixItems"][0]["properties"]["dispatch_role"]["const"],
            "primary",
        )
        self.assertEqual(
            conclusive_branch["then"]["properties"]["candidates"]["items"]["properties"]["dispatch_role"]["const"],
            "fallback",
        )

        # Branch 1: underdetermined
        underdetermined_branch = all_of[1]
        self.assertEqual(underdetermined_branch["if"]["properties"]["selection_status"]["const"], "underdetermined")
        self.assertEqual(underdetermined_branch["then"]["properties"]["tie_break_applied"]["type"], "string")
        self.assertEqual(underdetermined_branch["then"]["properties"]["tie_break_applied"]["minLength"], 1)
        self.assertEqual(underdetermined_branch["then"]["properties"]["candidates"]["minItems"], 1)
        self.assertEqual(
            underdetermined_branch["then"]["properties"]["candidates"]["prefixItems"][0]["properties"]["dispatch_role"]["const"],
            "primary",
        )
        self.assertEqual(
            underdetermined_branch["then"]["properties"]["candidates"]["items"]["properties"]["dispatch_role"]["const"],
            "fallback",
        )

        # Branch 2: awaiting_operator
        awaiting_branch = all_of[2]
        self.assertEqual(awaiting_branch["if"]["properties"]["selection_status"]["const"], "awaiting_operator")
        self.assertEqual(awaiting_branch["then"]["properties"]["tie_break_applied"]["type"], "null")
        self.assertEqual(awaiting_branch["then"]["properties"]["candidates"]["minItems"], 2)
        self.assertEqual(
            awaiting_branch["then"]["properties"]["candidates"]["items"]["properties"]["dispatch_role"]["const"],
            "unassigned",
        )

        # Branch 3: infeasible
        infeasible_branch = all_of[3]
        self.assertEqual(infeasible_branch["if"]["properties"]["selection_status"]["const"], "infeasible")
        self.assertEqual(infeasible_branch["then"]["properties"]["tie_break_applied"]["type"], "null")
        self.assertEqual(infeasible_branch["then"]["properties"]["candidates"]["maxItems"], 0)

        # 2. Counterproofs via canonical validator:
        # Helper to construct baseline role payload
        def make_payload(status: str, tie_break: str | None, evals: list, cands: list) -> dict:
            d = dict(self.base_v3)
            role_obj: dict[str, Any] = {
                "tier": "heavy",
                "selection_status": status,
                "reason": f"Testing {status}",
                "tie_break_applied": tie_break,
                "evaluations": evals,
                "candidates": cands,
            }
            if status in ("conclusive", "underdetermined"):
                role_obj["selection_basis"] = "minimum_sufficient"
                role_obj["escalation_reason"] = None
            d["roles"] = {"maker": role_obj}
            return d

        eval_codex = self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True)
        eval_claude = self._make_eval("claude", "sonnet", "high", True, "sufficient", True)
        eval_insuf = self._make_eval("codex", "gpt-5.6-terra", "high", True, "insufficient", False)

        cand_codex_pri = self._make_cand("codex", "gpt-5.6-terra", "high", "primary")
        cand_codex_fb = self._make_cand("codex", "gpt-5.6-terra", "high", "fallback")
        cand_codex_un = self._make_cand("codex", "gpt-5.6-terra", "high", "unassigned")
        cand_claude_fb = self._make_cand("claude", "sonnet", "high", "fallback")
        cand_claude_pri = self._make_cand("claude", "sonnet", "high", "primary")
        cand_claude_un = self._make_cand("claude", "sonnet", "high", "unassigned")

        # --- A. CONCLUSIVE ---
        # Valid: 1 candidate (primary), null tie-break
        self.assertTrue(validate_classification_data(make_payload("conclusive", None, [eval_codex], [cand_codex_pri]))[0])
        # Valid: 2 candidates (primary + fallback)
        self.assertTrue(validate_classification_data(make_payload("conclusive", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_fb]))[0])
        # Reject: empty candidates
        self.assertFalse(validate_classification_data(make_payload("conclusive", None, [eval_codex], []))[0])
        # Reject: candidate[0] is fallback
        self.assertFalse(validate_classification_data(make_payload("conclusive", None, [eval_codex], [cand_codex_fb]))[0])
        # Reject: candidate[0] is unassigned
        self.assertFalse(validate_classification_data(make_payload("conclusive", None, [eval_codex], [cand_codex_un]))[0])
        # Reject: candidate[1] is primary
        self.assertFalse(validate_classification_data(make_payload("conclusive", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_pri]))[0])
        # Reject: candidate[1] is unassigned
        self.assertFalse(validate_classification_data(make_payload("conclusive", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_un]))[0])
        # Reject: tie_break_applied != None
        self.assertFalse(validate_classification_data(make_payload("conclusive", "some_tie_break", [eval_codex], [cand_codex_pri]))[0])

        # --- B. UNDERDETERMINED ---
        tb_valid = "project_priority: codex/*/*"
        # Valid: 1 candidate (primary) + non-empty tie_break
        self.assertTrue(validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_pri]))[0])
        # Valid: 2 candidates (primary + fallback) + non-empty tie_break
        self.assertTrue(validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_fb]))[0])
        # Reject: empty candidates
        v, errs = validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex], []))
        self.assertFalse(v)
        self.assertTrue(any("at least 1 candidate" in e for e in errs))
        # Reject: candidate[0] is fallback
        v, errs = validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_fb]))
        self.assertFalse(v)
        self.assertTrue(any('candidates[0].dispatch_role == "primary"' in e for e in errs))
        # Reject: candidate[0] is unassigned
        v, errs = validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_un]))
        self.assertFalse(v)
        self.assertTrue(any('candidates[0].dispatch_role == "primary"' in e for e in errs))
        # Reject: candidate[1] is primary
        v, errs = validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_pri]))
        self.assertFalse(v)
        self.assertTrue(any('dispatch_role == "fallback"' in e for e in errs))
        # Reject: candidate[1] is unassigned
        v, errs = validate_classification_data(make_payload("underdetermined", tb_valid, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_un]))
        self.assertFalse(v)
        self.assertTrue(any('dispatch_role == "fallback"' in e for e in errs))
        # Reject: tie_break_applied is null
        v, errs = validate_classification_data(make_payload("underdetermined", None, [eval_codex], [cand_codex_pri]))
        self.assertFalse(v)
        self.assertTrue(any("non-empty tie_break_applied" in e for e in errs))
        # Reject: tie_break_applied is empty string
        v, errs = validate_classification_data(make_payload("underdetermined", "", [eval_codex], [cand_codex_pri]))
        self.assertFalse(v)
        self.assertTrue(any("non-empty tie_break_applied" in e for e in errs))

        # --- C. AWAITING_OPERATOR ---
        # Valid: 2 candidates, both unassigned, tie_break_applied=None
        v, errs = validate_classification_data(make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_un, cand_claude_un]))
        self.assertTrue(v, f"Valid awaiting_operator rejected: {errs}")
        # Reject: less than 2 candidates
        self.assertFalse(validate_classification_data(make_payload("awaiting_operator", None, [eval_codex], [cand_codex_un]))[0])
        # Reject: candidate[0] is primary
        self.assertFalse(validate_classification_data(make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_un]))[0])
        # Reject: candidate[0] is fallback
        self.assertFalse(validate_classification_data(make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_fb, cand_claude_un]))[0])
        # Reject: candidate[1] is primary
        self.assertFalse(validate_classification_data(make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_un, cand_claude_pri]))[0])
        # Reject: candidate[1] is fallback
        self.assertFalse(validate_classification_data(make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_un, cand_claude_fb]))[0])
        # Reject: tie_break_applied is "ask"
        v, errs = validate_classification_data(make_payload("awaiting_operator", "ask", [eval_codex, eval_claude], [cand_codex_un, cand_claude_un]))
        self.assertFalse(v)
        self.assertTrue(any("awaiting_operator status requires tie_break_applied to be null" in e for e in errs))
        # Reject: tie_break_applied is "project_priority: ..."
        v, errs = validate_classification_data(make_payload("awaiting_operator", "project_priority: codex/*/*", [eval_codex, eval_claude], [cand_codex_un, cand_claude_un]))
        self.assertFalse(v)
        self.assertTrue(any("awaiting_operator status requires tie_break_applied to be null" in e for e in errs))

        # --- D. INFEASIBLE ---
        # Valid: empty candidates, null tie_break
        self.assertTrue(validate_classification_data(make_payload("infeasible", None, [eval_insuf], []))[0])
        # Reject: 1 candidate (primary)
        v, errs = validate_classification_data(make_payload("infeasible", None, [eval_insuf], [cand_codex_pri]))
        self.assertFalse(v)
        self.assertTrue(any("infeasible status requires candidates[] to be empty" in e for e in errs))
        # Reject: 1 candidate (fallback)
        v, errs = validate_classification_data(make_payload("infeasible", None, [eval_insuf], [cand_codex_fb]))
        self.assertFalse(v)
        self.assertTrue(any("infeasible status requires candidates[] to be empty" in e for e in errs))
        # Reject: 1 candidate (unassigned)
        v, errs = validate_classification_data(make_payload("infeasible", None, [eval_insuf], [cand_codex_un]))
        self.assertFalse(v)
        self.assertTrue(any("infeasible status requires candidates[] to be empty" in e for e in errs))
        # Reject: tie_break_applied != None
        v, errs = validate_classification_data(make_payload("infeasible", "some_tie_break", [eval_insuf], []))
        self.assertFalse(v)
        self.assertTrue(any("infeasible status requires tie_break_applied to be null" in e for e in errs))

        # --- E. PARITY CHECK ON STATE MATRIX ---
        parity_cases = [
            ("conclusive_valid", True, make_payload("conclusive", None, [eval_codex], [cand_codex_pri])),
            ("conclusive_fb_at_0", False, make_payload("conclusive", None, [eval_codex], [cand_codex_fb])),
            ("conclusive_pri_at_1", False, make_payload("conclusive", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_pri])),
            ("conclusive_with_tb", False, make_payload("conclusive", "tb", [eval_codex], [cand_codex_pri])),
            ("underdetermined_valid", True, make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_pri])),
            ("underdetermined_empty_cands", False, make_payload("underdetermined", tb_valid, [eval_codex], [])),
            ("underdetermined_fb_at_0", False, make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_fb])),
            ("underdetermined_un_at_0", False, make_payload("underdetermined", tb_valid, [eval_codex], [cand_codex_un])),
            ("underdetermined_pri_at_1", False, make_payload("underdetermined", tb_valid, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_pri])),
            ("underdetermined_un_at_1", False, make_payload("underdetermined", tb_valid, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_un])),
            ("underdetermined_null_tb", False, make_payload("underdetermined", None, [eval_codex], [cand_codex_pri])),
            ("underdetermined_empty_tb", False, make_payload("underdetermined", "", [eval_codex], [cand_codex_pri])),
            ("awaiting_valid", True, make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_un, cand_claude_un])),
            ("awaiting_1_cand", False, make_payload("awaiting_operator", None, [eval_codex], [cand_codex_un])),
            ("awaiting_pri_at_0", False, make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_pri, cand_claude_un])),
            ("awaiting_fb_at_0", False, make_payload("awaiting_operator", None, [eval_codex, eval_claude], [cand_codex_fb, cand_claude_un])),
            ("awaiting_with_tb_ask", False, make_payload("awaiting_operator", "ask", [eval_codex, eval_claude], [cand_codex_un, cand_claude_un])),
            ("awaiting_with_tb_priority", False, make_payload("awaiting_operator", "project_priority: codex/*/*", [eval_codex, eval_claude], [cand_codex_un, cand_claude_un])),
            ("infeasible_valid", True, make_payload("infeasible", None, [eval_insuf], [])),
            ("infeasible_pri_cand", False, make_payload("infeasible", None, [eval_insuf], [cand_codex_pri])),
            ("infeasible_fb_cand", False, make_payload("infeasible", None, [eval_insuf], [cand_codex_fb])),
            ("infeasible_un_cand", False, make_payload("infeasible", None, [eval_insuf], [cand_codex_un])),
            ("infeasible_with_tb", False, make_payload("infeasible", "tb", [eval_insuf], [])),
        ]
        for name, expected, payload in parity_cases:
            self.assertEqual(validate_classification_data(payload)[0], expected, f"Parity mismatch in Python validator for {name}")

    def test_r11_hygiene_guard_no_private_scratch_paths_in_t019_content_paths(self) -> None:
        """Finding R11: Hygiene guard proving no private scratch or machine paths exist in T019 content paths."""
        t019_paths = [
            "distribution-manifest.json",
            "README.md",
            "SKILL.md",
            "docs/PROJECT_CONFIGURATION.md",
            "docs/WORK_MODEL.md",
            "prompts/classifier.md",
            "prompts/orchestrator.md",
            "prompts/orchestrator-perfis.md",
            "schemas/classification-result-v3.schema.json",
            "scripts/validate_classification.py",
            "scripts/tests/test_dynamic_primary_selection.py",
            "scripts/tests/test_automatic_mode.py",
            "CHANGELOG.md",
        ]
        forbidden_patterns = [
            "/Us" + "ers/",
            ".gem" + "ini/",
            "antigravity/" + "brain",
            "/ho" + "me/",
        ]
        violations = []
        for rel_path in t019_paths:
            full_path = ROOT / rel_path
            self.assertTrue(full_path.exists(), f"Content path {rel_path} does not exist")
            content = full_path.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), start=1):
                for pat in forbidden_patterns:
                    if pat in line:
                        violations.append(f"{rel_path}:{line_no} contains forbidden pattern '{pat}': {line.strip()}")

        self.assertEqual(violations, [], f"Private scratch/machine paths detected in versioned files:\n" + "\n".join(violations))

    def test_r11_and_r12_ajv_draft2020_12_direct_parity(self) -> None:
        """Findings R11 & R12: Portable direct AJV Draft 2020-12 validation and parity against Python validator."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("Node.js not found in environment; direct AJV parity test skipped")

        test_script = """
const fs = require('fs');
let Ajv2020;
try {
  Ajv2020 = require('ajv/dist/2020');
} catch (e) {
  console.log('AJV_UNAVAILABLE');
  process.exit(0);
}

const ajv = new Ajv2020({ allErrors: true });
const schema = JSON.parse(fs.readFileSync('schemas/classification-result-v3.schema.json', 'utf8'));
const validate = ajv.compile(schema);

function makePayload(status, tieBreak, candidates) {
  const role = {
    tier: 'heavy',
    selection_status: status,
    reason: 'test',
    tie_break_applied: tieBreak,
    evaluations: [{
      harness: 'codex', model: 'gpt-5.6-terra', effort: 'high',
      catalog_eligible: true, technical_adequacy: 'sufficient', dispatchable: true,
      cost_basis: 'token_price_only', evidence_ids: ['ev-1'], uncertainty: null, reason: 'test'
    }],
    candidates: candidates
  };
  if (status === 'conclusive' || status === 'underdetermined') {
    role.selection_basis = 'minimum_sufficient';
    role.escalation_reason = null;
  }
  return {
    schema_version: 3,
    story_id: 'T019',
    phase: 'implementation',
    context_revision: 'ctx',
    catalog_revision: 'cat',
    confidence: 'high',
    facts: ['test'],
    uncertainties: [],
    reclassify_when: ['test'],
    roles: {
      maker: role
    }
  };
}

const cPri = { harness: 'codex', model: 'gpt-5.6-terra', effort: 'high', dispatch_role: 'primary', evidence_ids: ['ev-1'], cost_basis: 'token_price_only', reason: 'test' };
const cFb = { harness: 'codex', model: 'gpt-5.6-terra', effort: 'high', dispatch_role: 'fallback', evidence_ids: ['ev-1'], cost_basis: 'token_price_only', reason: 'test' };
const cUn = { harness: 'codex', model: 'gpt-5.6-terra', effort: 'high', dispatch_role: 'unassigned', evidence_ids: ['ev-1'], cost_basis: 'token_price_only', reason: 'test' };

const suite = [
  // Conclusive
  { name: 'conclusive_valid', expected: true, payload: makePayload('conclusive', null, [cPri]) },
  { name: 'conclusive_fb_at_0', expected: false, payload: makePayload('conclusive', null, [cFb]) },
  { name: 'conclusive_pri_at_1', expected: false, payload: makePayload('conclusive', null, [cPri, cPri]) },
  { name: 'conclusive_with_tie_break', expected: false, payload: makePayload('conclusive', 'tb', [cPri]) },

  // Underdetermined
  { name: 'underdetermined_valid', expected: true, payload: makePayload('underdetermined', 'tb', [cPri]) },
  { name: 'underdetermined_empty_cands', expected: false, payload: makePayload('underdetermined', 'tb', []) },
  { name: 'underdetermined_fb_at_0', expected: false, payload: makePayload('underdetermined', 'tb', [cFb]) },
  { name: 'underdetermined_un_at_0', expected: false, payload: makePayload('underdetermined', 'tb', [cUn]) },
  { name: 'underdetermined_pri_at_1', expected: false, payload: makePayload('underdetermined', 'tb', [cPri, cPri]) },
  { name: 'underdetermined_un_at_1', expected: false, payload: makePayload('underdetermined', 'tb', [cPri, cUn]) },
  { name: 'underdetermined_null_tb', expected: false, payload: makePayload('underdetermined', null, [cPri]) },
  { name: 'underdetermined_empty_tb', expected: false, payload: makePayload('underdetermined', '', [cPri]) },

  // Awaiting Operator
  { name: 'awaiting_valid', expected: true, payload: makePayload('awaiting_operator', null, [cUn, cUn]) },
  { name: 'awaiting_1_cand', expected: false, payload: makePayload('awaiting_operator', null, [cUn]) },
  { name: 'awaiting_pri_at_0', expected: false, payload: makePayload('awaiting_operator', null, [cPri, cUn]) },
  { name: 'awaiting_fb_at_0', expected: false, payload: makePayload('awaiting_operator', null, [cFb, cUn]) },
  { name: 'awaiting_with_tb_ask', expected: false, payload: makePayload('awaiting_operator', 'ask', [cUn, cUn]) },
  { name: 'awaiting_with_tb_priority', expected: false, payload: makePayload('awaiting_operator', 'project_priority: codex/*/*', [cUn, cUn]) },

  // Infeasible
  { name: 'infeasible_valid', expected: true, payload: makePayload('infeasible', null, []) },
  { name: 'infeasible_pri_cand', expected: false, payload: makePayload('infeasible', null, [cPri]) },
  { name: 'infeasible_fb_cand', expected: false, payload: makePayload('infeasible', null, [cFb]) },
  { name: 'infeasible_un_cand', expected: false, payload: makePayload('infeasible', null, [cUn]) },
  { name: 'infeasible_with_tb', expected: false, payload: makePayload('infeasible', 'tb', []) },
];

for (const tc of suite) {
  const actual = validate(tc.payload);
  if (actual !== tc.expected) {
    console.error(`PARITY FAIL in AJV for case ${tc.name}: expected ${tc.expected}, got ${actual}`);
    process.exit(1);
  }
}

console.log('AJV_PARITY_OK');
"""
        proc = subprocess.run(
            [node_bin, "-e", test_script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if "AJV_UNAVAILABLE" in proc.stdout:
            self.skipTest("ajv/dist/2020 is not available in standard Node resolution paths; direct AJV validation skipped")

        self.assertEqual(proc.returncode, 0, f"AJV parity test failed: {proc.stderr}\n{proc.stdout}")
        self.assertIn("AJV_PARITY_OK", proc.stdout)


class MinimumSufficientCapabilityTest(unittest.TestCase):
    """Mandatory contractual and behavior tests for T031: Minimum Sufficient Capability & Efficiency Preference Policy."""

    def _make_eval(
        self,
        harness: str,
        model: str,
        effort: str,
        adequacy: str = "sufficient",
        dispatchable: bool = True,
        eligible: bool = True,
    ) -> dict[str, Any]:
        return {
            "harness": harness,
            "model": model,
            "effort": effort,
            "catalog_eligible": eligible,
            "technical_adequacy": adequacy,
            "dispatchable": dispatchable,
            "evidence_ids": ["price-flash" if harness == "agy" else "price-terra"],
            "uncertainty": None if adequacy != "uncertain" else "Material uncertainty regarding complex edge cases",
            "reason": f"Evaluation for {harness}/{model}/{effort}",
        }

    def test_case_1_all_sufficient_prefers_codex_high(self) -> None:
        """Caso 1: Agy, Codex high, Codex xhigh e Claude todos sufficient -> Codex High primário pela preferência global."""
        evals = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high"),
            self._make_eval("codex", "gpt-5.6-terra", "high"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh"),
            self._make_eval("claude", "sonnet", "high"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("codex", "gpt-5.6-terra", "high"))
        self.assertEqual(basis, "minimum_sufficient")
        self.assertIsNone(esc_reason)

    def test_case_2_codex_insufficient_falls_back_to_gemini(self) -> None:
        """Caso 2: Codex High insufficient e Gemini sufficient -> Gemini assume sem promover Codex xhigh."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("agy", "gemini-3.8-flash-high", "high"))
        self.assertEqual(basis, "escalation")
        self.assertEqual(esc_reason, "efficient_candidate_insufficient")

    def test_case_3_same_model_effort_high_vs_xhigh_selects_high(self) -> None:
        """Caso 3: Dentro do mesmo modelo (Codex), high e xhigh ambos sufficient -> high vence por minimum-sufficient effort."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("codex", "gpt-5.6-terra", "high"))
        self.assertEqual(basis, "minimum_sufficient")
        self.assertIsNone(esc_reason)

    def test_case_4_concrete_technical_necessity_allows_escalation(self) -> None:
        """Caso 4: Necessidade técnica concreta comprovada (require_xhigh=True) autoriza escalada com xhigh."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals, require_xhigh=True)
        self.assertEqual(winner, ("codex", "gpt-5.6-terra", "xhigh"))
        self.assertEqual(basis, "escalation")
        self.assertEqual(esc_reason, "concrete_technical_necessity")

    def test_case_5_codex_uncertain_falls_back_with_reason(self) -> None:
        """Caso 5: Codex High uncertain e Gemini sufficient -> Gemini assume com razão explícita."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="uncertain", dispatchable=False),
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient"),
            self._make_eval("claude", "sonnet", "high", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("agy", "gemini-3.8-flash-high", "high"))
        self.assertEqual(basis, "escalation")
        self.assertEqual(esc_reason, "efficient_candidate_uncertain")

    def test_case_6_codex_unavailable_falls_back_to_gemini(self) -> None:
        """Caso 6: Codex High indisponível no pre-dispatch -> Gemini assume deterministicamente."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(
            evals,
            pre_dispatch_unavailable={("codex", "gpt-5.6-terra", "high")},
        )
        self.assertEqual(winner, ("agy", "gemini-3.8-flash-high", "high"))
        self.assertEqual(basis, "escalation")
        self.assertEqual(esc_reason, "pre_dispatch_unavailable")

    def test_case_7_tier_heavy_still_prefers_codex_high_over_xhigh(self) -> None:
        """Caso 7: tier heavy não força xhigh; Codex High sufficient continua sendo o primário global."""
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        winner, basis, esc_reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("codex", "gpt-5.6-terra", "high"))
        self.assertEqual(basis, "minimum_sufficient")

        # Validar payload completo com tier heavy e selection_basis minimum_sufficient
        data = {
            "schema_version": 3,
            "story_id": "T031-canary-heavy",
            "phase": "implementation",
            "context_revision": "ctx-heavy",
            "catalog_revision": "cat-heavy",
            "confidence": "high",
            "facts": ["Tier heavy task where efficient candidate is technically sufficient"],
            "uncertainties": [],
            "reclassify_when": ["Scope changes"],
            "roles": {
                "maker": {
                    "tier": "heavy",
                    "selection_status": "conclusive",
                    "selection_basis": "minimum_sufficient",
                    "escalation_reason": None,
                    "reason": "Maker classificado com base em capacidade minima suficiente.",
                    "tie_break_applied": None,
                    "evaluations": evals,
                    "candidates": [
                        {
                            "harness": "codex",
                            "model": "gpt-5.6-terra",
                            "effort": "high",
                            "dispatch_role": "primary",
                            "evidence_ids": ["price-terra"],
                            "cost_basis": "token_price_only",
                            "reason": "Preferência global do Maker e adequação técnica suficiente.",
                        },
                        {
                            "harness": "agy",
                            "model": "gemini-3.8-flash-high",
                            "effort": "high",
                            "dispatch_role": "fallback",
                            "evidence_ids": ["price-flash"],
                            "cost_basis": "token_price_only",
                            "reason": "Fallback de quota ou infraestrutura do Maker.",
                        },
                        {
                            "harness": "codex",
                            "model": "gpt-5.6-terra",
                            "effort": "xhigh",
                            "dispatch_role": "fallback",
                            "evidence_ids": ["price-terra"],
                            "cost_basis": "token_price_only",
                            "reason": "Escalada de effort somente com necessidade concreta.",
                        },
                    ],
                }
            },
        }
        ok, errors = validate_classification_data(data)
        self.assertTrue(ok, f"Validation failed: {errors}")

    def test_case_8_rejection_of_forbidden_overselection_phrases(self) -> None:
        """Caso 8: Rejeição estrita de argumentos vazios de over-selection ('frontier model', 'mais forte', 'tier heavy exige modelo máximo')."""
        forbidden_samples = [
            "Optamos pelo Codex por ser um frontier model de maior capacidade.",
            "Modelo mais forte selecionado para garantir precisão.",
            "Tier heavy exige modelo maximo para o papel Maker.",
            "Maior capacidade de raciocinio para codigo complexo.",
            "Maior densidade arquitetural observada no modelo.",
        ]
        evals = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
        ]
        for phrase in forbidden_samples:
            data = {
                "schema_version": 3,
                "story_id": "T031-overselection-rejection",
                "phase": "implementation",
                "context_revision": "ctx-test",
                "catalog_revision": "cat-test",
                "confidence": "high",
                "facts": ["Testing rejection of buzzwords"],
                "uncertainties": [],
                "reclassify_when": ["Scope changes"],
                "roles": {
                    "maker": {
                        "tier": "heavy",
                        "selection_status": "conclusive",
                        "selection_basis": "escalation",
                        "escalation_reason": phrase,
                        "reason": f"Justificativa: {phrase}",
                        "tie_break_applied": None,
                        "evaluations": evals,
                        "candidates": [
                            {
                                "harness": "codex",
                                "model": "gpt-5.6-terra",
                                "effort": "high",
                                "dispatch_role": "primary",
                                "evidence_ids": ["price-terra"],
                                "cost_basis": "token_price_only",
                                "reason": phrase,
                            }
                        ],
                    }
                },
            }
            ok, errors = validate_classification_data(data)
            self.assertFalse(ok, f"Expected validation to fail for phrase: '{phrase}'")
            self.assertTrue(
                any("forbidden over-selection phrase" in e for e in errors),
                f"Expected forbidden phrase error for '{phrase}', got: {errors}",
            )


class MinimumSufficientEnforcementTest(unittest.TestCase):
    """Negative and permutation tests enforcing fail-closed MSC and resolver invariants."""

    def _make_eval(
        self,
        harness: str,
        model: str,
        effort: str,
        adequacy: str = "sufficient",
        dispatchable: bool = True,
        eligible: bool = True,
        reason: str = "Evaluation reason",
    ) -> dict[str, Any]:
        return {
            "harness": harness,
            "model": model,
            "effort": effort,
            "catalog_eligible": eligible,
            "technical_adequacy": adequacy,
            "dispatchable": dispatchable,
            "evidence_ids": ["price-test"],
            "uncertainty": None,
            "reason": reason,
        }

    def _make_cand(
        self,
        harness: str,
        model: str,
        effort: str,
        dispatch_role: str = "primary",
        evidence_ids: list[str] | None = None,
        reason: str = "Candidate reason",
    ) -> dict[str, Any]:
        return {
            "harness": harness,
            "model": model,
            "effort": effort,
            "dispatch_role": dispatch_role,
            "evidence_ids": evidence_ids or ["price-test"],
            "cost_basis": "token_price_only",
            "reason": reason,
        }

    def _base_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 3,
            "story_id": "T031-enforcement",
            "phase": "implementation",
            "context_revision": "ctx-enf",
            "catalog_revision": "cat-enf",
            "confidence": "high",
            "facts": ["MSC enforcement testing"],
            "uncertainties": [],
            "reclassify_when": ["Scope change"],
            "roles": {},
        }

    def test_missing_selection_basis_fails_when_primary_present(self) -> None:
        """Conclusive and underdetermined states require selection_basis."""
        payload = self._base_payload()
        evals = [self._make_eval("agy", "gemini-3.8-flash-high", "high")]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("requires selection_basis" in e for e in errors))

    def test_invalid_selection_basis_enum_fails(self) -> None:
        """selection_basis must be one of allowed enum values."""
        payload = self._base_payload()
        evals = [self._make_eval("agy", "gemini-3.8-flash-high", "high")]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "arbitrary_choice",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("selection_basis invalid" in e for e in errors))

    def test_escalation_requires_valid_closed_enum_escalation_reason(self) -> None:
        """selection_basis: escalation requires a valid enum escalation_reason."""
        payload = self._base_payload()
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("agy", "gemini-3.8-flash-high", "high"),
        ]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]

        # Missing escalation_reason
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "escalation",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("requires non-empty escalation_reason" in e for e in errors))

        # Invalid escalation_reason enum (e.g. 'because it feels stronger')
        payload["roles"]["maker"]["escalation_reason"] = "because it feels stronger"
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("invalid enum value" in e for e in errors))

        # Valid escalation_reason enum
        payload["roles"]["maker"]["escalation_reason"] = "efficient_candidate_insufficient"
        ok, errors = validate_classification_data(payload)
        self.assertTrue(ok, f"Expected valid escalation to pass, got: {errors}")

    def test_non_escalation_with_non_null_escalation_reason_fails(self) -> None:
        """selection_basis != escalation must have null or omitted escalation_reason."""
        payload = self._base_payload()
        evals = [self._make_eval("agy", "gemini-3.8-flash-high", "high")]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "escalation_reason": "efficient_candidate_insufficient",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("escalation_reason must be null when selection_basis is not 'escalation'" in e for e in errors))

    def test_forbidden_phrase_in_evaluations_reason_fails(self) -> None:
        """Direct probe: forbidden over-selection phrase in evaluations[].reason must be rejected."""
        payload = self._base_payload()
        evals = [
            self._make_eval(
                "agy",
                "gemini-3.8-flash-high",
                "high",
                reason="frontier model is preferred for this phase",
            )
        ]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("roles.maker.evaluations[0].reason contains forbidden over-selection phrase" in e for e in errors))

    def test_xhigh_without_concrete_technical_necessity_fails(self) -> None:
        """xhigh effort when same-model high is sufficient cannot be justified by mere substring mention; requires concrete_technical_necessity."""
        payload = self._base_payload()
        evals = [
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        cands = [
            self._make_cand("codex", "gpt-5.6-terra", "xhigh", "primary"),
        ]

        # Mere mention of 'xhigh' in reason without escalation basis fails
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "reason": "Selecting xhigh effort because of high architectural density",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("violating minimum sufficient effort" in e or "primary candidate uses effort 'xhigh'" in e for e in errors))

        # Escalation with wrong escalation_reason fails
        payload["roles"]["maker"]["selection_basis"] = "escalation"
        payload["roles"]["maker"]["escalation_reason"] = "efficient_candidate_insufficient"
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("Requires selection_basis 'escalation' with escalation_reason 'concrete_technical_necessity'" in e for e in errors))

        # Escalation with concrete_technical_necessity and evidence_ids passes
        payload["roles"]["maker"]["escalation_reason"] = "concrete_technical_necessity"
        cands[0]["evidence_ids"] = ["formal-proof-artifact-1"]
        ok, errors = validate_classification_data(payload)
        self.assertTrue(ok, f"Expected concrete technical necessity to pass, got: {errors}")

    def test_partial_pins_deterministic_across_input_order_permutations(self) -> None:
        """Partial pins must resolve deterministically by eff_order regardless of input order."""
        eval_z = self._make_eval("codex", "model-z", "high")
        eval_a = self._make_eval("codex", "model-a", "high")

        # Order 1: [z, a]
        res1, basis1, _ = resolve_minimum_sufficient([eval_z, eval_a], pins={"harness": "codex"})
        # Order 2: [a, z]
        res2, basis2, _ = resolve_minimum_sufficient([eval_a, eval_z], pins={"harness": "codex"})

        self.assertEqual(res1, res2, f"Partial pin was non-deterministic: {res1} vs {res2}")
        self.assertEqual(basis1, "pinned")
        self.assertEqual(basis2, "pinned")

        # Now with gpt-5.6-terra (in DEFAULT_EFFICIENCY_ORDER) vs model-z (not in DEFAULT_EFFICIENCY_ORDER)
        eval_terra = self._make_eval("codex", "gpt-5.6-terra", "high")
        res3, _, _ = resolve_minimum_sufficient([eval_z, eval_terra], pins={"harness": "codex"})
        res4, _, _ = resolve_minimum_sufficient([eval_terra, eval_z], pins={"harness": "codex"})
        self.assertEqual(res3, ("codex", "gpt-5.6-terra", "high"))
        self.assertEqual(res4, ("codex", "gpt-5.6-terra", "high"))

    def test_default_efficiency_order_prefers_terra_xhigh_over_opus(self) -> None:
        """When Agy, Terra high and Sonnet are insufficient, Terra xhigh is chosen before Opus in default policy."""
        evals = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("claude", "sonnet", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("claude", "claude-opus-5", "high", adequacy="sufficient"),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient"),
        ]
        winner, basis, reason = resolve_minimum_sufficient(evals)
        self.assertEqual(winner, ("codex", "gpt-5.6-terra", "xhigh"))
        self.assertEqual(basis, "escalation")
        self.assertNotEqual(winner[0], "claude")
        self.assertNotEqual(winner[1], "claude-opus-5")

    def test_escalation_contradicted_by_sufficient_efficient_candidate_fails(self) -> None:
        """Codex's round 2 counterproof: escalation cannot claim efficient_candidate_insufficient when Agy is evaluated as sufficient."""
        payload = self._base_payload()
        evals = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="sufficient", dispatchable=True),
            self._make_eval("codex", "gpt-5.6-terra", "xhigh", adequacy="sufficient", dispatchable=True),
        ]
        cands = [self._make_cand("codex", "gpt-5.6-terra", "xhigh", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "escalation",
                "escalation_reason": "efficient_candidate_insufficient",
                "reason": "Claiming Agy is insufficient despite evaluation marking it sufficient",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(
            any("is contradicted by evaluation for ('agy', 'gemini-3.8-flash-high', 'high')" in e for e in errors),
            f"Expected contradiction error, got: {errors}",
        )

    def test_duplicate_evaluations_for_same_pair_fails(self) -> None:
        """Evaluations with duplicate (harness, model, effort) pairs must be rejected fail-closed."""
        payload = self._base_payload()
        evals = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high"),
            self._make_eval("agy", "gemini-3.8-flash-high", "high"),
        ]
        cands = [self._make_cand("agy", "gemini-3.8-flash-high", "high", "primary")]
        payload["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "selection_basis": "minimum_sufficient",
                "reason": "Test reason",
                "tie_break_applied": None,
                "evaluations": evals,
                "candidates": cands,
            }
        }
        ok, errors = validate_classification_data(payload)
        self.assertFalse(ok)
        self.assertTrue(any("contains duplicate evaluation" in e for e in errors))

    def test_resolver_deterministic_for_extra_candidates_outside_default_order(self) -> None:
        """Codex's round 2 counterproof: resolver must be deterministic for extra candidates outside default order."""
        base = [
            self._make_eval("agy", "gemini-3.8-flash-high", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("codex", "gpt-5.6-terra", "high", adequacy="insufficient", dispatchable=False),
            self._make_eval("claude", "sonnet", "high", adequacy="insufficient", dispatchable=False),
        ]
        a = self._make_eval("codex", "model-a", "high", adequacy="sufficient", dispatchable=True)
        z = self._make_eval("codex", "model-z", "high", adequacy="sufficient", dispatchable=True)

        res1, basis1, reason1 = resolve_minimum_sufficient(base + [z, a])
        res2, basis2, reason2 = resolve_minimum_sufficient(base + [a, z])

        self.assertEqual(res1, ("codex", "model-a", "high"))
        self.assertEqual(res2, ("codex", "model-a", "high"))
        self.assertEqual(res1, res2)
        self.assertEqual(basis1, "escalation")
        self.assertEqual(basis2, "escalation")
        self.assertEqual(reason1, "efficient_candidate_insufficient")
        self.assertEqual(reason2, "efficient_candidate_insufficient")


if __name__ == "__main__":
    unittest.main()
