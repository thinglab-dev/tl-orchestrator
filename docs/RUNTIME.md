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
- Não abre outro lote ao fechar — salvo sob `AUTO_STORY` (T032), em que uma única autorização
  humana cobre a Story inteira e o runtime deriva lotes filhos estritamente *patch-only* dentro
  daquele envelope. Mesmo aí ele nunca avança para a próxima Story do backlog, nunca fabrica
  assinatura para o lote filho e nunca ultrapassa o teto global de chamadas.

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

`permitted_effects` ganha as chaves opcionais `pull_request_merge` e `ci_rerun` (v0.17.0 / T028):
a flag `pull_request_merge` declara unicamente a **capacidade técnica** de merge, **não autorização** (`capability != authorization`). Mesmo com a flag ativa, o merge para a base protegida exige estritamente autorização out-of-band confirmada via `MergeAuthorityGate` (`scripts/tl_merge_guard.py`) e apresentação de `AuthorityReceipt`; sem essa autorização, a unidade estaciona em `awaiting_operator` (ou para em `human_merge_only`). Sem `ci_rerun`, nunca reexecuta CI. `local_merge` faz merge `--no-ff` na branch base quando não há
PR (também condicionado ao guard de autoridade quando a base é protegida). `continue_independent_after_block` decide se unidades independentes continuam depois
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
| `local_commit` | `T042:commit:<tree>` (sem `permitted_effects.local_commit`, trabalho aprovado vai para `awaiting_operator` com a árvore num ref, nunca para `completed`) |
| `push` | `T042:push:<commit>` |
| `pull_request` | `T042:pr` |
| `pull_request_merge` / `local_merge` | `T042:merge:<commit>` |
| `ci_query` | `T042:ci:<commit>:<ts>` (nunca reutilizado) |
| `ci_rerun` | `T042:ci_rerun:<commit>:1` (só com `permitted_effects.ci_rerun`) |

Retomar é dobrar o journal: resultado `ok` com o mesmo `input_digest` é reutilizado; step
sem resultado é reconciliado antes de qualquer escalonamento:

| Intenção aberta | Evidência consultada | Veredito |
| :--- | :--- | :--- |
| `model_call` | estado do `tl_job.py`; resultado `ok` já gravado para o mesmo step id é reutilizado mesmo que o pack recompilado tenha outro digest (a chamada já aconteceu e foi cobrada) | nunca iniciou → `released` (não cobrada) · ainda rodando → o runtime **anexa** ao supervisor e espera · terminou sem resultado gravado → `ambiguous`, cobrada; a árvore suja vira checkpoint (`refs/tl/checkpoints/...`) e o próximo Maker recebe "continue do checkpoint" |
| `local_commit` | árvore e pai de `HEAD` | árvore da intenção sobre o pai gravado → `ok` · `HEAD` avançou além do pai sem ser o commit esperado → `ambiguous`, `awaiting_operator` (nunca adota commit alheio) · senão → `released`. Com resultado já gravado, a entrega usa o commit do journal e exige que a branch ainda aponte para ele; "nada a commitar" nunca adota `HEAD` (`commit_ambiguous`) |
| `push` | `git push origin <commit revisado>:refs/heads/<branch>` (o refspec fixa o efeito no commit revisado; branch local apontando para outro commit → `awaiting_operator`, nada enviado) · `git ls-remote` contra o `remote_before` gravado na intenção (também quando o próprio `git push` devolve erro: remoto no commit → `ok`; remoto como antes → falha normal; outro estado → `awaiting_operator`, nunca retry) | remoto no commit esperado → `ok` · remoto exatamente como observado antes da intenção → `released` (push roda: o efeito de um push é visível na ref remota, então "estado igual ao anterior" é a única condição em que repetir produz exatamente o resultado autorizado, mesmo que uma automação tenha apagado a branch entre a queda e a retomada) · qualquer outro estado (movido, apagado quando antes existia, divergente, inacessível) → `ambiguous`, unidade em `awaiting_operator` |
| `pull_request` | `gh pr list --head` | existe `OPEN` com a mesma base e `headRefOid` exatamente igual ao commit revisado gravado na intenção → `ok` · existe `MERGED` com base e head exatos → `ok` e a unidade completa como mesclada · `CLOSED` → `ambiguous` · não existe → `released` (o create adota um PR existente da branch só com base e head exatos, nunca duplica) · base/head diferentes, head ausente ou `gh` falhou → `ambiguous`, `awaiting_operator` |
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
| Antes de descartar árvore | toda restauração (escopo, artefato de portão, Checker que escreveu, unidade parada) grava antes o estado atual em `refs/tl/discarded/<lote>/<n>` e anota no journal; `clean -fd` roda antes do `read-tree`, com as regras de ignore em vigor, para que um arquivo ignorado só pelas regras descartadas fique no disco | nada é apagado sem cópia (arquivos ignorados não entram na cópia, mas também nunca são apagados); limpar as refs é tarefa do operador |
| Antes de cada unidade | árvore suja antes do `prepare` para o lote (`unexpected_tree_state`), inclusive quando a branch da unidade já está em checkout: edição do operador nunca vira commit do runtime | sujeira produzida pelo próprio runtime (crash no meio do Maker) é reconhecida pelo journal e vira checkpoint |
| Depois de cada Maker (sob `AUTO_STORY`, `do_not_touch` inclui os `forbidden_paths` e `protected_paths` do filho vinculado) | `sensitive_paths` e varredura de padrões de segredo no diff **integral** e nos bytes de cada arquivo alterado (binário incluso; AWS, chaves privadas, GitHub, Anthropic/OpenAI, Slack, Google) têm precedência e param o lote; depois `dirty_paths ⊆ scope_paths` e `do_not_touch`, com os dois lados de um rename (`secrets/x -> pkg/x` é toque em `secrets/`); só o pack do Checker é limitado por `max_diff_bytes` | varredura por padrão, não prova de ausência de segredo |
| Em todo comando git do runtime | `core.hooksPath` aponta para um diretório vazio (git ≥ 2.31): hooks do repositório (`post-checkout`, `pre-push`, ...) não rodam dentro de checkout, commit, merge ou push do runtime; a verificação é dos portões | workers e portões não herdam essa variável e podem acionar hooks por conta própria |
| Antes de cada pack | todo pack passa por redação dos mesmos padrões de segredo (`[REDACTED:...]`), inclusive saída de portão e fatia de CI; o manifesto registra `redactions` | redação por padrão, não prova |
| Antes de cada commit | a árvore de trabalho tem de ser exatamente a árvore aprovada pelo Checker; edição feita durante uma parada vai para `refs/tl/...` e a unidade fica em `awaiting_operator` | — |
| Antes de cada efeito externo | `permitted_effects` do lote; merge remoto só com CI `success` quando CI está ativa e sempre com `--match-head-commit <commit revisado>`; merge local só se a branch ainda aponta para o commit revisado; merge para base protegida exige estritamente `AuthorityReceipt` emitido por `MergeAuthorityGate` (T028) | `gh` autenticado é do operador; o runtime não gerencia credenciais; autorização de merge é validada out-of-band |
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

## `AUTO_STORY`: uma autorização humana por Story (T032)

`AUTO_STORY` é **estritamente opt-in**. Um lote sem `authorization.story_authority_mode`
continua sendo `direct_proposal`: a semântica de lote único, um digest de proposta por
autorização humana, exatamente como antes. Nada em histórico precisa migrar.

Sob `AUTO_STORY`, uma única decisão humana cobre a Story inteira, com teto global estrito de
chamadas e escopo monotonicamente decrescente. O runtime deriva e abre sozinho os lotes filhos
necessários para resolver apontamentos residuais do Checker — e só esses.

### Autoridade imutável e consumo mutável

Os dois nunca se misturam.

| | Caminho | Natureza |
| :--- | :--- | :--- |
| Autoridade | `_tl-orc/project/story-authorities/<authority_id>.json` | Imutável. Nunca reescrita para registrar saldo. |
| Consumo | `_tl-orc/runtime/story-authorities/<authority_id>/` | `journal.jsonl` (append-only, write-ahead, fsync, hash-chain, escritor único sob `lease.lock`) e `status.json`, que é só projeção. |

