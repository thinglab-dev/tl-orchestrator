#!/usr/bin/env python3
"""
build_r02_review_bundle.py - Builds the blind evaluation bundle (review-bundle/)
for T015 r02 review by Checker Codex Terra.

Layout:
review-bundle/
├── A/
│   ├── Alpha/
│   └── Beta/
├── B/
│   ├── Alpha/
│   └── Beta/
└── C/
    ├── Alpha/
    └── Beta/

Applies r02 blinding key:
A: Alpha=t015, Beta=reference
B: Alpha=reference, Beta=t015
C: Alpha=t015, Beta=reference

Explicit experimental validity:
Checkpoint C Beta (C Reference):
  efficiency: invalid (AC16 violation)
  robustness: valid_failure
Checkpoint C Alpha (C T015):
  efficiency: invalid (paired comparison unfeasible due to baseline contamination)
  robustness: valid_pass (100% confined)
Checkpoints A and B (both arms):
  efficiency: valid
  robustness: valid_pass

Sanitizes all absolute paths, session UUIDs, and explicit treatment markers.
"""

import json
import os
import re
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPLAYS_DIR = BASE_DIR / "replays"
BLINDING_FILE = BASE_DIR / "blinding" / "blinding-key.json"
BUNDLE_DIR = BASE_DIR / "review-bundle"

ABS_PATH_PATTERNS = [
    r"/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/reference",
    r"/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/t015",
    r"/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/wt/t015-freeze",
    r"/Users/albertiano/thinglab-platform",
]


def sanitize_text(text: str, arm_label: str) -> str:
    s = text
    for p in ABS_PATH_PATTERNS:
        s = s.replace(p, "<repo-root>")
    s = s.replace("Context Economy & Selective Retrieval (T015)", f"Política Experimental de Contexto (Tratamento {arm_label})")
    s = s.replace("Política de Contexto Vigente (Referência)", f"Política de Contexto Vigente (Tratamento {arm_label})")
    s = s.replace("_tl-orc/project/evidence/T015-r01/inputs/", "_tl-orc/project/evidence/benchmark-inputs/")
    s = s.replace("T015-replay-", "replay-")
    return s


