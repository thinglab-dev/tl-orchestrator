#!/usr/bin/env python3
"""Fail-closed verification of offline or opt-in interface runtime proof."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from workflow_quality import errors_for_proof, load_json, write_json

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof", required=True, type=Path)
    parser.add_argument("--code-id", required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--allow-interface", action="store_true")
    parser.add_argument("--now", help="RFC3339 time for deterministic verification")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError("--now requires timezone")
        errors = errors_for_proof(load_json(args.proof), args.proof.parent, args.allow_interface, args.code_id, args.fixture_id, now)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors = [str(exc)]
    write_json({"approved": not errors, "errors": errors, "proof": str(args.proof)}, args.output)
    raise SystemExit(0 if not errors else 1)
if __name__ == "__main__": main()

