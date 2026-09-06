# Execução e verificação

Complemento do [contrato do Orquestrador](orchestrator.md). As raízes e os portões vêm do [projeto consumidor](../docs/PROJECT_CONFIGURATION.md).

## Searcher sob demanda

Quando faltar contexto factual para uma decisão, o Orquestrador pode consultar o Searcher antes ou
durante preparação, debate ou classificação, respeitando pergunta concreta, fontes autorizadas,
frescor e limites de tempo, chamadas e resposta. Registre cobertura, lacunas e acessos; falha de
ferramenta ou permissão fica explícita como parcial/bloqueada. O Searcher usa sessão separada e seu
resumo é evidência orientadora, não prova única nem substituto de leitura obrigatória.

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
Conduza Maker, validação de evidências e Checker antes de buscar duplicata e publicar. Duplicata
existente impede novo PR; não modifique trabalho de terceiro nem reabra rejeitado. Sem permissão
comprovada, pare sem configurar fork. Nunca faça merge automático. Feature nova depende de intenção delimitada
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
retomada. Não varra todos os backlogs nem escolha uma story apenas pela data.

Uma ativação processa **no máximo uma** story. Considere a primeira story não concluída na ordem
declarada pelo board e prossiga somente se ela estiver pronta, com dependências satisfeitas e sem
decisão humana pendente. Se ela estiver bloqueada ou ambígua, não pule para outra por conveniência:
registre o motivo e aguarde a decisão ou a atualização do board. Quando BMAD reger o módulo,
execute primeiro a sincronização exigida pela política local e use somente o sprint daquele módulo.

