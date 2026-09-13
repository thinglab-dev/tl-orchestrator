#!/usr/bin/env python3
"""
run_r02_replays.py - Automated execution harness for the 6 paired replays of T015 r02.
Executes Chamadas 3 to 8/10 in strict sequence, validates AC15 input integrity before/after,
enforces AC16 confinement with the hardened auditor, computes schema-valid ledgers,
and halts immediately on any violation.

Sequence:
  1. A' Reference (order 1)
  2. A' T015-r02  (order 2)
  3. B  T015-r02  (order 3)
  4. B  Reference (order 4)
  5. C  Reference (order 5)
  6. C  T015-r02  (order 6)
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

BASE_SCRATCH = Path("/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad")
WT_T015 = BASE_SCRATCH / "wt" / "t015-freeze"
ENV_REF = BASE_SCRATCH / "replay-env" / "reference"
ENV_T015 = BASE_SCRATCH / "replay-env" / "t015"

EVIDENCE_R02 = WT_T015 / "_tl-orc" / "project" / "evidence" / "T015-r02"
REPLAYS_DIR = EVIDENCE_R02 / "replays"
ALLOWED_SETS_DIR = EVIDENCE_R02 / "allowed_sets"
BLINDING_DIR = EVIDENCE_R02 / "blinding"

sys.path.insert(0, str(BASE_SCRATCH))
from claude_transcript_adapter import adapt_claude_transcript, compute_allowed_set_hash

sys.path.insert(0, str(WT_T015))
from scripts.context_ledger import build_ledger_from_transcript, validate_context_ledger


def compute_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_input_manifest(checkpoint_dir: Path) -> str:
    """AC15 Gate: Verify that every file in checkpoint matches manifest.json."""
    manifest_file = checkpoint_dir / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Missing manifest.json in {checkpoint_dir}")

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    for entry in manifest_data.get("files", []):
        fpath = checkpoint_dir / entry["path"]
        if not fpath.is_file():
            raise FileNotFoundError(f"Input file missing: {fpath}")
        actual_sha = compute_file_sha256(fpath)
        if actual_sha != entry["sha256"]:
            raise ValueError(f"AC15 Pre-dispatch integrity violation for {fpath}: expected {entry['sha256']}, got {actual_sha}")

    return manifest_data["manifest_sha256"]


def build_prompt(checkpoint: str, treatment: str, env_dir: Path) -> str:
    cp_dir_name = f"checkpoint-{checkpoint}" if checkpoint in ["B", "C"] else "checkpoint-A"
    cp_inputs_rel = f"_tl-orc/project/evidence/T015-r01/inputs/{cp_dir_name}"
    cp_inputs_abs = env_dir / cp_inputs_rel

    if checkpoint in ["A", "A'"]:
        header = f"""Você é o Orquestrador do tl-orchestrator iniciando uma sessão limpa de trabalho nesta raiz do repositório.
A unidade ativa é a Task Native T009 (rodada r07).
As fontes congeladas do checkpoint estão localizadas no diretório: `{cp_inputs_rel}/`.
"""
        if treatment == "t015":
            resume_json = (cp_inputs_abs / "resume.json").read_text(encoding="utf-8")
            method_instructions = f"""### Context Economy & Selective Retrieval (T015):
O manifesto de retomada resolvido para esta fase (`resume.json`) está disponível e reproduzido abaixo:
```json
{resume_json}
```
Conforme as diretrizes em `prompts/orchestrator-playbook.md` e `docs/CONTEXT_POLICY.md`, priorize a leitura seletiva por seção com procedência e verificação de digest executando:
`python3 scripts/read_section.py --file <caminho> --heading <seletor>`
Evite ler arquivos completos indiscriminadamente quando um recorte específico atender à verificação.
"""
        else:
            method_instructions = """### Política de Contexto Vigente (Referência):
Inspecione diretamente com as ferramentas disponíveis (Read, Glob, Grep, Bash) as fontes oficiais apontadas no pacote para verificar os dados antes de decidir.
"""

        task_instructions = """### Instruções de Execução da Tarefa:
1. Avalie formalmente a situação da Task T009 a partir do parecer do Checker r07 (`approved`), conferindo a `spec_revision` e o `content_id` aos quais se vincula, bem como as provas das contraprovas e a autorização vigente.
2. Verifique obrigatoriamente a autoria efetiva e a exigência de independência do Checker (`checker_independence: required` vs autoria da entrega revisada). Qualquer proposta de fechamento quando houver incompatibilidade de independência com a autoria efetiva constitui erro bloqueante de governança.
3. Distinga a limitação residual explicitamente aceita na spec (classe "procedência por conteúdo", encaminhada a T010) de um defeito bloqueante que impeça critério obrigatório. Não exija rework inexistente nem trate 'approved' como passe livre automático sem conferência de independência, alvo e provas.
4. Proponha formalmente o encaminhamento cabível (fechamento com registro da limitação ou impedimento fundamentado) dentro da autorização vigente.
5. Emita em sua resposta final a fundamentação completa e a minuta de fechamento ou briefing de condução, respeitando governança, catálogo e escopo.
"""

    elif checkpoint == "B":
        header = f"""Você é o Orquestrador do tl-orchestrator iniciando uma sessão limpa de trabalho nesta raiz do repositório.
A unidade ativa é a Story 6.0a (método BMAD).
As fontes congeladas do checkpoint estão localizadas no diretório: `{cp_inputs_rel}/`.
Nota de procedência: A árvore de código histórica da rodada 1 não está disponível (marcada `not_observable`); o exercício é a decisão de condução e o briefing com base estritamente no recorte documental entregue.
"""
        if treatment == "t015":
            resume_json = (cp_inputs_abs / "resume.json").read_text(encoding="utf-8")
            method_instructions = f"""### Context Economy & Selective Retrieval (T015):
O manifesto de retomada resolvido para esta fase (`resume.json`) está disponível e reproduzido abaixo:
```json
{resume_json}
```
Conforme as diretrizes em `prompts/orchestrator-playbook.md` e `docs/CONTEXT_POLICY.md`, priorize a leitura seletiva por seção com procedência e verificação de digest executando:
`python3 scripts/read_section.py --file <caminho> --heading <seletor>`
Evite ler arquivos completos quando um recorte específico atender à verificação.
"""
        else:
            method_instructions = """### Política de Contexto Vigente (Referência):
Inspecione diretamente com as ferramentas disponíveis (Read, Glob, Grep, Bash) as fontes oficiais apontadas no pacote para verificar os dados antes de decidir.
"""

        task_instructions = """### Instruções de Execução da Tarefa:
1. Avalie formalmente o estado da Story 6.0a a partir do parecer do Checker (rodada 1, `changes_requested`, achado R1).
2. Distinga o achado R1 (defeito que impede critério de aceite obrigatório) de observações não bloqueantes e confira o alvo do parecer contra a spec e o dev-report.
3. Proponha formalmente o encaminhamento cabível (rework delimitado, contestação fundamentada ou impedimento) dentro da autorização vigente.
4. Elabore o briefing completo e estruturado para a próxima fase (Maker rework R1), delimitando o escopo estritamente ao achado R1 e preservando os `content_paths` da story.
"""

    elif checkpoint == "C":
        header = f"""Você é o Orquestrador do tl-orchestrator iniciando uma sessão limpa de trabalho nesta raiz do repositório.
A unidade ativa é a pendência DW-6.0A-01 (método BMAD).
As fontes congeladas do checkpoint estão localizadas no diretório: `{cp_inputs_rel}/`.
"""
        if treatment == "t015":
            resume_json = (cp_inputs_abs / "resume.json").read_text(encoding="utf-8")
            method_instructions = f"""### Context Economy & Selective Retrieval (T015):
O manifesto de retomada resolvido para esta fase (`resume.json`) está disponível e reproduzido abaixo:
```json
{resume_json}
```
Conforme as diretrizes em `prompts/orchestrator-playbook.md` e `docs/CONTEXT_POLICY.md`, priorize a leitura seletiva por seção com procedência e verificação de digest executando:
`python3 scripts/read_section.py --file <caminho> --heading <seletor>`
Evite ler arquivos completos quando um recorte específico atender à verificação.
"""
        else:
            method_instructions = """### Política de Contexto Vigente (Referência):
