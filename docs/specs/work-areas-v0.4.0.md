<!-- Documento de trabalho do repositório fonte. Não faz parte da distribuição (fora do distribution-manifest.json). Referência canônica da implementação da v0.4.0. -->

# tl-orchestrator — Especificação: áreas de trabalho por módulo (revisão 7, com registro de achados na migração)

```text
Status: conceptual contract frozen
Implementation: not authorized
Target version: v0.4.0
```

Nova capacidade com compatibilidade legada preservada. A correção de redação do menu acompanha como item separado.
**Base:** v0.3.0 (`3e717f0`).
**Revisão 7:** acrescenta, por pedido do usuário, o registro de erros e bugs encontrados durante a importação e migração na fila de correção. As demais decisões da revisão 6 permanecem; implementação não autorizada.

**Motivação:** o `platform` organiza trabalho por módulo. O contrato v0.3.0 permite `work_method` por módulo, mas a ativação resolve `_tl-orc/...` pela raiz consumidora e fixa `_tl-orc/project/` como única área documental.

## 1. Modelo

**Modo padrão: projeto sem módulos**, inclusive em instalações novas. Tudo em `_tl-orc/project/`: contexto, status, Tasks, Deliverables, decisões, discussões, evidências e Feature Briefs. Sem áreas adicionais cadastradas, o Orquestrador assume `global` sem perguntar qual módulo usar, sem exigir `## Work Areas` e sem criar pasta `modules/`. Native e BMAD continuam disponíveis conforme a autoridade configurada.

| Projeto | Organização documental |
| :--- | :--- |
| Sem módulos | tudo em `_tl-orc/project/` |
| Com módulos cadastrados | área global mais áreas documentais dos módulos |

O suporte a múltiplas áreas é opcional. Uma instalação por repositório; documentos globais e, quando cadastrados, documentos por módulo. **A organização documental por área é distinta da coordenação de escrita, que continua por árvore.**

| Área | Local | Responsabilidade |
| :--- | :--- | :--- |
| Instalação e configuração | `_tl-orc/` | pacote, procedência, políticas, cadastro das áreas |
| Trabalho global | `_tl-orc/project/` | contexto compartilhado, trabalho que atravessa módulos, **coordenação de escrita da árvore** |
| Trabalho do módulo | `<path cadastrado>` (o campo `path` do §3 já contém o caminho documental completo), por exemplo `modules/billing/_tl-orc/project/` no `platform` | contextos, Tasks, Deliverables, decisões, discussões, evidências e importações do módulo; progresso local |

`modules/<module>/` é apenas o exemplo do `platform`. Projetos organizados em `apps/`, `services/` ou outros caminhos usam o cadastro com seus próprios `path`, sem renomear pastas.

Termos: **work area** = `global` ou um módulo cadastrado; **area_id** = `global`, identificador reservado e sempre disponível, ou o nome cadastrado.

## 2. Coordenação por árvore, progresso por área

- O `coordinator` do `STATUS.md` **global** governa a escrita em toda a árvore do repositório, inclusive em `project/` de módulos e na seção `## Areas`. A regra de um escritor por árvore, que já inclui autores de specs e relatórios, permanece; caminhos de resultado separados não demonstram isolamento, porque Git, configuração, índices e outros recursos são compartilhados.
- O `STATUS.md` de módulo **não** tem `coordinator`. Mantém `active_work_ref`, `next_action`, `current_role`, contadores locais, tabela derivada de Tasks e uma linha `coordination: global` referenciando a coordenação global.
- Execução simultânea em árvores distintas (worktrees) segue o contrato existente, sem configuração nova nesta evolução. `tree: shared|dedicated` fica fora desta entrega.
- Formato interno dos documentos de unidade reutilizado; a diferença entre coordenação global e progresso local fica explícita nos templates de `STATUS.md` global e de módulo.

## 3. Descoberta explícita e cadastro

Seção **`## Work Areas`** em `_tl-orc/PROJECT.md`, sem arquivo adicional:

```text
## Work Areas
| area_id | path | work_method | status_source | evidence |
| global  | _tl-orc/project | <omitido: usa o work_method global já declarado> | ... | ... |
| billing | modules/billing/_tl-orc/project | bmad | modules/billing/_bmad-output/sprint.md | ... |
```

