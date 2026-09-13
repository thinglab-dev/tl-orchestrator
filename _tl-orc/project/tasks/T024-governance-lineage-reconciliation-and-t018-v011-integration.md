id: T024
title: Governance Lineage Reconciliation and T018/v0.11 Integration
type: gov
deliverable: none
standalone: true
method: native
status: ready
state_revision: 0
depends_on: [T015, T018]
blocked_by: []
origin: decisão normativa do mantenedor em 2026-09-13 (aceite da Estratégia D do Advisor — Reseat · Delegate · Serial-by-declaration — com as cinco decisões humanas mandatórias H1 a H5)
decisions: []
spec_author: planner
spec_revision: 948c44332c6f8195
rework_round: 0
affects_context: []
provenance: []
integration_base: 2aca4f42bdd399c943ad4a5afeb403725018f6ae
integration_target: unknown até a implementação
integration_content_id: 2aca4f42bdd399c943ad4a5afeb403725018f6ae:651a76ce753ec023
content_id: 2aca4f42bdd399c943ad4a5afeb403725018f6ae:651a76ce753ec023
effective_authors: [google, anthropic]
checker_independence: required
content_paths: [_tl-orc/project/lineage-map.md, _tl-orc/project/STATUS.md, _tl-orc/project/tasks/T020-regras-contratuais-de-esperas-liveness-e-lote-autorizado.md, _tl-orc/project/tasks/T021-politica-global-de-participantes-e-perfis-padrao.md, _tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md, _tl-orc/project/tasks/T023-piloto-retomada-curta-entre-ciclos.md, _tl-orc/project/tasks/T024-governance-lineage-reconciliation-and-t018-v011-integration.md, _tl-orc/project/tasks/T016-verification-cadence-targeted-tests-and-major-boundary-integration-gates.md, _tl-orc/project/tasks/T019-dynamic-primary-harness-selection-separate-quality-ranking-from-infrastructure-fallback.md, scripts/audit_lineage.py, scripts/tests/test_audit_lineage.py, schemas/batch.schema.json, scripts/tests/test_automatic_mode.py, docs/EXECUTION_PROTOCOL.md, docs/WORK_MODEL.md, prompts/orchestrator-playbook.md, prompts/orchestrator.md, SKILL.md, README.md, distribution-manifest.json, docs/PROJECT_CONFIGURATION.md, CHANGELOG.md, .github/workflows/validate.yml]

## Finding
source: auditoria de linhagem conduzida em 2026-09-13 sobre origin/main@2aca4f4 (v0.11.0) e feat/t018-automatic-mode@55a3ca9, a partir do parecer consultivo do Advisor (adjust, Estratégia D) e das cinco decisões humanas mandatórias H1–H5 do mantenedor.
observed: o tl-orchestrator sofreu divergência estrutural entre a linhagem local de governança (T013–T018) e a linhagem upstream (v0.9.0–v0.11.0). Isso produziu: (1) colisão tripla de task IDs (T013, T014, T015 alocados independentemente em ambas as linhagens); (2) colisão intra-linhagem pré-existente e órfã de T012 com o piloto T012-piloto; (3) re-binding semântico silencioso de dependências operacionais (como T016 dependendo falsamente de concorrência física em vez de context economy); (4) ausência de guarda mecânica de integridade de board e tasks; (5) incompatibilidade com o CAS atômico de STATUS.md do v0.11; (6) autoridade contraditória sobre auto_merge; e (7) sobreposição não documentada de responsabilidades entre governança e runtime físico.
expected: reconciliar as linhagens em um grafo operacional único, acíclico e com identidades biunívocas; reseat cirúrgico de IDs locais colididos para T020–T023; T012 upstream como canônica done; T018 intocada em spec e parecer histórico; T024 como integration overlay formal; remoção completa de auto_merge; declaração explícita da matriz de responsabilidades governança vs. runtime; e guarda mecânica determinística (scripts/audit_lineage.py e suíte de testes).
impact: elimina o risco de execução de código com dependências falsas, restaura a operabilidade do runtime v0.11 e previne a reintrodução de colisões de linhagem.
hypothesis: a criação de um mapa de linhagem com digest, aliada a um validador de integridade relacional executado no CI e pré-transição, estabiliza a governança sem descaracterizar as entregas prévias.
dedup: T013–T015 upstream entregaram mecanismo físico; T016 fixou cadência de verificação; T017 introduziu o Advisor; T018 unificou a governança do Modo Automático. T024 não reimplementa nada de T013–T018: reconcilia identidades, declara fronteiras e instala guarda mecânica.

