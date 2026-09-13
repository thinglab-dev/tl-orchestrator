id: T013
type: feat
deliverable: package
standalone: true
method: native
status: done
state_revision: 1
depends_on: []
blocked_by: []
origin: user (2026-09-12: "A e vá orquestrando até terminar de fazer as 3 skills com maxima qualidade /tl-orchestrator", "Cade não criou release nova no tl-orchestrator isso é um update")
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
content_paths: [prompts/planner.md, prompts/maker.md, prompts/checker-report-only.md, prompts/orchestrator-playbook.md, README.md, SKILL.md, CHANGELOG.md, skills/tl-spec-hardener/SKILL.md, skills/tl-impeccable-design/SKILL.md, skills/tl-deep-review/SKILL.md]
content_id: auto
worktree: branch feat/skills-especializadas

## Finding
source: solicitação de Erick e refinamento multi-modelo com Gemini, Claude Code e OpenAI Codex
observed: Os papéis do Orquestrador (Planner, Maker e Checker) operavam sob contratos genéricos que dependiam fortemente do alinhamento do prompt do modelo em cada execução. Falhas recorrentes em projetos consumidores incluíam: (1) specs do Planner com critérios vagos, sem pré-mortem e sem mapeamento estrito de arquivo:linha; (2) entregas de UI pelo Maker com vícios de "AI-slop", falta de escala modular, contraste inacessível e estados interativos ausentes; (3) revisões superficiais do Checker que não auditavam concorrência/TOCTOU, vazamento de recursos, fail-closed e testes falsificáveis.
expected: O pacote `tl-orchestrator` deve incorporar formalmente três disciplinas especializadas nos contratos dos papéis, acompanhadas de scripts de auditoria mecânica e diretrizes de engenharia:
(a) Planner: `tl-spec-hardener` (pré-mortem, fronteiras invioláveis, Code Map estrito em arquivo:linha, critérios falsificáveis com `- [ ]` e validador `audit_spec.py`);
(b) Maker: `tl-impeccable-design` (diretrizes de design profissional sem AI-slop, escala modular 4px/8px, WCAG AA >= 4.5:1, 5 estados interativos e validador `audit_ui.py`);
(c) Checker: `tl-deep-review` (4 lentes obrigatórias: concorrência/TOCTOU, vazamentos de recursos, fail-closed/erros, falsificabilidade de testes e validador `audit_diff.py`).
impact: Elevação imediata da confiabilidade, rigor arquitetural, ergonomia de UI e blindagem contra bugs silenciosos em qualquer projeto orquestrado.

## Spec
### Intent
Incorporar formalmente nos contratos dos papéis e no repositório canônico do `tl-orchestrator` as 3 skills especializadas com seus respectivos validadores determinísticos e documentação completa, publicando a release `v0.9.0`.
### Scope and write paths
- `prompts/planner.md`: inclusão do padrão `tl-spec-hardener`.
- `prompts/maker.md`: inclusão do padrão `tl-impeccable-design`.
- `prompts/checker-report-only.md`: inclusão das 4 lentes `tl-deep-review`.
- `prompts/orchestrator-playbook.md`: instrução de injeção e cumprimento nos briefings.
- `skills/`: disponibilização das 3 skills completas e seus scripts de auditoria.
- `CHANGELOG.md`: documentação da release v0.9.0.
- `_tl-orc/project/STATUS.md`: atualização de status e contadores.
