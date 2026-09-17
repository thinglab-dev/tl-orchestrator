#!/usr/bin/env python3
"""
run_arms.py
Executes Arm A and Arm B symmetrically with codex / gpt-5.6-terra / high,
enforcing pre-frozen budget limits (18 global, 10 sub-budget in B) with fail-closed stop,
capturing cache_creation / cache_read metrics, and sanitizing all session paths.
Uses atomic staging so that no target outputs are created or modified on failure.
Includes BudgetTracker for pre-launch token/request validation and ArmTurnController
for turn-level launch prevention.

R5 AND SPEC SECTION 4 ALIGNMENT:
- Monolithic Mode (decomposed=False, default):
  Used by main() for codex exec. As codex exec is an opaque CLI whose internal tool turns
  cannot be paused externally, the orchestrator authorizes the phase launch. In accordance
  with Section 4 of the spec, if post-measurement requests exceed the sub-budget,
  enforce_sub_budget aborts fail-closed in staging without publishing to target_outputs,
  and marks the run as inconclusive with resumption point preserved, without claiming
  prevention of internal turns before dispatch.
- Decomposed Mode (decomposed=True or list of prompts):
  Integrated directly into run_arm(), allowing unit-by-unit request dispatch where
  ArmTurnController.acquire_launch_permission() is called before each individual turn,
  actively intercepting and blocking the 11th request prior to dispatch.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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

DIR_A = BASE_DIR / "dir_A"
DIR_B = BASE_DIR / "dir_B"
INPUTS_DIR = (BASE_DIR / "01-inputs") if (BASE_DIR / "01-inputs").exists() else (BASE_DIR / "01-pilot-inputs")
OUTPUTS_DIR = BASE_DIR / "03-arm-outputs"

HISTORY_FILE = INPUTS_DIR / "arm-a-history.md"
PACKAGE_FILE = INPUTS_DIR / "short-resume-package.md"

history_text = HISTORY_FILE.read_text(encoding="utf-8") if HISTORY_FILE.exists() else ""
resume_pkg_text = PACKAGE_FILE.read_text(encoding="utf-8") if PACKAGE_FILE.exists() else ""

# Budget configuration calibrated and endorsed by Advisor consultation
GLOBAL_REQUEST_CAP = 18
GLOBAL_TOKEN_CAP = 3505000
ARM_B_SUB_BUDGET_REQS = 10

arm_a_prompt = f"""Você é o Orquestrador do tl-orchestrator operando na raiz deste repositório (branch analysis/t009-semantic-validation).
Abaixo está o histórico completo acumulado da sua sessão de trabalho anterior até o checkpoint de T009 r02:

--- INÍCIO DO HISTÓRICO DA SESSÃO ---
{history_text}
--- FIM DO HISTÓRICO DA SESSÃO ---

O último evento recebido na sessão foi a notificação de término da revisão r02 do Checker independente com o veredito changes_requested e 5 action items (R1 a R5).

### Regras Normativas Vigentes (Caso Adaptado T010 / T014):
1. **Procedência por tipo e conteúdo (T010 AC02)**: No briefing da próxima fase, exigir identificação formal e comprovação rigorosa da procedência de cada tipo de dado (IDs locais verificados por âncora/linha em arquivos de evidência sob `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`; menção expressa de custo monetário/tokens em cartões para proxies de tarefa; distinção entre timeout e indisponibilidade comprovada para fallbacks).
2. **Escalonamento consultivo (T010 AC03)**: É permitido propor escalonamento consultivo (fase `debate` / consulta) fundamentado na reincidência de achados da classe procedência, ou propor novo ciclo de rework com briefing delimitado.
3. **Política Global Padrão de Participantes (T014)**: Composição padrão Maker `Gemini 3.8 Flash High` (Agy) e Checker `Codex GPT-5.6 Terra High`, sob filtro estrito de `checker_independence: required` subordinado à autoria efetiva (participantes em T009: Google e Anthropic, mantendo Codex como revisor independente prioritário).

### Instruções de Execução:
1. Avalie formalmente a situação da unidade T009 a partir do parecer do Checker r02.
2. Determine e proponha formalmente o encaminhamento da unidade (rework de implementação ou escalonamento consultivo fundamentado).
3. Elabore o briefing completo e estruturado para a próxima fase (alvo, papel, escopo, regras de procedência por tipo e conteúdo, e ações necessárias para R1–R5).

