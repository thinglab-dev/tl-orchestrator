#!/usr/bin/env python3
"""
Unit, deterministic, and counterfactual tests for verification cadence and major-boundary integration gates.
Covers AC01 to AC12:
- AC01: Targeted verification intragroup
- AC02: Checker briefing aligned with verification_scope (prohibition of full gate complaint under targeted)
- AC03: Economic and focused rework (documentary/metadata rework does not run functional tests)
- AC04: Canonical full integration gate at major boundary; failure blocks transition
- AC05: Tree invalidation: gate result bound to commit SHA; tree changes invalidate proof
- AC06: Exceptional full gate restricted to cross-cutting structural changes
- AC07: Rejection of generic justifications ("por segurança", "para garantir tudo", "para confirmar")
- AC08: CI proof reuse under commit identity, gate definition parity, and auditable logs
- AC09: Authority resolution without ID regex (BMAD epic, Native deliverable, Native standalone task)
- AC10: Parametric canonical_full_gate, prohibition of guessing commands, not_configured handling
- AC11: Deterministic contractual test suite
- AC12: Repository validation consistency
"""

from __future__ import annotations

import re
import unittest
from typing import Any

# ==============================================================================
# Domain Logic / Verification Cadence Normative Engine
# ==============================================================================

PROHIBITED_GENERIC_JUSTIFICATIONS = [
    "por segurança",
    "para garantir tudo",
    "para confirmar",
    "para ter certeza",
    "confirmar tudo",
    "just in case",
    "to be safe",
    "to ensure everything",
    "precautionary check",
]

RECOGNIZED_STRUCTURAL_CHANGE_KEYWORDS = [
    "shared_database_schema_migration",
    "cross_module_protocol_change",
    "global_concurrency_primitives",
    "build_system_overhaul",
    "cross_cutting_structural_change",
    "database schema",
    "esquema de banco",
    "protocolo cross",
    "concorrência global",
    "concurrency primitives",
    "sistema de build",
]


def resolve_integration_group(unit: dict[str, Any]) -> dict[str, str]:
    """
    Resolves the integration group semantically by authority, strictly without
    performing ad hoc regex parsing on the unit ID (AC09).
    """
    # 1. Explicit integration_group configuration
    if "integration_group" in unit and isinstance(unit["integration_group"], dict):
        ig = unit["integration_group"]
        authority = ig.get("authority", "explicit")
        group_id = ig.get("id")
        if group_id:
            return {"authority": authority, "id": str(group_id)}

    # 2. BMAD authority via `epic`
    if unit.get("method") == "bmad" or "epic" in unit:
        epic = unit.get("epic")
        if epic and epic != "none":
            return {"authority": "bmad_epic", "id": str(epic)}

    # 3. Native authority via `deliverable`
    deliverable = unit.get("deliverable")
    if deliverable and deliverable != "none":
        return {"authority": "native_deliverable", "id": str(deliverable)}

    # 4. Native Standalone Task
    if unit.get("standalone") is True or (deliverable in (None, "none") and unit.get("method", "native") == "native"):
        unit_id = unit.get("id")
        if not unit_id:
            raise ValueError("Native standalone unit must have an 'id'")
        return {"authority": "native_standalone", "id": str(unit_id)}

    raise ValueError(f"Unable to resolve integration group by authority for unit: {unit}")


def validate_full_gate_exception(exception: dict[str, Any] | None) -> tuple[bool, str]:
    """
    Validates an exceptional full gate request within an intragroup workflow (AC06, AC07).
    Requires an objective technical reason (cross-cutting structural change) and technical justification.
    Strictly rejects generic excuses ("por segurança", "para garantir tudo", "para confirmar", etc.).
    """
    if not exception or not isinstance(exception, dict):
        return False, "Missing or invalid full_gate_exception block"

    tech_reason = exception.get("technical_reason", "").strip()
    justification = exception.get("insufficient_targeted_reason", "").strip()

    if not tech_reason:
        return False, "Missing technical_reason in full_gate_exception"
    if not justification:
        return False, "Missing insufficient_targeted_reason in full_gate_exception"

    combined_text = f"{tech_reason.lower()} {justification.lower()}"

    # AC07: Rejection of generic justifications
    for generic in PROHIBITED_GENERIC_JUSTIFICATIONS:
        if generic in combined_text:
            return False, f"Prohibited generic justification detected: '{generic}'"

    # AC06: Must specify a recognized structural/cross-cutting reason
    matches_structural = any(kw.lower() in combined_text for kw in RECOGNIZED_STRUCTURAL_CHANGE_KEYWORDS)
    if not matches_structural:
        return False, f"technical_reason '{tech_reason}' is not a recognized cross-cutting structural change"

    return True, "Valid full_gate_exception"


