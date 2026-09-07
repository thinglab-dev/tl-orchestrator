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

## Rework 3 — Maker agy gemini-3.8-flash-high (20260907T232728Z → 20260907T233056Z, exit 0), spec s3, fase classificada (T010-r04-classifier-1)

### Alterações Implementadas

#### [R1] Precedência de fontes de política e catálogo montado
- **Arquivo e linhas**: [`prompts/orchestrator-perfis.md:234`](prompts/orchestrator-perfis.md#L234) e [`prompts/orchestrator-perfis.md:243-245`](prompts/orchestrator-perfis.md#L243-L245)
- **Frases resultantes**:
  - Na tabela de procedência ([linha 234](prompts/orchestrator-perfis.md#L234)):
    ```markdown
    | catálogo (harness/modelo/effort), pins e cadeias | fontes de política conforme a [precedência vigente](#perfil-padrão) (instrução atual do usuário registrada; configuração do consumidor em `PROJECT.md`; ou o perfil publicado quando não há configuração local) | o registro citado cita exatamente o par, o pin ou a cadeia |
    ```
  - No texto normativo pós-tabela ([linhas 243–245](prompts/orchestrator-perfis.md#L243-L245)):
    ```markdown
    Um catálogo montado para a chamada é legítimo quando cada entrada deriva de uma dessas fontes com procedência verificável; rejeita-se a entrada sem procedência, não o catálogo montado; isso preserva projetos sem perfil persistido.
    ```

---

#### [R2(a)] Searcher classificado em perfis
- **Arquivo e linhas**: [`prompts/orchestrator-perfis.md:8-13`](prompts/orchestrator-perfis.md#L8-L13)
- **Frase resultante**:
  ```markdown
  O Searcher é auxiliar de consulta. Quando necessário, use sessão nova: o Searcher recebe modelo e
  effort da classificação da fase (papel auxiliar searcher, sem tier de trabalho) ou de pin explícito
  do usuário ou do consumidor, ainda assim passado ao Classificador como restrição. A classificação da
  fase cobre as buscas daquela fase (não se reclassifica a cada busca). O Searcher não decide,
  implementa, aprova ou despacha, e devolve apenas o resumo verificável previsto em
  [seu contrato](searcher.md). Busca trivial direta continua sem agente.
  ```

---

#### [R2(b)] Searcher classificado no contrato do Orquestrador e exceção restrita ao Classificador
- **Arquivo e linhas**: [`prompts/orchestrator.md:35-37`](prompts/orchestrator.md#L35-L37) e [`prompts/orchestrator.md:46-54`](prompts/orchestrator.md#L46-L54)
- **Frases resultantes**:
  - Invariante de seleção ([linhas 35–37](prompts/orchestrator.md#L35-L37)):
    ```markdown
    **Ele nunca escolhe modelo ou effort de Planner, Maker, Checker ou Searcher por conta própria, por sugestão da conversa ou por conveniência:** em toda fase (`debate`, `planning`, `implementation`, `review`, `rework`), antes do primeiro despacho de cada papel, obtém e valida uma classificação da fase.
    ```
  - Regra de despacho sob demanda e contexto prévio ([linhas 46–54](prompts/orchestrator.md#L46-L54)):
    ```markdown
    O Searcher sob demanda também depende de classificação da fase ou de pin explícito: a única
    exceção de inicialização com perfil fixo é a do próprio Classificador (perfil fixo em
    [Perfil-padrão](orchestrator-perfis.md#perfil-padrão)). Quando uma pergunta exigir contexto antes de
    qualquer classificação, a primeira classificação da fase inclui o papel `searcher`. O Searcher é
    despachado em nova sessão, conforme [seu contrato](searcher.md). Confira o envelope e os erros do
    harness, a cobertura real e o estado de acesso: saída vazia ou consulta negada é bloqueada, não
    sucesso, e não exige que o Searcher tente responder sem acesso. O resumo orienta a decisão, mas não
    substitui leitura obrigatória, fontes críticas ou revisão independente; a classificação da fase
    cobre as buscas daquela fase, sem reclassificar a cada busca.
    ```

---

#### [R2(c)] Resolução do perfil no contrato do Searcher
- **Arquivo e linhas**: [`prompts/searcher.md:4-6`](prompts/searcher.md#L4-L6)
- **Frase resultante**:
  ```markdown
  É um auxiliar sob demanda, em sessão nova e separada, com modelo e effort resolvidos pelo
  Orquestrador a partir da classificação da fase ou de pin explícito. Busca trivial direta não exige
  Searcher.
  ```

---

#### [R2(d)] Admissão aditiva da propriedade opcional `searcher` no schema
- **Arquivo e linhas**: [`schemas/classification-result.schema.json:80-93`](schemas/classification-result.schema.json#L80-L93)
- **Trecho resultante**:
  ```json
        "properties": {
          "planner": {
            "$ref": "#/$defs/role"
          },
          "maker": {
            "$ref": "#/$defs/role"
          },
          "checker": {
            "$ref": "#/$defs/role"
          },
          "searcher": {
            "$ref": "#/$defs/role"
          }
        }
  ```

---

#### [R2(e)] Registro no CHANGELOG (Unreleased)
- **Arquivo e linhas**: [`CHANGELOG.md:14-20`](CHANGELOG.md#L14-L20) e [`CHANGELOG.md:28-33`](CHANGELOG.md#L28-L33)
- **Frases resultantes**:
  ```markdown
  catálogo, pins e cadeias de fontes de política conforme a precedência vigente — instrução atual do usuário registrada, configuração do consumidor em `PROJECT.md` ou perfil publicado na ausência de configuração local —, legitimando catálogo montado para a chamada quando cada entrada tem procedência verificável e rejeitando a entrada sem procedência, preservando projetos sem perfil persistido;
  ```
  ```markdown
  Searcher classificado sob demanda recebendo modelo e effort da classificação da fase (papel auxiliar `searcher`, sem tier de trabalho) ou de pin explícito passado como restrição, cobrindo as buscas daquela fase sem reclassificar a cada consulta, e tornando explícito que a única exceção de inicialização com perfil fixo é a do próprio Classificador; e admissão aditiva da propriedade opcional `searcher` em `roles` no schema de resultado de classificação (versão 2 mantida).
  ```

---

### Saída Literal do Validador

```
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```
Exit code: `0`

Validação sintática do schema (`python3 -c "import json; json.load(open('schemas/classification-result.schema.json'))"`): exit code `0`.

---

### Sondas por Leitura

- **(h) Catálogo montado para a chamada com entradas derivadas de `PROJECT.md` e do perfil publicado → aceito; entrada sem procedência → rejeitada**:
  Em [`prompts/orchestrator-perfis.md:243-245`](prompts/orchestrator-perfis.md#L243-L245), o texto define: *"Um catálogo montado para a chamada é legítimo quando cada entrada deriva de uma dessas fontes com procedência verificável; rejeita-se a entrada sem procedência, não o catálogo montado; isso preserva projetos sem perfil persistido."* Como tanto `PROJECT.md` quanto o perfil publicado são fontes de política autorizadas na precedência vigente, entradas derivadas de ambas possuem procedência verificável e são aceitas; entradas sem procedência são rejeitadas isoladamente sem invalidar o catálogo montado.

- **(i) Despacho do Searcher sem classificação nem pin → o texto o proíbe**:
  Em [`prompts/orchestrator.md:35-37`](prompts/orchestrator.md#L35-L37), veda-se expressamente: *"Ele nunca escolhe modelo ou effort de Planner, Maker, Checker ou Searcher por conta própria, por sugestão da conversa ou por conveniência: em toda fase (...), antes do primeiro despacho de cada papel, obtém e valida uma classificação da fase."* Complementado em [`prompts/orchestrator.md:46-48`](prompts/orchestrator.md#L46-L48): *"O Searcher sob demanda também depende de classificação da fase ou de pin explícito: a única exceção de inicialização com perfil fixo é a do próprio Classificador"*. Logo, despachar o Searcher sem classificação prévia nem pin explícito é terminantemente proibido.

- **(j) Perfil fixo do Classificador → continua permitido explicitamente**:
  Em [`prompts/orchestrator.md:46-48`](prompts/orchestrator.md#L46-L48), declara-se que *"a única exceção de inicialização com perfil fixo é a do próprio Classificador (perfil fixo em [Perfil-padrão](orchestrator-perfis.md#perfil-padrão))"*, mantendo a tabela de cadeia fixa do Classificador integralmente válida em [`prompts/orchestrator-perfis.md:20-27`](prompts/orchestrator-perfis.md#L20-L27).

---

### Confirmações de Confinamento

- Nenhum outro arquivo do repositório foi alterado (inclusive [`distribution-manifest.json`](distribution-manifest.json), mantido com 17 arquivos intactos).
- Nenhum commit foi realizado.

## Conferência do Orquestrador sobre o rework 3
Cinco arquivos alterados dentro do escopo (perfis, orchestrator, searcher, schema, CHANGELOG); schema aditivo (roles ganha searcher com a mesma estrutura de planner; additionalProperties false mantido; schema_version 2); validador exit 0. Diff sobre o commit publicado 4ede3a982a12cee02cc7e652b6e43c4a60c0de92. content_id r04: 4ede3a982a12cee02cc7e652b6e43c4a60c0de92:ff5682a1b25963bc.

## Rework 4 — Maker agy gemini-3.8-flash-high (20260907T234014Z → 20260907T234535Z, exit 0), spec s4, fase classificada (T010-r05-classifier-1)

### Alterações Realizadas (R1–R3)

#### R1 — [`prompts/classifier.md:12-17`](prompts/classifier.md#L12-L17)
```markdown
O papel searcher pode ser solicitado sozinho ou junto dos demais em `requested_roles`. Quando
solicitado, recebe a mesma estrutura dos outros papéis (tier, reason, candidates com
harness/modelo/effort/evidence_ids/cost_basis/reason, um candidato por harness na ordem da cadeia
informada); a semântica do tier para o Searcher é o dimensionamento da consulta (abrangência, risco
de fonte e custo da busca), não um tier de trabalho; pins e restrições valem igualmente. Sua
consulta segue [searcher.md](searcher.md).
```

#### R2 — [`prompts/orchestrator-perfis.md:8-11`](prompts/orchestrator-perfis.md#L8-L11)
```markdown
O Searcher é auxiliar de consulta. Quando necessário, use sessão nova: o Searcher recebe modelo e
effort da classificação da fase (papel auxiliar searcher, que usa a mesma estrutura dos demais
papéis e cujo tier dimensiona a consulta) ou de pin explícito do usuário ou do consumidor, ainda assim
passado ao Classificador como restrição. A classificação da
```
- **[`prompts/orchestrator.md:46-55`](prompts/orchestrator.md#L46-L55)**: no parágrafo do Searcher sob demanda, conferido que nada afirma ausência de tier.
- **[`schemas/classification-result.schema.json:90-92`](schemas/classification-result.schema.json#L90-L92)**: a propriedade `roles.searcher` já referencia `"$ref": "#/$defs/role"`; mantida inalterada conforme instrução.

#### R3 — [`CHANGELOG.md:22-24`](CHANGELOG.md#L22-L24) e [`CHANGELOG.md:33-35`](CHANGELOG.md#L33-L35)
Lines 22–24:
```markdown
  rejeitando fonte incompatível com o tipo ou com o valor, além de rejeitar listas compostas na hora
  sem procedência por entrada ou fontes genéricas como "um arquivo existente", com entrega ao
  Classificador apenas de IDs com origem;
```
Lines 33–35:
```markdown
  admissão aditiva da propriedade opcional `searcher` em `roles` no schema de
  resultado de classificação (versão 2 mantida); e contrato do Classificador que passa a admitir o
  papel searcher com tier de consulta.
```

---

### Validação

#### `python3 scripts/validate_repository.py`
Exit code: `0`
Saída literal:
```text
OK: 17 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```

#### `python3 -c "import json; json.load(open('schemas/classification-result.schema.json'))"`
Exit code: `0` (JSON do schema válido e sem erros de sintaxe).

---

### Sondas por Leitura

- **(l) `requested_roles` com `["searcher"]` sozinho**:
  O contrato em [`prompts/classifier.md:12`](prompts/classifier.md#L12) aceita o papel isoladamente:
  > *"O papel searcher pode ser solicitado sozinho ou junto dos demais em `requested_roles`."*

- **(m) `requested_roles` com `searcher` e pin de modelo**:
  O contrato em [`prompts/classifier.md:16`](prompts/classifier.md#L16) estabelece que o pin é restrição e não dispensa a classificação:
  > *"pins e restrições valem igualmente."*
  Alinhado a [`prompts/orchestrator.md:41-42`](prompts/orchestrator.md#L41-L42) (*"Mesmo com pin, o Classificador é chamado com o pin como restrição"*) e a [`prompts/orchestrator-perfis.md:10-11`](prompts/orchestrator-perfis.md#L10-L11) (*"ou de pin explícito do usuário ou do consumidor, ainda assim passado ao Classificador como restrição"*).

- **(n) Tier do Searcher definido como dimensionamento da consulta**:
  O contrato em [`prompts/classifier.md:15-16`](prompts/classifier.md#L15-L16) define explicitamente a semântica:
  > *"a semântica do tier para o Searcher é o dimensionamento da consulta (abrangência, risco de fonte e custo da busca), não um tier de trabalho;"*
  Alinhado a [`prompts/orchestrator-perfis.md:9-10`](prompts/orchestrator-perfis.md#L9-L10) (*"que usa a mesma estrutura dos demais papéis e cujo tier dimensiona a consulta"*).

---

### Confirmação de Escopo e Integridade
- **Nenhum outro trecho ou arquivo foi alterado**: somente os trechos especificados em [`prompts/classifier.md`](prompts/classifier.md), [`prompts/orchestrator-perfis.md`](prompts/orchestrator-perfis.md) e [`CHANGELOG.md`](CHANGELOG.md) foram editados; [`prompts/orchestrator.md`](prompts/orchestrator.md), [`prompts/searcher.md`](prompts/searcher.md) e [`schemas/classification-result.schema.json`](schemas/classification-result.schema.json) permaneceram inalterados.
- Nenhum arquivo de relatório foi criado e nenhum comando `git` foi executado.

## Conferência do Orquestrador sobre o rework 4
classifier.md, orchestrator-perfis.md e CHANGELOG.md alterados; exclusão do Searcher removida e tier de consulta definido; validador exit 0; schema JSON válido. Resíduo corrigido pelo Orquestrador (correção própria, autoria Anthropic declarada): a frase "sem tier de trabalho" permanecia no CHANGELOG, contra o R2; substituída por "com a mesma estrutura dos demais papéis e tier que dimensiona a consulta"; quebra de linha em perfis ajustada. content_id r05: 4ede3a982a12cee02cc7e652b6e43c4a60c0de92:f38196879c99d34f.

## Correção própria do Orquestrador após r05 (autoria Anthropic, declarada)
prompts/orchestrator-playbook.md: seção Searcher sob demanda condicionada à classificação prévia ou pin, com remissão aos perfis, e enumeração de papéis classificados incluindo o Searcher; validador exit 0. content_id r06: 4ede3a982a12cee02cc7e652b6e43c4a60c0de92:21768d877bbc9055.