## Spec
### Intent
Reconciliar as duas linhagens de governança do tl-orchestrator em um grafo operacional único, acíclico e de identidades únicas; declarar e tornar testável a fronteira de autoridade entre a governança do Modo Automático (T018) e o runtime físico de execução concorrente (v0.11); e instalar a guarda mecânica determinística que impede a reintrodução da classe de defeito que produziu a colisão.

T024 não altera comportamento de runtime, não reabre T018, não reescreve evidência histórica, não implementa T019 e não introduz nova funcionalidade de orquestração.

### Scope and write paths
- _tl-orc/project/lineage-map.md: mapa de linhagem com digest criptográfico, registrando identidades aposentadas, prefixos de evidência, procedência histórica e limites de replayabilidade.
- _tl-orc/project/STATUS.md: board reconciliado com 24 tasks T001–T024, formato canônico de 8 células por linha, compatível com CAS v0.11.
- _tl-orc/project/tasks/T020-regras-contratuais-de-esperas-liveness-e-lote-autorizado.md: reseat de T013 local.
- _tl-orc/project/tasks/T021-politica-global-de-participantes-e-perfis-padrao.md: reseat de T014 local, depends_on: [T020].
- _tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md: reseat de T015 local, depends_on: [], provenance: [T023].
- _tl-orc/project/tasks/T023-piloto-retomada-curta-entre-ciclos.md: reseat de T012 piloto, status: ready preservado, depends_on: [T010, T021].
- _tl-orc/project/tasks/T024-governance-lineage-reconciliation-and-t018-v011-integration.md: especificação formal do overlay de integração.
- _tl-orc/project/tasks/T016-verification-cadence-targeted-tests-and-major-boundary-integration-gates.md: correção de aresta operacional para [T022].
- _tl-orc/project/tasks/T019-dynamic-primary-harness-selection-separate-quality-ranking-from-infrastructure-fallback.md: depends_on: [T018, T024], blocked_by: [T024].
- scripts/audit_lineage.py: guarda mecânica relacional de linhagem, tasks e board.
- scripts/tests/test_audit_lineage.py: suíte de testes cobrindo as checagens relacionais L01–L14 e compatibilidade com CAS v0.11.
- schemas/batch.schema.json: adição de batch_concurrency: 1 obrigatório em frozen_scope e runtime_refs em execution.
- scripts/tests/test_automatic_mode.py: atualização de fixtures para batch_concurrency: 1 e testes contratuais da fronteira.
- docs/EXECUTION_PROTOCOL.md: remoção de menções a auto_merge, incorporação da matriz de responsabilidades e regras de precedência contra parked.
- docs/WORK_MODEL.md: sincronização de responsabilidades de governança vs runtime, provenance e protocolo de transição.
- prompts/orchestrator-playbook.md: remoção de menções a auto_merge, incorporação da matriz de responsabilidades e precedência de parada em lote.
- prompts/orchestrator.md, SKILL.md, README.md, distribution-manifest.json, docs/PROJECT_CONFIGURATION.md: sincronização do pacote em 22 arquivos canônicos.
- CHANGELOG.md: notas da reconciliação T024 em Unreleased preservando histórico v0.9–v0.11.
- .github/workflows/validate.yml: inclusão de scripts/tests/ e audit_lineage.py no CI canônico.

