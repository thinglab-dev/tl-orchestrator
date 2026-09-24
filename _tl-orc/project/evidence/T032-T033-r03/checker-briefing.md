Você é o Checker independente do tl-orchestrator, operando sob o contrato prompts/checker-report-only.md (leia-o e respeite-o estritamente).
Você está em uma sessão nova, limpa, somente leitura, avaliando o repositório em o repositório fonte na worktree t032-t033-auto-story.
NÃO modifique nenhum arquivo. Responda exclusivamente com um objeto JSON válido conforme schemas/review-result.schema.json (schema_version: 1), sem texto antes ou depois, sem markdown fences.

## Metadados Canônicos da Entrega (T032 + T033: Rodada r03)
- story_id: "T032, T033"
- phase: review
- round: r03
- target_commit: 44364ce95b0db2d0c409fdef69d4564188d1670d
- base_commit: 69d8351c1e304bb067dfe93e52c8db1a591bd6c1 (origin/main)
- spec_revision:
    T032: 03eef17f6d4b19b71121eb97c40a424611f01267e7ad99e370622deb08681ece
    T033: 64c7b9d81b031161c6398393fad04578620ba43a29b417d0ce5432641a7f75ef
- effective_authors: [anthropic, deepmind] (Planner/Maker inicial: Anthropic Claude Code 2.1.274 Opus 5; Principal Implementation Engineer & Finisher: Google DeepMind Antigravity)
- checker_independence: required (Checker OpenAI Codex gpt-5.6-terra high em sessão isolada e independente de todos os autores efetivos)
- verification_scope: integration_boundary
- integration_group:
    authority: native_standalone
    id: T032-T033
- canonical_full_gate:
    required_now: true
    executed: true
    status: pass

## Contexto da Rodada r03 (Rework do Apontamento R5 de r02)
Na rodada r02 (avaliada sobre o commit 84b45c1), o Checker independente:
- REJEITOU R1: provado sanado (literal sem whitespace/newline, regex `\Z`).
- REJEITOU R3: provado sanado (retry exige >= 1 rework).
- REJEITOU R4: provado sanado (CI Linux GitHub Actions verde no SHA).
- Declarou zero achados nas lentes de concorrência/corridas e esgotamento/recursos.
- Apontou exclusivamente o item crítico **R5 (critical / patch / maker)**:
  - **Problema:** A derivação persistida não era revalidada contra o envelope raiz antes de autorizar o lote. `record_child_derived()` aceitava qualquer proposal/proof sob lease; `load_child_derivation()` só validava digests internos; e o runtime comparava o lote apenas contra a proposta carregada. Assim, uma proposta/proof autodigerida (com hashes internos válidos) porém com efeitos, escopo ou predecessora fora do envelope raiz poderia ser journalizada e executada.
  - **Ação exigida:** Tornar a derivação uma transição validada sob o lease: antes de persistir child_derived, revalidar a proposta contra o envelope e o estado atual; ao bind no runtime, revalidar independentemente contenção, efeitos, orçamento, predecessor/closure e checkpoint contra o envelope, sem confiar apenas no digest ou em proof.checks. Adicionar contraprovas de uma proposta/proof autodigerida registrada diretamente com efeito expandido e com escopo expandido, exigindo HARD STOP antes de child_open/worker.

## Resolução Implementada no Commit 44364ce95b0db2d0c409fdef69d4564188d1670d:
1. **Validador canônico independente contra o envelope raiz (`assert_child_proposal_within_envelope`)**:
   - Implementado em `scripts/tl_story_authority.py`:
     - Valida `proposal` contra o schema Draft 2020-12 `story-child-proposal.schema.json`.
     - Valida imutabilidade de authority_id, work_ref, spec_revision e spec_sha256 contra o envelope raiz (`payload`).
     - Valida subconjunto estrito de escopo: união `required ∪ conditional` da proposta ⊆ união do envelope raiz; nenhum alvo colidindo com `forbidden_paths`; e preservação monotônica de caminhos proibidos (`parent_forbidden <= child_forbidden`).
     - Valida monotonicidade de protected paths (`assert_protected_paths_monotonic`).
     - Valida subconjunto de efeitos: `proposal.allowed_effects ⊆ payload.allowed_effects` contra `EFFECT_KEYS`.
     - Valida orçamento de chamadas: `model_call_budget <= global_model_call_budget`; e no momento da derivação inicial (quando a child ainda não está no journal), `model_call_budget <= remaining_global_budget`.
     - Valida prazo wall clock contra `payload["wall_clock_deadline"]`.
     - Valida integridade de estado (quando `state` é fornecido): autoridade não fechada, `max_child_batches`, `max_active_child_batches`, limite de falhas consecutivas, presença e fechamento do predecessor (`parent_child_batch_known` e `parent_child_batch_closed`), e herança exata do checkpoint funcional revisado pelo Checker anterior.
