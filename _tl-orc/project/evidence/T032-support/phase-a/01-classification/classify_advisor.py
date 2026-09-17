#!/usr/bin/env python3
"""
classify_advisor.py - Invokes Classifier (agy gemini-3.8-flash-medium) to classify
the Advisor role for Task T032 Phase A under Schema v3 (Minimum Sufficient Capability).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[5])).resolve()
SCRATCH_DIR = Path(__file__).resolve().parent
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

BRIEFING_FILE = SCRATCH_DIR / "advisor-role-briefing.md"
RAW_OUT_FILE = SCRATCH_DIR / "advisor-role-raw.txt"
JSON_OUT_FILE = SCRATCH_DIR / "advisor-role-classification.json"

briefing_text = """Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar o papel Advisor na fase debate para a Task T032 e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json, sem texto antes ou depois.

O JSON DEVE CONTER OBRIGATORIAMENTE ESTES CAMPOS NA RAIZ:
- schema_version: 3
- story_id: "T032"
- phase: "debate"
- context_revision: "tl-orchestrator@69d8351"
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
      "reason": "Advisor consultivo independente em modo Debater / Strategic Challenge para desafio da arquitetura e contratos de T032 antes do freeze da spec. Eleito candidato cross-family independente (Anthropic Claude Sonnet High ou OpenAI Codex Terra High) contra a proposta formulada por Google Antigravity.",
      "tie_break_applied": null,
      "evaluations": [
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "uncertainty": null,
          "reason": "Candidato cross-family primário da família Anthropic elegível e funcional no runtime."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-terra", "transport-openai"],
          "uncertainty": null,
          "reason": "Candidato cross-family alternativo da família OpenAI elegível e funcional no runtime."
        },
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "catalog_eligible": false,
          "technical_adequacy": "insufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-flash", "transport-flash"],
          "uncertainty": null,
          "reason": "Mesma família Google da proposta desafiada, violando preferência cross-family do Advisor."
        }
      ],
      "candidates": [
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "dispatch_role": "primary",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "cost_basis": "token_price_only",
          "reason": "Candidato primário cross-family independente (Anthropic) elegível e disponível no runtime."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "dispatch_role": "fallback",
          "evidence_ids": ["price-terra", "transport-openai"],
          "cost_basis": "token_price_only",
          "reason": "Fallback cross-family alternativo (OpenAI) elegível e disponível no runtime."
        }
      ]
    }
  }

## Contexto e Fatos
- Trata-se da consulta mandatória ao papel Advisor (consultivo, modo Debater) para a Task T032 (Protocolo de Retomada Curta e Transição entre Ciclos) antes do freeze da spec.
- O Advisor desafiará os 9 pontos do challenge packet definidos pelo mantenedor (custo real vs deslocamento, dados mínimos, não-autoridade do pacote, detecção de drift, condições de nova sessão, reconstrução de fontes, prevenção de bootstrap volumoso, automação vs limiares, estados fora da conversa).
- A proposta inicial foi formulada pelo Orquestrador sob o harness Antigravity (família Google).
- O papel Advisor opera sob preferência estrita por cross-family (contra-família da proposta desafiada) em sessão limpa isolada.
- Os harnesses comprovadamente disponíveis e funcionais no ambiente são: Claude (Anthropic), Codex (OpenAI) e Agy (Google).
- As famílias cross-family elegíveis e funcionais são Anthropic (Claude Sonnet High) como primário e OpenAI (Codex Terra High) como fallback.
- A família Google é preterida para esta função consultiva para assegurar independência de julgamento.

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

try:
    data = json.loads(raw)
except Exception as exc:
    print(f"ERROR: could not parse JSON: {exc}\nRAW:\n{raw}")
    sys.exit(1)

JSON_OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f">>> Parsed JSON written to {JSON_OUT_FILE}")

val_cmd = [
    sys.executable,
    str(REPO_ROOT / "scripts" / "validate_classification.py"),
    "--file", str(JSON_OUT_FILE),
    "--story", "T032",
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
