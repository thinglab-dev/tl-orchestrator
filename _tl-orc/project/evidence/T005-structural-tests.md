unit: native/task/T005@_tl-orc/project/tasks/T005-review-followups-e-agent-runs.md
kind: testes estruturais em consumidor sintético (spec §11, teste de estrutura), sem harness pago
content_id: 7923d9c22d1c4fe74cf07049e61810db0f36a14f:2f69fcb3080a395d (r02, aprovado; conteúdo distribuído intocado por estes testes)
script: `evidence/T005-structural-tests.py` (reproduzível: `python3 _tl-orc/project/evidence/T005-structural-tests.py <dir>`); executado em 20260907T194134Z, exit 0

## Método
Cada cenário constrói documentos sintéticos com resultados fabricados (evidência de rodada com tabela `Agent runs`, registro de revisão, bloco `RF-<unit_id>-rNN`, STATUS global com `review_followups`, Task ou story), aplica as regras do contrato como funções deterministas que transcrevem o texto aprovado (WORK_MODEL `Registro de revisão` e `Conclusão`; perfis `Independência do Checker`; playbook `Fechamento ou interrupção`) e verifica invariantes: âncora produzida pelo título e resolvida pela `heading_anchors` do validador do repositório; alvo idêntico (unidade, `spec_revision`, `content_id`) para fechar; famílias do parecer disjuntas de `families_used`; cadeia de substituição com `supersedes`, `superseded_by` e `reason` com mapeamento de garantias; estados válidos. Entradas, estado resultante e verificações estão no script e nas árvores geradas; excertos abaixo.

## Entradas e estados resultantes por cenário
| # | Entrada (sintética) | Operação do contrato | Estado resultante | Verificações |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Native T001, política preferred; Agent runs com Google (429) e Anthropic (401) indisponíveis; Checker OpenAI (mesma família do Maker) approved em sessão nova | abrir pendência | `RF-T001-r01` pending, limitação registrada; STATUS `review_followups` referencia `...T001-r01.md#rf-t001-r01`; Task done | 4 OK, inclusive recusa sem prova de indisponibilidade |
| 2 | mesmas entradas, política required | abrir pendência | ContractViolation; nenhum bloco; Task in_review com `blocked_by` e ponto de retomada; `review_followups: []` | 3 OK |
| 4 | RF pending; revisão r02 Anthropic approved, mesmo alvo | fechar | closed, `review_ref: evidence/T001-r02.md#r02 run_id=T001-r02-checker-1`, log acrescentado, alvo intacto | 3 OK, inclusive recusa de mesma família |
| 5 | RF pending; revisão r02 Google changes_requested; sem autorização | fechar | pending; `attempts` com o run; Task T002 fix draft criada; nenhum run de Maker | 2 OK |
| 6 | RF pending após changes_requested; autorização vigente; rework com novo content_id; reason com garantias G1/G2 mantidas e G3 retirada por DEC002 | substituir | original superseded com `superseded_by`; substituta `RF-T001-r03` pending com `supersedes` e `origin_review: r01 run_id: T001-r01-checker-3` | 2 OK |
| 6b | idem com parecer Anthropic approved já cobrindo o novo alvo | substituir + fechar | substituta nasce closed com review_ref; original superseded, não closed; cadeia navegável por âncora | 3 OK |
| 7 | RF pending; conteúdo alterado sem revisão; tentativas de substituição sem reason e só com dois content_id | substituir | pendência mantida; as duas tentativas rejeitadas; substituição com mapeamento aceita | 4 OK |
| 8 | RF pending; approved Anthropic com outro content_id | fechar | recusado; pending; attempts registra alvo divergente | 1 OK |
| 9 | RF pending de T001; approved de T002 com o mesmo content_id | fechar | recusado (unidade diferente); pending | 1 OK |
| 10 | duas stories `1.1` em `billing` e `identity`, projeto bmad multiárea | abrir pendências | dois blocos em artefatos de áreas distintas, âncoras `rf-billing11-r01` e `rf-identity11-r01` resolvidas; STATUS global lista as duas identidades completas; nenhuma Task Native | 3 OK |
| 12 | RF com `locator: not_recoverable` e reason; revisão posterior sobre conteúdo atual | fechar | recusado (outro content_id); pending com limitação | 2 OK |
| 15 | families_used = Google (Maker) + Anthropic (correção própria do Orquestrador) | elegibilidade e fechamento | só OpenAI elegível no catálogo; revisão por Anthropic recusada | 2 OK |
| * | todos os blocos gerados | invariante | status ∈ {pending, superseded, closed} | 1 OK |

