id: T032
title: Protocolo de Retomada Curta e Transicao entre Ciclos
type: feat
deliverable: package
standalone: true
method: native
status: ready
state_revision: 2
depends_on: [T022, T023]
blocked_by: []
origin: user (autorizacao formal em 2026-09-17 para institucionalizar as conclusoes de T023 e a base tecnica de T022; rework_round 1 ratificado para sanar acoplamento de limiar, metadata volátil e verificabilidade de bootstrap)
decisions: []
spec_author: orchestrator
spec_revision: 83a410d9244726c8
rework_round: 1
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
source: conclusoes empiricas de T023 (_tl-orc/project/evidence/T023-r01.md), base tecnica de T022 (_tl-orc/project/tasks/T022-*.md / evidence/T015-r03b.md), parecer consultivo do Advisor (evidence/T032-support/phase-a/02-advisor/advisor-verdict.json) e determinacoes do mantenedor no rework r01 em 2026-09-17
observed:
  1. T023 provou que a retomada em sessao limpa a partir de um Pacote Curto de Retomada como indice nao-tautologico de conferencia obrigatoria previne vicios cognitivos de historico longo e assegura 100% de aderencia a governanca (zero violacoes X1-X4 no Braco B contra violacao X2 no Braco A), com 81,8% de cache hit de prefixo no harness (356.864 tokens).
  2. No entanto, o piloto foi um experimento delimitado (N=1 pareado sobre checkpoint adaptado T009 r02). Conforme evidenciado na Tabela SS7.2 de T023-r01.md, o Braco B consumiu 436.372 tokens de entrada bruta contra 64.701 do Braco A (custo bruto de tokens cerca de 6,5x maior), demonstrando que a retomada curta decorre de trade-offs de infraestrutura (prefix cache) e nao garante reducao incondicional de tokens brutos em todos os cenarios.
  3. A auditoria do Advisor e a revisao do mantenedor identificaram quatro pontos criticos de desenho que poderiam gerar divida arquitetural se mantidos no freeze:
     - Acoplamento do limiar de ~120k tokens como invariante rigida universal, colidindo com a natureza cross-harness (onde janelas variam de 200k a 1M+ tokens);
     - Inclusao de generated_at como campo de identidade, o que tornaria o pacote nao-deterministico entre geracoes consecutivas no mesmo snapshot;
     - Falta de definicao mecanica e verificavel para o teto de leituras de bootstrap;
     - Necessidade de auditoria rigorosa de autoria efetiva pre-Checker para evitar repeticao de conflitos de independencia observados em T023.
expected:
  1. Tornar a transicao curta entre ciclos uma primitive oficial e deterministica do Orchestrator, integrando compilador de handoff, verificador mecanico fail-closed e contratos operacionais.
  2. Implementar a arquitetura formal:
     Ciclo N -> Close/checkpoint estavel -> Context Compiler -> Short Resume Package -> Nova sessao limpa do Orchestrator -> Verificacao mecanica fail-closed -> Leituras seletivas de fontes sob demanda -> Reconstrucao do contexto minimo suficiente -> Conducao do Ciclo N+1.
  3. Resolver conclusivamente os quatro pontos do rework r01: limiar de ~120k como default configuravel da fonte oficial, generated_at como metadata nao-identitaria, bootstrap budget com semantica fail-closed verificavel, e auditoria completa de effective_authors pre-Checker.
impact: confere robustez deterministica a transicao de ciclos do Orquestrador, prevenindo drift cognitivo e garantindo governanca estrita sem inflar o contexto inicial nem conferir falsa autoridade a artefatos derivados.
dedup: T022 construiu a biblioteca inicial de selective retrieval e schema de manifest; T023 produziu a evidencia experimental comparativa; T032 institucionaliza o protocolo no pacote distribuido.

## Spec
### Intent
Institucionalizar o protocolo deterministico de transicao curta entre ciclos e reconstrucao seletiva de contexto no Orchestrator, assegurando integridade mecanica das fontes, prevencao de drift, barreira contra autoridade indevida de resumos, criterios objetivos de ativacao e determinismo temporal estrito.

