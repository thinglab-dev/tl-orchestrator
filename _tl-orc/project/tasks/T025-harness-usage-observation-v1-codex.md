id: T025
title: Harness Usage Observation v1 - Codex
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: []
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (formalização da observabilidade real de uso por harness/chamada T025)
decisions: []
spec_author: orchestrator
spec_revision: 5fd6f539c17206ad
rework_round: 10
affects_context: []
content_id: e8e9201c43def8bdcabb8bbdb52d8d09b6f2b8b1:9c9c1725e3874015
effective_authors: [google]
checker_independence: required
content_paths: [scripts/tl_usage.py, scripts/tests/test_tl_usage.py, scripts/fixtures/tl_usage/codex/, schemas/usage-observation.schema.json, scripts/tests/test_audit_lineage.py]
checker_independence: required

## Finding
source: auditoria arquitetural do tl-orchestrator v0.12.0 e análise comparativa contra donvito/codex-astra-luna-orchestrator concluídas em 2026-09-14, acrescida da autorização de expansão mínima do mantenedor em 2026-09-14 para compatibilização de teste pré-existente.
observed: o tl-orchestrator possui registro conceitual de medição de contexto (context_ledger, economia de contexto e artefatos de evidência), mas ainda não dispõe de um instrumento determinístico capaz de transformar um rollout nativo de uma execução Codex em uma observação factual estruturada vinculada explicitamente a um run_id. Adicionalmente, o registro legítimo de T025 no board revelou que o teste pré-existente scripts/tests/test_audit_lineage.py (T34) continha um assert hardcoded sobre a contagem histórica de 24 tasks (25 != 24).
expected: instrumento determinístico em Python puro stdlib (scripts/tl_usage.py), puramente local, read-only, sem chamadas de modelo e sem rede, capaz de parsear rollouts Codex e fixtures sintéticas com preservação de contadores brutos, segregação de derivações, reconciliação campo a campo entre per-response delta e contadores cumulativos, distinção de contextos multi-model/multi-effort, relações entre threads, timing com semântica explícita, completude verificável, preservação absoluta de privacidade e validação contra schemas/usage-observation.schema.json. Como expansão mínima autorizada, ajustar dinamicamente scripts/tests/test_audit_lineage.py (T34) para validar CAS sobre a totalidade exata das tasks canônicas registradas no board, eliminando a constante histórica estática.
impact: estabelece uma base factual para futuras evidências de uso local (local_observed) sem alterar os 24 arquivos da distribuição v0.12.0, sem modificar contratos existentes e preservando 100% da suíte regressiva com asserção dinâmica estrita de tarefas.
hypothesis: o desacoplamento formal entre medição bruta de harness e avaliações de qualidade/rework, aliado a regras estritas de não-presunção (ausência não é zero, derivações exigem id versionado), garante observabilidade confiável e imune a heurísticas implícitas.
dedup: T022 implementou context economy e selective retrieval; T018 entregou modo automático e contabilidade de slots; T019 formalizou a seleção dinâmica de primário; T024 reconciliou a governança. T025 implementa a observabilidade do harness Codex como instrumento isolado fora da distribuição e harmoniza dinamicamente o teste T34.

## Spec
### Intent
Demonstrar, de forma read-only, local, determinística, sem chamada de modelo, sem rede e sem alteração dos 24 arquivos distribuídos da baseline v0.12.0, que um rollout Codex real conhecido pode ser parseado e convertido em uma observação factual estruturada com procedência, modelo/effort observados, contadores brutos, relações entre threads, timing explicitamente semântico, completude, digest da fonte e vínculo explícito com um run_id; e compatibilizar dinamicamente o teste CAS T34 de audit_lineage com a expansão legítima do board.

