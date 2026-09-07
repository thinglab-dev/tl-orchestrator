# Análise: Validação Semântica da Classificação pelo Orquestrador (T009)

unit: native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md  
base_revision: 0de10d6  
maker: agy gemini-3.8-flash-high (tier heavy)  
date_utc: 2026-09-07T22:45:00Z  
kind: analysis  
rework_round: 5 (+ correção própria do Orquestrador após c01)
---

## Sumário Executivo

Esta análise investiga a causa da aceitação recorrente de classificações inválidas pelo Orquestrador em múltiplos harnesses e releases, formaliza a proposta de separação da validação em três estágios explícitos (Conferência Mecânica, Julgamento Registrado Vinculado e Liberação de Despacho) com exigência estrita de procedência das entradas e verificação contra o schema, e demonstra, por meio de protótipo executável (`T009-mechanical-check.py`) aplicado sobre um piloto de 38 casos (o caso válido real de T005 review sob restrição `required`, 4 alterações deliberadas, 1 variante de `story_id` nulo, 1 controle de regras preservadas sob `preferred`, 10 controles de rework 2, 8 controles de rework 3, 7 controles de rework 4 e 6 novos controles de rework 5 cobrindo R1 e R2), a rejeição determinística de todas as alterações inválidas e o bloqueio de despachos indevidos com `despacho: nenhum` em 33 dos 38 casos testados.

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
        | • Procedência de evidências oficiais em docs/MODEL_ROUTING  |
        | • Medição local restrita a linhas de tabela em evidências   |
        | • Pertinência mecânica de evidências por modelo (R3-a)      |
        | • Sustentação de cost_basis vinculada ao conteúdo do cartão |
        +-------------------------------------------------------------+
                                       |
                       [Problemas mecânicos?]
                       /                     \
                   Sim /                       \ Não (APROVADA)
                      v                         v
        +--------------------------+  +-------------------------------+
        | BLOQUEIO NO GATE         |  | ESTÁGIO 2: JULGAMENTO         |
        | Status: REJEITADA        |  | REGISTRADO VINCULADO (E2)     |
        | Despacho: NENHUM         |  +-------------------------------+
        |                          |  | • Localização exata           |
        |                          |    (âncora exata ou linha)       |
        |                          |  | • judgment_for == sha256(doc) |
        |                          |  | • judged_inputs == sha256(in) |
        |                          |  | • judgment_verdict: aprovado  |
        +--------------------------+  +-------------------------------+
                                                       |
                                            [Julgamento verificado?]
                                            /                      \
                           Não / Pendente  /                        \ Sim (CONFIRMADO)
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

### Origem Obrigatória das Entradas e Procedência Verificável (R1 a R5)

A conferência proíbe listas compostas "na hora" ou procedência autodeclarada:

1. **Catálogo autorizado:** Extraído diretamente da tabela canônica em `_tl-orc/PROJECT.md#perfil-de-despacho`. Mapeia tuplas `(harness, modelo, effort) -> papéis autorizados`.
2. **IDs de evidência oficiais:** Extraídos estritamente das linhas de tabela (`| `id` |`), cartões (`### `id``) e linhas de transporte (`- `id`:`) de `docs/MODEL_ROUTING.md`. Marcadores documentais como `official-2026-09-05` são expressamente excluídos.
3. **Procedência estruturada de medição local (R1):** Um ID local só é medição registrada se for **linha de tabela estruturada** (`| <id> | ... |`) em arquivo de evidência sob `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`, excluindo expressamente `T009-cases/`, `T009-analysis.md` e o próprio protótipo `T009-mechanical-check.py`. O cabeçalho da tabela deve conter `run_id` (Agent runs) ou `measurement_id`/`id`. Menções em prosa corrida, JSONs de teste de casos ou descrições narrativas de controle são sumariamente rejeitadas.
4. **Resolução exata de âncoras Markdown (R2):** A resolução de âncoras em arquivos documentais é estrita por **igualdade exata com o slug gerado para títulos Markdown** (`github_slug`, incluindo sufixo `-1`, `-2` para cabeçalhos homônimos). Correspondência por prefixo (`startswith`) é expressamente proibida.
5. **Pertinência mecânica de evidências por modelo (R3-a):** O protótipo deriva diretamente de `docs/MODEL_ROUTING.md` o mapeamento `id -> modelos pertinentes` via detecção de termos de modelo (Astra, Terra, Luna, Sol, Sonnet, Opus, Flash, "3.1 Pro") articulados com um mapa explícito `model-id -> keyword` em código. Se um candidato citar evidência comprovadamente estranha ao modelo sob análise (por exemplo, modelo Astra citando `flash-deepswe`), o objeto é rejeitado no Estágio 1 da mecânica (`evidence_id não pertinente ao modelo`).
6. **Julgamento documental vinculado criptograficamente (R3-b):** No Estágio 2, o registro de julgamento deve residir em arquivo documental acessível por âncora exata ou `:linha` e conter metadados criptográficos de amarração:
   - `judgment_for: <sha256(canonical(doc))>` (hash SHA-256 da forma canônica do JSON de classificação avaliado);
   - `judged_inputs: <sha256(canonical(expected))> ` (hash SHA-256 da forma canônica das entradas de referência);
   - `judgment_verdict: aprovado | rejeitado`.
   - Se os hashes coincidirem e o veredito for `aprovado`, o julgamento é **CONFIRMADO**. Se os hashes divergirem, o julgamento é classificado como **PENDENTE** (`"julgamento não se aplica a este objeto: pendente"`). Se o veredito for `rejeitado`, o despacho é bloqueado (`"registro de julgamento com veredito 'rejeitado': não liberado"`). Se a localização declarada não existir, o status permanece **PENDENTE**.
