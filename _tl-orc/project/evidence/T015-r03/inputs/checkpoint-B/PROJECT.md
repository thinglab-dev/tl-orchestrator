format_version: 1
work_method: bmad

routing_mode: classifier

## Fontes autoritativas

| Tipo | Localização | Uso | Última conferência |
| :--- | :--- | :--- | :--- |
| Instruções gerais | `AGENTS.md` | ambiente, segurança, BMAD, orquestração e formato de status | conteúdo lido em 2026-09-04 |
| Instruções do Claude | `CLAUDE.md` | regras do harness e fluxos BMAD/WDS | conteúdo lido em 2026-09-04 |
| Política BMAD | `docs/BMAD_POLICY.md` | autoridade e fluxo quando uma tarefa BMAD/WDS for ativada | caminho conferido em 2026-09-04; reler na ativação |
| Decisões compartilhadas | `PLATFORM_DECISIONS.md` | decisões arquiteturais do Platform | caminho conferido em 2026-09-04; reler conforme a tarefa |
| Modelo de negócio | `BUSINESS_MODEL.md` | planos, limites, hosting, placement e preço | caminho conferido em 2026-09-04; reler antes de alterar esses assuntos |
| Regras visuais | `docs/DESIGN_SYSTEM.md` | decisões compartilhadas de interface | caminho conferido em 2026-09-04; reler quando aplicável |
| Arquitetura Go | `docs/GO_ARCHITECTURE.md` | criação, exportação e movimentação de pacotes Go | caminho conferido em 2026-09-04; reler quando aplicável |
| Trabalho BMAD | `modules/<módulo>/_bmad-output/` | sprint, stories e artefatos do módulo escolhido | descobrir novamente por tarefa; nunca usar outro módulo como fila |

## Portões

| Portão | Diretório | Origem/condição |
| :--- | :--- | :--- |
| `make dev-check` | raiz do Platform | portão geral definido por `AGENTS.md` para mudanças de código |
| `make bmad-sync MODULE=<módulo>` | raiz do Platform | obrigatório antes do corpo principal de um fluxo BMAD/WDS |
| Portões da story ou do módulo | diretório indicado pelo artefato | descobrir e executar conforme a tarefa ativa |
| comparação byte a byte, conjunto exato de 17 arquivos e SHA-256 | raiz do Platform | instalação ou atualização de `_tl-orc/package` |
| `git diff --check` e inspeção de referências vivas | raiz do Platform | mudanças documentais e de integração do método |

## Modelo de trabalho

`work_method: bmad`: a autoridade sobre stories e epics permanece nos artefatos BMAD de cada
módulo (`modules/<módulo>/_bmad-output/`), conforme `docs/BMAD_POLICY.md`. Nenhuma unidade BMAD foi
migrada para o perfil Native. `_tl-orc/project/` existe desde 2026-09-07 apenas como coordenação
global (cabeçalho, sem Tasks); as Tasks Native existentes pertencem à área `lynvia-mkauth-connector`
e não transferem autoridade sobre stories. Trabalho Native no Platform exige seleção explícita por unidade.

A v0.5.0 instalada acrescenta a revisão posterior por outra família: sob `checker_independence:
preferred`, revisão de mesma família em sessão nova abre pendência na evidência da unidade, listada em
`review_followups` do cabeçalho global, e a ativação oferece "Revisar por outra família (n)". Este
consumidor passou a `preferred` em 2026-09-07 por autorização do usuário; o fallback de Checker para a
mesma família e a pendência de revisão posterior aplicam-se conforme o contrato; identidade completa
de unidade, tabela `Agent runs`, `run_id` e `review_followups` valem para os registros daqui em diante. A v0.6.0 (instalada em 2026-09-08) consolida as regras de condução
(escalonamento consultivo, procedência por entrada nos briefings, limite das provas mecânicas, escopo de
leitura confinado) e classifica o Searcher; neste consumidor só a linha do Searcher em "Preferências
operacionais" mudou. Desde a v0.4.0 o pacote suporta áreas de trabalho por módulo via seção `## Work Areas` deste arquivo,
com projeto sem módulos como padrão. Uma área está cadastrada em `## Work Areas` (lynvia-mkauth-connector, para o piloto de Import
Context); os demais módulos ficam na área `global` implícita até cadastro explícito.

## Work Areas

| area_id | path | work_method | status_source | evidence |
| :--- | :--- | :--- | :--- | :--- |
| lynvia-mkauth-connector | modules/lynvia-mkauth-connector/_tl-orc/project | bmad | modules/lynvia-mkauth-connector/_bmad-output/implementation-artifacts/sprint-status.yaml | modules/lynvia-mkauth-connector/_tl-orc/project/evidence |

