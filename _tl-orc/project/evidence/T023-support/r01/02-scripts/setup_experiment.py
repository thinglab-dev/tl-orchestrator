#!/usr/bin/env python3
"""
setup_experiment.py
Prepares dir_A, dir_B, 01-inputs, and 02-manifest for T023.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

def find_repo_root() -> Path:
    if os.environ.get("REPO_ROOT"):
        return Path(os.environ["REPO_ROOT"]).resolve()
    for start in [Path(__file__).resolve().parent, Path.cwd().resolve()]:
        for p in [start] + list(start.parents):
            if (p / "_tl-orc").is_dir():
                return p
    return Path.cwd().resolve()

def find_base_dir() -> Path:
    if os.environ.get("EXPERIMENT_DIR"):
        return Path(os.environ["EXPERIMENT_DIR"]).resolve()
    cur = Path(__file__).resolve().parent
    if cur.name == "02-scripts":
        return cur.parent
    return cur

REPO_ROOT = find_repo_root()
BASE_DIR = find_base_dir()
SNAPSHOT_SRC = REPO_ROOT / "_tl-orc/project/evidence/T012-support/r01/06-snapshot-dir_A"
HISTORICAL_INPUTS = REPO_ROOT / "_tl-orc/project/evidence/T012-support/r01/01-pilot-inputs"

DIR_A = BASE_DIR / "dir_A"
DIR_B = BASE_DIR / "dir_B"
INPUTS_DIR = BASE_DIR / "01-inputs"
MANIFEST_DIR = BASE_DIR / "02-manifest"

print(">>> 1. Cleaning and cloning dir_A and dir_B...")
for target in [DIR_A, DIR_B]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SNAPSHOT_SRC, target)
print(">>> dir_A and dir_B cloned from snapshot.")

# Verify byte-for-byte identity
diff_proc = subprocess.run(["diff", "-r", str(DIR_A), str(DIR_B)], capture_output=True, text=True)
if diff_proc.returncode != 0:
    print("ERROR: dir_A and dir_B differ!")
    sys.exit(1)
print(">>> dir_A and dir_B are 100% byte-identical.")

# Run validate_repository.py on both
for label, d in [("dir_A", DIR_A), ("dir_B", DIR_B)]:
    val = subprocess.run([sys.executable, "scripts/validate_repository.py"], cwd=d, capture_output=True, text=True)
    if val.returncode != 0:
        print(f"ERROR: validate_repository.py failed in {label}: {val.stderr}")
        sys.exit(1)
    print(f">>> {label} structural validation: OK (exit code 0)")

print(">>> 2. Setting up 01-inputs...")
INPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Copy normative-rubric.md
rubric_src = HISTORICAL_INPUTS / "normative-rubric.md"
rubric_dst = INPUTS_DIR / "normative-rubric.md"
shutil.copy2(rubric_src, rubric_dst)

# Copy and sanitize arm-a-history.md
history_src = HISTORICAL_INPUTS / "arm-a-history.md"
history_dst = INPUTS_DIR / "arm-a-history.md"
hist_text = history_src.read_text(encoding="utf-8")
hist_text = hist_text.replace(str(REPO_ROOT), "<repo-root>")
username = os.environ.get("USER") or Path.home().name
if username:
    hist_text = hist_text.replace(username, "user")
priv_tmp = "/" + "private/" + "tmp"
hist_text = re.sub(re.escape(priv_tmp) + r"/claude-\d+/[^/]+/[^/]+/scratchpad/t009", "<scratchpad>/t009", hist_text)
hist_text = re.sub(re.escape(priv_tmp) + r"/claude-\d+/[^/]+/[^/]+/tasks/", "<tasks>/", hist_text)
hist_text = re.sub(re.escape(priv_tmp) + r"/[^\s\"'<>]+", "<tmp-path>", hist_text)
hist_text = re.sub(re.escape(priv_tmp), "<tmp-dir>", hist_text)
hist_text = re.sub(r"/Users/[a-zA-Z0-9_-]+", "<home>", hist_text)
hist_text = re.sub(r"-Users-[a-zA-Z0-9_-]+-", "-Users-clean-", hist_text)
history_dst.write_text(hist_text, encoding="utf-8")

# Generate updated short-resume-package.md with verified SHA-256 hashes
files_to_hash = [
    ("_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md", "Especificação e estado da Task T009"),
    ("_tl-orc/project/evidence/T009-r02.md", "Parecer oficial íntegro do Checker r02"),
    ("_tl-orc/PROJECT.md", "Política de governança e perfis locais"),
    ("prompts/orchestrator.md", "Contrato do papel Orquestrador"),
    ("prompts/orchestrator-perfis.md", "Perfis de despacho e regras de independência"),
    ("prompts/orchestrator-playbook.md", "Playbook de condução e ciclos"),
    ("prompts/maker.md", "Contrato do papel Maker"),
    ("prompts/checker-report-only.md", "Contrato do papel Checker"),
    ("schemas/review-result.schema.json", "Schema do parecer do Checker"),
    ("schemas/classification-result.schema.json", "Schema do resultado da classificação"),
    ("docs/WORK_MODEL.md", "Modelo de trabalho e ciclo de vida de tarefas"),
    ("docs/MODEL_ROUTING.md", "Cartões e catálogo oficial de roteamento"),
]

calculated_hashes = {}
table_rows = []
for rel_path, desc in files_to_hash:
    target_f = DIR_B / rel_path
    if not target_f.exists():
        print(f"ERROR: File {rel_path} not found in DIR_B!")
        sys.exit(1)
    sha = hashlib.sha256(target_f.read_bytes()).hexdigest()
    calculated_hashes[rel_path] = sha
    table_rows.append(f"| `{rel_path}` | {desc} | `{sha}` |")

table_md = "\n".join(table_rows)

package_content = f"""# Pacote Curto de Retomada (Índice Aberto de Navegação)

