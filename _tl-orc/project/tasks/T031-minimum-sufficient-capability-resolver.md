id: T031
title: Minimum Sufficient Capability and Deterministic Efficiency Preference Resolver
type: feat
deliverable: package
standalone: true
method: native
status: in_progress
state_revision: 1
depends_on: [T019, T027]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-15 após auditoria pós-fechamento do lote Canary B005 (Story connector:2-9)
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_paths: [prompts/classifier.md, prompts/orchestrator-perfis.md, schemas/classification-result-v3.schema.json, scripts/validate_classification.py, scripts/tests/test_dynamic_primary_selection.py, distribution-manifest.json, CHANGELOG.md, _tl-orc/project/STATUS.md]

## Finding
source: auditoria pós-encerramento do lote Canary B005 no ThingLab Platform em 2026-09-15.
observed: no lote B005, o Classificador avaliou Agy Flash High como sufficient e dispatchable, mas selecionou Codex Terra xhigh como primário sob justificativa genérica de "maior mérito técnico", "maior capacidade de raciocínio para tier heavy" e "modelo de fronteira". O contrato anterior (T019, R18) permitia ranking discricionário por mérito subjetivo em estado conclusive, sem um princípio normativo de capacidade mínima suficiente nem resolver determinístico de preferência de eficiência, permitindo over-selection de capacidade mesmo quando um modelo mais econômico já satisfazia plenamente o quality floor da fase.
expected:
1. Formalizar o princípio normativo de Minimum Sufficient Capability (MSC): utilizar o menor esforço e custo que satisfaça o quality floor da fase;
2. Separar a avaliação técnica individual (evaluations[]: sufficient, uncertain, insufficient) do ranking e seleção final de primário;
3. Implementar resolver determinístico de preferência de eficiência (Efficiency Preference Policy) desacoplado de fornecedor;
4. Condicionar a escalada para modelos mais caros/pesados a causas factuais obrigatórias comprovadas (efficient_candidate_insufficient, efficient_candidate_uncertain, checker_family_independence, operator_pinned, pre_dispatch_unavailable, proven_empirical_failure);
5. Proibir estritamente argumentos subjetivos de over-selection ("frontier model", "mais forte", "maior capacidade de raciocínio", "tier heavy exige modelo máximo");
6. Aplicar o princípio de menor esforço suficiente também ao reasoning effort (high sobre xhigh no mesmo modelo por padrão);
7. Atualizar schemas, prompts e validador mecânico scripts/validate_classification.py;
8. Cobrir com 8 casos de teste determinísticos obrigatórios em scripts/tests/test_dynamic_primary_selection.py.
impact: elimina a sobre-seleção de modelos caros quando modelos econômicos forem tecnicamente suficientes, reduzindo o custo operacional das tarefas sem degradar a qualidade técnica.
dedup: T019 introduziu a seleção dinâmica de primário v3; T027 instituiu o despacho orçado; T031 fecha a lacuna normativa e algorítmica de Minimum Sufficient Capability.

## Spec
### Acceptance criteria
- AC01: prompts/classifier.md atualizado com o princípio normativo de Minimum Sufficient Capability, regras de desempate por eficiência e proibição de justificativas de over-selection.
- AC02: prompts/orchestrator-perfis.md atualizado com a formalização da política efficiency_preference configurável no perfil.
- AC03: schemas/classification-result-v3.schema.json estendido com selection_basis (minimum_sufficient, escalation, pinned, only_available) e escalation_reason.
- AC04: scripts/validate_classification.py implementa validação mecânica estrita de frases proibidas de over-selection e validação de consistência entre evaluations, selection_basis e escalation_reason.
- AC05: scripts/validate_classification.py disponibiliza o resolver determinístico resolve_minimum_sufficient(...).
- AC06: Reasoning effort respeita o princípio de menor esforço suficiente (high sobre xhigh por padrão no mesmo modelo).
- AC07: 8 casos de teste contratuais obrigatórios implementados e validados em scripts/tests/test_dynamic_primary_selection.py.
- AC08: Versão do pacote incrementada para 0.18.0 com registro no CHANGELOG.md e distribution-manifest.json.

## Evidence
evidence/T031-r01.md
