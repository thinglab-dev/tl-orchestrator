# Análise: Briefing Mínimo do Classificador com Esqueleto Literal (T002)

unit: native/task/T002@_tl-orc/project/tasks/T002-esqueleto-do-schema-no-briefing.md  
kind: analysis  
deliverable: none  
standalone: true  
method: native  
spec_revision: d1826e1b23d2b131 (s1)  
content_paths: [_tl-orc/project/evidence/T002-analysis.md, _tl-orc/project/evidence/T002-briefing-template.md, _tl-orc/project/evidence/T002-briefing-skeleton.py, _tl-orc/project/evidence/T002-cases/]  

---

## Sumário Executivo

Esta análise investiga as causas das falhas estruturais e semânticas registradas nas primeiras chamadas do Classificador (`gpt-5.6-luna`, `effort: medium`), tanto nos smokes do consumidor `platform` quanto nas tarefas do repositório fonte (`T005`, `T009`, `T010`). O diagnóstico e a amostra observada sustentam a hipótese de que briefings sem esqueleto literal do schema e sem regras explícitas — nos quais os campos são descritos discursivamente em prosa — favorecem desvios de formato sistemáticos (como identificadores compostos `harness/modelo/effort`, `cost_basis` em prosa, confusão de enums de tier com effort e omissão de revisões), enquanto a ausência de uma regra explícita sobre cadeias favorece a omissão de candidatos inelegíveis pela política. Conforme delimitado em :165-166, registra-se que a causalidade isolada do esqueleto não foi demonstrada separadamente das regras, pois ambos os fatores foram alterados conjuntamente na medição.

Como solução, formaliza-se o conceito de **briefing mínimo**, composto por:
1. Procedência obrigatória por entrada conforme a tabela normativa de `prompts/orchestrator-perfis.md:236-244`;
2. Um esqueleto JSON literal derivado diretamente de `schemas/classification-result.schema.json` por protótipo não distribuído (`_tl-orc/project/evidence/T002-briefing-skeleton.py`);
3. Bloco de regras fixas determinando um candidato por harness na ordem da cadeia informada (inclusive inelegíveis, com justificativa em `reason`), tratamento de lacunas com `model: null` e `effort: null`, pertinência de `evidence_ids`, ancoragem econômica de `cost_basis` e fechamento obrigatório do JSON.

A medição empírica em smoke sintético (AC03), executada pelo Orquestrador em 2026-09-08 e registrada em `_tl-orc/project/evidence/T002-cases/RESULTS.md:1-31`, corroborou o diagnóstico com amostra controlada de $N = 3$ por condição: o briefing em prosa resultou em 0/3 respostas válidas na primeira chamada (2 JSONs malformados por fechamento prematuro com dados adicionais pendentes e 1 resposta com enums inválidos e revisões ausentes), enquanto o briefing mínimo obteve 3/3 respostas válidas (100% de conformidade mecânica de estrutura e catálogo). Registra-se que o experimento alterou conjuntamente o esqueleto literal e o bloco de regras fixas (não isolando os dois fatores) e não estabelece taxas populacionais universais, refletindo resultados estritamente observados na amostra. Propõe-se o delta normativo em rascunho para `prompts/orchestrator-perfis.md` e `prompts/classifier.md` (sem alterar arquivos distribuídos nesta Task) e analisam-se as premissas, alternativas consideradas e limites da conclusão.

---

## AC01: Diagnóstico com Ocorrências Registradas e Citações por Caminho

A especificação do Classificador em `prompts/classifier.md:99-106` e o procedimento em `prompts/orchestrator-perfis.md:82-106` exigem uma resposta estritamente conforme a `schemas/classification-result.schema.json`. Não obstante, registrou-se um padrão recorrente de falhas em primeiras respostas quando o modelo é despachado sem um esqueleto literal.

### Tabela de Ocorrências Registradas

