# Análise: Validação Semântica da Classificação pelo Orquestrador (T009)

unit: native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md  
base_revision: 0de10d6  
maker: agy gemini-3.8-flash-high (tier heavy)  
date_utc: 2026-09-07T21:37:00Z  
kind: analysis  
rework_round: 2  

---

## Sumário Executivo

Esta análise investiga a causa da aceitação recorrente de classificações inválidas pelo Orquestrador em múltiplos harnesses e releases, formaliza a proposta de separação da validação em três estágios explícitos (Conferência Mecânica, Julgamento Registrado e Liberação de Despacho) com exigência estrita de procedência das entradas e verificação contra o schema, e demonstra, por meio de protótipo executável (`T009-mechanical-check.py`) aplicado sobre um piloto de 17 casos (o caso válido real de T005 review sob restrição `required`, 4 alterações deliberadas, 1 variante de `story_id` nulo, 1 controle de regras preservadas sob `preferred`, e 10 novos controles cobrindo R2 a R5), a rejeição determinística de todas as alterações inválidas e o bloqueio de despachos indevidos com `despacho: nenhum`.

---

## AC01: Diagnóstico com Ocorrências Registradas e Citações por Caminho

A validação semântica prevista em `prompts/orchestrator-perfis.md#classificar-e-resolver` determina expressamente:
> "Valide o objeto contra o schema e confira a semântica: schema versão 2; correspondência exata de story, fase e revisões de contexto e catálogo; papéis exatos; um candidato por harness na ordem configurada; pares, efforts, pins, restrições e orçamento; model: null se e somente se effort: null; e cada evidence_id fornecido no briefing e pertinente ao modelo/tarefa. Confira também se cost_basis não promete mais que a evidência e, quando diferente de unknown, tem ao menos um ID econômico pertinente... Saída inválida permite no máximo uma correção de formato/contrato na mesma sessão; se continuar inválida, bloqueie."

Apesar dessa determinação congelada, múltiplos testes de roteamento e execuções no fonte registraram aceitação indevida de classificações inválidas. Em conformidade com o rigor metodológico de AC01, separam-se aqui três categorias explícitas:

### Categoria 1: Fatos Observados (com fonte)

1. **Consumidor platform — Smoke v0.4.0 r02**  
   *Citação:* evidência da atualização v0.4.0 do consumidor platform: `_tl-orc/evidence/tl-orchestrator-v0.4.0-working-tree-20260906T232811Z-r01.md`, linhas 53 e 60.  
   *Fato observado:* Orquestradores Claude e Agy declararam válidas classificações contendo pares modelo/effort fora do catálogo autorizado do projeto: `gpt-5.6-terra` nos papéis Planner e Checker; e `gemini-3.1-pro` nos papéis Planner e Maker.

2. **Consumidor platform — Smoke v0.5.0 r1 Claude**  
   *Citação:* evidência da atualização v0.5.0 do consumidor platform, `_tl-orc/evidence/tl-orchestrator-v0.5.0-working-tree-20260907T200541Z-r01.md`.  
   *Fato observado:* Primeira resposta do Classificador continha `claude-opus-5` fora do catálogo e `price-flash` citado para `gemini-3.1-pro`. A correção única via `codex exec resume` rodou acidentalmente em `gpt-6-astra` (modelo fora do perfil fixo do Classificador), e o objeto resultante foi aceito pelo Orquestrador.

3. **Consumidor platform — Smoke v0.5.0 r3 Claude**  
   *Citação:* evidência da atualização v0.5.0 do consumidor platform, `_tl-orc/evidence/tl-orchestrator-v0.5.0-working-tree-20260907T200541Z-r01.md`.  
   *Fato observado:* O Orquestrador aceitou classificação que escolheu e despachou `codex/gpt-5.6-luna` como Maker (par não autorizado para Maker no catálogo) e que preencheu `story_id: "lynvia-mkauth-connector:T005"` quando a especificação do smoke exigia expressamente `story_id: null`.

