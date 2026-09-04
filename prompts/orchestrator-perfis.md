# Perfis e despacho

Complemento do [contrato do Orquestrador](orchestrator.md). Este arquivo orienta seleção e transporte; não fixa fornecedores, modelos, flags ou instalações.

## Resolver a capacidade atual

Use a preferência já declarada pelo usuário e descubra ferramentas disponíveis no ambiente. Consulte ajuda local, configuração vigente e documentação oficial pertinente antes de usar uma CLI desconhecida. Não invente um comando de instalação ou uma flag por memória; não faça chamadas pagas só para descobrir uma preferência já registrada.

Dimensione o agente pelo trabalho que resta: decisões ainda abertas, variedade de casos, força das provas e impacto de um erro. Mudança documental pode exigir julgamento forte; grande volume mecânico não implica grande ambiguidade. Respeite custo e quota autorizados, sem rebaixar capacidade ou independência em silêncio.

Planner esclarece a spec; Maker executa; Checker recebe sessão nova e família distinta do Maker. Use ferramentas de despacho que realmente existam e caibam nas permissões atuais. Falta de ferramenta ou acesso é bloqueio a relatar, nunca evidência de que o trabalho ocorreu.

## Briefing concreto

Forneça o caminho real do contrato dentro da **raiz do pacote** e a **raiz consumidora** separadamente. Antes de despachar, confira que o agente terá acesso de leitura aos dois. O briefing contém:

- papel, resultado pedido e critério de parada;
- story/spec atual, decisões reservadas e estado base;
- raiz exata da árvore, caminhos de implementação permitidos, artefatos de evidência e arquivos protegidos;
- portões existentes, diretório de execução e recursos compartilhados;
- destino do relatório e operações proibidas;
- para Checker, base, diff inteiro, critérios congelados e schema acessível.

Configure permissões de leitura/escrita conforme o papel usando capacidades verificadas do harness. Uma instrução report-only não equivale a uma trava técnica. Não contorne controles de aprovação ou sandbox para completar um despacho.

## Acompanhar e retomar

Use o mecanismo de acompanhamento fornecido pela ferramenta. Registre identificador da sessão e resultado observado; processo vivo, log crescente e exit zero isolado não provam o cumprimento da tarefa. Não prometa ser acordado depois de encerrar a sessão.

Em falha de acesso, quota ou interrupção, preserve o trabalho e registre causa observada, base, diff disponível e próxima ação verificável no artefato da story. Um substituto só começa depois de cessada a escrita anterior e de conferir novamente árvore, spec e evidências. Se o usuário fixou ferramenta ou modelo, não troque sem a autorização correspondente. Reavalie apenas o trabalho residual; falha de capacidade não transforma decisão complexa em tarefa simples.