| Caminho / Origem | Briefing tinha esqueleto literal? | Defeito: briefing \| modelo \| condição | Fato observado / Erro estrutural | Desfecho / Consequência |
| :--- | :--- | :--- | :--- | :--- |
| `_tl-orc/project/tasks/T002-esqueleto-do-schema-no-briefing.md:16-20` (Finding: smokes v0.4.0 r03–r07) | Não | Relato secundário (Finding da Task T002 / briefing do Orquestrador; detalhes não verificados diretamente na árvore local por ausência dos arquivos do platform) | Classificador devolveu respostas estruturalmente inválidas: campos obrigatórios ausentes, propriedades extras, tier `"primary"`, confidence numérico, facts estruturados como objetos. | A inclusão posterior de esqueleto literal com enums e campos obrigatórios eliminou as falhas nas rodadas seguintes. |
| Consumidor platform — Smoke v0.5.0 r1 Claude Code | Parcial / Sem template padronizado | Relato secundário (spec/briefing do Orquestrador; _tl-orc/project/evidence/T009-analysis.md:30-32; detalhes não verificados diretamente na árvore local) | Primeira resposta de Luna incluiu modelo fora do catálogo autorizado (`claude-opus-5`) e citou evidência `price-flash` para `gemini-3.1-pro`. | Sessão corrigida via `resume` (com desvio de modelo no resume do Orquestrador). |
| Consumidor platform — Smoke v0.5.0 r3 Claude Code | Não padronizado | Relato secundário (spec/briefing do Orquestrador; _tl-orc/project/evidence/T009-analysis.md:35-37; detalhes não verificados diretamente na árvore local) | Par `codex/gpt-5.6-luna` como Maker (fora do catálogo de Maker) aceito pelo Orquestrador e `story_id: "lynvia-mkauth-connector:T005"` preenchido indevidamente quando se exigia null (_tl-orc/project/evidence/T009-analysis.md:35-37); inversão e posterior correção da ordem da cadeia mantidas como não verificado (relato secundário do briefing do Orquestrador). | Desvio de validação do Orquestrador aceitou candidato fora do catálogo; correção da cadeia mantida como não verificado (relato secundário). |
| Consumidor platform — Smoke v0.5.0 r3 Codex | Não estruturado | Relato secundário (spec/briefing do Orquestrador; T009-analysis.md:38-41; detalhes não verificados diretamente na árvore local) | Conforme T009-analysis.md:40, o Orquestrador compôs o briefing sem cartões de evidência do `MODEL_ROUTING.md`, fabricou identificadores de evidência genéricos no briefing e aceitou a classificação gerada. | Classificação inválida aceita indevidamente pelo Orquestrador por defeito na montagem do briefing. |
| Consumidor platform — Smoke v0.6.0 Claude Code (2026-09-08) | Não (campos descritos em prosa) | Relato secundário (spec/briefing do Orquestrador, Finding e AC01 da Task T002; detalhes não verificados diretamente na árvore local) | Briefing continha procedência e catálogo literal, mas descreveu campos em prosa: Luna devolveu 2 respostas estruturalmente inválidas: `model` composto (`"harness/modelo/effort"`), `cost_basis` em prosa ou `null`, `tier` fora do enum (`"medium"`/`"high"` em vez de `simple|normal|heavy`), `context_revision` e `catalog_revision` ausentes. | Bloqueio antes dos despachos; tarefa interrompida por esgotamento da correção sem classificação válida. |
| Repositório fonte — `_tl-orc/project/evidence/T005-classification.md:8-14, 27-28, 46` | Sim | Modelo (Luna na 1ª chamada; Terra na correção) \| Condição: `effort: medium` | Na fase `implementation` r01, Luna gerou primeira chamada com JSON truncado (:8). Na correção via `resume`, o Orquestrador executou sem `-m`, e a resposta que continha `transport-flash` atribuído a `gemini-3.1-pro-high` foi gerada por `gpt-5.6-terra` medium (:9 e :46), não por Luna. Na fase `review` r01, Luna gerou primeira chamada com `official_task_proxy` para Sonnet sem base econômica (:27-28); a correção válida foi gerada por Terra no resume sem `-m` (:28, :46). | Desvios registrados: Orquestrador despachou Maker sob classificação semanticamente inválida; correção única na fase review adotada após segundo run; descoberta posterior do desvio de modelo no resume. |
| Repositório fonte — `_tl-orc/project/evidence/T009-classification.md:7, 35, 64, 84, 103, 122, 141, 160` | Sim (com esqueleto e conferência mecânica) | Nenhum defeito estrutural \| Modelo (Luna) \| Condição: `effort: medium` | Em 8 de 8 fases classificadas com esqueleto literal e regras claras, a primeira resposta de Luna foi **100% estruturalmente válida** (`implementation`, `review r01`, `review r04`, `rework r05`, `review r05`, `debate c01`, `review r06`, `review r07`). | Todas as 8 classificações aceitas na primeira chamada após validação mecânica. |
| Repositório fonte — `_tl-orc/project/evidence/T010-classification.md:7, 29, 49, 68, 88, 107, 126, 145, 165, 184, 203, 223, 242, 245` | Sim (esqueleto presente, mas sem regra explícita de candidatos inelegíveis na cadeia) | Briefing (lacuna de regra) \| Modelo (Luna) \| Condição: `effort: medium` | Das 13 primeiras chamadas registradas no arquivo, **oito foram válidas** (linhas 7, 49, 88, 107, 126, 165, 184, 223) e **cinco foram inválidas** (linhas 29, 68, 145, 203, 242, com observação da quinta ocorrência em :245): Luna omitiu candidatos da cadeia do Checker que eram inelegíveis pela restrição `required` de família distinta, devolvendo 1 ou 2 candidatos em vez dos 3 correspondentes à cadeia configurada recebida no briefing (embora estruturalmente válido perante `schemas/classification-result.schema.json:117-120`, que admite de 1 a 3 candidatos, violou a conformidade à cadeia recebida). | 8 de 13 primeiras chamadas válidas (taxa observada: 61,5%); as 5 inválidas decorreram exclusivamente dessa omissão de candidatos inelegíveis e exigiram correção única com `-m`. |

### Distinção entre Defeito do Briefing, Defeito do Modelo e Condição Observada

1. **Defeito do Briefing:**
   - *Omissão do esqueleto literal:* Ao descrever os campos apenas discursivamente em prosa (caso crítico do smoke v0.6.0 do Claude Code e smokes v0.4.0), o briefing delega a inferência da gramática do JSON ao modelo. O modelo confunde os enums de `tier` (`simple|normal|heavy`) com os valores de `effort` (`medium|high`), concatena campos atômicos (`model: "codex/gpt-5.6-terra/high"`), omite campos estruturais (`context_revision`, `catalog_revision`) e converte enum em texto livre (`cost_basis: "baseado no token price"`).
   - *Omissão da regra de candidatos inelegíveis:* O briefing informava a política de independência (`checker_independence: required`) sem instruir expressamente que *todos os harnesses da cadeia devem ser preenchidos*, mesmo os inelegíveis. Diante da restrição, Luna filtrou preventivamente o candidato do harness conflitante, violando o contrato de entregar a cadeia inteira para resolução posterior pelo Orquestrador (`prompts/classifier.md:44-47`).
   - *Omissão de cartões de evidência pelo Orquestrador:* No smoke v0.5.0 r3 Codex, o Orquestrador montou o briefing sem os cartões de `docs/MODEL_ROUTING.md` e fabricou identificadores genéricos no próprio briefing (`T009-analysis.md:40`), induzindo a classificação inválida.

2. **Defeito do Modelo (`Codex gpt-5.6-luna`):**
   - *Truncamento vs. Fechamento prematuro:* Vulnerabilidade a interrupção prematura da saída. Distingue-se o corte abrupto registrado em `_tl-orc/project/evidence/T005-classification.md:8` como `"JSON truncado (sem chave final)"` — cuja atribuição a limite de saída permanece como hipótese não verificada, pois o registro histórico documenta apenas a ausência da chave final sem detalhar a causa mecânica do corte — do fechamento prematuro do objeto (encerramento da chave raiz antes do campo `confidence`, seguido da emissão do fragmento excedente fora da raiz, observado nas chamadas em prosa de AC03).
   - *Alucinação de pertinência:* Associação de cartões específicos de uma família a modelos de outra (como observado no smoke v0.5.0 r1; nota-se que o desvio correspondente em T005 foi gerado por `gpt-5.6-terra` no resume sem `-m`, e não por Luna).
   - *Sobregeneralização de restrições:* Tendência observada a aplicar filtros de política na geração dos candidatos, excluindo opções em vez de declará-las com motivo de inelegibilidade em `reason`.

