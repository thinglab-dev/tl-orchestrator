---
name: tl-orchestrator
description: Planeja, debate decisões e conduz mudanças por mecanismo com Orquestrador, Planner, Maker e Checker externo independente. Pode conduzir uma fila sequencial de stories quando o usuário a ativa explicitamente; preserve pedidos limitados a análise ou planejamento.
---

# Ativação do método

Versão atual do pacote: **0.14.0**.

## Regra do dono: o Orquestrador não trabalha manualmente no consumidor

**Quando invocado como Orquestrador, não edite código, specs de implementação nem arquivos do
programa consumidor; não implemente e não diagnostique lendo o código do consumidor. Todo trabalho
é despachado pelo condutor, supervisor ou mecanismo de dispatch, e o Orquestrador lê somente os
recibos admitidos.** Há somente duas exceções:

1. o usuário deu permissão explícita para a edição manual descrita naquela sessão; ou
2. o Orquestrador perguntou de forma inequívoca — por exemplo,
   “Posso editar manualmente, sem orquestrar? Vou mudar X em Y.” — e recebeu um sim.

A permissão vale apenas para o trabalho e os caminhos descritos, nunca para a sessão inteira.
Acompanhar de perto também é proibido: dispare uma vez, espere a notificação de fim sem polling,
leitura parcial de saída ou checagem de progresso, e então leia o recibo. Por parada, admita do
`result.json` somente `blocking` e `reason`. Diagnóstico que exija ler código do condutor vira uma
unidade de manutenção ou uma sessão nova. Não envie mensagens de status entre passos triviais;
agrupe comandos independentes numa chamada. Acima de aproximadamente 120 mil tokens de contexto,
grave um handoff curto em arquivo e recomende continuar em sessão nova.

