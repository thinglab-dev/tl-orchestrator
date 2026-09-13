# Decisão Beta

Conferi diretamente todas as fontes apontadas. Segue a avaliação formal, o encaminhamento proposto e o briefing. **Nada foi escrito em disco e nenhum agente foi despachado** (modo somente leitura).

---

# 1. Conferência das fontes (não-tautologia)

Inspecionei por leitura direta: a Task, o parecer r02 íntegro, `PROJECT.md`, os três contratos do Orquestrador, `maker.md`/`checker-report-only.md` (índice), `MODEL_ROUTING.md`, `STATUS.md`, a análise, o protótipo nas linhas citadas e os casos do piloto.

> **Limitação declarada:** não disponho de ferramenta de execução nesta sessão; **não recalculei os SHA-256** da tabela do Pacote de Retomada. A conferência foi por **conteúdo**, não por hash. Isso não invalida nada abaixo — todos os achados foram reproduzidos por leitura do código-fonte real.

## 1.1 Os cinco achados procedem — verificação independente

| # | Localização **oficial** (parecer) | Verifiquei em | Procede? |
| :--- | :--- | :--- | :--- |
| R1 | `T009-mechanical-check.py:130` | `:130-141` — `_strip_anchor_and_line()` **descarta** âncora/linha; checa só `filepath.exists()`; depois `if id_val not in file_text` sobre o arquivo **inteiro** | **Sim.** Âncora inexistente e linha inexistente passam; `local-fake` existe literalmente no próprio protótipo em `:671` (`bad_bare_list`), como exemplo negativo |
| R2 | `T009-mechanical-check.py:78` | `:78` — regex `\bcusto\b[^\n]{0,50}\btarefa\|\bpor\s+tarefa\b`. A **segunda alternativa é isolada** e casa com `astra-domain` (`MODEL_ROUTING.md:55-56`: "latência **simulada**… 40/75 **minutos por tarefa**"), cujo próprio cartão diz em `:57-58` "Não extrapolar" | **Sim.** `astra-coding` (`:47-48`, "custo API estimado por tarefa cerca de 9% menor") é o único cartão com afirmação de custo |
| R3 | `T009-mechanical-check.py:607` | `:607-621` — `proof` conferida por `proof not in src_file.read_text()`, substring no arquivo inteiro; `:625-628` — o loop de fallback filtra só `fam in authors and effort is not None`, **nunca consulta `availability` do candidato escolhido** | **Sim.** Some-se: `synthetic_unavailable_evidence.md:8` usa "endpoint timeout", que `orchestrator-perfis.md:170` exclui expressamente como prova |
| R4 | `T009-mechanical-check.py:570` | `:570-571` — `families.get(model)` devolve `None` para modelo desconhecido; `None in authors` → `False` → **tratado como família distinta**. O mesmo padrão reaparece em `:515`, `:587`, `:626` | **Sim.** `orchestrator-perfis.md:206-207` exige conferência prévia |
| R5 | `T009-mechanical-check.py:514` | `:514-516` — condição de `required` acrescentada a `problems`, forçando `REJEITADA` no Estágio 1. Contradiz a própria análise em `:148-152` e `orchestrator-perfis.md:209-211` (bloqueio da revisão, não invalidade do objeto). O tratamento correto **já existe** em `:583-584`, no Estágio 3 | **Sim.** |

**Conclusão:** os 5 achados são reais, todos `category: patch`, `target_role: maker`, nenhum atribuído a Planner (spec) ou ao usuário (intenção).

## 1.2 Divergências entre o Pacote de Retomada e as fontes oficiais

O Pacote é índice sem autoridade; onde diverge, **prevalece a fonte**:

| ID | Pacote diz | Fonte oficial diz | Efeito |
| :--- | :--- | :--- | :--- |
| **D1** | R2 em `:488` | Parecer r02, action_item R2: `:78` | Localização do Pacote **incorreta**. O defeito está em `parse_routing_evidence()`, `:78` |
| **D2** | R3 em `:431` | Parecer r02, action_item R3: `:607` (evidência cita `:618` e `:625-628`) | Localização do Pacote **incorreta** |
| **D3** | `rework_round: 2` | Task, `:14`: `rework_round: 0`; `:17`: `content_id: unknown` | **Frontmatter da Task desatualizado**. A análise (`:8`) e o r02 registram rework 2 e `content_id 0de10d6…:97b3612674fa4aa5`. `state_revision: 2` confere |
| **D4** | — | `STATUS.md:3,5,30`: `active_work_ref: none`, T009 `draft`, `state_revision 0`, `last_evidence -` | **Projeção central desatualizada** e em contradição com a autorização do usuário |
| **D5** | — | `_tl-orc/project/evidence/T009-r01.md` **não existe** na árvore | O parecer r01 é referenciado pelo r02 ("as seis sondas de r01") mas **não está preservado**, contra `orchestrator-playbook.md:278-283` |
| **D6** | — | Parecer cita `orchestrator-perfis.md:165`, `:195`, `:197-198`; o texto normativo está em `:170`, `:206-207`, `:209-211` | Âncoras de linha do Checker **deslocadas**; a substância procede e foi por mim reconfirmada. O rework deve citar as linhas corretas |
| **D7** | — | Análise `:248-253` apresenta `validate_repository.py` → exit 0 como saída literal; o Checker obteve **exit 1** (`FileNotFoundError: No usable temporary directory`) e conferiu por leitura | **Lacuna residual de portão**: não há execução íntegra verde observada sob condições de revisão |