3. **Condições Observadas e Hipóteses Comportamentais:**
   - *Condição de esforço nas sessões:* Em `_tl-orc/project/evidence/T009-analysis.md:46-47`, a condição observada de `effort: medium` refere-se às **sessões do Orquestrador**. Nas tarefas do repositório fonte (`T005`, `T009`, `T010`), o Classificador operou em `effort: medium` por ser esse o seu perfil padrão publicado em `prompts/orchestrator-perfis.md:22-26`.
   - *Hipótese comportamental não verificada:* A suposição de que o modelo em `effort: medium` "não realiza backtracking reflexivo extenso" para inferir esquemas complexos a partir de prosa constitui uma hipótese heurística não verificada sobre o funcionamento interno do LLM. O dado empiricamente comprovado é que, sob o mesmo nível `effort: medium`, o fornecimento de esqueleto literal rígido e regras explícitas elevou a validade estrutural observada de 0/3 (prosa) para 3/3 (mínimo) na medição de AC03, e manteve 100% de validade em T009 (8/8).

---

## AC02: Definição do Briefing Mínimo

O **briefing mínimo** é a proposta de padronização estruturada do conjunto de dados que o Orquestrador deve enviar ao Classificador com o objetivo de reduzir a incidência de primeiras respostas inválidas, conforme sustentado pela amostra observada. A proposta visa mitigar ambiguidades sintáticas e tratar as lacunas observadas nas ocorrências de AC01, sem constituir garantia absoluta de validade em qualquer cenário.

### 1. Campos Obrigatórios e Enums do Schema

Conforme definido em `schemas/classification-result.schema.json:6-17, 97-125, 127-230`:
- `schema_version`: Inteiro estrito constante (`2`).
- `story_id`: String não vazia (ex: `"T002"`, `"billing:T012"`) ou literal `null` quando o trabalho não possuir story cadastrada.
- `phase`: Enum obrigatório com exatamente 5 opções: `"debate" | "planning" | "implementation" | "review" | "rework"`.
- `context_revision`: String literal não vazia contendo o hash/revisão do contexto de trabalho recebido.
- `catalog_revision`: String literal não vazia contendo a revisão do catálogo de modelos autorizado.
- `confidence`: Enum restrito: `"high" | "medium" | "low"`.
- `facts`: Array de strings (mínimo 1 item) com fatos objetivos extraídos exclusivamente do briefing.
- `uncertainties`: Array de strings com incertezas materiais (pode ser vazio).
- `reclassify_when`: Array de strings (mínimo 1 item) com condições concretas para reclassificação.
- `roles`: Objeto contendo exclusivamente os papéis solicitados para a fase (`planner`, `maker`, `checker`, e sob demanda `searcher`). Cada papel contém:
  - `tier`: Enum restrito `"simple" | "normal" | "heavy"`.
  - `reason`: String curta e verificável justificando o dimensionamento do papel.
  - `candidates`: Array contendo exatamente **um candidato por harness na ordem da cadeia informada**. Cada candidato contém:
    - `harness`: Enum `"codex" | "claude" | "agy"`.
    - `model`: String com o ID autorizado no catálogo para o harness, ou `null` em caso de lacuna.
    - `effort`: Enum `"none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra" | null` (se `model` for `null`, `effort` deve ser obrigatoriamente `null`).
    - `evidence_ids`: Array de strings únicas contendo identificadores presentes no briefing.
    - `cost_basis`: Enum `"local_observed" | "official_task_proxy" | "token_price_only" | "unknown"`.
    - `reason`: String curta justificando a escolha ou o motivo da lacuna/inelegibilidade.

### 2. Regra Explícita de Candidatos por Cadeia e Inelegibilidade

Para erradicar as 5 ocorrências de omissão registradas em T010, o briefing mínimo impõe a regra:
> "Para cada papel solicitado, forneça exatamente um candidato por harness na ordem da cadeia informada, **inclusive candidatos inelegíveis pela política vigente**. Candidatos inelegíveis (por exemplo, por restrição de família no Checker) devem ser mantidos na sua posição na cadeia, com a restrição e o motivo explicitados no campo `reason`."

### 3. Catálogo Literal com Procedência e IDs de Evidência

- **Catálogo:** Enviado no briefing como pares literais autorizados `(harness, modelo, effort)`, capacidades, autorizações e restrições por papel (`prompts/classifier.md:30, 104`), sustentado por fonte autorizada conforme a precedência (`instrução do usuário > PROJECT.md > perfil publicado`, `prompts/orchestrator-perfis.md:239`), com procedência verificável por linha.
- **IDs de Evidência:** Somente IDs estáveis presentes em `docs/MODEL_ROUTING.md:14-36` ou em linhas de medições locais de evidências estruturadas do projeto (`prompts/orchestrator-perfis.md:241-242`). Para identificadores de medições locais (`local-*`), exige-se registro estruturado real no qual o ID conste obrigatoriamente na primeira coluna de uma tabela em evidência do projeto (`prompts/orchestrator-perfis.md:242-245`). É expressamente proibido enviar IDs fabricados ou inferidos.
- **Regras de `cost_basis`:** Quando `cost_basis` for diferente de `unknown`, `evidence_ids` deve conter ao menos um ID de evidência econômica (tarifa `price-*`, proxy de custo de tarefa `*-coding`, `flash-deepswe`, ou medição local estruturada `local-*`). Referências puramente de capacidade técnica não sustentam base econômica.

### 4. Instrução Mandatória de Fechamento

O briefing instrui o modelo a responder exclusivamente com o objeto JSON íntegro, fechando todas as chaves e colchetes abertos, sem qualquer texto introdutório, conclusivo, dados adicionais fora da raiz, truncamento ou fechamento prematuro.

### 5. Cobertura Efetiva e Derivação do Esqueleto pelo Protótipo