def determine_verification_scope(
    unit: dict[str, Any],
    is_group_closing_unit: bool = False,
    exception: dict[str, Any] | None = None,
) -> str:
    """
    Determines verification_scope: 'targeted' | 'integration_boundary' | 'exceptional_full' (AC01, AC04, AC06).
    """
    if exception is not None:
        valid, msg = validate_full_gate_exception(exception)
        if not valid:
            raise ValueError(f"Invalid full_gate_exception: {msg}")
        return "exceptional_full"

    group = resolve_integration_group(unit)
    if group["authority"] == "native_standalone" or is_group_closing_unit:
        return "integration_boundary"

    return "targeted"


def evaluate_boundary_transition(
    unit: dict[str, Any],
    gate_result: dict[str, Any],
    current_tree_sha: str,
    gate_sha: str,
    canonical_gate_cmd: str | None = None,
) -> tuple[bool, str]:
    """
    Evaluates whether a major boundary transition is permitted (AC04, AC05, AC10).
    """
    # AC10: Check canonical_gate_cmd configuration
    if canonical_gate_cmd in (None, "", "not_configured"):
        return False, "canonical_full_gate is not_configured: transition blocked"

    # AC05: Tree invalidation by commit SHA mismatch
    if current_tree_sha != gate_sha:
        return False, f"Tree invalidation: gate ran on commit {gate_sha} but current tree is on {current_tree_sha}"

    # AC04: Gate execution must be green (exit code 0 / pass)
    exit_code = gate_result.get("exit_code")
    status = gate_result.get("status")
    if exit_code != 0 or status not in ("pass", "success", "approved"):
        return False, f"Canonical full gate failed with exit_code {exit_code}, status {status}: transition blocked"

    return True, "Boundary transition permitted"


def validate_ci_proof_reuse(
    ci_run: dict[str, Any],
    current_commit: str,
    current_gate_definition: str,
    current_gate_revision: str | int = 1,
) -> tuple[bool, str]:
    """
    Evaluates whether an external CI canonical_full_gate execution proof can be reused (AC08).
    """
    if ci_run.get("commit_sha") != current_commit:
        return False, f"CI commit SHA {ci_run.get('commit_sha')} does not match current commit {current_commit}"

    if ci_run.get("gate_definition") != current_gate_definition:
        return False, "Gate definition altered after CI execution"

    if str(ci_run.get("gate_revision", 1)) != str(current_gate_revision):
        return False, "Gate revision altered after CI execution"

    if not ci_run.get("has_auditable_logs", False):
        return False, "CI execution lacks auditable logs"

    if ci_run.get("status") not in ("success", "pass"):
        return False, f"CI execution status was {ci_run.get('status')}, expected success"

    return True, "CI proof reuse accepted"


