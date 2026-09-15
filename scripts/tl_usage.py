#!/usr/bin/env python3
"""
tl_usage.py - Harness Usage Observation v1 (Codex).
Parses Codex rollout sessions in JSONL format and produces factual, deterministic,
read-only usage observations adhering to schemas/usage-observation.schema.json.
Pure Python standard library implementation.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_VERSION = 1
PARSER_VERSION = "1.0.0"
SOURCE_FORMAT = "codex_session_jsonl"
DERIVATION_ID_UNCACHED = "codex_v1_input_minus_cached"

SUPPORTED_CLI_VERSIONS = {"0.153.0", "0.153.4"}
SUPPORTED_FORMAT_FINGERPRINTS = {"d06994c44db0b498", "50107c10084f33f2", "487c9d7026a20365"}

MAX_REASONS_CAP = 50
MAX_RATE_LIMITS_CAP = 50
MAX_THREADS_CAP = 100
MAX_CONTEXTS_CAP = 50
MAX_EVENT_TYPES_CAP = 20
MAX_CORRELATIONS_CAP = 50
MAX_IDENTITY_LEDGER_CAP = 100

RULE_ID_CODEX_0_153_4 = "codex-0.153.4-structural-event-dedup-v1"

CLAUDE_SOURCE_FORMAT = "claude_session_jsonl"
SUPPORTED_CLAUDE_CLI_VERSIONS = {"2.1.257"}
CLAUDE_CANONICAL_ASSISTANT_PATHS = [
    "message.id",
    "message.model",
    "message.role",
    "message.usage.cache_creation_input_tokens",
    "message.usage.cache_read_input_tokens",
    "message.usage.input_tokens",
    "message.usage.output_tokens",
    "sessionId",
    "type",
    "uuid",
]
CLAUDE_CANONICAL_FINGERPRINT = "b3140fe31bd7968a"
RULE_ID_CLAUDE_CODE_V1 = "rule_claude_code_v1"
MAX_CLAUDE_IDENTITY_CAP = 100
MAX_CLAUDE_RECORDS_CAP = 50
MAX_CLAUDE_COMPACTIONS_CAP = 50
MAX_CLAUDE_TOOL_USE_IDS_CAP = 100
MAX_CLAUDE_NEGATIVE_MARKERS_CAP = 10
MAX_CLAUDE_VERSIONS_CAP = 10
MAX_CLAUDE_THREADS_CAP = 50
MAX_CLAUDE_SUBAGENTS_CAP = 50
MAX_CLAUDE_CONTEXT_STATS_CAP = 50

CLAUDE_COUNTER_FIELDS = [
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "thinking_tokens",
]
CANONICAL_COUNTER_FIELDS = [
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
]


def is_supported_harness_version(ver: Optional[str]) -> bool:
    if not ver or not isinstance(ver, str):
        return False
    return ver in SUPPORTED_CLI_VERSIONS


def has_nested_path(d: Any, path: str) -> bool:
    parts = path.split(".")
    curr = d
    for p in parts:
        if not isinstance(curr, dict) or p not in curr:
            return False
        curr = curr[p]
    return True


def sanitize_rate_limit_bucket(bucket: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(bucket, dict):
        return None
    used = bucket.get("used_percent")
    win = bucket.get("window_minutes")
    res = bucket.get("resets_at")

    used_val = float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) and 0 <= used <= 100 else None
    win_val = float(win) if isinstance(win, (int, float)) and not isinstance(win, bool) and win >= 0 else None
    res_val = float(res) if isinstance(res, (int, float)) and not isinstance(res, bool) and res >= 0 else None

    return {
        "used_percent": used_val,
        "window_minutes": win_val,
        "resets_at": res_val,
    }


def sanitize_rate_limit(rl: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(rl, dict):
        return None
    limit_id = rl.get("limit_id")
    limit_name = rl.get("limit_name")
    plan_type = rl.get("plan_type")

    lid_str = str(limit_id) if isinstance(limit_id, (str, int)) and not isinstance(limit_id, bool) else None
    lname_str = str(limit_name) if isinstance(limit_name, str) else None
    plan_str = str(plan_type) if isinstance(plan_type, str) else None

    prim = sanitize_rate_limit_bucket(rl.get("primary"))
    sec = sanitize_rate_limit_bucket(rl.get("secondary"))

    return {
        "scope": "account",
        "attribution": "unknown",
        "limit_id": lid_str,
        "limit_name": lname_str,
        "primary": prim,
        "secondary": sec,
        "plan_type": plan_str,
    }


def compute_sha256(filepath: str) -> str:
    """Compute hex SHA-256 digest of a file in binary read-only mode."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def parse_iso_timestamp(ts_str: Optional[str]) -> Optional[datetime.datetime]:
    if not ts_str or not isinstance(ts_str, str):
        return None
    s = ts_str.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def format_counter(val: Any) -> Any:
    """Format token counter: strictly integer >= 0 or 'not_observable'.

    Categorically rejects booleans, floats, strings, negative numbers, None, etc.
    """
    if isinstance(val, bool):
        return "not_observable"
    if isinstance(val, int) and val >= 0:
        return val
    return "not_observable"


def reconcile_field(cum_val: Any, per_val: Any) -> Dict[str, Any]:
    """Reconcile a single homologous field between cumulative and per-response sum."""
    c_fmt = format_counter(cum_val)
    p_fmt = format_counter(per_val)

    if c_fmt == "not_observable" or p_fmt == "not_observable":
        return {
            "status": "not_observable",
            "cumulative_value": c_fmt,
            "per_response_value": p_fmt,
            "delta": None,
        }

    delta = c_fmt - p_fmt
    status = "reconciled" if delta == 0 else "divergent"
    return {
        "status": status,
        "cumulative_value": c_fmt,
        "per_response_value": p_fmt,
        "delta": delta,
    }


def is_recognized_codex_event(record: Dict[str, Any]) -> bool:
    """Check if record matches known Codex rollout event structure and types."""
    if not isinstance(record, dict):
        return False
    rec_type = record.get("type")
    if not isinstance(rec_type, str):
        return False

    payload = record.get("payload")
    if not isinstance(payload, dict):
        return False

    if rec_type == "session_meta":
        return bool(payload.get("id") or payload.get("session_id"))

    if rec_type == "turn_context":
        return bool(
            payload.get("turn_id")
            or payload.get("model")
            or payload.get("effort")
            or payload.get("reasoning_effort")
        )

    if rec_type == "token_usage_record":
        usage = payload.get("usage")
        return isinstance(usage, dict) or any(
            k in payload for k in ("input_tokens", "output_tokens", "total_tokens")
        )

    if rec_type == "token_count":
        info = payload.get("info")
        return isinstance(info, dict) or isinstance(payload.get("usage"), dict) or any(
            k in payload for k in ("total_token_usage", "last_token_usage", "input_tokens", "total_tokens")
        )

    if rec_type == "response_item":
        return isinstance(payload, dict)

    if rec_type == "event_msg":
        p_type = payload.get("type")
        if not isinstance(p_type, str):
            return False
        known_event_msg_types = (
            "token_count",
            "task_started",
            "task_complete",
            "session_complete",
            "session_end",
            "item_completed",
            "turn_start",
            "turn_complete",
            "agent_message",
            "user_message",
        )
        if p_type not in known_event_msg_types:
            return False
        if p_type == "token_count":
            info = payload.get("info")
            rl = payload.get("rate_limits")
            return isinstance(info, dict) or isinstance(rl, dict)
        return True

    if rec_type == "world_state":
        return isinstance(payload, dict)

    return False


def resolve_schema(schema_node: Dict[str, Any], root_schema: Dict[str, Any]) -> Dict[str, Any]:
    current = schema_node
    while isinstance(current, dict) and "$ref" in current:
        ref = current["$ref"]
        if ref.startswith("#/"):
            parts = ref[2:].split("/")
            curr = root_schema
            for p in parts:
                curr = curr[p]
            current = curr
        else:
            raise ValueError(f"Unsupported non-local $ref: {ref}")
    return current


def validate_value(val: Any, subschema: Dict[str, Any], root_schema: Dict[str, Any], path: str = "$") -> List[str]:
    errors: List[str] = []
    subschema = resolve_schema(subschema, root_schema)

    # 1. oneOf
    if "oneOf" in subschema:
        matched = 0
        branch_errors = []
        for idx, branch in enumerate(subschema["oneOf"]):
            errs = validate_value(val, branch, root_schema, f"{path}[oneOf:{idx}]")
            if not errs:
                matched += 1
            else:
                branch_errors.append(f"branch_{idx}: {'; '.join(errs)}")
        if matched != 1:
            errors.append(
                f"{path}: expected exactly one matching branch in oneOf, matched {matched}. ({', '.join(branch_errors)})"
            )
        return errors

    # 2. const
    if "const" in subschema:
        expected = subschema["const"]
        if isinstance(expected, bool) != isinstance(val, bool) or val != expected:
            errors.append(f"{path}: expected const {expected!r}, got {val!r}")
            return errors

    # 3. enum
    if "enum" in subschema:
        allowed = subschema["enum"]
        match_found = False
        for item in allowed:
            if isinstance(item, bool) == isinstance(val, bool) and val == item:
                match_found = True
                break
        if not match_found:
            errors.append(f"{path}: value {val!r} not in enum {allowed}")
            return errors

    # 4. type
    if "type" in subschema:
        t_decl = subschema["type"]
        allowed_types = [t_decl] if isinstance(t_decl, str) else t_decl
        type_ok = False
        for t in allowed_types:
            if t == "object" and isinstance(val, dict):
                type_ok = True
                break
            elif t == "array" and isinstance(val, list):
                type_ok = True
                break
            elif t == "string" and isinstance(val, str):
                type_ok = True
                break
            elif t == "integer" and isinstance(val, int) and not isinstance(val, bool):
                type_ok = True
                break
            elif t == "number" and isinstance(val, (int, float)) and not isinstance(val, bool):
                type_ok = True
                break
            elif t == "boolean" and isinstance(val, bool):
                type_ok = True
                break
            elif t == "null" and val is None:
                type_ok = True
                break

        if not type_ok:
            errors.append(f"{path}: expected type {t_decl}, got {type(val).__name__} ({val!r})")
            return errors

    # 5. string constraints
    if isinstance(val, str):
        if "minLength" in subschema and len(val) < subschema["minLength"]:
            errors.append(f"{path}: string length {len(val)} < minLength {subschema['minLength']}")
        if "pattern" in subschema and not re.match(subschema["pattern"], val):
            errors.append(f"{path}: string {val!r} does not match pattern {subschema['pattern']!r}")

    # 6. number/integer constraints
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if "minimum" in subschema and val < subschema["minimum"]:
            errors.append(f"{path}: value {val} < minimum {subschema['minimum']}")

    # 7. array constraints
    if isinstance(val, list) and "items" in subschema:
        item_schema = subschema["items"]
        for i, elem in enumerate(val):
            errors.extend(validate_value(elem, item_schema, root_schema, f"{path}[{i}]"))

    # 8. object constraints
    if isinstance(val, dict):
        if "required" in subschema:
            for req_prop in subschema["required"]:
                if req_prop not in val:
                    errors.append(f"{path}: missing required property '{req_prop}'")

        props_schema = subschema.get("properties", {})
        if subschema.get("additionalProperties") is False:
            for k in val.keys():
                if k not in props_schema:
                    errors.append(f"{path}: unexpected additional property '{k}'")

        for k, prop_val in val.items():
            if k in props_schema:
                errors.extend(validate_value(prop_val, props_schema[k], root_schema, f"{path}.{k}"))

    return errors


def validate_against_schema(data: Any, schema_path: str) -> Tuple[bool, List[str]]:
    """Validate data against Draft 2020-12 schema using pure Python standard library."""
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    errors = validate_value(data, schema, schema, path="$")
    return (len(errors) == 0, errors)


def enforce_schema_validation(observation: Dict[str, Any]) -> Dict[str, Any]:
    """Mandatory unconditional validation against schemas/usage-observation.schema.json.

    Fails closed (raising FileNotFoundError or ValueError) if schema file is missing,
    unreadable, or observation does not conform.
    """
    repo_root = Path(__file__).resolve().parent.parent
    schema_file = repo_root / "schemas" / "usage-observation.schema.json"
    if not schema_file.exists():
        raise FileNotFoundError(f"Mandatory schema contract missing: {schema_file}")

    valid, errs = validate_against_schema(observation, str(schema_file))
    if not valid:
        raise ValueError(f"Generated observation violates schema Draft 2020-12: {errs}")
    return observation