O protótipo não distribuído `_tl-orc/project/evidence/T002-briefing-skeleton.py` deriva de `schemas/classification-result.schema.json` os enums (`phase`, `confidence`, `tier`, `effort`, `cost_basis`, `harness`), a constante `schema_version` e a admissão de `null` em `story_id`, `model` e `effort` (restrições cumulativas: o tipo precisa admitir `null` e, havendo `enum`, o `enum` precisa contê-lo). A cobertura é a de um gerador de esqueleto para o schema atual, não a de um validador genérico de JSON Schema: os nomes dos campos gerados são fixos e conferidos nos dois sentidos contra `required` (raiz, `$defs/role`, `$defs/candidate`), com interrupção e mensagem clara quando há campo obrigatório desconhecido ou esperado ausente; os campos de lista da raiz exigem `items.type: string`, por serem emitidos como placeholders de texto; um campo de enum ausente, vazio ou com formato incompatível interrompe a geração. Fora dessa cobertura declarada (por exemplo, `minItems`, `maxItems`, `pattern`, `minLength` ou palavras-chave condicionais), o protótipo não confere nem reproduz a restrição, e o esqueleto emitido pode não refletir alterações futuras nessas palavras-chave: a garantia é de coincidência com o schema atual nos campos e enums cobertos, não de adaptação automática a qualquer schema. Contraprovas executadas com cópias alteradas do schema em diretório temporário: campo obrigatório desconhecido na raiz → interrupção; `effort` removido de `$defs/candidate` → interrupção; `null` removido do enum de `effort` → esqueleto sem `|null`; `enum` acrescentado a `model` sem `null` (com `type` ainda admitindo `null`) → placeholder sem a alternativa `null`; `facts.items` alterado para `integer` → interrupção.

---

## AC03: Medição em Smoke Sintético (Resultados da Medição)

A verificação empírica da eficácia do briefing mínimo foi executada pelo Orquestrador em 2026-09-08, estruturada como experimento controlado pareado em ambiente sintético conforme registrado em `_tl-orc/project/evidence/T002-cases/RESULTS.md:1-31`.

### Condições e Desenho Experimental
- **Modelo e Esforço Fixos:** Codex `gpt-5.6-luna`, `model_reasoning_effort=medium` (perfil fixo do Classificador em `prompts/orchestrator-perfis.md:22-26`).
- **Ambiente de Execução:** Sandbox read-only, sessões novas e isoladas (`codex exec`), sem histórico compartilhado e **sem rodada interativa de correção** (`resume`), avaliando estritamente a **primeira resposta**.
- **Entradas Controladas:** Mesma intenção sintética (painel Debater, fase `debate`, `story_id: null`, papéis `planner`, `maker`, `checker`, risco baixo, sem diff nem escrita) e mesmo catálogo de modelos (perfil de despacho do repositório fonte em `_tl-orc/PROJECT.md`).
- **Amostra e Grupos ($N = 3$ por condição, total 6 chamadas):**
  1. *Grupo Controle (Prosa):* 3 chamadas (`prosa-1` a `prosa-3`) com briefings em `_tl-orc/project/evidence/T002-cases/briefing-prosa-1.md` a `briefing-prosa-3.md`, contendo os campos descritos discursivamente em prosa, sem esqueleto JSON literal (estilo smoke v0.6.0 do Claude Code).
  2. *Grupo Tratamento (Briefing Mínimo):* 3 chamadas (`minimo-1` a `minimo-3`) com briefings em `_tl-orc/project/evidence/T002-cases/briefing-minimo-1.md` a `briefing-minimo-3.md`, contendo as mesmas entradas textuais acrescidas do esqueleto JSON literal gerado por `_tl-orc/project/evidence/T002-briefing-skeleton.py` com as cadeias do repositório fonte e bloco de regras fixas de integridade.
- **Conferência Mecânica em Duas Camadas:**
  1. *Camada Estrutural (`check_struct.py`):* Validação mecânica contra `schemas/classification-result.schema.json` cobrindo `type`, `enum`, `const`, `required`, `additionalProperties`, `items`, `minItems`, `$ref`, `allOf`, `if-then` e `not`;
  2. *Camada de Catálogo, Cadeias, Pins e Evidências (`mech_check.py`):* Verificação mecânica automatizada baseada no protótipo de T009, checando pertencimento dos pares `(harness, model, effort)` ao catálogo autorizado, respeito à ordem das cadeias e aos pins (`maker: agy/gemini-3.8-flash-high/high`, `checker: codex/gpt-6-astra/high`), exatidão das revisões (`context_revision`, `catalog_revision`), pertinência dos identificadores em `evidence_ids` e regras econômicas de `cost_basis`.

### Resultados Consolidados por Chamada

| Chamada | Sessão Codex | Início → Fim UTC | Estrutura | Catálogo / Cadeias / Pins / IDs | Defeitos da Primeira Resposta | Registro de Conferência |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `prosa-1` | `01a07e99-d6b0-7343-93d5-72e66adaa2d9` | 20260908T012006Z → 20260908T012043Z | inválida | n/a | JSON malformado (fechamento prematuro com fragmento `,"confidence":"high"}` pendente fora da raiz); 'version' em vez de schema_version; revisões ausentes; tier fora do enum | `_tl-orc/project/evidence/T002-cases/check-prosa-1.txt:3-4, 7-8` |
| `prosa-2` | `01a07e9a-67fa-7233-8d3d-8c6869649da1` | 20260908T012043Z → 20260908T012132Z | inválida | rejeitada | schema_version/context_revision/catalog_revision ausentes; propriedade extra 'version'; tier fora do enum | `_tl-orc/project/evidence/T002-cases/check-prosa-2.txt:3-11, 22-24` |
| `prosa-3` | `01a07e9b-2a73-7d53-8c91-7be8cf144f20` | 20260908T012132Z → 20260908T012212Z | inválida | n/a | JSON malformado (fechamento prematuro com fragmento `,"confidence":"high"}` pendente fora da raiz); 'version' em vez de schema_version; revisões ausentes; tier fora do enum | `_tl-orc/project/evidence/T002-cases/check-prosa-3.txt:3-4, 7-8` |
| `minimo-1` | `01a07e9b-c78f-7442-9e5c-fef54d68754e` | 20260908T012212Z → 20260908T012246Z | válida | aceita | — (nenhum defeito; tier "normal" nos 3 papéis) | `_tl-orc/project/evidence/T002-cases/check-minimo-1.txt:3-15` |
| `minimo-2` | `01a07e9c-46f3-7a50-9412-53ae8b2f9516` | 20260908T012246Z → 20260908T012317Z | válida | aceita | — (nenhum defeito; tier "simple" nos 3 papéis) | `_tl-orc/project/evidence/T002-cases/check-minimo-2.txt:3-15` |
| `minimo-3` | `01a07e9c-c1d3-7e50-a5c7-19b9e359fe1f` | 20260908T012317Z → 20260908T012350Z | válida | aceita | — (nenhum defeito; tier "simple" nos 3 papéis) | `_tl-orc/project/evidence/T002-cases/check-minimo-3.txt:3-15` |