### Arquitetura e Invariantes do Protocolo
1. **Pipeline de Transicao:**
   - Ao atingir um ponto estavel de fechamento de unidade ou fronteira de lote, o Orquestrador invoca `scripts/resume_generate.py` para compilar o `resume.json`.
   - Na sessao limpa seguinte, o primeiro comando obrigatorio e a validacao deterministica via `scripts/resume_generate.py --verify <caminho> --json`.
   - Se a verificacao for aprovada (`status: verified`), o agente consome as classes `inline` e realiza leituras `excerpt` ou `on_demand` estritamente conforme a necessidade da conducao.
   - Se houver divergencia (`status: stale_package_rejected` ou `source_missing`), a sessao limpa descarta o pacote e reconstroi o estado diretamente das fontes oficiais em disco (`STATUS.md`, Task file e `PROJECT.md`).
2. **Barreira Contratual contra Autoridade Indevida (Principio 1 e Finding Q3):**
   - O `Short Resume Package` e um **indice de navegacao e atestacao de integridade**, nunca autoridade normativa.
   - E terminantemente PROIBIDO ao Orquestrador, Checker ou qualquer agente citar campos derivados do pacote (`open_items`, `next_action`, `resolved_context[].reason`) como prova factual em decisoes, relatorios ou pareceres. A citacao valida e obrigatoriamente o trio `(path, selector, digest)` inspecionado diretamente no arquivo fonte.
3. **Separacao Estrita entre Metadata Nao-Identitaria e Identidade Canonica (Rework r01):**
   - O campo `generated_at` atua exclusivamente como **metadata temporal de proveniencia**, sendo expressamente classificado como nao-identitario.
   - `generated_at` NAO participa de `content_id`, NAO participa do digest canonico das fontes e NAO afeta o resultado de verificacao de integridade.
   - Duas compilacoes consecutivas sobre a mesma arvore produzem exatamente os mesmos digests de fontes e o mesmo veredito de integridade mecanica, mesmo apresentando timestamps de geracao distintos.
   - Campos estaveis (`generator_version`, `spec_revision`, `state_revision`, `content_id` e digests de fontes) integram a identidade verificavel do pacote.
4. **Fechamento de Deteccao de Drift e Migracao Aditiva de Schema:**
   - `schemas/resume-manifest.schema.json` e estendido de forma retrocompativel para validar: `state_revision` (int >= 0), `generated_at` (string ISO 8601), `generator_version` (string) e `content_id` (string ou null).
   - O frontmatter da task ativa passa a integrar obrigatoriamente `sources[]` com seletor `frontmatter` (e campos volateis mascarados via `mask_volatile_fields`), garantindo deteccao de mudancas em `status`, `rework_round` e `state_revision`.
   - O comando `resume_generate.py --verify` passa a emitir saida JSON estruturada expondo os status canônicos (`verified`, `stale_package_rejected`, `source_missing`, `schema_invalid`) e o detalhe dos mismatches encontrados.
5. **Criterios de Continuidade e Desacoplamento do Limiar de Contexto (Rework r01):**
   - O valor de ~120.000 tokens e definido formalmente como o **default operacional e recomendacao vigente** constante de `docs/EXECUTION_PROTOCOL.md:23-24`, reutilizado como fonte unica da recomendacao, e NAO como invariante rigida universal do protocolo cross-harness.
   - O protocolo admite override explicito da recomendacao por projeto, modelo ou politica de contexto (adequando-se a janelas de 200k, 1M+ tokens ou restricoes especificas de harness); na ausencia de override, aplica-se o default centralizado de `EXECUTION_PROTOCOL.md`.
   - Os criterios **absolutos** para NAO rotacionar sessao vinculam-se exclusivamente a seguranca, integridade e continuidade do trabalho:
     a) Incompatibilidade de estado ou falha de integridade que impeca checkpoint estavel;
     b) Lote finito em andamento ativo (`active_batch != none` em `STATUS.md`), onde a interrupcao do condutor e reconstrucao parcial custaria mais do que continuar;
     c) Fases ou modos que exigem continuidade conversacional/discursiva imediata (e.g., fase `debate`);
     d) Unidade cujo conjunto de `content_paths` seja tao extenso que a leitura sob demanda degeneraria em leitura quase total da base;
     e) Sessao cujo contexto acumulado esteja confortavelmente abaixo do limiar recomendado daquele ambiente.
