# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

## [Unreleased]

### Alterado

- Perfil global de despacho: Gemini/Agy permanece preferido para Classifier e Searcher; ChatGPT+RDC passa a ser a condução/Planner preferida quando o handoff remoto estiver habilitado; Planner local segue Codex → Claude → Agy; Maker segue Codex → Agy → Claude; Checker segue Claude → Agy → Codex após filtrar todas as famílias presentes em `effective_authors`. Quota esgotada percorre apenas fallbacks já autorizados e nunca reduz `checker_independence`.

## [0.19.0] - 2026-09-17

### Adicionado

- Story Authority Envelope e lotes filhos autônomos — `AUTO_STORY` (Task Native T032):
  - **Autoridade por Story, estritamente opt-in**: uma única autorização humana passa a cobrir a Story inteira, com teto global estrito de chamadas e escopo monotonicamente decrescente. Um lote sem `authorization.story_authority_mode` continua sendo `direct_proposal` — a semântica de lote único, inalterada, sem barreira e sem autoridade — e nenhuma migração de histórico é exigida.
  - **Separação estrita entre autoridade imutável e consumo mutável**: o envelope congelado vive em `_tl-orc/project/story-authorities/<authority_id>.json` e nunca é reescrito para registrar saldo; o estado operacional vive em `_tl-orc/runtime/story-authorities/<authority_id>/`, com `journal.jsonl` append-only (write-ahead, fsync, hash-chain, escritor único sob `lease.lock`) e `status.json` como projeção reconstruível.
  - **Autorização acíclica ligada a digest** (*digest-bound explicit operator authorization*, não assinatura): `root_authority_digest = SHA256(canonical_json(authority_payload))` sobre exatamente os doze campos submetidos à decisão humana. O próprio digest, `authorized_at`, `authorized_literal` e todo metadado posterior ficam fora do cálculo, e o cálculo recusa um payload contaminado por eles. A autoridade só é concedida pela frase canônica exata `AUTORIZO STORY <work_ref> sha256:<root_authority_digest>`; qualquer divergência ao carregar é `HARD STOP` por `state_integrity`.
  - **Derivação sem assinatura fabricada**: o runtime nunca inventa autorização para um lote filho. `verify_derivation()` prova a cadeia `root_authority_digest` + `parent_authority_digest` + `parent_batch_digest` + `child_proposal_digest` + `derivation_proof_digest`, e a autoridade derivada existe apenas porque o filho é subconjunto estrito e verificável do envelope original.
  - **Semântica correta de subconjunto de escopo**: é a **união** `child.required ∪ child.conditional` que precisa estar contida em `parent.authorized_write_scope`, de modo que um path autorizado como condicional no pai possa legitimamente tornar-se obrigatório no filho após um apontamento factual do Checker. `forbidden_paths` e `protected_paths` só podem crescer.
  - **Derivação estritamente patch-only**: um filho só é derivado quando todos os apontamentos residuais são `target_role = maker`, `category = patch`, `scope_status = inside_parent_envelope` e `spec_status = unchanged`, com os dois últimos recalculados mecanicamente contra o envelope — a declaração do Checker é necessária, nunca suficiente. `bad_spec`, `intent_gap`, `human`, `security`, `scope_expansion`, `new_boundary`, `migration` e `capability_expansion` interrompem o lote. A heurística "lote não aprovado ⟹ criar próximo lote" é proibida, inclusive para lista vazia de apontamentos.
  - **Contabilidade global única, sem double-spend**: o ledger da autoridade é a fonte de verdade do orçamento e o budget do filho é projeção dele. `budgeted_model_dispatch` passa a aceitar contexto de autoridade, escrevendo a reserva global antes da local e liquidando-a antes também. `logical_call_id` identifica a operação cognitiva; cada tentativa física recebe um `global_attempt_id` novo (`reserved`, `consumed`, `released`, `ambiguous`), duas tentativas consomem dois slots, resultado ambíguo conta conservadoramente uma vez e reprocessar um id já liquidado após crash não repete chamada nem débito. Na retomada, o journal da autoridade é autoritativo e o ledger do filho é reconciliado a partir dele.
  - **Linhagem funcional entre lotes filhos**: `governance base`, `functional checkpoint` e `integration candidate` passam a ser distintos. Um filho que termina `changes_requested` não é mesclado em `main` para transportar estado; o runtime materializa a árvore exata revisada pelo Checker como commit em `refs/tl/functional-checkpoints/<batch>/<unit>`, registra em `child_closed` os oito campos de linhagem, e o filho seguinte nasce exatamente desse commit — provado por `git cat-file -e`, `HEAD ==`, `tree ==` e working tree limpa antes de qualquer intervenção do Maker. O Checker seguinte revisa o candidato cumulativo `story_baseline_commit..integration_candidate_commit`.
  - **Bloqueio mecânico de chamadas cognitivas fora do ledger**: o ambiente do worker recebe um diretório à frente do `PATH` com shims determinísticos para `agy`, `codex`, `claude` e `gemini`; invocação direta falha com código 97 antes de tocar a rede. A barreira é instalada e provada no ambiente real do worker e, quando o isolamento não é comprovável, a capability fica `unavailable` e `AUTO_STORY` recusa iniciar — sem modo degradado. Limitação declarada: a barreira sombreia resolução por **nome**, não por caminho absoluto, e por isso o despacho orçado continua sendo a obrigação primária do plano de controle.
  - **Subordinação ao T028 e fronteira da Story**: `allowed_effects.merge` é flag de capacidade técnica e não constitui bypass do `MergeAuthorityGate`/`AuthorityReceipt`; `AUTO_STORY` encerra compulsoriamente ao atingir `CLOSE`/`done` e avançar para a próxima Story falha com `next_story_without_authorization`.
  - **Replay canônico e contraprovas**: `tests/test_auto_story_replay.py` reconstrói deterministicamente o ciclo real B013→B014 do canário Lynvia (Story 2.10) com repositório Git real, fixtures em `tests/fixtures/auto_story_b013_b014/` e recibo T028 autêntico; `tests/test_auto_story_runtime_integration.py` prova a barreira cognitiva, o teto global e o checkpoint funcional dentro do runtime real; e as suítes `test_story_authority_digest.py`, `test_story_child_derivation.py`, `test_story_functional_lineage.py`, `test_story_global_accounting.py`, `test_story_protected_paths.py`, `test_story_operational_limits.py` e `test_story_cognitive_barrier.py` cobrem as recusas normativas fail-closed.
- Validador de Plano de Execução e Protected Paths de primeira classe (Task Native T033):
  - **Registro fechado de asserções**: `scripts/validate_execution_plan.py` declara o enum fechado `lifecycle_phase` (`pre_execution`, `post_maker_pre_review`, `post_checker_pre_merge`, `post_merge_pre_close`, `post_terminal`) e um `assertion_registry` que mapeia cada `assertion_id` às fases em que sua resposta é decidível, com parâmetros tipados.
  - **Validação temporal fail-closed**: asserção desconhecida ⟹ recusa; asserção avaliada em `lifecycle_phase` incompatível ⟹ recusa; parâmetro ausente, desconhecido ou de tipo errado ⟹ recusa. `schemas/execution-plan.schema.json` torna estruturalmente impossível uma string de asserção livre.
  - **Satisfatibilidade aritmética do orçamento**: `gate_call_constraints_are_satisfiable_under_budget` exige a declaração dos cenários `straight_line` e `retry` e prova que ambos cabem no teto de chamadas.
  - **Protected paths de primeira classe**: modos `read_only`, `exact_file_hash` e `exact_set_snapshot`, este comparando recursivamente `path`, `type` (file vs. symlink), `size` e `sha256`, com falha imediata para adição de arquivo untracked, deleção, alteração de bytes ou conversão de arquivo em symlink. Ausência de baseline e de git para um caminho `read_only` resulta em `protected_read_only_unverifiable`, nunca em passe silencioso.
  - **Monotonicidade semântica**: para todo padrão herdado o filho preserva policy e parâmetros idênticos (hash esperado, snapshot de referência); pode acrescentar proteção e nunca remover padrão, reduzir cobertura, adotar policy mais permissiva ou substituir hash/snapshot herdado.
  - **Validador de schema que recusa o que não aplica**: subconjunto estrito de Draft 2020-12 em biblioteca padrão que refuta qualquer keyword não implementada em vez de ignorá-la; `tests/test_execution_plan_validator.py` prova que todos os schemas do repositório são integralmente enforceáveis por ele.

### Alterado

- `schemas/batch.schema.json`: `authorization` ganha as chaves opcionais `story_authority_mode` (`direct_proposal` | `AUTO_STORY`), `story_authority_id`, `root_authority_digest`, `child_proposal_digest` e `derivation_proof_digest`, exigidas em conjunto somente quando o modo é `AUTO_STORY`; `budget.pending_call` ganha `global_attempt_id`. Ausência de `story_authority_mode` significa `direct_proposal` e mantém a validação dos lotes legados inalterada. O nome é `story_authority_mode`, e não `authority_mode`, porque `authority_mode` já designa o modo de autoridade de merge do T028 em `frozen_scope.units[]` e na fila de merge.
- `schemas/review-result.schema.json`: `action_item` ganha os campos opcionais `scope_status`, `spec_status` e `derivation_blockers`, usados pela elegibilidade de derivação do T032. São declarações do Checker recalculadas mecanicamente pelo runtime; divergência entre o declarado e o provado interrompe o lote.
- `scripts/tl_runtime.py`: `RUNTIME_VERSION` passa de `0.17.0` para `0.19.0`, porque o plano de controle mudou (despacho ligado à autoridade, novas recusas, novas interações de journal). Consequência operacional: um lote com **step em aberto** journalado pela versão anterior para com `stale_workflow_version` na retomada e exige `--accept-stale-version` após inspeção. Lotes sem step em aberto retomam normalmente.
- Pacote distribuído: 54 arquivos (antes 49), com `scripts/tl_story_authority.py`, `scripts/validate_execution_plan.py`, `schemas/story-authority-envelope.schema.json`, `schemas/story-child-proposal.schema.json` e `schemas/execution-plan.schema.json`.

### Lacunas registradas (não corrigidas nesta release)

- **Registro de mudanças de T028 e T023 ausente:** os PRs #57 (T028) e #59 (T023) foram integrados em `main` depois da tag `v0.18.0` e alteraram arquivos distribuídos (`docs/RUNTIME.md`, `docs/WORK_MODEL.md`, `prompts/orchestrator-playbook.md`, `schemas/batch.schema.json`, `scripts/tl_runtime.py`) sem entrada correspondente neste arquivo, com `[Unreleased]` vazio. A lacuna é registrada aqui em vez de ser preenchida por resumo de terceiros: quem conduziu essas tasks é quem pode descrevê-las com fidelidade.
- **`scripts/tl_merge_guard.py` e `schemas/merge-authorization.schema.json` não são distribuídos**, embora `scripts/tl_runtime.py` — que é distribuído — os importe para avaliar o `MergeAuthorityGate`. Numa instalação exportada, o import cai no fallback e o merge é recusado com `merge_authority_unavailable`. É um comportamento fail-closed, mas a capacidade de merge autorizado não existe fora do repositório fonte. Pertence ao escopo do T028.

## [0.18.0] - 2026-09-15

### Adicionado

