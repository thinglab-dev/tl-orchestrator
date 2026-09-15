id: T029
title: Harness Usage Observation v1 — Claude
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 12
depends_on: [T026]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (ratificação empírica da descoberta pós-T026 sobre logs nativos do Claude Code)
decisions: []
spec_author: orchestrator
spec_revision: f27ccbbb7a5ea30b
rework_round: 10
affects_context: []
effective_authors: [google]
checker_independence: required
content_id: f3984856ad4613c096efbec871df55a22f3bbf16:b2581d8cc17cf14b
content_paths: [scripts/tl_usage.py, schemas/usage-observation.schema.json, scripts/fixtures/tl_usage/claude/, scripts/tests/test_tl_usage_claude.py]

## Finding
source: investigação empírica realizada em 2026-09-14 sobre 1.503 rollouts e sessões reais do Claude Code (~/.claude/projects/), cobrindo 41.204 registros físicos assistant em 300 sessões amostradas.
observed: em 300 sessões amostradas, 41.204 registros físicos assistant correspondem a apenas 21.209 pares únicos (sessionId, message.id), com duplicação física média de 1,94x decorrente da emissão de múltiplos blocos de conteúdo compartilhando message.id, requestId e usage. O Claude Code emite contadores nativos heterogêneos (input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens, thinking_tokens), sem total_tokens nativo e sem snapshot cumulativo oficial de sessão. Eventos de compactação contêm métricas de histórico de contexto (preTokens, postTokens, cumulativeDroppedTokens) que não representam uso faturável de inferência. Subagentes vinculam-se por toolUseId, e sessões podem alternar de modelo ou conter registros assistant com message.model: "<synthetic>".
expected: implementar analisador factual determinístico para Claude em scripts/tl_usage.py tratando o harness como domínio de observação independente. Preservar contadores nativos literais sob raw_usage_channels (claude_assistant_messages e claude_unique_responses), correlacionar respostas por (sessionId, message.id) com consistência de requestId, classificar response_kind e excluir <synthetic> do agregado de inferência, isolar compactação em context_compaction_observations, vincular subagentes por referências explícitas mantendo fronteira contábil estrita com o pai, estabelecer completude fail-closed (sem emissão de complete em v1), declarar reconciliation.status como not_observable e evoluir o schema v1 de forma estritamente aditiva sob schema_version: 1.
impact: estende a observabilidade factual para Claude com a mesma robustez empírica conquistada no Codex, eliminando a inflação de ~2x em sessões multi-bloco sem forçar premissas incompatíveis entre os harnesses.
hypothesis: a correlação baseada em (sessionId, message.id) com verificação de consistência por requestId elimina duplicações de múltiplos blocos sem recorrer a heurísticas temporais ou numéricas, enquanto a preservação dos nomes nativos e isolamento de compactação asseguram integridade empírica irrefutável.
dedup: T025 implementou o parser base Codex; T026 calibrou a semântica de eventos Codex. T029 estabelece a observabilidade factual independente do harness Claude.

## Spec
### Intent
Codificar a observação factual, determinística e versionada de sessões do Claude Code (`source_kind: harness_native_log`), tratando o Claude como domínio de observação independente:
1. Preservar a contabilidade bruta e nomes nativos literais sob `raw_usage_channels`: registros físicos observados (`claude_assistant_messages`) e respostas estruturalmente únicas (`claude_unique_responses`).
2. Deduplicar repetições físicas exclusivamente por identidade primária `(sessionId, message.id)` com verificação de consistência estrutural via `requestId`, classificando cada resposta em `response_kind: "model" | "synthetic" | "unknown"`.
3. Contabilizar em `normalized_usage.semantic_request_sum` exclusivamente as respostas únicas com `response_kind == "model"`, preservando `<synthetic>` no canal bruto sem presunção de faturamento de modelo.
4. Manter fronteira contábil estrita entre sessão raiz e subagentes: a observação mede unicamente a sessão principal fornecida em `--session-ref`. Subagentes fornecidos explicitamente enriquecem apenas `thread_topology` via `toolUseId` e nunca são somados ao pai.
5. Isolar métricas de compactação de contexto em `context_compaction_observations` sem qualquer contaminação dos contadores de uso de inferência.
6. Estabelecer completude estritamente fail-closed (sem emissão de `complete` em Claude v1) e declarar `reconciliation.status: not_observable` em decorrência da ausência de acumulador cumulativo oficial de sessão no log nativo.
7. Conceder `parser_status: "supported"` exclusivamente à combinação congelada da versão `2.1.257` e do structural format profile canônico (fingerprint `b3140fe31bd7968a`), garantindo que eventos opcionais (compactação, attachments) não quebrem a compatibilidade.
8. Garantir memória $O(1)$ via ledger limitado a `MAX_CLAUDE_IDENTITY_CAP = 100` e cap de registros em 50, com degradação defensiva sob estouro.
9. Assegurar privacidade normativa absoluta: nunca persistir, emitir, logar ou incluir em digests qualquer conteúdo textual de prompts, respostas, tool calls, tool results ou descrições, e nunca expor caminhos absolutos de entrada.
10. Preservar 100% da retrocompatibilidade da CLI (Codex por padrão, `--harness claude` explícito) e das observações Codex de T025/T026 sob `schema_version: 1` estritamente aditiva.