D3, D4 e D5 são de **propriedade do Orquestrador** (`orchestrator.md:66-67`), não do Maker. Em modo somente leitura, apenas os reporto.

---

# 2. Avaliação formal da unidade

| Campo | Valor conferido |
| :--- | :--- |
| Unidade | `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md` |
| `spec_revision` | `4197dea48f75cd14` (congelada; nenhum achado a contesta) |
| `content_id` revisado | `0de10d60149cf7c038a0954c6aec302c9fcd111e:97b3612674fa4aa5` |
| Veredito r02 | `changes_requested` — 5 ações (4 high, 1 medium), 7 hipóteses rejeitadas com evidência |
| Autoria efetiva | **Google** (Maker Agy) + **Anthropic** (correções do próprio Orquestrador) |
| Independência | `required` específica desta revisão (Task `:46` + `PROJECT.md:83-90`) |
| Rodadas de rework concluídas | **2** |

## 2.1 Classe dos achados e reincidência

Há **duas classes distintas**, e isso é decisivo para o encaminhamento:

- **Classe A — procedência conferida por ocorrência textual (R1, R2).** É **reincidente**: em r01 o Checker já atacara procedência de IDs (ID inventado, `sonnet-effort` como proxy, marcador documental). O Maker corrigiu as **seis sondas concretas** — o r02 confirma que todas passaram a ser recusadas — mas manteve o **mecanismo genérico** (`substring` no arquivo inteiro; regex frouxa). Ou seja: corrigiram-se as manifestações, não a regra.
- **Classe B — separação entre validade do objeto e resolução do despacho (R3, R4, R5).** É **nova em r02** e só se tornou observável porque o rework 2 introduziu os 10 controles de independência/fallback. É progresso, não recaída.

## 2.2 Progresso comprovado no rework 2

O parecer r02 rejeita, com evidência de sondas executadas, 7 hipóteses de defeito: alvo idêntico ao informado; AC01 corrigido com citações conferidas e `effort medium` corretamente rotulado como condição, não causa; as seis sondas de r01 agora recusadas; fallback sem prova bloqueado; `unknown` com lista vazia aceito; piloto reproduzível com caso 01 idêntico a T005; AC05 completo; AC06 sem arquivo distribuído nem caminho privado. A unidade **está convergindo**.

---

# 3. Encaminhamento proposto

## Proposta: **novo ciclo de `rework` (rodada 3), delimitado — não escalonamento consultivo**

### Fundamentação normativa

1. **O gatilho obrigatório de `debate` não foi atingido.** `orchestrator-perfis.md:188-193` fixa: *"Após **N** rodadas de rework (N padrão 3; o consumidor pode fixar outro valor em `PROJECT.md`) em que o Checker aponte achados centrais da mesma classe…"*. **Conferi `PROJECT.md` integralmente: não há valor alternativo de N** → vale o padrão **3**. Concluíram-se **2** rodadas.
2. **O limite de duas rodadas do playbook não se aplica.** `orchestrator-playbook.md:98-99` limita a duas rodadas, mas **apenas no modo Fila sequencial**. Confirmei que **`_tl-orc/QUEUE.md` não existe** e a autorização do usuário é unitária ("Autorizo executar a T009 como analysis com o piloto delimitado"), não uma fila. Logo, governa o N=3 dos perfis.
3. **Nenhum achado questiona spec ou intenção.** `orchestrator-playbook.md:272` manda atribuir: correção no escopo → Maker; spec inconsistente → Planner; intenção → usuário. Os **5 achados são `patch`/`maker`**. A pergunta que um debate responderia — *"estamos corrigindo manifestações do mesmo problema ou descobrindo requisitos a consolidar?"* — **já tem resposta documental**: os requisitos existem e estão consolidados na **tabela normativa de procedência** de `orchestrator-perfis.md:236-247`, que o protótipo simplesmente **não implementa com o rigor que ela exige**. Não há requisito a descobrir; há regra publicada a aplicar.
4. **A Classe A é tratável por regra objetiva, não por deliberação.** O antídoto está literalmente escrito em `orchestrator-perfis.md:242` (*medição local → "linha de tabela estruturada em evidência do projeto; **ID na primeira coluna**"*), `:241` (*proxy de custo → "**afirmação de custo por tarefa no cartão**"*) e `:246-247` (*"**Localização que resolve … não basta**; fonte existente mas incompatível com o tipo ou com o valor é rejeitada"*). A r03 deixa de pedir "corrija a sonda" e passa a **impor a tabela normativa como critério de aceite**.