O envelope tem três partes, e a separação existe para quebrar a circularidade:

```json
{
  "authority_payload": { "…exatamente os 12 campos submetidos ao humano…" },
  "root_authority_digest": "sha256 do canonical_json(authority_payload)",
  "operator_authorization": { "authority_source": "…", "authorized_at": "…", "authorized_literal": "…" }
}
```

`root_authority_digest = SHA256(canonical_json(authority_payload))`. `canonical_json` é
UTF-8, chaves ordenadas lexicograficamente, separadores compactos (`,`, `:`), zero whitespace
incidental, ordem de array preservada e nenhum float. O payload contém **apenas**
`authority_id`, `work_ref`, `authorized_spec_revision`, `authorized_spec_sha256`,
`authorized_write_scope`, `allowed_effects`, `protected_paths`, `global_model_call_budget`,
`max_child_batches`, `max_consecutive_failed_batches`, `wall_clock_deadline` e `hard_stops`.
O próprio digest, `authorized_at`, `authorized_literal` e qualquer metadado produzido depois
da decisão humana ficam fora: incluí-los faria o digest depender de valores que só existem
porque o digest já havia sido calculado.

O fluxo de autorização é: o runtime formula o payload em modo somente-leitura, calcula o
digest, apresenta ambos ao operador e espera **uma** autorização explícita, exatamente neste
formato:

```text
AUTORIZO STORY <work_ref> sha256:<root_authority_digest>
```

Qualquer coisa diferente — prefixo, caixa, digest truncado, outra Story — é recusada. A frase
é julgada **byte a byte, exatamente como foi capturada**: nada é aparado, dobrado ou coagido
antes. Espaço, tab ou quebra de linha no início, no fim ou no lugar dos dois espaços internos,
BOM, espaço não separável e qualquer valor que não seja string são outra elocução, não uma
quase-autorização, e o envelope persiste o literal como foi emitido. A mesma comparação exata
roda de novo ao carregar o envelope. Só
depois disso o envelope é congelado e a derivação de lotes filhos é liberada. Ao carregar,
o digest é recalculado e comparado byte a byte; divergência é `HARD STOP` por
`state_integrity`. Conceitualmente isto é *digest-bound explicit operator authorization*, não
assinatura: não há chave assimétrica envolvida.

```
python scripts/tl_story_authority.py present --payload payload.json
python scripts/tl_story_authority.py freeze  --payload payload.json --authorization "AUTORIZO STORY connector:2-10 sha256:…" --source operator-terminal --repo .
python scripts/tl_story_authority.py status  --authority-id A001 --repo .
```

### Orçamento global sem double-spend

O journal da autoridade é a **única** fonte de verdade do orçamento. O ledger do lote filho é
projeção dele, nunca uma segunda contabilidade. Eventos mínimos: `authority_open`,
`model_call_reserved`, `model_call_consumed`, `model_call_released`, `child_derived`,
`child_open`, `child_closed`, `child_failed`, `hard_stop`, `authority_closed`.

Antes de qualquer reserva ou abertura de filho: adquirir o lease exclusivo, reconstruir o
consumo pelo replay do journal, validar `remaining_global_budget >= requested_calls`,
persistir a reserva write-ahead com fsync e só então executar o efeito. Em v1,
`max_active_child_batches = 1`.

Chamadas são identificadas em dois níveis:

- `logical_call_id` — a operação cognitiva abstrata (`B014-checker-review-r01`).
- `global_attempt_id` — cada tentativa física que **pode** ter alcançado o provider
  (`A001-attempt-004`). Um retry sempre gera um id novo; duas tentativas físicas consomem dois
  slots. Estados: `reserved`, `consumed`, `released` (comprovadamente pré-despacho) e
  `ambiguous` (resultado incerto, contado conservadoramente como consumido). Reprocessar o
  mesmo `global_attempt_id` após um crash não repete a chamada física nem o débito.

