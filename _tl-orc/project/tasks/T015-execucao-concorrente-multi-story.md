id: T015
type: feat
deliverable: package
standalone: true
method: native
status: done
state_revision: 1
depends_on: [T014]
blocked_by: []
origin: user (2026-09-13): pedido para suceder o pipelining assíncrono de pista única de T014 por execução concorrente de fato — N stories independentes do DAG rodando ao mesmo tempo em worktrees isolados, sem colisão de escopo entre sessões e sem duas sessões abrindo merge simultâneo na mesma branch alvo.
decisions: []
spec_author: planner
spec_revision: 1
rework_round: 0
affects_context: []
content_paths: [scripts/tl_supervisor.py, scripts/tl_run_story.py, tests/test_tl_supervisor.py, docs/EXECUTION_PROTOCOL.md, prompts/orchestrator-playbook.md, CHANGELOG.md, _tl-orc/project/STATUS.md]
content_id: auto
worktree: branch feat/multi-story-supervisor

## Status
`ready-for-dev` — aguardando ratificação do Checker antes de qualquer despacho ao Maker. Depende de `T014` (`done`), que entregou heartbeat e fencing de leases para uma única pista sequencial; esta story não pode iniciar decisão de merge concorrente sem essa base de recuperação atômica já disponível.

## Intent
T014 entregou pipelining assíncrono de **uma pista sequencial**: a Story N+1 só é despachada depois que a Story N publica seu PR, e apenas uma lease de execução existe por vez. Isso ainda serializa o trabalho real de codificação quando duas ou mais stories do DAG são mutuamente independentes. Esta story formaliza o `tl-supervisor`: um **Worktree Pool** com vagas concedidas atomicamente, um **Scope Arbiter** que recusa duas stories concorrentes reivindicando `content_paths` sobrepostos, e uma **Merge Queue Serializada** que garante um único `gh pr merge` em voo por vez na branch alvo mesmo com N sessões terminando na mesma janela de tempo. O valor entregue é paralelismo real de codificação sem introduzir corrupção de board, worktrees órfãos ou merges concorrentes na mesma branch.

### Finding
source: observação direta do gargalo remanescente de T014 e revisão cruzada com o protocolo de heartbeat/fencing já existente em `docs/EXECUTION_PROTOCOL.md`.
observed: mesmo após T014, o condutor mantém uma única lease de execução ativa por vez; duas stories sem dependência mútua no DAG (`depends_on` disjuntos) ainda esperam uma pela outra porque não existe mecanismo formal de (a) conceder mais de um worktree simultâneo, (b) impedir que duas sessões reivindiquem o mesmo arquivo de `content_paths`, e (c) serializar merges quando múltiplas sessões terminam próximas no tempo.
expected: o protocolo e o `tl-supervisor` devem formalizar um pool de worktrees com N vagas configuráveis, arbitragem de escopo por `content_paths` antes de qualquer abertura de worktree, uma fila de merge FIFO persistida em disco, e varredura de worktrees órfãos reaproveitando o heartbeat de T014.
impact: redução adicional do tempo de ciclo quando o DAG tem paralelismo real disponível, sem reintroduzir os riscos que T014 já eliminou (locks órfãos, board corrompido, merges concorrentes destrutivos).

### Pre-Mortem & Riscos Críticos
Exercício obrigatório: esta story foi implementada, passou nos testes superficiais e quebrou feio em produção depois de 48 horas rodando à noite sem supervisão. Os motivos mitigados nesta spec:
1. **Concorrência/TOCTOU no Scope Arbiter:** duas sessões chamam `claim_scope` no mesmo instante para `content_paths` sobrepostos; se a checagem de colisão e a gravação da reivindicação não forem uma única operação atômica, ambas passam pela checagem antes de qualquer uma gravar, e as duas stories escrevem no mesmo arquivo em worktrees diferentes. Mitigado pela Tarefa 2 (gravação atômica via `os.replace` antes de liberar o worktree).
2. **Contenção no pool de worktrees:** N sessões pedem vaga ao mesmo tempo quando `max_slots` está no limite; sem um teste de concorrência real (threads/subprocessos), uma condição de corrida pode conceder N+1 vagas. Mitigado pela Tarefa 1 e pelo teste de contenção da Tarefa 1.
3. **Corrupção do board (`_tl-orc/project/STATUS.md`):** duas sessões terminam stories diferentes e escrevem na tabela `## Tasks` no mesmo instante; uma reescrita ingênua do arquivo inteiro por uma sessão descarta a escrita da outra. Mitigado pela Tarefa 5 (checagem de `state_revision` antes de cada escrita, recusa fail-closed em divergência).
4. **Vazamento de tokens/orçamento:** se o Scope Arbiter falhar aberto (fail-open) em vez de fail-closed, duas sessões podem rodar Maker+Checker completos sobre o mesmo escopo em paralelo, duplicando custo de chamadas pagas sem que nenhuma das duas produza um resultado aproveitável. Mitigado pela restrição fail-closed explícita em Boundaries & Constraints e pelo teste de colisão da Tarefa 2.
5. **Worktrees órfãos:** um processo cai (crash, kill, queda de energia) com um worktree aberto e uma vaga do pool nunca é liberada, esgotando o pool permanentemente. Mitigado pela Tarefa 4, que reaproveita o heartbeat de lease de T014 (`docs/EXECUTION_PROTOCOL.md:446`) para identificar e varrer worktrees cuja lease expirou.
6. **Merge concorrente na mesma branch:** dois PRs de stories diferentes completam gates ao mesmo tempo e ambos chamam `gh pr merge --auto` sem coordenação, arriscando um merge sobre uma base desatualizada. Mitigado pela Tarefa 3 (fila FIFO persistida; o segundo merge só é despachado após o primeiro ser confirmado `merged` ou `failed`).