7. **Derivação verificável de proxies econômicos:** Cartões que sustentam `cost_basis: official_task_proxy` derivam estritamente de `docs/MODEL_ROUTING.md` mediante co-ocorrência verificável de "custo" e "tarefa" na mesma frase sem restrições explícitas. Apenas dois cartões qualificam formalmente: `astra-coding` e `flash-deepswe`. Cartões como `astra-domain` (minutos por tarefa, sem custo) e `sonnet-effort` (curvas e metodologia) não qualificam e são rejeitados se declarados como proxy.
8. **Prova de indisponibilidade e status do candidato:** A prova de indisponibilidade de infraestrutura deve ser localizada por `arquivo:linha`, apontando para registro em tabela de `Agent runs` sob diretório de evidência, pertinente ao candidato (mesmo harness e modelo), com texto de erro em categoria comprovante (quota, 401, 429, authentication, harness ausente); timeout isolado, saída vazia ou processo vivo não comprovam indisponibilidade. Candidatos de mesma família na cadeia de fallback devem ter status verificado em `availability` (marcado `disabled` ou `unknown` bloqueia o fallback).
9. **Resolução de família de modelos e validade vs resolução:** Candidato com modelo não presente no mapeamento de famílias sob `required` é admitido na validação estrutural do schema (E1), mas bloqueia o despacho (E3) com ponto de retomada (`"família não resolvida"`). A conformidade mecânica (E1) avalia a correção intrínseca do dimensionamento emitido pelo Classificador; a ausência de candidato independente sob `required` não invalida mecanicamente o objeto (E1 é APROVADA e E2 é CONFIRMADO), mas bloqueia a resolução operacional no estágio 3 (`despacho: nenhum`), gerando status `BLOQUEADO`.
10. **Origem obrigatória para todas as listas de referência (R1 - Rework 5):** Todas as listas de referência em `expected` (`roles`, `chains`, `pins`, `authors`, `families`, `policy`) devem vir estritamente envelopadas em `{"value": ..., "source": "arquivo#âncora|arquivo:linha"}`. Listas soltas passadas sem envelope são sumariamente rejeitadas por `unwrap_expected`. A resolução da origem é estrita: o arquivo de procedência deve existir fisicamente no repositório; âncoras (`#`) devem coincidir por igualdade exata com o `github_slug` do título Markdown correspondente; referências numéricas (`:linha`) devem apontar para linha existente. Adicionalmente, `roles` e `chains` devem originar-se de `_tl-orc/PROJECT.md` com conferência determinística de que a cadeia declarada coincide exatamente em conteúdo e ordem com a tabela de cadeias autorizadas em `_tl-orc/PROJECT.md#cadeias-preferência-operacional-fallbacks-autorizados-preservados`; `pins` deve originar-se de `PROJECT.md` (piloto) ou do arquivo da Task; e `authors` deve apontar para linha de tabela `Agent runs` em arquivo de evidência sob `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`.
11. **Tratamento de lacuna permitida `model: null` e `effort: null` (R2 - Rework 5):** `model: null` e `effort: null` com `reason` não vazio é formalmente admitido como declaração legítima de lacuna de harness (inexistência de opção técnica viável no harness para a tarefa). O objeto resultante é válido e aprovado no Estágio 1 da conferência mecânica (`APROVADA`), marcado na tabela de candidatos como `"lacuna: sem opção adequada no harness"` e pulado transparentemente durante a resolução de despacho no Estágio 3. Nulidade inconsistente (`model: null` com `effort` preenchido ou vice-versa) é sumariamente rejeitada pelo schema e pela conferência mecânica. Quando o primeiro candidato da cadeia é declarado como `model: null` e `effort: null` havendo pares autorizados no catálogo para o harness e papel, o candidato é marcado como `"lacuna suspeita de normalizar escolha inválida"`: o objeto permanece válido mecanicamente (APROVADA no E1), mas a resolução operacional no Estágio 3 é bloqueada com ponto de retomada (`"lacuna suspeita de normalizar escolha inválida no candidato 1 exige julgamento prévio"`).

### Conferência Estrutural Recursiva contra o Schema

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
   - A dependência de família é um critério de seleção operacional para despacho, e não um defeito estrutural do dimensionamento analítico feito pelo Classificador.
   - Um candidato de mesma família da autoria efetiva:
     - Sob `preferred`: é aceito no objeto e classificado como `elegível só com indisponibilidade comprovada (fallback)`.
     - Sob `required`: é aceito no objeto e classificado como `inelegível(required, mesma família)`. Se não houver candidato independente, o objeto aprova no E1, confirma no E2 e bloqueia no E3 com ponto de retomada.

2. **Preservação do Julgamento Qualitativo Humano:**
   - O validador mecânico não substitui a prerrogativa humana sobre a escolha qualitativa do modelo ou o dimensionamento de esforço intelectual.
   - O papel do código no Estágio 2 é verificar a **autenticidade documental e a integridade da amarração criptográfica** (`judgment_for`, `judged_inputs` e `judgment_verdict`). A apreciação do mérito substantivo da tarefa reside e permanece no julgamento registrado pelo avaliador humano/especialista.

