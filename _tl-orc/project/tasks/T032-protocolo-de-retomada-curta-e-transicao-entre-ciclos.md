id: T032
title: Protocolo de Retomada Curta e Transicao entre Ciclos
type: feat
deliverable: package
standalone: true
method: native
status: ready
state_revision: 1
depends_on: [T022, T023]
blocked_by: []
origin: user (autorizacao formal em 2026-09-17 para institucionalizar as conclusoes de T023 e a base tecnica de T022)
decisions: []
spec_author: orchestrator
spec_revision: a3c5405a2602566a
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_paths:
  - docs/WORK_MODEL.md
  - docs/EXECUTION_PROTOCOL.md
  - docs/CONTEXT_POLICY.md
  - prompts/orchestrator.md
  - prompts/orchestrator-playbook.md
  - schemas/resume-manifest.schema.json
  - scripts/resume_generate.py
  - scripts/tests/test_resume_generate.py
  - _tl-orc/project/STATUS.md
  - _tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md

## Finding
source: conclusoes empiricas de T023 (_tl-orc/project/evidence/T023-r01.md), base tecnica de T022 (_tl-orc/project/tasks/T022-*.md / evidence/T015-r03b.md), parecer consultivo do Advisor (evidence/T032-support/phase-a/02-advisor/advisor-verdict.json) e autorizacao do mantenedor em 2026-09-17
observed:
  1. T023 provou que a retomada em sessao limpa a partir de um Pacote Curto de Retomada como indice nao-tautologico de conferencia obrigatoria previne vicios cognitivos de historico longo e assegura 100% de aderencia a governanca (zero violacoes X1-X4 no Braco B contra violacao X2 no Braco A), com 81,8% de cache hit de prefixo no harness (356.864 tokens).
  2. No entanto, o piloto foi um experimento delimitado (N=1 pareado sobre checkpoint adaptado T009 r02). Conforme evidenciado na Tabela SS7.2 de T023-r01.md, o Braco B consumiu 436.372 tokens de entrada bruta contra 64.701 do Braco A (custo bruto de tokens cerca de 6,5x maior), demonstrando que a retomada curta decorre de trade-offs de infraestrutura (prefix cache) e nao garante reducao incondicional de tokens brutos em todos os cenarios.
  3. A auditoria do Advisor revelou lacunas concretas entre o estado herdado de T022 e os requisitos de robustez do protocolo:
     - O schema schemas/resume-manifest.schema.json nao contem state_revision, content_id, generated_at nem generator_version, impedindo distinguir alteracoes de status de alteracoes na secao Spec;
     - scripts/resume_generate.py nao inclui o frontmatter da task ativa em sources[], permitindo que status/rework avancem silenciosamente sem deteccao de drift;
     - A interface de verify nao emite saida estruturada com status discriminados nem expoe o literal stale_package_rejected;
     - Inexistem na documentacao normativa criterios negativos objetivos delimitando quando NAO iniciar sessao nova;
     - Inexiste teto para leituras on_demand durante o bootstrap, permitindo varredura em bloco desnecessaria;
     - Inexiste regra proibindo expressamente que campos derivados do manifesto sejam citados como prova documental em pareceres e decisoes.
expected:
  1. Tornar a transicao curta entre ciclos uma primitive oficial e deterministica do Orchestrator, integrando compilador de handoff, verificador mecanico fail-closed e contratos operacionais.
  2. Implementar a arquitetura formal:
     Ciclo N -> Close/checkpoint estavel -> Context Compiler -> Short Resume Package -> Nova sessao limpa do Orchestrator -> Verificacao mecanica fail-closed -> Leituras seletivas de fontes sob demanda -> Reconstrucao do contexto minimo suficiente -> Conducao do Ciclo N+1.
  3. Incorporar os 10 principios normativos e as recomendacoes conclusivas do parecer do Advisor (Q1 a Q9).
impact: confere robustez deterministica a transicao de ciclos do Orquestrador, prevenindo drift cognitivo e garantindo governanca estrita sem inflar o contexto inicial nem conferir falsa autoridade a artefatos derivados.
dedup: T022 construiu a biblioteca inicial de selective retrieval e schema de manifest; T023 produziu a evidencia experimental comparativa; T032 institucionaliza o protocolo no pacote distribuido.

