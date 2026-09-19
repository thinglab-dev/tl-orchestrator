id: T034
title: Remote Orchestrator Handoff, ChatGPT+RDC Entry and Owner-Direct Flow
type: feat
deliverable: package
standalone: true
method: native
status: draft
state_revision: 0
depends_on: [T032, T033]
blocked_by: []
origin: decisão do maintainer em 2026-09-19 para reduzir consumo de quotas locais mantendo ChatGPT+RDC como plano de controle, Codex como Maker e uma família independente como Checker.
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
effective_authors: [openai]
checker_independence: required
content_paths: [SKILL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, prompts/orchestrator-perfis.md, scripts/tl_handoff.py, scripts/validate_classification.py, scripts/tests/test_dynamic_primary_selection.py, docs/PROJECT_CONFIGURATION.md, docs/WORK_MODEL.md, docs/EXECUTION_PROTOCOL.md, tests/test_remote_orchestrator_handoff.py, README.md, CHANGELOG.md, distribution-manifest.json, _tl-orc/PROJECT.md, _tl-orc/project/STATUS.md]

## Finding
source: uso real do maintainer durante o fechamento de T032/T033, conduzindo Git, worktrees, processos, testes e GitHub pelo ChatGPT conectado ao computador via Remote Desktop Commander.
observed: o Orchestrador local consome quota dos mesmos harnesses caros usados como Planner, Maker e Checker para grande volume de trabalho mecânico; ao mesmo tempo, o ChatGPT+RDC consegue executar a coordenação local sem precisar manter Claude Code ou Codex como sessão longa de controle.
expected:
1. na ativação do Orquestrador, detectar deterministicamente se Codex está instalado e executável sem chamada cognitiva;
2. quando a capacidade remota estiver habilitada e Codex estiver pronto, oferecer ao maintainer escolha entre continuar localmente ou transferir a condução para ChatGPT+RDC;
3. preservar exatamente uma autoridade de condução por vez, sem dois coordenadores escritores;
4. permitir retorno explícito da condução remota para uma sessão local;
5. usar o fluxo preferido ChatGPT+RDC → Codex Maker/Rework → Checker independente;
6. tratar quota esgotada como indisponibilidade operacional, nunca como redução de independência ou qualidade.
impact: reduz consumo de quota do Planner/Maker/Checker em trabalho mecânico, permite continuidade quando uma assinatura fica temporariamente sem cota e mantém os gates e a autoria auditáveis.
dedup: T022 reduz contexto e melhora handoff entre ciclos; T018/T032 governam execução durável e autoridade de batch/Story. T034 governa quem possui a condução entre uma sessão local e ChatGPT+RDC e não substitui esses mecanismos.

## Spec
### Acceptance criteria
- AC01: o preflight remoto é puramente local e executa no mínimo `command -v codex` e `codex --version`; não reserva budget nem dispara modelo. Resultado fechado: `ready`, `missing`, `invalid` ou `unknown`.
- AC02: a opção **ChatGPT + RDC** só aparece quando a capacidade remota estiver habilitada e o Codex local estiver `ready`. Falha no preflight mantém **Continuar localmente** disponível e informa o motivo sem fallback silencioso.
- AC03: escolher o modo remoto cria um handoff privado e não versionado com ID opaco, repo root, branch, HEAD, dirty-state, active_work_ref, fase, papéis, famílias e revisão do contexto; nenhum segredo, token ou credencial pode entrar no artefato.
- AC04: o estado do handoff é fechado em `created → claimed → active → completed` ou `created|claimed|active → returned_to_local`. Replay, duplo claim e transição inválida falham fechado.
- AC05: `claim` revalida repo root, identidade Git, branch, HEAD, working tree, Codex e revisão do handoff antes de conceder condução. Divergência exige novo handoff ou retorno explícito; não é normalizada automaticamente.
- AC06: antes de tornar o handoff `active`, o coordenador local deve ter liberado sua autoridade/lease. O mecanismo impede dois escritores concorrentes e registra quem possui a condução.
- AC07: no modo remoto preferido, ChatGPT+RDC atua como Orchestrator+Planner, Codex como Maker/Rework e o Checker é resolvido por família independente de toda autoria efetiva; para produção OpenAI, Claude é preferido e Agy/Gemini é fallback independente.
- AC08: quota, autenticação ou indisponibilidade de Claude tornam Claude apenas indisponível. Se OpenAI já é autora, Gemini pode tornar-se Checker; Gemini não deve ser promovido a Maker quando isso eliminaria a única família independente disponível.
- AC09: operações mecânicas do ChatGPT/RDC (Git, worktrees, testes, CI, GitHub, processos, leitura e empacotamento de contexto) não entram em `effective_authors`; planejamento, spec, decisão arquitetural ou patch substantivo entram como autoria OpenAI.
- AC10: o modo remoto pode gerar `returned_to_local`; a ativação local reconhece esse estado, revalida a árvore e oferece retomar localmente ou criar nova transferência remota. Nenhum contexto conversacional é autoridade por si só.
- AC11: o handoff é compacto e recuperável por ID, mas todas as decisões relevantes apontam para fontes versionadas ou evidências duráveis; não copiar histórico longo, logs integrais ou segredos para o artefato.
- AC12: para o repositório fonte sob autoridade do maintainer, o fluxo suporta integração `owner-direct` depois de gates, Checker exigido e CI no SHA exato. PR permanece opcional salvo contribuição externa, decisão deliberada ou proteção da plataforma que o exija.
- AC13: o modo local atual continua compatível por omissão; consumidores que não habilitam handoff remoto não recebem novo requisito operacional.
- AC14: testes determinísticos cobrem Codex ausente/inválido, HEAD/branch/dirty drift, duplo claim, replay, handoff adulterado, coordenador local ainda ativo, return local, Checker sem família independente e seleção Gemini quando Claude está sem quota.
- AC15: o perfil global publicado prefere Gemini/Agy para Classifier e Searcher; ChatGPT+RDC para Orchestrator+Planner quando o handoff remoto estiver ativo; Planner local Codex → Claude → Agy; Maker Codex → Agy → Claude; Checker Claude → Agy → Codex após filtrar famílias autoras. O resolver mecânico de Maker usa Codex `gpt-5.6-terra/high` como primeiro candidato, Gemini como fallback e `xhigh` apenas como escalada factual.

### Verification
- `python3 -m unittest discover -s tests -p 'test_remote_orchestrator_handoff.py'`
- `python3 scripts/validate_repository.py`
- `python3 scripts/audit_lineage.py`
- `git diff --check`

## Evidence
Ainda não executada. A implementação deve ser feita somente após T032/T033 fecharem e a baseline de `main` incorporar a release correspondente.