3. **Condição estrita para fallback de mesma família sob `preferred`:**
   - O despacho de fallback para candidato de mesma família sob `preferred` é **bloqueado com ponto de retomada** a menos que haja indisponibilidade comprovada de todos os candidatos de família distinta.
   - A entrada `availability` deve trazer o estado (`available | unavailable | disabled | unknown`). Para `unavailable`, exige-se prova literal por `arquivo:linha` em linha de `Agent runs` sob evidências com categoria comprovante (401, 429, quota, authentication, harness ausente). Timeout, saída vazia ou processo vivo disparam bloqueio imediato.
   - O candidato de mesma família a ser despachado não pode estar marcado `disabled` ou `unknown`.

4. **Resolução de família de modelos:**
   - Modelos sem mapeamento de família sob `required` não impedem a aprovação estrutural mecânica, mas bloqueiam a liberação de despacho (`despacho: nenhum`) com ponto de retomada.

5. **Legitimidade de `cost_basis: unknown`:**
   - Declarar `unknown` com `evidence_ids: []` quando não há proxy de tarefa nem medição local é conduta legítima e recomendada. O validador aceita e preserva esse comportamento.

6. **Preservação do tratamento de lacunas de harness vs lacunas suspeitas (R2):**
   - Declarar lacuna (`model: null` e `effort: null`) quando fundamentada em justificativa explícita de ausência de modelo viável no harness é prática permitida e preservada. O candidato é reconhecido como lacuna legítima, mantendo o objeto aprovado na mecânica e sendo pulado na busca de candidatos operacionais.
   - A declaração de lacuna no primeiro candidato havendo opções autorizadas no catálogo para o harness não é descartada silenciosamente: o objeto é aprovado estruturalmente, mas a resolução operacional é suspensa com bloqueio no Estágio 3 para julgamento substantivo pelo Orquestrador, prevenindo a normalização velada de escolhas inválidas.

7. **Universalidade do envelope de procedência para listas de referência (R1):**
   - Nenhuma premissa ou lista de referência do orquestrador (`roles`, `chains`, `pins`, `authors`, `families`, `policy`) pode ser injetada sem procedência documental verificável.
   - A obrigatoriedade do envelope `{"value": ..., "source": ...}` torna rastreável a localização declarada de cada entrada (não o seu conteúdo; ver Limitações Residuais) entre as definições de projeto em `_tl-orc/PROJECT.md`, tarefas em `_tl-orc/project/tasks/`, referências em `docs/MODEL_ROUTING.md` e execuções em `Agent runs`.

---

## AC04: Piloto Delimitado — Tabela de Casos, Estágios e Prova de Não-Despacho

O piloto foi executado sobre 38 casos: o caso real de T005 review sob restrição `required` (`_tl-orc/project/evidence/T005-classification.md:37`), 4 alterações deliberadas unifatoriais, 1 variante de `story_id` nulo, 1 controle de regras preservadas sob `preferred`, 10 controles de rework 2, 8 controles de rework 3, 7 controles de rework 4 e 6 novos controles de rework 5 cobrindo R1 e R2.

### Tabela Completa do Piloto: Estágio 1 → Estágio 2 → Estágio 3 → Status → Despacho

