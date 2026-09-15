id: T026
title: Codex Usage Event Semantics and Deduplication v1
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 6
depends_on: [T025]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (ratificação empírica da calibração pós-T025 sobre canais concorrentes de uso no Codex 0.153.4)
decisions: []
spec_author: orchestrator
spec_revision: aebb3b21edab92ac
rework_round: 2
affects_context: []
effective_authors: [google]
checker_independence: required
content_id: f30b869706f8c5fef3af5e1f173f7a4a8d5a4bac:8fc31840318ec20c
content_paths: [scripts/tl_usage.py, scripts/tests/test_tl_usage.py, scripts/fixtures/tl_usage/codex/, schemas/usage-observation.schema.json, scripts/tests/test_audit_lineage.py]

## Finding
source: calibração empírica pós-T025 conduzida em 2026-09-14 sobre 5.173 sessões reais do Codex em ~/.codex/sessions/ (amostra de rollouts 0.153.4) e revisão independente adversarial r01.
observed: em rollouts reais compatíveis do Codex 0.153.4, dois canais de dados de consumo coexistem de forma recorrente: (1) `token_usage_record` contendo `payload.response_id`, `payload.turn_id`, `payload.thread_id` e contadores `payload.usage`; e (2) `event_msg` (type: `token_count`) contendo telemetria de UI com `payload.info.last_token_usage`, `payload.info.total_token_usage` e `payload.rate_limits`. `token_usage_record` é o único canal que transporta a identidade estrutural primária da resposta (`response_id`); `event_msg(token_count)` é um canal de telemetria desprovido de chaves de resposta (`response_id`, `turn_id`, `thread_id`). O analisador T025 processa ambos como deltas independentes em `raw_usage.per_response_sum`, produzindo aproximadamente 2x o snapshot cumulativo oficial e reportando `divergent`.
expected: determinar e codificar, de maneira determinística, versionada e verificável sem adivinhação e sem recorrer a adjacência temporal ou de ordem de linhas (I21), quais registros representam eventos de consumo estruturalmente identificados. Declarar formalmente `token_usage_record` como o ledger primário por resposta identificado por `response_id`, e `event_msg(token_count)` como canal de telemetria e snapshot cumulativo não correlacionável por resposta individual. Preservar canais brutos (`raw_usage_channels`), camada de correlação estrutural estrita (`semantic_correlations`) e agregado normalizado (`normalized_usage`), mantendo a semântica de `raw_usage` de T025 e garantindo `schema_version: 1` aditivo.
impact: viabiliza medição granular e exata do consumo de tokens por resposta e reconciliação exata com o acumulador cumulativo oficial para sessões elegíveis, sem quebrar retrocompatibilidade nem presumir igualdade semântica no Claude/Agy.
hypothesis: a correlação baseada em identidade primária explícita (response_id) e controles de consistência (turn_id, thread_id), combinada com o desacoplamento estrito de canais de telemetria desprovidos de chave (event_msg) e degradação para ambiguous em caso de ausência ou conflito de identidade, elimina duplicações espúrias sem recorrer a igualdade numérica ou adjacência.
dedup: T025 implementou o parser base, invariantes de observabilidade e validação de schema. T026 calibra a semântica interna de eventos de consumo e deduplicação estrutural para o harness Codex.

## Spec
### Intent
Determinar empiricamente e codificar de forma determinística, versionada e verificável, sem assumir equivalência por premissa e sem recorrer a heurísticas de valor numérico, adjacência sequencial ou proximidade temporal, quais registros no stream de rollouts do Codex representam eventos de consumo semanticamente independentes e quais constituem representações concorrentes ou de telemetria.

Garantir que, para sessões compatíveis estruturalmente elegíveis para a regra de normalização, o consumo semântico por resposta seja derivado de identidades estruturais comprovadas (`token_usage_records` com `response_id`) e reconcilie campo a campo com o acumulador cumulativo final oficial (`cumulative_snapshots` via `total_token_usage`, Σ semantic_per_response.<campo> == final_cumulative.<mesmo_campo>). Caso a evidência estrutural seja insuficiente, conflitante ou exceda os limites de memória auditáveis, o instrumento deve degradar explicitamente para ambiguous / partial / not_observable, sem forçar reconciliações artificiais e sem alterar o status de reconciliação em função do resultado numérico.

### Scope and write paths
- `scripts/tl_usage.py` [MODIFIED]:
  - Preservação estrita da semântica original de `raw_usage` (T025).
  - Implementação de `raw_usage_channels` com contabilidade separada de cada canal (`token_usage_record`, `event_msg_last_token_usage`, `cumulative_snapshots`).
  - Implementação da camada explícita `semantic_correlations` com identificadores de correlação baseados estritamente em `response_id`, eliminando qualquer associação de `event_msg` por adjacência de estado (`active_response_id`).
  - Implementação de `normalized_usage` com `rule_id` versionado e reconciliação campo a campo semântica.
  - Avaliação de `eligible_for_normalization` puramente sobre propriedades estruturais antes do cálculo do delta.
  - Bounded memory: cap auditável sobre `semantic_correlations.records` (50) e cap sobre o ledger interno de identidades (`MAX_IDENTITY_LEDGER_CAP = 100`) para garantir estado $O(1)$ estrito, degradando defensivamente caso o limite seja ultrapassado.
- `schemas/usage-observation.schema.json` [MODIFIED]:
  - Evolução estritamente aditiva sob `schema_version: 1` adicionando propriedades opcionais `raw_usage_channels`, `semantic_correlations` e `normalized_usage`.