Cadastro em 2026-09-07 por operação explícita do usuário para o piloto de Import Context do
epic-1. `global` é implícita em `_tl-orc/project/`. Validação no cadastro: `area_id` único;
`path` não sobrepõe `_tl-orc/project`, `_tl-orc/package` nem integrações de skill; caminho relativo
à raiz. Demais módulos permanecem sem cadastro até decisão posterior. A autoridade sobre stories e
epics do módulo continua no BMAD (`work_method: bmad`); trabalho Native na área exige seleção
explícita por unidade.

## Preferências operacionais

| Papel | Harness preferido | Modelo/família | Capacidade e permissões observadas | Origem | Última conferência |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Orquestrador | agente no qual a skill foi ativada | modelo atual não exposto; família OpenAI GPT nesta sessão | Codex Desktop com leitura, escrita e execução no workspace | preferência padrão aceita pelo usuário e sessão atual | 2026-09-04 |
| Planner | Claude | família Anthropic; modelo confirmado no despacho | CLI Claude Code `2.1.257` disponível; autenticação e modelo só se comprovam no despacho | perfil-padrão v0.1.5 e preferência declarada pelo usuário | 2026-09-05 |
| Maker | Codex | `gpt-5.6-terra` preferido; família OpenAI GPT | CLI Codex `0.152.0` autenticada; `gpt-5.6-terra` e `gpt-5.6-luna` funcionaram em sessões somente leitura, enquanto o default local `gpt-6-astra` exigiu CLI mais nova. Luna é fallback somente com autorização explícita do usuário. | perfil-padrão v0.1.5, preferência declarada pelo usuário e sessões locais conferidas | 2026-09-05 |
| Checker report-only | Agy/Antigravity | `gemini-3.1-pro-high` preferido; família Google Gemini | CLI Agy `1.1.26` autenticada e modelo listado; usar sessão independente e sem escrita | perfil-padrão v0.1.5 e preferência declarada pelo usuário | 2026-09-05 |
| Searcher sob demanda | Agy/Antigravity (cadeia por omissão Agy → Claude → Codex) | modelo e effort escolhidos pelo Classificador (papel `searcher`, classificação da fase ou pin explícito; v0.6.0); `gemini-3.8-flash-medium` permanece capacidade observada e restrição conservadora de entrada, não pin | auxiliar de consulta em sessão nova, sem escrita; não decide, implementa, aprova ou despacha; consulta inicial começa pela classificação da fase com o papel searcher | perfil-padrão v0.6.0 e capacidade observada em 2026-09-05 | 2026-09-08 |

O pedido atual do operador autoriza corrigir a adoção operacional do Classificador. A tabela
anterior contém preferências e observações históricas, não recomendações novas nem prova de
capacidade atual. Preserve Terra e Gemini 3.1 como restrições conservadoras enquanto a origem
"perfil-padrão e preferência declarada" não for reconciliada; não elimine uma escolha explícita
por inferência. Essas restrições NÃO dispensam a chamada ao Classificador, inclusive em Debater.

O Orquestrador conserva a seleção atual do usuário. O Classificador usa sessão auxiliar separada:
Codex `gpt-5.6-luna` / `medium` → Claude `sonnet` / `medium` → Agy
`gemini-3.8-flash-medium` / `medium`, em fallback sequencial, após conferir capacidade e aliases.
Planner conserva Claude → Codex → Agy; Maker Codex → Claude → Agy; Checker Agy → Claude → Codex;
Searcher Agy → Claude → Codex (cadeia por omissão publicada na v0.6.0). Escalonamento consultivo após
N rodadas de rework com achados centrais da mesma classe: N = 3 (padrão publicado; não fixado localmente).
Política de independência: `checker_independence: preferred`, autorizada pelo usuário em 2026-09-07 (antes `required`): priorize Checker de família distinta de toda autoria efetiva; só com indisponibilidade comprovada das famílias distintas admita a mesma família em sessão nova, registrando `same_family_fresh_session` e abrindo a pendência de revisão posterior na evidência da unidade (`review_followups` no cabeçalho global). O pin do Checker registrado em "Escolhas fixadas pelo usuário" permanece; a mudança de política não altera pins nem catálogo.


### Escolhas fixadas pelo usuário em 2026-09-07 (origem: instrução do usuário, prevalece sobre o perfil)

