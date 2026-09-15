"""Counterfactual contracts for optional workflow-quality helpers."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], text=True, capture_output=True)

class WorkflowQualityTest(unittest.TestCase):
    def write(self, root: Path, name: str, data: dict) -> Path:
        path = root / name; path.write_text(json.dumps(data), encoding="utf-8"); return path

    def proof(self, root: Path) -> Path:
        evidence = root / "evidence.txt"; evidence.write_text("observed", encoding="utf-8")
        return self.write(root, "proof.json", {"schema_version": 1, "scope": "offline", "code_identity": {"id": "c1"}, "fixture_identity": {"id": "f1"}, "expires_at": "2030-01-01T00:00:00Z", "criteria": [{"id": "works", "required": True, "applicability": "applicable", "status": "pass", "expected": "ok", "observed": "ok", "evidence": {"path": "evidence.txt", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}}]})

    def identity(self) -> dict:
        return {"task_id": "t", "task_revision": "r", "input_digest": "a" * 64, "model": "m", "effort": "medium"}

    def receipt(self, root: Path, arm: str, metrics: list[dict], identity: dict | None = None) -> tuple[Path, str]:
        runs = []
        for index, metric in enumerate(metrics):
            raw = self.write(root, f"{arm}-{index}.raw.json", {"simulated": True, "metrics": metric})
            runs.append({"id": f"{arm}-{index}", "raw": {"path": raw.name, "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}})
        receipt = self.write(root, f"{arm}-receipt.json", {"schema_version": 1, "producer": "consumer_executor", "tool": {"name": "harness", "version": "1", "fingerprint": "f1"}, "identity": identity or self.identity(), "runs": runs})
        return receipt, hashlib.sha256(receipt.read_bytes()).hexdigest()

    def evaluation(self, arm: str, metrics: list[dict]) -> dict:
        return {"schema_version": 1, "arm": arm, **self.identity(), "expected_activated_skills": [], "activated_skills": [], "repetitions": [{"pair_id": f"p{index}", "receipt_id": f"{arm}-{index}", **metric} for index, metric in enumerate(metrics)]}

    def compare(self, root: Path, base: dict, candidate: dict, base_receipt: tuple[Path, str], candidate_receipt: tuple[Path, str], output: Path | None = None) -> subprocess.CompletedProcess[str]:
        args = ["compare_skill_profiles.py", "--baseline", str(self.write(root, "base.json", base)), "--candidate", str(self.write(root, "candidate.json", candidate)), "--baseline-receipt", str(base_receipt[0]), "--candidate-receipt", str(candidate_receipt[0]), "--baseline-receipt-sha256", base_receipt[1], "--candidate-receipt-sha256", candidate_receipt[1]]
        if output: args.extend(("--output", str(output)))
        return run(*args)

    def test_runtime_proof_requires_current_identities_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); proof = self.proof(root)
            self.assertEqual(run("validate_runtime_proof.py", "--proof", str(proof), "--code-id", "c1", "--fixture-id", "f1", "--now", "2029-01-01T00:00:00Z").returncode, 0)
            self.assertNotEqual(run("validate_runtime_proof.py", "--proof", str(proof), "--code-id", "c2", "--fixture-id", "f1", "--now", "2029-01-01T00:00:00Z").returncode, 0)
            self.assertNotEqual(run("validate_runtime_proof.py", "--proof", str(proof), "--fixture-id", "f1").returncode, 0)
            data = json.loads(proof.read_text()); data["criteria"][0]["status"] = "inconclusive"; proof.write_text(json.dumps(data))
            self.assertNotEqual(run("validate_runtime_proof.py", "--proof", str(proof), "--code-id", "c1", "--fixture-id", "f1").returncode, 0)
            for field, value, error in (("required", False, "no required applicable criterion"), ("required", 0, "criterion[0] has invalid required"), ("required", None, "criterion[0] has invalid required"), ("status", "invalid", "criterion[0] has invalid status"), ("required", "missing", "criterion[0] is incomplete")):
                invalid = json.loads(self.proof(root).read_text())
                if value == "missing": invalid["criteria"][0].pop(field)
                else: invalid["criteria"][0][field] = value
                result = run("validate_runtime_proof.py", "--proof", str(self.write(root, f"proof-{field}-{value}.json", invalid)), "--code-id", "c1", "--fixture-id", "f1", "--now", "2029-01-01T00:00:00Z")
                self.assertNotEqual(result.returncode, 0); self.assertIn(error, json.loads(result.stdout)["errors"])
            self.assertIn('"approved": false', run("validate_runtime_proof.py", "--proof", str(root / "missing.json"), "--code-id", "c1", "--fixture-id", "f1").stdout)

    def test_comparison_uses_trusted_raw_metrics_and_unknown_is_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); base_metrics = [{"quality": "pass", "input_tokens": 3, "cache_read_tokens": 2, "output_tokens": 1, "cost_observed": 2}] * 3; candidate_metrics = [{"quality": "pass", "input_tokens": 1, "cache_read_tokens": 1, "output_tokens": 1, "cost_observed": 1}] * 3
            base_receipt, candidate_receipt = self.receipt(root, "baseline", base_metrics), self.receipt(root, "candidate", candidate_metrics)
            base, candidate = self.evaluation("baseline", base_metrics), self.evaluation("candidate", candidate_metrics)
            self.assertEqual(self.compare(root, base, candidate, base_receipt, candidate_receipt).returncode, 0)
            candidate["repetitions"][0]["quality"] = "fail"
            mismatch = self.compare(root, base, candidate, base_receipt, candidate_receipt)
            self.assertNotEqual(mismatch.returncode, 0); self.assertIn("quality differs from raw artifact", " ".join(json.loads(mismatch.stdout)["errors"]))
            worse_metrics = [{"quality": "fail", "cost_observed": 1}, {"quality": "pass", "cost_observed": 1}]
            worse = self.compare(root, self.evaluation("baseline", [{"quality": "pass", "cost_observed": 2}] * 2), self.evaluation("candidate", worse_metrics), self.receipt(root, "baseline", [{"quality": "pass", "cost_observed": 2}] * 2), self.receipt(root, "candidate", worse_metrics))
            worse_report = json.loads(worse.stdout)
            self.assertNotEqual(worse.returncode, 0); self.assertIn("candidate quality is worse", worse_report["errors"]); self.assertEqual(worse_report["economics"], "inconclusive")
            candidate = self.evaluation("candidate", candidate_metrics); candidate["repetitions"][1].pop("quality")
            self.assertNotEqual(self.compare(root, base, candidate, base_receipt, candidate_receipt).returncode, 0)
            candidate = self.evaluation("candidate", candidate_metrics); candidate["model"] = ""
            self.assertNotEqual(self.compare(root, base, candidate, base_receipt, candidate_receipt).returncode, 0)
            unknown = [{"quality": "pass"}]; base_unknown, candidate_unknown = self.receipt(root, "baseline", unknown), self.receipt(root, "candidate", unknown)
            report = self.compare(root, self.evaluation("baseline", unknown), self.evaluation("candidate", unknown), base_unknown, candidate_unknown)
            self.assertEqual(report.returncode, 0); self.assertIn('"input_tokens": "unknown"', report.stdout); self.assertIn('"economics": "inconclusive"', report.stdout)
            inconclusive = [{"quality": "inconclusive", "cost_observed": 1}]
            self.assertNotEqual(self.compare(root, self.evaluation("baseline", inconclusive), self.evaluation("candidate", inconclusive), self.receipt(root, "baseline", inconclusive), self.receipt(root, "candidate", inconclusive)).returncode, 0)
            base_receipt, candidate_receipt = self.receipt(root, "baseline", base_metrics), self.receipt(root, "candidate", candidate_metrics)
            candidate = self.evaluation("candidate", candidate_metrics); candidate["repetitions"][1]["receipt_id"] = "candidate-0"
            duplicate = self.compare(root, self.evaluation("baseline", base_metrics), candidate, base_receipt, candidate_receipt)
            duplicate_report = json.loads(duplicate.stdout)
            self.assertNotEqual(duplicate.returncode, 0); self.assertIn("candidate repetition[1] reuses receipt_id", duplicate_report["errors"])
            self.assertEqual(duplicate_report["tokens"]["candidate"]["input_tokens"], 2)
            failed = [{"quality": "fail", "cost_observed": 2}]
            all_failed = self.compare(root, self.evaluation("baseline", failed), self.evaluation("candidate", [{"quality": "fail", "cost_observed": 1}]), self.receipt(root, "baseline", failed), self.receipt(root, "candidate", [{"quality": "fail", "cost_observed": 1}]))
            all_failed_report = json.loads(all_failed.stdout)
            self.assertNotEqual(all_failed.returncode, 0); self.assertIn("baseline has no successful repetition", all_failed_report["errors"]); self.assertIn("candidate has no successful repetition", all_failed_report["errors"]); self.assertEqual(all_failed_report["economics"], "inconclusive")
            for field, value in (("expected_activated_skills", [{"bad": "type"}]), ("expected_activated_skills", None), ("activated_skills", [{"bad": "type"}]), ("activated_skills", None), ("receipt_id", ["bad"]), ("receipt_id", {"bad": "type"}), ("receipt_id", None)):
                malformed = self.evaluation("candidate", candidate_metrics)
                if field == "receipt_id": malformed["repetitions"][0][field] = value
                else: malformed[field] = value
                result = self.compare(root, self.evaluation("baseline", base_metrics), malformed, base_receipt, candidate_receipt)
                report = json.loads(result.stdout)
                self.assertNotEqual(result.returncode, 0); self.assertFalse(report["comparable"]); self.assertNotIn("Traceback", result.stdout + result.stderr)
            altered_identity = self.evaluation("candidate", candidate_metrics); altered_identity["model"] = "tampered"
            identity_result = self.compare(root, self.evaluation("baseline", base_metrics), altered_identity, base_receipt, candidate_receipt)
            self.assertIn("candidate model differs from trusted receipt", json.loads(identity_result.stdout)["errors"])
            for index, invalid in enumerate(("high", True, float("nan"), float("inf"), 1.1)):
                metrics = [{"quality": "pass", "coverage": invalid}]
                base_invalid, candidate_invalid = self.receipt(root, "baseline", metrics), self.receipt(root, "candidate", metrics)
                output = root / f"coverage-{index}.json"
                result = self.compare(root, self.evaluation("baseline", metrics), self.evaluation("candidate", metrics), base_invalid, candidate_invalid, output)
                report = json.loads(output.read_text())
                self.assertNotEqual(result.returncode, 0); self.assertFalse(report["comparable"])
                self.assertIn("invalid coverage", " ".join(report["errors"])); self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_ambiguity_cache_profile_and_protocol_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); spec = root / "spec.md"; spec.write_text("v1")
            digest = hashlib.sha256(spec.read_bytes()).hexdigest(); technical = {"schema_version": 1, "spec_sha256": digest, "items": [{"id": "T1", "kind": "reversible_technical", "status": "open", "summary": "implementation"}]}
            register = self.write(root, "register.json", technical)
            self.assertEqual(run("validate_ambiguities.py", "--register", str(register), "--spec", str(spec)).returncode, 0)
            divergent = dict(technical, spec_sha256="0" * 64)
            self.assertNotEqual(run("validate_ambiguities.py", "--register", str(self.write(root, "divergent.json", divergent)), "--spec", str(spec)).returncode, 0)
            acceptance = self.write(root, "acceptance.json", {"spec_sha256": digest}); spec.write_text("v2")
            updated_register = self.write(root, "updated-register.json", dict(technical, spec_sha256=hashlib.sha256(spec.read_bytes()).hexdigest()))
            acceptance_result = run("validate_ambiguities.py", "--register", str(updated_register), "--spec", str(spec), "--acceptance", str(acceptance))
            self.assertNotEqual(acceptance_result.returncode, 0)
            self.assertEqual(json.loads(acceptance_result.stdout)["errors"], ["acceptance invalidated by spec decision change"])
            raw = self.write(root, "prior.raw.json", {"result": "pass"}); receipt = self.write(root, "gate-receipt.json", {"producer": "consumer_executor", "status": "pass", "tool": {"name": "python", "version": "3.13", "fingerprint": "x"}, "raw_artifact": {"path": raw.name, "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}}); receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
            proof = {"status": "pass", "applicability": "applicable", "code_id": "c", "definition": "test", "effect": "assert", "environment": "windows", "tool": "python", "tool_version": "3.13", "tool_fingerprint": "x", "fixture_id": "f", "receipt_sha256": receipt_sha, "expires_at": "2030-01-01T00:00:00Z"}
            gate = self.write(root, "gate.json", proof); current = dict(proof)
            self.assertEqual(run("validate_gate_reuse.py", "--proof", str(gate), "--current", str(self.write(root, "current.json", current)), "--receipt", str(receipt), "--receipt-sha256", receipt_sha, "--now", "2029-01-01T00:00:00Z").returncode, 0)
            other_raw = self.write(root, "other.raw.json", {"result": "pass"})
            other_receipt = self.write(root, "other-receipt.json", {"producer": "consumer_executor", "status": "pass", "tool": {"name": "python", "version": "3.13", "fingerprint": "x"}, "raw_artifact": {"path": other_raw.name, "sha256": hashlib.sha256(other_raw.read_bytes()).hexdigest()}})
            other_sha = hashlib.sha256(other_receipt.read_bytes()).hexdigest()
            other_result = run("validate_gate_reuse.py", "--proof", str(gate), "--current", str(self.write(root, "current-other-receipt.json", current)), "--receipt", str(other_receipt), "--receipt-sha256", other_sha, "--now", "2029-01-01T00:00:00Z")
            self.assertNotEqual(other_result.returncode, 0); self.assertIn("identity mismatch: receipt_sha256", json.loads(other_result.stdout)["errors"])
            for field in ("code_id", "fixture_id", "tool_version", "tool_fingerprint"):
                changed = dict(current); changed[field] = f"changed-{field}"
                result = run("validate_gate_reuse.py", "--proof", str(gate), "--current", str(self.write(root, f"current-{field}.json", changed)), "--receipt", str(receipt), "--receipt-sha256", receipt_sha, "--now", "2029-01-01T00:00:00Z")
                self.assertNotEqual(result.returncode, 0); self.assertIn(f"identity mismatch: {field}", json.loads(result.stdout)["errors"])
            expired = dict(proof, expires_at="2030-01-01T00:00:00")
            self.assertNotEqual(run("validate_gate_reuse.py", "--proof", str(self.write(root, "naive.json", expired)), "--current", str(self.write(root, "current.json", current)), "--receipt", str(receipt), "--receipt-sha256", receipt_sha).returncode, 0)
            profile = {"schema_version": 1, "role": "maker", "task_kind": "ui", "conflict_authority": "consumer", "skill_limit": 1, "available_skills": ["ui"], "selected_skills": []}
            self.assertNotEqual(run("preflight_workflow.py", "--profile", str(self.write(root, "profile.json", profile))).returncode, 0)
            quality = {"profile": str(self.write(root, "valid-profile.json", dict(profile, available_skills=[]))), "register": str(updated_register), "spec": str(spec), "acceptance": str(self.write(root, "current-acceptance.json", {"spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest()})), "proof": {"path": str(self.proof(root)), "code_id": "c1", "fixture_id": "f1"}}
            self.assertEqual(run("preflight_workflow.py", "--profile", quality["profile"]).returncode, 0)
            self.assertEqual(run("validate_ambiguities.py", "--register", quality["register"], "--spec", quality["spec"], "--acceptance", quality["acceptance"]).returncode, 0)
            self.assertEqual(run("validate_runtime_proof.py", "--proof", quality["proof"]["path"], "--code-id", quality["proof"]["code_id"], "--fixture-id", quality["proof"]["fixture_id"], "--now", "2029-01-01T00:00:00Z").returncode, 0)
        protocol = (ROOT / "docs" / "EXECUTION_PROTOCOL.md").read_text(encoding="utf-8"); maker = (ROOT / "prompts" / "maker.md").read_text(encoding="utf-8"); checker = (ROOT / "prompts" / "checker-report-only.md").read_text(encoding="utf-8")
        envelope = json.loads(protocol.split("```json\n", 1)[1].split("\n```", 1)[0])["workflow_quality"]
        self.assertEqual(set(envelope), {"profile", "register", "spec", "acceptance", "proof", "gate_reuse"})
        self.assertEqual(set(envelope["proof"]), {"path", "code_id", "fixture_id"})
        self.assertEqual(set(envelope["gate_reuse"]), {"prior_proof", "current_identity", "receipt", "expected_receipt_sha256"})
        self.assertEqual(len(envelope["gate_reuse"]["expected_receipt_sha256"]), 64)
        self.assertIn('preflight_workflow.py --profile "$profile"', protocol); self.assertNotIn('preflight_workflow.py --profile "$profile" --tool "$tool"', protocol); self.assertLess(protocol.index("Quando o envelope ativa `workflow_quality`"), protocol.index("No condutor do consumidor, a cadeia autorizada é:")); self.assertIn("validate_ambiguities.py", protocol); self.assertIn("validate_runtime_proof.py", protocol); self.assertIn("workflow_quality", maker); self.assertIn("workflow_quality", checker)

    def test_browser_import_refuses_missing_evidence_and_preflight_timeout_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); browser = self.write(root, "browser.json", {"source": "reticle", "checks": [{"evidence_path": "missing.log"}]})
            result = run("import_browser_proof.py", "--input", str(browser), "--code-id", "c", "--fixture-id", "f", "--expires-at", "2030-01-01T00:00:00Z", "--output", str(root / "proof.json"))
            self.assertNotEqual(result.returncode, 0); self.assertIn("evidence unavailable", result.stderr)
        self.assertIn('"version": "unknown"', run("preflight_workflow.py", "--tool", "missing=tl-workflow-tool-that-does-not-exist,required").stdout)


if __name__ == "__main__": unittest.main()
