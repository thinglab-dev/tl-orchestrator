#!/usr/bin/env python3
"""Read-only executable/profile preflight. It never installs or invokes a global installer."""
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path
from workflow_quality import load_json, write_json

def version(command: str | None) -> str:
    if not command: return "unknown"
    try:
        return subprocess.run([command, "--version"], text=True, capture_output=True, timeout=3, check=False).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired): return "unknown"
def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--profile", type=Path); parser.add_argument("--tool", action="append", default=[], metavar="NAME=COMMAND[,required|optional]"); parser.add_argument("--output", type=Path); args = parser.parse_args()
    try: profile = load_json(args.profile) if args.profile else None
    except (OSError, UnicodeDecodeError, ValueError) as exc: write_json({"ok": False, "errors": [str(exc)], "tools": []}, args.output); raise SystemExit(1)
    errors = []
    if args.profile:
        required = {"schema_version", "role", "task_kind", "conflict_authority", "skill_limit", "available_skills", "selected_skills"}
        selected, available = profile.get("selected_skills"), profile.get("available_skills")
        if set(profile) - {"schema_version", "role", "task_kind", "conflict_authority", "skill_limit", "available_skills", "selected_skills", "compression"} or not required.issubset(profile) or profile.get("schema_version") != 1 or profile.get("conflict_authority") != "consumer": errors.append("invalid profile contract")
        if not isinstance(profile.get("skill_limit"), int) or isinstance(profile.get("skill_limit"), bool) or not 1 <= profile["skill_limit"] <= 5 or not isinstance(available, list) or not all(isinstance(name, str) and name.strip() for name in available) or not isinstance(selected, list) or len(selected) > profile.get("skill_limit", 0) or len(selected) > 5 or (available and not selected): errors.append("invalid skill selection limit")
        for skill in selected if isinstance(selected, list) else []:
            valid = isinstance(skill, dict) and set(skill) == {"name", "source", "ref", "sha256", "authors", "license", "on_demand"} and isinstance(skill.get("name"), str) and skill["name"].strip() in available and isinstance(skill.get("source"), str) and "://" in skill["source"] and isinstance(skill.get("ref"), str) and skill["ref"].strip() and isinstance(skill.get("sha256"), str) and __import__("re").fullmatch(r"[0-9a-f]{64}", skill["sha256"]) and isinstance(skill.get("authors"), list) and bool(skill["authors"]) and all(isinstance(author, str) and author.strip() for author in skill["authors"]) and isinstance(skill.get("license"), str) and skill["license"].strip() and skill.get("on_demand") is True
            if not valid: errors.append("invalid selected skill provenance")
        compression = profile.get("compression")
        if compression and (not isinstance(compression, dict) or not compression.get("configuration_ref") or (compression.get("adapter") == "codex" and compression.get("mode") == "input")): errors.append("invalid declared compression")
    tools = []
    for item in args.tool:
        if "=" not in item: errors.append(f"invalid tool: {item}"); continue
        name, command = item.split("=", 1); command, separator, requirement = command.rpartition(",")
        if not separator: command, requirement = item.split("=", 1)[1], "optional"
        if requirement not in {"required", "optional"}: errors.append(f"invalid requirement: {item}"); continue
        found = shutil.which(command)
        if requirement == "required" and not found: errors.append(f"required tool unavailable: {name}")
        tools.append({"name": name, "command": command, "requirement": requirement, "executable_found": bool(found), "availability": "available" if found else "unavailable", "version": version(found), "installed": "unknown"})
    result = {"ok": not errors, "errors": errors, "tools": tools, "profile": profile, "compression": (profile or {}).get("compression", {"status": "unknown"})}
    write_json(result, args.output); raise SystemExit(0 if not errors else 1)
if __name__ == "__main__": main()