### Por que **não** escalonar agora

Escalonar consultivo com N=2 seria antecipar um gatilho que a política fixa em 3, gastando três sessões consultivas para consolidar requisitos que já estão consolidados em `orchestrator-perfis.md:236-247`. A Classe B (R3–R5) sequer é reincidente. O risco real é o oposto: repetir um rework que corrige sondas em vez da regra.

### Pré-compromisso (registrado agora, para não ser decidido sob pressão depois)

> Se a revisão **r03** devolver `changes_requested` com achado central novamente da **Classe A (procedência)**, considero atingido **N=3** e o escalonamento para a fase `debate` de `orchestrator-perfis.md:188-193` passa a ser **obrigatório**, não discricionário — com classificação própria da fase `debate`, `requested_roles` exatamente `planner`, `maker`, `checker`, e a pergunta canônica do contrato.

## 3.1 Restrição de resolução crítica (consequência da política `required`)

Autoria efetiva = {Google, Anthropic}. Sob `required`, as únicas famílias elegíveis para Checker são as do harness **Codex (OpenAI)**.

> **Portanto: o Maker do rework 3 não pode ser do harness Codex.** Usar Codex como Maker acrescentaria OpenAI à autoria efetiva e deixaria **zero famílias elegíveis** para a revisão r03 sob `required`, bloqueando a unidade (`orchestrator-perfis.md:209-211`: indisponibilidade comprovada **nunca** converte `required` em `preferred`). Se Agy e Claude estiverem ambos indisponíveis, o correto é **bloquear com ponto de retomada**, não promover Codex a Maker.

## 3.2 Decisões que cabem ao usuário (não as respondo em seu nome)

| # | Decisão | Contexto conferido | Minha recomendação |
| :--- | :--- | :--- | :--- |
| **U1** | **Conflito de pin do Checker.** A regra T014 do pacote fixa Checker padrão `Codex GPT-5.6 Terra High`; a spec de T009 `:46` e `PROJECT.md:83-90` fixam o pin **`gpt-6-astra/high`** para esta unidade ("no piloto inicial o pin `gpt-6-astra/high` prevalece") | `orchestrator-perfis.md:48`: instrução do usuário > configuração do consumidor > perfil publicado. O pin é **específico da unidade e congelado na spec** | **Manter `codex/gpt-6-astra/high`.** Trocar para Terra no meio da unidade quebraria a comparabilidade do piloto do Astra. Ambos satisfazem `required` (OpenAI); o pin decide. `PROJECT.md:92` só admite Terra como **parecer consultivo sem valor de aprovação** |
| **U2** | **Leitura fora da raiz consumidora.** As citações de AC01 apontam para `../platform/_tl-orc/evidence/tl-orchestrator-v0.4.0-…-r01.md` e `…v0.5.0-…-r01.md`, que **não existem nesta raiz**. O Checker r02 as leu e **registrou o desvio (T008)** | `orchestrator.md:90-93`: fonte fora das raízes informadas exige **autorização explícita no briefing** | **Autorizar expressamente, somente leitura, apenas esses dois arquivos nomeados**, ou, se negado, exigir que AC01 rotule essas citações como referências externas não verificáveis no escopo. Sem uma das duas, AC01 fica inconferível e o desvio se repete |
| **U3** | **Reconciliação de estado.** D3 (frontmatter) e D4 (`STATUS.md`) exigem escrita do Orquestrador | `orchestrator.md:66-67`, `:99` | Autorizar a reconciliação (unidade → visão central) na próxima ativação com escrita. **Não executada agora** (somente leitura) |
| **U4** | **Parecer r01 ausente (D5)** | `orchestrator-playbook.md:278-283` | Se recuperável do registro operacional, preservar como `T009-r01.md`; se não, **registrar a lacuna explicitamente**. Não fabricar |

---

# 4. Briefing da próxima fase

> **Ordem normativa obrigatória.** `orchestrator.md:37-44` proíbe o Orquestrador de escolher modelo/effort por conta própria: **antes do primeiro despacho da fase `rework`, obtém-se e valida-se uma classificação da fase**. Por isso o briefing tem duas partes: **A** (ao Classificador, primeiro) e **B** (ao Maker, condicionada à classificação válida). A parte **C** é a fase seguinte, que exige **nova classificação** e **não está pré-autorizada**.

