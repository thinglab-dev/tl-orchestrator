#!/usr/bin/env python3
"""Bounded, dependency-free validators for optional workflow-quality artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_ARTIFACT_BYTES = 1_048_576
METRIC_FIELDS = ("quality", "rework", "duration_seconds", "input_tokens", "cache_read_tokens", "output_tokens", "cost_observed", "coverage")
COMPARABLE_IDENTITY_FIELDS = ("task_id", "task_revision", "input_digest", "model", "effort")


def bounded_bytes(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("artifact is unavailable")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds size limit")
    return path.read_bytes()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(bounded_bytes(path).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def digest(path: Path) -> str:
    return hashlib.sha256(bounded_bytes(path)).hexdigest()


def referenced_path(base: Path, reference: Any) -> Path:
    if not isinstance(reference, str) or not reference or Path(reference).is_absolute():
        raise ValueError("invalid artifact reference")
    root = base.resolve()
    path = (root / reference).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact reference escapes its root") from exc
    bounded_bytes(path)
    return path


def write_json(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def errors_for_proof(proof: dict[str, Any], base: Path, interface_enabled: bool,
                     code_id: str, fixture_id: str, now: datetime) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "scope", "code_identity", "fixture_identity", "expires_at", "criteria"}
    if set(proof) - {"schema_version", "scope", "code_identity", "fixture_identity", "expires_at", "criteria", "source"}:
        errors.append("unknown proof field")
    if not required.issubset(proof):
        return [*errors, "missing required proof field"]
    if proof["schema_version"] != 1 or not isinstance(proof["scope"], str) or proof["scope"] not in {"offline", "interface"}:
        errors.append("invalid proof schema_version or scope")
    if proof["scope"] == "interface" and not interface_enabled:
        errors.append("interface proof requires --allow-interface")
    for name, expected in (("code_identity", code_id), ("fixture_identity", fixture_id)):
        value = proof.get(name)
        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]:
            errors.append(f"invalid {name}")
        elif value["id"] != expected:
            errors.append(f"stale {name}")
    try:
        expiry = datetime.fromisoformat(str(proof["expires_at"]).replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry < now:
            errors.append("expired proof")
    except ValueError:
        errors.append("invalid expires_at")
    criteria = proof.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return [*errors, "criteria must be a non-empty array"]
    for index, criterion in enumerate(criteria):
        prefix = f"criterion[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{prefix} is not an object")
            continue
        needed = {"id", "required", "applicability", "status", "expected", "observed", "evidence"}
        if not needed.issubset(criterion) or not isinstance(criterion.get("applicability"), str) or criterion["applicability"] not in {"applicable", "not_applicable"}:
            errors.append(f"{prefix} is incomplete")
            continue
        if not isinstance(criterion["required"], bool):
            errors.append(f"{prefix} has invalid required")
        if not isinstance(criterion["status"], str) or criterion["status"] not in {"pass", "fail", "inconclusive"}:
            errors.append(f"{prefix} has invalid status")
        if criterion["required"] is True and (criterion["applicability"] != "applicable" or criterion["status"] != "pass"):
            errors.append(f"{prefix} does not approve")
        evidence = criterion["evidence"]
        if not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str) or not isinstance(evidence.get("sha256"), str):
            errors.append(f"{prefix} evidence is missing")
            continue
        try:
            actual = digest(referenced_path(base, evidence["path"]))
        except (OSError, ValueError):
            errors.append(f"{prefix} evidence is unrecoverable")
            continue
        if actual != evidence["sha256"]:
            errors.append(f"{prefix} evidence is tampered")
    if not any(isinstance(criterion, dict) and criterion.get("required") is True and criterion.get("applicability") == "applicable" and criterion.get("status") == "pass" for criterion in criteria):
        errors.append("no required applicable criterion")
    return errors


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def metric_errors(metrics: Any) -> list[str]:
    if not isinstance(metrics, dict) or not nonempty(metrics.get("quality")) or metrics["quality"] not in {"pass", "fail", "inconclusive"}:
        return ["raw metrics have invalid quality"]
    errors: list[str] = []
    for field in METRIC_FIELDS[1:]:
        value = metrics.get(field)
        if field in metrics and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0):
            errors.append(f"raw metrics have invalid {field}")
    coverage = metrics.get("coverage")
    if isinstance(coverage, (int, float)) and not isinstance(coverage, bool) and math.isfinite(coverage) and coverage > 1:
        errors.append("raw metrics have invalid coverage")
    return errors


def receipt_metrics(receipt_path: Path, expected_sha256: str) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    errors: list[str] = []
    if not sha256(expected_sha256):
        return {}, {}, ["caller must provide receipt SHA-256"]
    try:
        if digest(receipt_path) != expected_sha256:
            return {}, {}, ["trusted receipt digest mismatch"]
        receipt = load_json(receipt_path)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return {}, {}, [f"receipt unavailable: {exc}"]
    allowed = {"schema_version", "producer", "tool", "identity", "runs"}
    tool = receipt.get("tool")
    if set(receipt) != allowed or receipt.get("schema_version") != 1 or receipt.get("producer") != "consumer_executor":
        errors.append("invalid consumer execution receipt")
    if not isinstance(tool, dict) or set(tool) != {"name", "version", "fingerprint"} or not all(nonempty(tool.get(key)) for key in tool):
        errors.append("receipt tool identity is incomplete")
    identity = receipt.get("identity")
    if not isinstance(identity, dict) or set(identity) != set(COMPARABLE_IDENTITY_FIELDS) or not all(nonempty(identity.get(key)) for key in COMPARABLE_IDENTITY_FIELDS) or not sha256(identity.get("input_digest")):
        errors.append("receipt comparable identity is incomplete")
        identity = {}
    runs = receipt.get("runs")
    if not isinstance(runs, list) or not runs:
        return {}, identity, [*errors, "receipt runs missing"]
    result: dict[str, dict[str, Any]] = {}
    for index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != {"id", "raw"} or not nonempty(run.get("id")) or run["id"] in result:
            errors.append(f"receipt run[{index}] is invalid")
            continue
        raw = run["raw"]
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256"} or not nonempty(raw.get("path")) or not sha256(raw.get("sha256")):
            errors.append(f"receipt run[{index}] raw reference is invalid")
            continue
        try:
            raw_path = referenced_path(receipt_path.parent, raw["path"])
            if digest(raw_path) != raw["sha256"]:
                errors.append(f"receipt run[{index}] raw artifact is tampered")
                continue
            metrics = load_json(raw_path).get("metrics")
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            errors.append(f"receipt run[{index}] raw artifact is unrecoverable")
            continue
        metric_problems = metric_errors(metrics)
        errors.extend(f"receipt run[{index}] {error}" for error in metric_problems)
        if not metric_problems:
            result[run["id"]] = metrics
    return result, identity, errors


def evaluation_errors(baseline: dict[str, Any], candidate: dict[str, Any], baseline_metrics: dict[str, dict[str, Any]], candidate_metrics: dict[str, dict[str, Any]], baseline_identity: dict[str, str], candidate_identity: dict[str, str]) -> list[str]:
    errors: list[str] = []
    allowed = {"schema_version", "arm", *COMPARABLE_IDENTITY_FIELDS, "expected_activated_skills", "activated_skills", "repetitions"}
    for label, artifact in (("baseline", baseline), ("candidate", candidate)):
        if set(artifact) - allowed:
            errors.append(f"{label} has unknown field")
        for key in COMPARABLE_IDENTITY_FIELDS:
            if not nonempty(artifact.get(key)):
                errors.append(f"{label} has invalid {key}")
        if not sha256(artifact.get("input_digest")):
            errors.append(f"{label} has invalid input_digest")
        for key in ("expected_activated_skills", "activated_skills"):
            if key in artifact and (not isinstance(artifact[key], list) or not all(nonempty(value) for value in artifact[key])):
                errors.append(f"{label} has invalid {key}")
        receipt_identity = baseline_identity if label == "baseline" else candidate_identity
        for key in COMPARABLE_IDENTITY_FIELDS:
            if artifact.get(key) != receipt_identity.get(key):
                errors.append(f"{label} {key} differs from trusted receipt")
    for key in ("schema_version", *COMPARABLE_IDENTITY_FIELDS):
        if baseline.get(key) != candidate.get(key):
            errors.append(f"non-comparable {key}")
    if baseline.get("schema_version") != 1 or baseline.get("arm") != "baseline" or candidate.get("arm") != "candidate":
        errors.append("invalid evaluation identity")
    base_runs, candidate_runs = baseline.get("repetitions"), candidate.get("repetitions")
    if not isinstance(base_runs, list) or not base_runs:
        return [*errors, "baseline repetitions missing"]
    if not isinstance(candidate_runs, list) or len(candidate_runs) != len(base_runs):
        return [*errors, "candidate repetitions differ"]
    expected = candidate.get("expected_activated_skills", [])
    activated = candidate.get("activated_skills", [])
    if isinstance(expected, list) and isinstance(activated, list) and all(nonempty(value) for value in expected + activated) and sorted(expected) != sorted(activated):
        errors.append("unexpected skill activation")
    seen_pairs: set[str] = set()
    seen_receipts = {"baseline": set(), "candidate": set()}
    allowed_run = {"pair_id", "receipt_id", *METRIC_FIELDS}
    for index, (base_run, candidate_run) in enumerate(zip(base_runs, candidate_runs)):
        for label, run, metrics in (("baseline", base_run, baseline_metrics), ("candidate", candidate_run, candidate_metrics)):
            if not isinstance(run, dict) or set(run) - allowed_run or not nonempty(run.get("pair_id")) or not nonempty(run.get("receipt_id")) or "quality" not in run:
                errors.append(f"{label} repetition[{index}] is invalid")
                continue
            if run["receipt_id"] in seen_receipts[label]:
                errors.append(f"{label} repetition[{index}] reuses receipt_id")
                continue
            seen_receipts[label].add(run["receipt_id"])
            raw = metrics.get(run["receipt_id"])
            if raw is None:
                errors.append(f"{label} repetition[{index}] has no trusted raw artifact")
                continue
            for field in METRIC_FIELDS:
                if (field in run) != (field in raw) or field in run and run[field] != raw[field]:
                    errors.append(f"{label} repetition[{index}] {field} differs from raw artifact")
        if isinstance(base_run, dict) and isinstance(candidate_run, dict):
            pair_id = base_run.get("pair_id")
            if not isinstance(pair_id, str) or pair_id in seen_pairs or pair_id != candidate_run.get("pair_id"):
                errors.append(f"repetition[{index}] is not paired")
            else:
                seen_pairs.add(pair_id)
    return errors


def rate(repetitions: list[dict[str, Any]], field: str, wanted: Any) -> float | None:
    values = [item.get(field) for item in repetitions]
    return None if not values or any(value is None for value in values) else sum(value == wanted for value in values) / len(values)