## Boundaries & Constraints
**Arquivos permitidos para escrita:**
- `scripts/tl_supervisor.py` (novo módulo: Worktree Pool, Scope Arbiter, Merge Queue, varredura de órfãos)
- `scripts/tl_run_story.py` (novo módulo: ponto de entrada que despacha uma story através do `tl_supervisor`)
- `tests/test_tl_supervisor.py` (novo)
- `docs/EXECUTION_PROTOCOL.md` (nova seção formalizando os três mecanismos)
- `prompts/orchestrator-playbook.md` (instrução de quando despachar stories concorrentes vs. serializar)
- `CHANGELOG.md` (entrada da release `0.11.0`)
- `_tl-orc/project/STATUS.md` (registro de T015 e, se aplicável, contadores)

**Arquivos expressamente proibidos:**
- `scripts/tl_job.py` — não deve ser modificado; `tl_supervisor.py` importa e reutiliza suas primitivas de `Containment`/`Lease`/`lock_exclusive`, nunca duplica ou reescreve essa lógica.
- `scripts/validate_repository.py`, `distribution-manifest.json` — fora do escopo desta story.
- `prompts/planner.md`, `prompts/maker.md`, `prompts/checker-report-only.md`, `SKILL.md`, `README.md` — nenhum contrato de papel muda nesta story.
- qualquer conteúdo dentro de `worktrees/*` criado dinamicamente em runtime — é artefato gerado, nunca versionado.

**Restrições técnicas:**
- Python stdlib puro, sem novas dependências externas, seguindo o padrão de `scripts/tl_job.py:1-24` (apenas `argparse`, `contextlib`, `hashlib`, `json`, `os`, `subprocess`, `time`, `pathlib`, etc.).
- Toda concessão de vaga de worktree, reivindicação de escopo e avanço de fila de merge é publicada por rename atômico (`os.replace`); nenhuma operação lê-então-escreve sem revalidar o estado atual imediatamente antes de gravar.
- O Scope Arbiter é fail-closed: qualquer condição não coberta explicitamente por um teste (arquivo ilegível, `content_paths` malformado, falha ao gravar a reivindicação) resulta em recusa da story, nunca em liberação otimista do worktree.
- A Merge Queue nunca despacha o item seguinte antes do item anterior estar marcado `merged` ou `failed` no arquivo de fila; um `failed` sem marcação explícita nunca é tratado como `merged` implícito.

