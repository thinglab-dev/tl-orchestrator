id: T001
type: fix
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: platform v0.4.0 update evidence (smoke de triagem, Codex gpt-5.6-luna, sessão 01a0790b-8ea1-72d0-bf97-691b982ae8e4, 2026-09-06)
decisions: []
spec_author: none
content_paths: [SKILL.md]

## Finding
source: SKILL.md (v0.4.0) parágrafo do menu de ativação: "Executar fila sequencial somente com board ou fila declarada" e "só inclua fila quando houver board ou fila declarada"
expected: sem QUEUE.md e sem board declarado, a opção de fila não aparece no menu
observed: a sessão Codex em triagem no platform ofereceu "3. Executar fila sequencial somente com board ou fila declarada" sem board; a sessão Claude Code no mesmo estado não ofereceu
impact: divergência do contrato; risco de o usuário escolher fila inexistente
hypothesis: a redação do item ("somente com board ou fila declarada") é lida como rótulo da opção, não como condição de inclusão
next verification: reescrever a frase do SKILL.md separando a condição do rótulo; smoke de triagem em Codex e Claude Code confirmando ausência da opção sem board; sonda contrafactual: com QUEUE.md declarando board, a opção deve aparecer
