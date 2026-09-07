id: T011
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: [T010]
blocked_by: []
origin: user (2026-09-07, conferência de T009/T010: "o loop ainda não está completo")
decisions: []
spec_author: none
content_paths: []

## Finding
source: condução de T005, T009 e T010 no fonte em 2026-09-07
observed: o Orquestrador parou entre Tasks para pedir seleção ou autorização mesmo quando havia lote autorizado com Tasks elegíveis; T010 formalizou apenas o escalonamento consultivo dentro de uma Task; decisões técnicas dentro do escopo esperaram o usuário em vez de seguir para consulta após prazo
expected: continuação sobre um lote autorizado: concluir a unidade → selecionar a próxima elegível (draft com spec pronta e dependências satisfeitas, dentro do lote) → classificar → executar; decisão técnica dentro do escopo segue para consulta classificada após prazo definido; decisão que exige nova autorização fica registrada como pendência enquanto Tasks independentes continuam; sem daemon, sem promessa de continuidade fora da sessão
impact: ciclos interrompidos por perguntas evitáveis; tempo de agente ocioso; pendências de autorização misturadas com decisões técnicas
hypothesis: falta no contrato a noção de lote autorizado (quais Tasks, qual orçamento, qual prazo de consulta) e a regra de seleção da próxima elegível; a fila sequencial existente (QUEUE.md) cobre stories BMAD, não Tasks Native
next verification: analisar a fila sequencial existente e o Native Work Model; propor o registro do lote (Tasks, orçamento, prazo de consulta, condições de parada) e a regra de seleção; piloto em consumidor sintético; não ampliar T010
dedup: T010 (escalonamento consultivo dentro de uma Task) e fila sequencial (stories BMAD) são distintos