## Code Map
- `../../../scripts/tl_job.py:156` — `LEASE_NAME = "supervisor.lock"`: convenção de nome de lease que o `tl-supervisor` deve seguir para as leases de worktree/vaga do pool, mantendo o mesmo identificador dispositivo/inode usado pelo heartbeat de T014.
- `../../../scripts/tl_job.py:1240` — `lock_exclusive(handle)`: primitiva de lock exclusivo entre plataformas (`fcntl`/`msvcrt`) a ser reutilizada (via import, não cópia) pelo Worktree Pool e pela Merge Queue para serializar concessão de vagas e avanço de fila.
- `../../../scripts/tl_job.py:1262` — `class Lease`: modelo de lease com handle aberto cujo lock o sistema operacional libera ao encerrar o processo; o `tl-supervisor` referencia este contrato para a lease de cada worktree concedido.
- `../../../docs/EXECUTION_PROTOCOL.md:443` — parágrafo do "Desacoplamento do CI Remoto" de T014 que hoje despacha apenas a Story N+1 em worktree isolado; esta story generaliza esse parágrafo para N stories concorrentes via Worktree Pool.
- `../../../docs/EXECUTION_PROTOCOL.md:446` — `{pid, start_time, heartbeat_ts}` e recuperação atômica de lease expirada: mecanismo de heartbeat que a Tarefa 4 (varredura de órfãos) reaproveita para identificar worktrees abandonados.
- `../../../docs/EXECUTION_PROTOCOL.md:453` — cache de gates por `tree_sha`: mecanismo existente que a documentação desta story referencia para deixar explícito que o cache permanece por worktree, nunca compartilhado entre stories concorrentes com árvores diferentes.
- `../../../prompts/orchestrator-playbook.md:167` — instrução atual de registrar PR, liberar lock e avançar para a próxima story da fila; esta story estende essa instrução para decidir entre "avançar sequencialmente" e "despachar concorrentemente" conforme independência no DAG.
- `../../../prompts/orchestrator-playbook.md:170` — "inicie imediatamente a próxima story independente da fila em um Git worktree isolado": ponto exato onde a instrução de pista única deve passar a consultar o Worktree Pool/Scope Arbiter em vez de assumir uma única pista.
- `../STATUS.md:13` — `next_task_id: 15`: confirma que esta story ocupa o próximo id livre do board.
- `../STATUS.md:19` — cabeçalho `## Tasks` da tabela do board: local exato onde a Tarefa 5 (escrita atômica por `state_revision`) se aplica a cada linha adicionada ou atualizada por sessões concorrentes.

## Tasks & Acceptance

**1. Worktree Pool com vagas concedidas atomicamente**
- [ ] `scripts/tl_supervisor.py` expõe `acquire_worktree_slot(pool_dir, story_id, max_slots)` que executa `git worktree add worktrees/<story-id>` somente se o número de vagas ativas em `pool_dir` for menor que `max_slots`; caso contrário retorna `{"state": "pool_exhausted"}` sem criar worktree e sem efeito colateral.
- [ ] A concessão é publicada em `slot.json` por `os.replace` (rename atômico); nenhuma vaga é considerada concedida antes desse rename ter sucesso.
- [ ] Teste em `tests/test_tl_supervisor.py` cobre: `max_slots=1`, duas chamadas concorrentes (via `threading.Thread`) a `acquire_worktree_slot` para stories diferentes — exatamente uma retorna sucesso e a outra retorna `pool_exhausted`.

**2. Scope Arbiter (prevenção de colisão de `content_paths`)**
- [ ] `scripts/tl_supervisor.py` expõe `claim_scope(story_id, paths, claims_file)` que recusa com `{"state": "scope_conflict", "conflicting_with": <story-id existente>}` quando qualquer item de `paths` for igual a, prefixo de, ou tiver como prefixo um path já presente em `claims_file`.
- [ ] A reivindicação aceita é gravada em `claims_file` por `os.replace` antes de qualquer worktree ser aberto para a story; a checagem de colisão e a gravação ocorrem sob o mesmo lock exclusivo (via `lock_exclusive` de `scripts/tl_job.py:1240`), nunca como duas operações separadas.
- [ ] Teste cobre: duas stories com `content_paths` idênticos (`["docs/EXECUTION_PROTOCOL.md"]`) — a segunda reivindicação retorna `scope_conflict`.
- [ ] Teste cobre: duas stories com `content_paths` disjuntos (`["scripts/tl_supervisor.py"]` vs `["docs/EXECUTION_PROTOCOL.md"]`) — ambas as reivindicações retornam sucesso.
- [ ] Teste cobre: chamada concorrente de `claim_scope` (via `threading.Thread`) para o mesmo path por duas stories — exatamente uma vence, a outra recebe `scope_conflict`, nunca ambas vencem.

**3. Merge Queue Serializada**
- [ ] `scripts/tl_supervisor.py` expõe `enqueue_merge(story_id, pr_number, queue_file)` que adiciona um item ao fim de uma fila FIFO persistida em `queue_file` via escrita atômica.
- [ ] `scripts/tl_run_story.py` só invoca `gh pr merge` para o item no topo da fila cujo estado seja `pending`; nenhuma chamada de merge acontece para um item que não seja o topo.
- [ ] Após a chamada, o item é marcado `merged` ou `failed` em `queue_file`; um item `failed` nunca libera o próximo item da fila automaticamente — a liberação exige remoção explícita ou nova tentativa registrada.
- [ ] Teste cobre: duas stories enfileiram merge na mesma janela de tempo (chamadas concorrentes a `enqueue_merge`); a ordem de despacho respeita a ordem de chegada na fila (FIFO) e o segundo merge só é despachado depois que o primeiro está marcado `merged` ou `failed`.

