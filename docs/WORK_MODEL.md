# Modelo de trabalho nativo e importação de contexto

Este documento define o perfil **Native**: como o método organiza trabalho em
`_tl-orc/project/` quando o projeto consumidor não delega essa organização a outro método, e como
coordena a retomada mesmo quando o trabalho continua governado por BMAD ou outro sistema. Define
também a operação **Import Context**, que produz contextos derivados pequenos e rastreáveis a
partir de documentos existentes.

O núcleo de orquestração não muda: papéis, classificação por fase, independência do Checker, um
escritor por árvore e os limites operacionais do [contrato do Orquestrador](../prompts/orchestrator.md)
continuam valendo. Este documento acrescenta somente o modelo de documentos, o contrato de estado
e as regras de autoridade sobre eles. O [guia de configuração](PROJECT_CONFIGURATION.md) descreve
onde o perfil é declarado.

## Entidades

| Entidade | Definição | Campos |
| :--- | :--- | :--- |
| `Project` | Contexto permanente: objetivos, restrições e regras transversais. | `CONTEXT.md` |
| `Deliverable` | Resultado que reúne Tasks e tem condição própria de conclusão. | `id`, `method`, `goal`, `done_when`, `integration_criteria`, `tasks`, `order`, `status`, `origin`, `decisions` |
| `Task` | Unidade executável com resultado verificável. | `id`, `type`, `deliverable` ou `standalone: true`, `method`, `status`, `state_revision`, `depends_on`, `blocked_by`, `origin`, `decisions`, `spec_author`, `spec_revision`, `rework_round`, `affects_context`, `content_id`, `content_paths` |
| `Standalone Task` | Task sem Deliverable. Não implica tier `simple`. | os mesmos de Task |
| `Batch` | Lote finito de unidades com escopo e orçamento congelados para execução autônoma autorizada. | `id`, `status`, `batch_revision`, `authorization`, `frozen_scope`, `budget`, `execution` |
| `Story Authority` | Envelope imutável de autoridade humana que cobre uma Story inteira sob `AUTO_STORY`, com teto global de chamadas e escopo monotônico decrescente. Nunca reescrito para registrar saldo. | `authority_payload` (`authority_id`, `work_ref`, `authorized_spec_revision`, `authorized_spec_sha256`, `authorized_write_scope`, `allowed_effects`, `protected_paths`, `global_model_call_budget`, `max_child_batches`, `max_consecutive_failed_batches`, `wall_clock_deadline`, `hard_stops`), `root_authority_digest`, `operator_authorization` |
| `Decision` | Decisão consolidada com justificativa. | `id`, `kind`, `status`, `context`, `options`, `choice`, `rationale`, `origin` |
| `Discussion` | Síntese de um debate, com estado. | `id`, `status`, `question`, `context_refs`, `options`, `confirmed_decisions`, `hypotheses`, `open_questions`, `resulting_work` |

`type` da Task usa o núcleo `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `research` e
`analysis`; o consumidor pode estender a lista em `PROJECT.md`. O tipo sugere a verificação
inicial e nunca determina modelo, effort, tier ou método, nem dispensa uma verificação exigida
pelo trabalho. O Classificador não recebe o tipo como sinal de tier.

`kind` da Decision é `architecture`, `product` ou `operational`. A referência oficial de qualquer
entidade é o ID; o slug do nome de arquivo é auxiliar e pode mudar sem alterar referências.

**Somente o Orquestrador altera campos de estado e de coordenação em qualquer documento de
`project/`.** Os demais papéis escrevem apenas nas seções e caminhos autorizados em seu briefing.

## Layout

```text
_tl-orc/
├── package/                        # distribuição canônica, imutável entre atualizações
├── INSTALLATION.md                 # procedência e integridade
├── PROJECT.md                      # configuração do método; declara work_method
├── QUEUE.md                        # opcional; pode declarar permit_state_update
├── evidence/                       # fallback legado, permanece acessível
└── project/                        # documentos de trabalho; nunca tocado por atualizações
    ├── STATUS.md                   # coordenação, projeção de lote e tabela derivada
    ├── CONTEXT.md                  # contexto global curto
    ├── batches/Bnnn.md             # batches autorizados do Modo Automático
    ├── story-authorities/Annn.json # envelopes imutáveis de autoridade de Story (AUTO_STORY)
    ├── tasks/Tnnn-slug.md
    ├── deliverables/Dnnn-slug.md
    ├── decisions/DECnnn-slug.md    # um arquivo por decisão
    ├── discussions/DISCnnn-slug.md
    ├── evidence/Tnnn-rNN.md        # um arquivo por Task e rodada; rodadas anteriores preservadas
    ├── evidence/Tnnn-rNN/          # derivados e dados operacionais da rodada (inputs/, ledger/)
    ├── context/INDEX.md            # Import Context
    ├── context/features/Fnnn-slug.md
    └── imports/IMPnnn.md
```

`_tl-orc/PROJECT.md` descreve como o método está configurado no projeto. `project/CONTEXT.md`
descreve o trabalho. `project/STATUS.md` descreve onde o trabalho está e como continuar.
`STATUS.md` e `CONTEXT.md` são obrigatórios quando `project/` existe; `tasks/` é obrigatório a
partir da primeira Task; os demais diretórios são opcionais.

`project/` é criada na primeira operação autorizada que necessite dessa estrutura, inclusive para
coordenar trabalho BMAD. Nunca é criada por uma atualização do pacote, e sua criação não transfere
autoridade para o perfil Native.

### Layout de evidências e derivados por unidade/rodada

Evidências duráveis e derivados de execução de uma unidade (Task Native ou story BMAD) organizam-se
sob `evidence/<unidade>-rNN/` e no arquivo `evidence/<unidade>-rNN.md`. Pastas e arquivos de evidência
armazenam registros e dados de medição; nunca são autoridade de status. O status de uma Task Native
permanece exclusivamente na Task; o status de uma story BMAD permanece no artefato BMAD correspondente.
Mover ou reorganizar pastas de evidência não altera o status da unidade.

Toda árvore contida sob `project/evidence/` ou `evidence/` é terminantemente excluída da descoberta
operacional automática e do resolver de configuração ativa. Snapshots arquivados (como snapshots de
pilotos ou de rodadas anteriores) são dados passivos para auditoria e nunca configuram regras,
tarefas ou instruções ativas.

## Áreas de trabalho

O modo padrão é o **projeto sem módulos**, inclusive em instalações novas: tudo fica em
`_tl-orc/project/`, que é a área `global`. Sem áreas adicionais cadastradas, o Orquestrador assume
`global` sem perguntar qual módulo usar, sem exigir cadastro e sem criar pasta de módulos. Native e
BMAD continuam disponíveis conforme a autoridade configurada. O suporte a múltiplas áreas é
opcional e existe para repositórios que organizam trabalho por módulo.

| Projeto | Organização documental |
| :--- | :--- |
| Sem módulos | tudo em `_tl-orc/project/` |
| Com módulos cadastrados | área `global` mais uma área documental por módulo |

**A organização documental por área é distinta da coordenação de escrita, que continua por
árvore.** Uma instalação por repositório; documentos globais e, quando cadastrados, documentos por
módulo.

### Cadastro

Áreas adicionais são cadastradas na seção `## Work Areas` de `_tl-orc/PROJECT.md`, sem arquivo
extra. `global` é implícita e reservada, com caminho fixo `_tl-orc/project/`; sua linha pode ser
omitida, e seu `work_method` é o campo global já declarado em `PROJECT.md`, sem redeclaração.

```text
## Work Areas
| area_id | path | work_method | status_source | evidence |
| billing | modules/billing/_tl-orc/project | bmad | modules/billing/_bmad-output/sprint.md | modules/billing/_tl-orc/project/evidence |
```

- `path` é relativo à raiz consumidora e já contém o caminho documental completo da área. O
  exemplo `modules/<module>/` é de um consumidor específico; projetos organizados em `apps/`,
  `services/` ou outros caminhos usam o cadastro com seus próprios `path`, sem renomear pastas.
- Validação no cadastro e na ativação: `area_id` duplicado, sobreposição entre `path` de áreas
  e conflito com destinos da instalação (`_tl-orc/package`, integrações de skill). Cadastro
  inválido bloqueia a seleção da área, não a ativação.
- Uma pasta documental de módulo não cadastrado é reportada, não adotada.
- Área cadastrada não implica diretório criado. A ativação somente leitura informa a condição
  "cadastrada, sem documentos"; a estrutura nasce na primeira operação autorizada que precisar
  dela. Trabalhar em um módulo inicializa, na mesma operação, os documentos globais necessários à
  coordenação: `_tl-orc/project/STATUS.md` e `CONTEXT.md`.
- `work_method` omitido no módulo herda o global, sempre como padrão para trabalho novo, nunca
  para unidades existentes.
- Caminhos `_tl-orc/...` de instalação resolvem sempre pela raiz consumidora; documentos de área
  resolvem pelo `path` cadastrado. O caminho documental não determina o diretório de execução dos
  portões, que continua vindo da tarefa e da política do consumidor.
- Abrir uma subpasta ou informar `cwd` dentro de um módulo não seleciona área nem autoridade.

### Seleção de área e autoridade

Ordem: referência explícita do usuário, verificada na fonte; unidade já registrada; área
declarada na tarefa; pergunta. Sem área resolvida, nenhuma escrita em `project/` de módulo.

O método configurado na área define o padrão para trabalho novo sem autoridade anterior. Não
altera o método de unidades existentes: uma Task Native dentro de um módulo BMAD continua Native.
Referência explícita a unidade inexistente, ou que contradiz a área declarada, não autoriza criar
nem selecionar outra silenciosamente; é ambiguidade material.

### Coordenação por árvore, progresso por área

O `coordinator` do `STATUS.md` **global** governa a escrita em toda a árvore do repositório,
inclusive em `project/` de módulos e na seção `## Areas`. A regra de um escritor por árvore, que
já inclui autores de specs e relatórios, permanece: caminhos de resultado separados não demonstram
isolamento, porque Git, configuração, índices e outros recursos são compartilhados. Execução
simultânea em árvores distintas segue o contrato existente, sem configuração nova.

O `STATUS.md` de módulo não tem `coordinator`. Mantém `active_work_ref` da área, `next_action`,
`current_role`, contadores locais, tabela derivada de Tasks e a linha `coordination: global`.

### Camadas de status e ponto de retomada

| Camada | Conteúdo |
| :--- | :--- |
| Cabeçalho global (`_tl-orc/project/STATUS.md`) | `coordinator` e a referência da execução corrente na árvore: `active_work_ref`, qualificado no modo multiárea, inclusive quando a unidade pertence a um módulo; `current_role`; `next_action` |
| Cabeçalho do módulo | progresso local: `active_work_ref` da área, `next_action`, contadores, `coordination: global` |
| Task ou artefato externo | estado oficial da unidade |
| Seção `## Areas` do STATUS global | projeção dos módulos cadastrados, derivada e reconstruível, sem linha de `global`: `area_id`, `work_method`, `active_work_ref` e caminho do `STATUS.md` da área; ponteiro, nunca cópia de tabelas de Tasks nem de estado BMAD |

