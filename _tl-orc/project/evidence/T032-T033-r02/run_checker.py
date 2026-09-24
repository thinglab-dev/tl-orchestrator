#!/usr/bin/env python3
"""Dispatch independent Checker (OpenAI Codex gpt-5.6-terra / high) for T032+T033 r02."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
import jsonschema

WORKSPACE_DIR = Path(__file__).resolve().parents[4]
EVIDENCE_DIR = WORKSPACE_DIR / "_tl-orc" / "project" / "evidence" / "T032-T033-r02"
BRIEFING_FILE = EVIDENCE_DIR / "checker-briefing.md"
LAST_MESSAGE_FILE = EVIDENCE_DIR / "checker-last.txt"
RAW_LOG_FILE = EVIDENCE_DIR / "checker-raw.log"
REVIEW_RESULT_FILE = EVIDENCE_DIR / "review-result.json"
SCHEMA_FILE = WORKSPACE_DIR / "schemas" / "review-result.schema.json"
CODEX_PATH = "/opt/homebrew/bin/codex"


def extract_json(raw_text: str) -> dict:
    """Extract JSON object from text, handling optional markdown code fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, count=1)
        text = re.sub(r"\n?```\s*$", "", text, count=1)
        text = text.strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(text)


def main():
    if not BRIEFING_FILE.is_file():
        sys.exit(f"Error: Briefing file not found: {BRIEFING_FILE}")
    if not SCHEMA_FILE.is_file():
        sys.exit(f"Error: Schema file not found: {SCHEMA_FILE}")
    if not os.path.exists(CODEX_PATH):
        sys.exit(f"Error: Codex CLI not found at {CODEX_PATH}")

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    with open(BRIEFING_FILE, "r", encoding="utf-8") as f:
        briefing_text = f.read()

    cmd = [
        CODEX_PATH,
        "exec",
        "-s",
        "read-only",
        "-m",
        "gpt-5.6-terra",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'approval_policy="never"',
        "--output-last-message",
        str(LAST_MESSAGE_FILE),
        "-",
    ]

    print(f"Executing Codex Checker (r02) in {WORKSPACE_DIR}...")
    print(f"Command: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(WORKSPACE_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = proc.communicate(input=briefing_text)

    with open(RAW_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== STDOUT ===\n")
        f.write(stdout)
        f.write("\n=== STDERR ===\n")
        f.write(stderr)

    print(f"Codex process completed with exit code {proc.returncode}")

    output_text = None
    if LAST_MESSAGE_FILE.is_file():
        with open(LAST_MESSAGE_FILE, "r", encoding="utf-8") as f:
            output_text = f.read().strip()

    if not output_text:
        output_text = stdout.strip()

    if not output_text:
        print(f"STDERR:\n{stderr}", file=sys.stderr)
        sys.exit("Error: No output received from Codex.")

    try:
        result_json = extract_json(output_text)
    except Exception as e:
        print(f"Error parsing JSON from Checker output: {e}", file=sys.stderr)
        print(f"Output was:\n{output_text}", file=sys.stderr)
        sys.exit(1)

    try:
        jsonschema.validate(instance=result_json, schema=schema)
        print("Review result successfully validated against schemas/review-result.schema.json!")
    except jsonschema.ValidationError as ve:
        print(f"Schema validation error: {ve}", file=sys.stderr)
        with open(REVIEW_RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=2, ensure_ascii=False)
        sys.exit(1)

    with open(REVIEW_RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    print(f"Verdict: {result_json.get('verdict')}")
    print(f"Action Items: {len(result_json.get('action_items', []))}")
    print(f"Deferred: {len(result_json.get('deferred', []))}")
    print(f"Rejected: {len(result_json.get('rejected', []))}")
    print(f"Review result written to {REVIEW_RESULT_FILE}")


if __name__ == "__main__":
    main()
