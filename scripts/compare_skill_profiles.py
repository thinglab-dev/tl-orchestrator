#!/usr/bin/env python3
"""Compare paired consumer-executor artifacts; this CLI never runs an LLM."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from workflow_quality import evaluation_errors, load_json, rate, receipt_metrics, write_json


def totals(runs: list[dict], field: str):
    values = [run.get(field) for run in runs]
    return "unknown" if not values or any(value is None for value in values) else sum(values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path); parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--baseline-receipt", required=True, type=Path); parser.add_argument("--candidate-receipt", required=True, type=Path)
    parser.add_argument("--baseline-receipt-sha256", required=True); parser.add_argument("--candidate-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path); args = parser.parse_args()
    try:
        baseline, candidate = load_json(args.baseline), load_json(args.candidate)
        base_raw, base_identity, base_receipt_errors = receipt_metrics(args.baseline_receipt, args.baseline_receipt_sha256)
        candidate_raw, candidate_identity, candidate_receipt_errors = receipt_metrics(args.candidate_receipt, args.candidate_receipt_sha256)
        errors = [*base_receipt_errors, *candidate_receipt_errors, *evaluation_errors(baseline, candidate, base_raw, candidate_raw, base_identity, candidate_identity)]
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        write_json({"comparable": False, "errors": [str(exc)], "economics": "inconclusive"}, args.output); raise SystemExit(1)
    def observed(artifact, raw):
        seen = set()
        runs = []
        for run in artifact.get("repetitions", []):
            receipt_id = run.get("receipt_id") if isinstance(run, dict) else None
            if not isinstance(receipt_id, str): continue
            if receipt_id in seen: continue
            seen.add(receipt_id)
            runs.append(raw.get(receipt_id, {}))
        return runs
    base_runs, candidate_runs = observed(baseline, base_raw), observed(candidate, candidate_raw)
    base_quality, candidate_quality = rate(base_runs, "quality", "pass"), rate(candidate_runs, "quality", "pass")
    if any(run.get("quality") in {None, "inconclusive"} for run in base_runs + candidate_runs): errors.append("quality is missing or inconclusive")
    if base_quality is not None and candidate_quality is not None and candidate_quality < base_quality: errors.append("candidate quality is worse")
    if base_quality == 0: errors.append("baseline has no successful repetition")
    if candidate_quality == 0: errors.append("candidate has no successful repetition")
    observed_cost = bool(base_runs and candidate_runs) and all("cost_observed" in run for run in base_runs + candidate_runs)
    conclusion = "inconclusive"
    if not errors and observed_cost and base_quality is not None and candidate_quality is not None and base_quality > 0 and candidate_quality > 0 and candidate_quality >= base_quality:
        conclusion = "candidate_lower_observed_cost" if totals(candidate_runs, "cost_observed") < totals(base_runs, "cost_observed") else "no_observed_cost_reduction"
    report = {"comparable": not errors, "errors": errors, "quality": {"baseline_pass_rate": base_quality, "candidate_pass_rate": candidate_quality}, "coverage": "unknown" if not base_runs or not candidate_runs or any("coverage" not in run for run in base_runs + candidate_runs) else "reported", "rework": {"baseline_total": totals(base_runs, "rework"), "candidate_total": totals(candidate_runs, "rework")}, "duration_seconds": {"baseline_total": totals(base_runs, "duration_seconds"), "candidate_total": totals(candidate_runs, "duration_seconds")}, "economics": conclusion, "tokens": {arm: {field: totals(runs, field) for field in ("input_tokens", "cache_read_tokens", "output_tokens")} for arm, runs in (("baseline", base_runs), ("candidate", candidate_runs))}}
    write_json(report, args.output); raise SystemExit(0 if not errors else 1)


if __name__ == "__main__": main()
