id: T032
title: Story Authority Envelope and Autonomous Child Batches (AUTO_STORY)
type: feat
deliverable: package
standalone: true
method: native
status: in_review
state_revision: 1
depends_on: [T027, T028]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-17 após o canário de produção do projeto Lynvia (ciclo B011–B014 da Story 2.10), que comprovou a execução durável do T018 e expôs o atrito artificial da autoridade por proposta pontual.
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
effective_authors: [anthropic]
checker_independence: required
content_paths: [scripts/tl_story_authority.py, scripts/tl_runtime.py, scripts/tl_job.py, schemas/story-authority-envelope.schema.json, schemas/story-child-proposal.schema.json, schemas/batch.schema.json, schemas/review-result.schema.json, docs/RUNTIME.md, docs/WORK_MODEL.md, docs/EXECUTION_PROTOCOL.md, prompts/orchestrator.md, tests/story_authority_support.py, tests/test_auto_story_replay.py, tests/test_auto_story_runtime_integration.py, tests/test_story_authority_digest.py, tests/test_story_child_derivation.py, tests/test_story_functional_lineage.py, tests/test_story_global_accounting.py, tests/test_story_protected_paths.py, tests/test_story_operational_limits.py, tests/test_story_cognitive_barrier.py, tests/fixtures/auto_story_b013_b014/README.md, distribution-manifest.json, CHANGELOG.md, README.md, SKILL.md, docs/PROJECT_CONFIGURATION.md, _tl-orc/project/STATUS.md]

## Finding
source: canário de produção do projeto Lynvia, ciclo B013→B014 da Story 2.10, e auditoria do invariante terminal do T018.
observed: o B013 executou Classifier, Maker, Checker R01, Classifier de rework, Maker de rework e Checker R02 sob uma única autorização, atingiu `rework_limit_exhausted` com 98% da implementação aprovada e restaram apenas dois apontamentos cirúrgicos (Checker R5 e R6). Como o modo vigente é estritamente `AUTO_BATCH` por digest pontual de proposta, o sistema foi obrigado a parar e exigir do operador humano uma nova autorização criptográfica manual só para abrir o B014 — que herdou exatamente o commit funcional preservado do B013, corrigiu R5/R6, recebeu aprovação do Checker e fechou a Story. A invariante "um lote concluído/parado nunca abre outro lote" está correta como default, mas gera atrito operacional artificial quando uma Story precisa de mais de um lote para convergir.
expected:
1. Separar formalmente envelope imutável de autoridade (`_tl-orc/project/story-authorities/<authority_id>.json`) de ledger mutável de consumo (`_tl-orc/runtime/story-authorities/<authority_id>/`), sem nunca reescrever o envelope para registrar saldo;
2. Definir `root_authority_digest = SHA256(canonical_json(authority_payload))` sem circularidade, excluindo o próprio digest e todo metadado produzido após a decisão humana;
3. Exigir a frase canônica exata `AUTORIZO STORY <work_ref> sha256:<root_authority_digest>` como única forma de conceder a autoridade;
4. Derivar lotes filhos autonomamente apenas quando todos os apontamentos residuais forem estritamente patch-only, provando a autoridade derivada por cadeia de digests em vez de assinatura fabricada;
5. Manter uma única contabilidade global de chamadas, com `logical_call_id` separado de `global_attempt_id` e semântica conservadora para resultado ambíguo;
6. Preservar a linhagem funcional entre filhos sem mergear um child `changes_requested` em `main` só para transportar estado;
7. Bloquear mecanicamente invocação direta de CLIs cognitivas no ambiente do worker, recusando iniciar quando o isolamento não for comprovável;
8. Subordinar-se ao T028 no merge e encerrar compulsoriamente na fronteira da Story.
impact: uma autorização humana passa a cobrir a Story inteira com teto global estrito, eliminando a intervenção manual por lote sem afrouxar nenhuma garantia de autoridade, orçamento, escopo ou integridade.
dedup: T018 instituiu o lote finito autorizado; T027 instituiu o despacho orçado com write-ahead; T028 instituiu a autoridade de merge out-of-band. T032 acrescenta a camada de autoridade por Story acima do lote, sem substituir nenhuma das três.