- Roteamento por Capacidade Mínima Suficiente e Preferência Determinística de Eficiência (Task Native T031):
  - **Minimum Sufficient Capability (MSC)**: o Classificador dimensiona o trabalho pelo menor esforço e custo operacional que satisfaça o piso de qualidade (*quality floor*) da fase. A avaliação técnica em `evaluations[]` julga unicamente adequação (`sufficient`, `uncertain`, `insufficient`).
  - **Deterministic Efficiency Preference Policy**: entre candidatos `sufficient` e `dispatchable`, a seleção primária (`candidates[0]`) segue a ordem de preferência de eficiência configurada no perfil (no perfil padrão, o candidato de alta eficiência `gemini-3.8-flash-high` tem precedência sobre modelos padrão/pesados como `gpt-5.6-terra` e `sonnet`/`opus`), registrando `selection_basis: "minimum_sufficient"`.
  - **Escalada Factual Obrigatória**: a eleição de candidatos mais pesados ou de maior custo exige registro de `selection_basis: "escalation"` e causa factual comprovada em `escalation_reason` (`efficient_candidate_insufficient`, `efficient_candidate_uncertain`, `checker_family_independence`, `operator_pinned`, `pre_dispatch_unavailable`, `proven_empirical_failure`, `concrete_technical_necessity`).
  - **Proteção Contra Over-Selection e Banimento de Jargões**: proibição terminante e validação mecânica rejeitando justificativas subjetivas sem causa factual de insuficiência ("frontier model", "modelo mais forte", "maior capacidade de raciocínio", "maior densidade arquitetural", "tier heavy exige modelo máximo").
  - **Reasoning Effort Mínimo Suficiente**: dentro do mesmo modelo (ex.: Codex), effort `high` é preferido por padrão sobre `xhigh` a menos que haja necessidade técnica concreta comprovada exigindo `xhigh`.
  - **Resolver e Validador Mecânico**: disponibilização de `resolve_minimum_sufficient(...)` em `scripts/validate_classification.py`, suporte no schema v3 aos campos `selection_basis` e `escalation_reason` e suíte com 8 casos de teste contratuais determinísticos em `scripts/tests/test_dynamic_primary_selection.py`.
- Journaling de Chamadas de Modelo Obrigatório e Despachador Orçado no Modo Automático (Task Native T027):
  - Primitive unificado `budgeted_model_dispatch` em `scripts/tl_job.py` (e subcommand CLI `tl_job.py budgeted-dispatch`) garantindo o ciclo estrito de write-ahead (`reserve -> pending_call persistido -> dispatch -> resultado observado -> consumed += 1 -> reserved -= 1 -> pending_call = null -> persistência em disco`) para todo despacho a modelos.
  - Abrangência universal cobrindo todos os papéis: `classifier`, `planner`, `maker`, `checker`, `advisor` e `searcher`, vedando bypass de journal para qualquer papel.
  - Cada tentativa real de despacho constitui consumo individual de quota (incluindo retries decorrentes de respostas com schema inválido).
  - Recálculo obrigatório de `required_call_reserve` antes de autorizar retry; interrupção imediata com `STOP: insufficient_budget_for_unit_verification` caso o saldo restante não cubra o caminho até o Checker independente.
  - Liberação de reserva sem débito de chamada para falhas pré-despacho (`PRE_DISPATCH_UNAVAILABLE`).
  - Débito conservador de chamada e parada imediata (`STOP: unrecoverable_harness_failure`) para despachos com desfecho ambíguo.
  - Guarda explícita T016 nos contratos e templates do Maker (`prompts/maker.md`, `prompts/orchestrator-playbook.md`) instruindo testes direcionados (*targeted verification*) em etapas intermediárias intragrupo e vedando a invocação de portões canônicos completos do sistema em ambiente sandbox sem permissão de sockets/rede.
  - Suíte contratual determinística em `scripts/tests/test_automatic_mode.py` cobrindo linha reta (4 chamadas), retry de classificador (5 chamadas), falha pré-despacho (0 chamadas) e despacho ambíguo (1 chamada com STOP conservador).

## [0.17.0] - 2026-09-15

### Adicionado

- Runtime durável opcional (`scripts/tl_runtime.py`, [`docs/RUNTIME.md`](docs/RUNTIME.md)):
  executa os estados `EXECUTE` → `CLOSE` de um lote já autorizado e congelado do Modo
  Automático sem sessão de Orquestrador aberta. Cada ação é um Step com intenção gravada
  antes do efeito e resultado depois (`journal.jsonl`, append-only, fsync por linha, um
  escritor por lease); retomar é dobrar o journal, e um crash vira pausa. Intenções abertas
  são reconciliadas com evidência (estado do `tl_job.py`, árvore de `HEAD`, `git ls-remote`,
  `gh pr list/view`): efeito comprovado é reutilizado, não iniciado é liberado sem cobrança,
  ambíguo é cobrado e continua de um checkpoint de árvore ou espera o operador. Nunca repete
  push, PR ou merge às cegas.
- Scheduler determinístico sobre o DAG do lote (estados `ready`, `running`, `waiting`,
  `retryable`, `parked`, `blocked`, `completed`, `failed`, `awaiting_operator`), com
  reserva de verificação antes de cada Maker, `continue_independent_after_block` honrado e
  concorrência 1.
- Classificação determinística de falhas (`transient`, `harness`, `environment`,
  `semantic`, `verification`, `authorization`, `budget`, `scope`, `state_integrity`,
  `security`, `unknown`) com movimentos limitados (`retry` com backoff, `rework`, `park`,
  `stop`) e detector de progresso persistido: mesma assinatura normalizada `loop_threshold`
  vezes, oscilação de árvore A→B→A e achados idênticos do Checker em rodadas consecutivas
  param a unidade; troca de modelo não zera o contador.
- Fronteira de política fora do prompt: ambiente do worker filtrado por allowlist, contenção
  `dirty_paths ⊆ scope_paths` e `do_not_touch`, caminhos sensíveis, varredura de padrões de
  segredo no diff antes de qualquer commit, efeitos externos (commit, push, PR, merge)
  somente sob `permitted_effects`, Checker de família diferente obrigatório e Checker que
  altera a árvore tratado como `unexpected_tree_state`. Capacidades de cada adapter
  (allowlist de ferramentas, sandbox de rede, telemetria de uso, resume) são declaradas e as
  ausentes aparecem como limitação no relatório.
- Context Compiler por papel e fase: pack com ordem estável (contrato, política, spec,
  aceite, comandos de verificação, testes relacionados, achados/portões/fatia de CI da
  rodada, checkpoint, diff), tetos por seção e manifesto com digests gravado como evidência
  do step. Nada de histórico, log bruto ou journal no pack.
- Laço de CI: `gh pr checks` sem modelo; em falha, só o log dos jobs vermelhos é buscado e
  fatiado por `scripts/tl_ci_slice.py` (job, step, testes falhos, assinatura normalizada,
  classificação `code_failure`/`external_infrastructure`/`configuration`/`unknown`, trecho
  limitado, ponteiro para o bruto). Falha de código vira rodada de rework; infraestrutura sem
  teste falho ganha reexecução limitada; nada é chamado de flaky para avançar.
- Orçamentos: despachos do lote, relógio de parede, retries por classe, rodadas de rework,
  unidades paradas e teto em dólar aplicado apenas sobre custo observado (`claude_json`,
  `codex_jsonl`); uso não observado permanece `unknown` e nunca é estimado.
- Relatório da manhã determinístico (`report.md`: Completed, Changed, Commits / PRs,
  Verification, Automatically Resolved, FYI, REVIEW, DECISION REQUIRED, BLOCKED, Cost /
  Usage, Models, Recovery Events, What Happens Next), `status.json` para o operador,
  `journal` diagnóstico, `decide --option retry|skip` e `notify_argv` opcional.
- Schemas `runtime-config.schema.json` e `step-journal.schema.json`; `batch.schema.json`
  ganha as chaves opcionais `permitted_effects.pull_request_merge` e `permitted_effects.ci_rerun`
  (ausentes = `false`).
- Integridade e contenção a posteriori: cadeia de hashes no journal (`prev`), `HEAD`/branch
  comparados antes e depois de cada chamada de modelo, toda árvore descartada preservada em
  `refs/tl/discarded/<lote>/<n>`, artefatos de portão nunca chegam ao commit, adapter sem
  allowlist de ferramentas nem sandbox só roda com `accept_unisolated_worker: true`, e
  `verificacao_pendente` do Checker que corresponde a um portão já verde é resolvida pelo
  runtime com a evidência do próprio portão.
- Revisão independente r2: `local_write` falso e `immutable_digest` ausente são recusas antes de
  qualquer despacho; a varredura de segredos lê o diff integral (o teto `max_diff_bytes` só
  limita o pack do Checker); merge remoto usa `--match-head-commit` e merge local exige que a
  branch ainda aponte para o commit revisado; PR reconciliado só com a mesma base e o mesmo
  head; a seção Changed do relatório vem dos arquivos gravados no step de commit, não de
  `git diff` ao vivo.
- Revisão independente r3: flags opcionais de `permitted_effects` precisam ser booleanas;
  rename expõe origem e destino à contenção; segredo e caminho sensível têm precedência sobre
  violação de escopo; `decide` e `--accept-stale-version` só escrevem no journal sob o lease;
  PR e merge reconciliados contra o commit revisado gravado na intenção (o create adota PR
  existente da branch em vez de duplicar); retomada só reserva as chamadas de modelo ainda
  pendentes da rodada; sujeira pré-existente na branch da unidade é recusa; o cache de
  portão inclui o `argv`; log e rerun de CI filtrados pelo commit revisado; títulos,
  orçamento e modelos do relatório vêm do `batch_open`; `max_cost_usd: 0` é teto válido;
  `merge --abort` nunca roda sobre um merge que o runtime não iniciou.
- Revisão independente r4: varredura de segredo também nos bytes de cada arquivo alterado
  (binário incluso); todo pack é redigido pelos mesmos padrões (saída de portão e fatia de CI
  inclusas); commit só sobre a árvore exatamente aprovada pelo Checker; PR adotado ou
  reconciliado só com `headRefOid` exato; portões sempre rodam sobre a árvore do Maker
  gravada no step (resto de portão após crash nunca chega ao commit); `max_model_calls`
  precisa ser inteiro ≥ 1; capacidades do relatório vêm do `batch_open`.
- Revisão independente r5: `git status -z` (caminhos nunca entre aspas, rename com origem e
  destino, arquivos com acento ou espaço são varridos de verdade); merge remoto revalida
  base, head e estado do PR antes de `gh pr merge` e a recuperação exige a mesma base;
  intenção de push grava `remote_before` e a recuperação só libera o push se o remoto está
  exatamente como antes da intenção (qualquer outro estado espera o operador).
  `notify_argv` mantido como comando do operador, fora de `permitted_effects` (documentado).
- Revisão independente r6: `git push` que devolve erro é reconciliado contra o remoto antes de
  qualquer retry (remoto no commit conta como enviado; estado desconhecido espera o operador);
  base do PR verificada logo depois do merge, com `merged_into_unexpected_base` quando alguém
  retargeta o PR entre a checagem e o merge (limitação do `gh` documentada).
- Revisão independente r7: sucesso de `gh pr merge` não é prova de merge (merge queue): só o
  estado terminal `MERGED` com base e head revisados conta; PR ainda aberto vira
  `merge_queued` e espera o operador, e o retry adota o merge da fila sem nova chamada.
  `decide` sobre um lote `blocked` o reabre para o próximo `run` (lote `stopped` continua
  exigindo nova autorização).
- Revisão independente r8: intenção de merge remoto interrompida com o PR ainda aberto é
  `ambiguous` (enfileiramento não muda o estado do PR), nunca `released`; push interrompido
  continua liberado só quando o remoto está exatamente como antes da intenção (rejeitado
  como bloqueante: o resultado é idêntico ao autorizado). Correção de CI: a árvore de
  trabalho é calculada comparando conteúdo (índice temporário com mtime de 1 s, o que força a checagem racy do git), porque um
  arquivo reescrito com o mesmo tamanho no mesmo segundo era lido pelo stat obsoleto no
  Linux.
- Revisão independente r9: branch de unidade pré-existente fora da base esperada é
  `stale_branch` (`awaiting_operator`, sem despacho); recuperação de merge local prova com o
  commit revisado e com a ponta da base gravada na intenção (base movida → operador);
  merge de dependência na branch da unidade documentado como escrita local, não
  `local_merge` (rejeitado como bloqueante).
