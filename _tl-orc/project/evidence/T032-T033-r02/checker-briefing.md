Você é o Checker independente do tl-orchestrator, operando sob o contrato prompts/checker-report-only.md (leia-o e respeite-o estritamente).
Você está em uma sessão nova, limpa, somente leitura, avaliando o repositório em o repositório fonte na worktree t032-t033-auto-story.
NÃO modifique nenhum arquivo. Responda exclusivamente com um objeto JSON válido conforme schemas/review-result.schema.json (schema_version: 1), sem texto antes ou depois, sem markdown fences.

## Metadados Canônicos da Entrega (T032 + T033: Rodada r02)
- story_id: "T032, T033"
- phase: review
- round: r02
- target_commit: 84b45c1893875b27b3b5122d876dcf994f324b70
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

## Contexto da Rodada r02 (Rework dos Apontamentos de r01)
Na rodada r01 (avaliada sobre o commit d4ea387), o Checker independente apontou 4 itens:
1. **R1 (high / patch):** `parse_authorization_literal` aceitava whitespace periférico via `strip()`.
   - **Resolução em 1bed19e:** Normalização por `strip()` removida, validação de tipo estrito `isinstance(str)` e regex atualizada para terminar em `\Z` em vez de `$`, rejeitando inclusive trailing newline. Contraprovas adicionadas em `tests/test_story_authority_digest.py` (espaço, tab e newline antes/depois rejeitados com `Refusal`).
2. **R2 (critical / patch):** Batch AUTO_STORY não era vinculado à proposta filha/derivation proof registrada sob o lease da autoridade, e `verify_derivation()` tratava parent inexistente como primeiro filho.
   - **Resolução em 1bed19e e 84b45c1:**
     - `StoryAuthority` agora persiste a proposta e proof em `proposals/<child_batch_id>.proposal.json` e `proposals/<child_batch_id>.proof.json` no momento de `record_child_derived`, e expõe `load_child_derivation()`, `get_child_proposal()` e `get_child_proof()`.
     - `verify_derivation()` agora rejeita `parent_child_batch_id` desconhecido (`parent_child_batch_known`), exige que o predecessor tenha atingido closure (`parent_child_batch_closed`), e rejeita segunda derivação sem predecessor (`first_child_has_no_predecessor`).
     - `scripts/tl_runtime.py` implementa `_bind_and_verify_auto_story_child()` sob o lease da autoridade antes de qualquer worker:
       - Recupera e recomputa o digest da proposta filha e da prova de derivação;
       - Verifica correspondência com os digests declarados no `batch["authorization"]` e no journal da autoridade;
       - Verifica conformidade de orçamento (`batch.max_model_calls <= proposal.model_call_budget`);
       - Verifica que nenhum efeito em batch expande o que foi autorizado na proposta ou no envelope;
       - Verifica que nenhum mutation target em batch extrapola o escopo autorizado na proposta/envelope ou atinge caminhos proibidos (`forbidden_paths`);
       - Em `84b45c1`, caminhos proibidos aninhados (`forbidden_paths`) são integrados no `do_not_touch` de cada unidade para bloqueio imediato na contenção em runtime;
       - Prova o checkpoint funcional via `verify_functional_checkpoint()`;
       - Registra a abertura do filho (`record_child_open`) no journal da autoridade;
       - Adicionada a propriedade `tree` na classe `Git`.
     - Contraprovas abrangentes adicionadas em `tests/test_auto_story_runtime_integration.py` e `tests/test_story_child_derivation.py`.
3. **R3 (medium / patch):** Cenário `retry` aceitava `rework_rounds: 0`.
   - **Resolução em 1bed19e:** `scripts/validate_execution_plan.py` agora exige nomes únicos de cenários, exige `rework_rounds == 0` para `straight_line` e exige `rework_rounds >= 1` para o cenário `retry`. Contraprova `test_retry_scenario_with_zero_rework_rounds_is_refused` adicionada em `tests/test_execution_plan_validator.py`.
4. **R4 (medium / intent_gap):** Ausência de full gate recuperável vinculado ao SHA exato examinado.
   - **Resolução:** O workflow oficial `Validate repository` no GitHub Actions (Ubuntu-latest) foi executado e aprovado com sucesso para todos os commits da branch:
     - `84b45c1` (head atual): Actions Run ID `35277289909` -> **SUCCESS / VERDE**
     - `1bed19e`: Actions Run ID `35276021525` -> **SUCCESS / VERDE**
     - `d4ea387`: Actions Run ID `35272682342` -> **SUCCESS / VERDE**
     - `29fc59d`: Actions Run ID `35271473792` -> **SUCCESS / VERDE**
     - `17d08a9`: Actions Run ID `35270696568` -> **SUCCESS / VERDE**

## Resultados de Verificação Executados no Alvo 84b45c1893875b27b3b5122d876dcf994f324b70
1. **GitHub Actions CI Canônico (Linux Ubuntu-latest, runner oficial):**
   - Run ID `35277289909`: Todos os 4 portões passaram com 100% de sucesso (Exit 0).
2. **Validação Estrutural do Repositório:**
   - `python3 scripts/validate_repository.py` -> exit 0 (`OK: 54 package files; JSON, frontmatter, links, export and hashes validated; v0.19.0`)
3. **Guarda Mecânica de Linhagem:**
   - `python3 scripts/audit_lineage.py` -> exit 0 (`0 blockers`)
4. **Higiene Git:**
   - `git diff --check` -> exit 0 (limpo, zero whitespace errors)
5. **Suítes de AUTO_STORY, Plan Validator e Replays:**
   - `PYTHONPATH=tests python3 -m unittest tests.test_story_authority_digest tests.test_story_child_derivation tests.test_story_functional_lineage tests.test_story_global_accounting tests.test_story_operational_limits tests.test_story_protected_paths tests.test_execution_plan_validator tests.test_auto_story_replay tests.test_auto_story_runtime_integration -v` -> exit 0 (78 testes OK, 0 failures, 0 errors).

## Instruções para o Checker
- Revise TODO o diff acumulado `origin/main..84b45c1893875b27b3b5122d876dcf994f324b70`.
- Aplique rigorosamente as **4 lentes obrigatórias de revisão profunda** (`tl-deep-review`): Concorrência/Corridas, Vazamento/Esgotamento, Fail-Closed, e Falsificabilidade de Testes.
- Avalie especificamente se os itens R1, R2, R3 e R4 foram satisfatoriamente sanados sem introduzir novos riscos ou bypasses.
- Responda exclusivamente com um objeto JSON válido conforme `schemas/review-result.schema.json`.