6. **Mecanismo e Teto Verificavel de Bootstrap (Rework r01):**
   - O teto de leituras sob demanda durante o bootstrap e formalmente parametrizado em `docs/CONTEXT_POLICY.md` (`bootstrap_on_demand_budget`, default operacional: 5 leituras `on_demand`), sobrescrevivel na politica da unidade.
   - Contabiliza-se como leitura de bootstrap cada consulta a ferramenta de leitura (`read_section.py` ou leitura pontual) executada antes do primeiro despacho material ou decisao de conducao da sessao nova.
   - Semantica de estouro fail-closed: se o agente exceder o teto sem emitir a decisao ou sem justificar explicitamente a necessidade, o sistema emite `STOP: bootstrap_budget_exceeded`, bloqueando o prosseguimento e impedindo a reintroducao silenciosa de historico volumoso.
7. **Ciclo de Vida do Pacote de Retomada:**
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
- **AC03 (Verify Estruturado e Literal stale_package_rejected):** `scripts/resume_generate.py --verify` emite JSON estruturado com status `verified`, `stale_package_rejected` ou `source_missing`.
- **AC04 (Barreira contra Autoridade Indevida):** `prompts/orchestrator.md` e `prompts/orchestrator-playbook.md` proíbem taxativamente citar resumos como prova em decisões e fixam a citação mandatória de `(path, selector, digest)` das fontes oficiais.
- **AC05 (Criterios de Continuidade e Limiar Configuravel):** `docs/WORK_MODEL.md` e `docs/EXECUTION_PROTOCOL.md` normatizam os criterios absolutos de continuidade e tratam o limiar de ~120k como default operacional recomendavel e configuravel, sem hardcode concorrente.
- **AC06 (Teto Mecanico de Bootstrap):** `docs/CONTEXT_POLICY.md` formaliza o teto operacional de leituras `on_demand` no turno inicial de retomada com semantica fail-closed sob `bootstrap_budget_exceeded`.
- **AC07 (Determinismo e Separacao de Metadata):** `generated_at` e classificado como metadata nao-identitaria; variacoes de timestamp nao alteram a identidade canonica nem causam falsa rejeicao de integridade.
- **AC08 (Nao-Presuncao de Economia Universal):** Toda a documentacao normativa enfatiza que a retomada curta visa governanca e seguranca cognitiva, sem prometer reducao incondicional de custos monetarios ou de tokens brutos.
- **AC09 (Testes Unitarios e Contrafactuais):** `scripts/tests/test_resume_generate.py` expande a suite para cobrir deteccao de drift de `state_revision`, emissao do literal `stale_package_rejected`, determinismo de `generated_at` e estouro fail-closed do teto de bootstrap.
- **AC10 (Validacao Estrutural):** `python3 scripts/validate_repository.py` retorna exit code 0 sem desvios estruturais, links quebrados ou hashes inconsistentes.
- **AC11 (Auditoria Mandatoria de Autoria Efetiva e Checker Independente):** Reconciliacao previa e mandatoria de `effective_authors` antes do despacho do Checker final (auditando Phase A, Phase B e eventual incorporacao textual de parecer do Advisor), com veredito final aprovado por Checker cross-family independente sob `checker_independence: required`.

### Verification Plan
1. **Validacao Estrutural:** `python3 scripts/validate_repository.py`
2. **Suite de Testes Unitarios e Contrafactuais:** `python3 -m unittest scripts/tests/test_resume_generate.py` cobrindo AC01, AC02, AC03, AC07 e AC09.
3. **Prova de Verificacao em Disco:** Geracao de `resume.json` de teste sobre T032, mutacao induzida de arquivo e comprovacao mecanica do status `stale_package_rejected`.
4. **Auditoria de Integridade e Caminhos Privados:** `python3 scripts/audit_lineage.py` e verificacao de ausencia de caminhos privados locais em toda a entrega.
5. **Auditoria Pre-Classificacao de Autoria Efetiva (Mandatoria):**
   Imediatamente antes do despacho do Classificador para a rodada do Checker final:
   - Auditar as familias autoras materiais de toda a Task T032 (Phase A: Google; Phase B: Maker efetivo);
   - Inspecionar minuciosamente os diffs de `content_paths` contra o texto do parecer do Advisor (`advisor-stdout.txt` / Anthropic Claude); se houver incorporacao substantiva de redacao ou proposicao autoral do Advisor, Anthropic DEVE ser adicionada a `effective_authors`;
   - Consolidar a lista final em `effective_authors` e fornecer ao Classificador sob `checker_independence: required`, bloqueando qualquer candidato da mesma familia de qualquer autor efetivo.
6. **Revisao do Checker Independente:** Invocacao do Checker cross-family eleito em sessao limpa report-only contra a arvore imutavel congelada.
