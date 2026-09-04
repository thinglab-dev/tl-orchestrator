---
name: tl-orchestrator
description: Planeja e conduz mudanças por mecanismo com Orquestrador, Planner, Maker e Checker externo independente, usando regras e portões do projeto consumidor. Use para coordenar esse método ou planejar sua execução; preserve pedidos limitados a análise ou planejamento.
---

# Ativação do método

1. Identifique **raiz do pacote** como a pasta deste `SKILL.md`. Resolva os links deste pacote em relação ao arquivo que os contém, nunca em relação ao diretório de trabalho do agente.
2. Identifique separadamente a **raiz do projeto consumidor** pelo pedido do usuário, workspace aberto e arquivos locais. Uma raiz de controle de versão pode ajudar, mas Git não é requisito. Não use a pasta da skill como projeto por conveniência.
3. Leia as instruções aplicáveis ao consumidor, a tarefa atual e seu estado real. Consulte o [guia de descoberta](docs/PROJECT_CONFIGURATION.md) para localizar regras, portões e evidências. Aproveite o que já estiver decidido; pergunte somente por lacuna material que as fontes não resolvam.
4. Preserve o papel designado pelo usuário. Se ele designou Planner, Maker ou Checker, leia somente o [contrato desse papel](#contratos) e o contexto necessário; esta skill não transforma um Maker em Orquestrador.
5. Para conduzir como Orquestrador, leia o [contrato](prompts/orchestrator.md) e o [playbook](prompts/orchestrator-playbook.md). Consulte os [perfis](prompts/orchestrator-perfis.md) quando houver despacho autorizado.
6. Declare brevemente objetivo, raiz consumidora, limites e próximo passo. Execute apenas o modo pedido: análise ou planejamento não inicia implementação, ciclo de backlog, despacho de Maker, instalação ou efeito externo. Sem tarefa discernível, pergunte qual resultado o usuário deseja.

## Contratos

- [Planner](prompts/planner.md): auditar e especificar.
- [Maker](prompts/maker.md): implementar a spec autorizada.
- [Checker report-only](prompts/checker-report-only.md): revisar de forma independente.

A skill é a entrada; cada contrato possui suas regras. Não duplique mecânica ou configurações pessoais aqui. BMAD não é requisito de ativação: se existir no consumidor, siga suas políticas locais e sua instalação oficial separada.
