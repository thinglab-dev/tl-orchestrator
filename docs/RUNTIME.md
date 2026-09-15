# Runtime durável (opcional): executar um lote autorizado sem sessão de Orquestrador

`scripts/tl_runtime.py` é o plano de controle determinístico entre `AUTHORIZE` e `CLOSE` do
[Modo Automático](WORK_MODEL.md#modo-automático-execução-de-lote-finito-autorizado). Ele
executa um lote congelado por horas sem manter nenhuma conversa de modelo aberta: cada
chamada de Maker ou Checker é curta, recebe um Context Pack montado por código e devolve um
arquivo de resultado. O runtime escolhe a próxima unidade pelo DAG, roda portões, aplica
política, faz commit/push/PR/merge conforme os efeitos permitidos, acompanha CI, classifica
falhas, detecta loops e escreve o relatório da manhã a partir do journal.

Ele é **opcional** e **adicional**: o método documental continua válido sem ele. Não há
servidor, banco, daemon permanente nem dependência fora da biblioteca padrão do Python. O
runtime nasce no `FREEZE_BATCH` e morre no `CLOSE`; um crash vira pausa, e a retomada é
`tl_runtime.py run` de novo.

## O que ele nunca faz

- Não escolhe trabalho fora de `frozen_scope.units`, não cria Task e não amplia escopo.
- Não edita a própria política, os limites, as rotas ou os portões; só mede e recomenda.
- Não executa `push`, PR, merge, tag ou release sem o efeito correspondente em
  `authorization.permitted_effects`. O worker nunca roda `git`/`gh`: o runtime executa.
- Não converte ambiguidade em certeza: efeito externo sem resultado gravado é reconciliado
  contra Git, remoto ou `gh`; sem evidência suficiente, a unidade espera o operador.
- Não inventa custo nem tokens: uso não observado fica `unknown`, e um teto em dólar só é
  aplicado sobre chamadas cujo adapter reportou custo.
- Não abre outro lote ao fechar.

## Instalar e usar

O arquivo é distribuído no pacote (`_tl-orc/package/scripts/tl_runtime.py`) junto com
`tl_ci_slice.py` e importa `tl_job.py` do mesmo diretório. Exige Python 3.10+ e `git`; `gh`
somente quando o lote permite PR/merge remoto.

```
python _tl-orc/package/scripts/tl_runtime.py validate --batch _tl-orc/project/batches/B023.json --config _tl-orc/runtime.json --repo .
python _tl-orc/package/scripts/tl_runtime.py run      --batch _tl-orc/project/batches/B023.json --config _tl-orc/runtime.json --repo .
python _tl-orc/package/scripts/tl_runtime.py status   --batch ... --config ... --repo .
python _tl-orc/package/scripts/tl_runtime.py report   --batch ... --config ... --repo . [--out morning-report.md]
python _tl-orc/package/scripts/tl_runtime.py journal  --batch ... --config ... --repo . [--unit T042]
python _tl-orc/package/scripts/tl_runtime.py decide   --batch ... --config ... --repo . --unit T042 --option retry|skip
```

`run` devolve 0 (fechado ou ocioso), 2 (parada de lote ou recusa de entrada), 3 (fechado com
unidades paradas/bloqueadas), 4 (entrada inválida), 5 (outro runtime segura o lease). O
estado fica em `<repo>/_tl-orc/runtime/<batch id>/` (ou `--state-dir`): `journal.jsonl`,
`status.json`, `report.md`, `packs/`, `artifacts/`, `jobs/` (estado do `tl_job.py`),
`lease.lock`. O runtime acrescenta `/.tl-runtime/` e `/_tl-orc/runtime/` ao
`.git/info/exclude` do consumidor; nada disso entra em commit.

Para dormir com o lote rodando, deixe o processo em segundo plano (por exemplo, `nohup`,
`Start-Process` ou um Job do PowerShell). Se a máquina dormir e o processo morrer, rode
`run` de novo ao acordar: ele reconcilia e continua.

## Entradas

### Lote congelado (`batch.schema.json`)

O mesmo objeto do Modo Automático, em JSON. O runtime exige `authorization` completa
(`proposal_digest`, `authority_source`, `authorized_at`, `permitted_effects`),
`batch_concurrency: 1` e `frozen_scope.units[]` com `work_ref`, `spec_revision` e
`dependencies` dentro do próprio lote. `immutable_digest` é obrigatório: o SHA-256 do JSON
canônico de `frozen_scope` sem essa chave (a recusa imprime o valor esperado). `local_write`
falso é recusa: sem ele não há Maker. As seções mutáveis `budget` e `execution` são **projeção**: o runtime as
reescreve a partir do journal para que leitores do Modo Automático vejam consumo, chamada
pendente e unidade corrente; as seções congeladas nunca são tocadas.

`permitted_effects` ganha as chaves opcionais `pull_request_merge` e `ci_rerun` (v0.17.0):
sem a primeira, o runtime abre o PR e para ali; sem a segunda, nunca reexecuta CI. `local_merge` faz merge `--no-ff` na branch base quando não há
PR. `continue_independent_after_block` decide se unidades independentes continuam depois
de uma unidade parada; o padrão do schema continua `false`.

### Especificação da unidade

`work_ref` é um caminho relativo ao repositório ou um id resolvido em `tasks_dir`
(`T042` → `_tl-orc/project/tasks/T042*.md`). O arquivo precisa de frontmatter com
`scope_paths` (ou `content_paths`); opcionalmente `do_not_touch`, `flags` (ativam portões
de `gates.by_flag`), `type`, `acceptance` e `verification`. `spec_revision` do lote é o
SHA-256 do arquivo (64, 16 ou 12 hex); divergência é `unexpected_revision_drift` e nada roda.

### Configuração do runtime (`runtime-config.schema.json`)

```json
{
  "schema_version": 1,
  "adapters": {
    "claude": {
      "argv": ["claude", "-p", "Read the file {pack_path} and do exactly what it says. Write the result file it names.",
               "--output-format", "json", "--model", "{model}", "--permission-mode", "acceptEdits", "--allowedTools", "{tools}"],
      "family": "anthropic", "usage_parser": "claude_json",
      "capabilities": {"tools_allowlist": true, "network_sandbox": false, "usage_telemetry": true}
    },
    "codex": {
      "argv": ["codex", "exec", "--json", "--sandbox", "workspace-write", "--model", "{model}", "-C", ".", "{pack_text}"],
      "family": "openai", "usage_parser": "codex_jsonl",
      "capabilities": {"tools_allowlist": false, "network_sandbox": true, "usage_telemetry": true}
    }
  },
  "roles": {
    "maker":   {"adapter": "claude", "model": "claude-sonnet-5", "tools": ["Read", "Glob", "Grep", "Edit", "Write", "Bash(go test:*)"], "timeout_seconds": 1800},
    "checker": {"adapter": "codex",  "model": "gpt-5.6", "timeout_seconds": 900}
  },
  "gates": {
    "always": [{"id": "vet", "argv": ["go", "vet", "./..."]}, {"id": "test", "argv": ["go", "test", "./..."]}],
    "by_flag": {"ui": [{"id": "e2e", "argv": ["npm", "run", "e2e"]}]},
    "canonical": [{"id": "full", "argv": ["go", "test", "-count=1", "./..."]}]
  },
  "ci": {"enabled": true, "poll_seconds": 60, "timeout_seconds": 1800},
  "limits": {"max_wall_clock_seconds": 43200, "max_cost_usd": null},
  "base_branch": "main", "sensitive_paths": ["deploy/", ".github/workflows/"],
  "env_allowlist": ["GOFLAGS"]
}
```

Placeholders do `argv`: `{pack_path}`, `{pack_text}`, `{result_path}`, `{model}`,
`{effort}`, `{tools}`, `{role}`. Portões aceitam `{repo}`, `{unit}`, `{branch}`, `{base_commit}` e
`{tree}` (por exemplo, `audit_diff.py --base {base_commit}` do tl-deep-review), e seus
resultados entram no pack do Checker como verificação já executada. As capacidades são declaradas pelo consumidor, não
inferidas; toda capacidade `false` aparece como limitação no relatório. Maker e Checker
precisam de `family` diferente (`required_checker_independence_unavailable` caso contrário).

## Step: a primitive do journal

Toda ação é um Step com id estável, classe de efeito e digest de entrada. O runtime grava
`step_intent` **antes** do efeito e `step_result` **depois**, com `tree_before`/`tree_after`
(árvore Git do diretório de trabalho, inclusive arquivos novos) para classes mutantes. É o
write-ahead AC07 do Modo Automático generalizado de "chamada de modelo" para qualquer ação.

| Classe de efeito | Exemplos de step |
| :--- | :--- |
| `none` | `T042:prepare`, `gate:test:<tree>` (cache por árvore: mesmo tree, mesmo resultado) |
| `model_call` | `T042:r1:maker`, `T042:r2:checker`, `T042:r1:maker:a1` (nova tentativa) |
| `local_commit` | `T042:commit:<tree>` |
| `push` | `T042:push:<commit>` |
| `pull_request` | `T042:pr` |
| `pull_request_merge` / `local_merge` | `T042:merge:<commit>` |
| `ci_query` | `T042:ci:<commit>:<ts>` (nunca reutilizado) |
| `ci_rerun` | `T042:ci_rerun:<commit>:1` (só com `permitted_effects.ci_rerun`) |

Retomar é dobrar o journal: resultado `ok` com o mesmo `input_digest` é reutilizado; step
sem resultado é reconciliado antes de qualquer escalonamento:

| Intenção aberta | Evidência consultada | Veredito |
| :--- | :--- | :--- |
| `model_call` | estado do `tl_job.py` | nunca iniciou → `released` (não cobrada) · ainda rodando → o runtime **anexa** ao supervisor e espera · terminou sem resultado gravado → `ambiguous`, cobrada; a árvore suja vira checkpoint (`refs/tl/checkpoints/...`) e o próximo Maker recebe "continue do checkpoint" |
| `local_commit` | árvore e pai de `HEAD` | árvore da intenção sobre o pai gravado → `ok` · `HEAD` avançou além do pai sem ser o commit esperado → `ambiguous`, `awaiting_operator` (nunca adota commit alheio) · senão → `released` |
| `push` | `git ls-remote` contra o `remote_before` gravado na intenção (também quando o próprio `git push` devolve erro: remoto no commit → `ok`; remoto como antes → falha normal; outro estado → `awaiting_operator`, nunca retry) | remoto no commit esperado → `ok` · remoto exatamente como observado antes da intenção → `released` (push roda: o efeito de um push é visível na ref remota, então "estado igual ao anterior" é a única condição em que repetir produz exatamente o resultado autorizado, mesmo que uma automação tenha apagado a branch entre a queda e a retomada) · qualquer outro estado (movido, apagado quando antes existia, divergente, inacessível) → `ambiguous`, unidade em `awaiting_operator` |
| `pull_request` | `gh pr list --head` | existe com a mesma base e `headRefOid` exatamente igual ao commit revisado gravado na intenção → `ok` · não existe → `released` (o create adota um PR existente da branch só com base e head exatos, nunca duplica) · base/head diferentes, head ausente ou `gh` falhou → `ambiguous`, `awaiting_operator` |
| `pull_request_merge` | `gh pr view` | mesclado com `baseRefName` e `headRefOid` iguais à base e ao commit revisados → `ok` · aberto → `ambiguous`, `awaiting_operator` (um enfileiramento em merge queue não muda o estado do PR, logo "aberto" não prova que a chamada não aconteceu; o retry do operador adota um merge feito pela fila sem nova chamada) · mesclado em outra base ou outro head, ou `gh` falhou → `ambiguous`, `awaiting_operator` |
| `local_merge` | `merge-base --is-ancestor` do commit revisado, `MERGE_HEAD`, ponta da base contra o `base_before` gravado na intenção | commit revisado alcançável da base → `ok` · merge em andamento na árvore → `ambiguous`, `awaiting_operator` (o runtime nunca faz `merge --abort` de um merge que não iniciou) · base exatamente como antes da intenção → `released` (o merge só roda se a branch ainda aponta para o commit revisado) · base movida → `ambiguous`, `awaiting_operator` |
| `ci_rerun` | nenhuma | `ambiguous`: contado como reexecução, nunca repetido |
| `gate`, `ci_query`, `prepare` | nenhuma | `released` (rodam de novo; antes dos portões a árvore volta à árvore do Maker gravada no step, para que resto de portão nunca chegue ao commit). `prepare` recusa uma branch `tl/<lote>/<unidade>` pré-existente cuja ponta não seja a base esperada (`stale_branch`, `awaiting_operator`): commit alheio nunca entra na entrega fora do diff revisado. Merge de dependência ainda não integrada na branch da unidade é escrita local na branch descartável do runtime (gravada no step `prepare` com `deps` e `base_commit`), não `local_merge` na base |

Cada intenção carrega `runtime_stamp` (`<versão>:<digest da config>`). Uma intenção aberta
gravada por outra versão para o lote com `stale_workflow_version`; depois de inspecionar,
`run --accept-stale-version` registra a aceitação e continua. Cada linha carrega `prev`, os
primeiros 16 hex do SHA-256 da linha anterior: linha editada, removida ou inserida depois
quebra a cadeia. Linha inválida ou cadeia quebrada é recusa (exit 2), nunca ignorada em
silêncio.

### Por que JSONL e não SQLite

Um lote tem um escritor por vez (lease com lock exclusivo, o mesmo mecanismo do
`tl_job.py`), gera centenas a poucos milhares de linhas, e cada linha é anexada com
`fsync`. Os fatos críticos que precisam ficar consistentes entre si (intenção, resultado,
orçamento, estado da unidade) são deriváveis de uma única sequência ordenada, então uma
transação multi-tabela não compra nada. O journal é legível com `grep`, versionável no
tempo e sobrevive a qualquer ferramenta. SQLite entraria só como índice derivado para
consultas entre muitos lotes, e isso não é necessidade desta geração.

## Scheduler

Estados: `ready`, `running`, `waiting`, `retryable`, `parked`, `blocked`, `completed`,
`failed`, `awaiting_operator`. A próxima unidade é a primeira em ordem topológica (desempate
por id) que está no lote, com `spec_revision` válida, dependências `completed`, sem outra
unidade `running`, com reserva de orçamento (a chamada do Maker mais uma de Checker) e sem
violação de política. Dependente de unidade `parked`/`failed`/`awaiting_operator` fica
`blocked`; com `continue_independent_after_block: false`, todas as demais ficam `blocked`.
Concorrência é 1; o journal e o scheduler não dependem disso, mas worktrees paralelas
ficam para depois de medir.

## Ciclo da unidade

`prepare` (branch `tl/<lote>/<unidade>` a partir da base ou da branch da dependência não
mesclada) → `implement` (Maker) → `contain` (escopo, caminhos sensíveis, segredos, mudança
real) → `gates` (sempre + por flag, cache por árvore) → `review` (Checker de outra família
sobre o diff completo) → rework limitado → `commit` → `push` → `pull_request` → `ci` →
`merge` → `complete`. O Checker que altera a árvore é `unexpected_tree_state` e a árvore é
restaurada. `intent_gap` dirigido a `human` põe a unidade em `awaiting_operator` com opções
`retry`/`skip`.

## Falhas, movimentos e detector de loop

Classes: `transient`, `harness`, `environment`, `semantic`, `verification`,
`authorization`, `budget`, `scope`, `state_integrity`, `security`, `unknown`. A
classificação é determinística (estado do transporte, `stderr`, `outcome`, `blockers`,
veredito). Movimentos: `retry` (transitória: backoff exponencial até `transient_retries`;
harness: até `harness_retries`), `rework` (semântica/verificação até
`max_rework_rounds_per_unit`; escopo: árvore restaurada uma vez), `park` (ambiente,
esgotamento, desconhecido), `stop` (autorização, orçamento, segurança, integridade de
estado). `secret_detected` e caminho sensível param o lote antes de qualquer commit.

O detector de loop usa o histórico persistido de tentativas (`attempt`) e nunca zera com
troca de modelo: mesma assinatura normalizada (números, hashes, caminhos e tempos removidos)
`loop_threshold` vezes → `parked: loop_detected`; árvore A→B→A → `diff_oscillation`; mesmos
achados do Checker em rodadas consecutivas → `stagnation` (a regra da fila sequencial).
`max_parked_units` para o lote quando o acúmulo de unidades paradas deixa de ser útil.

## Fronteira de política

| Ponto | Mecanismo | Limitação declarada |
| :--- | :--- | :--- |
| Spawn do worker | `tl_job.py` (contenção da árvore de processos, timeout, recibo limitado) com ambiente filtrado: só a allowlist base mais `env_allowlist`; `DO_NOT_TRACK=1` | ferramentas e sandbox de rede dependem do harness: use `{tools}` e sandbox nativos quando existirem; adapter sem nenhuma das duas só roda com `accept_unisolated_worker: true`, e o relatório avisa |
| Depois de cada chamada de modelo | `HEAD` e branch comparados antes/depois: worker que faz commit, checkout ou merge por conta própria é `unexpected_tree_state` e para o lote | a detecção é a posteriori; o harness sem allowlist ainda consegue executar `git` |
| Antes de descartar árvore | toda restauração (escopo, artefato de portão, Checker que escreveu, unidade parada) grava antes o estado atual em `refs/tl/discarded/<lote>/<n>` e anota no journal | nada é apagado sem cópia; limpar as refs é tarefa do operador |
| Antes de cada unidade | árvore suja antes do `prepare` para o lote (`unexpected_tree_state`), inclusive quando a branch da unidade já está em checkout: edição do operador nunca vira commit do runtime | sujeira produzida pelo próprio runtime (crash no meio do Maker) é reconhecida pelo journal e vira checkpoint |
| Depois de cada Maker | `sensitive_paths` e varredura de padrões de segredo no diff **integral** e nos bytes de cada arquivo alterado (binário incluso; AWS, chaves privadas, GitHub, Anthropic/OpenAI, Slack, Google) têm precedência e param o lote; depois `dirty_paths ⊆ scope_paths` e `do_not_touch`, com os dois lados de um rename (`secrets/x -> pkg/x` é toque em `secrets/`); só o pack do Checker é limitado por `max_diff_bytes` | varredura por padrão, não prova de ausência de segredo |
| Antes de cada pack | todo pack passa por redação dos mesmos padrões de segredo (`[REDACTED:...]`), inclusive saída de portão e fatia de CI; o manifesto registra `redactions` | redação por padrão, não prova |
| Antes de cada commit | a árvore de trabalho tem de ser exatamente a árvore aprovada pelo Checker; edição feita durante uma parada vai para `refs/tl/...` e a unidade fica em `awaiting_operator` | — |
| Antes de cada efeito externo | `permitted_effects` do lote; merge remoto só com CI `success` quando CI está ativa e sempre com `--match-head-commit <commit revisado>`; merge local só se a branch ainda aponta para o commit revisado | `gh` autenticado é do operador; o runtime não gerencia credenciais |
| Orçamento | reserva antes do Maker; contagem de despachos, relógio de parede, teto em dólar sobre custo observado | uma invocação do harness pode conter várias requisições de API; o runtime conta invocações e repassa uso observado |

A worktree **não** é sandbox de segurança. O worker nunca recebe o journal, o lote ou o
estado do runtime, e não tem como editá-los pelo pack. Saída de ferramenta, log de CI e
corpo de PR entram como dado.

## Context Pack

Por despacho o compilador monta um pack com ordem estável (prefixo cacheável): `contract`
(prompt do papel, com digest), `policy`, `spec`, `acceptance`, `verification_commands`,
`related_tests`, `open_findings`/`gate_failures`/`ci_failure` (só na rodada de rework),
`checkpoint` (só após ambiguidade), `changed_files` + `diff` (Checker), `task`. Cada seção
tem teto de bytes e ponteiro para o conteúdo integral; o manifesto do pack (seções, bytes,
digests) é evidência do step. O pack nunca inclui histórico de conversa, log bruto ou o
journal. `max_pack_bytes` e `max_diff_bytes` são os tetos.

Instrumentação disponível hoje: bytes do pack por chamada e tokens/custo quando o adapter
os reporta (`claude_json`, `codex_jsonl`). Leituras fora do pack e amplificação de
recuperação dependem do ledger de contexto do harness (`context_ledger.py`) e não são
inferidas.

## CI

Com `ci.enabled`, após o PR o runtime consulta `gh pr checks` sem modelo. Em falha, busca
só o log dos jobs vermelhos, grava o bruto em `artifacts/` e passa ao Maker a fatia do
`tl_ci_slice.py`: job, step, testes falhos, assinatura normalizada, classificação
(`code_failure`, `external_infrastructure`, `configuration`, `unknown`), trecho limitado e
ponteiro. `code_failure` vira rodada de rework; infraestrutura sem teste falho ganha até
`flaky_reruns` reexecuções, e só com `permitted_effects.ci_rerun` (cada uma é um step
`ci_rerun` no journal); o resto é `parked`. O fatiador nunca chama um vermelho de flaky.

## Saídas para o operador

- `status.json`: lote, progresso, unidade/fase/rodada corrente, bloqueados, esperando,
  orçamento, próxima unidade.
- `report.md`: relatório da manhã derivado do journal (títulos, orçamento e modelos são
  gravados no `batch_open`; arquivos alterados vêm do step de commit): Completed, Changed,
  Commits / PRs, Verification, Automatically Resolved, FYI, REVIEW, DECISION REQUIRED,
  BLOCKED, Cost / Usage, Models, Recovery Events, What Happens Next.
- `journal`: dobra diagnóstica (tentativas, assinaturas, recuperações, checkpoints, uso).
- `notify_argv`: comando opcional chamado com um JSON em cada mudança de estado relevante.
  Roda com a confiança do operador, como os `argv` de adapters e portões (a configuração é
  do consumidor, não do modelo), com o mesmo ambiente filtrado dos workers; não é um efeito
  do lote e `permitted_effects` não o governa.

`decide --option retry` devolve a unidade a `retryable` (o trabalho parado está no
checkpoint); `skip` marca `failed`. Um lote `blocked` (só por decisões) reabre no próximo
`run`; um lote `stopped` (segurança, orçamento, autorização, integridade) nunca reabre:
nova autorização.

## Testes e prova

`scripts/tests/test_tl_runtime.py` cobre, com harness e `gh` falsos scriptados e Git real:
DAG com dependência, rework, esgotamento, estagnação, loop por assinatura, oscilação,
`intent_gap` → decisão do operador, expansão de escopo (árvore restaurada), segredo,
caminho sensível, push não autorizado, drift de spec e de escopo, mesma família recusada,
reserva de orçamento, árvore suja, lease exclusivo, crash de harness, transitória com
backoff, bloqueio por autorização, e injeção de falha por `TL_RUNTIME_FAULT` (crash antes
do efeito do Maker, depois do efeito do Maker, depois do commit, depois do push, depois do
PR, remoto divergente, journal corrompido, versão obsoleta), além do laço de CI com fatia,
rerun de infraestrutura e reconciliação de merge.

## Limites conhecidos

- `gh pr merge` só aceita precondição de head (`--match-head-commit`), não de base, e devolve
  sucesso ao enfileirar num merge queue. O runtime revalida base, head e estado `OPEN`
  imediatamente antes e só conta como mesclado o estado terminal `MERGED` com a mesma base e
  o mesmo head logo depois: PR ainda aberto vira `merge_queued` (step `ambiguous`,
  `awaiting_operator`; o retry adota o merge feito pela fila sem nova chamada) e base ou
  head diferentes viram `merged_into_unexpected_base` / `merged_unexpected_head`, não um
  merge silencioso. Fechar essa janela é governança do
  repositório (proteção de branch), não do runtime.

- Concorrência 1. Worktrees em paralelo dependem do pool/árbitro do `tl_supervisor.py` e de
  medição; não entram nesta versão.
- Planner e Advisor não são despachados pelo runtime: a unidade precisa entrar com spec
  ratificada. Proposta e ratificação continuam na sessão do Orquestrador.
- Nenhum cálculo de custo estimado: sem uso observado, `unknown`.
- Sandbox de rede só onde o harness a oferece.
- A classificação de falha é por padrão; `unknown` leva a `parked`, não a tentativa cega.
- O journal e o lote não são protegidos por sistema de arquivos contra um worker com escrita
  irrestrita (por exemplo, `claude` sem sandbox). O runtime detecta árvore alterada pelo
  Checker, `HEAD`/branch movidos por qualquer worker e journal adulterado (cadeia de hashes),
  mas detecção não é prevenção: mantenha `--state-dir` fora do repositório, use a allowlist
  de ferramentas do harness e um sandbox quando ele existir.