- `scripts/fixtures/tl_usage/codex/` [MODIFIED/NEW]:
  - Fixtures dedicadas para cobertura das Classes A a F, com sanitização integral de caminhos privados e dados brutos de usuário.
- `scripts/tests/test_tl_usage.py` [MODIFIED]:
  - Testes focais para todas as 6 classes de teste (A a F), sondas contrafactuais de reordenação/adjacência e limites de bounded memory.
- `scripts/tests/test_audit_lineage.py` [PRESERVED]:
  - Mantido compatível com o CAS dinâmico do board.

### Invariants
- I1 a I19: Preservação integral das 19 invariantes de observabilidade e arquitetura de T025.
- I20 (Anti-Deduplicação Numérica): É terminantemente proibido deduplicar eventos de consumo com base em igualdade numérica de contadores de tokens.
- I21 (Anti-Deduplicação por Proximidade ou Adjacência): É proibido inferir mesma identidade de consumo com base em adjacência de linhas no JSONL, proximidade de timestamps, estado sequencial ativo ou ordinais isolados.
- I22 (Hierarquia Estrita de Correlação): A correlação obedece exclusivamente à hierarquia: `exact_identity` -> `versioned_structural_relation` -> `ambiguous`. Sem identidade comprovada, recusa-se normalização.
- I23 (Preservação Semântica de T025): O bloco `raw_usage` mantém exatamente a semântica cumulativa e de soma de deltas de T025; a nova visão reconciliada reside exclusivamente em `normalized_usage`.
- I24 (Elegibilidade Não Circular): A elegibilidade para normalização depende estritamente da estrutura do stream observada antes de inspecionar o delta; se a sessão for elegível e o delta for diferente de zero, o resultado permanece estritamente `divergent`.
- I25 (Bounded Memory Independente do Cálculo): O cap de persistência detalhada de correlações afeta apenas a amostra retida em `records`; a totalização de `summary` e `normalized_usage` processa 100% dos eventos observados dentro do limite do ledger.
- I26 (Conformidade Aditiva v1): O schema permanece `schema_version: 1` de forma estritamente aditiva; observações geradas sob T025 continuam 100% válidas.

### Classes de Teste Mandatórias (A a F)
- Classe A (Duplicação Estrutural Comprovada): Dois registros no stream compartilham identidade estrutural comprovada (`response_id` e mesmo ciclo de turno). Exatamente um entra em `semantic_per_response_sum`.
- Classe B (Eventos Independentes com Contadores Idênticos): Duas respostas com identidades distintas possuem coincidentemente os mesmos números de tokens. Ambas contam no agregado semântico.
- Classe C (Relação Ambígua por Falta de Identidade): Registros sem identificador estrutural suficiente degradam para `ambiguous`, `parser_status: partial` e `normalized_usage.status: not_observable`.
- Classe D (Reconciliação em Amostra Real Elegível): Rollouts reais do Codex 0.153.4 estruturalmente elegíveis produzem `reconciled` com delta zero campo a campo.
- Classe E (Regressão Integral T025): Todos os 48 testes pré-existentes de T025 passam integralmente sem quebra de contrato.
- Classe F (Identidade Estrutural Conflitante): Registros aparentemente correlacionados apresentam identificadores contraditórios (ex: turn_id divergente). Proibido escolher arbitrariamente; degrada para `ambiguous`, `partial` e `not_observable`.

### Acceptance Criteria
- AC1: `raw_usage_channels` expõe contadores segregados de `token_usage_records`, `event_msg_token_counts` e `cumulative_snapshots`.
- AC2: `raw_usage` preserva estritamente a semântica e os valores produzidos sob T025.
- AC3: Correlação estrutural baseia-se exclusivamente em `exact_identity` (com `response_id` como identidade primária no Codex 0.153.4 e `turn_id`/`thread_id` como controles de consistência sobre `token_usage_records`). `event_msg(token_count)` é classificado como canal de telemetria/snapshot sem identidade de resposta, sendo estritamente vedada sua associação a respostas por ordem ou adjacência (I21).
- AC4: Eventos independentes com números de tokens coincidentes são preservados como eventos distintos no consumo semântico (Classe B).
- AC5: Ausência de identidade (Classe C) ou conflito entre identificadores estruturais (Classe F) degrada obrigatoriamente para `ambiguous`, `parser_status: partial` e `normalized_usage.status: not_observable`.
- AC6: Para sessões estruturalmente elegíveis (versão/fingerprint suportados, canais necessários observáveis, sem ambiguidade/conflito e snapshot cumulativo observável), `semantic_per_response_sum` (derivado do ledger estrutural de `token_usage_records`) reconcilia com delta 0 em relação ao acumulador final. Se houver divergência factual, permanece `divergent`.
- AC7: O cap de retenção de registros de correlação não trunca a contabilidade de `summary` e `normalized_usage`, e reporta metadados de truncamento (`records_observed`, `records_retained`, `records_truncated`).
- AC8: Contrato JSON Schema evolui estritamente de forma aditiva mantendo `schema_version: 1`, com retrocompatibilidade total com as observações de T025.
- AC9: Suíte de testes unitários e de integração cobre rigorosamente as Classes A a F, sondas contrafactuais de reordenação/adjacência e limites de bounded memory, passando com 100% de sucesso.
- AC10: Os 24 arquivos de distribuição listados em `distribution-manifest.json` permanecem byte-idênticos à baseline v0.12.0.
- AC11: `scripts/validate_repository.py` e `scripts/audit_lineage.py` passam com zero erros.
- AC12: Parecer formal `approved` (0 action items) emitido em sessão limpa e somente leitura por Checker report-only de família distinta de todos os autores efetivos do conteúdo, sob `checker_independence: required`, selecionado pelo Classifier.
