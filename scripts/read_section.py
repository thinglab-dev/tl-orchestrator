#!/usr/bin/env python3
"""
read_section.py - Thin CLI for deterministic selective section retrieval from Markdown files.
Uses context_lib for structural parsing, canonicalization, and SHA-256 computation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path so scripts/context_lib can be imported cleanly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.context_lib import (
    AmbiguousSelectorError,
    InvalidEmptySectionError,
    SelectorNotFoundError,
    select_section,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Selective Markdown section retrieval with structural parsing and canonical hash."
    )
    parser.add_argument("--file", "-f", required=True, help="Path to the Markdown file.")
    parser.add_argument("--heading", "-H", required=True, help="Heading path or selector to extract.")
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format: json (default) or raw text.",
    )
    return parser.parse_args()


def canonical_section_payload(file_path: Path, section: object) -> dict[str, object]:
    """Return the stable telemetry contract consumed by context_ledger.

    ``select_section`` owns canonicalization, so its section SHA-256 and byte
    count are relayed verbatim rather than recalculated from JSON serialization.
    """
    return {
        "path": str(file_path),
        "heading_path": section.heading_path,
        "start_line": section.start_line,
        "end_line": section.end_line,
        "sha256": section.sha256,
        "bytes": section.bytes,
        "content": section.content,
    }


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)

    if not file_path.is_file():
        err_payload = {
            "error": "file_not_found",
            "path": str(file_path),
            "message": f"File does not exist: {file_path}",
        }
        if args.format == "json":
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: {err_payload['message']}", file=sys.stderr)
        sys.exit(3)

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        err_payload = {
            "error": "read_error",
            "path": str(file_path),
            "message": str(exc),
        }
        if args.format == "json":
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(3)

    try:
        sec = select_section(content, args.heading)
    except SelectorNotFoundError as exc:
        err_payload = {
            "error": "selector_not_found",
            "selector": exc.selector,
            "path": str(file_path),
            "available_headings": exc.available_headings,
        }
        if args.format == "json":
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: selector_not_found: {exc.selector}", file=sys.stderr)
        sys.exit(1)
    except AmbiguousSelectorError as exc:
        err_payload = {
            "error": "ambiguous_selector",
            "selector": exc.selector,
            "path": str(file_path),
            "candidates": exc.candidates,
        }
        if args.format == "json":
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: ambiguous_selector: {exc.selector}", file=sys.stderr)
        sys.exit(2)
    except InvalidEmptySectionError as exc:
        err_payload = {
            "error": "invalid_empty_section",
            "selector": args.heading,
            "path": str(file_path),
            "message": str(exc),
        }
        if args.format == "json":
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: invalid_empty_section: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        payload = canonical_section_payload(file_path, sec)
        print(json.dumps(payload, indent=2))
    else:
        print(sec.content, end="")

    sys.exit(0)


if __name__ == "__main__":
    main()
