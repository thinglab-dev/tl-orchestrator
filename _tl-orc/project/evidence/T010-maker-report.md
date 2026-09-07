unit: native/task/T010@_tl-orc/project/tasks/T010-regras-de-conducao-origem-limites-e-escalonamento.md
kind: relatório do Maker (resposta final literal; dado, não prova)
content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:2f0806717632e1df

## Rodada r01 — Maker agy gemini-3.8-flash-high (20260907T224035Z → 20260907T224347Z, exit 0), em worktree dedicado (branch fix/t010-conduction-rules)

### Tabela Coverage AC01–AC06

| Critério | Arquivo:Linhas | Frase Decisiva |
| :--- | :--- | :--- |
| **AC01** (Escalonamento consultivo) | [prompts/orchestrator-perfis.md:L183-188](prompts/orchestrator-perfis.md#L183-L188) | `"Após N rodadas de rework (N padrão 3; o consumidor pode fixar outro valor em \`PROJECT.md\`) em que o Checker aponte achados centrais da mesma classe, o Orquestrador classifica uma fase consultiva (fase \`debate\`, papéis conforme o risco) e despacha um consultor com a pergunta \"estamos corrigindo manifestações do mesmo problema ou descobrindo requisitos que precisam ser consolidados antes de continuar?\". A orientação é consolidada (spec, abordagem ou critérios) antes de classificar outro rework; correções delimitadas seguem o fluxo normal."` |
| **AC02** (Origem por tipo) | [prompts/orchestrator-perfis.md:L228-234](prompts/orchestrator-perfis.md#L228-L234) | `"Cada informação do briefing declara a fonte do seu tipo: catálogo e pins da política autorizada do consumidor; tarefa, \`story_id\`, fase e papéis da solicitação ou spec; autoria efetiva e disponibilidade dos runs efetivos registrados; evidências dos registros identificados (cartões e tabelas de [MODEL_ROUTING.md](../docs/MODEL_ROUTING.md), medições locais com ID e localização). Listas compostas na hora ou fontes genéricas como \"um arquivo existente\" não valem como origem e são rejeitadas; o Classificador só recebe IDs com origem. Fontes externas às raízes informadas só podem ser consultadas se constarem explicitamente no briefing."` |
| **AC03** (Limite das provas mecânicas) | [prompts/orchestrator-playbook.md:L260-262](prompts/orchestrator-playbook.md#L260-L262) | `"Conferência mecânica e vinculação por hash comprovam correspondência e integridade (o objeto e as entradas conferidos são estes), não correção nem pertinência; pertinência ao workload, adequação do esforço e alcance econômico são julgamento registrado, com quem julgou e sobre o quê."` |
| **AC04** (Escopo de leitura) | [prompts/checker-report-only.md:L5-6](prompts/checker-report-only.md#L5-L6)<br>[prompts/orchestrator.md:L87-90](prompts/orchestrator.md#L87-L90) | `"Leia apenas a raiz consumidora e a raiz do pacote informadas; outra fonte só se constar explicitamente no briefing; leitura fora desse escopo é desvio a declarar no parecer."`<br>`"- **Escopo de leitura:** todos os papéis despachados leem somente a raiz consumidora e a raiz do pacote informadas; qualquer outra fonte exige autorização explícita no [briefing concreto](orchestrator-perfis.md#briefing-concreto). Leitura fora desse escopo é desvio a declarar no parecer ou relatório, conforme o [contrato do Checker](checker-report-only.md)."` |
| **AC05** (Coerência) | [prompts/orchestrator-perfis.md:L183-188](prompts/orchestrator-perfis.md#L183-L188)<br>[prompts/orchestrator.md:L87-90](prompts/orchestrator.md#L87-L90) | Nenhuma contradição introduzida: reclassificação por fase preservada (`"classifica uma fase consultiva (fase \`debate\`, papéis conforme o risco)"` e `"antes de classificar outro rework"`); regra de escolha de modelo pelo Classificador preservada (`"o Classificador só recebe IDs com origem"`); independência preferred/required intacta; escopos de T007 e T008 inalterados; nenhum outro arquivo foi modificado. |
| **AC06** (Portões, CHANGELOG e Sondas) | [CHANGELOG.md:L7-22](CHANGELOG.md#L7-L22) | Portão do repositório verde (exit 0); manifesto e schemas inalterados; [CHANGELOG.md](CHANGELOG.md) em `## [Unreleased]` sob `### Corrigido` descrevendo as quatro regras em termos do método sem nomes de ferramentas ou autoria; sondas resolvidas pelas frases normativas. |

---

### Âncoras novas e links que as usam

- **Âncoras novas:** Nenhuma âncora nova foi criada, preservando a regra de não fragmentar títulos normativos e manter mudanças mínimas.
- **Links com âncoras e arquivos existentes utilizados:**
  - Em [prompts/orchestrator.md:L89](prompts/orchestrator.md#L89): link `[briefing concreto](orchestrator-perfis.md#briefing-concreto)` remete à âncora existente `#briefing-concreto` em [prompts/orchestrator-perfis.md](prompts/orchestrator-perfis.md).
  - Em [prompts/orchestrator.md:L90](prompts/orchestrator.md#L90): link `[contrato do Checker](checker-report-only.md)` remete ao arquivo canônico [prompts/checker-report-only.md](prompts/checker-report-only.md).
  - Em [prompts/orchestrator-perfis.md:L231](prompts/orchestrator-perfis.md#L231): link `[MODEL_ROUTING.md](../docs/MODEL_ROUTING.md)` remete ao catálogo de evidências existente.

---

### Saída literal do validador e exit

**Comando:** `python3 scripts/validate_repository.py`  
**Exit code:** `0`  
**Saída:**
```text
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```

---

### Sondas de AC06

- **(a) Briefing com origem genérica → o texto o rejeita:**  
  Decidida por [prompts/orchestrator-perfis.md:L232-233](prompts/orchestrator-perfis.md#L232-L233):  
  `"Listas compostas na hora ou fontes genéricas como \"um arquivo existente\" não valem como origem e são rejeitadas; o Classificador só recebe IDs com origem."`

- **(b) Quarto rework com achado da mesma classe → o texto manda escalar:**  
  Decidida por [prompts/orchestrator-perfis.md:L183-188](prompts/orchestrator-perfis.md#L183-L188):  
  `"Após N rodadas de rework (N padrão 3; o consumidor pode fixar outro valor em \`PROJECT.md\`) em que o Checker aponte achados centrais da mesma classe, o Orquestrador classifica uma fase consultiva (fase \`debate\`, papéis conforme o risco) e despacha um consultor com a pergunta \"estamos corrigindo manifestações do mesmo problema ou descobrindo requisitos que precisam ser consolidados antes de continuar?\". A orientação é consolidada (spec, abordagem ou critérios) antes de classificar outro rework; correções delimitadas seguem o fluxo normal."`

- **(c) Checker que leu fora da raiz sem autorização → o texto manda declarar desvio:**  
  Decidida por [prompts/checker-report-only.md:L5-6](prompts/checker-report-only.md#L5-L6) (e reiterada em [prompts/orchestrator.md:L89-90](prompts/orchestrator.md#L89-L90)):  
  `"Leia apenas a raiz consumidora e a raiz do pacote informadas; outra fonte só se constar explicitamente no briefing; leitura fora desse escopo é desvio a declarar no parecer."`

---

### O que ficou fora ou incerto

- Nada ficou fora ou incerto.
- Todas as quatro regras normativas foram inseridas exclusivamente nos 5 arquivos autorizados, mantendo texto normativo único por assunto, sem menção a ferramentas específicas ou autoria em [CHANGELOG.md](CHANGELOG.md), e nenhum commit Git foi executado.

## Conferência do Orquestrador sobre r01
Integridade: só os cinco caminhos permitidos alterados; nenhum arquivo novo; validador exit 0; 48 inserções e 6 exclusões; texto normativo único por assunto com remissões (orchestrator.md invariante → briefing concreto e contrato do Checker); leitura própria do diff sem defeito encontrado. content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:2f0806717632e1df.

## Rework 1 — Maker agy gemini-3.8-flash-high (20260907T225232Z → 20260907T225409Z, exit 0), fase rework classificada (T010-r02-classifier-1)

### Arquivo e Linha

[prompts/orchestrator-perfis.md:233-234](prompts/orchestrator-perfis.md#L233-L234)

**Frase resultante:**
> A autorização de fontes além das raízes informadas segue o [escopo de leitura](orchestrator.md#invariantes).

Parágrafo completo resultante ([prompts/orchestrator-perfis.md:228-234](prompts/orchestrator-perfis.md#L228-L234)):
```markdown
Cada informação do briefing declara a fonte do seu tipo: catálogo e pins da política autorizada do
consumidor; tarefa, `story_id`, fase e papéis da solicitação ou spec; autoria efetiva e
disponibilidade dos runs efetivos registrados; evidências dos registros identificados (cartões e
tabelas de [MODEL_ROUTING.md](../docs/MODEL_ROUTING.md), medições locais com ID e localização).
Listas compostas na hora ou fontes genéricas como "um arquivo existente" não valem como origem e
são rejeitadas; o Classificador só recebe IDs com origem. A autorização de fontes além das raízes
informadas segue o [escopo de leitura](orchestrator.md#invariantes).
```

---

### Saída Literal do Validador

**Comando:** `python3 scripts/validate_repository.py`  
**Exit code:** `0`  
**Saída:**
```text
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```

---

### Confirmação de Integridade

Confirmo que:
- Nenhuma outra alteração foi feita em [prompts/orchestrator-perfis.md](prompts/orchestrator-perfis.md). O restante do parágrafo (origem por tipo, rejeição de listas compostas na hora e entrega ao Classificador apenas de IDs com origem) foi preservado integralmente.
- Nenhum outro arquivo do repositório foi alterado.
- Nenhum comando git ou de rede foi executado e nenhum commit foi realizado.

## Conferência do Orquestrador sobre o rework 1
Só prompts/orchestrator-perfis.md alterado; frase repetida substituída por remissão a orchestrator.md#invariantes; validador exit 0. content_id r02: 0de10d60149cf7c038a0954c6aec302c9fcd111e:cb481171771a7e47.

## Rework 2 — Maker agy gemini-3.8-flash-high (20260907T230139Z → 20260907T230410Z, exit 0), spec s2, fase classificada (T010-r03-classifier-1)

### Arquivo:linhas alterados

- [`prompts/orchestrator-perfis.md:L228-244`](prompts/orchestrator-perfis.md#L228-L244) (substituiu linhas 228-234 anteriores): introdução ajustada sem redundância, tabela normativa de procedência em 3 colunas com os 6 tipos ordenados, frase normativa pós-tabela (localização que resolve não basta; fonte existente mas incompatível com o tipo ou valor é rejeitada) e preservação da regra de listas compostas na hora / escopo de leitura.
- [`CHANGELOG.md:L9-26`](CHANGELOG.md#L9-L26) (substituiu linhas 9-22 anteriores): complementação da entrada de `Unreleased` com a tabela normativa de procedência por tipo e conteúdo sustentado, sem citar ferramentas nem autoria.

---

### Tabela resultante

| Tipo de informação | Fonte autorizada | Conteúdo que sustenta o valor e conferência |
| :--- | :--- | :--- |
| `story_id`, fase e papéis solicitados | solicitação ou spec da Task/fase | o registro citado contém o valor literal |
| catálogo (harness/modelo/effort), pins e cadeias | política autorizada do consumidor (PROJECT.md) | a tabela ou seção cita exatamente o par, o pin ou a cadeia |
| autoria efetiva e famílias | registro de `Agent runs` efetivo | a linha citada declara harness, modelo e família usados |
| evidências de custo e capacidade | [docs/MODEL_ROUTING.md](../docs/MODEL_ROUTING.md) | pertinência ao modelo e, para proxy de custo, afirmação de custo por tarefa no cartão |
| medição local | linha de tabela estruturada em evidência do projeto | ID na primeira coluna |
| julgamento | registro documental vinculado por hash ao objeto e às entradas | hash coincide e veredito explícito |

---

### Saída literal do validador com exit

Comando executado:
```sh
python3 scripts/validate_repository.py
```

Exit code: `0`

Saída:
```text
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```

---

### Sondas por leitura

- **(a) Fonte que existe mas não contém o valor → a tabela/frase a rejeita**:
  A frase normativa logo após a tabela determina: *"Localização que resolve (arquivo existe, âncora resolve, linha existe) não basta; fonte existente mas incompatível com o tipo ou com o valor é rejeitada."* Combinada com a terceira coluna da tabela (*"Conteúdo que sustenta o valor e conferência"*), que exige sustentação estrita (valor literal citado, citação exata de par/pin/cadeia, linha declarando harness/modelo/família, afirmação de custo por tarefa no cartão, ID na primeira coluna, hash coincidente com veredito explícito), qualquer fonte cuja localização resolva mas cujo conteúdo não contenha o valor alegado é sumariamente rejeitada.

- **(b) Papéis solicitados apontando para PROJECT.md em vez da solicitação → rejeitado pelo tipo**:
  Conforme a linha 1 da tabela, a fonte autorizada para `story_id`, fase e papéis solicitados é unicamente a *"solicitação ou spec da Task/fase"*. A política do consumidor (`PROJECT.md`) é fonte autorizada apenas para *"catálogo (harness/modelo/effort), pins e cadeias"* (linha 2). Pela regra normativa de que *"fonte existente mas incompatível com o tipo ou com o valor é rejeitada"*, apontar `PROJECT.md` para papéis solicitados viola a tipagem da procedência e é rejeitado por incompatibilidade de tipo.

---

### Confirmação de integridade

- Nenhum outro trecho ou arquivo foi alterado além das linhas especificadas em [`prompts/orchestrator-perfis.md`](prompts/orchestrator-perfis.md) e [`CHANGELOG.md`](CHANGELOG.md).
- Nenhum comando git ou de rede foi executado.
- Nenhum commit foi realizado.

## Conferência do Orquestrador sobre o rework 2
Só orchestrator-perfis.md e CHANGELOG.md alterados; tabela com os seis tipos na ordem da spec; frase normativa sobre localização insuficiente; validador exit 0. content_id r03: 0de10d60149cf7c038a0954c6aec302c9fcd111e:bea29257fea4b474.
