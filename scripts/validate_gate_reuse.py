#!/usr/bin/env python3
"""Allow reuse only for a trusted consumer-executor receipt with full identity."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from workflow_quality import digest, load_json, referenced_path, write_json

FIELDS = ("code_id", "definition", "effect", "environment", "tool", "tool_version", "tool_fingerprint", "fixture_id")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof", required=True, type=Path); parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path); parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--now"); parser.add_argument("--output", type=Path); args = parser.parse_args()
    errors = []
    try:
        proof, current, receipt = load_json(args.proof), load_json(args.current), load_json(args.receipt)
        if digest(args.receipt) != args.receipt_sha256: errors.append("trusted receipt digest mismatch")
        if proof.get("status") != "pass" or proof.get("applicability") != "applicable": errors.append("prior proof was not approved and applicable")
        for field in FIELDS:
            if not proof.get(field) or proof.get(field) != current.get(field): errors.append(f"identity mismatch: {field}")
        if not proof.get("receipt_sha256") or proof.get("receipt_sha256") != current.get("receipt_sha256") or proof.get("receipt_sha256") != args.receipt_sha256:
            errors.append("identity mismatch: receipt_sha256")
        tool = receipt.get("tool")
        if receipt.get("producer") != "consumer_executor" or receipt.get("status") != "pass" or not isinstance(tool, dict) or {"name", "version", "fingerprint"} != set(tool): errors.append("invalid consumer execution receipt")
        elif tool["name"] != current.get("tool") or tool["version"] != current.get("tool_version") or tool["fingerprint"] != current.get("tool_fingerprint"): errors.append("receipt tool identity mismatch")
        raw = receipt.get("raw_artifact")
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256"}: errors.append("receipt raw artifact missing")
        else:
            raw_path = referenced_path(args.receipt.parent, raw["path"])
            if digest(raw_path) != raw["sha256"]: errors.append("receipt raw artifact is tampered")
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(str(proof["expires_at"]).replace("Z", "+00:00"))
        if now.tzinfo is None or expiry.tzinfo is None: errors.append("proof expiry requires timezone")
        elif expiry < now: errors.append("prior proof expired")
    except (KeyError, OSError, UnicodeDecodeError, ValueError) as exc: errors.append(f"invalid gate reuse input: {exc}")
    write_json({"reusable": not errors, "errors": errors}, args.output); raise SystemExit(0 if not errors else 1)


if __name__ == "__main__": main()