---

## PARTE A — Briefing ao Classificador (fase `rework`)

| Campo | Valor |
| :--- | :--- |
| Perfil do Classificador | **Fixo**, não classificável: Codex `gpt-5.6-luna`/medium → Claude `sonnet`/medium → Agy `gemini-3.8-flash-medium`/medium (`orchestrator-perfis.md:20-30`). Chamar **apenas o primeiro utilizável** |
| `story_id` | `T009` — fonte: `_tl-orc/project/tasks/T009-…md:1` (literal `id: T009`) |
| `phase` | `rework` |
| `requested_roles` | **exatamente `["maker"]`** — o Checker é resolvido depois, conhecida toda a autoria efetiva (`orchestrator-perfis.md:116`) |
| `context_revision` / `catalog_revision` | `catalog_revision`: `PROJECT.md-perfil-de-despacho-2026-09-07` — fonte `_tl-orc/PROJECT.md#perfil-de-despacho`. `context_revision`: derivar de `spec_revision 4197dea48f75cd14` + `content_id 0de10d6…:97b3612674fa4aa5`, ambos lidos da Task e do parecer r02 |
| Catálogo de pares autorizados | Lido de `_tl-orc/PROJECT.md#catálogo-permitido`, linhas 58-77. Para Maker: `agy/gemini-3.8-flash-high/high`, `codex/gpt-5.6-terra/{medium,high,xhigh}`, `claude/sonnet/{medium,high}`, `claude/claude-opus-5/high`. `max` e `ultra` **não constam** (`:79`) |
| Restrição de entrada | **O candidato Maker do harness `codex` é inelegível nesta unidade** enquanto vigorar `required` (ver §3.1). Declarar como restrição, não como palpite do Orquestrador |
| Preferência | `agy/gemini-3.8-flash-high` registrada como "preferência do usuário" em `PROJECT.md:67`; é preferência, **não pin** — o Classificador escolhe o par no catálogo |
| Tier | **Não herdar o tier anterior** (`orchestrator-perfis.md:127-128`). Entradas de risco: 5 achados high/medium em código determinístico de gate; correção de **regra genérica**, não de sondas pontuais; risco de regressão sobre 17 casos existentes; exigência de novos controles negativos e positivos |
| Evidências | Recorte com IDs e origem: `astra-coding` (`docs/MODEL_ROUTING.md#astra-coding`) e `astra-domain` (`docs/MODEL_ROUTING.md#astra-domain`). **Proibido compor lista na hora** (`orchestrator-perfis.md:246-248`) |
| `cost_basis` | `unknown` com `evidence_ids: []` é **legítimo** (Task `:29`). Se diferente de `unknown`, exige ≥1 ID econômico pertinente |

**Validação obrigatória do objeto devolvido** (`orchestrator-perfis.md:97-106`): schema versão 2; `story_id`/fase/revisões exatos; papéis exatos; um candidato por harness na ordem configurada; pares ∈ catálogo; `model: null` ⟺ `effort: null`; cada `evidence_id` fornecido no briefing e pertinente. Saída inválida admite **no máximo uma** correção de formato na mesma sessão; persistindo, **bloquear**.

---

## PARTE B — Briefing ao Maker (fase `rework`, rodada 3) — *condicionado à classificação válida*

### B.1 Identificação

| Campo | Valor |
| :--- | :--- |
| Unidade | `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md` |
| Papel | **Maker** (implementação e prova; sem despachar agentes) |
| Fase / rodada | `rework` / **r03** |
| `spec_revision` | `4197dea48f75cd14` — **congelada**; nenhum achado a contesta |
| `content_id` base | `0de10d60149cf7c038a0954c6aec302c9fcd111e:97b3612674fa4aa5` |
| Branch | `analysis/t009-semantic-validation` |
| Parecer que origina a rodada | `_tl-orc/project/evidence/T009-r02.md` — **ler íntegro**, inclusive os 7 `rejected` (definem o que **não** regredir) |
| Perfil de verificação | `analysis` (Task `:46`) |
| Contexto inicial | `_tl-orc/project/CONTEXT.md`; cabeçalho de `_tl-orc/project/STATUS.md`; a Task; `T009-r02.md`; `T009-analysis.md`; `T009-mechanical-check.py`; `T009-cases/` |

### B.2 Escopo e caminhos de escrita

**Permitido escrever — exclusivamente:**
- `_tl-orc/project/evidence/T009-mechanical-check.py`
- `_tl-orc/project/evidence/T009-analysis.md`
- `_tl-orc/project/evidence/T009-cases/` (inclui `pilot_summary.json` e `synthetic_unavailable_evidence.md`)

