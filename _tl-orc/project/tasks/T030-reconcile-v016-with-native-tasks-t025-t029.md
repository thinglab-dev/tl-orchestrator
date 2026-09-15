id: T030
title: Reconcile v0.16.0 with Native Tasks T025–T029
type: gov
deliverable: none
standalone: true
method: native
status: in_progress
state_revision: 1
depends_on: [T029]
blocked_by: []
origin: determinação do mantenedor em 2026-09-15 para reconciliação da branch feat/t029-claude-usage-observation com origin/main@7b25b960 (v0.16.0)
decisions: []
spec_author: orchestrator
spec_revision: c18900b69e1cb3b3
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_paths: [CHANGELOG.md, prompts/maker.md, _tl-orc/project/STATUS.md]

## Finding
source: determinação do mantenedor em 2026-09-15 após diagnóstico da divergência de linhagem Git entre a branch local feat/t029-claude-usage-observation (head 88b7bf5) e origin/main (congelado em 7b25b960 / v0.16.0).
observed: a branch feat/t029-claude-usage-observation divergiu de origin/main em e8e9201 (v0.12.0), carregando a sequência histórica T025/T026/T027/fixes/T029, enquanto origin/main avançou através das releases v0.13.0, v0.14.0, v0.15.0 e v0.16.0 (total de 44 package files). O PR #51 continha acidentalmente todo esse pacote histórico com conflito de mergeable: false. A reconciliação real envolve a interseção de exatamente 5 arquivos, com apenas 2 conflitos textuais (CHANGELOG.md e prompts/maker.md) e 3 auto-merges limpos semanticamente compatíveis (docs/EXECUTION_PROTOCOL.md, prompts/orchestrator-playbook.md, prompts/orchestrator.md). Os 4 content paths aprovados de T029 (scripts/tl_usage.py, schemas/usage-observation.schema.json, scripts/fixtures/tl_usage/claude/, scripts/tests/test_tl_usage_claude.py) são 100% exclusivos da linhagem local e nunca foram tocados por origin/main.
expected: reconciliar de forma limpa, não destrutiva e rastreável a baseline v0.16.0 com as tarefas nativas T025–T029 através de branch dedicada de integração (integrate/reconcile-v0.16-with-t025-t029), preservando integralmente os commits e SHAs históricos (sem rebase, squash ou cherry-pick), assegurando intocabilidade criptográfica de T029 (zero bytes de diff contra 88b7bf5 nos 4 caminhos de T029), resolvendo os 2 conflitos textuais conforme especificado, mantendo a integridade da distribuição v0.16.0 (44 arquivos), submetendo a governança da reconciliação a parecer formal aprovado de Checker independente sob checker_independence: required, abrindo novo PR limpo e fechando o PR #51 sem merge, com STOP final aguardando autorização humana para merge em main.
impact: unifica a árvore de desenvolvimento do tl-orchestrator na versão mais recente v0.16.0 incorporando as capacidades de observabilidade factual de usage (Codex e Claude) e journaling orçado (T027) sem quebra de linhagem nem perda de histórico.
hypothesis: a criação de uma branch de integração dedicada com merge commit explícito preserva a linhagem de ambas as histórias, permite auditoria independente do diff de reconciliação e cumpre integralmente os requisitos de governança do repositório.
dedup: T024 reconciliou linhagens de v0.11 com T018; T028 permanece rascunho futuro não reutilizado; T030 governa a reconciliação de v0.16.0 com T025–T029.

## Spec
### Intent
1. Reconciliar a baseline remota congelada `origin/main@7b25b960d631bd1372b8ec01243a04347f484506` (`v0.16.0`) com os commits históricos locais T025–T029 originários de `feat/t029-claude-usage-observation` (`88b7bf564ffa34aa5885af48ba41afeed2609809`).
2. Preservar rigorosamente a história Git existente (sem `rebase`, sem `squash`, sem `cherry-pick`), mantendo intactos os SHAs históricos das tarefas locais.
3. Garantir a intocabilidade criptográfica absoluta da implementação de T029: diff zero contra `88b7bf5` nos 4 caminhos de conteúdo (`scripts/tl_usage.py`, `schemas/usage-observation.schema.json`, `scripts/fixtures/tl_usage/claude/`, `scripts/tests/test_tl_usage_claude.py`).
4. Resolver os dois conflitos textuais reais:
   - `CHANGELOG.md`: manter as notas de T027 sob `## [Unreleased]`; preservar integralmente as seções `## [0.16.0]`, `## [0.15.0]`, `## [0.14.0]`, `## [0.13.0]` e links correspondentes; não fabricar releases para tarefas de escopo puramente interno (`deliverable: none`).
   - `prompts/maker.md`: conciliar regras de UI profiles, verificação direcionada antes de passagens completas, proibição de full gates de sistema em ambiente sandbox intermediário sem rede (T016/T027), opt-in de `workflow_quality` e comandos literais de allowlist.
