#!/usr/bin/env python3
"""
run_advisor.py - Executes the Advisor role (claude sonnet high) for Task T032 Phase A
under Schema v3, capturing structured JSON verdict and validating against advisor-result.schema.json.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / "distribution-manifest.json").is_file():
            return current
        current = current.parent
    raise RuntimeError("Could not find repository root")

REPO_ROOT = find_repo_root(Path(__file__))
SUPPORT_DIR = Path(__file__).resolve().parent
BRIEFING_FILE = SUPPORT_DIR / "advisor-briefing.md"
STDOUT_FILE = SUPPORT_DIR / "advisor-stdout.txt"
STDERR_FILE = SUPPORT_DIR / "advisor-stderr.txt"
VERDICT_FILE = SUPPORT_DIR / "advisor-verdict.json"
SCHEMA_FILE = REPO_ROOT / "schemas" / "advisor-result.schema.json"

if "--validate-only" not in sys.argv:
    briefing_content = BRIEFING_FILE.read_text(encoding="utf-8")
    cmd = [
        "claude",
        "-p", briefing_content,
        "--model", "sonnet",
        "--no-session-persistence",
        "--dangerously-skip-permissions"
    ]
    print(">>> Dispatching Advisor (claude sonnet high)...")
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    STDOUT_FILE.write_text(proc.stdout, encoding="utf-8")
    STDERR_FILE.write_text(proc.stderr, encoding="utf-8")
    print(f">>> Advisor finished with exit code {proc.returncode}")
    if proc.returncode != 0:
        print(f"ERROR: Advisor process returned non-zero code {proc.returncode}", file=sys.stderr)
        print("STDERR:\n", proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)

raw = STDOUT_FILE.read_text(encoding="utf-8").strip()
# Extract JSON block
json_match = re.search(r"(\{[\s\S]*\})", raw)
if not json_match:
    print(f"ERROR: Could not find JSON object in stdout:\n{raw}", file=sys.stderr)
    sys.exit(1)

json_str = json_match.group(1)
try:
    verdict_data = json.loads(json_str)
except Exception as exc:
    print(f"ERROR: Failed to parse JSON: {exc}\nExtracted string:\n{json_str}", file=sys.stderr)
    sys.exit(1)

# Validate against schemas/advisor-result.schema.json
try:
    import jsonschema
    schema_data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=verdict_data, schema=schema_data)
    print(">>> JSON successfully validated against schemas/advisor-result.schema.json!")
except ImportError:
    # Basic fallback checks
    required = ["schema_version", "verdict", "confidence", "findings", "alternatives", "missing_evidence", "debate_required", "reason"]
    for f in required:
        if f not in verdict_data:
            print(f"ERROR: Missing required field '{f}' in advisor result", file=sys.stderr)
            sys.exit(1)
    if verdict_data["verdict"] not in ["proceed", "adjust", "plan", "debate", "stop"]:
        print(f"ERROR: Invalid verdict '{verdict_data['verdict']}'", file=sys.stderr)
        sys.exit(1)
    if verdict_data["verdict"] == "debate" and not verdict_data.get("debate_required"):
        print("ERROR: debate_required must be true when verdict is debate", file=sys.stderr)
        sys.exit(1)
    print(">>> Fallback validation succeeded!")

VERDICT_FILE.write_text(json.dumps(verdict_data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f">>> Validated verdict written to {VERDICT_FILE}")
print(f"Verdict: {verdict_data['verdict'].upper()} (confidence: {verdict_data['confidence']})")
print(f"Reason: {verdict_data['reason']}")
print(f"Findings count: {len(verdict_data['findings'])}")