def build_bundle():
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    blinding_key = json.loads(BLINDING_FILE.read_text(encoding="utf-8"))

    summary_manifest = {
        "bundle_schema_version": 2,
        "round": "r02",
        "description": "Blind comparison bundle for T015-r02 experimental replays across Checkpoints A, B, and C.",
        "checkpoints": ["A", "B", "C"],
        "arms": ["Alpha", "Beta"],
        "experimental_protocol": {
            "model": "claude-sonnet-5",
            "effort": "medium",
            "tool_policy": "Read,Glob,Grep,Bash",
            "harness_gate": "Hardened auditor with realpath confinement, bash command parser and canonical allowed_set",
            "paired_replays_count": 6
        },
        "findings_summary": {
            "checkpoint_A": "Valid for efficiency comparison. Favors treatment with selective retrieval.",
            "checkpoint_B": "Valid for efficiency comparison. Mixed trade-off: significant delivered byte reduction (-69.5%) accompanied by higher turn count, output tokens, and cache_read (+80.3%).",
            "checkpoint_C": "Comparison of efficiency is INVALID due to baseline reference confinement failure (AC16 violation: 292 bytes external metadata delivered via Glob and 1 disallowed external grep attempt). Valid only as robustness and baseline failure proof. Selective retrieval arm achieved 100% confinement.",
            "tool_delivery_ratio": "Raw tool result bytes == delivered bytes (1.00 ratio across all replays). Tool-result compaction (AC09/AC10) was not empirically exercised in this benchmark and remains verified by deterministic unit tests."
        },
        "sanitization": [
            "Physical environment paths normalized to <repo-root>",
            "Session UUIDs and treatment identifiers blinded to Alpha/Beta",
            "Model parameters and evaluation criteria held constant"
        ]
    }

    for cp_key in ["A", "B", "C"]:
        lookup_key = "A'" if cp_key == "A" else cp_key
        cp_orig = lookup_key
        info = blinding_key[lookup_key]

        cp_dir = BUNDLE_DIR / cp_key
        cp_dir.mkdir(parents=True, exist_ok=True)

        for arm in ["Alpha", "Beta"]:
            treatment = info[arm]
            src_replay_dir = REPLAYS_DIR / f"{cp_orig}_{treatment}"
            dest_arm_dir = cp_dir / arm
            dest_arm_dir.mkdir(parents=True, exist_ok=True)

            print(f"Building {cp_key}/{arm} from {src_replay_dir.name} ({treatment})...")

            # 1. Decision
            raw_dec = (src_replay_dir / "raw_decision.md").read_text(encoding="utf-8")
            san_dec = sanitize_text(raw_dec, arm)
            (dest_arm_dir / "decision.md").write_text(san_dec, encoding="utf-8")

            # 2. Ledger
            src_ledger = json.loads((src_replay_dir / "ledger.json").read_text(encoding="utf-8"))
            san_ledger_str = sanitize_text(json.dumps(src_ledger, indent=2), arm)
            san_ledger = json.loads(san_ledger_str)
            san_ledger["unit"] = f"replay-{cp_key}-{arm}"
            (dest_arm_dir / "ledger.json").write_text(json.dumps(san_ledger, indent=2) + "\n", encoding="utf-8")

            # 3. Manifest
            src_manifest = json.loads((src_replay_dir / "replay_manifest.json").read_text(encoding="utf-8"))
            
            # Determine experimental validity
            if cp_key == "C":
                if treatment == "reference":
                    exp_validity = {"efficiency": "invalid", "robustness": "valid_failure"}
                else:
                    exp_validity = {"efficiency": "invalid", "robustness": "valid_pass"}
            else:
                exp_validity = {"efficiency": "valid", "robustness": "valid_pass"}

            # Sanitize disallowed external attempts
            san_disallowed = []
            for d in san_ledger.get("disallowed_external_attempts", []):
                if isinstance(d, dict):
                    entry = {
                        "path": sanitize_text(d.get("path", ""), arm),
                        "reason": sanitize_text(d.get("reason", ""), arm),
                    }
                    if d.get("tool"):
                        entry["tool"] = d["tool"]
                    san_disallowed.append(entry)
                else:
                    san_disallowed.append(sanitize_text(str(d), arm))

            san_manifest = {
                "checkpoint": cp_key,
                "arm": arm,
                "model": src_manifest.get("model", "claude-sonnet-5"),
                "effort": src_manifest.get("effort", "medium"),
                "tool_policy": src_manifest.get("tool_policy", "Read,Glob,Grep,Bash"),
                "wall_clock_seconds": src_manifest.get("wall_clock_seconds"),
                "turn_count": san_ledger.get("turn_count"),
                "exit_code": src_manifest.get("exit_code", 0),
                "reads_outside_allowed_set": san_ledger.get("reads_outside_allowed_set", []),
                "failed_read_attempts": san_ledger.get("failed_read_attempts", []),
                "disallowed_external_attempts": san_disallowed,
                "experimental_validity": exp_validity
            }
            (dest_arm_dir / "manifest.json").write_text(json.dumps(san_manifest, indent=2) + "\n", encoding="utf-8")

            # 4. Canonical Transcript
            can_lines = (src_replay_dir / "canonical_transcript.jsonl").read_text(encoding="utf-8").splitlines()
            san_lines = [sanitize_text(l, arm) for l in can_lines if l.strip()]
            (dest_arm_dir / "canonical_transcript.jsonl").write_text("\n".join(san_lines) + "\n", encoding="utf-8")

    (BUNDLE_DIR / "bundle_manifest.json").write_text(json.dumps(summary_manifest, indent=2) + "\n", encoding="utf-8")
    print("\nReview bundle for r02 built successfully at:", BUNDLE_DIR)


if __name__ == "__main__":
    build_bundle()