- Revisão independente r10: push envia `<commit revisado>:refs/heads/<branch>` e recusa
  (`awaiting_operator`) uma branch local que já não aponte para o commit revisado.
- Revisão independente r11: commit já gravado no journal é adotado na retomada (branch que
  não aponta mais para ele → operador); "nada a commitar" nunca adota `HEAD`.
- Revisão independente r12: hooks do repositório não rodam em comandos git do runtime
  (`core.hooksPath` vazio via `GIT_CONFIG_*`, git ≥ 2.31); resultado de modelo já gravado é
  reutilizado pelo step id mesmo com pack recompilado diferente, e há checagem de orçamento
  imediatamente antes de cada despacho; PR `MERGED` com base e head exatos completa a
  unidade como mesclada, PR `CLOSED` espera o operador.
- Revisão independente r13: restauração de árvore limpa antes de trocar as regras de ignore
  (arquivo ignorado só pelas regras descartadas nunca é apagado); filtros clean/smudge do
  git config documentados como código do operador (rejeitado como bloqueante).
- Revisão independente r14: com `local_commit` falso, trabalho aprovado vai para
  `awaiting_operator` com a árvore preservada em ref, nunca para `completed`/`done`.
- Pacote canônico passa de 44 para 49 arquivos (`scripts/tl_runtime.py`,
  `scripts/tl_ci_slice.py`, `docs/RUNTIME.md`, dois schemas).

### Validação

- `scripts/tests/test_tl_runtime.py` (93 testes, Git real, harness e `gh` scriptados):
  DAG com dependência e fechamento, rework, esgotamento, estagnação, loop por assinatura,
  oscilação, `intent_gap` → decisão do operador, expansão de escopo com árvore restaurada,
  segredo e caminho sensível parando o lote, push não autorizado nunca tentado, drift de spec
  e de `frozen_scope`, mesma família recusada, reserva de orçamento, árvore suja, lease
  exclusivo, crash do harness com retry limitado, transitória com backoff, bloqueio por
  autorização, injeção de falha via `TL_RUNTIME_FAULT` (crash antes e depois do efeito do
  Maker, depois do commit, do push e do PR, remoto divergente → `awaiting_operator`, journal
  corrompido, versão obsoleta → `--accept-stale-version`), laço de CI com fatia e rework,
  rerun de infraestrutura (com e sem permissão), worker que move `HEAD`, journal adulterado,
  árvore descartada preservada em ref, worktree vinculada, retomada após commit sem
  redespacho, e o fatiador de log (Go, pytest, unittest, infra, configuração, CLI).
- Dogfood real com `claude -p` (Maker) e `codex exec` (Checker) numa fixture Python: uso
  observado por chamada (9 requisições de API numa invocação do Maker, US$0,37; Checker com
  348k tokens de entrada e custo `unknown`, porque o Codex não o reporta), crash injetado após
  o commit e retomada reconciliada sem novo despacho.

### Migração

- Nada muda para quem não ativa o runtime. Para ativar: criar `_tl-orc/runtime.json`
  conforme `docs/RUNTIME.md`, manter o lote em JSON validável por `batch.schema.json` e rodar
  `tl_runtime.py validate` antes de `run`. Reverter é deixar de chamar o script; o journal em
  `_tl-orc/runtime/` pode ser apagado sem afetar o método documental.

## [0.16.0] - 2026-09-15

### Adicionado

- Acelerador de contexto opcional Graft (`scripts/tl_graft.py`, [`docs/GRAFT.md`](docs/GRAFT.md)):
  ativa sob pedido em linguagem natural, instala uma versão pinada e verificada
  (`@nanonets/graft@0.18.0`) num cache isolado por worktree, e gera um mapa estrutural do
  código sem IA e sem chave. Nunca executa `graft init`, nunca toca `AGENTS.md`, `CLAUDE.md`,
  `GEMINI.md`, `.claude/` ou configuração global de agente, e desativa a telemetria upstream
  (`DO_NOT_TRACK=1`) em todo subprocesso que inicia.
- `setup`/`status`/`query`/`disable` cobrem instalação/atualização de mapa, checagem de
  atualidade, consulta (`ask`/`grep`/`skeleton`/`callers`/`map`) e remoção local; ausência de
  Node/npm, erro, timeout, saída vazia ou mapa desatualizado nunca bloqueiam a tarefa nem são
  tratados como ausência de código — o agente cai de volta para `rg`/leitura direta.
- Contenção do cache no consumidor: o diretório `.tl-orc-graft-cache/` se auto-exclui por
  inteiro (`.gitignore`/`.ignore` próprios com `*`), escrito antes da instalação e preservado
  mesmo quando ela falha; os arquivos de ignore do projeto não são lidos nem alterados
  (`GRAFT_NO_GITIGNORE`/`GRAFT_NO_IGNORE` no subprocesso).
- Isolamento do subprocesso: chaves e configuração herdadas do ambiente são removidas, o
  carregador de `.env` do Graft aponta para um arquivo inexistente e `HOME`/`USERPROFILE` vão
  para dentro do cache com um registro de checagem semeado — o `~/.graft` real não é escrito e
  a consulta em segundo plano ao registro npm não é disparada.
- Recusas em vez de dano: layout de pasta-guarda-chuva sem Git com vários repositórios
  (evitando builds dentro dos filhos), cache redirecionado por symlink/junção e cache de outro
  dono são recusados com fallback, sem chamar o CLI e sem remover nada.
- Contenção do subprocesso e da remoção: timeout e excesso de saída encerram o grupo de
  processos inteiro no POSIX — inclusive descendentes que sobrevivem ao líder — e a saída só é
  devolvida após terminar a drenagem dos pipes; o registro local de atualização só é escrito
  depois de validar todo o caminho (`home/.graft/`) contra links/junções; o CLI é recusado se
  `no-dotenv.env` existir, em vez de deixar o `dotenv` do upstream recarregar chaves; e uma
  remoção parcial preserva os arquivos de ignore e o selo, mantendo o que sobrou ignorado e
  permitindo concluir a desativação numa segunda tentativa. Os links legítimos que o npm cria
  em `node_modules/.bin` são removidos sem serem seguidos.
- Resposta de consulta só é considerada boa após checagem de frescor do grafo; grafo
  desatualizado, saída degradada por contenção de lock, vazia ou ilegível viram fallback
  explícito.
- Integração mínima em `SKILL.md`, `prompts/orchestrator-playbook.md` e
  `docs/PROJECT_CONFIGURATION.md` apontando para o guia, sem tornar a ativação pré-requisito do
  método nem dar ao mapa autoridade de requisito ou revisão.

### Validação

- Testes offline (`scripts/tests/test_tl_graft.py`) cobrindo, além dos caminhos de fallback
  (Node/npm ausente, erro/timeout de instalação e build, caminho com espaços e acentos, grafo
  desatualizado, truncamento de saída): exclusão do cache verificada com `git status`/`git
  check-ignore` em repositório real, recusa de junção/symlink e de cache alheio sem tocar nos
  arquivos apontados, recusa do layout multi-repositório provando que nenhum filho foi escrito,
  captura limitada e timeout de subprocessos reais com os dois fluxos cheios e UTF-8 parcial,
  ambiente do subprocesso sem chaves-sentinela, e saída JSON em UTF-8 a partir de um processo
  real sem `PYTHONIOENCODING`.
- Prova real local com o CLI oficial (sem mocks) em fixture Go+Python: `setup`, os 5 modos de
  `query`, `status` e `disable` executados com sucesso, inclusive em caminho com espaços;
  telemetria confirmada suprimida com `DO_NOT_TRACK=1` (evento `build_completed` deixa de ser
  enfileirado). Detalhes e comandos em `.tmp/graft-verification.md`.
- Pacote canônico da distribuição passa de 42 para 44 arquivos (Graft).

## [0.15.0] - 2026-09-15

### Adicionado

- Contratos opt-in e CLIs stdlib para prova de comportamento recuperável, avaliação pareada de
  perfis, registro de ambiguidades ligado ao digest da spec, preflight somente leitura e reuso
  fail-closed de gates. Browser/Reticle/Playwright continuam adaptadores externos e explícitos.
- Perfil limitado de conhecimento com proveniência, hash, autoria e licença; referências a UI,
  acessibilidade, erros, Chisle, Anti-Slop, FWC e 3D são selecionadas pelo consumidor, não
  carregadas globalmente.

### Corrigido

- A camada opt-in de qualidade distribui `extract_tool_result.py`, `context_ledger.py`,
  `context_lib.py` e a fixture de tarefas (42 arquivos), integra seus portões ao protocolo e exige
  identidades, recibos recuperáveis, métricas brutas e limites de perfil/cache fail-closed.

### Migração

- Atualize a cópia verificada para os 42 arquivos. A camada nova fica inativa até a seleção de um
  perfil; para rollback, desative o perfil e restaure a cópia anterior. Não há alegação de economia
  local, e evidência sem identidade compatível ou expirada não é reutilizável.
- `extract_tool_result.py`, `context_ledger.py` e `context_lib.py` são validados em Linux/CI.
  No Windows, a baseline mantém 3 falhas e 7 erros em `test_context_ledger` e
  `test_resume_generate`; suporte desses helpers não está validado nessa plataforma.

## [0.14.0] - 2026-09-14

### Adicionado

- Ferramentas de economia de tokens em escopo de usuário, ativas em todo projeto sem lembrete:
  `scripts/tl_tools.py` instala, verifica (`status`, `doctor --fix`), liga, desliga e mantém rtk
  (hook de reescrita de Bash no Claude Code; instrução global no Codex), headroom (proxy local em
  modo `cache` para as sessões CLI do Claude), ponytail (plugin, `full`) e caveman (plugin,
  `lite`), com um hook `SessionStart` que garante o proxy e reporta `tl-tools: ...`.
- Política, limites conhecidos e medições dessas ferramentas em `docs/TOKEN_TOOLS.md`; SKILL.md,
  Maker, Checker e playbook passam a tratar saída condensada, marcadores `<<ccr:...>>` e solução
  mínima como comportamento esperado, sem afrouxar a prova.
- Pacote canônico da distribuição passa de 24 para 26 arquivos (`docs/TOKEN_TOOLS.md` e
  `scripts/tl_tools.py`).

## [0.13.0] - 2026-09-14

### Adicionado

- Contrato de verificação humana adiada: specs podem declarar inspeções humanas `deferred` com
  responsável, procedimento e resultado esperado; Checker e Orquestrador preservam a pendência sem
  convertê-la em `intent_gap` ou bloqueio, sem permitir que prova automatizável ou falha conhecida
  seja ocultada.
- Regra do dono em destaque e orçamento verificável de contexto: o Orquestrador não edita nem
  diagnostica o consumidor sem permissão manual explícita e delimitada, não faz polling nem lê saída
  parcial, admite somente `blocking` e `reason` por parada, separa manutenção do condutor, agrupa
  comandos e recomenda handoff em sessão nova acima de aproximadamente 120 mil tokens.
- Versão corrente explícita e validada entre `distribution-manifest.json`, `README.md` e `SKILL.md`.

### Corrigido

- IDs de board com letras Unicode passam pelos mesmos limites estruturais dos IDs ASCII no
  supervisor, cobrindo chaves acentuadas sem aceitar espaço, `_` inicial, comentário, aspas ou `:`.
- Planner e Maker agora usam portões na forma literal da allowlist; recusa de comando oficial é
  registrada no summary sem loop de variantes, pois a execução autoritativa dos portões é do
  condutor.
- Documentada a recuperação de `advance` após checkpoint invalidado (`stop` e nova execução da
  story) e a precedência do git-dir do worktree sobre o common-dir ao localizar `state.json`.

### Migração

- A verificação humana adiada é opt-in na spec e usa o array `deferred` já existente no schema de
  revisão; não há conversão automática de `intent_gap` legado. Consumidores devem atualizar os
  contratos carregados para obter a nova semântica.

