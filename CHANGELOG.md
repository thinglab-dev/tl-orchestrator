# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

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
[0.2.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.1.5...v0.2.0
