#!/usr/bin/env python3
"""
classify_evaluator_role.py
Invokes Classifier to classify the Blind Evaluator role for Task T023
under Schema v3 and checker_independence: required.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[4])).resolve()
SCRATCH_DIR = Path(os.environ.get("CLASSIFICATION_DIR", Path(__file__).resolve().parent)).resolve()
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

BRIEFING_FILE = SCRATCH_DIR / "evaluator-role-briefing.md"
RAW_OUT_FILE = SCRATCH_DIR / "evaluator-role-raw.txt"
JSON_OUT_FILE = SCRATCH_DIR / "evaluator-role-classification.json"

briefing_text = """Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar a fase indicada e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json, sem texto antes ou depois.

## Metadados
- story_id: "T023"
- phase: "review"
- context_revision: "tl-orchestrator@3b7ff25"
- catalog_revision: "PROJECT.md-2026-09-07"
- schema_version: 3
- confidence: "high"
- requested_roles: ["checker"]

## Contexto e Fatos
- Trata-se da avaliação cega das decisões produzidas pelos dois braços experimentais da Task T023 (piloto de retomada curta entre ciclos).
- O alvo de julgamento são as duas decisões cegas sanitizadas ('decision-alpha.md' e 'decision-beta.md') avaliadas contra o gabarito normativo congelado ('normative-rubric.md').
- Autoria participante das decisões de T023: ambas as decisões foram formuladas sob o harness Codex (família OpenAI).
- Política de independência: 'checker_independence: required'. Sob esta regra inegociável, a família OpenAI (autora das decisões avaliadas) está ESTRITAMENTE IMPEDIDA de atuar como avaliadora/revisora independente nesta fase.
- O harness Claude (família Anthropic) está fisicamente indisponível no ambiente operacional (sessão OAuth expirada / pre_dispatch_unavailable).
- O único harness independente, elegível no catálogo e comprovadamente funcional no ambiente runtime é: Agy (Google), com o modelo 'gemini-3.1-pro-high' (effort: high).
- Catálogo permitido para o papel 'checker' conforme _tl-orc/PROJECT.md:
  1. codex / gpt-5.6-terra (effort: high) - família OpenAI. Impedido por checker_independence: required devido à autoria das decisões por OpenAI. (catalog_eligible: false ou technical_adequacy: "insufficient", dispatchable: false).
  2. claude / sonnet (effort: high) - família Anthropic. Indisponível no ambiente operacional (dispatchable: false).
  3. agy / gemini-3.1-pro-high (effort: high) - família Google. Totalmente independente de OpenAI, elegível e disponível (catalog_eligible: true, technical_adequacy: "sufficient", dispatchable: true).
- Cartões de evidência aplicáveis de docs/MODEL_ROUTING.md:
  - "price-flash", "flash-deepswe", "transport-flash" para Agy Gemini
  - "price-terra", "gpt56-coding", "transport-openai" para Codex Terra
  - "price-sonnet", "sonnet-effort", "transport-claude" para Claude Sonnet
- Regras normativas de seleção:
  - Em 'evaluations[]':
    * agy / gemini-3.1-pro-high / high: catalog_eligible: true, technical_adequacy: "sufficient", dispatchable: true, cost_basis: "token_price_only", evidence_ids: ["price-flash", "transport-flash"], reason: "Revisor independente primario da familia Google, nao participante da autoria das decisoes de T023 e funcional no runtime."
    * codex / gpt-5.6-terra / high: catalog_eligible: false, technical_adequacy: "insufficient", dispatchable: false, cost_basis: "token_price_only", evidence_ids: ["price-terra", "transport-openai"], reason: "Impedido sob checker_independence: required por pertencer a mesma familia (OpenAI) que gerou as decisoes avaliadas."
    * claude / sonnet / high: catalog_eligible: true, technical_adequacy: "sufficient", dispatchable: false, cost_basis: "token_price_only", evidence_ids: ["price-sonnet", "transport-claude"], reason: "Indisponivel no runtime por expiracao de sessao OAuth (pre_dispatch_unavailable)."
  - Em candidates[0]: agy / gemini-3.1-pro-high / high com dispatch_role: "primary", selection_status: "conclusive", selection_basis: "escalation", escalation_reason: "checker_family_independence" (ou only_available).
  - Proibido usar frases de overselection.

## Formato de saída
Responda APENAS com o JSON válido de acordo com o Schema v3. Sem markdown, sem ```json, sem texto antes ou depois.
"""

BRIEFING_FILE.write_text(briefing_text, encoding="utf-8")
print(f">>> Briefing written to {BRIEFING_FILE}")

cmd = [
    "agy",
    "--print", briefing_text,
    "--model", "gemini-3.8-flash-medium",
    "--dangerously-skip-permissions"
]

print(">>> Calling Classifier (agy gemini-3.8-flash-medium)...")
proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
RAW_OUT_FILE.write_text(proc.stdout, encoding="utf-8")
print(f">>> Raw output written ({len(proc.stdout)} bytes), exit code {proc.returncode}")

content = proc.stdout.strip()
start = content.find("{")
end = content.rfind("}") + 1
if start != -1 and end != 0:
    json_str = content[start:end]
    data = json.loads(json_str)
    JSON_OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f">>> Parsed JSON written to {JSON_OUT_FILE}")
else:
    print("ERROR: No JSON block found in output!")
    sys.exit(1)

# Validate with validate_classification.py
val_cmd = [
    sys.executable,
    str(REPO_ROOT / "scripts" / "validate_classification.py"),
    "--file", str(JSON_OUT_FILE),
    "--story", "T023",
    "--phase", "review",
    "--schema-version", "3"
]
print(f">>> Running validator: {' '.join(val_cmd)}")
val_proc = subprocess.run(val_cmd, capture_output=True, text=True)
print("STDOUT:", val_proc.stdout)
print("STDERR:", val_proc.stderr)
print(f"Validation exit code: {val_proc.returncode}")
if val_proc.returncode != 0:
    sys.exit(val_proc.returncode)
print(">>> Evaluator role classification successfully validated!")
