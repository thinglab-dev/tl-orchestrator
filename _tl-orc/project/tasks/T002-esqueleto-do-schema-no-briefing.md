id: T002
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: platform v0.4.0 update evidence (smokes r03–r07, 2026-09-06/07)
decisions: []
spec_author: none
content_paths: [prompts/orchestrator-perfis.md, prompts/classifier.md, docs/MODEL_ROUTING.md]

## Finding
source: relatórios de smoke em Claude Code e Codex como Orquestrador
observed: o Classificador (Codex gpt-5.6-luna e Claude sonnet) devolveu respostas estruturalmente inválidas em várias primeiras chamadas (campos obrigatórios ausentes, campo extra, tier "primary", confidence numérico, facts como objetos); incluir no briefing o esqueleto literal do schema com enums e a lista de campos obrigatórios eliminou as falhas nas rodadas seguintes
hypothesis: o briefing padrão de "schema compacto" não é específico o bastante; a melhoria é definir no contrato o esqueleto mínimo a enviar
next verification: analisar orchestrator-perfis.md e classifier.md; propor texto normativo do esqueleto; medir taxa de resposta válida na primeira chamada em smoke sintético antes e depois
