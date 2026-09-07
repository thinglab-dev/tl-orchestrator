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
observed: Orquestradores em effort medium (Claude sonnet, Codex terra, Agy flash) declaram "válida" classificações com par fora do catálogo ou evidência inexistente; a falha se repete entre harnesses e releases, e não é corrigida por briefings mais explícitos
impact: o gate do Classificador é contornado silenciosamente; smokes de adoção não sustentam operational_verified; despachos fora do catálogo
hypothesis: a validação semântica é delegada a raciocínio livre do modelo; sem um procedimento mecânico (lista literal de pares permitidos e de IDs de evidência no briefing, e conferência item a item com resultado tabelado) o Orquestrador tende a afirmar conformidade; T002 (esqueleto do schema) resolve a estrutura, não a semântica
next verification: (a) propor no contrato um checklist literal por candidato (par ∈ catálogo? IDs ∈ lista fornecida? cost_basis sustentado? família ≠ autoria?) cujo resultado tabelado entra no relatório; (b) avaliar um validador mecânico distribuído (script) para a semântica, análogo ao validador estrutural; (c) sonda: repetir o smoke v0.5.0 nos dois harnesses pendentes com o checklist e observar rejeição correta de um par fora do catálogo introduzido de propósito
dedup: T002 (estrutura/esqueleto), T003 (avançar cadeia), T006 (resume), T007 (saída vazia) são distintos; nenhum trata da validação semântica em si