### Scope and write paths
- `scripts/tl_usage.py` [NEW]: utilitário CLI e biblioteca stdlib para parseamento factual de rollouts Codex em formato Draft 2020-12, suportando `--run-id <run_id> --session-ref <caminho-ou-ref>` e emissão em stdout ou `--output <caminho>`.
- `schemas/usage-observation.schema.json` [NEW]: contrato JSON Schema Draft 2020-12 definindo a estrutura canônica da observação de uso factual (run_id, session_ref_digest, harness, parser_status, completeness, raw_usage, derived_usage, observed_contexts, thread_topology, timing, rate_limits).
- `scripts/fixtures/tl_usage/codex/` [NEW]: fixtures de teste sintéticas positivas (rollout simples, multi-turn, multi-model/multi-effort, subthreads, rate limits) e negativas (rollout truncado, JSON malformado, formato não suportado).
- `scripts/tests/test_tl_usage.py` [NEW]: suíte de testes determinísticos cobrindo CLI, parser, reconciliação campo a campo, regras de derivação, semântica de timing, tolerância a falhas e validação de schema.
- `scripts/tests/test_audit_lineage.py`: ajuste dinâmico de test_t34 para exigir igualdade exata de conjuntos entre os IDs das tasks canônicas em disco e o board STATUS.md, exercitando CAS sobre todas elas sem número fixo histórico.

### Invariants
- I1 (Correlação Explícita): `run_id` e `session_ref` são fornecidos explicitamente pela CLI; zero auto-descoberta silenciosa, heurísticas de proximidade temporal, cwd ou timestamp.
- I2 (Fonte Somente Leitura): a leitura do arquivo de rollout é estritamente read-only, sem criação de arquivos acessórios no diretório da fonte e sem alteração de permissões ou mtime.
- I3 (Ausência não é Zero): campos ou métricas ausentes no rollout são expressos como `"not_observable"` (ou ausência tipada no schema), sendo expressamente proibido injetar `0` para preencher schema.
- I4 (Segregação Raw vs Derived): contadores literais extraídos da fonte residem em `raw_usage`; qualquer campo derivado reside em `derived_usage` acompanhado obrigatoriamente de `derivation_id` versionado e documentado.
- I5 (Reconciliação Campo a Campo): quando existirem deltas por resposta e contadores cumulativos, a verificação de reconciliação compara estritamente campos homólogos (input com input, output com output, reasoning com reasoning), sem pressupor equações como `input_uncached = input - cached`.
- I6 (Anti-Soma de Cumulativos): snapshots cumulativos identificados no rollout nunca podem ser somados entre si.
- I7 (Preservação de Contextos): turnos com modelos ou reasoning efforts distintos são registrados em `observed_contexts`, sem colapso silencioso no último turno encontrado.
- I8 (Topologia de Threads): distinção explícita entre root thread, child threads e auto-review/guardian quando observáveis no payload da sessão.
- I9 (Semântica Estrita de Timing): métricas temporais limitam-se a `observed_session_span_seconds` (diferença entre o último e o primeiro timestamp válidos do rollout); durações de job e latências internas de modelo são registradas como `"not_observable"`.
- I10 (Completude e Integridade): status de completude (`complete`, `incomplete`, `not_observable`) exige verificação de marcador terminal formal da versão; EOF puro, truncamento ou erro de parse JSON nunca podem resultar em `complete`.
- I11 (Privacidade Absoluta): proibido persistir no repositório caminhos absolutos privados (`/Users/...`), rollouts reais, prompts, respostas textuais ou credenciais; apenas digests criptográficos SHA-256 da fonte e metadados estruturados são mantidos.
- I12 (Isolamento de Qualidade): vereditos de aprovação, acceptance, reworks ou métricas de qualidade não fazem parte da observação de uso bruta do harness.
- I13 (Quota Account-Scoped): observações de limite de taxa ou quota de assinatura são marcadas com `scope: "account"` e `attribution: "unknown"`, sem atribuição ao `run_id` e sem conversão em moeda (USD).
- I14 (Parser Status Verificável): classificação de compatibilidade entre `supported` (versão/fingerprint coberta por fixtures), `partial` e `unsupported`, sem métricas autorreferentes de confiança.
- I15 (Preservação dos 24 Arquivos Distribuídos): todos os 24 arquivos declarados em `distribution-manifest.json` permanecem byte-idênticos ao baseline v0.12.0.
- I16 (Zero Dependências Externas): código restrito a Python 3 stdlib, sem pacotes externos, sem rede e sem subprocessos de harness/LLM.
- I17 (Política de Retenção e Bounded Memory): streaming com limites estritos (caps) para prevenir exaustão de recursos em rollouts adversariais: agregação O(1) de contadores; rate limits deduplicados por limit_id retendo snapshot mais recente (cap 50); cap 50 para razões com contagem de truncamento; cap 50 para contextos; cap 100 para threads.
- I18 (Atomicidade de Hashing e Leitura): cálculo de SHA-256 e parsing de linhas operam atomicamente sobre o mesmo descritor de arquivo aberto.
- I19 (Conformidade Incondicional com o Schema): validação interna mandatória contra Draft 2020-12 e normalização de metadados externos garantem que o resultado é 100% válido independente de flags CLI.

