#!/usr/bin/env python3
"""
context_lib.py - Shared library for selective context retrieval, Markdown parsing,
canonical section digesting, freshness checking, and snapshot isolation.

No CLI interface is provided by this module. It is imported by read_section.py,
resume_generate.py, and context_ledger.py.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union


class ContextLibError(Exception):
    """Base exception for context_lib."""
    code: str = "context_lib_error"


class SelectorNotFoundError(ContextLibError):
    """Raised when a heading or selector is not found in the document."""
    code: str = "selector_not_found"

    def __init__(self, selector: str, available_headings: Optional[Sequence[str]] = None):
        super().__init__(f"selector_not_found: {selector}")
        self.selector = selector
        self.available_headings = list(available_headings or [])


class AmbiguousSelectorError(ContextLibError):
    """Raised when a short selector matches multiple distinct headings."""
    code: str = "ambiguous_selector"

    def __init__(self, selector: str, candidates: Sequence[str]):
        super().__init__(f"ambiguous_selector: {selector} matches multiple paths: {list(candidates)}")
        self.selector = selector
        self.candidates = list(candidates)


class InvalidEmptySectionError(ContextLibError):
    """Raised when a non-empty section in the file produces an empty extraction."""
    code: str = "invalid_empty_section"


@dataclass(frozen=True)
class Section:
    heading_line: str
    heading_path: str
    heading_text: str
    level: int  # 0 for frontmatter, 1 for #, 2 for ##, etc.
    start_line: int  # 1-indexed
    end_line: int    # 1-indexed, inclusive
    content: str     # canonical content ending in single \n
    sha256: str      # SHA-256 hex digest
    bytes: int       # byte count in UTF-8


ATX_HEADING_RE = re.compile(r"^[ ]{0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
CODE_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
VOLATILE_FIELDS_RE = re.compile(
    r"((?:last_write_at|session|started_at):\s*)[^\n]+|"
    r"(\b\d{4}-?\d{2}-?\d{2}T\d{2}:?\d{2}:?\d{2}[^\s\n]*)"
)


def canonicalize_newlines(text: str) -> str:
    """Normalize CRLF and CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compute_sha256(content: Union[str, bytes]) -> str:
    """Compute standard SHA-256 hex digest for UTF-8 string or bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def normalize_selector(selector: str) -> str:
    """Normalize a heading selector for comparison."""
    selector = selector.strip()
    # Normalize spaces around '>'
    parts = [p.strip() for p in selector.split(">")]
    return " > ".join(parts)


def parse_markdown_sections(text: str, ignore_code_fences: bool = False) -> list[Section]:
    """
    Parse a Markdown document into structural sections.

    Rules:
    1. ATX headings (# to ######) start at 0-3 leading spaces, followed by '#' and space/eol.
    2. Mentions in prose or inline code (e.g. `## Result`) do NOT start or end sections.
    3. Headings inside code fences (``` or ~~~) do NOT start or end sections (unless ignore_code_fences=True).
    4. Content before the first heading is parsed as the 'frontmatter' section (level 0).
    5. A section extends from its heading line (inclusive) until immediately before the next
       heading of equal or higher level (level <= current.level).
    6. Each section's canonical content ends with a single newline '\\n'.
    """
    normalized = canonicalize_newlines(text)
    raw_lines = normalized.splitlines()
    if not raw_lines:
        return []

    fence_char: Optional[str] = None
    fence_len = 0
    heading_entries: list[dict] = []

    for idx, line in enumerate(raw_lines):
        line_num = idx + 1

        # Check code fence toggle
        if not ignore_code_fences:
            fence_match = CODE_FENCE_RE.match(line)
            if fence_match:
                chars = fence_match.group(1)
                char = chars[0]
                length = len(chars)
                if fence_char is None:
                    # Opening fence
                    fence_char = char
                    fence_len = length
                    continue
                elif char == fence_char and length >= fence_len:
                    # Closing fence
                    fence_char = None
                    fence_len = 0
                    continue

        if fence_char is not None and not ignore_code_fences:
            # Inside code fence: ignore any '#' line
            continue

        # Check for ATX heading
        heading_match = ATX_HEADING_RE.match(line)
        if heading_match:
            hashes = heading_match.group(1)
            title = (heading_match.group(2) or "").strip()
            level = len(hashes)
            heading_entries.append({
                "line_num": line_num,
                "level": level,
                "hashes": hashes,
                "title": title,
                "raw_line": line,
            })

    sections: list[Section] = []

    # Case: Frontmatter (content before the first heading)
    if heading_entries:
        first_heading_line = heading_entries[0]["line_num"]
        if first_heading_line > 1:
            fm_lines = raw_lines[:first_heading_line - 1]
            fm_content = "\n".join(fm_lines) + "\n"
            sections.append(Section(
                heading_line="frontmatter",
                heading_path="frontmatter",
                heading_text="frontmatter",
                level=0,
                start_line=1,
                end_line=first_heading_line - 1,
                content=fm_content,
                sha256=compute_sha256(fm_content),
                bytes=len(fm_content.encode("utf-8")),
            ))
    else:
        # Document has no headings at all; whole document is frontmatter
        fm_content = "\n".join(raw_lines) + "\n"
        sections.append(Section(
            heading_line="frontmatter",
            heading_path="frontmatter",
            heading_text="frontmatter",
            level=0,
            start_line=1,
            end_line=len(raw_lines),
            content=fm_content,
            sha256=compute_sha256(fm_content),
            bytes=len(fm_content.encode("utf-8")),
        ))
        return sections

    # Track hierarchy stack to build heading_path
    # Stack items: (level, prefix_with_hashes, title)
    # e.g. (1, "# Title", "Title"), (2, "## Section", "Section")
    for i, entry in enumerate(heading_entries):
        start_line = entry["line_num"]
        level = entry["level"]
        hashes = entry["hashes"]
        title = entry["title"]
        heading_line = f"{hashes} {title}".strip()

        # Find where this section ends: the next heading with level <= current level
        end_line = len(raw_lines)
        for next_entry in heading_entries[i + 1:]:
            if next_entry["level"] <= level:
                end_line = next_entry["line_num"] - 1
                break

        # Extract lines for this section
        section_lines = raw_lines[start_line - 1:end_line]
        # Canonical ending: single \n
        content = "\n".join(section_lines) + "\n"

        # Build full heading path based on predecessor stack
        path_components: list[str] = []
        for prev in heading_entries[:i]:
            if prev["line_num"] < start_line and prev["level"] < level:
                # Check if it's still active (no heading between prev and current with <= prev.level)
                is_active = True
                for between in heading_entries:
                    if prev["line_num"] < between["line_num"] < start_line and between["level"] <= prev["level"]:
                        is_active = False
                        break
                if is_active:
                    prev_line = f"{prev['hashes']} {prev['title']}".strip()
                    if not path_components or path_components[-1] != prev_line:
                        path_components.append(prev_line)

        path_components.append(heading_line)
        full_heading_path = " > ".join(path_components)

        sections.append(Section(
            heading_line=heading_line,
            heading_path=full_heading_path,
            heading_text=title,
            level=level,
            start_line=start_line,
            end_line=end_line,
            content=content,
            sha256=compute_sha256(content),
            bytes=len(content.encode("utf-8")),
        ))

    return sections


def select_section(
    document_text: str,
    selector: str,
    ignore_code_fences: bool = False,
) -> Section:
    """
    Select a section by heading selector.

    Accepts:
    - 'frontmatter'
    - Exact heading line (e.g. '## Finding')
    - Exact title text (e.g. 'Finding')
    - Full heading path (e.g. '## Review record > ### Resultado da revisão')
    - Partial sub-path (e.g. '### Resultado da revisão')

    Raises:
    - SelectorNotFoundError if no matching section is found.
    - AmbiguousSelectorError if multiple distinct sections match and selector is ambiguous.
    - InvalidEmptySectionError if extracted body is empty while document body wasn't empty.
    """
    sections = parse_markdown_sections(document_text, ignore_code_fences=ignore_code_fences)
    norm_sel = normalize_selector(selector)

    # Check for frontmatter
    if norm_sel.lower() == "frontmatter":
        for sec in sections:
            if sec.level == 0 or sec.heading_line == "frontmatter":
                return sec
        raise SelectorNotFoundError(selector, [s.heading_path for s in sections])

    matches: list[Section] = []

    for sec in sections:
        # Match candidates
        sec_path = normalize_selector(sec.heading_path)
        sec_line = sec.heading_line
        sec_text = sec.heading_text

        # 1. Exact full path match
        if sec_path == norm_sel:
            matches.append(sec)
            continue

        # 2. Exact heading line match (e.g. "## Finding")
        if sec_line == norm_sel:
            matches.append(sec)
            continue

        # 3. Exact heading text match (e.g. "Finding")
        if sec_text == norm_sel:
            matches.append(sec)
            continue

        # 4. Path suffix match (e.g. "### Sub" matching "## Root > ### Sub")
        if sec_path.endswith(f" > {norm_sel}"):
            matches.append(sec)
            continue

        # 5. Matching without hashes (e.g. "Root > Sub")
        stripped_sec_path = re.sub(r"#{1,6}\s*", "", sec_path)
        stripped_norm_sel = re.sub(r"#{1,6}\s*", "", norm_sel)
        if stripped_sec_path == stripped_norm_sel or stripped_sec_path.endswith(f" > {stripped_norm_sel}"):
            matches.append(sec)
            continue

    if not matches:
        raise SelectorNotFoundError(selector, [s.heading_path for s in sections])

    # If multiple matches, check if one is an exact match on full heading_path
    exact_path_matches = [m for m in matches if normalize_selector(m.heading_path) == norm_sel]
    if len(exact_path_matches) == 1:
        chosen = exact_path_matches[0]
    elif len(matches) > 1:
        # Ambiguous!
        raise AmbiguousSelectorError(selector, [m.heading_path for m in matches])
    else:
        chosen = matches[0]

    # Validate non-spurious empty section (AC08 test 5)
    # Check if raw lines in file for this section only had heading + whitespace
    lines = chosen.content.splitlines()
    body_lines = lines[1:] if chosen.level > 0 else lines
    body_text = "\n".join(body_lines).strip()
    if not body_text:
        # Body is empty. Verify that the original document between start_line and end_line
        # was indeed empty (no non-empty body lines).
        raw_all = canonicalize_newlines(document_text).splitlines()
        raw_slice = raw_all[chosen.start_line - 1:chosen.end_line]
        raw_body = raw_slice[1:] if chosen.level > 0 else raw_slice
        if any(l.strip() for l in raw_body):
            raise InvalidEmptySectionError(
                f"Section '{chosen.heading_path}' extracted as empty body, but document contains non-empty lines."
            )

    return chosen


def strip_text_pattern(content: str, pattern: Union[str, re.Pattern]) -> tuple[str, str, str]:
    """
    Remove text matching pattern from content.
    Returns (transformed_content, hash_before, hash_after).
    Guaranteed to be idempotent.
    """
    hash_before = compute_sha256(content)
    if isinstance(pattern, re.Pattern):
        transformed = pattern.sub("", content)
    else:
        transformed = re.sub(pattern, "", content)

    # Ensure canonical newline
    transformed = canonicalize_newlines(transformed).rstrip() + "\n"
    hash_after = compute_sha256(transformed)
    return transformed, hash_before, hash_after


def mask_volatile_fields(text: str) -> str:
    """Mask volatile fields (timestamps, last_write_at, session, started_at) for stable digest."""
    def repl(m: re.Match) -> str:
        if m.group(1):
            return f"{m.group(1)}<VOLATILE>"
        return "<VOLATILE>"
    return VOLATILE_FIELDS_RE.sub(repl, text)


def evaluate_freshness(
    document_or_path: Union[str, Path],
    selector: str,
    expected_digest: str,
) -> dict:
    """
    Evaluate freshness state of a referenced section:
    - 'current': selector found and sha256 matches expected_digest
    - 'digest_changed': selector found but sha256 != expected_digest
    - 'selector_not_found': selector not found in document
    """
    if isinstance(document_or_path, Path):
        if not document_or_path.is_file():
            return {
                "status": "selector_not_found",
                "actual_digest": None,
                "expected_digest": expected_digest,
                "section": None,
                "reason": f"File not found: {document_or_path}",
            }
        text = document_or_path.read_text(encoding="utf-8")
    else:
        text = document_or_path

    try:
        sec = select_section(text, selector)
    except (SelectorNotFoundError, AmbiguousSelectorError):
        return {
            "status": "selector_not_found",
            "actual_digest": None,
            "expected_digest": expected_digest,
            "section": None,
        }

    if sec.sha256 == expected_digest:
        return {
            "status": "current",
            "actual_digest": sec.sha256,
            "expected_digest": expected_digest,
            "section": sec,
        }
    else:
        return {
            "status": "digest_changed",
            "actual_digest": sec.sha256,
            "expected_digest": expected_digest,
            "section": sec,
        }


def is_archived_evidence_path(path: Union[str, Path]) -> bool:
    """
    Check if a path points into archived evidence directories.
    Blocks any active discovery from snapshot trees.
    """
    parts = Path(path).parts
    for idx, part in enumerate(parts):
        if part == "evidence":
            return True
        if part == "project" and idx + 1 < len(parts) and parts[idx + 1] == "evidence":
            return True
    return False


def discover_active_roots(
    consumer_root: Union[str, Path],
    exclude_evidence: bool = True,
) -> dict[str, Path]:
    """
    Discover active canonical roots in a repository.
    Safe discovery (AC17): strictly excludes any paths under 'evidence/'.

    Returns dict mapping:
    - 'project_config': path to _tl-orc/PROJECT.md
    - 'status': path to _tl-orc/project/STATUS.md
    """
    root = Path(consumer_root).resolve()
    project_md = root / "_tl-orc" / "PROJECT.md"
    status_md = root / "_tl-orc" / "project" / "STATUS.md"

    if exclude_evidence and (is_archived_evidence_path(project_md) or is_archived_evidence_path(status_md)):
        raise PermissionError("Access to archived evidence prohibited in active discovery")

    results: dict[str, Path] = {}
    if project_md.is_file():
        results["project_config"] = project_md
    if status_md.is_file():
        results["status"] = status_md

    return results