Regras:
- Caminhos relativos à raiz consumidora. Validação no cadastro e na ativação: duplicidade de `area_id`, sobreposição entre `path` de áreas, e conflito com destinos da instalação (`_tl-orc/package`, integrações de skill). Cadastro inválido bloqueia a seleção da área, não a ativação.
- `global` é implícita e reservada, com caminho fixo `_tl-orc/project/`; sua linha no cadastro pode ser omitida. Áreas adicionais precisam de cadastro. Uma pasta documental de módulo não cadastrado é reportada, não adotada.
- Área cadastrada não implica diretório criado. A ativação somente leitura informa a condição "cadastrada, sem documentos"; a estrutura nasce na primeira operação autorizada que precisar dela. Trabalhar em um módulo inicializa também os documentos globais necessários à coordenação (`_tl-orc/project/STATUS.md` e `CONTEXT.md`), na mesma operação autorizada.
- `work_method` omitido no módulo herda o global, sempre como padrão para trabalho novo, nunca para unidades existentes.
- `_tl-orc/...` de instalação resolve sempre pela raiz consumidora; documentos de área resolvem pelo `path` cadastrado. O caminho documental **não** determina o diretório de execução dos portões, que continua vindo da tarefa e da política do consumidor.
- Abrir uma subpasta ou informar `cwd` dentro de um módulo não seleciona área nem autoridade.
- O `work_method` de `global` é o campo global já existente em `PROJECT.md`; a linha `global` do cadastro não o redeclara, evitando duas fontes.

## 4. Seleção de área e autoridade

Ordem: referência explícita do usuário, verificada na fonte → unidade já registrada → área declarada na tarefa → pergunta. Sem área resolvida, nenhuma escrita em `project/` de módulo.

> O método configurado na área define o padrão para trabalho novo sem autoridade anterior. Não altera o método de unidades existentes.

Uma Task Native dentro de um módulo BMAD continua Native. Referência explícita a unidade inexistente, ou que contradiz a área declarada, não autoriza criar nem selecionar outra silenciosamente: é ambiguidade material.

## 5. Referências cruzadas

- Locais dentro da área (`T012`); qualificadas entre áreas com `:` (`billing:T012`, `global:DEC003`). Aceitas em `depends_on`, `decisions`, `origin`, `deliverable`, `tasks`, `affects_context`, `resulting_work` e nos links de discussões. Sem prefixo, a referência é local.
- **Pertencimento** é campo próprio, distinto de procedência. Task de módulo pertencente a Deliverable global declara:

```text
deliverable: global:D002
standalone: false
origin: global:D002
```

`origin` registra procedência e não substitui `deliverable`. O Deliverable global lista `tasks` qualificadas; seu fechamento exige `integration_criteria` verificados através das áreas.
- Referências cruzadas não autorizam escrever nem despachar trabalho em outra área.
- **Vínculo do parecer.** O registro de revisão, fora do JSON do Checker, identifica a unidade qualificada (`<area_id>:<id>`), `spec_revision` e `content_id`. Igualdade de hashes entre unidades não autoriza transportar uma aprovação de uma Task para outra.
- Dependências entre áreas preservam `blocked_by` e a regra de `cancelled`; ciclos entre áreas são detectados e bloqueiam a seleção com a cadeia exibida.
- `active_work_ref` passa a `<method>/<unit_type>/<area_id>:<id>@<source_location>` no modo com múltiplas áreas.
- **Formatos legados preservados.** Sem cadastro, os formatos de v0.3.0 continuam aceitos e produzidos. No modo com múltiplas áreas, registros e despachos novos usam referências qualificadas; referências antigas sem prefixo são interpretadas somente quando a área de origem é inequívoca pelo documento que as contém, e divergência exige esclarecimento. A atualização do pacote não reescreve documentos para acrescentar `global:`.
- Classificador: `area_id` entra no **briefing**; o schema v2 não recebe propriedade nova. `story_id` recebe o ID qualificado no modo multiárea. **Normalização explícita** para validação e reuso: a comparação usa a forma qualificada canônica `<area_id>:<id>`, obtida do briefing; um `story_id` sem prefixo só é canonizado quando a área é inequívoca. **Procedência da normalização:** uma classificação anterior é normalizada usando o seu próprio briefing de origem, verificável no registro da classificação, nunca o briefing da tarefa atual; sem essa procedência, reclassifique. Um resultado antigo para `T001` não pode ser reinterpretado como pertencente a outro módulo. Essa regra é verificada pelo teste de isolamento entre áreas já previsto. Aceitar dois formatos nunca permite reutilizar classificação entre áreas diferentes; as demais exigências de igualdade (fase, papéis, revisões de contexto, catálogo e contrato, pins, política) permanecem. Testes obrigatórios: correspondência exata e reuso com `billing:T001` e `global:T001` distintos, e com `T001` legado sem cadastro.

## 6. Status sem duplicação e ponto de retomada

Quatro camadas com donos distintos:

| Camada | Conteúdo |
| :--- | :--- |
| Cabeçalho global (`_tl-orc/project/STATUS.md`) | coordenação (`coordinator`) e **referência da execução corrente na árvore** (`active_work_ref`, qualificado no modo multiárea conforme §5, inclusive quando a unidade pertence a um módulo), `current_role`, `next_action` |
| Cabeçalho do módulo | progresso local: `active_work_ref` da área, `next_action`, contadores, `coordination: global` |
| Task ou artefato externo | estado oficial da unidade |
| Seção `## Areas` do STATUS global | projeção dos módulos cadastrados, derivada e reconstruível, sem linha autorreferente de `global`; ponteiro, nunca cópia de tabelas de Tasks nem de estado BMAD |

Um novo harness lê o cabeçalho global e sabe qual unidade, de qual área, estava sendo conduzida, sem procurar módulo a módulo. Ordem de escrita sem atomicidade: primeiro a unidade, depois as projeções locais do módulo, por último a visão global. Na retomada, reler a unidade oficial antes de reconciliar cabeçalhos atrasados; divergência esperada não exige confirmação adicional, conforme a tabela de recuperação do WORK_MODEL.

## 7. Carregamento pequeno e importação por área

Conjunto inicial: `CONTEXT.md` global curto, `CONTEXT.md` da área, `INDEX.md` da área quando existir, briefs afetados e dependências diretas, unidade ativa e decisões referenciadas, inclusive `global:DEC…`. Compartilhados por referência e revisão, nunca copiados. Import Context roda por área. **O brief fica na área responsável pela feature:** em projetos sem módulos, todos os briefs ficam em `_tl-orc/project/context/features/`; em projetos com módulos, features de escopo global ficam na área global e as demais na área correspondente. Fontes BMAD preservadas como em v0.3.0.

## 7.1 Migration Findings — registro na fila de correção

Durante `Import Context` e, quando implementada, `Migrate Work`, o Orquestrador registra erros, bugs e suspeitas materiais encontrados na análise na fila de trabalho da área responsável. O registro faz parte da operação autorizada: não exige uma nova decisão do usuário por achado. Esta cláusula acrescenta captura e triagem documental; não implementa a transferência de autoridade de `Migrate Work` nesta evolução.

- **Unidades novas.** Esta política da operação seleciona explicitamente `method: native` para os achados novos, inclusive quando o trabalho de produto continua em BMAD. Bug confirmado gera Task `type: fix`, inicialmente `status: draft`. Suspeita sem confirmação gera Task `type: analysis`, também `draft`, com a hipótese e a verificação necessária; não é apresentada como bug comprovado. O tipo não decide método nem capacidade do executor.
- **Área.** A Task fica na área responsável pela correção; problemas de escopo global ficam em `global`. Em projetos sem módulos, todos os achados ficam em `global`, sem exigir cadastro adicional. Referências entre áreas seguem o §5.
- **Evidência mínima.** A Task registra origem (importação e epic/story/documento, quando existentes), fonte com caminho e revisão, comportamento esperado e observado, evidência ou passos de reprodução disponíveis, impacto observado, incertezas e próximo passo de verificação. Uma divergência entre documentos é registrada como tal, sem presumir falha no código. O registro de importação e as `Open Questions` dos briefs afetados apontam para a unidade correspondente.
- **Deduplicação e autoridade.** Antes de criar uma Task, confira unidades relacionadas nas fontes autoritativas da área. Se a mesma correção já estiver registrada, reutilize sua referência e vincule a nova evidência no registro da operação, sem criar outra unidade nem alterar o estado original. Uma unidade BMAD existente continua na fila BMAD até transferência deliberada; não ganha cópia Native nem é despachada pelos dois métodos. Repetir a importação não recria os mesmos achados.
- **Visibilidade e prontidão.** A Task nova aparece na tabela derivada de `STATUS.md` da área, com o estado real `draft`. O Orquestrador promove para `ready` somente depois de cumprir o contrato de spec, critérios e verificação. O registro não habilita `QUEUE.md`, não amplia suas permissões e não torna um item `draft` elegível para execução. A correção segue o ciclo normal de classificação, planejamento quando exigido, Maker e Checker, dentro da autorização de execução aplicável.
- **Coordenação e escopo.** Criação de Tasks, alocação de IDs e atualização das projeções seguem a coordenação global e a regra de um escritor por árvore. Descobrir um bug não amplia o escopo para modificar código ou corrigir produto durante a migração; correções já cobertas por uma autorização vigente seguem essa autorização.
- **Bloqueios.** A existência de um bug preexistente não bloqueia automaticamente toda a importação ou migração. Se impedir o critério de conclusão ou a transferência correta de autoridade, bloqueie apenas a unidade afetada, registrando `blocked_by` com a referência e o motivo. Os demais achados permanecem visíveis na fila, sem declarar resolvida uma funcionalidade que continua com defeito.

## 8. Filas