## Spec
### Intent
Institucionalizar o protocolo deterministico de transicao curta entre ciclos e reconstrucao seletiva de contexto no Orchestrator, assegurando integridade mecanica das fontes, prevencao de drift, barreira contra autoridade indevida de resumos e criterios objetivos de ativacao.

### Arquitetura e Invariantes do Protocolo
1. **Pipeline de Transicao:**
   - Ao atingir um ponto estavel de fechamento de unidade ou fronteira de lote, o Orquestrador invoca `scripts/resume_generate.py` para compilar o `resume.json`.
   - Na sessao limpa seguinte, o primeiro comando obrigatorio e a validacao deterministica via `scripts/resume_generate.py --verify <caminho> --json`.
   - Se a verificacao for aprovada (`status: verified`), o agente consome as classes `inline` e realiza leituras `excerpt` ou `on_demand` estritamente conforme a necessidade da conducao.
   - Se houver divergencia (`status: stale_package_rejected` ou `source_missing`), a sessao limpa descarta o pacote e reconstroi o estado diretamente das fontes oficiais em disco (`STATUS.md`, Task file e `PROJECT.md`).
2. **Barreira Contratual contra Autoridade Indevida (Principio 1 e Finding Q3):**
   - O `Short Resume Package` e um **indice de navegacao e atestacao de integridade**, nunca autoridade normativa.
   - E terminantemente PROIBIDO ao Orquestrador, Checker ou qualquer agente citar campos derivados do pacote (`open_items`, `next_action`, `resolved_context[].reason`) como prova factual em decisoes, relatorios ou pareceres. A citacao valida e obrigatoriamente o trio `(path, selector, digest)` inspecionado diretamente no arquivo fonte.
3. **Migracao de Schema Aditiva (schemas/resume-manifest.schema.json, Finding Q2):**
   - O schema e estendido de forma retrocompativel para incluir:
     - `state_revision`: integer >= 0 (revisao de estado da unidade ativa);
     - `content_id`: string ou null (digest dos content_paths da unidade quando aplicavel);
     - `generated_at`: string ISO 8601 UTC;
     - `generator_version`: string identificadora do gerador deterministico;
     - `task_frontmatter_digest`: string SHA-256 do frontmatter da task ativa.
4. **Fechamento de Deteccao de Drift (scripts/resume_generate.py, Finding Q4 e Q6):**
   - O frontmatter da task ativa passa a integrar obrigatoriamente `sources[]` com seletor `frontmatter` (e campos volateis mascarados).
   - O comando `--verify` passa a emitir saida JSON estruturada contendo:
     - `status`: enum `["verified", "stale_package_rejected", "source_missing", "schema_invalid"]`;
     - `verified_sources_count`: integer;
     - `mismatches`: array de objetos detalhando `path`, `selector`, `expected_digest`, `actual_digest` e `reason`.
5. **Criterios Negativos de Sessao Nova (docs/WORK_MODEL.md e EXECUTION_PROTOCOL.md, Finding Q5):**
   - A inicializacao de sessao nova via transicao curta e formalmente contraindicada quando:
     a) O contexto acumulado na sessao corrente estiver confortavelmente abaixo do limiar de 120.000 tokens;
     b) Houver um lote em andamento ativo (`active_batch != none` em `STATUS.md`), onde a reconstrucao de estado parcial custaria mais do que manter o condutor ativo;
     c) A fase corrente for `debate`, cujo padrao comunicacional exige contexto discursivo contiguo;
     d) A unidade envolver um volume de `content_paths` cuja leitura granular degeneraria em releitura de quase toda a arvore.
6. **Teto de Leituras de Bootstrap (docs/CONTEXT_POLICY.md, Finding Q7):**
   - No primeiro turno de conducao de uma sessao retomada, o Orquestrador e limitado a no maximo 5 leituras `on_demand`, prevenindo a reintroducao massiva e acritica de arquivos antes da tomada de decisao.
