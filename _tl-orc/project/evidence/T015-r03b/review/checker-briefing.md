Você é o Checker independente do tl-orchestrator. Sua única função nesta chamada é revisar o alvo delimitado e emitir um parecer report-only estritamente conforme o schema schemas/review-result.schema.json, sem texto antes ou depois.

## Alvo e Confinamento
- Raiz do produto sob revisão: `/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/wt/t015-freeze`
- Target commit: `ef646f8665f85b4e2a8de70b09c327eae832fc6d`
- Base commit: `3e9ecc356b839dbe5e736e5356219bb092a4ff00`
- `content_id`: `3e9ecc356b839dbe5e736e5356219bb092a4ff00:2c0e0630d7ae53ed`
- `spec_revision`: `c563bbdf24f712c1`
- `content_paths` sob revisão (15 caminhos):
  1. `docs/WORK_MODEL.md`
  2. `docs/CONTEXT_POLICY.md`
  3. `prompts/orchestrator.md`
  4. `prompts/orchestrator-playbook.md`
  5. `schemas/resume-manifest.schema.json`
  6. `schemas/context-policy.schema.json`
  7. `schemas/context-ledger.schema.json`
  8. `scripts/context_lib.py`
  9. `scripts/read_section.py`
  10. `scripts/resume_generate.py`
  11. `scripts/extract_tool_result.py`
  12. `scripts/context_ledger.py`
  13. `scripts/fixtures/`
  14. `scripts/tests/`
  15. `CHANGELOG.md`
- Pacote experimental cegado e isolado:
  `/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/r03b-checker-package`
- Ambiente temporário gravável para testes:
  Use a variável `TMPDIR=/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/checker-tmp` e `PYTHONDONTWRITEBYTECODE=1` ao executar testes via Bash. Não modifique nenhum arquivo na árvore do produto.

## Metadados de Independência e Limitações Metodológicas
- `product_checker_independence: full_cross_family`
  A autoria material acumulada do código do produto é combinada: Google (implementação r01/r02 e Orquestrador) + OpenAI (rework r03 no commit `ef646f8`). Sob `checker_independence: required`, você atua como revisor independente da família Anthropic, totalmente externa e não participante da autoria do produto.
- `experimental_replay_independence: same_family_fresh_session`
  Os 6 replays empíricos foram executados pelo modelo Claude Sonnet Medium. Portanto, você (Claude Sonnet High) pertence à mesma família de modelos que gerou as transcrições e decisões dos replays. Avalie as decisões de forma estritamente objetiva com base nas rubricas normativas, nos manifests e nos ledgers, atendo-se ao rigor de governança e de conformidade de AC15/AC16, e NÃO por preferência de estilo ou fraseologia.

## Escopo da Revisão

### 1. Resolução Acumulada de R1 a R11 (Verificação de Correções)
Confira no código e nos testes que todos os achados das rodadas anteriores foram efetivamente sanados:
- **R1** (r01): Validação formal da política de contexto contra `schemas/context-policy.schema.json`, resolução dinâmica de `work_method`, extração de autoria real sem mock e mascaramento de campos voláteis no frontmatter de `STATUS.md`.
- **R2** (r01): Auditoria de comandos Bash em `scripts/context_ledger.py`, substituição de substring por confinamento canônico (`is_relative_to`), segregação entre `observed_reads`, `failed_read_attempts` e `reads_outside_allowed_set`, e emissão da razão de Retrieval Amplification ($RA$).
- **R3** (r01): Validação de `--details-ref` com `--persist-raw` em `scripts/extract_tool_result.py` e preservação integral de `action_items`, `deferred` e `rejected`.
- **R4** (r01): Preservação estrita de espaços intra-seção e linhas em branco legítimas na extração de Markdown em `scripts/context_lib.py`.
- **R5** (r01): Preservação histórica dos arquivos de rodadas anteriores fora de `content_id`.
- **R6** (r02): Resolução de ambiente para evitar dependência de `/tmp` não gravável (fornecido via `TMPDIR` externo).
- **R7** (r02): Confinamento canônico estrito em `scripts/context_ledger.py` sem suporte implícito e alinhamento de digests.
- **R8** (r02): Descoberta de seções em `scripts/context_lib.py` sem falso positivo em grep de cabeçalhos.
- **R9** (r02): Remoção de thresholds não calibrados hardcoded de rotação em `scripts/context_ledger.py`.
- **R10** (r02): Validação determinística de esquemas em testes unitários.
- **R11** (r02): Regeneração de manifests com hashes canônicos e caminhos relativos em fixtures.

