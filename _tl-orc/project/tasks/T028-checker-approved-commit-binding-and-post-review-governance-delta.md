id: T028
title: Checker-Approved Commit Binding, Post-Review Governance Delta, and Out-of-Band Merge Authority v2
type: gov
deliverable: none
standalone: true
method: native
status: in_progress
state_revision: 15
depends_on: [T027]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (ratificação B004) e extensão formal ratificada em 2026-09-15 após auditoria do incidente de merge do PR #55
decisions: []
spec_author: orchestrator
spec_revision: 765a1c3333c85d00
rework_round: 15
affects_context: []
effective_authors: [google]
checker_independence: required
content_id: 13ee49e4593022713ab7dc38292344a41a3b5f71:7ee5200f9f0ed95a
content_paths:
  - docs/WORK_MODEL.md
  - docs/RUNTIME.md
  - prompts/orchestrator-playbook.md
  - schemas/batch.schema.json
  - schemas/merge-authorization.schema.json
  - scripts/tl_merge_guard.py
  - scripts/tl_runtime.py
  - scripts/tl_run_story.py
  - scripts/tl_supervisor.py
  - scripts/tests/test_tl_merge_guard.py
  - tests/test_tl_supervisor.py
  - scripts/tests/test_tl_runtime.py
  - scripts/fixtures/runtime/fake_gh.py
  - _tl-orc/project/STATUS.md
  - _tl-orc/project/tasks/T028-checker-approved-commit-binding-and-post-review-governance-delta.md
  - _tl-orc/project/evidence/T028-r01.md

## Finding
source: auditoria pós-encerramento do lote Canary B004 na Story connector:2-8 em 2026-09-14 combinada com a auditoria de autoridade do incidente de merge do PR #55 em 2026-09-15.
observed:
1. No lote B004, o Checker independente aprovou o commit 102cec41, mas um commit subsequente (86106359) foi mesclado sem validação estrita de que a mutação pós-revisão era puramente documental/governança.
2. No PR #55, a reconciliação T030 foi concluída com CI verde, mas o merge em main (13ee49e) ocorreu sem autorização humana expressa para o efeito final. O sistema permitiu o avanço porque confundiu validade técnica com autoridade do operador, porque a flag permitted_effects.pull_request_merge foi tratada como autorização em vez de mera capacidade técnica, e porque main não possuía branch protection nem rulesets exigindo status check com integration_id de App confiável no GitHub.
expected:
1. Formalizar a vinculação estrita em duas etapas: checker_approved_commit -> integration_candidate_commit -> merge_execution_authority;
2. Garantir que technical_merge_validity != operator_authority e que permitted_effects.pull_request_merge == capability != authorization;
3. Estabelecer que qualquer mutação pós-aprovação fora da allowlist normalizada post_review_governance_delta_only exige obrigatoriamente nova rodada de Checker independente;
4. Implementar barreira em duas camadas: Layer 1 interna (MergeAuthorityGate em Python para todos os effect producers) e Layer 2 de plataforma (GitHub Ruleset exigindo status check Merge Authority preso a integration_id de Dedicated GitHub App);
5. Rejeitar armazenamento do envelope na árvore da PR candidata para evitar circularidade de SHA e forjamento; usar envelope out-of-band com canonicalização estrita (canonical_authorization_payload_v1), derivação não-circular de authorization_id a partir do claim e anti-replay atômico em trust domain externo;
6. Suportar os modos operacionais human_merge_only (enforced/policy_only) e delegated_single_merge, com fail-closed estrito contra base drift, head drift, fake checks e ambiguidade.
impact: fecha integralmente a fronteira entre aprovação técnica e autoridade executiva, eliminando tanto bypasses por scripts/runtimes quanto bypasses manuais pela interface web do GitHub.
dedup: T024 reconciliou linhagens de v0.11 com T018; T030 reconciliou T025-T029 com v0.16/v0.17; T028 fecha a governança de binding pós-review e autoridade de merge.