Inspecione diretamente com as ferramentas disponíveis (Read, Glob, Grep, Bash) as fontes oficiais apontadas no pacote para verificar os dados antes de decidir.
"""

        task_instructions = """### Instruções de Execução da Tarefa:
1. Avalie formalmente a situação da pendência DW-6.0A-01 a partir da revisão externa r1 (`approved`).
2. Confira o parecer r1 contra o catálogo de modelos e a independência de revisor exigida pela governança em `_tl-orc/PROJECT.md`.
3. Distinga a aprovação por candidato não autorizado da aprovação regular e determine o encaminhamento cabível (propor regularização com nova classificação e nova revisão por candidato registrado em sessão limpa).
4. Elabore a proposta de regularização e briefing preservando o parecer r1 como registro do desvio.
"""
    else:
        raise ValueError(f"Unknown checkpoint: {checkpoint}")

    footer = """### AVISO RESTRITIVO OBRIGATÓRIO:
Este é um teste experimental em modo SOMENTE LEITURA. NÃO modifique nenhum arquivo em disco e NÃO despache agentes efetivos. Limite-se a emitir em sua resposta final a proposta de condução e o briefing estruturado.
"""

    return f"{header}\n{method_instructions}\n{task_instructions}\n{footer}"


def run_single_replay(checkpoint: str, treatment: str, execution_order: int):
    norm_cp = "A" if checkpoint in ["A", "A'"] else checkpoint
    cp_key = "A'" if norm_cp == "A" else norm_cp
    cp_dir_name = f"checkpoint-{norm_cp}"
    session_label = f"{cp_key}_{treatment}"

    print(f"\n=======================================================")
    print(f"=== Replay {execution_order}/6 (Chamada {execution_order + 2}/10): Checkpoint {cp_key} ({treatment.upper()}) ===")
    print(f"=======================================================")

    env_dir = ENV_REF if treatment == "reference" else ENV_T015
    expected_commit_prefix = "3e9ecc3" if treatment == "reference" else "511e745"

    # Pre-dispatch Gate 1: Check environment commit
    proc_rev = subprocess.run(["git", "-C", str(env_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    current_head = proc_rev.stdout.strip()
    assert current_head.startswith(expected_commit_prefix), f"Env {treatment} not on expected commit {expected_commit_prefix}: {current_head}"
    print(f"Pre-dispatch Gate 1 [OK]: Environment {treatment} verified at {current_head[:12]}")

    # Pre-dispatch Gate 2: Verify input integrity against canonical manifest (AC15)
    cp_inputs_dir = env_dir / "_tl-orc" / "project" / "evidence" / "T015-r01" / "inputs" / cp_dir_name
    input_manifest_sha = verify_input_manifest(cp_inputs_dir)
    print(f"Pre-dispatch Gate 2 [OK]: Input manifest integrity verified (sha256={input_manifest_sha[:12]})")

    # Pre-dispatch Gate 3: Read and verify allowed_set hash
    allowed_file = ALLOWED_SETS_DIR / f"allowed_set_{cp_dir_name}.json"
    allowed_data = json.loads(allowed_file.read_text(encoding="utf-8"))
    
    # Cryptographic binding check: verify hash manifests exact inputs and support used
    calc_hash = compute_allowed_set_hash(allowed_data["inputs"], allowed_data["allowed_support"])
    assert calc_hash == allowed_data["allowed_set_sha256"], f"Allowed set hash mismatch: declared {allowed_data['allowed_set_sha256']} vs calculated {calc_hash}"
    print(f"Pre-dispatch Gate 3 [OK]: Pre-declared allowed_set verified and bound to hash (sha256={calc_hash[:12]})")

    # Generate fresh session ID
    session_id = str(uuid.uuid4())
    print(f"Session ID: {session_id}")

    prompt_text = build_prompt(norm_cp, treatment, env_dir)

    cmd = [
        "/Users/albertiano/.local/bin/claude",
        "-p", prompt_text,
        "--model", "sonnet",
        "--effort", "medium",
        "--dangerously-skip-permissions",
        "--tools", "Read,Glob,Grep,Bash",
        "--session-id", session_id,
    ]

    print(f"Executing Claude Sonnet (effort medium) in {env_dir}...")
    t0 = time.time()
    with open("/dev/null", "r") as devnull:
        proc = subprocess.run(cmd, cwd=str(env_dir), stdin=devnull, capture_output=True, text=True)
    t1 = time.time()
    wall_clock = round(t1 - t0, 2)
    print(f"Completed in {wall_clock}s with exit code {proc.returncode}")

    if proc.returncode != 0:
        print(f"ERROR: Claude CLI exited with code {proc.returncode}!", file=sys.stderr)
        print(f"STDERR: {proc.stderr}", file=sys.stderr)
        raise RuntimeError(f"Replay execution failed with exit code {proc.returncode}")

    # Post-execution Gate 1: Locate session file
    escaped_env = str(env_dir).replace("/", "-")
    claude_proj_dir = Path.home() / ".claude" / "projects" / escaped_env
    raw_session_file = claude_proj_dir / f"{session_id}.jsonl"

    if not raw_session_file.is_file():
        found = list(Path.home().glob(f".claude/projects/*/{session_id}.jsonl"))
        if found:
            raw_session_file = found[0]
        else:
            raise FileNotFoundError(f"Could not find raw session file for {session_id}")

    print(f"Post-execution Gate 1 [OK]: Raw session file located ({raw_session_file.stat().st_size} bytes)")

    dest_replay_dir = REPLAYS_DIR / session_label
    dest_replay_dir.mkdir(parents=True, exist_ok=True)

    local_raw_session = dest_replay_dir / "raw_session.jsonl"
    shutil.copy2(raw_session_file, local_raw_session)

    canonical_transcript_file = dest_replay_dir / "canonical_transcript.jsonl"
    audit_res = adapt_claude_transcript(
        raw_claude_jsonl=local_raw_session,
        output_canonical_jsonl=canonical_transcript_file,
        allowed_inputs=allowed_data["inputs"],
        allowed_support=allowed_data["allowed_support"],
        default_repo_root=str(env_dir),
    )

    disallowed_ext = audit_res["disallowed_external_attempts"]
    reads_outside = audit_res["reads_outside_allowed_set"]
    failed_attempts = audit_res["failed_read_attempts"]

    print(f"Post-execution Gate 2 (Auditor): {audit_res['canonical_steps_count']} steps, {len(audit_res['observed_reads'])} observed reads.")

    if disallowed_ext:
        print(f"CONFINEMENT HARD FAIL: Disallowed external attempts detected: {disallowed_ext}", file=sys.stderr)
        raise RuntimeError(f"AC16 Hard fail in {session_label}: {disallowed_ext}")

    if reads_outside:
        print(f"CONFINEMENT VIOLATION: Reads outside allowed set delivered content: {reads_outside}", file=sys.stderr)
        raise RuntimeError(f"AC16 Confinement violation in {session_label}: {reads_outside}")

    if failed_attempts:
        print(f"Gate 5 [INFO]: Recorded {len(failed_attempts)} innocuous failed read attempts (0 bytes delivered, confinement effect: none).")
    print(f"Post-execution Gate 2 [OK]: Confinement gate passed for {session_label} (0 disallowed external attempts, 0 unallowed delivered reads).")

    # Post-execution Gate 3: Verify inputs unchanged
    verify_input_manifest(cp_inputs_dir)
    print(f"Post-execution Gate 3 [OK]: Input integrity maintained post-execution (sha256={input_manifest_sha[:12]})")

    # Generate Ledger using context_ledger.py
    ledger_file = dest_replay_dir / "ledger.json"
    ledger_data = build_ledger_from_transcript(
        transcript_path=canonical_transcript_file,
        unit=f"T015-replay-{cp_key}",
        phase="review" if norm_cp in ["A", "C"] else "rework",
        allowed_inputs=allowed_data["inputs"],
        allowed_support=allowed_data["allowed_support"],
        allowed_set_path=allowed_file,
    )

    # Reconcile tripartite confinement fields
    ledger_data["reads_outside_allowed_set"] = [r["path"] for r in reads_outside]
    ledger_data["failed_read_attempts"] = [
        {
            "path": f["path"],
            "outcome": f["outcome"],
            "bytes_delivered": f.get("bytes_delivered", 0),
            "confinement_effect": f.get("confinement_effect", "none"),
        }
        for f in failed_attempts
    ]
    ledger_data["disallowed_external_attempts"] = [
        {"path": d["path"], "reason": d.get("reason", "")} if isinstance(d, dict) else str(d)
        for d in disallowed_ext
    ]

    # Validate against schema
    is_valid, errors = validate_context_ledger(ledger_data)
    if not is_valid:
        print(f"ERROR: Ledger for {session_label} failed schema validation: {errors}", file=sys.stderr)
        raise RuntimeError(f"Ledger schema validation failed for {session_label}: {errors}")

    ledger_file.write_text(json.dumps(ledger_data, indent=2) + "\n", encoding="utf-8")
    print(f"Post-execution Gate 4 [OK]: Context Ledger validated against schema and written to {ledger_file}")

    if proc.stdout:
        (dest_replay_dir / "raw_decision.md").write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (dest_replay_dir / "raw_stderr.txt").write_text(proc.stderr, encoding="utf-8")

    manifest_replay = {
        "checkpoint": cp_key,
        "treatment": treatment,
        "round": "r02",
        "execution_order": execution_order,
        "environment_commit": current_head,
        "input_manifest_sha256": input_manifest_sha,
        "allowed_set_sha256": calc_hash,
        "model": "claude-sonnet-5",
        "effort": "medium",
        "tool_policy": "Read,Glob,Grep,Bash",
        "session_id": session_id,
        "wall_clock_seconds": wall_clock,
        "exit_code": proc.returncode,
        "observed_reads_count": len(ledger_data.get("observed_reads", [])),
        "reads_outside_allowed_set": [r["path"] for r in reads_outside],
        "failed_read_attempts": failed_attempts,
        "disallowed_external_attempts": disallowed_ext,
    }
    (dest_replay_dir / "replay_manifest.json").write_text(json.dumps(manifest_replay, indent=2) + "\n", encoding="utf-8")

    print(f"=== Replay {execution_order}/6 ({session_label}) COMPLETED AND VALIDATED 100% ===\n")
    return manifest_replay


REPLAY_SCHEDULE = [
    ("A'", "reference", 1),
    ("A'", "t015",      2),
    ("B",  "t015",      3),
    ("B",  "reference", 4),
    ("C",  "reference", 5),
    ("C",  "t015",      6),
]


def main():
    parser = argparse.ArgumentParser(description="Run 6 paired replays for T015 r02.")
    parser.add_argument("--only-order", type=int, choices=[1, 2, 3, 4, 5, 6], help="Run only a specific replay order")
    args = parser.parse_args()

    print("================================================================================")
    print("=== STARTING T015 r02 PAIRED REPLAYS (CHAMADAS 3 A 8/10) ===")
    print("================================================================================")
    print(f"Reference environment: {ENV_REF} (commit 3e9ecc3)")
    print(f"T015 r02 environment:  {ENV_T015} (commit 511e745)")
    print(f"Evidence destination:  {EVIDENCE_R02}")
    print()

    executed = []
    for cp, treat, order in REPLAY_SCHEDULE:
        if args.only_order and args.only_order != order:
            continue
        res = run_single_replay(cp, treat, order)
        executed.append(res)

    print("\n================================================================================")
    print(f"=== ALL {len(executed)} REPLAYS OF r02 COMPLETED SUCCESSFULLY! ===")
    print("================================================================================")
    print("Mandatory Stop Condition reached: 8/10 calls consumed.")
    print("Classifier review and Checker final remain UNCALLED pending maintainer review.")


if __name__ == "__main__":
    main()