4. **Consumidor platform — Smoke v0.5.0 r3 Codex**  
   *Citação:* evidência da atualização v0.5.0 do consumidor platform, `_tl-orc/evidence/tl-orchestrator-v0.5.0-working-tree-20260907T200541Z-r01.md`.  
   *Fato observado:* O Orquestrador compôs o briefing sem cartões de evidência do `MODEL_ROUTING.md`, fabricou identificadores de evidência genéricos (valor não informado) e posteriormente aceitou a classificação gerada declarando esses IDs como fornecidos e pertinentes.

5. **Repositório fonte — Task T005 fase implementation**  
   *Citações:* `_tl-orc/project/evidence/T005-classification.md:14` e `_tl-orc/project/evidence/T005-r01.md:11`.  
   *Fato observado:* Na rodada T005-r01, o terceiro candidato de Checker (`agy/gemini-3.1-pro-high`) citou `transport-flash`, cartão exclusivo da família Gemini 3.8 Flash e não pertinente ao Gemini 3.1 Pro. A correção única já havia sido consumida pela recuperação de JSON truncado. Pelo contrato, o Orquestrador deveria bloquear e relatar; em vez disso, aceitou o objeto e despachou o Maker com o candidato pin.

6. **Condição observada comum:** Em todas as 5 ocorrências catalogadas, as sessões do Orquestrador executaram com raciocínio configurado em `effort: medium`.

### Categoria 2: Hipóteses Causais (rotuladas)

- *Hipótese causal:* A aceitação indevida recorrente não resulta de uma fraqueza particular do modelo em nível `medium`, mas da **ausência de conferência objetiva independente**. Como a validação semântica foi integralmente delegada ao raciocínio em linguagem natural do modelo, que comparava o objeto gerado contra resumos e premissas soltas que ele próprio compilara no contexto da chamada, criou-se um mecanismo de "conformidade tautológica", no qual uma invenção consistente passa por conformidade formal.

### Categoria 3: Afirmações Não Verificadas (rotuladas)

- *Afirmação não verificada (eficácia de effort maior):* A hipótese de que elevar o raciocínio para `high` ou `max` eliminaria tais aceitações indevidas não foi verificada; sem um experimento pareado controlado (`medium` vs `high`/`max` com mesma semente e entradas idênticas), não se pode afirmar causalmente se o nível de esforço do LLM resolveria ou atenuaria essa falha estrutural.

---

## AC02: Proposta em Três Estágios e Origem Obrigatória das Entradas

Para eliminar a validação ilusória, o fluxo de validação é estruturado em três estágios explícitos e sequenciais:

```
+-----------------------------------------------------------------------------+
|                      FLUXO DE VALIDAÇÃO DA CLASSIFICAÇÃO                    |
+-----------------------------------------------------------------------------+
                                       |
                                       v
        +-------------------------------------------------------------+
        | ESTÁGIO 1: CONFERÊNCIA MECÂNICA (Determinística / Código)   |
        +-------------------------------------------------------------+
        | • Validação estrutural do schema JSON (v2 recursivo)        |
        | • Correspondência exata: story_id (inclusive null estrito)  |
        | • Correspondência de phase, context_revision, catalog_rev   |
        | • Papéis solicitados exatos (roles)                         |
        | • Ordem exata dos harnesses na cadeia configurada           |
        | • Pertencimento ao catálogo: (harness, modelo, effort) ∈ CAT|
        | • Pins atendidos no primeiro candidato                      |
        | • Procedência verificável de todos os evidence_ids          |
        | • Sustentação de cost_basis vinculada ao conteúdo do cartão |
        +-------------------------------------------------------------+
                                       |
                       [Problemas mecânicos?]
                       /                     \
                   Sim /                       \ Não (APROVADA)
                      v                         v
        +--------------------------+  +-------------------------------+
        | BLOQUEIO NO GATE         |  | ESTÁGIO 2: JULGAMENTO         |
        | Status: REJEITADA        |  | REGISTRADO (Humano/Doc)       |
        | Despacho: NENHUM         |  +-------------------------------+
        +--------------------------+  | • Referência arquivo:linha ao |
                                      |   registro documental         |
                                      | • Presença de âncora/trecho   |
                                      +-------------------------------+
                                                       |
                                            [Julgamento verificado?]
                                            /                      \
                           Não / Ausente   /                        \ Sim (CONFIRMADO)
                                          v                          v
                        +--------------------------+  +-------------------------------+
                        | DESPACHO NÃO LIBERADO    |  | ESTÁGIO 3: LIBERAÇÃO DE      |
                        | Status: ACEITA           |  | DESPACHO (Operacional)        |
                        | (aguardando julgamento)  |  +-------------------------------+
                        | Despacho: NENHUM         |  | • Resolução de elegibilidade  |
                        +--------------------------+  | • Verificação de disponibilidade|
                                                      |   (fallback sob preferred     |
                                                      |   exige prova de erro)        |
                                                      +-------------------------------+
                                                                       |
                                                                       v
                                                      +-------------------------------+
                                                      | DESPACHO EFETIVO              |
                                                      | (1º candidato elegível        |
                                                      | ou NENHUM se bloqueado)       |
                                                      +-------------------------------+
```