def parse_codex_rollout(session_path: str, run_id: str) -> Dict[str, Any]:
    """Parse a Codex session JSONL file and extract factual usage observation."""
    if not os.path.exists(session_path):
        raise FileNotFoundError(f"Session file not found: {session_path}")
    if os.path.isdir(session_path):
        raise IsADirectoryError(f"Session path is a directory: {session_path}")

    hasher = hashlib.sha256()

    session_id: Optional[str] = None
    harness_version: Optional[str] = None

    first_valid_dt: Optional[datetime.datetime] = None
    first_valid_ts_str: Optional[str] = None
    last_valid_dt: Optional[datetime.datetime] = None
    last_valid_ts_str: Optional[str] = None

    parser_reasons: List[str] = []
    completeness_reasons: List[str] = []
    syntax_error_encountered = False
    truncated_line_encountered = False
    unrecognized_event_encountered = False
    first_unrecognized_reason: Optional[str] = None
    terminal_event_observed = False
    recognized_events_count = 0
    total_valid_json_count = 0

    has_structural_session_meta = False
    has_structural_turn_context = False
    has_usage_counters = False

    current_turn_id: Optional[str] = None
    current_model: Optional[str] = None
    current_effort: Optional[str] = None
    active_turn_id: Optional[str] = None
    active_turn_key: Optional[Tuple[Optional[str], Optional[str]]] = None

    threads_data: Dict[str, Dict[str, Any]] = {}
    thread_order: List[str] = []

    counter_fields = [
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ]

    # R5 & R12: Bounded O(1) memory aggregation and retention caps
    latest_cum: Dict[str, Any] = {}
    per_resp_sums: Dict[str, int] = {f: 0 for f in counter_fields}
    per_resp_observed: Dict[str, bool] = {f: False for f in counter_fields}
    response_count: int = 0
    context_stats: Dict[Tuple[Optional[str], Optional[str]], Dict[str, Any]] = {}

    rate_limits_by_id: Dict[str, Dict[str, Any]] = {}
    seen_event_types: set[str] = set()

    pending_decode_error: Optional[Tuple[int, str, json.JSONDecodeError]] = None

    # R19: Collection cap truncation tracking
    contexts_cap_exceeded = False
    threads_cap_exceeded = False
    rate_limits_cap_exceeded = False

    # T026: Raw usage channels tracking
    token_usage_records_count: int = 0
    token_usage_records_sums: Dict[str, int] = {f: 0 for f in counter_fields}
    token_usage_records_observed: Dict[str, bool] = {f: False for f in counter_fields}

    event_msg_token_counts_count: int = 0
    event_msg_token_counts_sums: Dict[str, int] = {f: 0 for f in counter_fields}
    event_msg_token_counts_observed: Dict[str, bool] = {f: False for f in counter_fields}

    cumulative_snapshots_count: int = 0
    latest_cumulative_snapshot: Dict[str, Any] = {f: "not_observable" for f in counter_fields}

    # T026: Semantic correlation & normalization tracking (R2 & R3: bounded identity ledger)
    identity_ledger: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

    semantic_correlations_records: List[Dict[str, Any]] = []
    records_observed_count: int = 0
    records_overflow_count: int = 0
    correlated_events_count: int = 0
    ambiguous_events_count: int = 0
    unmatched_events_count: int = 0

    semantic_response_count: int = 0
    semantic_per_resp_sums: Dict[str, int] = {f: 0 for f in counter_fields}
    semantic_per_resp_observed: Dict[str, bool] = {f: False for f in counter_fields}

    has_ambiguous_identity: bool = False
    has_conflicting_identity: bool = False
    structural_ineligibility_reasons: List[str] = []

    def append_reason(reasons_list: List[str], reason: str) -> None:
        if len(reasons_list) < MAX_REASONS_CAP - 1:
            reasons_list.append(reason)
        elif len(reasons_list) == MAX_REASONS_CAP - 1:
            reasons_list.append("additional_reasons_truncated")

    def finalize_parser_reasons(
        base_reasons: List[str],
        mandatory_priorities: List[str],
    ) -> List[str]:
        """R22: Explicitly preserve all mandatory priority reasons without substring heuristics
        or positional overwrites, strictly capped at MAX_REASONS_CAP (50) with truncation marker.
        """
        # 1. Deduplicate mandatory priorities preserving insertion order
        priorities: List[str] = []
        for p in mandatory_priorities:
            if p and p not in priorities:
                priorities.append(p)

        # 2. Track whether truncation occurred in base_reasons and filter base_reasons
        had_truncation = "additional_reasons_truncated" in base_reasons
        filtered_base: List[str] = []
        for r in base_reasons:
            if r and r not in priorities and r not in filtered_base and r != "additional_reasons_truncated":
                filtered_base.append(r)

        total_needed = len(filtered_base) + len(priorities)
        if not had_truncation and total_needed <= MAX_REASONS_CAP:
            return filtered_base + priorities

        # Must truncate to fit MAX_REASONS_CAP. Reserve 1 slot for marker and len(priorities) slots
        slots_for_base = max(0, MAX_REASONS_CAP - 1 - len(priorities))
        truncated_base = filtered_base[:slots_for_base]
        return truncated_base + priorities + ["additional_reasons_truncated"]

    def commit_pending_error_as_syntax(err_tuple: Tuple[int, str, json.JSONDecodeError]) -> None:
        nonlocal syntax_error_encountered
        syntax_error_encountered = True
        idx, _, exc = err_tuple
        append_reason(completeness_reasons, f"json_syntax_error_line_{idx}:{exc.msg}")

    def register_turn(new_turn_id: Optional[str]) -> None:
        nonlocal active_turn_id, active_turn_key, current_turn_id, contexts_cap_exceeded
        if not new_turn_id:
            return
        current_turn_id = new_turn_id
        ctx_key = (current_model, current_effort)
        if active_turn_id != new_turn_id:
            active_turn_id = new_turn_id
            active_turn_key = ctx_key
            if ctx_key not in context_stats:
                if len(context_stats) < MAX_CONTEXTS_CAP:
                    context_stats[ctx_key] = {
                        "turn_count": 0,
                        "sums": {f: 0 for f in counter_fields},
                        "observed": {f: False for f in counter_fields},
                    }
                else:
                    contexts_cap_exceeded = True
            if ctx_key in context_stats:
                context_stats[ctx_key]["turn_count"] += 1
        elif active_turn_key != ctx_key:
            if active_turn_key in context_stats and context_stats[active_turn_key]["turn_count"] > 0:
                context_stats[active_turn_key]["turn_count"] -= 1
                if context_stats[active_turn_key]["turn_count"] == 0 and not any(context_stats[active_turn_key]["observed"].values()):
                    del context_stats[active_turn_key]
            if ctx_key not in context_stats:
                if len(context_stats) < MAX_CONTEXTS_CAP:
                    context_stats[ctx_key] = {
                        "turn_count": 0,
                        "sums": {f: 0 for f in counter_fields},
                        "observed": {f: False for f in counter_fields},
                    }
                else:
                    contexts_cap_exceeded = True
            if ctx_key in context_stats:
                context_stats[ctx_key]["turn_count"] += 1
            active_turn_key = ctx_key

    def process_delta(delta: Dict[str, Any]) -> None:
        nonlocal response_count, has_usage_counters, contexts_cap_exceeded
        if not isinstance(delta, dict):
            return
        response_count += 1
        has_usage_counters = True

        for f in counter_fields:
            val = delta.get(f)
            if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                per_resp_sums[f] += val
                per_resp_observed[f] = True

        ctx_key = (current_model, current_effort)
        if ctx_key not in context_stats:
            if len(context_stats) < MAX_CONTEXTS_CAP:
                context_stats[ctx_key] = {
                    "turn_count": 1,
                    "sums": {f: 0 for f in counter_fields},
                    "observed": {f: False for f in counter_fields},
                }
            else:
                contexts_cap_exceeded = True
        if ctx_key in context_stats:
            for f in counter_fields:
                val = delta.get(f)
                if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                    context_stats[ctx_key]["sums"][f] += val
                    context_stats[ctx_key]["observed"][f] = True

    # R9: Streaming single-pass line-by-line reading + hashing on the same open descriptor
    with open(session_path, "rb") as bf:
        for line_idx, raw_bytes in enumerate(bf, start=1):
            hasher.update(raw_bytes)
            raw_line = raw_bytes.decode("utf-8", errors="replace")
            stripped = raw_line.strip()
            if not stripped:
                continue

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if pending_decode_error is not None:
                    commit_pending_error_as_syntax(pending_decode_error)
                pending_decode_error = (line_idx, raw_line, exc)
                continue

            if pending_decode_error is not None:
                commit_pending_error_as_syntax(pending_decode_error)
                pending_decode_error = None

            if not isinstance(data, dict):
                syntax_error_encountered = True
                append_reason(parser_reasons, f"line_{line_idx}_not_a_json_object")
                continue

            total_valid_json_count += 1
            rec_type = data.get("type")
            if rec_type and isinstance(rec_type, str):
                if len(seen_event_types) < MAX_EVENT_TYPES_CAP:
                    seen_event_types.add(rec_type)

                if is_recognized_codex_event(data):
                    recognized_events_count += 1
                else:
                    unrecognized_event_encountered = True
                    if rec_type == "event_msg" and isinstance(data.get("payload"), dict):
                        subtype = str(data.get("payload", {}).get("type"))
                        unrec_r = f"unrecognized_event_msg_subtype:{subtype}"
                    else:
                        unrec_r = f"unrecognized_event_structure:{rec_type}"
                    if first_unrecognized_reason is None:
                        first_unrecognized_reason = unrec_r
                    append_reason(parser_reasons, unrec_r)

            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            # R7: Parse timestamp strictly; ignore invalid timestamps
            raw_ts = data.get("timestamp")
            if isinstance(raw_ts, str) and raw_ts:
                dt = parse_iso_timestamp(raw_ts)
                if dt is not None:
                    if first_valid_dt is None:
                        first_valid_dt = dt
                        first_valid_ts_str = raw_ts
                    last_valid_dt = dt
                    last_valid_ts_str = raw_ts

            if rec_type == "session_meta":
                has_structural_session_meta = True
                sess_id = payload.get("session_id") or payload.get("id")
                if session_id is None and sess_id is not None:
                    session_id = str(sess_id) if isinstance(sess_id, (str, int)) and not isinstance(sess_id, bool) else None
                h_ver = payload.get("cli_version")
                if harness_version is None and h_ver is not None:
                    harness_version = str(h_ver) if isinstance(h_ver, (str, int)) and not isinstance(h_ver, bool) else None

                t_id = payload.get("id")
                p_id = payload.get("parent_thread_id")
                agent_role = payload.get("agent_role")

                t_id_str = str(t_id) if isinstance(t_id, str) else None
                p_id_str = str(p_id) if isinstance(p_id, str) else None
                role_str = str(agent_role) if isinstance(agent_role, str) else None

                if t_id_str:
                    if t_id_str not in threads_data:
                        if len(threads_data) < MAX_THREADS_CAP:
                            threads_data[t_id_str] = {
                                "thread_id": t_id_str,
                                "parent_thread_id": p_id_str,
                                "agent_role": role_str,
                                "turn_count": 0,
                            }
                            thread_order.append(t_id_str)
                        else:
                            threads_cap_exceeded = True
                    else:
                        threads_data[t_id_str]["parent_thread_id"] = p_id_str
                        if role_str:
                            threads_data[t_id_str]["agent_role"] = role_str

                if p_id_str and p_id_str not in threads_data:
                    if len(threads_data) < MAX_THREADS_CAP:
                        threads_data[p_id_str] = {
                            "thread_id": p_id_str,
                            "parent_thread_id": None,
                            "agent_role": None,
                            "turn_count": 0,
                        }
                        thread_order.append(p_id_str)
                    else:
                        threads_cap_exceeded = True

            elif rec_type == "turn_context":
                has_structural_turn_context = True
                t_id = payload.get("turn_id")
                new_m = payload.get("model")
                new_eff = payload.get("effort") or payload.get("reasoning_effort")
                if new_m is not None:
                    current_model = str(new_m) if isinstance(new_m, str) else None
                if new_eff is not None:
                    current_effort = str(new_eff) if isinstance(new_eff, str) else None
                register_turn(str(t_id) if isinstance(t_id, str) else current_turn_id)

            elif rec_type == "event_msg":
                msg_type = payload.get("type")
                msg_turn_id = payload.get("turn_id")
                if msg_turn_id:
                    register_turn(str(msg_turn_id) if isinstance(msg_turn_id, str) else None)

                if msg_type in ("task_complete", "session_complete", "session_end"):
                    terminal_event_observed = True

                elif msg_type == "token_count":
                    info = payload.get("info", {})
                    if isinstance(info, dict):
                        tot = info.get("total_token_usage")
                        if isinstance(tot, dict):
                            latest_cum = {k: format_counter(tot[k]) for k in counter_fields if k in tot}
                            has_usage_counters = True
                            cumulative_snapshots_count += 1
                            latest_cumulative_snapshot = {k: format_counter(tot.get(k)) for k in counter_fields}

                        last = info.get("last_token_usage")
                        if isinstance(last, dict):
                            process_delta(last)
                            event_msg_token_counts_count += 1
                            for f in counter_fields:
                                val = last.get(f)
                                if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                                    event_msg_token_counts_sums[f] += val
                                    event_msg_token_counts_observed[f] = True

                    rl = payload.get("rate_limits")
                    sanitized_rl = sanitize_rate_limit(rl)
                    if sanitized_rl:
                        lid = sanitized_rl.get("limit_id") or "default"
                        if lid in rate_limits_by_id:
                            rate_limits_by_id[lid] = sanitized_rl
                        elif len(rate_limits_by_id) < MAX_RATE_LIMITS_CAP:
                            rate_limits_by_id[lid] = sanitized_rl
                        else:
                            rate_limits_cap_exceeded = True

                    # T026 (R1 & R2): event_msg(token_count) is an unkeyed UI telemetry/snapshot channel.
                    # It has no response_id; per I21, it is strictly not associated to response_id by adjacency.

            elif rec_type == "token_usage_record":
                usage = payload.get("usage")
                t_id = payload.get("thread_id")
                turn_id = payload.get("turn_id")
                response_id = payload.get("response_id")

                t_id_str = str(t_id) if isinstance(t_id, (str, int)) and not isinstance(t_id, bool) else None
                turn_id_str = str(turn_id) if isinstance(turn_id, (str, int)) and not isinstance(turn_id, bool) else None

                if turn_id:
                    register_turn(turn_id_str)
                if t_id and t_id in threads_data:
                    threads_data[t_id]["turn_count"] += 1
                if isinstance(usage, dict):
                    process_delta(usage)

                # T026: Channel accounting for token_usage_records
                if isinstance(usage, dict):
                    token_usage_records_count += 1
                    for f in counter_fields:
                        val = usage.get(f)
                        if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                            token_usage_records_sums[f] += val
                            token_usage_records_observed[f] = True

                # T026: Structural correlation & identity validation
                is_valid_resp_id = isinstance(response_id, str) and bool(response_id.strip())
                if not is_valid_resp_id:
                    # In Codex 0.153.4, missing response_id is ambiguous (Classe C)
                    if harness_version == "0.153.4":
                        has_ambiguous_identity = True
                        ambiguous_events_count += 1
                        records_observed_count += 1
                        reason = "ambiguous_usage_event_identity:missing_response_id"
                        if reason not in structural_ineligibility_reasons:
                            structural_ineligibility_reasons.append(reason)
                        if len(semantic_correlations_records) < MAX_CORRELATIONS_CAP:
                            semantic_correlations_records.append({
                                "correlation_id": f"ambiguous_token_usage_record_line_{line_idx}",
                                "status": "ambiguous",
                                "strategy": "none",
                                "response_id": None,
                                "turn_id": turn_id_str,
                                "thread_id": t_id_str,
                                "channels": ["token_usage_record"],
                                "counters": {f: format_counter(usage.get(f)) if isinstance(usage, dict) else "not_observable" for f in counter_fields},
                                "reasons": [reason],
                            })
                        else:
                            records_overflow_count += 1
                else:
                    resp_id_str = str(response_id).strip()
                    # Check for conflicting identity (Classe F)
                    if resp_id_str in identity_ledger:
                        prev_turn, prev_thread = identity_ledger[resp_id_str]
                        if (turn_id_str is not None and prev_turn is not None and turn_id_str != prev_turn) or (t_id_str is not None and prev_thread is not None and t_id_str != prev_thread):
                            # Conflicting reuse of response_id across different turns/threads (Classe F)
                            has_conflicting_identity = True
                            ambiguous_events_count += 1
                            records_observed_count += 1
                            conflict_r = "conflicting_structural_identity:response_id_reused_with_different_turn_or_thread"
                            if conflict_r not in structural_ineligibility_reasons:
                                structural_ineligibility_reasons.append(conflict_r)
                            if len(semantic_correlations_records) < MAX_CORRELATIONS_CAP:
                                semantic_correlations_records.append({
                                    "correlation_id": f"{resp_id_str}_conflict_line_{line_idx}",
                                    "status": "ambiguous",
                                    "strategy": "none",
                                    "response_id": resp_id_str,
                                    "turn_id": turn_id_str,
                                    "thread_id": t_id_str,
                                    "channels": ["token_usage_record"],
                                    "counters": {f: format_counter(usage.get(f)) if isinstance(usage, dict) else "not_observable" for f in counter_fields},
                                    "reasons": [conflict_r],
                                })
                            else:
                                records_overflow_count += 1
                        else:
                            # Proven structural duplicate in same turn cycle (Classe A)
                            correlated_events_count += 1
                            records_observed_count += 1
                            for rec in semantic_correlations_records:
                                if rec.get("correlation_id") == resp_id_str:
                                    rec["channels"].append("token_usage_record")
                                    rec["reasons"].append("duplicate_token_usage_record_correlated_exact_identity")
                                    break
                    else:
                        # New distinct response event!
                        if len(identity_ledger) < MAX_IDENTITY_LEDGER_CAP:
                            identity_ledger[resp_id_str] = (turn_id_str, t_id_str)
                            correlated_events_count += 1
                            records_observed_count += 1
                            semantic_response_count += 1
                            resp_counters = {}
                            if isinstance(usage, dict):
                                for f in counter_fields:
                                    val = usage.get(f)
                                    if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                                        semantic_per_resp_sums[f] += val
                                        semantic_per_resp_observed[f] = True
                                        resp_counters[f] = val
                                    else:
                                        resp_counters[f] = "not_observable"
                            else:
                                resp_counters = {f: "not_observable" for f in counter_fields}

                            rec_data = {
                                "correlation_id": resp_id_str,
                                "status": "correlated",
                                "strategy": "exact_identity",
                                "response_id": resp_id_str,
                                "turn_id": turn_id_str,
                                "thread_id": t_id_str,
                                "channels": ["token_usage_record"],
                                "counters": resp_counters,
                                "reasons": ["exact_response_id_registered"],
                            }
                            if len(semantic_correlations_records) < MAX_CORRELATIONS_CAP:
                                semantic_correlations_records.append(rec_data)
                            else:
                                records_overflow_count += 1
                        else:
                            # R3: Bounded memory cap on identity ledger exceeded
                            has_ambiguous_identity = True
                            ambiguous_events_count += 1
                            records_observed_count += 1
                            cap_r = f"identity_ledger_cap_exceeded:{MAX_IDENTITY_LEDGER_CAP}"
                            if cap_r not in structural_ineligibility_reasons:
                                structural_ineligibility_reasons.append(cap_r)
                            if len(semantic_correlations_records) < MAX_CORRELATIONS_CAP:
                                semantic_correlations_records.append({
                                    "correlation_id": f"ledger_overflow_{resp_id_str}",
                                    "status": "ambiguous",
                                    "strategy": "none",
                                    "response_id": resp_id_str,
                                    "turn_id": turn_id_str,
                                    "thread_id": t_id_str,
                                    "channels": ["token_usage_record"],
                                    "counters": {f: format_counter(usage.get(f)) if isinstance(usage, dict) else "not_observable" for f in counter_fields},
                                    "reasons": [cap_r],
                                })
                            else:
                                records_overflow_count += 1


            # Track thread references from payload
            ref_t_id = payload.get("thread_id")
            if ref_t_id and isinstance(ref_t_id, str):
                if ref_t_id not in threads_data:
                    if len(threads_data) < MAX_THREADS_CAP:
                        threads_data[ref_t_id] = {
                            "thread_id": ref_t_id,
                            "parent_thread_id": None,
                            "agent_role": None,
                            "turn_count": 0,
                        }
                        thread_order.append(ref_t_id)
                    else:
                        threads_cap_exceeded = True

    file_digest = hasher.hexdigest()
    rate_limits_extracted = list(rate_limits_by_id.values())

    # Handle final pending decode error at EOF
    if pending_decode_error is not None:
        p_idx, p_raw, p_exc = pending_decode_error
        is_truncated = (
            not p_raw.endswith("\n")
            or "Unterminated" in p_exc.msg
            or "unterminated" in p_exc.msg.lower()
            or "Expecting" in p_exc.msg
        )
        if is_truncated:
            truncated_line_encountered = True
            append_reason(completeness_reasons, f"truncated_line_at_line_{p_idx}:{p_exc.msg}")
        else:
            syntax_error_encountered = True
            append_reason(completeness_reasons, f"json_syntax_error_line_{p_idx}:{p_exc.msg}")
        pending_decode_error = None

    # Format fingerprint
    fingerprint_seed = f"{SOURCE_FORMAT}:{sorted(list(seen_event_types))}"
    format_fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:16]

    # R3 & R18: Format recognition & structural landmarks validation
    has_legitimate_landmarks = has_structural_session_meta or (
        has_structural_turn_context and has_usage_counters
    )

    if recognized_events_count == 0 or not has_legitimate_landmarks:
        if total_valid_json_count == 0:
            return build_empty_or_unsupported_observation(
                run_id=run_id,
                session_ref_digest=file_digest,
                parser_status="unsupported",
                parser_reasons=["empty_or_completely_unparseable_file"],
                completeness_status="incomplete",
                completeness_reasons=completeness_reasons or ["no_valid_json_lines"],
                source_format_fingerprint=format_fingerprint,
            )
        elif unrecognized_event_encountered:
            mandatory_priorities: List[str] = []
            if first_unrecognized_reason:
                mandatory_priorities.append(first_unrecognized_reason)
            else:
                mandatory_priorities.append("unrecognized_event_or_subtype_in_stream")
            if contexts_cap_exceeded:
                mandatory_priorities.append(f"observed_contexts_cap_exceeded:{MAX_CONTEXTS_CAP}")
            if threads_cap_exceeded:
                mandatory_priorities.append(f"threads_topology_cap_exceeded:{MAX_THREADS_CAP}")
            if rate_limits_cap_exceeded:
                mandatory_priorities.append(f"rate_limits_cap_exceeded:{MAX_RATE_LIMITS_CAP}")
            final_reasons = finalize_parser_reasons(
                parser_reasons,
                mandatory_priorities,
            )
            return build_empty_or_unsupported_observation(
                run_id=run_id,
                session_ref_digest=file_digest,
                parser_status="partial",
                parser_reasons=final_reasons or ["unrecognized_event_or_subtype_in_stream"],
                completeness_status="complete" if terminal_event_observed else "not_observable",
                completeness_reasons=completeness_reasons or (["clean_terminal_event_observed"] if terminal_event_observed else ["no_explicit_terminal_marker_in_rollout"]),
                source_format_fingerprint=format_fingerprint,
            )
        else:
            return build_empty_or_unsupported_observation(
                run_id=run_id,
                session_ref_digest=file_digest,
                parser_status="unsupported",
                parser_reasons=["unrecognized_event_schema_for_codex"],
                completeness_status="not_observable",
                completeness_reasons=["unrecognized_event_schema_for_codex"],
                source_format_fingerprint=format_fingerprint,
            )

    # 1. Raw Usage: Cumulative Snapshot (Invariant I6: never sum cumulative snapshots!)
    raw_cum: Dict[str, Any] = {}
    for f in counter_fields:
        if f in latest_cum:
            raw_cum[f] = format_counter(latest_cum[f])
        else:
            raw_cum[f] = "not_observable"

    # 2. Raw Usage: Per-Response Sum (strictly integer >= 0, ignore non-integers)
    per_resp_sum: Dict[str, Any] = {}
    if response_count == 0:
        for f in counter_fields:
            per_resp_sum[f] = "not_observable"
    else:
        for f in counter_fields:
            if per_resp_observed[f]:
                per_resp_sum[f] = per_resp_sums[f]
            else:
                per_resp_sum[f] = "not_observable"

    # 3. Field-by-field Reconciliation
    field_reconciliations: Dict[str, Any] = {}
    any_divergent = False
    any_observable = False

    for f in counter_fields:
        r = reconcile_field(raw_cum.get(f), per_resp_sum.get(f))
        field_reconciliations[f] = r
        if r["status"] == "divergent":
            any_divergent = True
        if r["status"] == "reconciled":
            any_observable = True

    if any_divergent:
        overall_recon_status = "divergent"
    elif any_observable:
        overall_recon_status = "reconciled"
    else:
        overall_recon_status = "not_observable"

    raw_usage = {
        "cumulative": raw_cum,
        "per_response_sum": per_resp_sum,
        "reconciliation": {
            "status": overall_recon_status,
            "fields": field_reconciliations,
        },
        "response_count": response_count,
    }

    # T026: Raw Usage Channels (AC1)
    raw_usage_channels = {
        "token_usage_records": {
            "event_count": token_usage_records_count,
            "per_response_sum": {
                f: (token_usage_records_sums[f] if token_usage_records_observed[f] else "not_observable")
                for f in counter_fields
            },
        },
        "event_msg_token_counts": {
            "event_count": event_msg_token_counts_count,
            "per_response_sum": {
                f: (event_msg_token_counts_sums[f] if event_msg_token_counts_observed[f] else "not_observable")
                for f in counter_fields
            },
        },
        "cumulative_snapshots": {
            "snapshot_count": cumulative_snapshots_count,
            "latest_snapshot": latest_cumulative_snapshot,
        },
    }

    # T026: Semantic Correlations Layer (AC3, AC7, I25)
    records_retained = len(semantic_correlations_records)
    records_observed = records_retained + records_overflow_count
    records_truncated = records_overflow_count > 0
    semantic_correlations = {
        "rule_id": RULE_ID_CODEX_0_153_4 if harness_version == "0.153.4" else None,
        "summary": {
            "records_observed": records_observed,
            "records_retained": records_retained,
            "records_truncated": records_truncated,
            "correlated_events": correlated_events_count,
            "ambiguous_events": ambiguous_events_count,
            "unmatched_events": unmatched_events_count,
        },
        "records": semantic_correlations_records,
    }

    # T026: Normalized Usage Layer & Non-Circular Eligibility Evaluation (AC6, I24)
    ineligibility_reasons: List[str] = []

    # 1. Rule applicability & supported version
    if harness_version != "0.153.4":
        ineligibility_reasons.append(f"unsupported_rule_harness_version:{harness_version}")

    # 2. Format fingerprint & structural integrity
    if format_fingerprint not in SUPPORTED_FORMAT_FINGERPRINTS:
        ineligibility_reasons.append(f"unsupported_source_format_fingerprint:{format_fingerprint}")
    if syntax_error_encountered or truncated_line_encountered:
        ineligibility_reasons.append("encountered_json_syntax_or_truncation_errors")
    if unrecognized_event_encountered:
        ineligibility_reasons.append(first_unrecognized_reason or "unrecognized_event_in_stream")

    # 3. Required channels observable
    if token_usage_records_count == 0:
        ineligibility_reasons.append("required_usage_channel_missing:token_usage_records")
    if cumulative_snapshots_count == 0:
        ineligibility_reasons.append("required_usage_channel_missing:cumulative_snapshots")

    # 4. No ambiguous or conflicting usage identities (Classe C and Classe F)
    if has_ambiguous_identity or has_conflicting_identity:
        for r in structural_ineligibility_reasons:
            if r not in ineligibility_reasons:
                ineligibility_reasons.append(r)

    eligible_for_normalization = (len(ineligibility_reasons) == 0)

    if eligible_for_normalization:
        norm_status = "normalized"
        norm_rule_id = RULE_ID_CODEX_0_153_4
        norm_resp_count = semantic_response_count
        norm_per_resp_sum = {
            f: (semantic_per_resp_sums[f] if semantic_per_resp_observed[f] else "not_observable")
            for f in counter_fields
        }
        norm_cum = raw_cum

        norm_field_reconciliations: Dict[str, Any] = {}
        norm_any_divergent = False
        norm_any_observable = False

        for f in counter_fields:
            r = reconcile_field(norm_cum.get(f), norm_per_resp_sum.get(f))
            norm_field_reconciliations[f] = r
            if r["status"] == "divergent":
                norm_any_divergent = True
            if r["status"] == "reconciled":
                norm_any_observable = True

        if norm_any_divergent:
            norm_overall_recon = "divergent"
        elif norm_any_observable:
            norm_overall_recon = "reconciled"
        else:
            norm_overall_recon = "not_observable"

        normalized_usage = {
            "status": norm_status,
            "rule_id": norm_rule_id,
            "eligible_for_normalization": True,
            "ineligibility_reasons": [],
            "semantic_response_count": norm_resp_count,
            "semantic_per_response_sum": norm_per_resp_sum,
            "cumulative": norm_cum,
            "reconciliation": {
                "status": norm_overall_recon,
                "fields": norm_field_reconciliations,
            },
        }
    else:
        normalized_usage = {
            "status": "not_observable",
            "rule_id": RULE_ID_CODEX_0_153_4 if harness_version == "0.153.4" else None,
            "eligible_for_normalization": False,
            "ineligibility_reasons": ineligibility_reasons,
            "semantic_response_count": 0,
            "semantic_per_response_sum": {f: "not_observable" for f in counter_fields},
            "cumulative": raw_cum,
            "reconciliation": {
                "status": "not_observable",
                "fields": {
                    f: {
                        "status": "not_observable",
                        "cumulative_value": raw_cum.get(f, "not_observable"),
                        "per_response_value": "not_observable",
                        "delta": None,
                    }
                    for f in counter_fields
                },
            },
        }


    # 4. Derived Usage (Invariant I5: strictly not_observable)
    derived_usage = {
        "uncached_input_tokens": "not_observable",
    }

    # 5. Observed Contexts (Preserve multi-model and multi-effort directly from context_stats)
    observed_contexts: List[Dict[str, Any]] = []
    if not context_stats:
        ctx_cum: Dict[str, Any] = {}
        for f in counter_fields:
            ctx_cum[f] = raw_cum.get(f, "not_observable")
        observed_contexts.append({
            "model": current_model,
            "effort": current_effort,
            "turn_count": 1 if recognized_events_count > 0 else 0,
            "raw_usage": ctx_cum,
        })
    else:
        for (m, eff), c_data in context_stats.items():
            ctx_counts: Dict[str, Any] = {}
            for f in counter_fields:
                if c_data["observed"][f]:
                    ctx_counts[f] = c_data["sums"][f]
                else:
                    ctx_counts[f] = "not_observable"
            observed_contexts.append({
                "model": m,
                "effort": eff,
                "turn_count": c_data["turn_count"],
                "raw_usage": ctx_counts,
            })

    # 6. Thread Topology (R1: deterministic topological root resolution and role mapping)
    def resolve_root_thread_id() -> Optional[str]:
        if not threads_data:
            return None

        def get_ancestor(tid: str) -> str:
            curr = tid
            visited = {curr}
            while curr in threads_data:
                pid = threads_data[curr].get("parent_thread_id")
                if not pid or pid in visited:
                    break
                visited.add(pid)
                curr = pid
            return curr

        roots_with_no_parent = [
            tid for tid in thread_order
            if threads_data[tid].get("parent_thread_id") is None
        ]

        if not roots_with_no_parent:
            return get_ancestor(thread_order[0])

        first_tid_anc = get_ancestor(thread_order[0])
        if first_tid_anc in roots_with_no_parent:
            return first_tid_anc

        ancestor_counts: Dict[str, int] = {}
        for tid in thread_order:
            anc = get_ancestor(tid)
            ancestor_counts[anc] = ancestor_counts.get(anc, 0) + 1

        return max(roots_with_no_parent, key=lambda r: ancestor_counts.get(r, 0))

    root_thread_id = resolve_root_thread_id()

    threads_list: List[Dict[str, Any]] = []
    ordered_ids = (
        [root_thread_id] + [t for t in thread_order if t != root_thread_id]
        if root_thread_id and root_thread_id in threads_data
        else thread_order
    )

    for t_id in ordered_ids:
        t_info = threads_data[t_id]
        if t_id == root_thread_id:
            role = "root"
        elif t_info.get("agent_role") in ("guardian", "auto_review"):
            role = t_info["agent_role"]
        else:
            role = "child"
        threads_list.append({
            "thread_id": t_info["thread_id"],
            "parent_thread_id": t_info["parent_thread_id"],
            "role": role,
            "turn_count": t_info["turn_count"],
        })

    thread_topology = {
        "root_thread_id": root_thread_id,
        "session_id": session_id,
        "threads": threads_list,
    }

    # 7. Timing Semantics (R7: strictly over valid timestamps)
    span_seconds: Any = "not_observable"
    if first_valid_dt is not None and last_valid_dt is not None and last_valid_dt >= first_valid_dt:
        span_seconds = round((last_valid_dt - first_valid_dt).total_seconds(), 3)

    timing = {
        "observed_session_span_seconds": span_seconds,
        "first_timestamp": first_valid_ts_str,
        "last_timestamp": last_valid_ts_str,
        "source": "rollout_first_last_timestamp",
        "job_wall_seconds": "not_observable",
        "model_latency_seconds": "not_observable",
    }


    # 8. Completeness & Parser Status (R3, R10, R13, R17, R19: verifiable supported format policy)
    if syntax_error_encountered or truncated_line_encountered:
        completeness_status = "incomplete"
        parser_status = "partial"
        append_reason(parser_reasons, "encountered_json_syntax_or_truncation_errors")
    elif harness_version is None:
        completeness_status = "complete" if terminal_event_observed else "not_observable"
        parser_status = "partial"
        append_reason(parser_reasons, "missing_or_unverified_harness_version")
    elif harness_version not in SUPPORTED_CLI_VERSIONS:
        completeness_status = "complete" if terminal_event_observed else "not_observable"
        parser_status = "partial"
        append_reason(parser_reasons, f"unsupported_or_untested_harness_version:{harness_version}")
    elif format_fingerprint not in SUPPORTED_FORMAT_FINGERPRINTS:
        completeness_status = "complete" if terminal_event_observed else "not_observable"
        parser_status = "partial"
        append_reason(parser_reasons, f"unsupported_source_format_fingerprint:{format_fingerprint}")
    elif unrecognized_event_encountered:
        completeness_status = "complete" if terminal_event_observed else "not_observable"
        parser_status = "partial"
    elif contexts_cap_exceeded or threads_cap_exceeded or rate_limits_cap_exceeded:
        completeness_status = "complete" if terminal_event_observed else "not_observable"
        parser_status = "partial"
        if terminal_event_observed:
            append_reason(completeness_reasons, "clean_terminal_event_observed")
        else:
            append_reason(completeness_reasons, "no_explicit_terminal_marker_in_rollout")
    elif terminal_event_observed:
        completeness_status = "complete"
        append_reason(completeness_reasons, "clean_terminal_event_observed")
        parser_status = "supported"
        append_reason(parser_reasons, "full_codex_rollout_recognized_and_complete")
    else:
        completeness_status = "not_observable"
        append_reason(completeness_reasons, "no_explicit_terminal_marker_in_rollout")
        parser_status = "supported"
        append_reason(parser_reasons, "valid_codex_records_parsed_without_syntax_error")

    # R19, R20, R21 & R22: Explicitly model all mandatory priorities without substring heuristics or positional overwrites
    mandatory_priorities: List[str] = []
    if unrecognized_event_encountered:
        mandatory_priorities.append(first_unrecognized_reason or "unrecognized_event_or_subtype_in_stream")
    if contexts_cap_exceeded:
        mandatory_priorities.append(f"observed_contexts_cap_exceeded:{MAX_CONTEXTS_CAP}")
    if threads_cap_exceeded:
        mandatory_priorities.append(f"threads_topology_cap_exceeded:{MAX_THREADS_CAP}")
    if rate_limits_cap_exceeded:
        mandatory_priorities.append(f"rate_limits_cap_exceeded:{MAX_RATE_LIMITS_CAP}")
    if has_ambiguous_identity:
        for r in structural_ineligibility_reasons:
            if "ambiguous" in r or "missing" in r:
                mandatory_priorities.append(r)
        if not any("ambiguous" in p or "missing" in p for p in mandatory_priorities):
            mandatory_priorities.append("ambiguous_usage_event_identity")
    if has_conflicting_identity:
        for r in structural_ineligibility_reasons:
            if "conflict" in r or "mismatch" in r:
                mandatory_priorities.append(r)
        if not any("conflict" in p or "mismatch" in p for p in mandatory_priorities):
            mandatory_priorities.append("conflicting_structural_identity")

    if mandatory_priorities:
        parser_status = "partial"
        if "full_codex_rollout_recognized_and_complete" in parser_reasons:
            parser_reasons.remove("full_codex_rollout_recognized_and_complete")
        if "valid_codex_records_parsed_without_syntax_error" in parser_reasons:
            parser_reasons.remove("valid_codex_records_parsed_without_syntax_error")

    final_parser_reasons = finalize_parser_reasons(
        parser_reasons,
        mandatory_priorities,
    )

    obs_result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "session_ref_digest": file_digest,
        "harness": "codex",
        "harness_version": harness_version,
        "source_format": SOURCE_FORMAT,
        "source_format_fingerprint": format_fingerprint,
        "parser_status": {
            "status": parser_status,
            "parser_version": PARSER_VERSION,
            "reasons": final_parser_reasons or ["valid_session_parsed"],
        },
        "completeness": {
            "status": completeness_status,
            "reasons": completeness_reasons or ["rollout_stream_analyzed"],
        },
        "timing": timing,
        "raw_usage": raw_usage,
        "raw_usage_channels": raw_usage_channels,
        "semantic_correlations": semantic_correlations,
        "normalized_usage": normalized_usage,
        "derived_usage": derived_usage,
        "observed_contexts": observed_contexts,
        "thread_topology": thread_topology,
        "rate_limits": rate_limits_extracted,
    }

    # R11 & R14: Unconditional verification against schema Draft 2020-12
    return enforce_schema_validation(obs_result)


