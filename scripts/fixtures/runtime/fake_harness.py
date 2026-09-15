#!/usr/bin/env python3
"""Scripted stand-in for a model harness, used by the runtime tests.

Reads `<scenario>/<role>.json` (a list of actions) and applies the next unconsumed action:
write or delete files, emit a result file, exit with a code, crash without a result, or
print a fake usage line. The counter lives on disk so the runtime's own restarts see the
same sequence a real harness would.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    scenario = Path(args.scenario)
    actions = json.loads((scenario / f"{args.role}.json").read_text(encoding="utf-8"))
    counter = scenario / f"{args.role}.count"
    index = int(counter.read_text(encoding="utf-8")) if counter.is_file() else 0
    counter.write_text(str(index + 1), encoding="utf-8")
    action = actions[min(index, len(actions) - 1)] if actions else {}
    pack = Path(args.pack).read_text(encoding="utf-8")
    (scenario / f"{args.role}-{index}.pack.md").write_text(pack, encoding="utf-8")
    (scenario / f"{args.role}-{index}.env.json").write_text(json.dumps(sorted(os.environ)), encoding="utf-8")
    if action.get("sleep"):
        time.sleep(float(action["sleep"]))
    for rel, content in (action.get("files") or {}).items():
        path = Path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for rel in action.get("delete") or []:
        Path(rel).unlink(missing_ok=True)
    if action.get("argv"):
        import subprocess
        subprocess.run(action["argv"], check=False)
    if action.get("stdout"):
        sys.stdout.write(action["stdout"] + "\n")
    if action.get("stderr"):
        sys.stderr.write(action["stderr"] + "\n")
    if action.get("crash"):
        return int(action.get("exit", 1))
    result = Path(args.result)
    result.parent.mkdir(parents=True, exist_ok=True)
    if args.role == "checker":
        payload = {"schema_version": 1, "verdict": action.get("verdict", "approved"),
                   "action_items": action.get("action_items", []), "deferred": action.get("deferred", []), "rejected": []}
    else:
        payload = {"outcome": action.get("outcome", "ready_for_delivery"), "decision": action.get("decision", "done"),
                   "blockers": action.get("blockers", []), "next_action": "runtime gates", "observable_usage": "unknown", "proof_refs": []}
    if not action.get("no_result"):
        result.write_text(json.dumps(payload), encoding="utf-8")
    return int(action.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