### Origem Obrigatória das Entradas e Procedência Verificável (R2)

A conferência proíbe listas compostas "na hora" ou procedência autodeclarada:

1. **Catálogo autorizado:** Extraído diretamente da tabela canônica em `_tl-orc/PROJECT.md#perfil-de-despacho`. Mapeia tuplas `(harness, modelo, effort) -> papéis autorizados`.
2. **IDs de evidência oficiais:** Extraídos estritamente das linhas de tabela (`| `id` |`), cartões (`### `id``) e linhas de transporte (`- `id`:`) de `docs/MODEL_ROUTING.md`. Marcadores documentais como `official-2026-09-05` são expressamente excluídos.
3. **IDs locais e registro efetivo:** Medições locais devem declarar arquivo de procedência com linha ou âncora (`arquivo#âncora` ou `arquivo:linha`). O arquivo deve existir **e conter o ID literal no seu texto**; caminhos existentes sem registro do ID disparam rejeição imediata.
4. **Categoria econômica vinculada ao conteúdo:**
   - `official_task_proxy`: sustentado exclusivamente se o cartão correspondente em `MODEL_ROUTING.md` contiver texto de custo por tarefa (regex por "custo" próximo de "tarefa" ou "por tarefa"). Cartões puramente metodológicos (como `sonnet-effort`) são rejeitados se declarados como proxy.
   - `local_observed`: sustentado exclusivamente por ID local devidamente registrado no arquivo de procedência.
   - `token_price_only`: sustentado exclusivamente por linha de tabela de preço (`price-*`).
   - Qualquer tentativa de declarar categorias arbitrárias em `expected` é rejeitada.

### Conferência Estrutural Recursiva contra o Schema (R3)

O protótipo implementa verificador recursivo contra `schemas/classification-result.schema.json` cobrindo integralmente:
- `required` em todos os níveis (ex.: candidato sem `reason` é rejeitado);
- `type` escalar e composto (`string`, `null`, `object`, `array`, `integer`);
- `enum` e `const` (`schema_version: 2`, `phase`, `confidence`, `cost_basis`, `effort`);
- `minItems` e `maxItems` (ex.: `facts: []` é rejeitado por violar `minItems: 1`);
- `uniqueItems` em listas de identificadores;
- `additionalProperties: false` recursivo (ex.: propriedades adicionais disparam rejeição imediata);
- `allOf` / `if` / `then` / `else` (ex.: `model == null` se e somente se `effort == null`; `cost_basis != unknown` exige `evidence_ids >= 1`).

---

## AC03: Regras Preservadas e Demonstração no Protótipo

A implementação mecânica respeita as regras normativas fundamentais estabelecidas nos perfis (`prompts/orchestrator-perfis.md`):