| Papel | Harness | Modelo / effort | Escopo | Motivo |
| :--- | :--- | :--- | :--- | :--- |
| Maker | Agy/Antigravity | `gemini-3.8-flash-high` (effort high embutido no ID) | Tasks Native a partir de `lynvia-mkauth-connector:T004` | avaliar o Gemini em implementação real com pouco retrabalho e preservar quota Codex. Evidência em 2026-09-07 (T004, análise): favorável; não demonstra equivalência geral em implementação de código. Preferência mantida pelo usuário, sujeita à classificação por fase e ao catálogo permitido |
| Checker report-only | Claude (família) | modelo e effort escolhidos pelo Classificador dentro do catálogo Claude (`sonnet` ou `claude-opus-5`, efforts medium/high), por instrução do usuário em 2026-09-07: não fixar modelo por suposição; a única restrição é família independente dos Makers efetivos (Agy Gemini e Codex GPT) em sessão nova | idem | independência e dimensionamento por risco/custo, não por palpite |

Esses pins são restrições de entrada do Classificador e não dispensam sua chamada. `gemini-3.8-flash-high` entra no catálogo permitido para Maker por esta instrução; capacidade observada no smoke da v0.4.0 (Agy `gemini-3.8-flash-medium` como Orquestrador e `gemini-3.1-pro-high` como Checker); o par `high` ainda sem medição local.

## Catálogo permitido

Monte o recorte por despacho a partir das preferências acima e das capacidades verificadas do
harness: Codex Terra para Maker e Luna para Classificador; Claude da família Anthropic com ID
concreto e efforts a confirmar; Agy Gemini 3.1 Pro high para Checker e Flash 3.8 medium para
Classificador/Searcher. Essa enumeração não comprova disponibilidade, aliases nem todos os pares
de effort e não autoriza ampliar permissões ou orçamento. Registre pares válidos, fontes e
limitações atuais antes da chamada; capacidade desconhecida bloqueia a resolução, não permite
herdar defaults. Alternativas de trabalho além das restrições conservadoras exigem reconciliação
da preferência; `null`/`null` representa ausência de candidato adequado conforme o contrato.

## Classificação e despacho

Antes de qualquer participante de Debater, obtenha e valide resultado versão 2 com `phase: debate`
e `roles` exatamente `planner`, `maker`, `checker`. Registre story, revisões de contexto/catálogo/
contrato, pins, tier, recomendação e evidências; depois resolva disponibilidade e independência.
Passe modelo e effort explicitamente, confira o par efetivo e registre sessão e ordem. Ausência
de resultado válido bloqueia o painel inteiro. Não execute diretamente os modelos da tabela nem
herde `max` da CLI. Consulte os contratos em `_tl-orc/package/prompts/orchestrator-perfis.md`.

## Adoção operacional