5. Preservar os 3 arquivos auto-mesclados limpos (`docs/EXECUTION_PROTOCOL.md`, `prompts/orchestrator-playbook.md`, `prompts/orchestrator.md`).
6. Reconciliar `_tl-orc/project/STATUS.md` garantindo que T001–T024 reflitam o estado unificado, T025–T027 estejam `done`, T028 permaneça `draft`, T029 esteja `done`, T030 esteja registrado e `next_task_id` seja avançado para 31.
7. Preservar o manifesto canônico de distribuição de v0.16.0 (44 package files) verificado por `scripts/validate_repository.py`.
8. Executar e aprovar todos os testes unitários (`scripts/tests/` e `tests/`), integridade de linhagem (`scripts/audit_lineage.py`) e validação estrutural.
9. Obter parecer formal `approved` (0 action items) de Checker independente sob `checker_independence: required`.
10. Publicar PR de integração no GitHub, encerrar PR #51 sem merge apontando para o novo PR, e parar solicitando autorização humana explícita para o merge final em `main`.

### Scope and write paths
- `CHANGELOG.md`: resolução do conflito mantendo T027 sob Unreleased e 0.16.0..0.13.0 abaixo.
- `prompts/maker.md`: resolução do conflito unificando regras de UI profiles e targeted verification T016/T027.
- `_tl-orc/project/STATUS.md`: registro de T030 e avanço de `next_task_id: 31`.
- `_tl-orc/project/tasks/T030-reconcile-v016-with-native-tasks-t025-t029.md`: especificação da tarefa de governança.
- `_tl-orc/project/evidence/T030-r01.md`: evidência e parecer de revisão independente da reconciliação.

### Acceptance Criteria
- AC1: A branch de integração `integrate/reconcile-v0.16-with-t025-t029` foi criada a partir de `88b7bf5` e mesclou `7b25b960` preservando ambas as linhagens sem rebase nem squash.
- AC2: `git diff 88b7bf5 -- scripts/tl_usage.py schemas/usage-observation.schema.json scripts/fixtures/tl_usage/claude/ scripts/tests/test_tl_usage_claude.py` retorna exatamente zero bytes.
- AC3: Conflitos em `CHANGELOG.md` e `prompts/maker.md` resolvidos sem marcadores residuais de conflito.
- AC4: `_tl-orc/project/STATUS.md` atualizado com T025–T027 `done`, T028 `draft`, T029 `done`, T030 `done` (ao final), `next_task_id: 31` e compatível com CAS e `audit_lineage.py`.
- AC5: `python3 scripts/validate_repository.py` executa com sucesso validando exatamente os 44 arquivos canônicos da distribuição v0.16.0.
- AC6: `python3 -m unittest discover -s scripts/tests -v` e `python3 -m unittest discover -s tests -v` executam com sucesso (100% pass).
- AC7: `python3 scripts/audit_lineage.py` executa sem blockers (exit 0).
- AC8: Parecer formal `approved` emitido por Checker independente de família distinta sob `checker_independence: required` em `_tl-orc/project/evidence/T030-r01.md`.
- AC9: Novo PR aberto no GitHub para a branch de integração e PR #51 encerrado sem merge com apontamento explícito para o novo PR.
- AC10: NENHUM merge na branch `main` é realizado sem autorização humana explícita do usuário.

## Verification profile
gov: execução de `scripts/validate_repository.py` (44 arquivos), `scripts/audit_lineage.py` (exit 0), regressão integral de `tests/` e `scripts/tests/`, verificação criptográfica de diff zero em T029, e parecer formal de Checker independente sob `checker_independence: required`.