**Proibido escrever:** qualquer arquivo distribuído (`SKILL.md`, `prompts/`, `docs/`, `schemas/`, manifesto), `scripts/`, `_tl-orc/PROJECT.md`, outras Tasks, `STATUS.md` e o **frontmatter da própria Task** — campos de estado e coordenação são do Orquestrador (`orchestrator.md:66-67`).

**Escopo de leitura:** raiz consumidora e raiz do pacote informadas. Fonte fora disso exige autorização expressa — ver **U2**; sem decisão do usuário, **não ler `../platform/`** e declarar a limitação.

### B.3 Regra normativa central desta rodada — procedência por tipo **e** conteúdo

Esta rodada **não é "corrigir as cinco sondas"**. É elevar o critério: a conferência mecânica passa a implementar a tabela normativa de `prompts/orchestrator-perfis.md:236-247` como **contrato de aceite**.

Cláusula que rege toda a rodada — `orchestrator-perfis.md:246-247`:

> *"Localização que resolve (arquivo existe, âncora resolve, linha existe) **não basta**; fonte existente mas **incompatível com o tipo ou com o valor** é rejeitada."*

| Tipo de dado | Fonte autorizada | Conteúdo que sustenta o valor (critério de aceite) | Base |
| :--- | :--- | :--- | :--- |
| `story_id`, fase, papéis | solicitação ou spec da Task/fase | o registro citado contém o **valor literal** | perfis:238 |
| catálogo, pins, cadeias | `_tl-orc/PROJECT.md` (ou instrução do usuário / perfil publicado, na precedência) | o registro citado cita **exatamente** o par, o pin ou a cadeia | perfis:239 |
| autoria efetiva e famílias | registro de `Agent runs` **efetivo** | a linha citada declara harness, modelo e família usados | perfis:240 |
| evidência de custo/capacidade | `docs/MODEL_ROUTING.md` | pertinência ao modelo e, **para proxy de custo, afirmação de custo por tarefa no cartão** | perfis:241 |
| **medição local** | **linha de tabela estruturada em evidência do projeto** (`_tl-orc/project/evidence/`; em consumidor, `_tl-orc/evidence/`) | **ID na primeira coluna** | perfis:242 |
| julgamento | registro documental **vinculado por hash** ao objeto e às entradas | **hash coincide** e veredito explícito | perfis:243 |

### B.4 Ações exigidas — R1 a R5

Para **cada** item: corrigir a **regra**, não o caso; acrescentar controles reproduzíveis ao `--self-test`; registrar motivo tabelado e **provar `despacho: nenhum`**.

---

#### **R1 — high | `T009-mechanical-check.py:130` | AC02**
*Ocorrência textual de um ID é aceita como registro de medição local, inclusive com âncora ou linha inexistente.*

**Causa conferida:** `_strip_anchor_and_line()` (`:94-98`) descarta a localização; `:132` só testa existência do arquivo; `:141` faz `id_val not in file_text` sobre o arquivo inteiro.

**Regra a implementar (perfis:242 + :246-247):** um ID de medição local só é aceito quando, cumulativamente —
1. a fonte declarada está **sob `_tl-orc/project/evidence/`** (equivalente de consumidor: `_tl-orc/evidence/`); implementar ambos, controlar pelo caminho que existe nesta raiz;
2. a **âncora resolve** a um cabeçalho real, **ou** o **número de linha existe** no arquivo;
3. **naquela localização resolvida** há uma **linha de tabela estruturada** cuja **primeira coluna é o ID**.

**Rejeitar explicitamente:** cartão oficial do `MODEL_ROUTING.md` reclassificado como medição local; ocorrência do ID como **exemplo negativo no próprio código** (`T009-mechanical-check.py:671`, `bad_bare_list = ["price-astra", "local-fake"]`); âncora e linha inexistentes.

**Controles novos** (todos `REJEITADA` / `despacho: nenhum`, salvo o positivo):
- `local_id` com `source: docs/MODEL_ROUTING.md#ancora-inexistente` → rejeitado por **âncora não resolvida** e por **tipo incompatível**
- `local_id` com `source: _tl-orc/project/evidence/T009-mechanical-check.py:671` → rejeitado: exemplo negativo em código, não medição
- `local_id` com linha além do fim do arquivo → rejeitado
- `local_id` apontando a `docs/MODEL_ROUTING.md:74` (cartão oficial) → rejeitado por tipo
- **Positivo:** medição local **sintética e rotulada como tal**, criada em `T009-cases/`, com o ID na primeira coluna de uma tabela → **ACEITA**

---

#### **R2 — high | `T009-mechanical-check.py:78` | AC02**
*Derivação de proxy aceita menção a "por tarefa" sem requisito de custo e ignora as ressalvas do cartão.*

> **Nota:** o Pacote de Retomada indica `:488`; a localização oficial e verificada é **`:78`** (ver D1).