As três cópias de 17 arquivos da release `v0.6.0` foram comparadas byte a byte com o commit
`f7739bd83ac458c9865df9d0a774c3062ef57fdf` em 2026-09-08: `synchronized`. Fresh load somente leitura por
harness na v0.6.0 (Codex pelo destino `.agents/skills`, Claude Code por `.claude/skills`, Agy pela
cópia canônica): os três leram versão e commit instalados, `work_method`, a área cadastrada e
`review_followups: []`, e resolveram por leitura a consulta inicial ao Searcher exatamente como a
v0.6.0 prevê (cadeia por omissão Agy → Claude → Codex; modelo e effort pelo Classificador; classificação
da fase com o papel `searcher` antes do despacho), sem executá-la e sem escrever. Repetição dos smokes de
roteamento pendentes (Task T001) na v0.6.0: instalação e fresh loads concluídos; bloqueios conformes
observados; roteamento completo ainda não comprovado — classificação estruturalmente inválida no Claude
Code (bloqueio correto, correção única com `-m` e effort, nenhum despacho; o fluxo parou antes dos
despachos, então o trecho que na v0.5.0 aceitava candidatos inválidos não foi exercitado; preparação do
briefing a tratar, esqueleto literal ausente como causa candidata, T002 do fonte) e resposta
indeterminada do harness aninhado no Codex (saída vazia tratada como `unknown`, sem fallback proibido,
briefing com procedência por entrada; limitação nas condições concretas das tentativas, sem demonstrar
impossibilidade geral). Estados após a execução autorizada da spec s2 da Task T002 (20260908T135658Z; evidência `_tl-orc/evidence/tl-orchestrator-t002-working-tree-20260908T134328Z-r02.md`; revisão externa aprovada na retomada autorizada de 2026-09-08; Codex em andamento no mesmo lote):
Claude Code `operational_verified` no alcance consultivo (fase debate), com parecer aprovado da revisão externa obtido na retomada (Checker Agy gemini-3.1-pro-high, conversa d8a381d9-f5b6-4eed-a02f-7e01c5842204): briefing do Classificador
transcrito literalmente de arquivo, classificação de Luna válida na primeira resposta e aceita pelo gate
mecânico com expectativas derivadas da solicitação (story_id nulo; um candidato por harness; catálogo por
papel; pin do Maker; sem null/null), três despachos consultivos em ordem com modelo e effort explícitos e
Checker de família distinta do Maker efetivo; o ciclo com Maker escrevendo continua não exercitado. Codex
`operational_verified` proposto no alcance consultivo, condicionado ao parecer da revisão da rodada de retomada
(registrado na evidência): classificação válida reaproveitada nas condições de reuso (Classificador Claude
aninhado após indisponibilidade literal do Codex aninhado), três despachos em primeiro plano com janela longa,
Maker com fallback autorizado (Codex aninhado indisponível → Claude) e Checker Agy de família distinta;
parecer aprovado da revisão desta rodada (Checker Agy 526ef1cf-bfef-4fed-8754-103dfd9f976c); em todas as tentativas
e condições desta Task, o Codex aninhado não iniciou sob o sandbox do Codex (erro literal do app-server); isso
não demonstra impossibilidade em outras configurações do sandbox nem justifica descartar o candidato de forma
permanente — próxima verificação, se e quando autorizada, deve tentar sandboxes ou configurações distintas antes
de tratá-lo como indisponível por definição. Agy `operational_verified`
(inalterado). Regras mantidas: conferência de árvore com não rastreados antes e depois de cada execução;
permissões efetivas do harness verificadas; correção única do Classificador aninhado em sessão nova quando
`--resume` não existir no ambiente. O Checker desta atualização foi o Gemini
3.1 Pro, conforme o catálogo; migrar o papel para Astra ou avaliar o Gemini 3.8 é alteração explícita
do perfil. Divergência menor: Claude Code ofereceu "Debater" sem
decisão material pendente no fresh load. Sessões, tempos e achados na evidência da atualização v0.6.0.

Histórico v0.5.0: as três cópias de 17 arquivos da release `v0.5.0` foram comparadas byte a byte com o commit
`f1528f699f3d20369ff3fc1043f7b5102ab8a134` em 2026-09-07: `synchronized`. Fresh load somente leitura por
harness na v0.5.0 (Codex pelo destino `.agents/skills`, Claude Code por `.claude/skills`, Agy pela
cópia canônica): os três leram versão e commit instalados, `work_method`, a área cadastrada e
`review_followups: []`, decidiram pelo SKILL.md que a opção "Revisar por outra família" não entra
e nada escreveram: `operational_verified` para o alcance desta release (fresh load, leitura do campo
novo e decisão do menu). Smoke operacional do roteamento repetido na v0.5.0 em 2026-09-07, porque a release altera
instruções de despacho, disponibilidade e independência: pergunta sintética sem efeito de produto,
Classificador em sessão auxiliar validado estrutural e semanticamente contra este catálogo antes do
primeiro despacho, três despachos consultivos somente leitura com modelo e effort explícitos e
carimbos UTC em ordem, Checker de família distinta do Maker efetivo. Agy
`operational_verified` (primeiros candidatos das três cadeias, sem fallback; verificado em modo plan
com aprovação automática). Claude Code: `synchronized`; roteamento `operational_pending`. Primeira rodada: correção do
Classificador produzida por `gpt-6-astra` (resume sem `-m`), fora do perfil; repetição com `-m` e
effort no resume (conforme) aceitou um par de Maker fora do catálogo (`codex/gpt-5.6-luna`) e o
despachou. Codex: `synchronized`; roteamento `operational_pending`. Primeira rodada: avanço sobre
saída vazia do `claude -p` aninhado, fallback não autorizado; repetição respeitou a tabela de estados
(Luna indisponível com erro literal → Claude adotado), mas o briefing do Classificador não trouxe
cartões do MODEL_ROUTING e fabricou identificadores de evidência. A prova de fresh load continua
válida nos dois. Causa comum: validação semântica da classificação pelo Orquestrador em effort medium
(achado T009 no repositório fonte). Pendências: Task Native `T001` da área global deste consumidor e T006–T008
no repositório fonte. Divergências menores: o Agy ofereceu Debater sem decisão
pendente no fresh load e executou um `find` fora da raiz consumidora. Sessões, tempos e achados
na evidência da atualização v0.5.0.

