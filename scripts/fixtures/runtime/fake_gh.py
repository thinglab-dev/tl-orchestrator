#!/usr/bin/env python3
"""Scripted stand-in for the GitHub CLI, used by the runtime tests.

State lives in the JSON file named by TL_FAKE_GH_STATE. `checks` answers are consumed from
the `checks_sequence` list so a test can script pending → failure → success. Every call is
appended to `calls` so a test can prove an effect happened exactly once.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    state_path = Path(os.environ["TL_FAKE_GH_STATE"])
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    state.setdefault("prs", {})
    state.setdefault("calls", [])
    state.setdefault("checks_sequence", ["success"])
    state.setdefault("failed_log", "")
    state["calls"].append(argv)
    out = ""
    code = 0
    if argv[:2] == ["pr", "create"]:
        head = argv[argv.index("--head") + 1]
        number = len(state["prs"]) + 100
        state["prs"][head] = {"number": number, "url": f"https://example.invalid/pr/{number}", "state": "OPEN", "mergedAt": None}
        out = state["prs"][head]["url"]
    elif argv[:2] == ["pr", "list"]:
        head = argv[argv.index("--head") + 1]
        pr = state["prs"].get(head)
        out = json.dumps([{"number": pr["number"], "url": pr["url"]}] if pr else [])
    elif argv[:2] == ["pr", "view"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        out = json.dumps({"state": pr["state"], "mergedAt": pr["mergedAt"]} if pr else {})
        code = 0 if pr else 1
    elif argv[:2] == ["pr", "merge"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        if pr is None or state.get("merge_fails"):
            code = 1
            sys.stderr.write("merge refused\n")
        else:
            pr["state"], pr["mergedAt"] = "MERGED", "2026-01-01T00:00:00Z"
    elif argv[:2] == ["pr", "checks"]:
        seq = state["checks_sequence"]
        current = seq.pop(0) if len(seq) > 1 else seq[0]
        mapping = {"success": "SUCCESS", "failure": "FAILURE", "pending": "PENDING"}
        out = json.dumps([{"name": "ci", "state": mapping.get(current, current), "link": "", "workflow": "Validate"}])
        code = 0 if current == "success" else 1
    elif argv[:2] == ["run", "list"]:
        out = json.dumps([{"databaseId": 7, "conclusion": "failure", "status": "completed"}])
    elif argv[:2] == ["run", "view"]:
        out = state["failed_log"]
    elif argv[:2] == ["run", "rerun"]:
        state["reruns"] = state.get("reruns", 0) + 1
    else:
        code = 2
        sys.stderr.write("unsupported fake gh call\n")
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
