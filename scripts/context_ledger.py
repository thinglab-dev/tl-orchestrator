#!/usr/bin/env python3
"""
context_ledger.py - Post-hoc Context Ledger and Rotation Observability CLI.
Parses harness JSONL transcripts, measures context and tool metrics, audits reads against
confinement gates (AC16), and computes rotation recommendations (AC11, AC12).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Optional


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_path_in_allowed_set(
    path_str: str,
    allowed_inputs: list[str],
    allowed_support: list[str],
    repo_root: Optional[Path] = None,
    cwd: Optional[Path] = None,
) -> bool:
    """
    Check if a file path is permitted under AC16 confinement rules.
    Permitted classes:
    - inputs (frozen checkpoint inputs, spec, task docs)
    - allowed_support (git metadata, harness technical logs, python lib, etc.)
    Uses strict path confinement (no permissive substring checks).
    """
    if not path_str or not isinstance(path_str, str):
        return False

    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    clean_path = path_str.strip().strip("'\"")
    if clean_path.startswith("file://"):
        clean_path = clean_path[7:]

    # /dev/null is a sink, never a source of repository content.  It is the
    # sole system exception; every useful input/support root is frozen by the
    # caller in allowed_inputs or allowed_support.
    if clean_path in ("/dev/null", "dev/null"):
        return True

    p = Path(clean_path)
    if not p.is_absolute():
        p = (cwd or repo_root) / p

    try:
        resolved_p = p.resolve()
        resolved_root = repo_root.resolve()
    except Exception:
        return False

    # External files outside repo
    if not resolved_p.is_relative_to(resolved_root):
        # An external root may only be granted explicitly and absolutely.
        for rule in list(allowed_inputs) + list(allowed_support):
            rule_clean = rule.strip().strip("'\"")
            if rule_clean in ("/dev/null", "dev/null"):
                continue
            rule_p = Path(rule_clean)
            if rule_p.is_absolute():
                try:
                    resolved_rule = rule_p.resolve()
                    if resolved_p == resolved_rule or resolved_p.is_relative_to(resolved_rule):
                        return True
                except (OSError, ValueError):
                    continue
        return False

    # Inside the repository, relative rules are rooted at the repository, not
    # at an arbitrary shell cwd.  Compare canonical paths to defeat traversal
    # and symlink aliases.
    rel = resolved_p.relative_to(resolved_root)
    all_allowed = list(allowed_inputs) + list(allowed_support)

    for rule in all_allowed:
        rule_clean = rule.strip().strip("'\"")
        if rule_clean in ("/dev/null", "dev/null"):
            continue
        rule_p = Path(rule_clean)
        try:
            if rule_p.is_absolute():
                resolved_rule = rule_p.resolve()
                if resolved_p == resolved_rule or resolved_p.is_relative_to(resolved_rule):
                    return True
            elif rel == rule_p or rel.is_relative_to(rule_p):
                return True
        except (OSError, ValueError):
            continue

    return False


def parse_bash_read_commands(command_str: str) -> list[tuple[str, str]]:
    """
    Extract file read operations from a bash command string.
    Returns a list of (file_path, selector) tuples.
    """
    results: list[tuple[str, str]] = []
    if not command_str or not isinstance(command_str, str):
        return results

    # A here-document feeds stdin; its delimiter/body are not files read by
    # cat.  Remove complete bodies before splitting pipelines or newlines.
    without_heredocs = re.sub(
        r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
        "",
        command_str,
        flags=re.MULTILINE | re.DOTALL,
    )

    # This is intentionally a conservative audit parser, not a shell.  It
    # only reports operands of known read commands, never generic words from
    # echo/printf or shell write constructs.
    segments = re.split(r"(?:;|&&|\|\||\||\n)", without_heredocs)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except Exception:
            tokens = segment.split()

        if not tokens:
            continue

        # 1. Check for read_section.py
        read_sec_idx = -1
        for i, tok in enumerate(tokens):
            if tok.endswith("read_section.py"):
                if i == 0 or (i > 0 and tokens[i - 1] in ("python", "python3", "python3.11", "python3.12", "python3.13", "python3.14")):
                    read_sec_idx = i
                    break

        if read_sec_idx != -1:
            sub_tokens = tokens[read_sec_idx + 1:]
            file_path = None
            heading = "full_file"
            i = 0
            pos_args = []
            while i < len(sub_tokens):
                tok = sub_tokens[i]
                if tok.startswith((">", "<", "1>", "2>", "2>&1")):
                    break
                if tok in ("--file", "-f"):
                    if i + 1 < len(sub_tokens):
                        file_path = sub_tokens[i + 1]
                        i += 2
                        continue
                elif tok in ("--heading", "-H", "-s", "--selector"):
                    if i + 1 < len(sub_tokens):
                        heading = sub_tokens[i + 1]
                        i += 2
                        continue
                elif tok.startswith("--file="):
                    file_path = tok.split("=", 1)[1]
                elif tok.startswith(("-f=", "--heading=", "-H=", "-s=", "--selector=")):
                    heading = tok.split("=", 1)[1]
                elif not tok.startswith("-"):
                    pos_args.append(tok)
                i += 1

            if not file_path and pos_args:
                file_path = pos_args[0]
                if len(pos_args) > 1 and heading == "full_file":
                    heading = pos_args[1]

            if file_path and not file_path.startswith((">", "<", "1>", "2>")):
                results.append((file_path, heading))
            continue

        # Look at command name (skip env vars or wrappers)
        cmd_name = None
        cmd_idx = 0
        while cmd_idx < len(tokens):
            tok = tokens[cmd_idx]
            if "=" in tok and not tok.startswith("-"):
                cmd_idx += 1
                continue
            if tok in ("sudo", "env", "time", "nice", "nohup"):
                cmd_idx += 1
                continue
            cmd_name = Path(tok).name
            break

        if not cmd_name:
            continue

        remaining = tokens[cmd_idx + 1:]

        # 2. Check for cat
        if cmd_name == "cat":
            if any(tok.startswith("<<") for tok in remaining):
                continue
            for tok in remaining:
                if tok.startswith("-"):
                    continue
                if tok in (">", ">>", "<", "2>", "1>", "2>&1"):
                    break
                results.append((tok, "full_file"))
            continue

        # 3. Check for head or tail
        if cmd_name in ("head", "tail"):
            skip_next = False
            for tok in remaining:
                if skip_next:
                    skip_next = False
                    continue
                if tok in ("-n", "-c", "-lines", "-bytes"):
                    skip_next = True
                    continue
                if tok.startswith("-"):
                    continue
                if tok in (">", ">>", "<", "2>", "1>", "2>&1"):
                    break
                results.append((tok, "full_file"))
            continue

        # 4. Check for sed
        if cmd_name == "sed":
            # In-place sed is a write operation in this audit model.  Its
            # operands are often temporary output targets and must not become
            # telemetry for source reads.
            if any(tok == "-i" or tok.startswith("-i") for tok in remaining):
                continue
            non_opts: list[str] = []
            skip_next = False
            for idx, tok in enumerate(remaining):
                if skip_next:
                    skip_next = False
                    continue
                if tok in ("-e", "--expression", "-f", "--file"):
                    skip_next = True
                    continue
                if tok == "-i":
                    # GNU sed accepts an optional empty backup suffix.  Do
                    # not mistake it for the edit program or a source file.
                    if idx + 1 < len(remaining) and remaining[idx + 1] == "":
                        skip_next = True
                    continue
                if tok.startswith("-"):
                    continue
                if tok in (">", ">>", "<", "2>", "1>", "2>&1"):
                    break
                non_opts.append(tok)

            # The first remaining operand is sed's program.  Only operands
            # after it are files.  This avoids classifying substitution
            # expressions and temporary write targets as reads.
            for f in non_opts[1:]:
                results.append((f, "full_file"))
            continue

    return results


def build_ledger_from_transcript(
    transcript_path: Path,
    unit: str,
    phase: str,
    wrapper_telemetry_path: Optional[Path] = None,
    allowed_inputs: Optional[list[str]] = None,
    allowed_support: Optional[list[str]] = None,
    allowed_set_path: Optional[Path] = None,
    sources_manifest_path: Optional[Path] = None,
    decision_path: Optional[Path] = None,
    max_turns: Optional[int] = None,
    max_tool_bytes: Optional[int] = None,
    max_cache_tokens: Optional[int] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Parse JSONL transcript and generate the post-hoc context ledger.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    inputs_list = list(allowed_inputs or [])
    support_list = list(allowed_support or [])
    allowed_set_ref: Optional[str] = None

    if allowed_set_path:
        asp = Path(allowed_set_path)
        if asp.is_file():
            allowed_set_ref = str(allowed_set_path)
            try:
                as_data = json.loads(asp.read_text(encoding="utf-8"))
                if "allowed_set" in as_data and isinstance(as_data["allowed_set"], dict):
                    as_data = as_data["allowed_set"]
                for inp in as_data.get("inputs", []):
                    if inp not in inputs_list:
                        inputs_list.append(inp)
                for sup in as_data.get("allowed_support", []):
                    if sup not in support_list:
                        support_list.append(sup)
            except Exception as exc:
                print(f"Warning: could not parse allowed set file: {exc}", file=sys.stderr)

    lines = [l.strip() for l in transcript_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    turn_count = 0
    tool_calls_count = 0
    raw_result_bytes = 0
    delivered_result_bytes = 0

    # Token accounting
    has_token_data = False
    input_tokens = 0
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    output_tokens = 0
    thinking_tokens = 0

    observed_reads: list[dict[str, Any]] = []
    failed_read_attempts: list[dict[str, Any]] = []
    reads_outside_allowed: list[str] = []
    disallowed_external_attempts: list[dict[str, str]] = []

    for line in lines:
        try:
            step = json.loads(line)
        except json.JSONDecodeError:
            continue

        turn_count += 1

        # Check tokens if recorded in step
        usage = step.get("usage") or step.get("tokens")
        if isinstance(usage, dict):
            has_token_data = True
            input_tokens += usage.get("input_tokens", 0)
            cache_creation_input_tokens += usage.get("cache_creation_input_tokens", 0)
            cache_read_input_tokens += usage.get("cache_read_input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            thinking_tokens += usage.get("thinking_tokens", 0)

        # Check tool calls
        tool_calls = step.get("tool_calls") or []
        for call in tool_calls:
            tool_calls_count += 1
            tool_name = call.get("tool") or call.get("name", "unknown")
            params = call.get("parameters") or call.get("args") or {}
            output_content = call.get("output") or call.get("result") or ""
            out_str = output_content if isinstance(output_content, str) else json.dumps(output_content)
            out_bytes = len(out_str.encode("utf-8"))

            raw_result_bytes += out_bytes
            delivered_result_bytes += out_bytes

            is_error = bool(call.get("is_error") or call.get("error") or (call.get("exit_code", 0) != 0))
            err_indicators = [
                "FileNotFoundError",
                "No such file or directory",
                "SelectorNotFoundError",
                "Permission denied",
                "The command exited with code 1",
                "The command exited with code 2",
                "The command exited with code 3",
                "exit code 1",
                "exit code 2",
                "exit code 3",
            ]
            has_err_indicators = any(err in out_str for err in err_indicators)
            is_failure = is_error or (has_err_indicators and out_bytes < 500)

            reads_to_process: list[tuple[str, str, str, Path]] = []
            effective_cwd = params.get("cwd") or params.get("Cwd") or params.get("workdir") or params.get("WorkDir")
            command_cwd = Path(str(effective_cwd)) if effective_cwd else repo_root
            if not command_cwd.is_absolute():
                command_cwd = repo_root / command_cwd

            # Read, Grep, and Glob each accept a path/root directly.  Audit
            # that root against the actual cwd used by the tool invocation.
            target_path = params.get("AbsolutePath") or params.get("file") or params.get("path") or params.get("TargetFile") or params.get("FilePath")
            direct_read_tools = ["read", "view", "section", "cat", "grep", "glob"]
            if target_path and any(k in tool_name.lower() for k in direct_read_tools):
                target_str = str(target_path)
                selector = params.get("heading") or params.get("selector") or "full_file"
                reads_to_process.append((target_str, str(selector), f"Tool execution: {tool_name}", command_cwd))

            # Check bash command read actions
            cmd_str = params.get("CommandLine") or params.get("command") or params.get("cmd")
            if cmd_str and any(k in tool_name.lower() for k in ["bash", "command", "shell", "exec", "terminal"]):
                bash_reads = parse_bash_read_commands(str(cmd_str))
                for b_path, b_sel in bash_reads:
                    reads_to_process.append((b_path, b_sel, f"Bash command: {str(cmd_str)[:60]}", command_cwd))

            for r_path, r_sel, r_reason, read_cwd in reads_to_process:
                in_allowed = is_path_in_allowed_set(r_path, inputs_list, support_list, repo_root, read_cwd)
                if not in_allowed:
                    if r_path not in reads_outside_allowed:
                        reads_outside_allowed.append(r_path)
                    disallowed_external_attempts.append({
                        "path": r_path,
                        "selector": r_sel,
                        "reason": f"Path outside allowed set: {r_path}",
                    })

                if is_failure:
                    outcome = "error"
                    if "FileNotFoundError" in out_str:
                        outcome = "FileNotFoundError"
                    elif "No such file or directory" in out_str:
                        outcome = "No such file or directory"
                    elif "SelectorNotFoundError" in out_str:
                        outcome = "SelectorNotFoundError"
                    elif "Permission denied" in out_str:
                        outcome = "Permission denied"
                    elif call.get("exit_code", 0) != 0:
                        outcome = f"exit_code_{call.get('exit_code')}"
                    elif call.get("error"):
                        outcome = str(call.get("error"))
                    else:
                        outcome = out_str.strip().splitlines()[0][:80] if out_str.strip() else "read_failed"

                    confinement_effect = "blocked" if ("Permission denied" in out_str or not in_allowed) else "none"

                    failed_read_attempts.append({
                        "path": r_path,
                        "outcome": outcome,
                        "bytes_delivered": 0,
                        "confinement_effect": confinement_effect,
                    })
                else:
                    # Check if output is read_section JSON
                    read_bytes = out_bytes
                    read_digest = compute_sha256(out_str)
                    actual_selector = r_sel

                    try:
                        parsed_json = json.loads(out_str)
                        if isinstance(parsed_json, dict) and "bytes" in parsed_json:
                            # read_section.py emits sha256 (not digest), bytes,
                            # and heading_path.  Prefer those canonical fields;
                            # retain legacy aliases for old transcripts.
                            read_digest = parsed_json.get("sha256", parsed_json.get("digest", read_digest))
                            read_bytes = int(parsed_json["bytes"])
                            actual_selector = parsed_json.get(
                                "heading_path", parsed_json.get("heading", actual_selector)
                            )
                    except Exception:
                        pass

                    observed_reads.append({
                        "path": r_path,
                        "selector": actual_selector,
                        "bytes": read_bytes,
                        "digest": read_digest,
                        "reason": r_reason,
                    })

    # Tool delivery ratio
    if raw_result_bytes > 0:
        tool_delivery_ratio = round(delivered_result_bytes / raw_result_bytes, 4)
    else:
        tool_delivery_ratio = None

    tokens_block = {
        "input_tokens": input_tokens if has_token_data else "not_observable",
        "cache_creation_input_tokens": cache_creation_input_tokens if has_token_data else "not_observable",
        "cache_read_input_tokens": cache_read_input_tokens if has_token_data else "not_observable",
        "output_tokens": output_tokens if has_token_data else "not_observable",
        "thinking_tokens": thinking_tokens if has_token_data else "not_observable",
    }

    # Retrieval Amplification (RA) metric (Section 5 of CONTEXT_POLICY.md)
    used_digests: Optional[set[str]] = None
    target_sources_path = sources_manifest_path or decision_path
    if target_sources_path:
        sp = Path(target_sources_path)
        if sp.is_file():
            try:
                s_data = json.loads(sp.read_text(encoding="utf-8"))
                sources_list = s_data.get("sources") or []
                used_digests = {s.get("digest") for s in sources_list if isinstance(s, dict) and "digest" in s}
            except Exception as exc:
                print(f"Warning: could not parse sources/decision: {exc}", file=sys.stderr)

    total_loaded_bytes = sum(r.get("bytes", 0) for r in observed_reads)
    if used_digests is not None:
        used_bytes = sum(r.get("bytes", 0) for r in observed_reads if r.get("digest") in used_digests)
        if used_bytes > 0:
            retrieval_amplification: Optional[float] = round(total_loaded_bytes / used_bytes, 4)
        else:
            retrieval_amplification = None
    else:
        if total_loaded_bytes > 0:
            unique_bytes = sum({r["digest"]: r.get("bytes", 0) for r in observed_reads if "digest" in r}.values())
            if unique_bytes > 0:
                retrieval_amplification = round(total_loaded_bytes / unique_bytes, 4)
            else:
                retrieval_amplification = None
        else:
            retrieval_amplification = None

    # Wrapper telemetry and divergence
    telemetry_divergence = None
    wrapper_telemetry_obj = None

    if wrapper_telemetry_path:
        wt_path = Path(wrapper_telemetry_path)
        if wt_path.is_file():
            try:
                raw_wt = wt_path.read_text(encoding="utf-8")
                telemetry_paths: set[str] = set()
                try:
                    wt_json = json.loads(raw_wt)
                    if isinstance(wt_json, dict):
                        wrapper_telemetry_obj = wt_json
                        for k in ["reads", "observed_reads", "paths", "events"]:
                            if k in wt_json and isinstance(wt_json[k], list):
                                for item in wt_json[k]:
                                    if isinstance(item, str):
                                        telemetry_paths.add(item)
                                    elif isinstance(item, dict) and "path" in item:
                                        telemetry_paths.add(item["path"])
                    elif isinstance(wt_json, list):
                        wrapper_telemetry_obj = {"events": wt_json}
                        for item in wt_json:
                            if isinstance(item, str):
                                telemetry_paths.add(item)
                            elif isinstance(item, dict) and "path" in item:
                                telemetr_path = item.get("path")
                                if telemetr_path:
                                    telemetry_paths.add(telemetr_path)
                except json.JSONDecodeError:
                    wrapper_telemetry_obj = {"raw_lines": len(raw_wt.splitlines())}
                    for w_line in raw_wt.splitlines():
                        w_line = w_line.strip()
                        if not w_line:
                            continue
                        try:
                            item = json.loads(w_line)
                            if isinstance(item, dict) and "path" in item:
                                telemetry_paths.add(item["path"])
                        except Exception:
                            pass

                transcript_paths = {r["path"] for r in observed_reads}
                in_transcript_not_in_telemetry = sorted(list(transcript_paths - telemetry_paths))
                in_telemetry_not_in_transcript = sorted(list(telemetry_paths - transcript_paths))
                divergence_count = len(in_transcript_not_in_telemetry) + len(in_telemetry_not_in_transcript)
                div_status = "aligned" if divergence_count == 0 else "divergent"

                telemetry_divergence = {
                    "status": div_status,
                    "divergence_count": divergence_count,
                    "in_transcript_not_in_telemetry": in_transcript_not_in_telemetry,
                    "in_telemetry_not_in_transcript": in_telemetry_not_in_transcript,
                }
            except Exception as exc:
                print(f"Warning: could not process wrapper telemetry: {exc}", file=sys.stderr)

    # Rotation observability is inert until an experiment supplies calibration.
    # T015 deliberately records no normative threshold defaults.
    applied_thresholds = {
        name: value
        for name, value in {
            "max_turns": max_turns,
            "max_tool_bytes": max_tool_bytes,
            "max_cache_tokens": max_cache_tokens,
        }.items()
        if value is not None
    }
    rotation_reasons = []
    if max_turns is not None and turn_count > max_turns:
        rotation_reasons.append(f"Turn count ({turn_count}) exceeds threshold ({max_turns}) for session compaction.")
    if max_tool_bytes is not None and raw_result_bytes > max_tool_bytes:
        rotation_reasons.append(f"Cumulative raw tool result bytes ({raw_result_bytes}) exceed threshold ({max_tool_bytes}).")
    if max_cache_tokens is not None and has_token_data and cache_read_input_tokens > max_cache_tokens:
        rotation_reasons.append(f"Accumulated cache_read ({cache_read_input_tokens}) exceeds threshold ({max_cache_tokens}).")

    rotation_recommended = bool(rotation_reasons)
    if not applied_thresholds:
        rotation_reason_text = "not_calibrated"
    else:
        rotation_reason_text = " ".join(rotation_reasons) if rotation_reasons else "Session metrics within configured bounds."

    # Pricing block
    pricing_block = {
        "basis": "official_task_proxy" if has_token_data else "unknown",
        "source": "docs/MODEL_ROUTING.md (proxy rubric)",
        "verified_at": "2026-09-11",
        "assumptions": [
            "Cache read priced at 10% of base input token price",
            "Cache creation priced at 1.25x of base input token price",
        ],
        "observed_tokens": (input_tokens + output_tokens) if has_token_data else None,
        "estimated_token_cost": round((input_tokens * 0.000003) + (output_tokens * 0.000015), 4) if has_token_data else None,
        "subscription_quota_impact": "unknown",
    }

    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    ledger: dict[str, Any] = {
        "schema_version": 1,
        "unit": unit,
        "phase": phase,
        "created_at": created_at,
        "turn_count": turn_count,
        "tool_calls": tool_calls_count,
        "tokens": tokens_block,
        "tool_metrics": {
            "raw_result_bytes": raw_result_bytes,
            "delivered_result_bytes": delivered_result_bytes,
            "tool_delivery_ratio": tool_delivery_ratio,
        },
        "retrieval_amplification": retrieval_amplification,
        "observed_reads": observed_reads,
        "failed_read_attempts": failed_read_attempts,
        "reads_outside_allowed_set": reads_outside_allowed,
        "disallowed_external_attempts": disallowed_external_attempts,
        "allowed_set": {
            "reference": allowed_set_ref,
            "inputs": inputs_list,
            "allowed_support": support_list,
        },
        "telemetry_divergence": telemetry_divergence,
        "pricing": pricing_block,
        "rotation": {
            "rotation_recommended": rotation_recommended,
            "reason": rotation_reason_text,
            "applied_thresholds": applied_thresholds,
        },
    }

    if wrapper_telemetry_obj is not None:
        ledger["wrapper_telemetry"] = wrapper_telemetry_obj

    is_valid, validation_errors = validate_context_ledger(ledger)
    if not is_valid:
        raise ValueError(f"Ledger violates schema: {validation_errors}")

    return ledger


def validate_context_ledger(ledger: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate ledger dictionary against schemas/context-ledger.schema.json rules.
    Returns (is_valid, list_of_errors).
    """
    errors: list[str] = []
    if not isinstance(ledger, dict):
        return False, ["Ledger must be a dictionary"]

    required_keys = [
        "schema_version", "unit", "phase", "created_at", "turn_count",
        "tool_calls", "tokens", "tool_metrics", "retrieval_amplification",
        "observed_reads", "failed_read_attempts", "reads_outside_allowed_set",
        "disallowed_external_attempts", "allowed_set", "telemetry_divergence",
        "pricing", "rotation"
    ]
    for k in required_keys:
        if k not in ledger:
            errors.append(f"Missing required field: {k}")

    if ledger.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    if not isinstance(ledger.get("unit"), str) or not ledger.get("unit"):
        errors.append("unit must be a non-empty string")

    valid_phases = {"planning", "implementation", "review", "rework", "debate"}
    if ledger.get("phase") not in valid_phases:
        errors.append(f"phase must be one of {valid_phases}")

    if not isinstance(ledger.get("created_at"), str) or not ledger.get("created_at"):
        errors.append("created_at must be a non-empty string")

    if not isinstance(ledger.get("turn_count"), int) or ledger.get("turn_count", 0) < 0:
        errors.append("turn_count must be a non-negative integer")

    if not isinstance(ledger.get("tool_calls"), int) or ledger.get("tool_calls", 0) < 0:
        errors.append("tool_calls must be a non-negative integer")

    # tokens
    tokens = ledger.get("tokens")
    if not isinstance(tokens, dict):
        errors.append("tokens must be an object")
    else:
        for tk in ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "thinking_tokens"]:
            val = tokens.get(tk)
            if not ((isinstance(val, int) and val >= 0) or val == "not_observable"):
                errors.append(f"tokens.{tk} must be non-negative integer or 'not_observable'")

    # tool_metrics
    tm = ledger.get("tool_metrics")
    if not isinstance(tm, dict):
        errors.append("tool_metrics must be an object")
    else:
        if not isinstance(tm.get("raw_result_bytes"), int) or tm.get("raw_result_bytes", 0) < 0:
            errors.append("tool_metrics.raw_result_bytes must be a non-negative integer")
        if not isinstance(tm.get("delivered_result_bytes"), int) or tm.get("delivered_result_bytes", 0) < 0:
            errors.append("tool_metrics.delivered_result_bytes must be a non-negative integer")
        tdr = tm.get("tool_delivery_ratio")
        if tdr is not None and not isinstance(tdr, (int, float)):
            errors.append("tool_metrics.tool_delivery_ratio must be a number or null")

    # retrieval_amplification
    ra = ledger.get("retrieval_amplification")
    if ra is not None and not isinstance(ra, (int, float)):
        errors.append("retrieval_amplification must be a number or null")

    # observed_reads
    obs = ledger.get("observed_reads")
    if not isinstance(obs, list):
        errors.append("observed_reads must be an array")
    else:
        for idx, entry in enumerate(obs):
            if not isinstance(entry, dict):
                errors.append(f"observed_reads[{idx}] must be an object")
                continue
            for rf in ["path", "selector", "bytes", "digest", "reason"]:
                if rf not in entry:
                    errors.append(f"observed_reads[{idx}] missing {rf}")
            if not isinstance(entry.get("bytes"), int) or entry.get("bytes", 0) < 0:
                errors.append(f"observed_reads[{idx}].bytes must be non-negative int")

    # failed_read_attempts
    failed = ledger.get("failed_read_attempts")
    if not isinstance(failed, list):
        errors.append("failed_read_attempts must be an array")
    else:
        for idx, entry in enumerate(failed):
            if not isinstance(entry, dict):
                errors.append(f"failed_read_attempts[{idx}] must be an object")
                continue
            for rf in ["path", "outcome", "bytes_delivered", "confinement_effect"]:
                if rf not in entry:
                    errors.append(f"failed_read_attempts[{idx}] missing {rf}")
            if not isinstance(entry.get("bytes_delivered"), int) or entry.get("bytes_delivered", 0) < 0:
                errors.append(f"failed_read_attempts[{idx}].bytes_delivered must be non-negative int")

    # reads_outside_allowed_set
    ro = ledger.get("reads_outside_allowed_set")
    if not isinstance(ro, list) or not all(isinstance(x, str) for x in ro):
        errors.append("reads_outside_allowed_set must be an array of strings")

    # disallowed_external_attempts
    dea = ledger.get("disallowed_external_attempts")
    if not isinstance(dea, list):
        errors.append("disallowed_external_attempts must be an array")
    else:
        for idx, entry in enumerate(dea):
            if isinstance(entry, str):
                continue
            elif isinstance(entry, dict):
                if not isinstance(entry.get("path"), str) or not entry.get("path"):
                    errors.append(f"disallowed_external_attempts[{idx}] must have a non-empty string 'path'")
            else:
                errors.append(f"disallowed_external_attempts[{idx}] must be string or object")

    # allowed_set
    al = ledger.get("allowed_set")
    if not isinstance(al, dict):
        errors.append("allowed_set must be an object")
    else:
        if not isinstance(al.get("inputs"), list) or not all(isinstance(x, str) for x in al.get("inputs", [])):
            errors.append("allowed_set.inputs must be an array of strings")
        if not isinstance(al.get("allowed_support"), list) or not all(isinstance(x, str) for x in al.get("allowed_support", [])):
            errors.append("allowed_set.allowed_support must be an array of strings")
        ref = al.get("reference")
        if ref is not None and not isinstance(ref, str):
            errors.append("allowed_set.reference must be a string or null")

    # telemetry_divergence
    td = ledger.get("telemetry_divergence")
    if td is not None and not isinstance(td, dict):
        errors.append("telemetry_divergence must be an object or null")

    # pricing
    pr = ledger.get("pricing")
    if not isinstance(pr, dict):
        errors.append("pricing must be an object")
    else:
        valid_basis = {"official_task_proxy", "token_price_only", "local_observed", "unknown"}
        if pr.get("basis") not in valid_basis:
            errors.append(f"pricing.basis must be one of {valid_basis}")
        if pr.get("subscription_quota_impact") != "unknown":
            errors.append("pricing.subscription_quota_impact must be 'unknown'")

    # rotation
    rot = ledger.get("rotation")
    if not isinstance(rot, dict):
        errors.append("rotation must be an object")
    else:
        if not isinstance(rot.get("rotation_recommended"), bool):
            errors.append("rotation.rotation_recommended must be a boolean")
        if not isinstance(rot.get("reason"), str) or not rot.get("reason"):
            errors.append("rotation.reason must be a non-empty string")

    return len(errors) == 0, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construct context ledger and rotation observability metrics from transcript JSONL."
    )
    parser.add_argument("--transcript", "-t", required=True, help="Path to transcript JSONL.")
    parser.add_argument("--output", "-o", help="Path to output ledger JSON (default: stdout).")
    parser.add_argument("--unit", "-u", default="T015", help="Unit identifier (e.g. T015).")
    parser.add_argument(
        "--phase",
        "-p",
        choices=["planning", "implementation", "review", "rework", "debate"],
        default="implementation",
        help="Phase of execution.",
    )
    parser.add_argument("--wrapper-telemetry", "-w", help="Optional wrapper telemetry log.")
    parser.add_argument("--allowed-inputs", nargs="*", default=[], help="Allowed input paths/prefixes.")
    parser.add_argument("--allowed-support", nargs="*", default=[], help="Allowed support paths/prefixes.")
    parser.add_argument("--allowed-set", help="Path to frozen allowed set JSON file.")
    parser.add_argument("--sources-manifest", help="Path to sources manifest JSON file.")
    parser.add_argument("--decision", help="Path to decision JSON file with sources.")
    parser.add_argument("--max-turns", type=int, help="Explicit turn threshold for rotation recommendation.")
    parser.add_argument("--max-tool-bytes", type=int, help="Explicit cumulative tool byte threshold.")
    parser.add_argument("--max-cache-tokens", type=int, help="Explicit accumulated cache read threshold.")
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.is_file():
        print(f"ERROR: transcript file does not exist: {transcript_path}", file=sys.stderr)
        sys.exit(1)

    wrapper_path = Path(args.wrapper_telemetry) if args.wrapper_telemetry else None
    allowed_set_path = Path(args.allowed_set) if args.allowed_set else None
    sources_path = Path(args.sources_manifest) if args.sources_manifest else None
    decision_path = Path(args.decision) if args.decision else None

    ledger = build_ledger_from_transcript(
        transcript_path=transcript_path,
        unit=args.unit,
        phase=args.phase,
        wrapper_telemetry_path=wrapper_path,
        allowed_inputs=args.allowed_inputs,
        allowed_support=args.allowed_support,
        allowed_set_path=allowed_set_path,
        sources_manifest_path=sources_path,
        decision_path=decision_path,
        max_turns=args.max_turns,
        max_tool_bytes=args.max_tool_bytes,
        max_cache_tokens=args.max_cache_tokens,
    )

    formatted = json.dumps(ledger, indent=2, sort_keys=True) + "\n"

    if args.output and args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted, encoding="utf-8")
    else:
        sys.stdout.write(formatted)

    sys.exit(0)


if __name__ == "__main__":
    main()