def build_empty_or_unsupported_observation(
    run_id: str,
    session_ref_digest: str,
    parser_status: str,
    parser_reasons: List[str],
    completeness_status: str,
    completeness_reasons: List[str],
    source_format_fingerprint: Optional[str] = None,
    harness: str = "codex",
    source_format: Optional[str] = None,
) -> Dict[str, Any]:
    counter_fields = [
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ]
    not_obs_counters = {f: "not_observable" for f in counter_fields}
    not_obs_claude_counters = {f: "not_observable" for f in CLAUDE_COUNTER_FIELDS}
    not_obs_recons = {
        f: {
            "status": "not_observable",
            "cumulative_value": "not_observable",
            "per_response_value": "not_observable",
            "delta": None,
        }
        for f in counter_fields
    }

    if harness == "claude":
        s_format = source_format or CLAUDE_SOURCE_FORMAT
        raw_channels: Dict[str, Any] = {
            "claude_assistant_messages": {
                "event_count": 0,
                "native_counters_sum": not_obs_claude_counters,
            },
            "claude_unique_responses": {
                "event_count": 0,
                "native_counters_sum": not_obs_claude_counters,
            },
        }
        normalized_block: Dict[str, Any] = {
            "status": "not_observable",
            "rule_id": None,
            "eligible_for_normalization": False,
            "ineligibility_reasons": parser_reasons or ["empty_or_unsupported_session"],
            "semantic_response_count": 0,
            "semantic_per_response_sum": not_obs_counters,
            "semantic_request_sum": not_obs_claude_counters,
            "cumulative": not_obs_counters,
            "reconciliation": {
                "status": "not_observable",
                "fields": not_obs_recons,
            },
        }
        compaction_obs: List[Dict[str, Any]] = []
    else:
        s_format = source_format or SOURCE_FORMAT
        raw_channels = {
            "token_usage_records": {
                "event_count": 0,
                "per_response_sum": not_obs_counters,
            },
            "event_msg_token_counts": {
                "event_count": 0,
                "per_response_sum": not_obs_counters,
            },
            "cumulative_snapshots": {
                "snapshot_count": 0,
                "latest_snapshot": not_obs_counters,
            },
        }
        normalized_block = {
            "status": "not_observable",
            "rule_id": None,
            "eligible_for_normalization": False,
            "ineligibility_reasons": parser_reasons or ["empty_or_unsupported_session"],
            "semantic_response_count": 0,
            "semantic_per_response_sum": not_obs_counters,
            "cumulative": not_obs_counters,
            "reconciliation": {
                "status": "not_observable",
                "fields": not_obs_recons,
            },
        }
        compaction_obs = []

    res: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "session_ref_digest": session_ref_digest,
        "harness": harness,
        "harness_version": None,
        "source_format": s_format,
        "source_format_fingerprint": source_format_fingerprint or hashlib.sha256(b"empty_or_unsupported").hexdigest()[:16],
        "parser_status": {
            "status": parser_status,
            "parser_version": PARSER_VERSION,
            "reasons": parser_reasons,
        },
        "completeness": {
            "status": completeness_status,
            "reasons": completeness_reasons,
        },
        "timing": {
            "observed_session_span_seconds": "not_observable",
            "first_timestamp": None,
            "last_timestamp": None,
            "source": "rollout_first_last_timestamp",
            "job_wall_seconds": "not_observable",
            "model_latency_seconds": "not_observable",
        },
        "raw_usage": {
            "cumulative": not_obs_counters,
            "per_response_sum": not_obs_counters,
            "reconciliation": {
                "status": "not_observable",
                "fields": not_obs_recons,
            },
            "response_count": 0,
        },
        "raw_usage_channels": raw_channels,
        "semantic_correlations": {
            "rule_id": None,
            "summary": {
                "records_observed": 0,
                "records_retained": 0,
                "records_truncated": False,
                "correlated_events": 0,
                "ambiguous_events": 0,
                "unmatched_events": 0,
            },
            "records": [],
        },
        "normalized_usage": normalized_block,
        "derived_usage": {
            "uncached_input_tokens": "not_observable",
        },
        "observed_contexts": [],
        "thread_topology": {
            "root_thread_id": None,
            "session_id": None,
            "threads": [],
        },
        "rate_limits": [],
    }
    if harness == "claude":
        res["source_kind"] = "harness_native_log"
        res["context_compaction_observations"] = compaction_obs
    return enforce_schema_validation(res)


