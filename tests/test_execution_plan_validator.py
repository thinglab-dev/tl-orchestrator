#!/usr/bin/env python3
"""F) Execution Plan Validator: closed registry and temporal validation (T033), counterfactual 27."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from story_authority_support import FIXTURES, REPO_ROOT, SCRIPTS, load_fixture, plan_validator

validate = plan_validator.validate_execution_plan
CLI = SCRIPTS / "validate_execution_plan.py"


def violations(result: dict) -> set[str]:
    return {error["violation"] for error in result["errors"]}


class ExecutionPlanValidatorTest(unittest.TestCase):

    def plan(self, **overrides) -> dict:
        plan = copy.deepcopy(load_fixture("execution-plan.json"))
        plan.update(overrides)
        return plan

    def test_execution_plan_validator_rejects_temporal_phase_mismatch(self) -> None:
        """27. An assertion evaluated in a phase where its answer is not decidable is refused."""
        for phase, assertion in (
            ("pre_execution", "checker_approved"),
            ("pre_execution", "merge_commit_exists"),
            ("post_maker_pre_review", "checker_approved"),
            ("post_checker_pre_merge", "origin_synced"),
            ("post_terminal", "main_not_merged"),
            ("post_terminal", "functional_checkpoint_matches"),
        ):
            plan = self.plan()
            registry = plan_validator.ASSERTION_REGISTRY[assertion]
            parameters = {
                "unit": "connector:2-10", "reviewed_commit": "1" * 40, "commit": "2" * 40,
                "tree": "3" * 40, "branch": "main", "remote": "origin", "gate_id": "unit-tests",
                "work_ref": "connector:2-10", "sha256": "a" * 64, "policy_id": "p1", "minimum_remaining": 1,
            }
            plan["gates"] = [{
                "gate_id": "g-under-test", "lifecycle_phase": phase, "model_calls": 0,
                "assertions": [{"assertion_id": assertion,
                                "parameters": {k: parameters[k] for k in registry["required"]}}],
            }]
            result = validate(plan)
            self.assertFalse(result["approved"], f"{assertion} in {phase}")
            self.assertIn("assertion_phase_mismatch", violations(result))
            mismatch = next(e for e in result["errors"] if e["violation"] == "assertion_phase_mismatch")
            self.assertEqual(mismatch["assertion_id"], assertion)
            self.assertEqual(mismatch["lifecycle_phase"], phase)
            self.assertEqual(mismatch["allowed_phases"], list(registry["phases"]))

    def test_unknown_assertion_fails_closed(self) -> None:
        plan = self.plan()
        plan["gates"][0]["assertions"].append({"assertion_id": "looks_fine_to_me", "parameters": {}})
        result = validate(plan)
        self.assertFalse(result["approved"])
        self.assertIn("unknown_assertion", violations(result))

    def test_free_form_assertion_strings_are_structurally_impossible(self) -> None:
        """A plan cannot smuggle prose past the registry: the schema admits no such shape."""
        plan = self.plan()
        plan["gates"][0]["assertions"] = ["main is green and the checker said ok"]
        self.assertIn("schema_invalid", violations(validate(plan)))

        plan = self.plan()
        plan["gates"][0]["assertions"] = [{"assertion_id": "checker_approved", "expression": "1 == 1"}]
        self.assertIn("schema_invalid", violations(validate(plan)))

        plan = self.plan()
        plan["gates"][0]["assertions"] = [{"assertion_id": "Checker Approved!", "parameters": {}}]
        self.assertIn("schema_invalid", violations(validate(plan)))

    def test_assertion_parameters_are_typed_and_closed(self) -> None:
        plan = self.plan()
        gate = next(g for g in plan["gates"] if g["gate_id"] == "g-pre-merge")
        assertion = next(a for a in gate["assertions"] if a["assertion_id"] == "checker_approved")
        assertion["parameters"]["reviewed_commit"] = "not-a-sha"
        self.assertIn("assertion_parameter_invalid", violations(validate(plan)))

        plan = self.plan()
        gate = next(g for g in plan["gates"] if g["gate_id"] == "g-pre-merge")
        assertion = next(a for a in gate["assertions"] if a["assertion_id"] == "checker_approved")
        assertion["parameters"]["force"] = True
        self.assertIn("assertion_parameter_unknown", violations(validate(plan)))

        plan = self.plan()
        gate = next(g for g in plan["gates"] if g["gate_id"] == "g-pre-merge")
        assertion = next(a for a in gate["assertions"] if a["assertion_id"] == "checker_approved")
        assertion["parameters"].pop("unit")
        self.assertIn("assertion_parameter_missing", violations(validate(plan)))

    def test_unknown_lifecycle_phase_fails_closed(self) -> None:
        plan = self.plan()
        plan["gates"][0]["lifecycle_phase"] = "whenever_convenient"
        self.assertIn("schema_invalid", violations(validate(plan)))
        self.assertEqual(
            list(plan_validator.LIFECYCLE_PHASES),
            ["pre_execution", "post_maker_pre_review", "post_checker_pre_merge", "post_merge_pre_close",
             "post_terminal"])

    def test_gate_call_constraints_are_satisfiable_under_budget(self) -> None:
        plan = self.plan()
        self.assertEqual(plan_validator.gate_call_constraints_are_satisfiable_under_budget(plan), [])

        # Straight line fits, the retry path does not: the plan is refused.
        tight = self.plan()
        tight["budget"]["max_model_calls"] = 5
        findings = plan_validator.gate_call_constraints_are_satisfiable_under_budget(tight)
        self.assertEqual([f["violation"] for f in findings], ["gate_call_constraints_unsatisfiable"])
        self.assertEqual(findings[0]["scenario"], "retry")
        self.assertEqual(findings[0]["required_calls"], 8)
        self.assertFalse(validate(tight)["approved"])

        # Gates that themselves cost cognitive calls are counted: 2 + 3x2 + 3 = 11 > 8 on retry,
        # while the straight line still fits at 2 + 1x2 + 3 = 7.
        costly = self.plan()
        costly["budget"]["max_model_calls"] = 8
        costly["gates"][0]["model_calls"] = 3
        self.assertEqual(
            {f["scenario"] for f in plan_validator.gate_call_constraints_are_satisfiable_under_budget(costly)},
            {"retry"})

    def test_missing_retry_scenario_is_refused(self) -> None:
        plan = self.plan()
        plan["scenarios"] = [{"name": "straight_line", "rework_rounds": 0},
                             {"name": "optimistic", "rework_rounds": 0}]
        result = validate(plan)
        self.assertIn("missing_budget_scenario", violations(result))
        self.assertIn("retry", {e.get("scenario") for e in result["errors"]})

    def test_protected_paths_are_verified_against_a_real_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl-plan-paths-") as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "ARCH.md").write_bytes((FIXTURES / "docs-arch.md").read_bytes())
            plan = self.plan()
            result = validate(plan, repo_root=root, verify_paths=True)
            self.assertTrue(result["approved"], result["errors"])

            (root / "docs" / "ARCH.md").write_text("tampered\n", encoding="utf-8")
            result = validate(plan, repo_root=root, verify_paths=True)
            self.assertIn("protected_file_hash_mismatch", violations(result))

        plan = self.plan()
        self.assertIn("protected_paths_unverifiable", violations(validate(plan, verify_paths=True)))

    def test_parent_protected_paths_must_be_inherited(self) -> None:
        plan = self.plan()
        # The plan protects only docs/ARCH.md, so a parent protecting all of docs/ is narrowed.
        narrowing = [{"pattern": "docs", "policy": "read_only"}]
        self.assertIn("protected_path_coverage_reduced",
                      violations(validate(plan, parent_protected_paths=narrowing)))
        dropped = [{"pattern": "secrets", "policy": "read_only"}]
        self.assertIn("protected_path_removed", violations(validate(plan, parent_protected_paths=dropped)))
        self.assertTrue(validate(plan, parent_protected_paths=plan["protected_paths"])["approved"])


class SchemaSubsetValidatorTest(unittest.TestCase):
    """The validator must refuse a schema it cannot fully enforce, never quietly ignore it."""

    def test_unsupported_keyword_is_refused_rather_than_ignored(self) -> None:
        schema = {"type": "object", "unevaluatedProperties": False}
        with self.assertRaises(plan_validator.SchemaError) as raised:
            plan_validator.validate_json_schema({}, schema, schema)
        self.assertIn("unsupported schema keyword", str(raised.exception))
        ok, errors = plan_validator.validate_against_schema_file({}, FIXTURES / "does-not-exist.json")
        self.assertFalse(ok)
        self.assertIn("schema unavailable", errors[0])

    def test_conditional_and_combinator_keywords_are_really_enforced(self) -> None:
        schema = {
            "type": "object",
            "properties": {"kind": {"enum": ["a", "b"]}, "value": {"type": "integer", "minimum": 1}},
            "required": ["kind"],
            "allOf": [{"if": {"properties": {"kind": {"const": "a"}}, "required": ["kind"]},
                       "then": {"required": ["value"]}}],
        }
        self.assertEqual(plan_validator.validate_json_schema({"kind": "a", "value": 2}, schema, schema), [])
        self.assertTrue(plan_validator.validate_json_schema({"kind": "a"}, schema, schema))
        self.assertEqual(plan_validator.validate_json_schema({"kind": "b"}, schema, schema), [])

        array = {"type": "array", "items": {"type": "integer"}, "uniqueItems": True, "maxItems": 3}
        self.assertEqual(plan_validator.validate_json_schema([1, 2, 3], array, array), [])
        self.assertTrue(plan_validator.validate_json_schema([1, 1], array, array))
        self.assertTrue(plan_validator.validate_json_schema([1, 2, 3, 4], array, array))

        # JSON equality: true is not 1, so an integer enum never matches a boolean.
        boolean = {"enum": [1, 2]}
        self.assertTrue(plan_validator.validate_json_schema(True, boolean, boolean))

    # Keywords whose value is a map from arbitrary names to schemas, not a schema itself.
    NAME_MAPS = ("properties", "$defs", "patternProperties", "dependentRequired")
    # Keywords whose value is a list of schemas.
    SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
    # Keywords whose value is a single schema.
    SCHEMA_VALUES = ("items", "contains", "not", "if", "then", "else", "additionalProperties", "propertyNames")

    def test_every_repository_schema_is_fully_enforceable_by_this_validator(self) -> None:
        checked = 0
        for path in sorted((REPO_ROOT / "schemas").glob("*.schema.json")):
            self.walk(json.loads(path.read_text(encoding="utf-8")), path.name)
            checked += 1
        self.assertGreaterEqual(checked, 16)

    def walk(self, node, name: str, pointer: str = "$") -> None:
        """Walk only the positions that are schemas, so property names are never read as keywords."""
        if not isinstance(node, dict):
            return
        unsupported = sorted(set(node) - plan_validator.SUPPORTED_KEYWORDS)
        if unsupported:
            self.fail(f"{name}{pointer} uses keyword(s) {unsupported} the stdlib validator does not enforce")
        for keyword in self.NAME_MAPS:
            for key, value in (node.get(keyword) or {}).items():
                self.walk(value, name, f"{pointer}.{keyword}.{key}")
        for keyword in self.SCHEMA_LISTS:
            for index, value in enumerate(node.get(keyword) or []):
                self.walk(value, name, f"{pointer}.{keyword}[{index}]")
        for keyword in self.SCHEMA_VALUES:
            if keyword in node:
                self.walk(node[keyword], name, f"{pointer}.{keyword}")

    def test_canonical_json_refuses_floats(self) -> None:
        with self.assertRaises(ValueError):
            plan_validator.canonical_json({"cost": 1.5})
        self.assertEqual(plan_validator.canonical_json({"b": 1, "a": [2, 3]}), '{"a":[2,3],"b":1}')


class ExecutionPlanCliTest(unittest.TestCase):

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, check=False)

    def test_cli_approves_the_fixture_plan_and_refuses_a_phase_mismatch(self) -> None:
        ok = self.run_cli("--plan", str(FIXTURES / "execution-plan.json"))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["approved"])

        plan = copy.deepcopy(load_fixture("execution-plan.json"))
        plan["gates"][0]["assertions"].append({"assertion_id": "checker_approved",
                                               "parameters": {"unit": "u", "reviewed_commit": "1" * 40}})
        with tempfile.TemporaryDirectory(prefix="tl-plan-cli-") as tmp:
            target = Path(tmp) / "plan.json"
            target.write_text(json.dumps(plan), encoding="utf-8")
            bad = self.run_cli("--plan", str(target))
            self.assertEqual(bad.returncode, 1)
            self.assertIn("assertion_phase_mismatch", bad.stdout)

            missing = self.run_cli("--plan", str(Path(tmp) / "absent.json"))
            self.assertEqual(missing.returncode, 1)
            self.assertIn("plan_unreadable", missing.stdout)

    def test_cli_prints_the_closed_registry(self) -> None:
        printed = self.run_cli("--print-registry")
        self.assertEqual(printed.returncode, 0, printed.stderr)
        registry = json.loads(printed.stdout)
        self.assertEqual(registry["lifecycle_phases"], list(plan_validator.LIFECYCLE_PHASES))
        self.assertEqual(sorted(registry["assertions"]), sorted(plan_validator.ASSERTION_REGISTRY))
        self.assertEqual(registry["assertions"]["origin_synced"]["phases"], ["post_terminal"])
        self.assertEqual(registry["assertions"]["checker_approved"]["phases"], ["post_checker_pre_merge"])


if __name__ == "__main__":
    unittest.main()