## Relatório literal da execução
| cenário | verificação | resultado | detalhe |
| :--- | :--- | :--- | :--- |
| 1 | bloco RF criado com status pending e limitação | OK | RF-T001-r01 |
| 1 | STATUS referencia por caminho e âncora produzida pelo título | OK | native/task/T001@_tl-orc/project/tasks/T001-slug.md@_tl-orc/project/evidence/T001-r01.md#rf-t001-r01 |
| 1 | done permitido sob preferred com pendência aberta | OK |  |
| 1 | mesma família recusada sem prova de indisponibilidade | OK |  |
| 2 | required bloqueia sem abrir bloco | OK |  |
| 2 | done não permitido sem parecer approved | OK |  |
| 2 | review_followups vazio no STATUS | OK |  |
| 4 | closed com review_ref contendo evidência, rodada e run_id | OK | evidence/T001-r02.md#r02 run_id=T001-r02-checker-1 |
| 4 | registro de controle acrescenta log sem alterar alvo | OK |  |
| 4 | mesma família de families_used é recusada para fechar | OK |  |
| 5 | pendência permanece pending com attempts registrado | OK |  |
| 5 | achados entram na fila como Task fix draft; nenhum run de maker após o parecer | OK |  |
| 6 | original superseded com superseded_by e reason com garantias | OK | RF-T001-r03 |
| 6 | substituta pending herda origin_review (rodada e run da original) e registra supersedes | OK | RF-T001-r03 |
| 6b | substituta nasce closed com review_ref; original superseded; nenhuma pendência aberta | OK |  |
| 6b | aprovação do conteúdo novo não fecha a original (fica superseded, não closed) | OK |  |
| 6b | cadeia navegável: superseded_by aponta para bloco existente com âncora própria | OK | native/task/T001@_tl-orc/project/tasks/T001-slug.md@_tl-orc/project/evidence/T001-r03.md#rf-t001-r03 |
| 7 | alteração do conteúdo sem revisão não fecha nem apaga a pendência | OK |  |
| 7 | substituição sem reason é rejeitada | OK |  |
| 7 | substituição com dois content_id e sem mapeamento de garantias é rejeitada | OK |  |
| 7 | nova revisão de mesma família no conteúdo novo cria substituta vinculada | OK |  |
| 8 | approved distinto com outro content_id não fecha e fica em attempts | OK |  |
| 9 | mesmo content_id em outra unidade não transporta | OK |  |
| 10 | duas pendências distintas, blocos nos artefatos de cada área | OK | bmad/story/billing:1.1@modules/billing/_bmad-output/implementation-artifacts/sprint-status.yaml@modules/billing/_bmad-output/implementation-artifacts/evidence-1.1-r01.md#rf-billing11-r01; bmad/story/identity:1.1@modules/identity/_bmad-output/implementation-artifacts/sprint-status.yaml@modules/identity/_bmad-output/implementation-artifacts/evidence-1.1-r01.md#rf-identity11-r01 |
| 10 | nenhuma Task Native criada | OK |  |
| 10 | STATUS global lista as duas identidades completas | OK |  |
| 12 | pendência permanece pending com limitação e reason | OK |  |
| 12 | fechamento pelo conteúdo atual (outro content_id) é recusado | OK |  |
| 15 | families_used inclui a família do Orquestrador; só OpenAI elegível | OK | ['codex/gpt-5.6-terra/high'] |
| 15 | revisão posterior por família já usada (Anthropic) é recusada | OK |  |
| * | todos os blocos RF gerados têm status em {pending, superseded, closed} | OK | [] |

31/31 verificações OK; árvores em <dir>

## Limitações
- As regras foram transcritas para funções pelo Orquestrador a partir do texto aprovado; uma divergência entre script e texto seria defeito do script, não prova sobre o método. Cada função cita a cláusula de origem; a leitura normativa pelo Checker Astra (r01/r02) e estes testes são evidências complementares, não a mesma evidência.
- Resultados de agentes são fabricados; nenhuma revisão real de mesma família ocorreu. A criação persistida do bloco por um Orquestrador em fallback real continua limitação de adoção.
- O cenário 3 (ativação) e o 13 (decisão de fallback) usaram harness real com estado construído e entradas fabricadas; ver `T005-verification-matrix.md`.
