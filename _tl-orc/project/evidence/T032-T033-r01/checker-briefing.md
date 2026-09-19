Você é o Checker independente do tl-orchestrator, operando sob o contrato prompts/checker-report-only.md (leia-o e respeite-o estritamente).
Você está em uma sessão nova, limpa, somente leitura, avaliando o repositório local (worktree t032-t033-auto-story).
NÃO modifique nenhum arquivo. Responda exclusivamente com um objeto JSON válido conforme schemas/review-result.schema.json (schema_version: 1), sem texto antes ou depois, sem markdown fences.

## Metadados Canônicos da Entrega (T032 + T033: Rodada r01)
- story_id: "T032, T033"
- phase: review
- round: r01
- target_commit: d4ea38742eeca75b3f67e98c0f491f32b32ae5a3
- base_commit: 69d8351c1e304bb067dfe93e52c8db1a591bd6c1 (origin/main)
- spec_revision:
    T032: 03eef17f6d4b19b71121eb97c40a424611f01267e7ad99e370622deb08681ece
    T033: 64c7b9d81b031161c6398393fad04578620ba43a29b417d0ce5432641a7f75ef
- effective_authors: [anthropic] (Planner/Maker: Anthropic Claude Code 2.1.274 Opus 5)
- checker_independence: required (Checker OpenAI Codex gpt-5.6-terra high em sessão isolada e independente de todos os autores efetivos)
- verification_scope: integration_boundary
- integration_group:
    authority: native_standalone
    id: T032-T033
- canonical_full_gate:
    required_now: true
    executed: true
    status: pass

## Resultados de Verificação Executados no Alvo d4ea38742eeca75b3f67e98c0f491f32b32ae5a3
1. **GitHub Actions CI Canônico (Linux Ubuntu-latest, runner oficial):**
   - PR #60 (`feat/t032-t033-auto-story-and-plan-validator`)
   - Workflow `Validate repository` (Run ID `35271473792`, Job ID `105371681724`):
     - `Validate repository structure` (`validate_repository.py`): PASS
     - `Run behavior tests for the optional supervisor` (`python3 -m unittest discover -s tests -p "test_*.py" -v`): PASS
     - `Run contractual and domain test suites` (`python3 -m unittest discover -s scripts/tests -p "test_*.py" -v`): PASS
     - `Run mechanical lineage and governance audit` (`audit_lineage.py`): PASS
     - Status final: **SUCCESSFUL / VERDE (10m52s)**.
2. **Validação Estrutural do Repositório:**
   - `python3 scripts/validate_repository.py` -> exit 0 (`OK: 54 package files; JSON, frontmatter, links, export and hashes validated; v0.19.0`)
3. **Guarda Mecânica de Linhagem:**
   - `python3 scripts/audit_lineage.py` -> exit 0 (`0 blockers`, apenas warnings L12 preexistentes de menções a tasks aposentadas)
4. **Higiene Git:**
   - `git diff --check` -> exit 0 (limpo, zero whitespace errors)
5. **Suíte Completa das 27 Contraprovas e Replays de AUTO_STORY e Plan Validator:**
   - `PYTHONPATH=tests python3 -m unittest tests.test_story_authority_digest tests.test_story_child_derivation tests.test_story_functional_lineage tests.test_story_global_accounting tests.test_story_operational_limits tests.test_story_protected_paths tests.test_execution_plan_validator tests.test_auto_story_replay tests.test_auto_story_runtime_integration -v` -> exit 0 (`Ran 73 tests in 22.311s: OK, 0 failures, 0 errors`)
6. **Nota de Ambiente Local (macOS Darwin vs Linux Ubuntu):**
   - No ambiente local macOS, o sandbox nega `killpg(9)` process group signals (`tests/test_tl_job.py`) e `/var` é symlink para `/private/var` (`scripts/tests/test_tl_graft.py`). Ambos os módulos são comprovadamente byte-idênticos a `origin/main` (zero regressões). O sinal canônico é o CI oficial Linux onde ambos executaram e passaram 100% verde (Run ID 35271473792).

## Escopo e Especificação Técnica (T032 + T033)