| Caso | Arquivo | Alteração / Entrada | Mecânica (E1) | Julgamento (E2) | Despacho (E3) | Status | Despacho Simulado | Motivos Principais |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **01 (Válido)** | `case_01_valid.json` | Nenhuma (JSON íntegro de T005 review sob required e julgamento vinculado confirmado) | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, evidências e julgamento confirmado por sha256 |
| **02 (Catálogo)** | `case_02_invalid_catalog.json` | Candidato 2 com par fora do catálogo (`claude/claude-opus-5/medium`) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `checker ('claude', 'claude-opus-5', 'medium'): catálogo=False` |
| **03 (Story ID)** | `case_03_invalid_story_id.json` | `story_id: null` quando briefing exigia `"T005"` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `story_id: esperado 'T005', obtido None` |
| **03b (Story ID inv)** | `case_03b_invalid_story_id_null.json` | `story_id: "T005"` quando briefing exigia `null` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `story_id: esperado None, obtido 'T005'` |
| **04 (ID inexistente)** | `case_04_invalid_evidence_id.json` | Candidato 3 cita `"price-gemini-pro"` (inexistente) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ids_desconhecidos=['price-gemini-pro']` |
| **05 (Evidência incomp)** | `case_05_incompatible_evidence.json` | Candidato 2 `official_task_proxy` sustentado por `sonnet-effort` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `cost_basis=official_task_proxy sustentado=False` |
| **06 (Controle regras)** | `case_06_control_preserved_rules.json` | Candidato 3 Google sob `preferred` elegível como fallback; `unknown` com `[]` | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, evidências e julgamento vinculado confirmado |
| **07 (R2: ID local sem registro)** | `case_07_r2_unregistered_local_id.json` | ID local fabricado `local-fake` em `README.md` (fora de evidence) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Registro de medição local 'local-fake' em 'README.md' rejeitado: só é aceito em arquivo de evidência` |
| **08 (R2: Proxy sem custo)** | `case_08_r2_invalid_proxy_card.json` | `sonnet-effort` declarado como proxy em `expected` sem custo por tarefa | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ID 'sonnet-effort' em 'proxy_ids' rejeitado: não contém comprovação de custo por tarefa` |
| **09 (R2: Marcador oficial)** | `case_09_r2_official_marker_as_evidence.json` | Candidato 1 cita marcador de revisão documental `official-2026-09-05` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ids_desconhecidos=['official-2026-09-05']` |
| **10 (R3: Sem reason)** | `case_10_r3_missing_candidate_reason.json` | Candidato 1 sem a propriedade obrigatória `reason` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: $.roles.checker.candidates[0] faltando campo obrigatório 'reason'` |
| **11 (R3: Facts vazio)** | `case_11_r3_empty_facts.json` | Array `facts: []` violando cardinalidade mínima | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: $.facts deve ter no mínimo 1 itens, obtido 0 (minItems: 1)` |
| **12 (R3: Propriedade extra)** | `case_12_r3_extra_property.json` | Propriedade extra `"extra_property"` violando `additionalProperties: false` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: propriedade adicional não permitida 'extra_property' em $` |
| **13 (R4: Fallback sem prova)** | `case_13_r4_preferred_unproven_fallback.json` | Fallback sob `preferred` sem prova literal de indisponibilidade de infra | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `fallback de mesma família sob preferred bloqueado: candidato 'codex/gpt-6-astra' com status 'unknown'` |
| **14 (R4: Fallback com prova)** | `case_14_r4_preferred_proven_fallback.json` | Fallback sob `preferred` com indisponibilidade comprovada em tabela Agent runs (401/429) | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:agy/gemini-3.1-pro-high/high (fallback: same_family_fresh_session)` | Conforme catálogo, schema, evidências e julgamento vinculado confirmado |
| **15 (R5: Validade vs Resolução)** | `case_15_r4_required_same_family.json` | Todos os candidatos pertencem a famílias autoras sob `required` (R5: validade ≠ resolução) | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `bloqueado com ponto de retomada: nenhum candidato elegível sob required` |
| **16 (R5: Sem julgamento)** | `case_16_r5_valid_without_judgment.json` | Caso válido estruturalmente, mas sem entrada `judgment` em `expected` | **APROVADA** | **PENDENTE** | **NENHUM** | **ACEITA (aguardando julgamento)** | **nenhum** | `aceita mecanicamente; despacho não liberado (aguardando julgamento)` |
| **17 (R1: Sonda local routing)** | `case_17_r1_local_routing_anchor.json` | Sonda R1: registro local apontando para `docs/MODEL_ROUTING.md#astra-coding--terminal-engenharia-e-migrações` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Registro de medição local 'sonnet-effort' em 'docs/MODEL_ROUTING.md' rejeitado: só é aceito em arquivo de evidência` |
| **18 (R1: Sonda local protótipo)** | `case_18_r1_local_prototype_line.json` | Sonda R1: registro local apontando para `T009-mechanical-check.py:999999` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Registro de medição local 'local-fake' em 'T009-mechanical-check.py' rejeitado: só é aceito em arquivo de evidência` |
| **19 (R1: Controle local positivo)** | `case_19_r1_local_valid_reference.json` | Controle R1 positivo: `T005-r01-checker-1` registrado na tabela Agent runs em `T005-r01.md:16` | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, linha de tabela estruturada em evidências e julgamento vinculado |
| **20 (R2: Sonda astra-domain)** | `case_20_r2_astra_domain_proxy.json` | Sonda R2: cartão `astra-domain` (minutos por tarefa, sem custo) como único proxy | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `ID 'astra-domain' em 'proxy_ids' rejeitado: cartão em docs/MODEL_ROUTING.md não contém comprovação de custo por tarefa` |
| **21 (R3: Sonda texto README)** | `case_21_r3_unproven_text_readme.json` | Sonda R3: texto sem erro em `README.md` como suposta prova de indisponibilidade | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `fallback sob preferred bloqueado: arquivo de prova 'README.md' rejeitado (não é registro de Agent runs)` |
| **22 (R3: Sonda timeout isolado)** | `case_22_r3_timeout_as_proof.json` | Sonda R3: timeout isolado fornecido como suposta prova de indisponibilidade | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `fallback sob preferred bloqueado: timeout isolado, saída vazia ou processo vivo não comprovam indisponibilidade` |
| **23 (R3: Sonda mesma fam disabled)** | `case_23_r3_same_family_disabled.json` | Sonda R3: candidato de mesma família (Agy) marcado `disabled` sob fallback | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `fallback de mesma família sob preferred não liberado (candidato 'agy/gemini-3.1-pro-high' marcado disabled)` |
| **24 (R4: Sonda família não resolvida)** | `case_24_r4_unresolved_family.json` | Sonda R4: modelo `gpt-6-astra` removido do mapa de famílias sob `required` | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `bloqueado com ponto de retomada: família não resolvida para modelo(s) ['gpt-6-astra']` |
| **25 (R1: Sonda local em JSON de caso)** | `case_25_r1_local_json_case.json` | Sonda R1 Checker: medição local apontando para `expected_r2_unregistered_local_id.json:55` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Registro em 'expected_r2_unregistered_local_id.json' rejeitado: só é aceito em arquivo de evidência estruturada (excluindo T009-cases/)` |
| **26 (R1: Sonda local em análise)** | `case_26_r1_local_analysis.json` | Sonda R1 Checker: medição local apontando para `T009-analysis.md:181` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Registro em 'T009-analysis.md' rejeitado: T009-analysis.md é documento de análise e não constitui registro estruturado de medição` |
| **27 (R2: Sonda âncora prefixo)** | `case_27_r2_anchor_prefix.json` | Sonda R2 Checker: âncora declarada por prefixo `#conferência-mecânica-pelo` em `T009-classification.md` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `Âncora '#conferência-mecânica-pelo' não encontrada como título Markdown exato em 'T009-classification.md'` |
| **28 (R3-a: Evidência não pertinente)** | `case_28_r3_unrelated_model_evidence.json` | Sonda R3-a Checker: candidato Astra com evidence_id `flash-deepswe` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `evidence_id 'flash-deepswe' não pertinente ao modelo 'gpt-6-astra' (modelos pertinentes: ['Flash'], modelo: 'Astra')` |
| **29 (R3-b: Julgamento objeto alterado)** | `case_29_r3_altered_object_judgment.json` | Sonda R3-b Checker: objeto alterado fornecido com registro de julgamento do Caso 01 | **APROVADA** | **PENDENTE** | **NENHUM** | **ACEITA (aguardando julgamento)** | **nenhum** | `julgamento não se aplica a este objeto: pendente (divergência de hash SHA-256)` |
| **30 (R3-b: Julgamento veredito rejeitado)** | `case_30_r3_rejected_judgment.json` | Sonda R3-b Checker: registro de julgamento vinculado com `judgment_verdict: rejeitado` | **APROVADA** | **REJEITADO** | **NENHUM** | **REJEITADA** | **nenhum** | `registro de julgamento com veredito 'rejeitado': não liberado` |
| **31 (R3-b: Julgamento linha inexistente)** | `case_31_r3_missing_judgment_location.json` | Sonda R3-b Checker: registro de julgamento apontando para linha inexistente `T005-classification.md:999999` | **APROVADA** | **PENDENTE** | **NENHUM** | **ACEITA (aguardando julgamento)** | **nenhum** | `linha 999999 inexistente em 'T005-classification.md': localização inexistente` |
| **32 (R1: Roles lista solta)** | `case_32_r1_bare_list_roles.json` | Sonda R1 Checker: `roles` fornecida como lista solta sem envelope de procedência | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `roles fornecida como lista solta sem envelope (proibido; toda lista de referência deve vir em envelope {'value': ..., 'source': ...})` |
| **33 (R1: Fonte inexistente)** | `case_33_r1_nonexistent_source.json` | Sonda R1 Checker: `roles` com procedência apontando para `arquivo-inexistente.md#inventado` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `arquivo de procedência 'arquivo-inexistente.md' de 'roles' não existe` |
| **34 (R1: Cadeia divergente)** | `case_34_r1_divergent_chain.json` | Sonda R1 Checker: cadeia declarada para checker (`[agy, codex, claude]`) diverge de `PROJECT.md` | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `cadeia declarada para 'checker' (['agy', 'codex', 'claude']) diverge da tabela de PROJECT.md (['codex', 'claude', 'agy'])` |
| **35 (R2: Lacuna legítima)** | `case_35_r2_null_candidate_lacuna.json` | Controle R2 positivo: agy como 3º candidato com `model:null, effort:null` e `reason`; despacha pin | **APROVADA** | **CONFIRMADO** | **LIBERADO** | **ACEITA** | `checker:codex/gpt-6-astra/high` | Conforme catálogo, schema, evidências, lacuna de 3º candidato pulada e julgamento vinculado confirmado |
| **36 (R2: Nulidade inconsistente)** | `case_36_r2_inconsistent_null.json` | Sonda R2 Checker: candidato com `model: null` e `effort: 'high'` (nulidade inconsistente) | **REJEITADA** | N/A | NENHUM | **REJEITADA** | **nenhum** | `schema: $.roles.checker.candidates[2].effort esperado tipo null, obtido str; nulidade inconsistente` |
| **37 (R2: Lacuna suspeita 1º cand)** | `case_37_r2_suspicious_first_cand_lacuna.json` | Sonda R2 Checker: 1º candidato com `model:null/effort:null` havendo par no catálogo | **APROVADA** | **CONFIRMADO** | **BLOQUEADO** | **BLOQUEADO** | **nenhum** | `bloqueado com ponto de retomada: lacuna suspeita de normalizar escolha inválida no candidato 1 (checker: codex) exige julgamento prévio` |