## Spec
### Intent
1. Instituir a distinção de primeira classe entre permissão de preparação de merge (gates + Checker) e autoridade de execução de merge (envelope out-of-band assinado/atestado).
2. Fornecer o validador canônico `scripts/tl_merge_guard.py` (`MergeAuthorityGate` e `AuthorityReceipt`) exigido por todos os caminhos executores de merge (`tl_runtime.py`, `tl_run_story.py`, `tl_supervisor.py`).
3. Eliminar a circularidade criptográfica através de dois objetos: `authorization_claim_v1` (sem id nem assinatura) e `signed_authorization_envelope_v1`, derivando `authorization_id = "auth-" + sha256(canonical_claim)[:32]`.
4. Congelar para a v1 o trust backend primário: Dedicated Merge Authority GitHub App + external authority store com controle atômico anti-replay (CAS: unused -> reserved -> consumed/indeterminate).
5. Exigir que a autorização seja out-of-band (transporte determinístico via PR Comment Metadata com parsing estrito: 0 -> missing, 1 -> ok, >1 distintas -> FAIL_CLOSED ambíguo).
6. Vincular atomicamente a autorização a `(target_repository, target_pr, expected_head_sha, expected_base_sha, checker_approved_commit, integration_candidate_commit)`. Qualquer base drift ou head drift invalida imediatamente o token (`FAIL_CLOSED`).
7. Formalizar a allowlist estrita `post_review_governance_delta_only` por caminhos canônicos normalizados (`_tl-orc/project/tasks/*.md`, `_tl-orc/project/evidence/*.md`, `_tl-orc/project/STATUS.md`).
8. Especificar a camada de enforcement no GitHub com Ruleset em `main` exigindo PR, base estritamente atualizada e status check `Merge Authority` preso ao `integration_id` da App confiável.
9. Formalizar a separação de credenciais: a credencial do agente não pode atualizar `main` unilateralmente nem satisfazer o check de autoridade confiável.
10. Definir rollback seguro como degradação para `human_merge_only.enforced`, tratando `break_glass` separadamente como procedimento humano explícito com audit trail.

### Scope and write paths
- `schemas/merge-authorization.schema.json`: schema universal Draft 2020-12 cobrindo claim, envelope e proveniência.
- `schemas/batch.schema.json`: inclusão formal dos campos `checker_approved_commit`, `integration_candidate_commit` e semântica de capacidade de `permitted_effects.pull_request_merge`.
- `scripts/tl_merge_guard.py`: primitive canônico `MergeAuthorityGate`, dataclass `AuthorityReceipt`, canonicalizador byte-a-byte, parser de transporte PR Comment, validador de delta e contrato de store externo.
- `scripts/tl_runtime.py`: condicionamento mandatório de `pull_request_merge` e `local_merge` (para base protegida) ao `AuthorityReceipt`.
- `scripts/tl_run_story.py`: integração de `merge_queue_head` ao `MergeAuthorityGate`.
- `scripts/tl_supervisor.py`: imposição de que `merge_runner` comprove posse de `AuthorityReceipt` válido (Regra B).
- `scripts/tests/test_tl_merge_guard.py`: suíte contrafactual completa cobrindo todas as 16 sondas mandatórias e a regressão exata do PR #55.
- `tests/test_tl_supervisor.py`: atualização dos testes de supervisor para respeitar a exigência de `AuthorityReceipt` e isolamento de target repository.
- `scripts/tests/test_tl_runtime.py`: sonda contrafactual de isolamento de repositório e fallbacks fail-closed no Runtime e CI.
- `docs/WORK_MODEL.md` e `docs/RUNTIME.md`: documentação normativa das regras de autoridade, modos operacionais e distinção capacidade vs autorização.
- `prompts/orchestrator-playbook.md`: atualização do playbook do orquestrador vedando avanço sem fechamento formal de autoridade.
- `_tl-orc/project/STATUS.md`: registro de T028 e sincronização de CAS.

