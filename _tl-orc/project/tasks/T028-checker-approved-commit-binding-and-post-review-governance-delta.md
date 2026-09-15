id: T028
title: Checker Approved Commit Binding and Post-Review Governance Delta v1
type: gov
deliverable: none
standalone: true
method: native
status: draft
state_revision: 1
depends_on: [T027]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (ratificação do Post-Close Audit do B004 e identificação da necessidade de binding explícito do commit aprovado pelo Checker)
decisions: []
spec_author: orchestrator
spec_revision: pending
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_id: pending
content_paths: [docs/WORK_MODEL.md, schemas/batch.schema.json, prompts/orchestrator-playbook.md]

## Finding
source: auditoria pós-encerramento do lote Canary B004 na Story connector:2-8 do ThingLab Platform em 2026-09-14.
observed: o Checker independente R02 auditou e aprovou o commit 102cec41d3f7fc541b3830e4d13244df71a15b2c. Antes do merge em main, um commit subsequente (86106359942a492f74151b753f7f8976bcf64166) foi gerado para alinhar uma única linha do cabeçalho documental do dev-report. O método upstream valida expected_tree_checkpoint na admissão da unidade, mas não possui um campo explícito vinculando o commit auditado pelo Checker (checker_approved_commit) ao candidato de integração (integration_candidate_commit), nem normatiza quando um delta pós-revisão pode ser aceito sem nova rodada de Checker independente.
expected:
1. Formalizar os campos checker_approved_commit e integration_candidate_commit no schema e no ciclo de vida do lote;
2. Estabelecer a regra de que qualquer mutação em arquivos de produção ou teste pós-aprovação exige obrigatoriamente nova rodada de revisão pelo Checker independente;
3. Definir formalmente a exceção post_review_governance_delta_only, restrita a caminhos puramente documentais/metadados com prova auditável de que zero linhas de produção ou teste foram alteradas.
impact: elimina ambiguidade na proveniência do código integrado e garante que nenhum código de produto escape à revisão independente.