1. **Independência do Checker como filtro de resolução, não de validade do objeto:**
   - A dependência de família é um critério de seleção operacional para despacho, e não um defeito intrínseco do dimensionamento analítico feito pelo Classificador.
   - Um candidato de mesma família da autoria efetiva:
     - Sob `preferred`: é aceito no objeto e classificado como `elegível só com indisponibilidade comprovada (fallback)`.
     - Sob `required`: é aceito no objeto e classificado como `inelegível(required, mesma família)`.

2. **Condição estrita para fallback de mesma família sob `preferred` (R4):**
   - O despacho de fallback para candidato de mesma família sob `preferred` é **bloqueado com ponto de retomada** a menos que haja indisponibilidade comprovada de todos os candidatos de família distinta.
   - A entrada `availability` deve trazer o estado (`available | unavailable | disabled | unknown`). Para `unavailable`, exige-se prova literal do erro com indicação de arquivo de evidência existente no repositório contendo esse texto.
   - Sem comprovação ou sob estado `unknown`, o despacho de mesma família é bloqueado (`despacho: nenhum`), preservando a validade do objeto.
   - Sob `required`, mesma família é permanentemente inelegível (`despacho: nenhum`).

3. **Legitimidade de `cost_basis: unknown`:**
   - Declarar `unknown` com `evidence_ids: []` quando não há proxy de tarefa nem medição local é conduta legítima e recomendada. O validador aceita e preserva esse comportamento.

---

## AC04: Piloto Delimitado — Tabela de Casos, Estágios e Prova de Não-Despacho

O piloto foi executado sobre 17 casos: o caso real de T005 review sob restrição `required` (`_tl-orc/project/evidence/T005-classification.md:37`), 4 alterações deliberadas unifatoriais, 1 variante de `story_id` nulo, 1 controle de regras preservadas sob `preferred`, e 10 novos casos de controle rigorosamente desenhados para comprovar as correções de R2 a R5.

### Tabela Completa do Piloto: Estágio 1 → Estágio 2 → Estágio 3 → Status → Despacho