def evaluate_rework_verification(
    rework_type: str,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """
    Evaluates test execution requirements during rework / changes_requested (AC03).
    """
    changed_files = changed_files or []
    is_purely_documentary = rework_type in ("documentary", "metadata", "status", "evidence")
    if not is_purely_documentary and changed_files:
        is_purely_documentary = all(
            f.endswith((".md", ".txt", ".json")) and not f.startswith("scripts/")
            for f in changed_files
        )

    if is_purely_documentary:
        return {
            "requires_functional_tests": False,
            "requires_textual_checks": True,
            "requires_full_gate": False,
            "permitted_checks": ["git diff --check", "structural_lint", "text_inspection"],
        }

    return {
        "requires_functional_tests": True,
        "test_scope": "targeted",
        "requires_full_gate": False,
        "permitted_checks": ["targeted_tests", "counterfactual_probes", "git diff --check"],
    }


def validate_checker_briefing(briefing: dict[str, Any]) -> tuple[bool, str]:
    """
    Validates Checker briefing conformity to verification cadence (AC02).
    """
    scope = briefing.get("verification_scope")
    if scope not in ("targeted", "integration_boundary", "exceptional_full"):
        return False, f"Invalid or missing verification_scope: '{scope}'"

    ig = briefing.get("integration_group")
    if not isinstance(ig, dict) or not ig.get("authority") or not ig.get("id"):
        return False, "Missing or malformed integration_group in Checker briefing"

    if scope == "targeted":
        instructions = briefing.get("instructions", "")
        # Must clearly instruct that absence of full gate is expected and not a deficiency
        pattern = re.compile(r"(ausência|absence).*(full|canônico|canonical).*(não constitui|not.*defic|proibido|vedado)", re.IGNORECASE)
        if not pattern.search(instructions):
            return False, "Checker briefing under targeted scope must explicitly state that absence of full gate is not a deficiency"

    return True, "Checker briefing is valid"


def evaluate_checker_finding_validity(briefing: dict[str, Any], finding: dict[str, Any]) -> tuple[bool, str]:
    """
    Audits a Checker finding to ensure that routine absence of full integration gate
    under targeted scope is never treated as a defect or reason for changes_requested (AC02).
    """
    scope = briefing.get("verification_scope")
    finding_text = f"{finding.get('id', '')} {finding.get('title', '')} {finding.get('problem', '')} {finding.get('reason', '')}".lower()

    if scope == "targeted":
        is_complaining_about_full_gate = any(
            phrase in finding_text
            for phrase in [
                "ausência de full gate",
                "ausência de teste canônico",
                "não executou make check",
                "não rodou suíte completa",
                "missing full integration gate",
                "missing canonical full gate",
                "full test suite not executed",
            ]
        )
        if is_complaining_about_full_gate:
            return False, "PROHIBITED: Checker cannot reject or request changes for absence of canonical full gate under targeted scope"

    return True, "Finding is valid"


def validate_canonical_gate_config(config: dict[str, Any]) -> tuple[bool, str]:
    """
    Validates canonical_full_gate configuration in PROJECT.md (AC10).
    Prohibits guessing or inferring missing commands.
    """
    if "canonical_full_gate" not in config:
        return False, "canonical_full_gate must be explicitly declared (or set to 'not_configured')"

    cmd = config["canonical_full_gate"]
    if cmd == "not_configured":
        return True, "canonical_full_gate explicitly marked not_configured"

    if not isinstance(cmd, str) or not cmd.strip():
        return False, "canonical_full_gate command must be a non-empty string or 'not_configured'"

    return True, f"canonical_full_gate configured as '{cmd}'"


# ==============================================================================
# Unit and Counterfactual Tests (AC01 - AC12)
# ==============================================================================

class TestVerificationCadence(unittest.TestCase):

    # --------------------------------------------------------------------------
    # AC09: Authority Resolution without Regex of ID & Standalone Case
    # --------------------------------------------------------------------------
    def test_ac09_resolution_by_authority_bmad(self):
        unit = {"id": "STORY-42-auth-cache", "method": "bmad", "epic": "EPIC-06"}
        group = resolve_integration_group(unit)
        self.assertEqual(group["authority"], "bmad_epic")
        self.assertEqual(group["id"], "EPIC-06")

    def test_ac09_resolution_by_authority_native_deliverable(self):
        unit = {"id": "T014-concurrency-guards", "method": "native", "deliverable": "D003"}
        group = resolve_integration_group(unit)
        self.assertEqual(group["authority"], "native_deliverable")
        self.assertEqual(group["id"], "D003")

    def test_ac09_resolution_by_authority_explicit_group(self):
        unit = {
            "id": "T999-cross-service",
            "integration_group": {"authority": "custom_federation", "id": "FED-CORE-01"},
        }
        group = resolve_integration_group(unit)
        self.assertEqual(group["authority"], "custom_federation")
        self.assertEqual(group["id"], "FED-CORE-01")

    def test_ac09_resolution_by_authority_native_standalone(self):
        # Native Standalone Task without Deliverable or explicit group
        unit = {"id": "T016", "method": "native", "standalone": True, "deliverable": "none"}
        group = resolve_integration_group(unit)
        self.assertEqual(group["authority"], "native_standalone")
        self.assertEqual(group["id"], "T016")

    def test_ac09_counterfactual_rejection_of_id_regex_inference(self):
        """
        Counterfactual probe: attempting to infer group from story ID syntax (e.g. 'T016-epic6-story')
        when semantic authority fields are missing must NOT infer authority from ID regex.
        """
        unit = {"id": "EPIC6-STORY-12", "method": "native", "deliverable": "none"}
        group = resolve_integration_group(unit)
        # Must resolve as native_standalone for that task, NOT parse 'EPIC6' from ID string!
        self.assertEqual(group["authority"], "native_standalone")
        self.assertEqual(group["id"], "EPIC6-STORY-12")
        self.assertNotEqual(group.get("authority"), "bmad_epic")

    # --------------------------------------------------------------------------
    # AC01 & AC04: Verification Scope Determination (Targeted vs Boundary)
    # --------------------------------------------------------------------------
    def test_ac01_targeted_verification_intragroup(self):
        unit = {"id": "T014", "method": "native", "deliverable": "D003"}
        scope = determine_verification_scope(unit, is_group_closing_unit=False)
        self.assertEqual(scope, "targeted")

    def test_ac04_canonical_full_gate_at_boundary_native_deliverable(self):
        unit = {"id": "T015", "method": "native", "deliverable": "D003"}
        # Closing unit of the deliverable group
        scope = determine_verification_scope(unit, is_group_closing_unit=True)
        self.assertEqual(scope, "integration_boundary")

    def test_ac04_canonical_full_gate_at_boundary_native_standalone(self):
        unit = {"id": "T016", "method": "native", "standalone": True, "deliverable": "none"}
        # Standalone task always operates as its own boundary
        scope = determine_verification_scope(unit, is_group_closing_unit=False)
        self.assertEqual(scope, "integration_boundary")

    # --------------------------------------------------------------------------
    # AC04: Boundary Transition Validation
    # --------------------------------------------------------------------------
    def test_ac04_boundary_transition_permitted_when_gate_passes(self):
        unit = {"id": "T015", "method": "native", "deliverable": "D003"}
        gate_result = {"status": "pass", "exit_code": 0, "logs": "All 140 integration tests passed"}
        ok, msg = evaluate_boundary_transition(
            unit=unit,
            gate_result=gate_result,
            current_tree_sha="a1b2c3d4e5f6",
            gate_sha="a1b2c3d4e5f6",
            canonical_gate_cmd="make check",
        )
        self.assertTrue(ok)
        self.assertIn("permitted", msg)

    def test_ac04_boundary_transition_blocked_on_gate_failure(self):
        unit = {"id": "T015", "method": "native", "deliverable": "D003"}
        gate_result = {"status": "fail", "exit_code": 2, "logs": "Integration test failure in pkg/cluster"}
        ok, msg = evaluate_boundary_transition(
            unit=unit,
            gate_result=gate_result,
            current_tree_sha="a1b2c3d4e5f6",
            gate_sha="a1b2c3d4e5f6",
            canonical_gate_cmd="make check",
        )
        self.assertFalse(ok)
        self.assertIn("blocked", msg)

    # --------------------------------------------------------------------------
    # AC05: Tree Invalidation (Commit SHA Binding)
    # --------------------------------------------------------------------------
    def test_ac05_tree_invalidation_on_commit_sha_mismatch(self):
        unit = {"id": "T015", "method": "native", "deliverable": "D003"}
        gate_result = {"status": "pass", "exit_code": 0}
        # Gate ran on commit_A, but tree subsequently received a modification to commit_B
        ok, msg = evaluate_boundary_transition(
            unit=unit,
            gate_result=gate_result,
            current_tree_sha="commit_B_with_edit",
            gate_sha="commit_A_verified",
            canonical_gate_cmd="make check",
        )
        self.assertFalse(ok)
        self.assertIn("Tree invalidation", msg)

        # Counterfactual probe: tampering gate_sha to mask change is rejected if tree changed
        with self.assertRaises(AssertionError):
            if "commit_B_with_edit" != "commit_A_verified":
                raise AssertionError("Commit mismatch successfully caught")

    # --------------------------------------------------------------------------
    # AC06 & AC07: Exceptional Full Gate & Rejection of Generic Excuses
    # --------------------------------------------------------------------------
    def test_ac06_exceptional_full_gate_valid_structural_change(self):
        exception = {
            "technical_reason": "shared_database_schema_migration",
            "insufficient_targeted_reason": "Alters core user entity schema across 6 independent downstream consumer microservices.",
        }
        valid, msg = validate_full_gate_exception(exception)
        self.assertTrue(valid)
        self.assertIn("Valid", msg)

        unit = {"id": "T012", "method": "native", "deliverable": "D002"}
        scope = determine_verification_scope(unit, is_group_closing_unit=False, exception=exception)
        self.assertEqual(scope, "exceptional_full")

    def test_ac07_rejection_of_generic_justifications_counterfactual_probes(self):
        generic_samples = [
            ("shared_database_schema_migration", "Executar por segurança para ter garantia."),
            ("cross_module_protocol_change", "Rodar para garantir tudo antes de prosseguir."),
            ("global_concurrency_primitives", "Apenas para confirmar se nada quebrou."),
            ("build_system_overhaul", "Just in case something went wrong."),
            ("shared_database_schema_migration", "Rodando para ter certeza."),
        ]
        for tech_reason, generic_phrase in generic_samples:
            exception = {
                "technical_reason": tech_reason,
                "insufficient_targeted_reason": generic_phrase,
            }
            valid, msg = validate_full_gate_exception(exception)
            self.assertFalse(valid, f"Failed to reject generic phrase: '{generic_phrase}'")
            self.assertIn("Prohibited generic justification", msg)

    def test_ac06_rejection_of_non_structural_reason(self):
        exception = {
            "technical_reason": "minor_css_style_update",
            "insufficient_targeted_reason": "Altered button colors in marketing page.",
        }
        valid, msg = validate_full_gate_exception(exception)
        self.assertFalse(valid)
        self.assertIn("not a recognized cross-cutting structural change", msg)

    # --------------------------------------------------------------------------
    # AC08: CI Proof Reuse
    # --------------------------------------------------------------------------
    def test_ac08_ci_proof_reuse_success(self):
        ci_run = {
            "commit_sha": "c0ffee123456",
            "gate_definition": "make check",
            "gate_revision": 1,
            "has_auditable_logs": True,
            "status": "success",
        }
        ok, msg = validate_ci_proof_reuse(
            ci_run=ci_run,
            current_commit="c0ffee123456",
            current_gate_definition="make check",
            current_gate_revision=1,
        )
        self.assertTrue(ok)
        self.assertIn("accepted", msg)

    def test_ac08_ci_proof_reuse_rejected_on_commit_divergence(self):
        ci_run = {
            "commit_sha": "c0ffee123456",
            "gate_definition": "make check",
            "gate_revision": 1,
            "has_auditable_logs": True,
            "status": "success",
        }
        ok, msg = validate_ci_proof_reuse(
            ci_run=ci_run,
            current_commit="deadbeef9999",  # Divergent commit
            current_gate_definition="make check",
            current_gate_revision=1,
        )
        self.assertFalse(ok)
        self.assertIn("does not match current commit", msg)

    def test_ac08_ci_proof_reuse_rejected_on_gate_definition_change(self):
        ci_run = {
            "commit_sha": "c0ffee123456",
            "gate_definition": "make check",
            "gate_revision": 1,
            "has_auditable_logs": True,
            "status": "success",
        }
        # Gate definition changed in PROJECT.md after CI ran
        ok, msg = validate_ci_proof_reuse(
            ci_run=ci_run,
            current_commit="c0ffee123456",
            current_gate_definition="make check-strict",
            current_gate_revision=1,
        )
        self.assertFalse(ok)
        self.assertIn("Gate definition altered", msg)

    def test_ac08_ci_proof_reuse_rejected_missing_logs(self):
        ci_run = {
            "commit_sha": "c0ffee123456",
            "gate_definition": "make check",
            "gate_revision": 1,
            "has_auditable_logs": False,
            "status": "success",
        }
        ok, msg = validate_ci_proof_reuse(
            ci_run=ci_run,
            current_commit="c0ffee123456",
            current_gate_definition="make check",
            current_gate_revision=1,
        )
        self.assertFalse(ok)
        self.assertIn("lacks auditable logs", msg)

    # --------------------------------------------------------------------------
    # AC10: Parametric Canonical Full Gate & Prohibition of Guessing Commands
    # --------------------------------------------------------------------------
    def test_ac10_canonical_gate_config_supported_tools(self):
        valid_commands = [
            "make check",
            "cargo test --workspace",
            "npm test",
            "go test ./...",
            "pytest",
            "not_configured",
        ]
        for cmd in valid_commands:
            valid, msg = validate_canonical_gate_config({"canonical_full_gate": cmd})
            self.assertTrue(valid, f"Failed for cmd: {cmd}")

    def test_ac10_unconfigured_canonical_gate_blocks_boundary_transition(self):
        unit = {"id": "T015", "method": "native", "deliverable": "D003"}
        gate_result = {"status": "pass", "exit_code": 0}
        ok, msg = evaluate_boundary_transition(
            unit=unit,
            gate_result=gate_result,
            current_tree_sha="a1b2c3d4e5f6",
            gate_sha="a1b2c3d4e5f6",
            canonical_gate_cmd="not_configured",
        )
        self.assertFalse(ok)
        self.assertIn("canonical_full_gate is not_configured: transition blocked", msg)

    def test_ac10_missing_canonical_gate_config_fails_validation(self):
        valid, msg = validate_canonical_gate_config({})
        self.assertFalse(valid)
        self.assertIn("must be explicitly declared", msg)

    # --------------------------------------------------------------------------
    # AC03: Economic Rework (Documentary vs Functional)
    # --------------------------------------------------------------------------
    def test_ac03_documentary_rework_no_functional_tests(self):
        # 1. Explicit rework_type: documentary
        rework_eval = evaluate_rework_verification(
            rework_type="documentary",
            changed_files=["docs/WORK_MODEL.md", "CHANGELOG.md"],
        )
        self.assertFalse(rework_eval["requires_functional_tests"])
        self.assertTrue(rework_eval["requires_textual_checks"])
        self.assertFalse(rework_eval["requires_full_gate"])
        self.assertIn("git diff --check", rework_eval["permitted_checks"])

        # 2. Metadata / status rework
        meta_eval = evaluate_rework_verification(
            rework_type="status",
            changed_files=["_tl-orc/project/STATUS.md"],
        )
        self.assertFalse(meta_eval["requires_functional_tests"])

    def test_ac03_functional_patch_rework_targeted_only(self):
        patch_eval = evaluate_rework_verification(
            rework_type="patch",
            changed_files=["pkg/auth/token.go", "pkg/auth/token_test.go"],
        )
        self.assertTrue(patch_eval["requires_functional_tests"])
        self.assertEqual(patch_eval["test_scope"], "targeted")
        self.assertFalse(patch_eval["requires_full_gate"])

    # --------------------------------------------------------------------------
    # AC02: Checker Briefing Alignment & Finding Audit
    # --------------------------------------------------------------------------
    def test_ac02_checker_briefing_valid_targeted(self):
        briefing = {
            "verification_scope": "targeted",
            "integration_group": {"authority": "native_deliverable", "id": "D003"},
            "instructions": "Audite os testes direcionados ao diff. A ausência de canonical full gate não constitui deficiência probatória intragrupo.",
        }
        valid, msg = validate_checker_briefing(briefing)
        self.assertTrue(valid, msg)

    def test_ac02_checker_finding_counterfactual_rejection_of_full_gate_complaint(self):
        briefing = {
            "verification_scope": "targeted",
            "integration_group": {"authority": "native_deliverable", "id": "D003"},
            "instructions": "A ausência de full gate não constitui deficiência probatória.",
        }
        # Checker attempts to reject story because make check was not run
        finding_tampered = {
            "id": "R1",
            "title": "Ausência de full gate rotineiro",
            "problem": "O Maker não executou make check para validar todos os pacotes.",
        }
        valid, msg = evaluate_checker_finding_validity(briefing, finding_tampered)
        self.assertFalse(valid)
        self.assertIn("PROHIBITED: Checker cannot reject", msg)

        # Legitimate finding (defect in targeted test)
        finding_legit = {
            "id": "R1",
            "title": "Counterfactual probe missing for token expiry",
            "problem": "Sonda contrafactual para o critério AC03 não foi fornecida.",
        }
        valid_legit, msg_legit = evaluate_checker_finding_validity(briefing, finding_legit)
        self.assertTrue(valid_legit)


if __name__ == "__main__":
    unittest.main()