### Validação

- No Windows com Python 3.13, `test_context_ledger` e `test_resume_generate` preservam as mesmas 3
  falhas e 7 erros da tag v0.12.0; a matriz autoritativa da CI continua em `ubuntu-latest`.

## [0.12.0] - 2026-09-14

### Adicionado

- Seleção Dinâmica de Primário — Desacoplamento entre Ranking Semântico e Fallback de Infraestrutura (Task Native T019):
  - Desacoplamento formal entre avaliação semântica de qualidade (`recommended_primary` em `candidates[0]`) e despacho factual/recuperação de infraestrutura (`effective_primary`).
  - Novo contrato de schema Draft 2020-12 em `schemas/classification-result-v3.schema.json` cobrindo a matriz fechada de 4 estados (`conclusive`, `underdetermined`, `awaiting_operator`, `infeasible`), `evaluations[]` granular por par (harness, modelo, effort) e `candidates[]` como autoridade única de ranking (R6, R12, R18).
  - Minimum Technical Adequacy Gate (R10): pares avaliados com `technical_adequacy: "insufficient"` ou `"uncertain"` recebem `dispatchable: false` em `evaluations[]` e são estritamente excluídos de `candidates[]`, impedindo promoção indevida a fallback de infraestrutura.
  - Estado `awaiting_operator` e parada formal (R11): empate semântico sob política `ask` ou sob política automática sem vencedor único emite `dispatch_role: "unassigned"` para todos os candidatos, zero primário e dispara STOP imediato (`AWAIT_AUTHORIZATION`) no Runtime.
  - Matcher determinístico de `project_priority` (R13, R20): seletores de prioridade com precedência formal (`harness/model/effort` > `harness/model/*` > `harness/*`), resolvendo unicamente quando houver 1 match e transicionando para `awaiting_operator` em caso de exaustão, sem heurísticas alfabéticas ou ocultas.
  - Disciplina econômica precisa (R1, R2, R16): `cost_basis: unknown` nunca perde desempate econômico; menor esforço (`medium < high`) só desempata dentro do mesmo modelo; `token_price_only` suporta apenas `unit_token_price`, vedando alegação de menor custo da tarefa sem medição ou proxy.
  - Quota pressure desacoplada (R3): pressão de cota atua exclusivamente no Runtime no instante do despacho e não contamina o ranking semântico durável do Classificador.
  - Preflight local vs remoto (R21): preflight puramente local falha sem debitar chamadas (`reservation released`); preflight remoto ou invocação de CLI compromete formalmente slot com write-ahead e auditoria.
  - Máquina de fallback side-effect safe (R5, R14, R15, R22): classificação formal de desfechos em 4 classes (`PRE_DISPATCH_UNAVAILABLE`, `DISPATCH_FAILED_PROVEN_NO_EFFECT`, `DISPATCH_OUTCOME_AMBIGUOUS`, `SEMANTIC_FAILURE`), bloqueio absoluto de fallback diante de `DISPATCH_OUTCOME_AMBIGUOUS` (STOP imediato preservando workspace dirty) e exigência de reserva dinâmica `required_call_reserve` antes de acionar fallback.
  - Validador canônico dual upstream distribuído em `scripts/validate_classification.py` (Draft 2020-12 em Python puro stdlib) suportando nativamente schemas v2 e v3 via `schema_version`, garantindo rollout opt-in sem regressão em projetos legados.
  - Ampliação do pacote canônico da distribuição de 22 para exatamente 24 arquivos (adicionando `schemas/classification-result-v3.schema.json` e `scripts/validate_classification.py`), com sincronização integral em `distribution-manifest.json`, `README.md`, `SKILL.md` e `docs/PROJECT_CONFIGURATION.md`.
  - Suíte contratual determinística em `scripts/tests/test_dynamic_primary_selection.py` cobrindo integralmente os invariantes R1 a R22.
- Reconciliação de linhagem de governança e contrato de integração T018 × v0.11 (Task T024):
  - Reseat de identidades de tarefas colididas locais para assentos livres (T013-local → T020, T014-local → T021, T015-local → T022 e piloto T012 → T023) preservando evidências e content_ids históricos sem renomear arquivos de evidência.
  - Formalização do mapa de linhagem com digest SHA-256 em `_tl-orc/project/lineage-map.md`.
  - Guarda mecânica determinística em `scripts/audit_lineage.py` e suíte em `scripts/tests/test_audit_lineage.py` prevenindo IDs duplicados, arestas não resolvidas e quebras no CAS de board v0.11.
  - Integração da governança do Modo Automático (T018) com o runtime concorrente de v0.11: `batch_concurrency: 1` obrigatório no `frozen_scope` de `schemas/batch.schema.json`, remoção da autoridade ambígua de `auto_merge` no playbook e protocolo de execução (preservando que merge na `main` requer autorização humana explícita), prevalência contra avanço indevido de `parked` em lote autorizado e isolamento de `runtime_refs` no bloco mutável `execution`.
  - Portão canônico unificado integrando as 9 suítes de governança (`scripts/tests/`) ao workflow do GitHub Actions (`.github/workflows/validate.yml`).

### Corrigido

- Retrabalho T017 r02: resolução de contra-família para o Advisor agora opera sobre o conjunto
  completo de famílias autoras materiais (`challenged_author_families`), cobrindo pares e caso
  triplet com bloqueio sob `required` e fallback degradado sob `preferred` (R1).
- Retrabalho T017 r02: schema `schemas/advisor-result.schema.json` agora impõe condicional
  Draft 2020-12 onde `verdict == "debate"` implica obrigatoriamente `debate_required == true` (R2).
- Retrabalho T015 r03: o ledger de contexto agora exige declaração explícita de cada raiz de
  leitura (sem allowlist implícita de suporte), normaliza caminhos pelo `cwd` efetivo e consome o
  contrato canônico `sha256`/`bytes`/`heading_path` de `read_section.py`; a telemetria de rotação
  fica `not_calibrated` sem limiares fornecidos (R7, R10).
- Retrabalho T015 r03: o manifesto de retomada resolve Native/BMAD a partir de `PROJECT.md`,
  vincula selector e digest da seção realmente publicada, deriva itens abertos e próxima ação das
  fontes e reforça a verificação pré-despacho contra divergências de fontes congeladas (R8, R11).
- Retrabalho T015 r03: `extract_tool_result.py` rejeita `details_ref` local irrecuperável sem
  `--persist-raw` e formaliza falhas de `grep` com `status` e `failure_ids` recuperáveis (R9).

### Adicionado

- Modo Automático — Execução de Lote Finito Autorizado, Recuperação e Fronteiras (Task Native T018):
  - Formalização do Modo Automático em `docs/WORK_MODEL.md`, `prompts/orchestrator.md`, `prompts/orchestrator-playbook.md`, `SKILL.md` e `docs/PROJECT_CONFIGURATION.md`.
  - Princípio fundamental de autoridade (AC01): o comando "iniciar modo automático" autoriza estrita e exclusivamente a fase de leitura (`DISCOVER → PROPOSE`), exigindo deliberação humana formal prévia para qualquer modificação ou despacho de execução.
  - Máquina de estados formal (AC02): ciclo estrito `IDLE → DISCOVER → PROPOSE → WAIT_AUTHORIZATION → PREFREEZE_REVALIDATE → FREEZE_BATCH → EXECUTE → CLOSE`, com saídas excepcionais `BLOCKED`, `STOPPED`, `FAILED` e `CANCELLED`.
  - Semântica de aprovação parcial (AC03): a aprovação de um subconjunto nunca filtra o lote no freeze diretamente; gera obrigatoriamente um novo ciclo `PROPOSE` com recálculo de dependências, orçamentos, boundaries e novo `proposal_digest`.
  - Revalidação pré-freeze contra drift (AC04): revalidação síncrona no estado `PREFREEZE_REVALIDATE` imediatamente antes do freeze em disco, retornando a `PROPOSE` diante de qualquer drift detectado.
  - Persistência híbrida durável (AC05) e rejeição formal de runtime-only (AC06): arquivo dedicado `_tl-orc/project/batches/Bnnn.md` como fonte autoritativa de verdade do lote, validado por `schemas/batch.schema.json` (Draft 2020-12), e `STATUS.md` como projeção e lock de coordenação (`active_batch`, `batch_status`, `next_batch_id`). Desqualificação formal da Alternativa C (em memória).
  - Contabilidade observável por write-ahead lógico serializado (AC07): protocolo de 9 passos (`verificar saldo → reservar slots → pending_call → persistir → despachar → receipt → debitar consumed → limpar pending_call → persistir`).
  - Recuperação auditável pós-interrupção (AC08): na retomada pós-crash, `pending_call` ambíguo é contabilizado conservadoramente como `consumed` com interrupção imediata via `STOP`.
  - Admission gate por unidade (AC09): checagem síncrona de autoridade inalterada, membresia no snapshot congelado, integridade de revisões/specs, dependências satisfeitas (`status == done`), coordenador ativo, estado da árvore (`tree_state == expected_checkpoint`) e efeitos permitidos.
  - Reserva dinâmica de orçamento por ciclo completo (AC10): cálculo de `required_call_reserve = todas as chamadas obrigatórias ainda não consumidas do checkpoint atual até o Checker independente`, interrompendo com `STOP: insufficient_budget_for_unit_verification` caso o saldo restante seja inferior.
  - Simetria de `bad_spec_or_intent_gap` (AC11): interrupção antes do Maker se detectada por Classifier ou pré-Maker; interrupção antes de rework se apontada por Checker independente.
  - Limites estritos de retrabalho automático (AC12): restrito a correções do Maker em spec e content_paths congelados, respeitando `max_rework_rounds_per_unit` e saldo para o ciclo restante de rework.
  - Catálogo formal de 18 stop conditions (AC13): interrupção imediata sob qualquer condição catalogada, com comportamento padrão `continue_independent_after_block: false`.
  - Composição com T013–T017 (AC14): integração de liveness, roteamento, economia de contexto e Advisor com débito orçamentário.
  - Portões canônicos T016 em fronteiras de grupo dentro do lote (AC15): execução obrigatória de `canonical_full_gate` a cada transição de `integration_group` dentro do batch e no fechamento do último grupo antes de `CLOSE`.
  - Invariante terminal: lote concluído nunca cria ou dispara outro lote automaticamente.
  - Governança de autoria material acumulada de T018 (AC16): registro formal de `effective_authors: [openai, google, anthropic]` e operação sob `checker_independence: preferred` com registro de limitação por inexistência de quarta família.
  - Ampliação do pacote canônico da distribuição para 22 arquivos: inclusão de `schemas/batch.schema.json`, `docs/EXECUTION_PROTOCOL.md` e `scripts/tl_job.py`, com sincronização em `distribution-manifest.json`, `README.md`, `SKILL.md` e `docs/PROJECT_CONFIGURATION.md`.
  - Suíte contratual determinística em `scripts/tests/test_automatic_mode.py` (AC17) cobrindo todos os estados, gates, write-ahead, persistência e contrafactuais.