| Caso | Arquivo | Alteração / Entrada | Mecânica (E1) | Julgamento (E2) | Despacho (E3) | Status | Despacho Simulado | Motivos Principais |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **01 (Válido)** | `case_01_valid.json` | Nenhuma (JSON íntegro de T005 review sob required e julgamento confirmado) | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, evidências e julgamento confirmado |
| **02 (Catálogo)** | `case_02_invalid_catalog.json` | Candidato 2 com par fora do catálogo (`claude/claude-opus-5/medium`) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `checker ('claude', 'claude-opus-5', 'medium'): catálogo=False` |
| **03 (Story ID)** | `case_03_invalid_story_id.json` | `story_id: null` quando briefing exigia `"T005"` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `story_id: esperado 'T005', obtido None` |
| **03b (Story ID inv)** | `case_03b_invalid_story_id_null.json` | `story_id: "T005"` quando briefing exigia `null` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `story_id: esperado None, obtido 'T005'` |
| **04 (ID inexistente)** | `case_04_invalid_evidence_id.json` | Candidato 3 cita `"price-gemini-pro"` (inexistente) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ids_desconhecidos=['price-gemini-pro']` |
| **05 (Evidência incomp)** | `case_05_incompatible_evidence.json` | Candidato 2 `official_task_proxy` sustentado por `sonnet-effort` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `cost_basis=official_task_proxy sustentado=False` |
| **06 (Controle regras)** | `case_06_control_preserved_rules.json` | Candidato 3 Google sob `preferred` elegível como fallback; `unknown` com `[]` | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, evidências e julgamento confirmado |
| **07 (R2: ID local sem registro)** | `case_07_r2_unregistered_local_id.json` | ID local fabricado `local-fake` em `README.md` onde o ID não existe | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ID local 'local-fake' em 'local_ids' rejeitado: não registrado efetivamente no arquivo` |
| **08 (R2: Proxy sem custo)** | `case_08_r2_invalid_proxy_card.json` | `sonnet-effort` declarado como proxy em `expected` sem custo por tarefa | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ID 'sonnet-effort' em 'proxy_ids' rejeitado: não contém comprovação de custo por tarefa` |
| **09 (R2: Marcador oficial)** | `case_09_r2_official_marker_as_evidence.json` | Candidato 1 cita marcador de revisão documental `official-2026-09-05` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ids_desconhecidos=['official-2026-09-05']` |
| **10 (R3: Sem reason)** | `case_10_r3_missing_candidate_reason.json` | Candidato 1 sem a propriedade obrigatória `reason` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: $.roles.checker.candidates[0] faltando campo obrigatório 'reason'` |
| **11 (R3: Facts vazio)** | `case_11_r3_empty_facts.json` | Array `facts: []` violando cardinalidade mínima | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: $.facts deve ter no mínimo 1 itens, obtido 0 (minItems: 1)` |
| **12 (R3: Propriedade extra)** | `case_12_r3_extra_property.json` | Propriedade extra `"extra_property"` violando `additionalProperties: false` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: propriedade adicional não permitida 'extra_property' em $` |
| **13 (R4: Fallback sem prova)** | `case_13_r4_preferred_unproven_fallback.json` | Fallback sob `preferred` sem prova literal de indisponibilidade de infra | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `fallback de mesma família sob preferred bloqueado: candidato 'codex/gpt-6-astra' com status 'unknown'` |
| **14 (R4: Fallback com prova)** | `case_14_r4_preferred_proven_fallback.json` | Fallback sob `preferred` com indisponibilidade comprovada em arquivo sintético | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:agy/gemini-3.1-pro-high/high (fallback: same_family_fresh_session)` | Conforme catálogo, schema, evidências e julgamento confirmado |
| **15 (R4: Required mesma fam)** | `case_15_r4_required_same_family.json` | Todos os candidatos pertencem a famílias autoras sob `required` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `checker: nenhum candidato elegível sob required (todas as famílias são autoras)` |
| **16 (R5: Sem julgamento)** | `case_16_r5_valid_without_judgment.json` | Caso válido estruturalmente, mas sem entrada `judgment` em `expected` | **APROVADA** | **PENDENTE** | **NENHUM** | **ACEITA (aguardando julgamento)** | **nenhum** | `aceita mecanicamente; despacho não liberado (aguardando julgamento)` |

### Prova de Não-Despacho

Em todos os 14 casos que não obtiveram aprovação integral nos três estágios (rejeitados na mecânica, rejeitados no julgamento ou bloqueados no despacho), o despacho simulado resulta estritamente em **`nenhum`**, impedindo que qualquer despacho indevido seja registrado ou executado.

---

## AC05: Premissas, Alternativas Consideradas e Escopo Excluído

Em cumprimento a AC05 e R1, o detalhamento das premissas e alternativas é dividido em três categorias explícitas:

### Categoria 1: Fatos Observados (com fonte)

- Nos smokes documentados (`v0.4.0 r02`, `v0.5.0 r1`, `v0.5.0 r3` no consumidor `platform`, e `T005` no repositório fonte), todas as sessões do Orquestrador que aceitaram classificações inválidas executaram com `effort: medium`.
- Nos smokes registrados, a validação semântica foi executada diretamente pelo raciocínio em linguagem natural do modelo, sem uso de script executável ou validador determinístico.

### Categoria 2: Hipóteses Causais (rotuladas)

- *Hipótese da complacência cognitiva:* Modelos LLM atuando como avaliadores de saídas complexas tendem a assumir conformidade quando restrições textuais não são checadas por código determinístico.
- *Hipótese da conformidade tautológica:* Quando o modelo compara uma classificação com resumos e premissas que ele próprio compilou no contexto do prompt, distorções conceituais ou identificadores fabricados tendem a ser confirmados como válidos.

### Categoria 3: Afirmações Não Verificadas e Comparação de Alternativas