### Totais e Inventário de Defeitos Observados

- **Totais Comparativos:**
  - **Briefing em Prosa:** **0/3** respostas válidas na primeira chamada (taxa de sucesso observada: 0%). Foram registrados 2 casos de JSON malformado por fechamento prematuro (gerando `Extra data` no validador) e 1 caso de estrutura JSON parseável porém inválida perante o schema.
  - **Briefing Mínimo:** **3/3** respostas válidas na primeira chamada (taxa de sucesso observada: 100%), com conformidade mecânica plena tanto na camada estrutural de schema quanto na camada de catálogo, cadeias, pins e identificadores de evidência.

- **Defeitos Observados por Chamada:**
  1. *Chamada `prosa-1` (`_tl-orc/project/evidence/T002-cases/check-prosa-1.txt:3-4, 7-8` e `_tl-orc/project/evidence/T002-cases/resposta-prosa-1.json:1`):*
     - Erro sintático de JSON (fechamento prematuro, não truncamento): o objeto raiz foi encerrado prematuramente logo após a chave `reclassify_when`, deixando o fragmento `,"confidence":"high"}` pendente fora da raiz, gerando `Extra data: line 1 column 3247 (char 3246)`;
     - Chave de schema adulterada: emissão de `"version": 2` no lugar do campo obrigatório `"schema_version"`;
     - Campos obrigatórios omitidos: ausência integral de `"context_revision"` e `"catalog_revision"`;
     - Enum de `tier` inválido: o modelo atribuiu o valor `"moderate"` para os três papéis (`planner`, `maker`, `checker`), termo inexistente no enum restrito `['simple','normal','heavy']`;
     - Conferência de catálogo: não executada em decorrência da invalidade sintática do JSON.
  2. *Chamada `prosa-2` (`_tl-orc/project/evidence/T002-cases/check-prosa-2.txt:3-11, 22-24` e `_tl-orc/project/evidence/T002-cases/resposta-prosa-2.json:1`):*
     - Erro estrutural perante o schema: JSON sintaticamente parseável, porém inválido por omitir os campos obrigatórios `"schema_version"`, `"context_revision"` e `"catalog_revision"`;
     - Inclusão de propriedade extra: envio de `"version": 2`, violando `additionalProperties: false`;
     - Confusão de enums com níveis de esforço: atribuição de `"medium"` para planner e maker e `"high"` para checker, misturando os valores de `effort` com os enums formais de `tier`;
     - Conferência de catálogo rejeitada: embora as 9 tuplas de candidatos indicassem pares válidos do catálogo e respeitassem os pins, as revisões exigidas `context_revision` (`"tl-orchestrator@c873846+T002-medicao-AC03"`) e `catalog_revision` (`"PROJECT.md-perfil-de-despacho-2026-09-07"`) resultaram em `None`.
  3. *Chamada `prosa-3` (`_tl-orc/project/evidence/T002-cases/check-prosa-3.txt:3-4, 7-8` e `_tl-orc/project/evidence/T002-cases/resposta-prosa-3.json:1`):*
     - Reprodução exata do defeito de sintaxe de `prosa-1` (fechamento prematuro, não truncamento): encerramento precoce do JSON com `,"confidence":"high"}` excluído do objeto raiz, gerando `Extra data: line 1 column 2917 (char 2916)`;
     - Substituição de `"schema_version"` por `"version"`;
     - Omissão de `"context_revision"` e `"catalog_revision"`;
     - Enum de `tier` inválido: atribuição de `"medium"` para planner e `"high"` para maker e checker;
     - Conferência de catálogo: não executada por JSON inválido.
  4. *Chamadas `minimo-1`, `minimo-2` e `minimo-3` (`_tl-orc/project/evidence/T002-cases/check-minimo-1..3.txt` e `_tl-orc/project/evidence/T002-cases/resposta-minimo-1..3.json`):*
     - Camada estrutural: 100% válida nas três chamadas. Todos os campos obrigatórios (`schema_version: 2`, `story_id: null`, `phase: "debate"`, revisões literais, listas, enums de tier válidos) foram emitidos corretamente sem chaves espúrias, truncamento ou fechamento prematuro;
     - Tiers reais observados: `minimo-1` (`resposta-minimo-1.json:1`) atribuiu `tier: "normal"` aos três papéis (`planner`, `maker`, `checker`); `minimo-2` (`resposta-minimo-2.json:1`) e `minimo-3` (`resposta-minimo-3.json:1`) atribuíram `tier: "simple"` aos três papéis;
     - Camada de catálogo/cadeias/pins/IDs: 100% aceita nas três chamadas. As 9 tuplas de candidatos em cada execução corresponderam a pares válidos do catálogo, os pins de maker (`agy/gemini-3.8-flash-high/high`) e checker (`codex/gpt-6-astra/high`) foram cumpridos na primeira posição da cadeia, as revisões bateram literalmente com as entradas, e os identificadores de `evidence_ids` e `cost_basis` respeitaram a ancoragem econômica.

