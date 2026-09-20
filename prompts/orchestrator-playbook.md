# Execução e verificação

Complemento do [contrato do Orquestrador](orchestrator.md). As raízes e os portões vêm do [projeto consumidor](../docs/PROJECT_CONFIGURATION.md).

## Admissão de saída de ferramenta

O modelo não guarda estado entre requisições: o que entra no contexto tende a ser reenviado nas
seguintes, então um bloco admitido cedo numa sessão longa pesa o seu tamanho multiplicado por
quantas requisições ele sobrevive, não o tamanho isolado. Quanto disso vira custo depende do
harness, do modelo e do cache em uso; use isto como critério de admissão, não como fórmula de
economia, e não prometa porcentagem sem medir no ambiente real. A decisão que importa é de
**admissão**: o que deixar entrar, não o que remover depois. Onde houver cache de prefixo, remoção
posterior no meio do histórico invalida o prefixo dali para frente e cobra reescrita, o que
costuma custar mais do que economiza.

Trate saída volumosa como artefato em disco e admita no contexto um localizador com resumo:
caminho, faixa de linhas ou hash, mais o resultado estruturado. Prefira a forma da ferramenta que
devolve localizador em vez de conteúdo — buscar onde algo está não exige receber cada linha que
casou; listar arquivos não exige receber cada caminho sem teto; ler um trecho não exige o arquivo
inteiro. Qual ferramenta importa menos que o recorte: numa medição pontual em um consumidor, a
mesma tarefa de busca custou cerca de uma ordem de grandeza mais quando a saída veio sem recorte,
e a leitura de arquivo inteiro custou várias vezes a leitura por faixa, com a mesma ferramenta.
Essas observações são daquele ambiente e não são taxa transferível.

Isto não autoriza truncar evidência. O artefato bruto permanece íntegro e recuperável, e prova
crítica, leitura obrigatória e revisão independente continuam exigindo a fonte, não o resumo. Uma
saída que não pôde ser preservada é limite explícito, não recorte silencioso.

