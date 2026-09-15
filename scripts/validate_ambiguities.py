#!/usr/bin/env python3
"""Validate a spec-linked ambiguity register without reopening ratified decisions."""
from __future__ import annotations
import argparse
from pathlib import Path
from workflow_quality import digest, load_json, write_json

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); errors = []
    try: register = load_json(args.register); spec_digest = digest(args.spec)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        write_json({"approved": False, "errors": [str(exc)]}, args.output); raise SystemExit(1)
    if register.get("schema_version") != 1 or register.get("spec_sha256") != spec_digest: errors.append("register is not linked to this spec digest")
    items = register.get("items")
    if not isinstance(items, list): errors.append("register items must be an array"); items = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in {"decision_required", "reversible_technical", "verifiable_fact", "already_decided"}: errors.append("invalid ambiguity item"); continue
        if item.get("kind") == "decision_required" and item.get("status") != "resolved": errors.append(f"material decision pending: {item.get('id', '?')}")
    if args.acceptance:
        try: acceptance = load_json(args.acceptance)
        except (OSError, UnicodeDecodeError, ValueError) as exc: errors.append(f"acceptance unavailable: {exc}")
        else:
            if acceptance.get("spec_sha256") != spec_digest: errors.append("acceptance invalidated by spec decision change")
    write_json({"approved": not errors, "errors": errors}, args.output); raise SystemExit(0 if not errors else 1)
if __name__ == "__main__": main()