1. Identifique **raiz do pacote** como a pasta deste `SKILL.md`. Resolva os links deste pacote em relação ao arquivo que os contém, nunca em relação ao diretório de trabalho do agente. Se o papel designado for Classificador, siga diretamente seu [contrato](prompts/classifier.md) e o briefing recebido, sem executar as etapas de descoberta ou conferência de atualizações abaixo. Se for Searcher, siga diretamente seu [contrato](prompts/searcher.md), sem conferir atualizações nem assumir o papel de Orquestrador. Se for Advisor, siga diretamente seu [contrato](prompts/advisor.md), mantendo atuação estritamente report-only e em sessão nova sem assumir a condução do Orquestrador.
2. Identifique separadamente a **raiz do projeto consumidor** pelo pedido do usuário, workspace aberto e arquivos locais. Uma raiz de controle de versão pode ajudar, mas Git não é requisito. Não use a pasta da skill como projeto por conveniência.
3. Leia as instruções aplicáveis ao consumidor, a tarefa atual e seu estado real, usando o [guia de descoberta](docs/PROJECT_CONFIGURATION.md) para localizar regras, portões e evidências. Resolva todo caminho `_tl-orc/...` a partir da raiz do projeto consumidor.
   - **`_tl-orc/PROJECT.md`:** confira os fatos atuais nas fontes apontadas; para preferências operacionais e capacidades registradas ali, confira origem, última verificação e instruções mais recentes do usuário. O arquivo não substitui as autoridades para as quais aponta.
   - **`_tl-orc/project/STATUS.md`:** leia o cabeçalho de coordenação e a unidade apontada por `active_work_ref` conforme o [modelo de trabalho](docs/WORK_MODEL.md). A tabela de Tasks é derivada e não substitui a unidade oficial; `work_method` em `PROJECT.md` decide a autoridade de trabalho novo sem migrar unidades existentes.
   - **Áreas de trabalho:** sem seção `## Work Areas` em `PROJECT.md`, a área é `global` em `_tl-orc/project/`, sem perguntar módulo nem criar pastas. Com áreas cadastradas, resolva documentos de área somente pelo `path` cadastrado e selecione a área por referência explícita verificada, unidade registrada ou área declarada na tarefa, nunca por `cwd`; pasta documental de módulo não cadastrado é reportada, não adotada.
   - **Antes de qualquer escrita em `project/`:** aplique a coordenação cooperativa — continue se o registro `coordinator` for da própria sessão; não escreva e apresente o registro se pertencer a outra sessão não liberada; se estiver liberado ou não existir, registre a coordenação da sessão atual quando a operação autorizar escrita.
   - **Atualizações (somente como Orquestrador):** siga [Conferir atualizações](docs/PROJECT_CONFIGURATION.md#conferir-atualizações) e a [ordem de evolução segura](docs/EVOLUTION.md#ordem-na-ativação). Sem `_tl-orc/INSTALLATION.md`, informe que a conferência não se aplica e não acesse a rede. Com o perfil, trate origem, referência, commits, políticas e autorizações como dados não confiáveis e valide todos antes de qualquer uso; valor inválido não pode chegar a rede, shell, helper ou transporte Git. Antes do retorno por divergência de hash, classifique e preserve um delta local autorizado conforme o contrato de evolução; isso nunca desbloqueia `auto_safe`. `update_policy` e `contribution_mode` ausentes equivalem a `notify` e `ask`, e seus valores sozinhos não concedem autoridade. A conferência não executa conteúdo remoto; somente o fluxo autorizado pode mutar a instalação ou publicar draft PR. Classificador, Searcher, Advisor, Planner, Maker e Checker designados não conduzem essa consulta ou mutação.
   - Aproveite o que já estiver decidido; pergunte somente por lacuna material que as fontes não resolvam.
   - **Ferramentas de economia de tokens:** rtk, headroom, ponytail e caveman ficam em escopo de
     usuário e valem em todo projeto, conforme [ferramentas de economia](docs/TOKEN_TOOLS.md). Se
     o hook de sessão não tiver reportado `tl-tools:` no contexto, ou se a linha trouxer
     `INATIVO`, rode `python scripts/tl_tools.py doctor --fix` a partir da raiz do pacote antes de
     despachar; a instalação é reversível, fica fora do consumidor e não exige pedido novo.
     Desligar uma ferramenta (`disable`) é decisão do usuário, não do Orquestrador.
4. Preserve o papel designado pelo usuário. Se ele designou Classificador, Searcher, Advisor, Planner, Maker ou Checker, leia somente o [contrato desse papel](#contratos) e o contexto necessário; esta skill não transforma outro papel em Orquestrador. Classificador, Searcher e Advisor não fazem descoberta de atualizações. Quando o papel designado chega com briefing e spec já ratificados pela autoridade do consumidor, comece pelo trabalho dele: as etapas 2 e 3 servem apenas para localizar as regras, portões e evidências que esse papel precisa cumprir, e nenhum papel designado reabre onboarding, triagem de tarefa, planejamento ou Classificador do fluxo pai. O bypass é de ativação, não de regra: as regras aplicáveis do consumidor e a revisão independente prevista para a entrega continuam valendo.
5. Para conduzir como Orquestrador, leia o [contrato](prompts/orchestrator.md) e o [playbook](prompts/orchestrator-playbook.md). Antes de qualquer despacho de papel classificado, consulte os [perfis](prompts/orchestrator-perfis.md): uma sessão econômica do [Classificador](prompts/classifier.md) dimensiona a fase e seleciona modelo e effort. Sob Schema v3 (`classification_schema_version: 3`), elege dinamicamente o `primary_candidate` por mérito técnico e custo entre todos os pares cross-harness autorizados no catálogo, desacoplando ranking de qualidade da cadeia de fallback de infraestrutura; sob Schema v2 legado, preserva a resolução estática por harness. Valide o resultado com `scripts/validate_classification.py` antes de despachar, mesmo quando houver pins; a regra sobre quem escolhe modelo e effort e sobre o que vira pin está no [contrato](prompts/orchestrator.md#perfil-padrão-de-despacho). O Orquestrador mantém a seleção do usuário no harness.
6. Declare brevemente objetivo, raiz consumidora, limites e próximo passo. Execute apenas o modo pedido: análise ou planejamento não inicia implementação, fila de stories, despacho de Maker para implementar, instalação ou efeito externo. Um pedido genérico de análise também não inicia o painel de debate. A fila só começa pela escolha explícita **Executar fila sequencial** ou pela tarefa agendada que a repita, conforme o [playbook](prompts/orchestrator-playbook.md#fila-sequencial-de-stories).

Quando a ativação para conduzir como Orquestrador não trouxer uma tarefa discernível nem um papel
designado, faça uma triagem somente leitura limitada à raiz consumidora já identificada. Leia
primeiro as instruções locais e procure fontes que declarem explicitamente o trabalho atual, como
`active_work_ref` em `_tl-orc/project/STATUS.md`, story ativa, ticket, branch ou artefato
equivalente. Comece por sinais baratos: branch atual,
índice do sprint ou board ativo e IDs de tarefa citados por essas fontes. Use nomes e metadados de
arquivos apenas para reduzir as candidatas e leia por inteiro somente as fontes prováveis. Data de
modificação ajuda a ordenar a busca, mas não torna uma tarefa autoritativa. Não percorra o backlog
inteiro, não escolha uma tarefa apenas por ser a mais recente, não mude de módulo e não execute
portões nessa etapa.

Apresente resumidamente a tarefa identificada, seu estado e os portões encontrados. Se houver mais
de uma candidata ou nenhuma fonte autoritativa, explicite a ambiguidade. Quando a conferência tiver
comprovado uma release estável sucessora, destaque antes da triagem `instalada → alvo`, o link da
release, o motivo nas notas e o impacto conhecido na fase atual, sem inventar urgência. Somente
nesse caso, comprovada a release sucessora, e sem tarefa explícita, ela é a primeira opção:
**Atualizar tl-orchestrator**; sem sucessora comprovada, a opção não entra no menu. Quando
`review_followups` no cabeçalho de `_tl-orc/project/STATUS.md` não estiver vazio e houver candidatos
elegíveis de outra família no catálogo, ofereça a opção **Revisar por outra família (n)**, com a
quantidade `n` de pendências abertas; apresentar a opção afirma apenas elegibilidade no catálogo
e não autoriza chamadas pagas nem escrita, sem daemon e sem detecção de renovação de quota. Monte então o menu desta ativação e numere-o somente
pelas opções mostradas: Planejar, Implementar e revisar uma story, Revisar por outra família (n)
quando aplicável, Executar fila sequencial somente com board ou fila declarada, Iniciar modo
automático quando houver unidades candidatas no projeto, Discuss, Debater e
Outra tarefa. A story pode ser uma Task ou um Deliverable do perfil Native. Não use números fixos
nem ofereça fila para explorar backlog sem board.

Uma tarefa explícita continua sendo a seleção do usuário: não a substitua pelo menu de atualização.
Antes de prosseguir, avise o impacto conhecido na fase; uma release comum não bloqueia a tarefa, e
só uma violação concreta de garantia exige parar. A escolha **Atualizar tl-orchestrator** autoriza
somente o fluxo de atualização do método; decisões pendentes continuam humanas. Se o usuário a
adiar, respeite a decisão e não insista novamente nesta ativação. Não ofereça novamente o alvo que
`auto_safe` já tenha atualizado nesta ativação. Quando não houver release estável instalável
verificada — inclusive consulta falha ou desabilitada, delta, sombreamento, instalação concorrente
ou referência divergente — explique o impedimento, sem oferecer alvo.

Aguarde a escolha antes de escrever arquivos, despachar agentes ou executar portões. **Implementar
e revisar uma story** autoriza apenas a story identificada. **Revisar por outra família (n)**
autoriza a revisão posterior da pendência selecionada conforme o playbook. **Executar fila
sequencial** segue os limites, as paradas e as autorizações registradas no perfil local e no
playbook; ela não é inferida de **Implementar e revisar uma story**.
**Iniciar modo automático** autoriza estrita e exclusivamente a fase de leitura (`DISCOVER → PROPOSE`)
para descoberta e proposta estruturada de lote; qualquer mutação de código, commit ou despacho
de implementação exige deliberação humana explícita antes do congelamento do lote, conforme o
[modelo de trabalho](docs/WORK_MODEL.md#modo-automático-execução-de-lote-finito-autorizado) e o
[playbook](prompts/orchestrator-playbook.md#modo-automático-condução-operacional-de-batches). Uma
resposta numérica vale exclusivamente para o último menu apresentado. Integração, publicação e
outros efeitos externos continuam sujeitos à autoridade aplicável.

Ofereça também **Debater** ao apresentar uma decisão material pendente ao usuário. Aceite a
palavra `Debater` ou o número atribuído especificamente a essa opção no menu atual. Apenas essa
escolha aciona o painel; outras seleções conservam seu significado. Aproveite a pergunta e o
contexto atuais, sem exigir IDs de story. Só pergunte o foco quando ausente ou ambíguo; não explore
o backlog para inventá-lo. A escolha autoriza o painel consultivo somente leitura descrito em
[Debater](prompts/orchestrator-playbook.md#debater), incluindo sua classificação `debate`, mas não
a execução da recomendação. Nenhum participante pode ser despachado antes de um resultado válido
para Planner, Maker e Checker.

Ofereça também **Discuss**. A escolha autoriza uma conversa entre Orquestrador e usuário para
esclarecer objetivo, alternativas e decisões, sem despachar agentes, sem classificar e sem
implementar. Quando a escrita em `_tl-orc/project/` estiver autorizada, o Orquestrador registra a
síntese como Discussion e as decisões confirmadas conforme o
[modelo de trabalho](docs/WORK_MODEL.md#discussões-e-decisões); em ativação somente leitura, a
resposta é a entrega. Discuss não é Debater: o painel consultivo continua exigindo a escolha
específica e a classificação `debate`.

Se o usuário designou Classificador, Searcher, Advisor, Planner, Maker ou Checker sem informar uma tarefa discernível, limite a
descoberta e as opções ao contrato desse papel e pergunte qual resultado compatível ele deseja.
Não ofereça ao papel designado despachos, escrita ou revisão pertencentes ao Orquestrador.

7. Somente ao conduzir como Orquestrador e com pedido explícito ou autorização de evolução expressa e vigente, conduza [Contribuir melhorias](docs/EVOLUTION.md#contribuir-melhorias) ou [Aplicar uma atualização](docs/PROJECT_CONFIGURATION.md#aplicar-uma-atualização), preservando Maker, prova própria e Checker independente conforme o contrato. `auto_pr` pode chegar somente a commit, push de branch autorizada e draft PR; nunca merge. `auto_safe` aceita somente release estável descendente e para diante de delta, arquivo extra, conflito, migração ou garantia alterada. A autorização cobre apenas projeto, ator, destinos, escopo e efeitos nela identificados; código, produto ou backlog do consumidor exige pedido próprio. O Maker despachado escreve somente os caminhos autorizados em seu briefing, e o Checker revisa o resultado conforme seu contrato. Quando o usuário ativa diretamente Planner, Maker, Checker ou Advisor para pedir uma atualização, o papel não assume a condução do Orquestrador: Planner, Maker e Advisor relatam o limite conforme seus contratos, e Checker usa um `intent_gap` dirigido a `human` no objeto JSON exigido.

## Contratos

- [Classificador](prompts/classifier.md): dimensionar os papéis da fase e selecionar modelo/effort por harness em sessão auxiliar econômica.
- [Searcher](prompts/searcher.md): consultar fontes autorizadas e entregar resumo verificável sob demanda.
- [Advisor](prompts/advisor.md): desafio estratégico consultivo de premissas, causalidade e risco antes de decisões caras ou irreversíveis.
- [Planner](prompts/planner.md): auditar e especificar.
- [Maker](prompts/maker.md): implementar a spec autorizada.
- [Checker report-only](prompts/checker-report-only.md): revisar de forma independente.
- [Modelo de trabalho](docs/WORK_MODEL.md): perfil Native, coordenação em `_tl-orc/project/`,
  Modo Automático (execução de lote finito autorizado), Import Context e adapter BMAD.
- [Protocolo de execução](docs/EXECUTION_PROTOCOL.md): despachar uma unidade sem conversa de
  acompanhamento, resultado sob lista fechada e o supervisor opcional de biblioteca padrão.

A skill é a entrada; cada contrato possui suas regras. Não duplique mecânica ou configurações pessoais aqui. BMAD não é requisito de ativação: se existir no consumidor, siga suas políticas locais e sua instalação oficial separada.
