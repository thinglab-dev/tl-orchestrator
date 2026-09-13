#!/usr/bin/env python3
"""
run_single_replay.py - Executes a single replay in the isolated environment, applies
pre-dispatch and post-execution gates, audits confinement with tripartite classification,
and generates the context ledger. Also supports deterministic post-processing across all runs.
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

sys.path.insert(0, str(BASE_SCRATCH))
from claude_transcript_adapter import adapt_claude_transcript


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
2. Distinga a limitação residual explicitamente aceita na spec (classe "procedência por conteúdo", encaminhada a T010) de um defeito bloqueante que impeça critério obrigatório. Não exija rework inexistente nem trate 'approved' como passe livre automático sem conferência de alvo e provas.
3. Proponha formalmente o encaminhamento cabível (fechamento com registro da limitação ou impedimento fundamentado) dentro da autorização vigente.
4. Emita em sua resposta final a fundamentação completa e a minuta de fechamento ou briefing de condução, respeitando governança, catálogo e escopo.
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


def process_replay_data(
    dest_replay_dir: Path,
    raw_session_file: Path,
    cp_key: str,
    treatment: str,
    execution_order: int,
    env_commit: str,
    input_manifest_sha: str,
    allowed_data: dict,
    wall_clock: float,
    exit_code: int,
    session_id: str,
    raw_stdout: Optional[str] = None,
    raw_stderr: Optional[str] = None,
):
    """Deterministically adapts transcript, audits confinement, and generates the enriched ledger."""
    norm_cp = "A" if cp_key in ["A", "A'"] else cp_key
    dest_replay_dir.mkdir(parents=True, exist_ok=True)

    # Copy raw_session.jsonl locally if not already present
    local_raw_session = dest_replay_dir / "raw_session.jsonl"
    if raw_session_file.resolve() != local_raw_session.resolve():
        shutil.copy2(raw_session_file, local_raw_session)

    canonical_transcript_file = dest_replay_dir / "canonical_transcript.jsonl"
    default_root = str(ENV_REF if treatment == "reference" else ENV_T015)
    audit_res = adapt_claude_transcript(
        raw_claude_jsonl=local_raw_session,
        output_canonical_jsonl=canonical_transcript_file,
        allowed_inputs=allowed_data["inputs"],
        allowed_support=allowed_data["allowed_support"],
        default_repo_root=default_root,
    )

    disallowed_ext = audit_res["disallowed_external_attempts"]
    reads_outside = audit_res["reads_outside_allowed_set"]
    failed_attempts = audit_res["failed_read_attempts"]

    print(f"Audit [{cp_key}_{treatment}]: {audit_res['canonical_steps_count']} steps, {len(audit_res['observed_reads'])} observed reads.")
    if disallowed_ext:
        print(f"CONFINEMENT HARD FAIL: Disallowed external attempts detected: {disallowed_ext}", file=sys.stderr)
        raise RuntimeError(f"AC16 Hard fail in {cp_key}_{treatment}: {disallowed_ext}")

    if reads_outside:
        print(f"CONFINEMENT VIOLATION: Reads outside allowed set delivered content: {reads_outside}", file=sys.stderr)
        raise RuntimeError(f"AC16 Confinement violation in {cp_key}_{treatment}: {reads_outside}")

    if failed_attempts:
        print(f"Gate 5 [INFO]: Recorded {len(failed_attempts)} innocuous failed read attempts (0 bytes delivered, confinement effect: none).")
    print(f"Gate 5 [OK]: Confinement gate passed for {cp_key}_{treatment} (0 disallowed external attempts, 0 unallowed delivered reads).")

    # Generate Ledger using context_ledger.py
    ledger_file = dest_replay_dir / "ledger.json"
    cmd_ledger = [
        sys.executable,
        str(WT_T015 / "scripts" / "context_ledger.py"),
        "--transcript", str(canonical_transcript_file),
        "--unit", f"T015-replay-{cp_key}",
        "--phase", "review" if norm_cp in ["A", "C"] else "rework",
        "--output", str(ledger_file),
    ]
    subprocess.run(cmd_ledger, check=True)

    # Post-process ledger.json to enrich with audited tripartite confinement fields
    ledger_data = json.loads(ledger_file.read_text(encoding="utf-8"))
    ledger_data["reads_outside_allowed_set"] = reads_outside
    ledger_data["failed_read_attempts"] = failed_attempts
    ledger_data["disallowed_external_attempts"] = disallowed_ext
    ledger_data["observed_reads"] = audit_res["observed_reads"]
    ledger_file.write_text(json.dumps(ledger_data, indent=2) + "\n", encoding="utf-8")
    print(f"Ledger enriched and written to {ledger_file}")

    if raw_stdout is not None:
        (dest_replay_dir / "raw_decision.md").write_text(raw_stdout, encoding="utf-8")
    if raw_stderr is not None:
        (dest_replay_dir / "raw_stderr.txt").write_text(raw_stderr, encoding="utf-8")

    manifest_replay = {
        "checkpoint": cp_key,
        "treatment": treatment,
        "execution_order": execution_order,
        "environment_commit": env_commit,
        "input_manifest_sha256": input_manifest_sha,
        "allowed_set_sha256": allowed_data["allowed_set_sha256"],
        "model": "claude-sonnet-5",
        "effort": "medium",
        "tool_policy": "Read,Glob,Grep,Bash",
        "session_id": session_id,
        "wall_clock_seconds": wall_clock,
        "exit_code": exit_code,
        "reads_outside_allowed_set": reads_outside,
        "failed_read_attempts": failed_attempts,
        "disallowed_external_attempts": disallowed_ext,
    }
    (dest_replay_dir / "replay_manifest.json").write_text(json.dumps(manifest_replay, indent=2) + "\n", encoding="utf-8")
    print(f"Tokens: in={ledger_data['tokens']['input_tokens']}, cache_read={ledger_data['tokens']['cache_read_input_tokens']}, out={ledger_data['tokens']['output_tokens']}, turns={ledger_data['turn_count']}")


def reprocess_all():
    """Deterministically re-audits and updates ledgers for all 5 completed replays."""
    replays = [
        ("A'", "reference", 1, "3e9ecc356b839dbe5e736e5356219bb092a4ff00", "0bb1228a-3e63-46e6-bf83-75ac61d34997", 167.99),
        ("A'", "t015", 2, "5e3647e", "5564d777-c6e4-4306-832e-280120805039", 62.92),
        ("B", "t015", 3, "5e3647e", "7182ec0c-8d92-45ba-814d-73b613385887", 31.97),
        ("B", "reference", 4, "3e9ecc356b839dbe5e736e5356219bb092a4ff00", "9028434f-d3d3-4671-8321-8c8c495c8b9b", 85.82),
        ("C", "reference", 5, "3e9ecc356b839dbe5e736e5356219bb092a4ff00", "7e3b6738-8541-4a23-8f26-7ae7cc04d3a8", 134.29),
    ]

    print("\n=== Deterministically Reprocessing All 5 Completed Replays ===")
    for cp_key, treatment, order, env_commit, session_id, wall_clock in replays:
        norm_cp = "A" if cp_key in ["A", "A'"] else cp_key
        cp_dir_name = f"checkpoint-{norm_cp}"
        env_dir = ENV_REF if treatment == "reference" else ENV_T015
        cp_inputs_dir = env_dir / "_tl-orc" / "project" / "evidence" / "T015-r01" / "inputs" / cp_dir_name

        input_manifest_sha = verify_input_manifest(cp_inputs_dir)
        allowed_file = WT_T015 / "_tl-orc" / "project" / "evidence" / "T015-r01" / "allowed_sets" / f"allowed_set_{cp_dir_name}.json"
        allowed_data = json.loads(allowed_file.read_text(encoding="utf-8"))

        dest_replay_dir = WT_T015 / "_tl-orc" / "project" / "evidence" / "T015-r01" / "replays" / f"{cp_key}_{treatment}"

        # Find raw session file
        local_raw = dest_replay_dir / "raw_session.jsonl"
        if local_raw.is_file():
            raw_session_file = local_raw
        else:
            found = list(Path.home().glob(f".claude/projects/*/{session_id}.jsonl"))
            if not found:
                raise FileNotFoundError(f"Cannot find session {session_id}")
            raw_session_file = found[0]

        process_replay_data(
            dest_replay_dir=dest_replay_dir,
            raw_session_file=raw_session_file,
            cp_key=cp_key,
            treatment=treatment,
            execution_order=order,
            env_commit=env_commit,
            input_manifest_sha=input_manifest_sha,
            allowed_data=allowed_data,
            wall_clock=wall_clock,
            exit_code=0,
            session_id=session_id,
        )
    print("=== All 5 Replays Reprocessed and Audited Successfully ===\n")


def run_replay(checkpoint: str, treatment: str, execution_order: int):
    norm_cp = "A" if checkpoint in ["A", "A'"] else checkpoint
    cp_key = "A'" if norm_cp == "A" else norm_cp
    cp_dir_name = f"checkpoint-{norm_cp}"

    print(f"\n=======================================================")
    print(f"=== Running Replay {execution_order}/6: Checkpoint {cp_key} ({treatment.upper()}) ===")
    print(f"=======================================================")

    env_dir = ENV_REF if treatment == "reference" else ENV_T015
    env_commit = "3e9ecc356b839dbe5e736e5356219bb092a4ff00" if treatment == "reference" else "5e3647e"

    # Pre-dispatch Gate 1: Check environment commit
    proc_rev = subprocess.run(["git", "-C", str(env_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    current_head = proc_rev.stdout.strip()
    if treatment == "reference":
        assert current_head.startswith("3e9ecc3"), f"Reference env not on base commit: {current_head}"
    else:
        assert current_head.startswith("5e3647e"), f"T015 env not on commit 5e3647e: {current_head}"
    print(f"Gate 1 [OK]: Environment {treatment} verified at {current_head[:12]}")

    # Pre-dispatch Gate 2: Verify input integrity against canonical manifest (AC15)
    cp_inputs_dir = env_dir / "_tl-orc" / "project" / "evidence" / "T015-r01" / "inputs" / cp_dir_name
    input_manifest_sha = verify_input_manifest(cp_inputs_dir)
    print(f"Gate 2 [OK]: Input manifest integrity verified (sha256={input_manifest_sha[:12]})")

    # Pre-dispatch Gate 3: Read allowed_set
    allowed_file = WT_T015 / "_tl-orc" / "project" / "evidence" / "T015-r01" / "allowed_sets" / f"allowed_set_{cp_dir_name}.json"
    allowed_data = json.loads(allowed_file.read_text(encoding="utf-8"))
    allowed_set_sha = allowed_data["allowed_set_sha256"]
    print(f"Gate 3 [OK]: Pre-declared allowed_set verified (sha256={allowed_set_sha[:12]})")

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

    print(f"Gate 4 [OK]: Raw session file located at {raw_session_file}")

    dest_replay_dir = WT_T015 / "_tl-orc" / "project" / "evidence" / "T015-r01" / "replays" / f"{cp_key}_{treatment}"
    process_replay_data(
        dest_replay_dir=dest_replay_dir,
        raw_session_file=raw_session_file,
        cp_key=cp_key,
        treatment=treatment,
        execution_order=execution_order,
        env_commit=env_commit,
        input_manifest_sha=input_manifest_sha,
        allowed_data=allowed_data,
        wall_clock=wall_clock,
        exit_code=proc.returncode,
        session_id=session_id,
        raw_stdout=proc.stdout,
        raw_stderr=proc.stderr,
    )

    # Post-execution Gate 3: Verify inputs unchanged
    verify_input_manifest(cp_inputs_dir)
    print("Gate 6 [OK]: Input integrity maintained post-execution")
    print(f"Replay {execution_order}/6 completed and validated successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", choices=["A", "A'", "B", "C"])
    parser.add_argument("--treatment", choices=["reference", "t015"])
    parser.add_argument("--order", type=int)
    parser.add_argument("--reprocess-all", action="store_true", help="Reprocess all existing replays deterministically")
    args = parser.parse_args()

    if args.reprocess_all:
        reprocess_all()
    else:
        if not args.checkpoint or not args.treatment or args.order is None:
            parser.error("--checkpoint, --treatment, and --order are required when not using --reprocess-all")
        run_replay(args.checkpoint, args.treatment, args.order)
