#!/usr/bin/env python3
"""
audit_table.py - Event-by-event audit of all tool calls across the 6 replays of r01.
Outputs the canonical audit table required by the maintainer:
- session
- tool_use_id
- tool
- raw_target
- cwd_at_call
- normalized_target
- result_status
- bytes_delivered
- classification
"""

import json
import re
import shlex
from pathlib import Path

WT = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/wt/t015-freeze")
EVIDENCE_DIR = WT / "_tl-orc" / "project" / "evidence" / "T015-r01"
REPLAYS_DIR = EVIDENCE_DIR / "replays"
ALLOWED_SETS_DIR = EVIDENCE_DIR / "allowed_sets"

REPLAYS = [
    ("A'_reference", "checkpoint-A", ALLOWED_SETS_DIR / "allowed_set_checkpoint-A.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/reference"),
    ("A'_t015", "checkpoint-A", ALLOWED_SETS_DIR / "allowed_set_checkpoint-A.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/t015"),
    ("B_reference", "checkpoint-B", ALLOWED_SETS_DIR / "allowed_set_checkpoint-B.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/reference"),
    ("B_t015", "checkpoint-B", ALLOWED_SETS_DIR / "allowed_set_checkpoint-B.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/t015"),
    ("C_reference", "checkpoint-C", ALLOWED_SETS_DIR / "allowed_set_checkpoint-C.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/reference"),
    ("C_t015", "checkpoint-C", ALLOWED_SETS_DIR / "allowed_set_checkpoint-C.json", "/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/replay-env/t015"),
]

def normalize_path(path_str: str, cwd_str: str, default_repo_root: str) -> str:
    """Normalize a raw path against effective cwd and repo root."""
    p_str = path_str.strip().strip("'\"")
    if p_str.startswith("file://"):
        p_str = p_str[7:]
    
    p = Path(p_str)
    if not p.is_absolute():
        p = Path(cwd_str) / p
    
    # Try resolving relative to default_repo_root
    try:
        resolved = p.resolve()
        repo_res = Path(default_repo_root).resolve()
        if resolved.is_relative_to(repo_res):
            return str(resolved.relative_to(repo_res))
    except Exception:
        pass
    
    # If path contains _tl-orc, strip before _tl-orc
    pos = p_str.find("_tl-orc")
    if pos != -1:
        return p_str[pos:]
    
    return str(p)

def classify_target(normalized_target: str, raw_target: str, is_fail: bool, out_bytes: int, allowed_inputs: list[str], allowed_support: list[str]) -> str:
    # Check prohibited hard-fail patterns
    prohibited = ["thinglab/platform", "blinding-key"]
    for pat in prohibited:
        if pat in raw_target or pat in normalized_target:
            return "disallowed_external_attempt"

    system_support = [".git", ".system_generated", "scripts", "docs", "prompts", "schemas", "CHANGELOG.md", "README.md", "SKILL.md", "/dev/null"]
    
    norm = normalized_target.lstrip("./")
    
    # Check allowed_inputs
    for inp in allowed_inputs:
        inp_norm = inp.strip().strip("'\"").lstrip("./")
        if norm == inp_norm or norm.startswith(inp_norm + "/") or norm.startswith(inp_norm):
            if is_fail or out_bytes == 0:
                return "failed_read_attempt"
            return "allowed_input"
            
    # Check allowed_support + system_support
    for supp in allowed_support + system_support:
        supp_norm = supp.strip().strip("'\"").lstrip("./")
        if norm == supp_norm or norm.startswith(supp_norm + "/") or norm.startswith(supp_norm) or norm == "/dev/null" or raw_target in ("/dev/null", "dev/null"):
            if is_fail or out_bytes == 0:
                return "failed_read_attempt"
            return "allowed_support"
            
    if is_fail or out_bytes == 0:
        return "failed_read_attempt"
    return "outside_allowed_set"

all_audit_rows = []