Histórico v0.4.0: as três cópias da release `v0.4.0` foram comparadas byte a byte com o commit
`0ed2df4c7abf65f3088a9fb5bb4f2bf00d378d6f` em 2026-09-06: `synchronized`. O estado por harness após essa
sincronização está registrado na evidência da atualização v0.4.0.
Fresh load e smoke operacional do roteamento em 2026-09-06 após a v0.4.0, por harness, com
Classificador em sessão auxiliar antes do primeiro despacho, validação estrutural e semântica contra
este catálogo, e três despachos consultivos somente leitura com modelo e effort explicitamente
transmitidos em cada comando e Checker de família distinta: Claude Code `operational_verified`;
Agy `operational_verified` após repetição estritamente sequencial com carimbos de tempo por passo (o
caminho headless com permissões padrão continua negando leituras; verificado em modo plan com aprovação
automática); Codex `operational_verified` com limitações: o sandbox do Codex
não inicia `codex exec` aninhado nem localiza sessões Claude para `--resume`, então Classificador e
Maker percorreram a cadeia por fallback documentado. Alcance: roteamento consultivo; o ciclo completo
de uma unidade com Maker escrevendo não foi exercitado. Sessões, tentativas e achados operacionais na
evidência da atualização v0.4.0.

A preferência por Agy não comprova sozinha a independência. Antes de cada revisão, o
Orquestrador registra o modelo e a família efetivos e escolhe um Checker de família distinta do
Maker. A CLI Gemini `0.46.0` também foi observada, mas não constitui fallback autorizado ou
autenticado por si só.

## Fila sequencial

Nenhuma fila está habilitada neste momento e não há heartbeat ou cron configurado. A v0.1.5 permite
criar `_tl-orc/QUEUE.md` para processar uma story por ativação com Planner Claude, Maker Codex e
Checker Agy; a configuração precisa primeiro declarar um único módulo, o board autoritativo, uma
árvore dedicada e os efeitos locais permitidos. As decisões pendentes e os boards de módulos não
podem ser escolhidos por inferência nesta configuração compartilhada.

## Defeitos do método

Um possível defeito do `tl-orchestrator` segue o procedimento da cópia instalada em
`_tl-orc/package/docs/PROJECT_CONFIGURATION.md#relatar-defeito-do-método`. O Checker somente o
registra com evidência; o Orquestrador pode preparar um rascunho sanitizado no artefato da tarefa
quando esse registro local estiver no escopo. Quando a falha for clara, reproduzível e delimitada,
um pedido explícito para preparar correção permite somente patch revisável no checkout fonte
isolado, em branch que não seja `main`, e rascunho local de pull request. Não altera o Platform,
`_tl-orc/package` ou as integrações. Buscar duplicatas requer pedido explícito e é somente leitura;
commit, push, criação ou atualização de pull request e abertura de issue em
`thinglab-dev/tl-orchestrator` requerem autorização explícita e específica do usuário. A suspeita
não autoriza workaround, patch no Platform, desativação ou outra alteração local.

## Evidências

Tarefas BMAD registram evidências no artefato da própria story e no local exigido pelo módulo.
Mudanças do método sem story usam `_tl-orc/evidence/`. O registro desta instalação está em
`_tl-orc/evidence/tl-orchestrator-installation-working-tree-20260905T004851Z-r01.md`; a
atualização de relato de defeitos está em
`_tl-orc/evidence/tl-orchestrator-method-defect-reporting-working-tree-20260905T011013Z-r01.md`; a
atualização do fluxo de correção por pull request está em
`_tl-orc/evidence/tl-orchestrator-method-pr-working-tree-20260905T014040Z-r01.md`; a
inclusão da opção Debater está em
`_tl-orc/evidence/tl-orchestrator-debate-working-tree-20260905T021754Z-r01.md`; a atualização do
perfil-padrão e da fila sequencial está em
`_tl-orc/evidence/tl-orchestrator-queue-defaults-working-tree-20260905T030125Z-r01.md`; a
evidência da atualização v0.2.1 é
`_tl-orc/evidence/tl-orchestrator-v0.2.1-working-tree-20260905T235140Z-r01.md`; a evidência da
atualização para `main@1e68982` é `_tl-orc/evidence/tl-orchestrator-main-1e68982-working-tree-20260906T144259Z-r01.md`; a
evidência da atualização v0.3.0 é `_tl-orc/evidence/tl-orchestrator-v0.3.0-working-tree-20260906T172052Z-r01.md`; a
evidência da atualização v0.4.0 é `_tl-orc/evidence/tl-orchestrator-v0.4.0-working-tree-20260906T232811Z-r01.md`.