> [!IMPORTANT]
> Este pacote atua estritamente como **índice derivado de navegação e conferência obrigatória**, sem autoridade normativa própria nem presunção de veracidade. Todas as decisões de condução devem ser fundamentadas pela inspeção direta das fontes oficiais apontadas abaixo.

## 1. Identidade Qualificada Completa
- `active_work_ref`: `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`
- `fase_corrente`: `rework` (ou proposição da próxima fase após `review` r02 com `changes_requested`)
- `state_revision`: 2
- `spec_revision`: 4197dea48f75cd14
- `content_id`: 0de10d60149cf7c038a0954c6aec302c9fcd111e:97b3612674fa4aa5
- `rework_round`: 2 (concluído; próximo ciclo é rework 3 ou escalonamento consultivo)

## 2. Governança & Política Ativa
- `politica_path`: `_tl-orc/PROJECT.md`
- `instrucao_usuario`: "Autorizo executar a T009 como analysis com o piloto delimitado"
- `branch_autorizada`: `analysis/t009-semantic-validation`
- `escopo_autorizado`: Somente os `content_paths` de T009 (`_tl-orc/project/evidence/T009-analysis.md`, `_tl-orc/project/evidence/T009-mechanical-check.py`, `_tl-orc/project/evidence/T009-cases`). Proibida alteração de arquivos do pacote distribuído ou escrita fora de evidência do projeto.
- `pins_e_restricoes`: Checker com restrição `required` e família distinta de toda autoria efetiva (participantes na autoria: Google e Anthropic).