### T032 — Story Authority Envelope & Autonomous Child Batches (AUTO_STORY)
1. **Opt-in estrito:** Lotes legados sem `story_authority_mode` continuam como `direct_proposal` sem barreira nem autoridade.
2. **Envelope imutável de Root Story Authority:**
   - Persistência humana: `_tl-orc/project/story-authorities/<authority_id>.json`
   - Persistência operacional: `_tl-orc/runtime/story-authorities/<authority_id>/` (`journal.jsonl`, `status.json`, `lease.lock`)
   - Separação formal: `authority_payload` de exatamente 12 campos, `root_authority_digest = SHA256(canonical_json(authority_payload))` sem autorreferência nem metadata posterior.
   - Frase humana canônica: `AUTORIZO STORY <work_ref> sha256:<root_authority_digest>`.
3. **Journal e Budget Global:**
   - Append-only, write-ahead, fsync, hash-chained com `prev`, single-writer sob `lease.lock`.
   - Eventos: `authority_open`, `model_call_reserved`, `model_call_consumed`, `model_call_released`, `child_derived`, `child_open`, `child_closed`, `child_failed`, `hard_stop`, `authority_closed`.
   - `status.json` é exclusivamente projeção reconstruível.
   - Child budget é apenas subalocação/projeção do ledger global.
4. **Logical Call != Physical Attempt:**
   - Separação de `logical_call_id` e `global_attempt_id`.
   - Retry: mesmo `logical_call_id`, novo `global_attempt_id`.
   - `ambiguous` conta conservadoramente como consumido. Replay do mesmo `global_attempt_id` é idempotente.
5. **Derivação Automática Patch-Only:**
   - Apenas se TODOS os findings forem `target_role = maker`, `category = patch`, `scope_status = inside_parent_envelope`, `spec_status = unchanged`.
   - Qualquer finding não-patch, `intent_gap`, `bad_spec` ou expansão gera HARD STOP.
6. **Subconjunto de Escopo:**
   - `union(child.required_mutation_targets, child.conditional_mutation_targets) ⊆ parent.authorized_write_scope`.
7. **Linhagem Funcional (Functional Lineage):**
   - Em `changes_requested` com limite esgotado, NÃO integra em `main`.
   - O runtime materializa o commit revisado em `refs/tl/functional-checkpoints/<batch>/<unit>`.
   - O próximo child nasce exatamente desse commit (`functional_parent_checkpoint`).
8. **Bloqueio Mecânico de Model Calls no Worker:**
   - PATH controlado no worker bloqueando chamadas diretas a `agy`, `codex`, `claude`, `gemini`.
9. **Invariante T028 Preservada:**
   - `allowed_effects.merge = true` NÃO faz bypass do `MergeAuthorityGate` nem de `AuthorityReceipt` do T028.
   - AUTO_STORY NUNCA inicia a próxima Story.

### T033 — Execution Plan Validator & First-Class Protected Paths
1. **Execution Plan Validator:**
   - `scripts/validate_execution_plan.py` implementa `LIFECYCLE_PHASES` fechado (`pre_execution`, `post_maker_pre_review`, `post_checker_pre_merge`, `post_merge_pre_close`, `post_terminal`) e `ASSERTION_REGISTRY` fechado.
   - Asserção desconhecida ou fase incompatível gera FAIL CLOSED imediato.
   - `gate_call_constraints_are_satisfiable_under_budget` valida aritmeticamente os cenários `straight_line` e `retry`.
2. **Protected Paths First-Class:**
   - Políticas: `read_only`, `exact_file_hash`, `exact_set_snapshot` (compara recursivamente `path`, `type`, `size`, `sha256`).
   - Monotonicidade parent -> child: padrão, policy e parâmetros herdados devem ser idênticos. Child pode adicionar proteções, mas não remover nem enfraquecer.

