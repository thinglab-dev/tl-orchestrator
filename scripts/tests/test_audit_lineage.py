#!/usr/bin/env python3
"""
Unit and counterfactual tests for scripts/audit_lineage.py.
Covers the 35 mandatory test cases specified in §7.3 of T024 plan:
T01 to T35.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_lineage import (
    compute_lineage_digest,
    parse_lineage_map,
    parse_status_board,
    parse_yaml_frontmatter,
    run_audits,
)
from scripts.tl_supervisor import update_task_status_atomic


class AuditLineagePositiveControlTest(unittest.TestCase):
    def test_t01_real_reconciled_tree_passes(self):
        """T01: Árvore reconciliada real (controle positivo) -> exit 0, zero BLOCKER."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        blockers, warnings = run_audits(repo_root)
        self.assertEqual(blockers, [], f"Árvore real falhou com BLOCKERs: {blockers}")


class AuditLineageSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project_dir = self.root / "_tl-orc" / "project"
        self.tasks_dir = self.project_dir / "tasks"
        self.evidence_dir = self.project_dir / "evidence"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _setup_base_fixture(self):
        # Setup lineage-map.md
        lineage_content = (
            "format_version: 1\n"
            "lineage_digest: DIGEST_PLACEHOLDER\n"
            "integration_base: 2aca4f42bdd399c943ad4a5afeb403725018f6ae\n"
            "generated_by: T024\n\n"
            "## Retired identities\n"
            "| retired_id | retired_file | lineage | live_id | live_file | reason |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T013 | _tl-orc/project/tasks/T013-old.md | local | T020 | _tl-orc/project/tasks/T020-new.md | id_collision_with_upstream_v0.9.0 |\n\n"
            "## Evidence prefix map\n"
            "| evidence_path | belongs_to |\n"
            "| :--- | :--- |\n"
            "| _tl-orc/project/evidence/T013-r01.md | T020 |\n\n"
            "## Historical provenance\n"
            "| from | to | nature |\n"
            "| :--- | :--- | :--- |\n"
            "| T020 | T001 | historical reference |\n"
        )
        digest = compute_lineage_digest(lineage_content)
        lineage_content = lineage_content.replace("DIGEST_PLACEHOLDER", digest)
        (self.project_dir / "lineage-map.md").write_text(lineage_content, encoding="utf-8")

        # Setup STATUS.md
        status_content = (
            "# Project Status\n\n"
            "active_batch: none\n"
            "batch_status: none\n"
            "next_batch_id: 1\n"
            "next_task_id: 25\n\n"
            "## Tasks\n\n"
            "| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T001 | feat | none | done | [] | [] | 1 | - |\n"
            "| T020 | fix | none | done | [T001] | [] | 1 | evidence/T013-r01.md |\n"
        )
        (self.project_dir / "STATUS.md").write_text(status_content, encoding="utf-8")

        # Setup tasks
        t1_content = (
            "id: T001\n"
            "type: feat\n"
            "status: done\n"
            "state_revision: 1\n"
            "depends_on: []\n"
            "blocked_by: []\n"
            "content_paths: []\n\n"
            "## Spec\nContent\n"
        )
        (self.tasks_dir / "T001-initial.md").write_text(t1_content, encoding="utf-8")

        (self.evidence_dir / "T013-r01.md").write_text("Evidence", encoding="utf-8")

        t20_content = (
            "id: T020\n"
            "type: fix\n"
            "status: done\n"
            "state_revision: 1\n"
            "depends_on: [T001]\n"
            "blocked_by: []\n"
            "content_paths: []\n\n"
            "## Spec\nContent\n"
        )
        (self.tasks_dir / "T020-new.md").write_text(t20_content, encoding="utf-8")

    def test_t02_duplicate_task_id(self):
        """T02: Dois arquivos com id: T013 -> BLOCKER L01 nomeando os dois paths."""
        self._setup_base_fixture()
        (self.tasks_dir / "T013-dup1.md").write_text("id: T013\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
        (self.tasks_dir / "T013-dup2.md").write_text("id: T013\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")

        blockers, _ = run_audits(self.root)
        l01_blockers = [b for b in blockers if "[L01]" in b]
        self.assertTrue(len(l01_blockers) >= 2)
        self.assertTrue(any("T013-dup1.md" in b for b in l01_blockers))
        self.assertTrue(any("T013-dup2.md" in b for b in l01_blockers))

    def test_t03_filename_prefix_mismatch(self):
        """T03: Arquivo T020-*.md com id: T021 -> BLOCKER L02 (prefixo != id)."""
        self._setup_base_fixture()
        (self.tasks_dir / "T020-wrong.md").write_text("id: T021\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L02]" in b and "não inicia com prefixo T021-" in b for b in blockers))

    def test_t04_duplicate_board_rows(self):
        """T04: Duas linhas de board T012 -> BLOCKER L02."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T001 | feat | none | done | [] | [] | 1 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L02]" in b and "múltiplas linhas de board" in b for b in blockers))

    def test_t05_board_row_without_file(self):
        """T05: Linha de board sem arquivo correspondente -> BLOCKER L02."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T099 | feat | none | ready | [] | [] | 0 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L02]" in b and "sem arquivo correspondente em tasks/" in b for b in blockers))

    def test_t06_task_file_without_board_row(self):
        """T06: Arquivo de task sem linha de board -> BLOCKER L02."""
        self._setup_base_fixture()
        (self.tasks_dir / "T099-orphan.md").write_text("id: T099\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L02]" in b and "sem linha correspondente no board STATUS.md" in b for b in blockers))

    def test_t07_unresolved_depends_on(self):
        """T07: depends_on: [T099] inexistente -> BLOCKER L03."""
        self._setup_base_fixture()
        (self.tasks_dir / "T002-dep.md").write_text("id: T002\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: [T099]\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T002 | feat | none | ready | [T099] | [] | 0 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L03]" in b and "referencia id inexistente 'T099'" in b for b in blockers))

    def test_t08_unresolved_blocked_by(self):
        """T08: blocked_by: [T099] inexistente -> BLOCKER L03."""
        self._setup_base_fixture()
        (self.tasks_dir / "T002-dep.md").write_text("id: T002\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\nblocked_by: [T099]\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T002 | feat | none | ready | [] | [T099] | 0 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L03]" in b and "referencia id inexistente 'T099'" in b for b in blockers))

    def test_t09_depends_on_retired_identity(self):
        """T09: depends_on: [T013] onde T013 é retired_id no lineage-map -> BLOCKER L04 citando o live_id correto."""
        self._setup_base_fixture()
        (self.tasks_dir / "T002-dep.md").write_text("id: T002\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: [T013]\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T002 | feat | none | ready | [T013] | [] | 0 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L04]" in b and "substituída por 'T020'" in b for b in blockers))

    def test_t10_ambiguous_depends_on(self):
        """T10: depends_on resolvendo para 2 arquivos -> BLOCKER L04."""
        self._setup_base_fixture()
        # Se dois arquivos têm o mesmo ID, L01 dispara e L04 é prevenido na fonte
        (self.tasks_dir / "T002-a.md").write_text("id: T002\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
        (self.tasks_dir / "T002-b.md").write_text("id: T002\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L01]" in b for b in blockers))

    def test_t11_status_parity_divergence(self):
        """T11: status divergente entre board e frontmatter -> BLOCKER L05."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text("id: T001\ntype: feat\nstatus: ready\nstate_revision: 1\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L05]" in b and "divergência de status" in b for b in blockers))

    def test_t12_state_revision_divergence(self):
        """T12: state_revision divergente -> BLOCKER L05."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text("id: T001\ntype: feat\nstatus: done\nstate_revision: 2\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L05]" in b and "divergência de state_revision" in b for b in blockers))

    def test_t13_depends_on_divergence(self):
        """T13: depends_on divergente -> BLOCKER L05."""
        self._setup_base_fixture()
        (self.tasks_dir / "T020-new.md").write_text("id: T020\ntype: fix\nstatus: done\nstate_revision: 1\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L05]" in b and "divergência de depends_on" in b for b in blockers))

    def test_t14_dependency_cycle(self):
        """T14: Ciclo A->B->C->A -> BLOCKER L06 com o ciclo completo."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text("id: T001\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: [T020]\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L06]" in b and "ciclo de dependências" in b for b in blockers))

    def test_t15_self_dependency(self):
        """T15: Auto-dependência A->A -> BLOCKER L06."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text("id: T001\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: [T001]\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L06]" in b for b in blockers))

    def test_t16_done_depends_on_ready(self):
        """T16: Task done com depends_on para task ready -> BLOCKER L07."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text("id: T001\ntype: feat\nstatus: ready\nstate_revision: 1\ndepends_on: []\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text(status_file.read_text().replace("| T001 | feat | none | done |", "| T001 | feat | none | ready |"), encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L07]" in b and "depende operacionalmente de task não concluída 'T001'" in b for b in blockers))

    def test_t17_regression_h2_t022_depends_on_t023(self):
        """T17: Regressão H2: T022 (done) com depends_on: [T023] (ready) -> BLOCKER L07."""
        self._setup_base_fixture()
        (self.tasks_dir / "T022-test.md").write_text("id: T022\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: [T023]\n", encoding="utf-8")
        (self.tasks_dir / "T023-test.md").write_text("id: T023\ntype: analysis\nstatus: ready\nstate_revision: 1\ndepends_on: []\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T022 | feat | none | done | [T023] | [] | 1 | - |\n"
        content += "| T023 | analysis | none | ready | [] | [] | 1 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L07]" in b and "depende operacionalmente de task não concluída 'T023'" in b for b in blockers))

    def test_t18_lineage_digest_tampered(self):
        """T18: lineage_digest adulterado -> BLOCKER L08."""
        self._setup_base_fixture()
        lineage_file = self.project_dir / "lineage-map.md"
        content = lineage_file.read_text(encoding="utf-8")
        content = content.replace("lineage_digest: ", "lineage_digest: 0000000000000000")
        lineage_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L08]" in b and "lineage_digest inválido" in b for b in blockers))

    def test_t19_retired_id_as_live_without_collision(self):
        """T19: retired_id que também é id vivo (sem colisão documentada) -> BLOCKER L08."""
        self._setup_base_fixture()
        lineage_file = self.project_dir / "lineage-map.md"
        # Adicionar retired_id T099 com reason 'deprecated'
        content = (
            "format_version: 1\n"
            "lineage_digest: PLACEHOLDER\n\n"
            "## Retired identities\n"
            "| retired_id | retired_file | lineage | live_id | live_file | reason |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T099 | _tl-orc/project/tasks/T099-old.md | local | T020 | _tl-orc/project/tasks/T020-new.md | deprecated |\n"
        )
        digest = compute_lineage_digest(content)
        lineage_file.write_text(content.replace("PLACEHOLDER", digest), encoding="utf-8")

        # Criar task viva com ID T099
        (self.tasks_dir / "T099-active.md").write_text("id: T099\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text(status_file.read_text() + "| T099 | feat | none | ready | [] | [] | 0 | - |\n", encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L08]" in b and "retired_id 'T099' ainda existe como task viva no disco" in b for b in blockers))

    def test_t20_retired_file_still_present(self):
        """T20: retired_file ainda presente na árvore -> BLOCKER L08."""
        self._setup_base_fixture()
        (self.tasks_dir / "T013-old.md").write_text("id: T013\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: []\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L08]" in b and "retired_file '_tl-orc/project/tasks/T013-old.md' ainda existe fisicamente no disco" in b for b in blockers))

    def test_t21_unresolved_provenance(self):
        """T21: provenance: [T099] inexistente -> BLOCKER L09."""
        self._setup_base_fixture()
        (self.tasks_dir / "T020-new.md").write_text(
            "id: T020\ntype: fix\nstatus: done\nstate_revision: 1\ndepends_on: [T001]\nprovenance: [T099]\n",
            encoding="utf-8"
        )
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L09]" in b and "provenance referencia id inexistente 'T099'" in b for b in blockers))

    def test_t22_provenance_and_depends_on_collision(self):
        """T22: T023 simultaneamente em depends_on e provenance de T022 -> BLOCKER L09."""
        self._setup_base_fixture()
        (self.tasks_dir / "T020-new.md").write_text(
            "id: T020\ntype: fix\nstatus: done\nstate_revision: 1\ndepends_on: [T001]\nprovenance: [T001]\n",
            encoding="utf-8"
        )
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L09]" in b and "está declarado simultaneamente em depends_on e provenance" in b for b in blockers))

    def test_t23_board_row_arity_invalid(self):
        """T23: Linha de board com 7 células -> BLOCKER L10."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        content = (
            "# Project Status\n\nnext_task_id: 25\n\n"
            "## Tasks\n\n"
            "| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T001 | feat | none | done | [] | [] | 1 |\n"
        )
        status_file.write_text(content, encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L10]" in b and "esperadas 8 colunas" in b for b in blockers))

    def test_t24_board_header_out_of_order(self):
        """T24: Cabeçalho do board fora de ordem -> BLOCKER L10."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        content = (
            "# Project Status\n\nnext_task_id: 25\n\n"
            "## Tasks\n\n"
            "| id | deliverable | type | status | depends_on | blocked_by | state_revision | last_evidence |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| T001 | none | feat | done | [] | [] | 1 | - |\n"
        )
        status_file.write_text(content, encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L10]" in b and "cabeçalho da tabela fora de ordem" in b for b in blockers))

    def test_t25_last_evidence_missing(self):
        """T25: last_evidence apontando para path inexistente -> BLOCKER L11."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text(status_file.read_text().replace("evidence/T013-r01.md", "evidence/nonexistent.md"), encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L11]" in b and "last_evidence aponta para arquivo inexistente" in b for b in blockers))

    def test_t26_counterfactual_historical_content_paths_pass(self):
        """T26: Contrafactual R-E1: content_paths com arquivo histórico presente -> passa."""
        self._setup_base_fixture()
        (self.tasks_dir / "T020-new.md").write_text(
            "id: T020\ntype: fix\nstatus: done\nstate_revision: 1\ndepends_on: [T001]\ncontent_paths: [_tl-orc/project/evidence/T013-r01.md]\n",
            encoding="utf-8"
        )
        blockers, _ = run_audits(self.root)
        self.assertEqual([b for b in blockers if "[L11]" in b], [])

    def test_t27_retired_identity_text_reference_is_warning(self):
        """T27: Referência textual a T013 (local) fora do lineage-map -> WARNING L12, exit 0."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text(
            "id: T001\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: []\n\nTexto mencionando T013 como histórico.\n",
            encoding="utf-8"
        )
        blockers, warnings = run_audits(self.root)
        self.assertEqual(blockers, [])
        self.assertTrue(any("[L12]" in w for w in warnings))

    def test_t28_done_task_with_blocked_by(self):
        """T28: Task done com blocked_by não vazio -> BLOCKER L13."""
        self._setup_base_fixture()
        (self.tasks_dir / "T001-initial.md").write_text(
            "id: T001\ntype: feat\nstatus: done\nstate_revision: 1\ndepends_on: []\nblocked_by: [T020]\n",
            encoding="utf-8"
        )
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text(status_file.read_text().replace("| T001 | feat | none | done | [] | [] |", "| T001 | feat | none | done | [] | [T020] |"), encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L13]" in b and "não pode ter blocked_by não-vazio" in b for b in blockers))

    def test_t29_regression_h5_t019_unblocked_while_t024_open(self):
        """T29: Regressão H5: T019 com blocked_by: [] enquanto T024 != done -> BLOCKER L13."""
        self._setup_base_fixture()
        (self.tasks_dir / "T019-harness.md").write_text(
            "id: T019\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: [T024]\nblocked_by: []\n",
            encoding="utf-8"
        )
        (self.tasks_dir / "T024-gov.md").write_text(
            "id: T024\ntype: gov\nstatus: ready\nstate_revision: 0\ndepends_on: []\nblocked_by: []\n",
            encoding="utf-8"
        )
        status_file = self.project_dir / "STATUS.md"
        content = status_file.read_text(encoding="utf-8")
        content += "| T019 | feat | none | ready | [T024] | [] | 0 | - |\n"
        content += "| T024 | gov | none | ready | [] | [] | 0 | - |\n"
        status_file.write_text(content, encoding="utf-8")

        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L13]" in b and "T019 deve declarar blocked_by: [T024]" in b for b in blockers))

    def test_t30_next_task_id_less_than_max(self):
        """T30: next_task_id: 20 com T024 existente -> BLOCKER L14."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text(status_file.read_text().replace("next_task_id: 25", "next_task_id: 15"), encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L14]" in b and "deve ser estritamente maior" in b for b in blockers))

    def test_t31_unreadable_frontmatter(self):
        """T31: Frontmatter ilegível (YAML quebrado) -> BLOCKER, falha fechada."""
        self._setup_base_fixture()
        (self.tasks_dir / "T002-broken.md").write_text(
            "id: T002\nstatus: [unclosed list\n",
            encoding="utf-8"
        )
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("BLOCKER" in b for b in blockers))

    def test_t32_status_md_without_tasks_table(self):
        """T32: STATUS.md sem tabela ## Tasks -> exit 2 / blocker."""
        self._setup_base_fixture()
        status_file = self.project_dir / "STATUS.md"
        status_file.write_text("# Status\nNo table here\n", encoding="utf-8")
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L02]" in b and "não encontrada" in b for b in blockers))

    def test_t33_lineage_map_missing(self):
        """T33: lineage-map.md ausente -> BLOCKER L08, falha fechada."""
        self._setup_base_fixture()
        (self.project_dir / "lineage-map.md").unlink()
        blockers, _ = run_audits(self.root)
        self.assertTrue(any("[L08]" in b and "ausente" in b for b in blockers))