`tl_job.budgeted_model_dispatch` aceita `authority_context`: a reserva global é escrita antes
da local e liquidada antes dela, de modo que o ledger do filho só pode ser projeção de um
débito que já existe globalmente. Na retomada, `reconcile_orphan_reservations` liquida
conservadoramente o que ficou aberto e o ledger do filho é reconstruído a partir do journal da
autoridade — nunca o inverso.

### Bloqueio mecânico de chamadas fora do ledger

Além da obrigação de passar pelo despacho orçado, o ambiente do worker recebe um *cognitive
call barrier*: um diretório à frente do `PATH` com shims determinísticos para `agy`, `codex`,
`claude` e `gemini`. Uma invocação direta falha com código 97 antes de tocar a rede. O runtime
instala e **prova** a barreira no ambiente real do worker; se o sistema não suportar o
isolamento, a capability fica `unavailable` e a inicialização de `AUTO_STORY` é recusada. Não
há modo degradado.

Limitação declarada, não contornada: a barreira sombreia a resolução por **nome**. Um worker
que já conheça o caminho absoluto de uma CLI real ainda consegue executá-la — por isso o
despacho orçado continua sendo a obrigação primária do plano de controle, e a barreira é a
segunda linha, não a única.

### Derivação estritamente patch-only

Um lote filho só é derivado automaticamente se **todos** os apontamentos residuais do Checker
forem `target_role = maker`, `category = patch`, `scope_status = inside_parent_envelope` e
`spec_status = unchanged`. Os dois últimos são recalculados mecanicamente contra o envelope; a
declaração do Checker (`scope_status`, `spec_status`, `derivation_blockers` em
`review-result.schema.json`) é necessária mas nunca suficiente, e divergência entre o
declarado e o provado é `HARD STOP`.

Qualquer `bad_spec`, `intent_gap`, `human`, `security`, `scope_expansion`, `new_boundary`,
`migration`, `capability_expansion` ou dúvida de intenção devolve o controle ao operador. A
heurística genérica "lote não aprovado ⟹ criar próximo lote" é proibida: uma lista vazia de
apontamentos também não deriva nada.

A autoridade do filho é puramente derivada, provada pela cadeia
`root_authority_digest` + `parent_authority_digest` + `parent_batch_digest` +
`child_proposal_digest` + `derivation_proof_digest`. `verify_derivation()` prova, entre
outras coisas:

- `child.required ∪ child.conditional ⊆ parent.authorized_write_scope` — é a **união** que
  precisa estar contida. Um path autorizado como condicional no pai pode legitimamente virar
  obrigatório no filho depois de um apontamento factual do Checker.
- `child.forbidden_paths ⊇ parent.forbidden_paths` e `child.protected_paths ⊇
  parent.protected_paths`, este com igualdade estrutural dos itens herdados (padrão, policy e
  parâmetros de hash/snapshot).
- Nenhum efeito além dos autorizados, spec congelada, orçamento dentro do saldo restante,
  `max_child_batches`, `max_consecutive_failed_batches` e `wall_clock_deadline`.
- Linhagem decidida pela ordem do journal: só o **primeiro** filho de uma Story pode declarar
  `parent_child_batch_id: null`; todo filho posterior declara um pai que foi derivado sob esta
  autoridade, está **fechado** (`child_closed`), é o último filho que um Checker revisou e fechou
  `changes_requested`. Pai inexistente, pai apenas `derived`/`open`/`failed`, pai `approved` e
  "segundo filho que se apresenta como primeiro" são `HARD STOP`. Um filho com pai não é
  verificável sem os apontamentos residuais de que deriva.
- `unresolved_action_items_digest` cobre também o que o Checker declarou sobre derivabilidade
  (`scope_status`, `spec_status`, `derivation_blockers`): um apontamento do qual se removeu um
  bloqueio é outro apontamento, e a proposta do filho não tem campo para bloqueio — logo um
  apontamento bloqueado nunca digere como um derivável.

### Registro da derivação e vínculo do lote executável