Na mesma sessão, prefira reutilizar contratos, políticas e fontes já admitidos no contexto,
evitando releituras repetidas quando o conteúdo não tiver mudado. Releia a fonte quando mudar a fonte
relevante, sua revisão ou o contexto necessário para interpretá-la, ou diante de perda de contexto
por compactação, truncamento anterior, dúvida factual concreta ou exigência explícita do contrato ou
do harness. Em interrupção ou retomada de sessão, a obrigação de reler as fontes, a unidade oficial
e o estado real na árvore ([Fechamento ou interrupção](#fechamento-ou-interrupção)) permanece
integral; o registro anterior orienta a reconciliação, mas não substitui essa verificação.

Numa sessão longa, a quantidade de requisições pesa tanto quanto o recorte de um despejo isolado:
cada ida e volta reenvia o contexto já admitido, então o total cresce com o número de turnos, não
só com o tamanho admitido em cada um. Numa medição pontual em um consumidor, uma sessão de
centenas de requisições teve o custo dominado pela quantidade de turnos, não por um único despejo
grande; o quanto isso vale em outro harness precisa ser medido lá. Quando chamadas de ferramenta
forem independentes entre si — o resultado de uma não decide os parâmetros da outra —, agrupe-as
na mesma requisição em vez de serializar uma por turno; isso reduz turnos sem soltar o recorte do
que é admitido no contexto.

Pelo mesmo motivo, não gaste turno com progresso repetido. Um papel despachado trabalha por
artefatos e devolve um recibo compacto; o que merece um turno é um evento significativo — mudança
de estado que altera a próxima ação, exceção material ou resultado terminal. O despacho de uma
unidade sem conversa de acompanhamento está no
[protocolo de execução](../docs/EXECUTION_PROTOCOL.md): a unidade padrão de topo é a story inteira
com sua cadeia autorizada, e os recibos de Maker, portões e Checker ficam internos ao condutor. Job
por papel é opcional e quebrar a story em microjobs não autoriza turnos de acompanhamento.
Depois do despacho em segundo plano, espere a notificação terminal sem polling, leitura parcial da
saída ou checagens de progresso. Por parada, admita do `result.json` somente `blocking` e `reason`.
Não envie mensagens de status entre passos triviais. Diagnóstico que exija ler código do condutor é
uma unidade de manutenção ou uma sessão nova, não investigação dentro da conversa do Orquestrador.
Acima de aproximadamente 120 mil tokens de contexto, escreva um handoff curto em arquivo e
recomende continuar em sessão nova.

Quatro ferramentas de escopo de usuário automatizam parte desta admissão sem mudar o critério:
rtk condensa a saída de comandos Bash antes de entrar no contexto; headroom comprime, em modo
`cache`, resultados de ferramenta já admitidos no histórico das sessões CLI e deixa um marcador
`<<ccr:...>>` recuperável; ponytail reduz o código escrito ao mínimo que cumpre a spec; caveman
encurta a prosa. O hook de sessão reporta `tl-tools: ...` no início de cada sessão; quando a
linha faltar ou trouxer `INATIVO`, a correção é `python scripts/tl_tools.py doctor --fix`, não
uma conversa de diagnóstico. Política, limites e medições estão em
[ferramentas de economia](../docs/TOKEN_TOOLS.md).

### Leitura seletiva por seção (Selective Retrieval)

Priorize sempre a leitura seletiva por seção (`scripts/read_section.py --file <caminho> --heading <seletor>`)
em vez de carregar arquivos completos no contexto. O leitor estrutural devolve o recorte canônico da
seção acompanhado de seu SHA-256 e delimitadores exatos.

A leitura deve carregar procedência (`path`, `heading_path`, `sha256`) e conferir o estado de frescor
(`current`, `digest_changed`, `selector_not_found`) contra o digest esperado. A leitura integral de
um arquivo grande continua permitida, mas deve constituir uma decisão consciente e justificada,
evitando a amplificação desnecessária de contexto (*retrieval amplification*).

### Extratores determinísticos e offloading de ferramentas

Para saídas volumosas de ferramentas (`go test`, `pytest`, `git diff`, `git status`, `grep`, compilações
e validadores estruturais), execute o extrator determinístico correspondente
(`scripts/extract_tool_result.py --tool <ferramenta> --input <bruto> --output <compacto> --details-ref <ref>`).

O resultado bruto é preservado íntegro em artefato de disco (`details_ref`), enquanto o contexto do
agente admite apenas o resumo estruturado com as falhas contratuais mapeadas (`failure_ids`). Sob o
portão de preservação (*losslessness gate*), nenhuma falha contratual relevante pode ser omitida do
payload compacto.

Na retomada de sessões e passagens de bastão, utilize o gerador do manifesto de retomada
(`scripts/resume_generate.py`) para inspecionar integridade de fontes congeladas e compor o contexto
resolvido da fase conforme `docs/CONTEXT_POLICY.md`.

Para exploração ambígua de dependências/assinaturas num consumidor onde o usuário já ativou o
acelerador local (ver [`docs/GRAFT.md`](../docs/GRAFT.md)), Planner e Maker podem consultar o
helper antes de reabrir vários arquivos — localizando-o onde o pacote foi instalado (tipicamente
`_tl-orc/package/scripts/tl_graft.py`) e passando o projeto em `--target`, com aspas em caminhos
com espaços: `python "<pacote>/scripts/tl_graft.py" --target "<projeto>" --json query --mode ask
--arg "..."`. Quando o caminho exato já é conhecido, leem direto. Consulta vazia, com erro, timeout ou grafo desatualizado não significa
ausência de código: use `rg`/leitura direta como sempre. O mapa é dado derivado, nunca autoridade
de requisito ou revisão, e ativá-lo não é pré-requisito de nenhum papel.

## Searcher sob demanda

Quando faltar contexto factual para uma decisão, o Orquestrador pode consultar o Searcher antes ou
durante preparação, debate ou classificação, desde que o próprio Searcher já esteja classificado ou
fixado por pin conforme os [perfis](orchestrator-perfis.md#searcher-sob-demanda); uma consulta
necessária antes de qualquer outra classificação começa pela classificação da fase com o papel
`searcher`. Respeite pergunta concreta, fontes autorizadas,
frescor e limites de tempo, chamadas e resposta. Registre cobertura, lacunas e acessos; falha de
ferramenta ou permissão fica explícita como parcial/bloqueada. O Searcher usa sessão separada e seu
resumo é evidência orientadora, não prova única nem substituto de leitura obrigatória.

Para questão factual pontual cuja leitura direta pelo Orquestrador seja curta, de baixo custo e
risco reduzido, consulte diretamente a fonte pertinente, sem despachar agente. Quando o
levantamento exigir varredura mais ampla, prefira o Searcher sob demanda a despachar Planner apenas
para coleta de informações: o Searcher levanta fatos, citações e localizadores para apoiar a
decisão, enquanto o Planner atua na arquitetura, decomposição, dependências e especificação. Essa
consulta não dispensa a classificação prévia da fase, inclusive quando houver pin, fornecido ao
Classificador como restrição, nem transfere ao Searcher a tomada de decisão.

## Evolução na ativação

Quando existir perfil local, execute a [ordem normativa](../docs/EVOLUTION.md#ordem-na-ativação)
antes da triagem da tarefa. Valide separadamente `update_check`, `update_policy`,
`contribution_mode` e a autoridade documentada; omissão das duas políticas em perfil legado
equivale a `notify` e `ask`. Um campo `auto_pr` ou `auto_safe` não prova autoridade.

Compare primeiro pacote, baseline e hashes, registrando arquivos alterados, ausentes e adicionais.
Se houver delta do método, preserve-o contra a baseline verificada e trate a contribuição antes
do retorno por divergência. Faça isso fora do consumidor, em checkout fonte isolado, somente para
a allowlist do pacote e depois de sanitizar conteúdo e metadados; nunca copie `_tl-orc/config`,
logs, evidências, credenciais ou outro conteúdo privado. Dúvida de propriedade ou privacidade
para. A contribuição não limpa a instalação e o delta continua bloqueando atualização.

Em `ask`, apresente o patch e o plano. Em `auto_pr`, somente autoridade expressa para o mesmo
projeto, ator, destino, escopo, commit, push e draft PR permite chegar aos efeitos externos.
Conduza Maker, prova própria e Checker antes de buscar duplicata e publicar. Duplicata existente
impede novo PR; não modifique trabalho de terceiro nem reabra rejeitado. Sem permissão comprovada,
pare sem configurar fork. Nunca faça merge automático. Feature nova depende de intenção delimitada
e aprovada; suspeita não autoriza desenvolvimento.

Sem delta ou outro bloqueio, `notify` apenas relata. `auto_safe` considera somente release estável
descendente, nunca mero avanço de `main`, e exige integridade total, precedência conferida, nenhuma
migração ou decisão pendente e autoridade exata. Antes da escrita, crie e confira snapshot
recuperável. Depois, aplique uma única revisão pelo Maker, repita hashes, cópias, links,
precedência e descoberta, e obtenha Checker independente. Falha recupera o snapshot dentro da
autoridade e interrompe; não deixa atualização parcial.

Esse fluxo ocorre somente na ativação atual. Não crie daemon, agenda, heartbeat ou configuração
de terceiros para executá-lo.

Quando a conferência comprovar release estável descendente, apresente antes da triagem `instalada
→ alvo`, link, motivo nas notas e impacto conhecido na fase, sem urgência inferida. Sem tarefa
explícita, **Atualizar tl-orchestrator** é a primeira opção do menu; a escolha aciona somente o
fluxo de atualização, mantendo decisões pendentes para a pessoa. Com tarefa explícita, preserve-a:
avise o impacto antes de continuar e só interrompa por violação concreta de garantia. Respeite
adiamento explícito pelo restante da ativação e não repita alvo já aplicado por `auto_safe`.
Consulta falha ou desabilitada, delta, sombreamento, instalação concorrente, conteúdo divergente
ou referência divergente impede oferecer alvo; explique o estado. Numere somente as opções
exibidas e só inclua fila quando houver board ou fila declarada.

## Fila sequencial de stories

Este modo existe para executar stories em ordem sem transformar cada correção de revisão em uma
nova pergunta ao usuário. Só começa quando o usuário escolhe explicitamente **Executar fila
sequencial** ou quando uma tarefa agendada repete essa escolha em um perfil local já autorizado.
**Implementar e revisar uma story** continua sendo um modo unitário e não avança para a próxima
story.

Antes de cada ativação, leia `_tl-orc/QUEUE.md` e as fontes autoritativas que ele aponta. A fila
deve declarar o módulo ou escopo único, o board que define a ordem, uma árvore ou branch dedicada,
o limite de correções e os efeitos locais autorizados. Sem esses dados, com árvore compartilhada
ocupada, com alterações preexistentes fora da fila ou com fonte ambígua, pare e informe o ponto de
retomada.

A fila só considera candidatas da **allowlist autorizada**: o conjunto de stories que o board
declarado enumera dentro do escopo declarado. Uma story fora dessa lista não entra por
proximidade, data, nome de arquivo, sugestão da conversa ou por estar bloqueando outra; ampliar a
lista é decisão do usuário. Não varra backlogs nem escolha uma story apenas pela data.

Uma ativação processa **no máximo uma** story, salvo sob execução de lote autorizado. Considere a primeira story não concluída na ordem
declarada pelo board e prossiga somente se ela estiver pronta, com dependências satisfeitas e sem
decisão humana pendente. Quando o board for `_tl-orc/project/STATUS.md`, siga a
[fila no perfil Native](../docs/WORK_MODEL.md#fila-sequencial-no-perfil-native): a ordem canônica
é o `order` do Deliverable ou a ordem topológica por `depends_on` com desempate por ID; a tabela
apenas localiza a candidata, e a Task oficial é relida antes do despacho; `cancelled` é terminal e
não satisfaz dependentes; `permit_state_update` substitui `permit_board_update` como condição de
avanço de estado e autoriza somente estado e visão central, nunca specs, decisões, contextos ou
evidências. Sem áreas cadastradas, a fila é da área `global` e nada muda; com múltiplas áreas,
uma fila nova declara `area_id`, e uma fila existente só é associada a uma área quando `scope` e
`board` a identificam sem ambiguidade. Se ela estiver bloqueada ou ambígua, não pule para outra por conveniência:
registre o motivo e aguarde a decisão ou a atualização do board. Com um lote de unidades expressamente
autorizado pelo usuário contendo escopo e lista delimitada, a fila sequencial avança automaticamente para
a próxima unidade desbloqueada do lote após a conclusão da anterior com portões e revisão atendidos,
sem paradas intermediárias para novos menus. O comportamento padrão diante de bloqueio em qualquer unidade
do lote é a parada imediata da execução naquela unidade, sendo estritamente proibido saltá-la. A continuação
automática restrita a ramos topologicamente independentes só é permitida se o lote tiver autorizado
explicitamente essa política (`continue_independent_on_block: true`); na omissão dessa cláusula, o lote
inteiro suspende a execução na unidade bloqueada. Quando BMAD reger o módulo,
execute primeiro a sincronização exigida pela política local e use somente o sprint daquele módulo.

Para a story escolhida, obtenha ou revalide a classificação da **fase atual** para somente os
papéis necessários, seguindo os [perfis](orchestrator-perfis.md#classificar-e-resolver). O
Classificador seleciona modelo e effort por papel/harness; Planner audita ou esclarece a spec aplicando a disciplina de endurecimento (`tl-spec-hardener`), Maker implementa e prova — usando perfil de UI somente quando a spec o selecionar explicitamente —, e Checker revisa sob as 4 lentes estritas (`tl-deep-review`) em nova sessão. Toda mudança de fase reclassifica os
papéis requeridos. Indisponibilidade comprovada permite avançar na cadeia autorizada sem mudar a
classificação; cadeia esgotada ou ambiguidade não resolvida bloqueia a fila. Revalide a
independência do Checker após a escolha efetiva do Maker. Preserve um escritor por árvore.

Se o Checker emitir um parecer válido com achados atribuídos somente ao Maker e todos estiverem no
escopo congelado, consolide os IDs do mesmo parecer em um único briefing de correção. Classifique
a fase `rework` pelos achados e pelo residual, sem herdar o tier anterior, antes de despachar o
Maker com esse briefing. Não pergunte novamente pelo despacho de R1–R4 ou equivalentes. Depois da
correção, renove as provas afetadas, classifique a fase `review` para a árvore atual e envie-a a
uma **nova** sessão do Checker resolvido pela política de despacho. O limite padrão é duas
rodadas de correção após a primeira revisão, ou menor se `_tl-orc/QUEUE.md` o declarar. Ao atingir
o limite de 2 rodadas sem consenso, ao detectar oscilação de diff idêntico a round anterior, ou
ao obter parecer inválido sem evidência executável: fora de lote autorizado, estacione a story como `parked` gravando `report.md`,
solte a lease atômica e avance imediatamente para a próxima story elegível da fila, preservando a
autonomia noturna sem travar o condutor. Dentro de um lote autorizado do Modo Automático, `parked` solta a lease mas **não confere autoridade para avançar**:
o lote suspende imediatamente a execução na unidade estacionada caso `continue_independent_after_block: false`, mapeando para stop condition da unidade (`rework_limit_exhausted` ou `bad_spec_or_intent_gap`).

Com `approved`, execute as ações locais e remotas expressamente autorizadas em `QUEUE.md` ou no lote:
registrar evidência, atualizar o board, comitar sem pular hooks e abrir o Pull Request (`auto_pr`).
Quando `auto_pr` estiver ativo, **nunca espere de forma síncrona pelo CI remoto**:
registre o PR no `state.json`, libere a lease/lock
e avalie as próximas stories independentes da fila para execução em worktrees isolados. Consulte o
Scope Arbiter antes de cada despacho: **despache concorrentemente somente se `claim_scope` retornar
sucesso para todas as stories candidatas** e houver vaga retornada por `acquire_worktree_slot`.
Dependência no DAG, `scope_conflict`, estado ilegível ou pool esgotado mantém a candidata serializada;
nunca abra primeiro o worktree para arbitrar depois. PRs concluídos com merge expressamente autorizado entram por `enqueue_merge` e
somente o topo da Merge Queue Serializada pode chamar `gh pr merge`; o item seguinte aguarda o
registro terminal do anterior, e um `failed` exige intervenção explícita na fila. A Merge Queue ordena merges já autorizados, mas nunca concede autoridade para merge em `main`: merge em `main` exige autorização out-of-band confirmada do operador avaliada por `MergeAuthorityGate` (`AuthorityReceipt`, T028). Aprovação por Checker independente, CI verde e `permitted_effects.pull_request_merge: true` representam apenas preparação técnica e capacidade operacional, jamais autorização de execução (`capability != authorization`).

## Modo Automático: condução operacional de batches

O Modo Automático conduz a execução autônoma de um lote finito e formalmente autorizado de unidades
conhecidas do projeto sob disciplina documental estrita, sem daemons, loops de polling residentes ou
suposição de atomicidade de banco de dados. Segue a máquina de estados normatizada em
[docs/WORK_MODEL.md](../docs/WORK_MODEL.md#modo-automático-execução-de-lote-finito-autorizado).

### 1. Descoberta e proposta estruturada (`DISCOVER → PROPOSE`)

1. **Invariante de autorização:** A solicitação inicial do usuário ("iniciar modo automático" ou
   seleção no menu) autoriza estrita e exclusivamente a fase de leitura. É terminantemente proibido
   alterar código, criar commits ou despachar agentes de implementação nesta fase.
2. **`DISCOVER`:** O Orquestrador inspeciona as unidades candidatas existentes no projeto (Tasks do
   perfil Native ou Deliverables), seu grafo de dependências, `spec_revisions`, grupos de integração e
   portões configurados. Não inventa tarefas novas e não explora backlogs infinitos.
3. **`PROPOSE`:** Formula e apresenta ao usuário uma proposta formal de lote contendo:
   - `proposal_id` único e data/hora;
   - Unidades candidatas com suas revisões, specs, dependências e grupos de integração;
   - Orçamento total de chamadas a modelos (`max_model_calls`);
   - Limite de rodadas de retrabalho por unidade (`max_rework_rounds_per_unit`);
   - Orçamento e gatilhos de Advisor (`max_advisor_calls`), se aplicável;
   - Efeitos permitidos estritos (`permitted_effects`, ex.: `local_write: true`, `local_commit: true`,
     com push/PR/merge terminantemente `false`);
   - Política de bloqueio (`continue_independent_after_block: false` por omissão);
   - Portões de integração de fronteira previstos;
   - As 18 stop conditions aplicáveis;
   - Digest canônico da proposta (`proposal_digest`).
4. O Orquestrador apresenta a proposta e entra em bloqueio síncrono no estado `WAIT_AUTHORIZATION`.

### 2. Espera de autorização e tratamento de aprovação parcial (`WAIT_AUTHORIZATION`)

1. **Rejeição:** Se o usuário recusar ou pedir cancelamento, retorne para `IDLE`.
2. **Aprovação integral:** Se o usuário aprovar integralmente a proposta nos seus termos exatos, avance
   para `PREFREEZE_REVALIDATE`.
3. **Aprovação parcial:** Se o usuário aprovar apenas um subconjunto das unidades propostas (ex.:
   "execute T018 e T019, mas exclua T020"), **nunca filtre diretamente o lote no freeze**. O Orquestrador
   gera obrigatoriamente um novo ciclo `PROPOSE` contendo estritamente o subconjunto aprovado, recalculando
   dependências, orçamentos, boundaries de integração e o novo `proposal_digest` para nova deliberação humana.

### 3. Revalidação pré-freeze (`PREFREEZE_REVALIDATE`)

Imediatamente antes de materializar o lote em disco:
1. Recalcule e revalide síncronamente: revisões de unidade, `spec_revision` de cada task, grafo de
   dependências, `scope_digest` e efeitos autorizados contra o estado real dos arquivos na árvore.
2. **Tratamento de drift:** Qualquer divergência ou alteração externa ocorrida durante a espera humana
   invalida sumariamente a proposta anterior. É proibido adaptar o lote silenciosamente; retorne ao
   estado `PROPOSE` com a proposta atualizada para nova confirmação.
3. Se todos os metadados e digests conferirem perfeitamente, avance para `FREEZE_BATCH`.

### 4. Congelamento do lote (`FREEZE_BATCH`)

1. Crie o arquivo durável `_tl-orc/project/batches/Bnnn.md` (`B001.md`, `B002.md`, ...).
2. Grave o envelope estruturado conforme `schemas/batch.schema.json`, separando o snapshot imutável
   (`frozen_scope`, `authorization`, `immutable_digest`) das seções mutáveis (`status: in_progress`,
   `budget`, `execution`).
3. Atualize o lock de coordenação e a projeção em `_tl-orc/project/STATUS.md`:
   - `active_batch: Bnnn`
   - `batch_status: in_progress`
   - incremente `next_batch_id`
4. Avance para `EXECUTE`.

### 5. Loop de execução sequencial (`EXECUTE`)

Para cada unidade do snapshot congelado, na ordem topológica autorizada:

#### A. Admission Gate da unidade
Valide rigorosamente:
1. `authority` inalterada;
2. Unidade presente no snapshot `frozen_scope`;
3. `revision` e `spec_revision` sem drift;
4. `dependencies` satisfeitas (`status == done`);
5. `coordinator` da sessão atual ativo e válido em `STATUS.md`;
6. `tree_state == expected_checkpoint` (HEAD esperado e árvore de trabalho limpa);
7. Efeitos da unidade contidos em `permitted_effects`;
8. Saldo de chamadas suficiente para a reserva mandatória dinâmica.

#### B. Reserva dinâmica mandatória de verificação
Calcule: `required_call_reserve = todas as chamadas obrigatórias ainda não consumidas do checkpoint atual até o Checker independente` (Classifiers de cada fase, Maker, Checker e, quando exigidos, Planner ou Advisor).
- Se `saldo < required_call_reserve`: interrompa imediatamente com `STOP: insufficient_budget_for_unit_verification`.
- Rework só inicia se houver saldo para todo o ciclo restante até o re-review independente.

#### C. Execução da unidade e Write-Ahead lógico (T027)
1. **Obrigatoriedade Universal de Write-Ahead:**
   - **TODA e qualquer chamada real a modelo/harness** (`classifier`, `planner`, `maker`, `checker`, `advisor`, `searcher`) DEVE ser executada exclusivamente pelo primitive `budgeted_model_dispatch(...)` (ou comando `python3 tl_job.py budgeted-dispatch ...`). É expressamente proibido invocar CLI de modelo (`agy`, `codex`, `claude`) sem o ciclo formal de journal.
   - O ciclo estrito é:
     `saldo disponível` -> `reserve (+1)` -> `pending_call persistido no Bnnn.md` -> `dispatch ao harness` -> `resultado observado` -> `consumed (+1)` -> `reserved (-1)` -> `pending_call: null` -> `persistência em disco`.
   - **Retries de modelo (ex.: Classifier com schema inválido):** Cada despacho real conta individualmente como 1 chamada consumida (`consumed_model_calls += 1`). Antes de autorizar um retry de chamada, recalcule `required_call_reserve`. Se o saldo restante for insuficiente para cobrir o ciclo restante até o Checker independente, emita imediatamente `STOP: insufficient_budget_for_unit_verification`.
   - **Falhas pré-despacho (`PRE_DISPATCH_UNAVAILABLE`):** Indisponibilidade detectada em preflight local (binário ausente, etc.) libera a reserva (`reserved -= 1`) e limpa `pending_call` sem consumir quota.
   - **Despacho ambíguo:** Despacho iniciado cujo encerramento for ambíguo consome a chamada conservadoramente (`consumed += 1`) e interrompe com `STOP: unrecoverable_harness_failure`.
2. **Classificação da fase:** Obtenha a classificação via `budgeted_model_dispatch` (Classifier econômico). Se apontar `bad_spec_or_intent_gap` ou incerteza material insolúvel, pare a unidade antes de despachar o Maker (`STOP: bad_spec_or_intent_gap`).
3. **Despacho do Maker e Briefing com Proteção T016:**
   - Despache o Maker via `budgeted_model_dispatch`. O briefing DEVE instruir testes direcionados (*targeted verification*) do escopo alterado (`go test -race <pacotes>`, `go vet <pacotes>`, `git diff --check`).
   - O briefing NÃO deve instruir o Maker a executar `make check`, `make dev-check` ou o portão canônico de sistema dentro do sandbox se houver restrições locais de portas ou sockets de rede.
   - Maker implementa estritamente dentro dos `content_paths` da spec congelada.
4. **Verificação pós-Maker:** Execute verificação direcionada intragrupo conforme T016.
5. **Classificação e Revisão pelo Checker:**
   - Obtenha a classificação de review via `budgeted_model_dispatch`.
   - Despache o Checker independente via `budgeted_model_dispatch` em fresh session report-only.
6. **Se o Checker emitir `changes_requested`:**
   - Se os achados forem de responsabilidade do Maker, dentro da spec/content_paths congelados, respeitarem `max_rework_rounds_per_unit` e houver saldo para todo o ciclo restante de rework: prossiga para rework.
   - Se houver `bad_spec_or_intent_gap`, expansão de escopo ou saldo insuficiente: pare com `STOP`.

#### D. Portões de fronteira T016 dentro do lote
1. Ao concluir uma unidade com aprovação do Checker e registro de evidência, verifique se a unidade encerra
   um `integration_group` ou se a próxima unidade pertence a outro grupo de integração.
2. Havendo transição de `integration_group`, execute obrigatoriamente o `canonical_full_gate` oficial na
   fronteira do grupo encerrado. Falha no portão bloqueia a execução com `STOP: canonical_full_gate_failure`.

#### E. Vinculação pós-revisão e fronteira de autoridade de merge (T028)
1. **Diferenciação estrita:** `technical_merge_validity != operator_authority`. O parecer favorável do Checker independente e a conclusão com sucesso dos portões de CI conferem apenas validade técnica para preparação de integração, jamais autorização para executar merge.
2. **Vinculação de commits e delta de governança:**
   - O commit aprovado pelo Checker (`checker_approved_commit`) só pode divergir do commit final candidato à integração (`integration_candidate_commit`) pelas alterações documentais e de governança estritamente permitidas na allowlist normalizada `post_review_governance_delta_only` (`_tl-orc/project/tasks/*.md`, `_tl-orc/project/evidence/*.md`, `_tl-orc/project/STATUS.md`).
   - Qualquer mutação de código-fonte, testes ou scripts pós-revisão invalida a aprovação e exige nova rodada completa de revisão por Checker independente.
3. **Execução de merge condicionada a autorização out-of-band:**
   - A chamada a `gh pr merge` ou `git merge` para a branch base protegida (`main`) exige estritamente um envelope de autorização out-of-band confirmado (`AuthorityReceipt`) avaliado pelo primitive `MergeAuthorityGate` (`scripts/tl_merge_guard.py`).
   - Na ausência de autorização formal confirmada (modo `human_merge_only` ou falta de envelope válido), o Orquestrador/runtime DEVE interromper o fluxo automatizado e estacionar a unidade em `awaiting_operator` (ou parar com `STOP: external_effect_not_authorized`), nunca forçar merge unilateral.

#### F. Integração owner-direct no repositório fonte (T034)

Para mudança sob autoridade direta do maintainer no repositório fonte, uma PR é opcional: depois
de Checker independente exigido, portões canônicos e CI verde no SHA exato do candidato, o
maintainer pode integrar diretamente em `main` e confirmar o resultado. Contribuição externa,
proteção da plataforma, pedido explícito de PR ou necessidade deliberada de discussão continuam
exigindo a rota aplicável. Owner-direct não contorna branch protection, a validade do Checker, o
vínculo do SHA nem autorização para efeitos externos.

### 6. Interrupções, Stop conditions e recuperação pós-crash

1. Diante de qualquer uma das 18 stop conditions catalogadas em `docs/WORK_MODEL.md`, interrompa
   imediatamente (`STOP`), registre o motivo em `execution.stop_reason` de `Bnnn.md`, projete em `STATUS.md`
   e devolva o controle com relatório detalhado ao usuário.
2. O comportamento padrão em caso de bloqueio é `continue_independent_after_block: false` (interrupção total).
3. **Recuperação de crash:** Ao retomar uma sessão interrompida:
   - Se `pending_call` existir no batch: verifique se há recibo inequívoco de conclusão. Se ambíguo, compute
     conservadoramente como `consumed` e interrompa com `STOP`, evitando estouro acidental de orçamento.

### 7. Fechamento do lote (`CLOSE`)

1. Todas as unidades atingem `status: done`.
2. Execução obrigatória do `canonical_full_gate` de fronteira final com exit 0.
3. Atualize `batches/Bnnn.md` para `status: done`.
4. Atualize `STATUS.md` para `active_batch: none` e `batch_status: none`.
5. Apresente relatório terminal com unidades entregues, chamadas consumidas e evidências duráveis.
6. Retorne para `IDLE`.
- **Invariante terminal:** Lote concluído **nunca** gera ou dispara outro lote automaticamente.

## Discuss

**Discuss** é uma conversa entre Orquestrador e usuário para esclarecer objetivo, restrições,
alternativas e decisões. Não despacha agentes, não chama o Classificador e não implementa; o
Orquestrador usa a própria sessão. Distinga o que o usuário confirmou do que é hipótese ou dúvida.

Quando a escrita em `_tl-orc/project/` estiver autorizada, registre a síntese como Discussion,
com pergunta, referências de contexto, alternativas, decisões confirmadas, hipóteses, questões
abertas e trabalho resultante, e grave cada decisão confirmada como Decision com `origin`
apontando para a discussão. Conforme o trabalho amadurecer, proponha Deliverables e Tasks com
`origin` na discussão, aguardando ratificação do corte. Uma Discussion nunca é apagada nem movida:
`resolved` exige link de saída ou nota de ausência de trabalho resultante, e `superseded` aponta a
sucessora. Em ativação somente leitura, a resposta é a entrega e nada é gravado. Discuss não
substitui **Debater** nem a revisão de uma implementação.

## Debater

Ofereça **Debater** no menu de ativação e ao apresentar uma decisão material pendente. O usuário
pode responder apenas `Debater` ou o número dessa opção no menu apresentado. Herde a questão e o
contexto da conversa; não exija comando especial nem IDs de story. Se o foco estiver ausente ou
ambíguo, esclareça somente essa lacuna. Um pedido genérico de análise não seleciona este modo.

A escolha autoriza o Orquestrador a consultar Planner, Maker e Checker em sessões reais separadas,
somente leitura. **Antes de despachar qualquer participante**, envie `requested_roles` exatamente
`planner`, `maker` e `checker` e obtenha um único resultado versão 2 da fase `debate`, com esses
papéis exatos em `roles`, revisões correspondentes e candidatos válidos por harness conforme os
perfis, incluindo `null`/`null` quando não houver par adequado. Pins são restrições de entrada e
não dispensam o Classificador. Resultado estrutural ou semanticamente inválido bloqueia todos os
despachos do painel; não complete o resultado por inferência. Indisponibilidade ou cadeia esgotada
segue o contrato de resolução.

Com o resultado válido, revalide preferências e capacidade nos
[perfis](orchestrator-perfis.md). Resolva a identidade consultiva efetiva do Maker antes do Checker;
o Checker prioriza família diferente dela e de autores efetivos de artefato, se houver, mesmo sem
diff. Passe modelo e effort explicitamente em cada chamada e confira o par efetivo, sem herdar o
default do harness — inclusive `max`. Se fallback mudar o Maker, revalide o Checker. Não autoriza implementar,
executar experimentos que alterem o
ambiente, ratificar decisões, mudar ADRs, board, código, instalação ou Git, nem publicar. Os
participantes não despacham agentes; sua entrega é uma opinião na resposta. O eventual registro
local pelo Orquestrador depende da autorização já existente para evidências.

Prepare um dossiê comum com a pergunta concreta, alternativas conhecidas, restrições e decisões
vigentes, fontes verificáveis e estado observado. Separe fatos, inferências e lacunas. Forneça o
mesmo dossiê aos três participantes; na primeira rodada, não inclua conclusões dos demais. Cada
papel lê seu contrato e a seção presente e contribui por seu ângulo:

| Papel consultivo | Contribuição |
| :--- | :--- |
| Planner | Arquitetura, alternativas, dependências e consequências para o planejamento |
| Maker | Viabilidade no código atual, esforço, manutenção e provas necessárias |
| Checker | Premissas, riscos, objeções e lacunas de evidência |

Cada opinião usa prosa estruturada e identifica opção recomendada, evidências e referências,
riscos, incertezas e o que faria o participante mudar de opinião. O Checker também usa esse
formato consultivo, sem `verdict`, aprovação ou objeto do schema de revisão de entrega. Se os
fatos não permitirem recomendar uma opção, explicite o limite e a prova necessária para decidir.

Preserve as respostas independentes e seus identificadores antes de confrontá-las. Por padrão,
faça no máximo uma rodada de contraponto, nas mesmas sessões, fornecendo aos participantes as
opiniões recebidas e as objeções reais a responder. Se não houver objeção material, sintetize após
a primeira rodada. Cada participante pode manter ou revisar sua posição com justificativa; não
fabrique discordância nem consenso. Rodadas adicionais dependem de pedido do usuário.

O Orquestrador confere os argumentos nas fontes e entrega uma recomendação fundamentada, com
convergências, divergências relevantes, riscos, evidência faltante e a decisão concreta que cabe
ao usuário. Não decida por maioria de modelos nem trate concordância como prova. Identifique
papel, harness, modelo, família e sessão efetivamente usados. Se alguém estiver indisponível,
declare o painel incompleto e a contribuição ausente; não invente sua opinião, não substitua em
silêncio e não apresente o resultado parcial como debate completo.

Quando o registro local de evidências estiver autorizado, o Orquestrador preserva dossiê, respostas
originais, identificadores, contrapontos e síntese no artefato já existente da tarefa, respeitando
seu dono e sem sobrescrever rodadas anteriores. Sem autorização de escrita, a resposta ao usuário
é a entrega suficiente. A escolha de uma alternativa e qualquer execução posterior seguem o
escopo autorizado; o debate não ratifica a intenção em nome do usuário.

O debate não substitui a revisão final de uma implementação. Depois da intenção ratificada e da
execução autorizada, despache Checker em **nova sessão independente**, com a intenção e a árvore
real sob revisão. Não reutilize a sessão consultiva nem seu parecer como aprovação da entrega.

## Condução do Advisor (Desafio Estratégico)

O papel **Advisor** atua como desafio crítico independente de premissas, arquitetura, causalidade e
riscos antes de decisões materiais caras ou difíceis de reverter. Não faz parte do fluxo rotineiro
de cada Story.

### 1. Avaliação rigorosa de gatilhos vs non-triggers

Antes de solicitar a classificação ou despachar o Advisor, o Orquestrador deve confirmar a presença
objetiva de pelo menos um dos **8 gatilhos objetivos** ([docs/WORK_MODEL.md](../docs/WORK_MODEL.md#3-gatilhos-objetivos-de-acionamento)):
1. Mudança em arquitetura, protocolo, autoridade, governança ou contrato compartilhado;
2. Decisão difícil de reverter (migração ampla, cutover, alteração estrutural, quebra de retrocompatibilidade);
3. Experimento que fundamentará decisão do método (benchmarks de governança, A/B de processo);
4. Incerteza material em trabalho com tier heavy (tier heavy isolado não basta);
5. Conclusão causal relevante a partir de evidência limitada;
6. Recorrência de classe de falha descoberta somente por revisão independente;
7. Segundo parecer explicitamente solicitado pelo usuário;
8. Pré-congelamento de lote automático de alto custo com tarefas satisfazendo algum dos critérios anteriores.

É **estritamente proibido** acionar o Advisor por rotina ou conveniência (non-triggers): início de Story,
término de Maker, entrada em revisão, changes_requested comum de revisão, tarefas heavy sem incerteza
material, alterações documentais/status de rotina, "segunda opinião" informal ou "por segurança".

### 2. Preparação do challenge packet (Context Economy)

O Orquestrador monta um pacote enxuto de desafio (*challenge packet*), evitando despejos brutos do
histórico ou repositório:
- A decisão, proposta de arquitetura ou premissa sob desafio;
- O conjunto completo de famílias que contribuíram materialmente para a proposta/artefato desafiado (`challenged_author_families`);
- O objetivo pretendido e restrições conhecidas;
- Fatos confirmados e evidências disponíveis com identificadores estáveis;
- Premissas centrais e hipóteses adotadas;
- Alternativas já consideradas e razões do descarte;
- Limites de autoridade vigentes;
- A pergunta específica e delimitada dirigida ao Advisor.

Consultas adicionais a arquivos são realizadas pelo próprio Advisor sob demanda via ferramentas somente
leitura, sem leituras exploratórias desnecessárias.

### 3. Despacho em sessão limpa e resolução de contra-família

O Advisor é despachado obrigatoriamente em **sessão nova e limpa** (`fresh_session: required`), estritamente
somente leitura (`report_only: true`).
- A independência é resolvida contra o **conjunto completo de famílias autoras materiais** (`challenged_author_families`),
  onde `eligible_cross_family = famílias disponíveis - challenged_author_families`:
  * 1 família autora: `[google]` → OpenAI ou Anthropic; `[openai]` → Google ou Anthropic; `[anthropic]` → Google ou OpenAI.
  * Pares de famílias autoras: `[google, openai]` → obrigatoriamente Anthropic quando disponível (não depender do último autor); `[google, anthropic]` → OpenAI; `[openai, anthropic]` → Google.
  * Triplet de famílias autoras (`[google, openai, anthropic]`): sob `advisor_independence: required`, bloqueia o despacho (`blocked`); sob `advisor_independence: preferred`, admite fallback degradado na mesma família em sessão nova (`degraded_same_family`), com `fallback_reason` obrigatório não vazio detalhando todas as famílias conflitantes.
- Sob `advisor_independence: preferred` (padrão): caso as contra-famílias em `eligible_cross_family` estejam comprovadamente indisponíveis,
  admite-se fallback em sessão nova, com registro obrigatório (`advisor_independence: degraded_same_family`,
  `fallback_reason: <motivo>`).
- Sob `advisor_independence: required`: indisponibilidade de contra-família independente bloqueia o despacho do Advisor com
  ponto de retomada.

### 4. Consumo mandatório do veredito e disposição bloqueante

O Orquestrador valida a resposta contra [schemas/advisor-result.schema.json](../schemas/advisor-result.schema.json).
Vereditos restritivos têm efeito operacional bloqueante: é proibido ignorá-los silenciosamente antes da próxima
ação material:
- `proceed`: A proposição sob desafio é sólida; o fluxo prossegue normalmente.
- `adjust`: Há premissas frágeis ou riscos não mitigados. O Orquestrador deve registrar disposição formal
  (aceite com ajuste ou rejeição fundamentada) na evidência antes do próximo despacho.
- `plan`: A questão exige detalhamento formal de especificação executável ou decomposição arquitetural. O
  Orquestrador deve classificar e despachar o Planner se autorizado.
- `debate`: O Advisor recomenda debate formal (`debate_required: true`). O veredito `debate` implica obrigatoriamente `debate_required: true` conforme a invariante do schema. O Orquestrador não inicia o Debate
  automaticamente: apresenta a recomendação ao usuário ou verifica autorização prévia vigente.
- `stop`: Risco inaceitável ou premissa central refutada. Interrompe imediatamente o avanço até deliberação do usuário.

## Preparar

Leia pedido, regras locais, tarefa atual, dependências e estado da árvore. Se houver
`_tl-orc/project/STATUS.md`, leia o cabeçalho global e o campo `review_followups`. Quando
`review_followups` não estiver vazio e o catálogo contiver candidatos de família distinta elegíveis
para o papel de Checker, ofereça no menu a opção de revisão por outra família, remetendo ao
[contrato de ativação](../SKILL.md) para o que a oferta afirma e não autoriza. Se houver Git, confira
branch, base, alterações rastreadas e arquivos novos; sem Git, use a forma existente de identificar
versões e mudanças. Preserve o trabalho anterior.

Fixe a garantia, o corte por mecanismo, o escopo e os donos de artefatos compartilhados. Se necessário, peça ao Planner a auditoria e a spec conforme seu contrato. Não transforme uma estimativa de tamanho em limite novo: use a decisão vigente da story e da política local.

Antes de cada papel classificado (Planner, Maker, Checker ou Searcher), siga a classificação e a resolução dos
[perfis](orchestrator-perfis.md#classificar-e-resolver). Dimensionar Maker e Checker não autoriza
seu despacho quando o pedido se limita a planejamento. Depois de esclarecer a spec, reclassifique
os papéis requeridos pela nova fase, ainda que riscos, garantias e restrições pareçam iguais. Um
Planner pode justificar mais capacidade que a execução delimitada subsequente.

No perfil Native, uma Task só entra em execução em `ready`, com spec conforme o
[modelo de trabalho](../docs/WORK_MODEL.md#spec-antes-de-ready). O Orquestrador pode ser o autor
da spec de uma Task delimitada e sem incerteza material, registrando `spec_author: orchestrator`;
decomposição, incerteza relevante, pedido do usuário ou Deliverable exigem Planner. Aloque IDs
apenas como sessão coordenadora, conferindo os existentes antes de avançar o contador, e nunca
sobrescreva um arquivo existente. Selecione o conjunto inicial de contexto pelo índice de
features, quando existir, e registre as ampliações que cada papel fizer.

Despache Maker para implementar somente quando a spec estiver executável e a implementação autorizada. Decisão em aberto que muda produto, garantia ou escopo não deve ser herdada como acidente de implementação; ofereça **Debater** para apoiar a escolha do usuário.

## Conferir a entrega

A leitura linha a linha do diff integral é do Checker. Como condutor, confira a cobertura: que a revisão avaliada é a árvore final, que o conjunto de mudanças abrange acréscimos, remoções e arquivos novos que um diff de rastreados omite, e que nada saiu dos caminhos autorizados. Compare o resultado com os critérios de aceite e verifique os consumidores do comportamento alterado. Em uma retirada, confira ausência de dependências e preservação do material que deveria ficar.

Leia dirigido na árvore o trecho de que o aceite depende e a fonte de uma prova, em vez de repetir a leitura integral do Checker. Para sondagem independente adicional, despache um verificador; não peça o parecer integral de volta ao seu contexto. Cobertura não conferida e parecer não lido por ninguém não viram aprovação.

Orquestre a verificação rigorosamente conforme a cadência do método: **"targeted early and throughout → canonical full integration gate only at major boundary"**.
- **Intragrupo (`verification_scope: targeted`):** durante a implementação e revisões de unidades dentro de um mesmo `integration_group` (Epic no BMAD, Deliverable no Native, agrupamento explícito ou Standalone), limite os testes aos módulos afetados, diff, consumidores diretos, ACs específicos e sondas contrafactuais. Não execute a suíte de integração global completa por rotina a cada tarefa.
- **Fronteira principal (`verification_scope: integration_boundary`):** dispare obrigatoriamente o `canonical_full_gate` configurado apenas no fechamento da unidade final do grupo de integração ou em Native Standalone Task, antes de autorizar a transição para o próximo grupo independente. O portão precisa terminar verde (sucesso, exit 0); falha no gate bloqueia terminantemente a transição. Se `canonical_full_gate` estiver como `not_configured` ou ausente, registre como pendência bloqueante e nunca infira comandos.
- **Invalidação estrita da árvore:** o resultado do `canonical_full_gate` é estritamente vinculado ao commit SHA verificado. Qualquer alteração posterior no código da árvore invalida a prova e exige nova execução antes da transição de fronteira.
- **Reaproveitamento de CI:** quando o CI externo já tiver executado o `canonical_full_gate` com sucesso sobre o mesmo commit SHA exato e sob a mesma definição/revisão do portão, com logs auditáveis, reaproveite essa evidência sem duplicar a execução local; se o código ou a definição do comando foi alterada após o CI, a prova anterior é nula.
- **Exceção antecipada (`verification_scope: exceptional_full`):** permitida estritamente para alterações estruturais transversais (ex.: esquema compartilhado de banco, protocolo cross-módulo, primitivas globais de concorrência, build system). Exige bloco formal `full_gate_exception` com razão técnica e justificativa objetiva; justificativas genéricas ("por segurança", "para garantir tudo", "para confirmar") são nulas e proibidas.
- **Retrabalho econômico (`changes_requested`):** re-execute testes estritamente no patch alterado, consumidores impactados e ACs pertinentes. Retrabalhos documentais, de evidência, metadados ou status não executam testes funcionais, admitindo no máximo verificações textuais (`git diff --check`, lint estrutural).

Derive a verificação dos riscos e contratos afetados, inclusive quem constrói ou consome tipos/configurações alterados. Execute os portões existentes definidos para a tarefa; uma alteração documental pode ser comprovada por inspeção, comparação de originais, referências e exportação. Não invente uma suíte de programação para validar documentos.

Um resultado de portão ou suíte só vale para a mesma revisão da árvore e a mesma definição do
portão: qualquer escrita posterior, mudança de comando, de escopo ou de ambiente invalida o
resultado anterior, que não é reaproveitado como prova. Quando um portão falhar, isole primeiro o
caso que falhou e execute-o dirigido; repita a suíte inteira depois de entender a falha, e uma vez
por revisão final. Repetir a suíte para ver se muda não é diagnóstico.

Antes do Checker, classifique a fase `review` pelo alcance do mecanismo, riscos e contraprovas
necessárias, não apenas pelo tamanho do diff. O Checker continua sempre em sessão nova, somente
leitura, e sua cadeia conserva a preferência publicada e a política de independência.

Quando a garantia depende de teste de comportamento, prove pessoalmente que ele discrimina o defeito por sonda prevista ou equivalente: confirme a alteração de fato, observe a falha esperada, recupere o conteúdo original e observe a passagem. Falha de compilação ou teste que não executou não prova discriminação. Use uma cópia isolada ou mecanismo seguro de restauração e confira o diff ao final, inclusive após interrupções.

## Medir e atribuir falhas

Mantenha a árvore estável durante portões. Serialize suítes e medições que disputam CPU, serviços, banco ou locks, inclusive entre worktrees. Verifique atividade e obtenha uma janela ociosa; não encerre processos alheios para fabricá-la.

Registre o comando literal, diretório, resultado e exit code real. Um pipe para filtrar saída pode esconder a falha do comando original: capture o resultado antes de resumir. Não deduza conclusão pelo nome de um log ou por uma mensagem citada nele.

Antes de chamar um vermelho de regressão, leia o teste e investigue o caminho causal, dependências e ambiente. Compare com a base apropriada sob condições equivalentes. A ausência de edição no arquivo que falhou não prova que a mudança é inocente. Se não puder atribuir, registre como não atribuído. Não repita indefinidamente até obter verde nem descarte amostras ruins.

Ao atingir o limite de rodadas ou turnos sem concluir, registre uma parada honesta: um checkpoint em disco com o estado alcançado, a evidência parcial e a causa observada, para reconciliação. Isso não é sucesso e não deve disparar sozinho um novo loop automático.

## Revisão externa

Esta seção e seu schema regem a revisão de entrega. As opiniões consultivas de
[Debater](#debater) seguem o formato próprio daquele modo e não têm valor de aprovação.

Entregue ao Checker o contrato, a intenção congelada, base, diff completo e evidências pertinentes. Não dirija sua primeira leitura para uma conclusão; memórias e relatos antigos entram apenas depois da inspeção independente das fontes atuais.

O briefing de revisão entregue ao Checker deve incluir obrigatoriamente os metadados de cadência de verificação:
- `verification_scope`: `targeted` | `integration_boundary` | `exceptional_full`
- `integration_group`: `{ authority: <bmad_epic | native_deliverable | native_standalone | explicit>, id: <id> }`
  A autoridade do grupo é resolvida semanticamente (Epic no BMAD, Deliverable no Native, ou Native Standalone Task como seu próprio grupo `authority: native_standalone, id: <Task_ID>`), sendo vedado parsing por regex sobre o identificador.
- Instrução explícita sobre o escopo: sob `verification_scope: targeted`, oriente claramente ao Checker que a verificação é focada no diff, consumidores impactados e ACs, e que a ausência de execução rotineira do `canonical_full_gate` intragrupo não constitui deficiência probatória, defeito ou motivo de reprovação. Sob `exceptional_full`, inclua o bloco formal `full_gate_exception`.

Preserve a resposta original do harness junto à evidência da tarefa. Se ele envolver o parecer
em um envelope de transporte, identifique seu campo final pela documentação ou pelo contrato
verificado do harness e registre o campo extraído. Metadados do envelope ficam fora do parecer.
Não procure um trecho que pareça aprovação no texto ou escolha um objeto entre vários por
conveniência.

O conteúdo extraído deve ser exatamente um objeto JSON. Tolere somente uma normalização de
transporte adicional: se a resposta final inteira, depois de remover espaço externo, for um único
bloco cuja linha de abertura seja formada por três crases seguidas de `json` e cuja linha de
fechamento tenha somente três crases, sem texto antes ou depois, retire exatamente essas duas
linhas e registre a normalização junto à resposta original. Não extraia blocos de prosa, não aceite
outro tipo de cerca, blocos múltiplos, cercas aninhadas, objetos concatenados (mesmo idênticos) ou
múltiplas respostas finais sem uma fonte canônica inequívoca. Não descarte campos, renomeie IDs ou
combine objetos para tornar válido um parecer inválido.

Confira a estrutura contra o [schema canônico](../schemas/review-result.schema.json) com
ferramenta existente, se disponível; sem validador, declare a conferência manual e sua limitação.
Sintaxe JSON não prova conformidade ao schema, e conformidade não prova correção do produto.
Conferência mecânica e vinculação por hash comprovam correspondência e integridade (o objeto e as
entradas conferidos são estes), não correção nem pertinência; pertinência ao workload, adequação do
esforço e alcance econômico são julgamento registrado, com quem julgou e sobre o quê. Campos extras
e inconsistência entre `verdict` e `action_items` também exigem correção pelo Checker. Enquanto o
parecer estiver ausente, inválido ou ambíguo, não o trate como aprovação. Faça no máximo uma
solicitação de correção de formato ao mesmo Checker, apontando os defeitos estruturais sem sugerir o
veredito. Se a nova resposta também for inválida, encerre essa revisão como `parecer válido não
obtido`; não repita até conseguir aprovação.

Atribua os achados: correção no escopo ao Maker, spec inconsistente ao Planner, decisão de intenção ao usuário. Registre trabalho fora do escopo sem corrigi-lo silenciosamente. Depois de mudança material, renove as provas afetadas e obtenha nova revisão independente da árvore final.

## Fechamento ou interrupção

Registre a evidência no artefato próprio da story: base/estado examinado, arquivos relevantes, critérios atendidos, comandos e exits, resultados de comparações/sondas, parecer e pendências. Declare separadamente o que foi observado, inferido e não verificado.

No perfil Native, o registro de revisão em `project/evidence/Tnnn-rNN.md` preserva o parecer
íntegro junto a `spec_revision`, `content_id`, `content_paths`, sessão, harness, modelo, effort,
família e limitações de independência. Toda chamada entra em `Agent runs`, e revisão de mesma família
sob `preferred` abre o bloco `## RF-<unit_id>-rNN` na evidência da unidade (e no artefato próprio da
story BMAD, sem Task Native duplicada), referenciado em `review_followups` do cabeçalho global,
conforme o [modelo de trabalho](../docs/WORK_MODEL.md#registro-de-revisão). Registrar o parecer e
atualizar o estado não alteram o `content_id`; alteração material em um caminho coberto exige nova
revisão. A Task só recebe `done` com portões executados, parecer `approved` vinculado ao `content_id`
e autoridade de fechamento já concedida; sob `preferred`, `done` é permitido com pendência aberta.
Um Deliverable só recebe `done` depois de verificar seus `integration_criteria`, listando
pendências abertas sem bloqueio. Quando a Task declarar `affects_context`, a atualização dos
Feature Briefs afetados faz parte do fechamento.

A revisão posterior é uma rodada nova `rNN`, em sessão nova, por família distinta de todas as
`families_used`, sobre o alvo registrado quando recuperável, ou sobre o conteúdo atual com pendência
substituta quando houver decisão registrada de substituição. Ela não autoriza corrigir uma Task
concluída:
- com autorização vigente que cubra o retrabalho, segue o fluxo normal: nova rodada, novo
  `content_id` e pendência substituta vinculada, nascendo `pending` ou `closed` conforme o parecer
  obtido sobre o novo alvo;
- sem autorização vigente, a pendência é preservada com o parecer em `attempts` e os achados entram
  na fila apropriada (Task `fix` ou `analysis` em `draft` na área responsável, ou referência à
  unidade BMAD existente), sem despachar implementação.

O resultado histórico da Task, a revisão posterior e a autorização para novas alterações ficam
estritamente separados.

Com autorização para integrar, confira o resultado da integração antes da próxima ação. Mudanças no conteúdo validado exigem nova conferência proporcional. Status concluído depende dos portões, revisão independente e autoridade local de ratificação; um verde isolado não fecha a story.

Se o pedido era somente planejamento, entregue o plano e encerre aí. Se houve interrupção, registre o ponto de retomada e preserve a árvore. A próxima sessão relê as fontes e o estado real; o registro ajuda a retomar, não executa continuidade por si só. Use um [checkpoint limitado](../docs/EXECUTION_PROTOCOL.md#contexto-por-papel) validado contra a árvore: resumo de conversa descreve o que foi dito, não o que existe no disco. No perfil Native, o encerramento normal grava `released: true` no registro `coordinator`, e a retomada começa pelo cabeçalho global, que aponta a unidade corrente mesmo quando ela pertence a um módulo, relê a unidade oficial e só então reconcilia cabeçalhos atrasados, na ordem unidade, projeções do módulo, visão global, aplicando a [tabela de recuperação](../docs/WORK_MODEL.md#transição-e-recuperação): tabela atrasada é reconstruída, referência ativa já concluída é reparada após conferir as evidências, unidade não encontrada é procurada antes de perguntar, e só estados incompatíveis ou evidência insuficiente interrompem a execução afetada.

### Próximos passos numerados

Ao fechar um ciclo ou devolver ao usuário uma decisão pendente, informe o resultado, o estado real
e os próximos passos pertinentes em lista numerada, com até três opções e no máximo uma marcada
como **Recomendado**. A regra vale em Native e BMAD, com ou sem módulos. Se não houver próximo
passo pertinente, informe isso sem inventar opções.

- Cada opção declara a ação concreta, o projeto e a unidade ou área quando aplicável, o escopo,
  os efeitos autorizáveis e o ponto de parada. Diferencie preparação, implementação, commit,
  push, PR, merge e release. Se houver chamadas a agentes, declare o teto do lote; correções,
  retomadas, fallback e consultas consomem esse mesmo teto, sem prometer conclusão dentro dele.
- Uma resposta do usuário contendo somente o número seleciona e autoriza exclusivamente a ação
  descrita naquela opção do último menu apresentado pelo Orquestrador. Registre essa origem
  conforme as regras de evidência e autoridade vigentes. Texto adicional do usuário delimita a
  escolha; ambiguidades materiais exigem esclarecimento antes da ação afetada.
- Na retomada, releia o menu e confira o estado real. Se o menu não estiver disponível, o número
  não existir ou houver mudança material que invalide o escopo da opção, apresente opções
  atualizadas em vez de inferir autorização. Não transporte a escolha para outra unidade.
- Apresentar ou recomendar uma opção não autoriza executá-la. Silêncio e passagem de tempo não
  selecionam opções. A escolha não dispensa classificação dos papéis aplicáveis, validações,
  coordenação, revisão nem permissões exigidas pelo método e pelo consumidor.
- Não interrompa uma fila ou lote já autorizado apenas para obter um número após cada Task.
  Continue as ações cobertas pela autorização vigente; solicite escolha apenas na condição de
  parada ou diante de uma decisão ainda não autorizada.