2. **Derivação como transição validada sob lease (`record_child_derived`)**:
   - Em `scripts/tl_story_authority.py:load_child_derivation`:
     - Após conferir todos os digests criptográficos internos, invoca `assert_child_proposal_within_envelope(proposal, self.payload, self.state, self)`. Mesmo que uma proposta e proof persistidas em disco tenham digests válidos e estejam journalizadas, são independentemente recusadas caso extrapolem qualquer restrição do envelope raiz.
   - Em `scripts/tl_story_authority.py:record_child_derived`:
     - Sob o lease e antes de qualquer gravação atômica em disco ou append no journal, invoca `assert_child_proposal_within_envelope(proposal, self.payload, self.state, self)`.
     - Revalida a integridade da prova e sua ancoragem no digest raiz da autoridade (`proof.root_authority_digest == self.root_digest`) e seu autodigest (`recomputed == proof.derivation_proof_digest`).
   - Em `scripts/tl_story_authority.py:assert_batch_matches_child_proposal`:
     - Invoca `assert_child_proposal_within_envelope(proposal=proposal, payload=payload)`.
     - Valida o lote não apenas contra a proposta filha, mas também diretamente contra o envelope raiz: alvos de mutação dentro de `root_authorized_union` e fora de `root_forbidden`, efeitos permitidos dentro de `payload.allowed_effects`, e chamadas declaradas dentro de `payload.global_model_call_budget`.
3. **Revalidação independente ao bind no runtime (`_bind_and_verify_auto_story_child`)**:
   - Em `scripts/tl_runtime.py:_bind_and_verify_auto_story_child`:
     - Sob o lease da autoridade, recupera proposta e prova via `load_child_derivation()` (que já revalida o envelope).
     - Executa diretamente `story_authority.assert_child_proposal_within_envelope(proposal=proposal, payload=self.authority.payload, state=self.authority.state, authority=self.authority)`.
     - Executa `assert_batch_matches_child_proposal()`.
     - Verifica o checkpoint funcional via `verify_functional_checkpoint()`.
     - Qualquer violação dispara `story_authority.HardStop`, liberando os leases e abortando antes de `record_child_open` ou execução de qualquer worker.
4. **Contraprovas adicionadas em `tests/test_auto_story_runtime_integration.py`**:
   - `test_auto_story_refuses_persisted_self_digested_proposal_with_expanded_effect`:
     - Cria uma proposta maliciosa com efeito expandido (`push: true`, quando o envelope veda push) e uma prova com digests criptográficos autogerados consistentes (hashing válido).
     - Persiste ambos diretamente nos diretórios da autoridade e journaliza `child_derived`.
     - Prova que sob o lease `record_child_derived` recusa com `HardStop("effect_expansion")`.
     - Prova que o runtime em `acquire()` recusa com `Refusal` provocado por `HardStop("effect_expansion")`.
     - Prova que `child_open` NUNCA é registrado no journal da autoridade e o estado do lote filho jamais vira `open`.
   - `test_auto_story_refuses_persisted_self_digested_proposal_with_expanded_scope`:
     - Cria uma proposta com escopo expandido (`unauthorized_dir/malicious.py` fora do envelope) e prova autodigerida com digests válidos.
     - Persiste ambos diretamente nos diretórios da autoridade e journaliza `child_derived`.
     - Prova que sob o lease `record_child_derived` recusa com `HardStop("scope_expansion")`.
     - Prova que o runtime em `acquire()` recusa com `Refusal` provocado por `HardStop("scope_expansion")`.
     - Prova que `child_open` NUNCA é registrado no journal da autoridade.

## Resultados de Verificação Executados no Alvo 44364ce95b0db2d0c409fdef69d4564188d1670d
1. **GitHub Actions CI Canônico (Linux Ubuntu-latest, runner oficial):**
   - Run ID `35290129200`: Todos os 4 portões passaram com 100% de sucesso (Exit 0):
     - Checkout sem credenciais persistidas: PASS
     - Validate repository structure: PASS
     - Run behavior tests for optional supervisor: PASS
     - Run contractual and domain test suites: PASS
     - Run mechanical lineage and governance audit: PASS
2. **Validação Estrutural do Repositório:**
   - `python3 scripts/validate_repository.py` -> exit 0 (`OK: 54 package files; JSON, frontmatter, links, export and hashes validated; v0.19.0`)
3. **Guarda Mecânica de Linhagem:**
   - `python3 scripts/audit_lineage.py` -> exit 0 (`0 blockers`)
4. **Higiene Git:**
   - `git diff --check origin/main` -> exit 0 (limpo, zero whitespace errors)
5. **Suítes de Testes Locais:**
   - `test_story_*.py`: 52 testes OK (Exit 0)
   - `test_auto_story_*.py`: 20 testes OK (incluindo as novas contraprovas) (Exit 0)
   - `test_execution_plan_validator.py`: 16 testes OK (Exit 0)
   - Total: 88 testes de autoridade, plano e runtime executados com 0 falhas e 0 erros.

## Instruções para o Checker
- Revise TODO o diff acumulado `origin/main..44364ce95b0db2d0c409fdef69d4564188d1670d`.
- Aplique rigorosamente as **4 lentes obrigatórias de revisão profunda** (`tl-deep-review`): Concorrência/Corridas, Vazamento/Esgotamento, Fail-Closed, e Falsificabilidade de Testes.
- Avalie especificamente se o item R5 foi integralmente e satisfatoriamente sanado sem introduzir novos riscos ou bypasses.
- Responda exclusivamente com um objeto JSON válido conforme `schemas/review-result.schema.json`.
