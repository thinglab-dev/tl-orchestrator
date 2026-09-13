#!/usr/bin/env python3
"""
claude_transcript_adapter.py - Adapts raw Claude CLI session JSONL logs into canonical
transcript JSONL format compatible with scripts/context_ledger.py, and audits all tool
calls against AC16 confinement rules with deterministic tripartite classification:
1. reads_outside_allowed_set: only reads that successfully delivered content (>0 bytes)
   from a path outside the allowed set.
2. failed_read_attempts: attempts targeting unallowed paths that failed before delivering
   content (e.g. FileNotFoundError, ENOENT, 0 bytes delivered, confinement effect: none).
3. disallowed_external_attempts: attempts directed at explicitly prohibited roots
   (e.g. thinglab/platform live tree, blinding key, other checkouts/replays).

HARDENING SPECIFICATION:
- Zero implicit system_support: all allowed support files must be explicitly declared
  in allowed_support and bound to the cryptographic hash of the allowed set.
- Real containment check: resolves realpath (following symlinks) against effective cwd
  and checks strict containment within default_repo_root without string-prefix heuristics.
- Comprehensive tool auditing: Read, Bash (cat, sed, head, tail, read_section with cd tracking),
  Grep, and Glob are all audited under identical confinement rules.
"""

import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Optional