Um novo harness lê o cabeçalho global e sabe qual unidade, de qual área, estava sendo conduzida.
Ordem de escrita, sem atomicidade: primeiro a unidade, depois as projeções locais do módulo, por
último a visão global. Na retomada, releia a unidade oficial antes de reconciliar cabeçalhos
atrasados; divergência esperada segue a [tabela de recuperação](#transição-e-recuperação) e não
exige confirmação adicional.

### Manifesto derivado de retomada (`resume.json`)

A retomada de sessão é coordenada pelo manifesto derivado `resume.json`, gerado deterministicamente
(duas execuções sobre a mesma árvore produzem saída byte-a-byte idêntica). O manifesto carrega a própria
procedência através de uma lista de `sources` com `path`, `selector` (por heading path) e `digest`
(SHA-256 canônico).

Campos de coordenação (`effective_authors`, `open_items`, `next_action`) são cópia derivada para consumo
rápido; a autoridade soberana permanece nos documentos originais (Task, `STATUS.md` e evidências). O
manifesto inclui a seção `resolved_context` (Resolved Context Manifest), que mapeia cada classe de
informação da política de contexto para o modo de entrega (`inline`, `excerpt`, `on_demand`)
apropriado à fase.

Antes de qualquer despacho, o gerador do manifesto executa uma verificação estrita de integridade:
se qualquer digest das fontes congeladas divergir dos arquivos atuais em disco, a operação encerra
com erro, impedindo o prosseguimento com contexto corrompido ou stale.

### Referências entre áreas

- Dentro da área, os IDs são locais (`T012`). Entre áreas, a referência qualificada usa `:`
  (`billing:T012`, `global:DEC003`) e é aceita em `depends_on`, `decisions`, `origin`,
  `deliverable`, `tasks`, `affects_context`, `resulting_work` e nos links de discussões. Sem
  prefixo, a referência é local.
- Pertencimento é campo próprio, distinto de procedência. Uma Task de módulo pertencente a um
  Deliverable global declara `deliverable: global:D002`, `standalone: false` e
  `origin: global:D002`; `origin` não substitui `deliverable`. O Deliverable global lista `tasks`
  qualificadas e só fecha com `integration_criteria` verificados através das áreas.
- Referências cruzadas não autorizam escrever nem despachar trabalho em outra área.
- Dependências entre áreas preservam `blocked_by` e a regra de `cancelled`; ciclos entre áreas
  são detectados e bloqueiam a seleção, com a cadeia exibida.
- `active_work_ref` no modo multiárea é `<method>/<unit_type>/<area_id>:<id>@<source_location>`.
- O registro de revisão identifica a unidade qualificada (`<area_id>:<id>`), `spec_revision` e
  `content_id`. Igualdade de hashes entre unidades não transporta uma aprovação de uma Task para
  outra.

### Formatos legados e classificação

Sem cadastro, os formatos deste documento para uma única área continuam aceitos e produzidos. No
modo multiárea, registros e despachos novos usam referências qualificadas; referências antigas sem
prefixo são interpretadas somente quando a área de origem é inequívoca pelo documento que as
contém, e divergência exige esclarecimento. Uma atualização do pacote não reescreve documentos
para acrescentar `global:`.

No briefing do Classificador, `area_id` é dado de contexto; o schema não recebe propriedade nova,
e `story_id` recebe o ID qualificado no modo multiárea. A validação e o reuso comparam a forma
canônica `<area_id>:<id>` obtida do briefing; um `story_id` sem prefixo só é canonizado quando a
área é inequívoca. Uma classificação anterior é normalizada pelo seu próprio briefing de origem,
verificável no registro daquela classificação, nunca pelo briefing da tarefa atual; sem essa
procedência, reclassifique. Aceitar dois formatos nunca permite reutilizar classificação entre
áreas diferentes, e as demais exigências de igualdade permanecem.

### Carregamento e importação por área

Conjunto inicial para uma unidade de módulo: `CONTEXT.md` global curto, `CONTEXT.md` da área,
`INDEX.md` da área quando existir, briefs afetados e dependências diretas, unidade ativa e decisões
referenciadas, inclusive `global:DEC…`. Documentos compartilhados são referenciados por link e
revisão, nunca copiados para áreas. Import Context roda por área. O brief fica na área responsável
pela feature: em projetos sem módulos, todos em `_tl-orc/project/context/features/`; com módulos,
features de escopo global na área global e as demais na área correspondente.

## Seleção de método e autoridade

`PROJECT.md` declara `work_method: native` ou `work_method: bmad` para a área global; uma área
cadastrada em `## Work Areas` só pode declarar outro valor na sua linha do cadastro, como padrão para
trabalho novo daquela área.
Cada unidade de trabalho tem uma única autoridade, registrada nela mesma em `method`. A seleção
segue esta ordem:

1. Referência explícita do usuário a uma unidade existente, verificada na fonte. Referência a
   unidade inexistente é ambiguidade material, não seleção.
2. Autoridade já registrada para aquele trabalho.
3. Método configurado para o projeto ou módulo.
4. Perfil Native, esclarecendo apenas ambiguidades materiais.

Trabalho Native em projeto BMAD é permitido por seleção explícita ou política configurada. Mudar a
autoridade de uma unidade já registrada é migração deliberada, descrita em
[Migrate Work](#migrate-work). A presença de uma instalação BMAD não seleciona método. O
Classificador recomenda capacidade de execução e nunca altera autoridade: trocar o executor não
troca onde o trabalho é governado.

Perfis anteriores sem `work_method` preservam suas fontes e seu comportamento de autoridade,
sejam BMAD, issues, tickets ou outros boards. Native é selecionado somente para trabalho novo sem
autoridade anterior ou por seleção explícita. Ausência de `work_method` não migra unidades
existentes.

## Estado

Estados da Task: `draft`, `ready`, `in_progress`, `in_review`, `done` e `cancelled`. Bloqueio é o
campo `blocked_by`, com IDs ou motivo, e não um estado, para que a retomada conheça o estado ao
qual voltar. Retrabalho é o contador `rework_round`.

A Task Native é dona de `status` e de `state_revision`, um inteiro que cresce a cada transição.
`STATUS.md` tem dois conteúdos com donos distintos:

- **Tabela de Tasks nativas:** derivada das Tasks, reconstruível a qualquer momento e nunca editada
  como fonte. Existe somente quando há Tasks nativas. Colunas: `id`, `type`, `deliverable`,
  `status`, `depends_on`, `blocked_by`, `state_revision`, `last_evidence`.
- **Cabeçalho de coordenação:** presente tanto em `native` quanto em `bmad`. O bloco abaixo é o
  cabeçalho do `STATUS.md` **global**; no modo multiárea, `<id>` é a referência qualificada
  `<area_id>:<id>` conforme [Áreas de trabalho](#áreas-de-trabalho), e o `STATUS.md` de módulo não
  tem `coordinator` e usa o template próprio em [Templates](#templates).

```text
format_version: 1
work_method: <native|bmad>
active_work_ref: <method>/<unit_type>/<id ou area_id:id no modo multiárea>@<source_location>
current_role: <orchestrator|planner|maker|checker|none>
next_action: <frase curta>
coordinator:
  harness: <codex|claude|agy|other>
  session: <identificador observado ou declarado>
  started_at: <UTC>
  last_write_at: <UTC>
  released: <true|false>
review_followups: [<unit>@<evidence_ref>#rf-<unit_id>-rnn]
next_task_id: <n>
next_deliverable_id: <n>
next_decision_id: <n>
next_discussion_id: <n>
open_discussions: [DISCnnn]
```

`active_work_ref` identifica a unidade ativa por método, tipo, ID e localização da fonte, e pode
apontar para um Deliverable em planejamento antes de existir Task ativa. Trabalho externo aparece
por referência; o estado de uma story é consultado no artefato oficial do BMAD, nunca copiado.

A linha `review_followups` lista as pendências de revisão posterior por outra família abertas na
árvore, no formato `<unit>@<evidence_ref>#rf-<unit_id>-rnn`; é um campo derivado e reconstruível a partir dos
blocos `## RF-<unit_id>-rNN` registrados nas evidências, presente tanto em `native` quanto em `bmad`.

A identidade completa da unidade reutiliza o formato do contrato (`active_work_ref`):
`<method>/<unit_type>/<id | area_id:id>@<source_location>`. Suas quatro formas canônicas são:
- Native sem módulos: `native/task/T003@_tl-orc/project/tasks/T003-slug.md`;
- Native multiárea: `native/task/billing:T003@modules/billing/_tl-orc/project/tasks/T003-slug.md`;
- BMAD sem módulos: `bmad/story/1.1@_bmad-output/implementation-artifacts/sprint-status.yaml`;
- BMAD multiárea: `bmad/story/billing:1.1@modules/billing/_bmad-output/implementation-artifacts/sprint-status.yaml`.

Essa mesma identidade aparece no alvo da pendência (`target.unit`), no bloco de follow-up, na tabela
`Agent runs` e no registro de revisão. Duas stories com o mesmo ID em áreas diferentes são unidades
distintas (por exemplo, `bmad/story/billing:1.1@...` e `bmad/story/identity:1.1@...`), gerando
pendências distintas com blocos registrados nos artefatos de evidência de cada área, sem criar Task
Native duplicada, enquanto o cabeçalho global de `STATUS.md` lista as identidades completas em
`review_followups`.

### Transição e recuperação

A ordem de escrita é Task, depois tabela, depois cabeçalho. O pacote não oferece atomicidade. Na
retomada, o Orquestrador relê a unidade ativa e o cabeçalho e aplica:

| Situação | Tratamento |
| :--- | :--- |
| Task avançou e a tabela ficou atrasada | Reconstruir a tabela. |
| `active_work_ref` aponta para Task `done` | Conferir o fechamento nas evidências, atualizar a coordenação e continuar conforme fila e autorizações existentes. |
| Unidade não encontrada | Verificar projeto, branch, caminhos e referências antes de pedir esclarecimento. |
| Estados incompatíveis ou evidência insuficiente | Interromper somente a execução afetada e esclarecer a divergência. |

Nenhuma dessas situações exige, por si só, confirmação humana.

### Coordenação cooperativa

O registro `coordinator` é um protocolo cooperativo. Não é lock, lease nem contador atômico, e não
impede sobrescrita concorrente. A primeira versão suporta uma única sessão coordenadora por
árvore do repositório, registrada no `STATUS.md` global e válida para todas as áreas, com cooperação
entre harnesses. Ausência de escrita por qualquer intervalo não indica
sessão encerrada.

Antes de qualquer escrita em `project/`, o Orquestrador confere o registro e aplica:

| Registro encontrado | Comportamento |
| :--- | :--- |
| Pertence à própria sessão (`harness` e `session` iguais aos observados) | Continuar dentro do escopo autorizado, atualizando `last_write_at`. |
| Pertence a outra sessão com `released: false` | Não escrever. Apresentar o registro e aplicar a transferência. |
| Liberado ou inexistente | Registrar a coordenação da sessão atual quando a operação autorizar escrita. |

A transferência exige que a execução anterior esteja comprovadamente interrompida ou encerrada, é
escolhida explicitamente pelo usuário e é registrada com motivo, sessão anterior e sessão nova
antes de qualquer outra escrita. Encerramento normal grava `released: true`. A identidade da sessão
é a observada no harness; se ele não a expuser, o Orquestrador declara um identificador no início
da sessão e o usa de forma consistente.

### Versão do trabalho

A Task registra três identificações separadas:

| Identificação | Escopo | Forma |
| :--- | :--- | :--- |
| `content_id` | Resultado revisado: código e documentos produzidos ou modificados pela Task, incluindo artefatos de `project/` que sejam resultado, como Feature Briefs, `INDEX.md` e registros de importação. | Com Git, commit base mais hash do conjunto de alterações, incluindo arquivos novos não rastreados que façam parte do trabalho. Sem código, hashes dos artefatos listados. |
| `spec_revision` | A spec da Task congelada para execução. | Hash da seção de spec ou revisão verificável equivalente. |
| Registros de controle | `status`, `state_revision`, `blocked_by`, `rework_round`, `content_id`, cabeçalho de coordenação, tabela de `STATUS.md` e registro de revisão. | Excluídos do `content_id`. |

A Task declara em `content_paths` a lista explícita de caminhos cobertos. Um caminho de `project/`
entra quando é resultado da Task e fica fora quando é registro de controle; a exclusão nunca é a
pasta inteira. Resumo é opcional e não substitui a identificação. Registrar o parecer e atualizar o
status preservam o `content_id`; modificar materialmente qualquer caminho coberto invalida o
reaproveitamento do parecer. Na retomada, o Orquestrador recalcula e compara com o registrado;
divergência é relatada antes de qualquer ação.

### Canonical section digest

O digest canônico por seção é o hash SHA-256 calculado sobre o conteúdo da seção Markdown, desde a
linha do cabeçalho (inclusive) até o início do próximo cabeçalho estrutural de nível igual ou superior
(ou fim do arquivo). O texto é normalizado para UTF-8 com quebras de linha LF (`\n`) e newline final
único, sem normalização semântica. Subseções de nível mais profundo ficam contidas na seção pai.

Linhas iniciadas por `#` dentro de cercas de código (```` ``` ```` ou `~~~`) e menções a cabeçalhos no
meio da prosa ou entre crases (por exemplo `` `## Result` ``) não delimitam seções. O conteúdo anterior
ao primeiro cabeçalho é endereçado deterministicamente como `frontmatter`.

Dois arquivos que diferem apenas em quebras de linha CRLF/LF ou em seções externas produzem exatamente
o mesmo digest para a seção selecionada.

### Estados de freshness

A avaliação de frescor de uma seção referenciada contra um digest esperado resulta em um de três estados:
- `current`: seletor encontrado no documento e digest idêntico ao esperado. A fonte que sustenta o fato permanece inalterada.
- `digest_changed`: seletor encontrado, mas digest diverge do esperado. Requer releitura restrita à seção afetada para apurar o impacto da alteração.
- `selector_not_found`: cabeçalho renomeado, movido ou ausente. Requer redescobrir o tópico no documento inteiro.

Digest idêntico comprova apenas que a fonte de sustentação não mudou; não atesta que o fato derivado
era originalmente correto.

### Política de campos voláteis e `always_read`

Campos temporais e contadores de sessão (`last_write_at`, timestamps, sessões de harness) não entram
no cálculo de digest estável de seções normativas. Blocos essencialmente voláteis de coordenação (como
o bloco `coordinator` de `STATUS.md`) são expressamente classificados como `always_read`: devem ser lidos
integralmente e incondicionalmente pelo Orquestrador na retomada.

### Identificadores

IDs são sequenciais por entidade e alocados apenas pela sessão coordenadora a partir dos
contadores do cabeçalho. Antes de alocar, o Orquestrador confere os IDs existentes em `project/` e
avança o contador quando estiver atrasado; nesse contexto serial, o maior ID existente é válido
como recuperação, sem constituir suporte a alocação concorrente. É proibido sobrescrever arquivo
existente ao criar uma unidade. Colisão real bloqueia a integração documental da unidade afetada
até reconciliação explícita das referências; não há sufixo automático.

## Spec antes de `ready`

`ready` exige spec com intenção; escopo e caminhos de escrita, que o autor da spec registra em
`content_paths` antes da execução; decisões vigentes referenciadas;
critérios observáveis; prova conforme o [perfil de verificação](#perfil-de-verificação); e a
declaração `affects_context` sempre que a operação Import Context estiver ativa no projeto, com a
lista dos briefs afetados ou explicitamente vazia quando nenhum brief for afetado. A exigência
vale independentemente de quem escreveu a spec.

`spec_author: orchestrator` é permitido para Task delimitada, sem incerteza material e coberta
pelas regras existentes. Decomposição, incerteza relevante, pedido do usuário ou Deliverable
exigem Planner. O Planner atua no Deliverable para decomposição, ordem, dependências e
`done_when`, e na Task para preparar a execução. O planejamento de um Deliverable usa a fase
`planning` com o ID do Deliverable no campo `story_id` do briefing de classificação.

## Perfil de verificação

O perfil combina o tipo da Task, os critérios de aceitação, os efeitos da alteração e os portões
do projeto. O tipo sugere a verificação inicial e nunca dispensa uma verificação exigida pelo
trabalho. A verificação precisa demonstrar o resultado esperado.

| Sugestão inicial por tipo | Verificação |
| :--- | :--- |
| `feat`, `fix`, `refactor`, `test` | Sonda contrafactual e portões do consumidor. |
| `docs` | Inspeção, comparação de originais e referências. |
| `chore` | Conforme os efeitos: permissões, configuração de produção ou dependências recebem o perfil dos efeitos. |
| `research` | Fontes com localizador e data, cobertura declarada e amostragem de citações pelo Checker. |
| `analysis` | Premissas, alternativas e o que mudaria a conclusão. |

Uma sonda contrafactual é obrigatória sempre que a garantia depender de comportamento
discriminável, qualquer que seja o tipo. As provas comportamentais exigidas pelas garantias
existentes são preservadas.

### Cadência de verificação e portões de integração

O método normatiza formalmente o princípio fundamental da cadência de verificação:
**"targeted early and throughout → canonical full integration gate only at major boundary"**.
O portão completo de integração pertence ao fechamento do bloco ou fronteira principal de integração,
e não à unidade de trabalho individual.

1. **Verificação direcionada intragrupo (targeted verification):**
   Dentro de um mesmo grupo de integração (`integration_group`), as etapas de implementação,
   revisão externa e retrabalho (`changes_requested`) utilizam exclusivamente testes direcionados ao diff,
   aos pacotes e módulos alterados, aos consumidores diretos do comportamento modificado, aos critérios
   de aceitação (ACs) específicos da unidade e a sondas contrafactuais. É vedada a exigência ou execução
   rotineira da suíte global completa a cada tarefa individual dentro do grupo.

2. **Resolução de grupo de integração por autoridade:**
   A identificação do grupo de integração é resolvida semanticamente pela autoridade de governança do
   trabalho, sendo expressamente vedado o parsing *ad hoc* de convenções de nomenclatura ou uso de regex
   sobre o identificador da Story ou Task:
   - No método BMAD: pelo campo `epic` do item ou documento da story;
   - No método Native: pelo campo `deliverable` da Task;
   - Agrupamento explícito: quando expressamente configurado no mapeamento do projeto consumidor
     (`integration_group: { authority: ..., id: ... }`);
   - **Caso Standalone (tarefa isolada):** Uma Native Standalone Task (`standalone: true` ou sem Deliverable
     e sem `integration_group` explícito) constitui seu próprio grupo de integração
     (`authority: native_standalone, id: <Task_ID>`). Por constituir seu próprio grupo e delimitar uma
     fronteira autônoma, o portão canônico de fronteira é exigido ao fechar esse grupo antes de autorizar
     a transição para outro grupo independente.

3. **Portão canônico de integração na fronteira principal (canonical full integration gate):**
   O portão completo canônico de integração (`canonical_full_gate`) é disparado obrigatoriamente e
   exclusivamente no fechamento da unidade final de um grupo principal de integração (por exemplo, no
   fechamento de um Epic antes de abrir o próximo Epic no BMAD, no fechamento do Deliverable ou da
   última Task de um bloco de integração no Native, ou no fechamento de uma Standalone Task). O
   `canonical_full_gate` precisa terminar verde (sucesso); qualquer falha no portão bloqueia a transição
   para o próximo grupo de integração.

4. **Invalidação estrita da árvore:**
   O resultado da execução do `canonical_full_gate` é rigorosamente vinculado à revisão específica da
   árvore (commit SHA). Qualquer modificação de código posterior dentro do grupo invalida a prova do gate
   e exige uma nova execução integral antes que a transição de fronteira possa ser autorizada.

5. **Regime restrito de exceção antecipada:**
   A execução de um full gate antecipado dentro do grupo é estritamente excepcional e restrita a
   mudanças estruturais transversais comprovadas (por exemplo, migração de esquema de banco compartilhado,
   alteração de protocolo cross-módulo, mudança em primitivas globais de concorrência ou no sistema de build).
   Toda execução antecipada exige a inclusão de um bloco formal de metadados (`full_gate_exception`) na
   evidência e no briefing, detalhando a razão técnica objetiva e a justificativa de por que testes
   direcionados seriam insuficientes. Justificativas vagas ou genéricas como "por segurança", "para garantir tudo",
   "para confirmar" ou "para ter certeza" são expressamente nulas, inválidas e rejeitadas.

6. **Reaproveitamento de prova de CI:**
   Quando um pipeline de CI externo (como GitHub Actions) já tiver executado com sucesso o
   `canonical_full_gate` sobre o mesmo commit SHA exato da árvore e sob a mesma definição e revisão do
   portão, com logs auditáveis acessíveis, o Orquestrador pode reutilizar essa prova, sendo proibido
   duplicar a execução completa local sem justificativa técnica. Caso o comando, a configuração ou a definição
   do portão tenham sido alterados após a execução do CI, a prova anterior é nula e a verificação deve
   ser refeita integralmente.

7. **Vedação a suposições e comando não configurado:**
   O método trata o comando do portão global como `canonical_full_gate` parametrizável e agnóstico às
   tecnologias do projeto consumidor (por exemplo, `make check`, `cargo test --workspace`, `npm test`,
   `go test ./...`, `pytest`). É expressamente proibido ao Orquestrador inferir, adivinhar ou presumir
   comandos de full gate não configurados. Se o consumidor não possuir um full gate explicitamente
   configurado em `PROJECT.md` ou derivável de política documentada existente, deve registrar formalmente
   `canonical_full_gate: not_configured`, tratando isso como uma pendência bloqueante antes de autorizar
   qualquer transição de fronteira que exija o portão.

8. **Rework econômico e focado:**
   Em ciclos de retrabalho decorrentes de `changes_requested`, a re-execução de testes restringe-se
   estritamente ao patch alterado, aos consumidores impactados e aos ACs relacionados. Retrabalhos de
   natureza puramente documental, de evidência, de metadados ou de atualização de status não executam
   testes funcionais, admitindo no máximo verificações textuais e estruturais (`git diff --check`, lint).

## Discussões e decisões

`discussions/DISCnnn-slug.md` tem `status` em `open`, `resolved` ou `superseded`. Nunca é apagada
nem movida. `resolved` exige pelo menos um link de saída para `DEC`, `D` ou `T`, ou nota explícita
de ausência de trabalho resultante. O cabeçalho de `STATUS.md` lista apenas as `open`.

O modo **Discuss** é uma conversa entre Orquestrador e usuário, sem despacho e sem classificação.
É distinto de **Debater**, que exige classificação `debate` e painel em sessões separadas. A
escrita em `project/discussions/` segue a autorização de escrita da operação.

Decisões usam um arquivo por decisão. Quando a persistência estiver autorizada, uma decisão
confirmada em discussão é gravada na mesma interação, com `origin` apontando para a discussão.
Esta cláusula não autoriza gravação em atividade somente leitura.

## Papel consultivo: Advisor (Cross-Family Strategic Challenge and Escalation)

O papel **Advisor** atua como desafio estratégico, consultivo e independente de premissas, causalidade,
arquitetura e risco antes de decisões materiais caras ou difíceis de reverter. Sua pergunta orientadora
central é: **"Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"**.

### 1. Fronteira do papel e vedações estritas (Role Boundary)

O Advisor é estritamente consultivo e somente leitura (`report_only: true`), executado obrigatoriamente
em sessão nova e limpa (`fresh_session: required`). É expressamente vedado ao Advisor:
- Criar, editar, sobrescrever, mover ou excluir arquivos no repositório (`may_edit: false`);
- Realizar commits, stage ou operações de controle de versão (`may_commit: false`);
- Alterar status, revisões ou metadados de tasks, deliverables ou boards (`may_change_state: false`);
- Fechar ou aprovar qualquer tarefa ou unidade de trabalho (`may_close_task: false`);
- Conceder autorizações de escopo, orçamento ou governança (`may_authorize: false`);
- Despachar, invocar ou orquestrar outros agentes (`may_dispatch_agents: false`);
- Substituir ou dispensar a revisão independente do Checker (`may_replace_checker: false`);
- Substituir o papel do Planner na especificação detalhada de planos executáveis (`may_replace_planner: false`);
- Iniciar debates por conta própria (`may_recommend_debate: true`: limita-se a recomendar a abertura de debate formal).

### 2. Distinção clara dos quatro papéis

As responsabilidades dos papéis são mutuamente exclusivas e operam em momentos e perspectivas distintos:
- **Planner:** *"Como devemos fazer?"* — projeta arquitetura, decompõe etapas e produz especificação executável e verificável.
- **Advisor:** *"Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"* — desafio crítico consultivo de premissas, causalidade frágil, riscos ocultos e custo de reversão antes de comprometer recursos caros.
- **Checker:** *"O que foi implementado atende a spec e a prova?"* — auditoria independente posterior ao diff de implementação, verificando critérios de aceitação congelados e integridade probatória.
- **Debate:** *"Temos alternativas materialmente concorrentes; qual direção devemos escolher?"* — painel consultivo de deliberação multi-perspectiva entre três papéis (Planner, Maker, Checker) sob contraponto estruturado.

O Advisor **não é um Checker antecipado** (não inspeciona diffs de código implementado nem audita conformidade contra specs prontas) e **não é uma quarta IA obrigatória** a ser acionada rotineiramente em cada Story.

### 3. Gatilhos objetivos de acionamento

O acionamento do Advisor é excepcional e restringe-se estritamente à presença de pelo menos um dos **8 gatilhos objetivos**:
1. **Mudança em arquitetura, protocolo, autoridade, governança ou contrato compartilhado:** alteração com impacto estrutural transversal sobre múltiplos componentes ou políticas centrais.
2. **Decisão difícil de reverter:** migração ampla de dados, cutover de infraestrutura, alteração de fundação arquitetural ou remoção de retrocompatibilidade.
3. **Experimento que fundamentará decisão do método:** benchmarks, testes A/B ou medições empíricas de custo/desempenho cujos resultados alterarão regras de governança ou perfis de roteamento.
4. **Incerteza material em trabalho com tier heavy:** tarefas classificadas como `heavy` que apresentem hipóteses não comprovadas ou riscos substanciais (o tier heavy isolado não basta).
5. **Conclusão causal importante a partir de evidência limitada:** asserções causais críticas fundamentadas em amostragem empírica restrita (ex.: "técnica X reduziu tokens em 40%", "biblioteca Y é intrinsecamente mais segura").
6. **Recorrência de classe de falha descoberta somente por revisão independente:** reincidência de problemas sistemáticos que escaparam ao planejamento inicial e foram flagrados apenas tardiamente no Checker.
7. **Segundo parecer explicitamente solicitado pelo usuário:** requisição direta do operador humano demandando contra-análise estratégica independente.
8. **Antes de congelar lote automático de alto custo:** antes de autorizar a execução de lote sequencial ou autônomo de tarefas que satisfaçam algum dos critérios anteriores.

### 4. Vedações de acionamento rotineiro (Non-triggers / Anti-overuse)

É expressamente proibido ao Orquestrador acionar o Advisor por conveniência, rotina ou redundância:
- No início padrão de uma Story ou Task comum;
- Ao término da implementação do Maker;
- Na entrada padrão em fase de revisão;
- Em ciclos comuns de retrabalho (`changes_requested`) com achados delimitados;
- Em tarefas com tier `heavy` desprovidas de incerteza arquitetural material;
- Em alterações puramente documentais, metadados ou atualizações rotineiras de status;
- Sob pretextos genéricos como "segunda opinião informal", "para ter certeza" ou "por segurança".

### 5. Challenge packet mínimo e Context Economy

Seguindo os princípios de Context Economy (T015), o Orquestrador entrega ao Advisor um pacote enxuto de desafio (*challenge packet*), evitando descarregar o histórico ou a árvore completa:
- Proposição, decisão ou artefato sob desafio;
- Objetivo pretendido e restrições conhecidas;
- Fatos confirmados e evidências verificadas;
- Premissas materiais e hipóteses adotadas;
- Alternativas já consideradas e razões de descarte;
- Limites de autoridade vigentes;
- Pergunta concreta e específica formulada pelo Orquestrador.

Consultas adicionais a arquivos pontuais são realizadas pelo próprio Advisor sob demanda via ferramentas somente leitura (`view_file`, `grep_search`, `read_section.py`), sem leituras exploratórias amplas.

### 6. Regime de independência, contra-família e fallback degradado

- **Preferência padrão:** Por padrão adota-se `advisor_independence: preferred`, com execução obrigatória em sessão limpa (`fresh_session: required`).
- **Resolução de contra-família contra o conjunto completo de famílias autoras materiais:** A independência do Advisor é avaliada contra o **conjunto completo de famílias que contribuíram materialmente para o artefato desafiado** (`challenged_author_families`), e não meramente contra uma única família ou contra o último autor:
  ```text
  challenged_author_families = conjunto completo das famílias que contribuíram materialmente para o artefato desafiado
  eligible_cross_family = famílias disponíveis - challenged_author_families
  ```
  * **Casos com 1 família autora:**
    - Se `challenged_author_families = [google]` → contra-família elegível: OpenAI (Codex) ou Anthropic (Claude);
    - Se `challenged_author_families = [openai]` → contra-família elegível: Google (Agy) ou Anthropic (Claude);
    - Se `challenged_author_families = [anthropic]` → contra-família elegível: Google (Agy) ou OpenAI (Codex).
  * **Casos com pares de famílias autoras materiais:**
    - Se `challenged_author_families = [google, openai]` → contra-família elegível: obrigatoriamente Anthropic (Claude) quando disponível; não pode depender do último autor;
    - Se `challenged_author_families = [google, anthropic]` → contra-família elegível: obrigatoriamente OpenAI (Codex);
    - Se `challenged_author_families = [openai, anthropic]` → contra-família elegível: obrigatoriamente Google (Agy).
  * **Caso extremo com as 3 famílias (`[google, openai, anthropic]`):**
    - Sob `advisor_independence: required`: nenhuma família independente disponível (`eligible_cross_family = ∅`), bloqueia terminantemente o despacho do Advisor (`blocked`) com emissão de impedimento fundamentado e ponto de retomada.
    - Sob `advisor_independence: preferred`: admite fallback na mesma família em sessão nova, obrigatoriamente registrado como `advisor_independence: degraded_same_family`, com `fallback_reason` obrigatório não vazio detalhando todas as famílias conflitantes.
- **Fallback degradado sob `preferred`:** Caso nenhuma contra-família alternativa de `eligible_cross_family` esteja utilizável no catálogo e a indisponibilidade esteja comprovada, admite-se o despacho do Advisor em sessão nova como fallback degradado, com registro formal mandatório na evidência (`advisor_independence: degraded_same_family`, `fallback_reason: <motivo>`).
- **Bloqueio sob `required`:** Sob configuração explícita `advisor_independence: required`, a indisponibilidade de contra-família independente em `eligible_cross_family` bloqueia terminantemente o despacho do Advisor com emissão de impedimento fundamentado e ponto de retomada.

### 7. Saída estruturada e semântica dos cinco vereditos

A resposta do Advisor consiste exclusivamente em um objeto JSON validado contra `schemas/advisor-result.schema.json` (Draft 2020-12), com os campos obrigatórios `schema_version: 1`, `verdict`, `confidence` (`high|medium|low`), `findings`, `alternatives`, `missing_evidence`, `debate_required` (boolean) e `reason`.

Semântica operacional mandatória de cada veredito:
- `proceed`: A proposição sob desafio é sólida, premissas sustentadas e riscos gerenciáveis. O fluxo prossegue normalmente.
- `adjust`: A direção é válida, mas há premissas frágeis, parâmetros incorretos ou riscos não mitigados. Exige disposição obrigatória e justificada do Orquestrador antes do próximo despacho de planejamento ou implementação.
- `plan`: A questão carece de detalhamento formal de especificação executável ou decomposição de impacto. O Orquestrador deve classificar e despachar o Planner se autorizado.
- `debate`: Existem alternativas concorrentes materiais ou incertezas estratégicas irreconciliáveis por análise unilateral. O Advisor recomenda a abertura de Debate formal (implicando obrigatoriamente `debate_required: true` no schema). O Advisor não autoriza nem inicia o debate.
- `stop`: A premissa central é falsa, o risco de dano estrutural ou custo de reversão é proibitivo, ou há carência absoluta de evidência/autoridade. O avanço material é interrompido imediatamente até deliberação superior do usuário.

### 8. Disposição obrigatória das recomendações restritivas

Os vereditos `adjust`, `plan`, `debate` e `stop`, bem como o sinalizador `debate_required: true`, possuem efeito operacional bloqueante: é terminantemente vedado ao Orquestrador ignorá-los silenciosamente antes da próxima ação material. Cada apontamento relevante deve receber disposição formal (aceite com ajuste, encaminhamento de planejamento/debate, ou justificativa explícita de rejeição fundamentada) registrada na evidência.

### 9. Regra estrita de autoria e independência do Checker

O parecer do Advisor é estritamente consultivo e **NÃO** insere a família do Advisor no conjunto de autoria efetiva (`effective_authors`).
Somente se conteúdo substantivo (especificação de arquitetura, texto formal de spec ou trechos de código de solução) produzido pelo Advisor for copiado diretamente ou incorporado à spec ou aos `content_paths` da entrega, a família do Advisor passará a integrar `effective_authors` para fins da avaliação de independência do Checker subsequente da unidade.

### 10. Interface declarativa para o Modo Automático

Para execução em lotes automáticos (Modo Automático), a política do Advisor integra a autoridade imutável e congelada do lote via bloco declarativo `frozen_scope.advisor_policy`:
- `frozen_scope.advisor_policy` é parte integrante da autoridade congelada do lote sob `additionalProperties: false`;
- `enabled`: ativa ou desativa o acionamento de Advisors no lote; quando `enabled: false`, qualquer despacho de Advisor é categoricamente impedido (`consumed_advisor_calls` permanece 0);
- `triggers`: lista fechada de gatilhos autorizados para o lote entre os 8 gatilhos objetivos. A presença de gatilhos autorizados não autoriza recursão (`advisor -> advisor`);
- `max_calls`: limite estrito de chamadas consultivas permitidas. `frozen_scope.advisor_policy.max_calls` é a autoridade de política congelada, enquanto `budget.max_advisor_calls` é a projeção usada pelo mecanismo genérico de orçamento. É mandatória a invariância de igualdade estrita: `advisor_policy.max_calls == budget.max_advisor_calls`.

É vedado ao Orquestrador realizar chamadas espontâneas a Advisors fora do orçamento e dos gatilhos declarados na política do lote.

## Conclusão

- **Task `done`:** portões aplicáveis executados conforme a cadência de verificação estabelecida
  (verificação direcionada intragrupo, ou portão canônico de fronteira na unidade de fechamento do grupo
  ou em tarefas standalone), parecer `approved` válido vinculado ao
  `content_id` revisado, e autoridade de fechamento já concedida pela política do projeto. Sob
  `checker_independence: preferred`, o estado `done` é permitido mesmo com pendência de revisão
  posterior aberta (`status: pending`). Sob `checker_independence: required`, a ausência de parecer
  de família distinta bloqueia o fechamento com ponto de retomada; a indisponibilidade nunca
  converte `required` em `preferred`. Sob `checker_independence: required`, qualquer coincidência
  entre a família do modelo do revisor e a autoria efetiva (incluindo Makers de todas as rodadas e
  reworks prévios) constitui impedimento absoluto, obrigando o Orquestrador a emitir impedimento
  fundamentado e impedindo a aprovação da unidade. Não há confirmação humana adicional por Task por padrão.
- **Deliverable `done`:** todas as Tasks exigidas `done` e `integration_criteria` verificados
  conforme os portões aplicáveis, com aprovação obrigatória do `canonical_full_gate` na fronteira principal
  de integração. Tasks todas `done` não comprovam, por si só, que as partes funcionam juntas. Ao fechar, o
  Deliverable lista as pendências de revisão abertas de suas Tasks sem que elas bloqueiem a sua conclusão. O
  Orquestrador registra o fechamento com a evidência da verificação integrada.
- **Reuso de parecer:** alteração material posterior à revisão, isto é, novo `content_id`, impede
  o reuso automático do parecer para fechar a Task.

### Registro de revisão

Fora do parecer e sem alterar o schema, o arquivo de evidência da rodada,
`project/evidence/Tnnn-rNN.md` (ou o artefato próprio da story BMAD), registra o parecer JSON
íntegro, a unidade revisada (qualificada como `<area_id>:<id>` no modo multiárea), `spec_revision`,
`content_id` revisado, `run_id` do Checker, sessão, harness, modelo, effort, família e limitações
de independência. Sob `checker_independence: required`, o registro deve comprovar a ausência total
de sobreposição entre a família do Checker e todas as famílias registradas na autoria efetiva da
unidade (Makers originais e de retrabalhos anteriores); qualquer coincidência invalida a revisão e
impede o fechamento. É esse registro que vincula o parecer ao conteúdo e à unidade; hashes iguais em
outra unidade não transportam a aprovação.

Toda chamada a agente entra na tabela `Agent runs` da evidência (Planner, Maker, Checker, sondas e
chamadas que falharam ou tentativas descartadas). A tabela herda a identidade completa da unidade
(`unit`, [Identidade](#estado)) do cabeçalho da evidência, sem coluna própria de unidade. Formato de
`run_id`: `<unit_id>-rNN-<role>-<seq>`, único na evidência da unidade, onde `unit_id` é o `id`
qualificado da identidade sem caminho. Tentativas descartadas e chamadas falhas são preservadas com
`outcome` e `fallback_reason`. Dados não observáveis no harness são preenchidos como
`not_observable`, nunca omitidos nem inferidos.

Quando uma revisão for concluída por mesma família em sessão nova sob
`checker_independence: preferred`, a pendência nasce na rodada de revisão que a gera e mora somente
ali: no bloco `## RF-<unit_id>-rNN` em `project/evidence/Tnnn-rNN.md` da área da unidade (em
Native) ou no mesmo bloco no artefato de evidência próprio da story (em BMAD). Nenhuma Task Native é
criada para acompanhar uma story BMAD. Task, STATUS e registros BMAD apenas referenciam o bloco por
caminho e âncora (`<evidence_ref>#rf-<unit_id>-rnn`). A âncora é o slug do título que carrega o id.
Atualizações de acompanhamento são registros de controle: acrescentam entradas datadas ao `log` do
bloco, sem modificar o alvo nem o parecer original.

```text
## RF-<unit_id>-rNN
kind: review follow-up
target:
  unit: <identidade completa da unidade>
  spec_revision: <s>
  content_id: <formato de versão do trabalho: com Git, commit base mais hash do diff; sem código, hashes dos artefatos>
  content_paths: [...]
  locator: <commit | artefato preservado | not_recoverable>
origin_review: <rNN> run_id: <run_id do Checker de mesma família>
limitation: same_family_fresh_session
families_used: [<Maker, reworks, correção própria do Orquestrador, Checker>]
status: pending | superseded | closed
review_ref: <evidence#rNN run_id=...> | none
attempts: [<rNN run_id=... verdict=...>]
superseded_by: <RF-...> | none
supersedes: <RF-...> | none
reason: <texto obrigatório em superseded e em not_recoverable>
log:
  - <UTC> <evento>
```

Estados e regras do follow-up:
- `pending`: o alvo registrado aguarda parecer independente de outra família.
- `closed`: somente com parecer `approved`, em sessão nova, de família distinta de todas as
  `families_used`, cujo registro cubra exatamente o alvo (mesma unidade, mesma `spec_revision` e
  mesmo `content_id`). `review_ref` guarda evidência, rodada e `run_id`. Aprovação em outra unidade ou
  com outro `content_id` não transporta e não fecha a pendência.
- `changes_requested`: mantém o estado `pending` e registra a rodada e o `run_id` em `attempts`.
- `superseded`: exige `superseded_by` apontando para a pendência substituta sobre o conteúdo novo e
  `reason` obrigatório que explique quais garantias do alvo original continuam cobertas pelo novo alvo
  e quais foram alteradas ou retiradas, citando a decisão registrada; a ausência de `reason` é
  rejeitada (dois `content_id` sozinhos não bastam). A substituta registra sua procedência em
  `supersedes` e nasce como `pending` (se ainda faltar a revisão independente) ou `closed` (quando já
  existir parecer independente `approved` cobrindo exatamente o novo alvo com `review_ref`). A
  pendência original nunca é fechada pelo parecer do conteúdo novo, e a substituta não inventa uma
  nova revisão de mesma família: herda o `origin_review` da original.
- Alteração posterior do conteúdo sem revisão não fecha nem apaga a pendência: ela permanece
  `pending`. Se o alvo original não puder ser recuperado (`locator: not_recoverable`), a pendência
  permanece `pending` com essa limitação e `reason` obrigatório, declarando o que a revisão posterior
  pôde examinar.

A condução da revisão posterior e o que ela autoriza ou não estão no [playbook](../prompts/orchestrator-playbook.md#fechamento-ou-interrupção).

## Proteção nas atualizações

O atualizador, inclusive `auto_safe`, não sobrescreve, exclui nem migra `project/` nem os caminhos
documentais das áreas cadastradas. Esses caminhos ficam fora da mutação e da recuperação por
snapshot da atualização, que é distinta de backup documental. Leitura, validação, versionamento e
backup autorizado continuam permitidos. `PROJECT.md`, `INSTALLATION.md`,
`QUEUE.md` e `_tl-orc/evidence/` seguem o [contrato de evolução](EVOLUTION.md).

## Adapter BMAD

| Conceito Native | BMAD |
| :--- | :--- |
| Task | story |
| Deliverable | epic |
| estado | artefato do sprint, consultado |
| evidência | local declarado pela política BMAD |

O cabeçalho de coordenação permanece. `work_method: bmad` muda a fonte de estado e evidência, não
a coordenação. A tabela de Tasks nativas só existe quando há Tasks nativas.

## Fila sequencial no perfil Native

`project/STATUS.md` pode ser o `board` de `QUEUE.md`, com estas regras adicionais:

- A ordem canônica é explícita: `order` do Deliverable; para Tasks standalone, ordem topológica
  por `depends_on` com desempate por ID. Nunca a ordem incidental dos arquivos.
- A tabela apenas localiza a candidata. A Task oficial é relida antes do despacho, com estado,
  dependências e autorização conferidos.
- `cancelled` é terminal para seleção e não satisfaz dependentes: Task dependente de uma cancelada
  recebe `blocked_by` e exige replanejamento.
- `permit_state_update: true` em `QUEUE.md` autoriza somente os campos de estado da Task e a
  atualização correspondente de `STATUS.md`. Não cobre specs, decisões, contextos ou evidências.
- Sem cadastro de áreas, a fila é da área `global` implícita e o comportamento anterior continua
  integralmente. Com múltiplas áreas, filas novas declaram `area_id`; filas existentes preservam
  `scope`, `board` e permissões, e sua área só é resolvida quando inequívoca a partir de `scope` e
  `board`. Divergência exige esclarecimento, sem inferência. Atualizar o pacote não reescreve
  `QUEUE.md` nem sua autorização.
- Limites: `max_rework_rounds` por Task, `max_replans` por Deliverable com omissão igual a `1`, e
  estagnação: duas rodadas consecutivas com os mesmos achados do Checker bloqueiam e apresentam a
  decisão necessária.
- Em lotes autorizados multitarefas expressamente aprovados pelo usuário com escopo e lista delimitada, a
  transição entre tarefas concluídas e subsequentes elegíveis desbloqueadas é contínua e automática dentro
  dos limites do lote, registrando o encerramento da unidade anterior e a abertura da seguinte. Qualquer
  bloqueio impõe parada imediata da execução na unidade afetada, sendo vedado saltá-la e projetando a pendência
  em `STATUS.md`. O avanço para tarefas independentes depende de autorização explícita no lote
  (`continue_independent_on_block: true`), permanecendo a suspensão total do lote como regra por omissão.
  Perguntas ao usuário iniciam contagem de prazo no evento tecnicamente observável `question_emitted_at`
  (admitindo `transport_ack_at` se fornecido pelo canal), sendo terminantemente proibido presumir leitura humana.

## Modo Automático: execução de lote finito autorizado

O Modo Automático permite a execução autônoma de um lote finito e explicitamente autorizado de unidades já conhecidas do projeto. Ele unifica as garantias de esperas e liveness (T013), roteamento e independência (T014), economia de contexto (T015), cadência de verificação com portões de fronteira (T016) e desafio consultivo por Advisor (T017).

### 1. Natureza do sistema e não-objetivos

- **Protocolo durável documental:** T018 não cria daemon, transação distribuída, engine autônomo persistente, lock distribuído ou atomicidade de banco de dados. O Modo Automático é um protocolo durável conduzido pelo Orchestrator/harness existente através de uma disciplina documental de write-ahead serializada pelo `coordinator`.
- **Composição com o protocolo de execução:** O despacho e a execução de cada unidade individual no estado `EXECUTE` seguem o protocolo por artefatos e recebimento de recibo terminal compacto (< 4 KiB) especificado em `docs/EXECUTION_PROTOCOL.md` (e `scripts/tl_job.py`). O Modo Automático atua como a autoridade de governança do lote finito, gerenciando admissão, reserva dinâmica de orçamento, avanço dos checkpoints duráveis em `_tl-orc/project/batches/Bnnn.md`, controle de paradas e portões canônicos de fronteira de integração (T016).
- **Anti-patterns expressamente vedados:**
  * Não criar agentes indefinidamente autônomos ou auto-direcionados;
  * Não percorrer backlog de forma contínua ou descontrolada;
  * Não criar ou formalizar novas Tasks espontaneamente;
  * Não auto-autorizar escopo, orçamento, efeitos ou exceções;
  * Não manter serviços em segundo plano, daemons permanentes ou loops de polling contínuo;
  * Não presumir nem executar `git push`, PR, merge remoto, tags git ou releases sem instrução humana explícita prévia.

### 2. Máquina de estados formal

A execução de batches obedece à máquina de estados estrita:

```text
IDLE
  ↓ comando explícito do usuário: "iniciar modo automático"
DISCOVER                  # read-only: inspeção de unidades candidatas existentes no projeto
  ↓
PROPOSE                   # read-only: formulação da proposta formal estruturada do lote
  ↓
WAIT_AUTHORIZATION        # bloqueio síncrono aguardando deliberação humana
  ├── rejeição → IDLE
  ├── aprovação parcial → PROPOSE revisado (novo ciclo com recálculo)
  └── aprovação integral
          ↓
PREFREEZE_REVALIDATE      # revalidação síncrona contra drift entre proposta e autorização
  ├── drift detectado → PROPOSE revisado (invalida proposta anterior)
  └── integridade confirmada
          ↓
FREEZE_BATCH              # materialização imutável do snapshot do lote em batches/Bnnn.md
          ↓
EXECUTE                   # loop sequencial de execução por unidade com admission gate
          ↓
CLOSE                     # fechamento do lote com relatório terminal e retorno a IDLE

Saídas excepcionais: BLOCKED | STOPPED | FAILED | CANCELLED
```

- **Invariante fundamental de autorização:**
  `"iniciar modo automático" ≠ autorização para executar`
  O comando inicial do usuário autoriza única e exclusivamente a fase de leitura `DISCOVER → PROPOSE`. Nenhuma modificação de código, criação de commit, mutação de arquivo ou despacho de agentes de implementação pode ocorrer antes de uma resposta humana formal que aprove a proposta apresentada.
- **Semântica estrita de aprovação parcial:** Caso o usuário aprove apenas um subconjunto das unidades propostas (ex.: *"execute T018 e T019, deixe T020 de fora"*), a resposta humana **nunca filtra diretamente o lote no freeze**. O Orquestrador gera obrigatoriamente um novo ciclo `PROPOSE` contendo estritamente o subconjunto aprovado, recalculando dependências, orçamentos, boundaries de integração e o novo `proposal_digest`, exigindo nova confirmação explícita.
- **Revalidação pré-freeze (`PREFREEZE_REVALIDATE`):** Imediatamente antes de materializar o lote em disco no estado `FREEZE_BATCH`, o Orquestrador recalcula e revalida síncronamente: revisões de unidade, `spec_revision` de cada task, grafo de dependências, `scope_digest` e efeitos autorizados. Havendo **qualquer divergência ou drift**, a proposta anterior é considerada sumariamente inválida; é terminantemente proibido adaptar o lote silenciosamente, retornando obrigatoriamente a `PROPOSE`.

### 3. Persistência durável: modelo híbrido adotado

A Alternativa C (*runtime-only* em memória) é formalmente desqualificada e rejeitada por violar a durabilidade e a recuperação auditável exigidas pelo método.

Adota-se a arquitetura híbrida de persistência:
1. **Fonte de verdade do lote:** Arquivo dedicado `_tl-orc/project/batches/Bnnn.md` (`B001.md`, `B002.md`, ...).
2. **Projeção e coordenação da árvore:** Ponteiro enxuto de uma linha no cabeçalho global de `_tl-orc/project/STATUS.md` (`active_batch`, `batch_status`, `next_batch_id`).
3. **Regra de resolução de conflito:** Se houver qualquer divergência entre `STATUS.md` e `Bnnn.md`, a autoridade sobre o lote é `Bnnn.md`. O Orquestrador relê o batch e reconcilia a projeção em `STATUS.md`.
4. **Validação por schema:** O envelope estruturado de `Bnnn.md` é validado estritamente por `schemas/batch.schema.json` (Draft 2020-12), separando o snapshot imutável de autoridade/escopo (`frozen_scope`, `authorization`, `immutable_digest`) das seções mutáveis de progresso da execução (`status`, `budget`, `execution`). O progresso da execução não pode alterar retroativamente a autoridade ou o escopo congelado.

### 4. Contabilidade de chamadas por write-ahead lógico

O controle orçamentário baseia-se em chamadas efetivamente realizadas observadas, operado via write-ahead lógico serializado pelo coordenador da árvore.

#### 4.0. Obrigatoriedade universal de write-ahead e retries (T027)

TODA e qualquer invocação real de modelo — sem qualquer exceção — deve passar pelo ciclo de write-ahead lógico serializado. Isso se aplica a todos os papéis: `classifier`, `planner`, `maker`, `checker`, `advisor` e `searcher`. O despachador orçado `budgeted_model_dispatch` em `scripts/tl_job.py` atua como primitive obrigatório que torna estruturalmente impossível disparar um harness sem prévio registro e persistência de `pending_call` em `Bnnn.md`.

**Contabilidade estrita de retries:**
Cada tentativa real de despacho constitui um evento de consumo individual. Se um Classifier for despachado e emitir uma resposta com JSON inválido ou schema não-conforme, essa tentativa consome 1 chamada (`consumed_model_calls += 1`). Para que uma nova tentativa (retry) ocorra:
1. Recalcula-se a reserva dinâmica necessária: `required_call_reserve(current_checkpoint)`;
2. Verifica-se se: `saldo_restante = max_model_calls - consumed_model_calls >= required_call_reserve`;
3. Se o saldo for insuficiente para cobrir o ciclo completo até o Checker independente, a execução interrompe-se imediatamente com `STOP: insufficient_budget_for_unit_verification`, impedindo tentativas adicionais que deixariam a unidade sem verificação independente.

1. Verificar saldo disponível no lote: `saldo = max_model_calls - consumed_model_calls - reserved_model_calls`;
2. Reservar slots obrigatórios: `reserved_model_calls += N`;
3. Gravar `pending_call` em `Bnnn.md` com `call_id`, `role`, `phase`, `payload_digest`, `dispatched_at`;
4. Persistir estado do lote em disco;
5. Despachar a chamada ao modelo;
6. Observar o receipt / resultado estruturado;
7. Converter: `reserved_model_calls -= 1`, `consumed_model_calls += 1`;
8. Limpar `pending_call` em `Bnnn.md` (`pending_call: null`);
9. Persistir estado atualizado em disco.

#### Recuperação de crash ou interrupção

Ao reiniciar a execução do lote após falha de processo, timeout ou encerramento de sessão:
- Se `pending_call` for `null`: retoma a partir do último checkpoint confirmado;
- Se `pending_call` existir:
  * Com evidência inequívoca de conclusão (recibo/log confirma saída): contabiliza como `consumed` e prossegue;
  * Se o despacho comprovadamente não ocorreu: libera a reserva e prossegue;
  * Em caso ambíguo: contabiliza conservadoramente como `consumed` e interrompe imediatamente com `STOP`, impedindo estouro silencioso de orçamento.

### 4.1. Máquina de fallback side-effect safe e classes formais de despacho (T019)

A execução e recuperação de despachos no Modo Automático compõe o protocolo de execução ([EXECUTION_PROTOCOL.md](EXECUTION_PROTOCOL.md)) com o desacoplamento de ranking semântico e fallback de infraestrutura de T019:

#### Preflight local vs remoto (R21)
- **Preflight local:** Inspeciona executáveis no `PATH`, variáveis de ambiente, arquivos locais de configuração e credenciais estáticas sem tráfego de rede e sem invocação de CLI pesada. Se falhar, é classificado como `PRE_DISPATCH_UNAVAILABLE`. Zero chamadas são debitadas do orçamento (`reservation released`), permitindo avançar imediatamente para o próximo candidato.
- **Preflight remoto ou CLI:** Qualquer sondagem remota, handshake de rede ou invocação de CLI constitui tentativa formal. Exige gravação write-ahead no journal (`pending_call`), compromete 1 slot do orçamento e passa a auditar efeitos colaterais.

#### As quatro classes formais de resultado de despacho (R5)
1. **`PRE_DISPATCH_UNAVAILABLE`:** Indisponibilidade detectada em preflight puramente local. Zero slots consumidos. O Runtime avança com segurança para o próximo candidato da cadeia de fallback.
2. **`DISPATCH_FAILED_PROVEN_NO_EFFECT`:** Falha operacional durante execução (timeout, crash com código não-zero, recusa 429 persistente de quota). O slot é debitado como `consumed`. O fallback automático para o próximo candidato só é permitido se comprovado cumulativamente ([R14]):
   - Árvore de processos da tentativa anterior inteiramente finalizada (`process-tree terminal`);
   - Checkpoint Git limpo (`git status --porcelain` vazio);
   - `content_paths` da tarefa estritamente inalterados;
   - Ausência comprovada de efeitos externos/rede via recibo e auditoria de execução;
   - Preservação da reserva mandatória de orçamento ([R22]):
     $$\text{remaining\_budget} \ge \text{fallback\_attempt\_cost} + \text{required\_call\_reserve}(\text{current\_checkpoint})$$
3. **`DISPATCH_OUTCOME_AMBIGUOUS`:** O processo sofreu timeout, encerramento anômalo ou falha, deixando a árvore de trabalho modificada (`dirty`), arquivos não rastreados ou impossibilidade de garantir ausência de efeitos externos. 1 slot é debitado como `consumed`.
   **O fallback automático é terminantemente PROIBIDO.** O Runtime emite STOP imediato (`dispatch_outcome_ambiguous`), congela o lote e preserva o estado dirty para reconciliação humana, impedindo que um candidato subsequente sobrescreva ou corrompa modificações parciais.
4. **`SEMANTIC_FAILURE`:** O processo encerra com código 0 e recibo terminal válido (< 4 KiB), mas a solução falha em testes de verificação ou o Checker emite achados no parecer. Não aciona fallback de infraestrutura; avança para o fluxo formal de retrabalho (*rework*) ou reclassificação.

### 5. Admission gate por unidade e reserva dinâmica de orçamento

#### Admission gate por unidade

Antes de admitir qualquer unidade para execução no loop `EXECUTE`:
1. `authority` permanece válida e inalterada;
2. `batch membership` confirmado (unidade presente no snapshot `frozen_scope`);
3. `revision` e `spec_revision` confirmadas sem drift em relação ao snapshot;
4. `dependencies` da unidade totalmente satisfeitas (`status == done`);
5. `coordinator` válido e ativo em `STATUS.md`;
6. `tree_state == expected_checkpoint` (HEAD esperado e árvore de trabalho limpa);
7. efeitos necessários contidos em `permitted_effects`;
8. saldo orçamentário suficiente para a reserva mandatória dinâmica.

#### Cálculo dinâmico da reserva mandatória de orçamento

A reserva mandatória de orçamento não é um número fixo universal, sendo calculada dinamicamente para cada unidade:

$$\text{required\_call\_reserve} = \text{todas as chamadas obrigatórias ainda não consumidas do checkpoint atual até o Checker independente}$$

- A admissão de uma unidade exige garantia de orçamento para cobrir todo o caminho obrigatório até a revisão independente, incluindo Classifiers obrigatórios de cada fase, Maker, Checker e, quando já exigidos pela política ou contexto, Planner ou Advisor.
- Exemplos típicos no fluxo comum (ilustrativos, nunca constantes normativas):
  * Unidade nova simples típica: $\ge 4$ chamadas (`Classifier impl + Maker + Classifier rev + Checker`); caso Advisor ou Planner entrem no caminho, a reserva sobe proporcionalmente.
  * Antes de despachar o Maker (com Classifier de impl já consumido): $\ge 3$ chamadas (`Maker + Classifier rev + Checker`).
  * Antes de retrabalho (*rework*): exige saldo para todo o ciclo restante até o re-review independente ($\ge 4$ chamadas para `Classifier rework + Maker + Classifier rev + Checker`).
- Se o saldo restante for inferior a `required_call_reserve`:
  $$\text{STOP: } insufficient\_budget\_for\_unit\_verification$$

#### Simetria de `bad_spec_or_intent_gap`

A sinalização de incerteza material insolúvel, contradição de autoridade ou lacuna de intenção opera simetricamente:
- Se apontada pelo Classifier da fase ou por verificação estática pré-Maker: interrompe a unidade antes de despachar o Maker (`STOP: bad_spec_or_intent_gap`), evitando consumo inútil de chamadas;
- Se apontada pelo Checker independente em seu parecer: interrompe antes de autorizar retrabalho automático.

#### Limites estritos de retrabalho automático

O avanço automático em `changes_requested` é restrito a achados direcionados ao Maker, contidos na `spec_revision` e `content_paths` congelados, sem alteração de arquitetura ou produto, respeitando `max_rework_rounds_per_unit` e dispondo de saldo para todo o ciclo restante de rework até o re-review independente.

### 6. Fronteiras de integração T016 dentro do lote

Um único lote pode conter unidades de diferentes grupos de integração (`integration_groups`). A cadência de verificação T016 aplica-se com rigor:
1. Dentro do mesmo grupo de integração: verificação direcionada (*targeted verification*);
2. Na transição de um grupo de integração para outro dentro do batch: execução obrigatória do `canonical_full_gate` oficial na fronteira do grupo que encerra. Falha no portão bloqueia com `STOP: canonical_full_gate_failure`;
3. No encerramento da última unidade do último grupo: execução obrigatória do `canonical_full_gate` antes de transitar para `CLOSE`.

### 7. 18 Condições formais de parada (*Stop conditions*)

A execução do lote é imediatamente interrompida (`STOP`), projetando a interrupção em `STATUS.md` e devolvendo o controle ao usuário, sob qualquer uma das 18 condições formais:

1. `authority_missing_or_ambiguous`: ausência de comando formal explícito.
2. `scope_expansion`: tentativa de escrita fora dos `content_paths` congelados.
3. `new_work_outside_frozen_batch`: necessidade de Task nova não presente no snapshot.
4. `model_call_budget_exhausted`: orçamento de chamadas do lote esgotado.
5. `rework_limit_exhausted`: esgotamento do número de rodadas de retrabalho da unidade.
6. `insufficient_budget_for_unit_verification`: saldo restante inferior a `required_call_reserve`.
7. `required_checker_independence_unavailable`: indisponibilidade de família independente sob política `required`.
8. `required_advisor_independence_unavailable`: indisponibilidade de consultor independente sob política `required`.
9. `advisor_verdict_stop`: parecer de parada emitido pelo Advisor.
10. `advisor_verdict_debate` (ou `debate_required: true`): necessidade de deliberação sem autorização prévia de debate.
11. `bad_spec_or_intent_gap`: especificação inconsistente ou lacuna de intenção levantada por Classifier ou Checker (simétrico).
12. `canonical_full_gate_failure`: falha de portão canônico em fronteira de grupo ou fechamento.
13. `coordinator_conflict`: divergência de coordenador da árvore.
14. `unexpected_tree_state`: árvore de trabalho não condiz com `expected_tree_checkpoint`.
15. `unexpected_revision_drift`: divergência de revisão em relação ao snapshot congelado.
16. `external_effect_not_authorized`: tentativa de invocar push, PR, merge, tag ou rede sem autorização.
17. `unrecoverable_harness_failure_or_ambiguous_dispatch`: falha persistente de infraestrutura de harness ou desfecho de despacho ambíguo (`DISPATCH_OUTCOME_AMBIGUOUS` com árvore de trabalho dirty), bloqueando fallback automático para evitar corrupção de workspace.
18. `dependency_block`: bloqueio de dependência de unidade no lote.
    - O comportamento padrão é `continue_independent_after_block: false` (interrompe no primeiro bloqueio). Continuidade restrita a ramos topologicamente independentes exige autorização expressa no lote.

### 8. Fechamento do lote (`CLOSE`) e invariante terminal

O lote transita para `CLOSE` quando:
1. Todas as unidades do lote atingem `status: done`;
2. O portão canônico de integração de fronteira final (`canonical_full_gate`) passa com exit 0;
3. O status do lote em `batches/Bnnn.md` é atualizado para `done`;
4. `active_batch` em `STATUS.md` é atualizado para `none` e `batch_status: none`;
5. É gerado o relatório terminal ao usuário contendo sumário de unidades, chamadas consumidas e evidências;
6. O sistema retorna ao estado `IDLE`.
- **Invariante terminal:** O fechamento de um lote **nunca** cria ou dispara outro lote automaticamente, exceto sob `AUTO_STORY` (seção 10), em que a autorização humana já cobre explicitamente a Story inteira e o lote filho é derivado — não autorizado de novo.
- **Runtime durável (opcional, v0.19.0):** os estados `EXECUTE` → `CLOSE` de um lote já congelado podem ser conduzidos por [`scripts/tl_runtime.py`](RUNTIME.md) sem sessão de Orquestrador aberta. Ele preserva estes invariantes (lote finito, efeitos permitidos, reserva de verificação, condições de parada, fechamento sem novo lote) e acrescenta journal de steps com retomada após crash. `DISCOVER`, `PROPOSE` e `AUTHORIZE` continuam humanos/Orquestrador.

### 9. Autoridade de Merge Out-of-Band, Vinculação de Commits e Modos Operacionais (T028)

A fronteira entre preparação técnica e autorização executiva de merge obedece a regras formais invioláveis:

- **Distinção fundamental de autoridade:** `technical_merge_validity != operator_authority` e `permitted_effects.pull_request_merge == capability != authorization`.
  * Aprovação formal por Checker independente e portões de CI verdes conferem exclusivamente **validade técnica de preparação**.
  * A flag `permitted_effects.pull_request_merge: true` declara unicamente a **capacidade técnica** do runtime/agente de interagir com o mecanismo de merge do GitHub quando formalmente autorizado. Ela **nunca** concede autorização de execução por si só.
  * O merge para a base protegida (`main`) exige estritamente um envelope out-of-band confirmado (`AuthorityReceipt`) avaliado pelo `MergeAuthorityGate` (`scripts/tl_merge_guard.py`).

- **Vinculação estrita de commits em duas etapas:**
  1. `checker_approved_commit`: o commit exato aprovado pelo Checker independente.
  2. `integration_candidate_commit`: o commit final preparado para integração e merge.
  * O `integration_candidate_commit` só pode diferir do `checker_approved_commit` pelos caminhos expressamente catalogados na allowlist normalizada `post_review_governance_delta_only`:
    - `_tl-orc/project/tasks/*.md`
    - `_tl-orc/project/evidence/*.md`
    - `_tl-orc/project/STATUS.md`
  * Qualquer alteração fora dessa allowlist (código-fonte, testes, automações, schemas, scripts) invalida o vínculo e exige obrigatoriamente uma nova rodada completa de revisão por Checker independente.

- **Modos operacionais de merge:**
  1. `delegated_single_merge`: O operador humano delega a execução de um único merge para um par estrito `(target_pr, expected_head_sha, expected_base_sha)`. A autorização é consumida atomicamente contra replay via CAS (`unused -> reserved -> consumed/indeterminate`) em store externo.
  2. `human_merge_only`:
     - Modo `enforced`: Qualquer tentativa de merge automatizado é terminantemente bloqueada e rejeitada; o merge na plataforma depende exclusivamente de ação manual do operador humano.
     - Modo `policy_only`: O runtime/orquestrador prepara o PR, aguarda CI, mas para e estaciona a unidade em `awaiting_operator`, aguardando que o operador humano realize o merge diretamente.
  - **Degradação segura:** Qualquer falha de infraestrutura, erro no store de autoridade, ambiguidade ou expiração de token degrada imediatamente e com segurança para `human_merge_only.enforced` (`FAIL_CLOSED`), nunca para merge desprotegido.

- **Arquitetura de enforcement em duas camadas:**
  * **Camada 1 (Interna/Runtime):** O primitive canônico `MergeAuthorityGate` em Python é avaliado por todos os effect producers (`tl_runtime.py`, `tl_run_story.py`, `tl_supervisor.py`). Nenhum comando `gh pr merge` ou `git merge` para a base protegida é executado sem a apresentação de um `AuthorityReceipt` válido e confirmado.
  * **Camada 2 (Plataforma GitHub):** Ruleset configurado na branch `main` exigindo Pull Request com linear history, branch estritamente atualizada contra a base e status check obrigatório `Merge Authority` emitido exclusivamente pela Dedicated GitHub App confiável (restringido pelo seu `integration_id`). A credencial de trabalho do agente não possui permissão para emitir esse status check nem contornar o ruleset.

- **Transporte out-of-band e invalidação por drift:**
  * O envelope de autorização trafega fora da árvore da branch candidata (via PR Comment metadata formatado estritamente como bloco markdown de código `json:tl-merge-authorization`).
  * O parser do transporte é determinístico e estrito: 0 envelopes → ausência de autorização; 1 envelope válido → verificação prossegue; >1 envelopes válidos distintos → parada imediata por ambiguidade (`FAIL_CLOSED: ambiguous_merge_authorization`).
  * **Invalidação imediata por drift:** Qualquer avanço na ponta da base (`base drift`) ou novo commit na branch do PR (`head drift`) invalida instantaneamente a autorização.

### 10. Story Authority Envelope e lotes filhos autônomos (`AUTO_STORY`, T032)

Motivação empírica: no ciclo real B013→B014 da Story 2.10 do projeto Lynvia, o lote B013
executou Classifier, Maker, Checker R01, Classifier de rework, Maker de rework e Checker R02,
atingiu `rework_limit_exhausted` com 98% da implementação aprovada e restaram dois apontamentos
cirúrgicos. Como a autoridade era por digest pontual de proposta, o sistema foi obrigado a parar
e exigir do operador uma nova autorização criptográfica manual só para abrir o B014 — que
herdou o commit funcional preservado, corrigiu os dois pontos e fechou a Story. `AUTO_STORY`
remove esse atrito artificial sem afrouxar nenhuma garantia.

- **Opt-in estrito e retrocompatibilidade:** `authorization.story_authority_mode` ausente
  significa `direct_proposal` — a semântica de lote único, validada contra
  `schemas/batch.schema.json`, inalterada. Nenhuma migração de histórico é exigida.
- **Separação entre autoridade e consumo:** o envelope imutável vive em
  `_tl-orc/project/story-authorities/<authority_id>.json` e nunca é reescrito para registrar
  saldo. O estado operacional mutável vive em
  `_tl-orc/runtime/story-authorities/<authority_id>/` (`journal.jsonl` append-only com
  write-ahead, fsync, hash-chain e escritor único sob `lease.lock`; `status.json` é
  exclusivamente projeção reconstruível).
- **Autorização acíclica por digest:** `root_authority_digest = SHA256(canonical_json(authority_payload))`,
  onde `authority_payload` contém exclusivamente os doze campos submetidos à decisão humana. O
  próprio digest, `authorized_at`, `authorized_literal` e qualquer metadado posterior ficam
  fora do cálculo. A autorização é a frase canônica exata
  `AUTORIZO STORY <work_ref> sha256:<root_authority_digest>`, julgada byte a byte sem qualquer
  normalização (espaço, tab ou quebra de linha a mais é recusa); ao carregar, o digest é
  recalculado e qualquer divergência é `HARD STOP` por `state_integrity`.
- **Derivação sem assinatura fabricada:** o runtime nunca inventa autorização para o filho. A
  autoridade derivada é provada pela cadeia `root_authority_digest` + `parent_authority_digest`
  + `parent_batch_digest` + `child_proposal_digest` + `derivation_proof_digest`, e só existe
  porque o filho é subconjunto estrito e verificável do envelope original. A proposta e a prova
  são registradas inteiras no evento `child_derived`, e o runtime só executa um lote depois de
  recuperar as registradas para exatamente `batch.id`, recalcular seus digests e re-provar
  envelope, linhagem e cadeia (`bind_child_batch`). Só o primeiro filho pode não ter pai; todo
  outro declara um pai derivado, fechado `changes_requested` e último revisado.
- **Escopo monotônico:** é a **união** `child.required ∪ child.conditional` que precisa estar
  contida em `parent.authorized_write_scope`; um path condicional no pai pode virar obrigatório
  no filho após apontamento factual do Checker. `forbidden_paths` e `protected_paths` só podem
  crescer, e os itens herdados de `protected_paths` preservam policy e parâmetros idênticos. Um
  path proibido aninhado num escopo amplo continua proibido: ele entra como `do_not_touch` no
  Context Pack do Maker e a contenção pós-Maker restaura a árvore se for tocado.
- **Derivação estritamente patch-only:** todos os apontamentos residuais precisam ser
  `target_role = maker`, `category = patch`, `scope_status = inside_parent_envelope` e
  `spec_status = unchanged`, com os dois últimos recalculados mecanicamente contra o envelope.
  `bad_spec`, `intent_gap`, `human`, `security`, `scope_expansion`, `new_boundary`, `migration`,
  `capability_expansion` ou dúvida de intenção interrompem e devolvem o controle ao operador. A
  heurística "lote não aprovado ⟹ criar próximo lote" é proibida.
- **Contabilidade global única:** o ledger da Story Authority é a fonte de verdade do orçamento
  global; o budget do filho é subalocação/projeção. Uma chamada física conta exatamente uma vez,
  sob um `global_attempt_id` que os dois ledgers referenciam. `logical_call_id` identifica a
  operação cognitiva; cada tentativa física recebe um `global_attempt_id` novo, com estados
  `reserved`, `consumed`, `released` e `ambiguous` (contado conservadoramente como consumido).
  Na retomada o journal da autoridade é autoritativo e o ledger do filho é reconciliado a partir
  dele, nunca o inverso.
- **Linhagem funcional:** `governance base`, `functional checkpoint` e `integration candidate`
  são coisas distintas. Um filho que termina `changes_requested` com apontamentos elegíveis não
  é mesclado em `main`, e o próximo filho não reinicia da base de governança: nasce exatamente
  do `checker_reviewed_commit` preservado. O Checker seguinte revisa o candidato cumulativo
  `story_baseline_commit..integration_candidate_commit`.
- **Subordinação ao T028 e fronteira da Story:** `allowed_effects.merge = true` é flag de
  capacidade técnica e não constitui bypass do `MergeAuthorityGate`/`AuthorityReceipt`.
  `AUTO_STORY` encerra compulsoriamente quando a Story autorizada atinge `CLOSE`/`done`; avançar
  para a próxima Story do backlog sem nova autorização humana é terminantemente proibido.

O ciclo de vida completo, os eventos do journal, o registro fechado de asserções e os modos de
protected path estão em [RUNTIME.md](RUNTIME.md#auto_story-uma-autorização-humana-por-story-t032).

## Autorizações de escrita

| Escrita | Autorização |
| :--- | :--- |
| Campos de estado da Task e visão central | Orquestrador, dentro da unidade autorizada; na fila, `permit_state_update: true`. |
| Spec, Deliverable, Decision, Discussion | Escopo autorizado da operação e do papel; `permit_state_update` não cobre. |
| `project/evidence/` | Maker na seção de evidência da sua rodada; Orquestrador no registro de revisão. |
| `context/` e `imports/` | Task de Import Context ou Task com `affects_context`; nunca por descoberta de `stale` em ativação somente leitura. |
| `project/` pelo atualizador | Proibido sobrescrever, excluir ou migrar. |

A localização de arquivos na mesma pasta não amplia autorização.

## Import Context

A operação aproveita documentos existentes, como PRD, arquitetura, epics, stories, decisões,
status e evidências, para produzir contextos pequenos, rastreáveis e carregados sob demanda, sem
transferir a autoridade do trabalho. Um resumo de epic não cria Deliverable Native nem converte
stories em Tasks.

### Documentos derivados

`context/INDEX.md` cataloga features com `id`, nome, descrição curta, palavras-chave, `status`
do brief, epics e stories de origem e links. Lista features com briefs `current` e `stale`; exclui
`retired` da seleção padrão, mantendo a referência histórica.

`context/features/Fnnn-slug.md` é um Feature Brief com cabeçalho `id`, `status` em `current`,
`stale` ou `retired`, `sources` com caminho, seção e revisão ou hash, `imports` e `last_verified`.
Seções fixas:

| Seção | Conteúdo |
| :--- | :--- |
| Purpose | O que a feature faz e para quem. |
| Behavior | Comportamento esperado e regras importantes; cada item marcado `planned` ou `implemented`. |
| Implementation | O que foi confirmado no código e onde; cada item `confirmed` diz o que foi confirmado, por qual evidência e em qual revisão. |
| Constraints | Invariantes, restrições e decisões a preservar. |
| Dependencies | Relações com outras features e componentes. |
| Open Questions | Diferenças entre planejamento, documentação e implementação. |
| Sources | Documentos, seções, decisões e evidências, com revisão. |

Atualidade e evidência são distintas. `current` diz que as fontes não mudaram desde
`last_verified`; não diz que a funcionalidade existe. `planned` e `implemented` descrevem a
situação do comportamento; `confirmed` é uma afirmação com evidência e revisão.

`imports/IMPnnn.md` registra `source_method`, fontes inventariadas com revisão, classificação
vigente ou superada, correspondência nos dois sentidos entre fontes e briefs, divergências
encontradas, data e sessão.

Briefs são derivados e herdam a regra do guia: dado em `_tl-orc/` não prevalece sobre as fontes.
O cabeçalho de cada brief declara isso. Conflito entre brief e fonte é registrado em Open
Questions, e a fonte prevalece.

### Carregamento e envelhecimento

Para uma unidade de trabalho, o Orquestrador seleciona o conjunto inicial: `CONTEXT.md`,
`INDEX.md`, briefs das features afetadas e das dependências diretas, unidade ativa e decisões
referenciadas. Planner, Maker e Checker podem ampliar a consulta quando o trabalho exigir e
registram o que ampliaram. Consultar fontes quando necessário é comportamento correto,
especialmente para o Checker, que confere as fontes das afirmações relevantes à revisão. Brief
`stale` continua encontrável; seu conteúdo exige conferência das fontes relevantes antes de
orientar a execução.

Na ativação que carrega um brief, o Orquestrador compara as revisões de `sources` com o estado
atual e, em caso de divergência, trata o brief como `stale`. A descoberta não autoriza gravação:
em ativação somente leitura, o Orquestrador relata; a atualização persistente segue as permissões
da operação. Cada Task declara `affects_context`; quando houver mudança de comportamento,
contrato ou decisão, atualizar os briefs afetados entra nos critérios de conclusão. Alterações
externas ao fluxo exigem nova conferência das fontes antes de usar o brief como contexto.

### Execução da importação

A operação roda pelo ciclo do método, como Deliverable Native com `method: native`, sem tocar a
autoridade sobre as unidades de produto:

1. **Inventariar:** localizar fontes nos caminhos configurados e registrar vigentes e superadas
   em `IMPnnn`.
2. **Gerar:** o Planner define o recorte por feature; o Maker produz `INDEX.md`, briefs e
   correspondências; regras globais vão para `CONTEXT.md`, sem repetição por brief.
3. **Verificar:** o Checker procura omissões, afirmações sem apoio, regras essenciais perdidas na
   síntese e marcações `confirmed` sem evidência.
4. **Registrar:** fechamento com evidência. Os originais permanecem acessíveis; mover ou arquivar
   só depois de verificar referências e concluir a transferência de autoridade.

### Migration Findings

Durante Import Context e, quando existir, Migrate Work, o Orquestrador registra erros, bugs e
suspeitas materiais encontrados na análise como unidades na fila de trabalho da área responsável.
O registro faz parte da operação autorizada e não exige nova decisão do usuário por achado; ele
acrescenta captura e triagem documental, sem transferir autoridade nem executar correção.

- **Unidades novas.** A política da operação seleciona explicitamente `method: native` para os
  achados novos, mesmo quando o trabalho de produto continua em BMAD. Bug confirmado gera Task
  `type: fix` em `status: draft`. Suspeita sem confirmação gera Task `type: analysis`, também
  `draft`, com a hipótese e a verificação necessária, sem ser apresentada como bug comprovado. O
  tipo não decide método nem capacidade do executor.
- **Área.** A Task fica na área responsável pela correção; problemas de escopo global ficam em
  `global`. Em projetos sem módulos, todos os achados ficam em `global`, sem cadastro adicional.
  Referências entre áreas seguem [Referências entre áreas](#referências-entre-áreas).
- **Evidência mínima.** A Task registra origem (importação e epic, story ou documento, quando
  existirem), fonte com caminho e revisão, comportamento esperado e observado, evidência ou passos
  de reprodução disponíveis, impacto observado, incertezas e próximo passo de verificação. Uma
  divergência entre documentos é registrada como tal, sem presumir falha no código. O registro de
  importação e as Open Questions dos briefs afetados apontam para a unidade correspondente.
- **Deduplicação e autoridade.** Antes de criar uma Task, confira unidades relacionadas nas fontes
  autoritativas da área. Se a mesma correção já estiver registrada, reutilize a referência e
  vincule a nova evidência no registro da operação, sem criar outra unidade nem alterar o estado
  original. Uma unidade BMAD existente continua na fila BMAD até transferência deliberada; não
  ganha cópia Native nem é despachada pelos dois métodos. Repetir a importação não recria os
  mesmos achados.
- **Visibilidade e prontidão.** A Task nova aparece na tabela derivada de `STATUS.md` da área com
  o estado real `draft`. O Orquestrador promove para `ready` somente depois de cumprir o contrato
  de spec, critérios e verificação. O registro não habilita `QUEUE.md`, não amplia suas
  permissões e não torna um item `draft` elegível para execução. A correção segue o ciclo normal
  de classificação, planejamento quando exigido, Maker e Checker, dentro da autorização aplicável.
- **Coordenação e escopo.** Criação de Tasks, alocação de IDs e atualização das projeções seguem
  a coordenação global e a regra de um escritor por árvore. Descobrir um bug não amplia o escopo
  para modificar código ou corrigir produto durante a migração; correções já cobertas por uma
  autorização vigente seguem essa autorização.
- **Bloqueios.** Um bug preexistente não bloqueia automaticamente toda a importação ou migração.
  Se impedir o critério de conclusão ou a transferência correta de autoridade, bloqueie apenas a
  unidade afetada, registrando `blocked_by` com a referência e o motivo. Os demais achados
  permanecem visíveis na fila, sem declarar resolvida uma funcionalidade que continua com defeito.

Um piloto mede contexto inicial carregado, leitura adicional efetiva, qualidade das respostas
sobre a feature e custo de criação e atualização. A meta é reduzir redescoberta e leitura
irrelevante, não premiar a ausência de consulta às fontes. A entrega mínima de um piloto é o
índice, os briefs de um epic, o mapa de origem, a lista de divergências e essas medidas, sem
mudar o método do projeto.

## Migrate Work

Transferir a autoridade de unidades existentes para o perfil Native é uma operação separada,
explicitamente autorizada e nunca inferida de Import Context. Uma implementação deve satisfazer:

- mapa persistente entre a unidade original e a unidade Native;
- definição explícita de qual método passa a governar cada unidade, registrada na unidade Native;
- desativação do despacho daquela unidade pelo fluxo anterior; não se presume que o BMAD aceite
  um estado como `migrated`, e se os consumidores antigos continuarem podendo despachá-la sem
  respeitar a transferência, a migração permanece bloqueada;
- referência na origem quando o formato e a autorização permitirem;
- stories pendentes ou em andamento podem virar Tasks preservando origem, dependências e
  evidências; stories concluídas permanecem como histórico referenciado e não são reexecutadas.

## Templates

Os blocos abaixo são modelos; substitua placeholders apenas por valores observados e mantenha
campos desconhecidos como desconhecidos.

### STATUS.md (área global; exemplo do modo padrão, sem áreas cadastradas)

```text
format_version: 1
work_method: native
active_work_ref: native/task/T001@_tl-orc/project/tasks/T001-slug.md
active_batch: B001
batch_status: in_progress
current_role: orchestrator
next_action: <frase curta>
coordinator:
  harness: <harness>
  session: <id>
  started_at: <UTC>
  last_write_at: <UTC>
  released: false
review_followups: []
next_task_id: 2
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
next_batch_id: 2
open_discussions: []

## Tasks
| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
```

Em projetos com `work_method: bmad`, o cabeçalho global usa `work_method: bmad`, `review_followups: []`
e a mesma estrutura de coordenação, sem tabela de Tasks nativas.

### STATUS.md de módulo (somente no modo multiárea)

```text
format_version: 1
area_id: billing
coordination: global
work_method: bmad
active_work_ref: bmad/story/billing:S-12@modules/billing/_bmad-output/sprint.md
current_role: none
next_action: <frase curta>
next_task_id: 1
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
open_discussions: []

## Tasks
| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
```

No STATUS global, com áreas cadastradas, `active_work_ref` passa à forma qualificada, por exemplo
`active_work_ref: native/task/billing:T001@modules/billing/_tl-orc/project/tasks/T001-slug.md`,
mesmo quando a unidade corrente é da área `global` (`global:T001`), e acrescente a projeção:

```text
## Areas
| area_id | work_method | active_work_ref | status |
| :--- | :--- | :--- | :--- |
| billing | bmad | bmad/story/billing:S-12@… | modules/billing/_tl-orc/project/STATUS.md |
```

### CONTEXT.md

```text
# Context
## Objectives
## Constraints
## Cross-cutting rules
## Sources
```

### Task

```text
id: Tnnn
type: <type>
deliverable: <Dnnn|none>
standalone: <true|false>
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: <DISCnnn|Dnnn|user>
decisions: []
spec_author: <planner|orchestrator>
spec_revision: <hash>
rework_round: 0
affects_context: []
content_paths: []
content_id: <unknown até a implementação>

## Spec
### Intent
### Scope and write paths
### Acceptance criteria
### Verification profile
## Result
## Evidence
## Review
```

### Batch (Bnnn.md)

```text
id: Bnnn
status: <in_progress|done|blocked|stopped|failed|cancelled>
batch_revision: 1

authorization:
  proposal_id: <proposal_id>
  proposal_digest: <sha256:...>
  authority_source: explicit_user_authorization
  authorized_at: <ISO-timestamp>
  permitted_effects:
    local_write: true
    local_commit: true
    local_merge: false
    pull_request: false
    pull_request_merge: false  # capacidade técnica (T028); execução estritamente requer autorização out-of-band
    ci_rerun: false
    push: false
    tag: false
    release: false
  continue_independent_after_block: false

frozen_scope:
  advisor_policy:
    enabled: true
    triggers:
      - architecture_or_contract_change
      - heavy_tier_material_uncertainty
    max_calls: 2
  units:
    - work_ref: <Tnnn>
      revision: 1
      spec_revision: <hash>
      integration_group: <group-id>
      dependencies: []
      checker_approved_commit: <40-hex-sha>      # T028: commit aprovado pelo Checker
      integration_candidate_commit: <40-hex-sha> # T028: commit preparado para integração
      authority_mode: delegated_single_merge     # T028: delegated_single_merge | human_merge_only
      authorization_id: <auth-32hex>             # T028: identificador acíclico da autorização

  integration_groups:
    <group-id>: [<Tnnn>]
  major_boundaries:
    - from: <group-id>
      to: batch_closure
      gate: <command>
  stop_conditions:
    - authority_missing_or_ambiguous
    - scope_expansion
    - new_work_outside_frozen_batch
    - model_call_budget_exhausted
    - rework_limit_exhausted
    - insufficient_budget_for_unit_verification
    - required_checker_independence_unavailable
    - required_advisor_independence_unavailable
    - advisor_verdict_stop
    - advisor_verdict_debate
    - bad_spec_or_intent_gap
    - canonical_full_gate_failure
    - coordinator_conflict
    - unexpected_tree_state
    - unexpected_revision_drift
    - external_effect_not_authorized
    - unrecoverable_harness_failure
    - dependency_block
  immutable_digest: <sha256:...>

budget:
  max_model_calls: 24
  consumed_model_calls: 0
  reserved_model_calls: 0
  max_rework_rounds_per_unit: 2
  max_advisor_calls: 2
  consumed_advisor_calls: 0
  pending_call: null

execution:
  current_unit: <Tnnn|null>
  current_phase: <phase|null>
  current_round: 0
  expected_tree_checkpoint: <commit_sha_ou_tree_digest>
  completed_units: []
  stop_reason: null
```

### Deliverable

```text
id: Dnnn
method: native
goal:
done_when:
integration_criteria:
tasks: []
order: []
status: draft
origin:
decisions: []
```

### Decision

```text
id: DECnnn
kind: <architecture|product|operational>
status: <confirmed|superseded>
origin: <DISCnnn|user>
## Context
## Options
## Choice
## Rationale
```

### Discussion

```text
id: DISCnnn
status: open
## Question
## Context refs
## Options
## Confirmed decisions
## Hypotheses
## Open questions
## Resulting work
```

### Evidence round

```text
unit: <identidade completa da unidade>
round: rNN
spec_revision:
content_id:
content_paths: []

## Agent runs
| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| <unit_id>-rNN-maker-01 | maker | <harness> | <model> | <effort> | <family> | <session> | implementation | rNN | success | none |
| <unit_id>-rNN-checker-01 | checker | <harness> | <model> | <effort> | <family> | <session> | review | rNN | success | none |

## Commands and exits
## Own proof
## Review record
run_id: <unit_id>-rNN-checker-01
harness / model / effort / family / session / independence:
### Verdict (JSON, íntegro)

## RF-<unit_id>-rNN
kind: review follow-up
target:
  unit: <identidade completa da unidade>
  spec_revision: <hash>
  content_id: <hash base+diff ou artefatos>
  content_paths: [...]
  locator: <commit | artefato preservado | not_recoverable>
origin_review: rNN run_id: <unit_id>-rNN-checker-01
limitation: same_family_fresh_session
families_used: [<famílias dos Makers, reworks, Orquestrador e Checker>]
status: pending
review_ref: none
attempts: []
superseded_by: none
supersedes: none
reason: none
log:
  - <UTC> pendência criada por revisão de mesma família sob preferred
```

`run_id` segue o formato `<unit_id>-rNN-<role>-<seq>`, único na evidência da unidade; `unit_id` é o
`id` qualificado da [identidade completa da unidade](#estado) sem caminho. A tabela `Agent runs` herda a identidade
completa `unit` do cabeçalho da evidência; tentativas descartadas e chamadas falhas são preservadas,
e dados não observáveis usam `not_observable`. O bloco `## RF-<unit_id>-rNN` é incluído quando a
revisão de mesma família gerar pendência sob `preferred`.

### INDEX.md

```text
| id | feature | status | keywords | sources | brief |
| :--- | :--- | :--- | :--- | :--- | :--- |
```

### Feature Brief

```text
id: Fnnn
status: current
last_verified: <UTC>
imports: [IMPnnn]
sources:
  - path: <caminho>
    section: <seção>
    revision: <commit ou hash>
precedence: derived; sources prevail

## Purpose
## Behavior
## Implementation
## Constraints
## Dependencies
## Open Questions
## Sources
```

### Import record

```text
id: IMPnnn
source_method: <bmad|other>
date: <UTC>
session: <id>
## Inventory
## Source → brief
## Brief → sources
## Divergences
```
