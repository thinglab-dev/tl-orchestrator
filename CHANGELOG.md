# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

## [Unreleased]

### Adicionado

- Áreas de trabalho opcionais: projetos sem módulos continuam o modo padrão, com tudo em
  `_tl-orc/project/`; repositórios por módulo cadastram áreas em `## Work Areas` de `PROJECT.md`,
  com caminho documental completo por área, validação de duplicidade, sobreposição e conflito com
  a instalação, e `work_method` herdado do global para trabalho novo. Coordenação de escrita
  continua uma só por árvore, no `STATUS.md` global, que aponta a unidade corrente mesmo em módulo;
  `STATUS.md` de módulo guarda progresso local, e `## Areas` no global é projeção. Referências
  qualificadas `<area_id>:<id>` entre áreas, pertencimento (`deliverable`) distinto de procedência
  (`origin`), detecção de ciclos, registro de revisão vinculado à unidade qualificada, briefs na
  área responsável pela feature.

### Alterado

- SKILL.md: a opção **Atualizar tl-orchestrator** só entra no menu com release estável sucessora
  comprovada, alinhando a triagem à cláusula "sem oferecer alvo".
- Classificação: `story_id` aceita ID qualificado no modo multiárea; validação e reuso comparam a
  forma canônica, classificações anteriores são normalizadas apenas pelo próprio briefing de
  origem, e dois formatos nunca permitem reuso entre áreas. Schema inalterado.
- Contrato de evolução protege também os caminhos das áreas cadastradas, distinguindo snapshot de
  recuperação da atualização de backup documental.

### Migração

- Sem `## Work Areas`, nada muda: formatos de v0.3.0 continuam aceitos e produzidos, filas
  existentes preservam `scope`, `board` e permissões, e a atualização não reescreve documentos nem
  `QUEUE.md`. Cadastrar áreas é ato explícito do consumidor.

## [0.3.0] - 2026-09-06

### Adicionado

- Perfil **Native** em `docs/WORK_MODEL.md`: hierarquia `Project → Deliverable → Task` com
  Tasks standalone, tipos que sugerem a verificação inicial sem decidir modelo, effort ou método,
  documentos de trabalho em `_tl-orc/project/`, estado oficial em cada Task com `STATUS.md`
  derivado e cabeçalho de coordenação cooperativa presente também em projetos BMAD, recuperação
  sem confirmação humana para desatualizações esperadas, identificação verificável do conteúdo
  revisado (`content_id`) separada dos registros de controle, IDs sequenciais com recuperação
  serial e bloqueio em colisão real, conclusão de Deliverable por critérios de integração.
- Operação **Import Context**: `context/INDEX.md`, Feature Briefs por feature com estados
  `current`, `stale` e `retired`, separação entre `planned`, `implemented` e `confirmed`, registro
  `imports/IMPnnn.md` com correspondência bidirecional, regra de carregamento seletivo e
  envelhecimento sem gravação em ativação somente leitura. **Migrate Work** fica definido apenas
  como interface.
- Modo **Discuss** no menu de ativação, distinto de **Debater**: conversa sem despacho nem
  classificação.
- `PROJECT.md` aceita `work_method` e `task_types`; `QUEUE.md` aceita `permit_state_update` e
  `max_replans`, com `STATUS.md` como board no perfil Native.
- Manifesto passa a 17 arquivos distribuídos.

### Alterado

- O contrato do Planner exige prova conforme o perfil de verificação: sonda contrafactual
  obrigatória sempre que a garantia for comportamentalmente discriminável, qualquer que seja o
  tipo; verificação por fontes, premissas ou inspeção nos demais tipos. As provas comportamentais
  exigidas pelas garantias existentes são preservadas.
- O Checker recebe `spec_revision`, `content_id` e `content_paths`, confere nas fontes as
  afirmações de Feature Briefs relevantes à revisão e tem seu parecer preservado no registro de
  revisão fora do schema, que permanece na versão 1.
- O contrato de evolução exclui `_tl-orc/project/` de snapshot, mutação e migração de
  atualizações, inclusive `auto_safe`.

### Migração

- `story_id` continua o nome do campo no schema de classificação, versão 2, e aceita IDs de Task
  ou Deliverable do perfil Native; a transição para `work_id` fica planejada para uma versão 3.
- Perfis sem `work_method` preservam suas fontes e autoridade; a atualização não cria
  `_tl-orc/project/` nem migra unidades existentes.
- `INSTALLATION.md` passa a registrar 17 hashes.

### Corrigido

- O contrato do Planner exige sonda contrafactual, tarefas e estado auditado específicos por
  story, e prova de que o consumidor executa o plano com as próprias ferramentas (dependências
  no arquivo e formato que o engine lê; efeito retroativo de declarações novas sobre itens
  concluídos). Motivado por uma rodada em que 17 specs saíram com a mesma sonda de template e um
  grafo de dependências que o engine consumidor ignorava.

## [0.2.2] - 2026-09-05

### Corrigido

- Destaca, antes da triagem, uma release estável sucessora comprovada como atualização explícita,
  com alvo, notas, impacto conhecido e numeração dinâmica do menu, sem transformar `notify` em
  escrita nem substituir uma tarefa já solicitada.

## [0.2.1] - 2026-09-05

### Manutenção

- Registra a rotina de fechamento do repositório fonte com publicação de release após
  revisão e validação, sem ampliar permissões de contribuições de consumidores.

### Corrigido

- Atualizações que sincronizam arquivos agora também exigem migração do perfil e das integrações,
  fresh load e smoke test de roteamento antes de declarar adoção operacional completa.
- O Debater bloqueia todo despacho até validar a classificação `debate` de Planner, Maker e Checker,
  com pares modelo/effort explícitos; pins continuam restrições sem dispensar o Classificador.
- Evidências distinguem conteúdo `synchronized` de `operational_verified` ou
  `operational_pending`, sem transformar indisponibilidade em sucesso.

## [0.2.0] - 2026-09-05

### Adicionado

- Classificador de fase com schema v2, escolha de modelo e effort por harness, evidências de
  roteamento e fallback validado.
- Searcher somente leitura, sob demanda e fora do schema de classificação.
- Políticas independentes `update_policy: notify|auto_safe` e
  `contribution_mode: ask|auto_pr`, com autoridade por projeto, ator, destino, escopo e
  procedência.
- Fluxo opt-in para preparar e publicar draft pull requests sanitizados antes de uma atualização,
  sem merge automático nem alteração do consumidor.
- Atualização automática conservadora somente para release estável descendente, com portões de
  integridade, snapshot, recuperação, prova do Orquestrador e Checker independente.
- Manifesto explícito dos 16 arquivos distribuídos e CI documental do repositório.

### Migração

- Perfis anteriores que omitem `update_policy` e `contribution_mode` mantêm o comportamento
  conservador: `notify` e `ask`.
- `update_check: enabled|disabled` continua controlando se a consulta remota de atualização pode
  ocorrer; ele não concede autoridade de escrita.
- A release pública v0.1.5 tem 11 arquivos distribuídos. A atualização para 0.2.0 adiciona
  `prompts/classifier.md`, `prompts/searcher.md`, `schemas/classification-result.schema.json`,
  `docs/MODEL_ROUTING.md` e `docs/EVOLUTION.md`, atualiza o manifesto e exige novos hashes para os
  16 arquivos.

[0.2.1]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.0...v0.2.1
[0.2.2]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.1...v0.2.2
[0.3.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.2.2...v0.3.0
[0.2.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.1.5...v0.2.0