Os digests que um lote declara em `authorization` são **alegações**. A fonte de verdade é o
evento `child_derived` do journal da autoridade, que carrega, num único append atômico, a
`child_proposal` e a `derivation_proof` inteiras além dos seus digests.

- `record_child_derived()` não journala nada por confiança: recalcula os digests dos dois
  documentos, exige que a prova seja a desta proposta, desta autoridade e da cadeia que o journal
  registra, re-prova o envelope e a linhagem, e recusa registrar de novo, de forma diferente, um
  filho já registrado (registro idêntico é replay idempotente e não acrescenta evento). No replay
  do journal a primeira derivação de um filho é a registrada; uma segunda, divergente, escrita
  por fora desse portão impede o ledger de abrir (`state_integrity`).
- Antes de **qualquer** worker, sob o lease da autoridade, o runtime chama
  `bind_child_batch()`: recupera a proposta e a prova registradas para exatamente `batch.id`,
  recalcula ambos os digests, exige igualdade com os do evento e com os declarados pelo lote,
  re-prova envelope, linhagem, cadeia e — para filho com pai — a elegibilidade patch-only contra
  o caminho real da spec da unidade, e então prova que o lote não pede nada além do filho:
  `work_ref` dentro da Story, spec de cada unidade igual a `authorized_spec_sha256`,
  `scope_paths ⊆ required ∪ conditional` e fora de `forbidden_paths`/`protected_paths`,
  `permitted_effects` dentro de `allowed_effects` (`pull_request_merge` ↔ `merge`; efeito sem
  correspondente no envelope, como `ci_rerun`, não foi autorizado) e
  `budget.max_model_calls ≤ model_call_budget`. O `functional_parent_checkpoint` usado pelo
  runtime é o da proposta verificada. Qualquer falha é `HARD STOP` journalado e recusa de
  iniciar, sem batch journal aberto, sem reserva de chamada e com os dois leases liberados.
- `verify_derivation`, `record_child_derived` e `bind_child_batch` executam os **mesmos**
  geradores de prova (`envelope_checks`, `lineage_checks`, `derivation_chain`,
  `patch_only_check`); não existe uma segunda implementação no runtime que possa divergir.
  Ficam só em `verify_derivation` as checagens que dependem do instante (saldo restante, filho
  ativo, deadline, sequência de falhas), que o ledger volta a impor a cada reserva.
- **Forbidden aninhado em escopo amplo continua proibido.** Um alvo dentro de um path proibido
  é recusado na derivação; o inverso — `forbidden_paths: [pkg/blocked.txt, pkg/vault/]` sob
  `scope_paths: [pkg/]` — é legítimo e vira política executável: o vínculo entrega
  `forbidden_paths` e os padrões de `protected_paths` do filho como `do_not_touch` de cada
  unidade, de modo que aparecem no Context Pack **antes** do Maker e a contenção pós-Maker
  recusa a rodada e restaura a árvore para qualquer dirty path coberto (criação, alteração,
  deleção e os dois lados de um rename). A proibição da Story é julgada pelo **mesmo matcher
  que provou a derivação** (`paths_denied`), não pelo `path_within` legado, de modo que um path
  de topo iniciado por ponto (`.github/workflows`, `.env`) é contido mesmo sob
  `scope_paths: [.]`. Nada proibido chega a commit, a checkpoint funcional ou a `main`; a árvore
  descartada fica, como em toda violação de escopo, apenas no ref local `refs/tl/discarded/...`. Limite herdado da contenção: ela enxerga o que `git status` enxerga, portanto um
  arquivo ignorado pelo `.gitignore` não é visto (e tampouco é commitado).

### Linhagem funcional entre lotes filhos

`AUTO_STORY` separa *governance base*, *functional checkpoint* e *integration candidate*.

```text
main / governance base
        |
        | B013 trabalha isolado
        v
B013 checker_reviewed_commit
        |
        | changes_requested / rework_limit_exhausted — NÃO MERGE
        v
functional checkpoint preservado
        |
        | derived child
        v
B014 parte EXATAMENTE desse checkpoint
        |
        | patch residual
        v
integration_candidate_commit
        |
        | Checker final approved (revisa story_baseline..integration_candidate)
        v
merge em main (sob T028)
```