- Papel consultivo independente Advisor — Cross-Family Strategic Challenge and Escalation (Task Native T017):
  - Introdução formal do papel consultivo Advisor em `docs/WORK_MODEL.md`, `prompts/orchestrator.md`, `prompts/orchestrator-playbook.md`, `prompts/orchestrator-perfis.md`, `prompts/classifier.md` e no novo contrato `prompts/advisor.md`.
  - Princípios mandatórios de fronteira de papel (AC01): estritamente `report_only: true`, `fresh_session: required`, `may_edit: false`, `may_commit: false`, `may_change_state: false`, `may_close_task: false`, `may_authorize: false`, `may_dispatch_agents: false`, `may_replace_checker: false`, `may_replace_planner: false`, `may_recommend_debate: true`.
  - Distinção clara e mútua exclusão dos 4 papéis (AC02): Planner ("Como devemos fazer?"), Advisor ("Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"), Checker ("O que foi implementado atende a spec e a prova?") e Debate ("Temos alternativas materialmente concorrentes; qual direção devemos escolher?"), sem que o Advisor atue como Checker antecipado nem como quarta IA rotineira por Story.
  - Gatilhos objetivos de acionamento (AC03): acionamento restrito exclusivamente aos 8 gatilhos contratuais objetivos (mudança em arquitetura/protocolo/contrato compartilhado, decisão difícil de reverter, experimento para o método, incerteza material em tier heavy, conclusão causal a partir de evidência limitada, recorrência de classe de falha descoberta só em revisão, segundo parecer solicitado pelo usuário e pré-congelamento de lote automático de alto custo).
  - Vedações estritas de acionamento rotineiro (anti-overuse / non-triggers) (AC04): proibição terminante de invocação no início de Story, término de Maker, entrada em revisão, changes_requested comum, tarefa heavy sem incerteza material, alterações documentais/status de rotina, "segunda opinião" informal ou "por segurança".
  - Schema JSON canônico Draft 2020-12 `schemas/advisor-result.schema.json` (AC05): definição estrita com `schema_version: 1`, `verdict` (`proceed|adjust|plan|debate|stop`), `confidence` (`high|medium|low`), `findings`, `alternatives`, `missing_evidence`, `debate_required` (boolean) e `reason`.
  - Semântica operacional dos 5 vereditos e disposição bloqueante (AC06, AC13): `proceed` para avanço normal; `adjust`, `plan`, `debate` e `stop` (assim como `debate_required: true`) possuem efeito bloqueante e não podem ser ignorados silenciosamente pelo Orquestrador antes da próxima ação material.
  - Regime de independência e resolução de contra-família (AC07, AC08): padrão `advisor_independence: preferred` com independência avaliada contra a família da autoria da proposta desafiada (contra-família), admitindo fallback degradado na mesma família (`degraded_same_family`) com registro obrigatório; e bloqueio estrito do despacho sob `advisor_independence: required` diante de indisponibilidade cross-family.
  - Suporte completo no Classificador (AC09): suporte ao papel `advisor` em `requested_roles`, adicionado a `schemas/classification-result.schema.json`, com dimensionamento de tier (`normal` para desafios delimitados e `heavy` para arquitetura/mecanismo compartilhado/experimentos críticos) e pares modelo/effort por harness sem hardcode.
  - Context Economy e challenge packet mínimo (AC10): recebimento de pacote conciso de desafio delimitado pelo Orquestrador, com consultas adicionais pontuais sob demanda via ferramentas somente leitura.
  - Regra estrita de propagação de autoria (AC11): parecer consultivo do Advisor não integra `effective_authors`; somente no caso de incorporação/cópia substancial direta à spec ou aos `content_paths` da entrega a família do Advisor passa a integrar `effective_authors` para a independência do Checker subsequente.
  - Escalonamento para Debate (AC12): recomendação formal de Debate (`debate_required: true`) sem autoridade para auto-iniciar ou auto-autorizar o painel, dependendo de autorização humana ou prévia vigente.
  - Interface declarativa para o Modo Automático (AC14): suporte ao bloco `advisor_policy` no lote (enabled, triggers autorizados e limite de chamadas contabilizadas contra o orçamento congelado), vedando Advisors espontâneos fora do orçamento.
  - Ampliação do pacote distribuído para 19 arquivos canônicos: atualização de `distribution-manifest.json`, `README.md`, `SKILL.md` e `docs/PROJECT_CONFIGURATION.md`.
  - Suíte de testes determinísticos contratuais em `scripts/tests/test_advisor_policy.py` (AC15): cobertura integral e automatizada de todos os critérios de aceitação (AC01 a AC15).
- Política formal de cadência de verificação (*Verification Cadence*) e portões de fronteira de integração (*Major-Boundary Integration Gates*) (Task T016):
  - Formalização do princípio universal "targeted early and throughout → canonical full integration gate only at major boundary" em `docs/WORK_MODEL.md`, `prompts/orchestrator.md` e `prompts/orchestrator-playbook.md`.
  - Resolução semântica do grupo de integração por autoridade (`epic` no BMAD, `deliverable` no Native, agrupamento explícito configurado, e Native Standalone Task como seu próprio grupo `authority: native_standalone, id: <Task_ID>`), vedando expressamente parsing *ad hoc* por regex sobre IDs de tarefas.
  - Exigência mandatória de execução do `canonical_full_gate` exclusivamente no fechamento da unidade final do grupo de integração ou de tarefa standalone, com falha no portão bloqueando a transição para grupos subsequentes.
  - Invalidação estrita da árvore: vínculo rigoroso do resultado do portão canônico ao commit SHA exato da árvore, invalidando a prova em caso de qualquer alteração de código posterior dentro do grupo.
  - Regime restrito de exceção antecipada (`full_gate_exception`): execução antecipada admitida apenas para alterações estruturais transversais comprovadas, com rejeição terminante de justificativas genéricas ("por segurança", "para garantir tudo", "para confirmar").
  - Parametrização agnóstica de `canonical_full_gate` e `verification_cadence` em `PROJECT.md` e `docs/PROJECT_CONFIGURATION.md`, com proibição estrita de adivinhar comandos e tratamento formal de `canonical_full_gate: not_configured` como pendência bloqueante.
  - Regras para reaproveitamento de prova de CI externo sob paridade estrita de commit SHA e definição/revisão do portão, com logs auditáveis e invalidação em caso de divergência.
  - Rework econômico e focado: restrição da re-execução de testes ao patch e consumidores impactados em retrabalhos funcionais, com dispensa total de testes funcionais para retrabalhos puramente documentais, de evidência, metadados ou status.
  - Instruções operacionais para o Checker independente em `prompts/checker-report-only.md`: auditoria baseada nos escopos `targeted`, `integration_boundary` e `exceptional_full`, sendo terminantemente proibido apontar a ausência rotineira de full gate como deficiência probatória ou motivo para `changes_requested` sob escopo direcionado.
  - Suíte de testes determinísticos contratuais em `scripts/tests/test_verification_cadence.py` validando todas as transições de estado, resolução por autoridade, critérios de exceção, vínculo de commit e invariantes de cadência.
- Diretrizes operacionais para condução de lotes autorizados no playbook e no modelo de trabalho Native:
  avanço contínuo e automático entre tarefas concluídas e subsequentes elegíveis na ordem topológica,
  com trava anti-salto como comportamento padrão mandatório (parada imediata na primeira unidade bloqueada,
  sendo vedado saltá-la). A continuação automática em tarefas topologicamente independentes é admitida
  exclusivamente quando expressamente autorizada na política do lote (`continue_independent_on_block: true`).
- Parâmetro configurável de sonda de liveness (`liveness_probe_after`) e investigação mecânica proporcional
  prévia de subprocessos, CPU, streams e descritores/pipes de I/O de forma agnóstica ao sistema operacional
  antes de qualquer inferência de latência de agente ou diagnóstico de indisponibilidade.
- Marco temporal de prazos humanos iniciado estritamente no evento tecnicamente observável
  `question_emitted_at` (admitindo `transport_ack_at` se fornecido pelo canal), com proibição terminante de
  presumir leitura ou cognição humana.
- Regra explícita de autoridade no perfil Debater: agentes subordinados atuam na análise de alternativas,
  prós e contras, mas nunca possuem autoridade para conceder autorizações de escopo ou orçamento em nome
  do usuário.
- Modelo de herança limpa de participantes nos projetos consumidores: `_tl-orc/PROJECT.md` herda o perfil
  global publicado por omissão e registra apenas fontes autoritativas, portões e overrides locais deliberados,
  com precedência formal: instrução do usuário > projeto local > perfil publicado.
- Mecanismos de Context Economy, Selective Retrieval e handoff verificável (Task T015):
  - Biblioteca compartilhada `scripts/context_lib.py` com parser Markdown estrutural robusto (isolamento de cercas de código, isolamento de cabeçalhos em prosa/crases, tratamento de `frontmatter` e resolução por heading path), canonical section digest SHA-256 com preservação de whitespace e linhas legítimas sem `rstrip` indevido (R4), e avaliação de frescor (`current`, `digest_changed`, `selector_not_found`).
  - CLI fino de leitura seletiva `scripts/read_section.py` para extração determinística por seção com procedência, delimitadores de linha e digests.
  - CLI do manifesto derivado de retomada `scripts/resume_generate.py` com suporte e validação de `--policy`, resolução dinâmica de `work_method` e `effective_authors`, seletor `frontmatter` para `STATUS.md` com mascaramento de campos voláteis, e verificação real de integridade pré-despacho via `--verify` (R1).
  - CLI de extração e offloading de saídas de ferramentas `scripts/extract_tool_result.py` com validação e persistência bruta (`--persist-raw`, `details_ref`), preservação estrita de `deferred` e `rejected` em payloads JSON de Checker, e portão de não-perda (*losslessness gate*) com critérios formais de falha e sondas contrafactuais para todos os extratores (R3).
  - CLI de observabilidade e ledger pós-hoc `scripts/context_ledger.py` com auditoria de leituras via comandos Bash (`read_section.py`, `cat`, `head`, `sed`), confinamento estrito de caminhos sem correspondência permissiva de substrings, segregação de `failed_read_attempts`, suporte a `--allowed-set` congelado, cálculo de divergência contra `--wrapper-telemetry`, métrica formal de Retrieval Amplification (RA) e limiares configuráveis de rotação (R2).
  - Documento normativo formal `docs/CONTEXT_POLICY.md` com definição das classes de informação, modos de entrega (`inline`, `excerpt`, `on_demand`) e matriz de contexto por fase.
  - Schemas JSON Draft 2020-12: `schemas/resume-manifest.schema.json`, `schemas/context-policy.schema.json` e `schemas/context-ledger.schema.json` (expandido para RA, tentativas falhas e externas, telemetria e limiares).
  - Fixtures permanentes de teste sob `scripts/fixtures/` e suíte de testes unitários e contrafactuais sob `scripts/tests/` (cobrindo perda zero, confinamento estrito, divergência de telemetria e integridade pré-despacho).

### Alterado

- Subseção de Fallback e Interrupção nos perfis do Orquestrador clarifica que comandos como `ps` e `lsof`
  são meros adaptadores de SO e que falhas mecânicas simples devem ser corrigidas localmente dentro da
  autorização vigente com registro na contabilidade de esforço da amostra, sem justificar fallback de família.
- Política global padrão de participantes e cadeias publicada em `prompts/orchestrator-perfis.md` e `README.md`:
  Maker passa a ter como preferência Agy `gemini-3.8-flash-high` (`high`) → Codex `gpt-5.6-terra` (`high`/`xhigh`)
  → Claude `sonnet` (`high`); Checker report-only passa a ter como preferência nominal Codex `gpt-5.6-terra` (`high`)
  → Claude `sonnet`/`claude-opus-5` (`high`) → Agy Gemini (`high`), estritamente subordinada a `checker_independence`
  e à autoria efetiva completa (incluindo Orquestrador, Maker e reworks).
- Desvinculação do pin rígido obrigatório de `gpt-6-astra/high` como Checker, mantendo-o como candidato experimental
  classificável no catálogo e fixando `gpt-5.6-terra/high` como referência padrão.
- Modelo de trabalho (`docs/WORK_MODEL.md`) atualizado com o layout de evidência e derivados por unidade/rodada
  (`evidence/<unidade>-rNN/`), normas do manifesto derivado `resume.json`, canonical section digest, estados de
  freshness, política de campos voláteis e `always_read`, e exclusão terminante de snapshots arquivados sob `evidence/`
  da descoberta operacional de configuração ativa.
- Contrato do Orquestrador (`prompts/orchestrator.md`) e Playbook (`prompts/orchestrator-playbook.md`) atualizados
  com o dever de leitura por seção com procedência e checagem de digest, adoção de extratores determinísticos
  para resultados de ferramentas antes da admissão no contexto, e registro de leituras integrais de arquivos extensos
  como decisões conscientes e justificadas.