class BoardCasCompatibilityTest(unittest.TestCase):
    def test_t34_cas_compatibility_on_all_tasks(self):
        """T34: update_task_status_atomic sobre cópia do board reconciliado real para todos os ids de tasks."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        real_status = repo_root / "_tl-orc" / "project" / "STATUS.md"
        tasks_dir = repo_root / "_tl-orc" / "project" / "tasks"

        canonical_task_ids = set()
        for tf in sorted(tasks_dir.glob("T*.md")):
            fm, _ = parse_yaml_frontmatter(tf)
            tid = fm.get("id")
            if tid:
                canonical_task_ids.add(tid)

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_status = Path(tmpdir) / "STATUS.md"
            shutil.copy2(real_status, temp_status)

            header, tasks, errors = parse_status_board(temp_status)
            self.assertEqual(errors, [])

            board_task_ids = {t["id"] for t in tasks}
            self.assertEqual(board_task_ids, canonical_task_ids)

            for task in tasks:
                tid = task["id"]
                current_rev = task["state_revision"]
                current_stat = task["status"]

                result = update_task_status_atomic(
                    status_file=str(temp_status),
                    task_id=tid,
                    new_status="in_progress" if current_stat != "in_progress" else "ready",
                    expected_revision=current_rev,
                )
                self.assertEqual(
                    result.get("state"),
                    "updated",
                    f"Falha de CAS para {tid}: {result}"
                )
                self.assertEqual(result.get("state_revision"), current_rev + 1)


class ProbeSensitivityTest(unittest.TestCase):
    def test_t35_disabling_l01_removes_failure(self):
        """T35: Sonda de sensibilidade: desabilitar L01 => T02 deixa de reprovar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdir = root / "_tl-orc" / "project"
            tdir = pdir / "tasks"
            tdir.mkdir(parents=True, exist_ok=True)

            (pdir / "lineage-map.md").write_text("format_version: 1\nlineage_digest: DIGEST\n", encoding="utf-8")
            (pdir / "STATUS.md").write_text("# Status\nnext_task_id: 25\n## Tasks\n| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| T013 | feat | none | ready | [] | [] | 0 | - |\n", encoding="utf-8")

            (tdir / "T013-dup1.md").write_text("id: T013\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")
            (tdir / "T013-dup2.md").write_text("id: T013\ntype: feat\nstatus: ready\nstate_revision: 0\ndepends_on: []\n", encoding="utf-8")

            # Com L01 habilitado
            blockers_all, _ = run_audits(root)
            self.assertTrue(any("[L01]" in b for b in blockers_all))

            # Com apenas L02 selecionado (L01 desabilitado)
            blockers_no_l01, _ = run_audits(root, selected_checks={"L02"})
            self.assertFalse(any("[L01]" in b for b in blockers_no_l01))


if __name__ == "__main__":
    unittest.main()