def parse_claude_session(
    session_path: str,
    run_id: str,
    subagent_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parse a Claude session JSONL file and extract factual usage observation."""
    if not os.path.exists(session_path):
        raise FileNotFoundError(f"Session file not found: {session_path}")
    if os.path.isdir(session_path):
        raise IsADirectoryError(f"Session path is a directory: {session_path}")

    hasher = hashlib.sha256()

    session_id: Optional[str] = None
    harness_version: Optional[str] = None
    observed_versions: set[str] = set()
    version_inconsistency_encountered = False

    first_valid_dt: Optional[datetime.datetime] = None
    first_valid_ts_str: Optional[str] = None
    last_valid_dt: Optional[datetime.datetime] = None
    last_valid_ts_str: Optional[str] = None

    parser_reasons: List[str] = []
    completeness_reasons: List[str] = []
    structural_ineligibility_reasons: List[str] = []

    syntax_error_encountered = False
    truncated_line_encountered = False
    total_valid_json_count = 0
    recognized_events_count = 0

    negative_markers_encountered: List[str] = []
    structural_paths_missing_in_assistant = False
    has_ambiguous_identity = False
    has_conflicting_identity = False
    identity_ledger_cap_exceeded = False
    compactions_cap_exceeded = False
    tool_use_ids_cap_exceeded = False
    invalid_counter_encountered = False
    context_stats_cap_exceeded = False
    subagents_cap_exceeded = False
    subagents_error_encountered = False
    subagent_association_unverifiable = False

    # Counters tracking
    claude_assistant_messages_count = 0
    claude_assistant_messages_sums = {f: 0 for f in CLAUDE_COUNTER_FIELDS}
    claude_assistant_messages_observed = {f: False for f in CLAUDE_COUNTER_FIELDS}
    claude_counter_invalid = {f: False for f in CLAUDE_COUNTER_FIELDS}

    # Bounded identity ledger: (sessionId, messageId) -> entry
    identity_ledger: Dict[Tuple[str, str], Dict[str, Any]] = {}
    unique_response_count = 0
    unique_response_sums = {f: 0 for f in CLAUDE_COUNTER_FIELDS}
    unique_response_observed = {f: False for f in CLAUDE_COUNTER_FIELDS}
    unique_response_invalid = {f: False for f in CLAUDE_COUNTER_FIELDS}

    semantic_model_response_count = 0
    semantic_model_sums = {f: 0 for f in CLAUDE_COUNTER_FIELDS}
    semantic_model_observed = {f: False for f in CLAUDE_COUNTER_FIELDS}

    context_stats: Dict[Tuple[Optional[str], Optional[str]], Dict[str, Any]] = {}
    compaction_obs: List[Dict[str, Any]] = []
    observed_tool_use_ids: set[str] = set()

    semantic_correlations_records: List[Dict[str, Any]] = []
    records_overflow_count = 0
    correlated_events_count = 0
    ambiguous_events_count = 0

    pending_decode_error: Optional[Tuple[int, str, json.JSONDecodeError]] = None

    def append_reason(reasons_list: List[str], reason: str) -> None:
        if len(reasons_list) < MAX_REASONS_CAP - 1:
            reasons_list.append(reason)
        elif len(reasons_list) == MAX_REASONS_CAP - 1:
            reasons_list.append("additional_reasons_truncated")

    def commit_pending_error_as_syntax(err_tuple: Tuple[int, str, json.JSONDecodeError]) -> None:
        nonlocal syntax_error_encountered
        syntax_error_encountered = True
        idx, _, exc = err_tuple
        append_reason(completeness_reasons, f"json_syntax_error_line_{idx}:{exc.msg}")

    with open(session_path, "rb") as bf:
        for line_idx, raw_bytes in enumerate(bf, start=1):
            hasher.update(raw_bytes)
            raw_line = raw_bytes.decode("utf-8", errors="replace")
            stripped = raw_line.strip()
            if not stripped:
                continue

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if pending_decode_error is not None:
                    commit_pending_error_as_syntax(pending_decode_error)
                pending_decode_error = (line_idx, raw_line, exc)
                continue

            if pending_decode_error is not None:
                commit_pending_error_as_syntax(pending_decode_error)
                pending_decode_error = None

            if not isinstance(data, dict):
                syntax_error_encountered = True
                append_reason(parser_reasons, f"line_{line_idx}_not_a_json_object")
                continue

            total_valid_json_count += 1
            line_type = data.get("type")

            # Extract sessionId and version
            s_id = data.get("sessionId")
            if session_id is None and s_id is not None:
                session_id = str(s_id) if isinstance(s_id, (str, int)) and not isinstance(s_id, bool) else None

            v_val = data.get("version")
            if v_val is not None:
                v_str = str(v_val) if isinstance(v_val, (str, int)) and not isinstance(v_val, bool) else "invalid_version_type"
                if len(observed_versions) < MAX_CLAUDE_VERSIONS_CAP:
                    observed_versions.add(v_str)

            # Timestamps
            raw_ts = data.get("timestamp")
            if isinstance(raw_ts, str) and raw_ts:
                dt = parse_iso_timestamp(raw_ts)
                if dt is not None:
                    if first_valid_dt is None:
                        first_valid_dt = dt
                        first_valid_ts_str = raw_ts
                    last_valid_dt = dt
                    last_valid_ts_str = raw_ts

            # Negative markers (completeness)
            for m_key, m_name in [
                ("isAbortedMidStream", "isAbortedMidStream_detected"),
                ("interruptedByShutdown", "interruptedByShutdown_detected"),
                ("isApiErrorMessage", "isApiErrorMessage_detected"),
            ]:
                if data.get(m_key) is True:
                    if m_name not in negative_markers_encountered:
                        if len(negative_markers_encountered) < MAX_CLAUDE_NEGATIVE_MARKERS_CAP:
                            negative_markers_encountered.append(m_name)

            if line_type in ("user", "system", "tool_result", "progress", "file-history-snapshot"):
                recognized_events_count += 1

            if line_type == "system":
                cm = data.get("compactMetadata")
                if isinstance(cm, dict):
                    pm = cm.get("preservedMessages")
                    uuids = pm.get("uuids") if isinstance(pm, dict) else []
                    if len(compaction_obs) < MAX_CLAUDE_COMPACTIONS_CAP:
                        compaction_obs.append({
                            "trigger": str(cm.get("trigger")) if cm.get("trigger") is not None else None,
                            "pre_tokens": format_counter(cm.get("preTokens")),
                            "post_tokens": format_counter(cm.get("postTokens")),
                            "cumulative_dropped_tokens": format_counter(cm.get("cumulativeDroppedTokens")),
                            "duration_ms": cm.get("durationMs") if isinstance(cm.get("durationMs"), (int, float)) and cm.get("durationMs") >= 0 else "not_observable",
                            "preserved_messages_count": len(uuids) if isinstance(uuids, list) else "not_observable",
                        })
                    else:
                        compactions_cap_exceeded = True
                        r_comp_cap = f"context_compaction_observations_cap_exceeded:{MAX_CLAUDE_COMPACTIONS_CAP}"
                        if r_comp_cap not in structural_ineligibility_reasons:
                            structural_ineligibility_reasons.append(r_comp_cap)

            elif line_type == "assistant":
                recognized_events_count += 1

                # Compaction summary text is discarded per Invariant I13 (Privacy)
                if data.get("isCompactSummary") is True:
                    continue

                msg = data.get("message")
                if not isinstance(msg, dict):
                    structural_paths_missing_in_assistant = True
                    r_msg = "structural_profile_mismatch_in_assistant_message:message_not_dict"
                    if r_msg not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_msg)
                    append_reason(parser_reasons, r_msg)
                    continue

                # Collect tool_use IDs for subagents linkage
                content = msg.get("content")
                if isinstance(content, list):
                    for blk in content:
                        if isinstance(blk, dict) and blk.get("type") == "tool_use":
                            tu_id = blk.get("id")
                            if tu_id and isinstance(tu_id, str):
                                if tu_id not in observed_tool_use_ids:
                                    if len(observed_tool_use_ids) < MAX_CLAUDE_TOOL_USE_IDS_CAP:
                                        observed_tool_use_ids.add(tu_id)
                                    else:
                                        tool_use_ids_cap_exceeded = True
                                        r_tu_cap = f"observed_tool_use_ids_cap_exceeded:{MAX_CLAUDE_TOOL_USE_IDS_CAP}"
                                        if r_tu_cap not in structural_ineligibility_reasons:
                                            structural_ineligibility_reasons.append(r_tu_cap)

                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    structural_paths_missing_in_assistant = True
                    r_usg = "structural_profile_mismatch_in_assistant_message:usage_not_dict"
                    if r_usg not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_usg)
                    append_reason(parser_reasons, r_usg)
                    continue

                # Verify required assistant paths
                path_missing = False
                for p in CLAUDE_CANONICAL_ASSISTANT_PATHS:
                    if not has_nested_path(data, p):
                        structural_paths_missing_in_assistant = True
                        r_path = f"structural_path_missing_in_assistant:{p}"
                        if r_path not in structural_ineligibility_reasons:
                            structural_ineligibility_reasons.append(r_path)
                        append_reason(parser_reasons, r_path)
                        path_missing = True
                        break
                if path_missing:
                    continue

                inp = usage.get("input_tokens")
                outp = usage.get("output_tokens")
                cc = usage.get("cache_creation_input_tokens")
                cr = usage.get("cache_read_input_tokens")
                details = usage.get("output_tokens_details")
                tt = details.get("thinking_tokens") if isinstance(details, dict) else (0 if details is None else details)

                # Strict type validation on all counters
                for cf_name, cf_raw in [
                    ("input_tokens", inp),
                    ("output_tokens", outp),
                    ("cache_creation_input_tokens", cc),
                    ("cache_read_input_tokens", cr),
                ]:
                    if cf_raw is not None:
                        if not isinstance(cf_raw, int) or isinstance(cf_raw, bool):
                            invalid_counter_encountered = True
                            claude_counter_invalid[cf_name] = True
                            r_cf = f"invalid_counter_type_{cf_name}:{type(cf_raw).__name__}"
                            append_reason(structural_ineligibility_reasons, r_cf)
                            append_reason(parser_reasons, r_cf)
                        elif cf_raw < 0:
                            invalid_counter_encountered = True
                            claude_counter_invalid[cf_name] = True
                            r_cf = f"negative_counter_value_{cf_name}"
                            append_reason(structural_ineligibility_reasons, r_cf)
                            append_reason(parser_reasons, r_cf)
                    else:
                        invalid_counter_encountered = True
                        claude_counter_invalid[cf_name] = True
                        r_cf = f"invalid_counter_type_{cf_name}:NoneType"
                        append_reason(structural_ineligibility_reasons, r_cf)
                        append_reason(parser_reasons, r_cf)

                if details is not None:
                    if not isinstance(details, dict):
                        invalid_counter_encountered = True
                        claude_counter_invalid["thinking_tokens"] = True
                        r_det = f"invalid_output_tokens_details_type:{type(details).__name__}"
                        append_reason(structural_ineligibility_reasons, r_det)
                        append_reason(parser_reasons, r_det)
                    elif "thinking_tokens" in details:
                        tt_raw = details["thinking_tokens"]
                        if not isinstance(tt_raw, int) or isinstance(tt_raw, bool):
                            invalid_counter_encountered = True
                            claude_counter_invalid["thinking_tokens"] = True
                            r_tt = f"invalid_thinking_tokens_type:{type(tt_raw).__name__}"
                            append_reason(structural_ineligibility_reasons, r_tt)
                            append_reason(parser_reasons, r_tt)
                        elif tt_raw < 0:
                            invalid_counter_encountered = True
                            claude_counter_invalid["thinking_tokens"] = True
                            r_tt = "negative_thinking_tokens_value"
                            append_reason(structural_ineligibility_reasons, r_tt)
                            append_reason(parser_reasons, r_tt)

                inp_val = inp if isinstance(inp, int) and not isinstance(inp, bool) and inp >= 0 else None
                outp_val = outp if isinstance(outp, int) and not isinstance(outp, bool) and outp >= 0 else None
                cc_val = cc if isinstance(cc, int) and not isinstance(cc, bool) and cc >= 0 else None
                cr_val = cr if isinstance(cr, int) and not isinstance(cr, bool) and cr >= 0 else None
                if details is None:
                    tt_val = 0
                elif isinstance(details, dict):
                    if "thinking_tokens" in details:
                        tt_raw = details["thinking_tokens"]
                        tt_val = tt_raw if isinstance(tt_raw, int) and not isinstance(tt_raw, bool) and tt_raw >= 0 else None
                    else:
                        tt_val = 0
                else:
                    tt_val = None

                # Physical accounting
                claude_assistant_messages_count += 1
                for cf, val in [
                    ("input_tokens", inp_val),
                    ("output_tokens", outp_val),
                    ("cache_creation_input_tokens", cc_val),
                    ("cache_read_input_tokens", cr_val),
                    ("thinking_tokens", tt_val),
                ]:
                    if val is not None:
                        claude_assistant_messages_sums[cf] += val
                        claude_assistant_messages_observed[cf] = True

                # Model & Response kind
                model = msg.get("model")
                model_str = str(model) if isinstance(model, str) else "unknown"
                if model_str == "<synthetic>":
                    response_kind = "synthetic"
                elif model_str and not model_str.startswith("<") and model_str != "unknown":
                    response_kind = "model"
                else:
                    response_kind = "unknown"

                msg_id = msg.get("id")
                req_id = data.get("requestId")
                line_sess = data.get("sessionId") or session_id or "unknown"
                req_id_str = str(req_id) if isinstance(req_id, str) else None

                curr_counters = {
                    "input_tokens": inp_val if inp_val is not None else "not_observable",
                    "output_tokens": outp_val if outp_val is not None else "not_observable",
                    "cache_creation_input_tokens": cc_val if cc_val is not None else "not_observable",
                    "cache_read_input_tokens": cr_val if cr_val is not None else "not_observable",
                    "thinking_tokens": tt_val if tt_val is not None else "not_observable",
                }

                if not msg_id or not isinstance(msg_id, str):
                    has_ambiguous_identity = True
                    ambiguous_events_count += 1
                    r_amb = "ambiguous_usage_event_identity:missing_message_id"
                    if r_amb not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_amb)
                    if len(semantic_correlations_records) < MAX_CLAUDE_RECORDS_CAP:
                        semantic_correlations_records.append({
                            "correlation_id": f"ambiguous_line_{line_idx}",
                            "status": "ambiguous",
                            "strategy": "none",
                            "response_id": None,
                            "turn_id": None,
                            "thread_id": None,
                            "channels": ["claude_assistant_messages"],
                            "counters": curr_counters,
                            "response_kind": response_kind,
                            "reasons": [r_amb],
                        })
                    else:
                        records_overflow_count += 1
                else:
                    key = (str(line_sess), str(msg_id))
                    if key in identity_ledger:
                        prev = identity_ledger[key]
                        req_match = (req_id_str == prev["request_id"])
                        model_match = (model_str == prev["model"])
                        counters_match = (curr_counters == prev["counters"])
                        if not (req_match and model_match and counters_match):
                            has_conflicting_identity = True
                            ambiguous_events_count += 1
                            r_conflict = "conflicting_structural_identity:message_id_reused_with_divergent_requestId_model_or_counters"
                            if r_conflict not in structural_ineligibility_reasons:
                                structural_ineligibility_reasons.append(r_conflict)
                            if len(semantic_correlations_records) < MAX_CLAUDE_RECORDS_CAP:
                                semantic_correlations_records.append({
                                    "correlation_id": f"{msg_id}_conflict_line_{line_idx}",
                                    "status": "ambiguous",
                                    "strategy": "none",
                                    "response_id": str(msg_id),
                                    "turn_id": None,
                                    "thread_id": None,
                                    "channels": ["claude_assistant_messages"],
                                    "counters": curr_counters,
                                    "response_kind": response_kind,
                                    "reasons": [r_conflict],
                                    })
                            else:
                                records_overflow_count += 1
                        else:
                            correlated_events_count += 1
                            for rec in semantic_correlations_records:
                                if rec.get("correlation_id") == str(msg_id):
                                    rec["channels"].append("claude_assistant_messages")
                                    rec["reasons"].append("duplicate_block_correlated_exact_identity")
                                    break
                    else:
                        if len(identity_ledger) < MAX_CLAUDE_IDENTITY_CAP:
                            identity_ledger[key] = {
                                "request_id": req_id_str,
                                "model": model_str,
                                "counters": curr_counters,
                                "response_kind": response_kind,
                            }
                            correlated_events_count += 1
                            unique_response_count += 1
                            for cf in CLAUDE_COUNTER_FIELDS:
                                val = curr_counters[cf]
                                if isinstance(val, int):
                                    unique_response_sums[cf] += val
                                    unique_response_observed[cf] = True
                                else:
                                    unique_response_invalid[cf] = True

                            if response_kind == "model":
                                semantic_model_response_count += 1
                                for cf in CLAUDE_COUNTER_FIELDS:
                                    val = curr_counters[cf]
                                    if isinstance(val, int):
                                        semantic_model_sums[cf] += val
                                        semantic_model_observed[cf] = True

                            ctx_key = (model_str, None)
                            if ctx_key not in context_stats:
                                if len(context_stats) < MAX_CLAUDE_CONTEXT_STATS_CAP:
                                    context_stats[ctx_key] = {
                                        "turn_count": 0,
                                        "sums": {cf: 0 for cf in CLAUDE_COUNTER_FIELDS},
                                        "observed": {cf: False for cf in CLAUDE_COUNTER_FIELDS},
                                        "invalid": {cf: False for cf in CLAUDE_COUNTER_FIELDS},
                                    }
                                else:
                                    context_stats_cap_exceeded = True
                                    r_ctx_cap = f"context_stats_cap_exceeded:{MAX_CLAUDE_CONTEXT_STATS_CAP}"
                                    if r_ctx_cap not in structural_ineligibility_reasons:
                                        structural_ineligibility_reasons.append(r_ctx_cap)
                                    append_reason(parser_reasons, r_ctx_cap)
                            if ctx_key in context_stats:
                                context_stats[ctx_key]["turn_count"] += 1
                                for cf in CLAUDE_COUNTER_FIELDS:
                                    val = curr_counters[cf]
                                    if isinstance(val, int):
                                        context_stats[ctx_key]["sums"][cf] += val
                                        context_stats[ctx_key]["observed"][cf] = True
                                    else:
                                        context_stats[ctx_key]["invalid"][cf] = True

                            if len(semantic_correlations_records) < MAX_CLAUDE_RECORDS_CAP:
                                semantic_correlations_records.append({
                                    "correlation_id": str(msg_id),
                                    "status": "correlated",
                                    "strategy": "exact_identity",
                                    "response_id": str(msg_id),
                                    "turn_id": None,
                                    "thread_id": None,
                                    "channels": ["claude_assistant_messages"],
                                    "counters": curr_counters,
                                    "response_kind": response_kind,
                                    "reasons": ["exact_identity_registered"],
                                })
                            else:
                                records_overflow_count += 1
                        else:
                            identity_ledger_cap_exceeded = True
                            has_ambiguous_identity = True
                            ambiguous_events_count += 1
                            cap_r = f"identity_ledger_cap_exceeded:{MAX_CLAUDE_IDENTITY_CAP}"
                            if cap_r not in structural_ineligibility_reasons:
                                structural_ineligibility_reasons.append(cap_r)
                            if len(semantic_correlations_records) < MAX_CLAUDE_RECORDS_CAP:
                                semantic_correlations_records.append({
                                    "correlation_id": f"ledger_overflow_{msg_id}",
                                    "status": "ambiguous",
                                    "strategy": "none",
                                    "response_id": str(msg_id),
                                    "turn_id": None,
                                    "thread_id": None,
                                    "channels": ["claude_assistant_messages"],
                                    "counters": curr_counters,
                                    "response_kind": response_kind,
                                    "reasons": [cap_r],
                                })
                            else:
                                records_overflow_count += 1

    file_digest = hasher.hexdigest()

    if pending_decode_error is not None:
        p_idx, p_raw, p_exc = pending_decode_error
        is_truncated = (
            not p_raw.endswith("\n")
            or "Unterminated" in p_exc.msg
            or "unterminated" in p_exc.msg.lower()
            or "Expecting" in p_exc.msg
        )
        if is_truncated:
            truncated_line_encountered = True
            append_reason(completeness_reasons, f"truncated_line_at_line_{p_idx}:{p_exc.msg}")
        else:
            syntax_error_encountered = True
            append_reason(completeness_reasons, f"json_syntax_error_line_{p_idx}:{p_exc.msg}")
        pending_decode_error = None

    # Format fingerprint
    if recognized_events_count == 0 or total_valid_json_count == 0:
        format_fingerprint = hashlib.sha256(b"empty_or_unsupported").hexdigest()[:16]
    elif structural_paths_missing_in_assistant:
        format_fingerprint = hashlib.sha256(b"claude_session_jsonl:missing_paths").hexdigest()[:16]
    else:
        format_fingerprint = CLAUDE_CANONICAL_FINGERPRINT

    if recognized_events_count == 0 or total_valid_json_count == 0:
        return build_empty_or_unsupported_observation(
            run_id=run_id,
            session_ref_digest=file_digest,
            parser_status="unsupported",
            parser_reasons=["empty_or_completely_unparseable_file"],
            completeness_status="incomplete",
            completeness_reasons=completeness_reasons or ["no_valid_json_lines"],
            source_format_fingerprint=format_fingerprint,
            harness="claude",
            source_format=CLAUDE_SOURCE_FORMAT,
        )

    # Subagent topology (evaluated before parser_status and ineligibility decision)
    threads_list: List[Dict[str, Any]] = []
    root_tid = session_id or "session_root"
    root_turn_count: Any = "not_observable" if identity_ledger_cap_exceeded else unique_response_count
    threads_list.append({
        "thread_id": root_tid,
        "parent_thread_id": None,
        "role": "root",
        "turn_count": root_turn_count,
        "tool_use_id": None,
    })

    if subagent_paths:
        if len(subagent_paths) > MAX_CLAUDE_SUBAGENTS_CAP:
            subagents_cap_exceeded = True
            r_sa_cap = f"subagent_refs_cap_exceeded:{MAX_CLAUDE_SUBAGENTS_CAP}"
            if r_sa_cap not in structural_ineligibility_reasons:
                structural_ineligibility_reasons.append(r_sa_cap)
            append_reason(parser_reasons, r_sa_cap)

        meta_by_tu_id: Dict[str, List[Dict[str, Any]]] = {}
        meta_base_keys: Dict[str, List[str]] = {}
        meta_sessions: Dict[str, List[str]] = {}
        meta_by_base: Dict[str, List[str]] = {}
        meta_by_session: Dict[str, List[str]] = {}
        total_meta_count = 0

        explicit_jsonls: Dict[str, int] = {}
        jsonl_turns_by_base: Dict[str, int] = {}
        jsonl_turns_by_session: Dict[str, int] = {}
        jsonl_by_base: Dict[str, List[str]] = {}
        jsonl_by_session: Dict[str, List[str]] = {}
        all_jsonl_count = 0

        for sa_path in subagent_paths[:MAX_CLAUDE_SUBAGENTS_CAP]:
            if not os.path.exists(sa_path):
                subagents_error_encountered = True
                r_sa_err = "subagent_ref_file_not_found"
                if r_sa_err not in structural_ineligibility_reasons:
                    structural_ineligibility_reasons.append(r_sa_err)
                append_reason(parser_reasons, r_sa_err)
                continue

            sa_path_obj = Path(sa_path)
            try:
                resolved_sa_path = str(sa_path_obj.resolve())
            except Exception:
                resolved_sa_path = str(sa_path_obj)

            if sa_path_obj.name.endswith(".meta.json") or (sa_path_obj.suffix == ".json" and not sa_path_obj.name.endswith(".meta.json")):
                if total_meta_count >= MAX_CLAUDE_SUBAGENTS_CAP:
                    subagents_cap_exceeded = True
                    r_sa_meta_cap = f"explicit_metas_cap_exceeded:{MAX_CLAUDE_SUBAGENTS_CAP}"
                    if r_sa_meta_cap not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_sa_meta_cap)
                    append_reason(parser_reasons, r_sa_meta_cap)
                    continue

                if sa_path_obj.name.endswith(".meta.json"):
                    base_k = resolved_sa_path[:-10]
                else:
                    base_k = resolved_sa_path[:-5]

                try:
                    with open(sa_path_obj, "r", encoding="utf-8") as mf:
                        meta_data = json.load(mf)
                    if isinstance(meta_data, dict):
                        tu_id = meta_data.get("toolUseId")
                        if tu_id and isinstance(tu_id, str):
                            total_meta_count += 1
                            meta_by_tu_id.setdefault(tu_id, []).append(meta_data)
                            meta_base_keys.setdefault(tu_id, []).append(base_k)
                            meta_by_base.setdefault(base_k, []).append(tu_id)
                            m_sess = meta_data.get("sessionId") or meta_data.get("agentId")
                            if m_sess and isinstance(m_sess, str):
                                meta_sessions.setdefault(tu_id, []).append(m_sess)
                                meta_by_session.setdefault(m_sess, []).append(tu_id)
                    else:
                        subagents_error_encountered = True
                        r_sa_err = "subagent_meta_not_dict"
                        if r_sa_err not in structural_ineligibility_reasons:
                            structural_ineligibility_reasons.append(r_sa_err)
                        append_reason(parser_reasons, r_sa_err)
                except Exception as ex:
                    subagents_error_encountered = True
                    r_sa_err = f"subagent_meta_read_error:{type(ex).__name__}"
                    if r_sa_err not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_sa_err)
                    append_reason(parser_reasons, r_sa_err)
            elif sa_path_obj.suffix == ".jsonl":
                if all_jsonl_count >= MAX_CLAUDE_SUBAGENTS_CAP:
                    subagents_cap_exceeded = True
                    r_sa_jsonl_cap = f"explicit_jsonls_cap_exceeded:{MAX_CLAUDE_SUBAGENTS_CAP}"
                    if r_sa_jsonl_cap not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_sa_jsonl_cap)
                    append_reason(parser_reasons, r_sa_jsonl_cap)
                    continue

                base_k = resolved_sa_path[:-6]
                child_turns = 0
                sa_session_id = None
                jsonl_file_error = False
                try:
                    with open(sa_path_obj, "r", encoding="utf-8") as jf:
                        for jl in jf:
                            jl_str = jl.strip()
                            if not jl_str:
                                continue
                            try:
                                j_obj = json.loads(jl_str)
                            except Exception as dec_ex:
                                jsonl_file_error = True
                                subagents_error_encountered = True
                                r_sa_dec = f"subagent_jsonl_decode_error:{type(dec_ex).__name__}"
                                if r_sa_dec not in structural_ineligibility_reasons:
                                    structural_ineligibility_reasons.append(r_sa_dec)
                                append_reason(parser_reasons, r_sa_dec)
                                break
                            if isinstance(j_obj, dict):
                                if j_obj.get("type") == "assistant":
                                    child_turns += 1
                                if sa_session_id is None and j_obj.get("sessionId"):
                                    sa_session_id = str(j_obj["sessionId"])
                    if not jsonl_file_error:
                        all_jsonl_count += 1
                        jsonl_turns_by_base[base_k] = child_turns
                        jsonl_by_base.setdefault(base_k, []).append(resolved_sa_path)
                        if sa_session_id:
                            jsonl_turns_by_session[sa_session_id] = child_turns
                            jsonl_by_session.setdefault(sa_session_id, []).append(resolved_sa_path)
                        explicit_jsonls[resolved_sa_path] = child_turns
                except Exception as ex:
                    subagents_error_encountered = True
                    r_sa_err = f"subagent_jsonl_read_error:{type(ex).__name__}"
                    if r_sa_err not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_sa_err)
                    append_reason(parser_reasons, r_sa_err)
            else:
                subagents_error_encountered = True
                r_sa_err = "subagent_ref_unsupported_extension"
                if r_sa_err not in structural_ineligibility_reasons:
                    structural_ineligibility_reasons.append(r_sa_err)
                append_reason(parser_reasons, r_sa_err)

        for tu_id in sorted(meta_by_tu_id.keys()):
            if len(threads_list) >= MAX_CLAUDE_THREADS_CAP:
                subagents_cap_exceeded = True
                r_th_cap = f"threads_list_cap_exceeded:{MAX_CLAUDE_THREADS_CAP}"
                if r_th_cap not in structural_ineligibility_reasons:
                    structural_ineligibility_reasons.append(r_th_cap)
                append_reason(parser_reasons, r_th_cap)
                break
            if tu_id in observed_tool_use_ids:
                c_turns: Any = 0
                tu_metas = meta_by_tu_id.get(tu_id, [])

                # Enforce uniqueness per toolUseId
                if len(tu_metas) > 1:
                    c_turns = "not_observable"
                    subagent_association_unverifiable = True
                    r_sa_unv = f"subagent_jsonl_association_unverifiable:{tu_id}"
                    if r_sa_unv not in structural_ineligibility_reasons:
                        structural_ineligibility_reasons.append(r_sa_unv)
                    append_reason(parser_reasons, r_sa_unv)
                else:
                    b_keys = meta_base_keys.get(tu_id, [])
                    b_k = b_keys[0] if b_keys else None
                    s_keys = meta_sessions.get(tu_id, [])
                    s_k = s_keys[0] if s_keys else None

                    matched_from_base = False
                    matched_from_session = False
                    base_turn_val = None
                    session_turn_val = None

                    # 1. Structural match by base path stem
                    if b_k and b_k in jsonl_turns_by_base and len(meta_by_base.get(b_k, [])) == 1 and len(jsonl_by_base.get(b_k, [])) == 1:
                        matched_from_base = True
                        base_turn_val = jsonl_turns_by_base[b_k]

                    # 2. Structural match by sessionId
                    if s_k and s_k in jsonl_turns_by_session and len(meta_by_session.get(s_k, [])) == 1 and len(jsonl_by_session.get(s_k, [])) == 1:
                        matched_from_session = True
                        session_turn_val = jsonl_turns_by_session[s_k]

                    if matched_from_base and matched_from_session:
                        if base_turn_val == session_turn_val:
                            c_turns = base_turn_val
                        else:
                            c_turns = "not_observable"
                            subagent_association_unverifiable = True
                            r_sa_unv = f"subagent_jsonl_association_unverifiable:{tu_id}"
                            if r_sa_unv not in structural_ineligibility_reasons:
                                structural_ineligibility_reasons.append(r_sa_unv)
                            append_reason(parser_reasons, r_sa_unv)
                    elif matched_from_base:
                        c_turns = base_turn_val
                    elif matched_from_session:
                        c_turns = session_turn_val
                    elif all_jsonl_count == 0:
                        c_turns = 0
                    else:
                        c_turns = "not_observable"
                        subagent_association_unverifiable = True
                        r_sa_unv = f"subagent_jsonl_association_unverifiable:{tu_id}"
                        if r_sa_unv not in structural_ineligibility_reasons:
                            structural_ineligibility_reasons.append(r_sa_unv)
                        append_reason(parser_reasons, r_sa_unv)

                threads_list.append({
                    "thread_id": f"subagent_{tu_id}",
                    "parent_thread_id": root_tid,
                    "role": "child",
                    "turn_count": c_turns,
                    "tool_use_id": str(tu_id),
                })

    # Version evaluation across all lines
    if len(observed_versions) == 0:
        harness_version = None
    elif len(observed_versions) == 1:
        harness_version = next(iter(observed_versions))
    else:
        sorted_vers = sorted(list(observed_versions))
        harness_version = "multiple_versions_observed"
        version_inconsistency_encountered = True
        append_reason(structural_ineligibility_reasons, f"multiple_versions_observed:{sorted_vers}")
        append_reason(parser_reasons, f"multiple_versions_observed:{sorted_vers}")

    # Completeness (Fail-Closed: never emit 'complete' in v1)
    if syntax_error_encountered or truncated_line_encountered:
        completeness_status = "incomplete"
    elif negative_markers_encountered:
        completeness_status = "incomplete"
        for nm in negative_markers_encountered:
            append_reason(completeness_reasons, nm)
    else:
        completeness_status = "not_observable"
        append_reason(completeness_reasons, "no_conclusive_terminal_marker_in_claude_log")

    # Parser Status
    has_structural_issue_or_cap = (
        has_ambiguous_identity
        or has_conflicting_identity
        or identity_ledger_cap_exceeded
        or compactions_cap_exceeded
        or tool_use_ids_cap_exceeded
        or invalid_counter_encountered
        or context_stats_cap_exceeded
        or subagents_cap_exceeded
        or subagents_error_encountered
        or subagent_association_unverifiable
        or structural_paths_missing_in_assistant
    )

    if syntax_error_encountered or truncated_line_encountered:
        parser_status = "partial"
        append_reason(parser_reasons, "encountered_json_syntax_or_truncation_errors")
    elif harness_version != "2.1.257" or version_inconsistency_encountered:
        parser_status = "partial"
        append_reason(parser_reasons, f"unsupported_claude_version:{harness_version}")
    elif format_fingerprint != CLAUDE_CANONICAL_FINGERPRINT:
        parser_status = "partial"
        append_reason(parser_reasons, f"unsupported_source_format_fingerprint:{format_fingerprint}")
    elif has_structural_issue_or_cap:
        parser_status = "partial"
        for r in structural_ineligibility_reasons:
            append_reason(parser_reasons, r)
    elif negative_markers_encountered:
        parser_status = "partial"
        append_reason(parser_reasons, "negative_termination_marker_observed")
    else:
        parser_status = "supported"
        append_reason(parser_reasons, "valid_claude_records_parsed_without_syntax_error")

    # Ineligibility reasons for normalization
    ineligibility_reasons: List[str] = []
    if harness_version != "2.1.257" or version_inconsistency_encountered:
        ineligibility_reasons.append(f"unsupported_rule_harness_version:{harness_version}")
    if format_fingerprint != CLAUDE_CANONICAL_FINGERPRINT:
        ineligibility_reasons.append(f"unsupported_source_format_fingerprint:{format_fingerprint}")
    if syntax_error_encountered or truncated_line_encountered:
        ineligibility_reasons.append("encountered_json_syntax_or_truncation_errors")
    if has_structural_issue_or_cap:
        for r in structural_ineligibility_reasons:
            if r not in ineligibility_reasons:
                ineligibility_reasons.append(r)

    eligible_for_normalization = (len(ineligibility_reasons) == 0)

    # Timing
    span_seconds: Any = "not_observable"
    if first_valid_dt is not None and last_valid_dt is not None and last_valid_dt >= first_valid_dt:
        span_seconds = round((last_valid_dt - first_valid_dt).total_seconds(), 3)

    timing = {
        "observed_session_span_seconds": span_seconds,
        "first_timestamp": first_valid_ts_str,
        "last_timestamp": last_valid_ts_str,
        "source": "rollout_first_last_timestamp",
        "job_wall_seconds": "not_observable",
        "model_latency_seconds": "not_observable",
    }

    # Raw usage canonical block
    not_obs_token_counters = {f: "not_observable" for f in CANONICAL_COUNTER_FIELDS}
    not_obs_claude_counters = {f: "not_observable" for f in CLAUDE_COUNTER_FIELDS}
    not_obs_reconciliations = {
        f: {
            "status": "not_observable",
            "cumulative_value": "not_observable",
            "per_response_value": (
                "not_observable"
                if claude_counter_invalid.get(f, False) or not claude_assistant_messages_observed.get(f, False)
                else claude_assistant_messages_sums.get(f, "not_observable")
            ) if f in ("input_tokens", "output_tokens") else "not_observable",
            "delta": None,
        }
        for f in CANONICAL_COUNTER_FIELDS
    }

    raw_usage = {
        "cumulative": not_obs_token_counters,
        "per_response_sum": {
            "input_tokens": (
                "not_observable"
                if claude_counter_invalid["input_tokens"] or not claude_assistant_messages_observed["input_tokens"]
                else claude_assistant_messages_sums["input_tokens"]
            ),
            "cached_input_tokens": "not_observable",
            "cache_write_input_tokens": "not_observable",
            "output_tokens": (
                "not_observable"
                if claude_counter_invalid["output_tokens"] or not claude_assistant_messages_observed["output_tokens"]
                else claude_assistant_messages_sums["output_tokens"]
            ),
            "reasoning_output_tokens": "not_observable",
            "total_tokens": "not_observable",
        } if claude_assistant_messages_count > 0 else not_obs_token_counters,
        "reconciliation": {
            "status": "not_observable",
            "fields": not_obs_reconciliations,
        },
        "response_count": claude_assistant_messages_count,
    }

    if identity_ledger_cap_exceeded:
        unique_responses_status = "truncated"
        unique_responses_count = "not_observable"
        unique_responses_sums = not_obs_claude_counters
    elif any(claude_counter_invalid.values()) or any(unique_response_invalid.values()):
        unique_responses_status = "not_observable"
        unique_responses_count = unique_response_count
        unique_responses_sums = {
            f: (
                "not_observable"
                if claude_counter_invalid[f] or unique_response_invalid[f] or not unique_response_observed[f]
                else unique_response_sums[f]
            )
            for f in CLAUDE_COUNTER_FIELDS
        }
    else:
        unique_responses_status = "exact"
        unique_responses_count = unique_response_count
        unique_responses_sums = {
            f: (unique_response_sums[f] if unique_response_observed[f] else "not_observable")
            for f in CLAUDE_COUNTER_FIELDS
        }

    asst_status = "not_observable" if any(claude_counter_invalid.values()) else "exact"
    asst_counters_sum = {
        f: (
            "not_observable"
            if claude_counter_invalid[f] or not claude_assistant_messages_observed[f]
            else claude_assistant_messages_sums[f]
        )
        for f in CLAUDE_COUNTER_FIELDS
    }

    raw_usage_channels = {
        "claude_assistant_messages": {
            "status": asst_status,
            "event_count": claude_assistant_messages_count,
            "native_counters_sum": asst_counters_sum,
        },
        "claude_unique_responses": {
            "status": unique_responses_status,
            "event_count": unique_responses_count,
            "native_counters_sum": unique_responses_sums,
        },
    }

    records_retained = len(semantic_correlations_records)
    records_observed = records_retained + records_overflow_count
    records_truncated = records_overflow_count > 0
    semantic_correlations = {
        "rule_id": RULE_ID_CLAUDE_CODE_V1 if harness_version == "2.1.257" else None,
        "summary": {
            "records_observed": records_observed,
            "records_retained": records_retained,
            "records_truncated": records_truncated,
            "correlated_events": correlated_events_count,
            "ambiguous_events": ambiguous_events_count,
            "unmatched_events": 0,
        },
        "records": semantic_correlations_records,
    }

    if eligible_for_normalization:
        norm_status = "normalized"
        norm_resp_count = semantic_model_response_count
        norm_per_resp_sum = {
            "input_tokens": semantic_model_sums["input_tokens"] if semantic_model_observed["input_tokens"] else "not_observable",
            "cached_input_tokens": "not_observable",
            "cache_write_input_tokens": "not_observable",
            "output_tokens": semantic_model_sums["output_tokens"] if semantic_model_observed["output_tokens"] else "not_observable",
            "reasoning_output_tokens": "not_observable",
            "total_tokens": "not_observable",
        }
        norm_req_sum = {
            f: (semantic_model_sums[f] if semantic_model_observed[f] else "not_observable")
            for f in CLAUDE_COUNTER_FIELDS
        }
    else:
        norm_status = "not_observable"
        norm_resp_count = 0
        norm_per_resp_sum = not_obs_token_counters
        norm_req_sum = not_obs_claude_counters

    normalized_usage = {
        "status": norm_status,
        "rule_id": RULE_ID_CLAUDE_CODE_V1,
        "eligible_for_normalization": eligible_for_normalization,
        "ineligibility_reasons": ineligibility_reasons,
        "semantic_response_count": norm_resp_count,
        "semantic_per_response_sum": norm_per_resp_sum,
        "semantic_request_sum": norm_req_sum,
        "cumulative": not_obs_token_counters,
        "reconciliation": {
            "status": "not_observable",
            "fields": not_obs_reconciliations,
        },
    }

    derived_usage = {
        "uncached_input_tokens": "not_observable",
    }

    observed_contexts_list: List[Dict[str, Any]] = []
    if not context_stats:
        observed_contexts_list.append({
            "model": "unknown",
            "effort": None,
            "turn_count": "not_observable" if (identity_ledger_cap_exceeded or context_stats_cap_exceeded) else 0,
            "raw_usage": not_obs_claude_counters,
        })
    elif identity_ledger_cap_exceeded or context_stats_cap_exceeded:
        for (m, _), c_data in context_stats.items():
            observed_contexts_list.append({
                "model": m,
                "effort": None,
                "turn_count": "not_observable",
                "raw_usage": not_obs_claude_counters,
            })
    else:
        for (m, _), c_data in context_stats.items():
            observed_contexts_list.append({
                "model": m,
                "effort": None,
                "turn_count": c_data["turn_count"],
                "raw_usage": {
                    f: (
                        "not_observable"
                        if claude_counter_invalid[f] or c_data.get("invalid", {}).get(f, False) or not c_data["observed"][f]
                        else c_data["sums"][f]
                    )
                    for f in CLAUDE_COUNTER_FIELDS
                },
            })

    obs_result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "session_ref_digest": file_digest,
        "harness": "claude",
        "harness_version": harness_version,
        "source_format": CLAUDE_SOURCE_FORMAT,
        "source_format_fingerprint": format_fingerprint,
        "source_kind": "harness_native_log",
        "parser_status": {
            "status": parser_status,
            "parser_version": PARSER_VERSION,
            "reasons": parser_reasons or ["valid_claude_session_parsed"],
        },
        "completeness": {
            "status": completeness_status,
            "reasons": completeness_reasons or ["claude_stream_analyzed"],
        },
        "timing": timing,
        "raw_usage": raw_usage,
        "raw_usage_channels": raw_usage_channels,
        "semantic_correlations": semantic_correlations,
        "normalized_usage": normalized_usage,
        "derived_usage": derived_usage,
        "observed_contexts": observed_contexts_list,
        "thread_topology": {
            "root_thread_id": root_tid,
            "session_id": session_id,
            "threads": threads_list,
        },
        "rate_limits": [],
        "context_compaction_observations": compaction_obs,
    }

    return enforce_schema_validation(obs_result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract factual usage observations from Codex or Claude rollout sessions."
    )
    parser.add_argument("--run-id", required=True, help="Explicit run_id associated with this observation.")
    parser.add_argument("--session-ref", required=True, help="Path to the rollout JSONL file (read-only).")
    parser.add_argument("--output", default=None, help="Destination file path for JSON output (default: stdout).")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="Output format.")
    parser.add_argument("--verify-schema", action="store_true", help="Validate output against usage-observation schema.")
    parser.add_argument("--harness", choices=["codex", "claude"], default="codex", help="Harness type (default: codex).")
    parser.add_argument("--subagent-ref", action="append", default=[], help="Explicit path to subagent metadata or session file (optional).")

    args = parser.parse_args()

    try:
        if args.harness == "claude":
            result = parse_claude_session(args.session_ref, args.run_id, subagent_paths=args.subagent_ref)
        else:
            result = parse_codex_rollout(args.session_ref, args.run_id)
    except FileNotFoundError:
        sys.stderr.write(f"Error: session file not found: {os.path.basename(args.session_ref)}\n")
        return 1
    except Exception as e:
        err_msg = str(e)
        sanitized_msg = re.sub(r"(/[a-zA-Z0-9_\.\-]+)+/([a-zA-Z0-9_\.\-]+)", r"\2", err_msg)
        sys.stderr.write(f"Error parsing session: {type(e).__name__}: {sanitized_msg}\n")
        return 2

    if args.verify_schema:
        repo_root = Path(__file__).resolve().parent.parent
        schema_file = repo_root / "schemas" / "usage-observation.schema.json"
        if schema_file.exists():
            valid, errs = validate_against_schema(result, str(schema_file))
            if not valid:
                sys.stderr.write(f"Schema validation failed: {errs}\n")
                return 3

    if args.format == "json":
        out_str = json.dumps(result, indent=2) + "\n"
    else:
        # Compact text summary
        if result.get("harness") == "claude":
            out_str = (
                f"Run ID: {result['run_id']}\n"
                f"Digest: {result['session_ref_digest']}\n"
                f"Harness: {result['harness']}\n"
                f"Completeness: {result['completeness']['status']}\n"
                f"Parser Status: {result['parser_status']['status']}\n"
                f"Normalized Status: {result.get('normalized_usage', {}).get('status')}\n"
                f"Semantic Responses: {result.get('normalized_usage', {}).get('semantic_response_count')}\n"
            )
        else:
            out_str = (
                f"Run ID: {result['run_id']}\n"
                f"Digest: {result['session_ref_digest']}\n"
                f"Completeness: {result['completeness']['status']}\n"
                f"Parser Status: {result['parser_status']['status']}\n"
                f"Total Tokens: {result['raw_usage']['cumulative'].get('total_tokens')}\n"
                f"Reconciliation: {result['raw_usage']['reconciliation']['status']}\n"
            )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_str)
    else:
        sys.stdout.write(out_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