### Prova de Não-Despacho

Em todos os 33 casos que não obtiveram aprovação integral e simultânea nos três estágios (rejeitados na mecânica, rejeitados no julgamento vinculado, com julgamento pendente ou bloqueados na resolução operacional de despacho), o despacho simulado resulta estritamente em **`nenhum`**, impedindo que qualquer despacho indevido seja registrado ou executado. Apenas os 5 casos conformes em todos os requisitos (`case_01`, `case_06`, `case_14`, `case_19` e `case_35`) liberam despacho simulado válido.

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
  - Rejeitou deterministicamente todas as mutações inválidas: pares fora do catálogo, divergências de `story_id` (inclusive null estrito), IDs inexistentes, marcadores documentais citados como evidência, ausência de campos obrigatórios do schema, fatos vazios, propriedades extras, medições locais fora do diretório de evidência, medições locais apontando para arquivos de casos ou de análise, âncoras Markdown referenciadas por prefixo incompleto, e evidências citadas não pertinentes à família do modelo avaliado (ex.: Astra com `flash-deepswe`).
  - Bloqueou despachos sob `preferred` quando ausente a prova literal de indisponibilidade de infraestrutura dos candidatos de família distinta, quando a prova indicada não está sob diretório de evidência em `Agent runs` (ex.: texto solto em README), quando a prova consiste em timeout isolado/saída vazia/processo vivo, ou quando o candidato de mesma família a despachar está marcado `disabled`.
  - Bloqueou despachos sob `required` com ponto de retomada quando a família do modelo não puder ser resolvida no catálogo.
  - Distinguiu validade mecânica de resolução de despacho: objeto sem candidato independente sob `required` é APROVADO na mecânica e BLOQUEADO no despacho (`despacho: nenhum`).
  - Bloqueou a liberação de despacho para casos sem julgamento documental registrado, com hash divergente do objeto avaliado, com veredito explicitamente `rejeitado` ou com localização documental inexistente.
  - Aceitou os casos válidos com liberação do despacho correto (inclusive fallback de mesma família com erro 401/429 comprovado e medição local legítima em linha de tabela de `Agent runs` em `T005-r01.md:16`).

