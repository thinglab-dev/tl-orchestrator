# Execução e verificação

Complemento do [contrato do Orquestrador](orchestrator.md). As raízes e os portões vêm do [projeto consumidor](../docs/PROJECT_CONFIGURATION.md).

## Preparar

Leia pedido, regras locais, tarefa atual, dependências e estado da árvore. Se houver Git, confira branch, base, alterações rastreadas e arquivos novos; sem Git, use a forma existente de identificar versões e mudanças. Preserve o trabalho anterior.

Fixe a garantia, o corte por mecanismo, o escopo e os donos de artefatos compartilhados. Se necessário, peça ao Planner a auditoria e a spec conforme seu contrato. Não transforme uma estimativa de tamanho em limite novo: use a decisão vigente da story e da política local.

Despache Maker somente quando a spec estiver executável e a implementação autorizada. Decisão em aberto que muda produto, garantia ou escopo não deve ser herdada como acidente de implementação.

## Conferir a entrega

Leia todos os acréscimos e remoções, incluindo arquivos novos que um diff de rastreados omite. Compare o resultado com os critérios de aceite e verifique os consumidores do comportamento alterado. Em uma retirada, confira ausência de dependências e preservação do material que deveria ficar.

Derive a verificação dos riscos e contratos afetados, inclusive quem constrói ou consome tipos/configurações alterados. Execute os portões existentes definidos para a tarefa; uma alteração documental pode ser comprovada por inspeção, comparação de originais, referências e exportação. Não invente uma suíte de programação para validar documentos.

Quando a garantia depende de teste de comportamento, prove pessoalmente que ele discrimina o defeito por sonda prevista ou equivalente: confirme a alteração de fato, observe a falha esperada, recupere o conteúdo original e observe a passagem. Falha de compilação ou teste que não executou não prova discriminação. Use uma cópia isolada ou mecanismo seguro de restauração e confira o diff ao final, inclusive após interrupções.

## Medir e atribuir falhas

Mantenha a árvore estável durante portões. Serialize suítes e medições que disputam CPU, serviços, banco ou locks, inclusive entre worktrees. Verifique atividade e obtenha uma janela ociosa; não encerre processos alheios para fabricá-la.

Registre o comando literal, diretório, resultado e exit code real. Um pipe para filtrar saída pode esconder a falha do comando original: capture o resultado antes de resumir. Não deduza conclusão pelo nome de um log ou por uma mensagem citada nele.

Antes de chamar um vermelho de regressão, leia o teste e investigue o caminho causal, dependências e ambiente. Compare com a base apropriada sob condições equivalentes. A ausência de edição no arquivo que falhou não prova que a mudança é inocente. Se não puder atribuir, registre como não atribuído. Não repita indefinidamente até obter verde nem descarte amostras ruins.

## Revisão externa

Entregue ao Checker o contrato, a intenção congelada, base, diff completo e evidências pertinentes. Não dirija sua primeira leitura para uma conclusão; memórias e relatos antigos entram apenas depois da inspeção independente das fontes atuais.

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