### Scope and write paths
- `scripts/tl_usage.py` [MODIFIED]:
  - Preservação da CLI legada (`--harness codex` default) e adição de `--harness claude`.
  - Implementação de `parse_claude_session(session_path, run_id, subagent_paths=None)`.
  - Canais nativos `raw_usage_channels.claude_assistant_messages` e `claude_unique_responses`.
  - Classificação estrutural `response_kind` (`model`, `synthetic`, `unknown`).
  - Isolamento de `context_compaction_observations`.
  - Vinculação de subagentes por `toolUseId` sem soma no pai.
  - Degradação fail-closed: completude (`incomplete` ou `not_observable`) e reconciliação (`not_observable`).
  - Suporte ao structural format profile `claude_session_jsonl_v1` (fingerprint `b3140fe31bd7968a`) para versão `2.1.257`.
  - Bounded memory auditável com caps fixos (100 identidades, 50 registros) e sanitização de caminhos.
- `schemas/usage-observation.schema.json` [MODIFIED]:
  - Evolução puramente aditiva sob `schema_version: 1`.
  - Suporte a `harness: "claude"` e `source_format: "claude_session_jsonl"`.
  - Suporte aos canais Claude e propriedade opcional `context_compaction_observations`.
- `scripts/fixtures/tl_usage/claude/` [NEW]:
  - Fixtures dedicadas cobrindo as Classes A a J (totalmente sanitizadas).
- `scripts/tests/test_tl_usage_claude.py` [NEW]:
  - Suíte de testes focais e contrafactuais para observabilidade Claude.

### Input Contract
- Entrada principal obrigatória: caminho explícito para `<session-id>.jsonl` via `--session-ref`.
- Subagentes opcionais: caminhos explícitos via `--subagent-ref` (pares de `.meta.json` e `.jsonl`).
- Proibição estrita: nenhuma varredura recursiva ou descoberta implícita de arquivos no filesystem.
- Fronteira contábil: `raw_usage_channels` e `normalized_usage` medem exclusivamente o arquivo de sessão principal. Subagentes enriquecem apenas `thread_topology`.
- Privacidade de caminhos: nenhum caminho absoluto de input aparece no JSON emitido (somente digests e refs opacas).

### Data Model and Native Channels
- Canais nativos sob `raw_usage_channels`:
  - `claude_assistant_messages`: contabilidade de registros físicos `assistant` contendo `message.usage`.
  - `claude_unique_responses`: contabilidade de responses estruturalmente únicos correlacionados por `(sessionId, message.id)`.
- Contadores nativos literais: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `thinking_tokens`.
- Três grandezas distintas legítimas:
  - `claude_assistant_messages.native_counters_sum`: soma literal física (apresenta inflação ~1.94x).
  - `claude_unique_responses.native_counters_sum`: soma de responses únicos (model + synthetic + unknown).
  - `normalized_usage.semantic_request_sum`: soma exclusiva de unique responses com `response_kind == "model"`.
- Proibições estritas de derivação semântica:
  - Proibido assumir `input_tokens == uncached_input_tokens`.
  - Proibido assumir `thinking_tokens == reasoning_output_tokens`.
  - Proibido assumir `total_input == input_tokens + cache_creation + cache_read`.
  - Proibido mapear `cache_read_input_tokens -> cached_input_tokens` no bloco canônico legado.
  - Campos canônicos sem equivalência comprovada (`total_tokens`, `reasoning_output_tokens`, `uncached_input_tokens`) recebem estritamente `"not_observable"`.