**Causa conferida:** `re.search(r"\bcusto\b[^\n]{0,50}\btarefa|\bpor\s+tarefa\b", body)`. A segunda alternativa é **isolada** e não exige termo de custo.

**Regra a implementar (perfis:241):** `official_task_proxy` exige **afirmação de custo monetário ou de tokens por tarefa** no cartão. Duração, latência e capacidade **não** sustentam a categoria. Exigir co-ocorrência, na mesma asserção, de termo de custo (`custo`, `preço`, `tarifa`, `US$`, `tokens`) com a unidade por tarefa; **remover a alternativa solta** `\bpor\s+tarefa\b`. Honrar o **escopo delimitado do cartão**: figura rotulada `simulada` ou de latência é recusada mesmo contendo "por tarefa".

**Referências literais conferidas:**
- `docs/MODEL_ROUTING.md:47-48` — `astra-coding`: *"Terminal-Bench mostra **custo API estimado por tarefa** cerca de 9% menor para Astra"* → **sustenta** proxy
- `docs/MODEL_ROUTING.md:55-58` — `astra-domain`: *"OSWorld com latência **simulada**, aproximadamente 40/75 **minutos por tarefa**… **Não extrapolar** esses resultados para qualquer debate, revisão ou tempo real de CLI"* → **não sustenta**

**Controles novos:** `astra-domain` declarado como proxy → **REJEITADA**, `despacho: nenhum`. `astra-coding` como proxy → **permanece ACEITA** (não regredir o controle positivo). Preservar `case_08` (`sonnet-effort`).

---

#### **R3 — high | `T009-mechanical-check.py:607` (e `:618`, `:625-628`) | AC03**
*Fallback de independência aceita texto arbitrário como prova de indisponibilidade e seleciona candidato indisponível.*

> **Nota:** o Pacote indica `:431`; a localização oficial e verificada é **`:607`** (ver D2).

**Causa conferida:** `:618` verifica `proof not in src_file.read_text()` — substring no arquivo inteiro, sem conferir localização, pertinência ao candidato ou natureza do erro. E `:625-628` seleciona o fallback filtrando apenas `fam in authors and c.get("effort") is not None`, **sem consultar `availability` do candidato escolhido**.

**Regras a implementar:**

| # | Regra | Base normativa (linha conferida) |
| :--- | :--- | :--- |
| a | Distinguir **timeout isolado** de **indisponibilidade comprovada**. *"Um timeout isolado, saída vazia ou processo ainda vivo **não comprovam** isso"*; *"Quota explicitamente esgotada, autenticação recusada ou harness ausente **podem** comprovar"* | `orchestrator-perfis.md:170-172` |
| b | A prova deve ser **registro pertinente**: run no **mesmo harness, mesma conta, mesma sessão de trabalho**, e a linha citada deve ser do **candidato declarado indisponível** | `orchestrator-perfis.md:166-167`, `:240` |
| c | Conferir a **localização declarada** da prova (âncora/linha resolvida), não o arquivo inteiro | `orchestrator-perfis.md:246` |
| d | Na **seleção** do fallback, respeitar o estado do candidato escolhido: pular `null`, `disabled`, `unavailable` e `inelegível`; `unknown` → conferir e, persistindo ambíguo, **bloquear** | `orchestrator-perfis.md:147-149`, `:152-153`, `:159-164` |
| e | Quota compartilhada comprovadamente esgotada marca **somente** os candidatos cobertos por essa mesma quota; não presumir conta compartilhada entre harnesses | `orchestrator-perfis.md:175-176` |
| f | Sob `preferred`, fallback de mesma família registra `same_family_fresh_session` **e abre o bloco `## RF-<unit_id>-rNN`** na evidência da unidade | `orchestrator-perfis.md:203-206` |

**Correção do controle positivo:** `T009-cases/synthetic_unavailable_evidence.md:8` usa `"infra_failure: 503 Service Unavailable (OpenAI endpoint timeout)"` para `codex/gpt-6-astra` — **inadmissível** pela regra (a). Substituir por prova admissível (quota explicitamente esgotada ou autenticação recusada, no mesmo harness/conta). A linha `:9` (`429 Rate limit exceeded / account quota exhausted`) **já é admissível** e deve ser preservada. Manter o arquivo rotulado como sintético.

**Controles novos** (todos `despacho: nenhum`):
- prova = texto arbitrário presente no arquivo mas sem erro de infraestrutura (ex.: `proof: "tl-orchestrator"`, `source: README.md#ancora-inexistente`) → **BLOQUEADO**
- prova com âncora/linha que não resolve → **BLOQUEADO**
- prova = **timeout isolado** → **BLOQUEADO** (perfis:170)
- prova pertinente a **outro** candidato que não o declarado indisponível → **BLOQUEADO**
- distintas comprovadamente indisponíveis, mas candidato de fallback com estado **`disabled`** → **BLOQUEADO**
- idem com estado **`unknown`** → **BLOQUEADO**
- `case_14` corrigido → **LIBERADO** com `same_family_fresh_session` e bloco `RF-` registrado

