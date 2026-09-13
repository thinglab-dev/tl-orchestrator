#!/usr/bin/env python3
"""
Unit and counterfactual tests for scripts/context_lib.py.
Covers AC03, AC04, AC05, AC08 (cases 1 to 8), and AC17.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.context_lib import (
    AmbiguousSelectorError,
    SelectorNotFoundError,
    canonicalize_newlines,
    compute_sha256,
    discover_active_roots,
    evaluate_freshness,
    is_archived_evidence_path,
    mask_volatile_fields,
    parse_markdown_sections,
    select_section,
    strip_text_pattern,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sections"
ARCHIVED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "archived_tree"


class TestContextLib(unittest.TestCase):
    # AC08 Case 1: Heading in prose or inline backticks does not delimit sections
    def test_case1_prose_heading_not_delimited(self):
        content = (FIXTURES_DIR / "prose_heading.md").read_text(encoding="utf-8")
        sections = parse_markdown_sections(content)
        heading_lines = [s.heading_line for s in sections]
        self.assertNotIn("## Result", heading_lines)
        self.assertNotIn("## Spec", heading_lines)
        self.assertIn("## Actual Heading", heading_lines)

    # AC08 Case 2: Headings inside code fences do not delimit sections
    def test_case2_code_fence_headings_ignored(self):
        content = (FIXTURES_DIR / "code_fence_heading.md").read_text(encoding="utf-8")
        sections = parse_markdown_sections(content)
        heading_lines = [s.heading_line for s in sections]
        self.assertNotIn("## This looks like a level 2 heading inside triple backticks", heading_lines)
        self.assertNotIn("# Markdown heading inside tildes", heading_lines)
        self.assertIn("## Real Heading", heading_lines)

    # AC08 Case 3: Missing delimiter returns selector_not_found
    def test_case3_missing_delimiter_raises_selector_not_found(self):
        content = (FIXTURES_DIR / "prose_heading.md").read_text(encoding="utf-8")
        with self.assertRaises(SelectorNotFoundError) as ctx:
            select_section(content, "## NonExistentHeading")
        self.assertEqual(ctx.exception.code, "selector_not_found")

    # AC08 Case 4: Ambiguous delimiter raises ambiguous_selector
    def test_case4_ambiguous_delimiter_raises_ambiguous_selector(self):
        content = (FIXTURES_DIR / "ambiguous_headings.md").read_text(encoding="utf-8")
        with self.assertRaises(AmbiguousSelectorError) as ctx:
            select_section(content, "## Envelope original")
        self.assertEqual(ctx.exception.code, "ambiguous_selector")
        self.assertEqual(len(ctx.exception.candidates), 2)

        # Full path resolves ambiguity
        resolved = select_section(content, "# Parent 1 > ## Envelope original")
        self.assertIn("Content of Envelope original under Parent 1.", resolved.content)

    # AC08 Case 5: Empty section only valid if file actually has empty section
    def test_case5_legitimate_empty_section(self):
        content = (FIXTURES_DIR / "empty_section.md").read_text(encoding="utf-8")
        sec = select_section(content, "## Empty Section")
        self.assertEqual(sec.content.strip(), "## Empty Section")

    # AC08 Case 6: Section ends at next heading of equal or higher level
    def test_case6_section_hierarchy_and_nesting(self):
        content = (FIXTURES_DIR / "nested_sections.md").read_text(encoding="utf-8")
        sec_a = select_section(content, "## Section A")
        # Subsections A1 and A2 remain inside Section A
        self.assertIn("### Subsection A1", sec_a.content)
        self.assertIn("### Subsection A2", sec_a.content)
        # Section B is not inside Section A
        self.assertNotIn("## Section B", sec_a.content)

    # AC08 Case 7: Frontmatter is addressable as frontmatter
    def test_case7_frontmatter_addressable(self):
        content = (FIXTURES_DIR / "with_frontmatter.md").read_text(encoding="utf-8")
        fm = select_section(content, "frontmatter")
        self.assertEqual(fm.level, 0)
        self.assertIn("id: T999", fm.content)
        self.assertIn("type: feat", fm.content)

    # AC08 Case 8: Textual pattern removal is idempotent with before/after hashes
    def test_case8_textual_pattern_removal_idempotent(self):
        content = (FIXTURES_DIR / "closing_phrase.md").read_text(encoding="utf-8")
        pattern = r"Fechamento em [^\n]+\n"
        cleaned1, hash_before1, hash_after1 = strip_text_pattern(content, pattern)
        self.assertNotIn("Fechamento em", cleaned1)
        self.assertNotEqual(hash_before1, hash_after1)

        # Second call is idempotent
        cleaned2, hash_before2, hash_after2 = strip_text_pattern(cleaned1, pattern)
        self.assertEqual(cleaned1, cleaned2)
        self.assertEqual(hash_before2, hash_after2)
        self.assertEqual(hash_after1, hash_after2)

    # AC03: Canonical digest - line ending normalization CRLF vs LF
    def test_ac03_canonical_digest_line_endings(self):
        content_lf = "# Title\n\n## Section\nLine 1\nLine 2\n"
        content_crlf = "# Title\r\n\r\n## Section\r\nLine 1\r\nLine 2\r\n"
        sec_lf = select_section(content_lf, "## Section")
        sec_crlf = select_section(content_crlf, "## Section")
        self.assertEqual(sec_lf.sha256, sec_crlf.sha256)
        self.assertEqual(sec_lf.content, sec_crlf.content)

    # AC03 & R4: Regression tests - whitespace preservation and distinct digests without rstrip
    def test_ac03_trailing_whitespace_and_empty_lines_produce_distinct_digests(self):
        # 1. Trailing spaces on line must yield distinct digests
        doc_no_spaces = "# Doc\n\n## Target\nLine without spaces\n\n## Next\n"
        doc_with_spaces = "# Doc\n\n## Target\nLine without spaces   \n\n## Next\n"
        sec_no_spaces = select_section(doc_no_spaces, "## Target")
        sec_with_spaces = select_section(doc_with_spaces, "## Target")
        self.assertNotEqual(
            sec_no_spaces.sha256,
            sec_with_spaces.sha256,
            "Sections differing by line-end spaces must produce distinct digests",
        )
        self.assertNotEqual(sec_no_spaces.content, sec_with_spaces.content)

        # 2. Additional empty line before next heading must yield distinct digests
        doc_single_blank = "# Doc\n\n## Target\nBody line\n\n## Next\n"
        doc_double_blank = "# Doc\n\n## Target\nBody line\n\n\n## Next\n"
        sec_single = select_section(doc_single_blank, "## Target")
        sec_double = select_section(doc_double_blank, "## Target")
        self.assertNotEqual(
            sec_single.sha256,
            sec_double.sha256,
            "Sections differing by trailing empty lines must produce distinct digests",
        )
        self.assertNotEqual(sec_single.content, sec_double.content)

    # AC04: Freshness states (current, digest_changed, selector_not_found)
    def test_ac04_freshness_states(self):
        base_text = "# Title\n\n## Target\nOriginal Body\n\n## Other\nOther Body\n"
        sec = select_section(base_text, "## Target")
        expected_digest = sec.sha256

        # 1. State 'current'
        res_current = evaluate_freshness(base_text, "## Target", expected_digest)
        self.assertEqual(res_current["status"], "current")

        # Mutating irrelevant section leaves Target as 'current'
        mutated_other = base_text.replace("Other Body", "Modified Other Body")
        res_other = evaluate_freshness(mutated_other, "## Target", expected_digest)
        self.assertEqual(res_other["status"], "current")

        # 2. State 'digest_changed'
        mutated_target = base_text.replace("Original Body", "Changed Body")
        res_changed = evaluate_freshness(mutated_target, "## Target", expected_digest)
        self.assertEqual(res_changed["status"], "digest_changed")

        # 3. State 'selector_not_found'
        renamed_target = base_text.replace("## Target", "## RenamedTarget")
        res_missing = evaluate_freshness(renamed_target, "## Target", expected_digest)
        self.assertEqual(res_missing["status"], "selector_not_found")

    # AC05: Volatile fields masking
    def test_ac05_volatile_fields_masking(self):
        text1 = "coordinator:\n  last_write_at: 20260911T120000Z\n  session: sess-1\n  started_at: 20260911T100000Z\n"
        text2 = "coordinator:\n  last_write_at: 20260911T165959Z\n  session: sess-2\n  started_at: 20260911T110000Z\n"
        masked1 = mask_volatile_fields(text1)
        masked2 = mask_volatile_fields(text2)
        self.assertEqual(compute_sha256(masked1), compute_sha256(masked2))

    # Counterfactual probe: Disabling code fence handling fails AC08b
    def test_counterfactual_code_fence_disabled_fails(self):
        content = (FIXTURES_DIR / "code_fence_heading.md").read_text(encoding="utf-8")
        # With normal handling, inside-fence header is NOT a section
        sections_normal = parse_markdown_sections(content, ignore_code_fences=False)
        self.assertNotIn("## This looks like a level 2 heading inside triple backticks", [s.heading_line for s in sections_normal])

        # When fence handling is disabled, it cuts sections spuriously
        sections_broken = parse_markdown_sections(content, ignore_code_fences=True)
        self.assertIn("## This looks like a level 2 heading inside triple backticks", [s.heading_line for s in sections_broken])

    # AC17 & Counterfactual probe: Snapshots under evidence/ are excluded from active discovery
    def test_ac17_snapshots_excluded_from_active_discovery(self):
        archived_snap = ARCHIVED_DIR / "evidence" / "T012-support" / "r01" / "06-snapshot-dir_A"
        self.assertTrue(is_archived_evidence_path(archived_snap))

        # Active discovery strictly rejects any root under evidence/
        with self.assertRaises(PermissionError):
            discover_active_roots(archived_snap, exclude_evidence=True)

        # Counterfactual probe: if exclude_evidence is False, it would improperly discover it
        roots = discover_active_roots(archived_snap, exclude_evidence=False)
        self.assertIn("project_config", roots)
        self.assertIn("status", roots)


if __name__ == "__main__":
    unittest.main()