## 3. Estado Operacional da Unidade
- `veredito_rodada_anterior`: `changes_requested`
- `parecer_checker_ref`: `_tl-orc/project/evidence/T009-r02.md`
- `resumo_achados_checker`:
  - **R1 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:130` — AC02: ocorrência textual de um ID ainda é aceita como registro de medição local, inclusive com âncora ou linha inexistente.
  - **R2 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:488` — AC02: derivação de proxy aceita menção a tarefa sem requisito de custo e ignora escopo delimitado no cartão.
  - **R3 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:431` — AC03: fallback de independência aceita texto arbitrário como prova de indisponibilidade e seleciona candidato indisponível.
  - **R4 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:570` — AC03: família desconhecida é tratada como distinta, permitindo contornar required.
  - **R5 (medium, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:514` — AC03: ausência de família independente sob required virou defeito mecânico do objeto, contrariando a separação entre validade e resolução.
- `proximo_passo_previsto`: Propor formalmente o encaminhamento da unidade (rework ou escalonamento consultivo fundamentado) e preparar o briefing correspondente em modo somente leitura (sem despacho efetivo).

## 4. Índice de Fontes Oficiais & Checksums (SHA-256 Verificados)
As seguintes fontes oficiais constituem a base documental da unidade e devem ser conferidas:

| Caminho Relativo | Descrição | SHA-256 |
| :--- | :--- | :--- |
{table_md}
"""

package_dst = INPUTS_DIR / "short-resume-package.md"
package_dst.write_text(package_content, encoding="utf-8")
print(f">>> short-resume-package.md written with verified hashes to {package_dst}")

print(">>> 3. Generating 02-manifest/experiment-manifest.json...")
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

manifest_data = {
    "task_id": "T023",
    "experiment": "Piloto de Retomada Curta entre Ciclos e Economia de Contexto",
    "timestamp_utc": "2026-09-16T21:30:00Z",
    "git_base_commit": "3b7ff25ce4203541eb563a25eb8429efef7f0ab2",
    "git_branch": "feat/t023-context-economy-pilot",
    "seed": 42,
    "advisor_role": {
        "classification_ref": "06-classification/advisor-role-classification.json",
        "harness": "agy",
        "model": "gemini-3.1-pro-high",
        "effort": "high",
        "family": "Google (cross-family consultivo em modo Debater)",
        "recommendation": "Aprovação do avanço experimental com ampliação de margem do sub-teto do Braço B para até 12 requisições e teto global de 18 requisições."
    },
    "experimental_role": {
        "classification_ref": "06-classification/experimental-role-classification.json",
        "harness": "codex",
        "model": "gpt-5.6-terra",
        "effort": "high",
        "frozen_symmetric": True,
        "arms": ["Arm_A", "Arm_B"]
    },
    "evaluator_role": {
        "classification_ref": "06-classification/evaluator-role-classification.json",
        "harness": "agy",
        "model": "gemini-3.1-pro-high",
        "effort": "high",
        "independence_policy": "required",
        "family": "Google (independent of OpenAI experimental author)"
    },
    "budget": {
        "max_ai_requests": 18,
        "max_input_tokens": 3400000,
        "max_output_tokens": 105000,
        "max_total_tokens": 3505000,
        "sub_budgets": {
            "preparation": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
            "classification": {"requests": 3, "input_tokens": 180000, "output_tokens": 10000},
            "advisor": {"requests": 1, "input_tokens": 100000, "output_tokens": 10000},
            "arm_a": {"requests": 1, "input_tokens": 2000000, "output_tokens": 25000},
            "arm_b": {"requests": 10, "input_tokens": 500000, "output_tokens": 30000},
            "evaluation": {"requests": 1, "input_tokens": 100000, "output_tokens": 10000},
            "checker": {"requests": 1, "input_tokens": 500000, "output_tokens": 15000},
            "contingency": {"requests": 1, "input_tokens": 20000, "output_tokens": 5000}
        }
    },
    "input_hashes": {
        "short-resume-package.md": hashlib.sha256(package_dst.read_bytes()).hexdigest(),
        "normative-rubric.md": hashlib.sha256(rubric_dst.read_bytes()).hexdigest(),
        "arm-a-history.md": hashlib.sha256(history_dst.read_bytes()).hexdigest(),
    },
    "snapshot_file_hashes": calculated_hashes
}

manifest_file = MANIFEST_DIR / "experiment-manifest.json"
manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f">>> Manifest written to {manifest_file}")
print(">>> Phase 2 Setup completed successfully!")