Um filho que termina `changes_requested` nunca chega ao `deliver`, portanto não tem commit de
entrega. O runtime materializa a árvore exata que o Checker revisou como commit em
`refs/tl/functional-checkpoints/<batch>/<unit>` e registra no evento `child_closed`:
`child_batch_id`, `governance_base_commit`, `checker_reviewed_commit`, `checker_reviewed_tree`,
`functional_checkpoint_commit`, `functional_checkpoint_tree`, `checker_verdict` e
`unresolved_action_items_digest`. Esse commit **não** é mesclado em `main` só para transportar
estado — isso é terminantemente proibido.

O filho seguinte nasce com `functional_parent_checkpoint = previous_child.checker_reviewed_commit`
e, antes de qualquer intervenção do Maker, prova deterministicamente: o commit existe
(`git cat-file -e`), `HEAD` é exatamente ele, a árvore bate com a registrada e a working tree
está limpa. Ausência, adulteração ou ambiguidade é `HARD STOP` por `state_integrity` /
`unexpected_tree_state`, e o filho anterior permanece imutável como evidência histórica.

O Checker do filho seguinte revisa o candidato **cumulativo**
(`story_baseline_commit..integration_candidate_commit`), não apenas o patch do filho corrente.
Assim a entrega final sempre tem `checker_reviewed_commit == integration_candidate_commit` e
esse commit carrega toda a linhagem funcional.

### Subordinação ao T028

`allowed_effects.merge = true` é uma *flag de capacidade técnica*, nunca um bypass. Operações
em branches protegidas continuam exigindo o `MergeAuthorityGate`, o `AuthorityReceipt`
autêntico e a autoridade out-of-band do T028. `AUTO_STORY` encerra compulsoriamente quando a
Story autorizada atinge `CLOSE`/`done`; avançar para a próxima Story do backlog exige nova
autorização humana e falha com `next_story_without_authorization`.

## Validador de plano de execução e protected paths (T033)

`scripts/validate_execution_plan.py` valida o plano de execução de uma proposta contra um
registro **fechado** de asserções. Cada `assertion_id` declara em quais fases do ciclo de vida
sua resposta é decidível:

| `lifecycle_phase` | asserções |
| :--- | :--- |
| `pre_execution` | `working_tree_clean`, `functional_checkpoint_matches`, `spec_digest_unchanged`, `protected_paths_intact`, `budget_not_exhausted` |
| `post_maker_pre_review` | `spec_digest_unchanged`, `protected_paths_intact`, `budget_not_exhausted` |
| `post_checker_pre_merge` | `checker_approved`, `main_not_merged`, `spec_digest_unchanged`, `protected_paths_intact`, `budget_not_exhausted` |
| `post_merge_pre_close` | `merge_commit_exists`, `canonical_gate_passed`, `working_tree_clean`, `spec_digest_unchanged`, `protected_paths_intact` |
| `post_terminal` | `origin_synced`, `merge_commit_exists`, `canonical_gate_passed`, `working_tree_clean`, `spec_digest_unchanged`, `protected_paths_intact` |

O plano referencia unicamente `assertion_id` e parâmetros tipados; `execution-plan.schema.json`
torna estruturalmente impossível uma string de asserção livre. Asserção desconhecida ⟹ **FAIL
CLOSED**; asserção numa fase incompatível ⟹ **FAIL CLOSED**. O validador também prova
`gate_call_constraints_are_satisfiable_under_budget` contra os cenários obrigatórios
`straight_line` e `retry`. Os nomes têm significado: `straight_line` tem exatamente
`rework_rounds = 0` e `retry` tem `rework_rounds >= 1` — um `retry` com zero rodadas só provaria
o caminho feliz duas vezes (`retry_scenario_without_rework`,
`straight_line_scenario_has_rework`). Cada nome de cenário é declarado uma única vez
(`duplicate_budget_scenario`), uma rodada precisa custar ao menos uma chamada
(`round_without_model_calls`) e todo cenário declarado tem de caber no teto
(`gate_call_constraints_unsatisfiable`). O validador de schema aplica `pattern` com a semântica
ECMA-262 do JSON Schema: `$` é fim da entrada, então um valor seguido de quebra de linha não casa
`^...$`.