- Sem `## Work Areas`, `global` é implícita e o comportamento legado continua integralmente.
- Com múltiplas áreas, filas novas declaram `area_id`.
- Filas existentes preservam `scope`, `board` e permissões. A associação a uma área só é resolvida quando inequívoca a partir de `scope` e `board`; divergência exige esclarecimento, sem inferência.
- Atualizar o pacote não reescreve `QUEUE.md` nem sua autorização.

## 9. Compatibilidade e evolução

- Sem cadastro: uma única área `global` em `_tl-orc/project/`, como v0.3.0.
- Nenhuma atualização cria áreas ou pastas; ativação somente leitura não cria diretórios.
- `docs/EVOLUTION.md` passa a proteger **todos os caminhos documentais das áreas cadastradas**, além de `_tl-orc/project/`: fora da mutação e da restauração por snapshot da atualização; leitura, validação, versionamento e backup autorizado permitidos. Redação distingue snapshot de recuperação da atualização de backup documental.
- Schemas inalterados.

## 10. Correção de redação do SKILL.md (item separado)

Oferecer "Atualizar tl-orchestrator" **somente** com release estável sucessora comprovada, alinhando o parágrafo de triagem à cláusula "sem oferecer alvo". Evidência: smoke v0.3.0 no `platform`, sessão Claude Code ofereceu sem sucessora; Codex não.

## 11. Alterações previstas por arquivo

| Arquivo | Alteração |
| :--- | :--- |
| `docs/WORK_MODEL.md` | áreas; coordenação global versus progresso local; templates de `STATUS.md` global (com `## Areas`) e de módulo; referências qualificadas e pertencimento; carregamento e importação por área; captura e triagem de Migration Findings |
| `SKILL.md` | resolução por cadastro; seleção de área explícita; correção do parágrafo de atualização |
| `prompts/orchestrator.md`, playbook, perfis | `active_work_ref` qualificado; `area_id` no briefing; fila com `area_id` e regra legada |
| `docs/PROJECT_CONFIGURATION.md` | `## Work Areas`; validações do cadastro; `area_id` em `QUEUE.md` com compatibilidade |
| `docs/EVOLUTION.md` | proteção dos caminhos das áreas; distinção snapshot versus backup |
| README, CHANGELOG | sem arquivo novo; manifesto inalterado |

## 12. Verificação

Conclusão da mudança no TL-Orc em **consumidor sintético** com `global` e dois módulos, incluindo execução real da skill em pelo menos um harness para a contraprova de coordenação; o smoke no `platform` é validação posterior da adoção.

Cenários: **projeto novo sem módulos e sem BMAD**, cobrindo trabalho Native e Import Context na área global sem cadastro, sem pergunta de módulo e sem criação de `modules/`; referência qualificada resolvida; pasta não cadastrada reportada; `cwd` em módulo não seleciona área; `## Areas` reconstruída; Deliverable global com Tasks em módulos e `deliverable`/`origin` distintos; ciclo entre áreas detectado. Contraprovas obrigatórias:
- coordenador de outra sessão ativo na árvore impede escrita em outro módulo, **provado por execução real da skill em harness** no consumidor sintético: outra sessão detém a árvore, pede-se escrita em um módulo diferente, e os arquivos permanecem intactos por hash; um script que apenas simula a decisão não comprova esse comportamento;
- fila legada sem `area_id` mantém o comportamento;
- dois `T001` em áreas diferentes não compartilham classificação nem parecer, verificado pelo registro de revisão com unidade qualificada;
- método configurado no módulo não substitui a autoridade registrada na Task;
- atualização preserva os documentos das áreas e ativação somente leitura não cria diretórios.

**Migration Findings:** no consumidor sintético, a importação encontra um bug comprovado e cria uma Task Native `fix` em `draft`, com origem e evidência, visível no `STATUS.md` da área; uma suspeita gera `analysis`, sem afirmação de bug confirmado. Repetir a operação não duplica Tasks. Um achado já coberto por unidade BMAD mantém essa referência e sua autoridade. O registro não modifica arquivos de produto, não habilita a fila de execução e não promove Tasks para `ready` sem spec. Verificar a área correta tanto com módulos quanto no projeto sem módulos, e o bloqueio somente da unidade cuja conclusão esteja impedida.

Mais: validador do repositório, Checker de família distinta, e smoke por harness na adoção.

## 13. Decisões fechadas nesta revisão

| Decisão | Definição |
| :--- | :--- |
| Cadastro | seção `## Work Areas` em `PROJECT.md` |
| Referência qualificada | `:` |
| `tree: dedicated` | retirado; coordenação por árvore preservada |
| Versão alvo | v0.4.0 proposta |
| Migration Findings | achados registrados na fila da área, com evidência, deduplicação, autoridade preservada e sem execução automática por descoberta |
| Implementação | depende de autorização explícita; contrato da revisão 6 preservado com o requisito adicional de Migration Findings solicitado pelo usuário |