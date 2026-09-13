#!/usr/bin/env python3
import json
from pathlib import Path

WT = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/wt/t015-freeze")
EVIDENCE_DIR = WT / "_tl-orc" / "project" / "evidence" / "T015-r01"
REPLAYS_DIR = EVIDENCE_DIR / "replays"

replays = ["A'_reference", "A'_t015", "B_reference", "B_t015", "C_reference", "C_t015"]

for r in replays:
    print(f"\n==================== {r} ====================")
    raw_file = REPLAYS_DIR / r / "raw_session.jsonl"
    canon_file = REPLAYS_DIR / r / "canonical_transcript.jsonl"

    print(f"--- RAW SESSION ({raw_file.name}) ---")
    if raw_file.is_file():
        raw_lines = [l.strip() for l in raw_file.read_text().splitlines() if l.strip()]
        for line_idx, line in enumerate(raw_lines):
            try:
                data = json.loads(line)
            except Exception as e:
                continue
            # Check for tool_use in message content
            msg = data.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool_use":
                        t_name = part.get("name")
                        t_input = part.get("input", {})
                        print(f"  [RAW tool_use] tool={t_name}, input={t_input}")

    print(f"--- CANONICAL TRANSCRIPT ({canon_file.name}) ---")
    if canon_file.is_file():
        canon_lines = [l.strip() for l in canon_file.read_text().splitlines() if l.strip()]
        for line in canon_lines:
            try:
                step = json.loads(line)
            except Exception:
                continue
            for call in step.get("tool_calls", []):
                t_name = call.get("tool")
                t_params = call.get("parameters", {})
                t_out = str(call.get("output", ""))[:120].replace("\n", " ")
                print(f"  [CANON call] tool={t_name}, params={t_params}")
                print(f"               output={t_out}...")