### Acceptance criteria
AC01 (Reseat T013-local → T020): O arquivo passa a se chamar T020-regras-contratuais-de-esperas-liveness-e-lote-autorizado.md com id: T020. status, state_revision: 2, spec_revision: 073029a7b89760b9, content_id: b06d37e3cca2f9f4507287c3ee25e7437db47f18:9e6cc414bfa89fbb, origin e todo o corpo da spec inalterados. depends_on: [T011] inalterado.
AC02 (Reseat T014-local → T021): Idem, com id: T021, spec_revision: 3462d25f16aba270, e depends_on: [T020] (correção de aresta ambígua).
AC03 (Reseat T015-local → T022): id: T022, spec_revision: c563bbdf24f712c1, content_id: 3e9ecc356b839dbe5e736e5356219bb092a4ff00:2c0e0630d7ae53ed, depends_on: [], provenance: [T023].
AC04 (Reseat do piloto T012 → T023): id: T023, status: ready preservado, state_revision: 1, spec_revision: 9c64bc99ae8a8e24, depends_on: [T010, T021], ## Result/## Evidence/## Review preservados byte a byte. Registro explícito de replayability: not_reconstructable com a razão factual. Proibido marcar done.
AC05 (Preservação de T016–T019 e das identidades upstream): Os arquivos de T016, T017, T018, T019 mantêm seus nomes e id. T013/T014/T015 upstream intocados (nome, id, frontmatter, corpo).
AC06 (T018 estritamente intocada): O arquivo T018-*.md é byte-idêntico ao de feat/t018-automatic-mode.
AC07 (Correção das arestas estruturais): Exatamente estas quatro arestas mudam: T016: [T015] → [T022]; T021: [T013] → [T020]; T022: [T012] → []; T023: [T010,T014] → [T010,T021]. Mais T019: [T018] → [T018,T024] + blocked_by: [T024]. Nenhuma outra aresta é alterada.
AC08 (Distinção provenance × dependência): Nenhuma task com status: done tem depends_on para task com status != done. Em particular T022 (done) não depende de T023 (ready). A relação T022→T023 existe somente como provenance e em lineage-map.md.
AC09 (Imutabilidade da evidência): Nenhum arquivo sob _tl-orc/project/evidence/ foi renomeado, movido, editado ou removido.
AC10 (Mapa de linhagem com digest): _tl-orc/project/lineage-map.md existe, cobre as 4 identidades aposentadas, o mapa de prefixos de evidência, a procedência histórica e a replayabilidade; lineage_digest confere.
AC11 (Board reconciliado): 24 linhas T001–T024, exatamente 8 células por linha, next_task_id: 25, campos active_batch/batch_status/next_batch_id presentes. T011 na forma da linhagem local (done, state_revision 2, evidence/T011-r02.md) por R-U1.
AC12 (Paridade board ↔ frontmatter): Para todo id: type, status, depends_on, blocked_by, state_revision são idênticos entre a linha do board e o frontmatter do arquivo.
AC13 (CAS v0.11 operacional sobre o board reconciliado): update_task_status_atomic() resolve toda linha T001–T024 sem invalid_board e sem task_not_found. Teste determinístico sobre cópia temporária do board, com rollback.
AC14 (scripts/audit_lineage.py detecta as classes relacionais): duplicate task id, duplicate active identity, unresolved depends_on, ambiguous depends_on, ciclos, quebra de bijeção, etc. Saída <path>:<linha>: BLOCKER [<classe>]: <mensagem>, exit 1 com qualquer BLOCKER, exit 0 limpo.
AC15 (Suíte contrafactual): scripts/tests/test_audit_lineage.py cobre todos os casos de teste sobre fixtures sintéticas, incluindo o controle positivo (árvore real passa) e os controles negativos por sonda.
AC16 (auto_merge removido das fontes de autoridade): Nenhuma ocorrência de auto_merge/auto-merge em prompts/orchestrator-playbook.md e docs/EXECUTION_PROTOCOL.md. CHANGELOG.md preservado. Merge Queue, FIFO, enqueue_merge, estados merging/merged/failed, timeout de 120 s e tolerância de 30 s preservados textualmente.
AC17 (Autoridade de merge declarada): SKILL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md e docs/EXECUTION_PROTOCOL.md afirmam, sem contradição entre si, que merge em main exige autorização humana explícita e que a Merge Queue apenas ordena merges já autorizados sem conceder autoridade.
AC18 (batch_concurrency: 1): schemas/batch.schema.json tem frozen_scope.properties.batch_concurrency = {"const": 1} e batch_concurrency em frozen_scope.required. Um Bnnn.md com batch_concurrency: 2 reprova; sem o campo, reprova. Coberto por immutable_digest.
AC19 (Precedência sobre parked): Teste contratual: lote com continue_independent_after_block: false + gatilho de parking => batch_status: stopped com stop_reason pertencente a {rework_limit_exhausted, bad_spec_or_intent_gap, dependency_block} e zero unidades admitidas depois. Contrafactual: true => avança apenas para unidade independente dentro do frozen_scope.
AC20 (runtime_refs no bloco mutável): execution.properties.runtime_refs presente, additionalProperties: false, fora de execution.required. Contrafactual: frozen_scope.runtime_refs => reprova por additionalProperties: false. runtime_refs não participa do cálculo de immutable_digest.
AC21 (Matriz de delegação documentada): docs/EXECUTION_PROTOCOL.md e docs/WORK_MODEL.md contêm a matriz das 10 responsabilidades de §4.2, nomeando literalmente acquire_worktree_slot, claim_scope, enqueue_merge, sweep_orphan_worktrees e update_task_status_atomic como runtime físico, e o envelope Bnnn.md como autoridade.
AC22 (Manifesto unificado em 22 arquivos): distribution-manifest.json com package_file_count: 22 e a união exata (19 upstream + prompts/advisor.md + schemas/advisor-result.schema.json + schemas/batch.schema.json). README sincronizado: lista, string exatamente 22 arquivos, bloco de export e bloco de checksums.
AC23 (Gate unificado no CI e local): .github/workflows/validate.yml executa, em passos distintos: validate_repository.py; unittest discover -s tests; unittest discover -s scripts/tests -t .; audit_lineage.py. As suítes de scripts/tests/ passam pelo CI.
AC24 (Regressão integral): Todas as suítes preexistentes passam sem modificação de asserções, exceto as fixtures de test_automatic_mode.py estritamente exigidas por AC18/AC20. Nenhuma asserção é afrouxada.
AC25 (Identidade de integração): integration_base: 2aca4f42bdd399c943ad4a5afeb403725018f6ae; integration_target = commit de integração reconciliado; integration_content_id = <integration_base>:<hash16 do diff> no formato canônico de docs/WORK_MODEL.md. Distinto do content_id de T018.
AC26 (Revisão independente): Parecer report-only de família distinta de todos os autores efetivos do diff de T024, sob checker_independence: required, cobrindo os 23 content_paths com spec_revision e integration_content_id do alvo. Evidência em _tl-orc/project/evidence/T024-r01.md.
AC27 (T019 estritamente bloqueada): T019.depends_on: [T018, T024], T019.blocked_by: [T024], status: ready. Enquanto T024.status != done, T019 é inelegível para despacho.

## Verification profile
gov: execução de scripts/audit_lineage.py (exit 0), suíte scripts/tests/test_audit_lineage.py (exit 0), regressão integral de tests/ e scripts/tests/, validação estrutural do repositório python3 scripts/validate_repository.py (exit 0) e auditoria de Checker independente de família distinta sob checker_independence: required.