---

#### **R4 — high | `T009-mechanical-check.py:570` | AC03**
*Família desconhecida é tratada como distinta, permitindo contornar `required`.*

**Causa conferida:** `families.get(c.get("model"))` devolve `None`; `None in authors` é `False`; o candidato é classificado como independente. O **mesmo padrão reaparece em `:515`, `:587` e `:626`** — corrigir os quatro pontos, não apenas `:570`.

**Regra a implementar:** família ausente do mapa é **estado não resolvido**, terceiro valor distinto de "autora" e "distinta". *"Família desconhecida exige conferência **antes da escolha**"* (`orchestrator-perfis.md:206-207`). Enquanto não resolvida, o candidato **não pode ser selecionado**, sob `required` **ou** `preferred` — a exigência de conferência não é condicionada à política.

**Controles novos:** candidato cujo modelo não consta em `families`, sob `required` → **BLOQUEADO**, motivo "família não resolvida", `despacho: nenhum`; o mesmo sob `preferred` → **BLOQUEADO**. Demonstrar ausência de despacho quando falta a família de um candidato potencialmente autor.

---

#### **R5 — medium | `T009-mechanical-check.py:514` | AC03**
*Ausência de família independente sob `required` virou defeito mecânico do objeto.*

**Causa conferida:** `:514-516` acrescenta a condição a `problems`, forçando `REJEITADA` no Estágio 1 — o que **contradiz a própria análise** (`T009-analysis.md:148-152`: mesma família *"é aceito no objeto e classificado como inelegível(required, mesma família)"*).

**Regra a implementar (perfis:209-211):** sob `required`, *"a ausência de família distinta **bloqueia a revisão com ponto de retomada**, **sem abrir bloco de pendência**"*. Isso é **resolução**, não validade. Remover `:514-516` do Estágio 1; o objeto válido permanece `APROVADA`; com julgamento confirmado, o Estágio 3 devolve **`BLOQUEADO` com ponto de retomada** e `despacho: nenhum`. O tratamento correto **já existe** em `:583-584` — basta deixá-lo assumir o caso. Explicitar o contraste: `preferred` + fallback ⇒ abre `RF-`; `required` ⇒ **não** abre.

**Atualizações de coerência obrigatórias:** `case_15` passa a **APROVADA | CONFIRMADO | BLOQUEADO | BLOQUEADO | nenhum**; propagar para `pilot_summary.json`, para a tabela de AC04 (`T009-analysis.md:188`), para a prova de não-despacho (`:193`) e para o texto de AC03 (`:158`).

---

### B.5 Item adicional de conferência própria do Orquestrador

> **Declaração de origem:** **O1 não vem do parecer r02.** É achado da minha conferência própria (`orchestrator.md:71`: *"Nem sua leitura substitui o Checker, nem o parecer dele substitui sua conferência"*). Está registrado abertamente, sem correção silenciosa (`orchestrator-playbook.md:272`).

#### **O1 — medium | `T009-mechanical-check.py:538-557` | AC02/AC03**
*O Estágio 2 confere o julgamento apenas por substring de uma âncora.*

`:550` faz `if j_anchor not in j_content`, com `j_anchor` caindo no default `"Validação pelo Orquestrador"` (`:539`). Mas `orchestrator-perfis.md:243` exige, para o tipo *julgamento*, **"registro documental vinculado por hash ao objeto e às entradas"**, com **"hash coincide e veredito explícito"**; e `orchestrator.md:99` exige vincular o parecer ao `content_id` revisado. A entrada `judgment` dos casos (`expected_t005_review.json:73-76`) traz apenas `{source, anchor}` — **sem hash e sem veredito explícito**.

**Ação:** exigir que `judgment` carregue hash do objeto de classificação e das entradas `expected`, mais veredito explícito, e que o Estágio 2 **confira a coincidência do hash**. **Este item não bloqueia a rodada:** se a mudança exigir redesenhar o formato do registro de julgamento além do orçamento de r03, o Maker deve **declarar a limitação** em AC03/AC05 em vez de deixar a conferência por substring sem ressalva. **R1–R5 têm precedência.**

### B.6 O que **não** regredir

O parecer r02 rejeitou 7 hipóteses de defeito com evidência. Estes comportamentos são **linha de base a preservar**, e a regressão de qualquer um deles é falha da rodada:

1. As **seis sondas de r01** continuam recusadas (ID inventado em `README.md`; `sonnet-effort` como proxy; marcador `official-2026-09-05`; `reason` ausente; `facts: []`; listas soltas em `local_ids`/`proxy_ids`)
2. Fallback **sem prova** sob `preferred` permanece bloqueado (`case_13`)
3. `cost_basis: unknown` com `evidence_ids: []` permanece **aceito** (`case_01`, `case_06`) — Task `:29`
4. `case_01` permanece **idêntico** ao resultado real de T005 review (`T005-classification.md:37`)
5. Catálogo lido de `PROJECT.md` (`:28`) e IDs oficiais de `MODEL_ROUTING.md` (`:54`) — nunca compostos na hora
6. AC01 mantém a separação fatos / hipóteses / não verificadas, com `effort medium` como **condição observada, não causa**
7. `--self-test` **sem escrita**, resumo em memória idêntico a `pilot_summary.json`
8. Nenhum arquivo distribuído alterado; nenhum caminho privado

### B.7 Portões e provas (AC06)

| Portão | Exigência |
| :--- | :--- |
| `python3 scripts/validate_repository.py` | Verde. **Se o ambiente impedir a execução íntegra** — em r02 houve `exit 1` com `FileNotFoundError: No usable temporary directory` —, registrar a **saída literal da falha** e a conferência alternativa. **Proibido apresentar `exit 0` não reproduzido** (ver D7) |
| `python3 _tl-orc/project/evidence/T009-mechanical-check.py --self-test` | `exit 0`, **sem escrita em disco**, cobrindo os 17 casos atuais **mais** todos os novos controles, com resumo em memória idêntico ao `pilot_summary.json` versionado |
| Integridade | Nenhum arquivo distribuído alterado; nenhum caminho privado nos `content_paths` |
| Registro | Comando literal, diretório, saída e **exit code real**; sem pipe que esconda o exit (`orchestrator-playbook.md:234`) |

### B.8 Critério de parada

Rodada concluída quando: **R1–R5 corrigidos na regra** (não na sonda); **O1 tratado ou limitação declarada**; controles novos no `--self-test` com motivo tabelado e `despacho: nenhum` comprovado; `case_14`, `case_15`, `synthetic_unavailable_evidence.md`, `pilot_summary.json` e `T009-analysis.md` (AC03, AC04, AC06) **mutuamente coerentes**; portões executados com saídas literais; nenhuma regressão de B.6.

**Fora do escopo — não iniciar** (Task `:30`, `:37`; análise `:235-240`): distribuir o validador; escolher linguagem definitiva; introduzir dependência ou requisito de instalação; alterar arquivo distribuído, `scripts/`, `PROJECT.md`, `STATUS.md`, outras Tasks ou o frontmatter da Task; comparação controlada de effort (opcional e não acionada).

---

## PARTE C — Fase seguinte (`review` r03) — **não pré-autorizada**

Registrada para previsibilidade; **exige nova classificação** (`orchestrator.md:42-44`: mudança de fase exige nova classificação dos papéis necessários).

| Campo | Valor |
| :--- | :--- |
| Classificação | Nova, fase `review`, `requested_roles: ["checker"]`, **após** conhecida a autoria efetiva do rework 3 |
| Independência | **`required`**, distinta de toda a autoria efetiva (Google, Anthropic) — Task `:46` + `PROJECT.md:87-88` |
| Pin | `codex/gpt-6-astra/high` — `PROJECT.md:85-86`, sujeito à decisão **U1** |
| Sessão | **Nova**, somente leitura; não reutilizar sessão de Maker, Classificador ou debate (`orchestrator-perfis.md:197-198`) |
| Se Codex indisponível | **Bloquear com ponto de retomada.** `required` **nunca** vira `preferred` por indisponibilidade comprovada (`orchestrator-perfis.md:210-211`) |
| Escopo de leitura | Declarar expressamente; se **U2** for negado, instruir a tratar as citações `../platform/` como externas não verificáveis, em vez de repetir o desvio T008 |
| Registro | `_tl-orc/project/evidence/T009-r03.md` com parecer íntegro, `spec_revision`, `content_id` novo, `content_paths`, sessão, harness, modelo, effort, família e limitações (`orchestrator-playbook.md:278-283`) |
| Se `changes_requested` com achado da Classe A | **Escalonamento consultivo obrigatório** — ver pré-compromisso em §3 |

---

# 5. O que não foi feito

Conforme o aviso restritivo: **nenhum arquivo foi criado, alterado ou removido**; **nenhum Classificador, Maker ou Checker foi despachado**; nenhuma classificação foi obtida. As Partes A, B e C são **proposta**, não execução.

Pendentes de autorização antes de qualquer execução: **U1** (pin do Checker), **U2** (leitura fora da raiz), **U3** (reconciliação de D3/D4), **U4** (parecer r01 ausente) — e a autorização para despachar a rodada de rework em si.

