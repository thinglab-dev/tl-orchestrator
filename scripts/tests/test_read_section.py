#!/usr/bin/env python3
"""
Unit tests for scripts/read_section.py CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "read_section.py"
SECTIONS_DIR = ROOT / "scripts" / "fixtures" / "sections"


class TestReadSectionCLI(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        cmd = [sys.executable, str(SCRIPT)] + list(args)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        return proc.returncode, proc.stdout, proc.stderr

    def test_json_output_success(self):
        file_path = SECTIONS_DIR / "nested_sections.md"
        code, stdout, stderr = self.run_cli("--file", str(file_path), "--heading", "## Section A")
        self.assertEqual(code, 0, f"CLI failed: {stderr}")
        data = json.loads(stdout)
        self.assertEqual(data["heading_path"], "# Root > ## Section A")
        self.assertIn("Section A intro", data["content"])
        self.assertIn("### Subsection A1", data["content"])
        self.assertNotIn("## Section B", data["content"])
        self.assertIsInstance(data["sha256"], str)
        self.assertGreater(data["bytes"], 0)

    def test_text_output_success(self):
        file_path = SECTIONS_DIR / "nested_sections.md"
        code, stdout, stderr = self.run_cli(
            "--file", str(file_path), "--heading", "### Subsection A1", "--format", "text"
        )
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("### Subsection A1"))
        self.assertIn("Content of A1.", stdout)

    def test_selector_not_found_exit_code_1(self):
        file_path = SECTIONS_DIR / "nested_sections.md"
        code, stdout, stderr = self.run_cli("--file", str(file_path), "--heading", "## Inexistent")
        self.assertEqual(code, 1)
        data = json.loads(stderr)
        self.assertEqual(data["error"], "selector_not_found")
        self.assertEqual(data["selector"], "## Inexistent")

    def test_ambiguous_selector_exit_code_2(self):
        file_path = SECTIONS_DIR / "ambiguous_headings.md"
        code, stdout, stderr = self.run_cli("--file", str(file_path), "--heading", "## Envelope original")
        self.assertEqual(code, 2)
        data = json.loads(stderr)
        self.assertEqual(data["error"], "ambiguous_selector")
        self.assertEqual(len(data["candidates"]), 2)

    def test_file_not_found_exit_code_3(self):
        code, stdout, stderr = self.run_cli("--file", "nonexistent/path.md", "--heading", "## Something")
        self.assertEqual(code, 3)
        data = json.loads(stderr)
        self.assertEqual(data["error"], "file_not_found")


if __name__ == "__main__":
    unittest.main()
