id: T009
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: user (smokes de roteamento v0.4.0 e v0.5.0 no consumidor platform, 2026-09-06 e 2026-09-07)
decisions: []
spec_author: none
content_paths: []

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