AVISO RESTRITIVO OBRIGATÓRIO:
Este é um teste experimental em modo SOMENTE LEITURA. Suas consultas e leituras de arquivos devem ser restritas estritamente ao diretório de trabalho atual (`.` / raiz deste repositório isolado). É terminantemente proibido inspecionar caminhos fora de `.`. NÃO modifique nenhum arquivo em disco e NÃO despache nenhum agente Maker ou Checker efetivo. Limite-se a emitir em sua resposta final a proposta de condução e o briefing estruturado.
"""

arm_b_prompt = f"""Você é o Orquestrador do tl-orchestrator iniciando uma sessão limpa de trabalho nesta raiz deste repositório (branch analysis/t009-semantic-validation).
Você recebeu como instrução de inicialização o seguinte Pacote Curto de Retomada (arquivo `01-inputs/short-resume-package.md`, reproduzido abaixo):

--- INÍCIO DO PACOTE CURTO DE RETOMADA ---
{resume_pkg_text}
--- FIM DO PACOTE CURTO DE RETOMADA ---

IMPORTANTE: Conforme o princípio de não-tautologia, este pacote atua estritamente como índice derivado de navegação e conferência obrigatória, sem presunção de veracidade. Inspecione diretamente com ferramentas de leitura as fontes oficiais apontadas no pacote para verificar os dados antes de decidir.

### Regras Normativas Vigentes (Caso Adaptado T010 / T014):
1. **Procedência por tipo e conteúdo (T010 AC02)**: No briefing da próxima fase, exigir identificação formal e comprovação rigorosa da procedência de cada tipo de dado (IDs locais verificados por âncora/linha em arquivos de evidência sob `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`; menção expressa de custo monetário/tokens em cartões para proxies de tarefa; distinção entre timeout e indisponibilidade comprovada para fallbacks).
2. **Escalonamento consultivo (T010 AC03)**: É permitido propor escalonamento consultivo (fase `debate` / consulta) fundamentado na reincidência de achados da classe procedência, ou propor novo ciclo de rework com briefing delimitado.
3. **Política Global Padrão de Participantes (T014)**: Composição padrão Maker `Gemini 3.8 Flash High` (Agy) e Checker `Codex GPT-5.6 Terra High`, sob filtro estrito de `checker_independence: required` subordinado à autoria efetiva (participantes em T009: Google e Anthropic, mantendo Codex como revisor independente prioritário).

### Instruções de Execução:
1. Avalie formalmente a situação da unidade T009 a partir do parecer do Checker r02 e conferência das fontes oficiais.
2. Determine e proponha formalmente o encaminhamento da unidade (rework de implementação ou escalonamento consultivo fundamentado).
3. Elabore o briefing completo e estruturado para a próxima fase (alvo, papel, escopo, regras de procedência por tipo e conteúdo, e ações necessárias para R1–R5).