### Limitações Residuais do Protótipo

**Limitação consolidada após a fase consultiva (rework 5 → r05 → consulta c01; parágrafo do Orquestrador, autoria Anthropic, 20260907T225831Z):** a conferência de procedência deste protótipo não é geral por tipo de informação e conteúdo. O que existe de específico: resolução da localização (arquivo existe, âncora resolve por slug exato, linha existe); registro literal do ID de medição local em linha de tabela estruturada; para cadeias, comparação de conteúdo e ordem com a tabela de `PROJECT.md`; para IDs de evidência, existência como cartão ou linha de tabela e derivação verificável dos proxies de custo. O que falta: pins e autoria são adotados sem comparar o valor declarado com o conteúdo da fonte; `story_id`, fase, revisões, política e famílias aceitam qualquer localização existente; e os papéis solicitados são exigidos da política (`PROJECT.md`) quando deveriam vir da solicitação ou spec, divergência conhecida desde r05. Prova de que a classe permanece aberta: o parecer r05 (`T009-r05.md`, R1) mostrou autoria aceita com fonte que registra outra família, pin aceito com fonte que não contém o pin, e `story_id`, fase, revisões e política aceitos com `README.md:1` como fonte; os campos `phase`, `context_revision`, `catalog_revision` e o conteúdo do registro de julgamento nunca foram sondados por conteúdo. Após quatro rodadas consecutivas com achados dessa classe, a fase consultiva (`T009-c01.md`) concluiu que se trata de requisitos a consolidar, não de manifestações a corrigir uma a uma: a especificação normativa passa a viver em T010 como tabela tipo de informação → fonte autorizada → conteúdo que sustenta o valor → como conferir. Este protótipo permanece ilustrativo da camada mecânica com essa lacuna declarada; ele não é a fonte de verdade da regra e não se torna validador distribuído.


Embora o protótipo execute a conferência mecânica com precisão determinística, certas dimensões da validação permanecem fora do alcance do código mecânico e demandam prerrogativa do julgamento humano ou de avaliações adicionais:
1. **Pertinência Fina à Tarefa (Task-Specific vs General Model):** O código valida se a evidência é pertinente à família técnica do modelo candidato (ex.: se o cartão é de Astra, Flash, Sonnet, etc.), mas a avaliação qualitativa sobre a adequação intrínseca do perfil de raciocínio do modelo às especificidades semânticas de uma tarefa de engenharia específica permanece no âmbito do julgamento humano registrado.
2. **Adequação do Esforço Intelectual (Effort Adequacy):** O código valida o formato e o catálogo do campo `effort` (`low`, `medium`, `high`, `max`), mas se uma tarefa requer imperativamente raciocínio `high` ou se `medium` seria suficiente é decisão qualitativa do Classificador sujeita à revisão do avaliador humano.
3. **Escopo Econômico Global (Budget Tradeoffs):** O validador confere a procedência dos identificadores econômicos e se o cartão sustenta formalmente custo por tarefa; no entanto, o equilíbrio de alocação de orçamento total da sprint/projeto e compensação de custos entre tarefas depende de governança humana.
4. **O que NÃO foi testado no piloto:**
   - Desempenho e comportamento do validador em ambiente de produção com execução concorrente de múltiplos agentes em tarefas de ponta a ponta.
   - Comparação pareada A/B controlada entre níveis de reasoning effort (`medium` vs `high`/`max`) em sessões idênticas do Orquestrador.
   - Latência agregada e consumo de I/O em repositórios com milhares de arquivos de evidência históricos.

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
=== T009 MECHANICAL CHECK: INÍCIO DO SELF-TEST (REWORK ROUND 5) ===

=== QUALIFICAÇÃO VERIFICÁVEL DE CARTÕES PROXY ECONÔMICO (R2) ===
Cartões que qualificaram como 'official_task_proxy' por afirmação de custo por tarefa:
  - 'astra-coding': "Terminal-Bench mostra custo API estimado por tarefa cerca de 9% menor para Astra."
  - 'flash-deepswe': "No gráfico oficial Gemini 3.8 Flash / DeepSWE v1.1, o eixo de custo por tarefa é **invertido**: direita significa menor custo."
Cartões que NÃO qualificaram (sem custo por tarefa): astra-domain, gpt56-coding, opus-effort, sonnet-effort.

=== DERIVAÇÃO DE PERTINÊNCIA DE EVIDÊNCIAS POR MODELO (R3-a) ===
  - 'astra-coding': modelos pertinentes ['Astra']
  - 'astra-domain': modelos pertinentes ['Astra']
  - 'flash-deepswe': modelos pertinentes ['Flash']
  - 'gpt56-coding': modelos pertinentes ['Luna', 'Sol', 'Terra']
  - 'opus-effort': modelos pertinentes ['Opus']
  - 'price-astra': modelos pertinentes ['Astra']
  - 'price-flash': modelos pertinentes ['Flash']
  - 'price-luna': modelos pertinentes ['Luna']
  - 'price-opus': modelos pertinentes ['Opus']
  - 'price-sol': modelos pertinentes ['Sol']
  - 'price-sonnet': modelos pertinentes ['Sonnet']
  - 'price-terra': modelos pertinentes ['Terra']
  - 'sonnet-effort': modelos pertinentes ['Sonnet']
  - 'transport-claude': modelos pertinentes ['Opus', 'Sonnet']
  - 'transport-flash': modelos pertinentes ['Flash']
  - 'transport-openai': modelos pertinentes ['Astra', 'Luna', 'Sol', 'Terra']