### Acceptance Criteria
- AC1: `scripts/tl_usage.py` recebe `--run-id` e `--session-ref` obrigatórios e opera em modo read-only.
- AC2: Execução com caminho inexistente ou inacessível falha com código diferente de zero e mensagem clara de erro.
- AC3: Rollouts sintéticos e reais do formato Codex 0.153+ são parseados identificando `session_id`, `harness_version`, `format_fingerprint` e `source_sha256`.
- AC4: Contadores brutos `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens` e `total_tokens` são preservados sem mutação.
- AC5: Se um contador bruto estiver ausente no payload, é emitido como `"not_observable"`, nunca 0.
- AC6: Derivações de token contêm `value` e `derivation_id`; derivações não comprovadas são emitidas como `"not_observable"`.
- AC7: Reconciliação campo a campo entre eventos de `token_count` / `token_usage_record` compara exclusivamente campos homólogos e registra o status de reconciliação.
- AC8: Múltiplos snapshots cumulativos não são somados em totalizadores gerais.
- AC9: Mudanças de modelo ou reasoning effort ao longo do rollout são refletidas em `observed_contexts`.
- AC10: Subthreads / child turns são mapeados em `thread_topology` mantendo a identificação do nó raiz e eventuais ramificações.
- AC11: `timing` registra `observed_session_span_seconds` com procedência nos timestamps inicial e final do rollout.
- AC12: `completeness` é avaliado como `complete` somente quando evidência terminal da sessão estiver presente; truncamentos resultam em `incomplete` com indicação de motivo.
- AC13: JSON malformado produz erro determinístico ou registro de incompletude sem falha silenciosa.
- AC14: Saída de `tl_usage.py` em conformidade estrita com `schemas/usage-observation.schema.json`.
- AC15: Fixtures sintéticas em `scripts/fixtures/tl_usage/codex/` cobrem casos normais, multi-contexto, truncados e malformados.
- AC16: Suíte de testes unitários em `scripts/tests/test_tl_usage.py` cobre todos os caminhos e passa com 100% de sucesso.
- AC17: Smoke test executado contra rollout Codex real local demonstra funcionamento ponta a ponta sem erros.
- AC18: Nenhuma informação pessoal, caminho privado ou segredo é persistido em arquivos rastreados pelo Git.
- AC19: Os 24 arquivos de distribuição listados em `distribution-manifest.json` mantêm seus hashes SHA-256 byte-idênticos ao baseline inicial.
- AC20: `scripts/validate_repository.py` executa e passa com sucesso.
- AC21: `scripts/audit_lineage.py` executa e confirma ausência de blockers.
- AC22: Ausência comprovada de chamadas de rede ou subprocessos de modelos em toda a execução do instrumento.
- AC23: Classificação v3 executada para Maker e Checker independente.
- AC24: Parecer de revisão emitido por Checker independente report-only confirmando atendimento integral da spec.
- AC25: `scripts/tests/test_audit_lineage.py` (T34) valida igualdade exata de conjuntos entre os IDs de tasks do board e as tasks canônicas em disco, e exercita update_task_status_atomic para todos os IDs sem constante histórica fixa.