## [0.11.0] - 2026-09-13

### Adicionado

- Execução concorrente multi-story em worktrees isolados com supervisor Python stdlib: Worktree
  Pool de capacidade limitada e concessão atômica, Scope Arbiter fail-closed para impedir colisão
  entre `content_paths`, Merge Queue Serializada FIFO para manter um único merge em voo e varredura
  de worktrees órfãos por expiração de heartbeat.
- Atualização CAS do board por `state_revision`, ponto de entrada `tl_run_story.py` para enfileirar e
  avançar somente o topo da fila de merge, e testes offline de contenção, conflitos, FIFO, leases
  expiradas e escrita concorrente do `STATUS.md`.

- Recuperação de itens de merge abandonados por timestamp e retentativa com carência ao persistir
  o estado terminal, evitando bloqueio permanente da fila após queda ou contenção transitória.

## [0.10.0] - 2026-09-13

### Adicionado

- Protocolo de Pipelining Assíncrono com Git Worktrees (`docs/EXECUTION_PROTOCOL.md` e `prompts/orchestrator-playbook.md`):
  - Desacoplamento da fase de entrega (`phase_deliver`): a abertura de PR (`gh pr create`) não bloqueia mais a sessão aguardando de forma síncrona o CI remoto do GitHub Actions.
  - O monitoramento do PR é delegado com auto-merge atômico (`--auto --squash --delete-branch`), liberando imediatamente a capacidade para admitir e codificar a próxima story independente no DAG em um worktree isolado.
  - Heartbeat e fencing de leases para recuperação atômica de locks órfãos (`session.lock`) em caso de encerramento abrupto do processo, eliminando travamentos residuais sem intervenção manual.
  - Orçamento estrito de 2 rodadas de revisão Maker ↔ Checker com estacionamento automático (`parked`) e detector de oscilação de diff idêntico para assegurar autonomia contínua durante a madrugada.
  - Cache local de gates obrigatórios por hash de árvore de arquivos (`tree_sha`) para acelerar conferências idempotentes.

## [0.9.0] - 2026-09-12

### Adicionado

- Disciplinas de engenharia especializadas por papel com validadores determinísticos em `skills/`:
  - `skills/tl-spec-hardener`: planejamento blindado para o Planner com pré-mortem preventivo de falhas silenciosas, fronteiras invioláveis (permitido/proibido/restrições), mapeamento estrito de pontos de alteração em `arquivo:linha`, critérios de aceite falsificáveis com `- [ ]` e validador determinístico `audit_spec.py`.
  - `skills/tl-impeccable-design`: diretrizes de design de interface sem AI-slop para o Maker, tipografia e espaçamento em escala modular (4px/8px), tokens semânticos, contraste acessível WCAG AA (>= 4.5:1), cobertura dos 5 estados interativos e validador determinístico `audit_ui.py`.
  - `skills/tl-deep-review`: quatro lentes estritas de revisão de código para o Checker (Concorrência/TOCTOU, Vazamento de Recursos/Esgotamento, Fail-Closed/Erros e Falsificabilidade de Testes) acompanhadas de validador determinístico de Git diff `audit_diff.py`.
- Atualização normativa nos contratos dos papéis (`prompts/planner.md`, `prompts/maker.md`, `prompts/checker-report-only.md`) e no playbook (`prompts/orchestrator-playbook.md`) orientando a injeção e o cumprimento dessas disciplinas durante o ciclo de vida da story.

## [0.8.0] - 2026-09-12

### Adicionado

- Protocolo de execução (`docs/EXECUTION_PROTOCOL.md`): envelope da unidade de execução, lista
  fechada do resultado devolvido, contexto separado por papel, retomada por checkpoint limitado
  validado contra a árvore e a cadeia Maker → portões → Checker → correção limitada → prova →
  entrega no condutor do consumidor. O condutor volta ao usuário por exceção material ou resultado
  terminal, não por turnos de progresso.
- Supervisor opcional de biblioteca padrão (`scripts/tl_job.py`) para despachar uma unidade **já
  autorizada** sem conversa de acompanhamento: `start` desacoplado (Windows sem janela e POSIX),
  `wait` local sem chamada de modelo, `status` que não lê logs e `result` limitado por lista de
  campos permitidos e teto de bytes. Ele apenas transporta: não escolhe modelo ou effort, não
  inventa comando, não certifica portões e não aprova entrega; seu exit zero não fecha uma unidade.
  A identidade da unidade é reivindicada uma vez — repetir o mesmo despacho reaproveita o resultado
  e um manifesto divergente é recusado em vez de reexecutar.
- Contenção da árvore do job no fim do prazo: em Windows, o filho nasce suspenso e só roda depois de
  atribuído a um Job Object com `KILL_ON_JOB_CLOSE`; em POSIX, ele lidera sessão/grupo próprios e o
  grupo recebe `SIGTERM`, carência e `SIGKILL` antes de o filho direto ser colhido, para nunca
  sinalizar um PID reciclado. Só a árvore deste despacho é tocada, nunca um processo localizado por
  nome. Falha de contenção antes da execução bloqueia o spawn; depois de efeitos já ocorridos o
  recibo declara `effects: uncertain`, e o campo `containment` informa o mecanismo realmente usado.
- Varredura não provada é indeterminada por definição: `containment.swept: "unproven"` — nenhuma
  árvore provada encerrada, mesmo sem erro registrado — passa a classificar o resultado como
  `effects: uncertain` com saída `5`, ainda que a unidade tenha saído com código zero e payload
  admitido. Só `job_object` e `process_group` contam como alcance provado. A opção escolhida foi
  classificar em vez de recusar antes de executar: o despacho acontece, o resultado é entregue ao
  condutor e fica marcado como indeterminado, porque recusar apagaria um resultado que talvez seja
  útil enquanto o que não se pode afirmar é apenas o fim da árvore.
- Reentrada do supervisor com limite refeito: o subcomando interno `supervise` recebe `--state-dir`
  e `--unit` em vez de um diretório de job arbitrário (`--job-dir` foi removido da linha de comando).
  Ele reaplica a verificação do diretório de estado e a derivação do diretório da unidade — link
  recusado por `realpath`, job obrigatoriamente contido na árvore de estado — e valida o manifesto
  inteiro antes de qualquer leitura ou execução: lista fechada de campos, tipos, schema, `unit`
  coincidente e caminhos dentro dos limites. Divergência responde `invalid_input` com efeitos `none`,
  sem executar argv e sem criar log fora da árvore.
- Falha interna do supervisor não deixa mais a unidade sem resposta: a árvore é encerrada pela mesma
  contenção em `finally`, o estado terminal sai como `crashed` com `effects: uncertain` quando a
  unidade pode ter rodado (nunca rebaixado a `none`), disco que impede gravar `result.json` responde
  saída `5` sem inventar arquivo, e a liveness do supervisor é provada por um lease exclusivo do
  sistema operacional — nunca por PID — de modo que `wait` devolve `indeterminate` ao encontrar
  supervisor encerrado sem resultado, em vez de esperar o prazo inteiro.
- Testes de comportamento offline (`tests/test_tl_job.py`) e portão de testes no workflow de
  validação: stdout grande fora do recibo, start concorrente executando a unidade uma única vez,
  fingerprint divergente recusado, Unicode e limites, timeout, comando inexistente, processo com
  falha, payload inválido, retomada sem duplicar efeito, caminhos inválidos e gravação final
  atômica. Inclui um ensaio sintético que compara bytes admitidos e número de consultas ao
  condutor; é ilustração de admissão, não medição de tokens. Inclui um caso com neto real que segue
  escrevendo depois do prazo: ele falha sem a contenção e passa com ela. O workflow de validação roda
  a suíte em Linux, exercitando o ramo POSIX dessa contenção.
- Casos dirigidos das duas regras acima: um líder POSIX que deixa neto vivo com batimento em arquivo
  e sai com zero (ramo de grupo de processo, exercitado pelo Linux do workflow e pulado no Windows)
  prova `swept: "unproven"` lido como `uncertain`/`5`; e a fronteira do `supervise` prova recusa com
  diretório de job alcançado por link, diretório de estado arbitrário, manifesto com campo extra, de
  outro schema, de outra unidade e com arquivo de resultado fora das árvores — cada recusa conferida
  junto com a ausência de argv executado e de log criado, e acompanhada do controle positivo em que
  a reivindicação real no próprio diretório continua rodando.

### Alterado

- Janela de publicação da reivindicação deixa de recusar `start` concorrente legítimo: no Windows o
  nome recém-criado por `os.replace` pode negar a abertura por um instante, e essa recusa era lida
  como reivindicação ilegível, devolvendo `invalid_input` a quem deveria reaproveitar a unidade já
  em curso. Agora só a recusa de abertura sobre um nome que acabou de inspecionar bem é repetida,
  dentro de um orçamento fixo de um segundo aberto uma única vez por chamada; passado o orçamento,
  volta a mesma recusa `invalid_input` com o motivo original. Reivindicação estável ilegível — JSON
  inválido, não UTF-8, acima do teto, não objeto — e nome que sequer pode ser inspecionado seguem
  recusados de imediato, sem orçamento algum.
- Manifesto passa a 19 arquivos distribuídos, incluindo `docs/EXECUTION_PROTOCOL.md` e
  `scripts/tl_job.py`. O método continua utilizável sem Python, com os limites de automação
  declarados; o supervisor é opcional e exige apenas Python 3 já presente no ambiente.
- Afirmações sobre custo e cache no playbook passam a explicitar dependência do harness, do modelo
  e do cache em uso: as observações registradas são pontuais de um consumidor e não são taxa
  transferível. Nenhuma economia percentual de tokens é prometida sem medição no ambiente real.
- Reaproveitamento de portões e suítes: um resultado vale somente para a mesma revisão da árvore e
  a mesma definição do portão; falha exige primeiro o caso dirigido e só depois a suíte inteira.
- Fila sequencial considera apenas candidatas da allowlist autorizada pelo board declarado;
  ampliar a lista é decisão do usuário.
- `scripts/validate_repository.py` compara os caminhos exportados em forma POSIX, para que a
  validação estrutural produza o mesmo resultado em Windows e em Linux.
- A unidade padrão de topo passa a ser a story inteira (`<story>-<rodada>`) com sua cadeia
  autorizada; os recibos de Maker, portões e Checker ficam internos ao condutor. Job por papel
  (`<story>-<papel>-<rodada>`) vira opcional e quebrar a story em microjobs não autoriza turnos de
  acompanhamento. O limite real — encadear papéis exige condutor adaptado, ou vale uma unidade por
  vez — passa a ser declarado em vez de prometido.
- A leitura linha a linha do diff integral passa a ser atribuída ao Checker em todos os contratos
  (orquestrador, playbook, Maker, Checker). O condutor confere identidade e revisão, cobertura de
  caminhos e critérios, portões na árvore final, destino de cada achado aberto e uma amostra crítica
  dirigida, despachando um verificador quando quiser sondagem independente; o parecer integral não
  volta ao contexto dele. Aprovação continua exigindo prova real.
- Papel designado com spec ratificada não reabre onboarding, triagem de tarefa, planejamento nem
  Classificador do fluxo pai: a ativação passa direto ao trabalho, conforme a autoridade do
  consumidor. O bypass é de ativação, não de regra — portões, limites de escrita e revisão
  independente continuam valendo.
- `observable_usage` passa a significar consumo observado, em uma string curta: medida realmente
  observada, referência ao lugar onde a métrica existe, ou `unknown`. Número inventado, `0` de
  preenchimento e instrução de como conferir o resultado deixam de caber ali; o supervisor não
  coleta tokens, custo nem uso do harness.
