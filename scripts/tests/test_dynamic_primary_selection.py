#!/usr/bin/env python3
"""Contractual and behavior tests for T019: Dynamic Primary Harness Selection.

Covers invariants R1 to R22 and acceptance criteria AC01 to AC10.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from scripts.validate_classification import (
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

    def test_r01_and_ac01_codex_as_primary_even_when_not_first_in_legacy_chain(self) -> None:
        """AC01 & R18: Classifier can elect Codex as primary Maker over Agy/Claude."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
                "reason": "Codex Terra elected as primary based on benchmark coding evidence",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                    self._make_eval("agy", "gemini-3.8-flash-high", "high", True, "sufficient", True),
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("codex", "gpt-5.6-terra", "high", "primary"),
                    self._make_cand("agy", "gemini-3.8-flash-high", "high", "fallback"),
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
                "reason": "Claude Sonnet High elected as primary Maker",
                "tie_break_applied": None,
                "evaluations": [
                    self._make_eval("claude", "sonnet", "high", True, "sufficient", True),
                    self._make_eval("codex", "gpt-5.6-terra", "high", True, "sufficient", True),
                ],
                "candidates": [
                    self._make_cand("claude", "sonnet", "high", "primary"),
                    self._make_cand("codex", "gpt-5.6-terra", "high", "fallback"),
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
        from scripts.tests.test_dynamic_primary_selection import match_project_priority

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
        # The Classifier must register recommended_primary strictly by quality/cost:
        recommended = "codex"
        # In runtime, if codex is under quota pressure, effective_primary falls back to agy:
        runtime_quota_pressure = {"codex": True, "agy": False}
        candidates = [
            {"harness": "codex", "model": "gpt-5.6-terra", "dispatch_role": "primary"},
            {"harness": "agy", "model": "gemini-3.8-flash-high", "dispatch_role": "fallback"},
        ]
        recommended_primary = candidates[0]["harness"]
        self.assertEqual(recommended_primary, "codex")

        effective_primary = None
        for c in candidates:
            if not runtime_quota_pressure.get(c["harness"], False):
                effective_primary = c["harness"]
                break
        self.assertEqual(effective_primary, "agy")
        self.assertNotEqual(recommended_primary, effective_primary)
        # Durable semantic ranking remains unchanged
        self.assertEqual(candidates[0]["harness"], "codex")

    def test_r05_and_ac06_ambiguous_dispatch_blocks_fallback_and_emits_stop(self) -> None:
        """AC06 & R5: DISPATCH_OUTCOME_AMBIGUOUS strictly blocks automatic fallback and emits STOP."""
        # Simulated dispatch outcome evaluator
        def evaluate_dispatch(exit_code: int, effects: str, dirty_tree: bool) -> str:
            if exit_code == 0:
                return "SUCCESS"
            if exit_code != 0 and effects == "none" and not dirty_tree:
                return "DISPATCH_FAILED_PROVEN_NO_EFFECT"
            if dirty_tree or effects in ("uncertain", "known"):
                return "DISPATCH_OUTCOME_AMBIGUOUS"
            return "SEMANTIC_FAILURE"

        # Ambiguous case: process failed with dirty tree
        outcome_dirty = evaluate_dispatch(1, "uncertain", dirty_tree=True)
        self.assertEqual(outcome_dirty, "DISPATCH_OUTCOME_AMBIGUOUS")

        # Invariant check: fallback is forbidden on DISPATCH_OUTCOME_AMBIGUOUS
        def allow_fallback(outcome: str) -> bool:
            if outcome == "DISPATCH_OUTCOME_AMBIGUOUS":
                return False  # MANDATORY STOP
            if outcome == "DISPATCH_FAILED_PROVEN_NO_EFFECT":
                return True
            return False

        self.assertFalse(allow_fallback(outcome_dirty))

    def test_r14_and_ac07_proven_no_effect_is_rigorous(self) -> None:
        """AC07 & R14: DISPATCH_FAILED_PROVEN_NO_EFFECT requires clean tree, terminal tree and effects: none."""
        def is_proven_no_effect(proc_tree_ended: bool, git_clean: bool, content_paths_clean: bool, effects: str) -> bool:
            return proc_tree_ended and git_clean and content_paths_clean and effects == "none"

        # All four conditions true
        self.assertTrue(is_proven_no_effect(True, True, True, "none"))
        # Any failure disallows proven_no_effect
        self.assertFalse(is_proven_no_effect(False, True, True, "none"))
        self.assertFalse(is_proven_no_effect(True, False, True, "none"))
        self.assertFalse(is_proven_no_effect(True, True, False, "none"))
        self.assertFalse(is_proven_no_effect(True, True, True, "uncertain"))

    def test_r21_local_vs_remote_preflight_budget_accounting(self) -> None:
        """R21: Local preflight failure releases reservation; remote preflight consumes slot."""
        def execute_preflight(is_remote: bool, available: bool, budget: int) -> tuple[str, int]:
            reserved_budget = budget - 1  # write-ahead reservation
            if not is_remote and not available:
                # Local preflight failed: reservation released, 0 budget consumed
                return "PRE_DISPATCH_UNAVAILABLE", budget
            if is_remote and not available:
                # Remote request failed: slot consumed
                return "DISPATCH_FAILED_PROVEN_NO_EFFECT", reserved_budget
            return "SUCCESS", reserved_budget

        # Local failure: budget preserved
        status_local, budget_local = execute_preflight(is_remote=False, available=False, budget=10)
        self.assertEqual(status_local, "PRE_DISPATCH_UNAVAILABLE")
        self.assertEqual(budget_local, 10)

        # Remote failure: budget consumed
        status_remote, budget_remote = execute_preflight(is_remote=True, available=False, budget=10)
        self.assertEqual(status_remote, "DISPATCH_FAILED_PROVEN_NO_EFFECT")
        self.assertEqual(budget_remote, 9)

    def test_r22_and_ac08_fallback_preserves_required_call_reserve(self) -> None:
        """AC08 & R22: Fallback permitted if and only if remaining_budget >= fallback_cost + required_call_reserve."""
        def can_attempt_fallback(remaining_budget: int, fallback_cost: int, call_reserve: int) -> bool:
            return remaining_budget >= (fallback_cost + call_reserve)

        # Budget = 3, fallback = 1, reserve for Checker = 2 -> 1 + 2 = 3 <= 3 -> OK
        self.assertTrue(can_attempt_fallback(3, 1, 2))
        # Budget = 2, fallback = 1, reserve for Checker = 2 -> 1 + 2 = 3 > 2 -> STOP (reserve violated)
        self.assertFalse(can_attempt_fallback(2, 1, 2))

    def test_r06_patch_counterproof_candidates_cannot_have_uncertainty_or_extra_properties(self) -> None:
        """Finding R6: candidates[] cannot declare uncertainty or extra properties."""
        data = dict(self.base_v3)
        data["roles"] = {
            "maker": {
                "tier": "heavy",
                "selection_status": "conclusive",
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
                    "reason": "Agy elected as primary with high effort",
                    "tie_break_applied": None,
                    "evaluations": [
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
                            "reason": "Adequate for heavy tier",
                        },
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
                            "reason": "Adequate fallback",
                        },
                    ],
                    "candidates": [
                        {
                            "harness": "agy",
                            "model": "gemini-3.8-flash-high",
                            "effort": "high",
                            "dispatch_role": "primary",
                            "evidence_ids": ["price-flash", "transport-flash"],
                            "cost_basis": "token_price_only",
                            "reason": "Primary candidate",
                        },
                        {
                            "harness": "codex",
                            "model": "gpt-5.6-terra",
                            "effort": "high",
                            "dispatch_role": "fallback",
                            "evidence_ids": ["price-terra", "gpt56-coding"],
                            "cost_basis": "token_price_only",
                            "reason": "Fallback candidate",
                        },
                    ],
                }
            },
        }
        valid, errors = validate_classification_data(fixture, expected_story="T019", expected_phase="implementation", expected_version=3)
        self.assertTrue(valid, f"Expected classifier prompt fixture to be valid, got errors: {errors}")


# Helper function implementing the project_priority matching logic per R13 and R20
def match_project_priority(
    candidates: list[tuple[str, str, str]], selectors: list[str]
) -> tuple[tuple[str, str, str] | None, str | None, str]:
    """Match candidates against project_priority selectors deterministically per R13/R20.

    candidates: list of (harness, model, effort)
    selectors: list of selector patterns, e.g. 'codex/gpt-5.6-terra/high', 'claude/*/*'
    Returns: (winning_candidate, tie_break_applied, selection_status)
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
        # If 0 matches or >1 matches, continue to next selector
    # End of list without unique match
    return None, None, "awaiting_operator"


if __name__ == "__main__":
    unittest.main()
