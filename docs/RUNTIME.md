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
`dependencies` dentro do próprio lote. `immutable_digest`, quando presente, tem de ser o
SHA-256 do JSON canônico de `frozen_scope` sem essa chave (`validate` imprime o valor
esperado). As seções mutáveis `budget` e `execution` são **projeção**: o runtime as
reescreve a partir do journal para que leitores do Modo Automático vejam consumo, chamada
pendente e unidade corrente; as seções congeladas nunca são tocadas.

`permitted_effects` ganha a chave opcional `pull_request_merge` (v0.17.0): sem ela, o
runtime abre o PR e para ali. `local_merge` faz merge `--no-ff` na branch base quando não há
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
`{effort}`, `{tools}`, `{role}`. As capacidades são declaradas pelo consumidor, não
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

Retomar é dobrar o journal: resultado `ok` com o mesmo `input_digest` é reutilizado; step
sem resultado é reconciliado antes de qualquer escalonamento:

| Intenção aberta | Evidência consultada | Veredito |
| :--- | :--- | :--- |
| `model_call` | estado do `tl_job.py` | nunca iniciou → `released` (não cobrada) · ainda rodando → o runtime **anexa** ao supervisor e espera · terminou sem resultado gravado → `ambiguous`, cobrada; a árvore suja vira checkpoint (`refs/tl/checkpoints/...`) e o próximo Maker recebe "continue do checkpoint" |
| `local_commit` | árvore de `HEAD` | igual à árvore da intenção → `ok` · senão → `released` |
| `push` | `git ls-remote` | remoto no commit esperado → `ok` · ausente ou atrás → `released` (push roda) · divergente ou inacessível → `ambiguous`, unidade em `awaiting_operator` |
| `pull_request` | `gh pr list --head` | existe → `ok` · não existe → `released` · `gh` falhou → `ambiguous` |
| `pull_request_merge` | `gh pr view` | mesclado → `ok` · aberto → `released` · `gh` falhou → `ambiguous`, `awaiting_operator` |
| `local_merge` | `merge-base --is-ancestor` | já mesclado → `ok` · senão → `released` |
| `gate`, `ci_query`, `prepare` | nenhuma | `released` (rodam de novo) |

Cada intenção carrega `runtime_stamp` (`<versão>:<digest da config>`). Uma intenção aberta
gravada por outra versão para o lote com `stale_workflow_version`; depois de inspecionar,
`run --accept-stale-version` registra a aceitação e continua. Linha inválida no journal é
recusa (exit 2), nunca ignorada em silêncio.

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
| Spawn do worker | `tl_job.py` (contenção da árvore de processos, timeout, recibo limitado) com ambiente filtrado: só a allowlist base mais `env_allowlist`; `DO_NOT_TRACK=1` | ferramentas e sandbox de rede dependem do harness: use `{tools}` e sandbox nativos quando existirem; sem eles, o adapter declara `false` e o relatório avisa |
| Depois de cada Maker | `dirty_paths ⊆ scope_paths`, `do_not_touch`, `sensitive_paths`, varredura de padrões de segredo no diff (AWS, chaves privadas, GitHub, Anthropic/OpenAI, Slack, Google) | varredura por padrão, não prova de ausência de segredo |
| Antes de cada efeito externo | `permitted_effects` do lote; merge remoto só com CI `success` quando CI está ativa | `gh` autenticado é do operador; o runtime não gerencia credenciais |
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
`flaky_reruns` reexecuções; o resto é `parked`. O fatiador nunca chama um vermelho de flaky.

## Saídas para o operador

- `status.json`: lote, progresso, unidade/fase/rodada corrente, bloqueados, esperando,
  orçamento, próxima unidade.
- `report.md`: relatório da manhã, 100% derivado do journal e do Git: Completed, Changed,
  Commits / PRs, Verification, Automatically Resolved, FYI, REVIEW, DECISION REQUIRED,
  BLOCKED, Cost / Usage, Models, Recovery Events, What Happens Next.
- `journal`: dobra diagnóstica (tentativas, assinaturas, recuperações, checkpoints, uso).
- `notify_argv`: comando opcional chamado com um JSON em cada mudança de estado relevante.

`decide --option retry` devolve a unidade a `retryable` (o trabalho parado está no
checkpoint); `skip` marca `failed`. Um lote já fechado não reabre: nova autorização.

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

- Concorrência 1. Worktrees em paralelo dependem do pool/árbitro do `tl_supervisor.py` e de
  medição; não entram nesta versão.
- Planner e Advisor não são despachados pelo runtime: a unidade precisa entrar com spec
  ratificada. Proposta e ratificação continuam na sessão do Orquestrador.
- Nenhum cálculo de custo estimado: sem uso observado, `unknown`.
- Sandbox de rede só onde o harness a oferece.
- A classificação de falha é por padrão; `unknown` leva a `parked`, não a tentativa cega.
- O journal e o lote não são protegidos por sistema de arquivos contra um worker com escrita
  irrestrita (por exemplo, `claude` sem sandbox). O runtime detecta árvore alterada pelo
  Checker, mas não adulteração do journal; mantenha `--state-dir` fora do repositório, use a
  allowlist de ferramentas do harness e um sandbox quando ele existir.
