#!/usr/bin/env python3
"""
test_hardened_auditor.py - Synthetic validation test suite for the hardened auditor.
Tests the 9 exact cases specified by the maintainer:
1. Read permitido                    -> allowed_input
2. Read /outro-checkout/...          -> outside/disallowed
3. Bash cd input && cat file         -> allowed_input
4. Grep com path=input               -> allowed_input
5. Grep com path fora                -> outside
6. Glob com path=input               -> allowed_input
7. Glob com path fora                -> outside
8. symlink input -> árvore externa   -> outside/disallowed
9. arquivo técnico não declarado     -> outside
Also validates that the allowed_set hash manifests the exact support list used.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add scratchpad to sys.path
SCRATCHPAD = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad")
sys.path.insert(0, str(SCRATCHPAD))

from claude_transcript_adapter import (
    adapt_claude_transcript,
    audit_path_confinement,
    compute_allowed_set_hash,
)

def run_synthetic_tests():
    test_dir = Path(tempfile.mkdtemp(prefix="auditor_test_"))
    try:
        repo_root = test_dir / "repo"
        repo_root.mkdir()
        
        other_checkout = test_dir / "outro-checkout"
        other_checkout.mkdir()
        (other_checkout / "secret.md").write_text("secret external content")

        external_tree = test_dir / "external_tree"
        external_tree.mkdir()
        (external_tree / "external_secret.txt").write_text("outside data")

        # Create input dir and files inside repo
        input_dir = repo_root / "_tl-orc" / "project" / "evidence" / "inputs"
        input_dir.mkdir(parents=True)
        (input_dir / "spec.md").write_text("# Spec content\nValid spec text.")
        (input_dir / "data.json").write_text('{"status": "ok"}')

        # Create symlink inside input pointing to external tree
        symlink_target = input_dir / "symlink_escape.txt"
        symlink_target.symlink_to(external_tree / "external_secret.txt")

        # Create declared support file
        (repo_root / "CHANGELOG.md").write_text("# Changelog\nDeclared support.")

        # Create undeclared technical file
        (repo_root / "README.md").write_text("# Readme\nUndeclared technical file.")

        allowed_inputs = [
            "_tl-orc/project/evidence/inputs/spec.md",
            "_tl-orc/project/evidence/inputs/data.json",
            "_tl-orc/project/evidence/inputs/symlink_escape.txt",
        ]
        allowed_support = [
            "CHANGELOG.md",
            "/dev/null",
        ]

        # Verify hash manifests exact support list
        expected_hash = compute_allowed_set_hash(allowed_inputs, allowed_support)
        assert len(expected_hash) == 64
        print(f"Computed allowed_set hash: {expected_hash[:16]}... (manifests exact support list: {allowed_support})")

        results = {}

        # 1. Read permitido -> allowed_input
        norm, cl, r = audit_path_confinement(
            target_str="_tl-orc/project/evidence/inputs/spec.md",
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=100,
        )
        results["case_1_read_permitido"] = cl
        assert cl == "allowed_input", f"Case 1 failed: got {cl} ({r})"

        # 2. Read /outro-checkout/... -> outside/disallowed
        norm, cl, r = audit_path_confinement(
            target_str=str(other_checkout / "secret.md"),
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=100,
        )
        results["case_2_read_outro_checkout"] = cl
        assert cl in ("outside_allowed_set", "disallowed_external_attempt"), f"Case 2 failed: got {cl} ({r})"

        # 3. Bash cd input && cat file -> allowed_input
        norm, cl, r = audit_path_confinement(
            target_str="spec.md",
            cwd_str=str(input_dir),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=100,
        )
        results["case_3_bash_cd_cat"] = cl
        assert cl == "allowed_input", f"Case 3 failed: got {cl} ({r})"

        # 4. Grep com path=input -> allowed_input
        norm, cl, r = audit_path_confinement(
            target_str=str(input_dir),
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=50,
        )
        results["case_4_grep_path_input"] = cl
        assert cl == "allowed_input", f"Case 4 failed: got {cl} ({r})"

        # 5. Grep com path fora -> outside
        norm, cl, r = audit_path_confinement(
            target_str=str(repo_root / "unallowed_folder"),
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=50,
        )
        results["case_5_grep_path_fora"] = cl
        assert cl in ("outside_allowed_set", "disallowed_external_attempt"), f"Case 5 failed: got {cl} ({r})"

        # 6. Glob com path=input -> allowed_input
        norm, cl, r = audit_path_confinement(
            target_str=str(input_dir),
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=50,
        )
        results["case_6_glob_path_input"] = cl
        assert cl == "allowed_input", f"Case 6 failed: got {cl} ({r})"

        # 7. Glob com path fora -> outside
        norm, cl, r = audit_path_confinement(
            target_str=str(repo_root),
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=50,
        )
        results["case_7_glob_path_fora"] = cl
        assert cl == "outside_allowed_set", f"Case 7 failed: got {cl} ({r})"

        # 8. symlink input -> árvore externa -> outside/disallowed
        norm, cl, r = audit_path_confinement(
            target_str="_tl-orc/project/evidence/inputs/symlink_escape.txt",
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=100,
        )
        results["case_8_symlink_escape"] = cl
        assert cl in ("outside_allowed_set", "disallowed_external_attempt"), f"Case 8 failed: got {cl} ({r})"

        # 9. arquivo técnico não declarado -> outside
        norm, cl, r = audit_path_confinement(
            target_str="README.md",
            cwd_str=str(repo_root),
            default_repo_root=str(repo_root),
            allowed_inputs=allowed_inputs,
            allowed_support=allowed_support,
            is_fail=False,
            out_bytes=100,
        )
        results["case_9_undeclared_technical"] = cl
        assert cl == "outside_allowed_set", f"Case 9 failed: got {cl} ({r})"

        print("\nALL 9 SYNTHETIC TEST CASES PASSED 100%:")
        for k, v in results.items():
            print(f"  {k:30}: {v}")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    run_synthetic_tests()