[Teste de Robustez A] ID local com caminho inexistente:
SUCESSO (recusa esperada): Caminho de procedência '_tl-orc/project/evidence/arquivo-fantasma.md' do ID 'local-fake' em 'local_ids' não existe.

[Teste de Robustez B] Lista de IDs passada 'na hora' sem origem:
SUCESSO (recusa esperada): ID 'price-astra' em 'local_ids' rejeitado: lista de IDs passada 'na hora' sem origem declarada (proibido; toda entrada deve declarar arquivo + âncora ou linha).

[Teste de Robustez C] ID local em docs/MODEL_ROUTING.md (R1):
SUCESSO (recusa esperada): Registro de medição local 'sonnet-effort' em 'docs/MODEL_ROUTING.md' rejeitado: só é aceito em arquivo de evidência sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/' (nunca em docs/MODEL_ROUTING.md, T009-cases/, T009-analysis.md ou no protótipo).

[Teste de Robustez D] ID local no protótipo com linha inexistente (R1):
SUCESSO (recusa esperada): Registro de medição local 'local-fake' em '_tl-orc/project/evidence/T009-mechanical-check.py' rejeitado: só é aceito em arquivo de evidência sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/' (nunca em docs/MODEL_ROUTING.md, T009-cases/, T009-analysis.md ou no protótipo).

[Teste de Robustez E] ID local legítimo apontando para tabela Agent runs em T005-r01.md:16 (R1):
SUCESSO (aceitação esperada): ID local registrado e localizado com sucesso na tabela Agent runs.

[Teste de Robustez F] Declaração indevida de astra-domain como proxy (R2):
SUCESSO (recusa esperada): ID 'astra-domain' em 'proxy_ids' rejeitado: cartão em docs/MODEL_ROUTING.md não contém comprovação de custo por tarefa (incompatível com official_task_proxy).

[Teste de Robustez G] ID local fabricado em arquivo JSON de caso (R1):
SUCESSO (recusa esperada): Registro de medição local 'local-fake' em '_tl-orc/project/evidence/T009-cases/expected_r2_unregistered_local_id.json' rejeitado: só é aceito em arquivo de evidência estruturada sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/' (excluindo T009-cases/, T009-analysis.md e o próprio protótipo).

[Teste de Robustez H] ID local fabricado em T009-analysis.md (R1):
SUCESSO (recusa esperada): Registro de medição local 'local-fake' em '_tl-orc/project/evidence/T009-analysis.md' rejeitado: T009-analysis.md é documento de análise e não constitui registro estruturado de medição.

[Teste de Robustez I] Âncora declarada por prefixo em T009-classification.md (R2):
SUCESSO (recusa esperada): ID 'local-t005-checker-astra' em 'local_ids' rejeitado: âncora '#conferência-mecânica-pelo' não encontrada como título Markdown em '_tl-orc/project/evidence/T009-classification.md'.

[Teste de Robustez J] Âncora exata completa em T009-classification.md (R2):
SUCESSO (aceitação esperada): âncora exata '#conferência-mecânica-pelo-orquestrador' validada com sucesso.

[Teste de Robustez K] Evidência não pertinente ao modelo (Astra com flash-deepswe) (R3-a):
SUCESSO (recusa esperada): candidato Astra com flash-deepswe rejeitado mecanicamente: checker ('codex', 'gpt-6-astra', 'high'): evidence_id 'flash-deepswe' não pertinente ao modelo 'gpt-6-astra' (modelos pertinentes: ['Flash'], modelo do candidato: 'Astra')

[Teste de Robustez L] Objeto alterado com mesmo registro de julgamento (R3-b):
SUCESSO (bloqueio esperado): objeto alterado resultou em julgamento pendente: PENDENTE (julgamento não se aplica a este objeto: pendente)

[Teste de Robustez M] Registro de julgamento com veredito rejeitado (R3-b):
SUCESSO (bloqueio esperado): julgamento com veredito rejeitado não liberado: REJEITADO (registro de julgamento com veredito 'rejeitado': não liberado)

[Teste de Robustez N] Registro de julgamento com localização inexistente (:999999) (R3-b):
SUCESSO (bloqueio esperado): localização inexistente resultou em julgamento pendente: PENDENTE (linha 999999 inexistente em '_tl-orc/project/evidence/T005-classification.md': localização inexistente)

[Teste de Robustez O] Lista solta sem envelope para roles em expected (R1):
SUCESSO (recusa esperada): roles fornecida como lista solta sem envelope (proibido; toda lista de referência deve vir em envelope {'value': ..., 'source': ...}).

[Teste de Robustez P] Procedência de roles apontando para arquivo inexistente (R1):
SUCESSO (recusa esperada): arquivo de procedência 'arquivo-inexistente.md' de 'roles' não existe.

[Teste de Robustez Q] Cadeia declarada divergente da tabela de PROJECT.md (R1):
SUCESSO (recusa esperada): cadeia declarada para 'checker' (['agy', 'codex', 'claude']) diverge da tabela de PROJECT.md (['codex', 'claude', 'agy']).

