format_version: 1
lineage_digest: 9215eb10b9e6ed42
integration_base: 2aca4f42bdd399c943ad4a5afeb403725018f6ae
generated_by: T024

## Retired identities
| retired_id | retired_file | lineage | live_id | live_file | reason |
| :--- | :--- | :--- | :--- | :--- | :--- |
| T013 | _tl-orc/project/tasks/T013-regras-contratuais-de-esperas-liveness-e-lote-autorizado.md | local | T020 | _tl-orc/project/tasks/T020-regras-contratuais-de-esperas-liveness-e-lote-autorizado.md | id_collision_with_upstream_v0.9.0 |
| T014 | _tl-orc/project/tasks/T014-politica-global-de-participantes-e-perfis-padrao.md | local | T021 | _tl-orc/project/tasks/T021-politica-global-de-participantes-e-perfis-padrao.md | id_collision_with_upstream_v0.10.0 |
| T015 | _tl-orc/project/tasks/T015-context-economy-selective-retrieval-e-handoff-verificavel.md | local | T022 | _tl-orc/project/tasks/T022-context-economy-selective-retrieval-e-handoff-verificavel.md | id_collision_with_upstream_v0.11.0 |
| T012 | _tl-orc/project/tasks/T012-piloto-retomada-curta-entre-ciclos.md | local | T023 | _tl-orc/project/tasks/T023-piloto-retomada-curta-entre-ciclos.md | intra_lineage_duplicate_since_ad4625e |

## Evidence prefix map (R-E1: files are never renamed)
| evidence_path | belongs_to |
| :--- | :--- |
| _tl-orc/project/evidence/T013-r01.md | T020 |
| _tl-orc/project/evidence/T013-contract-tests.py | T020 |
| _tl-orc/project/evidence/T014-r01.md | T021 |
| _tl-orc/project/evidence/T014-participant-policy-tests.py | T021 |
| _tl-orc/project/evidence/T015-r01/ … T015-r03b/ , T015-r03b.md | T022 |
| _tl-orc/project/evidence/T015-verification.md | T015 (upstream) |
| _tl-orc/project/evidence/T012-r01.md | T023 |
| _tl-orc/project/evidence/T012-support/r01/ | T023 |
| _tl-orc/project/evidence/T012-verification.md | T012 (canonical) |

## Historical provenance (NOT operational dependencies)
| from | to | nature |
| :--- | :--- | :--- |
| T022 | T023 | T022 nasceu da leitura posterior do relatório do piloto (evidence/T012-r01.md); nunca dependeu operacionalmente dele |

## Replayability
| unit | state | reason |
| :--- | :--- | :--- |
| T023 | not_reconstructable | checkpoint T009 r02 não reconstruível pelo histórico Git; 10 de 12 checksums do índice do pacote curto não correspondem às fontes preservadas nem a commit algum; Braço A leu a árvore viva e não a cópia isolada. Artefatos preservados por cópia em evidence/T012-support/r01/ servem à auditoria, não ao replay. |