Para a story escolhida, obtenha ou revalide a classificação da **fase atual** para somente os
papéis necessários, seguindo os [perfis](orchestrator-perfis.md#classificar-e-resolver). O
Classificador seleciona modelo e effort por papel/harness; Planner audita ou esclarece a spec,
Maker implementa e prova, e Checker revisa em nova sessão. Toda mudança de fase reclassifica os
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
o limite, obter parecer inválido, encontrar achado de intenção/spec, exigir permissão adicional ou
ver uma falha não atribuída, pare a fila e apresente a evidência e a próxima decisão necessária.

Com `approved`, execute somente as ações locais expressamente autorizadas em `QUEUE.md`, como
registrar evidência, atualizar o board e criar um commit na branch dedicada. Nunca faça push,
publique, abra pull request, altere outro módulo ou acione um sistema externo por causa da fila.
Depois de registrar a conclusão, encerre a ativação. Uma tarefa agendada pode despertar o método
mais tarde para escolher a próxima story; o pacote não mantém um processo, heartbeat ou loop
próprio.

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

## Preparar

Leia pedido, regras locais, tarefa atual, dependências e estado da árvore. Se houver Git, confira branch, base, alterações rastreadas e arquivos novos; sem Git, use a forma existente de identificar versões e mudanças. Preserve o trabalho anterior.

Fixe a garantia, o corte por mecanismo, o escopo e os donos de artefatos compartilhados. Se necessário, peça ao Planner a auditoria e a spec conforme seu contrato. Não transforme uma estimativa de tamanho em limite novo: use a decisão vigente da story e da política local.

Antes de cada papel classificado (Planner, Maker ou Checker), siga a classificação e a resolução dos
[perfis](orchestrator-perfis.md#classificar-e-resolver). Dimensionar Maker e Checker não autoriza
seu despacho quando o pedido se limita a planejamento. Depois de esclarecer a spec, reclassifique
os papéis requeridos pela nova fase, ainda que riscos, garantias e restrições pareçam iguais. Um
Planner pode justificar mais capacidade que a execução delimitada subsequente.

Despache Maker para implementar somente quando a spec estiver executável e a implementação autorizada. Decisão em aberto que muda produto, garantia ou escopo não deve ser herdada como acidente de implementação; ofereça **Debater** para apoiar a escolha do usuário.

## Validar a entrega

A auditoria integral do diff é do Checker e a execução dos portões é do Maker. Sua conferência é de
segunda ordem: verificar que a prova existe, cobre o que devia cobrir e é verificável, sem refazer a
leitura completa do diff nem reexecutar as suítes.

Comece pela identidade do que foi provado: base e head, árvore e branch, arquivos alterados,
adicionados e removidos. Compare essa lista com o que o Maker relatou e com o que o Checker examinou;
arquivo novo omitido por um diff de rastreados é divergência a esclarecer, não detalhe. Confira que
os portões executados são os declarados para a tarefa, com comando literal, diretório e exit real, e
que cada critério de aceite tem uma prova associada.

Depois, confira uma amostra crítica dirigida. Escolha-a pelos riscos, não pelo tamanho: os pontos
decisivos da garantia, os consumidores do comportamento alterado, o que uma retirada deveria
preservar e os achados de maior severidade do parecer. A amostra serve para detectar prova
fabricada, superficial ou desalinhada da intenção; não é uma segunda auditoria completa e não
substitui a do Checker.

Derive dos riscos e contratos afetados a verificação exigida, inclusive de quem constrói ou consome
tipos e configurações alterados, e declare-a no briefing de quem vai executá-la. Uma alteração
documental pode ser comprovada por inspeção, comparação de originais, referências e exportação; não
invente uma suíte de programação para validar documentos.

Quando a garantia depende de teste de comportamento, exija do Maker a prova de que ele discrimina o
defeito por sonda prevista ou equivalente, com cada passo registrado: confirmar a alteração de fato,
observar a falha esperada, recuperar o conteúdo original e observar a passagem, em cópia isolada ou
com restauração segura, conferindo o diff ao final, inclusive após interrupções. Falha de compilação
ou teste que não executou não prova discriminação. Valide esse registro; se ficar ambíguo, peça a
repetição ou a contraprova a quem tem o papel, em vez de executá-la no lugar dele.

Evidência ausente, inconsistente ou não verificável não vira aprovação nem tarefa sua: identifique o
papel responsável, peça o esclarecimento ou a prova que falta e mantenha a entrega em aberto.

Antes do Checker, classifique a fase `review` pelo alcance do mecanismo, riscos e contraprovas
necessárias, não apenas pelo tamanho do diff. O Checker continua sempre em sessão nova, somente
leitura, e sua cadeia conserva a preferência publicada e a política de independência.

## Medir e atribuir falhas

Estas regras valem para quem executa portões e medições, normalmente o Maker. O Orquestrador as
declara no briefing e depois as valida no registro recebido; reexecutar a suíte para conferir não é
sua função, e um relato que não permita essa validação é motivo para pedir a prova de novo.

Mantenha a árvore estável durante portões. Serialize suítes e medições que disputam CPU, serviços, banco ou locks, inclusive entre worktrees. Verifique atividade e obtenha uma janela ociosa; não encerre processos alheios para fabricá-la.

Registre o comando literal, diretório, resultado e exit code real. Um pipe para filtrar saída pode esconder a falha do comando original: capture o resultado antes de resumir. Não deduza conclusão pelo nome de um log ou por uma mensagem citada nele.

Antes de chamar um vermelho de regressão, leia o teste e investigue o caminho causal, dependências e ambiente. Compare com a base apropriada sob condições equivalentes. A ausência de edição no arquivo que falhou não prova que a mudança é inocente. Se não puder atribuir, registre como não atribuído. Não repita indefinidamente até obter verde nem descarte amostras ruins. Essa investigação pertence a quem executou o portão; o Orquestrador não trata um vermelho sem atribuição como regressão nem como inocência e devolve a atribuição ao papel responsável.

## Revisão externa

Esta seção e seu schema regem a revisão de entrega. As opiniões consultivas de
[Debater](#debater) seguem o formato próprio daquele modo e não têm valor de aprovação.

Entregue ao Checker o contrato, a intenção congelada, base, head, diff completo e evidências pertinentes. A auditoria integral desse diff é responsabilidade dele, não sua: entregue-o inteiro, por caminhos legíveis, incluindo arquivos novos e removidos, e não o reduza a um recorte conveniente. Não dirija sua primeira leitura para uma conclusão; memórias e relatos antigos entram apenas depois da inspeção independente das fontes atuais.

Declare no briefing que uma parte não examinada é lacuna material: ela vai ao parecer como
`verificacao_pendente:` dirigido a `human` e impede `approved`. Assim, `approved` afirma cobertura
completa do diff entregue, e o Orquestrador valida essa afirmação por identidade da base e do head,
correspondência entre os arquivos entregues e as localizações citadas no parecer, portões declarados
e amostra crítica dirigida, sem repetir a leitura integral. Parecer genérico, sem localização
verificável ou incompatível com o diff entregue não é revisão cumprida: peça o esclarecimento
necessário e, se a lacuna for da própria revisão, obtenha uma nova revisão independente em vez de
completá-la você mesmo.

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
Campos extras e inconsistência entre `verdict` e `action_items` também exigem correção pelo
Checker. Enquanto o parecer estiver ausente, inválido ou ambíguo, não o trate como aprovação.
Faça no máximo uma solicitação de correção de formato ao mesmo Checker, apontando os defeitos
estruturais sem sugerir o veredito. Se a nova resposta também for inválida, encerre essa revisão
como `parecer válido não obtido`; não repita até conseguir aprovação.

Atribua os achados: correção no escopo ao Maker, spec inconsistente ao Planner, decisão de intenção ao usuário. Registre trabalho fora do escopo sem corrigi-lo silenciosamente. Depois de mudança material, renove as provas afetadas e obtenha nova revisão independente da árvore final.

## Fechamento ou interrupção

Registre a evidência no artefato próprio da story: base/estado examinado, arquivos relevantes, critérios atendidos, comandos e exits, resultados de comparações/sondas, parecer e pendências. Declare separadamente o que foi observado, inferido e não verificado.

Com autorização para integrar, confira o resultado da integração antes da próxima ação. Mudanças no conteúdo validado exigem nova conferência proporcional. Status concluído depende dos portões, revisão independente e autoridade local de ratificação; um verde isolado não fecha a story.

Se o pedido era somente planejamento, entregue o plano e encerre aí. Se houve interrupção, registre o ponto de retomada e preserve a árvore. A próxima sessão relê as fontes e o estado real; o registro ajuda a retomar, não executa continuidade por si só.
