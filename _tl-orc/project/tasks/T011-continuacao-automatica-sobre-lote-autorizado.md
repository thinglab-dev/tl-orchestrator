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
expected: continuação sobre um lote autorizado, partindo da fila sequencial já definida para o perfil Native (`docs/WORK_MODEL.md#fila-sequencial-no-perfil-native`): concluir a unidade → selecionar a próxima elegível do lote (Task `ready`, com spec conforme o contrato e dependências satisfeitas; uma Task `draft` só é preparada e promovida a `ready` quando isso estiver autorizado) → conferir estado, dependências e autorização → classificar → executar; decisão técnica dentro do escopo segue para consulta classificada após prazo definido; decisão que exige nova autorização fica registrada como pendência enquanto Tasks independentes do lote continuam; sem daemon, sem promessa de continuidade fora da sessão
impact: ciclos interrompidos por perguntas evitáveis; tempo de agente ocioso; pendências de autorização misturadas com decisões técnicas
hypothesis: a fila sequencial do perfil Native já define ordem, paradas e autorizações por unidade; o que falta é (a) a noção de lote autorizado (quais Tasks, orçamento, prazo de consulta, condições de parada), (b) a regra de continuidade entre unidades sem nova pergunta quando o lote já autoriza, e (c) a consulta após prazo para decisões técnicas dentro do escopo, distinguindo-as de decisões que exigem nova autorização
next verification: análise que parta do texto vigente de "Fila sequencial no perfil Native" e do Native Work Model, identificando exatamente o que falta para continuidade e consulta após prazo, sem reconstruir a fila já definida; propor o registro do lote e a regra de continuidade; piloto em consumidor sintético com uma Task `ready` e uma `draft`; não ampliar T010
dedup: T010 (escalonamento consultivo dentro de uma Task) e a fila sequencial do perfil Native (já publicada) são distintos; esta Task complementa a fila, não a substitui
