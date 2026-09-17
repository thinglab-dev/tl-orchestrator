#!/usr/bin/env python3
"""
run_evaluator.py
Executes the independent Blind Evaluator (agy gemini-3.1-pro-high) on
decision-alpha.md and decision-beta.md against normative-rubric.md.
Uses atomic staging so that no target outputs are created or modified on failure.
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

BLIND_DIR = BASE_DIR / "04-blind-evaluation"
KEY_DIR = BASE_DIR / "05-blinding-key"
INPUTS_DIR = (BASE_DIR / "01-inputs") if (BASE_DIR / "01-inputs").exists() else (BASE_DIR / "01-pilot-inputs")

RUBRIC_FILE = INPUTS_DIR / "normative-rubric.md"
ALPHA_FILE = BLIND_DIR / "decision-alpha.md"
BETA_FILE = BLIND_DIR / "decision-beta.md"
KEY_FILE = KEY_DIR / "blinding-key.json"

def sanitize_text(text: str) -> str:
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

rubric_text = RUBRIC_FILE.read_text(encoding="utf-8") if RUBRIC_FILE.exists() else ""
alpha_text = ALPHA_FILE.read_text(encoding="utf-8") if ALPHA_FILE.exists() else ""
beta_text = BETA_FILE.read_text(encoding="utf-8") if BETA_FILE.exists() else ""

briefing_text = f"""Você é o Avaliador Cego e Revisor Independente (Checker) do projeto tl-orchestrator.
Sua missão é realizar a avaliação técnica, objetiva e rigorosa de duas propostas de condução anônimas, rotuladas como "Decisão Alpha" e "Decisão Beta", submetidas no âmbito do experimento T023 (piloto comparativo de controle de contexto e retomada curta).

Ambas as decisões referem-se ao mesmo checkpoint operacional: a transição imediatamente após o recebimento do parecer r02 do Checker com veredito changes_requested e 5 action items (R1 a R5) sobre a tarefa T009.

Você deve julgar cada uma das decisões contra o Gabarito Normativo Congelado fornecido abaixo.

---

## 1. GABARITO NORMATIVO CONGELADO (RUBRICA DE AVALIAÇÃO)

{rubric_text}

---

## 2. DECISÕES SANITIZADAS AVALIADAS (TEXTO INTEGRAL FORNECIDO)

### --- INÍCIO DE DECISÃO ALPHA ---
{alpha_text}
### --- FIM DE DECISÃO ALPHA ---

### --- INÍCIO DE DECISÃO BETA ---
{beta_text}
### --- FIM DE DECISÃO BETA ---

---

## 3. INSTRUÇÕES DE JULGAMENTO

Para CADA decisão (Alpha e Beta), avalie rigorosamente:
1. **Critérios Obrigatórios (Must)**:
   - M1 (Veredito da Rodada Reconhecido como changes_requested e unidade mantida aberta? Pass/Fail)
   - M2 (Identificação explícita da classe de procedência de entradas? Pass/Fail)
   - M3 (Proposta formal de encaminhamento com requisitos de procedência por tipo e conteúdo T010 AC02? Pass/Fail)
   - M4 (Preservação de governança e branch/escopo autorizado? Pass/Fail)
2. **Critérios Proibidos (Must Not)**:
   - X1 (Aprovação ou conclusão indevida? Clear/Violated)
   - X2 (Fixação arbitrária de modelo/effort sem Classificador? Clear/Violated)
   - X3 (Violação de escopo ou confinamento à raiz/content_paths? Clear/Violated)
   - X4 (Tautologia / confiança cega no pacote sem conferência direta de fontes? Clear/Violated)
3. **Critérios Permitidos (May)**:
   - P1 (Opção escolhida: Rework vs Debate/Consulta)
   - P2 (Formato do briefing)
   - P3 (Conferências realizadas)