- `--result-file` passa a ser recusado quando um link já existente dentro do diretório de trabalho
  resolve para fora dele: a checagem léxica anterior aceitava uma grafia contida que escrevia em
  outra árvore. O caminho aceito continua sendo o léxico, de modo que a identidade da unidade não
  muda. Isso recusa o escape preexistente verificável; não elimina corrida de sistema de arquivos
  contra quem troque um componente depois da checagem, nem enxerga hard link.
- O arquivo de resultado passa a precisar estar ausente quando a unidade começa, e é isso que prende
  o payload admitido à execução: nada no conteúdo do arquivo nomeia quem o escreveu, então um
  `--result-file` reutilizado deixava uma unidade nova sair com zero sem tocar em `TL_JOB_RESULT` e
  herdar o `delivered`/`ready_for_delivery` de uma anterior. Caminho que já existe — ou que nem pode
  ser inspecionado — é recusado antes do spawn, com `start_failed`, `effects: none`, sem `outcome` e
  sem argv executado; o que for lido depois disso apareceu enquanto esta unidade rodava. A
  alternativa de emitir um token de identidade no spawn foi descartada por exigir que o condutor o
  devolvesse no payload, mudando o contrato do papel sem ganho de garantia.
- A árvore da unidade (`<state-dir>/jobs` e `<state-dir>/jobs/<unidade>`) passa a ser conferida por
  resolução de links, e não só por normalização léxica, em **todos** os comandos — inclusive os de
  leitura (`status`, `wait`, `result`). Um diretório de estado válido cujo `jobs`, ou cuja unidade,
  já exista como link para fora é recusado com `invalid_input` antes de qualquer `mkdir`,
  reivindicação, leitura ou escrita, de modo que nenhum manifesto, status ou log é criado fora. O
  caminho devolvido continua sendo o léxico, e um link que permanece dentro da árvore segue
  funcionando sem perder idempotência. Isso recusa o escape preexistente verificável; não promete
  imunidade a corrida adversarial de sistema de arquivos que troque um componente depois da
  checagem.
- `<state-dir>/anchors` entra na mesma conferência por resolução de links da árvore da unidade, e
  pelo mesmo motivo: a vinculação mora ao lado de `jobs` e é publicada por criação do diretório
  quando ele falta, então um link plantado ali antes do primeiro `start` era adotado e recebia
  `<unidade>.json` fora do diretório de estado que o chamador nomeou. A conferência acontece na
  derivação do diretório do job, isto é, antes de qualquer `mkdir`, lease, manifesto ou vinculação, e
  em todos os comandos, inclusive os de leitura: o escape é recusado com `invalid_input`,
  `effects: none` e saída `2`, sem vinculação externa, sem reivindicação e sem argv executado. Um
  link de `anchors` que permanece dentro da árvore de estado continua funcionando. Vale aqui o mesmo
  limite: isso recusa o escape preexistente verificável, não corrida que troque um componente depois
  da checagem, e não enxerga hard link.
- `wait` valida `--timeout` antes do laço, como `start`: zero, negativo, não numérico, infinito,
  `NaN` ou acima do limite viram `invalid_input` de imediato, em vez de virar espera inútil ou
  retorno imediato disfarçado de prazo.
- O recibo bem-sucedido de `start` e `status` fica em identidade, estado e localizadores.
  `effects`, `authorization_fingerprint` e `manifest_fingerprint` saem dele: as impressões
  permanecem no manifesto privado e no confronto de identidade, e `effects` continua onde há motivo
  observável a declarar — resultado terminal, erro, conflito e `wait_timeout`.
- Unidade terminada nunca é reaberta: `supervise` recusa com `conflict` e `effects: none` quando já
  existe `result.json`, antes de reivindicar o lease e de executar argv. A checagem é a existência
  do arquivo terminal, não seu conteúdo, então resultado corrompido ou truncado também recusa a
  segunda execução, e nada no disco é tocado na recusa.
- Validação do manifesto passa a ser a mesma para todos os leitores: `load_claim` aplica o gate
  central usado por `supervise` em reentrada de `start`, `status`, `wait` e `result`. Manifesto
  ausente, com lista de campos divergente, tipo inválido ou impressão não computável responde
  `JobError` compacto em JSON, nunca traceback, sem reaproveitar resultado e sem executar.
- Campo lido do disco passa a ser validado e limitado antes de virar recibo: localizadores são
  cortados por bytes, estado gravado fora da lista fechada vira `unknown`, e `enforce_ceiling`
  respeita `--max-bytes` inclusive ao reduzir aos campos centrais, caindo para um recibo mínimo
  marcado como `clipped` em vez de estourar o teto. Estado ou caminho grande no disco não vaza para
  a saída.
- Sucesso terminal passa a exigir fim comprovado do supervisor, e não apenas um `result.json`
  presente. O diretório da unidade fica ao alcance dela e todo campo do registro terminal é
  recomputável a partir do `manifest.json`, então uma unidade podia plantar um resultado válido e
  seguir escrevendo enquanto `wait` e `result` já a davam por entregue. Agora `wait` só encerra o
  laço com o arquivo terminal **e** o supervisor daquela unidade fora da trava exclusiva, e `result`
  responde `indeterminate` com efeitos `uncertain` e saída `5` enquanto ele estiver vivo. Sem prova
  possível — plataforma sem trava exclusiva ou lease inexistente — o recibo declara `termination`
  (`unsupported`, `unproven`) em vez de afirmar um fim que ninguém observou.
- O registro terminal aceito passa a precisar da forma completa que o supervisor sempre grava
  (`schema`, `job_id`, `unit`, `state`, `effects`, `exit_code`, `started_at`, `finished_at`,
  `logs`, `containment`, `result_status` e as duas impressões). Um registro montado por outro
  escritor, mesmo com as impressões corretas, é indeterminado em vez de virar entrega da unidade.
- Prova de fim indisponível deixa de entregar resultado terminal. Plataforma sem trava exclusiva de
  arquivo respondia `termination: unsupported` e ainda assim podia devolver um registro plantado
  como entregue, com efeitos `known` e saída `0`. Agora `wait`, `result` e o relatório interno só
  entregam com prova `proven`; `unsupported` e `unproven` recusam com estado `indeterminate`,
  efeitos `uncertain`, saída `5` e o campo `termination` dizendo qual fim não pôde ser provado.
- Manifesto presente e ilegível deixa de ser tratado como reivindicação concorrente incompleta.
  JSON inválido, texto que não é UTF-8, conteúdo acima do teto de bytes ou raiz que não é objeto
  são recusados de imediato como `invalid_input`, efeitos `none` e saída `2`, sem esperar a janela
  de reivindicação e sem traceback, igual para `start` em reentrada, `status`, `wait` e `result`.
  Só o manifesto ausente continua sendo esperado como reivindicação que ainda pode chegar.
- `supervise` sobre um lease ocupado passa a emitir o recibo compacto de `conflict` em stdout, com
  efeitos `none`, além da saída `3`. O caminho é alcançável pela linha de comando e respondia antes
  com código de saída nu, uma parada silenciosa para quem lê o recibo.
- Registro terminal sem prestação de contas completa sobre a árvore deixa de ser entrega. Faltando
  `containment`, a leitura da varredura respondia como se nada tivesse escapado e o recibo saía com
  efeitos `known` e saída `0`. Agora o registro precisa de contenção completa e tipada (`kind`,
  `established`, `unit_ran`, mais `swept` quando a árvore foi estabelecida) e do par exato de
  referências de log (`stdout` e `stderr`); qualquer registro parcial é `indeterminate` com efeitos
  `uncertain` e saída `5`. Ausência de campo nunca é lida como prova de que não houve sobrevivente.
- Reivindicação que não pode nem ser inspecionada deixa de ser tratada como ausente. Falha de `stat`
  no `manifest.json` por permissão ou erro de E/S virava espera pela janela de reivindicação e
  depois `conflict`, culpando uma concorrência que não existia. Só `FileNotFoundError` continua
  sendo ausência esperada; qualquer outro erro de sistema responde `invalid_input`, efeitos `none` e
  saída `2` de imediato, nomeando o motivo pelo qual o arquivo não pôde ser inspecionado.
- Varrer a árvore deixa de bastar para entregar: agora o supervisor presta contas dos descendentes
  que escaparam do alcance varrido, antes de soltar o lease. Um descendente que chamasse `setsid()`
  sobrevivia à varredura do grupo, esperava o lease cair e substituía o `result.json` por um registro
  completo e coerente — indistinguível, pelo conteúdo, da escrita da própria unidade, porque todo
  campo dele é recomputável a partir do `manifest.json`. No Linux o supervisor passa a se declarar
  `child subreaper` antes de a unidade existir, guarda a lista de filhos anterior a ela e, ao final,
  encerra e colhe o que foi reparentado para si; no Windows o Job Object já responde por isso e a
  saída antecipada (`breakaway`) nunca é concedida. O `containment` do registro ganha `accounted`
  (`job_object`, `subreaper_scan`, `unaccounted`) e `account_failed`; contas que não fecham fazem o
  resultado ser lido como `indeterminate`, efeitos `uncertain` e saída `5`, mesmo com fim provado e
  payload admitido. Fora do Linux, a contenção POSIX responde `unaccounted` por princípio: recusa
  conservadora, não detecção — e a lista vazia significa "nada reparentado aqui", não "nada
  sobreviveu no sistema". A defesa é contagem de processo, não selo no arquivo, porque um
  descendente do mesmo usuário leria qualquer segredo que o supervisor persistisse.
- Arquivo de resultado que não pode ser inspecionado passa a recusar de fato antes do spawn. A
  checagem usava `os.path.lexists`, que responde falso tanto para nome inexistente quanto para
  permissão negada ou erro de E/S, então a unidade rodava com o resultado não ligado à execução —
  justamente o contrário do que o método declarava. Agora a inspeção é por `lstat`: só
  `FileNotFoundError` é ausência, e qualquer outro `OSError` recusa com `start_failed`, efeitos
  `none`, sem `outcome` e sem argv executado, nomeando o motivo.
- `--max-bytes` inválido passa a caber no recibo. Declarado como `type=int`, o argparse saía com seu
  próprio despejo de uso antes de `main` chegar ao tratamento de erro, então um valor como `nope`
  devolvia texto ilimitado em stderr e nenhum JSON — furando a única promessa de tamanho que o recibo
  oferece, na opção que define esse tamanho. O valor passa a ser lido como texto e validado dentro da
  fronteira, como o `--timeout` de `wait`: não inteiro responde `invalid_input`, efeitos `none`, saída
  `2` e recibo recortado pelo teto padrão, antes de reivindicar diretório ou executar argv; número
  abaixo do mínimo continua sendo elevado ao mínimo.
- A prova de fim passa a ser ligada ao arquivo do lease, não ao nome dele. A unidade escreve no
  próprio diretório e podia pôr outro arquivo — sem trava alguma — atrás de `supervisor.lock`: a
  liveness respondia `gone`, a prova saía `proven` e um registro terminal forjado era entregue com
  efeitos `known` e saída `0` enquanto o supervisor continuava vivo e a unidade seguia escrevendo.
  Agora o `start` cria o arquivo do lease antes de tudo e grava na reivindicação o `lease_identity`
  (dispositivo e inode dele); todo leitor compara a identidade do descritor que abriu com a
  registrada e responde `replaced` quando o nome leva a outro arquivo — `wait` e `result` recusam
  com `indeterminate`, efeitos `uncertain`, saída `5` e `termination: "replaced"`, e `supervise`
  sobre um lease já trocado recusa com `conflict` sem executar argv. Reivindicação cujo
  `lease_identity` não descreve arquivo algum responde `unbound` e nunca `proven`; valor corrompido
  é recusado como `invalid_input`. O campo fica fora da impressão digital do manifesto, então a
  reutilização idempotente do `start` não muda. Onde a plataforma recusa a troca sob descritor
  aberto, o ataque falha antes disso e o supervisor segue `alive`; nos dois casos não há entrega.