def compute_allowed_set_hash(inputs: list[str], allowed_support: list[str]) -> str:
    """Compute deterministic SHA-256 over canonical inputs and allowed_support lists."""
    canonical = {
        "allowed_support": sorted(list(set(str(s).strip().strip("'\"") for s in allowed_support))),
        "inputs": sorted(list(set(str(i).strip().strip("'\"") for i in inputs))),
    }
    canonical_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def audit_path_confinement(
    target_str: str,
    cwd_str: str,
    default_repo_root: str,
    allowed_inputs: list[str],
    allowed_support: list[str],
    is_fail: bool,
    out_bytes: int,
) -> tuple[str, str, str]:
    """
    Audits a target path against AC16 confinement rules without string-cutting heuristics.
    Resolves realpath/symlinks against effective cwd and checks containment in default_repo_root.
    Returns: (canonical_norm_path, classification, reason)
    Classification is one of:
      - "allowed_input"
      - "allowed_support"
      - "failed_read_attempt"
      - "outside_allowed_set"
      - "disallowed_external_attempt"
    """
    clean_target = str(target_str).strip().strip("'\"")
    if clean_target.startswith("file://"):
        clean_target = clean_target[7:]

    # Check prohibited patterns in target string or cwd
    prohibited_patterns = [
        "thinglab/platform",
        "blinding-key",
        "outro-checkout",
        "other-checkout",
        "replay-env/reference/_tl-orc/project/evidence/T015-r01/replays",
        "replay-env/t015/_tl-orc/project/evidence/T015-r01/replays",
        "replay-env/reference/_tl-orc/project/evidence/T015-r02/replays",
        "replay-env/t015/_tl-orc/project/evidence/T015-r02/replays",
    ]
    for pat in prohibited_patterns:
        if pat in clean_target or pat in cwd_str:
            return clean_target, "disallowed_external_attempt", f"Target or cwd matches prohibited pattern '{pat}'"

    # Special case: /dev/null
    if clean_target in ("/dev/null", "dev/null"):
        if "/dev/null" in allowed_support or "dev/null" in allowed_support:
            if is_fail or out_bytes == 0:
                return "/dev/null", "failed_read_attempt", "Target is /dev/null with 0 bytes"
            return "/dev/null", "allowed_support", "Permitted /dev/null device"
        else:
            return "/dev/null", "outside_allowed_set", "/dev/null not declared in allowed_support"

    repo_root = Path(default_repo_root).resolve()
    effective_cwd = Path(cwd_str).resolve() if cwd_str else repo_root

    raw_p = Path(clean_target)
    if not raw_p.is_absolute():
        raw_p = effective_cwd / raw_p

    # Realpath resolution (resolves symlinks)
    try:
        resolved_p = raw_p.resolve()
    except Exception as exc:
        return clean_target, "failed_read_attempt", f"Path resolution failed: {exc}"

    # Containment check: must be strictly inside repo_root
    try:
        is_contained = resolved_p.is_relative_to(repo_root)
    except AttributeError:
        try:
            resolved_p.relative_to(repo_root)
            is_contained = True
        except ValueError:
            is_contained = False

    if not is_contained:
        # Strict containment: any target whose realpath is outside the frozen repo root is a disallowed external attempt
        return str(resolved_p), "disallowed_external_attempt", f"Target realpath is outside frozen repo root: {resolved_p}"

    # Target is inside repo_root: compute exact canonical relative path
    rel_path = str(resolved_p.relative_to(repo_root))

    # NO system_support implicit list! Only explicitly declared allowed_inputs and allowed_support.

    # 1. Check allowed_inputs (exact file match, child of allowed input, or dedicated input directory)
    input_clean_list = [str(inp).strip().strip("'\"").lstrip("./") for inp in allowed_inputs if str(inp).strip().strip("'\"").lstrip("./")]
    for inp_clean in input_clean_list:
        if rel_path == inp_clean or rel_path.startswith(inp_clean + "/"):
            if is_fail or out_bytes == 0:
                return rel_path, "failed_read_attempt", "Input target failed or returned 0 bytes"
            return rel_path, "allowed_input", "Permitted input path"

    # If rel_path is a directory: check if it is within the dedicated input directories
    if input_clean_list:
        dir_parents = [str(Path(x).parent) for x in input_clean_list if str(Path(x).parent) not in (".", "")]
        if dir_parents:
            try:
                common_input_dir = os.path.commonpath(dir_parents)
                if common_input_dir and common_input_dir not in (".", ""):
                    if rel_path == common_input_dir or rel_path.startswith(common_input_dir + "/"):
                        if is_fail or out_bytes == 0:
                            return rel_path, "failed_read_attempt", "Input directory query failed or empty"
                        return rel_path, "allowed_input", "Permitted input directory"
            except Exception:
                pass

    # 2. Check allowed_support (strictly from allowed_set JSON)
    for supp in allowed_support:
        supp_clean = str(supp).strip().strip("'\"").lstrip("./")
        if supp_clean and (rel_path == supp_clean or rel_path.startswith(supp_clean + "/")):
            if is_fail or out_bytes == 0:
                return rel_path, "failed_read_attempt", "Support target failed or returned 0 bytes"
            return rel_path, "allowed_support", "Permitted support path"

    # 3. Neither in allowed_inputs nor in allowed_support
    if is_fail or out_bytes == 0:
        return rel_path, "failed_read_attempt", f"Failed attempt to unallowed path: {rel_path}"
    return rel_path, "outside_allowed_set", f"Read delivered content from undeclared path: {rel_path}"
def strip_heredocs(cmd_str: str) -> tuple[str, list[str]]:
    """Separates shell commands from heredoc stdin bodies."""
    lines = cmd_str.splitlines()
    cmd_lines = []
    heredoc_bodies = []
    in_heredoc = False
    heredoc_delim = ""
    for line in lines:
        if in_heredoc:
            if line.strip() == heredoc_delim:
                in_heredoc = False
            else:
                heredoc_bodies.append(line)
            continue
        m = re.search(r"<<-?\s*[\x27\"]?([A-Za-z0-9_]+)[\x27\"]?", line)
        if m:
            in_heredoc = True
            heredoc_delim = m.group(1)
            cmd_lines.append(line)
        else:
            cmd_lines.append(line)
    return "\n".join(cmd_lines), heredoc_bodies


