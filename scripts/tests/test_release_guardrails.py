"""Contract checks for the v0.13.0 operational guardrails (kept current through v0.16.0)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGuardrailsTest(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_package_version_is_consistent(self) -> None:
        manifest = json.loads(self.read("distribution-manifest.json"))
        marker = f"Versão atual do pacote: **{manifest['package_version']}**."
        self.assertEqual(manifest["package_version"], "0.19.0")
        self.assertIn(marker, self.read("README.md"))
        self.assertIn(marker, self.read("SKILL.md"))

    def test_active_package_counts_and_fixture_follow_manifest(self) -> None:
        manifest = json.loads(self.read("distribution-manifest.json"))
        count = manifest["package_file_count"]
        for relative in ("README.md", "docs/PROJECT_CONFIGURATION.md"):
            counts = re.findall(r"\b(\d+) arquivos\b", self.read(relative))
            self.assertTrue(counts)
            self.assertTrue(all(int(value) == count for value in counts), relative)
        fixture = "scripts/fixtures/workflow_quality/tasks.json"
        self.assertIn(fixture, manifest["package_files"])
        self.assertIn(fixture, self.read("README.md"))
        self.assertIn(fixture, self.read("docs/WORKFLOW_QUALITY.md"))

    def test_documented_export_executes_with_layout_and_hashes(self) -> None:
        readme = self.read("README.md")
        files = json.loads(self.read("distribution-manifest.json"))["package_files"]

        def block(first_line: str) -> str:
            marker = f"```sh\n{first_line}"
            return first_line + readme.split(marker, 1)[1].split("```", 1)[0]

        bash = None
        if os.name == "nt":
            candidate = Path(r"C:\Program Files\Git\bin\bash.exe")
            if candidate.is_file():
                bash = str(candidate)
        if bash is None:
            bash = shutil.which("bash")
        self.assertIsNotNone(bash, "bash is required to verify the documented POSIX export")
        command = "\n".join(
            (
                "export_dir=''",
                "trap 'case \"${export_dir:-}\" in /tmp/tl-orchestrator.*) rm -rf \"$export_dir\";; esac' EXIT",
                block("set -eu"),
                block("checksum_file=$(mktemp"),
                "printf '%s\\n' __export_layout__",
                "(cd \"$export_dir\" && find . -type f -print | LC_ALL=C sort)",
            )
        )
        result = subprocess.run(
            [bash, "-lc", command], cwd=ROOT, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checks = [line for line in result.stdout.splitlines() if line.endswith(": OK")]
        self.assertEqual(len(checks), len(files), result.stdout + result.stderr)
        layout = result.stdout.split("__export_layout__\n", 1)[1].splitlines()
        self.assertEqual(layout, [f"./{item}" for item in sorted(files)])

    def test_owner_rule_and_context_budget_are_durable(self) -> None:
        skill = self.read("SKILL.md")
        protocol = self.read("docs/EXECUTION_PROTOCOL.md")
        orchestrator = self.read("prompts/orchestrator.md")
        playbook = self.read("prompts/orchestrator-playbook.md")
        for phrase in (
            "Regra do dono",
            "Posso editar manualmente, sem orquestrar? Vou mudar X em Y.",
            "sem polling",
            "`blocking` e `reason`",
            "120 mil tokens",
            "agrupe comandos independentes numa chamada",
        ):
            self.assertIn(phrase, skill)
        self.assertIn("leia do `result.json` somente `blocking` e `reason`", protocol)
        self.assertIn("admita do `result.json` somente `blocking` e `reason`", playbook)
        self.assertIn("120 mil tokens", playbook)
        self.assertIn("polling, saída parcial e\nchecagens de progresso são proibidos", orchestrator)

    def test_deferred_human_verification_is_non_blocking_but_narrow(self) -> None:
        planner = self.read("prompts/planner.md")
        checker = self.read("prompts/checker-report-only.md")
        orchestrator = self.read("prompts/orchestrator.md")
        protocol = self.read("docs/EXECUTION_PROTOCOL.md")
        for text in (planner, checker, orchestrator, protocol):
            self.assertIn("`deferred`", text)
            self.assertIn("não bloqueante", text)
        self.assertIn("não geram por si só\n  `changes_requested`", checker)
        self.assertIn("não pode usar essa exceção", orchestrator)

        schema = json.loads(self.read("schemas/review-result.schema.json"))
        self.assertEqual(schema["properties"]["deferred"]["type"], "array")
        self.assertEqual(
            schema["properties"]["deferred"]["items"]["$ref"], "#/$defs/finding"
        )
        self.assertEqual(
            schema["allOf"][0]["then"]["properties"]["action_items"]["maxItems"], 0
        )

    def test_allowlist_and_recovery_rules_are_explicit(self) -> None:
        planner = self.read("prompts/planner.md")
        maker = self.read("prompts/maker.md")
        protocol = self.read("docs/EXECUTION_PROTOCOL.md")
        for token in ("`cd`", "`&&`", "`.exe`"):
            self.assertIn(token, planner)
            self.assertIn(token, maker)
        self.assertIn("declare\n  `completed`", maker)
        self.assertIn("execute `stop` e rode a story novamente", protocol)
        self.assertIn("git rev-parse --absolute-git-dir", protocol)
        self.assertIn("consultam o common-dir", protocol)


    def test_token_tools_are_wired_into_the_method(self) -> None:
        manifest = json.loads(self.read("distribution-manifest.json"))
        self.assertIn("docs/TOKEN_TOOLS.md", manifest["package_files"])
        self.assertIn("scripts/tl_tools.py", manifest["package_files"])
        self.assertEqual(manifest["package_file_count"], 54)
        self.assertIn("tl_tools.py doctor --fix", self.read("SKILL.md"))
        self.assertIn("rtk proxy <comando>", self.read("prompts/maker.md"))
        self.assertIn("`<<ccr:...>>`", self.read("prompts/checker-report-only.md"))
        self.assertIn("tl-tools: ...", self.read("prompts/orchestrator-playbook.md"))
        policy = self.read("docs/TOKEN_TOOLS.md")
        for phrase in ("## Política", "## Limites conhecidos", "## Medições", "disable"):
            self.assertIn(phrase, policy)
        self.assertIn("nunca falha nem bloqueia", self.read("scripts/tl_tools.py"))


if __name__ == "__main__":
    unittest.main()
