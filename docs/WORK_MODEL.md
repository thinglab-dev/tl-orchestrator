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
    ├── STATUS.md                   # coordenação e tabela derivada
    ├── CONTEXT.md                  # contexto global curto
    ├── tasks/Tnnn-slug.md
    ├── deliverables/Dnnn-slug.md
    ├── decisions/DECnnn-slug.md    # um arquivo por decisão
    ├── discussions/DISCnnn-slug.md
    ├── evidence/Tnnn-rNN.md        # um arquivo por Task e rodada; rodadas anteriores preservadas
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
- **Cabeçalho de coordenação:** presente tanto em `native` quanto em `bmad`.

```text
format_version: 1
work_method: <native|bmad>
active_work_ref: <method>/<unit_type>/<id>@<source_location>
current_role: <orchestrator|planner|maker|checker|none>
next_action: <frase curta>
coordinator:
  harness: <codex|claude|agy|other>
  session: <identificador observado ou declarado>
  started_at: <UTC>
  last_write_at: <UTC>
  released: <true|false>
next_task_id: <n>
next_deliverable_id: <n>
next_decision_id: <n>
next_discussion_id: <n>
open_discussions: [DISCnnn]
```

`active_work_ref` identifica a unidade ativa por método, tipo, ID e localização da fonte, e pode
apontar para um Deliverable em planejamento antes de existir Task ativa. Trabalho externo aparece
por referência; o estado de uma story é consultado no artefato oficial do BMAD, nunca copiado.

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

## Conclusão

- **Task `done`:** portões aplicáveis executados, parecer `approved` válido vinculado ao
  `content_id` revisado, e autoridade de fechamento já concedida pela política do projeto. Não há
  confirmação humana adicional por Task por padrão.
- **Deliverable `done`:** todas as Tasks exigidas `done` e `integration_criteria` verificados
  conforme os portões aplicáveis. Tasks todas `done` não comprovam, por si só, que as partes
  funcionam juntas. O Orquestrador registra o fechamento com a evidência da verificação integrada.
- **Reuso de parecer:** alteração material posterior à revisão, isto é, novo `content_id`, impede
  o reuso automático do parecer para fechar a Task.

### Registro de revisão

Fora do parecer e sem alterar o schema, o arquivo de evidência da rodada,
`project/evidence/Tnnn-rNN.md`, registra o parecer JSON íntegro, a unidade revisada (qualificada
como `<area_id>:<id>` no modo multiárea), `spec_revision`, `content_id` revisado, sessão, harness,
modelo, effort, família e limitações de independência. É esse registro que vincula o parecer ao
conteúdo e à unidade; hashes iguais em outra unidade não transportam a aprovação.

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

### STATUS.md

```text
format_version: 1
work_method: native
active_work_ref: native/task/T001@_tl-orc/project/tasks/T001-slug.md
current_role: orchestrator
next_action: <frase curta>
coordinator:
  harness: <harness>
  session: <id>
  started_at: <UTC>
  last_write_at: <UTC>
  released: false
next_task_id: 2
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
open_discussions: []

## Tasks
| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
```

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

No STATUS global, com áreas cadastradas, acrescente a projeção:

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
task: Tnnn
round: rNN
spec_revision:
content_id:
content_paths: []
## Commands and exits
## Own proof
## Review record
harness / model / effort / family / session / independence:
### Verdict (JSON, íntegro)
```

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