Protected paths são de primeira classe, em três modos:

- `read_only` — qualquer mutação sob o padrão é violação; sem baseline e sem git a resposta é
  `protected_read_only_unverifiable`, nunca um passe silencioso.
- `exact_file_hash` — o arquivo precisa existir como arquivo regular com exatamente aquele
  SHA-256; symlink ou ausência falha antes de qualquer comparação de hash.
- `exact_set_snapshot` — compara recursivamente `path`, `type` (file vs. symlink), `size` e
  `sha256`. Adição de arquivo untracked, deleção, alteração de bytes ou conversão de arquivo em
  symlink falham imediatamente.

A monotonicidade é semântica, não textual: para todo padrão herdado o filho preserva a mesma
policy e os mesmos parâmetros (hash esperado, snapshot de referência). Pode acrescentar
proteção; nunca remover padrão, reduzir cobertura, trocar por policy mais permissiva ou
substituir o hash/snapshot herdado.

O validador de schema embutido é um subconjunto estrito de Draft 2020-12 em biblioteca padrão
que **recusa** qualquer keyword que não implemente, em vez de ignorá-la — é assim que
validadores parciais deixam de aplicar silenciosamente a restrição que o autor achava ter
escrito.

```
python scripts/validate_execution_plan.py --plan plan.json --repo . --verify-protected-paths
python scripts/validate_execution_plan.py --print-registry
```

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

`AUTO_STORY` e o validador de plano têm suítes próprias em `tests/`:
`test_auto_story_replay.py` (replay canônico B013→B014 do canário Lynvia, com repositório Git
real e recibo T028 assinado), `test_auto_story_runtime_integration.py` (contraprova da barreira
cognitiva dentro do runtime real, teto global vencendo o ledger do filho, checkpoint funcional
materializado, vínculo do lote à derivação registrada — lote não derivado, digest adulterado,
journal editado, lote maior que o filho e segundo filho forjado como primeiro recusados antes de
qualquer worker —, forbidden aninhado em escopo amplo contido e restaurado, filho derivado
executado ponta a ponta a partir do checkpoint e retrocompatibilidade do lote legado),
`test_story_authority_digest.py`, `test_story_child_derivation.py`,
`test_story_derivation_binding.py`, `test_story_functional_lineage.py`,
`test_story_global_accounting.py`, `test_story_protected_paths.py`,
`test_story_operational_limits.py`, `test_story_cognitive_barrier.py` e
`test_execution_plan_validator.py`.

## Limites conhecidos

- Filtros `clean`/`smudge` (git-lfs, por exemplo) são definidos no git config do operador e
  rodam dentro dos comandos git do runtime (`add`, `read-tree`); não há chave do git que os
  desligue sem quebrar o consumidor que depende deles. São código do operador, como
  `notify_argv`; hooks, ao contrário, são desligados.
- `gh pr merge` só aceita precondição de head (`--match-head-commit`), não de base, e devolve
  sucesso ao enfileirar num merge queue. O runtime revalida base, head e estado `OPEN`
  imediatamente antes e só conta como mesclado o estado terminal `MERGED` com a mesma base e
  o mesmo head logo depois: PR ainda aberto vira `merge_queued` (step `ambiguous`,
  `awaiting_operator`; o retry adota o merge feito pela fila sem nova chamada) e base ou
  head diferentes viram `merged_into_unexpected_base` / `merged_unexpected_head`, não um
  merge silencioso. Na v2 (T028), o `MergeAuthorityGate` fecha a janela de base drift invalidando
  o envelope se o base SHA divergir de `expected_base_sha`, e a proteção no GitHub exige Ruleset
  com branch estritamente atualizada e status check `Merge Authority` emitido pela Dedicated GitHub App.

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