def adapt_claude_transcript(
    raw_claude_jsonl: Path,
    output_canonical_jsonl: Path,
    allowed_inputs: list[str],
    allowed_support: list[str],
    default_repo_root: Optional[str] = None,
) -> dict[str, Any]:
    repo_root_str = str(Path(default_repo_root).resolve()) if default_repo_root else str(Path.cwd().resolve())
    raw_lines = [l.strip() for l in raw_claude_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]

    canonical_steps = []
    tool_results_by_id = {}
    tool_errors_by_id = {}

    # First pass: collect tool results and error flags
    for line in raw_lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_use_id = part.get("tool_use_id")
                    res_content = part.get("content", "")
                    is_err = part.get("is_error", False)
                    if isinstance(res_content, list):
                        res_text = "\n".join(str(p.get("text", p)) for p in res_content)
                    else:
                        res_text = str(res_content)
                    if tool_use_id:
                        tool_results_by_id[tool_use_id] = res_text
                        tool_errors_by_id[tool_use_id] = bool(is_err)

    step_idx = 0
    all_observed_reads = []
    reads_outside_allowed = []
    failed_read_attempts = []
    disallowed_external_attempts = []

    # Second pass: assemble canonical steps and audit confinement
    for line in raw_lines:
        try:
            d = json.loads(line)
        except Exception:
            continue

        mtype = d.get("type")
        msg = d.get("message", {})
        role = msg.get("role")

        if mtype == "user" or role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                step_idx += 1
                canonical_steps.append({
                    "step_index": step_idx,
                    "source": "USER_INPUT",
                    "type": "USER_INPUT",
                    "content": content,
                })

        elif mtype == "assistant" or role == "assistant":
            step_idx += 1
            usage = msg.get("usage", {})
            u_block = {
                "input_tokens": usage.get("input_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "thinking_tokens": usage.get("output_tokens_details", {}).get("thinking_tokens", 0),
            }

            content = msg.get("content", [])
            t_calls = []
            text_parts = []

            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "tool_use":
                            tu_id = part.get("id")
                            t_name = part.get("name")
                            t_input = dict(part.get("input", {}))
                            t_out = tool_results_by_id.get(tu_id, "")
                            t_err = tool_errors_by_id.get(tu_id, False)

                            out_bytes = len(t_out.encode("utf-8"))
                            is_fail = t_err or ("File does not exist" in t_out) or ("No such file" in t_out) or ("No files found" in t_out) or (out_bytes == 0)
                            if is_fail:
                                if "File does not exist" in t_out or "No such file" in t_out or "No files found" in t_out:
                                    fail_outcome = "file_not_found"
                                elif t_err or "Exit code" in t_out or "Error" in t_out:
                                    fail_outcome = "tool_error"
                                elif out_bytes == 0:
                                    fail_outcome = "empty_result"
                                else:
                                    fail_outcome = "unknown_failure"
                            else:
                                fail_outcome = "none"

                            # 1. Auditing Tool: Read
                            if t_name == "Read":
                                raw_target = str(t_input.get("file_path") or t_input.get("path", ""))
                                norm_target, classification, reason = audit_path_confinement(
                                    target_str=raw_target,
                                    cwd_str=repo_root_str,
                                    default_repo_root=repo_root_str,
                                    allowed_inputs=allowed_inputs,
                                    allowed_support=allowed_support,
                                    is_fail=is_fail,
                                    out_bytes=out_bytes,
                                )
                                t_input["path"] = norm_target
                                t_input["AbsolutePath"] = norm_target

                                if classification == "disallowed_external_attempt":
                                    disallowed_external_attempts.append({
                                        "tool": t_name,
                                        "path": raw_target,
                                        "reason": reason,
                                    })
                                elif classification == "outside_allowed_set":
                                    reads_outside_allowed.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "bytes_delivered": out_bytes,
                                    })
                                elif classification == "failed_read_attempt":
                                    failed_read_attempts.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "outcome": fail_outcome,
                                        "bytes_delivered": 0,
                                        "confinement_effect": "none",
                                    })
                                else:
                                    all_observed_reads.append({
                                        "tool": t_name,
                                        "path": norm_target,
                                        "bytes": out_bytes,
                                        "status": "ok",
                                    })

                            # 2. Auditing Tool: Grep
                            elif t_name == "Grep":
                                raw_target = str(t_input.get("path") or ".")
                                norm_target, classification, reason = audit_path_confinement(
                                    target_str=raw_target,
                                    cwd_str=repo_root_str,
                                    default_repo_root=repo_root_str,
                                    allowed_inputs=allowed_inputs,
                                    allowed_support=allowed_support,
                                    is_fail=is_fail,
                                    out_bytes=out_bytes,
                                )
                                t_input["path"] = norm_target
                                if classification == "disallowed_external_attempt":
                                    disallowed_external_attempts.append({
                                        "tool": t_name,
                                        "path": raw_target,
                                        "reason": reason,
                                    })
                                elif classification == "outside_allowed_set":
                                    reads_outside_allowed.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "bytes_delivered": out_bytes,
                                    })
                                elif classification == "failed_read_attempt":
                                    failed_read_attempts.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "outcome": fail_outcome,
                                        "bytes_delivered": 0,
                                        "confinement_effect": "none",
                                    })
                                else:
                                    all_observed_reads.append({
                                        "tool": t_name,
                                        "path": norm_target,
                                        "bytes": out_bytes,
                                        "status": "ok",
                                    })

                            # 3. Auditing Tool: Glob
                            elif t_name == "Glob":
                                g_dir = t_input.get("path")
                                pattern = str(t_input.get("pattern") or "")
                                if g_dir:
                                    raw_target = str(g_dir)
                                else:
                                    m = re.match(r"^([^[*?{]+)/", pattern)
                                    if m:
                                        raw_target = m.group(1)
                                    else:
                                        raw_target = "."

                                norm_target, classification, reason = audit_path_confinement(
                                    target_str=raw_target,
                                    cwd_str=repo_root_str,
                                    default_repo_root=repo_root_str,
                                    allowed_inputs=allowed_inputs,
                                    allowed_support=allowed_support,
                                    is_fail=is_fail,
                                    out_bytes=out_bytes,
                                )
                                if classification == "disallowed_external_attempt":
                                    disallowed_external_attempts.append({
                                        "tool": t_name,
                                        "path": raw_target,
                                        "reason": reason,
                                    })
                                elif classification == "outside_allowed_set":
                                    reads_outside_allowed.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "bytes_delivered": out_bytes,
                                    })
                                elif classification == "failed_read_attempt":
                                    failed_read_attempts.append({
                                        "path": norm_target,
                                        "tool": t_name,
                                        "outcome": fail_outcome,
                                        "bytes_delivered": 0,
                                        "confinement_effect": "none",
                                    })
                                else:
                                    all_observed_reads.append({
                                        "tool": t_name,
                                        "path": norm_target,
                                        "bytes": out_bytes,
                                    })

                            # 4. Auditing Tool: Bash
                            elif t_name == "Bash":
                                cmd_str = str(t_input.get("command", ""))
                                current_cwd = repo_root_str
                                rewritten_sub_cmds = []

                                # Strip heredocs so stdin bodies are not parsed as shell commands
                                cmds_only, heredocs = strip_heredocs(cmd_str)

                                # Audit heredoc bodies for external paths
                                if heredocs:
                                    body_text = "\n".join(heredocs)
                                    for cand in re.findall(r"[\x27\"]([_a-zA-Z0-9./~-]+\.[a-zA-Z0-9]+)[\x27\"]", body_text):
                                        if cand.startswith("/") or cand.startswith("~") or "/" in cand:
                                            norm_target, classification, reason = audit_path_confinement(
                                                target_str=cand,
                                                cwd_str=current_cwd,
                                                default_repo_root=repo_root_str,
                                                allowed_inputs=allowed_inputs,
                                                allowed_support=allowed_support,
                                                is_fail=is_fail,
                                                out_bytes=out_bytes,
                                            )
                                            if classification == "disallowed_external_attempt":
                                                disallowed_external_attempts.append({
                                                    "tool": "Bash:heredoc",
                                                    "path": cand,
                                                    "reason": reason,
                                                })
                                            elif classification == "outside_allowed_set":
                                                reads_outside_allowed.append({
                                                    "path": norm_target,
                                                    "tool": "Bash:heredoc",
                                                    "bytes_delivered": out_bytes,
                                                })
                                            else:
                                                all_observed_reads.append({
                                                    "tool": "Bash:heredoc",
                                                    "path": norm_target,
                                                    "bytes": out_bytes,
                                                    "status": "ok",
                                                })

                                # Parse bash lines and split on command separators (;, &&, ||, |, &) while respecting quotes
                                parsed_sub_cmds = []
                                for line in cmds_only.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        toks = shlex.split(line)
                                    except Exception:
                                        toks = line.split()
                                    curr = []
                                    for tok in toks:
                                        if tok in (";", "&&", "||", "|", "&"):
                                            if curr:
                                                parsed_sub_cmds.append((" ".join(curr), curr))
                                                curr = []
                                        else:
                                            curr.append(tok)
                                    if curr:
                                        parsed_sub_cmds.append((" ".join(curr), curr))

                                for sc, tokens in parsed_sub_cmds:
                                    if not tokens:
                                        continue

                                    # Track cd
                                    if tokens[0] == "cd" and len(tokens) > 1:
                                        tdir = tokens[1].strip("'\"")
                                        p_dir = Path(tdir)
                                        if not p_dir.is_absolute():
                                            p_dir = Path(current_cwd) / p_dir
                                        try:
                                            current_cwd = str(p_dir.resolve())
                                        except Exception:
                                            current_cwd = str(p_dir)
                                        rewritten_sub_cmds.append(sc)
                                        continue

                                    # Check read_section.py
                                    read_sec_idx = -1
                                    for i, tok in enumerate(tokens):
                                        if tok.endswith("read_section.py"):
                                            read_sec_idx = i
                                            break
                                    if read_sec_idx != -1:
                                        sub_toks = tokens[read_sec_idx + 1:]
                                        rf = None
                                        for idx, tok in enumerate(sub_toks):
                                            if tok in ("--file", "-f") and idx + 1 < len(sub_toks):
                                                rf = sub_toks[idx + 1]
                                                break
                                            elif tok.startswith("--file="):
                                                rf = tok.split("=", 1)[1]
                                                break
                                            elif not tok.startswith("-"):
                                                rf = tok
                                                break
                                        if rf and not rf.startswith((">", "<", "1>", "2>")):
                                            norm_target, classification, reason = audit_path_confinement(
                                                target_str=rf,
                                                cwd_str=current_cwd,
                                                default_repo_root=repo_root_str,
                                                allowed_inputs=allowed_inputs,
                                                allowed_support=allowed_support,
                                                is_fail=is_fail,
                                                out_bytes=out_bytes,
                                            )
                                            if classification == "outside_allowed_set":
                                                reads_outside_allowed.append({
                                                    "path": norm_target,
                                                    "tool": "Bash:read_section",
                                                    "bytes_delivered": out_bytes,
                                                })
                                            elif classification == "failed_read_attempt":
                                                failed_read_attempts.append({
                                                    "path": norm_target,
                                                    "tool": "Bash:read_section",
                                                    "outcome": fail_outcome,
                                                    "bytes_delivered": 0,
                                                    "confinement_effect": "none",
                                                })
                                            elif classification == "disallowed_external_attempt":
                                                disallowed_external_attempts.append({
                                                    "tool": "Bash:read_section",
                                                    "path": rf,
                                                    "reason": reason,
                                                })
                                            else:
                                                all_observed_reads.append({
                                                    "tool": "Bash:read_section",
                                                    "path": norm_target,
                                                    "bytes": out_bytes,
                                                    "status": "ok",
                                                })
                                        rewritten_sub_cmds.append(sc)
                                        continue

                                    # General command file reading & target containment checks
                                    cname = Path(tokens[0]).name
                                    files = []
                                    if cname in ("cat", "head", "tail", "shasum", "sha256sum", "diff", "cmp", "wc"):
                                        for tok in tokens[1:]:
                                            if tok.startswith(("-", ">", "<", "1>", "2>")):
                                                continue
                                            files.append(tok)
                                    elif cname in ("grep", "egrep", "fgrep", "sed", "awk"):
                                        non_opts = [tok for tok in tokens[1:] if not tok.startswith(("-", ">", "<", "1>", "2>"))]
                                        if len(non_opts) > 1:
                                            files.extend(non_opts[1:])
                                        elif non_opts and "-e" in tokens:
                                            files.extend(non_opts)
                                    else:
                                        for tok in tokens[1:]:
                                            if (tok.startswith("/") or tok.startswith("~") or "/" in tok) and not tok.startswith(("-", ">", "<", "1>", "2>")):
                                                files.append(tok)

                                    # Always check any token in command that looks like an absolute path outside repo root
                                    for tok in tokens[1:]:
                                        if tok.startswith("/") and not tok.startswith(("-", ">", "<", "1>", "2>")) and tok not in files:
                                            files.append(tok)

                                    sc_rewritten = sc
                                    for f in files:
                                        norm_target, classification, reason = audit_path_confinement(
                                            target_str=f,
                                            cwd_str=current_cwd,
                                            default_repo_root=repo_root_str,
                                            allowed_inputs=allowed_inputs,
                                            allowed_support=allowed_support,
                                            is_fail=is_fail,
                                            out_bytes=out_bytes,
                                        )
                                        if norm_target != f and f in sc_rewritten:
                                            sc_rewritten = sc_rewritten.replace(f, norm_target)

                                        if classification == "outside_allowed_set":
                                            reads_outside_allowed.append({
                                                "path": norm_target,
                                                "tool": f"Bash:{cname}",
                                                "bytes_delivered": out_bytes,
                                            })
                                        elif classification == "failed_read_attempt":
                                            failed_read_attempts.append({
                                                "path": norm_target,
                                                "tool": f"Bash:{cname}",
                                                "outcome": fail_outcome,
                                                "bytes_delivered": 0,
                                                "confinement_effect": "none",
                                            })
                                        elif classification == "disallowed_external_attempt":
                                            disallowed_external_attempts.append({
                                                "tool": f"Bash:{cname}",
                                                "path": f,
                                                "reason": reason,
                                            })
                                        else:
                                            all_observed_reads.append({
                                                "tool": f"Bash:{cname}",
                                                "path": norm_target,
                                                "bytes": out_bytes,
                                                "status": "ok",
                                            })

                                    rewritten_sub_cmds.append(sc_rewritten)

                                # Update command parameter with rewritten command
                                t_input["command"] = " && ".join(rewritten_sub_cmds)

                            t_calls.append({
                                "tool": t_name,
                                "parameters": t_input,
                                "output": t_out,
                            })

            canonical_steps.append({
                "step_index": step_idx,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "usage": u_block,
                "tool_calls": t_calls,
                "content": "\n".join(text_parts),
            })

    output_canonical_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(output_canonical_jsonl, "w", encoding="utf-8") as f:
        for s in canonical_steps:
            f.write(json.dumps(s) + "\n")

    return {
        "canonical_steps_count": len(canonical_steps),
        "observed_reads": all_observed_reads,
        "reads_outside_allowed_set": reads_outside_allowed,
        "failed_read_attempts": failed_read_attempts,
        "disallowed_external_attempts": disallowed_external_attempts,
    }
