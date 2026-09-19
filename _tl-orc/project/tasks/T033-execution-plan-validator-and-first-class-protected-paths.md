id: T033
title: Execution Plan Validator and First-Class Protected Paths
type: feat
deliverable: package
standalone: true
method: native
status: in_review
state_revision: 1
depends_on: [T018]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-17, junto com T032, após a constatação de que asserções de portão trafegavam como strings livres sem validação temporal e de que protected paths não tinham verificação estrutural própria.
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
effective_authors: [anthropic]
checker_independence: required
content_paths: [scripts/validate_execution_plan.py, schemas/execution-plan.schema.json, docs/RUNTIME.md, docs/EXECUTION_PROTOCOL.md, tests/test_execution_plan_validator.py, tests/test_story_protected_paths.py, tests/fixtures/auto_story_b013_b014/execution-plan.json, distribution-manifest.json, CHANGELOG.md, README.md, SKILL.md, docs/PROJECT_CONFIGURATION.md, _tl-orc/project/STATUS.md]

## Finding
source: auditoria do plano de execução das propostas e do tratamento de caminhos protegidos durante a especificação do T032.
observed: o plano de execução admitia asserções como texto livre, sem registro fechado e sem qualquer noção de em que momento do ciclo de vida a asserção é decidível — uma asserção como `checker_approved` avaliada antes da revisão, ou `origin_synced` avaliada antes do merge, responde sobre o momento errado e ainda assim passava. Caminhos protegidos, por sua vez, eram tratados por presença textual de padrão, sem verificação estrutural da árvore e sem impedir que um lote filho substituísse o hash esperado ou o snapshot de referência herdado.
expected:
1. Declarar um enum fechado de `lifecycle_phase` (`pre_execution`, `post_maker_pre_review`, `post_checker_pre_merge`, `post_merge_pre_close`, `post_terminal`);
2. Criar um `assertion_registry` fechado mapeando cada `assertion_id` às fases em que é decidível, com parâmetros tipados;
3. Tornar estruturalmente impossível uma string de asserção livre, e recusar `FAIL CLOSED` asserção desconhecida ou em fase incompatível;
4. Provar a satisfatibilidade aritmética do orçamento contra os cenários de retry e straight-line;
5. Implementar protected paths de primeira classe nos modos `read_only`, `exact_file_hash` e `exact_set_snapshot`, com comparação recursiva de `path`, `type`, `size` e `sha256`;
6. Exigir monotonicidade semântica — e não apenas textual — dos protected paths herdados.
impact: o plano de execução passa a ser verificável mecanicamente e no momento certo, e caminhos protegidos deixam de depender da boa fé de quem escreve o padrão.
dedup: T016 definiu a cadência de verificação e os portões de fronteira; T018 congelou o escopo do lote. T033 acrescenta a validação temporal e estrutural desses portões, sem alterar a cadência.

## Spec
### Acceptance criteria
- AC01: `scripts/validate_execution_plan.py` declara `LIFECYCLE_PHASES` fechado e um `ASSERTION_REGISTRY` fechado que mapeia cada `assertion_id` às fases permitidas e aos parâmetros tipados aceitos.
- AC02: `schemas/execution-plan.schema.json` (Draft 2020-12) admite apenas objetos `{assertion_id, parameters}` com `assertion_id` casando `^[a-z][a-z0-9_]*$`, tornando impossível uma string de asserção livre.
- AC03: asserção desconhecida ⟹ `unknown_assertion` (FAIL CLOSED); asserção em `lifecycle_phase` incompatível ⟹ `assertion_phase_mismatch` (FAIL CLOSED); parâmetro ausente, desconhecido ou de tipo errado ⟹ recusa.
- AC04: `gate_call_constraints_are_satisfiable_under_budget` exige a declaração dos cenários `straight_line` e `retry` e prova aritmeticamente que ambos cabem no teto de chamadas.
- AC05: `verify_protected_paths` implementa `read_only` (mutação na árvore de trabalho), `exact_file_hash` (arquivo regular com o SHA-256 exato; symlink ou ausência falha antes da comparação) e `exact_set_snapshot` (comparação recursiva de `path`, `type`, `size` e `sha256`, detectando adição untracked, deleção, alteração de bytes e conversão de arquivo em symlink).
- AC06: ausência de baseline e de git para um caminho `read_only` resulta em `protected_read_only_unverifiable`, nunca em passe silencioso.
- AC07: `assert_protected_paths_monotonic` exige igualdade estrutural dos itens herdados (padrão, policy e parâmetros de hash/snapshot), permite acrescentar proteção e recusa remoção, redução de cobertura, policy mais permissiva e substituição de hash ou snapshot.
- AC08: a validação de schema é feita por um subconjunto estrito de Draft 2020-12 em biblioteca padrão que recusa qualquer keyword não implementada, e todos os schemas do repositório são integralmente enforceáveis por ele.

### Verification
- `python3 -m unittest discover -s tests`
- `python3 scripts/validate_execution_plan.py --plan tests/fixtures/auto_story_b013_b014/execution-plan.json`
- `python3 scripts/validate_execution_plan.py --print-registry`

## Evidence
evidence/T032-T033-verification.md — portões executados, incompatibilidade de ambiente registrada com prova de não regressão contra `origin/main`, e divergências explícitas em relação ao texto do prompt. Veredito de Checker independente upstream ainda pendente.