## Mapeamento das 27 Contraprovas Obrigatórias
1. `test_root_authority_digest_has_no_self_reference` (em `tests/test_story_authority_digest.py`) -> PASS
2. `test_authorization_metadata_does_not_change_root_digest` (em `tests/test_story_authority_digest.py`) -> PASS
3. `test_mutated_authority_payload_invalidates_operator_authorization` (em `tests/test_story_authority_digest.py`) -> PASS
4. `test_auto_story_cannot_start_without_exact_root_digest_authorization` (em `tests/test_story_authority_digest.py`) -> PASS
5. `test_child_rejects_spec_hash_mutation` (em `tests/test_story_child_derivation.py`) -> PASS
6. `test_child_budget_cannot_reset_or_exceed_parent_remaining` (em `tests/test_story_child_derivation.py`) -> PASS
7. `test_child_rejects_effect_expansion` (em `tests/test_story_child_derivation.py`) -> PASS
8. `test_non_patch_checker_finding_cannot_auto_derive_child` (em `tests/test_story_child_derivation.py`) -> PASS
9. `test_parent_conditional_path_can_become_child_required` (em `tests/test_story_child_derivation.py`) -> PASS
10. `test_derived_child_inherits_exact_unmerged_checker_reviewed_checkpoint` (em `tests/test_story_functional_lineage.py`) -> PASS
11. `test_two_runtimes_cannot_double_spend_parent_budget` (em `tests/test_story_global_accounting.py`) -> PASS
12. `test_cross_ledger_call_is_counted_exactly_once` (em `tests/test_story_global_accounting.py`) -> PASS
13. `test_crash_between_parent_and_child_reservation_does_not_double_debit` (em `tests/test_story_global_accounting.py`) -> PASS
14. `test_ambiguous_global_call_is_consumed_once` (em `tests/test_story_global_accounting.py`) -> PASS
15. `test_child_budget_is_projection_of_parent_allocation` (em `tests/test_story_global_accounting.py`) -> PASS
16. `test_retry_uses_new_global_attempt_id` (em `tests/test_story_global_accounting.py`) -> PASS
17. `test_two_provider_attempts_consume_two_global_slots` (em `tests/test_story_global_accounting.py`) -> PASS
18. `test_replay_same_global_attempt_id_is_idempotent` (em `tests/test_story_global_accounting.py`) -> PASS
19. `test_ambiguous_attempt_then_retry_consumes_two_slots` (em `tests/test_story_global_accounting.py`) -> PASS
20. `test_protected_paths_symlink_tampering` (em `tests/test_story_protected_paths.py`) -> PASS
21. `test_child_cannot_weaken_protected_path_policy` (em `tests/test_story_protected_paths.py`) -> PASS
22. `test_child_cannot_replace_expected_file_hash` (em `tests/test_story_protected_paths.py`) -> PASS
23. `test_child_cannot_replace_exact_set_snapshot` (em `tests/test_story_protected_paths.py`) -> PASS
24. `test_child_may_add_additional_protected_path` (em `tests/test_story_protected_paths.py`) -> PASS
25. `test_max_consecutive_failures_halts_auto_story` (em `tests/test_story_operational_limits.py`) -> PASS
26. `test_auto_story_strictly_prohibits_next_story_start` (em `tests/test_story_operational_limits.py`) -> PASS
27. `test_execution_plan_validator_rejects_temporal_phase_mismatch` (em `tests/test_execution_plan_validator.py`) -> PASS

## Replay B013 -> B014
- Implementado em `tests/test_auto_story_replay.py`.
- Reconstrói deterministicamente o ciclo com repositório Git real, fixtures em `tests/fixtures/auto_story_b013_b014/` e recibo T028 autêntico (`tests/fixtures/auto_story_b013_b014/b014-merge-receipt.json`).
- Distingue rigorosamente a fonte da autoridade (root Story Authority) da fonte do estado funcional (checkpoint B013).

## Instruções para o Checker
- Aplique rigorosamente as **4 lentes obrigatórias de revisão profunda** (`tl-deep-review`): Concorrência/Corridas, Vazamento/Esgotamento, Fail-Closed, e Falsificabilidade de Testes.
- Procure exclusivamente defeitos materiais, violações contratuais, riscos de integridade ou lacunas probatórias. Não faça sugestões de estilo ou polishing.
- Responda exclusivamente com um objeto JSON válido conforme `schemas/review-result.schema.json`.
