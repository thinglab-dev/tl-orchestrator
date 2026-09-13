#!/usr/bin/env python3
"""
run-arm-b.py
Executa o Braço B (Sessão Nova + Pacote Curto de Retomada) no dir_B.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DIR_B = Path("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/dir_B")
SCRATCH = Path("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot")
PACKAGE_FILE = SCRATCH / "short-resume-package.md"
resume_pkg_text = PACKAGE_FILE.read_text(encoding="utf-8")

prompt_text = f"""Você é o Orquestrador do tl-orchestrator iniciando uma sessão limpa de trabalho nesta raiz deste repositório (branch analysis/t009-semantic-validation).
Você recebeu como instrução de inicialização o seguinte Pacote Curto de Retomada (arquivo `{PACKAGE_FILE}`, reproduzido abaixo):

--- INÍCIO DO PACOTE CURTO DE RETOMADA ---
{resume_pkg_text}
--- FIM DO PACOTE CURTO DE RETOMADA ---

IMPORTANTE: Conforme o princípio de não-tautologia, este pacote atua estritamente como índice derivado de navegação e conferência obrigatória, sem presunção de veracidade. Inspecione diretamente com ferramentas de leitura (Read, Glob, Grep) as fontes oficiais apontadas no pacote para verificar os dados antes de decidir.

### Regras Normativas Vigentes (Caso Adaptado T010 / T014):
1. **Procedência por tipo e conteúdo (T010 AC02)**: No briefing da próxima fase, exigir identificação formal e comprovação rigorosa da procedência de cada tipo de dado (IDs locais verificados por âncora/linha em arquivos de evidência sob `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`; menção expressa de custo monetário/tokens em cartões para proxies de tarefa; distinção entre timeout e indisponibilidade comprovada para fallbacks).
2. **Escalonamento consultivo (T010 AC03)**: É permitido propor escalonamento consultivo (fase `debate` / consulta) fundamentado na reincidência de achados da classe procedência, ou propor novo ciclo de rework com briefing delimitado.
3. **Política Global Padrão de Participantes (T014)**: Composição padrão Maker `Gemini 3.8 Flash High` (Agy) e Checker `Codex GPT-5.6 Terra High`, sob filtro estrito de `checker_independence: required` subordinado à autoria efetiva (participantes em T009: Google e Anthropic, mantendo Codex como revisor independente prioritário).

### Instruções de Execução:
1. Avalie formalmente a situação da unidade T009 a partir do parecer do Checker r02 e conferência das fontes oficiais.
2. Determine e proponha formalmente o encaminhamento da unidade (rework de implementação ou escalonamento consultivo fundamentado).
3. Elabore o briefing completo e estruturado para a próxima fase (alvo, papel, escopo, regras de procedência por tipo e conteúdo, e ações necessárias para R1–R5).

AVISO RESTRITIVO OBRIGATÓRIO:
Este é um teste experimental em modo SOMENTE LEITURA. NÃO modifique nenhum arquivo em disco e NÃO despache nenhum agente Maker ou Checker efetivo. Limite-se a emitir em sua resposta final a proposta de condução e o briefing estruturado.
"""

claude_proj_dir = Path.home() / ".claude/projects/-Users-albertiano--gemini-antigravity-brain-c35bdc15-8391-494c-8de0-190630cac49e-scratch-t012-pilot-dir-B"
before_files = set(claude_proj_dir.glob("*.jsonl")) if claude_proj_dir.exists() else set()

cmd = [
    "claude",
    "-p", prompt_text,
    "--dangerously-skip-permissions",
    "--tools", "Read,Glob,Grep"
]

print(">>> Starting Arm B execution...")
t0 = time.time()
with open("/dev/null", "r") as devnull:
    proc = subprocess.run(cmd, cwd=DIR_B, stdin=devnull, capture_output=True, text=True)
t1 = time.time()
wall_clock = t1 - t0
print(f">>> Arm B finished in {wall_clock:.2f}s with exit code {proc.returncode}")

(SCRATCH / "raw-decision-B.md").write_text(proc.stdout, encoding="utf-8")
(SCRATCH / "raw-decision-B-stderr.txt").write_text(proc.stderr, encoding="utf-8")

# Parse session metrics
after_files = set(claude_proj_dir.glob("*.jsonl")) if claude_proj_dir.exists() else set()
new_files = list(after_files - before_files)
session_file = new_files[0] if new_files else (max(after_files, key=lambda p: p.stat().st_mtime) if after_files else None)

metrics = {
    "arm": "Arm_B",
    "description": "Braço B (Sessão Nova + Pacote Curto de Retomada)",
    "wall_clock_seconds": wall_clock,
    "exit_code": proc.returncode,
    "session_file": str(session_file) if session_file else None,
    "input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "output_tokens": 0,
    "thinking_tokens": 0,
    "turns": 0,
    "tool_calls": [],
    "tool_results_bytes": 0,
}

if session_file and session_file.exists():
    with open(session_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "message" in d and "usage" in d["message"]:
                u = d["message"]["usage"]
                metrics["input_tokens"] += u.get("input_tokens", 0)
                metrics["cache_creation_input_tokens"] += u.get("cache_creation_input_tokens", 0)
                metrics["cache_read_input_tokens"] += u.get("cache_read_input_tokens", 0)
                metrics["output_tokens"] += u.get("output_tokens", 0)
                metrics["thinking_tokens"] += u.get("output_tokens_details", {}).get("thinking_tokens", 0)
                metrics["turns"] += 1
            if d.get("type") == "assistant" or d.get("message", {}).get("role") == "assistant":
                content = d.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "tool_use":
                            metrics["tool_calls"].append({
                                "name": part.get("name"),
                                "input": part.get("input")
                            })
            if d.get("type") == "user" or d.get("message", {}).get("role") == "user":
                content = d.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "tool_result":
                            res_content = str(part.get("content", ""))
                            metrics["tool_results_bytes"] += len(res_content.encode("utf-8"))

(SCRATCH / "arm-b-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(">>> Metrics written to arm-b-metrics.json:")
print(json.dumps(metrics, indent=2))
