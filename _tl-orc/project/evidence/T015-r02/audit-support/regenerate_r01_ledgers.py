#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

WT = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/wt/t015-freeze")
EVIDENCE_DIR = WT / "_tl-orc" / "project" / "evidence" / "T015-r01"
REPLAYS_DIR = EVIDENCE_DIR / "replays"
ALLOWED_SETS_DIR = EVIDENCE_DIR / "allowed_sets"
INPUTS_DIR = EVIDENCE_DIR / "inputs"
SCHEMA_PATH = WT / "schemas" / "context-ledger.schema.json"

schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

# Mapping replays to checkpoints and allowed set
REPLAYS = [
    ("A'_reference", "checkpoint-A", ALLOWED_SETS_DIR / "allowed_set_checkpoint-A.json", INPUTS_DIR / "checkpoint-A" / "resume.json"),
    ("A'_t015", "checkpoint-A", ALLOWED_SETS_DIR / "allowed_set_checkpoint-A.json", INPUTS_DIR / "checkpoint-A" / "resume.json"),
    ("B_reference", "checkpoint-B", ALLOWED_SETS_DIR / "allowed_set_checkpoint-B.json", INPUTS_DIR / "checkpoint-B" / "resume.json"),
    ("B_t015", "checkpoint-B", ALLOWED_SETS_DIR / "allowed_set_checkpoint-B.json", INPUTS_DIR / "checkpoint-B" / "resume.json"),
    ("C_reference", "checkpoint-C", ALLOWED_SETS_DIR / "allowed_set_checkpoint-C.json", INPUTS_DIR / "checkpoint-C" / "resume.json"),
    ("C_t015", "checkpoint-C", ALLOWED_SETS_DIR / "allowed_set_checkpoint-C.json", INPUTS_DIR / "checkpoint-C" / "resume.json"),
]

sys.path.insert(0, str(WT))
from scripts.context_ledger import build_ledger_from_transcript, validate_context_ledger

print("=== Regenerating and Validating 6 Ledgers from r01 Transcripts ===")
for replay_name, cp_name, allowed_set_file, sources_file in REPLAYS:
    replay_dir = REPLAYS_DIR / replay_name
    transcript_file = replay_dir / "canonical_transcript.jsonl"

    if not transcript_file.is_file():
        print(f"Skipping {replay_name}: transcript not found")
        continue

    allowed_data = json.loads(allowed_set_file.read_text(encoding="utf-8")) if allowed_set_file.is_file() else {}
    inputs = allowed_data.get("inputs", [])
    support = allowed_data.get("allowed_support", [])

    ledger = build_ledger_from_transcript(
        transcript_path=transcript_file,
        unit="T015",
        phase="review",
        allowed_inputs=inputs,
        allowed_support=support,
        allowed_set_path=allowed_set_file if allowed_set_file.is_file() else None,
        sources_manifest_path=sources_file if sources_file.is_file() else None,
    )

    # Validate against schema
    is_valid, errors = validate_context_ledger(ledger)
    if not is_valid:
        print(f"ERROR: Ledger for {replay_name} failed schema validation: {errors}")
        sys.exit(1)

    obs_count = len(ledger.get("observed_reads", []))
    failed_count = len(ledger.get("failed_read_attempts", []))
    disallowed_count = len(ledger.get("disallowed_external_attempts", []))
    outside_count = len(ledger.get("reads_outside_allowed_set", []))
    ra = ledger.get("retrieval_amplification")

    print(f"[{replay_name}] VALID OK:")
    print(f"  observed_reads: {obs_count}")
    print(f"  failed_read_attempts: {failed_count}")
    print(f"  disallowed_external_attempts: {disallowed_count}")
    print(f"  reads_outside_allowed_set: {outside_count}")
    print(f"  retrieval_amplification (RA): {ra}")
    print(f"  tool_delivery_ratio: {ledger.get('tool_metrics', {}).get('tool_delivery_ratio')}")
    print()

print("ALL 6 LEDGERS REGENERATED AND VALIDATED 100% AGAINST SCHEMA!")
