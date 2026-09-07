id: T009
type: analysis
deliverable: none
standalone: true
method: native
status: done
state_revision: 9
depends_on: []
blocked_by: []
origin: user (smokes de roteamento v0.4.0 e v0.5.0 no consumidor platform, 2026-09-06 e 2026-09-07)
decisions: []
spec_author: orchestrator
spec_revision: 4197dea48f75cd14
rework_round: 5 (+2 correções próprias do Orquestrador)
affects_context: []
content_paths: [_tl-orc/project/evidence/T009-analysis.md, _tl-orc/project/evidence/T009-mechanical-check.py, _tl-orc/project/evidence/T009-cases]
content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:938ddfb319408b79

## Finding
source: relatórios dos Orquestradores em smokes de roteamento: v0.4.0 r02 (Claude e Agy aceitaram pares fora do catálogo), v0.5.0 r1 (Claude aceitou opus fora do catálogo e price-flash para Gemini 3.1 Pro só na primeira resposta), v0.5.0 r3 Claude (aceitou e despachou `codex/gpt-5.6-luna` como Maker, fora do catálogo; preencheu story_id que devia ser nulo), v0.5.0 r3 Codex (fabricou identificadores de evidência genéricos no briefing e os declarou pertinentes); no próprio fonte, T005 (Orquestrador Claude Code aceitou evidência não pertinente após a correção única)
expected: "Valide estrutura e semântica: cada par harness/modelo/effort dentro do catálogo; evidence_ids pertinentes ao modelo; cost_basis sustentado" (perfis, Classificar e resolver); evidências entregues ao Classificador são cartões do MODEL_ROUTING com IDs, não rótulos inventados
observed: Orquestradores declaram "válida" classificações com par fora do catálogo, `story_id` indevido ou evidência inexistente; a falha se repete entre harnesses e releases e não foi corrigida por briefings mais explícitos. Condição observada, não causa demonstrada: todas as ocorrências usaram effort medium; sem comparação controlada não se sabe se effort maior resolveria. Fato confirmado: aceitação recorrente de classificações inválidas
impact: o gate do Classificador é contornado silenciosamente; smokes de adoção não sustentam operational_verified; despachos fora do catálogo
hypothesis: a validação semântica é delegada a raciocínio livre do modelo, e parte dela compara o resultado com entradas que o próprio Orquestrador compôs (catálogo resumido, lista de evidências), de modo que uma invenção consistente passa por conformidade; T002 (esqueleto do schema) resolve a estrutura, não a semântica. Um checklist preenchido pela mesma IA melhora a rastreabilidade mas pode repetir o problema; os requisitos verificáveis precisam de conferência objetiva
proposal (revisada em 20260907T210033Z com o maintainer): dividir a validação em duas camadas.
  Mecânica (conferência objetiva, sem julgamento): schema; `story_id` esperado, inclusive `null`; fase e revisões de contexto/catálogo/contrato; papéis solicitados exatos; pares harness/modelo/effort ∈ catálogo autorizado; pins respeitados; existência e procedência dos IDs de evidência.
  Julgamento (Orquestrador, registrado): pertinência da evidência à tarefa; justificativa do esforço; alcance real da conclusão econômica.
  Origem das entradas: o catálogo conferido deve ser o da política autorizada do consumidor (PROJECT.md), não um resumo composto na hora; os IDs de evidência devem remeter a cartões reais do MODEL_ROUTING ou a medições locais registradas com ID; comparar com uma lista inventada pelo próprio Orquestrador só confirma uma invenção consistente.
  Regras preservadas: a independência segue `preferred`/`required` e as condições de fallback, sem virar proibição universal de mesma família; `cost_basis: unknown` é legítimo; o defeito é fabricar sustentação ou afirmar mais do que a evidência permite.
next verification (piloto delimitado, sem distribuir validador executável): (a) um resultado válido que passa nas duas camadas; (b) alterações deliberadamente inválidas, uma por vez: par fora do catálogo; `story_id` indevido (preenchido quando esperado `null`, ou divergente); ID de evidência inexistente; evidência existente usada para sustentar conclusão incompatível (por exemplo, cartão de capacidade sustentando `official_task_proxy`); para cada rejeição, registrar o motivo e comprovar que nenhum despacho se seguiu; (c) comparação controlada opcional de effort só se o piloto mostrar dependência. Decisões posteriores, fora desta Task: distribuir um validador executável, escolher linguagem, introduzir requisitos de instalação; esta Task avalia o ganho sem antecipar mudança de arquitetura
dedup: T002 (estrutura/esqueleto), T003 (avançar cadeia), T006 (resume), T007 (saída vazia) são distintos; nenhum trata da validação semântica em si