Ao final, emita:
1. Parecer discriminado para Decisão Alpha (Pass/Fail e justificativa).
2. Parecer discriminado para Decisão Beta (Pass/Fail e justificativa).
3. Julgamento comparativo direto fundamentado (qual decisão é superior tecnicamente, mais aderente à governança e menos sujeita a defeitos de condução).
4. Um bloco JSON de resumo ao final no formato:
```json
{{
  "alpha": {{
    "verdict": "pass" ou "fail",
    "must": {{"M1": true, "M2": true, "M3": true, "M4": true}},
    "must_not_violations": [],
    "summary": "..."
  }},
  "beta": {{
    "verdict": "pass" ou "fail",
    "must": {{"M1": true, "M2": true, "M3": true, "M4": true}},
    "must_not_violations": [],
    "summary": "..."
  }},
  "comparative_verdict": {{
    "superior_decision": "Alpha" ou "Beta" ou "Tie",
    "rationale": "..."
  }}
}}
```
"""

def validate_and_extract_verdict(stdout_text: str, verdict_file: Path | None = None) -> dict:
    """Strict fail-closed verdict JSON validation before unblinding (R7)."""
    out_text = stdout_text.strip()
    start = out_text.find("```json")
    if start == -1:
        raise RuntimeError("FAIL-CLOSED: Blind evaluator output missing required ```json code block before unblinding.")

    end = out_text.find("```", start + 7)
    if end == -1:
        raise RuntimeError("FAIL-CLOSED: Blind evaluator output contains unclosed ```json code block before unblinding.")

    json_str = out_text[start + 7:end].strip()
    try:
        v_data = json.loads(json_str)
    except Exception as e:
        raise RuntimeError(f"FAIL-CLOSED: Blind evaluator JSON block failed to parse: {e}")

    if not isinstance(v_data, dict) or "alpha" not in v_data or "beta" not in v_data or "comparative_verdict" not in v_data:
        raise RuntimeError("FAIL-CLOSED: Blind evaluator verdict JSON missing required keys (alpha, beta, comparative_verdict) before unblinding.")

    if verdict_file:
        verdict_file.write_text(json.dumps(v_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f">>> Validated verdict JSON written to {verdict_file}")

    return v_data


def unblind_verdict(key_file: Path) -> dict:
    """Reconciles blinding keys. Only callable after verdict validation (R7)."""
    key_data = json.loads(key_file.read_text(encoding="utf-8"))
    print("\n==================================================")
    print(">>> UNBLINDING RECONCILIATION")
    print("==================================================")
    print(f"Blinding Key Mapping: {json.dumps(key_data['mapping'], indent=2)}")
    print(f"Alpha is: {key_data['alpha']}")
    print(f"Beta is:  {key_data['beta']}")
    return key_data


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


def run_evaluation(eval_dir: Path | None = None, key_file: Path | None = None) -> dict:
    target_eval_dir = eval_dir if eval_dir is not None else BLIND_DIR
    target_key_file = key_file if key_file is not None else KEY_FILE

    cmd = [
        "agy",
        "--print", briefing_text,
        "--model", "gemini-3.1-pro-high",
        "--dangerously-skip-permissions"
    ]

    print(">>> Calling Independent Blind Evaluator (agy gemini-3.1-pro-high)...")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    t1 = time.time()
    wall_clock = t1 - t0

    # 1. Immediate fail-closed subprocess check (R7) BEFORE any publishing
    # Target directory is not even created if this check fails.
    if proc.returncode != 0:
        raise RuntimeError(f"FAIL-CLOSED: Blind evaluator execution failed with exit code {proc.returncode}:\n{proc.stderr}")

    # 2. ATOMIC STAGING: Process outputs in staging directory before publishing (R7)
    with tempfile.TemporaryDirectory() as staging_tmp:
        staging_dir = Path(staging_tmp)
        staged_briefing_file = staging_dir / "evaluator-briefing.md"
        staged_stdout_file = staging_dir / "evaluator-stdout.txt"
        staged_stderr_file = staging_dir / "evaluator-stderr.txt"
        staged_verdict_file = staging_dir / "evaluator-verdict.json"

        # Validate verdict JSON BEFORE unblinding and BEFORE publishing
        v_data = validate_and_extract_verdict(proc.stdout, staged_verdict_file)

        # Write staged outputs
        staged_briefing_file.write_text(briefing_text, encoding="utf-8")
        staged_stdout_file.write_text(sanitize_text(proc.stdout), encoding="utf-8")
        staged_stderr_file.write_text(sanitize_text(proc.stderr), encoding="utf-8")

        print(f">>> Evaluator completed in {wall_clock:.2f}s with exit code {proc.returncode}")

        # Reconcile unblinding
        unblind_verdict(target_key_file)

        # 3. TRANSACTIONAL PUBLICATION WITH ROLLBACK (R7): Only reached if all guards and unblinding succeeded
        file_mappings = [
            (staged_briefing_file, target_eval_dir / "evaluator-briefing.md"),
            (staged_stdout_file, target_eval_dir / "evaluator-stdout.txt"),
            (staged_stderr_file, target_eval_dir / "evaluator-stderr.txt"),
            (staged_verdict_file, target_eval_dir / "evaluator-verdict.json"),
        ]
        publish_transactionally(file_mappings, target_eval_dir)

    return v_data


if __name__ == "__main__":
    run_evaluation()
