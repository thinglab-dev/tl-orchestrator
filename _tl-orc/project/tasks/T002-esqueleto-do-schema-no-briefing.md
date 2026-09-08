id: T002
type: analysis
deliverable: none
standalone: true
method: native
status: in_progress
state_revision: 1
depends_on: []
blocked_by: []
origin: platform v0.4.0 update evidence (smokes r03–r07, 2026-09-06/07)
decisions: []
spec_author: orchestrator (claude-code-b1467fdf)
spec_revision: d1826e1b23d2b131 (s1)
content_paths: [_tl-orc/project/evidence/T002-analysis.md, _tl-orc/project/evidence/T002-briefing-template.md, _tl-orc/project/evidence/T002-briefing-skeleton.py, _tl-orc/project/evidence/T002-cases/]

## Finding
source: relatórios de smoke em Claude Code e Codex como Orquestrador
observed: o Classificador (Codex gpt-5.6-luna e Claude sonnet) devolveu respostas estruturalmente inválidas em várias primeiras chamadas (campos obrigatórios ausentes, campo extra, tier "primary", confidence numérico, facts como objetos); incluir no briefing o esqueleto literal do schema com enums e a lista de campos obrigatórios eliminou as falhas nas rodadas seguintes
hypothesis: o briefing padrão de "schema compacto" não é específico o bastante; a melhoria é definir no contrato o esqueleto mínimo a enviar
next verification: analisar orchestrator-perfis.md e classifier.md; propor texto normativo do esqueleto; medir taxa de resposta válida na primeira chamada em smoke sintético antes e depois

## Spec
### Intent
Definir o briefing mínimo do Classificador (campos, enums, campos obrigatórios, candidatos esperados por cadeia, procedência por entrada) a partir das falhas já registradas, medir a validade da primeira resposta com e sem esse briefing em smoke sintético, e propor o texto normativo como delta em rascunho, sem alterar arquivos distribuídos nem publicar release. Lote autorizado pelo maintainer em 2026-09-08 junto com a T002 do consumidor platform.
### Scope and write paths
Somente: `_tl-orc/project/evidence/T002-analysis.md` (análise e delta proposto), `_tl-orc/project/evidence/T002-briefing-template.md` (esqueleto literal mínimo reutilizável por consumidores), `_tl-orc/project/evidence/T002-briefing-skeleton.py` (protótipo não distribuído que deriva o esqueleto do schema), `_tl-orc/project/evidence/T002-cases/` (briefings e respostas da medição). Proibido: qualquer arquivo distribuído (SKILL.md, prompts/, docs/, schemas/, manifesto), `scripts/`, `_tl-orc/PROJECT.md`, outras Tasks.
### Acceptance criteria
AC01 Diagnóstico com as ocorrências registradas de primeira resposta inválida ou incompleta do Classificador, citadas por caminho: smokes v0.4.0 (evidência do platform, r03–r07, conforme o Finding), v0.5.0 (r1 e r3), v0.6.0 (smoke do Claude Code: briefing sem esqueleto literal, duas respostas de Luna estruturalmente inválidas — `model` composto, `cost_basis` em prosa, `tier` fora do enum, `context_revision`/`catalog_revision` ausentes), e as classificações do fonte com esqueleto literal (T005, T009, T010: primeira resposta válida na maioria; padrão recorrente de omissão dos candidatos inelegíveis, cinco ocorrências). Distinguir defeito do briefing, defeito do modelo e condição observada (effort medium).
AC02 Definição do briefing mínimo: esqueleto JSON literal com todos os campos obrigatórios e enums do schema (`schema_version`, `story_id` inclusive `null`, `phase`, `context_revision`, `catalog_revision`, `confidence`, listas `facts`/`uncertainties`/`reclassify_when`, `roles` exatamente os solicitados inclusive `searcher`, candidatos com `harness`/`model`/`effort`/`evidence_ids`/`cost_basis`/`reason`), regra explícita de um candidato por harness na ordem da cadeia informada inclusive os inelegíveis pela política (com o motivo em `reason`), catálogo literal por papel com procedência, IDs de evidência com pertinência e origem, regras de `cost_basis`, e instrução de fechamento. O esqueleto deve ser derivável do schema pelo protótipo, para não divergir dele.
AC03 Medição em smoke sintético (mesma intenção, mesmo catálogo, Luna medium, sessões novas, sem rodada de correção): pelo menos três chamadas com briefing no estilo "schema compacto" em prosa (como no smoke v0.6.0 do Claude Code) e três com o briefing mínimo; validade da primeira resposta conferida por camada mecânica (schema + catálogo + IDs) e registrada por chamada, com totais e limites declarados (N pequeno, um modelo, uma intenção).
AC04 Delta proposto para `prompts/orchestrator-perfis.md` (Briefing concreto) e `prompts/classifier.md`, em rascunho dentro da análise, com texto único por assunto e remissões; distribuição e release explicitamente fora do escopo (Task `fix` própria se autorizada).
AC05 Análise com premissas, alternativas consideradas (schema compacto com exemplo; normalização pelo Orquestrador; effort maior; validação mecânica pós-resposta) e o que mudaria a conclusão.
AC06 Portões: `python3 scripts/validate_repository.py` verde; nenhum arquivo distribuído alterado; nenhum caminho privado; medição reproduzível com comandos registrados; protótipo executável (`python3 _tl-orc/project/evidence/T002-briefing-skeleton.py schemas/classification-result.schema.json --roles planner,maker,checker`).
### Verification profile
`analysis`: premissas, alternativas e o que mudaria a conclusão (AC05); medição reproduzível (AC03, AC06); Checker report-only de família distinta de toda autoria efetiva, com hipótese rejeitada e citação por critério (pin do piloto do fonte: `gpt-6-astra/high`, restrição `required` específica desta revisão).

## Result
(pendente)

## Evidence
(pendente)

## Review
(pendente)
