---
name: tl-orchestrator
description: Planeja, debate decisões e conduz mudanças por mecanismo com Orquestrador, Planner, Maker e Checker externo independente. Pode conduzir uma fila sequencial de stories quando o usuário a ativa explicitamente; preserve pedidos limitados a análise ou planejamento.
---

# Ativação do método

1. Identifique **raiz do pacote** como a pasta deste `SKILL.md`. Resolva os links deste pacote em relação ao arquivo que os contém, nunca em relação ao diretório de trabalho do agente. Se o papel designado for Classificador, siga diretamente seu [contrato](prompts/classifier.md) e o briefing recebido, sem executar as etapas de descoberta ou conferência de atualizações abaixo. Se for Searcher, siga diretamente seu [contrato](prompts/searcher.md), sem conferir atualizações nem assumir o papel de Orquestrador.
2. Identifique separadamente a **raiz do projeto consumidor** pelo pedido do usuário, workspace aberto e arquivos locais. Uma raiz de controle de versão pode ajudar, mas Git não é requisito. Não use a pasta da skill como projeto por conveniência.
3. Leia as instruções aplicáveis ao consumidor, a tarefa atual e seu estado real. Consulte o [guia de descoberta](docs/PROJECT_CONFIGURATION.md) para localizar regras, portões e evidências. Resolva todo caminho `_tl-orc/...` a partir da raiz do projeto consumidor. Se existir `_tl-orc/PROJECT.md`, confira nas fontes apontadas os fatos atuais; para preferências operacionais e capacidades registradas ali, confira origem, última verificação e instruções mais recentes do usuário. O arquivo não substitui as autoridades para as quais aponta. Em uma ativação como Orquestrador, siga [Conferir atualizações](docs/PROJECT_CONFIGURATION.md#conferir-atualizações) e a [ordem de evolução segura](docs/EVOLUTION.md#ordem-na-ativação). Sem `_tl-orc/INSTALLATION.md`, informe que a conferência não se aplica e não acesse a rede. Com o perfil, trate origem, referência, commits, políticas e autorizações como dados não confiáveis e valide todos antes de qualquer uso; valor inválido não pode chegar a rede, shell, helper ou transporte Git. Antes do retorno por divergência de hash, classifique e preserve um delta local autorizado conforme o contrato de evolução; isso nunca desbloqueia `auto_safe`. `update_policy` e `contribution_mode` ausentes equivalem a `notify` e `ask`, e seus valores sozinhos não concedem autoridade. A conferência não executa conteúdo remoto; somente o fluxo autorizado pode mutar a instalação ou publicar draft PR. Classificador, Searcher, Planner, Maker e Checker designados não conduzem essa consulta ou mutação. Aproveite o que já estiver decidido; pergunte somente por lacuna material que as fontes não resolvam.
4. Preserve o papel designado pelo usuário. Se ele designou Classificador, Searcher, Planner, Maker ou Checker, leia somente o [contrato desse papel](#contratos) e o contexto necessário; esta skill não transforma outro papel em Orquestrador. Classificador e Searcher não fazem descoberta de atualizações.
5. Para conduzir como Orquestrador, leia o [contrato](prompts/orchestrator.md) e o [playbook](prompts/orchestrator-playbook.md). Quando houver despacho autorizado, consulte os [perfis](prompts/orchestrator-perfis.md): uma sessão econômica do [Classificador](prompts/classifier.md) escolhe modelo e effort dos papéis necessários na fase atual, usando somente o briefing e o recorte de [evidências de roteamento](docs/MODEL_ROUTING.md); o Orquestrador mantém a seleção do usuário no harness.
6. Declare brevemente objetivo, raiz consumidora, limites e próximo passo. Execute apenas o modo pedido: análise ou planejamento não inicia implementação, fila de stories, despacho de Maker para implementar, instalação ou efeito externo. Um pedido genérico de análise também não inicia o painel de debate. A fila só começa pela escolha explícita **Executar fila sequencial** ou pela tarefa agendada que a repita, conforme o [playbook](prompts/orchestrator-playbook.md#fila-sequencial-de-stories).

Quando a ativação para conduzir como Orquestrador não trouxer uma tarefa discernível nem um papel
designado, faça uma triagem somente leitura limitada à raiz consumidora já identificada. Leia
primeiro as instruções locais e procure fontes que declarem explicitamente o trabalho atual, como
story ativa, ticket, branch ou artefato equivalente. Comece por sinais baratos: branch atual,
índice do sprint ou board ativo e IDs de tarefa citados por essas fontes. Use nomes e metadados de
arquivos apenas para reduzir as candidatas e leia por inteiro somente as fontes prováveis. Data de
modificação ajuda a ordenar a busca, mas não torna uma tarefa autoritativa. Não percorra o backlog
inteiro, não escolha uma tarefa apenas por ser a mais recente, não mude de módulo e não execute
portões nessa etapa.

Apresente resumidamente a tarefa identificada, seu estado e os portões encontrados. Se houver mais
de uma candidata ou nenhuma fonte autoritativa, explicite a ambiguidade. Quando existir um board ou
fila declarada pelo consumidor, peça ao usuário que escolha:

1. **Planejar** — analisar ou preparar a spec;
2. **Implementar e revisar uma story** — se a spec estiver executável;
3. **Executar fila sequencial** — processar uma única story elegível da fila declarada;
4. **Debater** — consultar Planner, Maker e Checker sobre a questão atual;
5. **Outra tarefa** — indicar outro objetivo.

Sem board ou fila declarada, não ofereça a opção 3 como atalho para explorar o backlog: peça a
fonte e o módulo que a fila deve usar.

Aguarde a escolha antes de escrever arquivos, despachar agentes ou executar portões. **Implementar
e revisar uma story** autoriza apenas a story identificada. **Executar fila sequencial** segue os
limites, as paradas e as autorizações registradas no perfil local e no playbook; ela não é inferida
da opção 2. Integração, publicação e outros efeitos externos continuam sujeitos à autoridade
aplicável.

Ofereça também **Debater** ao apresentar uma decisão material pendente ao usuário. Aceite a
palavra `Debater` ou o número atribuído especificamente a essa opção no menu atual. Apenas essa
escolha aciona o painel; outras seleções conservam seu significado. Aproveite a pergunta e o
contexto atuais, sem exigir IDs de story. Só pergunte o foco quando ausente ou ambíguo; não explore
o backlog para inventá-lo. A escolha autoriza o painel consultivo somente leitura descrito em
[Debater](prompts/orchestrator-playbook.md#debater), não a execução da recomendação.

Se o usuário designou Classificador, Planner, Maker ou Checker sem informar uma tarefa discernível, limite a
descoberta e as opções ao contrato desse papel e pergunte qual resultado compatível ele deseja.
Não ofereça ao papel designado despachos, escrita ou revisão pertencentes ao Orquestrador.

7. Somente ao conduzir como Orquestrador e com pedido explícito ou autorização de evolução expressa e vigente, conduza [Contribuir melhorias](docs/EVOLUTION.md#contribuir-melhorias) ou [Aplicar uma atualização](docs/PROJECT_CONFIGURATION.md#aplicar-uma-atualização), preservando Maker, prova própria e Checker independente conforme o contrato. `auto_pr` pode chegar somente a commit, push de branch autorizada e draft PR; nunca merge. `auto_safe` aceita somente release estável descendente e para diante de delta, arquivo extra, conflito, migração ou garantia alterada. A autorização cobre apenas projeto, ator, destinos, escopo e efeitos nela identificados; código, produto ou backlog do consumidor exige pedido próprio. O Maker despachado escreve somente os caminhos autorizados em seu briefing, e o Checker revisa o resultado conforme seu contrato. Quando o usuário ativa diretamente Planner, Maker ou Checker para pedir uma atualização, o papel não assume a condução do Orquestrador: Planner e Maker relatam o limite conforme seus contratos, e Checker usa um `intent_gap` dirigido a `human` no objeto JSON exigido.

## Contratos

- [Classificador](prompts/classifier.md): dimensionar os papéis da fase e selecionar modelo/effort por harness em sessão auxiliar econômica.
- [Searcher](prompts/searcher.md): consultar fontes autorizadas e entregar resumo verificável sob demanda.
- [Planner](prompts/planner.md): auditar e especificar.
- [Maker](prompts/maker.md): implementar a spec autorizada.
- [Checker report-only](prompts/checker-report-only.md): revisar de forma independente.

A skill é a entrada; cada contrato possui suas regras. Não duplique mecânica ou configurações pessoais aqui. BMAD não é requisito de ativação: se existir no consumidor, siga suas políticas locais e sua instalação oficial separada.