## Spec
### Acceptance criteria
- AC01: `schemas/story-authority-envelope.schema.json` (Draft 2020-12) define o envelope com `authority_payload` de exatamente doze campos, `root_authority_digest` e `operator_authorization`, e `additionalProperties: false` em todos os níveis.
- AC02: `root_authority_digest` é calculado sobre `canonical_json(authority_payload)` e o cálculo recusa qualquer payload contaminado por campo pós-autorização (`root_authority_digest`, `operator_authorization_ref`, `authorized_at`, `authorized_literal`, `authority_source`).
- AC03: somente a frase canônica exata concede autoridade; divergência de payload após o congelamento é `HARD STOP` por `state_integrity`.
- AC04: o journal da autoridade é append-only, write-ahead, com fsync, hash-chain e escritor único sob `lease.lock`, registrando `authority_open`, `model_call_reserved`, `model_call_consumed`, `model_call_released`, `child_derived`, `child_open`, `child_closed`, `child_failed`, `hard_stop` e `authority_closed`; `status.json` é exclusivamente projeção.
- AC05: `verify_derivation()` prova contenção da **união** `required ∪ conditional` no escopo do pai, monotonicidade de `forbidden_paths` e `protected_paths`, imutabilidade da spec, não expansão de efeitos, orçamento dentro do saldo, `max_child_batches`, `max_consecutive_failed_batches` e `wall_clock_deadline`.
- AC06: a derivação automática exige todos os apontamentos residuais como `target_role = maker`, `category = patch`, `scope_status = inside_parent_envelope` e `spec_status = unchanged`, com os dois últimos recalculados mecanicamente e divergência com a declaração do Checker resultando em parada.
- AC07: `budgeted_model_dispatch` aceita contexto de autoridade, escreve a reserva global antes da local e a liquida antes dela; uma chamada física conta exatamente uma vez sob um `global_attempt_id` compartilhado pelos dois ledgers; retry gera id novo; replay de id liquidado não repete chamada nem débito; resultado ambíguo conta conservadoramente uma vez.
- AC08: o runtime materializa o `checker_reviewed_commit` de um filho `changes_requested` em `refs/tl/functional-checkpoints/<batch>/<unit>`, registra a linhagem completa em `child_closed` e o filho seguinte nasce exatamente desse commit, provado por `git cat-file -e`, `HEAD ==`, `tree ==` e working tree limpa.
- AC09: o ambiente do worker bloqueia mecanicamente `agy`, `codex`, `claude` e `gemini` por PATH, a barreira é provada no ambiente real do worker e `AUTO_STORY` recusa iniciar quando a capability for `unavailable`; a limitação de resolução por nome é declarada, não contornada.
- AC10: `allowed_effects.merge` não constitui bypass do `MergeAuthorityGate`/`AuthorityReceipt` do T028, e avançar para outra Story falha com `next_story_without_authorization`.
- AC11: retrocompatibilidade estrita — lote sem `story_authority_mode` continua validando contra `schemas/batch.schema.json` e executando com semântica de lote único, sem barreira e sem autoridade.
- AC12: replay determinístico do caso real B013→B014 em `tests/test_auto_story_replay.py` com repositório Git real, recibo T028 autêntico e fixtures em `tests/fixtures/auto_story_b013_b014/`.

### Verification
- `python3 -m unittest discover -s tests`
- `python3 -m unittest discover -s scripts/tests`
- `python3 scripts/validate_repository.py`
- `python3 scripts/audit_lineage.py`

## Evidence
evidence/T032-T033-verification.md — portões executados, incompatibilidade de ambiente registrada com prova de não regressão contra `origin/main`, e divergências explícitas em relação ao texto do prompt. Veredito de Checker independente upstream ainda pendente.