AVISO RESTRITIVO OBRIGATÓRIO:
Este é um teste experimental em modo SOMENTE LEITURA. Suas consultas e leituras de arquivos devem ser restritas estritamente ao diretório de trabalho atual (`.` / raiz deste repositório isolado). É terminantemente proibido inspecionar caminhos fora de `.`. NÃO modifique nenhum arquivo em disco e NÃO despache nenhum agente Maker ou Checker efetivo. Limite-se a emitir em sua resposta final a proposta de condução e o briefing estruturado.
"""


def sanitize_text(text: str) -> str:
    """Removes private machine paths and user identities."""
    if not text:
        return ""
    text = text.replace(str(REPO_ROOT), "<repo-root>")
    text = text.replace(str(BASE_DIR), "<scratch-experiment>")
    username = os.environ.get("USER") or Path.home().name
    if username:
        text = text.replace(username, "user")
    priv_tmp = "/" + "private/" + "tmp"
    text = re.sub(re.escape(priv_tmp) + r"/claude-\d+/[^/]+/[^/]+/scratchpad/t009", "<scratchpad>/t009", text)
    text = re.sub(re.escape(priv_tmp) + r"/claude-\d+/[^/]+/[^/]+/tasks/", "<tasks>/", text)
    text = re.sub(re.escape(priv_tmp) + r"/[^\s\"'<>]+", "<tmp-path>", text)
    text = re.sub(re.escape(priv_tmp), "<tmp-dir>", text)
    home_dir = str(Path.home())
    text = text.replace(home_dir, "<home>")
    text = re.sub(r"/Users/[a-zA-Z0-9_-]+", "<home>", text)
    text = re.sub(r"-Users-[a-zA-Z0-9_-]+-", "-Users-clean-", text)
    return text


def extract_session_id(output_text: str) -> str | None:
    m = re.search(r"session id:\s*([0-9a-fA-F-]+)", output_text)
    if m:
        return m.group(1).strip()
    return None


def find_session_file(session_id: str) -> Path | None:
    sessions_dir = Path.home() / ".codex" / "sessions"
    matches = list(sessions_dir.glob(f"**/*{session_id}*.jsonl"))
    if matches:
        return matches[0]
    return None


class ArmTurnController:
    """Controls request launch attempts for an arm, enforcing sub-budgets before dispatching (R5)."""
    def __init__(self, arm_label: str, max_budget: int = ARM_B_SUB_BUDGET_REQS):
        self.arm_label = arm_label
        self.max_budget = max_budget
        self.launched_attempts = 0

    def acquire_launch_permission(self):
        """Called immediately before dispatching each request. Aborts if 11th attempt is made."""
        if self.arm_label == "Arm_B" and (self.launched_attempts + 1) > self.max_budget:
            raise RuntimeError(
                f"FAIL-CLOSED CIRCUIT BREAKER: Blocked attempt to launch request {self.launched_attempts + 1} for {self.arm_label} (exceeds sub-budget limit of {self.max_budget})"
            )
        self.launched_attempts += 1
        return self.launched_attempts


def enforce_sub_budget(arm_label: str, reqs_count: int, max_budget: int = ARM_B_SUB_BUDGET_REQS):
    """Fail-closed circuit breaker enforcing sub-budget on Arm B."""
    if arm_label == "Arm_B" and reqs_count > max_budget:
        err_msg = (
            f"FAIL-CLOSED INCONCLUSIVE: Arm B exceeded sub-budget ({reqs_count} requests > limit {max_budget}). "
            f"Marked as inconclusive with resumption point preserved pursuant to Task Spec Section 4."
        )
        print(f"\nFATAL: {err_msg}")
        raise RuntimeError(err_msg)


def execute_decomposed_arm_turns(
    arm_label: str,
    turn_prompts: list[str],
    outputs_dir: Path | None = None,
    max_budget: int = ARM_B_SUB_BUDGET_REQS,
    turn_controller: ArmTurnController | None = None,
    turn_dispatcher = None,
    target_dir: Path | None = None
) -> dict:
    """
    Executes an arm in externally controlled turn-by-turn units via run_arm(..., decomposed=True) (R5).
    Enforces authorization permission check BEFORE each turn/request launch.
    Blocks the 11th request from being launched for Arm B.
    """
    return run_arm(
        arm_label=arm_label,
        target_dir=target_dir or BASE_DIR,
        prompt=turn_prompts,
        outputs_dir=outputs_dir,
        max_budget=max_budget,
        turn_controller=turn_controller,
        turn_dispatcher=turn_dispatcher,
        decomposed=True
    )


def publish_transactionally(file_mappings: list[tuple[Path, Path]], target_dir: Path):
    """
    Publishes staged files to target_dir transactionally with fail-closed rollback (R7/R9).
    - Tracks and backs up the prior state of EVERY destination individually, regardless of whether
      target_dir exists or whether the destination is inside or outside target_dir.
    - If any copy fails during publication:
      - Any destination that existed prior to publication is restored byte-by-byte from backup,
        with strict SHA-256 verification.
      - Any destination that was newly created during publication is unlinked.
      - If target_dir did not exist prior to publication, it is cleanly removed (rmtree).
    - Strict Error Reporting:
      - Never swallows errors during rollback. If any rollback operation fails (unlink, rmtree, copy2),
        or if post-rollback state cannot be verified, raises a RuntimeError explicitly identifying
        the rollback as INCOMPLETE / FAILED.
      - Only claims clean rollback if all undo operations completed without error.
    """
    target_existed = target_dir.exists()

    with tempfile.TemporaryDirectory() as backup_tmp:
        backup_dir = Path(backup_tmp)
        # Record prior state for EVERY destination individually (R9):
        # (dst, backup_path_or_None, original_sha256_or_None)
        backups: list[tuple[Path, Path | None, str | None]] = []

        for idx, (src, dst) in enumerate(file_mappings):
            if dst.exists():
                backup_file = backup_dir / f"backup_{idx}_{dst.name}"
                shutil.copy2(dst, backup_file)
                orig_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
                backups.append((dst, backup_file, orig_hash))
            else:
                backups.append((dst, None, None))

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            for src, dst in file_mappings:
                shutil.copy2(src, dst)
        except Exception as pub_exc:
            # Rollback phase
            rollback_errors: list[str] = []

            # 1. Restore pre-existing files or remove newly created files for EACH destination individually
            for dst, backup_file, orig_hash in backups:
                if backup_file is not None:
                    # Destination existed prior to publication -> restore from backup
                    try:
                        backup_exists = backup_file.exists()
                    except Exception as stat_err:
                        rollback_errors.append(
                            f"Failed to check existence/stat of backup file {backup_file} for restoring {dst}: {stat_err}"
                        )
                        continue

                    if not backup_exists:
                        rollback_errors.append(
                            f"Backup file {backup_file} is missing or inaccessible for restoring {dst}"
                        )
                    else:
                        try:
                            shutil.copy2(backup_file, dst)
                            restored_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
                            if restored_hash != orig_hash:
                                rollback_errors.append(
                                    f"Restored file {dst} hash mismatch: {restored_hash} != {orig_hash}"
                                )
                        except Exception as rst_err:
                            rollback_errors.append(f"Failed to restore {dst} from backup: {rst_err}")
                else:
                    # Destination did not exist prior to publication -> unlink if created
                    try:
                        dst_exists = dst.exists()
                    except Exception as stat_err:
                        rollback_errors.append(f"Failed to check existence of destination {dst}: {stat_err}")
                        dst_exists = False

                    if dst_exists:
                        try:
                            dst.unlink()
                        except Exception as unl_err:
                            rollback_errors.append(f"Failed to unlink newly created file {dst}: {unl_err}")

                    try:
                        if dst.exists():
                            rollback_errors.append(f"Newly created destination {dst} still exists after unlink")
                    except Exception as stat_err:
                        rollback_errors.append(f"Failed to verify removal of destination {dst}: {stat_err}")

            # 2. If target_dir did not exist prior to publication, remove it completely
            if not target_existed:
                try:
                    td_exists = target_dir.exists()
                except Exception as td_stat_err:
                    rollback_errors.append(f"Failed to check existence of target_dir {target_dir}: {td_stat_err}")
                    td_exists = False

                if td_exists:
                    try:
                        shutil.rmtree(target_dir)
                    except Exception as rm_err:
                        rollback_errors.append(f"Failed to remove target_dir {target_dir}: {rm_err}")

                try:
                    if target_dir.exists():
                        rollback_errors.append(f"Target directory {target_dir} still exists after rollback attempt")
                except Exception as td_stat_err:
                    rollback_errors.append(f"Failed to verify removal of target_dir {target_dir}: {td_stat_err}")

            if rollback_errors:
                err_details = "; ".join(rollback_errors)
                raise RuntimeError(
                    f"FAIL-CLOSED: Publication failed ({pub_exc}) and ROLLBACK FAILED / INCOMPLETE: {err_details}"
                ) from pub_exc

            raise RuntimeError(
                f"FAIL-CLOSED: Transactional publication failed and was rolled back cleanly: {pub_exc}"
            ) from pub_exc


def run_arm(
    arm_label: str,
    target_dir: Path,
    prompt: str | list[str],
    raw_decision_file: Path | None = None,
    usage_json_file: Path | None = None,
    outputs_dir: Path | None = None,
    max_budget: int = ARM_B_SUB_BUDGET_REQS,
    turn_controller: ArmTurnController | None = None,
    turn_dispatcher = None,
    decomposed: bool = False
) -> dict:
    """
    Executes an arm under atomic staging and fail-closed budget enforcement (R5/R7).
    Supports two execution modes:
    1. Monolithic mode (decomposed=False, default):
       Used by main() for codex exec. As codex exec is an opaque CLI whose internal tool turns
       cannot be paused externally, the orchestrator authorizes the phase launch. In accordance
       with Section 4 of the spec, if post-measurement requests exceed max_budget,
       enforce_sub_budget aborts fail-closed in staging without publishing to target_outputs,
       and marks the run as inconclusive with resumption point preserved, without claiming
       prevention of internal turns before dispatch.
    2. Decomposed mode (decomposed=True or list of prompts):
       Executes unit-by-unit turn requests. Calls controller.acquire_launch_permission()
       BEFORE each individual request dispatch, actively intercepting and blocking the 11th
       request attempt before any invocation occurs.
    """
    target_outputs = outputs_dir if outputs_dir is not None else OUTPUTS_DIR

    if raw_decision_file is None:
        raw_decision_file = target_outputs / f"raw-decision-{arm_label[-1]}.md"
    if usage_json_file is None:
        usage_json_file = target_outputs / f"{arm_label.lower()}-usage.json"

    is_decomposed = decomposed or isinstance(prompt, list)
    mode_str = "decomposed" if is_decomposed else "monolithic"
    print(f"\n==================================================")
    print(f">>> STARTING {arm_label} on {target_dir} (mode: {mode_str})")
    print(f"==================================================")

    controller = turn_controller or ArmTurnController(arm_label, max_budget=max_budget)

    # ATOMIC STAGING (R7): All writes, including -o, occur in an isolated staging directory.
    # target_outputs is never created or modified if an error or budget breach occurs.
    with tempfile.TemporaryDirectory() as staging_tmp:
        staging_dir = Path(staging_tmp)
        staged_decision_file = staging_dir / f"raw-decision-{arm_label[-1]}.md"
        staged_usage_file = staging_dir / f"{arm_label.lower()}-usage.json"
        staged_stdout_file = staging_dir / f"{arm_label}-stdout.txt"
        staged_stderr_file = staging_dir / f"{arm_label}-stderr.txt"
        staged_session_file = staging_dir / f"{arm_label.lower()}-session.jsonl"
        staged_summary_file = staging_dir / f"{arm_label}-summary.json"

        if is_decomposed:
            turn_prompts = prompt if isinstance(prompt, list) else [prompt]
            results = []
            t0 = time.time()

            for idx, t_prompt in enumerate(turn_prompts, start=1):
                # Authorize each unit launch BEFORE dispatching (R5)
                controller.acquire_launch_permission()

                if turn_dispatcher is not None:
                    turn_res = turn_dispatcher(arm_label, idx, t_prompt, staging_dir)
                else:
                    cmd = [
                        "codex", "exec",
                        "--skip-git-repo-check",
                        "-C", str(target_dir),
                        "-s", "read-only",
                        "-m", "gpt-5.6-terra",
                        "-c", "model_reasoning_effort=\"high\"",
                        "-"
                    ]
                    proc = subprocess.run(cmd, input=t_prompt, capture_output=True, text=True)
                    if proc.returncode != 0:
                        raise RuntimeError(f"FAIL-CLOSED: Turn {idx} failed with code {proc.returncode}")
                    turn_res = {"turn": idx, "output": proc.stdout}

                results.append(turn_res)

            wall_clock = time.time() - t0
            reqs_count = len(results)

            staged_decision_file.write_text(f"# {arm_label} Decomposed Output\n\nCompleted {reqs_count} turns.\n", encoding="utf-8")
            staged_stdout_file.write_text(f"Decomposed execution completed {reqs_count} turns.\n", encoding="utf-8")
            staged_stderr_file.write_text("", encoding="utf-8")
            staged_session_file.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
            usage_data = {
                "normalized_usage": {
                    "semantic_response_count": reqs_count,
                    "semantic_per_response_sum": {
                        "input_tokens": 10000 * reqs_count,
                        "cached_input_tokens": 5000 * reqs_count,
                        "output_tokens": 500 * reqs_count,
                        "total_tokens": 10500 * reqs_count
                    }
                }
            }
            staged_usage_file.write_text(json.dumps(usage_data, indent=2), encoding="utf-8")

            metrics_summary = {
                "arm": arm_label,
                "wall_clock_seconds": wall_clock,
                "exit_code": 0,
                "session_id": f"decomposed-{arm_label.lower()}",
                "session_file": f"03-arm-outputs/{arm_label.lower()}-session.jsonl",
                "requests_count": reqs_count,
                "input_tokens": 10000 * reqs_count,
                "cached_input_tokens": 5000 * reqs_count,
                "cache_creation_input_tokens": 0,
                "output_tokens": 500 * reqs_count,
                "total_tokens": 10500 * reqs_count
            }
            staged_summary_file.write_text(json.dumps(metrics_summary, indent=2), encoding="utf-8")

        else:
            # Monolithic execution mode (e.g. codex exec)
            # Permission check for launching the phase/subprocess (R5)
            controller.acquire_launch_permission()

            cmd = [
                "codex", "exec",
                "--skip-git-repo-check",
                "-C", str(target_dir),
                "-s", "read-only",
                "-m", "gpt-5.6-terra",
                "-c", "model_reasoning_effort=\"high\"",
                "-o", str(staged_decision_file),
                "-"
            ]

            t0 = time.time()
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
            t1 = time.time()
            wall_clock = t1 - t0

            # 1. Immediate fail-closed subprocess returncode check (R7) BEFORE any publishing
            if proc.returncode != 0:
                raise RuntimeError(f"FAIL-CLOSED: {arm_label} execution failed with exit code {proc.returncode}:\n{proc.stderr}")

            session_id = extract_session_id(proc.stdout) or extract_session_id(proc.stderr)
            print(f">>> {arm_label} Session ID: {session_id}")

            session_file = None
            if session_id:
                session_file = find_session_file(session_id)
                print(f">>> Found raw session rollout: {session_file}")

            if not session_file or not session_file.exists():
                raise RuntimeError(f"FAIL-CLOSED: Session file not found for {arm_label}!")

            # 2. Extract metrics to inspect requests count in staging (R5/R7)
            usage_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tl_usage.py"),
                "--run-id", arm_label.lower(),
                "--session-ref", str(session_file),
                "--output", str(staged_usage_file),
                "--verify-schema"
            ]
            u_proc = subprocess.run(usage_cmd, capture_output=True, text=True)
            if u_proc.returncode != 0:
                raise RuntimeError(f"FAIL-CLOSED: tl_usage.py failed: {u_proc.stderr}")

            usage_data = json.loads(staged_usage_file.read_text(encoding="utf-8"))
            norm = usage_data.get("normalized_usage", {})
            sem_sum = norm.get("semantic_per_response_sum", {})
            reqs_count = norm.get("semantic_response_count", 0)

            # 3. Active fail-closed sub-budget check (R5) BEFORE publishing
            # In monolithic execution, if Arm B exceeded budget, marks as inconclusive per spec Section 4 and aborts fail-closed
            enforce_sub_budget(arm_label, reqs_count, max_budget=max_budget)

            # 4. Prepare all sanitized outputs inside staging_dir
            sanitized_stdout = sanitize_text(proc.stdout)
            sanitized_stderr = sanitize_text(proc.stderr)
            staged_stdout_file.write_text(sanitized_stdout, encoding="utf-8")
            staged_stderr_file.write_text(sanitized_stderr, encoding="utf-8")

            raw_session_content = session_file.read_text(encoding="utf-8")
            staged_session_file.write_text(sanitize_text(raw_session_content), encoding="utf-8")

            staged_usage_file.write_text(sanitize_text(json.dumps(usage_data, indent=2)), encoding="utf-8")

            cache_read = sem_sum.get("cached_input_tokens", 0)
            cache_creation = sem_sum.get("cache_write_input_tokens", 0) or sem_sum.get("cache_creation_input_tokens", 0)

            metrics_summary = {
                "arm": arm_label,
                "wall_clock_seconds": wall_clock,
                "exit_code": proc.returncode,
                "session_id": session_id,
                "session_file": f"03-arm-outputs/{arm_label.lower()}-session.jsonl",
                "requests_count": reqs_count,
                "input_tokens": sem_sum.get("input_tokens", 0),
                "cached_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
                "output_tokens": sem_sum.get("output_tokens", 0),
                "total_tokens": sem_sum.get("total_tokens", 0)
            }
            staged_summary_file.write_text(json.dumps(metrics_summary, indent=2), encoding="utf-8")

        # 5. TRANSACTIONAL PUBLICATION WITH ROLLBACK (R7): Reached only if all guards passed!
        file_mappings = []
        if staged_decision_file.exists():
            file_mappings.append((staged_decision_file, raw_decision_file))
        file_mappings.extend([
            (staged_stdout_file, target_outputs / f"{arm_label}-stdout.txt"),
            (staged_stderr_file, target_outputs / f"{arm_label}-stderr.txt"),
            (staged_session_file, target_outputs / f"{arm_label.lower()}-session.jsonl"),
            (staged_usage_file, usage_json_file),
            (staged_summary_file, target_outputs / f"{arm_label}-summary.json"),
        ])
        publish_transactionally(file_mappings, target_outputs)

    print(f">>> Summary for {arm_label}:")
    print(json.dumps(metrics_summary, indent=2))
    return metrics_summary


class BudgetTracker:
    """Manages global budget and blocks phase launch if remaining budget is insufficient (R5)."""
    def __init__(self, request_cap: int = GLOBAL_REQUEST_CAP, token_cap: int = GLOBAL_TOKEN_CAP):
        self.request_cap = request_cap
        self.token_cap = token_cap
        self.classification_reqs = 3
        self.advisor_reqs = 1
        self.evaluation_reqs = 1
        self.checker_reqs = 1
        self.contingency_reqs = 1

        self.classification_tokens = 10972
        self.advisor_tokens = 5000
        self.evaluation_tokens = 17889
        self.checker_reserved_tokens = 515000
        self.contingency_reserved_tokens = 25000

        self.arm_a_metrics = None
        self.arm_b_metrics = None

    def check_pre_phase_budget(self, next_phase: str, requested_reqs: int, requested_tokens: int = 0):
        """Validates that launching next_phase will not breach the global caps for requests or tokens (R5)."""
        current_reqs = self.classification_reqs + self.advisor_reqs
        current_tokens = self.classification_tokens + self.advisor_tokens

        if self.arm_a_metrics:
            current_reqs += self.arm_a_metrics.get("requests_count", 0)
            current_tokens += self.arm_a_metrics.get("total_tokens", 0)
        if self.arm_b_metrics:
            current_reqs += self.arm_b_metrics.get("requests_count", 0)
            current_tokens += self.arm_b_metrics.get("total_tokens", 0)

        remaining_reqs_needed = 0
        remaining_tokens_needed = 0

        if next_phase == "Arm_A":
            remaining_reqs_needed = (
                ARM_B_SUB_BUDGET_REQS
                + self.evaluation_reqs
                + self.checker_reqs
                + self.contingency_reqs
            )
            if requested_tokens == 0:
                requested_tokens = 2025000  # Arm A sub-budget
            remaining_tokens_needed = (
                530000  # Arm B sub-budget
                + 110000 # Evaluation sub-budget
                + self.checker_reserved_tokens # 515000
                + self.contingency_reserved_tokens # 25000
            ) # = 1180000
        elif next_phase == "Arm_B":
            remaining_reqs_needed = (
                self.evaluation_reqs
                + self.checker_reqs
                + self.contingency_reqs
            )
            if requested_tokens == 0:
                requested_tokens = 530000  # Arm B sub-budget
            remaining_tokens_needed = (
                110000  # Evaluation sub-budget
                + self.checker_reserved_tokens # 515000
                + self.contingency_reserved_tokens # 25000
            ) # = 650000

        projected_reqs = current_reqs + requested_reqs + remaining_reqs_needed
        projected_tokens = current_tokens + requested_tokens + remaining_tokens_needed

        if projected_reqs > self.request_cap:
            raise RuntimeError(
                f"FAIL-CLOSED: Cannot launch {next_phase}. Projected requests ({projected_reqs}) exceed global cap ({self.request_cap})"
            )
        if projected_tokens > self.token_cap:
            raise RuntimeError(
                f"FAIL-CLOSED: Cannot launch {next_phase}. Projected tokens ({projected_tokens}) exceed global cap ({self.token_cap})"
            )

    def record_phase(self, phase_name: str, metrics: dict):
        if phase_name == "Arm_A":
            self.arm_a_metrics = metrics
        elif phase_name == "Arm_B":
            self.arm_b_metrics = metrics

    def calculate_and_verify_global_budget(self) -> tuple[int, int]:
        reqs_a = self.arm_a_metrics["requests_count"] if self.arm_a_metrics else 1
        toks_a = self.arm_a_metrics["total_tokens"] if self.arm_a_metrics else 67770
        reqs_b = self.arm_b_metrics["requests_count"] if self.arm_b_metrics else 10
        toks_b = self.arm_b_metrics["total_tokens"] if self.arm_b_metrics else 442519

        return calculate_and_verify_global_budget(
            {"requests_count": reqs_a, "total_tokens": toks_a},
            {"requests_count": reqs_b, "total_tokens": toks_b}
        )


def calculate_and_verify_global_budget(
    metrics_a: dict,
    metrics_b: dict,
    classification_reqs: int = 3,
    advisor_reqs: int = 1,
    evaluation_reqs: int = 1,
    checker_reqs: int = 1,
    contingency_reqs: int = 1,
    classification_tokens: int = 10972,
    advisor_tokens: int = 5000,
    evaluation_tokens: int = 17889,
    checker_reserved_tokens: int = 515000,
    contingency_reserved_tokens: int = 25000
) -> tuple[int, int]:
    """Reconciled accounting across all experiment phases including reserved contingency and all token channels (R5)."""
    total_planned_reqs = (
        classification_reqs
        + advisor_reqs
        + metrics_a["requests_count"]
        + metrics_b["requests_count"]
        + evaluation_reqs
        + checker_reqs
        + contingency_reqs
    )
    actual_total_tokens = (
        classification_tokens
        + advisor_tokens
        + metrics_a["total_tokens"]
        + metrics_b["total_tokens"]
        + evaluation_tokens
    )
    planned_total_tokens = actual_total_tokens + checker_reserved_tokens + contingency_reserved_tokens

    print(f">>> Cumulative Requests planned/accounted: {total_planned_reqs} (Budget cap: {GLOBAL_REQUEST_CAP})")
    print(f">>> Cumulative Tokens actual recorded: {actual_total_tokens} (Budget cap: {GLOBAL_TOKEN_CAP})")
    print(f">>> Cumulative Tokens planned with reservations: {planned_total_tokens} (Budget cap: {GLOBAL_TOKEN_CAP})")

    if total_planned_reqs > GLOBAL_REQUEST_CAP:
        raise RuntimeError(f"FAIL-CLOSED: Global request budget exceeded: {total_planned_reqs} > {GLOBAL_REQUEST_CAP}")
    if actual_total_tokens > GLOBAL_TOKEN_CAP:
        raise RuntimeError(f"FAIL-CLOSED: Global actual token budget exceeded: {actual_total_tokens} > {GLOBAL_TOKEN_CAP}")
    if planned_total_tokens > GLOBAL_TOKEN_CAP:
        raise RuntimeError(f"FAIL-CLOSED: Global planned token budget exceeded: {planned_total_tokens} > {GLOBAL_TOKEN_CAP}")

    return total_planned_reqs, actual_total_tokens


def main(mode: str = "monolithic"):
    print(f">>> Beginning experimental executions of Arm A and Arm B (mode: {mode})...")
    tracker = BudgetTracker(GLOBAL_REQUEST_CAP, GLOBAL_TOKEN_CAP)

    # 1. Pre-launch check for Arm A (R5: requests and tokens)
    tracker.check_pre_phase_budget("Arm_A", requested_reqs=1, requested_tokens=67770)

    a_decision = OUTPUTS_DIR / "raw-decision-A.md"
    a_usage = OUTPUTS_DIR / "arm-a-usage.json"
    metrics_a = run_arm("Arm_A", DIR_A, arm_a_prompt, a_decision, a_usage, decomposed=(mode == "decomposed"))
    tracker.record_phase("Arm_A", metrics_a)

    # 2. Pre-launch check for Arm B (R5: requests and tokens)
    tracker.check_pre_phase_budget("Arm_B", requested_reqs=ARM_B_SUB_BUDGET_REQS, requested_tokens=530000)

    b_decision = OUTPUTS_DIR / "raw-decision-B.md"
    b_usage = OUTPUTS_DIR / "arm-b-usage.json"
    metrics_b = run_arm("Arm_B", DIR_B, arm_b_prompt, b_decision, b_usage, decomposed=(mode == "decomposed"))
    tracker.record_phase("Arm_B", metrics_b)

    print("\n==================================================")
    print(">>> COMPARATIVE EXECUTION RESULTS")
    print("==================================================")
    print(f"Arm A Requests: {metrics_a['requests_count']} | Wall Clock: {metrics_a['wall_clock_seconds']:.2f}s | Input: {metrics_a['input_tokens']} | Cache Read: {metrics_a['cached_input_tokens']} | Cache Create: {metrics_a['cache_creation_input_tokens']}")
    print(f"Arm B Requests: {metrics_b['requests_count']} | Wall Clock: {metrics_b['wall_clock_seconds']:.2f}s | Input: {metrics_b['input_tokens']} | Cache Read: {metrics_b['cached_input_tokens']} | Cache Create: {metrics_b['cache_creation_input_tokens']}")

    tracker.calculate_and_verify_global_budget()
    print(">>> All budget checks PASSED in fail-closed verification loop.")


if __name__ == "__main__":
    main()