### Structural Identity and Deduplication Rules
- Identidade primária: `(sessionId, message.id)`.
- Controles de consistência estrutural: `requestId`, `message.model` e contadores `native_usage`.
- Deduplicação válida: mesmo `(sessionId, message.id)` com `requestId` consistente e contadores consistentes incrementa contagem física mas conta exatamente 1 vez em `claude_unique_responses` e `normalized_usage`.
- Identidade conflitante (Classe H): mesmo `message.id` com `requestId` divergente, modelo divergente ou contadores divergentes degrada obrigatoriamente para `ambiguous`, `parser_status: partial` e `normalized_usage.status: not_observable`.
- Registros `<synthetic>` (Classe J): classificados com `response_kind: "synthetic"`, preservados no canal físico bruto mas excluídos do `semantic_request_sum` de inferência de modelo.

### Context Compaction Observations
- Registrado em bloco isolado `context_compaction_observations`: `trigger`, `pre_tokens`, `post_tokens`, `cumulative_dropped_tokens`, `duration_ms`, `preserved_messages_count`.
- Proibição contábil: valores de compactação medem tamanho de contexto e jamais são somados a contadores de uso de inferência.
- Proibição de privacidade: textos de resumo de compactação são descartados e nunca persistidos.

### Subagents Topology
- Vinculação estritamente estrutural: `subagent.meta.json["toolUseId"] == parent.tool_use.id`.
- Fronteira contábil: tokens de subagentes NUNCA entram no `normalized_usage` do pai.
- Proibição de privacidade: `description`, prompts e tool payloads de subagentes são descartados.

### Completeness and Reconciliation Policy
- Completude Claude v1:
  - Marcador negativo comprovado (`isAbortedMidStream`, `interruptedByShutdown`, `isApiErrorMessage`, erro de sintaxe) -> `incomplete`.
  - Caso contrário -> `not_observable`.
  - Proibição: T029 v1 NUNCA emite `complete` para Claude (não há marcador positivo ratificado).
- Reconciliação Claude v1:
  - Como o log nativo Claude não emite snapshot cumulativo oficial de sessão, `reconciliation.status` permanece estritamente `"not_observable"`. Proibido fabricar reconciliação circular.

### Structural Format Profile and Bounded Memory Policy
- Structural format profile canônico: `claude_session_jsonl_v1:assistant_paths=[message.id, message.model, message.role, message.usage.cache_creation_input_tokens, message.usage.cache_read_input_tokens, message.usage.input_tokens, message.usage.output_tokens, sessionId, type, uuid]`.
- Fingerprint estável congelado: `b3140fe31bd7968a`.
- Eventos opcionais (compactação, attachments, etc.) não alteram o fingerprint nem a compatibilidade.
- Bounded memory $O(1)$: ledger limitado a `MAX_CLAUDE_IDENTITY_CAP = 100` e registros a `MAX_CLAUDE_RECORDS_CAP = 50`. Acima de 100 identidades, degrada defensivamente para `not_observable` com razão de estouro explícita.

### Invariants
- I1 (Procedência Nativa): `source_kind: harness_native_log`; sem presunções sobre SDK upstream.
- I2 (Anti-Deduplicação Numérica): Vedada deduplicação por contadores coincidentes.
- I3 (Anti-Adjacência): Vedada correlação por proximidade temporal ou ordem de linhas.
- I4 (Identidade Primária Estrita): Correlação governada exclusivamente por `(sessionId, message.id)` com verificação de consistência via `requestId`.
- I5 (Preservação de Nomes Nativos): Contadores mantidos sob nomes literais nativos do Claude.
- I6 (Campos Sem Equivalência como Not Observable): Campos canônicos sem prova contratual recebem `"not_observable"`.
- I7 (Cumulativo Não Factual como Not Observable): `reconciliation.status` e `cumulative` permanecem `"not_observable"`.
- I8 (Completude Fail-Closed): Proibida emissão de `complete` para Claude v1; ausência de erro resulta em `not_observable`.
- I9 (Isolamento de Compactação): Métricas de compactação pertencem a `context_compaction_observations` e nunca ao usage de inferência.
- I10 (Fronteira Contábil e Entrada Explícita de Subagentes): Sem descoberta recursiva; subagentes não são somados ao pai.
- I11 (Tratamento Estrutural de Synthetic): Registros `<synthetic>` recebem `response_kind: "synthetic"`, permanecem no raw e são excluídos do `semantic_request_sum`.
- I12 (Bounded Memory Auditável): Caps fixos no ledger e registros garantem $O(1)$; estouro degrada defensivamente sem gerar subtotais falsos.
- I13 (Privacidade Normativa): Proibida qualquer persistência, emissão, logging ou digest de textos de prompts, respostas, tool calls, tool results, descrições ou caminhos de entrada.
- I14 (Conformidade Aditiva v1 e CLI Retrocompatível): Invocação sem `--harness` mantém comportamento Codex legado por padrão (`--harness codex`); schema Draft 2020-12 estritamente aditivo sob `schema_version: 1`.