| Alternativa | Prós | Contras | Conclusão |
| :--- | :--- | :--- | :--- |
| **1. Checklist preenchido pela IA** (instruir o Orquestrador via prompt a preencher tabela de checagem antes de validar) | Dispensa código ou scripts; execução puramente em texto. | Não testado nesta Task; nos smokes registrados não havia checklist formal, então sua eficácia é desconhecida. Permanece suscetível à conformidade tautológica. | **Descartada como garantia única.** Pode servir de auxílio mnemônico, mas não oferece comprovação objetiva. |
| **2. Validador mecânico local** (script local pré-despacho, prototipado em T009) | Propriedades discretas verificáveis por código sem custo de tokens; bloqueio determinístico no gate; tempo de execução não mensurado formalmente nesta Task. | Exige manter script utilitário local de inspeção do catálogo e das evidências. | **Recomendada para decisão arquitetural posterior.** |
| **3. Effort maior com comparação controlada** (elevar reasoning effort para `high` ou `max` em todas as validações) | Poderia potencialmente reduzir descuidos atencionais simples do LLM. | Aumento de custo de tokens e latência não quantificados nesta Task; não oferece garantia contra aceitação indevida; eficácia não comprovada por teste controlado. | **Descartada como solução isolada.** Pode ser estudada para o julgamento qualitativo, mas é inadequada para regras discretas. |

### Alcance e Limitações da Evidência do Piloto

- **O que o piloto demonstrou:**
  - Rejeitou deterministicamente todas as mutações inválidas (pares fora do catálogo, divergências de `story_id`, IDs inexistentes, marcadores documentais citados como evidência, ausência de campos obrigatórios do schema, fatos vazios, propriedades extras, procedência local sem registro efetivo e proxies sem custo por tarefa).
  - Bloqueou despachos sob `preferred` quando ausente a prova literal de indisponibilidade de infraestrutura dos candidatos de família distinta.
  - Bloqueou a liberação de despacho para casos sem julgamento documental registrado.
  - Aceitou os casos válidos com liberação do despacho correto (inclusive fallback de mesma família com erro comprovado).
- **O que o piloto NÃO demonstrou:**
  - Desempenho em ambiente de produção com execução concorrente de múltiplos agentes em tarefas de ponta a ponta.
  - Eficácia de `effort: high` ou `max` sobre a validação em linguagem natural (não testada de forma pareada).

### O que mudaria a conclusão?

- Se testes futuros comprovarem que o uso de *Constrained Decoding* / *Structured Outputs* com esquemas dinâmicos injetados no nível de transporte garante conformidade absoluta com o catálogo vigente em runtime.
- Se um teste controlado A/B de larga escala demonstrasse empiricamente que `effort: high` atinge 0% de aceitação indevida com latência aceitável.

### Escopo Explicitamente Excluído

Permanecem fora do escopo desta Task (decisão congelada na spec de T009):
- Distribuição do validador como script empacotado no produto ou na release do `tl-orchestrator`;
- Escolha da linguagem definitiva de implementação do validador;
- Introdução de novas dependências externas ou requisitos de instalação nos consumidores.

---

## AC06: Portões de Validação e Saídas Literais

### 1. Validador do Repositório (`scripts/validate_repository.py`)

```text
$ python3 scripts/validate_repository.py
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
[Exit code: 0]
```

### 2. Auto-Teste da Conferência Mecânica (`_tl-orc/project/evidence/T009-mechanical-check.py --self-test`)

Em cumprimento a R6, o comando `--self-test` executa estritamente em modo de leitura (não escreve nem modifica nenhum arquivo no disco), computando a tabela inteira em memória e comparando com `T009-cases/pilot_summary.json` versionado:

```text
$ python3 _tl-orc/project/evidence/T009-mechanical-check.py --self-test
=== T009 MECHANICAL CHECK: INÍCIO DO SELF-TEST (REWORK ROUND 2) ===

[Teste de Robustez A] ID local com caminho de procedência inexistente:
SUCESSO (recusa esperada): Caminho de procedência '_tl-orc/project/evidence/arquivo-fantasma.md' do ID 'local-fake' em 'local_ids' não existe.

[Teste de Robustez B] Lista de IDs passada 'na hora' sem origem:
SUCESSO (recusa esperada): ID 'price-astra' em 'local_ids' rejeitado: lista de IDs passada 'na hora' sem origem declarada (proibido; toda entrada deve declarar arquivo + âncora ou linha).

[Teste de Robustez C] ID local em caminho existente mas sem registro efetivo:
SUCESSO (recusa esperada): ID local 'local-fake' em 'local_ids' rejeitado: não registrado efetivamente no arquivo 'README.md' (ID literal ausente no conteúdo).

[Teste de Robustez D] Declaração indevida de sonnet-effort como proxy:
SUCESSO (recusa esperada): ID 'sonnet-effort' em 'proxy_ids' rejeitado: cartão em docs/MODEL_ROUTING.md não contém comprovação de custo por tarefa (incompatível com official_task_proxy).

============================================================================================================================================
Caso                                 | Mecânica  | Julgamento  | Despacho  | Status     | Despacho Simulado
============================================================================================================================================
case_01_valid                        | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_02_invalid_catalog              | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_03_invalid_story_id             | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_03b_invalid_story_id_null       | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_04_invalid_evidence_id          | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_05_incompatible_evidence        | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_06_control_preserved_rules      | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_07_r2_unregistered_local_id     | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_08_r2_invalid_proxy_card        | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_09_r2_official_marker_as_evidence | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_10_r3_missing_candidate_reason  | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_11_r3_empty_facts               | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_12_r3_extra_property            | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_13_r4_preferred_unproven_fallback | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_14_r4_preferred_proven_fallback | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:agy/gemini-3.1-pro-high/...
case_15_r4_required_same_family      | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_16_r5_valid_without_judgment    | APROVADA  | PENDENTE (a | NENHUM    | ACEITA (aguardando julgamento) | nenhum
============================================================================================================================================

[Modo estrito sem escrita]: Resumo em memória coincide 100% com 'pilot_summary.json' (R6 cumprido).

=== AUTO-TESTE DO PILOTO: TODOS OS 17 CASOS PASSARAM COM AS REJEIÇÕES, BLOQUEIOS E APROVAÇÕES ESPERADAS (EXIT 0) ===
[Exit code: 0]
```

---

## Tabela de Cobertura (Coverage AC01–AC06)

| Critério de Aceitação | Seção do Documento | Linhas Exatas | Status |
| :--- | :--- | :--- | :--- |
| **AC01** (Diagnóstico, ocorrências citadas por caminho correto, separação explícita de fatos, hipóteses e não verificadas) | `## AC01: Diagnóstico com Ocorrências Registradas e Citações por Caminho` | L18–L57 | **Coberto** |
| **AC02** (Proposta em 3 estágios, procedência verificável, registro efetivo e schema recursivo) | `## AC02: Proposta em Três Estágios e Origem Obrigatória das Entradas` | L59–L142 | **Coberto** |
| **AC03** (Regras preservadas: independência como resolução, fallback sob preferred com prova, cost_basis unknown) | `## AC03: Regras Preservadas e Demonstração no Protótipo` | L144–L163 | **Coberto** |
| **AC04** (Piloto delimitado com 17 casos, três colunas de estágio, motivos tabelados e prova de não-despacho) | `## AC04: Piloto Delimitado — Tabela de Casos, Estágios e Prova de Não-Despacho` | L165–L195 | **Coberto** |
| **AC05** (Premissas, 3 alternativas sem quantificações não mensuradas, o que mudaria a conclusão, escopo excluído) | `## AC05: Premissas, Alternativas Consideradas e Escopo Excluído` | L197–L242 | **Coberto** |
| **AC06** (Portões verdes, saídas literais com exit codes, self-test estritamente sem escrita) | `## AC06: Portões de Validação e Saídas Literais` | L244–L303 | **Coberto** |