### Acceptance Criteria
- AC1: `schemas/merge-authorization.schema.json` é universal (`owner/repo`), validável por Draft 2020-12, sem repositórios hardcoded.
- AC2: `authorization_id` é calculado univocamente como `"auth-" + sha256(canonical_claim)[:32]` sobre o `authorization_claim_v1` (sem circularidade autorreferencial).
- AC3: Canonicalização determinística byte-a-byte implementada em Python (`canonical_authorization_payload_v1`) com ordenação lexicográfica, UTF-8, sem whitespace, UTC ISO 8601 e domínio de assinatura `"TL_MERGE_AUTHORIZATION_V1\0"`.
- AC4: `scripts/tl_merge_guard.py` implementa `MergeAuthorityGate` e `AuthorityReceipt` cobrindo integralmente a matriz de falha fechada.
- AC5: Todos os effect producers (`tl_runtime.py`, `tl_run_story.py`, `tl_supervisor.py`) exigem comprovadamente `AuthorityReceipt` válido antes de executar merge.
- AC6: Delta pós-revisão restrito com matching canônico normalizado à allowlist `post_review_governance_delta_only`; qualquer alteração de código ou teste pós-Checker exige nova rodada completa.
- AC7: Transporte determinístico por PR Comment implementado: 0 envelopes -> `missing_merge_authorization`; 1 envelope válido -> prossegue; >1 envelopes válidos distintos -> `FAIL_CLOSED: ambiguous_merge_authorization`.
- AC8: Anti-replay operando em trust domain externo com CAS atômico (`unused -> reserved -> consumed/indeterminate`); remoção do ledger local não permite reuso.
- AC9: Arquitetura de enforcement de plataforma especifica required check `Merge Authority` preso a `integration_id` de Dedicated GitHub App.
- AC10: A credencial do agente não pode contornar a branch protegida de integração, não pode gerar o status `Merge Authority` confiável e não pode atualizar o alvo sem todos os gates satisfeitos.
- AC11: Raiz de confiança de autorização opera fora da autoridade de processos do agente. Chaves de software locais no mesmo host são classificadas como `advisory / not mechanically isolated`.
- AC12: Base drift (`main` avançou) e head drift (novo commit no PR) invalidam imediatamente a autorização (`FAIL_CLOSED`).
- AC13: Falha no subsistema de autoridade degrada com segurança para `human_merge_only.enforced`, nunca para merge desprotegido. `break_glass` é restrito a procedimento humano explícito auditado.
- AC14: Mutações na branch candidata em workflows ou configurações de chaves públicas têm efeito zero sobre o avaliador de autoridade (que lê a base protegida).
- AC15: Suíte contrafactual `scripts/tests/test_tl_merge_guard.py` passa com 100% de aprovação (incluindo regressão exata do PR #55) e parecer formal `approved` (0 action items) de Checker independente.

### Security Properties
#### Security Properties We Actually Guarantee
1. **Binding Determinístico**: Nenhuma árvore pode ser preparada para merge se divergir do commit aprovado pelo Checker além da allowlist estrita de governança.
2. **Invalidação Automática por Drift**: Qualquer avanço na ponta de `main` ou qualquer novo commit inserido no PR invalida instantaneamente a autorização.
3. **Anti-Replay em Escala Externa**: Uma autorização consumida pelo authority store externo jamais pode ser reaproveitada para outro PR ou novo SHA, mesmo que o ledger local seja apagado.
4. **Bypass Impossível via UI do GitHub (para atores sujeitos ao ruleset)**: Com o Ruleset exigindo status check com `integration_id` da App de autoridade e base estritamente atualizada, a interface do GitHub bloqueia o merge caso a autorização out-of-band não esteja ativa.
5. **Universalidade Portável**: O schema e as ferramentas funcionam em qualquer repositório sem valores hardcoded.

#### Security Properties We Do NOT Guarantee
1. **Identidades Compartilhadas Sem Ruleset**: Se o operador e o agente compartilharem o mesmo PAT do GitHub com escopo `repo` sem o Ruleset configurado na plataforma, o sistema não garante isolamento contra chamadas diretas de API.
2. **Chaves de Software no Mesmo Host**: Chaves privadas em disco no mesmo SO do agente oferecem apenas garantia consultiva (`advisory`), não mecânica. A garantia forte exige canal humano out-of-band na Dedicated GitHub App ou hardware key FIDO2.
3. **Ataques de Administrador com Bypass de Ruleset**: Administradores com permissão explícita de contornar rulesets na organização GitHub podem forçar merges pela plataforma.

## Verification profile
gov_merge_authority: execução integral de `scripts/tests/test_tl_merge_guard.py` (todas as 16 sondas contrafactuais), suíte completa `scripts/tests/` e `tests/`, `scripts/validate_repository.py` (49 package files), `scripts/audit_lineage.py` (0 blockers) e parecer formal emitido por Checker independente sob `checker_independence: required`.