### Condições e Limites Declarados em RESULTS.md
- **Amostra deliberadamente reduzida ($N = 3$ por condição, total 6 chamadas):** Em conformidade com as diretrizes do projeto, a conclusão empírica não deve ser inflada além de $N = 3$. O resultado comprova objetivamente que, sob a configuração testada, o briefing discursivo em prosa foi incapaz de assegurar sintaxe JSON e enums válidos na primeira resposta (0/3), enquanto o briefing mínimo obteve conformidade imediata (3/3), sem pretensão de extrapolação estatística universal para taxas populacionais de todas as tarefas.
- **Não isolamento dos fatores esqueleto vs. regras:** O experimento alterou conjuntamente a inclusão do esqueleto literal e o bloco de regras fixas de preenchimento. Portanto, o desenho empírico não isola o efeito individual do esqueleto daquele das regras; ambos compõem o mecanismo conjunto do briefing mínimo.
- **Comparação literal dos briefings:** A medição com `wc -c` demonstra que `briefing-prosa-1.md` tem 3.545 caracteres (3.598 bytes) e `briefing-minimo-1.md` tem 10.131 caracteres (10.245 bytes), revelando que o briefing mínimo contém 6.586 caracteres a mais (6.647 bytes a mais).
- **Uniformidade de modelo e nível de raciocínio:** Medição realizada com um único modelo (`Codex gpt-5.6-luna`) e um único nível de raciocínio (`effort: medium`), correspondendo estritamente ao perfil padronizado do Classificador.
- **Uniformidade de intenção e catálogo:** Todas as 6 sessões receberam uma única intenção sintética de baixo risco (debate consultivo sem story) e o catálogo de modelos de `_tl-orc/PROJECT.md`.
- **Escopo estritamente mecânico da avaliação:** A aceitação das respostas mínimas atesta exclusivamente a **conformidade mecânica** (schema, catálogo, pins, IDs e regras econômicas). As respostas não foram avaliadas quanto à pertinência substantiva do julgamento qualitativo (se o tier `"normal"` em `minimo-1` vs. `"simple"` em `minimo-2/3` ou o texto de `reason` representam a melhor decisão de produto), atestando apenas que a máquina de despacho recebe uma carga parseável e executável de acordo com o contrato.
- **Limite sobre a procedência normativa dos IDs locais:** Conforme registrado em `RESULTS.md:27-28`, os quatro IDs `local-*` dos briefings foram fornecidos com referências genéricas aos relatórios de origem e não constam na primeira coluna de tabelas estruturadas nesses arquivos (`prompts/orchestrator-perfis.md:242-245`). A conferência mecânica verificou exclusivamente que as respostas utilizaram identificadores pertencentes ao conjunto fornecido no briefing, sem comprovar a procedência normativa desses IDs. O experimento histórico é preservado como teste de consistência mecânica, sem constituir prova de conformidade integral da procedência.
- **Rastreabilidade e separação de saídas:** Respostas completas preservadas em `_tl-orc/project/evidence/T002-cases/resposta-*.json`; os arquivos `_tl-orc/project/evidence/T002-cases/check-*.txt` separam a saída literal de cada comando de conferência da interpretação analítica do Orquestrador.

---

## AC04: Delta Normativo Proposto em Rascunho

A introdução normativa do briefing mínimo é formulada como delta em rascunho dentro desta análise. **Nenhum arquivo distribuído do repositório foi alterado nesta Task**, preservando o congelamento do pacote. A aplicação efetiva destes textos caberá a uma Task do tipo `fix` com release autorizada pelo maintainer.

### 1. Proposta de Alteração em `prompts/orchestrator-perfis.md`

Na seção `## Briefing concreto` (atualmente linhas 215–232), substituir o texto por redação que torne mandatório o envio do esqueleto literal derivado do schema e remeta a regra de candidatos e integridade exclusivamente ao contrato do Classificador:

```markdown
## Briefing concreto

Forneça o caminho real do contrato dentro da **raiz do pacote** e a **raiz consumidora**
separadamente. Confira acesso aos dois. Para Planner, Maker e Checker, inclua:

- papel, resultado, modo autorizado e critério de parada;
- classificação versão 2, story, fase, revisões de contexto/catálogo/contrato, tier, harness,
  modelo, effort, família, evidências e base de custo;
- story/spec, decisões reservadas e estado base;
- árvore, caminhos de escrita permitidos, evidências e arquivos protegidos;
- portões, diretório de execução, recursos compartilhados e operações proibidas;
- para Checker, base, diff inteiro, critérios congelados, schema e grau de independência;
- no perfil Native, `spec_revision`, `content_id` e `content_paths` da Task, o perfil de
  verificação da spec e o conjunto inicial de contexto selecionado pelo
  [modelo de trabalho](../docs/WORK_MODEL.md#carregamento-e-envelhecimento): `CONTEXT.md`, índice,
  briefs das features afetadas e dependências diretas, unidade ativa e decisões referenciadas. O
  tipo da Task não entra no briefing do Classificador como sinal de tier.

O briefing entregue ao Classificador segue obrigatoriamente a estrutura do **briefing mínimo**,
contendo:
1. Procedência por entrada para story, fase, revisões, catálogo autorizado, pins, cadeias, autoria
   efetiva e evidências, conforme a tabela normativa abaixo;
2. O **esqueleto JSON literal** com todos os campos obrigatórios e enums do
   [schema](../schemas/classification-result.schema.json) para os papéis da fase, derivado
   diretamente do schema. É expressamente proibido substituir o esqueleto literal por descrição dos
   campos em prosa;
3. O bloco de regras de preenchimento dos candidatos por cadeia e fechamento obrigatório do JSON,
   conforme a prescrição normativa única em [classifier.md](classifier.md#resultado-obrigatório).
```

### 2. Proposta de Alteração em `prompts/classifier.md`

Na seção `## Entrada e limites` (linhas 21–33), incluir remissão ao briefing mínimo com esqueleto literal recebido:

```markdown
Receba um briefing compacto estruturado com procedência por entrada e o esqueleto JSON literal
mínimo derivado do schema para os papéis solicitados, conforme
[orchestrator-perfis.md](orchestrator-perfis.md#briefing-concreto).
```

Na seção de critérios (linhas 88–91), a regra mecânica de preenchimento de lacunas é substituída por remissão à prescrição normativa única em `## Resultado obrigatório`, preservando integralmente suas salvaguardas conceituais contra IDs inventados, defaults ocultos e confusão entre disponibilidade e capacidade:

```markdown
Se não houver par adequado e autorizado no catálogo para um harness, siga a regra de preenchimento
de lacuna em [Resultado obrigatório](#resultado-obrigatório). Nunca invente um ID, use default oculto
ou devolva um par insuficiente apenas para preencher a cadeia. Quota, autenticação e timeout são
disponibilidade; não reduzem a capacidade necessária do trabalho.
```

Na seção `## Resultado obrigatório` (linha 105), estabelecer o **texto normativo único** para a prescrição completa da regra de candidatos (um por harness na ordem da cadeia, inclusive inelegíveis com motivo, e preenchimento de lacunas com `model: null` e `effort: null`) e integridade do JSON:

```markdown
Para cada papel, informe tier, justificativa e os candidatos na ordem da cadeia recebida, exatamente
uma vez por harness, incluindo candidatos inelegíveis pela política vigente (que devem ser mantidos
na cadeia com o motivo da inelegibilidade explicitado no campo `reason`). Se não houver par adequado
e autorizado no catálogo para um harness, preencha `model: null` e `effort: null`, com a justificativa
da lacuna em `reason`. Responda exclusivamente com o objeto JSON íntegro, sem comentários, dados
adicionais fora da raiz ou truncamento.
```

### 3. Remoção de Dependência Operacional e Localização Distribuível Futura

O template de briefing desenvolvido e testado nesta Task reside em `_tl-orc/project/evidence/T002-briefing-template.md`. Conforme estabelece `CONTRIBUTING.md:9-14`, o diretório `_tl-orc/project/` é a área interna do método Native para este repositório e **não faz parte da distribuição**.

Para não introduzir nenhuma dependência de artefato interno em arquivos de pacote, o delta proposto acima elimina qualquer remissão a caminhos de `_tl-orc/project/evidence/`. A prescrição completa da regra de candidatos (um por harness na ordem da cadeia, inclusive inelegíveis com motivo, e preenchimento de lacunas com `model: null` e `effort: null`) foi unificada em um único destino normativo em `prompts/classifier.md#resultado-obrigatório`. A seção `prompts/orchestrator-perfis.md#briefing-concreto` contém exclusivamente remissão a esse destino único. A regra preexistente de lacunas em `prompts/classifier.md:88-91` foi tratada explicitamente no rascunho, substituindo a instrução mecânica duplicada por remissão a `#resultado-obrigatório` e preservando integralmente suas salvaguardas conceituais contra IDs inventados e defaults ocultos. A futura Task do tipo `fix` decidirá a localização distribuível definitiva do esqueleto/template mínimo (por exemplo, incorporando um exemplo mínimo ilustrativo diretamente na seção de briefing de `prompts/classifier.md` ou introduzindo um novo arquivo de template padronizado registrado no manifesto `distribution-manifest.json`). Quaisquer alterações em arquivos distribuídos, atualizações de manifesto e publicação de release permanecem estritamente fora do escopo desta entrega.

---

## AC05: Premissas, Alternativas Consideradas e Condições de Mudança

### Premissas Adotadas
1. **P1 (Economia do Classificador):** O Classificador deve permanecer como sessão rápida e barata (`Codex gpt-5.6-luna`, `effort: medium`), sem justificar elevação de custos ou tempos de resposta apenas para contornar ambiguidades sintáticas evitáveis na entrada.
2. **P2 (Sensibilidade à Estrutura na Entrada):** Modelos econômicos respondem com precisão estrutural quando recebem esqueletos gramaticais explícitos (com enums e listas delimitadas), mas tendem à inferência heurística solta quando instruídos puramente por linguagem natural.
3. **P3 (Prevenção vs. Correção):** A comparação literal dos briefings por contagem de caracteres (`wc -c`) demonstra que o briefing mínimo adiciona 6.586 caracteres (6.647 bytes: de 3.545 caracteres / 3.598 bytes em prosa para 10.131 caracteres / 10.245 bytes no mínimo). Assume-se a hipótese econômica não medida de que o custo computacional desse texto adicional de entrada é amplamente compensado pela prevenção de rodadas de correção via `resume` ou bloqueios operacionais decorrentes de respostas inválidas.

### Alternativas Consideradas

1. **Schema compacto discursivo com exemplo ilustrativo:**
   - *Descrição:* Descrever o schema em prosa e incluir um exemplo de resposta preenchida no briefing.
   - *Por que foi descartada:* A suposição de que exemplos com valores concretos induziriam o modelo a reproduzir valores do exemplo (ancoragem indevida de IDs, tiers ou justificativas) é uma hipótese qualitativa plausível, porém **não verificada** empiricamente (não houve medição comparativa entre briefing com exemplo e briefing com esqueleto na amostra $N = 3$). Optou-se preventivamente pelo esqueleto literal com placeholders (`<...>`) e enums disjuntos (`simple|normal|heavy`) para orientar a forma sem expor valores substantivos passíveis de ancoragem, rotulando-se a alternativa com exemplo como não verificada.

2. **Normalização flexível pelo Orquestrador pós-resposta:**
   - *Descrição:* Permitir que o Orquestrador repare pequenas imperfeições (ex: mapear `tier: "medium"` para `"normal"`, dividir `model: "codex/terra/high"` em campos separados).
   - *Por que foi descartada:* Violação frontal do princípio de validação independente e preservação da resposta canônica (`prompts/orchestrator-perfis.md:107-111`). Normalização heurística pelo Orquestrador reintroduz riscos de falsa interpretação e mascara defeitos de roteamento.

3. **Elevação do nível de esforço (`effort: high` ou `max`):**
   - *Descrição:* Aumentar o raciocínio de Luna para `high` ou `max` para que ele deduza o formato correto sem necessidade de esqueleto.
   - *Por que foi descartada:* Constitui hipótese não verificada supor que esforço maior resolveria ambiguidades de formato sem esqueleto. Além disso, a elevação de esforço de medium para high/max implicaria acréscimo de tempo e processamento cuja relação custo-benefício não foi medida comparativamente para esta tarefa; não há evidência empírica de que raciocínio prolongado deduza enums ausentes no briefing na ausência de especificação formal.

