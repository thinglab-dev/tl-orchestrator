# Perfis e despacho

Complemento do [contrato do Orquestrador](orchestrator.md). Este arquivo orienta seleção e transporte; fixa apenas o perfil-padrão substituível, nunca uma flag, instalação ou modelo não conferido.

## Perfil-padrão

O padrão distribuído, quando o consumidor não registrar outra preferência e o usuário não a
alterar na sessão, é:

| Papel | Harness-padrão | Família esperada | Limite |
| :--- | :--- | :--- | :--- |
| Planner | Claude | Anthropic | audita e especifica; não implementa sem autorização própria |
| Maker | Codex | OpenAI | é o único escritor da árvore da story |
| Checker report-only | Agy/Antigravity | Google Gemini, se esse for o modelo observado | nova sessão, sem escrita e família distinta da do Maker |

O nome do harness não substitui a conferência do modelo, da família, da sessão e das permissões.
Registre os valores observados no artefato da story. Se o papel-padrão não puder ser despachado,
pare e informe a lacuna; não converta outro papel em Checker ou Maker por conveniência.

## Resolver a capacidade atual

Use a preferência já declarada pelo usuário; sem preferência local diferente, aplique o
[perfil-padrão](#perfil-padrão). Descubra ferramentas disponíveis no ambiente. Consulte ajuda
local, configuração vigente e documentação oficial pertinente antes de usar uma CLI desconhecida.
Não invente um comando de instalação ou uma flag por memória; não faça chamadas pagas só para
descobrir uma preferência já registrada.

Dimensione o agente pelo trabalho que resta: decisões ainda abertas, variedade de casos, força das provas e impacto de um erro. Mudança documental pode exigir julgamento forte; grande volume mecânico não implica grande ambiguidade. Respeite custo e quota autorizados, sem rebaixar capacidade ou independência em silêncio.

No fluxo de implementação, Planner esclarece a spec; Maker executa; Checker recebe sessão nova e família distinta do Maker. Use ferramentas de despacho que realmente existam e caibam nas permissões atuais. Falta de ferramenta ou acesso é bloqueio a relatar, nunca evidência de que o trabalho ocorreu.

Para **Debater**, siga o [playbook consultivo](orchestrator-playbook.md#debater): revalide harness,
modelo, família e permissões de cada participante no despacho, conforme as preferências vigentes.
As três sessões devem ser reais, separadas e somente leitura; o Checker mantém família distinta
do Maker. Informe indisponibilidade ou participação parcial, sem substituir alguém em silêncio ou
apresentar opiniões simuladas como respostas de agentes.

## Briefing concreto

Forneça o caminho real do contrato dentro da **raiz do pacote** e a **raiz consumidora** separadamente. Antes de despachar, confira que o agente terá acesso de leitura aos dois. O briefing contém:

- papel, resultado pedido e critério de parada;
- story/spec atual, decisões reservadas e estado base;
- raiz exata da árvore, caminhos de implementação permitidos, artefatos de evidência e arquivos protegidos;
- portões existentes, diretório de execução e recursos compartilhados;
- destino do relatório e operações proibidas;
- para Checker na revisão de entrega, base, diff inteiro, critérios congelados e schema acessível.

No debate, substitua o briefing de execução pelo dossiê comum do playbook, identifique o modo
consultivo e entregue o contrato de cada papel. Não exija spec executável nem forneça o schema de
aprovação: o resultado pedido é uma opinião consultiva na resposta, sem escrita no projeto.

Configure permissões de leitura/escrita conforme o papel usando capacidades verificadas do harness. Uma instrução report-only não equivale a uma trava técnica. Não contorne controles de aprovação ou sandbox para completar um despacho.

## Acompanhar e retomar

Use o mecanismo de acompanhamento fornecido pela ferramenta. Registre identificador da sessão e resultado observado; processo vivo, log crescente e exit zero isolado não provam o cumprimento da tarefa. Não prometa ser acordado depois de encerrar a sessão.

Em falha de acesso, quota ou interrupção, preserve o trabalho e registre causa observada, base, diff disponível e próxima ação verificável no artefato da story. Um substituto só começa depois de cessada a escrita anterior e de conferir novamente árvore, spec e evidências. Se o usuário fixou ferramenta ou modelo, não troque sem a autorização correspondente. Reavalie apenas o trabalho residual; falha de capacidade não transforma decisão complexa em tarefa simples.
