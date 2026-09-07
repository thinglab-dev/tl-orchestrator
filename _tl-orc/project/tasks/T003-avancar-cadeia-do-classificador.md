id: T003
type: analysis
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: platform v0.4.0 update evidence (Codex como Orquestrador, rodadas r05–r07, 2026-09-07)
decisions: []
spec_author: none
content_paths: [prompts/orchestrator-perfis.md]

## Finding
source: relatórios de smoke Codex como Orquestrador
observed: quando a correção única do Classificador é impossível (sessão Claude sem session_id exposto; `--resume` não encontrado no sandbox), o Orquestrador parou em vez de avançar ao próximo candidato da cadeia do Classificador; o contrato descreve a cadeia como fallback sequencial, mas não diz explicitamente que a impossibilidade de corrigir equivale a esgotar o candidato
hypothesis: lacuna de redação em "Classificar e resolver" / "Fallback e interrupção"
next verification: analisar se avançar a cadeia após correção impossível é compatível com "não consulte outros modelos até obter uma classificação conveniente"; propor redação; distinguir de indisponibilidade de infraestrutura
