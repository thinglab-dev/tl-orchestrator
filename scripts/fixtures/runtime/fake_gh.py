#!/usr/bin/env python3
"""Scripted stand-in for the GitHub CLI, used by the runtime tests.

State lives in the JSON file named by TL_FAKE_GH_STATE. `checks` answers are consumed from
the `checks_sequence` list so a test can script pending → failure → success. Every call is
appended to `calls` so a test can prove an effect happened exactly once.
"""

from __future__ import annotations

import json
import os
import subprocess
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
        base = argv[argv.index("--base") + 1]
        head_oid = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip()
        state["prs"][head] = {"number": number, "url": f"https://example.invalid/pr/{number}", "state": "OPEN", "mergedAt": None, "base": base, "head_oid": head_oid}
        out = state["prs"][head]["url"]
    elif argv[:2] == ["pr", "list"]:
        head = argv[argv.index("--head") + 1]
        pr = state["prs"].get(head)
        if pr and pr["state"] == "OPEN":
            pr["head_oid"] = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip() or pr.get("head_oid")
        out = json.dumps([{"number": pr["number"], "url": pr["url"], "baseRefName": pr.get("base"), "headRefOid": pr.get("head_oid"), "state": pr["state"]}] if pr else [])
    elif argv[:2] == ["pr", "view"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        if pr and pr["state"] == "OPEN":
            head = next(h for h, p in state["prs"].items() if p is pr)
            pr["head_oid"] = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip() or pr.get("head_oid")
        out = json.dumps({"state": pr["state"], "mergedAt": pr["mergedAt"], "headRefOid": pr.get("head_oid"), "baseRefName": pr.get("base")} if pr else {})
        code = 0 if pr else 1
    elif argv[:2] == ["pr", "merge"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        expected = argv[argv.index("--match-head-commit") + 1] if "--match-head-commit" in argv else None
        head_now = subprocess.run(["git", "rev-parse", next(h for h, p in state["prs"].items() if p is pr)], capture_output=True, text=True).stdout.strip() if pr else ""
        if pr is None or state.get("merge_fails") or (expected and expected != head_now):
            code = 1
            sys.stderr.write("merge refused" + chr(10))
        else:
            if state.get("merge_queues"):
                state["queued"] = state.get("queued", 0) + 1  # success reply, PR stays OPEN (merge queue)
                pr["head_oid"] = head_now
            else:
                pr["state"], pr["mergedAt"], pr["head_oid"] = "MERGED", "2026-01-01T00:00:00Z", head_now
            if state.get("retarget_on_merge"):
                pr["base"] = state["retarget_on_merge"]
    elif argv[:2] == ["pr", "checks"]:
        seq = state["checks_sequence"]
        current = seq.pop(0) if len(seq) > 1 else seq[0]
        mapping = {"success": "SUCCESS", "failure": "FAILURE", "pending": "PENDING"}
        out = json.dumps([{"name": "ci", "state": mapping.get(current, current), "link": "", "workflow": "Validate"}])
        code = 0 if current == "success" else 1
    elif argv[:2] == ["run", "list"]:
        commit = argv[argv.index("--commit") + 1] if "--commit" in argv else ""
        out = json.dumps([{"databaseId": 6, "conclusion": "failure", "status": "completed", "headSha": "0" * 40},
                          {"databaseId": 7, "conclusion": "failure", "status": "completed", "headSha": commit}])
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
