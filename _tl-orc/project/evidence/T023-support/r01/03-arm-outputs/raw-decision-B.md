Proposta formal: **escalonamento consultivo em `debate` antes de um rework 3**.

O r02 confirmou cinco defeitos materiais da mesma classe: procedência semântica e separação inválida entre validação do objeto e resolução operacional. Embora o gatilho automático usual seja três reworks, a regra adaptada permite escalar antes disso pela reincidência. Um terceiro patch sem consolidar o modelo de procedência tende a corrigir novos sintomas do mesmo problema.

Há uma pré-condição documental: antes de qualquer fase executiva, reconciliar a Task oficial, que registra `rework_round: 0` e `content_id: unknown`, com o recibo r02, que registra rework 2 e o `content_id` revisado. Não alterei nada.

## Briefing proposto — fase `debate` consultiva

- Unidade: `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`
- Objetivo: decidir se R1–R5 são manifestações de um único contrato incompleto de procedência/resolução e consolidar uma abordagem verificável antes de autorizar rework.
- Modo: somente leitura; sem despacho, edição, teste que escreva, mudança de estado ou alteração distribuída.
- Escopo de leitura: somente esta raiz; Task T009, parecer `_tl-orc/project/evidence/T009-r02.md`, `PROJECT.md`, contratos, schemas, `MODEL_ROUTING.md` e evidências T009.
- Papéis a classificar quando a consulta for efetivamente autorizada: Planner, Maker e Checker consultivos. A classificação deve ser nova para `phase: debate`; não reutilizar escolhas de r02.
- Independência: `checker_independence: required`; autores efetivos registrados incluem Google e Anthropic. Família desconhecida bloqueia seleção. O revisor independente prioritário é Codex, sujeito à classificação válida e ao pin/política vigente.
- Critério de parada: entregar recomendação consolidada de contrato, contraprovas e limites de escopo; não implementar.

Pergunta central ao painel:

> Estamos corrigindo manifestações do mesmo defeito de tipagem/procedência das entradas, ou há requisitos distintos que exigem consolidar explicitamente a separação entre validade mecânica, julgamento e resolução de despacho?

### Regras de procedência a consolidar

| Tipo | Fonte e validação exigidas |
|---|---|
| Medição local | Registro estruturado em `_tl-orc/project/evidence/` ou `_tl-orc/evidence/`, com ID na primeira coluna e localizador resolvido para o registro correto. Substring, âncora/linha inexistente, cartão oficial e exemplo negativo não valem. |
| Proxy econômico por tarefa | Cartão de `docs/MODEL_ROUTING.md` que declare expressamente custo monetário ou tokens por tarefa. Duração, latência, capacidade ou “minutos por tarefa” não satisfazem `official_task_proxy`. |
| Indisponibilidade | Evidência pertinente da falha de infraestrutura do candidato, com localização verificável; timeout isolado, texto arbitrário e âncora inexistente não provam indisponibilidade. |
| Família e autoria | Família vem de `Agent runs` efetivos e deve ser conhecida antes da escolha. Família ausente é estado não resolvido, nunca “distinta”. |
| Julgamento | Registro documental ligado por hash ao objeto e às entradas; não é substituído pela validação mecânica. |

### Ações que o debate deve converter em spec de rework

- **R1:** exigir resolução tipada do localizador e vínculo a uma medição local efetiva; adicionar controles para âncora inexistente, linha inexistente, cartão oficial e exemplo negativo.
- **R2:** vincular `official_task_proxy` exclusivamente a afirmação econômica por tarefa; incluir `astra-domain` como controle negativo.
- **R3:** validar prova de indisponibilidade e disponibilidade do candidato selecionado; rejeitar texto sem erro pertinente e candidato `disabled`; timeout isolado permanece insuficiente.
- **R4:** tornar família ausente um bloqueio de resolução, com nenhum despacho.
- **R5:** aceitar mecanicamente um objeto válido mesmo sem família independente sob `required`; bloquear somente a resolução, registrando ponto de retomada e nenhum despacho.

A eventual spec de rework deve preservar `cost_basis: unknown`, manter mesma família possível apenas nas condições de `preferred`, e exigir casos reproduzíveis que comprovem motivo explícito e `despacho: nenhum` para cada negativa. Nenhuma decisão de distribuir o protótipo, definir linguagem final ou introduzir instalação entra nesse rework.

Todos os SHA-256 indicados no pacote conferem com as fontes lidas. Não houve escrita, despacho nem inspeção fora da raiz.