**4. Varredura de worktrees órfãos**
- [ ] `scripts/tl_supervisor.py` expõe `sweep_orphan_worktrees(pool_dir, stale_after_seconds)` que remove (`git worktree remove --force`) todo worktree cujo `slot.json` associado referencie uma lease sem `heartbeat_ts` atualizado há mais de `stale_after_seconds`, liberando a vaga correspondente.
- [ ] Teste cobre: worktree com `heartbeat_ts` mais antigo que `stale_after_seconds` é removido e a vaga volta a `pool_exhausted=false`.
- [ ] Teste cobre: worktree com `heartbeat_ts` dentro do limiar NÃO é removido pela varredura (nenhum falso positivo de remoção).

**5. Integridade do board sob escrita concorrente**
- [ ] Toda escrita de `tl_supervisor.py`/`tl_run_story.py` em `_tl-orc/project/STATUS.md` lê o `state_revision` corrente da linha-alvo antes de gravar e grava apenas se esse valor não mudou desde a leitura; em caso de divergência, a escrita é recusada com `{"state": "state_revision_conflict"}` e não altera o arquivo.
- [ ] Teste cobre: duas escritas concorrentes simuladas sobre a mesma linha do board (mesmo `id`, `state_revision` lido igual) — a segunda escrita é recusada por `state_revision_conflict` e o arquivo final reflete apenas a primeira escrita, sem linhas duplicadas ou truncadas.

**6. Documentação e changelog**
- [ ] `docs/EXECUTION_PROTOCOL.md` ganha uma seção nomeando explicitamente Worktree Pool, Scope Arbiter, Merge Queue Serializada e varredura de órfãos, com os mesmos termos usados no código (`acquire_worktree_slot`, `claim_scope`, `enqueue_merge`, `sweep_orphan_worktrees`).
- [ ] `prompts/orchestrator-playbook.md` ganha instrução explícita de consultar o Scope Arbiter antes de despachar uma story concorrente, com o critério objetivo: "despache concorrentemente somente se `claim_scope` retornar sucesso para todas as stories candidatas".
- [ ] `CHANGELOG.md` recebe uma entrada `[0.11.0]` descrevendo os quatro mecanismos entregues.

## Verification
Comandos executáveis localmente, sem chamada de modelo:

python -m pytest tests/test_tl_supervisor.py -v
python -m pytest tests/test_tl_job.py -v
python scripts/validate_repository.py
python skills/tl-spec-hardener/scripts/audit_spec.py _tl-orc/project/tasks/T015-execucao-concorrente-multi-story.md

Teste de concorrência dedicado (contenção real do pool e do arbiter, não apenas chamadas sequenciais):

python -m pytest tests/test_tl_supervisor.py -k "concurrent or race" -v

## O que pedir à revisão independente
1. **TOCTOU no Scope Arbiter (Tarefa 2):** confirme que a checagem de colisão de `content_paths` e a gravação da reivindicação em `claims_file` acontecem sob o mesmo lock exclusivo, sem nenhuma janela entre "ler o arquivo de reivindicações" e "gravar a nova reivindicação" em que uma segunda sessão possa ler o mesmo estado desatualizado. Rode o teste de concorrência da Tarefa 2 isoladamente e tente forçar uma corrida manual (duas chamadas quase simultâneas) para provar que exatamente uma vence.
2. **Fail-closed real, não apenas nominal:** verifique todo caminho de erro do `Scope Arbiter` e da `Merge Queue` (arquivo de reivindicações ilegível, `claims_file`/`queue_file` corrompido, falha de `os.replace`) e confirme que cada um deles resulta em recusa da story/merge, nunca em um `try/except` silencioso que trata a falha como "sem conflito" ou "pode prosseguir".
3. **Corrupção do board (Tarefa 5):** confirme que a checagem de `state_revision` cobre qualquer escrita concorrente na tabela `## Tasks`, inclusive quando a leitura do `state_revision` falha (arquivo ausente, linha não encontrada) — esse caso deve recusar a escrita, não assumir `state_revision=0` e prosseguir.
4. **Varredura de órfãos (Tarefa 4):** confirme que o limiar `stale_after_seconds` usado pela varredura é maior que a janela de tolerância de heartbeat já definida no protocolo de T014 (`docs/EXECUTION_PROTOCOL.md:446`), para que a varredura nunca remova um worktree cuja lease apenas está atualizando com atraso legítimo de I/O.