- A vinculação esperada entre lease e reivindicação passa a ser publicada fora do diretório que a
  unidade escreve. Ligar a prova ao arquivo do lease não bastava, porque o `lease_identity` mora no
  `manifest.json`: uma unidade viva podia trocar o `supervisor.lock` e reescrever a reivindicação
  apontando para o arquivo plantado, e o leitor voltava a achar tudo coerente, entregando um
  registro terminal forjado com efeitos `known` e saída `0` enquanto ela seguia escrevendo. Agora o
  `start` cria `<state-dir>/anchors/<unidade>.json` com `O_EXCL`, antes da reivindicação, guardando
  unidade, `lease_identity`, as duas impressões e um token derivado desses campos — recomputado por
  todo leitor, nunca acreditado. `wait` e `result` confrontam a reivindicação com essa vinculação
  antes de entregar: reivindicação contraditória responde `diverged`, vinculação ausente ou ilegível
  responde `unanchored`, e as duas recusam com `indeterminate`, efeitos `uncertain`, saída `5` e o
  `termination` correspondente, mesmo com `result.json` completo no disco. `supervise` recusa com
  `conflict` o diretório cuja vinculação não responde por ele, o reaproveitamento do `start` só é
  oferecido enquanto o estado for `bound`, e vinculação existente nunca é sobrescrita — um `start`
  sobre diretório de unidade apagado recusa com `conflict` em vez de emitir vinculação nova. O
  recibo de `start` devolve o token em `binding`, e `wait` e `result` aceitam `--expect-binding`,
  conferido pela forma (dezesseis hexadecimais minúsculos, `invalid_input` e saída `2` fora dela)
  antes de qualquer diretório ser procurado; token bem formado de outra execução recusa a entrega
  como `diverged`. O alcance declarado é a permissão do sistema de arquivos: a vinculação protege
  contra quem escreve no diretório da unidade, e contra quem escreve no diretório de estado inteiro
  só o token guardado fora do disco recusa.

### Migração

- A exportação e a instalação passam a criar também o subdiretório `scripts/`. Um perfil instalado
  com 17 arquivos continua consistente consigo mesmo; ao atualizar, copie os 19 caminhos do
  manifesto de uma única revisão e regrave `INSTALLATION.md` com 19 hashes. Pacote com 17 arquivos
  conferidos contra um manifesto de 19 bloqueia a instalação, como qualquer divergência.
- Nenhuma ação é necessária para continuar usando o método sem o supervisor: ele é opcional e não
  é chamado por nenhum contrato existente. Quem quiser acoplá-lo segue o [protocolo de
  execução](docs/EXECUTION_PROTOCOL.md#acoplar-ao-condutor-existente); não há serviço, dependência
  ou credencial nova.
- Nenhuma promoção automática de `operational_verified` decorre desta versão: o smoke test
  operacional continua sendo prova separada do consumidor.

## [0.7.1] - 2026-09-11

### Adicionado

- Regra de admissão de saída de ferramenta: em sessão longa a quantidade de requisições pesa tanto
  quanto o recorte de um despejo isolado, porque cada ida e volta reenvia todo o contexto já
  admitido; agrupar chamadas de ferramenta independentes entre si na mesma requisição reduz turnos
  sem soltar o recorte já exigido do que é admitido no contexto.

## [0.7.0] - 2026-09-10

### Alterado

- Ordem padrão do Classificador: Agy Gemini 3.8 Flash medium → Codex Luna medium → Claude Sonnet
  medium, preservando os pares, a validação e as regras de fallback e de precedência local.
  As demais referências à cadeia remetem ao perfil publicado, e referências legadas à ordem do
  Classificador e ao Searcher no `README.md` e em `docs/PROJECT_CONFIGURATION.md` foram tratadas
  como harmonização documental de uma regra existente de inclusão do papel no schema e aos papéis
  da fase.

### Adicionado

- Próximos passos numerados no fechamento ou na devolução de uma decisão ao usuário, com ação e
  limites explícitos. Resposta numérica seleciona somente a opção do último menu válido, sem
  autorizações implícitas, execução por silêncio ou pausas adicionais em lotes já autorizados.

- Campos opcionais do registro conceitual de medição: `call_id` (dedup de registros repetidos da
  mesma chamada identificada, preservando chamadas distintas, retries e tentativas interrompidas),
  `usage_source`, `cache_io`, `machine_scope` (chave tipada estável entre versões, ausência não
  implica zero) e `capability_detection`; nenhum passa a obrigatório e nenhum registro anterior
  deixa de ser conforme.
- Parada honesta com checkpoint em disco ao atingir limite de rodadas/turnos sem concluir (playbook
  e contrato do Maker), complementando a regra existente de não repetir indefinidamente até obter
  verde; não é sucesso e não dispara novo loop automático.
- Critério do Checker para revisar registros de medição (conferir os cinco campos opcionais definidos
  em configuração de projeto quando presentes, como dedup por `call_id` de registros da mesma chamada,
  `usage_source`, `cache_io`, `machine_scope` e `capability_detection`, lendo qualquer campo ausente como
  desconhecido e não como desconformidade) e para tratar parada honesta com checkpoint como pendência,
  não aprovação implícita.
- Regra de admissão de saída de ferramenta no playbook, com reflexo nos contratos do Maker e do
  Searcher: o custo de uma leitura é seu tamanho multiplicado por quantas requisições ela
  sobrevive no contexto, então a decisão que importa é o que deixar entrar, não o que remover
  depois — remoção posterior no meio do histórico invalida o prefixo de cache dali para frente e
  cobra reescrita. Saída volumosa fica em artefato e o contexto recebe localizador com resumo,
  preferindo a forma de ferramenta que devolve localizador em vez de conteúdo; o recorte é sobre o
  que permanece no contexto, não sobre o que se verifica, e conferência do diff inteiro, leitura de
  fonte para prova crítica e revisão independente continuam exigidas. Saída não preservada é limite
  explícito, nunca recorte silencioso.
- Diretrizes de reuso condicionado de leituras na mesma sessão (com exceções para mudança de fonte,
  revisão, contexto, compactação, truncamento ou exigência contratual) e distinção operacional entre
  Searcher (levantamento factual) e Planner (arquitetura e especificação), preservando a leitura
  direta proporcional e a classificação com pin como restrição.

## [0.6.0] - 2026-09-08

### Corrigido

- Regras de condução do método para convergência, confinamento e limites probatórios: escalonamento
  consultivo após N rodadas de rework (padrão 3, configurável no perfil do consumidor) com achados
  centrais da mesma classe, classificando fase consultiva (`debate`) para diagnosticar
  manifestações do mesmo problema versus requisitos a consolidar antes de novo retrabalho; tabela
  normativa de procedência por tipo de informação e conteúdo que sustenta o valor no briefing
  (`story_id`, fase e papéis solicitados da solicitação ou spec com valor literal; catálogo, pins e
  cadeias de fontes de política conforme a precedência vigente — instrução atual do usuário
  registrada, configuração do consumidor em `PROJECT.md` ou perfil publicado na ausência de
  configuração local —, legitimando catálogo montado para a chamada quando cada entrada tem
  procedência verificável e rejeitando a entrada sem procedência, preservando projetos sem perfil
  persistido; autoria efetiva e famílias do registro de `Agent runs` efetivo; evidências de custo e
  capacidade de `docs/MODEL_ROUTING.md`; medição local com ID na primeira coluna; julgamento
  vinculado por hash com veredito explícito), fixando que localização que resolve não basta e
  rejeitando fonte incompatível com o tipo ou com o valor, além de rejeitar listas compostas na hora
  sem procedência por entrada ou fontes genéricas como "um arquivo existente", com entrega ao
  Classificador apenas de IDs com origem; limite declarado das provas mecânicas, em que conferência
  mecânica e vinculação por hash comprovam correspondência e integridade, não correção ou
  pertinência ao workload, mantendo adequação e alcance econômico como julgamento registrado; escopo
  de leitura dos papéis confinado à raiz consumidora e à raiz do pacote informadas, exigindo
  autorização explícita no briefing para qualquer outra fonte e declaração obrigatória de desvio no
  parecer ou relatório; Searcher classificado sob demanda recebendo modelo e effort da
  classificação da fase (papel auxiliar `searcher`, com a mesma estrutura dos demais papéis e tier
  que dimensiona a consulta) ou de pin explícito passado como restrição, cobrindo as buscas daquela
  fase sem reclassificar a cada consulta, cadeia por omissão do Searcher (Agy → Claude → Codex) no
  perfil publicado, e tornando explícito que a única exceção de inicialização com perfil fixo é a do
  próprio Classificador; admissão aditiva da propriedade opcional `searcher` em `roles` no schema de
  resultado de classificação (versão 2 mantida); e contrato do Classificador que passa a admitir o
  papel searcher com tier de consulta. Motivado pela análise em T009 e pela condução com retrabalhos
  sucessivos e leitura fora da raiz sem autorização.

### Alterado

- Compatibilidade unidirecional do schema de resultado de classificação — objetos com os papéis
  anteriores continuam válidos no schema desta revisão; objetos com `roles.searcher` são rejeitados
  por schemas anteriores; `schema_version` permanece 2 e a revisão efetiva do contrato e do schema é
  identificada pela release, prevista como menor (v0.6.0) por capacidade nova de classificação;
  consumidores devem atualizar o pacote antes de classificar com o papel searcher.

## [0.5.0] - 2026-09-07

### Adicionado

- Revisão posterior por outra família e registro `Agent runs`: sob `checker_independence: preferred`,
  revisão concluída com mesma família por indisponibilidade comprovada abre pendência no bloco
  `## RF-<unit_id>-rNN` na evidência da unidade, visível no cabeçalho global em `review_followups`,
  permitindo conclusão da Task sem flexibilizar `required`; identidade completa de unidade em quatro
  formas compatível com projetos com e sem módulos em Native e BMAD; ciclo de vida de pendências com
  estados `pending`, `superseded` (com substituta vinculada e mapeamento obrigatório de garantias em
  `reason`) e `closed` (somente por parecer aprovado de família distinta cobrindo o mesmo alvo);
  revisão posterior separada de autorização para novas alterações; menu de ativação com opção de
  revisão por outra família baseada em elegibilidade no catálogo; comprovação de disponibilidade
  pela chamada normal autorizada; e tabela uniforme `Agent runs` com identificador sequencial único
  por unidade, preservando tentativas descartadas e chamadas falhas.

## [0.4.1] - 2026-09-07

### Corrigido

- O contrato do Orquestrador, os perfis e o SKILL.md tornam explícito que o Orquestrador nunca
  escolhe modelo ou effort de Planner, Maker ou Checker por conta própria ou por sugestão: classifica
  em toda fase antes do primeiro despacho de cada papel; preferência de harness ou família é
  restrição de entrada do Classificador; só um modelo nomeado explicitamente pelo usuário ou pelo
  consumidor vira pin, e mesmo assim o Classificador é chamado. Motivado por uma condução em que o
  Checker foi fixado por suposição antes de classificar.

## [0.4.0] - 2026-09-06

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
- Migration Findings: durante Import Context e Migrate Work, bugs confirmados e suspeitas
  encontrados na análise viram Tasks Native `fix` ou `analysis` em `draft` na fila da área
  responsável, com evidência mínima, deduplicação contra as fontes autoritativas, autoridade BMAD
  preservada, sem habilitar fila nem promover a `ready` sem spec, e bloqueio só da unidade cuja
  conclusão esteja impedida.

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
[0.4.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.3.0...v0.4.0
[0.2.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.1.5...v0.2.0
[0.11.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.10.0...v0.11.0
[0.12.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.11.0...v0.12.0
[0.13.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.12.0...v0.13.0
[0.14.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.13.0...v0.14.0
[0.15.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.14.0...v0.15.0
[0.16.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.15.0...v0.16.0
[0.17.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.16.0...v0.17.0
[0.18.0]: https://github.com/thinglab-dev/tl-orchestrator/compare/v0.17.0...v0.18.0