## Spec
### Intent
Analisar por que a validação semântica da classificação feita pelo Orquestrador aceita objetos inválidos de forma recorrente, propor a divisão em camada mecânica (conferência objetiva) e camada de julgamento (registrada), exigindo origem verificável das entradas, e provar em piloto delimitado que a camada mecânica rejeita alterações deliberadamente inválidas e aceita um resultado válido, sem distribuir validador nem alterar o método.
### Scope and write paths
Somente: `_tl-orc/project/evidence/T009-analysis.md` (análise), `_tl-orc/project/evidence/T009-mechanical-check.py` (protótipo da camada mecânica, não distribuído), `_tl-orc/project/evidence/T009-cases/` (objetos do piloto e saídas). Proibido: qualquer arquivo distribuído (SKILL.md, prompts/, docs/, schemas/, manifesto), `scripts/`, `_tl-orc/PROJECT.md`, outras Tasks.
### Acceptance criteria
AC01 Diagnóstico com as ocorrências registradas (v0.4.0 r02; v0.5.0 r1 e r3 nos dois harnesses; T005 no fonte), citando as evidências por caminho, e distinguindo condição observada (effort medium) de causa demonstrada.
AC02 Proposta em duas camadas: mecânica (schema; `story_id` esperado, inclusive `null`; fase e revisões; papéis exatos; pares harness/modelo/effort no catálogo autorizado; pins; existência e procedência dos IDs de evidência) e julgamento (pertinência, esforço, alcance econômico), com origem obrigatória das entradas: catálogo lido de `_tl-orc/PROJECT.md#perfil-de-despacho`, IDs de evidência lidos de `docs/MODEL_ROUTING.md` e medições locais registradas com ID e caminho; nunca listas compostas na hora.
AC03 Regras preservadas e demonstradas no protótipo: independência conforme `preferred`/`required` e condições de fallback (mesma família não é proibição universal); `cost_basis: unknown` legítimo; rejeição só de sustentação fabricada ou de conclusão além da evidência.
AC04 Piloto: caso válido real (classificação da fase review de T005, `evidence/T005-classification.md`) que passa nas duas camadas; quatro alterações deliberadas, uma por vez: par fora do catálogo; `story_id` indevido; ID de evidência inexistente; evidência existente sustentando conclusão incompatível (cartão de capacidade sustentando `official_task_proxy`). Para cada rejeição: motivo tabelado por candidato e prova de que nenhum despacho se seguiu (o fluxo simulado do Orquestrador para no gate, sem linha de despacho em `Agent runs`).
AC05 Análise com premissas, alternativas consideradas (checklist preenchido pela IA; validador mecânico local; effort maior com comparação controlada) e o que mudaria a conclusão; decisões de distribuição, linguagem e instalação explicitamente fora do escopo.
AC06 Portões: `python3 scripts/validate_repository.py` verde; nenhum arquivo distribuído alterado; nenhum caminho privado; protótipo executável com `python3 _tl-orc/project/evidence/T009-mechanical-check.py --self-test` reproduzindo o piloto.
### Verification profile
`analysis`: premissas, alternativas e o que mudaria a conclusão (AC05); execução reproduzível do piloto (AC04, AC06); Checker report-only de família distinta de toda autoria efetiva, com hipótese rejeitada e citação por critério (pin do piloto do fonte: `gpt-6-astra/high`, restrição `required` específica desta revisão).
## Result
Análise e protótipo concluídos como `analysis`. Diagnóstico: aceitação recorrente de classificações inválidas pelo Orquestrador em três harnesses e duas releases (effort medium é condição observada, não causa demonstrada). Proposta: validação em três estágios (conferência mecânica → julgamento registrado → liberação de despacho) com origem obrigatória das entradas. Protótipo `T009-mechanical-check.py` e 38 casos (`T009-cases/`): um caso válido real, invalidações deliberadas e controles das regras preservadas (independência como filtro de resolução; `cost_basis: unknown` legítimo; `null/null` como lacuna; fallback sob preferred só com prova; família não resolvida bloqueia), `--self-test` sem escrita. Limitação residual explícita: a conferência de procedência do protótipo não é geral por tipo e conteúdo; após quatro rodadas com achados dessa classe, a fase consultiva (c01) concluiu que se trata de requisito a consolidar, feito em T010 (tabela normativa tipo → fonte → conteúdo → conferência). O protótipo não é distribuído; decisões de distribuição, linguagem e instalação ficam fora. Regra secundária de escalonamento consultivo aplicada e formalizada em T010.

## Evidence
`evidence/T009-classification.md` (8 classificações com conferência mecânica e os desvios registrados), `T009-maker-report.md` (entrega e 5 reworks com conferências), `T009-r01.md` a `T009-r07.md`, `T009-c01.md` (fase consultiva), `T009-analysis.md`, `T009-mechanical-check.py`, `T009-cases/`.

## Review
r01 changes_requested (6) → r02 (5) → r03 (3) → r04 (2) → r05 (1, escalonamento) → c01 consulta → r06 (1, análise) → r07 `approved`; 18 achados no total, 10 high; 24 chamadas pagas (Checker codex gpt-6-astra high, run T009-r07-checker-1, evidence/T009-r07.md). Desvios do Orquestrador registrados: classificação semanticamente inválida aceita não houve nesta Task; reworks 1–4 e reviews r02/r03 sem classificação de fase (corrigido a partir do rework 5); resumes anteriores sem -m (T005). Fechada em 20260907T231408Z.