4. **Validação mecânica isolada pós-resposta:**
   - *Descrição:* Manter o briefing em prosa e confiar apenas na rejeição pela camada mecânica.
   - *Por que foi descartada:* A validação mecânica é indispensável como guarda de integridade, mas, isolada, apenas detecta o erro e bloqueia o processo (como ocorreu em v0.6.0). A combinação sinérgica é: *Briefing Mínimo na entrada* (para maximizar acerto na 1ª chamada) + *Validação Mecânica na saída* (para garantir conformidade absoluta).

### O que Mudaria a Conclusão (Condições de Revisão)

No experimento controlado de AC03 (`_tl-orc/project/evidence/T002-cases/RESULTS.md:1-31`), a hipótese de desempenho equivalente produziu 0/3 primeiras respostas válidas no estilo em prosa (com 2 fechamentos prematuros seguidos de dados extras e 1 resposta com estrutura e enums inválidos) contra 3/3 respostas válidas na primeira tentativa com o briefing mínimo. Registra-se que esse resultado expressa estritamente o comportamento observado na amostra testada ($N = 3$, um modelo, uma intenção, um catálogo) e que o teste alterou conjuntamente o esqueleto e as regras fixas, sem isolar os dois fatores nem estabelecer taxas populacionais universais.

Permanece como cenário que alteraria a conclusão ou tornaria o briefing mínimo desnecessário:
1. **Comparação empírica ampliada com desempenho equivalente:** Se medições futuras com amostras estatisticamente amplas ($N \gg 3$) ou em outras tarefas/fases demonstrarem que o briefing discursivo em prosa atinge taxa de validade de primeira resposta equivalente ao briefing mínimo, ou se revelarem que o esqueleto literal induz algum tipo de degradação semântica não observada na amostra $N = 3$ (por exemplo, viés de confirmação no preenchimento de campos ou engessamento na análise de incertezas);
2. **Evolução de modelos econômicos (fine-tuning ou novas gerações):** Se versões futuras de modelos de classe econômica passarem a inferir consistentemente a gramática e os enums exatos de esquemas complexos a partir de descrições discursivas soltas na primeira chamada, dispensando o esqueleto estruturado;
3. **Degradação qualitativa de raciocínio comprovada:** Se testes cegos qualitativos evidenciarem que o fornecimento do esqueleto literal restringe a profundidade argumentativa nos campos livres (`reason`, `uncertainties`, `facts`) em comparação a briefings livres;
4. **Restrições extremas de janela de contexto:** Se cenários operacionais específicos impuserem orçamentos de contexto tão exíguos que o acréscimo medido de 6.586 caracteres do esqueleto literal e do bloco de regras fixas se torne proibitivo.

---

## AC06: Portões de Verificação e Evidências Técnicas

1. **Validador do Repositório:**
   - Comando: `python3 scripts/validate_repository.py`
   - Resultado: Executado com saída `OK: 17 package files; JSON, frontmatter, links, export and hashes validated` (exit code 0).
   - `scripts/__pycache__` removido após a execução.
2. **Integridade de Escrita:**
   - Nenhum arquivo distribuído foi modificado (`prompts/`, `schemas/`, `docs/`, `SKILL.md`, `scripts/`, `_tl-orc/PROJECT.md` permanecem intocados).
   - Escrita restrita estritamente aos caminhos autorizados da Task Native em `_tl-orc/project/evidence/`.
3. **Ausência de Caminhos Privados:**
   - Todos os artefatos gerados utilizam caminhos relativos ou canônicos do repositório, sem exposição de diretórios de máquina ou dados de ambiente.
4. **Protótipo Executável e Contraprovas:**
   - O comando de validação do protótipo executa com código 0 e sem dependências externas:
     ```sh
     python3 _tl-orc/project/evidence/T002-briefing-skeleton.py schemas/classification-result.schema.json --roles planner,maker,checker
     ```
   - Compatibilidade verificada também com as variantes `--roles planner,maker,checker,searcher`, `--roles searcher` e `--chain`.
   - Contraprovas mecânicas executadas com schemas temporários em `$TMPDIR`:
     - *(i) required desconhecido na raiz:* adição de `"required_probe"` ao array `required` da raiz interrompe com código 1 e `Schema não suportado: campos obrigatórios desconhecidos na raiz: ['required_probe']`;
     - *(ii) effort removido:* remoção de `effort` de `properties` e `required` em `$defs/candidate` interrompe com código 1 e `Schema não suportado: campos obrigatórios esperados ausentes em $defs/candidate: ['effort']` (e se removido apenas de properties, `propriedades esperadas ausentes em $defs/candidate: ['effort']`);
     - *(iii) null removido do enum:* remoção de `null` do enum de `effort` em `$defs/candidate` executa com código 0 e emite `effort` sem `|null` (`"effort": "none|minimal|low|medium|high|xhigh|max|ultra"`).
5. **Comandos de Reprodução da Medição e Conferência Mecânica:**
   Conforme documentado em `_tl-orc/project/evidence/T002-cases/RESULTS.md:14-25` e `_tl-orc/project/evidence/T002-cases/README.md:38-48`, distingue-se a **reprodução da conferência** sobre respostas preservadas de uma **nova medição**:
   - *Reprodução da conferência:* Executada a partir da raiz do repositório fonte sobre os arquivos preservados em `T002-cases/resposta-*.json`, sem chamadas pagas e sem acesso à rede, utilizando as ferramentas preservadas em `T002-cases/tools/`:
     ```bash
     python3 _tl-orc/project/evidence/T002-cases/tools/check_struct.py schemas/classification-result.schema.json _tl-orc/project/evidence/T002-cases/resposta-<prosa|minimo>-<N>.json
     python3 _tl-orc/project/evidence/T002-cases/tools/mech_check.py _tl-orc/project/evidence/T002-cases/resposta-<prosa|minimo>-<N>.json _tl-orc/project/evidence/T002-cases/tools/expected-medicao.json
     ```
   - *Nova medição empírica:* Exigiria a realização de 6 novas chamadas pagas via CLI do Codex (`codex exec`) em sandbox read-only, enviando cada um dos briefings (`briefing-*.md`) via entrada padrão (`RESULTS.md:17-19`), o que não se confunde com a simples verificação mecânica das respostas canônicas existentes.