[Teste de Robustez R] 3º candidato com model:null e effort:null com reason (lacuna legítima) (R2):
SUCESSO (aceitação esperada de lacuna legítima): s1=APROVADA, s2=CONFIRMADO, s3=LIBERADO, disp=checker:codex/gpt-6-astra/high

[Teste de Robustez S] Candidato com nulidade inconsistente (model: null e effort: 'high') (R2):
SUCESSO (recusa esperada): nulidade inconsistente rejeitada mecanicamente: schema: $.roles.checker.candidates[2].effort esperado tipo null, obtido str

[Teste de Robustez T] 1º candidato com model:null e effort:null havendo par no catálogo (lacuna suspeita) (R2):
SUCESSO (bloqueio esperado de lacuna suspeita): s1=APROVADA, s2=CONFIRMADO, s3=BLOQUEADO, disp=nenhum (bloqueado com ponto de retomada: lacuna suspeita de normalizar escolha inválida no candidato 1 (checker: codex) exige julgamento prévio)

============================================================================================================================================
Caso                                   | Mecânica  | Julgamento  | Despacho  | Status     | Despacho Simulado
============================================================================================================================================
case_01_valid                          | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_02_invalid_catalog                | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_03_invalid_story_id               | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_03b_invalid_story_id_null         | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_04_invalid_evidence_id            | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_05_incompatible_evidence          | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_06_control_preserved_rules        | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_07_r2_unregistered_local_id       | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_08_r2_invalid_proxy_card          | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_09_r2_official_marker_as_evidence | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_10_r3_missing_candidate_reason    | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_11_r3_empty_facts                 | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_12_r3_extra_property              | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_13_r4_preferred_unproven_fallback | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_14_r4_preferred_proven_fallback   | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:agy/gemini-3.1-pro-high/...
case_15_r4_required_same_family        | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_16_r5_valid_without_judgment      | APROVADA  | PENDENTE (a | NENHUM    | ACEITA (aguardando julgamento) | nenhum
case_17_r1_local_routing_anchor        | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_18_r1_local_prototype_line        | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_19_r1_local_valid_reference       | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_20_r2_astra_domain_proxy          | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_21_r3_unproven_text_readme        | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_22_r3_timeout_as_proof            | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_23_r3_same_family_disabled        | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_24_r4_unresolved_family           | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
case_25_r1_local_json_case             | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_26_r1_local_analysis              | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_27_r2_anchor_prefix               | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_28_r3_unrelated_model_evidence    | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_29_r3_altered_object_judgment     | APROVADA  | PENDENTE (j | NENHUM    | ACEITA (aguardando julgamento) | nenhum
case_30_r3_rejected_judgment           | APROVADA  | REJEITADO ( | NENHUM    | REJEITADA  | nenhum
case_31_r3_missing_judgment_location   | APROVADA  | PENDENTE (l | NENHUM    | ACEITA (aguardando julgamento) | nenhum
case_32_r1_bare_list_roles             | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_33_r1_nonexistent_source          | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_34_r1_divergent_chain             | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_35_r2_null_candidate_lacuna       | APROVADA  | CONFIRMADO  | LIBERADO  | ACEITA     | checker:codex/gpt-6-astra/high
case_36_r2_inconsistent_null           | REJEITADA | N/A         | NENHUM    | REJEITADA  | nenhum
case_37_r2_suspicious_first_cand_lacuna | APROVADA  | CONFIRMADO  | BLOQUEADO | BLOQUEADO  | nenhum
============================================================================================================================================

[Modo estrito sem escrita]: Resumo em memória coincide 100% com 'pilot_summary.json' (R6 cumprido).

=== AUTO-TESTE DO PILOTO: TODOS OS 38 CASOS PASSARAM COM AS REJEIÇÕES, BLOQUEIOS E APROVAÇÕES ESPERADAS (EXIT 0) ===
[Exit code: 0]
```

---

## Tabela de Cobertura (Coverage AC01–AC06)

| Critério de Aceitação | Seção do Documento | Linhas Exatas | Status |
| :--- | :--- | :--- | :--- |
| **AC01** (Diagnóstico, ocorrências citadas por caminho correto, separação explícita de fatos, hipóteses e não verificadas) | `## AC01: Diagnóstico com Ocorrências Registradas e Citações por Caminho` | L18–L57 | **Coberto** |
| **AC02** (Proposta em 3 estágios, procedência verificável de referências/listas, registro efetivo, lacuna de harness e schema recursivo) | `## AC02: Proposta em Três Estágios e Origem Obrigatória das Entradas` | L59–L153 | **Coberto** |
| **AC03** (Regras preservadas: independência como resolução, fallback sob preferred com prova, preservação do julgamento qualitativo, lacunas permitidas e cost_basis unknown) | `## AC03: Regras Preservadas e Demonstração no Protótipo` | L155–L188 | **Coberto** |
| **AC04** (Piloto delimitado com 38 casos, três colunas de estágio, motivos tabelados e prova de não-despacho) | `## AC04: Piloto Delimitado — Tabela de Casos, Estágios e Prova de Não-Despacho` | L190–L241 | **Coberto** |
| **AC05** (Premissas, 3 alternativas sem quantificações não mensuradas, limitações residuais do protótipo, o que mudaria a conclusão, escopo excluído) | `## AC05: Premissas, Alternativas Consideradas e Escopo Excluído` | L243–L298 | **Coberto** |
| **AC06** (Portões verdes, saídas literais com exit codes, self-test estritamente sem escrita) | `## AC06: Portões de Validação e Saídas Literais` | L300–L451 | **Coberto** |