for session_name, cp_name, allowed_set_file, default_cwd in REPLAYS:
    replay_dir = REPLAYS_DIR / session_name
    raw_file = replay_dir / "raw_session.jsonl"
    
    allowed_data = json.loads(allowed_set_file.read_text(encoding="utf-8")) if allowed_set_file.is_file() else {}
    allowed_inputs = allowed_data.get("inputs", [])
    allowed_support = allowed_data.get("allowed_support", [])
    
    raw_lines = [l.strip() for l in raw_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    
    # First pass: map tool results
    results_by_id = {}
    for line in raw_lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message", {})
        for part in msg.get("content", []):
            if isinstance(part, dict) and part.get("type") == "tool_result":
                tid = part.get("tool_use_id")
                results_by_id[tid] = part

    for line in raw_lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message", {})
        for part in msg.get("content", []):
            if isinstance(part, dict) and part.get("type") == "tool_use":
                tu_id = part.get("id")
                t_name = part.get("name")
                t_input = part.get("input", {})
                
                res_obj = results_by_id.get(tu_id, {})
                r_content = res_obj.get("content", "")
                if isinstance(r_content, list):
                    r_text = "\n".join(str(p.get("text", p)) for p in r_content)
                else:
                    r_text = str(r_content)
                is_err = res_obj.get("is_error", False)
                out_bytes = len(r_text.encode("utf-8"))
                
                # Check outcome status
                if is_err:
                    res_status = "error"
                elif "File does not exist" in r_text or "No such file" in r_text:
                    res_status = "file_not_found"
                elif out_bytes == 0:
                    res_status = "empty"
                else:
                    res_status = "success"

                # Case A: Read tool
                if t_name == "Read":
                    raw_target = str(t_input.get("file_path") or t_input.get("path", ""))
                    cwd_at_call = default_cwd
                    norm_target = normalize_path(raw_target, cwd_at_call, default_cwd)
                    is_failed = (res_status != "success")
                    classification = classify_target(norm_target, raw_target, is_failed, out_bytes, allowed_inputs, allowed_support)
                    
                    all_audit_rows.append({
                        "session": session_name,
                        "tool_use_id": tu_id,
                        "tool": "Read",
                        "raw_target": raw_target,
                        "cwd_at_call": cwd_at_call,
                        "normalized_target": norm_target,
                        "result_status": res_status,
                        "bytes_delivered": 0 if is_failed else out_bytes,
                        "classification": classification,
                    })

                # Case B: Bash tool
                elif t_name == "Bash":
                    cmd_str = str(t_input.get("command", ""))
                    # Parse chained commands and track cwd across cd
                    current_cwd = default_cwd
                    
                    # Split by &&, ;, ||
                    sub_cmds = re.split(r'(?:;|&&|\|\|)', cmd_str)
                    read_found = False
                    for sc in sub_cmds:
                        sc = sc.strip()
                        if not sc:
                            continue
                        try:
                            tokens = shlex.split(sc)
                        except Exception:
                            tokens = sc.split()
                        if not tokens:
                            continue
                        
                        # Handle cd
                        if tokens[0] == "cd" and len(tokens) > 1:
                            target_dir = tokens[1].strip("'\"")
                            p_dir = Path(target_dir)
                            if not p_dir.is_absolute():
                                p_dir = Path(current_cwd) / p_dir
                            current_cwd = str(p_dir)
                            continue
                            
                        # Handle read_section.py
                        read_sec_idx = -1
                        for i, tok in enumerate(tokens):
                            if tok.endswith("read_section.py"):
                                read_sec_idx = i
                                break
                        if read_sec_idx != -1:
                            sub_tokens = tokens[read_sec_idx + 1:]
                            rf = None
                            for idx, tok in enumerate(sub_tokens):
                                if tok in ("--file", "-f") and idx + 1 < len(sub_tokens):
                                    rf = sub_tokens[idx + 1]
                                    break
                                elif tok.startswith("--file="):
                                    rf = tok.split("=", 1)[1]
                                    break
                                elif not tok.startswith("-"):
                                    rf = tok
                                    break
                            if rf and not rf.startswith((">", "<", "1>", "2>")):
                                read_found = True
                                norm_target = normalize_path(rf, current_cwd, default_cwd)
                                is_failed = (res_status != "success")
                                classification = classify_target(norm_target, rf, is_failed, out_bytes, allowed_inputs, allowed_support)
                                all_audit_rows.append({
                                    "session": session_name,
                                    "tool_use_id": tu_id,
                                    "tool": "Bash:read_section",
                                    "raw_target": rf,
                                    "cwd_at_call": current_cwd,
                                    "normalized_target": norm_target,
                                    "result_status": res_status,
                                    "bytes_delivered": 0 if is_failed else out_bytes,
                                    "classification": classification,
                                })
                            continue

                        # Handle cat, head, sed
                        cname = Path(tokens[0]).name
                        if cname in ("cat", "head", "tail", "sed"):
                            # Extract file arguments
                            files = []
                            if cname in ("cat", "head", "tail"):
                                for tok in tokens[1:]:
                                    if tok in (">", ">>", "<", "1>", "2>", "2>&1", "|", "||", "&&", ";"):
                                        break
                                    if tok.startswith(("-", ">", "<", "1>", "2>")):
                                        continue
                                    files.append(tok)
                            elif cname == "sed":
                                for tok in tokens[1:]:
                                    if tok in (">", ">>", "<", "1>", "2>", "2>&1", "|", "||", "&&", ";"):
                                        break
                                non_opts = [tok for tok in tokens[1:] if not tok.startswith(("-", ">", "<", "1>", "2>")) and tok not in ("|", "||", "&&", ";")]
                                if non_opts and len(non_opts) > 1:
                                    files.extend(non_opts[1:])
                                elif non_opts and "-e" in tokens:
                                    files.extend(non_opts)

                            for f in files:
                                read_found = True
                                norm_target = normalize_path(f, current_cwd, default_cwd)
                                is_failed = (res_status != "success")
                                classification = classify_target(norm_target, f, is_failed, out_bytes, allowed_inputs, allowed_support)
                                all_audit_rows.append({
                                    "session": session_name,
                                    "tool_use_id": tu_id,
                                    "tool": f"Bash:{cname}",
                                    "raw_target": f,
                                    "cwd_at_call": current_cwd,
                                    "normalized_target": norm_target,
                                    "result_status": res_status,
                                    "bytes_delivered": 0 if is_failed else out_bytes,
                                    "classification": classification,
                                })

                # Case C: Grep tool
                elif t_name == "Grep":
                    raw_target = str(t_input.get("path", ""))
                    if raw_target:
                        norm_target = normalize_path(raw_target, default_cwd, default_cwd)
                        is_failed = (res_status != "success")
                        classification = classify_target(norm_target, raw_target, is_failed, out_bytes, allowed_inputs, allowed_support)
                        all_audit_rows.append({
                            "session": session_name,
                            "tool_use_id": tu_id,
                            "tool": "Grep",
                            "raw_target": raw_target,
                            "cwd_at_call": default_cwd,
                            "normalized_target": norm_target,
                            "result_status": res_status,
                            "bytes_delivered": 0 if is_failed else out_bytes,
                            "classification": classification,
                        })

out_json = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/rework-t015/audit_table.json")
out_json.write_text(json.dumps(all_audit_rows, indent=2))
print(f"Audit completed: {len(all_audit_rows)} file read events captured across 6 replays.")