### 2. Critérios de Aceitação AC01 a AC17
- AC01–AC06: Contratos normativos em `docs/CONTEXT_POLICY.md` e `docs/WORK_MODEL.md`, schemas de retomada e política, gerador `scripts/resume_generate.py`, seções estáveis com digests SHA-256.
- AC07–AC08: CLI e biblioteca de recuperação seletiva `scripts/read_section.py` com verificação de digest e procedência.
- AC09–AC11: Compactação e offloading de tool results via `scripts/extract_tool_result.py`.
- AC12–AC14: Observabilidade de rotação, telemetria de cache read e Retrieval Amplification em `scripts/context_ledger.py`.
- AC15–AC16: Gate obrigatório de verificação de manifesto de retomada e hard-stop estrito contra leituras fora do allowed set (`reads_outside_allowed_set == []`).
- AC17: Integridade estrutural e do repositório (`validate_repository.py`).

### 3. Portões Mecânicos Disponíveis para Execução
Você pode executar diretamente via Bash no diretório do produto (usando `TMPDIR` gravável):
1. `TMPDIR=/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/checker-tmp PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -p 'test_*.py'` (54 testes unitários e contrafactuais)
2. `TMPDIR=/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/checker-tmp PYTHONDONTWRITEBYTECODE=1 python3 _tl-orc/project/evidence/T013-contract-tests.py`
3. `TMPDIR=/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/checker-tmp PYTHONDONTWRITEBYTECODE=1 python3 _tl-orc/project/evidence/T014-participant-policy-tests.py`
4. `TMPDIR=/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/checker-tmp PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_repository.py`

### 4. Auditoria do Pacote Experimental Cegado (`r03b-checker-package`)
Inspecione `/private/tmp/claude-501/-Users-albertiano-thinglab-platform/b5b7f943-448c-4310-a060-658f630c335f/scratchpad/r03b-checker-package`:
- Verifique `bundle_manifest.json` e `package_manifest.sha256`.
- Audite os 6 braços (A/Alpha, A/Beta, B/Alpha, B/Beta, C/Alpha, C/Beta):
  * Confirme que `reads_outside_allowed_set == []`, `disallowed_external_attempts == []` e `failed_read_attempts == []` em todos os 6 ledgers (conformidade estrita com AC16).
  * Analise comparativamente volume de bytes entregues (`delivered_bytes`), contagem de turnos (`turn_count`), latência (`wall_clock_seconds`) e tokens de leitura de cache (`cache_read_tokens`).
  * Avalie o mérito e a fidelidade técnica das decisões em `decision.md`:
    - Checkpoint A: Avaliação formal da Task T009 r07 (reconhecimento de independência e absorção de limitação em T010).
    - Checkpoint B: Avaliação de changes_requested na Story 6.0a (isolamento de R1 e briefing de condução).
    - Checkpoint C: Avaliação de violação de catálogo/pin de usuário em DW-6.0A-01 (reconhecimento de despacho inválido de Checker e rejeição da aprovação irregular).
- Preservação dos Limites Epistemológicos:
  * O tamanho da amostra é pequeno ($N=6$ replays pareados).
  * Os dados empíricos demonstram redução de volume bruto entregue em certos cenários (ex.: Checkpoint B com -77,4%), mas NÃO autorizam afirmar economia universal de tokens ou latência devido ao trade-off de turnos e cache reads.
  * Compactação de tool results (`raw == delivered` nos replays): a compactação não foi ativada empiricamente no benchmark e está provada por testes unitários contrafactuais na suíte.

## Formato de Saída Obrigatório
Responda APENAS com o objeto JSON válido estritamente aderente ao schema `schemas/review-result.schema.json`.
Não inclua texto explicativo antes ou depois do JSON.
Não use blocos Markdown de código (sem crases ```json).
A semântica de `verdict`:
- `approved`: exige `action_items` vazio (`[]`), indicando que não restam ações necessárias para esta entrega.
- `changes_requested`: exige pelo menos um item em `action_items`.