7. **Harmonizacao do Limiar de Ativacao (docs/EXECUTION_PROTOCOL.md, Finding Q8):**
   - O limiar canonico recomendado permanece unificado em aproximadamente 120.000 tokens de contexto acumulado, formalizado como gatilho de recomendacao operacional para gravacao de handoff e abertura de sessao limpa.
8. **Ciclo de Vida do Pacote de Retomada (Finding Q9):**
   - O arquivo `resume.json` e sempre derivado sob demanda. Pode ser gerado em diretorio temporario de trabalho (`staging/` ou `scratch/`) para transporte e inspecionado mecanicamente, sem se tornar registro estatico versionado nem autoridade concorrente aos documentos Native.

### Scope and Frozen Write Paths
A execucao de Phase B e estrita aos seguintes 10 caminhos de arquivo:
1. `docs/WORK_MODEL.md`
2. `docs/EXECUTION_PROTOCOL.md`
3. `docs/CONTEXT_POLICY.md`
4. `prompts/orchestrator.md`
5. `prompts/orchestrator-playbook.md`
6. `schemas/resume-manifest.schema.json`
7. `scripts/resume_generate.py`
8. `scripts/tests/test_resume_generate.py`
9. `_tl-orc/project/STATUS.md`
10. `_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md`

### Acceptance Criteria (AC01–AC11)
- **AC01 (Schema Extendido):** `schemas/resume-manifest.schema.json` valida obrigatoriamente `state_revision`, `generated_at`, `generator_version` e suporta `content_id`, preservando compatibilidade Draft 2020-12.
- **AC02 (Compilacao com Frontmatter):** `scripts/resume_generate.py` inclui o frontmatter da task ativa em `sources[]` e preenche `state_revision` e `content_id` a partir da unidade ativa.
- **AC03 (Verify Estruturado e Literal stale_package_rejected):** `scripts/resume_generate.py --verify` emite JSON estruturado com status `verified` ou `stale_package_rejected` / `source_missing`.
- **AC04 (Barreira contra Autoridade Indevida):** `prompts/orchestrator.md` e `prompts/orchestrator-playbook.md` proíbem taxativamente citar resumos como prova em decisões e fixam a citação mandatória de `(path, selector, digest)` das fontes oficiais.
- **AC05 (Criterios Negativos):** `docs/WORK_MODEL.md` e `docs/EXECUTION_PROTOCOL.md` normatizam as quatro condicoes de contraindicacao de abertura de sessao nova.
- **AC06 (Teto de Bootstrap):** `docs/CONTEXT_POLICY.md` formaliza o teto operacional de leituras `on_demand` no turno inicial de retomada.
- **AC07 (Harmonizacao de Limiar):** `docs/EXECUTION_PROTOCOL.md` consolida o limiar de ~120 mil tokens como referencia unica recomendada para rotação de contexto.
- **AC08 (Nao-Presuncao de Economia Universal):** Toda a documentacao normativa enfatiza que a retomada curta visa governanca e seguranca cognitiva, sem prometer reducao incondicional de custos monetarios ou de tokens brutos.
- **AC09 (Testes Unitarios e Contrafactuais):** `scripts/tests/test_resume_generate.py` expande a suite para cobrir deteccao de drift de state_revision, emissao do literal stale_package_rejected e validacao do novo schema.
- **AC10 (Validacao Estrutural):** `python3 scripts/validate_repository.py` retorna exit code 0 sem desvios estruturais, links quebrados ou hashes inconsistentes.
- **AC11 (Revisao Independente Cross-Family):** Parecer formal do Checker independente cross-family aprovado com zero action items.

### Verification Plan
1. **Validacao Estrutural:** `python3 scripts/validate_repository.py`
2. **Suite de Testes Unitarios e Contrafactuais:** `python3 -m unittest scripts/tests/test_resume_generate.py`
3. **Prova de Verificacao em Disco:** Geracao de `resume.json` de teste sobre T032, mutacao induzida de arquivo e comprovacao mecanica do status `stale_package_rejected`.
4. **Auditoria de Integridade:** `python3 scripts/audit_lineage.py` e verificacao de ausencia de caminhos privados locais.
5. **Revisao do Checker Independente:** Invocacao do Checker cross-family em sessao limpa report-only contra a arvore congelada.
