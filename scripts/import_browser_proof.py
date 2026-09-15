#!/usr/bin/env python3
"""Adapt a small Reticle/Playwright-style JSON result; no browser SDK is imported."""
from __future__ import annotations
import argparse
from pathlib import Path
from workflow_quality import digest, load_json, referenced_path, write_json

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--code-id", required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try: source = load_json(args.input)
    except (OSError, UnicodeDecodeError, ValueError) as exc: raise SystemExit(f"input unavailable: {exc}")
    checks = source.get("checks", source.get("assertions"))
    if source.get("source") not in {"reticle", "playwright", "browser"} or not isinstance(checks, list) or not checks:
        raise SystemExit("input must name reticle, playwright, or browser and include checks")
    criteria = []
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("evidence_path"), str):
            raise SystemExit("each check must include evidence_path")
        evidence_path = check["evidence_path"]
        try: evidence = referenced_path(args.input.parent, evidence_path)
        except (OSError, ValueError) as exc: raise SystemExit(f"evidence unavailable: {exc}")
        criteria.append({"id": check.get("id", evidence_path), "required": check.get("required", True), "applicability": check.get("applicability", "applicable"), "status": check.get("status", "inconclusive"), "expected": check.get("expected"), "observed": check.get("observed"), "evidence": {"path": evidence_path, "sha256": digest(evidence)}})
    write_json({"schema_version": 1, "scope": "interface", "source": source["source"], "code_identity": {"id": args.code_id}, "fixture_identity": {"id": args.fixture_id}, "expires_at": args.expires_at, "criteria": criteria}, args.output)
if __name__ == "__main__": main()