### Classes de Teste Mandatórias (A a J)
- Classe A (Sessão Mono-Bloco Padrão): Uma linha assistant por resposta; contadores e IDs preservados 1:1.
- Classe B (Sessão Multi-Bloco com Duplicação Estrutural): Múltiplas linhas assistant consecutivas repetindo usage sob mesmo `message.id` e `requestId`. Exatamente 1 resposta contabilizada em `claude_unique_responses` e `normalized_usage`.
- Classe C (Extended Thinking): Mensagens com `thinking_tokens > 0`. Validação de extração literal e preservação independente, sem presunção de equações ou desigualdades com `output_tokens` e sem conversão em `reasoning_output_tokens`.
- Classe D (Compactação de Contexto): Stream com `compactMetadata` e `isCompactSummary`. Contadores registrados em `context_compaction_observations` sem contaminar usage.
- Classe E (Sessão Multi-Modelo): Respostas com modelos distintos no mesmo log; contabilidade segregada sem imposição de modelo único global.
- Classe F (Subagentes com Vinculação Explícita): Sessão raiz correlacionada a subagentes via `toolUseId` sem soma de tokens no pai.
- Classe G (Sessão Interrompida ou Falha de API): Presença de `isAbortedMidStream`, `interruptedByShutdown` ou `isApiErrorMessage` classificada como `incomplete`.
- Classe H (Identidade Estrutural Conflitante): Reutilização de `message.id` com `requestId`, modelo ou contadores divergentes degrada para `ambiguous`, `partial` e `not_observable`.
- Classe I (Identity Ledger Overflow): Mais de 100 respostas únicas disparam degradação defensiva para `not_observable` com razão de estouro explícita, mantendo $O(1)$.
- Classe J (Modelo Sintético / Assistente Anômalo): Registros com `message.model: "<synthetic>"` recebem `response_kind: "synthetic"`, permanecem no canal bruto e são excluídos de `semantic_request_sum`.

### Acceptance Criteria
- AC1: Suporte a `--harness claude` implementado em `scripts/tl_usage.py` em Python puro stdlib, preservando `--harness codex` como default sem quebra de CLI legada.
- AC2: `raw_usage_channels` expõe contadores segregados entre linhas físicas (`claude_assistant_messages`) e respostas únicas deduplicadas (`claude_unique_responses`).
- AC3: Deduplicação estrutural fundamentada estritamente no par `(sessionId, message.id)` com controle de consistência por `requestId`.
- AC4: Contadores nativos Claude (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `thinking_tokens`) extraídos literalmente sem derivações canônicas forçadas.
- AC5: `cumulative` e `reconciliation.status` permanecem estritamente `"not_observable"`.
- AC6: Eventos de compactação isolados em `context_compaction_observations`, sem soma de seus contadores a métricas de inferência.
- AC7: Subagentes vinculados exclusivamente por referências explícitas e correlação `toolUseId -> tool_use.id`, com fronteira contábil estrita (sem soma no pai).
- AC8: Completude governada por política fail-closed (ausência de erro gera `not_observable`, nunca `complete`).
- AC9: Conflito de identidade (Classe H) ou estouro de ledger (Classe I) degrada fail-closed para `ambiguous` / `partial` / `not_observable`.
- AC10: Registros `<synthetic>` (Classe J) identificados e excluídos de `semantic_request_sum`.
- AC11: Suporte versionado `supported` restrito à combinação congelada inicial (`2.1.257` + fingerprint estrutural canônico `b3140fe31bd7968a`), com degradação das demais versões/perfis.
- AC12: Schema JSON Draft 2020-12 evolui aditivamente sob `schema_version: 1`, suíte de testes passa com 100% nas Classes A a J e regressões Codex, 24 package files permanecem byte-idênticos à baseline v0.12.0, e parecer formal `approved` (0 action items) é emitido por Checker independente sob `checker_independence: required`.
