#!/usr/bin/env python3
"""
classify_advisor_role.py
Invokes Classifier (agy gemini-3.8-flash-medium) to classify the Advisor role
for Task T023 under Schema v3 (Minimum Sufficient Capability) with cross-family preference.
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

BRIEFING_FILE = SCRATCH_DIR / "advisor-role-briefing.md"
RAW_OUT_FILE = SCRATCH_DIR / "advisor-role-raw.txt"
JSON_OUT_FILE = SCRATCH_DIR / "advisor-role-classification.json"

briefing_text = """Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar a fase indicada e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json, sem texto antes ou depois.

O JSON DEVE CONTER OBRIGATORIAMENTE ESTES CAMPOS NA RAIZ:
- schema_version: 3
- story_id: "T023"
- phase: "debate"
- context_revision: "tl-orchestrator@3b7ff25"
- catalog_revision: "PROJECT.md-2026-09-07"
- confidence: "high"
- facts: [lista de strings descrevendo os fatos]
- uncertainties: [lista de strings descrevendo incertezas]
- reclassify_when: [lista de strings descrevendo condições de reclassificação]
- roles: {
    "advisor": {
      "tier": "normal",
      "selection_status": "conclusive",
      "selection_basis": "minimum_sufficient",
      "escalation_reason": null,
      "reason": "Advisor consultivo em modo Debater para saneamento de protocolo experimental antes do congelamento. Eleito primário da família Google (cross-family contra proposta OpenAI).",
      "tie_break_applied": null,
      "evaluations": [
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-flash", "transport-flash"],
          "uncertainty": null,
          "reason": "Candidato cross-family primário da família Google elegível e disponível no runtime."
        },
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "uncertainty": null,
          "reason": "Indisponível no runtime por expiração de sessão OAuth (pre_dispatch_unavailable)."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "catalog_eligible": false,
          "technical_adequacy": "insufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-terra", "transport-openai"],
          "uncertainty": null,
          "reason": "Mesma família OpenAI da proposta experimental desafiada, violando preferência cross-family do Advisor."
        }
      ],
      "candidates": [
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "dispatch_role": "primary",
          "evidence_ids": ["price-flash", "transport-flash"],
          "cost_basis": "token_price_only",
          "reason": "Candidato primário cross-family (Google) elegível e disponível no runtime."
        }
      ]
    }
  }

## Contexto e Fatos
- Trata-se do papel de Advisor (consultivo, modo Debater) do piloto de retomada curta entre ciclos (T023).
- O Advisor debaterá a proposta experimental, o orçamento calibrado (16 reqs globais / sub-teto de 10 em B), a regra ativa fail-closed de parada em run_arms.py e a sanitização estrita de caminhos privados locais antes do congelamento experimental.
- A proposta a ser desafiada utiliza o harness Codex (família OpenAI).
- Conforme prompts/orchestrator-perfis.md, o papel Advisor exige preferência estrita por cross-family (contra-família da proposta desafiada) em sessão limpa isolada.
- O harness Claude (família Anthropic) está fisicamente indisponível no ambiente runtime atual (sessão OAuth expirada / pre_dispatch_unavailable). Portanto, modelos do Claude não podem ser selecionados como primários utilizáveis nesta execução (dispatchable: false).
- Os harnesses comprovadamente disponíveis e funcionais no ambiente são: Codex (OpenAI) e Agy (Google).
- Como a proposta a ser desafiada é OpenAI (Codex), a família Google (Agy) é a candidata cross-family elegível e disponível primária.
- Sem frases de overselection.

## Formato de saída
Responda APENAS com o JSON válido de acordo com o Schema v3. Sem markdown, sem ```json, sem comentários.
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

raw = proc.stdout.strip()
if raw.startswith("```"):
    raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
    raw = re.sub(r"\n```$", "", raw)

data = json.loads(raw)
JSON_OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f">>> Parsed JSON written to {JSON_OUT_FILE}")

val_cmd = [
    sys.executable,
    str(REPO_ROOT / "scripts" / "validate_classification.py"),
    "--file", str(JSON_OUT_FILE),
    "--story", "T023",
    "--phase", "debate",
    "--schema-version", "3"
]
print(f">>> Running validator: {' '.join(val_cmd)}")
val_proc = subprocess.run(val_cmd, capture_output=True, text=True)
print("STDOUT:", val_proc.stdout)
print("STDERR:", val_proc.stderr)
print(f"Validation exit code: {val_proc.returncode}")
if val_proc.returncode != 0:
    sys.exit(val_proc.returncode)
print(">>> Advisor classification successfully validated!")
