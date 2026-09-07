id: T006
type: fix
deliverable: none
standalone: true
method: native
status: draft
state_revision: 0
depends_on: []
blocked_by: []
origin: user (achado de condução em 2026-09-07: T005 no fonte e smoke de roteamento v0.5.0 no consumidor platform)
decisions: []
spec_author: none
content_paths: [prompts/orchestrator-perfis.md, prompts/orchestrator-playbook.md]

## Finding
source: `codex exec resume <sessão>` sem `-m` nas correções únicas do Classificador (fonte T005: duas vezes; platform, smoke v0.5.0 em Claude Code: uma vez)
expected: a correção única corre no mesmo modelo e effort classificados para a sessão (perfil fixo do Classificador: Luna → Sonnet → Flash)
observed: a CLI reabre a sessão com o modelo padrão da configuração (`gpt-5.6-terra` ou `gpt-6-astra`) e só avisa no stderr ("session recorded with gpt-5.6-luna but resuming with ..."); o Orquestrador não repetiu `-m` nem o effort e adotou objetos produzidos fora do perfil
impact: objeto de classificação fora do perfil autorizado adotado como válido; registro de harness/modelo incorreto nas tabelas Agent runs
hypothesis: o contrato manda "Passe modelo e effort explicitamente" no despacho, mas não diz que a correção por resume é um novo despacho sujeito à mesma regra, nem manda conferir o stderr do resume
next verification: acrescentar em "Classificar e resolver" (perfis) e no playbook que todo `resume` de sessão de papel repete modelo e effort e confere o aviso de modelo; sonda: smoke com correção única em Codex mostrando `model:` igual ao classificado no stderr do resume
dedup: T003 trata de avançar a cadeia quando a correção é impossível; este achado é distinto (correção possível, modelo trocado)
